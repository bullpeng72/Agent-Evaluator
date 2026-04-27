"""Step 5: 나레이션 스크립트 + 에피소드 정보 → YouTube 메타데이터.

생성 항목: 제목, 설명(챕터 타임스탬프 포함), 태그, 해시태그

Usage:
    python generate_metadata.py S2E2
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import CLAUDE_MODEL, EPISODE_MAP_PATH, OUTPUT_DIR
from llm import call_claude

METADATA_PROMPT = """당신은 YouTube 채널 운영 전문가입니다.
다음 기술 영상의 메타데이터를 한국어로 작성하세요.

에피소드 정보:
- ID: {episode_id}
- 제목: {title}
- 예상 길이: {target_minutes}분
- 검색 키워드: {keywords}
- 핵심 훅: {hook}

나레이션 스크립트 (요약):
{narration_summary}

아래 JSON 형식으로 정확히 출력하세요. 다른 텍스트 없이 JSON만:

{{
  "title": "YouTube 제목 (100자 이내, 검색 키워드 포함)",
  "description": "영상 설명 (500자 이상, 아래 구조 포함):\\n\\n[내용 요약 2-3문장]\\n\\n⏱️ 챕터\\n00:00 인트로\\n[챕터 타임스탬프 목록]\\n\\n📦 Agent-Evaluator\\nhttps://github.com/bullpeng72/Agent-Evaluator\\n\\n#태그1 #태그2 #태그3",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5", "태그6", "태그7", "태그8", "태그9", "태그10"],
  "hashtags": "#태그1 #태그2 #태그3 #태그4 #태그5",
  "chapters": [
    {{"time": "00:00", "title": "인트로"}},
    {{"time": "00:30", "title": "섹션 제목"}}
  ]
}}"""


def load_episode(episode_id: str) -> dict:
    data = json.loads(EPISODE_MAP_PATH.read_text(encoding="utf-8"))
    ep = data["episodes"].get(episode_id)
    if not ep:
        print(f"[ERROR] 에피소드 '{episode_id}' 없음.")
        sys.exit(1)
    ep["id"] = episode_id
    return ep


def extract_sections(narration_text: str) -> list[tuple[str, str]]:
    """나레이션에서 섹션 헤더와 첫 문장을 추출."""
    sections = []
    lines = narration_text.split("\n")
    section_re = re.compile(r"^##\s+(?:\[.+?\])?\s*(.+?)(?:\s*\(.+\))?$")
    for line in lines:
        m = section_re.match(line)
        if m:
            sections.append(m.group(1).strip())
    return sections


def estimate_chapter_times(sections: list[str], total_minutes: int) -> list[dict]:
    """섹션별 타임스탬프 추정 (균등 분배)."""
    chapters = [{"time": "00:00", "title": "인트로"}]
    if not sections:
        return chapters

    # 인트로 30초, 아웃트로 30초 제외
    content_seconds = (total_minutes * 60) - 60
    section_duration = content_seconds / max(len(sections), 1)

    current_seconds = 30  # 인트로 30초 후 시작
    for section in sections:
        if "[INTRO]" in section or "[OUTRO]" in section:
            continue
        m = int(current_seconds // 60)
        s = int(current_seconds % 60)
        chapters.append({"time": f"{m:02d}:{s:02d}", "title": section})
        current_seconds += section_duration

    total_m = total_minutes - 1
    chapters.append({"time": f"{total_m:02d}:00", "title": "마무리 및 요약"})
    return chapters


def generate_metadata_with_claude(episode: dict, narration_text: str) -> dict:
    sections = extract_sections(narration_text)
    # 나레이션 요약: 처음 1000자만 전달
    narration_summary = narration_text[:1000].replace("\n", " ")
    keywords_str = ", ".join(episode.get("search_keywords", []))

    prompt = METADATA_PROMPT.format(
        episode_id=episode["id"],
        title=episode["title"],
        target_minutes=episode.get("target_minutes", 10),
        keywords=keywords_str,
        hook=episode.get("hook", ""),
        narration_summary=narration_summary,
    )

    print("  Claude로 메타데이터 생성 중...")
    raw = call_claude(
        system="당신은 YouTube 채널 운영 전문가입니다. 요청된 JSON 형식을 정확히 따르세요.",
        user=prompt,
        model=CLAUDE_MODEL,
        max_tokens=1500,
    ).strip()
    # JSON 추출 (마크다운 코드블록 안에 있을 수 있음)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        print(f"  [WARN] JSON 파싱 실패. 원시 응답 저장.")
        return {"raw": raw}

    try:
        metadata = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON 파싱 오류: {e}")
        return {"raw": raw}

    # 챕터 타임스탬프가 없으면 추정값으로 보완
    if "chapters" not in metadata or not metadata["chapters"]:
        metadata["chapters"] = estimate_chapter_times(
            sections, episode.get("target_minutes", 10)
        )

    return metadata


def format_metadata_file(episode_id: str, metadata: dict) -> str:
    """메타데이터를 YouTube 업로드용 텍스트로 포맷."""
    lines = [
        f"# YouTube 메타데이터 — {episode_id}",
        "",
        "## 제목",
        metadata.get("title", ""),
        "",
        "## 설명",
        metadata.get("description", ""),
        "",
        "## 태그 (쉼표 구분)",
        ", ".join(metadata.get("tags", [])),
        "",
        "## 해시태그",
        metadata.get("hashtags", ""),
        "",
        "## 챕터 타임스탬프",
    ]
    for ch in metadata.get("chapters", []):
        lines.append(f"{ch.get('time', '00:00')} {ch.get('title', '')}")

    if "raw" in metadata:
        lines.extend(["", "## 원시 응답 (참고)", metadata["raw"]])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="YouTube 메타데이터 생성")
    parser.add_argument("episode_id", help="에피소드 ID (예: S2E2)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    ep_dir = OUTPUT_DIR / episode_id
    narration_path = ep_dir / "narration.md"
    metadata_path = ep_dir / "metadata.txt"
    metadata_json_path = ep_dir / "metadata.json"

    if metadata_path.exists() and not args.force:
        print(f"[SKIP] {metadata_path} 이미 존재. --force로 덮어쓰기.")
        return str(metadata_path)

    if not narration_path.exists():
        print(f"[ERROR] narration.md 없음: {narration_path}")
        sys.exit(1)

    print(f"\n[Step 5] YouTube 메타데이터 생성: {episode_id}")
    episode = load_episode(episode_id)
    narration_text = narration_path.read_text(encoding="utf-8")

    metadata = generate_metadata_with_claude(episode, narration_text)

    # JSON 저장
    metadata_json_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 텍스트 포맷 저장
    formatted = format_metadata_file(episode_id, metadata)
    metadata_path.write_text(formatted, encoding="utf-8")

    print(f"  완료: {metadata_path}")
    print(f"  제목: {metadata.get('title', '(생성 실패)')[:60]}")
    return str(metadata_path)


if __name__ == "__main__":
    main()
