"""
agent_evaluator.core.otel — OpenTelemetry integration (opt-in).

설치:  pip install "agent-evaluator[otel]"
활성화: from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:4318")

otel 패키지 미설치 시 setup_otel()은 no-op OTELProvider를 반환하며
기존 JSON 저장 경로에 일절 영향을 주지 않는다.
"""

from __future__ import annotations

from typing import Optional

_provider: Optional["OTELProvider"] = None  # type: ignore[name-defined]  # noqa: F821
_metrics: Optional["OTELMetrics"] = None   # type: ignore[name-defined]  # noqa: F821


def setup_otel(
    endpoint: str = "http://localhost:4318",
    service_name: str = "agent-evaluator",
    enabled: bool = True,
) -> "OTELProvider":  # type: ignore[name-defined]  # noqa: F821
    """OTELProvider / OTELMetrics를 초기화하고 전역 등록한다.

    PerformanceMonitor는 이 전역 provider를 자동으로 감지해
    record_task() 시 스팬과 지표를 발행한다.

    Args:
        endpoint: OTLP HTTP receiver 주소 (Phoenix 기본: http://localhost:6006)
        service_name: Phoenix UI에 표시될 서비스 이름
        enabled: False 시 no-op (테스트/개발 환경 비활성화 용도)

    Returns:
        OTELProvider 인스턴스

    Example:
        >>> from agent_evaluator import setup_otel
        >>> setup_otel(endpoint="http://localhost:6006")
        >>> # 이후 monitor.record_task()가 자동으로 스팬 + 지표 발행
    """
    from agent_evaluator.core.otel.provider import OTELProvider
    from agent_evaluator.core.otel.metrics import OTELMetrics

    global _provider, _metrics
    _provider = OTELProvider(
        endpoint=endpoint,
        service_name=service_name,
        enabled=enabled,
    )
    _metrics = OTELMetrics(endpoint=endpoint, enabled=enabled)
    return _provider


def get_provider() -> Optional["OTELProvider"]:  # type: ignore[name-defined]  # noqa: F821
    """현재 활성화된 OTELProvider를 반환. 미설정 시 None."""
    return _provider


def get_metrics() -> Optional["OTELMetrics"]:  # type: ignore[name-defined]  # noqa: F821
    """현재 활성화된 OTELMetrics를 반환. 미설정 시 None."""
    return _metrics
