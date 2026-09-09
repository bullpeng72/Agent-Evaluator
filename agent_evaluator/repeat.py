"""
Whole-eval repeat / verdict-stability (SPEC-042 REQ-4).
========================================================

``judge_runs`` / ``judge_self_consistency`` (SPEC-041 P52) measure whether the
*judge* is stable. This module measures whether the *deploy verdict* is stable:
run the same eval K times and report how often the pass/fail call flips and which
tasks are non-deterministic.

Nothing here re-runs an agent on its own — the caller supplies a zero-arg
``eval_fn`` that runs their eval once and returns a result-JSON dict
(``monitor.generate_report().to_dict()`` or ``json.load(open(result_file))``).
``run_repeated`` calls it K times; ``summarize_repeated`` folds K result dicts
into one stability summary. Put that summary (or the raw list of run dicts) at
``result["extra_metrics"]["repeat_runs"]`` and ``build_insights`` surfaces it as
``insights.nondeterminism_repeat``.

This is an expensive check (K× the eval cost) — intended for release-candidate /
nightly runs, not every PR. It only makes sense for an **idempotent** agent
(re-running must not mutate external state); see ``IdempotencyConfig``.

No new scoring formula: "pass" here is the same gate line the rest of the SDK
uses (all measured Gate A–G scores >= ``gate_line``, default 0.7).
"""
from __future__ import annotations

import math
from typing import Any, Callable

_GATE_LINE = 0.7


def _run_harness_groups(run: dict[str, Any]) -> dict[str, Any]:
    em = run.get("extra_metrics")
    if isinstance(em, dict):
        hg = em.get("harness_groups")
        if isinstance(hg, dict):
            return dict(hg)
    hg2 = run.get("harness_groups")
    return dict(hg2) if isinstance(hg2, dict) else {}


def _run_gate_pass(run: dict[str, Any], gate_line: float) -> bool | None:
    """True/False if every *measured* Gate A–G is at/below the line; None when no
    Gate was measured (can't call it)."""
    hg = _run_harness_groups(run)
    measured = []
    for k in "ABCDEFG":
        g = hg.get(k)
        if not isinstance(g, dict):
            continue
        sc = g.get("score")
        if isinstance(sc, (int, float)):
            measured.append(float(sc))
    if not measured:
        return None
    return all(s >= gate_line - 1e-9 for s in measured)


def _run_tcr(run: dict[str, Any]) -> float | None:
    summary = run.get("summary")
    if isinstance(summary, dict):
        for key in ("tcr", "task_completion_rate", "tcr_pct"):
            v = summary.get(key)
            if isinstance(v, (int, float)):
                return float(v)
    v = run.get("task_completion_rate")
    return float(v) if isinstance(v, (int, float)) else None


def _run_task_pass(run: dict[str, Any]) -> dict[str, bool]:
    """Per-task pass/fail for the run, keyed by task_id. 'pass' = success and
    accuracy not clearly bad — mirrors ``insights._effective_fail`` loosely
    without importing it (this module has no reporting deps)."""
    out: dict[str, bool] = {}
    for t in run.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("task_id") or "")
        if not tid:
            continue
        acc = t.get("accuracy_score")
        comp = t.get("completion_score")
        ok = bool(t.get("success", False))
        if isinstance(acc, (int, float)) and acc < 0.7:
            ok = False
        if isinstance(comp, (int, float)) and comp < 0.4:
            ok = False
        out[tid] = ok
    return out


def _stddev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def summarize_repeated(
    runs: list[dict[str, Any]], *, gate_line: float = _GATE_LINE,
) -> dict[str, Any] | None:
    """Fold K result-JSON dicts (same task set, K independent runs) into a
    verdict-stability summary. Returns ``None`` for fewer than 2 runs.

    Returns::

        {
          "runs": K,
          "gate_pass_count": int,       # runs whose verdict is "pass"
          "gate_verdicts": ["pass"|"fail"|"unknown", ...],
          "flip_rate": float,           # fraction of runs disagreeing with the majority verdict
          "majority_verdict": "pass"|"fail"|"unknown",
          "tcr_values": [...], "tcr_mean": float|None, "tcr_stddev": float|None,
          "unstable_tasks": [{"task_id","pass_count","runs"}],  # pass in some runs, fail in others
          "n_unstable_tasks": int,
          "deterministic": bool,        # no verdict flip AND no unstable task
        }
    """
    runs = [r for r in (runs or []) if isinstance(r, dict)]
    if len(runs) < 2:
        return None

    verdicts: list[str] = []
    for r in runs:
        gp = _run_gate_pass(r, gate_line)
        verdicts.append("unknown" if gp is None else ("pass" if gp else "fail"))
    pass_count = verdicts.count("pass")

    # majority verdict (ties -> the more conservative "fail")
    counts = {v: verdicts.count(v) for v in set(verdicts)}
    top = max(counts.values())
    majority = (
        "fail" if counts.get("fail", 0) == top
        else max(counts, key=lambda v: counts[v])
    )
    flips = sum(1 for v in verdicts if v != majority)
    flip_rate = round(flips / len(verdicts), 4)

    tcrs = [v for v in (_run_tcr(r) for r in runs) if v is not None]
    tcr_mean = round(sum(tcrs) / len(tcrs), 3) if tcrs else None
    tcr_sd = round(_stddev(tcrs), 3) if len(tcrs) >= 2 else None

    per_run_task_pass = [_run_task_pass(r) for r in runs]
    all_task_ids: set[str] = set()
    for d in per_run_task_pass:
        all_task_ids.update(d.keys())
    unstable: list[dict[str, Any]] = []
    for tid in sorted(all_task_ids):
        seen = [d[tid] for d in per_run_task_pass if tid in d]
        if len(seen) >= 2 and 0 < sum(seen) < len(seen):
            unstable.append(
                {"task_id": tid, "pass_count": sum(seen), "runs": len(seen)}
            )

    return {
        "runs": len(runs),
        "gate_pass_count": pass_count,
        "gate_verdicts": verdicts,
        "flip_rate": flip_rate,
        "majority_verdict": majority,
        "tcr_values": [round(v, 3) for v in tcrs],
        "tcr_mean": tcr_mean,
        "tcr_stddev": tcr_sd,
        "unstable_tasks": unstable[:50],
        "n_unstable_tasks": len(unstable),
        "deterministic": flip_rate == 0.0 and not unstable,
    }


def run_repeated(
    eval_fn: Callable[[], dict[str, Any]],
    k: int = 3,
    *,
    gate_line: float = _GATE_LINE,
) -> dict[str, Any] | None:
    """Call ``eval_fn()`` ``k`` times and summarise verdict stability.

    ``eval_fn`` runs one full eval of the same task set and returns its
    result-JSON dict. Use for release-candidate / nightly runs on an idempotent
    agent — it costs k× the eval. ``k <= 1`` returns ``None`` (nothing to
    compare).

    Example::

        from agent_evaluator.repeat import run_repeated

        def one_run() -> dict:
            m = PerformanceMonitor(output_dir="results/")
            for q in questions:
                m.record_task(create_taskresult(...))
            return m.generate_report().to_dict()

        stability = run_repeated(one_run, k=5)
        # -> attach to a result: result["extra_metrics"]["repeat_runs"] = stability
    """
    if k <= 1:
        return None
    runs = [eval_fn() for _ in range(k)]
    return summarize_repeated(runs, gate_line=gate_line)
