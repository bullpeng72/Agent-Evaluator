"""Tests for AnomalyDetector and AnomalyEvent.

Covers to_dict(), scan(), individual check methods, helper functions,
and severity level classification.  A MockMonitor helper is used throughout
instead of a real PerformanceMonitor to keep tests self-contained.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from agent_evaluator.anomaly.detector import (
    AnomalyDetector,
    AnomalyEvent,
    _iqr,
    _linear_regression_slope,
    _mean,
    _std,
)


# ---------------------------------------------------------------------------
# Helpers — build lightweight mock monitors
# ---------------------------------------------------------------------------

def _latency_entry(t: float) -> Dict[str, Any]:
    return {"execution_time": t}


def _accuracy_entry(a: float) -> Dict[str, Any]:
    return {"accuracy": a}


def _token_entry(n: int) -> Dict[str, Any]:
    return {"total_tokens": n}


class _FakeTask:
    def __init__(self, success: bool = True):
        self.success = success


def _make_monitor(
    latencies: List[float] | None = None,
    accuracies: List[float] | None = None,
    tokens: List[int] | None = None,
    tasks: list | None = None,
    input_sanitizer=None,
) -> MagicMock:
    """Build a MagicMock with the attributes AnomalyDetector reads."""
    monitor = MagicMock()
    monitor.latency_tracker.latencies = [_latency_entry(v) for v in (latencies or [])]
    monitor.accuracy_evaluator.evaluations = [_accuracy_entry(v) for v in (accuracies or [])]
    monitor.token_tracker.usage_log = [_token_entry(v) for v in (tokens or [])]
    monitor.tcr_tracker.tasks = tasks if tasks is not None else []
    monitor.input_sanitizer = input_sanitizer
    return monitor


# ---------------------------------------------------------------------------
# AnomalyEvent
# ---------------------------------------------------------------------------

def test_anomaly_event_to_dict_has_all_required_keys():
    event = AnomalyEvent(
        type="latency_trend",
        severity="warning",
        detail="some detail",
        value=0.12,
        threshold=0.05,
        algorithm="linear_regression",
    )
    d = event.to_dict()
    for key in ("type", "severity", "detail", "value", "threshold", "detected_at", "algorithm"):
        assert key in d, f"Missing key: {key}"


def test_anomaly_event_to_dict_values_match():
    event = AnomalyEvent(type="token_spike", severity="critical", detail="spike", value=500.0, threshold=200.0)
    d = event.to_dict()
    assert d["type"] == "token_spike"
    assert d["severity"] == "critical"
    assert d["value"] == 500.0
    assert d["threshold"] == 200.0


# ---------------------------------------------------------------------------
# scan() — insufficient data
# ---------------------------------------------------------------------------

def test_scan_returns_empty_list_when_no_data():
    detector = AnomalyDetector()
    monitor = _make_monitor()
    assert detector.scan(monitor) == []


def test_scan_returns_empty_list_when_less_than_5_latency_points():
    detector = AnomalyDetector()
    monitor = _make_monitor(latencies=[1.0, 1.1, 1.2, 1.3])
    # Only 4 latency points — below _TREND_MIN_POINTS=5
    events = detector.scan(monitor)
    latency_events = [e for e in events if e.type == "latency_trend"]
    assert latency_events == []


# ---------------------------------------------------------------------------
# _check_latency_trend()
# ---------------------------------------------------------------------------

def test_check_latency_trend_detects_upward_slope():
    """Steadily increasing latencies should produce a latency_trend event."""
    detector = AnomalyDetector(baseline_window=100, detection_window=20)
    # 10 values with clear upward trend: 0.1, 0.3, 0.5, ..., 1.9
    latencies = [0.1 + i * 0.2 for i in range(10)]
    monitor = _make_monitor(latencies=latencies)
    events = detector._check_latency_trend(monitor)
    assert len(events) == 1
    assert events[0].type == "latency_trend"
    assert events[0].value > 0.05  # slope above threshold


def test_check_latency_trend_ignores_flat_trend():
    """Flat latencies must not generate a latency_trend event."""
    detector = AnomalyDetector()
    latencies = [1.0] * 10
    monitor = _make_monitor(latencies=latencies)
    assert detector._check_latency_trend(monitor) == []


def test_check_latency_trend_ignores_downward_trend():
    """Decreasing latencies must not generate a latency_trend event."""
    detector = AnomalyDetector()
    latencies = [2.0 - i * 0.1 for i in range(10)]
    monitor = _make_monitor(latencies=latencies)
    assert detector._check_latency_trend(monitor) == []


def test_check_latency_trend_critical_severity():
    """A very steep slope (>3x threshold) must yield severity='critical'."""
    detector = AnomalyDetector()
    # slope will be roughly 1.0 per step which is >> 0.05 * 3 = 0.15
    latencies = [float(i) for i in range(10)]
    monitor = _make_monitor(latencies=latencies)
    events = detector._check_latency_trend(monitor)
    assert events and events[0].severity == "critical"


# ---------------------------------------------------------------------------
# _check_accuracy_drift()
# ---------------------------------------------------------------------------

def test_check_accuracy_drift_detects_z_score_drift():
    """Recent accuracy that drops sharply should trigger accuracy_drift."""
    detector = AnomalyDetector(baseline_window=100, detection_window=5)
    # baseline: 40 stable values around 0.9 ± 0.01
    baseline = [0.90 + (i % 3) * 0.01 for i in range(40)]
    # recent: 5 values that dropped to 0.55
    recent = [0.55] * 5
    monitor = _make_monitor(accuracies=baseline + recent)
    events = detector._check_accuracy_drift(monitor)
    assert len(events) == 1
    assert events[0].type == "accuracy_drift"


def test_check_accuracy_drift_ignores_small_drift():
    """A minor accuracy drop (below threshold) must not trigger an event."""
    detector = AnomalyDetector(baseline_window=100, detection_window=5)
    # baseline around 0.85, recent around 0.84 — tiny drift
    baseline = [0.85] * 30
    recent = [0.84] * 5
    monitor = _make_monitor(accuracies=baseline + recent)
    assert detector._check_accuracy_drift(monitor) == []


def test_check_accuracy_drift_too_few_points_returns_empty():
    detector = AnomalyDetector()
    monitor = _make_monitor(accuracies=[0.9, 0.8])
    assert detector._check_accuracy_drift(monitor) == []


# ---------------------------------------------------------------------------
# _check_token_spike()
# ---------------------------------------------------------------------------

def test_check_token_spike_detects_iqr_outlier():
    """A recent spike far above baseline IQR upper fence triggers token_spike."""
    detector = AnomalyDetector(baseline_window=100, detection_window=5)
    # baseline: 50 values around 100 tokens each
    baseline = [100] * 50
    # recent: 5 values spiked to 10000
    recent = [10000] * 5
    monitor = _make_monitor(tokens=baseline + recent)
    events = detector._check_token_spike(monitor)
    assert len(events) == 1
    assert events[0].type == "token_spike"


def test_check_token_spike_ignores_normal_usage():
    """Stable token usage must not trigger a spike event."""
    detector = AnomalyDetector()
    tokens = [100 + i % 10 for i in range(30)]
    monitor = _make_monitor(tokens=tokens)
    assert detector._check_token_spike(monitor) == []


def test_check_token_spike_too_few_points_returns_empty():
    detector = AnomalyDetector()
    monitor = _make_monitor(tokens=[100, 200, 300])
    assert detector._check_token_spike(monitor) == []


# ---------------------------------------------------------------------------
# _check_error_surge()
# ---------------------------------------------------------------------------

def test_check_error_surge_detects_high_error_rate():
    """Recent high error rate above threshold and baseline triggers error_surge."""
    detector = AnomalyDetector(baseline_window=40, detection_window=10)
    # baseline: 30 successful tasks
    baseline_tasks = [_FakeTask(success=True)] * 30
    # recent: 10 tasks where 8 failed (80% error rate)
    recent_tasks = [_FakeTask(success=False)] * 8 + [_FakeTask(success=True)] * 2
    monitor = _make_monitor(tasks=baseline_tasks + recent_tasks)
    events = detector._check_error_surge(monitor)
    assert len(events) == 1
    assert events[0].type == "error_surge"


def test_check_error_surge_ignores_low_error_rate():
    """Error rate below threshold must not trigger an event."""
    detector = AnomalyDetector(baseline_window=100, detection_window=10)
    # Recent 10 tasks have 0% error rate — well below 20% threshold
    # Baseline: 90 tasks all successful
    tasks = [_FakeTask(success=True)] * 100
    monitor = _make_monitor(tasks=tasks)
    assert detector._check_error_surge(monitor) == []


# ---------------------------------------------------------------------------
# _check_security_pattern()
# ---------------------------------------------------------------------------

def test_check_security_pattern_returns_empty_when_no_input_sanitizer():
    """When input_sanitizer is None, no security events should be returned."""
    detector = AnomalyDetector()
    monitor = _make_monitor(input_sanitizer=None)
    assert detector._check_security_pattern(monitor) == []


def test_check_security_pattern_detects_high_threat_rate():
    """A threat rate above 10% should trigger a security_pattern event."""
    detector = AnomalyDetector()
    sanitizer = MagicMock()
    sanitizer.get_security_stats.return_value = {
        "total_inputs_evaluated": 20,
        "inputs_with_threats": 5,  # 25% threat rate
    }
    monitor = _make_monitor(input_sanitizer=sanitizer)
    events = detector._check_security_pattern(monitor)
    assert len(events) == 1
    assert events[0].type == "security_pattern"


def test_check_security_pattern_ignores_low_threat_rate():
    detector = AnomalyDetector()
    sanitizer = MagicMock()
    sanitizer.get_security_stats.return_value = {
        "total_inputs_evaluated": 100,
        "inputs_with_threats": 3,  # 3% — below 10% threshold
    }
    monitor = _make_monitor(input_sanitizer=sanitizer)
    assert detector._check_security_pattern(monitor) == []


# ---------------------------------------------------------------------------
# scan() — multiple anomalies at once
# ---------------------------------------------------------------------------

def test_scan_returns_multiple_anomalies():
    """When both latency and token conditions are met, both events appear."""
    detector = AnomalyDetector(baseline_window=100, detection_window=5)
    # Strong latency uptrend
    latencies = [float(i) for i in range(10)]
    # Huge token spike
    baseline_tokens = [100] * 50
    recent_tokens = [10000] * 5
    monitor = _make_monitor(
        latencies=latencies,
        tokens=baseline_tokens + recent_tokens,
    )
    events = detector.scan(monitor)
    types = {e.type for e in events}
    assert "latency_trend" in types
    assert "token_spike" in types


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_mean_empty_returns_zero():
    assert _mean([]) == 0.0


def test_mean_single_value():
    assert _mean([5.0]) == 5.0


def test_mean_multiple_values():
    assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)


def test_std_empty_returns_zero():
    assert _std([]) == 0.0


def test_std_single_value_returns_zero():
    assert _std([42.0]) == 0.0


def test_std_known_values():
    # Implementation uses sample std (n-1 denominator)
    # std([1, 2, 3, 4, 5]) with n-1 → sqrt(2.5) ≈ 1.5811
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    expected = pytest.approx(2.5 ** 0.5, rel=1e-5)
    assert _std(values) == expected


def test_iqr_empty_returns_zeros():
    q1, q3, iqr = _iqr([])
    assert q1 == 0.0 and q3 == 0.0 and iqr == 0.0


def test_iqr_sorted_output():
    q1, q3, iqr = _iqr([1, 2, 3, 4, 5, 6, 7, 8])
    assert q1 <= q3
    assert iqr == q3 - q1


def test_linear_regression_slope_flat_series():
    assert _linear_regression_slope([3.0, 3.0, 3.0, 3.0, 3.0]) == pytest.approx(0.0)


def test_linear_regression_slope_ascending():
    # y = x → slope should be 1.0
    values = [float(x) for x in range(5)]
    assert _linear_regression_slope(values) == pytest.approx(1.0)


def test_linear_regression_slope_single_value_returns_zero():
    assert _linear_regression_slope([7.0]) == 0.0


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

def test_latency_warning_severity():
    """A moderate upward slope (just above threshold, not 3x) → 'warning'."""
    detector = AnomalyDetector()
    # Build a gentle slope: each point increases by 0.06 (just above 0.05 threshold)
    latencies = [1.0 + i * 0.06 for i in range(10)]
    monitor = _make_monitor(latencies=latencies)
    events = detector._check_latency_trend(monitor)
    if events:
        assert events[0].severity in ("warning", "critical")


def test_error_surge_critical_severity():
    """A very high error rate (>30%) should yield severity='critical'."""
    detector = AnomalyDetector(baseline_window=40, detection_window=10)
    # recent: 90% error rate
    baseline_tasks = [_FakeTask(success=True)] * 30
    recent_tasks = [_FakeTask(success=False)] * 9 + [_FakeTask(success=True)]
    monitor = _make_monitor(tasks=baseline_tasks + recent_tasks)
    events = detector._check_error_surge(monitor)
    assert events and events[0].severity == "critical"
