"""
tests/test_session_types.py
===========================
evaluation_session / hybrid_evaluation_session / async_evaluation_session /
_TaskContext(monitor.task()) 통합 테스트
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
# async_evaluation_session (class-based)
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


# ===========================================================================
# async_evaluation_session (module-level async functions)
# ===========================================================================

async def test_async_evaluation_session_importable():
    """공개 API에서 임포트 가능한지 확인."""
    from agent_evaluator import async_evaluation_session as aes
    assert aes is not None


async def test_async_evaluation_session_records_task():
    """태스크가 기록되는지 확인."""
    import tempfile
    from agent_evaluator import create_taskresult

    with tempfile.TemporaryDirectory() as tmpdir:
        async with async_evaluation_session(
            output_filename="test_async_record",
            output_dir=tmpdir,
        ) as monitor:
            task = create_taskresult(
                task_id="t1",
                question="Q",
                response="A",
                ground_truth="A",
                execution_time=0.5,
            )
            monitor.record_task(task)

        report = monitor.generate_report()
        assert report.total_tasks == 1


async def test_async_evaluation_session_exception_handling():
    """예외 발생 시에도 세션이 정리되고 예외가 다시 전파되는지 확인."""
    with pytest.raises(ValueError, match="test error"):
        async with async_evaluation_session("test_exception") as monitor:
            raise ValueError("test error")


async def test_async_evaluation_session_multiple_tasks():
    """여러 태스크를 기록하고 report 총 수 확인."""
    import tempfile
    from agent_evaluator import create_taskresult

    with tempfile.TemporaryDirectory() as tmpdir:
        async with async_evaluation_session(
            output_filename="multi_task",
            output_dir=tmpdir,
        ) as monitor:
            for i in range(3):
                task = create_taskresult(
                    task_id=f"t{i}",
                    question=f"Q{i}",
                    response=f"A{i}",
                    ground_truth=f"A{i}",
                    execution_time=0.1,
                )
                monitor.record_task(task)

        report = monitor.generate_report()
        assert report.total_tasks == 3


async def test_async_evaluation_session_provides_monitor():
    """context manager가 PerformanceMonitor 인스턴스를 yield 하는지 확인."""
    from agent_evaluator import PerformanceMonitor

    async with async_evaluation_session("check_monitor_type") as monitor:
        assert isinstance(monitor, PerformanceMonitor)


# ===========================================================================
# _TaskContext (monitor.task()) context manager
# ===========================================================================

class TestTaskContextManager:
    """with monitor.task() 컨텍스트 매니저 테스트."""

    def test_task_context_records_task(self):
        """with monitor.task() 블록 후 태스크가 기록되어야 함."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t1", "qa", question="수도는?") as t:
            t.response = "서울"
            t.ground_truth = "서울"
        assert monitor.generate_report().total_tasks == 1

    def test_task_context_sets_task_id(self):
        """task_id가 결과에 반영됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("my_task_id", "qa") as t:
            t.response = "answer"
        tasks = monitor.tcr_tracker.tasks
        assert len(tasks) == 1
        assert tasks[0].task_id == "my_task_id"

    def test_task_context_measures_execution_time(self):
        """execution_time이 자동으로 측정됨 (0 이상)."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t2", "qa") as t:
            t.response = "answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].execution_time >= 0.0

    def test_task_context_success_true_when_response_set(self):
        """response를 설정하면 success=True로 추론됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t3", "qa") as t:
            t.response = "some answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is True

    def test_task_context_success_false_when_no_response(self):
        """response 미설정 시 success=False로 추론됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t4", "qa") as t:
            pass  # response 미설정
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_exception_still_records(self):
        """with 블록 내 예외 발생해도 태스크가 기록됨 (예외는 전파됨)."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with pytest.raises(ValueError):
            with monitor.task("t5", "qa") as t:
                raise ValueError("intentional error")
        # 예외가 발생해도 태스크는 기록됨
        assert monitor.generate_report().total_tasks == 1

    def test_task_context_exception_sets_success_false(self):
        """예외 발생 시 success=False로 설정됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with pytest.raises(RuntimeError):
            with monitor.task("t6", "qa") as t:
                raise RuntimeError("failure")
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_explicit_success_override(self):
        """t.success를 명시적으로 설정하면 그 값이 사용됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t7", "qa") as t:
            t.response = "answer"
            t.success = False  # 명시적 오버라이드
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_question_stored(self):
        """question이 TaskResult에 저장됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t8", "qa", question="my question") as t:
            t.response = "my answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].question == "my question"

    def test_task_context_tool_calls(self):
        """tool_calls 목록이 TaskResult에 전달됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        with monitor.task("t9", "tool_use") as t:
            t.response = "done"
            t.tool_calls = [{"name": "search", "args": {}}]
        tasks = monitor.tcr_tracker.tasks
        assert len(tasks[0].tool_calls) == 1
        assert tasks[0].tool_calls[0]["name"] == "search"

    def test_task_context_multiple_tasks(self):
        """여러 task 컨텍스트를 사용하면 모두 기록됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        for i in range(4):
            with monitor.task(f"task_{i}", "qa") as t:
                t.response = f"answer_{i}"
        assert monitor.generate_report().total_tasks == 4
