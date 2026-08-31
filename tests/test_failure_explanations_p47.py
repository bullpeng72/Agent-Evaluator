"""
tests/test_failure_explanations_p47.py
======================================
SPEC-041 P47 — insights.failure_explanations: split each failing response into
claims, mark supported / contradicts / unsupported, trace each to its source.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _claim_source,
    _claim_verdict,
    _failure_explanations_section,
    _sentences,
    build_insights,
)


def _t(tid, *, resp, gt, acc=0.2, ctx=None, tool_calls=None):
    d = {"task_id": tid, "task_type": "qa", "response": resp, "ground_truth": gt,
         "accuracy_score": acc, "completion_score": 1.0, "success": acc >= 0.6,
         "question": f"q {tid}"}
    if ctx is not None:
        d["context"] = ctx
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    return d


def test_sentences_splits_and_filters():
    s = _sentences("The sky is blue. It rains. Ok.\nA new line here now.")
    assert "The sky is blue." in s
    assert "Ok." not in s          # < 3 words dropped


def test_claim_verdict_supported():
    assert _claim_verdict("Refunds are available within 14 days of purchase.",
                          "Refunds are available within 14 days of purchase.") == "supported"


def test_claim_verdict_contradicts_on_negation():
    assert _claim_verdict("We do not ship internationally.",
                          "We ship internationally to the US and Japan.") \
        == "contradicts_ground_truth"


def test_claim_verdict_contradicts_on_number_mismatch():
    assert _claim_verdict("The warranty is 5 years on the body.",
                          "The warranty is 2 years on the body.") \
        == "contradicts_ground_truth"


def test_claim_verdict_unsupported_when_offtopic():
    assert _claim_verdict("Please contact our support centre.",
                          "Refunds within 14 days.") == "unsupported"


def test_claim_source_traces_to_context_chunk():
    chunks = ["ACME policy: unopened items get a full refund within fourteen days.",
              "Bulk orders have separate clauses."]
    src = _claim_source("Unopened items get a full refund within fourteen days.",
                        chunks, [])
    assert src == "context_chunk[0]"


def test_claim_source_tool_output_then_none():
    assert _claim_source("order 10293 is out for delivery", [],
                         ["Order 10293 status: out for delivery today"]) == "tool_output"
    assert _claim_source("the moon is made of cheese", [], []).startswith("none")


def test_section_shape_and_wrong_claim():
    tasks = [
        _t("f1", resp="We do not ship abroad. Delivery is 3 days.",
           gt="We ship abroad to the US, Japan and Singapore.",
           ctx="Policy: we ship abroad to the US, Japan and Singapore."),
        _t("ok1", resp="fine", gt="fine", acc=0.95),
    ]
    fe = _failure_explanations_section(tasks)
    assert fe and len(fe) == 1
    r = fe[0]
    assert r["task_id"] == "f1" and r["explained_by"] == "template"
    assert r["wrong_claim_verdict"] == "contradicts_ground_truth"
    assert any(c["verdict"] == "contradicts_ground_truth" for c in r["claims"])


def test_explainer_hook_and_fallback():
    tasks = [_t("f1", resp="Wrong stuff here entirely.", gt="Right answer.")]

    def good(payload):
        return {"claims": [{"text": "custom", "verdict": "contradicts_ground_truth",
                            "source": "LLM"}], "wrong_claim": "custom"}

    fe = _failure_explanations_section(tasks, explainer=good)
    assert fe[0]["explained_by"] == "explainer"
    assert fe[0]["claims"][0]["source"] == "LLM"

    fe_bad = _failure_explanations_section(tasks, explainer=lambda p: "nope")
    assert fe_bad[0]["explained_by"] == "template"

    fe_raise = _failure_explanations_section(
        tasks, explainer=lambda p: (_ for _ in ()).throw(RuntimeError()))
    assert fe_raise[0]["explained_by"] == "template"


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import (
        _build_failure_explanations,
    )

    cur = {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {}}}},
        "tasks": [_t(f"f{i}", resp="We do not ship abroad.",
                     gt="We ship abroad.", ctx="We ship abroad.")
                  for i in range(3)]}
    ins = build_insights(cur)
    fe = ins["failure_explanations"]
    assert fe and len(fe) == 3
    html = _build_failure_explanations(fe)
    assert "Claim-Level Failure Explanation" in html
    assert "contradicts ground truth" in html
    assert _build_failure_explanations(None) == ""
