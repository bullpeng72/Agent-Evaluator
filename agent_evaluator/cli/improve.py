"""
``agent-eval improve {plan,start,verify}`` (SPEC-041 P49) — the closed
improvement loop.

The insight layer already produces, for every failing / warning gate, a
concrete ``recommendations[].proposal`` (a prompt edit, a config change, or a
data fix) plus a falsifiable ``experiment`` prediction. This command turns that
into a tracked workflow:

    plan    — show the ordered improvement plan for a result file
    start   — register each proposal as an experiment in .aoo/experiments.jsonl
              and write an apply-me change stub to .aoo/improve/
    verify  — after the next run, score the open experiments predicted-vs-actual
              and (with --persist) resolve them + append to
              recommendation_outcomes.jsonl so future recommendations learn

No new logic — a thin wrapper around ``reporting.insights.build_insights`` and
``rca.experiments`` / ``rca.recommendation_tracking``. ``verify`` is
informational and never exits non-zero on a refuted prediction (HOTL: a wrong
prediction is data, not a build failure).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_evaluator.cli._utils import _supports_color

_COLOR = _supports_color()
G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""

_DEFAULT_LOG = ".aoo/experiments.jsonl"
_DEFAULT_OUT = ".aoo/improve"
_KIND_LABEL = {
    "prompt_edit": "prompt edit",
    "config_change": "config change",
    "data_fix": "data / eval-set fix",
}
_VERDICT_COLOR = {
    "confirmed": G, "partially_confirmed": Y, "refuted": RD,
    "inconclusive": D, "pending": D,
}


def _err(msg: str) -> str:
    return f"{RD}❌ {msg}{R}"


def _ok(msg: str) -> str:
    return f"{G}✅ {msg}{R}"


def _load_result(path_str: str | None) -> dict | None:
    if not path_str:
        return None
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


def _insights(current: dict, baseline: dict | None) -> dict[str, Any]:
    from agent_evaluator.reporting.insights import build_insights

    try:
        return build_insights(current, baseline) or {}
    except Exception as exc:  # pragma: no cover - build_insights never raises
        print(_err(f"Could not compute insights: {exc}"))
        return {}


def _proposals(ins: dict, gate_filter: str | None) -> list[dict[str, Any]]:
    """One row per recommendation that carries a proposal, richest gate first."""
    rows: list[dict[str, Any]] = []
    for rec in ins.get("recommendations") or []:
        prop = rec.get("proposal")
        if not prop:
            continue
        gate = str(rec.get("gate") or "")
        if gate_filter and gate.upper() != gate_filter.upper():
            continue
        exp = rec.get("experiment") or {}
        field = exp.get("field") or (
            (rec.get("shortfalls") or [{}])[0].get("field") if rec.get("shortfalls") else None
        )
        rows.append({
            "gate": gate,
            "gate_name": rec.get("gate_name") or f"Gate {gate}",
            "status": rec.get("status"),
            "kind": prop.get("kind"),
            "before": prop.get("before") or "",
            "after": prop.get("after") or "",
            "rationale": prop.get("rationale") or "",
            "evidence_task_ids": prop.get("evidence_task_ids") or [],
            "authored_by": prop.get("authored_by") or "template",
            "target_field": field,
            "predicted_delta": exp.get("predicted_gate_delta"),
            "recommended_tasks": exp.get("recommended_tasks"),
        })
    order = {"fail": 0, "warn": 1}
    rows.sort(key=lambda r: (order.get(r.get("status"), 9), r.get("gate")))
    return rows


def _exp_note(row: dict[str, Any]) -> str:
    rat = " ".join((row.get("rationale") or "").split())
    return f"[improve] Gate {row['gate']} {row.get('kind')}: {rat}"[:200]


def _print_plan(rows: list[dict[str, Any]], open_notes: set[str]) -> None:
    if not rows:
        print(f"{D}No proposals — every measured gate is at target, or the "
              f"result file has no failure clusters to act on.{R}")
        return
    print(f"{B}Improvement plan — {len(rows)} proposal(s){R}\n")
    for i, r in enumerate(rows, 1):
        pd = r.get("predicted_delta")
        pd_s = f"  predicted Δ {pd:+.3f}" if isinstance(pd, (int, float)) else ""
        tracked = f"  {G}[experiment open]{R}" if _exp_note(r) in open_notes else ""
        sc = RD if r.get("status") == "fail" else Y
        print(f"{B}{i}. Gate {r['gate']} — {r['gate_name']}{R} "
              f"{sc}({r.get('status')}){R}{pd_s}{tracked}")
        print(f"   change type : {_KIND_LABEL.get(r.get('kind'), r.get('kind'))}"
              f"  ({r.get('authored_by')})")
        if r.get("target_field"):
            print(f"   target field: {r['target_field']}")
        print(f"   before: {D}{_clip(r['before'])}{R}")
        print(f"   after : {_clip(r['after'])}")
        print(f"   why   : {D}{_clip(r['rationale'], 220)}{R}")
        if r.get("evidence_task_ids"):
            print(f"   tasks : {', '.join(r['evidence_task_ids'])}")
        print()
    print(f"{D}Next: agent-eval improve start <result.json>  "
          f"(registers experiments + writes change stubs){R}")


def _clip(s: str, n: int = 160) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _stub_text(row: dict[str, Any], eid: str) -> str:
    return (
        f"# Improvement stub — Gate {row['gate']} ({row['gate_name']})\n\n"
        f"- experiment_id: {eid}\n"
        f"- change type: {_KIND_LABEL.get(row.get('kind'), row.get('kind'))}\n"
        f"- target field: {row.get('target_field') or '(gate score)'}\n"
        f"- predicted Δ: {row.get('predicted_delta')}\n"
        f"- evidence tasks: {', '.join(row.get('evidence_task_ids') or []) or '—'}\n\n"
        f"## Rationale\n\n{row.get('rationale')}\n\n"
        f"## Before\n\n```\n{row.get('before')}\n```\n\n"
        f"## After (apply this)\n\n```\n{row.get('after')}\n```\n\n"
        f"## Then\n\n"
        f"1. Apply the change above to your agent / decorator / eval set.\n"
        f"2. Re-run the evaluation to produce a new result JSON.\n"
        f"3. `agent-eval improve verify <new_result.json> --baseline "
        f"<this_result.json> --persist`\n"
    )


def _cmd_plan(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(getattr(args, "baseline", None))
    ins = _insights(current, baseline)
    rows = _proposals(ins, getattr(args, "gate", None))
    from agent_evaluator.rca.experiments import load_experiments

    open_notes = {
        str(e.get("note") or "")
        for e in load_experiments(args.log, status="open")
    }
    _print_plan(rows, open_notes)
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(getattr(args, "baseline", None))
    ins = _insights(current, baseline)
    rows = _proposals(ins, getattr(args, "gate", None))
    if not rows:
        print(f"{D}Nothing to start — no actionable proposals in {args.result_file}.{R}")
        return 0

    from agent_evaluator.rca.experiments import load_experiments, register_experiment

    existing = {
        (str(e.get("target_gate")), e.get("target_field"), str(e.get("note") or ""))
        for e in load_experiments(args.log, status="open")
    }
    out_dir = Path(args.out)
    if not args.yes:
        print(f"{B}Will register {len(rows)} experiment(s) in {args.log} "
              f"and write stubs to {out_dir}/{R}")
        print(f"{D}Re-run with --yes to proceed.{R}")
        _print_plan(rows, {n for _, _, n in existing})
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    registered = skipped = 0
    for r in rows:
        note = _exp_note(r)
        key = (r["gate"], r.get("target_field"), note)
        if key in existing:
            print(f"{D}skip  Gate {r['gate']} — matching open experiment exists{R}")
            skipped += 1
            continue
        pd = r.get("predicted_delta")
        row = register_experiment(
            args.log,
            target_gate=r["gate"],
            predicted_delta=float(pd) if isinstance(pd, (int, float)) else 0.05,
            target_field=r.get("target_field"),
            note=note,
            baseline_ref=args.result_file,
        )
        eid = row["experiment_id"]
        stub = out_dir / f"{r['gate']}_{r.get('kind', 'change')}_{eid}.md"
        stub.write_text(_stub_text(r, eid), encoding="utf-8")
        print(_ok(f"Gate {r['gate']}: {eid}  →  {stub}"))
        registered += 1

    print(f"\n{B}{registered} registered, {skipped} skipped.{R}")
    if registered:
        print(f"{D}Apply the stubs, re-run, then: agent-eval improve verify "
              f"<new_result.json> --baseline {args.result_file} --persist{R}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(args.baseline)
    if baseline is None:
        return 1

    from agent_evaluator.rca.experiments import (
        load_experiments,
        resolve_experiment,
        score_experiments,
    )

    open_exps = load_experiments(args.log, status="open")
    improve_exps = [
        e for e in open_exps if str(e.get("note") or "").startswith("[improve]")
    ] or open_exps
    if not improve_exps:
        print(f"{D}No open experiments in {args.log}.{R}")
        return 0

    scored = score_experiments(improve_exps, current, baseline, min_effect=args.min_effect)
    print(f"{B}{'GATE/FIELD':<32} {'PRED':>8} {'ACTUAL':>8} VERDICT{R}")
    outcome_log = Path(args.result_file).parent / "recommendation_outcomes.jsonl"
    persisted = 0
    for row in scored:
        tgt = str(row.get("target_gate") or "?")
        if row.get("target_field"):
            tgt += f".{row['target_field']}"
        pred, act = row.get("predicted_delta"), row.get("actual_delta")
        verdict = row.get("verdict", "inconclusive")
        vc = _VERDICT_COLOR.get(verdict, "")
        print(f"{tgt[:32]:<32} "
              f"{(f'{pred:+.3f}' if isinstance(pred, (int, float)) else '-'):>8} "
              f"{(f'{act:+.3f}' if isinstance(act, (int, float)) else '-'):>8} "
              f"{vc}{verdict}{R}")
        if args.persist and verdict in ("confirmed", "partially_confirmed", "refuted"):
            resolve_experiment(
                args.log, row["experiment_id"], actual_delta=act, verdict=verdict,
                note=f"improve verify vs {Path(args.baseline).name}",
            )
            _record_outcome(outcome_log, row, args.baseline, baseline, current)
            persisted += 1
    if args.persist:
        print(_ok(f"Resolved {persisted} experiment(s); appended outcomes to {outcome_log}"))
    else:
        print(f"{D}Dry run — pass --persist to resolve experiments and log outcomes.{R}")
    return 0


def _record_outcome(
    outcome_log: Path, row: dict[str, Any], baseline_name: str,
    baseline: dict, current: dict,
) -> None:
    try:
        from agent_evaluator.rca.recommendation_tracking import record_recommendation_outcome

        record_recommendation_outcome(
            outcome_log,
            recommendation_id=f"improve:{row.get('experiment_id')}",
            target_gate=str(row.get("target_gate") or ""),
            before=baseline,
            after=current,
            target_field=row.get("target_field") or None,
            note=f"improve loop, predicted {row.get('predicted_delta')}, "
                 f"verdict {row.get('verdict')} (vs {baseline_name})",
        )
    except Exception:  # pragma: no cover - defensive
        pass


def build_improve_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "improve",
        help="Closed improvement loop: plan / start / verify proposals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Turn the insight layer's per-gate proposals into a tracked\n"
            "improvement workflow. `plan` shows them, `start` registers each as\n"
            "an experiment and writes an apply-me stub, `verify` scores the\n"
            "prediction once a new run exists.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval improve plan results/v3.json --baseline results/v2.json\n"
            "  agent-eval improve start results/v3.json --yes\n"
            "  agent-eval improve verify results/v4.json --baseline results/v3.json "
            "--persist\n"
        ),
    )
    isub = p.add_subparsers(dest="improve_command", metavar="{plan,start,verify}")

    pl = isub.add_parser("plan", help="Show the ordered improvement plan")
    pl.add_argument("result_file", help="Evaluation result JSON to plan from")
    pl.add_argument("--baseline", default=None, metavar="PATH",
                    help="Prior result JSON (enables baseline-aware proposals)")
    pl.add_argument("--gate", default=None, metavar="X", help="Only this Gate (A-G)")
    pl.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")

    st = isub.add_parser("start", help="Register experiments + write change stubs")
    st.add_argument("result_file", help="Evaluation result JSON to act on")
    st.add_argument("--baseline", default=None, metavar="PATH", help="Prior result JSON")
    st.add_argument("--gate", default=None, metavar="X", help="Only this Gate (A-G)")
    st.add_argument("--out", default=_DEFAULT_OUT, metavar="DIR",
                    help=f"Where to write change stubs (default: {_DEFAULT_OUT})")
    st.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")
    st.add_argument("--yes", "-y", action="store_true", help="Actually write (no dry run)")

    vf = isub.add_parser("verify", help="Score open experiments against a new run")
    vf.add_argument("result_file", help="New evaluation result JSON")
    vf.add_argument("--baseline", required=True, metavar="PATH",
                    help="The result the change was made against")
    vf.add_argument("--persist", action="store_true",
                    help="Resolve experiments + append to recommendation_outcomes.jsonl")
    vf.add_argument("--min-effect", type=float, default=0.02, dest="min_effect",
                    metavar="D", help="|delta| below this is noise (default: 0.02)")
    vf.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")


def cmd_improve(args: argparse.Namespace) -> int:
    handlers = {"plan": _cmd_plan, "start": _cmd_start, "verify": _cmd_verify}
    cmd = getattr(args, "improve_command", None)
    handler = handlers.get(cmd) if cmd is not None else None
    if handler is None:
        print(_err("Specify: agent-eval improve {plan,start,verify}"))
        print(f"{D}For details: agent-eval improve --help{R}")
        return 1
    return handler(args)
