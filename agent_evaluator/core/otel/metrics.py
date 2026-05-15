"""
agent_evaluator.core.otel.metrics — OTELMetrics (MeterProvider 래퍼).

주요 평가 지표를 히스토그램/카운터/게이지로 Phoenix에 전송한다.
opentelemetry-sdk 미설치 시 no-op.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    _HAS_OTEL_METRICS = True
except ImportError:
    _HAS_OTEL_METRICS = False


class OTELMetrics:
    """OTEL MeterProvider 래퍼.

    주요 지표를 히스토그램/게이지로 Phoenix에 전송.
    opentelemetry-sdk 미설치 시 no-op.

    Args:
        endpoint: OTLP HTTP receiver 주소
        enabled: False 시 즉시 no-op 모드

    Attributes:
        METRIC_DEFS: 발행 지표 정의 — (kind, description) 매핑

    Example:
        >>> m = OTELMetrics(endpoint="http://localhost:6006")
        >>> m.record("ae.tcr", 92.5, {"task_type": "qa"})
    """

    # 발행 지표 정의: name → (kind, description)
    METRIC_DEFS: Dict[str, tuple] = {
        "ae.tcr": ("gauge", "Task Completion Rate (%)"),
        "ae.accuracy": ("gauge", "Accuracy Score (0–1)"),
        "ae.latency_seconds": ("histogram", "Task Execution Latency (s)"),
        "ae.tokens_total": ("counter", "Cumulative Token Usage"),
        "ae.error_rate": ("gauge", "Error Rate (%)"),
    }

    def __init__(self, endpoint: str, enabled: bool = True) -> None:
        self._enabled = enabled and _HAS_OTEL_METRICS
        self._instruments: Dict[str, Any] = {}

        if not self._enabled:
            return

        try:
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
                export_interval_millis=15_000,  # 15초마다 배치 전송
            )
            provider = MeterProvider(metric_readers=[reader])
            metrics.set_meter_provider(provider)
            meter = metrics.get_meter("agent-evaluator")

            for name, (kind, desc) in self.METRIC_DEFS.items():
                if kind == "histogram":
                    self._instruments[name] = meter.create_histogram(name, description=desc)
                elif kind == "counter":
                    self._instruments[name] = meter.create_counter(name, description=desc)
                else:  # gauge → up_down_counter
                    self._instruments[name] = meter.create_up_down_counter(name, description=desc)

            logger.debug("OTELMetrics: initialized (endpoint=%s)", endpoint)
        except Exception as exc:
            logger.warning("OTELMetrics: initialization failed, switching to no-op mode: %s", exc)
            self._enabled = False

    def record(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """지표 값 기록. 미활성화 또는 미등록 지표면 no-op.

        Args:
            name: 지표 이름 (METRIC_DEFS 키 중 하나)
            value: 측정값
            attributes: 태그 딕셔너리 (예: {"task_type": "qa"})
        """
        if not self._enabled or name not in self._instruments:
            return
        try:
            self._instruments[name].record(value, attributes or {})
        except Exception as exc:
            # OTEL 오류가 평가 로직을 중단시키지 않도록 조용히 처리
            logger.debug("OTELMetrics.record: metric record failed (%s): %s", name, exc)

    @property
    def enabled(self) -> bool:
        """OTEL 지표 발행이 활성화되어 있으면 True."""
        return self._enabled
