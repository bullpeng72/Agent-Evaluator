"""Step 6: Marp 슬라이드 PNG + 음성 MP3 → YouTube MP4.

전제 조건:
    npm install -g @marp-team/marp-cli   # 슬라이드 → PNG
    brew install ffmpeg                   # PNG + MP3 → MP4

슬라이드 표시 시간 배분 전략:
    각 슬라이드가 차지하는 나레이션 텍스트 비율에 비례해 표시 시간 배분.
    나레이션 없는 슬라이드(타이틀·concept·요약)는 최소 2초 보장.

Usage:
    python slides_to_video.py S1E1
    python slides_to_video.py S1E1 --force
    python slides_to_video.py S1E1 --no-subtitles   # 자막 제외
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import OUTPUT_DIR

MIN_SLIDE_SECONDS = 2.0   # 슬라이드 최소 표시 시간
DEFAULT_FPS = 30


def check_deps() -> bool:
    ok = True
    for tool in ['marp', 'ffmpeg']:
        if shutil.which(tool) is None:
            hint = ('npm i -g @marp-team/marp-cli' if tool == 'marp'
                    else 'brew install ffmpeg')
            print(f'  [ERROR] {tool} 미설치 — {hint}')
            ok = False
        else:
            print(f'  ✅ {tool}')
    return ok


def export_slide_images(slides_path: Path, out_dir: Path) -> list[Path]:
    """marp CLI로 슬라이드 PNG 생성. slide.001.png 형식으로 반환."""
    result = subprocess.run(
        ['marp', str(slides_path),
         '--images', 'png',
         '--image-scale', '1.5',   # 1280×720 → 1920×1080
         '--allow-local-files',
         '--output', str(out_dir / 'slide')],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f'  [ERROR] marp PNG 생성 실패:\n{result.stderr[:400]}')
        return []

    images = sorted(out_dir.glob('slide.*.png'))
    if not images:
        # marp 버전에 따라 출력 파일명 패턴 다를 수 있음
        images = sorted(out_dir.glob('slide*.png'))
    return images


def parse_srt_duration(srt_path: Path) -> float:
    """SRT 파일에서 마지막 타임스탬프 → 총 재생 시간(초)."""
    content = srt_path.read_text(encoding='utf-8')
    # 모든 종료 시각 파싱
    ends = re.findall(r'--> (\d{2}:\d{2}:\d{2}[,\.]\d{3})', content)
    if not ends:
        return 0.0
    last = ends[-1].replace(',', '.')
    h, m, rest = last.split(':')
    s, ms = rest.split('.')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def calc_slide_durations(slides_md: str, narration_md: str,
                          total_seconds: float) -> list[float]:
    """슬라이드별 표시 시간 계산.

    1. slides.md에서 슬라이드 수 N 파악
    2. 나레이션 텍스트를 섹션별로 분할해 텍스트 비율 계산
    3. 비율에 비례해 total_seconds 배분 (MIN_SLIDE_SECONDS 하한 보장)
    """
    # 슬라이드 수
    n_slides = slides_md.count('\n---\n')
    if n_slides == 0:
        return [total_seconds]

    # 나레이션 섹션별 텍스트 길이 수집
    sections: list[str] = re.split(
        r'\[SLIDE:[^\]]*\]|\[CODE:[^\]]*\]|^##\s+.+',
        narration_md, flags=re.MULTILINE
    )
    sections = [s.strip() for s in sections if s.strip()]

    if not sections:
        # fallback: 균등 배분
        per = total_seconds / n_slides
        return [max(per, MIN_SLIDE_SECONDS)] * n_slides

    # 섹션 길이 → 슬라이드 비율 매핑
    # 타이틀 슬라이드(1장) + 섹션 슬라이드 + 요약 슬라이드(1장) 구조 반영
    weights = [MIN_SLIDE_SECONDS]  # 타이틀 슬라이드 최소 2초
    for sec in sections:
        char_count = len(re.sub(r'\s+', '', sec))
        weights.append(max(float(char_count), 50.0))
    weights.append(MIN_SLIDE_SECONDS)  # 요약 슬라이드

    # n_slides에 맞춰 weights 조정 (초과 시 마지막 버킷에 합산, 부족 시 최솟값 추가)
    while len(weights) < n_slides:
        weights.append(MIN_SLIDE_SECONDS)
    while len(weights) > n_slides:
        weights[-2] += weights.pop()

    total_weight = sum(weights)
    durations = [max(w / total_weight * total_seconds, MIN_SLIDE_SECONDS)
                 for w in weights]

    # 총합이 total_seconds를 초과하지 않도록 정규화
    scale = total_seconds / sum(durations)
    return [d * scale for d in durations]


def build_ffmpeg_input(images: list[Path], durations: list[float],
                        tmp_dir: Path) -> Path:
    """ffmpeg concat demuxer 입력 파일 생성."""
    # durations 길이를 images에 맞춤
    while len(durations) < len(images):
        durations.append(MIN_SLIDE_SECONDS)
    durations = durations[:len(images)]

    lines = []
    for img, dur in zip(images, durations):
        lines.append(f"file '{img}'")
        lines.append(f'duration {dur:.3f}')
    # ffmpeg concat 마지막 프레임 출력 보장
    if images:
        lines.append(f"file '{images[-1]}'")

    concat_path = tmp_dir / 'concat.txt'
    concat_path.write_text('\n'.join(lines), encoding='utf-8')
    return concat_path


def run_ffmpeg(concat_path: Path, audio_path: Path, srt_path: Optional[Path],
               output_path: Path) -> bool:
    """ffmpeg로 MP4 생성."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', str(concat_path),
        '-i', str(audio_path),
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest',
    ]

    if srt_path and srt_path.exists():
        # 자막 번인 (YouTube 하드 자막)
        srt_escaped = str(srt_path).replace(':', r'\:').replace("'", r"\'")
        cmd += ['-vf', f"subtitles='{srt_escaped}':force_style="
                       "'FontName=Noto Sans KR,FontSize=18,"
                       "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                       "BackColour=&H80000000,Bold=1,Outline=2'"]

    cmd.append(str(output_path))

    print(f'  ffmpeg 실행 중...')
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f'  [ERROR] ffmpeg 실패:\n{result.stderr[-600:]}')
        return False
    return True


# ── 메인 ─────────────────────────────────────────────────────────────────────

from typing import Optional  # noqa: E402 (already imported above, safe duplicate)


def main():
    parser = argparse.ArgumentParser(description='슬라이드 + 음성 → MP4 영상')
    parser.add_argument('episode_id', help='에피소드 ID (예: S1E1)')
    parser.add_argument('--force', action='store_true', help='기존 MP4 덮어쓰기')
    parser.add_argument('--no-subtitles', action='store_true', help='자막 없이 생성')
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    ep_dir = OUTPUT_DIR / episode_id
    slides_path = ep_dir / 'slides.md'
    audio_path = ep_dir / 'narration.mp3'
    srt_path = ep_dir / 'narration.srt'
    output_path = ep_dir / 'video.mp4'

    print(f'\n[Step 6] 슬라이드 + 음성 → 영상: {episode_id}')

    # 사전 점검
    print('\n  의존성 확인:')
    if not check_deps():
        sys.exit(1)

    if not slides_path.exists():
        print(f'  [ERROR] slides.md 없음: {slides_path}')
        sys.exit(1)
    if not audio_path.exists():
        print(f'  [ERROR] narration.mp3 없음: {audio_path}')
        print('  먼저 음성을 생성하세요: python narration_to_audio.py {episode_id}')
        sys.exit(1)
    if not srt_path.exists():
        print(f'  [WARN] narration.srt 없음 — 자막 없이 진행')
        srt_path = None

    if output_path.exists() and not args.force:
        print(f'  [SKIP] {output_path} 이미 존재. --force로 덮어쓰기.')
        return str(output_path)

    with tempfile.TemporaryDirectory(prefix='yt_video_') as tmp:
        tmp_dir = Path(tmp)

        # 1. 슬라이드 → PNG
        print('\n  슬라이드 → PNG 변환 중...')
        images = export_slide_images(slides_path, tmp_dir)
        if not images:
            sys.exit(1)
        print(f'  생성된 PNG: {len(images)}장')

        # 2. 타이밍 계산
        total_sec = parse_srt_duration(srt_path) if srt_path else 0.0
        if total_sec < 1.0:
            # SRT 없거나 0초 → 음성 길이를 ffprobe로 측정
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
                capture_output=True, text=True,
            )
            try:
                total_sec = float(probe.stdout.strip())
            except ValueError:
                total_sec = len(images) * 10.0

        slides_md = slides_path.read_text(encoding='utf-8')
        narration_path = ep_dir / 'narration.md'
        narration_md = narration_path.read_text(encoding='utf-8') if narration_path.exists() else ''
        durations = calc_slide_durations(slides_md, narration_md, total_sec)
        print(f'  총 재생 시간: {total_sec:.1f}초 ({total_sec/60:.1f}분)')

        # 3. concat 파일 생성
        concat_path = build_ffmpeg_input(images, durations, tmp_dir)

        # 4. FFmpeg MP4 생성
        use_srt = None if args.no_subtitles else srt_path
        print()
        ok = run_ffmpeg(concat_path, audio_path, use_srt, output_path)
        if not ok:
            sys.exit(1)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f'  완료: {output_path} ({size_mb:.1f} MB)')
    print(f'  해상도: 1920×1080 (YouTube 권장 품질)')
    return str(output_path)


if __name__ == '__main__':
    main()
