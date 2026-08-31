"""
tests/test_p35_round4_report_qa.py
==================================
SPEC-041 P35 round 4 — fourth example-report audit. Cross-section
contradictions and count bugs found by reading the generated report.
"""
from __future__ import annotations

from agent_evaluator.ontology.failure_taxonomy import classify_failure
from agent_evaluator.reporting.insights import (
    _claim_verdict,
    _uncertainty_budget_section,
    build_insights,
)


def _t(tid, comp, acc, ok, reason=None, ttype="qa", **kw):
    d = {"task_id": tid, "task_type": ttype, "completion_score": comp,
         "accuracy_score": acc, "success": ok, "partial_reason": reason,
         "question": kw.get("q", "q?"), "response": kw.get("resp", "r"),
         "ground_truth": kw.get("gt", "g")}
    for k in ("context", "tool_calls", "llm_judge", "extra"):
        if k in kw:
            d[k] = kw[k]
    return d


# ---- A1: one canonical "problem gate" list -------------------------------

def test_verdict_below_user_target_not_folded_into_headline_count():
    hg = {
        "A": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}},
        "E": {"score": 0.975, "status": "pass", "gate": "pass", "details": {}},
    }
    tasks = [_t(f"t{i}", 0.6, 0.6, i > 5) for i in range(20)]
    # E target 0.98 — a 0.005 shortfall, below the materiality floor
    ins = build_insights(
        {"extra_metrics": {"harness_groups": hg}, "tasks": tasks},
        targets={"gates": {"A": 0.80, "E": 0.98}},
    )
    v = ins["verdict"]
    # E's 0.005 gap is immaterial -> not in the count, not in the gap table
    assert "E" not in v["below_user_target_gates"]
    assert v["headline"].startswith("1 Gate(s) below your target: A")
    assert "E" not in (v["headline"])
    rd = ins["readiness"] or {}
    assert not any(g.get("gate") == "E" for g in (rd.get("gaps") or []))


def test_material_below_user_target_is_shown_as_parenthetical():
    hg = {
        "A": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}},
        "E": {"score": 0.88, "status": "pass", "gate": "pass", "details": {}},
    }
    tasks = [_t(f"t{i}", 0.6, 0.6, i > 5) for i in range(20)]
    ins = build_insights(
        {"extra_metrics": {"harness_groups": hg}, "tasks": tasks},
        targets={"gates": {"A": 0.80, "E": 0.98}},
    )
    v = ins["verdict"]
    assert v["below_user_target_gates"] == ["E"]     # 0.10 gap is material
    assert v["headline"].startswith("1 Gate(s) below your target: A")
    assert "plus 1 passing but below your target: E" in v["headline"]


# ---- A2: taxonomy classifier no longer over-fires RETRIEVAL_MISS -------

def test_timeout_is_runtime_error_not_retrieval_miss():
    c = classify_failure(
        {"partial_reason": "error: TimeoutError", "response": "",
         "context": ["some chunk that does not cover the answer"],
         "ground_truth": "the real answer", "tool_calls": [{"success": False}]},
        reason="error: timeouterror",
    )
    assert c["code"] == "RUNTIME_ERROR"


def test_contradicts_context_is_grounding_not_retrieval():
    c = classify_failure(
        {"partial_reason": "contradicts retrieved context (factual error)",
         "response": "Per the policy, four years on the body.",
         "ground_truth": "body 2y", "context": ["unrelated chunk"],
         "tool_calls": [{"success": False}]},
        reason="contradicts retrieved context (factual error)",
    )
    assert c["code"] in ("GROUNDING_MISS", "HALLUCINATED_FACT")


def test_multistep_reason_beats_a_failed_tool_step():
    c = classify_failure(
        {"partial_reason": "only part of a multi-step answer completed",
         "response": "step 1 done", "ground_truth": "all steps",
         "tool_calls": [{"success": False}]},
        reason="only part of a multi-step answer completed",
    )
    assert c["code"] == "PREMATURE_STOP"


def test_low_similarity_reason_not_retrieval_miss():
    c = classify_failure(
        {"partial_reason": "low ground_truth similarity", "response": "x",
         "ground_truth": "y", "context": ["z chunk"]},
        reason="low ground_truth similarity",
    )
    assert c["code"] in ("LOW_SIMILARITY", "LABEL_OR_SPEC_ISSUE")


def test_taxonomy_dominant_agrees_with_reason_clusters():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(6)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    tasks += [_t(f"g{i}", 0.3, 0.2, False,
                 "answer not grounded in the retrieved context",
                 resp="deflect", gt="real") for i in range(5)]
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": tasks})
    ft = ins["failure_taxonomy"]
    assert ft["dominant_mode"]["code"] in ("GROUNDING_MISS", "HALLUCINATED_FACT")
    # runtime bucket size matches the timeout cluster
    _rt = next(m for m in ft["by_mode"] if m["code"] == "RUNTIME_ERROR")
    assert _rt["n"] == 3


# ---- A3: efficiency doesn't suggest gating a hot failure step -----------

def test_efficiency_suppresses_gating_when_retrieval_is_a_top_failure():
    timed = [
        {"tool_name": "retrieve", "duration": 0.6, "success": True},
        {"tool_name": "synthesize", "duration": 1.2, "success": True},
    ]
    tasks = [_t(f"ok{i}", 1.0, 0.9, True, tool_calls=timed) for i in range(8)]
    tasks += [_t(f"g{i}", 0.2, 0.2, False,
                 "answer not grounded in the retrieved context",
                 tool_calls=timed) for i in range(6)]
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": tasks})
    eo = ins.get("efficiency_opportunities") or []
    assert not any(o.get("kind") == "step_gating"
                   and "retrieve" in o.get("title", "") for o in eo)


# ---- B: count bugs ----------------------------------------------------

def test_contamination_warning_counts_distinct_tasks():
    prompt = "How long does delivery take? It is 2-3 business days."
    tasks = [_t("t_dup", 1.0, 0.9, True, q="How long does delivery take",
                gt="2-3 business days")]
    tasks += [_t(f"ok{i}", 1.0, 0.9, True) for i in range(19)]
    ins = build_insights({
        "extra_metrics": {"harness_groups": {}, "lineage": {"prompt_text": prompt}},
        "tasks": tasks})
    esq = ins["eval_set_quality"]
    contam_warn = [w for w in esq["coverage_warnings"] if "overlap the system prompt" in w]
    assert contam_warn and contam_warn[0].startswith("1 task(s)")


def test_claim_verdict_spelled_numbers_contradict():
    assert _claim_verdict(
        "Per the retrieved policy, four years on the body, five year on the battery.",
        "body 2y, battery 1y",
    ) == "contradicts_ground_truth"


# ---- C: framing -----------------------------------------------------

def test_uncertainty_budget_says_no_dominant_driver_when_tied():
    out = {
        "verdict": {"confidence": "medium"},
        "metric_confidence": {"n_tasks": 24, "tcr_ci_halfwidth": 0.13, "tcr_pct": 70},
        "evaluator_trust": {"trust_level": "medium"},
        "freshness": {"baseline_age_days": 63},
        "threshold_sensitivity": {}, "readiness": {},
    }
    ub = _uncertainty_budget_section(out)
    assert ub is not None
    assert ub["dominant_source"] is None
    assert ub["tied_top"] == 3
    assert "No single dominant driver" in ub["note"]


def test_uncertainty_budget_borderline_ignores_passing_gate_under_stretch_target():
    # E passes SDK + is only 0.005 under a user target -> not a borderline driver
    out = {
        "verdict": {"confidence": "medium"},
        "metric_confidence": {"n_tasks": 200},
        "evaluator_trust": {}, "freshness": {},
        "threshold_sensitivity": {},
        "readiness": {"gaps": [{"gate": "A", "gap": 0.17}]},   # no <=0.05 gap
    }
    ub = _uncertainty_budget_section(out)
    assert ub is None or not any(c["source"] == "borderline" for c in ub["components"])


def test_review_queue_plain_regression_is_medium():
    base = {"extra_metrics": {"harness_groups": {}},
            "tasks": [_t("shared", 1.0, 0.9, True)]
            + [_t(f"t{i}", 1.0, 0.9, True) for i in range(20)]}
    cur = {"extra_metrics": {"harness_groups": {}},
           "tasks": [_t("shared", 0.2, 0.2, False)]
           + [_t(f"t{i}", 1.0, 0.9, True) for i in range(20)]}
    rq = build_insights(cur, base)["review_queue"]
    it = next(i for i in rq["items"] if i["task_id"] == "shared")
    assert it["priority"] == "medium"


# ---- D: polish -----------------------------------------------------

def test_reference_frame_marks_below_floor_percentile():
    from agent_evaluator.reporting.insights import _reference_frame_section

    ref = {"label": "r",
           "tcr_pct": {"p10": 62, "p25": 70, "p50": 78, "p75": 85, "p90": 91},
           "gate_scores": {"A": [0.71, 0.74, 0.77, 0.80, 0.83]}}
    hg = {"A": {"score": 0.50, "status": "fail", "gate": "fail", "details": {}}}
    tasks = [_t(f"t{i}", 0.4, 0.4, False) for i in range(20)]
    rf = _reference_frame_section({}, hg, tasks, ref)
    assert rf is not None
    ga = next(m for m in rf["metrics"] if m["metric"] == "gate_a")
    assert ga["percentile_is_floor"] is True     # 0.50 is below the p10 = 0.71


def test_conclusion_shows_faithfulness_and_gate_breakdown():
    from agent_evaluator.reporting.comprehensive_report import _build_conclusion

    hg = {"A": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}},
          "C": {"score": 0.63, "status": "warn", "gate": "warn",
                "details": {"avg_llm_faithfulness": 3.7}}}
    html = _build_conclusion(24, 71.0, 58.5, 0.0, hg, {})
    assert "Faithfulness (LLM judge):</strong> 3.70/5" in html
    assert "(2 warn, 0 fail)" in html
