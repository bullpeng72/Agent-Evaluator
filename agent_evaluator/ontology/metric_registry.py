"""
agent_evaluator.ontology.metric_registry
===========================================
Phase 2(확장성 인프라) — 회귀/추천 지식이 여러 곳에 하드코딩돼 있던 걸 하나로 통합한다.

흡수한 곳(감사에서 확인, 코드 실사 기준):
- ``serve/routers/data.py::explain_anomaly_event()``의 ``suggestions`` dict(지표 3개)
  → ``ANOMALY_METRIC_SUGGESTIONS``
- ``reporting/comprehensive_report.py::_build_recommendations()``의 ``gate_labels``(7개)
  + native metric 임계값 규칙(4개) → ``GATE_GUIDANCE`` / ``NATIVE_METRIC_RULES``

두 소비 함수는 이제 이 모듈을 import해서 읽기만 한다 — 지식 자체는 여기 한 곳에만
존재한다. Phase 4의 RCA/추천 엔진도 같은 데이터를 그대로 재사용할 수 있다.

``NATIVE_METRIC_RULES``와 ``ANOMALY_METRIC_SUGGESTIONS``를 하나로 합치지 않은 이유:
둘 다 "이 지표가 나쁠 때 뭘 하라"는 목적은 같지만 트리거 방식이 다르다 — 전자는 절대
임계값(예: latency > 5.0s), 후자는 AnomalyDetector가 낸 상대 편차 기반 이벤트다. 억지로
합치면 두 소비처의 트리거 의미가 달라져 버린다.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class GateGuidance:
    """Gate 하나가 fail/warn일 때 보여줄 라벨 + 안내문."""
    label: str
    guidance: str


GATE_GUIDANCE: dict[str, GateGuidance] = {
    "A": GateGuidance(
        "Goal Achievement",
        "Improve TCR, accuracy, and hallucination metrics. Add InstructionConfig / "
        "GoalAlignmentConfig to your decorator to enable detailed tracking.",
    ),
    "B": GateGuidance(
        "Behavioral Integrity",
        "Strengthen loop detection and scope compliance settings. Tune LoopDetectionConfig "
        "/ ScopeConfig parameters.",
    ),
    "C": GateGuidance(
        "Reliability",
        "Review retry policies and fault-tolerance mechanisms. Enable FaultToleranceConfig "
        "to measure recovery rate.",
    ),
    "D": GateGuidance(
        "Performance Contract",
        "SLA threshold exceeded. Use SLAConfig to define response time limits and monitor "
        "P95 latency.",
    ),
    "E": GateGuidance(
        "Security Boundary",
        "Security threats detected. Enable enable_security_metrics=True and "
        "ThreatSeverityConfig.",
    ),
    "F": GateGuidance(
        "Multi-Agent Coordination",
        "Agent collaboration score is low. Add ConsensusConfig / ConflictResolutionConfig.",
    ),
    "G": GateGuidance(
        "Observability",
        "Strengthen explainability and observability metrics. Enable ExplainabilityConfig "
        "/ ObservabilityConfig.",
    ),
}


@dataclasses.dataclass(frozen=True)
class MetricThresholdRule:
    """네이티브 지표 하나가 절대 임계값을 위반했을 때 보여줄 규칙."""
    metric: str        # "tcr" | "accuracy" | "hallucination_rate" | "latency"
    direction: str      # "below"(미달 시 위반) | "above"(초과 시 위반)
    threshold: float
    priority: str        # "high" | "medium"
    title: str
    guidance: str

    def is_violated(self, value: float | None) -> bool:
        if value is None:
            return False
        if self.direction == "below":
            return value < self.threshold
        return value > self.threshold


NATIVE_METRIC_RULES: list[MetricThresholdRule] = [
    MetricThresholdRule(
        "tcr", "below", 75.0, "high", "TCR Improvement Needed",
        "Task completion rate is below 75%. Improve agent prompts and analyze failure cases.",
    ),
    MetricThresholdRule(
        "accuracy", "below", 70.0, "high", "Accuracy Improvement Needed",
        "Accuracy is below 70%. Review RAG context quality or ground_truth configuration.",
    ),
    MetricThresholdRule(
        "hallucination_rate", "above", 0.2, "high", "High Hallucination Risk",
        "Hallucination rate exceeds 20%. Strengthen fact-verification logic.",
    ),
    MetricThresholdRule(
        "latency", "above", 5.0, "medium", "Response Latency Improvement Needed",
        "Average response time exceeds 5s. Consider parallel processing or caching.",
    ),
]


def evaluate_native_metric_rules(
    *, tcr: float, accuracy: float, hallucination_rate: float, latency: float,
) -> list[MetricThresholdRule]:
    """``NATIVE_METRIC_RULES``를 실제 값에 대입해 위반된 규칙만 순서대로 반환한다."""
    values = {
        "tcr": tcr, "accuracy": accuracy,
        "hallucination_rate": hallucination_rate, "latency": latency,
    }
    return [rule for rule in NATIVE_METRIC_RULES if rule.is_violated(values.get(rule.metric))]


# explain_anomaly_event()가 AnomalyDetector 이벤트의 metric 필드로 조회하는 제안문.
ANOMALY_METRIC_SUGGESTIONS: dict[str, str] = {
    "accuracy": "Accuracy is low. Consider improving prompts or upgrading the model.",
    "latency": "Response time is high. Consider caching or parallel processing.",
    "error_rate": "Error rate is high. Agent stability review is required.",
}

ANOMALY_METRIC_DEFAULT_SUGGESTION = "Analyze this metric in detail."


# storage/sqlite_backend.py::_summarize_violations()가 FTS5 색인 대상으로 삼는
# 위반 유형 7종. 새 Gate B/E 체크가 추가되면 여기도 같이 갱신해야 한다 — 이 상수를
# 옮기지 않고 그 자리에 그대로 뒀다면 "추가는 했는데 여기 갱신을 깜빡하는" 실수가
# 예외 없이 조용히 색인 누락으로 이어졌다(이번 감사에서 확인).
VIOLATION_TYPES: tuple[str, ...] = (
    "loop_detection", "deadlock", "scope", "tool_parameter_safety",
    "tool_authorization", "privilege_escalation", "tool_chain_attack",
)
