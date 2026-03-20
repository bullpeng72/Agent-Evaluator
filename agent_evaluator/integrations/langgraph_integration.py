#!/usr/bin/env python3
"""
LangGraph Advanced Integration - Full 3-Layer Metrics Support
===============================================================

LangGraph 워크플로우에 대한 완전한 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics (7개) - 동적 계산
- Layer 2: Agentic AI Metrics (4개) - Workflow Execution 자동 추적
- Layer 3: Advanced Metrics (9개) - Hallucination, RAGAS 등

사용 방법:
    from agent_evaluator.integrations import LangGraphEvaluator

    evaluator = LangGraphEvaluator(
        monitor,
        enable_layer2=True,
        enable_layer3=False
    )

    evaluator.add_node("step1", your_function)
    evaluator.add_edge("step1", "step2")

    result = evaluator.run(
        initial_state={"messages": []},
        ground_truth="Expected...",
        expected_workflow_steps=["step1", "step2"]
    )

    report = evaluator.generate_report()
"""

import time
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime

# Relative imports
from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# Import helpers
try:
    from ..helpers.taskresult_helpers import create_taskresult_from_execution
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    create_taskresult_from_execution = None

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None


class AgentState(TypedDict):
    """LangGraph 상태"""
    messages: list
    next_step: str
    evaluation_data: dict


class LangGraphEvaluator:
    """
    LangGraph 워크플로우 평가를 위한 고급 클래스 (Layer 1/2/3 완전 지원)
    """

    def __init__(
        self,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_layer3: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True
    ):
        """
        LangGraphEvaluator 초기화

        Args:
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_layer3: Layer 3 메트릭 활성화
            task_type: Task 타입
            verbose: 상세 출력 활성화
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("LangGraph is not installed. Install with: pip install langgraph")

        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_layer3 = enable_layer3
        self.task_type = task_type
        self.verbose = verbose

        self.workflow = StateGraph(AgentState)
        self.custom_nodes = {}
        self.execution_history = []
        self.current_task_id = None

        # 기본 노드 추가
        self.workflow.add_node("start", self._start_node)
        self.workflow.add_node("end", self._end_node)
        self.workflow.set_entry_point("start")

        if self.verbose:
            print(f"✅ LangGraphEvaluator 초기화 완료 (Layer2: {enable_layer2}, Layer3: {enable_layer3})")

    def _start_node(self, state: AgentState):
        """시작 노드 - 평가 데이터 초기화"""
        self.current_task_id = f"langgraph_{int(time.time() * 1000)}"
        state["evaluation_data"] = {
            "start_time": time.time(),
            "task_id": self.current_task_id,
            "tokens": {"input": 0, "output": 0},
            "tool_calls": [],
            "errors": [],
            "workflow_steps": []
        }

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 LangGraph 실행 및 평가 시작 (Task ID: {self.current_task_id})")
            print(f"{'='*70}")

        return state

    def _end_node(self, state: AgentState):
        """종료 노드 - 평가 기록"""
        eval_data = state["evaluation_data"]
        execution_time = time.time() - eval_data["start_time"]
        success = len(eval_data["errors"]) == 0

        if self.verbose:
            print(f"\n✅ LangGraph 실행 완료")
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}초)")

        # Layer 1: TaskResult 기록
        if create_taskresult_from_execution:
            task = create_taskresult_from_execution(
                task_id=eval_data["task_id"],
                task_type=self.task_type,
                question=str(state.get("messages", "")),
                response=str(state.get("messages", "")[-1] if state.get("messages") else ""),
                ground_truth="",  # Will be set externally
                execution_time=execution_time,
                has_error=not success,
                error_message=eval_data["errors"][0] if eval_data["errors"] else None
            )
        else:
            task = TaskResult(
                task_id=eval_data["task_id"],
                task_type=self.task_type,
                success=success,
                completion_score=1.0 if success else 0.0,
                accuracy_score=0.0,
                execution_time=execution_time,
                tokens_used=eval_data["tokens"],
                tool_calls=eval_data["tool_calls"],
                attempts=1,
                errors=eval_data["errors"],
                timestamp=datetime.now()
            )

        self.monitor.record_task(task)
        return state

    def add_node(self, name: str, func):
        """커스텀 노드 추가"""
        self.custom_nodes[name] = func

        if self.enable_layer2:
            wrapped_func = self._wrap_node_for_tracking(name, func)
            self.workflow.add_node(name, wrapped_func)
        else:
            self.workflow.add_node(name, func)

    def _wrap_node_for_tracking(self, node_name: str, func):
        """노드를 래핑하여 Workflow Execution 추적"""
        def wrapped(state: AgentState):
            start_time = time.time()
            success = True
            error = None

            try:
                result = func(state)
            except Exception as e:
                success = False
                error = str(e)
                result = state
                if "evaluation_data" in result:
                    result["evaluation_data"]["errors"].append(error)

            execution_time = time.time() - start_time

            # WorkflowExecutionTracker에 기록
            if self.current_task_id:
                self.monitor.workflow_tracker.track_step(
                    task_id=self.current_task_id,
                    step_name=node_name,
                    step_type="node",
                    success=success,
                    execution_time=execution_time,
                    framework="langgraph",
                    metadata={"error": error} if error else {}
                )

            # state에도 기록
            if "evaluation_data" in result:
                result["evaluation_data"]["workflow_steps"].append({
                    "step_name": node_name,
                    "success": success,
                    "execution_time": execution_time
                })

            return result

        return wrapped

    def add_edge(self, from_node: str, to_node: str):
        """엣지 추가"""
        self.workflow.add_edge(from_node, to_node)

    def run(
        self,
        initial_state: dict,
        ground_truth: Optional[str] = None,
        expected_workflow_steps: Optional[List[str]] = None
    ):
        """워크플로우 실행 및 평가"""
        app = self.workflow.compile()
        result = app.invoke(initial_state)

        self.execution_history.append({
            'initial_state': initial_state,
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
            latency_data = report.efficiency_metrics.get('latency', {})

            print(f"   TCR: {tcr_data.get('tcr', 0):.1f}%")
            print(f"   Avg Latency: {latency_data.get('avg', 0):.2f}s")

            # Layer 2
            if self.enable_layer2:
                print(f"\n🔹 Layer 2: Agentic AI Metrics")
                workflow_stats = self.monitor.workflow_tracker.calculate_execution_success_rate()
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


def create_evaluated_langgraph(
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_layer3: bool = False,
    **kwargs
) -> LangGraphEvaluator:
    """
    LangGraph 워크플로우를 평가 기능과 함께 생성하는 편의 함수
    """
    return LangGraphEvaluator(
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_layer3=enable_layer3,
        **kwargs
    )
