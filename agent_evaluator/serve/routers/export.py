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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from typing import Optional

router = APIRouter(prefix="/api/export", tags=["export"])


def _result_set(request: Request):
    return request.app.state.result_set


@router.get("/json/{file_id}", summary="JSON 내보내기")
def export_json(file_id: str, request: Request):
    """평가 결과 파일을 원본 JSON 형식으로 다운로드한다.

    추가 의존성 없음. ``Content-Disposition: attachment`` 헤더를 포함하므로
    브라우저에서 파일명이 ``<file_id>.json``으로 자동 설정된다.

    Args:
        file_id: 결과 파일 ID (``/api/results`` 목록의 ``id`` 필드).
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


@router.get("/csv/{file_id}", summary="CSV 내보내기")
def export_csv(file_id: str, request: Request):
    """평가 결과의 태스크 목록을 CSV 형식으로 다운로드한다.

    각 행은 태스크 1개를 나타내며, task_id · task_type · success · accuracy_score ·
    execution_time · tokens · framework · harness Gate 점수(16컬럼) 등을 포함한다.
    추가 의존성 없음.

    Args:
        file_id: 결과 파일 ID (``/api/results`` 목록의 ``id`` 필드).
    """
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    buf = io.StringIO()
    # Detect optional columns from data
    has_framework   = any(getattr(t, "framework", None) for t in rf.tasks)
    has_agentic     = rf.has_agentic
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


@router.get("/parquet/{file_id}", summary="Parquet 내보내기")
def export_parquet(file_id: str, request: Request):
    """태스크 결과를 Apache Parquet 형식으로 다운로드한다.

    ``pyarrow`` 설치가 필요하다. 미설치 시 HTTP 409를 반환한다.

    설치: ``pip install "agent-evaluator[export]"`` 또는 ``pip install pyarrow``

    Args:
        file_id: 결과 파일 ID (``/api/results`` 목록의 ``id`` 필드).
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise HTTPException(
            status_code=409,
            detail="pyarrow 미설치: pip install pyarrow",
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


@router.get("/excel/{file_id}", summary="Excel 내보내기")
def export_excel(file_id: str, request: Request):
    """태스크 결과를 Excel (.xlsx) 형식으로 다운로드한다.

    ``openpyxl`` 설치가 필요하다. 미설치 시 HTTP 501을 반환한다.

    설치: ``pip install "agent-evaluator[export]"`` 또는 ``pip install openpyxl``

    Args:
        file_id: 결과 파일 ID (``/api/results`` 목록의 ``id`` 필드).
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="openpyxl 미설치: pip install openpyxl",
        )

    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    wb = openpyxl.Workbook()
    ws = wb.active
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


@router.get("/html/{file_id}", summary="HTML 리포트 내보내기")
def export_html(file_id: str, request: Request):
    """Harness Gate A–G 중심의 독립 HTML 리포트를 다운로드한다.

    단일 파일로 완결된 리포트이며 외부 CDN 의존성 없이 브라우저에서 직접 열 수 있다.
    추가 의존성 없음.

    Args:
        file_id: 결과 파일 ID (``/api/results`` 목록의 ``id`` 필드).
    """
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    from agent_evaluator.reporting.comprehensive_report import generate_html_from_result_file
    html = generate_html_from_result_file(rf)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{rf.name}_report.html"'},
    )
