"""
Agent Evaluator SDK v0.9.4
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

Quick Start (Decorator):
    >>> from agent_evaluator import PerformanceMonitor
    >>> from agent_evaluator.decorators import agent_eval
    >>>
    >>> monitor = PerformanceMonitor()
    >>>
    >>> @agent_eval(monitor, task_type="qa", framework="openai")
    ... def my_agent(question, ground_truth=""):
    ...     return client.chat.completions.create(...)
    >>> # Metrics auto-recorded on every call!
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "1.0.0-rc2"
__author__ = "Sungwoo Kim"

# Exception hierarchy (경량 — 외부 의존성 없음)
# Anomaly Detection (Phase 3-B)
from .anomaly import AnomalyDetector, AnomalyEvent

# Config & init helpers (cli.main 임포트 없이 제공 — import-time side-effect 없음)
from .config import get_settings, init_from_app, load_env

# Core (numpy/pandas를 사용하지만 SDK의 핵심이므로 즉시 로드)
from .core.agent_evaluator import (
    AccuracyEvaluator,
    AgentCoordinationTracker,
    EvaluationReport,
    HallucinationDetector,
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
    # Security Metrics (Layer 1 & 2)
    infer_privilege_level,
)

# Import context managers
from .core.monitor_context import (
    async_evaluation_session,
    evaluation_session,
    hybrid_evaluation_session,
)

# BaseTracker ABC — 커스텀 트래커 구현 시 상속
from .core.trackers.base import BaseTracker

# Conversation Evaluation (Phase 1-C)
from .core.trackers.conversation import ConversationMetrics, ConversationSession, ConversationTurn

# Cost Optimization (Phase 3-C)
from .cost import AdaptivePolicy, CostTracker, SamplingStage

# Decorator-based evaluation (Opik @track 스타일)
from .decorators import (
    # C6: 어댑터 메타데이터 레지스트리
    _FRAMEWORK_ADAPTER_META,
    # Task 1: 프레임워크 어댑터 레지스트리 (고급 사용자용)
    _FRAMEWORK_ADAPTERS,
    # H1: 사전 정의된 파라미터 묶음
    AGENT_EVAL_PRESETS,
    # v0.9.3+: Phase 4 Harness Config 데이터클래스
    AgentRoleConfig,
    AlertRuleBuilder,
    ComplianceConfig,
    ConflictResolutionConfig,
    ConsensusConfig,
    ContextRetentionConfig,
    ContextWindowConfig,
    CostPredictabilityConfig,
    DeadlockConfig,
    EfficiencyConfig,
    ErrorDiagnosisConfig,
    EvalDecorator,
    EvalMetadata,
    ExplainabilityConfig,
    FaultToleranceConfig,
    # M1: 프레임워크 타입 힌트 (IDE 자동완성 지원)
    FrameworkLiteral,
    GoalAlignmentConfig,
    GracefulDegradationConfig,
    # v0.9.5+: Phase 6 Harness Config 데이터클래스
    IdempotencyConfig,
    # v0.9.0+: Phase 1 Harness Config 데이터클래스
    InstructionConfig,
    KnowledgeRetentionConfig,
    LatencyAttributionConfig,
    # LLMJudgeConfig — LLM-as-Judge 파라미터 묶음 (v0.8.2+)
    LLMJudgeConfig,
    LoopDetectionConfig,
    ObservabilityConfig,
    PlanConfig,
    PropagationConfig,
    ReproducibilityConfig,
    ResourceBudgetConfig,
    # RetryConfig — 재시도 파라미터 묶음
    RetryConfig,
    RetryConsistencyConfig,
    # v0.9.2+: Phase 3 Harness Config 데이터클래스
    ScopeConfig,
    # SecurityConfig — 보안 메트릭 파라미터 묶음 (v0.8.3+)
    SecurityConfig,
    # Task 5: SimpleTaskAlertRule + E6: AlertRuleBuilder
    SimpleTaskAlertRule,
    # v0.9.1+: 신규 Harness Config 데이터클래스
    SLAConfig,
    StateConsistencyConfig,
    SubtaskConfig,
    ThreatResponseConfig,
    ThreatSeverityConfig,
    # v0.9.4+: Phase 5 Harness Config 데이터클래스
    ToolParameterSafetyConfig,
    TTFTVariabilityConfig,
    TurnMetadata,
    agent_eval,
    batch_eval,
    conversation_eval,
    eval_context,
    flush_all_conversations,
    flush_conversation,
    get_eval_ctx,
    get_framework_info,
    # 항목 W: preset 런타임 등록
    register_preset,
)
from .exceptions import (
    AgentEvaluatorError,
    ConfigurationError,
    FrameworkNotInstalledError,
    InvalidOperationError,
    MetricComputationError,
    StorageError,
    ValidationError,
)

# Import helpers with simplified names
from .helpers.taskresult_helpers import create_taskresult_from_execution as create_taskresult

# Framework-agnostic utilities (경량)
from .integrations.framework_integrations import (
    EvaluatorProtocol,
    to_crew_inputs,
    to_graph_state,
    to_task_string,
)

# Task 6: QuickEval — 원스톱 평가 Facade
from .quick_eval import CompareResult, HarnessEvaluationGate, QuickEval

# Transparency
from .utils.transparency_manager import (
    AnnotationType,
    TestStepStatus,
    TestTransparencyManager,
)

# ---------------------------------------------------------------------------
# Lazy imports — 무거운 패키지(litellm, crewai, autogen, langchain, etc.)는
# 실제로 접근할 때만 로드한다. `from agent_evaluator import X` 도 동작한다.
# ---------------------------------------------------------------------------

_LAZY_IMPORTS = {
    # Feedback Tracker (Phase 2-C) — optional, graceful degradation without it
    "ImplicitFeedbackTracker": ("agent_evaluator.core.trackers.feedback", "ImplicitFeedbackTracker"),
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
    # LLM Judge
    "LLMJudge": ("agent_evaluator.integrations.llm_judge", "LLMJudge"),
    # Task 7: DSPy 통합
    "DSPyEvaluator": ("agent_evaluator.integrations.dspy_integration", "DSPyEvaluator"),
    "DSPyMetricAdapter": ("agent_evaluator.integrations.dspy_integration", "DSPyMetricAdapter"),
    # Task 7: PydanticAI 통합
    "PydanticAIEvaluator": ("agent_evaluator.integrations.pydanticai_integration", "PydanticAIEvaluator"),
    "PydanticAITokenExtractor": ("agent_evaluator.integrations.pydanticai_integration", "PydanticAITokenExtractor"),
}

# 모듈 이름 → extras 이름 매핑 (FrameworkNotInstalledError 메시지용)
_FRAMEWORK_EXTRA_MAP = {
    "ImplicitFeedbackTracker": "dev",   # core package — always available; lazy for import-time perf
    "StreamingEvaluator": "serve",
    "AgentEvalMiddleware": "serve",
    "AlertEngine": "serve",
    "AlertRule": "serve",
    "AlertEvent": "serve",
    "SlackHandler": "serve",
    "WebhookHandler": "serve",
    "EmailHandler": "serve",
    "GoldenSetBuilder": "all",
    "LLMJudge": "llm",
    "HybridPerformanceMonitor": "eval",
    "ExtendedTaskResult": "eval",
    "HybridEvaluationReport": "eval",
    "setup_otel": "otel",
    "OTELProvider": "otel",
}


# __all__에 포함된 lazy-import 이름들을 정적 분석기(Pylance/pyright)가
# reportUnsupportedDunderAll 없이 인식하도록 TYPE_CHECKING 시점에만 바인딩한다
# — 런타임 지연 로딩(__getattr__)은 그대로 유지된다(TYPE_CHECKING은 항상 False).
if TYPE_CHECKING:
    from agent_evaluator.alerts.engine import AlertEngine, AlertEvent, AlertRule
    from agent_evaluator.alerts.handlers import EmailHandler, SlackHandler, WebhookHandler
    from agent_evaluator.core.hybrid_monitor import (
        ExtendedTaskResult,
        HybridEvaluationReport,
        HybridPerformanceMonitor,
    )
    from agent_evaluator.core.trackers.feedback import ImplicitFeedbackTracker
    from agent_evaluator.datasets.builder import GoldenSetBuilder
    from agent_evaluator.integrations.llm_judge import LLMJudge
    from agent_evaluator.streaming.evaluator import StreamingEvaluator
    from agent_evaluator.streaming.middleware import AgentEvalMiddleware


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
    'RetryConfig',              # 재시도 파라미터 묶음 (agent_eval retry=)
    'get_eval_ctx',             # ContextVar context accessor (async-safe)
    'get_framework_info',       # C6: 어댑터 메타데이터 조회
    '_FRAMEWORK_ADAPTERS',      # Task 1: 프레임워크 어댑터 레지스트리 (고급 사용자용)
    'AGENT_EVAL_PRESETS',       # H1: 사전 정의된 파라미터 묶음
    'register_preset',          # 항목 W: preset 런타임 등록

    # Framework-agnostic protocol & input adapters
    'EvaluatorProtocol',
    'to_graph_state',   # str → LangGraph state dict
    'to_crew_inputs',   # str → CrewAI inputs dict
    'to_task_string',   # Any → str (LangChain/AutoGen용)
    'FrameworkLiteral',  # M1: 프레임워크 타입 힌트 (IDE 자동완성 지원)

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
    # LLMJudgeConfig — LLM-as-Judge 파라미터 묶음 (v0.8.2+)
    'LLMJudgeConfig',
    # SecurityConfig — 보안 메트릭 파라미터 묶음 (v0.8.3+)
    'SecurityConfig',
    # v0.9.0+: Phase 1 Harness Config 데이터클래스
    'InstructionConfig',
    'LoopDetectionConfig',
    'GoalAlignmentConfig',
    'ReproducibilityConfig',
    'FaultToleranceConfig',
    'PlanConfig',
    # v0.9.1+: 신규 Harness Config 데이터클래스
    'SLAConfig',
    'ThreatSeverityConfig',
    'EfficiencyConfig',
    'StateConsistencyConfig',
    'DeadlockConfig',
    'ObservabilityConfig',
    'ConsensusConfig',
    # v0.9.2+: Phase 3 Harness Config 데이터클래스
    'ScopeConfig',
    'ContextRetentionConfig',
    'ExplainabilityConfig',
    'SubtaskConfig',
    'PropagationConfig',
    # v0.9.3+: Phase 4 Harness Config 데이터클래스
    'AgentRoleConfig',
    'GracefulDegradationConfig',
    'ComplianceConfig',
    'ResourceBudgetConfig',
    'ConflictResolutionConfig',
    # v0.9.4+: Phase 5 Harness Config 데이터클래스
    'ToolParameterSafetyConfig',
    'KnowledgeRetentionConfig',
    'RetryConsistencyConfig',
    'TTFTVariabilityConfig',
    'ErrorDiagnosisConfig',
    # v0.9.5+: Phase 6 Harness Config 데이터클래스
    'IdempotencyConfig',
    'CostPredictabilityConfig',
    'ThreatResponseConfig',
    'ContextWindowConfig',
    'LatencyAttributionConfig',

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
    'SimpleTaskAlertRule',  # Task 5: 경량 TaskResult 기반 즉시 알림
    'AlertRuleBuilder',     # E6: when_accuracy_below() 등 빌더 API

    # Anomaly Detection (Phase 3-B)
    'AnomalyDetector',
    'AnomalyEvent',

    # Cost Optimization (Phase 3-C)
    'CostTracker',
    'AdaptivePolicy',
    'SamplingStage',

    # QuickEval Facade + HarnessEvaluationGate
    'QuickEval',
    'HarnessEvaluationGate',
    'CompareResult',

    # Golden Set Builder (Phase 3-A — lazy)
    'GoldenSetBuilder',

    # Transparency
    'TestTransparencyManager',
    'AnnotationType',
    'TestStepStatus',

]
