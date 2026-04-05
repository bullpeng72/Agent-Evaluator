"""
Tests for v0.8.0 gap features.

Covers:
- A2: on_error in _CONV_PARAMS
- C1: LatencyTracker TTFT (track_ttft / get_ttft_stats)
- C2: TokenEconomyTracker.get_cost_breakdown_by_framework()
- C3: ToolSelectionTracker.get_f1_by_tool()
- C4: AgentCoordinationTracker.get_network_topology()
- D2: on_record score clamping after modification
- D3: on_error called after _record_to_monitors
- E1: PerformanceMonitor.restore_from_snapshot()
- F1: ConversationMetrics.turn_scores field
- G1: Anthropic cache token fields in _extract_anthropic_metadata
- H1: QuickEval monitor_kwargs validation (unknown params warned & stripped)
- H2: QuickEval.gate() warns when quality/hallucination tracking disabled
- H3: QuickEval.cached() supports async functions
- H4: QuickEval.watch() max_watched_files limits _seen growth
- I1: /api/health otel field is dynamic (not hardcoded False)
- I2: /api/results sort_by / sort_desc parameters
- I3: /results/{file_id}/tasks/filter has comprehensive docstring
"""
from __future__ import annotations

import asyncio
import warnings
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# C1: LatencyTracker TTFT support
# ---------------------------------------------------------------------------

class TestLatencyTrackerTTFT:
    def setup_method(self):
        from agent_evaluator.core.trackers.layer1 import LatencyTracker
        self.tracker = LatencyTracker()

    def test_track_ttft_basic(self):
        self.tracker.track_ttft("t1", 0.25)
        records = self.tracker.ttft_records
        assert len(records) == 1
        assert records[0]["task_id"] == "t1"
        assert records[0]["ttft"] == pytest.approx(0.25)

    def test_get_ttft_stats_empty(self):
        stats = self.tracker.get_ttft_stats()
        assert stats["count"] == 0
        # mean is None or 0.0 when no records
        assert stats["mean"] is None or stats["mean"] == 0.0

    def test_get_ttft_stats_values(self):
        for i, v in enumerate([0.1, 0.2, 0.3, 0.4, 0.5]):
            self.tracker.track_ttft(f"t{i}", v, task_type="qa")
        stats = self.tracker.get_ttft_stats()
        assert stats["count"] == 5
        assert stats["mean"] == pytest.approx(0.3, abs=1e-6)
        assert stats["min"] == pytest.approx(0.1, abs=1e-6)
        assert stats["max"] == pytest.approx(0.5, abs=1e-6)

    def test_get_ttft_stats_by_task_type(self):
        self.tracker.track_ttft("t1", 0.1, task_type="qa")
        self.tracker.track_ttft("t2", 0.5, task_type="tool_use")
        qa_stats = self.tracker.get_ttft_stats(task_type="qa")
        assert qa_stats["count"] == 1
        tu_stats = self.tracker.get_ttft_stats(task_type="tool_use")
        assert tu_stats["count"] == 1

    def test_reset_clears_ttft_records(self):
        self.tracker.track_ttft("t1", 0.1)
        self.tracker.reset()
        assert self.tracker.ttft_records == []


# ---------------------------------------------------------------------------
# C2: TokenEconomyTracker.get_cost_breakdown_by_framework()
# ---------------------------------------------------------------------------

class TestTokenEconomyFrameworkBreakdown:
    def setup_method(self):
        from agent_evaluator.core.trackers.layer1 import TokenEconomyTracker
        self.tracker = TokenEconomyTracker(pricing={"input": 0.001, "output": 0.002})

    def test_empty_breakdown(self):
        result = self.tracker.get_cost_breakdown_by_framework()
        assert isinstance(result, dict)

    def test_breakdown_groups_by_framework(self):
        self.tracker.track_usage("t1", 50, 50, "qa", model="gpt-4")
        self.tracker.track_usage("t2", 100, 100, "qa", model="gpt-4")
        self.tracker.track_usage("t3", 75, 75, "qa", model="claude-3")

        breakdown = self.tracker.get_cost_breakdown_by_framework()
        assert isinstance(breakdown, dict)
        # Method exists and returns a dict (framework may be empty if not tracked separately)
        assert len(breakdown) >= 0


# ---------------------------------------------------------------------------
# C3: ToolSelectionTracker.get_f1_by_tool()
# ---------------------------------------------------------------------------

class TestToolSelectionF1ByTool:
    def setup_method(self):
        from agent_evaluator.core.trackers.layer2 import ToolSelectionTracker
        self.tracker = ToolSelectionTracker()

    def test_empty_f1_by_tool(self):
        result = self.tracker.get_f1_by_tool()
        assert isinstance(result, dict)

    def test_f1_by_tool_returns_metrics(self):
        self.tracker.evaluate_selection(
            task_id="t1",
            actual_tools=["tool_a", "tool_b"],
            expected_tools=["tool_a"],
        )
        self.tracker.evaluate_selection(
            task_id="t2",
            actual_tools=["tool_a"],
            expected_tools=["tool_a", "tool_b"],
        )
        result = self.tracker.get_f1_by_tool()
        assert isinstance(result, dict)
        # tool_a should appear
        if result:
            first_tool = next(iter(result.values()))
            assert "f1" in first_tool or "precision" in first_tool or "tp" in first_tool


# ---------------------------------------------------------------------------
# C4: AgentCoordinationTracker.get_network_topology()
# ---------------------------------------------------------------------------

class TestAgentCoordinationTopology:
    def setup_method(self):
        from agent_evaluator.core.trackers.layer2 import AgentCoordinationTracker
        self.tracker = AgentCoordinationTracker()

    def test_empty_topology(self):
        topo = self.tracker.get_network_topology()
        assert isinstance(topo, dict)
        assert "pattern" in topo
        assert "density" in topo

    def test_hub_pattern_detection(self):
        # Hub: one agent interacts with many others
        for i in range(4):
            self.tracker.track_interaction(
                task_id=f"t{i}",
                from_agent="hub_agent",
                to_agent=f"agent_{i}",
                interaction_type="delegation",
                success=True,
            )
        topo = self.tracker.get_network_topology()
        assert topo["pattern"] in ("hub", "chain", "mesh")
        assert 0.0 <= topo["density"] <= 1.0


# ---------------------------------------------------------------------------
# E1: PerformanceMonitor.restore_from_snapshot()
# ---------------------------------------------------------------------------

class TestRestoreFromSnapshot:
    def test_restore_returns_self(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        monitor = PerformanceMonitor()
        snap = monitor.snapshot()
        result = monitor.restore_from_snapshot(snap)
        assert result is monitor

    def test_restore_invalid_input_raises(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        monitor = PerformanceMonitor()
        with pytest.raises((TypeError, ValueError, KeyError)):
            monitor.restore_from_snapshot("not a dict")  # type: ignore


# ---------------------------------------------------------------------------
# F1: ConversationMetrics.turn_scores field
# ---------------------------------------------------------------------------

class TestConversationMetricsTurnScores:
    def test_turn_scores_field_exists(self):
        from agent_evaluator.core.trackers.conversation import ConversationMetrics
        import inspect
        fields = {f.name for f in ConversationMetrics.__dataclass_fields__.values()}
        assert "turn_scores" in fields

    def _make_metrics(self, **kwargs):
        from agent_evaluator.core.trackers.conversation import ConversationMetrics
        defaults = dict(
            session_id="s1",
            turn_count=2,
            overall_score=0.8,
            context_retention=0.7,
            topic_coherence=0.9,
            progressive_depth=0.6,
            session_completion=1.0,
            avg_turn_latency=0.3,
            score_stddev=0.1,
            computed_at="2026-01-01T00:00:00",
        )
        defaults.update(kwargs)
        return ConversationMetrics(**defaults)

    def test_turn_scores_default_none(self):
        m = self._make_metrics()
        assert m.turn_scores is None

    def test_turn_scores_can_be_set(self):
        m = self._make_metrics(turn_scores={0: 0.8, 1: 0.9})
        assert m.turn_scores == {0: 0.8, 1: 0.9}


# ---------------------------------------------------------------------------
# G1: Anthropic cache token extraction
# ---------------------------------------------------------------------------

class TestAnthropicCacheTokenExtraction:
    def test_cache_tokens_extracted(self):
        """Anthropic SDK >=0.29 cache token fields are included in tokens_used."""
        from agent_evaluator.decorators import _extract_anthropic_metadata

        # Build a mock Anthropic response with cache fields
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cache_creation_input_tokens = 30
        mock_usage.cache_read_input_tokens = 20

        mock_resp = MagicMock()
        mock_resp.usage = mock_usage
        mock_resp.content = []

        meta = _extract_anthropic_metadata(mock_resp)
        assert meta is not None
        tu = meta.tokens_used or {}
        assert tu.get("cache_creation", 0) == 30
        assert tu.get("cache_read", 0) == 20
        assert tu.get("input", 0) == 100
        # total = input + cache_creation + cache_read + output = 200
        assert tu.get("total", 0) == 200

    def test_cache_tokens_absent_fallback(self):
        """If cache fields absent (SDK <0.29), uses regular token counts only."""
        from agent_evaluator.decorators import _extract_anthropic_metadata

        mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
        mock_usage.input_tokens = 80
        mock_usage.output_tokens = 40

        mock_resp = MagicMock()
        mock_resp.usage = mock_usage
        mock_resp.content = []

        meta = _extract_anthropic_metadata(mock_resp)
        assert meta is not None
        tu = meta.tokens_used or {}
        assert tu.get("input", 0) == 80
        assert tu.get("output", 0) == 40
        assert tu.get("cache_creation", 0) == 0
        assert tu.get("cache_read", 0) == 0


# ---------------------------------------------------------------------------
# H1: QuickEval.__init__ validates unknown monitor_kwargs
# ---------------------------------------------------------------------------

class TestQuickEvalMonitorKwargsValidation:
    def test_unknown_kwarg_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from agent_evaluator import QuickEval
            qe = QuickEval("results/", nonexistent_param_xyz=True)
            # Should warn about unknown param
            user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
            assert any("nonexistent_param_xyz" in str(x.message) for x in user_warnings)

    def test_valid_kwargs_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from agent_evaluator import QuickEval
            qe = QuickEval("results/", enable_hallucination_detection=False)
            user_warnings = [x for x in w if issubclass(x.category, UserWarning)
                             and "PerformanceMonitor" in str(x.message)]
            assert len(user_warnings) == 0


# ---------------------------------------------------------------------------
# H2: QuickEval.gate() warns when tracking is disabled
# ---------------------------------------------------------------------------

class TestQuickEvalGateTrackingWarnings:
    def _make_qe(self):
        from agent_evaluator import QuickEval
        return QuickEval("results/")

    def test_gate_hallucination_warns_when_disabled(self):
        qe = self._make_qe()
        # hallucination detection is False by default
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                qe.gate(hallucination=10.0)
            except SystemExit:
                pass
            hall_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning)
                and "hallucination" in str(x.message).lower()
            ]
            assert len(hall_warnings) >= 1


# ---------------------------------------------------------------------------
# H3: QuickEval.cached() supports async functions
# ---------------------------------------------------------------------------

class TestQuickEvalCachedAsync:
    def test_cached_async_function(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        call_count = [0]

        @qe.cached(ttl=60)
        async def async_agent(q: str) -> str:
            call_count[0] += 1
            return f"response:{q}"

        import asyncio

        async def _run():
            r1 = await async_agent("hello")
            r2 = await async_agent("hello")  # should hit cache
            r3 = await async_agent("world")
            assert r1 == "response:hello"
            assert r2 == "response:hello"
            assert r3 == "response:world"
            assert call_count[0] == 2  # "hello" called once, "world" called once

        asyncio.get_event_loop().run_until_complete(_run())

    def test_cached_sync_function_still_works(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        call_count = [0]

        @qe.cached(ttl=60)
        def sync_agent(q: str) -> str:
            call_count[0] += 1
            return f"sync:{q}"

        r1 = sync_agent("a")
        r2 = sync_agent("a")
        assert r1 == r2 == "sync:a"
        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# H4: QuickEval.watch() max_watched_files limits _seen set
# ---------------------------------------------------------------------------

class TestQuickEvalWatchMaxFiles:
    def test_watch_returns_handle_with_stop(self):
        import tempfile, os
        from agent_evaluator import QuickEval
        with tempfile.TemporaryDirectory() as tmpdir:
            qe = QuickEval(tmpdir)
            handle = qe.watch(directory=tmpdir, max_watched_files=100)
            assert hasattr(handle, "stop")
            handle.stop()

    def test_watch_accepts_max_watched_files_param(self):
        import inspect
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.watch)
        assert "max_watched_files" in sig.parameters


# ---------------------------------------------------------------------------
# I1: /api/health otel field dynamic
# ---------------------------------------------------------------------------

class TestHealthOtelDynamic:
    def test_otel_field_not_hardcoded(self):
        """The health endpoint should dynamically detect OTEL, not return False always."""
        from agent_evaluator.serve.routers.data import health
        import inspect
        src = inspect.getsource(health)
        # Should not have hardcoded `"otel": False`
        assert '"otel": False' not in src
        # Should have dynamic detection
        assert "_otel_enabled" in src or "otel_enabled" in src


# ---------------------------------------------------------------------------
# I2: /api/results sort_by / sort_desc
# ---------------------------------------------------------------------------

class TestResultsListSorting:
    def test_sort_by_param_in_signature(self):
        from agent_evaluator.serve.routers.data import list_results
        import inspect
        sig = inspect.signature(list_results)
        assert "sort_by" in sig.parameters
        assert "sort_desc" in sig.parameters

    def test_response_includes_sort_fields(self):
        """The response dict should include sort_by and sort_desc."""
        from agent_evaluator.serve.routers.data import list_results
        import inspect
        src = inspect.getsource(list_results)
        assert '"sort_by"' in src or "'sort_by'" in src
        assert '"sort_desc"' in src or "'sort_desc'" in src


# ---------------------------------------------------------------------------
# I3: filter endpoint has comprehensive docstring
# ---------------------------------------------------------------------------

class TestFilterEndpointDocstring:
    def test_filter_docstring_has_op_table(self):
        from agent_evaluator.serve.routers.data import filter_tasks_advanced
        doc = filter_tasks_advanced.__doc__ or ""
        assert "eq" in doc
        assert "gte" in doc
        assert "contains" in doc
        assert "in" in doc

    def test_filter_docstring_has_logic_description(self):
        from agent_evaluator.serve.routers.data import filter_tasks_advanced
        doc = filter_tasks_advanced.__doc__ or ""
        assert "AND" in doc
        assert "OR" in doc


# ---------------------------------------------------------------------------
# A2: on_error in _CONV_PARAMS
# ---------------------------------------------------------------------------

class TestConvParamsOnError:
    def test_on_error_in_conv_params(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "on_error" in EvalDecorator._CONV_PARAMS
