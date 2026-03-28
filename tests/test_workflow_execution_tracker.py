"""
tests/test_workflow_execution_tracker.py
=========================================
WorkflowExecutionTracker 테스트
"""
import pytest

from agent_evaluator.core.trackers.layer2 import WorkflowExecutionTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_steps(
    tracker: WorkflowExecutionTracker,
    n: int = 3,
    success: bool = True,
    framework: str = "langchain",
    task_id: str = "t1",
) -> None:
    for i in range(n):
        tracker.track_step(
            task_id=task_id,
            step_name=f"step_{i}",
            step_type="chain_step",
            success=success,
            execution_time=float(i + 1),
            framework=framework,
        )


# ===========================================================================
# track_step
# ===========================================================================

class TestTrackStep:
    def test_basic_record(self):
        t = WorkflowExecutionTracker()
        result = t.track_step("t1", "retrieval", "node", True, 0.5, "langgraph")
        assert result["task_id"] == "t1"
        assert result["step_name"] == "retrieval"
        assert result["success"] is True
        assert result["execution_time"] == pytest.approx(0.5)
        assert result["framework"] == "langgraph"

    def test_metadata_stored(self):
        t = WorkflowExecutionTracker()
        result = t.track_step("t1", "s", "node", True, 1.0, metadata={"key": "val"})
        assert result["metadata"]["key"] == "val"

    def test_steps_accumulated(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 4)
        assert len(t.executions) == 4

    def test_multiple_frameworks(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 2, framework="langchain")
        _add_steps(t, 2, framework="langgraph")
        assert len(t.executions) == 4


# ===========================================================================
# calculate_execution_success_rate — empty state
# ===========================================================================

class TestCalculateExecutionSuccessRateEmpty:
    def test_empty_returns_structured_zeros(self):
        t = WorkflowExecutionTracker()
        result = t.calculate_execution_success_rate()
        assert result["step_success_rate"] == 0.0
        assert result["total_steps"] == 0
        assert result["total_tasks"] == 0
        assert result["task_success_rate"] == 0.0
        assert result["avg_steps_per_task"] == 0.0

    def test_empty_has_required_keys(self):
        t = WorkflowExecutionTracker()
        result = t.calculate_execution_success_rate()
        for key in (
            "step_success_rate", "total_steps", "successful_steps",
            "failed_steps", "total_tasks", "fully_successful_tasks",
            "task_success_rate", "avg_steps_per_task",
        ):
            assert key in result, f"missing key: {key}"

    def test_framework_filter_no_match(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 3, framework="langchain")
        result = t.calculate_execution_success_rate(framework="langgraph")
        assert result["total_steps"] == 0


# ===========================================================================
# calculate_execution_success_rate — populated
# ===========================================================================

class TestCalculateExecutionSuccessRatePopulated:
    def test_all_success(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 5, success=True)
        result = t.calculate_execution_success_rate()
        assert result["step_success_rate"] == pytest.approx(100.0)
        assert result["failed_steps"] == 0

    def test_all_fail(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 4, success=False)
        result = t.calculate_execution_success_rate()
        assert result["step_success_rate"] == pytest.approx(0.0)
        assert result["successful_steps"] == 0

    def test_mixed_success(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 2, success=True, task_id="t1")
        t.track_step("t1", "final", "chain_step", False, 1.0)
        result = t.calculate_execution_success_rate()
        assert result["step_success_rate"] == pytest.approx(2 / 3 * 100, rel=1e-3)

    def test_task_id_filter(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 3, task_id="t1")
        _add_steps(t, 2, task_id="t2")
        result = t.calculate_execution_success_rate(task_id="t1")
        assert result["total_steps"] == 3
        assert result["total_tasks"] == 1

    def test_framework_filter(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 3, framework="langchain", task_id="t1")
        _add_steps(t, 2, framework="langgraph", task_id="t2")
        result = t.calculate_execution_success_rate(framework="langgraph")
        assert result["total_steps"] == 2

    def test_fully_successful_tasks(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 2, success=True, task_id="t1")
        _add_steps(t, 2, success=False, task_id="t2")
        result = t.calculate_execution_success_rate()
        assert result["fully_successful_tasks"] == 1
        assert result["task_success_rate"] == pytest.approx(50.0)

    def test_avg_steps_per_task(self):
        t = WorkflowExecutionTracker()
        _add_steps(t, 3, task_id="t1")
        _add_steps(t, 1, task_id="t2")
        result = t.calculate_execution_success_rate()
        assert result["avg_steps_per_task"] == pytest.approx(2.0)


# ===========================================================================
# get_graph_traversal_efficiency
# ===========================================================================

class TestGetGraphTraversalEfficiency:
    def test_no_langgraph_data(self):
        t = WorkflowExecutionTracker()
        result = t.get_graph_traversal_efficiency("nonexistent")
        assert result["efficiency"] == 0
        assert "note" in result

    def test_langgraph_efficiency_calculation(self):
        t = WorkflowExecutionTracker()
        # 2 successful nodes + 1 branch = 3 total steps
        t.track_step("t1", "n1", "node", True, 1.0, "langgraph")
        t.track_step("t1", "n2", "node", True, 0.5, "langgraph")
        t.track_step("t1", "b1", "branch", True, 0.1, "langgraph")
        result = t.get_graph_traversal_efficiency("t1")
        assert result["nodes_executed"] == 2
        assert result["branches_taken"] == 1
        assert result["efficiency"] > 0

    def test_excludes_zero_duration_from_avg_node_time(self):
        t = WorkflowExecutionTracker()
        t.track_step("t1", "n1", "node", True, 2.0, "langgraph")
        t.track_step("t1", "n2", "node", True, 0.0, "langgraph")  # unmeasured
        result = t.get_graph_traversal_efficiency("t1")
        assert result["avg_node_time"] == pytest.approx(2.0)


# ===========================================================================
# get_critical_path_analysis
# ===========================================================================

class TestGetCriticalPathAnalysis:
    def test_empty_returns_structured_result(self):
        t = WorkflowExecutionTracker()
        result = t.get_critical_path_analysis()
        assert result["total_workflows"] == 0
        assert result["critical_path"] == []
        assert result["bottlenecks"] == []

    def test_bottlenecks_identified(self):
        t = WorkflowExecutionTracker()
        # slow step
        t.track_step("t1", "slow_llm", "node", True, 5.0)
        t.track_step("t1", "fast_retrieval", "node", True, 0.3)
        result = t.get_critical_path_analysis()
        # slow_llm should appear in bottlenecks
        bottleneck_names = [b["step_name"] for b in result["bottlenecks"]]
        assert "slow_llm" in bottleneck_names

    def test_excludes_zero_duration_from_critical_path(self):
        t = WorkflowExecutionTracker()
        t.track_step("t1", "s1", "node", True, 0.0)  # unmeasured
        t.track_step("t1", "s2", "node", True, 1.5)
        result = t.get_critical_path_analysis()
        # s2 should appear in critical path; s1 has avg_time 0
        step_names = [s["step_name"] for s in result["critical_path"]]
        assert "s2" in step_names

    def test_step_success_rate_calculated(self):
        t = WorkflowExecutionTracker()
        t.track_step("t1", "s1", "node", True, 1.0)
        t.track_step("t2", "s1", "node", False, 1.0)
        result = t.get_critical_path_analysis()
        s1 = next(s for s in result["critical_path"] if s["step_name"] == "s1")
        assert s1["success_rate"] == pytest.approx(50.0)


# ===========================================================================
# __repr__
# ===========================================================================

def test_repr_empty():
    t = WorkflowExecutionTracker()
    assert "WorkflowExecutionTracker" in repr(t)
    assert "steps=0" in repr(t)


def test_repr_after_track():
    t = WorkflowExecutionTracker()
    _add_steps(t, 4)
    assert "steps=4" in repr(t)
