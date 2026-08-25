"""
tests/test_phase4_verify_recommendation.py
=============================================
Phase 4(개선 엔진, 폐루프 학습) — rca.verify_recommendation_outcome()의 회귀 테스트.
"""
from __future__ import annotations

from agent_evaluator.rca import verify_recommendation_outcome


def _report(harness_groups: dict) -> dict:
    return {"extra_metrics": {"harness_groups": harness_groups}}


def _gate(score, **details):
    return {"score": score, "status": "pass", "gate": "pass", "details": details}


class TestVerdicts:
    def test_confirmed_when_improved_beyond_threshold(self):
        before = _report({"F": _gate(0.5)})
        after = _report({"F": _gate(0.8)})
        result = verify_recommendation_outcome(before, after, target_gate="F")
        assert result["verdict"] == "confirmed"
        assert result["gate_delta"] == 0.3

    def test_refuted_when_worsened_beyond_threshold(self):
        before = _report({"F": _gate(0.8)})
        after = _report({"F": _gate(0.5)})
        result = verify_recommendation_outcome(before, after, target_gate="F")
        assert result["verdict"] == "refuted"

    def test_inconclusive_when_change_within_noise_threshold(self):
        before = _report({"F": _gate(0.70)})
        after = _report({"F": _gate(0.72)})
        result = verify_recommendation_outcome(
            before, after, target_gate="F", improvement_threshold=0.05,
        )
        assert result["verdict"] == "inconclusive"

    def test_inconclusive_when_score_missing_in_either_report(self):
        before = _report({"F": _gate(0.5)})
        after = _report({})  # F not measured after
        result = verify_recommendation_outcome(before, after, target_gate="F")
        assert result["verdict"] == "inconclusive"
        assert result["gate_delta"] is None
        assert "reason" in result

    def test_exact_boundary_at_threshold_counts_as_confirmed(self):
        before = _report({"F": _gate(0.5)})
        after = _report({"F": _gate(0.55)})
        result = verify_recommendation_outcome(
            before, after, target_gate="F", improvement_threshold=0.05,
        )
        assert result["verdict"] == "confirmed"


class TestTargetFieldResult:
    def test_target_field_delta_reported_when_present_in_both(self):
        before = _report({"F": _gate(0.5, avg_consensus=0.4)})
        after = _report({"F": _gate(0.8, avg_consensus=0.9)})
        result = verify_recommendation_outcome(
            before, after, target_gate="F", target_field="avg_consensus",
        )
        assert result["target_field_result"] == {
            "field": "avg_consensus", "before": 0.4, "after": 0.9, "delta": 0.5,
        }

    def test_target_field_none_when_not_specified(self):
        before = _report({"F": _gate(0.5)})
        after = _report({"F": _gate(0.8)})
        result = verify_recommendation_outcome(before, after, target_gate="F")
        assert result["target_field_result"] is None

    def test_target_field_none_when_missing_in_either_report(self):
        before = _report({"F": _gate(0.5)})  # avg_consensus 없음
        after = _report({"F": _gate(0.8, avg_consensus=0.9)})
        result = verify_recommendation_outcome(
            before, after, target_gate="F", target_field="avg_consensus",
        )
        assert result["target_field_result"] is None

    def test_gate_verdict_independent_of_missing_field_data(self):
        """target_field 값이 없어도 Gate 점수 자체는 판정 가능해야 한다."""
        before = _report({"F": _gate(0.5)})
        after = _report({"F": _gate(0.8)})
        result = verify_recommendation_outcome(
            before, after, target_gate="F", target_field="nonexistent_field",
        )
        assert result["verdict"] == "confirmed"
        assert result["target_field_result"] is None


class TestCustomGateSupport:
    def test_works_with_registered_custom_gate_id(self):
        """register_gate()로 추가된 Gate("COST" 등)에도 그대로 동작해야 한다."""
        before = _report({"COST": _gate(0.4)})
        after = _report({"COST": _gate(0.7)})
        result = verify_recommendation_outcome(before, after, target_gate="COST")
        assert result["verdict"] == "confirmed"
