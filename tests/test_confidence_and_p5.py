"""
tests/test_confidence_and_p5.py
==================================
P5 — 통계적 정직성:

1. ``utils.confidence`` 순수 함수 (Wilson interval · 부트스트랩 CI · 표본 수 · 확신도)
2. 리포트 통합 — 헤더 CI · Executive Summary 확신도 배지 · 전 Gate insufficient 경고 ·
   Conclusion Grade 확신도
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.comprehensive_report import (
    _build_score_breakdown,
    generate_comprehensive_html_report,
)
from agent_evaluator.utils.confidence import (
    bootstrap_diff_ci,
    bootstrap_mean_ci,
    mde_two_proportions,
    required_n_for_halfwidth,
    verdict_confidence,
    wilson_interval,
)


class TestWilsonInterval:
    def test_contains_point_estimate(self):
        lo, hi = wilson_interval(7, 10)
        assert lo < 0.7 < hi
        assert 0.0 <= lo <= hi <= 1.0

    def test_extremes_stay_in_bounds(self):
        assert wilson_interval(0, 5) == (0.0, wilson_interval(0, 5)[1])
        lo, hi = wilson_interval(5, 5)
        assert hi <= 1.0 and lo > 0.0  # p=1이어도 상한 1, 하한 0 초과

    def test_zero_n_is_full_range(self):
        assert wilson_interval(0, 0) == (0.0, 1.0)

    def test_wider_with_smaller_n(self):
        w_small = wilson_interval(5, 10)
        w_big = wilson_interval(50, 100)
        assert (w_small[1] - w_small[0]) > (w_big[1] - w_big[0])


class TestBootstrapMeanCI:
    def test_deterministic(self):
        vals = [0.1, 0.5, 0.9, 0.3, 0.7, 0.6, 0.2, 0.8]
        assert bootstrap_mean_ci(vals) == bootstrap_mean_ci(vals)

    def test_brackets_mean(self):
        vals = [0.4, 0.5, 0.6, 0.5, 0.45, 0.55] * 5
        lo, hi = bootstrap_mean_ci(vals)
        assert lo < 0.5 < hi

    def test_tiny_sample_falls_back_to_minmax(self):
        assert bootstrap_mean_ci([0.2, 0.8]) == (0.2, 0.8)
        assert bootstrap_mean_ci([]) == (0.0, 0.0)


class TestRequiredN:
    def test_more_for_tighter_halfwidth(self):
        assert required_n_for_halfwidth(0.5, 0.05) > required_n_for_halfwidth(0.5, 0.10)

    def test_p_half_is_worst_case(self):
        assert required_n_for_halfwidth(0.5, 0.05) >= required_n_for_halfwidth(0.9, 0.05)


class TestMdeTwoProportions:
    def test_smaller_sample_larger_mde(self):
        assert mde_two_proportions(20, 20, 0.5) > mde_two_proportions(400, 400, 0.5)

    def test_zero_sample_returns_none(self):
        assert mde_two_proportions(0, 10) is None

    def test_typical_small_run_is_coarse(self):
        # n=24 per arm can only reliably detect a ~40pp swing at 80% power
        assert 0.30 < mde_two_proportions(24, 24, 0.5) < 0.55


class TestBootstrapDiffCI:
    def test_clear_difference_excludes_zero(self):
        lo, hi = bootstrap_diff_ci([1.0] * 18 + [0.0] * 2, [0.0] * 18 + [1.0] * 2)
        assert lo > 0  # a is clearly higher

    def test_no_difference_spans_zero(self):
        ci = bootstrap_diff_ci([1.0, 0.0] * 15, [1.0, 0.0] * 15)
        assert ci[0] <= 0 <= ci[1]

    def test_too_few_samples_returns_none(self):
        assert bootstrap_diff_ci([1.0, 0.0], [1.0, 0.0, 1.0]) is None

    def test_deterministic(self):
        a, b = [1.0] * 12 + [0.0] * 8, [1.0] * 8 + [0.0] * 12
        assert bootstrap_diff_ci(a, b) == bootstrap_diff_ci(a, b)


class TestVerdictConfidence:
    def test_small_sample_is_low(self):
        level, reasons = verdict_confidence(n_tasks=10)
        assert level == "low"
        assert any("10" in r for r in reasons)

    def test_healthy_is_high(self):
        level, reasons = verdict_confidence(
            n_tasks=200, tcr_ci_halfwidth=0.03, n_gate_components=6, margin_to_threshold=0.2,
        )
        assert level == "high"
        assert reasons == []

    def test_wide_ci_demotes(self):
        level, _ = verdict_confidence(n_tasks=100, tcr_ci_halfwidth=0.35)
        assert level == "low"

    def test_borderline_margin_demotes_to_medium(self):
        level, reasons = verdict_confidence(n_tasks=100, margin_to_threshold=0.02)
        assert level == "medium"
        assert any("threshold" in r for r in reasons)

    def test_lowest_signal_wins(self):
        level, _ = verdict_confidence(
            n_tasks=15, tcr_ci_halfwidth=0.05, n_gate_components=6,
        )
        assert level == "low"  # n_tasks<20 이 지배


class TestReportIntegration:
    def _mon(self, n=18):
        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(n):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q",
                response="모름" if i % 2 else "약 940만명",
                ground_truth="약 940만명", execution_time=1.0, task_type="qa",
            ))
        return m

    def test_header_and_conclusion_show_ci(self):
        html = generate_comprehensive_html_report(self._mon())
        assert "95% CI" in html
        assert "TCR 95% CI:" in html  # conclusion line

    def test_exec_summary_has_confidence_badge(self):
        html = generate_comprehensive_html_report(self._mon(18))
        assert "LOW CONFIDENCE" in html  # 18 tasks → low

    def test_grade_carries_confidence(self):
        html = generate_comprehensive_html_report(self._mon(18))
        seg = html[html.find('id="conclusion"'):]
        assert "confidence" in seg[:600]

    def test_insufficient_warning_rendered_for_any_gate(self):
        hg = {"score": 0.5, "status": "warn", "gate": "warn", "details": {
            "avg_consensus": 0.4, "avg_propagation": 0.5,
            "insufficient_data_warnings": ["consensus: 2 samples < min_samples=5"],
        }}
        html = _build_score_breakdown("F", hg)
        assert "Insufficient data" in html
        assert "min_samples=5" in html
