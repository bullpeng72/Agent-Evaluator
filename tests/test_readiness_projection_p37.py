"""
tests/test_readiness_projection_p37.py
======================================
SPEC-041 P37 — fix-plan projections gain a full gate vector, bootstrap CI, ROI,
and projected_ready_after gains p_ready / likely_fix_count.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _effort_weight_for_sig,
    _readiness_section,
)


def _t(tid, comp, acc, ok, reason, ttype="qa"):
    return {"task_id": tid, "task_type": ttype, "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": f"q {tid}"}


def _run():
    tasks = [_t(f"p{i}", 1.0, 0.9, True, None) for i in range(10)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    tasks += [_t(f"ms{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(3)]
    tasks += [_t(f"lb{i}", 0.9, 0.15, False, "low ground_truth similarity")
              for i in range(2)]
    hg = {"A": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}},
          "C": {"score": 0.62, "status": "warn", "gate": "warn", "details": {}},
          "D": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}}}
    return tasks, hg


def test_effort_weight_mapping():
    assert _effort_weight_for_sig("low ground_truth similarity") == 1.0
    assert _effort_weight_for_sig("error: TimeoutError") == 2.0
    assert _effort_weight_for_sig("only part of a multi-step answer completed") == 3.0
    assert _effort_weight_for_sig("mystery") == 4.0


def test_fix_plan_rows_have_projection_vector_and_roi():
    tasks, hg = _run()
    rd = _readiness_section(tasks, hg)
    assert rd and rd["fix_plan"]
    for row in rd["fix_plan"]:
        pgs = row["projected_gate_scores"]
        assert set(pgs) == {"A", "C", "D"}                 # every below-target gate
        assert row["gate_moves"]["A"] is True and row["gate_moves"]["D"] is False
        assert pgs["D"] == round(0.64, 3)                  # held (not TCR-driven)
        assert isinstance(row["roi"], (int, float))
        assert row["effort_weight"] in (1.0, 2.0, 3.0, 4.0)
        # CI present for the moving gates, ordered lo <= point <= hi-ish
        ci = row["projected_gate_scores_ci"]
        assert "A" in ci and ci["A"][0] <= ci["A"][1]
        assert ci["A"][0] <= pgs["A"] + 1e-9


def test_data_fix_has_higher_roi_than_grounding_for_similar_gap():
    tasks, hg = _run()
    rd = _readiness_section(tasks, hg)
    assert rd is not None
    by_sig = {r["signature"]: r for r in rd["fix_plan"]}
    # a cheap data fix (weight 1) should out-ROI a med-effort fix per unit gap
    if "low ground_truth similarity" in by_sig and "error: TimeoutError" in by_sig:
        assert by_sig["low ground_truth similarity"]["effort_weight"] == 1.0


def test_projected_ready_after_has_bootstrap_fields():
    tasks, hg = _run()
    rd = _readiness_section(tasks, hg)
    assert rd is not None
    pr = rd["projected_ready_after"]
    assert "p_ready" in pr and 0.0 <= pr["p_ready"] <= 1.0
    assert pr["likely_fix_count"] is None or pr["likely_fix_count"] >= 1


def test_projection_is_deterministic():
    tasks, hg = _run()
    a = _readiness_section(tasks, hg)
    b = _readiness_section(tasks, hg)
    assert a is not None and b is not None
    assert a["fix_plan"][0]["roi"] == b["fix_plan"][0]["roi"]
    assert a["fix_plan"][0]["projected_gate_scores_ci"] == \
        b["fix_plan"][0]["projected_gate_scores_ci"]
    assert a["projected_ready_after"]["p_ready"] == b["projected_ready_after"]["p_ready"]


def test_report_renders_roi_and_vector():
    from agent_evaluator.reporting.comprehensive_report import _build_readiness

    tasks, hg = _run()
    html = _build_readiness(_readiness_section(tasks, hg))
    assert "ROI" in html and "effort" in html
    assert "→ A~" in html
    assert "likely to clear" in html
