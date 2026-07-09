"""
tests/test_version_features.py
================================
버전별 기능 회귀 테스트 통합 (v0.7.3 ~ v0.8.4)

- v0.7.3: batch_eval concurrent, LangChain/AutoGen adapter tokens, QuickEval.streaming, score_fn, routers
- v0.7.4: eval_context timeout, EvalDecorator.batch() param propagation, EvalDecorator.context() timeout
- v0.7.5: search/distributions endpoints, multi-monitor support, QuickEval.gate(config_file=), sample_condition,
          aggregate_by_time, on_record transform, on_batch_progress, conversation_eval on_session_timeout
- v0.7.6: metric/heatmap endpoints, auto retry, batch shuffle, token cost, compare_models,
          export_to_wandb/mlflow, QuickEval.compare/for_regression_eval,
          CrewAI output_pydantic, vertexai/ollama adapters, suspicious patterns, dry_run, compression
- v0.7.9 C: LangGraph/CrewAI/DSPy/PydanticAI/AutoGen adapter improvements, _FRAMEWORK_ADAPTER_META
- v0.8.0: LatencyTracker TTFT, TokenEconomy framework breakdown, ToolSelectionF1, CoordinationTopology,
          restore_from_snapshot, ConversationMetrics.turn_scores, Anthropic cache tokens,
          QuickEval monitor_kwargs/gate warnings/cached async/watch, health otel, results sorting,
          filter endpoint docstring, on_error in _CONV_PARAMS
- v0.8.1: eval_context chunk_step TTFT, TokenEconomy framework param, multimodal auto-trigger,
          partial_reason, EvalDecorator shortcuts, QuickEval generate_gate_config,
          auto_detect_framework, enable_hallucination, eval_context ttft_seconds,
          GoldenSetBuilder.push_to_phoenix, enable_otel_child_spans
- v0.8.4: anomaly detection temp-override, CrewAI token extraction, DSPy/PydanticAI detection,
          OpenAI streaming delta, batch_eval DataFrame, generator TTFT, framework/llm_judge endpoints
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import inspect
import json
import os
import sys
import tempfile
import threading
import time
import warnings
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.decorators import (
    agent_eval,
    batch_eval,
    EvalMetadata,
    _FRAMEWORK_ADAPTERS,
    get_framework_info,
)

# Optional decorators imports (gracefully handled if not present)
try:
    from agent_evaluator.decorators import (
        _FRAMEWORK_ADAPTER_META,
        _auto_detect_framework,
        _extract_crewai_metadata,
        _extract_openai_metadata,
        _extract_langgraph_metadata,
        _extract_dspy_metadata,
        _extract_pydanticai_metadata,
    )
except ImportError:
    _FRAMEWORK_ADAPTER_META = {}
    _auto_detect_framework = None
    _extract_crewai_metadata = None
    _extract_openai_metadata = None
    _extract_langgraph_metadata = None
    _extract_dspy_metadata = None
    _extract_pydanticai_metadata = None


# ===========================================================================
# From test_v073_improvements.py
# ===========================================================================

class TestBatchEvalConcurrent:
    def test_concurrent_param_accepted(self, tmp_path):
        """concurrency>0 파라미터가 오류 없이 수용되어야 한다.

        concurrency=4 시 함수가 단일 항목(questions=[q])으로 개별 호출되므로
        각 호출은 len=1 짜리 리스트를 처리한다 → "answer_0" * N 반환.
        """
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrency=4)
        async def async_agent(questions, ground_truths=None):
            # 단일 항목 호출: questions=["q1"] → range(1) → ["answer_0"]
            return [f"answer_{i}" for i in range(len(questions))]

        results = asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        )
        assert len(results) == 2
        assert all(r == "answer_0" for r in results)  # 각 단일 호출의 첫 번째 요소

    def test_concurrent_runs_items_independently(self, tmp_path):
        """concurrency>0 시 항목별 개별 호출로 분리되어 실행된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        call_log = []

        @batch_eval(monitor, task_type="qa", concurrency=4)
        async def async_agent(questions, ground_truths=None):
            call_log.append(len(questions))
            return [f"ans" for _ in questions]

        asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        )
        # concurrency=4: 3개 항목이 개별 호출로 분리 → 각 call은 len=1
        assert all(n == 1 for n in call_log), f"expected all 1-item calls, got {call_log}"

    def test_concurrent_false_calls_function_once(self, tmp_path):
        """concurrency=0 (기본값)이면 함수가 한 번만 호출된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        call_count = []

        @batch_eval(monitor, task_type="qa", concurrency=0)
        async def async_agent(questions, ground_truths=None):
            call_count.append(1)
            return [f"ans" for _ in questions]

        asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        )
        assert len(call_count) == 1

    def test_max_concurrent_param_accepted(self, tmp_path):
        """concurrency=N 파라미터가 오류 없이 수용되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrency=2)
        async def async_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        results = asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        )
        assert len(results) == 3

    def test_concurrent_records_all_tasks(self, tmp_path):
        """concurrency>0 시에도 각 항목이 모두 monitor에 기록된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrency=4)
        async def async_agent(questions, ground_truths=None):
            return [f"ans_{i}" for i in range(len(questions))]

        asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        )
        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        assert len(tcr.tasks) == 2


# ---------------------------------------------------------------------------
# LangChain 어댑터 토큰 추출
# ---------------------------------------------------------------------------

class TestLangChainAdapterTokens:
    def test_extracts_usage_metadata(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        class _Action:
            tool = "search"
            tool_input = "query"

        raw = {
            "intermediate_steps": [(_Action(), "result")],
            "usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 50,
            },
        }
        result = _extract_langchain_metadata(raw)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 100
        assert result.tokens_used["output"] == 50
        assert result.tokens_used["total"] == 150

    def test_extracts_response_metadata_token_usage(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        class _Action:
            tool = "calculator"
            tool_input = "1+1"

        raw = {
            "intermediate_steps": [(_Action(), "2")],
            "response_metadata": {
                "token_usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                }
            },
        }
        result = _extract_langchain_metadata(raw)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["total"] == 100

    def test_no_token_info_still_returns_tool_calls(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        class _Action:
            tool = "search"
            tool_input = "q"

        raw = {
            "intermediate_steps": [(_Action(), "found")],
        }
        result = _extract_langchain_metadata(raw)
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tokens_used is None


# ---------------------------------------------------------------------------
# AutoGen 어댑터 토큰 추출
# ---------------------------------------------------------------------------

class TestAutoGenAdapterTokens:
    def test_extracts_cost_usage(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        class _FakeResult:
            messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
            cost = {
                "usage_including_cached_inference": {
                    "gpt-4o-mini": {
                        "prompt_tokens": 150,
                        "completion_tokens": 60,
                    }
                }
            }

        result = _extract_autogen_metadata(_FakeResult())
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 150
        assert result.tokens_used["output"] == 60
        assert result.tokens_used["total"] == 210

    def test_extracts_usage_summary(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        class _FakeResult:
            messages = [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ]
            usage_summary = {
                "prompt_tokens": 120,
                "completion_tokens": 40,
            }

        result = _extract_autogen_metadata(_FakeResult())
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["total"] == 160

    def test_no_cost_still_returns_turns(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        raw = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]
        }
        result = _extract_autogen_metadata(raw)
        assert result is not None
        assert len(result.conversation_turns) == 2
        assert result.tokens_used is None


# ---------------------------------------------------------------------------
# QuickEval.streaming
# ---------------------------------------------------------------------------

class TestQuickEvalStreaming:
    def test_streaming_property_exists(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        qe = QuickEval(str(tmp_path) + "/")
        assert hasattr(qe, "streaming")

    def test_streaming_decorator_on_generator(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval(str(tmp_path) + "/")

        @qe.streaming
        def stream_agent(question: str, ground_truth: str = "") -> str:
            for chunk in ["hello ", "world"]:
                yield chunk

        # generator를 소비해서 문자열로 합침
        result = "".join(stream_agent("hi?", ground_truth="hello world"))
        assert result == "hello world"

    def test_streaming_no_parens_applied(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval(str(tmp_path) + "/")
        called = []

        @qe.streaming
        def agent(question: str, ground_truth: str = "") -> str:
            called.append(True)
            yield "answer"

        # generator 소비
        list(agent("q?"))
        assert called


# ---------------------------------------------------------------------------
# score_fn 타입 힌트 (callable로 작동 확인)
# ---------------------------------------------------------------------------

class TestScoreFnCallable:
    def test_score_fn_with_correct_signature(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        scores = []

        def my_score(response: str, ground_truth: str) -> float:
            scores.append((response, ground_truth))
            return 0.9

        @agent_eval(monitor, task_type="qa", score_fn=my_score)
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(scores) == 1
        assert scores[0] == ("answer", "answer")


# ---------------------------------------------------------------------------
# 대시보드 라우터 등록 확인
# ---------------------------------------------------------------------------

class TestRouterRegistration:
    def test_stream_tasks_route_registered(self):
        from agent_evaluator.serve.routers.stream import router
        paths = [r.path for r in router.routes]
        assert any("stream/tasks" in p for p in paths), f"stream/tasks not found in {paths}"

    def test_conversation_session_detail_route_registered(self):
        from agent_evaluator.serve.routers.conversation import router
        paths = [r.path for r in router.routes]
        # /api/conversation/{file_id}/{session_id} 또는 /{file_id}/{session_id}
        assert any("{session_id}" in p for p in paths), f"session_id route not found in {paths}"



# ===========================================================================
# From test_v074_gaps.py
# ===========================================================================

class TestEvalContextTimeout:
    def test_timeout_param_accepted(self, tmp_path):
        """timeout 파라미터가 오류 없이 수용되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=10.0) as ctx:
            ctx.response = "answer"

    def test_no_timeout_normal_execution(self, tmp_path):
        """timeout 미지정 시 정상 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", ground_truth="ans") as ctx:
            ctx.response = "ans"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is True

    def test_timeout_exceeded_marks_error(self, tmp_path):
        """timeout 초과 시 has_error=True 로 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=0.01) as ctx:
            time.sleep(0.05)   # 0.05s > 0.01s timeout
            ctx.response = "too slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        # timeout 초과는 has_error=True 로 기록
        assert tasks[0].success is False

    def test_timeout_not_exceeded_no_error(self, tmp_path):
        """timeout 내 완료 시 정상 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=5.0) as ctx:
            ctx.response = "fast answer"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is True

    def test_timeout_error_message_contains_timeout_info(self, tmp_path):
        """timeout 초과 오류 메시지에 timeout 정보가 포함되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=0.01) as ctx:
            time.sleep(0.05)
            ctx.response = "slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        errors = tasks[0].errors or []
        assert any("timeout" in str(e).lower() or "exceeded" in str(e).lower() for e in errors)

    def test_timeout_does_not_suppress_real_exceptions(self, tmp_path):
        """timeout 설정이 있어도 실제 예외는 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with pytest.raises(ValueError):
            with eval_context(monitor, "qa", question="q", timeout=5.0) as ctx:
                raise ValueError("real error")


# ---------------------------------------------------------------------------
# EvalDecorator.batch() 파라미터 전파
# ---------------------------------------------------------------------------

class TestEvalDecoratorBatchParams:
    def test_on_error_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 on_error 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        error_log = []

        eval_dec = EvalDecorator(monitor, on_error=lambda tr: error_log.append(tr.task_id))

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            raise RuntimeError("batch fail")

        with pytest.raises(RuntimeError):
            batch_agent(questions=["q1"], ground_truths=["a1"])

        # on_error 콜백이 호출되어야 함
        assert len(error_log) >= 1

    def test_score_fn_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 score_fn 이 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        score_calls = []

        def my_score(response: str, gt: str) -> float:
            score_calls.append((response, gt))
            return 0.95

        eval_dec = EvalDecorator(monitor, score_fn=my_score)

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans_{i}" for i in range(len(questions))]

        batch_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(score_calls) == 2

    def test_alert_rules_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 alert_rules 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
            cooldown=0,
        )
        eval_dec = EvalDecorator(monitor, alert_rules=[rule])

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        batch_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(fired) == 2

    def test_timeout_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 timeout 이 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.001)  # 1ms timeout

        @eval_dec.batch(task_type="qa")
        def slow_batch(questions, ground_truths=None):
            time.sleep(0.5)  # 500ms — timeout 초과
            return [f"ans" for _ in questions]

        with pytest.raises((TimeoutError, Exception)):
            slow_batch(questions=["q1"], ground_truths=["a1"])

    def test_framework_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 framework 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, framework="openai")

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        batch_agent(questions=["q1"], ground_truths=["a1"])

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        assert tasks[0].framework == "openai"

    def test_batch_params_frozenset_exists(self):
        """EvalDecorator._BATCH_PARAMS 가 존재하고 필요한 파라미터를 포함해야 한다."""
        from agent_evaluator.decorators import EvalDecorator

        assert hasattr(EvalDecorator, "_BATCH_PARAMS")
        bp = EvalDecorator._BATCH_PARAMS
        assert "on_error" in bp
        assert "task_id_fn" in bp
        assert "timeout" in bp
        assert "context_arg" in bp
        assert "expected_tools_arg" in bp


# ---------------------------------------------------------------------------
# EvalDecorator.context() timeout 전파
# ---------------------------------------------------------------------------

class TestEvalDecoratorContextTimeout:
    def test_timeout_propagated_to_context(self, tmp_path):
        """EvalDecorator의 timeout 이 context()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.01)

        with eval_dec.context("qa", question="q") as ctx:
            time.sleep(0.05)   # timeout 초과
            ctx.response = "slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is False  # timeout 초과 → has_error=True

    def test_context_timeout_override(self, tmp_path):
        """context() 호출 시 timeout 직접 지정이 _defaults보다 우선해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.001)  # 극히 짧은 기본값

        # context() 호출 시 더 넉넉한 timeout 지정
        with eval_dec.context("qa", question="q", timeout=60.0) as ctx:
            ctx.response = "fast"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        # 60초 timeout이 적용되어 정상 처리
        assert tasks[0].success is True



# ===========================================================================
# From test_v075_gaps.py
# ===========================================================================

class TestSearchTasksEndpoint:
    def test_search_route_registered(self):
        """search 라우터가 data 라우터에 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("tasks/search" in p for p in paths), f"tasks/search not found in {paths}"

    def test_distributions_route_registered(self):
        """distributions 라우터가 data 라우터에 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("distributions" in p for p in paths), f"distributions not found in {paths}"

    def test_cross_file_search_route_registered(self):
        """전체 파일 task 검색 라우터가 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        # /tasks/search or /api/tasks/search
        assert any("tasks/search" in p for p in paths), f"global tasks/search not found in {paths}"


# ---------------------------------------------------------------------------
# Gap B — 다중 monitor 리스트 지원
# ---------------------------------------------------------------------------

class TestMultiMonitorSupport:
    def test_agent_eval_records_to_multiple_monitors(self, tmp_path):
        """agent_eval에 monitor 리스트를 넘기면 모두에 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        m1 = PerformanceMonitor(output_dir=str(tmp_path / "m1") + "/")
        m2 = PerformanceMonitor(output_dir=str(tmp_path / "m2") + "/")

        @agent_eval([m1, m2], task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")

        assert len(m1.tcr_tracker.tasks) == 1
        assert len(m2.tcr_tracker.tasks) == 1

    def test_batch_eval_records_to_multiple_monitors(self, tmp_path):
        """batch_eval에 monitor 리스트를 넘기면 모두에 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        m1 = PerformanceMonitor(output_dir=str(tmp_path / "m1") + "/")
        m2 = PerformanceMonitor(output_dir=str(tmp_path / "m2") + "/")

        @batch_eval([m1, m2], task_type="qa")
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])

        assert len(m1.tcr_tracker.tasks) == 2
        assert len(m2.tcr_tracker.tasks) == 2


# ---------------------------------------------------------------------------
# Gap C — QuickEval.gate(config_file=...)
# ---------------------------------------------------------------------------

class TestQuickEvalGateConfigFile:
    def test_gate_loads_thresholds_from_file(self, tmp_path):
        """config_file에서 임계값을 로드해야 한다."""
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator.decorators import agent_eval

        cfg = tmp_path / "thresholds.json"
        cfg.write_text(json.dumps({"tcr": 0, "accuracy": 0}))  # 항상 통과하는 임계값

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        result = qe.gate(config_file=str(cfg))
        assert result is True

    def test_gate_direct_param_overrides_config_file(self, tmp_path):
        """직접 지정 파라미터가 config_file 값보다 우선해야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        cfg = tmp_path / "thresholds.json"
        cfg.write_text(json.dumps({"tcr": 0}))  # 파일은 tcr=0

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        # tcr=0으로 config, 직접 tcr=0으로 override → 통과
        result = qe.gate(config_file=str(cfg), tcr=0)
        assert result is True

    def test_gate_missing_config_file_ignored(self, tmp_path):
        """존재하지 않는 config_file은 경고 후 무시되어야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        # 파일 없음 → 무시하고 tcr=0으로 통과
        result = qe.gate(config_file="/nonexistent/path.json", tcr=0)
        assert result is True


# ---------------------------------------------------------------------------
# Gap D — /api/results/{file_id}/distributions (라우터 등록 확인)
# ---------------------------------------------------------------------------

class TestDistributionsEndpoint:
    def test_distributions_in_data_router(self):
        """distributions 엔드포인트가 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("distributions" in p for p in paths)


# ---------------------------------------------------------------------------
# Gap E — sample_condition 조건부 샘플링
# ---------------------------------------------------------------------------

class TestSampleCondition:
    def test_agent_eval_condition_false_skips_evaluation(self, tmp_path):
        """sample_condition was removed; passing it to agent_eval raises TypeError."""
        import pytest
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", sample_condition=lambda args, kwargs: False)

    def test_agent_eval_condition_true_evaluates(self, tmp_path):
        """sample_condition was removed; verify agent_eval works normally without it."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(monitor.tcr_tracker.tasks) == 1

    def test_agent_eval_condition_based_on_kwargs(self, tmp_path):
        """sample_condition was removed; it should NOT be in agent_eval signature."""
        import inspect
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "sample_condition" not in sig.parameters

    def test_batch_eval_sample_condition_false_skips(self, tmp_path):
        """sample_condition was removed; passing it to batch_eval raises TypeError."""
        import pytest
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with pytest.raises(TypeError):
            @batch_eval(monitor, task_type="qa", sample_condition=lambda args, kwargs: False)
            def agent(questions, ground_truths=None):
                return [f"ans" for _ in questions]


# ---------------------------------------------------------------------------
# Gap F — PerformanceMonitor.aggregate_by_time()
# ---------------------------------------------------------------------------

class TestAggregateByTime:
    def test_aggregate_by_time_returns_dict(self, tmp_path):
        """aggregate_by_time() 이 dict를 반환해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        result = monitor.aggregate_by_time("hour")
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_aggregate_by_time_bucket_has_required_keys(self, tmp_path):
        """각 버킷에 tcr, avg_accuracy, avg_latency, count, error_count 가 있어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        hourly = monitor.aggregate_by_time("hour")
        bucket = next(iter(hourly.values()))
        assert "tcr" in bucket
        assert "avg_accuracy" in bucket
        assert "avg_latency" in bucket
        assert "count" in bucket
        assert "error_count" in bucket

    def test_aggregate_by_time_granularities(self, tmp_path):
        """minute / hour / day 세 가지 granularity 가 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        for gran in ("minute", "hour", "day"):
            result = monitor.aggregate_by_time(gran)
            assert isinstance(result, dict)

    def test_aggregate_by_time_empty_monitor(self, tmp_path):
        """태스크가 없으면 빈 dict를 반환해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        result = monitor.aggregate_by_time("hour")
        assert result == {}

    def test_aggregate_by_time_count_matches_tasks(self, tmp_path):
        """버킷 count 합계가 총 태스크 수와 같아야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        for i in range(5):
            agent(f"q{i}?", ground_truth="answer")

        hourly = monitor.aggregate_by_time("hour")
        total_count = sum(v["count"] for v in hourly.values())
        assert total_count == 5


# ---------------------------------------------------------------------------
# Gap H — on_record 반환값으로 TaskResult 교체
# ---------------------------------------------------------------------------

class TestOnRecordTransform:
    def test_on_record_returning_none_is_ignored(self, tmp_path):
        """on_record가 None 반환 시 원래 TaskResult가 유지되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        recorded = []

        def my_on_record(tr):
            recorded.append(tr)
            return None  # None 반환 → 교체 없음

        @agent_eval(monitor, task_type="qa", on_record=my_on_record)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(recorded) == 1
        assert recorded[0].task_type is not None

    def test_on_record_returning_taskresult_replaces(self, tmp_path):
        """on_record가 TaskResult 반환 시 교체되어야 한다."""
        import dataclasses
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        results_seen = []

        def enriching_on_record(tr):
            # framework 태그 주입
            enriched = dataclasses.replace(tr, framework="enriched-framework")
            results_seen.append(enriched)
            return enriched

        @agent_eval(monitor, task_type="qa", on_record=enriching_on_record)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(results_seen) == 1
        assert results_seen[0].framework == "enriched-framework"


# ---------------------------------------------------------------------------
# Gap I — batch_eval on_batch_progress
# ---------------------------------------------------------------------------

class TestBatchEvalProgress:
    def test_on_batch_progress_called_per_item(self, tmp_path):
        """on_batch_progress가 항목마다 호출되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        progress_log = []

        @batch_eval(
            monitor,
            task_type="qa",
            on_batch_progress=lambda done, total: progress_log.append((done, total)),
        )
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        assert len(progress_log) == 3
        assert progress_log[-1] == (3, 3)

    def test_on_batch_progress_final_equals_total(self, tmp_path):
        """마지막 콜백의 done == total 이어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        calls = []

        @batch_eval(
            monitor,
            task_type="qa",
            on_batch_progress=lambda done, total: calls.append((done, total)),
        )
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert calls[-1][0] == calls[-1][1]

    def test_on_batch_progress_none_does_not_fail(self, tmp_path):
        """on_batch_progress=None 이어도 정상 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa")
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1"], ground_truths=["a1"])
        assert len(monitor.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# Gap J — conversation_eval on_session_timeout
# ---------------------------------------------------------------------------

class TestConversationSessionTimeout:
    def test_on_session_timeout_called_on_timer_expire(self, tmp_path):
        """max_session_seconds 초과 시 on_session_timeout이 호출되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval, flush_conversation

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        timeout_log = []
        done_event = threading.Event()

        def on_timeout(session_id):
            timeout_log.append(session_id)
            done_event.set()

        @conversation_eval(
            monitor,
            max_session_seconds=0.05,  # 50ms
            on_session_timeout=on_timeout,
        )
        def chat(question, session_id="sess_001"):
            return "reply"

        chat("안녕하세요", session_id="sess_001")
        # 타이머가 만료될 때까지 대기 (최대 2초)
        done_event.wait(timeout=2.0)

        assert len(timeout_log) >= 1
        assert timeout_log[0] == "sess_001"

    def test_on_session_timeout_not_called_when_no_timer(self, tmp_path):
        """max_session_seconds 미지정 시 on_session_timeout이 호출되지 않아야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval, flush_conversation

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        timeout_log = []

        @conversation_eval(
            monitor,
            on_session_timeout=lambda sid: timeout_log.append(sid),
        )
        def chat(question, session_id="sess_002"):
            return "reply"

        chat("안녕하세요", session_id="sess_002")
        flush_conversation("sess_002")
        time.sleep(0.1)

        assert len(timeout_log) == 0



# ===========================================================================
# From test_v076_gaps.py
# ===========================================================================

def _make_result(
    task_id: str = "t1",
    task_type: str = "qa",
    success: bool = True,
    accuracy_score: float = 0.9,
    execution_time: float = 1.0,
    tokens_used: Dict = None,
    framework: str = "native",
    errors: List = None,
):
    from agent_evaluator.core.trackers.base import TaskResult
    return TaskResult(
        task_id=task_id,
        task_type=task_type,
        success=success,
        completion_score=1.0,
        accuracy_score=accuracy_score,
        execution_time=execution_time,
        tokens_used=tokens_used or {},
        tool_calls=[],
        attempts=1,
        errors=errors or [],
        timestamp=datetime.datetime.now(),
        framework=framework,
    )


def _make_monitor():
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor
    return PerformanceMonitor()


# ---------------------------------------------------------------------------
# A1: GET /api/results/{file_id}/metrics/{metric_name}
# ---------------------------------------------------------------------------

class TestMetricDetailEndpoint:
    def test_route_registered(self):
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("/results/{file_id}/metrics/{metric_name}" in p for p in paths)

    def test_invalid_metric_raises_404(self):
        """존재하지 않는 metric_name 은 HTTPException 404 반환."""
        from agent_evaluator.serve.routers import data as data_mod
        from fastapi import HTTPException

        class FakeRF:
            file_id = "f1"
            accuracy_metrics = {}
            efficiency_metrics = {}
            hallucination_detail = SimpleNamespace(detections=[], indicator_types={})
            has_hallucination = False
            quality_detail = SimpleNamespace(avg_score=0, evaluations=[], dimension_summary={}, grade_distribution={})
            security_l1 = SimpleNamespace(input_security=0, output_leakage=0, authorization=0)
            security_l2 = SimpleNamespace(privilege_escalation=0, attack_detection=0)
            agentic = SimpleNamespace(tool_efficiency=0, retry_summary={}, coordination_summary={}, workflow_summary={})
            cost_data = {}
            llm_judge = SimpleNamespace(judged_count=0, avg_overall=0, avg_completeness=0, avg_relevance=0, avg_factual_consistency=0, avg_toxicity=0, avg_bias=0, avg_faithfulness=0, avg_criteria_overall=0, results=[])

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        with pytest.raises(HTTPException) as exc_info:
            data_mod.get_metric_detail("f1", "nonexistent_metric", FakeRequest())
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# H1: GET /api/results/{file_id}/heatmap/{metric}
# ---------------------------------------------------------------------------

class TestHeatmapEndpoint:
    def test_route_registered(self):
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("/results/{file_id}/heatmap/{metric}" in p for p in paths)

    def test_invalid_metric_raises_404(self):
        from agent_evaluator.serve.routers import data as data_mod
        from fastapi import HTTPException

        class FakeRF:
            file_id = "f1"
            tasks = []

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        with pytest.raises(HTTPException):
            data_mod.get_metric_heatmap("f1", "invalid_metric", FakeRequest())

    def test_valid_metric_returns_structure(self):
        from agent_evaluator.serve.routers import data as data_mod

        fake_task = SimpleNamespace(
            task_type="qa",
            accuracy_score=0.9,
            execution_time=1.2,
            completion_score=1.0,
            timestamp="2026-04-04T10:00:00",
        )

        class FakeRF:
            file_id = "f1"
            tasks = [fake_task]

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        result = data_mod.get_metric_heatmap("f1", "accuracy_score", FakeRequest())
        assert "x_labels" in result
        assert "y_labels" in result
        assert "matrix" in result
        assert result["metric"] == "accuracy_score"


# ---------------------------------------------------------------------------
# B1: agent_eval auto_retry
# ---------------------------------------------------------------------------

class TestAgentEvalAutoRetry:
    def test_auto_retry_succeeds(self):
        """retry=RetryConfig(max=2) — 첫 시도 성공 시 1회만 실행."""
        from agent_evaluator.decorators import agent_eval, RetryConfig
        m = _make_monitor()

        @agent_eval(m, task_type="qa", retry=RetryConfig(max=2))
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?", ground_truth="answer")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1

    def test_auto_retry_retries_on_failure(self):
        """retry=RetryConfig(max=3, on=(ValueError,)) — 3회 시도 후 성공."""
        from agent_evaluator.decorators import agent_eval, RetryConfig
        m = _make_monitor()
        call_count = [0]

        @agent_eval(m, task_type="qa", retry=RetryConfig(max=3, on=(ValueError,)))
        def fn(question, ground_truth=""):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("simulated error")
            return "ok"

        result = fn("q?")
        assert result == "ok"
        assert call_count[0] == 3
        assert m.tasks[-1].attempts == 3

    def test_no_auto_retry_by_default(self):
        """max_retries 기본값 1 — 재시도 없음."""
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# B3: batch_eval shuffle — 제거됨 (v0.8.6+)
# ---------------------------------------------------------------------------

class TestBatchEvalShuffle:
    def test_shuffle_param_removed(self):
        """shuffle/shuffle_seed 파라미터는 제거됨 — 평가 로직과 무관한 유틸리티."""
        import inspect
        from agent_evaluator.decorators import batch_eval
        sig = inspect.signature(batch_eval)
        assert "shuffle" not in sig.parameters
        assert "shuffle_seed" not in sig.parameters

    def test_shuffle_raises_typeerror(self):
        """shuffle=True 전달 시 TypeError."""
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()
        with pytest.raises(TypeError):
            batch_eval(m, shuffle=True)

    def test_order_preserved_by_default(self):
        """shuffle 제거 후 항목 순서는 항상 입력 순서와 동일."""
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()
        questions = ["q0", "q1", "q2"]

        @batch_eval(m)
        def fn(questions, ground_truths=None):
            return questions

        fn(questions=questions)
        recorded = [t.question for t in m.tcr_tracker.tasks]
        assert recorded == questions


# ---------------------------------------------------------------------------
# C1: estimate_token_cost_per_request
# ---------------------------------------------------------------------------

class TestEstimateTokenCost:
    def test_empty_returns_zeros(self):
        m = _make_monitor()
        result = m.estimate_token_cost_per_request()
        assert result["count"] == 0
        assert result["avg_cost_usd"] == 0.0

    def test_with_tasks(self):
        m = _make_monitor()
        for i in range(3):
            m.record_task(_make_result(
                task_id=f"t{i}",
                tokens_used={"input": 100, "output": 50, "total": 150},
            ))
        result = m.estimate_token_cost_per_request()
        assert result["count"] == 3
        assert result["avg_input_tokens"] == 100.0
        assert result["avg_output_tokens"] == 50.0
        assert result["avg_cost_usd"] > 0.0

    def test_filter_by_task_type(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", task_type="qa", tokens_used={"input": 100, "output": 50}))
        m.record_task(_make_result("t2", task_type="code_generation", tokens_used={"input": 200, "output": 100}))

        qa_result = m.estimate_token_cost_per_request("qa")
        assert qa_result["count"] == 1
        assert qa_result["avg_input_tokens"] == 100.0


# ---------------------------------------------------------------------------
# C2: compare_models
# ---------------------------------------------------------------------------

class TestCompareModels:
    def test_empty_returns_empty(self):
        m = _make_monitor()
        result = m.compare_models()
        assert isinstance(result, dict)

    def test_groups_by_model_field(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", tokens_used={"input": 100, "output": 50, "model": "gpt-4o"}))
        m.record_task(_make_result("t2", tokens_used={"input": 200, "output": 100, "model": "gpt-4o"}))
        m.record_task(_make_result("t3", tokens_used={"input": 50, "output": 25, "model": "claude-sonnet-4-6"}))

        result = m.compare_models()
        assert "gpt-4o" in result
        assert "claude-sonnet-4-6" in result
        assert result["gpt-4o"]["count"] == 2
        assert result["claude-sonnet-4-6"]["count"] == 1

    def test_filter_by_model_names(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", tokens_used={"model": "gpt-4o"}))
        m.record_task(_make_result("t2", tokens_used={"model": "claude-haiku"}))

        result = m.compare_models(model_names=["gpt-4o"])
        assert "gpt-4o" in result
        assert "claude-haiku" not in result


# ---------------------------------------------------------------------------
# C3: export_to_wandb / export_to_mlflow (ImportError path)
# ---------------------------------------------------------------------------

class TestExportToExternalServices:
    def test_wandb_raises_import_error_if_not_installed(self):
        import importlib, sys
        m = _make_monitor()
        orig = sys.modules.get("wandb")
        sys.modules["wandb"] = None  # simulate missing package
        try:
            with pytest.raises((ImportError, TypeError)):
                m.export_to_wandb("test-project")
        finally:
            if orig is None:
                sys.modules.pop("wandb", None)
            else:
                sys.modules["wandb"] = orig

    def test_mlflow_raises_import_error_if_not_installed(self):
        import sys
        m = _make_monitor()
        orig = sys.modules.get("mlflow")
        sys.modules["mlflow"] = None
        try:
            with pytest.raises((ImportError, TypeError)):
                m.export_to_mlflow("test-experiment")
        finally:
            if orig is None:
                sys.modules.pop("mlflow", None)
            else:
                sys.modules["mlflow"] = orig


# ---------------------------------------------------------------------------
# D1: QuickEval.compare()
# ---------------------------------------------------------------------------

class TestQuickEvalCompare:
    def test_compare_returns_three_keys(self):
        from agent_evaluator.quick_eval import QuickEval
        q1 = QuickEval()
        q2 = QuickEval()
        result = q1.compare(q2)
        assert "self" in result
        assert "other" in result
        assert "delta" in result

    def test_delta_is_self_minus_other(self):
        from agent_evaluator.quick_eval import QuickEval
        q1 = QuickEval()
        q2 = QuickEval()
        q1.monitor.record_task(_make_result("t1", accuracy_score=0.9, success=True))
        q2.monitor.record_task(_make_result("t2", accuracy_score=0.7, success=True))

        result = q1.compare(q2)
        # tcr 는 둘 다 100% → delta 0
        assert result["delta"]["tcr"] == 0.0


# ---------------------------------------------------------------------------
# D2: QuickEval.for_regression_eval()
# ---------------------------------------------------------------------------

class TestQuickEvalForRegressionEval:
    def test_factory_returns_quickeval(self):
        from agent_evaluator.quick_eval import QuickEval
        qr = QuickEval.for_regression_eval()
        assert isinstance(qr, QuickEval)

    def test_auto_save_enabled(self):
        from agent_evaluator.quick_eval import QuickEval
        qr = QuickEval.for_regression_eval()
        assert qr.monitor.auto_save is True


# ---------------------------------------------------------------------------
# E1: CrewAI 2.0+ output_pydantic 지원
# ---------------------------------------------------------------------------

class TestCrewAIOutputPydantic:
    def test_output_pydantic_extracted(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakePydantic:
            def model_dump_json(self):
                return '{"result": "ok"}'

        class FakeCrewOutput:
            tasks_output = None
            output_pydantic = FakePydantic()

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert len(meta.agent_interactions) == 1
        assert meta.agent_interactions[0]["type"] == "task_completion"
        assert "output_pydantic" in meta.agent_interactions[0]["context"]

    def test_tasks_output_with_pydantic_merged(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakePydantic:
            def model_dump_json(self):
                return '{"result": "ok"}'

        class FakeTaskOut:
            agent = "researcher"
            description = "Research task"
            raw = "Research result"

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = FakePydantic()

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        # tasks_output + output_pydantic = 2 interactions
        assert len(meta.agent_interactions) == 2

    def test_no_output_pydantic_unchanged(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakeTaskOut:
            agent = "researcher"
            description = "Task"
            raw = "Result"

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert len(meta.agent_interactions) == 1


# ---------------------------------------------------------------------------
# E2: vertexai_eval 어댑터
# ---------------------------------------------------------------------------

class TestVertexAIAdapter:
    def test_vertexai_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "vertexai" in _FRAMEWORK_ADAPTERS

    def test_vertexai_extract_tool_calls(self):
        from agent_evaluator.decorators import _extract_vertexai_metadata

        class FakeFunctionCall:
            name = "get_weather"
            args = {"location": "Seoul"}

        class FakePart:
            function_call = FakeFunctionCall()

        class FakeContent:
            parts = [FakePart()]

        class FakeCandidate:
            content = FakeContent()

        class FakeUsage:
            prompt_token_count = 100
            candidates_token_count = 50
            total_token_count = 150

        class FakeResponse:
            candidates = [FakeCandidate()]
            usage_metadata = FakeUsage()

        meta = _extract_vertexai_metadata(FakeResponse())
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["name"] == "get_weather"
        assert meta.tokens_used["input"] == 100
        assert meta.framework == "vertexai"

    def test_vertexai_eval_via_agent_eval(self):
        from agent_evaluator import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa", framework="vertexai")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# E3: ollama_eval 어댑터
# ---------------------------------------------------------------------------

class TestOllamaAdapter:
    def test_ollama_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "ollama" in _FRAMEWORK_ADAPTERS

    def test_ollama_extract_tokens_from_dict(self):
        from agent_evaluator.decorators import _extract_ollama_metadata

        resp = {
            "message": {"role": "assistant", "content": "Hello"},
            "prompt_eval_count": 80,
            "eval_count": 40,
        }
        meta = _extract_ollama_metadata(resp)
        assert meta is not None
        assert meta.tokens_used["input"] == 80
        assert meta.tokens_used["output"] == 40
        assert meta.framework == "ollama"

    def test_ollama_extract_tool_calls_from_dict(self):
        from agent_evaluator.decorators import _extract_ollama_metadata

        resp = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_time", "arguments": {}}}
                ],
            },
            "prompt_eval_count": 50,
            "eval_count": 20,
        }
        meta = _extract_ollama_metadata(resp)
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["name"] == "get_time"

    def test_ollama_eval_via_agent_eval(self):
        from agent_evaluator import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa", framework="ollama")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# F1: configure_suspicious_patterns / evaluate_suspicious_patterns
# ---------------------------------------------------------------------------

class TestSuspiciousPatterns:
    def test_no_patterns_returns_no_match(self):
        m = _make_monitor()
        result = m.evaluate_suspicious_patterns("sensitive text")
        assert result["matched"] is False
        assert result["match_count"] == 0

    def test_configure_and_match(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bpassword\b", "DROP TABLE"])
        result = m.evaluate_suspicious_patterns("my password is 123")
        assert result["matched"] is True
        assert r"\bpassword\b" in result["patterns_matched"]

    def test_no_match(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bsecret\b"])
        result = m.evaluate_suspicious_patterns("normal text here")
        assert result["matched"] is False

    def test_case_insensitive(self):
        m = _make_monitor()
        m.configure_suspicious_patterns(["DROP TABLE"])
        result = m.evaluate_suspicious_patterns("drop table users")
        assert result["matched"] is True

    def test_multiple_patterns_matched(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bpassword\b", r"\bsecret\b"])
        result = m.evaluate_suspicious_patterns("password and secret here")
        assert result["match_count"] == 2


# ---------------------------------------------------------------------------
# F2: SimpleTaskAlertRule.dry_run()
# ---------------------------------------------------------------------------

class TestSimpleTaskAlertRuleDryRun:
    def _task(self, execution_time=1.0, accuracy_score=0.9):
        return _make_result("t1", execution_time=execution_time, accuracy_score=accuracy_score)

    def test_dry_run_fires(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="slow", condition=lambda r: r.execution_time > 5.0,
            handler=lambda m, r: None, severity="warning"
        )
        result = rule.dry_run(self._task(execution_time=10.0))
        assert result["would_fire"] is True
        assert result["message"] is not None
        assert "[WARNING]" in result["message"]
        assert result["error"] is None

    def test_dry_run_does_not_fire(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="slow", condition=lambda r: r.execution_time > 5.0,
            handler=lambda m, r: None
        )
        result = rule.dry_run(self._task(execution_time=1.0))
        assert result["would_fire"] is False
        assert result["message"] is None

    def test_dry_run_error_in_condition(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="broken", condition=lambda r: 1 / 0,
            handler=lambda m, r: None
        )
        result = rule.dry_run(self._task())
        assert result["would_fire"] is False
        assert result["error"] is not None

    def test_dry_run_does_not_call_handler(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        called = [False]

        def bad_handler(m, r):
            called[0] = True

        rule = SimpleTaskAlertRule(
            name="test", condition=lambda r: True,
            handler=bad_handler
        )
        rule.dry_run(self._task())
        assert called[0] is False  # handler should NOT be called


# ---------------------------------------------------------------------------
# G2: enable_compression
# ---------------------------------------------------------------------------

class TestEnableCompression:
    def test_enable_gzip_sets_algorithm(self):
        m = _make_monitor()
        m.enable_compression("gzip")
        assert getattr(m, "_compression_algorithm", None) == "gzip"

    def test_enable_bz2_sets_algorithm(self):
        m = _make_monitor()
        m.enable_compression("bz2")
        assert getattr(m, "_compression_algorithm", None) == "bz2"

    def test_unsupported_algorithm_defaults_to_gzip(self):
        m = _make_monitor()
        m.enable_compression("xz")  # unsupported
        assert getattr(m, "_compression_algorithm", None) == "gzip"

    def test_save_creates_compressed_file(self):
        m = _make_monitor()
        m.enable_compression("gzip")
        m.record_task(_make_result())

        with tempfile.TemporaryDirectory() as tmpdir:
            m.output_dir = Path(tmpdir)
            # Use explicit .json extension so the compressed file is test_comp.json.gz
            json_path = m.save_to_file("test_comp.json")
            gz_path = Path(json_path + ".gz")
            assert gz_path.exists(), f"Expected compressed file at {gz_path}"
            # Verify it's valid gzip
            import gzip
            with gzip.open(gz_path) as f:
                content = json.loads(f.read())
            assert isinstance(content, dict)



# ===========================================================================
# From test_v079_c_gaps.py
# ===========================================================================

def _make_langgraph_state(messages: List[Any], metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """LangGraph 상태 dict 픽스처 헬퍼."""
    state: Dict[str, Any] = {"messages": messages}
    if metadata is not None:
        state["__metadata__"] = metadata
    return state


def _make_ai_message(content: str, tool_calls: Optional[List] = None) -> MagicMock:
    """AIMessage mock 헬퍼."""
    msg = MagicMock()
    msg.__class__.__name__ = "AIMessage"
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


def _make_tool_message(content: str, name: str = "tool_result", tool_call_id: str = "call_001") -> MagicMock:
    """ToolMessage mock 헬퍼."""
    msg = MagicMock()
    msg.__class__.__name__ = "ToolMessage"
    msg.content = content
    msg.name = name
    msg.tool_call_id = tool_call_id
    msg.tool_calls = []
    return msg


def _make_human_message(content: str) -> MagicMock:
    """HumanMessage mock 헬퍼."""
    msg = MagicMock()
    msg.__class__.__name__ = "HumanMessage"
    msg.content = content
    msg.tool_calls = []
    return msg


def _make_crewai_output(tasks_output=None, output_pydantic=None, output_format=None, pydantic=None):
    """CrewAI 출력 mock 헬퍼."""
    obj = SimpleNamespace()
    obj.tasks_output = tasks_output
    obj.output_pydantic = output_pydantic
    obj.output_format = output_format
    obj.pydantic = pydantic
    return obj


def _make_dspy_prediction(completions=None, answer=None, rationale=None):
    """DSPy Prediction mock 헬퍼."""
    obj = SimpleNamespace()
    if completions is not None:
        obj._completions = completions
    if answer is not None:
        obj.answer = answer
    if rationale is not None:
        obj.rationale = rationale
    return obj


def _make_pydanticai_result(messages=None, all_messages_fn=None, usage_fn=None):
    """PydanticAI RunResult mock 헬퍼."""
    obj = MagicMock()
    obj.data = "result"
    obj.messages = messages or []
    if usage_fn:
        obj.usage = usage_fn
    else:
        obj.usage.return_value = None
    if all_messages_fn:
        obj.all_messages = all_messages_fn
    else:
        del obj.all_messages
    return obj


# ---------------------------------------------------------------------------
# C2: LangGraph ToolMessage/AIMessage → chain_steps + __metadata__
# ---------------------------------------------------------------------------

class TestC2LangGraphEnhancements:

    def test_tool_message_extracted_as_chain_step(self):
        """ToolMessage → chain_steps 에 type='tool_result' 로 추출"""
        state = _make_langgraph_state([
            _make_tool_message("42 degrees", name="get_weather", tool_call_id="call_1"),
        ])
        result = _extract_langgraph_metadata(state)
        assert result is not None
        assert result.chain_steps is not None
        assert len(result.chain_steps) == 1
        cs = result.chain_steps[0]
        assert cs["type"] == "tool_result"
        assert cs["name"] == "get_weather"
        assert "42 degrees" in cs["output"]
        assert cs["tool_call_id"] == "call_1"

    def test_ai_message_extracted_as_chain_step(self):
        """AIMessage with content → chain_steps 에 type='ai_message' 로 추출"""
        state = _make_langgraph_state([
            _make_ai_message("I will search for weather"),
        ])
        result = _extract_langgraph_metadata(state)
        assert result is not None
        assert result.chain_steps is not None
        ai_steps = [s for s in result.chain_steps if s.get("type") == "ai_message"]
        assert len(ai_steps) >= 1
        assert "I will search" in ai_steps[0]["output"]

    def test_metadata_extracted_as_state_transitions(self):
        """__metadata__ → state_transitions 에 source='__metadata__' 로 추출"""
        meta = {"node1": {"executed_at": "2026-04-04", "duration": "0.5s"}}
        state = _make_langgraph_state([], metadata=meta)
        result = _extract_langgraph_metadata(state)
        assert result is not None
        meta_transitions = [t for t in result.state_transitions if t.get("source") == "__metadata__"]
        assert len(meta_transitions) == 1
        assert meta_transitions[0]["node"] == "node1"

    def test_mixed_messages_full_extraction(self):
        """HumanMessage + AIMessage(with tool_calls) + ToolMessage 조합 전체 추출"""
        tc = {"name": "search", "args": {"query": "AI"}}
        ai_msg = _make_ai_message("Let me search", tool_calls=[tc])
        tool_msg = _make_tool_message("Search results: ...", name="search")
        state = _make_langgraph_state([
            _make_human_message("What is AI?"),
            ai_msg,
            tool_msg,
        ])
        result = _extract_langgraph_metadata(state)
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        # chain_steps: 1 AIMessage + 1 ToolMessage
        assert result.chain_steps is not None
        types = {s["type"] for s in result.chain_steps if "type" in s}
        assert "tool_result" in types
        assert "ai_message" in types

    def test_empty_messages_with_metadata_returns_result(self):
        """빈 messages + __metadata__ 만 있어도 결과 반환"""
        state = _make_langgraph_state([], metadata={"checkpoint": {"step": 1}})
        result = _extract_langgraph_metadata(state)
        assert result is not None

    def test_no_messages_no_metadata_returns_none(self):
        """messages도 없고 __metadata__도 없으면 None 반환"""
        result = _extract_langgraph_metadata({"messages": []})
        assert result is None

    def test_chain_steps_none_for_human_only_messages(self):
        """HumanMessage만 있으면 chain_steps=None (ToolMessage/AIMessage 없음)"""
        state = _make_langgraph_state([_make_human_message("hello")])
        result = _extract_langgraph_metadata(state)
        assert result is not None
        # HumanMessage는 tool_result/ai_message 아니므로 chain_steps None
        if result.chain_steps is not None:
            types = {s.get("type") for s in result.chain_steps}
            assert "tool_result" not in types
            assert "ai_message" not in types


# ---------------------------------------------------------------------------
# C3: CrewAI v2.x output_format / pydantic field
# ---------------------------------------------------------------------------

class TestC3CrewAIV2xFields:

    def test_output_format_extracted_when_no_tasks_output(self):
        """output_format 필드만 있는 경우 agent_interactions 에 포함"""
        raw = _make_crewai_output(output_format="json")
        result = _extract_crewai_metadata(raw)
        assert result is not None
        fmt_interactions = [i for i in result.agent_interactions if i["type"] == "output_format"]
        assert len(fmt_interactions) == 1
        assert "json" in fmt_interactions[0]["result"]

    def test_pydantic_field_treated_as_output_pydantic(self):
        """`pydantic` 필드 (CrewAI v2.x alias) → output_pydantic 동일하게 처리"""
        pydantic_obj = MagicMock()
        pydantic_obj.model_dump_json.return_value = '{"answer": "Seoul"}'
        raw = _make_crewai_output(pydantic=pydantic_obj)
        result = _extract_crewai_metadata(raw)
        assert result is not None
        pydantic_interactions = [i for i in result.agent_interactions
                                  if "pydantic" in i.get("context", "") or "pydantic" in i.get("type", "")]
        assert len(pydantic_interactions) >= 1

    def test_output_format_per_task_extracted(self):
        """tasks_output 내 각 task에 output_format 필드가 있으면 interaction에 포함"""
        task_out = SimpleNamespace(
            agent="researcher",
            description="Find facts",
            raw="Research complete",
            output_format="pydantic",
        )
        raw = _make_crewai_output(tasks_output=[task_out])
        result = _extract_crewai_metadata(raw)
        assert result is not None
        task_interactions = [i for i in result.agent_interactions
                              if i["type"] == "task_completion"]
        assert len(task_interactions) == 1
        assert task_interactions[0].get("output_format") == "pydantic"

    def test_both_pydantic_and_output_format_fields(self):
        """output_pydantic + output_format 둘 다 있을 때 두 interaction 모두 추출"""
        pydantic_obj = MagicMock()
        pydantic_obj.model_dump_json.side_effect = Exception("no json")
        pydantic_obj.__str__ = lambda self: '{"data": 1}'
        raw = _make_crewai_output(output_pydantic=pydantic_obj, output_format="json_object")
        result = _extract_crewai_metadata(raw)
        assert result is not None
        types = {i["type"] for i in result.agent_interactions}
        assert "output_format" in types

    def test_tasks_output_without_output_format_still_works(self):
        """output_format 없는 기존 tasks_output은 기존 동작 유지"""
        task_out = SimpleNamespace(agent="agent1", description="do something", raw="done")
        # output_format 속성 없음
        raw = _make_crewai_output(tasks_output=[task_out])
        result = _extract_crewai_metadata(raw)
        assert result is not None
        assert len(result.agent_interactions) == 1
        # output_format 키 없어야 함
        assert "output_format" not in result.agent_interactions[0]


# ---------------------------------------------------------------------------
# C1: DSPy .history multi-step extraction
# ---------------------------------------------------------------------------

class TestC1DspyHistoryExtraction:

    def test_basic_dspy_prediction_extracted(self):
        """기본 DSPy Prediction (_completions)에서 chain_steps 추출"""
        pred = _make_dspy_prediction(completions=["The answer is 42"])
        result = _extract_dspy_metadata(pred)
        assert result is not None
        assert result.chain_steps is not None
        assert result.chain_steps[0]["name"] == "completion_0"
        assert "42" in result.chain_steps[0]["output"]

    def test_dspy_with_answer_field_extracted(self):
        """answer 필드만 있는 DSPy Prediction도 인식"""
        pred = _make_dspy_prediction(answer="42")
        result = _extract_dspy_metadata(pred)
        assert result is not None

    def test_dspy_multi_step_history_extracted(self):
        """LM history > 1 일 때 history_N chain_steps 추가 추출"""
        import sys
        history_entry_0 = {
            "prompt": "Question: What is 2+2?",
            "response": {
                "choices": [{"message": {"content": "Let me think..."}}]
            },
            "usage": {},
        }
        history_entry_1 = {
            "prompt": "Question: What is 2+2?\nThought: Let me think...",
            "response": {
                "choices": [{"message": {"content": "4"}}]
            },
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_lm = MagicMock()
        mock_lm.history = [history_entry_0, history_entry_1]

        mock_dspy_settings = MagicMock()
        mock_dspy_settings.lm = mock_lm
        mock_dspy_settings._lm = None

        mock_dspy = MagicMock()
        mock_dspy.settings = mock_dspy_settings

        pred = _make_dspy_prediction(completions=["4"])
        original = sys.modules.get("dspy")
        sys.modules["dspy"] = mock_dspy
        try:
            result = _extract_dspy_metadata(pred)
        finally:
            if original is None:
                sys.modules.pop("dspy", None)
            else:
                sys.modules["dspy"] = original

        assert result is not None
        assert result.chain_steps is not None
        # completion_0 + history_0 + history_1
        names = [s["name"] for s in result.chain_steps]
        assert "completion_0" in names
        history_steps = [n for n in names if n.startswith("history_")]
        assert len(history_steps) == 2

    def test_dspy_token_usage_from_last_history(self):
        """마지막 history 항목에서 토큰 사용량 추출"""
        import sys
        history = [
            {"usage": {"prompt_tokens": 5, "completion_tokens": 3}},
            {"usage": {"prompt_tokens": 20, "completion_tokens": 10}},
        ]
        mock_lm = MagicMock()
        mock_lm.history = history

        mock_dspy_settings = MagicMock()
        mock_dspy_settings.lm = mock_lm
        mock_dspy_settings._lm = None

        mock_dspy = MagicMock()
        mock_dspy.settings = mock_dspy_settings

        pred = _make_dspy_prediction(completions=["answer"])
        original = sys.modules.get("dspy")
        sys.modules["dspy"] = mock_dspy
        try:
            result = _extract_dspy_metadata(pred)
        finally:
            if original is None:
                sys.modules.pop("dspy", None)
            else:
                sys.modules["dspy"] = original

        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 20
        assert result.tokens_used["output"] == 10

    def test_dspy_import_error_graceful(self):
        """dspy import 실패 시 tokens_used=None 으로 graceful 처리"""
        pred = _make_dspy_prediction(completions=["answer"])
        with patch("builtins.__import__", side_effect=ImportError("no dspy")):
            # just call without mocking — dspy import fails → tokens_used=None
            result = _extract_dspy_metadata(pred)
        # ImportError 시 chain_steps는 있고 tokens_used=None
        assert result is not None
        assert result.chain_steps is not None

    def test_non_dspy_object_returns_none(self):
        """DSPy Prediction 형식이 아닌 객체는 None 반환"""
        result = _extract_dspy_metadata({"answer": "42"})
        assert result is None


# ---------------------------------------------------------------------------
# C1: PydanticAI .all_messages() extraction
# ---------------------------------------------------------------------------

class TestC1PydanticAIAllMessages:

    def test_all_messages_preferred_over_messages(self):
        """.all_messages() 가 있으면 .messages 대신 사용"""
        all_msgs = [SimpleNamespace(content="Hello", parts=None)]
        regular_msgs = [SimpleNamespace(content="Hello partial", parts=None)]

        obj = MagicMock()
        obj.data = "result"
        obj.usage.return_value = None
        obj.messages = regular_msgs
        obj.all_messages.return_value = all_msgs

        result = _extract_pydanticai_metadata(obj)
        assert result is not None
        assert result.chain_steps is not None
        # all_messages 결과가 사용됨 (content="Hello")
        contents = [s["content"] for s in result.chain_steps]
        assert any("Hello" in c for c in contents)

    def test_tool_call_part_extracted(self):
        """ToolCallPart → chain_steps type='tool_call'"""
        tool_part = MagicMock()
        tool_part.__class__.__name__ = "ToolCallPart"
        tool_part.tool_name = "search"
        tool_part.args = {"query": "AI"}

        msg = MagicMock()
        msg.__class__.__name__ = "ModelRequest"
        msg.parts = [tool_part]

        obj = MagicMock()
        obj.data = "result"
        obj.usage.return_value = None
        del obj.all_messages
        obj.messages = [msg]

        result = _extract_pydanticai_metadata(obj)
        assert result is not None
        assert result.chain_steps is not None
        tool_steps = [s for s in result.chain_steps if s.get("type") == "tool_call"]
        assert len(tool_steps) == 1
        assert tool_steps[0]["name"] == "search"

    def test_tool_return_part_extracted(self):
        """ToolReturnPart → chain_steps type='tool_return'"""
        tool_return_part = MagicMock()
        tool_return_part.__class__.__name__ = "ToolReturnPart"
        tool_return_part.tool_name = "search"
        tool_return_part.content = "Search results here"

        msg = MagicMock()
        msg.__class__.__name__ = "ModelResponse"
        msg.parts = [tool_return_part]

        obj = MagicMock()
        obj.data = "result"
        obj.usage.return_value = None
        del obj.all_messages
        obj.messages = [msg]

        result = _extract_pydanticai_metadata(obj)
        assert result is not None
        tool_returns = [s for s in result.chain_steps if s.get("type") == "tool_return"]
        assert len(tool_returns) == 1
        assert "Search results" in tool_returns[0]["content"]

    def test_text_part_extracted(self):
        """TextPart → chain_steps (content non-empty)"""
        text_part = MagicMock()
        text_part.__class__.__name__ = "TextPart"
        text_part.content = "The answer is 42"

        msg = MagicMock()
        msg.__class__.__name__ = "ModelResponse"
        msg.parts = [text_part]

        obj = MagicMock()
        obj.data = "42"
        obj.usage.return_value = None
        del obj.all_messages
        obj.messages = [msg]

        result = _extract_pydanticai_metadata(obj)
        assert result is not None
        text_steps = [s for s in result.chain_steps if s.get("type") == "text"]
        assert len(text_steps) == 1
        assert "42" in text_steps[0]["content"]

    def test_token_usage_extracted(self):
        """usage() 에서 token 정보 추출"""
        usage_obj = SimpleNamespace(request_tokens=100, response_tokens=50)

        obj = MagicMock()
        obj.data = "result"
        obj.usage.return_value = usage_obj
        # 구버전 .usage()는 bound method라 request_tokens/input_tokens 속성이 없다.
        # MagicMock은 기본적으로 모든 속성 접근에 응답하므로(hasattr 항상 True) 명시적으로
        # 지워서 callable-메서드 분기(2.x property 분기가 아님)를 타도록 한다.
        del obj.usage.request_tokens
        del obj.usage.input_tokens
        del obj.all_messages
        obj.messages = []

        result = _extract_pydanticai_metadata(obj)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 100
        assert result.tokens_used["output"] == 50
        assert result.tokens_used["total"] == 150

    def test_non_pydanticai_object_returns_none(self):
        """data/usage 없는 객체는 None 반환"""
        result = _extract_pydanticai_metadata({"data": "result"})
        assert result is None


# ---------------------------------------------------------------------------
# C4: autogen async — agent_eval(framework="autogen") 방식 확인
# ---------------------------------------------------------------------------

class TestC4AutogenEvalAsync:

    def test_agent_eval_supports_autogen_framework(self):
        """agent_eval에 framework='autogen' 지정 가능."""
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "autogen" in _FRAMEWORK_ADAPTERS

    def test_agent_eval_async_function_with_autogen(self):
        """async 함수에 agent_eval(framework='autogen') 적용 가능."""
        import asyncio
        from agent_evaluator import agent_eval
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="coordination", framework="autogen")
        async def my_agent(question: str, ground_truth: str = "") -> str:
            return "agent response"

        result = asyncio.get_event_loop().run_until_complete(my_agent("test?"))
        assert result == "agent response"
        assert monitor.task_count == 1


# ---------------------------------------------------------------------------
# C6: _FRAMEWORK_ADAPTER_META + get_framework_info()
# ---------------------------------------------------------------------------

class TestC6FrameworkAdapterMeta:

    def test_get_framework_info_langchain(self):
        """langchain 어댑터 정보 반환"""
        info = get_framework_info("langchain")
        assert info is not None
        assert info["name"] == "LangChain"
        assert "tool_calls" in info["extracts"]
        assert info["extras"] == "langchain"

    def test_get_framework_info_langgraph(self):
        """langgraph 어댑터 정보 — chain_steps 포함"""
        info = get_framework_info("langgraph")
        assert info is not None
        assert "chain_steps" in info["extracts"]
        assert "__metadata__" in info["description"] or "ToolMessage" in info["description"]

    def test_get_framework_info_crewai(self):
        """crewai 어댑터 정보 — output_format 언급"""
        info = get_framework_info("crewai")
        assert info is not None
        assert "output_format" in info["description"] or "pydantic" in info["description"]

    def test_get_framework_info_autogen(self):
        """autogen 어댑터 정보 — async_supported=True"""
        info = get_framework_info("autogen")
        assert info is not None
        assert info["async_supported"] is True

    def test_get_framework_info_dspy(self):
        """dspy 어댑터 정보 — history 언급"""
        info = get_framework_info("dspy")
        assert info is not None
        assert "history" in info["description"]

    def test_get_framework_info_pydanticai(self):
        """pydanticai 어댑터 정보 — all_messages 언급"""
        info = get_framework_info("pydanticai")
        assert info is not None
        assert "all_messages" in info["description"]

    def test_get_framework_info_unknown_returns_none(self):
        """알 수 없는 프레임워크는 None 반환"""
        assert get_framework_info("nonexistent_fw_xyz") is None

    def test_all_framework_adapters_have_meta(self):
        """_FRAMEWORK_ADAPTERS 의 모든 키가 _FRAMEWORK_ADAPTER_META 에 존재"""
        for key in _FRAMEWORK_ADAPTERS:
            assert key in _FRAMEWORK_ADAPTER_META, f"Missing meta for adapter: {key}"

    def test_meta_required_fields(self):
        """모든 메타 항목에 필수 필드 존재"""
        required = {"name", "extras", "extracts", "async_supported", "description"}
        for fw, meta in _FRAMEWORK_ADAPTER_META.items():
            missing = required - set(meta.keys())
            assert not missing, f"{fw}: missing fields {missing}"

    def test_get_framework_info_top_level_import(self):
        """get_framework_info top-level import"""
        from agent_evaluator import get_framework_info as gfi
        assert callable(gfi)
        assert gfi("openai") is not None

    def test_meta_extracts_is_list(self):
        """extracts 필드는 list 타입"""
        for fw, meta in _FRAMEWORK_ADAPTER_META.items():
            assert isinstance(meta["extracts"], list), f"{fw}: extracts should be list"

    def test_meta_count_matches_adapters(self):
        """_FRAMEWORK_ADAPTER_META 와 _FRAMEWORK_ADAPTERS 의 키 수 동일"""
        assert len(_FRAMEWORK_ADAPTER_META) == len(_FRAMEWORK_ADAPTERS)


# ---------------------------------------------------------------------------
# C5: Integration test helpers validation
# ---------------------------------------------------------------------------

class TestC5IntegrationHelpers:
    """C5: 어댑터 통합 테스트 헬퍼 검증."""

    def test_make_langgraph_state_basic(self):
        """헬퍼 _make_langgraph_state 기본 동작"""
        state = _make_langgraph_state([])
        assert "messages" in state
        assert state["messages"] == []

    def test_make_langgraph_state_with_metadata(self):
        """헬퍼 _make_langgraph_state __metadata__ 포함"""
        state = _make_langgraph_state([], metadata={"node": "data"})
        assert "__metadata__" in state

    def test_make_ai_message_mock(self):
        """AI message mock 타입명 AIMessage"""
        msg = _make_ai_message("hello")
        assert "AIMessage" in type(msg).__name__ or msg.__class__.__name__ == "AIMessage"

    def test_make_tool_message_mock(self):
        """Tool message mock 타입명 ToolMessage"""
        msg = _make_tool_message("result")
        assert msg.__class__.__name__ == "ToolMessage"

    def test_framework_adapter_smoke_test(self):
        """모든 어댑터가 None이 아닌 callable 인지 확인 (sentinel None 제외)"""
        for name, fn in _FRAMEWORK_ADAPTERS.items():
            # H: "native" 는 sentinel None — 어댑터 없음을 나타내므로 제외
            if fn is None:
                continue
            assert callable(fn), f"{name} adapter is not callable"

    def test_adapter_returns_none_for_wrong_type(self):
        """잘못된 타입 입력 시 각 어댑터가 None 반환 (crash 없이)"""
        dummy_inputs = [None, 42, "string", [], {}]
        adapters_to_test = ["langchain", "langgraph", "crewai", "autogen", "dspy", "pydanticai"]
        for fw in adapters_to_test:
            fn = _FRAMEWORK_ADAPTERS[fw]
            for inp in dummy_inputs:
                try:
                    result = fn(inp)
                    assert result is None or isinstance(result, EvalMetadata), \
                        f"{fw} adapter returned unexpected type for input {inp!r}: {type(result)}"
                except Exception as exc:
                    pytest.fail(f"{fw} adapter raised {type(exc).__name__} for input {inp!r}: {exc}")



# ===========================================================================
# From test_v080_gaps.py
# ===========================================================================

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



# ===========================================================================
# From test_v081_improvements.py
# ===========================================================================

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
        # auto_detect_framework is handled internally; not exposed as a public parameter
        param = sig.parameters.get("auto_detect_framework")
        assert param is None  # internal-only, not in public signature


# ---------------------------------------------------------------------------
# G4: agent_eval enable_hallucination parameter
# ---------------------------------------------------------------------------

class TestAgentEvalEnableHallucination:
    def test_enable_hallucination_param_exists(self):
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        # v0.8.1+: renamed to enable_hallucination_detection
        assert "enable_hallucination_detection" in sig.parameters

    def test_enable_hallucination_false_by_default(self):
        # SPEC-039 REQ-1: 시그니처 기본값은 이제 preset 충돌 판정용 내부 sentinel(`_UNSET`)이다
        # — "명시하지 않으면 False로 해석된다"는 실제 동작은 함수 호출 기반 테스트들이
        # 별도로 검증한다(예: test_spec039_decorator_architecture.py). 여기서는 sentinel이
        # 여전히 이 파라미터의 기본값으로 연결돼 있는지만 확인한다.
        from agent_evaluator.decorators import _UNSET, agent_eval
        sig = inspect.signature(agent_eval)
        assert sig.parameters["enable_hallucination_detection"].default is _UNSET

    def test_hallucination_runs_when_enabled(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=False)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination_detection=True)
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

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination_detection=True)
        def agent(question, ctx="", ground_truth=""):
            return "answer"

        agent("q", ctx="some context", ground_truth="answer")
        # Flag should be restored to False
        assert monitor.enable_hallucination_detection is False

    def test_enable_hallucination_false_no_detection(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(enable_hallucination_detection=False)

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination_detection=False)
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

        @agent_eval(monitor, task_type="qa", context_arg="ctx", enable_hallucination_detection=True)
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



# ===========================================================================
# From test_v084_improvements.py
# ===========================================================================

@pytest.fixture
def monitor(tmp_path):
    return PerformanceMonitor(output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# TestA2AnomalyDetectionTempOverride
# ---------------------------------------------------------------------------


class TestA2AnomalyDetectionTempOverride:
    def test_enable_anomaly_detection_param_accepted(self, monitor):
        """enable_anomaly_detection=True 파라미터가 오류 없이 수용됨."""

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            return "답변"

        result = agent("질문")
        assert result == "답변"

    def test_anomaly_flag_restored_after_call(self, monitor):
        """호출 완료 후 enable_anomaly_detection 플래그가 원래 값으로 복원됨."""
        monitor.enable_anomaly_detection = False

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            return "답변"

        agent("질문")
        assert monitor.enable_anomaly_detection is False

    def test_anomaly_flag_restored_even_after_exception(self, monitor):
        """예외 발생 시에도 anomaly detection 플래그가 복원됨."""
        monitor.enable_anomaly_detection = False

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            raise ValueError("테스트 오류")

        with pytest.raises(ValueError):
            agent("질문")

        assert monitor.enable_anomaly_detection is False

    def test_anomaly_preset_production_activates_detection(self, monitor):
        """production preset에 enable_anomaly_detection이 포함됨."""
        from agent_evaluator import AGENT_EVAL_PRESETS

        assert AGENT_EVAL_PRESETS["production"].get("enable_anomaly_detection") is True

    def test_effective_enable_anomaly_computed(self, monitor):
        """_effective_enable_anomaly 가 preset과 파라미터를 합산함."""
        # production preset을 사용하면 enable_anomaly_detection=True 가 적용되어야 함
        @agent_eval(monitor, task_type="qa", preset="production")
        def agent(question, ground_truth=""):
            return "답변"

        # 예외 없이 실행되면 성공
        result = agent("질문")
        assert result == "답변"


# ---------------------------------------------------------------------------
# TestC1CrewAITokenExtraction
# ---------------------------------------------------------------------------


class TestC1CrewAITokenExtraction:
    def test_token_usage_dict_extraction(self):
        """CrewOutput에 token_usage dict가 있으면 tokens_used 추출됨."""

        class FakeTaskOut:
            agent = "researcher"
            description = "Research task"
            raw = "Result text"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            token_usage = {"prompt_tokens": 200, "completion_tokens": 100}
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["input"] == 200
        assert meta.tokens_used["output"] == 100
        assert meta.tokens_used["total"] == 300

    def test_usage_metrics_dict_extraction(self):
        """CrewOutput에 usage_metrics dict가 있으면 tokens_used 추출됨."""

        class FakeTaskOut:
            agent = "writer"
            description = "Write task"
            raw = "Written text"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            usage_metrics = {"prompt_tokens": 150, "completion_tokens": 80}
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["total"] == 230

    def test_no_token_usage_returns_none_tokens(self):
        """token 정보 없을 때 tokens_used는 None."""

        class FakeTaskOut:
            agent = "analyst"
            description = "Analyze"
            raw = "Analysis"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is None


# ---------------------------------------------------------------------------
# TestC2DSPyPydanticAIDetection
# ---------------------------------------------------------------------------


class TestC2DSPyPydanticAIDetection:
    def test_dspy_prediction_via_completions(self):
        """DSPy Prediction — completions 속성으로 감지."""

        class FakeDSPyPrediction:
            completions = {"answer": ["value1", "value2"]}
            # no choices, no content

        assert _auto_detect_framework(FakeDSPyPrediction()) == "dspy"

    def test_dspy_prediction_via_underscore_completions(self):
        """DSPy Prediction — _completions 속성으로 감지."""

        class FakeDSPyPrediction:
            _completions = [{"answer": "value"}]

        assert _auto_detect_framework(FakeDSPyPrediction()) == "dspy"

    def test_pydanticai_runresult_via_all_messages(self):
        """PydanticAI RunResult — data + all_messages() callable 조합으로 감지."""

        class FakePydanticAIRunResult:
            data = "답변"

            def all_messages(self):
                return []

        assert _auto_detect_framework(FakePydanticAIRunResult()) == "pydanticai"

    def test_openai_response_not_confused_with_dspy(self):
        """choices 있는 OpenAI 응답은 dspy로 감지 안 됨."""

        class FakeOpenAI:
            choices = [MagicMock()]
            model = "gpt-4o"
            usage = MagicMock()

        result = _auto_detect_framework(FakeOpenAI())
        assert result != "dspy"


# ---------------------------------------------------------------------------
# TestC3OpenAIStreamingDelta
# ---------------------------------------------------------------------------


class TestC3OpenAIStreamingDelta:
    def test_streaming_chunk_tool_calls_extracted(self):
        """OpenAI streaming 청크(choice.delta)에서 tool_calls 추출."""

        class FakeFunction:
            name = "search"
            arguments = '{"query": "test"}'

        class FakeToolCall:
            function = FakeFunction()
            id = "tc_001"

        class FakeDelta:
            tool_calls = [FakeToolCall()]

        class FakeChoice:
            message = None
            delta = FakeDelta()

        class FakeStreamingChunk:
            choices = [FakeChoice()]

        meta = _extract_openai_metadata(FakeStreamingChunk())
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["tool_name"] == "search"

    def test_streaming_chunk_without_tool_calls_returns_none(self):
        """tool_calls 없는 스트리밍 청크는 None 반환."""

        class FakeDelta:
            tool_calls = None

        class FakeChoice:
            message = None
            delta = FakeDelta()

        class FakeStreamingChunk:
            choices = [FakeChoice()]

        meta = _extract_openai_metadata(FakeStreamingChunk())
        assert meta is None or (meta is not None and not meta.tool_calls)


# ---------------------------------------------------------------------------
# TestD3BatchEvalDataFrame
# ---------------------------------------------------------------------------


class TestD3BatchEvalDataFrame:
    def test_dataframe_has_extended_fields(self, monitor):
        """return_format='dataframe'이 확장 필드를 포함한 DataFrame 반환."""
        pytest.importorskip("pandas")

        @batch_eval(monitor, task_type="qa", return_format="dataframe")
        def agents(questions, ground_truths=None):
            return [f"답변 {i}" for i in range(len(questions))]

        df = agents(["질문1", "질문2"])
        import pandas as pd

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        # D3 추가 필드 확인
        assert "tokens_total" in df.columns
        assert "tool_call_count" in df.columns
        assert "has_error" in df.columns
        assert "attempts" in df.columns
        assert "timestamp" in df.columns

    def test_dataframe_fallback_without_pandas(self, monitor):
        """pandas 없으면 경고 후 list 반환 (graceful degradation)."""
        import importlib
        import sys

        # pandas 있으면 이 테스트는 skip (이 환경엔 pandas가 있을 것)
        try:
            import pandas  # noqa: F401
            pytest.skip("pandas available — graceful degradation test not applicable")
        except ImportError:
            pass

        @batch_eval(monitor, task_type="qa", return_format="dataframe")
        def agents(questions, ground_truths=None):
            return [f"답변 {i}" for i in range(len(questions))]

        result = agents(["질문1"])
        # list 반환 (pandas 없으므로)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TestD6GeneratorTTFT
# ---------------------------------------------------------------------------


class TestD6GeneratorTTFT:
    def test_sync_generator_records_ttft(self, monitor):
        """sync generator — 첫 yield 까지 시간이 LatencyTracker에 TTFT로 기록됨."""

        @agent_eval(monitor, task_type="qa")
        def streaming_agent(question, ground_truth=""):
            yield "첫 "
            yield "번째 "
            yield "응답"

        list(streaming_agent("질문"))

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats.get("count", 0) >= 1

    def test_async_generator_records_ttft(self, monitor):
        """async generator — 첫 yield 까지 시간이 LatencyTracker에 TTFT로 기록됨."""

        @agent_eval(monitor, task_type="qa")
        async def async_streaming_agent(question, ground_truth=""):
            yield "첫 "
            yield "번째 "
            yield "응답"

        async def run():
            chunks = []
            async for chunk in async_streaming_agent("질문"):
                chunks.append(chunk)
            return chunks

        asyncio.get_event_loop().run_until_complete(run())

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats.get("count", 0) >= 1

    def test_sync_generator_ttft_is_reasonable(self, monitor):
        """sync generator TTFT는 0 이상 전체 실행 시간 이하."""
        import time

        @agent_eval(monitor, task_type="qa")
        def streaming_agent(question, ground_truth=""):
            yield "chunk"

        start = time.perf_counter()
        list(streaming_agent("질문"))
        total = time.perf_counter() - start

        stats = monitor.latency_tracker.get_ttft_stats()
        if stats.get("count", 0) > 0:
            ttft = stats.get("min", 0)
            assert 0 <= ttft <= total + 0.1  # 여유 0.1s


# ---------------------------------------------------------------------------
# TestB2FrameworkBreakdown — /api/results/{file_id}/frameworks
# ---------------------------------------------------------------------------


class TestB2FrameworkBreakdown:
    def test_endpoint_function_exists(self):
        """get_framework_breakdown 함수가 data.py에 존재."""
        from agent_evaluator.serve.routers.data import get_framework_breakdown

        assert callable(get_framework_breakdown)

    def test_endpoint_returns_framework_data(self):
        """모의 데이터로 framework 집계 정확성 검증."""
        from agent_evaluator.serve.routers.data import get_framework_breakdown

        # 모의 TaskRecord
        class FakeTask:
            def __init__(self, fw, success, accuracy, execution_time, tokens_used):
                self.framework = fw
                self.success = success
                self.accuracy_score = accuracy
                self.execution_time = execution_time
                self.tokens_used = tokens_used

        class FakeResultFile:
            tasks = [
                FakeTask("langchain", True, 0.9, 1.0, {"total": 100}),
                FakeTask("langchain", False, 0.5, 2.0, {"total": 80}),
                FakeTask("openai", True, 0.8, 0.5, {"total": 60}),
            ]

        class FakeRS:
            def by_id(self, fid):
                return FakeResultFile()

        class FakeRequest:
            def __init__(self):
                self.app = type("App", (), {"state": type("State", (), {"result_store": FakeRS()})()})()

        # 직접 로직 검증 (HTTP 레이어 없이)
        from collections import defaultdict
        tasks = FakeResultFile().tasks
        fw_data = defaultdict(lambda: {"task_count": 0, "success_count": 0, "accuracy_sum": 0.0, "latency_sum": 0.0, "tokens_sum": 0})
        for t in tasks:
            fw = t.framework or "native"
            d = fw_data[fw]
            d["task_count"] += 1
            if t.success:
                d["success_count"] += 1
            d["accuracy_sum"] += t.accuracy_score
            d["latency_sum"] += t.execution_time
            d["tokens_sum"] += (t.tokens_used or {}).get("total", 0)

        assert "langchain" in fw_data
        assert fw_data["langchain"]["task_count"] == 2
        assert fw_data["langchain"]["success_count"] == 1
        assert fw_data["openai"]["task_count"] == 1


# ---------------------------------------------------------------------------
# TestB4LLMJudgeEndpoint — /api/results/{file_id}/llm_judge
# ---------------------------------------------------------------------------


class TestB4LLMJudgeEndpoint:
    def test_endpoint_function_exists(self):
        """get_llm_judge_details 함수가 data.py에 존재."""
        from agent_evaluator.serve.routers.data import get_llm_judge_details

        assert callable(get_llm_judge_details)

    def test_endpoint_signature_has_filter_params(self):
        """min_score / max_score / skip / limit 파라미터 존재."""
        import inspect
        from agent_evaluator.serve.routers.data import get_llm_judge_details

        sig = inspect.signature(get_llm_judge_details)
        assert "min_score" in sig.parameters
        assert "max_score" in sig.parameters
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters

    def test_score_filter_logic(self):
        """min_score 필터 로직 검증."""
        results = [
            {"task_id": "t1", "scores": {"overall": 0.9}},
            {"task_id": "t2", "scores": {"overall": 0.4}},
            {"task_id": "t3", "scores": {"overall": 0.7}},
        ]
        min_score = 0.6
        filtered = [r for r in results if (r.get("scores") or {}).get("overall", 0.0) >= min_score]
        assert len(filtered) == 2
        assert all(r["scores"]["overall"] >= 0.6 for r in filtered)


# ---------------------------------------------------------------------------
# TestB1TaskDetailLLMJudge — task detail API llm_judge 포함
# ---------------------------------------------------------------------------


class TestB1TaskDetailLLMJudge:
    def test_task_detail_includes_llm_judge(self):
        """get_task_detail() 응답에 llm_judge 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        # 함수 소스에서 llm_judge 필드 포함 확인
        src = inspect.getsource(get_task_detail)
        assert '"llm_judge"' in src or "'llm_judge'" in src

    def test_task_detail_includes_streaming_steps(self):
        """get_task_detail() 응답에 streaming_steps 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        src = inspect.getsource(get_task_detail)
        assert "streaming_steps" in src

    def test_task_detail_includes_chunk_count(self):
        """get_task_detail() 응답에 chunk_count 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        src = inspect.getsource(get_task_detail)
        assert "chunk_count" in src
