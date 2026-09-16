"""
Harness Autopilot M0 로컬 대시보드 (설계서 SPEC-AP-001 §5.1·§6 M0).

M0 완료조건("대시보드가 실제 .aoo/claims.jsonl·decisions.jsonl을 렌더")만
채운다 — UI 목업(claude.ai artifact)의 나머지 9개 화면(승인 큐·모니터링·
Gate 스코어보드 등)은 아직 실데이터에 연결돼 있지 않다. 이 앱은 기존
``agent_evaluator/serve/server.py``의 대시보드를 대체하지 않는 별도의
가벼운 읽기 전용 서버다(포트 8766, 결과 대시보드의 8765와 분리).

새 판정 로직은 없다(원칙2) — ``team_concurrency.load_active_claims()``·
``rca.decision_ledger.load_decisions()``·``autopilot_state`` 모듈을 그대로
읽어 JSON/HTML로 보여줄 뿐이다.
"""
from __future__ import annotations

from html import escape as _esc
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    load_all_tasks,
    load_team,
)
from agent_evaluator.gates.team_concurrency import load_active_claims
from agent_evaluator.rca.decision_ledger import load_decisions


def _safe_claims(claims_path: Path) -> list[dict[str, Any]]:
    try:
        return load_active_claims(claims_path)
    except Exception:
        return []


def _safe_decisions(log_path: Path) -> list[dict[str, Any]]:
    try:
        return load_decisions(log_path)
    except Exception:
        return []


def create_autopilot_app(root: Path) -> FastAPI:
    root = Path(root)
    tasks_dir = root / ".aoo" / "tasks"
    team_path = root / ".aoo" / "team.json"
    claims_path = root / ".aoo" / "claims.jsonl"
    decisions_path = root / ".aoo" / "decisions.jsonl"

    app = FastAPI(title="Harness Autopilot — M0 Dashboard")

    @app.get("/api/tasks")
    def api_tasks() -> JSONResponse:
        return JSONResponse(load_all_tasks(tasks_dir))

    @app.get("/api/team")
    def api_team() -> JSONResponse:
        return JSONResponse(load_team(team_path))

    @app.get("/api/claims")
    def api_claims() -> JSONResponse:
        return JSONResponse(_safe_claims(claims_path))

    @app.get("/api/decisions")
    def api_decisions() -> JSONResponse:
        return JSONResponse(_safe_decisions(decisions_path))

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        tasks = load_all_tasks(tasks_dir)
        team = load_team(team_path)
        claims = _safe_claims(claims_path)
        decisions = _safe_decisions(decisions_path)
        return _render_page(root=root, tasks=tasks, team=team, claims=claims, decisions=decisions)

    return app


# ---------------------------------------------------------------------------
# HTML — 목업(설계서 §8 UI 목업)과 같은 토큰 팔레트를 재사용한, M0 실데이터 전용 축소판
# ---------------------------------------------------------------------------

_STYLE = """
:root{
  --paper:#F3F4F1; --paper-raised:#FFFFFF; --paper-sunken:#E9EBE7;
  --ink:#14181D; --ink-dim:#5B6169; --ink-faint:#8B9198;
  --line:#DCDFDB; --accent-h:#B85420; --accent-h-soft:#F1E1D1;
  --accent-a:#2E5A7A; --accent-a-soft:#DCE6EC;
  --success:#2E7D46; --success-soft:#DDEEE1;
  --warning:#96661C; --warning-soft:#F1E4C6;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:'IBM Plex Sans KR','IBM Plex Sans',-apple-system,'Segoe UI',sans-serif;
  font-size:14.5px;line-height:1.55;padding:28px 24px 60px;}
h1{font-size:20px;margin:0 0 4px;}
.eyebrow{font-family:monospace;font-size:11px;color:var(--accent-h);letter-spacing:.06em;
  text-transform:uppercase;font-weight:700;}
.banner{background:var(--warning-soft);color:var(--warning);border-radius:10px;
  padding:12px 16px;font-size:12.8px;margin:16px 0 26px;}
.card{background:var(--paper-raised);border:1px solid var(--line);border-radius:12px;
  padding:16px;margin-bottom:18px;}
.card h2{font-size:14.5px;margin:0 0 10px;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-faint);padding:0 8px 6px;}
td{padding:8px;border-top:1px solid var(--line);font-family:monospace;font-size:12.5px;}
.empty{color:var(--ink-faint);font-size:12.5px;padding:6px 0;}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:10.5px;
  font-weight:700;background:var(--accent-a-soft);color:var(--accent-a);}
.badge.aoo{background:var(--success-soft);color:var(--success);}
"""


def _task_rows(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return (
            '<tr><td colspan="4" class="empty">아직 과제가 없습니다 — '
            "agent-eval autopilot new-task로 등록하세요.</td></tr>"
        )
    rows = []
    for t in tasks:
        plat = _esc(str(t.get("platform", "?")))
        badge_cls = "aoo" if plat == "AOO" else ""
        phase = t.get("current_phase")
        label = PHASE_LABELS.get(phase, str(phase))
        rows.append(
            f"<tr><td>{_esc(str(t.get('task_id')))}</td>"
            f"<td>{_esc(str(t.get('title')))}</td>"
            f"<td><span class='badge {badge_cls}'>{plat}</span></td>"
            f"<td>Phase {_esc(str(phase))} · {_esc(label)}</td></tr>"
        )
    return "".join(rows)


def _team_rows(team: list[dict[str, Any]]) -> str:
    if not team:
        return (
            '<tr><td colspan="3" class="empty">등록된 팀원이 없습니다 — '
            "agent-eval autopilot add-member로 등록하세요.</td></tr>"
        )
    rows = []
    for m in team:
        roles = ", ".join(m.get("roles", []))
        synced = "✅" if m.get("synced") else "⚠️ GitHub 반영 필요"
        rows.append(
            f"<tr><td>{_esc(str(m.get('name')))}</td><td>{_esc(roles)}</td><td>{synced}</td></tr>"
        )
    return "".join(rows)


def _claim_rows(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return '<tr><td colspan="3" class="empty">활성 클레임 없음</td></tr>'
    rows = []
    for c in claims:
        scope = ", ".join(c.get("scope", []))
        rows.append(
            f"<tr><td>{_esc(str(c.get('developer')))}</td>"
            f"<td>{_esc(scope)}</td><td>{_esc(str(c.get('claim_id')))}</td></tr>"
        )
    return "".join(rows)


def _decision_rows(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return '<tr><td colspan="4" class="empty">기록된 게이트 실행이 없음</td></tr>'
    rows = []
    for d in decisions:
        if d.get("kind") != "gate_run":
            continue
        outcome = d.get("outcome", "pending")
        rows.append(
            f"<tr><td>{_esc(str(d.get('id', '')))[:12]}</td>"
            f"<td>exit {_esc(str(d.get('exit_code')))}</td>"
            f"<td>{_esc(str(d.get('verdict_level', '')))}</td>"
            f"<td>{_esc(str(outcome))}</td></tr>"
        )
    return "".join(rows) or '<tr><td colspan="4" class="empty">기록된 게이트 실행이 없음</td></tr>'


def _render_page(
    *,
    root: Path,
    tasks: list[dict[str, Any]],
    team: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Harness Autopilot — M0</title>
<style>{_STYLE}</style></head>
<body>
<div class="eyebrow">Harness Autopilot · M0 실데이터 미리보기</div>
<h1>{_esc(str(root))}</h1>
<div class="banner">
  이 화면은 설계서(SPEC-AP-001) M0 완료조건만 채운 축소판입니다 — 승인 큐·모니터링·
  Gate 스코어보드 등 나머지 9개 화면은 아직 이 실데이터에 연결돼 있지 않고, UI 목업
  아티팩트에만 정적으로 존재합니다.
</div>

<div class="card">
  <h2>과제 — .aoo/tasks/ ({len(tasks)})</h2>
  <table><thead><tr><th>ID</th><th>제목</th><th>플랫폼</th><th>Phase</th></tr></thead>
  <tbody>{_task_rows(tasks)}</tbody></table>
</div>

<div class="card">
  <h2>팀 — .aoo/team.json ({len(team)})</h2>
  <table><thead><tr><th>이름</th><th>역할</th><th>동기화</th></tr></thead>
  <tbody>{_team_rows(team)}</tbody></table>
</div>

<div class="card">
  <h2>활성 클레임 — .aoo/claims.jsonl ({len(claims)})</h2>
  <table><thead><tr><th>담당자</th><th>스코프</th><th>claim_id</th></tr></thead>
  <tbody>{_claim_rows(claims)}</tbody></table>
</div>

<div class="card">
  <h2>배포 결정 원장 — .aoo/decisions.jsonl</h2>
  <table><thead><tr><th>gate run</th><th>exit</th><th>판정</th><th>사람 결정</th></tr></thead>
  <tbody>{_decision_rows(decisions)}</tbody></table>
</div>

<div style="font-size:11.5px;color:var(--ink-faint);margin-top:20px;">
  API: <a href="/api/tasks">/api/tasks</a> · <a href="/api/team">/api/team</a> ·
  <a href="/api/claims">/api/claims</a> · <a href="/api/decisions">/api/decisions</a>
</div>
</body></html>"""
