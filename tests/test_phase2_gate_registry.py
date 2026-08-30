"""
tests/test_phase2_gate_registry.py
=====================================
Phase 2(확장성 인프라) — PerformanceMonitor.register_gate()로 등록한 서드파티
Gate가 harness_groups/overall에 실제로 반영되는지, 내장 A-G 7개의 기존 동작을
전혀 건드리지 않는지 검증하는 end-to-end 테스트.
"""
from __future__ import annotations

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.gates.base import _g


def _monitor_with_tasks() -> PerformanceMonitor:
    m = PerformanceMonitor()
    for i in range(3):
        m.record_task(create_taskresult(
            task_id=f"t{i}", question="q", response="Seoul",
            ground_truth="Seoul", execution_time=1.0, extra={},
        ))
    return m


def _custom_cost_gate(tasks, min_samples_default):
    # (t.extra or {}) — 코드베이스 전반의 표준 관용구. extra는 기본값 None이라
    # 직접 .get()을 호출하면 AttributeError가 난다.
    scores: list[float] = []
    for t in tasks:
        v = (t.extra or {}).get("custom_cost")
        if v is not None:
            scores.append(v)
    if not scores:
        return _g(None, "Custom Cost Gate", {"avg_cost": None})
    avg = sum(scores) / len(scores)
    return _g(round(1.0 - min(1.0, avg), 4), "Custom Cost Gate", {"avg_cost": avg})


class TestRegisterGateValidation:
    def test_reserved_builtin_id_rejected(self):
        m = PerformanceMonitor()
        with pytest.raises(ValueError, match="reserved for the built-in Gates"):
            m.register_gate("A", _custom_cost_gate)

    def test_duplicate_registration_rejected(self):
        m = PerformanceMonitor()
        m.register_gate("COST", _custom_cost_gate)
        with pytest.raises(ValueError, match="already registered"):
            m.register_gate("COST", _custom_cost_gate)

    def test_multi_char_id_allowed(self):
        m = PerformanceMonitor()
        m.register_gate("CUSTOM_COST", _custom_cost_gate)  # 예외 없이 통과해야 함


class TestRegisterGateEndToEnd:
    def test_custom_gate_appears_in_harness_groups(self):
        m = _monitor_with_tasks()
        m.register_gate("COST", _custom_cost_gate)
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        assert "COST" in hg
        assert hg["COST"]["name"] == "Custom Cost Gate"

    def test_custom_gate_with_no_matching_data_yields_none_not_crash(self):
        """커스텀 Gate가 조회하는 extra 필드가 없으면 None — 크래시 없이 우아하게 처리."""
        m = _monitor_with_tasks()
        m.register_gate("COST", _custom_cost_gate)
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["harness_groups"]["COST"]["score"] is None

    def test_custom_gate_contributes_to_overall(self):
        m = _monitor_with_tasks()
        for t in m.tcr_tracker.tasks:
            assert t.extra is not None  # _monitor_with_tasks()가 extra={}로 생성함
            t.extra["custom_cost"] = 0.0  # avg_cost=0.0 → COST 점수=1.0
        m.register_gate("COST", _custom_cost_gate)
        report = m.generate_report()
        assert report.extra_metrics is not None
        overall = report.extra_metrics["harness_groups"]["overall"]
        assert "COST" in overall["scored_group_ids"]

    def test_builtin_gates_unaffected_by_custom_registration(self):
        """커스텀 Gate 등록이 A-G 내장 Gate의 결과를 조금도 바꾸지 않아야 한다."""
        m1 = _monitor_with_tasks()
        report1 = m1.generate_report()
        assert report1.extra_metrics is not None
        hg1 = report1.extra_metrics["harness_groups"]

        m2 = _monitor_with_tasks()
        m2.register_gate("COST", _custom_cost_gate)
        report2 = m2.generate_report()
        assert report2.extra_metrics is not None
        hg2 = report2.extra_metrics["harness_groups"]

        for gate_id in "ABCDEFG":
            assert hg1[gate_id] == hg2[gate_id], f"Gate {gate_id} 결과가 커스텀 Gate 등록으로 바뀜"

    def test_failing_custom_gate_does_not_crash_report_generation(self):
        def _broken_gate(tasks, min_samples_default):
            raise RuntimeError("boom")

        m = _monitor_with_tasks()
        m.register_gate("BROKEN", _broken_gate)
        with pytest.warns(RuntimeWarning, match="BROKEN"):
            report = m.generate_report()  # 예외가 전파되지 않아야 함
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        assert "BROKEN" not in hg  # 실패한 Gate는 이번 리포트에서 조용히 제외
        assert "A" in hg  # 다른 Gate는 정상 계산됨
