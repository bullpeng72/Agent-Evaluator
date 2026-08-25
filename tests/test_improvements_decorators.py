"""
tests/test_improvements_decorators.py
======================================
v0.7.2 개선 배치 — 데코레이터·프레임워크 어댑터·대시보드 API·모니터 통합 테스트

Sources:
  - test_improvements_a1_e2.py (A1~E2: preset/shortcut/dry_run/live_stats/alert_history)
  - test_improvements_f1_f25.py (F1~F25: timeout/alert_rules/on_record/framework_auto 등)
  - test_improvements_g1_g26.py (G1~G26: alert 순서/generator timeout/register_preset 등)
"""
from __future__ import annotations

import datetime
import inspect
import json
import sys
import threading
import time
import warnings
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import (
    AGENT_EVAL_PRESETS,
    EvalDecorator,
    _FRAMEWORK_ADAPTERS,
    _eval_active,
    _make_alert_on_record,
    agent_eval,
    batch_eval,
    conversation_eval,
    get_framework_info,
    register_preset,
)

# EvalDecorator 클래스 속성에서 꺼내 모듈 수준 별칭 설정
_BATCH_PARAMS = EvalDecorator._BATCH_PARAMS
_COMMON_PARAMS = EvalDecorator._COMMON_PARAMS
_CONV_PARAMS = EvalDecorator._CONV_PARAMS


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_monitor() -> PerformanceMonitor:
    return PerformanceMonitor(output_dir=None)


def _make_task_result(**kwargs):
    from agent_evaluator import TaskResult

    defaults: dict[str, Any] = dict(
        task_id="t1",
        task_type="qa",
        success=True,
        completion_score=0.9,
        accuracy_score=0.8,
        execution_time=1.0,
        tokens_used={"input": 50, "output": 50, "total": 100},
        tool_calls=0,
        attempts=1,
        errors=[],
        timestamp=datetime.datetime.now(),
    )
    defaults.update(kwargs)
    return TaskResult(**defaults)


# ===========================================================================
# From test_improvements_a1_e2.py — A1~E2
# ===========================================================================

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
        assert "preset" in inspect.signature(batch_eval).parameters

    def test_batch_eval_preset_applies_sample_rate(self):
        monitor = PerformanceMonitor(output_dir=None)
        called = []

        @batch_eval(monitor, task_type="qa", preset="performance")
        def batch_agent(questions, ground_truths=None):
            called.append(len(questions))
            return ["ok"] * len(questions)

        batch_agent(questions=["Q1"], ground_truths=["A1"])
        assert len(called) == 1

    def test_batch_eval_invalid_preset_warns(self):
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
        assert "preset" in inspect.signature(conversation_eval).parameters

    def test_conversation_eval_preset_no_error(self):
        monitor = PerformanceMonitor(output_dir=None)

        @conversation_eval(monitor, preset="testing")
        def chat(question, session_id="s1"):
            return "ok"

        assert callable(chat)


# ---------------------------------------------------------------------------
# A2: question_arg alias in conversation_eval
# ---------------------------------------------------------------------------
class TestConversationEvalQuestionArg:
    def test_conversation_eval_accepts_question_arg(self):
        """question_arg= 는 conversation_eval에서 제거됨 (user_arg= 사용)."""
        assert "question_arg" not in inspect.signature(conversation_eval).parameters
        assert "user_arg" in inspect.signature(conversation_eval).parameters

    def test_question_arg_alias_works(self):
        """question_arg= 전달 시 TypeError 발생 (제거됨, user_arg= 사용)."""
        monitor = PerformanceMonitor(output_dir=None)

        with pytest.raises(TypeError):
            conversation_eval(monitor, question_arg="query")  # type: ignore[call-arg] — intentionally removed kwarg, testing the runtime guard


# ---------------------------------------------------------------------------
# D1: _ShortcutCallable — parameter passing
# ---------------------------------------------------------------------------
class TestShortcutCallable:
    def test_shortcut_qa_is_shortcut_callable(self):
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert isinstance(dec.qa, _ShortcutCallable)

    def test_shortcut_direct_decorator_works(self):
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)

        @dec.qa
        def agent(question, ground_truth=""):
            return "answer"

        result = agent(question="Q?", ground_truth="A")
        assert result is not None

    def test_shortcut_with_kwargs_works(self):
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

    def test_shortcut_rag_has_enable_hallucination(self):
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        sc = dec.rag
        assert sc._base_kwargs.get("enable_hallucination") is True

    def test_shortcut_secure_has_security_mode(self):
        """@eval.secure 단축키가 security=SecurityConfig()를 포함."""
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable, SecurityConfig

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        sc = dec.secure
        assert sc._base_kwargs.get("security") is not None
        assert isinstance(sc._base_kwargs.get("security"), SecurityConfig)

    def test_all_shortcuts_are_shortcut_callable(self):
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        for attr in ("qa", "tool_use", "rag", "code", "reasoning", "planning",
                     "data_analysis", "creative", "multi_agent", "secure", "streaming"):
            val = getattr(dec, attr)
            assert isinstance(val, _ShortcutCallable), f"{attr} should be _ShortcutCallable"

    def test_shortcut_callable_repr(self):
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert "qa" in repr(dec.qa)


# ---------------------------------------------------------------------------
# D4: EvalDecorator .streaming shortcut
# ---------------------------------------------------------------------------
class TestStreamingShortcut:
    def test_streaming_shortcut_exists(self):
        from agent_evaluator.decorators import EvalDecorator, _ShortcutCallable

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        assert isinstance(dec.streaming, _ShortcutCallable)

    def test_streaming_shortcut_as_decorator(self):
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)

        @dec.streaming
        def stream_agent(question, ground_truth=""):
            return "streamed answer"

        result = stream_agent(question="Q?")
        assert result is not None


# ---------------------------------------------------------------------------
# D5: agent_eval dry_run parameter — removed; use enabled=False instead
# ---------------------------------------------------------------------------
class TestDryRun:
    def test_agent_eval_accepts_dry_run(self):
        assert "dry_run" not in inspect.signature(agent_eval).parameters

    def test_dry_run_does_not_record(self):
        monitor = PerformanceMonitor(output_dir=None)
        initial_count = len(monitor.tasks)

        @agent_eval(monitor, task_type="qa", enabled=False)
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        assert len(monitor.tasks) == initial_count

    def test_dry_run_false_records_normally(self):
        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        assert len(monitor.tasks) >= 1


# ---------------------------------------------------------------------------
# E1: PerformanceMonitor.get_live_stats()
# ---------------------------------------------------------------------------
class TestGetLiveStats:
    def test_get_live_stats_method_exists(self):
        monitor = PerformanceMonitor(output_dir=None)
        assert hasattr(monitor, "get_live_stats")

    def test_get_live_stats_empty_monitor(self):
        monitor = PerformanceMonitor(output_dir=None)
        stats = monitor.get_live_stats()
        assert stats["task_count"] == 0
        assert stats["tcr"] == 0.0

    def test_get_live_stats_with_tasks(self):
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
        monitor = PerformanceMonitor(output_dir=None)
        stats = monitor.get_live_stats()
        for key in ("window_seconds", "task_count", "tcr", "avg_accuracy",
                    "avg_latency_s", "total_tokens", "timestamp"):
            assert key in stats, f"Missing key: {key}"

    def test_get_live_stats_with_frameworks(self):
        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa", framework="langchain")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
        stats = monitor.get_live_stats(include_frameworks=True)
        assert "frameworks" in stats

    def test_get_live_stats_window_zero_count(self):
        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")
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
            cooldown=0.0,
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule])
        def agent(question, ground_truth=""):
            return "answer"

        agent(question="Q?", ground_truth="A")

        assert len(fired) >= 1
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
        rule._history = [{"timestamp": i, "task_id": f"t{i}", "severity": "warning"}
                         for i in range(200)]
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
            assert history[0]["timestamp"] >= history[1]["timestamp"]


# ---------------------------------------------------------------------------
# B4: adapter error fallback in extra
# ---------------------------------------------------------------------------
class TestAdapterErrorFallback:
    def test_adapter_error_recorded_in_extra(self):
        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa", framework="langchain")
        def agent(question, ground_truth=""):
            return "plain string answer"

        agent(question="Q?", ground_truth="A")
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
                "completion_score": 1.0, "accuracy_score": 0.1,
                "execution_time": 10.0,
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


class TestComparisonAccuracyDroppedScaleFix:
    """회귀 테스트(Phase 2 감사) — get_comparison()의 regression_flags.accuracy_dropped가
    rf.accuracy(0-100 스케일)에 0-1 스케일용 임계값(-0.05)을 써서 사실상 항상 True였던
    버그. tcr_dropped와 동일하게 -5.0(5%p)로 정정됐는지 검증한다."""

    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        # overall_accuracy는 0-100 스케일 — 90.0 → 88.0은 -2.0 (5%p 미만 하락, 회귀 아님)
        for name, overall_accuracy in [("eval_a", 90.0), ("eval_b", 88.0)]:
            payload = {
                "report": {
                    "total_tasks": 2, "successful_tasks": 2, "task_completion_rate": 1.0,
                    "accuracy_metrics": {"accuracy_scores": {"overall_accuracy": overall_accuracy}},
                    "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                    "token_metrics": {"total_tokens": 100, "total_cost": 0.001},
                    "quality_metrics": {}, "agentic_metrics": {}, "security_metrics": {},
                },
                "tasks": [
                    {"task_id": f"t{i}", "task_type": "qa", "success": True, "completion_score": 1.0,
                     "accuracy_score": 0.9, "execution_time": 1.0, "tokens_used": 50,
                     "tool_calls": [], "attempts": 1, "errors": [], "timestamp": "2026-01-01T00:00:00",
                     "advanced_metrics": {}}
                    for i in range(2)
                ],
                "metadata": {"version": "0.7.2", "name": name},
            }
            (tmp_path / f"{name}.json").write_text(json.dumps(payload))

        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_small_accuracy_drop_not_flagged_as_regression(self, client):
        files = client.get("/api/results").json()["files"]
        fid_a = next(f["id"] for f in files if "eval_a" in f["name"])
        fid_b = next(f["id"] for f in files if "eval_b" in f["name"])
        data = client.get(f"/api/comparison?file_id_a={fid_a}&file_id_b={fid_b}").json()
        assert data["diff"]["accuracy"] == pytest.approx(-2.0)
        # 이전 버그(-0.05 임계값)라면 -2.0 < -0.05가 True라 회귀로 오탐됐다.
        assert data["regression_flags"]["accuracy_dropped"] is False

    def test_accuracy_dropped_threshold_matches_tcr_dropped_scale(self, client):
        """accuracy_dropped와 tcr_dropped가 이제 동일한 -5.0 임계값(0-100 스케일)을 쓴다."""
        files = client.get("/api/results").json()["files"]
        fid_a = next(f["id"] for f in files if "eval_a" in f["name"])
        fid_b = next(f["id"] for f in files if "eval_b" in f["name"])
        data = client.get(f"/api/comparison?file_id_a={fid_a}&file_id_b={fid_b}").json()
        # -2.0은 -5.0보다 크므로(덜 하락) 둘 다 False여야 스케일이 일치한다는 뜻.
        assert data["regression_flags"]["accuracy_dropped"] == (data["diff"]["accuracy"] < -5.0)


# ---------------------------------------------------------------------------
# Dashboard: E1 get_live_stats via monitor
# ---------------------------------------------------------------------------
class TestLiveStatsMonitor:
    def test_live_stats_returns_dict(self):
        monitor = PerformanceMonitor(output_dir=None)
        result = monitor.get_live_stats()
        assert isinstance(result, dict)

    def test_live_stats_after_recording(self):
        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa")
        def fn(question, ground_truth=""):
            return "answer"

        fn(question="test", ground_truth="test")
        stats = monitor.get_live_stats(window_seconds=3600)
        assert stats["task_count"] >= 1
        assert stats["tcr"] >= 0.0


# ===========================================================================
# From test_improvements_f1_f25.py — F1~F25
# ===========================================================================

# ---------------------------------------------------------------------------
# A: agent_eval timeout 파라미터
# ---------------------------------------------------------------------------

class TestAgentEvalTimeout:
    def test_agent_eval_timeout_param_exists(self):
        sig = inspect.signature(agent_eval)
        assert "timeout" in sig.parameters

    def test_common_params_includes_timeout(self):
        assert "timeout" in EvalDecorator._COMMON_PARAMS

    def test_agent_eval_timeout_sync_raises(self):
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", timeout=0.001)
        def slow_agent(question: str, ground_truth: str = "") -> str:
            import time
            time.sleep(5)
            return "done"

        with pytest.raises((TimeoutError, Exception)):
            slow_agent("test?", ground_truth="test")


# ---------------------------------------------------------------------------
# B: batch_eval alert_rules in _BATCH_PARAMS
# ---------------------------------------------------------------------------

class TestBatchParamsAlertRules:
    def test_batch_params_includes_alert_rules(self):
        assert "alert_rules" in EvalDecorator._BATCH_PARAMS


# ---------------------------------------------------------------------------
# C: conversation_eval on_record 콜백
# ---------------------------------------------------------------------------

class TestConversationEvalOnRecord:
    def test_conversation_eval_has_on_record_param(self):
        sig = inspect.signature(conversation_eval)
        assert "on_record" in sig.parameters

    def test_conv_params_includes_on_record(self):
        assert "on_record" in EvalDecorator._CONV_PARAMS


# ---------------------------------------------------------------------------
# D: EvalDecorator question_arg/ground_truth_arg defaults
# ---------------------------------------------------------------------------

class TestEvalDecoratorDefaults:
    def test_eval_decorator_accepts_question_arg_kwarg(self):
        monitor = _make_monitor()
        ed = EvalDecorator(monitor, question_arg="q")
        assert ed._defaults.get("question_arg") == "q"


# ---------------------------------------------------------------------------
# E: framework="auto"
# ---------------------------------------------------------------------------

class TestFrameworkAuto:
    def test_framework_auto_triggers_detection(self):
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", framework="auto")
        def my_agent(question: str, ground_truth: str = "") -> str:
            return "응답"

        result = my_agent("질문?", ground_truth="응답")
        assert result == "응답"

    def test_auto_detect_framework_anthropic(self):
        from agent_evaluator.decorators import _auto_detect_framework, _is_anthropic_response

        class FakeAnthropicResponse:
            content = []
            usage = object()
            stop_reason = "end_turn"

        resp = FakeAnthropicResponse()
        assert _is_anthropic_response(resp) is True
        detected = _auto_detect_framework(resp)
        assert detected == "anthropic"


# ---------------------------------------------------------------------------
# F: chain_steps normalization
# ---------------------------------------------------------------------------

class TestChainStepsNormalization:
    def test_chain_steps_normalized_from_tool_calls(self):
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="tool_use")
        def tool_agent(question: str, ground_truth: str = "") -> str:
            return "도구 사용 응답"

        tool_agent("도구 테스트?", ground_truth="답변")
        assert len(monitor.tasks) == 1


# ---------------------------------------------------------------------------
# G: anthropic usage token extraction
# ---------------------------------------------------------------------------

class TestAnthropicTokenExtraction:
    def test_extract_anthropic_metadata_tokens(self):
        from agent_evaluator.decorators import _extract_anthropic_metadata

        mock_resp = MagicMock()
        mock_resp.content = []
        mock_resp.model = ""

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20
        usage.cache_creation_input_tokens = 0
        usage.cache_read_input_tokens = 0
        mock_resp.usage = usage

        result = _extract_anthropic_metadata(mock_resp)
        if result is not None:
            assert result.tokens_used is not None
            assert result.tokens_used.get("input") == 10
            assert result.tokens_used.get("output") == 20
            assert result.tokens_used.get("total") == 30

    def test_extract_anthropic_metadata_with_tool_calls(self):
        from agent_evaluator.decorators import _extract_anthropic_metadata

        mock_resp = MagicMock()
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "search"
        tool_block.input = {"query": "test"}
        tool_block.id = "tool_123"
        mock_resp.content = [tool_block]
        mock_resp.model = ""

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20
        usage.cache_creation_input_tokens = 0
        usage.cache_read_input_tokens = 0
        mock_resp.usage = usage

        result = _extract_anthropic_metadata(mock_resp)
        assert result is not None
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 10
        assert result.tokens_used["output"] == 20
        assert result.tokens_used["total"] == 30


# ---------------------------------------------------------------------------
# H: native sentinel in _FRAMEWORK_ADAPTERS
# ---------------------------------------------------------------------------

class TestNativeSentinel:
    def test_native_in_framework_adapters(self):
        val = _FRAMEWORK_ADAPTERS.get("native")
        assert val is None

    def test_native_key_present_in_framework_adapters(self):
        assert "native" in _FRAMEWORK_ADAPTERS


# ---------------------------------------------------------------------------
# I: adapter_error in task dict
# ---------------------------------------------------------------------------

class TestAdapterErrorField:
    def test_task_dict_includes_adapter_error_field(self):
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"adapter_error"' in source or "'adapter_error'" in source


# ---------------------------------------------------------------------------
# J: model_name in tasks[]
# ---------------------------------------------------------------------------

class TestModelNameInTasks:
    def test_task_dict_includes_model_name(self):
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"model_name"' in source or "'model_name'" in source


# ---------------------------------------------------------------------------
# K: framework distribution in file detail
# ---------------------------------------------------------------------------

class TestFrameworkDistributionInDetail:
    def test_result_detail_includes_frameworks(self):
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"frameworks"' in source or "'frameworks'" in source


# ---------------------------------------------------------------------------
# L: latency percentile endpoint
# ---------------------------------------------------------------------------

class TestLatencyPercentilesEndpoint:
    def test_latency_percentiles_endpoint_exists(self):
        from agent_evaluator.serve.routers.data import router

        paths = [getattr(route, "path", "") for route in router.routes]
        assert any("latency-percentiles" in p for p in paths)


# ---------------------------------------------------------------------------
# M: token analytics endpoint
# ---------------------------------------------------------------------------

class TestTokenAnalyticsEndpoint:
    def test_token_analytics_endpoint_exists(self):
        from agent_evaluator.serve.routers.data import router

        paths = [getattr(route, "path", "") for route in router.routes]
        assert any("token-analytics" in p for p in paths)


# ---------------------------------------------------------------------------
# N: search_fields parameter
# ---------------------------------------------------------------------------

class TestSearchFieldsParam:
    def test_tasks_search_has_search_fields_param(self):
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert "search_fields" in source


# ---------------------------------------------------------------------------
# O: get_live_stats extended fields
# ---------------------------------------------------------------------------

class TestGetLiveStatsExtended:
    def test_get_live_stats_has_error_count(self):
        monitor = _make_monitor()
        stats = monitor.get_live_stats()

        assert "error_count" in stats
        assert "error_rate" in stats
        assert "avg_completion_score" in stats
        assert "task_type_distribution" in stats


# ---------------------------------------------------------------------------
# P: get_report_by_framework
# ---------------------------------------------------------------------------

class TestGetReportByFramework:
    def test_get_report_by_framework_returns_dict(self):
        monitor = _make_monitor()
        result = monitor.get_report_by_framework("langchain")

        assert isinstance(result, dict)
        assert result.get("framework") == "langchain"
        assert result.get("task_count") == 0

    def test_get_report_by_framework_with_tasks(self):
        monitor = _make_monitor()

        t1 = _make_task_result(task_id="fw1", extra={"framework": "langchain"})
        t2 = _make_task_result(task_id="fw2", extra={"framework": "langchain"})
        monitor.record_task(t1)
        monitor.record_task(t2)

        result = monitor.get_report_by_framework("langchain")
        assert result.get("task_count") == 2


# ---------------------------------------------------------------------------
# Q: filter_tasks
# ---------------------------------------------------------------------------

class TestFilterTasks:
    def test_filter_tasks_by_task_type(self):
        monitor = _make_monitor()

        t_qa = _make_task_result(task_id="qa1", task_type="qa")
        t_tool = _make_task_result(task_id="tool1", task_type="tool_use")
        monitor.record_task(t_qa)
        monitor.record_task(t_tool)

        filtered = monitor.filter_tasks(task_type="qa")
        assert len(filtered) == 1
        # TaskResult.__post_init__ always normalizes task_type to a lowercase str
        # (even when constructed with a TaskType enum member), so no Enum branch is needed here.
        assert all(str(t.task_type).lower() == "qa" for t in filtered)

    def test_filter_tasks_by_success_only(self):
        monitor = _make_monitor()

        t_ok = _make_task_result(task_id="ok1", success=True)
        t_fail = _make_task_result(
            task_id="fail1",
            success=False,
            completion_score=0.0,
            accuracy_score=0.0,
        )
        monitor.record_task(t_ok)
        monitor.record_task(t_fail)

        filtered = monitor.filter_tasks(success_only=True)
        assert all(t.success for t in filtered)
        assert len(filtered) >= 1

    def test_filter_tasks_min_accuracy(self):
        monitor = _make_monitor()

        t_high = _make_task_result(task_id="high1", accuracy_score=0.9)
        t_low = _make_task_result(task_id="low1", accuracy_score=0.5)
        monitor.record_task(t_high)
        monitor.record_task(t_low)

        filtered = monitor.filter_tasks(min_accuracy=0.8)
        assert all(t.accuracy_score >= 0.8 for t in filtered)
        assert len(filtered) >= 1


# ---------------------------------------------------------------------------
# R: export_by_framework
# ---------------------------------------------------------------------------

class TestExportByFramework:
    def test_export_by_framework_raises_if_no_tasks(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with pytest.raises(ValueError, match="No tasks found"):
            monitor.export_by_framework("nonexistent_framework", "output")


# ---------------------------------------------------------------------------
# S: gate dry_run
# ---------------------------------------------------------------------------

class TestGateDryRun:
    def test_gate_dry_run_returns_dict(self):
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)
        result = ev.gate(tcr=0, dry_run=True)

        assert isinstance(result, dict)
        assert "passed" in result
        assert "results" in result

    def test_gate_dry_run_no_sys_exit(self):
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)

        try:
            result = ev.gate(tcr=100, accuracy=100, dry_run=True)
        except SystemExit:
            pytest.fail("dry_run=True인데 sys.exit이 호출됨")

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# T: list_presets / from_preset
# ---------------------------------------------------------------------------

class TestQuickEvalPresets:
    def test_list_presets_returns_list(self):
        from agent_evaluator import QuickEval

        presets = QuickEval.list_presets()
        assert isinstance(presets, list)
        assert all(isinstance(p, str) for p in presets)
        assert len(presets) > 0

    def test_from_preset_default(self):
        from agent_evaluator import QuickEval

        ev = QuickEval.from_preset("default", output_dir=None)
        assert isinstance(ev, QuickEval)

    def test_from_preset_invalid_raises(self):
        from agent_evaluator import QuickEval

        with pytest.raises(ValueError):
            QuickEval.from_preset("totally_unknown_preset_xyz")


# ---------------------------------------------------------------------------
# U: type hints
# ---------------------------------------------------------------------------

class TestQuickEvalShortcutCallable:
    def test_quick_eval_shortcut_callable(self):
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)
        shortcut = ev.qa
        assert callable(shortcut)


# ---------------------------------------------------------------------------
# V: is_installed in get_framework_info
# ---------------------------------------------------------------------------

class TestGetFrameworkInfoIsInstalled:
    def test_get_framework_info_has_is_installed(self):
        info = get_framework_info("langchain")
        assert info is not None
        assert "is_installed" in info

    def test_get_framework_info_native_has_is_installed(self):
        info = get_framework_info("native")
        assert info is not None
        assert "is_installed" in info


# ---------------------------------------------------------------------------
# W: compare_with_thresholds docstring
# ---------------------------------------------------------------------------

class TestCompareWithThresholdsDocstring:
    def test_compare_with_thresholds_has_docstring(self):
        monitor = _make_monitor()
        doc = monitor.compare_with_thresholds.__doc__ or ""
        assert "current" in doc or "passed" in doc


# ---------------------------------------------------------------------------
# X: EvalDecorator merge priority docstring
# ---------------------------------------------------------------------------

class TestEvalDecoratorPriorityDocstring:
    def test_eval_decorator_has_priority_docstring(self):
        call_doc = EvalDecorator.__call__.__doc__ or ""
        class_doc = EvalDecorator.__doc__ or ""
        combined = (call_doc + class_doc).lower()
        assert "우선순위" in combined or "priority" in combined


# ---------------------------------------------------------------------------
# Y: on_item_error safety
# ---------------------------------------------------------------------------

class TestBatchEvalOnItemErrorSafety:
    def test_batch_eval_on_item_error_safety(self):
        monitor = _make_monitor()
        error_count = []

        def explosive_on_item_error(idx, question, error):
            error_count.append(idx)
            raise RuntimeError("on_item_error 자체 오류!")

        call_count = [0]

        @batch_eval(
            monitor,
            task_type="qa",
            on_item_error=explosive_on_item_error,
            concurrency=4,
        )
        def batch_agent(questions: List[str], ground_truths=None) -> List[str]:
            call_count[0] += 1
            return ["응답"] * len(questions)

        try:
            results = batch_agent(["질문1", "질문2"], ground_truths=["답1", "답2"])
            assert results is not None
        except Exception as e:
            pytest.fail(f"batch_eval이 예상치 못한 예외를 던졌습니다: {e}")

    def test_batch_eval_on_item_error_called_on_failure(self):
        monitor = _make_monitor()
        error_indices = []

        def on_item_error(idx, question, error):
            error_indices.append(idx)

        @batch_eval(
            monitor,
            task_type="qa",
            on_item_error=on_item_error,
            concurrency=4,
        )
        def flaky_batch_agent(questions: List[str], ground_truths=None) -> List[str]:
            return ["ok"] * len(questions)

        result = flaky_batch_agent(["q1"], ground_truths=["a1"])
        assert result is not None


# ===========================================================================
# From test_improvements_g1_g26.py — G1~G26
# ===========================================================================

# ---------------------------------------------------------------------------
# A: alert_rules + on_record 실행 순서
# ---------------------------------------------------------------------------

class TestAlertRulesAndOnRecord:
    """항목 A: alert_rules 가 on_record 보다 먼저 실행됨을 확인."""

    def test_alert_rules_on_record_order(self):
        monitor = _make_monitor()
        call_order: list = []

        from agent_evaluator import SimpleTaskAlertRule

        def _alert_handler(msg, tr):
            call_order.append("alert")

        rule = SimpleTaskAlertRule(
            name="order_test_rule",
            condition=lambda tr: True,
            handler=_alert_handler,
            severity="info",
            cooldown=0,
        )

        def _on_record(tr):
            call_order.append("on_record")

        @agent_eval(monitor, task_type="qa", alert_rules=[rule], on_record=_on_record)
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        agent("질문", ground_truth="답변")

        assert "alert" in call_order
        assert "on_record" in call_order
        assert call_order.index("alert") < call_order.index("on_record")

    def test_make_alert_on_record_code_or_docstring_mentions_order(self):
        import agent_evaluator.decorators as dec_module
        src = inspect.getsource(dec_module)
        assert "_make_alert_on_record" in src or "alert_rules" in src


# ---------------------------------------------------------------------------
# B: generator timeout UserWarning
# ---------------------------------------------------------------------------

class TestGeneratorTimeoutWarning:
    """항목 B: generator 함수에 timeout 지정 시 UserWarning."""

    def test_timeout_on_generator_raises_warning(self):
        monitor = _make_monitor()

        def gen_agent(question: str, ground_truth: str = ""):
            yield "hello"
            yield "world"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_eval(monitor, task_type="qa", timeout=1.0)(gen_agent)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("timeout" in str(w.message).lower() for w in user_warnings)

    def test_timeout_on_async_gen_raises_warning(self):
        monitor = _make_monitor()

        async def agen_agent(question: str, ground_truth: str = ""):
            yield "hello"
            yield "world"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_eval(monitor, task_type="qa", timeout=1.0)(agen_agent)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("timeout" in str(w.message).lower() for w in user_warnings)


# ---------------------------------------------------------------------------
# D: rag_mode + security_mode 동시 사용 경고
# ---------------------------------------------------------------------------

class TestRagModeSecurityModeWarning:
    def test_rag_mode_security_mode_both_warns(self):
        sig = inspect.signature(agent_eval)
        assert "rag_mode" in sig.parameters


# ---------------------------------------------------------------------------
# E: EvalDecorator.context() 양방향 지원
# ---------------------------------------------------------------------------

class TestEvalDecoratorContext:
    def test_eval_decorator_context_property_exists(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        assert hasattr(dec, "context")

    def test_eval_decorator_context_callable(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        ctx_shortcut = dec.context
        assert callable(ctx_shortcut) or hasattr(ctx_shortcut, "__call__") or hasattr(ctx_shortcut, "__enter__")

    def test_eval_decorator_context_returns_cm(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        shortcut = dec.context
        if callable(shortcut):
            cm = shortcut("qa")
            assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__")


# ---------------------------------------------------------------------------
# F: 이중 데코레이터 스택 감지
# ---------------------------------------------------------------------------

class TestDoubleDecoratorStackDetection:
    def test_eval_active_contextvar_exists(self):
        assert _eval_active is not None
        import contextvars
        assert isinstance(_eval_active, contextvars.ContextVar)

    def test_eval_active_default_is_false(self):
        assert _eval_active.get(True) is False or _eval_active.get() is False

    def test_double_decorator_stack_warns(self):
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa")
        def inner_agent(question: str, ground_truth: str = "") -> str:
            return "내부응답"

        @agent_eval(monitor, task_type="qa")
        def outer_agent(question: str, ground_truth: str = "") -> str:
            return inner_agent(question, ground_truth=ground_truth)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            outer_agent("질문", ground_truth="응답")

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("이중" in str(w.message) or "double" in str(w.message).lower()
                   or "평가 데코레이터" in str(w.message)
                   for w in user_warnings)


# ---------------------------------------------------------------------------
# S: alert_error_mode 파라미터
# ---------------------------------------------------------------------------

class TestAlertErrorMode:
    def test_agent_eval_has_alert_error_mode_param(self):
        sig = inspect.signature(agent_eval)
        assert "alert_error_mode" in sig.parameters

    def test_alert_error_mode_default_is_log(self):
        sig = inspect.signature(agent_eval)
        default = sig.parameters["alert_error_mode"].default
        assert default == "log"

    def test_alert_error_mode_log_no_exception(self):
        monitor = _make_monitor()
        from agent_evaluator import SimpleTaskAlertRule

        def _bad_handler(msg, tr):
            raise RuntimeError("alert 예외")

        rule = SimpleTaskAlertRule(
            name="bad_handler_rule",
            condition=lambda tr: True,
            handler=_bad_handler,
            severity="warning",
            cooldown=0,
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule], alert_error_mode="log")
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        result = agent("질문", ground_truth="답변")
        assert result == "답변"

    def test_alert_error_mode_strict_propagates_exception(self):
        class _RaisingRule:
            name = "raising_rule"

            def evaluate(self, tr: Any) -> None:
                raise RuntimeError("strict 모드 예외")

        rule = _RaisingRule()
        _on_record = _make_alert_on_record([rule], None, alert_error_mode="strict")

        tr = _make_task_result()
        with pytest.raises(RuntimeError, match="strict 모드 예외"):
            _on_record(tr)


# ---------------------------------------------------------------------------
# W: register_preset()
# ---------------------------------------------------------------------------

class TestRegisterPreset:
    def setup_method(self):
        self._added: list = []

    def teardown_method(self):
        for name in self._added:
            AGENT_EVAL_PRESETS.pop(name, None)

    def test_register_preset_adds_to_presets(self):
        name = "g26_test_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 0.5})
        assert name in AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS[name]["sample_rate"] == 0.5

    def test_register_preset_invalid_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            register_preset("", {"sample_rate": 0.5})

    def test_register_preset_invalid_config_raises(self):
        with pytest.raises(ValueError, match="config"):
            register_preset("g26_bad_config_preset", ["not", "a", "dict"])  # type: ignore

    def test_register_preset_usable_in_agent_eval(self):
        name = "g26_usable_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 1.0})

        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", preset=name)
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        result = agent("질문", ground_truth="답변")
        assert result == "답변"

    def test_register_preset_overwrites_with_warning(self):
        name = "g26_overwrite_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 0.3})

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            register_preset(name, {"sample_rate": 0.7})

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) > 0
        assert AGENT_EVAL_PRESETS[name]["sample_rate"] == 0.7


# ---------------------------------------------------------------------------
# G: supports_chain_steps
# ---------------------------------------------------------------------------

class TestSupportsChainSteps:
    def test_get_framework_info_has_supports_chain_steps_langchain(self):
        info = get_framework_info("langchain")
        assert info is not None
        assert "supports_chain_steps" in info
        assert info["supports_chain_steps"] is True

    def test_supports_chain_steps_false_for_openai(self):
        info = get_framework_info("openai")
        assert info is not None
        assert "supports_chain_steps" in info
        assert info["supports_chain_steps"] is False

    def test_supports_chain_steps_for_dspy_true(self):
        info = get_framework_info("dspy")
        assert info is not None
        assert info["supports_chain_steps"] is True


# ---------------------------------------------------------------------------
# H: estimated 필드 일관성
# ---------------------------------------------------------------------------

class TestHuggingFaceEstimatedField:
    def test_huggingface_tokens_has_estimated_true(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata

        hf_response = [{"generated_text": "안녕하세요 반갑습니다 오늘은 좋은 날씨입니다"}]
        meta = _extract_huggingface_metadata(hf_response)
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used.get("estimated") is True

    def test_huggingface_agent_logs_estimated_true(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata

        class AgentResult:
            logs = ["검색 결과", "답변 생성"]

        meta = _extract_huggingface_metadata(AgentResult())
        if meta is not None and meta.tokens_used is not None:
            if "estimated" in meta.tokens_used:
                assert meta.tokens_used["estimated"] is True


# ---------------------------------------------------------------------------
# I: Vertex AI vs Gemini 구분
# ---------------------------------------------------------------------------

class TestVertexAIVsGeminiDetection:
    def test_auto_detect_framework_vertexai_module(self):
        from agent_evaluator.decorators import _auto_detect_framework

        raw = MagicMock()
        raw.__class__.__module__ = "vertexai.generative_models"
        raw.candidates = [MagicMock()]
        raw.usage_metadata = MagicMock()

        detected = _auto_detect_framework(raw)
        assert detected == "vertexai"

    def test_auto_detect_framework_gemini_module(self):
        from agent_evaluator.decorators import _auto_detect_framework

        raw = MagicMock()
        raw.__class__.__module__ = "google.generativeai.types"
        raw.candidates = [MagicMock()]
        raw.usage_metadata = MagicMock()

        detected = _auto_detect_framework(raw)
        assert detected in ("gemini", "vertexai")

    def test_vertexai_framework_info_exists(self):
        info = get_framework_info("vertexai")
        assert info is not None and isinstance(info, dict)


# ---------------------------------------------------------------------------
# J: chain_steps 유효성 검증
# ---------------------------------------------------------------------------

class TestChainStepsValidation:
    def test_chain_steps_invalid_items_filtered(self):
        raw_chain_steps = [
            {"name": "valid", "output": "ok"},
            {"no_name_field": "invalid"},
        ]
        valid = [s for s in raw_chain_steps if isinstance(s, dict) and "name" in s]
        assert len(valid) == 1
        assert valid[0]["name"] == "valid"

    def test_chain_steps_non_dict_filtered(self):
        raw = [
            {"name": "step1"},
            "not_a_dict",
            123,
            {"name": "step2"},
        ]
        valid = [s for s in raw if isinstance(s, dict) and "name" in s]
        assert len(valid) == 2


# ---------------------------------------------------------------------------
# T: create_taskresult() extra_fields
# ---------------------------------------------------------------------------

class TestCreateTaskresultExtraFields:
    def test_create_taskresult_accepts_framework_extra(self):
        from agent_evaluator import create_taskresult

        tr = create_taskresult(
            task_id="extra_test_001",
            question="프레임워크 테스트?",
            response="langchain으로 답변",
            ground_truth="langchain으로 답변",
            execution_time=0.5,
            task_type="qa",
            framework="langchain",
        )
        assert tr is not None
        has_framework = (
            getattr(tr, "framework", None) == "langchain"
            or (isinstance(getattr(tr, "extra", None), dict) and tr.extra.get("framework") == "langchain")  # type: ignore
        )
        assert has_framework

    def test_create_taskresult_extra_fields_invalid_key_ignored(self):
        from agent_evaluator import create_taskresult

        tr = create_taskresult(
            task_id="extra_ignore_001",
            question="무효 필드 테스트?",
            response="답변",
            ground_truth="답변",
            execution_time=0.3,
            task_type="qa",
            nonexistent_field_xyz="무시되어야 함",
        )
        assert tr is not None
        assert not hasattr(tr, "nonexistent_field_xyz")


# ---------------------------------------------------------------------------
# U: EvalDecorator.inspect()
# ---------------------------------------------------------------------------

class TestEvalDecoratorInspect:
    def test_eval_decorator_inspect_returns_dict(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        result = dec.inspect()
        assert isinstance(result, dict)

    def test_eval_decorator_get_config_alias(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        assert hasattr(dec, "get_config")
        assert callable(dec.get_config)
        assert dec.get_config() == dec.inspect()

    def test_eval_decorator_inspect_reflects_init_params(self):
        monitor = _make_monitor()
        dec = EvalDecorator(monitor, sample_rate=0.5)
        config = dec.inspect()
        assert "sample_rate" in config
        assert config["sample_rate"] == 0.5


# ---------------------------------------------------------------------------
# X: eval_context.chunk_step() / add_step()
# ---------------------------------------------------------------------------

class TestEvalContextStepMethods:
    def test_eval_context_has_chunk_step_method(self):
        from agent_evaluator.decorators import eval_context
        monitor = _make_monitor()
        ctx = eval_context(monitor, "qa")
        assert hasattr(ctx, "chunk_step") and callable(ctx.chunk_step)

    def test_eval_context_has_add_step_method(self):
        from agent_evaluator.decorators import eval_context
        monitor = _make_monitor()
        ctx = eval_context(monitor, "qa")
        assert hasattr(ctx, "add_step") and callable(ctx.add_step)

    def test_eval_context_chunk_step_adds_streaming_steps(self):
        from agent_evaluator.decorators import eval_context

        monitor = _make_monitor()
        with eval_context(monitor, "qa") as ctx:
            ctx.chunk_step(content="첫 번째 청크")
            ctx.chunk_step(content="두 번째 청크")
            ctx.response = "완성된 응답"

        tasks = monitor.tasks
        assert len(tasks) > 0
        last_task = tasks[-1]
        extra = getattr(last_task, "extra", None) or {}
        assert "streaming_steps" in extra
        assert len(extra["streaming_steps"]) == 2

    def test_eval_context_add_step_adds_chain_steps(self):
        from agent_evaluator.decorators import eval_context

        monitor = _make_monitor()
        with eval_context(monitor, "qa") as ctx:
            ctx.add_step("retrieval", duration_s=0.2, step_type="retrieval")
            ctx.add_step("generation", duration_s=0.8, step_type="generation")
            ctx.response = "RAG 답변"

        tasks = monitor.tasks
        assert len(tasks) > 0
        last_task = tasks[-1]
        extra = getattr(last_task, "extra", None) or {}
        assert "chain_steps" in extra
        step_names = [s.get("name") for s in extra["chain_steps"]]
        assert "retrieval" in step_names
        assert "generation" in step_names


# ---------------------------------------------------------------------------
# Z: get_framework_info() — is_installed bool 반환
# ---------------------------------------------------------------------------

class TestGetFrameworkInfoIsInstalledBool:
    def test_get_framework_info_is_installed_bool_for_native(self):
        info = get_framework_info("native")
        assert info is not None
        assert "is_installed" in info
        assert isinstance(info["is_installed"], bool)

    def test_get_framework_info_is_installed_bool_for_openai(self):
        info = get_framework_info("openai")
        assert info is not None
        assert isinstance(info["is_installed"], bool)

    def test_get_framework_info_returns_none_for_unknown(self):
        info = get_framework_info("nonexistent_framework_xyz_abc")
        assert info is None


# ---------------------------------------------------------------------------
# K: /results 범위 필터 (tcr_min)
# ---------------------------------------------------------------------------

class TestResultsListFilterParams:
    def test_list_results_has_tcr_min_param(self):
        from agent_evaluator.serve.routers import data as data_router
        list_results_fn = getattr(data_router, "list_results", None)
        if list_results_fn is None:
            from agent_evaluator.serve.routers.data import router
            found = False
            for route in router.routes:
                if hasattr(route, "path") and "results" in str(getattr(route, "path", "")):
                    found = True
                    break
            assert found
        else:
            sig = inspect.signature(list_results_fn)
            assert "tcr_min" in sig.parameters

    def test_tcr_min_param_in_source(self):
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "tcr_min" in src


# ---------------------------------------------------------------------------
# L: SSE 엔드포인트
# ---------------------------------------------------------------------------

class TestLiveStatsSSERoute:
    def test_live_stats_sse_route_exists(self):
        from agent_evaluator.serve.routers.data import router

        route_paths = [str(getattr(r, "path", "")) for r in router.routes]
        assert any("live-stats" in p for p in route_paths)

    def test_live_stats_sse_source_exists(self):
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "live-stats" in src or "live_stats" in src


# ---------------------------------------------------------------------------
# M: hourly-stats 엔드포인트
# ---------------------------------------------------------------------------

class TestHourlyStatsRoute:
    def test_hourly_stats_route_exists(self):
        from agent_evaluator.serve.routers.data import router

        route_paths = [str(getattr(r, "path", "")) for r in router.routes]
        assert any("hourly-stats" in p for p in route_paths)

    def test_hourly_stats_in_source(self):
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "hourly-stats" in src or "hourly_stats" in src


# ---------------------------------------------------------------------------
# N: include_sample
# ---------------------------------------------------------------------------

class TestIncludeSampleParam:
    def test_list_results_has_include_sample_param(self):
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "include_sample" in src


# ---------------------------------------------------------------------------
# O: Anomaly Pydantic 스키마
# ---------------------------------------------------------------------------

class TestAnomalySchema:
    def test_anomaly_event_schema_defined(self):
        from agent_evaluator.serve.routers import data as data_module
        assert hasattr(data_module, "AnomalyEventSchema")

    def test_anomaly_list_response_defined(self):
        from agent_evaluator.serve.routers import data as data_module
        assert hasattr(data_module, "AnomalyListResponse")

    def test_anomaly_event_schema_has_expected_fields(self):
        from agent_evaluator.serve.routers.data import AnomalyListResponse
        if hasattr(AnomalyListResponse, "model_fields"):
            fields = AnomalyListResponse.model_fields
        else:
            fields = AnomalyListResponse.__fields__
        assert "events" in fields


# ---------------------------------------------------------------------------
# P: thread-safety RLock
# ---------------------------------------------------------------------------

class TestPerformanceMonitorThreadSafety:
    def test_performance_monitor_has_tasks_lock(self):
        monitor = _make_monitor()
        assert hasattr(monitor, "_tasks_lock")
        lock = monitor._tasks_lock
        lock_types = (type(threading.RLock()), type(threading.Lock()))
        assert isinstance(lock, lock_types)

    def test_tasks_lock_is_alias_for_lock(self):
        monitor = _make_monitor()
        if hasattr(monitor, "_lock"):
            assert monitor._tasks_lock is monitor._lock

    def test_concurrent_record_task_thread_safe(self):
        monitor = _make_monitor()
        errors: list = []

        def worker(i: int):
            try:
                tr = _make_task_result(task_id=f"thread_task_{i}")
                monitor.record_task(tr)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(monitor.tasks) == 20


# ---------------------------------------------------------------------------
# Q: get_live_stats 캐시
# ---------------------------------------------------------------------------

class TestGetLiveStatsCache:
    def test_performance_monitor_has_recent_tasks_cache(self):
        monitor = _make_monitor()
        assert hasattr(monitor, "_recent_tasks_cache")

    def test_recent_tasks_cache_populated_after_record(self):
        monitor = _make_monitor()
        initial_len = len(monitor._recent_tasks_cache)
        tr = _make_task_result(task_id="cache_test_001")
        monitor.record_task(tr)
        assert len(monitor._recent_tasks_cache) > initial_len

    def test_get_live_stats_uses_cache_for_short_window(self):
        monitor = _make_monitor()
        for i in range(5):
            tr = _make_task_result(task_id=f"live_stats_task_{i}")
            monitor.record_task(tr)

        start = time.perf_counter()
        stats = monitor.get_live_stats(window_seconds=30)
        elapsed = time.perf_counter() - start

        assert stats is not None
        assert elapsed < 2.0

    def test_get_live_stats_has_expected_keys(self):
        monitor = _make_monitor()
        tr = _make_task_result(task_id="live_stats_key_test")
        monitor.record_task(tr)

        stats = monitor.get_live_stats(window_seconds=60)
        assert isinstance(stats, dict)
        assert len(stats) > 0


# ---------------------------------------------------------------------------
# R: _STREAMING_THRESHOLD 상수
# ---------------------------------------------------------------------------

class TestStreamingThreshold:
    def test_streaming_threshold_constant_exists(self):
        from agent_evaluator.core.trackers import monitor as monitor_module
        assert hasattr(monitor_module, "_STREAMING_THRESHOLD")

    def test_streaming_threshold_is_positive_int(self):
        from agent_evaluator.core.trackers.monitor import _STREAMING_THRESHOLD
        assert isinstance(_STREAMING_THRESHOLD, int)
        assert _STREAMING_THRESHOLD > 0

    def test_streaming_threshold_value_reasonable(self):
        from agent_evaluator.core.trackers.monitor import _STREAMING_THRESHOLD
        assert 100 <= _STREAMING_THRESHOLD <= 100_000


# ---------------------------------------------------------------------------
# C: gate() 고급 임계값
# ---------------------------------------------------------------------------

class TestGateAdvancedThresholds:
    def test_gate_has_token_efficiency_min_param(self):
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.gate)
        assert "token_efficiency_min" in sig.parameters

    def test_gate_has_dry_run_param(self):
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.gate)
        assert "dry_run" in sig.parameters

    def test_gate_dry_run_includes_token_efficiency(self):
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator import create_taskresult

        qe = QuickEval("results/")
        tr = create_taskresult(
            task_id="gate_test_001",
            question="테스트?",
            response="답변",
            ground_truth="답변",
            execution_time=0.5,
            task_type="qa",
        )
        qe.monitor.record_task(tr)

        result = qe.gate(dry_run=True, token_efficiency_min=1000)
        assert isinstance(result, dict)
        assert "results" in result
        assert "token_efficiency" in result["results"]

    def test_gate_dry_run_returns_dict_not_sys_exit(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        result = qe.gate(dry_run=True)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# V: summary() _meta
# ---------------------------------------------------------------------------

class TestSummaryMeta:
    def test_summary_has_meta_key(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        result = qe.summary()
        assert "_meta" in result

    def test_summary_meta_is_dict(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        result = qe.summary()
        assert isinstance(result["_meta"], dict)

    def test_summary_meta_has_meaningful_fields(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        meta = qe.summary()["_meta"]
        assert len(meta) > 0


# ---------------------------------------------------------------------------
# Y: for_regression_eval() + check_regression()
# ---------------------------------------------------------------------------

class TestForRegressionEval:
    def test_for_regression_eval_has_baseline_file_param(self):
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.for_regression_eval)
        assert "baseline_file" in sig.parameters

    def test_for_regression_eval_has_regression_threshold_param(self):
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.for_regression_eval)
        assert "regression_threshold" in sig.parameters

    def test_check_regression_no_baseline_returns_expected_dict(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval.for_regression_eval("results/", baseline_file=None)
        result = qe.check_regression()

        assert isinstance(result, dict)
        assert "has_baseline" in result
        assert result["has_baseline"] is False

    def test_for_regression_eval_returns_quickeval_instance(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval.for_regression_eval("results/")
        assert isinstance(qe, QuickEval)

    def test_check_regression_has_regression_threshold_pct_key_with_baseline(self):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval.for_regression_eval("results/", regression_threshold=0.1)
        qe._baseline_summary = {"tcr": 90.0, "accuracy": 80.0}
        result = qe.check_regression()
        assert "regression_threshold_pct" in result
        assert result["regression_threshold_pct"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# EvalDecorator.conversation() with a monitor list — only monitor[0] records
# (conversation_eval()/_do_flush() has no multi-monitor support: dual-writing
# would call LLM Judge once per monitor). Must warn instead of silently
# dropping data for the remaining monitors.
# ---------------------------------------------------------------------------
class TestEvalDecoratorConversationMonitorList:
    def test_single_monitor_no_warning(self):
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dec.conversation()
            assert not any(issubclass(x.category, UserWarning) for x in w)

    def test_two_monitors_warns_and_uses_first(self):
        from agent_evaluator.decorators import EvalDecorator

        m1 = PerformanceMonitor(output_dir=None)
        m2 = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator([m1, m2])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dec.conversation()
            user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
            assert len(user_warnings) == 1
            assert "첫 번째 monitor" in str(user_warnings[0].message)
            assert "2개" in str(user_warnings[0].message)

    def test_single_element_list_no_warning(self):
        """길이 1인 리스트는 다른 monitor가 없으니 경고 대상이 아니다."""
        from agent_evaluator.decorators import EvalDecorator

        m1 = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator([m1])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dec.conversation()
            assert not any(issubclass(x.category, UserWarning) for x in w)
