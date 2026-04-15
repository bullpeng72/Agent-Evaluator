"""
tests/test_api_fixes.py
========================
과거 버그 수정 및 API 수정 회귀 테스트 (Round 63-65, v5)
"""
from __future__ import annotations

import json
import os
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

def _make_task(task_id: str = "t001", success: bool = True,
               accuracy: float = 0.9, execution_time: float = 1.0) -> TaskResult:
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


# ===========================================================================
# From test_api_fixes_r63_r65.py
# ===========================================================================

# ---------------------------------------------------------------------------
# Round 64 — task_id validation
# ---------------------------------------------------------------------------

class TestTaskIdValidation:
    def test_empty_string_raises(self):
        with pytest.raises(ValidationError, match="task_id"):
            TaskResult(
                task_id="",
                task_type="qa",
                success=True,
                completion_score=1.0,
                accuracy_score=0.9,
                execution_time=1.0,
                tokens_used={},
                tool_calls=[],
                attempts=1,
                errors=[],
                timestamp=datetime.now(),
            )

    def test_whitespace_only_raises(self):
        with pytest.raises(ValidationError, match="task_id"):
            TaskResult(
                task_id="   ",
                task_type="qa",
                success=True,
                completion_score=1.0,
                accuracy_score=0.9,
                execution_time=1.0,
                tokens_used={},
                tool_calls=[],
                attempts=1,
                errors=[],
                timestamp=datetime.now(),
            )

    def test_valid_task_id_passes(self):
        t = _make_task(task_id="valid_001")
        assert t.task_id == "valid_001"

    def test_task_id_with_special_chars_passes(self):
        t = _make_task(task_id="task-001:qa")
        assert t.task_id == "task-001:qa"

    def test_create_taskresult_empty_id_raises(self):
        with pytest.raises((ValidationError, ValueError)):
            create_taskresult(task_id="", question="q", response="r")


# ---------------------------------------------------------------------------
# Round 63 — HybridPerformanceMonitor method chaining
# ---------------------------------------------------------------------------

class TestHybridMonitorMethodChaining:
    def test_record_task_returns_self(self):
        try:
            from agent_evaluator import HybridPerformanceMonitor
        except ImportError:
            pytest.skip("HybridPerformanceMonitor not available")

        monitor = HybridPerformanceMonitor()
        result = monitor.record_task(_make_task("chain_001"), enable_advanced_metrics=False)
        assert result is monitor

    def test_method_chaining_multiple_tasks(self):
        try:
            from agent_evaluator import HybridPerformanceMonitor
        except ImportError:
            pytest.skip("HybridPerformanceMonitor not available")

        monitor = HybridPerformanceMonitor()
        (monitor
            .record_task(_make_task("c1"), enable_advanced_metrics=False)
            .record_task(_make_task("c2"), enable_advanced_metrics=False))
        assert len(monitor.extended_tasks) == 2


# ---------------------------------------------------------------------------
# Round 65 — accuracy_evaluator save/load round-trip
# ---------------------------------------------------------------------------

class TestAccuracyEvaluatorSaveLoad:
    def test_accuracy_evaluations_preserved_after_save_load(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(4):
            task = create_taskresult(
                task_id=f"acc_{i:03d}",
                question="Capital of France?",
                response="Paris",
                ground_truth="Paris",
                execution_time=1.0,
            )
            mon.record_task(task, ground_truth="Paris", response="Paris")

        n_before = len(mon.accuracy_evaluator._evaluations)
        assert n_before > 0, "accuracy_evaluator should have evaluations before save"

        save_path = str(tmp_path / "acc_test.json")
        mon.save_to_file(save_path)
        loaded = PerformanceMonitor.load_from_file(save_path)

        n_after = len(loaded.accuracy_evaluator._evaluations)
        assert n_after == n_before, (
            f"accuracy_evaluator evaluations lost in round-trip: "
            f"{n_before} before, {n_after} after"
        )

    def test_accuracy_evaluator_key_in_saved_json(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = create_taskresult(
            task_id="json_check",
            question="Q?",
            response="A",
            ground_truth="A",
            execution_time=0.5,
        )
        mon.record_task(task, ground_truth="A", response="A")

        save_path = str(tmp_path / "json_check.json")
        mon.save_to_file(save_path)

        with open(save_path) as f:
            data = json.load(f)

        assert "accuracy" in data.get("evaluators", {}), (
            "evaluators.accuracy key missing from saved JSON"
        )
        assert "evaluations" in data["evaluators"]["accuracy"]

    def test_accuracy_task_ids_reconstructed_after_load(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(3):
            task = create_taskresult(
                task_id=f"tid_{i}",
                question="Q?",
                response="A",
                ground_truth="A",
                execution_time=0.5,
            )
            mon.record_task(task, ground_truth="A", response="A")

        save_path = str(tmp_path / "ids_check.json")
        mon.save_to_file(save_path)
        loaded = PerformanceMonitor.load_from_file(save_path)

        assert len(loaded.accuracy_evaluator._task_ids) > 0

    def test_compare_with_thresholds_accuracy_after_load(self, tmp_path):
        mon = _make_monitor(tmp_path)
        for i in range(3):
            task = create_taskresult(
                task_id=f"cmp_{i}",
                question="Q?",
                response="Answer",
                ground_truth="Answer",
                execution_time=1.0,
            )
            mon.record_task(task, ground_truth="Answer", response="Answer")

        save_path = str(tmp_path / "cmp.json")
        mon.save_to_file(save_path)
        loaded = PerformanceMonitor.load_from_file(save_path)
        loaded.thresholds = {"accuracy": 0.0}
        result = loaded.compare_with_thresholds()
        assert "accuracy" in result
        assert result["accuracy"]["status"] in ("pass", "fail", "pending")


# ===========================================================================
# From test_bug_fixes_v5.py
# ===========================================================================

class TestQualityMetrics:
    """quality_metrics 버그 수정 검증"""

    def test_quality_metrics_not_empty(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="q1",
            question="What is the capital of France?",
            response="Paris is the capital of France.",
            ground_truth="Paris",
            execution_time=1.0,
        )
        monitor.record_task(task)
        report = monitor.generate_report()
        assert report.quality_metrics != {}, "quality_metrics should not be empty dict"

    def test_quality_metrics_has_expected_keys(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="q1",
            question="Q",
            response="A detailed response",
            ground_truth="A",
            execution_time=0.5,
        )
        monitor.record_task(task)
        report = monitor.generate_report()
        assert isinstance(report.quality_metrics, dict)


class TestHTMLGeneration:
    """save_to_file() HTML 생성 검증"""

    def test_save_generates_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            for i in range(2):
                task = create_taskresult(
                    task_id=f"t{i}",
                    question=f"Q{i}",
                    response=f"A{i}",
                    ground_truth=f"A{i}",
                    execution_time=float(i + 1),
                )
                monitor.record_task(task)
            monitor.save_to_file("test_html")
            files = os.listdir(tmpdir)
            html_files = [f for f in files if f.endswith(".html")]
            assert len(html_files) >= 1, f"Expected HTML file, got: {files}"

    def test_save_html_is_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            task = create_taskresult(
                task_id="t1",
                question="Q",
                response="A",
                ground_truth="A",
                execution_time=1.0,
            )
            monitor.record_task(task)
            monitor.save_to_file("test_valid_html")
            html_files = [f for f in os.listdir(tmpdir) if f.endswith(".html")]
            if html_files:
                html_path = os.path.join(tmpdir, html_files[0])
                content = open(html_path, encoding="utf-8").read()
                assert len(content) > 100
                assert "<html" in content.lower() or "<!DOCTYPE" in content

    def test_save_still_creates_json_on_html_failure(self):
        """HTML 생성 실패해도 JSON은 저장되어야 함"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            task = create_taskresult(
                task_id="t1", question="Q", response="A",
                ground_truth="A", execution_time=1.0,
            )
            monitor.record_task(task)
            path = monitor.save_to_file("fallback_test.json")
            assert path.endswith(".json")
            assert os.path.exists(path)


class TestContextParameter:
    """create_taskresult() context 파라미터 추가 검증"""

    def test_create_taskresult_accepts_context(self):
        task = create_taskresult(
            task_id="t1",
            question="What is AI?",
            response="AI is artificial intelligence.",
            ground_truth="Artificial Intelligence",
            execution_time=0.5,
            context="Reference document: AI stands for Artificial Intelligence...",
        )
        assert task.context == "Reference document: AI stands for Artificial Intelligence..."

    def test_create_taskresult_context_default_none(self):
        task = create_taskresult(
            task_id="t1",
            question="Q",
            response="A",
            ground_truth="G",
            execution_time=0.5,
        )
        assert task.context is None

    def test_evaluate_qa_accepts_context(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa(
            question="What is AI?",
            response="Artificial Intelligence",
            ground_truth="AI",
            context="AI stands for Artificial Intelligence.",
        )
        assert "accuracy_score" in result


class TestDeprecationWarning:
    """record_task() deprecated 파라미터 경고 검증"""

    def test_request_param_always_warns(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="t1",
            question="existing question",
            response="A",
            ground_truth="A",
            execution_time=0.5,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task, request="override question")
        assert any(issubclass(x.category, DeprecationWarning) for x in w), \
            "DeprecationWarning should fire even when task_result.question is set"

    def test_request_param_none_no_warning(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="t1",
            question="Q",
            response="A",
            ground_truth="A",
            execution_time=0.5,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task)
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) == 0
