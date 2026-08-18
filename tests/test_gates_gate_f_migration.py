"""
tests/test_gates_gate_f_migration.py
=======================================
SPEC-000 Commit 1: Gate F(Multi-Agent Coordination) 패키지 이관 검증.

기존 tests/test_gate_f_bugs.py(27건)·tests/test_min_sample_guard.py·
tests/test_report_harness_groups.py는 수정 없이 그대로 통과해야 한다(re-export 검증).
이 파일은 이관 자체(항등성 + monitor.py 위임 호출과 aggregate.compute() 직접 호출의
동등성)를 검증한다.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra
    )


class TestConfigIdentity:
    def test_consensus_config_same_object(self):
        from agent_evaluator.decorators import ConsensusConfig as C1
        from agent_evaluator.gates.gate_f_multiagent.configs import ConsensusConfig as C2
        from agent_evaluator import ConsensusConfig as C3
        assert C1 is C2 is C3

    def test_propagation_config_same_object(self):
        from agent_evaluator.decorators import PropagationConfig as C1
        from agent_evaluator.gates.gate_f_multiagent.configs import PropagationConfig as C2
        assert C1 is C2

    def test_agent_role_config_same_object(self):
        from agent_evaluator.decorators import AgentRoleConfig as C1
        from agent_evaluator.gates.gate_f_multiagent.configs import AgentRoleConfig as C2
        assert C1 is C2

    def test_conflict_resolution_config_same_object(self):
        from agent_evaluator.decorators import ConflictResolutionConfig as C1
        from agent_evaluator.gates.gate_f_multiagent.configs import ConflictResolutionConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_consensus_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_consensus as E1
        from agent_evaluator.gates.gate_f_multiagent.evaluators import eval_consensus as E2
        assert E1 is E2

    def test_eval_propagation_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_propagation as E1
        from agent_evaluator.gates.gate_f_multiagent.evaluators import eval_propagation as E2
        assert E1 is E2

    def test_eval_role_adherence_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_role_adherence as E1
        from agent_evaluator.gates.gate_f_multiagent.evaluators import eval_role_adherence as E2
        assert E1 is E2

    def test_eval_conflict_resolution_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_conflict_resolution as E1
        from agent_evaluator.gates.gate_f_multiagent.evaluators import eval_conflict_resolution as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    m = PerformanceMonitor()
    # consensus: majority 3건(0.9/0.8/0.7 → 평균 0.8) + single 1건(제외 확인용)
    m.record_task(_task("c1", {"consensus": {"consensus_score": 0.9, "method": "majority"}}))
    m.record_task(_task("c2", {"consensus": {"consensus_score": 0.8, "method": "majority"}}))
    m.record_task(_task("c3", {"consensus": {"consensus_score": 0.7, "method": "majority"}}))
    m.record_task(_task("c4", {"consensus": {"consensus_score": 0.5, "method": "single"}}))
    # propagation: 2건만(min_samples_default=3 미만 → 표본 부족 경고 트리거)
    m.record_task(_task("p1", {"propagation": {"fidelity_score": 0.6}}))
    m.record_task(_task("p2", {"propagation": {"fidelity_score": 0.4}}))
    # agent_role: 3건(1.0/0.9/0.8 → 평균 0.9)
    m.record_task(_task("r1", {"agent_role": {"role_compliance_score": 1.0}}))
    m.record_task(_task("r2", {"agent_role": {"role_compliance_score": 0.9}}))
    m.record_task(_task("r3", {"agent_role": {"role_compliance_score": 0.8}}))
    # conflict_resolution: 3건(1.0/1.0/0.5 → 평균 0.8333)
    m.record_task(_task("k1", {"conflict_resolution": {"resolution_score": 1.0}}))
    m.record_task(_task("k2", {"conflict_resolution": {"resolution_score": 1.0}}))
    m.record_task(_task("k3", {"conflict_resolution": {"resolution_score": 0.5}}))
    # Gate F와 무관한 태스크 1건 (무관성 확인용)
    m.record_task(_task("n1", {}))

    # coordination/tool_selection은 record_task/extra 경로가 아니라 트래커 API 직접 호출
    m.agent_coordination_tracker.track_interaction(
        task_id="c1", from_agent="orchestrator", to_agent="worker",
        interaction_type="delegation", success=True,
    )
    m.agent_coordination_tracker.track_interaction(
        task_id="c2", from_agent="worker", to_agent="orchestrator",
        interaction_type="communication", success=True,
    )
    m.tool_selection_tracker.evaluate_selection(
        task_id="c1", expected_tools=["search", "calculator"], actual_tools=["search", "calculator"],
    )
    return m


class TestGateFMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_f_multiagent import aggregate as gate_f_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        via_monitor = report.extra_metrics["harness_groups"]["F"]

        direct = gate_f_aggregate.compute(
            list(m.tcr_tracker.tasks),
            m.agent_coordination_tracker,
            m.tool_selection_tracker,
            m._min_samples_default,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        f = report.extra_metrics["harness_groups"]["F"]
        details = f["details"]

        assert details["avg_consensus"] == 0.8  # single(0.5) 제외, (0.9+0.8+0.7)/3
        assert details["avg_propagation"] == 0.5  # (0.6+0.4)/2
        assert details["avg_role_compliance"] == 0.9  # (1.0+0.9+0.8)/3
        assert round(details["avg_conflict_resolution"], 4) == 0.8333  # (1.0+1.0+0.5)/3
        assert details["coordination_score"] is not None  # 트래커 인터랙션 2건 기록됨
        assert details["avg_tool_selection_f1"] is not None  # 트래커 평가 1건 기록됨
        # SPEC-012: coordination_score/tool_selection_f1도 이벤트 수 기반 min-sample 가드 대상
        assert details["insufficient_data_warnings"] == [
            "propagation: 2 samples < min_samples=3",
            "coordination_score: 2 interactions < min_samples=3",
            "tool_selection_f1: 1 evaluations < min_samples=3",
        ]
        assert f["name"] == "Multi-Agent Coordination"
        assert f["score"] is not None
        assert f["status"] in ("pass", "warn", "fail")
        assert f["gate"] == f["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한 6+1개인지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        details = report.extra_metrics["harness_groups"]["F"]["details"]
        assert set(details.keys()) == {
            "coordination_score", "avg_tool_selection_f1", "avg_consensus",
            "avg_propagation", "avg_role_compliance", "avg_conflict_resolution",
            "insufficient_data_warnings",
        }
