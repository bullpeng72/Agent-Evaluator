"""
agent-eval dataset  CLI — 골든 데이터셋 관리.

명령어:
    agent-eval dataset build  운영 결과에서 골든셋 후보 자동 추출
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI helpers (main.py에서 직접 복사 불가 — 경량 재정의)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()
_B  = "\033[1m"  if _USE_COLOR else ""
_G  = "\033[32m" if _USE_COLOR else ""
_Y  = "\033[33m" if _USE_COLOR else ""
_RD = "\033[31m" if _USE_COLOR else ""
_R  = "\033[0m"  if _USE_COLOR else ""


def cmd_dataset(args: argparse.Namespace) -> int:
    """골든 데이터셋 관리 서브커맨드 진입점."""
    cmd = getattr(args, "dataset_command", None)
    if cmd == "build":
        return _cmd_build(args)
    # 서브커맨드 미지정 — 도움말 출력
    print(
        f"{_B}agent-eval dataset{_R} — Golden Dataset Management\n\n"
        f"  {_Y}build{_R}   Auto-extract golden set candidates from production results\n\n"
        f"Usage: agent-eval dataset build --help",
        file=sys.stderr,
    )
    return 1


def _cmd_build(args: argparse.Namespace) -> int:
    """운영 결과 파일에서 골든셋 후보를 추출하여 저장한다."""
    try:
        from agent_evaluator.datasets.builder import GoldenSetBuilder
    except ImportError as exc:
        print(f"{_RD}❌  Failed to load GoldenSetBuilder: {exc}{_R}", file=sys.stderr)
        return 1

    source = Path(getattr(args, "source", "./results"))
    output = getattr(args, "output", None)
    output_dir = Path(output) if output else source / "golden_datasets"
    strategies: list[str] = getattr(args, "strategy", ["failure_cases", "edge_cases"])
    max_cases: int = getattr(args, "max_cases", 50)
    no_review: bool = getattr(args, "no_review", False)
    name: str | None = getattr(args, "name", None)

    if not source.exists():
        print(f"{_RD}❌  Source directory not found: {source}{_R}", file=sys.stderr)
        return 1

    print()
    print(f"  {_B}Agent Evaluator — Golden Set Builder{_R}")
    print(f"  {'─' * 44}")
    print(f"  📁  Source    : {source}")
    print(f"  📁  Output    : {output_dir}")
    print(f"  🎯  Strategy  : {', '.join(strategies)}")
    print(f"  🔢  Max cases : {max_cases}")
    print()

    builder = GoldenSetBuilder(source_dir=str(source), output_dir=str(output_dir))

    try:
        candidates = builder.extract(
            strategies=strategies,
            max_cases=max_cases,
            require_human_review=not no_review,
        )
    except Exception as exc:
        print(f"{_RD}❌  Extraction failed: {exc}{_R}", file=sys.stderr)
        return 1

    if not candidates:
        print(f"  ⚠️  No candidate cases were extracted.\n"
              f"  {_Y}Hint:{_R} Check that --source path contains evaluation result JSON files.")
        return 0

    print(f"  ✅  {_G}{len(candidates)}{_R} candidate cases extracted")

    # print distribution by strategy
    from collections import Counter
    dist = Counter(c.get("strategy", "unknown") for c in candidates)
    for strat, cnt in dist.most_common():
        print(f"      {_Y}{strat}{_R}: {cnt}")

    # save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = name or f"candidates_{ts}.json"
    try:
        saved_path = builder.save_candidates(candidates, filename=filename)
    except Exception as exc:
        print(f"{_RD}❌  Save failed: {exc}{_R}", file=sys.stderr)
        return 1

    print()
    print(f"  💾  Saved to: {_G}{saved_path}{_R}")
    if not no_review:
        print(f"  📋  Human-review flags are included. Review then merge into the golden set.")
        print(f"  {_Y}Hint:{_R} Use builder.merge_to_golden(cases, version='v1.0') to merge")
    print()
    return 0
