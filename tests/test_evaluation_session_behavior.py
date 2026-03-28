"""
tests/test_evaluation_session_behavior.py
==========================================
evaluation_session / hybrid_evaluation_session / async_evaluation_session 동작 테스트

커버 범위:
  - 정상 종료 시 파일 저장 확인
  - 예외 발생 시에도 파일 저장 후 예외 재전파
  - output_dir 파라미터 전달 확인
  - 저장 실패 시 예외 전파 (원래 예외 없을 때)
  - 저장 실패 + 원래 예외 동시 발생 시 원래 예외 우선
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_evaluator.core.monitor_context import (
    evaluation_session,
    hybrid_evaluation_session,
    async_evaluation_session,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _session_file_exists(tmp_path: Path, stem: str) -> bool:
    """Check whether a JSON (or any suffixed) result file was created."""
    # save_to_file() appends .json automatically
    candidates = list(tmp_path.glob(f"{stem}*"))
    return len(candidates) > 0


# ===========================================================================
# evaluation_session
# ===========================================================================

class TestEvaluationSession:
    def test_file_created_on_normal_exit(self, tmp_path):
        stem = "test_normal"
        with evaluation_session(str(tmp_path / stem)) as monitor:
            pass
        assert _session_file_exists(tmp_path, stem)

    def test_monitor_is_performance_monitor(self, tmp_path):
        from agent_evaluator import PerformanceMonitor
        with evaluation_session(str(tmp_path / "x")) as monitor:
            assert isinstance(monitor, PerformanceMonitor)

    def test_file_created_when_exception_inside(self, tmp_path):
        stem = "test_exc"
        with pytest.raises(ValueError):
            with evaluation_session(str(tmp_path / stem)) as monitor:
                raise ValueError("deliberate")
        assert _session_file_exists(tmp_path, stem)

    def test_original_exception_reraised(self, tmp_path):
        with pytest.raises(RuntimeError, match="boom"):
            with evaluation_session(str(tmp_path / "reraise")) as monitor:
                raise RuntimeError("boom")

    def test_save_failure_propagates_when_no_body_exception(self, tmp_path):
        """If save fails and body had no exception, the save error must propagate."""
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.side_effect = OSError("disk full")
            with pytest.raises(OSError, match="disk full"):
                with evaluation_session(str(tmp_path / "save_fail")) as _:
                    pass

    def test_save_failure_suppressed_when_body_exception_exists(self, tmp_path):
        """If save fails AND body raised, the body exception takes priority."""
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.side_effect = OSError("disk full")
            with pytest.raises(ValueError, match="original"):
                with evaluation_session(str(tmp_path / "dual_fail")) as _:
                    raise ValueError("original")

    def test_enable_security_forwarded(self, tmp_path):
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.return_value = None
            with evaluation_session(
                str(tmp_path / "sec"), enable_security=True
            ) as _:
                pass
            call_kwargs = MockMonitor.call_args.kwargs
            assert call_kwargs.get("enable_security_metrics") is True

    def test_enable_hallucination_forwarded(self, tmp_path):
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.return_value = None
            with evaluation_session(
                str(tmp_path / "hall"), enable_hallucination=False
            ) as _:
                pass
            call_kwargs = MockMonitor.call_args.kwargs
            assert call_kwargs.get("enable_hallucination_detection") is False

    def test_extra_kwargs_forwarded(self, tmp_path):
        """output_dir and other kwargs reach PerformanceMonitor."""
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.return_value = None
            with evaluation_session(
                str(tmp_path / "kw"), output_dir=str(tmp_path)
            ) as _:
                pass
            call_kwargs = MockMonitor.call_args.kwargs
            assert call_kwargs.get("output_dir") == str(tmp_path)


# ===========================================================================
# hybrid_evaluation_session
# ===========================================================================

class TestHybridEvaluationSession:
    def test_file_created_on_normal_exit(self, tmp_path):
        stem = "hybrid_normal"
        with hybrid_evaluation_session(str(tmp_path / stem)) as monitor:
            pass
        assert _session_file_exists(tmp_path, stem)

    def test_monitor_is_hybrid(self, tmp_path):
        from agent_evaluator import HybridPerformanceMonitor
        with hybrid_evaluation_session(str(tmp_path / "h")) as monitor:
            assert isinstance(monitor, HybridPerformanceMonitor)

    def test_exception_reraised(self, tmp_path):
        with pytest.raises(KeyError):
            with hybrid_evaluation_session(str(tmp_path / "exc")) as _:
                raise KeyError("not_found")

    def test_file_created_despite_exception(self, tmp_path):
        stem = "hybrid_exc"
        with pytest.raises(KeyError):
            with hybrid_evaluation_session(str(tmp_path / stem)) as _:
                raise KeyError("x")
        assert _session_file_exists(tmp_path, stem)

    def test_save_failure_propagates_on_clean_body(self, tmp_path):
        with patch(
            "agent_evaluator.core.hybrid_monitor.HybridPerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.side_effect = IOError("no space")
            with pytest.raises(IOError, match="no space"):
                with hybrid_evaluation_session(str(tmp_path / "sf")) as _:
                    pass

    def test_use_deepeval_forwarded(self, tmp_path):
        with patch(
            "agent_evaluator.core.hybrid_monitor.HybridPerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.return_value = None
            with hybrid_evaluation_session(
                str(tmp_path / "dv"), use_deepeval=True
            ) as _:
                pass
            call_kwargs = MockMonitor.call_args.kwargs
            assert call_kwargs.get("use_deepeval") is True

    def test_use_ragas_forwarded(self, tmp_path):
        with patch(
            "agent_evaluator.core.hybrid_monitor.HybridPerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.return_value = None
            with hybrid_evaluation_session(
                str(tmp_path / "rg"), use_ragas=True
            ) as _:
                pass
            call_kwargs = MockMonitor.call_args.kwargs
            assert call_kwargs.get("use_ragas") is True


# ===========================================================================
# async_evaluation_session
# ===========================================================================

class TestAsyncEvaluationSession:
    @pytest.mark.asyncio
    async def test_file_created_on_normal_exit(self, tmp_path):
        stem = "async_normal"
        async with async_evaluation_session(str(tmp_path / stem)) as monitor:
            pass
        assert _session_file_exists(tmp_path, stem)

    @pytest.mark.asyncio
    async def test_exception_reraised(self, tmp_path):
        with pytest.raises(ValueError, match="async_boom"):
            async with async_evaluation_session(str(tmp_path / "aboom")) as _:
                raise ValueError("async_boom")

    @pytest.mark.asyncio
    async def test_file_created_despite_exception(self, tmp_path):
        stem = "async_exc"
        with pytest.raises(ValueError):
            async with async_evaluation_session(str(tmp_path / stem)) as _:
                raise ValueError("x")
        assert _session_file_exists(tmp_path, stem)

    @pytest.mark.asyncio
    async def test_existing_monitor_reused(self, tmp_path):
        """When a monitor is passed in, it must be yielded back unchanged."""
        from agent_evaluator import PerformanceMonitor
        existing = PerformanceMonitor()
        async with async_evaluation_session(
            str(tmp_path / "reuse"), monitor=existing
        ) as m:
            assert m is existing

    @pytest.mark.asyncio
    async def test_save_failure_propagates_on_clean_body(self, tmp_path):
        with patch(
            "agent_evaluator.core.agent_evaluator.PerformanceMonitor"
        ) as MockMonitor:
            instance = MockMonitor.return_value
            instance.save_to_file.side_effect = OSError("write error")
            with pytest.raises(OSError, match="write error"):
                async with async_evaluation_session(str(tmp_path / "asf")) as _:
                    pass
