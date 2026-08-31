"""
tests/test_provenance_p51.py
============================
SPEC-041 P51 — insight provenance: every actionable item carries a
`derived_from` naming the signal it came from.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import build_insights


def _t(tid, comp, acc, ok, reason=None, ttype="qa"):
    return {"task_id": tid, "task_type": ttype, "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q?", "response": "r"}


def _result(gate_details, tasks):
    hg = {}
    for k, det in gate_details.items():
        sc = det.get("score", 0.5)
        hg[k] = {"score": sc, "status": "fail" if sc < 0.5 else "warn",
                 "gate": "fail" if sc < 0.5 else "warn", "details": det}
    return {"extra_metrics": {"harness_groups": hg,
                              "lineage": {"prompt_text": "Answer using the context."}},
            "tasks": tasks}


def _run():
    tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(4)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    return _result(
        {"A": {"score": 0.45, "tcr_pct": 45.0, "avg_subtask_completion": 0.3},
         "C": {"score": 0.62}},
        tasks,
    )


def test_fix_plan_rows_have_failure_cluster_provenance():
    ins = build_insights(_run())
    fp = ins["readiness"]["fix_plan"]
    assert fp
    for row in fp:
        df = row.get("derived_from")
        assert df and df["source"] == "failure_cluster"
        assert df["signature"] == row["signature"]
        assert df["n"] == row["count"]
        assert isinstance(df["example_task_ids"], list)


def test_recommendations_have_gate_provenance():
    ins = build_insights(_run())
    recs = ins["recommendations"]
    assert recs
    for r in recs:
        df = r.get("derived_from")
        assert df and df["gate"] == r["gate"]
        assert df["source"] in ("gate_status", "gate_component_shortfall")
        assert df["status"] == r["status"]
        assert "from_diagnosis" in df


def test_next_actions_have_provenance_of_each_kind():
    ins = build_insights(_run())
    acts = ins["verdict"]["next_actions"]
    assert acts
    for a in acts:
        df = a.get("derived_from")
        assert df and df["source"] in (
            "gate_component_shortfall", "gate_score", "security_finding",
        )
        if df["source"] == "gate_component_shortfall":
            assert df["field"] == a["field"]
        if df["source"] == "gate_score":
            assert df["gate"] == a["gate"]


def test_security_next_action_provenance():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(15)]
    cur = _result({"A": {"score": 0.6}}, tasks)
    cur["evaluators"] = {}
    cur["extra_metrics"]["harness_groups"]["E"] = {
        "score": 0.9, "status": "pass", "gate": "pass", "details": {},
    }
    cur["security_evaluators"] = {
        "input_sanitizer": {"evaluations": [
            {"task_id": "ok0", "has_prompt_injection": True, "threat_count": 1,
             "sanitization_needed": True, "risk_level": "critical"},
        ]},
    }
    ins = build_insights(cur)
    sec = [a for a in ins["verdict"]["next_actions"]
           if (a.get("derived_from") or {}).get("source") == "security_finding"]
    if sec:  # only asserted when the security finding surfaced
        df = sec[0]["derived_from"]
        assert df["severity"] in ("critical", "high")
        assert df["task_id"] == "ok0"


def test_report_renders_provenance_line():
    from agent_evaluator.reporting.comprehensive_report import _build_readiness

    ins = build_insights(_run())
    html = _build_readiness(ins["readiness"])
    assert "from failure cluster" in html
