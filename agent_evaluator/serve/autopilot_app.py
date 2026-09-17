"""
Harness Autopilot M0/M0.5 로컬 대시보드 (설계서 SPEC-AP-001 §5.1·§6).

M0 완료조건("대시보드가 실제 .aoo/claims.jsonl·decisions.jsonl을 렌더")과
M0.5 산출물(과제 보드·팀 관리 화면, §9 개선안)을 채운다. UI 목업(claude.ai
artifact)의 정적 화면과 달리, 여기는 폼 제출이 실제로 ``.aoo/`` 파일을
바꾼다 — 그래서 순수 서버 렌더 HTML(자바스크립트 없음)로 만들었다. 나머지
화면(모니터링·Gate 스코어보드 등, M1 이후 실데이터가 생겨야 의미 있는 것들)
은 여전히 목업에만 있다.

기존 ``agent_evaluator/serve/server.py``의 결과 대시보드(포트 8765)를
대체하지 않는 별도 앱이다(포트 8766). 새 판정 로직은 없다(원칙4 — 이미
있는 Gate A–G 채점 엔진을 다시 만들지 않는다) —
``team_concurrency.load_active_claims()``·``rca.decision_ledger.load_decisions()``·
``autopilot_state`` 모듈을 그대로 읽고 쓸 뿐이다.

이 두 함수에 대한 반환 계약과 ``.aoo/*.jsonl`` 포맷 자체의 인터페이스
경계는 ``Docs/specs/SPEC-AP-001-harness-autopilot-interface.md`` 참고.
"""
from __future__ import annotations

from collections import Counter
from html import escape as _esc
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    VALID_PLATFORMS,
    VALID_ROLES,
    add_team_member,
    compute_rejection_rate,
    create_task,
    decide_approval,
    load_all_tasks,
    load_approvals,
    load_pending_approvals,
    load_task,
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
    approvals_path = root / ".aoo" / "approvals.jsonl"

    app = FastAPI(title="Harness Autopilot Dashboard")

    # ------------------------------------------------------------------
    # JSON API — 읽기 전용
    # ------------------------------------------------------------------

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

    @app.get("/api/approvals")
    def api_approvals() -> JSONResponse:
        return JSONResponse(load_approvals(approvals_path))

    # ------------------------------------------------------------------
    # 과제 보드 — 홈
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def board() -> str:
        tasks = load_all_tasks(tasks_dir)
        team = load_team(team_path)
        pending = load_pending_approvals(approvals_path)
        return _layout("board", "과제 보드", _board_body(tasks, team, pending))

    @app.post("/tasks")
    def create_task_route(
        title: str = Form(...),
        platform: str = Form(...),
        priority: str = Form("normal"),
        task_id: str = Form(""),
        analysis: str = Form(""),
        design: str = Form(""),
    ) -> RedirectResponse:
        import uuid

        tid = task_id.strip() or f"T-{uuid.uuid4().hex[:6].upper()}"
        owners: dict[str, str] = {}
        if analysis.strip():
            owners["analysis"] = analysis.strip()
        if design.strip():
            owners["design"] = design.strip()
        try:
            create_task(
                tasks_dir, task_id=tid, title=title, platform=platform,
                priority=priority, owners=owners,
            )
        except ValueError:
            pass  # 중복 id 등 — 폼 재제출 시 조용히 무시하고 보드로 돌아간다(M0.5 범위)
        return RedirectResponse("/", status_code=303)

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    def task_detail(task_id: str) -> HTMLResponse:
        task = load_task(tasks_dir, task_id)
        if task is None:
            body = f"<p class='empty'>과제 {_esc(task_id)}를 찾을 수 없습니다.</p>"
            return HTMLResponse(_layout("board", "과제 없음", body), status_code=404)
        related = [
            a for a in load_approvals(approvals_path) if a.get("task_id") == task_id
        ]
        page_title = f"{task_id} · {task.get('title', '')}"
        return HTMLResponse(_layout("board", page_title, _task_detail_body(task, related)))

    # ------------------------------------------------------------------
    # 팀 관리
    # ------------------------------------------------------------------

    @app.get("/team", response_class=HTMLResponse)
    def team_page() -> str:
        return _layout("team", "팀 관리", _team_body(load_team(team_path)))

    @app.post("/team")
    def add_member_route(
        member_id: str = Form(...),
        name: str = Form(...),
        role: list[str] = Form(...),
        github: str = Form(""),
    ) -> RedirectResponse:
        try:
            add_team_member(
                team_path, member_id=member_id, name=name, roles=role,
                github=github.strip() or None,
            )
        except ValueError:
            pass  # 중복 id·알 수 없는 역할 — 조용히 무시(M0.5 범위, 폼 검증은 M1 이후)
        return RedirectResponse("/team", status_code=303)

    # ------------------------------------------------------------------
    # 승인 대기 큐
    # ------------------------------------------------------------------

    @app.get("/approvals", response_class=HTMLResponse)
    def approvals_page() -> str:
        pending = load_pending_approvals(approvals_path)
        drafts = [a for a in load_approvals(approvals_path) if a.get("status") == "draft"]
        return _layout("approvals", "승인 대기", _approvals_body(pending, drafts))

    @app.post("/approvals/{approval_id}/decide")
    def decide_route(
        approval_id: str,
        decision: str = Form(...),
        decided_by: str = Form(...),
        rationale: str = Form(""),
    ) -> RedirectResponse:
        try:
            decide_approval(
                approvals_path, approval_id, decision=decision,
                decided_by=decided_by, rationale=rationale.strip() or None,
            )
        except ValueError:
            pass  # 잘못된 id/사유 누락 — 큐로 돌아가 다시 시도(M0.5 범위)
        return RedirectResponse("/approvals", status_code=303)

    # ------------------------------------------------------------------
    # 운영 현황 — 클레임 · 결정 원장 (M0 완료조건)
    # ------------------------------------------------------------------

    @app.get("/ops", response_class=HTMLResponse)
    def ops_page() -> str:
        claims = _safe_claims(claims_path)
        decisions = _safe_decisions(decisions_path)
        rejection = compute_rejection_rate(approvals_path)
        return _layout("ops", "운영 현황", _ops_body(claims, decisions, rejection))

    return app


# ---------------------------------------------------------------------------
# HTML — 목업(설계서 §8)과 같은 토큰 팔레트를 재사용한 서버 렌더 전용판.
# 자바스크립트 없음 — 폼 제출이 실제로 .aoo/ 파일을 바꾸는 게 목적이라
# 순수 HTML form + 303 redirect로 단순하게 유지한다.
# ---------------------------------------------------------------------------

_STYLE = """
:root{
  --paper:#F3F4F1; --paper-raised:#FFFFFF; --paper-sunken:#E9EBE7;
  --ink:#14181D; --ink-dim:#5B6169; --ink-faint:#8B9198;
  --line:#DCDFDB; --accent-h:#B85420; --accent-h-soft:#F1E1D1;
  --accent-a:#2E5A7A; --accent-a-soft:#DCE6EC;
  --success:#2E7D46; --success-soft:#DDEEE1;
  --warning:#96661C; --warning-soft:#F1E4C6;
  --critical:#B23B3B; --critical-soft:#F5DEDE;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:'IBM Plex Sans KR','IBM Plex Sans',-apple-system,'Segoe UI',sans-serif;
  font-size:14.5px;line-height:1.55;}
a{color:var(--accent-a);}
.shell{max-width:920px;margin:0 auto;padding:20px 20px 60px;}
.nav{display:flex;gap:4px;align-items:center;padding:12px 20px;
  border-bottom:1px solid var(--line);background:var(--paper-raised);flex-wrap:wrap;}
.nav .brand{font-weight:800;font-family:monospace;font-size:13px;margin-right:16px;
  color:var(--accent-h);}
.nav a{text-decoration:none;color:var(--ink-dim);padding:6px 12px;border-radius:8px;
  font-size:13px;font-weight:600;}
.nav a.active{background:var(--ink);color:var(--paper);}
h1{font-size:20px;margin:18px 0 4px;}
.eyebrow{font-family:monospace;font-size:11px;color:var(--accent-h);letter-spacing:.06em;
  text-transform:uppercase;font-weight:700;}
.banner{background:var(--warning-soft);color:var(--warning);border-radius:10px;
  padding:12px 16px;font-size:12.8px;margin:14px 0 22px;}
.card{background:var(--paper-raised);border:1px solid var(--line);border-radius:12px;
  padding:16px;margin-bottom:18px;}
.card h2{font-size:14.5px;margin:0 0 10px;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-faint);padding:0 8px 6px;}
td{padding:8px;border-top:1px solid var(--line);font-family:monospace;font-size:12.5px;
  vertical-align:top;}
.empty{color:var(--ink-faint);font-size:12.5px;padding:6px 0;}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:10.5px;
  font-weight:700;background:var(--accent-a-soft);color:var(--accent-a);}
.badge.aoo{background:var(--success-soft);color:var(--success);}
.badge.pending{background:var(--warning-soft);color:var(--warning);}
.badge.draft{background:var(--paper-sunken);color:var(--ink-faint);}
.badge.approved{background:var(--success-soft);color:var(--success);}
.badge.rejected,.badge.changes_requested{background:var(--critical-soft);color:var(--critical);}
.badge.pass{background:var(--success-soft);color:var(--success);}
.badge.warning{background:var(--warning-soft);color:var(--warning);}
.task-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;}
.task-card{display:block;text-decoration:none;color:inherit;background:var(--paper-raised);
  border:1px solid var(--line);border-radius:12px;padding:14px;}
.task-card:hover{border-color:var(--accent-a);}
.task-card .tt{font-weight:700;font-size:13.3px;margin:8px 0 4px;}
.task-card .tm{font-family:monospace;font-size:11.3px;color:var(--ink-dim);}
.phase-dots{display:flex;gap:3px;margin:8px 0 0;}
.phase-dots i{width:7px;height:7px;border-radius:50%;background:var(--paper-sunken);
  border:1px solid var(--line);display:block;}
.phase-dots i.done{background:var(--success);border-color:var(--success);}
.phase-dots i.cur{background:var(--accent-h);border-color:var(--accent-h);}
form.inline{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;}
.field{display:flex;flex-direction:column;gap:4px;}
.field label{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-faint);font-weight:700;}
input[type=text],select,textarea{border:1px solid var(--line);border-radius:8px;padding:7px 9px;
  font:inherit;font-size:12.8px;background:var(--paper-sunken);color:var(--ink);}
textarea{min-height:50px;width:100%;resize:vertical;}
button{border:1px solid var(--ink);background:var(--ink);color:var(--paper);border-radius:8px;
  padding:8px 14px;font-size:12.5px;font-weight:700;cursor:pointer;font-family:inherit;}
button.ghost{background:transparent;color:var(--ink-dim);border-color:var(--line);}
button.danger{background:transparent;color:var(--critical);border-color:var(--critical);}
.approval-item{border:1px solid var(--line);border-radius:12px;padding:14px;
  margin-bottom:12px;background:var(--paper-raised);}
.approval-item.top{border-left:4px solid var(--critical);}
.checklist{list-style:none;padding:0;margin:8px 0;font-size:12.5px;}
.checklist li{padding:3px 0;}
.checklist li.blocking{color:var(--warning);}
.nc-tag{display:block;font-size:12px;color:var(--warning);}
"""

_NAV_ITEMS = [("board", "/", "과제 보드"), ("approvals", "/approvals", "승인 대기"),
              ("team", "/team", "팀 관리"), ("ops", "/ops", "운영 현황")]


def _nav(active: str) -> str:
    links = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for key, href, label in _NAV_ITEMS
    )
    return f'<div class="nav"><span class="brand">HARNESS AUTOPILOT</span>{links}</div>'


def _layout(active: str, title: str, body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_esc(title)} — Harness Autopilot</title>
<style>{_STYLE}</style></head>
<body>
{_nav(active)}
<div class="shell">
{body}
</div>
</body></html>"""


def _platform_badge(platform: str) -> str:
    p = _esc(str(platform))
    cls = "aoo" if p == "AOO" else ""
    return f'<span class="badge {cls}">{p}</span>'


def _status_badge(status: str) -> str:
    s = _esc(str(status))
    return f'<span class="badge {s}">{s}</span>'


def _phase_label(phase: Any) -> str:
    """``current_phase``가 없거나(구버전 파일) 정수가 아니어도 안전하게 라벨을 찾는다."""
    return PHASE_LABELS.get(phase if isinstance(phase, int) else -1, str(phase))


def _phase_dots(current_phase: int) -> str:
    dots = []
    for i in range(9):
        cls = "done" if i < current_phase else ("cur" if i == current_phase else "")
        dots.append(f'<i class="{cls}"></i>')
    return f'<div class="phase-dots">{"".join(dots)}</div>'


def _board_body(
    tasks: list[dict[str, Any]],
    team: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]] | None = None,
) -> str:
    # blocking_on(과제 파일 필드)은 아직 아무도 쓰지 않는다 — 대신 "이 과제를
    # task_id로 건 pending 승인이 있는가"를 매번 여기서 직접 센다. 필드를
    # 억지로 동기화하면 §9 마찰 #6과 똑같은 새 동기화 버그를 또 만든다.
    pending_by_task = Counter(a.get("task_id") for a in (pending_approvals or []))

    if tasks:
        cards = "".join(
            f'<a class="task-card" href="/tasks/{_esc(str(t.get("task_id")))}">'
            f'{_platform_badge(t.get("platform", "?"))} '
            f'{_status_badge_for_task(t, pending_by_task)}'
            f'<div class="tt">{_esc(str(t.get("title")))}</div>'
            f'<div class="tm">{_esc(str(t.get("task_id")))}</div>'
            f'{_phase_dots(t.get("current_phase", 0))}'
            f'<div class="tm">Phase {_esc(str(t.get("current_phase")))} · '
            f'{_esc(_phase_label(t.get("current_phase")))}</div>'
            f"</a>"
            for t in tasks
        )
        grid = f'<div class="task-grid">{cards}</div>'
    else:
        grid = '<p class="empty">아직 과제가 없습니다 — 아래에서 등록하세요.</p>'

    owner_options = "".join(
        f'<option value="{_esc(m["id"])}">{_esc(m["name"])}</option>' for m in team
    )
    platform_options = "".join(f'<option value="{p}">{p}</option>' for p in VALID_PLATFORMS)

    form = f"""
<div class="card">
  <h2>+ 새 과제</h2>
  <form class="inline" method="post" action="/tasks">
    <div class="field"><label>제목</label>
      <input type="text" name="title" required></div>
    <div class="field"><label>플랫폼</label>
      <select name="platform">{platform_options}</select></div>
    <div class="field"><label>분석 담당</label>
      <select name="analysis"><option value=""></option>{owner_options}</select></div>
    <div class="field"><label>설계 담당</label>
      <select name="design"><option value=""></option>{owner_options}</select></div>
    <button type="submit">과제 등록 — Phase 0</button>
  </form>
</div>"""

    return f"""
<div class="eyebrow">과제 보드</div>
<h1>진행 중인 과제 ({len(tasks)})</h1>
{grid}
{form}
"""


def _status_badge_for_task(task: dict[str, Any], pending_by_task: Counter[Any]) -> str:
    if pending_by_task.get(task.get("task_id"), 0) > 0:
        return '<span class="badge pending">승인 대기</span>'
    if task.get("current_phase") == 8:
        return '<span class="badge approved">운영중</span>'
    return ""


def _task_detail_body(task: dict[str, Any], related_approvals: list[dict[str, Any]]) -> str:
    owners = task.get("owners") or {}
    owners_html = "".join(
        f"<tr><td>{_esc(k)}</td><td>{_esc(str(v))}</td></tr>" for k, v in owners.items()
    ) or '<tr><td colspan="2" class="empty">담당자 미배정</td></tr>'

    approvals_html = "".join(
        f'<li>{_status_badge(a.get("status", ""))} {_esc(str(a.get("title")))} '
        f'<span class="tm">({_esc(str(a.get("kind")))})</span></li>'
        for a in related_approvals
    ) or '<li class="empty">관련 승인 항목 없음</li>'

    phase_label_html = _esc(_phase_label(task.get("current_phase")))
    return f"""
<p><a href="/">← 과제 보드</a></p>
<div class="eyebrow">{_platform_badge(task.get("platform", "?"))}
  {_esc(str(task.get("task_id")))}</div>
<h1>{_esc(str(task.get("title")))}</h1>
{_phase_dots(task.get("current_phase", 0))}
<p class="tm">Phase {_esc(str(task.get("current_phase")))} · {phase_label_html}</p>

<div class="card">
  <h2>담당자</h2>
  <table>{owners_html}</table>
</div>

<div class="card">
  <h2>관련 승인 항목</h2>
  <ul class="checklist">{approvals_html}</ul>
</div>
"""


def _team_body(team: list[dict[str, Any]]) -> str:
    if team:
        rows = "".join(
            f"<tr><td>{_esc(str(m.get('name')))}</td>"
            f"<td>{', '.join(_esc(r) for r in m.get('roles', []))}</td>"
            f"<td>{'✅' if m.get('synced') else '⚠️ GitHub 반영 필요'}</td>"
            f"<td>{_esc(str(m.get('github') or '—'))}</td></tr>"
            for m in team
        )
    else:
        rows = '<tr><td colspan="4" class="empty">등록된 팀원이 없습니다.</td></tr>'

    role_options = "".join(
        f'<label style="font-weight:400;text-transform:none;letter-spacing:0;">'
        f'<input type="checkbox" name="role" value="{r}"> {r}</label>'
        for r in VALID_ROLES
    )

    return f"""
<div class="eyebrow">팀 관리</div>
<h1>팀원 ({len(team)})</h1>
<div class="card">
  <table><thead><tr><th>이름</th><th>역할</th><th>동기화</th><th>GitHub</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>

<div class="card">
  <h2>+ 팀원 추가</h2>
  <form class="inline" method="post" action="/team">
    <div class="field"><label>ID</label>
      <input type="text" name="member_id" required></div>
    <div class="field"><label>이름</label>
      <input type="text" name="name" required></div>
    <div class="field"><label>역할</label>
      <div style="display:flex;gap:10px;">{role_options}</div></div>
    <div class="field"><label>GitHub</label>
      <input type="text" name="github" placeholder="@handle"></div>
    <button type="submit">팀원 추가</button>
  </form>
  <p style="font-size:11.5px;color:var(--warning);margin:10px 0 0;">
    ⚠️ 추가해도 GitHub CODEOWNERS는 자동으로 갱신되지 않습니다 — 별도로 반영해야
    이 사람의 승인이 실제로 라우팅됩니다(설계서 §4.6).
  </p>
</div>
"""


def _approval_card(a: dict[str, Any], *, top: bool = False) -> str:
    checklist = a.get("checklist") or []
    # gate_on_checklist=False면 이 체크리스트는 "할 일 목록"이지 승인 게이트가
    # 아니다(예: threshold_review의 4단계 절차) — pending이어도 경고색을 안 준다.
    is_gate = a.get("gate_on_checklist", True)
    checklist_html = "".join(
        f'<li class="{"blocking" if is_gate and c.get("status") != "ok" else ""}">'
        f'[{_esc(str(c.get("status")))}] {_esc(str(c.get("label")))}</li>'
        for c in checklist
    )
    nc = a.get("needs_clarification") or []
    nc_html = "".join(f'<span class="nc-tag">⚠ {_esc(n)}</span>' for n in nc)

    required = a.get("required_approvals", 1) or 1
    recorded = a.get("approvals_recorded") or []
    progress_html = ""
    if required > 1:
        who = ", ".join(_esc(str(r.get("by", ""))) for r in recorded) or "아직 없음"
        progress_html = (
            f'<p class="tm">승인 {len(recorded)}/{required}명 · {who}'
            f'<br>2인 승인 대상 — 아래에서 승인해도 이미 승인한 사람과 '
            f'같은 이름이면 거부됩니다.</p>'
        )

    decide_form = ""
    if a.get("status") in ("pending",):
        decide_form = f"""
<form method="post" action="/approvals/{_esc(str(a.get("id")))}/decide" style="margin-top:10px;">
  <div class="field"><label>결정자</label>
    <input type="text" name="decided_by" required placeholder="예: 이지훈"></div>
  <textarea name="rationale" placeholder="근거(반려·수정요청 시 필수)"></textarea>
  <div style="display:flex;gap:8px;margin-top:8px;">
    <button type="submit" name="decision" value="approved">승인</button>
    <button type="submit" name="decision" value="changes_requested" class="ghost">수정 요청</button>
    <button type="submit" name="decision" value="rejected" class="danger">반려</button>
  </div>
</form>
"""

    cls = "approval-item top" if top else "approval-item"
    meta = (
        f'[{_esc(str(a.get("task_id")))}] · {_esc(str(a.get("kind")))} '
        f'· phase {_esc(str(a.get("phase")))}'
    )
    return f"""
<div class="{cls}">
  <div>{_status_badge(a.get("status", ""))} <b>{_esc(str(a.get("title")))}</b>
    <span class="tm">{meta}</span></div>
  {f'<ul class="checklist">{checklist_html}</ul>' if checklist_html else ""}
  {nc_html}
  {progress_html}
  {decide_form}
</div>"""


def _approvals_body(pending: list[dict[str, Any]], drafts: list[dict[str, Any]]) -> str:
    pending_html = "".join(_approval_card(a, top=(a.get("kind") == "deploy")) for a in pending) or (
        '<p class="empty">승인 대기 중인 항목이 없습니다.</p>'
    )
    drafts_html = "".join(_approval_card(a) for a in drafts) or ""
    drafts_header = f"초안 — 아직 사람 큐에 안 올라옴 ({len(drafts)})"
    drafts_section = (
        f'<div class="card"><h2>{drafts_header}</h2>{drafts_html}</div>' if drafts else ""
    )

    return f"""
<div class="eyebrow">HITL 승인 큐</div>
<h1>승인 대기 ({len(pending)})</h1>
<div class="banner">
  "결정자"란은 자유 텍스트입니다 — 실제 사용자 인증(로그인, GitHub required review
  연동)은 아직 없습니다. 2인 승인 대상 항목은 서로 다른 이름을
  넣어야 합니다 — 같은 이름으로 두 번 승인해도 카운트되지 않습니다.
</div>
{pending_html}
{drafts_section}
"""


def _rejection_rate_card(rejection: dict[str, Any]) -> str:
    """원칙6 자가점검(부록 H.7) — "HITL 관문 반려 이력이 0건이다"가 위반 신호다.

    새 데이터 없음 — ``.aoo/approvals.jsonl`` 기존 이력만 다시 센다(§9.5.4 순위4).
    """
    total = rejection.get("total", 0)
    rate = rejection.get("rejection_rate")
    window = rejection.get("window")

    if total == 0:
        body = '<p class="empty">아직 결정된 승인이 없음 — 반려율을 아직 계산할 수 없음</p>'
    else:
        pct = f"{rate * 100:.0f}%" if rate is not None else "—"
        rubber_stamp_risk = total >= 5 and rate == 0.0
        cls = "warning" if rubber_stamp_risk else "pass"
        note = (
            ' <span class="tm">— 반려 이력 0건, 형식적 승인(고무도장) 위험 신호(부록 H.7)</span>'
            if rubber_stamp_risk else ""
        )
        body = (
            f'<p><span class="badge {cls}">반려율 {pct}</span> '
            f'최근 {total}건(최대 {window}건 기준) 중 반려·수정요청 '
            f'{rejection.get("rejected_or_changes_requested", 0)}건{note}</p>'
        )

    return f"""
<div class="card">
  <h2>원칙6 자가점검 — 승인 반려율</h2>
  {body}
</div>"""


def _ops_body(
    claims: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    rejection: dict[str, Any] | None = None,
) -> str:
    claim_rows = "".join(
        f"<tr><td>{_esc(str(c.get('developer')))}</td>"
        f"<td>{_esc(', '.join(c.get('scope', [])))}</td>"
        f"<td>{_esc(str(c.get('claim_id')))}</td></tr>"
        for c in claims
    ) or '<tr><td colspan="3" class="empty">활성 클레임 없음</td></tr>'

    decision_rows = ""
    for d in decisions:
        if d.get("kind") != "gate_run":
            continue
        decision_rows += (
            f"<tr><td>{_esc(str(d.get('id', '')))[:12]}</td>"
            f"<td>exit {_esc(str(d.get('exit_code')))}</td>"
            f"<td>{_esc(str(d.get('verdict_level', '')))}</td>"
            f"<td>{_esc(str(d.get('outcome', 'pending')))}</td></tr>"
        )
    decision_rows = (
        decision_rows or '<tr><td colspan="4" class="empty">기록된 게이트 실행이 없음</td></tr>'
    )

    rejection_html = _rejection_rate_card(rejection) if rejection is not None else ""

    return f"""
<div class="eyebrow">원칙6 자가점검</div>
<h1>운영 현황</h1>
<div class="card">
  <h2>활성 클레임 — .aoo/claims.jsonl ({len(claims)})</h2>
  <table><thead><tr><th>담당자</th><th>스코프</th><th>claim_id</th></tr></thead>
  <tbody>{claim_rows}</tbody></table>
</div>
<div class="card">
  <h2>배포 결정 원장 — .aoo/decisions.jsonl</h2>
  <table><thead><tr><th>gate run</th><th>exit</th><th>판정</th><th>사람 결정</th></tr></thead>
  <tbody>{decision_rows}</tbody></table>
</div>
{rejection_html}
"""
