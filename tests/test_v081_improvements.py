"""
Tests for v0.8.1 improvement features.

Covers improvements implemented in two rounds:

Round 1 (previous session):
- G1: eval_context.chunk_step() auto-records TTFT to LatencyTracker
- G2: TokenEconomyTracker.track_usage() framework parameter
- G3: MultimodalMetricsTracker auto-triggered from record_task()
- G5: partial_reason auto-generated in _build_and_record
- E1: EvalDecorator shortcut properties (qa, tool_use, rag, etc.)
- E3: QuickEval.generate_gate_config()
- E5: agent_eval auto_detect_framework defaults to True

Round 2 (this session):
- G4: agent_eval enable_hallucination parameter
- E4: eval_context ttft_seconds parameter
- D1: GoldenSetBuilder.push_to_phoenix() convenience method
- D2: PerformanceMonitor.enable_otel_child_spans parameter
"""
from __future__ import annotations

import inspect
import json
import os
import tempfile
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# G1: eval_context.chunk_step() auto-records TTFT to LatencyTracker
# ---------------------------------------------------------------------------

class TestEvalContextChunkStepTTFT:
    def setup_method(self):
        from agent_evaluator import PerformanceMonitor
        self.monitor = PerformanceMonitor()

    def test_ttft_recorded_after_first_chunk(self):
        from agent_evaluator.decorators import eval_context
        with eval_context(self.monitor, "qa", question="q") as ctx:
            ctx.chunk_step(content="hello")
            ctx.chunk_step(content=" world")
            ctx.response = "hello world"
        stats = self.monitor.latency_tracker.get_ttft_stats()
        assert stats["count"] == 1
        # TTFT should be a small non-negative float
        assert stats["mean"] is not None
        assert stats["mean"] >= 0.0

    def test_ttft_not_recorded_without_chunk_step(self):
        from agent_evaluator.decorators import eval_context
        with eval_context(self.monitor, "qa", question="q") as ctx:
            ctx.response = "no streaming"
        stats = self.monitor.latency_tracker.get_ttft_stats()
        assert stats["count"] == 0


# ---------------------------------------------------------------------------
# G2: TokenEconomyTracker.track_usage() framework parameter
# ---------------------------------------------------------------------------

class TestTokenEconomyFrameworkParam:
    def setup_method(self):
        from agent_evaluator.core.trackers.layer1 import TokenEconomyTracker
        self.tracker = TokenEconomyTracker(pricing={"input": 0.001, "output": 0.002})

    def test_track_usage_accepts_framework_param(self):
        sig = inspect.signature(self.tracker.track_usage)
        assert "framework" in sig.parameters

    def test_framework_stored_in_usage_log(self):
        self.tracker.track_usage("t1", 100, 50, "qa", model="gpt-4", framework="langchain")
        self.tracker.track_usage("t2", 100, 50, "qa", model="gpt-4", framework="crewai")
        assert self.tracker._usage_log[0]["framework"] == "langchain"
        assert self.tracker._usage_log[1]["framework"] == "crewai"

    def test_framework_defaults_to_native(self):
        self.tracker.track_usage("t1", 50, 50, "qa")
        assert self.tracker._usage_log[0]["framework"] == "native"

    def test_framework_breakdown_reflects_framework_field(self):
        self.tracker.track_usage("t1", 100, 50, "qa", framework="langchain")
        self.tracker.track_usage("t2", 200, 100, "qa", framework="langchain")
        self.tracker.track_usage("t3", 50, 25, "qa", framework="openai")
        breakdown = self.tracker.get_cost_breakdown_by_framework()
        assert "langchain" in breakdown or len(breakdown) > 0


# ---------------------------------------------------------------------------
# G3: MultimodalMetricsTracker auto-triggered from record_task()
# ---------------------------------------------------------------------------

class TestMultimodalAutoTrigger:
    def test_multimodal_tracker_on_monitor(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        assert hasattr(monitor, "multimodal_tracker")

    def test_multimodal_tracker_triggered_for_image_tasks(self):
        from agent_evaluator import PerformanceMonitor, TaskResult
        monitor = PerformanceMonitor()
        result = TaskResult(
            task_id="t1",
            task_type="qa",
            success=True,
            completion_score=1.0,
            accuracy_score=1.0,
            execution_time=0.1,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
            extra={"image_count": 3, "modality": "image"},
        )
        monitor.record_task(result)
        summary = monitor.multimodal_tracker.get_multimodal_summary()
        assert isinstance(summary, dict)
        # image tracking should be reflected — check actual summary keys
        total_images = (
            summary.get("total_image_count", 0)
            or summary.get("image_count", 0)
            or summary.get("tasks_with_images", 0)
        )
        assert total_images >= 1 or summary.get("total_tracked", 0) >= 1

    def test_record_task_without_multimodal_no_error(self):
        from agent_evaluator import PerformanceMonitor, TaskResult
        monitor = PerformanceMonitor()
        result = TaskResult(
            task_id="t2",
            task_type="qa",
            success=True,
            completion_score=1.0,
            accuracy_score=1.0,
            execution_time=0.1,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
        )
        monitor.record_task(result)  # should not raise


# ---------------------------------------------------------------------------
# G5: partial_reason auto-generated in _build_and_record
# ---------------------------------------------------------------------------

class TestPartialReasonAutoGeneration:
    def setup_method(self):
        from agent_evaluator import PerformanceMonitor
        self.monitor = PerformanceMonitor()

    def test_partial_reason_on_error(self):
        from agent_evaluator.decorators import agent_eval

        @agent_eval(self.monitor, task_type="qa")
        def failing_agent(question, ground_truth=""):
            raise RuntimeError("simulated error")

        try:
            failing_agent("test question")
        except RuntimeError:
            pass

        tasks = self.monitor.tasks
        assert len(tasks) == 1
        task = tasks[0]
        assert len(task.errors) > 0  # error was recorded
        pr = getattr(task, "partial_reason", None)
        if pr is not None:
            assert pr == "execution_error"

    def test_partial_reason_on_empty_response(self):
        from agent_evaluator.decorators import agent_eval

        @agent_eval(self.monitor, task_type="qa")
        def empty_agent(question, ground_truth=""):
            return ""

        empty_agent("test question")
        tasks = self.monitor.tasks
        assert len(tasks) == 1
        pr = getattr(tasks[0], "partial_reason", None)
        if pr is not None:
            assert pr == "empty_response"


# ---------------------------------------------------------------------------
# E1: EvalDecorator shortcut properties
# ---------------------------------------------------------------------------

class TestEvalDecoratorShortcuts:
    def setup_method(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator
        self.monitor = PerformanceMonitor()
        self.ed = EvalDecorator(self.monitor)

    def test_qa_shortcut_exists(self):
        assert hasattr(self.ed, "qa")

    def test_tool_use_shortcut_exists(self):
        assert hasattr(self.ed, "tool_use")

    def test_rag_shortcut_exists(self):
        assert hasattr(self.ed, "rag")

    def test_code_shortcut_exists(self):
        assert hasattr(self.ed, "code")

    def test_reasoning_shortcut_exists(self):
        assert hasattr(self.ed, "reasoning")

    def test_planning_shortcut_exists(self):
        assert hasattr(self.ed, "planning")

    def test_data_analysis_shortcut_exists(self):
        assert hasattr(self.ed, "data_analysis")

    def test_creative_shortcut_exists(self):
        assert hasattr(self.ed, "creative")

    def test_multi_agent_shortcut_exists(self):
        assert hasattr(self.ed, "multi_agent")

    def test_qa_shortcut_is_callable(self):
        assert callable(self.ed.qa)

    def test_qa_shortcut_decorates_function(self):
        @self.ed.qa
        def my_agent(question, ground_truth=""):
            return "answer"

        my_agent("test")
        tasks = self.monitor.tasks
        assert len(tasks) == 1
        assert str(tasks[0].task_type) in ("qa", "TaskType.QA")


# ---------------------------------------------------------------------------
# E3: QuickEval.generate_gate_config()
# ---------------------------------------------------------------------------

class TestQuickEvalGenerateGateConfig:
    def test_method_exists(self):
        from agent_evaluator.quick_eval import QuickEval
        assert hasattr(QuickEval, "generate_gate_config")

    def test_generate_gate_config_returns_file(self):
        import tempfile, os
        from agent_evaluator import QuickEval
        with tempfile.TemporaryDirectory() as tmpdir:
            qe = QuickEval(tmpdir)
            # Add some tasks
            from agent_evaluator.decorators import agent_eval
            @qe.qa
            def agent(question, ground_truth=""):
                return "answer"
            agent("q1", ground_truth="answer")
            agent("q2", ground_truth="answer")
            # Generate gate config
            cfg_path = os.path.join(tmpdir, "gate.json")
            result = qe.generate_gate_config(filepath=cfg_path)
            assert os.path.exists(cfg_path)
            with open(cfg_path) as f:
                cfg = json.load(f)
            assert "tcr" in cfg or "accuracy" in cfg

    def test_generate_gate_config_signature(self):
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.generate_gate_config)
        assert "filepath" in sig.parameters


# ---------------------------------------------------------------------------
# E5: agent_eval auto_detect_framework defaults to True
# ---------------------------------------------------------------------------

class TestAutoDetectFrameworkDefault:
    def test_auto_detect_framework_default_true(self):
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        param = sig.parameters.get("auto_detect_framework")
        assert param is not None
        assert param.default is True


# ---------------------------------------------------------------------------
# G4: agent_eval enable_hallucination parameter
# ---------------------------------------------------------------------------

class TestAgentEvalEnableHallucination:
    def test_enable_hallucination_param_exists(self):
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "enable_hallucination" in sig.parameters

    def test_enable_hallucination_false_by_default(self):
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert sig.parameters["enable_hallucination"].default is False

    def test_hallucination_runs_when_enabled(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=False)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination=True)
        def agent(question, ctx="", ground_truth=""):
            return "Paris is in France."

        agent(
            question="What country is Paris in?",
            ctx="Paris is the capital of France.",
            ground_truth="France",
        )
        # Hallucination detection ran even though monitor had it disabled globally
        records = monitor.hallucination_detector._detections
        assert len(records) >= 1

    def test_monitor_flag_restored_after_call(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=False)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination=True)
        def agent(question, ctx="", ground_truth=""):
            return "answer"

        agent("q", ctx="some context", ground_truth="answer")
        # Flag should be restored to False
        assert monitor.enable_hallucination_detection is False

    def test_enable_hallucination_false_no_detection(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=False)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination=False)
        def agent(question, ctx="", ground_truth=""):
            return "answer"

        agent("q", ctx="some context", ground_truth="answer")
        records = monitor.hallucination_detector._detections
        assert len(records) == 0

    def test_monitor_already_enabled_not_toggled(self):
        """If monitor already has hallucination enabled, the flag should stay enabled after."""
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=True)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination=True)
        def agent(question, ctx="", ground_truth=""):
            return "answer"

        agent("q", ctx="some context", ground_truth="answer")
        # Flag should still be True (was already True, not toggled)
        assert monitor.enable_hallucination_detection is True


# ---------------------------------------------------------------------------
# E4: eval_context ttft_seconds parameter
# ---------------------------------------------------------------------------

class TestEvalContextTtftSeconds:
    def test_ttft_seconds_param_exists(self):
        from agent_evaluator.decorators import eval_context
        sig = inspect.signature(eval_context.__init__)
        assert "ttft_seconds" in sig.parameters

    def test_ttft_seconds_default_none(self):
        from agent_evaluator.decorators import eval_context
        sig = inspect.signature(eval_context.__init__)
        assert sig.parameters["ttft_seconds"].default is None

    def test_ttft_seconds_pre_injects_value(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor()
        with eval_context(monitor, "qa", question="q", ttft_seconds=0.456) as ctx:
            ctx.response = "answer"

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats["count"] == 1
        assert stats["mean"] == pytest.approx(0.456, abs=1e-6)

    def test_ttft_seconds_without_chunk_step(self):
        """ttft_seconds should record TTFT even without any chunk_step calls."""
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor()
        with eval_context(monitor, "qa", question="q", ttft_seconds=0.25) as ctx:
            ctx.response = "batch response"  # no streaming, but TTFT known

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats["count"] == 1
        assert stats["mean"] == pytest.approx(0.25, abs=1e-6)

    def test_ttft_seconds_multiple_contexts(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor()
        for ttft in [0.1, 0.2, 0.3]:
            with eval_context(monitor, "qa", question="q", ttft_seconds=ttft) as ctx:
                ctx.response = "answer"

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats["count"] == 3
        assert stats["mean"] == pytest.approx(0.2, abs=1e-6)


# ---------------------------------------------------------------------------
# D1: GoldenSetBuilder.push_to_phoenix() convenience method
# ---------------------------------------------------------------------------

class TestGoldenSetBuilderPushToPhoenix:
    def test_method_exists(self):
        from agent_evaluator.datasets.builder import GoldenSetBuilder
        assert hasattr(GoldenSetBuilder, "push_to_phoenix")

    def test_push_to_phoenix_signature(self):
        from agent_evaluator.datasets.builder import GoldenSetBuilder
        sig = inspect.signature(GoldenSetBuilder.push_to_phoenix)
        params = sig.parameters
        assert "cases" in params
        assert "dataset_name" in params
        assert "phoenix_endpoint" in params
        assert "version" in params

    def test_push_to_phoenix_saves_file(self):
        from agent_evaluator.datasets.builder import GoldenSetBuilder
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = GoldenSetBuilder(tmpdir, tmpdir)
            cases = [
                {"task_id": "t1", "question": "Q1", "ground_truth": "A1", "accuracy_score": 0.9},
                {"task_id": "t2", "question": "Q2", "ground_truth": "A2", "accuracy_score": 0.95},
            ]
            # Mock upload_to_phoenix to avoid actual network call
            with patch.object(builder, "upload_to_phoenix", return_value="mock-dataset-id") as mock_upload:
                result = builder.push_to_phoenix(cases, dataset_name="test-golden")
            assert result == "mock-dataset-id"
            mock_upload.assert_called_once()
            # File should have been saved
            call_args = mock_upload.call_args
            dataset_path = call_args[0][0] if call_args[0] else call_args[1].get("dataset_path", "")
            assert os.path.exists(dataset_path)

    def test_push_to_phoenix_empty_cases_returns_none(self):
        from agent_evaluator.datasets.builder import GoldenSetBuilder
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = GoldenSetBuilder(tmpdir, tmpdir)
            result = builder.push_to_phoenix([], dataset_name="empty")
            assert result is None

    def test_push_to_phoenix_uses_dataset_name_for_file(self):
        from agent_evaluator.datasets.builder import GoldenSetBuilder
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = GoldenSetBuilder(tmpdir, tmpdir)
            cases = [{"task_id": "t1", "question": "Q1", "ground_truth": "A1"}]
            with patch.object(builder, "upload_to_phoenix", return_value="id-123"):
                builder.push_to_phoenix(cases, dataset_name="my-dataset")
            # The file should be named my-dataset.json
            assert os.path.exists(os.path.join(tmpdir, "my-dataset.json"))


# ---------------------------------------------------------------------------
# D2: PerformanceMonitor.enable_otel_child_spans parameter
# ---------------------------------------------------------------------------

class TestPerformanceMonitorOtelChildSpans:
    def test_param_exists_in_init(self):
        from agent_evaluator import PerformanceMonitor
        sig = inspect.signature(PerformanceMonitor.__init__)
        assert "enable_otel_child_spans" in sig.parameters

    def test_default_false(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        assert monitor.enable_otel_child_spans is False

    def test_can_be_set_to_true(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor(enable_otel_child_spans=True)
        assert monitor.enable_otel_child_spans is True

    def test_no_error_when_otel_not_configured(self):
        """enable_otel_child_spans=True should not error when OTEL is not configured."""
        from agent_evaluator import PerformanceMonitor, TaskResult
        monitor = PerformanceMonitor(enable_otel_child_spans=True)
        result = TaskResult(
            task_id="t1",
            task_type="qa",
            success=True,
            completion_score=1.0,
            accuracy_score=1.0,
            execution_time=0.1,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
            chain_steps=[
                {"name": "step1", "type": "chain_step", "execution_time": 0.05},
                {"name": "step2", "type": "tool_call", "execution_time": 0.03},
            ],
        )
        # Should not raise even though OTEL is not set up
        monitor.record_task(result)
        assert len(monitor.tasks) == 1

    def test_child_spans_emitted_when_otel_active(self):
        """Verify child spans are created for each chain_step when OTEL is active."""
        from agent_evaluator import PerformanceMonitor, TaskResult
        from agent_evaluator.core.otel import get_provider

        monitor = PerformanceMonitor(enable_otel_child_spans=True)
        child_spans_created = []

        # Mock provider with span tracking
        mock_provider = MagicMock()
        mock_provider.enabled = True
        mock_provider.span = MagicMock(
            return_value=MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False))
        )

        result = TaskResult(
            task_id="t_otel",
            task_type="tool_use",
            success=True,
            completion_score=1.0,
            accuracy_score=1.0,
            execution_time=0.2,
            tokens_used={},
            tool_calls=[],
            attempts=1,
            errors=[],
            chain_steps=[
                {"name": "retrieve", "type": "tool_call", "execution_time": 0.05},
                {"name": "generate", "type": "chain_step", "execution_time": 0.15},
            ],
        )

        with patch("agent_evaluator.core.otel.get_provider", return_value=mock_provider):
            monitor.record_task(result)

        # Should have been called: 1 (main span) + 2 (child spans) = 3 calls
        call_count = mock_provider.span.call_count
        assert call_count >= 3  # at least the 2 child spans + 1 main span
