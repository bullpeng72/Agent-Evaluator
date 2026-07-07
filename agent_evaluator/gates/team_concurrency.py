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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


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
    """

    claims_path: str = ".aoo/claims.jsonl"
    shared_files_path: Optional[str] = None
    scoped_tool_names: Tuple[str, ...] = ("read", "edit", "write")
    path_param_candidates: Tuple[str, ...] = ("file", "filePath", "path")
    fail_on_conflict: bool = True


def load_active_claims(claims_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """``claims_path``에서 ``status == "active"``인 최신 클레임만 읽어 반환한다.

    클레임 로그는 append-only JSON Lines다 — 각 줄이 클레임 개설(active) 또는
    해제(released) 이벤트 하나이고, 같은 ``claim_id``의 최신 상태만 유효하다(§28.5).

    Args:
        claims_path: ``.aoo/claims.jsonl`` 경로. 파일이 없으면 빈 리스트.

    Returns:
        활성 클레임 dict 리스트(각각 ``claim_id``/``developer``/``scope``/... 포함).
    """
    latest_by_id: Dict[str, Dict[str, Any]] = {}
    path = Path(claims_path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            latest_by_id[entry["claim_id"]] = {**latest_by_id.get(entry["claim_id"], {}), **entry}
    return [claim for claim in latest_by_id.values() if claim.get("status") == "active"]


def _scopes_overlap(path_a: str, scopes: List[str]) -> bool:
    """prefix 겹침 판정 — ``p1 == p2 or p1.startswith(p2) or p2.startswith(p1)``와
    동일한 원칙(``check_scope_claim()``이 이미 쓰던 로직, 재해석 없음)."""
    return any(path_a == s or path_a.startswith(s) or s.startswith(path_a) for s in scopes)


def check_scope_claim(
    proposed_scope: List[str], claims_path: Union[str, Path] = ".aoo/claims.jsonl",
) -> List[Dict[str, Any]]:
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


def _load_shared_files(shared_files_path: Optional[str]) -> List[str]:
    """``shared_files_path``의 비어있지 않은 줄만 읽어 반환한다. ``None``이거나
    파일이 없으면 빈 리스트(에러 아님)."""
    if shared_files_path is None:
        return []
    path = Path(shared_files_path)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_path_param(
    parameters: Optional[dict], candidates: Tuple[str, ...],
) -> Optional[str]:
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
