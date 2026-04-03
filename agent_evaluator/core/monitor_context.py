"""
Context manager for evaluation sessions
Provides automatic resource management and result saving
"""

import contextlib
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


@contextmanager
def evaluation_session(
    output_filename: str,
    enable_security: bool = False,
    enable_hallucination: bool = False,
    **monitor_kwargs
):
    """
    Context manager for evaluation sessions
    Automatically saves results on exit (even if exception occurs)

    Example:
        ```python
        from agent_evaluator import evaluation_session

        with evaluation_session("my_results.json", enable_security=True) as monitor:
            # Your evaluation code
            task = create_taskresult_from_execution(...)
            monitor.record_task(task)
        # Results auto-saved!
        ```

    Args:
        output_filename: Output JSON filename
        enable_security: Enable security metrics (default: False)
        enable_hallucination: Enable hallucination detection (default: True)
        **monitor_kwargs: Additional arguments for PerformanceMonitor

    Yields:
        PerformanceMonitor instance

    Raises:
        Any exception raised in the context block (after auto-saving)
    """
    from .agent_evaluator import PerformanceMonitor

    # output_filename에서 사람이 읽기 쉬운 레이블 추출
    # 예: "results/01_quality_eval.json" → "01_quality_eval"
    import os as _os
    _label = _os.path.splitext(_os.path.basename(output_filename))[0]

    # Create monitor (session_label → Phoenix Sessions 탭 그룹핑 & ae.source 속성)
    monitor = PerformanceMonitor(
        enable_security_metrics=enable_security,
        enable_hallucination_detection=enable_hallucination,
        session_label=_label,
        **monitor_kwargs
    )

    # OTEL 루트 span (opt-in, no-op if not configured)
    # 세션 스팬 이름에 레이블 포함 → Phoenix에서 어느 평가 스크립트인지 바로 식별 가능
    def _otel_ctx():
        try:
            from agent_evaluator.core.otel import get_provider

            provider = get_provider()
            if provider and provider.enabled:
                session_span_name = f"ae.session/{_label}" if _label else "ae.session"
                return provider.span(session_span_name, {
                    "openinference.span.kind": "CHAIN",
                    "ae.session_file": output_filename,
                    "ae.source": _label,
                    "session.id": monitor._otel_session_id,
                })
        except Exception as _e:
            logger.debug("OTEL 컨텍스트 스팬 설정 실패 (무시): %s", _e)
        return contextlib.nullcontext()

    exception_occurred = None

    with _otel_ctx():
        try:
            yield monitor
        except Exception as e:
            # Capture exception but don't raise yet (save first)
            exception_occurred = e
        finally:
            # Auto-save on exit (even if exception occurred)
            # Note: save_to_file() automatically includes full report
            try:
                monitor.save_to_file(output_filename)
                if exception_occurred:
                    logger.warning(
                        "evaluation_session: exception occurred but results saved to '%s'",
                        output_filename,
                    )
                else:
                    logger.info("evaluation_session: auto-saved to '%s'", output_filename)
            except Exception as save_error:
                logger.error(
                    "evaluation_session: FAILED to save results to '%s': %s",
                    output_filename,
                    save_error,
                )
                if exception_occurred is None:
                    # Only save failed — surface that error to the caller
                    raise save_error

        # Now raise the original exception if it occurred
        if exception_occurred:
            raise exception_occurred


@contextmanager
def hybrid_evaluation_session(
    output_filename: str,
    use_deepeval: bool = False,
    use_ragas: bool = False,
    enable_security: bool = False,
    **monitor_kwargs
):
    """
    Context manager for hybrid evaluation sessions (Layer 3)
    Automatically saves results on exit

    Example:
        ```python
        from agent_evaluator import hybrid_evaluation_session

        with hybrid_evaluation_session(
            "rag_results.json",
            use_ragas=True
        ) as monitor:
            # Your RAG evaluation code
            monitor.record_rag_metrics(...)
        # Results auto-saved!
        ```

    Args:
        output_filename: Output JSON filename
        use_deepeval: Enable DeepEval metrics (default: False)
        use_ragas: Enable Ragas metrics (default: False)
        enable_security: Enable security metrics (default: False)
        **monitor_kwargs: Additional arguments for HybridPerformanceMonitor

    Yields:
        HybridPerformanceMonitor instance
    """
    from .hybrid_monitor import HybridPerformanceMonitor

    # Create hybrid monitor
    monitor = HybridPerformanceMonitor(
        use_deepeval=use_deepeval,
        use_ragas=use_ragas,
        enable_security_metrics=enable_security,
        **monitor_kwargs
    )

    exception_occurred = None

    try:
        yield monitor
    except Exception as e:
        exception_occurred = e
    finally:
        # Auto-save on exit
        try:
            monitor.save_to_file(output_filename)
            if exception_occurred:
                logger.warning(
                    "hybrid_evaluation_session: exception occurred but results saved to '%s'",
                    output_filename,
                )
            else:
                logger.info("hybrid_evaluation_session: auto-saved to '%s'", output_filename)
        except Exception as save_error:
            logger.error(
                "hybrid_evaluation_session: FAILED to save results to '%s': %s",
                output_filename, save_error,
            )
            if exception_occurred is None:
                raise save_error

        if exception_occurred:
            raise exception_occurred


@asynccontextmanager
async def async_evaluation_session(
    output_filename: str = "evaluation",
    output_dir: Optional[str] = None,
    monitor=None,
    **monitor_kwargs,
):
    """비동기 평가 세션 context manager.

    async with 문과 함께 사용하여 비동기 에이전트를 평가할 때 사용한다.
    세션 종료 시 자동으로 결과를 저장한다 (예외 발생 시에도).

    Args:
        output_filename: 저장할 파일명 (확장자 제외)
        output_dir: 저장 디렉토리 (기본값: None → 현재 디렉토리)
        monitor: 기존 PerformanceMonitor 인스턴스 (기본값: 새로 생성)
        **monitor_kwargs: PerformanceMonitor 초기화 파라미터

    Yields:
        PerformanceMonitor: 평가 모니터 인스턴스

    Example:
        >>> async with async_evaluation_session("results") as monitor:
        ...     result = await agent.ainvoke(question)
        ...     monitor.record_task(create_taskresult(...))
    """
    from .agent_evaluator import PerformanceMonitor
    import os as _os
    _label = _os.path.splitext(_os.path.basename(output_filename))[0]

    _monitor = monitor or PerformanceMonitor(
        output_dir=output_dir, session_label=_label, **monitor_kwargs
    )
    exception_occurred = None

    try:
        yield _monitor
    except Exception as exc:
        exception_occurred = exc
        logger.error("async_evaluation_session: exception in body: %s", exc)
    finally:
        try:
            _monitor.save_to_file(output_filename)
            logger.info(
                "async_evaluation_session: saved to '%s'", output_filename
            )
        except Exception as save_exc:
            logger.error(
                "async_evaluation_session: failed to save '%s': %s",
                output_filename, save_exc,
            )
            if exception_occurred is None:
                raise save_exc
        if exception_occurred is not None:
            raise exception_occurred
