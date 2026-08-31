"""
tests/test_contrast_pairs_p62.py
================================
SPEC-041 P62 — within-run contrast pairs: each worst failure beside the most
similar passing task + a structured diff isolating the likely differentiator.
"""
from __future__ import annotations

from agent_evaluator.integrations.ask_insights_mcp import contrast_text
from agent_evaluator.reporting.insights import _contrast_pairs_section, build_insights


def _t(tid, comp, acc, ok, q, resp="r", gt="", ctx=None, tools=None, extra=None):
    d = {"task_id": tid, "task_type": "qa", "completion_score": comp,
         "accuracy_score": acc, "success": ok, "question": q, "response": resp,
         "ground_truth": gt}
    if ctx is not None:
        d["context"] = ctx
    if tools is not None:
        d["tool_calls"] = tools
    if extra is not None:
        d["extra"] = extra
    return d


def _mixed():
    return [
        _t("f1", 0.2, 0.2, False, "How do I return a laptop for a refund?",
           resp="short", gt="14 days full refund",
           ctx=["Office hours are 9 to 5.", "We ship worldwide."],
           tools=[{"tool_name": "search"}], extra={"model": "haiku"}),
        _t("p1", 1.0, 0.95, True, "How do I return a phone for a refund?",
           resp="a much longer answer about the 14 day refund policy and the process",
           gt="14 days full refund",
           ctx=["Returns: unopened items within 14 days get a full refund."],
           tools=[{"tool_name": "search"}, {"tool_name": "lookup_policy"}],
           extra={"model": "sonnet"}),
    ] + [_t(f"ok{i}", 1.0, 0.9, True, f"unrelated question {i}") for i in range(8)]


# ---- section -------------------------------------------------------------

def test_none_without_both_sides():
    assert _contrast_pairs_section([_t("f1", 0.1, 0.1, False, "q")]) is None
    assert _contrast_pairs_section([_t("p1", 1.0, 0.9, True, "q")]) is None


def test_pairs_and_retrieval_differentiator():
    rows = _contrast_pairs_section(_mixed())
    assert rows and rows[0]["fail_task_id"] == "f1"
    r = rows[0]
    assert r["pass_task_id"] == "p1"
    assert r["question_similarity"] >= 0.4
    assert r["differences"]["retrieval"]["pass_best_gt_overlap"] > \
        r["differences"]["retrieval"]["fail_best_gt_overlap"]
    assert "retrieval" in r["likely_differentiator"]


def test_tool_differentiator_when_retrieval_equal():
    tasks = [
        _t("f1", 0.2, 0.2, False, "look up my order status now",
           tools=[{"tool_name": "search"}]),
        _t("p1", 1.0, 0.95, True, "look up my order status please",
           tools=[{"tool_name": "search"}, {"tool_name": "order_api"}]),
    ] + [_t(f"ok{i}", 1.0, 0.9, True, f"other {i}") for i in range(6)]
    rows = _contrast_pairs_section(tasks)
    assert rows is not None
    assert "tools" in rows[0]["likely_differentiator"]
    assert "order_api" in rows[0]["likely_differentiator"]


def test_metadata_differentiator():
    tasks = [
        _t("f1", 0.2, 0.2, False, "explain the warranty claim process",
           extra={"model": "haiku"}),
        _t("p1", 1.0, 0.95, True, "explain the warranty claim steps",
           extra={"model": "sonnet"}),
    ] + [_t(f"ok{i}", 1.0, 0.9, True, f"z {i}") for i in range(6)]
    rows = _contrast_pairs_section(tasks)
    assert rows is not None
    assert "metadata" in rows[0]["likely_differentiator"]
    assert rows[0]["differences"]["metadata"]["model"] == ["haiku", "sonnet"]


def test_limit_and_similarity_floor():
    # a failing task with no similar pass -> no row
    tasks = [_t("f1", 0.2, 0.2, False, "quantum chromodynamics lattice gauge")]
    tasks += [_t(f"p{i}", 1.0, 0.9, True, f"how do I bake bread {i}") for i in range(6)]
    assert _contrast_pairs_section(tasks) is None


# ---- MCP text -----------------------------------------------------------

def test_contrast_text():
    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": _mixed()})
    txt = contrast_text({"tasks": _mixed()}, ins, "f1")
    assert "Failing  f1" in txt and "Passing  p1" in txt
    assert "Likely differentiator" in txt and "retrieval" in txt
    # unknown id -> lists available
    assert "Available:" in contrast_text({}, ins, "nope")
    # no pairs at all
    assert "No contrast pairs" in contrast_text({}, {"contrast_pairs": []}, "x")


# ---- end to end -----------------------------------------------------------

def test_build_insights_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_contrast_pairs

    ins = build_insights({"extra_metrics": {"harness_groups": {}}, "tasks": _mixed()})
    cp = ins["contrast_pairs"]
    assert cp and cp[0]["fail_task_id"] == "f1"
    html = _build_contrast_pairs(cp)
    assert "Failure vs Nearest Pass" in html and "f1" in html and "p1" in html
    assert _build_contrast_pairs(None) == ""
