#!/usr/bin/env python3
"""
Level 1 Foundation - Example 07: 대화 및 상태 전이 추적
=======================================================

🎯 목표: TaskResult 고급 필드로 복잡한 Agent 동작 추적

📚 학습 내용:
1. conversation_turns - 대화형 Agent의 턴별 대화 기록 추적
2. state_transitions - 상태 기반 워크플로우의 전이 추적
3. agent_interactions - 멀티 Agent 상호작용 상세 로그

💡 사용 시기:
- 채팅봇, 대화형 AI 개발 및 디버깅
- Finite State Machine (FSM) 기반 워크플로우 추적
- 멀티 Agent 시스템의 상호작용 분석 및 디버깅
- 복잡한 Agent 동작의 투명성 확보

⏱️ 예상 소요 시간: 25분
💰 비용: 무료 (Layer 1만 사용)

실행 방법:
    python level_1_foundation/07_conversation_state_tracking.py
"""

from datetime import datetime
from agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TaskType
)

FILE_PREFIX = "[L1-07]_"


def main():
    """대화 및 상태 전이 추적 - TaskResult 고급 필드 활용"""

    print("=" * 80)
    print("🎯 Level 1 Foundation - 대화 및 상태 전이 추적")
    print("=" * 80)
    print("TaskResult 고급 필드로 복잡한 Agent 동작을 추적합니다.")
    print("")

    # Monitor 생성
    monitor = PerformanceMonitor()


    # ============================================================================
    # 1. conversation_turns - 대화형 Agent 추적
    # ============================================================================
    print("\n" + "=" * 80)
    print("💬 1/3: conversation_turns - 대화형 Agent 추적")
    print("=" * 80)
    print("목적: 채팅봇, 대화형 AI의 턴별 대화 기록 추적")
    print("")

    # 시나리오: 고객 지원 챗봇
    conversation_turns_1 = [
        {
            "turn": 1,
            "role": "user",
            "content": "환불 정책이 어떻게 되나요?",
            "timestamp": datetime.now().isoformat()
        },
        {
            "turn": 2,
            "role": "agent",
            "content": "구매일로부터 30일 이내 환불이 가능합니다. 주문번호를 알려주시겠어요?",
            "timestamp": datetime.now().isoformat(),
            "intent": "request_info",
            "confidence": 0.95
        },
        {
            "turn": 3,
            "role": "user",
            "content": "주문번호는 12345입니다.",
            "timestamp": datetime.now().isoformat()
        },
        {
            "turn": 4,
            "role": "agent",
            "content": "주문번호 12345를 확인했습니다. 환불 처리를 시작하겠습니다.",
            "timestamp": datetime.now().isoformat(),
            "intent": "process_refund",
            "confidence": 0.98,
            "tool_calls": [
                {"tool": "database_query", "success": True},
                {"tool": "refund_processor", "success": True}
            ]
        }
    ]

    task_chatbot = TaskResult(
        task_id="chatbot_001",
        task_type=TaskType.QA.value,  # Conversational QA
        success=True,
        completion_score=1.0,
        accuracy_score=0.95,
        execution_time=15.2,
        tokens_used={"input": 150, "output": 120, "total": 270},
        tool_calls=[
            {"name": "database_query", "success": True, "duration": 0.5},
            {"name": "refund_processor", "success": True, "duration": 1.2}
        ],
        attempts=1,
        errors=[],
        conversation_turns=conversation_turns_1,  # 🆕 대화 턴 추적
        timestamp=datetime.now()
    )

    monitor.record_task(task_chatbot)

    print("✅ 대화형 Agent 추적 결과:")
    print(f"  Task ID: {task_chatbot.task_id}")
    print(f"  총 대화 턴: {len(conversation_turns_1)}턴")
    print(f"  대화 시간: {task_chatbot.execution_time:.1f}초")
    print("")
    print("  대화 흐름:")
    for turn in conversation_turns_1:
        role_icon = "👤" if turn["role"] == "user" else "🤖"
        print(f"    {role_icon} Turn {turn['turn']} ({turn['role']}): {turn['content'][:50]}...")

    print("\n💡 활용 방법:")
    print("  → 대화 흐름 분석으로 사용자 경험 개선")
    print("  → Intent 분류 정확도 모니터링")
    print("  → 대화 이탈 지점 파악 (예: 4턴 이상 걸리는 작업)")
    print("  → Tool 호출 시점과 대화 컨텍스트 연결")


    # ============================================================================
    # 2. state_transitions - 상태 기반 워크플로우 추적
    # ============================================================================
    print("\n" + "=" * 80)
    print("🔄 2/3: state_transitions - 상태 기반 워크플로우 추적")
    print("=" * 80)
    print("목적: FSM, 상태 머신 기반 Agent의 상태 전이 추적")
    print("")

    # 시나리오: 주문 처리 워크플로우 (FSM)
    state_transitions_1 = [
        {
            "from_state": "INITIAL",
            "to_state": "VALIDATING_ORDER",
            "trigger": "order_received",
            "timestamp": datetime.now().isoformat(),
            "data": {"order_id": "ORD-12345"}
        },
        {
            "from_state": "VALIDATING_ORDER",
            "to_state": "CHECKING_INVENTORY",
            "trigger": "validation_passed",
            "timestamp": datetime.now().isoformat(),
            "data": {"items": 3, "total": 150000}
        },
        {
            "from_state": "CHECKING_INVENTORY",
            "to_state": "PROCESSING_PAYMENT",
            "trigger": "inventory_available",
            "timestamp": datetime.now().isoformat(),
            "data": {"warehouse": "Seoul-01"}
        },
        {
            "from_state": "PROCESSING_PAYMENT",
            "to_state": "CONFIRMING_ORDER",
            "trigger": "payment_success",
            "timestamp": datetime.now().isoformat(),
            "data": {"transaction_id": "TXN-98765"}
        },
        {
            "from_state": "CONFIRMING_ORDER",
            "to_state": "COMPLETED",
            "trigger": "order_confirmed",
            "timestamp": datetime.now().isoformat(),
            "data": {"confirmation_number": "CONF-55555"}
        }
    ]

    task_workflow = TaskResult(
        task_id="workflow_001",
        task_type=TaskType.PLANNING.value,  # Workflow execution
        success=True,
        completion_score=1.0,
        accuracy_score=1.0,
        execution_time=8.5,
        tokens_used={"input": 200, "output": 100, "total": 300},
        tool_calls=[
            {"name": "validate_order", "success": True, "duration": 0.5},
            {"name": "check_inventory", "success": True, "duration": 1.2},
            {"name": "process_payment", "success": True, "duration": 3.5},
            {"name": "send_confirmation", "success": True, "duration": 0.8}
        ],
        attempts=1,
        errors=[],
        state_transitions=state_transitions_1,  # 🆕 상태 전이 추적
        timestamp=datetime.now()
    )

    monitor.record_task(task_workflow)

    print("✅ 상태 기반 워크플로우 추적 결과:")
    print(f"  Task ID: {task_workflow.task_id}")
    print(f"  총 상태 전이: {len(state_transitions_1)}회")
    print(f"  실행 시간: {task_workflow.execution_time:.1f}초")
    print("")
    print("  상태 전이 흐름:")
    for i, trans in enumerate(state_transitions_1, 1):
        print(f"    {i}. {trans['from_state']} → {trans['to_state']}")
        print(f"       Trigger: {trans['trigger']}")
        print(f"       Data: {trans['data']}")

    print("\n💡 활용 방법:")
    print("  → 상태 전이 경로 분석으로 워크플로우 최적화")
    print("  → 병목 상태 식별 (예: PROCESSING_PAYMENT에서 오래 걸림)")
    print("  → 비정상 전이 탐지 (예: 건너뛴 상태, 순환)")
    print("  → 상태별 성공률 모니터링")


    # 실패 케이스: 상태 전이 중 실패
    state_transitions_2 = [
        {
            "from_state": "INITIAL",
            "to_state": "VALIDATING_ORDER",
            "trigger": "order_received",
            "timestamp": datetime.now().isoformat()
        },
        {
            "from_state": "VALIDATING_ORDER",
            "to_state": "CHECKING_INVENTORY",
            "trigger": "validation_passed",
            "timestamp": datetime.now().isoformat()
        },
        {
            "from_state": "CHECKING_INVENTORY",
            "to_state": "ERROR",
            "trigger": "inventory_unavailable",
            "timestamp": datetime.now().isoformat(),
            "data": {"error": "Out of stock"}
        }
    ]

    task_workflow_fail = TaskResult(
        task_id="workflow_002",
        task_type=TaskType.PLANNING.value,  # Workflow execution
        success=False,
        completion_score=0.6,  # 부분 완료
        accuracy_score=0.0,
        execution_time=2.3,
        tokens_used={"input": 100, "output": 50, "total": 150},
        tool_calls=[
            {"name": "validate_order", "success": True, "duration": 0.5},
            {"name": "check_inventory", "success": False, "duration": 1.0}
        ],
        attempts=1,
        errors=["Inventory check failed: Out of stock"],
        state_transitions=state_transitions_2,  # 🆕 실패 시 상태 전이
        timestamp=datetime.now()
    )

    monitor.record_task(task_workflow_fail)

    print("\n  실패 케이스:")
    print(f"  Task ID: {task_workflow_fail.task_id}")
    print(f"  최종 상태: ERROR")
    print(f"  실패 원인: {task_workflow_fail.errors[0]}")
    print("  → 상태 전이 기록으로 정확한 실패 지점 파악 가능")


    # ============================================================================
    # 3. agent_interactions - 멀티 Agent 상호작용 추적
    # ============================================================================
    print("\n" + "=" * 80)
    print("🤝 3/3: agent_interactions - 멀티 Agent 상호작용 추적")
    print("=" * 80)
    print("목적: 멀티 Agent 시스템의 상호작용 상세 로그")
    print("")

    # 시나리오: CrewAI 스타일 멀티 Agent 협업
    agent_interactions_1 = [
        {
            "interaction_id": "int_001",
            "from_agent": "researcher",
            "to_agent": "analyst",
            "message_type": "data_request",
            "content": "시장 조사 데이터가 필요합니다.",
            "timestamp": datetime.now().isoformat()
        },
        {
            "interaction_id": "int_002",
            "from_agent": "analyst",
            "to_agent": "researcher",
            "message_type": "data_response",
            "content": "2024년 시장 규모 데이터를 전달합니다.",
            "timestamp": datetime.now().isoformat(),
            "data": {"market_size": "10B", "growth_rate": "15%"}
        },
        {
            "interaction_id": "int_003",
            "from_agent": "researcher",
            "to_agent": "writer",
            "message_type": "task_delegation",
            "content": "분석 결과를 기반으로 리포트를 작성해주세요.",
            "timestamp": datetime.now().isoformat(),
            "data": {"analysis": "positive_trend"}
        },
        {
            "interaction_id": "int_004",
            "from_agent": "writer",
            "to_agent": "reviewer",
            "message_type": "review_request",
            "content": "리포트 초안을 검토해주세요.",
            "timestamp": datetime.now().isoformat()
        },
        {
            "interaction_id": "int_005",
            "from_agent": "reviewer",
            "to_agent": "writer",
            "message_type": "feedback",
            "content": "몇 가지 수정 사항이 있습니다.",
            "timestamp": datetime.now().isoformat(),
            "data": {"revisions_needed": 3}
        },
        {
            "interaction_id": "int_006",
            "from_agent": "writer",
            "to_agent": "coordinator",
            "message_type": "task_complete",
            "content": "최종 리포트가 완성되었습니다.",
            "timestamp": datetime.now().isoformat()
        }
    ]

    task_multiagent = TaskResult(
        task_id="multiagent_001",
        task_type=TaskType.TOOL_USE.value,  # Multi-agent coordination
        success=True,
        completion_score=1.0,
        accuracy_score=0.92,
        execution_time=45.5,
        tokens_used={"input": 1500, "output": 800, "total": 2300},
        tool_calls=[
            {"name": "web_search", "success": True, "duration": 5.2},
            {"name": "data_analysis", "success": True, "duration": 12.5},
            {"name": "document_generation", "success": True, "duration": 8.3}
        ],
        attempts=1,
        errors=[],
        agent_interactions=agent_interactions_1,  # 🆕 Agent 간 상호작용 추적
        timestamp=datetime.now()
    )

    monitor.record_task(task_multiagent)

    print("✅ 멀티 Agent 상호작용 추적 결과:")
    print(f"  Task ID: {task_multiagent.task_id}")
    print(f"  총 상호작용: {len(agent_interactions_1)}회")
    print(f"  실행 시간: {task_multiagent.execution_time:.1f}초")
    print("")
    print("  Agent 간 상호작용 흐름:")

    # Agent 참여 통계
    agents = set()
    for inter in agent_interactions_1:
        agents.add(inter["from_agent"])
        agents.add(inter["to_agent"])

    print(f"\n  참여 Agent: {len(agents)}개")
    for agent in sorted(agents):
        sent = sum(1 for i in agent_interactions_1 if i["from_agent"] == agent)
        received = sum(1 for i in agent_interactions_1 if i["to_agent"] == agent)
        print(f"    - {agent}: 송신 {sent}회, 수신 {received}회")

    print("\n  상호작용 타입:")
    msg_types = {}
    for inter in agent_interactions_1:
        msg_type = inter["message_type"]
        msg_types[msg_type] = msg_types.get(msg_type, 0) + 1

    for msg_type, count in sorted(msg_types.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {msg_type}: {count}회")

    print("\n💡 활용 방법:")
    print("  → Agent 간 협업 패턴 분석 (Hub, Chain, Mesh)")
    print("  → 병목 Agent 식별 (특정 Agent에 요청이 집중)")
    print("  → 불필요한 상호작용 제거 (중복 요청, 순환 참조)")
    print("  → Agent 역할 최적화 (과부하 Agent 분담)")


    # ============================================================================
    # 종합 분석: 3가지 필드 활용
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 종합 분석: 고급 필드 통합 활용")
    print("=" * 80)

    # 복잡한 시나리오: 대화 + 상태 전이 + 멀티 Agent
    # 예: 고객이 챗봇과 대화하면서 주문 처리 워크플로우가 실행되고,
    #     내부적으로 여러 Agent가 협업하는 경우

    complex_scenario = TaskResult(
        task_id="complex_001",
        task_type=TaskType.TOOL_USE.value,  # Multi-agent coordination
        success=True,
        completion_score=1.0,
        accuracy_score=0.95,
        execution_time=35.2,
        tokens_used={"input": 1000, "output": 600, "total": 1600},
        tool_calls=[
            {"name": "order_validator", "success": True, "duration": 0.5},
            {"name": "inventory_checker", "success": True, "duration": 1.2},
            {"name": "payment_processor", "success": True, "duration": 3.5}
        ],
        attempts=1,
        errors=[],
        # 3가지 고급 필드를 모두 활용
        conversation_turns=[
            {"turn": 1, "role": "user", "content": "주문하고 싶습니다."},
            {"turn": 2, "role": "agent", "content": "네, 도와드리겠습니다. 상품을 선택해주세요."}
        ],
        state_transitions=[
            {"from_state": "INITIAL", "to_state": "ORDER_TAKING", "trigger": "user_intent_detected"},
            {"from_state": "ORDER_TAKING", "to_state": "PROCESSING", "trigger": "items_selected"},
            {"from_state": "PROCESSING", "to_state": "COMPLETED", "trigger": "payment_confirmed"}
        ],
        agent_interactions=[
            {"from_agent": "chatbot", "to_agent": "order_processor", "message_type": "task_delegation"},
            {"from_agent": "order_processor", "to_agent": "payment_agent", "message_type": "payment_request"},
            {"from_agent": "payment_agent", "to_agent": "chatbot", "message_type": "confirmation"}
        ],
        timestamp=datetime.now()
    )

    monitor.record_task(complex_scenario)

    print("\n✅ 복잡한 시나리오 추적 결과:")
    print(f"  Task ID: {complex_scenario.task_id}")
    print(f"  대화 턴: {len(complex_scenario.conversation_turns)}턴")
    print(f"  상태 전이: {len(complex_scenario.state_transitions)}회")
    print(f"  Agent 상호작용: {len(complex_scenario.agent_interactions)}회")
    print(f"  실행 시간: {complex_scenario.execution_time:.1f}초")

    print("\n💡 통합 활용 이점:")
    print("  → 사용자 대화 → 내부 상태 전이 → Agent 협업을 연결하여 전체 플로우 파악")
    print("  → End-to-End 디버깅 가능 (어느 지점에서 문제가 발생했는지 정확히 파악)")
    print("  → 성능 병목 지점 식별 (대화, 상태, Agent 중 어디가 느린지)")


    # ============================================================================
    # 종합 요약
    # ============================================================================
    print("\n" + "=" * 80)
    print("🎉 대화 및 상태 전이 추적 완료!")
    print("=" * 80)

    print("\n📊 학습한 고급 필드 요약:")
    print("-" * 80)
    print("1. conversation_turns - 대화형 Agent")
    print("   → 채팅봇, 대화형 AI의 턴별 대화 기록")
    print("   → Intent, Confidence, Tool 호출 시점 추적")
    print("   → 대화 이탈 지점 파악")
    print("")
    print("2. state_transitions - 상태 기반 워크플로우")
    print("   → FSM, 상태 머신의 전이 경로 추적")
    print("   → 병목 상태, 비정상 전이 탐지")
    print("   → 상태별 성공률 모니터링")
    print("")
    print("3. agent_interactions - 멀티 Agent 상호작용")
    print("   → Agent 간 메시지 전달 추적")
    print("   → 협업 패턴 분석 (Hub, Chain, Mesh)")
    print("   → 병목 Agent, 불필요한 상호작용 식별")

    print("\n💡 프로덕션 활용:")
    print("-" * 80)
    print("✓ 복잡한 Agent 시스템의 투명성 확보")
    print("✓ 디버깅 시간 단축 (정확한 문제 지점 파악)")
    print("✓ 사용자 경험 개선 (대화 흐름 최적화)")
    print("✓ Agent 협업 최적화 (불필요한 상호작용 제거)")

    print("\n✅ 다음 예제:")
    print("   Level 2 - 08_advanced_workflow_analysis.py → 워크플로우 Critical Path 분석")


if __name__ == "__main__":
    main()
