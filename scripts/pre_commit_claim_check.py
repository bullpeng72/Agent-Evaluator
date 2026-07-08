#!/usr/bin/env python3
"""
scripts/pre_commit_claim_check.py
=====================================
`.aoo/claims.jsonl` 정합성 + 보호 브랜치 커밋을 커밋 전에 로컬에서 차단한다.

`TeamConcurrencyConfig`/`BranchGuardConfig`(Ch27 §27.8, §27.4)는 AI 에이전트의
도구 호출(`LiveGuardrail.check_before_tool_call()`)만 검사한다 — 사람이 터미널에서
직접 `git commit`을 치면 이 검사를 전혀 거치지 않는다. 이 스크립트는 같은 판정
함수(`audit_claims()`, SPEC-034 / `get_current_branch()`+`is_branch_protected()`,
SPEC-035)를 재사용해 그 빈틈을 커밋 시점에 한 번 더 메운다 — 새 판정 로직은
추가하지 않는다.

pre-commit 프레임워크 연동(``.pre-commit-config.yaml``)::

    repos:
      - repo: local
        hooks:
          - id: aoo-claim-check
            name: AOO claim log + branch guard check
            entry: python scripts/pre_commit_claim_check.py
            language: system
            pass_filenames: false
            always_run: true

프레임워크 없이 순수 git 훅으로 쓰려면 ``.git/hooks/pre-commit``에 아래 두 줄만
추가한다(실행 권한 필요: ``chmod +x .git/hooks/pre-commit``)::

    #!/bin/sh
    python scripts/pre_commit_claim_check.py || exit 1

종료 코드:
    0 — 위반 없음(커밋 진행)
    1 — 클레임 위반 또는 보호 브랜치 위반(커밋 차단)
"""
from __future__ import annotations

import sys

from agent_evaluator.gates.branch_guard import (
    BranchGuardConfig,
    get_current_branch,
    is_branch_protected,
)
from agent_evaluator.gates.team_concurrency import audit_claims

_CLAIMS_PATH = ".aoo/claims.jsonl"
_TTL_HOURS = 8.0
_PROTECTED_BRANCHES = ("main", "master")


def check_claims(claims_path: str = _CLAIMS_PATH, ttl_hours: float = _TTL_HOURS) -> bool:
    """클레임 로그 위반이 있으면 출력하고 ``False``를 반환한다."""
    violations = audit_claims(claims_path, ttl_hours=ttl_hours)
    if not violations:
        return True

    print(f"❌ 클레임 로그 위반 {len(violations)}건 발견 ({claims_path})", file=sys.stderr)
    for v in violations:
        if v["type"] == "ttl_exceeded":
            print(
                f"  TTL 초과  claim_id={v['claim_id']}  developer={v['developer']}  "
                f"경과={v['age_hours']}h  (기준 {ttl_hours}h)  "
                f"— agent-eval claims release {v['claim_id']}로 해제하세요",
                file=sys.stderr,
            )
        elif v["type"] == "overlapping_claims":
            print(
                f"  스코프 겹침  {v['claim_id_a']}({v['developer_a']}) "
                f"↔ {v['claim_id_b']}({v['developer_b']})  scope={v['scope']}",
                file=sys.stderr,
            )
    return False


def check_branch(protected: tuple = _PROTECTED_BRANCHES) -> bool:
    """현재 브랜치가 보호 브랜치이면 출력하고 ``False``를 반환한다."""
    config = BranchGuardConfig(protected_branches=protected)
    branch = get_current_branch()
    if not is_branch_protected(branch, config):
        return True

    print(
        f"❌ 보호 브랜치({branch})에서 직접 커밋을 시도했습니다. "
        f"전용 브랜치를 만들어 작업하세요(Chapter 28 §28.2).",
        file=sys.stderr,
    )
    return False


def main() -> int:
    claims_ok = check_claims()
    branch_ok = check_branch()
    return 0 if (claims_ok and branch_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
