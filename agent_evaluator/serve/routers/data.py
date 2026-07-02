"""
Data API routes — full rich data exposure.
"""
from __future__ import annotations

import os
import time as _time_module
from collections import defaultdict
from datetime import datetime as _datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import json as _json_mod

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_evaluator.serve.routers._utils import _rs

_SERVER_START_TIME: float = _time_module.time()  # B1: 서버 기동 시각

router = APIRouter(prefix="/api", tags=["results"])

# ---------------------------------------------------------------------------
# B1: 결과 파일 아카이브/삭제 인메모리 저장소
# ---------------------------------------------------------------------------
_ARCHIVE_STORE: Dict[str, bool] = {}

# ---------------------------------------------------------------------------
# B2: 태스크 태그 인메모리 저장소 {file_id: {task_id: [tags]}}
# ---------------------------------------------------------------------------
_TASK_TAG_STORE: Dict[str, Dict[str, List[str]]] = {}


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
        "has_security":     f.has_security,
        "has_agentic":      f.has_agentic,
        "has_advanced":     f.has_advanced,
        "has_rag":          f.has_rag,
        "has_quality":      f.has_quality_detail,
        "has_conversation": f.has_conversation,
        "has_feedback":     f.has_feedback,
        "has_streaming":    f.has_streaming,
        "has_anomaly":      f.has_anomaly,
        "has_cost":         f.has_cost,
        "has_llm_judge":    f.has_llm_judge,
        # Gate B 세부: 도구·워크플로우
        "has_tool_use":     f.has_tool_use,
        "has_workflow":     f.has_workflow,
        # Gate C 세부: 재시도
        "has_retry":        f.has_retry,
        # Gate F 세부: 멀티에이전트 조율
        "has_coordination": f.has_coordination,
        # 단일 정규 Gate 활성화 소스 — 대시보드 전체가 이 값을 사용
        "gate_active":      f.gate_data_presence,
        # D2: LLM Judge 요약 — list_results 에서도 avg_overall 제공
        "llm_judge_avg":    round(f.llm_judge.avg_overall, 4) if f.has_llm_judge else None,
        # 보안 위협 건수 — 목록에서 보안 인시던트 정렬·필터 지원
        "security_incidents_count": (
            int(f.security_l1.input_security.get("inputs_with_threats", 0) or 0)
            + int(f.security_l1.output_leakage.get("outputs_with_leakage", 0) or 0)
            + int(f.security_l1.authorization.get("unauthorized_calls", 0) or 0)
            + len(f.security_l2.escalation_events)
            + len(f.security_l2.attack_detections)
        ) if f.has_security else 0,
        # 멀티모달 태스크 현황
        "has_multimodal":        f.has_multimodal if hasattr(f, "has_multimodal") else False,
        "multimodal_task_count": f.multimodal_task_count if hasattr(f, "multimodal_task_count") else 0,
    }


@router.get("/health", summary="Server health check")
def health(request: Request) -> Dict[str, Any]:
    """Return server status, version, file count, and total task count in detail."""
    try:
        _rs_obj = _rs(request)
        _files = getattr(_rs_obj, "files", [])
        _result_files_count = len(_files)
        _total_tasks = sum(getattr(f, "total_tasks", 0) for f in _files)
        _out_dir = str(getattr(request.app.state, "output_dir", "results/"))
    except Exception:
        _result_files_count = 0
        _total_tasks = 0
        _out_dir = "results/"

    try:
        from agent_evaluator import __version__ as _ver
    except Exception:
        try:
            import importlib.metadata as _im
            _ver = _im.version("agent-evaluator")
        except Exception:
            _ver = "unknown"

    # I1: OTEL 활성화 여부를 동적으로 감지
    try:
        from agent_evaluator.integrations.otel_provider import OTELProvider as _OTELProvider
        _otel_enabled = _OTELProvider.is_active() if hasattr(_OTELProvider, "is_active") else False
    except Exception:
        try:
            import opentelemetry  # noqa: F401
            _otel_enabled = True
        except ImportError:
            _otel_enabled = False

    return {
        "status": "ok",
        "version": _ver,
        "uptime_seconds": round(_time_module.time() - _SERVER_START_TIME, 1),
        "result_files_count": _result_files_count,
        "total_tasks_count": _total_tasks,
        "output_dir": _out_dir,
        "features": {
            "security_metrics": True,
            "hallucination_detection": True,
            "otel": _otel_enabled,  # I1: 하드코딩 False → 동적 감지
        },
    }


@router.get("/stats", summary="Overall statistics summary")
def get_stats(request: Request) -> Dict[str, Any]:
    """Return system-wide statistics summary."""
    try:
        _rs_obj = _rs(request)
        _files = getattr(_rs_obj, "files", [])
        _total_files = len(_files)
        _total_tasks = sum(getattr(f, "total_tasks", 0) for f in _files)
        _task_types: Dict[str, int] = defaultdict(int)
        _fw_dist: Dict[str, int] = defaultdict(int)
        _tcr_vals, _acc_vals, _err_rates = [], [], []

        for _f in _files:
            _tcr_vals.append(getattr(_f, "tcr", 0.0))
            _acc_vals.append(getattr(_f, "accuracy", 0.0))
            # task_type distribution from raw task data
            _tasks = getattr(_f, "tasks", []) or []
            for _t in _tasks:
                _tt = str(getattr(_t, "task_type", "unknown"))
                _task_types[_tt] += 1
                _fw = str((getattr(_t, "extra", {}) or {}).get("framework", "native"))
                _fw_dist[_fw] += 1
                _errs = getattr(_t, "errors", []) or []
                _err_rates.append(1.0 if _errs else 0.0)

        return {
            "total_files": _total_files,
            "total_tasks": _total_tasks,
            "avg_tcr": round(sum(_tcr_vals) / len(_tcr_vals), 4) if _tcr_vals else 0.0,
            "avg_accuracy": round(sum(_acc_vals) / len(_acc_vals), 4) if _acc_vals else 0.0,
            "top_task_types": sorted(_task_types, key=lambda k: _task_types[k], reverse=True)[:5],
            "framework_distribution": dict(_fw_dist),
            "error_rate": round(sum(_err_rates) / len(_err_rates), 4) if _err_rates else 0.0,
            "uptime_seconds": round(_time_module.time() - _SERVER_START_TIME, 1),
        }
    except Exception as _e:
        raise HTTPException(status_code=500, detail=str(_e))


@router.get("/results", summary="Result file list")
def list_results(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    sort_by: str = Query(
        default="timestamp",
        description="Sort field — timestamp | tcr | accuracy | avg_latency | total_tasks | total_cost",
    ),
    sort_desc: bool = Query(default=True, description="Sort descending (default True)"),
    # K: 범위 필터
    tcr_min: Optional[float] = Query(None, description="TCR minimum value (0–100)"),
    tcr_max: Optional[float] = Query(None, description="TCR maximum value (0–100)"),
    accuracy_min: Optional[float] = Query(None, description="Accuracy minimum value (0–100)"),
    age_hours: Optional[float] = Query(None, description="Files from the last N hours only"),
    # N: 샘플 태스크 포함
    include_sample: bool = Query(False, description="Include latest 3 task samples per file"),
) -> Dict[str, Any]:
    """Result file list — pagination + sorting support (B12, I2).

    **Sort keys (sort_by)**:
    - ``timestamp`` — file creation time (default)
    - ``tcr`` — Task Completion Rate (%)
    - ``accuracy`` — overall accuracy (0–100)
    - ``avg_latency`` — average response time in seconds
    - ``total_tasks`` — total task count
    - ``total_cost`` — total cost (USD)
    """
    # watch 모드: 항상 디스크에서 직접 읽어 최신 파일 목록 보장
    # SPEC-013: previous=기존 result_set을 전달해 변경되지 않은 파일은 재파싱을 건너뛴다
    # (요청마다 전량 재파싱하던 것을 요청마다 변경분만 재파싱하는 것으로 전환).
    if getattr(request.app.state, "watcher", None) is not None:
        try:
            from ..loader import load_results as _load_results
            request.app.state.result_set = _load_results(
                request.app.state.results_dir,
                previous=getattr(request.app.state, "result_set", None),
            )
        except Exception:
            pass

    _SORT_FIELDS = {"timestamp", "tcr", "accuracy", "avg_latency", "total_tasks", "total_cost"}
    if sort_by not in _SORT_FIELDS:
        sort_by = "timestamp"

    import datetime as _dt_mod

    rs = _rs(request)
    all_files = [f for f in rs.files if not _ARCHIVE_STORE.get(f.file_id, False)]

    # K: 범위 필터 적용
    if tcr_min is not None:
        all_files = [f for f in all_files if f.tcr >= tcr_min]
    if tcr_max is not None:
        all_files = [f for f in all_files if f.tcr <= tcr_max]
    if accuracy_min is not None:
        all_files = [f for f in all_files if f.accuracy >= accuracy_min]
    if age_hours is not None:
        _cutoff = _dt_mod.datetime.now() - _dt_mod.timedelta(hours=age_hours)
        def _file_mtime(f) -> _dt_mod.datetime:
            # 파일 수정 시간 또는 timestamp 필드로 필터
            try:
                _path = getattr(f, "path", None)
                if _path is not None:
                    import os as _os
                    return _dt_mod.datetime.fromtimestamp(_os.path.getmtime(str(_path)))
            except Exception:
                pass
            try:
                _ts = getattr(f, "timestamp", None)
                if _ts:
                    return _dt_mod.datetime.fromisoformat(str(_ts)[:19])
            except Exception:
                pass
            return _dt_mod.datetime.min
        all_files = [f for f in all_files if _file_mtime(f) >= _cutoff]

    # I2: 정렬
    def _sort_key(f):
        v = getattr(f, sort_by, None)
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    all_files.sort(key=_sort_key, reverse=sort_desc)

    total = len(all_files)
    skip = (page - 1) * limit
    files_page = all_files[skip: skip + limit]
    total_pages = max(1, (total + limit - 1) // limit)
    # D3: 전체 파일 기준 framework 분포 집계 (페이지 관계없이 전체 파일에서 계산)
    from collections import Counter as _Counter
    _fw_dist: _Counter = _Counter()
    for _f in all_files:
        for _t in (_f.tasks or []):
            _fw = str((getattr(_t, "extra", {}) or {}).get("framework", None)
                      or getattr(_t, "framework", None) or "native")
            _fw_dist[_fw] += 1

    # N: 각 파일의 최근 3개 태스크 샘플 구성
    def _build_entry(f) -> Dict[str, Any]:
        entry = _to_meta(f)
        if include_sample:
            try:
                _tasks = sorted(
                    f.tasks or [],
                    key=lambda t: str(getattr(t, "timestamp", "") or ""),
                    reverse=True,
                )[:3]
                entry["sample_tasks"] = [
                    {
                        "task_id":       t.task_id,
                        "task_type":     str(t.task_type),
                        "success":       t.success,
                        "accuracy_score": t.accuracy_score,
                        "timestamp":     (
                            t.timestamp.isoformat()
                            if hasattr(t.timestamp, "isoformat")
                            else str(t.timestamp)
                        ),
                    }
                    for t in _tasks
                ]
            except Exception:
                entry["sample_tasks"] = []
        return entry

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "sort_by": sort_by,
        "sort_desc": sort_desc,
        "framework_distribution": dict(_fw_dist),
        "files": [_build_entry(f) for f in files_page],
    }


# ---------------------------------------------------------------------------
# L: SSE 실시간 통계 엔드포인트
# ---------------------------------------------------------------------------
@router.get("/live-stats", summary="Live statistics stream (SSE)")
async def live_stats_sse(
    request: Request,
    file_id: Optional[str] = Query(None, description="Specific file ID (omit for global statistics)"),
    interval_seconds: float = Query(2.0, ge=0.5, le=30.0, description="Push interval in seconds"),
) -> StreamingResponse:
    """Push live statistics via SSE (Server-Sent Events).

    Sends current metrics as JSON via EventSource every interval_seconds.
    """
    import asyncio as _asyncio
    import datetime as _dt_mod2

    rs = _rs(request)

    async def event_stream():
        while True:
            try:
                stats: Dict[str, Any] = {
                    "timestamp": _dt_mod2.datetime.now().isoformat(),
                }
                if file_id:
                    rf = rs.by_id(file_id)
                    if rf is not None:
                        stats["file_id"] = file_id
                        stats["task_count"] = rf.total_tasks
                        _acc = [
                            t.accuracy_score
                            for t in (rf.tasks or [])
                            if hasattr(t, "accuracy_score")
                        ]
                        stats["avg_accuracy"] = round(sum(_acc) / len(_acc), 4) if _acc else 0.0
                        stats["tcr"] = round(rf.tcr, 2)
                        stats["avg_latency"] = round(rf.avg_latency, 3)
                    else:
                        stats["error"] = f"file_id '{file_id}' not found"
                else:
                    # 전체 통계
                    _files = [f for f in rs.files if not _ARCHIVE_STORE.get(f.file_id, False)]
                    stats["file_count"] = len(_files)
                    stats["total_tasks"] = sum(f.total_tasks for f in _files)
                    _all_tcr = [f.tcr for f in _files]
                    stats["avg_tcr"] = round(sum(_all_tcr) / len(_all_tcr), 2) if _all_tcr else 0.0
                yield f"data: {_json_mod.dumps(stats)}\n\n"
            except Exception as _e:
                yield f"data: {_json_mod.dumps({'error': str(_e)})}\n\n"
            await _asyncio.sleep(interval_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# M: 시간대별 지표 트렌드 엔드포인트
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/hourly-stats", summary="Hourly aggregate statistics")
def get_hourly_stats(
    file_id: str,
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Last N hours"),
    metrics: str = Query(
        "tcr,avg_accuracy,avg_latency",
        description="Comma-separated metric list — tcr|avg_accuracy|avg_latency|task_count|error_rate",
    ),
) -> Dict[str, Any]:
    """Return metric trend aggregated in hourly buckets."""
    import datetime as _dt_mod3

    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    _ALLOWED_METRICS = {"tcr", "avg_accuracy", "avg_latency", "task_count", "error_rate"}
    requested = {m.strip() for m in metrics.split(",") if m.strip() in _ALLOWED_METRICS}

    # 시간 범위 컷오프
    _cutoff = _dt_mod3.datetime.now() - _dt_mod3.timedelta(hours=hours)

    # tasks를 시간 단위로 bucketing
    buckets: Dict[str, list] = {}
    for task in (rf.tasks or []):
        try:
            ts_raw = getattr(task, "timestamp", None) or ""
            ts = _dt_mod3.datetime.fromisoformat(str(ts_raw)[:19]) if ts_raw else None
            if ts is None or ts < _cutoff:
                continue
            hour_key = ts.strftime("%Y-%m-%dT%H:00")
        except Exception:
            continue
        buckets.setdefault(hour_key, []).append(task)

    trend: List[Dict[str, Any]] = []
    for hour_key in sorted(buckets.keys()):
        bucket = buckets[hour_key]
        entry: Dict[str, Any] = {"hour": hour_key, "task_count": len(bucket)}
        if "tcr" in requested:
            entry["tcr"] = round(
                sum(1 for t in bucket if t.success) / len(bucket), 4
            ) if bucket else 0.0
        if "avg_accuracy" in requested:
            _accs = [t.accuracy_score for t in bucket]
            entry["avg_accuracy"] = round(sum(_accs) / len(_accs), 4) if _accs else 0.0
        if "avg_latency" in requested:
            _lats = [t.execution_time for t in bucket]
            entry["avg_latency"] = round(sum(_lats) / len(_lats), 4) if _lats else 0.0
        if "error_rate" in requested:
            entry["error_rate"] = round(
                sum(1 for t in bucket if t.errors) / len(bucket), 4
            ) if bucket else 0.0
        trend.append(entry)

    return {
        "file_id": file_id,
        "hours": hours,
        "metrics": sorted(requested),
        "trend": trend,
    }


@router.get("/results/{file_id}", summary="Result file detail")
def get_result(file_id: str, request: Request) -> Dict[str, Any]:
    """Return the full content of a single evaluation result file.

    Includes ``summary`` (TCR, accuracy, latency aggregates), ``tasks`` (per-task detail),
    ``harness_gates`` (Gate A–G scores), ``extra_metrics``, and more.

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    def _task_extra_field(t, key):
        """Safely extract a field from TaskResult.extra or raw."""
        extra = getattr(t, "extra", None)
        if isinstance(extra, dict):
            return extra.get(key)
        # extra 없는 경우 raw에서 fallback
        raw = getattr(t, "raw", None)
        if isinstance(raw, dict):
            return raw.get(key)
        return None

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
        # I — adapter_error_fallback 노출
        "adapter_error": (
            lambda _ae: {"framework": _ae.get("framework"), "error": _ae.get("error")}
            if _ae else None
        )(_task_extra_field(t, "adapter_error_fallback")),
        # J — model_name
        "model_name": _task_extra_field(t, "model_name"),
        # P1-C: 상세 필드 — chain_steps, quality_dimensions, streaming_metadata
        "chain_steps": _task_extra_field(t, "chain_steps"),
        "quality_dimensions": (
            t.advanced_metrics.get("quality_dimensions")
            if isinstance(t.advanced_metrics, dict) else None
        ),
        "streaming_metadata": {
            "ttft_ms": (
                round(_task_extra_field(t, "ttft_seconds") * 1000, 2)
                if _task_extra_field(t, "ttft_seconds") is not None else None
            ),
            "chunk_count": _task_extra_field(t, "chunk_count"),
        } if (
            _task_extra_field(t, "ttft_seconds") is not None
            or _task_extra_field(t, "chunk_count") is not None
        ) else None,
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

    # K — frameworks 분포 집계
    _fw_dist: Dict[str, int] = {}
    for t in rf.tasks:
        _fw = getattr(t, "framework", None) or _task_extra_field(t, "framework") or "native"
        _fw_dist[_fw] = _fw_dist.get(_fw, 0) + 1

    return {
        "id":                  rf.file_id,
        "name":                rf.name,
        "timestamp":           rf.timestamp,
        "total_tasks":         rf.total_tasks,
        "frameworks":          _fw_dist,
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
        # Phase 1-C: 멀티턴 대화 세션
        "conversation_sessions": rf.conversation_sessions,
        "has_conversation": len(rf.conversation_sessions) > 0,
        # Phase 2-C: 사용자 반응 (ImplicitFeedback)
        "feedback_data": rf.feedback_data,
        "has_feedback": bool(rf.feedback_data and rf.feedback_data.get("total", 0) > 0),
        # Phase 2-A: 실시간 스트리밍 스냅샷
        "streaming_data": rf.streaming_data,
        "has_streaming": bool(rf.streaming_data),
        # Phase 3-B: 이상 감지
        "anomaly_data": rf.anomaly_data,
        "has_anomaly": len(rf.anomaly_data) > 0,
        # 비용 추적
        "cost_data": rf.cost_data,
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
            "avg_toxicity":           rf.llm_judge.avg_toxicity,
            "avg_bias":               rf.llm_judge.avg_bias,
            "avg_faithfulness":       rf.llm_judge.avg_faithfulness,       # v0.7.6
            "avg_criteria_overall":   rf.llm_judge.avg_criteria_overall,   # v0.7.6
            "total_cost_usd":         rf.llm_judge.total_cost_usd,
            "model":                  rf.llm_judge.model,
            "results":                rf.llm_judge.results,
        },
        # 단일 정규 Gate 활성화 소스
        "gate_active":             getattr(rf, "gate_data_presence", {}),
        # Phase 2: Harness 그룹 + 에이전틱 확장
        "harness_groups":          getattr(rf, "harness_groups", None),
        "has_harness":             getattr(rf, "has_harness", False),
        "loop_events":             getattr(rf, "loop_events", []),
        "fault_tolerance_by_tool": getattr(rf, "fault_tolerance_by_tool", {}),
    }


@router.delete("/results/{file_id}", summary="Delete result file")
def delete_result(
    file_id: str,
    request: Request,
    soft: bool = Query(default=True),
) -> Dict[str, Any]:
    """Delete a result file (B1 extension).

    soft=True: archive (sets in-memory _archived flag)
    soft=False: permanently delete the file
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    if soft:
        _ARCHIVE_STORE[file_id] = True
        return {"file_id": file_id, "archived": True, "name": rf.name}
    else:
        path = getattr(rf, "path", None)
        if path is not None and os.path.exists(str(path)):
            results_dir: Path = request.app.state.results_dir
            try:
                Path(str(path)).resolve().relative_to(results_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=400, detail="File path outside results directory")
            try:
                os.remove(str(path))
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}")
        return {"deleted": True, "file_id": file_id, "name": rf.name}


@router.post("/results/{file_id}/tasks/bulk-tag", summary="Bulk tag tasks")
async def bulk_tag_tasks(
    file_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Bulk add tags to multiple tasks.

    Body example::

        {"task_ids": ["task_001", "task_002"], "tags": ["regression", "slow"]}
    """
    import json as _json
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        body = await request.body()
        data = _json.loads(body) if body else {}
    except Exception:
        data = {}

    task_ids: List[str] = data.get("task_ids", [])
    tags: List[str] = data.get("tags", [])

    if not isinstance(task_ids, list):
        task_ids = [str(task_ids)]
    if not isinstance(tags, list):
        tags = [str(tags)]

    if file_id not in _TASK_TAG_STORE:
        _TASK_TAG_STORE[file_id] = {}

    for tid in task_ids:
        existing = _TASK_TAG_STORE[file_id].get(tid, [])
        new_tags = [t for t in tags if t not in existing]
        _TASK_TAG_STORE[file_id][tid] = existing + new_tags

    return {"updated": len(task_ids), "tags": tags, "task_ids": task_ids}


@router.get("/results/{file_id}/aggregate", summary="Task group aggregate")
def aggregate_tasks(
    file_id: str,
    request: Request,
    by: str = Query(default="task_type", description="Grouping key: task_type|framework|hour|day"),
) -> Dict[str, Any]:
    """Metric aggregate — grouped by the specified key.

    Returns:
        file_id, by, groups (key → count/avg_accuracy/avg_latency/tcr/total_tokens)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    from datetime import datetime as _dt

    groups: Dict[str, Dict[str, Any]] = {}

    for t in rf.tasks:
        if by == "task_type":
            key = str(getattr(t, "task_type", "unknown"))
        elif by == "framework":
            key = str(getattr(t, "framework", "native") or "native")
        elif by == "hour":
            try:
                ts_raw = getattr(t, "timestamp", None) or ""
                ts = _dt.fromisoformat(str(ts_raw)[:19]) if ts_raw else None
                key = str(ts.hour) if ts else "unknown"
            except Exception:
                key = "unknown"
        elif by == "day":
            try:
                ts_raw = getattr(t, "timestamp", None) or ""
                ts = _dt.fromisoformat(str(ts_raw)[:19]) if ts_raw else None
                key = ts.strftime("%Y-%m-%d") if ts else "unknown"
            except Exception:
                key = "unknown"
        else:
            key = str(getattr(t, by, "unknown"))

        if key not in groups:
            groups[key] = {"_acc": [], "_lat": [], "_success": 0, "_tokens": 0}

        groups[key]["_acc"].append(t.accuracy_score)
        groups[key]["_lat"].append(t.execution_time)
        if t.success:
            groups[key]["_success"] += 1
        tok = t.tokens_used or {}
        total_tok = tok.get("total", tok.get("input", 0) + tok.get("output", 0))
        groups[key]["_tokens"] += total_tok

    result_groups: Dict[str, Any] = {}
    for key, g in groups.items():
        count = len(g["_acc"])
        result_groups[key] = {
            "count": count,
            "avg_accuracy": round(sum(g["_acc"]) / count, 4) if count else 0.0,
            "avg_latency": round(sum(g["_lat"]) / count, 4) if count else 0.0,
            "tcr": round(g["_success"] / count * 100, 2) if count else 0.0,
            "total_tokens": g["_tokens"],
        }

    return {
        "file_id": file_id,
        "by": by,
        "groups": result_groups,
        # Phase 2: Harness 그룹 집계 포함
        "harness_groups": getattr(rf, "harness_groups", None),
    }


@router.get("/results/{file_id}/reliability", summary="Reliability metrics")
def get_reliability(file_id: str, request: Request) -> Dict[str, Any]:
    """Reliability tab — reproducibility, loop, and tool fault-tolerance aggregate (Phase 2).

    Returns:
        error_free_rate, retry_free_rate, loop_events, fault_tolerance_by_tool,
        harness_groups, reproducibility_by_type
    """
    import math
    from collections import defaultdict

    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    tasks = rf.tasks
    n = len(tasks) or 1
    error_free = sum(1 for t in tasks if not t.errors)
    retry_free = sum(1 for t in tasks if t.attempts <= 1)

    # completion_score 분산 by task_type
    by_type: Dict[str, list] = defaultdict(list)
    for t in tasks:
        by_type[str(getattr(t, "task_type", "unknown"))].append(
            getattr(t, "completion_score", 0.0) or 0.0
        )

    repro_by_type: Dict[str, Any] = {}
    for tt, scores in by_type.items():
        if len(scores) < 2:
            repro_by_type[tt] = {"count": len(scores), "mean": None, "std": None, "cv": None}
            continue
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = math.sqrt(variance)
        cv = round(std / mean * 100, 1) if mean > 0 else None
        repro_by_type[tt] = {
            "count": len(scores),
            "mean": round(mean, 3),
            "std": round(std, 3),
            "cv": cv,
        }

    return {
        "file_id": file_id,
        "total_tasks": rf.total_tasks,
        "error_free_rate": round(error_free / n * 100, 1),
        "retry_free_rate": round(retry_free / n * 100, 1),
        "loop_events": getattr(rf, "loop_events", []),
        "fault_tolerance_by_tool": getattr(rf, "fault_tolerance_by_tool", {}),
        "harness_groups": getattr(rf, "harness_groups", None),
        "reproducibility_by_type": repro_by_type,
    }


@router.post("/results/{file_id}/tasks/filter", summary="Advanced task filter")
async def filter_tasks_advanced(file_id: str, request: Request) -> Dict[str, Any]:
    """Search tasks by compound filter conditions (B4, I3).

    **Request body format**::

        {
            "conditions": [
                {"field": "accuracy_score", "op": "gte", "value": 0.7},
                {"field": "task_type",      "op": "eq",  "value": "qa"},
                {"field": "errors",         "op": "eq",  "value": []},
                {"field": "tokens_used.total", "op": "lt", "value": 5000}
            ],
            "logic": "AND",
            "skip": 0,
            "limit": 50
        }

    **Supported operators (op)**:

    | op       | type         | description                                   |
    |----------|--------------|----------------------------------------------|
    | eq       | any type     | equality check (case-insensitive for strings) |
    | ne       | any type     | inequality check                              |
    | gt       | number       | greater than                                  |
    | gte      | number       | greater than or equal                         |
    | lt       | number       | less than                                     |
    | lte      | number       | less than or equal                            |
    | contains | string       | substring match (case-insensitive)            |
    | in       | list         | field value in the provided list              |

    **Supported fields**:
    - Top-level TaskResult attributes: ``task_id``, ``task_type``, ``success``, ``completion_score``,
      ``accuracy_score``, ``execution_time``, ``attempts``, ``errors``, ``framework``
    - Nested fields: ``tokens_used.total``, ``tokens_used.input``, ``tokens_used.output``
    - ``extra`` dictionary keys: ``extra.model``, ``extra.framework``, etc.

    **logic**: ``"AND"`` (default) or ``"OR"`` — how conditions are combined.
    """
    import json as _json
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        body = await request.body()
        data = _json.loads(body) if body else {}
    except Exception:
        data = {}

    conditions: List[Dict[str, Any]] = data.get("conditions", [])
    logic: str = data.get("logic", "AND").upper()
    skip: int = int(data.get("skip", 0))
    limit: int = int(data.get("limit", 50))

    def _match(task, cond: Dict[str, Any]) -> bool:
        field = cond.get("field", "")
        op = cond.get("op", "eq")
        value = cond.get("value")
        # Support nested fields like "tokens_used.total"
        parts = field.split(".")
        tv = task
        try:
            for part in parts:
                if isinstance(tv, dict):
                    tv = tv.get(part)
                else:
                    tv = getattr(tv, part, None)
        except Exception:
            tv = None

        if op == "eq":
            return str(tv).lower() == str(value).lower() if isinstance(value, str) else tv == value
        elif op == "ne":
            return str(tv).lower() != str(value).lower() if isinstance(value, str) else tv != value
        elif op == "gt":
            return float(tv or 0) > float(value)
        elif op == "gte":
            return float(tv or 0) >= float(value)
        elif op == "lt":
            return float(tv or 0) < float(value)
        elif op == "lte":
            return float(tv or 0) <= float(value)
        elif op == "contains":
            return str(value).lower() in str(tv or "").lower()
        elif op == "in":
            return tv in value if isinstance(value, list) else False
        return True

    filtered = []
    for t in rf.tasks:
        if not conditions:
            filtered.append(t)
            continue
        results_bool = [_match(t, c) for c in conditions]
        if logic == "OR":
            if any(results_bool):
                filtered.append(t)
        else:  # AND
            if all(results_bool):
                filtered.append(t)

    total = len(filtered)
    page_tasks = filtered[skip: skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "results": [{
            "task_id":        t.task_id,
            "task_type":      t.task_type,
            "framework":      t.framework,
            "success":        t.success,
            "accuracy_score": round(t.accuracy_score, 4),
            "completion_score": t.completion_score,
            "execution_time": t.execution_time,
            "errors":         t.errors,
            "timestamp":      t.timestamp,
        } for t in page_tasks],
    }


@router.get("/results/{file_id}/tasks/search", summary="Task search")
def search_tasks(
    file_id: str,
    request: Request,
    task_type: Optional[str] = Query(default=None),
    framework: Optional[str] = Query(default=None),
    accuracy_min: float = Query(default=0.0, ge=0.0, le=1.0),
    accuracy_max: float = Query(default=1.0, ge=0.0, le=1.0),
    has_error: Optional[bool] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> Dict[str, Any]:
    """Task filter search — combine task_type / framework / accuracy / has_error.

    Returns:
        total (count after filtering), tasks (page slice), aggregates (average metrics)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    filtered = rf.tasks
    if task_type is not None:
        _tt = task_type.lower()
        filtered = [t for t in filtered if str(getattr(t, "task_type", "")).lower() == _tt]
    if framework is not None:
        _fw = framework.lower()
        filtered = [t for t in filtered if str(getattr(t, "framework", "")).lower() == _fw]
    if has_error is not None:
        filtered = [t for t in filtered if bool(t.errors) == has_error]
    filtered = [
        t for t in filtered
        if accuracy_min <= t.accuracy_score <= accuracy_max
    ]

    total = len(filtered)
    page = filtered[skip: skip + limit]

    avg_accuracy = round(sum(t.accuracy_score for t in filtered) / total, 4) if total else 0.0
    avg_latency = round(sum(t.execution_time for t in filtered) / total, 4) if total else 0.0
    avg_completion = round(sum(t.completion_score for t in filtered) / total, 4) if total else 0.0
    success_count = sum(1 for t in filtered if t.success)

    return {
        "file_id": file_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "aggregates": {
            "avg_accuracy": avg_accuracy,
            "avg_latency": avg_latency,
            "avg_completion": avg_completion,
            "tcr": round(success_count / total * 100, 2) if total else 0.0,
            "error_count": sum(1 for t in filtered if t.errors),
        },
        "tasks": [{
            "task_id":        t.task_id,
            "task_type":      t.task_type,
            "framework":      t.framework,
            "success":        t.success,
            "accuracy_score": round(t.accuracy_score, 4),
            "completion_score": t.completion_score,
            "execution_time": t.execution_time,
            "errors":         t.errors,
            "timestamp":      t.timestamp,
        } for t in page],
    }


@router.get("/results/{file_id}/distributions", summary="Score distribution")
def get_task_distributions(file_id: str, request: Request) -> Dict[str, Any]:
    """Distribution statistics by task_type / framework / accuracy range — for dashboard charts."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    by_type: Dict[str, int] = defaultdict(int)
    by_framework: Dict[str, int] = defaultdict(int)
    accuracy_buckets: Dict[str, int] = {
        "0-20%": 0, "20-40%": 0, "40-60%": 0, "60-80%": 0, "80-100%": 0,
    }
    latency_buckets: Dict[str, int] = {
        "<1s": 0, "1-3s": 0, "3-10s": 0, ">10s": 0,
    }
    error_count = 0

    for t in rf.tasks:
        by_type[str(getattr(t, "task_type", "unknown"))] += 1
        by_framework[str(getattr(t, "framework", "native"))] += 1
        acc = t.accuracy_score * 100
        if acc < 20:
            accuracy_buckets["0-20%"] += 1
        elif acc < 40:
            accuracy_buckets["20-40%"] += 1
        elif acc < 60:
            accuracy_buckets["40-60%"] += 1
        elif acc < 80:
            accuracy_buckets["60-80%"] += 1
        else:
            accuracy_buckets["80-100%"] += 1
        lat = t.execution_time
        if lat < 1:
            latency_buckets["<1s"] += 1
        elif lat < 3:
            latency_buckets["1-3s"] += 1
        elif lat < 10:
            latency_buckets["3-10s"] += 1
        else:
            latency_buckets[">10s"] += 1
        if t.errors:
            error_count += 1

    total = len(rf.tasks)
    return {
        "file_id": file_id,
        "total_tasks": total,
        "task_types": dict(by_type),
        "frameworks": dict(by_framework),
        "accuracy_distribution": accuracy_buckets,
        "latency_distribution": latency_buckets,
        "error_rate": round(error_count / total * 100, 2) if total else 0.0,
    }


_SEARCH_ALLOWED_FIELDS = {"question", "response", "framework", "task_type", "task_id"}


@router.get("/tasks/search", summary="Cross-file task search")
def search_task_across_files(
    request: Request,
    task_id: Optional[str] = Query(default=None, description="Search by specific task_id"),
    framework: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Full-text search query (applied to search_fields)"),
    search_fields: str = Query(
        default="question,response",
        description="Comma-separated fields to search: question,response,framework,task_type,task_id",
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    """Cross-file search by task_id / framework / task_type / q (N: includes search_fields parameter)."""
    rs = _rs(request)
    results: List[Dict[str, Any]] = []

    # N: search_fields 파싱 및 유효성 검증
    _parsed_fields = [f.strip() for f in search_fields.split(",") if f.strip()]
    _valid_fields = [f for f in _parsed_fields if f in _SEARCH_ALLOWED_FIELDS]
    if not _valid_fields:
        _valid_fields = ["question", "response"]

    def _field_value(t, field: str) -> str:
        """Extract search field values from a task."""
        if field in ("question", "response"):
            raw = getattr(t, "raw", None) or {}
            if field == "question":
                return str(raw.get("question") or raw.get("input") or "")
            return str(raw.get("response") or raw.get("output") or "")
        return str(getattr(t, field, "") or "")

    for file in rs.files:
        for t in file.tasks:
            if task_id is not None and t.task_id != task_id:
                continue
            if framework is not None and str(getattr(t, "framework", "")).lower() != framework.lower():
                continue
            if task_type is not None and str(getattr(t, "task_type", "")).lower() != task_type.lower():
                continue
            # N: q 파라미터로 search_fields 검색
            if q is not None:
                _q_lower = q.lower()
                _matched = any(_q_lower in _field_value(t, f).lower() for f in _valid_fields)
                if not _matched:
                    continue
            results.append({
                "file_id":      file.file_id,
                "file_name":    file.name,
                "task_id":      t.task_id,
                "task_type":    t.task_type,
                "framework":    t.framework,
                "success":      t.success,
                "accuracy_score": round(t.accuracy_score, 4),
                "execution_time": t.execution_time,
                "timestamp":    t.timestamp,
            })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    return {
        "total": len(results),
        "limit": limit,
        "search_fields": _valid_fields,
        "q": q,
        "results": results,
    }


@router.get("/results/{file_id}/tasks/{task_id}", summary="Task detail")
def get_task_detail(file_id: str, task_id: str, request: Request) -> Dict[str, Any]:
    """Per-task detail API — includes chain_steps, state_transitions, agent_interactions."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    task = next((t for t in rf.tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    raw = task.raw or {}
    return {
        "task_id":          task.task_id,
        "task_type":        task.task_type,
        "success":          task.success,
        "completion_score": task.completion_score,
        "accuracy_score":   round(task.accuracy_score, 4),
        "execution_time":   task.execution_time,
        "tokens_used":      task.tokens_used,
        "attempts":         task.attempts,
        "errors":           task.errors,
        "timestamp":        task.timestamp,
        "framework":        task.framework,
        # 기본 필드
        "question":         raw.get("question") or raw.get("input"),
        "response":         raw.get("response") or raw.get("output"),
        "ground_truth":     raw.get("ground_truth") or raw.get("expected_output") or raw.get("expected"),
        "accuracy_detail":  raw.get("accuracy_detail"),
        # Layer 2 agentic 필드 — WorkflowExecutionTracker, AgentCoordinationTracker 활성화 트리거
        "tool_calls":       task.tool_calls,
        "expected_tools":   task.expected_tools,
        "chain_steps":      raw.get("chain_steps"),
        "state_transitions": raw.get("state_transitions"),
        "agent_interactions": raw.get("agent_interactions"),
        # 고급 지표
        "advanced_metrics": task.advanced_metrics,
        # D3: partial_reason + 멀티모달 extra 필드
        "partial_reason":         raw.get("extra", {}).get("partial_reason") if isinstance(raw.get("extra"), dict) else None,
        "image_count":            (raw.get("extra") or {}).get("image_count"),
        "audio_duration_seconds": (raw.get("extra") or {}).get("audio_duration_seconds"),
        "video_frames":           (raw.get("extra") or {}).get("video_frames"),
        # B1: LLM Judge 결과 (태스크별 스코어)
        "llm_judge":              raw.get("llm_judge"),
        # A1: streaming 메트릭
        "streaming_steps":        (raw.get("extra") or {}).get("streaming_steps"),
        "chunk_count":            (raw.get("extra") or {}).get("chunk_count"),
    }


@router.get("/results/{file_id}/metrics/{metric_name}", summary="Metric detail")
def get_metric_detail(file_id: str, metric_name: str, request: Request) -> Dict[str, Any]:
    """Return detailed data for a single metric specified by name.

    Supported metric_name values:
    ``tcr``, ``accuracy``, ``latency``, ``tokens``, ``hallucination``,
    ``quality``, ``security``, ``agentic``, ``cost``, ``llm_judge``
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    _METRIC_MAP: Dict[str, Any] = {
        "tcr":           (rf.accuracy_metrics or {}).get("tcr", {}),
        "accuracy":      (rf.accuracy_metrics or {}).get("accuracy_scores", {}),
        "latency":       (rf.efficiency_metrics or {}).get("latency", {}),
        "tokens":        (rf.efficiency_metrics or {}).get("tokens", {}),
        "hallucination": {
            "rate":     rf.accuracy_metrics.get("hallucination", {}).get("total_flagged", 0),
            "detail":   rf.hallucination_detail.detections if rf.has_hallucination else [],
            "indicator_types": rf.hallucination_detail.indicator_types if rf.has_hallucination else {},
        },
        "quality": {
            "avg_score":         rf.quality_detail.avg_score,
            "evaluations":       rf.quality_detail.evaluations,
            "dimension_summary": rf.quality_detail.dimension_summary,
            "grade_distribution":rf.quality_detail.grade_distribution,
        },
        "security": {
            "input":  rf.security_l1.input_security,
            "output": rf.security_l1.output_leakage,
            "auth":   rf.security_l1.authorization,
            "privilege_escalation": rf.security_l2.privilege_escalation,
            "attack_detection":     rf.security_l2.attack_detection,
        },
        "agentic": {
            "tool_efficiency":  rf.agentic.tool_efficiency,
            "retry_summary":    rf.agentic.retry_summary,
            "coordination_summary": rf.agentic.coordination_summary,
            "workflow_summary": rf.agentic.workflow_summary,
        },
        "cost":          rf.cost_data,
        "llm_judge": {
            "judged_count":           rf.llm_judge.judged_count,
            "avg_overall":            rf.llm_judge.avg_overall,
            "avg_completeness":       rf.llm_judge.avg_completeness,
            "avg_relevance":          rf.llm_judge.avg_relevance,
            "avg_factual_consistency":rf.llm_judge.avg_factual_consistency,
            "avg_toxicity":           rf.llm_judge.avg_toxicity,
            "avg_bias":               rf.llm_judge.avg_bias,
            "avg_faithfulness":       rf.llm_judge.avg_faithfulness,       # v0.7.6
            "avg_criteria_overall":   rf.llm_judge.avg_criteria_overall,   # v0.7.6
            "results":                rf.llm_judge.results,
        },
    }

    if metric_name not in _METRIC_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown metric '{metric_name}'. Valid: {sorted(_METRIC_MAP)}",
        )

    return {
        "file_id":     file_id,
        "metric_name": metric_name,
        "data":        _METRIC_MAP[metric_name],
    }


@router.get("/results/{file_id}/heatmap/{metric}", summary="Metric heatmap")
def get_metric_heatmap(file_id: str, metric: str, request: Request) -> Dict[str, Any]:
    """Return task × time heatmap data.

    metric: ``accuracy_score``, ``execution_time``, ``completion_score``

    Returns:
        x_labels (time buckets), y_labels (task_type), matrix (y×x grid)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    _VALID = {"accuracy_score", "execution_time", "completion_score"}
    if metric not in _VALID:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown metric '{metric}'. Valid: {sorted(_VALID)}",
        )

    from datetime import datetime as _dt

    # Collect (hour_bucket, task_type, value)
    bucket_map: Dict[str, Dict[str, List[float]]] = {}  # hour → task_type → [values]
    for t in rf.tasks:
        try:
            ts_raw = getattr(t, "timestamp", None) or ""
            ts = _dt.fromisoformat(str(ts_raw)[:19]) if ts_raw else None
            hour_key = ts.strftime("%Y-%m-%dT%H:00") if ts else "unknown"
        except Exception:
            hour_key = "unknown"
        tt = str(getattr(t, "task_type", "unknown"))
        val = float(getattr(t, metric, 0.0) or 0.0)
        bucket_map.setdefault(hour_key, {}).setdefault(tt, []).append(val)

    x_labels = sorted(bucket_map.keys())
    y_labels_set: set = set()
    for tmap in bucket_map.values():
        y_labels_set.update(tmap.keys())
    y_labels = sorted(y_labels_set)

    matrix: List[List[Optional[float]]] = []
    for y in y_labels:
        row: List[Optional[float]] = []
        for x in x_labels:
            vals = bucket_map.get(x, {}).get(y)
            row.append(round(sum(vals) / len(vals), 4) if vals else None)
        matrix.append(row)

    return {
        "file_id":  file_id,
        "metric":   metric,
        "x_labels": x_labels,
        "y_labels": y_labels,
        "matrix":   matrix,
    }


@router.get("/summary", summary="Overall result summary")
def get_summary(request: Request) -> Dict[str, Any]:
    """Return summary statistics for all result files + transparency data availability.

    Unlike ``/api/stats``, also includes ``has_traces``, ``has_audit``, and ``has_annotations`` flags
    (used to determine whether the dashboard Transparency tab should be enabled).

    Returns:
        Summary metrics including total_files, total_tasks, avg_tcr, +
        has_traces (bool), has_audit (bool), has_annotations (bool)
    """
    rs = _rs(request)
    s = rs.summary()
    s["has_traces"]      = len(rs.transparency.trace_files) > 0
    s["has_audit"]       = len(rs.transparency.audit_files) > 0
    s["has_annotations"] = len(rs.transparency.annotation_files) > 0
    return s


# ---------------------------------------------------------------------------
# v0.7.7 신규 API endpoints (B1–B6)
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/timeline", summary="Timeline aggregate")
def get_result_timeline(
    file_id: str,
    request: Request,
    metric: str = Query(default="accuracy_score", description="Aggregation metric"),
    bucket: str = Query(default="hour", description="Time bucket: minute|hour|day"),
) -> Dict[str, Any]:
    """Task time-series aggregate — aggregates the specified metric into time buckets.

    Returns:
        buckets (time key list), values (average per bucket), counts (task count per bucket)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    _VALID_METRICS = {"accuracy_score", "execution_time", "completion_score", "tokens_used"}
    if metric not in _VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Invalid metric. Valid: {sorted(_VALID_METRICS)}")

    _VALID_BUCKETS = {"minute", "hour", "day"}
    if bucket not in _VALID_BUCKETS:
        bucket = "hour"

    from datetime import datetime as _dt

    fmt = {"minute": "%Y-%m-%dT%H:%M", "hour": "%Y-%m-%dT%H:00", "day": "%Y-%m-%d"}[bucket]
    bucket_data: Dict[str, List[float]] = {}

    for t in rf.tasks:
        try:
            ts_raw = getattr(t, "timestamp", None) or ""
            ts = _dt.fromisoformat(str(ts_raw)[:19]) if ts_raw else None
            bk = ts.strftime(fmt) if ts else "unknown"
        except Exception:
            bk = "unknown"
        raw_val = getattr(t, metric, None)
        if isinstance(raw_val, dict):
            raw_val = raw_val.get("total", 0)
        val = float(raw_val or 0.0)
        bucket_data.setdefault(bk, []).append(val)

    buckets = sorted(bucket_data.keys())
    values = [round(sum(bucket_data[b]) / len(bucket_data[b]), 4) for b in buckets]
    counts = [len(bucket_data[b]) for b in buckets]

    return {
        "file_id": file_id,
        "metric": metric,
        "bucket": bucket,
        "buckets": buckets,
        "values": values,
        "counts": counts,
    }


@router.get("/compare", summary="Result file comparison")
def compare_results(
    request: Request,
    ids: str = Query(..., description="Comma-separated file_id list (e.g. id1,id2)"),
    detailed: bool = Query(default=False, description="If True, compute detailed diff based on common task_ids"),
) -> Dict[str, Any]:
    """Compare key metrics across multiple result files side by side (B2/B5).

    When detailed=True, computes accuracy_delta/latency_delta for common task_ids
    and returns regression_tasks/improvement_tasks lists.

    Returns:
        files (list of per-file metric dicts), delta (first vs. rest difference),
        [when detailed=True] detailed, regression_tasks, improvement_tasks
    """
    rs = _rs(request)
    file_ids = [fid.strip() for fid in ids.split(",") if fid.strip()]
    if not file_ids:
        raise HTTPException(status_code=400, detail="ids parameter is required")

    # 실제 ResultFile 객체 보존 (detailed 계산용)
    rf_map: Dict[str, Any] = {}
    files_data: List[Dict[str, Any]] = []
    for fid in file_ids:
        rf = rs.by_id(fid)
        if rf is None:
            files_data.append({"file_id": fid, "found": False})
            continue
        rf_map[fid] = rf
        files_data.append({
            "file_id":    fid,
            "name":       rf.name,
            "found":      True,
            "total_tasks": rf.total_tasks,
            "tcr":        round(rf.tcr, 2),
            "accuracy":   round(rf.accuracy, 2),
            "avg_latency": round(rf.avg_latency, 3),
            "total_cost": round(rf.total_cost, 6),
        })

    delta: List[Dict[str, Any]] = []
    if len(files_data) >= 2 and files_data[0].get("found") and files_data[1].get("found"):
        base = files_data[0]
        for other in files_data[1:]:
            if other.get("found"):
                delta.append({
                    "vs": other["file_id"],
                    "tcr_delta":      round(base["tcr"] - other["tcr"], 2),
                    "accuracy_delta": round(base["accuracy"] - other["accuracy"], 2),
                    "latency_delta":  round(base["avg_latency"] - other["avg_latency"], 3),
                })

    result: Dict[str, Any] = {"file_count": len(file_ids), "files": files_data, "delta": delta}

    if detailed and len(file_ids) >= 2:
        fid_a, fid_b = file_ids[0], file_ids[1]
        rf_a = rf_map.get(fid_a)
        rf_b = rf_map.get(fid_b)
        if rf_a is not None and rf_b is not None:
            tasks_a = {t.task_id: t for t in rf_a.tasks}
            tasks_b = {t.task_id: t for t in rf_b.tasks}
            common_ids = set(tasks_a.keys()) & set(tasks_b.keys())
            per_task_diff: List[Dict[str, Any]] = []
            regression_tasks: List[Dict[str, Any]] = []
            improvement_tasks: List[Dict[str, Any]] = []
            for tid in sorted(common_ids):
                ta = tasks_a[tid]
                tb = tasks_b[tid]
                acc_delta = round(ta.accuracy_score - tb.accuracy_score, 4)
                lat_delta = round(ta.execution_time - tb.execution_time, 4)
                entry = {
                    "task_id": tid,
                    "task_type": ta.task_type,
                    f"accuracy_{fid_a}": round(ta.accuracy_score, 4),
                    f"accuracy_{fid_b}": round(tb.accuracy_score, 4),
                    "accuracy_delta": acc_delta,
                    "latency_delta": lat_delta,
                }
                per_task_diff.append(entry)
                if acc_delta <= -0.05:
                    regression_tasks.append(entry)
                elif acc_delta >= 0.05:
                    improvement_tasks.append(entry)

            result["detailed"] = {
                "common_task_count": len(common_ids),
                "only_in_first": len(tasks_a) - len(common_ids),
                "only_in_second": len(tasks_b) - len(common_ids),
                "per_task": per_task_diff,
            }
            result["regression_tasks"] = regression_tasks
            result["improvement_tasks"] = improvement_tasks

    return result


@router.get("/leaderboard", summary="Leaderboard")
def get_leaderboard(
    request: Request,
    sort_by: str = Query(default="tcr", description="Sort key: tcr|accuracy|avg_latency|total_cost"),
    limit: int = Query(default=20, ge=1, le=100),
    ascending: bool = Query(default=False),
) -> Dict[str, Any]:
    """Leaderboard of all evaluation files — ranked by the specified metric.

    Returns:
        leaderboard (rank, file_id, name, key metrics dict list)
    """
    rs = _rs(request)
    _VALID_SORT = {"tcr", "accuracy", "avg_latency", "total_cost", "total_tasks"}
    if sort_by not in _VALID_SORT:
        sort_by = "tcr"

    entries: List[Dict[str, Any]] = []
    for rf in rs.files:
        entries.append({
            "file_id":    rf.file_id,
            "name":       rf.name,
            "timestamp":  rf.timestamp,
            "total_tasks": rf.total_tasks,
            "tcr":        round(rf.tcr, 2),
            "accuracy":   round(rf.accuracy, 2),
            "avg_latency": round(rf.avg_latency, 3),
            "total_cost": round(rf.total_cost, 6),
        })

    entries.sort(key=lambda x: x.get(sort_by, 0), reverse=not ascending)
    ranked = entries[:limit]
    for i, e in enumerate(ranked):
        e["rank"] = i + 1

    return {"sort_by": sort_by, "ascending": ascending, "total": len(entries), "leaderboard": ranked}


def _enrich_session_turns(session: Dict[str, Any]) -> Dict[str, Any]:
    """Augment the session turn list with tool_calls / model_name / tokens_used fields."""
    turns = session.get("turns", [])
    # turns 가 int (turn_count) 인 경우 그대로 반환 (구버전 호환)
    if not isinstance(turns, list):
        return session
    enriched_turns = []
    for t in turns:
        if not isinstance(t, dict):
            enriched_turns.append(t)
            continue
        meta = t.get("metadata") or {}
        enriched_turn = dict(t)
        # metadata 안에 있는 tool_calls / model_name / tokens_used를 최상위로 노출
        if "tool_calls" not in enriched_turn:
            enriched_turn["tool_calls"] = meta.get("tool_calls")
        if "model_name" not in enriched_turn:
            enriched_turn["model_name"] = meta.get("model_name") or meta.get("model")
        if "tokens_used" not in enriched_turn:
            enriched_turn["tokens_used"] = meta.get("tokens_used") or meta.get("token_usage")
        enriched_turns.append(enriched_turn)
    return {**session, "turns": enriched_turns}


@router.get("/results/{file_id}/sessions", summary="Conversation sessions list")
def get_sessions(
    file_id: str,
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    include_turns: bool = Query(default=True, description="Include per-turn detail data"),
) -> Dict[str, Any]:
    """Multi-turn conversation sessions list (B4/M3) — pagination + per-turn tool_calls/model_name/tokens_used.

    Returns:
        total, sessions (per-session summary dict; includes tool_calls/model_name/tokens_used when turns included)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    sessions = rf.conversation_sessions or []
    total = len(sessions)
    page = sessions[skip: skip + limit]

    if include_turns:
        page = [_enrich_session_turns(s) for s in page]

    return {
        "file_id": file_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "sessions": page,
    }


# In-memory tag store (process 재시작 시 초기화) — 프로덕션에서는 영속 저장소 사용 권장
_TAG_STORE: Dict[str, List[str]] = {}
_tag_store_lock = defaultdict(list)


@router.post("/results/{file_id}/tags", summary="Add tags")
def add_tags(
    file_id: str,
    request: Request,
    tags: List[str] = None,
) -> Dict[str, Any]:
    """Add tags to a file.

    Body: JSON list of tag strings  (e.g. ``["production", "v2", "regression"]``)

    Returns:
        file_id, tags (complete current tag list)
    """
    import json as _json
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Accept tags from query param or body
    if tags is None:
        try:
            import asyncio
            body = asyncio.get_event_loop().run_until_complete(request.body())
            tags = _json.loads(body) if body else []
        except Exception:
            tags = []
    if not isinstance(tags, list):
        tags = [str(tags)]

    existing = _TAG_STORE.get(file_id, [])
    new_tags = [str(t) for t in tags if str(t) not in existing]
    _TAG_STORE[file_id] = existing + new_tags
    return {"file_id": file_id, "tags": _TAG_STORE[file_id], "added": new_tags}


@router.get("/results/{file_id}/tags", summary="Tag list")
def get_tags(file_id: str, request: Request) -> Dict[str, Any]:
    """Get file tags (B5 auxiliary)."""
    rs = _rs(request)
    if rs.by_id(file_id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"file_id": file_id, "tags": _TAG_STORE.get(file_id, [])}


@router.get("/results/{file_id}/tasks/{task_id}/similar", summary="Similar task search")
def get_similar_tasks(
    file_id: str,
    task_id: str,
    request: Request,
    top_k: int = Query(default=5, ge=1, le=50),
) -> Dict[str, Any]:
    """Similar task search — approximate similarity based on accuracy_score + task_type.

    Returns:
        task_id, similar (top_k similar task dict list)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    target = next((t for t in rf.tasks if t.task_id == task_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Task not found")

    candidates = []
    for t in rf.tasks:
        if t.task_id == task_id:
            continue
        # Similarity: type match (0.5 bonus) + accuracy proximity
        type_bonus = 0.5 if t.task_type == target.task_type else 0.0
        acc_sim = 1.0 - abs(t.accuracy_score - target.accuracy_score)
        score = round(type_bonus + acc_sim * 0.5, 4)
        candidates.append({
            "task_id":      t.task_id,
            "task_type":    t.task_type,
            "accuracy_score": round(t.accuracy_score, 4),
            "execution_time": t.execution_time,
            "similarity":   score,
            "question":     (t.raw or {}).get("question") or (t.raw or {}).get("input"),
        })

    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return {
        "file_id": file_id,
        "task_id": task_id,
        "top_k": top_k,
        "similar": candidates[:top_k],
    }


# ---------------------------------------------------------------------------
# B2: TaskResult.extra 필드 집계 API
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/aggregate/extra", summary="extra field aggregate")
def aggregate_extra_field(
    file_id: str,
    request: Request,
    field: str = Query(..., description="Key to aggregate from the extra dictionary"),
) -> Dict[str, Any]:
    """Return the value frequency distribution for a specific extra field."""
    rs = _rs(request)
    f = next((x for x in rs.files if x.file_id == file_id), None)
    if f is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    tasks = getattr(f, "tasks", []) or []
    freq: Dict[str, int] = defaultdict(int)
    missing = 0
    for t in tasks:
        extra = getattr(t, "extra", {}) or {}
        if field in extra:
            freq[str(extra[field])] += 1
        else:
            missing += 1
    return {
        "field": field,
        "values": dict(sorted(freq.items(), key=lambda x: x[1], reverse=True)),
        "total_tasks": len(tasks),
        "tasks_with_field": len(tasks) - missing,
        "missing_count": missing,
    }


# ---------------------------------------------------------------------------
# B3: Anomaly 이벤트 설명 API
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/anomaly/explain/{event_id}", summary="Anomaly event explanation")
def explain_anomaly_event(
    file_id: str,
    event_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Return the cause and recommendations for a specific anomaly detection event."""
    rs = _rs(request)
    f = next((x for x in rs.files if x.file_id == file_id), None)
    if f is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    raw = getattr(f, "raw", {}) or {}
    anomaly_data = raw.get("anomaly_data", {}) or {}
    events = anomaly_data.get("anomalies", []) or []
    event = next((e for e in events if str(e.get("event_id", "")) == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Anomaly event not found: {event_id}")
    metric = event.get("metric", "unknown")
    value = event.get("value", 0.0)
    threshold = event.get("threshold", 0.0)
    deviation_pct = abs(value - threshold) / max(abs(threshold), 1e-9) * 100
    severity = "critical" if deviation_pct > 30 else ("warning" if deviation_pct > 10 else "info")
    suggestions = {
        "accuracy": "Accuracy is low. Consider improving prompts or upgrading the model.",
        "latency": "Response time is high. Consider caching or parallel processing.",
        "error_rate": "Error rate is high. Agent stability review is required.",
    }
    return {
        "event_id": event_id,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "deviation_pct": round(deviation_pct, 2),
        "severity": severity,
        "explanation": f"{metric} value {value:.4f} exceeded threshold {threshold:.4f} by {deviation_pct:.1f}%.",
        "suggested_action": suggestions.get(metric, "Analyze this metric in detail."),
        "timestamp": event.get("timestamp", ""),
    }


# ---------------------------------------------------------------------------
# B2: 프레임워크별 지표 집계 API
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/frameworks", summary="Framework analysis")
def get_framework_breakdown(file_id: str, request: Request) -> Dict[str, Any]:
    """Framework-level metric aggregate — TCR / accuracy / latency / token analysis by framework.

    Returns:
        file_id, framework_count, frameworks (framework → metrics dict)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    from collections import defaultdict as _defaultdict
    fw_data: Dict[str, Dict[str, Any]] = _defaultdict(lambda: {
        "task_count": 0, "success_count": 0,
        "accuracy_sum": 0.0, "latency_sum": 0.0, "tokens_sum": 0,
        "completion_sum": 0.0, "tool_calls_sum": 0, "error_count": 0,
    })

    for task in rf.tasks:
        fw = task.framework or "native"
        d = fw_data[fw]
        d["task_count"] += 1
        if task.success:
            d["success_count"] += 1
        d["accuracy_sum"] += task.accuracy_score
        d["latency_sum"] += task.execution_time
        d["tokens_sum"] += (task.tokens_used or {}).get("total", 0)
        d["completion_sum"] += task.completion_score
        d["tool_calls_sum"] += len(task.tool_calls) if task.tool_calls else 0
        _has_error = bool(task.errors) if task.errors is not None else False
        if _has_error:
            d["error_count"] += 1

    result: Dict[str, Any] = {}
    for fw, d in fw_data.items():
        tc = d["task_count"]
        result[fw] = {
            "task_count":           tc,
            "tcr":                  round(d["success_count"] / tc * 100, 2) if tc else 0.0,
            "avg_accuracy":         round(d["accuracy_sum"] / tc, 4) if tc else 0.0,
            "avg_completion":       round(d["completion_sum"] / tc, 4) if tc else 0.0,
            "avg_latency_s":        round(d["latency_sum"] / tc, 4) if tc else 0.0,
            "avg_tokens_total":     round(d["tokens_sum"] / tc) if tc else 0,
            "avg_tool_calls":       round(d["tool_calls_sum"] / tc, 2) if tc else 0.0,
            "error_rate":           round(d["error_count"] / tc * 100, 2) if tc else 0.0,
        }

    return {
        "file_id":         file_id,
        "framework_count": len(result),
        "frameworks":      result,
    }


# ---------------------------------------------------------------------------
# B4: LLM Judge 상세 집계 API
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/llm_judge", summary="LLM Judge detail results")
def get_llm_judge_details(
    file_id: str,
    request: Request,
    min_score: Optional[float] = Query(default=None, description="Minimum overall score filter"),
    max_score: Optional[float] = Query(default=None, description="Maximum overall score filter"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    """LLM Judge result detail aggregate endpoint.

    Returns individual task judge scores (completeness/relevance/factual_consistency/overall).
    Filter by overall score range using min_score / max_score.

    Returns:
        file_id, model, aggregate statistics, results (per-task judge result list)
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    jd = rf.llm_judge
    results = list(jd.results or [])

    # 점수 범위 필터
    if min_score is not None:
        results = [r for r in results if (r.get("scores") or {}).get("overall", 0.0) >= min_score]
    if max_score is not None:
        results = [r for r in results if (r.get("scores") or {}).get("overall", 1.0) <= max_score]

    total = len(results)
    page = results[skip: skip + limit]

    return {
        "file_id":               file_id,
        "judged_count":          jd.judged_count,
        "model":                 jd.model,
        "avg_completeness":      jd.avg_completeness,
        "avg_relevance":         jd.avg_relevance,
        "avg_factual_consistency": jd.avg_factual_consistency,
        "avg_overall":           jd.avg_overall,
        "total_cost_usd":        jd.total_cost_usd,
        "filtered_count":        total,
        "skip":                  skip,
        "limit":                 limit,
        "results":               page,
    }


# ---------------------------------------------------------------------------
# O: Anomaly 응답 Pydantic 스키마
# ---------------------------------------------------------------------------

class AnomalyEventSchema(BaseModel):
    """Schema for individual anomaly detection events."""
    event_id: str = ""
    event_type: str = ""
    detected_at: str = ""
    metric_name: Optional[str] = None
    current_value: Optional[float] = None
    baseline_value: Optional[float] = None
    anomaly_score: Optional[float] = None
    description: Optional[str] = None


class AnomalyListResponse(BaseModel):
    """Response schema for anomaly detection event list."""
    file_id: str
    anomaly_count: int
    events: list  # List[AnomalyEventSchema] — dict compatible


# ---------------------------------------------------------------------------
# D7: Anomaly 이벤트 목록 API
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/anomaly", summary="Anomaly detection results (file)", response_model=AnomalyListResponse)
def get_anomaly(file_id: str, request: Request) -> Dict[str, Any]:
    """Return anomaly detection event list and summary."""
    rs = _rs(request)
    f = next((x for x in rs.files if x.file_id == file_id), None)
    if f is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    # anomaly_data: list from rf.anomaly_data or dict from raw
    anomaly_events = []
    if hasattr(f, "anomaly_data") and isinstance(f.anomaly_data, list):
        anomaly_events = f.anomaly_data
    else:
        raw = getattr(f, "raw", {}) or {}
        ad = raw.get("anomaly_data") or {}
        if isinstance(ad, list):
            anomaly_events = ad
        elif isinstance(ad, dict):
            anomaly_events = ad.get("anomalies", []) or []

    by_severity: Dict[str, int] = {}
    by_metric: Dict[str, int] = {}
    for ev in anomaly_events:
        sev = str(ev.get("severity", "unknown"))
        met = str(ev.get("metric", "unknown"))
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_metric[met] = by_metric.get(met, 0) + 1

    return {
        "file_id": file_id,
        "anomaly_count": len(anomaly_events),
        "events": anomaly_events,      # O: AnomalyListResponse compatible
        "anomalies": anomaly_events,   # backward compatible
        "summary": {
            "by_severity": by_severity,
            "by_metric": by_metric,
        },
    }


# ---------------------------------------------------------------------------
# D9: Multimodal 집계 API
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/multimodal", summary="Multimodal data")
def get_multimodal(file_id: str, request: Request) -> Dict[str, Any]:
    """Return multimodal metric aggregate based on task extra fields."""
    rs = _rs(request)
    f = next((x for x in rs.files if x.file_id == file_id), None)
    if f is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    total_tasks = f.total_tasks or 0
    tasks_with_images = 0
    tasks_with_audio = 0
    tasks_with_video = 0
    total_images = 0
    total_audio_seconds = 0.0
    total_video_frames = 0
    for task in (f.tasks or []):
        extra = (getattr(task, "extra", None) or {})
        imgs = extra.get("image_count", 0) or 0
        aud = extra.get("audio_duration_seconds", 0) or 0.0
        vid = extra.get("video_frames", 0) or 0
        if imgs:
            tasks_with_images += 1
            total_images += int(imgs)
        if aud:
            tasks_with_audio += 1
            total_audio_seconds += float(aud)
        if vid:
            tasks_with_video += 1
            total_video_frames += int(vid)
    multimodal_tasks = max(tasks_with_images, tasks_with_audio, tasks_with_video)
    return {
        "file_id": file_id,
        "total_tasks": total_tasks,
        "multimodal_task_rate": round(multimodal_tasks / total_tasks * 100, 2) if total_tasks > 0 else 0.0,
        "tasks_with_images": tasks_with_images,
        "tasks_with_audio": tasks_with_audio,
        "tasks_with_video": tasks_with_video,
        "total_images": total_images,
        "total_audio_seconds": round(total_audio_seconds, 2),
        "total_video_frames": total_video_frames,
    }


# ---------------------------------------------------------------------------
# B4: Implicit feedback stats API
# ---------------------------------------------------------------------------
@router.get("/results/{file_id}/feedback/stats", summary="Feedback statistics")
def feedback_stats(file_id: str, request: Request) -> Dict[str, Any]:
    """Return implicit feedback statistics."""
    rs = _rs(request)
    f = next((x for x in rs.files if x.file_id == file_id), None)
    if f is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    raw = getattr(f, "raw", {}) or {}
    fb_data = raw.get("feedback_data", {}) or {}
    if not fb_data:
        return {"total_feedback": 0, "message": "no feedback data found"}
    entries = fb_data.get("entries", []) or []
    if not entries:
        return {"total_feedback": 0, "message": "no feedback entries found"}
    scores = [float(e.get("score", 0)) for e in entries if "score" in e]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    positive = sum(1 for s in scores if s >= 0.5)
    by_type: Dict[str, int] = defaultdict(int)
    for e in entries:
        tt = str(e.get("task_type", "unknown"))
        by_type[tt] += 1
    return {
        "total_feedback": len(entries),
        "avg_score": round(avg_score, 4),
        "positive_count": positive,
        "negative_count": len(scores) - positive,
        "by_task_type": dict(by_type),
    }


# ---------------------------------------------------------------------------
# B5: Webhook firing history API
# ---------------------------------------------------------------------------
_WEBHOOK_HISTORY: Dict[str, list] = {}


@router.get("/webhooks/{webhook_id}/history", summary="Webhook history")
def webhook_history(webhook_id: str) -> Dict[str, Any]:
    """Return webhook trigger history."""
    history = _WEBHOOK_HISTORY.get(webhook_id, [])
    return {
        "webhook_id": webhook_id,
        "history": history,
        "total_fires": len(history),
    }


@router.post("/webhooks/{webhook_id}/test", summary="Send webhook test")
def webhook_test(webhook_id: str) -> Dict[str, Any]:
    """Record a test entry in the webhook trigger history (in-memory).

    Does not send an actual HTTP request to an external URL. To send a real POST to an external URL,
    use ``POST /api/webhook/test`` (body: ``{"url": "..."}``).

    Args:
        webhook_id: Arbitrary webhook identifier. Retrieve history via ``GET /api/webhooks/{webhook_id}/history``.
    """
    entry = {
        "fired_at": _datetime.now().isoformat(),
        "payload": {"test": True, "webhook_id": webhook_id},
        "success": True,
        "status_code": 200,
    }
    _WEBHOOK_HISTORY.setdefault(webhook_id, []).append(entry)
    return {"status": "fired", "entry": entry}


# ---------------------------------------------------------------------------
# B6: Result JSON file import API
# ---------------------------------------------------------------------------
@router.post("/results/import", summary="Import result file")
async def import_results(
    request: Request,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload a JSON result file and save it to output_dir."""
    import json as _json
    content = await file.read()
    try:
        data = _json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    if "task_results" not in data and "tasks" not in data:
        raise HTTPException(status_code=400, detail="JSON must contain 'task_results' or 'tasks' key")
    task_count = len(data.get("task_results", data.get("tasks", [])))
    ts = int(_time_module.time())
    filename = f"imported_{ts}"
    try:
        out_dir = str(getattr(request.app.state, "output_dir", "results"))
        os.makedirs(out_dir, exist_ok=True)
        fpath = os.path.join(out_dir, f"{filename}.json")
        with open(fpath, "w", encoding="utf-8") as _fh:
            _json.dump(data, _fh, ensure_ascii=False, indent=2)
    except Exception as _e:
        raise HTTPException(status_code=500, detail=f"Save failed: {_e}")
    return {"file_id": filename, "task_count": task_count, "message": "imported successfully"}


# ---------------------------------------------------------------------------
# B7: API version info
# ---------------------------------------------------------------------------
@router.get("/version", summary="API version info")
def api_version() -> Dict[str, Any]:
    """Return API version information."""
    return {
        "current": "v1",
        "supported": ["v1"],
        "deprecated": [],
    }


# ---------------------------------------------------------------------------
# B8: Rate limit status API
# ---------------------------------------------------------------------------
_REQUEST_COUNTS: Dict[str, int] = defaultdict(int)


@router.get("/rate-limit/status", summary="API rate limit status")
def rate_limit_status() -> Dict[str, Any]:
    """Get API rate limit configuration.

    In the current version, ``current_counts`` is not aggregated and always returns an empty object (``{}``).
    ``limits.default`` (default 1000) is a reference configuration value; no actual blocking logic is implemented.
    """
    return {
        "limits": {"default": 1000},
        "current_counts": dict(_REQUEST_COUNTS),
        "reset_time": "hourly",
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# H3: API response cache stats endpoint
# ---------------------------------------------------------------------------
@router.get("/cache/stats", summary="Cache statistics")
def cache_stats() -> Dict[str, Any]:
    """Return response cache hit/miss statistics."""
    try:
        from agent_evaluator.serve.cache import _GLOBAL_CACHE
        return _GLOBAL_CACHE.stats()
    except Exception:
        return {"status": "cache not available"}


# ---------------------------------------------------------------------------
# P2-C: Quality Heatmap endpoint
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/quality-heatmap", summary="Quality heatmap")
def get_quality_heatmap(
    file_id: str,
    request: Request,
    group_by: str = Query("task_type", description="Grouping key: task_type | framework | hour"),
    metric: str = Query("accuracy_score", description="Metric: accuracy_score | completion_score | execution_time"),
) -> Dict[str, Any]:
    """Quality heatmap — group_by × metric cross-aggregate (P2-C).

    Used to visualize the distribution of quality metrics by task_type/framework/time period as a heatmap in the dashboard.

    Args:
        file_id: Evaluation result file ID.
        group_by: Row axis grouping key (``task_type`` | ``framework`` | ``hour``).
        metric: Metric to aggregate (``accuracy_score`` | ``completion_score`` | ``execution_time``).

    Returns:
        groups (group name list), matrix (group → bucket → average value), bucket_labels (bucket labels).
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    _allowed_metrics = {"accuracy_score", "completion_score", "execution_time"}
    if metric not in _allowed_metrics:
        raise HTTPException(status_code=422, detail=f"metric must be one of {sorted(_allowed_metrics)}")

    _allowed_groups = {"task_type", "framework", "hour"}
    if group_by not in _allowed_groups:
        raise HTTPException(status_code=422, detail=f"group_by must be one of {sorted(_allowed_groups)}")

    from collections import defaultdict as _dd

    # score_buckets: 0.0~0.2, 0.2~0.4, 0.4~0.6, 0.6~0.8, 0.8~1.0
    bucket_labels = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    _NUM_BUCKETS = 5

    # {group: {bucket_idx: [values]}}
    data: Dict[str, Dict[int, List[float]]] = _dd(lambda: _dd(list))

    for t in rf.tasks:
        # 그룹 키 결정
        if group_by == "task_type":
            grp = str(t.task_type or "unknown")
        elif group_by == "framework":
            grp = str(t.framework or "native")
        else:  # hour
            try:
                ts = t.timestamp
                if hasattr(ts, "hour"):
                    grp = f"{ts.hour:02d}:00"
                elif isinstance(ts, str):
                    grp = ts[11:13] + ":00" if len(ts) >= 13 else "00:00"
                else:
                    grp = "00:00"
            except Exception:
                grp = "00:00"

        # 지표 값 결정
        if metric == "accuracy_score":
            val = float(t.accuracy_score or 0.0)
        elif metric == "completion_score":
            val = float(t.completion_score or 0.0)
        else:  # execution_time — normalize (10s baseline)
            raw_val = float(t.execution_time or 0.0)
            val = min(1.0, raw_val / 10.0)

        # 0~4 버킷 할당
        bucket_idx = min(int(val * _NUM_BUCKETS), _NUM_BUCKETS - 1)
        data[grp][bucket_idx].append(val)

    # 집계
    groups = sorted(data.keys())
    matrix: Dict[str, List[Optional[float]]] = {}
    for grp in groups:
        row: List[Optional[float]] = []
        for bi in range(_NUM_BUCKETS):
            vals = data[grp].get(bi, [])
            row.append(round(sum(vals) / len(vals), 4) if vals else None)
        matrix[grp] = row

    return {
        "file_id":       file_id,
        "group_by":      group_by,
        "metric":        metric,
        "groups":        groups,
        "bucket_labels": bucket_labels,
        "matrix":        matrix,
    }


# ---------------------------------------------------------------------------
# C1: Chain-steps 상세 데이터 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/tasks/{task_id}/chain-steps", summary="Chain execution steps")
def get_task_chain_steps(file_id: str, task_id: str, request: Request) -> Dict[str, Any]:
    """Return chain_steps detail data for a specific task.

    Used to visualize the agent's execution flow in the dashboard.
    Falls back to advanced_metrics when chain_steps is not present.
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    task = next((t for t in rf.tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # extra 또는 raw에서 chain_steps 추출
    extra = getattr(task, "extra", None) or {}
    chain_steps = (extra.get("chain_steps") if isinstance(extra, dict) else None)
    # advanced_metrics fallback
    if chain_steps is None:
        adv = getattr(task, "advanced_metrics", {}) or {}
        chain_steps = adv.get("chain_steps")

    # step_timeline 구성 (누적 타이밍)
    step_timeline = []
    if chain_steps:
        cumulative_ms = 0.0
        for step in chain_steps:
            dur_ms = float(step.get("execution_time", 0.0)) * 1000
            step_timeline.append({
                "name": step.get("name", "step"),
                "type": step.get("type", "unknown"),
                "start_ms": cumulative_ms,
                "duration_ms": dur_ms,
                "status": "success" if step.get("success", True) else "error",
                "output_preview": str(step.get("output", ""))[:200],
            })
            cumulative_ms += dur_ms

    return {
        "file_id": file_id,
        "task_id": task_id,
        "chain_steps": chain_steps or [],
        "step_count": len(chain_steps) if chain_steps else 0,
        "step_timeline": step_timeline,
        "framework": getattr(task, "framework", None),
    }


# ---------------------------------------------------------------------------
# C2: 대화 세션 턴별 상세 데이터 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/conversations/{session_id}/turns", summary="Conversation turn list")
def get_conversation_turns(
    file_id: str,
    session_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Return per-turn detail data for a specific conversation session."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    sessions = getattr(rf, "sessions", None) or []
    session = next((s for s in sessions if getattr(s, "session_id", None) == session_id), None)

    if session is None:
        # fallback: look in tasks' extra for session_id matching
        session_tasks = [
            t for t in rf.tasks
            if (getattr(t, "extra", None) or {}).get("session_id") == session_id
            or (getattr(t, "raw", None) or {}).get("session_id") == session_id
        ]
        if not session_tasks:
            raise HTTPException(status_code=404, detail="Session not found")
        turns = [
            {
                "turn_index": i,
                "task_id": t.task_id,
                "accuracy_score": round(t.accuracy_score, 4),
                "completion_score": round(t.completion_score, 4),
                "execution_time": t.execution_time,
                "tool_calls": len(t.tool_calls) if t.tool_calls else 0,
                "errors": bool(t.errors),
                "question": (getattr(t, "raw", {}) or {}).get("question"),
                "response": (getattr(t, "raw", {}) or {}).get("response"),
            }
            for i, t in enumerate(session_tasks)
        ]
        return {
            "file_id": file_id,
            "session_id": session_id,
            "turn_count": len(turns),
            "turns": turns,
            "avg_accuracy": round(sum(t["accuracy_score"] for t in turns) / len(turns), 4) if turns else 0.0,
        }

    # session object가 있는 경우
    turns_raw = getattr(session, "turns", []) or []
    turns = [
        {
            "turn_index": i,
            "user_input": getattr(t, "user_input", ""),
            "agent_response": getattr(t, "agent_response", ""),
            "latency_ms": round(getattr(t, "latency_ms", 0.0), 2),
            "metadata": getattr(t, "metadata", {}),
        }
        for i, t in enumerate(turns_raw)
    ]
    return {
        "file_id": file_id,
        "session_id": session_id,
        "turn_count": len(turns),
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# C3: 태스크별 이상(anomaly) 이벤트 조회 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/tasks/{task_id}/anomaly", summary="Task-level anomaly detection")
def get_task_anomaly(file_id: str, task_id: str, request: Request) -> Dict[str, Any]:
    """Query anomaly events related to a specific task."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    task = next((t for t in rf.tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # anomaly_data에서 해당 task_id 관련 이벤트 필터
    anomaly_data = rf.anomaly_data if hasattr(rf, "anomaly_data") else {}
    events = anomaly_data.get("events", []) if isinstance(anomaly_data, dict) else []
    task_events = [e for e in events if e.get("task_id") == task_id]

    # 태스크 지표와 이상 패턴 비교 분석
    analysis: Dict[str, Any] = {}
    if hasattr(rf, "accuracy_metrics"):
        avg_accuracy = rf.accuracy_metrics.get("avg_accuracy", 0)
        if avg_accuracy and task.accuracy_score < avg_accuracy * 0.7:
            analysis["accuracy_anomaly"] = {
                "task_score": round(task.accuracy_score, 4),
                "avg_score": round(float(avg_accuracy), 4),
                "deviation": round(float(avg_accuracy) - task.accuracy_score, 4),
            }
    if hasattr(rf, "latency_metrics"):
        p95 = rf.latency_metrics.get("p95", 0) or 0
        if p95 and task.execution_time > p95:
            analysis["latency_anomaly"] = {
                "task_latency": round(task.execution_time, 4),
                "p95_latency": round(float(p95), 4),
            }

    return {
        "file_id": file_id,
        "task_id": task_id,
        "anomaly_events": task_events,
        "anomaly_count": len(task_events),
        "analysis": analysis,
        "has_anomaly": bool(task_events or analysis),
    }


# ---------------------------------------------------------------------------
# C4: 두 평가 결과 파일 비교(diff) 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/comparison", summary="Detailed file comparison")
def get_comparison(
    request: Request,
    file_id_a: str = Query(..., description="Baseline file ID for comparison"),
    file_id_b: str = Query(..., description="Target file ID for comparison"),
) -> Dict[str, Any]:
    """Return metric diff between two evaluation result files.

    Compares two versions of the same agent or results from two different time points.
    """
    rs = _rs(request)
    rf_a = rs.by_id(file_id_a)
    rf_b = rs.by_id(file_id_b)
    if rf_a is None:
        raise HTTPException(status_code=404, detail=f"File A not found: {file_id_a}")
    if rf_b is None:
        raise HTTPException(status_code=404, detail=f"File B not found: {file_id_b}")

    def _safe_round(v, n=4):
        try:
            return round(float(v), n)
        except Exception:
            return None

    def _diff(a_val, b_val):
        if a_val is None or b_val is None:
            return None
        try:
            return round(float(b_val) - float(a_val), 4)
        except Exception:
            return None

    metrics_a = {
        "tcr": _safe_round(rf_a.tcr),
        "accuracy": _safe_round(rf_a.accuracy),
        "avg_latency": _safe_round(rf_a.avg_latency, 3),
        "total_cost": _safe_round(rf_a.total_cost, 6),
        "total_tasks": rf_a.total_tasks,
    }
    metrics_b = {
        "tcr": _safe_round(rf_b.tcr),
        "accuracy": _safe_round(rf_b.accuracy),
        "avg_latency": _safe_round(rf_b.avg_latency, 3),
        "total_cost": _safe_round(rf_b.total_cost, 6),
        "total_tasks": rf_b.total_tasks,
    }

    diff = {k: _diff(metrics_a.get(k), metrics_b.get(k)) for k in metrics_a}

    # 공통 task_id가 있으면 per-task diff
    task_ids_a = {t.task_id for t in rf_a.tasks}
    task_ids_b = {t.task_id for t in rf_b.tasks}
    common_ids = task_ids_a & task_ids_b

    per_task_diff: List[Dict[str, Any]] = []
    if common_ids:
        tasks_a = {t.task_id: t for t in rf_a.tasks}
        tasks_b = {t.task_id: t for t in rf_b.tasks}
        for tid in sorted(common_ids)[:50]:  # max 50
            ta, tb = tasks_a[tid], tasks_b[tid]
            per_task_diff.append({
                "task_id": tid,
                "accuracy_diff": _diff(ta.accuracy_score, tb.accuracy_score),
                "latency_diff": _diff(ta.execution_time, tb.execution_time),
                "success_changed": ta.success != tb.success,
            })

    return {
        "file_id_a": file_id_a,
        "file_id_b": file_id_b,
        "name_a": rf_a.name,
        "name_b": rf_b.name,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "diff": diff,
        "common_task_count": len(common_ids),
        "per_task_diff": per_task_diff,
        "regression_flags": {
            "accuracy_dropped": (diff.get("accuracy") or 0) < -0.05,
            "latency_increased": (diff.get("avg_latency") or 0) > 0.5,
            "tcr_dropped": (diff.get("tcr") or 0) < -5.0,
        },
    }


# ---------------------------------------------------------------------------
# L: P50/P75/P95/P99 레이턴시 퍼센타일 엔드포인트
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: List[float], p: float) -> Optional[float]:
    """Return the p-th percentile from a sorted list (0 < p <= 100)."""
    if not sorted_vals:
        return None
    try:
        import numpy as _np
        return round(float(_np.percentile(sorted_vals, p)), 4)
    except ImportError:
        n = len(sorted_vals)
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 4)


@router.get("/results/{file_id}/latency-percentiles", summary="Latency percentiles")
def get_latency_percentiles(file_id: str, request: Request) -> Dict[str, Any]:
    """P50/P75/P95/P99 latency percentiles and per-task-type analysis (L).

    Returns:
        file_id, count, p50, p75, p95, p99, min, max, mean, by_task_type
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    latencies = sorted(t.execution_time for t in rf.tasks)
    count = len(latencies)

    if count == 0:
        return {
            "file_id": file_id,
            "count": 0,
            "p50": None, "p75": None, "p95": None, "p99": None,
            "min": None, "max": None, "mean": None,
            "by_task_type": {},
        }

    mean_val = round(sum(latencies) / count, 4)

    # by_task_type 분석
    by_type: Dict[str, List[float]] = {}
    for t in rf.tasks:
        tt = str(getattr(t, "task_type", "unknown"))
        by_type.setdefault(tt, []).append(t.execution_time)

    by_task_type: Dict[str, Any] = {}
    for tt, vals in by_type.items():
        sv = sorted(vals)
        by_task_type[tt] = {
            "p50": _percentile(sv, 50),
            "p95": _percentile(sv, 95),
            "count": len(sv),
        }

    return {
        "file_id": file_id,
        "count": count,
        "p50": _percentile(latencies, 50),
        "p75": _percentile(latencies, 75),
        "p95": _percentile(latencies, 95),
        "p99": _percentile(latencies, 99),
        "min": round(latencies[0], 4),
        "max": round(latencies[-1], 4),
        "mean": mean_val,
        "by_task_type": by_task_type,
    }


# ---------------------------------------------------------------------------
# M: 토큰 분석 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/results/{file_id}/token-analytics", summary="Token usage analysis")
def get_token_analytics(file_id: str, request: Request) -> Dict[str, Any]:
    """Task token usage analysis — aggregate by task_type / framework (M).

    If tokens_used is an int it is treated as total; if dict, input/output/total keys are extracted.

    Returns:
        total_tokens, avg_tokens_per_task, by_task_type, by_framework
    """
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    def _extract_tokens(tok) -> Dict[str, int]:
        if isinstance(tok, int):
            return {"total": tok, "input": 0, "output": 0}
        if isinstance(tok, dict):
            total = tok.get("total", tok.get("input", 0) + tok.get("output", 0))
            return {
                "total": int(total or 0),
                "input": int(tok.get("input", 0) or 0),
                "output": int(tok.get("output", 0) or 0),
            }
        return {"total": 0, "input": 0, "output": 0}

    total_tokens = 0
    by_type: Dict[str, Dict[str, Any]] = {}
    by_fw: Dict[str, Dict[str, Any]] = {}

    for t in rf.tasks:
        tok = _extract_tokens(getattr(t, "tokens_used", None))
        total_tokens += tok["total"]

        tt = str(getattr(t, "task_type", "unknown"))
        if tt not in by_type:
            by_type[tt] = {"_total": [], "_input": [], "_output": []}
        by_type[tt]["_total"].append(tok["total"])
        by_type[tt]["_input"].append(tok["input"])
        by_type[tt]["_output"].append(tok["output"])

        fw = str(getattr(t, "framework", None) or "native")
        if fw not in by_fw:
            by_fw[fw] = {"_total": []}
        by_fw[fw]["_total"].append(tok["total"])

    count = len(rf.tasks)
    avg_total = round(total_tokens / count, 2) if count else 0.0

    by_task_type: Dict[str, Any] = {}
    for tt, d in by_type.items():
        n = len(d["_total"])
        by_task_type[tt] = {
            "avg_total": round(sum(d["_total"]) / n, 2) if n else 0.0,
            "avg_input": round(sum(d["_input"]) / n, 2) if n else 0.0,
            "avg_output": round(sum(d["_output"]) / n, 2) if n else 0.0,
            "count": n,
        }

    by_framework: Dict[str, Any] = {}
    for fw, d in by_fw.items():
        n = len(d["_total"])
        by_framework[fw] = {
            "avg_total": round(sum(d["_total"]) / n, 2) if n else 0.0,
            "count": n,
        }

    return {
        "file_id": file_id,
        "total_tokens": total_tokens,
        "avg_tokens_per_task": avg_total,
        "by_task_type": by_task_type,
        "by_framework": by_framework,
    }


@router.get("/security/events", summary="Security events list")
def get_security_events(
    request: Request,
    file_id: Optional[str] = Query(default=None, description="Filter by specific result file ID"),
    category: Optional[str] = Query(default=None, description="input_sanitization|output_leakage|tool_authorization|privilege_escalation|chain_attack"),
    threats_only: bool = Query(default=False, description="Return only items with threats detected"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    """Return detailed list of security events.

    Retrieves data recorded with ``enable_security_metrics=True`` or ``security_mode=True``,
    organized by category.

    Args:
        file_id: Query a specific result file only (omit for all-file aggregate).
        category: Security category to query. Omit to include all categories.
        threats_only: When True, return only events with threats detected.
        skip / limit: pagination.

    Returns:
        summary (per-category aggregate), events (event list), total.
    """
    rs = _rs(request)
    files = [rs.by_id(file_id)] if file_id else getattr(rs, "files", [])
    files = [f for f in files if f is not None]

    if not files:
        raise HTTPException(status_code=404, detail="No result files found")

    # 카테고리별 집계 및 이벤트 목록 수집
    summary: Dict[str, Any] = {
        "input_sanitization": {"total": 0, "threats": 0, "threat_rate": 0.0, "by_type": {}},
        "output_leakage":     {"total": 0, "leakages": 0, "leakage_rate": 0.0, "by_type": {}},
        "tool_authorization": {"total_calls": 0, "violations": 0, "violation_rate": 0.0},
        "privilege_escalation": {"total": 0, "escalations": 0},
        "chain_attack":       {"total": 0, "attacks": 0},
    }
    events: List[Dict[str, Any]] = []

    for rf in files:
        fid = rf.file_id

        # --- input_sanitization ---
        if not category or category == "input_sanitization":
            sec = rf.security_l1.input_security
            summary["input_sanitization"]["total"] += int(sec.get("total_inputs_evaluated", 0) or 0)
            summary["input_sanitization"]["threats"] += int(sec.get("inputs_with_threats", 0) or 0)
            for attack_type in ("sql_injection", "command_injection", "path_traversal", "xss", "prompt_injection"):
                key = f"{attack_type}_attempts"
                cnt = int(sec.get(key, 0) or 0)
                bt = summary["input_sanitization"]["by_type"]
                bt[attack_type] = bt.get(attack_type, 0) + cnt
            for ev in rf.security_l1.input_evals:
                if threats_only and not ev.get("sanitization_needed"):
                    continue
                events.append({
                    "file_id": fid,
                    "category": "input_sanitization",
                    "has_threat": bool(ev.get("sanitization_needed")),
                    "sql_injection": bool(ev.get("has_sql_injection")),
                    "command_injection": bool(ev.get("has_command_injection")),
                    "path_traversal": bool(ev.get("has_path_traversal")),
                    "xss": bool(ev.get("has_xss")),
                    "prompt_injection": bool(ev.get("has_prompt_injection")),
                    "task_id": ev.get("task_id"),
                    "input_preview": str(ev.get("input", ""))[:200],
                })

        # --- output_leakage ---
        if not category or category == "output_leakage":
            sec = rf.security_l1.output_leakage
            summary["output_leakage"]["total"] += int(sec.get("total_outputs_evaluated", 0) or 0)
            summary["output_leakage"]["leakages"] += int(sec.get("outputs_with_leakage", 0) or 0)
            for leak_type in ("api_key", "password", "credit_card", "email", "ssn", "phone", "private_ip", "file_path"):
                key = f"{leak_type}_leaks"
                cnt = int(sec.get(key, 0) or 0)
                bt = summary["output_leakage"]["by_type"]
                bt[leak_type] = bt.get(leak_type, 0) + cnt
            for ev in rf.security_l1.output_detections:
                if threats_only and ev.get("leakage_count", 0) == 0:
                    continue
                events.append({
                    "file_id": fid,
                    "category": "output_leakage",
                    "leakage_count": int(ev.get("leakage_count", 0) or 0),
                    "severity": ev.get("severity", "none"),
                    "contains_api_key": bool(ev.get("contains_api_key")),
                    "contains_password": bool(ev.get("contains_password")),
                    "contains_credit_card": bool(ev.get("contains_credit_card")),
                    "contains_email": bool(ev.get("contains_email")),
                    "task_id": ev.get("task_id"),
                    "output_preview": str(ev.get("output", ""))[:200],
                })

        # --- tool_authorization ---
        if not category or category == "tool_authorization":
            sec = rf.security_l1.authorization
            summary["tool_authorization"]["total_calls"] += int(sec.get("total_tool_calls", 0) or 0)
            summary["tool_authorization"]["violations"] += int(sec.get("violations", 0) or sec.get("unauthorized_calls", 0) or 0)
            for ev in rf.security_l1.tool_calls:
                is_auth = ev.get("is_authorized", True)
                if threats_only and is_auth:
                    continue
                events.append({
                    "file_id": fid,
                    "category": "tool_authorization",
                    "tool_name": ev.get("tool_name", ""),
                    "is_authorized": bool(is_auth),
                    "is_restricted": bool(ev.get("is_restricted")),
                    "has_dangerous_params": bool(ev.get("has_dangerous_params")),
                    "task_id": ev.get("task_id"),
                })

        # --- privilege_escalation ---
        if not category or category == "privilege_escalation":
            summary["privilege_escalation"]["total"] += len(rf.security_l2.escalation_events)
            escalations = [e for e in rf.security_l2.escalation_events if e.get("escalation_detected")]
            summary["privilege_escalation"]["escalations"] += len(escalations)
            for ev in rf.security_l2.escalation_events:
                if threats_only and not ev.get("escalation_detected"):
                    continue
                events.append({
                    "file_id": fid,
                    "category": "privilege_escalation",
                    "escalation_detected": bool(ev.get("escalation_detected")),
                    "privilege_level": ev.get("privilege_level", ""),
                    "task_id": ev.get("task_id"),
                })

        # --- chain_attack ---
        if not category or category == "chain_attack":
            summary["chain_attack"]["total"] += len(rf.security_l2.attack_detections)
            attacks = [e for e in rf.security_l2.attack_detections if e.get("attack_detected")]
            summary["chain_attack"]["attacks"] += len(attacks)
            for ev in rf.security_l2.attack_detections:
                if threats_only and not ev.get("attack_detected"):
                    continue
                events.append({
                    "file_id": fid,
                    "category": "chain_attack",
                    "attack_detected": bool(ev.get("attack_detected")),
                    "attack_type": ev.get("attack_type", ""),
                    "task_id": ev.get("task_id"),
                })

    # 비율 계산
    _si = summary["input_sanitization"]
    if _si["total"] > 0:
        _si["threat_rate"] = round(_si["threats"] / _si["total"] * 100, 2)
    _ol = summary["output_leakage"]
    if _ol["total"] > 0:
        _ol["leakage_rate"] = round(_ol["leakages"] / _ol["total"] * 100, 2)
    _ta = summary["tool_authorization"]
    if _ta["total_calls"] > 0:
        _ta["violation_rate"] = round(_ta["violations"] / _ta["total_calls"] * 100, 2)

    total = len(events)
    paged = events[skip: skip + limit]
    return {
        "summary": summary,
        "events": paged,
        "total": total,
        "skip": skip,
        "limit": limit,
        "file_ids": [f.file_id for f in files],
    }
