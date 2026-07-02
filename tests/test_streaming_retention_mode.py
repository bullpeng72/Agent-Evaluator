"""
tests/test_streaming_retention_mode.py
========================================
SPEC-004: 옵트인 스트리밍 모니터 모드(retention_mode) 검증.

REQ-1: PerformanceMonitor(retention_mode="full"|"windowed", window_size=int) 추가.
       기본값 "full"은 기존 동작(무제한 리스트)과 100% 동일해야 한다.
REQ-2: "windowed"에서 self.tasks는 deque(maxlen=window_size)처럼 동작한다.
       Gate A/C의 TCR 컴포넌트는 record_task() 시점에 갱신되는 러닝 집계로 전체
       이력을 반영한다(축소 범위 — 다른 Gate 지표는 windowed 태스크 목록만으로 재계산됨,
       자세한 내용은 SPEC-004 문서의 구현 노트 참고).
REQ-3: "windowed"에서 get_report_by_type/get_report_by_framework/export_by_framework/
       register_aggregator 호출 시 UserWarning이 매번 발생해야 한다.
REQ-4: window_size는 양의 정수만 허용 — 0 이하이면 ValueError.
"""
import warnings

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id: str, completion_score: float, **kwargs):
    return create_taskresult(
        task_id=task_id,
        question="q",
        response="r",
        execution_time=0.1,
        task_type="qa",
        completion_score=completion_score,
        **kwargs,
    )


def _hg(monitor: PerformanceMonitor):
    """모니터 현재 태스크 목록으로 harness groups를 계산한다 (private API — 기존
    tests/test_min_sample_guard.py의 헬퍼와 동일한 패턴)."""
    return monitor._compute_harness_groups(
        tasks=list(monitor.tcr_tracker.tasks),
        security_metrics=monitor._collect_security_metrics(),
        layer1=monitor._collect_layer1_metrics(),
        layer2=monitor._collect_layer2_metrics(),
        ttft_variability_config=monitor._ttft_variability_config,
        cost_predictability_config=monitor._cost_predictability_config,
    )


class TestRetentionModeDefaultIsFull:
    """REQ-1: retention_mode 미지정 시 기존 동작과 100% 동일."""

    def test_default_retention_mode_is_full(self):
        m = PerformanceMonitor()
        assert m._retention_mode == "full"
        assert m._window_size == 10000

    def test_full_mode_tasks_grow_unbounded(self):
        m = PerformanceMonitor()
        for i in range(50):
            m.record_task(_task(f"t{i}", 1.0))
        assert len(m.tasks) == 50

    def test_full_mode_no_windowed_warning_on_apis(self):
        m = PerformanceMonitor()
        m.record_task(_task("t0", 1.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.get_report_by_type("qa")
            m.get_report_by_framework("native")
            m.register_aggregator("noop", lambda tasks: len(tasks))
            _retention_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning) and "retention_mode" in str(x.message)
            ]
            assert _retention_warnings == []


class TestWindowSizeValidation:
    """REQ-4: window_size는 양의 정수만 허용."""

    @pytest.mark.parametrize("bad_size", [0, -1, -100])
    def test_non_positive_window_size_raises(self, bad_size):
        with pytest.raises(ValueError):
            PerformanceMonitor(window_size=bad_size)

    @pytest.mark.parametrize("bad_size", [0, -5])
    def test_non_positive_window_size_raises_even_in_full_mode(self, bad_size):
        # window_size는 retention_mode와 무관하게 항상 검증되어야 한다.
        with pytest.raises(ValueError):
            PerformanceMonitor(retention_mode="full", window_size=bad_size)

    def test_invalid_retention_mode_raises(self):
        with pytest.raises(ValueError):
            PerformanceMonitor(retention_mode="bogus")

    def test_positive_window_size_accepted(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=1)
        assert m._window_size == 1


class TestWindowedTaskCap:
    """REQ-2: windowed 모드에서 self.tasks가 deque(maxlen=window_size)처럼 동작."""

    def test_tasks_capped_at_window_size(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        assert len(m.tasks) == 5

    def test_tasks_keep_most_recent_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        kept_ids = [t.task_id for t in m.tasks]
        assert kept_ids == [f"t{i}" for i in range(15, 20)]

    def test_task_count_property_reflects_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        assert m.task_count == 5


class TestWindowedRunningTCRAggregate:
    """REQ-2: Gate A/C의 TCR 컴포넌트는 windowed 상태에서도 전체 이력을 반영해야 한다
    (러닝 집계로 유지되는 유일한 지표 — 축소 범위)."""

    def test_running_agg_reflects_full_history_beyond_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        # 20개 태스크 중 정확히 절반(10개)만 완전 성공(completion_score=1.0)
        for i in range(20):
            cs = 1.0 if i % 2 == 0 else 0.0
            m.record_task(_task(f"t{i}", cs))

        # 윈도우에는 마지막 5개(t15..t19)만 남음: i=16,18 → cs=1.0(2개), i=15,17,19 → cs=0.0(3개)
        # windowed-only TCR이라면 2/5 = 40.0%가 되어야 하지만, 러닝 집계는 전체 20개 기준
        # 10/20 = 50.0%를 반영해야 한다.
        assert len(m.tasks) == 5
        agg = m._running_tcr_agg
        assert agg["total_count"] == 20
        assert agg["full_success"] == 10
        assert agg["failures"] == 10
        assert agg["weighted_sum"] == pytest.approx(10.0)

    def test_gate_a_tcr_pct_uses_full_history_not_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            cs = 1.0 if i % 2 == 0 else 0.0
            m.record_task(_task(f"t{i}", cs))

        hg = _hg(m)
        # 전체 이력 기준 TCR = 50.0% (windowed-only라면 40.0%가 나와야 함 — 다른 값)
        assert hg["A"]["details"]["tcr_pct"] == pytest.approx(50.0)
        assert hg["C"]["details"]["tcr_pct"] == pytest.approx(50.0)

    def test_gate_a_tcr_pct_matches_full_mode_equivalent(self):
        # windowed 모드의 러닝 집계 기반 tcr_pct가, 동일한 태스크를 "full" 모드로
        # 기록했을 때의 tcr_pct와 정확히 일치하는지 교차 검증한다.
        tasks_scores = [1.0 if i % 3 == 0 else 0.0 for i in range(30)]

        m_full = PerformanceMonitor(retention_mode="full")
        for i, cs in enumerate(tasks_scores):
            m_full.record_task(_task(f"t{i}", cs))
        full_tcr = _hg(m_full)["A"]["details"]["tcr_pct"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=7)
        for i, cs in enumerate(tasks_scores):
            m_win.record_task(_task(f"t{i}", cs))
        windowed_tcr = _hg(m_win)["A"]["details"]["tcr_pct"]

        assert windowed_tcr == pytest.approx(full_tcr)


class TestWindowedRetentionWarnings:
    """REQ-3: windowed 모드에서 get_report_by_type/get_report_by_framework/
    export_by_framework/register_aggregator 호출 시 UserWarning이 매번 발생."""

    def _monitor(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        m.record_task(_task("t0", 1.0))
        return m

    def test_get_report_by_type_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.get_report_by_type("qa")

    def test_get_report_by_framework_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.get_report_by_framework("native")

    def test_register_aggregator_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.register_aggregator("noop", lambda tasks: len(tasks))

    def test_export_by_framework_warns(self, tmp_path):
        m = self._monitor()
        m.output_dir = tmp_path
        with pytest.warns(UserWarning, match="retention_mode"):
            m.export_by_framework("native", "out")

    def test_warning_fires_every_call_not_just_once(self):
        m = self._monitor()
        for _ in range(3):
            with pytest.warns(UserWarning, match="retention_mode"):
                m.get_report_by_type("qa")
