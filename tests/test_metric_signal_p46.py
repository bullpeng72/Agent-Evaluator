"""
tests/test_metric_signal_p46.py
===============================
SPEC-041 P46 — insights.metric_signal: pairwise correlation of the per-task
metrics, redundant-pair flags, and (with extra.outcome) outcome-predictiveness.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import _metric_signal_section, build_insights
from agent_evaluator.utils.confidence import pearson_r


def test_pearson_r():
    assert pearson_r([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert pearson_r([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert abs(pearson_r([1, 2, 3, 4, 5], [1, 2, 1, 2, 1])) < 0.5
    assert pearson_r([1, 1, 1], [1, 2, 3]) is None      # zero variance
    assert pearson_r([1, 2], [1, 2]) is None            # < 3 pairs


def _t(tid, comp, acc, *, judge=None, faith=None, outcome=None):
    d = {"task_id": tid, "task_type": "qa", "completion_score": comp,
         "accuracy_score": acc, "success": acc >= 0.6, "question": "q"}
    if judge is not None or faith is not None:
        sc = {}
        if judge is not None:
            sc["overall"] = judge
        if faith is not None:
            sc["faithfulness"] = faith
        d["llm_judge"] = {"scores": sc}
    if outcome is not None:
        d["extra"] = {"outcome": outcome}
    return d


def test_none_when_too_few_metrics():
    assert _metric_signal_section([{"task_id": "a"}]) is None


def test_redundant_pair_detected():
    # completion == accuracy exactly -> r = 1.0 -> redundant
    tasks = [_t(f"t{i}", i / 10, i / 10) for i in range(2, 10)]
    ms = _metric_signal_section(tasks)
    assert ms is not None
    pairs = {tuple(sorted(r["pair"])) for r in ms["redundant_pairs"]}
    assert ("accuracy", "completion") in pairs
    assert "redundant" in ms["note"]


def test_independent_metrics_not_redundant():
    comp = [0.2, 0.8, 0.5, 0.9, 0.3, 0.6, 0.7, 0.4]
    acc = [0.7, 0.6, 0.9, 0.4, 0.5, 0.8, 0.3, 0.65]      # ~uncorrelated with comp
    tasks = [_t(f"t{i}", c, a) for i, (c, a) in enumerate(zip(comp, acc))]
    ms = _metric_signal_section(tasks)
    assert not any(set(r["pair"]) == {"accuracy", "completion"}
                   for r in ms["redundant_pairs"])


def test_outcome_correlation_ranks_metrics():
    # outcome tracks accuracy, ignores completion (completion is constant-ish)
    tasks = []
    for i in range(10):
        acc = 0.1 + i * 0.08
        tasks.append(_t(f"t{i}", 0.5, acc, outcome=1.0 + acc * 4.0))
    ms = _metric_signal_section(tasks)
    oc = ms["outcome_correlation"]
    assert oc is not None
    top = oc[0]
    assert top["metric"] == "accuracy" and top["r"] > 0.9


def test_no_outcome_when_absent():
    tasks = [_t(f"t{i}", i / 10, (10 - i) / 10) for i in range(1, 9)]
    ms = _metric_signal_section(tasks)
    assert ms["outcome_correlation"] is None


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_metric_signal

    tasks = [_t(f"t{i}", x / 10, x / 10, outcome=1.0 + x * 0.4)
             for i, x in enumerate(range(1, 10))]
    cur = {"extra_metrics": {"harness_groups": {}}, "tasks": tasks}
    ins = build_insights(cur)
    ms = ins["metric_signal"]
    assert ms and ms["correlations"]
    html = _build_metric_signal(ms)
    assert "Metric Signal" in html and "Pairwise correlation" in html
    assert "Predicts the recorded outcome" in html
    assert _build_metric_signal(None) == ""
