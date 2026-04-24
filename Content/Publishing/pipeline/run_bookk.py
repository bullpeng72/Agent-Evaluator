"""부크크 출판 준비 파이프라인.

Usage:
    python run_bookk.py                      # 메타데이터 + PDF + EPUB 빌드
    python run_bookk.py --meta-only          # 메타데이터만
    python run_bookk.py --pdf-only           # 종이책 PDF만
    python run_bookk.py --epub-only          # 전자책 EPUB만
    python run_bookk.py --size b5            # B5 판형 (기본: A5)
    python run_bookk.py --cover cover.jpg
    python run_bookk.py --check              # 의존성 확인
"""
import argparse
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent


def run_script(script: str, extra_args: list[str]) -> bool:
    cmd = [sys.executable, str(PIPELINE_DIR / script)] + extra_args
    return subprocess.run(cmd).returncode == 0


def check_deps():
    print("\n[의존성 확인]")
    ok = True

    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        print(f"  ✅ pandoc: {r.stdout.split(chr(10))[0]}")
    except FileNotFoundError:
        print("  ❌ pandoc: brew install pandoc")
        ok = False

    try:
        import weasyprint
        print(f"  ✅ weasyprint: {weasyprint.__version__}")
    except ImportError:
        print("  ❌ weasyprint: pip install weasyprint")
        ok = False

    try:
        import anthropic
        print(f"  ✅ anthropic: {anthropic.__version__}")
    except ImportError:
        print("  ❌ anthropic: pip install anthropic")
        ok = False

    import os
    from dotenv import load_dotenv
    load_dotenv(PIPELINE_DIR.parent.parent.parent / ".env")
    if os.getenv("ANTHROPIC_API_KEY"):
        print("  ✅ ANTHROPIC_API_KEY: 설정됨")
    else:
        print("  ❌ ANTHROPIC_API_KEY: .env에 설정 필요")
        ok = False

    return ok


def print_final_checklist(output_dir: Path):
    bookk_dir = output_dir / "bookk"
    print(f"\n{'═' * 58}")
    print("  부크크 업로드 준비 파일")
    print(f"{'─' * 58}")

    from config import BOOK_TITLE
    pdf_name = f"{BOOK_TITLE.replace(' ', '_')}_bookk.pdf"
    epub_name = f"{BOOK_TITLE.replace(' ', '_')}_kdp.epub"  # 전자책은 KDP EPUB 재사용

    files = {
        "종이책 PDF": [bookk_dir / pdf_name],
        "부크크 메타데이터": [bookk_dir / "bookk_metadata.md"],
        "책 소개 텍스트": [bookk_dir / "description.txt"],
        "전자책 EPUB": [output_dir / "kdp" / epub_name],
    }
    all_ok = True
    for label, paths in files.items():
        for p in paths:
            exists = p.exists()
            icon = "✅" if exists else "❌"
            size = f"  ({p.stat().st_size / 1024:.0f} KB)" if exists else " (없음)"
            print(f"  {icon} {label}: {p.name}{size}")
            if not exists:
                all_ok = False

    print(f"{'─' * 58}")
    if all_ok:
        print("  모든 파일 준비 완료.")
    else:
        print("  일부 파일 누락. 위 오류를 확인하세요.")
    print(f"{'═' * 58}\n")

    print("  다음 단계:")
    print("  1. Publishing/output/bookk/bookk_metadata.md 검토")
    print("  2. 표지 이미지 준비")
    print("     종이책: 1968×2953px (300DPI, CMYK 권장)")
    print("     전자책: 1400×2000px")
    print("  3. bookk.co.kr → 책 만들기 → 종이책 / 전자책 각각 등록")
    print("  4. 유통 채널 선택: 교보문고 + 예스24 + 알라딘 체크")
    print("  5. ISBN 발급 신청 (부크크 무료 제공)")


def main():
    parser = argparse.ArgumentParser(description="부크크 출판 준비 파이프라인")
    parser.add_argument("--meta-only", action="store_true", help="메타데이터만 생성")
    parser.add_argument("--pdf-only", action="store_true", help="종이책 PDF만 빌드")
    parser.add_argument("--epub-only", action="store_true", help="전자책 EPUB만 빌드")
    parser.add_argument("--size", choices=["a5", "b5", "a4"], default=None,
                        help="종이책 판형 (기본값: config.py BOOKK_PAPER_SIZE)")
    parser.add_argument("--cover", type=Path, help="표지 이미지 경로")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true", help="의존성 확인만")
    args = parser.parse_args()

    if args.check:
        check_deps()
        return

    from config import OUTPUT_DIR

    print(f"\n{'█' * 58}")
    print("  부크크 출판 준비 파이프라인")
    print(f"{'█' * 58}")

    force_arg = ["--force"] if args.force else []
    build_pdf = not args.epub_only and not args.meta_only
    build_epub = not args.pdf_only and not args.meta_only
    build_meta = not args.pdf_only and not args.epub_only

    if build_meta:
        print("\n[Step 1] 부크크 메타데이터 생성")
        if not run_script("generate_bookk_metadata.py", force_arg):
            print("[FAIL] 메타데이터 생성 실패.")
            sys.exit(1)

    if build_pdf:
        print("\n[Step 2] 종이책 PDF 빌드 (부크크)")
        pdf_args = force_arg.copy()
        if args.size:
            pdf_args += ["--size", args.size]
        if args.cover:
            pdf_args += ["--cover", str(args.cover)]
        if not run_script("build_pdf_bookk.py", pdf_args):
            print("[FAIL] PDF 빌드 실패.")
            sys.exit(1)

    if build_epub:
        print("\n[Step 3] 전자책 EPUB 빌드 (KDP 포맷 재사용)")
        epub_args = ["--target", "kdp"] + force_arg
        if args.cover:
            epub_args += ["--cover", str(args.cover)]
        if not run_script("build_epub.py", epub_args):
            print("[FAIL] EPUB 빌드 실패.")
            sys.exit(1)

    print_final_checklist(OUTPUT_DIR)


if __name__ == "__main__":
    main()
