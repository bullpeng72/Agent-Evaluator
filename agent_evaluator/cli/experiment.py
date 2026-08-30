"""
agent-eval experiment — register and score falsifiable improvement hypotheses
(SPEC-041 P27), stored append-only in ``.aoo/experiments.jsonl``.

A thin terminal wrapper around ``agent_evaluator.rca.experiments`` — no new
logic. Workflow:

    register  — "I expect Gate A's avg_subtask_completion to rise +0.08"
    list      — show open / resolved hypotheses
    score     — re-check open hypotheses against a baseline result and (with
                --persist) write the confirmed/partially_confirmed/refuted verdict

``score`` is informational — it never exits non-zero on a refuted hypothesis
(HOTL: a wrong prediction is data, not a build failure).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.rca.experiments import (
    load_experiments,
    register_experiment,
    resolve_experiment,
    score_experiments,
)

_COLOR = _supports_color()
G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""

_DEFAULT_LOG = ".aoo/experiments.jsonl"
_VERDICT_COLOR = {
    "confirmed": G, "partially_confirmed": Y, "refuted": RD,
    "inconclusive": D, "pending": D,
}


def _err(msg: str) -> str:
    return f"{RD}❌ {msg}{R}"


def _ok(msg: str) -> str:
    return f"{G}✅ {msg}{R}"


def _load_result(path_str: str) -> dict | None:
    p = Path(path_str)
    if not p.is_file():
        print(_err(f"File not found: {p}"))
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(_err(f"Failed to parse JSON: {exc}"))
        return None


def _cmd_register(args: argparse.Namespace) -> int:
    row = register_experiment(
        args.log,
        target_gate=args.gate,
        predicted_delta=args.predict_delta,
        target_field=args.field,
        note=args.note,
        baseline_ref=args.baseline,
    )
    tgt = f"Gate {row['target_gate']}" + (
        f" · {row['target_field']}" if row["target_field"] else " score"
    )
    print(_ok(
        f"Registered {row['experiment_id']}: {tgt} {row['predicted_delta']:+.3f}"
    ))
    print(f"{D}  log: {args.log}{R}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    exps = load_experiments(args.log, status=args.status)
    if not exps:
        where = f" (status={args.status})" if args.status else ""
        print(f"{D}No experiments{where} in {args.log}{R}")
        return 0
    print(f"{B}{'ID':<16} {'GATE/FIELD':<34} {'PRED':>8} {'ACTUAL':>8} "
          f"{'VERDICT':<20} STATUS{R}")
    for e in exps:
        tgt = f"{e.get('target_gate', '?')}"
        if e.get("target_field"):
            tgt += f".{e['target_field']}"
        pred = e.get("predicted_delta")
        act = e.get("actual_delta")
        verdict = e.get("verdict") or ("open" if e.get("status") != "resolved" else "-")
        vc = _VERDICT_COLOR.get(verdict, "")
        print(
            f"{e.get('experiment_id', '?'):<16} {tgt[:34]:<34} "
            f"{(f'{pred:+.3f}' if isinstance(pred, (int, float)) else '-'):>8} "
            f"{(f'{act:+.3f}' if isinstance(act, (int, float)) else '-'):>8} "
            f"{vc}{verdict:<20}{R} {e.get('status', '?')}"
        )
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(args.baseline)
    if baseline is None:
        return 1
    open_exps = load_experiments(args.log, status="open")
    if not open_exps:
        print(f"{D}No open experiments in {args.log}{R}")
        return 0
    scored = score_experiments(
        open_exps, current, baseline, min_effect=args.min_effect,
    )
    persisted = 0
    print(f"{B}{'ID':<16} {'GATE/FIELD':<34} {'PRED':>8} {'ACTUAL':>8} VERDICT{R}")
    for row in scored:
        tgt = f"{row.get('target_gate', '?')}"
        if row.get("target_field"):
            tgt += f".{row['target_field']}"
        pred = row.get("predicted_delta")
        act = row.get("actual_delta")
        verdict = row.get("verdict", "inconclusive")
        vc = _VERDICT_COLOR.get(verdict, "")
        print(
            f"{row.get('experiment_id', '?'):<16} {tgt[:34]:<34} "
            f"{(f'{pred:+.3f}' if isinstance(pred, (int, float)) else '-'):>8} "
            f"{(f'{act:+.3f}' if isinstance(act, (int, float)) else '-'):>8} "
            f"{vc}{verdict}{R}"
        )
        if args.persist and verdict in ("confirmed", "partially_confirmed", "refuted"):
            resolve_experiment(
                args.log, row["experiment_id"],
                actual_delta=act, verdict=verdict,
                note=f"scored against {Path(args.baseline).name}",
            )
            persisted += 1
    if args.persist:
        print(_ok(f"Persisted {persisted} resolution(s) to {args.log}"))
    else:
        print(f"{D}Dry run — pass --persist to write verdicts back to {args.log}{R}")
    return 0


def build_experiment_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``experiment`` subcommand on the argparse subparsers."""
    p = sub.add_parser(
        "experiment",
        help="Register / score improvement hypotheses (.aoo/experiments.jsonl)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Register a falsifiable prediction about a change you are about to\n"
            "make, then score it once a new run gives you a baseline to compare\n"
            "against. Thin wrapper around agent_evaluator.rca.experiments.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval experiment register --gate A "
            "--field avg_subtask_completion --predict-delta 0.08 --note 'add SubtaskConfig'\n"
            "  agent-eval experiment list\n"
            "  agent-eval experiment score results/v3.json --baseline results/v2.json --persist\n"
        ),
    )
    esub = p.add_subparsers(dest="experiment_command")

    reg = esub.add_parser("register", help="Register a new hypothesis")
    reg.add_argument("--gate", required=True, metavar="X", help="Target Gate (A-G or custom id)")
    reg.add_argument(
        "--field", default=None, metavar="NAME",
        help="Target details key (optional; e.g. avg_subtask_completion)",
    )
    reg.add_argument(
        "--predict-delta", type=float, required=True, dest="predict_delta", metavar="D",
        help="Expected signed change in the Gate score / field (e.g. 0.08 or -0.05)",
    )
    reg.add_argument("--note", default=None, help="What change this prediction is about")
    reg.add_argument(
        "--baseline", default=None, metavar="REF",
        help="Path/label of the run this is measured against (informational)",
    )
    reg.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                     help=f"Experiments log path (default: {_DEFAULT_LOG})")

    lst = esub.add_parser("list", help="List registered hypotheses")
    lst.add_argument("--status", choices=["open", "resolved"], default=None,
                     help="Filter by status")
    lst.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                     help=f"Experiments log path (default: {_DEFAULT_LOG})")

    sc = esub.add_parser("score", help="Score open hypotheses against a baseline result")
    sc.add_argument("result_file", help="Current evaluation result JSON")
    sc.add_argument("--baseline", required=True, metavar="PATH",
                    help="Prior evaluation result JSON to measure movement from")
    sc.add_argument("--persist", action="store_true",
                    help="Write confirmed/partially_confirmed/refuted verdicts back to the log")
    sc.add_argument("--min-effect", type=float, default=0.02, dest="min_effect", metavar="D",
                    help="|delta| below this is treated as noise (default: 0.02)")
    sc.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log path (default: {_DEFAULT_LOG})")


def cmd_experiment(args: argparse.Namespace) -> int:
    """``experiment`` subcommand handler — dispatches on ``experiment_command``."""
    handlers = {
        "register": _cmd_register,
        "list": _cmd_list,
        "score": _cmd_score,
    }
    cmd = getattr(args, "experiment_command", None)
    handler = handlers.get(cmd) if cmd is not None else None
    if handler is None:
        print(_err("Specify an experiment subcommand: register | list | score"))
        print(f"{D}For details: agent-eval experiment --help{R}")
        return 1
    return handler(args)
