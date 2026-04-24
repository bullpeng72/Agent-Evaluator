"""리디북스 출판 준비 파이프라인.

Usage:
    python run_ridibooks.py                  # 메타데이터 + EPUB 빌드
    python run_ridibooks.py --meta-only      # 메타데이터만
    python run_ridibooks.py --epub-only      # EPUB만
    python run_ridibooks.py --cover cover.jpg
    python run_ridibooks.py --check          # 의존성 확인
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
    ridi_dir = output_dir / "ridibooks"
    print(f"\n{'═' * 55}")
    print("  리디북스 업로드 준비 파일")
    print(f"{'─' * 55}")

    from config import BOOK_TITLE
    epub_name = f"{BOOK_TITLE.replace(' ', '_')}_ridi.epub"

    files = {
        "EPUB 파일 (리디 최적화)": [ridi_dir / epub_name],
        "리디북스 메타데이터": [ridi_dir / "ridi_metadata.md"],
        "책 소개 텍스트": [ridi_dir / "description.txt"],
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

    print(f"{'─' * 55}")
    if all_ok:
        print("  모든 파일 준비 완료.")
    else:
        print("  일부 파일 누락. 위 오류를 확인하세요.")
    print(f"{'═' * 55}\n")

    print("  다음 단계:")
    print("  1. Publishing/output/ridibooks/ridi_metadata.md 검토")
    print("  2. 표지 이미지 준비 (1400×2000px 이상, JPG)")
    print("  3. ridibooks.com/publish → 출판사 등록 (미등록 시)")
    print("  4. 도서 등록 → EPUB + 표지 업로드 → 가격 설정 → 심사 신청")


def main():
    parser = argparse.ArgumentParser(description="리디북스 출판 준비 파이프라인")
    parser.add_argument("--meta-only", action="store_true", help="메타데이터만 생성")
    parser.add_argument("--epub-only", action="store_true", help="EPUB만 빌드")
    parser.add_argument("--cover", type=Path, help="표지 이미지 경로")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true", help="의존성 확인만")
    args = parser.parse_args()

    if args.check:
        check_deps()
        return

    from config import OUTPUT_DIR

    print(f"\n{'█' * 55}")
    print("  리디북스 출판 준비 파이프라인")
    print(f"{'█' * 55}")

    force_arg = ["--force"] if args.force else []

    if not args.epub_only:
        print("\n[Step 1] 리디북스 메타데이터 생성")
        if not run_script("generate_ridibooks_metadata.py", force_arg):
            print("[FAIL] 메타데이터 생성 실패.")
            sys.exit(1)

    if not args.meta_only:
        print("\n[Step 2] 리디북스 최적화 EPUB 빌드")
        epub_args = ["--target", "ridi"] + force_arg
        if args.cover:
            epub_args += ["--cover", str(args.cover)]
        if not run_script("build_epub.py", epub_args):
            print("[FAIL] EPUB 빌드 실패.")
            sys.exit(1)

    print_final_checklist(OUTPUT_DIR)


if __name__ == "__main__":
    main()
