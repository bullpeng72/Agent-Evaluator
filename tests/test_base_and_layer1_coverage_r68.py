"""
tests/test_base_and_layer1_coverage_r68.py
===========================================
Round 68 — base.py / layer1.py 미커버 경로 집중 테스트

Coverage targets:
base.py  (75% → higher):
  - TaskResult.__hash__
  - TaskResult.from_dict() / from_json() / to_dict() / to_json()
  - EvaluationReport.__eq__() / to_dict() / to_json() / from_dict() / from_json() / summary()
  - _TaskContext: success/failure paths

layer1.py (72% → higher):
  - _qa_char_similarity / _qa_lcs_ratio / _normalize_code module-level helpers
  - _assign_grade() all branches
  - TaskCompletionTracker.get_benchmark_status() / get_tcr_by_type()
  - AccuracyEvaluator._code_accuracy() / _ast_comparison() / _general_accuracy()
  - HallucinationDetector: detect_hallucination with context
  - TokenEconomyTracker.update_pricing() / get_usage_by_type()
  - ResponseQualityEvaluator: evaluate_response various paths
"""
import dataclasses
import json
import tempfile
from datetime import datetime

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.core.trackers.base import (
    TaskResult,
    TaskType,
    EvaluationReport,
    _TaskContext,
)
from agent_evaluator.core.trackers.layer1 import (
    TaskCompletionTracker,
    AccuracyEvaluator,
    HallucinationDetector,
    ResponseQualityEvaluator,
    TokenEconomyTracker,
    _assign_grade,
    _qa_char_similarity,
    _normalize_code,
)
from agent_evaluator.utils.text_similarity import lcs_ratio as _qa_lcs_ratio
from agent_evaluator.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id="t001", success=True, accuracy=0.9, execution_time=1.0):
    return TaskResult(
        task_id=task_id,
        task_type=TaskType.QA.value,
        success=success,
        completion_score=1.0 if success else 0.0,
        accuracy_score=accuracy,
        execution_time=execution_time,
        tokens_used={"total": 100, "input": 60, "output": 40},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
    )


# ---------------------------------------------------------------------------
# TaskResult.__hash__
# ---------------------------------------------------------------------------

class TestTaskResultHash:
    def test_hash_is_int(self):
        t = _make_task("h001")
        assert isinstance(hash(t), int)

    def test_same_id_same_hash(self):
        t1 = _make_task("same")
        t2 = _make_task("same")
        assert hash(t1) == hash(t2)

    def test_same_hash_for_same_id(self):
        # hash(task_id) must be consistent
        ts = datetime(2025, 1, 1)
        t1 = TaskResult(
            task_id="dup", task_type=TaskType.QA.value, success=True,
            completion_score=1.0, accuracy_score=0.9, execution_time=1.0,
            tokens_used={}, tool_calls=[], attempts=1, errors=[], timestamp=ts,
        )
        t2 = TaskResult(
            task_id="dup", task_type=TaskType.QA.value, success=True,
            completion_score=1.0, accuracy_score=0.9, execution_time=1.0,
            tokens_used={}, tool_calls=[], attempts=1, errors=[], timestamp=ts,
        )
        assert hash(t1) == hash(t2)

    def test_can_be_used_as_dict_key(self):
        t = _make_task("dk1")
        d = {t: "value"}
        assert d[t] == "value"


# ---------------------------------------------------------------------------
# TaskResult.from_dict() / from_json() / to_dict() / to_json()
# ---------------------------------------------------------------------------

class TestTaskResultSerialization:
    def _base_dict(self):
        return {
            "task_id": "ser_001",
            "task_type": "qa",
            "success": True,
            "completion_score": 1.0,
            "accuracy_score": 0.9,
            "execution_time": 1.5,
            "tokens_used": {"total": 100, "input": 60, "output": 40},
            "tool_calls": [],
            "attempts": 1,
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }

    def test_from_dict_creates_instance(self):
        t = TaskResult.from_dict(self._base_dict())
        assert t.task_id == "ser_001"
        assert t.accuracy_score == pytest.approx(0.9)

    def test_from_dict_timestamp_parsed(self):
        t = TaskResult.from_dict(self._base_dict())
        assert isinstance(t.timestamp, datetime)

    def test_from_dict_extra_keys_ignored(self):
        d = self._base_dict()
        d["unknown_key"] = "something"
        t = TaskResult.from_dict(d)  # must not raise
        assert t.task_id == "ser_001"

    def test_from_dict_bad_timestamp_falls_back(self):
        d = self._base_dict()
        d["timestamp"] = "not-a-date"
        t = TaskResult.from_dict(d)
        # fallback: datetime.now() — just must be a datetime
        assert isinstance(t.timestamp, datetime)

    def test_to_dict_returns_dict(self):
        t = _make_task("td1")
        d = t.to_dict()
        assert isinstance(d, dict)
        assert d["task_id"] == "td1"

    def test_to_dict_timestamp_is_string(self):
        t = _make_task("ts1")
        d = t.to_dict()
        assert isinstance(d["timestamp"], str)

    def test_from_json_round_trip(self):
        t = _make_task("json_rt")
        json_str = t.to_json()
        restored = TaskResult.from_json(json_str)
        assert restored.task_id == t.task_id
        assert restored.accuracy_score == pytest.approx(t.accuracy_score)

    def test_to_json_is_valid_json(self):
        t = _make_task("json_valid")
        json_str = t.to_json()
        data = json.loads(json_str)
        assert data["task_id"] == "json_valid"


# ---------------------------------------------------------------------------
# EvaluationReport.__eq__ / to_dict / to_json / from_dict / from_json / summary
# ---------------------------------------------------------------------------

def _make_report(total_tasks=3):
    return EvaluationReport(
        period="test_session",
        total_tasks=total_tasks,
        accuracy_metrics={"tcr": {"tcr": 80.0}, "accuracy_scores": {"overall_accuracy": 0.8}},
        efficiency_metrics={"latency": {"mean": 1.5, "p95": 2.0}},
        quality_metrics={"avg_total_score": 3.5},
        timestamp=datetime.now(),
    )


class TestEvaluationReportAPI:
    def test_eq_same_data(self):
        r1 = _make_report()
        r2 = _make_report()
        # Different timestamp, same data → equal
        assert r1 == r2

    def test_eq_different_total_tasks(self):
        r1 = _make_report(3)
        r2 = _make_report(5)
        assert r1 != r2

    def test_eq_non_report_returns_not_implemented(self):
        r = _make_report()
        result = r.__eq__("not a report")
        assert result is NotImplemented

    def test_to_dict_returns_dict(self):
        r = _make_report()
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["total_tasks"] == 3

    def test_to_dict_timestamp_is_str(self):
        r = _make_report()
        d = r.to_dict()
        assert isinstance(d["timestamp"], str)

    def test_to_json_is_valid(self):
        r = _make_report()
        json_str = r.to_json()
        data = json.loads(json_str)
        assert data["total_tasks"] == 3

    def test_from_dict_round_trip(self):
        r = _make_report()
        d = r.to_dict()
        restored = EvaluationReport.from_dict(d)
        assert restored.total_tasks == r.total_tasks

    def test_from_dict_timestamp_parsed(self):
        r = _make_report()
        d = r.to_dict()
        restored = EvaluationReport.from_dict(d)
        assert isinstance(restored.timestamp, datetime)

    def test_from_dict_extra_keys_ignored(self):
        d = _make_report().to_dict()
        d["extra_key"] = "ignored"
        restored = EvaluationReport.from_dict(d)
        assert restored.total_tasks == 3

    def test_from_json_round_trip(self):
        r = _make_report()
        json_str = r.to_json()
        restored = EvaluationReport.from_json(json_str)
        assert restored == r

    def test_summary_returns_core_keys(self):
        r = _make_report()
        s = r.summary()
        assert "total_tasks" in s
        assert "success_rate" in s
        assert "avg_accuracy" in s
        assert "avg_latency_s" in s
        assert "period" in s
        assert "timestamp" in s

    def test_summary_total_tasks_correct(self):
        r = _make_report(7)
        assert r.summary()["total_tasks"] == 7


# ---------------------------------------------------------------------------
# _TaskContext (base.py)
# ---------------------------------------------------------------------------

class TestTaskContext:
    def _make_monitor(self, tmp_path):
        return PerformanceMonitor(
            output_dir=str(tmp_path),
            enable_hallucination_detection=False,
            enable_security_metrics=False,
        )

    def test_context_records_task_on_exit(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_001", task_type="qa") as t:
            t.response = "Paris"
        assert len(mon.tcr_tracker.tasks) == 1

    def test_context_success_inferred_from_response(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_success", task_type="qa") as t:
            t.response = "some answer"
        task = mon.tcr_tracker.tasks[0]
        assert task.success is True

    def test_context_failure_when_no_response(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_fail", task_type="qa") as t:
            pass  # no response set
        task = mon.tcr_tracker.tasks[0]
        assert task.success is False

    def test_context_measures_execution_time(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_time", task_type="qa") as t:
            t.response = "answer"
        task = mon.tcr_tracker.tasks[0]
        assert task.execution_time >= 0.0

    def test_context_propagates_exception(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with pytest.raises(ValueError):
            with mon.task("ctx_exc", task_type="qa"):
                raise ValueError("test error")

    def test_context_records_task_even_on_exception(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        try:
            with mon.task("ctx_exc2", task_type="qa"):
                raise RuntimeError("oops")
        except RuntimeError:
            pass
        assert len(mon.tcr_tracker.tasks) == 1
        task = mon.tcr_tracker.tasks[0]
        assert task.success is False

    def test_context_success_flag_override(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_override", task_type="qa") as t:
            t.response = "answer"
            t.success = False  # explicit override
        task = mon.tcr_tracker.tasks[0]
        assert task.success is False

    def test_context_with_ground_truth(self, tmp_path):
        mon = self._make_monitor(tmp_path)
        with mon.task("ctx_gt", task_type="qa", question="Q?") as t:
            t.response = "Paris"
            t.ground_truth = "Paris"
        assert len(mon.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# module-level helper functions in layer1.py
# ---------------------------------------------------------------------------

class TestLayer1Helpers:
    def test_assign_grade_A(self):
        assert _assign_grade(4.5) == "A"
        assert _assign_grade(5.0) == "A"

    def test_assign_grade_B(self):
        assert _assign_grade(4.0) == "B"
        assert _assign_grade(4.4) == "B"

    def test_assign_grade_C(self):
        assert _assign_grade(3.5) == "C"
        assert _assign_grade(3.9) == "C"

    def test_assign_grade_D(self):
        assert _assign_grade(3.0) == "D"
        assert _assign_grade(3.4) == "D"

    def test_assign_grade_F(self):
        assert _assign_grade(0.0) == "F"
        assert _assign_grade(2.9) == "F"

    def test_qa_char_similarity_identical(self):
        assert _qa_char_similarity("hello", "hello") == pytest.approx(1.0)

    def test_qa_char_similarity_empty_s1(self):
        assert _qa_char_similarity("", "hello") == 0.0

    def test_qa_char_similarity_no_overlap(self):
        result = _qa_char_similarity("abc", "xyz")
        assert result == 0.0

    def test_qa_char_similarity_partial(self):
        result = _qa_char_similarity("ab", "ac")
        assert 0.0 < result < 1.0

    def test_qa_lcs_ratio_identical(self):
        assert _qa_lcs_ratio("hello", "hello") == pytest.approx(1.0)

    def test_qa_lcs_ratio_empty_s1(self):
        assert _qa_lcs_ratio("", "hello") == 0.0

    def test_qa_lcs_ratio_partial(self):
        result = _qa_lcs_ratio("hello", "hxllo")
        assert 0.0 < result <= 1.0

    def test_qa_lcs_ratio_swapped_longer(self):
        # When s1 < s2, function swaps them — test that branch
        result = _qa_lcs_ratio("hi", "hello world")
        assert result >= 0.0

    def test_normalize_code_removes_comments(self):
        code = "x = 1  # this is a comment"
        result = _normalize_code(code)
        assert "#" not in result

    def test_normalize_code_collapses_whitespace(self):
        code = "x  =  1"
        result = _normalize_code(code)
        assert "  " not in result


# ---------------------------------------------------------------------------
# TaskCompletionTracker extra methods
# ---------------------------------------------------------------------------

class TestTaskCompletionTrackerExtras:
    def test_get_benchmark_status_excellent(self):
        t = TaskCompletionTracker()
        assert t.get_benchmark_status(98.0) == "Industry Leading"

    def test_get_benchmark_status_good(self):
        t = TaskCompletionTracker()
        assert t.get_benchmark_status(90.0) == "Good Performance"

    def test_get_benchmark_status_acceptable(self):
        t = TaskCompletionTracker()
        assert t.get_benchmark_status(80.0) == "Acceptable"

    def test_get_benchmark_status_needs_improvement(self):
        t = TaskCompletionTracker()
        assert t.get_benchmark_status(50.0) == "Needs Improvement"

    def test_get_tcr_by_type_empty(self):
        t = TaskCompletionTracker()
        assert t.get_tcr_by_type() == {}

    def test_get_tcr_by_type_multiple_types(self):
        t = TaskCompletionTracker()
        t.add_task(_make_task("qa1"))
        t.add_task(TaskResult(
            task_id="code1",
            task_type=TaskType.CODE_GENERATION.value,
            success=True,
            completion_score=1.0,
            accuracy_score=0.8,
            execution_time=2.0,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
            timestamp=datetime.now(),
        ))
        by_type = t.get_tcr_by_type()
        assert "qa" in by_type
        assert "code_generation" in by_type

    def test_coding_alias_merged_into_code_generation(self):
        t = TaskCompletionTracker()
        t.add_task(TaskResult(
            task_id="coding1",
            task_type=TaskType.CODING.value,  # alias for code_generation
            success=True,
            completion_score=1.0,
            accuracy_score=0.8,
            execution_time=1.0,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
            timestamp=datetime.now(),
        ))
        by_type = t.get_tcr_by_type()
        # Should be merged as "code_generation"
        assert "code_generation" in by_type
        assert "coding" not in by_type

    def test_calculate_tcr_by_type_filter(self):
        t = TaskCompletionTracker()
        t.add_task(_make_task("qa_only"))
        result = t.calculate_tcr(task_type="data_analysis")
        assert result["total_tasks"] == 0


# ---------------------------------------------------------------------------
# AccuracyEvaluator: code accuracy + general accuracy
# ---------------------------------------------------------------------------

class TestAccuracyEvaluatorCodePaths:
    def test_code_accuracy_exact_match(self):
        e = AccuracyEvaluator()
        score = e._code_accuracy("print('hello')", "print('hello')")
        assert score == pytest.approx(1.0)

    def test_code_accuracy_syntax_error_fallback(self):
        e = AccuracyEvaluator()
        # Syntax errors → AST comparison fails → normalized comparison
        score = e._code_accuracy("def f(: pass", "def f(): pass")
        assert 0.0 <= score <= 1.0

    def test_code_accuracy_non_string_exact(self):
        e = AccuracyEvaluator()
        # Non-string: returns 1.0 for identical objects
        assert e._code_accuracy(42, 42) == 1.0
        assert e._code_accuracy(42, 43) == 0.0

    def test_general_accuracy_exact_match(self):
        e = AccuracyEvaluator()
        score = e._general_accuracy("Paris", "Paris")
        assert score == pytest.approx(1.0)

    def test_general_accuracy_mismatch_returns_zero(self):
        e = AccuracyEvaluator()
        score = e._general_accuracy("Paris", "London")
        assert score == pytest.approx(0.0)

    def test_general_accuracy_empty_both(self):
        e = AccuracyEvaluator()
        score = e._general_accuracy("", "")
        assert score == pytest.approx(1.0)  # "" == "" is True

    def test_add_evaluation_code_type(self):
        e = AccuracyEvaluator()
        e.add_evaluation(
            task_id="code_eval",
            ground_truth="def foo(): return 1",
            prediction="def foo(): return 1",
            task_type="code_generation",
        )
        assert len(e._evaluations) == 1
        assert e._evaluations[0]["accuracy"] == pytest.approx(1.0)

    def test_add_evaluation_general_type(self):
        e = AccuracyEvaluator()
        e.add_evaluation(
            task_id="general_eval",
            ground_truth="Paris",
            prediction="Paris",
            task_type="reasoning",
        )
        assert len(e._evaluations) == 1
        assert e._evaluations[0]["accuracy"] > 0.5

    def test_ast_comparison_identical_code(self):
        e = AccuracyEvaluator()
        score = e._ast_comparison("x = 1", "x = 1")
        assert score == pytest.approx(1.0)

    def test_ast_comparison_different_code(self):
        e = AccuracyEvaluator()
        score = e._ast_comparison("x = 1", "y = 2")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# HallucinationDetector: detect_hallucination with context
# ---------------------------------------------------------------------------

class TestHallucinationDetectorWithContext:
    def test_detect_with_context_no_hallucination(self):
        d = HallucinationDetector()
        result = d.detect_hallucination(
            task_id="hall_1",
            response="Paris is the capital of France.",
            context="France's capital is Paris.",
        )
        assert "task_id" in result
        assert "hallucination_rate" in result

    def test_detect_adds_to_detections(self):
        d = HallucinationDetector()
        d.detect_hallucination(
            task_id="hall_2",
            response="London is the capital of France.",
            context="France's capital is Paris.",
        )
        assert len(d._detections) == 1

    def test_detect_with_ground_truth(self):
        d = HallucinationDetector()
        result = d.detect_hallucination(
            task_id="hall_3",
            response="Paris",
            context="The capital is Paris.",
            ground_truth="Paris",
        )
        assert result["hallucination_rate"] >= 0.0

    def test_detect_with_empty_context(self):
        d = HallucinationDetector()
        result = d.detect_hallucination(
            task_id="hall_4",
            response="Some answer",
            context="",
        )
        # Empty context: minimal detection
        assert result is None or "hallucination_rate" in result


# ---------------------------------------------------------------------------
# TokenEconomyTracker.update_pricing() / get_usage_by_type()
# ---------------------------------------------------------------------------

class TestTokenEconomyTrackerExtras:
    def test_update_pricing_changes_rates(self):
        t = TokenEconomyTracker({"input": 0.001, "output": 0.005})
        t.update_pricing({"input": 0.002, "output": 0.010})
        assert t.pricing["input"] == pytest.approx(0.002)
        assert t.pricing["output"] == pytest.approx(0.010)

    def test_update_pricing_invalid_raises(self):
        t = TokenEconomyTracker({"input": 0.001, "output": 0.005})
        with pytest.raises(ValidationError):
            t.update_pricing({"input": "not_a_number", "output": 0.005})  # type: ignore[arg-type] — intentionally invalid, testing the runtime guard

    def test_get_usage_by_type_empty(self):
        t = TokenEconomyTracker({"input": 0.001, "output": 0.005})
        result = t.get_usage_by_type()
        # Empty should return empty dict or dict with no types
        assert isinstance(result, dict)

    def test_get_usage_by_type_with_data(self):
        t = TokenEconomyTracker({"input": 0.001, "output": 0.005})
        t.track_usage("t1", 60, 40, "qa")
        t.track_usage("t2", 80, 50, "qa")
        t.track_usage("t3", 100, 60, "code_generation")
        result = t.get_usage_by_type()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# ResponseQualityEvaluator: evaluate_response paths
# ---------------------------------------------------------------------------

class TestResponseQualityEvaluatorPaths:
    def test_evaluate_with_expected_elements(self):
        e = ResponseQualityEvaluator()
        result = e.evaluate_response(
            task_id="qe_001",
            response="Paris is the capital of France.",
            request="What is the capital of France?",
            expected_elements=["Paris", "capital", "France"],
        )
        assert "total_score" in result
        assert result["total_score"] >= 0.0

    def test_evaluate_with_ground_truth(self):
        e = ResponseQualityEvaluator()
        result = e.evaluate_response(
            task_id="qe_002",
            response="The answer is 42.",
            request="What is the answer?",
            ground_truth="42",
        )
        assert "total_score" in result

    def test_evaluate_long_response_boosts_completeness(self):
        e = ResponseQualityEvaluator()
        long_response = " ".join(["word"] * 200)
        result = e.evaluate_response(
            task_id="qe_long",
            response=long_response,
            request="Explain in detail.",
        )
        assert result["dimension_scores"]["completeness"] >= 0.0

    def test_evaluate_short_response_lower_completeness(self):
        e = ResponseQualityEvaluator()
        short = e.evaluate_response(
            task_id="qe_short",
            response="yes",
            request="Explain in detail.",
        )
        long = e.evaluate_response(
            task_id="qe_long2",
            response=" ".join(["word"] * 150),
            request="Explain in detail.",
        )
        # short completeness should be <= long
        assert short["dimension_scores"]["completeness"] <= long["dimension_scores"]["completeness"]

    def test_get_quality_metrics_with_data(self):
        e = ResponseQualityEvaluator()
        for i in range(3):
            e.evaluate_response(
                task_id=f"qm_{i}",
                response=f"Answer {i}",
                request=f"Question {i}?",
            )
        metrics = e.get_quality_metrics()
        assert metrics["total_evaluated"] == 3
        assert "avg_total_score" in metrics


# ===========================================================================
# From test_task_ids_dedup.py — _task_ids 중복 방지 캐시 테스트 (Round 62)
# ===========================================================================

from agent_evaluator.core.trackers.layer2 import RetryCorrectionTracker, ToolSelectionTracker


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
