"""
agent_evaluator.core.trackers.base
===================================
Core data classes: TaskResult, EvaluationReport, TaskType, _TaskContext.
"""

from __future__ import annotations

import dataclasses
import json as _json
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from agent_evaluator.exceptions import ValidationError

if TYPE_CHECKING:
    from .monitor import PerformanceMonitor


@dataclass(frozen=True)
class TaskResult:
    """Individual task execution result with Agentic AI support.

    .. note:: **Subclassing**

        ``TaskResult`` is a Python dataclass where all required fields
        (``task_id`` … ``errors``) precede optional fields.  If you subclass
        and add a *required* field (no default), Python raises ``TypeError``
        because a non-default field follows fields that have defaults.

        To extend ``TaskResult``, add *optional* fields only::

            @dataclass
            class MyTaskResult(TaskResult):
                my_extra: Optional[str] = None  # ✓ optional, safe
    """
    task_id: str
    task_type: str
    success: bool
    completion_score: float
    accuracy_score: float
    execution_time: float
    tokens_used: dict[str, int]
    tool_calls: list[dict[str, Any]]
    attempts: int
    errors: list[str]
    timestamp: datetime = field(default_factory=datetime.now)

    # Agentic AI specific fields
    agent_interactions: list[dict[str, Any]] | None = None      # Multi-agent interactions (CrewAI)
    chain_steps: list[dict[str, Any]] | None = None             # Chain execution steps (LangChain)
    graph_traversal: dict[str, Any] | None = None               # Graph traversal path (LangGraph)
    conversation_turns: list[dict[str, Any]] | None = None      # Conversation turns (AutoGen)
    expected_tools: list[str] | None = None                     # Expected tools from golden dataset
    state_transitions: list[dict[str, Any]] | None = None       # State transitions (LangGraph)
    framework: str | None = None                                 # Framework used (crewai, langchain, langgraph, autogen)
    partial_reason: str | None = None                            # 부분 성공/실패 원인 설명 (자동 추론 또는 사용자 직접 지정)
    # Raw content fields — persisted to JSON for dashboard display
    question: str | None = None                                  # User question / input
    response: str | None = None                                  # Agent response / output
    ground_truth: str | None = None                              # Expected answer
    context: str | None = None                                   # RAG context (for judge / hallucination)
    # LLM Judge result (Phase 1-A) — set by PerformanceMonitor when enable_llm_judge=True
    llm_judge: dict[str, Any] | None = None                      # {scores, reasoning, model, cost_usd}
    # Free-form user-defined metadata — attached via EvalMetadata.extra or get_eval_ctx().extra
    extra: dict[str, Any] | None = None                          # {"intent": "search", "source": "api", ...}

    def __post_init__(self) -> None:
        """입력값 유효성 검증 및 task_type 정규화."""
        # Normalise task_type to lowercase-stripped string so "QA", "qa ", "Qa"
        # all map to the same bucket in aggregation methods.
        # Also accept TaskType enum values for ergonomics.
        # frozen=True requires object.__setattr__ for any field mutation in __post_init__.
        if isinstance(self.task_type, Enum):
            object.__setattr__(self, 'task_type', self.task_type.value)
        object.__setattr__(self, 'task_type', str(self.task_type).lower().strip())

        if not self.task_id or not self.task_id.strip():
            raise ValidationError(
                f"task_id must be a non-empty string, got {self.task_id!r}. "
                "Each task needs a unique identifier (e.g. 'task_001')."
            )

        if not (0.0 <= self.completion_score <= 1.0):
            raise ValidationError(
                f"completion_score must be in [0.0, 1.0], got {self.completion_score}. "
                "Use create_taskresult() for automatic score calculation."
            )
        if not (0.0 <= self.accuracy_score <= 1.0):
            raise ValidationError(
                f"accuracy_score must be in [0.0, 1.0], got {self.accuracy_score}."
            )
        if self.execution_time < 0.0:
            raise ValidationError(
                f"execution_time must be >= 0.0, got {self.execution_time}."
            )
        if self.attempts < 1:
            raise ValidationError(
                f"attempts must be >= 1, got {self.attempts}."
            )

    def __hash__(self) -> int:
        """Hash by task_id (natural primary key).

        ``frozen=True`` auto-generates ``__hash__`` from *all* fields, but
        ``tokens_used: Dict`` and ``tool_calls: List`` are unhashable, making the
        default ``hash()`` always raise ``TypeError``.  Using only ``task_id``
        (a string, always hashable) restores the expected behavior and lets
        ``TaskResult`` objects be stored in sets or used as dict keys.
        """
        return hash(self.task_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskResult:
        """Create a TaskResult from a plain dict (e.g. loaded from JSON).

        Extra keys in *data* are silently ignored so that dicts produced by
        ``dataclasses.asdict()`` on a subclass (e.g. ``ExtendedTaskResult``)
        round-trip correctly when passed to the base class.

        The ``timestamp`` field is accepted as either a :class:`datetime`
        object or an ISO-8601 string; other types fall back to
        ``datetime.now()``.

        Args:
            data: Mapping of field names to values.

        Returns:
            A new ``TaskResult`` (or subclass) instance.

        Raises:
            ValidationError: If required fields are missing or out of range.
            TypeError: If *data* is not a mapping.

        Example::

            import json, dataclasses
            task = create_taskresult(task_id="t1", ...)
            serialized = json.dumps(dataclasses.asdict(task))
            restored = TaskResult.from_json(serialized)
        """
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        kwargs: dict[str, Any] = {k: v for k, v in data.items() if k in valid_fields}

        # Convert timestamp from ISO-8601 string to datetime if needed
        ts = kwargs.get("timestamp")
        if isinstance(ts, str):
            try:
                kwargs["timestamp"] = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                kwargs["timestamp"] = datetime.now()

        return cls(**kwargs)

    @classmethod
    def from_json(cls, json_str: str) -> TaskResult:
        """Create a TaskResult from a JSON string.

        Convenience wrapper around :meth:`from_dict` for JSON strings
        produced by ``json.dumps(dataclasses.asdict(task_result))``.

        Args:
            json_str: JSON-encoded string with TaskResult fields.

        Returns:
            A new ``TaskResult`` (or subclass) instance.

        Example::

            import json, dataclasses
            task = create_taskresult(task_id="t1", ...)
            json_str = json.dumps(dataclasses.asdict(task))
            restored = TaskResult.from_json(json_str)
        """
        return cls.from_dict(_json.loads(json_str))

    def to_dict(self) -> dict[str, Any]:
        """Convert this TaskResult to a plain dict.

        ``datetime`` fields are serialized to ISO-8601 strings so the
        result can be passed to ``json.dumps()`` without a custom encoder.
        Mirrors :meth:`EvaluationReport.to_dict` for API consistency.

        Returns:
            Dict[str, Any]: All fields including optional ones.

        Example::

            import dataclasses
            task = create_taskresult(task_id="t1", ...)
            d = task.to_dict()
            restored = TaskResult.from_dict(d)  # full round-trip
        """
        def _convert(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(item) for item in obj]
            return obj

        return _convert(dataclasses.asdict(self))

    def to_json(self, indent: int = 2) -> str:
        """Convert this TaskResult to a JSON string.

        Args:
            indent: JSON indentation level (default 2).

        Returns:
            str: JSON string with ISO-8601 timestamps.

        Example::

            task = create_taskresult(task_id="t1", ...)
            json_str = task.to_json()
            restored = TaskResult.from_json(json_str)  # full round-trip
        """
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "value"):  # Enum
                return obj.value
            return str(obj)

        return _json.dumps(self.to_dict(), indent=indent, default=_serialize)


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report"""
    period: str
    total_tasks: int
    accuracy_metrics: dict[str, Any]   # {"tcr": {...}, "accuracy_scores": {...}, ...}
    efficiency_metrics: dict[str, Any]
    quality_metrics: dict[str, Any]    # {"avg_total_score": float, "grade_distribution": {...}, ...}
    security_metrics: dict[str, Any] | None = None  # Optional security metrics (Layer 1 & 2)
    alerts: list[dict[str, str]] | None = None
    recommendations: list[dict[str, str]] | None = None
    timestamp: datetime | None = None
    extra_metrics: dict[str, Any] | None = None  # v0.9.0+: harness_groups, etc.

    def __eq__(self, other: object) -> bool:
        """Semantic equality — compares evaluation data fields, excludes ``timestamp``.

        The default dataclass ``__eq__`` includes ``timestamp``, so two reports
        produced from the same data at different moments (or after a JSON
        round-trip that re-parses the timestamp) would incorrectly compare as
        unequal.  This override makes equality reflect whether the *evaluation
        results* are the same, not when the report object was created.
        """
        if not isinstance(other, EvaluationReport):
            return NotImplemented
        return (
            self.period == other.period
            and self.total_tasks == other.total_tasks
            and self.accuracy_metrics == other.accuracy_metrics
            and self.efficiency_metrics == other.efficiency_metrics
            and self.quality_metrics == other.quality_metrics
            and self.security_metrics == other.security_metrics
            and self.alerts == other.alerts
            and self.recommendations == other.recommendations
        )

    def to_dict(self) -> dict[str, Any]:
        """EvaluationReport를 dict로 변환한다.

        datetime 필드는 ISO-8601 문자열로 변환되므로 반환값은
        ``json.dumps()`` 없이 바로 직렬화 가능합니다.

        Returns:
            Dict[str, Any]: 모든 필드를 포함한 dict

        Example:
            >>> report = monitor.generate_report()
            >>> d = report.to_dict()
            >>> print(d["total_tasks"])
        """
        def _convert(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(item) for item in obj]
            return obj

        return _convert(dataclasses.asdict(self))

    def to_json(self, indent: int = 2) -> str:
        """EvaluationReport를 JSON 문자열로 변환한다.

        Args:
            indent: JSON 들여쓰기 (기본값 2)

        Returns:
            str: JSON 문자열

        Example:
            >>> report = monitor.generate_report()
            >>> print(report.to_json())
        """
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "value"):  # Enum
                return obj.value
            return str(obj)

        return _json.dumps(self.to_dict(), indent=indent, default=_serialize)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationReport:
        """Reconstruct an EvaluationReport from a dict (e.g. loaded from JSON).

        Extra keys in *data* are silently ignored.  The ``timestamp`` field
        is accepted as either a :class:`datetime` object or an ISO-8601
        string; other types are stored as-is (``None`` if missing).

        Args:
            data: Mapping produced by :meth:`to_dict` or ``json.loads(to_json())``.

        Returns:
            A new ``EvaluationReport`` instance.

        Example::

            import json
            report = monitor.generate_report()
            json_str = report.to_json()
            restored = EvaluationReport.from_json(json_str)
            assert restored.total_tasks == report.total_tasks
        """
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        kwargs: dict[str, Any] = {k: v for k, v in data.items() if k in valid_fields}

        ts = kwargs.get("timestamp")
        if isinstance(ts, str):
            try:
                kwargs["timestamp"] = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                kwargs["timestamp"] = None

        return cls(**kwargs)

    @classmethod
    def from_json(cls, json_str: str) -> EvaluationReport:
        """Reconstruct an EvaluationReport from a JSON string.

        Convenience wrapper around :meth:`from_dict` for JSON strings
        produced by :meth:`to_json`.

        Args:
            json_str: JSON-encoded string.

        Returns:
            A new ``EvaluationReport`` instance.
        """
        return cls.from_dict(_json.loads(json_str))

    def summary(self) -> dict[str, Any]:
        """핵심 지표만 담은 요약 dict를 반환한다.

        Returns:
            Dict[str, Any]: 총 태스크 수, 성공률, 평균 정확도, 평균 지연시간 등 핵심 수치

        Example:
            >>> report = monitor.generate_report()
            >>> s = report.summary()
            >>> print(s["success_rate"])  # 0.95
        """
        tcr_data = self.accuracy_metrics.get("tcr") or {}
        accuracy_data = self.accuracy_metrics.get("accuracy_scores") or {}
        latency_data = (self.efficiency_metrics or {}).get("latency") or {}
        return {
            "total_tasks": self.total_tasks,
            "success_rate": tcr_data.get("success_rate", 0.0),
            "avg_accuracy": accuracy_data.get("overall_accuracy", 0.0),
            "avg_latency_s": latency_data.get("mean", 0.0),
            "period": self.period,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
        }


class BaseTracker(ABC):
    """Abstract base class for all evaluation trackers.

    All Layer 1, Layer 2, and Security trackers inherit from this class.
    Guarantees a ``reset()`` contract, which lets ``PerformanceMonitor``
    iterate over all trackers uniformly without hard-coding each name.

    To implement a custom tracker, subclass ``BaseTracker`` and override
    ``reset()``::

        from agent_evaluator import BaseTracker

        class MyTracker(BaseTracker):
            def __init__(self):
                self.records = []

            def reset(self) -> None:
                self.records.clear()
    """

    @abstractmethod
    def reset(self) -> None:
        """Clear all accumulated data.

        Called by ``PerformanceMonitor.reset()`` to wipe state between
        evaluation sessions (e.g., in CI loops).
        """


class TaskType(Enum):
    """Task type enumeration for agent evaluation metrics.

    Use these values in ``TaskResult.task_type`` or ``create_taskresult()`` to
    enable per-type accuracy breakdowns and benchmark comparisons.

    Values:
        QA: Question-answering / factual retrieval tasks.
        DATA_ANALYSIS: Data processing, aggregation, or transformation.
        CODE_GENERATION: Code synthesis, completion, or debugging.
        DOCUMENT_CREATION: Long-form writing, summarisation, report generation.
        INFORMATION_RETRIEVAL: Search, RAG, knowledge-base lookup.
        REASONING: Multi-step reasoning, chain-of-thought, logic problems.
        CREATIVE: Open-ended creative writing or ideation.
        CODING: Alias for CODE_GENERATION (kept for backward compatibility).
        PLANNING: Task decomposition, scheduling, or goal planning.
        TOOL_USE: Tasks requiring external tool / API calls.
    """
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
        monitor: PerformanceMonitor,
        task_id: str,
        task_type: str,
        question: str | None,
        **kwargs: Any,
    ) -> None:
        self._monitor = monitor
        self._task_id = task_id
        self._task_type = task_type
        self._question = question
        self._kwargs = kwargs
        self._start_time: float | None = None

        # Public attributes set by the user inside the with-block
        self.response: str | None = None
        self.ground_truth: str | None = None
        self.context: str | None = None
        self.success: bool | None = None
        self.tool_calls: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.attempts: int = 1
        self.tokens_used: dict[str, int] | None = None

    def __enter__(self) -> _TaskContext:
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
        tokens = self.tokens_used or {"input": 0, "output": 0, "total": 0, "model": "unknown"}

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
            # All fields already set on task_result; pass without deprecated kwargs
            # to avoid triggering DeprecationWarnings in user code.
            self._monitor.record_task(task_result)
        except Exception as _e:
            warnings.warn(
                f"record_task failed in task context {self._task_id}: {_e}",
                RuntimeWarning,
                stacklevel=2,
            )
        return False  # always propagate exceptions
