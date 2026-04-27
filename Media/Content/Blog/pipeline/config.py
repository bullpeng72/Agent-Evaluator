"""블로그 파이프라인 설정."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

PIPELINE_DIR = Path(__file__).parent
BLOG_DIR = PIPELINE_DIR.parent
PROJECT_ROOT = BLOG_DIR.parent.parent.parent
BOOK_DIR = PROJECT_ROOT / "Media" / "Book"
OUTPUT_DIR = BLOG_DIR / "output"
POST_MAP_PATH = BLOG_DIR / "post_map.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

TARGET_PLATFORM = "velog"

# 블로그 시리즈 기본 정보
SERIES_NAME = "AI 에이전트 Harness Engineering 실무 가이드"
GITHUB_URL = "https://github.com/bullpeng72/Agent-Evaluator"
PYPI_URL = "https://pypi.org/project/agent-evaluator/"

# 한국어 평균 독서 속도: 분당 약 500자
KOREAN_READ_SPEED = 500
