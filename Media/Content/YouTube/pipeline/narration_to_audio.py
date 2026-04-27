"""Step 3: 나레이션 스크립트 → 음성 파일 (.mp3).

ElevenLabs 또는 Naver CLOVA Voice를 사용한다.
TTS_PROVIDER 환경변수로 공급자를 선택한다.

Usage:
    python narration_to_audio.py S2E2
    python narration_to_audio.py S2E2 --provider clova
"""
import argparse
import re
import sys
import time
from pathlib import Path

import requests

from config import (
    CLOVA_CLIENT_ID, CLOVA_CLIENT_SECRET, CLOVA_PITCH,
    CLOVA_SPEAKER, CLOVA_SPEED, ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL_ID, ELEVENLABS_VOICE_ID, OUTPUT_DIR, TTS_PROVIDER,
)

# ElevenLabs 무료 플랜 문자 제한 (청크 단위)
ELEVENLABS_CHUNK_CHARS = 2500
# CLOVA Voice 최대 문자 수
CLOVA_MAX_CHARS = 5000


def clean_narration(text: str) -> str:
    """나레이션에서 마커·메타 정보를 제거하고 순수 발화 텍스트만 추출."""
    # 메타 헤더 제거 (--- 구분선 앞)
    if "---" in text:
        parts = text.split("---", 1)
        text = parts[1] if len(parts) > 1 else text

    # 마커 제거
    text = re.sub(r"\[SLIDE:[^\]]*\]", "", text)
    text = re.sub(r"\[CODE:[^\]]*\]", "", text)
    text = re.sub(r"\[PAUSE\]", ".\n", text)
    text = re.sub(r"\[INTRO\]|\[OUTRO\]|\[SECTION \d+\]", "", text)

    # Markdown 헤더·구문 제거
    text = re.sub(r"^#{1,6}\s+\[?[A-Z]*\]?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)

    # 메타 정보 줄 제거
    text = re.sub(r"^\*\*(예상 길이|화면 유형|검색 키워드).*$", "", text, flags=re.MULTILINE)

    # 빈 줄 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_chunks(text: str, max_chars: int) -> list[str]:
    """문장 경계를 유지하면서 max_chars 이하 청크로 분할."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current.strip())
    return chunks


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def generate_elevenlabs(text: str, output_path: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        print("[ERROR] ELEVENLABS_API_KEY 환경변수 미설정.")
        return False

    chunks = split_chunks(text, ELEVENLABS_CHUNK_CHARS)
    audio_parts: list[bytes] = []

    for i, chunk in enumerate(chunks, 1):
        print(f"  ElevenLabs 청크 {i}/{len(chunks)} ({len(chunk)}자)...")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": chunk,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  [ERROR] ElevenLabs API 오류 {resp.status_code}: {resp.text[:200]}")
            return False
        audio_parts.append(resp.content)
        if i < len(chunks):
            time.sleep(0.5)  # Rate limit 방지

    combined = b"".join(audio_parts)
    output_path.write_bytes(combined)
    return True


# ── Naver CLOVA Voice ─────────────────────────────────────────────────────────

def generate_clova(text: str, output_path: Path) -> bool:
    if not CLOVA_CLIENT_ID or not CLOVA_CLIENT_SECRET:
        print("[ERROR] CLOVA_CLIENT_ID / CLOVA_CLIENT_SECRET 환경변수 미설정.")
        return False

    chunks = split_chunks(text, CLOVA_MAX_CHARS)
    audio_parts: list[bytes] = []

    for i, chunk in enumerate(chunks, 1):
        print(f"  CLOVA Voice 청크 {i}/{len(chunks)} ({len(chunk)}자)...")
        url = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"
        headers = {
            "X-NCP-APIGW-API-KEY-ID": CLOVA_CLIENT_ID,
            "X-NCP-APIGW-API-KEY": CLOVA_CLIENT_SECRET,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "speaker": CLOVA_SPEAKER,
            "text": chunk,
            "speed": str(CLOVA_SPEED),
            "pitch": str(CLOVA_PITCH),
            "format": "mp3",
        }
        resp = requests.post(url, headers=headers, data=data, timeout=60)
        if resp.status_code != 200:
            print(f"  [ERROR] CLOVA API 오류 {resp.status_code}: {resp.text[:200]}")
            return False
        audio_parts.append(resp.content)
        if i < len(chunks):
            time.sleep(0.3)

    combined = b"".join(audio_parts)
    output_path.write_bytes(combined)
    return True


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="나레이션 → 음성 파일 생성")
    parser.add_argument("episode_id", help="에피소드 ID (예: S2E2)")
    parser.add_argument("--provider", choices=["elevenlabs", "clova"],
                        help="TTS 공급자 (기본값: TTS_PROVIDER 환경변수)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    provider = args.provider or TTS_PROVIDER
    narration_path = OUTPUT_DIR / episode_id / "narration.md"
    audio_path = OUTPUT_DIR / episode_id / "narration.mp3"

    if not narration_path.exists():
        print(f"[ERROR] narration.md 없음: {narration_path}")
        sys.exit(1)

    if audio_path.exists() and not args.force:
        print(f"[SKIP] {audio_path} 이미 존재. --force로 덮어쓰기.")
        return str(audio_path)

    print(f"\n[Step 3] 나레이션 → 음성: {episode_id} (공급자: {provider})")
    narration_text = narration_path.read_text(encoding="utf-8")
    clean_text = clean_narration(narration_text)
    print(f"  정제된 텍스트: {len(clean_text):,}자")

    if provider == "none":
        print("  [SKIP] TTS_PROVIDER=none — 음성 생성 건너뜀.")
        return None

    success = False
    if provider == "elevenlabs":
        success = generate_elevenlabs(clean_text, audio_path)
    elif provider == "clova":
        success = generate_clova(clean_text, audio_path)
    else:
        print(f"[ERROR] 알 수 없는 공급자: {provider}")
        sys.exit(1)

    if success:
        size_kb = audio_path.stat().st_size / 1024
        print(f"  완료: {audio_path} ({size_kb:.0f} KB)")
        return str(audio_path)
    else:
        print("  [ERROR] 음성 생성 실패.")
        sys.exit(1)


if __name__ == "__main__":
    main()
