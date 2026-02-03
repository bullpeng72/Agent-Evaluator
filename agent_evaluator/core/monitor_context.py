"""
Context manager for evaluation sessions
Provides automatic resource management and result saving
"""

from contextlib import contextmanager
from typing import Optional
from pathlib import Path


@contextmanager
def evaluation_session(
    output_filename: str,
    enable_security: bool = False,
    enable_hallucination: bool = True,
    **monitor_kwargs
):
    """
    Context manager for evaluation sessions
    Automatically saves results on exit (even if exception occurs)

    Example:
        ```python
        from agent_evaluator.core.monitor_context import evaluation_session

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

    # Create monitor
    monitor = PerformanceMonitor(
        enable_security_metrics=enable_security,
        enable_hallucination_detection=enable_hallucination,
        **monitor_kwargs
    )

    exception_occurred = None

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
                print(f"⚠️ 오류 발생했지만 결과는 저장되었습니다: {output_filename}")
            else:
                print(f"✅ 자동 저장 완료: {output_filename}")
        except Exception as save_error:
            print(f"❌ 저장 중 오류 발생: {save_error}")

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
        from agent_evaluator.core.monitor_context import hybrid_evaluation_session

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
                print(f"⚠️ 오류 발생했지만 결과는 저장되었습니다: {output_filename}")
            else:
                print(f"✅ 자동 저장 완료: {output_filename}")
        except Exception as save_error:
            print(f"❌ 저장 중 오류 발생: {save_error}")

        if exception_occurred:
            raise exception_occurred
