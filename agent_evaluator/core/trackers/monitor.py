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
import os
import re
import statistics
import warnings
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from .base import TaskResult, EvaluationReport, TaskType, _TaskContext
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

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Main performance monitoring and reporting system"""

    def __init__(
        self,
        pricing: Dict[str, float] = None,
        model_name: str = "",
        enable_transparency: bool = False,
        enable_hallucination_detection: bool = True,
        enable_security_metrics: bool = False,
        security_config: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None,
        # LLM Judge (Phase 1-A)
        enable_llm_judge: bool = False,
        judge_model: Optional[str] = None,
        judge_sample_rate: float = 0.1,
        judge_budget_per_day: Optional[float] = None,
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
                - True (default): Automatic rule-based hallucination detection (no external deps)
                - False: Disable hallucination detection for maximum performance
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
        self.rag_metrics = {
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
            except Exception as e:
                warnings.warn(f"LLM Judge 초기화 실패: {e}", RuntimeWarning, stacklevel=2)
                self.enable_llm_judge = False

        # 임계값 설정 (DataEditorManager에서 로드 가능)
        self.thresholds = None
        self.golden_dataset_path = None
        self.golden_datasets = []

        # Phase 1-C: 멀티턴 대화 세션 목록
        self.conversation_sessions: List[Any] = []

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
        from .conversation import ConversationSession
        return ConversationSession(session_id=session_id, monitor=self)

    def load_golden_dataset(self, dataset_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Golden Dataset 로드

        Args:
            dataset_path: Golden Dataset 파일 경로 (None이면 config에서 로드)

        Returns:
            List[Dict]: Golden Dataset 항목 리스트
        """
        import json
        import os

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
            logger.warning("Golden Dataset 파일을 찾을 수 없습니다: %s", dataset_path)
            return []

        try:
            with open(dataset_path, encoding='utf-8') as f:
                data = json.load(f)

            # Handle both formats: direct array or object with qa_pairs key
            if isinstance(data, list):
                self.golden_datasets = data
            elif isinstance(data, dict) and 'qa_pairs' in data:
                self.golden_datasets = data['qa_pairs']
            else:
                logger.warning("Unexpected Golden Dataset format")
                self.golden_datasets = []
                return []

            logger.info("Golden Dataset 로드: %d개 항목", len(self.golden_datasets))
            return self.golden_datasets
        except Exception as e:
            logger.error("Golden Dataset 로드 실패: %s", e)
            return []

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

        Args:
            agent_fn: 평가할 에이전트 함수 (question을 입력받아 결과 반환)
                      반환값: Dict with keys: answer, tools_used (optional)
            dataset_path: Golden Dataset 파일 경로
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
        if not self.golden_datasets or dataset_path:
            self.load_golden_dataset(dataset_path)

        if not self.golden_datasets:
            return {"error": "Golden Dataset을 로드할 수 없습니다"}

        total = len(self.golden_datasets)
        if verbose:
            print(f"🚀 Golden Dataset 기반 자동 평가 시작 ({total}개 항목)")

        # 각 QA 쌍 평가
        for idx, qa_pair in enumerate(self.golden_datasets, 1):
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
                    attempts=result.get('retry_count', 0) if isinstance(result, dict) else 0,
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
        comparison = self.compare_with_thresholds() if self.thresholds else {}

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
        """
        현재 메트릭 값을 임계값과 비교

        Returns:
            Dict: 각 메트릭별 비교 결과
            {
                'metric_name': {
                    'value': 실제 값,
                    'threshold': 임계값,
                    'status': 'pass' | 'fail',
                    'direction': 'higher' | 'lower'  # 높을수록 좋은지, 낮을수록 좋은지
                }
            }
        """
        if not self.thresholds:
            return {}

        comparison = {}

        # TCR
        tcr_data = self.tcr_tracker.calculate_tcr()
        if 'tcr' in self.thresholds:
            comparison['tcr'] = {
                'name': '작업 완료율 (TCR)',
                'value': tcr_data.get('tcr', 0),
                'threshold': self.thresholds['tcr'],
                'status': 'pass' if tcr_data.get('tcr', 0) >= self.thresholds['tcr'] else 'fail',
                'direction': 'higher',
                'unit': '%'
            }

        # Accuracy
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data and 'accuracy' in self.thresholds:
            comparison['accuracy'] = {
                'name': '정확도 (Accuracy)',
                'value': accuracy_data.get('overall_accuracy', 0),
                'threshold': self.thresholds['accuracy'],
                'status': 'pass' if accuracy_data.get('overall_accuracy', 0) >= self.thresholds['accuracy'] else 'fail',
                'direction': 'higher',
                'unit': '%'
            }

        # Hallucination
        hall_data = self.hallucination_detector.get_hallucination_rate()
        if 'hallucination' in self.thresholds:
            comparison['hallucination'] = {
                'name': '환각 발생률 (Hallucination)',
                'value': hall_data.get('overall_rate', 0),
                'threshold': self.thresholds['hallucination'],
                'status': 'pass' if hall_data.get('overall_rate', 0) <= self.thresholds['hallucination'] else 'fail',
                'direction': 'lower',
                'unit': '%'
            }

        # Quality
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and 'quality' in self.thresholds:
            avg_quality = quality_data.get('avg_total_score', 0) * 2  # Convert to 10-point scale
            comparison['quality'] = {
                'name': '응답 품질 (Quality)',
                'value': avg_quality,
                'threshold': self.thresholds['quality'],
                'status': 'pass' if avg_quality >= self.thresholds['quality'] else 'fail',
                'direction': 'higher',
                'unit': '/10'
            }

        # Latency
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data and 'latency' in self.thresholds:
            comparison['latency'] = {
                'name': '응답 시간 (Latency)',
                'value': latency_data.get('p95', 0),
                'threshold': self.thresholds['latency'],
                'status': 'pass' if latency_data.get('p95', 0) <= self.thresholds['latency'] else 'fail',
                'direction': 'lower',
                'unit': 's'
            }

        # Cost per Task
        token_data = self.token_tracker.get_usage_stats()
        if 'cost_per_task' in self.thresholds:
            comparison['cost_per_task'] = {
                'name': '작업당 비용 (Cost per Task)',
                'value': token_data.get('avg_cost_per_task', 0),
                'threshold': self.thresholds['cost_per_task'],
                'status': 'pass' if token_data.get('avg_cost_per_task', 0) <= self.thresholds['cost_per_task'] else 'fail',
                'direction': 'lower',
                'unit': '$'
            }

        # RAG Metrics
        # Faithfulness
        if 'faithfulness' in self.thresholds:
            faithfulness_values = self.rag_metrics.get('faithfulness', [])
            avg_faithfulness = statistics.mean(faithfulness_values) if faithfulness_values else 0.0
            comparison['faithfulness'] = {
                'name': 'Faithfulness',
                'value': avg_faithfulness,
                'threshold': self.thresholds['faithfulness'],
                'status': 'pass' if avg_faithfulness >= self.thresholds['faithfulness'] else 'fail' if faithfulness_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Answer Relevancy
        if 'answer_relevancy' in self.thresholds:
            relevancy_values = self.rag_metrics.get('answer_relevancy', [])
            avg_relevancy = statistics.mean(relevancy_values) if relevancy_values else 0.0
            comparison['answer_relevancy'] = {
                'name': 'Answer Relevancy',
                'value': avg_relevancy,
                'threshold': self.thresholds['answer_relevancy'],
                'status': 'pass' if avg_relevancy >= self.thresholds['answer_relevancy'] else 'fail' if relevancy_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Context Recall
        if 'context_recall' in self.thresholds:
            recall_values = self.rag_metrics.get('context_recall', [])
            avg_recall = statistics.mean(recall_values) if recall_values else 0.0
            comparison['context_recall'] = {
                'name': 'Context Recall',
                'value': avg_recall,
                'threshold': self.thresholds['context_recall'],
                'status': 'pass' if avg_recall >= self.thresholds['context_recall'] else 'fail' if recall_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Context Precision
        if 'context_precision' in self.thresholds:
            precision_values = self.rag_metrics.get('context_precision', [])
            avg_precision = statistics.mean(precision_values) if precision_values else 0.0
            comparison['context_precision'] = {
                'name': 'Context Precision',
                'value': avg_precision,
                'threshold': self.thresholds['context_precision'],
                'status': 'pass' if avg_precision >= self.thresholds['context_precision'] else 'fail' if precision_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Layer 2: Agentic AI Metrics
        # Tool Selection Accuracy
        tool_stats = self.tool_selection_tracker.get_accuracy_stats()
        if tool_stats and 'tool_selection_accuracy' in self.thresholds:
            comparison['tool_selection_accuracy'] = {
                'name': '도구 선택 정확도 (Tool Selection Accuracy)',
                'value': tool_stats.get('avg_accuracy', 0),
                'threshold': self.thresholds['tool_selection_accuracy'],
                'status': 'pass' if tool_stats.get('avg_accuracy', 0) >= self.thresholds['tool_selection_accuracy'] else 'fail',
                'direction': 'higher',
                'unit': '%',
                'layer': 'Layer 2'
            }

        # Agent Coordination Score
        coord_data = self.agent_coordination_tracker.calculate_coordination_score()
        if coord_data and 'agent_coordination' in self.thresholds:
            # coordination_score는 0-10 척도, threshold도 0-10으로 설정
            comparison['agent_coordination'] = {
                'name': '에이전트 협업 점수 (Agent Coordination)',
                'value': coord_data.get('score', 0),
                'threshold': self.thresholds['agent_coordination'],
                'status': 'pass' if coord_data.get('score', 0) >= self.thresholds['agent_coordination'] else 'fail',
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
        if workflow_stats and 'workflow_execution' in self.thresholds:
            comparison['workflow_execution'] = {
                'name': '워크플로우 실행 성공률 (Workflow Execution)',
                'value': workflow_stats.get('step_success_rate', 0),
                'threshold': self.thresholds['workflow_execution'],
                'status': 'pass' if workflow_stats.get('step_success_rate', 0) >= self.thresholds['workflow_execution'] else 'fail',
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
        import uuid
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

        Args:
            items: 평가할 항목 목록. 각 항목은 다음 키를 포함:
                - question (str): 질문
                - response (str): 에이전트 응답
                - ground_truth (str): 정답
                - task_id (str, 선택): 태스크 ID
                - execution_time (float, 선택): 실행 시간
            task_type: 태스크 유형 (기본값: "qa")
            task_id_prefix: 자동 생성 task_id 접두사 (기본값: "batch")

        Returns:
            List[Dict[str, Any]]: 각 태스크의 평가 결과 목록

        Example:
            >>> results = monitor.evaluate_batch([
            ...     {"question": "Q1", "response": "A1", "ground_truth": "G1"},
            ...     {"question": "Q2", "response": "A2", "ground_truth": "G2"},
            ... ])
            >>> avg = sum(r["accuracy_score"] for r in results) / len(results)
        """
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

    def record_task(self, task_result: TaskResult,
                   ground_truth: Optional[Any] = None,
                   context: Optional[str] = None,
                   request: Optional[str] = None,       # deprecated: use task_result.question
                   response: Optional[str] = None,      # deprecated: use task_result.response
                   expected_elements: Optional[List[str]] = None) -> None:
        """
        Record a complete task execution

        Args:
            task_result: TaskResult from agent execution
            ground_truth: Expected/correct output
            context: Context or retrieved documents for hallucination detection
            request: User request/query
            response: Agent's response/output for hallucination detection
            expected_elements: Expected elements in response

        .. deprecated::
            ``request``, ``response``, ``ground_truth``, ``context`` 파라미터는
            deprecated입니다. TaskResult 필드를 직접 설정하세요.
        """
        # Deprecation warnings for parameters that duplicate TaskResult fields
        if request is not None:
            warnings.warn(
                "record_task(request=...) is deprecated. "
                "Use TaskResult(question=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if ground_truth is not None:
            warnings.warn(
                "record_task(ground_truth=...) is deprecated. "
                "Use TaskResult(ground_truth=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Persist raw content onto TaskResult so it is included in asdict() → JSON
        # 경고는 항상, 덮어쓰기는 None일 때만
        if request is not None and task_result.question is None:
            task_result.question = request
        if response is not None and task_result.response is None:
            task_result.response = response
        if ground_truth is not None and task_result.ground_truth is None:
            task_result.ground_truth = str(ground_truth) if not isinstance(ground_truth, str) else ground_truth

        # Task completion
        self.tcr_tracker.add_task(task_result)
        
        # Accuracy - use TaskResult's accuracy_score
        # Normalize to 0-1 scale: users may pass 0-100 scale values
        _accuracy = task_result.accuracy_score
        if _accuracy is not None and _accuracy > 1.0:
            _accuracy = _accuracy / 100.0
        self.accuracy_evaluator.evaluations.append({
            "task_id": task_result.task_id,
            "task_type": task_result.task_type,
            "accuracy": _accuracy,
            "timestamp": datetime.now()
        })
        
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
            existing_retry_ids = {a.get('task_id') for a in self.retry_tracker.attempts}
            if task_result.task_id not in existing_retry_ids:
                attempts_log = [
                    {"success": i == task_result.attempts - 1, "duration": 1.0}
                    for i in range(task_result.attempts)
                ]
                self.retry_tracker.track_attempts(task_result.task_id, attempts_log)

        # Agentic AI: Tool Selection Accuracy
        # integration(_record_layer2)이 이미 기록했으면 중복 기록하지 않음
        if task_result.expected_tools and task_result.tool_calls:
            existing_selection_ids = {s.get('task_id') for s in self.tool_selection_tracker.selections}
            if task_result.task_id not in existing_selection_ids:
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
        _eff_response_hall = response or task_result.response
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
            except Exception as e:
                # Silent fail - don't break the entire evaluation
                warnings.warn(f"Hallucination detection failed for {task_result.task_id}: {e}")

        # Auto-trigger: Quality Evaluation (response + request 있을 때 자동 평가)
        _eff_request = request or task_result.question
        _eff_response = response or task_result.response
        if _eff_request and _eff_response:
            _existing_quality_ids = {e.get("task_id") for e in self.quality_evaluator.evaluations}
            if task_result.task_id not in _existing_quality_ids:
                try:
                    _gt_str = str(ground_truth) if ground_truth is not None else task_result.ground_truth
                    _ee = expected_elements or []
                    # expected_elements 없으면 ground_truth에서 자동 추출
                    if not _ee and _gt_str:
                        _STOPWORDS = {
                            "이", "가", "은", "는", "을", "를", "의", "에", "도", "로",
                            "the", "a", "an", "is", "are", "was", "were", "in", "on", "at"
                        }
                        _ee = [
                            w for w in re.sub(r'[^\w\s]', '', _gt_str).split()
                            if len(w) >= 2 and w.lower() not in _STOPWORDS
                        ][:10]
                    self.quality_evaluator.evaluate_response(
                        task_id=task_result.task_id,
                        response=_eff_response,
                        request=_eff_request,
                        expected_elements=_ee,
                        ground_truth=_gt_str,
                    )
                except Exception as _qe:
                    warnings.warn(
                        f"Auto quality evaluation failed for {task_result.task_id}: {_qe}",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        # Auto-trigger: Accuracy Evaluation (response + ground_truth 있고, accuracy_score==0일 때)
        _eff_gt = ground_truth if ground_truth is not None else task_result.ground_truth
        if _eff_response and _eff_gt:
            _has_score = task_result.accuracy_score is not None and task_result.accuracy_score != 0.0
            _existing_acc_ids = {e.get("task_id") for e in self.accuracy_evaluator.evaluations}
            if not _has_score and task_result.task_id not in _existing_acc_ids:
                try:
                    self.accuracy_evaluator.add_evaluation(
                        task_id=task_result.task_id,
                        ground_truth=str(_eff_gt),
                        prediction=_eff_response,
                        task_type=task_result.task_type,
                    )
                except Exception as _ae:
                    warnings.warn(
                        f"Auto accuracy evaluation failed for {task_result.task_id}: {_ae}",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        # Auto-trigger: LLM Judge (opt-in, Phase 1-A)
        if self.enable_llm_judge and self.llm_judge and _eff_request and _eff_response:
            try:
                judge_result = self.llm_judge.judge(
                    task_id=task_result.task_id,
                    question=_eff_request,
                    response=_eff_response,
                    context=context or task_result.context,
                )
                # Attach judge scores directly onto the TaskResult so they are
                # serialised into the JSON output without needing schema changes.
                if not judge_result.get("skipped") and judge_result.get("scores"):
                    task_result.llm_judge = judge_result
            except Exception as _je:
                warnings.warn(
                    f"LLM Judge failed for {task_result.task_id}: {_je}",
                    RuntimeWarning,
                    stacklevel=2,
                )

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
        if faithfulness is not None:
            self.rag_metrics['faithfulness'].append(faithfulness)
        if answer_relevancy is not None:
            self.rag_metrics['answer_relevancy'].append(answer_relevancy)
        if context_recall is not None:
            self.rag_metrics['context_recall'].append(context_recall)
        if context_precision is not None:
            self.rag_metrics['context_precision'].append(context_precision)

    def get_rag_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of RAG metrics

        Returns:
            Dict containing average and statistics for each RAG metric
        """
        summary = {}

        for metric_name, values in self.rag_metrics.items():
            if values:
                mean_val = statistics.mean(values)
                summary[metric_name] = {
                    'mean': mean_val,  # Use 'mean' for consistency with dashboard
                    'average': mean_val,  # Alias for compatibility
                    'min': min(values),
                    'max': max(values),
                    'std': statistics.stdev(values) if len(values) > 1 else 0.0,
                    'count': len(values)
                }
            else:
                summary[metric_name] = {
                    'mean': 0.0,
                    'average': 0.0,
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
        return {
            "layer1_security": {
                "input_security": self.input_sanitizer.get_security_stats() if self.input_sanitizer else {},
                "output_leakage": self.output_leakage_detector.get_leakage_stats() if self.output_leakage_detector else {},
                "authorization": self.tool_authorizer.get_compliance_stats() if self.tool_authorizer else {},
            },
            "layer2_security": {
                "privilege_escalation": self.privilege_escalation_detector.get_escalation_stats() if self.privilege_escalation_detector else {},
                "attack_detection": self.tool_chain_attack_detector.get_attack_stats() if self.tool_chain_attack_detector else {},
            },
        }

    def generate_report(self) -> "EvaluationReport":
        """Generate comprehensive evaluation report"""
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
        thresholds = self.thresholds if self.thresholds else {
            'tcr': 80.0,
            'accuracy': 70.0,
            'hallucination': 10.0,
            'quality': 6.0,
            'latency': 10.0,
            'cost_per_task': 0.05,
        }

        # Check TCR
        tcr_data = self.tcr_tracker.calculate_tcr()
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

        # Check accuracy
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data:
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

        # Check quality
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and "avg_total_score" in quality_data:
            # MEDIUM PRIORITY FIX: Only generate alerts when data actually exists
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

        # Accuracy improvement
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data:
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

        # Quality improvement
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and "avg_total_score" in quality_data:
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
            print(f"    - Agent Coordination Score   : {coord_stats.get('score', 0):.2f}")
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

    def print_metric_breakdown(self, task_id: str = None, verbose: bool = True) -> None:
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
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(asdict(report), f, indent=2, default=str)
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
        import os

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
            "rag_metrics": self.rag_metrics,
            # Save advanced metrics summary (DeepEval, Ragas 등)
            "advanced_metrics_summary": getattr(self, '_advanced_metrics_summary', {})
        }

        # Auto-add security evaluators if enabled
        if hasattr(self, 'input_sanitizer') and self.input_sanitizer is not None:
            security_data = self._get_security_evaluator_data()
            if security_data:  # Only add if there's actually security data
                data["evaluators"]["security"] = security_data

        # Always add full report data (for Dashboard compatibility)
        self._append_report_data(data)

        # Convert datetime objects and enum values to strings
        for task in data["tasks"]:
            if isinstance(task.get("timestamp"), datetime):
                task["timestamp"] = task["timestamp"].isoformat()
            tt = task.get("task_type")
            if hasattr(tt, "value"):
                task["task_type"] = tt.value

        def _json_serializer(obj: Any) -> Any:
            """Custom JSON serializer for non-standard types."""
            from datetime import datetime as _dt
            from enum import Enum
            if isinstance(obj, _dt):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="replace")
            logger.debug("JSON serialization fallback for type %s", type(obj).__name__)
            return str(obj)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=_json_serializer)

        logger.info("Performance data saved to %s", filename)

        # HTML 보고서 자동 생성 (실패해도 JSON 저장은 완료된 것으로 처리)
        try:
            from ...reporting.comprehensive_report import generate_comprehensive_html_report
            html_path = filename if filename.endswith(".html") else filename.rsplit(".json", 1)[0] + ".html"
            if not html_path.endswith(".html"):
                html_path = filename + ".html"
            html_content = generate_comprehensive_html_report(self)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
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

        장시간 운영되는 서비스에서 메모리를 관리하기 위해 사용한다.

        Returns:
            Dict[str, Any]: flush 전 수집된 평가 요약 통계

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... 1000개 태스크 처리 ...
            >>> summary = monitor.flush()  # 요약 저장 후 메모리 정리
            >>> print(summary["total_tasks"])  # 1000
        """
        import datetime as _dt_mod

        # 현재 상태 요약 계산
        report = self.generate_report()
        tcr_data = report.accuracy_metrics.get("tcr") or {}
        latency_data = (report.efficiency_metrics.get("latency") or {})
        accuracy_data = report.accuracy_metrics.get("accuracy_scores") or {}

        summary: Dict[str, Any] = {
            "total_tasks": report.total_tasks,
            "success_rate": tcr_data.get("success_rate", 0.0),
            "avg_latency_ms": latency_data.get("mean", 0.0),
            "avg_accuracy": accuracy_data.get("overall_accuracy", 0.0),
            "flushed_at": _dt_mod.datetime.now().isoformat(),
        }

        # 각 트래커 초기화
        self.tcr_tracker.tasks.clear()
        self.accuracy_evaluator.evaluations.clear()
        self.hallucination_detector.detections.clear()
        self.latency_tracker.latencies.clear()
        self.token_tracker.usage_log.clear()
        self.retry_tracker.attempts.clear()
        self.tool_analyzer.executions.clear()
        self.tool_selection_tracker.selections.clear()
        self.agent_coordination_tracker.interactions.clear()
        self.workflow_tracker.executions.clear()
        self.quality_evaluator.evaluations.clear()

        # RAG 지표 초기화
        for key in self.rag_metrics:
            self.rag_metrics[key] = []

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
        import os as _os
        tm.log_event(
            event_type="lifecycle",
            user="system",
            action="file_saved",
            target_type="file",
            target_id=_os.path.basename(filename),
            details={
                "filepath": filename,
                "total_tasks": n,
                "file_size_bytes": _os.path.getsize(filename) if _os.path.exists(filename) else 0,
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
        import os

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
            import dataclasses as _dc
            _tr_fields = {f.name for f in _dc.fields(TaskResult)}
            task = TaskResult(**{k: v for k, v in task_dict.items() if k in _tr_fields})
            monitor.record_task(task)

        # Restore evaluator data (if available)
        evaluators = data.get("evaluators", {})

        if evaluators:
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
                if "input_sanitizer" in security_data:
                    monitor.input_sanitizer.evaluations = security_data["input_sanitizer"].get("evaluations", [])

                # Output Leakage Detector
                if "output_leakage_detector" in security_data:
                    monitor.output_leakage_detector.detections = security_data["output_leakage_detector"].get("detections", [])

                # Tool Authorizer
                if "tool_authorizer" in security_data:
                    monitor.tool_authorizer.tool_calls = security_data["tool_authorizer"].get("tool_calls", [])

                # Privilege Escalation Detector
                if "privilege_escalation_detector" in security_data:
                    monitor.privilege_escalation_detector.escalation_events = security_data["privilege_escalation_detector"].get("escalation_events", [])

                # Tool Chain Attack Detector
                if "tool_chain_attack_detector" in security_data:
                    monitor.tool_chain_attack_detector.detections = security_data["tool_chain_attack_detector"].get("detections", [])

            logger.debug(
                "Restored evaluator data: Quality=%d, Hallucination=%d, ToolCalls=%d, "
                "ToolSelection=%d, AgentCoord=%d, Workflow=%d",
                len(monitor.quality_evaluator.evaluations),
                len(monitor.hallucination_detector.detections),
                len(monitor.tool_analyzer.executions),
                len(monitor.tool_selection_tracker.selections),
                len(monitor.agent_coordination_tracker.interactions),
                len(monitor.workflow_tracker.executions),
            )
            if "security" in evaluators:
                logger.debug(
                    "Restored security data: InputEvals=%d, OutputDetections=%d, ToolCalls=%d",
                    len(monitor.input_sanitizer.evaluations),
                    len(monitor.output_leakage_detector.detections),
                    len(monitor.tool_authorizer.tool_calls),
                )

        # Restore advanced_metrics_summary (DeepEval, Ragas 등) — check both top-level and report.*
        _ams = data.get("advanced_metrics_summary") or data.get("report", {}).get("advanced_metrics_summary")
        if _ams:
            monitor._advanced_metrics_summary = _ams
            logger.debug("Restored advanced metrics summary with %d metrics", len(_ams))

        # Restore RAG metrics
        if "rag_metrics" in data:
            monitor.rag_metrics = data["rag_metrics"]
            total_rag_values = sum(len(v) for v in monitor.rag_metrics.values() if v)
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
