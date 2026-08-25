"""
tests/test_phase4_mast_taxonomy.py
=====================================
Phase 4(개선 엔진, 추천 v1) — ontology/mast_taxonomy.py(외부 검증 taxonomy)와
rca/diagnose.py의 Gate F 연결 회귀 테스트.

MAST_FAILURE_MODES의 14개 항목·코드·prevalence_pct는 논문 Figure 1을 직접 읽어
옮긴 값이다(Cemri et al., NeurIPS 2025, arXiv:2503.13657v3) — 이 테스트는 그 옮겨
적은 값이 정확한지(14개, 3범주, 합계 등)를 구조적으로 검증한다.
"""
from __future__ import annotations

from agent_evaluator.ontology.mast_taxonomy import (
    MAST_FAILURE_MODES,
    mast_failure_mode_by_code,
    mast_failure_modes_for_gate_f_metric,
)
from agent_evaluator.rca import diagnose


class TestMastTaxonomyStructure:
    def test_exactly_fourteen_modes(self):
        assert len(MAST_FAILURE_MODES) == 14

    def test_three_categories(self):
        assert {m.category for m in MAST_FAILURE_MODES} == {
            "system_design_issues", "inter_agent_misalignment", "task_verification",
        }

    def test_category_counts_match_paper_figure_1(self):
        by_cat: dict[str, int] = {}
        for m in MAST_FAILURE_MODES:
            by_cat[m.category] = by_cat.get(m.category, 0) + 1
        assert by_cat == {
            "system_design_issues": 5, "inter_agent_misalignment": 6, "task_verification": 3,
        }

    def test_all_codes_unique(self):
        codes = [m.code for m in MAST_FAILURE_MODES]
        assert len(codes) == len(set(codes))

    def test_prevalence_within_each_category_sums_to_reported_total(self):
        """논문 Figure 1의 범주별 합계(44.2% / 32.3% / 23.5%)와 개별 항목 합이 일치."""
        sums = {
            "system_design_issues": 44.2,
            "inter_agent_misalignment": 32.3,
            "task_verification": 23.5,
        }
        for cat, expected in sums.items():
            total = sum(m.prevalence_pct for m in MAST_FAILURE_MODES if m.category == cat)
            assert abs(total - expected) < 0.2  # 반올림 오차 허용

    def test_lookup_by_code(self):
        mode = mast_failure_mode_by_code("2.6")
        assert mode is not None
        assert mode.name == "Reasoning-Action Mismatch"

    def test_lookup_by_unknown_code_returns_none(self):
        assert mast_failure_mode_by_code("9.9") is None


class TestMastFilterByGateFMetric:
    def test_consensus_returns_only_consensus_related(self):
        modes = mast_failure_modes_for_gate_f_metric("consensus")
        assert all(m.related_gate_f_metric == "consensus" for m in modes)
        assert len(modes) >= 1

    def test_unmapped_metric_returns_empty(self):
        assert mast_failure_modes_for_gate_f_metric("nonexistent") == ()


class TestRcaGateFMastIntegration:
    def _report(self, harness_groups):
        return {"extra_metrics": {"harness_groups": harness_groups}}

    def _gate(self, score, **details):
        return {"score": score, "status": "pass", "gate": "pass", "details": details}

    def test_gate_f_finding_includes_mast_candidates(self):
        current = self._report({
            "F": self._gate(0.3, avg_consensus=0.2, avg_propagation=0.9),
        })
        baseline = self._report({
            "F": self._gate(0.8, avg_consensus=0.9, avg_propagation=0.9),
        })
        result = diagnose(current, baseline, regression_threshold=0.1)
        finding = result["findings"][0]
        assert finding["gate"] == "F"
        assert "mast_candidates" in finding
        codes = {m["code"] for m in finding["mast_candidates"]}
        assert "2.2" in codes  # Fail to Ask for Clarification — related_gate_f_metric="consensus"

    def test_non_gate_f_finding_has_no_mast_key(self):
        current = self._report({"A": self._gate(0.3)})
        baseline = self._report({"A": self._gate(0.8)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert "mast_candidates" not in result["findings"][0]

    def test_gate_f_with_unmapped_top_field_yields_empty_candidates(self):
        current = self._report({"F": self._gate(0.3, coordination_score=0.2)})
        baseline = self._report({"F": self._gate(0.8, coordination_score=0.9)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        # coordination_score는 _GATE_F_FIELD_TO_MAST_METRIC에 없음 — 빈 리스트, 에러 아님
        assert result["findings"][0]["mast_candidates"] == []
