"""
tests/test_cli_dataset_promote.py
=====================================
SPEC-041 P15 — ``agent-eval dataset promote`` turns a result file's
``insights.review_queue`` into golden regression cases (closing the
failure -> regression-test loop).
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.cli.dataset import _cmd_promote


def _ns(result_file, **kw):
    d = dict(
        result_file=result_file, baseline=None, min_priority="medium",
        out=None, name=None, promote_version="review",
    )
    d.update(kw)
    return argparse.Namespace(**d)


def _result(tmp_path, name="v.json"):
    tasks = (
        # judge/heuristic disagreement -> high
        [{"task_id": f"d{i}", "task_type": "qa", "success": False,
          "question": f"q d{i}", "response": "r", "ground_truth": "gt",
          "accuracy_score": 0.2, "completion_score": 0.2,
          "llm_judge": {"skipped": False, "scores": {"overall": 9.0}}}
         for i in range(3)]
        # borderline -> medium
        + [{"task_id": f"b{i}", "task_type": "qa", "success": True,
            "question": f"q b{i}", "response": "r", "ground_truth": "gt",
            "accuracy_score": 0.66, "completion_score": 1.0,
            "llm_judge": {"skipped": False, "scores": {"overall": 7.0}}}
           for i in range(2)]
        + [{"task_id": f"ok{i}", "task_type": "qa", "success": True,
            "question": "q", "response": "r", "ground_truth": "gt",
            "accuracy_score": 0.95, "completion_score": 1.0,
            "llm_judge": {"skipped": False, "scores": {"overall": 9.0}}}
           for i in range(12)]
    )
    data = {
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.55, "status": "fail", "gate": "fail",
                  "details": {"tcr_pct": 55.0}},
        }},
        "tasks": tasks,
    }
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestPromote:
    def test_writes_golden_dataset_from_review_queue(self, tmp_path, capsys):
        rp = _result(tmp_path)
        rc = _cmd_promote(_ns(str(rp)))
        assert rc == 0
        gd = tmp_path / "golden_datasets"
        files = list(gd.glob("*.json"))
        assert len(files) == 1
        ds = json.loads(files[0].read_text())
        ids = {c["source_task_id"] for c in ds["items"]}
        assert {"d0", "d1", "d2"} <= ids            # disagreements promoted
        assert all(c["needs_human_review"] for c in ds["items"])
        assert all(c["review_reasons"] for c in ds["items"])

    def test_min_priority_high_drops_borderline(self, tmp_path):
        rp = _result(tmp_path)
        _cmd_promote(_ns(str(rp), min_priority="high"))
        ds = json.loads(next((tmp_path / "golden_datasets").glob("*.json")).read_text())
        prios = {c["review_priority"] for c in ds["items"]}
        assert prios == {"high"}

    def test_missing_file_exits_1(self, tmp_path, capsys):
        rc = _cmd_promote(_ns(str(tmp_path / "nope.json")))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_empty_queue_is_ok(self, tmp_path, capsys):
        data = {
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}},
            }},
            "tasks": [
                {"task_id": f"t{i}", "task_type": "qa", "success": True,
                 "question": "q", "response": "r", "ground_truth": "gt",
                 "accuracy_score": 0.95, "completion_score": 1.0}
                for i in range(20)
            ],
        }
        p = tmp_path / "clean.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        rc = _cmd_promote(_ns(str(p)))
        assert rc == 0
        assert "empty" in capsys.readouterr().out.lower()
