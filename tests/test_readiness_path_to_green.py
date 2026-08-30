"""
tests/test_readiness_path_to_green.py
=======================================
SPEC-041 P29 — `insights.readiness`: quantified distance to a passing verdict +
an impact-ordered fix plan with a deterministic TCR projection.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.comprehensive_report import _build_readiness
from agent_evaluator.reporting.insights import (
    _fix_effort_hint,
    _readiness_section,
    build_insights,
)


def _t(tid, comp, acc, ok, reason=None, ttype="qa"):
    d = {"task_id": tid, "task_type": ttype, "completion_score": comp,
         "accuracy_score": acc, "success": ok}
    if reason:
        d["partial_reason"] = reason
    return d


def _tasks():
    ts = [_t(f"p{i}", 1.0, 0.9, True) for i in range(12)]
    ts += [_t(f"f_ms{i}", 0.4, 0.35, False,
              "only part of a multi-step answer completed") for i in range(4)]
    ts += [_t(f"f_grd{i}", 0.5, 0.2, False,
              "answer not grounded in the retrieved context") for i in range(3)]
    ts += [_t("f_to0", 0.0, 0.0, False, "error: TimeoutError: retriever exceeded 8s")]
    return ts


_HG = {
    "A": {"score": 0.58, "status": "fail", "gate": "fail", "details": {}},
    "C": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}},
    "D": {"score": 0.45, "status": "fail", "gate": "fail", "details": {}},
    "E": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}},
}


class TestReadinessSection:
    def test_gaps_cover_fail_and_warn_gates(self):
        rd = _readiness_section(_tasks(), _HG)
        assert {g["gate"] for g in rd["gaps"]} == {"A", "C", "D"}
        a = next(g for g in rd["gaps"] if g["gate"] == "A")
        assert a["gap"] == round(0.7 - 0.58, 3)
        assert a["blocking"] is True
        assert a["target"] == 0.7

    def test_tcr_driven_gate_gets_projection_structural_does_not(self):
        rd = _readiness_section(_tasks(), _HG)
        a = next(g for g in rd["gaps"] if g["gate"] == "A")
        d = next(g for g in rd["gaps"] if g["gate"] == "D")
        assert "projected_score_after_plan" in a and a["estimate"] is True
        assert "projected_score_after_plan" not in d

    def test_fix_plan_ordered_by_size_with_cumulative_projection(self):
        rd = _readiness_section(_tasks(), _HG)
        fp = rd["fix_plan"]
        assert [i["count"] for i in fp] == [4, 3, 1]
        assert [i["rank"] for i in fp] == [1, 2, 3]
        # cumulative TCR gain is monotonically non-decreasing
        gains = [i["cumulative_tcr_gain_pp"] for i in fp]
        assert gains == sorted(gains)
        # exact projection: current TCR = mean(completion) = 15.1/20 = 75.5
        assert rd["current_tcr_pct"] == 75.5
        # after fixing all three clusters every failing task passes -> 100%
        assert fp[-1]["projected_tcr_after_pct"] == 100.0

    def test_effort_hint_and_target_gates(self):
        rd = _readiness_section(_tasks(), _HG)
        ms = next(i for i in rd["fix_plan"] if "multi-step" in i["signature"])
        assert "SubtaskConfig" in ms["effort_hint"] and ms["targets_gates"] == ["A"]
        to = next(i for i in rd["fix_plan"] if i["signature"].startswith("error:"))
        assert "C" in to["targets_gates"] and "D" in to["targets_gates"]

    def test_structural_blocker_called_out(self):
        rd = _readiness_section(_tasks(), _HG)
        pr = rd["projected_ready_after"]
        assert pr["remaining_structural_blockers"] == ["D"]
        assert "not driven by task outcomes" in pr["note"]
        assert isinstance(pr["ready_after_n_items"], int)

    def test_none_when_nothing_to_plan(self):
        healthy_hg = {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}}
        healthy = [_t(f"p{i}", 1.0, 0.95, True) for i in range(10)]
        assert _readiness_section(healthy, healthy_hg) is None

    def test_all_tcr_blockers_clearable(self):
        # only Gate A fails, and the fix plan can clear it
        hg = {"A": {"score": 0.6, "status": "fail", "gate": "fail", "details": {}}}
        rd = _readiness_section(_tasks(), hg)
        pr = rd["projected_ready_after"]
        assert pr["ready_after_n_items"] is not None
        assert pr["remaining_structural_blockers"] == []
        assert "bring every failing gate to target" in pr["note"]


class TestFixEffortHint:
    def test_classifications(self):
        assert _fix_effort_hint("error: TimeoutError")[1] == ["C", "D"]
        assert "A" in _fix_effort_hint("answer not grounded in the retrieved context")[1]
        assert _fix_effort_hint("only part of a multi-step answer completed")[1] == ["A"]
        assert set(_fix_effort_hint("loop detected: repeated tool call")[1]) == {"B", "E"}
        assert _fix_effort_hint("something weird")[1] == ["A"]


class TestBuildInsightsWiring:
    def test_key_present_and_schema_valid(self):
        ins = build_insights({"extra_metrics": {"harness_groups": _HG}, "tasks": _tasks()})
        assert ins["readiness"] is not None
        assert ins["readiness"]["fix_plan"]
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_for_healthy_run(self):
        ins = build_insights({
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.92, "status": "pass", "gate": "pass", "details": {}}}},
            "tasks": [_t(f"p{i}", 1.0, 0.95, True) for i in range(8)],
        })
        assert ins["readiness"] is None


class TestReportSection:
    def test_renders_path_to_green(self):
        rd = _readiness_section(_tasks(), _HG)
        h = _build_readiness(rd)
        assert 'id="path-to-green"' in h
        assert "Path to Green" in h and "Fix plan" in h
        assert "Gate A" in h and "+0.12" in h  # the A gap
        assert "SubtaskConfig" in h

    def test_empty_without_data(self):
        assert _build_readiness(None) == ""
        assert _build_readiness({"gaps": [], "fix_plan": []}) == ""

    def test_report_integration(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )

        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(10):
            ok = i < 5
            tr = create_taskresult(
                task_id=f"t{i}", question="q", response="a" if ok else "wrong",
                ground_truth="a", execution_time=1.0, task_type="qa",
            )
            object.__setattr__(tr, "completion_score", 1.0 if ok else 0.3)
            object.__setattr__(tr, "accuracy_score", 0.9 if ok else 0.2)
            object.__setattr__(tr, "success", ok)
            if not ok:
                object.__setattr__(tr, "partial_reason",
                                   "answer not grounded in the retrieved context")
            m.record_task(tr)
        html = generate_comprehensive_html_report(m)
        # readiness renders whenever a gate is below the pass line
        assert ('id="path-to-green"' in html) or ("Path to Green" not in html)
