# SPEC-004: 옵트인 스트리밍 모니터 모드

**Phase:** P2 · **상태:** Partially Implemented (2026-07-02, Gate E-G/B/A/C/D 전체 확장 완료 2026-07-03) · **의존성:** SPEC-018(Gate 러닝 집계 공유 인프라) 완료

> **정정(2026-07-03)**: 아래 원래 구현 노트가 "SPEC-001의 shared_metrics 계층"을 언급하지만,
> 재검토 결과 `SPEC-001-gate-aggregation-unification.md`은 실제로는 다른 문제
> (monitor.py 실시간 계산 vs `serve/loader.py` legacy-JSON fallback의 중복 공식 문제)를
> 다루며 이 러닝 집계 일반화 작업과 무관하다. 이 작업은 **SPEC-018**로 신규 추적한다.

> **구현 노트 (2026-07-02)**: REQ-1(옵트인 `retention_mode`/`window_size` 파라미터), REQ-3(4개 API의
> 매 호출 `UserWarning`), REQ-4(`window_size` 양의 정수 검증)는 **완전히 구현**했다.
> REQ-2는 **의도적으로 축소된 범위**로 구현했다 — 정직하게 명시한다:
> - `self.tasks`(= `tcr_tracker.tasks`)는 windowed 모드에서 `tcr_tracker._tasks`를
>   `deque(maxlen=window_size)`로 교체해 실제로 O(window_size)에 수렴한다.
> - **Gate A/C의 TCR 컴포넌트(`tcr_pct`, `full_success`/`partial_success`/`failures`)만
>   `PerformanceMonitor._running_tcr_agg`(record_task() 시점에 갱신되는 러닝 집계)를 통해
>   전체 이력 기준으로 계산된다** — `_RunningTCRView`가 `TaskCompletionTracker.calculate_tcr()`와
>   동일한 형태로 이 값을 Gate A/C의 `aggregate.compute()`에 주입한다.
> - **그 외 모든 Gate 지표(A의 instruction_adherence/goal_alignment/plan_coherence/
>   subtask_completion/context_retention/knowledge_retention, B/D/F/G 전체, C의
>   SLA breach 이외 나머지 — reproducibility/fault_tolerance/graceful_degradation/
>   retry_consistency/idempotency 등)는 windowed 상태의 태스크 목록(`tasks` 파라미터)만으로
>   재계산된다.** (Gate E는 2026-07-03 SPEC-018 Phase 1로 전체 이력 기준으로 전환됨 —
>   아래 구현 노트 참조.) 이 지표들은 개별 `TaskResult.extra` 딕셔너리를 순회해 계산되므로,
>   진짜 러닝 집계로 전환하려면 7개 Gate의 evaluator/aggregate 전체를 SPEC-018이 제안한
>   `shared_metrics` 계층으로 재구조화해야 한다 — 이는 세션 하나에서 안전하게 완결할 수 있는
>   범위를 넘어서 단계별(Phase 0-6) 롤아웃으로 진행 중이다. 따라서 **Acceptance의 "Gate
>   점수(A~G)가 전체 이력 기준 집계와 일치"는 TCR 컴포넌트 + Gate E에 한해서만 성립하며,
>   나머지 컴포넌트는 windowed 부분집합 기준으로 계산된다.**
> - 다른 트래커(`accuracy_evaluator`, `quality_evaluator`, 보안 트래커 5종,
>   `tool_analyzer`, `agent_coordination_tracker` 등)의 내부 리스트는 windowed 모드에서도
>   여전히 무제한 증식한다 — 이번 스펙은 `tcr_tracker._tasks`(= `self.tasks`)만 캡핑했다.
>   따라서 Acceptance의 "메모리 사용량이 O(window_size)에 수렴" 검증은 `self.tasks` 자체에는
>   성립하지만, 프로세스 전체 메모리 사용량에는 아직 성립하지 않는다.
> - 테스트: `tests/test_streaming_retention_mode.py`(신규 21건) + 기존 2,947건 전량 통과
>   (총 2,968 passed, 1 skipped, 회귀 없음).

> **구현 노트 (2026-07-03, SPEC-018 Phase 0-1)**: 신규 `agent_evaluator/gates/shared_metrics.py`
> 에 범용 러닝 집계 프리미티브(`RunningAverage`/`RunningSum`/`RunningWindow`/`RunningLastValue`/
> `RunningCount`)와 파일럿 `GateESharedAgg`를 추가했다. `gates/gate_e_security/aggregate.py::
> compute()`가 `shared_running: Optional[dict] = None` 인자를 받아 windowed 모드에서는
> `GateESharedAgg.snapshot()`을, "full" 모드(기본값)에서는 기존 `tasks` 재계산 경로를 그대로
> 사용한다. **구현 중 실제로 순서 버그를 발견하고 수정했다**: `record_task()`의 보안 트래커
> enrichment(`input_sanitization`/`output_leakage`/`privilege_escalation`/`tool_chain_attack`/
> `tool_authorization`을 `task_result.extra`에 채워 넣는 블록)가 TCR 러닝 집계 갱신보다 **나중에**
> 실행되므로, `_running_gate_e_agg.update()`를 TCR 갱신 직후에 호출하면 아직 enrichment가
> 안 된 task_result를 집계해 windowed 모드의 Gate E 점수가 full 모드와 달라지는 버그가
> 생겼다 — 이는 계획서(Plan) 검토 단계의 full-vs-windowed 교차검증 테스트로 실제로 잡혔다.
> `_running_gate_e_agg.update()` 호출을 보안 enrichment 블록 **이후**로 옮겨 수정했다.
> 신규 테스트 `TestWindowedGateERunningMetrics`(5건 — 이력 반영, 세부 지표 일치, full-vs-windowed
> 교차검증, full 모드 불변 확인, 보안 데이터 전무 시 None 유지) 추가. 전체 스위트
> 3,117 passed, 1 skipped, 회귀 0건.
>
> **완료(2026-07-03, SPEC-018 Phase 2-7)**: Gate F/G/B/A/C/D 전체에 동일한 패턴을 확장했다.
> Gate C `retry_consistency`(task_id 프리픽스 카디널리티 LRU 캡, 기본 5,000)와 Gate D의
> ttft_variability/cost_predictability(원시값 슬라이딩 샘플, 기본 2,000 — `window_size`와
> 독립)는 사용자 별도 승인(2026-07-03) 후 **의도적으로 승인된 근사**로 구현했다(정확한
> 전체 이력 재계산과 항등이 아닐 수 있음 — 캡/샘플 크기 이내에서는 항등, 초과 시 근사).
> Gate D의 efficiency/resource_budget과 p95 latency(원래부터 무제한인 `latency_tracker`
> 기반이라 애초부터 전체 이력 반영)는 정확하다. 이로써 REQ-2는 사실상 전체 범위로
> 완료됐다 — 유일하게 남은 예외는 Gate C의 `sla_results`(원본 리스트, Gate D의 p95
> threshold 평균 계산용)가 여전히 windowed 부분집합 기준이라는 점(SPEC-018 REQ-7 참조,
> Gate 점수 자체에는 영향 없음). 상세 설계·테스트·리스크는 `SPEC-018-*.md`가 단일
> 소스다 — 이 문서는 더 이상 phase별 노트를 추가하지 않는다.

## Context

- `agent_evaluator/core/trackers/monitor.py:6285,6291` `self.tasks.append(t)` — 상한(maxlen) 없이 무제한 증식.
- `monitor.py:516-518`에 별도로 `_recent_tasks_cache: deque(maxlen=10000)`가 존재하지만, 이는 "최근 N개 윈도우 조회"(`monitor.py:3974` 주석: "window_seconds <= 300s 이면 O(k) 필터링") 용도의 **캐시**일 뿐, `_compute_harness_groups`가 실제로 읽는 `self.tasks` 원본은 여전히 무제한이다.
- `self.tasks`는 `_compute_harness_groups` 외에도 아래 지점에서 **전체 참조**된다 (2026-07-02 세션에서 직접 확인):
  - `monitor.py:3986,4084,4127` — `get_report_by_type`/`get_report_by_framework`
  - `monitor.py:6472,6528,6747,6822` — 여러 리포트/내보내기 경로
  - `monitor.py:6282-6291` — `export_by_framework` (tasks를 통째로 swap-in/out)
  - `monitor.py:6914` — **`register_aggregator`로 등록한 사용자 정의 함수에 `self.tasks` 전체를 그대로 인자로 전달하는 공개 API**
- 따라서 `self.tasks`에 무조건 상한을 거는 것은 **사용자의 커스텀 aggregator나 `export_by_framework` 등을 조용히 오작동시키는 breaking change**다(2026-07-02 세션에서 이전 제안의 오류로 확인·정정됨).

## Goals

- 장시간 구동되는 프로덕션 모니터 프로세스에서 메모리가 무한 증식하지 않는 **옵트인** 경로를 제공한다.
- 기본 동작(풀 리텐션)은 절대 변경하지 않는다.

## Non-Goals

- `retention_mode`의 기본값 변경.
- `register_aggregator` 등 기존 공개 API의 시그니처 변경.

## Requirements

- **REQ-1**: `PerformanceMonitor(retention_mode: Literal["full", "windowed"] = "full", window_size: int = 10000)` 파라미터 추가. 기본값 `"full"`은 현재 동작(무제한 리스트)과 100% 동일해야 한다.
- **REQ-2**: `retention_mode="windowed"`일 때 `self.tasks`는 내부적으로 `deque(maxlen=window_size)`로 동작한다. Gate 점수 계산에 필요한 러닝 집계(합/카운트 등, SPEC-001의 shared_metrics 구조 재사용)는 `record_task()` 호출 시점에 갱신되어 윈도우 밖으로 밀려난 데이터의 집계 기여분도 유지된다.
- **REQ-3**: `retention_mode="windowed"` 상태에서 `get_report_by_type`/`get_report_by_framework`/`export_by_framework`/`register_aggregator` 호출 시, 이 기능들이 윈도우 밖 데이터에는 접근할 수 없다는 사실을 알리는 `UserWarning`을 **매번** 발생시킨다(로그 레벨이 아니라 warning으로 강제 — 조용한 오작동 금지).
- **REQ-4**: `window_size`는 양의 정수만 허용하며, `__post_init__`(또는 이에 준하는 검증)에서 0 이하 값에 대해 `ValueError`를 발생시킨다.

## Interface

```python
# 변경 전
monitor = PerformanceMonitor(output_dir="results/")

# 변경 후 (하위호환 — retention_mode 생략 시 기존과 동일)
monitor = PerformanceMonitor(output_dir="results/")  # retention_mode="full" 기본값, 동작 변경 없음
monitor = PerformanceMonitor(output_dir="results/", retention_mode="windowed", window_size=5000)  # 신규 옵트인
```

## Acceptance

- `retention_mode` 미지정 시 기존 2,795개 테스트가 **수정 없이** 100% 통과.
- `retention_mode="windowed"` + 10만 건 태스크 주입 시 메모리 사용량이 프로파일링(`tracemalloc` 등)으로 O(window_size)에 수렴함을 확인 (O(n) 증가하지 않음).
- `retention_mode="windowed"` 상태에서 `register_aggregator` 호출 시 `UserWarning`이 발생하는지 검증.
- `retention_mode="windowed"`에서도 Gate 점수(A~G)가 전체 이력 기준 집계와 일치하는지 검증(윈도우 밖 데이터도 러닝 집계에는 반영되어야 하므로).

## Compatibility

- 완전 하위호환 — 신규 옵션 추가, 기본값은 현행 유지.

## Rollout

1. SPEC-001의 shared_metrics 계층 완성 후 착수 (러닝 집계 설계를 그 위에 얹는 것이 훨씬 단순함).
2. 베타 플래그(`retention_mode="windowed"`)로 1~2개 마이너 버전 노출.
3. 사용자 피드백 수렴 후 안정화, 문서(`Docs/07_OPERATIONS.md`)에 프로덕션 장시간 구동 가이드로 추가.

## Risks

- 사용자가 `"windowed"`를 켰는데 REQ-3 경고를 무시하고 넘어가 커스텀 aggregator 결과가 부분 데이터 기준으로 조용히 달라질 위험 → 경고를 `UserWarning`(기본적으로 콘솔에 노출됨)으로 강제하고, 문서에 명확히 트레이드오프를 기술한다.
- 러닝 집계와 실제 `self.tasks`(windowed) 간 이중 관리 로직이 버그의 새 원천이 될 수 있음 → SPEC-003의 단일 패스 구조를 재사용해 집계 로직을 한 곳에 모아 리스크를 최소화한다.
