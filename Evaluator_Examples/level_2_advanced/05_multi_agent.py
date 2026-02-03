#!/usr/bin/env python3
"""
Level 2 Advanced - Example 05: Multi-Agent 평가
================================================

FILE_PREFIX: [L2-05]_

🎯 주제: Multi-Agent 협업 패턴 및 평가

📚 학습 내용:
1. AgentCoordinationTracker 활용
2. Agent 간 협업 패턴 (delegation, communication, collaboration)
3. 역할 분담 효율성
4. Agent 간 충돌 및 병목 현상 탐지

🔍 핵심 개념:
- Agent Interaction Types: delegation, communication, collaboration
- Coordination Score: Agent 간 협업 품질
- Success Rate: 상호작용 성공률
- Interaction Patterns: 협업 패턴 분석

실행 방법:
    python level_2_advanced/05_multi_agent.py
"""

FILE_PREFIX = "[L2-05]_"

from agent_evaluator import PerformanceMonitor, create_taskresult
import time

def main():
    print("=" * 80)
    print("🤝 Level 2 Advanced - Multi-Agent 평가")
    print("=" * 80)

    monitor = PerformanceMonitor()

    print("""
🤝 Agent Coordination Metrics:
- Coordination Score: Agent 간 협업 품질 (0-100)
- Success Rate: 상호작용 성공률
- Interaction Count: 상호작용 횟수
- Avg Interaction Time: 평균 상호작용 시간

🔄 Interaction Types:
- delegation: 작업 위임 (A → B에게 작업 전달)
- communication: 정보 교환 (A ↔ B 데이터 공유)
- collaboration: 공동 작업 (A + B 함께 작업)
    """)

    # ========================================================================
    # Part 1: Simple Delegation Chain (순차 위임)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Simple Delegation Chain - 순차적 작업 위임")
    print("=" * 80)

    print("""
시나리오: 연구 보고서 작성
1. Manager → Researcher (데이터 조사 위임)
2. Researcher → Analyst (데이터 분석 위임)
3. Analyst → Writer (보고서 작성 위임)
4. Writer → Manager (최종 보고서 전달)
    """)

    delegation_chain = [
        {
            "from": "Manager",
            "to": "Researcher",
            "type": "delegation",
            "task": "Collect market data",
            "success": True,
            "duration": 2.0
        },
        {
            "from": "Researcher",
            "to": "Analyst",
            "type": "delegation",
            "task": "Analyze collected data",
            "success": True,
            "duration": 3.0
        },
        {
            "from": "Analyst",
            "to": "Writer",
            "type": "delegation",
            "task": "Write analysis report",
            "success": True,
            "duration": 2.5
        },
        {
            "from": "Writer",
            "to": "Manager",
            "type": "delegation",
            "task": "Deliver final report",
            "success": True,
            "duration": 0.5
        }
    ]

    task_id = "delegation_chain_001"
    for i, interaction in enumerate(delegation_chain, 1):
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=interaction["success"],
            context={"step": i, "task": interaction["task"], "duration": interaction["duration"]}
        )
        print(f"  Step {i}: {interaction['from']} → {interaction['to']}")
        print(f"    Task: {interaction['task']}")
        print(f"    Duration: {interaction['duration']:.1f}s, Success: {interaction['success']}")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="multi_agent",
        question="시장 조사 보고서 작성",
        response="보고서 작성 완료",
        ground_truth="",
        execution_time=sum(i["duration"] for i in delegation_chain)
    )
    monitor.record_task(task)

    # Calculate statistics manually
    total_interactions = len(delegation_chain)
    successful = sum(1 for i in delegation_chain if i["success"])
    success_rate = (successful / total_interactions * 100) if total_interactions > 0 else 0
    total_duration = sum(i["duration"] for i in delegation_chain)
    avg_duration = total_duration / total_interactions if total_interactions > 0 else 0

    print(f"\n📊 Delegation Chain Statistics:")
    print(f"  - Total Interactions: {total_interactions}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Total Duration: {total_duration:.1f}s")
    print(f"  - Avg Interaction Time: {avg_duration:.2f}s")
    print(f"  ✓ 분석: 순차적 위임 성공 (선형 워크플로우)")

    # ========================================================================
    # Part 2: Parallel Collaboration (병렬 협업)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: Parallel Collaboration - 병렬 협업")
    print("=" * 80)

    print("""
시나리오: 웹사이트 개발 프로젝트
- Frontend Dev ↔ Backend Dev (API 설계 협의)
- Designer ↔ Frontend Dev (UI/UX 협의)
- Backend Dev ↔ DBA (데이터베이스 설계)
→ 동시 다발적 협업
    """)

    parallel_collaboration = [
        # Frontend ↔ Backend
        {
            "from": "Frontend_Dev",
            "to": "Backend_Dev",
            "type": "communication",
            "task": "Discuss API endpoints",
            "success": True,
            "duration": 1.5
        },
        {
            "from": "Backend_Dev",
            "to": "Frontend_Dev",
            "type": "communication",
            "task": "Share API documentation",
            "success": True,
            "duration": 1.0
        },
        # Designer ↔ Frontend
        {
            "from": "Designer",
            "to": "Frontend_Dev",
            "type": "collaboration",
            "task": "UI component design",
            "success": True,
            "duration": 2.0
        },
        {
            "from": "Frontend_Dev",
            "to": "Designer",
            "type": "communication",
            "task": "Implementation feedback",
            "success": True,
            "duration": 0.8
        },
        # Backend ↔ DBA
        {
            "from": "Backend_Dev",
            "to": "DBA",
            "type": "collaboration",
            "task": "Database schema design",
            "success": True,
            "duration": 2.5
        },
        {
            "from": "DBA",
            "to": "Backend_Dev",
            "type": "communication",
            "task": "Query optimization advice",
            "success": True,
            "duration": 1.2
        }
    ]

    task_id = "parallel_collab_001"
    for interaction in parallel_collaboration:
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=interaction["success"],
            context={"task": interaction["task"], "duration": interaction["duration"]}
        )

    print(f"\n상호작용 맵:")
    agents = set()
    for i in parallel_collaboration:
        agents.add(i["from"])
        agents.add(i["to"])
    print(f"  참여 Agent: {sorted(agents)}")
    print(f"  총 상호작용: {len(parallel_collaboration)}회")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="multi_agent",
        question="웹사이트 개발 협업",
        response="개발 완료",
        ground_truth="",
        execution_time=max(i["duration"] for i in parallel_collaboration)  # 병렬이므로 max
    )
    monitor.record_task(task)

    # Calculate statistics
    total_interactions = len(parallel_collaboration)
    successful = sum(1 for i in parallel_collaboration if i["success"])
    success_rate = (successful / total_interactions * 100) if total_interactions > 0 else 0

    print(f"\n📊 Parallel Collaboration Statistics:")
    print(f"  - Total Interactions: {total_interactions}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Communication: {sum(1 for i in parallel_collaboration if i['type'] == 'communication')}회")
    print(f"  - Collaboration: {sum(1 for i in parallel_collaboration if i['type'] == 'collaboration')}회")
    print(f"  ✓ 분석: 다자간 병렬 협업 성공")

    # ========================================================================
    # Part 3: Failed Interactions (실패한 협업)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Failed Interactions - 협업 실패 사례")
    print("=" * 80)

    print("""
시나리오: 충돌 및 실패가 있는 협업
- Agent 간 의견 불일치
- 통신 오류
- 작업 위임 실패
    """)

    failed_interactions = [
        {
            "from": "Agent_A",
            "to": "Agent_B",
            "type": "delegation",
            "task": "Process data",
            "success": True,
            "duration": 1.0
        },
        {
            "from": "Agent_B",
            "to": "Agent_C",
            "type": "delegation",
            "task": "Validate results",
            "success": False,  # ❌ 실패
            "duration": 2.0,
            "error": "Agent_C unavailable"
        },
        {
            "from": "Agent_A",
            "to": "Agent_C",
            "type": "delegation",
            "task": "Retry validation",
            "success": False,  # ❌ 실패
            "duration": 1.5,
            "error": "Still unavailable"
        },
        {
            "from": "Agent_A",
            "to": "Agent_D",
            "type": "delegation",
            "task": "Alternative validation",
            "success": True,  # ✓ 성공 (대체 경로)
            "duration": 1.8
        },
        {
            "from": "Agent_B",
            "to": "Agent_A",
            "type": "communication",
            "task": "Report conflict",
            "success": False,  # ❌ 통신 실패
            "duration": 0.5,
            "error": "Communication timeout"
        }
    ]

    task_id = "failed_001"
    for i, interaction in enumerate(failed_interactions, 1):
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=interaction["success"],
            context={
                "task": interaction["task"],
                "duration": interaction["duration"],
                "error": interaction.get("error", "")
            }
        )
        status = "✓" if interaction["success"] else "❌"
        print(f"  {status} Step {i}: {interaction['from']} → {interaction['to']}")
        print(f"    Task: {interaction['task']}")
        if not interaction["success"]:
            print(f"    Error: {interaction.get('error', 'Unknown')}")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="multi_agent",
        question="데이터 처리 및 검증",
        response="부분 완료 (일부 실패)",
        ground_truth="",
        execution_time=sum(i["duration"] for i in failed_interactions)
    )
    monitor.record_task(task)

    # Calculate statistics
    total_interactions = len(failed_interactions)
    successful = sum(1 for i in failed_interactions if i["success"])
    success_rate = (successful / total_interactions * 100) if total_interactions > 0 else 0
    failed_count = total_interactions - successful

    print(f"\n📊 Failed Interactions Statistics:")
    print(f"  - Total Interactions: {total_interactions}")
    print(f"  - Success Rate: {success_rate:.1f}% ⚠️")
    print(f"  - Failed Interactions: {failed_count}")
    print(f"  ⚠️ 문제:")
    print(f"    - Agent_C 가용성 문제")
    print(f"    - 통신 타임아웃")
    print(f"    - 대체 경로 필요")

    # ========================================================================
    # Part 4: Bottleneck Detection (병목 현상)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Bottleneck Detection - 병목 Agent 탐지")
    print("=" * 80)

    print("""
시나리오: Agent_Hub가 모든 요청을 처리 (병목)
- 많은 Agent가 Hub에 의존
- Hub의 과부하
    """)

    bottleneck_case = [
        # 모든 Agent가 Hub에 요청
        {"from": "Agent_1", "to": "Hub", "type": "delegation", "success": True, "duration": 0.5},
        {"from": "Agent_2", "to": "Hub", "type": "delegation", "success": True, "duration": 0.6},
        {"from": "Agent_3", "to": "Hub", "type": "delegation", "success": True, "duration": 0.7},
        {"from": "Agent_4", "to": "Hub", "type": "delegation", "success": True, "duration": 0.8},
        {"from": "Agent_5", "to": "Hub", "type": "delegation", "success": True, "duration": 0.9},
        # Hub가 점점 느려짐
        {"from": "Hub", "to": "Worker_1", "type": "delegation", "success": True, "duration": 2.0},
        {"from": "Hub", "to": "Worker_2", "type": "delegation", "success": True, "duration": 2.5},
        {"from": "Hub", "to": "Worker_3", "type": "delegation", "success": False, "duration": 3.0},  # 과부하로 실패
    ]

    task_id = "bottleneck_001"
    for interaction in bottleneck_case:
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=interaction["success"],
            context={"duration": interaction["duration"]}
        )

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="multi_agent",
        question="분산 작업 처리",
        response="부분 완료",
        ground_truth="",
        execution_time=sum(i["duration"] for i in bottleneck_case)
    )
    monitor.record_task(task)

    # Hub 관련 통계 계산
    hub_incoming = [i for i in bottleneck_case if i["to"] == "Hub"]
    hub_outgoing = [i for i in bottleneck_case if i["from"] == "Hub"]

    print(f"\n📊 Bottleneck Analysis:")
    print(f"  Hub 수신: {len(hub_incoming)}회")
    print(f"  Hub 발신: {len(hub_outgoing)}회")
    print(f"  Hub 평균 처리 시간: {sum(i['duration'] for i in hub_outgoing) / len(hub_outgoing):.2f}s")
    print(f"  Hub 실패율: {sum(1 for i in hub_outgoing if not i['success']) / len(hub_outgoing) * 100:.1f}%")
    print(f"  🚨 경고: Hub가 병목 지점!")
    print(f"     → 해결: 부하 분산, 캐싱, 비동기 처리")

    # ========================================================================
    # Part 5: Efficient Role Distribution (효율적 역할 분담)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Efficient Role Distribution - 최적 역할 분담")
    print("=" * 80)

    print("""
시나리오: 뉴스 분석 시스템
- Crawler: 뉴스 수집
- Classifier: 카테고리 분류
- Summarizer: 요약 생성
- Sentiment: 감정 분석
- Publisher: 결과 발행

→ 각자 전문 영역, 순차 + 병렬 혼합
    """)

    efficient_roles = [
        # 1단계: Crawler 수집
        {"from": "Orchestrator", "to": "Crawler", "type": "delegation", "success": True, "duration": 1.0},

        # 2단계: 병렬 처리 (Classifier, Summarizer)
        {"from": "Crawler", "to": "Classifier", "type": "delegation", "success": True, "duration": 0.8},
        {"from": "Crawler", "to": "Summarizer", "type": "delegation", "success": True, "duration": 1.2},

        # 3단계: 감정 분석 (Summarizer 결과 필요)
        {"from": "Summarizer", "to": "Sentiment", "type": "delegation", "success": True, "duration": 0.5},

        # 4단계: 결과 통합 및 발행
        {"from": "Classifier", "to": "Publisher", "type": "communication", "success": True, "duration": 0.3},
        {"from": "Sentiment", "to": "Publisher", "type": "communication", "success": True, "duration": 0.3},
        {"from": "Publisher", "to": "Orchestrator", "type": "communication", "success": True, "duration": 0.2},
    ]

    task_id = "efficient_001"
    for i, interaction in enumerate(efficient_roles, 1):
        monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=interaction["success"],
            context={"duration": interaction["duration"]}
        )

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="multi_agent",
        question="뉴스 분석 파이프라인",
        response="분석 완료",
        ground_truth="",
        execution_time=4.3  # 병렬 고려한 실제 시간
    )
    monitor.record_task(task)

    # Calculate statistics
    total_interactions = len(efficient_roles)
    successful = sum(1 for i in efficient_roles if i["success"])
    success_rate = (successful / total_interactions * 100) if total_interactions > 0 else 0

    print(f"\n📊 Efficient Role Distribution Statistics:")
    print(f"  - Total Interactions: {total_interactions}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Agents Involved: 6개")
    print(f"  - Parallel Steps: 2단계 (Classifier + Summarizer 병렬)")
    print(f"  ✓ 장점:")
    print(f"    - 명확한 역할 분담")
    print(f"    - 병렬 처리로 시간 단축")
    print(f"    - 높은 성공률")

    # ========================================================================
    # Part 6: 전체 통계 및 패턴 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 Coordination 통계")
    print("=" * 80)

    overall_score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    overall_score = overall_score_data.get('coordination_score', 0)

    print(f"\n🤝 Overall Agent Coordination Metrics:")
    print(f"  - Coordination Score: {overall_score:.1f}/100")

    # Interaction Type 분포
    print(f"\n📊 Interaction Type Distribution:")
    type_counts = {}
    total_count = 0

    # Check if interactions is a list or dict
    interactions_data = monitor.agent_coordination_tracker.interactions
    if isinstance(interactions_data, list):
        for interaction in interactions_data:
            itype = interaction.get('interaction_type', 'unknown')
            type_counts[itype] = type_counts.get(itype, 0) + 1
            total_count += 1
    elif isinstance(interactions_data, dict):
        for task_id in interactions_data:
            for interaction in interactions_data[task_id]:
                itype = interaction.get('interaction_type', 'unknown')
                type_counts[itype] = type_counts.get(itype, 0) + 1
                total_count += 1

    if type_counts:
        for itype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_count * 100) if total_count > 0 else 0
            print(f"  - {itype}: {count}회 ({percentage:.1f}%)")
    else:
        print(f"  (데이터 없음)")

    # 점수 평가
    print(f"\n🎯 Coordination Quality Assessment:")
    if overall_score >= 80:
        print(f"  ✅ 우수 (Score: {overall_score:.1f})")
        print(f"     - 높은 성공률과 효율적 협업")
    elif overall_score >= 60:
        print(f"  ⚠️ 양호 (Score: {overall_score:.1f})")
        print(f"     - 개선 가능한 영역 존재")
    else:
        print(f"  ❌ 개선 필요 (Score: {overall_score:.1f})")
        print(f"     - 실패율 높음 또는 비효율적 패턴")

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n✅ Multi-Agent Coordination Report:")
    print(f"  - Coordination Score: {overall_score:.1f}/100")
    print(f"  - Total Interactions: {total_count}")

    # 결과 저장
    filename = f"{FILE_PREFIX}multi_agent_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    print("\n" + "=" * 80)
    print("🎉 Multi-Agent 평가 학습 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ Agent Coordination Metrics (Score, Success Rate)
2. ✅ Interaction Types (delegation, communication, collaboration)
3. ✅ 협업 패턴 (순차, 병렬, 실패 처리)
4. ✅ 병목 현상 탐지 및 역할 분담

🔍 실제 활용:
- CrewAI: Agent 간 task delegation
- LangGraph: Node 간 상태 전달
- AutoGen: Agent conversation patterns

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py
  → {filename} 선택
  → Layer 2 Metrics 탭에서 Agent Coordination 상세 확인

🚀 다음 단계:
  level_2_advanced/06_workflow.py: Workflow 실행 패턴 학습
    """)

if __name__ == "__main__":
    main()
