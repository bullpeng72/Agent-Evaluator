"""
tests/test_spec043_eval_set_delta.py
====================================
SPEC-043 REQ-2 — eval-set versioning + change ↔ score attribution
(``lineage.eval_set_hash`` / ``eval_set_size`` + ``insights.eval_set_delta``).
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.insights import (
    _eval_set_delta_section,
    build_insights,
)


def _task(tid, *, ok=True):
    return {
        "task_id": tid,
        "success": ok,
        "accuracy_score": 0.95 if ok else 0.2,
        "completion_score": 1.0 if ok else 0.1,
        "question": f"q-{tid}",
        "response": "r",
        "ground_truth": "r",
        "task_type": "qa",
    }


def _result(tasks, *, eval_set_hash=None, eval_set_size=None):
    lineage = {}
    if eval_set_hash is not None:
        lineage["eval_set_hash"] = eval_set_hash
    if eval_set_size is not None:
        lineage["eval_set_size"] = eval_set_size
    return {
        "summary": {"tcr": 0.0, "total_tasks": len(tasks)},
        "extra_metrics": {
            "harness_groups": {"A": {"score": 0.8, "status": "pass"}},
            "lineage": lineage,
        },
        "tasks": tasks,
    }


# --------------------------------------------------------------------------- #
# lineage stamping
# --------------------------------------------------------------------------- #
class TestLineageEvalSetHash:
    def test_monitor_stamps_hash_and_size(self, tmp_path):
        mon = PerformanceMonitor(output_dir=str(tmp_path))
        for i in range(3):
            mon.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}", response="a",
                ground_truth="a", execution_time=0.1,
            ))
        path = mon.save_to_file("run")
        import json

        data = json.loads(open(path).read())
        lin = data["extra_metrics"]["lineage"]
        assert isinstance(lin["eval_set_hash"], str) and len(lin["eval_set_hash"]) == 16
        assert lin["eval_set_size"] == 3

    def test_hash_is_content_stable_order_independent(self, tmp_path):
        def _hash_for(order):
            mon = PerformanceMonitor(output_dir=str(tmp_path))
            for i in order:
                mon.record_task(create_taskresult(
                    task_id=f"t{i}", question=f"q{i}", response="a",
                    ground_truth=f"gt{i}", execution_time=0.1,
                ))
            return mon._build_lineage()["eval_set_hash"]

        assert _hash_for([0, 1, 2]) == _hash_for([2, 0, 1])

    def test_hash_changes_when_a_case_changes(self, tmp_path):
        mon_a = PerformanceMonitor(output_dir=str(tmp_path))
        mon_b = PerformanceMonitor(output_dir=str(tmp_path))
        for i in range(3):
            mon_a.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}", response="a",
                ground_truth="a", execution_time=0.1,
            ))
        for i in range(3):
            mon_b.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}-EDITED", response="a",
                ground_truth="a", execution_time=0.1,
            ))
        assert mon_a._build_lineage()["eval_set_hash"] != \
            mon_b._build_lineage()["eval_set_hash"]


# --------------------------------------------------------------------------- #
# _eval_set_delta_section
# --------------------------------------------------------------------------- #
class TestEvalSetDeltaSection:
    def test_none_without_baseline(self):
        assert _eval_set_delta_section(_result([_task("a")]), None) is None

    def test_none_when_hashes_missing(self):
        cur = _result([_task("a")])
        base = _result([_task("a")])
        assert _eval_set_delta_section(cur, base) is None

    def test_none_when_hashes_equal(self):
        cur = _result([_task("a")], eval_set_hash="same")
        base = _result([_task("a")], eval_set_hash="same")
        assert _eval_set_delta_section(cur, base) is None

    def test_decomposition_isolates_eval_set_change(self):
        # baseline: t1,t2 pass / t3,t4 fail  -> full TCR 50%
        base = _result(
            [_task("t1"), _task("t2"), _task("t3", ok=False), _task("t4", ok=False)],
            eval_set_hash="base", eval_set_size=4,
        )
        # current: dropped the two hard cases (t3,t4), added t5 (pass), t6 (fail)
        # t1,t2 still pass -> common-set agent movement 0pp; full TCR 75%
        cur = _result(
            [_task("t1"), _task("t2"), _task("t5"), _task("t6", ok=False)],
            eval_set_hash="cur", eval_set_size=4,
        )
        d = _eval_set_delta_section(cur, base)
        assert d is not None
        assert d["attributable"] is True
        assert d["added_cases"] == 2 and d["removed_cases"] == 2
        assert d["common_cases"] == 2
        assert d["tcr_movement_pp"] == 25.0
        assert d["attributable_to_agent_pp"] == 0.0
        assert d["attributable_to_eval_set_change_pp"] == 25.0

    def test_agent_movement_when_common_set_shifts(self):
        base = _result(
            [_task("t1"), _task("t2", ok=False)],
            eval_set_hash="base",
        )
        # same task_ids, t2 now passes -> pure agent gain, no eval-set change term
        cur = _result(
            [_task("t1"), _task("t2"), _task("t3")],
            eval_set_hash="cur",
        )
        d = _eval_set_delta_section(cur, base)
        assert d is not None
        assert d["common_cases"] == 2
        assert d["attributable_to_agent_pp"] == 50.0

    def test_no_common_ids_not_attributable(self):
        base = _result([_task("a"), _task("b")], eval_set_hash="base")
        cur = _result([_task("x"), _task("y")], eval_set_hash="cur")
        d = _eval_set_delta_section(cur, base)
        assert d is not None
        assert d["attributable"] is False
        assert "cannot be split" in d["note"]


# --------------------------------------------------------------------------- #
# build_insights wiring
# --------------------------------------------------------------------------- #
class TestBuildInsightsWiring:
    def test_eval_set_delta_key_present_with_baseline(self):
        base = _result(
            [_task("t1"), _task("t2"), _task("t3", ok=False)],
            eval_set_hash="base",
        )
        cur = _result(
            [_task("t1"), _task("t2"), _task("t4", ok=False)],
            eval_set_hash="cur",
        )
        ins = build_insights(cur, base)
        assert "eval_set_delta" in ins
        assert ins["eval_set_delta"]["attributable"] is True

    def test_eval_set_delta_null_when_no_change(self):
        cur = _result([_task("t1")], eval_set_hash="same")
        base = _result([_task("t1")], eval_set_hash="same")
        ins = build_insights(cur, base)
        assert ins["eval_set_delta"] is None

    def test_regression_attribution_mentions_eval_set(self):
        # a real regression (t1 passed, now fails) plus an eval-set change
        base = _result(
            [_task("t1"), _task("t2"), _task("h1", ok=False), _task("h2", ok=False)],
            eval_set_hash="base",
        )
        cur = _result(
            [_task("t1", ok=False), _task("t2"), _task("n1"), _task("n2")],
            eval_set_hash="cur",
        )
        ins = build_insights(cur, base)
        ra = ins.get("regression_attribution")
        assert ra is not None
        assert ra.get("eval_set_changed") is True
        assert "eval-set change" in ra["note"]

    def test_partial_mode_has_no_eval_set_delta(self):
        cur = _result([_task("t1")], eval_set_hash="cur")
        ins = build_insights(cur, partial=True)
        assert "eval_set_delta" not in ins
