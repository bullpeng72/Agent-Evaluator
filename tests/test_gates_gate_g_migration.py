"""
tests/test_gates_gate_g_migration.py
=======================================
SPEC-000: Gate G(Observability) 패키지 이관 검증.

이 이관으로 SPEC-000의 Gate A-G 전체 이관이 완료된다(F→E→D→A→B→C→G).

기존 tests/test_decorators_harness.py·test_report_harness_groups.py는 수정 없이 그대로
통과해야 한다(re-export 검증). 이 파일은 이관 자체(항등성 + monitor.py 위임 호출과
aggregate.compute() 직접 호출의 동등성, Gate C→G hall_rate 공유)를 검증한다.

SPEC-011: 이관 과정에서 발견된 "self.tool_call_analyzer" 속성명 결함(실제는
self.tool_analyzer — SPEC-000 이전부터 항상 AttributeError가 삼켜져 tool_coverage가
한 번도 계산된 적이 없었음)은 이 파일이 아니라 SPEC-011로 수정되었다. 관련 회귀 테스트는
아래 TestToolCoverageAttributeFix 참조.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra=None, **kwargs):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra, **kwargs
    )


class TestConfigIdentity:
    def test_observability_config_same_object(self):
        from agent_evaluator.decorators import ObservabilityConfig as C1
        from agent_evaluator.gates.gate_g_observability.configs import ObservabilityConfig as C2
        from agent_evaluator import ObservabilityConfig as C3
        assert C1 is C2 is C3

    def test_explainability_config_same_object(self):
        from agent_evaluator.decorators import ExplainabilityConfig as C1
        from agent_evaluator.gates.gate_g_observability.configs import ExplainabilityConfig as C2
        assert C1 is C2

    def test_error_diagnosis_config_same_object(self):
        from agent_evaluator.decorators import ErrorDiagnosisConfig as C1
        from agent_evaluator.gates.gate_g_observability.configs import ErrorDiagnosisConfig as C2
        assert C1 is C2

    def test_latency_attribution_config_same_object(self):
        from agent_evaluator.decorators import LatencyAttributionConfig as C1
        from agent_evaluator.gates.gate_g_observability.configs import LatencyAttributionConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_observability_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_observability as E1
        from agent_evaluator.gates.gate_g_observability.evaluators import eval_observability as E2
        assert E1 is E2

    def test_eval_explainability_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_explainability as E1
        from agent_evaluator.gates.gate_g_observability.evaluators import eval_explainability as E2
        assert E1 is E2

    def test_eval_error_diagnosis_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_error_diagnosis as E1
        from agent_evaluator.gates.gate_g_observability.evaluators import eval_error_diagnosis as E2
        assert E1 is E2

    def test_eval_latency_attribution_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_latency_attribution as E1
        from agent_evaluator.gates.gate_g_observability.evaluators import eval_latency_attribution as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # observability: 3건
    for i, score in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"ob{i}", {"observability": {"observability_score": score}}))
    # explainability: 3건
    for i, score in enumerate([1.0, 0.7, 0.3], start=1):
        m.record_task(_task(f"ex{i}", {"explainability": {"score": score}}))
    # error_diagnosis: 3건
    for i, score in enumerate([0.9, 0.6, 0.3], start=1):
        m.record_task(_task(f"ed{i}", {"error_diagnosis": {"diagnosis_score": score}}))
    # latency_attribution: 3건
    for i, score in enumerate([1.0, 0.8, 0.5], start=1):
        m.record_task(_task(f"la{i}", {"latency_attribution": {"attribution_score": score}}))
    return m


class TestGateGMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_g_observability import aggregate as gate_g_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        via_monitor = report.extra_metrics["harness_groups"]["G"]

        tasks = list(m.tcr_tracker.tasks)
        direct = gate_g_aggregate.compute(
            tasks, m.tool_analyzer, m._min_samples_default,
            hall_rate=None, avg_llm_faithfulness=None,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        g = report.extra_metrics["harness_groups"]["G"]
        details = g["details"]

        assert round(details["avg_observability_score"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_explainability"], 4) == round((1.0 + 0.7 + 0.3) / 3, 4)
        assert round(details["avg_error_diagnosis"], 4) == round((0.9 + 0.6 + 0.3) / 3, 4)
        assert round(details["avg_latency_attribution"], 4) == round((1.0 + 0.8 + 0.5) / 3, 4)
        assert g["name"] == "Observability"
        assert g["score"] is not None
        assert g["status"] in ("pass", "warn", "fail")
        assert g["gate"] == g["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["G"]["details"]
        assert set(details.keys()) == {
            "tool_coverage", "hallucination_rate", "avg_observability_score",
            "avg_explainability", "avg_error_diagnosis", "avg_latency_attribution",
            "insufficient_data_warnings",
        }

    def test_no_tool_calls_keeps_tool_coverage_none(self):
        """도구 호출이 없는 세션은 SPEC-011 수정 후에도 여전히 tool_coverage=None이어야 한다
        (ToolCallAnalyzer._executions가 비어 total_calls=0 → None, 회귀 없음)."""
        m = _build_monitor_with_fixtures()  # 이 픽스처들은 tool_calls를 포함하지 않음
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["G"]["details"]
        assert details["tool_coverage"] is None

    def test_hall_rate_shared_from_gate_c_disables_when_faithfulness_present(self):
        """LLM Judge faithfulness가 있으면 Gate G의 hallucination fallback이 비활성화되어야 한다
        (Gate C에 이미 귀속되어 이중 반영을 방지하는 기존 로직)."""
        from agent_evaluator.gates.gate_g_observability import aggregate as gate_g_aggregate

        m = _build_monitor_with_fixtures()
        tasks = list(m.tcr_tracker.tasks)
        # hall_rate가 있어도 avg_llm_faithfulness가 not None이면 hallucination fallback 미사용
        with_faith = gate_g_aggregate.compute(
            tasks, None, m._min_samples_default, hall_rate=0.3, avg_llm_faithfulness=4.0,
        )
        without_faith = gate_g_aggregate.compute(
            tasks, None, m._min_samples_default, hall_rate=0.3, avg_llm_faithfulness=None,
        )
        # faithfulness 없을 때만 hall_rate가 obs_vals에 반영되어 최종 점수가 달라진다
        assert with_faith["score"] != without_faith["score"]
        # 두 경우 모두 hallucination_rate details는 raw hall_rate를 그대로 노출(반영 여부와 무관)
        assert with_faith["details"]["hallucination_rate"] == 0.3
        assert without_faith["details"]["hallucination_rate"] == 0.3


class TestToolCoverageAttributeFix:
    """SPEC-011: self.tool_call_analyzer(존재한 적 없는 속성명) → self.tool_analyzer 수정 검증.

    SPEC-000 이관 전에는 이 오탈자가 Gate G 블록 내부의 지역 try/except에 삼켜져
    tool_coverage가 도구 호출 여부와 무관하게 항상 None이었다. SPEC-011로 실제 속성을
    참조하도록 고쳐 tool_coverage가 처음으로 정상 계산된다.
    """

    def test_performance_monitor_has_tool_analyzer_not_tool_call_analyzer(self):
        m = PerformanceMonitor()
        assert hasattr(m, "tool_analyzer")
        assert not hasattr(m, "tool_call_analyzer")

    def test_tool_calls_present_yields_real_tool_coverage(self):
        """도구 호출이 기록된 세션에서 tool_coverage가 실제 success_rate 기반 값으로 계산돼야 한다."""
        m = PerformanceMonitor()
        # 성공 2건 + 실패 1건 → success_rate = 2/3 * 100 ≈ 66.67
        m.record_task(_task("tc1", tool_calls=[{"name": "search", "success": True}]))
        m.record_task(_task("tc2", tool_calls=[{"name": "search", "success": True}]))
        m.record_task(_task("tc3", tool_calls=[{"name": "search", "success": False}]))

        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["G"]["details"]

        expected = m.tool_analyzer.get_efficiency_stats()["success_rate"] / 100.0
        assert details["tool_coverage"] is not None
        assert round(details["tool_coverage"], 4) == round(expected, 4)
        assert round(details["tool_coverage"], 4) == round(2 / 3, 4)

    def test_monitor_delegation_matches_direct_call_with_real_tool_calls(self):
        """실제 tool_analyzer를 사용한 byte-diff 동등성 — monitor 경유와 직접 호출이 일치해야 한다."""
        from agent_evaluator.gates.gate_g_observability import aggregate as gate_g_aggregate

        m = PerformanceMonitor()
        m.record_task(_task("tc1", tool_calls=[{"name": "search", "success": True}]))
        m.record_task(_task("tc2", tool_calls=[{"name": "search", "success": False}]))

        report = m.generate_report()
        via_monitor = report.extra_metrics["harness_groups"]["G"]

        tasks = list(m.tcr_tracker.tasks)
        direct = gate_g_aggregate.compute(
            tasks, m.tool_analyzer, m._min_samples_default,
            hall_rate=None, avg_llm_faithfulness=None,
        )
        assert via_monitor == direct
