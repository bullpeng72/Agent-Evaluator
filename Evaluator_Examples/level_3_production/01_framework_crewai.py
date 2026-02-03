#!/usr/bin/env python3
"""
Level 3 Production - Example 01: CrewAI Framework 통합
======================================================

🎯 목표: CrewAI 프레임워크와 Agent Evaluator 통합

📚 학습 내용:
1. CrewAI 기본 구조 (Agents, Tasks, Crew)
2. CrewAI Integration Module 사용
3. 멀티 에이전트 워크플로우 평가
4. Layer 1 + Layer 2 자동 수집
5. Production 환경 모니터링

🔍 평가 지표:
- Layer 1: TCR, Accuracy, Latency, Cost
- Layer 2: Tool Selection, Agent Coordination, Workflow Execution

⏱️ 예상 소요 시간: 15분
💰 비용: 무료 (Layer 1+2만 사용)

⚠️  주의사항:
- pip install crewai crewai-tools 필요
- OpenAI API 키 필요 (CrewAI 실행용)

실행 방법:
    python level_3_production/01_framework_crewai.py
"""

import os
from dotenv import load_dotenv

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L3-01]_"


def check_dependencies():
    """필수 라이브러리 확인"""
    print("=" * 70)
    print("🔍 환경 확인")
    print("=" * 70)

    # OpenAI API 키 확인
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("\n❌ OpenAI API 키가 설정되지 않았습니다.")
        print("\n설정 방법:")
        print('   OPENAI_API_KEY="your-key-here" in .env')
        return False

    print(f"✅ OpenAI API 키 확인됨: {api_key[:10]}...")

    # 라이브러리 확인
    missing_libs = []

    try:
        import crewai
        print(f"✅ crewai 설치됨")
    except ImportError:
        missing_libs.append("crewai")
        print("❌ crewai 설치 필요")

    try:
        from crewai_tools import SerperDevTool
        print(f"✅ crewai-tools 설치됨")
    except ImportError:
        missing_libs.append("crewai-tools")
        print("❌ crewai-tools 설치 필요")

    if missing_libs:
        print(f"\n❌ 다음 라이브러리를 설치하세요:")
        print(f"   pip install {' '.join(missing_libs)}")
        return False

    print("\n✅ 모든 종속성 확인 완료!")
    return True


def main():
    """CrewAI 프레임워크 통합 실습"""

    print("=" * 70)
    print("🎯 Level 3 Production - CrewAI Framework 통합")
    print("=" * 70)


    # ========================================================================
    # Step 1: 환경 확인
    # ========================================================================
    if not check_dependencies():
        print("\n⚠️  환경 설정 후 다시 실행하세요.")
        print("\n설치 명령:")
        print("   pip install crewai crewai-tools")
        return


    # ========================================================================
    # Step 2: CrewAI Integration 이해
    # ========================================================================
    print("\n" + "=" * 70)
    print("📚 Step 2: CrewAI Integration 이해")
    print("=" * 70)

    print("""
🤖 CrewAI란?
- 멀티 에이전트 협업 프레임워크
- Agent + Task + Tool + Crew 구조
- 역할 기반 에이전트 (Researcher, Writer, Analyst 등)
- 순차/병렬 실행 지원

📊 Agent Evaluator 통합 방식:

방법 1: Manual Integration (수동) ✅ 이 예제
  ├─ CrewAI Crew 실행
  ├─ 결과 수집
  ├─ Layer 2 Tracker API 호출
  └─ PerformanceMonitor.record_task()

방법 2: Auto Integration (자동)
  ├─ @track_crewai_task 데코레이터
  ├─ 자동 지표 수집
  └─ Layer 1 + Layer 2 자동 계산

🎯 자동 수집 지표:
【Layer 1】
- TCR: Task 성공/실패
- Accuracy: 출력 품질 (수동 검증 필요)
- Latency: 실행 시간
- Cost: Token 사용량

【Layer 2】
- Tool Selection: Agent별 Tool 선택
- Agent Coordination: Agent 간 협업
- Workflow Execution: 전체 워크플로우 실행
    """)


    # ========================================================================
    # Step 3: CrewAI Agents 및 Tasks 정의
    # ========================================================================
    print("\n" + "=" * 70)
    print("🤖 Step 3: CrewAI Agents 및 Tasks 정의")
    print("=" * 70)

    from crewai import Agent, Task, Crew, Process

    print("\n📝 Scenario: 기술 블로그 작성")
    print("-" * 70)

    # Agent 1: Researcher (연구원)
    researcher = Agent(
        role='Tech Researcher',
        goal='최신 기술 트렌드를 조사하고 핵심 내용을 요약',
        backstory='기술 트렌드 전문가로 10년 경력',
        verbose=True,
        allow_delegation=False
    )

    # Agent 2: Writer (작가)
    writer = Agent(
        role='Tech Writer',
        goal='조사 내용을 바탕으로 읽기 쉬운 블로그 글 작성',
        backstory='기술 블로그 전문 작가로 5년 경력',
        verbose=True,
        allow_delegation=False
    )

    # Agent 3: Editor (편집자)
    editor = Agent(
        role='Editor',
        goal='작성된 글을 검토하고 개선점 제안',
        backstory='편집 전문가로 8년 경력',
        verbose=True,
        allow_delegation=False
    )

    print("✅ 3개 Agent 정의 완료:")
    print("  1. Researcher: 조사")
    print("  2. Writer: 작성")
    print("  3. Editor: 편집")

    # Task 정의
    print("\n📝 Tasks 정의...")

    task1 = Task(
        description='AI 에이전트 평가 프레임워크에 대해 조사하고 핵심 내용 3가지를 정리하세요.',
        agent=researcher,
        expected_output='핵심 내용 3가지를 bullet point로 정리'
    )

    task2 = Task(
        description='조사 내용을 바탕으로 500자 내외의 블로그 글을 작성하세요.',
        agent=writer,
        expected_output='500자 블로그 글'
    )

    task3 = Task(
        description='작성된 글을 검토하고 개선점 2가지를 제안하세요.',
        agent=editor,
        expected_output='개선점 2가지'
    )

    print("✅ 3개 Task 정의 완료")


    # ========================================================================
    # Step 4: PerformanceMonitor 생성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 4: PerformanceMonitor 생성")
    print("=" * 70)

    from agent_evaluator import PerformanceMonitor

    monitor = PerformanceMonitor()

    print("✅ PerformanceMonitor 생성 완료")
    print("  - Layer 1 + Layer 2 활성화")


    # ========================================================================
    # Step 5: CrewAI Crew 실행 및 평가
    # ========================================================================
    print("\n" + "=" * 70)
    print("🚀 Step 5: CrewAI Crew 실행")
    print("=" * 70)

    print("\n⚠️  CrewAI 실행 중... (1-2분 소요)")
    print("   Agent들이 협업하여 블로그 글을 작성합니다.\n")

    # Crew 생성
    crew = Crew(
        agents=[researcher, writer, editor],
        tasks=[task1, task2, task3],
        process=Process.sequential,  # 순차 실행
        verbose=True
    )

    # Manual Integration 방식
    import time
    from agent_evaluator import create_taskresult

    start_time = time.time()

    try:
        # Crew 실행
        result = crew.kickoff()
        execution_time = time.time() - start_time

        print(f"\n✅ CrewAI 실행 완료! ({execution_time:.1f}초)")
        print(f"\n📄 결과:\n{result}\n")

        # TaskResult 생성 및 기록
        task_result = create_taskresult(
            task_id="crewai_001",
            task_type="creative",
            question="AI 에이전트 평가 프레임워크에 대한 블로그 글 작성",
            response=str(result),
            ground_truth="",  # Creative task는 ground_truth 불필요
            execution_time=execution_time,
            
        )

        # Layer 2 메트릭 추가 기록
        # Tool Selection: 각 Agent를 "도구"로 간주
        monitor.tool_selection_tracker.evaluate_selection(
            task_id="crewai_001",
            expected_tools=["Researcher", "Writer", "Editor"],
            actual_tools=["Researcher", "Writer", "Editor"]
        )

        # Agent Coordination: Agent 간 협업 추적
        # Researcher → Writer
        monitor.agent_coordination_tracker.track_interaction(
            task_id="crewai_001",
            from_agent="Researcher",
            to_agent="Writer",
            interaction_type="delegation",
            success=True
        )
        # Writer → Editor
        monitor.agent_coordination_tracker.track_interaction(
            task_id="crewai_001",
            from_agent="Writer",
            to_agent="Editor",
            interaction_type="delegation",
            success=True
        )

        # Workflow Execution: 각 단계 추적
        monitor.workflow_tracker.track_step(
            task_id="crewai_001",
            step_name="Research",
            step_type="agent_task",
            success=True,
            execution_time=execution_time / 3,
            framework="crewai"
        )
        monitor.workflow_tracker.track_step(
            task_id="crewai_001",
            step_name="Writing",
            step_type="agent_task",
            success=True,
            execution_time=execution_time / 3,
            framework="crewai"
        )
        monitor.workflow_tracker.track_step(
            task_id="crewai_001",
            step_name="Editing",
            step_type="agent_task",
            success=True,
            execution_time=execution_time / 3,
            framework="crewai"
        )

        # 기록
        monitor.record_task(task_result)

        print("✅ 평가 지표 기록 완료")

    except Exception as e:
        print(f"\n❌ 실행 실패: {str(e)}")
        print("\n💡 Troubleshooting:")
        print("  1. OpenAI API 키 확인")
        print("  2. API 할당량 확인")
        print("  3. 네트워크 연결 확인")
        return


    # ========================================================================
    # Step 6: 평가 결과 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 6: 평가 결과 분석")
    print("=" * 70)

    report = monitor.generate_report()

    print(f"\n【Layer 1 Metrics】")
    tcr_data = report.accuracy_metrics.get('tcr', {})
    latency_data = report.efficiency_metrics.get('latency', {})
    tokens_data = report.efficiency_metrics.get('tokens', {})
    print(f"  - TCR: {tcr_data.get('tcr', 0):.1f}%")
    print(f"  - 평균 Latency: {latency_data.get('avg', 0):.1f}초")
    print(f"  - 총 Cost: ${tokens_data.get('total_cost', 0):.4f}")

    print(f"\n【Layer 2 Metrics】")

    # Tool Selection 통계
    tool_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    if tool_stats.get('total_evaluations', 0) > 0:
        print(f"  - Tool Selection Accuracy: {tool_stats.get('avg_accuracy', 0):.1f}%")
        print(f"  - Tool Selection F1 Score: {tool_stats.get('avg_f1_score', 0):.1f}%")

    # Agent Coordination 통계
    coord_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
    if coord_stats.get('total_interactions', 0) > 0:
        print(f"  - Agent Coordination Score: {coord_stats.get('score', 0):.2f}/10")
        print(f"  - Interaction Success Rate: {coord_stats.get('success_rate', 0):.1f}%")

    # Workflow Execution 통계
    workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    if workflow_stats.get('total_steps', 0) > 0:
        print(f"  - Workflow Step Success: {workflow_stats.get('step_success_rate', 0):.1f}%")
        print(f"  - Task Completion Rate: {workflow_stats.get('task_success_rate', 0):.1f}%")


    # ========================================================================
    # Step 7: 결과 저장
    # ========================================================================
    print("\n" + "=" * 70)
    print("💾 Step 7: 결과 저장")
    print("=" * 70)

    filename = f"{FILE_PREFIX}crewai_integration_result.json"
    monitor.save_to_file(filename)

    print(f"✓ 저장 완료: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")


    # ========================================================================
    # Step 8: CrewAI Integration 모범 사례
    # ========================================================================
    print("\n" + "=" * 70)
    print("💡 Step 8: CrewAI Integration 모범 사례")
    print("=" * 70)

    print("""
🏆 Production 환경 권장 사항:

【1. Manual Integration 구현】
# Layer 2 Tracker 사용법
monitor.tool_selection_tracker.evaluate_selection(
    task_id="task_001",
    expected_tools=["search", "calculator"],
    actual_tools=["search", "calculator"]
)

monitor.agent_coordination_tracker.track_interaction(
    task_id="task_001",
    from_agent="Agent1",
    to_agent="Agent2",
    interaction_type="delegation",
    success=True
)

monitor.workflow_tracker.track_step(
    task_id="task_001",
    step_name="Step1",
    step_type="processing",
    success=True,
    execution_time=1.5,
    framework="crewai"
)

→ 각 Tracker의 정확한 API 사용

【2. Error Handling】
try:
    result = crew.kickoff()
    execution_time = time.time() - start_time

    # 성공 케이스 기록
    task_result = create_taskresult(...)
    monitor.record_task(task_result)

except Exception as e:
    # 실패 케이스도 기록
    task_result = create_taskresult(
        ...,
        success=False
    )
    monitor.record_task(task_result)

→ 실패 케이스도 기록

【3. Threshold 설정】
monitor.thresholds = {
    'tcr': 90.0,
    'latency': 60.0,  # CrewAI는 느림
    'agent_coordination': 0.8
}

→ CrewAI 특성에 맞게 조정

【4. 주기적 모니터링】
# 매 시간마다 리포트 생성
schedule.every(1).hours.do(
    lambda: monitor.save_to_file(
        f"{FILE_PREFIX}crewai_{datetime.now()}.json"
    )
)

→ Production 환경에서 지속 모니터링

【5. A/B 테스트】
# 다른 Agent 구성 비교
crew_v1 = Crew(agents=[a1, a2], ...)
crew_v2 = Crew(agents=[a1, a2, a3], ...)

monitor_v1 = PerformanceMonitor()
monitor_v2 = PerformanceMonitor()

→ 최적 구성 찾기
    """)


    # ========================================================================
    # Dashboard 확인 안내
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 CrewAI Integration 완료!")
    print("=" * 70)

    print("""
📊 Dashboard에서 확인하기:

1. Dashboard 실행:
   cd Dashboard
   streamlit run streamlit_dashboard.py

2. 파일 선택:
   → [L3-01]_crewai_integration_result.json

3. 확인할 탭:
   📊 Overview: 전체 성능
   🤖 Agentic AI: Layer 2 지표 상세
   ⚡ Performance: Latency, Cost

4. 분석 포인트:
   - Multi-Agent 협업 효율성
   - Agent별 기여도
   - 워크플로우 병목 지점
    """)

    print("\n✅ 다음 예제: 02_cost_optimization.py")
    print("   → 비용 최적화 전략")


if __name__ == "__main__":
    main()
