"""
tests/test_eval_representativeness_p54.py
========================================
SPEC-041 P54 — does the eval set match production? Opt-in
extra_metrics.production_sample -> insights.eval_representativeness
(query coverage + per-key distribution gaps + a prod-weighted TCR estimate).
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _eval_representativeness_section,
    build_insights,
)


def _t(tid, comp, acc, ok, q, topic=None):
    d = {"task_id": tid, "task_type": "qa", "completion_score": comp,
         "accuracy_score": acc, "success": ok, "question": q, "response": "r",
         "ground_truth": "x"}
    if topic:
        d["extra"] = {"topic": topic}
    return d


def _tasks():
    t = [_t(f"r{i}", 0.9, 0.9, True, f"how do I return item {i}", "returns")
         for i in range(12)]
    t += [_t(f"s{i}", 0.3, 0.3, False, f"where is my order {i}", "shipping")
          for i in range(2)]
    return t


def _cur(sample):
    return {"extra_metrics": {"harness_groups": {}, "production_sample": sample},
            "tasks": _tasks()}


# ---- section ------------------------------------------------------------------

def test_none_without_sample():
    assert _eval_representativeness_section(_tasks(), {"extra_metrics": {}}) is None
    assert _eval_representativeness_section(_tasks(),
                                           {"extra_metrics": {"production_sample": {}}}) is None


def test_query_coverage_and_blind_spots():
    er = _eval_representativeness_section(_tasks(), _cur({"queries": [
        "how do I return an item", "where is my package",
        "update my credit card on file", "cancel my subscription"]}))
    assert er is not None
    qc = er["query_coverage"]
    assert qc["n_production_queries"] == 4
    assert qc["n_covered"] == 3
    assert "update my credit card on file" in qc["blind_spots"]
    assert "no close match" in er["note"]


def test_topic_histogram_gaps_and_over_representation():
    er = _eval_representativeness_section(_tasks(), _cur({"topics": {
        "returns": 0.25, "shipping": 0.45, "billing": 0.30}}))
    assert er is not None
    d = er["distributions"][0]
    assert d["key"] == "topic"
    gap_vals = {g["value"] for g in d["coverage_gaps"]}
    assert "shipping" in gap_vals and "billing" in gap_vals
    over_vals = {o["value"] for o in d["over_represented"]}
    assert "returns" in over_vals
    assert d["distribution_distance"] > 0


def test_prod_weighted_tcr_below_measured():
    er = _eval_representativeness_section(_tasks(), _cur({"topics": {
        "returns": 0.2, "shipping": 0.8}}))
    # eval is mostly the easy 'returns' topic; prod is mostly failing 'shipping'
    assert er is not None
    assert er["prod_weighted_tcr_estimate_pct"] < er["measured_tcr_pct"]


def test_metadata_histogram_key():
    tasks = [_t(f"e{i}", 1.0, 0.9, True, f"q {i}") for i in range(8)]
    for t in tasks:
        t["extra"] = {"difficulty": "easy"}
    tasks += [{"task_id": f"h{i}", "task_type": "qa", "completion_score": 0.3,
               "accuracy_score": 0.3, "success": False, "question": f"hq {i}",
               "response": "r", "ground_truth": "x",
               "extra": {"difficulty": "hard"}} for i in range(2)]
    er = _eval_representativeness_section(tasks, {
        "extra_metrics": {"production_sample": {
            "metadata": {"difficulty": {"easy": 0.3, "hard": 0.7}}}},
        "tasks": tasks})
    assert er is not None
    d = next(x for x in er["distributions"] if x["key"] == "difficulty")
    assert any(g["value"] == "hard" for g in d["coverage_gaps"])


# ---- end to end -----------------------------------------------------------

def test_build_insights_and_report():
    from agent_evaluator.reporting.comprehensive_report import (
        _build_eval_representativeness,
    )

    ins = build_insights(_cur({
        "topics": {"returns": 0.25, "shipping": 0.75},
        "queries": ["return an item", "track my package", "billing question"]}))
    er = ins["eval_representativeness"]
    assert er and er["distributions"]
    html = _build_eval_representativeness(er)
    assert "Eval vs Production" in html and "production-weighted" in html
    assert _build_eval_representativeness(None) == ""
