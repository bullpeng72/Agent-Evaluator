"""
tests/test_spec043_decision_ledger.py
======================================
SPEC-043 REQ-3 — deploy-decision ledger
(``rca.decision_ledger`` + ``insights.deploy_decision`` +
``agent-eval decisions`` + ``agent-eval gate --decision-log``).
"""
from __future__ import annotations

import argparse
import json

import pytest

from agent_evaluator.cli.decisions import cmd_decisions
from agent_evaluator.cli.gate import cmd_gate
from agent_evaluator.rca.decision_ledger import (
    load_decisions,
    record_decision_outcome,
    record_gate_decision,
    summarize_decisions,
)
from agent_evaluator.reporting.insights import build_insights


def _log(tmp_path):
    return str(tmp_path / "decisions.jsonl")


def _result(tasks_ok=3, gate_a=0.9):
    tasks = [{"task_id": f"t{i}", "success": True, "accuracy_score": 0.9,
              "completion_score": 1.0, "question": "q", "response": "r",
              "ground_truth": "r", "task_type": "qa"} for i in range(tasks_ok)]
    return {
        "summary": {"tcr": 100.0, "total_tasks": len(tasks)},
        "agent_version": "abc123",
        "extra_metrics": {"harness_groups": {"A": {"score": gate_a, "status": "pass"}}},
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
        requirements=None, require_spec_coverage=False, decision_log=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


class TestLedgerModule:
    def test_record_and_load_gate_run(self, tmp_path):
        log = _log(tmp_path)
        e = record_gate_decision(
            log, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
            undecided_reason="CI straddles", gate_scores={"A": 0.9},
        )
        assert len(e["id"]) == 12
        rows = load_decisions(log)
        assert rows == [e]
        assert rows[0]["kind"] == "gate_run"

    def test_outcome_links_to_latest_pending(self, tmp_path):
        log = _log(tmp_path)
        e1 = record_gate_decision(log, result_file="a", agent_version=None,
                                  exit_code=75, verdict_level="ready",
                                  decision_ready=False)
        e2 = record_gate_decision(log, result_file="b", agent_version=None,
                                  exit_code=75, verdict_level="ready",
                                  decision_ready=False)
        o = record_decision_outcome(log, outcome="overridden", decided_by="sw",
                                    rationale="small eval set")
        assert o["gate_run_id"] == e2["id"]        # latest pending
        s = summarize_decisions(load_decisions(log))
        assert s["n_pending"] == 1
        assert s["pending"][0]["id"] == e1["id"]
        assert s["by_outcome"] == {"overridden": 1}

    def test_explicit_gate_run_id(self, tmp_path):
        log = _log(tmp_path)
        e1 = record_gate_decision(log, result_file="a", agent_version=None,
                                  exit_code=0, verdict_level="ready",
                                  decision_ready=True)
        record_gate_decision(log, result_file="b", agent_version=None,
                             exit_code=75, verdict_level="ready",
                             decision_ready=False)
        record_decision_outcome(log, outcome="accepted", decided_by="sw",
                                gate_run_id=e1["id"])
        s = summarize_decisions(load_decisions(log))
        assert s["n_pending"] == 1                 # e2 still open

    def test_invalid_outcome_raises(self, tmp_path):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="a", agent_version=None, exit_code=75,
                             verdict_level="ready", decision_ready=False)
        with pytest.raises(ValueError):
            record_decision_outcome(log, outcome="maybe", decided_by="sw")

    def test_no_pending_raises(self, tmp_path):
        log = _log(tmp_path)
        with pytest.raises(ValueError):
            record_decision_outcome(log, outcome="accepted", decided_by="sw")

    def test_missing_file_and_corrupt_line(self, tmp_path):
        assert load_decisions(str(tmp_path / "nope.jsonl")) == []
        log = tmp_path / "d.jsonl"
        log.write_text('{"kind": "gate_run", "id": "x"}\nnot json\n{"kind":"outcome","gate_run_id":"x","outcome":"accepted"}\n')
        rows = load_decisions(str(log))
        assert len(rows) == 2

    def test_summarize_last(self, tmp_path):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="a", agent_version=None, exit_code=0,
                             verdict_level="ready", decision_ready=True)
        e2 = record_gate_decision(log, result_file="b", agent_version=None,
                                  exit_code=75, verdict_level="ready",
                                  decision_ready=False)
        record_decision_outcome(log, outcome="held", decided_by="sw")
        s = summarize_decisions(load_decisions(log))
        assert s["last"]["gate_run"]["id"] == e2["id"]
        assert s["last"]["outcome"]["outcome"] == "held"


class TestInsightsDeployDecision:
    def test_null_without_log(self):
        assert build_insights(_result())["deploy_decision"] is None

    def test_populated_with_log(self, tmp_path):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="r", agent_version=None, exit_code=75,
                             verdict_level="ready", decision_ready=False)
        ins = build_insights(_result(), decision_log_path=log)
        dd = ins["deploy_decision"]
        assert dd["n_gate_runs"] == 1
        assert dd["n_pending"] == 1
        assert dd["last"]["pending"] is True

    def test_reflects_recorded_outcome(self, tmp_path):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="r", agent_version=None, exit_code=75,
                             verdict_level="ready", decision_ready=False)
        record_decision_outcome(log, outcome="overridden", decided_by="sw")
        dd = build_insights(_result(), decision_log_path=log)["deploy_decision"]
        assert dd["n_pending"] == 0
        assert dd["last"]["outcome"] == "overridden"


class TestDecisionsCli:
    def _dns(self, **kw):
        return argparse.Namespace(decisions_command=None, **kw)

    def test_list_empty(self, tmp_path, capsys):
        rc = cmd_decisions(argparse.Namespace(
            decisions_command="list", log=_log(tmp_path), pending=False, as_json=False))
        assert rc == 0
        assert "No gate runs" in capsys.readouterr().out

    def test_record_then_list(self, tmp_path, capsys):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="r", agent_version=None, exit_code=75,
                             verdict_level="ready", decision_ready=False)
        rc = cmd_decisions(argparse.Namespace(
            decisions_command="record", log=log, outcome="held",
            decided_by="sw", rationale="wait for more data", gate_run_id=None))
        assert rc == 0
        assert "Recorded: held" in capsys.readouterr().out

        rc = cmd_decisions(argparse.Namespace(
            decisions_command="list", log=log, pending=True, as_json=False))
        assert rc == 0
        assert "No gate runs awaiting" in capsys.readouterr().out

    def test_record_no_pending_returns_1(self, tmp_path, capsys):
        rc = cmd_decisions(argparse.Namespace(
            decisions_command="record", log=_log(tmp_path), outcome="accepted",
            decided_by="sw", rationale=None, gate_run_id=None))
        assert rc == 1
        assert "no pending" in capsys.readouterr().err.lower()

    def test_list_json(self, tmp_path, capsys):
        log = _log(tmp_path)
        record_gate_decision(log, result_file="r", agent_version=None, exit_code=0,
                             verdict_level="ready", decision_ready=True)
        rc = cmd_decisions(argparse.Namespace(
            decisions_command="list", log=log, pending=False, as_json=True))
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["n_gate_runs"] == 1


class TestGateDecisionLog:
    def test_gate_appends_entry(self, tmp_path):
        r = tmp_path / "run.json"
        r.write_text(json.dumps(_result()))
        log = _log(tmp_path)
        rc = cmd_gate(_ns(result_file=str(r), decision_log=log))
        assert rc == 0
        rows = load_decisions(log)
        assert len(rows) == 1
        assert rows[0]["exit_code"] == 0
        assert rows[0]["agent_version"] == "abc123"
        assert rows[0]["gate_scores"].get("A") == 0.9

    def test_no_decision_log_writes_nothing(self, tmp_path):
        r = tmp_path / "run.json"
        r.write_text(json.dumps(_result()))
        assert cmd_gate(_ns(result_file=str(r))) == 0
        assert not (tmp_path / "decisions.jsonl").exists()
