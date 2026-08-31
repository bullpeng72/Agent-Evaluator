"""
tests/test_ablation_hints_p56.py
================================
SPEC-041 P56 — ablation hints: the one prompt line / config knob most
implicated in each failure mode, ranked by how many failures it touches.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _ablation_hints_section,
    _prompt_sentences,
    build_insights,
)


def _t(tid, comp, acc, ok, reason=None):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q", "response": "r", "ground_truth": ""}


_PROMPT = (
    "You are a support agent.\n"
    "Answer helpfully and in detail.\n"
    "Always use the retrieved context to ground your answer.\n"
    "Break the task into numbered steps and complete every step."
)


def _cur(tasks, prompt=_PROMPT):
    return {"extra_metrics": {
        "harness_groups": {"A": {"score": 0.5, "status": "fail",
                                 "gate": "fail", "details": {}}},
        "lineage": {"prompt_text": prompt}}, "tasks": tasks}


def _tax(tasks):
    from agent_evaluator.reporting.insights import _failure_taxonomy_section
    return _failure_taxonomy_section(tasks)


# ---- helpers ---------------------------------------------------------------

def test_prompt_sentences_indexed_and_filtered():
    s = _prompt_sentences("Short.\nThis one has enough words to keep.\nx")
    assert s == [(1, "This one has enough words to keep.")]


def test_none_without_taxonomy():
    assert _ablation_hints_section([], {}, None) is None
    assert _ablation_hints_section([], {}, {"by_mode": []}) is None


# ---- section -----------------------------------------------------------

def test_prompt_line_hit_for_premature_stop():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(4)]
    hints = _ablation_hints_section(tasks, _cur(tasks), _tax(tasks))
    ps = next(h for h in hints if h["taxonomy_code"] == "PREMATURE_STOP")
    assert ps["target_kind"] == "prompt_line"
    assert "numbered steps" in ps["target"] and ps["prompt_line_index"] == 3
    assert ps["n_tasks"] == 4


def test_config_knob_for_runtime_error_and_ranking():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(5)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(2)]
    hints = _ablation_hints_section(tasks, _cur(tasks), _tax(tasks))
    # runtime (5) ranks above premature-stop (2)
    assert hints[0]["taxonomy_code"] == "RUNTIME_ERROR"
    assert hints[0]["target_kind"] == "config_knob"
    assert "FaultToleranceConfig" in hints[0]["target"]
    assert [h["n_tasks"] for h in hints] == sorted(
        (h["n_tasks"] for h in hints), reverse=True)


def test_missing_prompt_line_is_flagged():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(3)]
    # prompt has no step/decomposition instruction
    hints = _ablation_hints_section(
        tasks, _cur(tasks, "You are a support agent. Answer questions."), _tax(tasks))
    ps = next(h for h in hints if h["taxonomy_code"] == "PREMATURE_STOP")
    assert ps["prompt_line_index"] is None
    assert "no rule addressing it" in ps["rationale"]


def test_low_similarity_and_small_buckets_skipped():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t("solo", 0.3, 0.2, False, "only part of a multi-step answer completed")]
    hints = _ablation_hints_section(tasks, _cur(tasks), _tax(tasks))
    # n=1 bucket -> below the n>=2 floor
    assert hints is None or all(h["n_tasks"] >= 2 for h in hints)


# ---- end to end -----------------------------------------------------------

def test_build_insights_wires_it():
    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(4)]
    ins = build_insights(_cur(tasks))
    assert ins["ablation_hints"] and ins["ablation_hints"][0]["n_tasks"] == 4


def test_report_render():
    from agent_evaluator.reporting.comprehensive_report import _build_ablation_hints

    tasks = [_t(f"ok{i}", 1.0, 0.9, True) for i in range(8)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(3)]
    hints = _ablation_hints_section(tasks, _cur(tasks), _tax(tasks))
    html = _build_ablation_hints(hints)
    assert "What to Change First" in html and "PROMPT LINE" in html
    assert _build_ablation_hints(None) == ""
