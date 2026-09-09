"""
SPEC-043 REQ-3 — deploy-decision ledger.

``agent-eval gate`` produces the *evidence* (exit code, verdict, gate scores)
but nothing records the *decision* a human made on it — who accepted / held /
overrode / rejected, on what grounds, when. This module is that record: an
append-only JSON Lines log, same pattern as
``rca/recommendation_tracking.py`` / ``.aoo/claims.jsonl`` (schemas differ).

Two entry kinds:

  - ``{"kind": "gate_run", "id", "recorded_at", "result_file", "agent_version",
       "exit_code", "verdict_level", "decision_ready", "undecided_reason?",
       "gate_scores"}`` — written by ``agent-eval gate --decision-log PATH``.
  - ``{"kind": "outcome", "gate_run_id", "recorded_at", "outcome",
       "decided_by", "rationale?"}`` — written by
       ``agent-eval decisions record``.

Pure logging + counting. No verdict, no ranking. Never raises on a corrupt
line (it is skipped).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

VALID_OUTCOMES = ("accepted", "held", "overridden", "rejected")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(log_path: Union[str, Path], entry: dict[str, Any]) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_gate_decision(
    log_path: Union[str, Path],
    *,
    result_file: str,
    agent_version: str | None,
    exit_code: int,
    verdict_level: str | None,
    decision_ready: bool | None,
    undecided_reason: str | None = None,
    gate_scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one ``gate_run`` entry. Returns it (with the generated ``id``)."""
    entry: dict[str, Any] = {
        "kind": "gate_run",
        "id": uuid.uuid4().hex[:12],
        "recorded_at": _now(),
        "result_file": str(result_file),
        "agent_version": agent_version,
        "exit_code": int(exit_code),
        "verdict_level": verdict_level,
        "decision_ready": decision_ready,
        "gate_scores": gate_scores or {},
    }
    if undecided_reason:
        entry["undecided_reason"] = undecided_reason
    _append(log_path, entry)
    return entry


def record_decision_outcome(
    log_path: Union[str, Path],
    *,
    outcome: str,
    decided_by: str,
    rationale: str | None = None,
    gate_run_id: str | None = None,
) -> dict[str, Any]:
    """Append one ``outcome`` entry.

    ``outcome`` must be one of :data:`VALID_OUTCOMES`. When ``gate_run_id`` is
    omitted, it links to the most recent ``gate_run`` that has no outcome yet;
    ``ValueError`` if there is none.
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(
            f"outcome must be one of {VALID_OUTCOMES}, got {outcome!r}"
        )
    if gate_run_id is None:
        pending = [r["id"] for r in _pending_gate_runs(load_decisions(log_path))]
        if not pending:
            raise ValueError(
                "no pending gate_run in the ledger to attach this outcome to "
                "(pass --gate-run-id explicitly)"
            )
        gate_run_id = pending[-1]
    entry: dict[str, Any] = {
        "kind": "outcome",
        "gate_run_id": gate_run_id,
        "recorded_at": _now(),
        "outcome": outcome,
        "decided_by": str(decided_by),
    }
    if rationale:
        entry["rationale"] = rationale
    _append(log_path, entry)
    return entry


def load_decisions(log_path: Union[str, Path]) -> list[dict[str, Any]]:
    """Every entry in write order. Missing file -> ``[]``. Corrupt lines skipped."""
    path = Path(log_path)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _pending_gate_runs(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = {
        e.get("gate_run_id") for e in entries if e.get("kind") == "outcome"
    }
    return [
        e for e in entries
        if e.get("kind") == "gate_run" and e.get("id") not in resolved
    ]


def summarize_decisions(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold the ledger into a governance snapshot.

    Returns ``{n_gate_runs, n_outcomes, n_pending, pending[], by_outcome{},
    last{gate_run, outcome|None}}``. Pure counting."""
    gate_runs = [e for e in entries if e.get("kind") == "gate_run"]
    outcomes = [e for e in entries if e.get("kind") == "outcome"]
    by_id_outcome: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        rid = o.get("gate_run_id")
        if rid:
            by_id_outcome[rid] = o  # last outcome for a run wins
    pending = _pending_gate_runs(entries)

    by_outcome: dict[str, int] = {}
    for o in outcomes:
        k = str(o.get("outcome") or "?")
        by_outcome[k] = by_outcome.get(k, 0) + 1

    last: dict[str, Any] | None = None
    if gate_runs:
        gr = gate_runs[-1]
        last = {"gate_run": gr, "outcome": by_id_outcome.get(str(gr.get("id")))}

    return {
        "n_gate_runs": len(gate_runs),
        "n_outcomes": len(outcomes),
        "n_pending": len(pending),
        "pending": [
            {
                "id": p.get("id"),
                "recorded_at": p.get("recorded_at"),
                "exit_code": p.get("exit_code"),
                "verdict_level": p.get("verdict_level"),
                "result_file": p.get("result_file"),
            }
            for p in pending
        ],
        "by_outcome": by_outcome,
        "last": last,
    }
