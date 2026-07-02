"""
tests/test_min_sample_guard.py
================================
SPEC-002: 전 Gate 공통 최소 표본 가드 검증.

이벤트 기반 지표(Gate F coordination/tool_selection, Gate G tool_coverage)의
min-sample 가드는 SPEC-012로 별도 구현되었다 — TestEventBasedInsufficientSamples 참조.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra, **kwargs):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra, **kwargs
    )


def _hg(monitor):
    return monitor._compute_harness_groups(
        tasks=list(monitor.tcr_tracker.tasks),
        security_metrics=monitor._collect_security_metrics(),
        layer1=monitor._collect_layer1_metrics(),
        layer2=monitor._collect_layer2_metrics(),
        ttft_variability_config=monitor._ttft_variability_config,
        cost_predictability_config=monitor._cost_predictability_config,
    )


class TestGateAInsufficientSamples:
    def test_goal_alignment_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"goal_alignment": {"score": 0.8}}))
        warnings = _hg(m)["A"]["details"]["insufficient_data_warnings"]
        assert warnings == ["goal_alignment: 2 samples < min_samples=3"]

    def test_zero_samples_not_flagged(self):
        m = PerformanceMonitor()
        m.record_task(_task("t0", {}))
        warnings = _hg(m)["A"]["details"]["insufficient_data_warnings"]
        assert warnings is None


class TestGateCAndDSharedSlaWarning:
    def test_sla_four_samples_shared_between_c_and_d(self):
        m = PerformanceMonitor()
        for i in range(4):
            m.record_task(_task(f"t{i}", {"sla": {"sla_met": True}}))
        hg = _hg(m)
        expected = "sla: 4 samples < min_samples=5"
        # Gate C는 SLA 외 다른 Gate C 지표가 없으므로 sla 경고만 존재
        assert hg["C"]["details"]["insufficient_data_warnings"] == [expected]
        # Gate D는 SLA 외에도 cost_predictability(4 tasks < min_samples=5)가 독립적으로
        # 경고되므로 리스트에 포함될 수 있다 — sla 경고가 동일 문자열로 공유되는지만 확인.
        assert expected in hg["D"]["details"]["insufficient_data_warnings"]

    def test_sla_five_samples_no_warning(self):
        m = PerformanceMonitor()
        for i in range(5):
            m.record_task(_task(f"t{i}", {"sla": {"sla_met": True}}))
        hg = _hg(m)
        assert hg["C"]["details"]["insufficient_data_warnings"] is None
        assert hg["D"]["details"]["insufficient_data_warnings"] is None


class TestGateBInsufficientSamples:
    def test_scope_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"scope": {"scope_score": 0.9}}))
        warnings = _hg(m)["B"]["details"]["insufficient_data_warnings"]
        assert warnings == ["scope: 2 samples < min_samples=3"]

    def test_goal_alignment_not_duplicated_in_gate_b(self):
        # Gate A 진단용 재참조(goal_alignment/plan_coherence)는 Gate B에서 중복 경고하지 않는다.
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"goal_alignment": {"score": 0.8}}))
        warnings = _hg(m)["B"]["details"]["insufficient_data_warnings"]
        assert warnings is None


class TestGateEInsufficientSamples:
    def test_compliance_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"compliance": {"compliance_score": 0.9}}))
        warnings = _hg(m)["E"]["details"]["insufficient_data_warnings"]
        assert warnings == ["compliance: 2 samples < min_samples=3"]

    def test_privilege_escalation_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"privilege_escalation": {"escalation_detected": False}}))
        warnings = _hg(m)["E"]["details"]["insufficient_data_warnings"]
        assert warnings == ["privilege_escalation: 2 samples < min_samples=3"]


class TestGateFAndGInsufficientSamples:
    def test_consensus_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(
                f"t{i}", {"consensus": {"consensus_score": 0.7, "method": "multi"}}
            ))
        warnings = _hg(m)["F"]["details"]["insufficient_data_warnings"]
        assert warnings == ["consensus: 2 samples < min_samples=3"]

    def test_observability_two_samples_warns(self):
        m = PerformanceMonitor()
        for i in range(2):
            m.record_task(_task(f"t{i}", {"observability": {"observability_score": 0.8}}))
        warnings = _hg(m)["G"]["details"]["insufficient_data_warnings"]
        assert warnings == ["observability: 2 samples < min_samples=3"]

    def test_event_based_metrics_zero_count_not_flagged(self):
        # count=0(측정 자체가 없음)은 "표본 부족"이 아니라 "미측정"이므로 경고 대상이 아니다
        # (SPEC-002/SPEC-012 공통 컨벤션) — coordination/tool_selection/tool_coverage 모두
        # 이벤트가 전혀 기록되지 않았으므로 여전히 경고가 뜨지 않아야 한다.
        m = PerformanceMonitor(enable_security_metrics=False)
        m.record_task(_task("t0", {}))
        hg = _hg(m)
        assert hg["F"]["details"]["insufficient_data_warnings"] is None
        assert hg["G"]["details"]["insufficient_data_warnings"] is None


class TestEventBasedInsufficientSamples:
    """SPEC-012: coordination_score/tool_selection_f1(Gate F), tool_coverage(Gate G) —
    task 수가 아니라 이벤트/호출 수를 분모로 쓰는 3개 지표의 min-sample 가드."""

    def test_coordination_score_two_interactions_warns(self):
        m = PerformanceMonitor()
        m.agent_coordination_tracker.track_interaction(
            task_id="c1", from_agent="orchestrator", to_agent="worker",
            interaction_type="delegation", success=True,
        )
        m.agent_coordination_tracker.track_interaction(
            task_id="c2", from_agent="worker", to_agent="orchestrator",
            interaction_type="communication", success=True,
        )
        m.record_task(_task("t0", {}))
        warnings = _hg(m)["F"]["details"]["insufficient_data_warnings"]
        assert warnings == ["coordination_score: 2 interactions < min_samples=3"]

    def test_tool_selection_f1_one_evaluation_warns(self):
        m = PerformanceMonitor()
        m.tool_selection_tracker.evaluate_selection(
            task_id="c1", expected_tools=["search"], actual_tools=["search"],
        )
        m.record_task(_task("t0", {}))
        warnings = _hg(m)["F"]["details"]["insufficient_data_warnings"]
        assert warnings == ["tool_selection_f1: 1 evaluations < min_samples=3"]

    def test_tool_coverage_two_calls_warns(self):
        m = PerformanceMonitor()
        m.record_task(_task("t0", {}, tool_calls=[{"name": "search", "success": True}]))
        m.record_task(_task("t1", {}, tool_calls=[{"name": "search", "success": False}]))
        warnings = _hg(m)["G"]["details"]["insufficient_data_warnings"]
        assert warnings == ["tool_coverage: 2 calls < min_samples=3"]

    def test_coordination_score_three_interactions_no_warning(self):
        m = PerformanceMonitor()
        for i in range(3):
            m.agent_coordination_tracker.track_interaction(
                task_id=f"c{i}", from_agent="orchestrator", to_agent="worker",
                interaction_type="delegation", success=True,
            )
        m.record_task(_task("t0", {}))
        warnings = _hg(m)["F"]["details"]["insufficient_data_warnings"]
        assert warnings is None


class TestFullSampleRegressionNoWarnings:
    def test_three_full_samples_all_gates_none(self):
        m = PerformanceMonitor()
        for i in range(3):
            m.record_task(_task(f"t{i}", {
                "goal_alignment": {"score": 0.8},
                "compliance": {"compliance_score": 0.9},
                "consensus": {"consensus_score": 0.7, "method": "multi"},
                "observability": {"observability_score": 0.8},
            }))
        hg = _hg(m)
        for gate in ("A", "E", "F", "G"):
            assert hg[gate]["details"]["insufficient_data_warnings"] is None, gate

    def test_min_samples_never_nulls_score(self):
        # REQ-4: 표본 미달이어도 score 자체는 None이 되지 않는다 (계산 가능하면).
        m = PerformanceMonitor()
        m.record_task(_task("t0", {"goal_alignment": {"score": 0.8}}))
        hg = _hg(m)
        assert hg["A"]["score"] is not None
        assert hg["A"]["details"]["insufficient_data_warnings"] == [
            "goal_alignment: 1 samples < min_samples=3"
        ]

    def test_min_samples_default_configurable(self):
        # min_samples_default를 낮추면 동일 표본 수에도 경고가 사라짐을 확인.
        m = PerformanceMonitor(min_samples_default=1)
        for i in range(2):
            m.record_task(_task(f"t{i}", {"goal_alignment": {"score": 0.8}}))
        warnings = _hg(m)["A"]["details"]["insufficient_data_warnings"]
        assert warnings is None
