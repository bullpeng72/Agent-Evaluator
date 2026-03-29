"""
tests/test_task_ids_dedup.py
=============================
Round 62 — _task_ids 중복 방지 캐시 테스트

네 개의 트래커(RetryCorrectionTracker, ToolSelectionTracker,
AccuracyEvaluator, ResponseQualityEvaluator)가 런타임·setter·reset 경로
모두에서 _task_ids 집합을 올바르게 유지하는지 검증한다.

또한 PerformanceMonitor.record_task()가 _task_ids를 통해 중복 평가를
방지하는지 통합 수준에서 검증한다.
"""
from datetime import datetime

import pytest

from agent_evaluator.core.trackers.layer1 import AccuracyEvaluator, ResponseQualityEvaluator
from agent_evaluator.core.trackers.layer2 import RetryCorrectionTracker, ToolSelectionTracker
from agent_evaluator import PerformanceMonitor, create_taskresult


# ---------------------------------------------------------------------------
# RetryCorrectionTracker
# ---------------------------------------------------------------------------

class TestRetryCorrectionTrackerTaskIds:
    def test_empty_on_init(self):
        t = RetryCorrectionTracker()
        assert t._task_ids == set()

    def test_ids_populated_on_track(self):
        t = RetryCorrectionTracker()
        t.track_attempts("task_A", [{"success": True, "duration": 0.5}])
        assert "task_A" in t._task_ids

    def test_ids_match_attempts_list(self):
        t = RetryCorrectionTracker()
        for i in range(5):
            t.track_attempts(f"t{i}", [{"success": i % 2 == 0, "duration": 0.1}])
        assert t._task_ids == {f"t{i}" for i in range(5)}

    def test_reset_clears_ids(self):
        t = RetryCorrectionTracker()
        t.track_attempts("x", [{"success": True, "duration": 0.2}])
        t.reset()
        assert t._task_ids == set()
        assert t._attempts == []

    def test_setter_reconstructs_ids(self):
        t = RetryCorrectionTracker()
        t.attempts = [
            {"task_id": "a", "total_attempts": 2},
            {"task_id": "b", "total_attempts": 1},
            {"task_id": None, "total_attempts": 1},  # None must be skipped
        ]
        assert t._task_ids == {"a", "b"}

    def test_setter_skips_missing_task_id(self):
        t = RetryCorrectionTracker()
        t.attempts = [{"total_attempts": 1}]  # no task_id key
        assert t._task_ids == set()


# ---------------------------------------------------------------------------
# ToolSelectionTracker
# ---------------------------------------------------------------------------

class TestToolSelectionTrackerTaskIds:
    def test_empty_on_init(self):
        t = ToolSelectionTracker()
        assert t._task_ids == set()

    def test_ids_populated_on_evaluate(self):
        t = ToolSelectionTracker()
        t.evaluate_selection("task_1", ["search"], ["search"])
        assert "task_1" in t._task_ids

    def test_multiple_evaluations(self):
        t = ToolSelectionTracker()
        for i in range(4):
            t.evaluate_selection(f"t{i}", ["tool_a"], ["tool_a"])
        assert len(t._task_ids) == 4

    def test_reset_clears_ids(self):
        t = ToolSelectionTracker()
        t.evaluate_selection("z", ["x"], ["x"])
        t.reset()
        assert t._task_ids == set()
        assert t._selections == []

    def test_setter_reconstructs_ids(self):
        t = ToolSelectionTracker()
        t.selections = [
            {"task_id": "s1", "f1_score": 100.0},
            {"task_id": "s2", "f1_score": 50.0},
            {"task_id": None},
        ]
        assert t._task_ids == {"s1", "s2"}

    def test_no_expected_tools_still_adds_id(self):
        # evaluate_selection with no expected_tools returns early but appends — check id
        t = ToolSelectionTracker()
        t.evaluate_selection("early_exit", [], ["tool_a"])
        # no expected tools → returns without appending to _selections per current impl
        # the key assertion is that _task_ids tracks whatever was added
        assert len(t._selections) == 0  # early return skips append
        assert "early_exit" not in t._task_ids  # nothing appended


# ---------------------------------------------------------------------------
# AccuracyEvaluator
# ---------------------------------------------------------------------------

class TestAccuracyEvaluatorTaskIds:
    def test_empty_on_init(self):
        e = AccuracyEvaluator()
        assert e._task_ids == set()

    def test_add_evaluation_updates_ids(self):
        e = AccuracyEvaluator()
        e.add_evaluation("t1", "Paris", "Paris", "qa")
        assert "t1" in e._task_ids

    def test_record_score_updates_ids(self):
        e = AccuracyEvaluator()
        e.record_score("t_score", "qa", 0.9)
        assert "t_score" in e._task_ids

    def test_reset_clears_ids(self):
        e = AccuracyEvaluator()
        e.add_evaluation("t1", "a", "a", "qa")
        e.reset()
        assert e._task_ids == set()
        assert e._evaluations == []

    def test_setter_reconstructs_ids(self):
        e = AccuracyEvaluator()
        e.evaluations = [
            {"task_id": "ev1", "accuracy": 0.8, "task_type": "qa"},
            {"task_id": "ev2", "accuracy": 0.5, "task_type": "qa"},
            {"task_id": None, "accuracy": 0.3},
        ]
        assert e._task_ids == {"ev1", "ev2"}

    def test_cached_avg_invalidated_on_reset(self):
        e = AccuracyEvaluator()
        e.add_evaluation("t1", "x", "x", "qa")
        _ = repr(e)  # populate _cached_avg
        assert e._cached_avg is not None
        e.reset()
        assert e._cached_avg is None

    def test_repr_no_data_shows_no_data(self):
        e = AccuracyEvaluator()
        r = repr(e)
        assert "no-data" in r
        assert "evaluations=0" in r

    def test_repr_all_none_accuracy_shows_no_data(self):
        e = AccuracyEvaluator()
        e.record_score("t1", "qa", None)  # accuracy=None
        r = repr(e)
        assert "no-data" in r
        assert "evaluations=1" in r

    def test_repr_with_data_shows_percentage(self):
        e = AccuracyEvaluator()
        e.add_evaluation("t1", "Paris", "Paris", "qa")
        r = repr(e)
        assert "%" in r
        assert "no-data" not in r


# ---------------------------------------------------------------------------
# ResponseQualityEvaluator
# ---------------------------------------------------------------------------

class TestResponseQualityEvaluatorTaskIds:
    def test_empty_on_init(self):
        e = ResponseQualityEvaluator()
        assert e._task_ids == set()

    def test_evaluate_updates_ids(self):
        e = ResponseQualityEvaluator()
        e.evaluate_response("t1", "Good answer", "What is Python?")
        assert "t1" in e._task_ids

    def test_reset_clears_ids(self):
        e = ResponseQualityEvaluator()
        e.evaluate_response("t1", "answer", "question")
        e.reset()
        assert e._task_ids == set()
        assert e._evaluations == []

    def test_setter_reconstructs_ids(self):
        e = ResponseQualityEvaluator()
        e.evaluations = [
            {"task_id": "q1", "total_score": 4.0},
            {"task_id": "q2", "total_score": 3.5},
        ]
        assert e._task_ids == {"q1", "q2"}


# ---------------------------------------------------------------------------
# PerformanceMonitor — _task_ids prevents duplicate evaluation via record_task
# ---------------------------------------------------------------------------

class TestMonitorDedupViaTaskIds:
    """record_task()를 같은 task_id로 두 번 호출해도 quality/accuracy 평가가
    한 번만 실행되는지 검증한다."""

    def _make_monitor(self):
        return PerformanceMonitor(
            enable_hallucination_detection=False,
            enable_security_metrics=False,
        )

    def _make_task(self, task_id: str):
        return create_taskresult(
            task_id=task_id,
            question="What is the capital of France?",
            response="Paris",
            ground_truth="Paris",
            execution_time=1.0,
        )

    def test_single_record_adds_one_quality_eval(self):
        mon = self._make_monitor()
        mon.record_task(self._make_task("unique_001"), request="What is the capital of France?", response="Paris")
        assert len(mon.quality_evaluator._evaluations) == 1

    def test_duplicate_task_id_does_not_add_second_quality_eval(self):
        mon = self._make_monitor()
        task = self._make_task("dup_001")
        mon.record_task(task, request="What is the capital of France?", response="Paris")
        mon.record_task(task, request="What is the capital of France?", response="Paris")
        # quality_evaluator should only have 1 evaluation for this task_id
        evals = [e for e in mon.quality_evaluator._evaluations if e.get("task_id") == "dup_001"]
        assert len(evals) == 1

    def test_different_task_ids_each_get_quality_eval(self):
        mon = self._make_monitor()
        for i in range(3):
            mon.record_task(
                self._make_task(f"task_{i}"),
                request="question",
                response="answer",
            )
        assert len(mon.quality_evaluator._evaluations) >= 3
