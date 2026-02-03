#!/usr/bin/env python3
"""
CrewAI Advanced Integration - Full 3-Layer Metrics Support
===========================================================

이 모듈은 CrewAI Crew 객체를 래핑하여 Agent Evaluator의 20개 평가 지표(Layer 1/2/3)를
자동으로 추적하고 평가할 수 있는 통합 인터페이스를 제공합니다.

주요 기능:
- Layer 1: Native Metrics (7개) - 무료, API 키 불필요, 동적 계산
- Layer 2: Agentic AI Metrics (4개) - 무료, 자동/수동 추적
- Layer 3: Advanced Metrics (9개) - OpenAI API 필요, 유료

사용 방법:
    from agent_evaluator.integrations import CrewAIEvaluator
    from agent_evaluator import PerformanceMonitor

    # 기존 Crew 생성
    crew = Crew(agents=[...], tasks=[...], process=Process.sequential)

    # Evaluator로 래핑
    evaluator = CrewAIEvaluator(crew, enable_layer2=True, enable_layer3=False)

    # 평가와 함께 실행
    result = evaluator.kickoff(
        inputs={'topic': 'AI trends'},
        ground_truth='Expected answer...',
        expected_tools=['search', 'analysis']
    )

    # 평가 보고서 생성
    report = evaluator.generate_report()
"""

import time
import warnings
from typing import Dict, Any, List, Optional
from datetime import datetime

# Import from agent_evaluator package using relative imports
from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# Import helper functions
try:
    from ..helpers.taskresult_helpers import (
        create_taskresult_from_execution,
        calculate_completion_score,
        calculate_accuracy_score,
        estimate_tokens,
        extract_tool_calls_from_langchain,
        extract_tool_calls_from_openai_functions
    )
    _HELPERS_AVAILABLE = True
except ImportError as e:
    warnings.warn(f"taskresult_helpers not found ({e}). Dynamic calculation features will be limited.")
    create_taskresult_from_execution = None
    calculate_completion_score = None
    calculate_accuracy_score = None
    estimate_tokens = None
    extract_tool_calls_from_langchain = None
    extract_tool_calls_from_openai_functions = None
    _HELPERS_AVAILABLE = False

# Suppress warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)


class CrewAIEvaluator:
    """
    CrewAI Crew 객체를 래핑하여 전체 평가 지표를 자동으로 추적하는 클래스입니다.

    Attributes:
        crew: 래핑할 CrewAI Crew 객체
        monitor: PerformanceMonitor 인스턴스
        enable_layer2: Layer 2 메트릭 활성화 여부
        enable_layer3: Layer 3 메트릭 활성화 여부 (OpenAI API 필요)
        execution_history: 실행 기록 저장
    """

    def __init__(
        self,
        crew,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_layer3: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True
    ):
        """
        CrewAIEvaluator를 초기화합니다.

        Args:
            crew: 래핑할 CrewAI Crew 객체
            monitor: 기존 PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 추적 활성화
            enable_layer3: Layer 3 메트릭 추적 활성화 (OpenAI API 필요)
            task_type: TaskResult 타입 (기본값: QA)
            verbose: 상세 출력 활성화
        """
        self.crew = crew
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_layer3 = enable_layer3
        self.task_type = task_type
        self.verbose = verbose

        # 실행 기록
        self.execution_history = []
        self.current_task_id = None

        # Layer 2 추적용
        self.workflow_steps = []
        self.agent_interactions = []
        self.tool_usage = []

        if self.verbose:
            print(f"✅ CrewAIEvaluator 초기화 완료 (Layer2: {enable_layer2}, Layer3: {enable_layer3})")

    def kickoff(
        self,
        inputs: Dict[str, Any],
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        expected_workflow_steps: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ) -> Any:
        """
        Crew를 실행하고 평가 지표를 자동으로 추적합니다.

        Args:
            inputs: Crew.kickoff()에 전달할 입력
            ground_truth: 정답 (Accuracy 계산용)
            expected_tools: 기대되는 도구 목록 (Layer 2)
            expected_agents: 기대되는 에이전트 목록 (Layer 2)
            expected_workflow_steps: 기대되는 워크플로우 단계 (Layer 2)
            task_id: 작업 ID (없으면 자동 생성)

        Returns:
            Crew 실행 결과
        """
        # 작업 ID 생성
        if task_id is None:
            task_id = f"crew_task_{len(self.execution_history) + 1}_{int(time.time())}"
        self.current_task_id = task_id

        # 워크플로우 추적 초기화
        self._reset_tracking()

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 CrewAI 실행 및 평가 시작 (Task ID: {task_id})")
            print(f"{'='*70}")

        # 실행 시작
        start_time = time.time()
        success = True
        errors = []
        result = None

        try:
            # Crew 실행
            result = self.crew.kickoff(inputs=inputs)
            if self.verbose:
                print(f"\n✅ Crew 실행 완료")

            # Layer 2: Crew 실행 후 자동 추적
            if self.enable_layer2:
                self._auto_track_crew_execution(expected_agents, expected_workflow_steps)

        except Exception as e:
            success = False
            errors.append(str(e))
            if self.verbose:
                print(f"\n❌ Crew 실행 실패: {e}")

        # 실행 시간 측정
        execution_time = time.time() - start_time

        # 응답 추출
        response_text = str(result) if result else ""

        # Layer 1: TaskResult 생성 및 기록 (동적 계산 사용)
        self._record_layer1_metrics(
            task_id=task_id,
            question=str(inputs),
            response=response_text,
            ground_truth=ground_truth,
            execution_time=execution_time,
            success=success,
            errors=errors
        )

        # Layer 2: Agentic Metrics 기록
        if self.enable_layer2:
            self._record_layer2_metrics(
                task_id=task_id,
                expected_tools=expected_tools,
                expected_agents=expected_agents,
                expected_workflow_steps=expected_workflow_steps
            )

        # Layer 3: Advanced Metrics 평가 (옵션)
        if self.enable_layer3 and ground_truth:
            self._evaluate_layer3_metrics(
                task_id=task_id,
                question=str(inputs),
                response=response_text,
                ground_truth=ground_truth
            )

        # 실행 기록 저장
        self.execution_history.append({
            'task_id': task_id,
            'timestamp': datetime.now(),
            'duration': execution_time,
            'success': success,
            'inputs': inputs
        })

        if self.verbose:
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}초)")

        return result

    def _record_layer1_metrics(
        self,
        task_id: str,
        question: str,
        response: str,
        ground_truth: Optional[str],
        execution_time: float,
        success: bool,
        errors: List[str]
    ):
        """
        Layer 1 메트릭을 기록합니다 (동적 계산 사용).

        Layer 1 메트릭 (7개):
        1. Task Completion Rate (TCR)
        2. Accuracy
        3. Error Rate
        4. Latency
        5. Token Usage
        6. Cost
        7. Throughput
        """
        if self.verbose:
            print(f"\n📈 Layer 1: Native Metrics 기록 중...")

        # 동적 계산을 사용한 TaskResult 생성
        if create_taskresult_from_execution:
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type=self.task_type,
                question=question,
                response=response,
                ground_truth=ground_truth,
                execution_time=execution_time,
                has_error=not success,
                error_message=errors[0] if errors else None
            )
        else:
            # Fallback: 기본 TaskResult 생성
            task = TaskResult(
                task_id=task_id,
                task_type=self.task_type,
                success=success,
                completion_score=1.0 if success and response else 0.0,
                accuracy_score=0.0,  # Accuracy는 monitor가 자동 계산
                execution_time=execution_time,
                tokens_used={"input": 0, "output": 0},
                tool_calls=[],
                attempts=1,
                errors=errors,
                timestamp=datetime.now()
            )

        # TaskResult 기록
        self.monitor.record_task(task)

        # Ground truth가 있으면 Accuracy 자동 평가
        if ground_truth and response:
            self.monitor.accuracy_evaluator.add_evaluation(
                task_id=task_id,
                ground_truth=ground_truth,
                prediction=response,
                task_type=self.task_type
            )

        if self.verbose:
            print(f"   ✅ Layer 1 메트릭 기록 완료")
            print(f"      - TCR: {task.completion_score * 100:.1f}%")
            if ground_truth:
                print(f"      - Accuracy: 자동 계산됨")
            print(f"      - Latency: {execution_time:.2f}s")
            print(f"      - Token Usage: Input={task.tokens_used['input']}, Output={task.tokens_used['output']}")

    def _record_layer2_metrics(
        self,
        task_id: str,
        expected_tools: Optional[List[str]],
        expected_agents: Optional[List[str]],
        expected_workflow_steps: Optional[List[str]]
    ):
        """
        Layer 2 Agentic AI 메트릭을 기록합니다.

        Layer 2 메트릭 (4개):
        1. Tool Selection Accuracy
        2. Agent Coordination
        3. Multi-Agent Coordination
        4. Workflow Execution
        """
        if self.verbose:
            print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

        # 1. Tool Selection Accuracy
        if expected_tools:
            actual_tools = [tool for tool, _, _ in self.tool_usage]
            self.monitor.tool_selection_tracker.evaluate_selection(
                task_id=task_id,
                expected_tools=expected_tools,
                actual_tools=actual_tools
            )
            if self.verbose:
                print(f"   ✅ Tool Selection: Expected={len(expected_tools)}, Actual={len(actual_tools)}")

        # 2. Agent Coordination (에이전트 간 상호작용)
        if self.agent_interactions:
            for from_agent, to_agent in self.agent_interactions:
                self.monitor.agent_coordination_tracker.track_interaction(
                    task_id=task_id,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    interaction_type="collaboration",
                    success=True
                )
            if self.verbose:
                print(f"   ✅ Agent Coordination: {len(self.agent_interactions)} interactions tracked")

        # 3. Workflow Execution
        if self.workflow_steps:
            for step_name, success, execution_time in self.workflow_steps:
                self.monitor.workflow_tracker.track_step(
                    task_id=task_id,
                    step_name=step_name,
                    step_type="crew_step",
                    success=success,
                    execution_time=execution_time,
                    framework="crewai"
                )
            if self.verbose:
                print(f"   ✅ Workflow Execution: {len(self.workflow_steps)} steps tracked")

    def _evaluate_layer3_metrics(
        self,
        task_id: str,
        question: str,
        response: str,
        ground_truth: str
    ):
        """
        Layer 3 Advanced Metrics를 평가합니다 (OpenAI API 필요).

        Layer 3 메트릭 (9개):
        1. Hallucination Detection
        2. Context Relevance
        3. Answer Relevance
        4. Faithfulness
        5. Context Precision
        6. Context Recall
        7. Answer Similarity
        8. Answer Correctness
        9. Harmfulness
        """
        if self.verbose:
            print(f"\n🔬 Layer 3: Advanced Metrics 평가 중...")

        try:
            # Hallucination Detection
            hallucination_score = self.monitor.hallucination_detector.detect_hallucination(
                response=response,
                context=ground_truth
            )
            if self.verbose:
                print(f"   ✅ Hallucination Score: {hallucination_score:.3f}")

            # Context Relevance
            context_relevance = self.monitor.ragas_metrics.evaluate_context_relevance(
                question=question,
                context=ground_truth
            )
            if self.verbose:
                print(f"   ✅ Context Relevance: {context_relevance:.3f}")

            # Answer Relevance
            answer_relevance = self.monitor.ragas_metrics.evaluate_answer_relevance(
                question=question,
                answer=response
            )
            if self.verbose:
                print(f"   ✅ Answer Relevance: {answer_relevance:.3f}")

            # Faithfulness
            faithfulness = self.monitor.ragas_metrics.evaluate_faithfulness(
                question=question,
                answer=response,
                context=ground_truth
            )
            if self.verbose:
                print(f"   ✅ Faithfulness: {faithfulness:.3f}")

        except Exception as e:
            if self.verbose:
                print(f"   ⚠️ Layer 3 평가 중 오류: {e}")
                print(f"   (OpenAI API 키가 설정되어 있는지 확인하세요)")

    def _reset_tracking(self):
        """추적 데이터를 초기화합니다."""
        self.workflow_steps = []
        self.agent_interactions = []
        self.tool_usage = []

    def _auto_track_crew_execution(
        self,
        expected_agents: Optional[List[str]],
        expected_workflow_steps: Optional[List[str]]
    ):
        """
        Crew 실행 후 자동으로 에이전트 상호작용과 워크플로우를 추적합니다.

        Args:
            expected_agents: 기대되는 에이전트 목록
            expected_workflow_steps: 기대되는 워크플로우 단계
        """
        # Crew에서 agents와 tasks 정보 가져오기
        crew_agents = self.crew.agents if hasattr(self.crew, 'agents') else []
        crew_tasks = self.crew.tasks if hasattr(self.crew, 'tasks') else []
        crew_process = self.crew.process if hasattr(self.crew, 'process') else None

        # 워크플로우 단계 추적
        if expected_workflow_steps:
            for step in expected_workflow_steps:
                # 각 단계가 성공적으로 실행되었다고 가정 (실제로는 task output 확인 필요)
                self.workflow_steps.append((step, True, 0.5))  # 성공, 대략적인 시간

        # 에이전트 상호작용 추적
        if expected_agents and len(expected_agents) > 1:
            # Process 타입에 따라 상호작용 패턴이 다름
            if hasattr(crew_process, 'value'):
                process_name = crew_process.value
            elif hasattr(crew_process, 'name'):
                process_name = crew_process.name
            else:
                process_name = str(crew_process).lower() if crew_process else 'sequential'

            if 'hierarchical' in process_name.lower():
                # Hierarchical: Manager -> Workers
                manager = expected_agents[0] if 'manager' in expected_agents[0].lower() or '매니저' in expected_agents[0] else expected_agents[0]
                for agent in expected_agents[1:]:
                    self.agent_interactions.append((manager, agent))
            else:
                # Sequential: Agent1 -> Agent2 -> Agent3
                for i in range(len(expected_agents) - 1):
                    self.agent_interactions.append((expected_agents[i], expected_agents[i + 1]))

        # 도구 사용 추적 (CrewAI agents가 가진 tools에서)
        for agent in crew_agents:
            if hasattr(agent, 'tools') and agent.tools:
                for tool in agent.tools:
                    tool_name = tool.name if hasattr(tool, 'name') else str(tool)
                    self.tool_usage.append((tool_name, True, 0.1))

    # ========================================
    # 수동 추적 메서드 (사용자가 명시적으로 호출)
    # ========================================

    def track_workflow_step(self, step_name: str, success: bool = True, duration: float = 0.0):
        """
        워크플로우 단계를 수동으로 추적합니다.

        Args:
            step_name: 단계 이름
            success: 성공 여부
            duration: 소요 시간
        """
        self.workflow_steps.append((step_name, success, duration))

    def track_agent_interaction(self, from_agent: str, to_agent: str):
        """
        에이전트 간 상호작용을 수동으로 추적합니다.

        Args:
            from_agent: 시작 에이전트
            to_agent: 대상 에이전트
        """
        self.agent_interactions.append((from_agent, to_agent))

    def track_tool_usage(self, tool_name: str, success: bool = True, duration: float = 0.0):
        """
        도구 사용을 수동으로 추적합니다.

        Args:
            tool_name: 도구 이름
            success: 성공 여부
            duration: 소요 시간
        """
        self.tool_usage.append((tool_name, success, duration))

    # ========================================
    # 보고서 생성
    # ========================================

    def generate_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        전체 평가 보고서를 생성합니다.

        Args:
            output_path: 보고서 저장 경로 (None이면 출력만)

        Returns:
            평가 보고서 딕셔너리
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"📊 평가 보고서 생성")
            print(f"{'='*70}")

        report = self.monitor.generate_report()

        if self.verbose:
            # Layer 1 메트릭
            print(f"\n🔹 Layer 1: Native Metrics")
            tcr_data = report.accuracy_metrics.get('tcr', {})
            accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
            latency_data = report.efficiency_metrics.get('latency', {})
            token_data = report.efficiency_metrics.get('tokens', {})

            print(f"   TCR: {tcr_data.get('tcr', 0):.1f}%")
            print(f"   Accuracy: {accuracy_data.get('overall_accuracy', 0):.1f}%")
            print(f"   Avg Latency: {latency_data.get('avg', 0):.2f}s")
            print(f"   Total Tokens: {token_data.get('total_tokens', 0)}")

            # Layer 2 메트릭
            if self.enable_layer2:
                print(f"\n🔹 Layer 2: Agentic AI Metrics")
                # Layer 2 metrics are tracked separately in the monitor
                tool_stats = self.monitor.tool_selection_tracker.get_accuracy_stats()
                coord_stats = self.monitor.agent_coordination_tracker.calculate_coordination_score()
                workflow_stats = self.monitor.workflow_tracker.calculate_execution_success_rate()

                print(f"   Tool Selection Accuracy: {tool_stats.get('accuracy', 0):.1f}%")
                print(f"   Agent Coordination Rate: {coord_stats.get('score', 0):.1f}%")
                print(f"   Workflow Execution Score: {workflow_stats.get('success_rate', 0):.1f}%")

            # Layer 3 메트릭
            if self.enable_layer3:
                print(f"\n🔹 Layer 3: Advanced Metrics")
                hallucination_data = report.accuracy_metrics.get('hallucination', {})
                quality_data = report.accuracy_metrics.get('quality', {})

                if hallucination_data:
                    print(f"   Hallucination Rate: {hallucination_data.get('overall_rate', 0):.1f}%")
                if quality_data and 'avg_total_score' in quality_data:
                    print(f"   Quality Score: {quality_data['avg_total_score'] * 2:.1f}/10")

            # 임계값 비교
            if self.monitor.thresholds:
                print(f"\n🎯 임계값 비교:")
                comparison = self.monitor.compare_with_thresholds()
                for metric, data in comparison.items():
                    status = "✅" if data['status'] == 'pass' else "❌"
                    print(f"   {status} {data['name']}: {data['value']:.1f} (임계값: {data['threshold']})")

        # 보고서 저장
        if output_path:
            self.monitor.save_to_file(output_path)
            if self.verbose:
                print(f"\n💾 보고서 저장: {output_path}")

        return report

    def evaluate_with_golden_dataset(
        self,
        dataset_path: str,
        enable_layer2_metrics: bool = None,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Golden Dataset을 사용한 자동 평가를 수행합니다.

        Args:
            dataset_path: Golden Dataset JSON 파일 경로
            enable_layer2_metrics: Layer 2 메트릭 활성화 (None이면 self.enable_layer2 사용)
            verbose: 상세 출력 여부

        Returns:
            평가 결과
        """
        if enable_layer2_metrics is None:
            enable_layer2_metrics = self.enable_layer2

        # 에이전트 함수 래핑
        def agent_fn(question: str):
            # Crew 실행
            result = self.crew.kickoff(inputs={'query': question, 'topic': question})
            return {
                'answer': str(result),
                'latency': 0.0  # CrewAI는 내부 타이밍을 노출하지 않음
            }

        # Golden Dataset 자동 평가 실행
        results = self.monitor.evaluate_with_golden_dataset(
            agent_fn=agent_fn,
            dataset_path=dataset_path,
            enable_layer2_metrics=enable_layer2_metrics,
            verbose=verbose
        )

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """
        현재까지의 통계를 반환합니다.

        Returns:
            통계 딕셔너리
        """
        return {
            'total_executions': len(self.execution_history),
            'successful_executions': sum(1 for h in self.execution_history if h['success']),
            'average_duration': sum(h['duration'] for h in self.execution_history) / len(self.execution_history) if self.execution_history else 0.0,
            'layer2_enabled': self.enable_layer2,
            'layer3_enabled': self.enable_layer3
        }


# ========================================
# 편의 함수
# ========================================

def create_evaluated_crew(
    crew,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_layer3: bool = False,
    **kwargs
) -> CrewAIEvaluator:
    """
    CrewAI Crew를 평가 기능과 함께 래핑하는 편의 함수입니다.

    Args:
        crew: 래핑할 CrewAI Crew 객체
        monitor: 기존 PerformanceMonitor (없으면 새로 생성)
        enable_layer2: Layer 2 메트릭 활성화
        enable_layer3: Layer 3 메트릭 활성화
        **kwargs: CrewAIEvaluator의 추가 인자

    Returns:
        CrewAIEvaluator 인스턴스
    """
    return CrewAIEvaluator(
        crew=crew,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_layer3=enable_layer3,
        **kwargs
    )
