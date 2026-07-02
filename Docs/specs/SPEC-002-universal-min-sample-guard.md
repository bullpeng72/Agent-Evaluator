# SPEC-002: 전 Gate 공통 최소 표본 가드

**Phase:** P0 · **상태:** Implemented (2026-07-02) · **의존성:** 없음 (독립 착수 가능)

> **구현 노트**: `monitor.py::_compute_harness_groups`에 `_min_sample_warning()` 헬퍼와 `PerformanceMonitor(min_samples_default=3)` 파라미터를 추가해 Gate A/B/C/E/F/G에 `insufficient_data_warnings`를 적용했다(Gate D는 기존 구현 유지, SLA 경고만 Gate C와 공유하도록 `_sla_warning` 변수로 통합). 이벤트 기반 지표(Gate F coordination/tool_selection, Gate G tool_coverage)는 Non-Goals에 따라 제외 — 백로그 추적. 테스트: `tests/test_min_sample_guard.py`(신규 14건) + 기존 2,797건 전량 통과(총 2,811 passed, 1 skipped, 회귀 없음).

## Context

- `agent_evaluator/core/trackers/monitor.py:3355` `_ttft_min_samples`, `:3423` `_cost_min_samples` (기본값 5), `:3488-3510` `_d_insufficient` 리스트, `:3899` `"insufficient_data_warnings"` — 이 표본 부족 가드 메커니즘은 **Gate D에만** 존재한다.
- SLA breach 데이터(`monitor.py:3074-3082`)는 Gate C의 `_rel_vals`에도 반영되지만(`:3082`), 표본 부족 경고(`:3509-3510` `f"sla: {len(_sla_results)} samples < recommended_min=5"`)는 Gate D의 `_d_insufficient`에만 추가되고 Gate C의 `details`에는 동등한 경고가 없다.
- Gate A/B/E/F/G에는 표본 수 검증 로직이 전혀 없다 — task 1~2건만으로도 확정 점수가 산출되고 경고 없이 CI/CD 게이트(`agent-eval gate`)를 통과할 수 있다.

## Goals

- 모든 Gate가 표본 수 미달 시 동일한 스키마로 경고를 노출하도록 표준화한다.
- 여러 Gate가 같은 원본 데이터를 공유하는 경우(SLA→C&D), 경고도 공유 데이터 단위로 한 번 판정해 관련된 모든 Gate에 동시 반영한다.

## Non-Goals

- 신뢰구간/부트스트랩 등 통계적 엄밀성 강화(별도 스펙 후보) — 이번 스펙은 "표본 미달 여부 표시"까지만 다룬다.
- Gate D의 기존 `min_samples=5` 기본값 변경.
- **이벤트 기반 지표의 min-sample 가드 제외**: Gate F의 `coordination_score`(AgentCoordinationTracker, 분모 `total_interactions`)·`tool_selection_f1`(ToolSelectionTracker, 분모 `total_evaluations`), Gate G의 `tool_coverage`(ToolCallAnalyzer, 분모 `total_calls`) 3개 지표는 태스크 수가 아니라 이벤트/호출 수를 분모로 쓰므로, 이번 스펙의 "task 기반 min_samples=3" 契約과 자연스럽게 비교되지 않는다. 강제로 끼워 맞추면 의미가 혼동된 경고가 생기므로 이번 스펙에서 명시적으로 제외한다. → **[SPEC-012](SPEC-012-event-based-min-sample-guard.md)로 구현 완료 (2026-07-02)**.

## Requirements

- **REQ-1**: 각 Gate 계산 로직(향후 SPEC-001의 `gates/gate_x` 모듈, 그 전이라면 `monitor.py` 내 해당 섹션)에 `min_samples: int = 3` 계약을 도입한다. 새 Gate/Config 추가 시 이 값을 생략할 수 없도록 (예: 데이터클래스 필수 필드 또는 린트 규칙으로) 강제한다.
- **REQ-2**: 표본 미달 시 해당 Gate의 `details`에 `"insufficient_data_warnings": List[str] | None`을 Gate D와 동일한 문자열 포맷(`"<metric>: <n> samples < min_samples=<min>"`)으로 추가한다.
- **REQ-3**: SLA처럼 원본 데이터가 여러 Gate에 공유되는 경우, 표본 부족 판정을 데이터 소스 단위로 한 번만 계산하고 그 경고를 관련된 모든 Gate의 `details`에 동시에 반영한다 (Gate C와 D가 서로 다른 결론을 내리지 않도록).
- **REQ-4**: 표본 미달이 Gate 점수 자체를 `None`으로 만들지는 않는다(기존 동작 유지) — 어디까지나 경고 노출이 목적이며, 점수 산출 자체를 막는 것은 별도 논의 대상.

## Interface

`details` 딕셔너리에 키 추가만 발생하므로 기존 공개 API 시그니처 변경 없음.

```python
# 변경 후 예시 (Gate A details)
{
    "tcr_pct": 85.0,
    ...,
    "insufficient_data_warnings": ["goal_alignment: 2 samples < min_samples=3"],  # 신규
}
```

## Acceptance

- task 1~2건짜리 픽스처로 A/B/C/E/F/G 각각에서 `insufficient_data_warnings`가 non-null로 채워지는지 검증하는 테스트 추가.
- SLA 표본 부족 픽스처(4건)에서 Gate C와 Gate D의 `insufficient_data_warnings`에 **동일한** SLA 경고 문자열이 동시에 나타나는지 검증.
- 표본이 충분한 기존 픽스처에서는 `insufficient_data_warnings`가 여전히 `None`인지 회귀 검증 (기존 2,795개 테스트 영향 없음 확인).

## Compatibility

- Additive — 기존에 없던 필드가 추가되는 것이므로 하위호환 유지.
- 기존 사용자가 새로 뜨는 경고에 대해 문의할 수 있음 → CHANGELOG/릴리스 노트에 명시.

## Rollout

1. Gate D의 기존 패턴(`_ttft_min_samples`, `_d_insufficient`)을 참조 구현으로 삼아 공통 헬퍼 함수 추출.
2. Gate A/B/C/E/F/G 순으로 적용 (Gate C는 SLA 공유 로직 때문에 Gate D와 동시 작업).
3. 기존 테스트 스위트 전량 통과 확인 후 병합.

## Risks

- SLA처럼 공유 데이터의 표본 판정 로직을 한 곳으로 모으는 과정에서 Gate C/D 각각의 기존 계산 순서를 건드릴 수 있음 → SPEC-003(단일 패스 정리)과 함께 진행하면 충돌 위험 감소.
