"""
agent-eval opencode CLI — LiveGuardrail OpenCode 플러그인 설치.

명령어:
    agent-eval opencode install  번들된 플러그인(SPEC-019 참조 구현)을
                                 OpenCode 플러그인 디렉터리로 복사

agent_evaluator/integrations/opencode_plugin/agent-evaluator.ts는 판정 로직이 없는
얇은 stdio 클라이언트다 — Gate B/E 판정 로직의 유일한 소스는 항상
agent_evaluator.gates.live_guardrail.LiveGuardrail이며, 이 명령어는 그 클라이언트
파일을 OpenCode가 자동 로드하는 위치에 복사할 뿐이다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI helpers (main.py에서 직접 복사 불가 — 경량 재정의)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()
_B  = "\033[1m"  if _USE_COLOR else ""
_G  = "\033[32m" if _USE_COLOR else ""
_Y  = "\033[33m" if _USE_COLOR else ""
_RD = "\033[31m" if _USE_COLOR else ""
_D  = "\033[2m"  if _USE_COLOR else ""
_R  = "\033[0m"  if _USE_COLOR else ""

_PYTHON_PLACEHOLDER = "__AGENT_EVALUATOR_PYTHON_DEFAULT__"

_BUNDLED_PLUGIN = (
    Path(__file__).resolve().parent.parent
    / "integrations" / "opencode_plugin" / "agent-evaluator.ts"
)
_LOCAL_TARGET = Path(".opencode") / "plugin" / "agent-evaluator.ts"
_GLOBAL_TARGET = Path.home() / ".config" / "opencode" / "plugin" / "agent-evaluator.ts"


def cmd_opencode(args: argparse.Namespace) -> int:
    """opencode 서브커맨드 진입점."""
    cmd = getattr(args, "opencode_command", None)
    if cmd == "install":
        return _cmd_install(args)
    print(
        f"{_B}agent-eval opencode{_R} — LiveGuardrail OpenCode Plugin\n\n"
        f"  {_Y}install{_R}   Copy the bundled plugin into OpenCode's plugin directory\n\n"
        f"Usage: agent-eval opencode install --help",
        file=sys.stderr,
    )
    return 1


def _cmd_install(args: argparse.Namespace) -> int:
    """번들된 agent-evaluator.ts를 OpenCode 플러그인 디렉터리로 복사한다."""
    if not _BUNDLED_PLUGIN.exists():
        print(f"{_RD}❌ Bundled plugin not found: {_BUNDLED_PLUGIN}{_R}", file=sys.stderr)
        return 1

    is_global: bool = getattr(args, "global_install", False)
    force: bool = getattr(args, "force", False)
    target = _GLOBAL_TARGET if is_global else _LOCAL_TARGET

    if target.exists() and not force:
        print(
            f"{_Y}⚠️  Already exists: {target}{_R} — use --force to overwrite "
            f"(your edited GUARDRAIL_CONFIG will be lost)",
            file=sys.stderr,
        )
        return 1

    content = _BUNDLED_PLUGIN.read_text(encoding="utf-8")
    content = content.replace(_PYTHON_PLACEHOLDER, sys.executable)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    print(f"{_G}✅ Installed: {target}{_R}")
    print(f"{_D}   python interpreter (baked in as default): {sys.executable}{_R}")
    print()
    print(f"{_B}Next steps:{_R}")
    print(f"  1. Edit {target} — adjust GUARDRAIL_CONFIG for your project")
    print("     (edit the copy, not the package-bundled source — reinstalling overwrites it)")
    print("  2. Restart OpenCode (or start a new session) so it loads the plugin")
    print(
        f"  {_D}Full Config/tracker option reference: "
        f"agent_evaluator/gates/gate_b_behavioral/configs.py, "
        f"agent_evaluator/core/trackers/security.py{_R}"
    )
    return 0


def build_opencode_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """opencode 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "opencode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Install the LiveGuardrail OpenCode plugin (real-time Gate B/E guardrail)",
        description=(
            "Install the bundled OpenCode plugin (SPEC-019 LiveGuardrail reference\n"
            "implementation) into the location OpenCode auto-loads plugins from.\n"
            f"{_D}The plugin is a thin Node/Bun stdio client — the sole source of truth\n"
            f"for Gate B/E judgment logic always stays in the Python LiveGuardrail.{_R}"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode install{_R}\n"
            f"  {_G}agent-eval opencode install --global{_R}\n"
            f"  {_G}agent-eval opencode install --force{_R}\n"
        ),
    )
    op_sub = p.add_subparsers(dest="opencode_command")

    install_p = op_sub.add_parser(
        "install",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Copy the bundled plugin to the OpenCode plugin directory",
        description=(
            "Copy the bundled OpenCode plugin (agent-evaluator.ts) into the location\n"
            "OpenCode auto-loads plugins from, baking in the current Python\n"
            "interpreter's absolute path as the plugin's default PYTHON_BIN."
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode install{_R}          {_D}# .opencode/plugin/{_R}\n"
            f"  {_G}agent-eval opencode install --global{_R} {_D}# ~/.config/opencode/plugin/{_R}\n"
            f"  {_G}agent-eval opencode install --force{_R}  {_D}# overwrite existing{_R}\n"
        ),
    )
    install_p.add_argument(
        "--global", dest="global_install", action="store_true",
        help=(
            "Install to ~/.config/opencode/plugin/ (all projects) instead of the "
            "project-local .opencode/plugin/ (default)"
        ),
    )
    install_p.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing installed plugin file",
    )
