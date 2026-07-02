# SPEC-004: 옵트인 스트리밍 모니터 모드

**Phase:** P2 · **상태:** Draft · **의존성:** SPEC-001(shared_metrics 계층) 선행 권장

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
