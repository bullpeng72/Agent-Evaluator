"""
tests/test_spec042_hold_on_undecided.py
========================================
SPEC-042 REQ-2 — insights.verdict.decision_ready + `agent-eval gate
--hold-on-undecided` (exit 75 for a would-be PASS whose deploy call is
statistically borderline).
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.cli.gate import cmd_gate
from agent_evaluator.reporting.insights import build_insights


def _task(tid, ok, acc=0.9):
    return {
        "task_id": tid,
        "success": ok,
        "accuracy_score": acc if ok else 0.1,
        "completion_score": 1.0 if ok else 0.0,
        "question": "q", "response": "r", "ground_truth": "r", "task_type": "qa",
    }


def _result(n_pass, n_fail, gate_a_score=0.9):
    tasks = [_task(f"p{i}", True) for i in range(n_pass)]
    tasks += [_task(f"f{i}", False) for i in range(n_fail)]
    return {
        "schema_version": "1.1",
        "summary": {"tcr": round(n_pass / (n_pass + n_fail) * 100, 1),
                    "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {
            "A": {"score": gate_a_score,
                  "status": "pass" if gate_a_score >= 0.7 else "fail",
                  "gate": "pass" if gate_a_score >= 0.7 else "fail",
                  "details": {}},
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
        max_review_high=None, notify=None, hold_on_undecided=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


# --------------------------------------------------------------------------- #
# insights.verdict.decision_ready
# --------------------------------------------------------------------------- #
class TestDecisionReadyField:
    def test_borderline_pass_rate_is_not_decision_ready(self):
        ins = build_insights(_result(12, 5))
        v = ins["verdict"]
        assert v["level"] in ("ready", "caution")
        assert v["decision_ready"] is False
        assert "straddles" in (v["undecided_reason"] or "")

    def test_clear_pass_is_decision_ready(self):
        ins = build_insights(_result(20, 0))
        v = ins["verdict"]
        assert v["decision_ready"] is True
        assert v["undecided_reason"] is None

    def test_hard_gate_failure_is_always_decision_ready(self):
        # a failing gate is a decisive call — not a statistical one
        ins = build_insights(_result(6, 11, gate_a_score=0.30))
        v = ins["verdict"]
        assert v["level"] == "not_ready"
        assert v["decision_ready"] is True

    def test_field_present_even_in_partial_mode(self):
        ins = build_insights(_result(12, 5), partial=True)
        assert "decision_ready" in ins["verdict"]


# --------------------------------------------------------------------------- #
# agent-eval gate --hold-on-undecided  (exit 75)
# --------------------------------------------------------------------------- #
class TestHoldOnUndecidedGate:
    def _file(self, tmp_path, n_pass, n_fail, **rkw):
        p = tmp_path / "run.json"
        p.write_text(json.dumps(_result(n_pass, n_fail, **rkw)))
        return str(p)

    def test_borderline_would_be_pass_becomes_exit_75(self, tmp_path, capsys):
        f = self._file(tmp_path, 12, 5)
        rc = cmd_gate(_ns(result_file=f, hold_on_undecided=True))
        assert rc == 75
        assert "held for human review" in capsys.readouterr().err.lower()

    def test_without_flag_borderline_still_passes(self, tmp_path):
        f = self._file(tmp_path, 12, 5)
        assert cmd_gate(_ns(result_file=f)) == 0

    def test_clear_pass_stays_zero_with_flag(self, tmp_path):
        f = self._file(tmp_path, 20, 0)
        assert cmd_gate(_ns(result_file=f, hold_on_undecided=True)) == 0

    def test_flag_never_overrides_a_real_failure(self, tmp_path):
        # TCR threshold not met -> exit 1, and --hold-on-undecided must not touch it
        f = self._file(tmp_path, 12, 5)
        rc = cmd_gate(_ns(result_file=f, tcr=95.0, hold_on_undecided=True))
        assert rc == 1
