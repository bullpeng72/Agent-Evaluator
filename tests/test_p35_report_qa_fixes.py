"""
tests/test_p35_report_qa_fixes.py
====================================
SPEC-041 P35 — fixes from auditing the round-5 example report.

B1  _review_dict_tasks carries partial_reason/errors → real failure signatures
B3  goal-drift no longer fires on a healthy short Q&A session
B4  trace-diff compares against the nearest prior cohort version
B5  trace-diff response summary reads "X% similar" not "0% unchanged"
B6  Path-to-Green note is correct when only warning gates are below target
B7  exec-summary next-action score is rounded; field name is prettified
I1  fix-plan / engineer brief show task_type / merge same-signature rows
I2  RCA diagnosis splits newly-measured metrics out of the regression table
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.comprehensive_report import (
    _build_readiness,
    _build_trace_diffs,
    _pretty_field,
    _review_dict_tasks,
    _td_resp_summary,
)
from agent_evaluator.reporting.insights import (
    _briefs_section,
    _conversation_section,
    _readiness_section,
    _trace_diffs_section,
    build_insights,
)


# ---- B1 -------------------------------------------------------------------

def test_b1_review_dict_tasks_carries_reason():
    tr = create_taskresult(task_id="t1", question="q", response="wrong",
                           ground_truth="right", execution_time=1.0, task_type="qa")
    object.__setattr__(tr, "completion_score", 0.3)
    object.__setattr__(tr, "accuracy_score", 0.2)
    object.__setattr__(tr, "success", False)
    object.__setattr__(tr, "partial_reason", "answer not grounded in the retrieved context")
    dt = _review_dict_tasks([tr])[0]
    assert dt["partial_reason"] == "answer not grounded in the retrieved context"
    assert dt["errors"] == []


def test_b1_readiness_fix_plan_gets_real_signatures():
    m = PerformanceMonitor(output_dir="/tmp")
    reasons = (["only part of a multi-step answer completed"] * 4
               + ["answer not grounded in the retrieved context"] * 3
               + ["error: TimeoutError"])
    for i in range(12):
        tr = create_taskresult(task_id=f"ok{i}", question="q", response="a",
                               ground_truth="a", execution_time=1.0, task_type="qa")
        object.__setattr__(tr, "completion_score", 1.0)
        object.__setattr__(tr, "accuracy_score", 0.9)
        object.__setattr__(tr, "success", True)
        m.record_task(tr)
    for i, rsn in enumerate(reasons):
        tr = create_taskresult(task_id=f"f{i}", question="q", response="x",
                               ground_truth="y", execution_time=1.0, task_type="qa")
        object.__setattr__(tr, "completion_score", 0.3)
        object.__setattr__(tr, "accuracy_score", 0.2)
        object.__setattr__(tr, "success", False)
        object.__setattr__(tr, "partial_reason", rsn)
        m.record_task(tr)
    data = m.generate_report().to_dict()
    data["tasks"] = _review_dict_tasks(list(m.tcr_tracker.tasks))
    data.setdefault("extra_metrics", {})["harness_groups"] = {
        "A": {"score": 0.55, "status": "fail", "gate": "fail", "details": {}}}
    ins = build_insights(data)
    sigs = {row["signature"] for row in ins["readiness"]["fix_plan"]}
    assert any("multi-step" in s for s in sigs)
    assert any("grounded" in s for s in sigs)
    assert "incomplete · low accuracy" not in sigs


# ---- B3 -------------------------------------------------------------------

def _sess(sid, turns, topic=0.8):
    return {
        "session_id": sid, "turn_count": len(turns),
        "turns": [{"turn_index": i, "user": u, "agent": a, "timestamp": "t", "metadata": {}}
                  for i, (u, a) in enumerate(turns)],
        "metrics": {"overall_score": 0.7, "context_retention": 0.7,
                    "topic_coherence": topic, "progressive_depth": 0.7,
                    "session_completion": 0.8},
    }


def test_b3_goal_drift_signal_removed():
    # P35: the lexical goal-drift heuristic false-positived on a healthy 4-turn
    # returns conversation (topic_coherence came back 0.098 — no threshold could
    # separate it) and was removed entirely.
    healthy = _sess("clean", [
        ("How do I return an item?", "Unopened items within 14 days get a full refund."),
        ("What about opened items?", "Opened items within 14 days get store credit only."),
        ("Do I pay the return shipping?", "No — we email you a prepaid label."),
        ("How long until I see the money?", "Refunds post within 3 business days."),
    ], topic=0.1)
    cv = _conversation_section({"conversation_sessions": [healthy]})
    assert "goal_drift_sessions" not in cv
    # degradation_after_turn still covers "the session went bad"
    assert "degradation_after_turn" in cv


# ---- B4 -------------------------------------------------------------------

def test_b4_trace_diff_uses_nearest_prior():
    def run(lbl, acc):
        return {"extra_metrics": {"harness_groups": {}, "lineage": {"agent_version": lbl}},
                "tasks": [{"task_id": "t1", "task_type": "qa", "question": "q",
                           "response": f"resp {lbl}", "completion_score": 1.0 if acc > 0.5 else 0.3,
                           "accuracy_score": acc, "success": acc > 0.5}]}
    td = _trace_diffs_section(run("v3", 0.2), [run("v1", 0.9), run("v2", 0.85)])
    assert td[0]["compared"] == ["v2", "v3"]


# ---- B5 -------------------------------------------------------------------

def test_b5_response_summary_wording():
    assert _td_resp_summary({"similarity": 0.0}) == "Response fully rewritten"
    assert _td_resp_summary({"similarity": 1.0}) == "Response essentially unchanged"
    assert "40% similar" in _td_resp_summary({"similarity": 0.4})


# ---- B6 -------------------------------------------------------------------

def test_b6_warn_only_note_has_no_failing_wording():
    tasks = ([{"task_id": f"p{i}", "task_type": "qa", "completion_score": 1.0,
               "accuracy_score": 0.9, "success": True} for i in range(10)]
             + [{"task_id": f"f{i}", "task_type": "qa", "completion_score": 0.3,
                 "accuracy_score": 0.2, "success": False,
                 "partial_reason": "only part of a multi-step answer completed"}
                for i in range(6)])
    hg = {"A": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}},
          "C": {"score": 0.63, "status": "warn", "gate": "warn", "details": {}},
          "D": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}}}
    rd = _readiness_section(tasks, hg)
    note = rd["projected_ready_after"]["note"]
    assert "failing gate" not in note
    assert "D (Performance Contract)" in note  # structural blocker called out
    assert rd["projected_ready_after"]["remaining_structural_blockers"] == ["D"]
    h = _build_readiness(rd)
    assert "does not clear every failing gate" not in h


# ---- B7 -------------------------------------------------------------------

def test_b7_pretty_field():
    assert _pretty_field("tcr_pct") == "TCR"
    assert _pretty_field("avg_quality_relevance_completeness") == "response relevance/completeness"
    assert _pretty_field("p95_latency_s") == "P95 latency"
    assert _pretty_field("some_unknown_thing") == "some unknown thing"


def test_b7_verdict_fallback_action_rounds_score():
    from agent_evaluator.reporting.insights import _verdict_section
    hg = {"D": {"score": 0.63723, "status": "warn", "gate": "warn", "details": {}}}
    v = _verdict_section(hg, None, {"n_tasks": 20}, 20)
    acts = [a["action"] for a in v["next_actions"] if a["gate"] == "D"]
    assert acts and "0.6372" not in acts[0] and "0.64" in acts[0]


# ---- I1 ----------------------------------------------------------------

def test_i1_engineer_brief_merges_same_signature():
    ins = {
        "verdict": {"level": "not_ready", "failing_gates": ["A"], "confidence": "medium"},
        "readiness": {"fix_plan": [
            {"rank": 1, "signature": "only part of a multi-step answer completed",
             "task_type": "qa", "count": 3, "effort_hint": "add SubtaskConfig",
             "projected_tcr_after_pct": 80.0},
            {"rank": 2, "signature": "only part of a multi-step answer completed",
             "task_type": "information_retrieval", "count": 2, "effort_hint": "add SubtaskConfig",
             "projected_tcr_after_pct": 90.0},
        ], "projected_ready_after": {}},
        "review_queue": {}, "evaluator_trust": {}, "failure_segments": [],
        "recommendations": [], "security_findings": [], "freshness": {},
    }
    br = _briefs_section(ins)
    eng = [e for e in br["engineer"] if "multi-step" in e]
    assert len(eng) == 1
    assert "5 task(s)" in eng[0]  # 3 + 2 merged
    assert "qa" in eng[0] and "information_retrieval" in eng[0]


def test_i1_fix_plan_row_shows_task_type():
    rd = {
        "target_gate_score": 0.7, "current_tcr_pct": 70.0,
        "gaps": [{"gate": "A", "gate_name": "Goal Achievement", "score": 0.6,
                  "target": 0.7, "gap": 0.1, "blocking": True}],
        "fix_plan": [{"rank": 1, "signature": "error: TimeoutError", "task_type": "tool_use",
                      "count": 2, "impact_pct": 8.0, "effort_hint": "retry config",
                      "targets_gates": ["C", "D"], "projected_tcr_after_pct": 85.0,
                      "cumulative_tcr_gain_pp": 15.0}],
        "projected_ready_after": {"note": "x"},
    }
    h = _build_readiness(rd)
    assert "tool_use" in h


# ---- I2 ----------------------------------------------------------------

def test_i2_diagnosis_splits_newly_measured():
    from agent_evaluator.reporting.comprehensive_report import _build_diagnosis

    def _run(c_score, c_details):
        return {"extra_metrics": {"harness_groups": {
            "C": {"score": c_score, "status": "warn" if c_score < 0.7 else "pass",
                  "gate": "warn" if c_score < 0.7 else "pass", "details": c_details}}},
            "tasks": []}

    cur = _run(0.63, {"tcr_pct": 71.04, "avg_llm_faithfulness": 3.74,
                      "avg_reproducibility": 0.41})
    base = _run(0.84, {"tcr_pct": 83.75})   # faithfulness/repro not measured then
    html = _build_diagnosis(cur, base)
    assert "Newly measured this run" in html
    assert "avg_llm_faithfulness" in html or "avg_reproducibility" in html
    # the newly-measured metric is not rendered as a "n/a | n/a" delta row
    assert "n/a</td><td>3.74" not in html.replace(" ", "")
