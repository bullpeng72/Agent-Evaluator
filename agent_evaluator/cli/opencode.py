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
import subprocess as subprocess  # re-export: tests monkeypatch opencode.subprocess.run directly
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

# Harness Method Ch06 §6.2 — 훅이 하나라도 빠지면 실시간 차단은 되는데 배치 채점
# 데이터는 하나도 안 쌓이는 "절반만 작동하는 상태"를 알아채기 어렵다. 온보딩
# 체크리스트에만 맡기는 대신 설치 시점에 자동으로 확인한다.
_REQUIRED_HOOKS: tuple[tuple[str, str], ...] = (
    ('"tool.execute.before":', "tool.execute.before"),
    ('"tool.execute.after":', "tool.execute.after"),
    ("event:", "event"),
)


def _missing_hooks(content: str) -> list[str]:
    """설치될 내용에 세 훅이 전부 등록돼 있는지 확인해 빠진 것의 이름을 반환한다."""
    return [label for marker, label in _REQUIRED_HOOKS if marker not in content]

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


_VIOLATION_SEARCH_MCP_NAME = "agent-evaluator-violations"


def _register_violation_search_mcp() -> None:
    """(SPEC-024 REQ-6) ``opencode mcp add``로 REQ-4의 stdio MCP 서버를 등록한다.

    실패해도(``opencode`` CLI 미설치, 사용자가 ``mcp`` extra 미설치 등) 경고만
    출력하고 예외를 올리지 않는다 — 플러그인 설치 자체(``_cmd_install``의 본래
    목적)는 이 등록 성공 여부와 무관하게 이미 끝난 뒤이므로, 이 단계의 실패로
    전체 install 명령을 실패 처리할 이유가 없다(``live_guardrail_report.py`` 저장
    실패가 세션 종료를 막지 않는 것과 동일한 원칙, SPEC-019 Rollout 6단계 참고).
    """
    try:
        result = subprocess.run(
            [
                "opencode", "mcp", "add", _VIOLATION_SEARCH_MCP_NAME, "--",
                sys.executable, "-m", "agent_evaluator.integrations.violation_search_mcp",
            ],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print(
            f"{_Y}⚠️  --with-violation-search: 'opencode' CLI를 찾지 못해 MCP 서버 등록을 "
            f"건너뜁니다. 수동 등록: opencode mcp add {_VIOLATION_SEARCH_MCP_NAME} -- "
            f"{sys.executable} -m agent_evaluator.integrations.violation_search_mcp{_R}",
            file=sys.stderr,
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"{_Y}⚠️  --with-violation-search: 'opencode mcp add' 호출이 시간 초과됐습니다 "
            f"— 수동으로 등록하세요.{_R}",
            file=sys.stderr,
        )
        return

    if result.returncode == 0:
        print(f"{_G}✅ MCP server registered: {_VIOLATION_SEARCH_MCP_NAME}{_R}")
    else:
        print(
            f"{_Y}⚠️  --with-violation-search: 'opencode mcp add' 실패(exit "
            f"{result.returncode}) — 수동 등록: opencode mcp add "
            f"{_VIOLATION_SEARCH_MCP_NAME} -- {sys.executable} -m "
            f"agent_evaluator.integrations.violation_search_mcp{_R}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"{_D}   {result.stderr.strip()}{_R}", file=sys.stderr)


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

    missing = _missing_hooks(content)
    if missing:
        print(
            f"{_RD}⚠️  Warning: the installed plugin is missing hook(s): "
            f"{', '.join(missing)}{_R}\n"
            f"{_D}   Real-time blocking and/or batch reporting may silently not work — "
            f"this should never happen with the bundled plugin (agent_evaluator/"
            f"integrations/opencode_plugin/agent-evaluator.ts); please file an issue.{_R}",
            file=sys.stderr,
        )

    if getattr(args, "with_violation_search", False):
        print()
        _register_violation_search_mcp()

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
            f"  {_G}agent-eval opencode install --with-violation-search{_R}\n"
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
            f"  {_G}agent-eval opencode install{_R} {_D}# .opencode/plugin/{_R}\n"
            f"  {_G}agent-eval opencode install --global{_R} {_D}# ~/.config/opencode/plugin/{_R}\n"
            f"  {_G}agent-eval opencode install --force{_R} {_D}# overwrite existing{_R}\n"
            f"  {_G}agent-eval opencode install --with-violation-search{_R}\n"
            f"      {_D}# + register search_violations MCP server{_R}\n"
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
    install_p.add_argument(
        "--with-violation-search", dest="with_violation_search", action="store_true",
        help=(
            "(SPEC-024 REQ-6) Also run 'opencode mcp add' to register the "
            "search_violations MCP server (opt-in, requires the 'mcp' extra: "
            "pip install \"agent-evaluator[mcp]\")"
        ),
    )
