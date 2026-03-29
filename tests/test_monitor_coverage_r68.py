"""
tests/test_monitor_coverage_r68.py
====================================
Round 68 — PerformanceMonitor 주요 미커버 경로 집중 테스트

Coverage targets (monitor.py 36% → higher):
- factory classmethods: for_rag_evaluation(), for_secure_agents()
- record_task() deprecated-param code paths, hallucination trigger, retry trigger
- record_rag_metrics() + get_rag_metrics_summary()
- reset() verifies all trackers cleared
- flush() returns summary and clears state
- generate_report() with security_metrics enabled
- save_to_file() / load_from_file() round-trip
- __repr__() method
- _generate_alerts() branches
- rag_metrics property isolation (shallow copy)
"""
import json
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.core.trackers.base import TaskResult, TaskType
from agent_evaluator.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(
    task_id: str = "t001",
    success: bool = True,
    accuracy: float = 0.9,
    execution_time: float = 1.0,
    attempts: int = 1,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        task_type=TaskType.QA,
        success=success,
        completion_score=1.0 if success else 0.0,
        accuracy_score=accuracy,
        execution_time=execution_time,
        tokens_used={"total": 100, "input": 60, "output": 40},
        tool_calls=[],
        attempts=attempts,
        errors=[],
        timestamp=datetime.now(),
    )


def _make_monitor(tmp_path=None, **kwargs) -> PerformanceMonitor:
    out = str(tmp_path) if tmp_path else tempfile.mkdtemp()
    return PerformanceMonitor(
        output_dir=out,
        enable_hallucination_detection=False,
        enable_security_metrics=False,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Factory classmethods
# ---------------------------------------------------------------------------

class TestFactoryClassmethods:
    def test_for_rag_evaluation_creates_monitor(self, tmp_path):
        mon = PerformanceMonitor.for_rag_evaluation(output_dir=str(tmp_path))
        assert isinstance(mon, PerformanceMonitor)
        assert mon.enable_hallucination_detection is True

    def test_for_rag_evaluation_disable_hallucination(self, tmp_path):
        mon = PerformanceMonitor.for_rag_evaluation(
            output_dir=str(tmp_path),
            enable_hallucination_detection=False,
        )
        assert mon.enable_hallucination_detection is False

    def test_for_secure_agents_creates_monitor(self, tmp_path):
        mon = PerformanceMonitor.for_secure_agents(output_dir=str(tmp_path))
        assert isinstance(mon, PerformanceMonitor)
        assert mon.enable_security_metrics is True
        assert mon.input_sanitizer is not None
        assert mon.output_leakage_detector is not None

    def test_for_secure_agents_with_config(self, tmp_path):
        config = {"allowed_tools": ["search", "calculator"]}
        mon = PerformanceMonitor.for_secure_agents(
            security_config=config,
            output_dir=str(tmp_path),
        )
        assert mon.enable_security_metrics is True
        assert mon.tool_authorizer is not None


# ---------------------------------------------------------------------------
# record_task() deprecated params
# ---------------------------------------------------------------------------

class TestRecordTaskDeprecatedParams:
    def test_deprecated_request_warns(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = _make_task("dep_req")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mon.record_task(task, request="what?")
        assert any("request" in str(warning.message) for warning in w)

    def test_deprecated_response_warns(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = _make_task("dep_res")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mon.record_task(task, response="answer")
        assert any("response" in str(warning.message) for warning in w)

    def test_deprecated_ground_truth_warns(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = _make_task("dep_gt")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mon.record_task(task, ground_truth="expected")
        assert any("ground_truth" in str(warning.message) for warning in w)

    def test_request_fills_empty_question(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = _make_task("fill_q")  # question="" by default
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            mon.record_task(task, request="Test question?")
        # Quality evaluator triggered because request+response now non-empty
        # (response comes from task_result.response which may be empty too)
        # Just verify no exception raised
        assert len(mon.tcr_tracker.tasks) == 1

    def test_record_task_with_question_response_triggers_quality(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = create_taskresult(
            task_id="q_qual",
            question="Capital of France?",
            response="Paris",
            execution_time=1.0,
        )
        mon.record_task(task)
        assert len(mon.quality_evaluator._evaluations) == 1

    def test_record_task_with_ground_truth_triggers_quality(self, tmp_path):
        """Tasks with question+response trigger quality_evaluator."""
        mon = _make_monitor(tmp_path)
        task = create_taskresult(
            task_id="gt_qual",
            question="Q?",
            response="Paris",
            ground_truth="Paris",
            execution_time=1.0,
        )
        mon.record_task(task)
        # quality_evaluator triggered because question+response are set
        assert any(
            e.get("task_id") == "gt_qual"
            for e in mon.quality_evaluator._evaluations
        )

    def test_record_task_with_attempts_gt1_triggers_retry(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = _make_task("retry_task", attempts=3)
        mon.record_task(task)
        assert len(mon.retry_tracker._attempts) >= 1

    def test_record_task_with_tool_calls_triggers_tool_analyzer(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = TaskResult(
            task_id="tool_task",
            task_type=TaskType.QA,
            success=True,
            completion_score=1.0,
            accuracy_score=0.9,
            execution_time=1.0,
            tokens_used={"total": 100, "input": 60, "output": 40},
            tool_calls=[{"tool_name": "search", "success": True, "duration": 0.5}],
            attempts=1,
            errors=[],
            timestamp=datetime.now(),
        )
        mon.record_task(task)
        assert len(mon.tool_analyzer._executions) == 1

    def test_record_task_method_chaining(self, tmp_path):
        mon = _make_monitor(tmp_path)
        result = (
            mon
            .record_task(_make_task("c1"))
            .record_task(_make_task("c2"))
            .record_task(_make_task("c3"))
        )
        assert result is mon
        assert len(mon.tcr_tracker.tasks) == 3


# ---------------------------------------------------------------------------
# record_rag_metrics() + get_rag_metrics_summary()
# ---------------------------------------------------------------------------

class TestRagMetrics:
    def test_record_faithfulness(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=0.85)
        assert 0.85 in mon._rag_metrics["faithfulness"]

    def test_record_all_rag_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(
            faithfulness=0.9,
            answer_relevancy=0.8,
            context_recall=0.7,
            context_precision=0.6,
        )
        assert len(mon._rag_metrics["faithfulness"]) == 1
        assert len(mon._rag_metrics["answer_relevancy"]) == 1
        assert len(mon._rag_metrics["context_recall"]) == 1
        assert len(mon._rag_metrics["context_precision"]) == 1

    def test_rag_metrics_property_is_shallow_copy(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=0.9)
        snapshot = mon.rag_metrics
        snapshot["faithfulness"].append(99.0)  # mutate the copy
        # Internal state must be unchanged
        assert 99.0 not in mon._rag_metrics["faithfulness"]

    def test_get_rag_metrics_summary_empty(self, tmp_path):
        mon = _make_monitor(tmp_path)
        summary = mon.get_rag_metrics_summary()
        assert summary["faithfulness"]["count"] == 0
        assert summary["faithfulness"]["mean"] == 0.0

    def test_get_rag_metrics_summary_with_data(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=0.8)
        mon.record_rag_metrics(faithfulness=1.0)
        summary = mon.get_rag_metrics_summary()
        assert summary["faithfulness"]["count"] == 2
        assert summary["faithfulness"]["mean"] == pytest.approx(0.9, abs=0.01)
        assert summary["faithfulness"]["min"] == pytest.approx(0.8, abs=0.01)
        assert summary["faithfulness"]["max"] == pytest.approx(1.0, abs=0.01)
        # std > 0 for two different values
        assert summary["faithfulness"]["std"] > 0

    def test_record_none_rag_metrics_skipped(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=None, answer_relevancy=None)
        assert len(mon._rag_metrics["faithfulness"]) == 0


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all_trackers(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(5):
            mon.record_task(_make_task(f"r_{i}"))
        assert len(mon.tcr_tracker.tasks) == 5
        mon.reset()
        assert len(mon.tcr_tracker.tasks) == 0
        assert len(mon.latency_tracker._latencies) == 0
        assert len(mon.accuracy_evaluator._evaluations) == 0

    def test_reset_clears_rag_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=0.9)
        mon.reset()
        assert len(mon._rag_metrics["faithfulness"]) == 0

    def test_reset_clears_conversation_sessions(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.conversation_sessions.append({"session_id": "s1"})
        mon.reset()
        assert len(mon.conversation_sessions) == 0

    def test_reset_preserves_config(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.thresholds = {"tcr": 80.0}
        mon.record_task(_make_task("pre_reset"))
        mon.reset()
        # Config preserved after reset
        assert mon.thresholds == {"tcr": 80.0}
        assert mon.output_dir is not None


# ---------------------------------------------------------------------------
# flush()
# ---------------------------------------------------------------------------

class TestFlush:
    def test_flush_returns_summary(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(3):
            mon.record_task(_make_task(f"f_{i}"))
        summary = mon.flush()
        assert summary["total_tasks"] == 3
        assert "success_rate" in summary
        assert "avg_latency_s" in summary
        assert "avg_accuracy" in summary
        assert "flushed_at" in summary

    def test_flush_clears_tasks(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_task(_make_task("pre_flush"))
        mon.flush()
        assert len(mon.tcr_tracker.tasks) == 0

    def test_flush_clears_rag_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_rag_metrics(faithfulness=0.8)
        mon.flush()
        assert len(mon._rag_metrics["faithfulness"]) == 0

    def test_flush_empty_monitor_returns_zero_tasks(self, tmp_path):
        mon = _make_monitor(tmp_path)
        summary = mon.flush()
        assert summary["total_tasks"] == 0


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_no_tasks(self, tmp_path):
        mon = _make_monitor(tmp_path)
        r = repr(mon)
        assert "PerformanceMonitor" in r
        assert "tasks=0" in r

    def test_repr_with_tasks(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_task(_make_task("rep_1", success=True))
        mon.record_task(_make_task("rep_2", success=False))
        r = repr(mon)
        assert "tasks=2" in r
        assert "tcr=" in r

    def test_repr_with_security_on(self, tmp_path):
        mon = PerformanceMonitor(
            output_dir=str(tmp_path),
            enable_security_metrics=True,
            enable_hallucination_detection=False,
        )
        r = repr(mon)
        assert "security=on" in r

    def test_repr_with_hallucination_on(self, tmp_path):
        mon = PerformanceMonitor(
            output_dir=str(tmp_path),
            enable_hallucination_detection=True,
            enable_security_metrics=False,
        )
        r = repr(mon)
        assert "hallucination=on" in r


# ---------------------------------------------------------------------------
# save_to_file() / load_from_file() round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def _populate(self, mon, n=5):
        for i in range(n):
            mon.record_task(create_taskresult(
                task_id=f"task_{i:03d}",
                question="Q?",
                response="A",
                ground_truth="A",
                execution_time=1.0 + i * 0.1,
            ))
        mon.record_rag_metrics(faithfulness=0.9, answer_relevancy=0.8)

    def test_save_returns_filepath(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "out.json"))
        assert path.endswith(".json")
        assert Path(path).exists()

    def test_save_creates_valid_json(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "out.json"))
        with open(path) as f:
            data = json.load(f)
        assert "tasks" in data
        assert len(data["tasks"]) == 5

    def test_load_restores_task_count(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "round_trip.json"))
        loaded = PerformanceMonitor.load_from_file(path)
        assert len(loaded.tcr_tracker.tasks) == 5

    def test_load_restores_rag_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "rag.json"))
        loaded = PerformanceMonitor.load_from_file(path)
        # RAG faithfulness was recorded
        assert len(loaded._rag_metrics["faithfulness"]) >= 1

    def test_load_restores_quality_evaluations(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        n_before = len(mon.quality_evaluator._evaluations)
        path = mon.save_to_file(str(tmp_path / "quality.json"))
        loaded = PerformanceMonitor.load_from_file(path)
        assert len(loaded.quality_evaluator._evaluations) == n_before

    def test_save_json_contains_evaluators_key(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "ev.json"))
        with open(path) as f:
            data = json.load(f)
        assert "evaluators" in data

    def test_save_json_contains_rag_metrics_key(self, tmp_path):
        mon = _make_monitor(tmp_path)
        self._populate(mon)
        path = mon.save_to_file(str(tmp_path / "rm.json"))
        with open(path) as f:
            data = json.load(f)
        assert "rag_metrics" in data


# ---------------------------------------------------------------------------
# generate_report() paths
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_with_security_enabled(self, tmp_path):
        mon = PerformanceMonitor(
            output_dir=str(tmp_path),
            enable_security_metrics=True,
            enable_hallucination_detection=False,
        )
        mon.record_task(_make_task("sec_001"))
        report = mon.generate_report()
        assert report is not None
        assert report.total_tasks == 1

    def test_report_security_metrics_populated(self, tmp_path):
        mon = PerformanceMonitor(
            output_dir=str(tmp_path),
            enable_security_metrics=True,
            enable_hallucination_detection=False,
        )
        mon.record_task(_make_task("sec_002"))
        report = mon.generate_report()
        # security_metrics should contain layer1_security and layer2_security
        assert "layer1_security" in report.security_metrics
        assert "layer2_security" in report.security_metrics

    def test_report_empty_monitor_no_exception(self, tmp_path):
        mon = _make_monitor(tmp_path)
        report = mon.generate_report()
        assert report.total_tasks == 0

    def test_report_contains_quality_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = create_taskresult(
            task_id="qual_rpt",
            question="What is 2+2?",
            response="4",
            execution_time=0.5,
        )
        mon.record_task(task)
        report = mon.generate_report()
        assert report.quality_metrics is not None


# ---------------------------------------------------------------------------
# _generate_alerts() branches
# ---------------------------------------------------------------------------

class TestGenerateAlerts:
    def _mon_with_low_tcr(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(5):
            mon.record_task(_make_task(f"la_{i}", success=False))
        return mon

    def test_low_tcr_generates_alert(self, tmp_path):
        mon = self._mon_with_low_tcr(tmp_path)
        report = mon.generate_report()
        # Alerts for low TCR should be present
        assert len(report.alerts) >= 1
        alert_metrics = [a.get("metric", "") for a in report.alerts]
        assert any("TCR" in m for m in alert_metrics)

    def test_no_alerts_for_good_metrics(self, tmp_path):
        mon = _make_monitor(tmp_path)
        # All success, good latency, low cost
        for i in range(10):
            mon.record_task(_make_task(f"good_{i}", success=True, execution_time=1.0))
        report = mon.generate_report()
        # May have some alerts but TCR should be fine (100% success)
        tcr_alerts = [
            a for a in report.alerts
            if "TCR" in a.get("metric", "")
        ]
        assert len(tcr_alerts) == 0

    def test_alerts_is_list(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_task(_make_task("alert_test"))
        report = mon.generate_report()
        assert isinstance(report.alerts, list)

    def test_recommendations_is_list(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.record_task(_make_task("rec_test"))
        report = mon.generate_report()
        assert isinstance(report.recommendations, list)


# ---------------------------------------------------------------------------
# thresholds setter edge cases
# ---------------------------------------------------------------------------

class TestThresholdsSetter:
    def test_set_to_none_clears(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.thresholds = {"tcr": 80.0}
        mon.thresholds = None
        assert mon.thresholds is None

    def test_set_non_dict_raises(self, tmp_path):
        mon = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            mon.thresholds = [80.0]  # type: ignore

    def test_set_non_numeric_value_raises(self, tmp_path):
        mon = _make_monitor(tmp_path)
        with pytest.raises(ValidationError):
            mon.thresholds = {"tcr": "eighty"}  # type: ignore

    def test_integer_values_accepted(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.thresholds = {"tcr": 80}  # int is valid
        assert mon.thresholds["tcr"] == 80


# ---------------------------------------------------------------------------
# golden_datasets property
# ---------------------------------------------------------------------------

class TestGoldenDatasetsProperty:
    def test_property_returns_shallow_copy(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon._golden_datasets = [{"id": 1}, {"id": 2}]
        snapshot = mon.golden_datasets
        snapshot.append({"id": 99})
        assert len(mon._golden_datasets) == 2

    def test_setter_stores_list(self, tmp_path):
        mon = _make_monitor(tmp_path)
        mon.golden_datasets = [{"id": 1}]
        assert len(mon._golden_datasets) == 1
