"""한국어 Book 챕터를 영문으로 번역한다. Book/*.md → Book_EN/*.md

코드 블록(``` ... ```)과 HTML 블록은 원본 그대로 보존한다.
진행 상태를 체크포인트 파일에 저장하므로 중단 후 재시작이 안전하다.

Usage:
    python translate_to_en.py --list              # 번역 현황 출력
    python translate_to_en.py --chapter 01        # 챕터 번호로 단일 번역
    python translate_to_en.py --chapter 00_서문   # 파일명 패턴으로 단일 번역
    python translate_to_en.py --all               # 전체 번역 (미완료 파일만)
    python translate_to_en.py --all --force       # 전체 강제 재번역
    python translate_to_en.py --check             # 의존성 확인
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from config import BOOK_DIR, CHAPTER_ORDER, CLAUDE_MODEL
from llm import call_claude

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BOOK_EN_DIR = BOOK_DIR.parent / "Book_EN"
CHECKPOINT_FILE = Path(__file__).parent.parent / "output_en" / ".translation_checkpoint.json"

# ── 번역에서 변경하지 않을 고정 기술 용어 ───────────────────────────────────
FIXED_TERMS = [
    "Harness Engineering", "HarnessEvaluationGate",
    "Gate A", "Gate B", "Gate C", "Gate D", "Gate E", "Gate F", "Gate G",
    "TCR", "SLA", "SLO", "TTFT", "P50", "P90", "P95", "P99",
    "QuickEval", "PerformanceMonitor", "HybridPerformanceMonitor",
    "LLMJudge", "AnomalyDetector", "GoldenSetBuilder", "CostTracker",
    "AdaptivePolicy", "ConversationSession",
    "InstructionConfig", "GoalAlignmentConfig", "PlanConfig", "SubtaskConfig",
    "LoopDetectionConfig", "ScopeConfig", "StateConsistencyConfig", "DeadlockConfig",
    "ReproducibilityConfig", "FaultToleranceConfig", "IdempotencyConfig",
    "SLAConfig", "EfficiencyConfig", "ResourceBudgetConfig",
    "ThreatSeverityConfig", "ComplianceConfig", "ThreatResponseConfig",
    "ConsensusConfig", "PropagationConfig", "AgentRoleConfig",
    "ExplainabilityConfig", "ObservabilityConfig", "ErrorDiagnosisConfig",
    "agent-evaluator", "agent_evaluator",
]

# ── 번역 프롬프트 ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are a professional technical translator specializing in AI/ML engineering books.
Translate Korean text to fluent, professional English technical writing.

RULES:
1. Translate ALL Korean text to natural, professional English
2. Preserve ALL markdown formatting exactly: ##, *, -, |, `, >, [text](url), bold (**text**)
3. Keep these technical terms UNCHANGED (do not translate them):
   {', '.join(FIXED_TERMS[:20])}
   and any other CamelCase class names or snake_case identifiers
4. Keep code placeholders <<<AE_CODE_N>>> EXACTLY as-is — never translate or modify them
5. Keep inline code like `this` and `function_name()` unchanged
6. Translate chapter/section headings too (e.g., "## 목표달성" → "## Goal Achievement")
7. Table content should be translated (headers and cells), keeping | separators
8. Do NOT add footnotes, explanatory notes, or change the document structure
9. Return ONLY the translated text — no preamble, no "Translation:", no commentary"""


# ── 코드/HTML 블록 추출·복원 ──────────────────────────────────────────────────

# fenced code blocks (``` ... ```) — 다중행 포함
_FENCE_RE = re.compile(r'(```[\s\S]*?```)', re.MULTILINE)

# HTML 블록 — <div, <svg, <style, <section 등으로 시작하는 블록
_HTML_BLOCK_RE = re.compile(
    r'(<(?:div|svg|style|section|figure|table)[^>]*>[\s\S]*?</(?:div|svg|style|section|figure|table)>)',
    re.MULTILINE | re.IGNORECASE,
)


def _extract_preserved_blocks(text: str) -> tuple[str, dict[str, str]]:
    """코드 블록과 HTML 블록을 플레이스홀더로 교체하고 원본 매핑을 반환한다."""
    block_map: dict[str, str] = {}
    counter = [0]

    def _replace(m: re.Match) -> str:
        key = f"<<<AE_CODE_{counter[0]}_BLOCK>>>"
        block_map[key] = m.group(0)
        counter[0] += 1
        return key

    text = _FENCE_RE.sub(_replace, text)
    text = _HTML_BLOCK_RE.sub(_replace, text)
    return text, block_map


def _restore_blocks(text: str, block_map: dict[str, str]) -> str:
    for key, original in block_map.items():
        text = text.replace(key, original)
    return text


# ── 텍스트 청킹 ───────────────────────────────────────────────────────────────

def _split_into_chunks(text: str, max_chars: int = 3500) -> list[str]:
    """## 헤더 경계에서 청크를 나눈다. 단일 섹션이 너무 크면 단락 경계에서 추가 분할."""
    # ## 또는 # 헤더 앞에서 분할 (헤더 자체는 다음 청크에 포함)
    parts = re.split(r'(?=\n#{1,3} )', '\n' + text)
    parts = [p.lstrip('\n') for p in parts if p.strip()]

    chunks: list[str] = []
    buf = ""

    for part in parts:
        if len(buf) + len(part) <= max_chars:
            buf += ('\n\n' if buf else '') + part
        else:
            if buf:
                chunks.append(buf)
            if len(part) > max_chars:
                # 단락 경계에서 추가 분할
                paras = part.split('\n\n')
                sub = ""
                for para in paras:
                    if len(sub) + len(para) + 2 <= max_chars:
                        sub += ('\n\n' if sub else '') + para
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = para
                if sub:
                    chunks.append(sub)
                buf = ""
            else:
                buf = part

    if buf:
        chunks.append(buf)

    return chunks if chunks else [text]


# ── 단일 파일 번역 ─────────────────────────────────────────────────────────────

def translate_file(src_path: Path, dst_path: Path, force: bool = False) -> bool:
    """src_path를 번역해 dst_path에 저장한다. 이미 존재하면 force 시에만 재번역."""
    if dst_path.exists() and not force:
        print(f"  [SKIP] {dst_path.name} — 이미 번역됨 (--force 로 재번역)")
        return True

    print(f"\n  번역 중: {src_path.relative_to(BOOK_DIR.parent)}")
    original = src_path.read_text(encoding="utf-8")

    # 코드/HTML 블록 보존
    processed, block_map = _extract_preserved_blocks(original)
    blocks_count = len(block_map)
    print(f"    코드/HTML 블록 보존: {blocks_count}개")

    # 청크 분할
    chunks = _split_into_chunks(processed)
    print(f"    청크 수: {len(chunks)}개 (총 {len(processed):,}자)")

    translated_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"    [{i}/{len(chunks)}] {len(chunk)}자 번역 중...", end=" ", flush=True)
        t0 = time.time()
        result = call_claude(SYSTEM_PROMPT, chunk, CLAUDE_MODEL, max_tokens=4096)
        elapsed = time.time() - t0
        print(f"완료 ({elapsed:.1f}s)")
        translated_parts.append(result)

    translated = '\n\n'.join(translated_parts)

    # 코드/HTML 블록 복원
    translated = _restore_blocks(translated, block_map)

    # 복원 검증
    missing = [k for k in block_map if k in translated]
    if missing:
        print(f"    [WARN] {len(missing)}개 플레이스홀더 미복원 — 원본 대체 적용")
        for k in missing:
            translated = translated.replace(k, block_map[k])

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(translated, encoding="utf-8")
    print(f"    저장: {dst_path.relative_to(BOOK_EN_DIR.parent)}")
    return True


# ── 체크포인트 ─────────────────────────────────────────────────────────────────

def _load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return set(data.get("completed", []))
    return set()


def _save_checkpoint(completed: set[str]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(
        json.dumps({"completed": sorted(completed)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 챕터 목록 해석 ────────────────────────────────────────────────────────────

def _resolve_chapter(pattern: str) -> list[Path]:
    """챕터 번호(01) 또는 파일명 패턴으로 Book/ 내 파일을 찾는다."""
    matches = []
    for rel in CHAPTER_ORDER:
        p = BOOK_DIR / rel
        if pattern in p.name or pattern in rel:
            if p.exists():
                matches.append(p)
    if not matches:
        print(f"[ERROR] 챕터 패턴 '{pattern}'에 맞는 파일 없음")
    return matches


def _all_source_files() -> list[tuple[Path, Path]]:
    """(src, dst) 쌍 목록 — config.py CHAPTER_ORDER 기준."""
    pairs = []
    for rel in CHAPTER_ORDER:
        src = BOOK_DIR / rel
        if src.exists():
            dst = BOOK_EN_DIR / rel
            pairs.append((src, dst))
        else:
            print(f"  [WARN] 소스 파일 없음: {rel}")
    return pairs


# ── 명령행 진입점 ──────────────────────────────────────────────────────────────

def cmd_list() -> None:
    completed = _load_checkpoint()
    pairs = _all_source_files()
    done = sum(1 for s, _ in pairs if str(s.relative_to(BOOK_DIR)) in completed
               or (BOOK_EN_DIR / s.relative_to(BOOK_DIR)).exists())
    print(f"\n번역 현황: {done}/{len(pairs)}개 완료\n")
    for src, dst in pairs:
        rel = str(src.relative_to(BOOK_DIR))
        status = "✅" if dst.exists() else "⬜"
        size = f"({src.stat().st_size // 1024}KB)" if src.exists() else ""
        print(f"  {status} {rel} {size}")


def cmd_translate_chapter(pattern: str, force: bool) -> None:
    sources = _resolve_chapter(pattern)
    if not sources:
        sys.exit(1)
    completed = _load_checkpoint()
    for src in sources:
        rel = str(src.relative_to(BOOK_DIR))
        dst = BOOK_EN_DIR / src.relative_to(BOOK_DIR)
        ok = translate_file(src, dst, force=force)
        if ok:
            completed.add(rel)
            _save_checkpoint(completed)


def cmd_translate_all(force: bool) -> None:
    pairs = _all_source_files()
    completed = _load_checkpoint()
    total = len(pairs)
    done_count = sum(1 for _, dst in pairs if dst.exists())
    print(f"\n전체 번역 시작: {total}개 파일 (이미 완료: {done_count}개)")
    print("=" * 62)

    success, skipped, failed = 0, 0, 0
    for i, (src, dst) in enumerate(pairs, 1):
        rel = str(src.relative_to(BOOK_DIR))
        print(f"\n[{i}/{total}] {rel}")
        if dst.exists() and not force:
            print(f"  [SKIP] 이미 번역됨")
            skipped += 1
            completed.add(rel)
            continue
        ok = translate_file(src, dst, force=force)
        if ok:
            success += 1
            completed.add(rel)
            _save_checkpoint(completed)
        else:
            failed += 1

    print(f"\n{'=' * 62}")
    print(f"완료: {success}개  건너뜀: {skipped}개  실패: {failed}개")
    if failed:
        print(f"[INFO] 중단 후 재실행하면 완료된 파일은 건너뜀 (--force 없이)")


def cmd_check() -> None:
    print("\n[의존성 확인]")
    try:
        from llm import call_claude as _cc
        print("  ✅ llm.py: call_claude 사용 가능")
    except ImportError as e:
        print(f"  ❌ llm.py 오류: {e}")

    import shutil
    if shutil.which("claude"):
        print("  ✅ claude CLI: Claude Code 인증 사용 가능")
    else:
        import os
        from config import ANTHROPIC_API_KEY
        if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-ant-"):
            print("  ✅ ANTHROPIC_API_KEY: 설정됨")
        else:
            print("  ❌ claude CLI 없음 + ANTHROPIC_API_KEY 미설정")

    print(f"  소스 디렉토리: {BOOK_DIR}")
    print(f"  대상 디렉토리: {BOOK_EN_DIR}")
    files = [BOOK_DIR / r for r in CHAPTER_ORDER if (BOOK_DIR / r).exists()]
    print(f"  번역 대상: {len(files)}개 파일")
    total_lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)
    print(f"  총 줄 수: {total_lines:,}줄 (예상 비용: Claude Sonnet ~$15–25)")


def main() -> None:
    parser = argparse.ArgumentParser(description="한국어 Book → 영문 Book_EN 번역")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--list", action="store_true", help="번역 현황 출력")
    grp.add_argument("--check", action="store_true", help="의존성 확인")
    grp.add_argument("--chapter", metavar="PATTERN", help="단일 챕터 번역 (번호 또는 파일명 패턴)")
    grp.add_argument("--all", action="store_true", help="전체 번역")
    parser.add_argument("--force", action="store_true", help="이미 번역된 파일도 재번역")
    args = parser.parse_args()

    if args.list:
        cmd_list()
    elif args.check:
        cmd_check()
    elif args.chapter:
        cmd_translate_chapter(args.chapter, args.force)
    elif args.all:
        cmd_translate_all(args.force)


if __name__ == "__main__":
    main()
