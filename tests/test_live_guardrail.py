"""
tests/test_live_guardrail.py
===============================
SPEC-019 Rollout 1-3단계(Gate B 4종 + Gate E 3종) 검증:
agent_evaluator.gates.live_guardrail.LiveGuardrail.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.core.trackers.security import (
    PrivilegeEscalationDetector,
    ToolAuthorizationTracker,
    ToolChainAttackDetector,
)
from agent_evaluator.gates.gate_b_behavioral import evaluators as gate_b_evaluators
from agent_evaluator.gates.gate_b_behavioral.configs import (
    DeadlockConfig,
    LoopDetectionConfig,
    ScopeConfig,
    ToolParameterSafetyConfig,
)
from agent_evaluator.gates.live_guardrail import LiveGuardrail, LiveVerdict


class TestNoViolationRegression:
    def test_clean_sequence_never_blocks(self):
        guardrail = LiveGuardrail(
            loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, on_loop_detected="fail"),
            scope=ScopeConfig(forbidden_tools=["shell_exec"], fail_on_violation=True),
            tool_parameter_safety=ToolParameterSafetyConfig(fail_on_dangerous=True),
            deadlock=DeadlockConfig(fail_on_deadlock=True),
        )
        # window_size=5(기본값)에서 동일 도구가 3회 이상 등장하면 window_duplicate로
        # 탐지되므로(default duplicate_in_window_threshold=3), "위반 없음"을 보장하려면
        # 어떤 5-윈도우에서도 각 도구가 최대 2회까지만 등장하도록 시퀀스를 구성한다.
        for name in ["search", "summarize", "calculate", "translate", "search", "summarize"]:
            verdict = guardrail.check_before_tool_call("t1", name, {"q": "x"})
            assert verdict.block is False
            assert verdict.gate is None
            guardrail.record_tool_call("t1", name, {"q": "x"})


class TestLoopDetectionBlocks:
    def test_third_consecutive_call_blocks(self):
        guardrail = LiveGuardrail(
            loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, on_loop_detected="fail"),
        )
        v1 = guardrail.check_before_tool_call("t1", "search", {})
        assert v1.block is False
        guardrail.record_tool_call("t1", "search", {})

        v2 = guardrail.check_before_tool_call("t1", "search", {})
        assert v2.block is False
        guardrail.record_tool_call("t1", "search", {})

        v3 = guardrail.check_before_tool_call("t1", "search", {})
        assert v3.block is True
        assert v3.gate == "B"
        assert "loop_detection" in v3.reason

    def test_on_loop_detected_record_does_not_block(self):
        # on_loop_detected 기본값("record")이면 위반이 감지돼도 차단하지 않는다 —
        # 기존 배치 경로의 "감지는 하되 실패로 강제하지 않음" 시맨틱을 그대로 존중.
        guardrail = LiveGuardrail(
            loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),  # on_loop_detected="record"
        )
        for _ in range(4):
            verdict = guardrail.check_before_tool_call("t1", "search", {})
            assert verdict.block is False
            guardrail.record_tool_call("t1", "search", {})


class TestScopeBlocks:
    def test_forbidden_tool_blocks_immediately(self):
        guardrail = LiveGuardrail(
            scope=ScopeConfig(forbidden_tools=["shell_exec"], fail_on_violation=True),
        )
        verdict = guardrail.check_before_tool_call("t1", "shell_exec", {"cmd": "ls"})
        assert verdict.block is True
        assert verdict.gate == "B"
        assert "scope violation" in verdict.reason

    def test_fail_on_violation_false_does_not_block(self):
        guardrail = LiveGuardrail(
            scope=ScopeConfig(forbidden_tools=["shell_exec"], fail_on_violation=False),
        )
        verdict = guardrail.check_before_tool_call("t1", "shell_exec", {"cmd": "ls"})
        assert verdict.block is False


class TestToolParameterSafetyBlocks:
    def test_dangerous_pattern_blocks(self):
        guardrail = LiveGuardrail(
            tool_parameter_safety=ToolParameterSafetyConfig(fail_on_dangerous=True),
        )
        verdict = guardrail.check_before_tool_call(
            "t1", "shell_exec", {"cmd": "rm -rf / && echo done"},
        )
        assert verdict.block is True
        assert verdict.gate == "B"


class TestDeadlockBlocks:
    def test_depth_exceeded_blocks(self):
        guardrail = LiveGuardrail(
            deadlock=DeadlockConfig(max_delegation_depth=2, fail_on_deadlock=True),
        )
        for i in range(5):
            guardrail.record_tool_call("t1", "delegate_agent", {"depth": i})
        verdict = guardrail.check_before_tool_call("t1", "delegate_agent", {"depth": 5})
        assert verdict.block is True
        assert verdict.gate == "B"
        assert "deadlock" in verdict.reason


class TestSnapshotEqualsBatchEvaluators:
    """REQ-4/5: record_tool_call 누적 이후 snapshot()이 배치 eval_* 직접 호출과 byte-diff 동일해야 한다."""

    def test_snapshot_matches_direct_eval_calls(self):
        guardrail = LiveGuardrail(
            loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
            deadlock=DeadlockConfig(),
            scope=ScopeConfig(allowed_tools=["search", "summarize"]),
            tool_parameter_safety=ToolParameterSafetyConfig(),
        )
        calls = [
            ("search", {"q": "a"}),
            ("summarize", {"text": "b"}),
            ("search", {"q": "c"}),
        ]
        for name, params in calls:
            guardrail.record_tool_call("t1", name, params)

        snap = guardrail.snapshot()

        tool_calls = [{"name": n, "arguments": p} for n, p in calls]
        expected_loop = gate_b_evaluators.eval_loop_detection(tool_calls, None, guardrail._loop_detection)
        expected_deadlock = gate_b_evaluators.eval_deadlock(tool_calls, None, guardrail._deadlock)
        expected_scope = gate_b_evaluators.eval_scope(tool_calls, guardrail._scope)
        expected_tps = gate_b_evaluators.eval_tool_parameter_safety(tool_calls, guardrail._tool_parameter_safety)

        assert snap["loop_detection"] == expected_loop
        assert snap["deadlock"] == expected_deadlock
        assert snap["scope"] == expected_scope
        assert snap["tool_parameter_safety"] == expected_tps

    def test_snapshot_only_includes_configured_metrics(self):
        guardrail = LiveGuardrail(scope=ScopeConfig())
        guardrail.record_tool_call("t1", "search", {})
        snap = guardrail.snapshot()
        assert set(snap.keys()) == {"scope"}


class TestToTaskExtraBatchIntegration:
    """REQ-6: to_task_extra()로 만든 extra를 record_task()에 넘겼을 때 Gate B가
    동일한 tool_calls를 직접 배치 경로(gate_b_evaluators)로 넣었을 때와 동일한
    점수를 내야 한다 — 라이브/배치 이중 소스가 생기지 않음을 확인."""

    def test_gate_b_score_matches_direct_extra(self):
        scope_cfg = ScopeConfig(allowed_tools=["search"])
        calls = [("search", {"q": "a"}), ("search", {"q": "b"})]

        guardrail = LiveGuardrail(scope=scope_cfg)
        for name, params in calls:
            guardrail.record_tool_call("t1", name, params)
        live_extra = guardrail.to_task_extra()

        tool_calls = [{"name": n, "arguments": p} for n, p in calls]
        direct_extra = {"scope": gate_b_evaluators.eval_scope(tool_calls, scope_cfg)}

        assert live_extra == direct_extra

        monitor_live = PerformanceMonitor(output_dir="/tmp")
        monitor_live.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0, extra=live_extra,
        ))
        report_live = monitor_live.generate_report()

        monitor_direct = PerformanceMonitor(output_dir="/tmp")
        monitor_direct.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0, extra=direct_extra,
        ))
        report_direct = monitor_direct.generate_report()

        b_live = report_live.to_dict()["extra_metrics"]["harness_groups"]["B"]
        b_direct = report_direct.to_dict()["extra_metrics"]["harness_groups"]["B"]
        assert b_live == b_direct


class TestLiveVerdictDefaults:
    def test_default_verdict_is_non_blocking(self):
        v = LiveVerdict(block=False)
        assert v.gate is None
        assert v.reason is None
        assert v.detail == {}


# ── Gate E (SPEC-019 Rollout 3단계) ──────────────────────────────────────────


class TestToolAuthorizationBlocks:
    def test_restricted_tool_blocks(self):
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker(restricted_tools=["rm"]))
        verdict = guardrail.check_before_tool_call("t1", "rm", {"path": "/tmp/x"})
        assert verdict.block is True
        assert verdict.gate == "E"
        # peek이므로 실제 tracker 로그에는 남지 않아야 한다 (순수 조회).
        assert guardrail._tool_authorization.tool_calls == []

    def test_unauthorized_tool_blocks(self):
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker(allowed_tools=["search"]))
        verdict = guardrail.check_before_tool_call("t1", "shell_exec", {})
        assert verdict.block is True
        assert verdict.gate == "E"

    def test_dangerous_params_blocks(self):
        # SPEC-019 Rollout 3단계 구현 중 발견/수정: 초안 REQ-3에는 has_dangerous_params가
        # 빠져 있었으나, 이는 명백한 차단 대상이라 SPEC 문서와 함께 보정했다.
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker())
        verdict = guardrail.check_before_tool_call("t1", "shell", {"cmd": "sudo rm -rf /"})
        assert verdict.block is True
        assert verdict.gate == "E"

    def test_clean_call_does_not_block_and_leaves_no_log(self):
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker())
        verdict = guardrail.check_before_tool_call("t1", "search", {"q": "hi"})
        assert verdict.block is False
        assert guardrail._tool_authorization.tool_calls == []


class TestPrivilegeEscalationBlocks:
    def test_escalation_blocks(self):
        guardrail = LiveGuardrail(privilege_escalation=PrivilegeEscalationDetector())
        guardrail.record_tool_call("t1", "web_search", {})
        verdict = guardrail.check_before_tool_call("t1", "exec_shell", {})
        assert verdict.block is True
        assert verdict.gate == "E"
        # peek이므로 분석기 내부 이력에는 남지 않아야 한다.
        assert guardrail._privilege_escalation.escalation_events == []

    def test_no_escalation_does_not_block(self):
        guardrail = LiveGuardrail(privilege_escalation=PrivilegeEscalationDetector())
        verdict = guardrail.check_before_tool_call("t1", "web_search", {})
        assert verdict.block is False


class TestToolChainAttackBlocks:
    def test_attack_pattern_blocks(self):
        guardrail = LiveGuardrail(tool_chain_attack=ToolChainAttackDetector())
        guardrail.record_tool_call("t1", "query_database", {})
        guardrail.record_tool_call("t1", "encode_data", {})
        verdict = guardrail.check_before_tool_call("t1", "post_request", {})
        assert verdict.block is True
        assert verdict.gate == "E"
        assert guardrail._tool_chain_attack.detections == []

    def test_clean_sequence_does_not_block(self):
        guardrail = LiveGuardrail(tool_chain_attack=ToolChainAttackDetector())
        guardrail.record_tool_call("t1", "search", {})
        verdict = guardrail.check_before_tool_call("t1", "summarize", {})
        assert verdict.block is False


class TestToolAuthorizationSummary:
    def test_summary_matches_manual_aggregation(self):
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker(restricted_tools=["rm"]))
        guardrail.record_tool_call("t1", "search", {})
        guardrail.record_tool_call("t1", "rm", {"path": "/x"})
        snap = guardrail.snapshot()
        assert snap["tool_authorization"] == {
            "unauthorized_calls": 0,
            "restricted_calls": 1,
            "dangerous_param_calls": 0,
            "total_violations": 1,
            "total_calls": 2,
            "compliance_rate": round((2 - 1) / 2, 4),
        }

    def test_no_confirmed_calls_omits_key(self):
        guardrail = LiveGuardrail(tool_authorization=ToolAuthorizationTracker())
        snap = guardrail.snapshot()
        assert "tool_authorization" not in snap


class TestGateESnapshotIdempotency:
    """snapshot()을 여러 번 호출해도 체인 분석기(privilege_escalation/tool_chain_attack)
    내부 이력이 중복 누적되지 않아야 한다 — check_before_tool_call의 peek과 동일한 원칙."""

    def test_snapshot_does_not_grow_tracker_history(self):
        guardrail = LiveGuardrail(
            tool_authorization=ToolAuthorizationTracker(),
            privilege_escalation=PrivilegeEscalationDetector(),
            tool_chain_attack=ToolChainAttackDetector(),
        )
        guardrail.record_tool_call("t1", "web_search", {})
        guardrail.record_tool_call("t1", "exec_shell", {})

        snap1 = guardrail.snapshot()
        snap2 = guardrail.snapshot()
        assert snap1 == snap2
        assert len(guardrail._privilege_escalation.escalation_events) == 0
        assert len(guardrail._tool_chain_attack.detections) == 0
        # tool_authorization은 record_tool_call() 시점에 이미 확정 반영되므로 누적되어야 한다.
        assert len(guardrail._tool_authorization.tool_calls) == 2

    def test_snapshot_matches_direct_analysis(self):
        guardrail = LiveGuardrail(
            privilege_escalation=PrivilegeEscalationDetector(),
            tool_chain_attack=ToolChainAttackDetector(),
        )
        guardrail.record_tool_call("t1", "web_search", {})
        guardrail.record_tool_call("t1", "exec_shell", {})
        snap = guardrail.snapshot()

        expected_pe = PrivilegeEscalationDetector().analyze_privilege_chain(
            "t1", ["web_search", "exec_shell"],
        )
        expected_tc = ToolChainAttackDetector().analyze_tool_chain(
            "t1", ["web_search", "exec_shell"],
        )
        assert snap["privilege_escalation"] == expected_pe
        assert snap["tool_chain_attack"] == expected_tc


class TestToTaskExtraGateEIntegration:
    """REQ-6: Gate E도 Gate B와 동일하게 to_task_extra()가 만든 extra를
    record_task()에 넘겼을 때 직접 만든 extra와 동일한 Gate E 점수를 내야 한다."""

    def test_gate_e_score_matches_direct_extra(self):
        calls = [("web_search", {}), ("exec_shell", {})]

        guardrail = LiveGuardrail(
            tool_authorization=ToolAuthorizationTracker(),
            privilege_escalation=PrivilegeEscalationDetector(),
            tool_chain_attack=ToolChainAttackDetector(),
        )
        for name, params in calls:
            guardrail.record_tool_call("t1", name, params)
        live_extra = guardrail.to_task_extra()

        direct_pe = PrivilegeEscalationDetector().analyze_privilege_chain(
            "t1", [n for n, _ in calls],
        )
        direct_tc = ToolChainAttackDetector().analyze_tool_chain(
            "t1", [n for n, _ in calls],
        )
        direct_extra = {
            "tool_authorization": {
                "unauthorized_calls": 0,
                "restricted_calls": 0,
                "dangerous_param_calls": 0,
                "total_violations": 0,
                "total_calls": 2,
                "compliance_rate": 1.0,
            },
            "privilege_escalation": direct_pe,
            "tool_chain_attack": direct_tc,
        }
        assert live_extra == direct_extra

        monitor_live = PerformanceMonitor(output_dir="/tmp")
        monitor_live.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0, extra=live_extra,
        ))
        report_live = monitor_live.generate_report()

        monitor_direct = PerformanceMonitor(output_dir="/tmp")
        monitor_direct.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0, extra=direct_extra,
        ))
        report_direct = monitor_direct.generate_report()

        e_live = report_live.to_dict()["extra_metrics"]["harness_groups"]["E"]
        e_direct = report_direct.to_dict()["extra_metrics"]["harness_groups"]["E"]
        assert e_live == e_direct
