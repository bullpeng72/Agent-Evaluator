"""
``agent-eval benchmark {set,show,clear}`` (SPEC-041 P53) — pin an external
reference distribution in ``.aoo/reference.json`` so the insight layer can say
where a run sits *relative to what's normal / possible*, not just vs 0.7 or its
own baseline.

    set    --tcr 78 --gate A=0.75 --label ... [--from-results DIR]
    show   [--json]
    clear

``--from-results DIR`` scans a directory of result JSONs and stores the observed
TCR + per-gate score *distributions* (5-point percentile summaries) as the
reference — the "our own best historical runs" path.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.utils.reference import (
    DEFAULT_REFERENCE_PATH,
    load_reference,
    percentiles_from_values,
    save_reference,
)


def build_benchmark_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "benchmark",
        help="Set / show an external reference distribution (.aoo/reference.json)",
        description=(
            "Pin a reference distribution (public benchmark, your own best runs, "
            "or a competitor eval). insights.reference_frame then reports the "
            "current run's percentile and gap to the frontier."
        ),
    )
    bsub = p.add_subparsers(dest="benchmark_command", metavar="{set,show,clear}")

    sp = bsub.add_parser("set", help="Set reference values (merged into the file)")
    sp.add_argument("--tcr", type=float, metavar="78", help="Reference TCR (percent)")
    sp.add_argument("--accuracy", type=float, metavar="75",
                    help="Reference accuracy (percent)")
    sp.add_argument("--gate", action="append", metavar="X=0.75", default=[],
                    help="Per-gate reference score, e.g. --gate A=0.75 --gate E=0.95")
    sp.add_argument("--label", type=str, help="Short name for this reference set")
    sp.add_argument("--source", type=str, help="Where the numbers came from")
    sp.add_argument("--note", type=str, help="Free-text note")
    sp.add_argument("--from-results", metavar="DIR", dest="from_results",
                    help="Build TCR + per-gate percentile distributions from the "
                         "result JSONs in DIR (overrides --tcr / --gate)")
    sp.add_argument("--path", default=DEFAULT_REFERENCE_PATH)

    shp = bsub.add_parser("show", help="Print the current reference")
    shp.add_argument("--json", action="store_true", dest="as_json")
    shp.add_argument("--path", default=DEFAULT_REFERENCE_PATH)

    cp = bsub.add_parser("clear", help="Delete the reference file")
    cp.add_argument("--path", default=DEFAULT_REFERENCE_PATH)


def _fmt_entry(v: object) -> str:
    if isinstance(v, dict):
        return "p50 " + ", ".join(f"{k}={v[k]}" for k in ("p10", "p50", "p90") if k in v)
    if isinstance(v, list):
        return f"{len(v)} samples (min {min(v):.3g}, max {max(v):.3g})"
    return str(v)


def _fmt(ref: dict) -> str:
    lines = []
    if ref.get("label"):
        lines.append(f"  label: {ref['label']}")
    if ref.get("source"):
        lines.append(f"  source: {ref['source']}")
    if "tcr_pct" in ref:
        lines.append(f"  TCR: {_fmt_entry(ref['tcr_pct'])}")
    if "accuracy_pct" in ref:
        lines.append(f"  accuracy: {_fmt_entry(ref['accuracy_pct'])}")
    for g, v in sorted((ref.get("gate_scores") or {}).items()):
        lines.append(f"  Gate {g}: {_fmt_entry(v)}")
    if ref.get("note"):
        lines.append(f"  note: {ref['note']}")
    return "\n".join(lines) or "  (empty)"


def _from_results(dir_path: str) -> dict:
    from agent_evaluator.reporting.history import scan_history

    hist = scan_history(dir_path, limit=200)
    if not hist:
        raise ValueError(f"no usable result JSONs in {dir_path}")
    tcrs = [r["tcr"] for r in hist if isinstance(r.get("tcr"), (int, float))]
    patch: dict = {
        "source": f"{len(hist)} runs in {dir_path}",
        "label": "historical",
    }
    if len(tcrs) >= 2:
        patch["tcr_pct"] = percentiles_from_values(tcrs)
    gate_scores: dict = {}
    for g in "ABCDEFG":
        vals = [r["gate_scores"].get(g) for r in hist]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if len(vals) >= 2:
            gate_scores[g] = percentiles_from_values(vals)
    if gate_scores:
        patch["gate_scores"] = gate_scores
    return patch


def cmd_benchmark(args: argparse.Namespace) -> int:
    cmd = getattr(args, "benchmark_command", None)
    path = getattr(args, "path", DEFAULT_REFERENCE_PATH)

    if cmd in (None, "show"):
        ref = load_reference(path)
        if not ref:
            print(f"No reference set ({path}). "
                  f"Use `agent-eval benchmark set --tcr 78 --gate A=0.75`.")
            return 0
        if getattr(args, "as_json", False):
            print(json.dumps(ref, indent=2, ensure_ascii=False))
        else:
            print(f"Reference ({path}):\n{_fmt(ref)}")
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
        if args.from_results:
            try:
                patch = _from_results(args.from_results)
            except ValueError as exc:
                print(f"❌ {exc}")
                return 1
        gates: dict = {}
        for spec in args.gate or []:
            if "=" not in spec:
                print(f"❌ --gate expects X=0.75, got {spec!r}")
                return 1
            gk, gv = spec.split("=", 1)
            try:
                gates[gk.strip().upper()] = float(gv)
            except ValueError:
                print(f"❌ --gate value not a number: {spec!r}")
                return 1
        if gates:
            patch.setdefault("gate_scores", {}).update(gates)
        if args.tcr is not None:
            patch["tcr_pct"] = args.tcr
        if args.accuracy is not None:
            patch["accuracy_pct"] = args.accuracy
        for k in ("label", "source", "note"):
            if getattr(args, k, None) is not None:
                patch[k] = getattr(args, k)
        if not patch:
            print("Nothing to set. See `agent-eval benchmark set -h`.")
            return 1
        resolved = save_reference(patch, path)
        print(f"Wrote {path}:\n{_fmt(resolved)}")
        return 0

    print("Usage: agent-eval benchmark {set,show,clear}")
    return 1
