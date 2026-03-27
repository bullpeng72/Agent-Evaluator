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
]
