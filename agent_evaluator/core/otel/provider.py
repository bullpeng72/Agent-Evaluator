"""
agent_evaluator.core.otel.provider — OTELProvider (TracerProvider 래퍼).

opentelemetry-sdk 미설치 시 모든 메서드가 no-op으로 동작한다.
기존 JSON 저장 경로에 일절 영향을 주지 않는다.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class OTELProvider:
    """OTEL TracerProvider 래퍼.

    opentelemetry-sdk 미설치 시 모든 메서드가 no-op으로 동작한다.
    기존 JSON 저장 경로에 일절 영향을 주지 않는다.

    Args:
        endpoint: OTLP HTTP receiver 주소 (Phoenix 13.x 기본: http://localhost:6006)
        service_name: Phoenix UI에 표시될 서비스 이름
        enabled: False 시 즉시 no-op 모드

    Example:
        >>> provider = OTELProvider(endpoint="http://localhost:6006")
        >>> with provider.span("ae.task", {"ae.task_id": "t1"}):
        ...     pass  # 평가 로직
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:6006",
        service_name: str = "agent-evaluator",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled and _HAS_OTEL
        self._tracer: Any | None = None
        self._base_endpoint: str | None = endpoint if (enabled and _HAS_OTEL) else None

        if not self._enabled:
            if enabled and not _HAS_OTEL:
                logger.warning(
                    "OTELProvider: opentelemetry-sdk is not installed; running in no-op mode. "
                    "Install: pip install 'agent-evaluator[otel]'"
                )
            return

        try:
            resource = Resource(attributes={
                "service.name": service_name,
                "openinference.project.name": service_name,
            })
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(
                endpoint=f"{endpoint}/v1/traces",
                headers={"x-phoenix-project-name": service_name},
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
            logger.debug(
                "OTELProvider: initialized (endpoint=%s, service=%s)",
                endpoint,
                service_name,
            )
        except Exception as exc:
            logger.warning("OTELProvider: initialization failed, switching to no-op mode: %s", exc)
            self._enabled = False

    @contextlib.contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any],
        start_time_ns: int | None = None,
    ) -> Iterator[Any]:
        """컨텍스트 매니저형 스팬. 미활성화 시 no-op.

        Args:
            name: 스팬 이름 (예: "ae.task", "ae.session")
            attributes: 스팬에 기록할 속성 dict
            start_time_ns: 스팬 시작 시각 (나노초, Unix epoch).
                지정하면 span duration = (exit 시각) - start_time_ns 로 계산된다.
                태스크 실행 시작 시각을 지정하면 Phoenix latency 차트가 실제 레이턴시를 표시한다.

        Example:
            >>> with provider.span("ae.task", {"ae.task_id": "t1"}) as s:
            ...     pass
        """
        if not self._enabled or self._tracer is None:
            yield None
            return

        # 스팬 시작 (setup) 단계 — 실패 시 no-op으로 폴백
        try:
            span_ctx = self._tracer.start_as_current_span(
                name,
                start_time=start_time_ns,  # None이면 SDK가 현재 시각 사용
            )
            s = span_ctx.__enter__()
        except Exception as exc:
            logger.debug("OTELProvider.span: span start failed (%s): %s", name, exc)
            yield None
            return

        # 속성 설정
        for k, v in attributes.items():
            try:
                s.set_attribute(k, v)
            except Exception as _e:
                logger.debug("span attribute set failed (ignored): %s", _e)

        # yield — caller body 실행; 예외가 오더라도 span_ctx.__exit__ 를 보장
        exc_info = (None, None, None)
        try:
            yield s
        except BaseException:
            import sys
            exc_info = sys.exc_info()
            raise
        finally:
            try:
                span_ctx.__exit__(*exc_info)
            except Exception as close_exc:
                logger.debug("OTELProvider.span: span close failed (%s): %s", name, close_exc)

    @property
    def enabled(self) -> bool:
        """OTEL이 활성화되어 있으면 True."""
        return self._enabled

    @property
    def base_endpoint(self) -> str | None:
        """OTLP 수신 서버 기본 URL (예: http://localhost:6006). 비활성화 시 None."""
        return self._base_endpoint

    def force_flush(self, timeout_ms: int = 5000) -> None:
        """BatchSpanProcessor 큐를 즉시 플러시한다."""
        if not self._enabled:
            return
        try:
            from opentelemetry import trace as _trace
            provider = _trace.get_tracer_provider()
            if hasattr(provider, "force_flush"):
                provider.force_flush(timeout_millis=timeout_ms)
        except Exception as exc:
            logger.debug("OTELProvider.force_flush: %s", exc)
