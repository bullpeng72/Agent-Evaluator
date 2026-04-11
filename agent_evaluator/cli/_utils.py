"""
agent_evaluator.cli._utils — 공유 CLI 유틸리티
"""
from __future__ import annotations

import os
import sys


def _supports_color() -> bool:
    """터미널이 ANSI 색상을 지원하는지 확인한다."""
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Windows: ANSICON 또는 Windows Terminal 환경 확인
        return "ANSICON" in os.environ or "WT_SESSION" in os.environ
    return True
