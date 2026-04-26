"""day_plan.json 기반 일별 콘텐츠 자동 생성기.

Usage:
    python run_day.py day_01                 # day_01 콘텐츠 전체 생성
    python run_day.py day_01 --blog-only     # 블로그만
    python run_day.py day_01 --youtube-only  # YouTube만
    python run_day.py day_01 --skip-audio    # 음성 생략 (기본 적용)
    python run_day.py --list                 # 전체 day 계획 출력
    python run_day.py day_01 --status        # 해당 day 생성 현황 확인
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).parent.parent
REPO_ROOT = CONTENT_DIR.parent
DAY_PLAN = CONTENT_DIR / "day_plan.json"
BLOG_PIPELINE = CONTENT_DIR / "Blog" / "pipeline" / "run_all.py"
YOUTUBE_PIPELINE = CONTENT_DIR / "YouTube" / "pipeline" / "run_all.py"
BLOG_OUTPUT = CONTENT_DIR / "Blog" / "output"
YOUTUBE_OUTPUT = CONTENT_DIR / "YouTube" / "output"


def load_plan() -> dict:
    with open(DAY_PLAN, encoding="utf-8") as f:
        return json.load(f)


def run(cmd: list[str], label: str) -> bool:
    print(f"\n  [{label}] $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    ok = result.returncode == 0
    print(f"  [{label}] {'완료' if ok else '실패 (종료코드 ' + str(result.returncode) + ')'}")
    return ok


def check_status(day_key: str, day_data: dict) -> None:
    print(f"\n[현황] {day_key} — {day_data['theme']}")
    print(f"  note: {day_data.get('note', '')}\n")

    blog_ids = day_data.get("blog", [])
    if blog_ids:
        print("  블로그:")
        for pid in blog_ids:
            out = BLOG_OUTPUT / pid / "post_velog.md"
            icon = "✅" if out.exists() else "·"
            print(f"    {icon} {pid}")

    youtube_ids = day_data.get("youtube", [])
    if youtube_ids:
        print("  YouTube:")
        for eid in youtube_ids:
            narr = YOUTUBE_OUTPUT / eid / "narration.md"
            meta = YOUTUBE_OUTPUT / eid / "metadata.txt"
            if meta.exists():
                icon = "✅"
            elif narr.exists():
                icon = "📝"
            else:
                icon = "·"
            print(f"    {icon} {eid}  {'(나레이션만)' if icon == '📝' else ''}")

    publish = day_data.get("publish", [])
    if publish:
        print(f"  출판: {', '.join(publish)} (수동 실행: /publish --platform <platform>)")


def print_list(plan: dict) -> None:
    print(f"\n{'═' * 64}")
    print(f"  30일 콘텐츠 계획  (총 {plan['meta']['total_days']}일)")
    print(f"{'─' * 64}")
    for day_key, day_data in sorted(plan["days"].items()):
        blogs = day_data.get("blog", [])
        ytbs = day_data.get("youtube", [])
        pubs = day_data.get("publish", [])

        blog_done = sum(1 for p in blogs if (BLOG_OUTPUT / p / "post_velog.md").exists())
        ytb_done = sum(1 for e in ytbs if (YOUTUBE_OUTPUT / e / "metadata.txt").exists())

        blog_str = f"blog {blog_done}/{len(blogs)}" if blogs else ""
        ytb_str = f"YT {ytb_done}/{len(ytbs)}" if ytbs else ""
        pub_str = f"pub:{','.join(pubs)}" if pubs else ""

        parts = [p for p in [blog_str, ytb_str, pub_str] if p]
        status = "  ".join(parts) if parts else "(수작업)"

        num = day_key.split("_")[1]
        print(f"  Day {num}  {day_data['theme'][:30]:<31} {status}")
    print(f"{'═' * 64}\n")


def run_blog(blog_ids: list[str], force: bool) -> list[str]:
    failed = []
    for pid in blog_ids:
        out = BLOG_OUTPUT / pid / "post_velog.md"
        if out.exists() and not force:
            print(f"\n  [blog/{pid}] 이미 생성됨 (건너뜀). --force 로 재생성 가능.")
            continue
        ok = run(
            [sys.executable, str(BLOG_PIPELINE), pid],
            f"blog/{pid}",
        )
        if not ok:
            failed.append(f"blog/{pid}")
    return failed


def run_youtube(youtube_ids: list[str], skip_audio: bool, force: bool) -> list[str]:
    failed = []
    for eid in youtube_ids:
        narr = YOUTUBE_OUTPUT / eid / "narration.md"
        meta = YOUTUBE_OUTPUT / eid / "metadata.txt"

        if meta.exists() and not force:
            print(f"\n  [youtube/{eid}] 이미 완성됨 (건너뜀). --force 로 재생성 가능.")
            continue

        if narr.exists() and not force:
            print(f"\n  [youtube/{eid}] 나레이션 있음 → --force 로 슬라이드/자막/메타데이터 생성")
            continue

        # 나레이션 생성
        ok = run(
            [sys.executable, str(YOUTUBE_PIPELINE), "--narration-only", eid],
            f"youtube/{eid} 나레이션",
        )
        if not ok:
            failed.append(f"youtube/{eid}")
            continue

        if force:
            extra = ["--skip-audio"] if skip_audio else []
            ok2 = run(
                [sys.executable, str(YOUTUBE_PIPELINE), eid] + extra,
                f"youtube/{eid} 전체",
            )
            if not ok2:
                failed.append(f"youtube/{eid}")

    return failed


def main():
    parser = argparse.ArgumentParser(description="day_plan.json 기반 일별 콘텐츠 생성")
    parser.add_argument("day", nargs="?", help="day_01 ~ day_30 또는 --list")
    parser.add_argument("--list", action="store_true", help="전체 계획 출력")
    parser.add_argument("--status", action="store_true", help="해당 day 현황 확인")
    parser.add_argument("--blog-only", action="store_true", help="블로그만 생성")
    parser.add_argument("--youtube-only", action="store_true", help="YouTube만 생성")
    parser.add_argument("--skip-audio", action="store_true", default=True, help="음성 생략 (기본값)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    plan = load_plan()

    if args.list:
        print_list(plan)
        return

    if not args.day:
        parser.print_help()
        return

    day_key = args.day if args.day.startswith("day_") else f"day_{args.day.zfill(2)}"
    if day_key not in plan["days"]:
        print(f"[ERROR] {day_key} 를 day_plan.json에서 찾을 수 없습니다.")
        sys.exit(1)

    day_data = plan["days"][day_key]

    if args.status:
        check_status(day_key, day_data)
        return

    num = day_key.split("_")[1]
    print(f"\n{'█' * 64}")
    print(f"  Day {num} — {day_data['theme']}")
    if day_data.get("note"):
        print(f"  note: {day_data['note']}")
    print(f"{'█' * 64}")

    publish = day_data.get("publish", [])
    if publish:
        print(f"\n  ⚠️  출판 단계 ({', '.join(publish)}) 는 수동 실행이 필요합니다:")
        for p in publish:
            print(f"    /publish --platform {p}")

    failed = []

    if not args.youtube_only:
        blog_ids = day_data.get("blog", [])
        if blog_ids:
            print(f"\n{'─' * 64}")
            print(f"  블로그 ({len(blog_ids)}개): {', '.join(blog_ids)}")
            print(f"{'─' * 64}")
            failed += run_blog(blog_ids, args.force)

    if not args.blog_only:
        youtube_ids = day_data.get("youtube", [])
        if youtube_ids:
            print(f"\n{'─' * 64}")
            print(f"  YouTube ({len(youtube_ids)}편): {', '.join(youtube_ids)}")
            print(f"{'─' * 64}")
            failed += run_youtube(youtube_ids, args.skip_audio, args.force)

    print(f"\n{'═' * 64}")
    if failed:
        print(f"  ⚠️  실패: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"  Day {num} 생성 완료")

    if not args.youtube_only:
        blog_ids = day_data.get("blog", [])
        if blog_ids:
            print("\n  다음 단계:")
            for pid in blog_ids:
                out = BLOG_OUTPUT / pid / "post_velog.md"
                if out.exists():
                    print(f"    /blog {pid} --publish   ← Velog 발행")

    youtube_ids = day_data.get("youtube", [])
    if youtube_ids and not args.blog_only:
        print("\n  YouTube 나레이션 검토 후:")
        for eid in youtube_ids:
            narr = YOUTUBE_OUTPUT / eid / "narration.md"
            if narr.exists():
                print(f"    /youtube {eid} --force --skip-audio   ← 슬라이드·자막·메타데이터")
    print(f"{'═' * 64}\n")


if __name__ == "__main__":
    main()
