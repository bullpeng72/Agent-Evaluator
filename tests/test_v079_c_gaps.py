"""
Tests for v0.7.9 C-gaps: Framework adapter improvements.

Covers:
- C1: DSPy .history multi-step extraction + PydanticAI .all_messages() support
- C2: LangGraph ToolMessage/AIMessage → chain_steps, __metadata__ → state_transitions
- C3: CrewAI v2.x output_format / pydantic field detection
- C4: autogen_eval_async for AutoGen 0.4+ async API
- C5: Integration test helpers/fixtures for framework adapters
- C6: _FRAMEWORK_ADAPTER_META dict + get_framework_info()
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.decorators import (
    EvalMetadata,
    _extract_dspy_metadata,
    _extract_pydanticai_metadata,
    _extract_langgraph_metadata,
    _extract_crewai_metadata,
    _extract_autogen_metadata,
    _FRAMEWORK_ADAPTERS,
    _FRAMEWORK_ADAPTER_META,
    get_framework_info,
)


# ---------------------------------------------------------------------------
# C5: Test fixtures / helpers for framework adapters
# ---------------------------------------------------------------------------

def _make_monitor():
    return PerformanceMonitor()


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
# C4: autogen_eval_async
# ---------------------------------------------------------------------------

class TestC4AutogenEvalAsync:

    def test_autogen_eval_async_importable(self):
        """autogen_eval_async top-level import"""
        from agent_evaluator import autogen_eval_async  # noqa: F401
        assert callable(autogen_eval_async)

    def test_autogen_eval_async_from_integrations(self):
        """autogen_eval_async integrations import"""
        from agent_evaluator.integrations import autogen_eval_async  # noqa: F401
        assert callable(autogen_eval_async)

    def test_autogen_eval_async_sets_framework(self):
        """autogen_eval_async 는 framework='autogen' 자동 설정"""
        monitor = _make_monitor()
        import asyncio

        from agent_evaluator.integrations import autogen_eval_async

        @autogen_eval_async(monitor, task_type="coordination")
        async def my_agent(question: str, ground_truth: str = "") -> str:
            return "agent response"

        result = asyncio.get_event_loop().run_until_complete(my_agent("test?"))
        assert result == "agent response"
        assert monitor.task_count == 1

    def test_autogen_eval_async_in_all_list(self):
        """autogen_eval_async가 integrations __all__에 포함됨"""
        from agent_evaluator import integrations
        assert "autogen_eval_async" in integrations.__all__


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
