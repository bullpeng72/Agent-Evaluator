"""
Result file loader — parses agent_evaluator JSON output files into a unified model.

Zero-configuration: auto-detects traces / audit_logs / annotations sub-directories
adjacent to the results directory.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    success: bool
    completion_score: float
    accuracy_score: float
    execution_time: float
    tokens_used: Dict[str, int]
    tool_calls: List[Any]
    attempts: int
    errors: List[Any]
    timestamp: str
    expected_tools: Optional[List[str]]
    framework: Optional[str]
    advanced_metrics: Dict[str, Any]
    raw: Dict[str, Any]


@dataclass
class SecurityL1:
    input_security: Dict[str, Any] = field(default_factory=dict)
    output_leakage: Dict[str, Any] = field(default_factory=dict)
    authorization: Dict[str, Any] = field(default_factory=dict)
    # Raw evaluator arrays for detail views
    input_evals: List[Dict[str, Any]] = field(default_factory=list)
    output_detections: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SecurityL2:
    privilege_escalation: Dict[str, Any] = field(default_factory=dict)
    attack_detection: Dict[str, Any] = field(default_factory=dict)
    escalation_events: List[Dict[str, Any]] = field(default_factory=list)
    attack_detections: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgenticMetrics:
    # Tool Selection
    tool_selections: List[Dict[str, Any]] = field(default_factory=list)   # per-task precision/recall/f1
    tool_selection_summary: Dict[str, Any] = field(default_factory=dict)
    # Tool Efficiency
    tool_efficiency: Dict[str, Any] = field(default_factory=dict)
    tool_call_executions: List[Dict[str, Any]] = field(default_factory=list)  # per-task call metrics
    # Multi-Agent Coordination
    agent_interactions: List[Dict[str, Any]] = field(default_factory=list)
    coordination_summary: Dict[str, Any] = field(default_factory=dict)
    # Workflow
    workflow_executions: List[Dict[str, Any]] = field(default_factory=list)
    workflow_summary: Dict[str, Any] = field(default_factory=dict)
    # Retry
    retry_attempts: List[Dict[str, Any]] = field(default_factory=list)
    retry_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityDetail:
    evaluations: List[Dict[str, Any]] = field(default_factory=list)
    dimension_summary: Dict[str, float] = field(default_factory=dict)
    grade_distribution: Dict[str, int] = field(default_factory=dict)
    avg_score: float = 0.0


@dataclass
class HallucinationDetail:
    detections: List[Dict[str, Any]] = field(default_factory=list)
    indicator_types: Dict[str, int] = field(default_factory=dict)


@dataclass
class AdvancedMetrics:
    summary: Dict[str, Any] = field(default_factory=dict)   # from report.advanced_metrics_summary
    rag_metrics: Dict[str, List[float]] = field(default_factory=dict)
    per_task: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMJudgeData:
    """Aggregated LLM Judge results from tasks[*].llm_judge"""
    results: List[Dict[str, Any]] = field(default_factory=list)   # per-task judge results
    avg_completeness: float = 0.0
    avg_relevance: float = 0.0
    avg_factual_consistency: float = 0.0
    avg_overall: float = 0.0
    avg_toxicity: float = 0.0
    avg_bias: float = 0.0
    avg_faithfulness: float = 0.0       # v0.7.6: RAG mode faithfulness (Ragas 대체)
    avg_criteria_overall: float = 0.0   # v0.7.6: G-Eval 커스텀 기준 평균
    total_cost_usd: float = 0.0
    judged_count: int = 0
    model: str = ""


@dataclass
class InsightsData:
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TransparencyMeta:
    """Pointers to transparency files adjacent to results_dir."""
    trace_files: List[Path] = field(default_factory=list)
    audit_files: List[Path] = field(default_factory=list)
    annotation_files: List[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main ResultFile model
# ---------------------------------------------------------------------------

@dataclass
class ResultFile:
    path: Path
    file_id: str
    name: str
    timestamp: str
    total_tasks: int
    tasks: List[TaskRecord]
    accuracy_metrics: Dict[str, Any]
    efficiency_metrics: Dict[str, Any]
    security_l1: SecurityL1
    security_l2: SecurityL2
    agentic: AgenticMetrics
    quality_detail: QualityDetail
    hallucination_detail: HallucinationDetail
    advanced: AdvancedMetrics
    insights: InsightsData
    rag_metrics: Dict[str, List[float]]
    pricing: Dict[str, Any]
    raw: Dict[str, Any]
    llm_judge: "LLMJudgeData" = field(default_factory=LLMJudgeData)
    conversation_sessions: List[Dict[str, Any]] = field(default_factory=list)
    feedback_data: Dict[str, Any] = field(default_factory=dict)
    anomaly_data: List[Dict[str, Any]] = field(default_factory=list)
    cost_data: Dict[str, Any] = field(default_factory=dict)
    streaming_data: Dict[str, Any] = field(default_factory=dict)
    # Phase 2: Harness 그룹 집계 (EvaluationReport.extra_metrics["harness_groups"])
    harness_groups: Optional[Dict[str, Any]] = field(default_factory=dict)
    loop_events: List[Dict[str, Any]] = field(default_factory=list)
    fault_tolerance_by_tool: Dict[str, Any] = field(default_factory=dict)

    # ---- computed helpers ------------------------------------------------
    @property
    def tcr(self) -> float:
        return self.accuracy_metrics.get("tcr", {}).get("tcr", 0.0)

    @property
    def accuracy(self) -> float:
        return self.accuracy_metrics.get("accuracy_scores", {}).get("overall_accuracy", 0.0)

    @property
    def hallucination_rate(self) -> float:
        return self.accuracy_metrics.get("hallucination", {}).get("overall_rate", 0.0)

    @property
    def avg_latency(self) -> float:
        return self.efficiency_metrics.get("latency", {}).get("mean", 0.0)

    @property
    def p95_latency(self) -> float:
        return self.efficiency_metrics.get("latency", {}).get("p95", 0.0)

    @property
    def total_cost(self) -> float:
        return self.efficiency_metrics.get("tokens", {}).get("total_cost", 0.0)

    @property
    def avg_cost_per_task(self) -> float:
        return self.efficiency_metrics.get("tokens", {}).get("avg_cost_per_task", 0.0)

    @property
    def total_tokens(self) -> int:
        return self.efficiency_metrics.get("tokens", {}).get("total_tokens", 0)

    @property
    def has_security(self) -> bool:
        return bool(self.security_l1.input_evals or
                    self.security_l1.output_detections or
                    self.security_l1.tool_calls or
                    self.security_l2.escalation_events or
                    self.security_l2.attack_detections)

    @property
    def has_multimodal(self) -> bool:
        """멀티모달 태스크(이미지/오디오/비디오) 포함 여부."""
        return any(
            t.raw.get("extra", {}) and (
                t.raw["extra"].get("image_count") or
                t.raw["extra"].get("audio_duration_seconds") or
                t.raw["extra"].get("video_frames")
            )
            for t in self.tasks
        )

    @property
    def multimodal_task_count(self) -> int:
        """멀티모달 입력을 포함한 태스크 수."""
        return sum(
            1 for t in self.tasks
            if t.raw.get("extra", {}) and (
                t.raw["extra"].get("image_count") or
                t.raw["extra"].get("audio_duration_seconds") or
                t.raw["extra"].get("video_frames")
            )
        )

    @property
    def has_agentic(self) -> bool:
        return bool(self.agentic.tool_selections or
                    self.agentic.agent_interactions or
                    self.agentic.workflow_executions or
                    self.agentic.retry_attempts)

    @property
    def has_advanced(self) -> bool:
        return bool(self.advanced.summary or self.advanced.per_task)

    @property
    def has_rag(self) -> bool:
        return any(len(v) > 0 for v in self.rag_metrics.values())

    @property
    def has_quality_detail(self) -> bool:
        return len(self.quality_detail.evaluations) > 0

    @property
    def has_hallucination(self) -> bool:
        return len(self.hallucination_detail.detections) > 0

    # --- Agentic sub-flags ---
    @property
    def has_tool_use(self) -> bool:
        return bool(self.agentic.tool_selections or self.agentic.tool_efficiency)

    @property
    def has_coordination(self) -> bool:
        return bool(self.agentic.agent_interactions)

    @property
    def has_workflow(self) -> bool:
        return bool(self.agentic.workflow_executions)

    @property
    def has_retry(self) -> bool:
        return bool(self.agentic.retry_attempts)

    # --- Phase 1-A / 1-C / 2-C / 3-B / 3-C ---
    @property
    def has_llm_judge(self) -> bool:
        return self.llm_judge.judged_count > 0

    @property
    def has_conversation(self) -> bool:
        return len(self.conversation_sessions) > 0

    @property
    def has_feedback(self) -> bool:
        return bool(self.feedback_data and self.feedback_data.get("total", 0) > 0)

    @property
    def has_streaming(self) -> bool:
        return bool(self.streaming_data)

    @property
    def has_anomaly(self) -> bool:
        return len(self.anomaly_data) > 0

    @property
    def has_cost(self) -> bool:
        return bool(self.cost_data and self.cost_data.get("call_count", 0) > 0)

    # --- Security sub-flags ---
    @property
    def has_input_security(self) -> bool:
        return bool(self.security_l1.input_evals)

    @property
    def has_output_security(self) -> bool:
        return bool(self.security_l1.output_detections)

    @property
    def has_tool_auth(self) -> bool:
        return bool(self.security_l1.tool_calls)

    @property
    def has_attack_detect(self) -> bool:
        return bool(self.security_l2.escalation_events or self.security_l2.attack_detections)

    @property
    def has_llm_judge(self) -> bool:
        return self.llm_judge.judged_count > 0

    @property
    def has_conversations(self) -> bool:
        return len(self.conversation_sessions) > 0

    @property
    def has_harness(self) -> bool:
        return bool(self.harness_groups and len(self.harness_groups) > 1)

    @property
    def harness_is_configured(self) -> bool:
        """extra_metrics.harness_groups가 JSON에 실제 저장된 경우 True (fallback 계산 아님)."""
        extra = (self.raw or {}).get("extra_metrics", {}) or {}
        return isinstance(extra.get("harness_groups"), dict)

    @property
    def gate_data_presence(self) -> Dict[str, bool]:
        """각 Gate(A~G)에 실제 데이터가 있는지 판정하는 단일 정규 소스.

        대시보드 전체(미니패널·에이전틱탭·내보내기 배지·파일목록)가 이 값만 사용해야 한다.
        - Harness Config 사용 파일: harness_groups 점수 존재 여부로 판정
        - 그 외(fallback 계산): has_* 플래그 매핑으로 판정
        """
        if self.harness_is_configured and self.harness_groups:
            return {
                gk: (self.harness_groups.get(gk) or {}).get("score") is not None
                for gk in ["A", "B", "C", "D", "E", "F", "G"]
            }
        return {
            "A": True,
            "B": self.has_tool_use or self.has_workflow,
            "C": self.has_retry or self.has_anomaly,
            "D": self.has_cost or self.has_streaming,
            "E": self.has_security,
            "F": self.has_coordination or self.has_conversation,
            "G": self.has_quality_detail or self.has_llm_judge or self.has_feedback,
        }


@dataclass
class ResultSet:
    files: List[ResultFile] = field(default_factory=list)
    transparency: TransparencyMeta = field(default_factory=TransparencyMeta)

    def by_id(self, file_id: str) -> Optional[ResultFile]:
        for f in self.files:
            if f.file_id == file_id:
                return f
        return None

    def summary(self) -> Dict[str, Any]:
        if not self.files:
            return {}
        return {
            "file_count": len(self.files),
            "total_tasks": sum(f.total_tasks for f in self.files),
            "avg_tcr":           _avg(f.tcr for f in self.files),
            "avg_accuracy":      _avg(f.accuracy for f in self.files),
            "avg_hallucination": _avg(f.hallucination_rate for f in self.files),
            "avg_latency":       _avg(f.avg_latency for f in self.files),
            "avg_p95_latency":   _avg(f.p95_latency for f in self.files),
            "total_cost":        sum(f.total_cost for f in self.files),
            "avg_cost_per_task": _avg(f.avg_cost_per_task for f in self.files),
            "total_tokens":      sum(f.total_tokens for f in self.files),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avg(iterable) -> float:
    vals = [v for v in iterable if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _file_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode()).hexdigest()[:8]


def _safe_list(d: dict, *keys) -> list:
    """Traverse nested dict keys and return list or []."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(k, {})
    return cur if isinstance(cur, list) else []


def _safe_dict(d: dict, *keys) -> dict:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(k, {})
    return cur if isinstance(cur, dict) else {}


# ---------------------------------------------------------------------------
# Security parsing
# ---------------------------------------------------------------------------

def _parse_security_l1(raw: dict) -> SecurityL1:
    sec_eval = _safe_dict(raw, "evaluators", "security")
    sec_metrics = _safe_dict(raw, "security_metrics", "layer1_security")
    if not sec_metrics:
        sec_metrics = _safe_dict(raw.get("report", {}), "security_metrics", "layer1_security")

    input_evals = _safe_list(sec_eval, "input_sanitizer", "evaluations")
    output_dets = _safe_list(sec_eval, "output_leakage_detector", "detections")
    tool_calls  = _safe_list(sec_eval, "tool_authorizer", "tool_calls")

    # Use aggregated security_metrics when available; else compute from raw arrays
    input_security = _safe_dict(sec_metrics, "input_security")
    if not input_security and input_evals:
        n = len(input_evals)
        threats = sum(1 for e in input_evals if e.get("sanitization_needed"))
        input_security = {
            "total_inputs_evaluated": n,
            "inputs_with_threats": threats,
            "threat_rate": round(threats / n * 100, 1) if n else 0,
            "sql_injection_attempts": sum(1 for e in input_evals if e.get("has_sql_injection")),
            "command_injection_attempts": sum(1 for e in input_evals if e.get("has_command_injection")),
            "path_traversal_attempts": sum(1 for e in input_evals if e.get("has_path_traversal")),
            "xss_attempts": sum(1 for e in input_evals if e.get("has_xss")),
            "prompt_injection_attempts": sum(1 for e in input_evals if e.get("has_prompt_injection")),
        }

    output_leakage = _safe_dict(sec_metrics, "output_leakage")
    if not output_leakage and output_dets:
        n = len(output_dets)
        leaked = sum(1 for e in output_dets if e.get("leakage_count", 0) > 0)
        output_leakage = {
            "total_outputs_evaluated": n,
            "outputs_with_leakage": leaked,
            "leakage_rate": round(leaked / n * 100, 1) if n else 0,
            "api_key_leaks":         sum(1 for e in output_dets if e.get("contains_api_key")),
            "password_leaks":        sum(1 for e in output_dets if e.get("contains_password")),
            "credit_card_leaks":     sum(1 for e in output_dets if e.get("contains_credit_card")),
            "email_leaks":           sum(1 for e in output_dets if e.get("contains_email")),
            "ssn_leaks":             sum(1 for e in output_dets if e.get("contains_ssn")),
            "phone_leaks":           sum(1 for e in output_dets if e.get("contains_phone")),
            "private_ip_leaks":      sum(1 for e in output_dets if e.get("contains_private_ip")),
            "file_path_leaks":       sum(1 for e in output_dets if e.get("contains_file_path")),
            "critical_severity_count": sum(1 for e in output_dets if e.get("severity") == "critical"),
            "high_severity_count":     sum(1 for e in output_dets if e.get("severity") == "high"),
        }

    authorization = _safe_dict(sec_metrics, "authorization")
    if not authorization and tool_calls:
        n = len(tool_calls)
        violations = sum(1 for t in tool_calls if not t.get("is_authorized", True))
        authorization = {
            "total_tool_calls": n,
            "authorized_calls": n - violations,
            "unauthorized_calls": violations,
            "compliance_rate": round((n - violations) / n * 100, 1) if n else 100,
            "violation_rate": round(violations / n * 100, 1) if n else 0,
            "violations": violations,
            "restricted_tool_attempts": sum(1 for t in tool_calls if t.get("is_restricted")),
            "dangerous_param_attempts": sum(1 for t in tool_calls if t.get("has_dangerous_params")),
            "restricted_attempts": sum(1 for t in tool_calls if t.get("is_restricted")),
            "dangerous_params": sum(1 for t in tool_calls if t.get("has_dangerous_params")),
        }
    elif authorization:
        # Normalize keys: tracker uses long names, dashboard expects short aliases
        if "violations" not in authorization:
            authorization["violations"] = authorization.get("unauthorized_calls", 0)
        if "restricted_attempts" not in authorization:
            authorization["restricted_attempts"] = authorization.get("restricted_tool_attempts", 0)
        if "dangerous_params" not in authorization:
            authorization["dangerous_params"] = authorization.get("dangerous_param_attempts", 0)

    # Detect tracking gap: tasks have tool_calls but ToolAuthorizationTracker recorded none
    task_tool_calls_total = sum(
        len(t.get("tool_calls", [])) if isinstance(t.get("tool_calls"), list)
        else int(t.get("tool_calls") or 0)
        for t in raw.get("tasks", [])
    )
    if authorization is None and task_tool_calls_total > 0:
        # Tracker not active at all but tasks have tool calls → create stub with tracking_active=False
        authorization = {
            "total_tool_calls": 0,
            "authorized_calls": 0,
            "unauthorized_calls": 0,
            "compliance_rate": 100,
            "violation_rate": 0,
            "violations": 0,
            "restricted_attempts": 0,
            "dangerous_params": 0,
            "tracking_active": False,
            "task_tool_calls_total": task_tool_calls_total,
        }
    elif authorization is not None:
        tracked = authorization.get("total_tool_calls", 0)
        authorization["task_tool_calls_total"] = task_tool_calls_total
        # tracking_active:
        #   False  — tracker recorded 0 calls but tasks show >0 (tracker not wired up)
        #   "partial" — tracker recorded some calls but tasks have significantly more
        #   True   — tracker recorded ≥tasks calls, or tasks have 0 calls
        if tracked == 0 and task_tool_calls_total > 0:
            authorization["tracking_active"] = False
        elif tracked > 0 and task_tool_calls_total > 0 and task_tool_calls_total > tracked * 1.5:
            authorization["tracking_active"] = "partial"
            authorization["tracking_coverage"] = round(tracked / task_tool_calls_total * 100, 1)
        else:
            authorization["tracking_active"] = True

    return SecurityL1(
        input_security=input_security,
        output_leakage=output_leakage,
        authorization=authorization,
        input_evals=input_evals,
        output_detections=output_dets,
        tool_calls=tool_calls,
    )


def _parse_security_l2(raw: dict) -> SecurityL2:
    sec_eval = _safe_dict(raw, "evaluators", "security")
    sec_metrics = _safe_dict(raw, "security_metrics", "layer2_security")
    if not sec_metrics:
        sec_metrics = _safe_dict(raw.get("report", {}), "security_metrics", "layer2_security")

    esc_events = _safe_list(sec_eval, "privilege_escalation_detector", "escalation_events")
    atk_dets   = _safe_list(sec_eval, "tool_chain_attack_detector", "detections")

    priv_esc = _safe_dict(sec_metrics, "privilege_escalation")
    if not priv_esc and esc_events:
        n = len(esc_events)
        detected = sum(1 for e in esc_events if e.get("escalation_detected"))
        priv_esc = {
            "total_evaluations": n,
            "escalations_detected": detected,
            "escalation_rate": round(detected / n * 100, 1) if n else 0,
        }
    elif priv_esc and "escalations_detected" not in priv_esc:
        # ensure dashboard key exists even when loaded from report-level data
        priv_esc["escalations_detected"] = priv_esc.get("total_escalations_detected", 0)

    atk_summary = _safe_dict(sec_metrics, "attack_detection")
    if not atk_summary and atk_dets:
        n = len(atk_dets)
        suspicious = sum(1 for d in atk_dets if d.get("is_suspicious_chain"))
        atk_summary = {
            "total_chains_analyzed": n,
            "suspicious_chains": suspicious,
            "detection_rate": round(suspicious / n * 100, 1) if n else 0,
        }
    elif atk_summary and "suspicious_chains" not in atk_summary:
        # ensure dashboard key exists even when loaded from report-level data
        atk_summary["suspicious_chains"] = atk_summary.get("total_suspicious_chains", 0)

    # Detect L2 tracking gaps (same pattern as L1 authorization)
    task_count = len(raw.get("tasks", []))
    task_tool_calls_total = sum(
        len(t.get("tool_calls", [])) if isinstance(t.get("tool_calls"), list)
        else int(t.get("tool_calls") or 0)
        for t in raw.get("tasks", [])
    )

    # PrivilegeEscalationDetector tracking gap
    priv_evals = (priv_esc or {}).get("total_evaluations", 0)
    if priv_evals == 0 and task_count > 0:
        if priv_esc is None:
            priv_esc = {"total_evaluations": 0, "escalations_detected": 0, "escalation_rate": 0}
        priv_esc["tracking_active"] = False
        priv_esc["task_count"] = task_count
        priv_esc["task_tool_calls_total"] = task_tool_calls_total
    elif priv_esc is not None:
        priv_esc["tracking_active"] = True

    # ToolChainAttackDetector tracking gap
    atk_chains = (atk_summary or {}).get("total_chains_analyzed", 0)
    if atk_chains == 0 and task_tool_calls_total > 0:
        if atk_summary is None:
            atk_summary = {"total_chains_analyzed": 0, "suspicious_chains": 0, "detection_rate": 0}
        atk_summary["tracking_active"] = False
        atk_summary["task_tool_calls_total"] = task_tool_calls_total
    elif atk_summary is not None:
        atk_summary["tracking_active"] = True

    return SecurityL2(
        privilege_escalation=priv_esc,
        attack_detection=atk_summary,
        escalation_events=esc_events,
        attack_detections=atk_dets,
    )


# ---------------------------------------------------------------------------
# Conversation / Feedback / Cost parsing
# ---------------------------------------------------------------------------

def _parse_conversation_sessions(raw: dict) -> List[Dict[str, Any]]:
    """conversation_sessions 파싱."""
    sessions_raw = raw.get("conversation_sessions", [])
    if not isinstance(sessions_raw, list):
        return []
    result = []
    for s in sessions_raw:
        if not isinstance(s, dict):
            continue
        metrics = s.get("metrics", {})
        is_dict = isinstance(metrics, dict)
        # turn_count: 최상위 우선, 없으면 metrics 내부, 없으면 turns 리스트 길이로 fallback
        turn_count = (
            s.get("turn_count")
            or (metrics.get("turn_count") if is_dict else None)
            or len(s.get("turns", []))
        )
        # avg_turn_latency: SDK가 "avg_turn_latency"로 저장, 구버전 호환 "avg_response_latency" fallback
        avg_latency = (
            (metrics.get("avg_turn_latency") or metrics.get("avg_response_latency") or 0.0)
            if is_dict else 0.0
        )
        result.append({
            "session_id": s.get("session_id", ""),
            "turn_count": turn_count,
            "turns": s.get("turns", []),
            "metrics": {
                "overall_score": metrics.get("overall_score", 0.0) if is_dict else 0.0,
                "context_retention": metrics.get("context_retention", 0.0) if is_dict else 0.0,
                "topic_coherence": metrics.get("topic_coherence", 0.0) if is_dict else 0.0,
                "progressive_depth": metrics.get("progressive_depth", 0.0) if is_dict else 0.0,
                "session_completion": metrics.get("session_completion", 0.0) if is_dict else 0.0,
                "avg_response_latency": avg_latency,
            },
        })
    return result


def _parse_feedback_data(raw: dict) -> Dict[str, Any]:
    """피드백 데이터 파싱."""
    fb = raw.get("feedback", {})
    if not fb:
        return {}
    return {
        "total": fb.get("total", 0),
        "positive_count": fb.get("positive_count", 0),
        "negative_count": fb.get("negative_count", 0),
        "positive_rate": fb.get("positive_rate", 0.0),
        "negative_rate": fb.get("negative_rate", 0.0),
        "regenerate_rate": fb.get("regenerate_rate", 0.0),
        "abandon_rate": fb.get("abandon_rate", 0.0),
        "type_distribution": fb.get("type_distribution", {}),
        "records": fb.get("records", []),
    }


def _parse_cost_data(raw: dict) -> Dict[str, Any]:
    """비용 데이터 파싱 — budget/sampling 필드 포함.

    evaluation_cost: CostTracker 결과 (total_usd, by_provider, call_count 등)
    pricing:         토큰 단가 테이블 (input, output — evaluation_cost와 별개)
    """
    # evaluation_cost 우선(CostTracker), 없으면 빈 dict
    cost = raw.get("evaluation_cost", {})
    # pricing은 토큰 단가 전용 — 모델명만 보조로 참조
    pricing = raw.get("pricing", {})

    if not cost:
        return {}

    llm_judge_cost = cost.get("llm_judge_usd", 0.0)
    total = cost.get("total_usd", llm_judge_cost)
    budget_remaining = cost.get("budget_remaining_usd")
    budget_per_day = cost.get("budget_per_day")
    sample_rate = cost.get("sample_rate_current", 0.0)
    projected = cost.get("projected_daily_usd", total)

    return {
        "total_usd": round(float(total), 6),
        "llm_judge_usd": round(float(llm_judge_cost), 6),
        "by_provider": cost.get("by_provider", {}),
        "call_count": cost.get("call_count", 0),
        "model": cost.get("model", pricing.get("model", "")),
        "budget_per_day": budget_per_day,
        "budget_remaining_usd": round(float(budget_remaining), 6) if budget_remaining is not None else None,
        "sample_rate_current": float(sample_rate),
        "projected_daily_usd": round(float(projected), 6),
    }


def _parse_streaming_data(raw: dict) -> Dict[str, Any]:
    """StreamingEvaluator 슬라이딩 윈도우 스냅샷 파싱.

    save_to_file()에서 ``streaming_data`` 키로 저장된 dict를 그대로 반환한다.
    형식: {"1m": {count, tcr, avg_latency, ...}, "5m": {...}, "1h": {...}}
    """
    sd = raw.get("streaming_data", {})
    if not sd or not isinstance(sd, dict):
        return {}
    return sd


def _parse_anomaly_data(raw: dict) -> List[Dict[str, Any]]:
    """이상 탐지 데이터 파싱.

    save_to_file()은 ``anomaly_data.anomalies`` 구조로 저장한다.
    하위 호환을 위해 최상위 ``anomalies`` 키도 지원한다.
    """
    nested = raw.get("anomaly_data")
    if isinstance(nested, dict):
        anomalies_raw = nested.get("anomalies", [])
    else:
        anomalies_raw = raw.get("anomalies", [])
    if not isinstance(anomalies_raw, list):
        return []
    result = []
    for a in anomalies_raw:
        if not isinstance(a, dict):
            continue
        result.append({
            "type": a.get("type", "unknown"),
            "severity": a.get("severity", "warning"),
            "detail": a.get("detail", a.get("message", a.get("description", ""))),
            "detected_at": a.get("detected_at", a.get("timestamp", "")),
            "metric": a.get("metric", ""),
            "value": a.get("value"),
            "threshold": a.get("threshold"),
            "algorithm": a.get("algorithm", ""),
        })
    return result


def _compute_harness_groups_fallback(report: dict) -> Dict[str, Any]:
    """기존 JSON 파일에 harness_groups 없을 때 기존 지표에서 A~G 그룹 계산.

    monitor.py의 _compute_harness_groups()와 동일한 그룹 체계를 따르되,
    직렬화된 report dict에서 직접 읽는다.
    """
    acc = report.get("accuracy_metrics") or {}
    eff = report.get("efficiency_metrics") or {}
    sec = report.get("security_metrics") or {}

    # ── Group A: Goal Achievement ──────────────────────────────────────────
    tcr_pct = float((acc.get("tcr") or {}).get("tcr", 0.0) or 0.0)
    overall_acc = float((acc.get("accuracy_scores") or {}).get("overall_accuracy", 0.0) or 0.0) / 100.0
    a_score = round((tcr_pct / 100.0 + overall_acc) / 2.0, 4)

    # ── Group B: Behavioral Integrity ─────────────────────────────────────
    # 루프 감지 없으면 TCR 기반 프록시
    b_score = round(min(1.0, tcr_pct / 100.0 * 0.95), 4)

    # ── Group C: Reliability ─────────────────────────────────────────────
    retry_block = acc.get("retry_correction") or {}
    avg_retry = retry_block.get("avg_retry_count") or retry_block.get("avg_retries_per_task")
    if avg_retry is not None:
        c_score = round(max(0.0, 1.0 - float(avg_retry) / 5.0), 4)
    else:
        c_score = round(min(1.0, tcr_pct / 100.0), 4)

    # ── Group D: Performance Contract ────────────────────────────────────
    lat = (eff.get("latency") or {})
    p95 = lat.get("p95") or lat.get("p95_latency")
    if p95 is not None:
        p95 = float(p95)
        d_score = round(1.0 if p95 < 5.0 else (0.7 if p95 < 10.0 else 0.3), 4)
    else:
        d_score = 0.5

    # ── Group E: Security Boundary ────────────────────────────────────────
    threat_count = int(sec.get("threat_count", 0) or 0)
    n = max(1, int(report.get("total_tasks", 1) or 1))
    e_score = round(max(0.0, 1.0 - threat_count / n), 4)

    # ── Group F: Multi-Agent Coordination ────────────────────────────────
    coord_block = report.get("coordination_metrics") or {}
    coord_rate = (
        (coord_block.get("interaction_patterns") or {}).get("coordination_success_rate")
        or coord_block.get("coordination_success_rate")
    )
    f_score = round(float(coord_rate), 4) if coord_rate is not None else None

    # ── Group G: Observability ────────────────────────────────────────────
    hall_block = acc.get("hallucination") or {}
    hall_rate = hall_block.get("overall_rate") or hall_block.get("average_hallucination_rate") or 0.0
    g_score = round(max(0.0, 1.0 - float(hall_rate) / 100.0), 4)

    def _gate(score: Optional[float], hi: float = 0.7, lo: float = 0.5) -> str:
        if score is None:
            return "n/a"
        return "pass" if score >= hi else ("warn" if score >= lo else "fail")

    groups: Dict[str, Any] = {
        "A": {"name": "Goal Achievement",          "score": a_score, "gate": _gate(a_score)},
        "B": {"name": "Behavioral Integrity",       "score": b_score, "gate": _gate(b_score)},
        "C": {"name": "Reliability",               "score": c_score, "gate": _gate(c_score)},
        "D": {"name": "Performance Contract",       "score": d_score, "gate": _gate(d_score)},
        "E": {"name": "Security Boundary",          "score": e_score, "gate": _gate(e_score, hi=0.9, lo=0.7)},
        "F": {"name": "Multi-Agent Coordination",   "score": f_score, "gate": _gate(f_score)},
        "G": {"name": "Observability",              "score": g_score, "gate": _gate(g_score)},
    }
    scored = [v["score"] for v in groups.values() if v["score"] is not None]
    overall = round(sum(scored) / len(scored), 4) if scored else 0.0
    gates = [v["gate"] for v in groups.values() if v["gate"] != "n/a"]
    overall_gate = "fail" if "fail" in gates else ("warn" if "warn" in gates else "pass")
    groups["overall"] = {"score": overall, "gate": overall_gate}
    return groups


def _parse_harness_data(
    raw: dict,
) -> "tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]":
    """EvaluationReport.extra_metrics["harness_groups"] 및 task extras 파싱.

    Returns:
        (harness_groups, loop_events, fault_tolerance_by_tool)
        harness_groups: 항상 8-key dict (A~G + overall) 반환 (has_harness 판별은 ResultFile.has_harness).
    """
    # harness_groups: report.extra_metrics.harness_groups
    report = raw.get("report", raw)
    extra = report.get("extra_metrics", {})
    if not isinstance(extra, dict):
        extra = {}
    harness_groups: Optional[Dict[str, Any]] = extra.get("harness_groups")
    if not isinstance(harness_groups, dict):
        harness_groups = None

    # monitor.py 는 "status" 키를 사용, 대시보드는 "gate" 키를 사용 — 정규화
    if isinstance(harness_groups, dict):
        for gv in harness_groups.values():
            if isinstance(gv, dict) and "status" in gv and "gate" not in gv:
                gv["gate"] = gv["status"]

    # 기존 파일(Phase 1 이전 생성)에 harness_groups 없으면 기존 지표에서 fallback 계산
    if harness_groups is None:
        try:
            harness_groups = _compute_harness_groups_fallback(report)
        except Exception:
            harness_groups = None

    # loop_events: tasks[*].extra.loop_detection.detected=True 목록 병합
    loop_events: List[Dict[str, Any]] = []
    # fault_tolerance_by_tool: tasks[*].extra.fault_tolerance 도구별 집계
    ft_acc: Dict[str, Dict[str, int]] = {}

    for t in raw.get("tasks", []):
        if not isinstance(t, dict):
            continue
        task_extra = t.get("extra") or {}
        if not isinstance(task_extra, dict):
            continue
        task_id = t.get("task_id", "")

        # loop_events
        ld = task_extra.get("loop_detection")
        if isinstance(ld, dict) and ld.get("detected"):
            loop_events.append({
                "task_id": task_id,
                "type": ld.get("type", "unknown"),
                "at_step": ld.get("at_step"),
                "tool": ld.get("tool"),
                "detected_at": t.get("timestamp", ""),
            })

        # fault_tolerance_by_tool
        ft = task_extra.get("fault_tolerance")
        if isinstance(ft, dict):
            failures = int(ft.get("failures_detected", 0) or 0)
            fallbacks = int(ft.get("fallback_attempts", 0) or 0)
            # 도구명은 task_extra나 tool_calls에서 추출
            tool_name = "unknown"
            tcs = t.get("tool_calls") or []
            if isinstance(tcs, list) and tcs:
                first_failed = next(
                    (tc.get("name", "unknown") for tc in tcs
                     if isinstance(tc, dict) and not tc.get("success", True)),
                    tcs[0].get("name", "unknown") if isinstance(tcs[0], dict) else "unknown",
                )
                tool_name = first_failed
            if failures > 0:
                if tool_name not in ft_acc:
                    ft_acc[tool_name] = {"total": 0, "recovered": 0}
                ft_acc[tool_name]["total"] += failures
                ft_acc[tool_name]["recovered"] += min(fallbacks, failures)

    fault_tolerance_by_tool: Dict[str, Any] = {
        tool: {
            "total": v["total"],
            "recovered": v["recovered"],
            "recovery_rate": round(v["recovered"] / v["total"] * 100, 1) if v["total"] else 0.0,
        }
        for tool, v in ft_acc.items()
    }

    return harness_groups, loop_events, fault_tolerance_by_tool


# ---------------------------------------------------------------------------
# Agentic parsing
# ---------------------------------------------------------------------------

def _parse_agentic(raw: dict) -> AgenticMetrics:
    ev = _safe_dict(raw, "evaluators")

    # Tool Selection
    selections = _safe_list(ev, "tool_selection", "selections")
    tool_sel_summary: Dict[str, Any] = {}
    if selections:
        prec  = _avg(s.get("precision",  0) for s in selections)
        rec   = _avg(s.get("recall",     0) for s in selections)
        f1    = _avg(s.get("f1_score",   0) for s in selections)
        acc   = _avg(s.get("accuracy",   0) for s in selections)
        tool_sel_summary = {
            "total_selections": len(selections),
            "avg_precision": round(prec, 1),
            "avg_recall":    round(rec,  1),
            "avg_f1_score":  round(f1,   1),
            "avg_accuracy":  round(acc,  1),
        }

    # Tool Efficiency (from efficiency_metrics, not evaluators)
    # Fallback: HybridPerformanceMonitor stores efficiency_metrics inside "report"
    tool_eff = _safe_dict(raw, "efficiency_metrics", "tool_efficiency")
    if not tool_eff:
        tool_eff = _safe_dict(raw.get("report", {}), "efficiency_metrics", "tool_efficiency")

    # Tool Call Executions — per-task breakdown for detail table
    tool_call_executions = _safe_list(ev, "tool_calls", "executions")

    # Agent Coordination
    interactions = _safe_list(ev, "agent_coordination", "interactions")
    coord_summary: Dict[str, Any] = {}
    if interactions:
        successful = sum(1 for i in interactions if i.get("success"))
        agents = set()
        for i in interactions:
            agents.add(i.get("from_agent", ""))
            agents.add(i.get("to_agent", ""))
        agents.discard("")
        coord_summary = {
            "total_interactions": len(interactions),
            "successful_interactions": successful,
            "success_rate": round(successful / len(interactions) * 100, 1),
            "unique_agents": len(agents),
            "agent_list": list(agents),
        }

    # Workflow
    wf_executions = _safe_list(ev, "workflow", "executions")
    wf_summary: Dict[str, Any] = {}
    if wf_executions:
        successful_steps = sum(1 for s in wf_executions if s.get("success"))
        frameworks = list({s.get("framework", "") for s in wf_executions} - {""})
        # Group by task_id to compute task-level success rate
        task_groups: dict = defaultdict(list)
        for s in wf_executions:
            task_groups[s.get("task_id", "_")].append(s)
        fully_successful = sum(
            1 for steps in task_groups.values() if all(s.get("success") for s in steps)
        )
        task_count = len(task_groups)
        wf_summary = {
            "total_steps": len(wf_executions),
            "successful_steps": successful_steps,
            "step_success_rate": round(successful_steps / len(wf_executions) * 100, 1),
            "total_tasks": task_count,
            "fully_successful_tasks": fully_successful,
            "task_success_rate": round(fully_successful / task_count * 100, 1) if task_count else 0.0,
            "frameworks": frameworks,
        }

    # Retry
    retry_attempts = _safe_list(ev, "retry", "attempts")
    retry_summary = _safe_dict(raw, "efficiency_metrics", "retries")
    if not retry_summary:
        retry_summary = _safe_dict(raw.get("report", {}), "efficiency_metrics", "retries")
    if retry_attempts and not retry_summary:
        total = len(retry_attempts)
        all_attempts = [a.get("total_attempts", 1) for a in retry_attempts]
        tasks_with_retry = sum(1 for a in retry_attempts if a.get("total_attempts", 1) > 1)
        successful = sum(1 for a in retry_attempts if a.get("final_success", True))
        retry_summary = {
            "total_attempts": total,
            "total_tasks_with_retries": tasks_with_retry,
            "avg_attempts_per_task": round(sum(all_attempts) / len(all_attempts), 2) if all_attempts else 1.0,
            "eventual_success_rate": round(successful / total * 100, 1) if total else 0.0,
        }

    return AgenticMetrics(
        tool_selections=selections,
        tool_selection_summary=tool_sel_summary,
        tool_efficiency=tool_eff,
        tool_call_executions=tool_call_executions,
        agent_interactions=interactions,
        coordination_summary=coord_summary,
        workflow_executions=wf_executions,
        workflow_summary=wf_summary,
        retry_attempts=retry_attempts,
        retry_summary=retry_summary,
    )


# ---------------------------------------------------------------------------
# Quality / Hallucination detail
# ---------------------------------------------------------------------------

def _parse_quality_detail(raw: dict) -> QualityDetail:
    evals = _safe_list(raw, "evaluators", "quality", "evaluations")
    if not evals:
        # Some files put quality data at accuracy_metrics.quality
        q = _safe_dict(raw, "accuracy_metrics", "quality")
        dim = q.get("dimension_averages", {})
        grade = q.get("grade_distribution", {})
        avg = q.get("avg_total_score", 0.0)
        return QualityDetail(evaluations=[], dimension_summary=dim, grade_distribution=grade, avg_score=avg)

    # Layer 3(DeepEval) 기록은 외부 평가 탭으로 분리 — 품질 탭은 Layer 1(네이티브)만 표시
    evals = [e for e in evals if e.get("source") != "deepeval"]

    # Deduplicate by task_id — keep the latest evaluation per task (same task may be
    # evaluated multiple times when record_task() auto-eval + explicit evaluate_response()
    # are both called; duplicate keys break x-for rendering in the frontend).
    seen: Dict[str, int] = {}  # task_id → last index
    for i, ev in enumerate(evals):
        tid = ev.get("task_id")
        if tid is not None:
            seen[tid] = i
    evals = [evals[i] for i in sorted(seen.values())]

    # Aggregate dimension scores from evaluations
    dim_sums: Dict[str, float] = {}
    dim_counts: Dict[str, int] = {}
    grades: Dict[str, int] = {}
    scores = []
    for ev in evals:
        ds = ev.get("dimension_scores", {})
        for dk, dv in ds.items():
            dim_sums[dk] = dim_sums.get(dk, 0) + dv
            dim_counts[dk] = dim_counts.get(dk, 0) + 1
        score = ev.get("total_score", 0)
        scores.append(score)
        grade = ev.get("grade", "")
        if grade:
            grades[grade] = grades.get(grade, 0) + 1

    dim_avg = {k: round(dim_sums[k] / dim_counts[k], 2) for k in dim_sums}
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    return QualityDetail(evaluations=evals, dimension_summary=dim_avg, grade_distribution=grades, avg_score=avg)


def _parse_hallucination_detail(raw: dict) -> HallucinationDetail:
    dets = _safe_list(raw, "evaluators", "hallucination", "detections")
    # Layer 3(DeepEval) 기록은 외부 평가 탭으로 분리 — 품질 탭은 Layer 1(네이티브)만 표시
    dets = [d for d in dets if d.get("source") != "deepeval"]
    ind_types: Dict[str, int] = {}
    for d in dets:
        for ind in d.get("indicators", []):
            t = ind.get("type", "unknown")
            ind_types[t] = ind_types.get(t, 0) + 1
    return HallucinationDetail(detections=dets, indicator_types=ind_types)


# ---------------------------------------------------------------------------
# Advanced metrics (DeepEval / toxicity / bias / answer_relevancy)
# ---------------------------------------------------------------------------

_RAGAS_KEYS = (
    "ragas_faithfulness", "ragas_answer_relevancy",
    "ragas_context_recall", "ragas_context_precision",
)


def _parse_advanced(raw: dict) -> AdvancedMetrics:
    # Summary from report.advanced_metrics_summary (HybridPerformanceMonitor)
    # or top-level advanced_metrics_summary (PerformanceMonitor.save_to_file)
    summary = _safe_dict(raw, "report", "advanced_metrics_summary")
    if not summary:
        summary = _safe_dict(raw, "advanced_metrics_summary")

    # Per-task advanced_metrics
    per_task = []
    for t in raw.get("tasks", []):
        am = t.get("advanced_metrics")
        if am and isinstance(am, dict):
            per_task.append({"task_id": t.get("task_id", ""), **am})

    # RAG metrics — prefer top-level field; fall back to building from per-task
    rag = raw.get("rag_metrics", {})
    if not isinstance(rag, dict):
        rag = {}

    # If the top-level rag_metrics has no actual values, try to build from per-task
    # (e.g. files generated by RAGPipelineEvaluator store ragas_* in task.advanced_metrics)
    if not any(isinstance(v, list) and len(v) > 0 for v in rag.values()):
        built: Dict[str, List[float]] = {}
        for t_am in per_task:
            for k in _RAGAS_KEYS:
                v = t_am.get(k)
                if isinstance(v, (int, float)):
                    # Strip "ragas_" prefix to match dashboard template key format
                    short_k = k[len("ragas_"):] if k.startswith("ragas_") else k
                    built.setdefault(short_k, []).append(float(v))
        if built:
            rag = built

    return AdvancedMetrics(summary=summary, rag_metrics=rag, per_task=per_task)


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------

def _parse_llm_judge(raw_tasks: List[Dict[str, Any]]) -> "LLMJudgeData":
    """Collect llm_judge entries from task list and compute aggregates."""
    results = []
    model = ""
    total_cost = 0.0

    for t in raw_tasks:
        jd = t.get("llm_judge")
        if not jd or not isinstance(jd, dict) or jd.get("skipped") or not jd.get("scores"):
            continue
        results.append({
            "task_id": t.get("task_id", ""),
            **jd,
        })
        if not model and jd.get("model"):
            model = jd["model"]
        total_cost += jd.get("cost_usd", 0.0)

    if not results:
        return LLMJudgeData()

    dims = ["completeness", "relevance", "factual_consistency", "overall",
            "toxicity", "bias", "faithfulness", "criteria_overall"]
    avgs = {}
    for dim in dims:
        vals = [r["scores"][dim] for r in results if r.get("scores") and dim in r["scores"]]
        avgs[dim] = round(sum(vals) / len(vals), 3) if vals else 0.0

    return LLMJudgeData(
        results=results,
        avg_completeness=avgs.get("completeness", 0.0),
        avg_relevance=avgs.get("relevance", 0.0),
        avg_factual_consistency=avgs.get("factual_consistency", 0.0),
        avg_overall=avgs.get("overall", 0.0),
        avg_toxicity=avgs.get("toxicity", 0.0),
        avg_bias=avgs.get("bias", 0.0),
        avg_faithfulness=avgs.get("faithfulness", 0.0),
        avg_criteria_overall=avgs.get("criteria_overall", 0.0),
        total_cost_usd=round(total_cost, 6),
        judged_count=len(results),
        model=model,
    )


def _parse_tasks(raw_tasks: List[Dict[str, Any]]) -> List[TaskRecord]:
    result = []
    for t in raw_tasks:
        result.append(TaskRecord(
            task_id=t.get("task_id", ""),
            task_type=t.get("task_type", "unknown"),
            success=bool(t.get("success", False)),
            completion_score=float(t.get("completion_score", 0)),
            accuracy_score=float(t.get("accuracy_score", 0)),
            execution_time=float(t.get("execution_time", 0)),
            tokens_used=t.get("tokens_used") if isinstance(t.get("tokens_used"), dict) else {},
            tool_calls=t.get("tool_calls") or [],
            attempts=int(t.get("attempts", 1)),
            errors=t.get("errors") or [],
            timestamp=t.get("timestamp", ""),
            expected_tools=t.get("expected_tools"),
            framework=t.get("framework"),
            advanced_metrics=t.get("advanced_metrics") or {},
            raw=t,
        ))
    return result


# ---------------------------------------------------------------------------
# Main parse
# ---------------------------------------------------------------------------

def parse_file(path: Path) -> ResultFile:
    try:
        raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as _parse_err:
        logger.warning("parse_file: '%s' 파싱 실패 (빈 결과 반환): %s", path, _parse_err)
        raw = {}

    # Parse advanced first so we can reuse its rag_metrics for has_rag detection
    advanced = _parse_advanced(raw)
    harness_groups, loop_events, fault_tolerance_by_tool = _parse_harness_data(raw)

    # ResultFile.rag_metrics: top-level field wins; fall back to advanced.rag_metrics
    # (which was already built from per-task data if needed)
    top_rag = raw.get("rag_metrics", raw.get("report", {}).get("rag_metrics", {})) or {}
    rag_for_file = (
        top_rag
        if any(isinstance(v, list) and len(v) > 0 for v in top_rag.values())
        else advanced.rag_metrics
    )

    raw_tasks = raw.get("tasks", [])
    return ResultFile(
        path=path,
        file_id=_file_id(path),
        name=path.stem,
        timestamp=raw.get("timestamp", raw.get("metadata", {}).get("created_at", "")),
        total_tasks=int(raw.get("total_tasks",
                        raw.get("metadata", {}).get("total_tasks",
                        len(raw_tasks)))),
        tasks=_parse_tasks(raw_tasks),
        accuracy_metrics=raw.get("accuracy_metrics",
                                 raw.get("report", {}).get("accuracy_metrics", {})),
        efficiency_metrics=raw.get("efficiency_metrics",
                                   raw.get("report", {}).get("efficiency_metrics", {})),
        security_l1=_parse_security_l1(raw),
        security_l2=_parse_security_l2(raw),
        agentic=_parse_agentic(raw),
        quality_detail=_parse_quality_detail(raw),
        hallucination_detail=_parse_hallucination_detail(raw),
        advanced=advanced,
        insights=InsightsData(
            alerts=raw.get("alerts",
                           raw.get("report", {}).get("alerts", [])),
            recommendations=raw.get("recommendations",
                                    raw.get("report", {}).get("recommendations", [])),
        ),
        rag_metrics=rag_for_file,
        pricing=raw.get("pricing", {}),
        raw=raw,
        llm_judge=_parse_llm_judge(raw_tasks),
        conversation_sessions=_parse_conversation_sessions(raw),
        feedback_data=_parse_feedback_data(raw),
        anomaly_data=_parse_anomaly_data(raw),
        cost_data=_parse_cost_data(raw),
        streaming_data=_parse_streaming_data(raw),
        harness_groups=harness_groups,
        loop_events=loop_events,
        fault_tolerance_by_tool=fault_tolerance_by_tool,
    )


# ---------------------------------------------------------------------------
# Transparency file loader
# ---------------------------------------------------------------------------

_SKIP_DIRS = {"traces", "audit_logs", "annotations", "transparent_reports", "golden_datasets"}


def _load_transparency(results_dir: Path) -> TransparencyMeta:
    """Auto-detect trace/audit/annotation files adjacent to or inside results_dir."""
    meta = TransparencyMeta()
    # Check both inside and sibling of results_dir
    candidates = [results_dir, results_dir.parent]
    for base in candidates:
        traces_dir = base / "traces"
        if traces_dir.exists():
            meta.trace_files = sorted(traces_dir.glob("*.json"))
        audit_dir = base / "audit_logs"
        if audit_dir.exists():
            meta.audit_files = sorted(audit_dir.glob("*.json"))
        ann_dir = base / "annotations"
        if ann_dir.exists():
            meta.annotation_files = sorted(ann_dir.glob("*.json"))
    return meta


# ---------------------------------------------------------------------------
# Top-level load
# ---------------------------------------------------------------------------

def load_results(results_dir: Path) -> ResultSet:
    """
    Recursively parse all result JSON files in results_dir.
    Auto-detects transparency sub-directories (zero configuration).
    """
    files: List[ResultFile] = []

    for json_path in sorted(results_dir.rglob("*.json")):
        parts = {p.name for p in json_path.parents}
        if parts & _SKIP_DIRS:
            continue
        if "golden_datasets" in str(json_path):
            continue
        try:
            rf = parse_file(json_path)
            # Skip files that clearly have no task data and are configs
            if rf.total_tasks == 0 and not rf.raw.get("tasks") and json_path.stem in (
                "thresholds", "config", "advanced_eval_config"
            ):
                continue
            files.append(rf)
        except Exception as e:
            logger.debug("Failed to parse result file %s: %s", json_path, e)

    files.sort(key=lambda f: f.timestamp, reverse=True)
    transparency = _load_transparency(results_dir)
    return ResultSet(files=files, transparency=transparency)
