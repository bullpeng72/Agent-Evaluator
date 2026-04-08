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
        writer.writerow(row)

    content = buf.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.csv"'},
    )


@router.get("/parquet/{file_id}")
def export_parquet(file_id: str, request: Request):
    """TaskResult 리스트를 Apache Parquet 형식으로 다운로드.

    requires: ``pip install pyarrow`` (선택 의존성)
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


@router.get("/excel/{file_id}")
def export_excel(file_id: str, request: Request):
    """Excel (.xlsx) 형식으로 내보내기 (B10).

    openpyxl이 없으면 501 오류 반환.
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


@router.get("/html/{file_id}", response_class=HTMLResponse, summary="HTML 리포트 내보내기")
def export_html(file_id: str, request: Request):
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    tcr = rf.accuracy_metrics.get("tcr", {})
    acc = rf.accuracy_metrics.get("accuracy_scores", {})
    hall = rf.accuracy_metrics.get("hallucination", {})
    lat = rf.efficiency_metrics.get("latency", {})
    tok = rf.efficiency_metrics.get("tokens", {})

    def pct(v):
        return f"{float(v):.1f}%" if v is not None else "—"

    def sec_(v):
        return f"{float(v):.3f}s" if v is not None else "—"

    def cost(v):
        if v is None:
            return "—"
        v = float(v)
        if v == 0:
            return "$0"
        s = f"{v:.6f}" if v < 0.01 else f"{v:.4f}"
        return "$" + s.rstrip("0").rstrip(".")

    def score_color(v, hi=70, lo=50):
        """Return a hex color based on score 0-100."""
        if v is None:
            return "#9ca3af"
        if v >= hi:
            return "#10b981"
        if v >= lo:
            return "#f59e0b"
        return "#ef4444"

    tasks_rows = ""
    for t in rf.tasks:
        ok_color = "#10b981" if t.success else "#ef4444"
        ok_text  = "성공" if t.success else "실패"
        tu = t.tokens_used or {}
        tok_tot = tu.get("total", tu.get("input", 0) + tu.get("output", 0))
        fw = getattr(t, "framework", "") or "—"
        tc = len(t.tool_calls) if t.tool_calls else 0
        tasks_rows += (
            f"<tr>"
            f"<td>{t.task_id}</td>"
            f"<td>{t.task_type}</td>"
            f"<td style='color:{ok_color};font-weight:600'>{ok_text}</td>"
            f"<td>{pct(t.completion_score * 100)}</td>"
            f"<td>{pct(t.accuracy_score * 100)}</td>"
            f"<td>{sec_(t.execution_time)}</td>"
            f"<td style='text-align:right'>{tok_tot:,}</td>"
            f"<td style='text-align:right'>{tc}</td>"
            f"<td style='text-align:right'>{t.attempts}</td>"
            f"<td>{fw}</td>"
            f"</tr>\n"
        )

    # Quality section
    quality_section = ""
    if rf.has_quality_detail:
        qd = rf.quality_detail
        dims = ["relevance", "completeness", "clarity", "accuracy", "usefulness"]
        dim_labels = {"relevance": "관련성", "completeness": "완전성", "clarity": "명확성",
                      "accuracy": "정확성", "usefulness": "유용성"}
        dim_rows = ""
        for d in dims:
            v = qd.dimension_summary.get(d)
            if v is not None:
                bar_w = int(float(v) / 5 * 100)
                dim_rows += (f"<tr><td>{dim_labels.get(d, d)}</td>"
                             f"<td style='color:{score_color(float(v)/5*100)}'>{float(v):.2f}/5</td>"
                             f"<td><div style='height:8px;background:#e5e7eb;border-radius:4px'>"
                             f"<div style='height:8px;width:{bar_w}%;background:{score_color(float(v)/5*100)};border-radius:4px'></div></div></td></tr>\n")
        hall_rate = rf.accuracy_metrics.get("hallucination", {}).get("overall_rate", 0) or 0
        quality_section = f"""
<h2>🧠 응답 품질</h2>
<p style="font-size:12px;color:#5a6080">평균 품질 점수: <b style="color:{score_color(qd.avg_score*20)}">{qd.avg_score:.2f}/5</b> &nbsp;|&nbsp; 환각률: <b style="color:{score_color(100-hall_rate*100)}">{hall_rate*100:.1f}%</b></p>
<table>
<thead><tr><th>차원</th><th>평균 점수</th><th>분포</th></tr></thead>
<tbody>{dim_rows}</tbody>
</table>"""

    # Security section
    security_section = ""
    if rf.has_security:
        sl1 = rf.security_l1
        sl2 = rf.security_l2
        # Extract numeric values from Dict fields
        inp  = sl1.input_security or {}
        out  = sl1.output_leakage or {}
        auth = sl1.authorization  or {}
        priv = sl2.privilege_escalation or {}
        atk  = sl2.attack_detection     or {}

        inp_evals    = inp.get("total_inputs_evaluated", len(sl1.input_evals))
        inp_threat   = inp.get("threat_rate", 0)             # 0-100 (위협 비율)
        inp_safe     = 100 - float(inp_threat)               # 안전 비율

        out_evals    = out.get("total_outputs_evaluated", len(sl1.output_detections))
        out_leak     = float(out.get("leakage_rate", 0))     # 0-100 (유출 비율)
        out_safe     = 100 - out_leak                        # 무유출 비율

        auth_total   = auth.get("total_tool_calls", 0)
        auth_comply  = float(auth.get("compliance_rate", 100 if not auth_total else 0))

        priv_total   = priv.get("total_evaluations", len(sl2.escalation_events))
        priv_rate    = float(priv.get("escalation_rate", 0)) # 0-100
        priv_safe    = 100 - priv_rate

        atk_total    = atk.get("total_chains_analyzed", len(sl2.attack_detections))
        atk_rate     = float(atk.get("detection_rate", 0))  # 탐지율 (높을수록 위험)
        atk_safe     = 100 - atk_rate

        sec_rows = f"""
  <div class="kpi"><div class="kpi-lbl">입력 보안 (L1)</div><div class="kpi-val" style="color:{score_color(inp_safe)}">{inp_safe:.1f}%</div><div style="font-size:11px;color:#5a6080">{inp_evals}건 평가 · 위협 {float(inp_threat):.1f}%</div></div>
  <div class="kpi"><div class="kpi-lbl">출력 유출 방지 (L1)</div><div class="kpi-val" style="color:{score_color(out_safe)}">{out_safe:.1f}%</div><div style="font-size:11px;color:#5a6080">{out_evals}건 평가 · 유출 {out_leak:.1f}%</div></div>
  <div class="kpi"><div class="kpi-lbl">도구 권한 준수 (L1)</div><div class="kpi-val" style="color:{score_color(auth_comply)}">{auth_comply:.1f}%</div><div style="font-size:11px;color:#5a6080">{auth_total}건 호출</div></div>
  <div class="kpi"><div class="kpi-lbl">권한 상승 방어 (L2)</div><div class="kpi-val" style="color:{score_color(priv_safe)}">{priv_safe:.1f}%</div><div style="font-size:11px;color:#5a6080">{priv_total}건 평가 · 탐지 {priv_rate:.1f}%</div></div>
  <div class="kpi"><div class="kpi-lbl">공격 체인 탐지 (L2)</div><div class="kpi-val" style="color:{score_color(atk_safe)}">{atk_safe:.1f}%</div><div style="font-size:11px;color:#5a6080">{atk_total}건 분석 · 의심 {atk_rate:.1f}%</div></div>"""
        security_section = f"""
<h2>🛡️ 보안 지표</h2>
<div class="kpis">{sec_rows}
</div>"""

    # RAG section
    rag_section = ""
    if rf.has_rag:
        rm = rf.rag_metrics
        rag_keys = ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]
        rag_labels = {"faithfulness": "Faithfulness", "answer_relevancy": "Ans. Relevancy",
                      "context_recall": "Ctx. Recall", "context_precision": "Ctx. Precision"}
        rag_rows = ""
        for k in rag_keys:
            vals = rm.get(k, [])
            if vals:
                avg_v = sum(vals) / len(vals)
                mn = min(vals)
                mx = max(vals)
                rag_rows += (f"<tr><td>{rag_labels[k]}</td>"
                             f"<td style='color:{score_color(avg_v*100)}'>{avg_v:.3f}</td>"
                             f"<td>{mn:.2f}</td><td>{mx:.2f}</td><td>{len(vals)}건</td></tr>\n")
        rag_section = f"""
<h2>📚 RAG 지표 (Ragas)</h2>
<table>
<thead><tr><th>지표</th><th>평균</th><th>최솟값</th><th>최댓값</th><th>건수</th></tr></thead>
<tbody>{rag_rows}</tbody>
</table>"""

    # Agentic section
    agentic_section = ""
    if rf.has_agentic:
        ag = rf.agentic
        tool_eff = ag.get("tool_efficiency") if isinstance(ag, dict) else getattr(ag, "tool_efficiency", None)
        tool_sel = ag.get("tool_selection_summary") if isinstance(ag, dict) else getattr(ag, "tool_selection_summary", None)
        retry    = ag.get("retry_summary") if isinstance(ag, dict) else getattr(ag, "retry_summary", None)
        coord    = ag.get("coordination_summary") if isinstance(ag, dict) else getattr(ag, "coordination_summary", None)
        workflow = ag.get("workflow_summary") if isinstance(ag, dict) else getattr(ag, "workflow_summary", None)
        def _ag_row(label, d, key, fmt=lambda v: f"{float(v):.1f}%"):
            if not d or not isinstance(d, dict):
                return ""
            v = d.get(key)
            return f"<tr><td>{label}</td><td>{fmt(v) if v is not None else '—'}</td></tr>\n"
        ag_rows = ""
        if isinstance(tool_eff, dict):
            ag_rows += _ag_row("평균 도구 효율성", tool_eff, "avg_efficiency")
            ag_rows += _ag_row("도구 중복 호출률", tool_eff, "redundancy_rate")
            ag_rows += _ag_row("도구 실패율", tool_eff, "failure_rate")
        if isinstance(tool_sel, dict):
            f1 = tool_sel.get("avg_f1")
            ag_rows += f"<tr><td>Tool Selection F1</td><td>{'—' if f1 is None else f'{float(f1):.3f}'}</td></tr>\n"
        if isinstance(retry, dict):
            ag_rows += _ag_row("전체 재시도율", retry, "overall_retry_rate")
            ag_rows += _ag_row("수정 성공률", retry, "correction_success_rate")
        if isinstance(coord, dict):
            ag_rows += _ag_row("협업 점수", coord, "avg_coordination_score")
        if isinstance(workflow, dict):
            ag_rows += _ag_row("워크플로우 성공률", workflow, "success_rate")
            ag_rows += _ag_row("단계 성공률", workflow, "step_success_rate")
        if ag_rows:
            agentic_section = f"""
<h2>🤖 에이전틱 지표</h2>
<table>
<thead><tr><th>지표</th><th>값</th></tr></thead>
<tbody>{ag_rows}</tbody>
</table>"""

    # LLM Judge section
    llm_judge_section = ""
    if getattr(rf, "llm_judge", None) and rf.llm_judge.judged_count > 0:
        lj = rf.llm_judge
        llm_judge_section = f"""
<h2>⚖️ LLM Judge</h2>
<div class="kpis">
  <div class="kpi"><div class="kpi-lbl">평가 건수</div><div class="kpi-val">{lj.judged_count}</div></div>
  <div class="kpi"><div class="kpi-lbl">종합 점수</div><div class="kpi-val" style="color:{score_color(float(lj.avg_overall or 0)*10)}">{float(lj.avg_overall or 0):.2f}/10</div></div>
  <div class="kpi"><div class="kpi-lbl">완전성</div><div class="kpi-val">{float(lj.avg_completeness or 0):.2f}/10</div></div>
  <div class="kpi"><div class="kpi-lbl">관련성</div><div class="kpi-val">{float(lj.avg_relevance or 0):.2f}/10</div></div>
  <div class="kpi"><div class="kpi-lbl">사실 일관성</div><div class="kpi-val">{float(lj.avg_factual_consistency or 0):.2f}/10</div></div>
  <div class="kpi"><div class="kpi-lbl">평가 모델</div><div class="kpi-val" style="font-size:11px">{lj.model or '—'}</div></div>
  <div class="kpi"><div class="kpi-lbl">평가 비용</div><div class="kpi-val" style="font-size:16px">{cost(lj.total_cost_usd)}</div></div>
</div>"""

    # Advanced / DeepEval section
    advanced_section = ""
    if rf.has_advanced:
        summary = rf.advanced.summary
        de_keys = ["g_eval_score", "hallucination_score", "toxicity_score", "bias_score", "answer_relevancy_score"]
        de_labels = {"g_eval_score": "G-Eval", "hallucination_score": "Hallucination",
                     "toxicity_score": "Toxicity", "bias_score": "Bias",
                     "answer_relevancy_score": "Ans. Relevancy"}
        de_rows = ""
        for k in de_keys:
            v = summary.get(k)
            if v:
                mean_v = v.get("mean", 0) or 0
                de_rows += (f"<tr><td>{de_labels.get(k, k)}</td>"
                            f"<td style='color:{score_color(mean_v*100)}'>{mean_v:.3f}</td>"
                            f"<td>{v.get('min', 0):.2f}</td><td>{v.get('max', 0):.2f}</td></tr>\n")
        if de_rows:
            advanced_section = f"""
<h2>🔬 외부 평가 (DeepEval)</h2>
<table>
<thead><tr><th>지표</th><th>평균</th><th>최솟값</th><th>최댓값</th></tr></thead>
<tbody>{de_rows}</tbody>
</table>"""

    data_json = json.dumps({
        "tcr": tcr.get("tcr", 0),
        "acc": acc.get("overall_accuracy", 0),
        "full": tcr.get("full_success", 0),
        "part": tcr.get("partial_success", 0),
        "fail": tcr.get("failures", 0),
    })

    # Capability badges
    badges = []
    badges.append('<span style="background:#6366f133;color:#818cf8;padding:2px 8px;border-radius:99px;font-size:11px">기본</span>')
    if rf.has_quality_detail:
        badges.append('<span style="background:#8b5cf633;color:#a78bfa;padding:2px 8px;border-radius:99px;font-size:11px">품질</span>')
    if rf.has_agentic:
        badges.append('<span style="background:#06b6d433;color:#22d3ee;padding:2px 8px;border-radius:99px;font-size:11px">에이전틱</span>')
    if rf.has_security:
        badges.append('<span style="background:#ef444433;color:#f87171;padding:2px 8px;border-radius:99px;font-size:11px">보안</span>')
    if rf.has_rag:
        badges.append('<span style="background:#10b98133;color:#34d399;padding:2px 8px;border-radius:99px;font-size:11px">RAG</span>')
    if rf.has_advanced:
        badges.append('<span style="background:#f59e0b33;color:#fbbf24;padding:2px 8px;border-radius:99px;font-size:11px">외부평가</span>')
    badges_html = " ".join(badges)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Agent Evaluator Report — {rf.name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f5f6fa;color:#1e2030;margin:0;padding:20px;font-size:14px}}
h1{{font-size:20px;margin-bottom:4px}} h2{{font-size:14px;font-weight:600;margin:20px 0 8px;color:#1e2030;border-bottom:1px solid #dde0ec;padding-bottom:4px}}
.meta{{font-size:12px;color:#5a6080;margin-bottom:8px}}
.badges{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:16px}}
.kpi{{background:#ffffff;border:1px solid #dde0ec;border-radius:10px;padding:12px}}
.kpi-lbl{{font-size:10px;color:#5a6080;text-transform:uppercase}}
.kpi-val{{font-size:22px;font-weight:800;margin:3px 0;color:#1e2030}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:16px}}
th{{background:#eef0f8;padding:7px 10px;text-align:left;border-bottom:1px solid #dde0ec;color:#5a6080}}
td{{padding:6px 10px;border-bottom:1px solid #eef0f8;color:#1e2030}}
tr:hover td{{background:#eef0f8}}
.chart-wrap{{background:#ffffff;border:1px solid #dde0ec;border-radius:10px;padding:12px;margin-bottom:16px;max-width:340px}}
canvas{{max-height:180px}}
.footer{{margin-top:24px;font-size:11px;color:#5a6080;border-top:1px solid #dde0ec;padding-top:10px}}
</style>
</head>
<body>
<h1>🤖 Agent Evaluator Report</h1>
<div class="meta">파일: <b>{rf.name}</b> &nbsp;|&nbsp; 타임스탬프: {rf.timestamp} &nbsp;|&nbsp; 총 Tasks: {rf.total_tasks}</div>
<div class="badges">{badges_html}</div>

<h2>📊 핵심 지표</h2>
<div class="kpis">
  <div class="kpi"><div class="kpi-lbl">TCR</div><div class="kpi-val" style="color:{score_color(float(tcr.get('tcr') or 0))}">{pct(tcr.get('tcr'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Accuracy</div><div class="kpi-val" style="color:{score_color(float(acc.get('overall_accuracy') or 0))}">{pct(acc.get('overall_accuracy'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Hallucination</div><div class="kpi-val" style="color:{score_color(100 - float(hall.get('overall_rate') or 0) * 100)}">{pct(float(hall.get('overall_rate') or 0) * 100)}</div></div>
  <div class="kpi"><div class="kpi-lbl">Avg Latency</div><div class="kpi-val">{sec_(lat.get('mean'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">P95 Latency</div><div class="kpi-val">{sec_(lat.get('p95'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Total Cost</div><div class="kpi-val">{cost(tok.get('total_cost'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Total Tokens</div><div class="kpi-val">{tok.get('total_tokens', 0):,}</div></div>
  <div class="kpi"><div class="kpi-lbl">Total Tasks</div><div class="kpi-val">{rf.total_tasks}</div></div>
</div>

<div class="chart-wrap">
  <div style="font-size:12px;color:#8890b0;margin-bottom:8px">성공/실패 분포</div>
  <canvas id="donut"></canvas>
</div>

{quality_section}
{agentic_section}
{security_section}
{llm_judge_section}
{rag_section}
{advanced_section}

<h2>📋 태스크 목록</h2>
<table>
<thead><tr><th>Task ID</th><th>유형</th><th>성공</th><th>완료율</th><th>정확도</th><th>지연(s)</th><th>토큰</th><th>도구호출</th><th>시도횟수</th><th>프레임워크</th></tr></thead>
<tbody>{tasks_rows}</tbody>
</table>

<div class="footer">Generated by Agent Evaluator &nbsp;|&nbsp; {rf.timestamp}</div>

<script>
const D = {data_json};
new Chart(document.getElementById('donut'), {{
  type: 'doughnut',
  data: {{
    labels: ['완전성공','부분성공','실패'],
    datasets: [{{ data:[D.full,D.part,D.fail], backgroundColor:['#4ade80','#facc15','#f87171'], borderWidth:0 }}]
  }},
  options: {{ cutout:'70%', plugins:{{ legend:{{ labels:{{ color:'#5a6080', font:{{size:11}} }} }} }} }}
}});
</script>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{rf.name}_report.html"'},
    )
