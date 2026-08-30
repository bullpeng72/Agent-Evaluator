"""
tests/test_insight_changes_freshness.py
==========================================
SPEC-041 P33 — insight meta-diff + staleness.

`insights.insight_changes` diffs the *findings* vs the baseline (new/resolved
clusters, verdict move, judge-trust move, new security findings). `insights.
freshness` flags a stale baseline / unchanged eval set / mislabelled cases /
tiny eval set.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.comprehensive_report import (
    _build_freshness_banner,
    _build_insight_changes,
)
from agent_evaluator.reporting.insights import build_insights


def _t(tid, q, comp, acc, ok, reason=None):
    d = {"task_id": tid, "task_type": "qa", "question": q, "response": "r",
         "completion_score": comp, "accuracy_score": acc, "success": ok}
    if reason:
        d["partial_reason"] = reason
    return d


def _baseline():
    ts = [_t(f"p{i}", f"q{i}", 1.0, 0.9, True) for i in range(10)]
    ts += [_t(f"to{i}", f"tq{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    return {
        "timestamp": "2026-06-01T09:00:00Z",
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.75, "status": "pass", "gate": "pass", "details": {}}}},
        "tasks": ts,
    }


def _current():
    ts = [_t(f"p{i}", f"q{i}", 1.0, 0.9, True) for i in range(8)]
    ts += [_t(f"g{i}", f"new grounding q {i}", 0.4, 0.3, False,
              "answer not grounded in the retrieved context") for i in range(4)]
    ts += [_t("extra1", "brand new question", 1.0, 0.9, True)]
    return {
        "timestamp": "2026-08-30T09:00:00Z",
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.45, "status": "fail", "gate": "fail", "details": {}}}},
        "tasks": ts,
    }


class TestInsightChanges:
    def test_verdict_and_gate_move(self):
        ic = build_insights(_current(), _baseline())["insight_changes"]
        assert ic["verdict_change"] == {"from": "ready", "to": "not_ready"}
        assert "A" in ic["newly_failing_gates"]
        assert ic["newly_passing_gates"] == []

    def test_new_and_resolved_clusters(self):
        ic = build_insights(_current(), _baseline())["insight_changes"]
        assert any("grounded" in s for s in ic["new_clusters"])
        assert any("Timeout" in s for s in ic["resolved_clusters"])

    def test_none_without_baseline(self):
        assert build_insights(_current())["insight_changes"] is None

    def test_none_when_nothing_moved(self):
        b = _baseline()
        assert build_insights(b, b)["insight_changes"] is None


class TestFreshness:
    def test_old_baseline_warning(self):
        fr = build_insights(_current(), _baseline())["freshness"]
        assert fr["baseline_age_days"] > 30
        assert any("days old" in w for w in fr["warnings"])
        assert fr["eval_set_identical_to_baseline"] is False

    def test_unchanged_eval_set_flagged(self):
        # same file both sides, but it has failures -> "eval set unchanged" warning
        b = _baseline()
        fr = build_insights(b, b)["freshness"]
        assert fr["eval_set_identical_to_baseline"] is True
        assert any("has not changed" in w for w in fr["warnings"])

    def test_tiny_eval_set_warns_without_baseline(self):
        small = {"extra_metrics": {"harness_groups": {}},
                 "tasks": [_t(f"p{i}", f"q{i}", 1.0, 0.9, True) for i in range(5)]}
        fr = build_insights(small)["freshness"]
        assert fr is not None
        assert any("widen it" in w for w in fr["warnings"])
        assert fr["baseline_age_days"] is None

    def test_none_for_healthy_large_run(self):
        big = {"extra_metrics": {"harness_groups": {}},
               "tasks": [_t(f"p{i}", f"q{i}", 1.0, 0.95, True) for i in range(40)]}
        assert build_insights(big)["freshness"] is None


class TestSchemaAndReport:
    def test_schema_valid(self):
        ins = build_insights(_current(), _baseline())
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_report_renders(self):
        ins = build_insights(_current(), _baseline())
        h1 = _build_insight_changes(ins["insight_changes"])
        assert 'id="insight-changes"' in h1 and "Verdict" in h1
        h2 = _build_freshness_banner(ins["freshness"])
        assert 'id="freshness"' in h2 and "days old" in h2

    def test_report_empty_without_data(self):
        assert _build_insight_changes(None) == ""
        assert _build_freshness_banner(None) == ""
        assert _build_freshness_banner({"warnings": []}) == ""
