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


# ---------------------------------------------------------------------------
# Framework-specific decorator aliases
# e.g. langchain_eval(monitor) == agent_eval(monitor, framework="langchain")
# ---------------------------------------------------------------------------

def _make_framework_eval(framework_name: str):
    """Return a partial of agent_eval with framework pre-set."""
    from agent_evaluator.decorators import agent_eval as _agent_eval
    import functools

    @functools.wraps(_agent_eval)
    def _eval(monitor, task_type="qa", **kwargs):
        kwargs.setdefault("framework", framework_name)
        return _agent_eval(monitor, task_type=task_type, **kwargs)

    _eval.__name__ = f"{framework_name}_eval"
    _eval.__qualname__ = f"{framework_name}_eval"
    return _eval


langchain_eval = _make_framework_eval("langchain")
langgraph_eval = _make_framework_eval("langgraph")
crewai_eval = _make_framework_eval("crewai")
autogen_eval = _make_framework_eval("autogen")
dspy_eval = _make_framework_eval("dspy")
pydanticai_eval = _make_framework_eval("pydanticai")
anthropic_eval = _make_framework_eval("anthropic")
openai_eval = _make_framework_eval("openai")
gemini_eval = _make_framework_eval("gemini")
llamaindex_eval = _make_framework_eval("llamaindex")
haystack_eval = _make_framework_eval("haystack")


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

    # Framework-specific decorator aliases
    'langchain_eval',
    'langgraph_eval',
    'crewai_eval',
    'autogen_eval',
    'dspy_eval',
    'pydanticai_eval',
    'anthropic_eval',
    'openai_eval',
    'gemini_eval',
    'llamaindex_eval',
    'haystack_eval',
]
