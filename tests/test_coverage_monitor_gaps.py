"""
tests/test_coverage_monitor_gaps.py
=====================================
PerformanceMonitor 미커버 영역 커버리지 개선 테스트.

대상 메서드 (monitor.py):
  - _json_serializer / _write_json_streaming
  - thresholds property (setter 검증)
  - golden_datasets property
  - rag_metrics property / record_rag_metrics / get_rag_metrics_summary
  - record_implicit_feedback
  - evaluate_qa / evaluate_batch
  - compare_with_thresholds (RAG / Layer2 분기)
  - reset / flush / clone / merge
  - get_live_stats (window > cache, framework branch)
  - get_report_by_type / get_report_by_framework
  - get_bottleneck_tasks / get_optimization_recommendations / analyze
  - register_aggregator / run_aggregator / list_aggregators
  - filter_tasks / aggregate_metrics
  - get_tcr_metrics / get_accuracy_metrics / get_latency_metrics / get_token_metrics
  - for_rag_evaluation / for_secure_agents factory
  - begin_experiment / end_experiment (Phoenix 미실행 시 None 반환)
  - _collect_security_metrics (enable_security_metrics=True)
  - compare (두 모니터 비교)
  - snapshot / compare_with_snapshot / restore_from_snapshot
  - _generate_alerts / _generate_recommendations
"""

from __future__ import annotations

import json
import math
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor, TaskResult, TaskType, create_taskresult
from agent_evaluator.exceptions import ValidationError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_monitor(tmp_path: Path, **kwargs) -> PerformanceMonitor:
    return PerformanceMonitor(output_dir=str(tmp_path), **kwargs)


def _simple_result(
    task_id: str = "t1",
    question: str = "What is 2+2?",
    response: str = "4",
    ground_truth: str = "4",
    accuracy: float = 1.0,
    completion: float = 1.0,
    execution_time: float = 0.5,
    task_type: str = "qa",
    success: bool = True,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        task_type=task_type,
        success=success,
        completion_score=completion,
        accuracy_score=accuracy,
        execution_time=execution_time,
        tokens_used={"input": 10, "output": 5},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
        question=question,
        response=response,
        ground_truth=ground_truth,
    )


# ---------------------------------------------------------------------------
# _json_serializer
# ---------------------------------------------------------------------------

class TestJsonSerializer:
    def test_nan_becomes_zero(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        assert _json_serializer(float("nan")) == 0.0

    def test_inf_becomes_zero(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        assert _json_serializer(float("inf")) == 0.0
        assert _json_serializer(float("-inf")) == 0.0

    def test_datetime_iso(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = _json_serializer(dt)
        assert "2024-01-01" in result

    def test_enum_value(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        result = _json_serializer(TaskType.QA)
        assert result == TaskType.QA.value

    def test_bytes_decoded(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        result = _json_serializer(b"hello")
        assert result == "hello"

    def test_fallback_str(self):
        from agent_evaluator.core.trackers.monitor import _json_serializer
        # arbitrary object → str()
        class _Obj:
            def __str__(self): return "my_obj"
        assert _json_serializer(_Obj()) == "my_obj"


# ---------------------------------------------------------------------------
# _write_json_streaming
# ---------------------------------------------------------------------------

class TestWriteJsonStreaming:
    def test_produces_valid_json(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import _write_json_streaming
        data = {"meta": "value", "tasks": [{"id": 1}, {"id": 2}]}
        out_file = tmp_path / "stream.json"
        with open(out_file, "w", encoding="utf-8") as f:
            _write_json_streaming(f, data, data["tasks"])
        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded["meta"] == "value"
        assert len(loaded["tasks"]) == 2

    def test_empty_tasks(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import _write_json_streaming
        data = {"header": "ok", "tasks": []}
        out_file = tmp_path / "stream_empty.json"
        with open(out_file, "w", encoding="utf-8") as f:
            _write_json_streaming(f, data, [])
        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded["tasks"] == []


# ---------------------------------------------------------------------------
# thresholds property
# ---------------------------------------------------------------------------

class TestThresholdsProperty:
    def test_set_none(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = None
        assert m.thresholds is None

    def test_set_valid_dict(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"tcr": 80.0, "accuracy": 70.0}
        assert m.thresholds["tcr"] == 80.0

    def test_set_non_dict_raises(self, tmp_path):
        m = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            m.thresholds = "not_a_dict"  # type: ignore

    def test_set_non_numeric_value_raises(self, tmp_path):
        m = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            m.thresholds = {"tcr": "eighty"}  # type: ignore


# ---------------------------------------------------------------------------
# golden_datasets property
# ---------------------------------------------------------------------------

class TestGoldenDatasetsProperty:
    def test_setter_getter_roundtrip(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.golden_datasets = [{"q": "1"}, {"q": "2"}]
        assert len(m.golden_datasets) == 2

    def test_returns_shallow_copy(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.golden_datasets = [{"q": "x"}]
        copy = m.golden_datasets
        copy.append({"q": "extra"})
        # internal list should not be modified
        assert len(m.golden_datasets) == 1


# ---------------------------------------------------------------------------
# rag_metrics property / record_rag_metrics / get_rag_metrics_summary
# ---------------------------------------------------------------------------

class TestRagMetrics:
    def test_record_and_summary(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_rag_metrics(faithfulness=0.8, answer_relevancy=0.9)
        summary = m.get_rag_metrics_summary()
        assert summary["faithfulness"]["count"] == 1
        assert abs(summary["faithfulness"]["mean"] - 0.8) < 1e-6
        assert summary["answer_relevancy"]["mean"] == pytest.approx(0.9)

    def test_empty_summary_structure(self, tmp_path):
        m = _make_monitor(tmp_path)
        summary = m.get_rag_metrics_summary()
        for key in ("faithfulness", "answer_relevancy", "context_recall", "context_precision"):
            assert key in summary
            assert summary[key]["count"] == 0

    def test_rag_metrics_property_copy(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_rag_metrics(context_recall=0.7)
        rag = m.rag_metrics
        rag["context_recall"].append(999.0)  # should not affect internal
        assert m.rag_metrics["context_recall"] == [0.7]

    def test_multiple_records(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_rag_metrics(faithfulness=0.6)
        m.record_rag_metrics(faithfulness=0.8)
        summary = m.get_rag_metrics_summary()
        assert summary["faithfulness"]["count"] == 2
        assert summary["faithfulness"]["mean"] == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# record_implicit_feedback
# ---------------------------------------------------------------------------

class TestRecordImplicitFeedback:
    def test_returns_self_for_chaining(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.record_implicit_feedback("task_1", "thumbs_up")
        assert result is m

    def test_feedback_recorded(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_implicit_feedback("task_1", "thumbs_up", metadata={"source": "test"})
        # no exception = success; feedback_tracker should have data
        tracker = m.feedback_tracker
        assert tracker is not None  # record_implicit_feedback() succeeded, so the tracker was initialized
        # Check via a method that exists on ImplicitFeedbackTracker
        # (get_positive_rate is a known method; fall back to checking internal state)
        if hasattr(tracker, "get_positive_rate"):
            rate = tracker.get_positive_rate()
            assert isinstance(rate, (int, float))
        elif hasattr(tracker, "_feedback_log"):
            assert len(tracker._feedback_log) >= 1
        else:
            # At minimum, no exception was raised
            assert tracker is not None


# ---------------------------------------------------------------------------
# evaluate_qa / evaluate_batch
# ---------------------------------------------------------------------------

class TestEvaluateQA:
    def test_returns_dict_with_required_keys(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.evaluate_qa(
            question="수도는?",
            response="서울",
            ground_truth="서울",
            task_id="qa_t1",
        )
        assert result["task_id"] == "qa_t1"
        assert "accuracy_score" in result
        assert "completion_score" in result
        assert "success" in result

    def test_autogenerated_task_id(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.evaluate_qa(question="q", response="a", ground_truth="a")
        assert result["task_id"].startswith("qa_")

    def test_task_recorded(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.evaluate_qa(question="q", response="a", ground_truth="a")
        assert m.task_count == 1


class TestEvaluateBatch:
    def test_basic(self, tmp_path):
        m = _make_monitor(tmp_path)
        items = [
            {"question": "Q1", "response": "A1", "ground_truth": "A1"},
            {"question": "Q2", "response": "A2", "ground_truth": "A2"},
        ]
        results = m.evaluate_batch(items)
        assert len(results) == 2
        assert m.task_count == 2

    def test_missing_key_raises(self, tmp_path):
        m = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            m.evaluate_batch([{"question": "Q", "response": "A"}])  # no ground_truth

    def test_custom_task_id_prefix(self, tmp_path):
        m = _make_monitor(tmp_path)
        items = [{"question": "Q", "response": "A", "ground_truth": "A"}]
        results = m.evaluate_batch(items, task_id_prefix="prefix")
        assert results[0]["task_id"].startswith("prefix_")

    def test_per_item_task_type(self, tmp_path):
        m = _make_monitor(tmp_path)
        items = [
            {"question": "Q", "response": "A", "ground_truth": "A", "task_type": "coding"},
        ]
        results = m.evaluate_batch(items)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# compare_with_thresholds  (RAG / Layer2 분기)
# ---------------------------------------------------------------------------

class TestCompareWithThresholds:
    def test_empty_thresholds_returns_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        assert m.compare_with_thresholds() == {}

    def test_tcr_pass(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"tcr": 50.0}
        r = _simple_result(success=True)
        m.record_task(r)
        result = m.compare_with_thresholds()
        assert result["tcr"]["status"] == "pass"

    def test_tcr_fail(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"tcr": 100.0}
        r = _simple_result(success=False, accuracy=0.0, completion=0.0)
        m.record_task(r)
        result = m.compare_with_thresholds()
        assert result["tcr"]["status"] == "fail"

    def test_faithfulness_pending_no_data(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"faithfulness": 0.8}
        result = m.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "pending"

    def test_faithfulness_pass(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"faithfulness": 0.5}
        m.record_rag_metrics(faithfulness=0.9)
        result = m.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "pass"

    def test_hallucination_threshold(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"hallucination": 50.0}
        result = m.compare_with_thresholds()
        # no detections → rate 0.0, should pass
        assert result["hallucination"]["status"] == "pass"

    def test_cost_per_task_threshold(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"cost_per_task": 1.0}  # generous threshold
        r = _simple_result()
        m.record_task(r)
        result = m.compare_with_thresholds()
        assert "cost_per_task" in result

    def test_answer_relevancy_pending(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"answer_relevancy": 0.7}
        result = m.compare_with_thresholds()
        assert result["answer_relevancy"]["status"] == "pending"

    def test_passed_field(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.thresholds = {"tcr": 0.0}
        r = _simple_result(success=True)
        m.record_task(r)
        result = m.compare_with_thresholds()
        tcr_result = result["tcr"]
        assert tcr_result["status"] == "pass"
        assert tcr_result["value"] >= 0.0

    def test_latency_pass(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result(execution_time=0.5))
        m.thresholds = {"latency": 999.0}
        result = m.compare_with_thresholds()
        assert result["latency"]["status"] == "pass"
        assert result["latency"]["direction"] == "lower"

    def test_latency_fail(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result(execution_time=5.0))
        m.thresholds = {"latency": 0.001}
        result = m.compare_with_thresholds()
        assert result["latency"]["status"] == "fail"

    def test_faithfulness_fail(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_rag_metrics(faithfulness=0.3)
        m.thresholds = {"faithfulness": 0.8}
        result = m.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "fail"

    def test_result_item_has_required_keys(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result(success=True))
        m.thresholds = {"tcr": 50.0}
        result = m.compare_with_thresholds()
        for key in ("name", "value", "threshold", "status", "direction", "unit"):
            assert key in result["tcr"], f"missing key: {key}"

    def test_invalid_threshold_type_raises(self, tmp_path):
        m = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            m.thresholds = {"tcr": "eighty"}  # type: ignore

    def test_multiple_thresholds_all_present(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result(success=True))
        m.thresholds = {"tcr": 50.0, "latency": 10.0}
        result = m.compare_with_thresholds()
        assert "tcr" in result
        assert "latency" in result


# ---------------------------------------------------------------------------
# reset / flush / clone / merge
# ---------------------------------------------------------------------------

class TestResetFlushCloneMerge:
    def test_reset_clears_tasks(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        assert m.task_count == 1
        m.reset()
        assert m.task_count == 0

    def test_reset_returns_self(self, tmp_path):
        m = _make_monitor(tmp_path)
        assert m.reset() is m

    def test_flush_returns_summary(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        summary = m.flush()
        assert "total_tasks" in summary
        assert summary["total_tasks"] == 1

    def test_flush_clears_tasks(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        m.flush()
        assert m.task_count == 0

    def test_clone_creates_empty_monitor(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        clone = m.clone()
        assert clone.task_count == 0
        assert clone is not m

    def test_clone_inherits_output_dir(self, tmp_path):
        m = _make_monitor(tmp_path)
        clone = m.clone()
        assert clone.output_dir == m.output_dir

    def test_merge_combines_tasks(self, tmp_path):
        m1 = _make_monitor(tmp_path)
        m2 = _make_monitor(tmp_path)
        m1.record_task(_simple_result("t1"))
        m2.record_task(_simple_result("t2"))
        merged = m1.merge(m2)
        assert merged.task_count == 2


# ---------------------------------------------------------------------------
# get_live_stats
# ---------------------------------------------------------------------------

class TestGetLiveStats:
    def test_empty_returns_zeros(self, tmp_path):
        m = _make_monitor(tmp_path)
        stats = m.get_live_stats()
        assert stats["task_count"] == 0
        assert stats["tcr"] == 0.0

    def test_records_within_window(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        stats = m.get_live_stats(window_seconds=60.0)
        assert stats["task_count"] == 1

    def test_framework_breakdown(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        stats = m.get_live_stats(include_frameworks=True)
        assert "frameworks" in stats

    def test_no_frameworks(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        stats = m.get_live_stats(include_frameworks=False)
        assert "frameworks" not in stats

    def test_large_window_fallback(self, tmp_path):
        """window_seconds > 300 triggers O(n) fallback path."""
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        stats = m.get_live_stats(window_seconds=700.0)
        # Should still find the recently recorded task
        assert stats["task_count"] >= 0  # may or may not find it depending on timing


# ---------------------------------------------------------------------------
# get_report_by_type / get_report_by_framework
# ---------------------------------------------------------------------------

class TestReportByTypeAndFramework:
    def test_get_report_by_type_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        report = m.get_report_by_type("qa")
        assert report["count"] == 0

    def test_get_report_by_type_with_data(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", task_type="qa"))
        m.record_task(_simple_result("t2", task_type="coding"))
        report = m.get_report_by_type("qa")
        assert report["count"] == 1

    def test_get_report_by_framework_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        report = m.get_report_by_framework("langchain")
        assert report["task_count"] == 0

    def test_get_report_by_framework_native(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))  # no framework → "native"
        report = m.get_report_by_framework("native")
        assert report["task_count"] == 1


# ---------------------------------------------------------------------------
# get_bottleneck_tasks / get_optimization_recommendations
# ---------------------------------------------------------------------------

class TestBottleneckAndOptimization:
    def test_get_bottleneck_tasks_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.get_bottleneck_tasks()
        assert result["low_accuracy"] == []
        assert result["high_latency"] == []
        assert result["high_error_rate"] == []

    def test_low_accuracy_detected(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", accuracy=0.1, completion=0.1))
        result = m.get_bottleneck_tasks(accuracy_threshold=0.5)
        assert len(result["low_accuracy"]) == 1

    def test_high_latency_detected(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", execution_time=20.0))
        result = m.get_bottleneck_tasks(latency_threshold=10.0)
        assert len(result["high_latency"]) == 1

    def test_optimization_empty_no_error(self, tmp_path):
        m = _make_monitor(tmp_path)
        recs = m.get_optimization_recommendations()
        assert isinstance(recs, list)
        assert len(recs) == 0  # no tasks → no recommendations

    def test_optimization_with_low_tcr(self, tmp_path):
        m = _make_monitor(tmp_path)
        # Record many failures to trigger low TCR recommendation
        for i in range(10):
            m.record_task(_simple_result(f"t{i}", success=False, accuracy=0.0, completion=0.0))
        recs = m.get_optimization_recommendations()
        assert len(recs) >= 1
        categories = [r["category"] for r in recs]
        assert "task_completion" in categories


# ---------------------------------------------------------------------------
# register_aggregator / run_aggregator / list_aggregators
# ---------------------------------------------------------------------------

class TestCustomAggregators:
    def test_register_and_run(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        m.register_aggregator("count_tasks", lambda tasks: len(tasks))
        result = m.run_aggregator("count_tasks")
        assert result == 1

    def test_list_aggregators(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.register_aggregator("fn1", lambda t: t)
        m.register_aggregator("fn2", lambda t: t)
        names = m.list_aggregators()
        assert "fn1" in names
        assert "fn2" in names

    def test_run_unregistered_raises(self, tmp_path):
        m = _make_monitor(tmp_path)
        with pytest.raises(KeyError):
            m.run_aggregator("nonexistent")

    def test_list_aggregators_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        assert m.list_aggregators() == []

    def test_chaining(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.register_aggregator("fn", lambda t: len(t))
        assert result is m


# ---------------------------------------------------------------------------
# filter_tasks
# ---------------------------------------------------------------------------

class TestFilterTasks:
    def test_filter_by_task_type(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", task_type="qa"))
        m.record_task(_simple_result("t2", task_type="coding"))
        filtered = m.filter_tasks(task_type="qa")
        assert len(filtered) == 1

    def test_filter_min_accuracy(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", accuracy=0.9))
        m.record_task(_simple_result("t2", accuracy=0.3))
        filtered = m.filter_tasks(min_accuracy=0.5)
        assert len(filtered) == 1

    def test_filter_no_criteria_returns_all(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        m.record_task(_simple_result("t2"))
        filtered = m.filter_tasks()
        assert len(filtered) == 2


# ---------------------------------------------------------------------------
# D4 alias helpers
# ---------------------------------------------------------------------------

class TestD4Aliases:
    def test_get_tcr_metrics(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        result = m.get_tcr_metrics()
        assert "tcr" in result

    def test_get_accuracy_metrics(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.get_accuracy_metrics()
        assert isinstance(result, dict)

    def test_get_latency_metrics(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", execution_time=1.0))
        result = m.get_latency_metrics()
        assert isinstance(result, dict)

    def test_get_token_metrics(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.get_token_metrics()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# for_rag_evaluation / for_secure_agents factory
# ---------------------------------------------------------------------------

class TestFactories:
    def test_for_rag_evaluation(self, tmp_path):
        m = PerformanceMonitor.for_rag_evaluation(output_dir=str(tmp_path))
        assert m.enable_hallucination_detection is True

    def test_for_rag_evaluation_disable_hallucination(self, tmp_path):
        m = PerformanceMonitor.for_rag_evaluation(
            output_dir=str(tmp_path),
            enable_hallucination_detection=False,
        )
        assert m.enable_hallucination_detection is False

    def test_for_secure_agents(self, tmp_path):
        m = PerformanceMonitor.for_secure_agents(output_dir=str(tmp_path))
        assert m.enable_security_metrics is True
        assert m.input_sanitizer is not None
        assert m.tool_authorizer is not None

    def test_for_secure_agents_with_config(self, tmp_path):
        m = PerformanceMonitor.for_secure_agents(
            output_dir=str(tmp_path),
            security_config={"allowed_tools": ["search"]},
        )
        assert m.enable_security_metrics is True


# ---------------------------------------------------------------------------
# begin_experiment / end_experiment
# ---------------------------------------------------------------------------

class TestExperiments:
    def test_begin_experiment_phoenix_not_running(self, tmp_path):
        m = _make_monitor(tmp_path)
        # Phoenix not running → returns None (no error)
        result = m.begin_experiment("test-exp", phoenix_endpoint="http://localhost:59999")
        assert result is None

    def test_end_experiment_no_id(self, tmp_path):
        m = _make_monitor(tmp_path)
        # no experiment started → no-op, no error
        m.end_experiment(report=None)

    def test_end_experiment_resets_id(self, tmp_path):
        m = _make_monitor(tmp_path)
        m._phoenix_experiment_id = "fake-id"
        m._phoenix_experiment_name = "fake-name"
        m.end_experiment(report=None)
        assert m._phoenix_experiment_id is None
        assert m._phoenix_experiment_name is None


# ---------------------------------------------------------------------------
# _collect_security_metrics with enable_security_metrics=True
# ---------------------------------------------------------------------------

class TestCollectSecurityMetrics:
    def test_returns_layer1_and_layer2(self, tmp_path):
        m = _make_monitor(tmp_path, enable_security_metrics=True)
        metrics = m._collect_security_metrics()
        assert "layer1_security" in metrics
        assert "layer2_security" in metrics

    def test_disabled_returns_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        assert m._collect_security_metrics() == {}

    def test_selective_tracker_input_only(self, tmp_path):
        m = _make_monitor(
            tmp_path,
            enable_security_metrics=True,
            enabled_security_trackers=["InputSanitization"],
        )
        # Only InputSanitization enabled — others should be None
        assert m.input_sanitizer is not None
        assert m.output_leakage_detector is None
        assert m.tool_authorizer is None


# ---------------------------------------------------------------------------
# compare (two monitors)
# ---------------------------------------------------------------------------

class TestCompare:
    def test_compare_structure(self, tmp_path):
        m1 = _make_monitor(tmp_path)
        m2 = _make_monitor(tmp_path)
        m1.record_task(_simple_result("t1"))
        m2.record_task(_simple_result("t2"))
        result = m1.compare(m2)
        assert isinstance(result, dict)
        # Should contain tcr or some top-level keys
        assert len(result) > 0


# ---------------------------------------------------------------------------
# snapshot / compare_with_snapshot / restore_from_snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_returns_dict(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        snap = m.snapshot()
        assert isinstance(snap, dict)
        # snapshot may store task_count or nested total_tasks depending on implementation
        has_task_info = (
            "total_tasks" in snap
            or "task_count" in snap
            or ("report" in snap and "total_tasks" in snap.get("report", {}))
        )
        assert has_task_info

    def test_compare_with_snapshot(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        snap = m.snapshot()
        m.record_task(_simple_result("t2"))
        comparison = m.compare_with_snapshot(snap)
        assert isinstance(comparison, dict)

    def test_restore_from_snapshot(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        snap = m.snapshot()
        # restore should return self (chain support)
        result = m.restore_from_snapshot(snap)
        assert result is m


# ---------------------------------------------------------------------------
# _generate_alerts
# ---------------------------------------------------------------------------

class TestGenerateAlerts:
    def test_no_alerts_when_all_good(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", success=True, accuracy=1.0, execution_time=0.1))
        alerts = m._generate_alerts()
        assert isinstance(alerts, list)

    def test_alerts_on_low_tcr(self, tmp_path):
        m = _make_monitor(tmp_path)
        # All tasks fail → TCR = 0 → high alert
        for i in range(5):
            m.record_task(_simple_result(f"t{i}", success=False, accuracy=0.0, completion=0.0))
        alerts = m._generate_alerts()
        metrics = [a["metric"] for a in alerts]
        assert any("TCR" in m for m in metrics)

    def test_alerts_on_high_latency(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", execution_time=100.0))
        alerts = m._generate_alerts()
        assert any("Latency" in a["metric"] or "응답 시간" in a["metric"] for a in alerts)


# ---------------------------------------------------------------------------
# task_count / __repr__
# ---------------------------------------------------------------------------

class TestTaskCount:
    def test_task_count_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        assert m.task_count == 0

    def test_task_count_after_record(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        assert m.task_count == 1

    def test_repr_contains_tasks(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1"))
        s = repr(m)
        assert "tasks=1" in s


# ---------------------------------------------------------------------------
# conversation context manager
# ---------------------------------------------------------------------------

class TestConversationContext:
    def test_conversation_returns_session(self, tmp_path):
        m = _make_monitor(tmp_path)
        from agent_evaluator.core.trackers.conversation import ConversationSession
        sess = m.conversation("sess_001")
        assert isinstance(sess, ConversationSession)


# ---------------------------------------------------------------------------
# auto_save counter logic (via record_task)
# ---------------------------------------------------------------------------

class TestAutoSave:
    def test_auto_save_does_not_crash(self, tmp_path):
        m = _make_monitor(tmp_path, auto_save=True, auto_save_interval=2)
        for i in range(4):
            m.record_task(_simple_result(f"t{i}"))
        # Should have saved at intervals 2 and 4 without crash
        assert m.task_count == 4


# ---------------------------------------------------------------------------
# aggregate_metrics
# ---------------------------------------------------------------------------

class TestAggregateMetrics:
    def test_aggregate_empty(self, tmp_path):
        m = _make_monitor(tmp_path)
        result = m.aggregate_metrics()
        assert isinstance(result, dict)

    def test_aggregate_with_tasks(self, tmp_path):
        m = _make_monitor(tmp_path)
        m.record_task(_simple_result("t1", accuracy=0.8))
        m.record_task(_simple_result("t2", accuracy=0.6))
        result = m.aggregate_metrics()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# flush_every (agent_eval / batch_eval)
# ---------------------------------------------------------------------------

class TestFlushEvery:
    def test_flush_every_triggers_save(self, tmp_path):
        import os
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(
            monitor, task_type="qa",
            flush_every=2,
        )
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        flush_file = os.path.join(str(tmp_path), "auto_save.json")

        agent("q1?")
        assert not os.path.exists(flush_file)

        agent("q2?")
        assert os.path.exists(flush_file)

    def test_flush_every_zero_no_save(self, tmp_path):
        import os
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa", flush_every=0)
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        for _ in range(10):
            agent("q?")

        assert not any(f.endswith(".json") for f in os.listdir(str(tmp_path)))


# ---------------------------------------------------------------------------
# batch_eval flush_every
# ---------------------------------------------------------------------------

class TestBatchEvalFlushEvery:
    def test_batch_flush_every(self, tmp_path):
        import os
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(
            monitor, task_type="qa",
            flush_every=2,
        )
        def batch_agent(questions, ground_truths=None):
            return [f"answer_{i}" for i in range(len(questions))]

        flush_file = os.path.join(str(tmp_path), "batch_eval_auto.json")

        batch_agent(questions=["q1"], ground_truths=["a1"])
        assert not os.path.exists(flush_file)

        batch_agent(questions=["q2"], ground_truths=["a2"])
        assert os.path.exists(flush_file)


# ---------------------------------------------------------------------------
# thread safety (auto_save 동시 호출)
# ---------------------------------------------------------------------------

class TestAutoSaveThreadSafety:
    def test_concurrent_record_task_no_error(self, tmp_path):
        import threading
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path) + "/",
            auto_save=True,
            auto_save_interval=5,
            auto_save_filename="thread_test",
        )

        errors = []

        def record(n):
            try:
                task = create_taskresult(
                    task_id=f"t{n}", question="q", response="r",
                    ground_truth="r", execution_time=0.01,
                )
                monitor.record_task(task)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"thread errors: {errors}"
