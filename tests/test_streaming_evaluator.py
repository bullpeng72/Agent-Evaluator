"""Tests for StreamingEvaluator and SlidingWindow.

Covers window expiry, record aggregation, TCR/P95 computation,
get_stats()/get_all_stats(), and start()/stop() lifecycle.
The PerformanceMonitor dependency is always mocked.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator.streaming.evaluator import SlidingWindow, StreamingEvaluator, StreamingRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_monitor() -> MagicMock:
    return MagicMock()


def _make_evaluator(**kwargs) -> StreamingEvaluator:
    return StreamingEvaluator(monitor=_mock_monitor(), **kwargs)


def _record(
    task_id: str = "t",
    success: bool = True,
    execution_time: float = 1.0,
    tokens_used: int = 100,
    has_error: bool = False,
) -> StreamingRecord:
    return StreamingRecord(
        task_id=task_id,
        success=success,
        execution_time=execution_time,
        tokens_used=tokens_used,
        has_error=has_error,
    )


# ---------------------------------------------------------------------------
# SlidingWindow
# ---------------------------------------------------------------------------

def test_sliding_window_add_record():
    window = SlidingWindow(window_seconds=60)
    window.add(_record())
    stats = window.get_stats()
    assert stats["count"] == 1


def test_sliding_window_empty_returns_zero_stats():
    window = SlidingWindow(window_seconds=60)
    stats = window.get_stats()
    assert stats["count"] == 0
    assert stats["tcr"] == 0.0
    assert stats["p95_latency"] == 0.0
    assert stats["avg_tokens"] == 0.0


def test_sliding_window_evicts_expired_records():
    """Records older than window_seconds must be evicted."""
    window = SlidingWindow(window_seconds=1)
    # Add a record with a timestamp that is already expired
    old = _record(execution_time=99.0)
    old.timestamp = time.time() - 5  # 5 seconds ago — expired for a 1s window
    with window._lock:
        window._records.append(old)
    # Trigger eviction by calling get_stats
    stats = window.get_stats()
    assert stats["count"] == 0


def test_sliding_window_keeps_recent_records():
    """Records within the window must not be evicted."""
    window = SlidingWindow(window_seconds=300)
    window.add(_record(execution_time=1.5))
    window.add(_record(execution_time=2.5))
    assert window.get_stats()["count"] == 2


def test_sliding_window_tcr_all_success():
    window = SlidingWindow(window_seconds=300)
    for _ in range(5):
        window.add(_record(success=True))
    assert window.get_stats()["tcr"] == 100.0


def test_sliding_window_tcr_mixed():
    window = SlidingWindow(window_seconds=300)
    window.add(_record(success=True))
    window.add(_record(success=True))
    window.add(_record(success=False))
    window.add(_record(success=False))
    stats = window.get_stats()
    assert stats["tcr"] == 50.0


def test_sliding_window_p95_latency():
    """With 20 records, p95 should be the 19th sorted latency."""
    window = SlidingWindow(window_seconds=300)
    for i in range(1, 21):  # latencies 1..20
        window.add(_record(execution_time=float(i)))
    stats = window.get_stats()
    # p95_idx = max(0, int(20*0.95) - 1) = 18 → latencies[18] = 19.0
    assert stats["p95_latency"] == pytest.approx(19.0)


def test_sliding_window_avg_tokens():
    window = SlidingWindow(window_seconds=300)
    window.add(_record(tokens_used=100))
    window.add(_record(tokens_used=200))
    window.add(_record(tokens_used=300))
    assert window.get_stats()["avg_tokens"] == pytest.approx(200.0)


def test_sliding_window_error_rate():
    window = SlidingWindow(window_seconds=300)
    window.add(_record(has_error=True))
    window.add(_record(has_error=True))
    window.add(_record(has_error=False))
    window.add(_record(has_error=False))
    stats = window.get_stats()
    assert stats["error_rate"] == 50.0


# ---------------------------------------------------------------------------
# StreamingEvaluator.__init__()
# ---------------------------------------------------------------------------

def test_streaming_evaluator_creates_three_windows():
    ev = _make_evaluator()
    assert set(ev._windows.keys()) == {"1m", "5m", "1h"}


def test_streaming_evaluator_window_durations():
    ev = _make_evaluator()
    assert ev._windows["1m"].window_seconds == 60
    assert ev._windows["5m"].window_seconds == 300
    assert ev._windows["1h"].window_seconds == 3600


def test_streaming_evaluator_stores_monitor_and_flush_interval():
    monitor = _mock_monitor()
    ev = StreamingEvaluator(monitor=monitor, flush_interval=30)
    assert ev.monitor is monitor
    assert ev.flush_interval == 30


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

def test_record_adds_to_all_three_windows():
    ev = _make_evaluator()
    ev.record(task_id="t1", success=True, execution_time=1.0, tokens_used=50)
    for name, window in ev._windows.items():
        assert window.get_stats()["count"] == 1, f"Window '{name}' missing the record"


def test_record_multiple_tasks():
    ev = _make_evaluator()
    for i in range(5):
        ev.record(task_id=f"t{i}", success=True, execution_time=float(i + 1), tokens_used=100)
    assert ev.get_stats("5m")["count"] == 5


def test_record_calls_alert_handler_when_set():
    alert_handler = MagicMock()
    ev = StreamingEvaluator(monitor=_mock_monitor(), alert_handler=alert_handler)
    ev.record("t1", True, 1.0)
    alert_handler.evaluate.assert_called_once_with(ev)


def test_record_no_alert_handler_does_not_raise():
    ev = _make_evaluator()
    ev.record("t1", True, 1.0)  # must not raise


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------

def test_get_stats_valid_window_1m():
    ev = _make_evaluator()
    stats = ev.get_stats("1m")
    assert "count" in stats
    assert stats["window_seconds"] == 60


def test_get_stats_valid_window_5m():
    ev = _make_evaluator()
    stats = ev.get_stats("5m")
    assert stats["window_seconds"] == 300


def test_get_stats_valid_window_1h():
    ev = _make_evaluator()
    stats = ev.get_stats("1h")
    assert stats["window_seconds"] == 3600


def test_get_stats_invalid_window_raises():
    ev = _make_evaluator()
    with pytest.raises(ValueError):
        ev.get_stats("2h")


def test_get_stats_returns_required_keys():
    ev = _make_evaluator()
    ev.record("t1", True, 0.5, 80)
    stats = ev.get_stats("5m")
    for key in ("count", "tcr", "avg_latency", "p95_latency", "error_rate", "avg_tokens"):
        assert key in stats, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# get_all_stats()
# ---------------------------------------------------------------------------

def test_get_all_stats_returns_all_windows():
    ev = _make_evaluator()
    all_stats = ev.get_all_stats()
    assert set(all_stats.keys()) == {"1m", "5m", "1h"}


def test_get_all_stats_each_entry_has_count():
    ev = _make_evaluator()
    ev.record("t1", True, 1.0)
    all_stats = ev.get_all_stats()
    for name, stats in all_stats.items():
        assert "count" in stats, f"'{name}' stats missing 'count'"


# ---------------------------------------------------------------------------
# start() and stop()
# ---------------------------------------------------------------------------

def test_start_does_not_raise():
    ev = _make_evaluator(flush_interval=3600)  # very long — won't fire in test
    ev.start()
    ev.stop()


def test_start_twice_does_not_create_two_threads():
    ev = _make_evaluator(flush_interval=3600)
    ev.start()
    thread_before = ev._flush_thread
    ev.start()  # second call should be a no-op
    assert ev._flush_thread is thread_before
    ev.stop()


def test_stop_sets_running_false():
    ev = _make_evaluator()
    ev.start()
    ev.stop()
    assert ev._running is False


# ---------------------------------------------------------------------------
# Empty window edge cases
# ---------------------------------------------------------------------------

def test_empty_window_tcr_is_zero():
    ev = _make_evaluator()
    assert ev.get_stats("1m")["tcr"] == 0.0


def test_empty_window_p95_latency_is_zero():
    ev = _make_evaluator()
    assert ev.get_stats("5m")["p95_latency"] == 0.0


def test_empty_window_avg_tokens_is_zero():
    ev = _make_evaluator()
    assert ev.get_stats("1h")["avg_tokens"] == 0.0
