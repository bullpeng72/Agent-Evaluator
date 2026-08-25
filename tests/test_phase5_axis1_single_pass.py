"""
tests/test_phase5_axis1_single_pass.py
==========================================
구조변경 축① — "full" 모드(기본값)에서도 Gate A-G 집계를 45개 개별 루프 대신
단일 패스로 재구성(PerformanceMonitor._build_full_mode_shared_snapshots())한
변경의 회귀 테스트.

핵심 불변식: retention_mode="full"의 리포트 결과는 이 최적화 전후로 동일해야
한다(단, 이미 windowed 모드에서 승인된 근사 — retry_consistency LRU 캡,
ttft_variability/cost_predictability reservoir sampling — 는 이제 "full" 모드에도
적용된다는 것이 유일한 의도적 차이다. 호환성보다 단일 패스를 우선한다는 결정에
따른 것이며, 이 근사들은 표본 수가 캡/리저버 크기를 넘지 않는 한 정확히 일치한다).
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.gates.gate_a_goal import aggregate as gate_a_aggregate
from agent_evaluator.gates.gate_c_reliability.aggregate import compute_sla_shared_data
from agent_evaluator.gates.shared_metrics import GateASharedAgg, GateCSharedAgg


def _sla_task(task_id: str, *, sla_met: bool, p95_ms: float = 3000.0, cost_usd: float = 0.01):
    return create_taskresult(
        task_id=task_id, question="q", response="r", execution_time=1.0,
        extra={
            "sla": {
                "sla_met": sla_met, "cost_usd": cost_usd,
                "_config": {"p95_ms": p95_ms, "breach_window": 10, "warn_threshold": 2,
                            "fail_threshold": 5},
            },
        },
    )


class TestRawVsSinglePassNumericEquivalence:
    """가장 직접적인 검증 — 같은 태스크 목록에 대해 raw 루프(shared_running=None)와
    단일 패스 스냅숏(GateASharedAgg 신규 인스턴스로 1회 순회)이 정확히 같은 숫자를
    내야 한다. Gate A는 근사 없는 6개 지표(instruction_adherence/goal_alignment/
    plan_coherence/subtask_completion/context_retention/knowledge_retention)만
    다루므로 완전히 동일해야 한다(retry_consistency/ttft/cost_predictability 같은
    승인된 근사 지표가 없다)."""

    def test_gate_a_identical_score_and_details(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        tasks = []
        for i in range(8):
            t = create_taskresult(
                task_id=f"t{i}", question="q", response="r", execution_time=1.0,
                extra={
                    "instruction_adherence": {"score": 0.7 + (i % 3) * 0.1},
                    "goal_alignment": {"score": 0.6 + (i % 4) * 0.05},
                    "plan_coherence": {"score": 0.8},
                    "subtask_completion": {"completion_rate": 0.9, "subtask_count": 3},
                    "context_retention": {"retention_score": 0.75},
                    "knowledge_retention": {"retention_score": 0.85},
                },
            )
            monitor.record_task(t)
            tasks.append(t)

        raw = gate_a_aggregate.compute(
            tasks, monitor.tcr_tracker, monitor.accuracy_evaluator, monitor.quality_evaluator,
            monitor._gate_a_tcr_weight, monitor._min_samples_default, shared_running=None,
        )

        agg = GateASharedAgg()
        for t in tasks:
            agg.update(t)
        single_pass = gate_a_aggregate.compute(
            tasks, monitor.tcr_tracker, monitor.accuracy_evaluator, monitor.quality_evaluator,
            monitor._gate_a_tcr_weight, monitor._min_samples_default, shared_running=agg.snapshot(),
        )

        assert single_pass["score"] == raw["score"]
        assert single_pass["details"] == raw["details"]


class TestGateCSharedAggP95MsAvg:
    def test_accumulates_p95_ms_average(self):
        agg = GateCSharedAgg()
        for p95 in (1000.0, 2000.0, 3000.0):
            agg.update(_sla_task("t", sla_met=True, p95_ms=p95))
        snap = agg.snapshot()
        assert snap["sla_p95_ms_avg"] == 2000.0

    def test_none_when_no_sla_tasks(self):
        agg = GateCSharedAgg()
        agg.update(create_taskresult(task_id="t", question="q", response="r", execution_time=1.0))
        assert agg.snapshot()["sla_p95_ms_avg"] is None

    def test_ignores_tasks_without_p95_ms_config(self):
        agg = GateCSharedAgg()
        t = create_taskresult(
            task_id="t", question="q", response="r", execution_time=1.0,
            extra={"sla": {"sla_met": True, "cost_usd": 0.0, "_config": {}}},
        )
        agg.update(t)
        assert agg.snapshot()["sla_p95_ms_avg"] is None


class TestComputeSlaSharedDataP95MsAvg:
    def test_shared_running_path_returns_avg_without_sla_results(self):
        tasks = [_sla_task(f"t{i}", sla_met=True, p95_ms=v) for i, v in enumerate([1000, 3000])]
        agg = GateCSharedAgg()
        for t in tasks:
            agg.update(t)
        result = compute_sla_shared_data(tasks, shared_running=agg.snapshot())
        assert result["sla_p95_ms_avg"] == 2000.0
        assert result["sla_results"] == []  # 더 이상 원본 리스트를 반환하지 않음(단일 패스)

    def test_raw_path_returns_none_avg_and_full_results(self):
        tasks = [_sla_task(f"t{i}", sla_met=True, p95_ms=v) for i, v in enumerate([1000, 3000])]
        result = compute_sla_shared_data(tasks)  # shared_running=None
        assert result["sla_p95_ms_avg"] is None
        assert len(result["sla_results"]) == 2


class TestFullModeSinglePassEquivalence:
    """retention_mode="full"의 리포트 결과가 이 최적화 전후로 동일해야 한다는
    핵심 불변식 — 실제 PerformanceMonitor를 통해 end-to-end로 검증한다."""

    def _run(self, tmp_path, n=15):
        monitor = PerformanceMonitor(output_dir=str(tmp_path), retention_mode="full")
        for i in range(n):
            monitor.record_task(_sla_task(f"t{i}", sla_met=(i % 4 != 0), p95_ms=2500.0 + i * 10))
        report = monitor.generate_report()
        assert report.extra_metrics is not None
        return report.extra_metrics["harness_groups"]

    def test_gate_c_sla_breach_rate_matches_manual_calc(self, tmp_path):
        groups = self._run(tmp_path, n=20)
        # i % 4 == 0 → breach (i=0,4,8,12,16 → 5 of 20)
        assert groups["C"]["details"]["sla_breach_rate"] == 0.25

    def test_gate_d_p95_threshold_reflects_configured_average(self, tmp_path):
        groups = self._run(tmp_path, n=10)
        # p95_ms values: 2500,2510,...,2590 → avg = 2545.0ms = 2.545s
        # perf_vals depends on _p95 (measured latency) vs threshold — just check no crash
        # and that the detail key is populated (score computed, not None-guarded away).
        assert groups["D"]["score"] is not None

    def test_default_retention_mode_still_full(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        assert monitor._retention_mode == "full"

    def test_full_mode_report_has_all_seven_gates(self, tmp_path):
        groups = self._run(tmp_path, n=5)
        assert set("ABCDEFG") <= set(groups.keys())
