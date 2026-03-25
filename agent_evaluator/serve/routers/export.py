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

router = APIRouter(prefix="/api/export")


def _result_set(request: Request):
    return request.app.state.result_set


@router.get("/json/{file_id}")
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


@router.get("/csv/{file_id}")
def export_csv(file_id: str, request: Request):
    rs = _result_set(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")

    buf = io.StringIO()
    fieldnames = [
        "task_id", "task_type", "success", "completion_score",
        "accuracy_score", "execution_time", "tokens_total", "attempts", "errors",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for t in rf.tasks:
        writer.writerow({
            "task_id":          t.task_id,
            "task_type":        t.task_type,
            "success":          t.success,
            "completion_score": t.completion_score,
            "accuracy_score":   round(t.accuracy_score, 4),
            "execution_time":   t.execution_time,
            "tokens_total":     t.tokens_used.get("total",
                                    t.tokens_used.get("input", 0) + t.tokens_used.get("output", 0)),
            "attempts":         t.attempts,
            "errors":           "; ".join(str(e) for e in t.errors),
        })

    content = buf.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{rf.name}.csv"'},
    )


@router.get("/html/{file_id}", response_class=HTMLResponse)
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
        ok = "✅" if t.success else "❌"
        tasks_rows += (
            f"<tr><td>{t.task_id}</td><td>{t.task_type}</td><td>{ok}</td>"
            f"<td>{pct(t.completion_score * 100)}</td>"
            f"<td>{pct(t.accuracy_score * 100)}</td>"
            f"<td>{sec_(t.execution_time)}</td>"
            f"<td>{t.tokens_used.get('total', t.tokens_used.get('input', 0) + t.tokens_used.get('output', 0))}</td>"
            f"<td>{t.attempts}</td></tr>\n"
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
        security_section = f"""
<h2>🛡️ 보안 지표</h2>
<div class="kpis">
  <div class="kpi"><div class="kpi-lbl">입력 보안 (L1)</div><div class="kpi-val" style="color:{score_color(sl1.input_security)}">{sl1.input_security:.1f}%</div><div style="font-size:11px;color:#5a6080">{sl1.input_evals}건 평가</div></div>
  <div class="kpi"><div class="kpi-lbl">출력 유출 방지 (L1)</div><div class="kpi-val" style="color:{score_color(100-sl1.output_leakage)}">{sl1.output_leakage:.1f}%</div><div style="font-size:11px;color:#5a6080">{sl1.output_detections}건 탐지</div></div>
  <div class="kpi"><div class="kpi-lbl">도구 권한 준수 (L1)</div><div class="kpi-val" style="color:{score_color(sl1.authorization)}">{sl1.authorization:.1f}%</div></div>
  <div class="kpi"><div class="kpi-lbl">권한 상승 방어 (L2)</div><div class="kpi-val" style="color:{score_color(sl2.privilege_escalation)}">{sl2.privilege_escalation:.1f}%</div><div style="font-size:11px;color:#5a6080">{sl2.escalation_events}건 이벤트</div></div>
  <div class="kpi"><div class="kpi-lbl">공격 체인 탐지 (L2)</div><div class="kpi-val" style="color:{score_color(sl2.attack_detection)}">{sl2.attack_detection:.1f}%</div><div style="font-size:11px;color:#5a6080">{sl2.attack_detections}건 탐지</div></div>
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
  <div class="kpi"><div class="kpi-lbl">Hallucination</div><div class="kpi-val" style="color:{score_color(100 - float(hall.get('overall_rate') or 0) * 100)}">{pct(hall.get('overall_rate'))}</div></div>
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
{security_section}
{rag_section}
{advanced_section}

<h2>📋 태스크 목록</h2>
<table>
<thead><tr><th>Task ID</th><th>Type</th><th>✓</th><th>Completion</th><th>Accuracy</th><th>Latency</th><th>Tokens</th><th>Attempts</th></tr></thead>
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
