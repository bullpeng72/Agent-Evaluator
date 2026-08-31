"""
tests/test_threshold_sensitivity_p44.py
=======================================
SPEC-041 P44 — insights.threshold_sensitivity: sweep the gate pass line + the
per-task accuracy threshold and flag a knife-edge verdict.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _threshold_sensitivity_section,
    _ts_verdict,
    build_insights,
)


def _hg(scores):
    return {k: {"score": s, "status": "pass", "gate": "pass", "details": {}}
            for k, s in scores.items()}


def _tasks(accs):
    return [{"task_id": f"t{i}", "task_type": "qa", "accuracy_score": a,
             "completion_score": 1.0, "success": True, "question": "q"}
            for i, a in enumerate(accs)]


def test_ts_verdict_model():
    assert _ts_verdict([0.9, 0.85], 0.7) == "ready"
    assert _ts_verdict([0.9, 0.62], 0.7) == "caution"       # one below line, > line-0.15
    assert _ts_verdict([0.9, 0.4], 0.7) == "not_ready"      # one below line-0.15
    assert _ts_verdict([], 0.7) == "unknown"


def test_none_without_data():
    assert _threshold_sensitivity_section({}, []) is None


def test_sweep_shape_and_current_marker():
    ts = _threshold_sensitivity_section(
        _hg({"A": 0.72, "C": 0.9, "D": 0.68}), _tasks([0.6, 0.8, 0.9, 0.5]),
    )
    assert ts is not None
    assert ts["current_line"] == 0.7
    assert ts["n_gates_measured"] == 3 and ts["n_tasks_with_accuracy"] == 4
    lines = [r["line"] for r in ts["gate_line_sweep"]]
    assert 0.7 in lines and 0.85 in lines
    at_50 = next(r for r in ts["gate_line_sweep"] if r["line"] == 0.5)
    assert at_50["gates_meeting"] == 3 and at_50["verdict"] == "ready"
    at_80 = next(r for r in ts["gate_line_sweep"] if r["line"] == 0.8)
    assert at_80["gates_below"] == 2
    # accuracy sweep monotone non-increasing
    prs = [r["pass_rate_pct"] for r in ts["accuracy_threshold_sweep"]]
    assert all(a >= b for a, b in zip(prs, prs[1:]))


def test_knife_edge_detected():
    # at 0.70: A=0.66 is < line and < line-0.15? no (0.66 > 0.55) -> caution.
    # at 0.65: 0.66 >= line -> ready. So the call flips -> knife edge.
    ts = _threshold_sensitivity_section(_hg({"A": 0.66, "C": 0.9}), _tasks([0.8]))
    assert ts is not None
    assert ts["knife_edge"] is True
    assert "0.65" in ts["knife_edge_detail"]


def test_not_knife_edge_when_stable():
    ts = _threshold_sensitivity_section(_hg({"A": 0.95, "C": 0.92}), _tasks([0.9]))
    assert ts is not None
    assert ts["knife_edge"] is False


def test_respects_user_target_line():
    ts = _threshold_sensitivity_section(
        _hg({"A": 0.82, "C": 0.9}), _tasks([0.8]),
        targets={"gates": {"A": 0.85}},
    )
    assert ts is not None
    assert ts["current_line"] == 0.85          # user bar, not 0.7


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import (
        _build_threshold_sensitivity,
    )

    cur = {"extra_metrics": {"harness_groups": _hg({"A": 0.66, "C": 0.9})},
           "tasks": _tasks([0.6, 0.8, 0.9])}
    ins = build_insights(cur)
    ts = ins["threshold_sensitivity"]
    assert ts and "gate_line_sweep" in ts
    html = _build_threshold_sensitivity(ts)
    assert "Threshold Sensitivity" in html and "← current" in html
    assert _build_threshold_sensitivity(None) == ""
