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
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["D"]["details"]
        assert set(details.keys()) == {
            "p95_latency_s", "avg_efficiency_calibrated_score", "avg_efficiency_ratio",
            "avg_budget_score", "ttft_variability_score", "ttft_stddev_ms",
            "ttft_p50_ms", "ttft_p95_ms", "avg_cost_predictability",
            "insufficient_data_warnings",
        }

    def test_ttft_insufficient_samples_warns(self):
        """TTFT 표본이 min_samples(5) 미만이면 insufficient_data_warnings에 반영된다."""
        m = PerformanceMonitor()
        m.record_task(_task("t1", {"ttft_ms": 100}))
        m.record_task(_task("t2", {"ttft_ms": 110}))
        report = m.generate_report()
        warnings = report.extra_metrics["harness_groups"]["D"]["details"]["insufficient_data_warnings"]
        assert warnings is not None
        assert any("ttft_variability" in w for w in warnings)
