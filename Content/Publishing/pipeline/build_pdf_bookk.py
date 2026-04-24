"""Book/ 챕터 Markdown → PDF 빌드 (부크크 종이책용, pandoc + weasyprint).

부크크 종이책 규격:
  - 판형: A5 (148×210mm) 기본, B5 (182×257mm) 선택 가능
  - 본문 폰트: 10pt 권장
  - 내지 여백: 상하 20mm, 좌우 외측 15mm / 내측 18mm (제본 여유)
  - 최소 쪽수: 40쪽, 최대 쪽수: 700쪽
  - 허용 파일: PDF (PDF/X-1a 권장)

필요 도구:
    brew install pandoc
    pip install weasyprint                   # HTML → PDF 변환 엔진
    # 또는: pip install "weasyprint>=60.0"

    # 한국어 폰트 (macOS 시스템 폰트 자동 사용)
    # Linux 환경: apt install fonts-noto-cjk

Usage:
    python build_pdf_bookk.py                # PDF 빌드 (A5 기본)
    python build_pdf_bookk.py --size b5      # B5 판형
    python build_pdf_bookk.py --cover cover.jpg
    python build_pdf_bookk.py --check        # 의존성 확인
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from config import (
    AUTHOR_NAME, BOOK_DIR, BOOK_SUBTITLE, BOOK_TITLE,
    BOOKK_FONT_SIZE_PT, BOOKK_PAPER_SIZE, CHAPTER_ORDER, OUTPUT_DIR,
)

PDF_OUTPUT = OUTPUT_DIR / "bookk" / f"{BOOK_TITLE.replace(' ', '_')}_bookk.pdf"

# 판형별 페이지 크기 정의 (CSS)
PAGE_SIZES = {
    "a5":  "148mm 210mm",
    "b5":  "182mm 257mm",
    "a4":  "210mm 297mm",
}

# 판형별 여백 (내측 제본 여유 포함)
MARGINS = {
    "a5":  "top:20mm; bottom:20mm; inside:18mm; outside:15mm",
    "b5":  "top:22mm; bottom:22mm; inside:20mm; outside:17mm",
    "a4":  "top:25mm; bottom:25mm; inside:22mm; outside:20mm",
}


def make_css(paper_size: str) -> str:
    size = PAGE_SIZES.get(paper_size, PAGE_SIZES["a5"])
    margin_str = MARGINS.get(paper_size, MARGINS["a5"])
    margins = dict(m.split(":") for m in margin_str.split("; "))
    font_pt = BOOKK_FONT_SIZE_PT

    return f"""\
@charset "UTF-8";
@page {{
    size: {size};
    margin-top: {margins['top']};
    margin-bottom: {margins['bottom']};
    margin-left: {margins['outside']};
    margin-right: {margins['outside']};
    @bottom-center {{
        content: counter(page);
        font-size: 9pt;
        font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
        color: #666;
    }}
}}
@page :left  {{ margin-left: {margins['inside']}; margin-right: {margins['outside']}; }}
@page :right {{ margin-left: {margins['outside']}; margin-right: {margins['inside']}; }}

body {{
    font-family: 'Noto Serif KR', 'KoPubWorldBatang', 'Apple SD Gothic Neo', serif;
    font-size: {font_pt}pt;
    line-height: 1.85;
    color: #1a1a1a;
    word-break: keep-all;
    overflow-wrap: break-word;
}}
h1 {{
    font-family: 'Noto Sans KR', 'KoPubWorldDotum', sans-serif;
    font-size: {font_pt + 8}pt;
    font-weight: 700;
    page-break-before: always;
    margin-top: 0;
    margin-bottom: 1.5em;
    padding-bottom: 0.4em;
    border-bottom: 2px solid #1a1a1a;
}}
h2 {{
    font-family: 'Noto Sans KR', 'KoPubWorldDotum', sans-serif;
    font-size: {font_pt + 4}pt;
    font-weight: 700;
    margin-top: 2em;
    margin-bottom: 0.8em;
}}
h3 {{
    font-family: 'Noto Sans KR', 'KoPubWorldDotum', sans-serif;
    font-size: {font_pt + 2}pt;
    font-weight: 600;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}}
h4 {{
    font-size: {font_pt + 1}pt;
    font-weight: 600;
    margin-top: 1.2em;
}}
p {{
    margin: 0.5em 0;
    text-indent: 1em;
}}
h1 + p, h2 + p, h3 + p, h4 + p, li p {{ text-indent: 0; }}
code {{
    font-family: 'D2Coding', 'Courier New', monospace;
    font-size: {font_pt - 1}pt;
    background: #f5f5f5;
    padding: 0.1em 0.3em;
    border-radius: 2px;
}}
pre {{
    font-family: 'D2Coding', 'Courier New', monospace;
    font-size: {font_pt - 2}pt;
    background: #f5f5f5;
    border-left: 3px solid #888;
    padding: 0.8em 1em;
    margin: 1em 0;
    overflow-x: auto;
    page-break-inside: avoid;
    line-height: 1.6;
}}
blockquote {{
    border-left: 4px solid #e63946;
    margin: 1em 0;
    padding: 0.5em 1em;
    background: #fff5f5;
    color: #333;
    font-style: italic;
    page-break-inside: avoid;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: {font_pt - 1}pt;
    page-break-inside: avoid;
}}
th, td {{
    border: 1px solid #bbb;
    padding: 0.4em 0.6em;
    text-align: left;
}}
th {{ background: #eee; font-weight: 700; }}
ul, ol {{ margin: 0.5em 0; padding-left: 1.8em; }}
li {{ margin: 0.3em 0; }}
a {{ color: #1a1a1a; text-decoration: none; }}
img {{ max-width: 100%; height: auto; }}
"""


def check_deps() -> bool:
    ok = True
    # pandoc
    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        print(f"  ✅ pandoc: {r.stdout.split(chr(10))[0]}")
    except FileNotFoundError:
        print("  ❌ pandoc: brew install pandoc")
        ok = False

    # weasyprint
    try:
        import weasyprint
        print(f"  ✅ weasyprint: {weasyprint.__version__}")
    except ImportError:
        print("  ❌ weasyprint: pip install weasyprint")
        ok = False

    return ok


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


def build_html(chapters: list[Path], tmp_dir: Path, cover_image: Path | None) -> Path:
    """pandoc으로 단일 HTML 생성."""
    html_path = tmp_dir / "book.html"

    # 표지 이미지용 HTML 헤더
    cover_html = ""
    if cover_image and cover_image.exists():
        cover_html = f'<div style="page-break-after:always;text-align:center;padding-top:30mm;"><img src="{cover_image.resolve()}" style="max-width:80%;"/></div>\n'

    title_page = f"""\
<div style="page-break-after:always; text-align:center; padding-top:60mm;">
  <h1 style="font-size:22pt; border:none; margin-bottom:0.5em;">{BOOK_TITLE}</h1>
  <p style="font-size:14pt; color:#555; margin-top:0;">{BOOK_SUBTITLE}</p>
  <p style="font-size:12pt; margin-top:4em;">{AUTHOR_NAME}</p>
</div>
"""

    cmd = [
        "pandoc",
        "--from=markdown+smart",
        "--to=html5",
        "--standalone",
        "--toc", "--toc-depth=2",
        f"--output={html_path}",
    ] + [str(p) for p in chapters]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pandoc HTML 변환 실패:\n{result.stderr[:500]}")

    raw = html_path.read_text(encoding="utf-8")
    # <body> 태그 직후에 표지와 속표지 삽입
    raw = raw.replace("<body>", f"<body>\n{cover_html}{title_page}", 1)
    html_path.write_text(raw, encoding="utf-8")
    return html_path


def build_pdf(paper_size: str, cover_image: Path | None = None) -> bool:
    try:
        import weasyprint
    except ImportError:
        print("  [ERROR] weasyprint 미설치. pip install weasyprint")
        return False

    PDF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    chapters = collect_chapters()
    if not chapters:
        print("  [ERROR] 빌드할 챕터 파일 없음.")
        return False

    print(f"  총 {len(chapters)}개 챕터, 판형: {paper_size.upper()} → PDF 빌드 중...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # CSS 파일 저장
        css_path = tmp_dir / "bookk.css"
        css_path.write_text(make_css(paper_size), encoding="utf-8")

        # pandoc → HTML
        print("  [1/2] pandoc → HTML 변환 중...")
        try:
            html_path = build_html(chapters, tmp_dir, cover_image)
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            return False

        # weasyprint → PDF
        print("  [2/2] weasyprint → PDF 변환 중... (수 분 소요)")
        doc = weasyprint.HTML(filename=str(html_path))
        stylesheet = weasyprint.CSS(filename=str(css_path))
        doc.write_pdf(str(PDF_OUTPUT), stylesheets=[stylesheet])

    size_mb = PDF_OUTPUT.stat().st_size / 1024 / 1024
    print(f"\n  PDF 생성 완료: {PDF_OUTPUT}")
    print(f"  파일 크기: {size_mb:.1f} MB")
    print(f"  판형: {paper_size.upper()} ({PAGE_SIZES[paper_size]})")
    print(f"  챕터: {len(chapters)}개")

    print("\n  다음 단계:")
    print("  1. Adobe Acrobat / Preview로 레이아웃 확인")
    print("  2. bookk.co.kr 로그인 → 내 서재 → 책 만들기 → 종이책")
    print("  3. PDF 파일 업로드 → 미리보기 확인 → 출판")
    return True


def main():
    parser = argparse.ArgumentParser(description="Book Markdown → 부크크 종이책 PDF")
    parser.add_argument("--size", choices=["a5", "b5", "a4"], default=BOOKK_PAPER_SIZE,
                        help=f"판형 (기본값: {BOOKK_PAPER_SIZE})")
    parser.add_argument("--cover", type=Path, help="표지 이미지 경로")
    parser.add_argument("--check", action="store_true", help="의존성 확인만")
    args = parser.parse_args()

    print(f"\n[부크크 PDF 빌드] {BOOK_TITLE}")

    if args.check:
        check_deps()
        return

    if not check_deps():
        sys.exit(1)

    ok = build_pdf(args.size, cover_image=args.cover)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
