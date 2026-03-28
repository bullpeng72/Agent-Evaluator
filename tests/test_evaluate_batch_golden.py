"""
tests/test_evaluate_batch_golden.py
====================================
evaluate_batch() / load_golden_dataset() / evaluate_with_golden_dataset() 테스트
"""
import json
import os
import threading
import tempfile
from pathlib import Path

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.exceptions import ValidationError, StorageError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monitor(**kwargs) -> PerformanceMonitor:
    return PerformanceMonitor(
        output_dir=tempfile.mkdtemp(),
        enable_hallucination_detection=False,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# evaluate_batch()
# ---------------------------------------------------------------------------

class TestEvaluateBatch:
    def test_basic_batch(self):
        mon = _make_monitor()
        items = [
            {"question": "Q1", "response": "A1", "ground_truth": "A1"},
            {"question": "Q2", "response": "A2", "ground_truth": "A2"},
        ]
        results = mon.evaluate_batch(items)
        assert len(results) == 2
        for r in results:
            assert "accuracy_score" in r
            assert "completion_score" in r

    def test_empty_list_returns_empty(self):
        mon = _make_monitor()
        results = mon.evaluate_batch([])
        assert results == []

    def test_missing_question_raises(self):
        mon = _make_monitor()
        with pytest.raises(ValidationError, match="question"):
            mon.evaluate_batch([{"response": "A", "ground_truth": "G"}])

    def test_missing_response_raises(self):
        mon = _make_monitor()
        with pytest.raises(ValidationError, match="response"):
            mon.evaluate_batch([{"question": "Q", "ground_truth": "G"}])

    def test_missing_ground_truth_raises(self):
        mon = _make_monitor()
        with pytest.raises(ValidationError, match="ground_truth"):
            mon.evaluate_batch([{"question": "Q", "response": "A"}])

    def test_multiple_invalid_items_all_reported(self):
        mon = _make_monitor()
        items = [
            {"question": "Q"},               # missing response, ground_truth
            {"response": "A"},               # missing question, ground_truth
            {"question": "Q", "response": "A", "ground_truth": "G"},  # valid
        ]
        with pytest.raises(ValidationError) as exc_info:
            mon.evaluate_batch(items)
        msg = str(exc_info.value)
        assert "item[0]" in msg
        assert "item[1]" in msg
        assert "item[2]" not in msg

    def test_custom_task_id_preserved(self):
        mon = _make_monitor()
        items = [
            {"question": "Q", "response": "A", "ground_truth": "G", "task_id": "custom_007"},
        ]
        results = mon.evaluate_batch(items)
        assert results[0]["task_id"] == "custom_007"

    def test_auto_task_id_prefix(self):
        mon = _make_monitor()
        items = [
            {"question": "Q1", "response": "A1", "ground_truth": "G1"},
            {"question": "Q2", "response": "A2", "ground_truth": "G2"},
        ]
        results = mon.evaluate_batch(items, task_id_prefix="test")
        assert results[0]["task_id"] == "test_0000"
        assert results[1]["task_id"] == "test_0001"

    def test_custom_task_type(self):
        mon = _make_monitor()
        items = [
            {"question": "Write code", "response": "def f(): pass", "ground_truth": "def f(): pass"},
        ]
        results = mon.evaluate_batch(items, task_type="code_generation")
        assert results[0]["task_id"].startswith("batch_")


# ---------------------------------------------------------------------------
# load_golden_dataset()
# ---------------------------------------------------------------------------

class TestLoadGoldenDataset:
    def test_file_not_found_raises_storage_error(self):
        mon = _make_monitor()
        with pytest.raises(StorageError, match="찾을 수 없습니다"):
            mon.load_golden_dataset("/nonexistent/path/dataset.json")

    def test_load_list_format(self, tmp_path):
        data = [
            {"qa_id": "q1", "question": "Q1", "ground_truth": "A1"},
            {"qa_id": "q2", "question": "Q2", "ground_truth": "A2"},
        ]
        f = tmp_path / "dataset.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        mon = _make_monitor()
        result = mon.load_golden_dataset(str(f))
        assert len(result) == 2
        assert result[0]["qa_id"] == "q1"

    def test_load_qa_pairs_format(self, tmp_path):
        data = {"qa_pairs": [{"qa_id": "q1", "question": "Q1", "ground_truth": "A1"}]}
        f = tmp_path / "dataset.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        mon = _make_monitor()
        result = mon.load_golden_dataset(str(f))
        assert len(result) == 1

    def test_invalid_json_raises_storage_error(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{invalid json", encoding="utf-8")

        mon = _make_monitor()
        with pytest.raises(StorageError, match="JSON"):
            mon.load_golden_dataset(str(f))

    def test_unexpected_format_raises_storage_error(self, tmp_path):
        f = tmp_path / "weird.json"
        f.write_text(json.dumps({"other_key": []}), encoding="utf-8")

        mon = _make_monitor()
        with pytest.raises(StorageError, match="포맷"):
            mon.load_golden_dataset(str(f))

    def test_cached_in_golden_datasets(self, tmp_path):
        data = [{"qa_id": "q1", "question": "Q1", "ground_truth": "A1"}]
        f = tmp_path / "dataset.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        mon = _make_monitor()
        mon.load_golden_dataset(str(f))
        assert len(mon.golden_datasets) == 1


# ---------------------------------------------------------------------------
# evaluate_with_golden_dataset()
# ---------------------------------------------------------------------------

class TestEvaluateWithGoldenDataset:
    def _make_dataset_file(self, tmp_path, n=3):
        data = [
            {"qa_id": f"q{i}", "question": f"What is {i}?", "ground_truth": str(i)}
            for i in range(n)
        ]
        f = tmp_path / "dataset.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        return str(f)

    def test_string_returning_agent(self, tmp_path):
        mon = _make_monitor()
        path = self._make_dataset_file(tmp_path)

        def agent_fn(question):
            return "42"

        results = mon.evaluate_with_golden_dataset(agent_fn, dataset_path=path, verbose=False)
        assert results["total_evaluated"] == 3
        assert "layer1_metrics" in results
        assert "tcr" in results["layer1_metrics"]

    def test_dict_returning_agent(self, tmp_path):
        mon = _make_monitor()
        path = self._make_dataset_file(tmp_path)

        def agent_fn(question):
            return {"answer": "42", "tools_used": ["search"]}

        results = mon.evaluate_with_golden_dataset(agent_fn, dataset_path=path, verbose=False)
        assert results["total_evaluated"] == 3

    def test_dataset_not_found_raises(self):
        mon = _make_monitor()

        def agent_fn(question):
            return "answer"

        with pytest.raises(StorageError):
            mon.evaluate_with_golden_dataset(agent_fn, dataset_path="/no/such/file.json", verbose=False)

    def test_layer2_metrics_returned_when_enabled(self, tmp_path):
        data = [
            {"qa_id": "q1", "question": "Q", "ground_truth": "A",
             "expected_tools": ["search"]}
        ]
        f = tmp_path / "ds.json"
        f.write_text(json.dumps(data), encoding="utf-8")

        mon = _make_monitor()

        def agent_fn(question):
            return {"answer": "A", "tools_used": ["search"]}

        results = mon.evaluate_with_golden_dataset(
            agent_fn, dataset_path=str(f), enable_layer2_metrics=True, verbose=False
        )
        assert "layer2_metrics" in results
        assert "tool_selection_accuracy" in results["layer2_metrics"]


# ---------------------------------------------------------------------------
# Thread safety — conversation_sessions
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_conversation_append(self, tmp_path):
        """여러 스레드에서 동시에 conversation_sessions에 append해도 안전해야 한다."""
        mon = _make_monitor()
        errors = []

        def run_session(i):
            try:
                with mon.conversation(f"session_{i}") as conv:
                    conv.turn(user=f"안녕 {i}", agent=f"응답 {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=run_session, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(mon.conversation_sessions) == 10
