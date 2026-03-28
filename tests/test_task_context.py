"""_TaskContext (monitor.task()) context manager 테스트."""
import pytest
from agent_evaluator import PerformanceMonitor


class TestTaskContextManager:
    """with monitor.task() 컨텍스트 매니저 테스트."""

    def test_task_context_records_task(self):
        """with monitor.task() 블록 후 태스크가 기록되어야 함."""
        monitor = PerformanceMonitor()
        with monitor.task("t1", "qa", question="수도는?") as t:
            t.response = "서울"
            t.ground_truth = "서울"
        assert monitor.generate_report().total_tasks == 1

    def test_task_context_sets_task_id(self):
        """task_id가 결과에 반영됨."""
        monitor = PerformanceMonitor()
        with monitor.task("my_task_id", "qa") as t:
            t.response = "answer"
        tasks = monitor.tcr_tracker.tasks
        assert len(tasks) == 1
        assert tasks[0].task_id == "my_task_id"

    def test_task_context_measures_execution_time(self):
        """execution_time이 자동으로 측정됨 (0 이상)."""
        monitor = PerformanceMonitor()
        with monitor.task("t2", "qa") as t:
            t.response = "answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].execution_time >= 0.0

    def test_task_context_success_true_when_response_set(self):
        """response를 설정하면 success=True로 추론됨."""
        monitor = PerformanceMonitor()
        with monitor.task("t3", "qa") as t:
            t.response = "some answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is True

    def test_task_context_success_false_when_no_response(self):
        """response 미설정 시 success=False로 추론됨."""
        monitor = PerformanceMonitor()
        with monitor.task("t4", "qa") as t:
            pass  # response 미설정
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_exception_still_records(self):
        """with 블록 내 예외 발생해도 태스크가 기록됨 (예외는 전파됨)."""
        monitor = PerformanceMonitor()
        with pytest.raises(ValueError):
            with monitor.task("t5", "qa") as t:
                raise ValueError("intentional error")
        # 예외가 발생해도 태스크는 기록됨
        assert monitor.generate_report().total_tasks == 1

    def test_task_context_exception_sets_success_false(self):
        """예외 발생 시 success=False로 설정됨."""
        monitor = PerformanceMonitor()
        with pytest.raises(RuntimeError):
            with monitor.task("t6", "qa") as t:
                raise RuntimeError("failure")
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_explicit_success_override(self):
        """t.success를 명시적으로 설정하면 그 값이 사용됨."""
        monitor = PerformanceMonitor()
        with monitor.task("t7", "qa") as t:
            t.response = "answer"
            t.success = False  # 명시적 오버라이드
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].success is False

    def test_task_context_question_stored(self):
        """question이 TaskResult에 저장됨."""
        monitor = PerformanceMonitor()
        with monitor.task("t8", "qa", question="my question") as t:
            t.response = "my answer"
        tasks = monitor.tcr_tracker.tasks
        assert tasks[0].question == "my question"

    def test_task_context_tool_calls(self):
        """tool_calls 목록이 TaskResult에 전달됨."""
        monitor = PerformanceMonitor()
        with monitor.task("t9", "tool_use") as t:
            t.response = "done"
            t.tool_calls = [{"name": "search", "args": {}}]
        tasks = monitor.tcr_tracker.tasks
        assert len(tasks[0].tool_calls) == 1
        assert tasks[0].tool_calls[0]["name"] == "search"

    def test_task_context_multiple_tasks(self):
        """여러 task 컨텍스트를 사용하면 모두 기록됨."""
        monitor = PerformanceMonitor()
        for i in range(4):
            with monitor.task(f"task_{i}", "qa") as t:
                t.response = f"answer_{i}"
        assert monitor.generate_report().total_tasks == 4
