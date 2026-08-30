"""
agent_evaluator.rca.experiments
==================================
Phase 4 (improvement engine, closed-loop learning) — SPEC-041 P27.

A registered *experiment* is a falsifiable hypothesis about a change you are
about to make: "I expect Gate A's ``avg_subtask_completion`` to rise by +0.08".
It is written append-only to ``.aoo/experiments.jsonl`` (same JSON Lines pattern
as ``gates/team_concurrency.py``'s ``claims.jsonl`` and
``rca/recommendation_tracking.py``'s outcome log).

When a later run supplies a *baseline*, :func:`score_experiments` re-checks each
open hypothesis with :func:`agent_evaluator.rca.verify.verify_recommendation_outcome`
and reports ``confirmed`` / ``partially_confirmed`` / ``refuted`` /
``inconclusive`` — the prediction held, held in direction only, went the wrong
way, or could not be measured. **No causal claim** (other changes may have
ridden along, per Chapter 31 §31.2) and **no ranking** — the same boundary
``rca/verify.py`` drew. Scoring is a pure function; persistence of a resolution
is an explicit :func:`resolve_experiment` call (``agent-eval experiment score``),
never a side effect of building a report.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from agent_evaluator.rca.verify import verify_recommendation_outcome

_MIN_EFFECT = 0.02  # |delta| below this is treated as measurement noise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def register_experiment(
    log_path: Union[str, Path],
    *,
    target_gate: str,
    predicted_delta: float,
    target_field: str | None = None,
    note: str | None = None,
    baseline_ref: str | None = None,
) -> dict[str, Any]:
    """Append one open hypothesis to ``log_path`` and return the written row.

    Args:
        log_path: ``.aoo/experiments.jsonl`` path — parent dirs are created.
        target_gate: the Gate the change targets (``"A"``–``"G"`` or a
            registered custom id).
        predicted_delta: expected change in the Gate score, or in
            ``target_field`` when given (signed — negative = expected drop).
        target_field: optional ``details`` key the prediction is really about.
        note: free-text description of the change being made.
        baseline_ref: optional path/label of the run this prediction is measured
            against (informational).
    """
    eid = "exp-" + hashlib.sha1(  # noqa: S324 - short id, not security
        f"{target_gate}|{target_field}|{_now()}|{predicted_delta}".encode()
    ).hexdigest()[:10]
    row: dict[str, Any] = {
        "experiment_id": eid,
        "registered_at": _now(),
        "status": "open",
        "target_gate": str(target_gate),
        "target_field": target_field,
        "predicted_delta": round(float(predicted_delta), 6),
        "note": note,
        "baseline_ref": baseline_ref,
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_experiments(
    log_path: Union[str, Path], *, status: str | None = None,
) -> list[dict[str, Any]]:
    """Read ``log_path`` and fold rows by ``experiment_id`` (last write wins,
    registration fields preserved). Unlike the recommendation-outcome log, an
    experiment *does* carry mutable state (open → resolved), like
    ``claims.jsonl``. Corrupt lines are skipped. Missing file → ``[]``.

    Args:
        status: if given, only return experiments whose folded status matches.
    """
    path = Path(log_path)
    if not path.exists():
        return []
    folded: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = row.get("experiment_id")
                if not eid:
                    continue
                if eid not in folded:
                    folded[eid] = {}
                    order.append(eid)
                folded[eid].update(row)
    except OSError:
        return []
    out = [folded[e] for e in order]
    if status is not None:
        out = [e for e in out if e.get("status") == status]
    return out


def _actual_delta(vr: dict[str, Any], target_field: str | None) -> float | None:
    if target_field and isinstance(vr.get("target_field_result"), dict):
        return vr["target_field_result"].get("delta")
    return vr.get("gate_delta")


def _prediction_verdict(
    predicted: float, actual: float | None, *, min_effect: float = _MIN_EFFECT,
) -> str:
    """confirmed / partially_confirmed / refuted / inconclusive — did the signed
    prediction hold?"""
    if actual is None:
        return "inconclusive"
    dp, da = _sign(predicted), _sign(actual)
    if dp == 0:
        return "confirmed" if abs(actual) < min_effect else "inconclusive"
    if abs(actual) < min_effect:
        return "refuted"  # predicted a real move, saw noise
    if da != dp:
        return "refuted"
    if abs(actual) >= 0.5 * abs(predicted):
        return "confirmed"
    return "partially_confirmed"


def score_experiments(
    open_experiments: list[dict[str, Any]],
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    min_effect: float = _MIN_EFFECT,
) -> list[dict[str, Any]]:
    """Pure — for each open experiment, compare predicted vs actual movement of
    the target Gate/field between ``baseline`` and ``current``. Returns a scored
    copy (does not write). With ``baseline=None`` every verdict is ``pending``."""
    scored: list[dict[str, Any]] = []
    for exp in open_experiments:
        gate = str(exp.get("target_gate") or "")
        field = exp.get("target_field")
        predicted = float(exp.get("predicted_delta") or 0.0)
        row = {
            "experiment_id": exp.get("experiment_id"),
            "target_gate": gate,
            "target_field": field,
            "predicted_delta": round(predicted, 6),
            "note": exp.get("note"),
            "status": exp.get("status", "open"),
        }
        if baseline is None:
            row.update(actual_delta=None, gate_delta=None, verdict="pending")
            scored.append(row)
            continue
        try:
            vr = verify_recommendation_outcome(
                baseline, current, target_gate=gate, target_field=field or None,
            )
        except Exception:  # pragma: no cover - defensive
            row.update(actual_delta=None, gate_delta=None, verdict="inconclusive")
            scored.append(row)
            continue
        actual = _actual_delta(vr, field)
        row.update(
            actual_delta=None if actual is None else round(float(actual), 6),
            gate_delta=vr.get("gate_delta"),
            before_score=vr.get("before_score"),
            after_score=vr.get("after_score"),
            verdict=_prediction_verdict(predicted, actual, min_effect=min_effect),
        )
        scored.append(row)
    return scored


def resolve_experiment(
    log_path: Union[str, Path],
    experiment_id: str,
    *,
    actual_delta: float | None,
    verdict: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Append a resolution row (same ``experiment_id``, ``status="resolved"``).
    Idempotent-ish: re-resolving just appends another row that folds over the
    previous one."""
    row: dict[str, Any] = {
        "experiment_id": experiment_id,
        "resolved_at": _now(),
        "status": "resolved",
        "actual_delta": None if actual_delta is None else round(float(actual_delta), 6),
        "verdict": verdict,
    }
    if note is not None:
        row["note"] = note
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def recalibrated_delta(
    experiments: list[dict[str, Any]],
    target_gate: str,
    target_field: str | None,
    heuristic_delta: float,
) -> tuple[float, int]:
    """Blend a heuristic predicted Δ with the mean *actual* Δ of past resolved
    experiments for the same Gate/field whose verdict confirmed the direction.
    Needs ≥2 samples, else the heuristic is returned unchanged.

    Returns:
        ``(delta, n_samples)`` — ``n_samples`` is how many past outcomes fed the
        blend (0 when the heuristic passed through).
    """
    hits = [
        e.get("actual_delta")
        for e in experiments
        if e.get("status") == "resolved"
        and str(e.get("target_gate")) == str(target_gate)
        and e.get("target_field") == target_field
        and e.get("verdict") in ("confirmed", "partially_confirmed")
        and isinstance(e.get("actual_delta"), (int, float))
    ]
    if len(hits) < 2:
        return round(float(heuristic_delta), 4), 0
    mean_actual = sum(hits) / len(hits)
    return round(0.5 * float(heuristic_delta) + 0.5 * mean_actual, 4), len(hits)
