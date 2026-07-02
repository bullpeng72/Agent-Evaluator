# SPEC-012: 이벤트 기반 지표 최소 표본 가드 (Gate F/G)

**Phase:** P1 (SPEC-002 후속) · **상태:** Implemented (2026-07-02) · **의존성:** SPEC-002(구현 완료) — Non-Goals에서 명시적으로 제외됐던 3개 지표를 다룬다. SPEC-011(구현 완료) — Gate G `tool_coverage`가 처음으로 실제 값을 반환하게 되어 이 가드의 실효성이 생겼다.

> **구현 노트**: `gates/base.py::_min_sample_warning()`에 `unit: str = "samples"` 파라미터 추가(기존 호출부 전부 하위호환 유지 확인). `gate_f_multiagent/aggregate.py`가 `total_interactions`/`total_evaluations`를 지역 변수로 캡처해 `coordination_score`/`tool_selection_f1` 경고를 `unit="interactions"`/`"evaluations"`로 추가. `gate_g_observability/aggregate.py`가 `total_calls`를 캡처해 `tool_coverage` 경고를 `unit="calls"`로 추가. `tests/test_min_sample_guard.py`에 `TestEventBasedInsufficientSamples`(4건) 신규 추가, 기존 `test_event_based_metrics_excluded_from_guard`는 `test_event_based_metrics_zero_count_not_flagged`로 의미 갱신(count=0은 여전히 미경고 — 회귀 아님). 기존 `tests/test_gates_gate_f_migration.py::test_expected_values`가 새 경고 2건을 기대하도록 갱신(의도된 동작 변화). 전체 스위트 2,947 passed, 1 skipped, 회귀 0건.

## Context

- `Docs/specs/SPEC-002-universal-min-sample-guard.md`의 Non-Goals: "Gate F의 `coordination_score`(AgentCoordinationTracker, 분모 `total_interactions`)·`tool_selection_f1`(ToolSelectionTracker, 분모 `total_evaluations`), Gate G의 `tool_coverage`(ToolCallAnalyzer, 분모 `total_calls`) 3개 지표는 태스크 수가 아니라 이벤트/호출 수를 분모로 쓰므로... 이번 스펙에서 명시적으로 제외한다."로 명시되어 있고, "SPEC-000의 Gate F/G 이관 단계에서 함께 설계"를 권장했다. SPEC-000의 Gate F(2026-07-02)·Gate G(2026-07-02) 이관이 모두 완료된 지금이 이 권장 시점이다.
- `agent_evaluator/gates/gate_f_multiagent/aggregate.py:36-52` — `_coord_data`/`_ts_data` 계산부에서 `agent_coordination_tracker.calculate_coordination_score()["total_interactions"]`와 `tool_selection_tracker.get_accuracy_stats()["total_evaluations"]`을 이미 조건 분기(`> 0`)에 사용하고 있어, 카운트 값 자체는 이미 지역 변수로 존재한다(경고 생성에만 미사용).
- `agent_evaluator/gates/gate_f_multiagent/aggregate.py:127-137` — `_f_insufficient` 리스트는 현재 `consensus`/`propagation`/`agent_role`/`conflict_resolution` 4개 task 기반 지표만 검사하고, `coordination_score`/`avg_tool_selection_f1`은 제외되어 있다.
- `agent_evaluator/gates/gate_g_observability/aggregate.py:42-47` — `_tool_coverage` 계산부에서 `tool_call_analyzer.get_efficiency_stats()["total_calls"]`를 조건 분기에 이미 사용한다.
- `agent_evaluator/gates/gate_g_observability/aggregate.py:109-119` — `_g_insufficient` 리스트는 `observability`/`explainability`/`error_diagnosis`/`latency_attribution` 4개만 검사하고 `tool_coverage`는 제외되어 있다.
- **SPEC-011로 인한 실효성 변화**: SPEC-011 이전에는 `self.tool_call_analyzer`가 존재하지 않는 속성명 오탈자로 인해 `tool_coverage`가 항상 `None`이었으므로, 이 지표에 대한 min-sample 가드는 그 자체로 의미가 없었다(측정값이 아예 없으니 "표본 부족" 경고도 낼 수 없었다). SPEC-011로 `tool_coverage`가 실제 계산되기 시작하면서, 도구 호출 1~2회만으로 산출된 `success_rate`가 통계적으로 무의미한데도 확정 점수처럼 노출될 위험이 처음으로 실재하게 됐다 — 이 스펙의 착수 시점이 SPEC-011 이후인 이유다.
- `gates/base.py::_min_sample_warning(metric_name, count, min_samples)`는 메시지 포맷이 `f"{metric_name}: {count} samples < min_samples={min_samples}"`로 고정되어 있다. "samples"라는 단어는 task 기반 지표에는 맞지만, interaction/evaluation/call 수를 "samples"라고 부르면 사용자가 태스크 수로 오인할 수 있다(SPEC-002 Non-Goals가 우려한 "혼동된 경고").

## Goals

- Gate F의 `coordination_score`·`avg_tool_selection_f1`, Gate G의 `tool_coverage` 3개 지표에 대해, 각각의 자연스러운 분모(상호작용 수·평가 수·호출 수)가 `min_samples_default` 미만일 때 `insufficient_data_warnings`에 경고를 추가한다.
- 경고 메시지가 "samples"가 아닌 실제 단위(예: "interactions", "evaluations", "calls")를 사용해 task 기반 경고와 명확히 구분되도록 한다.

## Non-Goals

- `min_samples_default`(현재 3, `PerformanceMonitor(min_samples_default=...)`) 자체의 기본값 변경 — 이벤트 기반 지표도 동일한 계약값을 그대로 재사용한다(별도 이벤트 전용 임계값 파라미터는 도입하지 않음 — 과도한 설정 표면 확장 방지).
- Gate D의 TTFT/Cost 5-표본 계약(자체 min_samples) 변경 — 이 스펙과 무관.
- `AgentCoordinationTracker`/`ToolSelectionTracker`/`ToolCallAnalyzer` 자체의 통계 계산 로직(예: `success_rate`, `overall_score`) 재검토 — 이 스펙은 경고 노출만 다룬다.

## Requirements

- **REQ-1**: `gates/base.py::_min_sample_warning()`에 `unit: str = "samples"` 파라미터를 추가한다. 기존 호출부(모두 기본값 사용)는 메시지가 완전히 동일하게 유지되어야 한다(하위호환).
- **REQ-2**: `gate_f_multiagent/aggregate.py`가 `total_interactions`(0 < count < min_samples_default)일 때 `"coordination_score: {n} interactions < min_samples={min}"` 경고를 `_f_insufficient`에 추가한다.
- **REQ-3**: `gate_f_multiagent/aggregate.py`가 `total_evaluations`(0 < count < min_samples_default)일 때 `"tool_selection_f1: {n} evaluations < min_samples={min}"` 경고를 `_f_insufficient`에 추가한다.
- **REQ-4**: `gate_g_observability/aggregate.py`가 `total_calls`(0 < count < min_samples_default)일 때 `"tool_coverage: {n} calls < min_samples={min}"` 경고를 `_g_insufficient`에 추가한다.
- **REQ-5**: 카운트가 0(측정 자체가 없음)이면 기존 컨벤션(SPEC-002)과 동일하게 경고를 내지 않는다 — "미측정"과 "표본 부족"을 혼동하지 않는다.
- **REQ-6**: 트래커 메서드 호출이 예외를 던지는 경우(기존에도 `try/except Exception: pass`로 방어됨) 카운트를 얻을 수 없으므로 경고도 생성하지 않는다(기존 방어 패턴 유지, 새로운 실패 모드를 만들지 않음).

## Interface

`details` 딕셔너리에 `insufficient_data_warnings` 리스트의 원소가 추가될 뿐, 키 자체는 신규 추가되지 않는다(기존 키 재사용). 공개 API 시그니처 변경 없음.

```python
# 변경 후 예시 (Gate F details, total_interactions=2, min_samples_default=3)
{
    ...,
    "coordination_score": 0.65,
    "insufficient_data_warnings": ["coordination_score: 2 interactions < min_samples=3"],  # 신규
}
```

## Acceptance

- `total_interactions`가 1~2인 픽스처(예: `AgentCoordinationTracker.track_interaction()` 2회 호출)에서 Gate F의 `insufficient_data_warnings`에 `"coordination_score: 2 interactions < min_samples=3"`이 포함되는지 검증.
- `total_evaluations`가 1~2인 픽스처(`ToolSelectionTracker.evaluate_selection()` 2회 호출)에서 `"tool_selection_f1: 2 evaluations < min_samples=3"` 포함 검증.
- `tool_calls`가 1~2건인 픽스처에서 Gate G의 `insufficient_data_warnings`에 `"tool_coverage: 2 calls < min_samples=3"` 포함 검증.
- 이벤트가 전혀 없는(count=0) 기존 픽스처(`tests/test_min_sample_guard.py::test_event_based_metrics_excluded_from_guard`)는 여전히 경고가 `None`인지 회귀 검증 — 테스트명/주석은 "제외"에서 "count=0이라 미측정 상태 유지"로 의미를 갱신한다.
- 표본이 min_samples_default 이상인 기존 픽스처에서 새 경고가 나타나지 않는지 전체 스위트로 회귀 검증.

## Compatibility

- Additive — 기존에 없던 경고 문자열이 조건부로 `insufficient_data_warnings` 리스트에 추가되는 것이므로 하위호환 유지. 단, 이 필드를 파싱해 `None` 여부만 확인하던 하류 코드가 있다면 새로 `None`이 아니게 되는 케이스가 생길 수 있다(표본이 부족한 경우에 한함) — 이미 SPEC-002가 도입한 필드의 자연스러운 확장이므로 major 변경은 아니다.

## Rollout

1. REQ-1: `gates/base.py::_min_sample_warning`에 `unit` 파라미터 추가(하위호환 확인).
2. REQ-2~3: Gate F aggregate.py 수정.
3. REQ-4: Gate G aggregate.py 수정.
4. `tests/test_min_sample_guard.py` 갱신 + 신규 이벤트 가드 테스트 3건 추가.
5. 전체 스위트 통과 확인 후 SPEC-012 상태를 `Implemented`로 갱신, `Docs/specs/README.md` 백로그에서 "이벤트 기반 지표 min-sample 가드" 항목 제거.

## Risks

- `AgentCoordinationTracker.calculate_coordination_score()`/`ToolSelectionTracker.get_accuracy_stats()`/`ToolCallAnalyzer.get_efficiency_stats()`가 반환하는 카운트 키 이름(`total_interactions`/`total_evaluations`/`total_calls`)이 향후 트래커 리팩터로 바뀌면 이 가드가 조용히 무력화될 수 있다 — 완화책: 각 aggregate.py의 기존 `> 0` 조건 분기와 동일한 키를 재사용하므로(이미 검증된 키), 트래커 API가 바뀌면 기존 점수 계산 로직도 함께 깨져 테스트가 실패하게 되어 있다(단일 실패점이 아님).
