"""
User-defined targets / SLOs (SPEC-041 P43).

A project can pin its *own* pass bar per gate and for TCR / accuracy / cost, so
every "below target" statement in the insight layer, the report and
``agent-eval gate`` measures against that bar instead of the built-in 0.7.

Format — ``.aoo/targets.json`` (all keys optional)::

    {
      "gate_default": 0.75,
      "gates": {"A": 0.85, "E": 0.95},
      "tcr_pct": 90,
      "accuracy_pct": 75,
      "cost_per_task_usd": 0.03,
      "note": "team SLO for the support agent"
    }

Pure stdlib; every reader tolerates a missing / malformed file (returns ``None``).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_TARGETS_PATH = ".aoo/targets.json"

_GATE_KEYS = set("ABCDEFG")
_SCALAR_KEYS = {"gate_default", "tcr_pct", "accuracy_pct", "cost_per_task_usd"}


def _coerce(d: Any) -> dict[str, Any] | None:
    """Keep only recognised keys, coerce to float, drop anything out of range."""
    if not isinstance(d, dict):
        return None
    out: dict[str, Any] = {}
    for k in _SCALAR_KEYS:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
    gates = d.get("gates")
    if isinstance(gates, dict):
        g: dict[str, float] = {}
        for gk, gv in gates.items():
            if str(gk).upper() in _GATE_KEYS and isinstance(gv, (int, float)):
                v = float(gv)
                if 0.0 < v <= 1.0:
                    g[str(gk).upper()] = v
        if g:
            out["gates"] = g
    if isinstance(d.get("note"), str):
        out["note"] = d["note"][:200]
    return out or None


def load_targets(path: str | Path = DEFAULT_TARGETS_PATH) -> dict[str, Any] | None:
    """Read + validate the targets file. ``None`` when absent or unusable."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        return _coerce(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # pragma: no cover - defensive
        return None


def save_targets(
    targets: dict[str, Any], path: str | Path = DEFAULT_TARGETS_PATH,
) -> dict[str, Any]:
    """Merge ``targets`` into the file (shallow; ``gates`` is deep-merged) and
    write it back. Returns the resolved dict."""
    cur = load_targets(path) or {}
    merged: dict[str, Any] = dict(cur)
    for k, v in (targets or {}).items():
        if k == "gates" and isinstance(v, dict):
            merged.setdefault("gates", {})
            merged["gates"] = {**merged.get("gates", {}), **v}
        else:
            merged[k] = v
    resolved = _coerce(merged) or {}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(resolved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return resolved


def gate_target(targets: dict[str, Any] | None, gate: str, default: float = 0.7) -> float:
    """The pass bar for ``gate`` — per-gate override, else ``gate_default``, else
    the SDK default."""
    if not targets:
        return default
    per = (targets.get("gates") or {}).get(str(gate).upper())
    if isinstance(per, (int, float)):
        return float(per)
    gd = targets.get("gate_default")
    return float(gd) if isinstance(gd, (int, float)) else default


def is_user_defined(targets: dict[str, Any] | None) -> bool:
    return bool(targets) and (
        "gates" in targets or "gate_default" in targets
        or "tcr_pct" in targets or "accuracy_pct" in targets
        or "cost_per_task_usd" in targets
    )
