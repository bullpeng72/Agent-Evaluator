"""
tests/test_shared_metrics_primitives.py
===========================================
SPEC-018 Phase 0: gates/shared_metrics.py의 범용 누적 프리미티브 단위 테스트.

PerformanceMonitor/TaskResult와 무관한 순수 단위 테스트 — 이 프리미티브들은
아직 어떤 Gate의 aggregate.py에도 배선되지 않았으므로(Phase 0), 다른 코드 경로에
영향이 없는 완전 추가적(additive) 변경이다.
"""
from __future__ import annotations

import pytest

from agent_evaluator.gates.shared_metrics import (
    MonotonicFlag,
    RunningAverage,
    RunningCategoryCounter,
    RunningCount,
    RunningLastValue,
    RunningSum,
    RunningWindow,
)


class TestRunningAverage:
    def test_empty_average_is_none(self):
        ra = RunningAverage()
        assert ra.average() is None
        assert ra.count == 0

    def test_average_matches_manual_computation(self):
        ra = RunningAverage()
        values = [1.0, 2.0, 3.0, 4.0]
        for v in values:
            ra.add(v)
        assert ra.average() == pytest.approx(sum(values) / len(values))
        assert ra.count == len(values)

    def test_single_value(self):
        ra = RunningAverage()
        ra.add(5.0)
        assert ra.average() == pytest.approx(5.0)
        assert ra.count == 1


class TestRunningSum:
    def test_empty_sum_is_zero(self):
        rs = RunningSum()
        assert rs.total == 0.0

    def test_sum_accumulates(self):
        rs = RunningSum()
        for v in [1.5, 2.5, 3.0]:
            rs.add(v)
        assert rs.total == pytest.approx(7.0)


class TestRunningLastValue:
    def test_initial_value_is_none(self):
        rlv = RunningLastValue()
        assert rlv.get() is None

    def test_overwrites_on_each_set(self):
        rlv = RunningLastValue()
        rlv.set({"breach_window": 10})
        rlv.set({"breach_window": 20})
        assert rlv.get() == {"breach_window": 20}


class TestRunningWindow:
    def test_values_preserve_order(self):
        rw = RunningWindow(maxlen=3)
        for v in [1, 2, 3]:
            rw.add(v)
        assert rw.values() == [1, 2, 3]

    def test_maxlen_evicts_oldest(self):
        rw = RunningWindow(maxlen=3)
        for v in [1, 2, 3, 4, 5]:
            rw.add(v)
        assert rw.values() == [3, 4, 5]

    def test_resize_larger_preserves_existing(self):
        rw = RunningWindow(maxlen=2)
        rw.add(1)
        rw.add(2)
        rw.resize(4)
        rw.add(3)
        assert rw.values() == [1, 2, 3]

    def test_resize_smaller_truncates_from_left(self):
        rw = RunningWindow(maxlen=5)
        for v in [1, 2, 3, 4, 5]:
            rw.add(v)
        rw.resize(2)
        assert rw.values() == [4, 5]

    def test_resize_to_same_value_is_noop(self):
        rw = RunningWindow(maxlen=3)
        rw.add(1)
        rw.resize(3)
        assert rw.values() == [1]


class TestMonotonicFlag:
    def test_initial_state_unset(self):
        flag = MonotonicFlag()
        assert flag.is_set() is False

    def test_mark_sets_permanently(self):
        flag = MonotonicFlag()
        flag.mark()
        assert flag.is_set() is True
        # 재호출해도 여전히 True(단조 증가 — 되돌릴 방법이 없음을 확인)
        flag.mark()
        assert flag.is_set() is True


class TestRunningCount:
    def test_initial_count_is_zero(self):
        rc = RunningCount()
        assert rc.count == 0

    def test_default_increment_is_one(self):
        rc = RunningCount()
        rc.add()
        rc.add()
        assert rc.count == 2

    def test_custom_increment(self):
        rc = RunningCount()
        rc.add(5)
        rc.add(3)
        assert rc.count == 8


class TestRunningCategoryCounter:
    def test_empty_snapshot(self):
        rcc = RunningCategoryCounter()
        assert rcc.snapshot() == {}

    def test_counts_by_category(self):
        rcc = RunningCategoryCounter()
        for k in ["resource", "resource", "communication", "resource"]:
            rcc.add(k)
        assert rcc.snapshot() == {"resource": 3, "communication": 1}

    def test_snapshot_is_a_copy(self):
        rcc = RunningCategoryCounter()
        rcc.add("a")
        snap = rcc.snapshot()
        snap["a"] = 999
        assert rcc.snapshot() == {"a": 1}
