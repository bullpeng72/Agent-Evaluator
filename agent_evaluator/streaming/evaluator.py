"""
StreamingEvaluator — Phase 2-A 스트리밍 평가 엔진

PerformanceMonitor를 래핑하여 실시간 슬라이딩 윈도우 지표를 제공한다.
각 요청마다 즉시 평가하고 임계값 위반 시 AlertEngine을 호출한다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor
    from agent_evaluator.alerts.engine import AlertEngine


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

    Example::
        from agent_evaluator.streaming import StreamingEvaluator

        evaluator = StreamingEvaluator(monitor=monitor, flush_interval=60)
        evaluator.record(task_id="t1", success=True, execution_time=1.2, tokens_used=150)
        stats = evaluator.get_stats()
    """

    def __init__(
        self,
        monitor: "PerformanceMonitor",
        flush_interval: int = 60,
        alert_handler: Optional["AlertEngine"] = None,
    ) -> None:
        self.monitor = monitor
        self.flush_interval = flush_interval
        self.alert_handler = alert_handler

        # 슬라이딩 윈도우: 1분, 5분, 1시간
        self._windows = {
            "1m": SlidingWindow(60),
            "5m": SlidingWindow(300),
            "1h": SlidingWindow(3600),
        }
        self._lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        """백그라운드 flush 스레드 시작."""
        if self._running:
            return
        self._running = True
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
            except Exception:
                pass

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
            except Exception:
                pass

    def _flush(self) -> None:
        pass  # 향후 확장: 집계된 지표를 파일/DB에 저장
