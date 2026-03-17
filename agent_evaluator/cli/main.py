"""
agent-eval CLI — Agent Evaluator 설정 마법사.

사용법:
    agent-eval init      API 키 대화형 설정
    agent-eval check     현재 설정 상태 확인
    agent-eval version   버전 출력
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    __version__ = _pkg_version("agent-evaluator")
except PackageNotFoundError:
    __version__ = "0.5.1"

from agent_evaluator.config import (
    DEFAULTS,
    find_dotenv,
    get_global_config_dir,
    get_global_env_path,
    key_source,
    load_env,
)


# ---------------------------------------------------------------------------
# ANSI 색상 (터미널이 아닌 경우 비활성화)
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Windows: ANSICON 또는 Windows Terminal 환경 확인
        return "ANSICON" in os.environ or "WT_SESSION" in os.environ
    return True


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
# 키 메타데이터
# ---------------------------------------------------------------------------

KEY_DEFS: List[Dict] = [
    {
        "env":      "OPENAI_API_KEY",
        "label":    "OpenAI API Key",
        "required": True,
        "used_for": "LLMHelper, DeepEval, Ragas (GPT 모델 기반 평가)",
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
        "used_for": "ClaudeHelper (Claude 모델 기반 평가)",
        "url":      "https://console.anthropic.com/settings/keys",
        "prefix":   "sk-ant-",
        "companion": [
            ("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001", "사용할 Claude 모델명"),
        ],
    },
    {
        "env":      "LANGSMITH_API_KEY",
        "label":    "LangSmith API Key",
        "required": False,
        "used_for": "LangSmithAdapter — LangChain 트레이싱 연동 (선택)",
        "url":      "https://smith.langchain.com/settings",
        "prefix":   "ls__",
        "companion": [
            ("LANGCHAIN_TRACING_V2", "true",             "LangSmith 트레이싱 활성화"),
            ("LANGCHAIN_PROJECT",    "agent-evaluator",  "LangSmith 프로젝트명"),
        ],
    },
    {
        "env":      "DEEPEVAL_API_KEY",
        "label":    "DeepEval API Key",
        "required": False,
        "used_for": "DeepEvalAdapter — Confident AI 대시보드 연동 (선택, OpenAI 키로도 동작)",
        "url":      "https://app.confident-ai.com/",
        "prefix":   "",
        "companion": [],
    },
]

# 기타 설정값
EXTRA_DEFS: List[Tuple[str, str, str]] = [
    ("AGENT_EVALUATOR_OUTPUT_DIR", "./results", "평가 결과 저장 디렉토리"),
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
    if not val:
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
        ("LANGCHAIN_TRACING_V2",       "LangSmith 트레이싱"),
        ("LANGCHAIN_PROJECT",          "LangSmith 프로젝트"),
    ]:
        default_val = DEFAULTS.get(extra_var, "")
        val = os.getenv(extra_var, default_val)
        print(f"  {extra_var:35s}  {val}")

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
# cmd_serve
# ---------------------------------------------------------------------------

def cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI web dashboard (agent-eval serve)."""
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

    raw_dir     = getattr(args, "results_dir", None)
    host        = getattr(args, "host",  "127.0.0.1")
    port        = getattr(args, "port",  8765)
    watch       = getattr(args, "watch", False)
    open_browser= getattr(args, "open",  False)
    slide       = getattr(args, "slide", False)
    share       = getattr(args, "share", False)
    title       = getattr(args, "title", "Agent Evaluator Dashboard")

    if share:
        host = "0.0.0.0"

    # ── 결과 디렉토리 탐지 ──────────────────────────────────────────────
    # 우선순위:
    #   1. CLI 인수로 명시된 경로 (사용자가 직접 지정)
    #   2. CWD의 ./results (기본값) — JSON 파일이 존재하는 경우에만
    #   3. path_helpers.get_evaluation_results_dir() 자동 탐지
    #      (Dashboard/data/evaluation_results — 예제 스크립트가 저장하는 위치)

    user_specified = raw_dir not in (None, "./results", "results")

    if user_specified:
        results_dir = Path(raw_dir).resolve()
    else:
        # 기본 ./results 에 파일이 있으면 그대로 사용
        default_dir = Path("./results").resolve()
        has_results = default_dir.exists() and any(default_dir.rglob("*.json"))
        if has_results:
            results_dir = default_dir
        else:
            # 자동 탐지: path_helpers 와 동일한 로직 사용
            try:
                from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
                detected = get_evaluation_results_dir()
                if detected.exists() and any(detected.rglob("*.json")):
                    results_dir = detected
                    if not user_specified:
                        print(
                            f"  {_dim(f'ℹ  결과 디렉토리 자동 감지: {results_dir}')}"
                        )
                else:
                    results_dir = default_dir
            except Exception:
                results_dir = default_dir

    if not results_dir.exists():
        results_dir.mkdir(parents=True, exist_ok=True)

    # Banner
    base_url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    json_files = list(results_dir.rglob("*.json"))
    n_files = len([f for f in json_files
                   if not any(p in str(f) for p in
                              ("traces/","audit_logs/","annotations/","transparent_reports/","golden_datasets/"))])
    print()
    print(f"  {B}Agent Evaluator Dashboard{R} v{__version__}")
    print(f"  {'─' * 40}")
    print(f"  📁  Results dir : {results_dir}  ({n_files}개 파일 발견)")
    print(f"  🌐  Dashboard   : {base_url}")
    print(f"  📊  Slides      : {base_url}/slides")
    print(f"  📡  API docs    : {base_url}/api/docs")
    print(f"  🔄  Watch mode  : {'ON' if watch else 'OFF'}")
    if share:
        print(f"  🌍  외부 접근   : {host}:{port} (모든 인터페이스)")
    print()
    print(f"  {_dim('Ctrl+C 로 종료')}")
    print()

    app = create_app(
        results_dir=results_dir,
        title=title,
        watch=watch,
        version=__version__,
    )

    if open_browser:
        import threading
        import webbrowser
        url = f"{base_url}/slides" if slide else base_url

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

from agent_evaluator.config import init_from_app  # noqa: E402 (re-export)


# ---------------------------------------------------------------------------
# argparse entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-eval",
        description="Agent Evaluator CLI — API 키 설정, 환경 확인, 대시보드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  agent-eval init                  대화형 API 키 설정 마법사 실행
  agent-eval check                 현재 설정 상태 출력
  agent-eval serve                 결과 대시보드 웹 서버 실행
  agent-eval serve ./results --open --watch
  agent-eval version               버전 출력
""",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init",    help="대화형 API 키 설정 마법사")
    sub.add_parser("check",   help="현재 설정 상태 확인")
    sub.add_parser("version", help="버전 출력")

    # serve subcommand
    serve_p = sub.add_parser("serve", help="평가 결과 웹 대시보드 실행")
    serve_p.add_argument(
        "results_dir", nargs="?", default="./results",
        help="평가 결과 디렉토리 (기본: ./results)",
    )
    serve_p.add_argument("--host",  default="127.0.0.1", help="바인딩 호스트")
    serve_p.add_argument("--port",  default=8765, type=int, help="포트 번호")
    serve_p.add_argument("--open",  action="store_true", help="브라우저 자동 오픈")
    serve_p.add_argument("--watch", action="store_true", help="파일 변경 감시 (핫 리로드)")
    serve_p.add_argument("--slide", action="store_true", help="시작 화면을 슬라이드로 설정")
    serve_p.add_argument("--share", action="store_true", help="외부 접근 허용 (host=0.0.0.0)")
    serve_p.add_argument("--title", default="Agent Evaluator Dashboard", help="대시보드 제목")

    args = parser.parse_args()

    handlers = {
        "init":    cmd_init,
        "check":   cmd_check,
        "version": cmd_version,
        "serve":   cmd_serve,
    }

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
