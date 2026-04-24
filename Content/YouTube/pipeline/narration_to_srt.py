"""Step 4: 나레이션 스크립트 → SRT 자막 파일.

음성 파일 없이도 문자 수 기반으로 타임스탬프를 추정한다.
실제 음성이 있다면 --from-audio 옵션으로 Whisper를 사용한다.

Usage:
    python narration_to_srt.py S2E2
    python narration_to_srt.py S2E2 --from-audio   # Whisper 사용 (정확)
"""
import argparse
import re
import sys
from pathlib import Path

from config import KOREAN_CHARS_PER_MINUTE, OUTPUT_DIR

# 자막 한 줄 최대 문자 수
MAX_CHARS_PER_LINE = 40
# 자막 블록 최대 표시 시간 (초)
MAX_SUBTITLE_DURATION = 5.0
# 자막 블록 최소 표시 시간 (초)
MIN_SUBTITLE_DURATION = 1.5


def format_timestamp(seconds: float) -> str:
    """초 → SRT 타임스탬프 형식 (HH:MM:SS,mmm)."""
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = int(seconds // 60) % 60
    h = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clean_for_subtitle(text: str) -> str:
    """나레이션 텍스트에서 마커·Markdown을 제거하고 발화 텍스트만 남긴다."""
    text = re.sub(r"\[SLIDE:[^\]]*\]|\[CODE:[^\]]*\]|\[PAUSE\]", "", text)
    text = re.sub(r"^\*\*(예상 길이|화면 유형|검색 키워드).*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s+\[?[A-Z]*\]?\s*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def split_into_subtitle_blocks(text: str) -> list[str]:
    """텍스트를 자막 블록으로 분할 (문장 단위, MAX_CHARS_PER_LINE 기준 줄바꿈)."""
    # 문장 분리
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    blocks = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # 긴 문장은 MAX_CHARS_PER_LINE 기준으로 분할
        if len(sentence) <= MAX_CHARS_PER_LINE * 2:
            blocks.append(sentence)
        else:
            # 쉼표·조사 경계에서 분할
            parts = re.split(r"(?<=[,，])\s+|(?<=요)\s+|(?<=다)\s+", sentence)
            current = ""
            for part in parts:
                if len(current) + len(part) <= MAX_CHARS_PER_LINE * 2:
                    current = f"{current} {part}".strip() if current else part
                else:
                    if current:
                        blocks.append(current)
                    current = part
            if current:
                blocks.append(current)

    return [b for b in blocks if b.strip()]


def estimate_duration(text: str) -> float:
    """문자 수 기반으로 발화 시간(초)을 추정."""
    chars = len(text.replace(" ", ""))
    seconds = (chars / KOREAN_CHARS_PER_MINUTE) * 60
    return max(MIN_SUBTITLE_DURATION, min(MAX_SUBTITLE_DURATION, seconds))


def generate_srt_from_text(narration_text: str) -> str:
    """나레이션 텍스트 → SRT 문자열 (타임스탬프 추정)."""
    clean = clean_for_subtitle(narration_text)
    blocks = split_into_subtitle_blocks(clean)

    srt_lines = []
    current_time = 0.0

    for i, block in enumerate(blocks, 1):
        duration = estimate_duration(block)
        end_time = current_time + duration

        # 두 줄 포맷 (MAX_CHARS_PER_LINE 기준)
        if len(block) > MAX_CHARS_PER_LINE:
            mid = len(block) // 2
            # 가장 가까운 공백에서 분리
            split_at = block.rfind(" ", 0, mid) or mid
            line1 = block[:split_at].strip()
            line2 = block[split_at:].strip()
            subtitle_text = f"{line1}\n{line2}"
        else:
            subtitle_text = block

        srt_lines.append(str(i))
        srt_lines.append(f"{format_timestamp(current_time)} --> {format_timestamp(end_time)}")
        srt_lines.append(subtitle_text)
        srt_lines.append("")  # 빈 줄 구분

        current_time = end_time + 0.1  # 0.1초 gap

    return "\n".join(srt_lines)


def generate_srt_from_audio(audio_path: Path) -> str:
    """Whisper로 음성 파일에서 SRT 직접 생성 (정확도 최상)."""
    try:
        import whisper  # type: ignore
    except ImportError:
        print("  [ERROR] whisper 미설치: pip install openai-whisper")
        sys.exit(1)

    print("  Whisper 모델 로딩 (medium)...")
    model = whisper.load_model("medium")
    print("  음성 인식 중...")
    result = model.transcribe(str(audio_path), language="ko", task="transcribe")

    srt_lines = []
    for i, segment in enumerate(result["segments"], 1):
        start = format_timestamp(segment["start"])
        end = format_timestamp(segment["end"])
        text = segment["text"].strip()
        srt_lines.extend([str(i), f"{start} --> {end}", text, ""])

    return "\n".join(srt_lines)


def main():
    parser = argparse.ArgumentParser(description="나레이션 → SRT 자막 생성")
    parser.add_argument("episode_id", help="에피소드 ID (예: S2E2)")
    parser.add_argument("--from-audio", action="store_true",
                        help="Whisper로 음성 파일에서 자막 생성 (정확)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    ep_dir = OUTPUT_DIR / episode_id
    narration_path = ep_dir / "narration.md"
    srt_path = ep_dir / "narration.srt"

    if srt_path.exists() and not args.force:
        print(f"[SKIP] {srt_path} 이미 존재. --force로 덮어쓰기.")
        return str(srt_path)

    print(f"\n[Step 4] 나레이션 → 자막(.srt): {episode_id}")

    if args.from_audio:
        audio_path = ep_dir / "narration.mp3"
        if not audio_path.exists():
            print(f"[ERROR] narration.mp3 없음: {audio_path}")
            sys.exit(1)
        print("  모드: Whisper (음성 기반, 정확)")
        srt_content = generate_srt_from_audio(audio_path)
    else:
        if not narration_path.exists():
            print(f"[ERROR] narration.md 없음: {narration_path}")
            sys.exit(1)
        print("  모드: 문자 수 추정 (빠름, 약간 부정확)")
        narration_text = narration_path.read_text(encoding="utf-8")
        srt_content = generate_srt_from_text(narration_text)

    srt_path.write_text(srt_content, encoding="utf-8")
    block_count = srt_content.count("\n\n")
    print(f"  완료: {srt_path} ({block_count}개 자막 블록)")
    return str(srt_path)


if __name__ == "__main__":
    main()
