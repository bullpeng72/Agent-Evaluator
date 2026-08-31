"""
tests/test_eval_set_gap_p45.py
==============================
SPEC-041 P45 — eval_set_quality gains capability_coverage, contamination and
targeted_additions.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _capability_coverage,
    _contamination,
    _eval_set_quality_section,
    _q_ngrams,
    _targeted_additions,
    build_insights,
)


def _t(tid, tt="qa", *, q="how does this work in practice", gt="a real answer",
       acc=0.9, ok=True, tools=False, difficulty=None):
    d = {"task_id": tid, "task_type": tt, "question": q, "ground_truth": gt,
         "accuracy_score": acc, "completion_score": 1.0 if ok else 0.2,
         "success": ok}
    if tools:
        d["tool_calls"] = [{"tool_name": "x", "success": True}]
    if difficulty:
        d["extra"] = {"difficulty": difficulty}
    return d


def test_q_ngrams():
    assert _q_ngrams("a b c", 4) == set()
    g = _q_ngrams("the quick brown fox jumps", 4)
    assert "the quick brown fox" in g and "quick brown fox jumps" in g


def test_capability_coverage_cells_and_thin():
    tasks = ([_t(f"q{i}", "qa", difficulty="hard") for i in range(6)]
             + [_t(f"t{i}", "tool_use", tools=True, difficulty="easy", ok=False)
                for i in range(2)])
    cov = _capability_coverage(tasks)
    assert cov["cells"]["task_type"]["qa"]["n"] == 6
    assert cov["cells"]["uses_tools"]["yes"]["n"] == 2
    assert cov["cells"]["uses_tools"]["yes"]["fail_n"] == 2
    thin = {(c["dimension"], c["value"]) for c in cov["thin_cells"]}
    assert ("task_type", "tool_use") in thin        # n=2 < 3
    assert ("difficulty", "easy") in thin


def test_contamination_flags_prompt_leak():
    prompt = ("You are a helper.\nExample — Q: what is the refund window "
              "for opened items A: fourteen days")
    tasks = [
        _t("leak", q="what is the refund window for opened items"),
        _t("clean", q="how many colours does the deluxe model come in"),
    ]
    c = _contamination(tasks, prompt)
    ids = {x["task_id"] for x in c}
    assert "leak" in ids and "clean" not in ids
    assert c[0]["overlap_pct"] >= 40.0


def test_contamination_empty_without_prompt():
    assert _contamination([_t("a")], "") == []


def test_targeted_additions():
    tasks = ([_t(f"qa{i}", "qa") for i in range(20)]
             + [_t(f"ir{i}", "information_retrieval", ok=False, acc=0.2)
                for i in range(3)])
    hist = {"qa": 20, "information_retrieval": 3}
    adds = _targeted_additions(tasks, hist)
    assert adds and adds[0]["task_type"] == "information_retrieval"
    assert adds[0]["failing_n"] == 3 and adds[0]["current_n"] == 3
    assert adds[0]["suggested_add"] >= 1


def test_section_carries_new_keys_and_contamination_warning():
    tasks = [_t(f"x{i}", "qa", q="what is the return policy exactly please tell me")
             for i in range(4)]
    cur = {"extra_metrics": {"lineage": {
        "prompt_text": "Example: what is the return policy exactly please tell me"}}}
    q = _eval_set_quality_section(tasks, None, {}, cur)
    assert "capability_coverage" in q and "contamination" in q
    assert q["contamination"]
    assert any("overlap the system prompt" in w for w in q["coverage_warnings"])


def test_end_to_end_and_report():
    from agent_evaluator.reporting.comprehensive_report import _build_eval_set_quality

    tasks = ([_t(f"qa{i}", "qa") for i in range(4)]
             + [_t(f"t{i}", "tool_use", tools=True, ok=False, acc=0.2)
                for i in range(2)])
    cur = {"extra_metrics": {"harness_groups": {}, "lineage": {}}, "tasks": tasks}
    ins = build_insights(cur)
    esq = ins["eval_set_quality"]
    assert esq and "capability_coverage" in esq
    html = _build_eval_set_quality(None, None, {}, esq)
    assert "Capability coverage" in html
