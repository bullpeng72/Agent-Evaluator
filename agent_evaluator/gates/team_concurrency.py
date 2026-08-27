"""
agent_evaluator.gates.team_concurrency
==========================================
SPEC-032: `.aoo/claims.jsonl` 기반 다중 세션 스코프 충돌 감지 — 축소 범위.

``check_scope_claim()``/``append_claim()``은 ``Evaluator_Examples/ch28_local_ade_loop.py``
섹션 6의 예제 전용 코드를 그대로 승격한 것이다(로직 재해석 없음) — 세션 시작 *전*
사람이 직접 호출해 스코프 겹침을 확인하는 절차용이다. ``TeamConcurrencyConfig``는
이 확인을 ``LiveGuardrail.check_before_tool_call()``에 연결해, 구조화된 파일 경로
파라미터를 갖는 도구(``read``/``edit``/``write``)에 한해 세션 *도중*에도 자동으로
검사되게 한다 — ``bash`` 같은 자유 형식 도구는 파일 경로를 안정적으로 파싱할 방법이
없어 대상에서 제외한다(1차 검토에서 확인된 미해결 문제, SPEC-032 Non-Goals).

클레임은 ``LiveGuardrail`` 생성 시점에 **1회만** 로드된다 — 매 도구 호출마다
``claims_path``를 재조회하지 않는다(``check_before_tool_call()``의 "순수 조회,
외부 I/O 없음" 계약 유지).
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union


@dataclasses.dataclass
class TeamConcurrencyConfig:
    """``LiveGuardrail(team_concurrency=...)``에 전달하는 설정 (SPEC-032 REQ-2).

    Attributes:
        claims_path: ``.aoo/claims.jsonl`` 경로.
        shared_files_path: 클레임 여부와 무관하게 항상 조율이 필요한 파일 목록
            (한 줄에 경로 하나). ``None``(기본값)이면 이 검사를 하지 않는다.
        scoped_tool_names: 이 검사 대상이 되는 도구 이름. 기본값은 구조화된
            파일 경로 파라미터를 갖는 도구만 — ``bash``는 의도적으로 제외.
        path_param_candidates: 도구 호출 ``parameters``에서 파일 경로를 찾을
            후보 키, 순서대로 시도한다. 못 찾으면 이 도구 호출에 대해서만
            검사를 건너뛴다(오탐 대신 안전한 폴백).
        fail_on_conflict: ``True``(기본값)면 겹침 발견 시 실제로 차단한다.
        owner: (SPEC-036) 이 세션을 운영하는 개발자 이름. 클레임 로그의
            ``developer`` 필드와 정확히 일치하면, 그 클레임은 충돌 검사에서
            제외된다 — 자기 자신이 정당하게 건 클레임이 자기 세션을 막지
            않게 하기 위함. ``None``(기본값)이면 예외를 적용하지 않는다
            (기존 동작 그대로 — 자기 자신의 클레임도 충돌로 잡힌다).

            (SPEC-037) ``"auto"``는 예약 센티널이다 — ``LiveGuardrail`` 생성
            시점에 ``git config user.name``을 1회 조회해 그 값으로 치환한다
            (``agent_version="auto"``, SPEC-027과 동일한 패턴). git 미설치·
            ``user.name`` 미설정 등 어떤 이유로든 조회에 실패하면 예외 없이
            ``None``으로 조용히 떨어진다 — 이 경우 기존 동작(자기 자신의
            클레임도 충돌로 잡힘)이 그대로 유지된다. ``"auto"`` 외의 다른
            문자열이나 ``None``은 이전과 동일하게 그대로 사용된다.
    """

    claims_path: str = ".aoo/claims.jsonl"
    shared_files_path: str | None = None
    # SPEC-041: OpenCode(read/edit/write) + Claude Code(Read/Edit/Write/MultiEdit/
    # NotebookEdit) 둘 다 커버. check_before_tool_call() 매칭도 대소문자 무시.
    scoped_tool_names: tuple[str, ...] = (
        "read", "Read", "edit", "Edit", "write", "Write", "MultiEdit", "NotebookEdit",
    )
    # OpenCode(file/filePath/path) + Claude Code(file_path/notebook_path) + MCP(path).
    path_param_candidates: tuple[str, ...] = (
        "file", "filePath", "file_path", "path", "notebook_path", "notebookPath",
    )
    fail_on_conflict: bool = True
    owner: str | None = None


def resolve_owner(owner: str | None) -> str | None:
    """``owner`` 필드의 ``"auto"`` 센티널을 해석한다 (SPEC-037).

    ``"auto"``가 아니면(``None`` 포함) 인자를 그대로 반환한다 — 이 함수는
    센티널 값 하나만 처리하는 순수 변환이다.

    ``"auto"``이면 ``git config user.name``을 1회 조회해 그 결과를 반환한다.
    git 미설치, 리포지토리 밖, ``user.name`` 미설정 등 어떤 이유로든 조회에
    실패하거나 빈 문자열이 나오면 예외를 전파하지 않고 ``None``을 반환한다
    (``agent_version="auto"``의 git 조회와 동일한 fail-open 원칙,
    ``core/trackers/monitor.py``의 ``self._git_commit`` 계산부 참고).

    Args:
        owner: ``TeamConcurrencyConfig.owner``에 설정된 원본 값.

    Returns:
        해석된 owner 문자열, 또는 조회 실패/미해당 시 원본 값 그대로
        (``"auto"``였다면 ``None``).
    """
    if owner != "auto":
        return owner
    try:
        import subprocess as _subprocess
        _result = _subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=2,
        )
        _name = _result.stdout.strip() if _result.returncode == 0 else ""
        return _name or None
    except Exception:
        return None


def load_active_claims(claims_path: Union[str, Path]) -> list[dict[str, Any]]:
    """``claims_path``에서 ``status == "active"``인 최신 클레임만 읽어 반환한다.

    클레임 로그는 append-only JSON Lines다 — 각 줄이 클레임 개설(active) 또는
    해제(released) 이벤트 하나이고, 같은 ``claim_id``의 최신 상태만 유효하다(§28.5).

    Args:
        claims_path: ``.aoo/claims.jsonl`` 경로. 파일이 없으면 빈 리스트.

    Returns:
        활성 클레임 dict 리스트(각각 ``claim_id``/``developer``/``scope``/... 포함).
    """
    latest_by_id: dict[str, dict[str, Any]] = {}
    path = Path(claims_path)
    try:
        _text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        _text = ""
    for line in _text.splitlines():
        if not line.strip():
            continue
        # SPEC-041: 손상된 줄(부분 write·수동 편집 실수) 하나가 전체 로드를 깨거나
        # LiveGuardrail 생성을 실패시키면 안 된다 — 그 줄만 건너뛴다(append-only 로그의
        # 다른 이력은 유효). claim_id 없는 줄도 무시.
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or not entry.get("claim_id"):
            continue
        _cid = entry["claim_id"]
        latest_by_id[_cid] = {**latest_by_id.get(_cid, {}), **entry}
    return [claim for claim in latest_by_id.values() if claim.get("status") == "active"]


def _scopes_overlap(path_a: str, scopes: list[str]) -> bool:
    """prefix 겹침 판정 — ``p1 == p2 or p1.startswith(p2) or p2.startswith(p1)``와
    동일한 원칙(``check_scope_claim()``이 이미 쓰던 로직, 재해석 없음)."""
    return any(path_a == s or path_a.startswith(s) or s.startswith(path_a) for s in scopes)


def check_scope_claim(
    proposed_scope: list[str], claims_path: Union[str, Path] = ".aoo/claims.jsonl",
) -> list[dict[str, Any]]:
    """활성 클레임 중 ``proposed_scope``와 겹치는 것이 있으면 반환한다 (SPEC-032 REQ-1).

    ``Evaluator_Examples/ch28_local_ade_loop.py`` 섹션 6의 예제 코드를 그대로
    승격한 것 — 세션을 시작하기 *전* 사람이 직접 호출해야 한다(§28.2 그라운드 룰).
    ``LiveGuardrail``은 이 확인을 대신해주지 않는다 — 세션 *도중* 자동 검사가
    필요하면 ``TeamConcurrencyConfig``를 쓸 것.

    Args:
        proposed_scope: 이 세션이 작업하려는 경로/디렉토리 목록.
        claims_path: ``.aoo/claims.jsonl`` 경로.

    Returns:
        겹치는 활성 클레임 dict 리스트. 없으면 빈 리스트.
    """
    return [
        claim for claim in load_active_claims(claims_path)
        if any(_scopes_overlap(p, claim.get("scope", [])) for p in proposed_scope)
    ]


def append_claim(claims_path: Union[str, Path], **fields: Any) -> None:
    """클레임 로그에 이벤트 한 줄을 append한다(개설 또는 해제) (SPEC-032 REQ-1)."""
    with open(claims_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(fields, ensure_ascii=False) + "\n")


def audit_claims(
    claims_path: Union[str, Path] = ".aoo/claims.jsonl", ttl_hours: float = 8.0,
) -> list[dict[str, Any]]:
    """CI에서 클레임 로그의 정합성을 점검한다 (SPEC-034 REQ-1~4).

    TTL을 초과하도록 해제되지 않은 활성 클레임과, 스코프가 겹치는 두 개 이상의
    활성 클레임을 찾는다. ``load_active_claims()``(SPEC-032)를 그대로 재사용하므로
    "같은 claim_id는 최신 상태만 유효하다"는 규칙을 다시 구현하지 않는다 — 이미
    해제된 클레임이 여기서 다시 위반으로 잡히는 일은 없다.

    Args:
        claims_path: ``.aoo/claims.jsonl`` 경로.
        ttl_hours: 이 시간을 넘도록 해제되지 않은 활성 클레임을 위반으로 본다.

    Returns:
        위반 dict 리스트. 비어 있으면 위반 없음(``sys.exit()``은 호출하지 않는다 —
        CI 종료 코드 결정은 호출자의 몫).
    """
    claims = load_active_claims(claims_path)
    violations: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for claim in claims:
        started_at = claim.get("started_at")
        if not started_at:
            continue
        try:
            started = datetime.fromisoformat(started_at)
        except ValueError:
            continue  # 파싱 불가능한 타임스탬프는 조용히 건너뜀 — TTL 판정 불가로 예외 전파 방지
        if started.tzinfo is None:
            # naive는 UTC로 간주 — offset-aware datetime.now(timezone.utc)와 뺄셈 가능하게
            started = started.replace(tzinfo=timezone.utc)
        age_hours = (now - started).total_seconds() / 3600
        if age_hours > ttl_hours:
            violations.append({
                "type": "ttl_exceeded",
                "claim_id": claim.get("claim_id"),
                "developer": claim.get("developer"),
                "scope": claim.get("scope", []),
                "age_hours": round(age_hours, 2),
            })

    for i, c1 in enumerate(claims):
        for c2 in claims[i + 1:]:
            _scope1 = c1.get("scope", [])
            _scope2 = c2.get("scope", [])
            if any(_scopes_overlap(p, _scope2) for p in _scope1):
                violations.append({
                    "type": "overlapping_claims",
                    "claim_id_a": c1.get("claim_id"),
                    "developer_a": c1.get("developer"),
                    "claim_id_b": c2.get("claim_id"),
                    "developer_b": c2.get("developer"),
                    "scope": _scope1,
                })

    return violations


def _load_shared_files(shared_files_path: str | None) -> list[str]:
    """``shared_files_path``의 비어있지 않은 줄만 읽어 반환한다. ``None``이거나
    파일이 없으면 빈 리스트(에러 아님)."""
    if shared_files_path is None:
        return []
    path = Path(shared_files_path)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_path_param(
    parameters: dict | None, candidates: tuple[str, ...],
) -> str | None:
    """``parameters``에서 ``candidates`` 순서로 첫 문자열 값을 찾는다 (SPEC-032 REQ-4).

    못 찾으면 ``None`` — 호출자는 이 경우 team_concurrency 검사를 건너뛴다
    (신호 없음 = 차단 안 함, SPEC-031과 동일한 원칙).
    """
    if not parameters:
        return None
    for key in candidates:
        value = parameters.get(key)
        if isinstance(value, str) and value:
            return value
    return None
