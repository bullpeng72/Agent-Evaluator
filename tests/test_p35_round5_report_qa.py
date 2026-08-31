"""
tests/test_p35_round5_report_qa.py
==================================
SPEC-041 P35 round 5 — fifth example-report audit. Empty Gate F section,
Gate A naive-mean double-counting accuracy, "newly vs still below target",
weak slice concentration, "fixed" flaky tasks, redundant track-record blocks.
"""
from __future__ import annotations

from agent_evaluator.reporting.comprehensive_report import (
    _build_cohort_comparison,
    _build_failure_lineage,
    _build_gate_f,
    _build_insight_changes,
    _build_score_breakdown,
    _norm_task_for_case,
)
from agent_evaluator.reporting.insights import (
    _insight_changes_section,
    _regression_attribution_section,
    build_insights,
)


def _t(tid, comp, acc, ok, reason=None, extra=None):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q?", "response": "r", "ground_truth": "g",
            "extra": extra or {}}


# ---- N3: Gate F score breakdown renders --------------------------------------

def test_gate_f_breakdown_shows_coordination_score():
    hf = {"score": 0.502, "status": "warn", "gate": "warn",
          "details": {"coordination_score": 0.502, "avg_tool_selection_f1": None,
                      "avg_consensus": None, "avg_propagation": None,
                      "avg_role_compliance": None, "avg_conflict_resolution": None}}
    bd = _build_score_breakdown("F", hf)
    assert bd != ""
    assert "Coordination Score" in bd and "50.2%" in bd
    assert "Gate F Score" in bd


def test_gate_f_section_not_empty():
    hf = {"score": 0.502, "status": "warn", "gate": "warn",
          "details": {"coordination_score": 0.502}}
    html = _build_gate_f({}, {}, False, hf)
    assert "Coordination Score" in html
    assert "Gate F Score" in html


# ---- N2: Gate A naive mean excludes the blended accuracy term --------------

def test_gate_a_naive_mean_excludes_blended_accuracy():
    ha = {"score": 0.633, "status": "warn", "gate": "warn", "details": {
        "tcr_pct": 71.2, "avg_instruction_adherence": 0.783,
        "avg_subtask_completion": 0.662, "avg_accuracy": 0.578,
        "avg_quality_relevance_completeness": 0.404,
        "gate_a_tcr_weight": 0.4,
    }}
    bd = _build_score_breakdown("A", ha)
    # the accuracy row is present but marked as not a separate averaged term
    assert "not a separate averaged term" in bd
    # the "÷ N" divisor is 4 (TCR, IFR, subtask, rel/comp), not 5
    assert "÷ 4" in bd and "÷ 5" not in bd


# ---- N16: newly vs still below target ------------------------------------

def test_insight_changes_separates_newly_and_still_below():
    def _r(a, c, d):
        return {"extra_metrics": {"harness_groups": {
            "A": {"score": a, "status": "warn" if a < 0.7 else "pass",
                  "gate": "warn" if a < 0.7 else "pass", "details": {}},
            "C": {"score": c, "status": "warn" if c < 0.7 else "pass",
                  "gate": "warn" if c < 0.7 else "pass", "details": {}},
            "D": {"score": d, "status": "warn" if d < 0.7 else "pass",
                  "gate": "warn" if d < 0.7 else "pass", "details": {}}}},
                "tasks": []}
    cur = _r(0.6, 0.6, 0.6)          # A, C newly below; D still below
    base = _r(0.9, 0.9, 0.5)
    ic = _insight_changes_section(cur, base, None, None,
                                  cur["extra_metrics"]["harness_groups"])
    assert ic is not None
    assert set(ic["newly_failing_gates"]) == {"A", "C"}
    assert ic["still_below_gates"] == ["D"]
    html = _build_insight_changes(ic)
    assert "Still below target" in html and "D" in html


# ---- N17: weak slice concentration dropped -----------------------------

def test_regression_attribution_drops_immaterial_slice_concentration():
    from agent_evaluator.reporting.insights import _metadata_slices_section

    cur = [_t(f"c{i}", 1.0, 0.9, True, extra={"difficulty": "standard"})
           for i in range(10)]
    cur += [_t(f"f{i}", 0.2, 0.2, False, "low ground_truth similarity",
               extra={"difficulty": "standard"}) for i in range(2)]
    base = [_t(f"c{i}", 1.0, 0.92, True, extra={"difficulty": "standard"})
            for i in range(10)]
    base += [_t(f"f{i}", 0.95, 0.9, True, extra={"difficulty": "standard"})
             for i in range(2)]
    md = _metadata_slices_section(cur, {"tasks": base})
    ra = _regression_attribution_section(cur, {"regressed": ["f0", "f1"]}, {}, md)
    # 'standard' barely regressed overall -> not surfaced as "concentrates in"
    if ra:
        for c in ra["clusters"]:
            for s in c["slice_concentration"]:
                assert s.get("slice_tcr_delta_pp") is None \
                    or s["slice_tcr_delta_pp"] <= -5.0


# ---- N23: non-deterministic "fixed" task is separated ----------------

def test_failure_lineage_separates_flaky_fixed():
    base = {"tasks": [{"task_id": "flaky", "success": False, "accuracy_score": 0.2,
                       "completion_score": 0.2},
                      {"task_id": "clean", "success": False, "accuracy_score": 0.2,
                       "completion_score": 0.2},
                      {"task_id": "p", "success": True, "accuracy_score": 0.9,
                       "completion_score": 1.0}]}
    cases = [
        {"task_id": "flaky", "success": True, "accuracy_score": 0.9,
         "completion_score": 1.0, "extra": {"reproducibility": {"score": 0.41}}},
        {"task_id": "clean", "success": True, "accuracy_score": 0.9,
         "completion_score": 1.0, "extra": {}},
        {"task_id": "p", "success": True, "accuracy_score": 0.9,
         "completion_score": 1.0, "extra": {}},
    ]
    html = _build_failure_lineage(cases, base)
    assert "Fixed since baseline (1)" in html and "clean" in html
    assert "non-deterministic" in html and "flaky" in html


def test_norm_task_for_case_carries_extra():
    class _TR:
        task_id = "x"
        extra = {"reproducibility": {"score": 0.3}}
    d = _norm_task_for_case(_TR())
    assert d["extra"] == {"reproducibility": {"score": 0.3}}


# ---- N10: only one track-record block per rec card --------------------

def test_recommendation_card_has_one_track_record_block(tmp_path):
    import json

    (tmp_path / "experiments.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"experiment_id": "e1", "status": "resolved", "target_gate": "A",
         "note": "[improve] Gate A prompt_edit: g", "verdict": "confirmed",
         "actual_delta": 0.08},
        {"experiment_id": "e2", "status": "resolved", "target_gate": "A",
         "note": "prompt rewrite", "verdict": "confirmed", "actual_delta": 0.05},
    ]))
    (tmp_path / "recommendation_outcomes.jsonl").write_text(json.dumps(
        {"verdict": "confirmed", "target_gate": "A", "gate_delta": 0.1,
         "note": "past thing"}))
    tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
    tasks += [_t(f"g{i}", 0.3, 0.2, False,
                 "answer not grounded in the retrieved context") for i in range(4)]
    cur = {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}}},
        "lineage": {"prompt_text": "Answer using the context."}}, "tasks": tasks}
    ins = build_insights(
        cur, recommendation_log_path=str(tmp_path / "recommendation_outcomes.jsonl"),
        experiments_log_path=str(tmp_path / "experiments.jsonl"))
    from agent_evaluator.reporting.comprehensive_report import _build_recommendations

    hg = cur["extra_metrics"]["harness_groups"]
    html = _build_recommendations(
        hg, 60.0, 55.0, 0.0, 2.0, {},
        recommendation_log_path=str(tmp_path / "recommendation_outcomes.jsonl"),
        insights_recs=ins["recommendations"],
    )
    # the P57 "Track record" line supersedes the P8 "Past changes to Gate A" block
    assert "Track record:" in html
    assert "Past changes to Gate A" not in html


# ---- N22: cohort shows "—" for unmeasured gates ---------------------

def test_cohort_comparison_shows_dash_for_unmeasured_gate():
    cc = {"metric": "tcr", "versions": [
        {"label": "v3", "n_tasks": 24, "tcr_pct": 71.2,
         "gate_scores": {"A": 0.63, "F": 0.50}},
        {"label": "v2", "n_tasks": 24, "tcr_pct": 83.8,
         "gate_scores": {"A": 0.74}},
    ], "pairwise": [], "winner": {"verdict": "no_clear_winner", "detail": "x"}}
    html = _build_cohort_comparison(cc)
    assert "F —" in html          # v2 didn't measure F
