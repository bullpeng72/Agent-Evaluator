"""
agent_evaluator.gates.branch_guard
======================================
SPEC-035: 보호 브랜치 git 변경 차단 — LiveGuardrail 전용.

AI 세션이 main/master 같은 보호 브랜치에서 직접 git commit/push를 시도하는 것을
실행 전에 자동으로 차단한다. Ch28 §28.2 그라운드 룰("전용 브랜치")이 지금까지는
사람이 체크리스트로만 확인하던 것을, TeamConcurrencyConfig(SPEC-032)와 동일한
"생성자 시점 1회 조회" 원칙으로 기계적으로 강제한다.

현재 브랜치는 LiveGuardrail 생성 시점에 1회만 조회된다(agent_version="auto"가
이미 쓰는 것과 동일한 subprocess 패턴 재사용) — check_before_tool_call()의
순수 조회 계약을 지키기 위해 매 호출마다 재조회하지 않는다. 세션 도중 브랜치를
전환했다면 LiveGuardrail을 재생성해야 한다(SPEC-035 Non-Goals).
"""
from __future__ import annotations

import dataclasses
import re
import subprocess
from typing import Optional, Tuple


@dataclasses.dataclass
class BranchGuardConfig:
    """보호 브랜치 git 변경 차단 설정 (SPEC-035 REQ-1).

    Example::

        LiveGuardrail(branch_guard=BranchGuardConfig(
            protected_branches=("main", "master"),
        ))
    """
    protected_branches: Tuple[str, ...] = ("main", "master")
    git_mutation_patterns: Tuple[str, ...] = (r"git\s+commit", r"git\s+push")
    require_branch_prefix: Optional[str] = None
    scoped_tool_names: Tuple[str, ...] = ("bash",)
    fail_on_violation: bool = True


def get_current_branch() -> Optional[str]:
    """현재 git 브랜치 이름을 조회한다 (SPEC-035 REQ-2).

    git 미설치·비-git 디렉토리·타임아웃 등 어떤 실패든 예외 전파 없이 ``None``을
    반환한다 — ``monitor.py``의 ``agent_version="auto"``가 쓰는 것과 동일한
    fail-open 폴백 원칙(REQ-2).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        branch = result.stdout.strip() if result.returncode == 0 else None
        return branch or None
    except Exception:
        return None


def is_branch_protected(branch: Optional[str], config: BranchGuardConfig) -> bool:
    """``branch``가 ``config`` 기준으로 보호 대상인지 판정한다 (SPEC-035 REQ-3).

    ``branch``가 ``None``이면(비-git 환경 등 브랜치를 알 수 없는 경우) 차단하지
    않는다 — fail-open. git이 없는 환경에서 이 SDK를 쓰는 기존 사용자에게 새로운
    실패를 강제하지 않기 위함(SPEC-035 Non-Goals).
    """
    if branch is None:
        return False
    if branch in config.protected_branches:
        return True
    if config.require_branch_prefix and not branch.startswith(config.require_branch_prefix):
        return True
    return False


def matches_git_mutation(args_str: str, config: BranchGuardConfig) -> bool:
    """``args_str``(도구 호출 인자를 JSON 직렬화한 문자열)이 ``git_mutation_patterns``
    중 하나와 매치하는지 확인한다 (SPEC-035 REQ-5 헬퍼)."""
    return any(
        re.search(pattern, args_str, re.IGNORECASE)
        for pattern in config.git_mutation_patterns
        if isinstance(pattern, str) and pattern.strip()
    )
