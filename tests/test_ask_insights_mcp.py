"""
tests/test_ask_insights_mcp.py
=================================
SPEC-041 P31 — the `ask_insights` stdio MCP server: interrogate a result JSON's
insight layer (verdict, path to green, why a task failed, task lists by filter)
instead of re-reading the whole HTML report. Pure retrieval, no result mutation.
"""
from __future__ import annotations

import json

import pytest

from agent_evaluator.integrations.ask_insights_mcp import (
    _insights_for,
    list_task_ids,
    readiness_text,
    summary_text,
    why_failed_text,
)


def _t(tid, q, comp, acc, ok, **kw):
    d = {"task_id": tid, "task_type": "qa", "question": q, "response": "r",
         "completion_score": comp, "accuracy_score": acc, "success": ok}
    d.update(kw)
    return d


@pytest.fixture()
def result_files(tmp_path):
    tasks = [_t(f"ok{i}", f"passing question {i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [
        _t("f1", "How do I get a refund for a returned item?", 0.4, 0.3, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="full refund within 14 days",
           context="Loyalty program grants points.", response="You earn points."),
        _t("f2", "What is the return shipping cost for a refund?", 0.4, 0.25, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="return shipping is free"),
        _t("f3", "Can I return an opened item for a refund?", 0.5, 0.2, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="opened items get store credit"),
        _t("h1", "Check delivery of order 10293", 0.0, 0.0, False,
           partial_reason="error: TimeoutError",
           tool_calls=[{"tool_name": "order_api", "success": False, "error": "503"}]),
    ]
    res = tmp_path / "v3.json"
    res.write_text(json.dumps({
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.55, "status": "fail", "gate": "fail", "details": {}},
            "D": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}}},
        "tasks": tasks,
    }))
    btasks = [dict(t) for t in tasks]
    for t in btasks:
        if t["task_id"] == "f1":
            t.update(completion_score=1.0, accuracy_score=0.9, success=True)
    base = tmp_path / "v2.json"
    base.write_text(json.dumps({
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.7, "status": "pass", "gate": "pass", "details": {}}}},
        "tasks": btasks,
    }))
    return str(res), str(base)


class TestSummary:
    def test_verdict_and_segments(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        out = summary_text(data, ins)
        assert "Verdict: NOT_READY" in out
        assert "A (Goal Achievement)" in out
        assert "Biggest failure" in out


class TestReadiness:
    def test_fix_plan_rendered(self, result_files):
        res, _ = result_files
        _data, ins = _insights_for(res)
        out = readiness_text(ins)
        assert "Fix plan" in out and "Gate A" in out
        assert "projected TCR" in out.lower() or "projected tcr" in out.lower()

    def test_none_message_when_healthy(self):
        assert "No path-to-green" in readiness_text({})


class TestWhyFailed:
    def test_task_detail(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        out = why_failed_text(data, ins, "f1")
        assert "Task f1" in out
        assert "Reason:" in out
        assert "trigger" in out.lower() or "segment" in out.lower()

    def test_unknown_task(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        assert "No task with id" in why_failed_text(data, ins, "nope")

    def test_tool_failure_task(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        out = why_failed_text(data, ins, "h1")
        assert "order_api" in out or "TimeoutError" in out


class TestList:
    def test_failing(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        out = list_task_ids(data, ins, "failing")
        assert "f1" in out and "h1" in out

    def test_segment_filter(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        out = list_task_ids(data, ins, "segment:return")
        assert "f1" in out or "f2" in out or "f3" in out

    def test_regressed_needs_baseline(self, result_files):
        res, base = result_files
        data, ins = _insights_for(res)
        assert "needs a baseline" in list_task_ids(data, ins, "regressed")
        data2, ins2 = _insights_for(res, base)
        assert "f1" in list_task_ids(data2, ins2, "regressed")

    def test_unknown_filter(self, result_files):
        res, _ = result_files
        data, ins = _insights_for(res)
        assert "Unknown filter" in list_task_ids(data, ins, "bogus")


class TestServer:
    def test_build_server_registers_tools(self):
        mcp = pytest.importorskip("mcp.server.fastmcp")  # noqa: F841
        from agent_evaluator.integrations.ask_insights_mcp import build_server

        srv = build_server()
        assert srv.name == "agent-evaluator-ask-insights"

    def test_main_without_mcp_extra_message(self, monkeypatch, capsys):
        import agent_evaluator.integrations.ask_insights_mcp as m

        def _boom():
            raise ImportError("no mcp")

        monkeypatch.setattr(m, "build_server", _boom)
        with pytest.raises(SystemExit):
            m.main()
        assert "agent-evaluator[mcp]" in capsys.readouterr().err
