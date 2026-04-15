"""
tests/test_golden_datasets.py
==============================
GoldenSetBuilder / evaluate_batch() / load_golden_dataset() /
evaluate_with_golden_dataset() 통합 테스트
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.datasets.builder import GoldenSetBuilder
from agent_evaluator.exceptions import ValidationError, StorageError


# ---------------------------------------------------------------------------
# Helpers — write fake result JSON files into temp dirs
# ---------------------------------------------------------------------------

def _write_tasks_file(directory: Path, filename: str, tasks: List[Dict[str, Any]]) -> None:
    """Write a {tasks: [...]} JSON file into directory."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")


def _task(
    task_id: str = "t1",
    success: bool = True,
    completion_score: float = 0.8,
    accuracy_score: float = 0.8,
    question: str = "What is the capital city?",
    task_type: str = "qa",
) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "success": success,
        "completion_score": completion_score,
        "accuracy_score": accuracy_score,
        "question": question,
        "task_type": task_type,
    }


def _make_monitor(**kwargs) -> PerformanceMonitor:
    return PerformanceMonitor(
        output_dir=tempfile.mkdtemp(),
        enable_hallucination_detection=False,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# GoldenSetBuilder — __init__
# ---------------------------------------------------------------------------

def test_init_stores_source_dir(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(source), str(output))
    assert builder.source_dir == source


def test_init_stores_output_dir(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(source), str(output))
    assert builder.output_dir == output


# ---------------------------------------------------------------------------
# extract() — no source files
# ---------------------------------------------------------------------------

def test_extract_returns_empty_list_when_no_source_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases"])
    assert result == []


# ---------------------------------------------------------------------------
# extract() — failure_cases strategy
# ---------------------------------------------------------------------------

def test_extract_failure_cases_picks_failed_tasks(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", success=False, question="Long enough question here?"),
        _task("t2", success=True),
        _task("t3", success=False, question="Another long enough question here?"),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases"], min_question_length=5)
    ids = [r["task_id"] for r in result]
    assert "t1" in ids
    assert "t3" in ids
    assert "t2" not in ids


def test_extract_failure_cases_excludes_short_questions(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", success=False, question="Hi?"),  # too short (3 chars)
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases"], min_question_length=10)
    assert result == []


# ---------------------------------------------------------------------------
# extract() — edge_cases strategy
# ---------------------------------------------------------------------------

def test_extract_edge_cases_picks_completion_score_zero(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", completion_score=0.0),
        _task("t2", completion_score=0.5),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["edge_cases"])
    ids = [r["task_id"] for r in result]
    assert "t1" in ids
    assert "t2" not in ids


def test_extract_edge_cases_picks_completion_score_one(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", completion_score=1.0),
        _task("t2", completion_score=0.7),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["edge_cases"])
    ids = [r["task_id"] for r in result]
    assert "t1" in ids
    assert "t2" not in ids


def test_extract_edge_cases_excludes_middle_scores(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", completion_score=0.5),
        _task("t2", completion_score=0.9),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["edge_cases"])
    assert result == []


# ---------------------------------------------------------------------------
# extract() — high_value strategy
# ---------------------------------------------------------------------------

def test_extract_high_value_picks_high_accuracy(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", accuracy_score=0.95),
        _task("t2", accuracy_score=0.7),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["high_value"])
    ids = [r["task_id"] for r in result]
    assert "t1" in ids
    assert "t2" not in ids


def test_extract_high_value_picks_high_completion(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [
        _task("t1", completion_score=0.96, accuracy_score=0.5),
        _task("t2", completion_score=0.5, accuracy_score=0.5),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["high_value"])
    ids = [r["task_id"] for r in result]
    assert "t1" in ids
    assert "t2" not in ids


# ---------------------------------------------------------------------------
# extract() — max_cases limit
# ---------------------------------------------------------------------------

def test_extract_respects_max_cases(tmp_path):
    source = tmp_path / "source"
    tasks = [_task(f"t{i}", success=False, question="Long enough question here?") for i in range(20)]
    _write_tasks_file(source, "run.json", tasks)
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases"], max_cases=5, min_question_length=5)
    assert len(result) <= 5


def test_extract_max_cases_zero_returns_empty(tmp_path):
    source = tmp_path / "source"
    _write_tasks_file(source, "run.json", [_task("t1", success=False, question="Question long enough?")])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases"], max_cases=0, min_question_length=5)
    assert result == []


# ---------------------------------------------------------------------------
# extract() — multi-strategy deduplication
# ---------------------------------------------------------------------------

def test_extract_deduplicates_across_strategies(tmp_path):
    """A task matching both failure_cases and edge_cases must appear only once."""
    source = tmp_path / "source"
    # completion_score=0 and success=False → matches both strategies
    _write_tasks_file(source, "run.json", [
        _task("t1", success=False, completion_score=0.0, question="What is the capital city?"),
    ])
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    result = builder.extract(strategies=["failure_cases", "edge_cases"], min_question_length=5)
    task_ids = [r["task_id"] for r in result]
    assert task_ids.count("t1") == 1


# ---------------------------------------------------------------------------
# extract() — unsupported strategy
# ---------------------------------------------------------------------------

def test_extract_raises_on_unsupported_strategy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    builder = GoldenSetBuilder(str(source), str(tmp_path / "output"))
    with pytest.raises(ValueError):
        builder.extract(strategies=["bad_strategy"])


# ---------------------------------------------------------------------------
# save_candidates()
# ---------------------------------------------------------------------------

def test_save_candidates_creates_json_file(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    candidates = [_task("t1")]
    path = builder.save_candidates(candidates)
    assert path.exists()
    assert path.suffix == ".json"


def test_save_candidates_content_is_valid_json(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    candidates = [_task("t1"), _task("t2")]
    path = builder.save_candidates(candidates)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert len(loaded) == 2


def test_save_candidates_custom_filename(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    path = builder.save_candidates([_task("t1")], filename="my_candidates.json")
    assert path.name == "my_candidates.json"


def test_save_candidates_creates_output_dir_if_missing(tmp_path):
    output = tmp_path / "new" / "nested" / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    builder.save_candidates([_task("t1")])
    assert output.exists()


# ---------------------------------------------------------------------------
# merge_to_golden()
# ---------------------------------------------------------------------------

def test_merge_to_golden_creates_golden_file(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    path = builder.merge_to_golden([_task("t1")], version="v1.0")
    assert path.exists()
    assert "golden" in path.name


def test_merge_to_golden_file_has_required_keys(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    cases = [_task("t1"), _task("t2")]
    path = builder.merge_to_golden(cases, version="v1.0")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "version" in data
    assert "created_at" in data
    assert "count" in data
    assert "items" in data


def test_merge_to_golden_count_matches_cases(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    cases = [_task(f"t{i}") for i in range(7)]
    path = builder.merge_to_golden(cases, version="v2.0")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["count"] == 7
    assert len(data["items"]) == 7


def test_merge_to_golden_custom_output_name(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    path = builder.merge_to_golden([_task("t1")], output_name="custom_golden.json")
    assert path.name == "custom_golden.json"


def test_merge_to_golden_version_stored_correctly(tmp_path):
    output = tmp_path / "output"
    builder = GoldenSetBuilder(str(tmp_path / "source"), str(output))
    path = builder.merge_to_golden([_task("t1")], version="v3.1")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == "v3.1"


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
