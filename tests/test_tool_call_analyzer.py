"""
Tests for ToolCallAnalyzer
"""

import pytest
from agent_evaluator.core.trackers.layer2 import ToolCallAnalyzer


@pytest.fixture
def analyzer():
    return ToolCallAnalyzer()


# ---------------------------------------------------------------------------
# 1. Single tool call — statistics are correct
# ---------------------------------------------------------------------------

def test_single_tool_call(analyzer):
    tool_calls = [{"tool": "web_search", "success": True, "duration": 0.5, "parameters": {}}]
    result = analyzer.analyze_execution("t1", tool_calls)
    assert result["total_calls"] == 1
    assert result["failed_calls"] == 0
    assert result["redundant_calls"] == 0
    assert result["efficiency_score"] == 100.0


# ---------------------------------------------------------------------------
# 2. Multiple tool calls — call count aggregation
# ---------------------------------------------------------------------------

def test_multiple_tool_calls_count(analyzer):
    tool_calls = [
        {"tool": "web_search", "success": True, "duration": 0.3, "parameters": {"q": "AI"}},
        {"tool": "calculator", "success": True, "duration": 0.1, "parameters": {"expr": "1+1"}},
        {"tool": "web_search", "success": True, "duration": 0.4, "parameters": {"q": "ML"}},
    ]
    result = analyzer.analyze_execution("t2", tool_calls)
    assert result["total_calls"] == 3
    assert result["unique_tools"] == 2


# ---------------------------------------------------------------------------
# 3. Failed tool call — failed_calls count increments
# ---------------------------------------------------------------------------

def test_failed_tool_call(analyzer):
    tool_calls = [
        {"tool": "web_search", "success": True, "duration": 0.2, "parameters": {}},
        {"tool": "broken_tool", "success": False, "duration": 0.0, "parameters": {}},
    ]
    result = analyzer.analyze_execution("t3", tool_calls)
    assert result["failed_calls"] == 1


# ---------------------------------------------------------------------------
# 4. Average call duration calculation
# ---------------------------------------------------------------------------

def test_avg_call_duration(analyzer):
    tool_calls = [
        {"tool": "tool_a", "success": True, "duration": 1.0, "parameters": {}},
        {"tool": "tool_b", "success": True, "duration": 3.0, "parameters": {}},
    ]
    result = analyzer.analyze_execution("t4", tool_calls)
    # Only calls with duration > 0 are included; average of 1.0 and 3.0 = 2.0
    assert abs(result["avg_call_duration"] - 2.0) < 0.001


# ---------------------------------------------------------------------------
# 5. get_efficiency_stats — return structure
# ---------------------------------------------------------------------------

def test_get_efficiency_stats_structure(analyzer):
    tool_calls = [{"tool": "web_search", "success": True, "duration": 0.5, "parameters": {}}]
    analyzer.analyze_execution("t5", tool_calls)
    stats = analyzer.get_efficiency_stats()
    assert "total_calls" in stats
    assert "avg_calls_per_task" in stats
    assert "avg_efficiency_score" in stats
    assert "total_failed_calls" in stats
    assert "failure_rate" in stats


# ---------------------------------------------------------------------------
# 6. Empty state — get_efficiency_stats without division by zero
# ---------------------------------------------------------------------------

def test_get_efficiency_stats_empty_no_division_by_zero():
    a = ToolCallAnalyzer()
    result = a.get_efficiency_stats()
    # Should return empty dict when no executions recorded
    assert result == {}


# ---------------------------------------------------------------------------
# 7. Redundant calls — same tool+params twice = 1 redundant
# ---------------------------------------------------------------------------

def test_redundant_call_detection(analyzer):
    same_params = {"q": "AI"}
    tool_calls = [
        {"tool": "web_search", "success": True, "duration": 0.3, "parameters": same_params},
        {"tool": "web_search", "success": True, "duration": 0.3, "parameters": same_params},
    ]
    result = analyzer.analyze_execution("t7", tool_calls)
    assert result["redundant_calls"] == 1
    assert result["efficiency_score"] < 100.0


# ---------------------------------------------------------------------------
# 8. Empty tool_calls list — returns minimal dict without error
# ---------------------------------------------------------------------------

def test_empty_tool_calls(analyzer):
    result = analyzer.analyze_execution("t8", [])
    assert result["total_calls"] == 0
    assert result["efficiency_score"] == 100.0
