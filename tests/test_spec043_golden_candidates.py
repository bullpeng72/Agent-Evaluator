"""
tests/test_spec043_golden_candidates.py
=======================================
SPEC-043 REQ-4 — production anomaly / low-confidence → golden-set candidate queue.

Covers ``datasets.golden_candidates``, the ``StreamingEvaluator`` sink,
``agent-eval dataset review-candidates``, and the ``golden_health`` count line.
"""
from __future__ import annotations

import argparse
import json

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.datasets.golden_candidates import (
    append_candidate,
    load_candidates,
    pending_candidates,
    record_candidate_review,
    summarize_candidates,
)
from agent_evaluator.streaming.evaluator import StreamingEvaluator


# --------------------------------------------------------------------------- #
# golden_candidates module
# --------------------------------------------------------------------------- #
class TestGoldenCandidatesModule:
    def test_append_and_load_roundtrip(self, tmp_path):
        p = tmp_path / "q.jsonl"
        e = append_candidate(p, question="q1", response="r1", trigger="error",
                             task_id="t1")
        assert e["kind"] == "candidate" and e["reviewed"] is False and e["id"]
        rows = load_candidates(p)
        assert len(rows) == 1 and rows[0]["question"] == "q1"

    def test_load_missing_file_returns_empty(self, tmp_path):
        assert load_candidates(tmp_path / "nope.jsonl") == []

    def test_corrupt_line_skipped(self, tmp_path):
        p = tmp_path / "q.jsonl"
        append_candidate(p, question="q", response="r", trigger="error")
        with open(p, "a") as f:
            f.write("{bad json\n")
        append_candidate(p, question="q2", response="r2", trigger="anomaly:tcr")
        assert len(load_candidates(p)) == 2

    def test_pending_excludes_reviewed(self, tmp_path):
        p = tmp_path / "q.jsonl"
        a = append_candidate(p, question="a", response="", trigger="error")
        append_candidate(p, question="b", response="", trigger="error")
        record_candidate_review(p, candidate_id=a["id"], decision="reject")
        pend = pending_candidates(load_candidates(p))
        assert [x["question"] for x in pend] == ["b"]

    def test_review_rejects_bad_decision(self, tmp_path):
        p = tmp_path / "q.jsonl"
        e = append_candidate(p, question="a", response="", trigger="error")
        with pytest.raises(ValueError):
            record_candidate_review(p, candidate_id=e["id"], decision="maybe")

    def test_summarize_counts(self, tmp_path):
        p = tmp_path / "q.jsonl"
        a = append_candidate(p, question="a", response="", trigger="error")
        append_candidate(p, question="b", response="", trigger="low_confidence:0.3")
        append_candidate(p, question="c", response="", trigger="anomaly:tcr")
        record_candidate_review(p, candidate_id=a["id"], decision="accept")
        s = summarize_candidates(load_candidates(p))
        assert s["n_candidates"] == 3
        assert s["n_pending"] == 2
        assert s["by_decision"] == {"accept": 1}
        assert s["by_trigger"] == {"error": 1, "low_confidence": 1, "anomaly": 1}


# --------------------------------------------------------------------------- #
# StreamingEvaluator sink
# --------------------------------------------------------------------------- #
class TestStreamingSink:
    def _ev(self, tmp_path, **kw):
        mon = PerformanceMonitor(output_dir=str(tmp_path))
        return StreamingEvaluator(monitor=mon, **kw), tmp_path / "golden_candidates.jsonl"

    def test_no_sink_is_unchanged(self, tmp_path):
        ev, sink = self._ev(tmp_path)
        ev.record("t1", success=False, execution_time=1.0, has_error=True)
        assert not sink.exists()

    def test_error_task_becomes_candidate(self, tmp_path):
        ev, sink = self._ev(tmp_path, golden_candidate_sink=None)
        ev.golden_candidate_sink = str(sink)
        ev.record("t1", success=False, execution_time=1.0, has_error=True,
                  question="boom", response="stack")
        rows = load_candidates(sink)
        assert len(rows) == 1
        assert rows[0]["trigger"] == "error" and rows[0]["task_id"] == "t1"
        assert rows[0]["question"] == "boom"

    def test_low_confidence_becomes_candidate(self, tmp_path):
        ev, sink = self._ev(
            tmp_path, golden_candidate_sink=None,
        )
        ev.golden_candidate_sink = str(sink)
        ev.candidate_confidence_threshold = 0.5
        ev.record("t1", success=True, execution_time=1.0, question="q",
                  response="r", confidence=0.2)
        rows = load_candidates(sink)
        assert rows and rows[0]["trigger"].startswith("low_confidence:")
        assert rows[0]["extra"]["confidence"] == 0.2

    def test_high_confidence_success_no_candidate(self, tmp_path):
        ev, sink = self._ev(tmp_path)
        ev.golden_candidate_sink = str(sink)
        ev.candidate_confidence_threshold = 0.5
        ev.record("t1", success=True, execution_time=1.0, confidence=0.9)
        assert not sink.exists()

    def test_no_threshold_means_only_errors_trigger(self, tmp_path):
        ev, sink = self._ev(tmp_path)
        ev.golden_candidate_sink = str(sink)
        ev.record("t1", success=True, execution_time=1.0, confidence=0.01)
        assert not sink.exists()


# --------------------------------------------------------------------------- #
# CLI: dataset review-candidates
# --------------------------------------------------------------------------- #
def _ns(**kw):
    base = dict(
        candidates_file="", accept=None, reject=None, defer=None,
        accept_to=None, reviewed_by=None, as_json=False,
    )
    base.update(kw)
    return argparse.Namespace(dataset_command="review-candidates", **base)


class TestReviewCandidatesCli:
    def test_list_pending(self, tmp_path, capsys):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        append_candidate(q, question="what is 2+2", response="5", trigger="error")
        rc = cmd_dataset(_ns(candidates_file=str(q)))
        assert rc == 0
        assert "1 pending" in capsys.readouterr().out

    def test_list_json(self, tmp_path, capsys):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        append_candidate(q, question="q", response="r", trigger="anomaly:tcr")
        cmd_dataset(_ns(candidates_file=str(q), as_json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["n_pending"] == 1

    def test_reject_records_review(self, tmp_path, capsys):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        e = append_candidate(q, question="q", response="r", trigger="error")
        rc = cmd_dataset(_ns(candidates_file=str(q), reject=e["id"]))
        assert rc == 0
        assert pending_candidates(load_candidates(q)) == []

    def test_accept_without_to_fails(self, tmp_path):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        e = append_candidate(q, question="q", response="r", trigger="error")
        rc = cmd_dataset(_ns(candidates_file=str(q), accept=e["id"]))
        assert rc == 1

    def test_accept_merges_into_golden(self, tmp_path):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        e = append_candidate(q, question="what is 2+2", response="5", trigger="error")
        golden = tmp_path / "golden" / "prod.json"
        rc = cmd_dataset(_ns(
            candidates_file=str(q), accept=e["id"], accept_to=str(golden),
        ))
        assert rc == 0
        # a golden file with the case now exists somewhere under tmp_path/golden
        merged = list((tmp_path / "golden").glob("*.json"))
        assert merged
        blob = json.loads(merged[0].read_text())
        cases = blob if isinstance(blob, list) else blob.get("items") or blob.get("cases")
        assert any("2+2" in (c.get("question") or "") for c in cases)
        assert pending_candidates(load_candidates(q)) == []

    def test_unknown_id_fails(self, tmp_path):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        append_candidate(q, question="q", response="r", trigger="error")
        rc = cmd_dataset(_ns(candidates_file=str(q), reject="deadbeef"))
        assert rc == 1

    def test_two_decisions_at_once_fails(self, tmp_path):
        from agent_evaluator.cli.dataset import cmd_dataset

        q = tmp_path / "golden_candidates.jsonl"
        e = append_candidate(q, question="q", response="r", trigger="error")
        rc = cmd_dataset(_ns(candidates_file=str(q), reject=e["id"], defer=e["id"]))
        assert rc == 1


# --------------------------------------------------------------------------- #
# golden_health pending line
# --------------------------------------------------------------------------- #
class TestGoldenHealthPendingLine:
    def test_pending_count_surfaced(self, tmp_path):
        from agent_evaluator.datasets.golden_health import assess_golden_health

        append_candidate(tmp_path / "golden_candidates.jsonl",
                         question="q", response="r", trigger="error")
        golden = tmp_path / "golden.json"
        golden.write_text(json.dumps({"cases": [{"question": "what is 2+2",
                                                 "ground_truth": "4"}]}))
        gh = assess_golden_health(str(golden), {"tasks": []})
        assert gh is not None
        assert gh["pending_production_candidates"] == 1
        assert "awaiting review" in gh["note"]

    def test_absent_when_no_queue(self, tmp_path):
        from agent_evaluator.datasets.golden_health import assess_golden_health

        golden = tmp_path / "golden.json"
        golden.write_text(json.dumps({"cases": [{"question": "q", "ground_truth": "a"}]}))
        gh = assess_golden_health(str(golden), {"tasks": []})
        assert gh is not None
        assert "pending_production_candidates" not in gh
