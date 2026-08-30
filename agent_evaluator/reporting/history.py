"""
agent_evaluator.reporting.history
=====================================
Longitudinal view (P13) — scan sibling result JSON files in a directory and
summarise how the Gate scores and TCR have moved over the last N runs.

A single static HTML report is point-in-time: it can't say "Gate D has dropped
three runs in a row". This module gives the report generator that context
without a database — it just reads the ``*.json`` files already sitting next to
the current result.

Pure data + stdlib only. Never raises on a bad file — it is skipped.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_GATES = "ABCDEFG"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _tcr_from(data: dict[str, Any]) -> float | None:
    am = data.get("accuracy_metrics") or {}
    tcr = am.get("tcr")
    if isinstance(tcr, dict):
        tcr = tcr.get("tcr")
    if isinstance(tcr, (int, float)):
        return float(tcr)
    tasks = [t for t in (data.get("tasks") or []) if isinstance(t, dict)]
    comps = [t.get("completion_score") for t in tasks]
    comps = [c for c in comps if isinstance(c, (int, float))]
    return (sum(comps) / len(comps) * 100.0) if comps else None


def scan_history(
    results_dir: str | Path,
    *,
    limit: int = 20,
    exclude: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return ``[{file, timestamp, tcr, gate_scores{A..G}, overall}]`` for the
    result JSON files in ``results_dir``, oldest first, capped to the newest
    ``limit``. ``exclude`` (a path) is skipped — pass the current result file.
    """
    d = Path(results_dir)
    if not d.is_dir():
        return []
    excl = Path(exclude).resolve() if exclude else None
    rows: list[dict[str, Any]] = []
    for path in d.glob("*.json"):
        if path.name in ("baseline.json", "recommendation_outcomes.jsonl"):
            continue
        if excl and path.resolve() == excl:
            continue
        data = _load(path)
        if data is None:
            continue
        hg = (data.get("extra_metrics") or {}).get("harness_groups") or {}
        if not hg:
            continue
        gate_scores = {
            g: (hg.get(g) or {}).get("score")
            for g in _GATES
            if isinstance((hg.get(g) or {}).get("score"), (int, float))
        }
        if not gate_scores:
            continue
        rows.append({
            "file": path.name,
            "timestamp": data.get("timestamp") or "",
            "tcr": _tcr_from(data),
            "gate_scores": gate_scores,
            "overall": (hg.get("overall") or {}).get("score"),
        })
    rows.sort(key=lambda r: (r["timestamp"], r["file"]))
    return rows[-limit:]


def trend_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-Gate direction over the scanned history.

    ``consecutive_decline`` counts, from the most recent run backwards, how many
    times in a row the score went down (a small tolerance absorbs noise).
    ``slope`` is a plain first-to-last delta — not a regression, just direction.
    """
    out: dict[str, Any] = {"n_runs": len(history), "gates": {}}
    if len(history) < 2:
        return out
    tol = 0.005
    for g in _GATES:
        series = [
            r["gate_scores"].get(g) for r in history
            if isinstance(r["gate_scores"].get(g), (int, float))
        ]
        if len(series) < 2:
            continue
        dec = 0
        # count trailing declines: consecutive points from the newest backwards
        for i in range(len(series) - 1, 0, -1):
            if series[i] < series[i - 1] - tol:
                dec += 1
            else:
                break
        out["gates"][g] = {
            "first": round(series[0], 4),
            "last": round(series[-1], 4),
            "slope": round(series[-1] - series[0], 4),
            "consecutive_decline": dec,
        }
    return out


def load_change_ledger(
    results_dir: str | Path, *, limit: int = 20,
) -> list[dict[str, Any]]:
    """Read ``recommendation_outcomes.jsonl`` (the append-only log written by
    ``rca.record_recommendation_outcome()``) into a browsable list — "which
    change moved which Gate". Newest first. Empty when the file is absent."""
    path = Path(results_dir) / "recommendation_outcomes.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    except OSError:
        return []
    out.reverse()
    return out[:limit]
