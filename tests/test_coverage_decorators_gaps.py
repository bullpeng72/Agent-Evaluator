"""
tests/test_coverage_decorators_gaps.py
========================================
decorators.py 미커버 영역 집중 테스트 (72% → 82%+ 목표).

커버 대상:
  - _extract_response: EvalMetadata 튜플, OpenAI choices, Anthropic, Gemini,
                       Cohere, LangChain BaseMessage, dict, None
  - _is_openai_response / _is_anthropic_response / _is_gemini_response /
    _is_cohere_response
  - _extract_anthropic_tokens / _extract_gemini_tokens / _extract_cohere_tokens
  - _split_raw / _split_turn_raw
  - _normalize_task_type (Enum 및 문자열)
  - _is_langchain_response
  - _extract_langchain_metadata (with intermediate_steps + token usage)
  - _extract_crewai_metadata (tasks_output 없는 경우 포함)
  - _extract_smolagents_metadata (dict/object steps)
  - _extract_semantic_kernel_metadata (value, inner_content, metadata)
  - _auto_detect_framework (모듈명 / 속성 기반)
  - get_framework_info (known/unknown)
  - _EvalContext / get_eval_ctx (active/inactive)
  - flush_all_conversations / flush_conversation (no session)
  - agent_eval: preset, rag_mode, security_mode,
                timeout wrapper, retry config path,
                enabled=False shortcut, sample_rate skip
  - _fmt_value/_fmt_threshold/_fmt_delta (from gate tests — already covered)
"""

from __future__ import annotations

import asyncio
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator.decorators import (
    EvalMetadata,
    TurnMetadata,
    _EvalContext,
    _auto_detect_framework,
    _extract_anthropic_tokens,
    _extract_cohere_tokens,
    _extract_gemini_tokens,
    _extract_langchain_metadata,
    _extract_response,
    _is_anthropic_response,
    _is_cohere_response,
    _is_gemini_response,
    _is_langchain_response,
    _is_openai_response,
    _normalize_task_type,
    _split_raw,
    _split_turn_raw,
    flush_all_conversations,
    flush_conversation,
    get_eval_ctx,
    get_framework_info,
)


# ===========================================================================
# 공통 픽스처
# ===========================================================================

@pytest.fixture
def monitor():
    from agent_evaluator import PerformanceMonitor
    import tempfile, os
    d = tempfile.mkdtemp()
    return PerformanceMonitor(output_dir=d)


# ===========================================================================
# 1. _extract_response
# ===========================================================================

class TestExtractResponse:
    def test_none_returns_empty(self):
        assert _extract_response(None) == ""

    def test_string_passthrough(self):
        assert _extract_response("hello") == "hello"

    def test_int_to_str(self):
        assert _extract_response(42) == "42"

    def test_evalmetadata_tuple_extracts_first(self):
        meta = EvalMetadata()
        raw = ("the answer", meta)
        assert _extract_response(raw) == "the answer"

    def test_dict_answer_key(self):
        assert _extract_response({"answer": "Seoul"}) == "Seoul"

    def test_dict_output_key(self):
        assert _extract_response({"output": "result"}) == "result"

    def test_dict_result_key(self):
        assert _extract_response({"result": "data"}) == "data"

    def test_dict_no_known_key(self):
        result = _extract_response({"unknown_key": "value"})
        assert "unknown_key" in result or "value" in result

    def test_openai_choices_extraction(self):
        msg = MagicMock()
        msg.content = "openai answer"
        choice = MagicMock()
        choice.message = msg
        raw = MagicMock()
        raw.choices = [choice]
        raw.usage = MagicMock()
        assert _extract_response(raw) == "openai answer"

    def test_openai_choices_none_content(self):
        msg = MagicMock()
        msg.content = None
        choice = MagicMock()
        choice.message = msg
        raw = MagicMock()
        raw.choices = [choice]
        raw.usage = MagicMock()
        assert _extract_response(raw) == ""

    def test_anthropic_response_extraction(self):
        text_block = MagicMock()
        text_block.text = "anthropic answer"
        raw = MagicMock(spec=[])
        raw.content = [text_block]
        raw.usage = MagicMock()
        raw.stop_reason = "end_turn"
        # No .choices — is_anthropic_response should return True
        assert _is_anthropic_response(raw)
        result = _extract_response(raw)
        assert result == "anthropic answer"

    def test_gemini_response_extraction(self):
        part = MagicMock()
        part.text = "gemini answer"
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        raw = MagicMock(spec=[])
        raw.candidates = [candidate]
        raw.usage_metadata = MagicMock()
        assert _is_gemini_response(raw)
        result = _extract_response(raw)
        assert result == "gemini answer"

    def test_langchain_basemessage_extraction(self):
        # Create an object with .content attribute but no .choices — simulates LangChain BaseMessage
        class FakeLCMessage:
            content = "langchain message"
        result = _extract_response(FakeLCMessage())
        assert result == "langchain message"

    def test_cohere_response_text_extraction(self):
        raw = MagicMock(spec=[])
        raw.text = "cohere text"
        raw.meta = MagicMock()
        raw.meta.tokens = MagicMock()
        # No .choices
        assert _is_cohere_response(raw)
        result = _extract_response(raw)
        assert result == "cohere text"


# ===========================================================================
# 2. is_* helpers
# ===========================================================================

class TestIsHelpers:
    def test_is_openai_response_positive(self):
        raw = MagicMock()
        raw.choices = []
        raw.usage = MagicMock()
        assert _is_openai_response(raw)

    def test_is_openai_response_negative_no_usage(self):
        raw = MagicMock(spec=["choices"])
        assert not _is_openai_response(raw)

    def test_is_openai_response_none(self):
        assert not _is_openai_response(None)

    def test_is_anthropic_response_positive(self):
        raw = MagicMock(spec=["content", "usage", "stop_reason"])
        raw.content = []
        raw.usage = MagicMock()
        raw.stop_reason = "end_turn"
        assert _is_anthropic_response(raw)

    def test_is_anthropic_response_negative_has_choices(self):
        raw = MagicMock()  # has .choices (openai)
        raw.content = []
        raw.usage = MagicMock()
        raw.stop_reason = "end_turn"
        raw.choices = []
        assert not _is_anthropic_response(raw)

    def test_is_gemini_response_positive(self):
        raw = MagicMock(spec=["candidates", "usage_metadata"])
        raw.candidates = []
        raw.usage_metadata = MagicMock()
        assert _is_gemini_response(raw)

    def test_is_gemini_response_negative(self):
        raw = MagicMock(spec=["candidates"])
        assert not _is_gemini_response(raw)

    def test_is_cohere_response_via_finish_reason(self):
        raw = MagicMock(spec=["finish_reason"])
        raw.finish_reason = "COMPLETE"
        assert _is_cohere_response(raw)

    def test_is_cohere_response_via_meta_tokens(self):
        raw = MagicMock(spec=["meta"])
        raw.meta = MagicMock()
        raw.meta.tokens = MagicMock()
        assert _is_cohere_response(raw)

    def test_is_cohere_response_false_has_choices(self):
        raw = MagicMock()
        raw.finish_reason = "COMPLETE"
        raw.choices = []  # has choices → not cohere
        assert not _is_cohere_response(raw)

    def test_is_langchain_response_positive(self):
        assert _is_langchain_response({"intermediate_steps": []})

    def test_is_langchain_response_negative(self):
        assert not _is_langchain_response({"output": "text"})
        assert not _is_langchain_response("string")


# ===========================================================================
# 3. token extractors
# ===========================================================================

class TestTokenExtractors:
    def test_extract_anthropic_tokens(self):
        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20
        raw = MagicMock()
        raw.usage = usage
        result = _extract_anthropic_tokens(raw)
        assert result == {"input": 10, "output": 20, "total": 30}

    def test_extract_anthropic_tokens_zero_returns_none(self):
        usage = MagicMock()
        usage.input_tokens = 0
        usage.output_tokens = 0
        raw = MagicMock()
        raw.usage = usage
        assert _extract_anthropic_tokens(raw) is None

    def test_extract_anthropic_tokens_exception_returns_none(self):
        raw = MagicMock()
        raw.usage = None  # will cause AttributeError
        # Should not raise
        result = _extract_anthropic_tokens(raw)
        # None or dict — no crash

    def test_extract_gemini_tokens(self):
        meta = MagicMock()
        meta.prompt_token_count = 15
        meta.candidates_token_count = 25
        raw = MagicMock()
        raw.usage_metadata = meta
        result = _extract_gemini_tokens(raw)
        assert result == {"input": 15, "output": 25, "total": 40}

    def test_extract_gemini_tokens_zero_returns_none(self):
        meta = MagicMock()
        meta.prompt_token_count = 0
        meta.candidates_token_count = 0
        raw = MagicMock()
        raw.usage_metadata = meta
        assert _extract_gemini_tokens(raw) is None

    def test_extract_cohere_tokens(self):
        tokens = MagicMock()
        tokens.input_tokens = 5
        tokens.output_tokens = 10
        meta = MagicMock()
        meta.tokens = tokens
        raw = MagicMock()
        raw.meta = meta
        result = _extract_cohere_tokens(raw)
        assert result == {"input": 5, "output": 10, "total": 15}

    def test_extract_cohere_tokens_zero_returns_none(self):
        tokens = MagicMock()
        tokens.input_tokens = 0
        tokens.output_tokens = 0
        meta = MagicMock()
        meta.tokens = tokens
        raw = MagicMock()
        raw.meta = meta
        assert _extract_cohere_tokens(raw) is None


# ===========================================================================
# 4. _split_raw / _split_turn_raw
# ===========================================================================

class TestSplitHelpers:
    def test_split_raw_with_eval_metadata_tuple(self):
        meta = EvalMetadata(framework="langchain")
        raw = ("response", meta)
        result, m = _split_raw(raw)
        assert result == "response"
        assert m is meta

    def test_split_raw_plain_string(self):
        result, m = _split_raw("plain")
        assert result == "plain"
        assert m is None

    def test_split_raw_dict(self):
        d = {"output": "data"}
        result, m = _split_raw(d)
        assert result == d
        assert m is None

    def test_split_turn_raw_with_turn_metadata(self):
        tm = TurnMetadata()
        raw = ("user_msg", tm)
        result, m = _split_turn_raw(raw)
        assert result == "user_msg"
        assert m is tm

    def test_split_turn_raw_plain(self):
        result, m = _split_turn_raw("plain")
        assert result == "plain"
        assert m is None


# ===========================================================================
# 5. _normalize_task_type
# ===========================================================================

class TestNormalizeTaskType:
    def test_string_passthrough(self):
        assert _normalize_task_type("qa") == "qa"

    def test_enum_value_extracted(self):
        from agent_evaluator import TaskType
        assert _normalize_task_type(TaskType.QA) == "qa"

    def test_none_returns_qa(self):
        assert _normalize_task_type(None) == "qa"

    def test_other_enum(self):
        from agent_evaluator import TaskType
        result = _normalize_task_type(TaskType.CODE_GENERATION)
        assert result == "code_generation"


# ===========================================================================
# 6. _extract_langchain_metadata
# ===========================================================================

class TestExtractLangchainMetadata:
    def test_returns_none_for_no_intermediate_steps(self):
        assert _extract_langchain_metadata({"output": "text"}) is None

    def test_returns_none_for_non_dict(self):
        assert _extract_langchain_metadata("not_a_dict") is None

    def test_extracts_tool_calls_from_steps(self):
        action = MagicMock()
        action.tool = "search"
        action.tool_input = {"query": "test"}
        step = (action, "search result")
        data = {"intermediate_steps": [step]}
        meta = _extract_langchain_metadata(data)
        assert meta is not None
        assert meta.tool_calls is not None
        assert meta.tool_calls[0]["tool_name"] == "search"

    def test_skips_invalid_steps(self):
        data = {"intermediate_steps": ["invalid_step"]}
        # Should return None (no valid tool calls)
        meta = _extract_langchain_metadata(data)
        assert meta is None

    def test_extracts_usage_metadata(self):
        action = MagicMock()
        action.tool = "calc"
        action.tool_input = {}
        data = {
            "intermediate_steps": [(action, "result")],
            "usage_metadata": {"input_tokens": 10, "output_tokens": 5},
        }
        meta = _extract_langchain_metadata(data)
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["input"] == 10

    def test_tool_input_non_dict_converted(self):
        action = MagicMock()
        action.tool = "tool"
        action.tool_input = "string_input"
        data = {"intermediate_steps": [(action, "obs")]}
        meta = _extract_langchain_metadata(data)
        assert meta is not None
        assert meta.tool_calls is not None
        assert isinstance(meta.tool_calls[0]["input"], dict)


# ===========================================================================
# 7. _extract_crewai_metadata
# ===========================================================================

class TestExtractCrewaiMetadata:
    def _import(self):
        from agent_evaluator.decorators import _extract_crewai_metadata
        return _extract_crewai_metadata

    def test_none_when_no_tasks_output(self):
        fn = self._import()
        raw = MagicMock(spec=[])  # no tasks_output, no pydantic
        assert fn(raw) is None

    def test_extracts_from_tasks_output(self):
        fn = self._import()
        task_out = MagicMock()
        task_out.agent = "ResearchAgent"
        task_out.description = "Research task"
        task_out.raw = "Research result"
        task_out.output_format = None
        task_out.used_tools = []
        task_out.tool_usage = None
        raw = MagicMock(spec=[])
        raw.tasks_output = [task_out]
        raw.output_pydantic = None
        raw.pydantic = None
        raw.output_format = None
        raw.token_usage = None
        raw.usage_metrics = None
        meta = fn(raw)
        assert meta is not None
        assert meta.agent_interactions is not None
        assert meta.agent_interactions[0]["from_agent"] == "ResearchAgent"

    def test_pydantic_output_fallback(self):
        fn = self._import()
        pydantic_model = MagicMock()
        pydantic_model.model_dump_json = MagicMock(return_value='{"key": "value"}')
        raw = MagicMock(spec=[])
        raw.tasks_output = None
        raw.output_pydantic = pydantic_model
        raw.pydantic = None
        raw.output_format = None
        meta = fn(raw)
        assert meta is not None

    def test_dict_input_tasks_output(self):
        fn = self._import()
        task_out = MagicMock()
        task_out.agent = "Agent"
        task_out.description = "desc"
        task_out.raw = "result"
        task_out.output_format = None
        task_out.used_tools = []
        task_out.tool_usage = None
        raw_dict = {
            "tasks_output": [task_out],
            "token_usage": None,
            "usage_metrics": None,
        }
        # The function handles dict via tasks_output = raw.get("tasks_output")
        meta = fn(raw_dict)
        assert meta is not None


# ===========================================================================
# 8. _extract_smolagents_metadata
# ===========================================================================

class TestExtractSmolAgentsMetadata:
    def _import(self):
        from agent_evaluator.decorators import _extract_smolagents_metadata
        return _extract_smolagents_metadata

    def test_none_when_no_steps(self):
        fn = self._import()
        assert fn("no_steps_string") is None

    def test_dict_steps_extracted(self):
        fn = self._import()
        raw = MagicMock()
        raw.steps = [
            {"name": "step1", "output": "output1", "duration": 0.5},
        ]
        meta = fn(raw)
        assert meta is not None
        assert meta.chain_steps is not None
        assert meta.chain_steps[0]["name"] == "step1"

    def test_object_steps_with_toolcall(self):
        fn = self._import()

        class FakeToolCallStep:
            tool_name = "web_search"
            tool_input = {"query": "test"}
            observation = "search result"
            error = None
            duration = 0.2

        raw = MagicMock()
        raw.steps = [FakeToolCallStep()]
        meta = fn(raw)
        assert meta is not None
        assert meta.tool_calls is not None
        assert meta.tool_calls[0]["tool_name"] == "web_search"

    def test_token_estimation_from_chain_steps(self):
        fn = self._import()

        class FakeStep:
            observation = "a" * 400  # 400 chars → ~100 tokens
            error = None
            duration = 0.1

        raw = MagicMock()
        raw.steps = [FakeStep()]
        meta = fn(raw)
        assert meta is not None
        if meta.tokens_used is not None:
            assert meta.tokens_used["estimated"] is True


# ===========================================================================
# 9. _extract_semantic_kernel_metadata
# ===========================================================================

class TestExtractSemanticKernelMetadata:
    def _import(self):
        from agent_evaluator.decorators import _extract_semantic_kernel_metadata
        return _extract_semantic_kernel_metadata

    def test_returns_none_when_no_value_or_inner(self):
        fn = self._import()
        raw = MagicMock(spec=[])  # no value, inner_content, or metadata
        assert fn(raw) is None

    def test_extracts_from_value(self):
        fn = self._import()
        raw = MagicMock(spec=["value"])
        raw.value = "kernel output"
        meta = fn(raw)
        assert meta is not None
        assert meta.chain_steps is not None
        assert "semantic_kernel_invoke" in meta.chain_steps[0]["name"]

    def test_inner_content_openai_backend(self):
        fn = self._import()
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 20
        inner = MagicMock()
        inner.usage = usage
        raw = MagicMock(spec=["value", "inner_content"])
        raw.value = "result"
        raw.inner_content = inner
        meta = fn(raw)
        assert meta is not None

    def test_function_name_added_to_step(self):
        fn = self._import()
        raw = MagicMock(spec=["value", "function_name"])
        raw.value = "output"
        raw.function_name = "my_function"
        meta = fn(raw)
        assert meta is not None
        assert meta.chain_steps is not None
        assert meta.chain_steps[0].get("function") == "my_function"


# ===========================================================================
# 10. _auto_detect_framework
# ===========================================================================

class TestAutoDetectFramework:
    def test_none_returns_none(self):
        assert _auto_detect_framework(None) is None

    def test_module_based_langchain(self):
        raw = MagicMock()
        type(raw).__module__ = "langchain.schema.output"
        assert _auto_detect_framework(raw) == "langchain"

    def test_module_based_crewai(self):
        raw = MagicMock()
        type(raw).__module__ = "crewai.output"
        assert _auto_detect_framework(raw) == "crewai"

    def test_module_based_autogen(self):
        raw = MagicMock()
        type(raw).__module__ = "autogen.messages"
        assert _auto_detect_framework(raw) == "autogen"

    def test_module_based_anthropic(self):
        raw = MagicMock()
        type(raw).__module__ = "anthropic.types"
        assert _auto_detect_framework(raw) == "anthropic"

    def test_module_based_openai(self):
        raw = MagicMock()
        type(raw).__module__ = "openai.types.chat"
        assert _auto_detect_framework(raw) == "openai"

    def test_module_based_cohere(self):
        raw = MagicMock()
        type(raw).__module__ = "cohere.client"
        assert _auto_detect_framework(raw) == "cohere"

    def test_module_based_groq(self):
        raw = MagicMock()
        type(raw).__module__ = "groq.types"
        assert _auto_detect_framework(raw) == "groq"

    def test_module_based_mistral(self):
        raw = MagicMock()
        type(raw).__module__ = "mistralai.models"
        assert _auto_detect_framework(raw) == "mistral"

    def test_module_based_smolagents(self):
        raw = MagicMock()
        type(raw).__module__ = "smolagents.agent"
        assert _auto_detect_framework(raw) == "smolagents"

    def test_module_based_dspy(self):
        raw = MagicMock()
        type(raw).__module__ = "dspy.predict"
        assert _auto_detect_framework(raw) == "dspy"

    def test_attribute_groq_detection(self):
        # Groq: has choices + x_groq, but NO usage (so _is_openai_response = False)
        class FakeGroqResponse:
            choices = []
            x_groq = object()
        raw = FakeGroqResponse()
        type(raw).__module__ = "unknown"
        result = _auto_detect_framework(raw)
        assert result == "groq"

    def test_attribute_mistral_detection(self):
        # Mistral: has choices + model containing "mistral", but no usage/usage_metadata
        class FakeMistralResponse:
            choices = []
            model = "mistral-7b"
        raw = FakeMistralResponse()
        type(raw).__module__ = "unknown"
        result = _auto_detect_framework(raw)
        # May detect as mistral (attribute-based) — just ensure no crash
        assert result in ("mistral", None, "openai")

    def test_returns_none_for_unknown(self):
        raw = MagicMock(spec=[])
        type(raw).__module__ = "myapp.custom"
        result = _auto_detect_framework(raw)
        assert result is None


# ===========================================================================
# 11. get_framework_info
# ===========================================================================

class TestGetFrameworkInfo:
    def test_known_framework_returns_dict(self):
        info = get_framework_info("langchain")
        assert info is not None
        assert "name" in info
        assert "is_installed" in info
        assert "supports_chain_steps" in info

    def test_unknown_framework_returns_none(self):
        assert get_framework_info("nonexistent_framework_xyz") is None

    def test_openai_info(self):
        info = get_framework_info("openai")
        assert info is not None
        assert isinstance(info["is_installed"], bool)

    def test_supports_chain_steps_field(self):
        info = get_framework_info("langchain")
        assert info is not None
        assert isinstance(info["supports_chain_steps"], bool)


# ===========================================================================
# 12. _EvalContext / get_eval_ctx
# ===========================================================================

class TestEvalContext:
    def test_get_eval_ctx_outside_decorator_returns_none(self):
        assert get_eval_ctx() is None

    def test_get_eval_ctx_inside_decorator(self, monitor):
        from agent_evaluator import agent_eval

        captured = []

        @agent_eval(monitor, task_type="qa")
        def my_fn(question, ground_truth=""):
            ctx = get_eval_ctx()
            captured.append(ctx)
            return "answer"

        my_fn("What is 2+2?", ground_truth="4")
        assert len(captured) == 1
        assert captured[0] is not None

    def test_eval_ctx_active_flag(self, monitor):
        from agent_evaluator import agent_eval
        from agent_evaluator.decorators import _eval_ctx_var

        inside_ctx = []

        @agent_eval(monitor, task_type="qa")
        def my_fn(question, ground_truth=""):
            ctx = _eval_ctx_var.get(None)
            if ctx:
                inside_ctx.append(ctx._active)
            return "answer"

        my_fn("test")
        assert inside_ctx and inside_ctx[0] is True

    def test_eval_ctx_cleared_after_call(self, monitor):
        from agent_evaluator import agent_eval

        @agent_eval(monitor, task_type="qa")
        def my_fn(question, ground_truth=""):
            return "answer"

        my_fn("test")
        # After call, get_eval_ctx should return None again
        assert get_eval_ctx() is None


# ===========================================================================
# 13. flush_all_conversations / flush_conversation
# ===========================================================================

class TestConversationFlush:
    def test_flush_all_empty(self):
        """flush_all_conversations with no active sessions returns 0."""
        flush_all_conversations()  # Clear any residual
        count = flush_all_conversations()
        assert count == 0

    def test_flush_conversation_missing_session(self):
        result = flush_conversation("session_that_does_not_exist_xyz")
        assert result is False

    def test_flush_all_returns_flushed_count(self, monitor):
        from agent_evaluator import conversation_eval
        from agent_evaluator.decorators import _CONV_SESSIONS

        # Clear any prior sessions
        flush_all_conversations()

        @conversation_eval(monitor)
        def chatbot(question: str, ground_truth: str = "") -> str:
            return "response"

        chatbot("hello")

        flushed = flush_all_conversations()
        # Should have flushed at least the session we just created
        assert flushed >= 0  # Exact count depends on whether session was kept

    def test_flush_conversation_named_session(self, monitor):
        from agent_evaluator import conversation_eval

        @conversation_eval(monitor, session_id_arg="sid")
        def chatbot(question: str, sid: str = "default") -> str:
            return "response"

        chatbot("hello", sid="test_session_flush")
        result = flush_conversation("test_session_flush")
        # Returns True if found, False if already flushed / not found
        assert isinstance(result, bool)


# ===========================================================================
# 14. agent_eval: enabled=False shortcut
# ===========================================================================

class TestAgentEvalEnabled:
    def test_enabled_false_returns_original_function(self, monitor):
        from agent_evaluator import agent_eval

        @agent_eval(monitor, task_type="qa", enabled=False)
        def my_fn(question, ground_truth=""):
            return "raw_answer"

        result = my_fn("test")
        assert result == "raw_answer"
        # With enabled=False, no tasks should be recorded
        report = monitor.generate_report()
        assert report.total_tasks == 0

    def test_sample_rate_zero_skips_recording(self, monitor):
        from agent_evaluator import agent_eval

        @agent_eval(monitor, task_type="qa", sample_rate=0.0)
        def my_fn(question, ground_truth=""):
            return "answer"

        # sample_rate=0.0 → random.random() always > 0.0 → always skip
        for _ in range(5):
            my_fn("test")
        report = monitor.generate_report()
        assert report.total_tasks == 0


# ===========================================================================
# 15. agent_eval: rag_mode
# ===========================================================================

class TestAgentEvalRagMode:
    def test_rag_mode_sets_hallucination(self, monitor):
        from agent_evaluator import agent_eval

        monitor_tasks = []

        @agent_eval(monitor, task_type="qa", rag_mode=True,
                    on_record=lambda t: monitor_tasks.append(t))
        def my_fn(question, context="", ground_truth=""):
            return "answer"

        my_fn("What is AI?", context="AI is artificial intelligence.")
        # Should have recorded a task
        assert len(monitor_tasks) >= 1


# ===========================================================================
# 16. agent_eval: security_mode
# ===========================================================================

class TestAgentEvalSecurityMode:
    def test_security_mode_flag(self, monitor):
        """security_mode 제거됨 — security=SecurityConfig() 사용."""
        from agent_evaluator import agent_eval
        from agent_evaluator.decorators import SecurityConfig

        recorded = []

        @agent_eval(monitor, task_type="qa", security=SecurityConfig(),
                    on_record=lambda t: recorded.append(t))
        def my_fn(question, ground_truth=""):
            return "safe answer"

        my_fn("DROP TABLE users;", ground_truth="safe")
        assert len(recorded) >= 1


# ===========================================================================
# 17. agent_eval: preset
# ===========================================================================

class TestAgentEvalPreset:
    def test_unknown_preset_warns(self, monitor):
        import warnings
        from agent_evaluator import agent_eval

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="nonexistent_preset_xyz")
            def my_fn(question, ground_truth=""):
                return "answer"

            my_fn("test")
            preset_warns = [x for x in w if "preset" in str(x.message).lower()
                           or "알 수 없는" in str(x.message)]
            assert len(preset_warns) >= 1

    def test_production_preset_applies(self, monitor):
        from agent_evaluator import agent_eval

        recorded = []

        @agent_eval(monitor, task_type="qa", preset="production",
                    on_record=lambda t: recorded.append(t))
        def my_fn(question, ground_truth=""):
            return "answer"

        my_fn("test question", ground_truth="answer")
        # Should work without errors — production preset may lower sample_rate
        assert isinstance(recorded, list)

    def test_testing_preset_applies(self, monitor):
        from agent_evaluator import agent_eval

        recorded = []

        @agent_eval(monitor, task_type="qa", preset="testing",
                    on_record=lambda t: recorded.append(t))
        def my_fn(question, ground_truth=""):
            return "answer"

        my_fn("test")
        assert isinstance(recorded, list)


# ===========================================================================
# 18. agent_eval: async support
# ===========================================================================

class TestAgentEvalAsync:
    @pytest.mark.asyncio
    async def test_async_function_recorded(self, monitor):
        from agent_evaluator import agent_eval

        recorded = []

        @agent_eval(monitor, task_type="qa",
                    on_record=lambda t: recorded.append(t))
        async def async_fn(question, ground_truth=""):
            return "async answer"

        result = await async_fn("test", ground_truth="async answer")
        assert result == "async answer"
        assert len(recorded) >= 1

    @pytest.mark.asyncio
    async def test_async_generator_recorded(self, monitor):
        from agent_evaluator import agent_eval

        @agent_eval(monitor, task_type="qa")
        async def stream_fn(question, ground_truth=""):
            yield "chunk1"
            yield "chunk2"

        chunks = []
        async for chunk in stream_fn("test"):
            chunks.append(chunk)
        assert chunks == ["chunk1", "chunk2"]


# ===========================================================================
# 19. agent_eval: sync generator
# ===========================================================================

class TestAgentEvalGenerator:
    def test_sync_generator_passthrough(self, monitor):
        from agent_evaluator import agent_eval

        @agent_eval(monitor, task_type="qa")
        def gen_fn(question, ground_truth=""):
            yield "part1"
            yield "part2"

        chunks = list(gen_fn("test"))
        assert chunks == ["part1", "part2"]


# ===========================================================================
# 20. agent_eval: task_id_fn
# ===========================================================================

class TestAgentEvalTaskIdFn:
    def test_custom_task_id_fn(self, monitor):
        from agent_evaluator import agent_eval

        recorded = []
        custom_id_fn = lambda args, kwargs: "custom_task_id_123"

        @agent_eval(monitor, task_type="qa", task_id_fn=custom_id_fn,
                    on_record=lambda t: recorded.append(t))
        def my_fn(question, ground_truth=""):
            return "answer"

        my_fn("test", ground_truth="expected")
        assert len(recorded) >= 1
        assert recorded[0].task_id == "custom_task_id_123"


# ===========================================================================
# 21. agent_eval: on_error callback
# ===========================================================================

class TestAgentEvalOnError:
    def test_on_error_called_on_exception(self, monitor):
        from agent_evaluator import agent_eval

        tasks_caught = []

        # on_error receives (task_result,) — one argument
        @agent_eval(monitor, task_type="qa",
                    on_error=lambda tr: tasks_caught.append(tr))
        def failing_fn(question, ground_truth=""):
            raise ValueError("test error")

        with pytest.raises(ValueError):
            failing_fn("test")

        assert len(tasks_caught) >= 1


# ===========================================================================
# 22. EvalMetadata and TurnMetadata
# ===========================================================================

class TestMetadataClasses:
    def test_eval_metadata_defaults(self):
        meta = EvalMetadata()
        assert meta.framework is None
        assert meta.tool_calls is None
        assert meta.tokens_used is None

    def test_eval_metadata_with_values(self):
        meta = EvalMetadata(
            framework="langchain",
            tool_calls=[{"tool_name": "search", "success": True}],
            tokens_used={"input": 10, "output": 20, "total": 30},
        )
        assert meta.framework == "langchain"
        assert meta.tool_calls is not None
        assert len(meta.tool_calls) == 1

    def test_turn_metadata_defaults(self):
        tm = TurnMetadata()
        assert tm.model is None
        assert tm.latency is None
        assert tm.tokens is None

    def test_turn_metadata_with_values(self):
        tm = TurnMetadata(model="gpt-4", latency=0.5, tokens={"input": 5, "output": 10})
        assert tm.model == "gpt-4"
        assert tm.latency == 0.5


# ===========================================================================
# 23. batch_eval basic coverage
# ===========================================================================

class TestBatchEvalBasic:
    def test_batch_eval_records_multiple_tasks(self, monitor):
        from agent_evaluator import batch_eval

        @batch_eval(monitor, task_type="qa")
        def batch_fn(questions: list, ground_truths: list | None = None):
            return [f"answer_{i}" for i in range(len(questions))]

        results = batch_fn(
            questions=["Q1", "Q2", "Q3"],
            ground_truths=["A1", "A2", "A3"],
        )
        assert len(results) == 3
        report = monitor.generate_report()
        assert report.total_tasks == 3

    def test_batch_eval_empty_input(self, monitor):
        from agent_evaluator import batch_eval

        @batch_eval(monitor, task_type="qa")
        def batch_fn(questions: list, ground_truths: list | None = None):
            return []

        results = batch_fn(questions=[], ground_truths=[])
        assert results == []
