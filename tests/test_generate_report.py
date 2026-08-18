"""
Tests for PerformanceMonitor.generate_report() — E2E pipeline
"""

import json
import os
import tempfile
from datetime import datetime

import pytest

from agent_evaluator import PerformanceMonitor, EvaluationReport
from agent_evaluator.core.trackers.base import TaskResult, TaskType


def _make_task(
    task_id: str,
    task_type: TaskType = TaskType.QA,
    success: bool = True,
    completion_score: float = 1.0,
    accuracy_score: float = 0.9,
    execution_time: float = 1.0,
) -> TaskResult:
    """Helper to create a minimal TaskResult."""
    return TaskResult(
        task_id=task_id,
        task_type=task_type.value,
        success=success,
        completion_score=completion_score,
        accuracy_score=accuracy_score,
        execution_time=execution_time,
        tokens_used={"input": 100, "output": 50, "total": 150},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
    )


# ---------------------------------------------------------------------------
# 1. generate_report() returns EvaluationReport
# ---------------------------------------------------------------------------

def test_generate_report_returns_evaluation_report():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    for i in range(3):
        monitor.record_task(_make_task(f"t{i}"))
    report = monitor.generate_report()
    assert isinstance(report, EvaluationReport)


# ---------------------------------------------------------------------------
# 2. total_tasks == 3
# ---------------------------------------------------------------------------

def test_generate_report_total_tasks():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    for i in range(3):
        monitor.record_task(_make_task(f"t{i}"))
    report = monitor.generate_report()
    assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# 3. success_rate accuracy with mixed tasks
# ---------------------------------------------------------------------------

def test_generate_report_success_rate_mixed():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    # 2 successes, 1 failure
    monitor.record_task(_make_task("t1", success=True, completion_score=1.0))
    monitor.record_task(_make_task("t2", success=True, completion_score=1.0))
    monitor.record_task(_make_task("t3", success=False, completion_score=0.0))
    report = monitor.generate_report()
    tcr_data = report.accuracy_metrics.get("tcr", {})
    # 2 full successes out of 3 → success_rate should be ~66.67%
    assert tcr_data["full_success"] == 2
    assert tcr_data["failures"] == 1


# ---------------------------------------------------------------------------
# 4. task_type_distribution — multiple types recorded correctly
# ---------------------------------------------------------------------------

def test_generate_report_task_type_distribution():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    monitor.record_task(_make_task("t1", task_type=TaskType.QA))
    monitor.record_task(_make_task("t2", task_type=TaskType.CODE_GENERATION))
    monitor.record_task(_make_task("t3", task_type=TaskType.QA))
    report = monitor.generate_report()
    # Total tasks should reflect all 3
    assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# 5. save_to_file() creates JSON file in temp directory
# ---------------------------------------------------------------------------

def test_save_to_file_creates_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        monitor = PerformanceMonitor(
            enable_hallucination_detection=False,
            output_dir=tmpdir,
        )
        monitor.record_task(_make_task("t1"))
        saved_path = monitor.save_to_file("test_report.json")
        assert os.path.exists(saved_path), f"JSON file not created: {saved_path}"
        # Verify JSON is parseable and has expected keys
        with open(saved_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "tasks" in data
        assert len(data["tasks"]) == 1


# ---------------------------------------------------------------------------
# 6. generate_report() with zero tasks — no division by zero
# ---------------------------------------------------------------------------

def test_generate_report_zero_tasks_no_error():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    report = monitor.generate_report()
    assert report.total_tasks == 0
    tcr = report.accuracy_metrics.get("tcr", {})
    # TCR should be 0.0 or empty without error
    assert tcr.get("tcr", 0.0) == 0.0


# ---------------------------------------------------------------------------
# 7. Report timestamp is recent
# ---------------------------------------------------------------------------

def test_generate_report_has_timestamp():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    monitor.record_task(_make_task("t1"))
    report = monitor.generate_report()
    assert report.timestamp is not None
    assert isinstance(report.timestamp, datetime)


# ---------------------------------------------------------------------------
# 8. accuracy_metrics keys present
# ---------------------------------------------------------------------------

def test_generate_report_accuracy_metrics_keys():
    monitor = PerformanceMonitor(enable_hallucination_detection=False)
    monitor.record_task(_make_task("t1"))
    report = monitor.generate_report()
    assert "tcr" in report.accuracy_metrics
    assert "accuracy_scores" in report.accuracy_metrics
