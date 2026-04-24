"""파이프라인 전역 설정 — 환경변수·경로·API 키."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# ── 디렉토리 경로 ─────────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent
YOUTUBE_DIR = PIPELINE_DIR.parent
PROJECT_ROOT = YOUTUBE_DIR.parent.parent
BOOK_DIR = PROJECT_ROOT / "Book"
OUTPUT_DIR = YOUTUBE_DIR / "output"
EPISODE_MAP_PATH = YOUTUBE_DIR / "episode_map.json"

# ── Claude API ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── TTS 공급자 설정 ───────────────────────────────────────────────────────────
# "elevenlabs" | "clova" | "none" (음성 생성 건너뜀)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# ElevenLabs Voice ID — Typecast 대신 사용할 경우 설정
# 기본값: Rachel (영어). 한국어는 ElevenLabs 한국어 지원 보이스 ID로 교체
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

# Naver CLOVA Voice
CLOVA_CLIENT_ID = os.getenv("CLOVA_CLIENT_ID", "")
CLOVA_CLIENT_SECRET = os.getenv("CLOVA_CLIENT_SECRET", "")
# CLOVA 화자 ID — 한국어 기본값: "nara" (여성) / "nminsang" (남성)
CLOVA_SPEAKER = os.getenv("CLOVA_SPEAKER", "nara")
CLOVA_SPEED = int(os.getenv("CLOVA_SPEED", "0"))   # -5(빠름) ~ 5(느림)
CLOVA_PITCH = int(os.getenv("CLOVA_PITCH", "0"))

# ── 나레이션 생성 설정 ────────────────────────────────────────────────────────
# 한국어 평균 발화 속도: 분당 약 350자
KOREAN_CHARS_PER_MINUTE = 350
