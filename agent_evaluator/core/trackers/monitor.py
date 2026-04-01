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
from .feedback import ImplicitFeedbackTracker

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


class PerformanceMonitor:
    """Main performance monitoring and reporting system"""

    def __init__(
        self,
        pricing: Dict[str, float] = None,
        model_name: str = "",
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
        # Anomaly Detection (Phase 3-B)
        enable_anomaly_detection: bool = False,
        anomaly_baseline_window: int = 100,
        anomaly_detection_window: int = 20,
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
            enable_anomaly_detection: Enable automatic anomaly detection at save_to_file() time.
                When True, AnomalyDetector.scan() is called and results are stored under
                ``anomaly_data`` in the JSON output, making the dashboard 이상 감지 tab
                show real data. Requires no external dependencies.
            anomaly_baseline_window: Number of tasks used as the baseline for anomaly detection.
            anomaly_detection_window: Number of recent tasks used for current-state comparison.
        """
        if pricing is None:
            pricing = {"input": 0.003, "output": 0.015}  # Default: Claude Sonnet 4.5

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
        self.accuracy_evaluator = AccuracyEvaluator()
        self.hallucination_detector = HallucinationDetector()
        self.quality_evaluator = ResponseQualityEvaluator()
        self.latency_tracker = LatencyTracker()
        self.token_tracker = TokenEconomyTracker(pricing)
        self.retry_tracker = RetryCorrectionTracker()

        # Layer 1: Security trackers (optional)
        self.input_sanitizer = None
        self.output_leakage_detector = None
        self.tool_authorizer = None

        if enable_security_metrics:
            self.input_sanitizer = InputSanitizationTracker()
            self.output_leakage_detector = OutputLeakageDetector()
            self.tool_authorizer = ToolAuthorizationTracker(
                allowed_tools=self.security_config.get('allowed_tools'),
                restricted_tools=self.security_config.get('restricted_tools')
            )
            logger.info("Security metrics (Layer 1) 활성화됨")

        # Layer 2: Agentic AI trackers
        self.tool_analyzer = ToolCallAnalyzer()  # Tool call efficiency
        self.tool_selection_tracker = ToolSelectionTracker()  # Tool selection accuracy
        self.agent_coordination_tracker = AgentCoordinationTracker()
        self.workflow_tracker = WorkflowExecutionTracker()

        # Layer 2: Agentic Security trackers (optional)
        self.privilege_escalation_detector = None
        self.tool_chain_attack_detector = None

        if enable_security_metrics:
            self.privilege_escalation_detector = PrivilegeEscalationDetector()
            self.tool_chain_attack_detector = ToolChainAttackDetector()
            logger.info("Security metrics (Layer 2) 활성화됨")

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

        # Phase 2-C: 암묵적 피드백 트래커
        self.feedback_tracker = ImplicitFeedbackTracker()

        # Phase 2-A: StreamingEvaluator 스냅샷 (외부에서 set → save_to_file에 자동 포함)
        self._streaming_snapshot: Optional[Dict[str, Any]] = None

        # Thread safety: golden_datasets/conversation_sessions 동시 접근 보호
        self._lock = threading.Lock()

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
    def rag_metrics(self) -> Dict[str, List]:
        """RAG 지표 딕셔너리의 얕은 복사본.

        각 키의 리스트도 복사되므로 반환값을 변경해도 내부 상태에
        영향을 주지 않습니다.  RAG 지표를 추가하려면 반드시
        :meth:`record_rag_metrics` 를 사용하세요.
        """
        return {k: list(v) for k, v in self._rag_metrics.items()}

    def conversation(self, session_id: str) -> "ConversationSession":
        """멀티턴 대화 평가 세션 시작.

        Usage::

            with monitor.conversation("session_001") as conv:
                conv.turn(user="질문", agent="응답")
            # 세션 종료 시 자동으로 지표 계산 및 monitor.conversation_sessions에 기록

        Args:
            session_id: 세션 고유 ID.

        Returns:
            ConversationSession 인스턴스.
        """
        return ConversationSession(session_id=session_id, monitor=self)

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
            각 메트릭 이름을 키로 하는 비교 결과 dict. 각 항목은 다음 키를 포함한다:

            - ``name`` (str): 메트릭 표시 이름 (예: "작업 완료율 (TCR)")
            - ``value`` (float): 현재 측정값
            - ``threshold`` (float): 목표 임계값
            - ``status`` (str): ``"pass"`` / ``"fail"`` / ``"pending"``.
              ``"pending"``은 RAG 지표(faithfulness 등)에서 아직 측정값이 없을 때 반환된다.
            - ``direction`` (str): ``"higher"`` (높을수록 좋음) 또는 ``"lower"`` (낮을수록 좋음)
            - ``unit`` (str): 표시 단위 (예: ``"%"``, ``"s"``, ``"$"``)
            - ``layer`` (str, 선택): Layer 2 에이전틱 지표에만 존재. 항상 ``"Layer 2"``.

            임계값이 설정되지 않은 경우 빈 dict ``{}`` 반환.

            Note:
                ``quality`` 임계값은 0-10 척도로 설정한다.
                내부적으로 ResponseQualityEvaluator의 0-5 점수에 ``_QUALITY_SCORE_TO_10_SCALE``
                (= 2.0)를 곱해 변환한다.

        Example:
            >>> monitor.thresholds = {"tcr": 80.0, "hallucination": 10.0}
            >>> results = monitor.compare_with_thresholds()
            >>> results["tcr"]["status"]   # "pass" 또는 "fail"
            >>> results["tcr"]["value"]    # 실제 TCR 값 (%)
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

    def reset(self) -> None:
        """Clear all accumulated data across every tracker (thread-safe).

        Use this when reusing a ``PerformanceMonitor`` instance across
        multiple evaluation sessions (e.g., in a CI loop) to prevent
        data from one session leaking into the next.

        All mutations are performed under the monitor lock so no concurrent
        ``record_task()`` call can interleave partial state.
        """
        with self._lock:
            for tracker in self._iter_trackers():
                tracker.reset()
            self.conversation_sessions.clear()
            self._golden_datasets.clear()
            for key in self._rag_metrics:
                self._rag_metrics[key].clear()
            self.feedback_tracker.reset()

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

        with self._lock:  # guard all tracker mutations for thread safety
            # Task completion
            self.tcr_tracker.add_task(task_result)
            
            # Accuracy — store via record_score() to keep _cached_avg consistent.
            # TaskResult validates accuracy_score ∈ [0.0, 1.0] in __post_init__,
            # so no further normalisation is needed here.
            self.accuracy_evaluator.record_score(
                task_id=task_result.task_id,
                task_type=task_result.task_type,
                accuracy=task_result.accuracy_score,
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
    
            # Layer1: Hallucination Detection (opt-in, rule-based, free)
            _eff_response_hall = response if response is not None else task_result.response
            _eff_request_hall = request or task_result.question
            if self.enable_hallucination_detection and context and _eff_response_hall:
                try:
                    # Convert ground_truth to string if needed
                    ground_truth_str = None
                    if ground_truth is not None:
                        if isinstance(ground_truth, str):
                            ground_truth_str = ground_truth
                        else:
                            ground_truth_str = str(ground_truth)
    
                    self.hallucination_detector.detect_hallucination(
                        task_id=task_result.task_id,
                        response=_eff_response_hall,
                        context=context,
                        ground_truth=ground_truth_str,
                        request=_eff_request_hall
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

        # OTEL 스팬 발행 (opt-in, no-op if not configured)
        self._emit_otel_span(task_result)

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
            input_val = getattr(result, "question", None) or result.task_id
            output_val = getattr(result, "response", None) or str(result.completion_score)
            attributes = {
                # Phoenix UI: kind / input / output 컬럼
                "openinference.span.kind": "CHAIN",
                "input.value": str(input_val),
                "output.value": str(output_val),
                # Agent Evaluator 고유 지표
                "ae.task_id": result.task_id,
                "ae.task_type": str(result.task_type),
                "ae.success": result.success,
                "ae.completion_score": float(result.completion_score),
                "ae.accuracy_score": float(result.accuracy_score),
                "ae.execution_time": float(result.execution_time),
                "ae.tokens_used": result.tokens_used.get("total", 0)
                if isinstance(result.tokens_used, dict)
                else int(result.tokens_used or 0),
                "ae.tool_calls_count": len(result.tool_calls) if result.tool_calls else 0,
                "ae.attempts": result.attempts,
                "ae.framework": getattr(result, "framework", "native"),
            }
            with provider.span("ae.task", attributes):
                pass  # 스팬 기록만, 평가 로직은 이미 완료
        except Exception as _otel_exc:
            logger.debug("_emit_otel_span: 스팬 발행 실패: %s", _otel_exc)

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
        return {
            "tool_efficiency": self.tool_analyzer.get_efficiency_stats(),
            "retries": self.retry_tracker.get_retry_metrics(),
        }

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

        report = EvaluationReport(
            period="current_session",
            total_tasks=len(self.tcr_tracker.tasks),
            accuracy_metrics=accuracy_metrics,
            efficiency_metrics=efficiency_metrics,
            quality_metrics=quality_metrics if quality_metrics else {},
            security_metrics=security_metrics,
            alerts=self._generate_alerts(),
            recommendations=self._generate_recommendations(),
            timestamp=datetime.now()
        )

        return report
    
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

        pricing_data: Dict[str, Any] = dict(self.token_tracker.pricing)
        if self.model_name:
            pricing_data["model"] = self.model_name

        data = {
            "tasks": [asdict(task) for task in self.tcr_tracker.tasks],
            "pricing": pricing_data,
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
            # Phase 2-C: 암묵적 피드백
            "feedback": {
                **self.feedback_tracker.get_stats(),
                "records": self.feedback_tracker.feedbacks,
            },
        }

        # Phase 2-A: StreamingEvaluator 슬라이딩 윈도우 스냅샷 (opt-in)
        if self._streaming_snapshot:
            data["streaming_data"] = self._streaming_snapshot

        # Phase 3-C: LLM Judge 비용 정보
        if self.llm_judge is not None:
            judge_summary = self.llm_judge.get_summary()
            judge_cost = judge_summary.get("total_cost_usd", 0.0)
            budget = self.llm_judge.budget_per_day
            # by_provider: llm_judge는 단일 모델을 사용하므로 해당 모델명으로 집계
            _judge_model = getattr(self.llm_judge, "model", "")
            _by_provider = {_judge_model: round(judge_cost, 6)} if judge_cost > 0 and _judge_model else {}
            data["evaluation_cost"] = {
                "total_usd": judge_cost,
                "llm_judge_usd": judge_cost,
                "call_count": judge_summary.get("count", 0),
                "model": _judge_model,
                "sample_rate_current": self.llm_judge.sample_rate,
                "budget_per_day": budget,
                "budget_remaining_usd": (
                    round(max(0.0, budget - judge_cost), 6)
                    if budget is not None else None
                ),
                "projected_daily_usd": judge_cost,
                "by_provider": _by_provider,
            }

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

        # Atomic write: write to a temp file in the same directory, then rename.
        # Prevents partial-write corruption if the process is killed mid-write.
        _dir = os.path.dirname(os.path.abspath(filename))
        _fd, _tmp_path = tempfile.mkstemp(dir=_dir, suffix=".tmp")
        try:
            with os.fdopen(_fd, 'w', encoding='utf-8') as _f:
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

        return filename

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
        scores = [e.get("accuracy", 0) for e in self.accuracy_evaluator.evaluations]

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
