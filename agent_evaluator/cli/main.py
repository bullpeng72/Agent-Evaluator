"""
agent-eval CLI — Agent Evaluator 설정 마법사.

사용법:
    agent-eval init       API 키 대화형 설정
    agent-eval check      현재 설정 상태 확인
    agent-eval --version  버전 출력
"""

from __future__ import annotations

import argparse
import getpass
import importlib
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    __version__ = _pkg_version("agent-evaluator")
except PackageNotFoundError:
    try:
        from agent_evaluator import __version__
    except ImportError:
        __version__ = "unknown"

from agent_evaluator.config import (
    DEFAULTS,
    find_dotenv,
    get_global_env_path,
    key_source,
    load_env,
)
from agent_evaluator.cli.gate import cmd_gate
from agent_evaluator.cli.dataset import cmd_dataset
from agent_evaluator.cli.monitor import build_monitor_subparser, cmd_monitor
from agent_evaluator.cli.opencode import build_opencode_subparser, cmd_opencode
from agent_evaluator.cli.trend import build_trend_subparser, cmd_trend
from agent_evaluator.cli._utils import _supports_color


# ---------------------------------------------------------------------------
# ANSI 색상 (터미널이 아닌 경우 비활성화)
# ---------------------------------------------------------------------------

_COLOR = _supports_color()

R  = "\033[0m"    if _COLOR else ""
B  = "\033[1m"    if _COLOR else ""   # bold
G  = "\033[32m"   if _COLOR else ""   # green
Y  = "\033[33m"   if _COLOR else ""   # yellow
C  = "\033[36m"   if _COLOR else ""   # cyan
D  = "\033[2m"    if _COLOR else ""   # dim
RD = "\033[31m"   if _COLOR else ""   # red
BL = "\033[34m"   if _COLOR else ""   # blue


def _ok(msg: str)   -> str: return f"{G}✅ {msg}{R}"
def _warn(msg: str) -> str: return f"{Y}⚠️  {msg}{R}"
def _err(msg: str)  -> str: return f"{RD}❌ {msg}{R}"
def _info(msg: str) -> str: return f"{BL}ℹ  {msg}{R}"
def _dim(msg: str)  -> str: return f"{D}{msg}{R}"
def _hdr(msg: str)  -> str: return f"{B}{C}{msg}{R}"


# ---------------------------------------------------------------------------
# ColoredHelpFormatter — argparse 도움말 컬러 출력
# ---------------------------------------------------------------------------

class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """ANSI 색상이 적용된 argparse HelpFormatter.

    TTY 여부는 _COLOR 전역 변수로 제어된다 (non-TTY 에서는 색상 없음).
    """

    def start_section(self, heading: Optional[str]) -> None:  # type: ignore[override]
        if heading and _COLOR:
            heading = f"{B}{heading}{R}"
        super().start_section(heading)

    def _format_usage(self, usage, actions, groups, prefix):  # type: ignore[override]
        if prefix is None:
            prefix = f"{B}Usage{R}: " if _COLOR else "Usage: "
        result = super()._format_usage(usage, actions, groups, prefix)
        if _COLOR:
            result = re.sub(r"\bagent-eval\b", f"{C}agent-eval{R}", result, count=1)
        return result

    def _format_action(self, action):  # type: ignore[override]
        result = super()._format_action(action)
        if not _COLOR:
            return result
        # --option 플래그 → 노란색
        result = re.sub(r"(--?[\w-]+)", f"{Y}\\1{R}", result)
        return result


# ---------------------------------------------------------------------------
# 키 메타데이터
# ---------------------------------------------------------------------------

KEY_DEFS: List[Dict] = [
    {
        "env":      "OPENAI_API_KEY",
        "label":    "OpenAI API Key",
        "required": False,
        "extra":    "llm",
        "used_for": "@agent_eval(framework='openai') · LLMJudge · DeepEval · Ragas (pip install 'agent-evaluator[llm]')",
        "url":      "https://platform.openai.com/api-keys",
        "prefix":   "sk-",
        "companion": [
            ("OPENAI_MODEL", "gpt-5-nano", "Model name to use"),
            ("AGENT_EVALUATOR_JUDGE_PROVIDER", "auto", "LLM Judge provider (auto / openai / anthropic)"),
        ],
    },
    {
        "env":      "ANTHROPIC_API_KEY",
        "label":    "Anthropic API Key",
        "required": False,
        "extra":    "llm",
        "used_for": "@agent_eval(framework='anthropic') · Claude 평가 (pip install 'agent-evaluator[llm]')",
        "url":      "https://console.anthropic.com/settings/keys",
        "prefix":   "sk-ant-",
        "companion": [
            ("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001", "Claude model name to use"),
        ],
    },
]



# ---------------------------------------------------------------------------
# 헬퍼: 마스킹
# ---------------------------------------------------------------------------

def _mask(value: str) -> str:
    """API 키를 앞 8자 + ... 형태로 마스킹한다."""
    if not value:
        return ""
    visible = min(8, max(1, len(value) - 3))
    return value[:visible] + "..."


def _current_value(env_var: str) -> Tuple[Optional[str], str]:
    """
    환경 변수의 현재 값과 출처를 반환한다.

    config._PRE_LOAD_KEYS 스냅샷을 통해 시스템 환경 변수와
    .env 로드 값을 정확히 구별한다.

    Returns:
        (value_or_None, source_label)
        source_label: "system env" | "loaded .env" | "not set"
    """
    val = os.environ.get(env_var, "")
    if not _is_real_key(val):
        return None, "not set"
    return val, key_source(env_var)


# ---------------------------------------------------------------------------
# .env 파일 읽기 / 쓰기
# ---------------------------------------------------------------------------

def _read_env_file(path: Path) -> Dict[str, str]:
    """기존 .env 파일을 파싱해 {key: value} 딕셔너리로 반환한다."""
    result: Dict[str, str] = {}
    if not path.is_file():
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    result[key] = val
    return result


def _update_env_file(env_path: Path, updates: Dict[str, str]) -> None:
    """
    .env 파일의 특정 키만 업데이트하거나 새로 추가한다.
    기존 주석·공백·다른 키는 그대로 보존한다.
    """
    lines: List[str] = []
    updated_keys: set = set()

    if env_path.is_file():
        with open(env_path, encoding="utf-8") as f:
            raw_lines = f.read().splitlines()

        for line in raw_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f'{key}={updates[key]}')
                    updated_keys.add(key)
                    continue
            lines.append(line)
    else:
        lines = []

    # 파일에 없던 새 키 추가
    new_keys = [k for k in updates if k not in updated_keys]
    if new_keys:
        if lines and lines[-1].strip():   # 빈 줄 구분
            lines.append("")
        lines.append("# Added by agent-eval init")
        for key in new_keys:
            lines.append(f"{key}={updates[key]}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")
    # API 키 파일은 소유자만 읽기/쓰기 가능하도록 제한 (POSIX: 0o600)
    try:
        env_path.chmod(0o600)
    except OSError:
        pass  # Windows 등 미지원 플랫폼에서는 무시


# ---------------------------------------------------------------------------
# 저장 위치 선택
# ---------------------------------------------------------------------------

def _choose_save_location(detected: Optional[Path]) -> Optional[Path]:
    """
    .env 저장 위치를 대화형으로 묻고 경로를 반환한다.
    None 이면 저장하지 않는다.
    """
    print()
    print(f"{B}Where do you want to save?{R}")

    options: List[Tuple[str, Optional[Path]]] = []

    if detected:
        label = f"Update existing file       {_dim(str(detected))}"
        options.append((label, detected))

    cwd_env = Path.cwd() / ".env"
    if not detected or detected != cwd_env:
        label = f"Create in current directory {_dim(str(cwd_env))}"
        options.append((label, cwd_env))

    global_env = get_global_env_path()
    label = f"Global config file         {_dim(str(global_env))}"
    options.append((label, global_env))

    options.append(("Don't save  (set env vars manually)", None))

    for i, (label, _) in enumerate(options, 1):
        print(f"  [{i}] {label}")

    default = 1
    try:
        raw = input(f"\nChoose [{default}]: ").strip()
        idx = int(raw) - 1 if raw else default - 1
        if not (0 <= idx < len(options)):
            raise ValueError
    except (ValueError, EOFError):
        idx = default - 1

    _, chosen_path = options[idx]
    return chosen_path


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:  # noqa: C901
    """대화형 API 키 설정 마법사."""

    print()
    print(_hdr(f"  Agent Evaluator v{__version__} — Setup Wizard  "))
    print(_dim("─" * 50))

    # .env 탐색
    detected = find_dotenv()
    global_env = get_global_env_path()

    if detected:
        print(_info(f".env found: {detected}"))
        load_env(detected)
    elif global_env.is_file():
        print(_info(f"Global config loaded: {global_env}"))
        load_env()
    else:
        print(_dim("  No .env file found. A new one will be created."))

    print()

    # 수집할 키값 저장
    to_save: Dict[str, str] = {}

    for step_num, key_def in enumerate(KEY_DEFS, 1):
        env_var   = key_def["env"]
        label     = key_def["label"]
        required  = key_def["required"]
        used_for  = key_def["used_for"]
        url       = key_def["url"]
        companions = key_def["companion"]

        badge = f"{RD}required{R}" if required else f"{D}optional{R}"
        print(f"{B}[{step_num}/{len(KEY_DEFS)}] {label}{R}  {badge}")
        print(f"  {_dim('Used for:')} {used_for}")
        print(f"  {_dim('Get key:')} {url}")

        current_val, source = _current_value(env_var)

        if current_val:
            print(f"  Current value: {G}{_mask(current_val)}{R}  {_dim(f'({source})')}")
            try:
                keep = input("  Keep existing? [Y/n]: ").strip().lower()
            except EOFError:
                keep = "y"
            if keep in ("n", "no"):
                # 새 값 입력
                prompt = "  Enter API key (blank to skip): "
                try:
                    new_val = getpass.getpass(prompt).strip()
                except (EOFError, getpass.GetPassWarning):
                    new_val = ""

                if new_val:
                    to_save[env_var] = new_val
                    print(f"  {G}→ Will be saved{R}  {_dim(_mask(new_val))}")
        else:
            print(f"  Current value: {_dim('not set')}")
            # 새 값 입력
            prompt = "  Enter API key (blank to skip): "
            try:
                new_val = getpass.getpass(prompt).strip()
            except (EOFError, getpass.GetPassWarning):
                new_val = ""

            if new_val:
                to_save[env_var] = new_val
                print(f"  {G}→ Will be saved{R}  {_dim(_mask(new_val))}")

        # companion 설정값 처리 (키가 있거나 새로 설정된 경우)
        effective_val = to_save.get(env_var) or current_val
        if effective_val:
            for comp_var, comp_default, comp_desc in companions:
                comp_cur, comp_src = _current_value(comp_var)

                # 모델명 등은 마스킹하지 않음 (키가 아니므로)
                val_display = _mask(comp_cur) if "KEY" in comp_var else (comp_cur or "")

                if comp_cur:
                    print(f"  {comp_var}: {val_display}  {_dim(f'({comp_src})')}")
                    if comp_cur != comp_default:
                        print(f"  {Y}Notice: New code default is {comp_default}{R}")

                    try:
                        keep_comp = input(f"  Keep existing {comp_var}? [Y/n]: ").strip().lower()
                    except EOFError:
                        keep_comp = "y"

                    if keep_comp in ("n", "no"):
                        comp_cur = None  # Force re-entry

                if not comp_cur:
                    try:
                        comp_input = input(
                            f"  {comp_var} [{comp_default}]  ({comp_desc}): "
                        ).strip()
                    except EOFError:
                        comp_input = ""
                    to_save[comp_var] = comp_input or comp_default

        print()

    # 기타 설정 (AGENT_EVALUATOR_OUTPUT_DIR)
    print(f"{B}[Other] Output Directory{R}")
    out_cur, out_src = _current_value("AGENT_EVALUATOR_OUTPUT_DIR")
    if out_cur:
        print(f"  Current value: {out_cur}  {_dim(f'({out_src})')}")
        try:
            keep = input("  Keep existing? [Y/n]: ").strip().lower()
        except EOFError:
            keep = "y"
        if keep in ("n", "no"):
            out_cur = None

    if not out_cur:
        try:
            new_out = input("  Results directory [./results]: ").strip()
        except EOFError:
            new_out = ""
        to_save["AGENT_EVALUATOR_OUTPUT_DIR"] = new_out or "./results"

    print()

    if not to_save:
        print(_ok("No changes. Using existing configuration."))
        return 0

    # 저장 위치 결정
    save_path = _choose_save_location(detected)

    if save_path is None:
        print()
        print(_warn("Not saved. Set environment variables manually:"))
        for k, v in to_save.items():
            # 보안: API 키 값은 마스킹하여 출력 (터미널 스크롤백·로그 노출 방지)
            print(f"  export {k}={_mask(v)}  {_dim('← replace with actual value')}")
        return 0

    # 파일 쓰기
    _update_env_file(save_path, to_save)

    print()
    print(_ok(f"Configuration saved → {save_path}"))
    print()

    # 저장된 키에 따라 필요한 extra 설치 힌트
    extras_needed: List[str] = []
    for kd in KEY_DEFS:
        if kd["env"] in to_save and kd.get("extra") not in extras_needed:
            extras_needed.append(kd["extra"])
    if extras_needed:
        print(_dim("  Required packages:"))
        for extra in extras_needed:
            print(f"    {C}pip install 'agent-evaluator[{extra}]'{R}")
        print()

    print(_dim("  To auto-load from your library:"))
    print(f"    {C}from agent_evaluator.config import load_env{R}")
    print(f"    {C}load_env()  # or specify dotenv_path=Path('...'){R}")
    print()
    print(_dim("  The project .env is auto-detected. (CWD → parent directory search)"))
    return 0


# ---------------------------------------------------------------------------
# cmd_check
# ---------------------------------------------------------------------------

def cmd_check(_args: argparse.Namespace) -> int:
    """현재 환경 설정 상태를 출력한다."""

    # .env 로드
    detected = find_dotenv()
    loaded_from = None
    if detected:
        load_env(detected)
        loaded_from = detected
    else:
        load_env()
        global_env = get_global_env_path()
        if global_env.is_file():
            loaded_from = global_env

    print()
    print(_hdr(f"  Agent Evaluator v{__version__} — Configuration Status  "))
    print(_dim("─" * 50))

    if loaded_from:
        print(_info(f"Loaded .env: {loaded_from}"))
    else:
        print(_dim("  No .env file (using system environment variables only)"))
    print()

    # 존재하는 .env 파일들
    existing_files: List[Path] = []
    if detected:
        existing_files.append(detected)
    global_env = get_global_env_path()
    if global_env.is_file() and global_env not in existing_files:
        existing_files.append(global_env)

    if existing_files:
        print(f"{B}Detected .env files:{R}")
        for p in existing_files:
            keys_in_file = list(_read_env_file(p).keys())
            print(f"  {p}  {_dim(f'({len(keys_in_file)} keys)')}")
        print()

    # API 키 상태
    print(f"{B}API Key Status:{R}")
    rows: List[Tuple[str, str, str, str]] = []
    for kd in KEY_DEFS:
        env_var = kd["env"]
        label   = kd["label"]
        val, src = _current_value(env_var)
        if val:
            status = f"{G}✅  {_mask(val)}{R}"
        elif kd["required"]:
            status = f"{RD}❌  not set (required){R}"
        else:
            status = f"{D}⚪  not set (optional){R}"
        rows.append((env_var, label, status, src))

    max_env = max(len(r[0]) for r in rows)
    for env_var, label, status, src in rows:
        pad = " " * (max_env - len(env_var))
        src_label = f"  {_dim(f'({src})')}" if src != "not set" else ""
        print(f"  {env_var}{pad}  {status}{src_label}")

    print()

    # 기타 설정 (DEFAULTS 상수로 단일 출처 유지)
    print(f"{B}Other Settings:{R}")
    for extra_var, desc in [
        ("AGENT_EVALUATOR_OUTPUT_DIR", "Results directory"),
        ("OPENAI_MODEL",               "OpenAI model"),
        ("ANTHROPIC_MODEL",            "Claude model"),
        ("LANGCHAIN_TRACING_V2",       "LangChain tracing"),
        ("LANGCHAIN_PROJECT",          "LangChain project"),
    ]:
        default_val = DEFAULTS.get(extra_var, "")
        val = os.getenv(extra_var, default_val)
        print(f"  {extra_var:35s}  {val}")

    # 패키지 설치 상태
    print()
    print(f"{B}Package Status:{R}")
    _PKG_MAP = [
        ("openai",     "llm",        "@agent_eval(framework='openai') · LLMJudge · DeepEval · Ragas"),
        ("anthropic",  "llm",        "@agent_eval(framework='anthropic') · LLMJudge"),
        ("langchain",  "langchain",  "@agent_eval(framework='langchain') · LangChain integration"),
        ("deepeval",   "eval",       "DeepEvalAdapter"),
        ("ragas",      "eval",       "RagasAdapter"),
    ]
    for pkg, extra, usage in _PKG_MAP:
        try:
            importlib.import_module(pkg)
            print(f"  {G}✅{R}  {pkg:12s}  {_dim(usage)}")
        except ImportError:
            print(f"  {D}⚪{R}  {pkg:12s}  {_dim(f'not installed  →  pip install agent-evaluator[{extra}]')}")

    print()
    print(_dim("  Run 'agent-eval init' to configure missing keys."))
    print()
    return 0


# ---------------------------------------------------------------------------
# cmd_version
# ---------------------------------------------------------------------------

def cmd_version(_args: argparse.Namespace) -> int:
    print(f"agent-evaluator {__version__}")
    return 0


# ---------------------------------------------------------------------------
# _print_welcome — `agent-eval` (인수 없음) 전용 웰컴 화면
# ---------------------------------------------------------------------------

_PLACEHOLDER_PREFIXES = ("your-", "your_", "<", "REPLACE", "CHANGE", "TODO", "FIXME", "example")

def _is_real_key(value: str) -> bool:
    """플레이스홀더나 빈 값을 실제 키로 오인하지 않도록 검증한다."""
    if not value:
        return False
    low = value.lower()
    return not any(low.startswith(p.lower()) for p in _PLACEHOLDER_PREFIXES)


def _print_welcome() -> None:
    """agent-eval 을 인수 없이 실행했을 때의 간결한 시작 화면."""

    # ── API 키 빠른 상태 체크 (import 없이 os.environ 직독) ──────────────
    load_env()
    _key_vars = [
        ("OPENAI_API_KEY",    "OpenAI",    False),
        ("ANTHROPIC_API_KEY", "Anthropic", False),
    ]
    set_count = sum(1 for k, _, _ in _key_vars if _is_real_key(os.environ.get(k, "")))
    total     = len(_key_vars)

    key_lines = []
    for env_var, label, required in _key_vars:
        if _is_real_key(os.environ.get(env_var, "")):
            key_lines.append(f"  {G}✔{R}  {label}")
        elif required:
            key_lines.append(f"  {RD}✘{R}  {label} {RD}(required — run agent-eval init){R}")
        else:
            key_lines.append(f"  {D}–{R}  {label} {D}(optional){R}")

    bar_filled = "█" * set_count
    bar_empty  = "░" * (total - set_count)
    bar_color  = G if set_count == total else (Y if set_count > 0 else RD)
    bar        = f"{bar_color}{bar_filled}{D}{bar_empty}{R}"

    print()
    print(f"  {B}{C}Agent Evaluator{R}  {D}v{__version__}{R}")
    print(f"  {D}{'─' * 36}{R}")
    print()
    print(f"  {B}API Key Status{R}  {bar}  {set_count}/{total}")
    for line in key_lines:
        print(line)
    print()
    print(f"  {B}Commands{R}")
    print(f"  {Y}init{R}       Interactive API key setup wizard")
    print(f"  {Y}check{R}      Show current configuration status")
    print(f"  {Y}dashboard{R}  Run the web dashboard  {D}(default port 8765){R}")
    print(f"  {Y}monitor{R}    Live monitoring  {D}(Phoenix + OTEL){R}")
    print(f"  {Y}gate{R}       CI/CD quality gating  {D}(pass/fail by threshold){R}")
    print(f"  {Y}trend{R}      Sequential evaluation trend analysis  {D}(TCR·accuracy regression){R}")
    print(f"  {Y}dataset{R}    Golden dataset management  {D}(auto-extract from results){R}")
    print(f"  {Y}--version{R}  Show version")
    print()
    print(f"  {D}Full options: {R}{C}agent-eval --help{R}")
    print()


# ---------------------------------------------------------------------------
# cmd_dashboard
# ---------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Start the FastAPI server and open /dashboard (developer/QM view)."""
    try:
        import uvicorn
    except ImportError:
        print(
            f"{RD}❌  uvicorn is not installed.{R}\n"
            f"   Install with: pip install 'agent-evaluator[serve]'",
            file=sys.stderr,
        )
        return 1

    try:
        from agent_evaluator.serve.server import create_app
    except ImportError as exc:
        print(f"{RD}❌  Failed to load server module: {exc}{R}", file=sys.stderr)
        return 1

    raw_dir      = getattr(args, "results_dir", None)
    host         = getattr(args, "host",    "127.0.0.1")
    port         = getattr(args, "port",    8765)
    watch        = getattr(args, "watch",   False)
    open_browser = getattr(args, "open",    True)
    offline      = getattr(args, "offline", False)
    title        = getattr(args, "title",   "Agent Evaluator — Dev Dashboard")
    # SPEC-005: CLI 플래그 우선, 없으면 환경변수 폴백. 둘 다 없으면 auth_token=None(무인증, 기존 동작).
    auth_token   = getattr(args, "auth_token", None) or os.environ.get("AGENT_EVALUATOR_DASHBOARD_TOKEN")

    user_specified = raw_dir not in (None, "./results", "results")
    if user_specified:
        results_dir = Path(raw_dir).resolve()
    else:
        default_dir = Path("./results").resolve()
        has_results = default_dir.exists() and any(default_dir.rglob("*.json"))
        if has_results:
            results_dir = default_dir
        else:
            try:
                from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
                detected = get_evaluation_results_dir()
                if detected.exists() and any(detected.rglob("*.json")):
                    results_dir = detected
                    print(f"  {_dim(f'ℹ  Results directory auto-detected: {results_dir}')}")
                else:
                    results_dir = default_dir
            except Exception:
                results_dir = default_dir

    if not results_dir.exists():
        results_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    json_files = list(results_dir.rglob("*.json"))
    n_files = len([f for f in json_files
                   if not any(p in str(f) for p in
                              ("traces/", "audit_logs/", "annotations/",
                               "transparent_reports/", "golden_datasets/"))])
    print()
    print(f"  {B}Agent Evaluator Dev Dashboard{R} v{__version__}")
    print(f"  {'─' * 40}")
    print(f"  📁  Results dir   : {results_dir}  ({n_files} files found)")
    print(f"  🗂️   Dev Dashboard : {base_url}/dashboard")
    print(f"  🌐  Dashboard     : {base_url}")
    print(f"  📊  Slides        : {base_url}/slides")
    print(f"  📡  API docs      : {base_url}/api/docs")
    print(f"  🔄  Watch mode    : {'ON' if watch else 'OFF'}")
    print(f"  🔒  Auth          : {'ON (Bearer token required)' if auth_token else 'OFF (localhost-only assumption)'}")
    print()
    print(f"  {_dim('Press Ctrl+C to stop')}")
    print()

    app = create_app(
        results_dir=results_dir,
        title=title,
        watch=watch,
        version=__version__,
        offline=offline,
        auth_token=auth_token,
    )

    if open_browser:
        import threading
        import webbrowser
        url = f"{base_url}/dashboard"

        def _open():
            import time
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


# ---------------------------------------------------------------------------
# 라이브러리 사용자용 헬퍼: config 모듈에서 재export
# (cli/main.py 를 라이브러리 모드로 임포트하는 비용 없이 사용 가능)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# argparse entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-eval",
        description=(
            f"{B}{C}Agent Evaluator CLI{R} — AI agent evaluation framework\n"
            "\n"
            "Manages the entire pipeline of collecting, saving, and visualizing evaluation results.\n"
            "Supports API key setup, environment check, web dashboard, CI/CD gating,\n"
            "golden dataset management, Phoenix live monitoring, and trend analysis."
        ),
        formatter_class=ColoredHelpFormatter,
        epilog=(
            f"{B}Commands:{R}\n"
            f"  {Y}init{R}         Interactively configure OpenAI/Anthropic API keys\n"
            f"  {Y}check{R}        Show API key and configuration status\n"
            f"  {Y}dashboard{R}    Run the FastAPI web dashboard for evaluation results\n"
            f"  {Y}gate{R}         CI/CD quality gating — pass/fail by threshold\n"
            f"  {Y}trend{R}        Sequential evaluation trend analysis — TCR/accuracy regression\n"
            f"  {Y}dataset{R}      Auto-extract golden datasets from production results\n"
            f"  {Y}monitor{R}      Start Arize Phoenix + OTLP span receiver (live monitoring)\n"
            f"  {Y}opencode{R}     Install the LiveGuardrail OpenCode plugin\n"
            "\n"
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval init{R}\n"
            f"  {G}agent-eval check{R}\n"
            f"  {G}agent-eval dashboard{R}\n"
            f"  {G}agent-eval dashboard ./results --port 8080{R}\n"
            f"  {G}agent-eval dashboard ./results --watch --no-open{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --accuracy 70{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --save-baseline{R}\n"
            f"  {G}agent-eval trend results/ --window 10{R}\n"
            f"  {G}agent-eval trend results/ --fail-on-regression{R}\n"
            f"  {G}agent-eval dataset build --source results/ --max-cases 30{R}\n"
            f"  {G}agent-eval monitor{R}\n"
            f"  {G}agent-eval monitor --port 6007{R}\n"
            f"  {G}agent-eval monitor --check{R}\n"
            f"  {G}agent-eval monitor --reset{R}\n"
            f"  {G}agent-eval monitor --reset --yes{R}\n"
            f"  {G}agent-eval opencode install{R}\n"
            f"  {G}agent-eval --version{R}\n"
            "\n"
            f"{B}More help:{R}\n"
            f"  {D}agent-eval <command> --help{R}"
        ),
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "init",
        help="Interactive API key setup wizard",
        description=(
            "Interactively enter OpenAI and Anthropic API keys\n"
            "and save them to a .env file.\n"
            "\n"
            f"{B}Settings:{R}\n"
            f"  {C}OPENAI_API_KEY{R}              {D}(optional){R} @agent_eval(framework='openai') · LLMJudge · DeepEval · Ragas\n"
            f"  {C}ANTHROPIC_API_KEY{R}           {D}(optional){R} @agent_eval(framework='anthropic') · Claude evaluation\n"
            f"  {C}AGENT_EVALUATOR_OUTPUT_DIR{R}  Evaluation results directory {D}(default: ./results){R}\n"
            "\n"
            f"{B}Save location:{R} chosen interactively at runtime\n"
            f"  • Update detected existing .env {D}(if found){R}\n"
            f"  • Create .env in current directory\n"
            f"  • Global config {D}(~/.agent-evaluator/.env — used by all projects){R}\n"
            f"  • Don't save {D}(print export commands){R}\n"
            "\n"
            f"{B}Load priority:{R}\n"
            f"  system env > explicit path > CWD .env search > ~/.agent-evaluator/.env"
        ),
        formatter_class=ColoredHelpFormatter,
    )
    sub.add_parser(
        "check",
        help="Show current configuration status",
        description=(
            "Show API key and configuration status for the current environment.\n"
            "\n"
            f"{B}Output includes:{R}\n"
            f"  {Y}API key status{R}    {C}OPENAI_API_KEY{R}, {C}ANTHROPIC_API_KEY{R}\n"
            f"  {Y}Other settings{R}    {C}AGENT_EVALUATOR_OUTPUT_DIR{R}, {C}OPENAI_MODEL{R},\n"
            f"                   {C}ANTHROPIC_MODEL{R}, {C}LANGCHAIN_TRACING_V2{R},\n"
            f"                   {C}LANGCHAIN_PROJECT{R}\n"
            f"  {Y}Package status{R}    openai, anthropic, langchain, deepeval, ragas installed\n"
            f"  {Y}.env location{R}     path of loaded .env file\n"
            "\n"
            f"{D}API keys are shown as the first 8 characters only (rest masked).{R}"
        ),
        formatter_class=ColoredHelpFormatter,
    )
    # dashboard subcommand
    dash_p = sub.add_parser(
        "dashboard",
        help="Run the evaluation results web dashboard (default port 8765)",
        formatter_class=ColoredHelpFormatter,
        description=(
            "Run the FastAPI web dashboard for visualizing evaluation results.\n"
            f"{D}Requires: pip install 'agent-evaluator[serve]'{R}\n"
            "\n"
            f"{B}URLs:{R}\n"
            f"  {C}http://localhost:8765/dashboard{R}  Dev dashboard (main, auto-opens browser)\n"
            f"  {C}http://localhost:8765{R}            Dashboard\n"
            f"  {C}http://localhost:8765/slides{R}     Slides view\n"
            f"  {C}http://localhost:8765/sdk-docs{R}   SDK docs\n"
            f"  {C}http://localhost:8765/api/docs{R}   Swagger UI\n"
        ),
        epilog=(
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval dashboard{R}\n"
            f"  {G}agent-eval dashboard ./results --port 8080{R}\n"
            f"  {G}agent-eval dashboard ./results --watch{R}\n"
            f"  {G}agent-eval dashboard ./results --no-open{R}\n"
            f"  {G}agent-eval dashboard ./results --offline{R}\n"
        ),
    )
    dash_p.add_argument(
        "results_dir", nargs="?", default="./results",
        help="Evaluation results JSON directory (default: ./results)",
    )
    dash_p.add_argument("--host",  default="127.0.0.1", metavar="HOST",
                        help="Bind host (default: 127.0.0.1)")
    dash_p.add_argument("--port",  default=8765, type=int, metavar="PORT",
                        help="Port number (default: 8765)")
    dash_p.add_argument("--open",  action="store_true", default=True,
                        help="Auto-open browser after server starts (default)")
    dash_p.add_argument("--no-open", dest="open", action="store_false",
                        help="Disable auto-open browser")
    dash_p.add_argument("--watch", action="store_true",
                        help="Watch result files for changes and auto-refresh")
    dash_p.add_argument("--offline", action="store_true",
                        help="Cache CDN assets locally for offline use")
    dash_p.add_argument("--title", default="Agent Evaluator — Dev Dashboard",
                        metavar="TITLE",
                        help="Dashboard title (default: 'Agent Evaluator — Dev Dashboard')")
    dash_p.add_argument(
        "--auth-token", dest="auth_token", default=None, metavar="TOKEN",
        help="Require Bearer token (or AGENT_EVALUATOR_DASHBOARD_TOKEN env var) to access "
             "the dashboard. Default: no authentication (localhost-only assumption).",
    )

    # gate subcommand
    gate_p = sub.add_parser(
        "gate",
        help="CI/CD quality gating — pass/fail by threshold",
        formatter_class=ColoredHelpFormatter,
        description=(
            "Read evaluation result JSON and determine pass/fail by threshold.\n"
            "Use as a quality gate in CI/CD pipelines (GitHub Actions, GitLab CI, etc.).\n"
            "\n"
            f"{B}Supported metrics:{R}\n"
            f"  {Y}--tcr{R}               Task Completion Rate (%%)\n"
            f"  {Y}--accuracy{R}          Accuracy (%%)\n"
            f"  {Y}--p95-latency{R}       P95 latency upper bound (seconds)\n"
            f"  {Y}--hallucination{R}     Hallucination rate upper bound (%%)\n"
            f"  {Y}--llm-judge{R}         LLM Judge overall score lower bound (0–5)\n"
            f"  {Y}--fail-on-regression{R} Allowed regression vs baseline (%%)\n"
        ),
        epilog=(
            f"{B}Exit codes:{R}\n"
            f"  {G}0{R}  All criteria passed\n"
            f"  {RD}1{R}  Below threshold\n"
            f"  {RD}2{R}  Regression detected vs previous version (when --fail-on-regression used)\n"
            "\n"
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --accuracy 70 --p95-latency 3.0{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --save-baseline{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --fail-on-regression 10{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --junit-xml test-results.xml{R}\n"
        ),
    )
    gate_p.add_argument("result_file", help="Evaluation result JSON file path")
    gate_p.add_argument("--tcr", type=float, metavar="PCT", help="Minimum TCR (%%)")
    gate_p.add_argument("--accuracy", type=float, metavar="PCT", help="Minimum accuracy (%%)")
    gate_p.add_argument(
        "--p95-latency", type=float, metavar="SEC", dest="p95_latency",
        help="Maximum P95 latency (seconds)",
    )
    gate_p.add_argument(
        "--hallucination", type=float, metavar="PCT",
        help="Maximum hallucination rate (%%)",
    )
    gate_p.add_argument(
        "--llm-judge", type=float, metavar="SCORE", dest="llm_judge",
        help="Minimum LLM Judge overall score (0–5)",
    )
    gate_p.add_argument(
        "--fail-on-regression", type=float, metavar="PCT", dest="fail_on_regression",
        help="Allowed regression vs baseline (%%) — returns exit code 2 if exceeded",
    )
    gate_p.add_argument(
        "--baseline", metavar="PATH",
        help="Baseline file path (default: <result_dir>/baseline.json)",
    )
    gate_p.add_argument(
        "--save-baseline", action="store_true", dest="save_baseline",
        help="Save current results as baseline",
    )
    gate_p.add_argument(
        "--junit-xml", metavar="PATH", dest="junit_xml",
        help="JUnit XML output path (for CI system integration)",
    )
    gate_p.add_argument(
        "--min-gate-score", type=float, metavar="SCORE", dest="min_gate_score",
        help=(
            "Harness Gate A–G composite score lower bound (0.0–1.0). "
            "Fails if weighted group average falls below this value."
        ),
    )
    gate_p.add_argument(
        "--group-weights", metavar="WEIGHTS", dest="group_weights",
        help=(
            "Per-gate group weights (default: all 1.0). "
            "Format: 'A:2.0,B:1.5,E:3.0'. "
            "Used with --min-gate-score."
        ),
    )
    gate_p.add_argument(
        "--gate-thresholds", metavar="THRESHOLDS", dest="gate_thresholds",
        help=(
            "Per-gate minimum score thresholds (0.0–1.0). "
            "Format: 'A:0.8,D:0.9,E:0.95'. "
            "Gates not listed fall back to --min-gate-score."
        ),
    )
    gate_p.add_argument(
        "--required-gates", metavar="GATES", dest="required_gates",
        help=(
            "Comma-separated list of Gates to check. "
            "Format: 'A,D,E'. Default: all Gates with data."
        ),
    )
    gate_p.add_argument(
        "--fail-on-gate-warn", action="store_true", dest="fail_on_gate_warn",
        help="Treat Gate status 'warn' as failure.",
    )

    # dataset subcommand
    ds_p = sub.add_parser(
        "dataset",
        help="Golden dataset management (build — auto-extract from results)",
        formatter_class=ColoredHelpFormatter,
        description=(
            "Manage golden datasets.\n"
            "Auto-extract high-quality cases from production results for regression testing.\n"
            f"{D}For Phoenix upload use 'agent-eval monitor --sync-datasets'.{R}\n"
        ),
        epilog=(
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval dataset build{R}\n"
            f"  {G}agent-eval dataset build --source results/ --strategy failure_cases edge_cases{R}\n"
            f"  {G}agent-eval dataset build --max-cases 30 --output data/golden_datasets/{R}\n"
        ),
    )
    ds_sub = ds_p.add_subparsers(dest="dataset_command")

    build_p = ds_sub.add_parser(
        "build",
        help="Auto-extract golden dataset candidates from result files",
        formatter_class=ColoredHelpFormatter,
        description=(
            "Auto-extract golden dataset candidates from production evaluation result JSON files.\n"
            "\n"
            f"{B}Extraction strategies (--strategy){R}\n"
            f"  {Y}failure_cases{R}  Failed tasks → regression test material {D}(default){R}\n"
            f"  {Y}edge_cases{R}     Outliers (abnormal length, special chars, etc.) {D}(default){R}\n"
            f"  {Y}high_value{R}     Cases with high positive feedback\n"
            f"  {Y}coverage_gap{R}   Types not yet covered by existing golden set\n"
        ),
        epilog=(
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval dataset build{R}\n"
            f"  {G}agent-eval dataset build --source results/ --strategy failure_cases high_value{R}\n"
            f"  {G}agent-eval dataset build --max-cases 30 --output data/golden_datasets/{R}\n"
            f"  {G}agent-eval dataset build --no-review --name my_golden.json{R}\n"
        ),
    )
    build_p.add_argument(
        "--source", default="./results", metavar="DIR",
        help="Results JSON directory (default: ./results)",
    )
    build_p.add_argument(
        "--output", default=None, metavar="DIR",
        help="Golden set output directory (default: <source>/golden_datasets/)",
    )
    build_p.add_argument(
        "--strategy", nargs="+",
        default=["failure_cases", "edge_cases"],
        metavar="STRATEGY",
        help="Extraction strategy — multiple values allowed (default: failure_cases edge_cases)",
    )
    build_p.add_argument(
        "--max-cases", type=int, default=50, dest="max_cases", metavar="N",
        help="Maximum number of cases to extract (default: 50)",
    )
    build_p.add_argument(
        "--no-review", action="store_true", dest="no_review",
        help="Save immediately without human review (default: includes review-needed flag)",
    )
    build_p.add_argument(
        "--name", default=None, metavar="FILENAME",
        help="Output filename (default: candidates_YYYYMMDD_HHMMSS.json)",
    )

    # monitor subcommand
    build_monitor_subparser(sub)

    # opencode subcommand
    build_opencode_subparser(sub)

    # trend subcommand
    build_trend_subparser(sub)

    parser.add_argument(
        "--version", action="store_true",
        help="Show package version",
    )

    args = parser.parse_args()

    if args.version:
        sys.exit(cmd_version(args))

    handlers = {
        "init":      cmd_init,
        "check":     cmd_check,
        "dashboard": cmd_dashboard,
        "monitor":   cmd_monitor,
        "opencode":  cmd_opencode,
        "gate":      cmd_gate,
        "dataset":   cmd_dataset,
        "trend":     cmd_trend,
    }

    if args.command is None:
        _print_welcome()
        sys.exit(0)

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
