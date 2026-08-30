"""
tests/test_score_breakdowns.py
==================================
SPEC-041 P23 — per-example score decomposition (`insights.score_breakdowns`).
"Which signal dragged this task's score down" — the accuracy sub-signals and the
LLM judge's rationale, surfaced per failing task.
"""
from __future__ import annotations

import json

import jsonschema
import pytest

from agent_evaluator.core.trackers.layer1 import AccuracyEvaluator
from agent_evaluator.reporting.insights import _score_breakdowns_section, build_insights


class TestDecomposeQA:
    def test_components_sum_to_the_score(self):
        ae = AccuracyEvaluator()
        d = ae.decompose_qa("The capital of France is Paris", "Paris is the capital of France")
        for k in ("token_overlap_f1", "jaccard", "lcs_ratio", "char_sim", "weighted"):
            assert 0.0 <= d[k] <= 1.0
        recomputed = (0.4 * d["token_overlap_f1"] + 0.3 * d["jaccard"]
                      + 0.2 * d["lcs_ratio"] + 0.1 * d["char_sim"])
        assert d["weighted"] == pytest.approx(recomputed, abs=1e-3)
        assert d["weakest"] in d and d[d["weakest"]] == min(
            d["token_overlap_f1"], d["jaccard"], d["lcs_ratio"], d["char_sim"]
        )

    def test_qa_accuracy_unchanged_by_refactor(self):
        ae = AccuracyEvaluator()
        s = ae._qa_accuracy("The capital is Paris", "The capital is Paris")
        assert s == pytest.approx(1.0, abs=1e-6)
        assert ae._qa_accuracy("Paris", "completely unrelated answer") < 0.3

    def test_empty_ground_truth(self):
        assert AccuracyEvaluator().decompose_qa("", "anything")["weighted"] == 0.0


def _task(tid, *, ok, judge=None, ttype="qa"):
    d = {
        "task_id": tid, "task_type": ttype, "success": ok,
        "completion_score": 1.0 if ok else 0.2,
        "accuracy_score": 0.9 if ok else 0.18,
        "question": "What is the capital of France?",
        "response": "The capital of France is Paris." if ok
        else "It could be Lyon somewhere in the south",
        "ground_truth": "The capital of France is Paris.",
    }
    if judge is not None:
        d["llm_judge"] = judge
    return d


class TestScoreBreakdownsSection:
    def test_none_when_nothing_failing(self):
        assert _score_breakdowns_section([_task(f"t{i}", ok=True) for i in range(5)]) is None

    def test_accuracy_components_and_weakest(self):
        rows = _score_breakdowns_section(
            [_task(f"t{i}", ok=False) for i in range(3)]
            + [_task(f"ok{i}", ok=True) for i in range(5)]
        )
        assert len(rows) == 3
        r = rows[0]
        assert set(r["accuracy_components"]) == {
            "token_overlap_f1", "jaccard", "lcs_ratio", "char_sim"
        }
        assert r["accuracy_weakest"] in r["accuracy_components"]
        assert r["weakest_signal"] is not None

    def test_judge_reasoning_and_dimensions_included(self):
        judge = {"skipped": False, "reasoning": "Wrong city, hedged.",
                 "scores": {"overall": 3.0, "completeness": 2, "relevance": 4, "faithfulness": 1}}
        rows = _score_breakdowns_section([_task("t0", ok=False, judge=judge)])
        r = rows[0]
        assert r["judge_reasoning"] == "Wrong city, hedged."
        assert r["judge_dimensions"] == {"completeness": 2, "relevance": 4, "faithfulness": 1}
        assert r["judge_overall"] == 3.0
        # weakest_signal ranks accuracy signals (0-1) and judge dims (÷5) together
        assert r["weakest_signal"] in (
            "jaccard", "token_overlap_f1", "lcs_ratio", "char_sim", "judge.faithfulness"
        )

    def test_judge_dimension_can_be_the_weakest_when_text_matches(self):
        # a grounded, textually-close answer that the judge still marks unfaithful
        t = {
            "task_id": "t0", "task_type": "qa", "success": False,
            "completion_score": 0.9, "accuracy_score": 0.85,
            "question": "capital of France?",
            "response": "The capital of France is Paris.",
            "ground_truth": "The capital of France is Paris.",
            "llm_judge": {"skipped": False, "reasoning": "Fabricated a citation.",
                          "scores": {"overall": 4.0, "completeness": 5,
                                     "relevance": 5, "faithfulness": 1}},
        }
        r = _score_breakdowns_section([t])[0]
        assert r["weakest_signal"] == "judge.faithfulness"

    def test_code_and_tool_use_get_a_note_not_components(self):
        rows = _score_breakdowns_section([
            {**_task("c0", ok=False), "task_type": "coding", "ground_truth": ""},
            {**_task("tu0", ok=False), "task_type": "tool_use", "ground_truth": ""},
        ])
        by = {r["task_id"]: r for r in rows}
        assert "AST" in by["c0"]["accuracy_note"]
        assert "tool_calls" in by["tu0"]["accuracy_note"]
        assert "accuracy_components" not in by["c0"]


class TestBuildInsightsWiring:
    def test_key_present_and_schema_valid(self):
        rpt = {
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}},
            }},
            "tasks": [_task(f"t{i}", ok=i % 3 == 0) for i in range(12)],
        }
        ins = build_insights(rpt)
        assert ins["score_breakdowns"] and len(ins["score_breakdowns"]) >= 1
        json.dumps(ins)
        from pathlib import Path
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_report_renders_collapsible_detail(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )

        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(10):
            fail = i < 4
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="What is the capital of France?",
                response="Paris." if not fail else "Maybe Lyon in the south of France",
                ground_truth="The capital of France is Paris.",
                execution_time=1.0, task_type="qa",
            ))
        html = generate_comprehensive_html_report(m)
        assert "▸ Score breakdown" in html
        assert "accuracy signals:" in html
