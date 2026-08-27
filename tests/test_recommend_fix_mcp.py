"""
tests/test_recommend_fix_mcp.py
====================================
``agent_evaluator.integrations.recommend_fix_mcp`` — ``recommend_fix`` MCP 도구.

새 판정 로직이 없는 정적 지식 조회이므로, 여기서는 ① ontology 데이터
(GATE_GUIDANCE/NATIVE_METRIC_RULES/ANOMALY_METRIC_SUGGESTIONS/mast_taxonomy)를
올바르게 읽어 오는지, ② 잘못된 입력(존재하지 않는 Gate)을 지어내지 않고
명시적으로 알리는지, ③ FastMCP 서버가 정상적으로 빌드되는지만 확인한다.
"""
from __future__ import annotations

import pytest

from agent_evaluator.integrations.recommend_fix_mcp import (
    build_server,
    format_recommendation,
)
from agent_evaluator.ontology.metric_registry import GATE_GUIDANCE


class TestFormatRecommendationGateLevel:
    @pytest.mark.parametrize("gate", list("ABCDEFG"))
    def test_valid_gate_returns_guidance(self, gate):
        text = format_recommendation(gate, None, None)
        assert GATE_GUIDANCE[gate].label in text
        assert GATE_GUIDANCE[gate].guidance in text

    def test_lowercase_gate_is_normalized(self):
        text = format_recommendation("a", None, None)
        assert GATE_GUIDANCE["A"].label in text

    def test_whitespace_is_stripped(self):
        text = format_recommendation("  D  ", None, None)
        assert GATE_GUIDANCE["D"].label in text

    def test_invalid_gate_does_not_fabricate(self):
        text = format_recommendation("Z", None, None)
        assert "유효한 Gate가 아닙니다" in text
        # 존재하지 않는 Gate에 대해 GATE_GUIDANCE 내용을 지어내지 않는다
        for g in GATE_GUIDANCE.values():
            assert g.guidance not in text

    def test_always_ends_with_hotl_disclaimer(self):
        text = format_recommendation("A", None, None)
        assert "사람의 몫" in text or "사람이" in text


class TestFormatRecommendationWithMetric:
    def test_native_metric_rule_matched(self):
        text = format_recommendation("D", "latency", None)
        assert "Response Latency Improvement Needed" in text

    def test_value_violates_threshold(self):
        text = format_recommendation("D", "latency", 6.2)
        assert "위반" in text

    def test_value_within_threshold(self):
        text = format_recommendation("D", "latency", 1.0)
        assert "정상 범위" in text

    def test_anomaly_suggestion_matched(self):
        # SPEC-041: canonical "error_rate" → AnomalyEvent.type "error_surge" 제안으로 연결.
        text = format_recommendation("A", "error_rate", None)
        assert "[이상탐지 참고]" in text
        assert "Error rate has surged" in text

    def test_unknown_metric_says_no_specific_rule(self):
        text = format_recommendation("A", "totally_made_up_metric", None)
        assert "세부 규칙은 없습니다" in text
        # 그래도 Gate 레벨 안내는 여전히 나온다
        assert GATE_GUIDANCE["A"].label in text

    def test_gate_f_metric_surfaces_mast_candidates(self):
        text = format_recommendation("F", "conflict_resolution", None)
        assert "MAST" in text
        assert "Cemri et al" in text
        assert "% of paper traces" in text

    def test_gate_f_unmatched_metric_falls_back_to_no_rule_message(self):
        text = format_recommendation("F", "not_a_real_mast_metric", None)
        assert "세부 규칙은 없습니다" in text

    def test_no_metric_given_omits_metric_specific_sections(self):
        text = format_recommendation("D", None, None)
        assert "Response Latency Improvement Needed" not in text


class TestFormatRecommendationMetricNameNormalization:
    """SPEC-041: rca.diagnose()가 주는 필드명(hall_rate, avg_role_compliance,
    p95_latency_ms, tcr_pct …)을 canonical 규칙 키로 정규화해, 두 MCP 도구가 같은
    어휘를 쓰게 한다 — 예전엔 "규칙이 있는데 없다"고 답했다."""

    def test_hall_rate_maps_to_hallucination_rule(self):
        # SPEC-041: hallucination_rate는 퍼센트(0-100) 규약 — 35%는 20% 임계값 초과.
        text = format_recommendation("C", "hall_rate", 35.0)
        assert "High Hallucination Risk" in text
        assert "위반" in text
        assert "'hall_rate' → 'hallucination_rate'" in text

    def test_hall_rate_low_percent_is_within_range(self):
        text = format_recommendation("C", "hall_rate", 3.0)  # 3% < 20%
        assert "정상 범위" in text

    def test_p95_latency_ms_maps_to_latency_rule(self):
        text = format_recommendation("D", "p95_latency_ms")
        assert "Response Latency Improvement Needed" in text

    def test_tcr_pct_maps_to_tcr_rule(self):
        text = format_recommendation("A", "tcr_pct", 60.0)
        assert "TCR Improvement Needed" in text

    def test_gate_f_avg_role_compliance_maps_to_role_adherence_mast(self):
        text = format_recommendation("F", "avg_role_compliance")
        assert "MAST" in text
        assert "Disobey Role Specification" in text  # 1.2, related_gate_f_metric=role_adherence

    def test_already_canonical_name_unchanged_and_no_interpretation_note(self):
        text = format_recommendation("D", "latency")
        assert "Response Latency Improvement Needed" in text
        assert "→ 'latency'" not in text  # 이미 canonical이라 해석 안내 없음

    def test_truly_unknown_metric_still_says_no_rule(self):
        text = format_recommendation("B", "some_made_up_field")
        assert "세부 규칙은 없습니다" in text


class TestBuildServer:
    def test_server_builds_with_expected_name(self):
        pytest.importorskip("mcp")
        server = build_server()
        assert server.name == "agent-evaluator-recommend-fix"
