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
    }
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


def compute_rejection_rate(
    approvals_path: Union[str, Path], window: int = 20
) -> dict[str, Any]:
    """최근 결정된 승인 중 반려율을 센다(부록 H.7 자가점검 — "HITL 관문 반려

    이력이 0건이다"는 원칙6 위반 신호, §9.5.4 순위4). 새 데이터가 필요
    없다 — ``.aoo/approvals.jsonl``에 이미 있는 결정 이력만 다시 읽는다
    (원칙4). ``pending``/``draft``(아직 결정 안 됨)는 분모에서 뺀다.

    Returns:
        ``{"window", "total", "rejected_or_changes_requested", "rejection_rate"}``.
        ``rejection_rate``는 결정된 항목이 하나도 없으면 ``None``이다
        ("0%"과 "아직 아무도 결정 안 함"은 다른 상태다).
    """
    decided = [
        a
        for a in load_approvals(approvals_path)
        if a.get("status") in ("approved", "rejected", "changes_requested")
    ]
    decided.sort(key=lambda a: a.get("decided_at") or "")
    recent = decided[-window:] if window else decided

    total = len(recent)
    non_approved = sum(1 for a in recent if a.get("status") != "approved")
    rate = (non_approved / total) if total else None

    return {
        "window": window,
        "total": total,
        "rejected_or_changes_requested": non_approved,
        "rejection_rate": rate,
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

    Returns:
        ``[{"kind", "labels": tuple[str, ...], "count", "approval_ids"}]``,
        ``count`` 내림차순.
    """
    from collections import defaultdict

    groups: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    for a in load_approvals(approvals_path):
        labels = tuple(sorted(c.get("label", "") for c in a.get("checklist") or []))
        if not labels:
            continue
        key = (a.get("kind", ""), labels)
        groups[key].append(a.get("id", ""))

    candidates = [
        {"kind": kind, "labels": labels, "count": len(ids), "approval_ids": ids}
        for (kind, labels), ids in groups.items()
        if len(ids) >= min_occurrences
    ]
    candidates.sort(key=lambda c: -cast(int, c["count"]))
    return candidates


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
