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
        f"{_B}agent-eval dataset{_R} — 골든 데이터셋 관리\n\n"
        f"  {_Y}build{_R}   운영 결과에서 골든셋 후보 자동 추출\n\n"
        f"사용법: agent-eval dataset build --help",
        file=sys.stderr,
    )
    return 1


def _cmd_build(args: argparse.Namespace) -> int:
    """운영 결과 파일에서 골든셋 후보를 추출하여 저장한다."""
    try:
        from agent_evaluator.datasets.builder import GoldenSetBuilder
    except ImportError as exc:
        print(f"{_RD}❌  GoldenSetBuilder 로드 실패: {exc}{_R}", file=sys.stderr)
        return 1

    source = Path(getattr(args, "source", "./results"))
    output = getattr(args, "output", None)
    output_dir = Path(output) if output else source / "golden_datasets"
    strategies: list[str] = getattr(args, "strategy", ["failure_cases", "edge_cases"])
    max_cases: int = getattr(args, "max_cases", 50)
    no_review: bool = getattr(args, "no_review", False)
    name: str | None = getattr(args, "name", None)

    if not source.exists():
        print(f"{_RD}❌  source 디렉토리를 찾을 수 없습니다: {source}{_R}", file=sys.stderr)
        return 1

    print()
    print(f"  {_B}Agent Evaluator — 골든셋 빌더{_R}")
    print(f"  {'─' * 44}")
    print(f"  📁  Source    : {source}")
    print(f"  📁  Output    : {output_dir}")
    print(f"  🎯  전략      : {', '.join(strategies)}")
    print(f"  🔢  최대 케이스: {max_cases}개")
    print()

    builder = GoldenSetBuilder(source_dir=str(source), output_dir=str(output_dir))

    try:
        candidates = builder.extract(
            strategies=strategies,
            max_cases=max_cases,
            require_human_review=not no_review,
        )
    except Exception as exc:
        print(f"{_RD}❌  추출 실패: {exc}{_R}", file=sys.stderr)
        return 1

    if not candidates:
        print(f"  ⚠️  추출된 후보 케이스가 없습니다.\n"
              f"  {_Y}힌트:{_R} --source 경로에 평가 결과 JSON 파일이 있는지 확인하세요.")
        return 0

    print(f"  ✅  {_G}{len(candidates)}개{_R} 후보 케이스 추출 완료")

    # 전략별 분포 출력
    from collections import Counter
    dist = Counter(c.get("strategy", "unknown") for c in candidates)
    for strat, cnt in dist.most_common():
        print(f"      {_Y}{strat}{_R}: {cnt}건")

    # 저장
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = name or f"candidates_{ts}.json"
    try:
        saved_path = builder.save_candidates(candidates, filename=filename)
    except Exception as exc:
        print(f"{_RD}❌  저장 실패: {exc}{_R}", file=sys.stderr)
        return 1

    print()
    print(f"  💾  저장 위치: {_G}{saved_path}{_R}")
    if not no_review:
        print(f"  📋  검토 필요 플래그가 포함됩니다. 검토 후 골든셋에 병합하세요.")
        print(f"  {_Y}힌트:{_R} builder.merge_to_golden(cases, version='v1.0') 으로 병합")
    print()
    return 0
