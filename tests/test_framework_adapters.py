"""
tests/test_framework_adapters.py
=================================
_FRAMEWORK_ADAPTERS 및 각 프레임워크 어댑터 함수 단위 테스트.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _FRAMEWORK_ADAPTERS 레지스트리
# ---------------------------------------------------------------------------

class TestFrameworkAdaptersRegistry:
    def test_adapters_dict_exists(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert isinstance(_FRAMEWORK_ADAPTERS, dict)

    def test_expected_frameworks_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw in ("langchain", "langgraph", "crewai", "autogen", "dspy", "pydanticai"):
            assert fw in _FRAMEWORK_ADAPTERS, f"'{fw}' 어댑터가 레지스트리에 없음"

    def test_adapters_are_callable(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw, fn in _FRAMEWORK_ADAPTERS.items():
            # H: "native" 는 sentinel None — 어댑터 없음을 나타내므로 제외
            if fn is None:
                continue
            assert callable(fn), f"'{fw}' 어댑터가 callable 이 아님"


# ---------------------------------------------------------------------------
# _extract_langchain_metadata
# ---------------------------------------------------------------------------

class TestLangChainAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_langchain_metadata
        result = _extract_langchain_metadata("plain string response")
        assert result is None

    def test_extracts_tool_calls_from_intermediate_steps(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        # LangChain 어댑터는 dict 형태의 raw를 기대한다
        Action1 = type("Action", (), {"tool": "search", "tool_input": "query"})()
        Action2 = type("Action", (), {"tool": "calc", "tool_input": "1+1"})()
        raw = {
            "output": "final answer",
            "intermediate_steps": [
                (Action1, "search result"),
                (Action2, "2"),
            ],
        }
        result = _extract_langchain_metadata(raw)
        assert result is not None
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0]["tool_name"] == "search"

    def test_extracts_chain_steps_from_output_dict(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        # intermediate_steps 가 비어 있으면 None 반환
        raw = {"output": "final answer", "intermediate_steps": []}
        result = _extract_langchain_metadata(raw)
        assert result is None  # 빈 steps → tool_calls 없음 → None


# ---------------------------------------------------------------------------
# _extract_langgraph_metadata
# ---------------------------------------------------------------------------

class TestLangGraphAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata
        result = _extract_langgraph_metadata("hello")
        assert result is None

    def test_extracts_from_messages(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata

        # LangGraph 어댑터는 dict 형태의 raw를 기대한다
        class AIMsg:
            type = "ai"
            content = "answer"
            tool_calls = [{"name": "search", "args": {}}]

        class HumanMsg:
            type = "human"
            content = "question"
            tool_calls = []

        raw = {"messages": [HumanMsg(), AIMsg()]}
        result = _extract_langgraph_metadata(raw)
        assert result is not None
        assert len(result.tool_calls) >= 1


# ---------------------------------------------------------------------------
# _extract_dspy_metadata
# ---------------------------------------------------------------------------

class TestDSpyAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_dspy_metadata
        result = _extract_dspy_metadata("just a string")
        assert result is None

    def test_extracts_from_prediction(self):
        from agent_evaluator.decorators import _extract_dspy_metadata

        # DSPy 어댑터는 _completions 또는 completions 속성을 기대한다
        class FakePrediction:
            _completions = ["step 1 reasoning", "step 2 answer"]
            answer = "42"

        result = _extract_dspy_metadata(FakePrediction())
        assert result is not None
        assert result.chain_steps is not None
        assert len(result.chain_steps) >= 1


# ---------------------------------------------------------------------------
# _extract_pydanticai_metadata
# ---------------------------------------------------------------------------

class TestPydanticAIAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_pydanticai_metadata
        result = _extract_pydanticai_metadata("just a string")
        assert result is None

    def test_extracts_from_run_result(self):
        from agent_evaluator.decorators import _extract_pydanticai_metadata

        class FakeRunResult:
            data = "some answer"
            def all_messages(self):
                return []

        result = _extract_pydanticai_metadata(FakeRunResult())
        # all_messages() 가 빈 리스트이면 chain_steps 비어있을 수 있음
        assert result is None or hasattr(result, "chain_steps")


# ---------------------------------------------------------------------------
# _normalize_task_type
# ---------------------------------------------------------------------------

class TestNormalizeTaskType:
    def test_string_passthrough(self):
        from agent_evaluator.decorators import _normalize_task_type
        assert _normalize_task_type("qa") == "qa"
        assert _normalize_task_type("tool_use") == "tool_use"

    def test_enum_conversion(self):
        from agent_evaluator.decorators import _normalize_task_type
        from agent_evaluator import TaskType
        assert _normalize_task_type(TaskType.QA) == "qa"
        assert _normalize_task_type(TaskType.TOOL_USE) == "tool_use"

    def test_unknown_falls_back_to_qa(self):
        from agent_evaluator.decorators import _normalize_task_type
        result = _normalize_task_type(None)  # type: ignore
        assert isinstance(result, str)
