"""
tests/test_v073_improvements.py
================================
v0.7.3 개선 사항 테스트:
  - batch_eval concurrent 옵션
  - LangChain 어댑터 토큰 추출
  - AutoGen 어댑터 토큰 추출
  - QuickEval.streaming 속성
  - score_fn 타입 힌트 (callable 동작 확인)
  - SSE /stream/tasks/{file_id} 라우터 등록 확인
  - ConversationSession 상세 API 라우터 등록 확인
"""
from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# batch_eval concurrent
# ---------------------------------------------------------------------------

class TestBatchEvalConcurrent:
    def test_concurrent_param_accepted(self, tmp_path):
        """concurrent=True 파라미터가 오류 없이 수용되어야 한다.

        concurrent=True 시 함수가 단일 항목(questions=[q])으로 개별 호출되므로
        각 호출은 len=1 짜리 리스트를 처리한다 → "answer_0" * N 반환.
        """
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrent=True)
        async def async_agent(questions, ground_truths=None):
            # 단일 항목 호출: questions=["q1"] → range(1) → ["answer_0"]
            return [f"answer_{i}" for i in range(len(questions))]

        results = asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        )
        assert len(results) == 2
        assert all(r == "answer_0" for r in results)  # 각 단일 호출의 첫 번째 요소

    def test_concurrent_runs_items_independently(self, tmp_path):
        """concurrent=True 시 항목별 개별 호출로 분리되어 실행된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        call_log = []

        @batch_eval(monitor, task_type="qa", concurrent=True)
        async def async_agent(questions, ground_truths=None):
            call_log.append(len(questions))
            return [f"ans" for _ in questions]

        asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        )
        # concurrent=True: 3개 항목이 개별 호출로 분리 → 각 call은 len=1
        assert all(n == 1 for n in call_log), f"expected all 1-item calls, got {call_log}"

    def test_concurrent_false_calls_function_once(self, tmp_path):
        """concurrent=False (기본값)이면 함수가 한 번만 호출된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        call_count = []

        @batch_eval(monitor, task_type="qa", concurrent=False)
        async def async_agent(questions, ground_truths=None):
            call_count.append(1)
            return [f"ans" for _ in questions]

        asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        )
        assert len(call_count) == 1

    def test_max_concurrent_param_accepted(self, tmp_path):
        """max_concurrent 파라미터가 오류 없이 수용되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrent=True, max_concurrent=2)
        async def async_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        results = asyncio.get_event_loop().run_until_complete(
            async_agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        )
        assert len(results) == 3

    def test_concurrent_records_all_tasks(self, tmp_path):
        """concurrent=True 시에도 각 항목이 모두 monitor에 기록된다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", concurrent=True)
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
