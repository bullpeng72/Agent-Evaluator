"""
tests/test_judge_robustness_p52.py
==================================
SPEC-041 P52 — insights.judge_robustness: how much the deploy picture depends
on *which* judge model scored the run. Reads the opt-in
extra_metrics.judge_runs (>= 2 runs).
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _jr_runs,
    _jr_score_map,
    _judge_robustness_section,
    build_insights,
)


def _tasks(n=8):
    return [{"task_id": f"t{i}", "task_type": "qa", "completion_score": 1.0,
             "accuracy_score": 0.9, "success": True, "question": "q", "response": "r"}
            for i in range(n)]


def _cur(judge_runs, *, total_cost=2.0):
    return {"extra_metrics": {"harness_groups": {}, "judge_runs": judge_runs},
            "efficiency_metrics": {"tokens": {"total_cost": total_cost}},
            "tasks": _tasks()}


def test_none_without_two_runs():
    assert _judge_robustness_section({"extra_metrics": {}}, _tasks()) is None
    one = [{"model": "m1", "scores": {"t0": {"overall": 8}}}]
    assert _judge_robustness_section({"extra_metrics": {"judge_runs": one}}, _tasks()) is None


def test_runs_accepts_list_or_wrapped():
    runs = [{"model": "a", "scores": {}}, {"model": "b", "scores": {}}]
    assert len(_jr_runs({"extra_metrics": {"judge_runs": runs}})) == 2
    assert len(_jr_runs({"extra_metrics": {"judge_runs": {"runs": runs}}})) == 2


def test_score_map_normalises_10_and_1_scales_and_list_form():
    assert _jr_score_map({"scores": {"t0": {"overall": 8.0}}}) == {"t0": 0.8}
    assert _jr_score_map({"scores": {"t0": {"overall": 0.8}}}) == {"t0": 0.8}
    assert _jr_score_map({"scores": [{"task_id": "t0", "overall": 7}]}) == {"t0": 0.7}


def test_stable_when_models_agree():
    runs = [
        {"model": "haiku", "cost_usd": 0.1,
         "scores": {f"t{i}": {"overall": 8.0} for i in range(8)}},
        {"model": "sonnet", "cost_usd": 0.1,
         "scores": {f"t{i}": {"overall": 8.2} for i in range(8)}},
    ]
    jr = _judge_robustness_section(_cur(runs), _tasks())
    assert jr is not None
    assert jr["verdict_stability_across_models"]["stable"] is True
    assert jr["n_sensitive"] == 0
    assert "stable across judges" in jr["note"]


def test_unstable_flags_bucket_flips_and_cost_share():
    runs = [
        {"model": "haiku", "cost_usd": 0.15,
         "scores": {f"t{i}": {"overall": 5.0 if i % 2 == 0 else 8.0} for i in range(8)}},
        {"model": "sonnet", "cost_usd": 0.85,
         "scores": {f"t{i}": {"overall": 6.5 if i % 2 == 0 else 8.5} for i in range(8)}},
    ]
    jr = _judge_robustness_section(_cur(runs, total_cost=2.0), _tasks())
    assert jr is not None
    assert jr["verdict_stability_across_models"]["stable"] is False
    assert jr["n_sensitive"] == 4
    assert all(s["bucket_flip"] for s in jr["judge_sensitive_tasks"])
    # 1.0 judge cost / (1.0 + 2.0) eval  -> ~33%
    assert 30.0 <= jr["judge_cost_share_pct"] <= 35.0
    assert jr["models"] == ["haiku", "sonnet"]


def test_cost_share_none_without_total_cost():
    runs = [
        {"model": "a", "scores": {f"t{i}": {"overall": 8} for i in range(6)}},
        {"model": "b", "scores": {f"t{i}": {"overall": 8} for i in range(6)}},
    ]
    cur = {"extra_metrics": {"harness_groups": {}, "judge_runs": runs}, "tasks": _tasks()}
    jr = _judge_robustness_section(cur, _tasks())
    assert jr is not None
    assert jr["judge_cost_share_pct"] is None


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_judge_robustness

    runs = [
        {"model": "haiku", "cost_usd": 0.1,
         "scores": {f"t{i}": {"overall": 5.0 if i < 3 else 8.0} for i in range(8)}},
        {"model": "sonnet", "cost_usd": 0.1,
         "scores": {f"t{i}": {"overall": 7.0 if i < 3 else 8.0} for i in range(8)}},
    ]
    ins = build_insights(_cur(runs))
    jr = ins["judge_robustness"]
    assert jr and jr["n_runs"] == 2
    html = _build_judge_robustness(jr)
    assert "Judge Robustness" in html and "Per-model mean overall" in html
    assert _build_judge_robustness(None) == ""
