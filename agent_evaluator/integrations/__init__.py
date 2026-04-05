"""
Framework integrations and metric adapters

v0.5.0: Removed deprecated legacy classes (EvaluatedCrew, LangChainEvaluationCallback, etc.)
All users should migrate to the new Evaluator classes:
- CrewAIEvaluator (instead of EvaluatedCrew)
- LangChainEvaluator + AdvancedLangChainCallback (instead of LangChainEvaluationCallback)
- LangGraphEvaluator (instead of LangGraphEvaluatedWorkflow)
- AutoGenEvaluator (instead of EvaluatedAutoGenAgent)

v0.6.5: Framework integration imports are now lazy to avoid loading heavy packages
(crewai, autogen, langchain, langgraph) at import time.

새 프레임워크 어댑터 추가 방법
-----------------------------
1. ``agent_evaluator/decorators.py`` 에 ``_extract_{framework}_metadata(raw)`` 함수 추가
   - ``EvalMetadata`` 또는 ``None`` 반환
2. ``_FRAMEWORK_ADAPTERS`` dict에 ``"{framework}": _extract_{framework}_metadata`` 추가
3. ``agent_evaluator/integrations/__init__.py`` 에 ``{framework}_eval`` 함수 추가 및 ``__all__`` 포함
4. ``agent_evaluator/__init__.py`` 에 ``{framework}_eval`` import 추가
5. 테스트: ``tests/`` 에 어댑터 단위 테스트 추가
"""

# ============================================================================
# Lightweight utility functions — 즉시 로드 (외부 의존성 없음)
# ============================================================================

from .framework_integrations import (
    check_framework_availability,
    get_installation_instructions,
    print_framework_status,
    ensure_security_trackers,
    extract_tools_from_framework_object,
    EvaluatorProtocol,
    to_graph_state,
    to_crew_inputs,
    to_task_string,
    infer_privilege_level,
)

# Metric adapters — LLM API 클라이언트 미사용, 즉시 로드 허용
from .metric_adapters import (
    DeepEvalAdapter,
    RagasAdapter,
    MetricAdapter,
)


# ============================================================================
# Heavy framework integrations — lazy loading
# ============================================================================

_LAZY = {
    "CrewAIEvaluator": (".crewai_integration", "CrewAIEvaluator"),
    "create_evaluated_crew": (".crewai_integration", "create_evaluated_crew"),
    "create_evaluated_crewai_agent": (".crewai_integration", "create_evaluated_crewai_agent"),
    "LangChainEvaluator": (".langchain_integration", "LangChainEvaluator"),
    "AdvancedLangChainCallback": (".langchain_integration", "AdvancedLangChainCallback"),
    "create_evaluated_langchain_agent": (".langchain_integration", "create_evaluated_langchain_agent"),
    "LangGraphEvaluator": (".langgraph_integration", "LangGraphEvaluator"),
    "create_evaluated_langgraph": (".langgraph_integration", "create_evaluated_langgraph"),
    "create_evaluated_langgraph_agent": (".langgraph_integration", "create_evaluated_langgraph_agent"),
    "AutoGenEvaluator": (".autogen_integration", "AutoGenEvaluator"),
    "create_evaluated_autogen_agent": (".autogen_integration", "create_evaluated_autogen_agent"),
    "LLMEvaluationHelper": (".llm_helpers", "LLMEvaluationHelper"),
    "AnthropicEvaluationHelper": (".llm_helpers", "AnthropicEvaluationHelper"),
    "LLMJudge": (".llm_judge", "LLMJudge"),
    # DSPy
    "DSPyEvaluator": (".dspy_integration", "DSPyEvaluator"),
    "DSPyMetricAdapter": (".dspy_integration", "DSPyMetricAdapter"),
    # PydanticAI
    "PydanticAIEvaluator": (".pydanticai_integration", "PydanticAIEvaluator"),
    "PydanticAITokenExtractor": (".pydanticai_integration", "PydanticAITokenExtractor"),
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib
        rel_module, attr = _LAZY[name]
        # Convert relative to absolute path
        abs_module = f"agent_evaluator.integrations{rel_module}"
        try:
            mod = importlib.import_module(abs_module)
            value = getattr(mod, attr)
        except (ImportError, AttributeError):
            value = None
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================================
# Task 3: 프레임워크 전용 데코레이터
# — @agent_eval + framework 어댑터 자동 주입 + 최적 기본값 설정
# ============================================================================

def langchain_eval(
    monitor: "Any",
    task_type: "Any" = "tool_use",
    **kwargs: "Any",
) -> "Any":
    """LangChain AgentExecutor 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="langchain")`` 의 편의 별칭이다.
    ``intermediate_steps`` 에서 ``tool_calls`` / ``chain_steps`` 를 자동 추출한다.

    Args:
        monitor: 결과를 기록할 PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"tool_use"``).
        **kwargs: :func:`agent_eval` 에 전달되는 추가 파라미터.

    Example::

        from agent_evaluator.integrations import langchain_eval

        @langchain_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return agent_executor.invoke({"input": question})
        # → intermediate_steps에서 tool_calls 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "langchain")
    return agent_eval(monitor, task_type, **kwargs)


def langgraph_eval(
    monitor: "Any",
    task_type: "Any" = "reasoning",
    **kwargs: "Any",
) -> "Any":
    """LangGraph 그래프 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="langgraph")`` 의 편의 별칭이다.
    ``messages`` 에서 ``state_transitions`` / ``graph_traversal`` / ``tool_calls`` 를 자동 추출한다.

    Args:
        monitor: 결과를 기록할 PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"reasoning"``).
        **kwargs: :func:`agent_eval` 에 전달되는 추가 파라미터.

    Example::

        from agent_evaluator.integrations import langgraph_eval

        @langgraph_eval(monitor, track_nodes=True)
        def my_graph(question: str, ground_truth: str = ""):
            return graph.invoke({"messages": [("user", question)]})
        # → state_transitions, graph_traversal 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "langgraph")
    # track_nodes는 어댑터 내부에서 처리하므로 agent_eval에 전달 전 제거
    kwargs.pop("track_nodes", None)
    return agent_eval(monitor, task_type, **kwargs)


def crewai_eval(
    monitor: "Any",
    task_type: "Any" = "planning",
    **kwargs: "Any",
) -> "Any":
    """CrewAI Crew 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="crewai")`` 의 편의 별칭이다.
    ``tasks_output`` 에서 ``agent_interactions`` 를 자동 추출한다.

    Args:
        monitor: 결과를 기록할 PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"planning"``).
        **kwargs: :func:`agent_eval` 에 전달되는 추가 파라미터.

    Example::

        from agent_evaluator.integrations import crewai_eval

        @crewai_eval(monitor)
        def my_crew_task(question: str, ground_truth: str = ""):
            return crew.kickoff({"topic": question})
        # → agent_interactions 자동 추출, AgentCoordinationTracker 활성화
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "crewai")
    return agent_eval(monitor, task_type, **kwargs)


def autogen_eval(
    monitor: "Any",
    task_type: "Any" = "coordination",
    **kwargs: "Any",
) -> "Any":
    """AutoGen Agent 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="autogen")`` 의 편의 별칭이다.
    ``messages`` / ``chat_history`` 에서 ``conversation_turns`` 를 자동 추출한다.
    AutoGen 0.4+ async API 는 ``@agent_eval_async`` 와 함께 사용한다.

    Args:
        monitor: 결과를 기록할 PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"coordination"``).
        **kwargs: :func:`agent_eval` 에 전달되는 추가 파라미터.

    Example::

        from agent_evaluator.integrations import autogen_eval

        @autogen_eval(monitor)
        def my_autogen_task(question: str, ground_truth: str = ""):
            result = agent.initiate_chat(user, message=question)
            return result.summary
        # → conversation_turns 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "autogen")
    return agent_eval(monitor, task_type, **kwargs)


def autogen_eval_async(
    monitor: "Any",
    task_type: "Any" = "coordination",
    **kwargs: "Any",
) -> "Any":
    """AutoGen 0.4+ async API 전용 비동기 데코레이터 (C4).

    ``@agent_eval_async(monitor, framework="autogen")`` 의 편의 별칭이다.
    AutoGen 0.4+ (autogen-agentchat 0.4+)는 async API로 전환되어 동기 wrapping이
    불가능하므로 ``agent_eval_async`` 를 사용한다.

    Args:
        monitor: 결과를 기록할 PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"coordination"``).
        **kwargs: :func:`agent_eval_async` 에 전달되는 추가 파라미터.

    Example::

        from agent_evaluator.integrations import autogen_eval_async

        @autogen_eval_async(monitor)
        async def my_autogen_task(question: str, ground_truth: str = ""):
            # AutoGen 0.4+ async API
            result = await Console(team.run_stream(task=question))
            return result.messages[-1].content if result.messages else ""
        # → conversation_turns 자동 추출
    """
    from agent_evaluator.decorators import agent_eval_async
    kwargs.setdefault("framework", "autogen")
    return agent_eval_async(monitor, task_type, **kwargs)


def dspy_eval(
    monitor: "Any",
    task_type: "Any" = "reasoning",
    **kwargs: "Any",
) -> "Any":
    """DSPy Program 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="dspy")`` 의 편의 별칭이다.
    DSPy Prediction 객체에서 ``chain_steps`` 와 토큰 사용량을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import dspy_eval

        @dspy_eval(monitor)
        def my_program(question: str, ground_truth: str = ""):
            return cot(question=question)
        # → chain_steps, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "dspy")
    return agent_eval(monitor, task_type, **kwargs)


def pydanticai_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """PydanticAI Agent 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="pydanticai")`` 의 편의 별칭이다.

    어댑터는 PydanticAI Agent 실행 결과에서 토큰 사용량을 자동 추출한다.
    우선 ``.all_messages()`` 를 탐색하고, 없으면 ``.messages`` 로 fallback한다.
    응답 객체의 ``usage`` / ``usage()`` 속성에서 입력·출력 토큰을 추출한다 (G2).

    .. note::
        PydanticAI v0.0.13+에서는 ``RunResult`` 대신 ``AgentRunResult`` 가 반환될 수
        있다. 두 경우 모두 동일하게 처리된다.

    Example::

        from agent_evaluator.integrations import pydanticai_eval

        @pydanticai_eval(monitor)
        async def my_agent(question: str, ground_truth: str = ""):
            result = await agent.run(question)
            return result.data
        # → tokens_used, chain_steps 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "pydanticai")
    return agent_eval(monitor, task_type, **kwargs)


def anthropic_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Anthropic SDK 응답 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="anthropic")`` 의 편의 별칭이다.
    Anthropic ``Message`` 객체의 ``content`` 리스트에서 ``tool_use`` 블록과
    ``usage`` 필드에서 토큰 사용량을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import anthropic_eval
        import anthropic

        client = anthropic.Anthropic()

        @anthropic_eval(monitor, task_type="tool_use")
        def my_agent(question: str, ground_truth: str = ""):
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": question}],
            )
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "anthropic")
    return agent_eval(monitor, task_type, **kwargs)


def openai_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """OpenAI SDK 응답 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="openai")`` 의 편의 별칭이다.
    ``ChatCompletion`` 객체의 ``tool_calls`` 와 ``usage`` 필드를 자동 추출한다.
    Assistants API의 ``required_action.submit_tool_outputs.tool_calls`` 도 지원한다.

    Example::

        from agent_evaluator.integrations import openai_eval
        from openai import OpenAI

        client = OpenAI()

        @openai_eval(monitor, task_type="tool_use")
        def my_agent(question: str, ground_truth: str = ""):
            return client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": question}],
            )
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "openai")
    return agent_eval(monitor, task_type, **kwargs)


def gemini_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Google Gemini SDK 응답 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="gemini")`` 의 편의 별칭이다.
    ``GenerateContentResponse`` 의 ``candidates[0].content.parts`` 에서
    ``function_call`` 파트와 ``usage_metadata`` 토큰을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import gemini_eval
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-1.5-flash")

        @gemini_eval(monitor, task_type="tool_use")
        def my_agent(question: str, ground_truth: str = ""):
            return model.generate_content(question)
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "gemini")
    return agent_eval(monitor, task_type, **kwargs)


def llamaindex_eval(
    monitor: "Any",
    task_type: "Any" = "information_retrieval",
    **kwargs: "Any",
) -> "Any":
    """LlamaIndex 쿼리 엔진 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="llamaindex")`` 의 편의 별칭이다.
    ``QueryBundle`` 응답 객체의 ``source_nodes`` 에서 검색 단계를 ``chain_steps`` 로,
    ``metadata`` 에서 토큰 사용량을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import llamaindex_eval

        @llamaindex_eval(monitor)
        def my_query_engine(question: str, ground_truth: str = ""):
            return query_engine.query(question)
        # → chain_steps (source_nodes), tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "llamaindex")
    kwargs.setdefault("context_arg", "context")
    return agent_eval(monitor, task_type, **kwargs)


def haystack_eval(
    monitor: "Any",
    task_type: "Any" = "information_retrieval",
    **kwargs: "Any",
) -> "Any":
    """Haystack 파이프라인 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="haystack")`` 의 편의 별칭이다.
    파이프라인 ``run()`` 결과 딕셔너리의 컴포넌트 출력을 ``chain_steps`` 로 자동 추출한다.

    Example::

        from agent_evaluator.integrations import haystack_eval
        from haystack import Pipeline

        pipeline = Pipeline()
        # pipeline.add_component(...)

        @haystack_eval(monitor)
        def my_pipeline(question: str, ground_truth: str = ""):
            return pipeline.run({"query": question})
        # → chain_steps (컴포넌트 출력) 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "haystack")
    return agent_eval(monitor, task_type, **kwargs)


def vertexai_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Google Vertex AI SDK 응답 평가 전용 데코레이터 (E2).

    ``@agent_eval(monitor, framework="vertexai")`` 의 편의 별칭이다.
    ``GenerateContentResponse`` 에서 ``function_call`` 파트와 ``usage_metadata`` 토큰을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import vertexai_eval
        import vertexai
        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel("gemini-1.5-flash-001")

        @vertexai_eval(monitor, task_type="tool_use")
        def my_agent(question: str, ground_truth: str = ""):
            return model.generate_content(question)
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "vertexai")
    return agent_eval(monitor, task_type, **kwargs)


def ollama_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Ollama API 응답 평가 전용 데코레이터 (E3).

    ``@agent_eval(monitor, framework="ollama")`` 의 편의 별칭이다.
    ``ollama.chat()`` / ``ollama.generate()`` 응답에서 tool_calls와 토큰 수를 자동 추출한다.

    Example::

        from agent_evaluator.integrations import ollama_eval
        import ollama

        @ollama_eval(monitor, task_type="qa")
        def my_agent(question: str, ground_truth: str = ""):
            return ollama.chat(
                model="llama3",
                messages=[{"role": "user", "content": question}],
            )
        # → tokens_used (prompt_eval_count/eval_count) 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "ollama")
    return agent_eval(monitor, task_type, **kwargs)


def cohere_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Cohere SDK 응답 평가 전용 데코레이터 (C1).

    ``@agent_eval(monitor, framework="cohere")`` 의 편의 별칭이다.
    Cohere v5+ ``NonStreamedChatResponse`` 에서 tool_calls 와 토큰 사용량을 자동 추출한다.
    ``pip install cohere`` 필요.

    Example::

        from agent_evaluator.integrations import cohere_eval
        import cohere

        co = cohere.Client()

        @cohere_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return co.chat(model="command-r-plus", message=question)
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "cohere")
    return agent_eval(monitor, task_type, **kwargs)


def groq_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Groq SDK 응답 평가 전용 데코레이터 (C2).

    ``@agent_eval(monitor, framework="groq")`` 의 편의 별칭이다.
    Groq 는 OpenAI 호환 형식을 사용하므로 OpenAI 메타데이터 추출기를 재사용한다.
    ``pip install groq`` 필요.

    Example::

        from agent_evaluator.integrations import groq_eval
        from groq import Groq

        client = Groq()

        @groq_eval(monitor, task_type="qa")
        def my_agent(question: str, ground_truth: str = ""):
            return client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": question}],
            )
        # → tool_calls, tokens_used 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "groq")
    return agent_eval(monitor, task_type, **kwargs)


def mistral_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Mistral AI SDK 응답 평가 전용 데코레이터 (C3).

    ``@agent_eval(monitor, framework="mistral")`` 의 편의 별칭이다.
    ``mistralai`` 라이브러리의 ``ChatCompletionResponse`` 에서 tool_calls 와 usage 를 자동 추출한다.
    ``pip install mistralai`` 필요.

    Example::

        from agent_evaluator.integrations import mistral_eval
        from mistralai import Mistral

        client = Mistral(api_key="...")

        @mistral_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": question}],
            )
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "mistral")
    return agent_eval(monitor, task_type, **kwargs)


def bedrock_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """AWS Bedrock Converse API 응답 평가 전용 데코레이터 (C4).

    ``@agent_eval(monitor, framework="bedrock")`` 의 편의 별칭이다.
    ``bedrock_runtime.converse()`` 응답 dict 에서 tool_calls 와 usage 를 자동 추출한다.

    Example::

        from agent_evaluator.integrations import bedrock_eval
        import boto3

        client = boto3.client("bedrock-runtime", region_name="us-east-1")

        @bedrock_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return client.converse(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                messages=[{"role": "user", "content": [{"text": question}]}],
            )
        # → toolUse, usage 자동 추출
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "bedrock")
    return agent_eval(monitor, task_type, **kwargs)


def smolagents_eval(
    monitor: "Any",
    task_type: "Any" = "reasoning",
    **kwargs: "Any",
) -> "Any":
    """HuggingFace smolagents 응답 평가 전용 데코레이터 (C5).

    ``@agent_eval(monitor, framework="smolagents")`` 의 편의 별칭이다.
    ``agent.run()`` 결과의 ``steps`` 필드에서 실행 단계를 ``chain_steps`` 로 자동 추출한다.
    ``pip install smolagents`` 필요.

    Example::

        from agent_evaluator.integrations import smolagents_eval
        from smolagents import CodeAgent

        agent = CodeAgent(tools=[...], model=...)

        @smolagents_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return agent.run(question)
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "smolagents")
    return agent_eval(monitor, task_type, **kwargs)


def semantic_kernel_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """Microsoft Semantic Kernel 응답 평가 전용 데코레이터 (C6).

    ``@agent_eval(monitor, framework="semantic_kernel")`` 의 편의 별칭이다.
    ``kernel.invoke()`` 결과의 ``value`` / ``inner_content`` 와 ``metadata`` 에서
    실행 정보를 자동 추출한다.
    ``pip install semantic-kernel`` 필요.

    Example::

        from agent_evaluator.integrations import semantic_kernel_eval
        import semantic_kernel as sk

        kernel = sk.Kernel()

        @semantic_kernel_eval(monitor)
        async def my_agent(question: str, ground_truth: str = ""):
            return await kernel.invoke(my_function, input=question)
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "semantic_kernel")
    return agent_eval(monitor, task_type, **kwargs)


def vllm_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """vLLM OpenAI-호환 API 응답 평가 전용 데코레이터 (F4).

    ``@agent_eval(monitor, framework="vllm")`` 의 편의 별칭이다.
    vLLM ``choices[0].message.tool_calls`` + ``usage.total_tokens`` 를 자동 추출한다.

    Example::

        from agent_evaluator.integrations import vllm_eval
        from openai import OpenAI

        client = OpenAI(base_url="http://localhost:8000/v1", api_key="token")

        @vllm_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return client.chat.completions.create(
                model="mistralai/Mistral-7B-Instruct-v0.2",
                messages=[{"role": "user", "content": question}],
            )
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "vllm")
    return agent_eval(monitor, task_type, **kwargs)


def huggingface_eval(
    monitor: "Any",
    task_type: "Any" = "qa",
    **kwargs: "Any",
) -> "Any":
    """HuggingFace transformers/trl 응답 평가 전용 데코레이터 (F4).

    ``@agent_eval(monitor, framework="huggingface")`` 의 편의 별칭이다.
    ``pipeline()`` list 응답, ``transformers.agents`` Agent 응답,
    ``generate()`` dict 응답을 자동 추출한다.

    Example::

        from agent_evaluator.integrations import huggingface_eval
        from transformers import pipeline

        pipe = pipeline("text-generation", model="gpt2")

        @huggingface_eval(monitor)
        def my_agent(question: str, ground_truth: str = ""):
            return pipe(question, max_new_tokens=100)
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "huggingface")
    return agent_eval(monitor, task_type, **kwargs)


__all__ = [
    # Lightweight utilities
    'check_framework_availability',
    'get_installation_instructions',
    'print_framework_status',
    'ensure_security_trackers',
    'extract_tools_from_framework_object',
    'EvaluatorProtocol',
    'to_graph_state',
    'to_crew_inputs',
    'to_task_string',
    'infer_privilege_level',

    # Metric adapters
    'DeepEvalAdapter',
    'RagasAdapter',
    'MetricAdapter',

    # Framework Integrations (lazy)
    'CrewAIEvaluator',
    'create_evaluated_crew',
    'create_evaluated_crewai_agent',
    'LangChainEvaluator',
    'AdvancedLangChainCallback',
    'create_evaluated_langchain_agent',
    'LangGraphEvaluator',
    'create_evaluated_langgraph',
    'create_evaluated_langgraph_agent',
    'AutoGenEvaluator',
    'create_evaluated_autogen_agent',
    'LLMEvaluationHelper',
    'AnthropicEvaluationHelper',
    'LLMJudge',

    # DSPy / PydanticAI (lazy)
    'DSPyEvaluator',
    'DSPyMetricAdapter',
    'PydanticAIEvaluator',
    'PydanticAITokenExtractor',

    # Task 3: 프레임워크 전용 데코레이터
    'langchain_eval',
    'langgraph_eval',
    'crewai_eval',
    'autogen_eval',
    'autogen_eval_async',  # C4: AutoGen 0.4+ async API 전용
    'dspy_eval',
    'pydanticai_eval',
    # LLM SDK 전용 데코레이터
    'anthropic_eval',
    'openai_eval',
    'gemini_eval',
    'llamaindex_eval',
    'haystack_eval',
    # Cloud / Local LLM 전용 데코레이터 (E2, E3)
    'vertexai_eval',
    'ollama_eval',
    # 추가 프레임워크 전용 데코레이터 (v0.7.7 C1-C6)
    'cohere_eval',
    'groq_eval',
    'mistral_eval',
    'bedrock_eval',
    'smolagents_eval',
    'semantic_kernel_eval',
    # F4: 신규 어댑터
    'vllm_eval',
    'huggingface_eval',
]
