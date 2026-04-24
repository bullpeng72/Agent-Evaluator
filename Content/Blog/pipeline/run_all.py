"""블로그 파이프라인 전체 실행.

Usage:
    python run_all.py gate_a                  # 단일 포스트
    python run_all.py gate_a gate_b gate_c    # 복수 포스트
    python run_all.py --all --skip-seo        # 전체 포스트 (SEO 생략)
    python run_all.py --list                  # 포스트 목록
    python run_all.py --type 튜토리얼         # 유형별 실행
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from config import OUTPUT_DIR, POST_MAP_PATH

PIPELINE_DIR = Path(__file__).parent

STEPS = [
    ("chapter_to_blog.py", "Step 1: 챕터 → 블로그 포스트"),
    ("generate_seo.py",    "Step 2: SEO 메타데이터"),
]


def load_posts() -> dict:
    return json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))["posts"]


def post_status(post_id: str) -> str:
    d = OUTPUT_DIR / post_id
    icons = {
        "V": d / "post_velog.md",
        "S": d / "seo.json",
    }
    return "".join(k if v.exists() else "·" for k, v in icons.items())


def list_posts():
    posts = load_posts()
    ordered = sorted(posts.items(), key=lambda x: x[1].get("series_order", 99))
    print(f"\n{'상태':4s} {'ID':25s} {'순서':5s} {'유형':8s} 제목")
    print("─" * 85)
    for post_id, post in ordered:
        status = post_status(post_id)
        print(f" {status}  {post_id:23s} {str(post.get('series_order','?')):5s} "
              f"{post.get('type',''):8s} {post['title'][:45]}")
    print("\n상태: V=Velog포스트 S=SEO메타 ·=미생성\n")


def run_step(script: str, post_id: str, extra: list[str]) -> bool:
    cmd = [sys.executable, str(PIPELINE_DIR / script), post_id] + extra
    return subprocess.run(cmd).returncode == 0


def run_post(post_id: str, platform: str, skip_seo: bool, force: bool) -> dict[str, bool]:
    results = {}
    force_arg = ["--force"] if force else []

    for script, label in STEPS:
        if script == "generate_seo.py" and skip_seo:
            print(f"  [SKIP] {label}")
            results[script] = True
            continue

        extra = force_arg.copy()
        if script == "chapter_to_blog.py":
            extra += ["--platform", platform]

        print(f"\n{'─' * 45}")
        ok = run_step(script, post_id, extra)
        results[script] = ok
        if not ok:
            print(f"  [FAIL] {label}")
            break
        time.sleep(0.3)

    return results


def print_summary(post_id: str, results: dict[str, bool]):
    labels = dict(STEPS)
    ok_count = sum(results.values())
    total = len(results)
    icon = "✅" if ok_count == total else "⚠️"
    print(f"\n  {icon} {post_id}: {ok_count}/{total} 완료")
    for script, ok in results.items():
        print(f"     {'✅' if ok else '❌'} {labels.get(script, script)}")

    out_dir = OUTPUT_DIR / post_id
    if out_dir.exists():
        for f in sorted(out_dir.iterdir()):
            print(f"     📄 {f.name}  ({f.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description="블로그 콘텐츠 파이프라인")
    parser.add_argument("post_ids", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--all", action="store_true", help="전체 포스트 실행")
    parser.add_argument("--type", help="특정 유형만 실행 (예: 튜토리얼, 개념)")
    parser.add_argument("--platform", default="velog",
                        choices=["velog", "tistory", "medium", "all"])
    parser.add_argument("--skip-seo", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.list:
        list_posts()
        return

    all_posts = load_posts()
    post_ids: list[str] = []

    if args.all:
        post_ids = list(all_posts.keys())
    elif args.type:
        post_ids = [pid for pid, p in all_posts.items() if p.get("type") == args.type]
        if not post_ids:
            print(f"[ERROR] type='{args.type}'에 해당하는 포스트 없음.")
            sys.exit(1)
    elif args.post_ids:
        post_ids = args.post_ids
    else:
        parser.print_help()
        sys.exit(0)

    for pid in post_ids:
        if pid not in all_posts:
            print(f"[ERROR] 알 수 없는 포스트 ID: {pid}")
            sys.exit(1)

    print(f"\n총 {len(post_ids)}개 포스트 처리 시작\n")
    all_results = {}
    for pid in post_ids:
        post = all_posts[pid]
        print(f"\n{'█' * 45}")
        print(f"  {pid} — {post['title'][:50]}")
        results = run_post(pid, args.platform, args.skip_seo, args.force)
        all_results[pid] = results
        print_summary(pid, results)

    if len(post_ids) > 1:
        success = sum(1 for r in all_results.values() if all(r.values()))
        print(f"\n전체: {success}/{len(post_ids)}편 완료")


if __name__ == "__main__":
    main()
