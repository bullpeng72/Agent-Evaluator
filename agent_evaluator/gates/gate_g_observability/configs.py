"""
agent_evaluator.gates.gate_g_observability.configs
=====================================================
Gate G(Observability) Harness Config 데이터클래스 4종.

SPEC-000: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ObservabilityConfig:
    """Trace 완성도 및 감사 이벤트 SLO 설정.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    observability=ObservabilityConfig(min_coverage=0.99))
        def agent(question, ground_truth=""): ...
    """
    required_span_attributes: list[str] = dataclasses.field(
        default_factory=lambda: ["task_id", "task_type", "execution_time"]
    )
    check_trace_continuity: bool = True
    audit_events: list[str] = dataclasses.field(default_factory=list)
    min_coverage: float = 0.95

    def __post_init__(self) -> None:
        import warnings as _w
        # min_coverage는 trace_coverage(0-1)와 >= 비교된다(evaluators.py:94의 slo_met).
        # 범위 밖 값은 SLO 판정을 항상 통과 또는 항상 미달로 고정시킨다.
        if not (0.0 <= self.min_coverage <= 1.0):
            _w.warn(
                f"ObservabilityConfig: min_coverage={self.min_coverage} 은 [0.0, 1.0] 범위를 "
                f"벗어납니다. trace_coverage(0-1)와 비교되므로 음수면 SLO가 항상 통과, "
                f"1.0 초과면 항상 미달로 판정됩니다.",
                UserWarning, stacklevel=2,
            )


@dataclasses.dataclass
class ExplainabilityConfig:
    """응답 설명 가능성 요구 사항 설정 (Harness G — Observability).

    Example::

        @agent_eval(monitor, task_type="reasoning",
                    explainability=ExplainabilityConfig(require_reasoning=True, require_citations=True))
        def agent(question, ground_truth=""): ...
    """
    require_reasoning: bool = True
    reasoning_markers: list[str] = dataclasses.field(
        default_factory=lambda: ["because", "therefore", "since", "thus", "reason", "왜냐하면", "따라서"]
    )
    require_uncertainty_expression: bool = False
    uncertainty_markers: list[str] = dataclasses.field(
        default_factory=lambda: ["uncertain", "may", "might", "possibly", "not sure", "불확실"]
    )
    require_citations: bool = False
    citation_markers: list[str] = dataclasses.field(
        default_factory=lambda: ["according to", "based on", "source:", "ref:", "참고:"]
    )
    min_reasoning_length: int = 20
    check_action_explanation_alignment: bool = False

    def __post_init__(self) -> None:
        import warnings as _w
        # BUG-G7 fix: min_reasoning_length < 0 → 길이 검사 `len(response) >= negative` 가 항상 True
        # → 빈 응답도 reasoning 길이 기준 통과 → Gate G 인플레이션
        if self.min_reasoning_length < 0:
            _w.warn(
                f"ExplainabilityConfig: min_reasoning_length={self.min_reasoning_length} < 0 이므로 "
                f"기본값 20으로 보정됩니다. 음수 값은 길이 검사를 항상 통과시켜 Gate G를 인플레이션시킵니다.",
                UserWarning,
                stacklevel=2,
            )
            self.min_reasoning_length = 20


@dataclasses.dataclass
class ErrorDiagnosisConfig:
    """오류 진단 품질 측정 설정 (Harness G — Observability).

    실패 응답이 오류를 인정하고, 근본 원인을 제시하며, 대안을 제안하는지 평가한다.

    Example::

        @agent_eval(monitor, task_type="qa",
                    error_diagnosis=ErrorDiagnosisConfig(only_on_failure=True))
        def agent(question, ground_truth=""): ...
    """
    failure_acknowledgment_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "failed", "unable", "error", "could not", "오류", "실패", "불가능", "할 수 없"
    ])
    root_cause_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "because", "due to", "caused by", "reason", "왜냐하면", "때문에", "원인"
    ])
    suggestion_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "try", "suggest", "recommend", "alternatively", "시도", "제안", "대신"
    ])
    only_on_failure: bool = True
    acknowledgment_weight: float = 0.3
    root_cause_weight: float = 0.5
    suggestion_weight: float = 0.2

    def __post_init__(self) -> None:
        import warnings as _w
        # BUG-G5 fix: 음수 가중치 → diagnosis_score가 음수 → Gate G 점수 음수 방지
        for _attr, _default in [
            ("acknowledgment_weight", 0.3),
            ("root_cause_weight", 0.5),
            ("suggestion_weight", 0.2),
        ]:
            if getattr(self, _attr) < 0.0:
                _w.warn(
                    f"ErrorDiagnosisConfig: {_attr}={getattr(self, _attr)} < 0 이므로 "
                    f"기본값 {_default}으로 보정됩니다. 음수 가중치는 diagnosis_score를 음수로 만들어 "
                    f"Gate G 점수를 왜곡합니다.",
                    UserWarning,
                    stacklevel=2,
                )
                setattr(self, _attr, _default)
        # 가중치 합이 0이면 어떤 응답도 점수 없음 → 의도치 않은 Gate G 제외
        if (self.acknowledgment_weight + self.root_cause_weight + self.suggestion_weight) == 0.0:
            _w.warn(
                "ErrorDiagnosisConfig: 모든 가중치(acknowledgment_weight + root_cause_weight + "
                "suggestion_weight)의 합이 0.0입니다. diagnosis_score가 항상 0이 됩니다.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class LatencyAttributionConfig:
    """지연 원인 분석 평가 설정 (Gate G — Observability).

    전체 실행 시간 중 도구·모델·네트워크·미귀속 지연의 비율을 측정한다.

    Example::

        @agent_eval(monitor, task_type="tool_use",
                    latency_attribution=LatencyAttributionConfig(max_tool_time_ratio=0.6))
        def agent(question, ground_truth=""): ...
    """
    tool_latency_key: str = "tool_latencies"
    model_latency_key: str = "model_latency_ms"
    network_latency_key: str = "network_latency_ms"
    max_tool_time_ratio: float = 0.6
    max_unattributed_ratio: float = 0.3

    def __post_init__(self) -> None:
        import warnings as _w
        # BUG-G4 fix: 비율 값이 [0, 1] 범위 밖이면 Gate G 점수 왜곡
        # > 1.0: 해당 penalty가 항상 0 → attribution_score 항상 1.0 (인플레이션)
        # < 0.0: 해당 ratio가 항상 penalty 발생 → 완전 귀속 태스크도 감점 (디플레이션)
        for _attr, _default in [
            ("max_tool_time_ratio", 0.6),
            ("max_unattributed_ratio", 0.3),
        ]:
            _val = getattr(self, _attr)
            if not (0.0 <= _val <= 1.0):
                _w.warn(
                    f"LatencyAttributionConfig: {_attr}={_val} 은 [0.0, 1.0] 범위를 벗어납니다. "
                    f"기본값 {_default}으로 보정됩니다. "
                    f">1.0이면 해당 페널티가 항상 0이 되어 Gate G를 인플레이션시키고, "
                    f"<0.0이면 완전 귀속 태스크도 감점되어 Gate G를 디플레이션시킵니다.",
                    UserWarning,
                    stacklevel=2,
                )
                setattr(self, _attr, _default)
