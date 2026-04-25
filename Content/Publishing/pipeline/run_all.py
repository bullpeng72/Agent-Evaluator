"""세 플랫폼(KDP · 리디북스 · 부크크) 통합 출판 파이프라인.

Usage:
    python run_all.py                        # 세 플랫폼 전체 실행
    python run_all.py --platform kdp         # Amazon KDP만
    python run_all.py --platform ridi        # 리디북스만
    python run_all.py --platform bookk       # 부크크만
    python run_all.py --platform kdp,ridi    # KDP + 리디북스
    python run_all.py --meta-only            # 메타데이터만 (세 플랫폼)
    python run_all.py --epub-only            # EPUB만 (KDP + 리디)
    python run_all.py --cover cover.jpg      # 표지 이미지 공통 지정
    python run_all.py --check                # 의존성 전체 확인
"""
import argparse
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent


def run_script(script: str, extra_args: list[str]) -> bool:
    print(f"    $ python {script} {' '.join(extra_args)}")
    cmd = [sys.executable, str(PIPELINE_DIR / script)] + extra_args
    return subprocess.run(cmd).returncode == 0


def check_all_deps():
    print("\n[전체 의존성 확인]")
    ok = True

    checks = {
        "pandoc": (["pandoc", "--version"], "brew install pandoc"),
        "anthropic": None,
        "weasyprint": None,
    }

    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        print(f"  ✅ pandoc: {r.stdout.split(chr(10))[0]}")
    except FileNotFoundError:
        print("  ❌ pandoc (brew install pandoc)")
        ok = False

    for pkg, install_hint in [("anthropic", "pip install anthropic"),
                               ("weasyprint", "pip install weasyprint")]:
        try:
            mod = __import__(pkg)
            print(f"  ✅ {pkg}: {mod.__version__}")
        except ImportError:
            print(f"  ❌ {pkg} ({install_hint})")
            ok = False

    import os
    from dotenv import load_dotenv
    load_dotenv(PIPELINE_DIR.parent.parent.parent.parent.parent / ".env")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key and api_key.startswith("sk-ant-") and len(api_key) > 20:
        print("  ✅ ANTHROPIC_API_KEY: 유효한 키 설정됨")
    else:
        import shutil
        if shutil.which("claude"):
            print("  ✅ claude CLI: Claude Code 인증 사용 (API 키 불필요)")
        else:
            print("  ❌ ANTHROPIC_API_KEY 미설정 + claude CLI 없음")
            ok = False

    return ok


def print_summary(output_dir: Path, platforms: list[str]):
    from config import BOOK_TITLE
    slug = BOOK_TITLE.replace(" ", "_")

    print(f"\n{'═' * 62}")
    print("  출판 준비 파일 요약")
    print(f"{'─' * 62}")

    all_files = []

    if "kdp" in platforms:
        all_files += [
            ("KDP", "EPUB", output_dir / "kdp" / f"{slug}_kdp.epub"),
            ("KDP", "메타데이터", output_dir / "kdp" / "kdp_metadata.md"),
            ("KDP", "HTML 설명", output_dir / "kdp" / "description.html"),
            ("KDP", "키워드", output_dir / "kdp" / "keywords.txt"),
        ]
    if "ridi" in platforms:
        all_files += [
            ("리디", "EPUB", output_dir / "ridibooks" / f"{slug}_ridi.epub"),
            ("리디", "메타데이터", output_dir / "ridibooks" / "ridi_metadata.md"),
            ("리디", "책 소개", output_dir / "ridibooks" / "description.txt"),
        ]
    if "bookk" in platforms:
        all_files += [
            ("부크크", "PDF", output_dir / "bookk" / f"{slug}_bookk.pdf"),
            ("부크크", "메타데이터", output_dir / "bookk" / "bookk_metadata.md"),
            ("부크크", "책 소개", output_dir / "bookk" / "description.txt"),
        ]

    for platform, label, path in all_files:
        exists = path.exists()
        icon = "✅" if exists else "❌"
        size = f" ({path.stat().st_size / 1024:.0f} KB)" if exists else " (없음)"
        print(f"  {icon} [{platform}] {label}: {path.name}{size}")

    total_ok = sum(1 for _, _, p in all_files if p.exists())
    total = len(all_files)
    print(f"{'─' * 62}")
    print(f"  {total_ok}/{total}개 파일 준비 완료")
    print(f"{'═' * 62}\n")

    print("  업로드 경로:")
    if "kdp" in platforms:
        print("  [KDP]  kdp.amazon.com → Bookshelf → + Kindle eBook")
    if "ridi" in platforms:
        print("  [리디] ridibooks.com/publish → 도서 등록")
    if "bookk" in platforms:
        print("  [부크크] bookk.co.kr → 책 만들기 → 종이책 / 전자책")


def main():
    parser = argparse.ArgumentParser(description="세 플랫폼 통합 출판 파이프라인")
    parser.add_argument(
        "--platform", default="all",
        help="실행 플랫폼: kdp | ridi | bookk | all | 쉼표로 여러 개 (예: kdp,ridi)",
    )
    parser.add_argument("--meta-only", action="store_true", help="메타데이터만 생성")
    parser.add_argument("--epub-only", action="store_true", help="EPUB만 빌드 (KDP+리디)")
    parser.add_argument("--cover", type=Path, help="표지 이미지 (공통 적용)")
    parser.add_argument("--size", choices=["a5", "b5", "a4"],
                        help="부크크 종이책 판형")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true", help="의존성 확인만")
    args = parser.parse_args()

    if args.check:
        check_all_deps()
        return

    # 플랫폼 파싱
    if args.platform == "all":
        platforms = ["kdp", "ridi", "bookk"]
    else:
        platforms = [p.strip() for p in args.platform.split(",")]
        invalid = [p for p in platforms if p not in ("kdp", "ridi", "bookk")]
        if invalid:
            print(f"[ERROR] 알 수 없는 플랫폼: {invalid}")
            sys.exit(1)

    from config import OUTPUT_DIR

    print(f"\n{'█' * 62}")
    print(f"  통합 출판 파이프라인 — {', '.join(p.upper() for p in platforms)}")
    print(f"{'█' * 62}")

    force_arg = ["--force"] if args.force else []
    cover_arg = ["--cover", str(args.cover)] if args.cover else []
    size_arg = ["--size", args.size] if args.size else []
    failed = []

    # ── Amazon KDP ──────────────────────────────────────────────────────────
    if "kdp" in platforms:
        print(f"\n{'─' * 62}")
        print("  Amazon KDP")
        print(f"{'─' * 62}")

        if not args.epub_only:
            print("\n  [KDP-1] 메타데이터 생성")
            if not run_script("generate_kdp_metadata.py", force_arg):
                failed.append("KDP 메타데이터")

        if not args.meta_only:
            print("\n  [KDP-2] KDP EPUB 빌드")
            epub_args = ["--target", "kdp"] + cover_arg + force_arg
            if not run_script("build_epub.py", epub_args):
                failed.append("KDP EPUB")

    # ── 리디북스 ─────────────────────────────────────────────────────────────
    if "ridi" in platforms:
        print(f"\n{'─' * 62}")
        print("  리디북스")
        print(f"{'─' * 62}")

        if not args.epub_only:
            print("\n  [리디-1] 메타데이터 생성")
            if not run_script("generate_ridibooks_metadata.py", force_arg):
                failed.append("리디 메타데이터")

        if not args.meta_only:
            print("\n  [리디-2] 리디북스 EPUB 빌드")
            epub_args = ["--target", "ridi"] + cover_arg + force_arg
            if not run_script("build_epub.py", epub_args):
                failed.append("리디 EPUB")

    # ── 부크크 ───────────────────────────────────────────────────────────────
    if "bookk" in platforms:
        print(f"\n{'─' * 62}")
        print("  부크크")
        print(f"{'─' * 62}")

        if not args.epub_only:
            print("\n  [부크크-1] 메타데이터 생성")
            if not run_script("generate_bookk_metadata.py", force_arg):
                failed.append("부크크 메타데이터")

        if not args.meta_only and not args.epub_only:
            print("\n  [부크크-2] 종이책 PDF 빌드")
            pdf_args = size_arg + cover_arg + force_arg
            if not run_script("build_pdf_bookk.py", pdf_args):
                failed.append("부크크 PDF")

    if failed:
        print(f"\n[WARN] 일부 단계 실패: {', '.join(failed)}")
        print("  성공한 파일은 정상적으로 사용 가능합니다.")

    print_summary(OUTPUT_DIR, platforms)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
