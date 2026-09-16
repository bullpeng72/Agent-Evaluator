"""
agent-eval autopilot — Harness Autopilot M0 (설계서 SPEC-AP-001 §5.1·§6 M0).

    install    — .aoo/tasks/, .aoo/team.json 스켈레톤 생성 + harness-autopilot 스킬 배치
    doctor     — 헬스체크(디렉토리·스키마 확인, 미동기화 팀원 경고)
    dashboard  — 로컬 대시보드 — claims.jsonl·decisions.jsonl 실데이터 렌더(M0 완료조건)
    new-task   — 터미널에서 과제 등록(대시보드 "+ 새 과제"의 CLI 대응, 설계서 §8)
    add-member — 팀원 등록(.aoo/team.json)

이 서브커맨드는 GitHub Actions 상태머신(§3.3)이나 에이전트 러너 무인 트리거
(§3.6)를 구현하지 않는다 — M0는 "오케스트레이터가 지금 상태를 안다"까지이고,
Phase 자동 전이·승인 큐 연동은 M1 이후다. 새 채점/판정 로직은 추가하지
않는다(원칙2) — 여기서는 기존 ``load_active_claims()``/``load_decisions()``와
``autopilot_state`` 모듈의 얇은 읽기/쓰기만 감싼다.
"""
from __future__ import annotations

import argparse
import shutil
import uuid
from pathlib import Path

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    VALID_ROLES,
    add_team_member,
    create_task,
    find_member,
    load_all_tasks,
    load_team,
)

_COLOR = _supports_color()

G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""


def _ok(msg: str) -> str:
    return f"{G}✅ {msg}{R}"


def _warn(msg: str) -> str:
    return f"{Y}⚠️  {msg}{R}"


def _err(msg: str) -> str:
    return f"{RD}❌ {msg}{R}"


# Skills/harness-autopilot/SKILL.md — repo root 기준 (agent_evaluator/cli/ 에서 두 단계 위)
_SKILL_SRC = Path(__file__).resolve().parents[2] / "Skills" / "harness-autopilot" / "SKILL.md"

_M0_SCOPE_NOTE = (
    f"{D}이 명령은 M0 범위만 채운다 — GitHub Actions 상태머신·에이전트 러너 무인 트리거는\n"
    f"  아직 없다(설계서 §3.3·§3.6, M1 이후 구현).{R}"
)


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def _cmd_autopilot_install(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    team_path = root / ".aoo" / "team.json"
    platform = args.platform.upper()

    print()
    print(f"{B}Harness Autopilot — install ({platform}){R}")
    print(f"{D}{'─' * 40}{R}")

    tasks_dir.mkdir(parents=True, exist_ok=True)
    print(_ok(f"{tasks_dir}/"))

    if not team_path.is_file():
        team_path.parent.mkdir(parents=True, exist_ok=True)
        team_path.write_text('{"members": []}\n', encoding="utf-8")
        print(_ok(f"{team_path}"))
    else:
        print(f"{D}  {team_path} already exists — left untouched{R}")

    skill_dir_name = ".claude" if platform == "AC" else ".opencode"
    skill_dest = root / skill_dir_name / "skills" / "harness-autopilot"
    if _SKILL_SRC.is_file():
        skill_dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SKILL_SRC, skill_dest / "SKILL.md")
        print(_ok(f"{skill_dest / 'SKILL.md'}"))
    else:
        print(_warn(f"skill source not found: {_SKILL_SRC} (skipped)"))

    print()
    print(f"{B}Next:{R}")
    print(f"  {G}agent-eval autopilot doctor{R}")
    print(
        f"  {G}agent-eval autopilot new-task --title \"...\" --platform {platform.lower()}{R}"
    )
    print(f"  {G}agent-eval autopilot dashboard{R}")
    print()
    print(_M0_SCOPE_NOTE)
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _cmd_autopilot_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    team_path = root / ".aoo" / "team.json"
    healthy = True

    print()
    print(f"{B}Harness Autopilot — doctor{R}")
    print(f"{D}{'─' * 40}{R}")

    if tasks_dir.is_dir():
        tasks = load_all_tasks(tasks_dir)
        print(_ok(f".aoo/tasks/  — {len(tasks)} task(s)"))
        for t in tasks:
            tid = t.get("task_id", "?")
            phase = t.get("current_phase")
            plat = t.get("platform", "?")
            label = PHASE_LABELS.get(phase, str(phase))
            print(f"    {D}{tid}{R}  [{plat}]  Phase {phase} · {label}")
    else:
        healthy = False
        print(_err(".aoo/tasks/ not found — run 'agent-eval autopilot install' first"))

    if team_path.is_file():
        members = load_team(team_path)
        unsynced = [m for m in members if not m.get("synced", False)]
        print(_ok(f".aoo/team.json — {len(members)} member(s)"))
        if unsynced:
            names = ", ".join(m.get("name", m.get("id", "?")) for m in unsynced)
            print(
                _warn(
                    f"{len(unsynced)} unsynced (GitHub CODEOWNERS not updated yet): {names}"
                )
            )
    else:
        healthy = False
        print(_err(".aoo/team.json not found — run 'agent-eval autopilot install' first"))

    print()
    if healthy:
        print(_ok("Harness Autopilot M0 skeleton looks healthy."))
        return 0
    print(_err("Harness Autopilot M0 skeleton incomplete."))
    return 1


# ---------------------------------------------------------------------------
# new-task
# ---------------------------------------------------------------------------


def _cmd_autopilot_new_task(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    team_path = root / ".aoo" / "team.json"

    task_id = args.task_id or f"T-{uuid.uuid4().hex[:6].upper()}"
    owners: dict[str, str] = {}

    for role_key, name, role_label in (
        ("analysis", args.analysis, "분석"),
        ("design", args.design, "설계"),
    ):
        if not name:
            continue
        owners[role_key] = name
        member = find_member(team_path, name)
        if member is None:
            print(_warn(f"'{name}' is not registered in .aoo/team.json — assigned anyway"))
        elif role_label not in member.get("roles", []):
            print(
                _warn(
                    f"'{name}' is registered but not with role '{role_label}' "
                    f"(registered roles: {member.get('roles')}) — assigned anyway"
                )
            )
        elif not member.get("synced", False):
            print(
                _warn(
                    f"'{name}' is registered but not yet GitHub-synced — "
                    f"review routing to this person may not work (see 'autopilot doctor')"
                )
            )

    try:
        task = create_task(
            tasks_dir,
            task_id=task_id,
            title=args.title,
            platform=args.platform,
            priority=args.priority,
            owners=owners,
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Task registered: {task['task_id']} — {task['title']}"))
    print(f"  {D}platform:{R} {task['platform']}   {D}phase:{R} 0 · {task['phase_label']}")

    problem_md = root / "docs" / f"PROBLEM_{task_id}.md"
    if not problem_md.is_file():
        problem_md.parent.mkdir(parents=True, exist_ok=True)
        problem_md.write_text(
            f"# {task['title']} ({task_id})\n\n"
            "## 무엇을\n\n## 왜\n\n## 성공 기준\n\n## 제약\n\n## 범위 밖\n",
            encoding="utf-8",
        )
        print(_ok(f"PROBLEM scaffold → {problem_md}"))

    return 0


# ---------------------------------------------------------------------------
# add-member
# ---------------------------------------------------------------------------


def _cmd_autopilot_add_member(args: argparse.Namespace) -> int:
    root = Path(args.root)
    team_path = root / ".aoo" / "team.json"

    try:
        member = add_team_member(
            team_path,
            member_id=args.member_id,
            name=args.name,
            roles=args.roles,
            github=args.github,
            codeowner_scopes=args.codeowner_scopes or [],
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Team member added: {member['name']} ({member['id']})  roles={member['roles']}"))
    print(
        _warn(
            "synced=false — GitHub CODEOWNERS must be updated manually before this "
            "person's reviews actually route (design doc §4.6)."
        )
    )
    return 0


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def _cmd_autopilot_dashboard(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        import uvicorn
    except ImportError:
        print(_err("uvicorn is not installed. Install with: pip install 'agent-evaluator[serve]'"))
        return 1
    try:
        from agent_evaluator.serve.autopilot_app import create_autopilot_app
    except ImportError as exc:
        print(_err(f"Failed to load autopilot dashboard module: {exc}"))
        return 1

    app = create_autopilot_app(root=root)
    host, port = args.host, args.port

    print()
    print(f"{B}Harness Autopilot Dashboard{R}")
    print(f"{D}{'─' * 40}{R}")
    print(f"  📁  root  : {root}")
    print(f"  🌐  http://{host}:{port}")
    print()
    print(
        f"  {D}Renders real .aoo/claims.jsonl + .aoo/decisions.jsonl + tasks/team{R}"
    )
    print(
        f"  {D}(M0 scope only — the other views in the design mockup are still static).{R}"
    )
    print()
    print(f"  {D}Press Ctrl+C to stop{R}")
    print()

    if args.open:
        import threading
        import time
        import webbrowser

        def _open() -> None:
            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


# ---------------------------------------------------------------------------
# argparse 서브파서 빌더 (main.py에서 호출)
# ---------------------------------------------------------------------------


def build_autopilot_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "autopilot",
        help="Harness Autopilot — task/team registry, doctor, local dashboard (M0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Harness Autopilot M0 — multi-task / multi-team / AC·AOO foundation.\n"
            "No new scoring logic; wraps .aoo/tasks/*.json and .aoo/team.json.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval autopilot install --platform ac\n"
            "  agent-eval autopilot doctor\n"
            "  agent-eval autopilot add-member --id yj --name 유진 --role 설계\n"
            "  agent-eval autopilot new-task --title \"반품정책 자동화\" --platform ac "
            "--analysis 정민\n"
            "  agent-eval autopilot dashboard\n"
        ),
    )
    ap_sub = p.add_subparsers(dest="autopilot_command")

    install_p = ap_sub.add_parser(
        "install", help="Create .aoo/tasks/, .aoo/team.json, install the skill"
    )
    install_p.add_argument("--platform", choices=["ac", "aoo"], default="ac")
    install_p.add_argument("--root", default=".", metavar="DIR")

    doctor_p = ap_sub.add_parser("doctor", help="Health-check the M0 skeleton")
    doctor_p.add_argument("--root", default=".", metavar="DIR")

    dash_p = ap_sub.add_parser(
        "dashboard", help="Local dashboard (claims + decisions + tasks/team, M0 scope)"
    )
    dash_p.add_argument("--root", default=".", metavar="DIR")
    dash_p.add_argument("--host", default="127.0.0.1")
    dash_p.add_argument("--port", type=int, default=8766)
    dash_p.add_argument("--open", action="store_true", default=True)
    dash_p.add_argument("--no-open", dest="open", action="store_false")

    nt_p = ap_sub.add_parser("new-task", help="Register a new task (Phase 0)")
    nt_p.add_argument("--title", required=True)
    nt_p.add_argument("--platform", choices=["ac", "aoo"], default="ac")
    nt_p.add_argument("--priority", choices=["high", "normal", "low"], default="normal")
    nt_p.add_argument("--task-id", default=None, dest="task_id")
    nt_p.add_argument("--analysis", default=None, help="Analysis owner (team member id or name)")
    nt_p.add_argument("--design", default=None, help="Design owner (team member id or name)")
    nt_p.add_argument("--root", default=".", metavar="DIR")

    am_p = ap_sub.add_parser("add-member", help="Register a team member (.aoo/team.json)")
    am_p.add_argument("--id", required=True, dest="member_id")
    am_p.add_argument("--name", required=True)
    am_p.add_argument(
        "--role", action="append", required=True, dest="roles", choices=list(VALID_ROLES)
    )
    am_p.add_argument("--github", default=None)
    am_p.add_argument("--codeowner-scope", action="append", dest="codeowner_scopes")
    am_p.add_argument("--root", default=".", metavar="DIR")


def cmd_autopilot(args: argparse.Namespace) -> int:
    """autopilot 서브커맨드 핸들러 — autopilot_command에 따라 분기한다."""
    handlers = {
        "install": _cmd_autopilot_install,
        "doctor": _cmd_autopilot_doctor,
        "dashboard": _cmd_autopilot_dashboard,
        "new-task": _cmd_autopilot_new_task,
        "add-member": _cmd_autopilot_add_member,
    }
    autopilot_command = getattr(args, "autopilot_command", None)
    handler = handlers.get(autopilot_command) if autopilot_command is not None else None
    if handler is None:
        print(_err(
            "Specify an autopilot subcommand: install | doctor | dashboard | "
            "new-task | add-member"
        ))
        print(f"{D}For details: agent-eval autopilot --help{R}")
        return 1
    return handler(args)
