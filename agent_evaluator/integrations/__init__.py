"""
Framework integrations and metric adapters

v0.5.0: Removed deprecated legacy classes (EvaluatedCrew, LangChainEvaluationCallback, etc.)
All users should migrate to the new Evaluator classes:
- CrewAIEvaluator (instead of EvaluatedCrew)
- LangChainEvaluator + AdvancedLangChainCallback (instead of LangChainEvaluationCallback)
- LangGraphEvaluator (instead of LangGraphEvaluatedWorkflow)
- AutoGenEvaluator (instead of EvaluatedAutoGenAgent)
"""

# ============================================================================
# Framework Integrations - Full 3-Layer Support
# ============================================================================

# CrewAI Integration
try:
    from .crewai_integration import (
        CrewAIEvaluator,
        create_evaluated_crew,
    )
    _CREWAI_EXPORTS = ['CrewAIEvaluator', 'create_evaluated_crew']
except ImportError:
    _CREWAI_EXPORTS = []

# LangChain Integration
try:
    from .langchain_integration import (
        LangChainEvaluator,
        AdvancedLangChainCallback,
        create_evaluated_langchain_agent,
    )
    _LANGCHAIN_EXPORTS = ['LangChainEvaluator', 'AdvancedLangChainCallback', 'create_evaluated_langchain_agent']
except ImportError:
    _LANGCHAIN_EXPORTS = []

# LangGraph Integration
try:
    from .langgraph_integration import (
        LangGraphEvaluator,
        create_evaluated_langgraph,
    )
    _LANGGRAPH_EXPORTS = ['LangGraphEvaluator', 'create_evaluated_langgraph']
except ImportError:
    _LANGGRAPH_EXPORTS = []

# AutoGen Integration
try:
    from .autogen_integration import (
        AutoGenEvaluator,
        create_evaluated_autogen_agent,
    )
    _AUTOGEN_EXPORTS = ['AutoGenEvaluator', 'create_evaluated_autogen_agent']
except ImportError:
    _AUTOGEN_EXPORTS = []


# ============================================================================
# Utility Functions
# ============================================================================

try:
    from .framework_integrations import (
        check_framework_availability,
        get_installation_instructions,
        print_framework_status,
        ensure_security_trackers,
        extract_tools_from_framework_object,
    )
    _UTILITY_EXPORTS = [
        'check_framework_availability',
        'get_installation_instructions',
        'print_framework_status',
        'ensure_security_trackers',
        'extract_tools_from_framework_object',
    ]
except ImportError:
    _UTILITY_EXPORTS = []


# ============================================================================
# Metric Adapters
# ============================================================================

from .metric_adapters import (
    DeepEvalAdapter,
    RagasAdapter,
    MetricAdapter,
)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Framework Integrations
    *_CREWAI_EXPORTS,
    *_LANGCHAIN_EXPORTS,
    *_LANGGRAPH_EXPORTS,
    *_AUTOGEN_EXPORTS,

    # Metric adapters
    'DeepEvalAdapter',
    'RagasAdapter',
    'MetricAdapter',

    # Utility functions
    *_UTILITY_EXPORTS,
]