"""
``agent-eval target {set,show,clear}`` (SPEC-041 P43) — manage a project's
per-gate / TCR / accuracy / cost pass bar in ``.aoo/targets.json``.

Once set, ``agent-eval gate`` uses it automatically (unless ``--gate-thresholds``
is given) and every "below target" line in the report / insights measures
against it.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.utils.targets import (
    DEFAULT_TARGETS_PATH,
    load_targets,
    save_targets,
)


def build_target_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "target",
        help="Set / show project targets (SLOs) in .aoo/targets.json",
        description=(
            "Pin your own pass bar. `agent-eval gate` and the insight layer then "
            "measure 'below target' against it instead of the built-in 0.7."
        ),
    )
    tsub = p.add_subparsers(dest="target_command", metavar="{set,show,clear}")

    sp = tsub.add_parser("set", help="Set one or more targets (merged into the file)")
    sp.add_argument("--gate", action="append", metavar="X=0.85", default=[],
                    help="Per-gate pass bar, e.g. --gate A=0.85 --gate E=0.95")
    sp.add_argument("--gate-default", type=float, metavar="0.75",
                    help="Pass bar for gates without an explicit --gate")
    sp.add_argument("--tcr", type=float, metavar="90", help="TCR target (percent)")
    sp.add_argument("--accuracy", type=float, metavar="75",
                    help="Accuracy target (percent)")
    sp.add_argument("--max-cost-per-task", type=float, metavar="0.03",
                    help="Cost-per-task SLO (USD)")
    sp.add_argument("--note", type=str, help="Free-text note")
    sp.add_argument("--path", default=DEFAULT_TARGETS_PATH)

    shp = tsub.add_parser("show", help="Print the current targets")
    shp.add_argument("--json", action="store_true", dest="as_json")
    shp.add_argument("--path", default=DEFAULT_TARGETS_PATH)

    cp = tsub.add_parser("clear", help="Delete the targets file")
    cp.add_argument("--path", default=DEFAULT_TARGETS_PATH)


def _fmt(t: dict) -> str:
    lines = []
    if t.get("gates"):
        lines.append("  gates: " + ", ".join(
            f"{k} ≥ {v}" for k, v in sorted(t["gates"].items())
        ))
    for key, label in (("gate_default", "gate default"), ("tcr_pct", "TCR"),
                       ("accuracy_pct", "accuracy"),
                       ("cost_per_task_usd", "cost/task (USD)")):
        if key in t:
            lines.append(f"  {label}: {t[key]}")
    if t.get("note"):
        lines.append(f"  note: {t['note']}")
    return "\n".join(lines) or "  (empty)"


def cmd_target(args: argparse.Namespace) -> int:
    cmd = getattr(args, "target_command", None)
    path = getattr(args, "path", DEFAULT_TARGETS_PATH)

    if cmd in (None, "show"):
        t = load_targets(path)
        if not t:
            print(f"No targets set ({path}). Use `agent-eval target set --gate A=0.85`.")
            return 0
        if getattr(args, "as_json", False):
            print(json.dumps(t, indent=2, ensure_ascii=False))
        else:
            print(f"Targets ({path}):\n{_fmt(t)}")
        return 0

    if cmd == "clear":
        import os
        if os.path.isfile(path):
            os.remove(path)
            print(f"Removed {path}.")
        else:
            print(f"Nothing to remove ({path}).")
        return 0

    if cmd == "set":
        patch: dict = {}
        gates: dict = {}
        for spec in args.gate or []:
            if "=" not in spec:
                print(f"❌ --gate expects X=0.85, got {spec!r}")
                return 1
            gk, gv = spec.split("=", 1)
            try:
                gates[gk.strip().upper()] = float(gv)
            except ValueError:
                print(f"❌ --gate value not a number: {spec!r}")
                return 1
        if gates:
            patch["gates"] = gates
        if args.gate_default is not None:
            patch["gate_default"] = args.gate_default
        if args.tcr is not None:
            patch["tcr_pct"] = args.tcr
        if args.accuracy is not None:
            patch["accuracy_pct"] = args.accuracy
        if args.max_cost_per_task is not None:
            patch["cost_per_task_usd"] = args.max_cost_per_task
        if args.note is not None:
            patch["note"] = args.note
        if not patch:
            print("Nothing to set. See `agent-eval target set -h`.")
            return 1
        resolved = save_targets(patch, path)
        print(f"Wrote {path}:\n{_fmt(resolved)}")
        return 0

    print("Usage: agent-eval target {set,show,clear}")
    return 1
