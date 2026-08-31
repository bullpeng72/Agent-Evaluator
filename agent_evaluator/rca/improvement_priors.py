"""
Improvement priors (SPEC-041 P57) — cross-run learning.

``.aoo/experiments.jsonl`` and ``recommendation_outcomes.jsonl`` accumulate a
record of what was tried and whether it worked, but nothing synthesised them.
This module folds both logs into a per-``(gate, change-category)`` track record:
*"prompt edits to Gate A here: 4 of 6 confirmed, mean +0.08"* — a learned prior
that lets the recommendation layer say when a proposed change *type* has a poor
history for this project.

Pure counting + means over verdicts the existing ``rca.verify`` /
``rca.experiments`` machinery already produced. **No new judgement, no ranking
of recommendations against each other** — the same boundary
``rca/recommendation_tracking.py`` drew.
"""
from __future__ import annotations

import re
from typing import Any

_CATEGORIES = ("prompt_edit", "config_change", "data_fix", "other")

_CAT_HINTS = (
    ("config_change", re.compile(
        r"\b(config|retry|timeout|fault_tolerance|loop_detection|sla|"
        r"threshold|scope|guardrail|top_k|top-k|rerank|budget|parallel|cache)\b",
        re.I)),
    ("data_fix", re.compile(
        r"\b(ground[_ ]?truth|label|dataset|eval[- ]?set|question wording|"
        r"golden|annotation)\b", re.I)),
    ("prompt_edit", re.compile(
        r"\b(prompt|instruction|system message|few[- ]?shot|wording|"
        r"rephrase|grounding instruction|decompose|sub[- ]?step)\b", re.I)),
)

_CONFIRMED = {"confirmed", "partially_confirmed"}
_REFUTED = {"refuted"}


def _category_of(note: Any) -> str:
    """Bucket a change by its free-text note. ``[improve] Gate X kind: …`` (P49)
    is honoured first, then keyword hints, else ``"other"``."""
    s = str(note or "")
    m = re.search(r"\bGate\s+[A-G]\s+(prompt_edit|config_change|data_fix)\b", s)
    if m:
        return m.group(1)
    for cat, rx in _CAT_HINTS:
        if rx.search(s):
            return cat
    return "other"


def _rows_from_experiments(experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in experiments or []:
        if e.get("status") != "resolved" or not e.get("verdict"):
            continue
        out.append({
            "gate": str(e.get("target_gate") or "?"),
            "category": _category_of(e.get("note")),
            "verdict": str(e.get("verdict")),
            "delta": e.get("actual_delta"),
            "source": "experiment",
        })
    return out


def _rows_from_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for o in outcomes or []:
        if not o.get("verdict"):
            continue
        out.append({
            "gate": str(o.get("target_gate") or "?"),
            "category": _category_of(o.get("note") or o.get("recommendation_id")),
            "verdict": str(o.get("verdict")),
            "delta": o.get("gate_delta"),
            "source": "outcome",
        })
    return out


def _bucket_verdict(n: int, confirm_rate: float | None) -> str:
    if n < 2 or confirm_rate is None:
        return "insufficient_data"
    if confirm_rate >= 0.6:
        return "works_well"
    if confirm_rate <= 0.25:
        return "ineffective"
    return "mixed"


def synthesize_priors(
    experiments: list[dict[str, Any]] | None,
    outcomes: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Fold both logs into per-``(gate, category)`` track records.

    Args:
        experiments: ``rca.experiments.load_experiments(log)`` output.
        outcomes: ``rca.recommendation_tracking.load_recommendation_outcomes(log)``
            output.

    Returns:
        ``{by_bucket[], by_category{}, overall{}, note}`` or ``None`` when
        neither log has a resolved verdict.
    """
    rows = _rows_from_experiments(experiments or []) + _rows_from_outcomes(outcomes or [])
    if not rows:
        return None

    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["gate"], r["category"])
        b = buckets.setdefault(key, {
            "gate": r["gate"], "category": r["category"],
            "n": 0, "confirmed": 0, "refuted": 0, "deltas": [],
        })
        b["n"] += 1
        if r["verdict"] in _CONFIRMED:
            b["confirmed"] += 1
            if isinstance(r["delta"], (int, float)):
                b["deltas"].append(float(r["delta"]))
        elif r["verdict"] in _REFUTED:
            b["refuted"] += 1

    by_bucket: list[dict[str, Any]] = []
    for b in buckets.values():
        decisive = b["confirmed"] + b["refuted"]
        cr = round(b["confirmed"] / decisive, 2) if decisive else None
        md = round(sum(b["deltas"]) / len(b["deltas"]), 4) if b["deltas"] else None
        by_bucket.append({
            "gate": b["gate"],
            "category": b["category"],
            "n": b["n"],
            "confirmed": b["confirmed"],
            "refuted": b["refuted"],
            "confirm_rate": cr,
            "mean_confirmed_delta": md,
            "verdict": _bucket_verdict(decisive, cr),
        })
    by_bucket.sort(key=lambda x: (-x["n"], x["gate"], x["category"]))

    by_category: dict[str, dict[str, Any]] = {}
    for cat in _CATEGORIES:
        sub = [r for r in rows if r["category"] == cat]
        if not sub:
            continue
        dec = [r for r in sub if r["verdict"] in _CONFIRMED | _REFUTED]
        conf = [r for r in dec if r["verdict"] in _CONFIRMED]
        by_category[cat] = {
            "n": len(sub),
            "confirm_rate": round(len(conf) / len(dec), 2) if dec else None,
        }

    dec_all = [r for r in rows if r["verdict"] in _CONFIRMED | _REFUTED]
    conf_all = [r for r in dec_all if r["verdict"] in _CONFIRMED]
    overall = {
        "n": len(rows),
        "n_decisive": len(dec_all),
        "confirm_rate": round(len(conf_all) / len(dec_all), 2) if dec_all else None,
    }

    weak = [b for b in by_bucket
            if b["verdict"] == "ineffective" and b["n"] >= 2]
    strong = [b for b in by_bucket if b["verdict"] == "works_well"]
    bits = [f"{len(rows)} past change(s) across {len(buckets)} gate/category buckets"]
    if strong:
        s = strong[0]
        bits.append(f"{s['category'].replace('_', ' ')} on Gate {s['gate']} has the "
                    f"best record ({s['confirm_rate']:.0%}, n={s['n']})")
    if weak:
        w = weak[0]
        bits.append(f"{w['category'].replace('_', ' ')} on Gate {w['gate']} has a poor "
                    f"record here ({w['confirm_rate']:.0%}, n={w['n']}) — deprioritise")

    return {
        "by_bucket": by_bucket,
        "by_category": by_category,
        "overall": overall,
        "note": "; ".join(bits),
    }


def prior_for(
    priors: dict[str, Any] | None, gate: str, category: str,
) -> dict[str, Any] | None:
    """The ``(gate, category)`` bucket, or the category-level rollup, or None."""
    if not priors:
        return None
    for b in priors.get("by_bucket") or []:
        if b["gate"] == str(gate) and b["category"] == category:
            return b
    cat = (priors.get("by_category") or {}).get(category)
    if cat:
        return {"gate": str(gate), "category": category, "n": cat["n"],
                "confirm_rate": cat["confirm_rate"], "mean_confirmed_delta": None,
                "verdict": _bucket_verdict(cat["n"], cat["confirm_rate"]),
                "scope": "category"}
    return None
