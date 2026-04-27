"""전체 파이프라인 실행 — 챕터 → 나레이션 → 슬라이드 → 음성 → 자막 → 메타데이터.

Usage:
    # 단일 에피소드 전체 실행
    python run_all.py S2E2

    # 음성 생성 건너뜀 (API 키 없거나 비용 절약)
    python run_all.py S2E2 --skip-audio

    # 슬라이드 PDF 변환까지
    python run_all.py S2E2 --pdf

    # 기존 파일 모두 덮어쓰기
    python run_all.py S2E2 --force

    # 모든 에피소드 목록 출력
    python run_all.py --list

    # 여러 에피소드 순차 실행
    python run_all.py S2E2 S2E3 S2E4

    # Season 2 전체 실행
    python run_all.py --season 2 --skip-audio
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from config import EPISODE_MAP_PATH, OUTPUT_DIR

PIPELINE_DIR = Path(__file__).parent

STEPS = [
    ("chapter_to_narration.py",  "Step 1: 챕터 → 나레이션"),
    ("narration_to_slides.py",   "Step 2: 나레이션 → 슬라이드"),
    ("narration_to_audio.py",    "Step 3: 나레이션 → 음성"),
    ("narration_to_srt.py",      "Step 4: 나레이션 → 자막"),
    ("generate_metadata.py",     "Step 5: YouTube 메타데이터"),
]


def load_all_episodes() -> dict:
    return json.loads(EPISODE_MAP_PATH.read_text(encoding="utf-8"))["episodes"]


def list_episodes():
    episodes = load_all_episodes()
    print("\n사용 가능한 에피소드:\n")

    seasons: dict[str, list] = {}
    for ep_id, ep in episodes.items():
        s = str(ep.get("season", "special"))
        seasons.setdefault(s, []).append((ep_id, ep))

    for season_key in sorted(seasons.keys(), key=lambda x: (x.isdigit(), int(x) if x.isdigit() else x)):
        if season_key.isdigit():
            print(f"  [ Season {season_key} ]")
        else:
            print(f"  [ Special ]")
        for ep_id, ep in seasons[season_key]:
            status = _episode_status(ep_id)
            print(f"    {ep_id:6s}  {status}  {ep['title']}")
    print()


def _episode_status(episode_id: str) -> str:
    """에피소드 생성 상태를 아이콘으로 표시."""
    ep_dir = OUTPUT_DIR / episode_id
    files = {
        "N": ep_dir / "narration.md",
        "S": ep_dir / "slides.md",
        "A": ep_dir / "narration.mp3",
        "T": ep_dir / "narration.srt",
        "M": ep_dir / "metadata.txt",
    }
    return "".join(k if v.exists() else "·" for k, v in files.items())


def get_season_episodes(season: int) -> list[str]:
    episodes = load_all_episodes()
    return [ep_id for ep_id, ep in episodes.items() if ep.get("season") == season]


def run_step(script: str, episode_id: str, extra_args: list[str]) -> bool:
    script_path = PIPELINE_DIR / script
    cmd = [sys.executable, str(script_path), episode_id] + extra_args
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def run_episode(episode_id: str, skip_audio: bool, pdf: bool, force: bool) -> dict[str, bool]:
    results = {}
    force_arg = ["--force"] if force else []

    for script, label in STEPS:
        # 음성 생성 건너뜀
        if script == "narration_to_audio.py" and skip_audio:
            print(f"\n  [SKIP] {label} (--skip-audio)")
            results[script] = True
            continue

        # PDF 변환 옵션
        extra = force_arg.copy()
        if script == "narration_to_slides.py" and pdf:
            extra.append("--pdf")

        print(f"\n{'─' * 50}")
        ok = run_step(script, episode_id, extra)
        results[script] = ok
        if not ok:
            print(f"  [FAIL] {label} — 이후 단계 중단.")
            break
        time.sleep(0.2)

    return results


def print_summary(episode_id: str, results: dict[str, bool]):
    print(f"\n{'═' * 50}")
    print(f"  결과 요약: {episode_id}")
    print(f"{'─' * 50}")
    labels = dict(STEPS)
    for script, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {labels.get(script, script)}")

    ep_dir = OUTPUT_DIR / episode_id
    print(f"\n  출력 디렉토리: {ep_dir}")
    for f in sorted(ep_dir.iterdir()) if ep_dir.exists() else []:
        size = f.stat().st_size
        print(f"    {f.name:30s}  {size:>8,} bytes")
    print(f"{'═' * 50}\n")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube 콘텐츠 파이프라인 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("episode_ids", nargs="*", help="에피소드 ID (복수 가능)")
    parser.add_argument("--list", action="store_true", help="에피소드 목록 출력")
    parser.add_argument("--season", type=int, help="시즌 전체 실행 (예: --season 2)")
    parser.add_argument("--skip-audio", action="store_true", help="음성 생성 건너뜀")
    parser.add_argument("--pdf", action="store_true", help="슬라이드 PDF 변환")
    parser.add_argument("--force", action="store_true", help="기존 파일 모두 덮어쓰기")
    args = parser.parse_args()

    if args.list:
        list_episodes()
        return

    # 실행할 에피소드 목록 결정
    episode_ids: list[str] = []
    if args.season:
        episode_ids = get_season_episodes(args.season)
        if not episode_ids:
            print(f"[ERROR] Season {args.season}에 해당하는 에피소드 없음.")
            sys.exit(1)
        print(f"Season {args.season} 에피소드: {', '.join(episode_ids)}")
    elif args.episode_ids:
        episode_ids = [ep.upper() for ep in args.episode_ids]
    else:
        parser.print_help()
        sys.exit(0)

    # 유효성 검사
    all_episodes = load_all_episodes()
    for ep_id in episode_ids:
        if ep_id not in all_episodes:
            print(f"[ERROR] 알 수 없는 에피소드: {ep_id}")
            print(f"사용 가능: {', '.join(list(all_episodes.keys())[:10])} ...")
            sys.exit(1)

    # 실행
    all_results = {}
    for ep_id in episode_ids:
        print(f"\n{'█' * 50}")
        print(f"  에피소드: {ep_id} — {all_episodes[ep_id]['title']}")
        print(f"{'█' * 50}")

        results = run_episode(ep_id, args.skip_audio, args.pdf, args.force)
        all_results[ep_id] = results
        print_summary(ep_id, results)

    # 복수 에피소드 최종 요약
    if len(episode_ids) > 1:
        success = sum(1 for r in all_results.values() if all(r.values()))
        print(f"\n전체 결과: {success}/{len(episode_ids)}편 완료")


if __name__ == "__main__":
    main()
