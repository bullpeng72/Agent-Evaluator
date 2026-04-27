"""Step 2: 나레이션 스크립트 → Marp 슬라이드 Markdown.

Usage:
    python narration_to_slides.py S2E2
    python narration_to_slides.py S2E2 --pdf   # marp CLI로 PDF 변환까지 수행
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from config import EPISODE_MAP_PATH, OUTPUT_DIR

MARP_HEADER = """\
---
marp: true
theme: default
paginate: true
style: |
  section {{
    font-family: 'Noto Sans KR', sans-serif;
    font-size: 28px;
  }}
  section.lead h1 {{
    font-size: 52px;
  }}
  code {{
    font-size: 22px;
  }}
  .highlight {{
    color: #e63946;
    font-weight: bold;
  }}
---

"""

TITLE_SLIDE = """\
<!-- _class: lead -->

# {title}

### {subtitle}

---

"""

SECTION_SLIDE = """\
## {heading}

{content}

---

"""

SUMMARY_SLIDE = """\
<!-- _class: lead -->

## 핵심 정리

{summary_points}

---

"""


def load_episode_title(episode_id: str) -> tuple[str, str]:
    """episode_map.json에서 (title, season_name) 반환."""
    data = json.loads(EPISODE_MAP_PATH.read_text(encoding="utf-8"))
    ep = data["episodes"].get(episode_id, {})
    title = ep.get("title", episode_id)
    season = ep.get("season", "")
    season_name = f"Season {season}" if isinstance(season, int) else "Special"
    return title, season_name


def parse_narration(narration_text: str) -> list[dict]:
    """나레이션 텍스트를 슬라이드 단위로 파싱.

    ## [TAG] 형식(정석)과 ## 제목 형식(자유 형식) 모두 인식한다.
    INTRO/OUTRO는 헤더 텍스트에 키워드가 포함되면 감지한다.
    """
    slides = []
    lines = narration_text.split("\n")

    current_section = None
    current_content = []
    slide_marker_re = re.compile(r"\[SLIDE:\s*(.+?)\]", re.IGNORECASE)
    # 형식 무관: ## 로 시작하는 모든 헤더 인식
    section_re = re.compile(r"^##\s+(.+)")

    for line in lines:
        # [SLIDE: 제목] 마커 → 이전 섹션 콘텐츠 저장 후 슬라이드 마커 추가
        slide_match = slide_marker_re.search(line)
        if slide_match:
            if current_section and current_content:
                slides.append({"type": "section", "heading": current_section,
                               "content": "\n".join(current_content).strip()})
                current_content = []
            slides.append({"type": "slide_marker",
                           "heading": slide_match.group(1).strip(), "content": ""})
            continue

        # ## heading → 섹션 구분 (## [TAG] 형식·자유 형식 모두 처리)
        section_match = section_re.match(line)
        if section_match:
            if current_section and current_content:
                slides.append({"type": "section", "heading": current_section,
                               "content": "\n".join(current_content).strip()})
                current_content = []

            heading_raw = section_match.group(1).strip()
            upper = heading_raw.upper()

            # [TAG] 접두사 제거: ## [INTRO] 오프닝 → tag=INTRO, heading=오프닝
            tag_match = re.match(r'^\[([A-Z0-9]+)\]\s*(.*)', heading_raw)
            if tag_match:
                heading = tag_match.group(2).strip() or heading_raw
            else:
                heading = heading_raw

            # INTRO/OUTRO 키워드 감지 → build_marp에서 "[INTRO]"/["[OUTRO]" in heading으로 판별
            if "INTRO" in upper:
                current_section = f"[INTRO] {heading}"
            elif "OUTRO" in upper:
                current_section = f"[OUTRO] {heading}"
            else:
                current_section = heading
            continue

        # [CODE: ...] 마커 → 이전 콘텐츠 저장 + 코드 슬라이드 추가
        if line.strip().startswith("[CODE:"):
            code_desc = re.sub(r"\[CODE:\s*(.+?)\]", r"\1", line).strip()
            if current_section and current_content:
                slides.append({"type": "section", "heading": current_section,
                               "content": "\n".join(current_content).strip()})
                current_content = []
            slides.append({"type": "code_transition",
                           "heading": "💻 코드 실습",
                           "content": f"> {code_desc}"})
            # current_section 유지 — [CODE:] 이후 텍스트도 현재 섹션에 귀속
            continue

        # [PAUSE] → 무시 (나레이션 전용 마커)
        if line.strip() == "[PAUSE]":
            continue

        if current_section is not None:
            current_content.append(line)

    if current_section and current_content:
        slides.append({"type": "section", "heading": current_section,
                       "content": "\n".join(current_content).strip()})

    return slides


def narration_to_bullet(text: str, max_lines: int = 6) -> str:
    """긴 나레이션 텍스트를 슬라이드용 bullet points로 변환."""
    sentences = re.split(r"[.。!?]\s+", text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10][:max_lines]
    return "\n".join(f"- {s}" for s in sentences)


def build_marp(episode_id: str, slides_data: list[dict], title: str, season_name: str) -> str:
    """슬라이드 데이터 → Marp Markdown 문자열."""
    parts = [MARP_HEADER]
    parts.append(TITLE_SLIDE.format(title=title, subtitle=f"{season_name} · {episode_id}"))

    summary_bullets = []

    for slide in slides_data:
        heading = slide["heading"]
        content = slide["content"]

        if slide["type"] == "slide_marker":
            # [SLIDE: 제목] 마커 → 강조 슬라이드
            parts.append(SECTION_SLIDE.format(
                heading=heading,
                content=narration_to_bullet(content) if content else "",
            ))
        elif slide["type"] == "code_transition":
            parts.append(SECTION_SLIDE.format(heading=heading, content=content))
        elif "[INTRO]" in heading:
            # 오프닝 → 배경 질문 슬라이드
            parts.append(SECTION_SLIDE.format(
                heading="이 영상에서 다루는 것",
                content=narration_to_bullet(content, max_lines=4),
            ))
        elif "[OUTRO]" in heading:
            # 마무리 → 요약 슬라이드
            summary_bullets = narration_to_bullet(content, max_lines=3)
        else:
            bullet_content = narration_to_bullet(content)
            if bullet_content:
                parts.append(SECTION_SLIDE.format(heading=heading, content=bullet_content))
                # 첫 번째 핵심 문장 summary에 수집
                first = content.strip().split("\n")[0][:60]
                if first:
                    summary_bullets_list = getattr(build_marp, "_summary", [])
                    summary_bullets_list.append(first)

    if summary_bullets:
        parts.append(SUMMARY_SLIDE.format(summary_points=summary_bullets))

    return "".join(parts)


def convert_to_pdf(slides_path: Path) -> bool:
    """marp CLI로 PDF 변환. marp 미설치 시 False 반환."""
    try:
        result = subprocess.run(
            ["marp", str(slides_path), "--pdf", "--allow-local-files"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            pdf_path = slides_path.with_suffix(".pdf")
            print(f"  PDF 생성: {pdf_path}")
            return True
        else:
            print(f"  [WARN] marp PDF 변환 실패: {result.stderr[:200]}")
            return False
    except FileNotFoundError:
        print("  [WARN] marp CLI 미설치. `npm i -g @marp-team/marp-cli` 로 설치 후 재실행.")
        return False


def main():
    parser = argparse.ArgumentParser(description="나레이션 → Marp 슬라이드 생성")
    parser.add_argument("episode_id", help="에피소드 ID (예: S2E2)")
    parser.add_argument("--pdf", action="store_true", help="marp CLI로 PDF 변환")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    narration_path = OUTPUT_DIR / episode_id / "narration.md"
    slides_path = OUTPUT_DIR / episode_id / "slides.md"

    if not narration_path.exists():
        print(f"[ERROR] narration.md 없음: {narration_path}")
        print("먼저 chapter_to_narration.py를 실행하세요.")
        sys.exit(1)

    if slides_path.exists() and not args.force:
        print(f"[SKIP] {slides_path} 이미 존재. --force로 덮어쓰기.")
        return str(slides_path)

    print(f"\n[Step 2] 나레이션 → 슬라이드: {episode_id}")
    narration_text = narration_path.read_text(encoding="utf-8")
    title, season_name = load_episode_title(episode_id)

    slides_data = parse_narration(narration_text)
    print(f"  파싱된 슬라이드 단위: {len(slides_data)}개")

    marp_content = build_marp(episode_id, slides_data, title, season_name)
    slides_path.write_text(marp_content, encoding="utf-8")
    print(f"  완료: {slides_path}")

    if args.pdf:
        convert_to_pdf(slides_path)

    return str(slides_path)


if __name__ == "__main__":
    main()
