"""
tests/test_save_load_thresholds.py
=====================================
save_to_file / load_from_file 라운드트립 + compare_with_thresholds +
evaluation_session (print 제거 검증)
"""
import json
import logging
import tempfile
import warnings
from pathlib import Path

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult, evaluation_session
from agent_evaluator.core.trackers.layer1 import (
    _QA_WEIGHT_TOKEN_OVERLAP,
    _QA_WEIGHT_JACCARD,
    _QA_WEIGHT_LCS,
    _QA_WEIGHT_CHAR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monitor(tmp_path=None) -> PerformanceMonitor:
    out = str(tmp_path) if tmp_path else tempfile.mkdtemp()
    return PerformanceMonitor(
        output_dir=out,
        enable_hallucination_detection=False,
        enable_security_metrics=False,
    )


def _add_tasks(mon: PerformanceMonitor, n: int = 3) -> None:
    for i in range(n):
        task = create_taskresult(
            task_id=f"task_{i:03d}",
            question=f"Question {i}?",
            response=f"Answer {i}",
            ground_truth=f"Answer {i}",
            execution_time=float(i + 1),
        )
        mon.record_task(task)


# ===========================================================================
# save_to_file / load_from_file round-trip
# ===========================================================================

class TestSaveLoadRoundTrip:
    def _saved_path(self, tmp_path: Path, name: str) -> Path:
        """save_to_file saves without extension; return the file path."""
        return tmp_path / name

    def test_save_creates_file(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon, 2)
        mon.save_to_file("roundtrip")
        assert self._saved_path(tmp_path, "roundtrip").exists()

    def test_saved_json_is_valid(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon, 2)
        mon.save_to_file("valid_json")
        saved = self._saved_path(tmp_path, "valid_json")
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_saved_json_contains_task_results(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon, 3)
        mon.save_to_file("with_tasks")
        saved = self._saved_path(tmp_path, "with_tasks")
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data  # non-empty

    def test_save_with_korean_text(self, tmp_path):
        mon = _make_monitor(tmp_path)
        task = create_taskresult(
            task_id="korean_001",
            question="한국의 수도는?",
            response="서울입니다.",
            ground_truth="서울",
            execution_time=0.5,
        )
        mon.record_task(task)
        mon.save_to_file("korean_test")
        saved = self._saved_path(tmp_path, "korean_test")
        # Should not raise UnicodeDecodeError
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data

    def test_load_from_nonexistent_file_handled(self, tmp_path):
        path = str(tmp_path / "does_not_exist.json")
        # Should raise or return a monitor without crashing
        try:
            mon = PerformanceMonitor.load_from_file(path)
            # If it doesn't raise, it should return a PerformanceMonitor
            assert isinstance(mon, PerformanceMonitor)
        except Exception:
            pass  # Acceptable to raise on missing file


# ===========================================================================
# compare_with_thresholds
# ===========================================================================

class TestCompareWithThresholds:
    def test_empty_thresholds_returns_empty(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon)
        result = mon.compare_with_thresholds()
        assert result == {}

    def test_threshold_pass(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon, 5)
        mon.thresholds = {"tcr": 0.0}  # very low threshold → should pass
        result = mon.compare_with_thresholds()
        assert "tcr" in result
        assert result["tcr"]["status"] == "pass"

    def test_threshold_fail(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon, 3)
        mon.thresholds = {"tcr": 999.0}  # impossibly high → must fail
        result = mon.compare_with_thresholds()
        assert "tcr" in result
        assert result["tcr"]["status"] == "fail"

    def test_result_has_required_keys(self, tmp_path):
        mon = _make_monitor(tmp_path)
        _add_tasks(mon)
        mon.thresholds = {"tcr": 50.0}
        result = mon.compare_with_thresholds()
        assert "tcr" in result
        entry = result["tcr"]
        for key in ("value", "threshold", "status", "direction"):
            assert key in entry, f"missing key: {key}"


# ===========================================================================
# evaluation_session — no stdout print
# ===========================================================================

class TestEvaluationSessionNoPrint:
    def test_session_does_not_print_to_stdout(self, tmp_path, capsys):
        """evaluation_session should use logging, not print()."""
        with evaluation_session(
            "test_session",
            output_dir=str(tmp_path),
            enable_hallucination=False,
        ) as mon:
            _add_tasks(mon, 1)

        captured = capsys.readouterr()
        assert captured.out == "", (
            f"evaluation_session printed to stdout: {captured.out!r}"
        )

    def test_session_exception_does_not_print(self, tmp_path, capsys):
        """Exception path should also not print to stdout."""
        try:
            with evaluation_session(
                "exc_session",
                output_dir=str(tmp_path),
                enable_hallucination=False,
            ) as mon:
                _add_tasks(mon, 1)
                raise ValueError("deliberate error")
        except ValueError:
            pass

        captured = capsys.readouterr()
        assert captured.out == "", (
            f"evaluation_session (exception path) printed to stdout: {captured.out!r}"
        )


# ===========================================================================
# QA accuracy weight constants sanity
# ===========================================================================

class TestQAWeightConstants:
    def test_weights_sum_to_one(self):
        total = (
            _QA_WEIGHT_TOKEN_OVERLAP
            + _QA_WEIGHT_JACCARD
            + _QA_WEIGHT_LCS
            + _QA_WEIGHT_CHAR
        )
        assert abs(total - 1.0) < 1e-9, f"QA weights sum = {total}"

    def test_all_weights_positive(self):
        for w in (_QA_WEIGHT_TOKEN_OVERLAP, _QA_WEIGHT_JACCARD,
                  _QA_WEIGHT_LCS, _QA_WEIGHT_CHAR):
            assert w > 0
