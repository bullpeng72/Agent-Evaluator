"""
tests/test_briefs_narrative_audit.py
=======================================
SPEC-041 P34 — audience-targeted briefs + narrative claim audit.

`insights.briefs{pm, qa, engineer}` is the same run summarised deterministically
for three audiences. `insights.narrative_audit` checks the narrative's
quantitative claims against the structured numbers (catches an over-claiming
LLM narrator).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.comprehensive_report import (
    _build_briefs,
    _build_narrative_audit_note,
)
from agent_evaluator.reporting.insights import (
    _narrative_audit_section,
    build_insights,
)


def _t(tid, q, comp, acc, ok, reason=None):
    d = {"task_id": tid, "task_type": "qa", "question": q, "response": "r",
         "completion_score": comp, "accuracy_score": acc, "success": ok}
    if reason:
        d["partial_reason"] = reason
    return d


def _failing_report():
    tasks = [_t(f"p{i}", f"topic alpha question {i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"g{i}", f"refund shipping return question {i}", 0.4, 0.3, False,
                 "answer not grounded in the retrieved context") for i in range(4)]
    tasks += [_t("to0", "delivery status", 0.0, 0.0, False, "error: TimeoutError")]
    return {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.55, "status": "fail", "gate": "fail", "details": {}},
        "D": {"score": 0.62, "status": "warn", "gate": "warn", "details": {}}}},
        "tasks": tasks}


class TestBriefs:
    def test_pm_hold_with_effort_and_confidence(self):
        br = build_insights(_failing_report())["briefs"]
        assert br is not None
        assert br["pm"].startswith("Hold")
        assert "Gate A" in br["pm"]
        assert "confidence" in br["pm"].lower()

    def test_engineer_checklist_from_fix_plan(self):
        br = build_insights(_failing_report())["briefs"]
        eng = br["engineer"]
        assert isinstance(eng, list) and eng
        assert any("grounded" in s for s in eng)
        assert any("projected TCR" in s for s in eng)

    def test_qa_paragraph_mentions_review_and_segments(self):
        br = build_insights(_failing_report())["briefs"]
        assert "review" in br["qa"].lower()

    def test_healthy_run_still_produces_briefs(self):
        healthy = {"extra_metrics": {"harness_groups": {
            "A": {"score": 0.92, "status": "pass", "gate": "pass", "details": {}}}},
            "tasks": [_t(f"p{i}", f"q{i}", 1.0, 0.95, True) for i in range(30)]}
        br = build_insights(healthy)["briefs"]
        assert br is not None and br["pm"].startswith("Ship")

    def test_none_when_no_data(self):
        assert build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": []})[
            "briefs"
        ] is None


class TestNarrativeAudit:
    def test_template_narrative_is_clean(self):
        ins = build_insights(_failing_report())
        na = ins["narrative_audit"]
        assert na is not None and na["claims_checked"] is True
        assert na["clean"] is True
        assert na["adjustments"] == []

    def test_overclaiming_narrator_is_flagged(self):
        def bad(_d):
            return ("The agent is deployment-ready. TCR is 99%. "
                    "Big improvement since the baseline.")

        na = build_insights(_failing_report(), narrator=bad)["narrative_audit"]
        assert na["clean"] is False
        joined = " ".join(na["adjustments"])
        assert "ready to ship" in joined
        assert "headline metric" in joined or "baseline" in joined

    def test_component_health_percent_is_not_flagged(self):
        # P35: a bare "40%" that is NOT attributed to TCR/accuracy must not trip
        # the audit — component-health scores are legitimately different numbers.
        def calm(_d):
            return ("Gate A is below target. The biggest measured shortfall is "
                    "response relevance/completeness (40%). Confidence is LOW.")

        na = build_insights(_failing_report(), narrator=calm)["narrative_audit"]
        assert not any("headline metric" in a for a in na["adjustments"])

    def test_low_confidence_not_hedged_is_flagged(self):
        def terse(_d):
            return "Gate A is failing. Fix the grounding issues."

        na = build_insights(_failing_report(), narrator=terse)["narrative_audit"]
        assert any("LOW" in a for a in na["adjustments"])

    def test_direct_call_returns_none_for_empty(self):
        assert _narrative_audit_section("", {}) is None


class TestSchemaAndReport:
    def test_schema_valid(self):
        for kwargs in ({}, {"narrator": lambda _d: "deployment-ready, TCR 99%"}):
            ins = build_insights(_failing_report(), **kwargs)
            json.dumps(ins)
            schema = json.loads(
                (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
                 / "insights.schema.json").read_text()
            )
            jsonschema.validate(ins, schema)

    def test_report_briefs_render(self):
        br = build_insights(_failing_report())["briefs"]
        h = _build_briefs(br)
        assert 'id="briefs"' in h
        assert "For a PM" in h and "For QA" in h and "For the engineer" in h

    def test_report_audit_note_only_when_dirty(self):
        assert _build_narrative_audit_note({"clean": True, "adjustments": []}) == ""
        assert _build_narrative_audit_note(None) == ""
        h = _build_narrative_audit_note(
            {"clean": False, "adjustments": ["cites 99% which does not match"]}
        )
        assert "overstates" in h and "99%" in h


class TestCliDigest:
    def test_digest_flag_prints_briefs(self, tmp_path, capsys):
        import argparse

        from agent_evaluator.cli.gate import cmd_gate

        res = tmp_path / "r.json"
        res.write_text(json.dumps(_failing_report()))
        ns = argparse.Namespace(
            result_file=str(res), tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, max_cost_per_task=None,
            fail_on_regression=None, baseline=None, baseline_version=None,
            save_baseline=False, junit_xml=None, golden_set=None,
            fail_on_golden_regression=False, explain=False, digest=True,
            min_gate_score=None, gate_weights=None, gate_thresholds=None,
            required_gates=None, fail_on_gate_warn=False, baseline_result=None,
            fail_on_case_regression=False, max_review_high=None, notify=None,
        )
        cmd_gate(ns)
        out = capsys.readouterr().out
        assert "Briefs" in out and "PM:" in out and "Engineer:" in out

    def test_no_digest_flag_no_briefs(self, tmp_path, capsys):
        import argparse

        from agent_evaluator.cli.gate import cmd_gate

        res = tmp_path / "r.json"
        res.write_text(json.dumps(_failing_report()))
        ns = argparse.Namespace(
            result_file=str(res), tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, max_cost_per_task=None,
            fail_on_regression=None, baseline=None, baseline_version=None,
            save_baseline=False, junit_xml=None, golden_set=None,
            fail_on_golden_regression=False, explain=False, digest=False,
            min_gate_score=None, gate_weights=None, gate_thresholds=None,
            required_gates=None, fail_on_gate_warn=False, baseline_result=None,
            fail_on_case_regression=False, max_review_high=None, notify=None,
        )
        cmd_gate(ns)
        assert "Engineer:" not in capsys.readouterr().out
