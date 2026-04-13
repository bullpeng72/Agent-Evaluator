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
            prefix = f"{B}사용법{R}: " if _COLOR else "사용법: "
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
            ("OPENAI_MODEL", "gpt-4o-mini", "사용할 모델명"),
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
            ("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001", "사용할 Claude 모델명"),
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
    print(f"{B}어디에 저장할까요?{R}")

    options: List[Tuple[str, Optional[Path]]] = []

    if detected:
        label = f"기존 파일에 추가/업데이트  {_dim(str(detected))}"
        options.append((label, detected))

    cwd_env = Path.cwd() / ".env"
    if not detected or detected != cwd_env:
        label = f"현재 디렉토리에 생성       {_dim(str(cwd_env))}"
        options.append((label, cwd_env))

    global_env = get_global_env_path()
    label = f"전역 설정 파일             {_dim(str(global_env))}"
    options.append((label, global_env))

    options.append(("저장하지 않음  (환경 변수를 직접 설정)", None))

    for i, (label, _) in enumerate(options, 1):
        print(f"  [{i}] {label}")

    default = 1
    try:
        raw = input(f"\n선택 [{default}]: ").strip()
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
    print(_hdr(f"  Agent Evaluator v{__version__} — 설정 마법사  "))
    print(_dim("─" * 50))

    # .env 탐색
    detected = find_dotenv()
    global_env = get_global_env_path()

    if detected:
        print(_info(f".env 발견: {detected}"))
        load_env(detected)
    elif global_env.is_file():
        print(_info(f"전역 설정 로드: {global_env}"))
        load_env()
    else:
        print(_dim("  설정된 .env 파일이 없습니다. 새로 만들겠습니다."))

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

        badge = f"{RD}필수{R}" if required else f"{D}선택{R}"
        print(f"{B}[{step_num}/{len(KEY_DEFS)}] {label}{R}  {badge}")
        print(f"  {_dim('용도:')} {used_for}")
        print(f"  {_dim('발급:')} {url}")

        current_val, source = _current_value(env_var)

        if current_val:
            print(f"  현재 값: {G}{_mask(current_val)}{R}  {_dim(f'({source})')}")
            try:
                keep = input("  그대로 유지할까요? [Y/n]: ").strip().lower()
            except EOFError:
                keep = "y"
            if keep not in ("n", "no"):
                print()
                continue
        else:
            print(f"  현재 값: {_dim('설정 안 됨')}")

        # 새 값 입력
        prompt = f"  {'API 키' if not required else '  API 키'} 입력 (빈칸=건너뜀): "
        try:
            new_val = getpass.getpass(prompt).strip()
        except (EOFError, getpass.GetPassWarning):
            new_val = ""

        if new_val:
            to_save[env_var] = new_val
            print(f"  {G}→ 저장 예정{R}  {_dim(_mask(new_val))}")

            # companion 설정값 처리
            for comp_var, comp_default, comp_desc in companions:
                comp_cur, comp_src = _current_value(comp_var)
                if comp_cur:
                    print(
                        f"  {_dim(comp_var)}: {_mask(comp_cur)}  {_dim(f'({comp_src})')} "
                        f"— {_dim('유지')}"
                    )
                else:
                    try:
                        comp_input = input(
                            f"  {comp_var} [{comp_default}]  ({comp_desc}): "
                        ).strip()
                    except EOFError:
                        comp_input = ""
                    to_save[comp_var] = comp_input or comp_default

        print()

    # 기타 설정 (AGENT_EVALUATOR_OUTPUT_DIR)
    print(f"{B}[기타] 출력 디렉토리 설정{R}")
    out_cur, out_src = _current_value("AGENT_EVALUATOR_OUTPUT_DIR")
    if out_cur:
        print(f"  현재 값: {out_cur}  {_dim(f'({out_src})')}")
        try:
            keep = input("  그대로 유지할까요? [Y/n]: ").strip().lower()
        except EOFError:
            keep = "y"
        if keep in ("n", "no"):
            out_cur = None

    if not out_cur:
        try:
            new_out = input("  결과 저장 경로 [./results]: ").strip()
        except EOFError:
            new_out = ""
        to_save["AGENT_EVALUATOR_OUTPUT_DIR"] = new_out or "./results"

    print()

    if not to_save:
        print(_ok("변경 사항이 없습니다. 기존 설정을 사용합니다."))
        return 0

    # 저장 위치 결정
    save_path = _choose_save_location(detected)

    if save_path is None:
        print()
        print(_warn("저장하지 않았습니다. 아래를 참고해 환경 변수를 직접 설정하세요:"))
        for k, v in to_save.items():
            # 보안: API 키 값은 마스킹하여 출력 (터미널 스크롤백·로그 노출 방지)
            print(f"  export {k}={_mask(v)}  {_dim('← 실제 값으로 교체하세요')}")
        return 0

    # 파일 쓰기
    _update_env_file(save_path, to_save)

    print()
    print(_ok(f"설정이 저장되었습니다 → {save_path}"))
    print()

    # 저장된 키에 따라 필요한 extra 설치 힌트
    extras_needed: List[str] = []
    for kd in KEY_DEFS:
        if kd["env"] in to_save and kd.get("extra") not in extras_needed:
            extras_needed.append(kd["extra"])
    if extras_needed:
        print(_dim("  필요한 패키지 설치:"))
        for extra in extras_needed:
            print(f"    {C}pip install 'agent-evaluator[{extra}]'{R}")
        print()

    print(_dim("  라이브러리에서 자동 로드하려면:"))
    print(f"    {C}from agent_evaluator.config import load_env{R}")
    print(f"    {C}load_env()  # 혹은 dotenv_path=Path('...') 지정{R}")
    print()
    print(_dim("  현재 프로젝트 .env 가 자동으로 인식됩니다. (CWD → 상위 탐색)"))
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
    print(_hdr(f"  Agent Evaluator v{__version__} — 설정 상태  "))
    print(_dim("─" * 50))

    if loaded_from:
        print(_info(f".env 로드: {loaded_from}"))
    else:
        print(_dim("  .env 파일 없음 (시스템 환경 변수만 사용)"))
    print()

    # 존재하는 .env 파일들
    existing_files: List[Path] = []
    if detected:
        existing_files.append(detected)
    global_env = get_global_env_path()
    if global_env.is_file() and global_env not in existing_files:
        existing_files.append(global_env)

    if existing_files:
        print(f"{B}발견된 .env 파일:{R}")
        for p in existing_files:
            keys_in_file = list(_read_env_file(p).keys())
            print(f"  {p}  {_dim(f'({len(keys_in_file)}개 키)')}")
        print()

    # API 키 상태
    print(f"{B}API 키 상태:{R}")
    rows: List[Tuple[str, str, str, str]] = []
    for kd in KEY_DEFS:
        env_var = kd["env"]
        label   = kd["label"]
        val, src = _current_value(env_var)
        if val:
            status = f"{G}✅  {_mask(val)}{R}"
        elif kd["required"]:
            status = f"{RD}❌  미설정 (필수){R}"
        else:
            status = f"{D}⚪  미설정 (선택){R}"
        rows.append((env_var, label, status, src))

    max_env = max(len(r[0]) for r in rows)
    for env_var, label, status, src in rows:
        pad = " " * (max_env - len(env_var))
        src_label = f"  {_dim(f'({src})')}" if src != "not set" else ""
        print(f"  {env_var}{pad}  {status}{src_label}")

    print()

    # 기타 설정 (DEFAULTS 상수로 단일 출처 유지)
    print(f"{B}기타 설정:{R}")
    for extra_var, desc in [
        ("AGENT_EVALUATOR_OUTPUT_DIR", "결과 저장 경로"),
        ("OPENAI_MODEL",               "OpenAI 모델"),
        ("ANTHROPIC_MODEL",            "Claude 모델"),
        ("LANGCHAIN_TRACING_V2",       "LangChain 트레이싱"),
        ("LANGCHAIN_PROJECT",          "LangChain 프로젝트"),
    ]:
        default_val = DEFAULTS.get(extra_var, "")
        val = os.getenv(extra_var, default_val)
        print(f"  {extra_var:35s}  {val}")

    # 패키지 설치 상태
    print()
    print(f"{B}패키지 상태:{R}")
    _PKG_MAP = [
        ("openai",     "llm",        "@agent_eval(framework='openai') · LLMJudge · DeepEval · Ragas"),
        ("anthropic",  "llm",        "@agent_eval(framework='anthropic') · LLMJudge"),
        ("langchain",  "langchain",  "@agent_eval(framework='langchain') · LangChain 프레임워크 통합"),
        ("deepeval",   "eval",       "DeepEvalAdapter"),
        ("ragas",      "eval",       "RagasAdapter"),
    ]
    for pkg, extra, usage in _PKG_MAP:
        try:
            importlib.import_module(pkg)
            print(f"  {G}✅{R}  {pkg:12s}  {_dim(usage)}")
        except ImportError:
            print(f"  {D}⚪{R}  {pkg:12s}  {_dim(f'미설치  →  pip install agent-evaluator[{extra}]')}")

    print()
    print(_dim("  'agent-eval init' 을 실행하면 누락된 키를 설정할 수 있습니다."))
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
            key_lines.append(f"  {RD}✘{R}  {label} {RD}(필수 — agent-eval init 으로 설정){R}")
        else:
            key_lines.append(f"  {D}–{R}  {label} {D}(선택){R}")

    bar_filled = "█" * set_count
    bar_empty  = "░" * (total - set_count)
    bar_color  = G if set_count == total else (Y if set_count > 0 else RD)
    bar        = f"{bar_color}{bar_filled}{D}{bar_empty}{R}"

    print()
    print(f"  {B}{C}Agent Evaluator{R}  {D}v{__version__}{R}")
    print(f"  {D}{'─' * 36}{R}")
    print()
    print(f"  {B}API 키 현황{R}  {bar}  {set_count}/{total}")
    for line in key_lines:
        print(line)
    print()
    print(f"  {B}명령어{R}")
    print(f"  {Y}init{R}       API 키 대화형 설정 마법사")
    print(f"  {Y}check{R}      현재 설정 상태 출력")
    print(f"  {Y}dashboard{R}  웹 대시보드 실행  {D}(기본 포트 8765){R}")
    print(f"  {Y}monitor{R}    운영 실시간 모니터링  {D}(Phoenix + OTEL){R}")
    print(f"  {Y}gate{R}       CI/CD 품질 게이팅  {D}(임계값 기준 통과/실패){R}")
    print(f"  {Y}trend{R}      순차 평가 결과 추세 분석  {D}(TCR·정확도 회귀 감지){R}")
    print(f"  {Y}dataset{R}    골든 데이터셋 관리  {D}(운영 결과 자동 추출){R}")
    print(f"  {Y}--version{R}  버전 출력")
    print()
    print(f"  {D}전체 옵션 보기: {R}{C}agent-eval --help{R}")
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
            f"{RD}❌  uvicorn 이 설치되지 않았습니다.{R}\n"
            f"   pip install 'agent-evaluator[serve]' 로 설치하세요.",
            file=sys.stderr,
        )
        return 1

    try:
        from agent_evaluator.serve.server import create_app
    except ImportError as exc:
        print(f"{RD}❌  서버 모듈 로드 실패: {exc}{R}", file=sys.stderr)
        return 1

    raw_dir      = getattr(args, "results_dir", None)
    host         = getattr(args, "host",    "127.0.0.1")
    port         = getattr(args, "port",    8765)
    watch        = getattr(args, "watch",   False)
    open_browser = getattr(args, "open",    True)
    offline      = getattr(args, "offline", False)
    title        = getattr(args, "title",   "Agent Evaluator — Dev Dashboard")

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
                    print(f"  {_dim(f'ℹ  결과 디렉토리 자동 감지: {results_dir}')}")
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
    print(f"  📁  Results dir   : {results_dir}  ({n_files}개 파일 발견)")
    print(f"  🗂️   Dev Dashboard : {base_url}/dashboard")
    print(f"  🌐  원본 대시보드  : {base_url}")
    print(f"  📊  Slides        : {base_url}/slides")
    print(f"  📡  API docs      : {base_url}/api/docs")
    print(f"  🔄  Watch mode    : {'ON' if watch else 'OFF'}")
    print()
    print(f"  {_dim('Ctrl+C 로 종료')}")
    print()

    app = create_app(
        results_dir=results_dir,
        title=title,
        watch=watch,
        version=__version__,
        offline=offline,
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
            f"{B}{C}Agent Evaluator CLI{R} — AI 에이전트 평가 프레임워크\n"
            "\n"
            "평가 결과 수집·저장·시각화 전 구간을 단일 명령어로 관리합니다.\n"
            "API 키 설정, 환경 상태 확인, 웹 대시보드 실행, CI/CD 게이팅,\n"
            "골든 데이터셋 관리, Phoenix 실시간 모니터링, 추세 분석을 지원합니다."
        ),
        formatter_class=ColoredHelpFormatter,
        epilog=(
            f"{B}명령어:{R}\n"
            f"  {Y}init{R}         OpenAI·Anthropic API 키를 대화형으로 설정\n"
            f"  {Y}check{R}        현재 환경의 API 키 및 설정값 상태를 출력\n"
            f"  {Y}dashboard{R}    평가 결과를 시각화하는 FastAPI 웹 대시보드 실행\n"
            f"  {Y}gate{R}         CI/CD 품질 게이팅 — 임계값 기준 통과/실패 판정\n"
            f"  {Y}trend{R}        순차 평가 결과 추세 분석 — TCR·정확도 회귀 감지\n"
            f"  {Y}dataset{R}      운영 결과에서 골든 데이터셋 자동 추출\n"
            f"  {Y}monitor{R}      Arize Phoenix 기동 + OTLP 스팬 수신 설정 (실시간 모니터링)\n"
            "\n"
            f"{B}예시:{R}\n"
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
            f"  {G}agent-eval --version{R}\n"
            "\n"
            f"{B}더 자세한 도움말:{R}\n"
            f"  {D}agent-eval <명령어> --help{R}"
        ),
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "init",
        help="대화형 API 키 설정 마법사",
        description=(
            "OpenAI, Anthropic API 키를\n"
            "대화형으로 입력하고 .env 파일에 저장합니다.\n"
            "\n"
            f"{B}설정 항목:{R}\n"
            f"  {C}OPENAI_API_KEY{R}              {D}(선택){R} @agent_eval(framework='openai') · LLMJudge · DeepEval · Ragas\n"
            f"  {C}ANTHROPIC_API_KEY{R}           {D}(선택){R} @agent_eval(framework='anthropic') · Claude 평가\n"
            f"  {C}AGENT_EVALUATOR_OUTPUT_DIR{R}  평가 결과 저장 디렉토리 {D}(기본: ./results){R}\n"
            "\n"
            f"{B}저장 위치:{R} 실행 시 대화형으로 선택합니다\n"
            f"  • 탐지된 기존 .env 업데이트 {D}(존재하는 경우){R}\n"
            f"  • 현재 디렉토리에 .env 생성\n"
            f"  • 전역 설정 {D}(~/.agent-evaluator/.env — 모든 프로젝트에서 사용){R}\n"
            f"  • 저장하지 않음 {D}(export 명령어 출력){R}\n"
            "\n"
            f"{B}로드 우선순위:{R}\n"
            f"  시스템 환경변수 > 명시적 경로 > CWD 탐색 .env > ~/.agent-evaluator/.env"
        ),
        formatter_class=ColoredHelpFormatter,
    )
    sub.add_parser(
        "check",
        help="현재 설정 상태 확인",
        description=(
            "현재 환경에 설정된 API 키 및 설정값 상태를 출력합니다.\n"
            "\n"
            f"{B}출력 항목:{R}\n"
            f"  {Y}API 키 상태{R}    {C}OPENAI_API_KEY{R}, {C}ANTHROPIC_API_KEY{R}\n"
            f"  {Y}기타 설정{R}      {C}AGENT_EVALUATOR_OUTPUT_DIR{R}, {C}OPENAI_MODEL{R},\n"
            f"               {C}ANTHROPIC_MODEL{R}, {C}LANGCHAIN_TRACING_V2{R},\n"
            f"               {C}LANGCHAIN_PROJECT{R}\n"
            f"  {Y}패키지 상태{R}    openai, anthropic, langchain, deepeval, ragas 설치 여부\n"
            f"  {Y}.env 위치{R}      로드된 .env 파일 경로\n"
            "\n"
            f"{D}API 키는 앞 8자만 표시되며 나머지는 마스킹됩니다.{R}"
        ),
        formatter_class=ColoredHelpFormatter,
    )
    # dashboard subcommand
    dash_p = sub.add_parser(
        "dashboard",
        help="평가 결과 시각화 웹 대시보드 실행 (기본 포트 8765)",
        formatter_class=ColoredHelpFormatter,
        description=(
            "평가 결과를 시각화하는 FastAPI 웹 대시보드를 실행합니다.\n"
            f"{D}pip install 'agent-evaluator[serve]' 필요{R}\n"
            "\n"
            f"{B}접속 URL:{R}\n"
            f"  {C}http://localhost:8765/dashboard{R}  Dev 대시보드 (메인, 브라우저 자동 오픈)\n"
            f"  {C}http://localhost:8765{R}            원본 대시보드\n"
            f"  {C}http://localhost:8765/slides{R}     슬라이드 뷰\n"
            f"  {C}http://localhost:8765/sdk-docs{R}   SDK 문서\n"
            f"  {C}http://localhost:8765/api/docs{R}   Swagger UI\n"
        ),
        epilog=(
            f"{B}예시:{R}\n"
            f"  {G}agent-eval dashboard{R}\n"
            f"  {G}agent-eval dashboard ./results --port 8080{R}\n"
            f"  {G}agent-eval dashboard ./results --watch{R}\n"
            f"  {G}agent-eval dashboard ./results --no-open{R}\n"
            f"  {G}agent-eval dashboard ./results --offline{R}\n"
        ),
    )
    dash_p.add_argument(
        "results_dir", nargs="?", default="./results",
        help="평가 결과 JSON 파일 디렉토리 (기본: ./results)",
    )
    dash_p.add_argument("--host",  default="127.0.0.1", metavar="HOST",
                        help="바인딩 호스트 (기본: 127.0.0.1)")
    dash_p.add_argument("--port",  default=8765, type=int, metavar="PORT",
                        help="포트 번호 (기본: 8765)")
    dash_p.add_argument("--open",  action="store_true", default=True,
                        help="서버 시작 후 브라우저 자동 오픈 (기본값)")
    dash_p.add_argument("--no-open", dest="open", action="store_false",
                        help="브라우저 자동 오픈 비활성화")
    dash_p.add_argument("--watch", action="store_true",
                        help="결과 파일 변경 감시 후 자동 갱신")
    dash_p.add_argument("--offline", action="store_true",
                        help="CDN 에셋을 로컬에 캐시해 인터넷 없이 실행")
    dash_p.add_argument("--title", default="Agent Evaluator — Dev Dashboard",
                        metavar="TITLE",
                        help="대시보드 제목 (기본: 'Agent Evaluator — Dev Dashboard')")

    # gate subcommand
    gate_p = sub.add_parser(
        "gate",
        help="CI/CD 품질 게이팅 — 임계값 기준 통과/실패 판정",
        formatter_class=ColoredHelpFormatter,
        description=(
            "평가 결과 JSON 파일을 읽어 임계값 기준으로 통과/실패를 판정합니다.\n"
            "CI/CD 파이프라인(GitHub Actions, GitLab CI 등)에 연동해 품질 게이트로 사용합니다.\n"
            "\n"
            f"{B}지원 지표:{R}\n"
            f"  {Y}--tcr{R}               Task Completion Rate — 태스크 완료율 (%%)\n"
            f"  {Y}--accuracy{R}          정확도 (%%)\n"
            f"  {Y}--p95-latency{R}       P95 지연시간 상한 (초)\n"
            f"  {Y}--hallucination{R}     환각 탐지율 상한 (%%)\n"
            f"  {Y}--llm-judge{R}         LLM Judge 종합 점수 하한 (0–5)\n"
            f"  {Y}--fail-on-regression{R} 기준선 대비 허용 회귀 폭 (%%)\n"
        ),
        epilog=(
            f"{B}종료 코드:{R}\n"
            f"  {G}0{R}  모든 기준 통과\n"
            f"  {RD}1{R}  임계값 기준 미달\n"
            f"  {RD}2{R}  이전 버전 대비 회귀 감지 (--fail-on-regression 사용 시)\n"
            "\n"
            f"{B}예시:{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --accuracy 70 --p95-latency 3.0{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --save-baseline{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --fail-on-regression 10{R}\n"
            f"  {G}agent-eval gate results/ci_run.json --tcr 85 --junit-xml test-results.xml{R}\n"
        ),
    )
    gate_p.add_argument("result_file", help="평가 결과 JSON 파일 경로")
    gate_p.add_argument("--tcr", type=float, metavar="PCT", help="최소 TCR (%%)")
    gate_p.add_argument("--accuracy", type=float, metavar="PCT", help="최소 정확도 (%%)")
    gate_p.add_argument(
        "--p95-latency", type=float, metavar="SEC", dest="p95_latency",
        help="최대 P95 지연시간 (초)",
    )
    gate_p.add_argument(
        "--hallucination", type=float, metavar="PCT",
        help="최대 환각 탐지율 (%%)",
    )
    gate_p.add_argument(
        "--llm-judge", type=float, metavar="SCORE", dest="llm_judge",
        help="최소 LLM Judge 종합 점수 (0–5)",
    )
    gate_p.add_argument(
        "--fail-on-regression", type=float, metavar="PCT", dest="fail_on_regression",
        help="기준선 대비 허용 회귀 비율 (%%) — 이보다 나빠지면 종료 코드 2 반환",
    )
    gate_p.add_argument(
        "--baseline", metavar="PATH",
        help="기준선 파일 경로 (기본: <result_dir>/baseline.json)",
    )
    gate_p.add_argument(
        "--save-baseline", action="store_true", dest="save_baseline",
        help="현재 결과를 기준선으로 저장",
    )
    gate_p.add_argument(
        "--junit-xml", metavar="PATH", dest="junit_xml",
        help="JUnit XML 출력 경로 (CI 시스템 연동)",
    )

    # dataset subcommand
    ds_p = sub.add_parser(
        "dataset",
        help="골든 데이터셋 관리 (build — 운영 결과에서 자동 추출)",
        formatter_class=ColoredHelpFormatter,
        description=(
            "골든 데이터셋을 관리합니다.\n"
            "운영 평가 결과에서 고품질 케이스를 자동 추출해 회귀 테스트 소재로 활용합니다.\n"
            f"{D}Phoenix 업로드는 'agent-eval monitor --sync-datasets' 를 사용하세요.{R}\n"
        ),
        epilog=(
            f"{B}예시:{R}\n"
            f"  {G}agent-eval dataset build{R}\n"
            f"  {G}agent-eval dataset build --source results/ --strategy failure_cases edge_cases{R}\n"
            f"  {G}agent-eval dataset build --max-cases 30 --output data/golden_datasets/{R}\n"
        ),
    )
    ds_sub = ds_p.add_subparsers(dest="dataset_command")

    build_p = ds_sub.add_parser(
        "build",
        help="운영 결과 파일에서 골든셋 후보 자동 추출",
        formatter_class=ColoredHelpFormatter,
        description=(
            "운영 평가 결과 JSON 파일에서 골든 데이터셋 후보를 자동으로 추출합니다.\n"
            "\n"
            f"{B}추출 전략 (--strategy){R}\n"
            f"  {Y}failure_cases{R}  실패 태스크 → 회귀 테스트 소재 {D}(기본){R}\n"
            f"  {Y}edge_cases{R}     이상치 (비정상 길이·특수문자 등) {D}(기본){R}\n"
            f"  {Y}high_value{R}     긍정 피드백 높은 케이스\n"
            f"  {Y}coverage_gap{R}   기존 골든셋 미커버 유형\n"
        ),
        epilog=(
            f"{B}예시:{R}\n"
            f"  {G}agent-eval dataset build{R}\n"
            f"  {G}agent-eval dataset build --source results/ --strategy failure_cases high_value{R}\n"
            f"  {G}agent-eval dataset build --max-cases 30 --output data/golden_datasets/{R}\n"
            f"  {G}agent-eval dataset build --no-review --name my_golden.json{R}\n"
        ),
    )
    build_p.add_argument(
        "--source", default="./results", metavar="DIR",
        help="결과 JSON 파일 디렉토리 (기본: ./results)",
    )
    build_p.add_argument(
        "--output", default=None, metavar="DIR",
        help="골든셋 출력 디렉토리 (기본: <source>/golden_datasets/)",
    )
    build_p.add_argument(
        "--strategy", nargs="+",
        default=["failure_cases", "edge_cases"],
        metavar="STRATEGY",
        help="추출 전략 — 복수 지정 가능 (기본: failure_cases edge_cases). 위 설명 참조",
    )
    build_p.add_argument(
        "--max-cases", type=int, default=50, dest="max_cases", metavar="N",
        help="추출할 최대 케이스 수 (기본: 50)",
    )
    build_p.add_argument(
        "--no-review", action="store_true", dest="no_review",
        help="사람 검토 없이 바로 저장 (기본: 검토 필요 플래그 포함)",
    )
    build_p.add_argument(
        "--name", default=None, metavar="FILENAME",
        help="저장 파일 이름 (기본: candidates_YYYYMMDD_HHMMSS.json)",
    )

    # monitor subcommand
    build_monitor_subparser(sub)

    # trend subcommand
    build_trend_subparser(sub)

    parser.add_argument(
        "--version", action="store_true",
        help="패키지 버전 출력",
    )

    args = parser.parse_args()

    if args.version:
        sys.exit(cmd_version(args))

    handlers = {
        "init":      cmd_init,
        "check":     cmd_check,
        "dashboard": cmd_dashboard,
        "monitor":   cmd_monitor,
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
