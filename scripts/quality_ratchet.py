#!/usr/bin/env python3
"""
scripts/quality_ratchet.py
=============================
SPEC-021: 코드 품질 부채 래칫 — ruff/mypy 오류 수가 `.github/quality-baseline.json`의
baseline보다 늘어나면 실패한다. 기존 부채(도입 시점 4,120건/318건)를 전부 정리하는 대신,
"이번 변경이 부채를 늘렸는가"만 검사해 CI에서 부채 증가를 막는다.

baseline을 낮추는 것(부채를 실제로 줄인 뒤)은 사람이 `.github/quality-baseline.json`을
직접 수정하는 명시적 행위로 남긴다 — 이 스크립트는 자동으로 baseline을 낮추지 않는다.

실행::

    python scripts/quality_ratchet.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / ".github" / "quality-baseline.json"


def count_ruff_errors() -> int:
    """`ruff check --output-format=json`의 출력 배열 길이 = 위반 건수."""
    result = subprocess.run(
        ["ruff", "check", "agent_evaluator/", "--output-format=json"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    return len(json.loads(result.stdout or "[]"))


def count_mypy_errors() -> int:
    """mypy stdout에서 `": error:"`를 포함하는 줄의 수 = 오류 건수(별도 JSON 출력 없음)."""
    result = subprocess.run(
        ["mypy", "agent_evaluator/"], capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    return sum(1 for line in result.stdout.splitlines() if ": error:" in line)


def main() -> int:
    baseline = json.loads(_BASELINE_PATH.read_text())
    current = {"ruff_errors": count_ruff_errors(), "mypy_errors": count_mypy_errors()}

    failed = False
    for key, current_count in current.items():
        baseline_count = baseline.get(key, 0)
        if current_count > baseline_count:
            delta = current_count - baseline_count
            print(f"FAIL: {key} increased from {baseline_count} to {current_count} (+{delta})")
            failed = True
        else:
            print(f"OK: {key} = {current_count} (baseline {baseline_count})")

    if failed:
        print()
        print("Quality ratchet failed — this change increased lint/type debt.")
        print(
            f"If you intentionally reduced debt, update {_BASELINE_PATH.relative_to(_REPO_ROOT)} "
            "to the new lower count."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
