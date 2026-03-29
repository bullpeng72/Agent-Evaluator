"""
Data API routes — full rich data exposure.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api")


def _rs(request: Request):
    return request.app.state.result_set


def _to_meta(f) -> Dict[str, Any]:
    hall_ev = f.accuracy_metrics.get("hallucination", {})
    tot = hall_ev.get("total_evaluated", 0) or 0
    flagged = hall_ev.get("total_flagged", 0) or 0
    hall_rate = round(flagged / tot * 100, 2) if tot > 0 else 0.0
    return {
        "id":            f.file_id,
        "name":          f.name,
        "timestamp":     f.timestamp,
        "total_tasks":   f.total_tasks,
        "tcr":           round(f.tcr, 2),
        "accuracy":      round(f.accuracy, 2),
        "hallucination": round(float(hall_rate), 2),
        "avg_latency":   round(f.avg_latency, 3),
        "total_cost":    round(f.total_cost, 6),
        "quality_avg":   round(f.quality_detail.avg_score * 20, 1),
        "has_security":  f.has_security,
        "has_agentic":   f.has_agentic,
        "has_advanced":  f.has_advanced,
        "has_rag":       f.has_rag,
        "has_quality":   f.has_quality_detail,
    }


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/results")
def list_results(request: Request) -> List[Dict[str, Any]]:
    return [_to_meta(f) for f in _rs(request).files]


@router.get("/results/{file_id}")
def get_result(file_id: str, request: Request) -> Dict[str, Any]:
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    tasks = [{
        "task_id":          t.task_id,
        "task_type":        t.task_type,
        "success":          t.success,
        "completion_score": t.completion_score,
        "accuracy_score":   round(t.accuracy_score, 4),
        "execution_time":   t.execution_time,
        "tokens_used":      t.tokens_used,
        "tool_calls":       t.tool_calls,
        "attempts":         t.attempts,
        "errors":           t.errors,
        "timestamp":        t.timestamp,
        "expected_tools":   t.expected_tools,
        "framework":        t.framework,
        "advanced_metrics": t.advanced_metrics,
        # Raw content fields — for failure cause analysis
        "question":         t.raw.get("question") or t.raw.get("input"),
        "response":         t.raw.get("response") or t.raw.get("output"),
        "ground_truth":     t.raw.get("ground_truth") or t.raw.get("expected_output") or t.raw.get("expected"),
        "accuracy_detail":  t.raw.get("accuracy_detail"),
    } for t in rf.tasks]

    # Security L1
    sec_l1 = {
        "input_security":   rf.security_l1.input_security,
        "output_leakage":   rf.security_l1.output_leakage,
        "authorization":    rf.security_l1.authorization,
        "input_evals":      rf.security_l1.input_evals,
        "output_detections":rf.security_l1.output_detections,
        "tool_calls_detail":rf.security_l1.tool_calls,
    }
    # Security L2
    sec_l2 = {
        "privilege_escalation": rf.security_l2.privilege_escalation,
        "attack_detection":     rf.security_l2.attack_detection,
        "escalation_events":    rf.security_l2.escalation_events,
        "attack_detections":    rf.security_l2.attack_detections,
    }
    # Agentic
    agentic = {
        "tool_selections":        rf.agentic.tool_selections,
        "tool_selection_summary": rf.agentic.tool_selection_summary,
        "tool_efficiency":        rf.agentic.tool_efficiency,
        "tool_call_executions":   rf.agentic.tool_call_executions,
        "agent_interactions":     rf.agentic.agent_interactions,
        "coordination_summary":   rf.agentic.coordination_summary,
        "workflow_executions":    rf.agentic.workflow_executions,
        "workflow_summary":       rf.agentic.workflow_summary,
        "retry_attempts":         rf.agentic.retry_attempts,
        "retry_summary":          rf.agentic.retry_summary,
    }
    # Quality detail
    quality_detail = {
        "evaluations":       rf.quality_detail.evaluations,
        "dimension_summary": rf.quality_detail.dimension_summary,
        "grade_distribution":rf.quality_detail.grade_distribution,
        "avg_score":         rf.quality_detail.avg_score,
    }
    # Hallucination detail
    hallucination_detail = {
        "detections":    rf.hallucination_detail.detections,
        "indicator_types": rf.hallucination_detail.indicator_types,
    }
    # Advanced / RAG
    advanced = {
        "summary":  rf.advanced.summary,
        "rag_metrics": rf.advanced.rag_metrics,
        "per_task": rf.advanced.per_task,
    }

    return {
        "id":                  rf.file_id,
        "name":                rf.name,
        "timestamp":           rf.timestamp,
        "total_tasks":         rf.total_tasks,
        "tasks":               tasks,
        "accuracy_metrics":    rf.accuracy_metrics,
        "efficiency_metrics":  rf.efficiency_metrics,
        "rag_metrics":         rf.rag_metrics,
        "pricing":             rf.pricing,
        # Rich data
        "security_l1":         sec_l1,
        "security_l2":         sec_l2,
        "agentic":             agentic,
        "quality_detail":      quality_detail,
        "hallucination_detail":hallucination_detail,
        "advanced":            advanced,
        "insights": {
            "alerts":          rf.insights.alerts,
            "recommendations": rf.insights.recommendations,
        },
        # Capability flags (aggregated)
        "has_security":  rf.has_security,
        "has_agentic":   rf.has_agentic,
        "has_advanced":  rf.has_advanced,
        "has_rag":       rf.has_rag,
        "has_quality":   rf.has_quality_detail,
        # Quality sub-flags
        "has_hallucination":   rf.has_hallucination,
        # Agentic sub-flags
        "has_tool_use":        rf.has_tool_use,
        "has_coordination":    rf.has_coordination,
        "has_workflow":        rf.has_workflow,
        "has_retry":           rf.has_retry,
        # Security sub-flags
        "has_input_security":  rf.has_input_security,
        "has_output_security": rf.has_output_security,
        "has_tool_auth":       rf.has_tool_auth,
        "has_attack_detect":   rf.has_attack_detect,
        # LLM Judge (Phase 1-A)
        "has_llm_judge": rf.llm_judge.judged_count > 0,
        "llm_judge": {
            "judged_count":           rf.llm_judge.judged_count,
            "avg_overall":            rf.llm_judge.avg_overall,
            "avg_completeness":       rf.llm_judge.avg_completeness,
            "avg_relevance":          rf.llm_judge.avg_relevance,
            "avg_factual_consistency":rf.llm_judge.avg_factual_consistency,
            "total_cost_usd":         rf.llm_judge.total_cost_usd,
            "model":                  rf.llm_judge.model,
            "results":                rf.llm_judge.results,
        },
    }


@router.get("/summary")
def get_summary(request: Request) -> Dict[str, Any]:
    rs = _rs(request)
    s = rs.summary()
    s["has_traces"]      = len(rs.transparency.trace_files) > 0
    s["has_audit"]       = len(rs.transparency.audit_files) > 0
    s["has_annotations"] = len(rs.transparency.annotation_files) > 0
    return s
