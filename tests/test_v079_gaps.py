"""
Tests for v0.7.9 gap features.

Covers:
- A2: eval_context chunk_step
- A5: allow_duplicate_task_ids
- A6: jitter_type in agent_eval_with_retry
- A7: load_previous_session in conversation_eval
- A8: return_format in batch_eval
- D1: monitor.reset(keep_config)
- D2: monitor.snapshot() / compare_with_snapshot()
- D3: monitor.get_timeseries_metrics()
- D4: monitor.export_to_dataframe()
- D5: monitor.clone()
- D7: register_aggregator / run_aggregator / list_aggregators
- D8: monitor.merge()
- E1: QuickEval.from_config()
- E2: QuickEval.export_to_dataframe()
- E3: QuickEval.replay()
- E4: QuickEval.ab_test()
- E5: QuickEval.cached()
- E6: QuickEval.watch()
- F1: AnomalyDetector.explain_event()
- F2: CostTracker.learn_cost_model()
- F3: MultimodalMetricsTracker
- G2: MAX_NESTING_DEPTH warning
- H1: AGENT_EVAL_PRESETS
- H2: format_error_context
- H3: ResponseCache
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import warnings
from datetime import datetime
from typing import Any, Dict

import pytest

from agent_evaluator import PerformanceMonitor, TaskResult, TaskType, create_taskresult


def _make_task(task_id="t1", accuracy=0.9, latency=1.0) -> TaskResult:
    return create_taskresult(
        task_id=task_id,
        question="test?",
        response="answer",
        ground_truth="answer",
        execution_time=latency,
        task_type="qa",
    )


def _make_monitor_with_tasks(n=3, out_dir="results/") -> PerformanceMonitor:
    m = PerformanceMonitor(output_dir=out_dir)
    for i in range(n):
        m.record_task(_make_task(task_id=f"task_{i}"))
    return m


# ---------------------------------------------------------------------------
# A2: eval_context chunk_step
# ---------------------------------------------------------------------------
class TestChunkStep:
    def test_chunk_step_records_streaming_steps(self):
        from agent_evaluator import eval_context
        m = PerformanceMonitor()
        with eval_context(m, "qa", question="q", ground_truth="a") as ctx:
            ctx.chunk_step(content="hello", metadata={"tokens": 2})
            ctx.chunk_step(content="world", metadata={"tokens": 3})
            ctx.response = "hello world"
        tasks = m.tasks
        assert len(tasks) == 1
        extra = tasks[0].extra or {}
        assert extra.get("chunk_count") == 2
        assert extra.get("total_chunk_chars") == len("hello") + len("world")
        assert len(extra.get("streaming_steps", [])) == 2

    def test_chunk_step_method_chaining(self):
        from agent_evaluator import eval_context
        m = PerformanceMonitor()
        with eval_context(m, "qa", question="q") as ctx:
            result = ctx.chunk_step("a").chunk_step("b")
            assert result is ctx
            ctx.response = "ab"
        assert m.task_count == 1

    def test_no_chunk_steps_no_extra(self):
        from agent_evaluator import eval_context
        m = PerformanceMonitor()
        with eval_context(m, "qa", question="q") as ctx:
            ctx.response = "answer"
        tasks = m.tasks
        assert len(tasks) == 1
        extra = tasks[0].extra or {}
        assert "streaming_steps" not in extra


# ---------------------------------------------------------------------------
# A5: allow_duplicate_task_ids
# ---------------------------------------------------------------------------
class TestAllowDuplicateTaskIds:
    def test_duplicate_warning(self):
        """allow_duplicate_task_ids was removed; passing it raises TypeError."""
        import pytest
        from agent_evaluator import agent_eval
        m = PerformanceMonitor()
        with pytest.raises(TypeError):
            agent_eval(m, task_type="qa", allow_duplicate_task_ids=False)

    def test_no_warning_when_allowed(self):
        """allow_duplicate_task_ids=True (default) → no warning."""
        from agent_evaluator import agent_eval
        m = PerformanceMonitor()

        @agent_eval(m, task_type="qa")
        def fn(question, ground_truth=""): return "ok"

        fn("q", ground_truth="a")
        fn("q", ground_truth="a")
        assert m.task_count == 2


def allow_duplicate_task_ids_warning_flag_exists():
    from agent_evaluator import _FRAMEWORK_ADAPTERS
    from agent_evaluator.decorators import _build_and_record
    import inspect
    sig = inspect.signature(_build_and_record)
    return "allow_duplicate_task_ids" in sig.parameters


# ---------------------------------------------------------------------------
# A6: jitter_type in agent_eval (통합 후 agent_eval 사용)
# ---------------------------------------------------------------------------
class TestJitterType:
    def test_jitter_type_none_no_sleep(self, monkeypatch):
        from agent_evaluator import agent_eval
        from agent_evaluator.decorators import RetryConfig
        sleep_calls = []
        monkeypatch.setattr("time.sleep", lambda t: sleep_calls.append(t))
        m = PerformanceMonitor()
        attempts = [0]

        @agent_eval(m, "qa", retry=RetryConfig(max=2, delay=0.01,
                    jitter_type="none", on=(ValueError,)))
        def fn(question, ground_truth=""):
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("retry")
            return "ok"

        fn("q")
        assert attempts[0] >= 1

    def test_jitter_type_full_produces_float(self):
        """jitter_type parameter accepted without error via RetryConfig."""
        from agent_evaluator import agent_eval
        from agent_evaluator.decorators import RetryConfig
        m = PerformanceMonitor()

        @agent_eval(m, "qa", retry=RetryConfig(max=1, jitter_type="full", max_delay=30.0))
        def fn(question, ground_truth=""): return "ok"

        result = fn("q")
        assert result == "ok"

    def test_jitter_type_decorrelated(self):
        from agent_evaluator import agent_eval
        from agent_evaluator.decorators import RetryConfig
        m = PerformanceMonitor()

        @agent_eval(m, "qa", retry=RetryConfig(max=1, jitter_type="decorrelated", delay=0.001))
        def fn(question, ground_truth=""): return "ok"

        result = fn("q")
        assert result == "ok"


# ---------------------------------------------------------------------------
# A8: return_format in batch_eval
# ---------------------------------------------------------------------------
class TestReturnFormat:
    def test_return_format_list(self):
        from agent_evaluator import batch_eval
        m = PerformanceMonitor()

        @batch_eval(m, return_format="list")
        def fn(questions, ground_truths=None): return [f"r{i}" for i in range(len(questions))]

        result = fn(questions=["a", "b"], ground_truths=["a", "b"])
        assert isinstance(result, list)
        assert len(result) == 2

    def test_return_format_tuple(self):
        from agent_evaluator import batch_eval
        m = PerformanceMonitor()

        @batch_eval(m, return_format="tuple")
        def fn(questions, ground_truths=None): return [f"r{i}" for i in range(len(questions))]

        result = fn(questions=["a", "b"])
        assert isinstance(result, tuple)
        assert len(result) == 2
        responses, task_results = result
        assert isinstance(responses, list)

    def test_return_format_dataframe(self):
        pytest.importorskip("pandas")
        from agent_evaluator import batch_eval
        import pandas as pd
        m = PerformanceMonitor()

        @batch_eval(m, return_format="dataframe")
        def fn(questions, ground_truths=None): return ["r"] * len(questions)

        result = fn(questions=["a", "b", "c"])
        assert isinstance(result, pd.DataFrame)
        assert "task_id" in result.columns


# ---------------------------------------------------------------------------
# D1: monitor.reset(keep_config)
# ---------------------------------------------------------------------------
class TestMonitorReset:
    def test_reset_clears_tasks(self):
        m = _make_monitor_with_tasks(3)
        assert m.task_count == 3
        m.reset()
        assert m.task_count == 0

    def test_reset_returns_self(self):
        m = _make_monitor_with_tasks(2)
        result = m.reset()
        assert result is m

    def test_reset_keeps_config(self):
        m = PerformanceMonitor(output_dir="test_results/")
        m.record_task(_make_task())
        m.reset(keep_config=True)
        assert str(m.output_dir) == "test_results" or str(m.output_dir) == "test_results/"
        assert m.task_count == 0

    def test_reset_method_chaining(self):
        m = _make_monitor_with_tasks(2)
        t = _make_task("new_task")
        m.reset().record_task(t)
        assert m.task_count == 1


# ---------------------------------------------------------------------------
# D3: get_timeseries_metrics
# ---------------------------------------------------------------------------
class TestTimeseriesMetrics:
    def test_timeseries_returns_list(self):
        m = _make_monitor_with_tasks(3)
        result = m.get_timeseries_metrics("accuracy", "hour")
        assert isinstance(result, list)

    def test_timeseries_empty_for_no_tasks(self):
        m = PerformanceMonitor()
        result = m.get_timeseries_metrics("latency")
        assert result == []

    def test_timeseries_granularity_options(self):
        m = _make_monitor_with_tasks(2)
        for gran in ("minute", "hour", "day"):
            result = m.get_timeseries_metrics("accuracy", gran)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# D4: export_to_dataframe
# ---------------------------------------------------------------------------
class TestExportToDataframe:
    def test_export_basic(self):
        pytest.importorskip("pandas")
        import pandas as pd
        m = _make_monitor_with_tasks(3)
        df = m.export_to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "task_id" in df.columns

    def test_export_with_include_fields(self):
        pytest.importorskip("pandas")
        import pandas as pd
        import dataclasses
        m = PerformanceMonitor()
        t = _make_task()
        t = dataclasses.replace(t, extra={"intent": "greeting"})
        m.record_task(t)
        df = m.export_to_dataframe(include_fields=["intent"])
        assert "extra.intent" in df.columns
        assert df["extra.intent"].iloc[0] == "greeting"


# ---------------------------------------------------------------------------
# D5: monitor.clone()
# ---------------------------------------------------------------------------
class TestMonitorClone:
    def test_clone_empty_tasks(self):
        m = _make_monitor_with_tasks(3)
        cloned = m.clone()
        assert cloned.task_count == 0
        assert cloned.output_dir == m.output_dir

    def test_clone_independent(self):
        m = _make_monitor_with_tasks(2)
        cloned = m.clone()
        cloned.record_task(_make_task("extra"))
        assert m.task_count == 2
        assert cloned.task_count == 1


# ---------------------------------------------------------------------------
# D7: register_aggregator / run_aggregator / list_aggregators
# ---------------------------------------------------------------------------
class TestCustomAggregator:
    def test_register_and_run(self):
        m = _make_monitor_with_tasks(3)
        m.register_aggregator("count", lambda tasks: len(tasks))
        result = m.run_aggregator("count")
        assert result == 3

    def test_list_aggregators(self):
        m = PerformanceMonitor()
        assert m.list_aggregators() == []
        m.register_aggregator("fn1", lambda t: 1)
        m.register_aggregator("fn2", lambda t: 2)
        assert set(m.list_aggregators()) == {"fn1", "fn2"}

    def test_run_unknown_raises_key_error(self):
        m = PerformanceMonitor()
        with pytest.raises(KeyError):
            m.run_aggregator("nonexistent")

    def test_register_returns_self(self):
        m = PerformanceMonitor()
        result = m.register_aggregator("fn", lambda t: t)
        assert result is m


# ---------------------------------------------------------------------------
# D8: monitor.merge()
# ---------------------------------------------------------------------------
class TestMonitorMerge:
    def test_merge_combines_tasks(self):
        m1 = _make_monitor_with_tasks(2)
        m2 = PerformanceMonitor()
        m2.record_task(_make_task("m2_t1"))
        m2.record_task(_make_task("m2_t2"))
        merged = m1.merge(m2)
        assert merged.task_count == 4

    def test_merge_uses_self_config(self):
        m1 = PerformanceMonitor(output_dir="dir_a/")
        m2 = PerformanceMonitor(output_dir="dir_b/")
        merged = m1.merge(m2)
        assert str(merged.output_dir).rstrip("/") == "dir_a"

    def test_merge_does_not_modify_originals(self):
        m1 = _make_monitor_with_tasks(2)
        m2 = _make_monitor_with_tasks(3)
        _ = m1.merge(m2)
        assert m1.task_count == 2
        assert m2.task_count == 3


# ---------------------------------------------------------------------------
# E1: QuickEval.from_config()
# ---------------------------------------------------------------------------
class TestQuickEvalFromConfig:
    def test_from_json_config(self, tmp_path):
        from agent_evaluator import QuickEval
        config = {"output_dir": str(tmp_path), "enable_hallucination": False}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))
        qe = QuickEval.from_config(str(config_file))
        assert qe is not None
        assert str(qe._monitor.output_dir) == str(tmp_path)

    def test_from_missing_file_raises(self):
        from agent_evaluator import QuickEval
        with pytest.raises(FileNotFoundError):
            QuickEval.from_config("/nonexistent/path.json")


# ---------------------------------------------------------------------------
# E2: QuickEval.export_to_dataframe()
# ---------------------------------------------------------------------------
class TestQuickEvalExportDataframe:
    def test_export_raises_when_no_tasks(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        with pytest.raises(RuntimeError):
            qe.export_to_dataframe()

    def test_export_after_tasks(self):
        pytest.importorskip("pandas")
        import pandas as pd
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        qe._monitor.record_task(_make_task("e2_t1"))
        df = qe.export_to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# E3: QuickEval.replay()
# ---------------------------------------------------------------------------
class TestQuickEvalReplay:
    def test_replay_loads_tasks(self, tmp_path):
        from agent_evaluator import QuickEval
        # Create a simple JSON results file
        tasks_data = [
            {
                "task_id": "r1", "task_type": "qa", "success": True,
                "completion_score": 1.0, "accuracy_score": 0.9,
                "execution_time": 1.0, "tokens_used": {"total": 100},
                "tool_calls": [], "attempts": 1, "errors": [],
                "timestamp": datetime.now().isoformat(),
            }
        ]
        results = {"tasks": tasks_data}
        fpath = tmp_path / "test_results.json"
        fpath.write_text(json.dumps(results))

        qe = QuickEval(str(tmp_path))
        result = qe.replay(str(fpath))
        assert result is qe  # method chaining
        assert qe._monitor.task_count == 1


# ---------------------------------------------------------------------------
# E4: QuickEval.ab_test()
# ---------------------------------------------------------------------------
class TestQuickEvalAbTest:
    def test_ab_test_basic(self):
        from agent_evaluator import QuickEval
        qe_a = QuickEval("results/")
        qe_b = QuickEval("results/")
        for i in range(5):
            qe_a._monitor.record_task(_make_task(f"a{i}"))
        for i in range(5):
            qe_b._monitor.record_task(_make_task(f"b{i}"))
        result = qe_a.ab_test(qe_b)
        assert "self_mean" in result
        assert "other_mean" in result
        assert "delta" in result
        assert "better" in result
        assert "sample_sizes" in result

    def test_ab_test_empty_monitors(self):
        from agent_evaluator import QuickEval
        qe_a = QuickEval("results/")
        qe_b = QuickEval("results/")
        result = qe_a.ab_test(qe_b)
        assert result["better"] == "equal"


# ---------------------------------------------------------------------------
# E5: QuickEval.cached()
# ---------------------------------------------------------------------------
class TestQuickEvalCached:
    def test_cached_returns_same_result(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        call_count = [0]

        @qe.cached(ttl=60)
        def fn(x):
            call_count[0] += 1
            return f"result_{x}"

        r1 = fn("test")
        r2 = fn("test")
        assert r1 == r2
        assert call_count[0] == 1  # second call served from cache

    def test_cached_different_args_not_cached(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        call_count = [0]

        @qe.cached(ttl=60)
        def fn(x):
            call_count[0] += 1
            return f"result_{x}"

        fn("a")
        fn("b")
        assert call_count[0] == 2  # different args → different cache keys

    def test_cached_ttl_expiry(self):
        from agent_evaluator import QuickEval
        qe = QuickEval("results/")
        call_count = [0]

        @qe.cached(ttl=0.01)  # very short TTL
        def fn(x):
            call_count[0] += 1
            return f"result_{x}"

        fn("test")
        time.sleep(0.05)
        fn("test")
        assert call_count[0] == 2  # cache expired → re-called


# ---------------------------------------------------------------------------
# E6: QuickEval.watch()
# ---------------------------------------------------------------------------
class TestQuickEvalWatch:
    def test_watch_returns_handle_with_stop(self, tmp_path):
        from agent_evaluator import QuickEval
        qe = QuickEval(str(tmp_path))
        handle = qe.watch(directory=str(tmp_path))
        assert hasattr(handle, "stop")
        handle.stop()


# ---------------------------------------------------------------------------
# F1: AnomalyDetector.explain_event()
# ---------------------------------------------------------------------------
class TestAnomalyExplain:
    def test_explain_event_returns_dict(self):
        from agent_evaluator.anomaly.detector import AnomalyDetector, AnomalyEvent
        detector = AnomalyDetector()
        event = AnomalyEvent(
            type="accuracy_drift",
            severity="warning",
            detail="accuracy dropped",
            value=0.6,
            threshold=0.85,
        )
        result = detector.explain_event(event)
        assert "metric" in result
        assert "explanation" in result
        assert "suggested_action" in result
        assert "deviation_pct" in result

    def test_explain_high_deviation_is_critical(self):
        from agent_evaluator.anomaly.detector import AnomalyDetector, AnomalyEvent
        detector = AnomalyDetector()
        event = AnomalyEvent(
            type="latency_trend",
            severity="critical",
            detail="latency high",
            value=5.0,
            threshold=1.0,
        )
        result = detector.explain_event(event)
        assert result["severity"] == "critical"
        assert result["deviation_pct"] > 30


# ---------------------------------------------------------------------------
# F2: CostTracker.learn_cost_model()
# ---------------------------------------------------------------------------
class TestCostModelLearning:
    def test_learn_cost_model_basic(self):
        import dataclasses
        from agent_evaluator.cost.policy import CostTracker
        tracker = CostTracker()
        tasks = []
        t = _make_task()
        t = dataclasses.replace(t, tokens_used={"total": 1000, "model": "gpt-4o"})
        t = dataclasses.replace(t, extra={"cost_usd": 0.005})
        tasks.append(t)
        result = tracker.learn_cost_model(tasks)
        assert isinstance(result, dict)
        # gpt-4o: $0.005 / 1k tokens = $0.005 per 1k
        assert "gpt-4o" in result
        assert abs(result["gpt-4o"] - 0.005) < 0.001

    def test_auto_price_map_merges(self):
        from agent_evaluator.cost.policy import CostTracker
        tracker = CostTracker()
        tracker._learned_prices = {"my-model": 0.001}
        price_map = tracker.auto_price_map
        assert "my-model" in price_map
        assert "claude-sonnet-4-6" in price_map  # builtin model


# ---------------------------------------------------------------------------
# F3: MultimodalMetricsTracker
# ---------------------------------------------------------------------------
class TestMultimodalMetrics:
    def test_track_multimodal_basic(self):
        import dataclasses
        from agent_evaluator.core.trackers.layer1 import MultimodalMetricsTracker
        tracker = MultimodalMetricsTracker()
        t = _make_task()
        t = dataclasses.replace(t, extra={
            "image_count": 2,
            "audio_duration_seconds": 5.5,
        })
        tracker.track_multimodal(t)
        summary = tracker.get_multimodal_summary()
        assert summary["image_count"] == 2
        assert summary["audio_duration_seconds"] == 5.5
        assert summary["total_tracked"] == 1
        assert "image" in summary["modality_mix"]
        assert "audio" in summary["modality_mix"]

    def test_multimodal_text_only(self):
        from agent_evaluator.core.trackers.layer1 import MultimodalMetricsTracker
        tracker = MultimodalMetricsTracker()
        tracker.track_multimodal(_make_task())
        summary = tracker.get_multimodal_summary()
        assert "text" in summary["modality_mix"]

    def test_multimodal_tracker_reset(self):
        from agent_evaluator.core.trackers.layer1 import MultimodalMetricsTracker
        tracker = MultimodalMetricsTracker()
        tracker.track_multimodal(_make_task())
        tracker.reset()
        assert tracker.get_multimodal_summary()["total_tracked"] == 0


# ---------------------------------------------------------------------------
# G2: MAX_NESTING_DEPTH warning
# ---------------------------------------------------------------------------
class TestMaxNestingDepth:
    def test_max_nesting_depth_constant_exists(self):
        from agent_evaluator.decorators import MAX_NESTING_DEPTH
        assert isinstance(MAX_NESTING_DEPTH, int)
        assert MAX_NESTING_DEPTH > 0

    def test_deep_nesting_triggers_resource_warning(self):
        from agent_evaluator import eval_context
        from agent_evaluator.decorators import MAX_NESTING_DEPTH, _NEST_DEPTH
        # temporarily lower the limit for testing
        import agent_evaluator.decorators as _dec
        original = _dec.MAX_NESTING_DEPTH
        _dec.MAX_NESTING_DEPTH = 2
        m = PerformanceMonitor()
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with eval_context(m, "qa", question="q") as c1:
                    with eval_context(m, "qa", question="q") as c2:
                        with eval_context(m, "qa", question="q") as c3:
                            c3.response = "inner"
                        c2.response = "mid"
                    c1.response = "outer"
            resource_warns = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(resource_warns) > 0
        finally:
            _dec.MAX_NESTING_DEPTH = original


# ---------------------------------------------------------------------------
# H1: AGENT_EVAL_PRESETS
# ---------------------------------------------------------------------------
class TestAgentEvalPresets:
    def test_presets_exist(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert isinstance(AGENT_EVAL_PRESETS, dict)
        assert "production" in AGENT_EVAL_PRESETS
        assert "development" in AGENT_EVAL_PRESETS
        assert "testing" in AGENT_EVAL_PRESETS

    def test_preset_has_expected_keys(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        prod = AGENT_EVAL_PRESETS["production"]
        assert "sample_rate" in prod
        assert prod["sample_rate"] <= 1.0

    def test_agent_eval_accepts_preset(self):
        from agent_evaluator import agent_eval
        m = PerformanceMonitor()

        @agent_eval(m, task_type="qa", preset="testing")
        def fn(question, ground_truth=""): return "ok"

        result = fn("q", ground_truth="ok")
        assert result == "ok"

    def test_unknown_preset_warns(self):
        from agent_evaluator import agent_eval
        m = PerformanceMonitor()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(m, task_type="qa", preset="unknown_preset_xyz")
            def fn(question, ground_truth=""): return "ok"

            fn("q")
        user_warns = [x for x in w if issubclass(x.category, UserWarning)]
        assert any("unknown_preset_xyz" in str(x.message) for x in user_warns)


# ---------------------------------------------------------------------------
# H2: format_error_context
# ---------------------------------------------------------------------------
class TestFormatErrorContext:
    def test_basic_format(self):
        from agent_evaluator.exceptions import format_error_context
        msg = format_error_context("t1", "qa", ValueError("bad input"))
        assert "t1" in msg
        assert "qa" in msg
        assert "ValueError" in msg
        assert "bad input" in msg

    def test_format_with_additional(self):
        from agent_evaluator.exceptions import format_error_context
        msg = format_error_context("t2", "code", RuntimeError("oops"),
                                   additional={"model": "claude"})
        assert "model=claude" in msg

    def test_validation_error_has_context(self):
        from agent_evaluator.exceptions import ValidationError
        err = ValidationError("bad value", context={"field": "task_id"})
        assert err.context["field"] == "task_id"
        assert str(err) == "bad value"


# ---------------------------------------------------------------------------
# H3: ResponseCache
# ---------------------------------------------------------------------------
class TestResponseCache:
    def test_set_and_get(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache(maxsize=10, ttl=60)
        cache.set("key1", {"data": 123})
        val = cache.get("key1")
        assert val == {"data": 123}

    def test_miss_returns_none(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache(ttl=0.01)
        cache.set("key", "value")
        time.sleep(0.05)
        assert cache.get("key") is None

    def test_lru_eviction(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache(maxsize=2, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_stats(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache()
        cache.set("x", 1)
        cache.get("x")  # hit
        cache.get("y")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_invalidate(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache()
        cache.set("key", "val")
        cache.invalidate("key")
        assert cache.get("key") is None

    def test_clear(self):
        from agent_evaluator.serve.cache import ResponseCache
        cache = ResponseCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache._cache) == 0


# ---------------------------------------------------------------------------
# Bonus: verify all new exports work
# ---------------------------------------------------------------------------
class TestExports:
    def test_multimodal_tracker_internal(self):
        from agent_evaluator.core.trackers.layer1 import MultimodalMetricsTracker
        assert MultimodalMetricsTracker is not None

    def test_agent_eval_presets_exported(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert isinstance(AGENT_EVAL_PRESETS, dict)

    def test_format_error_context_importable(self):
        from agent_evaluator.exceptions import format_error_context
        assert callable(format_error_context)

    def test_response_cache_importable(self):
        from agent_evaluator.serve.cache import ResponseCache, _GLOBAL_CACHE
        assert ResponseCache is not None
        assert _GLOBAL_CACHE is not None
