"""
agent_evaluator.core.trackers.base
===================================
Core data classes: TaskResult, EvaluationReport, TaskType, _TaskContext.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .monitor import PerformanceMonitor


@dataclass
class TaskResult:
    """Individual task execution result with Agentic AI support"""
    task_id: str
    task_type: str
    success: bool
    completion_score: float
    accuracy_score: float
    execution_time: float
    tokens_used: Dict[str, int]
    tool_calls: List[Dict[str, Any]]
    attempts: int
    errors: List[str]
    timestamp: datetime

    # Agentic AI specific fields
    agent_interactions: Optional[List[Dict[str, Any]]] = None      # Multi-agent interactions (CrewAI)
    chain_steps: Optional[List[Dict[str, Any]]] = None             # Chain execution steps (LangChain)
    graph_traversal: Optional[Dict[str, Any]] = None               # Graph traversal path (LangGraph)
    conversation_turns: Optional[List[Dict[str, Any]]] = None      # Conversation turns (AutoGen)
    expected_tools: Optional[List[str]] = None                     # Expected tools from golden dataset
    state_transitions: Optional[List[Dict[str, Any]]] = None       # State transitions (LangGraph)
    framework: Optional[str] = None                                 # Framework used (crewai, langchain, langgraph, autogen)
    partial_reason: Optional[str] = None                            # 부분 성공/실패 원인 설명 (자동 추론 또는 사용자 직접 지정)
    # Raw content fields — persisted to JSON for dashboard display
    question: Optional[str] = None                                  # User question / input
    response: Optional[str] = None                                  # Agent response / output
    ground_truth: Optional[str] = None                              # Expected answer
    context: Optional[str] = None                                   # RAG context (for judge / hallucination)
    # LLM Judge result (Phase 1-A) — set by PerformanceMonitor when enable_llm_judge=True
    llm_judge: Optional[Dict[str, Any]] = None                      # {scores, reasoning, model, cost_usd}


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report"""
    period: str
    total_tasks: int
    accuracy_metrics: Dict[str, float]
    efficiency_metrics: Dict[str, Any]
    quality_metrics: Dict[str, float]
    security_metrics: Dict[str, Any] = None  # Optional security metrics (Layer 1 & 2)
    alerts: List[Dict[str, str]] = None
    recommendations: List[Dict[str, str]] = None
    timestamp: datetime = None


class TaskType(Enum):
    """Task type enumeration"""
    QA = "qa"
    DATA_ANALYSIS = "data_analysis"
    CODE_GENERATION = "code_generation"
    DOCUMENT_CREATION = "document_creation"
    INFORMATION_RETRIEVAL = "information_retrieval"
    REASONING = "reasoning"
    CREATIVE = "creative"
    CODING = "coding"
    PLANNING = "planning"
    TOOL_USE = "tool_use"


class _TaskContext:
    """
    Context manager returned by ``PerformanceMonitor.task()``.

    Measures ``execution_time`` automatically and calls ``record_task()``
    on exit.  Exceptions inside the block are recorded in ``self.errors``
    and ``self.success`` is set to ``False``, but the exception is still
    propagated to the caller.

    Attributes:
        response:     Agent output.  Set this inside the ``with`` block.
        ground_truth: Expected answer.
        context:      Retrieval context for hallucination detection.
        success:      Override success flag.  Inferred from ``response`` when ``None``.
        tool_calls:   List of tool-call dicts (same format as ``TaskResult.tool_calls``).
        errors:       List of error strings.
        attempts:     Number of attempts (default 1).
        tokens_used:  Token-usage dict ``{input, output, total}``.
    """

    def __init__(
        self,
        monitor: "PerformanceMonitor",
        task_id: str,
        task_type: str,
        question: Optional[str],
        **kwargs: Any,
    ) -> None:
        self._monitor = monitor
        self._task_id = task_id
        self._task_type = task_type
        self._question = question
        self._kwargs = kwargs
        self._start_time: Optional[float] = None

        # Public attributes set by the user inside the with-block
        self.response: Optional[str] = None
        self.ground_truth: Optional[str] = None
        self.context: Optional[str] = None
        self.success: Optional[bool] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.attempts: int = 1
        self.tokens_used: Optional[Dict[str, int]] = None

    def __enter__(self) -> "_TaskContext":
        import time as _time
        self._start_time = _time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        import time as _time
        execution_time = _time.time() - (self._start_time or 0.0)

        if exc_type is not None:
            self.success = False
            self.errors.append(str(exc_val))

        if self.success is None:
            self.success = self.response is not None and bool(str(self.response).strip())

        completion = 1.0 if self.success else 0.0
        tokens = self.tokens_used or {"input": 0, "output": 0, "total": 0}

        task_result = TaskResult(
            task_id=self._task_id,
            task_type=self._task_type,
            success=self.success,
            completion_score=completion,
            accuracy_score=0.0,
            execution_time=execution_time,
            tokens_used=tokens,
            tool_calls=self.tool_calls,
            attempts=self.attempts,
            errors=self.errors,
            timestamp=datetime.now(),
            question=self._question,
            response=self.response,
            ground_truth=self.ground_truth,
            context=self.context,
        )
        try:
            self._monitor.record_task(
                task_result,
                ground_truth=self.ground_truth,
                context=self.context,
                request=self._question,
                response=self.response,
            )
        except Exception as _e:
            warnings.warn(
                f"record_task failed in task context {self._task_id}: {_e}",
                RuntimeWarning,
                stacklevel=2,
            )
        return False  # always propagate exceptions
