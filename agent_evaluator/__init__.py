"""
Agent Evaluator SDK v0.6.2
===========================

Production-ready evaluation framework for AI agents.

Quick Start (Basic):
    >>> from agent_evaluator import PerformanceMonitor, create_taskresult
    >>>
    >>> monitor = PerformanceMonitor()
    >>> task = create_taskresult(
    ...     task_id="task_001",
    ...     question="What is the capital?",
    ...     response="Seoul",
    ...     ground_truth="Seoul",
    ...     execution_time=1.2
    ... )
    >>> monitor.record_task(task)
    >>> monitor.save_to_file("results.json")  # Auto-includes full report!

Quick Start (Context Manager):
    >>> from agent_evaluator import evaluation_session
    >>>
    >>> with evaluation_session("results.json") as monitor:
    ...     task = create_taskresult(...)
    ...     monitor.record_task(task)
    >>> # Auto-saved!

Quick Start (LLM Integration):
    >>> from agent_evaluator import PerformanceMonitor, LLMHelper
    >>>
    >>> monitor = PerformanceMonitor()
    >>> llm = LLMHelper(monitor)
    >>> task = llm.evaluate_openai("qa_001", "What is AI?", ground_truth="...")
    >>> # Auto-recorded in monitor!
"""

__version__ = "0.6.4"
__author__ = "Sungwoo Kim"

# Import from core module
# Config & init helpers (cli.main 임포트 없이 제공 — import-time side-effect 없음)
from .config import get_settings, init_from_app, load_env
from .integrations.framework_integrations import (
    EvaluatorProtocol,
    to_graph_state,
    to_crew_inputs,
    to_task_string,
)

# Transparency
from .utils.transparency_manager import (
    AnnotationType,
    TestStepStatus,
    TestTransparencyManager,
)
from .core.agent_evaluator import (
    AccuracyEvaluator,
    AgentCoordinationTracker,
    EvaluationReport,
    HallucinationDetector,
    # Security Metrics (Layer 1 & 2)
    infer_privilege_level,
    InputSanitizationTracker,
    LatencyTracker,
    OutputLeakageDetector,
    PerformanceMonitor,
    PrivilegeEscalationDetector,
    ResponseQualityEvaluator,
    RetryCorrectionTracker,
    TaskCompletionTracker,
    TaskResult,
    TaskType,
    TokenEconomyTracker,
    ToolAuthorizationTracker,
    ToolCallAnalyzer,
    ToolChainAttackDetector,
    ToolSelectionTracker,
    WorkflowExecutionTracker,
)

# Import Hybrid Monitor (with external library integration)
from .core.hybrid_monitor import (
    ExtendedTaskResult,
    HybridEvaluationReport,
    HybridPerformanceMonitor,
)

# Import context managers
from .core.monitor_context import evaluation_session, hybrid_evaluation_session

# Import helpers with simplified names
from .helpers.taskresult_helpers import create_taskresult_from_execution as create_taskresult
from .integrations.llm_helpers import (
    AnthropicEvaluationHelper as ClaudeHelper,
)

# Import LLM helpers
from .integrations.llm_helpers import (
    LLMEvaluationHelper as LLMHelper,
)

# LLM Judge (Phase 1-A)
from .integrations.llm_judge import LLMJudge

# Conversation Evaluation (Phase 1-C)
from .core.trackers.conversation import ConversationSession, ConversationMetrics, ConversationTurn

# Framework Evaluator classes + EvaluatorProtocol (optional deps — graceful fallback)
try:
    from .integrations.langchain_integration import LangChainEvaluator
except ImportError:
    LangChainEvaluator = None  # type: ignore[assignment]

try:
    from .integrations.langgraph_integration import LangGraphEvaluator
except ImportError:
    LangGraphEvaluator = None  # type: ignore[assignment]

try:
    from .integrations.crewai_integration import CrewAIEvaluator
except ImportError:
    CrewAIEvaluator = None  # type: ignore[assignment]

try:
    from .integrations.autogen_integration import AutoGenEvaluator
except ImportError:
    AutoGenEvaluator = None  # type: ignore[assignment]

# Framework factory functions (optional deps — graceful fallback on ImportError)
try:
    from .integrations.langchain_integration import create_evaluated_langchain_agent
except ImportError:
    create_evaluated_langchain_agent = None  # type: ignore[assignment]

try:
    from .integrations.langgraph_integration import (
        create_evaluated_langgraph,
        create_evaluated_langgraph_agent,
    )
except ImportError:
    create_evaluated_langgraph = None  # type: ignore[assignment]
    create_evaluated_langgraph_agent = None  # type: ignore[assignment]

try:
    from .integrations.crewai_integration import (
        create_evaluated_crew,
        create_evaluated_crewai_agent,
    )
except ImportError:
    create_evaluated_crew = None  # type: ignore[assignment]
    create_evaluated_crewai_agent = None  # type: ignore[assignment]

try:
    from .integrations.autogen_integration import create_evaluated_autogen_agent
except ImportError:
    create_evaluated_autogen_agent = None  # type: ignore[assignment]

__all__ = [
    # Core
    'PerformanceMonitor',
    'TaskResult',
    'TaskType',
    'EvaluationReport',

    # Hybrid Monitor
    'HybridPerformanceMonitor',
    'ExtendedTaskResult',
    'HybridEvaluationReport',

    # Helpers (simplified API)
    'create_taskresult',  # Simplified name
    'evaluation_session',  # Context manager
    'hybrid_evaluation_session',  # Context manager
    'LLMHelper',  # Simplified name
    'ClaudeHelper',  # Simplified name

    # Framework Evaluator classes (None if optional dep not installed)
    'LangChainEvaluator',
    'LangGraphEvaluator',
    'CrewAIEvaluator',
    'AutoGenEvaluator',

    # Framework-agnostic protocol & input adapters
    'EvaluatorProtocol',
    'to_graph_state',   # str → LangGraph state dict
    'to_crew_inputs',   # str → CrewAI inputs dict
    'to_task_string',   # Any → str (LangChain/AutoGen용)

    # Config & setup
    'load_env',       # Smart .env loader (priority: system > CWD .env > global)
    'get_settings',   # Settings singleton
    'init_from_app',  # Programmatic init for library callers

    # Trackers (for advanced users)
    'TaskCompletionTracker',
    'AccuracyEvaluator',
    'HallucinationDetector',
    'ResponseQualityEvaluator',
    'LatencyTracker',
    'TokenEconomyTracker',
    'ToolCallAnalyzer',
    'RetryCorrectionTracker',
    'ToolSelectionTracker',
    'AgentCoordinationTracker',
    'WorkflowExecutionTracker',

    # Security Metrics
    'infer_privilege_level',
    'InputSanitizationTracker',
    'OutputLeakageDetector',
    'ToolAuthorizationTracker',
    'PrivilegeEscalationDetector',
    'ToolChainAttackDetector',

    # LLM Judge
    'LLMJudge',

    # Conversation Evaluation (Phase 1-C)
    'ConversationSession',
    'ConversationMetrics',
    'ConversationTurn',

    # Transparency
    'TestTransparencyManager',
    'AnnotationType',
    'TestStepStatus',

    # Framework Factory Functions (None if optional dep not installed)
    'create_evaluated_langchain_agent',
    'create_evaluated_langgraph',
    'create_evaluated_langgraph_agent',   # from_compiled 모드 (compiled_graph 첫 인자)
    'create_evaluated_crew',
    'create_evaluated_crewai_agent',       # create_evaluated_crew 네이밍 통일 별칭
    'create_evaluated_autogen_agent',
]
