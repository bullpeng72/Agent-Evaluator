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
            "tokens_total":     t.tokens_used.get("total", 0),
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
        return f"${v:.6f}" if v < 0.01 else f"${v:.4f}"

    tasks_rows = ""
    for t in rf.tasks:
        ok = "✅" if t.success else "❌"
        tasks_rows += (
            f"<tr><td>{t.task_id}</td><td>{t.task_type}</td><td>{ok}</td>"
            f"<td>{pct(t.completion_score * 100)}</td>"
            f"<td>{pct(t.accuracy_score * 100)}</td>"
            f"<td>{sec_(t.execution_time)}</td>"
            f"<td>{t.tokens_used.get('total', 0)}</td>"
            f"<td>{t.attempts}</td></tr>\n"
        )

    data_json = json.dumps({
        "tcr": tcr.get("tcr", 0),
        "acc": acc.get("overall_accuracy", 0),
        "full": tcr.get("full_success", 0),
        "part": tcr.get("partial_success", 0),
        "fail": tcr.get("failures", 0),
    })

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Agent Evaluator Report — {rf.name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e2e4f0;margin:0;padding:20px;font-size:14px}}
h1{{font-size:20px;margin-bottom:4px}} h2{{font-size:14px;font-weight:600;margin:16px 0 8px}}
.meta{{font-size:12px;color:#8890b0;margin-bottom:20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
.kpi{{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:12px}}
.kpi-lbl{{font-size:10px;color:#8890b0;text-transform:uppercase}}
.kpi-val{{font-size:22px;font-weight:800;margin:3px 0}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px}}
th{{background:#1a1d27;padding:7px 10px;text-align:left;border-bottom:1px solid #2d3148;color:#8890b0}}
td{{padding:6px 10px;border-bottom:1px solid #1a1d27}}
tr:hover td{{background:#1a1d27}}
.chart-wrap{{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:12px;margin-bottom:16px;max-width:400px}}
canvas{{max-height:200px}}
.footer{{margin-top:24px;font-size:11px;color:#8890b0;border-top:1px solid #2d3148;padding-top:10px}}
</style>
</head>
<body>
<h1>🤖 Agent Evaluator Report</h1>
<div class="meta">파일: <b>{rf.name}</b> | 타임스탬프: {rf.timestamp} | 총 Tasks: {rf.total_tasks}</div>

<div class="kpis">
  <div class="kpi"><div class="kpi-lbl">TCR</div><div class="kpi-val">{pct(tcr.get('tcr'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Accuracy</div><div class="kpi-val">{pct(acc.get('overall_accuracy'))}</div></div>
  <div class="kpi"><div class="kpi-lbl">Hallucination</div><div class="kpi-val">{pct(hall.get('overall_rate'))}</div></div>
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

<h2>📋 태스크 목록</h2>
<table>
<thead><tr><th>Task ID</th><th>Type</th><th>✓</th><th>Completion</th><th>Accuracy</th><th>Latency</th><th>Tokens</th><th>Attempts</th></tr></thead>
<tbody>{tasks_rows}</tbody>
</table>

<div class="footer">Generated by Agent Evaluator | {rf.timestamp}</div>

<script>
const D = {data_json};
new Chart(document.getElementById('donut'), {{
  type: 'doughnut',
  data: {{
    labels: ['완전성공','부분성공','실패'],
    datasets: [{{ data:[D.full,D.part,D.fail], backgroundColor:['#4ade80','#facc15','#f87171'], borderWidth:0 }}]
  }},
  options: {{ cutout:'70%', plugins:{{ legend:{{ labels:{{ color:'#8890b0', font:{{size:11}} }} }} }} }}
}});
</script>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{rf.name}_report.html"'},
    )
