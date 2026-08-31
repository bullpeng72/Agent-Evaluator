"""
tests/test_improvement_priors_p57.py
====================================
SPEC-041 P57 — cross-run learning: rca.improvement_priors.synthesize_priors
folds the experiment + recommendation-outcome logs into a per-(gate,
change-category) track record; insights.improvement_priors + a `prior` on each
recommendation.
"""
from __future__ import annotations

import json

from agent_evaluator.rca.improvement_priors import (
    _category_of,
    prior_for,
    synthesize_priors,
)
from agent_evaluator.reporting.insights import build_insights

# ---- category detection ----------------------------------------------------

def test_category_of():
    assert _category_of("[improve] Gate A prompt_edit: add grounding") == "prompt_edit"
    assert _category_of("[improve] Gate C config_change: retry") == "config_change"
    assert _category_of("added retry + backoff config") == "config_change"
    assert _category_of("re-checked the ground_truth wording") == "data_fix"
    assert _category_of("rephrase the system prompt") == "prompt_edit"
    assert _category_of("something vague") == "other"


# ---- synthesis -----------------------------------------------------------

def _exp(gate, note, verdict, delta):
    return {"experiment_id": "e", "status": "resolved", "target_gate": gate,
            "note": note, "verdict": verdict, "actual_delta": delta}


def test_none_when_no_verdicts():
    assert synthesize_priors([], []) is None
    assert synthesize_priors([{"status": "open", "target_gate": "A"}], []) is None


def test_buckets_confirm_rate_and_verdict():
    exps = [
        _exp("A", "[improve] Gate A prompt_edit: g", "confirmed", 0.09),
        _exp("A", "[improve] Gate A prompt_edit: f", "refuted", -0.01),
        _exp("A", "prompt rewrite", "confirmed", 0.06),
        _exp("C", "added retry config", "refuted", 0.0),
        _exp("C", "retry backoff config", "refuted", 0.01),
    ]
    outs = [{"verdict": "confirmed", "target_gate": "D", "gate_delta": 0.16,
             "note": "parallelised the retriever + cache"}]
    p = synthesize_priors(exps, outs)
    assert p is not None
    a = next(b for b in p["by_bucket"] if b["gate"] == "A")
    assert a["category"] == "prompt_edit" and a["n"] == 3
    assert a["confirm_rate"] == round(2 / 3, 2) and a["verdict"] == "works_well"
    assert a["mean_confirmed_delta"] == 0.075
    c = next(b for b in p["by_bucket"] if b["gate"] == "C")
    assert c["confirm_rate"] == 0.0 and c["verdict"] == "ineffective"
    d = next(b for b in p["by_bucket"] if b["gate"] == "D")
    assert d["verdict"] == "insufficient_data"          # n=1 decisive
    assert p["overall"]["confirm_rate"] == 0.5
    assert "prompt edit on Gate A has the best record" in p["note"]
    assert "poor record here" in p["note"]


def test_prior_for_bucket_then_category_then_none():
    p = synthesize_priors(
        [_exp("A", "[improve] Gate A prompt_edit: x", "confirmed", 0.1),
         _exp("A", "[improve] Gate A prompt_edit: y", "confirmed", 0.1)], [])
    _pf = prior_for(p, "A", "prompt_edit")
    assert _pf is not None and _pf["verdict"] == "works_well"
    cat = prior_for(p, "B", "prompt_edit")           # no B bucket -> category rollup
    assert cat and cat["scope"] == "category"
    assert prior_for(p, "A", "data_fix") is None
    assert prior_for(None, "A", "prompt_edit") is None


# ---- end to end through build_insights ----------------------------------

def _t(tid, comp, acc, ok, reason=None):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q", "response": "r", "ground_truth": "x"}


def test_build_insights_wires_priors_and_annotates_recs(tmp_path):
    exps = [
        _exp("A", "[improve] Gate A prompt_edit: g", "confirmed", 0.09),
        _exp("A", "[improve] Gate A prompt_edit: f", "refuted", -0.01),
        _exp("A", "prompt rewrite", "confirmed", 0.06),
    ]
    (tmp_path / "experiments.jsonl").write_text(
        "\n".join(json.dumps({**e, "experiment_id": f"e{i}"}) for i, e in enumerate(exps)))
    (tmp_path / "recommendation_outcomes.jsonl").write_text(
        json.dumps({"verdict": "confirmed", "target_gate": "A",
                    "gate_delta": 0.05, "note": "prompt tweak"}))
    tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
    tasks += [_t(f"g{i}", 0.3, 0.2, False,
                 "answer not grounded in the retrieved context") for i in range(4)]
    cur = {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}}},
        "lineage": {"prompt_text": "Answer using the context."}}, "tasks": tasks}
    ins = build_insights(
        cur,
        recommendation_log_path=str(tmp_path / "recommendation_outcomes.jsonl"),
        experiments_log_path=str(tmp_path / "experiments.jsonl"),
    )
    ip = ins["improvement_priors"]
    assert ip is not None and ip["by_bucket"]
    rec_a = next(r for r in ins["recommendations"] if r["gate"] == "A")
    if rec_a.get("proposal", {}).get("kind") == "prompt_edit":
        assert rec_a["prior"]["verdict"] == "works_well"
        assert rec_a["prior"]["category"] == "prompt_edit"


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import (
        _build_improvement_priors,
        _rec_prior_html,
    )

    ip = synthesize_priors(
        [_exp("C", "retry config", "refuted", 0.0),
         _exp("C", "retry backoff config", "refuted", 0.01)], [])
    html = _build_improvement_priors(ip)
    assert "What Has Worked Here" in html and "Confirm rate" in html
    assert _build_improvement_priors(None) == ""
    line = _rec_prior_html({"category": "config_change", "n": 2,
                            "confirm_rate": 0.0, "verdict": "ineffective"})
    assert "poor track record" in line
    assert _rec_prior_html(None) == ""
