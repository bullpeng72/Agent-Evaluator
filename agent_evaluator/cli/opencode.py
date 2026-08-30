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
import contextlib
import json
import shutil
import subprocess as subprocess  # re-export: tests monkeypatch opencode.subprocess.run directly
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_evaluator.cli._integration_health import DoctorReport

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

# SPEC-041: 이 마커가 설치된 .ts에 없으면 그 플러그인은 구버전이다 — 외부
# agent-evaluator.config.json 설정 분리·stdio 데스싱크 수정·다중턴 세션 수정 등이
# 전부 빠져 있다는 뜻이라, "이미 있음" 거부 메시지에서 --force를 강하게 권한다.
_CURRENT_PLUGIN_MARKER = "EFFECTIVE_GUARDRAIL_CONFIG"


def _plugin_is_stale(content: str) -> bool:
    return bool(_missing_hooks(content)) or _CURRENT_PLUGIN_MARKER not in content


def cmd_opencode(args: argparse.Namespace) -> int:
    """opencode 서브커맨드 진입점."""
    cmd = getattr(args, "opencode_command", None)
    if cmd == "install":
        return _cmd_install(args)
    if cmd == "upgrade":
        return _cmd_upgrade(args)
    if cmd == "uninstall":
        return _cmd_uninstall(args)
    if cmd == "doctor":
        return _cmd_doctor(args)
    print(
        f"{_B}agent-eval opencode{_R} — LiveGuardrail OpenCode Plugin\n\n"
        f"  {_Y}install{_R}     Copy the bundled plugin into OpenCode's plugin directory\n"
        f"  {_Y}upgrade{_R}     Re-copy the plugin after a package update (keeps "
        f"agent-evaluator.config.json)\n"
        f"  {_Y}doctor{_R}      Verify the install works (plugin freshness + bridge round-trip)\n"
        f"  {_Y}uninstall{_R}   Remove the plugin + MCP entries (run before 'pip uninstall')\n\n"
        f"Usage: agent-eval opencode <command> --help",
        file=sys.stderr,
    )
    return 1


_VIOLATION_SEARCH_MCP_NAME = "agent-evaluator-violations"
_RECOMMEND_FIX_MCP_NAME = "agent-evaluator-recommend-fix"


def _register_mcp_server(name: str, module: str, flag: str) -> None:
    """``opencode mcp add``로 ``module``의 stdio MCP 서버를 등록한다.

    ``_register_violation_search_mcp()``/``_register_recommend_fix_mcp()``가 공유하는
    실행부 — 두 도구 모두 실패해도(``opencode`` CLI 미설치, ``mcp`` extra 미설치 등)
    경고만 출력하고 예외를 올리지 않는다. 플러그인 설치 자체(``_cmd_install``의 본래
    목적)는 이 등록 성공 여부와 무관하게 이미 끝난 뒤이므로, 이 단계의 실패로 전체
    install 명령을 실패 처리할 이유가 없다(``live_guardrail_report.py`` 저장 실패가
    세션 종료를 막지 않는 것과 동일한 원칙, SPEC-019 Rollout 6단계 참고).
    """
    _manual = f"opencode mcp add {name} -- {sys.executable} -m {module}"
    try:
        result = subprocess.run(
            ["opencode", "mcp", "add", name, "--", sys.executable, "-m", module],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print(
            f"{_Y}⚠️  {flag}: 'opencode' CLI not found — skipping MCP server registration. "
            f"Register manually: {_manual}{_R}",
            file=sys.stderr,
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"{_Y}⚠️  {flag}: 'opencode mcp add' timed out — register it manually.{_R}",
            file=sys.stderr,
        )
        return

    if result.returncode == 0:
        print(f"{_G}✅ MCP server registered: {name}{_R}")
    elif "already exists" in (result.stderr or "").lower():
        # 재설치/업그레이드 시 정상 상태 — 실패가 아니다.
        print(f"{_D}   MCP server already registered: {name} — nothing to change{_R}")
    else:
        print(
            f"{_Y}⚠️  {flag}: 'opencode mcp add' failed (exit {result.returncode}) — "
            f"register manually: {_manual}{_R}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"{_D}   {result.stderr.strip()}{_R}", file=sys.stderr)


# ``opencode mcp``에는 ``remove`` 서브커맨드가 없다(add/list/auth/logout/debug 뿐) —
# uninstall은 opencode 설정 JSON의 ``mcp.<name>`` 키를 직접 지운다.
_OPENCODE_GLOBAL_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
_OPENCODE_LOCAL_CONFIGS = (Path("opencode.json"), Path("opencode.jsonc"))


def _deregister_mcp_servers(names: list[str], *, is_global: bool) -> None:
    """opencode 설정 JSON에서 ``mcp.<name>`` 항목을 제거한다.

    ``opencode mcp``에 ``remove``가 없어 파일을 직접 편집한다. ``.jsonc``(주석 포함)는
    안전하게 파싱할 수 없으므로 발견 시 수동 안내만 출력한다.
    """
    if is_global:
        candidates = [_OPENCODE_GLOBAL_CONFIG]
    else:
        candidates = [Path.cwd() / c for c in _OPENCODE_LOCAL_CONFIGS]

    touched_any = False
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix == ".jsonc":
            print(
                f"{_Y}⚠️  {path} is JSONC (may contain comments) — not editing automatically. "
                f"Remove these keys by hand: mcp.{', mcp.'.join(names)}{_R}",
                file=sys.stderr,
            )
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"{_Y}⚠️  Could not read {path} ({exc}) — remove mcp entries by hand.{_R}",
                  file=sys.stderr)
            continue
        mcp = data.get("mcp")
        if not isinstance(mcp, dict):
            continue
        removed = [n for n in names if mcp.pop(n, None) is not None]
        if not removed:
            continue
        if not mcp:
            data.pop("mcp", None)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"{_G}✅ Removed MCP entr{'y' if len(removed) == 1 else 'ies'} "
              f"from {path}: {', '.join(removed)}{_R}")
        touched_any = True

    if not touched_any:
        print(f"{_D}   No opencode.json MCP entries to remove "
              f"({'global' if is_global else 'project'} scope){_R}")


def _register_recommend_fix_mcp() -> None:
    """(``--with-recommend-fix``) ``opencode mcp add``로 ``recommend_fix`` stdio MCP
    서버를 등록한다 — ``search_violations``와 나란히 등록하는 정적 지식 조회 도구다."""
    _register_mcp_server(
        _RECOMMEND_FIX_MCP_NAME,
        "agent_evaluator.integrations.recommend_fix_mcp",
        "--with-recommend-fix",
    )


def _register_violation_search_mcp() -> None:
    """(SPEC-024 REQ-6) ``opencode mcp add``로 REQ-4의 stdio MCP 서버를 등록한다."""
    _register_mcp_server(
        _VIOLATION_SEARCH_MCP_NAME,
        "agent_evaluator.integrations.violation_search_mcp",
        "--with-violation-search",
    )


def _cmd_install(args: argparse.Namespace) -> int:
    """번들된 agent-evaluator.ts를 OpenCode 플러그인 디렉터리로 복사한다."""
    if not _BUNDLED_PLUGIN.exists():
        print(f"{_RD}❌ Bundled plugin not found: {_BUNDLED_PLUGIN}{_R}", file=sys.stderr)
        return 1

    is_global: bool = getattr(args, "global_install", False)
    force: bool = getattr(args, "force", False)
    target = _GLOBAL_TARGET if is_global else _LOCAL_TARGET

    if target.exists() and not force:
        try:
            _stale = _plugin_is_stale(target.read_text(encoding="utf-8"))
        except OSError:
            _stale = False
        _cfg_hint = (
            "Put project config in a sibling agent-evaluator.config.json (JSON object, "
            "shallow-merged over the built-in defaults) — that file is never touched by "
            "reinstall, so future updates cost you nothing."
        )
        if _stale:
            print(
                f"{_Y}⚠️  {target} is OUT OF DATE{_R} — the bundled plugin has important "
                f"fixes it is missing (external config file, stdio response-id matching, "
                f"multi-turn session handling, fail-open hardening).\n"
                f"{_D}   Move any GUARDRAIL_CONFIG edits into agent-evaluator.config.json, "
                f"then rerun with --force. {_cfg_hint}{_R}",
                file=sys.stderr,
            )
        else:
            print(
                f"{_Y}⚠️  Already exists: {target}{_R} — use --force to overwrite the plugin "
                f"code.\n{_D}   {_cfg_hint}{_R}",
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

    if getattr(args, "with_recommend_fix", False):
        print()
        _register_recommend_fix_mcp()

    print()
    print(f"{_B}Next steps:{_R}")
    print(
        f"  1. To customize, create {target.parent / 'agent-evaluator.config.json'} — a JSON "
        f"object whose top-level keys (scope, tool_parameter_safety, …) are shallow-merged "
        f"over the built-in defaults."
    )
    print(
        f"     {_D}Keep config in that file, NOT in the .ts — reinstalling overwrites the .ts "
        f"code but never the .config.json.{_R}"
    )
    print("  2. Restart OpenCode (or start a new session) so it loads the plugin")
    print(
        f"  {_D}Full Config/tracker option reference: "
        f"agent_evaluator/gates/gate_b_behavioral/configs.py, "
        f"agent_evaluator/core/trackers/security.py{_R}"
    )
    print()
    print(
        f"{_Y}💡 Tuning tip:{_R} loop_detection.consecutive_repeat_threshold (plugin default 8) "
        f"fires only on N *identical* calls in a row — same tool name AND same arguments "
        f"(SPEC-041); a varied `bash` → `bash` → `bash` sequence with different commands is not a "
        f"loop. live_loop_window (default 15) also bounds the check to the last N calls. Raise the "
        f"threshold further only if you still see a legitimate genuinely-repeated call (e.g. "
        f"re-running the same failing test) getting flagged."
    )
    return 0


_MCP_NAMES = [_VIOLATION_SEARCH_MCP_NAME, _RECOMMEND_FIX_MCP_NAME]
_LGR_STDIO_MODULE = "agent_evaluator.integrations.live_guardrail_stdio"
_LGR_PLUGIN_MODULE = "agent_evaluator.integrations.opencode_plugin"  # doctor import 프로브용
_SIBLING_CONFIG = "agent-evaluator.config.json"


# ===========================================================================
# upgrade — 패키지 업데이트 후 플러그인 .ts만 갱신 (config.json은 절대 안 건드림)
# ===========================================================================
def _cmd_upgrade(args: argparse.Namespace) -> int:
    is_global: bool = getattr(args, "global_install", False)
    target = _GLOBAL_TARGET if is_global else _LOCAL_TARGET

    if not _BUNDLED_PLUGIN.exists():
        print(f"{_RD}❌ Bundled plugin not found: {_BUNDLED_PLUGIN}{_R}", file=sys.stderr)
        return 1
    if not target.exists():
        print(
            f"{_Y}No installed plugin at {target} — run `agent-eval opencode install` first.{_R}",
            file=sys.stderr,
        )
        return 1

    try:
        current = target.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{_RD}❌ Could not read {target}: {exc}{_R}", file=sys.stderr)
        return 1

    content = _BUNDLED_PLUGIN.read_text(encoding="utf-8").replace(
        _PYTHON_PLACEHOLDER, sys.executable,
    )
    if content == current:
        print(f"{_D}   Plugin already up to date ({target}){_R}")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"{_G}✅ Refreshed plugin: {target}{_R}")
    print(f"{_D}   python interpreter (baked in): {sys.executable}{_R}")

    sibling = target.parent / _SIBLING_CONFIG
    if sibling.exists():
        print(f"{_D}   {sibling} left untouched (your config){_R}")

    missing = _missing_hooks(content)
    if missing:
        print(
            f"{_RD}⚠️  Installed plugin is missing hook(s): {', '.join(missing)} — please "
            f"file an issue.{_R}",
            file=sys.stderr,
        )

    print()
    print(f"{_B}Done.{_R} Restart OpenCode (or start a new session) to load the refreshed plugin.")
    print(f"{_D}Run `agent-eval opencode doctor` to verify.{_R}")
    return 0


# ===========================================================================
# uninstall — 플러그인 파일 + MCP 항목 제거 (pip uninstall 전에 실행)
# ===========================================================================
def _cmd_uninstall(args: argparse.Namespace) -> int:
    is_global: bool = getattr(args, "global_install", False)
    keep_config: bool = getattr(args, "keep_config", False)
    purge: bool = getattr(args, "purge", False)
    dry_run: bool = getattr(args, "dry_run", False)
    assume_yes: bool = getattr(args, "yes", False)

    target = _GLOBAL_TARGET if is_global else _LOCAL_TARGET
    sibling = target.parent / _SIBLING_CONFIG

    plan: list[str] = []
    if target.exists():
        plan.append(f"delete plugin file {target}")
    if sibling.exists():
        if purge and not keep_config:
            plan.append(f"delete {sibling} (--purge)")
        else:
            plan.append(f"keep {sibling} (your config — pass --purge to remove)")
    plan.append(
        f"remove mcp.{{{', '.join(_MCP_NAMES)}}} from "
        f"{'~/.config/opencode/opencode.json' if is_global else './opencode.json'} if present"
    )

    if not target.exists() and not sibling.exists():
        print(f"{_D}No installed plugin at {target}.{_R}")
        if not dry_run:
            _deregister_mcp_servers(_MCP_NAMES, is_global=is_global)
        return 0

    print(f"{_B}agent-eval opencode uninstall{_R} will:")
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

    if target.exists():
        target.unlink()
        print(f"{_G}✅ Deleted {target}{_R}")
    if sibling.exists() and purge and not keep_config:
        sibling.unlink()
        print(f"{_G}✅ Deleted {sibling}{_R}")
    with contextlib.suppress(OSError):
        target.parent.rmdir()  # 비었을 때만

    _deregister_mcp_servers(_MCP_NAMES, is_global=is_global)

    print()
    print(
        f"{_B}Next:{_R} pip uninstall agent-evaluator  "
        f"{_D}(plugin is gone — safe to remove the package now){_R}"
    )
    return 0


# ===========================================================================
# doctor — 플러그인 신선도 + Python stdio 브리지 라운드트립
# ===========================================================================
def _doctor_bridge_roundtrip(rpt: DoctorReport) -> None:
    """live_guardrail_stdio 브리지를 띄워 init·check(허용/차단)·shutdown을 확인한다."""
    probe_cfg = {
        "op": "init",
        "tool_parameter_safety": {
            "dangerous_patterns": [r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f"],
            "scope_tool_names": ["bash"],
            "fail_on_dangerous": True,
        },
        "scope": {"forbidden_tools": ["webfetch"], "fail_on_violation": True},
    }
    msgs = [
        probe_cfg,
        {"op": "check", "task_id": "d", "tool_name": "read", "parameters": {"filePath": "x"}},
        {"op": "check", "task_id": "d", "tool_name": "bash",
         "parameters": {"command": "rm -rf /tmp/ae-doctor-xyz"}},
        {"op": "check", "task_id": "d", "tool_name": "webfetch", "parameters": {"url": "http://x"}},
        {"op": "shutdown"},
    ]
    payload = "\n".join(json.dumps(m) for m in msgs) + "\n"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", _LGR_STDIO_MODULE],
            input=payload, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        rpt.error("live", "Python stdio bridge round-trip", str(exc))
        return

    responses = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            with contextlib.suppress(json.JSONDecodeError):
                responses.append(json.loads(line))
    # 기대: [ {ok:true}, {block:false...}, {block:true...}, {block:true...} ]
    if len(responses) < 4:
        err_tail = (proc.stderr or "").strip().splitlines()
        rpt.error(
            "live", "Python stdio bridge round-trip",
            f"got {len(responses)} response(s), expected ≥4"
            + (f" ({err_tail[-1][:120]})" if err_tail else ""),
        )
        return
    init_ok = responses[0].get("ok") is True
    allow_ok = responses[1].get("block") is False
    rm_block = responses[2].get("block") is True
    web_block = responses[3].get("block") is True
    if init_ok:
        rpt.ok("live", "bridge init → ok")
    else:
        rpt.error("live", "bridge init → ok", str(responses[0]))
    if allow_ok:
        rpt.ok("live", "check: benign read → allow")
    else:
        rpt.error("live", "check: benign read → allow", str(responses[1]))
    if rm_block:
        rpt.ok("live", "check: rm -rf → block")
    else:
        rpt.error("live", "check: rm -rf → block", str(responses[2]))
    if web_block:
        rpt.ok("live", "check: webfetch → block (scope.forbidden_tools)")
    else:
        rpt.warn("live", "check: webfetch → block", str(responses[3]))


def _cmd_doctor(args: argparse.Namespace) -> int:
    from agent_evaluator.cli._integration_health import (
        DoctorReport,
        probe_import,
        validate_guardrail_config,
    )

    is_global: bool = getattr(args, "global_install", False)
    as_json: bool = getattr(args, "json", False)
    no_live: bool = getattr(args, "no_live", False)
    strict: bool = getattr(args, "strict", False)

    target = _GLOBAL_TARGET if is_global else _LOCAL_TARGET
    # OpenCode auto-loads plugins from BOTH the project-local and the global dir, so a
    # missing project-local plugin is not an error when a global one is installed —
    # fall back to checking that instead (mirrors OpenCode's own resolution).
    fell_back_to_global = False
    if not is_global and not target.exists() and _GLOBAL_TARGET.exists():
        target = _GLOBAL_TARGET
        fell_back_to_global = True

    sibling = target.parent / _SIBLING_CONFIG
    rpt = DoctorReport(title=f"agent-eval opencode doctor — {target}")

    # ---------- Tier 1: 정적 ----------
    content: str | None = None
    if not target.exists():
        rpt.error(
            "static", "plugin file exists",
            f"not found: {target} — run `agent-eval opencode install`"
            + ("" if is_global else " (or add --global)"),
        )
    else:
        try:
            content = target.read_text(encoding="utf-8")
            _detail = f"{target} (global — no project-local install)" if fell_back_to_global \
                else str(target)
            rpt.ok("static", "plugin file exists", _detail)
        except OSError as exc:
            rpt.error("static", "plugin file readable", str(exc))

    if content is not None:
        missing = _missing_hooks(content)
        if missing:
            rpt.error("static", "all hooks present", f"missing: {', '.join(missing)}")
        else:
            rpt.ok("static", "all hooks present", "tool.execute.before/after, event")
        if _CURRENT_PLUGIN_MARKER in content:
            rpt.ok("static", "plugin not stale")
        else:
            rpt.warn(
                "static", "plugin not stale",
                "missing recent fixes — run `agent-eval opencode upgrade`",
            )
        if _PYTHON_PLACEHOLDER in content:
            rpt.error(
                "static", "python interpreter baked in",
                "still the literal placeholder — reinstall so a real path is substituted",
            )
        else:
            rpt.ok("static", "python interpreter baked in")

    ok, err = probe_import(sys.executable, _LGR_STDIO_MODULE)
    if ok:
        rpt.ok("static", "bridge module importable", sys.executable)
    else:
        rpt.error("static", "bridge module importable", err)

    if sibling.exists():
        try:
            user_cfg = json.loads(sibling.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            rpt.error("static", f"{_SIBLING_CONFIG} is valid JSON", str(exc))
            user_cfg = None
        if isinstance(user_cfg, dict):
            built, warns = validate_guardrail_config(user_cfg)
            if built and not warns:
                rpt.ok("static", f"{_SIBLING_CONFIG} builds")
            elif built:
                rpt.warn("static", f"{_SIBLING_CONFIG} builds", f"SKIPPED: {' | '.join(warns)}")
            else:
                rpt.error("static", f"{_SIBLING_CONFIG} builds", " | ".join(warns))
        elif user_cfg is not None:
            rpt.warn(
                "static", f"{_SIBLING_CONFIG} is a JSON object", "top-level value is not an object",
            )
    else:
        rpt.info("static", f"{_SIBLING_CONFIG}", "not present (using plugin built-in defaults)")

    js_runtime = shutil.which("bun") or shutil.which("node")
    if js_runtime:
        rpt.ok("static", "JS runtime for the plugin", js_runtime)
    else:
        rpt.warn(
            "static", "JS runtime for the plugin",
            "neither 'bun' nor 'node' on PATH — OpenCode itself needs one to run the plugin",
        )

    # ---------- Tier 2: 라이브 (Python 브리지 라운드트립) ----------
    if no_live:
        rpt.info("live", "skipped (--no-live)")
    elif not ok:
        rpt.info("live", "skipped — bridge module not importable")
    else:
        _doctor_bridge_roundtrip(rpt)

    if as_json:
        print(rpt.render_json())
    else:
        print(rpt.render_text(color=_USE_COLOR))
    return rpt.exit_code(strict=strict)


def _add_common_target_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--global", dest="global_install", action="store_true",
        help="Target ~/.config/opencode/plugin/ instead of the project-local .opencode/plugin/",
    )


def build_opencode_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """opencode 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "opencode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Install the LiveGuardrail OpenCode plugin (real-time Gate B/E guardrail)",
        description=(
            "Install the bundled OpenCode plugin (LiveGuardrail reference implementation)\n"
            "into the location OpenCode auto-loads plugins from.\n"
            f"{_D}The plugin is a thin Node/Bun stdio client — the sole source of truth\n"
            f"for Gate B/E judgment logic always stays in the Python LiveGuardrail.{_R}"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode install{_R}\n"
            f"  {_G}agent-eval opencode install --global{_R}\n"
            f"  {_G}agent-eval opencode install --force{_R}\n"
            f"  {_G}agent-eval opencode install --with-violation-search{_R}\n"
            f"  {_G}agent-eval opencode install --with-recommend-fix{_R}\n"
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
            f"  {_G}agent-eval opencode install --with-recommend-fix{_R}\n"
            f"      {_D}# + register recommend_fix MCP server{_R}\n"
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
            "Also run 'opencode mcp add' to register the "
            "search_violations MCP server (opt-in, requires the 'mcp' extra: "
            "pip install \"agent-evaluator[mcp]\")"
        ),
    )
    install_p.add_argument(
        "--with-recommend-fix", dest="with_recommend_fix", action="store_true",
        help=(
            "Also run 'opencode mcp add' to register the "
            "recommend_fix MCP server — static Gate/metric remediation lookup, "
            "no result file required (opt-in, requires the 'mcp' extra: "
            "pip install \"agent-evaluator[mcp]\")"
        ),
    )

    # --- upgrade ---
    upgrade_p = op_sub.add_parser(
        "upgrade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Re-copy the bundled plugin after a package update (keeps your config.json)",
        description=(
            "Overwrite the installed agent-evaluator.ts with the current bundled version\n"
            "(re-baking the interpreter path). The sibling agent-evaluator.config.json is\n"
            "NEVER touched. No-op if the file is already identical."
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode upgrade{_R}\n"
            f"  {_G}agent-eval opencode upgrade --global{_R}\n"
        ),
    )
    _add_common_target_flags(upgrade_p)

    # --- doctor ---
    doctor_p = op_sub.add_parser(
        "doctor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Verify the install works (plugin freshness + Python bridge round-trip)",
        description=(
            "Static: plugin file present, all 3 hooks present, not stale, interpreter path\n"
            "substituted (not the literal placeholder), bridge module importable,\n"
            "agent-evaluator.config.json valid, a JS runtime (bun/node) on PATH.\n"
            "Live: spawns the live_guardrail_stdio bridge and checks init + a benign call\n"
            "is allowed + `rm -rf`/webfetch are blocked.\n"
            "Exit 1 on any error (add --strict to also fail on warnings)."
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode doctor{_R}\n"
            f"  {_G}agent-eval opencode doctor --global --json{_R}\n"
            f"  {_G}agent-eval opencode doctor --no-live{_R}\n"
        ),
    )
    _add_common_target_flags(doctor_p)
    doctor_p.add_argument(
        "--no-live", dest="no_live", action="store_true",
        help="Static checks only — don't spawn the bridge subprocess",
    )
    doctor_p.add_argument("--json", action="store_true", help="Emit the report as JSON (for CI)")
    doctor_p.add_argument(
        "--strict", action="store_true", help="Exit 1 on warnings too, not just errors",
    )

    # --- uninstall ---
    uninstall_p = op_sub.add_parser(
        "uninstall",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Remove the plugin file + MCP entries (run BEFORE 'pip uninstall agent-evaluator')",
        description=(
            "Deletes the installed agent-evaluator.ts and removes the mcp.<name> entries\n"
            "from opencode.json (opencode has no `mcp remove` subcommand, so this edits the\n"
            "JSON directly; .jsonc files are left for you to edit by hand).\n"
            "Keeps agent-evaluator.config.json unless --purge.\n\n"
            "NOTE: `agent-eval` disappears once the package is uninstalled, so run this\n"
            "first.  Order:  agent-eval opencode uninstall  →  pip uninstall agent-evaluator"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval opencode uninstall{_R}\n"
            f"  {_G}agent-eval opencode uninstall --global --yes{_R}\n"
            f"  {_G}agent-eval opencode uninstall --dry-run{_R}\n"
            f"  {_G}agent-eval opencode uninstall --purge{_R} {_D}# also delete config.json{_R}\n"
        ),
    )
    _add_common_target_flags(uninstall_p)
    uninstall_p.add_argument(
        "--keep-config", dest="keep_config", action="store_true",
        help="Keep agent-evaluator.config.json (default already keeps it unless --purge)",
    )
    uninstall_p.add_argument(
        "--purge", action="store_true",
        help="Also delete agent-evaluator.config.json",
    )
    uninstall_p.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Print what would be removed, change nothing",
    )
    uninstall_p.add_argument(
        "--yes", "-y", dest="yes", action="store_true", help="Skip the confirmation prompt",
    )
