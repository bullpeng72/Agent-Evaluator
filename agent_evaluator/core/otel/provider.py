"""
agent_evaluator.core.otel.provider — OTELProvider (TracerProvider 래퍼).

opentelemetry-sdk 미설치 시 모든 메서드가 no-op으로 동작한다.
기존 JSON 저장 경로에 일절 영향을 주지 않는다.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class OTELProvider:
    """OTEL TracerProvider 래퍼.

    opentelemetry-sdk 미설치 시 모든 메서드가 no-op으로 동작한다.
    기존 JSON 저장 경로에 일절 영향을 주지 않는다.

    Args:
        endpoint: OTLP HTTP receiver 주소 (기본: http://localhost:4318)
        service_name: Phoenix UI에 표시될 서비스 이름
        enabled: False 시 즉시 no-op 모드

    Example:
        >>> provider = OTELProvider(endpoint="http://localhost:4318")
        >>> with provider.span("ae.task", {"ae.task_id": "t1"}):
        ...     pass  # 평가 로직
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4318",
        service_name: str = "agent-evaluator",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled and _HAS_OTEL
        self._tracer: Optional[Any] = None

        if not self._enabled:
            if enabled and not _HAS_OTEL:
                logger.warning(
                    "OTELProvider: opentelemetry-sdk 가 설치되지 않아 no-op 모드로 실행됩니다. "
                    "pip install 'agent-evaluator[otel]' 로 설치하세요."
                )
            return

        try:
            resource = Resource(attributes={"service.name": service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
            logger.debug(
                "OTELProvider: 초기화 완료 (endpoint=%s, service=%s)",
                endpoint,
                service_name,
            )
        except Exception as exc:
            logger.warning("OTELProvider: 초기화 실패, no-op 모드로 전환: %s", exc)
            self._enabled = False

    @contextlib.contextmanager
    def span(self, name: str, attributes: Dict[str, Any]) -> Iterator[Any]:
        """컨텍스트 매니저형 스팬. 미활성화 시 no-op.

        Args:
            name: 스팬 이름 (예: "ae.task", "ae.session")
            attributes: 스팬에 기록할 속성 dict

        Example:
            >>> with provider.span("ae.task", {"ae.task_id": "t1"}) as s:
            ...     pass
        """
        if not self._enabled or self._tracer is None:
            yield None
            return

        try:
            with self._tracer.start_as_current_span(name) as s:
                for k, v in attributes.items():
                    try:
                        s.set_attribute(k, v)
                    except Exception:
                        pass  # 개별 속성 실패는 무시
                yield s
        except Exception as exc:
            logger.debug("OTELProvider.span: 스팬 발행 실패 (%s): %s", name, exc)
            yield None

    @property
    def enabled(self) -> bool:
        """OTEL이 활성화되어 있으면 True."""
        return self._enabled
