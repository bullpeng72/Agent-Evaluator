#!/usr/bin/env python3
"""
Level 1 Foundation - Example 08: 새로운 고급 API 빠른 시작
==========================================================

🎯 목표: 새로 구현된 7가지 고급 API 메서드를 빠르게 시작하기

📚 이 예제에서 다루는 새로운 API들:
1. HallucinationDetector.get_hallucination_by_type() - 환각 유형별 상세 분석
2. ResponseQualityEvaluator.get_quality_by_dimension() - 품질 차원별 상세 분석
3. LatencyTracker.get_latency_by_type() - Task 타입별 지연시간 분석
4. TokenEconomyTracker.get_cost_breakdown_by_model() - 모델별 비용 분해
5. ToolCallAnalyzer.get_tool_usage_patterns() - 도구 사용 패턴 분석
6. WorkflowExecutionTracker.get_critical_path_analysis() - Critical Path 분석
7. AgentCoordinationTracker.get_interaction_patterns() - 상호작용 패턴 분석

💡 사용 시기:
- 더 깊이 있는 성능 분석이 필요할 때
- 세밀한 비용 최적화를 원할 때
- 병목 지점을 정확히 파악하고 싶을 때
- 멀티 에이전트 협업 패턴을 이해하고 싶을 때

⏱️ 예상 소요 시간: 15분
💰 비용: 무료 (Layer 1 & 2만 사용)

실행 방법:
    python level_1_foundation/08_new_advanced_apis_quickstart.py
"""

from agent_evaluator import (
    PerformanceMonitor,
    TaskType
)

FILE_PREFIX = "[L1-08]_"


def example_1_hallucination_by_type(monitor):
    """예제 1: 환각 유형별 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 1: 환각 유형별 상세 분석")
    print("=" * 70)

    # 다양한 환각 유형을 포함하는 테스트 케이스
    test_cases = [
        # 숫자 오류
        {
            "response": "서울의 인구는 2천만 명입니다.",
            "context": "서울의 인구는 약 1천만 명입니다.",
            "truth": "서울 인구: 약 1천만 명"
        },
        # 시간 오류
        {
            "response": "한국 전쟁은 1960년에 발발했습니다.",
            "context": "한국 전쟁은 1950년에 발발했습니다.",
            "truth": "한국 전쟁: 1950년"
        },
        # 검증되지 않은 주장
        {
            "response": "이 제품은 100% 효과가 보장되며 부작용이 전혀 없습니다.",
            "context": "제품은 일부 사용자에게 효과가 있었습니다.",
            "truth": "일부 사용자에게 효과"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        monitor.hallucination_detector.detect_hallucination(
            task_id=f"task_{i}",
            response=case["response"],
            context=case["context"],
            ground_truth=case["truth"]
        )

    # 🎯 새로운 고급 API 사용!
    breakdown = monitor.hallucination_detector.get_hallucination_by_type()

    print(f"\n✓ 환각 유형별 통계:")
    print(f"  • 총 환각 수: {breakdown['total_hallucinations']}")
    print(f"  • 검증되지 않은 주장: {breakdown['unsupported_claims']}개")
    print(f"  • 숫자 오류: {breakdown['numerical_errors']}개")
    print(f"  • 시간 오류: {breakdown['temporal_errors']}개")
    print(f"  • 환각 비율: {breakdown['hallucination_rate']:.1f}%")

    print(f"\n  심각도별:")
    for severity, count in breakdown['by_severity'].items():
        print(f"    - {severity}: {count}건")

    print(f"\n💡 실전 활용:")
    print(f"  • 숫자 오류가 많으면 → 프롬프트에 '정확한 수치 사용' 명시")
    print(f"  • 시간 오류가 많으면 → 시간 정보 검증 로직 강화")
    print(f"  • 검증되지 않은 주장이 많으면 → 근거 제시 요구 추가")


def example_2_quality_by_dimension(monitor):
    """예제 2: 품질 차원별 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 2: 품질 차원별 상세 분석")
    print("=" * 70)

    # 다양한 품질 수준의 응답
    responses = [
        {
            "response": "AI는 인공지능을 의미하며, 컴퓨터가 인간처럼 학습하고 판단할 수 있게 하는 기술입니다.",
            "request": "AI가 뭔가요?",
            "elements": ["정의", "설명", "예시"]
        },
        {
            "response": "컴퓨터 관련된 거예요.",
            "request": "AI가 뭔가요?",
            "elements": ["정의", "설명", "예시"]
        }
    ]

    for i, r in enumerate(responses, 1):
        monitor.quality_evaluator.evaluate_response(
            task_id=f"qa_{i}",
            response=r["response"],
            request=r["request"],
            expected_elements=r["elements"]
        )

    # 🎯 새로운 고급 API 사용!
    quality = monitor.quality_evaluator.get_quality_by_dimension()

    print(f"\n✓ 품질 차원별 평균 점수 (0-5점):")
    dimensions = [
        ("관련성 (Relevance)", quality['relevance']),
        ("완전성 (Completeness)", quality['completeness']),
        ("정확성 (Accuracy)", quality['accuracy']),
        ("명확성 (Clarity)", quality['clarity']),
        ("유용성 (Usefulness)", quality['usefulness'])
    ]

    for name, score in dimensions:
        emoji = "🔴" if score < 2 else "🟡" if score < 3.5 else "🟢"
        print(f"  {emoji} {name}: {score:.2f}")

    print(f"\n  총 평가 수: {quality['total_evaluations']}")

    # 가장 낮은 차원 찾기
    dim_scores = {
        'relevance': quality['relevance'],
        'completeness': quality['completeness'],
        'accuracy': quality['accuracy'],
        'clarity': quality['clarity'],
        'usefulness': quality['usefulness']
    }
    lowest = min(dim_scores.items(), key=lambda x: x[1])

    print(f"\n💡 실전 활용:")
    print(f"  • 가장 개선이 필요한 차원: {lowest[0]} ({lowest[1]:.2f})")
    print(f"  • by_dimension_detailed를 통해 각 차원의 분포와 편차 확인 가능")


def example_3_latency_by_type(monitor):
    """예제 3: Task 타입별 지연시간 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 3: Task 타입별 지연시간 분석")
    print("=" * 70)

    # 다양한 task 타입의 지연시간
    latencies = [
        (TaskType.QA, 0.8),
        (TaskType.QA, 1.1),
        (TaskType.CODE_GENERATION, 3.5),
        (TaskType.CODE_GENERATION, 4.2),
        (TaskType.REASONING, 2.3),
    ]

    for i, (task_type, latency) in enumerate(latencies, 1):
        monitor.latency_tracker.record_latency(
            task_id=f"task_{i}",
            task_type=task_type.value,
            total_time=latency,
            breakdown={"llm": latency * 0.8, "processing": latency * 0.2}
        )

    # 🎯 새로운 고급 API 사용!
    latency_breakdown = monitor.latency_tracker.get_latency_by_type()

    print(f"\n✓ Task 타입별 지연시간:")
    for task_type, stats in latency_breakdown.items():
        print(f"\n  [{task_type}]")
        print(f"    - 평균: {stats['avg']:.3f}s")
        print(f"    - P95: {stats['p95']:.3f}s")
        print(f"    - 요청 수: {stats['count']}")

    # 가장 느린 타입
    slowest = max(latency_breakdown.items(), key=lambda x: x[1]['avg'])
    fastest = min(latency_breakdown.items(), key=lambda x: x[1]['avg'])

    print(f"\n💡 실전 활용:")
    print(f"  • 가장 느린 작업: {slowest[0]} (평균 {slowest[1]['avg']:.3f}s)")
    print(f"  • 가장 빠른 작업: {fastest[0]} (평균 {fastest[1]['avg']:.3f}s)")
    print(f"  • P95, P99로 SLA 준수 여부 확인 가능")


def example_4_cost_by_model(monitor):
    """예제 4: 모델별 비용 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 4: 모델별 비용 분해")
    print("=" * 70)

    # 여러 모델 사용 시뮬레이션
    usages = [
        ("gpt-4", 2000, 1000),
        ("gpt-4", 1500, 800),
        ("gpt-3.5-turbo", 1000, 500),
        ("gpt-3.5-turbo", 800, 400),
        ("claude-3-sonnet", 1200, 600),
    ]

    for i, (model, input_tok, output_tok) in enumerate(usages, 1):
        monitor.token_tracker.track_usage(
            task_id=f"task_{i}",
            input_tokens=input_tok,
            output_tokens=output_tok,
            task_type=TaskType.QA.value,
            model=model  # ← 모델 파라미터 추가!
        )

    # 🎯 새로운 고급 API 사용!
    cost_breakdown = monitor.token_tracker.get_cost_breakdown_by_model()

    print(f"\n✓ 모델별 비용 분석:")
    total_cost = 0
    for model, stats in cost_breakdown.items():
        print(f"\n  [{model}]")
        print(f"    - 총 비용: ${stats['total_cost']:.4f}")
        print(f"    - 작업당 평균: ${stats['avg_cost_per_task']:.4f}")
        print(f"    - 총 토큰: {stats['total_tokens']:,}")
        print(f"    - 1K 토큰당: ${stats['cost_per_1k_tokens']:.4f}")
        total_cost += stats['total_cost']

    print(f"\n  💰 전체 비용: ${total_cost:.4f}")

    # 가장 비싼 모델
    most_expensive = max(cost_breakdown.items(), key=lambda x: x[1]['avg_cost_per_task'])
    cheapest = min(cost_breakdown.items(), key=lambda x: x[1]['avg_cost_per_task'])

    print(f"\n💡 실전 활용:")
    print(f"  • 작업당 가장 비싼 모델: {most_expensive[0]}")
    print(f"  • 작업당 가장 저렴한 모델: {cheapest[0]}")
    print(f"  • 단순 작업은 저렴한 모델로 전환 고려")


def example_5_tool_usage_patterns(monitor):
    """예제 5: 도구 사용 패턴 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 5: 도구 사용 패턴 분석")
    print("=" * 70)

    # 도구 사용 패턴
    executions = [
        [{"tool_name": "search", "success": True, "duration": 0.5}],
        [{"tool_name": "db", "success": True, "duration": 1.0},
         {"tool_name": "db", "success": True, "duration": 1.1}],  # 중복
        [{"tool_name": "api", "success": False, "duration": 0.3},
         {"tool_name": "api", "success": True, "duration": 0.8}],  # 실패 후 재시도
    ]

    for i, tools in enumerate(executions, 1):
        monitor.tool_analyzer.analyze_execution(
            task_id=f"task_{i}",
            tool_calls=tools
        )

    # 🎯 새로운 고급 API 사용!
    patterns = monitor.tool_analyzer.get_tool_usage_patterns()

    print(f"\n✓ 도구 사용 패턴:")
    print(f"  • 총 작업: {patterns['total_tasks']}")
    print(f"  • 총 도구 호출: {patterns['total_tool_calls']}")
    print(f"  • 평균 효율성: {patterns['pattern_analysis']['avg_efficiency']:.1f}%")
    print(f"  • 중복 있는 작업: {patterns['pattern_analysis']['tasks_with_redundancy']}")
    print(f"  • 실패 있는 작업: {patterns['pattern_analysis']['tasks_with_failures']}")

    print(f"\n  사용 분포:")
    for range_name, count in patterns['usage_distribution'].items():
        if count > 0:
            print(f"    - {range_name}: {count}개")

    print(f"\n💡 실전 활용:")
    if patterns['redundancy_impact']['total_redundant'] > 0:
        print(f"  • 중복 호출 {patterns['redundancy_impact']['total_redundant']}개 → 캐싱 고려")
    if patterns['failure_impact']['total_failed'] > 0:
        print(f"  • 실패 {patterns['failure_impact']['total_failed']}개 → 재시도 로직 강화")


def example_6_critical_path(monitor):
    """예제 6: 워크플로우 Critical Path 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 6: 워크플로우 Critical Path 분석")
    print("=" * 70)

    # 워크플로우 실행
    steps = [
        ("init", 0.2),
        ("fetch", 1.5),
        ("process", 3.0),  # 병목!
        ("validate", 0.5),
        ("finalize", 0.3),
    ]

    for i, (step_name, exec_time) in enumerate(steps):
        monitor.workflow_tracker.track_step(
            task_id="workflow_1",
            step_name=step_name,
            step_type="node",
            success=True,
            execution_time=exec_time,
            framework="langgraph"
        )

    # 🎯 새로운 고급 API 사용!
    analysis = monitor.workflow_tracker.get_critical_path_analysis()

    print(f"\n✓ Critical Path 분석:")
    print(f"  • 총 워크플로우: {analysis['total_workflows']}")
    print(f"  • 총 단계: {analysis['total_steps']}")

    print(f"\n  🚨 Top 3 병목:")
    for i, bottleneck in enumerate(analysis['bottlenecks'][:3], 1):
        print(f"    {i}. {bottleneck['step_name']}: {bottleneck['avg_time']:.3f}s")

    ws = analysis['workflow_statistics']
    print(f"\n  📊 전체 통계:")
    print(f"    - 평균 시간: {ws['avg_total_time']:.3f}s")
    print(f"    - 성공률: {ws['avg_success_rate']:.1f}%")

    print(f"\n💡 실전 활용:")
    for i, rec in enumerate(analysis['optimization_recommendations'][:2], 1):
        print(f"  {i}. {rec}")


def example_7_interaction_patterns(monitor):
    """예제 7: 에이전트 상호작용 패턴 분석"""
    print("\n" + "=" * 70)
    print("📊 예제 7: 에이전트 상호작용 패턴 분석")
    print("=" * 70)

    # Hub 패턴 (중앙 조정자)
    interactions = [
        ("coordinator", "agent_a", "delegation"),
        ("coordinator", "agent_b", "delegation"),
        ("agent_a", "coordinator", "communication"),
        ("agent_b", "coordinator", "communication"),
    ]

    for from_agent, to_agent, interaction_type in interactions:
        monitor.agent_coordination_tracker.track_interaction(
            task_id="multi_agent_1",
            from_agent=from_agent,
            to_agent=to_agent,
            interaction_type=interaction_type,
            success=True
        )

    # 🎯 새로운 고급 API 사용!
    patterns = monitor.agent_coordination_tracker.get_interaction_patterns()

    print(f"\n✓ 상호작용 패턴:")
    print(f"  • 패턴 타입: {patterns['pattern_type'].upper()}")
    print(f"  • 신뢰도: {patterns['pattern_confidence']:.1f}%")
    print(f"  • Hub 에이전트: {patterns.get('hub_agent', 'N/A')}")
    print(f"  • 성공률: {patterns['success_rate']:.1f}%")

    print(f"\n  에이전트 역할:")
    for agent, info in list(patterns['agent_roles'].items())[:3]:
        print(f"    - {agent}: {info['role']} (송신: {info['sends']}, 수신: {info['receives']})")

    pc = patterns['pattern_characteristics']
    print(f"\n  패턴 특성:")
    print(f"    {pc['description']}")

    print(f"\n💡 실전 활용:")
    print(f"  • {pc['recommendation']}")


def main():
    """메인 함수"""
    print("\n" + "=" * 80)
    print("  🎯 Level 1 Foundation - 새로운 고급 API 빠른 시작")
    print("  Agent Evaluator v0.5.0")
    print("=" * 80)

    # Monitor 생성 (모든 예제에서 공유)
    monitor = PerformanceMonitor(enable_hallucination_detection=True)

    # 각 예제 실행
    example_1_hallucination_by_type(monitor)
    example_2_quality_by_dimension(monitor)
    example_3_latency_by_type(monitor)
    example_4_cost_by_model(monitor)
    example_5_tool_usage_patterns(monitor)
    example_6_critical_path(monitor)
    example_7_interaction_patterns(monitor)

    # 결과 저장
    print("\n" + "=" * 80)
    print("💾 결과 저장")
    print("=" * 80)

    filename = f"{FILE_PREFIX}new_advanced_apis_quickstart.json"
    monitor.save_to_file(filename)
    print(f"✓ 저장 완료: {filename}")
    print(f"✓ Dashboard에서 확인 가능")

    # 마무리
    print("\n" + "=" * 80)
    print("  ✅ 모든 고급 API 예제 완료!")
    print("=" * 80)

    print("\n📚 다음 단계:")
    print("  1. level_2_advanced/08_advanced_api_methods.py")
    print("     → 더 복잡한 시나리오와 실전 활용법")
    print("  2. Dashboard에서 결과 확인")
    print("     → streamlit run Dashboard/app.py")
    print("  3. level_3_production/")
    print("     → 프로덕션 환경에서의 통합 사례")

    print("\n💡 핵심 포인트:")
    print("  • 7개의 새로운 고급 API로 더 깊이 있는 분석 가능")
    print("  • 기존 기본 메서드와 함께 사용하여 종합적인 인사이트 확보")
    print("  • 유형별/차원별 분해로 정확한 문제 진단 및 최적화")
    print("  • 결과는 JSON 파일로 저장되어 Dashboard에서 시각화 가능")


if __name__ == "__main__":
    main()
