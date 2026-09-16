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
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

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
        return json.loads(path.read_text(encoding="utf-8"))
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
    }
    save_task(tasks_dir, task)
    return task


def transition_phase(
    tasks_dir: Union[str, Path],
    task_id: str,
    new_phase: int,
    mode: str = "auto",
    approved_by: str | None = None,
) -> dict[str, Any]:
    """Phase 전이(설계서 §3.3) — 이전 이력 항목을 닫고 새 항목을 연다."""
    task = load_task(tasks_dir, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")

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


def members_by_role(team_path: Union[str, Path], role: str) -> list[dict[str, Any]]:
    return [m for m in load_team(team_path) if role in m.get("roles", [])]


def find_member(team_path: Union[str, Path], id_or_name: str) -> dict[str, Any] | None:
    """id 또는 name으로 팀원을 찾는다(CLI 편의 — 새 과제 등록 시 담당자 검증용)."""
    for m in load_team(team_path):
        if m.get("id") == id_or_name or m.get("name") == id_or_name:
            return m
    return None
