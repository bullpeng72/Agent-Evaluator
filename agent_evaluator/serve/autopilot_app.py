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
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from agent_evaluator.cli.autopilot import _ADR_MODEL_TIER_CHECKLIST_LABEL, _parse_checklist_items
from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    VALID_APPROVAL_KINDS,
    VALID_PLATFORMS,
    VALID_ROLES,
    VALID_TASK_STATUSES,
    add_team_member,
    cancel_approval,
    check_phase_staleness,
    compute_rejection_rate,
    create_task,
    decide_approval,
    load_all_tasks,
    load_approvals,
    load_pending_approvals,
    load_task,
    load_team,
    open_approval,
    remove_team_member,
    set_task_status,
    transition_phase,
    update_approval_checklist,
    update_task,
    update_team_member,
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
    def board(show_all: bool = False) -> str:
        tasks = load_all_tasks(tasks_dir)
        team = load_team(team_path)
        pending = load_pending_approvals(approvals_path)
        stale_ids = {s["task_id"] for s in check_phase_staleness(tasks_dir, stale_days=7.0)}
        return _layout(
            "board", "과제 보드",
            _board_body(tasks, team, pending, stale_ids, show_all=show_all),
        )

    @app.post("/tasks")
    def create_task_route(
        title: str = Form(...),
        platform: str = Form(...),
        priority: str = Form("normal"),
        task_id: str = Form(""),
        analysis: str = Form(""),
        design: str = Form(""),
        development: str = Form(""),
        qa: str = Form(""),
        pm: str = Form(""),
        security: str = Form(""),
    ) -> RedirectResponse:
        import uuid

        tid = task_id.strip() or f"T-{uuid.uuid4().hex[:6].upper()}"
        owners: dict[str, str] = {}
        for role_key, value in (
            ("analysis", analysis), ("design", design), ("development", development),
            ("qa", qa), ("pm", pm), ("security", security),
        ):
            if value.strip():
                owners[role_key] = value.strip()
        try:
            create_task(
                tasks_dir, task_id=tid, title=title, platform=platform,
                priority=priority, owners=owners,
            )
        except ValueError:
            pass  # 중복 id 등 — 폼 재제출 시 조용히 무시하고 보드로 돌아간다(M0.5 범위)
        return RedirectResponse("/", status_code=303)

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    def task_detail(task_id: str, phase_error: str = "", phase_warning: str = "") -> HTMLResponse:
        task = load_task(tasks_dir, task_id)
        if task is None:
            body = f"<p class='empty'>과제 {_esc(task_id)}를 찾을 수 없습니다.</p>"
            return HTMLResponse(_layout("board", "과제 없음", body), status_code=404)
        related = [
            a for a in load_approvals(approvals_path) if a.get("task_id") == task_id
        ]
        stale = next(
            (s for s in check_phase_staleness(tasks_dir, stale_days=7.0)
             if s["task_id"] == task_id),
            None,
        )
        page_title = f"{task_id} · {task.get('title', '')}"
        return HTMLResponse(
            _layout(
                "board", page_title,
                _task_detail_body(
                    task, related, stale,
                    phase_error=phase_error, phase_warning=phase_warning,
                ),
            )
        )

    @app.post("/tasks/{task_id}/phase")
    def transition_phase_route(
        task_id: str,
        new_phase: int = Form(...),
        require_approval: str = Form(""),
        approved_by: str = Form(""),
    ) -> RedirectResponse:
        # docs/AUTOPILOT_IMPROVEMENTS.md §9 — 이 동작(Autopilot phase-gate,
        # PLANNING.md §6가 "책의 척추"라고 부르는 바로 그 메커니즘)이 대시보드에
        # 아예 없었다. CLI의 _cmd_autopilot_phase_transition()과 같은 비차단
        # 역행/건너뛰기 경고를 그대로 재현한다(새 판정 로직 아님).
        warning = ""
        existing_task = load_task(tasks_dir, task_id)
        if existing_task is not None:
            current_phase = existing_task.get("current_phase")
            if isinstance(current_phase, int) and new_phase < current_phase:
                warning = (
                    f"phase {new_phase} is BEHIND the current phase "
                    f"{current_phase} — proceeded anyway (not blocked)."
                )
            elif isinstance(current_phase, int) and new_phase > current_phase + 1:
                warning = (
                    f"skipping from phase {current_phase} to {new_phase} "
                    f"({new_phase - current_phase - 1} phase(s) skipped) — "
                    f"proceeded anyway (not blocked)."
                )
        try:
            transition_phase(
                tasks_dir, task_id, new_phase, mode="auto",
                approved_by=approved_by.strip() or None,
                approvals_path=approvals_path if require_approval else None,
                required_approval_kind=require_approval or None,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/tasks/{task_id}?phase_error={quote(str(exc))}", status_code=303
            )
        suffix = f"?phase_warning={quote(warning)}" if warning else ""
        return RedirectResponse(f"/tasks/{task_id}{suffix}", status_code=303)

    @app.post("/tasks/{task_id}/status")
    def set_task_status_route(
        task_id: str, status: str = Form(...), reason: str = Form("")
    ) -> RedirectResponse:
        try:
            set_task_status(tasks_dir, task_id, status, reason=reason.strip() or None)
        except ValueError:
            pass  # 알 수 없는 status 등 — 상세 페이지로 돌아가 다시 시도(M0.5 범위)
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

    @app.post("/tasks/{task_id}/update")
    def update_task_route(
        task_id: str,
        title: str = Form(""),
        platform: str = Form(""),
        priority: str = Form(""),
        analysis: str = Form(""),
        design: str = Form(""),
        development: str = Form(""),
        qa: str = Form(""),
        pm: str = Form(""),
        security: str = Form(""),
    ) -> RedirectResponse:
        # docs/AUTOPILOT_IMPROVEMENTS.md §1/§9 — 등록 후 제목·플랫폼·우선순위·
        # 담당자를 고칠 방법이 CLI(update-task)에도 대시보드에도 없었다. 폼이
        # 현재 값을 전부 미리 채워서 보내므로(_task_detail_body) 6칸 전체
        # 대체가 안전하다 — CLI의 부분 수정과 달리 화면에 이미 전체 상태가
        # 보이기 때문(+ 새 과제 폼과 같은 패턴).
        owners: dict[str, str] = {}
        for role_key, value in (
            ("analysis", analysis), ("design", design), ("development", development),
            ("qa", qa), ("pm", pm), ("security", security),
        ):
            if value.strip():
                owners[role_key] = value.strip()
        try:
            update_task(
                tasks_dir, task_id,
                title=title.strip() or None, platform=platform or None,
                priority=priority or None, owners=owners,
            )
        except ValueError:
            pass  # 알 수 없는 platform 등 — 상세 페이지로 돌아가 다시 시도(M0.5 범위)
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

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

    @app.post("/team/{member_id}/update")
    def update_member_route(
        member_id: str,
        name: str = Form(""),
        role: list[str] = Form([]),
        github: str = Form(""),
        synced: bool = Form(False),
    ) -> RedirectResponse:
        # docs/AUTOPILOT_IMPROVEMENTS.md §1 — update-member(v1.1.2)가 대시보드엔
        # 없었다. 폼이 현재 값을 그대로 미리 채워서 보내므로(_team_member_card),
        # 체크박스를 안 건드려도 synced가 조용히 False로 초기화되지 않는다.
        try:
            update_team_member(
                team_path, member_id,
                name=name.strip() or None, roles=role or None,
                github=github.strip() or None, synced=synced,
            )
        except ValueError:
            pass  # 알 수 없는 id·역할 — 조용히 무시(M0.5 범위)
        return RedirectResponse("/team", status_code=303)

    @app.post("/team/{member_id}/remove")
    def remove_member_route(member_id: str) -> RedirectResponse:
        try:
            remove_team_member(team_path, member_id)
        except ValueError:
            pass  # 없는 id — 조용히 무시(M0.5 범위)
        return RedirectResponse("/team", status_code=303)

    # ------------------------------------------------------------------
    # 승인 대기 큐
    # ------------------------------------------------------------------

    @app.get("/approvals", response_class=HTMLResponse)
    def approvals_page(open_error: str = "") -> str:
        pending = load_pending_approvals(approvals_path)
        drafts = [a for a in load_approvals(approvals_path) if a.get("status") == "draft"]
        tasks = load_all_tasks(tasks_dir)
        return _layout(
            "approvals", "승인 대기",
            _approvals_body(pending, drafts, tasks, open_error=open_error),
        )

    @app.post("/approvals")
    def open_approval_route(
        task_id: str = Form(...),
        kind: str = Form(...),
        phase: int = Form(...),
        title: str = Form(...),
        checklist_text: str = Form(""),
        body_text: str = Form(""),
        no_checklist_gate: bool = Form(False),
    ) -> RedirectResponse:
        # docs/AUTOPILOT_IMPROVEMENTS.md §9 — 새 승인 요청을 여는 것 자체가
        # 대시보드엔 없었다(decide/cancel만 가능). CLI의 _parse_checklist_items()
        # (마지막 콜론 분리, 잘못된 STATUS 즉시 거부)와 adr_review 자동 체크리스트
        # 추가(원칙5)를 그대로 재사용한다 — 새 판정 로직 아님.
        lines = [ln for ln in checklist_text.splitlines() if ln.strip()]
        try:
            checklist = _parse_checklist_items(lines)
        except ValueError as exc:
            return RedirectResponse(f"/approvals?open_error={quote(str(exc))}", status_code=303)

        if kind == "adr_review" and not any(
            "모델 tier" in item.get("label", "") for item in checklist
        ):
            checklist.append({"label": _ADR_MODEL_TIER_CHECKLIST_LABEL, "status": "pending"})

        try:
            open_approval(
                approvals_path, task_id=task_id, kind=kind, phase=phase, title=title,
                checklist=checklist, body_text=body_text.strip() or None,
                gate_on_checklist=not no_checklist_gate,
            )
        except ValueError as exc:
            return RedirectResponse(f"/approvals?open_error={quote(str(exc))}", status_code=303)
        return RedirectResponse("/approvals", status_code=303)

    @app.post("/approvals/{approval_id}/update")
    def update_checklist_route(
        approval_id: str,
        label: list[str] = Form([]),
        status: list[str] = Form([]),
    ) -> RedirectResponse:
        updates = [{"label": la, "status": st} for la, st in zip(label, status)]
        try:
            update_approval_checklist(approvals_path, approval_id, updates)
        except ValueError:
            pass  # 이미 결정됐거나 라벨 불일치 — 큐로 돌아가 다시 시도(M0.5 범위)
        return RedirectResponse("/approvals", status_code=303)

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

    @app.post("/approvals/{approval_id}/cancel")
    def cancel_route(approval_id: str, reason: str = Form("")) -> RedirectResponse:
        try:
            cancel_approval(approvals_path, approval_id, reason=reason.strip() or None)
        except ValueError:
            pass  # 이미 결정됐거나 없는 id — 큐로 돌아가 다시 시도(M0.5 범위)
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
.banner.critical{background:var(--critical-soft);color:var(--critical);}
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


_OWNER_ROLE_FIELDS = (
    ("analysis", "분석 담당"), ("design", "설계 담당"), ("development", "개발 담당"),
    ("qa", "QA 담당"), ("pm", "PM 담당"), ("security", "보안 담당"),
)


def _board_body(
    tasks: list[dict[str, Any]],
    team: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]] | None = None,
    stale_task_ids: set[Any] | None = None,
    *,
    show_all: bool = False,
) -> str:
    # blocking_on(과제 파일 필드)은 아직 아무도 쓰지 않는다 — 대신 "이 과제를
    # task_id로 건 pending 승인이 있는가"를 매번 여기서 직접 센다. 필드를
    # 억지로 동기화하면 §9 마찰 #6과 똑같은 새 동기화 버그를 또 만든다.
    pending_by_task = Counter(a.get("task_id") for a in (pending_approvals or []))
    stale_task_ids = stale_task_ids or set()

    all_tasks = tasks
    visible_tasks = tasks if show_all else [
        t for t in tasks if t.get("status", "active") == "active"
    ]
    hidden_count = len(all_tasks) - len(visible_tasks)

    if visible_tasks:
        cards = "".join(
            f'<a class="task-card" href="/tasks/{_esc(str(t.get("task_id")))}">'
            f'{_platform_badge(t.get("platform", "?"))} '
            f'{_status_badge_for_task(t, pending_by_task, stale_task_ids)}'
            f'<div class="tt">{_esc(str(t.get("title")))}</div>'
            f'<div class="tm">{_esc(str(t.get("task_id")))}</div>'
            f'{_phase_dots(t.get("current_phase", 0))}'
            f'<div class="tm">Phase {_esc(str(t.get("current_phase")))} · '
            f'{_esc(_phase_label(t.get("current_phase")))}</div>'
            f"</a>"
            for t in visible_tasks
        )
        grid = f'<div class="task-grid">{cards}</div>'
    elif all_tasks:
        grid = '<p class="empty">활성 과제가 없습니다 — 아래 링크로 전체를 확인하세요.</p>'
    else:
        grid = '<p class="empty">아직 과제가 없습니다 — 아래에서 등록하세요.</p>'

    toggle_html = (
        f'<p class="tm"><a href="/?show_all=1">전체 보기(완료·취소 {hidden_count}건 포함)</a></p>'
        if not show_all and hidden_count
        else ('<p class="tm"><a href="/">활성 과제만 보기</a></p>' if show_all else "")
    )

    owner_options = "".join(
        f'<option value="{_esc(m["id"])}">{_esc(m["name"])}</option>' for m in team
    )
    platform_options = "".join(f'<option value="{p}">{p}</option>' for p in VALID_PLATFORMS)
    owner_fields_html = "".join(
        f'<div class="field"><label>{label}</label>'
        f'<select name="{key}"><option value=""></option>{owner_options}</select></div>'
        for key, label in _OWNER_ROLE_FIELDS
    )

    form = f"""
<div class="card">
  <h2>+ 새 과제</h2>
  <form class="inline" method="post" action="/tasks">
    <div class="field"><label>제목</label>
      <input type="text" name="title" required></div>
    <div class="field"><label>플랫폼</label>
      <select name="platform">{platform_options}</select></div>
    {owner_fields_html}
    <button type="submit">과제 등록 — Phase 0</button>
  </form>
</div>"""

    return f"""
<div class="eyebrow">과제 보드</div>
<h1>진행 중인 과제 ({len(visible_tasks)})</h1>
{toggle_html}
{grid}
{form}
"""


def _status_badge_for_task(
    task: dict[str, Any], pending_by_task: Counter[Any], stale_task_ids: set[Any] | None = None,
) -> str:
    badges = []
    status = task.get("status", "active")
    if status != "active":
        badges.append(f'<span class="badge draft">{_esc(status)}</span>')
    if task.get("task_id") in (stale_task_ids or set()):
        badges.append('<span class="badge warning">phase 정체</span>')
    if pending_by_task.get(task.get("task_id"), 0) > 0:
        badges.append('<span class="badge pending">승인 대기</span>')
    if task.get("current_phase") == 8:
        badges.append('<span class="badge approved">운영중</span>')
    return " ".join(badges)


def _task_detail_body(
    task: dict[str, Any],
    related_approvals: list[dict[str, Any]],
    stale: dict[str, Any] | None = None,
    *,
    phase_error: str = "",
    phase_warning: str = "",
) -> str:
    owners = task.get("owners") or {}
    owners_html = "".join(
        f"<tr><td>{_esc(k)}</td><td>{_esc(str(v))}</td></tr>" for k, v in owners.items()
    ) or '<tr><td colspan="2" class="empty">담당자 미배정</td></tr>'

    approvals_html = "".join(
        f'<li>{_status_badge(a.get("status", ""))} {_esc(str(a.get("title")))} '
        f'<span class="tm">({_esc(str(a.get("kind")))})</span></li>'
        for a in related_approvals
    ) or '<li class="empty">관련 승인 항목 없음</li>'

    status = task.get("status", "active")
    status_html = (
        f'<p class="tm">상태: <span class="badge draft">{_esc(status)}</span>'
        f'{" — " + _esc(str(task["status_reason"])) if task.get("status_reason") else ""}</p>'
        if status != "active" else ""
    )

    # LIMITS_T-5E1FD6.md L4 — 이 phase가 실제 작업과 맞는지 확인하는 신호가
    # 대시보드엔 없었다(CLI의 doctor/phase check에만 있었음). 여기서도 똑같이
    # 보여준다 — 새 계측 없이 check_phase_staleness()가 이미 재는 값 그대로.
    stale_html = (
        f'<div class="banner">⚠ 이 과제는 phase {_esc(str(task.get("current_phase")))}'
        f'({_esc(_phase_label(task.get("current_phase")))})에 '
        f'{stale["days_in_phase"]:.1f}일째 머물러 있습니다(진입: '
        f'{_esc(str(stale["entered_at"]))}) — 실제 작업과 맞는지 확인하거나 '
        f'phase를 전이하세요.</div>'
        if stale else ""
    )

    error_html = (
        f'<div class="banner critical">✗ {_esc(phase_error)}</div>' if phase_error else ""
    )
    warning_html = (
        f'<div class="banner">⚠ {_esc(phase_warning)}</div>' if phase_warning else ""
    )

    kind_options = "".join(f'<option value="{k}">{k}</option>' for k in VALID_APPROVAL_KINDS)
    phase_form = f"""
<div class="card">
  <h2>Phase 전이</h2>
  <form class="inline" method="post" action="/tasks/{_esc(str(task.get("task_id")))}/phase">
    <div class="field"><label>새 phase</label>
      <input type="number" name="new_phase" min="0" max="8" required
        value="{_esc(str(task.get("current_phase", 0)))}"></div>
    <div class="field"><label>필요 승인(선택)</label>
      <select name="require_approval">
        <option value="">(게이트 없음)</option>{kind_options}</select></div>
    <div class="field"><label>승인자(선택)</label>
      <input type="text" name="approved_by" placeholder="예: pm-park"></div>
    <button type="submit">전이</button>
  </form>
  <p class="tm">필요 승인을 지정하면, 그 kind의 승인이 approved 상태로
    확정돼 있어야만 전이됩니다 — 없으면 아래에 에러가 뜨고 막힙니다.</p>
</div>"""

    status_options = "".join(
        f'<option value="{s}"{" selected" if s == status else ""}>{s}</option>'
        for s in VALID_TASK_STATUSES
    )
    status_form = f"""
<div class="card">
  <h2>과제 상태</h2>
  <form class="inline" method="post" action="/tasks/{_esc(str(task.get("task_id")))}/status">
    <div class="field"><label>상태</label>
      <select name="status">{status_options}</select></div>
    <div class="field"><label>사유(선택)</label>
      <input type="text" name="reason" placeholder="예: shipped"></div>
    <button type="submit" class="ghost">상태 변경</button>
  </form>
</div>"""

    # docs/AUTOPILOT_IMPROVEMENTS.md §1/§9 — 등록 후 제목·플랫폼·우선순위·
    # 담당자를 고칠 방법이 없었다(CLI update-task와 함께 신설). 현재 값을
    # 전부 미리 채우므로("+ 새 과제" 폼과 같은 패턴) 안 건드린 필드는
    # 그대로 다시 제출돼 안전하다.
    platform_options_edit = "".join(
        f'<option value="{p}"{" selected" if p == task.get("platform") else ""}>{p}</option>'
        for p in VALID_PLATFORMS
    )
    priority_options = "".join(
        f'<option value="{p}"{" selected" if p == task.get("priority") else ""}>{p}</option>'
        for p in ("high", "normal", "low")
    )
    owner_fields_edit = "".join(
        f'<div class="field"><label>{label}</label>'
        f'<input type="text" name="{key}" value="{_esc(str(owners.get(key, "")))}"></div>'
        for key, label in _OWNER_ROLE_FIELDS
    )
    edit_form = f"""
<div class="card">
  <h2>과제 수정</h2>
  <form class="inline" method="post" action="/tasks/{_esc(str(task.get("task_id")))}/update">
    <div class="field"><label>제목</label>
      <input type="text" name="title" value="{_esc(str(task.get('title')))}"></div>
    <div class="field"><label>플랫폼</label>
      <select name="platform">{platform_options_edit}</select></div>
    <div class="field"><label>우선순위</label>
      <select name="priority">{priority_options}</select></div>
    {owner_fields_edit}
    <button type="submit" class="ghost">과제 정보 저장</button>
  </form>
</div>"""

    phase_label_html = _esc(_phase_label(task.get("current_phase")))
    return f"""
<p><a href="/">← 과제 보드</a></p>
<div class="eyebrow">{_platform_badge(task.get("platform", "?"))}
  {_esc(str(task.get("task_id")))}</div>
<h1>{_esc(str(task.get("title")))}</h1>
{_phase_dots(task.get("current_phase", 0))}
<p class="tm">Phase {_esc(str(task.get("current_phase")))} · {phase_label_html}</p>
{status_html}
{stale_html}
{error_html}
{warning_html}

<div class="card">
  <h2>담당자</h2>
  <table>{owners_html}</table>
</div>

<div class="card">
  <h2>관련 승인 항목</h2>
  <ul class="checklist">{approvals_html}</ul>
</div>

{edit_form}
{phase_form}
{status_form}
"""


def _team_member_card(m: dict[str, Any]) -> str:
    # docs/AUTOPILOT_IMPROVEMENTS.md §1 — 팀원 수정/삭제가 CLI(update-member/
    # remove-member)에는 v1.1.2부터 있었는데 대시보드엔 조회 전용 표뿐이었다.
    # 현재 값을 그대로 미리 채운 폼이라 "고칠 것만 바꾸는" CLI의 부분 수정
    # 의미를 그대로 재현한다(update_team_member()가 그렇게 동작).
    member_id = _esc(str(m.get("id")))
    current_roles = set(m.get("roles") or [])
    role_options = "".join(
        f'<label style="font-weight:400;text-transform:none;letter-spacing:0;">'
        f'<input type="checkbox" name="role" value="{r}"'
        f'{" checked" if r in current_roles else ""}> {r}</label>'
        for r in VALID_ROLES
    )
    sync_note = "" if m.get("synced") else ' <span class="tm">(GitHub CODEOWNERS 반영 필요)</span>'
    return f"""
<div class="approval-item">
  <div><b>{_esc(str(m.get("name")))}</b>
    <span class="tm">{member_id} · {_esc(str(m.get("github") or "—"))}{sync_note}</span></div>
  <form class="inline" method="post" action="/team/{member_id}/update" style="margin-top:8px;">
    <div class="field"><label>이름</label>
      <input type="text" name="name" value="{_esc(str(m.get('name')))}"></div>
    <div class="field"><label>역할</label>
      <div style="display:flex;gap:10px;">{role_options}</div></div>
    <div class="field"><label>GitHub</label>
      <input type="text" name="github" value="{_esc(str(m.get('github') or ''))}"></div>
    <label style="font-weight:400;text-transform:none;letter-spacing:0;">
      <input type="checkbox" name="synced" value="1"{" checked" if m.get("synced") else ""}>
      GitHub 반영됨</label>
    <button type="submit" class="ghost">수정</button>
  </form>
  <form method="post" action="/team/{member_id}/remove" style="margin-top:6px;">
    <button type="submit" class="danger">삭제</button>
  </form>
</div>"""


def _team_body(team: list[dict[str, Any]]) -> str:
    if team:
        rows = "".join(
            f"<tr><td>{_esc(str(m.get('name')))}</td>"
            f"<td>{', '.join(_esc(r) for r in m.get('roles', []))}</td>"
            f"<td>{'✅' if m.get('synced') else '⚠️ GitHub 반영 필요'}</td>"
            f"<td>{_esc(str(m.get('github') or '—'))}</td></tr>"
            for m in team
        )
        member_cards = "".join(_team_member_card(m) for m in team)
    else:
        rows = '<tr><td colspan="4" class="empty">등록된 팀원이 없습니다.</td></tr>'
        member_cards = ""

    role_options = "".join(
        f'<label style="font-weight:400;text-transform:none;letter-spacing:0;">'
        f'<input type="checkbox" name="role" value="{r}"> {r}</label>'
        for r in VALID_ROLES
    )

    member_section = (
        f'<div class="card"><h2>팀원 수정/삭제</h2>{member_cards}</div>' if team else ""
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

{member_section}
"""


_CHECKLIST_STATUS_CHOICES = ("ok", "pending", "flag")


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

    # docs/AUTOPILOT_IMPROVEMENTS.md §9 — draft/pending의 체크리스트 항목
    # 상태를 고치는 것 자체가 대시보드엔 없었다(CLI approvals update 전용).
    # 각 항목의 label을 hidden으로, status를 select로 같은 순서로 반복
    # 제출한다(zip으로 다시 짝짓는다 — update_approval_checklist()는
    # label 일치만 검증하고 새 항목 추가는 거부한다, 새 판정 로직 아님).
    update_form = ""
    if checklist and a.get("status") in ("draft", "pending"):
        rows = "".join(
            f'<div style="display:flex;gap:8px;align-items:center;margin:4px 0;">'
            f'<input type="hidden" name="label" value="{_esc(str(c.get("label")))}">'
            f'<select name="status">'
            + "".join(
                f'<option value="{s}"{" selected" if s == c.get("status") else ""}>{s}</option>'
                for s in _CHECKLIST_STATUS_CHOICES
            )
            + f'</select><span class="tm">{_esc(str(c.get("label")))}</span></div>'
            for c in checklist
        )
        update_form = f"""
<form method="post" action="/approvals/{_esc(str(a.get("id")))}/update" style="margin-top:8px;">
  {rows}
  <button type="submit" class="ghost">체크리스트 반영</button>
</form>
"""

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

    # docs/AUTOPILOT_IMPROVEMENTS.md §4 — draft/pending 승인을 철회할 방법이
    # CLI(`approvals cancel`)에만 있고 대시보드엔 없었다. approved/rejected/
    # changes_requested로 이미 끝난 항목은 cancel_approval() 자체가 거부하므로
    # draft·pending에서만 보여준다.
    cancel_form = ""
    if a.get("status") in ("draft", "pending"):
        cancel_form = f"""
<form method="post" action="/approvals/{_esc(str(a.get("id")))}/cancel" style="margin-top:6px;">
  <div style="display:flex;gap:8px;align-items:center;">
    <input type="text" name="reason" placeholder="철회 사유(선택)" style="flex:1;">
    <button type="submit" class="ghost">철회</button>
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
  {update_form}
  {decide_form}
  {cancel_form}
</div>"""


def _approvals_body(
    pending: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
    tasks: list[dict[str, Any]] | None = None,
    *,
    open_error: str = "",
) -> str:
    pending_html = "".join(_approval_card(a, top=(a.get("kind") == "deploy")) for a in pending) or (
        '<p class="empty">승인 대기 중인 항목이 없습니다.</p>'
    )
    drafts_html = "".join(_approval_card(a) for a in drafts) or ""
    drafts_header = f"초안 — 아직 사람 큐에 안 올라옴 ({len(drafts)})"
    drafts_section = (
        f'<div class="card"><h2>{drafts_header}</h2>{drafts_html}</div>' if drafts else ""
    )

    # docs/AUTOPILOT_IMPROVEMENTS.md §9 — 새 승인 요청을 여는 폼이 대시보드엔
    # 없었다. 체크리스트는 CLI의 반복 --checklist-item과 같은 문법
    # ("LABEL:STATUS", 줄바꿈으로 구분)을 그대로 쓴다 — _parse_checklist_items()
    # 재사용.
    task_options = "".join(
        f'<option value="{_esc(str(t.get("task_id")))}">{_esc(str(t.get("task_id")))} — '
        f'{_esc(str(t.get("title")))}</option>'
        for t in (tasks or [])
    )
    kind_options = "".join(f'<option value="{k}">{k}</option>' for k in VALID_APPROVAL_KINDS)
    open_error_html = (
        f'<div class="banner critical">✗ {_esc(open_error)}</div>' if open_error else ""
    )
    checklist_label = (
        '체크리스트(한 줄에 하나, "라벨:상태" — 상태는 ok|pending|flag, 생략 시 pending)'
    )
    body_label = "본문(선택 — [NEEDS CLARIFICATION: ...] 태그 스캔용)"
    open_form = f"""
<div class="card">
  <h2>+ 새 승인 요청</h2>
  {open_error_html}
  <form class="inline" method="post" action="/approvals">
    <div class="field"><label>과제</label>
      <select name="task_id" required><option value=""></option>{task_options}</select></div>
    <div class="field"><label>종류</label>
      <select name="kind" required>{kind_options}</select></div>
    <div class="field"><label>Phase</label>
      <input type="number" name="phase" min="0" max="8" required value="0"></div>
    <div class="field"><label>제목</label>
      <input type="text" name="title" required></div>
    <div class="field" style="width:100%;"><label>{checklist_label}</label>
      <textarea name="checklist_text" placeholder="EARS 표기:ok&#10;Gate 매핑:ok"></textarea></div>
    <div class="field" style="width:100%;"><label>{body_label}</label>
      <textarea name="body_text"></textarea></div>
    <label style="font-weight:400;text-transform:none;letter-spacing:0;">
      <input type="checkbox" name="no_checklist_gate" value="1"> 체크리스트를 게이트로 쓰지 않음
      (threshold_review처럼 "할 일 목록"인 경우)</label>
    <button type="submit">승인 요청 열기</button>
  </form>
</div>"""

    return f"""
<div class="eyebrow">HITL 승인 큐</div>
<h1>승인 대기 ({len(pending)})</h1>
<div class="banner">
  "결정자"란은 자유 텍스트입니다 — 실제 사용자 인증(로그인, GitHub required review
  연동)은 아직 없습니다. 2인 승인 대상 항목은 서로 다른 이름을
  넣어야 합니다 — 같은 이름으로 두 번 승인해도 카운트되지 않습니다.
</div>
{open_form}
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
    stuck_in_draft = rejection.get("stuck_in_draft", 0)

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

    # LIMITS_T-5E1FD6.md L6 — 이 반려율은 확정된 승인만 본다. 체크리스트를
    # 못 넘겨 draft에 갇힌 항목(실제로는 반려에 가까운 상태)은 분모 밖이라
    # 위 숫자만 보면 사각지대를 놓친다 — 새 비율이 아니라 개수로만 옆에 붙인다.
    draft_note = (
        f'<p class="tm">draft 상태로 대기 중인 승인 {stuck_in_draft}건 — 위 반려율에는 '
        f'포함되지 않음(체크리스트 미충족으로 재드래프트되는 것도 실질적 반려일 수 있음)</p>'
        if stuck_in_draft else ""
    )

    return f"""
<div class="card">
  <h2>원칙6 자가점검 — 승인 반려율</h2>
  {body}
  {draft_note}
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
