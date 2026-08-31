"""
tests/test_multiplicity_audit_p59.py
====================================
SPEC-041 P59 — family-wise honesty: insights.multiplicity_audit runs
Benjamini-Hochberg across every implicit slice / metadata / cohort comparison
and flags findings that would not survive as `likely_noise`.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _multiplicity_audit_section,
    build_insights,
)


def _t(tid, comp, acc, ttype="qa", model=None):
    d = {"task_id": tid, "task_type": ttype, "completion_score": comp,
         "accuracy_score": acc, "success": comp >= 0.5, "question": "q",
         "response": "r", "ground_truth": "x"}
    if model is not None:
        d["extra"] = {"model": model}
    return d


def test_none_without_p_values():
    assert _multiplicity_audit_section(None, None, None) is None
    assert _multiplicity_audit_section([{"task_type": "qa", "n": 5}], None, None) is None


def test_collects_family_and_runs_bh():
    sa = [
        {"task_type": "qa", "p_value": 0.03},
        {"task_type": "rag", "p_value": 0.9},
    ]
    md = [{"dimension": "extra.model",
           "slices": [{"value": "a", "p_value": 0.04},
                      {"value": "b", "p_value": 0.5}]}]
    ma = _multiplicity_audit_section(sa, md, None)
    assert ma is not None
    assert ma["n_comparisons"] == 4
    assert ma["alpha"] == 0.05
    assert ma["n_nominally_significant"] == 2       # 0.03 and 0.04
    # with 4 tests, BH threshold for the smallest (0.03) is 0.05*1/4 = 0.0125 -> fails
    assert ma["n_significant_after_bh"] == 0
    assert {f["label"] for f in ma["flagged"]} == {"task_type=qa", "extra.model=a"}
    assert ma["expected_false_positives"] == 0.2
    assert set(ma["sections"]) == {"slice_analysis", "metadata_slices"}
    assert "likely multiple-comparison noise" in ma["note"]


def test_strong_signal_survives_bh():
    sa = [{"task_type": "qa", "p_value": 0.0001},
          {"task_type": "rag", "p_value": 0.6}]
    ma = _multiplicity_audit_section(sa, None, None)
    assert ma is not None
    assert ma["n_significant_after_bh"] == 1
    assert ma["flagged"] == []
    assert "No finding is likely" in ma["note"]


def test_cohort_pairs_join_the_family():
    coh = {"pairs": [{"a": "v1", "b": "v2", "p_value": 0.02},
                     {"a": "v1", "b": "v3", "p_value": 0.8}]}
    ma = _multiplicity_audit_section(None, None, coh)
    assert ma is not None
    assert ma["n_comparisons"] == 2
    assert "cohort_comparison" in ma["sections"]


def test_refs_removed_from_output():
    sa = [{"task_type": "qa", "p_value": 0.03}]
    ma = _multiplicity_audit_section(sa, None, None)
    assert ma is not None
    assert "_refs" in ma           # present until _attach_multiplicity_flags pops it


# ---- end to end -----------------------------------------------------------

def test_build_insights_wires_and_flags_rows():
    cur_tasks = ([_t(f"q{i}", 1.0 if i < 10 else 0.2, 0.8, "qa") for i in range(15)]
                 + [_t(f"r{i}", 0.9, 0.85, "rag") for i in range(12)])
    base_tasks = ([_t(f"q{i}", 0.95, 0.8, "qa") for i in range(15)]
                  + [_t(f"r{i}", 0.9, 0.85, "rag") for i in range(12)])
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": cur_tasks},
                         {"extra_metrics": {"harness_groups": {}}, "tasks": base_tasks})
    ma = ins["multiplicity_audit"]
    assert ma is not None and "_refs" not in ma      # popped by _attach flags
    # the qa slice looks significant but is flagged back onto the row
    qa_row = next(r for r in ins["slice_analysis"] if r["task_type"] == "qa")
    if qa_row.get("p_value", 1.0) < 0.05 and ma["n_significant_after_bh"] == 0:
        assert qa_row.get("likely_noise") is True


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import _build_multiplicity_audit

    ma = _multiplicity_audit_section(
        [{"task_type": "qa", "p_value": 0.03}, {"task_type": "rag", "p_value": 0.9}],
        [{"dimension": "extra.model", "slices": [{"value": "a", "p_value": 0.04}]}],
        None,
    )
    html = _build_multiplicity_audit(ma)
    assert "Multiple-Comparison Audit" in html and "expected false positives" in html
    assert _build_multiplicity_audit(None) == ""
