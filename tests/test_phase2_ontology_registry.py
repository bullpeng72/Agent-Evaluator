"""
tests/test_phase2_ontology_registry.py
=========================================
Phase 2(확장성 인프라) — ontology/metric_registry.py 및 이를 소비하도록 리팩터된
세 곳(_build_recommendations, explain_anomaly_event, _summarize_violations)의
회귀 테스트. 리팩터 전후로 출력이 완전히 동일해야 한다(동작 변경 없음, 통합만 목적).
"""
from __future__ import annotations

from agent_evaluator.ontology.metric_registry import (
    ANOMALY_METRIC_DEFAULT_SUGGESTION,
    ANOMALY_METRIC_SUGGESTIONS,
    GATE_GUIDANCE,
    NATIVE_METRIC_RULES,
    VIOLATION_TYPES,
    evaluate_native_metric_rules,
)


class TestRegistryCompleteness:
    def test_gate_guidance_covers_all_seven_gates(self):
        assert set(GATE_GUIDANCE.keys()) == set("ABCDEFG")

    def test_violation_types_match_sqlite_backend_formatters(self):
        from agent_evaluator.storage.sqlite_backend import _VIOLATION_FORMATTERS
        assert set(VIOLATION_TYPES) == set(_VIOLATION_FORMATTERS.keys())

    def test_native_metric_rules_cover_original_four_metrics(self):
        assert {r.metric for r in NATIVE_METRIC_RULES} == {
            "tcr", "accuracy", "hallucination_rate", "latency",
        }

    def test_anomaly_suggestions_cover_original_three_metrics(self):
        assert set(ANOMALY_METRIC_SUGGESTIONS.keys()) == {"accuracy", "latency", "error_rate"}


class TestEvaluateNativeMetricRules:
    def test_all_healthy_yields_no_violations(self):
        violated = evaluate_native_metric_rules(
            tcr=90.0, accuracy=85.0, hallucination_rate=0.05, latency=1.0,
        )
        assert violated == []

    def test_low_tcr_violates_in_original_order(self):
        violated = evaluate_native_metric_rules(
            tcr=50.0, accuracy=50.0, hallucination_rate=0.5, latency=10.0,
        )
        # 원본 코드의 순서(tcr, accuracy, hallucination_rate, latency) 그대로 보존
        assert [r.metric for r in violated] == ["tcr", "accuracy", "hallucination_rate", "latency"]

    def test_exact_boundary_not_violated(self):
        # 원본은 엄격 부등호(< / >)였다 — 경계값 자체는 위반 아님
        violated = evaluate_native_metric_rules(
            tcr=75.0, accuracy=70.0, hallucination_rate=0.2, latency=5.0,
        )
        assert violated == []


class TestBuildRecommendationsUsesRegistry:
    def test_gate_fail_uses_registry_label_and_guidance(self):
        from agent_evaluator.reporting.comprehensive_report import _build_recommendations

        harness_groups = {"E": {"status": "fail"}}
        html = _build_recommendations(
            harness_groups, tcr=90, acc=90, hall_rate=0.0, latency=1.0, quality_metrics={},
        )
        assert GATE_GUIDANCE["E"].label in html
        assert GATE_GUIDANCE["E"].guidance in html
        assert "FAIL" in html

    def test_all_healthy_yields_healthy_message(self):
        from agent_evaluator.reporting.comprehensive_report import _build_recommendations

        html = _build_recommendations(
            {}, tcr=90, acc=90, hall_rate=0.0, latency=1.0, quality_metrics={},
        )
        assert "All metrics healthy" in html

    def test_low_latency_metric_rule_renders(self):
        from agent_evaluator.reporting.comprehensive_report import _build_recommendations

        html = _build_recommendations(
            {}, tcr=90, acc=90, hall_rate=0.0, latency=10.0, quality_metrics={},
        )
        assert "Response Latency Improvement Needed" in html
        assert "priority-medium" in html


class TestSummarizeViolationsAllTypes:
    """_summarize_violations는 리팩터 전 직접 테스트가 없었다 — 7개 유형 전체를 처음 커버."""

    def _summarize(self, extra):
        from agent_evaluator.storage.sqlite_backend import _summarize_violations
        return _summarize_violations(extra)

    def test_no_violations_returns_none(self):
        assert self._summarize({}) is None

    def test_loop_detection(self):
        result = self._summarize({"loop_detection": {"detected": True, "detected_loops": [
            {"loop_type": "consecutive", "loop_tool": "search"},
        ]}})
        assert result == "loop_detection: consecutive:search"

    def test_deadlock(self):
        result = self._summarize({"deadlock": {"detected": True, "deadlock_type": "circular"}})
        assert result == "deadlock: circular"

    def test_scope(self):
        result = self._summarize({"scope": {"violations": ["forbidden_tool_used"]}})
        assert result == "scope: forbidden_tool_used"

    def test_tool_parameter_safety(self):
        result = self._summarize({"tool_parameter_safety": {"violations": ["dangerous_pattern"]}})
        assert result == "tool_parameter_safety: dangerous_pattern"

    def test_tool_authorization(self):
        result = self._summarize({"tool_authorization": {
            "total_violations": 2, "unauthorized_calls": 1,
            "restricted_calls": 1, "dangerous_param_calls": 0,
        }})
        assert result == (
            "tool_authorization: 2 violations "
            "(unauthorized=1, restricted=1, dangerous_params=0)"
        )

    def test_privilege_escalation(self):
        result = self._summarize({"privilege_escalation": {
            "escalation_detected": True, "initial_privilege": "user", "max_privilege": "admin",
        }})
        assert result == "privilege_escalation: user -> admin"

    def test_tool_chain_attack(self):
        result = self._summarize({"tool_chain_attack": {
            "is_suspicious_chain": True, "attack_patterns_detected": ["read_then_exfiltrate"],
        }})
        assert result == "tool_chain_attack: read_then_exfiltrate"

    def test_multiple_violations_joined_with_pipe(self):
        result = self._summarize({
            "deadlock": {"detected": True, "deadlock_type": "circular"},
            "scope": {"violations": ["forbidden_tool_used"]},
        })
        assert result == "deadlock: circular | scope: forbidden_tool_used"

    def test_falsy_dict_no_violation_excluded(self):
        assert self._summarize({"loop_detection": {"detected": False}}) is None


class TestExplainAnomalyEventUsesRegistry:
    def test_known_metric_uses_registry_suggestion(self):
        assert ANOMALY_METRIC_SUGGESTIONS["accuracy"] == (
            "Accuracy is low. Consider improving prompts or upgrading the model."
        )

    def test_unknown_metric_falls_back_to_default(self):
        result = ANOMALY_METRIC_SUGGESTIONS.get("unknown_metric", ANOMALY_METRIC_DEFAULT_SUGGESTION)
        assert result == ANOMALY_METRIC_DEFAULT_SUGGESTION
