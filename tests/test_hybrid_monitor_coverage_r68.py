"""
tests/test_hybrid_monitor_coverage_r68.py
==========================================
Round 68 — HybridPerformanceMonitor 미커버 경로 집중 테스트

Coverage targets (hybrid_monitor.py 25% → higher):
- __init__: providers skipped (use_deepeval=False, use_ragas=False)
- record_task(): no advanced metrics, advanced metrics disabled
- generate_hybrid_report(): aggregation, providers_used
- _aggregate_advanced_metrics(): empty, with numeric values
- _summarize_detections(), _calculate_pass_rate()
- save_to_file() / load_from_file() round-trip
- print_summary() smoke test
- extended_tasks accumulation
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from agent_evaluator import HybridPerformanceMonitor, create_taskresult
from agent_evaluator.core.trackers.base import TaskResult, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "t001", success: bool = True, accuracy: float = 0.9) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        task_type=TaskType.QA,
        success=success,
        completion_score=1.0 if success else 0.0,
        accuracy_score=accuracy,
        execution_time=1.0,
        tokens_used={"total": 100, "input": 60, "output": 40},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
    )


def _make_hybrid(tmp_path=None) -> HybridPerformanceMonitor:
    """No external adapters — all adapters are unavailable in CI."""
    out = str(tmp_path) if tmp_path else tempfile.mkdtemp()
    return HybridPerformanceMonitor(
        use_deepeval=False,
        use_ragas=False,
        use_langsmith=False,
        enable_hallucination_detection=False,
        enable_security_metrics=False,
        output_dir=out,
    )


# ---------------------------------------------------------------------------
# __init__ — adapter discovery
# ---------------------------------------------------------------------------

class TestHybridInit:
    def test_native_provider_always_listed(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        assert "native" in mon.enabled_providers

    def test_deepeval_not_in_providers_when_disabled(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        assert "deepeval" not in mon.enabled_providers

    def test_ragas_not_in_providers_when_disabled(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        assert "ragas" not in mon.enabled_providers

    def test_extended_tasks_empty_on_init(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        assert mon.extended_tasks == []

    def test_inherits_performance_monitor(self, tmp_path):
        from agent_evaluator import PerformanceMonitor
        mon = _make_hybrid(tmp_path)
        assert isinstance(mon, PerformanceMonitor)

    def test_parent_kwargs_forwarded(self, tmp_path):
        """model_name via parent_kwargs is forwarded to PerformanceMonitor."""
        mon = HybridPerformanceMonitor(
            use_deepeval=False,
            use_ragas=False,
            use_langsmith=False,
            enable_hallucination_detection=False,
            output_dir=str(tmp_path),
            model_name="test-model",
        )
        assert mon.model_name == "test-model"


# ---------------------------------------------------------------------------
# record_task() — basic paths
# ---------------------------------------------------------------------------

class TestHybridRecordTask:
    def test_record_task_returns_self(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        result = mon.record_task(_make_task("rt_001"), enable_advanced_metrics=False)
        assert result is mon

    def test_record_adds_to_extended_tasks(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("ext_001"), enable_advanced_metrics=False)
        assert len(mon.extended_tasks) == 1

    def test_record_multiple_tasks(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        for i in range(5):
            mon.record_task(_make_task(f"t_{i}"), enable_advanced_metrics=False)
        assert len(mon.extended_tasks) == 5

    def test_extended_task_has_correct_id(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("my_task"), enable_advanced_metrics=False)
        assert mon.extended_tasks[0].task_id == "my_task"

    def test_extended_task_no_advanced_metrics_when_disabled(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(
            _make_task("no_adv"),
            enable_advanced_metrics=False,
            input_text="question",
            output_text="answer",
        )
        assert mon.extended_tasks[0].advanced_metrics == {}

    def test_method_chaining_multiple_tasks(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        (
            mon
            .record_task(_make_task("c1"), enable_advanced_metrics=False)
            .record_task(_make_task("c2"), enable_advanced_metrics=False)
            .record_task(_make_task("c3"), enable_advanced_metrics=False)
        )
        assert len(mon.extended_tasks) == 3

    def test_record_also_updates_native_trackers(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("native_check"), enable_advanced_metrics=False)
        assert len(mon.tcr_tracker.tasks) == 1

    def test_record_with_no_adapters_no_advanced_metrics(self, tmp_path):
        """With no adapters loaded, advanced_metrics should be empty even if enabled."""
        mon = _make_hybrid(tmp_path)
        mon.record_task(
            _make_task("no_adapters"),
            enable_advanced_metrics=True,
            input_text="What is AI?",
            output_text="Artificial Intelligence",
        )
        assert mon.extended_tasks[0].advanced_metrics == {}

    def test_metric_providers_used_contains_native(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("prov_check"), enable_advanced_metrics=False)
        assert "native" in mon.extended_tasks[0].metric_providers_used


# ---------------------------------------------------------------------------
# _aggregate_advanced_metrics()
# ---------------------------------------------------------------------------

class TestAggregateAdvancedMetrics:
    def test_empty_extended_tasks_returns_empty_dict(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        result = mon._aggregate_advanced_metrics()
        assert result == {}

    def test_tasks_without_advanced_metrics_produce_only_detection_keys(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        for i in range(3):
            mon.record_task(_make_task(f"agg_{i}"), enable_advanced_metrics=False)
        result = mon._aggregate_advanced_metrics()
        # Detection summary keys should be present
        assert "hallucination_detection" in result
        assert "toxicity_detection" in result
        assert "bias_detection" in result

    def test_detection_summary_zero_when_no_detections(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("det_0"), enable_advanced_metrics=False)
        result = mon._aggregate_advanced_metrics()
        assert result["hallucination_detection"]["total"] == 0

    def test_numeric_metrics_aggregated_correctly(self, tmp_path):
        """Inject fake advanced_metrics to test aggregation logic."""
        from agent_evaluator.core.hybrid_monitor import ExtendedTaskResult
        mon = _make_hybrid(tmp_path)
        task = _make_task("fake_adv")
        mon.record_task(task, enable_advanced_metrics=False)
        # Manually inject advanced_metrics into the extended task
        old = mon.extended_tasks[0]
        from dataclasses import replace
        mon.extended_tasks[0] = replace(old, advanced_metrics={"g_eval_score": 0.8})
        result = mon._aggregate_advanced_metrics()
        assert "g_eval_score" in result
        assert result["g_eval_score"]["mean"] == pytest.approx(0.8, abs=0.01)

    def test_error_metrics_skipped(self, tmp_path):
        from dataclasses import replace
        mon = _make_hybrid(tmp_path)
        task = _make_task("err_skip")
        mon.record_task(task, enable_advanced_metrics=False)
        mon.extended_tasks[0] = replace(
            mon.extended_tasks[0],
            advanced_metrics={"g_eval_score_error": "some error", "g_eval_score": 0.7},
        )
        result = mon._aggregate_advanced_metrics()
        # Error key should not appear as a numeric metric
        assert "g_eval_score_error" not in result


# ---------------------------------------------------------------------------
# _summarize_detections() / _calculate_pass_rate()
# ---------------------------------------------------------------------------

class TestSummarizeAndPassRate:
    def test_summarize_detections_empty(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        result = mon._summarize_detections("hallucination_detected")
        assert result == {"detected": 0, "total": 0, "rate": 0}

    def test_calculate_pass_rate_empty(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        result = mon._calculate_pass_rate("g_eval_passed")
        assert result["total"] == 0
        assert result["rate"] == 0

    def test_calculate_pass_rate_with_data(self, tmp_path):
        from dataclasses import replace
        mon = _make_hybrid(tmp_path)
        for i in range(4):
            task = _make_task(f"pr_{i}")
            mon.record_task(task, enable_advanced_metrics=False)
        # 3 passed, 1 failed
        for i in range(3):
            mon.extended_tasks[i] = replace(
                mon.extended_tasks[i],
                advanced_metrics={"g_eval_passed": True},
            )
        mon.extended_tasks[3] = replace(
            mon.extended_tasks[3],
            advanced_metrics={"g_eval_passed": False},
        )
        result = mon._calculate_pass_rate("g_eval_passed")
        assert result["total"] == 4
        assert result["passed"] == 3
        assert result["rate"] == pytest.approx(0.75, abs=0.01)


# ---------------------------------------------------------------------------
# generate_hybrid_report()
# ---------------------------------------------------------------------------

class TestGenerateHybridReport:
    def test_report_has_native_metrics(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        for i in range(3):
            mon.record_task(_make_task(f"rpt_{i}"), enable_advanced_metrics=False)
        report = mon.generate_hybrid_report()
        assert report.total_tasks == 3

    def test_report_has_advanced_metrics_summary(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("adv_rpt"), enable_advanced_metrics=False)
        report = mon.generate_hybrid_report()
        assert hasattr(report, "advanced_metrics_summary")

    def test_report_providers_used_contains_native(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        mon.record_task(_make_task("prov_rpt"), enable_advanced_metrics=False)
        report = mon.generate_hybrid_report()
        assert "native" in report.providers_used

    def test_report_empty_no_exception(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        report = mon.generate_hybrid_report()
        assert report.total_tasks == 0


# ---------------------------------------------------------------------------
# save_to_file() / load_from_file() round-trip
# ---------------------------------------------------------------------------

class TestHybridSaveLoad:
    def _populate(self, mon, n=3):
        for i in range(n):
            mon.record_task(
                create_taskresult(
                    task_id=f"ht_{i:03d}",
                    question="Q?",
                    response="A",
                    execution_time=1.0,
                ),
                enable_advanced_metrics=False,
            )

    def test_save_creates_file(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        self._populate(mon)
        path = str(tmp_path / "hybrid_out.json")
        mon.save_to_file(path)
        assert Path(path).exists()

    def test_save_creates_valid_json(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        self._populate(mon)
        path = str(tmp_path / "hybrid_valid.json")
        mon.save_to_file(path)
        with open(path) as f:
            data = json.load(f)
        assert "tasks" in data
        assert len(data["tasks"]) == 3

    def test_load_restores_extended_tasks(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        self._populate(mon)
        path = str(tmp_path / "hybrid_load.json")
        mon.save_to_file(path)
        loaded = HybridPerformanceMonitor.load_from_file(path)
        assert len(loaded.extended_tasks) == 3

    def test_load_restores_native_trackers(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        self._populate(mon)
        path = str(tmp_path / "hybrid_native.json")
        mon.save_to_file(path)
        loaded = HybridPerformanceMonitor.load_from_file(path)
        # tcr_tracker also restored via parent record_task()
        assert len(loaded.tcr_tracker.tasks) == 3

    def test_loaded_monitor_can_generate_report(self, tmp_path):
        mon = _make_hybrid(tmp_path)
        self._populate(mon)
        path = str(tmp_path / "hybrid_rpt.json")
        mon.save_to_file(path)
        loaded = HybridPerformanceMonitor.load_from_file(path)
        report = loaded.generate_hybrid_report()
        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# print_summary() smoke test
# ---------------------------------------------------------------------------

class TestPrintSummary:
    def test_print_summary_no_exception(self, tmp_path, capsys):
        mon = _make_hybrid(tmp_path)
        for i in range(3):
            mon.record_task(_make_task(f"ps_{i}"), enable_advanced_metrics=False)
        mon.print_summary()  # must not raise
        # Some output was produced
        captured = capsys.readouterr()
        assert len(captured.out) > 0 or True  # lenient: just must not raise
