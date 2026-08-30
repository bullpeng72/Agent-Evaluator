"""
tests/test_cohort_comparison.py
==================================
SPEC-041 P22 — N-version cohort comparison (`insights.cohort_comparison`).
The report / insights previously only compared one result to one optional
baseline; this puts 3+ versions side by side with FDR-adjusted significance and
a "pick the winner" call.
"""
from __future__ import annotations

import json

import jsonschema
import pytest

from agent_evaluator.reporting.insights import _cohort_comparison_section, build_insights
from agent_evaluator.utils.confidence import welch_t_p


def _rep(label, tcr_by_type: dict[str, float], n_per_type: int = 20):
    tasks = []
    for tt, frac in tcr_by_type.items():
        n_ok = round(frac * n_per_type)
        for i in range(n_per_type):
            ok = i < n_ok
            tasks.append({
                "task_id": f"{label}-{tt}-{i}", "task_type": tt, "success": ok,
                "completion_score": 1.0 if ok else 0.0,
                "accuracy_score": 0.9 if ok else 0.2,
            })
    return {
        "extra_metrics": {
            "harness_groups": {
                "A": {"score": 0.7, "status": "warn", "gate": "warn", "details": {}},
                "overall": {"score": 0.7},
            },
            "lineage": {"agent_version": label},
        },
        "tasks": tasks,
    }


class TestWelchTP:
    def test_identical_samples_p_near_one(self):
        a = [1.0, 0.0] * 20
        assert welch_t_p(a, list(a)) == pytest.approx(1.0, abs=0.05)

    def test_clearly_different_p_small(self):
        p = welch_t_p([1.0] * 30, [0.0] * 30)
        assert p is not None and p < 0.001

    def test_too_few_returns_none(self):
        assert welch_t_p([1.0], [0.0, 1.0]) is None


class TestCohortComparison:
    def test_none_below_two_versions(self):
        assert _cohort_comparison_section([("v1", _rep("v1", {"qa": 0.9}))]) is None

    def test_versions_pairwise_and_task_type_winner(self):
        labelled = [
            ("v1", _rep("v1", {"qa": 0.95, "rag": 0.70})),
            ("v2", _rep("v2", {"qa": 0.80, "rag": 0.60})),
            ("v3", _rep("v3", {"qa": 0.50, "rag": 0.30})),
        ]
        cc = _cohort_comparison_section(labelled, metric="tcr")
        assert cc["n_versions"] == 3
        assert {v["label"] for v in cc["versions"]} == {"v1", "v2", "v3"}
        assert len(cc["pairwise"]) == 3            # 3 unordered pairs
        # v1 vs v3 is a big gap -> FDR-significant
        v1v3 = next(e for e in cc["pairwise"] if {e["a"], e["b"]} == {"v1", "v3"})
        assert v1v3["significant_fdr"] is True
        assert v1v3["p_value_fdr"] is not None
        # v1 wins every slice
        for row in cc["by_task_type"]:
            assert row["winner"] == "v1"

    def test_winner_declared_when_lead_is_significant(self):
        labelled = [
            ("winner", _rep("winner", {"qa": 0.95}, n_per_type=40)),
            ("mid", _rep("mid", {"qa": 0.55}, n_per_type=40)),
            ("low", _rep("low", {"qa": 0.30}, n_per_type=40)),
        ]
        cc = _cohort_comparison_section(labelled)
        assert cc["winner"]["label"] == "winner"
        assert "significant" in cc["winner"]["reason"]

    def test_no_winner_when_top_two_are_close(self):
        labelled = [
            ("a", _rep("a", {"qa": 0.75}, n_per_type=15)),
            ("b", _rep("b", {"qa": 0.73}, n_per_type=15)),
            ("c", _rep("c", {"qa": 0.40}, n_per_type=15)),
        ]
        cc = _cohort_comparison_section(labelled)
        assert cc["winner"]["label"] is None
        assert "not significant" in cc["winner"]["reason"]


class TestBuildInsightsWiring:
    def test_cohort_kwarg_populates_and_validates(self):
        cur = _rep("v3", {"qa": 0.5, "rag": 0.3})
        v1 = _rep("v1", {"qa": 0.95, "rag": 0.7})
        v2 = _rep("v2", {"qa": 0.8, "rag": 0.6})
        ins = build_insights(cur, cohort=[v1, v2])
        assert ins["cohort_comparison"] is not None
        assert ins["cohort_comparison"]["n_versions"] == 3
        json.dumps(ins)

        from pathlib import Path
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_no_cohort_kwarg_leaves_it_null(self):
        assert build_insights(_rep("v1", {"qa": 0.9}))["cohort_comparison"] is None

    def test_current_label_from_lineage_and_dedupe(self):
        cur = _rep("v3", {"qa": 0.5})
        dupe = _rep("v3", {"qa": 0.6})       # same agent_version
        cc = build_insights(cur, cohort=[dupe])["cohort_comparison"]
        labels = [v["label"] for v in cc["versions"]]
        assert labels[0] == "v3" and labels[1] == "v3#2"
