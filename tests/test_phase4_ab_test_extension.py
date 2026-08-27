"""
tests/test_phase4_ab_test_extension.py
=========================================
Phase 4(개선 엔진) — QuickEval.ab_test() 확장(지표 일반화·Guardrail Metric·효과크기·
표본크기 경고)의 회귀 테스트. 기본 호출(metric 생략)은 이전 동작과 100% 동일해야
한다(tests/test_v079_gaps.py::TestQuickEvalAbTest가 이미 그 하위호환을 검증).
"""
from __future__ import annotations

from typing import cast

import pytest

from agent_evaluator import QuickEval, create_taskresult


def _qeval(tmp_path, name, scores, latencies=None):
    qe = QuickEval(str(tmp_path / name))
    latencies = latencies or [1.0] * len(scores)
    for i, (score, lat) in enumerate(zip(scores, latencies)):
        qe._monitor.record_task(create_taskresult(
            task_id=f"{name}_{i}", question="q", response="r",
            accuracy_score=score, execution_time=lat, extra={},
        ))
    return qe


class TestMetricGeneralization:
    def test_default_metric_is_accuracy_score(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.9, 0.9])
        b = _qeval(tmp_path, "b", [0.5, 0.5, 0.5])
        result = a.ab_test(b)
        assert result["metric"] == "accuracy_score"
        assert result["self_mean"] == pytest.approx(0.9)

    def test_custom_attribute_metric(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 3, latencies=[1.0, 1.0, 1.0])
        b = _qeval(tmp_path, "b", [0.9] * 3, latencies=[3.0, 3.0, 3.0])
        result = a.ab_test(b, metric="execution_time")
        assert result["self_mean"] == pytest.approx(1.0)
        assert result["other_mean"] == pytest.approx(3.0)
        # ab_test()는 지표의 "좋은 방향"을 모른다 — delta=self-other=-2.0이므로
        # better="other"가 된다(direction 판단은 guardrails에서만 명시적으로 함).
        assert result["better"] == "other"

    def test_custom_extra_field_metric(self, tmp_path):
        a = QuickEval(str(tmp_path / "a"))
        b = QuickEval(str(tmp_path / "b"))
        for i, cost in enumerate([0.01, 0.02]):
            a._monitor.record_task(create_taskresult(
                task_id=f"a{i}", question="q", response="r", accuracy_score=0.9,
                execution_time=1.0, extra={"custom_cost": cost},
            ))
        for i, cost in enumerate([0.05, 0.06]):
            b._monitor.record_task(create_taskresult(
                task_id=f"b{i}", question="q", response="r", accuracy_score=0.9,
                execution_time=1.0, extra={"custom_cost": cost},
            ))
        result = a.ab_test(b, metric="custom_cost")
        assert result["self_mean"] == pytest.approx(0.015)
        assert result["other_mean"] == pytest.approx(0.055)

    def test_missing_metric_values_are_skipped_not_zero_filled(self, tmp_path):
        """extra에 없는 커스텀 지표는 0.0으로 채워지면 안 되고 건너뛰어야 한다 —
        0.0으로 채우면 실제로 안 잰 태스크가 '최악의 값'으로 잘못 집계된다."""
        a = QuickEval(str(tmp_path / "a"))
        a._monitor.record_task(create_taskresult(
            task_id="a0", question="q", response="r", accuracy_score=0.9,
            execution_time=1.0, extra={"custom_cost": 0.5},
        ))
        a._monitor.record_task(create_taskresult(
            task_id="a1", question="q", response="r", accuracy_score=0.9,
            execution_time=1.0, extra={},  # custom_cost 없음
        ))
        b = _qeval(tmp_path, "b", [0.9])
        result = a.ab_test(b, metric="custom_cost")
        assert result["sample_sizes"]["self"] == 1  # 2가 아니라 1(누락분 제외)
        assert result["self_mean"] == pytest.approx(0.5)  # 0.25가 아님


class TestEffectSizeAndSignificance:
    def test_effect_size_present_with_enough_samples(self, tmp_path):
        pytest.importorskip("scipy")
        a = _qeval(tmp_path, "a", [0.9, 0.85, 0.95, 0.88, 0.92])
        b = _qeval(tmp_path, "b", [0.5, 0.45, 0.55, 0.48, 0.52])
        result = a.ab_test(b)
        assert result["effect_size_cohens_d"] is not None
        assert result["effect_size_cohens_d"] > 0  # self가 확실히 더 높음

    def test_identical_distributions_yield_small_effect_size(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.7, 0.7, 0.7, 0.7])
        b = _qeval(tmp_path, "b", [0.7, 0.7, 0.7, 0.7])
        result = a.ab_test(b)
        assert result["delta"] == 0.0


class TestSampleSizeWarning:
    def test_small_sample_triggers_warning(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.8])
        b = _qeval(tmp_path, "b", [0.5, 0.4])
        result = a.ab_test(b, min_recommended_samples=30)
        assert result["sample_size_warning"] is not None
        assert "2" in result["sample_size_warning"]

    def test_large_sample_no_warning(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 35)
        b = _qeval(tmp_path, "b", [0.5] * 35)
        result = a.ab_test(b, min_recommended_samples=30)
        assert result["sample_size_warning"] is None


class TestGuardrailMetrics:
    def test_no_guardrails_yields_none_passed(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9])
        b = _qeval(tmp_path, "b", [0.5])
        result = a.ab_test(b)
        assert result["guardrail_results"] == []
        assert result["guardrails_passed"] is None

    def test_guardrail_passes_within_allowed_regression(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.9], latencies=[1.1, 1.1])
        b = _qeval(tmp_path, "b", [0.5, 0.5], latencies=[1.0, 1.0])
        result = a.ab_test(b, guardrails=[
            {"metric": "execution_time", "direction": "lower_is_better", "max_regression": 0.5},
        ])
        assert result["guardrails_passed"] is True
        assert result["guardrail_results"][0]["passed"] is True

    def test_guardrail_fails_when_regression_exceeds_allowance(self, tmp_path):
        """accuracy가 크게 개선돼도(주 지표), latency가 허용치를 넘으면 전체 실패."""
        a = _qeval(tmp_path, "a", [0.95, 0.95], latencies=[5.0, 5.0])
        b = _qeval(tmp_path, "b", [0.5, 0.5], latencies=[1.0, 1.0])
        result = a.ab_test(b, guardrails=[
            {"metric": "execution_time", "direction": "lower_is_better", "max_regression": 0.5},
        ])
        assert result["better"] == "self"  # 주 지표(accuracy)는 self가 압승
        assert result["guardrails_passed"] is False  # 그런데도 guardrail이 막는다
        assert result["guardrail_results"][0]["passed"] is False

    def test_higher_is_better_guardrail_direction(self, tmp_path):
        a = QuickEval(str(tmp_path / "a"))
        b = QuickEval(str(tmp_path / "b"))
        for i in range(2):
            a._monitor.record_task(create_taskresult(
                task_id=f"a{i}", question="q", response="r", accuracy_score=0.9,
                execution_time=1.0, extra={"safety_score": 0.3},  # 크게 하락
            ))
            b._monitor.record_task(create_taskresult(
                task_id=f"b{i}", question="q", response="r", accuracy_score=0.5,
                execution_time=1.0, extra={"safety_score": 0.9},
            ))
        result = a.ab_test(b, guardrails=[
            {"metric": "safety_score", "direction": "higher_is_better", "max_regression": 0.1},
        ])
        assert result["guardrails_passed"] is False

    def test_missing_direction_raises_value_error(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9])
        b = _qeval(tmp_path, "b", [0.5])
        with pytest.raises(ValueError, match="direction"):
            a.ab_test(b, guardrails=[{"metric": "execution_time", "max_regression": 0.5}])

    def test_invalid_direction_raises_value_error(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9])
        b = _qeval(tmp_path, "b", [0.5])
        with pytest.raises(ValueError, match="direction"):
            a.ab_test(b, guardrails=[
                {"metric": "execution_time", "direction": "sideways", "max_regression": 0.5},
            ])


class TestBenjaminiHochberg:
    """R의 p.adjust(method="BH")로 검증된 참조값과 대조 — 새 통계를 발명하지 않고
    표준 절차를 그대로 구현했는지 확인한다."""

    def test_reference_values_evenly_spaced(self):
        from agent_evaluator.quick_eval import _benjamini_hochberg
        result = _benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05])
        assert result == pytest.approx([0.05, 0.05, 0.05, 0.05, 0.05])

    def test_reference_values_mixed(self):
        from agent_evaluator.quick_eval import _benjamini_hochberg
        # R: p.adjust(c(0.005,0.011,0.02,0.04,0.13), "BH")
        # -> 0.025 0.0275 0.03333333 0.05 0.13
        result = _benjamini_hochberg([0.005, 0.011, 0.02, 0.04, 0.13])
        assert result == pytest.approx([0.025, 0.0275, 0.033333, 0.05, 0.13], abs=1e-4)

    def test_none_entries_preserved_and_excluded_from_ranking(self):
        from agent_evaluator.quick_eval import _benjamini_hochberg
        result = _benjamini_hochberg([0.01, None, 0.03])
        assert result[1] is None
        # m=2(None 제외): rank1(0.01)=min(rank2, 0.01*2/1=0.02), rank2(0.03)=0.03*2/2=0.03
        assert result[0] == pytest.approx(0.02)
        assert result[2] == pytest.approx(0.03)

    def test_all_none_returns_all_none(self):
        from agent_evaluator.quick_eval import _benjamini_hochberg
        assert _benjamini_hochberg([None, None]) == [None, None]

    def test_monotonic_non_decreasing_when_sorted_by_raw_p(self):
        from agent_evaluator.quick_eval import _benjamini_hochberg
        raw = [0.2, 0.001, 0.15, 0.03, 0.001]
        adjusted = _benjamini_hochberg(raw)
        assert all(v is not None for v in adjusted)  # raw has no None inputs
        adjusted_floats = cast("list[float]", adjusted)
        pairs = sorted(zip(raw, adjusted_floats), key=lambda pair: pair[0])
        adj_in_raw_order = [p[1] for p in pairs]
        assert adj_in_raw_order == sorted(adj_in_raw_order)


class TestAbTestNway:
    def test_requires_at_least_two_variants(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.9, 0.9])
        with pytest.raises(ValueError, match="at least 2"):
            QuickEval.ab_test_nway({"a": a})

    def test_three_way_returns_all_pairwise_combinations(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 10)
        b = _qeval(tmp_path, "b", [0.5] * 10)
        c = _qeval(tmp_path, "c", [0.7] * 10)
        result = QuickEval.ab_test_nway({"a": a, "b": b, "c": c})
        pairs = {(p["a"], p["b"]) for p in result["pairwise"]}
        assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}
        assert len(result["pairwise"]) == 3

    def test_variant_stats_report_mean_and_n(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.8, 1.0])
        b = _qeval(tmp_path, "b", [0.1, 0.2, 0.3])
        result = QuickEval.ab_test_nway({"a": a, "b": b})
        assert result["variant_stats"]["a"] == {"mean": pytest.approx(0.9), "n": 3}
        assert result["variant_stats"]["b"] == {"mean": pytest.approx(0.2), "n": 3}

    def test_better_field_points_to_higher_mean_variant(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 5)
        b = _qeval(tmp_path, "b", [0.2] * 5)
        result = QuickEval.ab_test_nway({"a": a, "b": b})
        assert result["pairwise"][0]["better"] == "a"

    def test_fdr_adjusted_pvalue_present_and_geq_raw(self, tmp_path):
        pytest.importorskip("scipy")
        import random
        rng = random.Random(42)
        a = _qeval(tmp_path, "a", [0.5 + rng.uniform(-0.05, 0.05) for _ in range(40)])
        b = _qeval(tmp_path, "b", [0.5 + rng.uniform(-0.05, 0.05) for _ in range(40)])
        c = _qeval(tmp_path, "c", [0.5 + rng.uniform(-0.05, 0.05) for _ in range(40)])
        result = QuickEval.ab_test_nway({"a": a, "b": b, "c": c})
        for entry in result["pairwise"]:
            if entry["p_value"] is not None:
                assert entry["p_value_fdr_adjusted"] >= entry["p_value"] - 1e-9

    def test_sample_size_warning_lists_variant_name(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 3)
        b = _qeval(tmp_path, "b", [0.5] * 40)
        result = QuickEval.ab_test_nway({"a": a, "b": b}, min_recommended_samples=30)
        assert any("'a'" in w for w in result["sample_size_warnings"])
        assert not any("'b'" in w for w in result["sample_size_warnings"])

    def test_fdr_method_and_alpha_reported(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 5)
        b = _qeval(tmp_path, "b", [0.5] * 5)
        result = QuickEval.ab_test_nway({"a": a, "b": b}, fdr_alpha=0.1)
        assert result["fdr_method"] == "benjamini_hochberg"
        assert result["fdr_alpha"] == 0.1

    def test_custom_metric_passed_through(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 3, latencies=[1.0, 1.0, 1.0])
        b = _qeval(tmp_path, "b", [0.9] * 3, latencies=[3.0, 3.0, 3.0])
        result = QuickEval.ab_test_nway({"a": a, "b": b}, metric="execution_time")
        assert result["metric"] == "execution_time"
        assert result["variant_stats"]["a"]["mean"] == pytest.approx(1.0)
        assert result["variant_stats"]["b"]["mean"] == pytest.approx(3.0)
