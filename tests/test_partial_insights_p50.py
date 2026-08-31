"""
tests/test_partial_insights_p50.py
==================================
SPEC-041 P50 — incremental / streaming insights: build_insights(partial=True)
returns the cheap baseline-free subset + a running readiness verdict with a
`decisive` early-stop flag; PerformanceMonitor.should_early_stop() wraps it.
"""
from __future__ import annotations

import tempfile

from agent_evaluator.reporting.insights import (
    _running_verdict_section,
    build_insights,
)


def _t(tid, comp, acc, ok):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "question": "q", "response": "r"}


def _hg(a_score):
    return {"A": {"score": a_score, "status": "warn" if a_score < 0.7 else "pass",
                  "gate": "warn" if a_score < 0.7 else "pass", "details": {}}}


# ---- _running_verdict_section --------------------------------------------

def test_undecided_below_min_tasks():
    rv = _running_verdict_section([_t(f"p{i}", 1.0, 1.0, True) for i in range(6)], _hg(0.9))
    assert rv["decisive"] is False and rv["verdict"] == "undecided"
    assert "need >= 10" in rv["reason"]


def test_decisive_not_ready_when_ci_upper_below_target():
    tasks = ([_t(f"f{i}", 0.1, 0.1, False) for i in range(28)]
             + [_t(f"p{i}", 1.0, 1.0, True) for i in range(3)])
    rv = _running_verdict_section(tasks, _hg(0.4))
    assert rv["decisive"] is True and rv["verdict"] == "not_ready"
    assert rv["pass_rate_ci_pct"][1] < rv["target_tcr_pct"]


def test_decisive_ready_when_ci_lower_above_target_and_gates_ok():
    tasks = [_t(f"p{i}", 1.0, 1.0, True) for i in range(60)]
    rv = _running_verdict_section(tasks, _hg(0.92))
    assert rv["decisive"] is True and rv["verdict"] == "ready"
    assert rv["gates_below_target"] == []


def test_not_ready_via_gate_even_if_tcr_ok():
    tasks = [_t(f"p{i}", 1.0, 1.0, True) for i in range(60)]
    rv = _running_verdict_section(tasks, _hg(0.5))   # Gate A below bar
    assert rv["decisive"] is False
    assert "A" in rv["gates_below_target"]
    assert "keep sampling" in rv["reason"]


def test_straddle_is_undecided():
    tasks = ([_t(f"p{i}", 1.0, 1.0, True) for i in range(20)]
             + [_t(f"f{i}", 0.1, 0.1, False) for i in range(15)])
    rv = _running_verdict_section(tasks, _hg(0.9))
    assert rv["decisive"] is False and rv["verdict"] == "undecided"
    assert "straddles" in rv["reason"]


def test_targets_override_tcr_bar():
    tasks = ([_t(f"p{i}", 1.0, 1.0, True) for i in range(40)]
             + [_t(f"f{i}", 0.1, 0.1, False) for i in range(10)])   # 80% pass
    lax = _running_verdict_section(tasks, _hg(0.9), targets={"tcr_pct": 60})
    strict = _running_verdict_section(tasks, _hg(0.9), targets={"tcr_pct": 95})
    assert lax["target_tcr_pct"] == 60.0 and strict["target_tcr_pct"] == 95.0
    assert strict["verdict"] == "not_ready"      # CI upper < 95
    assert lax["verdict"] == "ready"             # CI lower >= 60


# ---- build_insights(partial=True) ---------------------------------------

def test_partial_returns_reduced_dict():
    tasks = ([_t(f"f{i}", 0.1, 0.1, False) for i in range(25)]
             + [_t(f"p{i}", 1.0, 1.0, True) for i in range(5)])
    cur = {"extra_metrics": {"harness_groups": _hg(0.45)}, "tasks": tasks}
    ins = build_insights(cur, partial=True)
    assert ins["detection_mode"] == "partial" and ins["partial"] is True
    assert ins["n_tasks"] == 30
    assert ins["running_verdict"]["decisive"] is True
    # present: cheap baseline-free sections
    for k in ("verdict", "readiness", "metric_confidence", "gate_findings",
              "failure_clusters", "calibration", "narrative"):
        assert k in ins
    # absent: everything needing a baseline / cohort / history / experiments log
    for k in ("cohort_comparison", "trace_diffs", "longitudinal", "insight_changes",
              "change_attribution", "experiments", "regression_attribution",
              "briefs", "conversation"):
        assert k not in ins


def test_partial_never_raises_on_junk():
    assert build_insights({}, partial=True)["detection_mode"] == "partial"
    assert build_insights({"tasks": "nope"}, partial=True)["n_tasks"] == 0


# ---- PerformanceMonitor.should_early_stop -------------------------------

def test_monitor_should_early_stop():
    from agent_evaluator import PerformanceMonitor, create_taskresult

    m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
    for i in range(30):
        m.record_task(create_taskresult(
            task_id=f"t{i}", question="q", response="r",
            ground_truth="completely unrelated answer text", execution_time=0.4,
            task_type="qa",
        ))
    stop, rv = m.should_early_stop()
    assert stop is True and rv["verdict"] == "not_ready"
    ins = m.running_insights()
    assert ins["partial"] is True and ins["n_tasks"] == 30


def test_monitor_running_insights_empty_is_safe():
    from agent_evaluator import PerformanceMonitor

    m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
    stop, rv = m.should_early_stop()
    assert stop is False
    assert isinstance(m.running_insights(), dict)
