"""Amazon KDP 출판 준비 파이프라인 전체 실행.

Usage:
    python run_kdp.py                    # 메타데이터 + EPUB 빌드
    python run_kdp.py --meta-only        # 메타데이터만
    python run_kdp.py --epub-only        # EPUB만
    python run_kdp.py --cover cover.jpg  # 표지 이미지 포함
    python run_kdp.py --check            # 의존성 확인
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

    # pandoc
    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        print(f"  ✅ pandoc: {r.stdout.split(chr(10))[0]}")
    except FileNotFoundError:
        print("  ❌ pandoc: brew install pandoc")
        ok = False

    # anthropic
    try:
        import anthropic
        print(f"  ✅ anthropic: {anthropic.__version__}")
    except ImportError:
        print("  ❌ anthropic: pip install anthropic")
        ok = False

    # ANTHROPIC_API_KEY
    import os
    from dotenv import load_dotenv
    load_dotenv(PIPELINE_DIR.parent.parent / ".env")
    if os.getenv("ANTHROPIC_API_KEY"):
        print("  ✅ ANTHROPIC_API_KEY: 설정됨")
    else:
        print("  ❌ ANTHROPIC_API_KEY: .env에 설정 필요")
        ok = False

    return ok


def print_final_checklist(output_dir: Path):
    kdp_dir = output_dir / "kdp"
    print(f"\n{'═' * 55}")
    print("  KDP 업로드 준비 파일")
    print(f"{'─' * 55}")
    files = {
        "EPUB 파일": list(kdp_dir.glob("*.epub")),
        "KDP 메타데이터": [kdp_dir / "kdp_metadata.md"],
        "HTML 설명": [kdp_dir / "description.html"],
        "키워드 7개": [kdp_dir / "keywords.txt"],
    }
    all_ok = True
    for label, paths in files.items():
        for p in paths:
            exists = p.exists()
            icon = "✅" if exists else "❌"
            size = f"  ({p.stat().st_size/1024:.0f} KB)" if exists else " (없음)"
            print(f"  {icon} {label}: {p.name}{size}")
            if not exists:
                all_ok = False

    print(f"{'─' * 55}")
    if all_ok:
        print("  모든 파일 준비 완료. kdp.amazon.com에서 업로드하세요.")
    else:
        print("  일부 파일 누락. 위 오류를 확인하세요.")
    print(f"{'═' * 55}\n")

    print("  다음 단계:")
    print("  1. Publishing/output/kdp/kdp_metadata.md 검토·수정")
    print("  2. 표지 이미지 제작 (2560×1600px, JPG)")
    print("  3. python build_epub.py --cover cover.jpg  (표지 포함 재빌드)")
    print("  4. kdp.amazon.com 로그인 → Bookshelf → + Kindle eBook")


def main():
    parser = argparse.ArgumentParser(description="Amazon KDP 출판 준비 파이프라인")
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
    print("  Amazon KDP 출판 준비 파이프라인")
    print(f"{'█' * 55}")

    force_arg = ["--force"] if args.force else []

    # Step 1: KDP 메타데이터
    if not args.epub_only:
        print("\n[Step 1] KDP 메타데이터 생성")
        ok = run_script("generate_kdp_metadata.py", force_arg)
        if not ok:
            print("[FAIL] 메타데이터 생성 실패.")
            sys.exit(1)

    # Step 2: EPUB 빌드
    if not args.meta_only:
        print("\n[Step 2] EPUB 빌드")
        epub_args = force_arg.copy()
        if args.cover:
            epub_args += ["--cover", str(args.cover)]
        ok = run_script("build_epub.py", epub_args)
        if not ok:
            print("[FAIL] EPUB 빌드 실패.")
            sys.exit(1)

    print_final_checklist(OUTPUT_DIR)


if __name__ == "__main__":
    main()
