"""Step 1: 책 챕터 Markdown → YouTube 나레이션 스크립트.

Usage:
    python chapter_to_narration.py S2E2
    python chapter_to_narration.py S6E3 --force   # 기존 파일 덮어쓰기
"""
import argparse
import json
import sys
from pathlib import Path

from config import (
    BOOK_DIR, CLAUDE_MODEL,
    EPISODE_MAP_PATH, KOREAN_CHARS_PER_MINUTE, OUTPUT_DIR,
)
from llm import call_claude

SYSTEM_PROMPT = """당신은 기술 YouTube 채널의 나레이션 작가입니다.
AI 에이전트 평가 전문 서적의 챕터를 YouTube 영상 나레이션 스크립트로 변환합니다.

규칙:
- 구어체 한국어. 딱딱한 강의체 금지.
- 청중은 Python 개발자. 배경 지식 있음.
- 각 섹션 앞에 [SLIDE: 제목] 또는 [CODE: 설명] 마커로 화면 전환 지시.
- [PAUSE] 마커: 시청자가 내용을 소화할 시간이 필요한 지점.
- 오프닝 30초: 핵심 질문 또는 문제 제기로 시작.
- 마무리 30초: 핵심 요약 3줄 + 다음 편 예고.
- 코드 블록은 나레이션에 포함하지 않음 — [CODE: 파일명/설명]으로 대체.
- 목표 분량: {target_minutes}분 (약 {target_chars}자)."""

USER_PROMPT = """다음 책 챕터를 YouTube 나레이션 스크립트로 변환하세요.

에피소드 정보:
- ID: {episode_id}
- 제목: {title}
- 화면 유형: {screen}
- 목표 길이: {target_minutes}분 (약 {target_chars}자)
- 핵심 훅: {hook}
- 검색 키워드: {keywords}

챕터 내용:
---
{chapter_content}
---

아래 형식을 정확히 따라 스크립트를 작성하세요.
괄호 (…) 안 지시문은 실제 나레이션으로 교체하고, ## 헤더·마커 형식은 그대로 유지하세요.
## 헤더는 반드시 ## [태그] 형식을 사용하세요 (## 섹션1:, ## 🎬 등 다른 형식 금지).

---출력 형식---
# {episode_id} — {title}

**예상 길이**: {target_minutes}분
**화면 유형**: {screen}
**검색 키워드**: {keywords}

---

## [INTRO] 오프닝 (30초)

[SLIDE: (슬라이드 제목)]

(오프닝 나레이션: 핵심 질문 또는 문제 제기. 훅 "{hook}" 활용)

[PAUSE]

---

## [MAIN1] (첫 번째 섹션 제목)

[SLIDE: (슬라이드 제목)]

(나레이션 텍스트)

[PAUSE]

---

## [MAIN2] (두 번째 섹션 제목)

[SLIDE: (슬라이드 제목)]

(나레이션 텍스트)

[CODE: (코드 파일명 — 코드 내용 설명)]

(추가 나레이션)

[PAUSE]

---

(필요한 만큼 ## [MAINn] 섹션을 추가하세요)

---

## [OUTRO] 마무리 (30초)

[SLIDE: 핵심 정리 + 다음 편 예고]

첫째, (핵심 요약 1문장)
둘째, (핵심 요약 2문장)
셋째, (핵심 요약 3문장)

(다음 편 예고 1문장)
---출력 형식 끝---
"""


def load_episode(episode_id: str) -> dict:
    data = json.loads(EPISODE_MAP_PATH.read_text(encoding="utf-8"))
    ep = data["episodes"].get(episode_id)
    if not ep:
        print(f"[ERROR] 에피소드 '{episode_id}'를 episode_map.json에서 찾을 수 없습니다.")
        available = list(data["episodes"].keys())
        print(f"사용 가능한 에피소드: {', '.join(available[:10])} ...")
        sys.exit(1)
    ep["id"] = episode_id
    return ep


def load_chapter(chapter_file: str) -> str:
    path = BOOK_DIR / chapter_file
    if not path.exists():
        print(f"[ERROR] 챕터 파일 없음: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def generate_narration(episode: dict, chapter_content: str) -> str:
    target_chars = episode["target_minutes"] * KOREAN_CHARS_PER_MINUTE
    keywords_str = ", ".join(episode.get("search_keywords", []))

    system = SYSTEM_PROMPT.format(
        target_minutes=episode["target_minutes"],
        target_chars=target_chars,
    )
    user = USER_PROMPT.format(
        episode_id=episode["id"],
        title=episode["title"],
        screen=episode["screen"],
        target_minutes=episode["target_minutes"],
        target_chars=target_chars,
        hook=episode.get("hook", ""),
        keywords=keywords_str,
        chapter_content=chapter_content[:12000],  # 토큰 절약: 앞부분 우선
    )

    print(f"  Claude 호출 중 (모델: {CLAUDE_MODEL})...")
    return call_claude(system, user, model=CLAUDE_MODEL, max_tokens=4096)


def save_narration(episode_id: str, content: str) -> Path:
    out_dir = OUTPUT_DIR / episode_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "narration.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="챕터 → 나레이션 스크립트 생성")
    parser.add_argument("episode_id", help="에피소드 ID (예: S2E2, F1)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    out_path = OUTPUT_DIR / episode_id / "narration.md"

    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} 이미 존재. --force로 덮어쓰기.")
        return str(out_path)

    print(f"\n[Step 1] 챕터 → 나레이션: {episode_id}")
    episode = load_episode(episode_id)
    print(f"  챕터: {episode['chapter_file']}")

    chapter_content = load_chapter(episode["chapter_file"])
    print(f"  챕터 크기: {len(chapter_content):,}자")

    narration = generate_narration(episode, chapter_content)
    out_path = save_narration(episode_id, narration)

    char_count = len(narration)
    est_minutes = char_count / KOREAN_CHARS_PER_MINUTE
    print(f"  완료: {out_path}")
    print(f"  생성 분량: {char_count:,}자 (약 {est_minutes:.1f}분 예상)")
    return str(out_path)


if __name__ == "__main__":
    main()
