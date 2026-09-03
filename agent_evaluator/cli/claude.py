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
import contextlib
import json
import re
import shlex
import shutil
import subprocess as subprocess  # re-export: tests monkeypatch claude.subprocess.run directly
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_evaluator.cli._integration_health import DoctorReport

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
_ASK_INSIGHTS_MCP_NAME = "agent-evaluator-ask-insights"


def cmd_claude(args: argparse.Namespace) -> int:
    """claude 서브커맨드 진입점."""
    cmd = getattr(args, "claude_command", None)
    if cmd == "install":
        return _cmd_install(args)
    if cmd == "upgrade":
        return _cmd_upgrade(args)
    if cmd == "uninstall":
        return _cmd_uninstall(args)
    if cmd == "doctor":
        return _cmd_doctor(args)
    print(
        f"{_B}agent-eval claude{_R} — LiveGuardrail Claude Code CLI hooks\n\n"
        f"  {_Y}install{_R}     Register PreToolUse/PostToolUse/SessionEnd hooks in "
        f".claude/settings.json\n"
        f"  {_Y}upgrade{_R}     Refresh hooks/config after a package update "
        f"(keeps your guardrail_config.json edits)\n"
        f"  {_Y}doctor{_R}      Verify the install actually works (static + live round-trip)\n"
        f"  {_Y}uninstall{_R}   Remove the hooks/MCP servers (run before 'pip uninstall')\n\n"
        f"Usage: agent-eval claude <command> --help",
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
            f"{_Y}⚠️  {flag}: 'claude' CLI not found — skipping MCP server registration. "
            f"Register manually: {_manual}{_R}",
            file=sys.stderr,
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"{_Y}⚠️  {flag}: 'claude mcp add' timed out — register it manually.{_R}",
            file=sys.stderr,
        )
        return

    if result.returncode == 0:
        print(f"{_G}✅ MCP server registered: {name}{_R}")
    elif "already exists" in (result.stderr or "").lower():
        # 재설치/업그레이드 시 정상 상태 — 실패가 아니다. 과거엔 이걸 ⚠️ + 수동
        # 명령으로 출력해 업그레이드가 깨진 것처럼 보였다.
        print(f"{_D}   MCP server already registered: {name} — nothing to change{_R}")
    else:
        print(
            f"{_Y}⚠️  {flag}: 'claude mcp add' failed (exit {result.returncode}) — "
            f"register manually: {_manual}{_R}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"{_D}   {result.stderr.strip()}{_R}", file=sys.stderr)


def _deregister_mcp_server(name: str, scope: str) -> None:
    """``claude mcp remove``로 MCP 서버 등록을 해제한다 (uninstall용).

    ``_register_mcp_server()``와 동일한 fail-soft 원칙 — ``claude`` CLI 미설치나
    "not found"(이미 없음)는 조용히 넘어간다.
    """
    try:
        result = subprocess.run(
            ["claude", "mcp", "remove", name, "--scope", scope],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print(
            f"{_Y}⚠️  'claude' CLI not found — skipping deregistration of MCP server "
            f"'{name}'. Manually: claude mcp remove {name} --scope {scope}{_R}",
            file=sys.stderr,
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"{_Y}⚠️  'claude mcp remove {name}' timed out — deregister it manually.{_R}",
            file=sys.stderr,
        )
        return

    _stderr = (result.stderr or "").lower()
    if result.returncode == 0:
        print(f"{_G}✅ MCP server deregistered: {name}{_R}")
    elif "no mcp server" in _stderr or "not found" in _stderr or "does not exist" in _stderr:
        print(f"{_D}   MCP server not registered: {name} — nothing to remove{_R}")
    else:
        print(
            f"{_Y}⚠️  'claude mcp remove {name}' failed (exit {result.returncode}) — "
            f"manually: claude mcp remove {name} --scope {scope}{_R}",
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


def _register_ask_insights_mcp(scope: str) -> None:
    _register_mcp_server(
        _ASK_INSIGHTS_MCP_NAME, "agent_evaluator.integrations.ask_insights_mcp",
        "--with-ask-insights", scope,
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

    if getattr(args, "with_ask_insights", False):
        print()
        _register_ask_insights_mcp(scope)

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


# ===========================================================================
# upgrade — 패키지 업데이트 후 훅/설정 현행화 (사용자 편집 보존)
# ===========================================================================
def _mcp_is_registered(name: str) -> bool | None:
    """``claude mcp get <name>``으로 등록 여부를 확인한다. CLI 미설치/오류면 ``None``."""
    try:
        r = subprocess.run(
            ["claude", "mcp", "get", name], capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return r.returncode == 0


def _cmd_upgrade(args: argparse.Namespace) -> int:
    """``install``과 달리 사용자가 편집한 ``guardrail_config.json``을 보존하면서
    (1) 훅 matcher/인터프리터 경로를 현재 값으로 갱신하고 (2) 새로 추가된 기본 설정
    키만 deep-merge하고 (3) 이미 등록된 MCP 서버를 인터프리터 경로 갱신을 위해 재등록한다.
    """
    from agent_evaluator.cli._integration_health import deep_merge_defaults

    is_global: bool = getattr(args, "global_install", False)
    settings_path = _GLOBAL_SETTINGS if is_global else _LOCAL_SETTINGS
    config_path = _GLOBAL_CONFIG if is_global else _LOCAL_CONFIG
    scope = "user" if is_global else "local"

    if not settings_path.exists():
        print(
            f"{_Y}No existing install at {settings_path} — run `agent-eval claude install` "
            f"first.{_R}",
            file=sys.stderr,
        )
        return 1
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{_RD}❌ Failed to parse {settings_path}: {exc}{_R}", file=sys.stderr)
        return 1

    # 1. 훅: install과 동일한 병합(누락 훅 추가 + stale matcher/인터프리터 갱신).
    merged, added, updated = _merge_settings(existing, sys.executable)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    if added:
        print(f"{_G}✅ Added missing hooks: {', '.join(added)}{_R}")
    if updated:
        print(f"{_G}✅ Refreshed hook matcher/interpreter: {', '.join(updated)}{_R}")
    if not added and not updated:
        print(f"{_D}   Hooks already current{_R}")

    # 2. guardrail_config.json: 새 기본 키만 채우고 사용자 값은 절대 안 건드린다.
    if config_path.exists():
        try:
            user_cfg: object = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"{_Y}⚠️  {config_path} is not valid JSON ({exc}) — left untouched. Fix it, "
                f"or `agent-eval claude install --force` to reset to defaults.{_R}",
                file=sys.stderr,
            )
            user_cfg = None
        if isinstance(user_cfg, dict):
            new_cfg, new_keys = deep_merge_defaults(user_cfg, DEFAULT_GUARDRAIL_CONFIG)
            if new_keys:
                config_path.write_text(json.dumps(new_cfg, indent=2) + "\n", encoding="utf-8")
                print(
                    f"{_G}✅ Added {len(new_keys)} new default key(s) to {config_path} "
                    f"(your values kept):{_R}"
                )
                for k in new_keys:
                    print(f"     {_D}+ {k}{_R}")
            else:
                print(f"{_D}   guardrail_config.json already has every default key{_R}")
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(DEFAULT_GUARDRAIL_CONFIG, indent=2) + "\n", encoding="utf-8",
        )
        print(f"{_G}✅ Wrote default guardrail config: {config_path}{_R}")

    # 3. MCP 서버: install과 동일하게 --with-* 플래그를 줬을 때만 재등록(remove→add)한다.
    #    (get으로 자동 감지해 재등록하면 user-scope로만 등록된 서버를 local-scope에
    #     중복 등록하는 사고가 난다 — 스코프를 명시적으로 다루기 위해 opt-in 유지.)
    if getattr(args, "with_violation_search", False):
        print()
        _deregister_mcp_server(_VIOLATION_SEARCH_MCP_NAME, scope)
        _register_violation_search_mcp(scope)
    if getattr(args, "with_recommend_fix", False):
        print()
        _deregister_mcp_server(_RECOMMEND_FIX_MCP_NAME, scope)
        _register_recommend_fix_mcp(scope)
    if getattr(args, "with_ask_insights", False):
        print()
        _deregister_mcp_server(_ASK_INSIGHTS_MCP_NAME, scope)
        _register_ask_insights_mcp(scope)

    print()
    print(f"{_B}Done.{_R} Start a new Claude Code session (or /clear) to pick up the changes.")
    print(f"{_D}Run `agent-eval claude doctor` to verify.{_R}")
    return 0


# ===========================================================================
# uninstall — 훅/MCP 제거 (pip uninstall 전에 실행)
# ===========================================================================
def _scope_has_install(settings_path: Path, state_dir: Path) -> bool:
    """이 스코프에 agent-evaluator 훅 또는 남은 상태(config/sessions)가 있는지."""
    n = 0
    if settings_path.exists():
        try:
            s: object = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            s = None
        if isinstance(s, dict) and isinstance(s.get("hooks"), dict):
            for event in _HOOK_EVENTS:
                n += len(_our_hook_entries(s["hooks"].get(event) or []))
    if n:
        return True
    return (state_dir / "guardrail_config.json").exists() or (state_dir / "sessions").exists()


def _cmd_uninstall(args: argparse.Namespace) -> int:
    is_global: bool = getattr(args, "global_install", False)
    keep_config: bool = getattr(args, "keep_config", False)
    purge: bool = getattr(args, "purge", False)
    dry_run: bool = getattr(args, "dry_run", False)
    assume_yes: bool = getattr(args, "yes", False)

    # Claude Code merges ~/.claude/settings.json with the project-local one, so a user who
    # ran `install --global` and then a bare `uninstall` (no --global) would otherwise be
    # told "Nothing to remove" while the global hooks + user-scope MCP servers stay behind
    # (and the MCP deregister would run at the wrong --scope). Fall back to the global
    # install when the project-local scope has nothing, mirroring `doctor`.
    if (
        not is_global
        and not _scope_has_install(_LOCAL_SETTINGS, _LOCAL_CONFIG.parent)
        and _scope_has_install(_GLOBAL_SETTINGS, _GLOBAL_CONFIG.parent)
    ):
        is_global = True
        print(
            f"{_D}   No project-local install — targeting the global install (~/.claude). "
            f"Pass --global to silence this.{_R}"
        )

    settings_path = _GLOBAL_SETTINGS if is_global else _LOCAL_SETTINGS
    state_dir = (_GLOBAL_CONFIG if is_global else _LOCAL_CONFIG).parent
    config_file = state_dir / "guardrail_config.json"
    sessions_dir = state_dir / "sessions"
    scope = "user" if is_global else "local"

    settings: object = None
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{_RD}❌ Failed to parse {settings_path}: {exc}{_R}", file=sys.stderr)
            return 1

    n_hooks = 0
    if isinstance(settings, dict) and isinstance(settings.get("hooks"), dict):
        for event in _HOOK_EVENTS:
            n_hooks += len(_our_hook_entries(settings["hooks"].get(event) or []))

    plan: list[str] = []
    if n_hooks:
        plan.append(
            f"remove {n_hooks} agent-evaluator hook entr"
            f"{'y' if n_hooks == 1 else 'ies'} from {settings_path} (other hooks untouched)"
        )
    plan.append(
        f"deregister MCP servers {_VIOLATION_SEARCH_MCP_NAME}, {_RECOMMEND_FIX_MCP_NAME} "
        f"(--scope {scope}) if registered"
    )
    if purge and state_dir.exists():
        plan.append(f"delete the whole state dir {state_dir} (sessions + config)")
    else:
        if sessions_dir.exists():
            plan.append(f"delete session state {sessions_dir}")
        if config_file.exists() and not keep_config:
            plan.append(f"delete {config_file}")
        elif config_file.exists():
            plan.append(f"keep {config_file} (--keep-config)")

    if not (n_hooks or config_file.exists() or sessions_dir.exists()):
        print(
            f"{_D}Nothing to remove — no agent-evaluator hooks or state found "
            f"({settings_path}).{_R}"
        )
        # MCP는 별도 저장소라 그래도 시도해준다.
        if not dry_run:
            _deregister_mcp_server(_VIOLATION_SEARCH_MCP_NAME, scope)
            _deregister_mcp_server(_RECOMMEND_FIX_MCP_NAME, scope)
            _deregister_mcp_server(_ASK_INSIGHTS_MCP_NAME, scope)
        return 0

    print(f"{_B}agent-eval claude uninstall{_R} will:")
    for item in plan:
        print(f"  - {item}")

    if dry_run:
        print(f"\n{_D}(--dry-run — nothing changed){_R}")
        return 0

    if not assume_yes:
        try:
            resp = input("\nProceed? [y/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 1

    # --- 실행 ---
    if isinstance(settings, dict) and isinstance(settings.get("hooks"), dict):
        hooks = settings["hooks"]
        for event in list(hooks):
            if event not in _HOOK_EVENTS:
                continue
            entries = hooks.get(event) or []
            ours = _our_hook_entries(entries)
            kept = [e for e in entries if e not in ours]
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print(f"{_G}✅ Removed hook entries from {settings_path}{_R}")

    _deregister_mcp_server(_VIOLATION_SEARCH_MCP_NAME, scope)
    _deregister_mcp_server(_RECOMMEND_FIX_MCP_NAME, scope)
    _deregister_mcp_server(_ASK_INSIGHTS_MCP_NAME, scope)

    if purge and state_dir.exists():
        shutil.rmtree(state_dir, ignore_errors=True)
        print(f"{_G}✅ Deleted {state_dir}{_R}")
    else:
        if sessions_dir.exists():
            shutil.rmtree(sessions_dir, ignore_errors=True)
            print(f"{_G}✅ Deleted {sessions_dir}{_R}")
        if config_file.exists() and not keep_config:
            config_file.unlink()
            print(f"{_G}✅ Deleted {config_file}{_R}")
        with contextlib.suppress(OSError):
            state_dir.rmdir()  # 비었을 때만 성공

    print()
    print(
        f"{_B}Next:{_R} pip uninstall agent-evaluator  "
        f"{_D}(hooks are gone — safe to remove the package now){_R}"
    )
    return 0


# ===========================================================================
# doctor — 설치가 실제로 도는지 검증 (정적 + 라이브 라운드트립)
# ===========================================================================
def _doctor_live_claude(
    rpt: DoctorReport, cmd_parts: list[str], sandbox: Path, resolved_cfg: dict,
) -> None:
    """등록된 훅 커맨드를 hermetic sandbox(cwd)로 실제 실행해 allow/deny/배치리포트를 확인한다."""
    cfg = dict(resolved_cfg)
    cfg["output_dir"] = str(sandbox / "results")  # 상대경로 리포트가 sandbox 밖으로 안 새게
    state_dir = sandbox / ".claude" / ".agent-evaluator"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "guardrail_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    sid = "doctor-session"

    def _run(payload: dict, timeout: float = 60.0) -> tuple[int, object, str]:
        proc = subprocess.run(
            cmd_parts, input=json.dumps(payload), capture_output=True, text=True,
            cwd=str(sandbox), timeout=timeout,
        )
        parsed: object = None
        for line in reversed((proc.stdout or "").strip().splitlines()):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        return proc.returncode, parsed, proc.stderr or ""

    def _decision(parsed: object) -> object:
        if isinstance(parsed, dict):
            return (parsed.get("hookSpecificOutput") or {}).get("permissionDecision")
        return None

    def _pre(tool: str, tool_input: dict) -> dict:
        return {
            "hook_event_name": "PreToolUse", "session_id": sid, "cwd": str(sandbox),
            "tool_name": tool, "tool_input": tool_input,
        }

    # allow: 무해한 Bash
    try:
        rc, parsed, _ = _run(_pre("Bash", {"command": "ls -la"}))
        if _decision(parsed) == "allow":
            rpt.ok("live", "allow: benign Bash → allow")
        else:
            rpt.error(
                "live", "allow: benign Bash → allow",
                f"got decision={_decision(parsed)!r}, exit={rc}",
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        rpt.error("live", "allow: benign Bash → allow", str(exc))

    # block: rm -rf (Gate B dangerous_patterns)
    try:
        rc, parsed, _ = _run(_pre("Bash", {"command": "rm -rf /tmp/ae-doctor-target-xyz"}))
        if _decision(parsed) == "deny" and rc == 2:
            rpt.ok("live", "block: rm -rf → deny (exit 2)")
        else:
            rpt.error(
                "live", "block: rm -rf → deny (exit 2)",
                f"got decision={_decision(parsed)!r}, exit={rc}",
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        rpt.error("live", "block: rm -rf → deny (exit 2)", str(exc))

    # block: WebFetch (기본 scope.forbidden_tools)
    try:
        _, parsed, _ = _run(_pre("WebFetch", {"url": "https://example.com"}))
        dec = _decision(parsed)
        if dec == "deny":
            rpt.ok("live", "block: WebFetch → deny (scope.forbidden_tools)")
        else:
            rpt.warn(
                "live", "block: WebFetch → deny",
                f"got decision={dec!r} — is WebFetch still in scope.forbidden_tools?",
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        rpt.warn("live", "block: WebFetch → deny", str(exc))

    # 배치 리포트: PostToolUse → SessionEnd
    try:
        _run({
            "hook_event_name": "PostToolUse", "session_id": sid, "cwd": str(sandbox),
            "tool_name": "Bash", "tool_input": {"command": "ls"},
            "tool_result": {"type": "text", "content": "a\nb"},
        })
        _run({
            "hook_event_name": "SessionEnd", "session_id": sid, "cwd": str(sandbox),
            "reason": "doctor",
        })
        reports = list((sandbox / "results").rglob("claude_code_sessions*")) \
            if (sandbox / "results").exists() else []
        leftover = list(state_dir.glob("sessions/*")) if (state_dir / "sessions").exists() else []
        if reports and not leftover:
            rpt.ok("live", "batch report written + session files cleaned", reports[0].name)
        elif reports:
            rpt.warn(
                "live", "batch report written",
                f"{len(leftover)} session state file(s) left behind",
            )
        else:
            rpt.warn(
                "live", "batch report written",
                "no report produced — SessionEnd hook may not be wired (check its matcher)",
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        rpt.warn("live", "batch report", str(exc))


def _cmd_doctor(args: argparse.Namespace) -> int:
    from agent_evaluator.cli._integration_health import (
        DoctorReport,
        interpreter_from_command,
        mcp_initialize_probe,
        probe_import,
        validate_guardrail_config,
    )

    is_global: bool = getattr(args, "global_install", False)
    as_json: bool = getattr(args, "json", False)
    no_live: bool = getattr(args, "no_live", False)
    strict: bool = getattr(args, "strict", False)

    settings_path = _GLOBAL_SETTINGS if is_global else _LOCAL_SETTINGS
    config_path = _GLOBAL_CONFIG if is_global else _LOCAL_CONFIG
    # Claude Code merges ~/.claude/settings.json with the project-local one, so a missing
    # project-local file is not an error when the global install exists — check that instead.
    fell_back_to_global = False
    if not is_global and not settings_path.exists() and _GLOBAL_SETTINGS.exists():
        settings_path, config_path = _GLOBAL_SETTINGS, _GLOBAL_CONFIG
        fell_back_to_global = True

    rpt = DoctorReport(title=f"agent-eval claude doctor — {settings_path}")

    # ---------- Tier 1: 정적 ----------
    settings: object = None
    if not settings_path.exists():
        hint = "run `agent-eval claude install`" + ("" if is_global else " (or add --global)")
        rpt.error("static", "settings.json exists", f"not found: {settings_path} — {hint}")
    else:
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            _detail = (
                "global — no project-local .claude/settings.json" if fell_back_to_global else ""
            )
            rpt.ok("static", "settings.json parses", _detail)
        except json.JSONDecodeError as exc:
            rpt.error("static", "settings.json parses", str(exc))

    hook_cmd: str | None = None
    if isinstance(settings, dict):
        hooks = settings.get("hooks") or {}
        missing: list[str] = []
        stale: set[str] = set()
        for event in _HOOK_EVENTS:
            ours = _our_hook_entries(hooks.get(event) or [])
            if not ours:
                missing.append(event)
                continue
            for entry in ours:
                for h in entry.get("hooks", []):
                    if _HOOK_MODULE in (h.get("command") or "") and hook_cmd is None:
                        hook_cmd = h["command"]
                if entry.get("matcher") != _HOOK_MATCHERS[event]:
                    stale.add(event)
        if missing:
            rpt.error("static", "hooks registered", f"missing: {', '.join(missing)}")
        else:
            rpt.ok("static", "hooks registered", "PreToolUse, PostToolUse, SessionEnd")
        if stale:
            rpt.warn(
                "static", "hook matcher up to date",
                f"drift on {', '.join(sorted(stale))} — run `agent-eval claude upgrade`",
            )
        elif not missing:
            rpt.ok("static", "hook matcher up to date")

    py_bin: str | None = None
    if hook_cmd:
        py_bin = interpreter_from_command(hook_cmd)
        if py_bin and Path(py_bin).exists():
            rpt.ok("static", "hook interpreter exists", py_bin)
        elif py_bin:
            rpt.error(
                "static", "hook interpreter exists",
                f"{py_bin} is gone — recreate the venv / rerun `agent-eval claude install`",
            )
        else:
            rpt.warn("static", "hook interpreter exists", f"could not parse: {hook_cmd}")

    probe_bin = py_bin if (py_bin and Path(py_bin).exists()) else sys.executable
    ok, err = probe_import(probe_bin, _HOOK_MODULE)
    if ok:
        rpt.ok("static", "package importable from that interpreter", probe_bin)
    else:
        rpt.error("static", "package importable from that interpreter", err)

    resolved_cfg: dict | None = None
    try:
        from agent_evaluator.integrations.claude_code_hook import load_config

        resolved_cfg = dict(load_config(config_path.parent))
    except Exception as exc:  # noqa: BLE001
        rpt.error("static", "guardrail_config resolves", str(exc))
    if resolved_cfg is not None:
        src = str(config_path) if config_path.exists() else "package defaults (no config file)"
        built, warns = validate_guardrail_config(resolved_cfg)
        if built and not warns:
            rpt.ok("static", "guardrail_config builds", f"from {src}")
        elif built:
            rpt.warn("static", "guardrail_config builds", f"{src}; SKIPPED: {' | '.join(warns)}")
        else:
            rpt.error("static", "guardrail_config builds", " | ".join(warns))

    mcp_targets = (
        (_VIOLATION_SEARCH_MCP_NAME, "agent_evaluator.integrations.violation_search_mcp",
         "search_violations"),
        (_RECOMMEND_FIX_MCP_NAME, "agent_evaluator.integrations.recommend_fix_mcp",
         "recommend_fix"),
        (_ASK_INSIGHTS_MCP_NAME, "agent_evaluator.integrations.ask_insights_mcp",
         "insights_summary"),
    )
    mcp_status: dict[str, bool | None] = {}
    for mname, _mmod, _mtool in mcp_targets:
        reg = _mcp_is_registered(mname)
        mcp_status[mname] = reg
        if reg:
            rpt.ok("static", f"MCP registered: {mname}")
        elif reg is False:
            rpt.info(
                "static", f"MCP registered: {mname}",
                "not registered (only needed with --with-violation-search / --with-recommend-fix)",
            )
        else:
            rpt.info("static", f"MCP registered: {mname}", "could not query `claude mcp get`")

    # ---------- Tier 2: 라이브 ----------
    if no_live:
        rpt.info("live", "skipped (--no-live)")
    elif rpt.n_errors:
        rpt.info("live", "skipped — fix the static errors above first")
    elif not hook_cmd:
        rpt.info("live", "skipped — no hook command found")
    else:
        try:
            cmd_parts = shlex.split(hook_cmd)
        except ValueError:
            cmd_parts = []
        if not cmd_parts:
            rpt.warn("live", "run registered hook command", f"unparseable: {hook_cmd}")
        else:
            sandbox = Path(tempfile.mkdtemp(prefix="ae-claude-doctor-"))
            try:
                _doctor_live_claude(rpt, cmd_parts, sandbox, resolved_cfg or {})
            finally:
                shutil.rmtree(sandbox, ignore_errors=True)

    # ---------- Tier 3: MCP 핸드셰이크 (등록된 서버만) ----------
    if not no_live:
        for mname, mmod, mtool in mcp_targets:
            if mcp_status.get(mname):
                status, detail = mcp_initialize_probe(probe_bin, mmod, mtool)
                rpt.add("mcp", status, f"{mname} responds to initialize", detail)

    if as_json:
        print(rpt.render_json())
    else:
        print(rpt.render_text(color=_USE_COLOR))
    return rpt.exit_code(strict=strict)


def _add_common_target_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--global", dest="global_install", action="store_true",
        help="Target ~/.claude/settings.json instead of the project-local .claude/settings.json",
    )


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
    install_p.add_argument(
        "--with-ask-insights", dest="with_ask_insights", action="store_true",
        help=(
            "Also run 'claude mcp add' to register the ask_insights MCP server "
            "— query a result JSON's insight layer (verdict, path to green, why "
            "a task failed, task lists by filter) (opt-in, requires the 'mcp' "
            "extra: pip install \"agent-evaluator[mcp]\")"
        ),
    )

    # --- upgrade ---
    upgrade_p = cl_sub.add_parser(
        "upgrade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Refresh hooks/config after a package update (keeps your guardrail_config.json edits)",
        description=(
            "Idempotent refresh for an existing install. Unlike `install --force`:\n"
            "  - refreshes stale hook matchers and dead interpreter paths\n"
            "  - deep-merges only NEW default keys into guardrail_config.json (never\n"
            "    overwrites your values)\n"
            "  - with --with-violation-search/--with-recommend-fix, re-registers those\n"
            "    MCP servers (remove + add) so the interpreter path is refreshed too"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval claude upgrade{_R}\n"
            f"  {_G}agent-eval claude upgrade --global --with-recommend-fix{_R}\n"
        ),
    )
    _add_common_target_flags(upgrade_p)
    upgrade_p.add_argument(
        "--with-violation-search", dest="with_violation_search", action="store_true",
        help="Also re-register the search_violations MCP server (remove + add)",
    )
    upgrade_p.add_argument(
        "--with-recommend-fix", dest="with_recommend_fix", action="store_true",
        help="Also re-register the recommend_fix MCP server (remove + add)",
    )
    upgrade_p.add_argument(
        "--with-ask-insights", dest="with_ask_insights", action="store_true",
        help="Also re-register the ask_insights MCP server (remove + add)",
    )

    # --- doctor ---
    doctor_p = cl_sub.add_parser(
        "doctor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Verify the install actually works (static checks + live round-trip)",
        description=(
            "Static: settings.json parses, all 3 hooks registered, matcher current, hook\n"
            "interpreter alive, package importable from it, guardrail_config.json builds,\n"
            "MCP servers registered.\n"
            "Live (in a throwaway sandbox dir): runs the REAL registered hook command with\n"
            "synthetic PreToolUse/PostToolUse/SessionEnd payloads and checks that a benign\n"
            "call is allowed, `rm -rf`/WebFetch are denied, and a batch report is written.\n"
            "MCP: initialize + tools/list handshake against each registered MCP server.\n"
            "Exit 1 on any error (add --strict to also fail on warnings)."
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval claude doctor{_R}\n"
            f"  {_G}agent-eval claude doctor --global --json{_R}\n"
            f"  {_G}agent-eval claude doctor --no-live{_R} {_D}# static checks only{_R}\n"
        ),
    )
    _add_common_target_flags(doctor_p)
    doctor_p.add_argument(
        "--no-live", dest="no_live", action="store_true",
        help="Static checks only — don't spawn the hook subprocess",
    )
    doctor_p.add_argument(
        "--json", action="store_true", help="Emit the report as JSON (for CI)",
    )
    doctor_p.add_argument(
        "--strict", action="store_true", help="Exit 1 on warnings too, not just errors",
    )

    # --- uninstall ---
    uninstall_p = cl_sub.add_parser(
        "uninstall",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Remove the hooks + MCP servers (run BEFORE 'pip uninstall agent-evaluator')",
        description=(
            "Reverses `install`: removes only our hook entries from settings.json (other\n"
            "hooks untouched), deregisters the MCP servers, and deletes session state.\n"
            "Keeps guardrail_config.json by default (--purge removes everything).\n"
            "If the project-local scope has nothing, falls back to the global install\n"
            "(~/.claude) so a bare `uninstall` after `install --global` still works.\n\n"
            "NOTE: `agent-eval` disappears once the package is uninstalled, so this must be\n"
            "run first. Order:  agent-eval claude uninstall  →  pip uninstall agent-evaluator"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval claude uninstall{_R}\n"
            f"  {_G}agent-eval claude uninstall --global --yes{_R}\n"
            f"  {_G}agent-eval claude uninstall --dry-run{_R}\n"
            f"  {_G}agent-eval claude uninstall --purge{_R} {_D}# also delete config + state{_R}\n"
        ),
    )
    _add_common_target_flags(uninstall_p)
    uninstall_p.add_argument(
        "--keep-config", dest="keep_config", action="store_true",
        help="Keep guardrail_config.json (default already keeps it unless --purge)",
    )
    uninstall_p.add_argument(
        "--purge", action="store_true",
        help="Also delete guardrail_config.json and the whole .agent-evaluator state dir",
    )
    uninstall_p.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Print what would be removed, change nothing",
    )
    uninstall_p.add_argument(
        "--yes", "-y", dest="yes", action="store_true",
        help="Skip the confirmation prompt",
    )
