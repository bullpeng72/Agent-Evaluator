"""
Export routes.

GET /api/export/json/{id}  — raw JSON download
GET /api/export/csv/{id}   — CSV of tasks
GET /api/export/html/{id}  — self-contained HTML report
"""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

router = APIRouter(prefix="/api/export", tags=["export"])


def _result_set(request: Request):
    return request.app.state.result_set


@router.get("/json/{file_id}", summary="JSON export")
def export_json(file_id: str, request: Request):
    """Download the evaluation result file in raw JSON format.

    No extra dependencies required. Includes a ``Content-Disposition: attachment`` header
    so the browser automatically saves the file as ``<file_id>.json``.

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
    """
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    content = json.dumps(rf.raw, ensure_ascii=False, indent=2)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.json"'},
    )


@router.get("/csv/{file_id}", summary="CSV export")
def export_csv(file_id: str, request: Request):
    """Download the task list from the evaluation result as CSV.

    Each row represents one task and includes task_id, task_type, success, accuracy_score,
    execution_time, tokens, framework, harness Gate scores (16 columns), and more.
    No extra dependencies required.

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
    """
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    buf = io.StringIO()
    # Detect optional columns from data
    has_adv         = rf.has_advanced or rf.has_rag

    # Collect per-task advanced metric keys (ragas_*, g_eval_score, etc.)
    adv_keys: list = []
    if has_adv:
        key_set: set = set()
        for t in rf.tasks:
            am = t.advanced_metrics or {}
            key_set.update(am.keys())
        adv_keys = sorted(key_set)

    fieldnames = [
        "task_id", "task_type", "success",
        "completion_score", "accuracy_score",
        "execution_time",
        "tokens_input", "tokens_output", "tokens_total",
        "tool_calls_count", "attempts", "errors",
        "timestamp", "framework",
    ] + adv_keys

    has_harness = getattr(rf, 'has_harness', bool(getattr(rf, 'harness_groups', None)))
    if has_harness:
        for gk in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
            fieldnames.append(f'gate_{gk}_score')
            fieldnames.append(f'gate_{gk}_status')
        fieldnames.append('harness_overall_score')
        fieldnames.append('harness_overall_status')

    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for t in rf.tasks:
        tu = t.tokens_used or {}
        tok_in  = tu.get("input", 0)
        tok_out = tu.get("output", 0)
        tok_tot = tu.get("total", tok_in + tok_out)
        row = {
            "task_id":          t.task_id,
            "task_type":        t.task_type,
            "success":          t.success,
            "completion_score": round(t.completion_score, 4),
            "accuracy_score":   round(t.accuracy_score, 4),
            "execution_time":   t.execution_time,
            "tokens_input":     tok_in,
            "tokens_output":    tok_out,
            "tokens_total":     tok_tot,
            "tool_calls_count": len(t.tool_calls) if t.tool_calls else 0,
            "attempts":         t.attempts,
            "errors":           "; ".join(str(e) for e in t.errors),
            "timestamp":        t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp),
            "framework":        getattr(t, "framework", "") or "",
        }
        # Per-task advanced metrics
        am = t.advanced_metrics or {}
        for k in adv_keys:
            v = am.get(k)
            row[k] = round(float(v), 4) if isinstance(v, (int, float)) else (v or "")
        if has_harness:
            hg = getattr(rf, 'harness_groups', {}) or {}
            for gk in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
                g = hg.get(gk) or {}
                score = g.get('score')
                row[f'gate_{gk}_score'] = round(float(score), 4) if score is not None else ''
                row[f'gate_{gk}_status'] = (g.get('gate') or '').upper()
            overall = hg.get('overall') or {}
            ov_score = overall.get('score')
            row['harness_overall_score'] = round(float(ov_score), 4) if ov_score is not None else ''
            row['harness_overall_status'] = (overall.get('gate') or '').upper()
        writer.writerow(row)

    content = buf.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.csv"'},
    )


@router.get("/parquet/{file_id}", summary="Parquet export")
def export_parquet(file_id: str, request: Request):
    """Download task results in Apache Parquet format.

    Requires ``pyarrow``. Returns HTTP 409 if not installed.

    Install: ``pip install "agent-evaluator[export]"`` or ``pip install pyarrow``

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise HTTPException(
            status_code=409,
            detail="pyarrow not installed: pip install pyarrow",
        )
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    rows = []
    for t in rf.tasks:
        ts = t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp)
        tok = t.tokens_used or {}
        rows.append({
            "task_id":        t.task_id,
            "task_type":      str(t.task_type),
            "success":        t.success,
            "completion_score": float(t.completion_score),
            "accuracy_score": float(t.accuracy_score),
            "execution_time": float(t.execution_time),
            "attempts":       int(t.attempts),
            "framework":      str(getattr(t, "framework", "") or ""),
            "tokens_input":   int(tok.get("input", 0)),
            "tokens_output":  int(tok.get("output", 0)),
            "tokens_total":   int(tok.get("total", 0)),
            "has_error":      bool(t.errors),
            "timestamp":      ts,
        })

    if not rows:
        raise HTTPException(status_code=404, detail="No tasks found")

    table = pa.Table.from_pylist(rows)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.parquet"'},
    )


@router.get("/excel/{file_id}", summary="Excel export")
def export_excel(file_id: str, request: Request):
    """Download task results in Excel (.xlsx) format.

    Requires ``openpyxl``. Returns HTTP 501 if not installed.

    Install: ``pip install "agent-evaluator[export]"`` or ``pip install openpyxl``

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
    """
    try:
        import openpyxl  # pyright: ignore[reportMissingModuleSource]
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="openpyxl not installed: pip install openpyxl",
        )

    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None  # freshly created Workbook() always has an active sheet
    ws.title = "Tasks"

    # Detect advanced metric keys
    adv_keys: list = []
    if rf.has_advanced or rf.has_rag:
        key_set: set = set()
        for t in rf.tasks:
            am = t.advanced_metrics or {}
            key_set.update(am.keys())
        adv_keys = sorted(key_set)

    headers = [
        "task_id", "task_type", "success",
        "completion_score", "accuracy_score",
        "execution_time",
        "tokens_input", "tokens_output", "tokens_total",
        "tool_calls_count", "attempts", "errors",
        "timestamp", "framework",
    ] + adv_keys

    ws.append(headers)

    for t in rf.tasks:
        tu = t.tokens_used or {}
        tok_in = tu.get("input", 0)
        tok_out = tu.get("output", 0)
        tok_tot = tu.get("total", tok_in + tok_out)
        ts_str = t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp)
        row = [
            t.task_id,
            str(t.task_type),
            t.success,
            round(t.completion_score, 4),
            round(t.accuracy_score, 4),
            t.execution_time,
            tok_in,
            tok_out,
            tok_tot,
            len(t.tool_calls) if t.tool_calls else 0,
            t.attempts,
            "; ".join(str(e) for e in t.errors),
            ts_str,
            getattr(t, "framework", "") or "",
        ]
        # Per-task advanced metrics
        am = t.advanced_metrics or {}
        for k in adv_keys:
            v = am.get(k)
            row.append(round(float(v), 4) if isinstance(v, (int, float)) else (v or ""))
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.xlsx"'},
    )


@router.get("/html/compare", summary="Comparison HTML report export")
def export_html_compare(
    request: Request,
    ids: Optional[str] = Query(  # noqa: UP045
        default=None, description="Comma-separated file_id list (e.g. id1,id2)",
    ),
    group_by: Optional[str] = Query(  # noqa: UP045
        default=None, description="Group by prompt_version|agent_version instead of ids",
    ),
    pairwise: bool = Query(
        default=False,
        description="Include pairwise LLM Judge win-rate (requires exactly 2 resolved files)",
    ),
):
    """Download a self-contained HTML report for a multi-file comparison
    (``/api/compare`` — SPEC-025 REQ-2/5).

    Registered before ``/html/{file_id}`` so the literal ``compare`` path segment
    isn't swallowed by that route's ``{file_id}`` parameter.

    Args:
        ids: Comma-separated file_id list (mutually exclusive with ``group_by``).
        group_by: ``prompt_version`` | ``agent_version`` — auto-picks the latest
            file per distinct tag value instead of an explicit ``ids`` list.
        pairwise: If true, also runs a pairwise LLM Judge comparison per common
            task (real judge API calls — may be slow/costly for large task counts).
    """
    from .data import compare_results

    compare_result = compare_results(
        request, ids=ids, detailed=True, group_by=group_by, pairwise=pairwise,
    )

    from agent_evaluator.reporting.comprehensive_report import generate_comparison_html_report
    html = generate_comparison_html_report(compare_result)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": 'attachment; filename="comparison_report.html"'},
    )


@router.get("/html/{file_id}", summary="HTML report export")
def export_html(
    file_id: str,
    request: Request,
    baseline_id: Optional[str] = Query(  # noqa: UP045
        None, description="Baseline result file id for regression-based Gate RCA diagnosis",
    ),
):
    """Download a self-contained Harness Gate A–G HTML report.

    A single-file report that can be opened directly in the browser without any external CDN dependency.
    No extra dependencies required.

    Args:
        file_id: Result file ID (from the ``id`` field in ``/api/results``).
        baseline_id: (optional) Baseline result file id — same pairing as
            ``GET /api/diagnose/{file_id}?baseline_id=``. When given, the report's
            Gate RCA diagnosis section switches from absolute-threshold detection
            to regression-vs-baseline detection.
    """
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    baseline_raw = None
    if baseline_id:
        baseline_rf = rs.by_id(baseline_id)
        if baseline_rf is None:
            raise HTTPException(status_code=404, detail=f"Baseline file not found: {baseline_id}")
        baseline_raw = baseline_rf.raw

    from agent_evaluator.reporting.comprehensive_report import generate_html_from_result_file
    html = generate_html_from_result_file(rf, baseline=baseline_raw)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{rf.name}_report.html"'},
    )
