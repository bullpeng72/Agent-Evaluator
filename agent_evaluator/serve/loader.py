"""
Result file loader — parses agent_evaluator JSON output files into a unified model.

Zero-configuration: auto-detects traces / audit_logs / annotations sub-directories
adjacent to the results directory.
"""
from __future__ import annotations

import hashlib
import json
import logging
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
    pricing: Dict[str, float]
    raw: Dict[str, Any]

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

    return SecurityL2(
        privilege_escalation=priv_esc,
        attack_detection=atk_summary,
        escalation_events=esc_events,
        attack_detections=atk_dets,
    )


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
        from collections import defaultdict as _dd
        task_groups: dict = _dd(list)
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
            tokens_used=t.get("tokens_used") or {},
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
    raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    # Parse advanced first so we can reuse its rag_metrics for has_rag detection
    advanced = _parse_advanced(raw)

    # ResultFile.rag_metrics: top-level field wins; fall back to advanced.rag_metrics
    # (which was already built from per-task data if needed)
    top_rag = raw.get("rag_metrics", raw.get("report", {}).get("rag_metrics", {})) or {}
    rag_for_file = (
        top_rag
        if any(isinstance(v, list) and len(v) > 0 for v in top_rag.values())
        else advanced.rag_metrics
    )

    return ResultFile(
        path=path,
        file_id=_file_id(path),
        name=path.stem,
        timestamp=raw.get("timestamp", raw.get("metadata", {}).get("created_at", "")),
        total_tasks=int(raw.get("total_tasks",
                        raw.get("metadata", {}).get("total_tasks",
                        len(raw.get("tasks", []))))),
        tasks=_parse_tasks(raw.get("tasks", [])),
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
