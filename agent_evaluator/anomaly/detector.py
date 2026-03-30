"""
AnomalyDetector — Phase 3-B 이상 탐지

외부 ML 라이브러리 없이 Z-score + IQR + 선형 회귀로 이상을 탐지한다.

탐지 유형:
  latency_trend    선형 회귀 기반 지속적 상승 추세
  accuracy_drift   Z-score 기반 기준선 대비 통계적 이탈
  token_spike      IQR 기반 급격한 토큰 사용량 이상
  error_surge      오류율 급증
  security_pattern 보안 위협 패턴 급증
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor

_Z_SCORE_THRESHOLD = 2.5   # 통계적 이탈 기준
_IQR_FACTOR = 2.0          # IQR 이상치 배수
_TREND_MIN_POINTS = 5      # 추세 감지 최소 데이터 포인트
_TREND_SLOPE_THRESHOLD = 0.05  # 지연시간 상승 기울기 임계값 (초/태스크)
_ACCURACY_DRIFT_THRESHOLD = 0.15  # 정확도 기준선 대비 허용 이탈 비율
_ERROR_SURGE_THRESHOLD = 0.20     # 오류율 급증 임계값
_SECURITY_SURGE_THRESHOLD = 0.10  # 보안 위협율 급증 임계값


@dataclass
class AnomalyEvent:
    """탐지된 이상 이벤트."""
    type: str             # latency_trend, accuracy_drift, token_spike, error_surge, security_pattern
    severity: str         # warning, critical
    detail: str           # 사람이 읽기 쉬운 설명
    value: float          # 현재 측정값
    threshold: float      # 기준값
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    algorithm: str = ""   # z-score, iqr, linear_regression, ratio

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "detail": self.detail,
            "value": self.value,
            "threshold": self.threshold,
            "detected_at": self.detected_at,
            "algorithm": self.algorithm,
        }


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _iqr(values: List[float]) -> tuple:
    """Q1, Q3, IQR 반환."""
    if not values:
        return 0.0, 0.0, 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[(3 * n) // 4]
    return q1, q3, q3 - q1


def _linear_regression_slope(values: List[float]) -> float:
    """단순 선형 회귀 기울기 반환 (y=ax+b 에서 a)."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = _mean(values)
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator != 0 else 0.0


class AnomalyDetector:
    """운영 지표 이상 탐지기.

    Args:
        baseline_window: 기준선 계산에 사용할 태스크 수 (최근 N개). Default 100.
        detection_window: 현재값 계산에 사용할 태스크 수. Default 20.

    Example::
        detector = AnomalyDetector()
        anomalies = detector.scan(monitor)
        for a in anomalies:
            print(f"[{a.severity}] {a.type}: {a.detail}")
    """

    def __init__(
        self,
        baseline_window: int = 100,
        detection_window: int = 20,
    ) -> None:
        self.baseline_window = baseline_window
        self.detection_window = detection_window

    def scan(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        """모든 이상 탐지 규칙을 실행하고 탐지된 이상 목록을 반환한다.

        Args:
            monitor: 분석할 PerformanceMonitor 인스턴스.

        Returns:
            탐지된 AnomalyEvent 목록. 이상 없으면 빈 리스트.
        """
        events: List[AnomalyEvent] = []
        events.extend(self._check_latency_trend(monitor))
        events.extend(self._check_accuracy_drift(monitor))
        events.extend(self._check_token_spike(monitor))
        events.extend(self._check_error_surge(monitor))
        events.extend(self._check_security_pattern(monitor))
        return events

    def _get_latencies(self, monitor: "PerformanceMonitor") -> List[float]:
        try:
            latency_data = monitor.latency_tracker.latencies
            return [entry.get("execution_time", 0.0) for entry in latency_data if isinstance(entry, dict)]
        except Exception:
            return []

    def _get_accuracies(self, monitor: "PerformanceMonitor") -> List[float]:
        try:
            evals = monitor.accuracy_evaluator.evaluations
            return [e["accuracy"] for e in evals if isinstance(e, dict) and e.get("accuracy") is not None]
        except Exception:
            return []

    def _get_tokens(self, monitor: "PerformanceMonitor") -> List[float]:
        try:
            usage_log = monitor.token_tracker.usage_log
            return [entry.get("total_tokens", 0) for entry in usage_log if isinstance(entry, dict)]
        except Exception:
            return []

    def _get_error_rate(self, monitor: "PerformanceMonitor") -> tuple:
        try:
            tasks = monitor.tcr_tracker.tasks
            if not tasks:
                return 0.0, 0.0
            recent = tasks[-self.detection_window:]
            baseline = tasks[-self.baseline_window:-self.detection_window] if len(tasks) > self.detection_window else []
            recent_rate = sum(1 for t in recent if not t.success) / len(recent)
            base_rate = sum(1 for t in baseline if not t.success) / len(baseline) if baseline else 0.0
            return recent_rate, base_rate
        except Exception:
            return 0.0, 0.0

    def _check_latency_trend(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        latencies = self._get_latencies(monitor)
        if len(latencies) < _TREND_MIN_POINTS:
            return []
        recent = latencies[-self.detection_window:] if len(latencies) >= self.detection_window else latencies
        slope = _linear_regression_slope(recent)
        if slope > _TREND_SLOPE_THRESHOLD:
            change_pct = round(slope * len(recent) / (_mean(recent) or 1) * 100, 1)
            severity = "critical" if slope > _TREND_SLOPE_THRESHOLD * 3 else "warning"
            return [AnomalyEvent(
                type="latency_trend",
                severity=severity,
                detail=f"P95 지연시간 {len(recent)}개 태스크 동안 지속 상승 (+{change_pct}%)",
                value=round(slope, 4),
                threshold=_TREND_SLOPE_THRESHOLD,
                algorithm="linear_regression",
            )]
        return []

    def _check_accuracy_drift(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        accuracies = self._get_accuracies(monitor)
        if len(accuracies) < _TREND_MIN_POINTS:
            return []
        baseline = accuracies[-self.baseline_window:-self.detection_window] if len(accuracies) > self.detection_window else accuracies[:max(1, len(accuracies) // 2)]
        recent = accuracies[-self.detection_window:] if len(accuracies) >= self.detection_window else accuracies[-max(1, len(accuracies) // 2):]
        if not baseline or not recent:
            return []
        base_mean = _mean(baseline)
        recent_mean = _mean(recent)
        base_std = _std(baseline)
        if base_std == 0:
            return []
        z_score = abs(recent_mean - base_mean) / base_std
        drift = (base_mean - recent_mean) / (base_mean or 1)
        if z_score > _Z_SCORE_THRESHOLD and drift > _ACCURACY_DRIFT_THRESHOLD:
            severity = "critical" if drift > _ACCURACY_DRIFT_THRESHOLD * 2 else "warning"
            return [AnomalyEvent(
                type="accuracy_drift",
                severity=severity,
                detail=f"정확도 기준선 대비 -{round(drift * 100, 1)}% 이탈 (z-score={round(z_score, 2)})",
                value=round(recent_mean, 4),
                threshold=round(base_mean, 4),
                algorithm="z-score",
            )]
        return []

    def _check_token_spike(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        tokens = self._get_tokens(monitor)
        if len(tokens) < _TREND_MIN_POINTS:
            return []
        baseline = tokens[-self.baseline_window:-self.detection_window] if len(tokens) > self.detection_window else tokens
        recent_avg = _mean(tokens[-self.detection_window:] if len(tokens) >= self.detection_window else tokens[-3:])
        if not baseline:
            return []
        q1, q3, iqr = _iqr(baseline)
        upper_fence = q3 + _IQR_FACTOR * iqr
        if recent_avg > upper_fence and upper_fence > 0:
            ratio = round(recent_avg / (_mean(baseline) or 1) * 100 - 100, 1)
            severity = "critical" if ratio > 100 else "warning"
            return [AnomalyEvent(
                type="token_spike",
                severity=severity,
                detail=f"평균 토큰 사용량 기준선 대비 +{ratio}% 급증 (IQR 이상치)",
                value=round(recent_avg, 1),
                threshold=round(upper_fence, 1),
                algorithm="iqr",
            )]
        return []

    def _check_error_surge(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        recent_rate, base_rate = self._get_error_rate(monitor)
        if recent_rate > _ERROR_SURGE_THRESHOLD and recent_rate > base_rate * 2:
            severity = "critical" if recent_rate > 0.3 else "warning"
            return [AnomalyEvent(
                type="error_surge",
                severity=severity,
                detail=f"오류율 {round(recent_rate * 100, 1)}% (기준선 {round(base_rate * 100, 1)}% 대비 급증)",
                value=round(recent_rate, 4),
                threshold=_ERROR_SURGE_THRESHOLD,
                algorithm="ratio",
            )]
        return []

    def _check_security_pattern(self, monitor: "PerformanceMonitor") -> List[AnomalyEvent]:
        try:
            if monitor.input_sanitizer is None:
                return []
            stats = monitor.input_sanitizer.get_security_stats()
            total = stats.get("total_inputs_evaluated", 0)
            threats = stats.get("inputs_with_threats", 0)
            if total == 0:
                return []
            threat_rate = threats / total
            if threat_rate > _SECURITY_SURGE_THRESHOLD:
                severity = "critical" if threat_rate > 0.3 else "warning"
                return [AnomalyEvent(
                    type="security_pattern",
                    severity=severity,
                    detail=f"보안 위협 탐지율 {round(threat_rate * 100, 1)}% — 공격 패턴 의심",
                    value=round(threat_rate, 4),
                    threshold=_SECURITY_SURGE_THRESHOLD,
                    algorithm="frequency",
                )]
        except Exception:
            pass
        return []
