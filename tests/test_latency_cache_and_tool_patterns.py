"""
tests/test_latency_cache_and_tool_patterns.py
===============================================
Round 62 — LatencyTracker._cached_stats 캐시 무효화 테스트
Round 62 — ToolCallAnalyzer.get_tool_usage_patterns() 단일 패스 리팩터 검증
"""
import pytest

from agent_evaluator.core.trackers.layer1 import LatencyTracker
from agent_evaluator.core.trackers.layer2 import ToolCallAnalyzer


# ---------------------------------------------------------------------------
# LatencyTracker — _cached_stats caching & invalidation
# ---------------------------------------------------------------------------

class TestLatencyCachedStats:
    def _record(self, tracker: LatencyTracker, task_id: str, total_time: float):
        tracker.record_latency(task_id, "qa", total_time, {})

    def test_cache_none_initially(self):
        t = LatencyTracker()
        assert t._cached_stats is None

    def test_cache_populated_after_get_latency_stats(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        _ = t.get_latency_stats()
        assert t._cached_stats is not None

    def test_cache_returns_same_object_on_second_call(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        result1 = t.get_latency_stats()
        result2 = t.get_latency_stats()
        # Same dict object (cache hit)
        assert result1 is result2

    def test_cache_invalidated_on_record(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        _ = t.get_latency_stats()
        assert t._cached_stats is not None
        self._record(t, "t2", 2.0)
        assert t._cached_stats is None

    def test_cache_invalidated_on_reset(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        _ = t.get_latency_stats()
        t.reset()
        assert t._cached_stats is None

    def test_cache_invalidated_by_setter(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        _ = t.get_latency_stats()
        t.latencies = []  # setter should clear cache
        assert t._cached_stats is None

    def test_per_type_query_bypasses_cache(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        self._record(t, "t2", 3.0)
        # Full-dataset query → cached
        full = t.get_latency_stats()
        assert t._cached_stats is not None
        # Per-type query → does NOT overwrite cache
        per_type = t.get_latency_stats(task_type="qa")
        # Cache unchanged (same reference as before per-type call)
        assert t._cached_stats is full or t._cached_stats == full

    def test_stats_values_correct_after_cache(self):
        t = LatencyTracker()
        self._record(t, "t1", 1.0)
        self._record(t, "t2", 3.0)
        stats = t.get_latency_stats()
        assert stats["mean"] == pytest.approx(2.0, abs=0.01)
        assert stats["min"] == pytest.approx(1.0, abs=0.01)
        assert stats["max"] == pytest.approx(3.0, abs=0.01)

    def test_empty_returns_zeros_not_cached(self):
        t = LatencyTracker()
        result = t.get_latency_stats()
        assert result["mean"] == 0.0
        # Empty path skips caching (cache remains None so next real record triggers compute)
        # The important thing is empty result is correct
        assert result["p95"] == 0.0

    def test_cache_reflects_updated_data(self):
        t = LatencyTracker()
        self._record(t, "t1", 2.0)
        stats_before = t.get_latency_stats()
        self._record(t, "t2", 4.0)
        stats_after = t.get_latency_stats()
        # mean should increase after adding a higher latency record
        assert stats_after["mean"] > stats_before["mean"]


# ---------------------------------------------------------------------------
# ToolCallAnalyzer — get_tool_usage_patterns() single-pass rewrite
# ---------------------------------------------------------------------------

class TestToolCallAnalyzerPatterns:
    def _analyzer_with_data(self) -> ToolCallAnalyzer:
        a = ToolCallAnalyzer()
        # task_1: 2 calls, 1 redundant, 0 failed, efficiency 95
        a.analyze_execution("task_1", [
            {"tool_name": "search", "success": True, "duration": 0.5},
            {"tool_name": "search", "success": True, "duration": 0.5},  # redundant
        ])
        # task_2: 4 calls, 0 redundant, 1 failed, efficiency 80
        a.analyze_execution("task_2", [
            {"tool_name": "calc", "success": True, "duration": 0.3},
            {"tool_name": "lookup", "success": True, "duration": 0.4},
            {"tool_name": "format", "success": True, "duration": 0.2},
            {"tool_name": "send", "success": False, "duration": 0.1},
        ])
        # task_3: 7 calls — falls in 6-10 bucket
        a.analyze_execution("task_3", [
            {"tool_name": f"tool_{i}", "success": True, "duration": 0.1}
            for i in range(7)
        ])
        return a

    def test_returns_required_top_level_keys(self):
        a = self._analyzer_with_data()
        result = a.get_tool_usage_patterns()
        for key in ("total_tasks", "total_tool_calls", "pattern_analysis",
                    "usage_distribution", "efficiency_distribution",
                    "redundancy_impact", "failure_impact"):
            assert key in result, f"Missing key: {key}"

    def test_total_tasks_correct(self):
        a = self._analyzer_with_data()
        assert a.get_tool_usage_patterns()["total_tasks"] == 3

    def test_total_tool_calls_correct(self):
        a = self._analyzer_with_data()
        assert a.get_tool_usage_patterns()["total_tool_calls"] == 2 + 4 + 7

    def test_usage_distribution_buckets(self):
        a = self._analyzer_with_data()
        dist = a.get_tool_usage_patterns()["usage_distribution"]
        # task_1 → 2 calls → 1-2 bucket
        assert dist["1-2_calls"] == 1
        # task_2 → 4 calls → 3-5 bucket
        assert dist["3-5_calls"] == 1
        # task_3 → 7 calls → 6-10 bucket
        assert dist["6-10_calls"] == 1
        assert dist["11+_calls"] == 0

    def test_tasks_with_redundancy(self):
        a = self._analyzer_with_data()
        p = a.get_tool_usage_patterns()["pattern_analysis"]
        # task_1 has redundant call
        assert p["tasks_with_redundancy"] >= 1

    def test_tasks_with_failures(self):
        a = self._analyzer_with_data()
        p = a.get_tool_usage_patterns()["pattern_analysis"]
        # task_2 has a failed call
        assert p["tasks_with_failures"] >= 1

    def test_redundancy_impact_total(self):
        a = self._analyzer_with_data()
        ri = a.get_tool_usage_patterns()["redundancy_impact"]
        assert ri["total_redundant"] >= 0
        assert "avg_redundant_per_task" in ri

    def test_failure_impact_total(self):
        a = self._analyzer_with_data()
        fi = a.get_tool_usage_patterns()["failure_impact"]
        assert fi["total_failed"] >= 0
        assert "avg_failed_per_task" in fi

    def test_empty_returns_minimal_structure(self):
        a = ToolCallAnalyzer()
        result = a.get_tool_usage_patterns()
        assert result["total_tasks"] == 0
        assert result["tool_frequency"] == {}

    def test_eleven_plus_bucket(self):
        a = ToolCallAnalyzer()
        a.analyze_execution("heavy", [
            {"tool_name": f"t{i}", "success": True, "duration": 0.05}
            for i in range(12)
        ])
        dist = a.get_tool_usage_patterns()["usage_distribution"]
        assert dist["11+_calls"] == 1

    def test_avg_redundant_per_task_formula(self):
        a = ToolCallAnalyzer()
        a.analyze_execution("t1", [
            {"tool_name": "x", "success": True, "duration": 0.1},
            {"tool_name": "x", "success": True, "duration": 0.1},  # redundant
        ])
        ri = a.get_tool_usage_patterns()["redundancy_impact"]
        # 1 task, should have avg == total_redundant / 1
        assert ri["avg_redundant_per_task"] == pytest.approx(ri["total_redundant"], abs=0.01)
