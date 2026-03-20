#!/usr/bin/env python3
"""
LangChain Advanced Integration - Full 3-Layer Metrics Support
==============================================================

LangChain 에이전트에 대한 완전한 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics (7개) - 동적 계산
- Layer 2: Agentic AI Metrics (4개) - Tool Selection, Workflow 자동 추적
- Layer 3: Advanced Metrics (9개) - Hallucination, RAGAS 등

사용 방법:
    from agent_evaluator.integrations import LangChainEvaluator

    evaluator = LangChainEvaluator(
        agent,
        monitor,
        enable_layer2=True,
        enable_layer3=False
    )

    result = evaluator.run(
        query="What is AI?",
        ground_truth="Expected answer...",
        expected_tools=["search", "calculator"]
    )

    report = evaluator.generate_report()
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime

# Relative imports for package
from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# Import helpers
try:
    from ..helpers.taskresult_helpers import (
        create_taskresult_from_execution,
        extract_tool_calls_from_langchain
    )
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    create_taskresult_from_execution = None
    extract_tool_calls_from_langchain = None

# LangChain imports
try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.agents import AgentAction, AgentFinish
    from langchain_core.outputs import LLMResult
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.callbacks.base import BaseCallbackHandler
        from langchain.schema import AgentAction, AgentFinish, LLMResult
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False
        BaseCallbackHandler = object


if LANGCHAIN_AVAILABLE:
    class AdvancedLangChainCallback(BaseCallbackHandler):
        """
        LangChain용 고급 평가 콜백 핸들러 (Layer 1/2/3 완전 지원)
        """

        def __init__(
            self,
            monitor: PerformanceMonitor,
            task_type: str = TaskType.QA.value,
            expected_tools: Optional[List[str]] = None,
            ground_truth: Optional[str] = None,
            enable_layer2: bool = True,
            enable_layer3: bool = False,
            verbose: bool = True
        ):
            super().__init__()
            self.monitor = monitor
            self.task_type = task_type
            self.expected_tools = expected_tools
            self.ground_truth = ground_truth
            self.enable_layer2 = enable_layer2
            self.enable_layer3 = enable_layer3
            self.verbose = verbose

            # Tracking data
            self.current_task_id = None
            self.start_time = None
            self.tokens_used = {"input": 0, "output": 0}
            self.tool_calls = []
            self.workflow_steps = []
            self.errors = []
            self.task_input = ""
            self.task_output = ""

        def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs):
            """체인 시작"""
            self.current_task_id = f"langchain_{int(time.time() * 1000)}"
            self.start_time = time.time()
            self.tokens_used = {"input": 0, "output": 0}
            self.tool_calls = []
            self.workflow_steps = []
            self.errors = []
            self.task_input = str(inputs)

            if self.verbose:
                print(f"\n{'='*70}")
                print(f"🚀 LangChain 실행 및 평가 시작 (Task ID: {self.current_task_id})")
                print(f"{'='*70}")

        def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs):
            """LLM 호출 시작"""
            for prompt in prompts:
                self.tokens_used["input"] += len(prompt) // 4

        def on_llm_end(self, response: LLMResult, **kwargs):
            """LLM 호출 완료"""
            if response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})
                self.tokens_used["input"] = token_usage.get("prompt_tokens", self.tokens_used["input"])
                self.tokens_used["output"] += token_usage.get("completion_tokens", 0)

            if response.generations:
                for generation in response.generations[0]:
                    self.task_output += generation.text

        def on_agent_action(self, action: AgentAction, **kwargs):
            """도구 호출"""
            tool_name = action.tool
            self.tool_calls.append({
                "tool_name": tool_name,
                "parameters": {"input": str(action.tool_input)},
                "success": True,
                "duration": 0.1
            })

            # Layer 2: Workflow step tracking
            if self.enable_layer2:
                self.workflow_steps.append((tool_name, True, 0.1))

        def on_tool_end(self, output: str, **kwargs):
            """도구 호출 완료"""
            pass

        def on_chain_error(self, error: Exception, **kwargs):
            """에러 발생"""
            self.errors.append(str(error))

        def on_chain_end(self, outputs: Dict[str, Any], **kwargs):
            """체인 완료 - 평가 기록"""
            if self.current_task_id and self.start_time:
                execution_time = time.time() - self.start_time
                success = len(self.errors) == 0

                if self.verbose:
                    print(f"\n✅ LangChain 실행 완료")

                # Layer 1: TaskResult 생성 및 기록
                self._record_layer1_metrics(
                    task_id=self.current_task_id,
                    question=self.task_input,
                    response=self.task_output,
                    execution_time=execution_time,
                    success=success
                )

                # Layer 2: Agentic Metrics 기록
                if self.enable_layer2:
                    self._record_layer2_metrics(self.current_task_id)

                # Layer 3: Advanced Metrics 평가
                if self.enable_layer3 and self.ground_truth:
                    self._evaluate_layer3_metrics(
                        self.current_task_id,
                        self.task_input,
                        self.task_output
                    )

                if self.verbose:
                    print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}초)")

        def _record_layer1_metrics(
            self,
            task_id: str,
            question: str,
            response: str,
            execution_time: float,
            success: bool
        ):
            """Layer 1 메트릭 기록"""
            if self.verbose:
                print(f"\n📈 Layer 1: Native Metrics 기록 중...")

            if create_taskresult_from_execution:
                task = create_taskresult_from_execution(
                    task_id=task_id,
                    task_type=self.task_type,
                    question=question,
                    response=response,
                    ground_truth=self.ground_truth,
                    execution_time=execution_time,
                    has_error=not success,
                    error_message=self.errors[0] if self.errors else None
                )
            else:
                task = TaskResult(
                    task_id=task_id,
                    task_type=self.task_type,
                    success=success,
                    completion_score=1.0 if success else 0.0,
                    accuracy_score=0.0,
                    execution_time=execution_time,
                    tokens_used=self.tokens_used,
                    tool_calls=self.tool_calls,
                    attempts=1,
                    errors=self.errors,
                    timestamp=datetime.now()
                )

            self.monitor.record_task(task)

            if self.ground_truth and response:
                self.monitor.accuracy_evaluator.add_evaluation(
                    task_id=task_id,
                    ground_truth=self.ground_truth,
                    prediction=response,
                    task_type=self.task_type
                )

            if self.verbose:
                print(f"   ✅ Layer 1 메트릭 기록 완료")
                print(f"      - TCR: {task.completion_score * 100:.1f}%")
                if self.ground_truth:
                    print(f"      - Accuracy: 자동 계산됨")
                print(f"      - Latency: {execution_time:.2f}s")
                print(f"      - Tokens: Input={self.tokens_used['input']}, Output={self.tokens_used['output']}")

        def _record_layer2_metrics(self, task_id: str):
            """Layer 2 메트릭 기록"""
            if self.verbose:
                print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

            # Tool Selection Accuracy
            if self.expected_tools:
                actual_tools = [tool["tool_name"] for tool in self.tool_calls]
                self.monitor.tool_selection_tracker.evaluate_selection(
                    task_id=task_id,
                    expected_tools=self.expected_tools,
                    actual_tools=actual_tools
                )
                if self.verbose:
                    print(f"   ✅ Tool Selection: Expected={len(self.expected_tools)}, Actual={len(actual_tools)}")

            # Workflow Execution
            if self.workflow_steps:
                for step_name, success, duration in self.workflow_steps:
                    self.monitor.workflow_tracker.track_step(
                        task_id=task_id,
                        step_name=step_name,
                        step_type="tool_call",
                        success=success,
                        execution_time=duration,
                        framework="langchain"
                    )
                if self.verbose:
                    print(f"   ✅ Workflow Execution: {len(self.workflow_steps)} steps tracked")

        def _evaluate_layer3_metrics(self, task_id: str, question: str, response: str):
            """Layer 3 메트릭 평가"""
            if self.verbose:
                print(f"\n🔬 Layer 3: Advanced Metrics 평가 중...")

            try:
                # Hallucination Detection
                hallucination_score = self.monitor.hallucination_detector.detect_hallucination(
                    response=response,
                    context=self.ground_truth
                )
                if self.verbose:
                    print(f"   ✅ Hallucination Score: {hallucination_score:.3f}")

                # Context Relevance
                context_relevance = self.monitor.ragas_metrics.evaluate_context_relevance(
                    question=question,
                    context=self.ground_truth
                )
                if self.verbose:
                    print(f"   ✅ Context Relevance: {context_relevance:.3f}")

            except Exception as e:
                if self.verbose:
                    print(f"   ⚠️ Layer 3 평가 중 오류: {e}")


class LangChainEvaluator:
    """
    LangChain Agent 평가를 위한 고급 클래스 (Layer 1/2/3 완전 지원)
    """

    def __init__(
        self,
        agent,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_layer3: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True
    ):
        """
        LangChainEvaluator 초기화

        Args:
            agent: LangChain Agent 객체
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_layer3: Layer 3 메트릭 활성화
            task_type: Task 타입
            verbose: 상세 출력 활성화
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain is not installed. Install with: pip install langchain")

        self.agent = agent
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_layer3 = enable_layer3
        self.task_type = task_type
        self.verbose = verbose
        self.execution_history = []

        if self.verbose:
            print(f"✅ LangChainEvaluator 초기화 완료 (Layer2: {enable_layer2}, Layer3: {enable_layer3})")

    def run(
        self,
        query: str,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Agent 실행 및 평가

        Args:
            query: 질문
            ground_truth: 정답
            expected_tools: 기대되는 도구 목록
            **kwargs: Agent.run()에 전달할 추가 인자
        """
        callback = AdvancedLangChainCallback(
            monitor=self.monitor,
            task_type=self.task_type,
            expected_tools=expected_tools,
            ground_truth=ground_truth,
            enable_layer2=self.enable_layer2,
            enable_layer3=self.enable_layer3,
            verbose=self.verbose
        )

        callbacks = kwargs.get('callbacks', [])
        callbacks.append(callback)
        kwargs['callbacks'] = callbacks

        result = self.agent.run(query, **kwargs)

        self.execution_history.append({
            'query': query,
            'result': result,
            'timestamp': datetime.now()
        })

        return result

    def generate_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """평가 보고서 생성"""
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"📊 평가 보고서 생성")
            print(f"{'='*70}")

        report = self.monitor.generate_report()

        if self.verbose:
            # Layer 1
            print(f"\n🔹 Layer 1: Native Metrics")
            tcr_data = report.accuracy_metrics.get('tcr', {})
            accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
            latency_data = report.efficiency_metrics.get('latency', {})

            print(f"   TCR: {tcr_data.get('tcr', 0):.1f}%")
            print(f"   Accuracy: {accuracy_data.get('overall_accuracy', 0):.1f}%")
            print(f"   Avg Latency: {latency_data.get('avg', 0):.2f}s")

            # Layer 2
            if self.enable_layer2:
                print(f"\n🔹 Layer 2: Agentic AI Metrics")
                tool_stats = self.monitor.tool_selection_tracker.get_accuracy_stats()
                workflow_stats = self.monitor.workflow_tracker.calculate_execution_success_rate()

                print(f"   Tool Selection Accuracy: {tool_stats.get('accuracy', 0):.1f}%")
                print(f"   Workflow Execution Score: {workflow_stats.get('success_rate', 0):.1f}%")

        if output_path:
            self.monitor.save_to_file(output_path)
            if self.verbose:
                print(f"\n💾 보고서 저장: {output_path}")

        return report

    def get_statistics(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            'total_executions': len(self.execution_history),
            'layer2_enabled': self.enable_layer2,
            'layer3_enabled': self.enable_layer3
        }


# Convenience function
def create_evaluated_langchain_agent(
    agent,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_layer3: bool = False,
    **kwargs
) -> LangChainEvaluator:
    """
    LangChain Agent를 평가 기능과 함께 래핑하는 편의 함수
    """
    return LangChainEvaluator(
        agent=agent,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_layer3=enable_layer3,
        **kwargs
    )
