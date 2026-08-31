"""
agent-eval dataset  CLI — 골든 데이터셋 관리.

명령어:
    agent-eval dataset build    운영 결과에서 골든셋 후보 자동 추출
    agent-eval dataset promote  결과 파일의 HITL 리뷰 큐(insights.review_queue)를
                                골든 회귀 케이스로 승격 (SPEC-041 P15)
"""
from __future__ import annotations

import argparse
import json
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
    if cmd == "promote":
        return _cmd_promote(args)
    if cmd == "health":
        return _cmd_health(args)
    # 서브커맨드 미지정 — 도움말 출력
    print(
        f"{_B}agent-eval dataset{_R} — Golden Dataset Management\n\n"
        f"  {_Y}build{_R}     Auto-extract golden set candidates from production results\n"
        f"  {_Y}promote{_R}   Promote a result file's human-review queue into golden cases\n"
        f"  {_Y}health{_R}    Assess a golden set against a run — mode coverage, stale cases\n\n"
        f"Usage: agent-eval dataset build --help",
        file=sys.stderr,
    )
    return 1


def _cmd_health(args: argparse.Namespace) -> int:
    """``agent-eval dataset health <golden.json> --against <result.json>`` (P58)."""
    gp = Path(args.golden_file)
    rp = Path(args.against)
    if not gp.is_file():
        print(f"{_RD}❌  Golden file not found: {gp}{_R}", file=sys.stderr)
        return 1
    if not rp.is_file():
        print(f"{_RD}❌  Result file not found: {rp}{_R}", file=sys.stderr)
        return 1
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{_RD}❌  Failed to parse result JSON: {exc}{_R}", file=sys.stderr)
        return 1

    from agent_evaluator.datasets.golden_health import assess_golden_health

    # make sure the run's failure_taxonomy is available to the assessor
    ins = (result.get("extra_metrics") or {}).get("insights")
    if not (ins and ins.get("failure_taxonomy")):
        try:
            from agent_evaluator.reporting.insights import build_insights

            fresh = build_insights(result) or {}
            result.setdefault("extra_metrics", {}).setdefault("insights", {})[
                "failure_taxonomy"] = fresh.get("failure_taxonomy")
        except Exception:
            pass

    health = assess_golden_health(
        str(gp), result, history_dir=getattr(args, "history", None),
    )
    if health is None:
        print(f"{_RD}❌  No usable cases in {gp}{_R}", file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(health, ensure_ascii=False, indent=2))
        return 0

    print(f"\n  {_B}Golden-set health — {gp.name}{_R}")
    print(f"  {health['note']}")
    cp = health.get("coverage_pct")
    if cp is not None:
        col = _G if cp >= 80 else (_Y if cp >= 50 else _RD)
        print(f"  Failure-mode coverage: {col}{cp:.0f}%{_R} "
              f"({health['n_modes_considered']} mode(s) in this run)")
    for u in health.get("uncovered_failure_modes") or []:
        print(f"  {_RD}✗ not exercised:{_R} {u['name']} "
              f"({u['n_failures']} failure(s), owner {u['owner']})")
    for s in (health.get("stale_cases") or [])[:8]:
        print(f"  {_Y}~ stale:{_R} {s['reason']} — {s['question'][:80]}")
    for r in (health.get("redundant_cases") or [])[:8]:
        print(f"  {_Y}~ duplicate:{_R} case {r['case_index']} ≈ case {r['duplicate_of']}")
    return 0


def _cmd_promote(args: argparse.Namespace) -> int:
    """Promote the flagged tasks in a result file's ``insights.review_queue`` into
    a golden regression dataset (SPEC-041 P15).

    Closes the failure -> regression-test loop: the tasks whose automated verdict
    is least trustworthy become the cases a future run is measured against.
    """
    result_path = Path(args.result_file)
    if not result_path.is_file():
        print(f"{_RD}❌  Result file not found: {result_path}{_R}", file=sys.stderr)
        return 1
    try:
        with result_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"{_RD}❌  Could not read result file: {exc}{_R}", file=sys.stderr)
        return 1

    baseline_path = getattr(args, "baseline", None)
    baseline = None
    if baseline_path:
        try:
            with open(baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"{_Y}⚠  Ignoring unreadable baseline ({exc}){_R}", file=sys.stderr)

    try:
        from agent_evaluator.reporting.insights import build_insights
    except ImportError as exc:
        print(f"{_RD}❌  Failed to import build_insights: {exc}{_R}", file=sys.stderr)
        return 1

    insights = build_insights(data, baseline)
    rq = insights.get("review_queue") or {}
    items = rq.get("items") or []
    if not items:
        print("  ✅  Review queue is empty — nothing to promote.")
        return 0

    min_priority = getattr(args, "min_priority", "medium")
    order = {"high": 0, "medium": 1, "low": 2}
    cutoff = order.get(min_priority, 1)
    wanted = {it["task_id"]: it for it in items if order.get(it["priority"], 1) <= cutoff}
    if not wanted:
        print(f"  ✅  No review items at priority >= {min_priority}.")
        return 0

    tasks_by_id = {
        str(t.get("task_id")): t
        for t in (data.get("tasks") or []) if isinstance(t, dict) and t.get("task_id")
    }
    cases: list[dict] = []
    for tid, it in wanted.items():
        t = tasks_by_id.get(tid)
        if t is None:
            continue
        cases.append({
            "question": t.get("question") or "",
            "ground_truth": t.get("ground_truth") or "",
            "context": t.get("context") or "",
            "source_task_id": tid,
            "task_type": t.get("task_type") or "",
            "review_priority": it.get("priority"),
            "review_reasons": it.get("reasons") or [],
            "promoted_from": result_path.name,
            "promoted_at": datetime.now().isoformat(),
            "needs_human_review": True,
        })
    if not cases:
        print(f"{_Y}⚠  Review items found but their tasks are not in tasks[] — "
              f"cannot promote.{_R}", file=sys.stderr)
        return 1

    out_dir = Path(getattr(args, "out", None) or (result_path.parent / "golden_datasets"))
    version = getattr(args, "promote_version", None) or "review"
    try:
        from agent_evaluator.datasets.builder import GoldenSetBuilder

        builder = GoldenSetBuilder(source_dir=str(result_path.parent), output_dir=str(out_dir))
        name = getattr(args, "name", None)
        saved = builder.merge_to_golden(cases, version=version, output_name=name)
    except Exception as exc:
        print(f"{_RD}❌  Failed to write golden dataset: {exc}{_R}", file=sys.stderr)
        return 1

    print()
    print(f"  {_B}Promoted {len(cases)} review-queue task(s) to a golden dataset{_R}")
    from collections import Counter
    dist = Counter(c["review_priority"] for c in cases)
    for pri, cnt in dist.most_common():
        print(f"      {_Y}{pri}{_R}: {cnt}")
    print(f"  💾  Saved to: {_G}{saved}{_R}")
    print("  📋  Every case is flagged needs_human_review — verify labels before "
          "using as a gate.")
    print()
    return 0


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
        print("  📋  Human-review flags are included. Review then merge into the golden set.")
        print(f"  {_Y}Hint:{_R} Use builder.merge_to_golden(cases, version='v1.0') to merge")
    print()
    return 0
