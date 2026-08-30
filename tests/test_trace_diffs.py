"""
tests/test_trace_diffs.py
============================
SPEC-041 P32 — trace-level cross-version diff. cohort_comparison is aggregate;
`insights.trace_diffs` shows WHAT changed for a task that moved between cohort
versions — response text diff + trajectory step diff + score delta.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.comprehensive_report import _build_trace_diffs
from agent_evaluator.reporting.insights import _trace_diffs_section, build_insights


def _t(tid, q, comp, acc, ok, resp="", tools=None):
    return {"task_id": tid, "task_type": "qa", "question": q, "response": resp,
            "completion_score": comp, "accuracy_score": acc, "success": ok,
            "tool_calls": tools or []}


def _run(label, tasks):
    return {"extra_metrics": {"harness_groups": {}, "lineage": {"agent_version": label}},
            "tasks": tasks}


def _cohort():
    v1 = _run("v1", [
        _t("t1", "How do I get a refund?", 1.0, 0.9, True,
           "Unopened items get a full refund within 14 days.",
           [{"tool_name": "retrieve"}, {"tool_name": "answer"}]),
        _t("t2", "What is the water rating?", 1.0, 0.88, True, "It is IP68 rated."),
    ])
    v2 = _run("v2", [
        _t("t1", "How do I get a refund?", 1.0, 0.92, True,
           "Unopened items get a full refund within 14 days of purchase.",
           [{"tool_name": "retrieve"}, {"tool_name": "answer"}]),
        _t("t2", "What is the water rating?", 1.0, 0.9, True, "It is IP68 rated."),
    ])
    v3 = _run("v3", [
        _t("t1", "How do I get a refund?", 0.4, 0.3, False,
           "You earn loyalty points on returns, not a refund.",
           [{"tool_name": "retrieve"}, {"tool_name": "rerank"}, {"tool_name": "answer"}]),
        _t("t2", "What is the water rating?", 1.0, 0.9, True, "It is IP68 rated."),
    ])
    return v3, [v1, v2]


class TestTraceDiffsSection:
    def test_regressed_task_diffed(self):
        cur, coh = _cohort()
        td = _trace_diffs_section(cur, coh)
        assert td is not None
        row = next(d for d in td if d["task_id"] == "t1")
        assert row["verdict"] == "regressed"
        assert row["compared"] == ["v1", "v3"]
        assert row["score_delta"]["accuracy"] < 0

    def test_response_and_trajectory_diff(self):
        cur, coh = _cohort()
        row = next(d for d in _trace_diffs_section(cur, coh) if d["task_id"] == "t1")
        assert 0.0 <= row["response_diff"]["similarity"] < 1.0
        assert row["response_diff"]["added"] or row["response_diff"]["removed"]
        assert "rerank" in row["trajectory_diff"]["added"]
        assert "rerank" not in row["trajectory_diff"]["before"]

    def test_per_version_covers_all_versions_having_the_task(self):
        cur, coh = _cohort()
        row = next(d for d in _trace_diffs_section(cur, coh) if d["task_id"] == "t1")
        assert [v["label"] for v in row["per_version"]] == ["v3", "v1", "v2"]

    def test_unchanged_task_excluded(self):
        cur, coh = _cohort()
        td = _trace_diffs_section(cur, coh)
        assert all(d["task_id"] != "t2" for d in td)

    def test_none_without_cohort(self):
        cur, _ = _cohort()
        assert _trace_diffs_section(cur, None) is None
        assert _trace_diffs_section(cur, []) is None

    def test_reordered_flag(self):
        v1 = _run("v1", [_t("t1", "q", 1.0, 0.9, True, "same text here",
                            [{"tool_name": "a"}, {"tool_name": "b"}])])
        v2 = _run("v2", [_t("t1", "q", 0.4, 0.3, False, "same text here",
                            [{"tool_name": "b"}, {"tool_name": "a"}])])
        row = _trace_diffs_section(v2, [v1])[0]
        assert row["trajectory_diff"]["reordered"] is True


class TestBuildInsightsWiring:
    def test_key_and_schema(self):
        cur, coh = _cohort()
        ins = build_insights(cur, cohort=coh)
        assert ins["trace_diffs"] and ins["trace_diffs"][0]["task_id"] == "t1"
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_without_cohort(self):
        cur, _ = _cohort()
        assert build_insights(cur)["trace_diffs"] is None


class TestReportSection:
    def test_renders(self):
        cur, coh = _cohort()
        h = _build_trace_diffs(_trace_diffs_section(cur, coh))
        assert 'id="trace-diffs"' in h
        assert "regressed" in h and "rerank" in h and "Response" in h

    def test_empty_without_data(self):
        assert _build_trace_diffs(None) == ""
        assert _build_trace_diffs([]) == ""
