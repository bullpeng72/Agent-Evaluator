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
import re
import subprocess as subprocess  # re-export: tests monkeypatch claude.subprocess.run directly
import sys
from pathlib import Path

# 재export(redundant alias) — installer가 쓰는 기본 설정을 이 모듈의 공개 심볼로도 노출.
from agent_evaluator.integrations.claude_code_hook import (
    DEFAULT_GUARDRAIL_CONFIG as DEFAULT_GUARDRAIL_CONFIG,
)

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
# PreToolUse/PostToolUse matchers filter by *tool name* (a regex) — SessionEnd's matcher
# filters by session-end *reason* (clear/logout/prompt_input_exit/...) instead, so reusing
# the tool-name matcher there would silently never match and the batch-save hook would
# never fire. "*" means "match all" for SessionEnd (there's no tool name to restrict by).
#
# SPEC-041: Claude Code treats a matcher of only [A-Za-z0-9_\-, |\s] as an EXACT name
# (or |-separated exact list); anything with other chars is an unanchored regex. So the
# old "Bash|Edit|Write" was an exact list — it matched ONLY Bash/Edit/Write and silently
# MISSED NotebookEdit, MultiEdit, WebFetch, and every MCP tool (file/command creation via
# an MCP filesystem/editor/patch server had no PreToolUse check and left no PostToolUse
# history, so loop detection was blind to it too).
# This matcher contains regex metachars, so it IS a regex; it is fully anchored ^(...)$ so
# it behaves the same under re.search / re.match / re.fullmatch:
#   - built-ins: exact names (adding NotebookEdit/MultiEdit/WebFetch that the old list missed);
#     TodoWrite/BashOutput/Read/Glob/Grep stay excluded.
#   - WebFetch: included so the default scope.forbidden_tools=["WebFetch"] finally takes effect.
#   - MCP: mcp__<server>__<verb>... where <verb> is preceded by "_" (so read-only tools like
#     mcp__ctx__search / mcp__x__list_dir don't pay the per-call hook-subprocess cost).
_MCP_MUTATION_VERBS = (
    "write|edit|create|patch|apply|delete|remove|move|rename|mkdir|put|save|update|insert|append"
)
_TOOL_MATCHER = (
    f"^(Bash|Write|Edit|MultiEdit|NotebookEdit|WebFetch"
    f"|mcp__.+_({_MCP_MUTATION_VERBS})[a-zA-Z0-9_]*)$"
)
_HOOK_MATCHERS: dict[str, str] = {
    "PreToolUse": _TOOL_MATCHER,
    "PostToolUse": _TOOL_MATCHER,
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


def _our_hook_entries(entries: list) -> list[dict]:
    return [
        entry
        for entry in entries or []
        if any(_HOOK_MODULE in (h.get("command") or "") for h in entry.get("hooks", []))
    ]


# 우리가 쓴 정확한 형태: "<python> -m agent_evaluator.integrations.claude_code_hook"
# (_hook_entry가 만드는 그대로). 사용자가 래핑/추가 인자를 붙인 커맨드는 이 정규식에
# 안 걸리므로 건드리지 않는다.
_CANONICAL_HOOK_CMD_RE = re.compile(
    r"^\S+\s+-m\s+" + re.escape(_HOOK_MODULE) + r"\s*$"
)


def _refresh_hook_command(entry: dict, python_bin: str) -> bool:
    """entry.hooks[*].command가 우리의 정확한 canonical 형태인데 인터프리터 경로만
    다르면 현재 인터프리터로 갱신한다 (SPEC-041). venv 재생성·pipx reinstall 등으로
    옛 python 경로가 죽었을 때 `agent-eval claude install` 재실행만으로 고쳐지게 한다.
    래핑된 커맨드(추가 인자·셸 파이프 등)는 사용자 의도로 보고 그대로 둔다."""
    want = f"{python_bin} -m {_HOOK_MODULE}"
    bumped = False
    for h in entry.get("hooks", []):
        cmd = h.get("command") or ""
        if cmd != want and _CANONICAL_HOOK_CMD_RE.match(cmd):
            h["command"] = want
            bumped = True
    return bumped


def _has_our_hook(entries: list) -> bool:
    return bool(_our_hook_entries(entries))


def _merge_settings(existing: dict, python_bin: str) -> tuple[dict, list[str], list[str]]:
    """기존 ``settings.json``에 세 훅을 병합한다.

    이미 있는 다른 훅/설정은 그대로 보존한다 — 무조건 덮어쓰지 않는다(OpenCode installer의
    단순 파일 복사와 달리, Claude Code의 ``settings.json``은 사용자가 이미 다른 훅을 등록해
    뒀을 수 있는 공유 파일이라 read-modify-write가 필요하다).

    재설치 시:
      - 우리 훅이 없는 이벤트는 새로 추가한다(``added``에 기록).
      - 우리 훅이 이미 있는데 ``matcher``가 현재 :data:`_HOOK_MATCHERS`와 다르면
        그 필드만 갱신한다(``updated``). SPEC-041에서 matcher를 넓혔는데(MCP/NotebookEdit/
        WebFetch), 이 갱신이 없으면 기존 설치는 재설치해도 옛 matcher에 갇힌다.
        ``command``·기타 필드·다른 훅은 건드리지 않는다.

    Returns:
        ``(병합된 settings dict, 새로 추가된 이벤트, matcher가 갱신된 이벤트)``.
    """
    merged = dict(existing)
    hooks = dict(merged.get("hooks") or {})
    added: list[str] = []
    updated: list[str] = []
    for event in _HOOK_EVENTS:
        entries = list(hooks.get(event) or [])
        ours = _our_hook_entries(entries)
        if not ours:
            entries.append(_hook_entry(python_bin, event))
            hooks[event] = entries
            added.append(event)
            continue
        want = _HOOK_MATCHERS[event]
        bumped = False
        for entry in ours:
            if entry.get("matcher") != want:
                entry["matcher"] = want
                bumped = True
            if _refresh_hook_command(entry, python_bin):
                bumped = True
        if bumped:
            hooks[event] = entries
            updated.append(event)
    merged["hooks"] = hooks
    return merged, added, updated


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

    merged, added, updated = _merge_settings(existing_settings, sys.executable)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    if added:
        print(f"{_G}✅ Registered hooks in {settings_path}: {', '.join(added)}{_R}")
    if updated:
        print(f"{_G}✅ Refreshed tool matcher for existing hooks: {', '.join(updated)}{_R}")
    if not added and not updated:
        print(f"{_D}   Hooks already registered in {settings_path} — nothing to change{_R}")

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
        f"{_Y}💡 Tuning tips:{_R}\n"
        f"  - loop_detection.consecutive_repeat_threshold (default 8) only compares tool "
        f"*names*, not parameters. Only 'consecutive_repeat' loops hard-block on the live "
        f"path (live_loop_blocking_types); 'window_duplicate' is recorded but not enforced.\n"
        f"  - live_loop_window (default 15) bounds the live loop check to the last N calls, "
        f"so an early transient repeat can't latch the whole session.\n"
        f"  - circuit_breaker_after (default 5) flips the session to observe-only after that "
        f"many consecutive blocks — a miscalibrated config warns instead of locking you out.\n"
        f"  - tool_parameter_safety.scope_tool_names is [\"Bash\"] by default, so Write/Edit "
        f"file bodies are never length-checked or pattern-scanned.\n"
        f"  - shell file creation (cat/tee/echo/printf > FILE, heredocs, '| tee') is treated "
        f"like Write — dangerous strings in the *content* don't block; '| sh', ';', '&&', "
        f"'$(...)' do.\n"
        f"  - protected_write_paths (built-in default list: ~/.ssh, shell rc files, /etc, "
        f"cron, LaunchAgents, ...) blocks writes by *location* regardless of tool/content. "
        f"Add the key with your own regex list to customize, or [] to disable."
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
