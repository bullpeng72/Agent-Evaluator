"""
tests/test_gates_gate_d_migration.py
=======================================
SPEC-000: Gate D(Performance Contract) 패키지 이관 검증.

기존 tests/test_decorators_harness.py(280건)는 수정 없이 그대로 통과해야 한다
(re-export 검증). 이 파일은 이관 자체(항등성 + monitor.py 위임 호출과
aggregate.compute() 직접 호출의 동등성)를 검증한다.

주의: 픽스처는 "sla" extra를 포함하지 않는다 — SLA는 아직 이관되지 않은 Gate C
섹션에서 공유 계산되는 데이터이므로, sla_results=[]/penalties=0.0/warning=None을
그대로 aggregate.compute()에 전달해 순수하게 Gate D 자체 로직만 검증한다.
"""
import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra
    )


class TestConfigIdentity:
    def test_sla_config_same_object(self):
        from agent_evaluator.decorators import SLAConfig as C1
        from agent_evaluator.gates.gate_d_performance.configs import SLAConfig as C2
        from agent_evaluator import SLAConfig as C3
        assert C1 is C2 is C3

    def test_efficiency_config_same_object(self):
        from agent_evaluator.decorators import EfficiencyConfig as C1
        from agent_evaluator.gates.gate_d_performance.configs import EfficiencyConfig as C2
        assert C1 is C2

    def test_resource_budget_config_same_object(self):
        from agent_evaluator.decorators import ResourceBudgetConfig as C1
        from agent_evaluator.gates.gate_d_performance.configs import ResourceBudgetConfig as C2
        assert C1 is C2

    def test_ttft_variability_config_same_object(self):
        from agent_evaluator.decorators import TTFTVariabilityConfig as C1
        from agent_evaluator.gates.gate_d_performance.configs import TTFTVariabilityConfig as C2
        assert C1 is C2

    def test_cost_predictability_config_same_object(self):
        from agent_evaluator.decorators import CostPredictabilityConfig as C1
        from agent_evaluator.gates.gate_d_performance.configs import CostPredictabilityConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_sla_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_sla as E1
        from agent_evaluator.gates.gate_d_performance.evaluators import eval_sla as E2
        assert E1 is E2

    def test_eval_efficiency_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_efficiency as E1
        from agent_evaluator.gates.gate_d_performance.evaluators import eval_efficiency as E2
        assert E1 is E2

    def test_eval_resource_budget_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_resource_budget as E1
        from agent_evaluator.gates.gate_d_performance.evaluators import eval_resource_budget as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # efficiency: calibrated_score 3건
    m.record_task(_task("e1", {"efficiency": {"calibrated_score": 1.0, "efficiency_ratio": 0.01, "cost_unit": "usd"}}))
    m.record_task(_task("e2", {"efficiency": {"calibrated_score": 0.8, "efficiency_ratio": 0.02, "cost_unit": "usd"}}))
    m.record_task(_task("e3", {"efficiency": {"calibrated_score": 0.6, "efficiency_ratio": 0.03, "cost_unit": "usd"}}))
    # resource_budget: 3건 (rollover=False)
    for i, score in enumerate([0.9, 0.8, 0.7], start=1):
        m.record_task(_task(f"rb{i}", {"resource_budget": {
            "budget_score": score,
            "_config": {"rollover": False, "max_tokens": 1000, "max_cost_usd": None, "max_execution_time_ms": None},
        }}))
    # ttft_ms: 5건 (min_samples=5 기본값 충족)
    for i, ttft in enumerate([100, 120, 110, 130, 105], start=1):
        m.record_task(_task(f"ttft{i}", {"ttft_ms": ttft}))
    # cost_predictability는 tokens_used 기반 — 태스크 수가 min_samples(5) 미만이면 스킵되므로
    # 위 11개 태스크가 이미 5개 초과라 자동으로 CV 계산 대상(task_type="qa" 전부 동일).
    return m


class TestGateDMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_d_performance import aggregate as gate_d_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        via_monitor = report.extra_metrics["harness_groups"]["D"]

        direct = gate_d_aggregate.compute(
            list(m.tcr_tracker.tasks),
            m.latency_tracker,
            m._ttft_variability_config,
            m._cost_predictability_config,
            m._min_samples_default,
            sla_results=[],
            sla_window_penalty=0.0,
            sla_budget_penalty=0.0,
            sla_warning=None,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        d = report.extra_metrics["harness_groups"]["D"]
        details = d["details"]

        assert round(details["avg_efficiency_calibrated_score"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_budget_score"], 4) == 0.8  # (0.9+0.8+0.7)/3
        assert details["ttft_variability_score"] is not None  # 5건 >= min_samples=5
        assert details["avg_cost_predictability"] is not None
        assert d["name"] == "Performance Contract"
        assert d["score"] is not None
        assert d["status"] in ("pass", "warn", "fail")
        assert d["gate"] == d["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전(SPEC-000) + SLA penalty/efficiency reference
        cost 노출(Harness Method 검사 5-D 개선) 이후와 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        details = report.extra_metrics["harness_groups"]["D"]["details"]
        assert set(details.keys()) == {
            "p95_latency_s", "avg_efficiency_calibrated_score", "avg_efficiency_ratio",
            "avg_budget_score", "ttft_variability_score", "ttft_stddev_ms",
            "ttft_p50_ms", "ttft_p95_ms", "avg_cost_predictability",
            "insufficient_data_warnings",
            "perf_score_pre_sla_penalty", "sla_window_penalty", "sla_budget_penalty",
            "efficiency_ratio_reference_cost",
        }

    def test_ttft_insufficient_samples_warns(self):
        """TTFT 표본이 min_samples(5) 미만이면 insufficient_data_warnings에 반영된다."""
        m = PerformanceMonitor()
        m.record_task(_task("t1", {"ttft_ms": 100}))
        m.record_task(_task("t2", {"ttft_ms": 110}))
        report = m.generate_report()
        assert report.extra_metrics is not None
        warnings = report.extra_metrics["harness_groups"]["D"]["details"]["insufficient_data_warnings"]
        assert warnings is not None
        assert any("ttft_variability" in w for w in warnings)


# ---------------------------------------------------------------------------
# Harness Method 검사 5-D 개선: SLA penalty 역추적 가능성 + efficiency_ratio
# 폴백 정규화 기준 비용 설정 가능화 (gates/gate_d_performance/aggregate.py)
# ---------------------------------------------------------------------------

class TestSlaPenaltyVisibility:
    def test_sla_penalties_exposed_and_explain_score_gap(self):
        """SLA window/budget penalty가 details에 그대로 노출되고, perf_score_pre_sla_penalty에서
        (penalty 합) 만큼 뺀 값이 최종 score와 일치해야 한다(역추적 가능성)."""
        from agent_evaluator.gates.gate_d_performance import aggregate as gate_d_aggregate
        from agent_evaluator.core.trackers.layer1 import LatencyTracker

        tasks = [
            _task("d1", {"efficiency": {"calibrated_score": 1.0, "efficiency_ratio": 0.01, "cost_unit": "usd"}}),
        ]
        group = gate_d_aggregate.compute(
            tasks,
            LatencyTracker(),
            None,
            None,
            3,
            sla_results=[],
            sla_window_penalty=0.3,
            sla_budget_penalty=0.1,
            sla_warning=None,
        )
        details = group["details"]
        assert details["sla_window_penalty"] == 0.3
        assert details["sla_budget_penalty"] == 0.1
        assert details["perf_score_pre_sla_penalty"] == 1.0  # calibrated_score만 반영된 순수 성능값
        assert group["score"] == pytest.approx(1.0 - 0.3 - 0.1)  # 0.6

    def test_zero_penalty_explicitly_shown_not_omitted(self):
        """패널티가 0이어도(미발동) 키 자체는 항상 노출되어 'SLA 데이터 없음'과 구분되어야 한다."""
        from agent_evaluator.gates.gate_d_performance import aggregate as gate_d_aggregate
        from agent_evaluator.core.trackers.layer1 import LatencyTracker

        tasks = [
            _task("d1", {"efficiency": {"calibrated_score": 0.9, "efficiency_ratio": 0.01, "cost_unit": "usd"}}),
        ]
        group = gate_d_aggregate.compute(
            tasks, LatencyTracker(), None, None, 3,
            sla_results=[], sla_window_penalty=0.0, sla_budget_penalty=0.0, sla_warning=None,
        )
        details = group["details"]
        assert details["sla_window_penalty"] == 0.0
        assert details["sla_budget_penalty"] == 0.0
        assert details["perf_score_pre_sla_penalty"] == group["score"]


class TestEfficiencyRatioReferenceCost:
    def test_default_legacy_constant_used_when_config_absent(self):
        """fallback_reference_cost_per_completion 미설정 태스크는 cost_unit별 레거시 기본값을 쓴다."""
        from agent_evaluator.gates.gate_d_performance import aggregate as gate_d_aggregate
        from agent_evaluator.core.trackers.layer1 import LatencyTracker

        tasks = [
            _task("d1", {"efficiency": {"efficiency_ratio": 0.0005, "cost_unit": "tokens"}}),
        ]
        group = gate_d_aggregate.compute(
            tasks, LatencyTracker(), None, None, 3,
            sla_results=[], sla_window_penalty=0.0, sla_budget_penalty=0.0, sla_warning=None,
        )
        assert group["details"]["efficiency_ratio_reference_cost"] == 1000.0
        assert group["score"] == pytest.approx(min(1.0, 0.0005 * 1000.0))

    def test_custom_reference_cost_overrides_legacy_constant(self):
        """EfficiencyConfig(fallback_reference_cost_per_completion=...)가 태스크 _config에
        실려 있으면 그 값이 정규화 기준으로 쓰여야 한다."""
        from agent_evaluator.gates.gate_d_performance import aggregate as gate_d_aggregate
        from agent_evaluator.core.trackers.layer1 import LatencyTracker

        tasks = [
            _task("d1", {
                "efficiency": {
                    "efficiency_ratio": 0.0625,
                    "cost_unit": "tokens",
                    "_config": {"fallback_reference_cost_per_completion": 8.0},
                },
            }),
        ]
        group = gate_d_aggregate.compute(
            tasks, LatencyTracker(), None, None, 3,
            sla_results=[], sla_window_penalty=0.0, sla_budget_penalty=0.0, sla_warning=None,
        )
        assert group["details"]["efficiency_ratio_reference_cost"] == 8.0
        assert group["score"] == pytest.approx(0.5)  # 0.0625 * 8.0

    def test_calibrated_score_path_leaves_reference_cost_none(self):
        """calibrated_score가 사용되는 경로(target_cost_per_completion 설정)에서는
        폴백 정규화 자체가 실행되지 않으므로 efficiency_ratio_reference_cost는 None이어야 한다."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        details = report.extra_metrics["harness_groups"]["D"]["details"]
        assert details["avg_efficiency_calibrated_score"] is not None
        assert details["efficiency_ratio_reference_cost"] is None


class TestEfficiencyConfigFallbackReferenceCostField:
    def test_default_none(self):
        from agent_evaluator import EfficiencyConfig
        cfg = EfficiencyConfig()
        assert cfg.fallback_reference_cost_per_completion is None

    def test_valid_value_kept(self):
        from agent_evaluator import EfficiencyConfig
        cfg = EfficiencyConfig(fallback_reference_cost_per_completion=5.0)
        assert cfg.fallback_reference_cost_per_completion == 5.0

    def test_non_positive_value_warns_and_resets_to_none(self):
        from agent_evaluator import EfficiencyConfig
        with pytest.warns(UserWarning, match="fallback_reference_cost_per_completion"):
            cfg = EfficiencyConfig(fallback_reference_cost_per_completion=0.0)
        assert cfg.fallback_reference_cost_per_completion is None

    def test_eval_efficiency_threads_config_into_result(self):
        from agent_evaluator import EfficiencyConfig
        from agent_evaluator.gates.gate_d_performance.evaluators import eval_efficiency

        cfg = EfficiencyConfig(cost_unit="tokens", fallback_reference_cost_per_completion=8.0)
        result = eval_efficiency(
            completion_score=0.9, tokens_used=100, execution_time_s=1.0,
            cost_usd=None, config=cfg,
        )
        assert result["_config"]["fallback_reference_cost_per_completion"] == 8.0

    def test_eval_efficiency_omits_config_key_when_unset(self):
        from agent_evaluator import EfficiencyConfig
        from agent_evaluator.gates.gate_d_performance.evaluators import eval_efficiency

        cfg = EfficiencyConfig(cost_unit="tokens")
        result = eval_efficiency(
            completion_score=0.9, tokens_used=100, execution_time_s=1.0,
            cost_usd=None, config=cfg,
        )
        assert "_config" not in result
