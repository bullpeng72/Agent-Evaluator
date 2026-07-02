"""
tests/test_gates_gate_a_migration.py
=======================================
SPEC-000: Gate A(Goal Achievement) 패키지 이관 검증.

기존 tests/test_decorators_harness.py(280건)는 수정 없이 그대로 통과해야 한다
(re-export 검증). 이 파일은 이관 자체(항등성 + monitor.py 위임 호출과
aggregate.compute() 직접 호출의 동등성, Gate A→B 교차 참조)를 검증한다.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra
    )


class TestConfigIdentity:
    def test_instruction_config_same_object(self):
        from agent_evaluator.decorators import InstructionConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import InstructionConfig as C2
        from agent_evaluator import InstructionConfig as C3
        assert C1 is C2 is C3

    def test_goal_alignment_config_same_object(self):
        from agent_evaluator.decorators import GoalAlignmentConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import GoalAlignmentConfig as C2
        assert C1 is C2

    def test_plan_config_same_object(self):
        from agent_evaluator.decorators import PlanConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import PlanConfig as C2
        assert C1 is C2

    def test_context_retention_config_same_object(self):
        from agent_evaluator.decorators import ContextRetentionConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import ContextRetentionConfig as C2
        assert C1 is C2

    def test_subtask_config_same_object(self):
        from agent_evaluator.decorators import SubtaskConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import SubtaskConfig as C2
        assert C1 is C2

    def test_knowledge_retention_config_same_object(self):
        from agent_evaluator.decorators import KnowledgeRetentionConfig as C1
        from agent_evaluator.gates.gate_a_goal.configs import KnowledgeRetentionConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_instruction_adherence_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_instruction_adherence as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_instruction_adherence as E2
        assert E1 is E2

    def test_eval_goal_alignment_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_goal_alignment as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_goal_alignment as E2
        assert E1 is E2

    def test_eval_plan_coherence_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_plan_coherence as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_plan_coherence as E2
        assert E1 is E2

    def test_eval_context_retention_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_context_retention as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_context_retention as E2
        assert E1 is E2

    def test_eval_subtask_completion_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_subtask_completion as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_subtask_completion as E2
        assert E1 is E2

    def test_eval_knowledge_retention_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention as E1
        from agent_evaluator.gates.gate_a_goal.evaluators import eval_knowledge_retention as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # instruction_adherence: 3건
    for i, score in enumerate([1.0, 0.9, 0.8], start=1):
        m.record_task(_task(f"ia{i}", {"instruction_adherence": {"score": score}}))
    # goal_alignment: 3건
    for i, score in enumerate([0.9, 0.8, 0.7], start=1):
        m.record_task(_task(f"ga{i}", {"goal_alignment": {"score": score, "use_llm_scoring": False}}))
    # plan_coherence: 3건
    for i, score in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"pc{i}", {"plan_coherence": {"score": score, "use_llm_scoring": False}}))
    # subtask_completion: 3건(subtask_count > 0 이어야 집계 포함)
    for i, rate in enumerate([1.0, 0.8, 0.6], start=1):
        m.record_task(_task(f"sc{i}", {"subtask_completion": {"completion_rate": rate, "subtask_count": 3}}))
    # context_retention: 3건
    for i, score in enumerate([0.9, 0.8, 0.7], start=1):
        m.record_task(_task(f"cr{i}", {"context_retention": {"retention_score": score}}))
    # knowledge_retention: 2건만 (min_samples_default=3 미만 → 표본 부족 경고 트리거)
    for i, score in enumerate([0.9, 0.7], start=1):
        m.record_task(_task(f"kr{i}", {"knowledge_retention": {"retention_score": score}}))
    return m


class TestGateAMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_a_goal import aggregate as gate_a_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        via_monitor = report.extra_metrics["harness_groups"]["A"]

        direct = gate_a_aggregate.compute(
            list(m.tcr_tracker.tasks),
            m.tcr_tracker,
            m.accuracy_evaluator,
            m.quality_evaluator,
            m._gate_a_tcr_weight,
            m._min_samples_default,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        a = report.extra_metrics["harness_groups"]["A"]
        details = a["details"]

        assert round(details["avg_instruction_adherence"], 4) == 0.9  # (1.0+0.9+0.8)/3
        assert round(details["avg_goal_alignment"], 4) == 0.8  # (0.9+0.8+0.7)/3
        assert round(details["avg_plan_coherence"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_subtask_completion"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert round(details["avg_context_retention"], 4) == 0.8  # (0.9+0.8+0.7)/3
        assert round(details["avg_knowledge_retention"], 4) == 0.8  # (0.9+0.7)/2
        assert details["insufficient_data_warnings"] == [
            "knowledge_retention: 2 samples < min_samples=3"
        ]
        assert a["name"] == "Goal Achievement"
        assert a["score"] is not None
        assert a["status"] in ("pass", "warn", "fail")
        assert a["gate"] == a["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["A"]["details"]
        assert set(details.keys()) == {
            "tcr_pct", "avg_accuracy", "avg_quality_relevance_completeness",
            "gate_a_tcr_weight", "tasks_with_ifr", "avg_instruction_adherence",
            "avg_goal_alignment", "avg_plan_coherence", "avg_subtask_completion",
            "avg_context_retention", "avg_knowledge_retention",
            "insufficient_data_warnings",
        }

    def test_gate_b_cross_references_gate_a_values(self):
        """Gate B의 gate_a_ref__* 필드가 Gate A의 값과 정확히 일치해야 한다(재계산 아님, 재참조)."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        groups = report.extra_metrics["harness_groups"]
        a_details = groups["A"]["details"]
        b_details = groups["B"]["details"]
        assert b_details["gate_a_ref__avg_goal_alignment"] == a_details["avg_goal_alignment"]
        assert b_details["gate_a_ref__avg_plan_coherence"] == a_details["avg_plan_coherence"]
