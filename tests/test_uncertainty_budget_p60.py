"""
tests/test_uncertainty_budget_p60.py
====================================
SPEC-041 P60 — decompose the verdict's uncertainty into sampling / judge /
staleness / borderline buckets, each with the cheapest lever to shrink it.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import _uncertainty_budget_section, build_insights


def _t(tid, comp, acc, ok, judge=None):
    d = {"task_id": tid, "task_type": "qa", "completion_score": comp,
         "accuracy_score": acc, "success": ok, "question": "q", "response": "r",
         "ground_truth": "x"}
    if judge is not None:
        d["llm_judge"] = {"scores": {"overall": judge}}
    return d


# ---- section directly ---------------------------------------------------------

def test_none_when_high_confidence_and_nothing_flagged():
    out = {"verdict": {"confidence": "high"}, "metric_confidence": {"n_tasks": 200},
           "evaluator_trust": {"trust_level": "high"}, "freshness": {},
           "threshold_sensitivity": {}, "readiness": {}}
    assert _uncertainty_budget_section(out) is None


def test_sampling_component_with_task_estimate():
    out = {
        "verdict": {"confidence": "low"},
        "metric_confidence": {"n_tasks": 12, "tcr_ci_halfwidth": 0.24, "tcr_pct": 60.0},
        "evaluator_trust": {}, "freshness": {}, "threshold_sensitivity": {}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    s = next(c for c in ub["components"] if c["source"] == "sampling")
    assert "more tasks" in s["lever_cost"]
    assert "±5pp" in s["projected_reduction"]
    assert s["contribution_pct"] == 100.0
    assert ub["dominant_source"] == "sampling"


def test_judge_component_counts_disagreements():
    out = {
        "verdict": {"confidence": "medium"},
        "metric_confidence": {"n_tasks": 200},
        "evaluator_trust": {"trust_level": "low", "judge_vs_heuristic": {
            "disagreements": [{"task_id": "a"}, {"task_id": "b"}, {"task_id": "c"}]}},
        "freshness": {}, "threshold_sensitivity": {}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    j = next(c for c in ub["components"] if c["source"] == "judge")
    assert "3 judge" in j["cheapest_lever"] and j["lever_cost"] == "~3 tasks"


def test_staleness_ignores_tiny_eval_set_warning():
    out = {
        "verdict": {"confidence": "low"},
        "metric_confidence": {"n_tasks": 8},
        "evaluator_trust": {},
        "freshness": {"warnings": ["Only 8 task(s) in the eval set — widen it."]},
        "threshold_sensitivity": {}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    # the tiny-eval-set warning is sampling, not staleness
    assert not any(c["source"] == "staleness" for c in ub["components"])
    assert any(c["source"] == "sampling" for c in ub["components"])


def test_staleness_fires_on_old_baseline():
    out = {
        "verdict": {"confidence": "medium"},
        "metric_confidence": {"n_tasks": 200},
        "evaluator_trust": {}, "freshness": {"baseline_age_days": 63},
        "threshold_sensitivity": {}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    st = next(c for c in ub["components"] if c["source"] == "staleness")
    assert "63 days old" in st["description"]
    assert st["cheapest_lever"] == "re-baseline against a recent run"


def test_borderline_from_knife_edge_or_near_gap():
    out_knife = {
        "verdict": {"confidence": "medium"}, "metric_confidence": {"n_tasks": 200},
        "evaluator_trust": {}, "freshness": {},
        "threshold_sensitivity": {"knife_edge": True,
                                  "knife_edge_detail": "one 0.05 from flipping"},
        "readiness": {},
    }
    ub = _uncertainty_budget_section(out_knife)
    b = next(c for c in ub["components"] if c["source"] == "borderline")
    assert "not more measurement" in b["cheapest_lever"]

    out_gap = {
        "verdict": {"confidence": "medium"}, "metric_confidence": {"n_tasks": 200},
        "evaluator_trust": {}, "freshness": {}, "threshold_sensitivity": {},
        "readiness": {"gaps": [{"gate": "A", "gap": -0.02}]},
    }
    ub2 = _uncertainty_budget_section(out_gap)
    assert any(c["source"] == "borderline" for c in ub2["components"])


def test_contributions_sum_to_100():
    out = {
        "verdict": {"confidence": "low"},
        "metric_confidence": {"n_tasks": 12, "tcr_ci_halfwidth": 0.3, "tcr_pct": 55},
        "evaluator_trust": {"trust_level": "low"},
        "freshness": {"baseline_age_days": 90},
        "threshold_sensitivity": {"knife_edge": True}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    assert ub["n_sources"] == 4
    assert abs(sum(c["contribution_pct"] for c in ub["components"]) - 100.0) < 0.5
    # sorted by contribution desc
    pcts = [c["contribution_pct"] for c in ub["components"]]
    assert pcts == sorted(pcts, reverse=True)


# ---- end to end -----------------------------------------------------------

def test_build_insights_wires_it():
    tasks = ([_t(f"p{i}", 1.0, 0.9, True, judge=8.0) for i in range(6)]
             + [_t(f"f{i}", 0.2, 0.2, False, judge=8.5) for i in range(4)])
    cur = {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.66, "status": "warn", "gate": "warn", "details": {}}}},
        "tasks": tasks}
    ins = build_insights(cur)
    ub = ins["uncertainty_budget"]
    assert ub is not None and ub["components"]
    assert ub["overall_confidence"] == ins["verdict"]["confidence"]


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import _build_uncertainty_budget

    ub = _uncertainty_budget_section({
        "verdict": {"confidence": "low"},
        "metric_confidence": {"n_tasks": 12, "tcr_ci_halfwidth": 0.24, "tcr_pct": 60},
        "evaluator_trust": {}, "freshness": {}, "threshold_sensitivity": {},
        "readiness": {},
    })
    html = _build_uncertainty_budget(ub)
    assert "Uncertainty Budget" in html and "Cheapest lever" in html
    assert _build_uncertainty_budget(None) == ""
