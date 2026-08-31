"""
tests/test_failure_taxonomy_p55.py
==================================
SPEC-041 P55 — single-agent failure taxonomy (ontology.failure_taxonomy) +
insights.failure_taxonomy aggregation.
"""
from __future__ import annotations

from agent_evaluator.ontology.failure_taxonomy import (
    FAILURE_MODES,
    classify_failure,
    remediation_for,
)
from agent_evaluator.reporting.insights import _failure_taxonomy_section, build_insights


def _t(tid, comp, acc, ok, reason=None, **kw):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": kw.get("q", "q?"), "response": kw.get("resp", "r"),
            "ground_truth": kw.get("gt", ""), "context": kw.get("ctx"),
            "tool_calls": kw.get("tool_calls"),
            "expected_tools": kw.get("expected_tools")}


# ---- classifier ---------------------------------------------------------------

def test_all_modes_have_owner_and_remediation():
    for code, m in FAILURE_MODES.items():
        assert m.owner in {"prompt", "config", "data", "model", "infra"}
        assert m.remediation and remediation_for(code)


def test_runtime_error():
    c = classify_failure({"partial_reason": "error: TimeoutError"},
                         reason="error: timeouterror")
    assert c["code"] == "RUNTIME_ERROR" and c["owner"] == "infra"


def test_tool_execution_error():
    c = classify_failure({"tool_calls": [{"tool_name": "search", "success": False,
                                          "error": "500"}]})
    assert c["code"] == "TOOL_EXECUTION_ERROR"


def test_tool_selection_error():
    c = classify_failure({"expected_tools": ["lookup_order"],
                          "tool_calls": [{"tool_name": "web_search"}]})
    assert c["code"] == "TOOL_SELECTION_ERROR"


def test_refusal_when_answerable():
    c = classify_failure({"response": "I'm sorry, but I cannot help with that.",
                          "ground_truth": "Returns are accepted within 14 days."})
    assert c["code"] == "REFUSAL_WHEN_ANSWERABLE"


def test_format_violation():
    c = classify_failure({"question": "Give the steps as a JSON array",
                          "response": "First do this, then that, then the other.",
                          "ground_truth": "[\"a\",\"b\"]"})
    assert c["code"] == "FORMAT_VIOLATION"


def test_premature_stop():
    c = classify_failure({"partial_reason": "only part of a multi-step answer completed"},
                         reason="only part of a multi-step answer completed")
    assert c["code"] == "PREMATURE_STOP" and c["owner"] == "prompt"


def test_retrieval_miss_vs_grounding_miss():
    miss = classify_failure({
        "ground_truth": "The capital of France is Paris.",
        "context": ["Berlin is the capital of Germany.", "Rome hosts a festival."],
        "response": "It is Lyon."})
    assert miss["code"] == "RETRIEVAL_MISS"
    grd = classify_failure({
        "ground_truth": "The capital of France is Paris.",
        "context": ["The capital of France is Paris, a large city."],
        "response": "The capital of France is Lyon."},
        reason="answer not grounded in the retrieved context")
    assert grd["code"] == "GROUNDING_MISS"


def test_over_elaboration():
    c = classify_failure({
        "ground_truth": "Yes.",
        "response": ("Well " + "there are many considerations to weigh here " * 20)})
    assert c["code"] == "OVER_ELABORATION"


def test_label_issue_needs_repeat_and_low_acc():
    task = {"accuracy_score": 0.2, "response": "x", "ground_truth": "y"}
    assert classify_failure(task)["code"] != "LABEL_OR_SPEC_ISSUE"
    assert classify_failure(task, repeated_across_runs=True)["code"] == "LABEL_OR_SPEC_ISSUE"


def test_unclassified_is_low_similarity_low_conf():
    c = classify_failure({"response": "abc", "ground_truth": "xyz"})
    assert c["code"] == "LOW_SIMILARITY" and c["confidence"] == 0.3


# ---- section aggregation ---------------------------------------------------

def test_section_none_without_failures():
    assert _failure_taxonomy_section([_t("a", 1.0, 0.9, True)]) is None


def test_section_aggregates_and_sorts():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(4)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(2)]
    ft = _failure_taxonomy_section(tasks)
    assert ft["n_failures"] == 6
    codes = [m["code"] for m in ft["by_mode"]]
    assert codes[0] == "RUNTIME_ERROR"          # biggest bucket first
    assert ft["dominant_mode"]["code"] == "RUNTIME_ERROR"
    assert ft["owner_mix"].get("infra") == 4
    for m in ft["by_mode"]:
        assert 0.0 <= m["share_of_failures_pct"] <= 100.0
        assert m["remediation"]


def test_label_issue_uses_baseline():
    cur = {"tasks": [_t("bad", 0.1, 0.1, False, "low similarity", resp="x", gt="y")]}
    base = {"tasks": [_t("bad", 0.1, 0.1, False, "low similarity", resp="x", gt="y")]}
    ft = _failure_taxonomy_section(cur["tasks"], base)
    assert any(m["code"] == "LABEL_OR_SPEC_ISSUE" for m in ft["by_mode"])


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_failure_taxonomy

    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(6)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": tasks})
    ft = ins["failure_taxonomy"]
    assert ft and ft["by_mode"]
    html = _build_failure_taxonomy(ft)
    assert "Failure Taxonomy" in html and "Remediation" in html and "INFRA" in html
    assert _build_failure_taxonomy(None) == ""


def test_triggers_carry_taxonomy_code():
    from agent_evaluator.reporting.insights import _failure_triggers_section

    tasks = [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    trigs = _failure_triggers_section(tasks)
    assert trigs and all(tr.get("taxonomy_code") for tr in trigs)
