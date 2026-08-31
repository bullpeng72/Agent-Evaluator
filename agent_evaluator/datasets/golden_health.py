"""
Golden-set health (SPEC-041 P58).

``dataset promote`` adds cases to a golden set; nothing retires a case that has
passed for many runs, checks that the golden set still exercises the failure
modes actually being seen, or flags near-duplicates. This module answers those:

    assess_golden_health(golden, result_data, *, history_dir=None) -> {
        n_cases, coverage_pct, uncovered_failure_modes[], stale_cases[],
        redundant_cases[], note
    }

Pure stdlib. ``uncovered_failure_modes`` is the load-bearing signal — a golden
set that no longer catches the mode you are regressing on is a blind spot.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_STOP = frozenset(
    "the a an of to in on at for and or but is are was were be to it its this that "
    "with as by from into how what when where why do does did i we you they what".split()
)


def _cwords(text: Any) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if w not in _STOP and len(w) > 2}


def _jacc(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_golden_cases(golden: Any) -> list[dict[str, Any]]:
    """Accept a bare list, ``{items:[…]}`` (``merge_to_golden``), ``{cases:[…]}``,
    or a path to any of those."""
    if isinstance(golden, (str, Path)):
        try:
            golden = json.loads(Path(golden).read_text(encoding="utf-8"))
        except Exception:
            return []
    if isinstance(golden, list):
        return [c for c in golden if isinstance(c, dict)]
    if isinstance(golden, dict):
        for k in ("items", "cases", "golden_cases", "data", "candidates"):
            if isinstance(golden.get(k), list):
                return [c for c in golden[k] if isinstance(c, dict)]
    return []


def _case_q(c: dict[str, Any]) -> str:
    return str(c.get("question") or c.get("input") or c.get("prompt") or "")


def _task_fails(t: dict[str, Any]) -> bool:
    if not t.get("success", True):
        return True
    acc = t.get("accuracy_score")
    comp = t.get("completion_score")
    return (isinstance(acc, (int, float)) and acc < 0.7) or \
           (isinstance(comp, (int, float)) and comp < 0.4)


def assess_golden_health(
    golden: Any, result_data: dict[str, Any], *, history_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Assess a golden set against a current evaluation result.

    Args:
        golden: golden dataset (list / ``{items}`` / ``{cases}``) or a path.
        result_data: a loaded result JSON (needs ``tasks``; uses
            ``extra_metrics.insights.failure_taxonomy`` when present).
        history_dir: optional sibling-results directory — enables a
            ``passed_streak`` per stale case (consecutive runs the matching
            question passed).

    Returns:
        The health dict, or ``None`` when the golden set has no usable cases.
    """
    cases = load_golden_cases(golden)
    if not cases:
        return None
    tasks = [t for t in (result_data.get("tasks") or []) if isinstance(t, dict)]
    ins = ((result_data.get("extra_metrics") or {}).get("insights") or {})

    case_words = [(_case_q(c), _cwords(_case_q(c))) for c in cases]

    # 1. redundant near-duplicate cases -------------------------------------- #
    redundant: list[dict[str, Any]] = []
    seen: list[int] = []
    for i, (qi, wi) in enumerate(case_words):
        if not wi:
            continue
        for j in seen:
            if _jacc(wi, case_words[j][1]) >= 0.85:
                redundant.append({"case_index": i, "duplicate_of": j,
                                  "question": qi[:120]})
                break
        else:
            seen.append(i)

    # 2. stale / low-value cases ---------------------------------------------- #
    def _match_task(w: set[str]) -> dict[str, Any] | None:
        best, best_s = None, 0.0
        for t in tasks:
            s = _jacc(w, _cwords(t.get("question")))
            if s > best_s:
                best, best_s = t, s
        return best if best_s >= 0.6 else None

    hist_runs: list[dict[str, Any]] = []
    if history_dir:
        d = Path(history_dir)
        if d.is_dir():
            for p in sorted(d.glob("*.json")):
                if p.name == "baseline.json":
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                rt = [x for x in (data.get("tasks") or []) if isinstance(x, dict)]
                if rt:
                    hist_runs.append({"ts": data.get("timestamp") or p.name, "tasks": rt})
            hist_runs.sort(key=lambda r: str(r["ts"]))

    stale: list[dict[str, Any]] = []
    for i, (qi, wi) in enumerate(case_words):
        if not wi:
            continue
        mt = _match_task(wi)
        if mt is None or _task_fails(mt):
            continue
        acc = mt.get("accuracy_score")
        easy = isinstance(acc, (int, float)) and acc >= 0.9
        streak = 1
        for run in reversed(hist_runs):
            rm = max(
                (x for x in run["tasks"]),
                key=lambda x: _jacc(wi, _cwords(x.get("question"))),
                default=None,
            )
            if rm and _jacc(wi, _cwords(rm.get("question"))) >= 0.6 and not _task_fails(rm):
                streak += 1
            else:
                break
        if easy or streak >= 4:
            stale.append({
                "case_index": i, "question": qi[:120],
                "current_accuracy": round(float(acc), 3) if isinstance(acc, (int, float))
                else None,
                "passed_streak": streak,
                "reason": ("passed the last "
                           f"{streak} run(s)" if streak >= 4 else "currently trivial"),
            })

    # 3. uncovered failure modes ------------------------------------------- #
    ft = ins.get("failure_taxonomy") or {}
    modes = ft.get("by_mode") or []
    fail_q = [_cwords(t.get("question")) for t in tasks if _task_fails(t)]
    uncovered: list[dict[str, Any]] = []
    covered_modes = 0
    considered = 0
    for m in modes:
        if m.get("code") == "LOW_SIMILARITY":
            continue
        considered += 1
        ids = set(m.get("example_task_ids") or [])
        mode_q = [_cwords(t.get("question")) for t in tasks
                  if str(t.get("task_id")) in ids] or fail_q
        hit = any(
            _jacc(wi, mq) >= 0.5
            for _, wi in case_words if wi
            for mq in mode_q if mq
        )
        if hit:
            covered_modes += 1
        else:
            uncovered.append({
                "code": m.get("code"), "name": m.get("name"),
                "n_failures": m.get("n"), "owner": m.get("owner"),
                "remediation": m.get("remediation"),
            })

    coverage_pct = (round(covered_modes / considered * 100.0, 1)
                    if considered else None)

    bits = [f"{len(cases)} golden case(s)"]
    if uncovered:
        bits.append(f"{len(uncovered)} current failure mode(s) not exercised by any "
                    f"golden case (e.g. {uncovered[0]['name']})")
    elif considered:
        bits.append("every current failure mode is exercised by at least one case")
    if stale:
        bits.append(f"{len(stale)} case(s) look stale / trivial")
    if redundant:
        bits.append(f"{len(redundant)} near-duplicate case(s)")

    return {
        "n_cases": len(cases),
        "coverage_pct": coverage_pct,
        "n_modes_considered": considered,
        "uncovered_failure_modes": uncovered,
        "stale_cases": stale[:20],
        "redundant_cases": redundant[:20],
        "note": "; ".join(bits),
    }
