"""async_evaluation_session context manager 테스트."""
import pytest
from agent_evaluator import async_evaluation_session, create_taskresult


async def test_async_evaluation_session_importable():
    """공개 API에서 임포트 가능한지 확인."""
    assert async_evaluation_session is not None


async def test_async_evaluation_session_records_task():
    """태스크가 기록되는지 확인."""
    import tempfile

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
