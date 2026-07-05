#!/usr/bin/env python3
"""
Agent-Evaluator 도서 편집 UI 실행 스크립트.

lecture-forge 에디터를 기동해 agent-evaluator-book.html 을 브라우저에서
섹션 단위로 편집할 수 있게 한다.

사전 준비:
    pip install -e /path/to/Lecture_forge    # lecture-forge 설치
    python build_book.py                     # 최신 HTML 빌드

사용법:
    python edit_book.py                      # 기본 (포트 5757, 브라우저 자동 오픈)
    python edit_book.py --port 8080          # 포트 변경
    python edit_book.py --no-browser         # 브라우저 자동 오픈 비활성화
    python edit_book.py --out edited.html    # 저장 경로 지정 (기본: book_edited.html)
    python edit_book.py --rebuild            # 편집 전 HTML 재빌드
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

BOOK_DIR  = Path(__file__).parent
BOOK_HTML = BOOK_DIR / "agent-evaluator-book.html"
DEFAULT_OUT = BOOK_DIR / "agent-evaluator-book_edited.html"
DEFAULT_PORT = 5757


def _ensure_lecture_forge_importable() -> bool:
    """lecture_forge 가 importable 하지 않으면 해당 환경의 site-packages 를 sys.path 에 추가한다.

    pipx 격리 venv, conda 환경, 별도 venv 등 현재 인터프리터와 다른 환경에 설치된 경우
    PATH 에는 노출되지만 find_spec 은 실패한다.
    lecture-forge 바이너리와 같은 bin/ 디렉토리의 python 을 찾아
    site-packages 경로를 구한 뒤 sys.path 에 삽입한다.
    """
    if importlib.util.find_spec("lecture_forge") is not None:
        return True

    lf_bin = shutil.which("lecture-forge")
    if not lf_bin:
        return False

    venv_python = Path(os.path.realpath(lf_bin)).parent / "python"
    if not venv_python.exists():
        return False

    result = subprocess.run(
        [str(venv_python), "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False

    site_pkg = result.stdout.strip()
    if site_pkg and site_pkg not in sys.path:
        sys.path.insert(0, site_pkg)

    return importlib.util.find_spec("lecture_forge") is not None


def _check_lecture_forge() -> None:
    if not _ensure_lecture_forge_importable():
        print("❌ lecture-forge 가 설치되지 않았습니다.")
        print()
        print("   설치 방법 (pipx 권장):")
        print("     pipx install lecture-forge")
        print("   또는 개발 버전:")
        print("     pip install -e /path/to/Lecture_forge")
        sys.exit(1)


def _rebuild_html() -> None:
    print("🔨 HTML 재빌드 중 …")
    result = subprocess.run(
        [sys.executable, str(BOOK_DIR / "build_book.py")],
        cwd=str(BOOK_DIR),
    )
    if result.returncode != 0:
        print("❌ 빌드 실패. build_book.py 출력을 확인하세요.")
        sys.exit(1)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent-Evaluator 도서 편집 UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_PORT,
        help=f"서버 포트 (기본값: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--out", "-o",
        type=str,
        default=str(DEFAULT_OUT),
        help=f"편집 결과 저장 경로 (기본값: {DEFAULT_OUT.name})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="브라우저 자동 오픈 비활성화",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="편집 UI 기동 전 build_book.py 실행",
    )
    args = parser.parse_args()

    _check_lecture_forge()

    if args.rebuild:
        _rebuild_html()

    if not BOOK_HTML.exists():
        print(f"❌ HTML 파일이 없습니다: {BOOK_HTML}")
        print("   먼저 빌드하세요:  python build_book.py")
        print("   또는:             python edit_book.py --rebuild")
        sys.exit(1)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path

    print("📖 Agent-Evaluator 도서 편집 UI")
    print(f"   원본  : {BOOK_HTML}")
    print(f"   저장  : {out_path}")
    print(f"   URL   : http://localhost:{args.port}")
    print()
    print("   편집 완료 후 브라우저에서 [저장] 버튼을 누르세요.")
    print("   종료  : Ctrl+C\n")

    from lecture_forge.editor.server import run_editor
    run_editor(
        html_path=str(BOOK_HTML),
        output_path=str(out_path),
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
