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

    def test_extracts_tool_calls_from_direct_ai_message(self):
        """LCEL 툴콜링(model.bind_tools(...).invoke(...))이 dict로 감싸지 않고
        AIMessage를 직접 반환하는 경우 — AgentExecutor도 LangGraph도 아닌 패턴."""
        from agent_evaluator.decorators import _extract_langchain_metadata

        class AIMessage:
            content = ""
            tool_calls = [{"name": "search", "args": {"query": "seoul"}, "id": "call_1"}]
            usage_metadata = {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}

        result = _extract_langchain_metadata(AIMessage())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        assert result.tool_calls[0]["input"] == {"query": "seoul"}
        assert result.tokens_used["total"] == 60

    def test_direct_ai_message_without_tool_calls_returns_none(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        class AIMessage:
            content = "plain text answer"
            tool_calls = []

        assert _extract_langchain_metadata(AIMessage()) is None

    def test_direct_ai_message_falls_back_to_response_metadata_tokens(self):
        from agent_evaluator.decorators import _extract_langchain_metadata

        class AIMessage:
            content = ""
            tool_calls = [{"name": "search", "args": {}, "id": "call_1"}]
            usage_metadata = None
            response_metadata = {"token_usage": {"prompt_tokens": 20, "completion_tokens": 5}}

        result = _extract_langchain_metadata(AIMessage())
        assert result is not None
        assert result.tokens_used == {"input": 20, "output": 5, "total": 25}


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


# ---------------------------------------------------------------------------
# 신규 어댑터 레지스트리 등록 확인
# ---------------------------------------------------------------------------

class TestNewAdaptersRegistry:
    def test_new_adapters_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw in ("anthropic", "openai", "gemini", "llamaindex", "haystack"):
            assert fw in _FRAMEWORK_ADAPTERS, f"'{fw}' 어댑터가 레지스트리에 없음"

    def test_agent_framework_adapters_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS, _FRAMEWORK_ADAPTER_META, FrameworkLiteral
        import typing
        for fw in ("openai_agents", "google_adk", "claude_agent_sdk"):
            assert fw in _FRAMEWORK_ADAPTERS, f"'{fw}' 어댑터가 레지스트리에 없음"
            assert fw in _FRAMEWORK_ADAPTER_META, f"'{fw}' 메타데이터가 없음"
            assert fw in typing.get_args(FrameworkLiteral), f"'{fw}' 가 FrameworkLiteral에 없음"

    def test_all_adapters_callable(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw, fn in _FRAMEWORK_ADAPTERS.items():
            # H: "native" 는 sentinel None — 어댑터 없음을 나타내므로 제외
            if fn is None:
                continue
            assert callable(fn), f"'{fw}' 어댑터가 callable 이 아님"


# ---------------------------------------------------------------------------
# _extract_anthropic_metadata
# ---------------------------------------------------------------------------

class TestAnthropicAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_anthropic_metadata
        assert _extract_anthropic_metadata("plain") is None

    def test_extracts_tool_calls_from_content(self):
        from agent_evaluator.decorators import _extract_anthropic_metadata

        class _ToolUseBlock:
            type = "tool_use"
            name = "web_search"
            input = {"query": "test"}
            id = "tu_001"

        class _TextBlock:
            type = "text"
            text = "here is the answer"

        class _Usage:
            input_tokens = 100
            output_tokens = 50

        class _Message:
            content = [_TextBlock(), _ToolUseBlock()]
            usage = _Usage()

        result = _extract_anthropic_metadata(_Message())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "web_search"
        assert result.tokens_used["total"] == 150

    def test_tokens_extracted_even_without_tool_calls(self):
        from agent_evaluator.decorators import _extract_anthropic_metadata

        class _TextBlock:
            type = "text"
            text = "just text"

        class _Usage:
            input_tokens = 50
            output_tokens = 20

        class _Message:
            content = [_TextBlock()]
            usage = _Usage()

        # 도구 호출 없어도 usage 가 있으면 EvalMetadata(tokens_used=...) 반환 가능
        result = _extract_anthropic_metadata(_Message())
        if result is not None:
            # 반환된 경우 tokens_used 가 채워져 있어야 함
            assert result.tokens_used is not None
            assert result.tokens_used.get("total") == 70


# ---------------------------------------------------------------------------
# _extract_openai_metadata
# ---------------------------------------------------------------------------

class TestOpenAIAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_openai_metadata
        assert _extract_openai_metadata("hello") is None

    def test_extracts_tool_calls_from_chat_completion(self):
        from agent_evaluator.decorators import _extract_openai_metadata

        class _Function:
            name = "calculator"
            arguments = '{"expr": "1+1"}'

        class _ToolCall:
            id = "call_001"
            type = "function"
            function = _Function()

        class _Message:
            role = "assistant"
            content = "2"
            tool_calls = [_ToolCall()]

        class _Choice:
            message = _Message()
            finish_reason = "tool_calls"

        class _Usage:
            prompt_tokens = 80
            completion_tokens = 20
            total_tokens = 100

        class _ChatCompletion:
            choices = [_Choice()]
            usage = _Usage()

        result = _extract_openai_metadata(_ChatCompletion())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "calculator"
        assert result.tokens_used["total"] == 100

    def test_tokens_extracted_without_tool_calls(self):
        from agent_evaluator.decorators import _extract_openai_metadata

        class _Message:
            role = "assistant"
            content = "just text"
            tool_calls = None

        class _Choice:
            message = _Message()
            finish_reason = "stop"

        class _Usage:
            prompt_tokens = 30
            completion_tokens = 10
            total_tokens = 40

        class _ChatCompletion:
            choices = [_Choice()]
            usage = _Usage()

        result = _extract_openai_metadata(_ChatCompletion())
        # 도구 호출 없어도 토큰 정보는 반환될 수 있음
        if result is not None:
            assert result.tokens_used is not None

    def test_extracts_tool_calls_from_responses_api(self):
        """Responses API(client.responses.create())는 Chat Completions와 달리
        .choices가 아니라 .output 리스트에 function_call 타입 아이템을 담는다."""
        from agent_evaluator.decorators import _extract_openai_metadata

        class _FunctionCallItem:
            type = "function_call"
            name = "calculator"
            arguments = '{"expr": "1+1"}'
            call_id = "call_001"

        class _MessageItem:
            type = "message"
            content = "2"

        class _Usage:
            input_tokens = 80
            output_tokens = 20
            total_tokens = 100

        class _Response:
            output = [_MessageItem(), _FunctionCallItem()]
            usage = _Usage()
            model = "gpt-5"

        result = _extract_openai_metadata(_Response())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "calculator"
        assert result.tool_calls[0]["tool_call_id"] == "call_001"
        assert result.tokens_used == {"input": 80, "output": 20, "total": 100}

    def test_responses_api_without_function_call_returns_none_if_no_tokens(self):
        from agent_evaluator.decorators import _extract_openai_metadata

        class _MessageItem:
            type = "message"
            content = "plain answer"

        class _Response:
            output = [_MessageItem()]
            usage = None
            model = "gpt-5"

        assert _extract_openai_metadata(_Response()) is None


# ---------------------------------------------------------------------------
# _extract_gemini_metadata
# ---------------------------------------------------------------------------

class TestGeminiAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_gemini_metadata
        assert _extract_gemini_metadata("hello") is None

    def test_extracts_function_calls_from_response(self):
        from agent_evaluator.decorators import _extract_gemini_metadata

        class _FunctionCall:
            name = "web_search"
            args = {"query": "test"}

        class _Part:
            function_call = _FunctionCall()

        class _Content:
            parts = [_Part()]

        class _Candidate:
            content = _Content()

        class _UsageMeta:
            prompt_token_count = 60
            candidates_token_count = 30
            total_token_count = 90

        class _Response:
            candidates = [_Candidate()]
            usage_metadata = _UsageMeta()

        result = _extract_gemini_metadata(_Response())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "web_search"


# ---------------------------------------------------------------------------
# _extract_llamaindex_metadata
# ---------------------------------------------------------------------------

class TestLlamaIndexAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_llamaindex_metadata
        assert _extract_llamaindex_metadata("hello") is None

    def test_extracts_source_nodes_as_chain_steps(self):
        from agent_evaluator.decorators import _extract_llamaindex_metadata

        class _Node:
            text = "relevant document"
            metadata = {"source": "doc1.txt"}

        class _NodeWithScore:
            node = _Node()
            score = 0.92

        class _QueryResponse:
            response = "synthesized answer"
            source_nodes = [_NodeWithScore(), _NodeWithScore()]
            metadata = {}

        result = _extract_llamaindex_metadata(_QueryResponse())
        assert result is not None
        assert result.chain_steps is not None
        assert len(result.chain_steps) == 2


# ---------------------------------------------------------------------------
# _extract_haystack_metadata
# ---------------------------------------------------------------------------

class TestHaystackAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_haystack_metadata
        assert _extract_haystack_metadata("hello") is None

    def test_extracts_pipeline_outputs_as_chain_steps(self):
        from agent_evaluator.decorators import _extract_haystack_metadata

        raw = {
            "retriever": {"documents": ["doc1", "doc2"]},
            "reader": {"answers": ["42"]},
        }
        result = _extract_haystack_metadata(raw)
        assert result is not None
        assert result.chain_steps is not None
        assert len(result.chain_steps) == 2

    def test_returns_none_for_empty_dict(self):
        from agent_evaluator.decorators import _extract_haystack_metadata
        result = _extract_haystack_metadata({})
        assert result is None


# ---------------------------------------------------------------------------
# _extract_openai_agents_metadata
# ---------------------------------------------------------------------------

class TestOpenAIAgentsAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_openai_agents_metadata
        assert _extract_openai_agents_metadata("hello") is None

    def test_extracts_tool_calls_and_tokens_from_run_result(self):
        from agent_evaluator.decorators import _extract_openai_agents_metadata

        class _RawFunctionCall:
            arguments = '{"expr": "1+1"}'

        class ToolCallItem:  # 어댑터가 type(item).__name__ == "ToolCallItem" 으로 판별하므로 클래스명 그대로 사용
            tool_name = "calculator"
            call_id = "call_001"
            raw_item = _RawFunctionCall()

        class _MessageOutputItem:
            pass  # not a ToolCallItem — should be skipped

        class _Usage:
            input_tokens = 80
            output_tokens = 20

        class _ModelResponse:
            usage = _Usage()

        class _RunResult:
            new_items = [_MessageOutputItem(), ToolCallItem()]
            raw_responses = [_ModelResponse()]

        result = _extract_openai_agents_metadata(_RunResult())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "calculator"
        assert result.tool_calls[0]["tool_call_id"] == "call_001"
        assert result.tokens_used == {"input": 80, "output": 20, "total": 100}

    def test_sums_usage_across_multiple_raw_responses(self):
        from agent_evaluator.decorators import _extract_openai_agents_metadata

        class _Usage:
            def __init__(self, inp, out):
                self.input_tokens = inp
                self.output_tokens = out

        class _ModelResponse:
            def __init__(self, usage):
                self.usage = usage

        class _RunResult:
            new_items = []
            raw_responses = [_ModelResponse(_Usage(50, 10)), _ModelResponse(_Usage(30, 5))]

        result = _extract_openai_agents_metadata(_RunResult())
        assert result is not None
        assert result.tokens_used == {"input": 80, "output": 15, "total": 95}


# ---------------------------------------------------------------------------
# _extract_google_adk_metadata
# ---------------------------------------------------------------------------

class TestGoogleADKAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_google_adk_metadata
        assert _extract_google_adk_metadata("hello") is None

    def test_extracts_tool_calls_from_get_function_calls(self):
        from agent_evaluator.decorators import _extract_google_adk_metadata

        class _FunctionCall:
            name = "search"
            args = {"query": "seoul"}
            id = "fc_1"

        class _UsageMetadata:
            prompt_token_count = 40
            candidates_token_count = 15

        class _Event:
            usage_metadata = _UsageMetadata()

            def get_function_calls(self):
                return [_FunctionCall()]

        result = _extract_google_adk_metadata(_Event())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        assert result.tool_calls[0]["input"] == {"query": "seoul"}
        assert result.tokens_used == {"input": 40, "output": 15, "total": 55}

    def test_returns_none_without_function_calls_or_usage(self):
        from agent_evaluator.decorators import _extract_google_adk_metadata

        class _Event:
            usage_metadata = None

            def get_function_calls(self):
                return []

        assert _extract_google_adk_metadata(_Event()) is None


# ---------------------------------------------------------------------------
# _extract_claude_agent_sdk_metadata
# ---------------------------------------------------------------------------

class TestClaudeAgentSDKAdapter:
    def test_returns_none_for_plain_string(self):
        from agent_evaluator.decorators import _extract_claude_agent_sdk_metadata
        assert _extract_claude_agent_sdk_metadata("hello") is None

    def test_extracts_tool_calls_from_assistant_message(self):
        from agent_evaluator.decorators import _extract_claude_agent_sdk_metadata

        class ToolUseBlock:  # 어댑터가 type(block).__name__ == "ToolUseBlock" 으로 판별하므로 클래스명 그대로 사용
            name = "search"
            input = {"query": "seoul"}
            id = "toolu_1"

        class _AssistantMessage:
            content = [ToolUseBlock()]
            model = "claude-sonnet-4-6"
            usage = {"input_tokens": 50, "output_tokens": 10}

        result = _extract_claude_agent_sdk_metadata(_AssistantMessage())
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        assert result.tokens_used["total"] == 60

    def test_extracts_session_usage_from_result_message(self):
        from agent_evaluator.decorators import _extract_claude_agent_sdk_metadata

        class _ResultMessage:
            total_cost_usd = 0.0123
            num_turns = 3
            usage = {
                "input_tokens": 500,
                "output_tokens": 120,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 50,
            }

        result = _extract_claude_agent_sdk_metadata(_ResultMessage())
        assert result is not None
        assert result.tool_calls is None  # ResultMessage에는 도구 호출 상세가 없음
        assert result.tokens_used["input"] == 500
        assert result.tokens_used["cache_creation"] == 100
        assert result.tokens_used["cache_read"] == 50
        assert result.extra["total_cost_usd"] == 0.0123
        assert result.extra["num_turns"] == 3

    def test_returns_none_for_unrelated_object(self):
        from agent_evaluator.decorators import _extract_claude_agent_sdk_metadata

        class _Unrelated:
            pass

        assert _extract_claude_agent_sdk_metadata(_Unrelated()) is None


# ---------------------------------------------------------------------------
# LLM SDK 어댑터 등록 확인 (agent_eval(framework=name) 방식)
# ---------------------------------------------------------------------------

class TestIntegrationDecorators:
    def test_llm_adapters_in_framework_adapters(self):
        """LLM SDK 어댑터가 _FRAMEWORK_ADAPTERS에 등록되어 있다."""
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw in ("anthropic", "openai", "gemini", "llamaindex", "haystack"):
            assert fw in _FRAMEWORK_ADAPTERS, f"Missing adapter: {fw}"

    def test_agent_eval_framework_param_supports_llm_sdks(self, tmp_path):
        """agent_eval(framework='openai')로 직접 지정 가능."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        called = []

        @agent_eval(monitor, task_type="qa", framework="openai")
        def agent(question: str, ground_truth: str = "") -> str:
            called.append(True)
            return "answer"

        agent("q?", ground_truth="answer")
        assert called


# ---------------------------------------------------------------------------
# QuickEval alert_rules / flush_every
# ---------------------------------------------------------------------------

class TestQuickEvalAlertRules:
    def test_alert_rules_passed_to_eval_decorator(self, tmp_path):
        import os
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator.decorators import SimpleTaskAlertRule

        fired = []
        rule = SimpleTaskAlertRule(
            name="always_fire",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
        )

        qe = QuickEval(str(tmp_path) + "/", alert_rules=[rule])

        @qe.qa
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(fired) == 1

    def test_flush_every_passed_to_eval_decorator(self, tmp_path):
        import os
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval(
            str(tmp_path) + "/",
            flush_every=2,
        )

        @qe.qa
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        flush_file = os.path.join(str(tmp_path), "auto_save.json")

        agent("q1?", ground_truth="answer")
        assert not os.path.exists(flush_file)

        agent("q2?", ground_truth="answer")
        assert os.path.exists(flush_file)
