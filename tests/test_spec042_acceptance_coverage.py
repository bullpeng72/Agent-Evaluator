"""
tests/test_spec042_acceptance_coverage.py
==========================================
SPEC-042 REQ-1 — declared acceptance criteria as an optional first-class field
(``extra.acceptance_criteria``) surfaced as ``insights.acceptance_coverage``
(display only — never a Gate score).
"""
from __future__ import annotations

from agent_evaluator import create_taskresult
from agent_evaluator.reporting.insights import build_insights


def _task(tid, response, criteria=None, acc=0.9):
    t = {
        "task_id": tid,
        "success": True,
        "accuracy_score": acc,
        "completion_score": 1.0,
        "question": "q",
        "response": response,
        "ground_truth": "gt",
        "task_type": "qa",
    }
    if criteria is not None:
        t["extra"] = {"acceptance_criteria": criteria}
    return t


def _result(tasks, gate_a=0.9):
    return {
        "summary": {"tcr": 90.0, "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {"A": {"score": gate_a, "status": "pass"}}},
        "tasks": tasks,
    }


class TestCreateTaskresultKwarg:
    def test_acceptance_criteria_lands_in_extra(self):
        tr = create_taskresult(
            task_id="t1", question="q", response="r",
            acceptance_criteria=["must cite the source", "returns JSON"],
        )
        assert (tr.extra or {})["acceptance_criteria"] == ["must cite the source", "returns JSON"]

    def test_blank_criteria_filtered(self):
        tr = create_taskresult(
            task_id="t1", question="q", response="r",
            acceptance_criteria=["  ", "", "real one"],
        )
        assert (tr.extra or {})["acceptance_criteria"] == ["real one"]

    def test_none_leaves_extra_untouched(self):
        tr = create_taskresult(task_id="t1", question="q", response="r")
        assert "acceptance_criteria" not in (tr.extra or {})


class TestAcceptanceCoverageSection:
    def test_none_when_no_task_declares_criteria(self):
        ins = build_insights(_result([_task("t1", "hello")]))
        assert ins["acceptance_coverage"] is None

    def test_substring_criterion_is_satisfied(self):
        ins = build_insights(_result([
            _task("t1", "The answer is 42 and here is valid JSON output.",
                  criteria=["valid JSON output", "the answer is 42"]),
        ]))
        cov = ins["acceptance_coverage"]
        assert cov["total_criteria"] == 2
        assert cov["satisfied_criteria"] == 2
        assert cov["fully_satisfied_tasks"] == 1
        assert cov["coverage_pct"] == 100.0

    def test_unmet_criterion_is_listed(self):
        ins = build_insights(_result([
            _task("t1", "Seoul is the capital.",
                  criteria=["Seoul is the capital", "includes a population figure"]),
        ]))
        cov = ins["acceptance_coverage"]
        assert cov["satisfied_criteria"] == 1
        bt = cov["by_task"][0]
        assert bt["satisfied"] == 1 and bt["total"] == 2
        assert any("population" in u for u in bt["unmet"])

    def test_token_overlap_match(self):
        # 3 of 4 content tokens present -> >= 60% -> satisfied
        ins = build_insights(_result([
            _task("t1", "the report lists quarterly revenue and profit",
                  criteria=["report includes quarterly revenue profit"]),
        ]))
        assert ins["acceptance_coverage"]["satisfied_criteria"] == 1

    def test_aggregate_across_tasks(self):
        ins = build_insights(_result([
            _task("t1", "has foo and bar", criteria=["has foo", "has bar"]),
            _task("t2", "only foo here", criteria=["has foo", "has baz"]),
            _task("t3", "nothing", acc=0.9),  # no criteria -> excluded
        ]))
        cov = ins["acceptance_coverage"]
        assert cov["n_tasks_with_criteria"] == 2
        assert cov["total_criteria"] == 4
        assert cov["satisfied_criteria"] == 3
        assert cov["fully_satisfied_tasks"] == 1

    def test_not_a_gate_score(self):
        with_c = build_insights(_result([
            _task("t1", "x", criteria=["totally unmet requirement about y"]),
        ]))
        without_c = build_insights(_result([_task("t1", "x")]))
        assert with_c["verdict"]["level"] == without_c["verdict"]["level"]
        # coverage 0% but the gate verdict is untouched
        assert with_c["acceptance_coverage"]["coverage_pct"] == 0.0

    def test_present_in_partial_mode(self):
        ins = build_insights(
            _result([_task("t1", "has foo", criteria=["has foo"])]), partial=True,
        )
        assert ins["acceptance_coverage"]["satisfied_criteria"] == 1
