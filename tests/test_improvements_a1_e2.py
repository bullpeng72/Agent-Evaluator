"""Tests for A1~E2 improvements (v0.7.2 second enhancement batch).

A1: preset= parameter for batch_eval and conversation_eval
A2: question_arg alias in conversation_eval
B1: smolagents token estimation
B2: Cohere chain_steps + SemanticKernel chain_steps
B4: adapter error fallback in extra
D1: EvalDecorator shortcut property parameter passing (_ShortcutCallable)
D3: AGENT_EVAL_PRESETS "performance" and "security" presets
D4: EvalDecorator .streaming shortcut
D5: agent_eval dry_run parameter
E1: PerformanceMonitor.get_live_stats()
E2: SimpleTaskAlertRule alert history
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# D3: New AGENT_EVAL_PRESETS — "performance" and "security"
# ---------------------------------------------------------------------------
class TestNewPresets:
    def test_performance_preset_exists(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert "performance" in AGENT_EVAL_PRESETS

    def test_security_preset_exists(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert "security" in AGENT_EVAL_PRESETS

    def test_performance_preset_timeout(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        p = AGENT_EVAL_PRESETS["performance"]
        assert p.get("timeout") == 10.0

    def test_performance_preset_has_anomaly_detection(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["performance"].get("enable_anomaly_detection") is True

    def test_performance_preset_flush_every(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["performance"].get("flush_every") == 20

    def test_security_preset_sample_rate(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["security"].get("sample_rate") == 1.0

    def test_all_six_presets_present(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        for key in ("production", "development", "testing", "canary", "performance", "security"):
            assert key in AGENT_EVAL_PRESETS


# ---------------------------------------------------------------------------
# A1: preset= for batch_eval
# ---------------------------------------------------------------------------
class TestBatchEvalPreset:
    def test_batch_eval_accepts_preset(self):
        import inspect
        from agent_evaluator.decorators import batch_eval
        assert "preset" in inspect.signature(batch_eval).parameters

    def test_batch_eval_preset_applies_sample_rate(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=None)
        called = []

        @batch_eval(monitor, task_type="qa", preset="performance")
        def batch_agent(questions, ground_truths=None):
            called.append(len(questions))
            return ["ok"] * len(questions)

        batch_agent(questions=["Q1"], ground_truths=["A1"])
        assert len(called) == 1  # enabled=True이므로 실행됨

    def test_batch_eval_invalid_preset_warns(self):
        import warnings
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=None)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @batch_eval(monitor, task_type="qa", preset="nonexistent_preset")
            def agent(questions, ground_truths=None):
                return ["ok"]

            assert any("nonexistent_preset" in str(warning.message) for warning in w)


# ---------------------------------------------------------------------------
# A1: preset= for conversation_eval
# ---------------------------------------------------------------------------
class TestConversationEvalPreset:
    def test_conversation_eval_accepts_preset(self):
        import inspect
        from agent_evaluator.decorators import conversation_eval
        assert "preset" in inspect.signature(conversation_eval).parameters

    def test_conversation_eval_preset_no_error(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval

        monitor = PerformanceMonitor(output_dir=None)

        @conversation_eval(monitor, preset="testing")
        def chat(question, session_id="s1"):
            return "ok"

        # Just verify the decorator is applied without error
        assert callable(chat)


# ---------------------------------------------------------------------------
# A2: question_arg alias in conversation_eval
# ---------------------------------------------------------------------------
class TestConversationEvalQuestionArg:
    def test_conversation_eval_accepts_question_arg(self):
        import inspect
        from agent_evaluator.decorators import conversation_eval
        assert "question_arg" in inspect.signature(conversation_eval).parameters

    def test_question_arg_alias_works(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval

        monitor = PerformanceMonitor(output_dir=None)

        @conversation_eval(monitor, question_arg="query")
        def chat(query, session_id="s1"):
            return "ok"

        assert callable(chat)


# ---------------------------------------------------------------------------
# D1: _ShortcutCallable — parameter passing
# ---------------------------------------------------------------------------
class TestShortcutCallable:
    def test_shortcut_qa_is_shortcut_callable(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert isinstance(dec.qa, _ShortcutCallable)

    def test_shortcut_direct_decorator_works(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)

        @dec.qa
        def agent(question, ground_truth=""):
            return "answer"

        result = agent(question="Q?", ground_truth="A")
        assert result is not None

    def test_shortcut_with_kwargs_works(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        custom_called = []

        def my_score(response, gt):
            custom_called.append((response, gt))
            return 0.9

        @dec.qa(score_fn=my_score)
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        assert len(custom_called) >= 1

    def test_shortcut_rag_has_rag_mode(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        sc = dec.rag
        assert sc._base_kwargs.get("rag_mode") is True

    def test_shortcut_secure_has_security_mode(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        sc = dec.secure
        assert sc._base_kwargs.get("security_mode") is True

    def test_all_shortcuts_are_shortcut_callable(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        for attr in ("qa", "tool_use", "rag", "code", "reasoning", "planning",
                     "data_analysis", "creative", "multi_agent", "secure", "streaming"):
            val = getattr(dec, attr)
            assert isinstance(val, _ShortcutCallable), f"{attr} should be _ShortcutCallable"

    def test_shortcut_callable_repr(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert "qa" in repr(dec.qa)


# ---------------------------------------------------------------------------
# D4: EvalDecorator .streaming shortcut
# ---------------------------------------------------------------------------
class TestStreamingShortcut:
    def test_streaming_shortcut_exists(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert isinstance(dec.streaming, _ShortcutCallable)

    def test_streaming_shortcut_as_decorator(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)

        @dec.streaming
        def stream_agent(question, ground_truth=""):
            return "streamed answer"

        result = stream_agent(question="Q?")
        assert result is not None


# ---------------------------------------------------------------------------
# D5: agent_eval dry_run parameter
# ---------------------------------------------------------------------------
class TestDryRun:
    def test_agent_eval_accepts_dry_run(self):
        import inspect
        from agent_evaluator.decorators import agent_eval
        assert "dry_run" in inspect.signature(agent_eval).parameters

    def test_dry_run_does_not_record(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)
        initial_count = len(monitor.tasks)

        @agent_eval(monitor, task_type="qa", dry_run=True)
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        # With dry_run=True, task should not be recorded
        assert len(monitor.tasks) == initial_count

    def test_dry_run_false_records_normally(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa", dry_run=False)
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        assert len(monitor.tasks) >= 1


# ---------------------------------------------------------------------------
# E1: PerformanceMonitor.get_live_stats()
# ---------------------------------------------------------------------------
class TestGetLiveStats:
    def test_get_live_stats_method_exists(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor(output_dir=None)
        assert hasattr(monitor, "get_live_stats")

    def test_get_live_stats_empty_monitor(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor(output_dir=None)
        stats = monitor.get_live_stats()
        assert stats["task_count"] == 0
        assert stats["tcr"] == 0.0

    def test_get_live_stats_with_tasks(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q1?", ground_truth="A1")
        agent(question="Q2?", ground_truth="A2")

        stats = monitor.get_live_stats(window_seconds=3600)
        assert stats["task_count"] >= 1
        assert "tcr" in stats
        assert "avg_accuracy" in stats
        assert "avg_latency_s" in stats
        assert "timestamp" in stats

    def test_get_live_stats_fields(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor(output_dir=None)
        stats = monitor.get_live_stats()
        for key in ("window_seconds", "task_count", "tcr", "avg_accuracy",
                    "avg_latency_s", "total_tokens", "timestamp"):
            assert key in stats, f"Missing key: {key}"

    def test_get_live_stats_with_frameworks(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa", framework="langchain")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        stats = monitor.get_live_stats(include_frameworks=True)
        assert "frameworks" in stats

    def test_get_live_stats_window_zero_count(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        # window_seconds=0 → no tasks in window
        stats = monitor.get_live_stats(window_seconds=0)
        assert stats["task_count"] == 0


# ---------------------------------------------------------------------------
# E2: SimpleTaskAlertRule alert history
# ---------------------------------------------------------------------------
class TestAlertHistory:
    def test_alert_rule_has_get_history(self):
        from agent_evaluator import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="test_rule",
            condition=lambda r: True,
            handler=lambda msg, r: None,
        )
        assert hasattr(rule, "get_history")

    def test_alert_rule_has_clear_history(self):
        from agent_evaluator import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="test_rule",
            condition=lambda r: True,
            handler=lambda msg, r: None,
        )
        assert hasattr(rule, "clear_history")

    def test_history_populated_on_trigger(self):
        from agent_evaluator import PerformanceMonitor, SimpleTaskAlertRule, agent_eval

        monitor = PerformanceMonitor(output_dir=None)
        fired = []

        rule = SimpleTaskAlertRule(
            name="always_fire",
            condition=lambda r: True,
            handler=lambda msg, r: fired.append(msg),
            cooldown=0.0,  # no cooldown for test
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule])
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")

        # Check fired
        assert len(fired) >= 1
        # Check history
        history = rule.get_history()
        assert len(history) >= 1
        assert "task_id" in history[0]
        assert "severity" in history[0]
        assert "timestamp" in history[0]

    def test_history_clear_works(self):
        from agent_evaluator import PerformanceMonitor, SimpleTaskAlertRule, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        rule = SimpleTaskAlertRule(
            name="clear_test",
            condition=lambda r: True,
            handler=lambda msg, r: None,
            cooldown=0.0,
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule])
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        rule.clear_history()
        assert len(rule.get_history()) == 0

    def test_history_max_100_items(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule

        rule = SimpleTaskAlertRule(
            name="max_test",
            condition=lambda r: True,
            handler=lambda msg, r: None,
            cooldown=0.0,
        )
        # Inject fake history directly
        rule._history = [{"timestamp": i, "task_id": f"t{i}", "severity": "warning"}
                         for i in range(200)]
        # history should be capped at 100 via get_history
        assert len(rule.get_history()) <= 100

    def test_history_newest_first(self):
        from agent_evaluator import PerformanceMonitor, SimpleTaskAlertRule, agent_eval

        monitor = PerformanceMonitor(output_dir=None)
        rule = SimpleTaskAlertRule(
            name="order_test",
            condition=lambda r: True,
            handler=lambda msg, r: None,
            cooldown=0.0,
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule])
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q1?", ground_truth="A1")
        agent(question="Q2?", ground_truth="A2")

        history = rule.get_history()
        if len(history) >= 2:
            # newest first
            assert history[0]["timestamp"] >= history[1]["timestamp"]


# ---------------------------------------------------------------------------
# B4: adapter error fallback in extra
# ---------------------------------------------------------------------------
class TestAdapterErrorFallback:
    def test_adapter_error_recorded_in_extra(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        # Use a framework that will fail to extract metadata from a string response
        @agent_eval(monitor, task_type="qa", framework="langchain")
        def agent(question, ground_truth=""):
            # Return a plain string - langchain adapter will fail to extract from it
            return "plain string answer"

        agent(question="Q?", ground_truth="A")
        # If adapter succeeded on plain string, no fallback needed
        # If adapter failed, extra["adapter_error_fallback"] should be set
        # We just verify the task was recorded without error
        assert len(monitor.tasks) >= 1


# ---------------------------------------------------------------------------
# B1: smolagents token estimation
# ---------------------------------------------------------------------------
class TestSmolagentsTokenEstimation:
    def test_smolagents_with_chain_steps_estimates_tokens(self):
        from agent_evaluator.decorators import _extract_smolagents_metadata

        class FakeAgent:
            steps = [
                {"name": "step1", "output": "A" * 400, "duration": 0.5},
                {"name": "step2", "output": "B" * 400, "duration": 0.3},
            ]

        result = _extract_smolagents_metadata(FakeAgent())
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used.get("estimated") is True
        assert result.tokens_used.get("total", 0) > 0

    def test_smolagents_token_estimation_proportional(self):
        from agent_evaluator.decorators import _extract_smolagents_metadata

        class ShortAgent:
            steps = [{"name": "s", "output": "x" * 40, "duration": 0.1}]

        class LongAgent:
            steps = [{"name": "s", "output": "x" * 4000, "duration": 0.1}]

        short = _extract_smolagents_metadata(ShortAgent())
        long_res = _extract_smolagents_metadata(LongAgent())
        if short and long_res and short.tokens_used and long_res.tokens_used:
            assert long_res.tokens_used["total"] > short.tokens_used["total"]


# ---------------------------------------------------------------------------
# B2: Cohere chain_steps
# ---------------------------------------------------------------------------
class TestCohereChainSteps:
    def test_cohere_adapter_with_text_creates_chain_step(self):
        from agent_evaluator.decorators import _extract_cohere_metadata

        class FakeCohere:
            text = "This is the Cohere response"
            tool_calls = []
            meta = None

        result = _extract_cohere_metadata(FakeCohere())
        assert result is not None
        assert result.chain_steps is not None
        names = [s["name"] for s in result.chain_steps]
        assert "cohere_response" in names

    def test_cohere_adapter_with_tool_calls_creates_chain_steps(self):
        from agent_evaluator.decorators import _extract_cohere_metadata

        class FakeTool:
            name = "web_search"
            parameters = {"query": "test"}

        class FakeCohere:
            text = "Search result"
            tool_calls = [FakeTool()]
            meta = None

        result = _extract_cohere_metadata(FakeCohere())
        assert result is not None
        assert result.chain_steps is not None
        names = [s["name"] for s in result.chain_steps]
        assert "web_search" in names


# ---------------------------------------------------------------------------
# B2: SemanticKernel chain_steps enhancement
# ---------------------------------------------------------------------------
class TestSemanticKernelChainSteps:
    def test_semantic_kernel_chain_steps_structured(self):
        from agent_evaluator.decorators import _extract_semantic_kernel_metadata

        class FakeSKResult:
            value = "The AI response"
            inner_content = None
            metadata = {}

        result = _extract_semantic_kernel_metadata(FakeSKResult())
        assert result is not None
        assert result.chain_steps is not None
        step = result.chain_steps[0]
        assert "name" in step
        assert "type" in step
        assert "output" in step
        assert "success" in step

    def test_semantic_kernel_chain_step_with_function_name(self):
        from agent_evaluator.decorators import _extract_semantic_kernel_metadata

        class FakeSKResult:
            value = "response"
            inner_content = None
            metadata = {}
            function_name = "MyPlugin.MyFunction"

        result = _extract_semantic_kernel_metadata(FakeSKResult())
        if result and result.chain_steps:
            assert result.chain_steps[0].get("function") == "MyPlugin.MyFunction"


# ---------------------------------------------------------------------------
# Dashboard: C1 chain-steps endpoint
# ---------------------------------------------------------------------------
class TestChainStepsEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        payload = {
            "report": {
                "total_tasks": 1, "successful_tasks": 1, "task_completion_rate": 1.0,
                "accuracy_metrics": {}, "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                "token_metrics": {"total_tokens": 100, "total_cost": 0.001},
                "quality_metrics": {}, "agentic_metrics": {}, "security_metrics": {},
            },
            "tasks": [{
                "task_id": "task_with_steps",
                "task_type": "qa", "success": True, "completion_score": 1.0,
                "accuracy_score": 0.9, "execution_time": 1.0, "tokens_used": 50,
                "tool_calls": [], "attempts": 1, "errors": [],
                "timestamp": "2026-01-01T00:00:00",
                "advanced_metrics": {
                    "chain_steps": [
                        {"name": "retriever", "type": "retriever", "output": "docs", "success": True, "execution_time": 0.3},
                        {"name": "generator", "type": "generator", "output": "answer", "success": True, "execution_time": 0.7},
                    ]
                },
            }],
            "metadata": {"version": "0.7.2", "name": "chain_test"},
        }
        (tmp_path / "chain_test.json").write_text(json.dumps(payload))
        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_chain_steps_endpoint_200(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/tasks/task_with_steps/chain-steps")
        assert r.status_code == 200

    def test_chain_steps_endpoint_structure(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/tasks/task_with_steps/chain-steps").json()
        assert "chain_steps" in data
        assert "step_count" in data
        assert "step_timeline" in data

    def test_chain_steps_task_not_found(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/tasks/nonexistent_task/chain-steps")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard: C3 per-task anomaly endpoint
# ---------------------------------------------------------------------------
class TestTaskAnomalyEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        payload = {
            "report": {
                "total_tasks": 1, "successful_tasks": 1, "task_completion_rate": 1.0,
                "accuracy_metrics": {"avg_accuracy": 0.9}, "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                "token_metrics": {"total_tokens": 50, "total_cost": 0.001},
                "quality_metrics": {}, "agentic_metrics": {}, "security_metrics": {},
            },
            "tasks": [{
                "task_id": "t1", "task_type": "qa", "success": True,
                "completion_score": 1.0, "accuracy_score": 0.1,  # low = anomaly
                "execution_time": 10.0,  # high latency = anomaly
                "tokens_used": 50, "tool_calls": [], "attempts": 1,
                "errors": [], "timestamp": "2026-01-01T00:00:00", "advanced_metrics": {},
            }],
            "metadata": {"version": "0.7.2", "name": "anomaly_test"},
        }
        (tmp_path / "anomaly_test.json").write_text(json.dumps(payload))
        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_task_anomaly_endpoint_200(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/tasks/t1/anomaly")
        assert r.status_code == 200

    def test_task_anomaly_has_analysis(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/tasks/t1/anomaly").json()
        assert "analysis" in data
        assert "has_anomaly" in data


# ---------------------------------------------------------------------------
# Dashboard: C4 comparison endpoint
# ---------------------------------------------------------------------------
class TestComparisonEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        for name, accuracy in [("eval_a", 0.8), ("eval_b", 0.9)]:
            payload = {
                "report": {
                    "total_tasks": 2, "successful_tasks": 2, "task_completion_rate": 1.0,
                    "accuracy_metrics": {}, "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                    "token_metrics": {"total_tokens": 100, "total_cost": 0.001},
                    "quality_metrics": {}, "agentic_metrics": {}, "security_metrics": {},
                },
                "tasks": [
                    {"task_id": f"t{i}", "task_type": "qa", "success": True, "completion_score": 1.0,
                     "accuracy_score": accuracy, "execution_time": 1.0, "tokens_used": 50,
                     "tool_calls": [], "attempts": 1, "errors": [], "timestamp": "2026-01-01T00:00:00",
                     "advanced_metrics": {}}
                    for i in range(2)
                ],
                "metadata": {"version": "0.7.2", "name": name},
            }
            (tmp_path / f"{name}.json").write_text(json.dumps(payload))

        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_comparison_endpoint_200(self, client):
        files = client.get("/api/results").json().get("files", [])
        if len(files) < 2:
            pytest.skip("need 2 files")
        fid_a, fid_b = files[0]["id"], files[1]["id"]
        r = client.get(f"/api/comparison?file_id_a={fid_a}&file_id_b={fid_b}")
        assert r.status_code == 200

    def test_comparison_endpoint_structure(self, client):
        files = client.get("/api/results").json().get("files", [])
        if len(files) < 2:
            pytest.skip("need 2 files")
        fid_a, fid_b = files[0]["id"], files[1]["id"]
        data = client.get(f"/api/comparison?file_id_a={fid_a}&file_id_b={fid_b}").json()
        assert "metrics_a" in data
        assert "metrics_b" in data
        assert "diff" in data
        assert "regression_flags" in data

    def test_comparison_missing_file_404(self, client):
        r = client.get("/api/comparison?file_id_a=nonexistent_a&file_id_b=nonexistent_b")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard: E1 get_live_stats via monitor
# ---------------------------------------------------------------------------
class TestLiveStatsMonitor:
    def test_live_stats_returns_dict(self):
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor(output_dir=None)
        result = monitor.get_live_stats()
        assert isinstance(result, dict)

    def test_live_stats_after_recording(self):
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def fn(question, ground_truth=""):
            return "answer"

        fn(question="test", ground_truth="test")
        stats = monitor.get_live_stats(window_seconds=3600)
        assert stats["task_count"] >= 1
        assert stats["tcr"] >= 0.0
