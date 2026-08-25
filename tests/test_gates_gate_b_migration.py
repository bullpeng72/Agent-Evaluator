"""
tests/test_gates_gate_b_migration.py
=======================================
SPEC-000: Gate B(Behavioral Integrity) 패키지 이관 검증.

기존 테스트(예: tests/test_decorators_harness.py)는 수정 없이 그대로 통과해야 한다
(re-export 검증). 이 파일은 이관 자체(항등성 + monitor.py 위임 호출과
aggregate.compute() 직접 호출의 동등성, Gate A→B 교차 참조)를 검증한다.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra
    )


class TestConfigIdentity:
    def test_loop_detection_config_same_object(self):
        from agent_evaluator.decorators import LoopDetectionConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import LoopDetectionConfig as C2
        from agent_evaluator import LoopDetectionConfig as C3
        assert C1 is C2 is C3

    def test_state_consistency_config_same_object(self):
        from agent_evaluator.decorators import StateConsistencyConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import StateConsistencyConfig as C2
        assert C1 is C2

    def test_deadlock_config_same_object(self):
        from agent_evaluator.decorators import DeadlockConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import DeadlockConfig as C2
        assert C1 is C2

    def test_scope_config_same_object(self):
        from agent_evaluator.decorators import ScopeConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import ScopeConfig as C2
        assert C1 is C2

    def test_tool_parameter_safety_config_same_object(self):
        from agent_evaluator.decorators import ToolParameterSafetyConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import ToolParameterSafetyConfig as C2
        assert C1 is C2

    def test_context_window_config_same_object(self):
        from agent_evaluator.decorators import ContextWindowConfig as C1
        from agent_evaluator.gates.gate_b_behavioral.configs import ContextWindowConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_loop_detection_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_loop_detection as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_loop_detection as E2
        assert E1 is E2

    def test_eval_state_consistency_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_state_consistency as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_state_consistency as E2
        assert E1 is E2

    def test_eval_deadlock_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_deadlock as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_deadlock as E2
        assert E1 is E2

    def test_eval_scope_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_scope as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_scope as E2
        assert E1 is E2

    def test_eval_tool_parameter_safety_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_tool_parameter_safety as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_tool_parameter_safety as E2
        assert E1 is E2

    def test_eval_context_window_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_context_window as E1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import eval_context_window as E2
        assert E1 is E2

    def test_normalize_agent_interactions_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import _normalize_agent_interactions as H1
        from agent_evaluator.gates.gate_b_behavioral.evaluators import _normalize_agent_interactions as H2
        assert H1 is H2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # loop_detection: 3건 (1건 detected=True)
    for i, detected in enumerate([True, False, False], start=1):
        m.record_task(_task(f"ld{i}", {"loop_detection": {"detected": detected}}))
    # state_consistency: 3건
    for i, score in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"sc{i}", {"state_consistency": {"consistency_score": score}}))
    # deadlock: 3건 (1건 detected=True, type=circular)
    for i, (detected, dtype) in enumerate(
        [(True, "circular"), (False, None), (False, None)], start=1
    ):
        m.record_task(_task(f"dl{i}", {"deadlock": {"deadlock_detected": detected, "deadlock_type": dtype}}))
    # scope: 3건
    for i, score in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"sp{i}", {"scope": {"scope_score": score}}))
    # tool_parameter_safety: 3건
    for i, score in enumerate([1.0, 0.9, 0.8], start=1):
        m.record_task(_task(f"tps{i}", {"tool_parameter_safety": {"safety_score": score}}))
    # context_window: 2건만 (min_samples_default=3 미만 → 표본 부족 경고 트리거)
    for i, score in enumerate([0.9, 0.7], start=1):
        m.record_task(_task(f"cw{i}", {"context_window": {"context_window_score": score}}))
    return m


class TestGateBMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_a_goal import aggregate as gate_a_aggregate
        from agent_evaluator.gates.gate_b_behavioral import aggregate as gate_b_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        via_monitor = report.extra_metrics["harness_groups"]["B"]

        tasks = list(m.tcr_tracker.tasks)
        a_group = gate_a_aggregate.compute(
            tasks, m.tcr_tracker, m.accuracy_evaluator, m.quality_evaluator,
            m._gate_a_tcr_weight, m._min_samples_default,
        )
        direct = gate_b_aggregate.compute(
            tasks, m._gate_b_loop_weight, m._min_samples_default,
            a_group["details"]["avg_goal_alignment"], a_group["details"]["avg_plan_coherence"],
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        b = report.extra_metrics["harness_groups"]["B"]
        details = b["details"]

        assert round(details["loop_detection_rate"], 4) == round(1 / 3, 4)
        assert details["loop_count"] == 1
        assert round(details["avg_state_consistency"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert details["deadlock_count"] == 1
        assert details["deadlock_by_type"] == {"circular": 1}
        assert round(details["avg_scope_score"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_tool_parameter_safety"], 4) == 0.9  # (1.0+0.9+0.8)/3
        assert round(details["avg_context_window"], 4) == 0.8  # (0.9+0.7)/2
        assert details["insufficient_data_warnings"] == [
            "context_window: 2 samples < min_samples=3"
        ]
        assert b["name"] == "Behavioral Integrity"
        assert b["score"] is not None
        assert b["status"] in ("pass", "warn", "fail")
        assert b["gate"] == b["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        details = report.extra_metrics["harness_groups"]["B"]["details"]
        assert set(details.keys()) == {
            "loop_detection_rate", "loop_count", "gate_b_loop_weight",
            "gate_a_ref__avg_goal_alignment", "gate_a_ref__avg_plan_coherence",
            "avg_state_consistency", "deadlock_count", "deadlock_by_type",
            "avg_deadlock_score", "avg_scope_score", "avg_tool_parameter_safety",
            "avg_context_window", "insufficient_data_warnings",
        }

    def test_loop_weight_ignored_warning_when_no_loop_data(self):
        """회귀 테스트 — gate_b_loop_weight>0을 명시적으로 설정해도 loop_detection
        데이터가 없으면 단순평균으로 조용히 폴백됐다(사용자가 자기 설정이 적용됐는지
        알 방법이 없었음). 이제 insufficient_data_warnings에 그 사실이 남는다."""
        from agent_evaluator.gates.gate_b_behavioral import aggregate as gate_b_aggregate

        tasks = [_task("t1", {"state_consistency": {"score": 0.9}})]  # loop_detection 없음
        result = gate_b_aggregate.compute(tasks, 0.3, 3, None, None)  # gate_b_loop_weight=0.3
        warnings = result["details"]["insufficient_data_warnings"] or []
        assert any("gate_b_loop_weight" in w for w in warnings)

    def test_no_loop_weight_warning_when_weight_is_default(self):
        """기본값(0.0)일 때는 loop_detection 데이터가 없어도 이 경고가 뜨지 않아야 한다
        — "설정했는데 무시됨"이 아니라 "애초에 가중치를 요청하지 않음"이기 때문."""
        from agent_evaluator.gates.gate_b_behavioral import aggregate as gate_b_aggregate

        tasks = [_task("t1", {"state_consistency": {"score": 0.9}})]
        result = gate_b_aggregate.compute(tasks, 0.0, 3, None, None)
        warnings = result["details"]["insufficient_data_warnings"] or []
        assert not any("gate_b_loop_weight" in w for w in warnings)

    def test_gate_b_cross_references_gate_a_values(self):
        """Gate B의 gate_a_ref__* 필드가 Gate A의 값과 정확히 일치해야 한다(재계산 아님, 재참조)."""
        m = _build_monitor_with_fixtures()
        # Gate A용 데이터도 함께 기록 (goal_alignment/plan_coherence)
        for i, score in enumerate([0.9, 0.8, 0.7], start=1):
            m.record_task(_task(f"ga{i}", {"goal_alignment": {"score": score, "use_llm_scoring": False}}))
        for i, score in enumerate([1.0, 0.8, 0.6], start=1):
            m.record_task(_task(f"pc{i}", {"plan_coherence": {"score": score, "use_llm_scoring": False}}))

        report = m.generate_report()
        assert report.extra_metrics is not None
        groups = report.extra_metrics["harness_groups"]
        a_details = groups["A"]["details"]
        b_details = groups["B"]["details"]
        assert b_details["gate_a_ref__avg_goal_alignment"] == a_details["avg_goal_alignment"]
        assert b_details["gate_a_ref__avg_plan_coherence"] == a_details["avg_plan_coherence"]
