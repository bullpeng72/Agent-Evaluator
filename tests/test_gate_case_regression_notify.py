"""
tests/test_gate_case_regression_notify.py
============================================
SPEC-041 P26 — `agent-eval gate` case-level regression / review-queue gate
(exit 4) + `--notify` gate-result dispatch via AlertEngine.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.alerts import build_gate_result_message, dispatch_gate_result
from agent_evaluator.alerts.engine import _handler_for_target
from agent_evaluator.cli.gate import cmd_gate


def _task(tid, ok, acc, judge=None):
    t = {
        "task_id": tid, "success": ok, "accuracy_score": acc,
        "completion_score": 1.0 if ok else 0.0,
        "question": "q", "response": "r", "ground_truth": "r", "task_type": "qa",
    }
    if judge is not None:
        t["llm_judge"] = {"scores": {"overall": judge}}
    return t


def _result(tasks):
    return {
        "schema_version": "1.1",
        "summary": {"tcr": 60.0, "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
        }},
        "tasks": tasks,
    }


def _ns(**kw):
    base = dict(
        result_file="", tcr=None, accuracy=None, p95_latency=None,
        hallucination=None, llm_judge=None, fail_on_regression=None,
        baseline=None, baseline_version=None, save_baseline=False, junit_xml=None,
        golden_set=None, fail_on_golden_regression=False, explain=False,
        min_gate_score=None, gate_weights=None, gate_thresholds=None,
        required_gates=None, fail_on_gate_warn=False,
        baseline_result=None, fail_on_case_regression=False,
        max_review_high=None, notify=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


class TestCaseRegressionGate:
    def _files(self, tmp_path, base_tasks, cur_tasks):
        b = tmp_path / "baseline_result.json"
        c = tmp_path / "current.json"
        b.write_text(json.dumps(_result(base_tasks)))
        c.write_text(json.dumps(_result(cur_tasks)))
        return str(b), str(c)

    def test_exit_4_on_case_regression(self, tmp_path, capsys):
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9), _task("t2", True, 0.9)],
            [_task("t1", False, 0.1), _task("t2", True, 0.9)],
        )
        rc = cmd_gate(_ns(result_file=c, fail_on_case_regression=True, baseline_result=b))
        assert rc == 4
        assert "t1" in capsys.readouterr().err

    def test_no_exit_4_when_no_regression(self, tmp_path):
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9), _task("t3", False, 0.2)],
            [_task("t1", True, 0.9), _task("t3", False, 0.2)],
        )
        rc = cmd_gate(_ns(result_file=c, fail_on_case_regression=True, baseline_result=b))
        assert rc == 0

    def test_warns_and_skips_without_baseline_result(self, tmp_path, capsys):
        _, c = self._files(tmp_path, [_task("t1", True, 0.9)], [_task("t1", False, 0.1)])
        rc = cmd_gate(_ns(result_file=c, fail_on_case_regression=True))
        assert rc == 0
        assert "baseline result" in capsys.readouterr().err.lower()

    def test_baseline_summary_file_reused_when_it_carries_tasks(self, tmp_path):
        # --baseline points at a full result (has tasks[]) -> used for lineage
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9)],
            [_task("t1", False, 0.1)],
        )
        rc = cmd_gate(_ns(result_file=c, fail_on_case_regression=True, baseline=b))
        assert rc == 4

    def test_max_review_high_triggers_exit_4(self, tmp_path):
        # regressed AND judge/heuristic disagree (judge 9/10 vs heuristic ~0) ->
        # HIGH review items (P35r4: a plain regression alone is only MEDIUM)
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9, judge=9.0), _task("t2", True, 0.9, judge=9.0)],
            [_task("t1", False, 0.05, judge=9.0), _task("t2", False, 0.05, judge=9.0)],
        )
        rc = cmd_gate(_ns(result_file=c, max_review_high=0, baseline_result=b))
        assert rc == 4

    def test_max_review_high_generous_passes(self, tmp_path):
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9)],
            [_task("t1", False, 0.05)],
        )
        rc = cmd_gate(_ns(result_file=c, max_review_high=999, baseline_result=b))
        assert rc == 0

    def test_golden_regression_still_outranks_case_regression(self, tmp_path):
        b, c = self._files(
            tmp_path,
            [_task("t1", True, 0.9)],
            [_task("t1", False, 0.1)],
        )
        golden = tmp_path / "golden.json"
        golden.write_text(json.dumps([{"task_id": "gone", "question": "x"}]))
        rc = cmd_gate(_ns(
            result_file=c, fail_on_case_regression=True, baseline_result=b,
            golden_set=str(golden), fail_on_golden_regression=True,
        ))
        assert rc == 3


class TestNotify:
    def test_notify_bogus_target_reported_exit_unaffected(self, tmp_path, capsys):
        c = tmp_path / "current.json"
        c.write_text(json.dumps(_result([_task("t1", True, 0.9)])))
        rc = cmd_gate(_ns(result_file=str(c), notify=["file:///nope"]))
        assert rc == 0
        assert "failed" in capsys.readouterr().err.lower()

    def test_handler_resolution(self):
        assert _handler_for_target("file:///x") is None
        assert _handler_for_target("") is None
        w = _handler_for_target("webhook://example.com/h")
        assert type(w).__name__ == "WebhookHandler" and w.url == "https://example.com/h"
        s = _handler_for_target("slack://hooks.slack.com/services/T/B/X")
        assert type(s).__name__ == "SlackHandler"
        assert s.webhook_url == "https://hooks.slack.com/services/T/B/X"
        assert type(_handler_for_target("https://hooks.slack.com/services/A/B/C")).__name__ == "SlackHandler"
        assert type(_handler_for_target("https://example.com/x")).__name__ == "WebhookHandler"

    def test_message_includes_regressed_and_verdict(self):
        from agent_evaluator.reporting.insights import build_insights

        base = _result([_task("t1", True, 0.9), _task("t2", True, 0.9)])
        cur = _result([_task("t1", False, 0.1), _task("t2", True, 0.9)])
        msg = build_gate_result_message(
            build_insights(cur, base), passed=False, result_file="cur.json", exit_code=4,
        )
        assert "FAILED" in msg and "cur.json" in msg
        assert "Regressed cases (1)" in msg and "t1" in msg

    def test_dispatch_never_raises(self):
        rows = dispatch_gate_result(
            ["file:///nope", "webhook://"], {"narrative": "x"}, passed=False, exit_code=1,
        )
        assert all(r["ok"] is False and r["error"] for r in rows)
