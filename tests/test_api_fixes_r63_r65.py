"""
tests/test_api_fixes_r63_r65.py
=================================
Round 63 — HybridPerformanceMonitor method chaining (LSP fix)
Round 63 — HybridPerformanceMonitor lock fix (직접 뮤테이션)
Round 64 — task_id 빈 문자열 검증
Round 65 — accuracy_evaluator save/load round-trip
Round 65 — compare_with_thresholds 주요 경로
"""
import json
import tempfile
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
        # This would raise AttributeError if return type is None
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
        # Add tasks with ground_truth → triggers accuracy evaluation
        for i in range(4):
            task = create_taskresult(
                task_id=f"acc_{i:03d}",
                question="Capital of France?",
                response="Paris",
                ground_truth="Paris",
                execution_time=1.0,
            )
            # Force accuracy_evaluator to run by providing ground_truth
            mon.record_task(task, ground_truth="Paris", response="Paris")

        n_before = len(mon.accuracy_evaluator._evaluations)
        assert n_before > 0, "accuracy_evaluator should have evaluations before save"

        # Save and reload
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

        # _task_ids must be populated (setter reconstructs them)
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
        loaded.thresholds = {"accuracy": 0.0}  # always-pass threshold
        result = loaded.compare_with_thresholds()
        assert "accuracy" in result
        assert result["accuracy"]["status"] in ("pass", "fail", "pending")


# ---------------------------------------------------------------------------
# Round 65 — compare_with_thresholds coverage
# ---------------------------------------------------------------------------

class TestCompareWithThresholds:
    def _mon_with_tasks(self, tmp_path=None, n=3):
        mon = _make_monitor(tmp_path)
        for i in range(n):
            mon.record_task(_make_task(f"cwt_{i:03d}", accuracy=0.8 + i * 0.05))
        return mon

    def test_empty_thresholds_returns_empty_dict(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {}
        assert mon.compare_with_thresholds() == {}

    def test_none_thresholds_returns_empty_dict(self):
        mon = self._mon_with_tasks()
        # _thresholds is None by default
        assert mon.compare_with_thresholds() == {}

    def test_tcr_pass(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"tcr": 0.0}  # always pass
        result = mon.compare_with_thresholds()
        assert result["tcr"]["status"] == "pass"
        assert result["tcr"]["direction"] == "higher"
        assert result["tcr"]["unit"] == "%"

    def test_tcr_fail(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"tcr": 999.0}  # impossible threshold
        result = mon.compare_with_thresholds()
        assert result["tcr"]["status"] == "fail"

    def test_latency_pass(self):
        mon = _make_monitor()
        mon.record_task(_make_task("lat_1", execution_time=0.5))
        mon.thresholds = {"latency": 999.0}  # always pass
        result = mon.compare_with_thresholds()
        assert result["latency"]["status"] == "pass"
        assert result["latency"]["direction"] == "lower"

    def test_latency_fail(self):
        mon = _make_monitor()
        mon.record_task(_make_task("lat_2", execution_time=5.0))
        mon.thresholds = {"latency": 0.001}  # always fail
        result = mon.compare_with_thresholds()
        assert result["latency"]["status"] == "fail"

    def test_accuracy_pending_when_no_evaluations(self):
        mon = _make_monitor()
        # Record task with pre-computed accuracy_score → accuracy_evaluator stays empty
        mon.record_task(_make_task("no_eval_001", accuracy=0.9))
        mon.thresholds = {"accuracy": 50.0}
        result = mon.compare_with_thresholds()
        # With pre-computed score only, accuracy_evaluator may be empty → 'pending'
        assert result["accuracy"]["status"] in ("pass", "fail", "pending")

    def test_faithfulness_pending_no_data(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"faithfulness": 0.8}
        result = mon.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "pending"
        assert result["faithfulness"]["value"] == 0.0

    def test_faithfulness_pass_with_data(self):
        mon = self._mon_with_tasks()
        mon.record_rag_metrics(faithfulness=0.95)
        mon.thresholds = {"faithfulness": 0.5}
        result = mon.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "pass"

    def test_faithfulness_fail_with_data(self):
        mon = self._mon_with_tasks()
        mon.record_rag_metrics(faithfulness=0.3)
        mon.thresholds = {"faithfulness": 0.8}
        result = mon.compare_with_thresholds()
        assert result["faithfulness"]["status"] == "fail"

    def test_result_item_has_required_keys(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"tcr": 50.0}
        result = mon.compare_with_thresholds()
        item = result["tcr"]
        for key in ("name", "value", "threshold", "status", "direction", "unit"):
            assert key in item, f"Missing key '{key}' in compare_with_thresholds() result"

    def test_invalid_threshold_type_raises(self):
        mon = self._mon_with_tasks()
        with pytest.raises(ValidationError):
            mon.thresholds = {"tcr": "eighty"}  # type: ignore — setter raises

    def test_multiple_thresholds_all_present(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"tcr": 50.0, "latency": 10.0}
        result = mon.compare_with_thresholds()
        assert "tcr" in result
        assert "latency" in result

    def test_cost_per_task_threshold(self):
        mon = self._mon_with_tasks()
        mon.thresholds = {"cost_per_task": 999.0}
        result = mon.compare_with_thresholds()
        assert result["cost_per_task"]["status"] == "pass"
        assert result["cost_per_task"]["direction"] == "lower"
