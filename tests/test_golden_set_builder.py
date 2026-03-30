"""Tests for GoldenSetBuilder.

Covers __init__, extract() with all strategies, max_cases limit,
save_candidates(), merge_to_golden(), empty source directory,
and multi-strategy deduplication.
All tests use temporary directories for isolation.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from agent_evaluator.datasets.builder import GoldenSetBuilder


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


# ---------------------------------------------------------------------------
# __init__
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
