#!/usr/bin/env python3
"""
Level 1 Foundation: State Transitions 추적

이 예제는 상태 기반 워크플로우의 상태 전이(State Transitions)를 추적하는 방법을 다룹니다.

다루는 내용:
1. TaskResult.state_transitions 필드 활용
2. Finite State Machine (FSM) 워크플로우 추적
3. 상태 전이 패턴 분석
4. 상태별 메트릭 수집
5. 비정상 상태 전이 탐지

사용 사례:
- 상태 기반 Agent (State Machine Agent)
- 복잡한 비즈니스 프로세스 자동화
- 주문 처리, 승인 워크플로우 등

실행 방법:
    python level_1_foundation/10_state_transitions_tracking.py
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# Add agent_evaluator to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_evaluator import PerformanceMonitor, TaskType
from agent_evaluator.core.agent_evaluator import TaskResult

FILE_PREFIX = "[L1-10]_"


def print_section(title):
    """Print a section header"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def demo_basic_state_transitions():
    """Demo 1: 기본 상태 전이 추적"""
    print_section("1. 기본 State Transitions 추적")
    
    print("💡 시나리오: 주문 처리 워크플로우")
    print()
    
    # 주문 처리 상태 머신
    states = ["received", "validated", "payment_pending", "payment_confirmed", 
              "processing", "shipped", "delivered"]
    
    state_transitions = []
    
    print("📝 상태 전이 시퀀스:\n")
    
    current_time = time.time()
    
    for i, state in enumerate(states):
        transition = {
            "from_state": states[i-1] if i > 0 else "initial",
            "to_state": state,
            "timestamp": current_time + i * 0.5,
            "duration": 0.5,
            "success": True,
            "metadata": {
                "order_id": "ORD-12345",
                "customer": "customer@example.com"
            }
        }
        
        state_transitions.append(transition)
        
        print(f"  {i+1}. {transition['from_state']} → {transition['to_state']}")
        print(f"     Duration: {transition['duration']}s")
        print(f"     Success: {'✅' if transition['success'] else '❌'}")
    
    # TaskResult에 상태 전이 기록
    task = TaskResult(
        task_id="order_processing_001",
        task_type=TaskType.DATA_ANALYSIS,
        success=True,
        completion_score=1.0,
        accuracy_score=1.0,
        execution_time=sum(t['duration'] for t in state_transitions),
        tokens_used={"input_tokens": 0, "output_tokens": 0},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
        state_transitions=state_transitions
    )
    
    print(f"\n✅ TaskResult에 {len(state_transitions)}개의 상태 전이 기록 완료")
    print(f"   총 소요 시간: {sum(t['duration'] for t in state_transitions):.2f}s")
    
    return task


def demo_fsm_with_failures():
    """Demo 2: 실패가 있는 FSM 워크플로우"""
    print_section("2. 실패 및 재시도가 있는 State Machine")
    
    print("💡 시나리오: 결제 처리 (실패 후 재시도)")
    print()
    
    state_transitions = []
    
    # 정상 흐름
    transitions_sequence = [
        ("idle", "validating_card", True, 0.3),
        ("validating_card", "card_validated", True, 0.2),
        ("card_validated", "authorizing_payment", True, 0.5),
        ("authorizing_payment", "authorization_failed", False, 0.4),  # 실패!
        
        # 재시도
        ("authorization_failed", "retrying", True, 1.0),
        ("retrying", "authorizing_payment", True, 0.3),
        ("authorizing_payment", "payment_authorized", True, 0.6),  # 성공!
        ("payment_authorized", "capturing_payment", True, 0.4),
        ("capturing_payment", "payment_complete", True, 0.3),
    ]
    
    print("📝 상태 전이 (재시도 포함):\n")
    
    current_time = time.time()
    total_duration = 0
    
    for from_state, to_state, success, duration in transitions_sequence:
        transition = {
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": current_time + total_duration,
            "duration": duration,
            "success": success,
            "metadata": {
                "transaction_id": "TXN-98765",
                "amount": 150000,
                "currency": "KRW"
            }
        }
        
        state_transitions.append(transition)
        total_duration += duration
        
        status_icon = "✅" if success else "❌"
        print(f"  {status_icon} {from_state} → {to_state} ({duration}s)")
    
    # TaskResult 생성
    task = TaskResult(
        task_id="payment_processing_001",
        task_type=TaskType.DATA_ANALYSIS,
        success=True,
        completion_score=0.9,
        accuracy_score=1.0,
        execution_time=sum(t['duration'] for t in state_transitions),
        tokens_used={"input_tokens": 0, "output_tokens": 0},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
        state_transitions=state_transitions
   
    )
    
    # 통계 계산
    total_transitions = len(state_transitions)
    failed_transitions = sum(1 for t in state_transitions if not t['success'])
    success_rate = ((total_transitions - failed_transitions) / total_transitions) * 100
    
    print(f"\n📊 상태 전이 통계:")
    print(f"   총 전이 수: {total_transitions}")
    print(f"   실패 수: {failed_transitions}")
    print(f"   성공률: {success_rate:.1f}%")
    print(f"   총 소요 시간: {total_duration:.2f}s")
    
    return task


def demo_approval_workflow():
    """Demo 3: 승인 워크플로우 (다중 승인자)"""
    print_section("3. 다단계 승인 워크플로우")
    
    print("💡 시나리오: 구매 요청 승인 프로세스")
    print()
    
    state_transitions = []
    
    # 승인 워크플로우
    workflow_steps = [
        ("submitted", "manager_review", True, 1.2, "Manager 검토 중"),
        ("manager_review", "manager_approved", True, 0.8, "Manager 승인"),
        ("manager_approved", "finance_review", True, 1.5, "Finance 검토 중"),
        ("finance_review", "finance_approved", True, 1.0, "Finance 승인"),
        ("finance_approved", "cfo_review", True, 2.0, "CFO 최종 검토"),
        ("cfo_review", "cfo_approved", True, 0.5, "CFO 승인"),
        ("cfo_approved", "purchase_order_created", True, 0.3, "구매 주문서 생성"),
        ("purchase_order_created", "completed", True, 0.2, "완료"),
    ]
    
    print("📝 다단계 승인 프로세스:\n")
    
    current_time = time.time()
    total_duration = 0
    
    for from_state, to_state, success, duration, description in workflow_steps:
        transition = {
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": current_time + total_duration,
            "duration": duration,
            "success": success,
            "metadata": {
                "request_id": "REQ-2024-001",
                "amount": 5000000,
                "description": description,
                "approver": to_state.split('_')[0] if '_' in to_state else "system"
            }
        }
        
        state_transitions.append(transition)
        total_duration += duration
        
        print(f"  ✅ {from_state}")
        print(f"     ↓ ({duration}s)")
        print(f"     {to_state}: {description}\n")
    
    # TaskResult 생성
    task = TaskResult(
        task_id="approval_workflow_001",
        task_type=TaskType.DATA_ANALYSIS,
        success=True,
        completion_score=1.0,
        accuracy_score=1.0,
        execution_time=total_duration,
        tokens_used={"input_tokens": 0, "output_tokens": 0},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
        state_transitions=state_transitions
   
    )
    
    print(f"📊 승인 워크플로우 통계:")
    print(f"   승인 단계 수: {len([s for s in workflow_steps if 'approved' in s[1]])}")
    print(f"   총 소요 시간: {total_duration:.2f}s")
    print(f"   평균 승인 시간: {total_duration / len(workflow_steps):.2f}s")
    
    return task


def demo_abnormal_transitions():
    """Demo 4: 비정상 상태 전이 탐지"""
    print_section("4. 비정상 상태 전이 탐지")
    
    print("💡 시나리오: 비정상적인 상태 전이 패턴 발견")
    print()
    
    # 정상적인 상태 전이 규칙
    valid_transitions = {
        "idle": ["started"],
        "started": ["processing", "failed"],
        "processing": ["validating", "failed"],
        "validating": ["completed", "failed"],
        "failed": ["retrying", "abandoned"],
        "retrying": ["started"],
        "completed": [],  # 종료 상태
        "abandoned": []   # 종료 상태
    }
    
    # 실제 상태 전이 (비정상 포함)
    actual_transitions = [
        ("idle", "started", True),
        ("started", "processing", True),
        ("processing", "validating", True),
        ("validating", "completed", True),
        ("completed", "processing", False),  # ❌ 비정상! 완료 후 재처리
    ]
    
    print("📝 상태 전이 검증:\n")
    
    state_transitions = []
    anomalies = []
    
    current_time = time.time()
    
    for i, (from_state, to_state, is_valid) in enumerate(actual_transitions):
        # 전이 유효성 검증
        is_allowed = to_state in valid_transitions.get(from_state, [])
        
        if not is_allowed:
            anomalies.append({
                "index": i,
                "from": from_state,
                "to": to_state,
                "reason": f"Invalid transition: {from_state} cannot transition to {to_state}"
            })
        
        transition = {
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": current_time + i * 0.5,
            "duration": 0.5,
            "success": is_valid and is_allowed,
            "metadata": {
                "is_anomaly": not is_allowed,
                "valid_next_states": valid_transitions.get(from_state, [])
            }
        }
        
        state_transitions.append(transition)
        
        status = "✅ 정상" if is_allowed else "⚠️ 비정상"
        print(f"  {i+1}. {from_state} → {to_state}: {status}")
        
        if not is_allowed:
            print(f"     허용된 전이: {', '.join(valid_transitions.get(from_state, ['없음']))}")
    
    # TaskResult 생성
    task = TaskResult(
        task_id="state_validation_001",
        task_type=TaskType.DATA_ANALYSIS,
        success=True,
        completion_score=0.8 if anomalies else 1.0,
        accuracy_score=0.9,
        execution_time=sum(t['duration'] for t in state_transitions),
        tokens_used={"input_tokens": 0, "output_tokens": 0},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now(),
        state_transitions=state_transitions
   
    )
    
    if anomalies:
        print(f"\n🚨 비정상 상태 전이 발견:")
        for anomaly in anomalies:
            print(f"   [{anomaly['index']+1}] {anomaly['from']} → {anomaly['to']}")
            print(f"       이유: {anomaly['reason']}")
    
    return task


def demo_state_metrics_analysis():
    """Demo 5: 상태별 메트릭 분석"""
    print_section("5. 상태별 메트릭 분석")
    
    print("💡 시나리오: 상태별 성능 분석")
    print()
    
    monitor = PerformanceMonitor()
    
    # 여러 워크플로우 실행 시뮬레이션
    workflows = [
        # Workflow 1: 빠른 처리
        [
            ("idle", "processing", 0.3),
            ("processing", "completed", 0.5),
        ],
        # Workflow 2: 느린 처리
        [
            ("idle", "processing", 0.4),
            ("processing", "validating", 1.5),
            ("validating", "completed", 0.8),
        ],
        # Workflow 3: 재시도 있음
        [
            ("idle", "processing", 0.3),
            ("processing", "failed", 0.6),
            ("failed", "retrying", 0.2),
            ("retrying", "processing", 0.3),
            ("processing", "completed", 0.7),
        ],
    ]
    
    all_state_durations = {}
    
    for workflow_id, transitions in enumerate(workflows, 1):
        state_transitions = []
        current_time = time.time()
        total_duration = 0
        
        for from_state, to_state, duration in transitions:
            transition = {
                "from_state": from_state,
                "to_state": to_state,
                "timestamp": current_time + total_duration,
                "duration": duration,
                "success": to_state != "failed",
                "metadata": {"workflow_id": workflow_id}
            }
            
            state_transitions.append(transition)
            total_duration += duration
            
            # 상태별 duration 수집
            if to_state not in all_state_durations:
                all_state_durations[to_state] = []
            all_state_durations[to_state].append(duration)
        
        task = TaskResult(
            task_id=f"workflow_{workflow_id}",
            task_type=TaskType.DATA_ANALYSIS,
            success=True,
            completion_score=1.0,
            accuracy_score=1.0,
            execution_time=sum(t['duration'] for t in state_transitions),
            tokens_used={"input_tokens": 0, "output_tokens": 0},
            tool_calls=[],
            attempts=1,
            errors=[],
            timestamp=datetime.now(),
            state_transitions=state_transitions
        )
        
        monitor.record_task(task)
    
    # 상태별 통계 분석
    print("📊 상태별 성능 통계:\n")
    
    for state, durations in sorted(all_state_durations.items()):
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        
        print(f"  [{state}]")
        print(f"    • 평균 소요 시간: {avg_duration:.3f}s")
        print(f"    • 범위: {min_duration:.3f}s ~ {max_duration:.3f}s")
        print(f"    • 발생 횟수: {len(durations)}회")
        print()
    
    # 병목 상태 식별
    slowest_state = max(all_state_durations.items(), 
                       key=lambda x: sum(x[1]) / len(x[1]))
    
    print(f"🐌 병목 상태: {slowest_state[0]}")
    print(f"   평균 {sum(slowest_state[1]) / len(slowest_state[1]):.3f}s 소요")
    
    return monitor


def main():
    """메인 실행 함수"""
    print("\n" + "=" * 80)
    print("  Level 1 Foundation: State Transitions 추적")
    print("  Agent Evaluator v0.5.0")
    print("=" * 80)
    
    # 1. 기본 상태 전이
    task1 = demo_basic_state_transitions()
    
    # 2. 실패 및 재시도
    task2 = demo_fsm_with_failures()
    
    # 3. 다단계 승인 워크플로우
    task3 = demo_approval_workflow()
    
    # 4. 비정상 전이 탐지
    task4 = demo_abnormal_transitions()
    
    # 5. 상태별 메트릭 분석
    monitor = demo_state_metrics_analysis()

    # 최종 요약
    print_section("🎉 데모 완료")
    print("State Transitions 추적 방법을 모두 학습했습니다:")
    print("  ✓ 1. 기본 상태 전이 추적 (주문 처리)")
    print("  ✓ 2. 실패 및 재시도 처리 (결제 처리)")
    print("  ✓ 3. 다단계 승인 워크플로우 (구매 승인)")
    print("  ✓ 4. 비정상 전이 탐지 (규칙 기반 검증)")
    print("  ✓ 5. 상태별 메트릭 분석 (병목 지점 발견)")
    
    print("\n💡 State Transitions 활용:")
    print("   • FSM (Finite State Machine) Agent 추적")
    print("   • 비즈니스 프로세스 자동화 모니터링")
    print("   • 승인 워크플로우 분석")
    print("   • 비정상 상태 전이 감지")
    print("   • 상태별 성능 병목 지점 식별")
    
    print("\n다음 단계:")
    print("  → state_transitions를 Agent 워크플로우에 통합")
    print("  → 상태 전이 규칙 정의 및 검증")
    print("  → 병목 상태 최적화")
    print("  → Dashboard에서 상태 전이 시각화")


if __name__ == "__main__":
    main()
