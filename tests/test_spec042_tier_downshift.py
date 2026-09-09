"""
tests/test_spec042_tier_downshift.py
=====================================
SPEC-042 REQ-8 — ``insights.efficiency_opportunities`` emits a ``tier_downshift``
opportunity when a task type passes with a comfortable accuracy margin yet costs
about as much per task as the hardest type.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import build_insights


def _t(tid, ttype, acc, cost):
    return {
        "task_id": tid, "task_type": ttype,
        "success": True, "accuracy_score": acc, "completion_score": 1.0,
        "question": "q", "response": "r", "ground_truth": "r",
        "extra": {"cost_usd": cost},
    }


def _result(tasks):
    return {
        "summary": {"tcr": 100.0, "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {"A": {"score": 0.9, "status": "pass"}}},
        "tasks": tasks,
    }


def _eff(ins):
    return [o for o in (ins.get("efficiency_opportunities") or [])
            if o.get("kind") == "tier_downshift"]


class TestTierDownshift:
    def test_emitted_when_easy_type_costs_like_hard_type(self):
        tasks = (
            [_t(f"tu{i}", "tool_use", 0.92, 0.010) for i in range(3)]
            + [_t(f"rs{i}", "reasoning", 0.74, 0.011) for i in range(3)]
        )
        opp = _eff(build_insights(_result(tasks)))
        assert len(opp) == 1
        o = opp[0]
        assert "tool_use" in o["title"]
        assert "reasoning" in o["detail"]
        assert o["evidence"]["by_task_type"]

    def test_not_emitted_when_easy_type_is_already_cheap(self):
        tasks = (
            [_t(f"tu{i}", "tool_use", 0.95, 0.002) for i in range(3)]   # far cheaper
            + [_t(f"rs{i}", "reasoning", 0.74, 0.011) for i in range(3)]
        )
        assert _eff(build_insights(_result(tasks))) == []

    def test_not_emitted_when_easy_type_accuracy_is_marginal(self):
        tasks = (
            [_t(f"tu{i}", "tool_use", 0.80, 0.010) for i in range(3)]   # below 0.85
            + [_t(f"rs{i}", "reasoning", 0.74, 0.011) for i in range(3)]
        )
        assert _eff(build_insights(_result(tasks))) == []

    def test_needs_at_least_three_tasks_per_type(self):
        tasks = (
            [_t(f"tu{i}", "tool_use", 0.95, 0.010) for i in range(2)]
            + [_t(f"rs{i}", "reasoning", 0.74, 0.011) for i in range(3)]
        )
        assert _eff(build_insights(_result(tasks))) == []

    def test_single_task_type_yields_nothing(self):
        tasks = [_t(f"tu{i}", "tool_use", 0.95, 0.010) for i in range(5)]
        assert _eff(build_insights(_result(tasks))) == []

    def test_risk_note_present(self):
        tasks = (
            [_t(f"tu{i}", "tool_use", 0.92, 0.010) for i in range(3)]
            + [_t(f"rs{i}", "reasoning", 0.74, 0.011) for i in range(3)]
        )
        o = _eff(build_insights(_result(tasks)))[0]
        assert "measure" in o["risk"].lower()
        assert o["projected_saving_pct"] is None  # advisory, no hard projection
