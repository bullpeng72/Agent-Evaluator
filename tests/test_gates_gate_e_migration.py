"""
tests/test_gates_gate_e_migration.py
=======================================
SPEC-000: Gate E(Security Boundary) 패키지 이관 검증.

기존 tests/test_gate_e_round3.py(44건)·tests/test_security_trackers.py(51건)는
수정 없이 그대로 통과해야 한다(re-export 검증). 이 파일은 이관 자체(항등성 +
monitor.py 위임 호출과 aggregate.compute() 직접 호출의 동등성)를 검증한다.
"""
from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id, extra):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0, extra=extra
    )


class TestConfigIdentity:
    def test_threat_severity_config_same_object(self):
        from agent_evaluator.decorators import ThreatSeverityConfig as C1
        from agent_evaluator.gates.gate_e_security.configs import ThreatSeverityConfig as C2
        from agent_evaluator import ThreatSeverityConfig as C3
        assert C1 is C2 is C3

    def test_compliance_config_same_object(self):
        from agent_evaluator.decorators import ComplianceConfig as C1
        from agent_evaluator.gates.gate_e_security.configs import ComplianceConfig as C2
        assert C1 is C2

    def test_threat_response_config_same_object(self):
        from agent_evaluator.decorators import ThreatResponseConfig as C1
        from agent_evaluator.gates.gate_e_security.configs import ThreatResponseConfig as C2
        assert C1 is C2


class TestEvaluatorIdentity:
    def test_eval_threat_severity_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_threat_severity as E1
        from agent_evaluator.gates.gate_e_security.evaluators import eval_threat_severity as E2
        assert E1 is E2

    def test_eval_compliance_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_compliance as E1
        from agent_evaluator.gates.gate_e_security.evaluators import eval_compliance as E2
        assert E1 is E2

    def test_eval_threat_response_same_object(self):
        from agent_evaluator.helpers.taskresult_helpers import eval_threat_response as E1
        from agent_evaluator.gates.gate_e_security.evaluators import eval_threat_response as E2
        assert E1 is E2


def _build_monitor_with_fixtures() -> PerformanceMonitor:
    # enable_security_metrics=False: 실제 보안 트래커가 record_task 중 extra를 재분석해
    # 덮어쓰지 않도록 한다 — 여기서는 순수 집계 로직만 검증하므로 수동 주입 extra를 그대로 유지.
    # _has_security_config_data(threat_severity/compliance/threat_response 등)가 있으므로
    # enable_security_metrics=False여도 score는 여전히 계산된다(None이 되지 않음).
    m = PerformanceMonitor(enable_security_metrics=False)
    # threat_severity: 3건
    m.record_task(_task("ts1", {"threat_severity": {"weighted_score": 2.0}}))
    m.record_task(_task("ts2", {"threat_severity": {"weighted_score": 4.0}}))
    m.record_task(_task("ts3", {"threat_severity": {"weighted_score": 6.0}}))
    # compliance: 3건
    m.record_task(_task("c1", {"compliance": {"compliance_score": 1.0}}))
    m.record_task(_task("c2", {"compliance": {"compliance_score": 0.8}}))
    m.record_task(_task("c3", {"compliance": {"compliance_score": 0.6}}))
    # privilege_escalation: 3건(1건 위반)
    m.record_task(_task("pe1", {"privilege_escalation": {"escalation_detected": False}}))
    m.record_task(_task("pe2", {"privilege_escalation": {"escalation_detected": False}}))
    m.record_task(_task("pe3", {"privilege_escalation": {"escalation_detected": True}}))
    # tool_chain_attack: 3건
    m.record_task(_task("tc1", {"tool_chain_attack": {"is_suspicious_chain": False}}))
    m.record_task(_task("tc2", {"tool_chain_attack": {"is_suspicious_chain": False}}))
    m.record_task(_task("tc3", {"tool_chain_attack": {"is_suspicious_chain": False}}))
    # output_leakage: 3건(1건 유출)
    m.record_task(_task("ol1", {"output_leakage": {"leakage_count": 0}}))
    m.record_task(_task("ol2", {"output_leakage": {"leakage_count": 1}}))
    m.record_task(_task("ol3", {"output_leakage": {"leakage_count": 0}}))
    # input_sanitization: 3건
    m.record_task(_task("is1", {"input_sanitization": {"threat_count": 0}}))
    m.record_task(_task("is2", {"input_sanitization": {"threat_count": 0}}))
    m.record_task(_task("is3", {"input_sanitization": {"threat_count": 1}}))
    # tool_authorization: 3건
    m.record_task(_task("ta1", {"tool_authorization": {"total_violations": 0}}))
    m.record_task(_task("ta2", {"tool_authorization": {"total_violations": 1}}))
    m.record_task(_task("ta3", {"tool_authorization": {"total_violations": 0}}))
    # threat_response: 2건만 (min_samples_default=3 미만 → 표본 부족 경고 트리거)
    m.record_task(_task("tr1", {"threat_response": {"response_score": 0.9}}))
    m.record_task(_task("tr2", {"threat_response": {"response_score": 0.7}}))
    # Gate E와 무관한 태스크 1건
    m.record_task(_task("n1", {}))
    return m


class TestGateEMigrationEquivalence:
    def test_monitor_delegation_matches_direct_aggregate_call(self):
        """monitor.generate_report() 경유 결과와 aggregate.compute() 직접 호출 결과가 동일해야 한다."""
        from agent_evaluator.gates.gate_e_security import aggregate as gate_e_aggregate

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        via_monitor = report.extra_metrics["harness_groups"]["E"]

        direct = gate_e_aggregate.compute(
            list(m.tcr_tracker.tasks),
            m.enable_security_metrics,
            m._min_samples_default,
        )
        assert via_monitor == direct

    def test_expected_values(self):
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        e = report.extra_metrics["harness_groups"]["E"]
        details = e["details"]

        assert round(details["avg_cvss_weighted_score"], 4) == 4.0  # (2+4+6)/3
        assert round(details["avg_compliance_score"], 4) == 0.8  # (1.0+0.8+0.6)/3
        assert details["privilege_escalation_rate"] is not None
        assert details["leakage_count"] == 1
        assert details["injection_count"] == 1
        assert details["unauthorized_calls_count"] == 1
        assert round(details["avg_threat_response"], 4) == 0.8  # (0.9+0.7)/2
        assert details["insufficient_data_warnings"] == [
            "threat_response: 2 samples < min_samples=3"
        ]
        assert e["name"] == "Security Boundary"
        assert e["score"] is not None
        assert e["status"] in ("pass", "warn", "fail")
        assert e["gate"] == e["status"]

    def test_details_key_set_unchanged(self):
        """details 딕셔너리의 키 이름이 이관 전과 동일한지 확인."""
        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        details = report.extra_metrics["harness_groups"]["E"]["details"]
        assert set(details.keys()) == {
            "threat_count", "threat_free_rate", "avg_cvss_weighted_score",
            "avg_compliance_score", "privilege_escalation_rate", "chain_attack_rate",
            "leakage_count", "leakage_defense_rate", "injection_count",
            "injection_defense_rate", "unauthorized_calls_count",
            "tool_authorization_rate", "avg_threat_response",
            "insufficient_data_warnings",
        }

    def test_security_metrics_disabled_no_config_data_yields_none_score(self):
        """enable_security_metrics=False + Harness Config 데이터 없음 → score=None."""
        from agent_evaluator.gates.gate_e_security import aggregate as gate_e_aggregate
        m = PerformanceMonitor(enable_security_metrics=False)
        m.record_task(_task("t0", {}))
        result = gate_e_aggregate.compute(
            list(m.tcr_tracker.tasks), m.enable_security_metrics, m._min_samples_default,
        )
        assert result["score"] is None
