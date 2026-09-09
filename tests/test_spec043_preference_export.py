"""
tests/test_spec043_preference_export.py
=======================================
SPEC-043 REQ-6b — ``agent-eval feedback export-preferences``.

Covers ``datasets.preference_export`` (row extraction + file writing), the
pairwise-judge history serialization, and the CLI wiring.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.datasets.preference_export import (
    export_preferences,
    iter_preference_rows,
)


def _result(**over):
    base = {
        "tasks": [
            {"task_id": "t1", "question": "capital of france", "response": "berlin",
             "success": False, "accuracy_score": 0.1, "completion_score": 0.1},
            {"task_id": "t2", "question": "capital of france please",
             "response": "paris", "success": True, "accuracy_score": 0.95,
             "completion_score": 1.0},
        ],
        "extra_metrics": {},
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# iter_preference_rows
# --------------------------------------------------------------------------- #
class TestIterRows:
    def test_pairwise_judge_rows(self):
        r = _result(extra_metrics={"llm_judge_pairwise": [
            {"winner": "a", "question": "q", "response_a": "A", "response_b": "B"},
            {"winner": "tie", "question": "q2", "response_a": "A2", "response_b": "B2"},
            {"skipped": True},
            {"winner": "b", "question": "q3", "response_a": "", "response_b": ""},  # no text
        ]})
        rows = [x for x in iter_preference_rows(r) if x["source"] == "pairwise_judge"]
        assert len(rows) == 2
        assert rows[0]["preferred"] == "a"
        assert rows[1]["preferred"] == "tie"

    def test_annotation_from_extra_metrics(self):
        r = _result(extra_metrics={"preference_annotations": [
            {"question": "q", "response_a": "x", "response_b": "y",
             "preferred": "b", "annotator": "alice"},
        ]})
        rows = [x for x in iter_preference_rows(r) if x["source"] == "annotation"]
        assert rows == [{
            "question": "q", "response_a": "x", "response_b": "y",
            "preferred": "b", "source": "annotation", "annotator": "alice",
        }]

    def test_annotation_from_task_extra(self):
        r = _result()
        r["tasks"][0]["extra"] = {"preference": {
            "response_a": "aa", "response_b": "bb", "preferred": "a",
        }}
        rows = [x for x in iter_preference_rows(r) if x["source"] == "annotation"]
        assert len(rows) == 1
        assert rows[0]["question"] == "capital of france"
        assert "annotator" not in rows[0]

    def test_contrast_pair_joins_responses(self):
        r = _result(extra_metrics={"insights": {"contrast_pairs": [
            {"fail_task_id": "t1", "pass_task_id": "t2", "fail_question": "capital?"},
        ]}})
        rows = [x for x in iter_preference_rows(r) if x["source"] == "contrast_pair"]
        assert rows == [{
            "question": "capital?", "response_a": "berlin", "response_b": "paris",
            "preferred": "b", "source": "contrast_pair",
        }]

    def test_contrast_pair_skipped_if_task_missing(self):
        r = _result(extra_metrics={"insights": {"contrast_pairs": [
            {"fail_task_id": "nope", "pass_task_id": "t2"},
        ]}})
        assert [x for x in iter_preference_rows(r) if x["source"] == "contrast_pair"] == []

    def test_non_dict_input_yields_nothing(self):
        assert list(iter_preference_rows("garbage")) == []  # type: ignore[arg-type]

    def test_winner_synonyms_normalised(self):
        r = _result(extra_metrics={"llm_judge_pairwise": [
            {"winner": "win_b", "question": "q", "response_a": "A", "response_b": "B"},
        ]})
        rows = list(iter_preference_rows(r))
        assert rows[0]["preferred"] == "b"


# --------------------------------------------------------------------------- #
# export_preferences
# --------------------------------------------------------------------------- #
class TestExport:
    def test_writes_jsonl_and_summary(self, tmp_path):
        (tmp_path / "r1.json").write_text(json.dumps(_result(extra_metrics={
            "llm_judge_pairwise": [
                {"winner": "a", "question": "q", "response_a": "A", "response_b": "B"},
            ],
            "insights": {"contrast_pairs": [
                {"fail_task_id": "t1", "pass_task_id": "t2"},
            ]},
        })))
        out = tmp_path / "prefs.jsonl"
        summary = export_preferences(tmp_path, out)
        assert summary["n_written"] == 2
        assert summary["by_source"] == {"pairwise_judge": 1, "contrast_pair": 1}
        lines = [json.loads(x) for x in out.read_text().splitlines()]
        assert all("result_file" in x for x in lines)

    def test_single_file_input(self, tmp_path):
        f = tmp_path / "r.json"
        f.write_text(json.dumps(_result(extra_metrics={"preference_annotations": [
            {"question": "q", "response_a": "x", "response_b": "y", "preferred": "a"},
        ]})))
        summary = export_preferences(f, tmp_path / "p.jsonl")
        assert summary["n_written"] == 1 and summary["n_files_scanned"] == 1

    def test_malformed_file_skipped(self, tmp_path):
        (tmp_path / "ok.json").write_text(json.dumps(_result(extra_metrics={
            "preference_annotations": [
                {"question": "q", "response_a": "x", "response_b": "y", "preferred": "a"},
            ]})))
        (tmp_path / "bad.json").write_text("{not json")
        summary = export_preferences(tmp_path, tmp_path / "p.jsonl")
        assert summary["n_written"] == 1
        assert summary["n_files_skipped"] == 1

    def test_dedupes_identical_rows(self, tmp_path):
        payload = _result(extra_metrics={"preference_annotations": [
            {"question": "q", "response_a": "x", "response_b": "y", "preferred": "a"},
        ]})
        (tmp_path / "a.json").write_text(json.dumps(payload))
        (tmp_path / "b.json").write_text(json.dumps(payload))
        summary = export_preferences(tmp_path, tmp_path / "p.jsonl")
        assert summary["n_written"] == 1

    def test_empty_dir_writes_empty_file(self, tmp_path):
        (tmp_path / "e.json").write_text(json.dumps({"tasks": []}))
        summary = export_preferences(tmp_path, tmp_path / "p.jsonl")
        assert summary["n_written"] == 0
        assert (tmp_path / "p.jsonl").exists()


# --------------------------------------------------------------------------- #
# pairwise-judge history serialization
# --------------------------------------------------------------------------- #
class TestPairwiseSerialization:
    def test_monitor_dumps_pairwise_history(self, tmp_path, monkeypatch):
        from agent_evaluator import PerformanceMonitor

        mon = PerformanceMonitor(output_dir=str(tmp_path), enable_llm_judge=False)

        class _FakeJudge:
            model = "fake"
            sample_rate = 0.1
            pairwise_results = [
                {"winner": "a", "question": "q", "response_a": "A",
                 "response_b": "B", "reasoning": "..."},
                {"skipped": True, "reason": "budget"},
            ]

        mon.llm_judge = _FakeJudge()  # type: ignore[assignment]
        from agent_evaluator import create_taskresult

        mon.record_task(create_taskresult(  # minimal task so a report is produced
            task_id="t1", question="q", response="r", ground_truth="r",
            execution_time=0.1,
        ))
        path = mon.save_to_file("run")
        data = json.loads(open(path).read())
        pw = data["extra_metrics"].get("llm_judge_pairwise")
        assert isinstance(pw, list) and len(pw) == 1  # skipped one dropped
        assert pw[0]["winner"] == "a"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class TestCli:
    def test_export_command(self, tmp_path, capsys):
        from agent_evaluator.cli.feedback import cmd_feedback

        (tmp_path / "r.json").write_text(json.dumps(_result(extra_metrics={
            "preference_annotations": [
                {"question": "q", "response_a": "x", "response_b": "y", "preferred": "a"},
            ]})))
        out = tmp_path / "prefs.jsonl"
        rc = cmd_feedback(argparse.Namespace(
            feedback_command="export-preferences", path=str(tmp_path), out=str(out),
        ))
        assert rc == 0
        assert out.exists()
        assert "Exported 1 preference row" in capsys.readouterr().out

    def test_missing_path_exits_1(self, tmp_path, capsys):
        from agent_evaluator.cli.feedback import cmd_feedback

        rc = cmd_feedback(argparse.Namespace(
            feedback_command="export-preferences",
            path=str(tmp_path / "nope"), out=str(tmp_path / "p.jsonl"),
        ))
        assert rc == 1

    def test_no_subcommand_prints_help(self, capsys):
        from agent_evaluator.cli.feedback import cmd_feedback

        rc = cmd_feedback(argparse.Namespace(feedback_command=None))
        assert rc == 1
