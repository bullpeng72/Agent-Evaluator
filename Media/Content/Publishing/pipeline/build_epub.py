"""Book/ 챕터 Markdown → EPUB 빌드 (pandoc 기반).

필요 도구:
    brew install pandoc

Usage:
    python build_epub.py                   # 부크크용 EPUB 빌드
    python build_epub.py --cover cover.jpg # 표지 이미지 지정
    python build_epub.py --check           # pandoc 설치 확인
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from config import (
    AUTHOR_NAME, BOOK_DIR, BOOK_SUBTITLE, BOOK_TITLE,
    CHAPTER_ORDER, OUTPUT_DIR,
)

# ── 출력 경로 ──────────────────────────────────────────────────────────────────
BOOKK_EPUB = OUTPUT_DIR / "bookk" / f"{BOOK_TITLE.replace(' ', '_')}_bookk.epub"

# ── pandoc 공통 메타데이터 ────────────────────────────────────────────────────
PANDOC_METADATA = """\
---
title: "{title}"
subtitle: "{subtitle}"
author: "{author}"
language: ko
rights: "Copyright © 2026 {author}. All rights reserved."
description: "AI 에이전트를 프로덕션에 배포할 준비가 됐는지 7개 Gate로 판정하는 실전 평가 시스템"
publisher: "Self-Published"
date: "2026"
...
"""

# ── KDP CSS — 전통적 도서 레이아웃 ───────────────────────────────────────────
CSS_KDP = """\
body {
    font-family: 'Noto Serif KR', 'KoPubWorldBatang', serif;
    line-height: 1.8;
    font-size: 1em;
    margin: 1em;
}
h1, h2, h3 {
    font-family: 'Noto Sans KR', 'KoPubWorldDotum', sans-serif;
    margin-top: 2em;
}
code, pre {
    font-family: 'D2Coding', 'Source Code Pro', monospace;
    font-size: 0.85em;
    background: #f5f5f5;
    padding: 0.2em 0.4em;
    border-radius: 3px;
}
pre { padding: 1em; overflow-x: auto; }
blockquote {
    border-left: 4px solid #e63946;
    margin-left: 0; padding-left: 1em; color: #555;
}
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 0.5em; text-align: left; }
th { background: #f0f0f0; }
"""

# ── 리디북스 CSS — 리디 뷰어 최적화 ─────────────────────────────────────────
# 리디북스 뷰어는 독자가 폰트/크기를 조절하므로 em 단위 유지.
# KoPub 폰트를 1순위로, 시스템 기본 한국어 폰트를 fallback으로 사용.
CSS_RIDI = """\
@charset "UTF-8";
body {
    font-family: 'KoPubWorldBatang', 'KoPub바탕체', 'Noto Serif KR',
                 'Apple SD Gothic Neo', serif;
    line-height: 1.9;
    font-size: 1em;
    margin: 0.5em 1em;
    word-break: keep-all;
    overflow-wrap: break-word;
}
h1 {
    font-family: 'KoPubWorldDotum', 'KoPub돋움체', 'Noto Sans KR', sans-serif;
    font-size: 1.6em;
    margin-top: 2em;
    page-break-before: always;
}
h2 {
    font-family: 'KoPubWorldDotum', 'KoPub돋움체', 'Noto Sans KR', sans-serif;
    font-size: 1.3em;
    margin-top: 1.8em;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.2em;
}
h3 {
    font-family: 'KoPubWorldDotum', 'KoPub돋움체', 'Noto Sans KR', sans-serif;
    font-size: 1.1em;
    margin-top: 1.5em;
}
p { margin: 0.6em 0; text-indent: 1em; }
h1 + p, h2 + p, h3 + p { text-indent: 0; }
code {
    font-family: 'D2Coding', 'Courier New', monospace;
    font-size: 0.88em;
    background: #f8f8f8;
    padding: 0.15em 0.35em;
    border-radius: 2px;
}
pre {
    font-family: 'D2Coding', 'Courier New', monospace;
    font-size: 0.82em;
    background: #f8f8f8;
    padding: 0.8em 1em;
    overflow-x: auto;
    border-left: 3px solid #ddd;
    margin: 1em 0;
}
blockquote {
    border-left: 3px solid #e63946;
    margin: 1em 0;
    padding: 0.5em 1em;
    background: #fff8f8;
    color: #444;
}
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }
th, td { border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left; }
th { background: #f0f0f0; font-weight: bold; }
"""


def check_pandoc() -> bool:
    try:
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        print(f"  pandoc: {result.stdout.split(chr(10))[0]}")
        return True
    except FileNotFoundError:
        print("  [ERROR] pandoc 미설치. brew install pandoc 실행 후 재시도.")
        return False


def collect_chapters() -> list[Path]:
    chapters, missing = [], []
    for rel_path in CHAPTER_ORDER:
        full_path = BOOK_DIR / rel_path
        if full_path.exists():
            chapters.append(full_path)
        else:
            missing.append(rel_path)
    if missing:
        print(f"  [WARN] {len(missing)}개 파일 없음 (건너뜀):")
        for m in missing[:5]:
            print(f"    - {m}")
    return chapters


def write_temp_files(tmp_dir: Path, css: str) -> tuple[Path, Path]:
    meta_path = tmp_dir / "metadata.yaml"
    css_path = tmp_dir / "epub.css"
    meta_path.write_text(
        PANDOC_METADATA.format(title=BOOK_TITLE, subtitle=BOOK_SUBTITLE, author=AUTHOR_NAME),
        encoding="utf-8",
    )
    css_path.write_text(css, encoding="utf-8")
    return meta_path, css_path


def build_epub(output_path: Path, css: str, cover_image: Path | None = None) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chapters = collect_chapters()
    if not chapters:
        print("  [ERROR] 빌드할 챕터 파일 없음.")
        return False

    print(f"  총 {len(chapters)}개 챕터 → {output_path.name}")

    with tempfile.TemporaryDirectory() as tmp:
        meta_path, css_path = write_temp_files(Path(tmp), css)

        cmd = [
            "pandoc",
            "--from=markdown+smart",
            "--to=epub3",
            f"--metadata-file={meta_path}",
            f"--css={css_path}",
            "--toc", "--toc-depth=2",
            "--epub-chapter-level=1",
            f"--output={output_path}",
        ]
        if cover_image and cover_image.exists():
            cmd.append(f"--epub-cover-image={cover_image}")
            print(f"  표지: {cover_image.name}")

        cmd += [str(p) for p in chapters]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [ERROR] pandoc 오류:\n{result.stderr[:500]}")
            return False

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"  완료: {output_path}  ({size_mb:.1f} MB)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Book Markdown → 부크크 EPUB 빌드")
    parser.add_argument("--cover", type=Path, help="표지 이미지 경로 (JPG, 1600×2400px)")
    parser.add_argument("--check", action="store_true", help="pandoc 설치 확인만")
    args = parser.parse_args()

    print(f"\n[EPUB 빌드] {BOOK_TITLE}")

    if not check_pandoc():
        sys.exit(1)

    if args.check:
        print("  pandoc 설치 확인 완료.")
        return

    print("\n  -- 부크크 EPUB --")
    ok = build_epub(BOOKK_EPUB, CSS_KDP, args.cover)

    if not ok:
        sys.exit(1)

    print("\n  다음 단계:")
    print(f"  [부크크] bookk.co.kr → 책 만들기 → 전자책 → EPUB 업로드")


if __name__ == "__main__":
    main()
