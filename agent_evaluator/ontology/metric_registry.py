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
    """네이티브 지표 하나가 절대 임계값을 위반했을 때 보여줄 규칙.

    단위 규약(SPEC-041): ``tcr``·``accuracy``·``hallucination_rate``는 전부 **퍼센트
    (0-100)**다 — 네이티브 트래커가 그 스케일로 낸다(``TaskCompletionTracker.calculate_tcr``
    ``* 100``, ``AccuracyEvaluator.get_accuracy_scores`` ``* 100``,
    ``HallucinationDetector.get_hallucination_rate()['overall_rate']`` ``* 100``).
    ``latency``만 절대 단위(초). ``recommend_fix``로 ``value``를 넘길 때도 퍼센트로.
    """
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
        # SPEC-041: threshold는 20.0(퍼센트) — 옛 0.2(분수)는 모든 호출자가 퍼센트
        # (HallucinationDetector.overall_rate = mean*100)를 넘기는데 0.2와 비교돼,
        # 환각률이 0.2%만 넘어도(사실상 항상) "exceeds 20%" 추천이 뜨는 오탐이었다.
        "hallucination_rate", "above", 20.0, "high", "High Hallucination Risk",
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


# AnomalyDetector가 내는 이벤트 유형(``AnomalyEvent.type``)별 조치 제안.
# SPEC-041: Phase 2 통합 때 이 dict가 잘못 옮겨졌다 — 실제 이벤트 유형은
# latency_trend/accuracy_drift/token_spike/error_surge/feedback_negativity/
# security_pattern인데 accuracy/latency/error_rate 3개로 들어와서, explain_anomaly_event()
# 와 recommend_fix가 항상 기본 제안만 냈고 detector.py는 자기 사본을 따로 들고 있었다.
# 이제 이게 정본이고, detector.AnomalyDetector.explain_event()·serve의 anomaly explain
# 엔드포인트·recommend_fix가 전부 이걸 읽는다(아래 anomaly_suggestion_for()).
ANOMALY_METRIC_SUGGESTIONS: dict[str, str] = {
    "latency_trend": (
        "Response time is trending up. Consider caching, parallel processing, or a lighter model."
    ),
    "accuracy_drift": "Accuracy has dropped. Review prompt improvements or fine-tuning.",
    "token_spike": (
        "Token usage has spiked. Consider reducing context length or adding a summarization step."
    ),
    "error_surge": (
        "Error rate has surged. Check agent stability and external service connections."
    ),
    "feedback_negativity": (
        "Negative feedback (regenerate/thumbs_down/etc.) has surged. "
        "Review recent prompt/model changes."
    ),
    "security_pattern": (
        "Security pattern detected. Strengthen input validation and review audit logs."
    ),
}

ANOMALY_METRIC_DEFAULT_SUGGESTION = "Analyze this metric in detail."

# recommend_fix가 쓰는 canonical 지표명 → AnomalyEvent.type. recommend_fix(gate, metric=…)
# 는 Gate details 어휘(latency/accuracy/error_rate)로 오는데, 위 dict는 이벤트 유형
# 어휘라 이 표로 이어 준다.
_METRIC_TO_ANOMALY_TYPE: dict[str, str] = {
    "latency": "latency_trend",
    "accuracy": "accuracy_drift",
    "error_rate": "error_surge",
}


def anomaly_suggestion_for(name: str | None) -> str | None:
    """이상탐지 조치 제안을 반환한다 — ``name``은 ``AnomalyEvent.type``
    (``"latency_trend"``)이거나 canonical 지표명(``"latency"``) 둘 다 받는다.
    아무 것도 안 맞으면 ``None``(호출자가 기본 제안으로 폴백)."""
    if not name:
        return None
    if name in ANOMALY_METRIC_SUGGESTIONS:
        return ANOMALY_METRIC_SUGGESTIONS[name]
    mapped = _METRIC_TO_ANOMALY_TYPE.get(name)
    if mapped:
        return ANOMALY_METRIC_SUGGESTIONS.get(mapped)
    return None


# SPEC-041: RCA(rca.diagnose)가 내는 top_detail_deltas 필드명·Gate details 키와,
# NATIVE_METRIC_RULES / ANOMALY_METRIC_SUGGESTIONS / MAST 조회에 쓰는 canonical 키의
# 어휘가 달라서, recommend_fix(gate, metric=…)가 "규칙이 있는데 없다고" 답하던 문제를
# 없앤다. 예: diagnose가 Gate C의 top field로 "hall_rate"를 주는데 규칙 키는
# "hallucination_rate"라 매치가 안 됐고, Gate F의 "avg_role_compliance"는 MAST의
# related metric "role_adherence"와 안 맞았다. 이 별칭표 + canonical_metric_name()으로
# 두 도구가 같은 어휘를 쓰게 한다. 모르는 이름은 그대로 돌려준다(없는 규칙을 만들지 않음).
_METRIC_ALIASES: dict[str, str] = {
    # hallucination (Gate A/C/G) — diagnose는 hall_rate, 규칙 키는 hallucination_rate
    "hall_rate": "hallucination_rate",
    "hallucination": "hallucination_rate",
    "hallucination_score": "hallucination_rate",
    "avg_hallucination": "hallucination_rate",
    # TCR (Gate A/C)
    "tcr_pct": "tcr",
    "task_completion_rate": "tcr",
    "completion_rate": "tcr",
    "avg_completion": "tcr",
    # accuracy (Gate A)
    "accuracy_score": "accuracy",
    "avg_accuracy": "accuracy",
    # latency (Gate D) — 규칙은 초 단위지만 이름 정규화만 담당(단위 변환 아님)
    "p95_latency_ms": "latency",
    "p95_ms": "latency",
    "avg_latency_ms": "latency",
    "avg_latency": "latency",
    "latency_ms": "latency",
    "avg_response_time": "latency",
    "response_time": "latency",
    # error rate
    "error_pct": "error_rate",
    "failure_rate": "error_rate",
    "err_rate": "error_rate",
    # Gate F details 필드 → MAST related_gate_f_metric
    "avg_consensus": "consensus",
    "avg_propagation": "propagation",
    "avg_role_compliance": "role_adherence",
    "role_compliance": "role_adherence",
    "avg_conflict_resolution": "conflict_resolution",
}


def canonical_metric_name(metric: str | None) -> str | None:
    """Gate ``details`` 필드명·RCA ``top_detail_deltas`` 필드명을 규칙/제안/MAST 조회에
    쓰는 canonical 키로 정규화한다.

    1) ``_METRIC_ALIASES`` 직접 매치 → 그 값.
    2) 이미 알려진 canonical(NATIVE_METRIC_RULES.metric / ANOMALY_METRIC_SUGGESTIONS 키
       / MAST related metric) → 그대로.
    3) ``avg_`` 접두 + ``_ms/_pct/_rate/_score/_count`` 접미사만 벗겨서 1·2 재시도.
    4) 그래도 모르면 **원본 그대로** 반환한다 — 없는 규칙을 지어내지 않는다
       (recommend_fix가 "세부 규칙 없음"으로 안내).
    """
    if not metric:
        return metric
    m = metric.strip()
    _mast_metrics = {"consensus", "propagation", "role_adherence", "conflict_resolution"}
    _known = (
        {r.metric for r in NATIVE_METRIC_RULES}
        | set(ANOMALY_METRIC_SUGGESTIONS)
        | _mast_metrics
    )
    if m in _METRIC_ALIASES:
        return _METRIC_ALIASES[m]
    if m in _known:
        return m
    stripped = m[4:] if m.startswith("avg_") else m
    for _suf in ("_ms", "_pct", "_rate", "_score", "_count"):
        if stripped.endswith(_suf):
            stripped = stripped[: -len(_suf)]
            break
    if stripped in _METRIC_ALIASES:
        return _METRIC_ALIASES[stripped]
    if stripped in _known:
        return stripped
    return m


# storage/sqlite_backend.py::_summarize_violations()가 FTS5 색인 대상으로 삼는
# 위반 유형 7종. 새 Gate B/E 체크가 추가되면 여기도 같이 갱신해야 한다 — 이 상수를
# 옮기지 않고 그 자리에 그대로 뒀다면 "추가는 했는데 여기 갱신을 깜빡하는" 실수가
# 예외 없이 조용히 색인 누락으로 이어졌다(이번 감사에서 확인).
VIOLATION_TYPES: tuple[str, ...] = (
    "loop_detection", "deadlock", "scope", "tool_parameter_safety",
    "tool_authorization", "privilege_escalation", "tool_chain_attack",
)
