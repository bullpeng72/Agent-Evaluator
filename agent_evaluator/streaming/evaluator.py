"""
StreamingEvaluator — Phase 2-A 스트리밍 평가 엔진

PerformanceMonitor를 래핑하여 실시간 슬라이딩 윈도우 지표를 제공한다.
각 요청마다 즉시 평가하고 임계값 위반 시 AlertEngine을 호출한다.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

if TYPE_CHECKING:
    from agent_evaluator.alerts.engine import AlertEngine
    from agent_evaluator.anomaly.detector import AnomalyDetector, AnomalyEvent
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor


@dataclass
class StreamingRecord:
    """단일 요청의 실시간 평가 기록."""
    task_id: str
    success: bool
    execution_time: float
    tokens_used: int
    timestamp: float = field(default_factory=time.time)
    accuracy_score: float = 0.0
    has_error: bool = False


class SlidingWindow:
    """시간 기반 슬라이딩 윈도우."""

    def __init__(self, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self._records: Deque[StreamingRecord] = deque()
        self._lock = threading.Lock()

    def add(self, record: StreamingRecord) -> None:
        with self._lock:
            self._records.append(record)
            self._evict()

    def _evict(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._records and self._records[0].timestamp < cutoff:
            self._records.popleft()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._evict()
            records = list(self._records)

        if not records:
            return {"count": 0, "tcr": 0.0, "avg_latency": 0.0, "p95_latency": 0.0,
                    "error_rate": 0.0, "avg_tokens": 0.0, "window_seconds": self.window_seconds}

        n = len(records)
        successes = sum(1 for r in records if r.success)
        latencies = sorted(r.execution_time for r in records)
        p95_idx = max(0, int(n * 0.95) - 1)
        errors = sum(1 for r in records if r.has_error)

        return {
            "count": n,
            "tcr": round(successes / n * 100, 1),
            "avg_latency": round(sum(r.execution_time for r in records) / n, 3),
            "p95_latency": round(latencies[p95_idx], 3),
            "error_rate": round(errors / n * 100, 1),
            "avg_tokens": round(sum(r.tokens_used for r in records) / n, 1),
            "window_seconds": self.window_seconds,
        }


class StreamingEvaluator:
    """실시간 스트리밍 평가 엔진.

    Args:
        monitor: 기존 PerformanceMonitor 인스턴스.
        flush_interval: 지표 집계 및 저장 간격 (초). Default 60.
        alert_handler: AlertEngine 인스턴스 (선택).
        anomaly_detector: (SPEC-026 REQ-2, 선택) 지정하면 기존 flush 스레드가
            ``anomaly_scan_interval``마다 ``anomaly_detector.scan(self.monitor)``을
            호출해 그 결과를 :attr:`_last_anomalies`에 저장한다. 새 스레드를 만들지
            않고 이미 있는 flush 루프에 조건부 호출을 얹는 형태 — 미지정(기본값)이면
            기존 동작과 100% 동일.
        anomaly_scan_interval: ``anomaly_detector`` 스캔 주기(초). Default 300.
            ``flush_interval``과 독립적인 값 — 스트리밍 지표 flush는 자주(예: 60초),
            이상탐지 스캔은 더 느슨하게(예: 300초) 돌리는 식으로 따로 조정한다.
        anomaly_alert_handler: (SPEC-026 REQ-4, 선택) 지정하면 주기적 스캔이 이상을
            발견할 때마다 ``alert_handler.dispatch_anomaly_events(events, handler=
            anomaly_alert_handler)``(REQ-3)를 자동 호출해 실제로 알림을 발송한다.
            ``alert_handler``(``AlertEngine`` 인스턴스)와 ``anomaly_detector`` 둘 다
            설정돼 있어야 동작한다 — 셋 중 하나라도 없으면(기본값) 스캔 결과는
            :attr:`_last_anomalies`에만 쌓이고 발송되지 않는다.

    Example::
        from agent_evaluator.streaming import StreamingEvaluator

        evaluator = StreamingEvaluator(monitor=monitor, flush_interval=60)
        evaluator.record(task_id="t1", success=True, execution_time=1.2, tokens_used=150)
        stats = evaluator.get_stats()
    """

    def __init__(
        self,
        monitor: PerformanceMonitor,
        flush_interval: int = 60,
        alert_handler: Optional[AlertEngine] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        anomaly_scan_interval: int = 300,
        anomaly_alert_handler: Optional[Any] = None,
    ) -> None:
        self.monitor = monitor
        self.flush_interval = flush_interval
        self.alert_handler = alert_handler
        self.anomaly_detector = anomaly_detector
        self.anomaly_scan_interval = anomaly_scan_interval
        self.anomaly_alert_handler = anomaly_alert_handler

        # 슬라이딩 윈도우: 1분, 5분, 1시간
        self._windows = {
            "1m": SlidingWindow(60),
            "5m": SlidingWindow(300),
            "1h": SlidingWindow(3600),
        }
        self._lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._running = False

        # SPEC-026 REQ-2: 가장 최근 주기적 이상탐지 스캔 결과 — anomaly_detector
        # 미지정이면 항상 빈 리스트로 유지된다.
        self._last_anomalies: List[AnomalyEvent] = []
        self._last_anomaly_scan_time: float = 0.0

    def start(self) -> None:
        """백그라운드 flush 스레드 시작."""
        if self._running:
            return
        self._running = True
        # start() 시점을 기준선으로 삼아, 첫 이상탐지 스캔도 anomaly_scan_interval을
        # 온전히 기다린 뒤 실행되게 한다(생성 시점이 아니라 실제 가동 시점 기준).
        self._last_anomaly_scan_time = time.time()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        """백그라운드 flush 스레드 중지."""
        self._running = False

    def record(
        self,
        task_id: str,
        success: bool,
        execution_time: float,
        tokens_used: int = 0,
        accuracy_score: float = 0.0,
        has_error: bool = False,
    ) -> None:
        """실시간 지표 기록.

        Args:
            task_id: 태스크 ID.
            success: 태스크 성공 여부.
            execution_time: 실행 시간 (초).
            tokens_used: 토큰 사용량.
            accuracy_score: 정확도 점수 (0.0~1.0).
            has_error: 오류 발생 여부.
        """
        record = StreamingRecord(
            task_id=task_id,
            success=success,
            execution_time=execution_time,
            tokens_used=tokens_used,
            accuracy_score=accuracy_score,
            has_error=has_error,
        )
        for window in self._windows.values():
            window.add(record)

        if self.alert_handler is not None:
            try:
                self.alert_handler.evaluate(self)
            except Exception as _e:
                logger.debug("Alert handler evaluation failed (ignored): %s", _e)

    def get_stats(self, window: str = "5m") -> Dict[str, Any]:
        """슬라이딩 윈도우 통계 반환.

        Args:
            window: "1m", "5m", "1h" 중 하나.

        Returns:
            count, tcr, avg_latency, p95_latency, error_rate, avg_tokens
        """
        w = self._windows.get(window)
        if w is None:
            raise ValueError(f"window must be one of {list(self._windows.keys())}")
        return w.get_stats()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """모든 윈도우의 통계를 반환."""
        return {name: w.get_stats() for name, w in self._windows.items()}

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval)
            try:
                self._flush()
            except Exception as _e:
                logger.debug("Streaming flush failed (ignored): %s", _e)
            self._maybe_scan_anomalies()

    def _maybe_scan_anomalies(self) -> None:
        """SPEC-026 REQ-2: ``anomaly_detector``가 설정돼 있고 마지막 스캔 이후
        ``anomaly_scan_interval``초 이상 지났으면 스캔을 실행한다. ``flush_interval``
        주기로 도는 기존 루프 안에서 호출되므로, 실제 스캔 간격은 ``flush_interval``의
        배수로 근사된다(예: flush_interval=60, anomaly_scan_interval=300이면 5회
        flush마다 1회 스캔). 스캔이 이상을 발견하면 REQ-4(:meth:`_maybe_dispatch_anomalies`)로
        이어져 실제 알림 발송을 시도한다."""
        if self.anomaly_detector is None:
            return
        now = time.time()
        if now - self._last_anomaly_scan_time < self.anomaly_scan_interval:
            return
        self._last_anomaly_scan_time = now
        try:
            self._last_anomalies = self.anomaly_detector.scan(self.monitor)
        except Exception as _e:
            logger.debug("Anomaly scan failed (ignored): %s", _e)
            return
        self._maybe_dispatch_anomalies()

    def _maybe_dispatch_anomalies(self) -> None:
        """SPEC-026 REQ-4: REQ-2의 스캔 결과(:attr:`_last_anomalies`)를 REQ-3의
        ``AlertEngine.dispatch_anomaly_events()``로 넘겨 실제 알림을 발송한다.

        ``_last_anomalies``가 비어 있거나(이상 없음), ``alert_handler``/
        ``anomaly_alert_handler`` 중 하나라도 미설정이면 아무것도 하지 않는다 —
        새 쿨다운·재시도 로직을 만들지 않고 REQ-3에 그대로 위임한다. 발송 자체가
        실패해도(네트워크 등) flush 루프를 막지 않도록 예외를 삼킨다(``_flush()``/
        ``_maybe_scan_anomalies()``와 동일한 관례)."""
        if not self._last_anomalies:
            return
        if self.alert_handler is None or self.anomaly_alert_handler is None:
            return
        try:
            self.alert_handler.dispatch_anomaly_events(
                self._last_anomalies, handler=self.anomaly_alert_handler,
            )
        except Exception as _e:
            logger.debug("Anomaly alert dispatch failed (ignored): %s", _e)

    def _flush(self) -> None:
        """슬라이딩 윈도우 현재 스냅샷을 PerformanceMonitor에 저장.

        monitor.save_to_file() 호출 시 ``streaming_data`` 키에 포함되어
        결과 JSON 파일에 기록된다. 대시보드 '📡 실시간' 탭의 오프라인
        히스토리 소스로 활용된다.
        """
        all_stats = self.get_all_stats()
        # count=0 인 빈 윈도우는 제외하여 파일 크기 절약
        snapshot = {w: stats for w, stats in all_stats.items() if stats.get("count", 0) > 0}
        if snapshot and hasattr(self.monitor, "_streaming_snapshot"):
            self.monitor._streaming_snapshot = snapshot
