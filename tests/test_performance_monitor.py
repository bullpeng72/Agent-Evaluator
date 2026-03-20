"""Tests for PerformanceMonitor.generate_report() aggregation pipeline"""
from datetime import datetime

import pytest

from agent_evaluator.core.agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TaskType,
)


def _make_task(task_id: str, success: bool, accuracy: float = 0.8,
               execution_time: float = 1.0) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        task_type=TaskType.QA,
        success=success,
        completion_score=1.0 if success else 0.0,
        accuracy_score=accuracy,
        execution_time=execution_time,
        tokens_used={"total": 100, "input": 60, "output": 40},
        tool_calls=[],
        attempts=1,
        errors=[] if success else ["task failed"],
        timestamp=datetime.now(),
    )


@pytest.fixture
def monitor():
    return PerformanceMonitor()


@pytest.fixture
def populated_monitor():
    m = PerformanceMonitor()
    m.record_task(_make_task("t1", success=True, accuracy=0.9))
    m.record_task(_make_task("t2", success=True, accuracy=0.8))
    m.record_task(_make_task("t3", success=False, accuracy=0.3))
    return m


class TestPerformanceMonitorReport:
    def test_generate_report_returns_object(self, populated_monitor):
        report = populated_monitor.generate_report()
        assert report is not None

    def test_report_total_tasks_correct(self, populated_monitor):
        report = populated_monitor.generate_report()
        assert report.total_tasks == 3

    def test_report_accuracy_metrics_present(self, populated_monitor):
        report = populated_monitor.generate_report()
        assert "accuracy" in report.accuracy_metrics or "tcr" in report.accuracy_metrics

    def test_report_efficiency_metrics_present(self, populated_monitor):
        report = populated_monitor.generate_report()
        assert report.efficiency_metrics is not None

    def test_empty_monitor_report_no_error(self, monitor):
        report = monitor.generate_report()
        assert report.total_tasks == 0

    def test_record_task_increments_count(self, monitor):
        assert len(monitor.tcr_tracker.tasks) == 0
        monitor.record_task(_make_task("t1", success=True))
        assert len(monitor.tcr_tracker.tasks) == 1

    def test_all_success_high_tcr(self):
        m = PerformanceMonitor()
        for i in range(5):
            m.record_task(_make_task(f"t{i}", success=True))
        report = m.generate_report()
        tcr_data = report.accuracy_metrics.get("tcr", {})
        if isinstance(tcr_data, dict):
            assert tcr_data.get("tcr", 0) >= 90.0

    def test_all_failure_low_tcr(self):
        m = PerformanceMonitor()
        for i in range(5):
            m.record_task(_make_task(f"t{i}", success=False))
        report = m.generate_report()
        tcr_data = report.accuracy_metrics.get("tcr", {})
        if isinstance(tcr_data, dict):
            assert tcr_data.get("tcr", 100) <= 10.0
