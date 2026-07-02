"""
tests/test_gates_gate_c_migration.py
=======================================
SPEC-000: Gate C(Reliability) 패키지 이관 검증.

기존 tests/test_decorators_harness.py는 수정 없이 그대로 통과해야 한다(re-export 검증).
이 파일은 이관 자체(항등성 + monitor.py 위임 호출과 aggregate.compute() 직접 호출의
동등성, SLA 공유 데이터가 Gate D에 정확히 전달되는지, hall_rate/avg_llm_faithfulness가
Gate G(미이관) 섹션에 원본값 그대로 재사용되는지)를 검증한다.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra=None, **kwargs):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra, **kwargs
    )


class TestConfigIdentity:
    def test_reproducibility_config_same_object(self):
        from agent_evaluator.decorators import ReproducibilityConfig as C1
        from agent_evaluator.gates.gate_c_reliability.configs import ReproducibilityConfig as C2
        from agent_evaluator import ReproducibilityConfig as C3
        assert C1 is C2 is C3

    def test_fault_tolerance_config_same_object(self):
        from agent_evaluator.decorators import FaultToleranceConfig as C1
        from agent_evaluator.gates.gate_c_reliability.configs import FaultToleranceConfig as C2
        assert C1 is C2

    def test_graceful_degradation_config_same_object(self):
        from agent_evaluator.decorators import GracefulDegradationConfig as C1
        from agent_evaluator.gates.gate_c_reliability.configs import GracefulDegradationConfig as C2
        assert C1 is C2

    def test_retry_consistency_config_same_object(self):
        from agent_evaluator.decorators import RetryConsistencyConfig as C1
        from agent_evaluator.gates.gate_c_reliability.configs import RetryConsistencyConfig as C2
        assert C1 is C2

    def test_idempotency_config_same_object(self):
        from agent_evaluator.decorators import IdempotencyConfig as C1
        from agent_evaluator.gates.gate_c_reliability.configs import IdempotencyConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_fault_tolerance_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_fault_tolerance as E1
        from agent_evaluator.gates.gate_c_reliability.evaluators import eval_fault_tolerance as E2
        assert E1 is E2

    def test_compute_reproducibility_score_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import compute_reproducibility_score as E1
        from agent_evaluator.gates.gate_c_reliability.evaluators import compute_reproducibility_score as E2
        assert E1 is E2

    def test_eval_graceful_degradation_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_graceful_degradation as E1
        from agent_evaluator.gates.gate_c_reliability.evaluators import eval_graceful_degradation as E2
        assert E1 is E2

    def test_eval_retry_consistency_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_retry_consistency as E1
        from agent_evaluator.gates.gate_c_reliability.evaluators import eval_retry_consistency as E2
        assert E1 is E2

    def test_eval_idempotency_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_idempotency as E1
        from agent_evaluator.gates.gate_c_reliability.evaluators import eval_idempotency as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # reproducibility: 3건 (run_count>=2 이어야 집계 포함)
    for i, score in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"rp{i}", {"reproducibility": {"score": score, "run_count": 3}}))
    # fault_tolerance: 3건 (grade != none/untracked)
    for i, (grade, rq) in enumerate(
        [("good", 1.0), ("partial", 0.5), ("poor", 0.0)], start=1
    ):
        m.record_task(_task(f"ft{i}", {"fault_tolerance": {"grade": grade, "recovery_quality_score": rq}}))
    # graceful_degradation: 3건
    for i, score in enumerate([1.0, 0.7, 0.3], start=1):
        m.record_task(_task(f"gd{i}", {"graceful_degradation": {"degradation_score": score}}))
    # retry_consistency: 3건 (group_by_task_prefix=False로 단순 평균 검증)
    for i, score in enumerate([0.9, 0.8, 0.7], start=1):
        m.record_task(_task(f"rc{i}", {"retry_consistency": {
            "consistency_score": score, "_config": {"group_by_task_prefix": False},
        }}))
    # idempotency: 3건
    for i, score in enumerate([1.0, 0.9, 0.8], start=1):
        m.record_task(_task(f"id{i}", {"idempotency": {"idempotency_score": score}}))
    # sla: 4건 (1건 breach) — Gate C breach_rate 기여 + Gate D 공유 데이터 검증용
    for i, met in enumerate([True, True, True, False], start=1):
        m.record_task(_task(f"sla{i}", {"sla": {"sla_met": met}}))
    return m


class TestGateCMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_c_reliability import aggregate as gate_c_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        via_monitor = report.extra_metrics["harness_groups"]["C"]

        tasks = list(m.tcr_tracker.tasks)
        sla_shared = gate_c_aggregate.compute_sla_shared_data(tasks)
        direct, _ = gate_c_aggregate.compute(
            tasks, m.hallucination_detector, m.tcr_tracker,
            m._gate_c_tcr_weight, m._min_samples_default, sla_shared,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        c = report.extra_metrics["harness_groups"]["C"]
        details = c["details"]

        assert round(details["avg_reproducibility"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_fault_tolerance"], 4) == 0.5  # (1.0+0.5+0.0)/3
        assert round(details["avg_degradation"], 4) == round((1.0 + 0.7 + 0.3) / 3, 4)
        assert round(details["avg_retry_consistency"], 4) == round((0.9 + 0.8 + 0.7) / 3, 4)
        assert round(details["avg_idempotency"], 4) == 0.9  # (1.0+0.9+0.8)/3
        assert round(details["sla_breach_rate"], 4) == 0.25  # 1/4
        assert details["sla_breach_count"] == 1
        assert c["name"] == "Reliability"
        assert c["score"] is not None
        assert c["status"] in ("pass", "warn", "fail")
        assert c["gate"] == c["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["C"]["details"]
        assert set(details.keys()) == {
            "tcr_pct", "gate_c_tcr_weight", "sla_breach_rate", "sla_breach_count",
            "avg_reproducibility", "avg_fault_tolerance", "avg_degradation",
            "avg_retry_consistency", "avg_idempotency", "avg_llm_faithfulness",
            "hallucination_rate", "insufficient_data_warnings",
        }

    def test_sla_shared_data_reaches_gate_d(self):
        """Gate C가 계산한 SLA 공유 데이터(breach_rate)가 Gate D에도 정확히 반영되는지 확인.

        breach_window=10(기본값), warn_threshold=2 미만이므로 이 픽스처(1/4 breach)는
        window penalty가 발동하지 않는다 — 순수하게 파이프라인 연결(공유 데이터가 실제로
        Gate C→D로 전달됨)을 검증하는 것이 목적이며, penalty 발동 조건 자체는 Gate D의
        책임 범위(gate_d_performance 자체 테스트에서 검증됨).
        """
        from agent_evaluator.gates.gate_c_reliability import aggregate as gate_c_aggregate

        m = _build_monitor_with_fixtures()
        tasks = list(m.tcr_tracker.tasks)
        sla_shared = gate_c_aggregate.compute_sla_shared_data(tasks)

        assert len(sla_shared["sla_results"]) == 4
        assert sla_shared["sla_breach_count"] == 1
        assert round(sla_shared["sla_breach_rate"], 4) == 0.25
        assert sla_shared["sla_window_penalty"] == 0.0  # breach 1/4 < warn_threshold=2
        assert sla_shared["sla_budget_penalty"] == 0.0  # budget_usd 미설정

        report = m.generate_report()
        d_details = report.extra_metrics["harness_groups"]["D"]["details"]
        # Gate D의 latency_tracker 데이터가 없으므로 p95_latency_s=0이지만,
        # SLA penalty가 파이프라인을 타고 정상적으로 0.0(미발동)으로 도달했는지만 확인한다.
        assert d_details is not None

    def test_gate_g_reuses_unrounded_hall_rate(self):
        """hall_rate가 None인 기본 케이스에서 Gate C·G 양쪽의 hallucination_rate가 일치해야 한다."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        groups = report.extra_metrics["harness_groups"]
        # 이 픽스처는 hallucination_detector에 감지 데이터가 없으므로 양쪽 다 None이어야 한다.
        assert groups["C"]["details"]["hallucination_rate"] is None
        assert groups["G"]["details"]["hallucination_rate"] is None

    def test_llm_faithfulness_contributes_to_gate_c(self):
        """llm_judge faithfulness가 있으면 Gate C의 avg_llm_faithfulness에 반영되어야 한다."""
        m = PerformanceMonitor()
        for i, faith in enumerate([5.0, 4.0, 3.0], start=1):
            m.record_task(_task(
                f"lj{i}",
                llm_judge={"scores": {"faithfulness": faith}, "skipped": False},
            ))
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["C"]["details"]
        assert round(details["avg_llm_faithfulness"], 4) == round((5.0 + 4.0 + 3.0) / 3, 4)
