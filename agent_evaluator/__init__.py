"""
Agent Evaluator SDK v0.5.5
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

__version__ = "0.5.5"
__author__ = "Sungwoo Kim"

# Import from core module
# Config & init helpers (cli.main 임포트 없이 제공 — import-time side-effect 없음)
from .config import get_settings, init_from_app, load_env

# Transparency
from .utils.test_transparency_manager import (
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
    'InputSanitizationTracker',
    'OutputLeakageDetector',
    'ToolAuthorizationTracker',
    'PrivilegeEscalationDetector',
    'ToolChainAttackDetector',

    # Transparency
    'TestTransparencyManager',
    'AnnotationType',
    'TestStepStatus',
]
