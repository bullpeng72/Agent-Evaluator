"""
Framework integrations and metric adapters

v0.8.0: Direct-API wrapper classes (LangChainEvaluator, LangGraphEvaluator, CrewAIEvaluator,
AutoGenEvaluator, create_evaluated_*, LLMHelper, ClaudeHelper) 제거.
모든 프레임워크 통합은 데코레이터 방식으로 수행:
    @agent_eval(monitor, framework="langchain"|"langgraph"|"crewai"|"autogen"|...)

프레임워크별 편의 데코레이터 별칭:
    langchain_eval, langgraph_eval, crewai_eval, autogen_eval,
    dspy_eval, pydanticai_eval, anthropic_eval, openai_eval, ...

새 프레임워크 어댑터 추가 방법
-----------------------------
1. ``agent_evaluator/decorators.py`` 에 ``_extract_{framework}_metadata(raw)`` 함수 추가
   - ``EvalMetadata`` 또는 ``None`` 반환
2. ``_FRAMEWORK_ADAPTERS`` dict에 ``"{framework}": _extract_{framework}_metadata`` 추가
3. ``agent_evaluator/integrations/__init__.py`` 에 ``{framework}_eval`` 추가 및 ``__all__`` 포함
4. 테스트: ``tests/`` 에 어댑터 단위 테스트 추가
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# ============================================================================
# Lightweight utility functions — 즉시 로드 (외부 의존성 없음)
# ============================================================================
from .framework_integrations import (
    EvaluatorProtocol,
    check_framework_availability,
    ensure_security_trackers,
    extract_tools_from_framework_object,
    get_installation_instructions,
    infer_privilege_level,
    print_framework_status,
    to_crew_inputs,
    to_graph_state,
    to_task_string,
)

# Metric adapters — LLM API 클라이언트 미사용, 즉시 로드 허용
from .metric_adapters import (
    DeepEvalAdapter,
    MetricAdapter,
    RagasAdapter,
)

# ============================================================================
# Heavy framework integrations — lazy loading
# ============================================================================

_LAZY = {
    # LLM Judge
    "LLMJudge": (".llm_judge", "LLMJudge"),
    # DSPy
    "DSPyEvaluator": (".dspy_integration", "DSPyEvaluator"),
    "DSPyMetricAdapter": (".dspy_integration", "DSPyMetricAdapter"),
    # PydanticAI
    "PydanticAIEvaluator": (".pydanticai_integration", "PydanticAIEvaluator"),
    "PydanticAITokenExtractor": (".pydanticai_integration", "PydanticAITokenExtractor"),
}


# __all__에 포함된 lazy-import 이름들을 정적 분석기(Pylance/pyright)가
# reportUnsupportedDunderAll 없이 인식하도록 TYPE_CHECKING 시점에만 바인딩한다
# — 런타임 지연 로딩(__getattr__)은 그대로 유지된다(TYPE_CHECKING은 항상 False).
if TYPE_CHECKING:
    from .dspy_integration import DSPyEvaluator, DSPyMetricAdapter
    from .llm_judge import LLMJudge
    from .pydanticai_integration import PydanticAIEvaluator, PydanticAITokenExtractor


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
    import functools

    from agent_evaluator.decorators import agent_eval as _agent_eval

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

    # LLM Judge / DSPy / PydanticAI (lazy)
    'LLMJudge',
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
