"""
SPEC-043 REQ-4 — production anomaly / low-confidence → golden-set candidate queue.

The primitives already exist (``dataset build --source`` · ``dataset promote`` ·
``StreamingEvaluator`` · ``AnomalyDetector`` · ``insights.review_queue``); what is
missing is an *automatic* trigger — a production failure or a low-confidence
answer landing in a review queue without a human running ``dataset build`` on a
schedule.

This module is that queue: an append-only JSON Lines log, same pattern as
``rca/decision_ledger.py`` / ``rca/recommendation_tracking.py`` (schemas differ).

Two entry kinds:

  - ``{"kind": "candidate", "id", "recorded_at", "question", "response",
       "trigger", "task_id?", "extra?", "reviewed": false}`` — appended by
       ``StreamingEvaluator`` when ``golden_candidate_sink`` is set and a task
       errors, sits below ``candidate_confidence_threshold``, or a periodic
       anomaly scan flags it.
  - ``{"kind": "review", "candidate_id", "recorded_at", "decision",
       "reviewed_by?"}`` — appended by ``agent-eval dataset review-candidates``.
       ``decision`` ∈ :data:`VALID_DECISIONS`.

Pure logging + counting. Nothing here promotes a case into a golden set — that
stays a human step (``review-candidates --accept`` → ``GoldenSetBuilder``).
Never raises on a corrupt line (it is skipped).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

VALID_DECISIONS = ("accept", "reject", "defer")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(log_path: Union[str, Path], entry: dict[str, Any]) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_candidate(
    log_path: Union[str, Path],
    *,
    question: str,
    response: str,
    trigger: str,
    task_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one ``candidate`` entry. Returns it (with the generated ``id``)."""
    entry: dict[str, Any] = {
        "kind": "candidate",
        "id": uuid.uuid4().hex[:12],
        "recorded_at": _now(),
        "question": str(question or ""),
        "response": str(response or ""),
        "trigger": str(trigger or "unknown"),
        "reviewed": False,
    }
    if task_id:
        entry["task_id"] = str(task_id)
    if isinstance(extra, dict) and extra:
        entry["extra"] = extra
    _append(log_path, entry)
    return entry


def record_candidate_review(
    log_path: Union[str, Path],
    *,
    candidate_id: str,
    decision: str,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    """Append one ``review`` entry. ``decision`` must be in :data:`VALID_DECISIONS`."""
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"decision must be one of {VALID_DECISIONS}, got {decision!r}"
        )
    entry: dict[str, Any] = {
        "kind": "review",
        "candidate_id": str(candidate_id),
        "recorded_at": _now(),
        "decision": decision,
    }
    if reviewed_by:
        entry["reviewed_by"] = str(reviewed_by)
    _append(log_path, entry)
    return entry


def load_candidates(log_path: Union[str, Path]) -> list[dict[str, Any]]:
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


def pending_candidates(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``candidate`` entries with no later ``review`` entry pointing at them."""
    reviewed = {
        e.get("candidate_id") for e in entries if e.get("kind") == "review"
    }
    return [
        e for e in entries
        if e.get("kind") == "candidate" and e.get("id") not in reviewed
    ]


def summarize_candidates(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold the queue into a snapshot.

    Returns ``{n_candidates, n_reviewed, n_pending, by_decision{}, by_trigger{},
    pending[]}``. Pure counting."""
    cands = [e for e in entries if e.get("kind") == "candidate"]
    reviews = [e for e in entries if e.get("kind") == "review"]
    pending = pending_candidates(entries)

    by_decision: dict[str, int] = {}
    for r in reviews:
        k = str(r.get("decision") or "?")
        by_decision[k] = by_decision.get(k, 0) + 1
    by_trigger: dict[str, int] = {}
    for c in cands:
        k = str(c.get("trigger") or "unknown").split(":", 1)[0]
        by_trigger[k] = by_trigger.get(k, 0) + 1

    return {
        "n_candidates": len(cands),
        "n_reviewed": len(reviews),
        "n_pending": len(pending),
        "by_decision": by_decision,
        "by_trigger": by_trigger,
        "pending": [
            {
                "id": p.get("id"),
                "recorded_at": p.get("recorded_at"),
                "trigger": p.get("trigger"),
                "question": str(p.get("question") or "")[:160],
                "task_id": p.get("task_id"),
            }
            for p in pending
        ],
    }
