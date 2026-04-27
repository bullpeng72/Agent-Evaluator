"""Step 2: 나레이션 스크립트 → Marp 슬라이드 Markdown.

YouTube 16:9 (1920×1080) 최적화:
- 슬라이드당 본문 최대 5줄, 코드 최대 12줄
- [CODE: filename — keywords] → Evaluator_Examples/ 에서 실제 코드 자동 추출
- 다크 테마 — YouTube 시청 환경 최적화

Usage:
    python narration_to_slides.py S2E2
    python narration_to_slides.py S2E2 --png    # marp CLI로 PNG 이미지 추출
    python narration_to_slides.py S2E2 --pdf    # marp CLI로 PDF 변환
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import EPISODE_MAP_PATH, OUTPUT_DIR, PROJECT_ROOT

# ── YouTube 슬라이드 밀도 제한 ────────────────────────────────────────────────
MAX_BULLETS = 5        # 슬라이드당 최대 불렛 수
MAX_BULLET_CHARS = 50  # 불렛 1개 최대 글자 수
MAX_CODE_LINES = 12    # 코드 슬라이드 최대 줄 수

# ── Marp 헤더 — YouTube 16:9 다크 테마 ───────────────────────────────────────
MARP_HEADER = """\
---
marp: true
theme: default
size: 16:9
paginate: true
style: |
  section {
    font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
    font-size: 30px;
    padding: 44px 72px;
    background-color: #0f1117;
    color: #e2e8f0;
    line-height: 1.65;
  }
  h1 {
    font-size: 56px;
    color: #60a5fa;
    line-height: 1.2;
    margin-bottom: 8px;
  }
  h2 {
    font-size: 38px;
    color: #93c5fd;
    border-bottom: 3px solid #1d4ed8;
    padding-bottom: 10px;
    margin-bottom: 24px;
  }
  h3 {
    font-size: 28px;
    color: #94a3b8;
    font-weight: 400;
  }
  ul { padding-left: 36px; margin: 0; }
  li { margin: 10px 0; line-height: 1.5; }
  strong { color: #fbbf24; }
  em { color: #a78bfa; font-style: normal; }
  code {
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 23px;
    background: #1e293b;
    padding: 2px 8px;
    border-radius: 4px;
    color: #86efac;
  }
  pre {
    background: #0d1117;
    border-radius: 10px;
    padding: 22px 28px;
    border-left: 4px solid #1d4ed8;
    margin: 4px 0 0 0;
  }
  pre code {
    font-size: 19px;
    background: transparent;
    padding: 0;
    color: #cdd6f4;
    line-height: 1.6;
  }
  blockquote {
    border-left: 4px solid #60a5fa;
    padding: 12px 24px;
    background: #1e293b;
    border-radius: 0 8px 8px 0;
    color: #94a3b8;
    margin: 16px 0;
  }
  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
  }
  section.lead h1 { font-size: 60px; }
  section.lead h2 { border: none; font-size: 44px; color: #60a5fa; }
  section.lead h3 { font-size: 30px; margin-top: 16px; }
  section.concept {
    background: linear-gradient(135deg, #0f1117 0%, #1e1b4b 100%);
  }
  section.concept h2 {
    font-size: 46px;
    color: #a78bfa;
    border-color: #7c3aed;
    text-align: center;
    margin-top: 40px;
  }
  section.code h2 { font-size: 30px; color: #86efac; border-color: #15803d; }
  footer { display: none; }
---

"""

TITLE_SLIDE = """\
<!-- _class: lead -->

# {title}

### {subtitle}

---

"""

SECTION_SLIDE = """\
## {heading}

{content}

---

"""

CONCEPT_SLIDE = """\
<!-- _class: concept -->

## {heading}

---

"""

CODE_SLIDE = """\
<!-- _class: code -->

## 💻 `{filename}`

```python
{code}
```

---

"""

CODE_BASH_SLIDE = """\
<!-- _class: code -->

## 💻 `{filename}`

```bash
{code}
```

---

"""

CODE_FALLBACK_SLIDE = """\
<!-- _class: code -->

## 💻 코드 실습

> {desc}

---

"""

SUMMARY_SLIDE = """\
<!-- _class: lead -->

## 핵심 정리

{summary_points}

---

"""


# ── 코드 추출 엔진 ─────────────────────────────────────────────────────────────

def parse_code_marker(code_desc: str) -> tuple[str, list[str]]:
    """'ch01.py — InstructionConfig·SLAConfig 선언' → (filename, keywords)"""
    parts = re.split(r'\s*[—–-]\s*', code_desc, maxsplit=1)
    filename = parts[0].strip()
    if len(parts) < 2:
        return filename, []
    description = parts[1]
    # Python 식별자 추출 (CamelCase, @decorator, snake_case 4자+)
    raw = re.findall(r'@?[A-Z][a-zA-Z0-9]+|[a-z_][a-zA-Z0-9_]{3,}', description)
    stopwords = {'from', 'import', 'with', 'self', 'args', 'kwargs',
                 'true', 'false', 'none', 'print', 'return', 'class'}
    return filename, [k for k in raw if k.lower() not in stopwords]


def find_example_file(filename: str) -> Optional[Path]:
    """Evaluator_Examples/ 에서 파일 경로 반환."""
    for candidate in [
        PROJECT_ROOT / "Evaluator_Examples" / filename,
        PROJECT_ROOT / filename,
    ]:
        if candidate.exists():
            return candidate
    return None


_TERMINAL_WORDS = {'터미널', '터미날', 'terminal', 'shell', 'bash', '실행', 'cmd', 'cli'}

def is_terminal_marker(filename: str) -> bool:
    """파일명이 아니라 터미널 실행 지시인지 확인 (확장자 없고 터미널 단어 포함)."""
    base = filename.split('/')[-1].lower()
    return '.' not in base and any(kw in base for kw in _TERMINAL_WORDS)


def generate_terminal_snippet(description: str) -> str:
    """터미널 실행 마커 설명에서 bash 코드 블록 생성."""
    lines: list[str] = []
    # python -m 또는 python script.py 명령 — 한글 앞까지 추출
    py_match = re.search(
        r'(python(?:\s+-m\s+[\w./]+(?:\s+[\w./]+)*|\s+[\w./]+\.py(?:\s+[\w./]+)*))',
        description
    )
    if py_match:
        # 명령 끝에서 한글·쉼표·'실행' 등 설명 텍스트 제거
        cmd = re.sub(r'\s+[가-힣].*$', '', py_match.group(1)).strip()
        lines.append(f'$ {cmd}')
    # 결과 디렉토리 / JSON 파일 확인
    dir_match = re.search(r'([\w]+_results?/|results?/)', description)
    json_match = re.search(r'([\w]+\.json)', description)
    if dir_match or json_match:
        lines.append('')
        lines.append('# 결과 확인')
        if dir_match:
            lines.append(f'$ ls {dir_match.group(1)}')
        if json_match:
            lines.append(json_match.group(1))
    # agent-eval 명령
    ae_match = re.search(r'agent-eval\s+\S+', description)
    if ae_match:
        lines.append('')
        lines.append(f'$ {ae_match.group(0)}')
    # 아무것도 추출 안 되면 설명 앞부분 그대로
    if not lines:
        lines = [f'# {description[:80]}']
    return '\n'.join(lines)


def find_best_example_file(keywords: list[str],
                            exclude_file: Optional[Path] = None) -> Optional[Path]:
    """키워드 기준으로 Evaluator_Examples/ 전체에서 가장 적합한 파일 반환."""
    examples_dir = PROJECT_ROOT / "Evaluator_Examples"
    if not examples_dir.exists() or not keywords:
        return None
    best_file: Optional[Path] = None
    best_score = 0
    for py_file in sorted(examples_dir.glob("ch*.py")):
        if exclude_file and py_file.resolve() == exclude_file.resolve():
            continue
        try:
            text = py_file.read_text(encoding='utf-8')
        except OSError:
            continue
        # import·comment 줄 제외한 실제 코드에서 키워드 히트 수
        score = 0
        for line in text.split('\n'):
            s = line.strip()
            if s.startswith('#') or re.match(r'^(from\s+\S+\s+import|import\s+)', s):
                continue
            score += sum(1 for kw in keywords if kw in line)
        if score > best_score:
            best_score, best_file = score, py_file
    return best_file if best_score >= 2 else None


# 중복 방지 시 폴백에서 제외할 공통 키워드
_COMMON_FALLBACK_KWS = {'QuickEval', 'eval_session', 'measured_answer',
                         'question', 'result', 'answer', 'monitor'}


def _extract_from_file(filepath: Path, keywords: list[str]) -> Optional[str]:
    """filepath에서 키워드 기반 코드 스니펫 추출 (핵심 로직)."""
    lines = filepath.read_text(encoding='utf-8').split('\n')

    # import 블록 범위 마킹
    import_lines: set[int] = set()
    in_paren = False
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r'^(from\s+\S+\s+import|import\s+)', s):
            import_lines.add(i)
            in_paren = '(' in s and ')' not in s
        elif in_paren:
            import_lines.add(i)
            if ')' in s:
                in_paren = False

    # 우선순위: 실제 코드 > import > 주석
    hits: list[int] = []
    hits_comment: list[int] = []
    hits_import: list[int] = []
    if keywords:
        for i, line in enumerate(lines):
            if not any(kw in line for kw in keywords):
                continue
            stripped = line.strip()
            if i in import_lines:
                hits_import.append(i)
            elif stripped.startswith('#'):
                hits_comment.append(i)
            else:
                hits.append(i)
    if not hits:
        hits = hits_import or hits_comment

    if not hits:
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith('@') or s.startswith('def ') or s.startswith('class '):
                return _clean_snippet(lines[i:i + MAX_CODE_LINES])
        return _clean_snippet(lines[:MAX_CODE_LINES])

    # 가장 밀집된 시작점 (슬라이딩 윈도우)
    best_start = hits[0]
    if len(hits) > 1:
        best_count = 0
        for h in hits:
            count = sum(1 for x in hits if h <= x < h + MAX_CODE_LINES)
            if count > best_count:
                best_count, best_start = count, h

    # @decorator / def / class 경계 역탐색 (최대 6줄)
    start = best_start
    for i in range(best_start, max(0, best_start - 6), -1):
        s = lines[i].strip()
        if s.startswith('@') or s.startswith('def ') or s.startswith('class '):
            start = i
            break

    snippet: list[str] = []
    for line in lines[start:start + MAX_CODE_LINES * 2]:
        stripped = line.strip()
        if stripped.startswith('print(') and len(stripped) > 60:
            continue
        if re.match(r'^[=#]{10,}', stripped):
            continue
        snippet.append(line)
        if len(snippet) >= MAX_CODE_LINES:
            snippet.append('    ...')
            break

    return _clean_snippet(snippet)


def extract_code_snippet(filename: str, keywords: list[str],
                          used_snippets: Optional[set[str]] = None) -> Optional[str]:
    """키워드 군집 근처의 코드 블록을 MAX_CODE_LINES 이하로 추출.

    used_snippets: 이미 사용된 (filepath절대경로, 스니펫앞80자) 튜플 집합.
                   파일 수준 + 내용 수준 양쪽 중복 방지.
    """
    filepath = find_example_file(filename)
    is_fallback = filepath is None
    if is_fallback:
        # 폴백: 이미 사용된 파일은 제외하고 검색
        used_files: set[Path] = set()
        if used_snippets is not None:
            used_files = {p for p, _ in used_snippets if isinstance(p, Path)}
        filepath = find_best_example_file(keywords)
        # 이미 사용된 파일이면 다른 파일 재검색
        if filepath and filepath.resolve() in {f.resolve() for f in used_files}:
            unique_kws = [k for k in keywords if k not in _COMMON_FALLBACK_KWS]
            alt = find_best_example_file(unique_kws or keywords, exclude_file=filepath)
            if alt:
                filepath = alt

    if not filepath:
        return None

    result = _extract_from_file(filepath, keywords)

    # 스니펫 내용 수준 중복 감지
    if result and used_snippets is not None:
        fp = result[:80]
        if any(s == fp for _, s in used_snippets if isinstance(s, str)):
            unique_kws = [k for k in keywords if k not in _COMMON_FALLBACK_KWS]
            if unique_kws:
                alt_path = find_best_example_file(unique_kws, exclude_file=filepath)
                if alt_path:
                    alt = _extract_from_file(alt_path, unique_kws)
                    if alt:
                        result = alt
                        filepath = alt_path
        if result:
            used_snippets.add((filepath, result[:80]))

    return result


def _clean_snippet(lines: list[str]) -> Optional[str]:
    """앞뒤 빈 줄 제거 후 문자열 반환. 내용 없으면 None."""
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines) if lines else None


# ── 나레이션 파싱 ─────────────────────────────────────────────────────────────

def parse_narration(narration_text: str) -> list[dict]:
    """나레이션 텍스트를 슬라이드 단위 딕셔너리 리스트로 파싱."""
    slides = []
    lines = narration_text.split('\n')
    current_section: Optional[str] = None
    current_content: list[str] = []
    after_code: bool = False  # CODE 마커 이후 동일 섹션 여부

    slide_marker_re = re.compile(r'\[SLIDE:\s*(.+?)\]', re.IGNORECASE)
    section_re = re.compile(r'^##\s+(.+)')

    def _flush():
        nonlocal after_code
        if current_section and current_content:
            # CODE 직후 남은 내용은 section_continued 타입으로 마킹
            stype = 'section_continued' if after_code else 'section'
            slides.append({
                'type': stype,
                'heading': current_section,
                'content': '\n'.join(current_content).strip(),
            })
            current_content.clear()
        after_code = False

    for line in lines:
        # [SLIDE: 제목] 마커
        m = slide_marker_re.search(line)
        if m:
            _flush()
            slides.append({'type': 'slide_marker',
                           'heading': m.group(1).strip(), 'content': ''})
            continue

        # [CODE: 파일명 — 설명] 마커
        if line.strip().startswith('[CODE:'):
            code_desc = re.sub(r'\[CODE:\s*(.+?)\]', r'\1', line).strip()
            _flush()
            slides.append({'type': 'code_transition',
                           'heading': '💻 코드 실습',
                           'content': code_desc})
            after_code = True  # 이후 동일 섹션 내용은 continued 처리
            continue

        # [PAUSE] 무시
        if line.strip() == '[PAUSE]':
            continue

        # ## 섹션 헤더 → 새 섹션 시작 시 after_code 초기화
        m = section_re.match(line)
        if m:
            _flush()
            heading_raw = m.group(1).strip()
            tag_m = re.match(r'^\[([A-Z0-9]+)\]\s*(.*)', heading_raw)
            heading = tag_m.group(2).strip() or heading_raw if tag_m else heading_raw
            upper = heading_raw.upper()
            if 'INTRO' in upper:
                current_section = f'[INTRO] {heading}'
            elif 'OUTRO' in upper:
                current_section = f'[OUTRO] {heading}'
            else:
                current_section = heading
            continue

        if current_section is not None:
            current_content.append(line)

    _flush()
    return slides


# ── 불렛 밀도 제어 ────────────────────────────────────────────────────────────

def to_bullets(text: str, max_collect: Optional[int] = None) -> list[str]:
    """나레이션 텍스트 → YouTube 가독성 기준 불렛 리스트."""
    raw = re.split(r'\n+', text.strip())
    bullets = []
    for s in raw:
        s = s.strip().lstrip('-•* ')
        # ③ **bold** 마크다운 잔재 제거
        s = s.replace('**', '')
        s = s.strip()
        if len(s) < 10:
            continue
        if len(s) > MAX_BULLET_CHARS:
            cut = s[:MAX_BULLET_CHARS].rsplit(' ', 1)[0]
            s = cut + '…'
        bullets.append(s)
    limit = max_collect if max_collect is not None else MAX_BULLETS * 2
    return bullets[:limit]


def split_bullets(bullets: list[str], heading: str) -> list[tuple[str, str]]:
    """불렛이 MAX_BULLETS 초과 시 슬라이드 분할.

    마지막 청크가 1개 이하이면 앞 청크에 흡수 (단독 1불렛 슬라이드 방지).
    """
    if not bullets:
        return []
    if len(bullets) <= MAX_BULLETS:
        return [(heading, '\n'.join(f'- {b}' for b in bullets))]

    chunks = [bullets[i:i + MAX_BULLETS] for i in range(0, len(bullets), MAX_BULLETS)]
    # 마지막 청크가 1개 이하이면 앞 청크에 흡수 (단독 1불렛 슬라이드 방지)
    if len(chunks) > 1 and len(chunks[-1]) <= 1:
        tail = chunks.pop()       # 1-bullet 청크 제거
        chunks[-1] = chunks[-1] + tail  # 새 마지막 청크에 병합

    total = len(chunks)
    result = []
    for idx, chunk in enumerate(chunks):
        suffix = f' ({idx + 1}/{total})' if total > 1 else ''
        result.append((heading + suffix, '\n'.join(f'- {b}' for b in chunk)))
    return result


# ── Marp 조립 ─────────────────────────────────────────────────────────────────

def build_marp(episode_id: str, slides_data: list[dict],
               title: str, season_name: str) -> str:
    parts = [MARP_HEADER]
    parts.append(TITLE_SLIDE.format(title=title, subtitle=f'{season_name} · {episode_id}'))

    outro_bullets: list[str] = []
    used_snippets: set[tuple] = set()  # 중복 코드 슬라이드 방지 (filepath, snippet앞80자)

    for slide in slides_data:
        heading = slide['heading']
        content = slide['content']
        stype = slide['type']

        if stype == 'slide_marker':
            parts.append(CONCEPT_SLIDE.format(heading=heading))

        elif stype == 'code_transition':
            filename, keywords = parse_code_marker(content)
            # 터미널 실행 마커 → bash 코드 블록
            if is_terminal_marker(filename):
                bash_code = generate_terminal_snippet(content)
                parts.append(CODE_BASH_SLIDE.format(filename=filename, code=bash_code))
            else:
                code = extract_code_snippet(filename, keywords, used_snippets)
                if code:
                    parts.append(CODE_SLIDE.format(filename=filename, code=code))
                else:
                    parts.append(CODE_FALLBACK_SLIDE.format(desc=content))

        elif '[INTRO]' in heading:
            bullets = to_bullets(content)
            # 1개 이하 불렛은 intro 슬라이드 생략 (너무 얇은 전환 슬라이드 방지)
            if len(bullets) >= 2:
                for h, c in split_bullets(bullets, '이 영상에서 배울 것'):
                    parts.append(SECTION_SLIDE.format(heading=h, content=c))

        elif '[OUTRO]' in heading:
            # ④ OUTRO는 최대 5개까지 수집 (3개 제한 제거)
            outro_bullets = to_bullets(content, max_collect=5)

        elif stype == 'section_continued':
            # ① CODE 마커 직후 남은 내용 — 불렛 2개 이상일 때만 슬라이드 생성
            bullets = to_bullets(content)
            if len(bullets) >= 2:
                for h, c in split_bullets(bullets, heading):
                    parts.append(SECTION_SLIDE.format(heading=h, content=c))
            # ② 불렛 1개 이하 → 단독 슬라이드 생략

        else:
            bullets = to_bullets(content)
            if not bullets:
                continue
            for h, c in split_bullets(bullets, heading):
                parts.append(SECTION_SLIDE.format(heading=h, content=c))

    if outro_bullets:
        summary = '\n'.join(f'- {b}' for b in outro_bullets)
        parts.append(SUMMARY_SLIDE.format(summary_points=summary))

    return ''.join(parts)


# ── Marp CLI 변환 ─────────────────────────────────────────────────────────────

def _run_marp(slides_path: Path, mode: str) -> bool:
    """marp CLI 실행. 미설치 시 False."""
    flag_map = {
        'pdf': ['--pdf'],
        'png': ['--images', 'png', '--image-scale', '1.5'],  # 1280*1.5=1920px
    }
    try:
        result = subprocess.run(
            ['marp', str(slides_path), '--allow-local-files'] + flag_map[mode],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f'  {mode.upper()} 생성 완료')
            return True
        print(f'  [WARN] marp {mode} 변환 실패: {result.stderr[:200]}')
        return False
    except FileNotFoundError:
        print('  [WARN] marp CLI 미설치. `npm i -g @marp-team/marp-cli` 후 재실행.')
        return False


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='나레이션 → Marp 슬라이드 생성')
    parser.add_argument('episode_id', help='에피소드 ID (예: S2E2)')
    parser.add_argument('--pdf', action='store_true', help='marp CLI로 PDF 변환')
    parser.add_argument('--png', action='store_true', help='marp CLI로 PNG 이미지 추출')
    parser.add_argument('--force', action='store_true', help='기존 파일 덮어쓰기')
    args = parser.parse_args()

    episode_id = args.episode_id.upper()
    narration_path = OUTPUT_DIR / episode_id / 'narration.md'
    slides_path = OUTPUT_DIR / episode_id / 'slides.md'

    if not narration_path.exists():
        print(f'[ERROR] narration.md 없음: {narration_path}')
        sys.exit(1)

    if slides_path.exists() and not args.force:
        print(f'[SKIP] {slides_path} 이미 존재. --force로 덮어쓰기.')
        return str(slides_path)

    print(f'\n[Step 2] 나레이션 → 슬라이드: {episode_id}')

    data = json.loads(EPISODE_MAP_PATH.read_text(encoding='utf-8'))
    ep = data['episodes'].get(episode_id, {})
    title = ep.get('title', episode_id)
    season = ep.get('season', '')
    season_name = f'Season {season}' if isinstance(season, int) else 'Special'

    narration_text = narration_path.read_text(encoding='utf-8')
    slides_data = parse_narration(narration_text)
    print(f'  파싱된 슬라이드 단위: {len(slides_data)}개')

    # 코드 추출 가능 여부 미리 확인
    code_slides = [s for s in slides_data if s['type'] == 'code_transition']
    resolved = sum(1 for s in code_slides
                   if extract_code_snippet(*parse_code_marker(s['content'])[:2]) is not None)
    if code_slides:
        print(f'  코드 슬라이드: {resolved}/{len(code_slides)}개 자동 추출 성공')

    marp_content = build_marp(episode_id, slides_data, title, season_name)
    slides_path.write_text(marp_content, encoding='utf-8')

    # 슬라이드 수 카운트
    slide_count = marp_content.count('\n---\n')
    print(f'  완료: {slides_path} ({slide_count}개 슬라이드)')

    if args.pdf:
        _run_marp(slides_path, 'pdf')
    if args.png:
        _run_marp(slides_path, 'png')

    return str(slides_path)


if __name__ == '__main__':
    main()
