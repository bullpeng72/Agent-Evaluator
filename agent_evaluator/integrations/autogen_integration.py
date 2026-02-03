#!/usr/bin/env python3
"""
AutoGen Advanced Integration - Full 3-Layer Metrics Support
============================================================

AutoGen 에이전트에 대한 완전한 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics (7개) - 동적 계산
- Layer 2: Agentic AI Metrics (4개) - Agent Coordination 자동 추적
- Layer 3: Advanced Metrics (9개) - Hallucination, RAGAS 등

사용 방법:
    from agent_evaluator.integrations import AutoGenEvaluator

    assistant = AssistantAgent(name="assistant", llm_config={...})

    evaluator = AutoGenEvaluator(
        assistant,
        monitor,
        enable_layer2=True,
        enable_layer3=False
    )

    # evaluator.agent를 일반 agent처럼 사용
    user_proxy.initiate_chat(evaluator.agent, message="Hello")

    report = evaluator.generate_report()
"""

import time
import warnings
from typing import Dict, Any, List, Optional
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

# AutoGen imports
try:
    from autogen import AssistantAgent, UserProxyAgent
    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False


class AutoGenEvaluator:
    """
    AutoGen Agent 평가를 위한 고급 클래스 (Layer 1/2/3 완전 지원)
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
        AutoGenEvaluator 초기화

        Args:
            agent: AutoGen Agent 객체
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_layer3: Layer 3 메트릭 활성화
            task_type: Task 타입
            verbose: 상세 출력 활성화
        """
        if not AUTOGEN_AVAILABLE:
            raise ImportError("AutoGen is not installed. Install with: pip install pyautogen")

        self.original_agent = agent
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_layer3 = enable_layer3
        self.task_type = task_type
        self.verbose = verbose

        self.execution_history = []
        self.agent_interactions = []
        self.current_task_id = None

        # 원본 메서드 백업 및 래핑
        self._original_generate_reply = agent.generate_reply
        agent.generate_reply = self._evaluated_generate_reply

        # 래핑된 agent를 공개
        self.agent = agent

        if self.verbose:
            print(f"✅ AutoGenEvaluator 초기화 완료 (Layer2: {enable_layer2}, Layer3: {enable_layer3})")

    def _evaluated_generate_reply(self, messages, sender, **kwargs):
        """평가가 통합된 응답 생성"""
        self.current_task_id = f"autogen_{int(time.time() * 1000)}"
        start_time = time.time()
        errors = []
        reply = None
        success = True

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 AutoGen 실행 및 평가 시작 (Task ID: {self.current_task_id})")
            print(f"{'='*70}")

        try:
            # 원본 메서드 호출
            reply = self._original_generate_reply(messages, sender, **kwargs)

            if self.verbose:
                print(f"\n✅ AutoGen 실행 완료")

            # Layer 2: Agent Coordination 추적
            if self.enable_layer2:
                self._track_agent_interaction(sender)

        except Exception as e:
            errors.append(str(e))
            success = False
            if self.verbose:
                print(f"\n❌ AutoGen 실행 실패: {e}")

        execution_time = time.time() - start_time

        # Layer 1: TaskResult 기록
        self._record_layer1_metrics(
            task_id=self.current_task_id,
            messages=messages,
            reply=reply,
            execution_time=execution_time,
            success=success,
            errors=errors
        )

        # Layer 2: Agentic Metrics 기록
        if self.enable_layer2:
            self._record_layer2_metrics(self.current_task_id)

        if self.verbose:
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}초)")

        self.execution_history.append({
            'task_id': self.current_task_id,
            'messages': messages,
            'reply': reply,
            'timestamp': datetime.now(),
            'success': success
        })

        return reply

    def _track_agent_interaction(self, sender):
        """Agent Coordination 추적"""
        from_agent = sender.name if hasattr(sender, 'name') else str(sender)
        to_agent = self.original_agent.name if hasattr(self.original_agent, 'name') else "agent"

        self.agent_interactions.append((from_agent, to_agent))

    def _record_layer1_metrics(
        self,
        task_id: str,
        messages: List,
        reply: Any,
        execution_time: float,
        success: bool,
        errors: List[str]
    ):
        """Layer 1 메트릭 기록"""
        if self.verbose:
            print(f"\n📈 Layer 1: Native Metrics 기록 중...")

        # 토큰 추정
        input_text = " ".join([str(m) for m in messages if m is not None])
        output_text = str(reply) if reply else ""
        tokens_used = {
            "input": len(input_text) // 4,
            "output": len(output_text) // 4
        }

        if create_taskresult_from_execution:
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type=self.task_type,
                question=input_text,
                response=output_text,
                ground_truth="",  # Can be set externally
                execution_time=execution_time,
                has_error=not success,
                error_message=errors[0] if errors else None
            )
        else:
            task = TaskResult(
                task_id=task_id,
                task_type=self.task_type,
                success=success,
                completion_score=1.0 if success else 0.0,
                accuracy_score=0.0,
                execution_time=execution_time,
                tokens_used=tokens_used,
                tool_calls=[],
                attempts=1,
                errors=errors,
                timestamp=datetime.now()
            )

        self.monitor.record_task(task)

        if self.verbose:
            print(f"   ✅ Layer 1 메트릭 기록 완료")
            print(f"      - TCR: {task.completion_score * 100:.1f}%")
            print(f"      - Latency: {execution_time:.2f}s")
            print(f"      - Tokens: Input={tokens_used['input']}, Output={tokens_used['output']}")

    def _record_layer2_metrics(self, task_id: str):
        """Layer 2 메트릭 기록"""
        if self.verbose:
            print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

        # Agent Coordination
        if self.agent_interactions:
            for from_agent, to_agent in self.agent_interactions:
                self.monitor.agent_coordination_tracker.track_interaction(
                    task_id=task_id,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    interaction_type="message",
                    success=True,
                    context={"framework": "autogen"}
                )

            if self.verbose:
                print(f"   ✅ Agent Coordination: {len(self.agent_interactions)} interactions tracked")

            # 초기화
            self.agent_interactions = []

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
                coord_stats = self.monitor.agent_coordination_tracker.calculate_coordination_score()
                print(f"   Agent Coordination Rate: {coord_stats.get('score', 0):.1f}%")

        if output_path:
            self.monitor.save_to_file(output_path)
            if self.verbose:
                print(f"\n💾 보고서 저장: {output_path}")

        return report

    def get_statistics(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            'total_executions': len(self.execution_history),
            'successful_executions': sum(1 for h in self.execution_history if h['success']),
            'layer2_enabled': self.enable_layer2,
            'layer3_enabled': self.enable_layer3
        }


def create_evaluated_autogen_agent(
    agent,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_layer3: bool = False,
    **kwargs
) -> AutoGenEvaluator:
    """
    AutoGen Agent를 평가 기능과 함께 래핑하는 편의 함수
    """
    return AutoGenEvaluator(
        agent=agent,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_layer3=enable_layer3,
        **kwargs
    )
