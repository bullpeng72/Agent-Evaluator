"""
tests/test_retry_correction_tracker.py
=======================================
RetryCorrectionTracker 테스트
"""
import pytest

from agent_evaluator.core.trackers.layer2 import RetryCorrectionTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single_success():
    return [{"success": True, "duration": 1.0}]


def _retry_then_success():
    return [
        {"success": False, "retry_reason": "timeout", "duration": 1.2},
        {"success": True, "duration": 0.8},
    ]


def _three_attempts_fail():
    return [
        {"success": False, "retry_reason": "timeout", "duration": 1.0},
        {"success": False, "retry_reason": "rate_limit", "duration": 1.0},
        {"success": False, "retry_reason": "timeout", "duration": 1.0},
    ]


# ===========================================================================
# track_attempts
# ===========================================================================

class TestTrackAttempts:
    def test_empty_log_ignored(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", [])
        assert len(t.attempts) == 0

    def test_single_success_recorded(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())
        assert len(t.attempts) == 1
        assert t.attempts[0]["first_attempt_success"] is True
        assert t.attempts[0]["final_success"] is True
        assert t.attempts[0]["total_attempts"] == 1

    def test_retry_then_success_recorded(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())
        a = t.attempts[0]
        assert a["first_attempt_success"] is False
        assert a["final_success"] is True
        assert a["total_attempts"] == 2

    def test_retry_reasons_captured(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())
        assert "timeout" in t.attempts[0]["retry_reasons"]

    def test_task_type_stored(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success(), task_type="qa")
        assert t.attempts[0]["task_type"] == "qa"

    def test_total_retry_time_excludes_first_attempt(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())
        # Only second attempt (0.8s) counts as retry time
        assert t.attempts[0]["total_retry_time"] == pytest.approx(0.8)

    def test_multiple_tasks_accumulated(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())
        t.track_attempts("t2", _retry_then_success())
        assert len(t.attempts) == 2


# ===========================================================================
# get_retry_metrics — empty state
# ===========================================================================

class TestGetRetryMetricsEmpty:
    def test_empty_returns_structured_zeros(self):
        t = RetryCorrectionTracker()
        m = t.get_retry_metrics()
        assert m["total_tasks_with_retries"] == 0
        assert m["retry_rate"] == 0.0
        assert m["first_attempt_success_rate"] == 0.0
        assert m["eventual_success_rate"] == 0.0
        assert m["avg_retry_time"] == 0.0
        assert m["overall_retry_rate"] == 0.0

    def test_empty_has_all_required_keys(self):
        t = RetryCorrectionTracker()
        m = t.get_retry_metrics()
        for key in (
            "total_tasks_with_retries", "retry_rate", "first_attempt_success_rate",
            "eventual_success_rate", "retry_success_count", "correction_success_rate",
            "avg_attempts_per_task", "total_retry_time", "avg_retry_time",
            "overall_retry_rate", "avg_retries_per_task",
        ):
            assert key in m, f"missing key: {key}"


# ===========================================================================
# get_retry_metrics — populated
# ===========================================================================

class TestGetRetryMetricsPopulated:
    def test_no_retries_zero_retry_rate(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())
        t.track_attempts("t2", _single_success())
        m = t.get_retry_metrics()
        assert m["retry_rate"] == pytest.approx(0.0)
        assert m["first_attempt_success_rate"] == pytest.approx(100.0)

    def test_retry_rate_50_percent(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())
        t.track_attempts("t2", _retry_then_success())
        m = t.get_retry_metrics()
        assert m["retry_rate"] == pytest.approx(50.0)

    def test_first_attempt_success_rate(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())       # first = True
        t.track_attempts("t2", _retry_then_success())   # first = False
        m = t.get_retry_metrics()
        assert m["first_attempt_success_rate"] == pytest.approx(50.0)

    def test_eventual_success_rate(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())   # final = True
        t.track_attempts("t2", _three_attempts_fail())  # final = False
        m = t.get_retry_metrics()
        assert m["eventual_success_rate"] == pytest.approx(50.0)

    def test_correction_success_rate(self):
        """태스크 중 재시도 필요했고 최종 성공한 비율"""
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())   # needed retry, succeeded
        t.track_attempts("t2", _three_attempts_fail())  # needed retry, failed
        m = t.get_retry_metrics()
        assert m["correction_success_rate"] == pytest.approx(50.0)

    def test_avg_retry_time_excludes_no_retry_tasks(self):
        """avg_retry_time은 재시도가 있는 태스크만 대상으로 계산"""
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())       # no retry
        t.track_attempts("t2", _retry_then_success())   # retry_time = 0.8
        m = t.get_retry_metrics()
        assert m["avg_retry_time"] == pytest.approx(0.8)

    def test_overall_retry_rate_formula(self):
        """overall_retry_rate = (총 시도 - 총 태스크) / 총 시도 × 100"""
        t = RetryCorrectionTracker()
        # t1: 1 attempt, t2: 2 attempts → 3 total, 1 retry
        t.track_attempts("t1", _single_success())
        t.track_attempts("t2", _retry_then_success())
        m = t.get_retry_metrics()
        expected = (3 - 2) / 3 * 100
        assert m["overall_retry_rate"] == pytest.approx(expected, rel=1e-3)


# ===========================================================================
# analyze_failure_patterns
# ===========================================================================

class TestAnalyzeFailurePatterns:
    def test_empty_returns_empty_patterns(self):
        t = RetryCorrectionTracker()
        result = t.analyze_failure_patterns()
        assert result == {"patterns": {}}

    def test_no_failures_empty_patterns(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _single_success())
        result = t.analyze_failure_patterns()
        assert result == {"patterns": {}}

    def test_patterns_sorted_by_frequency(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", [
            {"success": False, "retry_reason": "timeout"},
            {"success": False, "retry_reason": "timeout"},
            {"success": False, "retry_reason": "rate_limit"},
            {"success": True},
        ])
        result = t.analyze_failure_patterns()
        patterns = result["patterns"]
        assert patterns["timeout"] == 2
        assert patterns["rate_limit"] == 1
        assert result["most_common"] == "timeout"

    def test_most_common_field_present(self):
        t = RetryCorrectionTracker()
        t.track_attempts("t1", _retry_then_success())
        result = t.analyze_failure_patterns()
        assert "most_common" in result


# ===========================================================================
# __repr__
# ===========================================================================

def test_repr_empty():
    t = RetryCorrectionTracker()
    assert "RetryCorrectionTracker" in repr(t)
    assert "attempts=0" in repr(t)


def test_repr_after_track():
    t = RetryCorrectionTracker()
    t.track_attempts("t1", _single_success())
    assert "attempts=1" in repr(t)
