"""
Agent Evaluator SDK v0.7.0
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

__version__ = "0.7.0"
__author__ = "Sungwoo Kim"

# Exception hierarchy (경량 — 외부 의존성 없음)
from .exceptions import (
    AgentEvaluatorError,
    ValidationError,
    FrameworkNotInstalledError,
    MetricComputationError,
    ConfigurationError,
    StorageError,
    InvalidOperationError,
)

# Config & init helpers (cli.main 임포트 없이 제공 — import-time side-effect 없음)
from .config import get_settings, init_from_app, load_env

# Framework-agnostic utilities (경량)
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

# BaseTracker ABC — 커스텀 트래커 구현 시 상속
from .core.trackers.base import BaseTracker

# Core (numpy/pandas를 사용하지만 SDK의 핵심이므로 즉시 로드)
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
# F3: MultimodalMetricsTracker
from .core.trackers.layer1 import MultimodalMetricsTracker

# Import context managers
from .core.monitor_context import evaluation_session, hybrid_evaluation_session, async_evaluation_session

# Decorator-based evaluation (Opik @track 스타일)
from .decorators import (
    agent_eval,
    batch_eval,
    conversation_eval,
    flush_conversation,
    flush_all_conversations,
    eval_context,
    EvalDecorator,
    EvalMetadata,
    TurnMetadata,
    get_eval_ctx,
    # Task 5: SimpleTaskAlertRule + E6: AlertRuleBuilder
    SimpleTaskAlertRule,
    AlertRuleBuilder,
    # Task 1: 프레임워크 어댑터 레지스트리 (고급 사용자용)
    _FRAMEWORK_ADAPTERS,
    # C6: 어댑터 메타데이터 레지스트리
    _FRAMEWORK_ADAPTER_META,
    get_framework_info,
    # H1: 사전 정의된 파라미터 묶음
    AGENT_EVAL_PRESETS,
    # 항목 W: preset 런타임 등록
    register_preset,
    # M1: 프레임워크 타입 힌트 (IDE 자동완성 지원)
    FrameworkLiteral,
)

# Task 6: QuickEval — 원스톱 평가 Facade
from .quick_eval import QuickEval

# Import helpers with simplified names
from .helpers.taskresult_helpers import create_taskresult_from_execution as create_taskresult

# Conversation Evaluation (Phase 1-C)
from .core.trackers.conversation import ConversationSession, ConversationMetrics, ConversationTurn

# Feedback Tracker (Phase 2-C)
from .core.trackers.feedback import ImplicitFeedbackTracker

# Anomaly Detection (Phase 3-B)
from .anomaly import AnomalyDetector, AnomalyEvent

# Cost Optimization (Phase 3-C)
from .cost import CostTracker, AdaptivePolicy, SamplingStage

# ---------------------------------------------------------------------------
# Lazy imports — 무거운 패키지(litellm, crewai, autogen, langchain, etc.)는
# 실제로 접근할 때만 로드한다. `from agent_evaluator import X` 도 동작한다.
# ---------------------------------------------------------------------------

_LAZY_IMPORTS = {
    # Streaming Evaluator (Phase 2-A) — requires serve extras (fastapi/starlette)
    "StreamingEvaluator": ("agent_evaluator.streaming.evaluator", "StreamingEvaluator"),
    "AgentEvalMiddleware": ("agent_evaluator.streaming.middleware", "AgentEvalMiddleware"),
    # Alert System (Phase 2-B)
    "AlertEngine": ("agent_evaluator.alerts.engine", "AlertEngine"),
    "AlertRule": ("agent_evaluator.alerts.engine", "AlertRule"),
    "AlertEvent": ("agent_evaluator.alerts.engine", "AlertEvent"),
    "SlackHandler": ("agent_evaluator.alerts.handlers", "SlackHandler"),
    "WebhookHandler": ("agent_evaluator.alerts.handlers", "WebhookHandler"),
    "EmailHandler": ("agent_evaluator.alerts.handlers", "EmailHandler"),
    # Golden Set Builder (Phase 3-A)
    "GoldenSetBuilder": ("agent_evaluator.datasets.builder", "GoldenSetBuilder"),
    # OTEL / 운영 모니터링 (Phase 4 / v0.7.x)
    "setup_otel": ("agent_evaluator.core.otel", "setup_otel"),
    "OTELProvider": ("agent_evaluator.core.otel.provider", "OTELProvider"),
    # Hybrid Monitor
    "HybridPerformanceMonitor": ("agent_evaluator.core.hybrid_monitor", "HybridPerformanceMonitor"),
    "ExtendedTaskResult": ("agent_evaluator.core.hybrid_monitor", "ExtendedTaskResult"),
    "HybridEvaluationReport": ("agent_evaluator.core.hybrid_monitor", "HybridEvaluationReport"),
    # LLM Helpers
    "LLMHelper": ("agent_evaluator.integrations.llm_helpers", "LLMEvaluationHelper"),
    "ClaudeHelper": ("agent_evaluator.integrations.llm_helpers", "AnthropicEvaluationHelper"),
    # LLM Judge
    "LLMJudge": ("agent_evaluator.integrations.llm_judge", "LLMJudge"),
    # Framework Evaluator classes
    "LangChainEvaluator": ("agent_evaluator.integrations.langchain_integration", "LangChainEvaluator"),
    "LangGraphEvaluator": ("agent_evaluator.integrations.langgraph_integration", "LangGraphEvaluator"),
    "CrewAIEvaluator": ("agent_evaluator.integrations.crewai_integration", "CrewAIEvaluator"),
    "AutoGenEvaluator": ("agent_evaluator.integrations.autogen_integration", "AutoGenEvaluator"),
    # Framework factory functions
    "create_evaluated_langchain_agent": (
        "agent_evaluator.integrations.langchain_integration",
        "create_evaluated_langchain_agent",
    ),
    "create_evaluated_langgraph": (
        "agent_evaluator.integrations.langgraph_integration",
        "create_evaluated_langgraph",
    ),
    "create_evaluated_langgraph_agent": (
        "agent_evaluator.integrations.langgraph_integration",
        "create_evaluated_langgraph_agent",
    ),
    "create_evaluated_crew": (
        "agent_evaluator.integrations.crewai_integration",
        "create_evaluated_crew",
    ),
    "create_evaluated_crewai_agent": (
        "agent_evaluator.integrations.crewai_integration",
        "create_evaluated_crewai_agent",
    ),
    "create_evaluated_autogen_agent": (
        "agent_evaluator.integrations.autogen_integration",
        "create_evaluated_autogen_agent",
    ),
    # Task 7: DSPy 통합
    "DSPyEvaluator": ("agent_evaluator.integrations.dspy_integration", "DSPyEvaluator"),
    "DSPyMetricAdapter": ("agent_evaluator.integrations.dspy_integration", "DSPyMetricAdapter"),
    # Task 7: PydanticAI 통합
    "PydanticAIEvaluator": ("agent_evaluator.integrations.pydanticai_integration", "PydanticAIEvaluator"),
    "PydanticAITokenExtractor": ("agent_evaluator.integrations.pydanticai_integration", "PydanticAITokenExtractor"),
}

# 모듈 이름 → extras 이름 매핑 (FrameworkNotInstalledError 메시지용)
_FRAMEWORK_EXTRA_MAP = {
    "StreamingEvaluator": "serve",
    "AgentEvalMiddleware": "serve",
    "AlertEngine": "serve",
    "AlertRule": "serve",
    "AlertEvent": "serve",
    "SlackHandler": "serve",
    "WebhookHandler": "serve",
    "EmailHandler": "serve",
    "GoldenSetBuilder": "all",
    "LangChainEvaluator": "langchain",
    "LangGraphEvaluator": "langchain",
    "CrewAIEvaluator": "crewai",
    "AutoGenEvaluator": "autogen",
    "create_evaluated_langchain_agent": "langchain",
    "create_evaluated_langgraph": "langchain",
    "create_evaluated_langgraph_agent": "langchain",
    "create_evaluated_crew": "crewai",
    "create_evaluated_crewai_agent": "crewai",
    "create_evaluated_autogen_agent": "autogen",
    "LLMHelper": "llm",
    "ClaudeHelper": "llm",
    "LLMJudge": "llm",
    "HybridPerformanceMonitor": "eval",
    "ExtendedTaskResult": "eval",
    "HybridEvaluationReport": "eval",
    "setup_otel": "otel",
    "OTELProvider": "otel",
}


def __getattr__(name: str):  # noqa: N807
    """Lazy-load heavy modules on first attribute access."""
    if name in _LAZY_IMPORTS:
        import importlib

        module_path, attr = _LAZY_IMPORTS[name]
        try:
            module = importlib.import_module(module_path)
            value = getattr(module, attr)
            # 모듈 네임스페이스에 캐시하여 이후 접근은 즉시 반환
            globals()[name] = value
            return value
        except ImportError as exc:
            extra = _FRAMEWORK_EXTRA_MAP.get(name, "all")
            # optional dep 미설치 → FrameworkNotInstalledError (None 반환 제거)
            raise FrameworkNotInstalledError(name, extra) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Exceptions
    'AgentEvaluatorError',
    'ValidationError',
    'FrameworkNotInstalledError',
    'MetricComputationError',
    'ConfigurationError',
    'StorageError',
    'InvalidOperationError',

    # Core
    'PerformanceMonitor',
    'TaskResult',
    'TaskType',
    'EvaluationReport',

    # Hybrid Monitor (lazy)
    'HybridPerformanceMonitor',
    'ExtendedTaskResult',
    'HybridEvaluationReport',

    # Helpers (simplified API)
    'create_taskresult',  # Simplified name
    'evaluation_session',  # Context manager
    'hybrid_evaluation_session',  # Context manager
    'async_evaluation_session',  # Async context manager
    'agent_eval',               # Decorator (sync+async+retry+framework 통합)
    'batch_eval',               # Decorator for List[str] batch functions
    'conversation_eval',        # Decorator for multi-turn conversation
    'flush_conversation',       # Flush conversation session
    'flush_all_conversations',  # Flush all active conversation sessions
    'eval_context',             # Context manager for non-decoratable code (sync+async)
    'EvalDecorator',            # Factory for shared monitor/defaults (Gap N)
    'EvalMetadata',             # Metadata injection via tuple return
    'TurnMetadata',             # Turn-level metadata for conversation_eval
    'get_eval_ctx',             # ContextVar context accessor (async-safe)
    'get_framework_info',       # C6: 어댑터 메타데이터 조회
    'LLMHelper',  # Simplified name (lazy)
    'ClaudeHelper',  # Simplified name (lazy)

    # Framework Evaluator classes (lazy — None if optional dep not installed)
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

    # BaseTracker ABC (for custom tracker implementation)
    'BaseTracker',

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

    # LLM Judge (lazy)
    'LLMJudge',

    # Conversation Evaluation (Phase 1-C)
    'ConversationSession',
    'ConversationMetrics',
    'ConversationTurn',

    # Feedback Tracker (Phase 2-C)
    'ImplicitFeedbackTracker',

    # Streaming Evaluator (Phase 2-A — lazy)
    'StreamingEvaluator',
    'AgentEvalMiddleware',

    # Alert System (Phase 2-B — lazy)
    'AlertEngine',
    'AlertRule',
    'AlertEvent',
    'SlackHandler',
    'WebhookHandler',
    'EmailHandler',

    # Anomaly Detection (Phase 3-B)
    'AnomalyDetector',
    'AnomalyEvent',

    # Cost Optimization (Phase 3-C)
    'CostTracker',
    'AdaptivePolicy',
    'SamplingStage',

    # Golden Set Builder (Phase 3-A — lazy)
    'GoldenSetBuilder',

    # Transparency
    'TestTransparencyManager',
    'AnnotationType',
    'TestStepStatus',

    # Framework Factory Functions (lazy — None if optional dep not installed)
    'create_evaluated_langchain_agent',
    'create_evaluated_langgraph',
    'create_evaluated_langgraph_agent',   # from_compiled 모드 (compiled_graph 첫 인자)
    'create_evaluated_crew',
    'create_evaluated_crewai_agent',       # create_evaluated_crew 네이밍 통일 별칭
    'create_evaluated_autogen_agent',
]
