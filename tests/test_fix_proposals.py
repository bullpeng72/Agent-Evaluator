"""
tests/test_fix_proposals.py
===========================
SPEC-041 P36 — evidence-grounded fix proposals on ``insights.recommendations``.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _deterministic_proposal,
    _proposal_category,
    _validate_proposal,
    build_insights,
)


def _t(tid, comp, acc, ok, reason, ttype="qa", q="q?", resp="r"):
    return {"task_id": tid, "task_type": ttype, "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": q, "response": resp}


def _result(gate_scores, tasks, *, prompt_text=None):
    hg = {k: {"score": s, "status": "warn" if s < 0.7 else "pass",
              "gate": "warn" if s < 0.7 else "pass", "details": {}}
          for k, s in gate_scores.items()}
    em = {"harness_groups": hg}
    if prompt_text is not None:
        em["lineage"] = {"prompt_text": prompt_text}
    return {"extra_metrics": em, "tasks": tasks}


# ---- category mapping ---------------------------------------------------------

def test_proposal_category():
    assert _proposal_category("error: TimeoutError") == "runtime"
    assert _proposal_category("answer not grounded in the retrieved context") == "grounding"
    assert _proposal_category("only part of a multi-step answer completed") == "decomposition"
    assert _proposal_category("consecutive_repeat loop detected") == "guardrail"
    assert _proposal_category("low ground_truth similarity") == "data"
    assert _proposal_category("something weird") == "generic"


# ---- deterministic proposal shape ------------------------------------------

def test_deterministic_grounding_proposal_uses_prompt_line():
    members = [_t("g1", 0.5, 0.2, False, "answer not grounded in the retrieved context")]
    p = _deterministic_proposal(
        "A", "answer not grounded in the retrieved context", members,
        "You are a support agent.\nAnswer helpfully and in detail.\n",
    )
    assert p["kind"] == "prompt_edit"
    assert "Answer helpfully and in detail." in p["before"]
    assert "Only state facts" in p["after"]
    assert p["evidence_task_ids"] == ["g1"]


def test_deterministic_runtime_proposal_is_config_change():
    members = [_t(f"r{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    p = _deterministic_proposal("C", "error: TimeoutError", members, "")
    assert p["kind"] == "config_change"
    assert "FaultToleranceConfig" in p["after"]
    assert "3 task(s)" in p["rationale"]


def test_deterministic_data_proposal():
    members = [_t("d1", 0.9, 0.1, False, "low ground_truth similarity")]
    p = _deterministic_proposal("A", "low ground_truth similarity", members, "")
    assert p["kind"] == "data_fix"
    assert "d1" in p["after"]


# ---- validation -----------------------------------------------------------

def test_validate_rejects_bad_kind():
    assert _validate_proposal({"kind": "nope"}) is None
    assert _validate_proposal("not a dict") is None
    ok = _validate_proposal({"kind": "prompt_edit", "before": "a", "after": "b",
                             "rationale": "r", "evidence_task_ids": ["x", "y"]})
    assert ok["kind"] == "prompt_edit" and ok["evidence_task_ids"] == ["x", "y"]
    assert ok["authored_by"] == "template"


# ---- end-to-end through build_insights -----------------------------------

def _run():
    tasks = [_t(f"p{i}", 1.0, 0.9, True, None) for i in range(10)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(4)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    return _result({"A": 0.6, "C": 0.62}, tasks,
                   prompt_text="Answer the question using the context.")


def test_build_insights_attaches_proposal():
    ins = build_insights(_run())
    props = {r["gate"]: r.get("proposal") for r in ins["recommendations"]}
    assert props.get("A") and props["A"]["kind"] == "prompt_edit"
    assert props.get("C") and props["C"]["kind"] == "config_change"
    assert all(p["authored_by"] == "template" for p in props.values() if p)


def test_fixer_callable_overrides_and_bad_fixer_falls_back():
    def good(payload):
        tp = payload["template_proposal"]
        return {"kind": "prompt_edit", "before": tp["before"],
                "after": "LLM: " + tp["after"], "rationale": "crafted",
                "evidence_task_ids": payload["evidence"][0:1] and
                [payload["evidence"][0]["task_id"]]}

    ins = build_insights(_run(), fixer=good)
    a = next(r["proposal"] for r in ins["recommendations"] if r["gate"] == "A")
    assert a["authored_by"] == "fixer" and a["after"].startswith("LLM: ")

    ins_bad = build_insights(_run(), fixer=lambda p: {"kind": "garbage"})
    a2 = next(r["proposal"] for r in ins_bad["recommendations"] if r["gate"] == "A")
    assert a2["authored_by"] == "template"

    ins_raise = build_insights(_run(), fixer=lambda p: (_ for _ in ()).throw(RuntimeError()))
    a3 = next(r["proposal"] for r in ins_raise["recommendations"] if r["gate"] == "A")
    assert a3["authored_by"] == "template"


def test_proposal_renders_in_recommendations_html():
    from agent_evaluator.reporting.comprehensive_report import _build_recommendations

    ins = build_insights(_run())
    hg = _run()["extra_metrics"]["harness_groups"]
    html = _build_recommendations(
        hg, 60.0, 55.0, 0.0, 2.0, {},
        insights_recs=ins["recommendations"],
    )
    assert "Proposed fix" in html
    assert "review before applying" in html
    assert "FaultToleranceConfig" in html          # Gate C config_change proposal


def test_rec_proposal_html_empty_when_none():
    from agent_evaluator.reporting.comprehensive_report import _rec_proposal_html

    assert _rec_proposal_html(None) == ""
    assert _rec_proposal_html({}) == ""
    out = _rec_proposal_html({"kind": "data_fix", "before": "x", "after": "y",
                              "rationale": "z", "evidence_task_ids": ["t1"],
                              "authored_by": "fixer"})
    assert "Eval-set fix" in out and "LLM-drafted" in out and "t1" in out
