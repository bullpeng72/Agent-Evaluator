"""
SPEC-043 REQ-3 — `agent-eval decisions` (deploy-decision ledger).

Thin CLI over ``agent_evaluator.rca.decision_ledger``:

  - ``decisions list <log> [--pending] [--json]``
  - ``decisions record <log> --outcome ... --by ... [--rationale ...] [--gate-run-id ...]``
"""
from __future__ import annotations

import argparse
import json
import sys

_G, _Y, _RD, _D, _B, _R = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m",
)


def cmd_decisions(args: argparse.Namespace) -> int:
    sub = getattr(args, "decisions_command", None)
    if sub == "list":
        return _cmd_list(args)
    if sub == "record":
        return _cmd_record(args)
    print(
        "usage: agent-eval decisions {list,record} <log> ...\n"
        "  list    — show gate runs + recorded outcomes (--pending for open ones)\n"
        "  record  — append a human decision (--outcome / --by / --rationale)",
        file=sys.stderr,
    )
    return 1


def _cmd_list(args: argparse.Namespace) -> int:
    from agent_evaluator.rca.decision_ledger import load_decisions, summarize_decisions

    entries = load_decisions(args.log)
    summary = summarize_decisions(entries)
    if getattr(args, "as_json", False):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not summary["n_gate_runs"]:
        print(f"{_D}No gate runs in {args.log}.{_R}")
        return 0

    if getattr(args, "pending", False):
        pend = summary["pending"]
        if not pend:
            print(f"{_G}✓ No gate runs awaiting a decision.{_R}")
            return 0
        print(f"{_Y}{_B}{len(pend)} gate run(s) awaiting a human decision:{_R}")
        for p in pend:
            print(
                f"  {p['id']}  exit {p['exit_code']}  {p.get('verdict_level') or '—'}  "
                f"{p.get('recorded_at', '')[:19]}  {p.get('result_file', '')}"
            )
        print(
            f"\n{_D}Record one with: agent-eval decisions record {args.log} "
            f"--outcome <accepted|held|overridden|rejected> --by <name> "
            f"[--gate-run-id <id>]{_R}"
        )
        return 0

    # full view
    outcomes_by_run: dict[str, dict] = {}
    for e in entries:
        if e.get("kind") == "outcome" and e.get("gate_run_id"):
            outcomes_by_run[e["gate_run_id"]] = e
    print(f"{_B}Deploy-decision ledger — {args.log}{_R}")
    print(
        f"{summary['n_gate_runs']} gate run(s), {summary['n_outcomes']} decision(s), "
        f"{summary['n_pending']} pending. "
        + (", ".join(f"{k}: {v}" for k, v in summary["by_outcome"].items()) or "")
    )
    print()
    for e in entries:
        if e.get("kind") != "gate_run":
            continue
        oc = outcomes_by_run.get(str(e.get("id")))
        _oc_s = (
            f"{_G}{oc['outcome']}{_R} by {oc.get('decided_by', '?')}"
            + (f" — {oc['rationale']}" if oc.get("rationale") else "")
            if oc else f"{_Y}PENDING{_R}"
        )
        print(
            f"  {e['id']}  exit {e.get('exit_code')}  "
            f"{e.get('verdict_level') or '—'}  {e.get('recorded_at', '')[:19]}\n"
            f"      {_oc_s}"
        )
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    from agent_evaluator.rca.decision_ledger import record_decision_outcome

    try:
        entry = record_decision_outcome(
            args.log,
            outcome=args.outcome,
            decided_by=args.decided_by,
            rationale=getattr(args, "rationale", None),
            gate_run_id=getattr(args, "gate_run_id", None),
        )
    except ValueError as exc:
        print(f"{_RD}✗ {exc}{_R}", file=sys.stderr)
        return 1

    print(
        f"{_G}✓ Recorded: {entry['outcome']} on gate run {entry['gate_run_id']} "
        f"by {entry['decided_by']}.{_R}"
    )
    return 0
