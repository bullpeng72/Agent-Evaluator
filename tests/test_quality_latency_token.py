"""
tests/test_quality_latency_token.py
=====================================
ResponseQualityEvaluator / LatencyTracker / TokenEconomyTracker 테스트
"""
import pytest

from agent_evaluator.core.trackers.layer1 import (
    ResponseQualityEvaluator,
    LatencyTracker,
    TokenEconomyTracker,
    _QUALITY_SCORE_MAX,
    _TCR_EXCELLENT,
    _TCR_GOOD,
    _TCR_ACCEPTABLE,
    _TCR_PARTIAL_THRESHOLD,
)
from agent_evaluator.exceptions import ValidationError


# ===========================================================================
# ResponseQualityEvaluator
# ===========================================================================

class TestResponseQualityEvaluator:
    def test_basic_evaluate_returns_score(self):
        ev = ResponseQualityEvaluator()
        result = ev.evaluate_response(
            task_id="t1",
            response="서울은 대한민국의 수도입니다.",
            request="한국의 수도는?",
            expected_elements=["서울"],
        )
        assert "total_score" in result
        assert 0.0 <= result["total_score"] <= _QUALITY_SCORE_MAX

    def test_scores_within_range(self):
        ev = ResponseQualityEvaluator()
        result = ev.evaluate_response(
            task_id="t1",
            response="The capital of France is Paris.",
            request="What is the capital of France?",
            expected_elements=["Paris"],
            ground_truth="Paris",
        )
        for dim in ["relevance", "completeness", "accuracy", "clarity", "usefulness"]:
            assert 0.0 <= result["dimension_scores"][dim] <= _QUALITY_SCORE_MAX, (
                f"{dim} out of range: {result['dimension_scores'][dim]}"
            )

    def test_get_quality_metrics_empty(self):
        ev = ResponseQualityEvaluator()
        assert ev.get_quality_metrics() == {}

    def test_get_quality_metrics_after_eval(self):
        ev = ResponseQualityEvaluator()
        ev.evaluate_response("t1", "Answer here.", "Question?", [])
        metrics = ev.get_quality_metrics()
        assert "dimension_averages" in metrics
        assert "relevance" in metrics["dimension_averages"]
        assert "total_evaluated" in metrics
        assert metrics["total_evaluated"] == 1

    def test_custom_dimensions_accepted(self):
        custom = {
            "relevance": 0.5,
            "completeness": 0.2,
            "accuracy": 0.1,
            "clarity": 0.1,
            "usefulness": 0.1,
        }
        ev = ResponseQualityEvaluator(dimensions=custom)
        assert ev.dimensions["relevance"] == 0.5

    def test_invalid_dimension_weights_raise(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            ResponseQualityEvaluator(
                dimensions={"relevance": 0.5, "completeness": 0.2}
            )

    def test_default_dimensions_unchanged_by_instance(self):
        ev = ResponseQualityEvaluator()
        ev.dimensions["relevance"] = 0.99  # mutate instance copy
        ev2 = ResponseQualityEvaluator()
        assert ev2.dimensions["relevance"] == 0.25  # class constant untouched

    def test_repr(self):
        ev = ResponseQualityEvaluator()
        r = repr(ev)
        assert "ResponseQualityEvaluator" in r
        assert "evaluations=0" in r

    def test_repr_after_eval(self):
        ev = ResponseQualityEvaluator()
        ev.evaluate_response("t1", "answer", "question?", [])
        r = repr(ev)
        assert "evaluations=1" in r


# ===========================================================================
# LatencyTracker
# ===========================================================================

class TestLatencyTracker:
    def test_record_and_get_stats(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 1.2, {"llm": 0.9, "retrieval": 0.3})
        lt.record_latency("t2", "qa", 0.8, {"llm": 0.6, "retrieval": 0.2})
        stats = lt.get_latency_stats()
        assert stats["mean"] == pytest.approx(1.0, rel=1e-3)
        assert stats["min"] == pytest.approx(0.8)
        assert stats["max"] == pytest.approx(1.2)

    def test_get_latency_stats_empty(self):
        lt = LatencyTracker()
        assert lt.get_latency_stats() == {}

    def test_get_latency_stats_by_type(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 1.0, {})
        lt.record_latency("t2", "code", 2.0, {})
        qa_stats = lt.get_latency_stats(task_type="qa")
        assert qa_stats["mean"] == pytest.approx(1.0)
        assert "code" not in str(qa_stats)

    def test_percentile_p95_single_value(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 3.0, {})
        stats = lt.get_latency_stats()
        assert stats["p95"] == pytest.approx(3.0)

    def test_analyze_bottlenecks_empty(self):
        lt = LatencyTracker()
        assert lt.analyze_bottlenecks() == {}

    def test_analyze_bottlenecks_no_breakdown(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 1.0, {})
        result = lt.analyze_bottlenecks()
        assert result["bottleneck"] is None

    def test_analyze_bottlenecks_identifies_slowest(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 1.5, {"llm": 1.0, "retrieval": 0.5})
        result = lt.analyze_bottlenecks()
        assert result["bottleneck"] == "llm"

    def test_check_sla_compliance_passes(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 0.5, {})
        lt.record_latency("t2", "qa", 0.8, {})
        results = lt.check_sla_compliance({"qa": 1.0})
        assert results["qa"]["compliance_rate"] == pytest.approx(100.0)

    def test_check_sla_compliance_partial(self):
        lt = LatencyTracker()
        lt.record_latency("t1", "qa", 0.5, {})
        lt.record_latency("t2", "qa", 2.0, {})  # exceeds 1.0s SLA
        results = lt.check_sla_compliance({"qa": 1.0})
        assert results["qa"]["compliance_rate"] == pytest.approx(50.0)

    def test_repr(self):
        lt = LatencyTracker()
        assert "LatencyTracker(records=0" in repr(lt)
        lt.record_latency("t1", "qa", 2.5, {})
        assert "records=1" in repr(lt)


# ===========================================================================
# TokenEconomyTracker
# ===========================================================================

class TestTokenEconomyTracker:
    _PRICING = {"input": 0.003, "output": 0.015}

    def test_basic_track_and_stats(self):
        tt = TokenEconomyTracker(self._PRICING)
        tt.track_usage("t1", input_tokens=100, output_tokens=50, task_type="qa")
        stats = tt.get_usage_stats()
        assert stats["total_input_tokens"] == 100
        assert stats["total_output_tokens"] == 50
        assert stats["total_cost"] > 0

    def test_get_usage_stats_empty(self):
        tt = TokenEconomyTracker(self._PRICING)
        assert tt.get_usage_stats() == {}

    def test_cost_calculation(self):
        tt = TokenEconomyTracker({"input": 1.0, "output": 2.0})
        tt.track_usage("t1", 1000, 500, "qa")  # 1.0 + 1.0 = 2.0
        stats = tt.get_usage_stats()
        assert stats["total_cost"] == pytest.approx(2.0, rel=1e-4)

    def test_negative_pricing_raises(self):
        with pytest.raises(ValidationError, match="invalid"):
            TokenEconomyTracker({"input": -0.001, "output": 0.015})

    def test_zero_pricing_allowed(self):
        tt = TokenEconomyTracker({"input": 0.0, "output": 0.0})
        tt.track_usage("t1", 100, 50, "qa")
        stats = tt.get_usage_stats()
        assert stats["total_cost"] == pytest.approx(0.0)

    def test_multiple_models_breakdown(self):
        tt = TokenEconomyTracker(self._PRICING)
        tt.track_usage("t1", 100, 50, "qa", model="gpt-4")
        tt.track_usage("t2", 200, 100, "qa", model="claude-3")
        breakdown = tt.get_cost_breakdown_by_model()
        assert "gpt-4" in breakdown
        assert "claude-3" in breakdown

    def test_repr(self):
        tt = TokenEconomyTracker(self._PRICING)
        assert "TokenEconomyTracker(records=0" in repr(tt)
        tt.track_usage("t1", 100, 50, "qa")
        assert "records=1" in repr(tt)
        assert "total_cost=" in repr(tt)


# ===========================================================================
# Constants sanity check
# ===========================================================================

class TestLayerConstants:
    def test_tcr_thresholds_ordered(self):
        assert _TCR_ACCEPTABLE < _TCR_GOOD < _TCR_EXCELLENT

    def test_tcr_partial_threshold_in_range(self):
        assert 0.0 < _TCR_PARTIAL_THRESHOLD < 1.0

    def test_quality_score_max_positive(self):
        assert _QUALITY_SCORE_MAX > 0
