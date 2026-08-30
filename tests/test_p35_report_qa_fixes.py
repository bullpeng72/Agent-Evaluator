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
    _build_conclusion,
    _build_readiness,
    _build_score_breakdown,
    _build_trace_diffs,
    _pretty_field,
    _review_dict_tasks,
    _td_resp_summary,
    _trim_field_restatement,
)
from agent_evaluator.reporting.insights import (
    _briefs_section,
    _conversation_section,
    _failure_segments_section,
    _insight_changes_section,
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

def test_i1_readiness_merges_signature_across_task_types():
    # P35b: _readiness_section produces ONE fix-plan row per signature; the
    # engineer brief just formats it (no second merge).
    tasks = ([{"task_id": f"p{i}", "task_type": "qa", "completion_score": 1.0,
               "accuracy_score": 0.9, "success": True} for i in range(10)]
             + [{"task_id": f"to_qa{i}", "task_type": "qa", "completion_score": 0.0,
                 "accuracy_score": 0.0, "success": False,
                 "partial_reason": "error: TimeoutError"} for i in range(2)]
             + [{"task_id": f"to_ir{i}", "task_type": "information_retrieval",
                 "completion_score": 0.0, "accuracy_score": 0.0, "success": False,
                 "partial_reason": "error: TimeoutError"} for i in range(2)])
    rd = _readiness_section(tasks, {"A": {"score": 0.55, "status": "fail",
                                          "gate": "fail", "details": {}}})
    to_rows = [r for r in rd["fix_plan"] if r["signature"] == "error: TimeoutError"]
    assert len(to_rows) == 1
    assert to_rows[0]["count"] == 4
    assert set(to_rows[0]["task_types"]) == {"qa", "information_retrieval"}

    br = _briefs_section({
        "verdict": {"level": "not_ready", "failing_gates": ["A"], "confidence": "medium"},
        "readiness": rd, "review_queue": {}, "evaluator_trust": {},
        "failure_segments": [], "recommendations": [], "security_findings": [],
        "freshness": {},
    })
    eng = [e for e in br["engineer"] if "TimeoutError" in e]
    assert len(eng) == 1
    assert "4 task(s)" in eng[0]
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


# ---- P35b: analysis round 2 -------------------------------------------------

def _t(tid, comp, acc, ok, reason=None, ttype="qa"):
    d = {"task_id": tid, "task_type": ttype, "completion_score": comp,
         "accuracy_score": acc, "success": ok, "question": f"q {tid}"}
    if reason:
        d["partial_reason"] = reason
    return d


def test_b2b_insight_changes_uses_full_signature_sets():
    # a cluster that merely drops in rank (still occurring) is NOT "resolved".
    def _r(score, tasks):
        return {"extra_metrics": {"harness_groups": {
            "A": {"score": score, "status": "fail" if score < 0.7 else "pass",
                  "gate": "fail" if score < 0.7 else "pass", "details": {}}}},
            "tasks": tasks}

    base = _r(0.8,
              [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
              + [_t("ms", 0.3, 0.3, False, "only part of a multi-step answer completed")]
              + [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(6)])
    cur = _r(0.55,
             [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
             + [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(6)]
             + [_t("grd", 0.5, 0.2, False, "answer not grounded in the retrieved context")])
    ic = _insight_changes_section(cur, base, None, None,
                                  cur["extra_metrics"]["harness_groups"])
    assert "only part of a multi-step answer completed" in ic["resolved_clusters"]
    assert "answer not grounded in the retrieved context" in ic["new_clusters"]
    assert "error: TimeoutError" not in ic["resolved_clusters"]


def test_b3_readiness_note_shows_projected_scores():
    tasks = ([_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
             + [_t(f"f{i}", 0.3, 0.2, False,
                   "answer not grounded in the retrieved context") for i in range(6)])
    hg = {"A": {"score": 0.58, "status": "fail", "gate": "fail", "details": {}},
          "D": {"score": 0.62, "status": "warn", "gate": "warn", "details": {}}}
    rd = _readiness_section(tasks, hg)
    pr = rd["projected_ready_after"]
    assert "projected_gate_scores" in pr and "A" in pr["projected_gate_scores"]
    assert "plan_fixes_projected" in pr
    assert f"Gate A ~{pr['projected_gate_scores']['A']:.2f}" in pr["note"]
    # the gap row's projected score reflects the recommended fix count, not all
    a_gap = next(g for g in rd["gaps"] if g["gate"] == "A")
    assert a_gap.get("after_plan_fixes") == pr["plan_fixes_projected"]


def test_conversation_per_session_and_best():
    from agent_evaluator.reporting.insights import _conversation_section

    def _s(sid, ov):
        return {"session_id": sid, "turn_count": 2,
                "turns": [{"turn_index": 0, "user": "hi", "agent": "hello there friend",
                           "timestamp": "t", "metadata": {}},
                          {"turn_index": 1, "user": "ok", "agent": "you are welcome",
                           "timestamp": "t", "metadata": {}}],
                "metrics": {"overall_score": ov, "context_retention": ov,
                            "topic_coherence": ov, "progressive_depth": ov,
                            "session_completion": ov}}

    cv = _conversation_section({"conversation_sessions": [_s("lo", 0.2), _s("hi", 0.9)]})
    assert [s["session_id"] for s in cv["sessions"]] == ["lo", "hi"]  # worst first
    assert cv["best_session"]["session_id"] == "hi"
    assert cv["worst_session"]["session_id"] == "lo"


def test_trace_diff_substitution_wording():
    td = [{
        "task_id": "t1", "question": "size?", "compared": ["v2", "v3"],
        "verdict": "regressed",
        "score_delta": {"completion": -0.5, "accuracy": -0.4},
        "response_diff": {"similarity": 0.4, "added": ["7 more"], "removed": ["7.8 mm and 172 g."]},
        "trajectory_diff": {"before": [], "after": [], "added": [], "removed": [],
                            "reordered": False},
        "per_version": [{"label": "v3", "completion": 0.4, "accuracy": 0.3,
                         "success": False, "response_excerpt": "x"}],
    }]
    h = _build_trace_diffs(td)
    assert "changed:" in h and "7.8 mm and 172 g. → 7 more" in h


# ---- P35 round 3: analysis round 3 ---------------------------------------

def test_r3_score_breakdown_weighted_gate_shows_honest_expression():
    """Gates A/C weight the TCR component — the breakdown must not print
    ( a + b + c ) ÷ N = score when that arithmetic does not equal score."""
    hg_c = {
        "score": 0.6309, "status": "warn",
        "details": {"tcr_pct": 71.04, "gate_c_tcr_weight": 0.4,
                    "avg_reproducibility": 0.408, "avg_llm_faithfulness": 3.74},
    }
    html = _build_score_breakdown("C", hg_c)
    # the naive mean (62.2%) is shown as an approximation, not "= 63.1%"
    assert "&asymp;" in html or "≈" in html
    assert "62.2%" in html                       # the component mean
    assert "63.1%" in html                       # the actual weighted score
    assert "weights the TCR component at 40%" in html


def test_r3_score_breakdown_unweighted_gate_still_reconciles():
    hg_g = {
        "score": 0.7529, "status": "pass",
        "details": {"tool_coverage": 0.7647, "avg_explainability": 0.6819,
                    "avg_latency_attribution": 0.812},
    }
    html = _build_score_breakdown("G", hg_g).replace("&nbsp;", " ")
    assert "( 0.765 + 0.682 + 0.812 ) ÷ 3 =" in html
    assert "75.3%" in html
    assert "≈" not in html and "&asymp;" not in html
    assert "indicative only" not in html


def test_r3_gate_e_excludes_threat_free_rate_from_average():
    """Gate E aggregate drops threat_free_rate when per-tracker scores exist —
    the breakdown's ÷N must match (5 defense rates, not 6)."""
    hg_e = {
        "score": 0.975, "status": "pass",
        "details": {
            "threat_count": 2, "threat_free_rate": 0.9167,
            "privilege_escalation_rate": 0.0417, "chain_attack_rate": 0.0,
            "leakage_defense_rate": 1.0, "leakage_count": 0,
            "injection_defense_rate": 0.9583, "injection_count": 1,
            "tool_authorization_rate": 0.9583, "unauthorized_calls_count": 1,
        },
    }
    html = _build_score_breakdown("E", hg_e).replace("&nbsp;", " ")
    assert "( 0.958 + 1.000 + 1.000 + 0.958 + 0.958 ) ÷ 5 =" in html
    assert "97.5%" in html and "(5 component(s) measured)" in html
    assert "not averaged" in html      # threat-free row is informational


def test_r3_conclusion_hallucination_na_when_not_measured():
    hg = {"A": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}},
          "C": {"score": 0.63, "status": "warn", "gate": "warn",
                "details": {"avg_llm_faithfulness": 3.7}}}  # faith != hallucination rate
    html = _build_conclusion(24, 71.0, 58.5, 0.0, hg, {})
    assert "Hallucination Rate:</strong> n/a (not enabled)" in html
    # only A and C are scored -> "2/2 measured", note the two unmeasured gates
    assert "measured PASS" in html
    assert "gate(s) not measured" in html


def test_r3_insight_changes_newly_below_target_includes_warn():
    def _r(status):
        return {"extra_metrics": {"harness_groups": {
            "A": {"score": 0.62 if status == "warn" else 0.8, "status": status,
                  "gate": status, "details": {}}}}, "tasks": []}

    ic = _insight_changes_section(_r("warn"), _r("pass"), None, None,
                                  _r("warn")["extra_metrics"]["harness_groups"])
    assert ic and "A" in ic["newly_failing_gates"]   # warn counts as "below target"


def test_r3_failure_segments_catch_all_flagged():
    # every failing question is lexically unique -> only the catch-all bucket
    tasks = [
        {"task_id": f"f{i}", "task_type": "qa", "completion_score": 0.2,
         "accuracy_score": 0.2, "success": False,
         "question": q, "partial_reason": "error: TimeoutError"}
        for i, q in enumerate([
            "how do I reset my password",
            "where is the nearest branch office located",
            "what colours does the deluxe chair ship in",
            "can I change my delivery address after ordering",
        ])
    ]
    segs = _failure_segments_section(tasks)
    assert segs and all(s.get("catch_all") for s in segs)


def test_r3_trace_diff_errored_version_shows_no_response():
    td = [{
        "task_id": "t1", "question": "refund policy?", "compared": ["v2", "v3"],
        "verdict": "regressed", "score_delta": {"completion": -1.0, "accuracy": -0.9},
        "response_diff": {"similarity": 0.0, "added": [], "removed": ["old good answer here"],
                          "errored": True, "error_reason": "error: TimeoutError"},
        "trajectory_diff": {"before": [], "after": [], "added": [], "removed": [],
                            "reordered": False},
        "per_version": [{"label": "v3", "completion": 0.0, "accuracy": 0.0,
                         "success": False, "response_excerpt": ""}],
    }]
    h = _build_trace_diffs(td)
    assert "Current version returned no response" in h
    assert "removed:" not in h        # no misleading word-diff against an empty response


def test_r3_narrative_no_duplicate_field_name():
    out = _trim_field_restatement(
        "response relevance/completeness",
        "Response relevance/completeness is low. Strengthen the response-format "
        "instructions and provide examples.",
    )
    assert out.startswith("Strengthen the response-format")
    # a guidance string that does NOT restate the field is left untouched
    assert _trim_field_restatement("TCR", "Improve agent prompts. Analyze failures.") == (
        "Improve agent prompts. Analyze failures.")
