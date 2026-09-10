"""
agent-eval feedback  CLI (SPEC-043 REQ-6b).

Currently one subcommand:
    agent-eval feedback export-preferences <path> --out prefs.jsonl
        Extract A/B preference signals (pairwise judge · human annotations ·
        fail↔pass contrast pairs) from result JSON files into one JSON Lines
        preference dataset. Export only — no training.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_USE_COLOR = sys.stdout.isatty()
_B = "\033[1m" if _USE_COLOR else ""
_G = "\033[32m" if _USE_COLOR else ""
_Y = "\033[33m" if _USE_COLOR else ""
_RD = "\033[31m" if _USE_COLOR else ""
_R = "\033[0m" if _USE_COLOR else ""


def cmd_feedback(args: argparse.Namespace) -> int:
    cmd = getattr(args, "feedback_command", None)
    if cmd == "export-preferences":
        return _cmd_export_preferences(args)
    print(
        f"{_B}agent-eval feedback{_R} — feedback / preference signals\n\n"
        f"  {_Y}export-preferences{_R}  Extract A/B preference rows from result "
        f"JSONs into a JSONL dataset\n\n"
        f"Usage: agent-eval feedback export-preferences <path> --out prefs.jsonl",
        file=sys.stderr,
    )
    return 1


def _cmd_export_preferences(args: argparse.Namespace) -> int:
    src = Path(args.path)
    if not src.exists():
        print(f"{_RD}❌  Not found: {src}{_R}", file=sys.stderr)
        return 1

    from agent_evaluator.datasets.preference_export import export_preferences

    try:
        summary = export_preferences(src, args.out)
    except Exception as exc:  # noqa: BLE001
        print(f"{_RD}❌  Export failed: {exc}{_R}", file=sys.stderr)
        return 1

    n = summary["n_written"]
    print()
    print(f"  {_B}Exported {n} preference row(s){_R} from "
          f"{summary['n_files_scanned']} file(s)")
    for s, c in sorted(summary["by_source"].items()):
        print(f"      {_Y}{s}{_R}: {c}")
    if summary["n_files_skipped"]:
        print(f"      {_Y}(skipped {summary['n_files_skipped']} unparseable file(s)){_R}")
    print(f"  💾  {_G}{summary['out_path']}{_R}")
    if n == 0:
        print(f"  {_Y}No pairwise-judge / annotation / contrast-pair signals found.{_R}")
    print()
    return 0


def build_feedback_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "feedback",
        help="Feedback / preference signals (export-preferences)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "`export-preferences` turns the A/B signals already in\n"
            "your result files — pairwise judge verdicts, human annotations, and\n"
            "fail↔pass contrast pairs — into one JSON Lines preference dataset.\n"
            "Export only: reward models / fine-tuning are out of scope."
        ),
    )
    fb_sub = p.add_subparsers(dest="feedback_command")

    ep = fb_sub.add_parser(
        "export-preferences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Extract A/B preference rows into a JSONL dataset",
        description=(
            "Scans a result JSON file or a directory of them and writes rows:\n"
            "  {question, response_a, response_b, preferred: a|b|tie,\n"
            "   source: pairwise_judge|annotation|contrast_pair, annotator?}\n\n"
            "Sources:\n"
            "  pairwise_judge  extra_metrics.llm_judge_pairwise (judge_pairwise() calls)\n"
            "  annotation      extra_metrics.preference_annotations / task extra.preference\n"
            "  contrast_pair   insights.contrast_pairs joined to tasks[] (fail=a, pass=b)\n"
        ),
        epilog=(
            f"{_B}Examples:{_R}\n"
            f"  {_G}agent-eval feedback export-preferences results/ --out prefs.jsonl{_R}\n"
            f"  {_G}agent-eval feedback export-preferences v3.json --out v3_prefs.jsonl{_R}\n"
        ),
    )
    ep.add_argument("path", help="A result JSON file or a directory of them")
    ep.add_argument("--out", required=True, metavar="JSONL",
                    help="Output JSON Lines path")
