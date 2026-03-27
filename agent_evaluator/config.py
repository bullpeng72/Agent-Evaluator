"""
Agent Evaluator — configuration & .env discovery.

.env 로드 우선순위 (높음 → 낮음):
  1. 시스템 환경 변수   (항상 최우선, 절대 덮어쓰지 않음)
  2. 명시적으로 지정한 dotenv_path
  3. CWD → 부모 디렉토리 탐색으로 발견된 .env  (호출 앱의 .env)
  4. ~/.agent-evaluator/.env              (전역 폴백)
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# config 모듈 임포트 시점의 시스템 환경 변수 키 스냅샷.
# load_env() 호출 후 os.environ 에 추가된 키는 .env 출처로 판별한다.
_PRE_LOAD_KEYS: frozenset = frozenset(os.environ.keys())


# ---------------------------------------------------------------------------
# .env 탐색 유틸
# ---------------------------------------------------------------------------

def find_dotenv(start: Optional[Path] = None, max_depth: int = 20) -> Optional[Path]:
    """
    start 디렉토리부터 루트까지 올라가며 .env 파일을 찾는다.

    라이브러리를 호출하는 앱의 프로젝트 루트에 있는 .env 를 자동으로
    감지하기 위해 사용한다.

    Args:
        start:     탐색 시작 디렉토리 (기본: CWD)
        max_depth: 최대 탐색 깊이 (무한 루프 방지, 기본 20)
    """
    current = (start or Path.cwd()).resolve()
    for _ in range(max_depth):
        candidate = current / ".env"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:          # 파일시스템 루트 도달
            break
        current = parent
    return None


def get_global_config_dir() -> Path:
    """~/.agent-evaluator/ 디렉토리 경로를 반환한다."""
    return Path.home() / ".agent-evaluator"


def get_global_env_path() -> Path:
    """~/.agent-evaluator/.env 경로를 반환한다."""
    return get_global_config_dir() / ".env"


def load_env(dotenv_path: Optional[Path] = None) -> Optional[Path]:
    """
    우선순위에 따라 .env 를 로드하고 실제로 로드된 경로를 반환한다.

    override=False 이므로 이미 시스템에 설정된 환경 변수는 절대 덮어쓰지 않는다.
    여러 소스를 중첩 로드해도 안전하다.

    Args:
        dotenv_path: 명시적으로 지정할 .env 파일 경로 (선택)

    Returns:
        마지막으로 로드된 .env 경로, 아무것도 없으면 None
    """
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return None

    loaded: Optional[Path] = None

    # 4순위: 전역 폴백
    global_env = get_global_env_path()
    if global_env.is_file():
        _load(global_env, override=False)
        loaded = global_env

    # 3순위: CWD → 상위 디렉토리 탐색
    discovered = find_dotenv()
    if discovered and discovered != global_env:
        _load(discovered, override=False)
        loaded = discovered

    # 2순위: 명시적 경로
    if dotenv_path is not None:
        p = Path(dotenv_path)
        if p.is_file():
            _load(p, override=False)
            loaded = p

    # 1순위: 시스템 환경 변수 — override=False 이므로 이미 적용돼 있음
    return loaded


def key_source(env_var: str) -> str:
    """
    환경 변수의 출처 레이블을 반환한다.

    _PRE_LOAD_KEYS 스냅샷과 비교하므로 load_env() 호출 전에 이 모듈을
    임포트했을 때 정확하게 동작한다.

    Returns:
        "system env" | "loaded .env" | "not set"
    """
    if env_var not in os.environ:
        return "not set"
    if env_var in _PRE_LOAD_KEYS:
        return "system env"
    return "loaded .env"


# ---------------------------------------------------------------------------
# 설정 데이터클래스
# ---------------------------------------------------------------------------

# 기본값 상수 (중복 제거 — Settings, KEY_DEFS, cmd_check 에서 공유)
DEFAULTS: Dict[str, str] = {
    "OPENAI_MODEL":               "gpt-4o-mini",
    "ANTHROPIC_MODEL":            "claude-haiku-4-5-20251001",
    "LANGCHAIN_TRACING_V2":       "false",
    "LANGCHAIN_PROJECT":          "agent-evaluator",
    "AGENT_EVALUATOR_OUTPUT_DIR": "./results",
}


@dataclass
class Settings:
    """
    Agent Evaluator 런타임 설정.

    환경 변수를 읽어 초기화한다.
    load_env() 를 먼저 호출해야 .env 값이 반영된다.
    """

    # OpenAI
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", DEFAULTS["OPENAI_MODEL"])
    )

    # Anthropic
    anthropic_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.getenv(
            "ANTHROPIC_MODEL", DEFAULTS["ANTHROPIC_MODEL"]
        )
    )

    # LangSmith (LANGCHAIN_API_KEY 도 허용)
    langsmith_api_key: Optional[str] = field(
        default_factory=lambda: (
            os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
        )
    )
    langchain_tracing_v2: bool = field(
        default_factory=lambda: os.getenv(
            "LANGCHAIN_TRACING_V2", DEFAULTS["LANGCHAIN_TRACING_V2"]
        ).lower() == "true"
    )
    langchain_project: str = field(
        default_factory=lambda: os.getenv(
            "LANGCHAIN_PROJECT", DEFAULTS["LANGCHAIN_PROJECT"]
        )
    )

    # 출력 디렉토리
    output_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("AGENT_EVALUATOR_OUTPUT_DIR", DEFAULTS["AGENT_EVALUATOR_OUTPUT_DIR"])
            or DEFAULTS["AGENT_EVALUATOR_OUTPUT_DIR"]
        )
    )

    # ------------------------------------------------------------------ #
    def __post_init__(self) -> None:
        # 빈 문자열 → 기본값으로 교정
        if not str(self.output_dir).strip():
            self.output_dir = Path(DEFAULTS["AGENT_EVALUATOR_OUTPUT_DIR"])
        self.output_dir = Path(self.output_dir)

    def __repr__(self) -> str:
        def mask(s: Optional[str]) -> str:
            if not s:
                return "(not set)"
            return s[:6] + "..." + s[-4:] if len(s) > 10 else "***"

        return (
            f"Settings("
            f"openai_api_key={mask(self.openai_api_key)}, "
            f"anthropic_api_key={mask(self.anthropic_api_key)}, "
            f"langsmith_api_key={mask(self.langsmith_api_key)}, "
            f"openai_model={self.openai_model!r}, "
            f"anthropic_model={self.anthropic_model!r}, "
            f"output_dir={self.output_dir!r})"
        )

    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    def has_langsmith(self) -> bool:
        return bool(self.langsmith_api_key)


# ---------------------------------------------------------------------------
# 싱글턴 (thread-safe)
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None
_settings_lock = threading.Lock()


def get_settings(
    dotenv_path: Optional[Path] = None,
    reload: bool = False,
) -> Settings:
    """
    전역 Settings 인스턴스를 반환한다 (최초 호출 시 .env 로드).

    thread-safe: 멀티스레드 환경에서 중복 초기화를 방지한다.

    Args:
        dotenv_path: 명시적 .env 경로 (선택)
        reload:      True 면 캐시를 무시하고 재초기화
    """
    global _settings
    with _settings_lock:
        if _settings is None or reload:
            load_env(dotenv_path)
            _settings = Settings()
    return _settings


# ---------------------------------------------------------------------------
# 라이브러리 사용자용 헬퍼: init_from_app()
# ---------------------------------------------------------------------------

def init_from_app(
    dotenv_path: Optional[Path] = None,
    required_keys: Optional[List[str]] = None,
    raise_on_missing: bool = False,
) -> Dict[str, Optional[str]]:
    """
    라이브러리를 호출하는 앱에서 programmatic 하게 초기화하는 헬퍼.

    .env 경로를 명시하거나, CWD → 상위 탐색 자동 감지를 사용한다.
    CLI 모듈을 임포트하지 않으므로 import 시 side-effect 없음.

    사용 예:
        from agent_evaluator.config import init_from_app
        env_status = init_from_app(dotenv_path=Path(".env"))

        # 특정 키가 반드시 필요할 때
        init_from_app(
            required_keys=["OPENAI_API_KEY"],
            raise_on_missing=True,
        )

    Args:
        dotenv_path:      명시적 .env 경로 (None 이면 자동 탐색)
        required_keys:    반드시 설정돼야 하는 환경 변수 목록
        raise_on_missing: True 면 누락 필수 키에 대해 EnvironmentError 발생

    Returns:
        {"OPENAI_API_KEY": "sk-...", "ANTHROPIC_API_KEY": None, ...} 형태
    """
    settings = get_settings(dotenv_path=dotenv_path, reload=True)

    status: Dict[str, Optional[str]] = {
        "OPENAI_API_KEY":             settings.openai_api_key,
        "ANTHROPIC_API_KEY":          settings.anthropic_api_key,
        "LANGSMITH_API_KEY":          settings.langsmith_api_key,
        "AGENT_EVALUATOR_OUTPUT_DIR": str(settings.output_dir),
    }

    if required_keys:
        missing = [k for k in required_keys if not status.get(k)]
        if missing:
            msg = (
                f"Agent Evaluator: 다음 환경 변수가 설정되지 않았습니다: "
                f"{', '.join(missing)}\n"
                f"  'agent-eval init' 을 실행하거나 .env 파일을 확인하세요."
            )
            if raise_on_missing:
                raise OSError(msg)
            print(f"\033[33m⚠️  {msg}\033[0m", file=sys.stderr)

    return status
