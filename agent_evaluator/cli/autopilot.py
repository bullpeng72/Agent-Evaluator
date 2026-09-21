"""
agent-eval autopilot — Harness Autopilot (설계서 SPEC-AP-001 §1.1 — 최종 목표는

agent-evaluator의 평가 데이터를 팀의 HITL 승인 절차에 잇는 경량 거버넌스
계층이다. Phase 0~8 전체 오케스트레이션은 범위 밖으로 동결됐다).

    install        — .aoo/tasks/, .aoo/team.json 스켈레톤 생성 + harness-autopilot 스킬 배치
    doctor         — 헬스체크(디렉토리·스키마 확인, 미동기화 팀원 경고)
    dashboard      — 로컬 대시보드 — claims/decisions/approvals 실데이터 렌더
    new-task       — 터미널에서 과제 등록(대시보드 "+ 새 과제"의 CLI 대응, 설계서 §8)
    list-tasks     — 등록된 과제 전체 목록(active만, --all로 archived/cancelled 포함)
    show-task      — 과제 하나의 상세(owners·phase_history·status)
    update-task    — 과제 필드 수정(제목·플랫폼·우선순위·담당자) — phase·status는 범위 밖
    set-task-status — 과제 생명주기(active/archived/cancelled) — current_phase와 별도 축
    add-member     — 팀원 등록(.aoo/team.json)
    remove-member  — 팀원 삭제
    update-member  — 팀원 필드 수정(역할·이름·github·synced 등)
    list-members   — 등록된 팀원 전체 목록
    phase          — Phase 전이, 옵트인으로 승인 상태에 게이트(§9.5.4 순위1).
                     ``phase policy``로 이 게이트를 프로젝트 정책 파일로 선언 가능.
                     ``phase check``로 오래 정체된 phase를 찾음(LIMITS L4)
    approvals      — HITL 승인 큐 — open/list/decide/update/cancel/scan-thresholds
    decisions      — 배포 결정 원장(``agent-eval decisions`` alias,
                     --log 기본값 .aoo/decisions.jsonl)
    skills         — 승인 이력에서 반복 체크리스트 패턴 탐지(읽기 전용) +
                     scaffold로 SKILL.md 초안 생성

GitHub Actions 상태머신·에이전트 러너 무인 트리거는 구현하지 않는다 — §1.1
재정의로 영구히 범위 밖이다(BMAD·Spec Kit·OpenHands가 이미 더 큰 규모로
푸는 문제라 원칙4와 맞지 않는다). 새 채점/판정 로직은 추가하지
않는다(원칙4 — 이미 있는 Gate A–G 채점 엔진을 다시 만들지 않는다) — 여기서는
기존 ``load_active_claims()``/``load_decisions()``와 ``autopilot_state`` 모듈의
얇은 읽기/쓰기만 감싼다.

이 모듈은 ``cli/main.py``가 직접 import하지 않는다 — entry-points 그룹
``agent_evaluator.cli_plugins``(``pyproject.toml``)와 이 파일 맨 아래의
``register()``를 통해서만 연결된다. 이유와 전체 인터페이스 경계는
``Docs/specs/SPEC-AP-001-harness-autopilot-interface.md`` 참고.
"""
from __future__ import annotations

import argparse
import shutil
import uuid
from pathlib import Path
from typing import Callable

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    VALID_APPROVAL_KINDS,
    VALID_DECISIONS,
    VALID_ROLES,
    VALID_TASK_STATUSES,
    add_team_member,
    cancel_approval,
    check_phase_staleness,
    create_task,
    decide_approval,
    detect_skill_candidates,
    find_member,
    load_all_tasks,
    load_approvals,
    load_gate_ready_policy,
    load_phase_policy,
    load_task,
    load_team,
    open_approval,
    open_threshold_reviews,
    remove_team_member,
    render_skill_stub,
    set_gate_ready_policy,
    set_phase_policy,
    set_task_status,
    transition_phase,
    update_approval_checklist,
    update_task,
    update_team_member,
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

# §9.5.4 순위5(원칙5 최소 기록) — adr_review에 자동으로 얹는 체크리스트 항목.
# 새 필드·새 판정 로직 없음 — CLI가 체크리스트 "템플릿"에 한 줄 더할 뿐이다.
_ADR_MODEL_TIER_CHECKLIST_LABEL = (
    "모델 tier 배정 근거 명시(원칙5 — Tier 1/Tier 2 배정과 그 근거를 ADR에 남긴다)"
)

_SCOPE_NOTE = (
    f"{D}Harness Autopilot은 HITL 승인 큐 — GitHub Actions 상태머신·에이전트 러너 무인\n"
    f"  트리거는 이 도구의 범위 밖이다(설계서 §1.1 최종 목표 재정의).{R}"
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
    print(_SCOPE_NOTE)
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
            phase_int = phase if isinstance(phase, int) else -1
            label = PHASE_LABELS.get(phase_int, str(phase))
            print(f"    {D}{tid}{R}  [{plat}]  Phase {phase} · {label}")

        stale_days = getattr(args, "stale_days", 7.0)
        if stale_days > 0:
            stale = check_phase_staleness(tasks_dir, stale_days=stale_days)
            for s in stale:
                print(
                    _warn(
                        f"{s['task_id']} has been in phase {s['current_phase']} "
                        f"({s['phase_label']}) for {s['days_in_phase']:.1f} day(s) "
                        f"(since {s['entered_at']}) — verify this still matches "
                        f"the actual work, or transition it (docs/"
                        f"AUTOPILOT_IMPROVEMENTS.md §3, LIMITS L4)."
                    )
                )
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
        print(_ok("Harness Autopilot installation looks healthy."))
        return 0
    print(_err("Harness Autopilot installation incomplete."))
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
        ("development", getattr(args, "development", None), "개발"),
        ("qa", getattr(args, "qa", None), "QA"),
        ("pm", getattr(args, "pm", None), "PM"),
        ("security", getattr(args, "security", None), "보안"),
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


def _cmd_autopilot_remove_member(args: argparse.Namespace) -> int:
    root = Path(args.root)
    team_path = root / ".aoo" / "team.json"

    try:
        removed = remove_team_member(team_path, args.member_id)
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Team member removed: {removed['name']} ({removed['id']})"))
    return 0


def _cmd_autopilot_update_member(args: argparse.Namespace) -> int:
    root = Path(args.root)
    team_path = root / ".aoo" / "team.json"

    synced = None
    if args.mark_synced:
        synced = True
    elif args.mark_unsynced:
        synced = False

    try:
        member = update_team_member(
            team_path, args.member_id,
            name=args.name, roles=args.roles, github=args.github,
            codeowner_scopes=args.codeowner_scopes, synced=synced,
            changed_by=getattr(args, "changed_by", None),
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(
        _ok(
            f"Team member updated: {member['name']} ({member['id']})  "
            f"roles={member['roles']}  synced={member['synced']}"
        )
    )
    return 0


def _cmd_autopilot_list_members(args: argparse.Namespace) -> int:
    root = Path(args.root)
    team_path = root / ".aoo" / "team.json"
    members = load_team(team_path)

    if not members:
        print(f"{D}No team members registered ({team_path}){R}")
        return 0

    print(f"{B}Team — {team_path}{R}")
    for m in members:
        sync_note = "" if m.get("synced") else f"  {Y}(unsynced){R}"
        print(
            f"  {m.get('id', '?'):<12} {m.get('name', '?'):<12} "
            f"roles={m.get('roles', [])}  github={m.get('github')}{sync_note}"
        )
    return 0


# ---------------------------------------------------------------------------
# tasks — read-only listing (SPEC-AP-001 백로그 §2, add-task는 new-task)
# ---------------------------------------------------------------------------


def _cmd_autopilot_list_tasks(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    show_all = getattr(args, "all", False)
    tasks = load_all_tasks(tasks_dir)
    if not show_all:
        tasks = [t for t in tasks if t.get("status", "active") == "active"]

    if not tasks:
        label = "" if show_all else " active"
        print(f"{D}No{label} tasks registered ({tasks_dir}){R}")
        return 0

    print(f"{B}Tasks — {tasks_dir}{R}")
    for t in sorted(tasks, key=lambda x: x.get("task_id", "")):
        phase = t.get("current_phase")
        phase_int = phase if isinstance(phase, int) else -1
        label = PHASE_LABELS.get(phase_int, str(phase))
        status = t.get("status", "active")
        status_note = f"  {Y}[{status}]{R}" if status != "active" else ""
        print(
            f"  {t.get('task_id', '?'):<14} [{t.get('platform', '?')}]  "
            f"Phase {phase} · {label}{status_note}  {D}{t.get('title', '')}{R}"
        )
    return 0


def _cmd_autopilot_set_task_status(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"

    try:
        task = set_task_status(
            tasks_dir, args.task_id, args.status, reason=args.reason,
            changed_by=getattr(args, "changed_by", None),
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"{task['task_id']} status → {task['status']}"))
    return 0


def _cmd_autopilot_show_task(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    task = load_task(tasks_dir, args.task_id)

    if task is None:
        print(_err(f"task not found: {args.task_id}"))
        return 1

    phase = task.get("current_phase")
    phase_int = phase if isinstance(phase, int) else -1
    label = PHASE_LABELS.get(phase_int, str(phase))
    print(f"{B}{task.get('task_id')}{R} — {task.get('title', '')}")
    print(f"  {D}platform:{R} {task.get('platform')}   {D}priority:{R} {task.get('priority')}")
    print(f"  {D}phase:{R} {phase} · {label}")
    status = task.get("status", "active")
    if status != "active":
        reason = task.get("status_reason")
        reason_note = f" — {reason}" if reason else ""
        print(f"  {D}status:{R} {Y}{status}{R}{reason_note}")
    owners = task.get("owners") or {}
    if owners:
        print(f"  {D}owners:{R} " + ", ".join(f"{k}={v}" for k, v in owners.items()))
    print(f"  {D}phase history:{R}")
    for h in task.get("phase_history", []):
        exited = h.get("exited_at") or f"{Y}(current){R}"
        print(f"    phase {h.get('phase')}  {h.get('entered_at')} → {exited}")
    return 0


_TASK_OWNER_ROLES = ("analysis", "design", "development", "qa", "pm", "security")


def _cmd_autopilot_update_task(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"

    # owners는 update_task()에서 통째로 대체되므로(update_team_member()의
    # roles와 같은 방식), 여기서는 기존 owners에서 주어진 역할만 덮어써 넘긴다
    # — 그래야 "제목만 고치기"가 담당자 전체를 지우지 않는다. 빈 문자열은
    # 명시적 해제로 취급한다.
    owners_given = any(getattr(args, role, None) is not None for role in _TASK_OWNER_ROLES)
    owners = None
    if owners_given:
        existing = load_task(tasks_dir, args.task_id)
        if existing is None:
            print(_err(f"task not found: {args.task_id}"))
            return 1
        owners = dict(existing.get("owners") or {})
        for role_key in _TASK_OWNER_ROLES:
            value = getattr(args, role_key, None)
            if value is None:
                continue
            if value == "":
                owners.pop(role_key, None)
            else:
                owners[role_key] = value

    try:
        task = update_task(
            tasks_dir, args.task_id,
            title=args.title, platform=args.platform, priority=args.priority,
            owners=owners, changed_by=getattr(args, "changed_by", None),
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Task updated: {task['task_id']} — {task['title']}"))
    print(
        f"  {D}platform:{R} {task['platform']}   {D}priority:{R} {task['priority']}   "
        f"{D}owners:{R} {task.get('owners') or {}}"
    )
    return 0


# ---------------------------------------------------------------------------
# phase transition — §9.5.4 순위1 (opt-in approval gate)
# ---------------------------------------------------------------------------


def _cmd_autopilot_phase_transition(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    approvals_path = root / ".aoo" / "approvals.jsonl"
    decisions_path = root / ".aoo" / "decisions.jsonl"
    policy_path = root / ".aoo" / "phase_policy.json"

    # docs/AUTOPILOT_IMPROVEMENTS.md §3 — transition_phase()는 역행이나 여러
    # 단계 건너뛰기를 그 자체로 막지 않는다(승인 조건 검사와 별개). 정당한
    # 되돌리기(예: 조기 진행 판단 취소)도 있을 수 있어 하드 차단은 안 하지만,
    # 최소한 사람 눈에 띄게는 한다 — 실수로 역행한 걸 아무도 못 알아채는
    # 것과, 알고도 역행하는 것은 다른 상황이다.
    existing_task = load_task(tasks_dir, args.task_id)
    if existing_task is not None:
        current_phase = existing_task.get("current_phase")
        if isinstance(current_phase, int) and args.new_phase < current_phase:
            print(
                _warn(
                    f"phase {args.new_phase} is BEHIND the current phase "
                    f"{current_phase} — proceeding anyway (not blocked)."
                )
            )
        elif isinstance(current_phase, int) and args.new_phase > current_phase + 1:
            print(
                _warn(
                    f"skipping from phase {current_phase} to {args.new_phase} "
                    f"({args.new_phase - current_phase - 1} phase(s) skipped) — "
                    f"proceeding anyway (not blocked)."
                )
            )

    require_approval = getattr(args, "require_approval", None)
    from_policy = False
    if require_approval is None:
        policy = load_phase_policy(policy_path)
        require_approval = policy.get(args.new_phase)
        from_policy = require_approval is not None

    # docs/AUTOPILOT_IMPROVEMENTS.md §16 — require_approval_kind와 나란히,
    # 이번엔 사람 승인이 아니라 Harness Gate A–G 판정 자체(decisions.jsonl)를
    # 조건으로 건다. --require-gate-ready {yes,no}가 명시되면 그 값을 그대로
    # 쓰고, 생략되면(None) phase_policy.json의 gate_ready 정책을 따른다 —
    # require_approval과 완전히 같은 "정책에 맡김" 편의 패턴.
    require_gate_ready_arg = getattr(args, "require_gate_ready", None)
    gate_ready_from_policy = False
    if require_gate_ready_arg is None:
        require_gate_ready = args.new_phase in load_gate_ready_policy(policy_path)
        gate_ready_from_policy = require_gate_ready
    else:
        require_gate_ready = require_gate_ready_arg == "yes"

    try:
        task = transition_phase(
            tasks_dir,
            args.task_id,
            args.new_phase,
            mode=args.mode,
            approved_by=args.approved_by,
            approvals_path=approvals_path if require_approval else None,
            required_approval_kind=require_approval,
            require_gate_ready=require_gate_ready,
            decisions_path=decisions_path if require_gate_ready else None,
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(
        _ok(
            f"{task['task_id']} → Phase {task['current_phase']} · {task['phase_label']}"
        )
    )
    if require_approval:
        source = "phase policy" if from_policy else "--require-approval"
        print(
            f"  {D}Gated on an approved '{require_approval}' approval "
            f"({source}) — satisfied.{R}"
        )
    if require_gate_ready:
        source = "phase policy" if gate_ready_from_policy else "--require-gate-ready"
        print(f"  {D}Gated on the latest Harness Gate run being ready ({source}) — satisfied.{R}")
    return 0


def _cmd_autopilot_phase_policy_set(args: argparse.Namespace) -> int:
    root = Path(args.root)
    policy_path = root / ".aoo" / "phase_policy.json"

    kind = None if args.clear else args.require_approval
    approval_touched = args.clear or kind is not None
    gate_ready_touched = getattr(args, "require_gate_ready", False) or getattr(
        args, "clear_gate_ready", False
    )

    if not approval_touched and not gate_ready_touched:
        print(
            _err(
                "Specify --require-approval KIND / --clear, and/or "
                "--require-gate-ready / --clear-gate-ready"
            )
        )
        return 1

    if approval_touched:
        try:
            set_phase_policy(policy_path, args.new_phase, kind)
        except ValueError as exc:
            print(_err(str(exc)))
            return 1
        if kind is None:
            print(_ok(f"Cleared the approval policy for phase {args.new_phase}"))
        else:
            print(
                _ok(
                    f"Phase {args.new_phase} now requires an approved '{kind}' approval "
                    f"on every 'phase transition' (until cleared or --require-approval "
                    f"is passed explicitly)"
                )
            )

    if gate_ready_touched:
        # docs/AUTOPILOT_IMPROVEMENTS.md §16 — 승인 kind와 독립적인 축이라
        # 같은 --to로 둘 다, 또는 한쪽만 건드릴 수 있다.
        required = bool(args.require_gate_ready)
        set_gate_ready_policy(policy_path, args.new_phase, required)
        if required:
            print(
                _ok(
                    f"Phase {args.new_phase} now also requires the latest Harness Gate "
                    f"run to be ready on every 'phase transition' (until cleared or "
                    f"--require-gate-ready no is passed explicitly)"
                )
            )
        else:
            print(_ok(f"Cleared the gate-ready policy for phase {args.new_phase}"))
    return 0


def _cmd_autopilot_phase_policy_show(args: argparse.Namespace) -> int:
    root = Path(args.root)
    policy_path = root / ".aoo" / "phase_policy.json"
    policy = load_phase_policy(policy_path)
    gate_ready_policy = load_gate_ready_policy(policy_path)

    if not policy and not gate_ready_policy:
        print(f"{D}No phase policy configured ({policy_path}){R}")
        return 0

    print(f"{B}Phase policy — {policy_path}{R}")
    for phase_num in sorted(set(policy) | gate_ready_policy):
        label = PHASE_LABELS.get(phase_num, str(phase_num))
        parts = []
        if phase_num in policy:
            parts.append(f"requires {policy[phase_num]}")
        if phase_num in gate_ready_policy:
            parts.append("requires gate-ready")
        print(f"  Phase {phase_num} ({label})  " + "  ·  ".join(parts))
    return 0


def _cmd_autopilot_phase_policy(args: argparse.Namespace) -> int:
    handlers = {
        "set": _cmd_autopilot_phase_policy_set,
        "show": _cmd_autopilot_phase_policy_show,
    }
    policy_command = getattr(args, "policy_command", None)
    handler = handlers.get(policy_command) if policy_command is not None else None
    if handler is None:
        print(_err("Specify a policy subcommand: set | show"))
        return 1
    return handler(args)


def _cmd_autopilot_phase_check(args: argparse.Namespace) -> int:
    root = Path(args.root)
    tasks_dir = root / ".aoo" / "tasks"
    stale = check_phase_staleness(tasks_dir, stale_days=args.stale_days)

    if not stale:
        print(f"{D}No task has been stuck in its current phase for "
              f"{args.stale_days:g}+ day(s).{R}")
        return 0

    print(f"{B}Phase staleness — {tasks_dir} (threshold: {args.stale_days:g} day(s)){R}")
    for s in stale:
        print(
            f"  {Y}{s['task_id']:<14}{R} phase {s['current_phase']} · "
            f"{s['phase_label']}  {D}{s['days_in_phase']:.1f}d since "
            f"{s['entered_at']}{R}"
        )
    return 0


def _cmd_autopilot_phase(args: argparse.Namespace) -> int:
    handlers = {
        "transition": _cmd_autopilot_phase_transition,
        "policy": _cmd_autopilot_phase_policy,
        "check": _cmd_autopilot_phase_check,
    }
    phase_command = getattr(args, "phase_command", None)
    handler = handlers.get(phase_command) if phase_command is not None else None
    if handler is None:
        print(_err("Specify a phase subcommand: transition | policy | check"))
        return 1
    return handler(args)


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
        f"  {D}(server-rendered HTML, no JS — task board · team · approvals · ops){R}"
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
# approvals — .aoo/approvals.jsonl (§4.2 승인 큐, §3.4 체크리스트 자동채점)
# ---------------------------------------------------------------------------


_VALID_CHECKLIST_STATUSES = ("ok", "pending", "flag")


def _parse_checklist_items(raw_items: list[str] | None) -> list[dict[str, str]]:
    """``--checklist-item "라벨:상태"`` 반복 인자를 파싱한다. 상태 생략 시 pending.

    **마지막** 콜론에서 분리한다 — 첫 콜론에서 자르면 "역할: 설명:ok" 같은
    라벨(콜론이 라벨 안에도 있는 경우)의 라벨이 잘리는 실제 버그가 있었다
    (AOO 실습서 Ch 35, docs/AUTOPILOT_IMPROVEMENTS.md §4). ``STATUS``가
    ``ok``/``pending``/``flag``가 아니면 조용히 통과시키지 않고 바로
    거부한다 — 오타 하나가 그 항목을 영원히 차단 상태로 묻어 두는 걸
    막는다.
    """
    items: list[dict[str, str]] = []
    for raw in raw_items or []:
        if ":" in raw:
            label, _, status = raw.rpartition(":")
        else:
            label, status = raw, ""
        status = status.strip() or "pending"
        if status not in _VALID_CHECKLIST_STATUSES:
            raise ValueError(
                f"invalid checklist status {status!r} in {raw!r} "
                f"(expected one of {_VALID_CHECKLIST_STATUSES})"
            )
        items.append({"label": label.strip(), "status": status})
    return items


def _cmd_autopilot_approvals_open(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"

    body_text = None
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.is_file():
            print(_err(f"--body-file not found: {body_path}"))
            return 1
        body_text = body_path.read_text(encoding="utf-8")

    try:
        checklist = _parse_checklist_items(args.checklist_item)
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    added_model_tier_item = False
    if args.kind == "adr_review" and not any(
        "모델 tier" in item.get("label", "") for item in checklist
    ):
        checklist.append({"label": _ADR_MODEL_TIER_CHECKLIST_LABEL, "status": "pending"})
        added_model_tier_item = True

    try:
        approval = open_approval(
            approvals_path,
            task_id=args.task_id,
            kind=args.kind,
            phase=args.phase,
            title=args.title,
            checklist=checklist,
            body_text=body_text,
            required_approvals=getattr(args, "required_approvals", None),
            gate_on_checklist=not getattr(args, "no_checklist_gate", False),
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    if added_model_tier_item:
        print(
            f"  {D}adr_review 기본 체크리스트 항목 자동 추가됨(원칙5, §9.5.4 순위5): "
            f"\"{_ADR_MODEL_TIER_CHECKLIST_LABEL}\" — 이미 이 항목을 --checklist-item으로 "
            f"직접 넣었다면 자동 추가되지 않는다.{R}"
        )
    if approval["required_approvals"] > 1:
        print(
            f"  {D}Requires {approval['required_approvals']} distinct approvers "
            f"before this counts as approved (kind={approval['kind']}).{R}"
        )
    if approval["status"] == "pending":
        print(_ok(f"Approval opened and ready for review: {approval['id']}"))
    else:
        print(_warn(f"Approval opened as DRAFT (not yet ready for review): {approval['id']}"))
        if approval["needs_clarification"]:
            print(f"  {D}NEEDS CLARIFICATION ({len(approval['needs_clarification'])}):{R}")
            for nc in approval["needs_clarification"]:
                print(f"    - {nc}")
        blocking = approval["checklist_score"]["blocking"]
        if blocking:
            print(f"  {D}Checklist not satisfied ({len(blocking)}):{R}")
            for b in blocking:
                print(f"    - [{b.get('status')}] {b.get('label')}")
        print(
            f"  {D}This stays out of the human review queue until resolved "
            f"(design doc §3.4 — no review request is sent).{R}"
        )
    return 0


def _cmd_autopilot_approvals_list(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"
    all_approvals = load_approvals(approvals_path)
    approvals = all_approvals if args.all else [
        a for a in all_approvals if a.get("status") == "pending"
    ]
    # §4 — draft가 기본 목록(pending만) 뒤에 조용히 쌓이는 공백. --all이면
    # 이미 보고 있으니 nudge가 불필요하다.
    n_draft = 0 if args.all else sum(1 for a in all_approvals if a.get("status") == "draft")

    label = "all" if args.all else "pending"
    if not approvals:
        print(f"{D}No {label} approvals ({approvals_path}){R}")
        if n_draft:
            print(
                _warn(
                    f"{n_draft} draft approval(s) exist but aren't shown here "
                    f"(they stay out of the review queue until their checklist "
                    f"is satisfied) — run with --all to see them."
                )
            )
        return 0

    print(f"{B}Approvals ({label}) — {approvals_path}{R}")
    for a in sorted(approvals, key=lambda x: x.get("opened_at", "")):
        status_color = {
            "pending": Y, "draft": D, "approved": G,
            "rejected": RD, "changes_requested": RD, "cancelled": D,
        }.get(a.get("status", ""), "")
        print(
            f"  {status_color}{a.get('status'):>18}{R}  {a.get('id')}  "
            f"[{a.get('task_id')}] {a.get('title')}  "
            f"{D}({a.get('kind')}, phase {a.get('phase')}){R}"
        )
    if n_draft:
        print(f"{D}({n_draft} draft approval(s) not shown — run with --all){R}")
    return 0


def _cmd_autopilot_approvals_decide(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"

    try:
        decided = decide_approval(
            approvals_path, args.approval_id,
            decision=args.decision, decided_by=args.decided_by, rationale=args.rationale,
        )
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    required = decided.get("required_approvals", 1)
    if decided["status"] == "pending" and required > 1:
        recorded = decided.get("approvals_recorded") or []
        who = ", ".join(r.get("by", "") for r in recorded)
        print(_warn(
            f"Approval recorded for {decided['id']} ({len(recorded)}/{required}: {who}) — "
            f"still needs {required - len(recorded)} more distinct approver(s)."
        ))
    else:
        print(
            _ok(f"Recorded: {decided['decision']} on {decided['id']} by {decided['decided_by']}")
        )
    return 0


def _cmd_autopilot_approvals_update(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"

    try:
        updates = _parse_checklist_items(args.checklist_item)
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    try:
        updated = update_approval_checklist(approvals_path, args.approval_id, updates)
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Checklist updated on {updated['id']} ({len(updates)} item(s))"))
    if updated["status"] == "pending":
        print(_ok(f"Now ready for review: {updated['id']}"))
    else:
        blocking = updated["checklist_score"]["blocking"]
        print(_warn(f"Still draft — {len(blocking)} item(s) not yet ok:"))
        for b in blocking:
            print(f"    - [{b.get('status')}] {b.get('label')}")
    return 0


def _cmd_autopilot_approvals_cancel(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"

    try:
        cancelled = cancel_approval(approvals_path, args.approval_id, reason=args.reason)
    except ValueError as exc:
        print(_err(str(exc)))
        return 1

    print(_ok(f"Cancelled: {cancelled['id']}"))
    return 0


def _cmd_autopilot_approvals_scan_thresholds(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"
    decisions_path = root / ".aoo" / "decisions.jsonl"

    opened = open_threshold_reviews(
        approvals_path, decisions_path, min_occurrences=args.min_occurrences
    )
    if not opened:
        print(f"{D}No repeated exit-75 pattern found "
              f"(threshold: {args.min_occurrences}+, or already under review).{R}")
        return 0

    for a in opened:
        print(_warn(f"Threshold review opened: {a['id']} — {a['title']}"))
    print(f"{D}Run the review with the threshold-realism-review skill "
          f"(설계서 §30/§31.6) — a 4-step pipeline, not an automatic change.{R}")
    return 0


def _cmd_autopilot_approvals(args: argparse.Namespace) -> int:
    handlers = {
        "open": _cmd_autopilot_approvals_open,
        "list": _cmd_autopilot_approvals_list,
        "decide": _cmd_autopilot_approvals_decide,
        "update": _cmd_autopilot_approvals_update,
        "cancel": _cmd_autopilot_approvals_cancel,
        "scan-thresholds": _cmd_autopilot_approvals_scan_thresholds,
    }
    approvals_command = getattr(args, "approvals_command", None)
    handler = handlers.get(approvals_command) if approvals_command is not None else None
    if handler is None:
        print(_err(
            "Specify an approvals subcommand: open | list | decide | update | "
            "cancel | scan-thresholds"
        ))
        return 1
    return handler(args)


# ---------------------------------------------------------------------------
# argparse 서브파서 빌더 (main.py에서 호출)
# ---------------------------------------------------------------------------


def build_autopilot_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "autopilot",
        help="Harness Autopilot — HITL approval queue on top of agent-evaluator's "
             "own Gate/decision data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Harness Autopilot — a lightweight governance layer that connects "
            "agent-evaluator's evaluation data (Gate scores, exit-75 holds, team "
            "claims) to your team's HITL approval process. Multi-task / multi-team / "
            "AC·AOO foundation. No new scoring logic; wraps .aoo/tasks/*.json, "
            "team.json and approvals.jsonl.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval autopilot install --platform ac\n"
            "  agent-eval autopilot doctor --stale-days 7\n"
            "  agent-eval autopilot add-member --id yj --name 유진 --role 설계\n"
            "  agent-eval autopilot new-task --title \"반품정책 자동화\" --platform ac "
            "--analysis 정민 --design 유진\n"
            "  agent-eval autopilot list-tasks --all\n"
            "  agent-eval autopilot update-task ST-014 --title \"새 제목\" --priority high\n"
            "  agent-eval autopilot set-task-status ST-014 --status archived "
            "--reason \"shipped\"\n"
            "  agent-eval autopilot phase transition --task ST-014 --to 2 "
            "--require-approval spec_review\n"
            "  agent-eval autopilot phase policy set --to 2 --require-approval spec_review\n"
            "  agent-eval autopilot phase check --stale-days 7\n"
            "  agent-eval autopilot approvals open --task ST-014 --kind spec_review "
            "--phase 1 \\\n"
            "      --title \"ST-014 SPEC 검토\" --body-file docs/SPEC_ST-014.md \\\n"
            "      --checklist-item \"EARS 표기:ok\" --checklist-item \"Gate 매핑:ok\"\n"
            "  agent-eval autopilot approvals list\n"
            "  agent-eval autopilot approvals decide ap-a1b2c3d4 --decision approved "
            "--by pm-park\n"
            "  agent-eval autopilot approvals cancel ap-a1b2c3d4 --reason \"no longer needed\"\n"
            "  agent-eval autopilot decisions list --pending\n"
            "  agent-eval autopilot skills detect\n"
            "  agent-eval autopilot skills scaffold --name my-new-skill\n"
            "  agent-eval autopilot dashboard\n"
        ),
    )
    ap_sub = p.add_subparsers(dest="autopilot_command")

    install_p = ap_sub.add_parser(
        "install", help="Create .aoo/tasks/, .aoo/team.json, install the skill"
    )
    install_p.add_argument("--platform", choices=["ac", "aoo"], default="ac")
    install_p.add_argument("--root", default=".", metavar="DIR")

    doctor_p = ap_sub.add_parser(
        "doctor",
        help="Health-check the Autopilot installation (also warns on stale phases)",
    )
    doctor_p.add_argument("--root", default=".", metavar="DIR")
    doctor_p.add_argument(
        "--stale-days", type=float, default=7.0, dest="stale_days",
        help="Warn when an active task has sat in its current phase this many "
             "days or longer (default: 7; 0 disables the check)",
    )

    dash_p = ap_sub.add_parser(
        "dashboard", help="Local dashboard (task board · team · approvals · ops)"
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
    nt_p.add_argument(
        "--development", default=None, help="Development owner (team member id or name)"
    )
    nt_p.add_argument("--qa", default=None, help="QA owner (team member id or name)")
    nt_p.add_argument("--pm", default=None, help="PM owner (team member id or name)")
    nt_p.add_argument("--security", default=None, help="Security owner (team member id or name)")
    nt_p.add_argument("--root", default=".", metavar="DIR")

    lt_p = ap_sub.add_parser(
        "list-tasks", help="List registered tasks (active only by default)"
    )
    lt_p.add_argument(
        "--all", action="store_true",
        help="Include archived/cancelled tasks (active-only by default)",
    )
    lt_p.add_argument("--root", default=".", metavar="DIR")

    st_p = ap_sub.add_parser(
        "show-task", help="Show one task's detail (owners, phase history, status)"
    )
    st_p.add_argument("task_id")
    st_p.add_argument("--root", default=".", metavar="DIR")

    ut_p = ap_sub.add_parser(
        "update-task",
        help="Edit a task's title/platform/priority/owners "
             "(not phase or status — see 'phase transition' / 'set-task-status')",
    )
    ut_p.add_argument("task_id")
    ut_p.add_argument("--title", default=None)
    ut_p.add_argument("--platform", default=None, choices=["ac", "aoo"])
    ut_p.add_argument("--priority", default=None, choices=["high", "normal", "low"])
    ut_p.add_argument(
        "--analysis", default=None, metavar="OWNER",
        help="Analysis owner (team member id or name); pass '' to clear",
    )
    ut_p.add_argument("--design", default=None, metavar="OWNER", help="Design owner; '' to clear")
    ut_p.add_argument(
        "--development", default=None, metavar="OWNER",
        help="Development owner; '' to clear",
    )
    ut_p.add_argument("--qa", default=None, metavar="OWNER", help="QA owner; '' to clear")
    ut_p.add_argument("--pm", default=None, metavar="OWNER", help="PM owner; '' to clear")
    ut_p.add_argument(
        "--security", default=None, metavar="OWNER", help="Security owner; '' to clear"
    )
    ut_p.add_argument(
        "--by", default=None, dest="changed_by", metavar="NAME",
        help="Who made this edit (optional, free text — recorded as last_updated_by)",
    )
    ut_p.add_argument("--root", default=".", metavar="DIR")

    sts_p = ap_sub.add_parser(
        "set-task-status", help="Mark a task active/archived/cancelled"
    )
    sts_p.add_argument("task_id")
    sts_p.add_argument("--status", required=True, choices=list(VALID_TASK_STATUSES))
    sts_p.add_argument("--reason", default=None)
    sts_p.add_argument(
        "--by", default=None, dest="changed_by", metavar="NAME",
        help="Who made this change (optional, free text — recorded as status_changed_by)",
    )
    sts_p.add_argument("--root", default=".", metavar="DIR")

    am_p = ap_sub.add_parser("add-member", help="Register a team member (.aoo/team.json)")
    am_p.add_argument("--id", required=True, dest="member_id")
    am_p.add_argument("--name", required=True)
    am_p.add_argument(
        "--role", action="append", required=True, dest="roles", choices=list(VALID_ROLES)
    )
    am_p.add_argument("--github", default=None)
    am_p.add_argument("--codeowner-scope", action="append", dest="codeowner_scopes")
    am_p.add_argument("--root", default=".", metavar="DIR")

    rm_p = ap_sub.add_parser("remove-member", help="Remove a team member (.aoo/team.json)")
    rm_p.add_argument("--id", required=True, dest="member_id")
    rm_p.add_argument("--root", default=".", metavar="DIR")

    um_p = ap_sub.add_parser(
        "update-member", help="Update a registered team member's fields"
    )
    um_p.add_argument("--id", required=True, dest="member_id")
    um_p.add_argument("--name", default=None)
    um_p.add_argument("--role", action="append", dest="roles", choices=list(VALID_ROLES))
    um_p.add_argument("--github", default=None)
    um_p.add_argument("--codeowner-scope", action="append", dest="codeowner_scopes")
    um_p.add_argument(
        "--mark-synced", action="store_true",
        help="Mark GitHub CODEOWNERS as updated for this person",
    )
    um_p.add_argument(
        "--mark-unsynced", action="store_true",
        help="Mark GitHub CODEOWNERS as NOT updated for this person",
    )
    um_p.add_argument(
        "--by", default=None, dest="changed_by", metavar="NAME",
        help="Who made this edit (optional, free text — recorded as last_updated_by)",
    )
    um_p.add_argument("--root", default=".", metavar="DIR")

    lm_p = ap_sub.add_parser("list-members", help="List all registered team members")
    lm_p.add_argument("--root", default=".", metavar="DIR")

    ph_p = ap_sub.add_parser(
        "phase",
        help="Task phase transitions + policy + staleness check "
             "(.aoo/tasks/<id>.json current_phase)",
    )
    ph_sub = ph_p.add_subparsers(dest="phase_command")
    pht_p = ph_sub.add_parser(
        "transition",
        help="Move a task to a new phase — optionally gated on an approved approval",
    )
    pht_p.add_argument("--task", required=True, dest="task_id")
    pht_p.add_argument("--to", required=True, type=int, dest="new_phase")
    pht_p.add_argument("--mode", default="auto", choices=["auto", "hitl"])
    pht_p.add_argument("--approved-by", default=None, dest="approved_by")
    pht_p.add_argument(
        "--require-approval", default=None, dest="require_approval",
        choices=list(VALID_APPROVAL_KINDS),
        help="Refuse the transition unless an approval of this kind is 'approved' "
             "for this task (§9.5.4 순위1 — opt-in, no gate by default)",
    )
    pht_p.add_argument(
        "--require-gate-ready", default=None, dest="require_gate_ready", choices=["yes", "no"],
        help="Refuse the transition unless the latest Harness Gate run "
             "(.aoo/decisions.jsonl) has verdict_level='ready' (or a human recorded "
             "accepted/overridden for it) — independent of --require-approval "
             "(docs/AUTOPILOT_IMPROVEMENTS.md §16). Omit to fall back to the phase "
             "policy's gate_ready setting; an explicit value here always overrides it.",
    )
    pht_p.add_argument("--root", default=".", metavar="DIR")

    php_p = ph_sub.add_parser(
        "policy",
        help="Declare a project-wide phase gate instead of a per-call --require-approval",
    )
    php_sub = php_p.add_subparsers(dest="policy_command")
    phps_p = php_sub.add_parser(
        "set", help="Require an approval kind for every transition into a phase"
    )
    phps_p.add_argument("--to", required=True, type=int, dest="new_phase")
    phps_p.add_argument(
        "--require-approval", default=None, dest="require_approval",
        choices=list(VALID_APPROVAL_KINDS),
    )
    phps_p.add_argument("--clear", action="store_true", help="Remove the policy for this phase")
    phps_p.add_argument(
        "--require-gate-ready", action="store_true", dest="require_gate_ready",
        help="Also require the latest Harness Gate run to be ready for every "
             "transition into this phase (docs/AUTOPILOT_IMPROVEMENTS.md §16) — "
             "independent of --require-approval, can be set alone or together with it",
    )
    phps_p.add_argument(
        "--clear-gate-ready", action="store_true", dest="clear_gate_ready",
        help="Remove the gate-ready policy for this phase",
    )
    phps_p.add_argument("--root", default=".", metavar="DIR")

    phpw_p = php_sub.add_parser("show", help="Show the current phase policy")
    phpw_p.add_argument("--root", default=".", metavar="DIR")

    phc_p = ph_sub.add_parser(
        "check",
        help="List active tasks stuck in their current phase (no forgotten "
             "transition, LIMITS L4 — pure elapsed-time signal, read-only)",
    )
    phc_p.add_argument(
        "--stale-days", type=float, default=7.0, dest="stale_days",
        help="Flag a task that has been in its current phase this many days "
             "or longer (default: 7)",
    )
    phc_p.add_argument("--root", default=".", metavar="DIR")

    dec_p = ap_sub.add_parser(
        "decisions",
        help="Deploy-decision ledger (alias for `agent-eval decisions`, "
             "defaults --log to .aoo/decisions.jsonl)",
    )
    dec_sub = dec_p.add_subparsers(dest="decisions_command", metavar="{list,record}")
    decl_p = dec_sub.add_parser("list", help="List gate runs + outcomes")
    decl_p.add_argument("--log", default=None, help="Override .aoo/decisions.jsonl")
    decl_p.add_argument("--pending", action="store_true",
                        help="Only gate runs with no recorded outcome yet")
    decl_p.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit the summary as JSON")
    decl_p.add_argument("--root", default=".", metavar="DIR")
    decr_p = dec_sub.add_parser("record", help="Append a human decision")
    decr_p.add_argument("--log", default=None, help="Override .aoo/decisions.jsonl")
    decr_p.add_argument("--outcome", required=True,
                        choices=["accepted", "held", "overridden", "rejected"])
    decr_p.add_argument("--by", required=True, dest="decided_by", metavar="NAME")
    decr_p.add_argument("--rationale", metavar="TEXT", default=None)
    decr_p.add_argument("--gate-run-id", metavar="ID", dest="gate_run_id", default=None,
                        help="Required when more than one gate_run is pending")
    decr_p.add_argument("--root", default=".", metavar="DIR")

    ap_p = ap_sub.add_parser(
        "approvals",
        help="HITL approval queue (.aoo/approvals.jsonl) — "
             "open/list/decide/update/cancel/scan-thresholds",
    )
    ap_ap_sub = ap_p.add_subparsers(dest="approvals_command")

    apo_p = ap_ap_sub.add_parser(
        "open", help="Open an approval — auto-scores the checklist (§3.4)"
    )
    apo_p.add_argument("--task", required=True, dest="task_id")
    apo_p.add_argument("--kind", required=True, choices=list(VALID_APPROVAL_KINDS))
    apo_p.add_argument("--phase", required=True, type=int)
    apo_p.add_argument("--title", required=True)
    apo_p.add_argument(
        "--body-file", default=None, dest="body_file",
        help="Draft text file to scan for [NEEDS CLARIFICATION: ...] tags",
    )
    apo_p.add_argument(
        "--checklist-item", action="append", dest="checklist_item", metavar="LABEL:STATUS",
        help="Repeatable. STATUS is ok|pending|flag (default: pending if omitted)",
    )
    apo_p.add_argument(
        "--required-approvals", type=int, default=None, dest="required_approvals",
        help="Distinct approvers needed before this counts as approved "
             "(default: 2 for deploy/release_hold, 1 otherwise)",
    )
    apo_p.add_argument(
        "--no-checklist-gate", action="store_true", dest="no_checklist_gate",
        help="Checklist is shown but does not block review (use when the checklist "
             "is a follow-up procedure list, not an entry condition — this is what "
             "'scan-thresholds' uses internally for threshold_review; without this "
             "flag a manually-opened approval of the same kind stays gated, "
             "docs/AUTOPILOT_IMPROVEMENTS.md §Appendix-M-finding-1)",
    )
    apo_p.add_argument("--root", default=".", metavar="DIR")

    apl_p = ap_ap_sub.add_parser("list", help="List approvals (pending by default)")
    apl_p.add_argument("--all", action="store_true", help="Include draft/decided items")
    apl_p.add_argument("--root", default=".", metavar="DIR")

    apd_p = ap_ap_sub.add_parser("decide", help="Record a human decision on an approval")
    apd_p.add_argument("approval_id")
    apd_p.add_argument("--decision", required=True, choices=list(VALID_DECISIONS))
    apd_p.add_argument("--by", required=True, dest="decided_by")
    apd_p.add_argument("--rationale", default=None)
    apd_p.add_argument("--root", default=".", metavar="DIR")

    apu_p = ap_ap_sub.add_parser(
        "update",
        help="Update checklist item status on an existing open (draft/pending) approval",
    )
    apu_p.add_argument("approval_id")
    apu_p.add_argument(
        "--checklist-item", action="append", required=True, dest="checklist_item",
        metavar="LABEL:STATUS",
        help="Repeatable. LABEL must match an existing item exactly; "
             "STATUS is ok|pending|flag",
    )
    apu_p.add_argument("--root", default=".", metavar="DIR")

    apc_p = ap_ap_sub.add_parser(
        "cancel", help="Withdraw an open (draft/pending) approval — a distinct terminal state"
    )
    apc_p.add_argument("approval_id")
    apc_p.add_argument("--reason", default=None)
    apc_p.add_argument("--root", default=".", metavar="DIR")

    aps_p = ap_ap_sub.add_parser(
        "scan-thresholds",
        help="Detect repeated exit-75 reasons (5+) and open threshold_review approvals",
    )
    aps_p.add_argument(
        "--min-occurrences", type=int, default=5, dest="min_occurrences",
        help="How many repeats of the same undecided_reason trigger a review (default: 5, "
             "matching 방법론서 §30)",
    )
    aps_p.add_argument("--root", default=".", metavar="DIR")

    sk_p = ap_sub.add_parser(
        "skills",
        help="Detect repeated approval checklist shapes as skill candidates, "
             "and scaffold a SKILL.md stub from one",
    )
    sk_sub = sk_p.add_subparsers(dest="skills_command")
    skd_p = sk_sub.add_parser(
        "detect", help="List repeated checklist patterns (read-only, creates nothing)"
    )
    skd_p.add_argument(
        "--min-occurrences", type=int, default=3, dest="min_occurrences",
        help="How many repeats count as a candidate (default: 3, 방법론서 §26.6)",
    )
    skd_p.add_argument("--root", default=".", metavar="DIR")

    sks_p = sk_sub.add_parser(
        "scaffold",
        help="Write a SKILL.md stub from a detected candidate (TODOs left for a human)",
    )
    sks_p.add_argument("--name", required=True, help="kebab-case skill name")
    sks_p.add_argument(
        "--kind", default=None, choices=list(VALID_APPROVAL_KINDS),
        help="Scaffold from the top candidate of this approval kind "
             "(default: the single highest-count candidate overall)",
    )
    sks_p.add_argument(
        "--min-occurrences", type=int, default=3, dest="min_occurrences",
        help="Same threshold as 'skills detect' (default: 3)",
    )
    sks_p.add_argument(
        "--out", default="Skills", metavar="DIR",
        help="Parent directory to write <out>/<name>/SKILL.md into (default: Skills)",
    )
    sks_p.add_argument("--force", action="store_true", help="Overwrite an existing stub")
    sks_p.add_argument("--root", default=".", metavar="DIR")


def _cmd_autopilot_skills_detect(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"
    candidates = detect_skill_candidates(approvals_path, min_occurrences=args.min_occurrences)

    if not candidates:
        print(f"{D}No repeated checklist pattern found "
              f"(threshold: {args.min_occurrences}+ occurrences).{R}")
        return 0

    print(f"{B}Skill candidates (read-only — nothing was created):{R}")
    for c in candidates:
        print(f"  {G}{c['count']}x{R}  kind={c['kind']}")
        for label in c["labels"]:
            print(f"      - {label}")
    print()
    print(f"{D}Before creating a skill: check against the existing 17+ in Skills/ "
          f"(원칙4, 방법론서 §26.6 자격확인). Creation itself stays a human step.{R}")
    return 0


def _cmd_autopilot_skills_scaffold(args: argparse.Namespace) -> int:
    root = Path(args.root)
    approvals_path = root / ".aoo" / "approvals.jsonl"
    candidates = detect_skill_candidates(approvals_path, min_occurrences=args.min_occurrences)

    if args.kind is not None:
        candidates = [c for c in candidates if c["kind"] == args.kind]
    if not candidates:
        print(_err(
            f"no skill candidate found "
            f"(threshold: {args.min_occurrences}+"
            + (f", kind={args.kind}" if args.kind else "")
            + ") — run 'agent-eval autopilot skills detect' first"
        ))
        return 1

    out_path = Path(args.out) / args.name / "SKILL.md"
    if out_path.exists() and not args.force:
        print(_err(f"{out_path} already exists — pass --force to overwrite"))
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_skill_stub(candidates[0], args.name), encoding="utf-8")
    print(_ok(f"Skill stub written: {out_path}"))
    print(
        f"  {D}Based on {candidates[0]['count']}x repeated kind={candidates[0]['kind']} "
        f"checklist. TODO markers are left for a human — fill in the description, "
        f"the reasoning, and each step's concrete procedure before treating this "
        f"as a real skill (원칙4, 방법론서 §26.6 자격확인).{R}"
    )
    return 0


def _cmd_autopilot_skills(args: argparse.Namespace) -> int:
    handlers = {"detect": _cmd_autopilot_skills_detect, "scaffold": _cmd_autopilot_skills_scaffold}
    skills_command = getattr(args, "skills_command", None)
    handler = handlers.get(skills_command) if skills_command is not None else None
    if handler is None:
        print(_err("Specify a skills subcommand: detect | scaffold"))
        return 1
    return handler(args)


def _cmd_autopilot_decisions(args: argparse.Namespace) -> int:
    """`agent-eval decisions`의 얇은 alias(SPEC-AP-001 백로그 §6 —

    개념적으로 Autopilot의 일부인데 CLI 트리가 최상위 명령으로 분리돼
    있었다). 구현은 그대로 `cli/decisions.py`를 재사용하고(원칙4 — 새
    로직 없음), `--log`를 안 주면 autopilot의 다른 명령들과 같은 관례로
    `.aoo/decisions.jsonl`을 기본값으로 채운다. 기존 최상위
    `agent-eval decisions ...`는 그대로 남아 있다 — 이건 대체가 아니라
    추가 경로다.
    """
    from agent_evaluator.cli.decisions import cmd_decisions

    sub = getattr(args, "decisions_command", None)
    if sub not in ("list", "record"):
        print(_err("Specify a decisions subcommand: list | record"))
        return 1
    if not getattr(args, "log", None):
        args.log = str(Path(args.root) / ".aoo" / "decisions.jsonl")
    return cmd_decisions(args)


def cmd_autopilot(args: argparse.Namespace) -> int:
    """autopilot 서브커맨드 핸들러 — autopilot_command에 따라 분기한다."""
    handlers = {
        "install": _cmd_autopilot_install,
        "doctor": _cmd_autopilot_doctor,
        "dashboard": _cmd_autopilot_dashboard,
        "new-task": _cmd_autopilot_new_task,
        "list-tasks": _cmd_autopilot_list_tasks,
        "show-task": _cmd_autopilot_show_task,
        "update-task": _cmd_autopilot_update_task,
        "set-task-status": _cmd_autopilot_set_task_status,
        "add-member": _cmd_autopilot_add_member,
        "remove-member": _cmd_autopilot_remove_member,
        "update-member": _cmd_autopilot_update_member,
        "list-members": _cmd_autopilot_list_members,
        "phase": _cmd_autopilot_phase,
        "approvals": _cmd_autopilot_approvals,
        "decisions": _cmd_autopilot_decisions,
        "skills": _cmd_autopilot_skills,
    }
    autopilot_command = getattr(args, "autopilot_command", None)
    handler = handlers.get(autopilot_command) if autopilot_command is not None else None
    if handler is None:
        print(_err(
            "Specify an autopilot subcommand: install | doctor | dashboard | "
            "new-task | list-tasks | show-task | update-task | set-task-status | "
            "add-member | remove-member | update-member | list-members | phase | "
            "approvals | decisions | skills"
        ))
        print(f"{D}For details: agent-eval autopilot --help{R}")
        return 1
    return handler(args)


# ---------------------------------------------------------------------------
# entry-points 진입점 — pyproject.toml의
# [project.entry-points."agent_evaluator.cli_plugins"] autopilot = "...:register"
# ---------------------------------------------------------------------------


def register(sub: argparse._SubParsersAction) -> Callable[[argparse.Namespace], int]:  # type: ignore[type-arg]
    """``agent_evaluator.cli_plugins`` 엔트리 포인트 그룹의 진입점.

    ``cli/main.py``는 ``build_autopilot_subparser``/``cmd_autopilot``을 직접
    import하지 않는다 — ``importlib.metadata.entry_points(group=...)``로 이
    함수만 찾아서 호출한다(``main.py``의 ``_load_cli_plugins()`` 참고). 이
    모듈이 통째로 별도 배포판(예: ``harness-autopilot`` 패키지가
    ``agent-evaluator``를 의존성으로 갖는 형태)으로 옮겨가도, entry-points
    선언만 그 패키지의 ``pyproject.toml``로 옮기면 ``main.py``는 한 줄도
    바꿀 필요가 없다 — 이게 이 함수를 따로 둔 이유다.
    """
    build_autopilot_subparser(sub)
    return cmd_autopilot
