"""
agent_evaluator.cli._utils — 공유 CLI 유틸리티
"""
from __future__ import annotations

import argparse
import os
import re
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


_COLOR = _supports_color()

_R = "\033[0m" if _COLOR else ""
_B = "\033[1m" if _COLOR else ""   # bold
_Y = "\033[33m" if _COLOR else ""  # yellow
_C = "\033[36m" if _COLOR else ""  # cyan


class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """ANSI 색상이 적용된 argparse HelpFormatter — 모든 서브커맨드가 공유한다.

    TTY 여부는 모듈의 ``_COLOR``로 제어된다 (non-TTY에서는 색상 없음).
    """

    def start_section(self, heading: str | None) -> None:  # type: ignore[override]
        if heading and _COLOR:
            heading = f"{_B}{heading}{_R}"
        super().start_section(heading)

    def _format_usage(self, usage, actions, groups, prefix):  # type: ignore[override]
        if prefix is None:
            prefix = f"{_B}Usage{_R}: " if _COLOR else "Usage: "
        result = super()._format_usage(usage, actions, groups, prefix)
        if _COLOR:
            result = re.sub(r"\bagent-eval\b", f"{_C}agent-eval{_R}", result, count=1)
        return result

    def _format_action(self, action):  # type: ignore[override]
        result = super()._format_action(action)
        if not _COLOR:
            return result
        # --option 플래그 → 노란색
        result = re.sub(r"(--?[\w-]+)", f"{_Y}\\1{_R}", result)
        return result
