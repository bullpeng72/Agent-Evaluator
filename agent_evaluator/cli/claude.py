"""
agent-eval claude CLI — Claude Code CLI 훅 기반 LiveGuardrail 통합.

``agent_evaluator/integrations/claude_code_hook.py``는 판정 로직이 없는 얇은 훅 브리지다 —
Gate B/E 판정 로직의 유일한 소스는 항상 ``agent_evaluator.gates.live_guardrail.LiveGuardrail``이며,
이 명령어는 (1) ``.claude/settings.json``에 ``PreToolUse``/``PostToolUse``/``SessionEnd`` 훅을
등록하고 (2) 기본 guardrail 설정을 ``.claude/.agent-evaluator/guardrail_config.json``에 복사할
뿐이다.

OpenCode installer(``cli/opencode.py``)와 달리 훅 스크립트 자체는 파일 복사가 필요 없다 —
Claude Code 훅은 설치된 패키지를 ``python -m agent_evaluator.integrations.claude_code_hook``으로
직접 호출하므로, 재설치 보호가 필요한 대상은 ``guardrail_config.json`` 하나뿐이다.
"""
from __future__ import annotations

import argparse
import json
import subprocess as subprocess  # re-export: tests monkeypatch claude.subprocess.run directly
import sys
from pathlib import Path

from agent_evaluator.integrations.claude_code_hook import DEFAULT_GUARDRAIL_CONFIG

# ---------------------------------------------------------------------------
# ANSI helpers (main.py에서 직접 복사 불가 — 경량 재정의, opencode.py와 동일 패턴)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()
_B  = "\033[1m"  if _USE_COLOR else ""
_G  = "\033[32m" if _USE_COLOR else ""
_Y  = "\033[33m" if _USE_COLOR else ""
_RD = "\033[31m" if _USE_COLOR else ""
_D  = "\033[2m"  if _USE_COLOR else ""
_R  = "\033[0m"  if _USE_COLOR else ""

_HOOK_MODULE = "agent_evaluator.integrations.claude_code_hook"
# PreToolUse/PostToolUse matchers filter by *tool name* — SessionEnd's matcher filters by
# session-end *reason* (clear/logout/prompt_input_exit/...) instead, so reusing the tool-name
# matcher there would silently never match and the batch-save hook would never fire. "*" means
# "match all" for SessionEnd (there's no tool name to restrict it by).
_HOOK_MATCHERS: dict[str, str] = {
    "PreToolUse": "Bash|Edit|Write",
    "PostToolUse": "Bash|Edit|Write",
    "SessionEnd": "*",
}
_HOOK_EVENTS: tuple[str, ...] = tuple(_HOOK_MATCHERS)

_LOCAL_SETTINGS = Path(".claude") / "settings.json"
_GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
_LOCAL_CONFIG = Path(".claude") / ".agent-evaluator" / "guardrail_config.json"
_GLOBAL_CONFIG = Path.home() / ".claude" / ".agent-evaluator" / "guardrail_config.json"

_VIOLATION_SEARCH_MCP_NAME = "agent-evaluator-violations"
_RECOMMEND_FIX_MCP_NAME = "agent-evaluator-recommend-fix"


def cmd_claude(args: argparse.Namespace) -> int:
    """claude 서브커맨드 진입점."""
    cmd = getattr(args, "claude_command", None)
    if cmd == "install":
        return _cmd_install(args)
    print(
        f"{_B}agent-eval claude{_R} — LiveGuardrail Claude Code CLI hooks\n\n"
        f"  {_Y}install{_R}   Register PreToolUse/PostToolUse/SessionEnd hooks in "
        f".claude/settings.json\n\n"
        f"Usage: agent-eval claude install --help",
        file=sys.stderr,
    )
    return 1


def _hook_entry(python_bin: str, event: str) -> dict:
    return {
        "matcher": _HOOK_MATCHERS[event],
        "hooks": [{"type": "command", "command": f"{python_bin} -m {_HOOK_MODULE}"}],
    }


def _has_our_hook(entries: list) -> bool:
    for entry in entries or []:
        for h in entry.get("hooks", []):
            if _HOOK_MODULE in (h.get("command") or ""):
                return True
    return False


def _merge_settings(existing: dict, python_bin: str) -> tuple[dict, list[str]]:
    """기존 ``settings.json``에 세 훅을 병합한다.

    이미 있는 다른 훅/설정은 그대로 보존한다 — 무조건 덮어쓰지 않는다(OpenCode installer의
    단순 파일 복사와 달리, Claude Code의 ``settings.json``은 사용자가 이미 다른 훅을 등록해
    뒀을 수 있는 공유 파일이라 read-modify-write가 필요하다).

    Returns:
        ``(병합된 settings dict, 새로 추가된 이벤트 이름 목록)``. 이미 등록된 이벤트는
        건너뛴다(재설치 시 중복 추가 방지) — 목록이 비어 있으면 이미 전부 등록된 상태다.
    """
    merged = dict(existing)
    hooks = dict(merged.get("hooks") or {})
    added: list[str] = []
    for event in _HOOK_EVENTS:
        entries = list(hooks.get(event) or [])
        if _has_our_hook(entries):
            continue
        entries.append(_hook_entry(python_bin, event))
        hooks[event] = entries
        added.append(event)
    merged["hooks"] = hooks
    return merged, added


def _register_mcp_server(name: str, module: str, flag: str, scope: str) -> None:
    """``claude mcp add``로 ``module``의 stdio MCP 서버를 등록한다.

    ``opencode.py``의 ``_register_mcp_server()``와 동일한 원칙 — 실패해도(``claude`` CLI
    미설치, ``mcp`` extra 미설치 등) 경고만 출력하고 예외를 올리지 않는다. 설치 자체(``install``의
    본래 목적)는 이 등록 성공 여부와 무관하게 이미 끝난 뒤이므로, 이 단계의 실패로 전체 install
    명령을 실패 처리할 이유가 없다.
    """
    _manual = f"claude mcp add {name} --scope {scope} -- {sys.executable} -m {module}"
    try:
        result = subprocess.run(
            ["claude", "mcp", "add", name, "--scope", scope, "--", sys.executable, "-m", module],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print(
            f"{_Y}⚠️  {flag}: 'claude' CLI를 찾지 못해 MCP 서버 등록을 건너뜁니다. "
            f"수동 등록: {_manual}{_R}",
            file=sys.stderr,
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"{_Y}⚠️  {flag}: 'claude mcp add' 호출이 시간 초과됐습니다 — 수동으로 등록하세요.{_R}",
            file=sys.stderr,
        )
        return

    if result.returncode == 0:
        print(f"{_G}✅ MCP server registered: {name}{_R}")
    else:
        print(
            f"{_Y}⚠️  {flag}: 'claude mcp add' 실패(exit {result.returncode}) — "
            f"수동 등록: {_manual}{_R}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"{_D}   {result.stderr.strip()}{_R}", file=sys.stderr)


def _register_violation_search_mcp(scope: str) -> None:
    _register_mcp_server(
        _VIOLATION_SEARCH_MCP_NAME, "agent_evaluator.integrations.violation_search_mcp",
        "--with-violation-search", scope,
    )


def _register_recommend_fix_mcp(scope: str) -> None:
    _register_mcp_server(
        _RECOMMEND_FIX_MCP_NAME, "agent_evaluator.integrations.recommend_fix_mcp",
        "--with-recommend-fix", scope,
    )


def _cmd_install(args: argparse.Namespace) -> int:
    is_global: bool = getattr(args, "global_install", False)
    force: bool = getattr(args, "force", False)
    settings_path = _GLOBAL_SETTINGS if is_global else _LOCAL_SETTINGS
    config_path = _GLOBAL_CONFIG if is_global else _LOCAL_CONFIG
    scope = "user" if is_global else "local"

    existing_settings: dict = {}
    if settings_path.exists():
        try:
            existing_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{_RD}❌ Failed to parse existing {settings_path}: {exc}{_R}", file=sys.stderr)
            return 1

    merged, added = _merge_settings(existing_settings, sys.executable)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    if added:
        print(f"{_G}✅ Registered hooks in {settings_path}: {', '.join(added)}{_R}")
    else:
        print(f"{_D}   Hooks already registered in {settings_path} — nothing to add{_R}")

    if config_path.exists() and not force:
        print(
            f"{_Y}⚠️  Guardrail config already exists: {config_path}{_R} — use --force to reset "
            f"to defaults (your edits will be lost)",
        )
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(DEFAULT_GUARDRAIL_CONFIG, indent=2) + "\n", encoding="utf-8",
        )
        print(f"{_G}✅ Wrote default guardrail config: {config_path}{_R}")

    if getattr(args, "with_violation_search", False):
        print()
        _register_violation_search_mcp(scope)

    if getattr(args, "with_recommend_fix", False):
        print()
        _register_recommend_fix_mcp(scope)

    print()
    print(f"{_B}Next steps:{_R}")
    print(f"  1. Edit {config_path} — adjust the guardrail config for your project")
    print("     (edit the copy, not the package default — reinstalling with --force overwrites it)")
    print("  2. Start a new Claude Code session (or /clear) so it picks up the new hooks")
    print(
        f"  {_D}Full Config/tracker option reference: "
        f"agent_evaluator/gates/gate_b_behavioral/configs.py, "
        f"agent_evaluator/core/trackers/security.py{_R}"
    )
    print()
    print(
        f"{_Y}💡 Tuning tip:{_R} same as the OpenCode plugin — "
        f"loop_detection.consecutive_repeat_threshold (default 6) only compares tool *names*, "
        f"not parameters. Raise it further if legitimate repeated Bash/Edit calls get "
        f"blocked/recorded as loops."
    )
    return 0


def build_claude_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """claude 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Install the LiveGuardrail Claude Code CLI hooks (real-time Gate B/E guardrail)",
        description=(
            "Register PreToolUse/PostToolUse/SessionEnd hooks in .claude/settings.json that call\n"
            "the bundled LiveGuardrail bridge (agent_evaluator.integrations.claude_code_hook).\n"
            f"{_D}The bridge is a thin, judgment-free hook script — the sole source of truth\n"
            f"for Gate B/E logic always stays in "
            f"agent_evaluator.gates.live_guardrail.LiveGuardrail.{_R}"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval claude install{_R}\n"
            f"  {_G}agent-eval claude install --global{_R}\n"
            f"  {_G}agent-eval claude install --force{_R}\n"
            f"  {_G}agent-eval claude install --with-violation-search{_R}\n"
            f"  {_G}agent-eval claude install --with-recommend-fix{_R}\n"
        ),
    )
    cl_sub = p.add_subparsers(dest="claude_command")

    install_p = cl_sub.add_parser(
        "install",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Register the LiveGuardrail hooks in .claude/settings.json",
        description=(
            "Merge PreToolUse/PostToolUse/SessionEnd hook entries into .claude/settings.json\n"
            "(or ~/.claude/settings.json with --global), baking in the current Python\n"
            "interpreter's absolute path, and write a default guardrail config file."
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval claude install{_R} {_D}# .claude/settings.json (project-local){_R}\n"
            f"  {_G}agent-eval claude install --global{_R} {_D}# ~/.claude/settings.json{_R}\n"
            f"  {_G}agent-eval claude install --force{_R} {_D}# reset guardrail_config.json{_R}\n"
            f"  {_G}agent-eval claude install --with-violation-search{_R}\n"
            f"      {_D}# + register search_violations MCP server{_R}\n"
            f"  {_G}agent-eval claude install --with-recommend-fix{_R}\n"
            f"      {_D}# + register recommend_fix MCP server{_R}\n"
        ),
    )
    install_p.add_argument(
        "--global", dest="global_install", action="store_true",
        help=(
            "Install to ~/.claude/settings.json (all projects) instead of the project-local "
            ".claude/settings.json (default)"
        ),
    )
    install_p.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing guardrail_config.json with defaults",
    )
    install_p.add_argument(
        "--with-violation-search", dest="with_violation_search", action="store_true",
        help=(
            "Also run 'claude mcp add' to register the "
            "search_violations MCP server (opt-in, requires the 'mcp' extra: "
            "pip install \"agent-evaluator[mcp]\")"
        ),
    )
    install_p.add_argument(
        "--with-recommend-fix", dest="with_recommend_fix", action="store_true",
        help=(
            "Also run 'claude mcp add' to register the "
            "recommend_fix MCP server — static Gate/metric remediation lookup, "
            "no result file required (opt-in, requires the 'mcp' extra: "
            "pip install \"agent-evaluator[mcp]\")"
        ),
    )
