"""
tests/test_insights_schema.py
=================================
SPEC-041 P20 — `extra_metrics.insights` is a documented contract.
``agent_evaluator/schemas/insights.schema.json`` is the source of truth; every
``build_insights()`` output must validate against it so CI / automation
consumers can rely on the shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from agent_evaluator.reporting.insights import INSIGHTS_SCHEMA_VERSION, build_insights

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent_evaluator" / "schemas" / "insights.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _task(tid, *, ok, ttype="qa", judge=None, extra=None):
    d = {
        "task_id": tid, "task_type": ttype, "success": ok,
        "question": f"q {tid}", "response": "r", "ground_truth": "gt",
        "accuracy_score": 0.9 if ok else 0.2,
        "completion_score": 1.0 if ok else 0.1,
        "tokens_used": {"input": 100, "output": 50, "total": 150},
    }
    if judge is not None:
        d["llm_judge"] = {"skipped": False, "scores": {"overall": judge}}
    if extra is not None:
        d["extra"] = extra
    return d


def _report(hg, tasks, *, pricing=True, lineage=None, security=None):
    r = {"extra_metrics": {"harness_groups": hg}, "tasks": tasks}
    if pricing:
        r["pricing"] = {"input": 0.003, "output": 0.015}
    if lineage:
        r["extra_metrics"]["lineage"] = lineage
    if security:
        r["evaluators"] = {"security": security}
    return r


class TestSchemaItself:
    def test_schema_is_valid_draft_2020_12(self, schema):
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_schema_version_matches_module_constant(self, schema):
        # the file is v1.x; the module constant should stay in the same major
        assert INSIGHTS_SCHEMA_VERSION.split(".")[0] == "1"


class TestBuildInsightsValidates:
    def _check(self, schema, ins):
        jsonschema.validate(ins, schema)
        json.dumps(ins)  # still serializable

    def test_empty_report(self, schema):
        self._check(schema, build_insights({}))

    def test_healthy_pass_report(self, schema):
        rpt = _report(
            {"A": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(25)],
        )
        self._check(schema, build_insights(rpt))

    def test_failing_report_with_all_signals(self, schema):
        tasks = (
            [_task(f"d{i}", ok=False, judge=9.0) for i in range(3)]
            + [_task(f"b{i}", ok=True, judge=7.0) for i in range(2)]
            + [_task("flaky", ok=True, judge=8.0,
                     extra={"reproducibility": {"score": 0.4, "variance": 0.05,
                                                "run_count": 3,
                                                "sample_responses": ["A", "B", "C"]}})]
            + [_task(f"ok{i}", ok=True, judge=8.5) for i in range(12)]
        )
        for t in tasks[:3]:
            t["accuracy_score"] = 0.2
        rpt = _report(
            {"A": {"score": 0.45, "status": "fail", "gate": "fail",
                   "details": {"tcr_pct": 45.0, "avg_subtask_completion": 0.3}}},
            tasks,
            lineage={"prompt_text": "You are helpful.", "prompt_hash": "abc123",
                     "config_snapshot": {"temperature": 0.7}},
            security={"input_sanitizer": {"evaluations": [
                {"task_id": "d0", "has_prompt_injection": True, "threat_count": 1,
                 "sanitization_needed": True, "risk_level": "high"},
            ]}},
        )
        ins = build_insights(rpt)
        self._check(schema, ins)
        # sanity: the rich signals are actually populated in this scenario
        assert ins["evaluator_trust"] is not None
        assert ins["review_queue"] is not None
        assert ins["security_findings"]
        assert ins["nondeterminism"]
        assert ins["narrative"]

    def test_regression_mode_with_baseline(self, schema):
        base = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(20)],
            lineage={"prompt_text": "v1 prompt\nline two", "prompt_hash": "h1"},
        )
        cur = _report(
            {"A": {"score": 0.5, "status": "fail", "gate": "fail",
                   "details": {"tcr_pct": 50.0}}},
            [_task(f"t{i}", ok=i > 9) for i in range(20)],
            lineage={"prompt_text": "v2 prompt\nline two changed", "prompt_hash": "h2"},
        )
        ins = build_insights(cur, base)
        self._check(schema, ins)
        assert ins["detection_mode"] == "regression_vs_baseline"
        assert ins["change_attribution"] is not None

    def test_multiplicity_audit_section(self, schema):
        # P59 — needs per-slice p-values, which need a baseline
        cur = _report(
            {"A": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"q{i}", ok=i < 10) for i in range(15)]
            + [_task(f"r{i}", ok=True) for i in range(12)],
        )
        for t in cur["tasks"][15:]:
            t["task_type"] = "rag"
        base = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"q{i}", ok=True) for i in range(15)]
            + [_task(f"r{i}", ok=True) for i in range(12)],
        )
        for t in base["tasks"][15:]:
            t["task_type"] = "rag"
        ins = build_insights(cur, base)
        self._check(schema, ins)
        if ins.get("multiplicity_audit"):
            assert "_refs" not in ins["multiplicity_audit"]

    def test_partial_mode_running_verdict(self, schema):
        # P50 — mid-run subset: still schema-valid, carries running_verdict
        cur = _report(
            {"A": {"score": 0.45, "status": "fail", "gate": "fail",
                   "details": {"tcr_pct": 30.0}}},
            [_task(f"f{i}", ok=False) for i in range(28)]
            + [_task(f"p{i}", ok=True) for i in range(4)],
        )
        ins = build_insights(cur, partial=True)
        self._check(schema, ins)
        assert ins["detection_mode"] == "partial" and ins["partial"] is True
        rv = ins["running_verdict"]
        assert rv["decisive"] is True and rv["verdict"] == "not_ready"
        # expensive / baseline sections are absent in partial mode
        assert "cohort_comparison" not in ins and "longitudinal" not in ins

    def test_improvement_priors_section(self, schema, tmp_path):
        # P57 — cross-run learning from the experiment + outcome logs
        import json as _j
        (tmp_path / "experiments.jsonl").write_text("\n".join(_j.dumps(e) for e in [
            {"experiment_id": "e1", "status": "resolved", "target_gate": "A",
             "note": "[improve] Gate A prompt_edit: g", "verdict": "confirmed",
             "actual_delta": 0.08},
            {"experiment_id": "e2", "status": "resolved", "target_gate": "A",
             "note": "prompt rewrite", "verdict": "confirmed", "actual_delta": 0.05},
        ]))
        rpt = _report(
            {"A": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"t{i}", ok=i > 5) for i in range(15)],
        )
        ins = build_insights(
            rpt, experiments_log_path=str(tmp_path / "experiments.jsonl"),
        )
        self._check(schema, ins)
        assert ins["improvement_priors"] is not None

    def test_failure_taxonomy_section(self, schema):
        # P55 — single-agent failure taxonomy
        tasks = (
            [_task(f"ok{i}", ok=True) for i in range(10)]
            + [_task(f"to{i}", ok=False) for i in range(3)]
            + [_task(f"m{i}", ok=False) for i in range(3)]
        )
        for t in tasks[10:13]:
            t["partial_reason"] = "error: TimeoutError"
            t["accuracy_score"] = 0.1
        for t in tasks[13:]:
            t["partial_reason"] = "only part of a multi-step answer completed"
            t["accuracy_score"] = 0.3
        rpt = _report(
            {"A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {}}},
            tasks,
        )
        ins = build_insights(rpt)
        self._check(schema, ins)
        ft = ins["failure_taxonomy"]
        assert ft is not None and ft["by_mode"]
        assert ft["dominant_mode"]["code"] in {m["code"] for m in ft["by_mode"]}

    def test_reference_frame_section(self, schema):
        # P53 — external reference distribution
        rpt = _report(
            {"A": {"score": 0.72, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"t{i}", ok=i % 4 != 0) for i in range(20)],
        )
        ref = {"label": "support-rag",
               "tcr_pct": {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91},
               "gate_scores": {"A": [0.71, 0.74, 0.77, 0.80, 0.83]}}
        ins = build_insights(rpt, reference=ref)
        self._check(schema, ins)
        assert ins["reference_frame"] is not None
        assert ins["reference_frame"]["metrics"]

    def test_judge_robustness_section(self, schema):
        # P52 — multi-judge runs in extra_metrics.judge_runs
        rpt = _report(
            {"A": {"score": 0.7, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"t{i}", ok=True, judge=8.0) for i in range(10)],
        )
        rpt["extra_metrics"]["judge_runs"] = [
            {"model": "haiku", "cost_usd": 0.1,
             "scores": {f"t{i}": {"overall": 5.0 if i < 4 else 8.0} for i in range(10)}},
            {"model": "sonnet", "cost_usd": 0.9,
             "scores": {f"t{i}": {"overall": 7.0 if i < 4 else 8.0} for i in range(10)}},
        ]
        rpt["efficiency_metrics"] = {"tokens": {"total_cost": 2.0}}
        ins = build_insights(rpt)
        self._check(schema, ins)
        assert ins["judge_robustness"] is not None
        assert ins["judge_robustness"]["n_runs"] == 2
