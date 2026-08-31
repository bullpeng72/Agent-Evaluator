"""
External reference frame (SPEC-041 P53).

Every Agent-Evaluator verdict is otherwise absolute-threshold or vs-own-baseline,
so "is a TCR of 78% any good?" has no anchor. A project can pin a *reference
distribution* — public benchmark stats, its own best historical runs, or a
competitor eval — and the insight layer then reports where the current run sits
against it (percentile + gap to the frontier).

Format — ``.aoo/reference.json`` (all metric keys optional). A metric value may be

  * a number            — a single reference point ("the bar to beat")
  * a list of numbers   — a sample; percentiles are computed from it
  * a percentile dict    — ``{"p10": .., "p25": .., "p50": .., "p75": .., "p90": ..}``

::

    {
      "label": "support-rag-2026H1",
      "source": "team: best 20 runs, 2026-01..2026-06",
      "tcr_pct": {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91},
      "gate_scores": {"A": [0.71, 0.74, 0.77, 0.80, 0.83], "E": 0.95},
      "accuracy_pct": 75,
      "note": "..."
    }

Pure stdlib; every reader tolerates a missing / malformed file (returns ``None``).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_REFERENCE_PATH = ".aoo/reference.json"

_GATE_KEYS = set("ABCDEFG")
_PCTILE_KEYS = ("p10", "p25", "p50", "p75", "p90")
_METRIC_SCALARS = {"tcr_pct", "accuracy_pct"}


# --------------------------------------------------------------------------- #
# entry = one metric's reference: number | list[number] | {p10..p90}
# --------------------------------------------------------------------------- #
def _clean_entry(v: Any) -> Any:
    """Coerce one metric entry to number | sorted list[float] | pctile dict."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        nums = sorted(
            float(x) for x in v
            if isinstance(x, (int, float)) and not isinstance(x, bool)
        )
        return nums if len(nums) >= 2 else None
    if isinstance(v, dict):
        d = {
            k: float(v[k]) for k in _PCTILE_KEYS
            if isinstance(v.get(k), (int, float)) and not isinstance(v.get(k), bool)
        }
        return d if "p50" in d else None
    return None


def _coerce(d: Any) -> dict[str, Any] | None:
    if not isinstance(d, dict):
        return None
    out: dict[str, Any] = {}
    for k in ("label", "source", "note"):
        if isinstance(d.get(k), str):
            out[k] = d[k][:200]
    for k in _METRIC_SCALARS:
        e = _clean_entry(d.get(k))
        if e is not None:
            out[k] = e
    gs = d.get("gate_scores")
    if isinstance(gs, dict):
        g: dict[str, Any] = {}
        for gk, gv in gs.items():
            if str(gk).upper() in _GATE_KEYS:
                e = _clean_entry(gv)
                if e is not None:
                    g[str(gk).upper()] = e
        if g:
            out["gate_scores"] = g
    return out if (out.get("tcr_pct") or out.get("gate_scores")
                   or out.get("accuracy_pct")) else None


def load_reference(
    path: str | Path = DEFAULT_REFERENCE_PATH,
) -> dict[str, Any] | None:
    """Read + validate the reference file. ``None`` when absent or unusable."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        return _coerce(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # pragma: no cover - defensive
        return None


def save_reference(
    patch: dict[str, Any], path: str | Path = DEFAULT_REFERENCE_PATH,
) -> dict[str, Any]:
    """Merge ``patch`` into the file (``gate_scores`` deep-merged) and write it
    back. Returns the resolved dict."""
    cur = load_reference(path) or {}
    merged: dict[str, Any] = dict(cur)
    for k, v in (patch or {}).items():
        if k == "gate_scores" and isinstance(v, dict):
            merged["gate_scores"] = {**merged.get("gate_scores", {}), **v}
        else:
            merged[k] = v
    resolved = _coerce(merged) or {}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(resolved, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return resolved


def percentiles_from_values(vals: list[float]) -> dict[str, float]:
    """The 5-point summary used when a reference metric is stored as a raw list."""
    s = sorted(float(v) for v in vals)
    n = len(s)

    def _q(frac: float) -> float:
        if n == 1:
            return s[0]
        pos = frac * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)

    return {"p10": round(_q(0.10), 4), "p25": round(_q(0.25), 4),
            "p50": round(_q(0.50), 4), "p75": round(_q(0.75), 4),
            "p90": round(_q(0.90), 4)}


def _pctile_map(entry: Any) -> dict[str, float] | None:
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, list):
        return percentiles_from_values(entry)
    return None


def reference_median(entry: Any) -> float | None:
    """The reference's central value: the number itself, or p50."""
    if isinstance(entry, (int, float)) and not isinstance(entry, bool):
        return float(entry)
    pm = _pctile_map(entry)
    return pm.get("p50") if pm else None


def reference_frontier(entry: Any) -> float | None:
    """The reference's strong end: p90 for a distribution, else the point."""
    pm = _pctile_map(entry)
    if pm:
        return pm.get("p90", pm.get("p50"))
    return float(entry) if isinstance(entry, (int, float)) else None


def percentile_of(value: float, entry: Any) -> int | None:
    """Where ``value`` sits within the reference, 0–100. ``None`` for a bare
    reference point (a single number carries no distribution)."""
    if not isinstance(value, (int, float)):
        return None
    if isinstance(entry, list) and entry:
        below = sum(1 for x in entry if x < value)
        eq = sum(1 for x in entry if x == value)
        return int(round((below + 0.5 * eq) / len(entry) * 100))
    pm = entry if isinstance(entry, dict) else None
    if pm:
        pts = sorted((int(k[1:]) / 100.0, v) for k, v in pm.items())
        if value <= pts[0][1]:
            return int(round(pts[0][0] * 100))
        if value >= pts[-1][1]:
            return int(round(pts[-1][0] * 100))
        for (q0, v0), (q1, v1) in zip(pts, pts[1:]):
            if v0 <= value <= v1 and v1 > v0:
                frac = (value - v0) / (v1 - v0)
                return int(round((q0 + (q1 - q0) * frac) * 100))
    return None


def is_defined(reference: dict[str, Any] | None) -> bool:
    return bool(reference) and bool(
        reference.get("tcr_pct") or reference.get("gate_scores")
        or reference.get("accuracy_pct")
    )
