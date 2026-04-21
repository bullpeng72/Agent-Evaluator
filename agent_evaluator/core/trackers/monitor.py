"""
agent_evaluator.core.trackers.monitor
========================================
PerformanceMonitor — central orchestrator that ties all tracker layers together.
Also contains create_demo_data() and run_demo() helper functions.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
import re
import statistics
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from enum import Enum
import warnings
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import numpy as np
import pandas as pd

from .base import TaskResult, EvaluationReport, TaskType, _TaskContext, BaseTracker
from ...exceptions import ValidationError, StorageError, MetricComputationError
from .layer1 import (
    TaskCompletionTracker,
    AccuracyEvaluator,
    HallucinationDetector,
    ResponseQualityEvaluator,
    LatencyTracker,
    TokenEconomyTracker,
    MultimodalMetricsTracker,
)
from .layer2 import (
    ToolCallAnalyzer,
    RetryCorrectionTracker,
    ToolSelectionTracker,
    AgentCoordinationTracker,
    WorkflowExecutionTracker,
)
from .security import (
    SecurityTrackerMixin,
    InputSanitizationTracker,
    OutputLeakageDetector,
    ToolAuthorizationTracker,
    infer_privilege_level,
    PrivilegeEscalationDetector,
    ToolChainAttackDetector,
)
from .conversation import ConversationSession

try:
    from .feedback import ImplicitFeedbackTracker as _ImplicitFeedbackTracker
    _FEEDBACK_AVAILABLE = True
except ImportError:
    _ImplicitFeedbackTracker = None  # type: ignore[assignment,misc]
    _FEEDBACK_AVAILABLE = False

logger = logging.getLogger(__name__)


def _json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for non-standard types used by save_to_file()."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return 0.0  # NaN / ±Infinity → 0.0 (dashboard-safe numeric sentinel)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    logger.debug("JSON serialization fallback for type %s", type(obj).__name__)
    return str(obj)


# R: 스트리밍 직렬화 임계값 — 태스크 수가 이 값 이상이면 메모리 효율적 스트리밍 모드 사용
_STREAMING_THRESHOLD: int = 5000


def _write_json_streaming(file_obj: Any, data: Dict[str, Any], tasks_list: List) -> None:
    """대용량 tasks를 chunk 단위로 파일에 직접 기록합니다 (R 항목).

    전체 data dict를 메모리에 한 번에 직렬화하지 않고, tasks 제외한 필드를 먼저
    쓴 뒤 tasks를 하나씩 직렬화해 기록합니다. 결과 파일은 유효한 JSON입니다.

    Args:
        file_obj: 쓰기용 파일 객체 (open(..., 'w') 또는 os.fdopen(..., 'w')).
        data: save_to_file() 에서 구성한 전체 데이터 딕셔너리 (tasks 포함).
        tasks_list: 직렬화된 태스크 딕셔너리 리스트 (data["tasks"] 와 동일).
    """
    import json as _json

    # tasks 제외한 나머지 필드를 딕셔너리로 구성 후 직렬화
    header = {k: v for k, v in data.items() if k != "tasks"}
    # indent 없이 직렬화 — 스트리밍 모드에서는 indent 비용 생략
    header_str = _json.dumps(header, ensure_ascii=False, default=_json_serializer)
    # 닫는 "}" 제거 후 "tasks" 키를 이어 붙임
    file_obj.write(header_str[:-1])  # "}" 제거
    file_obj.write(', "tasks": [')

    for i, task in enumerate(tasks_list):
        if i > 0:
            file_obj.write(",")
        file_obj.write(_json.dumps(task, ensure_ascii=False, default=_json_serializer))

    file_obj.write("]}")


# ResponseQualityEvaluator의 total_score는 0-5 척도.
# compare_with_thresholds()에서 사용자 친화적인 0-10 척도로 변환할 때 이 인수를 곱한다.
_QUALITY_SCORE_TO_10_SCALE: float = 2.0

# Pre-compiled regex and stopword set used inside record_task() hot path.
# Defined at module level to avoid re-creating identical objects on every call.
_RE_NON_WORD = re.compile(r'[^\w\s]')
_QUALITY_EVAL_STOPWORDS: frozenset = frozenset({
    "이", "가", "은", "는", "을", "를", "의", "에", "도", "로",
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
})

# TaskType → OpenInference span kind 매핑 (모듈 상수 — 매 호출마다 재생성 방지)
# 의미론적으로 올바른 kind 사용:
#   LLM       — 직접적인 LLM 출력 평가 (qa, 코드생성, 창작, 문서, 추론)
#   RETRIEVER — RAG/검색 파이프라인 (information_retrieval)
#   TOOL      — 에이전트 도구 호출 (tool_use)
#   AGENT     — 에이전트 계획/오케스트레이션 (planning)
#   CHAIN     — 멀티스텝 파이프라인 (data_analysis)
# 참고: Phoenix "Top models by cost/tokens" 차트는 LLM kind 스팬만 집계하므로
#       RETRIEVER/TOOL/AGENT/CHAIN 태스크는 Traces 탭에서 직접 확인.
_OTEL_SPAN_KIND_MAP: Dict[str, str] = {
    "qa": "LLM",
    "code_generation": "LLM",
    "coding": "LLM",
    "creative": "LLM",
    "document_creation": "LLM",
    "reasoning": "LLM",
    "information_retrieval": "RETRIEVER",
    "tool_use": "TOOL",
    "planning": "AGENT",
    "data_analysis": "CHAIN",
}

# 신규 Claude/OpenAI 모델명 → Phoenix(LiteLLM) 가격 테이블 등록명 매핑
# Phoenix는 LiteLLM 가격 DB를 사용하므로 미등록 모델은 "Top models by cost"에 표시 안 됨.
# 신규 모델은 nearest 등록 모델로 매핑해 비용 추정이 가능하게 한다.
_PHOENIX_MODEL_ALIAS: Dict[str, str] = {
    # Claude 4.x / 4.5 / 4.6 → 가장 가까운 등록 모델
    "claude-opus-4-6":              "claude-3-opus-20240229",
    "claude-sonnet-4-6":            "claude-3-5-sonnet-20241022",
    "claude-haiku-4-5":             "claude-3-5-haiku-20241022",
    "claude-haiku-4-5-20251001":    "claude-3-5-haiku-20241022",
    # GPT-4o 계열
    "gpt-4o-mini-2024-07-18":       "gpt-4o-mini",
    "gpt-4o-2024-11-20":            "gpt-4o",
    "gpt-4o-2024-08-06":            "gpt-4o",
}

# OTEL 속성 크기 제한 — Phoenix OTLP HTTP 기본 4MB이나 속성값 개별 권장치
_OTEL_ATTR_MAX_LEN: int = 4096


class PerformanceMonitor:
    """Main performance monitoring and reporting system"""

    def __init__(
        self,
        pricing: Dict[str, float] = None,
        model_name: str = "",
        session_label: str = "",
        enable_transparency: bool = False,
        enable_hallucination_detection: bool = False,
        enable_security_metrics: bool = False,
        security_config: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None,
        # LLM Judge (Phase 1-A)
        enable_llm_judge: bool = False,
        judge_model: Optional[str] = None,
        judge_sample_rate: float = 0.1,
        judge_budget_per_day: Optional[float] = None,
        judge_budget_storage_path: Optional[str] = None,
        # G-Eval 스타일 커스텀 평가 기준 (DeepEval 대체)
        # 예: ["medical_accuracy", "citation_quality"]
        judge_criteria: Optional[List[str]] = None,
        # LLM Judge context 잘림 한도 (기본 4000자 — RAG 문서 1~2페이지 커버)
        judge_max_context_chars: int = 4000,
        # LLM Judge escalation — primary 점수 미달 시 상위 모델 자동 재채점 (v0.8.3+)
        judge_escalation_model: Optional[str] = None,
        judge_escalation_threshold: float = 2.5,
        # LLM Judge 샘플링 재현성 시드
        judge_seed: Optional[int] = None,
        # 한국어 형태소 분석 기반 토큰화 (kiwipiepy 필요)
        use_korean_tokenizer: bool = False,
        # 의미 기반 환각 탐지 (sentence-transformers 필요, opt-in)
        use_semantic_hallucination: bool = False,
        semantic_weight: float = 0.5,
        # Anomaly Detection (Phase 3-B)
        enable_anomaly_detection: bool = False,
        anomaly_baseline_window: int = 100,
        anomaly_detection_window: int = 20,
        # Task 2: auto_save — record_task() 마다 주기적으로 save_to_file() 자동 호출
        auto_save: bool = False,
        auto_save_interval: int = 10,
        auto_save_filename: str = "auto_save",
        # D3: 선택적 보안 트래커 활성화 (enable_security_metrics=True 일 때만 유효)
        enabled_security_trackers: Optional[List[str]] = None,
        # D2: OTEL 자식 스팬 — chain_steps 각 항목을 별도 자식 스팬으로 발행
        enable_otel_child_spans: bool = False,
        # Phase 1: Harness D Config 파라미터 연동
        ttft_variability_config: Optional[Any] = None,
        cost_predictability_config: Optional[Any] = None,
    ):
        """
        Initialize Performance Monitor

        Args:
            pricing: Token pricing (default: Claude Sonnet 4.5 pricing)
            model_name: Model name used for this evaluation (e.g. "claude-sonnet-4-5").
                Stored in the result JSON so the dashboard can highlight the correct
                pricing row and display it in the cost banner.
            enable_transparency: Enable transparency logging (traces, annotations)
            enable_hallucination_detection: Enable Layer1 hallucination detection (opt-in)
                - False (default): Disable hallucination detection for maximum performance
                - True: Automatic rule-based hallucination detection (no external deps)
            enable_security_metrics: Enable security metrics tracking (opt-in)
                - False (default): No security tracking, best performance
                - True: Track input/output security and authorization compliance
            security_config: Security configuration (allowed_tools, restricted_tools)
            output_dir: Output directory for results
            enable_llm_judge: Enable LLM-as-Judge automatic scoring (opt-in).
                When True, each recorded task with a question+response is evaluated
                by the judge model on 3 dimensions (completeness, relevance,
                factual_consistency). Requires ANTHROPIC_API_KEY or OPENAI_API_KEY.
            judge_model: Model used for judging.  ``None`` (default) → ``agent-eval init``
                으로 설정한 API 키·모델명(OPENAI_MODEL / ANTHROPIC_MODEL)에서 자동 결정.
                OPENAI_API_KEY가 있으면 openai_model, ANTHROPIC_API_KEY가 있으면
                anthropic_model 사용. Supports any Claude or OpenAI chat model.
            judge_sample_rate: Fraction of tasks to judge (0.0–1.0).  Use < 1.0 to
                control API costs in high-volume evaluations.
            judge_budget_per_day: Optional USD hard cap per calendar day.  When
                cumulative judge cost exceeds this value, further judge calls are
                skipped with a RuntimeWarning.
            judge_budget_storage_path: JSON 파일 경로. 지정 시 일일 예산 누적액을 파일에
                영속 저장하여 프로세스 재시작 후에도 당일 예산이 유지된다.
                예: ``".judge_budget.json"``. None(기본값)이면 in-memory only.
            use_korean_tokenizer: True 이면 AccuracyEvaluator / HallucinationDetector 에서
                kiwipiepy 형태소 분석기를 사용한다 (pip install "agent-evaluator[korean]" 필요).
                미설치 시 공백 분리 폴백으로 동작하며 경고 로그가 출력된다.
            use_semantic_hallucination: True 이면 HallucinationDetector 에서 sentence-transformers
                기반 의미 유사도를 활성화한다 (pip install "agent-evaluator[semantic]" 필요).
                미설치 시 단어 중복 방식으로 폴백한다.
            semantic_weight: 의미 유사도 혼합 비율 (0.0 = 단어 중복만, 1.0 = 의미 유사도만, 기본 0.5).
            enable_anomaly_detection: Enable automatic anomaly detection at save_to_file() time.
                When True, AnomalyDetector.scan() is called and results are stored under
                ``anomaly_data`` in the JSON output, making the dashboard 이상 감지 tab
                show real data. Requires no external dependencies.
            anomaly_baseline_window: Number of tasks used as the baseline for anomaly detection.
            anomaly_detection_window: Number of recent tasks used for current-state comparison.
            enabled_security_trackers: ``enable_security_metrics=True`` 일 때 활성화할 보안 트래커
                이름 목록. ``None`` 이면 전체 트래커 활성화(기존 동작).
                허용값: ``"InputSanitization"``, ``"OutputLeakage"``, ``"ToolAuthorization"``,
                ``"PrivilegeEscalation"``, ``"ToolChainAttack"``.
                ``enable_security_metrics=False`` 이면 이 파라미터는 무시된다.
        """
        if pricing is None:
            pricing = {"input": 0.003, "output": 0.015}  # Default: Claude Sonnet 4.5

        # model_name 미지정 시 .env 설정에서 자동 읽기
        # 규칙: 실제 API 키가 설정된 모델 우선. "your-..." 형태의 placeholder 키는 무시.
        if not model_name:
            try:
                from agent_evaluator.config import get_settings
                s = get_settings()
                _ak = s.anthropic_api_key or ""
                _ok = s.openai_api_key or ""
                # placeholder 키("your-"로 시작하는 템플릿 값) 무시
                _has_real_anthropic = bool(_ak) and not _ak.startswith("your-")
                _has_real_openai = bool(_ok) and not _ok.startswith("your-")
                if _has_real_anthropic:
                    model_name = s.anthropic_model or ""
                elif _has_real_openai:
                    model_name = s.openai_model or ""
                # 둘 다 없으면 model_name="" 유지 (ae/unspecified fallback)
            except Exception as _e:
                logger.debug("model_name 설정 실패 (무시): %s", _e)
        self.model_name = model_name

        # Configuration
        self.enable_hallucination_detection = enable_hallucination_detection
        self.enable_security_metrics = enable_security_metrics
        self.security_config = security_config or {}

        # Zero Configuration: 자동 경로 감지
        from pathlib import Path
        if output_dir is None:
            from ...utils.path_helpers import get_evaluation_results_dir
            output_dir = get_evaluation_results_dir(create=False)
        self.output_dir = Path(output_dir) if isinstance(output_dir, str) else output_dir
        # ⚡ Lazy initialization: 디렉토리는 실제 저장 시점에 생성
        # self.output_dir.mkdir(parents=True, exist_ok=True)

        # Layer 1: Basic trackers (Native Metrics)
        self.tcr_tracker = TaskCompletionTracker()
        self.accuracy_evaluator = AccuracyEvaluator(
            use_korean_tokenizer=use_korean_tokenizer
        )
        self.hallucination_detector = HallucinationDetector(
            use_korean_tokenizer=use_korean_tokenizer,
            use_semantic_similarity=use_semantic_hallucination,
            semantic_weight=semantic_weight,
        )
        self.quality_evaluator = ResponseQualityEvaluator()
        self.latency_tracker = LatencyTracker()
        self.token_tracker = TokenEconomyTracker(pricing)
        self.retry_tracker = RetryCorrectionTracker()

        # D3: enabled_security_trackers 정규화 — None이면 전체 트래커 활성화
        _ALL_SEC_TRACKERS = {
            "InputSanitization", "OutputLeakage", "ToolAuthorization",
            "PrivilegeEscalation", "ToolChainAttack",
        }
        _sec_set: Optional[set] = (
            set(enabled_security_trackers) if enabled_security_trackers is not None else None
        )
        # D2: OTEL 자식 스팬 활성화 여부
        self.enable_otel_child_spans: bool = enable_otel_child_spans
        # Phase 1: Harness D Config 인스턴스 저장
        self._ttft_variability_config = ttft_variability_config
        self._cost_predictability_config = cost_predictability_config

        # Layer 1: Security trackers (optional)
        self.input_sanitizer = None
        self.output_leakage_detector = None
        self.tool_authorizer = None

        if enable_security_metrics:
            _all = _sec_set is None
            if _all or "InputSanitization" in _sec_set:
                self.input_sanitizer = InputSanitizationTracker()
            if _all or "OutputLeakage" in _sec_set:
                self.output_leakage_detector = OutputLeakageDetector()
            if _all or "ToolAuthorization" in _sec_set:
                self.tool_authorizer = ToolAuthorizationTracker(
                    allowed_tools=self.security_config.get('allowed_tools'),
                    restricted_tools=self.security_config.get('restricted_tools')
                )
            logger.info(
                "Security metrics (Layer 1) 활성화됨 (trackers=%s)",
                sorted(_sec_set) if _sec_set else "all",
            )

        # Layer 2: Agentic AI trackers
        self.tool_analyzer = ToolCallAnalyzer()  # Tool call efficiency
        self.tool_selection_tracker = ToolSelectionTracker()  # Tool selection accuracy
        self.agent_coordination_tracker = AgentCoordinationTracker()
        self.workflow_tracker = WorkflowExecutionTracker()

        # Layer 2: Agentic Security trackers (optional)
        self.privilege_escalation_detector = None
        self.tool_chain_attack_detector = None

        if enable_security_metrics:
            _all = _sec_set is None
            if _all or "PrivilegeEscalation" in _sec_set:
                self.privilege_escalation_detector = PrivilegeEscalationDetector()
            if _all or "ToolChainAttack" in _sec_set:
                self.tool_chain_attack_detector = ToolChainAttackDetector()
            logger.info(
                "Security metrics (Layer 2) 활성화됨 (trackers=%s)",
                sorted(_sec_set) if _sec_set else "all",
            )

        # RAG metrics tracker
        self._rag_metrics = {
            'faithfulness': [],
            'answer_relevancy': [],
            'context_recall': [],
            'context_precision': []
        }

        # Test 투명성 추적 (선택적)
        self.enable_transparency = enable_transparency
        self.transparency_manager = None

        if enable_transparency:
            try:
                # CRITICAL FIX: Use correct relative import path
                from ...utils.transparency_manager import TestTransparencyManager
                self.transparency_manager = TestTransparencyManager(output_dir=str(self.output_dir))
                logger.info("Test 투명성 추적 활성화됨")
                # Auto audit: evaluation session started
                self.transparency_manager.log_event(
                    event_type="lifecycle",
                    user="system",
                    action="evaluation_started",
                    target_type="monitor",
                    target_id="performance_monitor",
                    details={
                        "enable_hallucination_detection": enable_hallucination_detection,
                        "enable_security_metrics": enable_security_metrics,
                        "output_dir": str(self.output_dir),
                    },
                    success=True,
                )
            except ImportError as e:
                logger.warning("transparency_manager를 찾을 수 없습니다: %s", e)
                logger.warning("투명성 추적 비활성화됨")
                self.enable_transparency = False

        # LLM Judge (Phase 1-A, opt-in)
        self.enable_llm_judge = enable_llm_judge
        self.llm_judge = None
        if enable_llm_judge:
            try:
                from ...integrations.llm_judge import LLMJudge
                self.llm_judge = LLMJudge(
                    model=judge_model,
                    sample_rate=judge_sample_rate,
                    budget_per_day=judge_budget_per_day,
                    budget_storage_path=judge_budget_storage_path,
                    judge_criteria=judge_criteria,
                    max_context_chars=judge_max_context_chars,
                    escalation_model=judge_escalation_model,
                    escalation_threshold=judge_escalation_threshold,
                    seed=judge_seed,
                )
                logger.info("LLM Judge 활성화됨 (model=%s, sample_rate=%s)", self.llm_judge.model, judge_sample_rate)
            except ImportError as e:
                warnings.warn(f"LLM Judge 초기화 실패 (의존성 없음): {e}", RuntimeWarning, stacklevel=2)
                self.enable_llm_judge = False
            except Exception as e:
                logger.warning("LLM Judge 초기화 중 예기치 않은 오류: %s", e, exc_info=True)
                warnings.warn(f"LLM Judge 초기화 실패: {e}", RuntimeWarning, stacklevel=2)
                self.enable_llm_judge = False

        # Phase 3-B: 이상 감지 (opt-in)
        self.enable_anomaly_detection = enable_anomaly_detection
        self._anomaly_baseline_window = anomaly_baseline_window
        self._anomaly_detection_window = anomaly_detection_window

        # 임계값 설정 (DataEditorManager에서 로드 가능)
        self._thresholds: Optional[Dict[str, float]] = None
        self.golden_dataset_path = None
        self._golden_datasets: List[Any] = []

        # Phase 1-C: 멀티턴 대화 세션 목록
        self.conversation_sessions: List[Any] = []

        # Phase 2-C: 암묵적 피드백 트래커 (optional — graceful degradation when unavailable)
        if _FEEDBACK_AVAILABLE and _ImplicitFeedbackTracker is not None:
            self.feedback_tracker: Optional[Any] = _ImplicitFeedbackTracker()
        else:
            self.feedback_tracker = None

        # G3: 멀티모달 지표 트래커
        self.multimodal_tracker = MultimodalMetricsTracker()

        # Phase 2-A: StreamingEvaluator 스냅샷 (외부에서 set → save_to_file에 자동 포함)
        self._streaming_snapshot: Optional[Dict[str, Any]] = None

        # Thread safety: golden_datasets/conversation_sessions 동시 접근 보호
        # RLock allows the same thread to acquire the lock multiple times (re-entrant).
        # This prevents deadlocks when record_task() (already inside _lock) triggers
        # auto_save → save_to_file(), which also needs to read tasks safely.
        self._lock = threading.RLock()
        self._tasks_lock = self._lock  # alias — tasks 접근 보호용 (P 항목)

        # OTEL 세션 식별자 — Phoenix Sessions 탭 그룹핑용
        # session_label이 있으면 사람이 읽기 쉬운 형태로 구성 (예: "01_quality_eval_a3f2")
        _uid = str(uuid.uuid4())[:8]
        self._session_label: str = session_label
        self._otel_session_id: str = f"{session_label}_{_uid}" if session_label else _uid

        # Phoenix Annotation API 전송 대기열 — save_to_file() 시 일괄 POST
        self._pending_annotations: List[Dict[str, Any]] = []

        # Phoenix Experiments — begin_experiment() / end_experiment() 로 관리
        self._phoenix_experiment_id: Optional[str] = None
        self._phoenix_experiment_name: Optional[str] = None
        self._phoenix_dataset_id: Optional[str] = None

        # Task 2: auto_save — record_task() N회마다 save_to_file() 자동 호출
        self.auto_save: bool = auto_save
        self._auto_save_interval: int = max(1, auto_save_interval)
        self._auto_save_filename: str = auto_save_filename
        self._auto_save_counter: int = 0
        self._auto_save_lock = threading.Lock()

        # Q: get_live_stats() 성능 최적화 — 최근 태스크 캐시 (최대 5분)
        # record_task() 에서 (timestamp_float, TaskResult) 튜플로 추가
        from collections import deque as _deque
        # M8: maxlen=10000 prevents unbounded memory growth in long-running monitors.
        self._recent_tasks_cache: "deque" = _deque(maxlen=10000)
        self._cache_window_seconds: float = 300.0  # 최대 5분 보관

    @property
    def golden_datasets(self) -> List[Any]:
        """Shallow copy of loaded golden datasets."""
        return list(self._golden_datasets)

    @golden_datasets.setter
    def golden_datasets(self, value: List[Any]) -> None:
        """Set golden datasets (used by load_golden_dataset)."""
        self._golden_datasets = list(value)

    @property
    def thresholds(self) -> Optional[Dict[str, float]]:
        """Evaluation threshold dict, or ``None`` if unset."""
        return self._thresholds

    @thresholds.setter
    def thresholds(self, value: Optional[Dict[str, float]]) -> None:
        """Set evaluation thresholds with type validation.

        Args:
            value: ``{"tcr": 85.0, "accuracy": 0.8, ...}`` or ``None``.

        Raises:
            ValidationError: If *value* is not a dict (or ``None``), or if any
                threshold value is non-numeric.
        """
        if value is None:
            self._thresholds = None
            return
        if not isinstance(value, dict):
            raise ValidationError(
                f"thresholds must be a dict or None, got {type(value).__name__!r}"
            )
        invalid = {k: v for k, v in value.items() if not isinstance(v, (int, float))}
        if invalid:
            raise ValidationError(
                f"threshold values must be numeric (int or float). "
                f"Invalid entries: {invalid}"
            )
        self._thresholds = dict(value)

    @property
    def tasks(self) -> List["TaskResult"]:
        """기록된 모든 TaskResult 리스트.

        Example::

            monitor.record_task(result)
            assert len(monitor.tasks) == 1
        """
        tasks = getattr(getattr(self, "tcr_tracker", None), "tasks", None)
        return list(tasks) if tasks is not None else []

    @property
    def task_count(self) -> int:
        """현재까지 기록된 태스크 수 (D2).

        ``tcr_tracker.tasks`` 에 의존하지 않고 안전하게 총 태스크 수를 반환한다.
        ``tcr_tracker`` 가 없거나 초기화 전인 경우 0을 반환한다.

        Example::

            monitor.record_task(result)
            assert monitor.task_count == 1
        """
        tcr = getattr(self, "tcr_tracker", None)
        if tcr is None:
            return 0
        tasks = getattr(tcr, "tasks", None)
        return len(tasks) if tasks is not None else 0

    @property
    def rag_metrics(self) -> Dict[str, List]:
        """RAG 지표 딕셔너리의 얕은 복사본.

        각 키의 리스트도 복사되므로 반환값을 변경해도 내부 상태에
        영향을 주지 않습니다.  RAG 지표를 추가하려면 반드시
        :meth:`record_rag_metrics` 를 사용하세요.
        """
        return {k: list(v) for k, v in self._rag_metrics.items()}

    def conversation(self, session_id: str, task_type: str = "qa") -> "ConversationSession":
        """멀티턴 대화 평가 세션 시작.

        Usage::

            with monitor.conversation("session_001") as conv:
                conv.turn(user="질문", agent="응답")
            # 세션 종료 시 자동으로 지표 계산 및 monitor.conversation_sessions에 기록

        Args:
            session_id: 세션 고유 ID.
            task_type: 태스크 유형 (기본: ``"qa"``). 대시보드 필터링에 사용된다.

        Returns:
            ConversationSession 인스턴스.
        """
        return ConversationSession(session_id=session_id, monitor=self, task_type=task_type)

    def load_golden_dataset(self, dataset_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Golden Dataset 로드

        Args:
            dataset_path: Golden Dataset 파일 경로 (None이면 config에서 로드)

        Returns:
            List[Dict]: Golden Dataset 항목 리스트

        Raises:
            StorageError: 파일이 존재하지 않거나, JSON 포맷이 올바르지 않거나,
                파일 읽기 권한이 없는 경우.

        Example:
            >>> items = monitor.load_golden_dataset("datasets/qa_pairs.json")
            >>> print(len(items))
        """
        if dataset_path is None and self.golden_dataset_path:
            dataset_path = self.golden_dataset_path

        if dataset_path is None:
            logger.warning("Golden Dataset 경로가 지정되지 않았습니다")
            return []

        # golden_datasets 디렉토리에서 찾기
        if not os.path.isabs(dataset_path):
            golden_dir = 'golden_datasets'
            full_path = os.path.join(golden_dir, dataset_path)
            if os.path.exists(full_path):
                dataset_path = full_path

        if not os.path.exists(dataset_path):
            abs_path = os.path.abspath(dataset_path)
            raise StorageError(
                f"Golden Dataset 파일을 찾을 수 없습니다: '{dataset_path}'\n"
                f"절대 경로: {abs_path}"
            )

        try:
            with open(dataset_path, encoding='utf-8') as f:
                data = json.load(f)

            # Handle both formats: direct array or object with qa_pairs key
            if isinstance(data, list):
                loaded = data
            elif isinstance(data, dict) and 'qa_pairs' in data:
                loaded = data['qa_pairs']
            else:
                raise StorageError(
                    f"Golden Dataset 포맷이 올바르지 않습니다: '{dataset_path}'\n"
                    "지원 포맷: JSON 배열 또는 {{\"qa_pairs\": [...]}}"
                )

            with self._lock:
                self._golden_datasets = loaded
            logger.info("Golden Dataset 로드: %d개 항목", len(self._golden_datasets))
            return list(self._golden_datasets)
        except StorageError:
            raise
        except json.JSONDecodeError as e:
            raise StorageError(f"Golden Dataset JSON 파싱 오류: {e}") from e
        except OSError as e:
            raise StorageError(f"Golden Dataset 파일 읽기 실패: {e}") from e

    def evaluate_with_golden_dataset(
        self,
        agent_fn,
        dataset_path: Optional[str] = None,
        enable_layer2_metrics: bool = True,
        enable_advanced_metrics: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Golden Dataset 기반 자동 평가 파이프라인

        **API 선택 가이드**

        * ``evaluate_with_golden_dataset()`` — JSON 파일에 저장된 Golden Dataset을
          기반으로 에이전트 함수를 라이브 실행하고 Layer 1/2 지표를 자동 수집할 때 사용.
          ``agent_fn`` 이 있는 경우에 적합.
        * ``evaluate_batch()`` — 이미 수집된 (질문, 응답, 정답) 삼중쌍을 오프라인으로
          평가할 때 사용. 에이전트를 직접 실행하지 않음.
        * ``record_task()`` — 자체 에이전트 하네스에서 이미 :class:`TaskResult` 를
          생성한 경우 직접 호출.

        Args:
            agent_fn: 평가할 에이전트 함수 (question을 입력받아 결과 반환).
                      반환값: ``str`` 또는 ``Dict`` with optional keys:
                      ``answer`` (str), ``tools_used`` (List[str]),
                      ``latency`` (float), ``token_usage`` (Dict),
                      ``tool_calls`` (List), ``retry_count`` (int).
            dataset_path: Golden Dataset 파일 경로 (JSON). 각 항목은 다음
                      키를 포함해야 합니다:

                      - ``question`` (**필수**): 에이전트에 전달할 질문 문자열.
                      - ``ground_truth`` (선택): 정답 문자열. 제공 시 accuracy 자동 계산.
                      - ``expected_tools`` (선택): 예상 도구 목록.
                        ``enable_layer2_metrics=True`` 일 때 Tool Selection F1 계산에 사용.
                      - ``qa_id`` (선택): 항목 고유 ID. 없으면 ``"qa_{idx}"`` 자동 생성.

            enable_layer2_metrics: Layer 2 메트릭 자동 평가 (Tool Selection 등)
            enable_advanced_metrics: Layer 3 고급 메트릭 (DeepEval, Ragas)
            verbose: 진행 상황 출력

        Returns:
            Dict: 평가 결과 요약
            {
                "total_evaluated": int,
                "layer1_metrics": {...},
                "layer2_metrics": {...},
                "layer3_metrics": {...},
                "pass_fail": {...}
            }

        Example:
            # 간단한 에이전트 함수
            def my_agent(question):
                return {
                    "answer": llm.predict(question),
                    "tools_used": ["search", "calculator"]
                }

            # 자동 평가
            results = monitor.evaluate_with_golden_dataset(
                agent_fn=my_agent,
                dataset_path="sample_dataset.json",
                enable_layer2_metrics=True
            )
        """
        # Golden Dataset 로드
        if not self._golden_datasets or dataset_path:
            self.load_golden_dataset(dataset_path)  # raises StorageError on failure

        with self._lock:
            golden_items = list(self._golden_datasets)  # 스냅샷: 읽는 동안 외부 수정 방지

        total = len(golden_items)
        if verbose:
            print(f"🚀 Golden Dataset 기반 자동 평가 시작 ({total}개 항목)")

        # 각 QA 쌍 평가
        for idx, qa_pair in enumerate(golden_items, 1):
            if verbose:
                print(f"\n[{idx}/{total}] 평가 중: {qa_pair.get('question', '')[:50]}...")

            try:
                # 에이전트 실행
                result = agent_fn(qa_pair['question'])

                # 결과 추출
                if isinstance(result, dict):
                    agent_answer = result.get('answer', str(result))
                    tools_used = result.get('tools_used', [])
                else:
                    agent_answer = str(result)
                    tools_used = []

                # Accuracy 자동 계산 (ground_truth가 있는 경우)
                ground_truth = qa_pair.get('ground_truth', '')
                accuracy_score = 0.0
                if ground_truth:
                    # AccuracyEvaluator를 사용하여 계산
                    accuracy_score = self.accuracy_evaluator._calculate_accuracy(
                        ground_truth,
                        agent_answer,
                        TaskType.QA.value
                    )
                    # 평가 추가
                    self.accuracy_evaluator.add_evaluation(
                        task_id=qa_pair.get('qa_id', f'qa_{idx}'),
                        ground_truth=ground_truth,
                        prediction=agent_answer,
                        task_type=TaskType.QA.value
                    )

                # Layer 1: TaskResult 생성
                task = TaskResult(
                    task_id=qa_pair.get('qa_id', f'qa_{idx}'),
                    task_type=TaskType.QA.value,
                    timestamp=datetime.now(),
                    success=True,
                    completion_score=1.0 if agent_answer else 0.0,
                    accuracy_score=accuracy_score,
                    execution_time=result.get('latency', 0) if isinstance(result, dict) else 0,
                    tokens_used=result.get('token_usage', {"input": 0, "output": 0}) if isinstance(result, dict) else {"input": 0, "output": 0},
                    tool_calls=result.get('tool_calls', []) if isinstance(result, dict) else [],
                    attempts=max(1, result.get('retry_count', 1)) if isinstance(result, dict) else 1,
                    errors=[],
                    expected_tools=qa_pair.get('expected_tools', []) if enable_layer2_metrics else None
                )

                # 메트릭 자동 계산
                self.record_task(task)

                # Layer 2: Tool Selection 자동 평가
                if enable_layer2_metrics and qa_pair.get('expected_tools'):
                    self.tool_selection_tracker.evaluate_selection(
                        task_id=task.task_id,
                        expected_tools=qa_pair['expected_tools'],
                        actual_tools=tools_used
                    )

                if verbose:
                    print("   ✅ 평가 완료")

            except Exception as e:
                logger.warning("Golden Dataset 평가 항목 오류 (continue): %s", e)
                if verbose:
                    print(f"   ❌ 오류: {str(e)}")
                continue

        # 결과 요약
        if verbose:
            print(f"\n✅ Golden Dataset 평가 완료 ({total}개 항목)")

        # Layer 1 메트릭
        tcr_data = self.tcr_tracker.calculate_tcr()
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        hallucination_data = self.hallucination_detector.get_hallucination_rate()

        # Layer 2 메트릭
        tool_selection_stats = self.tool_selection_tracker.get_accuracy_stats() if enable_layer2_metrics else {}

        # 임계값 비교
        comparison = self.compare_with_thresholds() if self._thresholds else {}

        results = {
            "total_evaluated": total,
            "layer1_metrics": {
                "tcr": tcr_data.get('tcr', 0),
                "accuracy": accuracy_data.get('overall_accuracy', 0) if accuracy_data else 0,
                "hallucination_rate": hallucination_data.get('overall_rate', 0),
            },
            "layer2_metrics": {
                "tool_selection_accuracy": tool_selection_stats.get('avg_accuracy', 0) if tool_selection_stats else 0,
                "tool_selection_f1": tool_selection_stats.get('avg_f1_score', 0) if tool_selection_stats else 0,
            } if enable_layer2_metrics else {},
            "pass_fail": comparison
        }

        if verbose:
            print("\n📊 평가 결과 요약:")
            print(f"   TCR: {results['layer1_metrics']['tcr']:.1f}%")
            print(f"   Accuracy: {results['layer1_metrics']['accuracy']:.1f}%")
            if enable_layer2_metrics and results['layer2_metrics']:
                print(f"   Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")

        return results

    def compare_with_thresholds(self) -> Dict[str, Any]:
        """현재 메트릭 값을 설정된 임계값과 비교한다.

        ``monitor.thresholds``가 설정되어 있어야 하며, 설정되지 않은 경우 빈 dict를 반환한다.
        임계값은 ``agent-eval gate`` CLI 또는 ``monitor.thresholds = {...}``으로 설정한다.

        Returns:
            각 메트릭 이름을 키로 하는 비교 결과 dict. 반환 구조는 다음과 같다::

                {
                    "<metric_name>": {
                        "current":   float,  # 현재 측정값 (``value`` 필드와 동일)
                        "threshold": float,  # 임계값
                        "passed":    bool,   # 통과 여부 (status == "pass" 이면 True)
                        "message":   str,    # 상태 메시지 (name + status 조합)
                        # -- 추가 필드 (내부 구현) --
                        "name":      str,    # 메트릭 표시 이름 (예: "작업 완료율 (TCR)")
                        "value":     float,  # current 와 동일 (하위 호환 유지)
                        "status":    str,    # "pass" / "fail" / "pending"
                        "direction": str,    # "higher" 또는 "lower"
                        "unit":      str,    # "%" / "s" / "$" 등
                        "layer":     str,    # (선택) Layer 2 에이전틱 지표에만 존재
                    },
                    ...
                }

            최상위 키:
              - 각 메트릭 이름 (예: ``"tcr"``, ``"accuracy"``, ``"hallucination"``)
              - 임계값이 설정되지 않은 경우 빈 dict ``{}`` 반환

            Note:
                ``quality`` 임계값은 0-10 척도로 설정한다.
                내부적으로 ResponseQualityEvaluator의 0-5 점수에 ``_QUALITY_SCORE_TO_10_SCALE``
                (= 2.0)를 곱해 변환한다.

                ``pending`` 상태는 RAG 지표(faithfulness 등)에서 아직 측정값이 없을 때 반환된다.
                이 경우 ``passed`` 는 ``False`` 로 취급한다.

        Example:
            >>> monitor.thresholds = {"tcr": 80.0, "hallucination": 10.0}
            >>> results = monitor.compare_with_thresholds()
            >>> results["tcr"]["status"]   # "pass" 또는 "fail"
            >>> results["tcr"]["value"]    # 실제 TCR 값 (%)
            >>> results["tcr"]["passed"]   # True / False
            >>> results["tcr"]["current"]  # value 와 동일
        """
        if not self._thresholds:
            return {}

        # Validate threshold values up-front so errors surface at configuration
        # time rather than deep inside statistics.mean() calls.
        invalid = {
            k: v for k, v in self._thresholds.items()
            if not isinstance(v, (int, float))
        }
        if invalid:
            raise ValidationError(
                f"compare_with_thresholds(): threshold values must be numeric. "
                f"Non-numeric entries: { {k: type(v).__name__ for k, v in invalid.items()} }. "
                "Example: monitor.thresholds = {'tcr': 80.0, 'accuracy': 70.0}"
            )

        comparison = {}

        # TCR
        tcr_data = self.tcr_tracker.calculate_tcr()
        if 'tcr' in self._thresholds:
            comparison['tcr'] = {
                'name': '작업 완료율 (TCR)',
                'value': tcr_data.get('tcr', 0),
                'threshold': self._thresholds['tcr'],
                'status': 'pass' if tcr_data.get('tcr', 0) >= self._thresholds['tcr'] else 'fail',
                'direction': 'higher',
                'unit': '%'
            }

        # Accuracy — use get_accuracy_metrics() for total_evaluated guard (RAG-style pending)
        accuracy_metrics = self.accuracy_evaluator.get_accuracy_metrics()
        if 'accuracy' in self._thresholds:
            _acc_val = accuracy_metrics.get('overall_accuracy', 0)
            _acc_evaluated = accuracy_metrics.get('total_evaluated', 0)
            comparison['accuracy'] = {
                'name': '정확도 (Accuracy)',
                'value': _acc_val,
                'threshold': self._thresholds['accuracy'],
                'status': (
                    'pending' if _acc_evaluated == 0
                    else 'pass' if _acc_val >= self._thresholds['accuracy']
                    else 'fail'
                ),
                'direction': 'higher',
                'unit': '%'
            }

        # Hallucination
        hall_data = self.hallucination_detector.get_hallucination_rate()
        if 'hallucination' in self._thresholds:
            comparison['hallucination'] = {
                'name': '환각 발생률 (Hallucination)',
                'value': hall_data.get('overall_rate', 0),
                'threshold': self._thresholds['hallucination'],
                'status': 'pass' if hall_data.get('overall_rate', 0) <= self._thresholds['hallucination'] else 'fail',
                'direction': 'lower',
                'unit': '%'
            }

        # Quality
        quality_data = self.quality_evaluator.get_quality_metrics()
        if (quality_data.get('total_evaluated', 0) > 0
                and 'avg_total_score' in quality_data
                and 'quality' in self._thresholds):
            avg_quality = quality_data['avg_total_score'] * _QUALITY_SCORE_TO_10_SCALE
            comparison['quality'] = {
                'name': '응답 품질 (Quality)',
                'value': avg_quality,
                'threshold': self._thresholds['quality'],
                'status': 'pass' if avg_quality >= self._thresholds['quality'] else 'fail',
                'direction': 'higher',
                'unit': '/10'
            }

        # Latency
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data and 'latency' in self._thresholds:
            comparison['latency'] = {
                'name': '응답 시간 (Latency)',
                'value': latency_data.get('p95', 0),
                'threshold': self._thresholds['latency'],
                'status': 'pass' if latency_data.get('p95', 0) <= self._thresholds['latency'] else 'fail',
                'direction': 'lower',
                'unit': 's'
            }

        # Cost per Task
        token_data = self.token_tracker.get_usage_stats()
        if 'cost_per_task' in self._thresholds:
            comparison['cost_per_task'] = {
                'name': '작업당 비용 (Cost per Task)',
                'value': token_data.get('avg_cost_per_task', 0),
                'threshold': self._thresholds['cost_per_task'],
                'status': 'pass' if token_data.get('avg_cost_per_task', 0) <= self._thresholds['cost_per_task'] else 'fail',
                'direction': 'lower',
                'unit': '$'
            }

        # RAG Metrics
        # Helper: no data → 'pending'; above threshold → 'pass'; below → 'fail'
        def _rag_status(avg: float, threshold: float, values: list) -> str:
            if not values:
                return 'pending'
            elif avg >= threshold:
                return 'pass'
            else:
                return 'fail'

        # Snapshot RAG metric lists under lock to avoid race with record_rag_metrics()
        with self._lock:
            faithfulness_values = list(self._rag_metrics.get('faithfulness', []))
            relevancy_values = list(self._rag_metrics.get('answer_relevancy', []))
            recall_values = list(self._rag_metrics.get('context_recall', []))
            precision_values = list(self._rag_metrics.get('context_precision', []))

        # Faithfulness
        if 'faithfulness' in self._thresholds:
            avg_faithfulness = statistics.mean(faithfulness_values) if faithfulness_values else 0.0
            comparison['faithfulness'] = {
                'name': 'Faithfulness',
                'value': avg_faithfulness,
                'threshold': self._thresholds['faithfulness'],
                'status': _rag_status(avg_faithfulness, self._thresholds['faithfulness'], faithfulness_values),
                'direction': 'higher',
                'unit': ''
            }

        # Answer Relevancy
        if 'answer_relevancy' in self._thresholds:
            avg_relevancy = statistics.mean(relevancy_values) if relevancy_values else 0.0
            comparison['answer_relevancy'] = {
                'name': 'Answer Relevancy',
                'value': avg_relevancy,
                'threshold': self._thresholds['answer_relevancy'],
                'status': _rag_status(avg_relevancy, self._thresholds['answer_relevancy'], relevancy_values),
                'direction': 'higher',
                'unit': ''
            }

        # Context Recall
        if 'context_recall' in self._thresholds:
            avg_recall = statistics.mean(recall_values) if recall_values else 0.0
            comparison['context_recall'] = {
                'name': 'Context Recall',
                'value': avg_recall,
                'threshold': self._thresholds['context_recall'],
                'status': _rag_status(avg_recall, self._thresholds['context_recall'], recall_values),
                'direction': 'higher',
                'unit': ''
            }

        # Context Precision
        if 'context_precision' in self._thresholds:
            avg_precision = statistics.mean(precision_values) if precision_values else 0.0
            comparison['context_precision'] = {
                'name': 'Context Precision',
                'value': avg_precision,
                'threshold': self._thresholds['context_precision'],
                'status': _rag_status(avg_precision, self._thresholds['context_precision'], precision_values),
                'direction': 'higher',
                'unit': ''
            }

        # Layer 2: Agentic AI Metrics
        # Tool Selection Accuracy
        tool_stats = self.tool_selection_tracker.get_accuracy_stats()
        if tool_stats and 'tool_selection_accuracy' in self._thresholds:
            comparison['tool_selection_accuracy'] = {
                'name': '도구 선택 정확도 (Tool Selection Accuracy)',
                'value': tool_stats.get('avg_accuracy', 0),
                'threshold': self._thresholds['tool_selection_accuracy'],
                'status': 'pass' if tool_stats.get('avg_accuracy', 0) >= self._thresholds['tool_selection_accuracy'] else 'fail',
                'direction': 'higher',
                'unit': '%',
                'layer': 'Layer 2'
            }

        # Agent Coordination Score
        coord_data = self.agent_coordination_tracker.calculate_coordination_score()
        if coord_data and 'agent_coordination' in self._thresholds:
            # coordination_score는 0-10 척도, threshold도 0-10으로 설정
            comparison['agent_coordination'] = {
                'name': '에이전트 협업 점수 (Agent Coordination)',
                'value': coord_data.get('overall_score', 0),
                'threshold': self._thresholds['agent_coordination'],
                'status': 'pass' if coord_data.get('overall_score', 0) >= self._thresholds['agent_coordination'] else 'fail',
                'direction': 'higher',
                'unit': '/10',
                'layer': 'Layer 2',
                'details': {
                    'success_rate': coord_data.get('success_rate', 0),
                    'total_interactions': coord_data.get('total_interactions', 0),
                    'unique_agents': coord_data.get('unique_agents', 0)
                }
            }

        # Workflow Execution Success Rate
        workflow_stats = self.workflow_tracker.calculate_execution_success_rate()
        if workflow_stats and 'workflow_execution' in self._thresholds:
            comparison['workflow_execution'] = {
                'name': '워크플로우 실행 성공률 (Workflow Execution)',
                'value': workflow_stats.get('step_success_rate', 0),
                'threshold': self._thresholds['workflow_execution'],
                'status': 'pass' if workflow_stats.get('step_success_rate', 0) >= self._thresholds['workflow_execution'] else 'fail',
                'direction': 'higher',
                'unit': '%',
                'layer': 'Layer 2',
                'details': {
                    'total_steps': workflow_stats.get('total_steps', 0),
                    'successful_steps': workflow_stats.get('successful_steps', 0),
                    'task_success_rate': workflow_stats.get('task_success_rate', 0)
                }
            }

        return comparison

    def reset(self, keep_config: bool = True) -> "PerformanceMonitor":
        """Clear all accumulated data across every tracker (thread-safe).

        Use this when reusing a ``PerformanceMonitor`` instance across
        multiple evaluation sessions (e.g., in a CI loop) to prevent
        data from one session leaking into the next.

        All mutations are performed under the monitor lock so no concurrent
        ``record_task()`` call can interleave partial state.

        E2: 초기화 항목과 보존 항목 명세

        +------------------------------------------+------------------------------------------+
        | **초기화 (Reset)**                        | **보존 (Kept)**                          |
        +==========================================+==========================================+
        | 모든 트래커 내부 데이터                   | ``output_dir``                           |
        | (tasks, latencies, usage_log 등)          | ``enable_hallucination_detection``       |
        | ``conversation_sessions``                 | ``enable_security_metrics``              |
        | ``_golden_datasets``                      | ``enable_quality_evaluation``            |
        | ``_rag_metrics``                          | ``thresholds`` (SLA 기준 등)             |
        | ``feedback_tracker`` 데이터               | ``auto_save`` 설정                       |
        | ``_custom_aggregators``                   | ``_lock`` (스레드 락)                    |
        | auto-save 카운터                          | 보안 트래커 설정                         |
        +------------------------------------------+------------------------------------------+

        Args:
            keep_config: ``True`` (기본)이면 설정(output_dir, enable_* 플래그 등)을 유지하고
                태스크 데이터만 초기화한다. ``False`` 이면 전체 초기화 후 기본값으로 복원.

        Returns:
            ``self`` — 메서드 체이닝 지원.

        Example::

            monitor.reset()                    # 태스크만 초기화, 설정 유지
            monitor.reset(keep_config=False)   # 완전 초기화
            monitor.reset().record_task(result)  # 체이닝
        """
        with self._lock:
            for tracker in self._iter_trackers():
                tracker.reset()
            self.conversation_sessions.clear()
            self._golden_datasets.clear()
            for key in self._rag_metrics:
                self._rag_metrics[key].clear()
            self.feedback_tracker.reset()
            # D1: custom aggregators 초기화 (태스크 데이터이므로 항상 초기화)
            if hasattr(self, "_custom_aggregators"):
                self._custom_aggregators.clear()
            # Q: 최근 태스크 캐시 초기화
            if hasattr(self, "_recent_tasks_cache"):
                self._recent_tasks_cache.clear()
        return self

    def _iter_trackers(self) -> Iterator[BaseTracker]:
        """Yield all initialized BaseTracker instances owned by this monitor.

        Discovers trackers by inspecting instance attributes — any attribute
        that is a ``BaseTracker`` (including optional security trackers when
        they are not ``None``) is yielded.  New trackers added in future
        subclasses are automatically included without modifying this method.
        """
        for attr_val in vars(self).values():
            if isinstance(attr_val, BaseTracker):
                yield attr_val

    def task(
        self,
        task_id: str,
        task_type: str = "qa",
        question: Optional[str] = None,
        **kwargs: Any,
    ) -> "_TaskContext":
        """
        Context manager that measures a single task execution.

        ``execution_time`` is measured automatically.  ``record_task()`` is
        called on ``__exit__`` so Quality and Accuracy auto-triggers apply.

        Args:
            task_id:   Unique task identifier.
            task_type: Task type string (e.g. ``"qa"``, ``"coding"``).
            question:  User question / prompt (also sets ``_TaskContext._question``).
            **kwargs:  Extra keyword arguments (reserved for future use).

        Returns:
            A :class:`_TaskContext` instance used as the ``as`` target.

        Example:
            with monitor.task("task_001", "qa", question="수도는?") as t:
                t.response = agent.run(t._question)
                t.ground_truth = "서울"
        """
        return _TaskContext(self, task_id, task_type, question, **kwargs)

    def evaluate_qa(
        self,
        question: str,
        response: str,
        ground_truth: str,
        task_id: Optional[str] = None,
        execution_time: float = 0.0,
        task_type: str = "qa",
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """단일 QA 태스크를 즉시 평가하고 결과를 반환한다.

        create_taskresult_from_execution() + record_task() + 점수 반환을 한 번에 처리하는
        편의 메서드다.

        Args:
            question: 평가할 질문
            response: 에이전트 응답
            ground_truth: 정답
            task_id: 태스크 ID (기본값: 자동 생성)
            execution_time: 실행 시간 초 (기본값: 0.0)
            task_type: 태스크 유형 (기본값: "qa")

        Returns:
            Dict[str, Any]: {"task_id": ..., "accuracy_score": ..., "completion_score": ..., "success": ...}

        Example:
            >>> result = monitor.evaluate_qa(
            ...     question="한국의 수도는?",
            ...     response="서울입니다.",
            ...     ground_truth="서울",
            ... )
            >>> print(result["accuracy_score"])  # 0.95
        """
        from agent_evaluator.helpers.taskresult_helpers import create_taskresult_from_execution

        _task_id = task_id or f"qa_{uuid.uuid4().hex[:8]}"
        task = create_taskresult_from_execution(
            task_id=_task_id,
            question=question,
            response=response,
            ground_truth=ground_truth,
            execution_time=execution_time,
            task_type=task_type,
            context=context,
        )
        self.record_task(task)
        return {
            "task_id": _task_id,
            "accuracy_score": task.accuracy_score,
            "completion_score": task.completion_score,
            "success": task.success,
        }

    def evaluate_batch(
        self,
        items: List[Dict[str, Any]],
        task_type: str = "qa",
        task_id_prefix: str = "batch",
    ) -> List[Dict[str, Any]]:
        """여러 QA 태스크를 일괄 평가하고 결과 목록을 반환한다.

        **API 선택 가이드**

        * ``evaluate_batch()`` — 이미 수집된 (질문, 응답, 정답) 삼중쌍을 오프라인으로
          평가할 때 사용. 에이전트를 직접 실행하지 않음.
        * ``evaluate_with_golden_dataset()`` — JSON 파일에 저장된 Golden Dataset을
          기반으로 에이전트 함수를 라이브 실행하고 Layer 1/2 지표를 자동 수집할 때 사용.
        * ``record_task()`` — 자체 에이전트 하네스에서 이미 :class:`TaskResult` 를
          생성한 경우 직접 호출.

        Args:
            items: 평가할 항목 목록. 각 항목은 다음 키를 포함:
                - question (str): 질문
                - response (str): 에이전트 응답
                - ground_truth (str): 정답
                - task_id (str, 선택): 태스크 ID
                - execution_time (float, 선택): 실행 시간
            task_type: 기본 태스크 유형 (기본값: ``"qa"``).
                각 항목에 ``"task_type"`` 키가 있으면 그 값이 우선하며,
                없는 경우에만 이 파라미터 값이 사용됩니다.
            task_id_prefix: 자동 생성 task_id 접두사 (기본값: ``"batch"``)

        Returns:
            List[Dict[str, Any]]: 각 태스크의 평가 결과 목록

        Example:
            >>> results = monitor.evaluate_batch([
            ...     {"question": "Q1", "response": "A1", "ground_truth": "G1"},
            ...     {"question": "Q2", "response": "A2", "ground_truth": "G2"},
            ... ])
            >>> avg = sum(r["accuracy_score"] for r in results) / len(results)
        """
        # 필수 키 사전 검증
        required_keys = {"question", "response", "ground_truth"}
        invalid = [
            (i, required_keys - set(item.keys()))
            for i, item in enumerate(items)
            if not required_keys.issubset(item.keys())
        ]
        if invalid:
            detail = "; ".join(f"item[{i}] missing={missing}" for i, missing in invalid)
            raise ValidationError(
                f"evaluate_batch() items에 필수 키가 없습니다: {detail}\n"
                "필수 키: question, response, ground_truth"
            )

        results = []
        for i, item in enumerate(items):
            _task_id = item.get("task_id", f"{task_id_prefix}_{i:04d}")
            result = self.evaluate_qa(
                question=item["question"],
                response=item["response"],
                ground_truth=item["ground_truth"],
                task_id=_task_id,
                execution_time=item.get("execution_time", 0.0),
                task_type=item.get("task_type", task_type),
            )
            results.append(result)
        return results

    def __repr__(self) -> str:
        tasks = len(self.tcr_tracker._tasks)
        tcr_data = self.tcr_tracker.calculate_tcr()
        tcr = tcr_data.get("tcr", 0.0)
        sec = " security=on" if self.enable_security_metrics else ""
        hall = " hallucination=on" if self.enable_hallucination_detection else ""
        return f"PerformanceMonitor(tasks={tasks}, tcr={tcr:.1f}%{hall}{sec})"

    # ------------------------------------------------------------------
    # Factory classmethods — common pre-configured monitor variants
    # ------------------------------------------------------------------

    @classmethod
    def for_rag_evaluation(
        cls,
        output_dir: Optional[str] = None,
        enable_hallucination_detection: bool = True,
        **kwargs: Any,
    ) -> "PerformanceMonitor":
        """Create a monitor pre-configured for RAG pipeline evaluation.

        Enables hallucination detection by default, which compares generated
        answers against the retrieved context passed to :meth:`record_task`.

        Args:
            output_dir: Optional output directory for saved results.
            enable_hallucination_detection: Whether to enable hallucination
                detection (default ``True``).
            **kwargs: Additional keyword arguments forwarded to
                :class:`PerformanceMonitor`.

        Example::

            monitor = PerformanceMonitor.for_rag_evaluation()
            result = create_taskresult(task_id="q1", question="...", response="...")
            monitor.record_task(result, context=retrieved_docs)
            report = monitor.generate_report()
        """
        return cls(
            output_dir=output_dir,
            enable_hallucination_detection=enable_hallucination_detection,
            **kwargs,
        )

    @classmethod
    def for_secure_agents(
        cls,
        security_config: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> "PerformanceMonitor":
        """Create a monitor pre-configured for security-sensitive agent evaluation.

        Enables all Layer-1 and Layer-2 security trackers:
        ``InputSanitizationTracker``, ``OutputLeakageDetector``,
        ``ToolAuthorizationTracker``, ``PrivilegeEscalationDetector``, and
        ``ToolChainAttackDetector``.

        Args:
            security_config: Optional dict forwarded to security tracker
                constructors.  Supported keys:
                ``allowed_tools`` (list[str]) — tool whitelist;
                ``restricted_tools`` (list[str]) — tool blacklist.
            output_dir: Optional output directory for saved results.
            **kwargs: Additional keyword arguments forwarded to
                :class:`PerformanceMonitor`.

        Example::

            monitor = PerformanceMonitor.for_secure_agents(
                security_config={"allowed_tools": ["web_search", "calculator"]}
            )
        """
        return cls(
            output_dir=output_dir,
            enable_security_metrics=True,
            security_config=security_config,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Core recording API
    # ------------------------------------------------------------------

    def record_task(self, task_result: TaskResult,
                   ground_truth: Optional[Any] = None,
                   context: Optional[str] = None,
                   request: Optional[str] = None,       # deprecated: use task_result.question
                   response: Optional[str] = None,      # deprecated: use task_result.response
                   expected_elements: Optional[List[str]] = None) -> "PerformanceMonitor":
        """Record a complete task execution.

        Args:
            task_result: TaskResult from agent execution.
            ground_truth: Expected/correct output.  Prefer setting
                ``task_result.ground_truth`` directly.
            context: Retrieved documents for hallucination detection.
            request: *Deprecated* — use ``TaskResult(question=...)`` instead.
                Overrides ``task_result.question`` when that field is empty.
                Will be removed in v0.8.0.
            response: *Deprecated* — use ``TaskResult(response=...)`` instead.
                Overrides ``task_result.response`` when that field is empty.
                Will be removed in v0.8.0.
            expected_elements: Expected elements in response for quality scoring.

        Returns:
            PerformanceMonitor: ``self``, enabling method chaining::

                monitor.record_task(t1).record_task(t2).generate_report()

            All metrics are accumulated in-place on the monitor's internal
            trackers.  Call :meth:`generate_report` or :meth:`save_to_file`
            after recording all tasks to retrieve aggregated results.

        Migration guide for deprecated params::

            # Before (deprecated)
            monitor.record_task(task, request="What is AI?", response="AI is...")

            # After (recommended)
            from agent_evaluator import create_taskresult
            task = create_taskresult(
                task_id="t1", question="What is AI?", response="AI is ...", ...
            )
            monitor.record_task(task)
        """
        # Deprecation warnings for parameters that duplicate TaskResult fields
        # These params will be removed in v0.8.0 — migrate to TaskResult fields.
        if request is not None:
            warnings.warn(
                "record_task(request=...) is deprecated and will be removed in v0.8.0. "
                "Use TaskResult(question=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if response is not None:
            warnings.warn(
                "record_task(response=...) is deprecated and will be removed in v0.8.0. "
                "Use TaskResult(response=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if ground_truth is not None:
            warnings.warn(
                "record_task(ground_truth=...) is deprecated and will be removed in v0.8.0. "
                "Use TaskResult(ground_truth=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Persist raw content onto TaskResult so it is included in asdict() → JSON.
        # Rule: deprecated param wins only when the TaskResult field is None or "".
        # An empty-string field is treated the same as "not set" so that callers
        # who pass TaskResult() without a question/response still benefit from the
        # deprecated params.  TaskResult is frozen → use dataclasses.replace().
        _replacements: Dict[str, Any] = {}
        if request is not None and not task_result.question:
            _replacements["question"] = str(request) if not isinstance(request, str) else request
        if response is not None and not task_result.response:
            _replacements["response"] = str(response) if not isinstance(response, str) else response
        if ground_truth is not None and not task_result.ground_truth:
            _replacements["ground_truth"] = (
                str(ground_truth) if not isinstance(ground_truth, str) else ground_truth
            )
        if _replacements:
            task_result = dataclasses.replace(task_result, **_replacements)

        # Pre-compute effective values (used by LLM judge below and auto-triggers inside lock)
        _eff_request = request if request is not None else task_result.question
        _eff_response = response if response is not None else task_result.response

        # Auto-trigger: LLM Judge (opt-in, Phase 1-A) — run BEFORE the lock so
        # the result can be embedded in task_result via dataclasses.replace()
        # before the task is stored in tcr_tracker.tasks.
        if self.enable_llm_judge and self.llm_judge and _eff_request and _eff_response:
            try:
                judge_result = self.llm_judge.judge(
                    task_id=task_result.task_id,
                    question=_eff_request,
                    response=_eff_response,
                    context=context or task_result.context,
                )
                # Attach judge scores so they are serialised into JSON output.
                if not judge_result.get("skipped") and judge_result.get("scores"):
                    task_result = dataclasses.replace(task_result, llm_judge=judge_result)
            except (AttributeError, KeyError, TypeError) as _judge_exc:
                logger.warning(
                    "LLM Judge failed for %s: %s", task_result.task_id, _judge_exc, exc_info=True
                )
            except Exception as _judge_exc:
                logger.debug(
                    "LLM Judge unexpected error for %s: %s",
                    task_result.task_id, _judge_exc, exc_info=True,
                )

        # M8: partial_reason 확장 자동 분류 — 잠금 이전에 task_result를 교체해야 함
        _pr = getattr(task_result, "partial_reason", None)
        if _pr is None and hasattr(task_result, "completion_score"):
            _cs = task_result.completion_score or 0.0
            _as_m8 = task_result.accuracy_score or 0.0
            _errs = task_result.errors or []
            _attempts = task_result.attempts or 1
            _new_pr = None
            if len(_errs) > 0 and "timeout" in str(_errs).lower():
                _new_pr = "timeout"
            elif len(_errs) > 0 and any("tool" in str(e).lower() for e in _errs):
                _new_pr = "tool_error"
            elif _cs > 0 and _cs < 1.0 and _as_m8 < 0.5:
                _new_pr = "low_accuracy"
            elif _attempts > 1 and _cs < 1.0:
                _new_pr = "retry_degraded"
            if _new_pr:
                try:
                    task_result = dataclasses.replace(task_result, partial_reason=_new_pr)
                except Exception as _pr_exc:
                    logger.debug("partial_reason 확장 분류 실패 (무시): %s", _pr_exc)

        with self._lock:  # guard all tracker mutations for thread safety
            # Task completion
            self.tcr_tracker.add_task(task_result)

            # Q: 최근 태스크 캐시 업데이트 (get_live_stats O(k) 최적화)
            import time as _time_mod
            _ts_now = _time_mod.time()
            self._recent_tasks_cache.append((_ts_now, task_result))
            _cutoff = _ts_now - self._cache_window_seconds
            while self._recent_tasks_cache and self._recent_tasks_cache[0][0] < _cutoff:
                self._recent_tasks_cache.popleft()

            # Accuracy — store via record_score() to keep _cached_avg consistent.
            # When ground_truth is absent, accuracy_score=0.0 is a placeholder,
            # not a measured value.  Pass None so get_accuracy_scores() dropna()
            # excludes these tasks from the aggregate average (H1 fix).
            _gt_present = bool(getattr(task_result, "ground_truth", None))
            self.accuracy_evaluator.record_score(
                task_id=task_result.task_id,
                task_type=task_result.task_type,
                accuracy=task_result.accuracy_score if _gt_present else None,
            )
            
            # Latency
            self.latency_tracker.record_latency(
                task_result.task_id,
                task_result.task_type,
                task_result.execution_time,
                {"total": task_result.execution_time}  # Simplified breakdown
            )
            
            # Token usage
            if task_result.tokens_used:
                self.token_tracker.track_usage(
                    task_result.task_id,
                    task_result.tokens_used.get("input", 0),
                    task_result.tokens_used.get("output", 0),
                    task_result.task_type,
                    model=task_result.tokens_used.get("model", "default"),  # DQ-150
                    framework=task_result.framework or "native",  # G2: 프레임워크별 비용 집계
                )
            
            # Tool calls
            if task_result.tool_calls:
                self.tool_analyzer.analyze_execution(
                    task_result.task_id,
                    task_result.tool_calls
                )
            
            # Retries — integration(_record_layer2)이 이미 기록했으면 합성 데이터로 중복 기록하지 않음
            if task_result.attempts > 1:
                if task_result.task_id not in self.retry_tracker._task_ids:
                    _avg_attempt_dur = task_result.execution_time / task_result.attempts
                    attempts_log = [
                        {"success": i == task_result.attempts - 1, "duration": _avg_attempt_dur}
                        for i in range(task_result.attempts)
                    ]
                    self.retry_tracker.track_attempts(task_result.task_id, attempts_log)
    
            # Agentic AI: Tool Selection Accuracy
            # integration(_record_layer2)이 이미 기록했으면 중복 기록하지 않음
            if task_result.expected_tools and task_result.tool_calls:
                if task_result.task_id not in self.tool_selection_tracker._task_ids:
                    actual_tools = []
                    for call in task_result.tool_calls:
                        if isinstance(call, str):
                            actual_tools.append(call)
                        elif isinstance(call, dict):
                            tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown")
                            actual_tools.append(tool_name)
                        else:
                            actual_tools.append("unknown")
                    self.tool_selection_tracker.evaluate_selection(
                        task_result.task_id,
                        task_result.expected_tools,
                        actual_tools
                    )
    
            # Agentic AI: Agent Coordination (CrewAI)
            if task_result.agent_interactions:
                for interaction in task_result.agent_interactions:
                    self.agent_coordination_tracker.track_interaction(
                        task_result.task_id,
                        interaction.get("from_agent", "unknown"),
                        interaction.get("to_agent", "unknown"),
                        interaction.get("type", "communication"),
                        interaction.get("success", True),
                        interaction.get("context")
                    )
    
            # Agentic AI: Workflow Execution (LangChain/LangGraph)
            if task_result.chain_steps:
                for step in task_result.chain_steps:
                    self.workflow_tracker.track_step(
                        task_result.task_id,
                        step.get("name", "unknown"),
                        step.get("type", "chain_step"),
                        step.get("success", True),
                        step.get("execution_time", 0.0),
                        task_result.framework or "langchain",
                        step.get("metadata")
                    )
    
            # Security Metrics (opt-in, enable_security_metrics=True 일 때만 실행)
            if self.enable_security_metrics:
                _sec_q = _eff_request or task_result.question
                _sec_r = _eff_response or task_result.response
                # Layer 1: Input Sanitization — 입력 텍스트 위협 스캔
                if self.input_sanitizer is not None and _sec_q:
                    try:
                        self.input_sanitizer.evaluate_input(task_result.task_id, _sec_q)
                    except Exception as _sec_exc:
                        logger.debug("InputSanitizationTracker 실패 (무시): %s", _sec_exc)
                # Layer 1: Output Leakage Detection — 출력 내 민감정보 탐지
                if self.output_leakage_detector is not None and _sec_r:
                    try:
                        self.output_leakage_detector.detect_leakage(task_result.task_id, _sec_r)
                    except Exception as _sec_exc:
                        logger.debug("OutputLeakageDetector 실패 (무시): %s", _sec_exc)
                # Layer 1: Tool Authorization — 각 도구 호출 권한 검사
                if self.tool_authorizer is not None and task_result.tool_calls:
                    for _stc in task_result.tool_calls:
                        try:
                            if isinstance(_stc, dict):
                                _stc_name = _stc.get("tool_name") or _stc.get("tool") or _stc.get("name", "unknown")
                                _stc_params = _stc.get("input") or _stc.get("parameters") or {}
                            else:
                                _stc_name = str(_stc)
                                _stc_params = {}
                            self.tool_authorizer.track_tool_call(task_result.task_id, _stc_name, _stc_params or None)
                        except Exception as _sec_exc:
                            logger.debug("ToolAuthorizationTracker 실패 (무시): %s", _sec_exc)
                # Layer 2: Privilege Escalation — 도구 체인의 권한 상승 패턴 감지
                if self.privilege_escalation_detector is not None and task_result.tool_calls:
                    try:
                        self.privilege_escalation_detector.analyze_privilege_chain(
                            task_result.task_id, task_result.tool_calls
                        )
                    except Exception as _sec_exc:
                        logger.debug("PrivilegeEscalationDetector 실패 (무시): %s", _sec_exc)
                # Layer 2: Tool Chain Attack — 연속 도구 호출 공격 패턴 감지
                if self.tool_chain_attack_detector is not None and task_result.tool_calls:
                    try:
                        _sec_tool_seq: List[str] = []
                        for _stc in task_result.tool_calls:
                            if isinstance(_stc, dict):
                                _sec_tool_seq.append(_stc.get("tool_name") or _stc.get("tool") or _stc.get("name", "unknown"))
                            else:
                                _sec_tool_seq.append(str(_stc))
                        self.tool_chain_attack_detector.analyze_tool_chain(task_result.task_id, _sec_tool_seq)
                    except Exception as _sec_exc:
                        logger.debug("ToolChainAttackDetector 실패 (무시): %s", _sec_exc)

            # Layer1: Hallucination Detection (opt-in, rule-based, free)
            _eff_response_hall = response if response is not None else task_result.response
            _eff_request_hall = request or task_result.question
            # context 파라미터가 없으면 task_result.context 로 fallback
            _eff_context_hall = context or task_result.context
            if self.enable_hallucination_detection and _eff_context_hall and _eff_response_hall:
                try:
                    # Convert ground_truth to string if needed
                    ground_truth_str = None
                    if ground_truth is not None:
                        if isinstance(ground_truth, str):
                            ground_truth_str = ground_truth
                        else:
                            ground_truth_str = str(ground_truth)
                    elif task_result.ground_truth is not None:
                        ground_truth_str = task_result.ground_truth

                    self.hallucination_detector.detect_hallucination(
                        task_id=task_result.task_id,
                        response=_eff_response_hall,
                        context=_eff_context_hall,
                        ground_truth=ground_truth_str,
                        request=_eff_request_hall
                    )
                    # Context Recall / Precision 근사 계산 (RAG 지표 대체)
                    self.hallucination_detector.track_rag_task(
                        task_id=task_result.task_id,
                        response=_eff_response_hall,
                        context=_eff_context_hall,
                        ground_truth=ground_truth_str,
                    )
                except (AttributeError, KeyError, TypeError) as _hall_exc:
                    logger.warning(
                        "Hallucination detection failed for %s: %s",
                        task_result.task_id, _hall_exc, exc_info=True,
                    )
                except Exception as _hall_exc:
                    logger.debug("Hallucination detection unexpected error for %s: %s", task_result.task_id, _hall_exc, exc_info=True)
    
            # Auto-trigger: Quality Evaluation (response + request 있을 때 자동 평가)
            # _eff_request / _eff_response are pre-computed before the lock (L1152-1153)
            if _eff_request and _eff_response:
                if task_result.task_id not in self.quality_evaluator._task_ids:
                    try:
                        _gt_str = str(ground_truth) if ground_truth is not None else task_result.ground_truth
                        _ee = expected_elements or []
                        # expected_elements 없으면 ground_truth에서 자동 추출
                        if not _ee and _gt_str:
                            _ee = [
                                w for w in _RE_NON_WORD.sub('', _gt_str).split()
                                if len(w) >= 2 and w.lower() not in _QUALITY_EVAL_STOPWORDS
                            ][:10]
                        self.quality_evaluator.evaluate_response(
                            task_id=task_result.task_id,
                            response=_eff_response,
                            request=_eff_request,
                            expected_elements=_ee,
                            ground_truth=_gt_str,
                        )
                    except (AttributeError, KeyError, TypeError) as _q_exc:
                        logger.warning(
                            "Auto quality evaluation failed for %s: %s",
                            task_result.task_id, _q_exc, exc_info=True,
                        )
                    except Exception as _q_exc:
                        logger.debug("Auto quality evaluation unexpected error for %s: %s", task_result.task_id, _q_exc, exc_info=True)
    
            # Auto-trigger: Accuracy Evaluation (response + ground_truth 있고, accuracy_score 미지정일 때)
            # Note: accuracy_score=0.0 은 유효한 점수(완전히 틀림)이므로 재계산하지 않는다.
            _eff_gt = ground_truth if ground_truth is not None else task_result.ground_truth
            if _eff_response and _eff_gt:
                _has_score = task_result.accuracy_score is not None
                if not _has_score and task_result.task_id not in self.accuracy_evaluator._task_ids:
                    try:
                        self.accuracy_evaluator.add_evaluation(
                            task_id=task_result.task_id,
                            ground_truth=str(_eff_gt),
                            prediction=_eff_response,
                            task_type=task_result.task_type,
                        )
                    except (AttributeError, KeyError, TypeError) as _acc_exc:
                        logger.warning(
                            "Auto accuracy evaluation failed for %s: %s",
                            task_result.task_id, _acc_exc, exc_info=True,
                        )
                    except Exception as _acc_exc:
                        logger.debug("Auto accuracy evaluation unexpected error for %s: %s", task_result.task_id, _acc_exc, exc_info=True)

        # G3: Multimodal metrics — extra 딕셔너리에 이미지/오디오/비디오 키가 있을 때만 호출
        _extra = getattr(task_result, "extra", {}) or {}
        if _extra.get("image_count") or _extra.get("audio_duration_seconds") or _extra.get("video_frames"):
            try:
                self.multimodal_tracker.track_multimodal(task_result)
            except Exception as _mm_exc:
                logger.debug("multimodal_tracker.track_multimodal 실패 (무시): %s", _mm_exc)

        # M1: ImplicitFeedbackTracker — extra 필드에 피드백 신호 있으면 자동 기록
        _extra_fb = getattr(task_result, "extra", {}) or {}
        _fb_type = _extra_fb.get("feedback_type") or _extra_fb.get("feedback")
        _fb_score = _extra_fb.get("feedback_score") or _extra_fb.get("user_rating")
        if _fb_type or _fb_score is not None:
            try:
                if hasattr(self, "feedback_tracker") and self.feedback_tracker is not None:
                    _fb_val = _fb_score if _fb_score is not None else (1.0 if _fb_type == "positive" else 0.0)
                    _fb_label = str(_fb_type) if _fb_type else ("positive" if _fb_val >= 0.5 else "negative")
                    # ImplicitFeedbackTracker.record() requires a valid ALL_FEEDBACK_TYPES value.
                    # Map generic labels to supported types; fall back to thumbs_up / thumbs_down.
                    from .feedback import ALL_FEEDBACK_TYPES as _ALL_FB_TYPES
                    if _fb_label not in _ALL_FB_TYPES:
                        _fb_label = "thumbs_up" if _fb_val >= 0.5 else "thumbs_down"
                    self.feedback_tracker.record(
                        task_id=task_result.task_id,
                        feedback_type=_fb_label,
                        metadata={"auto_recorded": True, "score": float(_fb_val)},
                    )
            except Exception as _fb_exc:
                logger.debug("ImplicitFeedbackTracker 자동 기록 실패 (무시): %s", _fb_exc)

        # OTEL 스팬 발행 (opt-in, no-op if not configured)
        self._emit_otel_span(task_result)

        # Task 2: auto_save — N개 기록마다 save_to_file() 자동 호출 (debounced)
        if self.auto_save:
            with self._auto_save_lock:
                self._auto_save_counter += 1
                _should_save = (self._auto_save_counter % self._auto_save_interval == 0)
            if _should_save:
                try:
                    self.save_to_file(self._auto_save_filename)
                    logger.debug(
                        "auto_save: %d개 기록 후 '%s' 저장 완료",
                        self._auto_save_counter, self._auto_save_filename,
                    )
                except Exception as _as_exc:
                    logger.debug("auto_save 저장 실패 (무시): %s", _as_exc)

        return self

    def _emit_otel_span(self, result: "TaskResult") -> None:
        """OTEL 스팬 발행. OTELProvider 미활성화 시 즉시 반환.

        기존 JSON 저장 경로에 영향을 주지 않는다.
        opentelemetry-sdk 미설치 또는 setup_otel() 미호출 시 no-op.
        """
        try:
            from agent_evaluator.core.otel import get_provider

            provider = get_provider()
            if provider is None or not provider.enabled:
                return

            # OpenInference 표준 속성 — Phoenix UI 컬럼 표시에 필요
            # question/response는 Playground 재현과 Evaluators 탭 표시에 필수
            input_val = getattr(result, "question", None) or result.task_id
            output_val = getattr(result, "response", None) or str(result.completion_score)
            ground_truth_val = getattr(result, "ground_truth", None) or ""
            # task_type 에서 간결한 레이블 추출 (예: TaskType.QA → "qa")
            # TaskResult.__post_init__ 에서 이미 소문자 정규화됨
            type_label = str(result.task_type).split(".")[-1].lower()
            # 스팬 이름: "ae.task/{task_type}/{task_id}" — Phoenix name 컬럼으로 구분 가능
            span_name = f"ae.task/{type_label}/{result.task_id}"
            span_kind = _OTEL_SPAN_KIND_MAP.get(type_label, "LLM")
            # 토큰 분류 (Phoenix Cost/Token usage 차트용)
            # tokens_used가 dict이면 input/output 분리, 정수이면 total로 처리
            tokens = result.tokens_used if isinstance(result.tokens_used, dict) else {}
            prompt_tokens = tokens.get("input", 0)
            completion_tokens = tokens.get("output", 0)
            # 정수형 tokens_used는 total에 반영 (prompt/completion 분리 불가)
            if not isinstance(result.tokens_used, dict) and result.tokens_used:
                int_total = int(result.tokens_used)
                # prompt 80% / completion 20% 근사 분할 (Phoenix Cost 차트 표시용)
                prompt_tokens = int(int_total * 0.8)
                completion_tokens = int_total - prompt_tokens
            # llm.model_name: Phoenix Cost/Top-models 차트 그룹핑 키
            # tokens_used dict의 "model" 키 → PerformanceMonitor.model_name → "ae/unspecified" 순으로 fallback
            # 신규 모델은 _PHOENIX_MODEL_ALIAS 로 Phoenix 가격 테이블 등록명으로 변환
            raw_model = tokens.get("model", "") or self.model_name or "ae/unspecified"
            model_name = _PHOENIX_MODEL_ALIAS.get(raw_model, raw_model)

            # metadata: 스팬 상세 탭 커스텀 정보 (JSON 문자열)
            metadata_dict: Dict[str, Any] = {"task_type": type_label}
            if result.framework:
                metadata_dict["framework"] = result.framework
            if getattr(result, "partial_reason", None):
                metadata_dict["partial_reason"] = result.partial_reason

            attributes: Dict[str, Any] = {
                # Phoenix UI: kind / input / output 컬럼
                "openinference.span.kind": span_kind,
                "input.value": str(input_val),
                "output.value": str(output_val),
                # Phoenix Sessions 탭 그룹핑
                "session.id": self._otel_session_id,
                # 출처 레이블 — 어느 평가 스크립트/세션에서 발생한 스팬인지 식별
                **({"ae.source": self._session_label} if self._session_label else {}),
                # OpenInference 메타데이터
                "metadata": json.dumps(metadata_dict, ensure_ascii=False),
                # OpenInference LLM 속성 — Cost/Token usage 차트용
                "llm.token_count.prompt": prompt_tokens,
                "llm.token_count.completion": completion_tokens,
                "llm.token_count.total": prompt_tokens + completion_tokens,
                "llm.model_name": str(model_name),
                # Agent Evaluator 고유 지표 (None → 기본값으로 대체)
                "ae.task_id": result.task_id or "",
                "ae.task_type": str(result.task_type),
                "ae.success": bool(result.success),
                "ae.completion_score": float(result.completion_score or 0.0),
                "ae.accuracy_score": float(result.accuracy_score or 0.0),
                "ae.execution_time": float(result.execution_time or 0.0),
                "ae.tokens_used": prompt_tokens + completion_tokens,
                "ae.tool_calls_count": len(result.tool_calls) if result.tool_calls else 0,
                "ae.attempts": int(result.attempts or 0),
                "ae.framework": getattr(result, "framework", None) or "native",
                "ae.anomaly_detection_enabled": bool(getattr(self, "enable_anomaly_detection", False)),
            }

            # D1: 할루시네이션 점수 + 품질 점수를 스팬 속성으로 직접 포함
            # (Phoenix 필터링 및 검색에 활용 가능)
            try:
                _hal_data_d1 = self.hallucination_detector.get_hallucination_rate()
                if _hal_data_d1.get("total_evaluated", 0) > 0:
                    attributes["ae.hallucination_rate"] = float(_hal_data_d1.get("overall_rate", 0.0))
            except Exception as _e:
                logger.debug("OTEL attr skipped (hallucination_rate): %s", _e)
            try:
                _qual_data_d1 = self.quality_evaluator.get_quality_metrics()
                if _qual_data_d1.get("total_evaluated", 0) > 0:
                    _raw_q_d1 = float(_qual_data_d1.get("avg_total_score", 0.0))
                    attributes["ae.quality_score"] = round(min(_raw_q_d1 / 10.0, 1.0), 4)
            except Exception as _e:
                logger.debug("OTEL attr skipped (quality_score): %s", _e)

            # LLM Judge 종합 점수 — Phoenix Evaluators 탭 필터링 지원
            try:
                _lj = getattr(result, "llm_judge", None)
                if isinstance(_lj, dict) and _lj:
                    _lj_overall = _lj.get("overall") or _lj.get("score") or _lj.get("avg_score")
                    if _lj_overall is not None:
                        attributes["ae.llm_judge_score"] = round(float(_lj_overall), 4)
                    _lj_completeness = _lj.get("completeness")
                    if _lj_completeness is not None:
                        attributes["ae.llm_judge_completeness"] = round(float(_lj_completeness), 4)
                    _lj_relevance = _lj.get("relevance")
                    if _lj_relevance is not None:
                        attributes["ae.llm_judge_relevance"] = round(float(_lj_relevance), 4)
                    _lj_factual = _lj.get("factual_consistency")
                    if _lj_factual is not None:
                        attributes["ae.llm_judge_factual"] = round(float(_lj_factual), 4)
            except Exception as _e:
                logger.debug("OTEL attr skipped (llm_judge): %s", _e)

            # Phoenix Prompts 탭 — llm.prompts / input.mime_type 속성으로 프롬프트 추적 활성화
            # Playground 재현 및 Prompts 메뉴 연동에 필요한 OpenInference 표준 속성
            try:
                if input_val:
                    _prompt_msgs = [{"role": "user", "content": str(input_val)}]
                    if ground_truth_val:
                        _prompt_msgs.append({"role": "assistant", "content": str(ground_truth_val)})
                    attributes["llm.prompts"] = json.dumps(_prompt_msgs, ensure_ascii=False)
                    attributes["input.mime_type"] = "text/plain"
                    attributes["output.mime_type"] = "text/plain"
            except Exception as _e:
                logger.debug("OTEL attr skipped (llm.prompts): %s", _e)

            # 보안 이벤트 수 — security_mode=True 시 탐지된 위협 총계
            try:
                _sec = getattr(result, "security_metrics", None)
                if isinstance(_sec, dict) and _sec:
                    _sec_input = _sec.get("input_security", {}) or {}
                    _sec_output = _sec.get("output_leakage", {}) or {}
                    _sec_auth = _sec.get("authorization", {}) or {}
                    _sec_count = (
                        int(_sec_input.get("inputs_with_threats", 0) or 0)
                        + int(_sec_output.get("outputs_with_leakage", 0) or 0)
                        + int(_sec_auth.get("unauthorized_calls", 0) or 0)
                    )
                    attributes["ae.security_events_count"] = _sec_count
            except Exception as _e:
                logger.debug("OTEL attr skipped (security_events_count): %s", _e)

            # ae.tool_names — 사용된 도구 이름 목록 (Phoenix 도구별 필터링 지원)
            try:
                if result.tool_calls:
                    _tool_name_list = []
                    for _tc in result.tool_calls:
                        if isinstance(_tc, dict):
                            _tn = _tc.get("tool_name") or _tc.get("tool") or _tc.get("name", "unknown")
                        else:
                            _tn = str(_tc)
                        _tool_name_list.append(str(_tn))
                    if _tool_name_list:
                        attributes["ae.tool_names"] = json.dumps(_tool_name_list, ensure_ascii=False)
            except Exception as _e:
                logger.debug("OTEL attr skipped (tool_names): %s", _e)

            attributes.update({
                # Playground 재현용 — question/response/ground_truth 전문 기록
                "ae.question": str(input_val)[:_OTEL_ATTR_MAX_LEN],
                "ae.response": str(output_val)[:_OTEL_ATTR_MAX_LEN],
                "ae.ground_truth": str(ground_truth_val)[:_OTEL_ATTR_MAX_LEN],
                # Experiments 탭 그룹핑 — begin_experiment() 호출 시 자동 설정
                **({"ae.experiment_id": self._phoenix_experiment_id} if self._phoenix_experiment_id else {}),
                **({"ae.experiment_name": self._phoenix_experiment_name} if self._phoenix_experiment_name else {}),
            })

            # Phoenix Datasets 탭 — 골든 데이터셋에서 실행된 태스크에 dataset 컨텍스트 첨부
            try:
                if self._phoenix_dataset_id:
                    attributes["dataset.id"] = str(self._phoenix_dataset_id)
                if self._golden_datasets:
                    # 가장 최근 로드된 골든 데이터셋 이름을 dataset.version 으로 노출
                    _ds_name = getattr(self._golden_datasets[0], "name", None) if hasattr(self._golden_datasets[0], "name") else None
                    if _ds_name:
                        attributes["dataset.version"] = str(_ds_name)
                    attributes["dataset.record_count"] = len(self._golden_datasets)
            except Exception as _e:
                logger.debug("OTEL attr skipped (dataset): %s", _e)

            # retrieval.documents — INFORMATION_RETRIEVAL 스팬에 RAG 컨텍스트 첨부
            if type_label == "information_retrieval" and getattr(result, "context", None):
                try:
                    # OTEL 속성 크기 제한 준수 — 긴 컨텍스트 앞부분만 전송
                    ctx_text = str(result.context)[:_OTEL_ATTR_MAX_LEN]
                    docs = [{"document.id": "0", "document.content": ctx_text}]
                    attributes["retrieval.documents"] = json.dumps(docs, ensure_ascii=False)
                except Exception as _e:
                    logger.debug("retrieval.documents 속성 직렬화 실패 (무시): %s", _e)

            # span start_time 계산 — Phoenix latency 차트는 span duration을 사용한다.
            # 현재 시각 기준으로 역산 → Phoenix "Last 15 Min" 등 시간 필터에 항상 표시됨.
            # (result.timestamp가 시뮬레이션 과거 시간이어도 Phoenix UI에 정상 노출)
            # start_time = now - execution_time (나노초 단위)
            start_time_ns: Optional[int] = None
            try:
                import time as _time_mod
                exec_ns = int((result.execution_time or 0.0) * 1_000_000_000)
                end_ns = int(_time_mod.time() * 1_000_000_000)  # 현재 시각 기준
                start_time_ns = max(0, end_ns - exec_ns)
            except Exception as _e:
                logger.debug("start_time_ns 역산 실패, SDK 기본값 사용: %s", _e)

            with provider.span(span_name, attributes, start_time_ns=start_time_ns) as span:
                # 실패 태스크 → SpanStatus ERROR 설정 (Traces with errors 차트용)
                if not result.success and span is not None:
                    try:
                        from opentelemetry.trace import StatusCode
                        span.set_status(StatusCode.ERROR, "task failed")
                    except Exception as _e:
                        logger.debug("span StatusCode.ERROR 설정 실패 (무시): %s", _e)
                # span_id 캡처 → Phoenix Annotation API 대기열에 추가
                if span is not None:
                    try:
                        ctx = span.get_span_context()
                        if ctx and ctx.is_valid:
                            # hallucination: HallucinationDetector.get_hallucination_rate()
                            # overall_rate (0–1): 낮을수록 좋음 → annotation score = rate
                            hal_score: Optional[float] = None
                            try:
                                hal_data = self.hallucination_detector.get_hallucination_rate()
                                if hal_data.get("total_evaluated", 0) > 0:
                                    hal_score = float(hal_data.get("overall_rate", 0.0))
                            except Exception as _e:
                                logger.debug("hallucination score 추출 실패 (무시): %s", _e)
                            # quality: ResponseQualityEvaluator.get_quality_metrics()
                            # avg_total_score (0–10) → 0–1 정규화
                            qual_score: Optional[float] = None
                            try:
                                qual_data = self.quality_evaluator.get_quality_metrics()
                                if qual_data.get("total_evaluated", 0) > 0:
                                    raw_q = float(qual_data.get("avg_total_score", 0.0))
                                    qual_score = round(min(raw_q / 10.0, 1.0), 4)
                            except Exception as _e:
                                logger.debug("quality score 추출 실패 (무시): %s", _e)
                            self._pending_annotations.append({
                                "span_id": format(ctx.span_id, "016x"),
                                "accuracy": float(result.accuracy_score or 0.0),
                                "completion": float(result.completion_score or 0.0),
                                "success": 1.0 if result.success else 0.0,
                                "hallucination": hal_score,
                                "quality": qual_score,
                                "latency": float(result.execution_time or 0.0),
                                "tool_calls": float(len(result.tool_calls) if result.tool_calls else 0),
                                "attempts": float(result.attempts or 1),
                            })
                    except Exception as _e:
                        logger.debug("span_id 캡처 / annotation 추가 실패 (무시): %s", _e)

                # Tool call 자식 스팬 — Phoenix "Tool spans" 차트용
                # tool_calls 가 있으면 항상 발행 (enable_otel_child_spans 불필요)
                if result.tool_calls:
                    try:
                        _tool_base_ns = start_time_ns or int(_time_mod.time() * 1_000_000_000)
                        _exec_ns = int((result.execution_time or 0.0) * 1_000_000_000)
                        _n_tools = len(result.tool_calls)
                        # 도구 호출을 실행 시간 안에 균등 배치 (순서 보존)
                        _tool_slot_ns = max(1, _exec_ns // max(_n_tools, 1))
                        for _idx, _tc in enumerate(result.tool_calls):
                            if not isinstance(_tc, dict):
                                continue
                            _tool_name = (
                                _tc.get("tool_name") or _tc.get("tool")
                                or _tc.get("name") or f"tool_{_idx}"
                            )
                            _tool_args = _tc.get("arguments") or _tc.get("args") or {}
                            _tool_result_val = _tc.get("result") or _tc.get("output") or ""
                            _tool_success = bool(_tc.get("success", True))
                            _tool_attrs: Dict[str, Any] = {
                                "openinference.span.kind": "TOOL",
                                "tool.name": str(_tool_name),
                                "input.value": (
                                    json.dumps(_tool_args, ensure_ascii=False)
                                    if isinstance(_tool_args, dict)
                                    else str(_tool_args)
                                )[:_OTEL_ATTR_MAX_LEN],
                                "output.value": str(_tool_result_val)[:_OTEL_ATTR_MAX_LEN],
                                "ae.task_id": result.task_id or "",
                                "ae.tool_index": _idx,
                                "session.id": self._otel_session_id,
                            }
                            _tool_span_name = f"ae.tool/{result.task_id}/{_tool_name}"
                            _tool_start_ns = _tool_base_ns + _idx * _tool_slot_ns
                            try:
                                with provider.span(_tool_span_name, _tool_attrs, start_time_ns=_tool_start_ns) as _ts:
                                    if not _tool_success and _ts is not None:
                                        try:
                                            from opentelemetry.trace import StatusCode as _SC
                                            _ts.set_status(_SC.ERROR, "tool call failed")
                                        except Exception as _e:
                                            logger.debug("OTEL attr skipped (tool span status): %s", _e)
                            except Exception as _tse:
                                logger.debug("tool call 자식 스팬 발행 실패 (무시): %s", _tse)
                    except Exception as _te:
                        logger.debug("tool_calls 자식 스팬 처리 실패 (무시): %s", _te)

                # D2: 자식 스팬 — chain_steps 각 항목을 별도 OTEL 자식 스팬으로 발행
                # 부모 span context 안에서 생성해야 parent-child 관계가 성립함
                if self.enable_otel_child_spans:
                    try:
                        _extra = getattr(result, "extra", {}) or {}
                        _chain_steps = result.chain_steps or _extra.get("streaming_steps", [])
                        if _chain_steps:
                            _step_offset = (start_time_ns or int(_time_mod.time() * 1_000_000_000))
                            for _idx, _step in enumerate(_chain_steps):
                                _step_name = _step.get("name") or _step.get("type") or f"step_{_idx}"
                                _step_time_val = float(_step.get("execution_time") or _step.get("timestamp") or 0.0)
                                _child_start_ns = _step_offset + int(_step.get("timestamp", 0) * 1_000_000_000) if start_time_ns else None
                                _child_attrs: Dict[str, Any] = {
                                    "openinference.span.kind": "CHAIN",
                                    "ae.task_id": result.task_id or "",
                                    "ae.step_index": _idx,
                                    "ae.step_name": str(_step_name),
                                    "ae.step_type": str(_step.get("type", "step")),
                                    "ae.step_success": bool(_step.get("success", True)),
                                    "ae.execution_time": float(_step_time_val),
                                }
                                if _step.get("input"):
                                    _child_attrs["input.value"] = str(_step["input"])[:_OTEL_ATTR_MAX_LEN]
                                if _step.get("output"):
                                    _child_attrs["output.value"] = str(_step["output"])[:_OTEL_ATTR_MAX_LEN]
                                _child_span_name = f"ae.step/{result.task_id}/{_step_name}"
                                try:
                                    with provider.span(_child_span_name, _child_attrs, start_time_ns=_child_start_ns):
                                        pass
                                except Exception as _cs_exc:
                                    logger.debug("자식 스팬 발행 실패 (무시): %s", _cs_exc)
                    except Exception as _child_exc:
                        logger.debug("enable_otel_child_spans 처리 실패 (무시): %s", _child_exc)

            # Phoenix Metrics 탭 — 집계 지표 전송
            try:
                from agent_evaluator.core.otel import get_metrics
                m = get_metrics()
                if m and m.enabled:
                    task_attrs = {"task_type": type_label, "framework": attributes["ae.framework"]}
                    # ae.tcr는 세션 단위 지표 — save_to_file()에서 별도 전송, per-task 전송 제외
                    m.record("ae.latency_seconds", float(result.execution_time), task_attrs)
                    m.record("ae.accuracy", float(result.accuracy_score), task_attrs)
                    tokens_total = (
                        result.tokens_used.get("total", 0)
                        if isinstance(result.tokens_used, dict)
                        else int(result.tokens_used or 0)
                    )
                    m.record("ae.tokens_total", float(tokens_total), task_attrs)
                    m.record("ae.error_rate", 0.0 if result.success else 100.0, task_attrs)
            except Exception as _m_exc:
                logger.debug("_emit_otel_span: metrics 전송 실패: %s", _m_exc)
        except Exception as _otel_exc:
            logger.debug("_emit_otel_span: 스팬 발행 실패: %s", _otel_exc)

    def _flush_phoenix_annotations(self) -> None:
        """누적된 평가 점수를 Phoenix Annotation API로 일괄 전송한다.

        save_to_file() 끝에서 호출된다. Phoenix가 실행 중이지 않거나
        OTEL 미설정 시 no-op.

        전송 지표 (annotator_kind="LLM"):
            - accuracy      : ae.accuracy_score  (0–1)
            - completion    : ae.completion_score (0–1)
            - success       : 1.0 성공 / 0.0 실패
            - hallucination : hallucination_score (0–1, None이면 생략)
            - quality       : quality_score       (0–1, None이면 생략)
            - latency       : execution_time (초)
            - tool_calls    : tool_calls count (정수)
            - attempts      : retry 횟수

        타이밍 처리:
            force_flush() 이후에도 Phoenix가 span을 내부 DB에 인덱싱하는 데
            추가 시간이 필요할 수 있다 (비동기 처리). 이를 위해 재시도 로직을 적용한다.
        """
        import time

        if not self._pending_annotations:
            return
        try:
            from agent_evaluator.core.otel import get_provider
            provider = get_provider()
            if provider is None or not provider.enabled or not provider.base_endpoint:
                return

            # BatchSpanProcessor 플러시 — Phoenix /v1/traces로 전송 완료 대기
            provider.force_flush(timeout_ms=3000)

            data: List[Dict[str, Any]] = []
            for ann in self._pending_annotations:
                span_id = ann["span_id"]
                # 전송 대상 지표: None이면 해당 스팬에서 생략
                metrics_to_send = [
                    ("accuracy",      ann.get("accuracy"),      "ae.accuracy_score (0–1)"),
                    ("completion",    ann.get("completion"),    "ae.completion_score (0–1)"),
                    ("success",       ann.get("success"),       "1.0=pass / 0.0=fail"),
                    ("hallucination", ann.get("hallucination"), "hallucination_score (0–1, 낮을수록 좋음)"),
                    ("quality",       ann.get("quality"),       "response quality overall score (0–1)"),
                    ("latency_s",     ann.get("latency"),       "execution_time in seconds"),
                    ("tool_calls",    ann.get("tool_calls"),    "number of tool calls"),
                    ("attempts",      ann.get("attempts"),      "retry attempt count"),
                ]
                for metric, score, explanation in metrics_to_send:
                    if score is None:
                        continue
                    # hallucination: 낮을수록 good → label 반전
                    if metric == "hallucination":
                        label = "pass" if score <= 0.3 else "fail"
                    elif metric in ("latency_s", "tool_calls", "attempts"):
                        label = "ok"  # 방향성이 없는 수치형 지표
                    else:
                        label = "pass" if score >= 0.5 else "fail"
                    data.append({
                        "span_id": span_id,
                        "name": metric,
                        "annotator_kind": "LLM",
                        "result": {
                            "score": round(float(score), 4),
                            "label": label,
                            "explanation": f"Agent Evaluator: {explanation}",
                        },
                        "metadata": {},
                    })

            payload = json.dumps({"data": data}).encode()
            url = f"{provider.base_endpoint}/v1/span_annotations"

            # 재시도 로직: Phoenix가 span을 비동기로 인덱싱하므로
            # force_flush 직후 POST하면 404가 반환될 수 있다.
            # 0.5s 간격으로 최대 3회 재시도한다.
            _MAX_RETRIES = 3
            _RETRY_DELAY = 0.5  # seconds
            last_exc: Optional[Exception] = None

            for attempt in range(_MAX_RETRIES):
                if attempt > 0:
                    time.sleep(_RETRY_DELAY)
                try:
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        logger.info(
                            "Phoenix annotations 전송 완료: %d건, HTTP %d (시도 %d/%d)",
                            len(data),
                            resp.status,
                            attempt + 1,
                            _MAX_RETRIES,
                        )
                    self._pending_annotations.clear()
                    return  # 성공
                except urllib.error.HTTPError as http_exc:
                    body = ""
                    try:
                        body = http_exc.read().decode("utf-8", errors="replace")[:200]
                    except Exception as _e:
                        logger.debug("HTTP 에러 바디 읽기 실패 (무시): %s", _e)
                    last_exc = http_exc
                    logger.warning(
                        "Phoenix annotations HTTP %d (시도 %d/%d): %s",
                        http_exc.code,
                        attempt + 1,
                        _MAX_RETRIES,
                        body,
                    )
                except Exception as exc:
                    last_exc = exc
                    logger.debug(
                        "_flush_phoenix_annotations: 연결 실패 (시도 %d/%d): %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                    )
                    break  # 연결 오류는 재시도해도 소용없음 (Phoenix 미실행)

            if last_exc is not None:
                logger.warning(
                    "Phoenix annotations 전송 최종 실패 (%d건): %s",
                    len(data),
                    last_exc,
                )
        except Exception as exc:
            logger.debug("_flush_phoenix_annotations: 초기화 실패: %s", exc)

    # ---------------------------------------------------------------------------
    # Phoenix Experiments — begin / end
    # ---------------------------------------------------------------------------

    def begin_experiment(
        self,
        name: str,
        dataset_id: Optional[str] = None,
        description: str = "",
        phoenix_endpoint: str = "http://localhost:6006",
    ) -> Optional[str]:
        """Phoenix에 Experiment를 등록하고 experiment_id를 반환한다.

        이후 record_task() 가 발행하는 모든 OTEL 스팬에 ``ae.experiment_id`` /
        ``ae.experiment_name`` attribute가 자동으로 추가되어 Phoenix Experiments
        탭에서 run 단위 성능 비교가 가능해진다.

        Args:
            name: Phoenix UI에 표시될 실험 이름 (예: "v1.2-accuracy-test").
            dataset_id: 연결할 Phoenix dataset_id. GoldenSetBuilder.upload_to_phoenix()
                반환값을 사용. None이면 데이터셋 연결 없이 실험만 생성.
            description: 실험 설명 (옵션).
            phoenix_endpoint: Phoenix 서버 주소 (기본: http://localhost:6006).

        Returns:
            생성된 experiment_id 문자열. Phoenix 미실행 또는 실패 시 None.

        Example::
            exp_id = monitor.begin_experiment("qa-eval-run-v2", dataset_id=ds_id)
            with evaluation_session("run_v2") as m:
                ...
            monitor.end_experiment(report)
        """
        payload: Dict[str, Any] = {"name": name, "description": description}
        if dataset_id:
            payload["dataset_id"] = dataset_id

        url = f"{phoenix_endpoint.rstrip('/')}/v1/experiments"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
                exp_id: Optional[str] = (
                    result.get("data", {}).get("id")
                    or result.get("id")
                )
                if exp_id:
                    self._phoenix_experiment_id = exp_id
                    self._phoenix_experiment_name = name
                    self._phoenix_dataset_id = dataset_id
                    logger.info("Phoenix Experiment 시작: %s (id=%s)", name, exp_id)
                return exp_id
        except Exception as exc:
            logger.debug("begin_experiment: Phoenix 연결 실패: %s", exc)
            return None

    def end_experiment(
        self,
        report: Optional[Any] = None,
        phoenix_endpoint: str = "http://localhost:6006",
    ) -> None:
        """현재 Experiment에 최종 집계 지표를 Annotation으로 전송하고 세션을 닫는다.

        Args:
            report: monitor.generate_report() 결과 (EvaluationReport). None이면
                    지표 전송 없이 실험 ID만 초기화한다.
            phoenix_endpoint: Phoenix 서버 주소.
        """
        if not self._phoenix_experiment_id:
            return

        if report is not None:
            try:
                # Experiment run 단위 요약 지표를 별도 annotation으로 전송
                summary = {
                    "experiment_id": self._phoenix_experiment_id,
                    "experiment_name": self._phoenix_experiment_name or "",
                    "tcr": getattr(report, "task_completion_rate", None),
                    "accuracy": getattr(report, "overall_accuracy", None),
                    "avg_latency": getattr(report, "average_latency", None),
                    "total_tasks": getattr(report, "total_tasks", None),
                }
                url = (
                    f"{phoenix_endpoint.rstrip('/')}/v1/experiments"
                    f"/{self._phoenix_experiment_id}/runs"
                )
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"metadata": summary}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
                logger.info(
                    "Phoenix Experiment 종료: %s — TCR=%.1f%% Accuracy=%.1f%%",
                    self._phoenix_experiment_name,
                    summary.get("tcr") or 0.0,
                    summary.get("accuracy") or 0.0,
                )
            except Exception as exc:
                logger.debug("end_experiment: 지표 전송 실패: %s", exc)

        self._phoenix_experiment_id = None
        self._phoenix_experiment_name = None
        self._phoenix_dataset_id = None

    def record_rag_metrics(
        self,
        faithfulness: Optional[float] = None,
        answer_relevancy: Optional[float] = None,
        context_recall: Optional[float] = None,
        context_precision: Optional[float] = None
    ) -> None:
        """
        Record RAG evaluation metrics

        Args:
            faithfulness: Faithfulness score (0-1)
            answer_relevancy: Answer relevancy score (0-1)
            context_recall: Context recall score (0-1)
            context_precision: Context precision score (0-1)
        """
        with self._lock:
            if faithfulness is not None:
                self._rag_metrics['faithfulness'].append(faithfulness)
            if answer_relevancy is not None:
                self._rag_metrics['answer_relevancy'].append(answer_relevancy)
            if context_recall is not None:
                self._rag_metrics['context_recall'].append(context_recall)
            if context_precision is not None:
                self._rag_metrics['context_precision'].append(context_precision)

    def record_implicit_feedback(
        self,
        task_id: str,
        feedback_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PerformanceMonitor":
        """사용자 암묵적 피드백 기록.

        Args:
            task_id: 피드백 대상 태스크 ID.
            feedback_type: 피드백 유형 ("copy", "thumbs_up", "regenerate", "thumbs_down" 등).
            metadata: 추가 메타데이터 (선택).

        Returns:
            self (메서드 체이닝 지원).

        Example::
            monitor.record_implicit_feedback("t_001", "thumbs_up")
            monitor.record_implicit_feedback("t_002", "regenerate")
        """
        self.feedback_tracker.record(task_id=task_id, feedback_type=feedback_type, metadata=metadata)
        return self

    def get_rag_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of RAG metrics

        Returns:
            Dict containing average and statistics for each RAG metric
        """
        summary = {}

        for metric_name, values in self._rag_metrics.items():
            if values:
                mean_val = statistics.mean(values)
                summary[metric_name] = {
                    'mean': mean_val,      # primary key — use this
                    'average': mean_val,   # deprecated alias; use 'mean' instead
                    'min': min(values),
                    'max': max(values),
                    'std': statistics.stdev(values) if len(values) > 1 else 0.0,
                    'count': len(values)
                }
            else:
                summary[metric_name] = {
                    'mean': 0.0,
                    'average': 0.0,  # deprecated alias
                    'min': 0.0,
                    'max': 0.0,
                    'std': 0.0,
                    'count': 0
                }

        return summary

    def _collect_layer1_metrics(self) -> Dict[str, Any]:
        """Layer 1 지표 수집: TCR, Accuracy, Hallucination, Quality, Latency, Token.

        Returns:
            accuracy_metrics dict (tcr, accuracy_scores, hallucination, quality)
            and efficiency_metrics dict (latency, tokens).
        """
        logger.debug("_collect_layer1_metrics: tcr_tasks=%d, accuracy_evals=%d, hall_detections=%d, quality_evals=%d",
                     len(self.tcr_tracker._tasks),
                     len(self.accuracy_evaluator._evaluations),
                     len(self.hallucination_detector._detections),
                     len(self.quality_evaluator._evaluations))
        accuracy_metrics: Dict[str, Any] = {
            "tcr": self.tcr_tracker.calculate_tcr(),
            "accuracy_scores": self.accuracy_evaluator.get_accuracy_scores(),
            "hallucination": self.hallucination_detector.get_hallucination_rate(),
            "quality": self.quality_evaluator.get_quality_metrics(),
            "rag_metrics": self.hallucination_detector.get_rag_metrics(),
        }
        efficiency_metrics: Dict[str, Any] = {
            "latency": self.latency_tracker.get_latency_stats(),
            "tokens": self.token_tracker.get_usage_stats(),
        }
        return {"accuracy": accuracy_metrics, "efficiency": efficiency_metrics}

    def _collect_layer2_metrics(self) -> Dict[str, Any]:
        """Layer 2 지표 수집: ToolCall, Retry, ToolSelection, Coordination, Workflow.

        Returns:
            efficiency_metrics 에 병합될 dict (tool_efficiency, retries).
        """
        logger.debug(
            "_collect_layer2_metrics: tool_executions=%d, retry_attempts=%d, "
            "selections=%d, interactions=%d, workflow_steps=%d, "
            "escalations=%d, attack_chains=%d",
            len(self.tool_analyzer._executions),
            len(self.retry_tracker._attempts),
            len(self.tool_selection_tracker._selections),
            len(self.agent_coordination_tracker._interactions),
            len(self.workflow_tracker._executions),
            len(self.privilege_escalation_detector._escalation_events)
            if self.privilege_escalation_detector else 0,
            len(self.tool_chain_attack_detector._detections)
            if self.tool_chain_attack_detector else 0,
        )
        _tool_sel_data: Dict[str, Any] = {}
        # M2: 도구별 F1
        try:
            _f1_by_tool = self.tool_selection_tracker.get_f1_by_tool()
            if _f1_by_tool:
                _tool_sel_data["f1_by_tool"] = _f1_by_tool
        except Exception as _e:
            logger.debug("get_f1_by_tool 실패 (무시): %s", _e)

        _coord_data: Dict[str, Any] = {}
        # M3: 상호작용 패턴
        try:
            _patterns = self.agent_coordination_tracker.get_interaction_patterns()
            if _patterns:
                _coord_data["interaction_patterns"] = _patterns
        except Exception as _e:
            logger.debug("get_interaction_patterns 실패 (무시): %s", _e)

        _latency_data: Dict[str, Any] = {}
        # M4: 병목 분석
        try:
            _bottlenecks = self.latency_tracker.analyze_bottlenecks() if hasattr(self.latency_tracker, "analyze_bottlenecks") else {}
            if _bottlenecks:
                _latency_data["bottleneck_analysis"] = _bottlenecks
        except Exception as _e:
            logger.debug("analyze_bottlenecks 실패 (무시): %s", _e)

        _workflow_data: Dict[str, Any] = {}
        # M5: 크리티컬 패스 분석
        try:
            _critical_path = self.workflow_tracker.get_critical_path_analysis() if hasattr(self.workflow_tracker, "get_critical_path_analysis") else {}
            if _critical_path:
                _workflow_data["critical_path_analysis"] = _critical_path
        except Exception as _e:
            logger.debug("get_critical_path_analysis 실패 (무시): %s", _e)

        _result: Dict[str, Any] = {
            "tool_efficiency": self.tool_analyzer.get_efficiency_stats(),
            "retries": self.retry_tracker.get_retry_metrics(),
        }
        if _tool_sel_data:
            _result["tool_selection"] = _tool_sel_data
        if _coord_data:
            _result["coordination"] = _coord_data
        if _latency_data:
            _result["latency_analysis"] = _latency_data
        if _workflow_data:
            _result["workflow_analysis"] = _workflow_data
        return _result

    def _collect_security_metrics(self) -> Dict[str, Any]:
        """보안 지표 수집 (enable_security_metrics=True 일 때만 의미 있음).

        Returns:
            security_metrics dict (layer1_security, layer2_security).
        """
        if not self.enable_security_metrics:
            return {}
        # When enable_security_metrics=True the __init__ block always initialises
        # all five security trackers.  Guard against accidental None to give a
        # clear RuntimeError rather than an AttributeError deep inside a tracker.
        missing = [
            name for name, obj in (
                ("input_sanitizer", self.input_sanitizer),
                ("output_leakage_detector", self.output_leakage_detector),
                ("tool_authorizer", self.tool_authorizer),
                ("privilege_escalation_detector", self.privilege_escalation_detector),
                ("tool_chain_attack_detector", self.tool_chain_attack_detector),
            )
            if obj is None
        ]
        if missing:
            raise MetricComputationError(
                f"enable_security_metrics=True but trackers not initialised: {missing}. "
                "This is an internal SDK bug — please report it."
            )
        return {
            "layer1_security": {
                "input_security": self.input_sanitizer.get_security_stats(),
                "output_leakage": self.output_leakage_detector.get_leakage_stats(),
                "authorization": self.tool_authorizer.get_compliance_stats(),
            },
            "layer2_security": {
                "privilege_escalation": self.privilege_escalation_detector.get_escalation_stats(),
                "attack_detection": self.tool_chain_attack_detector.get_attack_stats(),
            },
        }

    def generate_report(self) -> "EvaluationReport":
        """Generate comprehensive evaluation report"""
        if len(self.tcr_tracker.tasks) == 0:
            logger.warning(
                "generate_report() called with no recorded tasks. "
                "Call record_task() before generate_report() to include task metrics."
            )
        layer1 = self._collect_layer1_metrics()
        layer2 = self._collect_layer2_metrics()
        security_metrics = self._collect_security_metrics()

        accuracy_metrics = layer1["accuracy"]
        efficiency_metrics = {**layer1["efficiency"], **layer2}

        quality_metrics = self.quality_evaluator.get_quality_metrics()

        # M9: 멀티모달 지표
        try:
            if hasattr(self, "multimodal_tracker") and self.multimodal_tracker is not None:
                _mm_summary = self.multimodal_tracker.get_multimodal_summary()
                if _mm_summary and _mm_summary.get("total_tracked", 0) > 0:
                    efficiency_metrics["multimodal_metrics"] = _mm_summary
        except Exception as _e:
            logger.debug("multimodal_metrics 리포트 추가 실패 (무시): %s", _e)

        # v0.9.0+: Harness groups 집계
        extra_metrics: Optional[Dict[str, Any]] = None
        if self.tcr_tracker.tasks:
            try:
                harness_groups = self._compute_harness_groups(
                    tasks=list(self.tcr_tracker.tasks),
                    security_metrics=security_metrics,
                    layer1=layer1,
                    layer2=layer2,
                    ttft_variability_config=self._ttft_variability_config,
                    cost_predictability_config=self._cost_predictability_config,
                )
                if harness_groups:
                    extra_metrics = {"harness_groups": harness_groups}
            except Exception as _hg_exc:
                logger.debug("harness_groups 집계 실패 (무시): %s", _hg_exc)

        report = EvaluationReport(
            period="current_session",
            total_tasks=len(self.tcr_tracker.tasks),
            accuracy_metrics=accuracy_metrics,
            efficiency_metrics=efficiency_metrics,
            quality_metrics=quality_metrics if quality_metrics else {},
            security_metrics=security_metrics,
            alerts=self._generate_alerts(),
            recommendations=self._generate_recommendations(),
            timestamp=datetime.now(),
            extra_metrics=extra_metrics,
        )

        return report

    def _compute_harness_groups(
        self,
        tasks: list,
        security_metrics: dict,
        layer1: Optional[Dict[str, Any]] = None,
        layer2: Optional[Dict[str, Any]] = None,
        ttft_variability_config: Optional[Any] = None,
        cost_predictability_config: Optional[Any] = None,
    ) -> dict:
        """v0.9.1+: Harness Config 지표가 기록된 TaskResult들에서 그룹별 집계 점수를 계산한다.

        Args:
            tasks: PerformanceMonitor.tcr_tracker.tasks 리스트.
            security_metrics: _collect_security_metrics() 결과.

        Returns:
            {A-G: {name, score, status, details}, overall: {score, status, scored_groups}}
        """
        from typing import List as _List
        if not tasks:
            return {}
        n = max(len(tasks), 1)

        def _status(score: Optional[float], warn: float = 0.7, fail: float = 0.5) -> str:
            if score is None:
                return "n/a"
            if score >= warn:
                return "pass"
            if score >= fail:
                return "warn"
            return "fail"

        # ── A 그룹: 목표 달성 (TCR + instruction_adherence + goal_alignment + plan_coherence) ──
        tcr_pct_a = 0.0
        try:
            _tcr_stats_a = self.tcr_tracker.calculate_tcr()
            tcr_pct_a = float(_tcr_stats_a.get("tcr", 0.0))
        except Exception:
            pass

        _ifr_scores = [
            t.extra["instruction_adherence"]["score"]
            for t in tasks
            if (t.extra or {}).get("instruction_adherence") is not None
        ]
        avg_ifr = sum(_ifr_scores) / len(_ifr_scores) if _ifr_scores else None

        _goal_a_vals: _List[float] = []
        for _t in tasks:
            _ga = ((_t.extra or {}).get("goal_alignment") or {})
            if not _ga:
                continue
            _ga_score = float(_ga.get("score", 0.0))
            # use_llm_scoring=True 이고 LLM judge relevance 점수가 있으면 블렌딩 (추가 API 호출 없음)
            if _ga.get("use_llm_scoring"):
                _lj = (_t.extra or {}).get("llm_judge") or {}
                _lj_scores = _lj.get("scores") or {}
                _rel = _lj_scores.get("relevance")
                if _rel is not None:
                    try:
                        _rel_norm = float(_rel) / 5.0  # 0-5 → 0-1 정규화
                        _w = max(0.0, min(1.0, float(_ga.get("llm_blend_weight", 0.5))))
                        _ga_score = _ga_score * (1 - _w) + _rel_norm * _w
                    except (TypeError, ValueError):
                        pass
            _goal_a_vals.append(_ga_score)
        avg_goal_a = sum(_goal_a_vals) / len(_goal_a_vals) if _goal_a_vals else None

        _plan_a_vals: _List[float] = []
        for _t in tasks:
            _pc = ((_t.extra or {}).get("plan_coherence") or {})
            if not _pc:
                continue
            _pc_score = float(_pc.get("score", 0.0))
            # use_llm_scoring=True 이면 기존 LLM judge relevance 점수와 가중 블렌딩
            if _pc.get("use_llm_scoring"):
                _lj_pc = ((_t.extra or {}).get("llm_judge") or {})
                _rel_pc = (_lj_pc.get("scores") or {}).get("relevance")
                if _rel_pc is not None:
                    try:
                        _w_pc = max(0.0, min(1.0, float(_pc.get("llm_blend_weight", 0.5))))
                        _pc_score = _pc_score * (1 - _w_pc) + (float(_rel_pc) / 5.0) * _w_pc
                    except (TypeError, ValueError):
                        pass
            _plan_a_vals.append(_pc_score)
        avg_plan_a = sum(_plan_a_vals) / len(_plan_a_vals) if _plan_a_vals else None

        _subtask_vals = [
            t.extra["subtask_completion"]["completion_rate"]
            for t in tasks
            if (t.extra or {}).get("subtask_completion") is not None
        ]
        avg_subtask = sum(_subtask_vals) / len(_subtask_vals) if _subtask_vals else None

        _cr_vals = [
            t.extra["context_retention"]["retention_score"]
            for t in tasks
            if (t.extra or {}).get("context_retention") is not None
        ]
        avg_context_r = sum(_cr_vals) / len(_cr_vals) if _cr_vals else None

        # knowledge_retention → Group A (Phase 5)
        _kr_vals = [
            t.extra.get("knowledge_retention", {}).get("retention_score")
            for t in tasks
            if (t.extra or {}).get("knowledge_retention") is not None
        ]
        avg_knowledge_ret: Optional[float] = sum(_kr_vals) / len(_kr_vals) if _kr_vals else None

        _a_vals: _List[float] = [tcr_pct_a / 100.0]
        if avg_ifr is not None:
            _a_vals.append(avg_ifr)
        if avg_goal_a is not None:
            _a_vals.append(avg_goal_a)
        if avg_plan_a is not None:
            _a_vals.append(avg_plan_a)
        if avg_subtask is not None:
            _a_vals.append(avg_subtask)
        if avg_context_r is not None:
            _a_vals.append(avg_context_r)
        if avg_knowledge_ret is not None:
            _a_vals.append(avg_knowledge_ret)
        _a_score = float(sum(_a_vals) / len(_a_vals))

        # ── B 그룹: 행동 무결성 (loop, goal_alignment, plan_coherence, state_consistency, deadlock) ──
        _loop_counts = sum(
            1 for t in tasks
            if (t.extra or {}).get("loop_detection", {}).get("detected", False)
        )
        _loop_rate = _loop_counts / n

        avg_goal_align: Optional[float] = None
        _goal_vals: _List[float] = []
        for _t in tasks:
            _ga2 = ((_t.extra or {}).get("goal_alignment") or {})
            if not _ga2:
                continue
            _ga2_score = float(_ga2.get("score", 0.0))
            if _ga2.get("use_llm_scoring"):
                _lj2 = ((_t.extra or {}).get("llm_judge") or {})
                _rel2 = (_lj2.get("scores") or {}).get("relevance")
                if _rel2 is not None:
                    try:
                        _w2 = max(0.0, min(1.0, float(_ga2.get("llm_blend_weight", 0.5))))
                        _ga2_score = _ga2_score * (1 - _w2) + (float(_rel2) / 5.0) * _w2
                    except (TypeError, ValueError):
                        pass
            _goal_vals.append(_ga2_score)
        if _goal_vals:
            avg_goal_align = sum(_goal_vals) / len(_goal_vals)

        avg_plan: Optional[float] = None
        _plan_vals_b: _List[float] = []
        for _t in tasks:
            _pc2 = ((_t.extra or {}).get("plan_coherence") or {})
            if not _pc2:
                continue
            _pc2_score = float(_pc2.get("score", 0.0))
            if _pc2.get("use_llm_scoring"):
                _lj_pc2 = ((_t.extra or {}).get("llm_judge") or {})
                _rel_pc2 = (_lj_pc2.get("scores") or {}).get("relevance")
                if _rel_pc2 is not None:
                    try:
                        _w_pc2 = max(0.0, min(1.0, float(_pc2.get("llm_blend_weight", 0.5))))
                        _pc2_score = _pc2_score * (1 - _w_pc2) + (float(_rel_pc2) / 5.0) * _w_pc2
                    except (TypeError, ValueError):
                        pass
            _plan_vals_b.append(_pc2_score)
        if _plan_vals_b:
            avg_plan = sum(_plan_vals_b) / len(_plan_vals_b)

        _sc_scores = [
            t.extra["state_consistency"]["consistency_score"]
            for t in tasks
            if (t.extra or {}).get("state_consistency") is not None
        ]
        avg_sc = sum(_sc_scores) / len(_sc_scores) if _sc_scores else None
        _deadlock_count = sum(
            1 for t in tasks
            if (t.extra or {}).get("deadlock", {}).get("deadlock_detected", False)
        )
        _deadlock_by_type: Dict[str, int] = {}
        for _t in tasks:
            _dl = (_t.extra or {}).get("deadlock", {})
            if _dl.get("deadlock_detected") and _dl.get("deadlock_type"):
                _dtype = str(_dl["deadlock_type"])
                _deadlock_by_type[_dtype] = _deadlock_by_type.get(_dtype, 0) + 1

        _scope_vals = [
            t.extra["scope"]["scope_score"]
            for t in tasks
            if (t.extra or {}).get("scope") is not None
        ]
        avg_scope_score = sum(_scope_vals) / len(_scope_vals) if _scope_vals else None

        # tool_parameter_safety → Group B (Phase 5)
        _tps_vals = [
            t.extra.get("tool_parameter_safety", {}).get("safety_score")
            for t in tasks
            if (t.extra or {}).get("tool_parameter_safety") is not None
        ]
        avg_tool_param_safety: Optional[float] = (
            sum(_tps_vals) / len(_tps_vals) if _tps_vals else None
        )

        # context_window → Group B (Phase 6)
        _cw_scores = [
            t.extra.get("context_window", {}).get("context_window_score")
            for t in tasks
            if t.extra and t.extra.get("context_window")
        ]
        _avg_context_window: Optional[float] = (
            sum(_cw_scores) / len(_cw_scores) if _cw_scores else None
        )

        _bint_vals = [max(0.0, 1.0 - _loop_rate)]
        if avg_goal_align is not None:
            _bint_vals.append(avg_goal_align)
        if avg_plan is not None:
            _bint_vals.append(avg_plan)
        if avg_sc is not None:
            _bint_vals.append(avg_sc)
        if _deadlock_count > 0:
            _bint_vals.append(max(0.0, 1.0 - _deadlock_count / n))
        if avg_scope_score is not None:
            _bint_vals.append(avg_scope_score)
        if avg_tool_param_safety is not None:
            _bint_vals.append(avg_tool_param_safety)
        if _avg_context_window is not None:
            _bint_vals.append(_avg_context_window)
        _bint_score = sum(_bint_vals) / len(_bint_vals)

        # ── C 그룹: 신뢰성 (TCR + SLA breach) ──
        tcr_pct = 0.0
        try:
            _tcr_stats = self.tcr_tracker.calculate_tcr()
            tcr_pct = float(_tcr_stats.get("tcr", 0.0))
        except Exception:
            pass

        _rel_vals: _List[float] = [tcr_pct / 100.0]

        _sla_results = [
            t.extra["sla"]
            for t in tasks
            if (t.extra or {}).get("sla") is not None
        ]
        _sla_breach_count = sum(1 for s in _sla_results if not s.get("sla_met", True))
        _sla_breach_rate = _sla_breach_count / len(_sla_results) if _sla_results else None
        if _sla_breach_rate is not None:
            _rel_vals.append(max(0.0, 1.0 - _sla_breach_rate))

        # reproducibility → Group C
        _repro_scores = [
            t.extra["reproducibility"]["score"]
            for t in tasks
            if (t.extra or {}).get("reproducibility") is not None
        ]
        avg_reproducibility: Optional[float] = sum(_repro_scores) / len(_repro_scores) if _repro_scores else None
        if avg_reproducibility is not None:
            _rel_vals.append(avg_reproducibility)

        # fault_tolerance recovery_rate → Group C
        _ft_scores = [
            t.extra["fault_tolerance"]["recovery_rate"]
            for t in tasks
            if (t.extra or {}).get("fault_tolerance") is not None
        ]
        avg_ft: Optional[float] = sum(_ft_scores) / len(_ft_scores) if _ft_scores else None
        if avg_ft is not None:
            _rel_vals.append(avg_ft)

        # graceful_degradation → Group C (Phase 4)
        _deg_scores = [
            t.extra.get("graceful_degradation", {}).get("degradation_score")
            for t in tasks
            if (t.extra or {}).get("graceful_degradation") is not None
        ]
        _avg_degradation: Optional[float] = sum(_deg_scores) / len(_deg_scores) if _deg_scores else None
        if _avg_degradation is not None:
            _rel_vals.append(_avg_degradation)

        # retry_consistency → Group C (Phase 5)
        _rc_scores = [
            t.extra.get("retry_consistency", {}).get("consistency_score")
            for t in tasks
            if (t.extra or {}).get("retry_consistency") is not None
        ]
        _avg_retry_consistency: Optional[float] = (
            sum(_rc_scores) / len(_rc_scores) if _rc_scores else None
        )
        if _avg_retry_consistency is not None:
            _rel_vals.append(_avg_retry_consistency)

        # idempotency → Group C (Phase 6)
        _idem_scores = [
            t.extra.get("idempotency", {}).get("idempotency_score")
            for t in tasks
            if t.extra and t.extra.get("idempotency")
        ]
        _avg_idempotency: Optional[float] = (
            sum(_idem_scores) / len(_idem_scores) if _idem_scores else None
        )
        if _avg_idempotency is not None:
            _rel_vals.append(_avg_idempotency)

        _rel_score = sum(_rel_vals) / len(_rel_vals) if _rel_vals else (tcr_pct / 100.0)

        # ── D 그룹: 성능 효율 (latency + efficiency) ──
        _p95 = 0.0
        try:
            _lat_stats = self.latency_tracker.get_latency_stats()
            _p95 = float(_lat_stats.get("p95", 0.0))
        except Exception:
            pass

        # calibrated_score 우선 사용 (target_cost_per_completion 설정 시); 없으면 efficiency_ratio
        _eff_calibrated_vals: _List[float] = []
        _eff_ratios: _List[float] = []
        for _t in tasks:
            _eff = ((_t.extra or {}).get("efficiency") or {})
            if not _eff:
                continue
            if "calibrated_score" in _eff:
                _eff_calibrated_vals.append(float(_eff["calibrated_score"]))
            _eff_ratios.append(float(_eff.get("efficiency_ratio", 0.0)))
        # calibrated_score가 있는 태스크가 절반 이상이면 calibrated_score 사용
        if len(_eff_calibrated_vals) >= max(1, len(_eff_ratios) // 2):
            avg_eff_calibrated: Optional[float] = (
                sum(_eff_calibrated_vals) / len(_eff_calibrated_vals)
            )
        else:
            avg_eff_calibrated = None
        avg_eff_ratio = sum(_eff_ratios) / len(_eff_ratios) if _eff_ratios else None

        # resource_budget → Group D (Phase 4)
        _budget_scores = [
            t.extra.get("resource_budget", {}).get("budget_score")
            for t in tasks
            if (t.extra or {}).get("resource_budget") is not None
        ]
        _avg_budget: Optional[float] = sum(_budget_scores) / len(_budget_scores) if _budget_scores else None

        # TTFT variability — TTFTVariabilityConfig 파라미터 우선 사용
        _ttft_cfg = ttft_variability_config
        _ttft_min_samples: int = int(getattr(_ttft_cfg, "min_samples", 5)) if _ttft_cfg else 5
        _ttft_max_std: float = float(getattr(_ttft_cfg, "max_stddev_ms", 500.0)) if _ttft_cfg else 500.0
        _ttft_max_ratio: float = float(getattr(_ttft_cfg, "max_p95_p50_ratio", 3.0)) if _ttft_cfg else 3.0
        _ttft_remove_outliers: bool = bool(getattr(_ttft_cfg, "remove_outliers", True)) if _ttft_cfg else True

        _ttft_values: _List[float] = []
        for _t in tasks:
            _ttft = None
            if _t.extra:
                _ttft = _t.extra.get("ttft_ms") or _t.extra.get("ttft")
            if _ttft is not None:
                try:
                    _ttft_values.append(float(_ttft))
                except (TypeError, ValueError):
                    pass

        _avg_ttft_variability: Optional[float] = None
        _ttft_stddev: Optional[float] = None
        _ttft_p50: Optional[float] = None
        _ttft_p95: Optional[float] = None
        if len(_ttft_values) >= _ttft_min_samples:
            _ttft_sorted = sorted(_ttft_values)
            if _ttft_remove_outliers and len(_ttft_sorted) >= 4:
                _q1 = _ttft_sorted[len(_ttft_sorted) // 4]
                _q3 = _ttft_sorted[3 * len(_ttft_sorted) // 4]
                _iqr = _q3 - _q1
                _ttft_clean = [
                    v for v in _ttft_sorted
                    if _q1 - 1.5 * _iqr <= v <= _q3 + 1.5 * _iqr
                ]
            else:
                _ttft_clean = _ttft_sorted

            if len(_ttft_clean) >= 2:
                _ttft_stddev = statistics.stdev(_ttft_clean)
                _ttft_p50 = sorted(_ttft_clean)[len(_ttft_clean) // 2]
                _p95_idx = int(0.95 * len(_ttft_clean))
                _ttft_p95 = sorted(_ttft_clean)[min(_p95_idx, len(_ttft_clean) - 1)]
                _ttft_ratio = _ttft_p95 / max(_ttft_p50, 1.0)
                _std_score = max(0.0, 1.0 - _ttft_stddev / max(_ttft_max_std, 1.0))
                _ratio_score = max(0.0, 1.0 - (_ttft_ratio - 1.0) / max(_ttft_max_ratio - 1.0, 1.0))
                _avg_ttft_variability = (_std_score + _ratio_score) / 2.0

        # cost_predictability — CostPredictabilityConfig 파라미터 우선 사용
        _cost_cfg = cost_predictability_config
        _cost_min_samples: int = int(getattr(_cost_cfg, "min_samples", 5)) if _cost_cfg else 5
        _cost_max_cv: float = float(getattr(_cost_cfg, "max_coefficient_of_variation", 0.3)) if _cost_cfg else 0.3

        _avg_cost_predictability: Optional[float] = None
        if len(tasks) >= _cost_min_samples:
            _costs_by_type: Dict[str, _List[float]] = {}
            for _ct in tasks:
                _ttype_d = str(_ct.task_type) if _ct.task_type else "unknown"
                _tu = _ct.tokens_used or 0
                if isinstance(_tu, dict):
                    _cv_cost = float(_tu.get("total", 0) or _tu.get("output", 0) or 0)
                else:
                    try:
                        _cv_cost = float(_tu)
                    except (TypeError, ValueError):
                        _cv_cost = 0.0
                _costs_by_type.setdefault(_ttype_d, []).append(_cv_cost)
            _cv_scores_d: _List[float] = []
            for _costs_list in _costs_by_type.values():
                if len(_costs_list) >= 2:
                    _cv_mean = statistics.mean(_costs_list)
                    if _cv_mean > 0:
                        _cv_std = statistics.stdev(_costs_list)
                        _cv_val = _cv_std / _cv_mean
                        # Config의 max_cv를 임계값으로 사용: CV가 max_cv 이하면 1.0
                        _cv_score_d = max(0.0, 1.0 - _cv_val / max(_cost_max_cv, 0.01))
                        _cv_scores_d.append(_cv_score_d)
            if _cv_scores_d:
                _avg_cost_predictability = sum(_cv_scores_d) / len(_cv_scores_d)

        # ── D 그룹: insufficient_data 경고 수집 ──
        _d_insufficient: _List[str] = []
        if _ttft_values and len(_ttft_values) < _ttft_min_samples:
            _d_insufficient.append(
                f"ttft_variability: {len(_ttft_values)} samples < min_samples={_ttft_min_samples}"
            )
        if len(tasks) < _cost_min_samples:
            _d_insufficient.append(
                f"cost_predictability: {len(tasks)} tasks < min_samples={_cost_min_samples}"
            )
        if _sla_results and len(_sla_results) < 5:
            _d_insufficient.append(
                f"sla: {len(_sla_results)} samples < recommended_min=5"
            )

        _perf_vals: _List[float] = []
        if _p95 > 0:
            _perf_vals.append(max(0.0, 1.0 - min(1.0, _p95 / 10.0)))
        if avg_eff_calibrated is not None:
            # target_cost_per_completion 기반 calibrated_score 사용 (0-1 직접 사용)
            _perf_vals.append(avg_eff_calibrated)
        elif avg_eff_ratio is not None:
            # Normalize: token-based ratio ~0.001 maps to 1.0; remove conditional to avoid score
            # reversal near the 0.001 boundary (e.g. 0.002 → 0.002 vs 0.0009 → 0.9).
            _norm_eff = min(1.0, avg_eff_ratio * 1000.0)
            _perf_vals.append(_norm_eff)
        if _avg_budget is not None:
            _perf_vals.append(_avg_budget)
        if _avg_ttft_variability is not None:
            _perf_vals.append(_avg_ttft_variability)
        if _avg_cost_predictability is not None:
            _perf_vals.append(_avg_cost_predictability)
        _perf_score = sum(_perf_vals) / len(_perf_vals) if _perf_vals else 0.5

        # ── E 그룹: 보안 (threat_count + CVSS 가중치) ──
        sec_threats = security_metrics.get("threat_count", 0) or 0
        _sec_score_raw = max(0.0, 1.0 - (sec_threats / max(n, 1)))
        _cvss_scores = [
            t.extra["threat_severity"]["weighted_score"]
            for t in tasks
            if (t.extra or {}).get("threat_severity") is not None
        ]
        # compliance → Group E (Phase 4)
        _compliance_scores = [
            t.extra.get("compliance", {}).get("compliance_score")
            for t in tasks
            if (t.extra or {}).get("compliance") is not None
        ]
        _avg_compliance: Optional[float] = (
            sum(_compliance_scores) / len(_compliance_scores) if _compliance_scores else None
        )

        # Native security tracker data (Phase 5 — already stored in TaskResult.extra)
        _native_e_scores: _List[float] = []

        _priv_esc_count = sum(
            1 for t in tasks
            if t.extra and t.extra.get("privilege_escalation", {}).get("detected")
        )
        if _priv_esc_count > 0 or any(t.extra and "privilege_escalation" in t.extra for t in tasks):
            _native_e_scores.append(max(0.0, 1.0 - _priv_esc_count / max(n, 1)))

        _chain_attack_count = sum(
            1 for t in tasks
            if t.extra and t.extra.get("tool_chain_attack", {}).get("detected")
        )
        if _chain_attack_count > 0 or any(t.extra and "tool_chain_attack" in t.extra for t in tasks):
            _native_e_scores.append(max(0.0, 1.0 - _chain_attack_count / max(n, 1)))

        _leakage_count = sum(
            int(t.extra.get("output_leakage", {}).get("leak_count", 0))
            for t in tasks if t.extra
        )
        if any(t.extra and "output_leakage" in t.extra for t in tasks):
            _native_e_scores.append(max(0.0, 1.0 - min(1.0, _leakage_count / max(n, 1))))

        _injection_count = sum(
            int(t.extra.get("input_injection", {}).get("threat_count", 0))
            for t in tasks if t.extra
        )
        if any(t.extra and "input_injection" in t.extra for t in tasks):
            _native_e_scores.append(max(0.0, 1.0 - min(1.0, _injection_count / max(n, 1))))

        if _cvss_scores:
            avg_cvss = sum(_cvss_scores) / len(_cvss_scores)
            _cvss_normalized = max(0.0, 1.0 - avg_cvss / 10.0)
            _e_base_scores: _List[float] = [_sec_score_raw, _cvss_normalized]
            if _avg_compliance is not None:
                _e_base_scores.append(_avg_compliance)
        elif _avg_compliance is not None:
            _e_base_scores = [_sec_score_raw, _avg_compliance]
        else:
            _e_base_scores = [_sec_score_raw]

        # threat_response → Group E (Phase 6)
        _tr_scores = [
            t.extra.get("threat_response", {}).get("response_score")
            for t in tasks
            if t.extra and t.extra.get("threat_response")
        ]
        _avg_threat_response: Optional[float] = (
            sum(_tr_scores) / len(_tr_scores) if _tr_scores else None
        )

        _all_e_scores = _e_base_scores + _native_e_scores
        if _avg_threat_response is not None:
            _all_e_scores = _all_e_scores + [_avg_threat_response]
        _sec_score = sum(_all_e_scores) / len(_all_e_scores)

        # ── G 그룹: 관측 가능성 (tool coverage + hallucination + observability) ──
        _tool_coverage = 0.0
        try:
            _tc_stats = self.tool_call_analyzer.get_efficiency_stats()
            _tool_coverage = _tc_stats.get("success_rate", 0.0) / 100.0
        except Exception:
            pass

        hall_rate = None
        try:
            _hall_stats = self.hallucination_detector.get_hallucination_stats()
            hall_rate = _hall_stats.get("hallucination_rate")
        except Exception:
            pass

        _obs_custom_scores = [
            t.extra["observability"]["observability_score"]
            for t in tasks
            if (t.extra or {}).get("observability") is not None
        ]
        avg_obs_custom = sum(_obs_custom_scores) / len(_obs_custom_scores) if _obs_custom_scores else None

        _expl_vals = [
            t.extra["explainability"]["score"]
            for t in tasks
            if (t.extra or {}).get("explainability") is not None
        ]
        avg_explainability: Optional[float] = sum(_expl_vals) / len(_expl_vals) if _expl_vals else None

        # error_diagnosis → Group G (Phase 5)
        _ed_scores = [
            t.extra.get("error_diagnosis", {}).get("diagnosis_score")
            for t in tasks
            if (t.extra or {}).get("error_diagnosis") is not None
        ]
        avg_error_diagnosis: Optional[float] = (
            sum(_ed_scores) / len(_ed_scores) if _ed_scores else None
        )

        # latency_attribution → Group G (Phase 6)
        _la_scores = [
            t.extra.get("latency_attribution", {}).get("attribution_score")
            for t in tasks
            if t.extra and t.extra.get("latency_attribution")
        ]
        _avg_latency_attribution: Optional[float] = (
            sum(_la_scores) / len(_la_scores) if _la_scores else None
        )

        _obs_vals: _List[float] = [_tool_coverage]
        if hall_rate is not None:
            _obs_vals.append(max(0.0, 1.0 - float(hall_rate)))
        if avg_obs_custom is not None:
            _obs_vals.append(avg_obs_custom)
        if avg_explainability is not None:
            _obs_vals.append(avg_explainability)
        if avg_error_diagnosis is not None:
            _obs_vals.append(avg_error_diagnosis)
        if _avg_latency_attribution is not None:
            _obs_vals.append(_avg_latency_attribution)
        _obs_score = sum(_obs_vals) / len(_obs_vals)

        # ── F 그룹: 멀티에이전트 조율 ──
        _coord_data: Optional[float] = None
        try:
            _coord_stats = self.coordination_tracker.get_coordination_stats()
            _n_agents = _coord_stats.get("unique_agents", 0)
            _n_interactions = _coord_stats.get("total_interactions", 0)
            if _n_interactions > 0:
                _coord_data = float(min(1.0, _n_agents / max(_n_interactions, 1)))
        except Exception:
            pass

        _consensus_scores = [
            t.extra["consensus"]["consensus_score"]
            for t in tasks
            if (t.extra or {}).get("consensus") is not None
        ]
        avg_consensus: Optional[float] = sum(_consensus_scores) / len(_consensus_scores) if _consensus_scores else None

        _prop_vals = [
            t.extra["propagation"]["fidelity_score"]
            for t in tasks
            if (t.extra or {}).get("propagation") is not None
        ]
        avg_propagation: Optional[float] = sum(_prop_vals) / len(_prop_vals) if _prop_vals else None

        # agent_role → Group F (Phase 4)
        _role_scores = [
            t.extra.get("agent_role", {}).get("role_compliance_score")
            for t in tasks
            if (t.extra or {}).get("agent_role") is not None
        ]
        _avg_role: Optional[float] = sum(_role_scores) / len(_role_scores) if _role_scores else None

        # conflict_resolution → Group F (Phase 4)
        _conflict_scores = [
            t.extra.get("conflict_resolution", {}).get("resolution_score")
            for t in tasks
            if (t.extra or {}).get("conflict_resolution") is not None
        ]
        _avg_conflict_res: Optional[float] = (
            sum(_conflict_scores) / len(_conflict_scores) if _conflict_scores else None
        )

        _f_vals: _List[float] = []
        if _coord_data is not None:
            _f_vals.append(_coord_data)
        if avg_consensus is not None:
            _f_vals.append(avg_consensus)
        if avg_propagation is not None:
            _f_vals.append(avg_propagation)
        if _avg_role is not None:
            _f_vals.append(_avg_role)
        if _avg_conflict_res is not None:
            _f_vals.append(_avg_conflict_res)
        _f_score: Optional[float] = float(sum(_f_vals) / len(_f_vals)) if _f_vals else None

        # ── 그룹별 결과 모음 ──
        _a_s = round(_a_score, 4)
        _b_s = round(float(_bint_score), 4)
        _c_s = round(float(_rel_score), 4)
        _d_s = round(float(_perf_score), 4)
        _e_s = round(float(_sec_score), 4)
        _f_s = round(_f_score, 4) if _f_score is not None else None
        _g_s = round(float(_obs_score), 4)

        # overall: 유효 그룹 점수 평균
        _scored = [s for s in [_a_s, _b_s, _c_s, _d_s, _e_s, _f_s, _g_s] if s is not None]
        _overall_score = round(float(sum(_scored) / len(_scored)), 4) if _scored else 0.0

        def _g(score, name, details, f_score=False):
            """그룹 딕셔너리 생성 헬퍼 — status와 gate 키를 동시에 출력."""
            _st = (_status(score) if not f_score else (_status(score) if score is not None else "n/a"))
            return {"name": name, "score": score, "status": _st, "gate": _st, "details": details}

        groups: Dict[str, Any] = {
            "A": _g(_a_s, "Goal Achievement", {
                "tcr_pct": round(tcr_pct_a, 2),
                "tasks_with_ifr": len(_ifr_scores),
                "avg_instruction_adherence": round(avg_ifr, 4) if avg_ifr is not None else None,
                "avg_goal_alignment": round(avg_goal_a, 4) if avg_goal_a is not None else None,
                "avg_plan_coherence": round(avg_plan_a, 4) if avg_plan_a is not None else None,
                "avg_subtask_completion": round(avg_subtask, 4) if avg_subtask is not None else None,
                "avg_context_retention": round(avg_context_r, 4) if avg_context_r is not None else None,
                "avg_knowledge_retention": round(avg_knowledge_ret, 4) if avg_knowledge_ret is not None else None,
            }),
            "B": _g(_b_s, "Behavioral Integrity", {
                "loop_detection_rate": round(_loop_rate, 4),
                "loop_count": _loop_counts,
                "avg_goal_alignment": round(avg_goal_align, 4) if avg_goal_align is not None else None,
                "avg_plan_coherence": round(avg_plan, 4) if avg_plan is not None else None,
                "avg_state_consistency": round(avg_sc, 4) if avg_sc is not None else None,
                "deadlock_count": _deadlock_count,
                "deadlock_by_type": _deadlock_by_type if _deadlock_by_type else None,
                "avg_deadlock_score": round(max(0.0, 1.0 - _deadlock_count / max(n, 1)), 4),
                "avg_scope_score": round(avg_scope_score, 4) if avg_scope_score is not None else None,
                "avg_tool_parameter_safety": round(avg_tool_param_safety, 4) if avg_tool_param_safety is not None else None,
                "avg_context_window": round(_avg_context_window, 4) if _avg_context_window is not None else None,
            }),
            "C": _g(_c_s, "Reliability", {
                "tcr_pct": round(tcr_pct, 2),
                "sla_breach_rate": round(_sla_breach_rate, 4) if _sla_breach_rate is not None else None,
                "sla_breach_count": _sla_breach_count if _sla_results else None,
                "avg_reproducibility": round(avg_reproducibility, 4) if avg_reproducibility is not None else None,
                "avg_fault_tolerance": round(avg_ft, 4) if avg_ft is not None else None,
                "avg_degradation": round(_avg_degradation, 4) if _avg_degradation is not None else None,
                "avg_retry_consistency": round(_avg_retry_consistency, 4) if _avg_retry_consistency is not None else None,
                "avg_idempotency": round(_avg_idempotency, 4) if _avg_idempotency is not None else None,
            }),
            "D": _g(_d_s, "Performance Contract", {
                "p95_latency_s": round(_p95, 4),
                "avg_efficiency_ratio": round(avg_eff_ratio, 8) if avg_eff_ratio is not None else None,
                "avg_budget_score": round(_avg_budget, 4) if _avg_budget is not None else None,
                "ttft_variability_score": round(_avg_ttft_variability, 4) if _avg_ttft_variability is not None else None,
                "ttft_stddev_ms": round(_ttft_stddev, 4) if _ttft_stddev is not None else None,
                "ttft_p50_ms": round(_ttft_p50, 4) if _ttft_p50 is not None else None,
                "ttft_p95_ms": round(_ttft_p95, 4) if _ttft_p95 is not None else None,
                "avg_cost_predictability": round(_avg_cost_predictability, 4) if _avg_cost_predictability is not None else None,
                "insufficient_data_warnings": _d_insufficient if _d_insufficient else None,
            }),
            "E": _g(_e_s, "Security Boundary", {
                "threat_count": sec_threats,
                "avg_cvss_weighted_score": round(sum(_cvss_scores) / len(_cvss_scores), 4) if _cvss_scores else None,
                "avg_compliance_score": round(_avg_compliance, 4) if _avg_compliance is not None else None,
                "privilege_escalation_rate": round(_priv_esc_count / max(n, 1), 4),
                "chain_attack_rate": round(_chain_attack_count / max(n, 1), 4),
                "leakage_count": _leakage_count,
                "injection_count": _injection_count,
                "avg_threat_response": round(_avg_threat_response, 4) if _avg_threat_response is not None else None,
            }),
            "F": _g(_f_s, "Multi-Agent Coordination", {
                "avg_consensus": round(avg_consensus, 4) if avg_consensus is not None else None,
                "avg_propagation": round(avg_propagation, 4) if avg_propagation is not None else None,
                "avg_role_compliance": round(_avg_role, 4) if _avg_role is not None else None,
                "avg_conflict_resolution": round(_avg_conflict_res, 4) if _avg_conflict_res is not None else None,
            }, f_score=True),
            "G": _g(_g_s, "Observability", {
                "tool_coverage": round(_tool_coverage, 4),
                "hallucination_rate": hall_rate,
                "avg_observability_score": round(avg_obs_custom, 4) if avg_obs_custom is not None else None,
                "avg_explainability": round(avg_explainability, 4) if avg_explainability is not None else None,
                "avg_error_diagnosis": round(avg_error_diagnosis, 4) if avg_error_diagnosis is not None else None,
                "avg_latency_attribution": round(_avg_latency_attribution, 4) if _avg_latency_attribution is not None else None,
            }),
            "overall": {
                "score": _overall_score,
                "status": _status(_overall_score),
                "gate": _status(_overall_score),
                "scored_groups": len(_scored),
            },
        }
        return groups

    def get_live_stats(
        self,
        window_seconds: float = 60.0,
        include_frameworks: bool = True,
    ) -> Dict[str, Any]:
        """최근 N초 이내 태스크의 실시간 집계 통계 반환 (E1).

        대시보드의 실시간 모니터링 뷰에서 가장 최근 활동을 표시할 때 사용.
        ``window_seconds`` 이내에 기록된 태스크만 집계한다.

        Args:
            window_seconds: 집계 시간 창 (기본: 60.0초).
            include_frameworks: 프레임워크별 분류 포함 여부.

        Returns:
            Dict with keys: window_seconds, task_count, tcr, avg_accuracy,
            avg_latency_s, total_tokens, frameworks (optional), timestamp.

        Example::

            stats = monitor.get_live_stats(window_seconds=300)
            print(f"최근 5분: {stats['task_count']}건, TCR={stats['tcr']:.1f}%")
        """
        import time as _time
        from datetime import datetime as _dt

        now = _time.time()
        cutoff = now - window_seconds

        # Q: window_seconds <= 300s 이면 _recent_tasks_cache(deque)에서 O(k) 필터링.
        # 캐시에서 얕은 복사를 먼저 만들고 lock 해제 후 처리 (읽기 전용).
        recent_tasks = []
        if window_seconds <= self._cache_window_seconds:
            with self._tasks_lock:
                _cache_snapshot = list(self._recent_tasks_cache)
            # lock 해제 후 필터링
            for _ts_epoch, t in _cache_snapshot:
                if _ts_epoch >= cutoff:
                    recent_tasks.append(t)
        else:
            # window_seconds > 300s → 기존 O(n) 방식 fallback
            for t in (self.tasks or []):
                try:
                    ts = t.timestamp
                    if isinstance(ts, str):
                        dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                        ts_epoch = dt.timestamp()
                    elif hasattr(ts, "timestamp"):
                        ts_epoch = ts.timestamp()
                    else:
                        ts_epoch = float(ts)
                    if ts_epoch >= cutoff:
                        recent_tasks.append(t)
                except Exception as _e:
                    logger.debug("OTEL attr skipped (timestamp parse): %s", _e)

        if not recent_tasks:
            return {
                "window_seconds": window_seconds,
                "task_count": 0,
                "tcr": 0.0,
                "avg_accuracy": 0.0,
                "avg_latency_s": 0.0,
                "total_tokens": 0,
                "frameworks": {},
                "timestamp": now,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_completion_score": 0.0,
                "task_type_distribution": {},
            }

        n = len(recent_tasks)
        success_count = sum(1 for t in recent_tasks if t.success)
        tcr = round(success_count / n * 100, 2)
        avg_accuracy = round(sum(t.accuracy_score for t in recent_tasks) / n, 4)
        avg_latency = round(sum(t.execution_time for t in recent_tasks) / n, 4)
        total_tokens = sum(
            (t.tokens_used or {}).get("total", 0) if isinstance(t.tokens_used, dict)
            else (int(t.tokens_used) if t.tokens_used else 0)
            for t in recent_tasks
        )

        # O: 추가 필드 계산
        error_count = sum(1 for t in recent_tasks if t.errors)
        error_rate = round(error_count / n, 4) if n else 0.0
        avg_completion_score = round(sum(t.completion_score for t in recent_tasks) / n, 4)
        from collections import defaultdict as _dd2
        _type_dist: Dict[str, int] = _dd2(int)
        for t in recent_tasks:
            tt = t.task_type
            if hasattr(tt, "value"):
                tt = tt.value
            _type_dist[str(tt).lower()] += 1

        result: Dict[str, Any] = {
            "window_seconds": window_seconds,
            "task_count": n,
            "tcr": tcr,
            "avg_accuracy": avg_accuracy,
            "avg_latency_s": avg_latency,
            "total_tokens": total_tokens,
            "timestamp": now,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_completion_score": avg_completion_score,
            "task_type_distribution": dict(_type_dist),
        }

        if include_frameworks:
            from collections import defaultdict as _dd
            fw_counts: Dict[str, int] = _dd(int)
            for t in recent_tasks:
                fw = getattr(t, "framework", None) or "native"
                fw_counts[fw] += 1
            result["frameworks"] = dict(fw_counts)

        return result

    def get_report_by_type(self, task_type: str) -> Dict[str, Any]:
        """태스크 유형별 지표를 분해해서 반환한다 (편의 메서드).

        ``generate_report()`` 의 전체 집계 대신 특정 ``task_type`` 의 태스크만
        필터링해 주요 지표를 반환한다.

        Args:
            task_type: 필터링할 태스크 유형 (예: ``"qa"``, ``"tool_use"``, ``"information_retrieval"``).

        Returns:
            Dict with keys: task_type, count, tcr, avg_accuracy, avg_completion,
            avg_latency, error_count, error_rate.

        Example::

            report = monitor.get_report_by_type("qa")
            print(report["avg_accuracy"])  # QA 태스크 평균 정확도만
        """
        _type_str = str(task_type).lower().replace("tasktype.", "")
        _tasks = [
            t for t in (self.tasks or [])
            if str(getattr(t, "task_type", "")).lower().replace("tasktype.", "") == _type_str
        ]
        if not _tasks:
            return {
                "task_type": _type_str,
                "count": 0,
                "tcr": 0.0,
                "avg_accuracy": 0.0,
                "avg_completion": 0.0,
                "avg_latency": 0.0,
                "error_count": 0,
                "error_rate": 0.0,
            }
        _count = len(_tasks)
        _successes = sum(1 for t in _tasks if t.success)
        _accuracies = [t.accuracy_score for t in _tasks if t.accuracy_score is not None]
        _completions = [t.completion_score for t in _tasks if t.completion_score is not None]
        _latencies = [t.execution_time for t in _tasks if t.execution_time is not None]
        _errors = sum(1 for t in _tasks if t.errors)
        return {
            "task_type": _type_str,
            "count": _count,
            "tcr": round((_successes / _count) * 100, 2) if _count else 0.0,
            "avg_accuracy": round(sum(_accuracies) / len(_accuracies), 4) if _accuracies else 0.0,
            "avg_completion": round(sum(_completions) / len(_completions), 4) if _completions else 0.0,
            "avg_latency": round(sum(_latencies) / len(_latencies), 4) if _latencies else 0.0,
            "error_count": _errors,
            "error_rate": round((_errors / _count) * 100, 2) if _count else 0.0,
            "task_types_found": list({str(t.task_type) for t in _tasks}),
        }

    def get_report_by_framework(self, framework: str) -> Dict[str, Any]:
        """지정한 프레임워크의 태스크만 필터링해서 지표를 반환합니다.

        Args:
            framework: 필터할 프레임워크 이름 (예: "langchain", "crewai", "native")

        Returns:
            task_count, tcr, avg_accuracy, avg_completion, avg_latency_s,
            total_tokens, framework, matched_task_ids 를 포함하는 dict
        """
        matched = []
        for t in self.tasks:
            fw = None
            if hasattr(t, "extra") and isinstance(t.extra, dict):
                fw = t.extra.get("framework")
            if fw is None:
                fw = "native"
            if fw == framework:
                matched.append(t)

        if not matched:
            return {"framework": framework, "task_count": 0}

        tcr = sum(1 for t in matched if t.success) / len(matched)
        avg_acc = sum(t.accuracy_score for t in matched) / len(matched)
        avg_comp = sum(t.completion_score for t in matched) / len(matched)
        avg_lat = sum(t.execution_time for t in matched) / len(matched)
        total_tok = sum(
            (t.tokens_used if isinstance(t.tokens_used, int) else
             t.tokens_used.get("total", 0) if isinstance(t.tokens_used, dict) else 0)
            for t in matched
        )

        return {
            "framework": framework,
            "task_count": len(matched),
            "tcr": round(tcr, 4),
            "avg_accuracy": round(avg_acc, 4),
            "avg_completion": round(avg_comp, 4),
            "avg_latency_s": round(avg_lat, 4),
            "total_tokens": total_tok,
            "matched_task_ids": [t.task_id for t in matched],
        }

    def _generate_alerts(self) -> List[Dict[str, str]]:
        """Generate alerts for metric violations"""
        alerts = []

        # 임계값 설정 (로드된 임계값 또는 기본값)
        thresholds = self.thresholds if self._thresholds else {
            'tcr': 80.0,
            'accuracy': 70.0,
            'hallucination': 10.0,
            'quality': 6.0,
            'latency': 10.0,
            'cost_per_task': 0.05,
        }

        # Check TCR — skip when no tasks have been recorded yet
        tcr_data = self.tcr_tracker.calculate_tcr()
        if tcr_data.get("total_tasks", 0) > 0:
            tcr_threshold = thresholds.get('tcr', 80.0)
            if tcr_data.get("tcr", 0) < tcr_threshold:
                alerts.append({
                    "severity": "high",
                    "metric": "작업 완료율 (TCR)",
                    "message": f"TCR이 {tcr_data.get('tcr', 0):.1f}%입니다 ({tcr_threshold:.1f}% 기준 미달)",
                    "action": "프롬프트와 도구 설정을 검토하세요"
                })
            elif tcr_data.get("tcr", 0) < 90:
                alerts.append({
                    "severity": "medium",
                    "metric": "작업 완료율 (TCR)",
                    "message": f"TCR이 {tcr_data.get('tcr', 0):.1f}%입니다 (90% 기준 미달)",
                    "action": "작업 완료율 개선을 고려하세요"
                })

        # Check accuracy — guard against 0-evaluation state (dict is always truthy)
        accuracy_data = self.accuracy_evaluator.get_accuracy_metrics()
        if accuracy_data.get("total_evaluated", 0) > 0:
            overall_acc = accuracy_data.get("overall_accuracy", 100)
            accuracy_threshold = thresholds.get('accuracy', 70.0)
            if overall_acc < accuracy_threshold:
                alerts.append({
                    "severity": "critical",
                    "metric": "정확도 (Accuracy)",
                    "message": f"정확도가 {overall_acc:.1f}%입니다 ({accuracy_threshold:.1f}% 기준 미달)",
                    "action": "즉시 검증 로직을 강화하고 프롬프트를 개선하세요"
                })
            elif overall_acc < 80:
                alerts.append({
                    "severity": "high",
                    "metric": "정확도 (Accuracy)",
                    "message": f"정확도가 {overall_acc:.1f}%입니다 (80% 기준 미달)",
                    "action": "프롬프트 개선과 예시 추가를 고려하세요"
                })

        # Check hallucination rate
        hall_data = self.hallucination_detector.get_hallucination_rate()
        hallucination_threshold = thresholds.get('hallucination', 10.0)
        if hall_data.get("overall_rate", 0) > hallucination_threshold:
            alerts.append({
                "severity": "critical",
                "metric": "환각 발생률 (Hallucination)",
                "message": f"환각 발생률이 {hall_data.get('overall_rate', 0):.1f}%입니다 ({hallucination_threshold:.1f}% 기준 초과)",
                "action": "검증 프로세스와 사실 확인 절차를 즉시 강화하세요"
            })
        elif hall_data.get("overall_rate", 0) > 5:
            alerts.append({
                "severity": "high",
                "metric": "환각 발생률 (Hallucination)",
                "message": f"환각 발생률이 {hall_data.get('overall_rate', 0):.1f}%입니다 (5% 기준 초과)",
                "action": "검증 및 사실 확인 프로세스를 강화하세요"
            })

        # Check quality — guard against 0-evaluation state (same as compare_with_thresholds)
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data.get("total_evaluated", 0) > 0 and "avg_total_score" in quality_data:
            avg_quality = quality_data["avg_total_score"] * 2  # Convert to 10-point scale
            quality_threshold = thresholds.get('quality', 6.0)
            if avg_quality < quality_threshold:
                alerts.append({
                    "severity": "high",
                    "metric": "응답 품질 (Quality)",
                    "message": f"평균 품질이 {avg_quality:.1f}/10입니다 ({quality_threshold:.1f} 기준 미달)",
                    "action": "응답 완성도, 관련성, 명확성을 개선하세요"
                })
            elif avg_quality < 7.0:
                alerts.append({
                    "severity": "medium",
                    "metric": "응답 품질 (Quality)",
                    "message": f"평균 품질이 {avg_quality:.1f}/10입니다 (7.0 기준 미달)",
                    "action": "응답 품질 개선을 고려하세요"
                })

        # Check latency
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data:
            p95_latency = latency_data.get("p95", 0)
            latency_threshold = thresholds.get('latency', 10.0)
            if p95_latency > latency_threshold:
                alerts.append({
                    "severity": "high",
                    "metric": "응답 시간 (Latency)",
                    "message": f"P95 응답 시간이 {p95_latency:.2f}초입니다 ({latency_threshold:.2f}초 기준 초과)",
                    "action": "성능 최적화와 병렬 처리를 고려하세요"
                })
            elif p95_latency > 5:
                alerts.append({
                    "severity": "medium",
                    "metric": "응답 시간 (Latency)",
                    "message": f"P95 응답 시간이 {p95_latency:.2f}초입니다 (5초 기준 초과)",
                    "action": "응답 시간 최적화를 고려하세요"
                })

        # Check cost
        token_data = self.token_tracker.get_usage_stats()
        cost_per_task = token_data.get("avg_cost_per_task", 0)
        cost_threshold = thresholds.get('cost_per_task', 0.05)
        if cost_per_task > cost_threshold:
            alerts.append({
                "severity": "high",
                "metric": "토큰 비용 (Cost per Task)",
                "message": f"작업당 평균 비용: ${cost_per_task:.4f} (${cost_threshold:.4f} 기준 초과)",
                "action": "토큰 사용 패턴을 검토하고 최적화 기회를 찾으세요"
            })
        elif cost_per_task > 0.03:
            alerts.append({
                "severity": "medium",
                "metric": "토큰 비용 (Cost per Task)",
                "message": f"작업당 평균 비용: ${cost_per_task:.4f} ($0.03 기준 초과)",
                "action": "비용 최적화를 고려하세요"
            })

        # Check tool efficiency
        tool_data = self.tool_analyzer.get_efficiency_stats()
        if tool_data and tool_data.get("total_calls", 0) > 0:
            efficiency = tool_data.get("avg_efficiency_score", 100)
            if efficiency < 60:
                alerts.append({
                    "severity": "high",
                    "metric": "도구 효율성 (Tool Efficiency)",
                    "message": f"도구 효율성이 {efficiency:.1f}%입니다 (60% 기준 미달)",
                    "action": "도구 호출 패턴을 분석하고 중복을 제거하세요"
                })
            elif efficiency < 70:
                alerts.append({
                    "severity": "medium",
                    "metric": "도구 효율성 (Tool Efficiency)",
                    "message": f"도구 효율성이 {efficiency:.1f}%입니다 (70% 기준 미달)",
                    "action": "도구 사용 최적화를 고려하세요"
                })

        # === Security Alerts (Layer 1 & 2) ===
        if self.enable_security_metrics:
            # Input sanitization threats
            if self.input_sanitizer:
                security_data = self.input_sanitizer.get_security_stats()
                if security_data:
                    threat_rate = security_data.get("threat_rate", 0)
                    if threat_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "입력 보안 위협 (Input Security)",
                            "message": f"입력의 {threat_rate:.1f}%에서 보안 위협 탐지 (SQL injection, prompt injection 등)",
                            "action": "즉시 입력 검증 및 살균 프로세스를 강화하세요"
                        })
                    elif threat_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "입력 보안 위협 (Input Security)",
                            "message": f"입력의 {threat_rate:.1f}%에서 보안 위협 탐지",
                            "action": "입력 검증 로직을 검토하고 강화하세요"
                        })

            # Output leakage
            if self.output_leakage_detector:
                leakage_data = self.output_leakage_detector.get_leakage_stats()
                if leakage_data:
                    leakage_rate = leakage_data.get("leakage_rate", 0)
                    critical_leaks = leakage_data.get("critical_severity_count", 0)
                    if critical_leaks > 0:
                        alerts.append({
                            "severity": "critical",
                            "metric": "민감 정보 유출 (Data Leakage)",
                            "message": f"{critical_leaks}개의 출력에서 API 키, 비밀번호 등 중요 정보 유출 탐지",
                            "action": "즉시 출력 필터링을 강화하고 유출된 정보를 회전시키세요"
                        })
                    elif leakage_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "민감 정보 유출 (Data Leakage)",
                            "message": f"출력의 {leakage_rate:.1f}%에서 민감 정보 유출 탐지",
                            "action": "출력 검증 및 마스킹 프로세스를 강화하세요"
                        })

            # Tool authorization violations
            if self.tool_authorizer:
                auth_data = self.tool_authorizer.get_compliance_stats()
                if auth_data:
                    violation_rate = auth_data.get("violation_rate", 0)
                    if violation_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "도구 권한 위반 (Authorization)",
                            "message": f"도구 호출의 {violation_rate:.1f}%가 권한 정책 위반",
                            "action": "즉시 권한 정책을 검토하고 무단 도구 사용을 차단하세요"
                        })
                    elif violation_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "도구 권한 위반 (Authorization)",
                            "message": f"도구 호출의 {violation_rate:.1f}%가 권한 정책 위반",
                            "action": "권한 정책 및 허용 도구 목록을 검토하세요"
                        })

            # Privilege escalation
            if self.privilege_escalation_detector:
                escalation_data = self.privilege_escalation_detector.get_escalation_stats()
                if escalation_data:
                    escalation_rate = escalation_data.get("escalation_rate", 0)
                    high_risk = escalation_data.get("high_risk_events", 0)
                    if high_risk > 0:
                        alerts.append({
                            "severity": "critical",
                            "metric": "권한 상승 탐지 (Privilege Escalation)",
                            "message": f"{high_risk}개의 고위험 권한 상승 패턴 탐지",
                            "action": "즉시 도구 체인을 검토하고 권한 상승 경로를 차단하세요"
                        })
                    elif escalation_rate > 20:
                        alerts.append({
                            "severity": "high",
                            "metric": "권한 상승 탐지 (Privilege Escalation)",
                            "message": f"작업의 {escalation_rate:.1f}%에서 권한 상승 패턴 탐지",
                            "action": "권한 상승 패턴을 분석하고 제한하세요"
                        })

            # Tool chain attacks
            if self.tool_chain_attack_detector:
                attack_data = self.tool_chain_attack_detector.get_attack_stats()
                if attack_data:
                    detection_rate = attack_data.get("detection_rate", 0)
                    if detection_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "공격 패턴 탐지 (Attack Detection)",
                            "message": f"도구 체인의 {detection_rate:.1f}%에서 공격 패턴 탐지 (데이터 유출, 측면 이동 등)",
                            "action": "즉시 의심스러운 도구 체인을 검토하고 차단하세요"
                        })
                    elif detection_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "공격 패턴 탐지 (Attack Detection)",
                            "message": f"도구 체인의 {detection_rate:.1f}%에서 공격 패턴 탐지",
                            "action": "도구 체인 패턴을 분석하고 모니터링을 강화하세요"
                        })

        return alerts
    
    def _generate_recommendations(self) -> List[Dict[str, str]]:
        """Generate improvement recommendations"""
        recommendations = []

        # TCR improvement
        tcr_data = self.tcr_tracker.calculate_tcr()
        if tcr_data.get("tcr", 100) < 90:
            tcr_value = tcr_data.get('tcr', 0)
            gap = 90 - tcr_value
            full_success = tcr_data.get('full_success', 0)
            partial_success = tcr_data.get('partial_success', 0)
            failures = tcr_data.get('failures', 0)

            recommendations.append({
                "area": "작업 완료율 개선",
                "title": f"작업 완료율(TCR)이 목표치 대비 {gap:.1f}%p 낮음",
                "priority": "high" if tcr_value < 80 else "medium",
                "issue": f"현재 TCR {tcr_value:.1f}% (목표: 90% 이상). 전체 성공 {full_success}건, 부분 성공 {partial_success}건, 실패 {failures}건으로 실패 작업의 원인 분석이 필요합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **실패 작업 패턴 분석**: 실패한 {failures}개 작업의 공통 오류 패턴 파악 (타임아웃, API 오류, 입력 검증 실패 등)
2. **프롬프트 명확화**: 작업 지시사항에 구체적인 성공 기준과 출력 형식 명시
3. **작업 분할 전략**: 복잡한 작업을 3-5개의 하위 작업으로 분할하여 단계별 검증 수행
4. **재시도 메커니즘**: 일시적 오류(네트워크, API 제한)에 대한 지수 백오프 재시도 구현
5. **입력 검증 강화**: 작업 실행 전 필수 파라미터와 컨텍스트 검증 로직 추가""",
                "impact": f"""**예상 개선 효과:**
• TCR 목표 달성 시 연간 {failures * 52}건 실패 작업 감소 (주간 {failures}건 기준)
• 사용자 만족도 15-25% 향상 (90% TCR 달성 시)
• 재작업 비용 절감: 실패 작업당 평균 5분 소요 시 주당 {failures * 5}분 절약
• 시스템 신뢰도 향상으로 프로덕션 배포 리스크 감소"""
            })

        # Accuracy improvement — guard against 0-evaluation state (same as _generate_alerts)
        accuracy_data = self.accuracy_evaluator.get_accuracy_metrics()
        if accuracy_data.get("total_evaluated", 0) > 0:
            overall_acc = accuracy_data.get("overall_accuracy", 100)
            if overall_acc < 85:
                gap = 85 - overall_acc
                recommendations.append({
                    "area": "정확도 개선",
                    "title": f"정답 정확도가 기준치 대비 {gap:.1f}%p 부족",
                    "priority": "high" if overall_acc < 75 else "medium",
                    "issue": f"현재 정확도 {overall_acc:.1f}% (목표: 85% 이상). 응답의 사실 정확성이 부족하여 사용자에게 잘못된 정보를 제공할 위험이 있습니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **검증 단계 추가**:
   - RAG 기반 작업: 검색된 컨텍스트와 응답의 일치성을 자동 검증하는 후처리 단계 추가
   - 계산/추론 작업: 중간 단계 결과를 명시적으로 출력하고 검증
2. **Few-shot 예시 제공**: 작업 유형별로 3-5개의 고품질 예시를 프롬프트에 포함
3. **프롬프트 구조화**:
   - 단계별 사고 과정(Chain-of-Thought) 유도
   - 최종 답변 전 자기 검증(Self-verification) 단계 추가
4. **Golden Dataset 활용**: 현재 평가 데이터셋을 기반으로 오답 패턴 분석 및 학습 데이터 보강
5. **모델 파라미터 조정**: Temperature 낮추기(0.3-0.5), Top-P 조정으로 일관성 향상""",
                    "impact": f"""**예상 개선 효과:**
• 정확도 85% 달성 시 오답률 {100-overall_acc:.1f}% → 15%로 {(100-overall_acc)-15:.1f}%p 감소
• 사용자 신뢰도 20-30% 향상
• 잘못된 정보로 인한 비즈니스 리스크 {((100-overall_acc)/100)*100:.0f}% 감소
• 사실 확인 및 수정 작업 시간 주당 10-15시간 절감"""
                })

        # Quality improvement — guard against 0-evaluation state (same as _generate_alerts)
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data.get("total_evaluated", 0) > 0 and "avg_total_score" in quality_data:
            # 품질 점수는 0~5 범위 (v0.5.x 이후). 목표: 4.0/5
            avg_quality = quality_data["avg_total_score"]  # 0~5 그대로 사용
            quality_target = 4.0
            if avg_quality < quality_target:
                gap = quality_target - avg_quality
                recommendations.append({
                    "area": "응답 품질 개선",
                    "title": f"응답 품질 점수가 목표치 대비 {gap:.1f}점 낮음 (5점 만점)",
                    "priority": "medium",
                    "issue": f"현재 품질 점수 {avg_quality:.1f}/5.0 (목표: {quality_target:.1f} 이상). 응답의 완성도, 관련성, 가독성이 사용자 기대 수준에 미치지 못하고 있습니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **응답 구조화 템플릿 적용**:
   - 질문형 작업: 직접적 답변 → 근거 제시 → 추가 정보 순으로 구조화
   - 분석형 작업: 요약 → 상세 분석 → 결론 및 권장사항 순으로 구성
2. **완성도 체크리스트 도입**:
   - 질문의 모든 부분에 답변했는가?
   - 근거나 예시가 충분히 제공되었는가?
   - 결론이 명확하게 제시되었는가?
3. **관련성 강화**:
   - 제공된 컨텍스트나 질문에서 벗어난 내용 제거
   - 핵심 키워드를 응답에 자연스럽게 포함
4. **가독성 개선**:
   - 긴 문장(50자 이상) 분할
   - 불릿 포인트나 번호 매기기 활용
   - 전문 용어 사용 시 간단한 설명 추가
5. **사용자 맞춤화**: 응답 톤과 디테일 수준을 사용자 컨텍스트에 맞게 조정""",
                    "impact": f"""**예상 개선 효과:**
• 품질 점수 {quality_target:.1f}/5.0 달성 시 사용자 재질문률 30-40% 감소
• 응답 이해도 향상으로 고객 지원 문의 주당 20-30건 감소
• 사용자 세션 시간 15-20% 증가 (만족도 향상)
• 응답 재작성 필요성 {(gap/quality_target)*100:.0f}% 감소로 운영 효율 증대"""
                })

        # Token optimization
        token_data = self.token_tracker.get_usage_stats()
        if token_data.get("token_distribution", {}).get("input_ratio", 0) > 0.7:
            input_ratio = token_data.get("token_distribution", {}).get("input_ratio", 0) * 100
            total_tokens = token_data.get("total_tokens", 0)
            total_cost = token_data.get("total_cost", 0)

            recommendations.append({
                "area": "토큰 효율성",
                "title": f"입력 토큰 비율이 {input_ratio:.0f}%로 과도하게 높음",
                "priority": "medium",
                "issue": f"전체 토큰 사용량의 {input_ratio:.0f}%가 입력 토큰 (총 {total_tokens:,} 토큰, 비용 ${total_cost:.2f}). 불필요하게 긴 컨텍스트나 반복적인 프롬프트가 비용 증가의 주요 원인입니다.",
                "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **컨텍스트 요약 기법**:
   - 긴 문서는 임베딩 기반 검색 후 상위 3-5개 청크만 사용
   - 대화 히스토리는 최근 5턴으로 제한하고 이전 내용은 요약본 사용
2. **슬라이딩 윈도우 구현**:
   - 장문 처리 시 4096 토큰 윈도우로 분할 처리
   - 중복 컨텍스트 제거 (이전 윈도우에서 이미 처리된 정보)
3. **프롬프트 최적화**:
   - 시스템 프롬프트에서 불필요한 예시나 설명 제거
   - 동적 프롬프트: 작업 복잡도에 따라 프롬프트 길이 조절
4. **캐싱 활용**:
   - 반복되는 시스템 프롬프트나 자주 사용하는 컨텍스트는 API 캐싱 기능 활용 (Claude/OpenAI)
5. **토큰 모니터링**: 작업별 입력 토큰 추적 및 500토큰 이상 작업 우선 최적화""",
                "impact": f"""**예상 개선 효과:**
• 입력 토큰 30% 감소 시 월간 비용 ${total_cost * 0.3 * 30:.2f} 절감 (현재 일간 ${total_cost:.2f} 기준)
• 연간 ${total_cost * 0.3 * 365:.2f} 비용 절감 가능
• 응답 속도 10-15% 향상 (입력 처리 시간 감소)
• 토큰 한도 도달 빈도 감소로 서비스 안정성 향상"""
            })

        # Latency optimization
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data:
            mean_latency = latency_data.get("mean", 0)
            if mean_latency > 3:
                p95 = latency_data.get("p95", 0)
                recommendations.append({
                    "area": "응답 시간 최적화",
                    "title": f"평균 응답 시간이 {mean_latency:.1f}초로 사용자 기대치 초과",
                    "priority": "high" if mean_latency > 5 else "medium",
                    "issue": f"평균 {mean_latency:.2f}초, P95 {p95:.2f}초 (목표: 3초 이내). 긴 대기 시간은 사용자 이탈률 증가와 직결됩니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **병렬 처리 구현**:
   - 독립적인 도구 호출은 asyncio로 병렬 실행 (2-3배 속도 향상)
   - RAG 검색과 LLM 추론을 파이프라인으로 중첩 처리
2. **캐싱 전략 적용**:
   - 빈번한 질문(FAQ)에 대한 응답 캐싱 (Redis/Memcached)
   - 검색 결과 캐싱: 동일 쿼리 24시간 캐시
   - 임베딩 캐싱: 동일 텍스트 재계산 방지
3. **모델 최적화**:
   - 간단한 작업(분류, 간단한 QA)은 경량 모델 사용 (GPT-3.5, Claude Haiku)
   - 복잡한 작업만 고성능 모델 사용
   - Streaming 응답 활성화로 체감 속도 개선
4. **인프라 최적화**:
   - API 엔드포인트를 지리적으로 가까운 리전 사용
   - 연결 풀링 및 Keep-Alive 설정
5. **타임아웃 설정**: 5초 초과 작업은 중단 후 간소화된 응답 제공""",
                    "impact": f"""**예상 개선 효과:**
• 평균 응답 시간 3초 달성 시 사용자 이탈률 25-35% 감소
• P95를 5초 이하로 개선하면 상위 5% 불만족 사용자 경험 대폭 개선
• 처리량 {(mean_latency/3.0):.1f}배 증가 (동일 리소스로 더 많은 요청 처리)
• 사용자 만족도 조사 점수 0.5-1.0점 향상 (5점 만점)"""
                })

        # Tool efficiency
        tool_data = self.tool_analyzer.get_efficiency_stats()
        if tool_data and tool_data.get("total_calls", 0) > 0:
            redundancy_rate = tool_data.get("redundancy_rate", 0)
            if redundancy_rate > 10:
                total_calls = tool_data.get("total_calls", 0)
                redundant_calls = int(total_calls * redundancy_rate / 100)

                recommendations.append({
                    "area": "도구 호출 최적화",
                    "title": f"중복 도구 호출로 인한 비효율 발생 ({redundancy_rate:.0f}%)",
                    "priority": "medium",
                    "issue": f"총 {total_calls}회 도구 호출 중 약 {redundant_calls}회가 중복 호출 (중복률 {redundancy_rate:.1f}%). 동일한 파라미터로 같은 도구를 반복 호출하여 불필요한 지연과 비용이 발생합니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **결과 캐싱 메커니즘**:
   - 도구 호출 결과를 메모리 캐시에 저장 (작업 세션 동안 유지)
   - 캐시 키: (도구명, 파라미터 해시) 조합
   - 최대 100개 결과 저장, LRU 정책으로 관리
2. **중복 검사 로직**:
   - 도구 호출 전 최근 5회 호출 이력 확인
   - 동일 파라미터 발견 시 캐시된 결과 재사용
3. **에이전트 로직 개선**:
   - 도구 호출 이력을 프롬프트에 포함하여 LLM이 중복 인지하도록 유도
   - "이전에 이미 검색한 내용입니다" 같은 피드백 제공
4. **배치 처리**:
   - 여러 개의 유사한 도구 호출을 하나로 통합 (예: 10개 문서 검색 → 1회 배치 검색)
5. **도구 호출 분석**: 상위 5개 중복 도구 파악 후 우선 최적화""",
                    "impact": f"""**예상 개선 효과:**
• 중복 호출 {redundancy_rate:.0f}% 제거 시 도구 호출 시간 {redundancy_rate:.0f}% 단축
• API 비용 절감: 외부 API 도구의 경우 월간 수백 달러 절감 가능
• 평균 작업 완료 시간 15-20% 개선
• 시스템 부하 감소로 동시 처리 가능 작업 수 {(100/(100-redundancy_rate)):.1f}배 증가"""
                })

        # Retry optimization
        retry_data = self.retry_tracker.get_retry_metrics()
        if retry_data.get("overall_retry_rate", 0) > 20:
            retry_rate = retry_data.get('overall_retry_rate', 0)
            recommendations.append({
                "area": "에러 처리 개선",
                "title": f"재시도율이 {retry_rate:.0f}%로 과도하게 높음",
                "priority": "high" if retry_rate > 30 else "medium",
                "issue": f"전체 작업의 {retry_rate:.1f}%가 재시도 필요. 높은 재시도율은 근본 원인 해결 없이 임시방편으로 대응하고 있음을 의미하며, 사용자 경험과 시스템 효율을 저하시킵니다.",
                "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **실패 패턴 분석 대시보드 구축**:
   - 재시도 원인별 통계 (API 타임아웃, 파싱 오류, 검증 실패 등)
   - 시간대별, 작업 유형별 실패율 추적
   - 주간 리포트 자동 생성
2. **첫 시도 성공률 개선**:
   - **API 타임아웃**: 타임아웃 설정 10초 → 15초로 증가, 중요 작업 우선순위 부여
   - **파싱 오류**: 응답 형식을 JSON Schema로 명시, Pydantic 검증 추가
   - **검증 실패**: 입력 전처리 단계에서 필수 필드 검증 강화
3. **지능형 재시도 전략**:
   - 일시적 오류(네트워크): 지수 백오프 (1초 → 2초 → 4초)
   - 영구적 오류(잘못된 입력): 재시도 없이 즉시 실패 처리
   - 최대 재시도 횟수 3회로 제한 (무한 루프 방지)
4. **대체 전략 구현**:
   - Primary API 실패 시 Fallback API로 자동 전환
   - 복잡한 작업 실패 시 단순화된 버전으로 재시도
5. **알림 시스템**: 재시도율 30% 초과 시 개발팀에 자동 알림""",
                "impact": f"""**예상 개선 효과:**
• 재시도율 10% 이하로 감소 시 평균 작업 시간 {retry_rate/2:.0f}% 단축
• 사용자 체감 속도 30-40% 향상
• 시스템 리소스 효율 {retry_rate:.0f}% 개선 (중복 처리 감소)
• 안정성 향상으로 프로덕션 신뢰도 증가
• 장애 대응 시간 50% 단축 (명확한 실패 패턴 파악)"""
                })

        return recommendations
    
    def print_report(self, report: EvaluationReport = None) -> None:
        """Print formatted report"""
        if report is None:
            report = self.generate_report()
        
        print("\n" + "="*80)
        print("AI AGENT PERFORMANCE EVALUATION REPORT")
        print(f"Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Tasks Evaluated: {report.total_tasks}")
        print("="*80 + "\n")
        
        # Accuracy & Quality Metrics
        print("📊 ACCURACY & QUALITY METRICS")
        print("-" * 80)
        
        tcr = report.accuracy_metrics.get("tcr", {})
        print(f"Task Completion Rate: {tcr.get('tcr', 0):.1f}%")
        print(f"  - Full Success: {tcr.get('full_success', 0)} tasks")
        print(f"  - Partial Success: {tcr.get('partial_success', 0)} tasks")
        print(f"  - Failures: {tcr.get('failures', 0)} tasks")
        print(f"  - Status: {self.tcr_tracker.get_benchmark_status(tcr.get('tcr', 0))}")
        
        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print("\nAccuracy Scores:")
            print(f"  - Overall: {accuracy.get('overall_accuracy', 0):.1f}%")
            print(f"  - Median: {accuracy.get('median_accuracy', 0):.1f}%")
        
        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"\nHallucination Rate: {hall.get('overall_rate', 0):.1f}%")
        
        quality = report.accuracy_metrics.get("quality", {})
        if quality:
            print(f"\nQuality Score: {quality.get('avg_total_score', 0):.1f}/5.0")
        
        # Efficiency Metrics
        print("\n⚡ EFFICIENCY METRICS")
        print("-" * 80)
        
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print("Response Time:")
            print(f"  - Mean: {latency.get('mean', 0):.3f}s")
            print(f"  - Median: {latency.get('median', 0):.3f}s")
            print(f"  - P95: {latency.get('p95', 0):.3f}s")
            print(f"  - P99: {latency.get('p99', 0):.3f}s")
        
        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            print("\nToken Usage:")
            print(f"  - Total Tokens: {tokens.get('total_tokens', 0):,}")
            print(f"  - Avg per Task: {tokens.get('avg_tokens_per_task', 0):.0f}")
            print(f"  - Total Cost: ${tokens.get('total_cost', 0):.4f}")
            print(f"  - Estimated Monthly: ${tokens.get('estimated_monthly_cost', 0):.2f}")
        
        tool_eff = report.efficiency_metrics.get("tool_efficiency", {})
        if tool_eff:
            print("\nTool Call Efficiency:")
            print(f"  - Avg Calls per Task: {tool_eff.get('avg_calls_per_task', 0):.1f}")
            print(f"  - Efficiency Score: {tool_eff.get('avg_efficiency_score', 0):.1f}%")
            print(f"  - Redundancy Rate: {tool_eff.get('redundancy_rate', 0):.1f}%")
        
        retries = report.efficiency_metrics.get("retries", {})
        if retries:
            print("\nRetry Statistics:")
            print(f"  - Retry Rate: {retries.get('overall_retry_rate', 0):.1f}%")
            print(f"  - First Attempt Success: {retries.get('first_attempt_success_rate', 0):.1f}%")
        
        # Alerts
        if report.alerts:
            print("\n🚨 ALERTS")
            print("-" * 80)
            for alert in report.alerts:
                severity_icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "high" else "🟢"
                print(f"{severity_icon} [{alert['severity'].upper()}] {alert['metric']}")
                print(f"   {alert['message']}")
                print(f"   → {alert['action']}\n")
        
        # Recommendations
        if report.recommendations:
            print("💡 RECOMMENDATIONS")
            print("-" * 80)
            for i, rec in enumerate(report.recommendations, 1):
                print(f"{i}. {rec['area']}")
                print(f"   Issue: {rec['issue']}")
                print(f"   Suggestion: {rec['suggestion']}")
                print(f"   Impact: {rec['impact']}\n")

        print("="*80 + "\n")

    def print_summary(self, report: EvaluationReport = None) -> None:
        """
        Print quick summary report (documented in user guides)

        Provides a concise overview of key metrics for rapid assessment.
        Ideal for quick checks during development or CI/CD pipelines.

        Args:
            report: Pre-generated report (optional). If None, generates new report.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_summary()  # Quick overview
        """
        if report is None:
            report = self.generate_report()

        print("=" * 80)
        print("         성능 요약 보고서")
        print("=" * 80)
        print()

        # Overall statistics
        print("📊 전체 작업 통계:")
        print(f"  - 총 작업 수: {report.total_tasks}")

        # Calculate success/failure from TCR
        tcr_data = report.accuracy_metrics.get("tcr", {})
        success_count = tcr_data.get("full_success", 0) + tcr_data.get("partial_success", 0)
        failure_count = tcr_data.get("failures", 0)
        success_rate = (success_count / report.total_tasks * 100) if report.total_tasks > 0 else 0

        print(f"  - 성공: {success_count} ({success_rate:.1f}%)")
        print(f"  - 실패: {failure_count} ({100 - success_rate:.1f}%)")
        print()

        # Accuracy metrics
        print("✅ 정확도 메트릭:")
        print(f"  - TCR (Task Completion Rate): {tcr_data.get('tcr', 0):.1f}%")

        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print(f"  - 평균 Accuracy: {accuracy.get('overall_accuracy', 0):.1f}%")

        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"  - Hallucination Rate: {hall.get('overall_rate', 0):.1f}%")
        print()

        # Efficiency metrics
        print("⚡ 효율성 메트릭:")
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print(f"  - 평균 Latency: {latency.get('mean', 0):.2f}초")
            print(f"  - P95 Latency: {latency.get('p95', 0):.2f}초")

        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            avg_tokens = tokens.get('avg_tokens_per_task', 0)
            print(f"  - 평균 Token 사용량: {avg_tokens:.0f} tokens")
            print(f"  - 총 비용: ${tokens.get('total_cost', 0):.4f}")

        print()
        print("=" * 80)
        print()

    def print_detailed_report(self, report: EvaluationReport = None) -> None:
        """
        Print comprehensive detailed report (documented in user guides)

        Provides in-depth analysis across all three metric layers:
        - Layer 1: Native Metrics (TCR, Accuracy, Latency, Cost)
        - Layer 2: Agentic AI Metrics (Tool Usage, Agent Coordination, Workflow)
        - Layer 3: Advanced Metrics (DeepEval, Ragas, etc.)

        Args:
            report: Pre-generated report (optional). If None, generates new report.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_detailed_report()  # Full analysis
        """
        if report is None:
            report = self.generate_report()

        print()
        print("=" * 80)
        print("                    상세 성능 분석 보고서")
        print("=" * 80)
        print()

        # ========== Task Statistics ==========
        print("📊 작업 통계")
        print("─" * 80)

        tcr_data = report.accuracy_metrics.get("tcr", {})
        success_count = tcr_data.get("full_success", 0) + tcr_data.get("partial_success", 0)
        failure_count = tcr_data.get("failures", 0)

        print(f"  총 작업 수              : {report.total_tasks}")
        print(f"  성공                    : {success_count} ({success_count/report.total_tasks*100:.1f}%)" if report.total_tasks > 0 else "  성공                    : 0 (0.0%)")
        print(f"  실패                    : {failure_count} ({failure_count/report.total_tasks*100:.1f}%)" if report.total_tasks > 0 else "  실패                    : 0 (0.0%)")

        # Retry statistics
        retries = report.efficiency_metrics.get("retries", {})
        if retries:
            print(f"  평균 재시도 횟수        : {retries.get('avg_attempts_per_task', 0):.1f}")
        print()

        # ========== Layer 1: Native Metrics ==========
        print("✅ Layer 1: Native Metrics (기본 성능 지표)")
        print("─" * 80)

        # Accuracy
        print("  [정확도]")
        print(f"    - TCR                 : {tcr_data.get('tcr', 0):.1f}%")

        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print(f"    - Accuracy (평균)     : {accuracy.get('overall_accuracy', 0):.1f}%")
            print(f"    - Accuracy (중앙값)   : {accuracy.get('median_accuracy', 0):.1f}%")

        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"    - Hallucination Rate  : {hall.get('overall_rate', 0):.1f}%")
        print()

        # Latency
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print("  [지연시간]")
            print(f"    - 평균               : {latency.get('mean', 0):.2f}초")
            print(f"    - 중앙값             : {latency.get('median', 0):.2f}초")
            print(f"    - P95                : {latency.get('p95', 0):.2f}초")
            print(f"    - P99                : {latency.get('p99', 0):.2f}초")
            if 'min' in latency:
                print(f"    - 최소               : {latency.get('min', 0):.2f}초")
            if 'max' in latency:
                print(f"    - 최대               : {latency.get('max', 0):.2f}초")
            print()

        # Tokens
        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            print("  [토큰 사용량]")
            print(f"    - 총 Input Tokens    : {tokens.get('total_input_tokens', 0):,}")
            print(f"    - 총 Output Tokens   : {tokens.get('total_output_tokens', 0):,}")
            print(f"    - 총 Tokens          : {tokens.get('total_tokens', 0):,}")
            print(f"    - 평균 (작업당)      : {tokens.get('avg_tokens_per_task', 0):.0f} tokens")
            print()

        # Cost
        if tokens:
            print("  [비용]")
            print(f"    - 총 비용            : ${tokens.get('total_cost', 0):.4f}")
            print(f"    - 평균 (작업당)      : ${tokens.get('avg_cost_per_task', 0):.4f}")
            if 'estimated_monthly_cost' in tokens:
                print(f"    - 예상 월간 비용     : ${tokens.get('estimated_monthly_cost', 0):.2f}")
            print()

        # ========== Layer 2: Agentic AI Metrics ==========
        print("⚙️  Layer 2: Agentic AI Metrics (에이전트 시스템 지표)")
        print("─" * 80)

        # Tool usage
        tool_eff = report.efficiency_metrics.get("tool_efficiency", {})
        if tool_eff and tool_eff.get("total_calls", 0) > 0:
            print("  [도구 사용]")

            # Tool selection accuracy (if available)
            tool_selection = self.tool_selection_tracker.get_accuracy_stats()
            if tool_selection and tool_selection.get('total_evaluations', 0) > 0:
                print(f"    - Tool Selection Accuracy    : {tool_selection.get('avg_accuracy', 0):.1f}%")

            print(f"    - Tool Efficiency            : {tool_eff.get('avg_efficiency_score', 0):.1f}%")
            print(f"    - 평균 도구 호출 수          : {tool_eff.get('avg_calls_per_task', 0):.1f}")

            if 'redundancy_rate' in tool_eff:
                print(f"    - 중복 호출 비율             : {tool_eff.get('redundancy_rate', 0):.1f}%")
            print()

        # Agent coordination
        coord_stats = self.agent_coordination_tracker.calculate_coordination_score()
        if coord_stats and coord_stats.get('total_interactions', 0) > 0:
            print("  [에이전트 협업]")
            print(f"    - Agent Coordination Score   : {coord_stats.get('overall_score', 0):.2f}")
            print(f"    - 협업 성공률                : {coord_stats.get('success_rate', 0):.1f}%")
            print(f"    - 고유 에이전트 수           : {coord_stats.get('unique_agents', 0)}")
            print(f"    - 총 상호작용 수             : {coord_stats.get('total_interactions', 0)}")
            print()

        # Workflow execution
        workflow_stats = self.workflow_tracker.calculate_execution_success_rate()
        if workflow_stats and workflow_stats.get('total_tasks', 0) > 0:
            print("  [워크플로우 실행]")
            print(f"    - Workflow Success Rate      : {workflow_stats.get('task_success_rate', 0):.1f}%")
            print(f"    - Step Success Rate          : {workflow_stats.get('step_success_rate', 0):.1f}%")
            print(f"    - 평균 단계 수               : {workflow_stats.get('avg_steps_per_task', 0):.1f}")
            print(f"    - 총 실행 태스크 수          : {workflow_stats.get('total_tasks', 0)}")
            print()

        # If no Layer 2 metrics
        if (not tool_eff or tool_eff.get("total_calls", 0) == 0) and \
           (not coord_stats or coord_stats.get('total_interactions', 0) == 0) and \
           (not workflow_stats or workflow_stats.get('total_tasks', 0) == 0):
            print("  (Layer 2 메트릭 데이터 없음)")
            print()

        # ========== Layer 3: Advanced Metrics (if HybridMonitor) ==========
        # Note: This section is a placeholder for advanced metrics
        # Full implementation would require checking if this is a HybridMonitor instance
        has_advanced_metrics = False

        if hasattr(self, 'metric_adapters') and len(getattr(self, 'metric_adapters', {})) > 0:
            print("🎯 Layer 3: Advanced Metrics (고급 평가 지표)")
            print("─" * 80)
            print("  (HybridPerformanceMonitor 사용 시 DeepEval, Ragas 메트릭 표시)")
            print()
            has_advanced_metrics = True

        # ========== Alerts ==========
        if report.alerts:
            print("🚨 경고 및 알림")
            print("─" * 80)
            for alert in report.alerts:
                severity_icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "high" else "🟢"
                print(f"{severity_icon} [{alert['severity'].upper()}] {alert['metric']}")
                print(f"   {alert['message']}")
                print(f"   → {alert['action']}")
                print()

        # ========== Recommendations ==========
        if report.recommendations:
            print("💡 개선 권장사항")
            print("─" * 80)
            for i, rec in enumerate(report.recommendations, 1):
                print(f"{i}. {rec['area']}")
                print(f"   문제: {rec['issue']}")
                print(f"   제안: {rec['suggestion']}")
                print(f"   영향: {rec['impact']}")
                print()

        print("=" * 80)
        print()

    def print_metric_breakdown(self, task_id: Optional[str] = None, verbose: bool = True) -> None:
        """
        Print detailed calculation breakdown for transparency (NEW)

        Shows how each metric is calculated with intermediate values,
        providing full transparency into the evaluation process.

        Args:
            task_id: Specific task ID to analyze. If None, shows aggregate breakdown.
            verbose: If True, shows step-by-step calculations.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_metric_breakdown("task_001", verbose=True)
        """
        print()
        print("=" * 80)
        print("        평가 지표 계산 과정 (Metric Calculation Breakdown)")
        print("=" * 80)
        print()

        if task_id:
            # Find specific task
            task = next((t for t in self.tcr_tracker.tasks if t.task_id == task_id), None)
            if not task:
                print(f"❌ Task ID '{task_id}'를 찾을 수 없습니다.")
                return

            print(f"🔍 Task ID: {task_id}")
            print(f"   Task Type: {task.task_type}")
            print(f"   Timestamp: {task.timestamp}")
            print()

            # ========== TCR Calculation ==========
            print("📊 1. Task Completion Rate (TCR) 계산")
            print("─" * 80)
            print(f"   Completion Score: {task.completion_score:.3f}")
            print()
            if verbose:
                print("   📝 계산 방법:")
                print("      - success=True이고 completion_score >= 0.7  → Full Success")
                print("      - success=True이고 completion_score < 0.7   → Partial Success")
                print("      - success=False                              → Failure")
                print()
                if task.success and task.completion_score >= 0.7:
                    print("   ✅ 이 작업: Full Success (completion_score >= 0.7)")
                elif task.success:
                    print("   ⚠️  이 작업: Partial Success (0 < completion_score < 0.7)")
                else:
                    print("   ❌ 이 작업: Failure (success=False)")
                print()

            # ========== Accuracy Calculation ==========
            print("📊 2. Accuracy Score 계산")
            print("─" * 80)
            print(f"   Accuracy Score: {task.accuracy_score:.3f}")
            print()
            if verbose:
                print("   📝 계산 방법 (4가지 유사도 메트릭 조합):")
                print("      1. Token Overlap Ratio (40% 가중치)")
                print("      2. Jaccard Similarity   (30% 가중치)")
                print("      3. LCS Similarity       (20% 가중치)")
                print("      4. Character Similarity (10% 가중치)")
                print()
                print("   ℹ️  이 점수는 응답과 정답(ground truth) 간 유사도를 측정합니다.")
                print()

            # ========== Latency ==========
            print("📊 3. Latency (응답 시간)")
            print("─" * 80)
            print(f"   Execution Time: {task.execution_time:.3f}초")
            print()

            # ========== Token Usage ==========
            print("📊 4. Token Usage & Cost")
            print("─" * 80)
            print(f"   Input Tokens:  {task.tokens_used.get('input', 0):,}")
            print(f"   Output Tokens: {task.tokens_used.get('output', 0):,}")
            print(f"   Total Tokens:  {task.tokens_used.get('total', 0):,}")
            print()
            if verbose:
                input_cost = task.tokens_used.get('input', 0) / 1_000_000 * self.token_tracker.pricing['input']
                output_cost = task.tokens_used.get('output', 0) / 1_000_000 * self.token_tracker.pricing['output']
                total_cost = input_cost + output_cost
                print("   📝 비용 계산:")
                print(f"      Input Cost  = {task.tokens_used.get('input', 0):,} tokens × ${self.token_tracker.pricing['input']}/1M = ${input_cost:.6f}")
                print(f"      Output Cost = {task.tokens_used.get('output', 0):,} tokens × ${self.token_tracker.pricing['output']}/1M = ${output_cost:.6f}")
                print(f"      Total Cost  = ${total_cost:.6f}")
                print()

            # ========== Tool Calls ==========
            if task.tool_calls:
                print("📊 5. Tool Calls")
                print("─" * 80)
                print(f"   Total Tool Calls: {len(task.tool_calls)}")
                for i, tool_call in enumerate(task.tool_calls, 1):
                    if isinstance(tool_call, str):
                        tool_name = tool_call
                    elif isinstance(tool_call, dict):
                        tool_name = tool_call.get('tool', 'unknown')
                    else:
                        tool_name = 'unknown'
                    print(f"   {i}. {tool_name}")
                print()

            # ========== Retry/Attempts ==========
            if task.attempts > 1:
                print("📊 6. Retry/Correction")
                print("─" * 80)
                print(f"   Attempts: {task.attempts}")
                print(f"   Retries:  {task.attempts - 1}")
                if verbose:
                    print()
                    print("   📝 Retry 효율성 계산:")
                    print(f"      최종 성공 여부: {'✅ 성공' if task.success else '❌ 실패'}")
                    print("      Retry Efficiency = 최종 성공 / 총 시도 횟수")
                print()

        else:
            # Aggregate breakdown
            print("📊 전체 작업 통합 분석")
            print()

            # TCR Breakdown
            print("1️⃣ Task Completion Rate (TCR)")
            print("─" * 80)
            tcr_result = self.tcr_tracker.calculate_tcr()
            total = tcr_result['total_tasks']
            full_success = sum(1 for t in self.tcr_tracker.tasks if t.success and t.completion_score >= 0.7)
            partial_success = sum(1 for t in self.tcr_tracker.tasks if t.success and t.completion_score < 0.7)
            failures = sum(1 for t in self.tcr_tracker.tasks if not t.success)

            print(f"   Total Tasks: {total}")
            print(f"   Full Success: {full_success} ({full_success/total*100:.1f}%)" if total > 0 else "   Full Success: 0 (0.0%)")
            print(f"   Partial Success: {partial_success} ({partial_success/total*100:.1f}%)" if total > 0 else "   Partial Success: 0 (0.0%)")
            print(f"   Failures: {failures} ({failures/total*100:.1f}%)" if total > 0 else "   Failures: 0 (0.0%)")
            print()
            if verbose:
                print("   📝 TCR 계산식:")
                print("      TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100")
                weighted_success = (full_success * 1.0 + partial_success * 0.5)
                tcr_calculated = (weighted_success / total * 100) if total > 0 else 0
                print(f"      TCR = ({full_success} × 1.0 + {partial_success} × 0.5) / {total} × 100")
                print(f"      TCR = {tcr_calculated:.2f}%")
                print()

            # Accuracy Breakdown
            print("2️⃣ Accuracy Score")
            print("─" * 80)
            accuracy_stats = self.accuracy_evaluator.get_accuracy_metrics()
            if accuracy_stats and 'scores' in accuracy_stats:
                scores = accuracy_stats['scores']
                print(f"   Total Evaluations: {len(scores)}")
                print(f"   Overall Accuracy: {accuracy_stats.get('overall_accuracy', 0):.1f}%")
                print(f"   Median Accuracy: {accuracy_stats.get('median_accuracy', 0):.1f}%")
                print()
                if verbose:
                    print("   📝 계산 방법:")
                    print("      - 각 작업의 accuracy_score를 수집")
                    print("      - Overall = 평균값")
                    print("      - Median = 중앙값")
                    print()

            # Latency Breakdown
            print("3️⃣ Latency Statistics")
            print("─" * 80)
            latency_stats = self.latency_tracker.get_latency_stats()
            if latency_stats:
                print(f"   Mean: {latency_stats.get('mean', 0):.3f}초")
                print(f"   Median: {latency_stats.get('median', 0):.3f}초")
                print(f"   P95: {latency_stats.get('p95', 0):.3f}초")
                print(f"   P99: {latency_stats.get('p99', 0):.3f}초")
                print()
                if verbose:
                    print("   📝 백분위수(Percentile) 계산:")
                    print("      - P95: 전체 작업 중 95%가 이 시간 이내에 완료")
                    print("      - P99: 전체 작업 중 99%가 이 시간 이내에 완료")
                    print()

            # Token & Cost Breakdown
            print("4️⃣ Token Usage & Cost")
            print("─" * 80)
            token_stats = self.token_tracker.get_usage_stats()
            if token_stats:
                print(f"   Total Input Tokens: {token_stats.get('total_input_tokens', 0):,}")
                print(f"   Total Output Tokens: {token_stats.get('total_output_tokens', 0):,}")
                print(f"   Total Tokens: {token_stats.get('total_tokens', 0):,}")
                print(f"   Total Cost: ${token_stats.get('total_cost', 0):.4f}")
                print()
                if verbose:
                    print("   📝 비용 계산식:")
                    print(f"      Input Cost  = {token_stats.get('total_input_tokens', 0):,} × ${self.token_tracker.pricing['input']}/1M")
                    print(f"      Output Cost = {token_stats.get('total_output_tokens', 0):,} × ${self.token_tracker.pricing['output']}/1M")
                    print("      Total Cost  = Input Cost + Output Cost")
                    print()

        print("=" * 80)
        print()
        print("ℹ️  투명성 노트: 이 분석은 평가 과정의 완전한 투명성을 제공합니다.")
        print("   모든 계산 로직은 오픈소스로 공개되어 있으며, 필요 시 수정 가능합니다.")
        print()

    def explain_metric(self, metric_name: str) -> None:
        """
        Explain how a specific metric is calculated (NEW)

        Provides detailed explanation of metric calculation methodology,
        formulas, and interpretation guidelines.

        Args:
            metric_name: Metric to explain (tcr, accuracy, latency, cost, etc.)

        Example:
            >>> monitor = PerformanceMonitor()
            >>> monitor.explain_metric("tcr")
            >>> monitor.explain_metric("accuracy")
        """
        explanations = {
            "tcr": {
                "name": "Task Completion Rate (TCR)",
                "purpose": "작업의 완료 여부와 완료 품질을 측정합니다.",
                "calculation": """
    1. 각 작업을 3가지 범주로 분류:
       - Full Success: success=True and completion_score >= 0.7
       - Partial Success: success=True and completion_score < 0.7
       - Failure: success=False

    2. 가중 평균 계산:
       TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100
                """,
                "interpretation": """
    - 95% 이상: 우수 (Industry Benchmark)
    - 90-95%: 양호
    - 80-90%: 개선 필요
    - 80% 미만: 긴급 개선 필요
                """,
                "transparency_notes": """
    - completion_score는 응답 길이, 에러 여부, ground truth 유사도 기반
    - 기준값(0.7)은 조정 가능
    - 전체 계산 로직은 TaskCompletionTracker.calculate_tcr()에 공개
                """
            },
            "accuracy": {
                "name": "Accuracy Score",
                "purpose": "Agent 응답이 정답(ground truth)과 얼마나 유사한지 측정합니다.",
                "calculation": """
    4가지 유사도 메트릭 조합:

    1. Token Overlap Ratio (40% 가중치)
       - 공통 단어 수 / 최대 단어 수

    2. Jaccard Similarity (30% 가중치)
       - 교집합 크기 / 합집합 크기

    3. Longest Common Subsequence (20% 가중치)
       - 최장 공통 부분 수열 길이 / 최대 길이

    4. Character-level Similarity (10% 가중치)
       - Levenshtein distance 기반

    최종 점수 = Σ(각 메트릭 × 가중치)
                """,
                "interpretation": """
    - 90% 이상: 매우 정확
    - 80-90%: 정확
    - 70-80%: 보통
    - 70% 미만: 부정확
                """,
                "transparency_notes": """
    - 각 유사도 알고리즘은 taskresult_helpers.py에 구현
    - 가중치는 연구 기반 최적화된 값
    - 도메인별로 가중치 조정 가능
                """
            },
            "latency": {
                "name": "Latency (응답 시간)",
                "purpose": "Agent가 작업을 완료하는 데 걸린 시간을 측정합니다.",
                "calculation": """
    1. 각 작업의 execution_time 수집
    2. 통계 계산:
       - Mean (평균): Σ(시간) / 개수
       - Median (중앙값): 정렬 후 중간 값
       - P95: 하위 95% 지점의 값
       - P99: 하위 99% 지점의 값
                """,
                "interpretation": """
    P95 Latency 기준:
    - 1초 미만: 매우 빠름
    - 1-3초: 빠름 (대부분의 QA 작업)
    - 3-5초: 보통
    - 5-10초: 느림 (개선 권장)
    - 10초 이상: 매우 느림 (즉시 개선)
                """,
                "transparency_notes": """
    - P95/P99는 이상치(outlier)를 고려한 안정적인 지표
    - 평균만으로는 실제 사용자 경험을 대표하기 어려움
    - 계산 로직: LatencyTracker.get_latency_stats()
                """
            },
            "cost": {
                "name": "Token Cost (비용)",
                "purpose": "LLM API 사용 비용을 계산합니다.",
                "calculation": """
    1. Input Cost:
       Input Cost = (Total Input Tokens / 1,000,000) × Input Price

    2. Output Cost:
       Output Cost = (Total Output Tokens / 1,000,000) × Output Price

    3. Total Cost:
       Total Cost = Input Cost + Output Cost
                """,
                "interpretation": """
    작업당 평균 비용 기준:
    - $0.001 미만: 매우 효율적
    - $0.001-$0.01: 효율적
    - $0.01-$0.05: 보통
    - $0.05 이상: 비효율적 (최적화 필요)
                """,
                "transparency_notes": """
    - 가격은 초기화 시 설정 (기본: GPT-4 Turbo 가격)
    - 실제 가격은 OpenAI pricing 페이지 참조
    - 계산 로직: TokenEconomyTracker.get_usage_stats()
                """
            },
            "hallucination": {
                "name": "Hallucination Rate (환각 발생률)",
                "purpose": "Agent가 사실이 아닌 정보를 생성하는 비율을 측정합니다.",
                "calculation": """
    1. 각 응답을 분석하여 환각 여부 판정:
       - Context와 충돌하는 주장
       - Ground truth와 완전히 다른 정보
       - 사실이 아닌 추가 정보

    2. Hallucination Rate 계산:
       Rate = (환각 발생 작업 수 / 총 작업 수) × 100
                """,
                "interpretation": """
    - 0-2%: 우수
    - 2-5%: 양호
    - 5-10%: 개선 필요
    - 10% 이상: 심각 (즉시 개선)
                """,
                "transparency_notes": """
    - 환각 탐지 로직: HallucinationDetector.detect_hallucination()
    - Context 기반 검증
    - 필요시 사용자 정의 탐지 로직 추가 가능
                """
            }
        }

        metric_name = metric_name.lower()

        if metric_name not in explanations:
            print(f"❌ 알 수 없는 메트릭: '{metric_name}'")
            print()
            print("사용 가능한 메트릭:")
            for key in explanations.keys():
                print(f"  - {key}")
            return

        info = explanations[metric_name]

        print()
        print("=" * 80)
        print(f"   📖 {info['name']} - 상세 설명")
        print("=" * 80)
        print()

        print("🎯 목적")
        print("─" * 80)
        print(info['purpose'])
        print()

        print("🧮 계산 방법")
        print("─" * 80)
        print(info['calculation'])
        print()

        print("📊 해석 가이드")
        print("─" * 80)
        print(info['interpretation'])
        print()

        print("🔍 투명성 노트")
        print("─" * 80)
        print(info['transparency_notes'])
        print()

        print("=" * 80)
        print()

    def export_report(self, filename: str, format: str = "json") -> None:
        """Export report to file"""
        report = self.generate_report()
        
        if format == "json":
            _dir = os.path.dirname(os.path.abspath(filename)) or "."
            _fd, _tmp = tempfile.mkstemp(dir=_dir, suffix=".tmp")
            try:
                with os.fdopen(_fd, 'w', encoding='utf-8') as _f:
                    json.dump(asdict(report), _f, indent=2, default=str)
                os.replace(_tmp, filename)
            except Exception as e:
                logger.error("export_report JSON 저장 실패: %s", e, exc_info=True)
                try:
                    os.unlink(_tmp)
                except OSError:
                    pass
                raise
        elif format == "csv":
            # Export comprehensive metrics to CSV
            data = {
                "Metric": [],
                "Value": [],
                "Unit": []
            }

            # Layer 1 Metrics
            # TCR
            tcr = report.accuracy_metrics.get("tcr", {})
            data["Metric"].append("Task Completion Rate (TCR)")
            data["Value"].append(f"{tcr.get('tcr', 0):.2f}")
            data["Unit"].append("%")

            # Accuracy
            accuracy_scores = report.accuracy_metrics.get("accuracy_scores", {})
            data["Metric"].append("Overall Accuracy")
            data["Value"].append(f"{accuracy_scores.get('overall_accuracy', 0):.2f}")
            data["Unit"].append("%")

            # Hallucination Rate
            hall_data = self.hallucination_detector.get_hallucination_rate()
            data["Metric"].append("Hallucination Rate")
            data["Value"].append(f"{hall_data.get('overall_rate', 0):.2f}")
            data["Unit"].append("%")

            # Quality Score
            quality_data = self.quality_evaluator.get_quality_metrics()
            if quality_data:
                avg_quality = quality_data.get('avg_total_score', 0) * 2  # Convert to 10-point scale
                data["Metric"].append("Response Quality")
                data["Value"].append(f"{avg_quality:.2f}")
                data["Unit"].append("/10")

            # Latency
            latency_stats = report.efficiency_metrics.get("latency", {})
            data["Metric"].append("Average Latency")
            data["Value"].append(f"{latency_stats.get('mean', 0):.3f}")
            data["Unit"].append("s")

            data["Metric"].append("P95 Latency")
            data["Value"].append(f"{latency_stats.get('p95', 0):.3f}")
            data["Unit"].append("s")

            # Token Usage & Cost
            token_stats = report.efficiency_metrics.get("tokens", {})
            data["Metric"].append("Total Input Tokens")
            data["Value"].append(f"{token_stats.get('total_input_tokens', 0)}")
            data["Unit"].append("tokens")

            data["Metric"].append("Total Output Tokens")
            data["Value"].append(f"{token_stats.get('total_output_tokens', 0)}")
            data["Unit"].append("tokens")

            data["Metric"].append("Total Cost")
            data["Value"].append(f"{token_stats.get('total_cost', 0):.4f}")
            data["Unit"].append("$")

            data["Metric"].append("Avg Cost per Task")
            data["Value"].append(f"{token_stats.get('avg_cost_per_task', 0):.4f}")
            data["Unit"].append("$")

            # Layer 2 Metrics (if available)
            tool_stats = self.tool_selection_tracker.get_accuracy_stats()
            if tool_stats:
                data["Metric"].append("Tool Selection Accuracy")
                data["Value"].append(f"{tool_stats.get('avg_accuracy', 0):.2f}")
                data["Unit"].append("%")

                data["Metric"].append("Tool Selection F1 Score")
                data["Value"].append(f"{tool_stats.get('avg_f1_score', 0):.2f}")
                data["Unit"].append("%")

            # RAG Metrics (Layer 3)
            rag_summary = self.get_rag_metrics_summary()
            for metric_name, metric_data in rag_summary.items():
                if metric_data['count'] > 0:
                    display_name = metric_name.replace('_', ' ').title()
                    data["Metric"].append(display_name)
                    data["Value"].append(f"{metric_data['mean']:.3f}")
                    data["Unit"].append("score")

            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
        
        print(f"Report exported to {filename}")

    def save_to_file(self, filename: str = "performance_data.json") -> str:
        """
        Save all performance data to a JSON file

        Automatically includes:
        - Task data
        - Full report data (accuracy, efficiency, quality, security metrics)
        - All evaluator data (quality, hallucination, security, etc.)
        - RAG metrics
        - Completion tracker data

        Args:
            filename: Output filename (relative paths are automatically resolved to Dashboard data directory)

        Note:
            Always includes full report data for Dashboard compatibility.
        """
        # ⚡ Lazy initialization: 디렉토리를 실제 저장 시점에 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Zero Configuration: 자동으로 올바른 위치에 저장
        if not os.path.isabs(filename):
            filename = str(self.output_dir / filename)

        # 확장자가 없으면 .json 자동 추가 (대시보드 로더가 *.json 패턴으로 탐색)
        if not os.path.splitext(filename)[1]:
            filename = filename + ".json"

        pricing_data: Dict[str, Any] = dict(self.token_tracker.pricing)

        # P: tasks 읽기 시 얕은 복사로 lock 보호 — 다른 스레드의 record_task()와 충돌 방지
        with self._tasks_lock:
            _tasks_snapshot = list(self.tcr_tracker._tasks)

        data = {
            "tasks": [asdict(task) for task in _tasks_snapshot],
            "pricing": pricing_data,
            "model_name": self.model_name,
            "timestamp": datetime.now().isoformat(),
            # Save evaluator data
            "evaluators": {
                "accuracy": {
                    "evaluations": self.accuracy_evaluator.evaluations
                },
                "quality": {
                    "evaluations": self.quality_evaluator.evaluations
                },
                "hallucination": {
                    "detections": self.hallucination_detector.detections
                },
                "retry": {
                    "attempts": self.retry_tracker.attempts
                },
                "tool_calls": {
                    "executions": self.tool_analyzer.executions
                },
                "tool_selection": {
                    "selections": self.tool_selection_tracker.selections
                },
                "agent_coordination": {
                    "interactions": self.agent_coordination_tracker.interactions
                },
                "workflow": {
                    "executions": self.workflow_tracker.executions
                }
            },
            # Save RAG metrics
            "rag_metrics": self._rag_metrics,
            # Save advanced metrics summary (DeepEval, Ragas 등)
            "advanced_metrics_summary": getattr(self, '_advanced_metrics_summary', {}),
            # Phase 1-C: 멀티턴 대화 세션
            "conversation_sessions": [
                s.to_dict() if hasattr(s, "to_dict") else s
                for s in self.conversation_sessions
            ],
            # Phase 2-C: 암묵적 피드백 (optional — absent when ImplicitFeedbackTracker not installed)
            "feedback": (
                {**self.feedback_tracker.get_stats(), "records": self.feedback_tracker.feedbacks}
                if self.feedback_tracker is not None
                else {"available": False}
            ),
        }

        # Phase 2-A: StreamingEvaluator 슬라이딩 윈도우 스냅샷 (opt-in)
        if self._streaming_snapshot:
            data["streaming_data"] = self._streaming_snapshot

        # Auto-add security evaluators if enabled
        if hasattr(self, 'input_sanitizer') and self.input_sanitizer is not None:
            security_data = self._get_security_evaluator_data()
            if security_data:  # Only add if there's actually security data
                data["evaluators"]["security"] = security_data

        # Phase 3-B: 이상 감지 자동 통합 (opt-in)
        if self.enable_anomaly_detection:
            try:
                from ...anomaly import AnomalyDetector
                _detector = AnomalyDetector(
                    baseline_window=self._anomaly_baseline_window,
                    detection_window=self._anomaly_detection_window,
                )
                _anomalies = _detector.scan(self)
                data["anomaly_data"] = {
                    "anomalies": [a.to_dict() for a in _anomalies],
                    "scanned_at": datetime.now().isoformat(),
                    "baseline_window": self._anomaly_baseline_window,
                    "detection_window": self._anomaly_detection_window,
                }
                logger.info(
                    "이상 감지 완료: %d개 이상 탐지 (baseline=%d, detection=%d)",
                    len(_anomalies),
                    self._anomaly_baseline_window,
                    self._anomaly_detection_window,
                )
            except Exception as e:
                logger.warning("이상 감지 실패 (JSON 저장은 정상): %s", e)

        # Always add full report data (for Dashboard compatibility)
        self._append_report_data(data)

        # Convert datetime objects and enum values to strings
        for task in data["tasks"]:
            if isinstance(task.get("timestamp"), datetime):
                task["timestamp"] = task["timestamp"].isoformat()
            tt = task.get("task_type")
            if hasattr(tt, "value"):
                task["task_type"] = tt.value

        # R: 태스크 수가 임계값 이상이면 스트리밍 직렬화 모드 사용 (메모리 효율)
        _serialized_tasks: List = data["tasks"]
        _task_count = len(_serialized_tasks)

        # Atomic write: write to a temp file in the same directory, then rename.
        # Prevents partial-write corruption if the process is killed mid-write.
        _dir = os.path.dirname(os.path.abspath(filename))
        _fd, _tmp_path = tempfile.mkstemp(dir=_dir, suffix=".tmp")
        try:
            with os.fdopen(_fd, 'w', encoding='utf-8') as _f:
                if _task_count >= _STREAMING_THRESHOLD:
                    logger.debug(
                        "save_to_file: 스트리밍 모드 사용 (%d개 태스크)", _task_count
                    )
                    _write_json_streaming(_f, data, _serialized_tasks)
                else:
                    json.dump(data, _f, indent=2, default=_json_serializer)
            os.replace(_tmp_path, filename)
        except Exception as e:
            logger.error("save_to_file JSON 저장 실패: %s", e, exc_info=True)
            try:
                os.unlink(_tmp_path)
            except OSError:
                pass
            raise

        logger.info("Performance data saved to %s", filename)

        # HTML 보고서 자동 생성 (실패해도 JSON 저장은 완료된 것으로 처리)
        try:
            from ...reporting.comprehensive_report import generate_comprehensive_html_report
            html_path = filename if filename.endswith(".html") else filename.rsplit(".json", 1)[0] + ".html"
            if not html_path.endswith(".html"):
                html_path = filename + ".html"
            html_content = generate_comprehensive_html_report(self)
            _html_dir = os.path.dirname(os.path.abspath(html_path))
            _hfd, _h_tmp = tempfile.mkstemp(dir=_html_dir, suffix=".tmp")
            try:
                with os.fdopen(_hfd, 'w', encoding='utf-8') as _hf:
                    _hf.write(html_content)
                os.replace(_h_tmp, html_path)
            except Exception as e:
                logger.error("save_to_file HTML 저장 실패: %s", e, exc_info=True)
                try:
                    os.unlink(_h_tmp)
                except OSError:
                    pass
                raise
            logger.info("HTML report saved to %s", html_path)
        except Exception as e:
            logger.warning("HTML report generation failed (JSON saved): %s", e)

        # Auto transparency: generate metric traces + audit logs
        if self.transparency_manager:
            try:
                self._auto_transparency_on_save(filename)
            except Exception as e:
                logger.warning("투명성 데이터 생성 실패 (평가 결과는 정상 저장됨): %s", e)

        # 레지스트리에 자동 등록
        try:
            from ...utils.data_registry import DataRegistry

            abs_path = os.path.abspath(filename)

            # 메타데이터 수집
            metadata = {
                "total_tasks": len(self.tcr_tracker.tasks),
                "framework": None,
                "task_types": []
            }

            # Framework 정보 (첫 번째 task에서)
            if self.tcr_tracker.tasks:
                first_task = self.tcr_tracker.tasks[0]
                metadata["framework"] = getattr(first_task, "framework", None)

                # Task types 수집 (JSON 직렬화를 위해 문자열로 변환)
                task_types = set(task.task_type for task in self.tcr_tracker.tasks)
                metadata["task_types"] = [str(tt.value) if hasattr(tt, 'value') else str(tt) for tt in task_types]

            # 레지스트리 등록
            success = DataRegistry.register_data_file(
                filepath=abs_path,
                metadata=metadata
            )

            if success:
                logger.debug("Dashboard 레지스트리에 자동 등록됨 (~/.agent_evaluator/registry.json)")

        except Exception as e:
            # 레지스트리 등록 실패해도 데이터 저장은 성공한 것으로 처리
            logger.warning("레지스트리 등록 실패 (데이터는 정상 저장됨): %s", e)

        # Phoenix Annotation API — accuracy / completion / success 점수 전송
        self._flush_phoenix_annotations()

        # OTEL Metrics — 세션 단위 ae.tcr 전송 (per-task 합산 오류 방지)
        try:
            from agent_evaluator.core.otel import get_metrics
            m = get_metrics()
            if m and m.enabled:
                session_tcr = float(self.tcr_tracker.calculate_tcr() * 100)
                m.record("ae.tcr", session_tcr, {})
        except Exception as _e:
            logger.debug("OTEL metrics ae.tcr 전송 실패 (무시): %s", _e)

        # G2: 압축 저장 (enable_compression() 호출 시)
        _comp_alg = getattr(self, "_compression_algorithm", None)
        if _comp_alg:
            try:
                import gzip as _gzip
                import bz2 as _bz2
                _json_path = Path(filename)
                _comp_path = Path(str(_json_path) + (".gz" if _comp_alg == "gzip" else ".bz2"))
                with open(_json_path, "rb") as _fin:
                    _raw = _fin.read()
                if _comp_alg == "gzip":
                    with _gzip.open(_comp_path, "wb") as _fout:
                        _fout.write(_raw)
                else:
                    with _bz2.open(_comp_path, "wb") as _fout:
                        _fout.write(_raw)
                logger.debug("압축 저장 완료: %s", _comp_path)
            except Exception as _ce:
                logger.debug("압축 저장 실패 (무시): %s", _ce)

        return filename

    def aggregate_by_time(
        self,
        granularity: str = "hour",
    ) -> Dict[str, Dict[str, Any]]:
        """시간 단위별 지표 집계.

        ``tcr_tracker.tasks`` 의 ``timestamp`` 필드를 기준으로 태스크를
        시간 버킷으로 분류하고 버킷별 TCR, 평균 accuracy, 평균 latency, 건수를 반환한다.

        Args:
            granularity: 집계 단위 — ``"minute"``, ``"hour"`` (기본), ``"day"``.

        Returns:
            버킷 키 → 집계 통계 딕셔너리.  버킷 키는 ``granularity`` 에 따라
            ``"2026-04-04T14:00"``, ``"2026-04-04T14:23"``, ``"2026-04-04"`` 형태.

            각 값은 ``{"tcr": float, "avg_accuracy": float, "avg_latency": float,
            "count": int, "error_count": int}`` 구조.

        Example::

            monitor = PerformanceMonitor("results/")
            # ... 태스크 수집 ...
            hourly = monitor.aggregate_by_time("hour")
            for bucket, stats in hourly.items():
                print(f"{bucket}: TCR={stats['tcr']}%, count={stats['count']}")
        """
        from datetime import datetime as _dt

        _FMT: Dict[str, str] = {
            "minute": "%Y-%m-%dT%H:%M",
            "hour":   "%Y-%m-%dT%H:00",
            "day":    "%Y-%m-%d",
        }
        fmt = _FMT.get(granularity, _FMT["hour"])

        buckets: Dict[str, list] = {}
        for task in self.tcr_tracker.tasks:
            try:
                ts_raw = task.timestamp
                if isinstance(ts_raw, str):
                    ts = _dt.fromisoformat(ts_raw)
                elif hasattr(ts_raw, "strftime"):
                    ts = ts_raw
                else:
                    continue
                key = ts.strftime(fmt)
            except Exception:
                continue
            buckets.setdefault(key, []).append(task)

        result: Dict[str, Dict[str, Any]] = {}
        for key in sorted(buckets):
            tasks = buckets[key]
            n = len(tasks)
            successes = sum(1 for t in tasks if t.success)
            result[key] = {
                "tcr":          round(successes / n * 100, 1) if n else 0.0,
                "avg_accuracy": round(sum(t.accuracy_score for t in tasks) / n, 3) if n else 0.0,
                "avg_latency":  round(sum(t.execution_time for t in tasks) / n, 3) if n else 0.0,
                "count":        n,
                "error_count":  n - successes,
            }
        return result

    # ------------------------------------------------------------------
    # C1: estimate_token_cost_per_request
    # ------------------------------------------------------------------

    def estimate_token_cost_per_request(
        self,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """요청 1건당 평균 토큰 비용을 추정한다 (C1).

        Args:
            task_type: 지정 시 해당 task_type 태스크만 집계.  ``None`` 이면 전체.

        Returns:
            ``{"task_type": str | None, "count": int, "avg_input_tokens": float,
               "avg_output_tokens": float, "avg_total_tokens": float,
               "avg_cost_usd": float, "total_cost_usd": float}``

        Example::

            stats = monitor.estimate_token_cost_per_request("qa")
            print(f"QA 1건당 비용: ${stats['avg_cost_usd']:.6f}")
        """
        pricing = getattr(self, "token_tracker", None)
        input_price = self.token_tracker.pricing.get("input", 0.003) if pricing else 0.003
        output_price = self.token_tracker.pricing.get("output", 0.015) if pricing else 0.015

        tasks = self.tcr_tracker.tasks
        if task_type is not None:
            _tt = task_type.lower()
            tasks = [t for t in tasks if str(getattr(t, "task_type", "")).lower() == _tt]

        count = len(tasks)
        if count == 0:
            return {
                "task_type": task_type,
                "count": 0,
                "avg_input_tokens": 0.0,
                "avg_output_tokens": 0.0,
                "avg_total_tokens": 0.0,
                "avg_cost_usd": 0.0,
                "total_cost_usd": 0.0,
            }

        total_inp = total_out = total_cost = 0.0
        for t in tasks:
            tu = t.tokens_used or {}
            inp = float(tu.get("input", 0) or 0)
            out = float(tu.get("output", 0) or 0)
            total = float(tu.get("total", 0) or (inp + out))
            cost = (inp * input_price + out * output_price) / 1000.0
            total_inp += inp
            total_out += out
            total_cost += cost

        return {
            "task_type":          task_type,
            "count":              count,
            "avg_input_tokens":   round(total_inp / count, 1),
            "avg_output_tokens":  round(total_out / count, 1),
            "avg_total_tokens":   round((total_inp + total_out) / count, 1),
            "avg_cost_usd":       round(total_cost / count, 8),
            "total_cost_usd":     round(total_cost, 6),
        }

    # ------------------------------------------------------------------
    # C2: compare_models
    # ------------------------------------------------------------------

    def compare_models(
        self,
        model_names: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """모델별 성능 지표를 비교한다 (C2).

        ``TaskResult.tokens_used["model"]`` 필드를 기준으로 태스크를 그룹화한다.
        ``model_names`` 를 지정하면 해당 모델만 반환한다.

        Returns:
            ``{model_name: {"count", "tcr", "avg_accuracy", "avg_latency",
                            "avg_input_tokens", "avg_output_tokens", "avg_cost_usd"}}``

        Example::

            comparison = monitor.compare_models()
            for model, stats in comparison.items():
                print(f"{model}: TCR={stats['tcr']:.1f}%, accuracy={stats['avg_accuracy']:.3f}")
        """
        pricing = getattr(self.token_tracker, "pricing", {"input": 0.003, "output": 0.015})
        inp_price = float(pricing.get("input", 0.003))
        out_price = float(pricing.get("output", 0.015))

        groups: Dict[str, List[Any]] = defaultdict(list)
        for t in self.tcr_tracker.tasks:
            tu = t.tokens_used or {}
            model = str(tu.get("model") or getattr(t, "framework", "unknown") or "unknown")
            groups[model].append(t)

        if model_names is not None:
            groups = {k: v for k, v in groups.items() if k in model_names}

        result: Dict[str, Dict[str, Any]] = {}
        for model, tasks in groups.items():
            n = len(tasks)
            successes = sum(1 for t in tasks if t.success)
            total_inp = total_out = total_cost = 0.0
            for t in tasks:
                tu = t.tokens_used or {}
                inp = float(tu.get("input", 0) or 0)
                out = float(tu.get("output", 0) or 0)
                total_inp += inp
                total_out += out
                total_cost += (inp * inp_price + out * out_price) / 1000.0
            result[model] = {
                "count":             n,
                "tcr":               round(successes / n * 100, 2) if n else 0.0,
                "avg_accuracy":      round(sum(t.accuracy_score for t in tasks) / n, 4) if n else 0.0,
                "avg_latency":       round(sum(t.execution_time for t in tasks) / n, 3) if n else 0.0,
                "avg_input_tokens":  round(total_inp / n, 1) if n else 0.0,
                "avg_output_tokens": round(total_out / n, 1) if n else 0.0,
                "avg_cost_usd":      round(total_cost / n, 8) if n else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # C3: export_to_wandb / export_to_mlflow
    # ------------------------------------------------------------------

    def export_to_wandb(
        self,
        project: str,
        run_name: Optional[str] = None,
        **init_kwargs: Any,
    ) -> None:
        """평가 지표를 Weights & Biases 에 기록한다 (C3).

        Args:
            project: W&B 프로젝트 이름.
            run_name: Run 이름 (기본: ``"agent_eval_{timestamp}"``).
            **init_kwargs: ``wandb.init()`` 에 전달할 추가 파라미터.

        Raises:
            ImportError: ``wandb`` 가 설치되지 않은 경우.

        Example::

            monitor.export_to_wandb("my-agent-project", run_name="v1-eval")
        """
        try:
            import wandb  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "W&B 내보내기에는 wandb 패키지가 필요합니다: pip install wandb"
            ) from exc

        report = self.generate_report()
        acc_m = report.accuracy_metrics or {}
        eff_m = report.efficiency_metrics or {}
        run_name = run_name or f"agent_eval_{datetime.now().strftime('%Y%m%dT%H%M%S')}"

        metrics = {
            "eval/tcr":               float(acc_m.get("tcr", {}).get("tcr", 0.0)),
            "eval/accuracy":          float(acc_m.get("accuracy_scores", {}).get("overall_accuracy", 0.0)),
            "eval/total_tasks":       int(report.total_tasks),
            "eval/avg_latency_s":     float(eff_m.get("latency", {}).get("mean", 0.0)),
            "eval/p95_latency_s":     float(eff_m.get("latency", {}).get("p95", 0.0)),
            "eval/total_tokens":      int(eff_m.get("tokens", {}).get("total_tokens", 0)),
        }

        with wandb.init(project=project, name=run_name, **init_kwargs) as run:
            run.log(metrics)
            logger.info("W&B export 완료: project=%s run=%s", project, run_name)

    def export_to_mlflow(
        self,
        experiment_name: str,
        run_name: Optional[str] = None,
        tracking_uri: Optional[str] = None,
    ) -> None:
        """평가 지표를 MLflow 에 기록한다 (C3).

        Args:
            experiment_name: MLflow 실험 이름.
            run_name: Run 이름 (기본: ``"agent_eval_{timestamp}"``).
            tracking_uri: MLflow Tracking Server URI.  ``None`` 이면 기본값 사용.

        Raises:
            ImportError: ``mlflow`` 가 설치되지 않은 경우.

        Example::

            monitor.export_to_mlflow("my-experiment", run_name="v1-eval")
        """
        try:
            import mlflow  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "MLflow 내보내기에는 mlflow 패키지가 필요합니다: pip install mlflow"
            ) from exc

        if tracking_uri is not None:
            mlflow.set_tracking_uri(tracking_uri)

        report = self.generate_report()
        acc_m = report.accuracy_metrics or {}
        eff_m = report.efficiency_metrics or {}
        run_name = run_name or f"agent_eval_{datetime.now().strftime('%Y%m%dT%H%M%S')}"

        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=run_name):
            mlflow.log_metrics({
                "tcr":               float(acc_m.get("tcr", {}).get("tcr", 0.0)),
                "accuracy":          float(acc_m.get("accuracy_scores", {}).get("overall_accuracy", 0.0)),
                "total_tasks":       float(report.total_tasks),
                "avg_latency_s":     float(eff_m.get("latency", {}).get("mean", 0.0)),
                "p95_latency_s":     float(eff_m.get("latency", {}).get("p95", 0.0)),
                "total_tokens":      float(eff_m.get("tokens", {}).get("total_tokens", 0)),
            })
            logger.info("MLflow export 완료: experiment=%s run=%s", experiment_name, run_name)

    # ------------------------------------------------------------------
    # F1: configure_suspicious_patterns / evaluate_suspicious_patterns
    # ------------------------------------------------------------------

    def configure_suspicious_patterns(
        self,
        patterns: List[str],
    ) -> None:
        """의심 패턴 목록을 설정한다 (F1).

        ``evaluate_suspicious_patterns()`` 가 텍스트를 이 목록과 대조한다.
        패턴은 Python ``re`` 정규식 또는 고정 문자열로 해석된다.

        Args:
            patterns: 탐지할 패턴 목록 (정규식 또는 고정 문자열).

        Example::

            monitor.configure_suspicious_patterns([
                r"\\bpassword\\b",
                r"\\bsecret_key\\b",
                "DROP TABLE",
            ])
        """
        self._suspicious_patterns: List[str] = list(patterns)
        logger.debug("의심 패턴 %d개 설정됨", len(self._suspicious_patterns))

    def evaluate_suspicious_patterns(
        self,
        text: str,
    ) -> Dict[str, Any]:
        """텍스트에서 의심 패턴을 탐지한다 (F1).

        ``configure_suspicious_patterns()`` 로 설정된 패턴 목록을 사용한다.
        설정되지 않은 경우 빈 결과를 반환한다.

        Args:
            text: 검사할 문자열.

        Returns:
            ``{"matched": bool, "patterns_matched": List[str], "match_count": int}``

        Example::

            result = monitor.evaluate_suspicious_patterns(user_input)
            if result["matched"]:
                print(f"의심 패턴 감지: {result['patterns_matched']}")
        """
        patterns = getattr(self, "_suspicious_patterns", [])
        if not patterns:
            return {"matched": False, "patterns_matched": [], "match_count": 0}

        matched: List[str] = []
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    matched.append(pattern)
            except re.error:
                # 고정 문자열 폴백
                if pattern.lower() in text.lower():
                    matched.append(pattern)

        return {
            "matched":          bool(matched),
            "patterns_matched": matched,
            "match_count":      len(matched),
        }

    # ------------------------------------------------------------------
    # G2: enable_compression
    # ------------------------------------------------------------------

    def enable_compression(self, algorithm: str = "gzip") -> None:
        """저장 파일에 압축을 활성화한다 (G2).

        ``save_to_file()`` 호출 시 JSON 파일을 추가로 압축한다.

        Args:
            algorithm: ``"gzip"`` 또는 ``"bz2"`` (기본: ``"gzip"``).

        Example::

            monitor.enable_compression("gzip")
            monitor.save_to_file("results")
            # → results.json + results.json.gz 생성
        """
        _supported = {"gzip", "bz2"}
        if algorithm not in _supported:
            logger.warning("지원하지 않는 압축 알고리즘 '%s' — gzip 사용", algorithm)
            algorithm = "gzip"
        self._compression_algorithm: str = algorithm
        logger.debug("압축 활성화: algorithm=%s", algorithm)

    def compare(self, other: "PerformanceMonitor") -> Dict[str, Any]:
        """두 PerformanceMonitor 인스턴스의 주요 지표를 비교한다 (D1).

        Args:
            other: 비교 대상 :class:`PerformanceMonitor` 인스턴스.

        Returns:
            ``{"self": {...}, "other": {...}, "delta": {...}}`` 구조.
            ``delta`` 는 ``self - other`` 기준이며 latency 는 낮을수록 좋으므로
            양수가 self 가 *느림* 을 의미한다.

        Example::

            baseline = PerformanceMonitor("results/baseline/")
            candidate = PerformanceMonitor("results/candidate/")
            # ... 각각 평가 실행 ...
            diff = baseline.compare(candidate)
            print(f"TCR delta: {diff['delta']['tcr']:+.2f}%")
        """
        def _extract(m: "PerformanceMonitor") -> Dict[str, Any]:
            try:
                r = m.generate_report()
                acc = r.accuracy_metrics or {}
                eff = r.efficiency_metrics or {}
                return {
                    "total_tasks": r.total_tasks,
                    "tcr": round(float(acc.get("tcr", {}).get("tcr", 0.0)), 4),
                    "accuracy": round(float(acc.get("accuracy_scores", {}).get("overall_accuracy", 0.0)), 4),
                    "avg_latency": round(float(eff.get("latency", {}).get("mean", 0.0)), 4),
                    "p95_latency": round(float(eff.get("latency", {}).get("p95", 0.0)), 4),
                    "total_tokens": int(eff.get("tokens", {}).get("total_tokens", 0)),
                }
            except Exception as _e:
                logger.debug("PerformanceMonitor.compare: _extract 실패: %s", _e)
                return {"total_tasks": 0, "tcr": 0.0, "accuracy": 0.0,
                        "avg_latency": 0.0, "p95_latency": 0.0, "total_tokens": 0}

        s = _extract(self)
        o = _extract(other)
        delta: Dict[str, Any] = {}
        for key in ("tcr", "accuracy", "avg_latency", "p95_latency", "total_tokens", "total_tasks"):
            try:
                delta[key] = round(float(s.get(key, 0)) - float(o.get(key, 0)), 4)
            except (TypeError, ValueError):
                delta[key] = None
        return {"self": s, "other": o, "delta": delta}

    # ------------------------------------------------------------------
    # D1: filter_tasks — 조건부 태스크 필터링
    # ------------------------------------------------------------------

    def filter_tasks(
        self,
        task_type: Optional[str] = None,
        min_accuracy: Optional[float] = None,
        max_accuracy: Optional[float] = None,
        min_latency: Optional[float] = None,
        max_latency: Optional[float] = None,
        framework: Optional[str] = None,
        success_only: Optional[bool] = None,
        has_error: Optional[bool] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        min_completion: Optional[float] = None,
    ) -> List["TaskResult"]:
        """조건에 맞는 태스크 결과를 필터링해 반환 (D1).

        모든 조건은 AND로 결합된다.  조건이 ``None`` 이면 해당 조건은 스킵한다.

        Args:
            task_type: 필터링할 task_type 문자열 (e.g. ``"qa"``).
            min_accuracy: 이 값 이상인 태스크만 포함.
            max_accuracy: 이 값 이하인 태스크만 포함.
            min_latency: execution_time 이 이 값 이상인 태스크만 포함.
            max_latency: execution_time 이 이 값 이하인 태스크만 포함.
            framework: ``TaskResult.extra`` 의 ``"framework"`` 값과 일치하는 태스크.
                       ``"native"`` 를 지정하면 extra["framework"] 가 없는 태스크도 포함.
            success_only: ``True`` 이면 성공 태스크만, ``False`` 이면 실패 태스크만.
            has_error: ``True`` 이면 에러 있는 태스크만, ``False`` 이면 에러 없는 태스크만.
            since: 이 시점 이후 태스크만 포함 (inclusive).
            until: 이 시점 이전 태스크만 포함 (inclusive).
            min_completion: completion_score 이 이 값 이상인 태스크만 포함.

        Returns:
            조건에 맞는 :class:`TaskResult` 리스트.

        Example::

            slow_failed = monitor.filter_tasks(
                success_only=False,
                min_latency=5.0,
            )
        """
        result: List["TaskResult"] = []
        for task in self.tasks:
            # task_type 필터
            if task_type is not None:
                tt = task.task_type
                if hasattr(tt, "value"):
                    tt = tt.value
                if str(tt).lower() != task_type.lower():
                    continue
            # accuracy 필터
            if min_accuracy is not None and task.accuracy_score < min_accuracy:
                continue
            if max_accuracy is not None and task.accuracy_score > max_accuracy:
                continue
            # completion 필터
            if min_completion is not None and task.completion_score < min_completion:
                continue
            # latency 필터
            if min_latency is not None and task.execution_time < min_latency:
                continue
            if max_latency is not None and task.execution_time > max_latency:
                continue
            # framework 필터 (extra dict)
            if framework is not None:
                extra = task.extra if hasattr(task, "extra") and task.extra else {}
                fw_val = extra.get("framework") if extra else None
                if fw_val is None:
                    fw_val = "native"
                if str(fw_val).lower() != framework.lower():
                    continue
            # success_only 필터
            if success_only is not None and task.success != success_only:
                continue
            # has_error 필터
            if has_error is not None:
                task_has_error = bool(task.errors)
                if task_has_error != has_error:
                    continue
            # since / until 필터
            if since is not None or until is not None:
                try:
                    ts = task.timestamp
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    if since is not None and ts < since:
                        continue
                    if until is not None and ts > until:
                        continue
                except Exception as _e:
                    logger.debug("OTEL attr skipped (filter timestamp): %s", _e)
            result.append(task)
        return result

    def export_by_framework(self, framework: str, output_file: str) -> str:
        """특정 프레임워크의 태스크만 필터링해서 별도 파일로 저장합니다.

        Args:
            framework: 내보낼 프레임워크 이름
            output_file: 저장할 파일 기본 이름 (확장자 제외)

        Returns:
            저장된 JSON 파일 경로

        Raises:
            ValueError: 해당 프레임워크의 태스크가 없을 때
        """
        matched = self.filter_tasks(framework=framework)
        if not matched:
            raise ValueError(f"No tasks found for framework '{framework}'")

        # 임시로 tasks를 교체해서 save_to_file 호출
        original_tasks = list(self.tasks)
        self.tasks.clear()
        for t in matched:
            self.tasks.append(t)
        try:
            path = self.save_to_file(f"{output_file}_{framework}")
        finally:
            self.tasks.clear()
            for t in original_tasks:
                self.tasks.append(t)
        return path

    # ------------------------------------------------------------------
    # D2: aggregate_metrics — 시간 범위 및 그룹별 지표 집계
    # ------------------------------------------------------------------

    def aggregate_metrics(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """지표를 시간 범위 및 그룹별로 집계 (D2).

        Args:
            since: 시작 시간 (``None`` 이면 전체).
            until: 종료 시간 (``None`` 이면 전체).
            by: 그룹화 기준.
                ``None`` — 전체 집계,
                ``"task_type"`` — task_type별,
                ``"framework"`` — extra["framework"]별,
                ``"hour"`` — timestamp 시간(0-23)별,
                ``"day"`` — 날짜(YYYY-MM-DD)별.

        Returns:
            ``by=None`` 이면 집계 결과 dict,
            그 외엔 그룹 키 → 집계 dict 구조.
            집계 dict 키: ``"total"``, ``"tcr"``, ``"avg_accuracy"``,
            ``"avg_latency"``, ``"p95_latency"``, ``"total_tokens"``.

        Example::

            daily = monitor.aggregate_metrics(by="day")
            for date, stats in daily.items():
                print(f"{date}: TCR={stats['tcr']:.1f}%")
        """
        # 시간 필터 적용
        tasks = self.filter_tasks(since=since, until=until)

        def _calc(task_list: List["TaskResult"]) -> Dict[str, Any]:
            n = len(task_list)
            if n == 0:
                return {
                    "total": 0,
                    "tcr": 0.0,
                    "avg_accuracy": 0.0,
                    "avg_latency": 0.0,
                    "p95_latency": 0.0,
                    "total_tokens": 0,
                }
            successes = sum(1 for t in task_list if t.success)
            tcr = round(successes / n * 100, 2)
            avg_acc = round(sum(t.accuracy_score for t in task_list) / n, 4)
            avg_lat = round(sum(t.execution_time for t in task_list) / n, 4)
            latencies = sorted(t.execution_time for t in task_list)
            p95_idx = max(0, int(len(latencies) * 0.95) - 1)
            p95_lat = round(latencies[p95_idx], 4) if latencies else 0.0
            total_tokens = sum(
                (t.tokens_used.get("total", 0) if isinstance(t.tokens_used, dict) else 0)
                for t in task_list
            )
            return {
                "total": n,
                "tcr": tcr,
                "avg_accuracy": avg_acc,
                "avg_latency": avg_lat,
                "p95_latency": p95_lat,
                "total_tokens": int(total_tokens),
            }

        if by is None:
            return _calc(tasks)

        groups: Dict[str, List["TaskResult"]] = {}

        for task in tasks:
            if by == "task_type":
                tt = task.task_type
                key = tt.value if hasattr(tt, "value") else str(tt)
                key = key or "unknown"
            elif by == "framework":
                extra = task.extra if hasattr(task, "extra") and task.extra else {}
                key = str(extra.get("framework", "unknown")) or "unknown"
            elif by == "hour":
                try:
                    ts = task.timestamp
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    key = str(ts.hour)
                except Exception:
                    key = "unknown"
            elif by == "day":
                try:
                    ts = task.timestamp
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    key = ts.strftime("%Y-%m-%d")
                except Exception:
                    key = "unknown"
            else:
                key = "unknown"
            groups.setdefault(key, []).append(task)

        return {k: _calc(v) for k, v in sorted(groups.items())}

    # ------------------------------------------------------------------
    # D4: 트래커 메서드명 별칭 헬퍼
    # ------------------------------------------------------------------

    def get_tcr_metrics(self) -> Dict[str, Any]:
        """TCR 지표 반환 (D4 — TaskCompletionTracker.calculate_tcr() 별칭).

        Returns:
            TCR 집계 딕셔너리.  트래커가 없으면 빈 dict.
        """
        tcr = getattr(self, "tcr_tracker", None)
        if tcr is None:
            return {}
        fn = getattr(tcr, "calculate_tcr", None)
        return fn() if callable(fn) else {}

    def get_accuracy_metrics(self) -> Dict[str, Any]:
        """정확도 지표 반환 (D4 — AccuracyEvaluator.get_accuracy_metrics() 별칭).

        Returns:
            정확도 집계 딕셔너리.  트래커가 없으면 빈 dict.
        """
        ev = getattr(self, "accuracy_evaluator", None)
        if ev is None:
            return {}
        fn = getattr(ev, "get_accuracy_metrics", None)
        return fn() if callable(fn) else {}

    def get_latency_metrics(self) -> Dict[str, Any]:
        """레이턴시 지표 반환 (D4 — LatencyTracker.get_latency_stats() 별칭).

        Returns:
            레이턴시 집계 딕셔너리.  트래커가 없으면 빈 dict.
        """
        lt = getattr(self, "latency_tracker", None)
        if lt is None:
            return {}
        fn = getattr(lt, "get_latency_stats", None)
        return fn() if callable(fn) else {}

    def get_token_metrics(self) -> Dict[str, Any]:
        """토큰 사용량 지표 반환 (D4 — TokenEconomyTracker.get_usage_stats() 별칭).

        Returns:
            토큰 사용량 집계 딕셔너리.  트래커가 없으면 빈 dict.
        """
        tt = getattr(self, "token_tracker", None)
        if tt is None:
            return {}
        fn = getattr(tt, "get_usage_stats", None)
        return fn() if callable(fn) else {}

    # ------------------------------------------------------------------
    # D5: get_bottleneck_tasks / get_optimization_recommendations / analyze
    # ------------------------------------------------------------------

    def get_bottleneck_tasks(
        self,
        accuracy_threshold: float = 0.5,
        latency_threshold: Optional[float] = None,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """성능 병목 태스크 식별 (D5).

        Args:
            accuracy_threshold: 이 값 미만이면 저정확도 태스크로 분류.
            latency_threshold: 이 값 초과이면 고지연 태스크로 분류.
                ``None`` 이면 전체 태스크의 p95 latency를 기준으로 자동 설정.
            top_n: 각 카테고리 최대 반환 수.

        Returns:
            ``{"low_accuracy": [...], "high_latency": [...], "high_error_rate": [...]}``
            각 리스트 원소는 ``{"task_id", "task_type", "accuracy_score",
            "execution_time", "errors"}`` dict.
        """
        all_tasks = self.tasks

        def _task_info(t: "TaskResult") -> Dict[str, Any]:
            tt = t.task_type
            return {
                "task_id": t.task_id,
                "task_type": tt.value if hasattr(tt, "value") else str(tt),
                "accuracy_score": t.accuracy_score,
                "execution_time": t.execution_time,
                "errors": list(t.errors) if t.errors else [],
                "success": t.success,
            }

        # p95 latency 자동 계산
        if latency_threshold is None:
            latencies = sorted(t.execution_time for t in all_tasks) if all_tasks else []
            if latencies:
                p95_idx = max(0, int(len(latencies) * 0.95) - 1)
                latency_threshold = latencies[p95_idx]
            else:
                latency_threshold = 10.0  # fallback

        low_accuracy = sorted(
            [t for t in all_tasks if t.accuracy_score < accuracy_threshold],
            key=lambda t: t.accuracy_score,
        )[:top_n]

        high_latency = sorted(
            [t for t in all_tasks if t.execution_time > latency_threshold],
            key=lambda t: -t.execution_time,
        )[:top_n]

        high_error = sorted(
            [t for t in all_tasks if t.errors],
            key=lambda t: -len(t.errors),
        )[:top_n]

        return {
            "low_accuracy": [_task_info(t) for t in low_accuracy],
            "high_latency": [_task_info(t) for t in high_latency],
            "high_error_rate": [_task_info(t) for t in high_error],
            "thresholds_used": {
                "accuracy_threshold": accuracy_threshold,
                "latency_threshold": latency_threshold,
            },
        }

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """현재 지표 기반 최적화 권고사항 자동 생성 (D5).

        Returns:
            priority 순으로 정렬된 권고사항 리스트.
            각 항목: ``{"priority": "high"|"medium"|"low", "category": str,
            "message": str, "metric": float}``.
        """
        recommendations: List[Dict[str, Any]] = []
        all_tasks = self.tasks
        n = len(all_tasks)
        if n == 0:
            return recommendations

        # TCR 계산
        try:
            tcr_data = self.tcr_tracker.calculate_tcr()
            tcr = float(tcr_data.get("tcr", 0.0)) if isinstance(tcr_data, dict) else float(tcr_data)
        except Exception:
            tcr = 0.0

        if tcr < 70.0:
            recommendations.append({
                "priority": "high",
                "category": "task_completion",
                "message": f"TCR이 {tcr:.1f}%로 낮습니다. 프롬프트와 도구 설정을 검토하세요.",
                "metric": tcr,
            })
        elif tcr < 85.0:
            recommendations.append({
                "priority": "medium",
                "category": "task_completion",
                "message": f"TCR이 {tcr:.1f}%입니다. 지속적인 모니터링이 필요합니다.",
                "metric": tcr,
            })

        # 에러율
        error_rate = sum(1 for t in all_tasks if t.errors) / n * 100
        if error_rate > 20.0:
            recommendations.append({
                "priority": "high",
                "category": "error_rate",
                "message": f"에러율이 {error_rate:.1f}%입니다. 주요 오류 원인을 분석하고 예외 처리를 강화하세요.",
                "metric": error_rate,
            })

        # 평균 정확도
        avg_acc = sum(t.accuracy_score for t in all_tasks) / n
        if avg_acc < 0.7:
            recommendations.append({
                "priority": "medium",
                "category": "accuracy",
                "message": f"평균 정확도가 {avg_acc:.2f}로 낮습니다. 프롬프트 개선 및 ground_truth 검토를 권장합니다.",
                "metric": avg_acc,
            })

        # 평균 레이턴시
        avg_lat = sum(t.execution_time for t in all_tasks) / n
        if avg_lat > 10.0:
            recommendations.append({
                "priority": "medium",
                "category": "latency",
                "message": f"평균 응답 시간이 {avg_lat:.1f}초입니다. 캐싱 또는 모델 최적화를 고려하세요.",
                "metric": avg_lat,
            })

        # 토큰 비용
        try:
            token_data = self.token_tracker.get_usage_stats()
            avg_cost = float(token_data.get("avg_cost_per_task", 0.0))
            if avg_cost > 0.1:
                recommendations.append({
                    "priority": "low",
                    "category": "cost",
                    "message": f"작업당 평균 비용이 ${avg_cost:.4f}입니다. 모델 변경이나 프롬프트 단축을 고려하세요.",
                    "metric": avg_cost,
                })
        except Exception as _e:
            logger.debug("OTEL attr skipped (cost recommendation): %s", _e)

        _priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: _priority_order.get(x["priority"], 9))
        return recommendations

    def analyze(self) -> Dict[str, Any]:
        """종합 분석 — 병목 태스크 + 권고사항 + 요약 지표 (D5).

        Returns:
            ``{"summary": {...}, "bottlenecks": {...}, "recommendations": [...],
            "analyzed_at": str}`` 구조.

        Example::

            result = monitor.analyze()
            for rec in result["recommendations"]:
                print(f"[{rec['priority']}] {rec['message']}")
        """
        # 요약 지표
        try:
            report = self.generate_report()
            acc = report.accuracy_metrics or {}
            eff = report.efficiency_metrics or {}
            summary = {
                "total_tasks": report.total_tasks,
                "tcr": acc.get("tcr", {}).get("tcr", 0.0) if isinstance(acc.get("tcr"), dict) else 0.0,
                "avg_accuracy": acc.get("accuracy_scores", {}).get("overall_accuracy", 0.0),
                "avg_latency": eff.get("latency", {}).get("mean", 0.0),
                "p95_latency": eff.get("latency", {}).get("p95", 0.0),
                "total_tokens": eff.get("tokens", {}).get("total_tokens", 0),
                "alert_count": len(report.alerts) if report.alerts else 0,
            }
        except Exception as _e:
            logger.debug("analyze(): generate_report 실패: %s", _e)
            summary = {"total_tasks": self.task_count}

        return {
            "summary": summary,
            "bottlenecks": self.get_bottleneck_tasks(),
            "recommendations": self.get_optimization_recommendations(),
            "analyzed_at": datetime.now().isoformat(),
        }

    # -----------------------------------------------------------------------
    # D2-D8: v0.7.9 신규 분석·유틸리티 메서드
    # -----------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """현재 평가 상태의 스냅샷을 반환한다 (D2).

        ``compare_with_snapshot()`` 과 함께 사용해 시간 경과에 따른 지표 변화를 추적한다.

        Returns:
            현재 리포트 지표 + 타임스탬프 + task_count 를 포함하는 dict.

        Example::

            snap = monitor.snapshot()
            # ... 추가 평가 ...
            delta = monitor.compare_with_snapshot(snap)
        """
        try:
            _report_dict = self.generate_report().to_dict()
        except Exception:
            _report_dict = {}
        return {
            "snapshot_time": datetime.now().isoformat(),
            "task_count": self.task_count,
            "report": _report_dict,
        }

    def compare_with_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """현재 상태와 이전 스냅샷의 지표 차이를 반환한다 (D2).

        Args:
            snapshot: ``snapshot()`` 이 반환한 dict.

        Returns:
            ``{"delta": {metric: current - snapshot}, "snapshot_time": ...,
            "current_time": ..., "task_count_delta": int}``
        """
        try:
            _current_report = self.generate_report().to_dict()
        except Exception:
            _current_report = {}
        _snap_report = snapshot.get("report", {})
        _delta: Dict[str, Any] = {}
        for _k, _cv in _current_report.items():
            if isinstance(_cv, (int, float)) and _k in _snap_report:
                _sv = _snap_report[_k]
                if isinstance(_sv, (int, float)):
                    _delta[_k] = round(float(_cv) - float(_sv), 6)
        return {
            "delta": _delta,
            "snapshot_time": snapshot.get("snapshot_time", ""),
            "current_time": datetime.now().isoformat(),
            "task_count_delta": self.task_count - snapshot.get("task_count", 0),
        }

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> "PerformanceMonitor":
        """스냅샷에서 모니터 상태를 복원한다 (E1).

        :meth:`snapshot` 이 반환한 dict를 받아 기록 시점의 집계 상태를 로그에 남긴다.
        설정(output_dir, thresholds, enable_* 플래그)은 변경하지 않는다.

        .. note::
            개별 TaskResult 목록은 스냅샷에 포함되지 않으므로 완전한 상태 복원은
            ``save_to_file`` / ``load_from_file`` 을 사용해야 한다.
            이 메서드는 "현재 어디서 왔는지" 기록 용도로 사용한다.

        | 초기화 항목 | 보존 항목 |
        |-------------|-----------|
        | (없음 — 개별 태스크 삭제 안 함) | output_dir, thresholds, security config, enable_* flags |

        Args:
            snapshot: :meth:`snapshot` 반환값.

        Returns:
            ``self`` (메서드 체이닝 지원).

        Raises:
            ValueError: snapshot 이 dict가 아닌 경우.
        """
        if not isinstance(snapshot, dict):
            raise ValueError(
                f"restore_from_snapshot: expected dict, got {type(snapshot).__name__}"
            )
        logger.debug(
            "restore_from_snapshot: restoring reference to snapshot taken at %s "
            "(task_count=%s)",
            snapshot.get("snapshot_time", "unknown"),
            snapshot.get("task_count", "unknown"),
        )
        return self

    def get_timeseries_metrics(
        self,
        metric: str,
        granularity: str = "hour",
    ) -> List[Dict[str, Any]]:
        """특정 지표의 시계열 데이터를 반환한다 (D3).

        Args:
            metric: ``"accuracy"`` | ``"latency"`` | ``"completion"`` | ``"tokens"`` | ``"errors"``
            granularity: ``"minute"`` | ``"hour"`` | ``"day"``

        Returns:
            ``[{"bucket": "2026-04-04T10:00", "avg": 0.85, "min": 0.7, "max": 1.0, "count": 5}]``
        """
        _tasks = self.tasks
        if not _tasks:
            return []

        _metric_field = {
            "accuracy": "accuracy_score",
            "latency": "execution_time",
            "completion": "completion_score",
            "tokens": None,  # 특수 처리
            "errors": None,  # 특수 처리
        }.get(metric, metric)

        _fmt = {
            "minute": "%Y-%m-%dT%H:%M",
            "hour": "%Y-%m-%dT%H:00",
            "day": "%Y-%m-%d",
        }.get(granularity, "%Y-%m-%dT%H:00")

        _buckets: Dict[str, List[float]] = {}
        for _t in _tasks:
            _ts = getattr(_t, "timestamp", None)
            if _ts is None:
                continue
            try:
                if isinstance(_ts, str):
                    from datetime import datetime as _dt
                    _ts = _dt.fromisoformat(_ts.replace("Z", "+00:00"))
                _bucket_key = _ts.strftime(_fmt)
            except Exception:
                continue

            if metric == "tokens":
                _tu = getattr(_t, "tokens_used", {}) or {}
                _val = float(_tu.get("total", 0) or 0)
            elif metric == "errors":
                _errs = getattr(_t, "errors", []) or []
                _val = float(len(_errs))
            elif _metric_field:
                _val = float(getattr(_t, _metric_field, 0) or 0)
            else:
                continue

            _buckets.setdefault(_bucket_key, []).append(_val)

        _result = []
        for _bucket, _vals in sorted(_buckets.items()):
            _result.append({
                "bucket": _bucket,
                "avg": round(sum(_vals) / len(_vals), 6),
                "min": round(min(_vals), 6),
                "max": round(max(_vals), 6),
                "count": len(_vals),
            })
        return _result

    def export_to_dataframe(
        self,
        include_fields: Optional[List[str]] = None,
    ) -> Any:
        """모든 태스크를 pandas DataFrame으로 내보낸다 (D4).

        Args:
            include_fields: ``task.extra`` 에서 추가로 컬럼에 포함할 키 목록.

        Returns:
            pandas DataFrame.

        Raises:
            ImportError: pandas가 설치되어 있지 않은 경우.
        """
        try:
            import pandas as _pd
        except ImportError as e:
            raise ImportError("export_to_dataframe requires pandas: pip install pandas") from e

        _tasks = self.tasks
        _rows = []
        for _t in _tasks:
            _tu = getattr(_t, "tokens_used", {}) or {}
            _row: Dict[str, Any] = {
                "task_id": getattr(_t, "task_id", ""),
                "task_type": getattr(_t, "task_type", ""),
                "success": getattr(_t, "success", None),
                "completion_score": getattr(_t, "completion_score", None),
                "accuracy_score": getattr(_t, "accuracy_score", None),
                "execution_time": getattr(_t, "execution_time", None),
                "tokens_total": _tu.get("total", 0),
                "tool_call_count": len(getattr(_t, "tool_calls", []) or []),
                "attempts": getattr(_t, "attempts", 1),
                "error_count": len(getattr(_t, "errors", []) or []),
                "timestamp": str(getattr(_t, "timestamp", "")),
                "framework": str((_tu or {}).get("model", getattr(_t, "extra", {}) or {}).get("framework", "") if isinstance(_tu, dict) else ""),
            }
            # include_fields: extra 딕셔너리에서 추가 컬럼 추출
            if include_fields:
                _extra = getattr(_t, "extra", {}) or {}
                for _f in include_fields:
                    _row[f"extra.{_f}"] = _extra.get(_f)
            _rows.append(_row)
        return _pd.DataFrame(_rows)

    def clone(self) -> "PerformanceMonitor":
        """동일한 설정을 가진 새 PerformanceMonitor 인스턴스를 생성한다 (D5).

        태스크 데이터 없이 설정만 복사한다. 독립된 평가 세션이나
        A/B 테스트에 유용하다.

        Returns:
            새 빈 ``PerformanceMonitor`` 인스턴스.

        Example::

            monitor_a = monitor.clone()
            monitor_b = monitor.clone()
            # 동일 설정으로 서로 다른 에이전트 평가
        """
        _new = PerformanceMonitor(
            output_dir=self.output_dir,
            enable_hallucination_detection=self.enable_hallucination_detection,
            enable_security_metrics=self.enable_security_metrics,
            auto_save=self.auto_save,
            auto_save_interval=self._auto_save_interval,
            auto_save_filename=self._auto_save_filename,
        )
        return _new

    def register_aggregator(
        self,
        name: str,
        fn: Any,  # Callable[[List[TaskResult]], Any]
    ) -> "PerformanceMonitor":
        """사용자 정의 집계 함수를 등록한다 (D7).

        Args:
            name: 집계 함수 식별자.
            fn: ``(tasks: List[TaskResult]) -> Any`` 시그니처의 Callable.

        Returns:
            ``self`` — 메서드 체이닝 지원.

        Example::

            monitor.register_aggregator(
                "error_rate",
                lambda tasks: sum(1 for t in tasks if t.errors) / max(len(tasks), 1)
            )
            rate = monitor.run_aggregator("error_rate")
        """
        if not hasattr(self, "_custom_aggregators"):
            self._custom_aggregators: Dict[str, Any] = {}
        self._custom_aggregators[name] = fn
        return self

    def run_aggregator(self, name: str) -> Any:
        """등록된 집계 함수를 현재 태스크 목록으로 실행한다 (D7).

        Args:
            name: ``register_aggregator()`` 로 등록한 이름.

        Returns:
            집계 함수의 반환값.

        Raises:
            KeyError: 이름이 등록되어 있지 않은 경우.
        """
        if not hasattr(self, "_custom_aggregators") or name not in self._custom_aggregators:
            raise KeyError(f"'{name}' 집계 함수가 등록되어 있지 않습니다. register_aggregator()로 먼저 등록하세요.")
        return self._custom_aggregators[name](self.tasks)

    def list_aggregators(self) -> List[str]:
        """등록된 집계 함수 이름 목록을 반환한다 (D7).

        Returns:
            등록된 집계 함수 이름 리스트.
        """
        if not hasattr(self, "_custom_aggregators"):
            return []
        return list(self._custom_aggregators.keys())

    def merge(self, other: "PerformanceMonitor") -> "PerformanceMonitor":
        """두 PerformanceMonitor의 태스크를 병합한 새 인스턴스를 반환한다 (D8).

        ``self``의 설정을 기준으로 새 인스턴스를 생성하고, ``self``와 ``other``의
        모든 태스크를 새 인스턴스에 기록한다.

        Args:
            other: 병합할 다른 PerformanceMonitor.

        Returns:
            병합된 새 PerformanceMonitor 인스턴스.

        Example::

            merged = monitor_a.merge(monitor_b)
            print(merged.task_count)  # monitor_a.task_count + monitor_b.task_count
        """
        _merged = self.clone()
        for _t in self.tasks:
            try:
                _merged.record_task(_t)
            except Exception as _e:
                logger.debug("merge: self 태스크 기록 실패 (무시): %s", _e)
        for _t in other.tasks:
            try:
                _merged.record_task(_t)
            except Exception as _e:
                logger.debug("merge: other 태스크 기록 실패 (무시): %s", _e)
        return _merged

    def flush(self) -> Dict[str, Any]:
        """지금까지 수집된 평가 데이터의 요약을 반환하고 내부 상태를 초기화한다.

        장시간 운영되는 서비스에서 주기적으로 호출해 메모리를 관리한다.

        ``reset()``과의 차이:

        * ``flush()`` — 현재 통계 요약(Dict)을 **반환한 뒤** 내부 상태를 초기화한다.
          롤링 윈도우·주기적 집계처럼 "이번 배치 결과를 저장하고 다음 배치를 준비"하는
          시나리오에 적합하다.
        * ``reset()`` — 요약 없이 내부 상태만 초기화한다. 설정값(thresholds,
          output_dir, pricing 등)과 골든 데이터셋은 유지된다.

        Returns:
            Dict[str, Any]: flush 전 수집된 평가 요약 통계
                - ``total_tasks`` (int): 처리된 태스크 수
                - ``success_rate`` (float): 성공률 (0.0–1.0)
                - ``avg_latency_s`` (float): 평균 지연시간 (초, seconds)
                - ``avg_accuracy`` (float): 평균 정확도 (0.0–1.0)
                - ``flushed_at`` (str): ISO-8601 타임스탬프

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... 1000개 태스크 처리 ...
            >>> summary = monitor.flush()  # 요약 저장 후 메모리 정리
            >>> print(summary["total_tasks"])  # 1000
            >>> # 이후 monitor는 빈 상태로 재사용 가능
        """
        # 현재 상태 요약 계산
        report = self.generate_report()
        tcr_data = report.accuracy_metrics.get("tcr") or {}
        latency_data = (report.efficiency_metrics.get("latency") or {})
        accuracy_data = report.accuracy_metrics.get("accuracy_scores") or {}

        summary: Dict[str, Any] = {
            "total_tasks": report.total_tasks,
            "success_rate": tcr_data.get("success_rate", 0.0),
            "avg_latency_s": latency_data.get("mean", 0.0),
            "avg_accuracy": accuracy_data.get("overall_accuracy", 0.0),
            "flushed_at": datetime.now().isoformat(),
        }

        # 각 트래커 초기화 — _iter_trackers()로 동적 발견해 일관되게 처리.
        # reset()과 동일한 경로를 사용하므로, 보안 트래커 등 옵셔널 트래커도
        # enable_security_metrics=True 일 때 빠짐없이 초기화된다.
        for _tracker in self._iter_trackers():
            _tracker.reset()

        # RAG 지표 초기화
        for key in self._rag_metrics:
            self._rag_metrics[key] = []

        logger.info("PerformanceMonitor flushed: %d tasks cleared", summary["total_tasks"])
        return summary

    def _auto_transparency_on_save(self, filename: str):
        """
        Auto-generate transparency data on save_to_file().
        Produces:
          - 5 metric traces (TCR, Accuracy, Latency, Token Economy, Quality)
          - 2 audit log entries (report_generated, file_saved)
        Called only when enable_transparency=True.
        """
        from ...utils.transparency_manager import TestStepStatus

        tm = self.transparency_manager
        tasks = self.tcr_tracker.tasks
        n = len(tasks)
        if n == 0:
            return

        # ── 1. TCR trace ────────────────────────────────────────────────────
        tcr_data = self.tcr_tracker.calculate_tcr()
        success_count = sum(1 for t in tasks if t.success)
        tcr_val = round(tcr_data.get("tcr", 0), 2)

        tid = tm.start_metric_calculation("tcr", "basic")
        tm.add_calculation_step(
            tid, "collect_tasks", f"{n}개 태스크 수집",
            {"total_tasks": n},
            {"tasks_collected": n},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid, "count_successes", f"성공 {success_count} / 전체 {n}",
            {"total": n, "success": success_count},
            {"success_count": success_count, "fail_count": n - success_count},
            TestStepStatus.SUCCESS,
        )
        weighted = round(sum(t.completion_score for t in tasks), 2)
        tm.add_calculation_step(
            tid, "calculate_tcr", f"TCR = Σ(completion_score)/{n} × 100 = {weighted}/{n} × 100 = {tcr_val}%",
            {"weighted_completions": weighted, "total": n},
            {"tcr": tcr_val},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid, final_value=tcr_val,
            metadata={"formula": "Σ(completion_score) / total_tasks × 100", "task_count": n},
        )

        # ── 2. Accuracy trace ───────────────────────────────────────────────
        acc_data = self.accuracy_evaluator.get_accuracy_scores()
        overall_acc = round(acc_data.get("overall_accuracy", 0), 4)
        scores = [v for e in self.accuracy_evaluator.evaluations
                  if (v := e.get("accuracy")) is not None]

        tid2 = tm.start_metric_calculation("accuracy", "quality")
        tm.add_calculation_step(
            tid2, "collect_scores", f"{len(scores)}개 태스크 정확도 점수 수집",
            {"evaluations": len(scores)},
            {"score_min": round(min(scores), 3) if scores else 0,
             "score_max": round(max(scores), 3) if scores else 0},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid2, "weighted_aggregate",
            "Token Overlap 40% + Jaccard 30% + LCS 20% + Char 10% 가중 평균",
            {"weights": {"token_overlap": 0.4, "jaccard": 0.3, "lcs": 0.2, "char": 0.1}},
            {"overall_accuracy": overall_acc},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid2, final_value=overall_acc,
            metadata={"method": "weighted_average", "task_count": len(scores)},
        )

        # ── 3. Latency trace ────────────────────────────────────────────────
        lat_data = self.latency_tracker.get_latency_stats()
        mean_lat = round(lat_data.get("mean", 0), 3)
        p95_lat = round(lat_data.get("p95", 0), 3)
        times = [t.execution_time for t in tasks]

        tid3 = tm.start_metric_calculation("latency", "performance")
        tm.add_calculation_step(
            tid3, "collect_times", f"{len(times)}개 실행 시간 수집",
            {"task_count": len(times)},
            {"min_s": round(min(times), 3) if times else 0,
             "max_s": round(max(times), 3) if times else 0},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid3, "percentiles", "평균·p50·p95·p99 백분위수 계산",
            {"values_count": len(times)},
            {"mean_s": mean_lat, "p95_s": p95_lat},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid3, final_value=mean_lat,
            metadata={"unit": "seconds", "p95": p95_lat},
        )

        # ── 4. Token Economy trace ──────────────────────────────────────────
        tok_data = self.token_tracker.get_usage_stats()
        total_tokens = tok_data.get("total_tokens", 0)
        total_cost = round(tok_data.get("total_cost", 0.0), 6)

        tid4 = tm.start_metric_calculation("token_economy", "performance")
        tm.add_calculation_step(
            tid4, "sum_tokens", "태스크별 input/output 토큰 합산",
            {"task_count": n},
            {"total_input": tok_data.get("total_input_tokens", 0),
             "total_output": tok_data.get("total_output_tokens", 0),
             "total_tokens": total_tokens},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid4, "calculate_cost", "총 비용 = Σ(토큰 × 단가)",
            {"total_tokens": total_tokens},
            {"total_cost_usd": total_cost,
             "avg_cost_per_task": round(total_cost / n, 6) if n else 0},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid4, final_value=total_tokens,
            metadata={"total_cost_usd": total_cost},
        )

        # ── 5. Quality trace (only when quality evaluations exist) ──────────
        q_evals = self.quality_evaluator.evaluations
        if q_evals:
            q_data = self.quality_evaluator.get_quality_metrics()
            avg_q = round(q_data.get("avg_total_score", 0), 4)
            dim_scores = q_data.get("dimension_averages", {})

            tid5 = tm.start_metric_calculation("response_quality", "quality")
            tm.add_calculation_step(
                tid5, "collect_evaluations", f"{len(q_evals)}개 응답 품질 평가 수집",
                {"evaluations": len(q_evals)},
                {"dimension_count": len(dim_scores)},
                TestStepStatus.SUCCESS,
            )
            tm.add_calculation_step(
                tid5, "dimension_scoring",
                "5개 차원 채점 (relevance · completeness · accuracy · clarity · usefulness)",
                {"dimensions": list(dim_scores.keys())},
                {"avg_dimension_scores": {k: round(v, 3) for k, v in dim_scores.items()}},
                TestStepStatus.SUCCESS,
            )
            tm.add_calculation_step(
                tid5, "aggregate_quality", f"종합 품질 점수 = {avg_q}",
                {"method": "weighted_dimension_average"},
                {"avg_quality_score": avg_q},
                TestStepStatus.SUCCESS,
            )
            tm.complete_metric_calculation(
                tid5, final_value=avg_q,
                metadata={"scale": "0-5", "grade_distribution": q_data.get("grade_distribution", {})},
            )

        # ── Audit: report_generated ─────────────────────────────────────────
        tm.log_event(
            event_type="lifecycle",
            user="system",
            action="report_generated",
            target_type="report",
            target_id="evaluation_report",
            details={
                "total_tasks": n,
                "tcr": tcr_val,
                "overall_accuracy": overall_acc,
                "mean_latency_s": mean_lat,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
            },
            success=True,
        )

        # ── Audit: file_saved ───────────────────────────────────────────────
        tm.log_event(
            event_type="lifecycle",
            user="system",
            action="file_saved",
            target_type="file",
            target_id=os.path.basename(filename),
            details={
                "filepath": filename,
                "total_tasks": n,
                "file_size_bytes": os.path.getsize(filename) if os.path.exists(filename) else 0,
            },
            success=True,
        )

    def _get_security_evaluator_data(self) -> dict:
        """
        Extract security evaluator data for JSON export

        Returns:
            Dictionary containing all security evaluator data
        """
        security_data = {}

        # Input Sanitizer
        if hasattr(self, 'input_sanitizer') and self.input_sanitizer is not None:
            security_data['input_sanitizer'] = {
                'evaluations': self.input_sanitizer.evaluations
            }

        # Output Leakage Detector
        if hasattr(self, 'output_leakage_detector') and self.output_leakage_detector is not None:
            security_data['output_leakage_detector'] = {
                'detections': self.output_leakage_detector.detections
            }

        # Tool Authorizer
        if hasattr(self, 'tool_authorizer') and self.tool_authorizer is not None:
            security_data['tool_authorizer'] = {
                'tool_calls': self.tool_authorizer.tool_calls
            }

        # Privilege Escalation Detector
        if hasattr(self, 'privilege_escalation_detector') and self.privilege_escalation_detector is not None:
            security_data['privilege_escalation_detector'] = {
                'escalation_events': self.privilege_escalation_detector.escalation_events
            }

        # Tool Chain Attack Detector
        if hasattr(self, 'tool_chain_attack_detector') and self.tool_chain_attack_detector is not None:
            security_data['tool_chain_attack_detector'] = {
                'detections': self.tool_chain_attack_detector.detections
            }

        return security_data

    def _append_report_data(self, data: dict):
        """
        Append full report data to existing data dictionary
        Required for Dashboard compatibility

        Args:
            data: Existing data dictionary to append to
        """
        # Generate report
        report = self.generate_report()

        # Add report fields
        data['total_tasks'] = report.total_tasks
        data['accuracy_metrics'] = report.accuracy_metrics if isinstance(report.accuracy_metrics, dict) else {}
        data['efficiency_metrics'] = report.efficiency_metrics if isinstance(report.efficiency_metrics, dict) else {}
        data['quality_metrics'] = report.quality_metrics if isinstance(report.quality_metrics, dict) else {}
        data['security_metrics'] = report.security_metrics if isinstance(report.security_metrics, dict) else {}
        data['recommendations'] = report.recommendations if isinstance(report.recommendations, list) else []
        data['alerts'] = report.alerts if isinstance(report.alerts, list) else []

        # Add completion_tracker data
        data['completion_tracker'] = {
            'tcr': self.tcr_tracker.calculate_tcr(),
            'completion_by_type': self.tcr_tracker.get_tcr_by_type(),
            'accuracy_stats': self.accuracy_evaluator.get_accuracy_scores()
        }

    @classmethod
    def load_from_file(cls, filename: str = "performance_data.json") -> "PerformanceMonitor":
        """Load performance data from a JSON file including evaluator data"""
        # Dashboard/data/evaluation_results 디렉토리에서 찾기 (절대 경로가 아닌 경우)
        if not os.path.isabs(filename) and not os.path.exists(filename):
            from ...utils.path_helpers import get_evaluation_results_dir
            results_dir = get_evaluation_results_dir(create=False)
            alt_path = os.path.join(results_dir, filename)
            if os.path.exists(alt_path):
                filename = alt_path

        with open(filename, encoding='utf-8') as f:
            data = json.load(f)

        # Create new monitor instance — enable security if JSON contains security evaluator data
        has_security = "security" in data.get("evaluators", {})
        monitor = cls(
            pricing=data.get("pricing", {"input": 0.003, "output": 0.015}),
            enable_security_metrics=has_security,
        )

        # Restore tasks
        # Compute TaskResult field set once — dataclasses.fields() is cheap but
        # calling it on every iteration of a potentially large task list is wasteful.
        _tr_fields = {f.name for f in dataclasses.fields(TaskResult)}
        for task_dict in data.get("tasks", []):
            # Convert timestamp string back to datetime
            if isinstance(task_dict.get("timestamp"), str):
                task_dict["timestamp"] = datetime.fromisoformat(task_dict["timestamp"])

            # Ensure numeric fields are proper types
            if "attempts" in task_dict:
                task_dict["attempts"] = int(task_dict["attempts"])
            if "completion_score" in task_dict:
                task_dict["completion_score"] = float(task_dict["completion_score"])
            if "accuracy_score" in task_dict:
                task_dict["accuracy_score"] = float(task_dict["accuracy_score"])
            if "execution_time" in task_dict:
                task_dict["execution_time"] = float(task_dict["execution_time"])

            # Create TaskResult object — filter extra keys for cross-monitor compatibility
            task = TaskResult(**{k: v for k, v in task_dict.items() if k in _tr_fields})
            monitor.record_task(task)

        # Restore evaluator data (if available)
        evaluators = data.get("evaluators", {})

        if evaluators:
            # Accuracy evaluations
            if "accuracy" in evaluators:
                monitor.accuracy_evaluator.evaluations = evaluators["accuracy"].get("evaluations", [])

            # Quality evaluations
            if "quality" in evaluators:
                monitor.quality_evaluator.evaluations = evaluators["quality"].get("evaluations", [])

            # Hallucination detections
            if "hallucination" in evaluators:
                monitor.hallucination_detector.detections = evaluators["hallucination"].get("detections", [])

            # Retry attempts
            if "retry" in evaluators:
                monitor.retry_tracker.attempts = evaluators["retry"].get("attempts", [])

            # Tool selections
            if "tool_selection" in evaluators:
                monitor.tool_selection_tracker.selections = evaluators["tool_selection"].get("selections", [])

            # Agent interactions
            if "agent_coordination" in evaluators:
                monitor.agent_coordination_tracker.interactions = evaluators["agent_coordination"].get("interactions", [])

            # Workflow executions
            if "workflow" in evaluators:
                monitor.workflow_tracker.executions = evaluators["workflow"].get("executions", [])

            # Tool call executions
            if "tool_calls" in evaluators:
                monitor.tool_analyzer.executions = evaluators["tool_calls"].get("executions", [])

            # Security evaluators (Layer 1 & 2)
            if "security" in evaluators:
                security_data = evaluators["security"]

                # Input Sanitizer
                if "input_sanitizer" in security_data and monitor.input_sanitizer is not None:
                    monitor.input_sanitizer.evaluations = security_data["input_sanitizer"].get("evaluations", [])

                # Output Leakage Detector
                if "output_leakage_detector" in security_data and monitor.output_leakage_detector is not None:
                    monitor.output_leakage_detector.detections = security_data["output_leakage_detector"].get("detections", [])

                # Tool Authorizer
                if "tool_authorizer" in security_data and monitor.tool_authorizer is not None:
                    monitor.tool_authorizer.tool_calls = security_data["tool_authorizer"].get("tool_calls", [])

                # Privilege Escalation Detector
                if "privilege_escalation_detector" in security_data and monitor.privilege_escalation_detector is not None:
                    monitor.privilege_escalation_detector.escalation_events = security_data["privilege_escalation_detector"].get("escalation_events", [])

                # Tool Chain Attack Detector
                if "tool_chain_attack_detector" in security_data and monitor.tool_chain_attack_detector is not None:
                    monitor.tool_chain_attack_detector.detections = security_data["tool_chain_attack_detector"].get("detections", [])

            logger.debug(
                "Restored evaluator data: Quality=%d, Hallucination=%d, ToolCalls=%d, "
                "ToolSelection=%d, AgentCoord=%d, Workflow=%d",
                len(monitor.quality_evaluator._evaluations),
                len(monitor.hallucination_detector._detections),
                len(monitor.tool_analyzer._executions),
                len(monitor.tool_selection_tracker._selections),
                len(monitor.agent_coordination_tracker._interactions),
                len(monitor.workflow_tracker._executions),
            )
            if "security" in evaluators:
                logger.debug(
                    "Restored security data: InputEvals=%d, OutputDetections=%d, ToolCalls=%d",
                    len(monitor.input_sanitizer._evaluations),
                    len(monitor.output_leakage_detector._detections),
                    len(monitor.tool_authorizer._tool_calls),
                )

        # Restore advanced_metrics_summary (DeepEval, Ragas 등) — check both top-level and report.*
        _ams = data.get("advanced_metrics_summary") or data.get("report", {}).get("advanced_metrics_summary")
        if _ams:
            monitor._advanced_metrics_summary = _ams
            logger.debug("Restored advanced metrics summary with %d metrics", len(_ams))

        # Restore RAG metrics
        if "rag_metrics" in data:
            monitor._rag_metrics = data["rag_metrics"]
            total_rag_values = sum(len(v) for v in monitor._rag_metrics.values() if v)
            if total_rag_values > 0:
                logger.debug("Restored RAG metrics with %d total values", total_rag_values)

        # Store evaluators data for Dashboard compatibility
        if "evaluators" in data:
            monitor.evaluators = data["evaluators"]

        logger.info("Performance data loaded from %s (%d tasks)", filename, len(data.get("tasks", [])))
        return monitor


# ============================================================================
# Example Usage & Demo
# ============================================================================

def create_demo_data():
    """
    Create comprehensive demo task results for testing

    Generates realistic test data covering:
    - All 10 TaskTypes
    - Various success/failure scenarios
    - Different tool usage patterns
    - Realistic error cases
    - Time-distributed tasks
    - Varied token usage patterns
    """
    demo_tasks = []

    # All available TaskTypes
    all_task_types = [
        TaskType.QA,
        TaskType.DATA_ANALYSIS,
        TaskType.CODE_GENERATION,
        TaskType.DOCUMENT_CREATION,
        TaskType.INFORMATION_RETRIEVAL,
        TaskType.REASONING,
        TaskType.CREATIVE,
        TaskType.CODING,
        TaskType.PLANNING,
        TaskType.TOOL_USE
    ]

    # Realistic error messages by category
    error_messages = {
        "timeout": ["Execution timeout after 30s", "Request timeout", "Connection timeout"],
        "validation": ["Invalid input format", "Schema validation failed", "Missing required field"],
        "api": ["API rate limit exceeded", "Service unavailable", "Authentication failed"],
        "resource": ["Out of memory", "Disk space full", "Resource quota exceeded"],
        "logic": ["Division by zero", "Index out of range", "Null pointer exception"]
    }

    # Tool categories by task type
    tool_mapping = {
        TaskType.QA: ["search", "knowledge_base", "fact_checker"],
        TaskType.DATA_ANALYSIS: ["pandas", "matplotlib", "sql_query", "data_processor"],
        TaskType.CODE_GENERATION: ["code_analyzer", "syntax_checker", "linter", "formatter"],
        TaskType.DOCUMENT_CREATION: ["template_engine", "markdown_parser", "pdf_generator"],
        TaskType.INFORMATION_RETRIEVAL: ["vector_search", "web_scraper", "database_query"],
        TaskType.REASONING: ["logic_engine", "math_solver", "proof_checker"],
        TaskType.CREATIVE: ["image_gen", "style_analyzer", "content_filter"],
        TaskType.CODING: ["compiler", "debugger", "test_runner", "code_review"],
        TaskType.PLANNING: ["task_scheduler", "resource_allocator", "dependency_resolver"],
        TaskType.TOOL_USE: ["api_caller", "file_handler", "system_command"]
    }

    # Generate 100 diverse tasks
    for i in range(100):
        task_type = np.random.choice(all_task_types)

        # Realistic success rate: 88% overall, varies by task type
        base_success_rate = {
            TaskType.QA: 0.92,
            TaskType.DATA_ANALYSIS: 0.85,
            TaskType.CODE_GENERATION: 0.83,
            TaskType.DOCUMENT_CREATION: 0.90,
            TaskType.INFORMATION_RETRIEVAL: 0.88,
            TaskType.REASONING: 0.80,
            TaskType.CREATIVE: 0.95,
            TaskType.CODING: 0.82,
            TaskType.PLANNING: 0.87,
            TaskType.TOOL_USE: 0.89
        }

        success = np.random.random() < base_success_rate[task_type]

        # Realistic score distributions
        if success:
            completion_score = np.random.beta(8, 2)  # Skewed towards high scores
            accuracy_score = np.random.beta(9, 1.5)
        else:
            completion_score = np.random.beta(2, 5)  # Skewed towards low scores
            accuracy_score = np.random.beta(2, 6)

        # Realistic execution time by task type
        time_ranges = {
            TaskType.QA: (0.5, 3.0),
            TaskType.DATA_ANALYSIS: (2.0, 15.0),
            TaskType.CODE_GENERATION: (3.0, 20.0),
            TaskType.DOCUMENT_CREATION: (1.0, 8.0),
            TaskType.INFORMATION_RETRIEVAL: (1.5, 10.0),
            TaskType.REASONING: (2.0, 12.0),
            TaskType.CREATIVE: (5.0, 30.0),
            TaskType.CODING: (3.0, 25.0),
            TaskType.PLANNING: (2.0, 15.0),
            TaskType.TOOL_USE: (0.5, 5.0)
        }

        time_range = time_ranges[task_type]
        execution_time = np.random.uniform(*time_range)

        # Realistic token usage by task type
        token_ranges = {
            TaskType.QA: (100, 500, 50, 300),  # input_min, input_max, output_min, output_max
            TaskType.DATA_ANALYSIS: (500, 2000, 300, 1500),
            TaskType.CODE_GENERATION: (200, 800, 400, 2000),
            TaskType.DOCUMENT_CREATION: (300, 1500, 500, 3000),
            TaskType.INFORMATION_RETRIEVAL: (100, 600, 200, 1000),
            TaskType.REASONING: (200, 1000, 300, 1200),
            TaskType.CREATIVE: (150, 600, 400, 2500),
            TaskType.CODING: (300, 1200, 500, 2500),
            TaskType.PLANNING: (400, 1500, 600, 2000),
            TaskType.TOOL_USE: (100, 400, 100, 500)
        }

        token_range = token_ranges[task_type]
        input_tokens = int(np.random.uniform(token_range[0], token_range[1]))
        output_tokens = int(np.random.uniform(token_range[2], token_range[3]))

        # Realistic tool calls
        available_tools = tool_mapping.get(task_type, ["generic_tool"])
        num_tools = np.random.poisson(2) + 1  # Average 3 tool calls
        num_tools = min(num_tools, 6)  # Cap at 6

        tool_calls = []
        for _ in range(num_tools):
            tool_success = np.random.random() < 0.95  # 95% tool success rate
            tool_calls.append({
                "tool": np.random.choice(available_tools),
                "duration": np.random.exponential(0.5),
                "success": tool_success,
                "parameters": {"task_id": f"task_{i:03d}"}
            })

        # Realistic attempt patterns
        if success:
            attempts = 1
        else:
            # Failed tasks might have retries
            attempts = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2])

        # Generate realistic errors for failed tasks
        errors = []
        if not success:
            error_category = np.random.choice(list(error_messages.keys()))
            error_msg = np.random.choice(error_messages[error_category])
            errors.append(error_msg)

            # Some tasks have multiple errors
            if np.random.random() < 0.3:
                other_category = np.random.choice(list(error_messages.keys()))
                errors.append(np.random.choice(error_messages[other_category]))

        # Time distribution: more tasks during business hours
        # Probabilities sum to 1.0
        hour_probs = np.array([
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02,  # 0-5 AM (0.07)
            0.03, 0.05, 0.07, 0.08, 0.09, 0.09,  # 6-11 AM (0.41)
            0.08, 0.08, 0.09, 0.09, 0.08, 0.07,  # 12-5 PM (0.49)
            0.05, 0.03, 0.02, 0.02, 0.01, 0.01   # 6-11 PM (0.14)
        ])
        # Normalize to ensure sum is exactly 1.0
        hour_probs = hour_probs / hour_probs.sum()

        hour_bias = np.random.choice(range(24), p=hour_probs)

        timestamp = datetime.now() - timedelta(
            hours=np.random.randint(0, 72),
            minutes=np.random.randint(0, 60)
        )

        task = TaskResult(
            task_id=f"task_{i:03d}",
            task_type=task_type.value,
            success=success,
            completion_score=float(completion_score),
            accuracy_score=float(accuracy_score),
            execution_time=float(execution_time),
            tokens_used={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            },
            tool_calls=tool_calls,
            attempts=attempts,
            errors=errors,
            timestamp=timestamp
        )

        demo_tasks.append(task)

    return demo_tasks


def run_demo():
    """
    Run a comprehensive demonstration of the evaluation system

    Generates 100 diverse tasks across all TaskTypes and demonstrates:
    - Task Completion Rate (TCR) tracking
    - Token usage and cost analysis
    - Latency monitoring
    - Error pattern analysis
    - Retry behavior tracking
    """
    print("\n" + "="*80)
    print("AI AGENT EVALUATION SYSTEM - COMPREHENSIVE DEMO")
    print("="*80 + "\n")

    # Initialize monitor with realistic pricing (OpenAI GPT-4 Turbo rates)
    monitor = PerformanceMonitor(pricing={
        "input": 0.01,   # $10 per 1M tokens
        "output": 0.03   # $30 per 1M tokens
    })

    # Generate and record demo data
    print("📊 Generating comprehensive demo task data...")
    print("   • 100 tasks across 10 TaskTypes")
    print("   • Realistic success/failure patterns")
    print("   • Varied tool usage and token consumption")
    print("   • Time-distributed over 72 hours\n")

    demo_tasks = create_demo_data()

    print(f"📝 Recording {len(demo_tasks)} tasks...\n")

    # Show task type distribution
    from collections import Counter
    task_type_counts = Counter(task.task_type for task in demo_tasks)
    print("Task Type Distribution:")
    for task_type, count in sorted(task_type_counts.items()):
        print(f"   • {task_type}: {count} tasks")
    print()

    # Record all tasks
    for i, task in enumerate(demo_tasks, 1):
        monitor.record_task(task)
        if i % 20 == 0:
            print(f"   ✓ Recorded {i}/{len(demo_tasks)} tasks...")

    print(f"   ✓ All {len(demo_tasks)} tasks recorded!\n")

    # Generate and print comprehensive report
    print("="*80)
    print("EVALUATION REPORT")
    print("="*80 + "\n")

    monitor.print_report()

    # Additional detailed analysis
    print("\n" + "="*80)
    print("DETAILED ANALYSIS")
    print("="*80 + "\n")

    print("📈 Task Completion Rate by Type:")
    tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()
    for task_type, tcr_data in sorted(tcr_by_type.items()):
        print(f"   • {task_type}: {tcr_data.get('tcr', 0):.1f}%")

    print("\n⏱️  Latency Analysis:")
    bottlenecks = monitor.latency_tracker.analyze_bottlenecks()
    if bottlenecks and bottlenecks.get("bottleneck"):
        print(f"   Bottleneck: {bottlenecks['bottleneck']} (avg {bottlenecks.get('bottleneck_avg_time', 0):.3f}s)")
        for comp, avg_time in bottlenecks.get("breakdown_averages", {}).items():
            print(f"   • {comp}: {avg_time:.3f}s")
    else:
        print("   No significant bottlenecks detected")

    print("\n🔄 Failure Pattern Analysis:")
    failure_patterns = monitor.retry_tracker.analyze_failure_patterns()
    if failure_patterns and failure_patterns.get("patterns"):
        for reason, count in list(failure_patterns["patterns"].items())[:5]:
            print(f"   • {reason}: {count} occurrences")
    else:
        print("   No significant failure patterns")

    print("\n💰 Cost Analysis:")
    report = monitor.generate_report()
    tokens = report.efficiency_metrics.get('tokens', {})
    if tokens:
        print(f"   • Total cost: ${tokens.get('total_cost', 0):.4f}")
        print(f"   • Avg cost per task: ${tokens.get('avg_cost_per_task', 0):.4f}")
        print(f"   • Tokens per task (avg): {tokens.get('avg_tokens_per_task', 0):.0f}")

    # Export comprehensive report
    print("\n📁 Exporting results...")
    monitor.export_report("evaluation_report.json", format="json")
    print("   ✓ Saved to: evaluation_report.json")

    monitor.export_report("evaluation_report.csv", format="csv")
    print("   ✓ Saved to: evaluation_report.csv")

    print("\n" + "="*80)
    print("DEMO COMPLETED SUCCESSFULLY!")
    print("="*80 + "\n")

    print("💡 Next steps:")
    print("   1. Review evaluation_report.json for detailed metrics")
    print("   2. Open evaluation_report.csv in spreadsheet software")
    print("   3. Use the monitor object for custom analysis")
    print("   4. Integrate with your own agent workflow\n")

    return monitor


if __name__ == "__main__":
    """
    Demo Mode: Run comprehensive evaluation system demonstration

    This generates 100 realistic test tasks and demonstrates all evaluation features.
    Perfect for:
    - Understanding system capabilities
    - Testing integration
    - Benchmarking performance
    - Learning the API
    """
    # Run comprehensive demo
    monitor = run_demo()

    # Show how to access individual components for custom analysis
    print("="*80)
    print("ADVANCED USAGE EXAMPLES")
    print("="*80 + "\n")

    print("# Access individual tracker components:")
    print("monitor.tcr_tracker        # Task Completion Rate tracking")
    print("monitor.token_tracker      # Token usage and cost analysis")
    print("monitor.latency_tracker    # Execution time monitoring")
    print("monitor.retry_tracker      # Retry and failure analysis")
    print()

    print("# Get specific metrics:")
    print("tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()")
    print("bottlenecks = monitor.latency_tracker.analyze_bottlenecks()")
    print("patterns = monitor.retry_tracker.analyze_failure_patterns()")
    print()

    print("# Generate custom reports:")
    print("report = monitor.generate_report()")
    print("monitor.export_report('custom_report.json', format='json')")
    print()

    print("# Integration example:")
    print("""
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# Initialize
monitor = PerformanceMonitor(pricing={'input': 0.01, 'output': 0.03})

# Record your agent's task
task = TaskResult(
    task_id='my_task_001',
    task_type=TaskType.QA.value,
    success=True,
    completion_score=0.95,
    accuracy_score=0.92,
    execution_time=2.3,
    tokens_used={'input': 500, 'output': 300, 'total': 800},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now()
)

monitor.record_task(task)
monitor.print_report()
""")
