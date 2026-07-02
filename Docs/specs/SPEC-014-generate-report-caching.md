# SPEC-014: `generate_report()` 재계산 방지 캐싱 (풀 리텐션 모드)

**Phase:** P2 · **상태:** Draft · **의존성:** 없음

## Context

- `agent_evaluator/core/trackers/monitor.py::generate_report()`(`:2897-2962`)는 호출될 때마다
  `_collect_layer1_metrics()`/`_collect_layer2_metrics()`/`_collect_security_metrics()`/
  `_compute_harness_groups()`(`:2926-2933`, Gate A-G 7개 `aggregate.compute()`를 전부 다시
  호출해 `tasks` 리스트를 처음부터 순회 — SPEC-000 이관 이후에도 캐싱 없이 매번 재계산)/
  `_generate_alerts()`/`_generate_recommendations()`를 **캐싱 없이 매번 처음부터 다시 실행**한다.
  직전 호출 이후 새 태스크가 하나도 기록되지 않았어도 완전히 동일한 계산을 반복한다(직접 코드
  대조로 확인 — 캐시 관련 필드나 dirty-flag가 전혀 없음).
- `generate_report()`는 코드베이스 내부에서 20곳 이상(직접 grep으로 확인, 예:
  `print_report()`(`:3797`)/`print_summary()`(`:3901`)/`print_detailed_report()`(`:3970`)/
  `save_to_file()` 경로/여러 export·dashboard 헬퍼)이 자체적으로 `report=None`이면
  `self.generate_report()`를 호출한다 — 사용자가 이 세 메서드를 연달아 호출하면(각각 `report`를
  넘겨주지 않는 한) Gate A-G 전체 집계가 3번 반복 계산된다.
- `record_task()`(`:1702` 부근)의 `auto_save` 로직(`:2046-2058`)은 `auto_save_interval`
  (기본 10)개마다 `save_to_file()`(내부적으로 `generate_report()` 호출)을 자동 실행한다 —
  장시간 세션에서 태스크가 누적될수록 `_compute_harness_groups()`가 전체 태스크 리스트를
  기준으로 반복 재계산되어(대략 `total_tasks / auto_save_interval`회), 세션 전체로 보면
  O(n²) 패턴에 가까운 누적 비용이 발생한다(SPEC-004가 windowed 모드의 TCR 컴포넌트에만
  러닝 집계를 도입했을 뿐, 이번 스펙이 다루는 "풀 리텐션 모드"에는 어떤 캐싱도 없다).
- **이미 기록된 태스크를 사후에 in-place로 수정하는 기존 패턴이 최소 2곳 존재한다** — 캐싱
  도입 시 반드시 무효화(invalidate)해야 할 지점:
  1. `decorators.py::_build_and_record()`의 BUG-E6 보정(`:4438-`) — `ThreatSeverityConfig`/
     `ThreatResponseConfig` 재평가가 `monitor.tcr_tracker._tasks`에서 방금 기록된 태스크를
     찾아 `task.extra`를 갱신한다. `record_task()`와 같은 동기 호출 스택 안에서 완료되므로
     race 위험은 없지만, 캐시 도입 시 이 지점도 무효화 대상에 포함해야 한다.
  2. SPEC-006(`agent_evaluator/decorators.py::_process_async_judge_targets()`)의 비동기 judge
     결과 반영 — `await ajudge(...)` 완료 후 `dataclasses.replace(..., llm_judge=result)`로
     이미 기록된 태스크를 patch한다. 이는 `record_task()` 호출과 분리된 별도의 `await` 지점이므로,
     그 사이에 다른 코드 경로가 `generate_report()`를 호출해 캐시를 "clean"으로 채워버리면
     이후 judge 패치가 캐시에 반영되지 않는 race가 이론적으로 가능하다 — 캐싱 설계에서 반드시
     명시적으로 처리해야 하는 지점(Requirements REQ-4).
- `monitor.py`는 이미 `self._lock = threading.RLock()`(`:609`)을 트래커 변경 보호에 광범위하게
  사용한다(`:1702` 등) — 새 캐시의 dirty-flag도 이 기존 락과 일관된 방식으로 보호해야 한다.

## Goals

- `generate_report()`가 직전 호출 이후 실제로 데이터가 바뀌지 않았다면 재계산을 건너뛰고 캐시된
  리포트를 즉시 반환하게 한다 — 특히 `print_report()`/`print_summary()`/`print_detailed_report()`
  연속 호출, `auto_save`의 반복 `save_to_file()` 호출 시 체감 가능한 이득을 목표로 한다.
- 캐시가 있어도 결과가 캐싱 없는 경우와 **완전히 동일**해야 한다(값이 다르면 안 됨 — 순수
  성능 최적화이지 동작 변경이 아니다).

## Non-Goals

- Gate A-G 점수 자체를 `record_task()` 시점에 O(1)로 갱신하는 진짜 증분(incremental) 알고리즘
  전환 — 이는 SPEC-004/SPEC-001이 이미 "shared_metrics 계층"이 선행돼야 하는 훨씬 큰 작업으로
  분류해 둔 범위이며, 이번 스펙은 그보다 훨씬 단순한 "직전 호출과 데이터가 같으면 재사용"
  메모이제이션이다.
- SPEC-004의 `retention_mode="windowed"` 자체 로직 변경 — 이번 캐싱은 `retention_mode`와
  무관하게 양쪽 모드 모두에 적용되지만, windowed 모드의 기존 러닝 집계 메커니즘은 그대로 둔다.

## Requirements

- **REQ-1**: `PerformanceMonitor.__init__`에 `self._report_cache: Optional[EvaluationReport] = None`,
  `self._report_cache_dirty: bool = True`를 추가한다.
- **REQ-2**: `record_task()`가 성공적으로 태스크를 추가한 직후(기존 `self._lock` 보호 블록 내부에서)
  `self._report_cache_dirty = True`로 설정한다.
- **REQ-3**: `generate_report(force_recompute: bool = False)`로 확장한다. `force_recompute=False`
  (기본값)이고 `not self._report_cache_dirty`이고 `self._report_cache is not None`이면 캐시를
  즉시 반환한다(재계산 완전히 스킵). 그 외의 경우 기존 로직대로 전체 재계산을 수행하고, 결과를
  `self._report_cache`에 저장하며 `self._report_cache_dirty = False`로 설정한다.
- **REQ-4**: 이미 기록된 태스크를 사후에 수정하는 기존 두 지점(BUG-E6 재평가, SPEC-006
  `_process_async_judge_targets`)이 수정 완료 후 반드시 `monitor._report_cache_dirty = True`
  (또는 이를 감싸는 공개 메서드 `invalidate_report_cache()`)를 호출하도록 배선한다 — 이 두 지점을
  놓치면 캐시가 사후 수정을 반영하지 못하는 회귀가 발생하므로 Acceptance에 각각 전용 테스트를
  둔다.
- **REQ-5**: dirty-flag 읽기/쓰기는 기존 `self._lock`(RLock, 재진입 가능)으로 보호해 `record_task()`
  와 `generate_report()`가 다른 스레드에서 동시 호출돼도 stale 캐시를 반환하지 않게 한다.
- **REQ-6**: `force_recompute=True`이면 dirty 상태와 무관하게 항상 재계산한다 — 이 스펙이 아직
  포착하지 못한 미래의 out-of-band 수정 지점을 위한 탈출구.

## Interface

```python
# 변경 전
report = monitor.generate_report()  # 매번 전체 재계산

# 변경 후 (하위호환 — 반환값 형태·내용 동일, 호출부 수정 불필요)
report = monitor.generate_report()                 # dirty 상태에 따라 캐시 재사용 또는 재계산
report = monitor.generate_report(force_recompute=True)  # 항상 재계산 (신규, 선택)
```

## Acceptance

- `record_task()` 없이 `generate_report()`를 연속 2회 호출하면, 두 번째 호출에서
  `_compute_harness_groups()`가 호출되지 않는지 `unittest.mock.patch`/spy로 검증하고, 두 리포트가
  동일한지(값 비교) 확인한다.
- 두 호출 사이에 `record_task()`를 1회 호출하면, 두 번째 `generate_report()`가 재계산을
  수행하고(spy로 확인) 새 태스크의 기여가 반영되는지 확인한다.
- BUG-E6 시나리오(threat_severity/threat_response 설정 + 보안 트래커 활성) 재현 픽스처에서,
  post-record 재평가 이후 호출한 `generate_report()`가 캐시가 아닌 갱신된 `extra`를 반영하는지
  검증(캐시 무효화가 정확히 배선됐는지 확인하는 회귀 테스트).
- SPEC-006 비동기 judge 시나리오 재현 픽스처에서, `_process_async_judge_targets()` 완료 후
  호출한 `generate_report()`의 `harness_groups`/`llm_judge` 관련 값이 judge 결과를 반영하는지 검증.
- `force_recompute=True`는 dirty=False 상태에서도 항상 재계산을 트리거하는지 확인.
- 캐싱 도입 전/후로 기존 `generate_report()`/`save_to_file()`/`print_report()` 등 관련 테스트
  전량이 무수정 통과하는지(값 자체는 절대 달라지면 안 됨) 회귀 검증.

## Compatibility

- 완전 하위호환 — `generate_report()`의 기존 0-인자 호출은 시그니처·반환값 형태 모두 그대로다.
  `force_recompute`는 기본값이 있는 신규 선택 파라미터.
- 캐시는 `PerformanceMonitor` 인스턴스 내부 상태이므로 직렬화(저장/로드)나 공개 API에 영향 없음.

## Rollout

1. REQ-1/2/3: 캐시 필드 + dirty-flag + `generate_report()` 단락(short-circuit) 로직 추가.
2. REQ-4: BUG-E6·SPEC-006 무효화 지점 배선 — 각각 전용 회귀 테스트로 고정.
3. REQ-5: 기존 `self._lock` 재사용해 스레드 안전성 확보.
4. `print_report()`+`print_summary()`+`print_detailed_report()` 연속 호출 시나리오로 수동
   벤치마크(재계산 스킵 전/후 소요 시간 비교) 진행 후 결과를 이 스펙 구현 노트에 기록.

## Risks

- **가장 큰 리스크**: 이번 스펙이 포착한 2곳(BUG-E6, SPEC-006 async judge) 외에, 향후 누군가
  이미 기록된 `TaskResult`를 사후에 in-place로 수정하는 새 코드를 추가하면서 캐시 무효화를
  빠뜨리면, `generate_report()`가 조용히 stale한 리포트를 반환하는 회귀가 생긴다. 완화책:
  "record_task() 이후 task_result.extra/llm_judge 등을 수정하는 모든 코드는 반드시
  `monitor.invalidate_report_cache()`를 호출해야 한다"는 불변식을 `CLAUDE.md`의 Architecture
  Principles에 명시하고, 코드 리뷰 체크리스트화한다.
- 동시성: `self._lock`이 이미 `record_task()` 경로 전반에 쓰이고 있어 재사용이 자연스럽지만,
  `generate_report()`가 락 안에서 무거운 재계산을 수행하게 되면(캐시 미스 시) 다른 스레드의
  `record_task()`가 그동안 블로킹될 수 있다 — dirty-flag 자체의 읽기/쓰기만 락으로 보호하고,
  실제 재계산(`_compute_harness_groups()` 등)은 락 밖에서 수행하는 방식(정확성보다 미세하게
  느슨한 격리)도 검토할 것.
