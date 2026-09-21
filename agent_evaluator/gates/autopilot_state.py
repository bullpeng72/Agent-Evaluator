"""
Harness Autopilot M0 — .aoo/tasks/<task_id>.json · .aoo/team.json 읽기/쓰기.

Harness Autopilot 설계서(SPEC-AP-001 §4.1·§4.5·§4.6)의 데이터 모델을 그대로
구현한다 — 새 채점/판정 로직은 없다(설계 원칙 2). 과제 하나당 파일 하나로
다중 과제를 지원하고(§4.5), 별도 인덱스를 두지 않고 디렉토리 자체를 진실
소스로 스캔한다 — 인덱스와 개별 파일이 어긋나는 새 동기화 문제를 만들지
않기 위해서다(같은 이유는 §9 마찰 #6·`sync-drift-check`에도 등장한다).

team.json의 `synced` 필드는 항상 등록 시 False로 시작한다 — 팀 관리 화면
에서 팀원을 추가해도 GitHub CODEOWNERS 파일은 자동으로 갱신되지 않는다는
설계서 §4.6의 명시적 결정을 그대로 반영한 것이다. 이 파일은 그 동기화를
수행하지 않는다(범위 밖, §7 리스크).

이 모듈이 `team_concurrency.load_active_claims()` / `rca.decision_ledger.
load_decisions()`에 기대는 반환 계약과 `.aoo/*.jsonl` 파일 포맷 자체의
인터페이스 경계는 `Docs/specs/SPEC-AP-001-harness-autopilot-interface.md`
참고.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union, cast

PHASE_LABELS: dict[int, str] = {
    0: "부트스트랩",
    1: "분석",
    2: "설계",
    3: "개발(TDD-AI)",
    4: "검증",
    5: "팀·PR CI",
    6: "Skills화",
    7: "릴리스 후보",
    8: "운영",
}

VALID_PLATFORMS = ("AC", "AOO")
VALID_ROLES = ("분석", "설계", "개발", "QA", "PM", "보안")

# task_id는 그대로 파일명(``task_path()``)이 된다 — "/"나 ".."가 섞이면
# .aoo/tasks/ 밖에 파일을 쓰거나 읽을 위험이 있다(경로 조작). CLI
# ``--task-id``는 사람이 직접 넣는 자유 텍스트라 여기서 막아야 한다.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 과제(Task) — .aoo/tasks/<task_id>.json (§4.1·§4.5)
# ---------------------------------------------------------------------------


def task_path(tasks_dir: Union[str, Path], task_id: str) -> Path:
    return Path(tasks_dir) / f"{task_id}.json"


def save_task(tasks_dir: Union[str, Path], task: dict[str, Any]) -> Path:
    """과제 상태를 파일 하나에 통째로 쓴다. ``task['task_id']`` 필수."""
    task_id = task.get("task_id")
    if not task_id:
        raise ValueError("task['task_id'] is required")
    tasks_dir = Path(tasks_dir)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = task_path(tasks_dir, task_id)
    path.write_text(
        json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def load_task(tasks_dir: Union[str, Path], task_id: str) -> dict[str, Any] | None:
    path = task_path(tasks_dir, task_id)
    if not path.is_file():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except json.JSONDecodeError:
        return None


def load_all_tasks(tasks_dir: Union[str, Path]) -> list[dict[str, Any]]:
    """디렉토리를 스캔해 모든 과제를 반환한다(§4.5 — 인덱스 파일 없음, 디렉토리가 진실 소스)."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    for f in sorted(tasks_dir.glob("*.json")):
        try:
            tasks.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return tasks


def create_task(
    tasks_dir: Union[str, Path],
    task_id: str,
    title: str,
    platform: str,
    priority: str = "normal",
    owners: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """새 과제를 Phase 0으로 생성한다(§4.5 "새 과제 등록" 흐름)."""
    if not _SLUG_RE.match(task_id):
        raise ValueError(
            f"invalid task_id: {task_id!r} — letters/digits/'-'/'_'/'.' only, "
            "must start with a letter or digit (it becomes a filename)"
        )
    platform_norm = platform.upper()
    if platform_norm not in VALID_PLATFORMS:
        raise ValueError(f"platform must be one of {VALID_PLATFORMS}, got {platform!r}")
    if load_task(tasks_dir, task_id) is not None:
        raise ValueError(f"task already exists: {task_id}")

    now = _now()
    task: dict[str, Any] = {
        "task_id": task_id,
        "title": title,
        "platform": platform_norm,
        "priority": priority,
        "current_phase": 0,
        "phase_label": PHASE_LABELS[0],
        "owners": owners or {},
        "phase_history": [
            {"phase": 0, "entered_at": now, "exited_at": None, "mode": "auto"}
        ],
        "blocking_on": [],
        "last_gate_run": None,
        "created_at": now,
        "status": "active",
    }
    save_task(tasks_dir, task)
    return task


def update_task(
    tasks_dir: Union[str, Path],
    task_id: str,
    *,
    title: str | None = None,
    platform: str | None = None,
    priority: str | None = None,
    owners: dict[str, str] | None = None,
    changed_by: str | None = None,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    """등록된 과제의 필드를 수정한다(대시보드/CLI에 과제 수정 기능이 없다는

    실사용 피드백 — 등록 후 제목·플랫폼·우선순위·담당자를 고칠 방법이
    없었다).

    ``phase``와 ``status``는 이 함수의 범위 밖이다 — 각각 ``transition_phase()``
    /``set_task_status()``가 이미 전담하고, 그 둘은 감사 이력(``phase_history``
    ·``status_changed_at``)을 남기는데 이 함수로 같이 바꾸면 그 이력 없이
    조용히 어긋난다(원칙2 — 정직한 기록). ``None``으로 남긴 인자는 기존
    값을 그대로 둔다.

    ``changed_by``(docs/AUTOPILOT_IMPROVEMENTS.md §14)는 ``transition_phase()``
    의 ``approved_by``·``decide_approval()``의 ``decided_by``와 같은 자리다 —
    지금까진 과제 수정만 "누가 했는지"를 하나도 안 남겼다. ``last_updated_by``
    /``last_updated_at``로 저장한다(선택 — 생략하면 이전과 동일하게 동작).

    ``expected_updated_at``(선택)은 낙관적 동시성 검사다 — 값을 주면, 폼을
    읽은 시점 이후 다른 사람이 먼저 저장해서 ``last_updated_at``이 달라졌을
    때 조용히 덮어쓰는 대신 ``ValueError``로 막는다. 새 잠금 인프라가 아니라
    이미 있는 타임스탬프를 재사용하는 비교일 뿐이다(원칙4).

    Args:
        tasks_dir: ``.aoo/tasks`` 디렉터리.
        task_id: 수정할 과제.
        title: 새 제목(선택).
        platform: 새 플랫폼(선택) — ``VALID_PLATFORMS`` 중 하나(대소문자 무관).
        priority: 새 우선순위(선택) — ``create_task()``와 같이 자유 문자열,
            SDK 레벨 검증 없음(CLI의 ``choices``가 그 역할을 한다).
        owners: 새 담당자 dict(선택) — ``update_team_member()``의 ``roles``와
            같은 방식으로 통째로 대체한다.
        changed_by: 이 수정을 한 사람(선택, 자유 텍스트).
        expected_updated_at: 낙관적 동시성 검사용(선택) — 폼을 그릴 때 본
            ``last_updated_at`` 값. 현재 값과 다르면 막는다.

    Returns:
        수정된 과제 dict.

    Raises:
        ValueError: 그 ``task_id``가 없거나, ``platform``이 알 수 없는 값이거나,
            ``expected_updated_at``이 주어졌는데 현재 값과 다르면.
    """
    task = load_task(tasks_dir, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")

    if expected_updated_at is not None and task.get("last_updated_at") != expected_updated_at:
        raise ValueError(
            f"conflict: task {task_id!r} was modified by someone else since you loaded "
            f"this page (current last_updated_at={task.get('last_updated_at')!r}) — "
            f"reload and retry"
        )

    if title is not None:
        task["title"] = title
    if platform is not None:
        platform_norm = platform.upper()
        if platform_norm not in VALID_PLATFORMS:
            raise ValueError(f"platform must be one of {VALID_PLATFORMS}, got {platform!r}")
        task["platform"] = platform_norm
    if priority is not None:
        task["priority"] = priority
    if owners is not None:
        task["owners"] = dict(owners)

    task["last_updated_at"] = _now()
    task["last_updated_by"] = changed_by

    save_task(tasks_dir, task)
    return task


VALID_TASK_STATUSES = ("active", "archived", "cancelled")


def set_task_status(
    tasks_dir: Union[str, Path],
    task_id: str,
    status: str,
    reason: str | None = None,
    *,
    changed_by: str | None = None,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    """과제 상태를 바꾼다(SPEC-AP-001 백로그 §2 — phase 8(운영) 이후 과제를
    "끝"으로 표시할 방법이 없었다).

    새 phase가 아니다 — phase는 SDLC 진행 단계(0~8), ``status``는 그
    과제 자체가 아직 살아 있는지("active")·끝났는지("archived")·중단됐는지
    ("cancelled")를 나타내는 별도 축이다. 이전 버전(``status`` 필드가 아예
    없던 과제 파일)을 읽으면 ``load_task()``가 그대로 반환하고, 이 함수를
    거치지 않는 한 필드가 안 생긴다 — 하위호환.

    ``changed_by``/``expected_updated_at``는 ``update_task()``와 같은
    자리다(docs/AUTOPILOT_IMPROVEMENTS.md §14) — "누가 바꿨는지"가 지금까지
    전혀 안 남았고, 낙관적 동시성 검사도 없었다. 둘 다 선택이라 생략하면
    이전과 동일하게 동작한다.

    Args:
        tasks_dir: ``.aoo/tasks`` 디렉터리.
        task_id: 대상 과제.
        status: ``VALID_TASK_STATUSES`` 중 하나.
        reason: 자유 텍스트(선택) — 왜 보관/취소했는지.
        changed_by: 이 상태 변경을 한 사람(선택, 자유 텍스트).
        expected_updated_at: 낙관적 동시성 검사용(선택) — 폼을 그릴 때 본
            ``last_updated_at`` 값. 현재 값과 다르면 막는다.

    Returns:
        갱신된 과제 dict.

    Raises:
        ValueError: 과제가 없거나 ``status``가 알 수 없는 값이거나,
            ``expected_updated_at``이 주어졌는데 현재 값과 다르면.
    """
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"status must be one of {VALID_TASK_STATUSES}, got {status!r}")
    task = load_task(tasks_dir, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    if expected_updated_at is not None and task.get("last_updated_at") != expected_updated_at:
        raise ValueError(
            f"conflict: task {task_id!r} was modified by someone else since you loaded "
            f"this page (current last_updated_at={task.get('last_updated_at')!r}) — "
            f"reload and retry"
        )
    task["status"] = status
    task["status_reason"] = reason
    task["status_changed_at"] = _now()
    task["status_changed_by"] = changed_by
    task["last_updated_at"] = task["status_changed_at"]
    task["last_updated_by"] = changed_by
    save_task(tasks_dir, task)
    return task


def transition_phase(
    tasks_dir: Union[str, Path],
    task_id: str,
    new_phase: int,
    mode: str = "auto",
    approved_by: str | None = None,
    *,
    approvals_path: Union[str, Path, None] = None,
    required_approval_kind: str | None = None,
) -> dict[str, Any]:
    """Phase 전이(설계서 §3.3) — 이전 이력 항목을 닫고 새 항목을 연다.

    ``required_approval_kind``는 옵트인 게이트다(기본값 ``None`` — 기존
    호출은 전부 이전과 동일하게 동작한다, §9.5.4 순위1). 값을 주면, 이
    ``task_id``에 그 ``kind``의 승인이 ``approved``로 확정돼 있는지
    ``approvals_path``에서 확인한 뒤에만 전이를 허용한다 — 새 판정 로직이
    아니라 이미 있는 ``.aoo/approvals.jsonl``의 결정 상태를 읽기만 한다
    (원칙4). SPEC 검토가 끝나지 않은 채 Phase 2(설계)로, 심지어 Phase
    8(운영)로 바로 넘어가는 걸 코드가 막지 않던 §9.5의 갭을 이 지점에서
    메운다 — "결정 먼저"(원칙1)가 습관이 아니라 구조로 강제된다.
    """
    task = load_task(tasks_dir, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")

    if required_approval_kind is not None:
        if approvals_path is None:
            raise ValueError(
                "approvals_path is required when required_approval_kind is given"
            )
        has_approval = any(
            a.get("task_id") == task_id
            and a.get("kind") == required_approval_kind
            and a.get("status") == "approved"
            for a in load_approvals(approvals_path)
        )
        if not has_approval:
            raise ValueError(
                f"cannot transition {task_id!r} to phase {new_phase} — no "
                f"approved {required_approval_kind!r} approval found for this "
                f"task (required_approval_kind gate)"
            )

    now = _now()
    history: list[dict[str, Any]] = task.get("phase_history", [])
    if history and history[-1].get("exited_at") is None:
        history[-1]["exited_at"] = now

    entry: dict[str, Any] = {"phase": new_phase, "entered_at": now, "exited_at": None, "mode": mode}
    if approved_by:
        entry["approved_by"] = approved_by
    history.append(entry)

    task["phase_history"] = history
    task["current_phase"] = new_phase
    task["phase_label"] = PHASE_LABELS.get(new_phase, str(new_phase))
    save_task(tasks_dir, task)
    return task


def check_phase_staleness(
    tasks_dir: Union[str, Path], stale_days: float = 7.0
) -> list[dict[str, Any]]:
    """현재 phase에 오래 머문 활성 과제를 찾는다(SPEC-AP-001 백로그 §3 —
    docs/AUTOPILOT_IMPROVEMENTS.md, LIMITS_T-5E1FD6.md L4).

    ``transition_phase()``에 조건을 안 넘기면(옵트인) 전이 자체를 그냥
    깜빡해도 아무 신호가 없다 — AOO Stack 실습서에서 이 정확한 실수가
    같은 프로젝트에서 두 번 재발했다(Part VIII 전체가 phase 4 활동인데
    task는 phase 3에 머묾, 그 다음 Part도 같은 식으로 재발). ``doctor``가
    현재 phase 숫자만 보여줄 뿐 "이 숫자가 얼마나 오래 안 바뀌었는지"는
    아예 안 쟀다는 게 그 공백의 원인이었다.

    이미 ``phase_history[-1]["entered_at"]``에 있는 값만 다시 읽는다(원칙4
    — git 커밋 시각 같은 새 계측을 붙이지 않는다). 순수 경과시간 신호라
    "이 phase에 정말 아직 작업 중인가"까지는 알 수 없다 — 그건 사람이
    판단할 몫이고, 이 함수는 그 판단이 필요하다는 것만 표면화한다.

    ``archived``/``cancelled`` 과제는 건너뛴다 — 끝났거나 중단된 과제가
    "정체"로 잡히는 건 오탐이다.

    Args:
        tasks_dir: ``.aoo/tasks`` 디렉터리.
        stale_days: 이 일수 이상 같은 phase에 머문 과제를 정체로 본다.

    Returns:
        ``[{"task_id", "current_phase", "phase_label", "entered_at",
        "days_in_phase"}]``, ``days_in_phase`` 내림차순. 비어 있으면 정체
        없음. ``phase_history``가 없거나 타임스탬프를 못 읽는 과제는
        조용히 건너뛴다(예외 전파 방지 — TTL 감사와 같은 패턴,
        ``team_concurrency.audit_claims()`` 참고).
    """
    now = datetime.now(timezone.utc)
    stale: list[dict[str, Any]] = []
    for task in load_all_tasks(tasks_dir):
        if task.get("status", "active") != "active":
            continue
        history: list[dict[str, Any]] = task.get("phase_history") or []
        if not history:
            continue
        entered_at = history[-1].get("entered_at")
        if not entered_at:
            continue
        try:
            entered = datetime.fromisoformat(entered_at)
        except ValueError:
            continue
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)
        days = (now - entered).total_seconds() / 86400
        if days < stale_days:
            continue
        phase = task.get("current_phase")
        phase_int = phase if isinstance(phase, int) else -1
        stale.append({
            "task_id": task.get("task_id"),
            "current_phase": phase,
            "phase_label": PHASE_LABELS.get(phase_int, str(phase)),
            "entered_at": entered_at,
            "days_in_phase": round(days, 1),
        })
    stale.sort(key=lambda s: -cast(float, s["days_in_phase"]))
    return stale


# ---------------------------------------------------------------------------
# 팀원 레지스트리 — .aoo/team.json (§4.6)
# ---------------------------------------------------------------------------


def load_team(team_path: Union[str, Path]) -> list[dict[str, Any]]:
    team_path = Path(team_path)
    if not team_path.is_file():
        return []
    try:
        data = json.loads(team_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    members = data.get("members", [])
    return members if isinstance(members, list) else []


def save_team(team_path: Union[str, Path], members: list[dict[str, Any]]) -> Path:
    team_path = Path(team_path)
    team_path.parent.mkdir(parents=True, exist_ok=True)
    team_path.write_text(
        json.dumps({"members": members}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return team_path


def add_team_member(
    team_path: Union[str, Path],
    member_id: str,
    name: str,
    roles: list[str],
    github: str | None = None,
    codeowner_scopes: list[str] | None = None,
) -> dict[str, Any]:
    """팀원을 등록한다. ``synced=False``로 시작한다(§4.6 — GitHub CODEOWNERS 별도 반영 필요)."""
    members = load_team(team_path)
    if any(m.get("id") == member_id for m in members):
        raise ValueError(f"team member id already exists: {member_id}")
    for r in roles:
        if r not in VALID_ROLES:
            raise ValueError(f"unknown role: {r!r} (expected one of {VALID_ROLES})")

    member: dict[str, Any] = {
        "id": member_id,
        "name": name,
        "roles": list(roles),
        "github": github,
        "codeowner_scopes": codeowner_scopes or [],
        "joined_at": _now(),
        "synced": False,
    }
    members.append(member)
    save_team(team_path, members)
    return member


def remove_team_member(team_path: Union[str, Path], member_id: str) -> dict[str, Any]:
    """Remove a team member by id (SPEC-AP-001 백로그 — team.json은 지금까지 등록만
    가능하고 삭제할 방법이 없었다, docs/AUTOPILOT_IMPROVEMENTS.md §1).

    ``team.json``은 append-only가 아니라 단일 스냅숏 파일이므로(§4.6), 다른
    ``.aoo/*.jsonl`` 원장과 달리 정말로 목록에서 제거한다 — 이력을 남기고
    싶으면 호출 전에 파일을 백업하거나 git으로 추적한다.

    Returns:
        제거된 팀원 dict.

    Raises:
        ValueError: 그 id의 팀원이 없으면.
    """
    members = load_team(team_path)
    idx = next((i for i, m in enumerate(members) if m.get("id") == member_id), None)
    if idx is None:
        raise ValueError(f"team member id not found: {member_id}")
    removed = members.pop(idx)
    save_team(team_path, members)
    return removed


def update_team_member(
    team_path: Union[str, Path],
    member_id: str,
    *,
    name: str | None = None,
    roles: list[str] | None = None,
    github: str | None = None,
    codeowner_scopes: list[str] | None = None,
    synced: bool | None = None,
    changed_by: str | None = None,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    """등록된 팀원의 필드를 수정한다(SPEC-AP-001 백로그 §1 — 등록 후 역할·이름·
    github·codeowner_scope를 고칠 방법이 없었다).

    ``None``으로 남긴 인자는 기존 값을 그대로 둔다 — 바꾸고 싶은 필드만
    넘기면 된다. 특히 ``synced``는 이 함수가 생기기 전까지 등록 시점의
    ``False``에서 절대 바뀌지 않았다(§4.6 경고가 매번 반복되던 이유) —
    GitHub CODEOWNERS를 실제로 갱신한 뒤 ``synced=True``로 직접 표시할 수
    있다.

    ``changed_by``/``expected_updated_at``는 ``update_task()``와 같은
    자리다(docs/AUTOPILOT_IMPROVEMENTS.md §14) — 둘 다 선택이라 생략하면
    이전과 동일하게 동작한다. (``remove_team_member()``는 그대로 둔다 —
    그 함수는 이미 "이력이 필요하면 git으로 추적하라"고 명시적으로
    범위를 밝혀둔 스냅숏 삭제라, 지워지는 레코드에 필드를 남길 자리가
    없다.)

    Args:
        team_path: ``.aoo/team.json`` 경로.
        member_id: 수정할 팀원의 id.
        name: 새 이름(선택).
        roles: 새 역할 목록(선택) — 기존 목록을 통째로 대체한다.
        github: 새 github 핸들(선택).
        codeowner_scopes: 새 codeowner scope 목록(선택) — 통째로 대체.
        synced: GitHub CODEOWNERS 동기화 여부를 직접 표시(선택).
        changed_by: 이 수정을 한 사람(선택, 자유 텍스트).
        expected_updated_at: 낙관적 동시성 검사용(선택) — 폼을 그릴 때 본
            ``last_updated_at`` 값. 현재 값과 다르면 막는다.

    Returns:
        수정된 팀원 dict.

    Raises:
        ValueError: 그 id의 팀원이 없거나, ``roles``에 알 수 없는 역할이 있거나,
            ``expected_updated_at``이 주어졌는데 현재 값과 다르면.
    """
    members = load_team(team_path)
    idx = next((i for i, m in enumerate(members) if m.get("id") == member_id), None)
    if idx is None:
        raise ValueError(f"team member id not found: {member_id}")

    member = dict(members[idx])
    if expected_updated_at is not None and member.get("last_updated_at") != expected_updated_at:
        raise ValueError(
            f"conflict: team member {member_id!r} was modified by someone else since you "
            f"loaded this page (current last_updated_at="
            f"{member.get('last_updated_at')!r}) — reload and retry"
        )
    if name is not None:
        member["name"] = name
    if roles is not None:
        for r in roles:
            if r not in VALID_ROLES:
                raise ValueError(f"unknown role: {r!r} (expected one of {VALID_ROLES})")
        member["roles"] = list(roles)
    if github is not None:
        member["github"] = github
    if codeowner_scopes is not None:
        member["codeowner_scopes"] = list(codeowner_scopes)
    if synced is not None:
        member["synced"] = synced

    member["last_updated_at"] = _now()
    member["last_updated_by"] = changed_by

    members[idx] = member
    save_team(team_path, members)
    return member


def members_by_role(team_path: Union[str, Path], role: str) -> list[dict[str, Any]]:
    return [m for m in load_team(team_path) if role in m.get("roles", [])]


def find_member(team_path: Union[str, Path], id_or_name: str) -> dict[str, Any] | None:
    """id 또는 name으로 팀원을 찾는다(CLI 편의 — 새 과제 등록 시 담당자 검증용)."""
    for m in load_team(team_path):
        if m.get("id") == id_or_name or m.get("name") == id_or_name:
            return m
    return None


# ---------------------------------------------------------------------------
# 승인 대기 큐 — .aoo/approvals.jsonl (§4.2 — decisions.jsonl과 역할 분리)
# ---------------------------------------------------------------------------
#
# decisions.jsonl(기존 SDK, rca/decision_ledger.py)은 "게이트 실행 + 그에 대한
# 최종 사람 결정"만 기록한다. approvals.jsonl은 SPEC 검토·ADR 승인·스킬 병합
# 처럼 게이트 실행이 아닌 승인을 추적한다(설계서 §4.2). claims.jsonl과 같은
# append-only 패턴을 그대로 재사용한다 — 각 줄이 이벤트 하나(open 또는
# decide)이고, 같은 id의 최신 줄이 유효 상태다(§28.5와 동일 원리, 원칙4).

VALID_APPROVAL_KINDS = (
    "spec_review", "adr_review", "skill_merge", "release_hold", "deploy", "threshold_review",
)

# 결정 원장(.aoo/decisions.jsonl)은 과제(task_id) 단위가 아니라 프로젝트 전체가
# 공유하는 원장이다(§4.2 설명 그대로 — decisions.jsonl은 approvals.jsonl과 달리
# 과제 스코프가 없다). threshold_review처럼 여러 과제에 걸친 패턴을 다룰 때는
# 특정 과제가 아니라 이 sentinel을 task_id로 쓴다 — 데이터 모델이 아직 이
# "포트폴리오 단위 승인"을 1급으로 다루지 않는다는 걸 그대로 드러내는 선택이다.
PORTFOLIO_TASK_ID = "PORTFOLIO"
VALID_DECISIONS = ("approved", "rejected", "changes_requested")

# §6 M4 "리드+보안 2인 승인" — GitHub의 "복수 팀 승인" 규칙과 같은 개념을
# 로컬에서 흉내낸다. release_hold/deploy는 한 사람의 "승인"만으로 끝내면
# 안 된다는 게 설계서의 명시적 요구라, 이 두 kind는 기본값을 2로 둔다.
# 다른 kind는 지금까지처럼 1명이면 충분하다(하위호환 — required_approvals=1일
# 때의 동작은 이 기능을 추가하기 전과 완전히 동일하다).
_DEFAULT_REQUIRED_APPROVALS: dict[str, int] = {"deploy": 2, "release_hold": 2}


# ---------------------------------------------------------------------------
# Phase 게이트 정책 — .aoo/phase_policy.json (SPEC-AP-001 백로그 §3)
# ---------------------------------------------------------------------------
#
# transition_phase()의 required_approval_kind는 그 호출 하나에만 적용되는
# opt-in 인자다 — 매번 --require-approval을 타이핑하는 걸 사람이 잊으면
# 그대로 조건 없이 전이된다(실제로 두 번 재발한 phase 드리프트의 근본 원인,
# docs/AUTOPILOT_IMPROVEMENTS.md §3). 이 정책 파일은 "이 phase로 들어갈 땐
# 항상 이 kind 승인이 필요하다"를 프로젝트 단위로 한 번 선언해 두는 것뿐이다
# — 새 판정 로직이 아니라, CLI가 --require-approval을 대신 채워 넣는
# 편의일 뿐이다(원칙4). 파일이 없거나 그 phase에 항목이 없으면 지금까지와
# 완전히 동일하게 동작한다(기본값 없음, opt-in 그대로).


def load_phase_policy(policy_path: Union[str, Path]) -> dict[int, str]:
    """``.aoo/phase_policy.json``을 읽는다. ``{phase_number: approval_kind}``.

    파일이 없거나, JSON이 깨졌거나, 알 수 없는 ``kind``가 있으면 그 항목만
    조용히 무시한다(fail-open — 정책이 없던 것과 똑같이 동작).
    """
    path = Path(policy_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    gates = data.get("gates", {})
    if not isinstance(gates, dict):
        return {}
    result: dict[int, str] = {}
    for k, v in gates.items():
        try:
            phase_num = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, str) and v in VALID_APPROVAL_KINDS:
            result[phase_num] = v
    return result


def set_phase_policy(
    policy_path: Union[str, Path], to_phase: int, kind: str | None
) -> dict[int, str]:
    """``to_phase``로 들어갈 때 필요한 승인 ``kind``를 정하거나(``kind`` 문자열),
    지운다(``kind=None``).

    Returns:
        갱신된 전체 정책 dict.

    Raises:
        ValueError: ``kind``가 ``None``이 아닌데 ``VALID_APPROVAL_KINDS``에
            없으면.
    """
    if kind is not None and kind not in VALID_APPROVAL_KINDS:
        raise ValueError(f"kind must be one of {VALID_APPROVAL_KINDS}, got {kind!r}")
    policy = load_phase_policy(policy_path)
    if kind is None:
        policy.pop(to_phase, None)
    else:
        policy[to_phase] = kind
    path = Path(policy_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"gates": {str(k): v for k, v in sorted(policy.items())}},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return policy


_NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION:\s*([^\]]+)\]")


def extract_needs_clarification(text: str | None) -> list[str]:
    """본문에서 ``[NEEDS CLARIFICATION: ...]`` 태그를 뽑는다(워크북 §6 표기법).

    빈 리스트면 그 태그가 없다는 뜻 — ``open_approval()``의 자동채점(§3.4
    "체크리스트 자동채점")이 이 결과를 그대로 쓴다.
    """
    if not text:
        return []
    return [m.group(1).strip() for m in _NEEDS_CLARIFICATION_RE.finditer(text)]


def score_checklist(checklist: list[dict[str, Any]] | None) -> dict[str, Any]:
    """체크리스트 항목들을 자동채점한다(설계서 §3.4 "8항목 체크리스트 자동채점").

    Args:
        checklist: ``[{"label": str, "status": "ok"|"pending"|"flag"}, ...]``.
            ``status``가 없는 항목은 ``"pending"``으로 간주한다.

    Returns:
        ``{"total", "ok_count", "blocking", "ready_for_review"}``.
        ``blocking``은 ``ok``가 아닌 항목들 — 하나라도 있으면
        ``ready_for_review=False``(§3.4 "체크리스트 미충족" 분기).
    """
    checklist = checklist or []
    blocking = [c for c in checklist if c.get("status", "pending") != "ok"]
    ok_count = len(checklist) - len(blocking)
    return {
        "total": len(checklist),
        "ok_count": ok_count,
        "blocking": blocking,
        "ready_for_review": len(blocking) == 0,
    }


def _approval_path(approvals_path: Union[str, Path]) -> Path:
    return Path(approvals_path)


def _append_approval_event(approvals_path: Union[str, Path], entry: dict[str, Any]) -> None:
    path = _approval_path(approvals_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def open_approval(
    approvals_path: Union[str, Path],
    *,
    task_id: str,
    kind: str,
    phase: int,
    title: str,
    checklist: list[dict[str, Any]] | None = None,
    body_text: str | None = None,
    approval_id: str | None = None,
    gate_on_checklist: bool = True,
    required_approvals: int | None = None,
) -> dict[str, Any]:
    """승인 항목을 연다.

    체크리스트·NEEDS CLARIFICATION을 자동채점해, 바로 사람 큐에 올릴지
    (``pending``) 아직 초안 단계로 묶어둘지(``draft``)를 스스로 정한다 —
    설계서 §3.4 시퀀스의 "체크리스트 미충족 → 승인요청 안 함" 분기를 그대로
    구현한 것이다.

    ``gate_on_checklist=False``면 ``checklist``는 화면에 표시만 되고
    ``ready_for_review`` 판정에 영향을 주지 않는다 — ``spec_review``처럼
    "이 조건을 채워야 사람에게 보인다"는 게 아니라, ``threshold_review``
    처럼 "체크리스트 자체가 사람이 밟을 후속 절차 목록"이라 애초에 게이트
    대상이 아닌 경우에 쓴다. 이 구분 없이 모든 체크리스트를 게이트로 쓰면,
    "할 일 목록"이 전부 처음부터 ``ok``로 시작하지 않는 한 영원히
    ``draft``에 갇힌다(실제로 이 버그를 스캔 스모크테스트에서 발견했다).
    """
    if kind not in VALID_APPROVAL_KINDS:
        raise ValueError(f"kind must be one of {VALID_APPROVAL_KINDS}, got {kind!r}")

    if required_approvals is None:
        required_approvals = _DEFAULT_REQUIRED_APPROVALS.get(kind, 1)
    if required_approvals < 1:
        raise ValueError(f"required_approvals must be >= 1, got {required_approvals!r}")

    needs_clarification = extract_needs_clarification(body_text)
    score = score_checklist(checklist)
    checklist_ready = score["ready_for_review"] or not gate_on_checklist
    ready = checklist_ready and not needs_clarification
    status = "pending" if ready else "draft"

    entry: dict[str, Any] = {
        "id": approval_id or f"ap-{uuid.uuid4().hex[:8]}",
        "task_id": task_id,
        "kind": kind,
        "phase": phase,
        "title": title,
        "opened_at": _now(),
        "status": status,
        "checklist": checklist or [],
        "gate_on_checklist": gate_on_checklist,
        "needs_clarification": needs_clarification,
        "checklist_score": score,
        "required_approvals": required_approvals,
        "approvals_recorded": [],
        "decision": None,
        "decided_by": None,
        "rationale": None,
    }
    _append_approval_event(approvals_path, entry)
    return entry


def load_approvals(approvals_path: Union[str, Path]) -> list[dict[str, Any]]:
    """모든 승인 항목의 최신 상태를 반환한다(id별 마지막 줄이 유효)."""
    path = _approval_path(approvals_path)
    if not path.is_file():
        return []
    latest: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            aid = entry.get("id")
            if aid:
                latest[aid] = entry
    return list(latest.values())


def load_pending_approvals(approvals_path: Union[str, Path]) -> list[dict[str, Any]]:
    """사람이 지금 볼 필요가 있는 항목만 반환한다(``status == "pending"``)."""
    return [a for a in load_approvals(approvals_path) if a.get("status") == "pending"]


def decide_approval(
    approvals_path: Union[str, Path],
    approval_id: str,
    *,
    decision: str,
    decided_by: str,
    rationale: str | None = None,
) -> dict[str, Any]:
    """사람의 승인/반려/수정요청을 기록한다(새 줄 append — 이전 줄은 그대로 둔다).

    ``required_approvals > 1``인 항목(§6 M4 — 기본값은 ``deploy``/
    ``release_hold``)은 서로 다른 사람의 "승인"이 그 수만큼 쌓여야 비로소
    ``status="approved"``로 확정된다 — 그 전까지는 ``status`` 그대로
    ``"pending"``에 머물러 큐에서 사라지지 않는다. 반려/수정요청은
    ``required_approvals``와 무관하게 누구 한 명이라도 걸면 즉시 확정된다
    (실제 2인 승인 워크플로에서도 거부권은 단독으로 행사되는 것과 같다).
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")

    existing = {a["id"]: a for a in load_approvals(approvals_path)}
    if approval_id not in existing:
        raise ValueError(f"approval not found: {approval_id}")
    if decision == "changes_requested" or decision == "rejected":
        if not rationale:
            raise ValueError(f"--rationale is required for decision={decision!r}")

    base = dict(existing[approval_id])
    required = int(base.get("required_approvals") or 1)
    recorded: list[dict[str, Any]] = list(base.get("approvals_recorded") or [])

    if decision == "approved" and required > 1:
        if any(r.get("by") == decided_by for r in recorded):
            raise ValueError(
                f"{decided_by!r} already recorded an approval on {approval_id} — "
                f"needs a different approver (requires {required} distinct approvers)"
            )
        recorded.append({"by": decided_by, "at": _now(), "rationale": rationale})
        base["approvals_recorded"] = recorded
        if len(recorded) < required:
            base["status"] = "pending"
            _append_approval_event(approvals_path, base)
            return base
        # required 수만큼 모였다 — 아래에서 그대로 확정 처리로 넘어간다.

    base["status"] = decision
    base["decision"] = decision
    base["decided_by"] = decided_by
    base["rationale"] = rationale
    base["decided_at"] = _now()
    if decision == "approved" and required > 1:
        base["approvals_recorded"] = recorded
    _append_approval_event(approvals_path, base)
    return base


def update_approval_checklist(
    approvals_path: Union[str, Path],
    approval_id: str,
    updates: list[dict[str, str]],
) -> dict[str, Any]:
    """열려 있는 승인의 체크리스트 항목 상태를 수정한다(SPEC-AP-001 백로그 §4 —
    docs/AUTOPILOT_IMPROVEMENTS.md).

    지금까지는 항목 하나가 ``pending``/``flag``로 걸려 ``draft``에 갇힌 뒤
    그 이슈가 실제로 해소돼도, 고칠 방법이 **새 승인을 처음부터 다시 여는
    것**뿐이었다 — 이 함수가 그 재드래프트를 대체한다. ``decide_approval()``
    과 같은 append-only 패턴으로 새 이벤트 줄을 남기고, 체크리스트만
    ``score_checklist()``(새 판정 로직 아님, 원칙4)로 재채점한다.

    Args:
        approvals_path: ``.aoo/approvals.jsonl`` 경로.
        approval_id: 수정할 승인의 id.
        updates: ``[{"label": str, "status": "ok"|"pending"|"flag"}, ...]``.
            각 ``label``은 기존 체크리스트 항목과 **정확히 일치**해야 한다 —
            이 함수는 수정 전용이지 항목 추가용이 아니다(새 항목이
            필요하면 ``open_approval()``로 새로 연다).

    Returns:
        갱신된 승인의 새 상태(``open_approval()``과 같은 모양).

    Raises:
        ValueError: 승인이 없거나, 이미 결정됐거나(``approved``/``rejected``/
            ``changes_requested`` — 확정된 승인은 불변이다), ``updates``의
            ``label``이 기존 체크리스트와 하나도 안 맞으면.
    """
    existing = {a["id"]: a for a in load_approvals(approvals_path)}
    if approval_id not in existing:
        raise ValueError(f"approval not found: {approval_id}")

    base = dict(existing[approval_id])
    if base.get("status") not in ("draft", "pending"):
        raise ValueError(
            f"cannot update {approval_id!r} — already decided "
            f"(status={base.get('status')!r}); a decided approval is final"
        )

    checklist = [dict(c) for c in (base.get("checklist") or [])]
    by_label = {c.get("label"): i for i, c in enumerate(checklist)}
    for u in updates:
        label = u.get("label")
        if label not in by_label:
            raise ValueError(
                f"no checklist item labeled {label!r} on {approval_id!r} — "
                f"update_approval_checklist() only changes existing items, "
                f"it does not add new ones"
            )
        checklist[by_label[label]]["status"] = u.get("status", "pending")

    score = score_checklist(checklist)
    checklist_ready = score["ready_for_review"] or not base.get("gate_on_checklist", True)
    ready = checklist_ready and not base.get("needs_clarification")

    base["checklist"] = checklist
    base["checklist_score"] = score
    base["status"] = "pending" if ready else "draft"
    _append_approval_event(approvals_path, base)
    return base


def cancel_approval(
    approvals_path: Union[str, Path], approval_id: str, reason: str | None = None
) -> dict[str, Any]:
    """열려 있는(``draft``/``pending``) 승인을 취소한다(SPEC-AP-001 백로그 §4 —
    폐기된 draft가 ``approvals.jsonl``에 영구 잔존해 "폐기됨"을 표시할 방법이
    없었다).

    ``decide_approval()``의 ``VALID_DECISIONS``(approved/rejected/
    changes_requested)에 속하지 않는 별도 종결 상태다 — 아무도 내용을
    검토해서 반려한 게 아니라, 애초에 철회됐다는 뜻이라 구분한다. 취소된
    승인도 ``load_approvals()``에는 계속 나타난다(append-only, 이력 삭제
    없음) — ``list``(기본, pending만)에선 다른 종결 상태와 마찬가지로
    빠지고, ``list --all``에선 ``cancelled``로 표시된다.

    Raises:
        ValueError: 승인이 없거나 이미 결정됐으면(이미 종결된 승인은
            취소도 다시 못 한다).
    """
    existing = {a["id"]: a for a in load_approvals(approvals_path)}
    if approval_id not in existing:
        raise ValueError(f"approval not found: {approval_id}")
    base = dict(existing[approval_id])
    if base.get("status") not in ("draft", "pending"):
        raise ValueError(
            f"cannot cancel {approval_id!r} — already decided "
            f"(status={base.get('status')!r})"
        )
    base["status"] = "cancelled"
    base["decision"] = "cancelled"
    base["decided_by"] = None
    base["rationale"] = reason
    base["decided_at"] = _now()
    _append_approval_event(approvals_path, base)
    return base


def compute_rejection_rate(
    approvals_path: Union[str, Path], window: int = 20
) -> dict[str, Any]:
    """최근 결정된 승인 중 반려율을 센다(부록 H.7 자가점검 — "HITL 관문 반려

    이력이 0건이다"는 원칙6 위반 신호, §9.5.4 순위4). 새 데이터가 필요
    없다 — ``.aoo/approvals.jsonl``에 이미 있는 결정 이력만 다시 읽는다
    (원칙4). ``pending``/``draft``(아직 결정 안 됨)는 분모에서 뺀다.

    ``stuck_in_draft``(LIMITS_T-5E1FD6.md L6): 반려율의 분모는 확정된
    승인만 본다는 바로 그 설계 때문에, 체크리스트를 못 넘겨 계속
    ``draft``에 머무는 항목은 안 잡힌다 — 실측(AOO 실습서 Ch35)에서 이
    프로젝트의 진짜 반려는 전부 draft 단계(콜론 문법 실수로 3번 재드래프트)
    에서 일어났는데, 반려율은 그걸 하나도 못 보고 0%로 나와 "형식적
    승인(고무도장) 위험" 오탐을 냈다. 이 필드는 새 비율을 만들지 않는다
    (원칙4) — 현재 ``draft`` 상태인 승인 개수를 그대로 셀 뿐이다. 반려율이
    낮게 나올 때 이 숫자도 함께 봐야 "진짜 반려가 적다"와 "반려가 draft
    단계에서 안 보이게 일어나고 있다"를 구별할 수 있다.

    Returns:
        ``{"window", "total", "rejected_or_changes_requested", "rejection_rate",
        "stuck_in_draft"}``. ``rejection_rate``는 결정된 항목이 하나도 없으면
        ``None``이다("0%"과 "아직 아무도 결정 안 함"은 다른 상태다).
    """
    all_approvals = load_approvals(approvals_path)
    decided = [
        a for a in all_approvals
        if a.get("status") in ("approved", "rejected", "changes_requested")
    ]
    decided.sort(key=lambda a: a.get("decided_at") or "")
    recent = decided[-window:] if window else decided

    total = len(recent)
    non_approved = sum(1 for a in recent if a.get("status") != "approved")
    rate = (non_approved / total) if total else None
    stuck_in_draft = sum(1 for a in all_approvals if a.get("status") == "draft")

    return {
        "window": window,
        "total": total,
        "rejected_or_changes_requested": non_approved,
        "rejection_rate": rate,
        "stuck_in_draft": stuck_in_draft,
    }


# ---------------------------------------------------------------------------
# 반복 패턴 탐지 — M3(Skills 자동추출)·M4(threshold-realism-review)
# ---------------------------------------------------------------------------
#
# 둘 다 "이미 쌓인 로컬 데이터에서 반복을 센다"는 같은 모양이다 — 무인
# 세션 로그나 GitHub 이벤트 같은, 이 환경에 없는 걸 요구하지 않는다.
# 원칙4(이미 있는 걸 다시 만들지 않는다)를 그대로 따른 것이다.


def detect_skill_candidates(
    approvals_path: Union[str, Path], min_occurrences: int = 3
) -> list[dict[str, Any]]:
    """승인 이력에서 반복되는 체크리스트 "모양"을 찾는다(방법론서 §26.6 자격확인 — 3회+).

    같은 ``kind``의 승인들이 정확히 같은 체크리스트 라벨 집합을 반복해서
    썼다면, 그 라벨 집합이 스킬 후보다 — 매번 같은 항목을 손으로 다시
    적고 있었다는 뜻이기 때문이다. 파일을 만들지는 않는다(설계서 §26.6이
    요구하는 사람 검토·기존 17개와 중복 대조는 이 함수 밖의 몫이다).

    ``count``는 승인 **항목(id) 개수가 아니라 서로 다른 task_id의 개수**다
    (SPEC-AP-001 백로그 §7 — AOO 실습서 Ch38이 실측으로 발견: 승인 항목
    하나가 체크리스트 오류로 반려·재오픈되면 매번 새 ``id``가 생기는데
    (``update_approval_checklist()``는 결정 전 승인만 수정하지, 이미
    ``rejected``/``changes_requested``로 끝난 건 새로 열어야 한다), 이걸
    그대로 세면 "같은 task가 한 승인을 4번 재시도한 것"과 "4개의 다른
    task가 독립적으로 같은 체크리스트가 필요했던 것"을 구별 못 한다 —
    전자는 반복 패턴이 아니라 재드래프트 churn이다. 같은 task_id 안에서
    난 반복은 1회로만 센다. 트레이드오프: 한 task가 정말로 같은 체크리스트
    모양을 두 번 독립적으로 필요로 한 드문 경우도 1회로 합쳐진다 —
    "재드래프트를 반복으로 오인하지 않는다"는 원래 문제 쪽이 훨씬 흔하므로
    이쪽을 택했다.

    Returns:
        ``[{"kind", "labels": tuple[str, ...], "count", "approval_ids"}]``,
        ``count``(distinct task_id 수) 내림차순. ``approval_ids``는 그
        모양을 만든 모든 승인 id(재드래프트 포함, 근거 인용용).
    """
    from collections import defaultdict

    groups: dict[tuple[str, tuple[str, ...]], dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for a in load_approvals(approvals_path):
        labels = tuple(sorted(c.get("label", "") for c in a.get("checklist") or []))
        if not labels:
            continue
        key = (a.get("kind", ""), labels)
        groups[key][a.get("task_id", "")].append(a.get("id", ""))

    candidates = []
    for (kind, labels), by_task in groups.items():
        if len(by_task) < min_occurrences:
            continue
        approval_ids = [aid for ids in by_task.values() for aid in ids]
        candidates.append(
            {"kind": kind, "labels": labels, "count": len(by_task), "approval_ids": approval_ids}
        )
    candidates.sort(key=lambda c: -cast(int, c["count"]))
    return candidates


def render_skill_stub(candidate: dict[str, Any], name: str) -> str:
    """``detect_skill_candidates()`` 후보 하나를 SKILL.md 초안 텍스트로

    렌더링한다(SPEC-AP-001 백로그 §7 — 후보가 나와도 SKILL.md를 손으로
    처음부터 써야 했다). 반복된 체크리스트 라벨을 절차 초안으로 그대로
    채우지만, ``description``과 각 절차의 구체적 실행 방법은 사람이
    채워야 할 자리로 명시적으로 ``TODO``로 남긴다 — 이 함수는 빈 페이지
    에서 시작하지 않게 할 뿐, 사람 검토(방법론서 §26.6 자격확인 — 기존
    스킬과 중복 대조)를 대체하지 않는다.

    파일을 쓰지 않는 순수 함수다 — 어디에 저장할지는 호출자(CLI)의 몫이다.

    Args:
        candidate: ``detect_skill_candidates()``가 반환한 항목 하나
            (``{"kind", "labels", "count", "approval_ids"}``).
        name: 새 스킬 디렉터리/frontmatter에 쓸 kebab-case 이름.

    Returns:
        기존 ``Skills/*/SKILL.md``와 같은 frontmatter 형식의 마크다운 텍스트.
    """
    labels = candidate.get("labels") or ()
    kind = candidate.get("kind", "")
    count = candidate.get("count", 0)
    approval_ids = ", ".join(candidate.get("approval_ids") or [])
    steps = "\n".join(f"{i}. {label}" for i, label in enumerate(labels, 1)) or "1. (TODO)"
    return (
        "---\n"
        f"name: {name}\n"
        "description: TODO — one line, plus 1-2 trigger phrases a user might "
        "say (see an existing Skills/*/SKILL.md for the format)\n"
        "aoo_dependency: full\n"
        "---\n\n"
        f"# {name}\n\n"
        "TODO — 이 스킬이 왜 필요한지 한 단락으로 설명한다. 근거: "
        f"`{kind}` 승인이 {count}회에 걸쳐 정확히 같은 체크리스트를 반복했다 "
        f"(approval ids: {approval_ids}).\n\n"
        "## 점검 절차\n\n"
        f"{steps}\n\n"
        "TODO — 각 단계를 실제 명령이나 판단 기준으로 구체화한다.\n\n"
        "> 절차 정본: `agent-eval autopilot skills detect`가 찾은 반복 패턴. "
        "만들기 전에 기존 Skills/의 스킬과 중복이 아닌지 반드시 확인한다"
        "(원칙4, 방법론서 §26.6).\n"
    )


def detect_repeated_undecided(
    decisions_path: Union[str, Path], min_occurrences: int = 5
) -> list[dict[str, Any]]:
    """exit 75(``--hold-on-undecided``)가 같은 사유로 반복되는지 찾는다.

    방법론서 §30: "이 기록이 5회 넘게 같은 사유로 반복되면, 그건 애매한
    게 아니라 임계값이 현실과 안 맞는 것"이라는 원칙을 그대로 센다 —
    기본 임계값도 5로 맞췄다. ``undecided_reason``이 같은 문자열인
    gate_run들을 묶는다(``rca/decision_ledger.py``의 스키마 그대로 사용,
    새 판정 로직 없음).

    Returns:
        ``[{"reason", "count", "gate_run_ids"}]``, ``count`` 내림차순.
        5회 미만인 사유는 아예 빠진다 — "개별 애매한 사례"와 "임계값
        자체의 문제"를 조기에 섞지 않기 위해서다.
    """
    from collections import defaultdict

    from agent_evaluator.rca.decision_ledger import load_decisions

    groups: dict[str, list[str]] = defaultdict(list)
    for e in load_decisions(decisions_path):
        if e.get("kind") != "gate_run" or e.get("exit_code") != 75:
            continue
        reason = e.get("undecided_reason")
        if not reason:
            continue
        groups[reason].append(e.get("id", ""))

    candidates = [
        {"reason": reason, "count": len(ids), "gate_run_ids": ids}
        for reason, ids in groups.items()
        if len(ids) >= min_occurrences
    ]
    candidates.sort(key=lambda c: -cast(int, c["count"]))
    return candidates


def open_threshold_reviews(
    approvals_path: Union[str, Path],
    decisions_path: Union[str, Path],
    min_occurrences: int = 5,
) -> list[dict[str, Any]]:
    """반복된 exit 75 사유마다 ``threshold_review`` 승인을 연다(멱등).

    같은 사유로 이미 열려 있는(``pending``/``draft``) 항목이 있으면
    다시 열지 않는다 — 매 실행마다 중복 카드가 쌓이는 걸 막는다.
    체크리스트는 ``threshold-realism-review`` 스킬의 4단계 파이프라인을
    그대로 항목화한다.

    중복 판정은 사유(``reason``) 문자열이 제목에 들어 있는지로 한다 —
    제목에 반복 횟수(``{count}회 반복``)가 박혀 있어서, 이전에 5회로 열어둔
    카드가 있는 상태에서 같은 사유가 6번째로 또 발생하면 제목 전체
    문자열은 더 이상 같지 않다. 예전엔 이 전체 문자열을 그대로
    대조해서, 카드가 열려 있는 동안 같은 사유가 한 번만 더 반복돼도
    중복 카드가 새로 열렸다(멱등성이 깨지는 실제 버그였다) — 그래서 여기선
    "이미 열린 제목 중 이 사유를 포함하는 게 있는가"만 본다.
    """
    candidates = detect_repeated_undecided(decisions_path, min_occurrences=min_occurrences)
    if not candidates:
        return []

    open_titles = [
        a.get("title", "")
        for a in load_approvals(approvals_path)
        if a.get("kind") == "threshold_review" and a.get("status") in ("pending", "draft")
    ]

    opened: list[dict[str, Any]] = []
    for c in candidates:
        if any(c["reason"] in t for t in open_titles):
            continue
        title = f"임계값 재검토 — \"{c['reason']}\" {c['count']}회 반복"
        approval = open_approval(
            approvals_path,
            task_id=PORTFOLIO_TASK_ID,
            kind="threshold_review",
            phase=7,
            title=title,
            checklist=[
                {"label": "설계자: 통계적으로 달성 가능한 임계값인가 판단", "status": "pending"},
                {"label": "개발자: agent-eval trend로 점수 분포 확인", "status": "pending"},
                {"label": "QA: RCA(5 Whys)로 새 임계값 정당화", "status": "pending"},
                {"label": "조직: .aoo/targets.json 갱신 + 확장 속도 결정", "status": "pending"},
            ],
            # 이 체크리스트는 "사람에게 보여줘도 되는 조건"이 아니라 "사람이 밟을
            # 4단계 절차" 그 자체다 — 게이트로 쓰면 절대 pending에 못 간다.
            gate_on_checklist=False,
        )
        opened.append(approval)
    return opened
