#!/usr/bin/env python3
"""
Level 2 Advanced: 새로 구현된 7개 고급 API 메서드 활용

이 예제는 Agent Evaluator v0.5.0에서 새로 구현된 고급 분석 API를 활용하는 방법을 보여줍니다.

다루는 고급 API:
1. HallucinationDetector.get_hallucination_by_type() - 환각 유형별 통계
2. ResponseQualityEvaluator.get_quality_by_dimension() - 품질 차원별 분포
3. LatencyTracker.get_latency_by_type() - Task 타입별 지연시간
4. TokenEconomyTracker.get_cost_breakdown_by_model() - 모델별 비용 분해
5. ToolCallAnalyzer.get_tool_usage_patterns() - 도구 사용 패턴
6. WorkflowExecutionTracker.get_critical_path_analysis() - Critical Path 분석
7. AgentCoordinationTracker.get_interaction_patterns() - 상호작용 패턴

실행 방법:
    python level_2_advanced/08_advanced_api_methods.py
"""

import sys
from pathlib import Path
import json

# Add agent_evaluator to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_evaluator import (
    PerformanceMonitor,
    TaskType,
    TaskResult
)

FILE_PREFIX = "[L2-08]_"


def print_section(title):
    """Print a section header"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def demo_hallucination_by_type():
    """Demo 1: 환각 유형별 세부 분석"""
    print_section("1. HallucinationDetector.get_hallucination_by_type()")

    evaluator = PerformanceMonitor()

    # 여러 종류의 환각을 포함한 응답들
    test_cases = [
        {
            "task_id": "medical_query_1",
            "response": "The patient has a temperature of 105°F and should take 5000mg of aspirin.",
            "context": "Normal body temperature is 98.6°F. Safe aspirin dose is 325-650mg.",
            "ground_truth": "Normal temperature: 98.6°F, Safe aspirin: 325-650mg"
        },
        {
            "task_id": "historical_query_1",
            "response": "The moon landing happened in 1975 by Neil Armstrong.",
            "context": "Apollo 11 mission landed on the moon in 1969.",
            "ground_truth": "Moon landing: 1969"
        },
        {
            "task_id": "factual_query_1",
            "response": "Python was invented by Guido van Rossum in 1989 and first released in 1991.",
            "context": "Python is a high-level programming language created by Guido van Rossum.",
            "ground_truth": "Python created in 1991"
        }
    ]

    for case in test_cases:
        evaluator.hallucination_detector.detect_hallucination(
            task_id=case["task_id"],
            response=case["response"],
            context=case["context"],
            ground_truth=case["ground_truth"]
        )

    # 🎯 새로운 고급 API 사용
    hallucination_breakdown = evaluator.hallucination_detector.get_hallucination_by_type()

    print("✓ 환각 유형별 통계:")
    print(f"  • 전체 환각 수: {hallucination_breakdown['total_hallucinations']}")
    print(f"  • 검증되지 않은 주장: {hallucination_breakdown['unsupported_claims']}")
    print(f"  • 숫자 오류: {hallucination_breakdown['numerical_errors']}")
    print(f"  • 시간 오류: {hallucination_breakdown['temporal_errors']}")
    print(f"  • 기타 오류: {hallucination_breakdown['other_errors']}")
    print(f"  • 환각 비율: {hallucination_breakdown['hallucination_rate']}%")

    print("\n  심각도별 분포:")
    for severity, count in hallucination_breakdown['by_severity'].items():
        print(f"    - {severity}: {count}건")

    print(f"\n  평균 환각/검출: {hallucination_breakdown['avg_per_detection']}")

    # 💡 활용 팁
    print("\n💡 활용 팁:")
    if hallucination_breakdown['numerical_errors'] > 0:
        print("  ⚠️  숫자 오류가 발견되었습니다. 프롬프트에 '정확한 숫자 사용' 지시 추가를 권장합니다.")
    if hallucination_breakdown['temporal_errors'] > 0:
        print("  ⚠️  시간 오류가 발견되었습니다. 시간 정보에 대한 사실 확인 강화가 필요합니다.")

    return evaluator


def demo_quality_by_dimension(evaluator):
    """Demo 2: 품질 차원별 상세 분석"""
    print_section("2. ResponseQualityEvaluator.get_quality_by_dimension()")

    # 다양한 품질 수준의 응답들
    test_cases = [
        {
            "task_id": "qa_1",
            "response": "Machine learning is a subset of AI that enables computers to learn from data.",
            "request": "What is machine learning?",
            "expected_elements": ["definition", "AI relationship", "learning concept"],
            "ground_truth": "Machine learning is a method of data analysis that automates analytical model building."
        },
        {
            "task_id": "qa_2",
            "response": "It's about computers.",
            "request": "What is machine learning?",
            "expected_elements": ["definition", "AI relationship", "learning concept"]
        },
        {
            "task_id": "qa_3",
            "response": "Machine learning is a powerful AI technique that allows computers to learn patterns from data without explicit programming. It's widely used in various applications.",
            "request": "What is machine learning?",
            "expected_elements": ["definition", "AI relationship", "learning concept"],
            "ground_truth": "Machine learning is a method of data analysis that automates analytical model building."
        }
    ]

    for case in test_cases:
        evaluator.quality_evaluator.evaluate_response(
            task_id=case["task_id"],
            response=case["response"],
            request=case["request"],
            expected_elements=case["expected_elements"],
            ground_truth=case.get("ground_truth")
        )

    # 🎯 새로운 고급 API 사용
    quality_breakdown = evaluator.quality_evaluator.get_quality_by_dimension()

    print("✓ 품질 차원별 평균 점수 (0-5점):")
    print(f"  • Relevance (관련성): {quality_breakdown['relevance']:.2f}")
    print(f"  • Completeness (완전성): {quality_breakdown['completeness']:.2f}")
    print(f"  • Accuracy (정확성): {quality_breakdown['accuracy']:.2f}")
    print(f"  • Clarity (명확성): {quality_breakdown['clarity']:.2f}")
    print(f"  • Usefulness (유용성): {quality_breakdown['usefulness']:.2f}")

    print(f"\n  총 평가 수: {quality_breakdown['total_evaluations']}")

    # 차원별 상세 통계
    print("\n  차원별 상세 통계:")
    for dimension, stats in quality_breakdown['by_dimension_detailed'].items():
        print(f"\n  [{dimension}]")
        print(f"    - 평균: {stats['average']:.2f}")
        print(f"    - 중앙값: {stats['median']:.2f}")
        print(f"    - 범위: {stats['min']:.2f} ~ {stats['max']:.2f}")
        print(f"    - 표준편차: {stats['std']:.2f}")

        # 분포 정보
        print(f"    - 점수 분포:")
        for score_range, count in stats['distribution'].items():
            if count > 0:
                print(f"      {score_range}점: {count}건")

    # 💡 개선 권장사항
    print("\n💡 개선 권장사항:")
    dimensions = {
        'relevance': '관련성',
        'completeness': '완전성',
        'accuracy': '정확성',
        'clarity': '명확성',
        'usefulness': '유용성'
    }

    for dim, name in dimensions.items():
        score = quality_breakdown[dim]
        if score < 2.0:
            print(f"  🔴 {name} 점수가 낮습니다 ({score:.2f}). 즉각적인 개선이 필요합니다.")
        elif score < 3.0:
            print(f"  🟡 {name} 점수가 보통입니다 ({score:.2f}). 개선을 권장합니다.")


def demo_latency_by_type(evaluator):
    """Demo 3: Task 타입별 지연시간 분석"""
    print_section("3. LatencyTracker.get_latency_by_type()")

    # 다양한 task 타입의 지연시간 시뮬레이션
    latency_data = [
        # QA tasks
        (TaskType.QA, 0.8, {"llm": 0.6, "processing": 0.2}),
        (TaskType.QA, 1.2, {"llm": 0.9, "processing": 0.3}),
        (TaskType.QA, 1.0, {"llm": 0.7, "processing": 0.3}),

        # Code generation tasks (더 오래 걸림)
        (TaskType.CODE_GENERATION, 3.5, {"llm": 2.8, "processing": 0.7}),
        (TaskType.CODE_GENERATION, 4.2, {"llm": 3.3, "processing": 0.9}),
        (TaskType.CODE_GENERATION, 3.8, {"llm": 3.0, "processing": 0.8}),

        # Data analysis tasks
        (TaskType.DATA_ANALYSIS, 2.1, {"llm": 1.5, "processing": 0.6}),
        (TaskType.DATA_ANALYSIS, 2.5, {"llm": 1.8, "processing": 0.7}),

        # Reasoning tasks
        (TaskType.REASONING, 2.8, {"llm": 2.2, "processing": 0.6}),
        (TaskType.REASONING, 3.1, {"llm": 2.4, "processing": 0.7}),
    ]

    for i, (task_type, total_time, breakdown) in enumerate(latency_data):
        evaluator.latency_tracker.record_latency(
            task_id=f"task_{i+1}",
            task_type=task_type.value,
            total_time=total_time,
            breakdown=breakdown
        )

    # 🎯 새로운 고급 API 사용
    latency_breakdown = evaluator.latency_tracker.get_latency_by_type()

    print("✓ Task 타입별 지연시간 분석:")

    for task_type, stats in latency_breakdown.items():
        print(f"\n  [{task_type}]")
        print(f"    - 평균: {stats['avg']:.3f}s")
        print(f"    - 중앙값: {stats['median']:.3f}s")
        print(f"    - 범위: {stats['min']:.3f}s ~ {stats['max']:.3f}s")
        print(f"    - P95: {stats['p95']:.3f}s (95%의 요청이 이 시간 내 완료)")
        print(f"    - P99: {stats['p99']:.3f}s (99%의 요청이 이 시간 내 완료)")
        print(f"    - 표준편차: {stats['std']:.3f}s")
        print(f"    - 총 요청 수: {stats['count']}")
        print(f"    - 총 소요 시간: {stats['total_time']:.3f}s")

    # 💡 성능 분석
    print("\n💡 성능 분석:")
    slowest_type = max(latency_breakdown.items(), key=lambda x: x[1]['avg'])
    fastest_type = min(latency_breakdown.items(), key=lambda x: x[1]['avg'])

    print(f"  • 가장 느린 작업: {slowest_type[0]} (평균 {slowest_type[1]['avg']:.3f}s)")
    print(f"  • 가장 빠른 작업: {fastest_type[0]} (평균 {fastest_type[1]['avg']:.3f}s)")

    # SLA 검증
    print("\n  SLA 검증 (목표: 모든 작업 < 5초):")
    for task_type, stats in latency_breakdown.items():
        if stats['p95'] > 5.0:
            print(f"    ⚠️  {task_type}: P95 {stats['p95']:.3f}s - SLA 위반 위험")
        else:
            print(f"    ✓ {task_type}: P95 {stats['p95']:.3f}s - SLA 충족")


def demo_cost_breakdown_by_model(evaluator):
    """Demo 4: 모델별 비용 분석"""
    print_section("4. TokenEconomyTracker.get_cost_breakdown_by_model()")

    # GPT-4 pricing (example)
    evaluator.token_tracker = evaluator.token_tracker or type('obj', (object,), {
        'pricing': {"input": 0.03, "output": 0.06},  # per 1K tokens
        'track_usage': lambda *args, **kwargs: None,
        'usage_log': []
    })()

    # 다양한 모델의 토큰 사용 시뮬레이션
    usage_data = [
        # GPT-4 사용
        ("task_1", 1500, 800, TaskType.CODE_GENERATION, "gpt-4"),
        ("task_2", 2000, 1200, TaskType.CODE_GENERATION, "gpt-4"),
        ("task_3", 1200, 600, TaskType.QA, "gpt-4"),

        # GPT-3.5-turbo 사용
        ("task_4", 800, 400, TaskType.QA, "gpt-3.5-turbo"),
        ("task_5", 1000, 500, TaskType.QA, "gpt-3.5-turbo"),
        ("task_6", 900, 450, TaskType.DATA_ANALYSIS, "gpt-3.5-turbo"),
        ("task_7", 850, 420, TaskType.QA, "gpt-3.5-turbo"),

        # Claude 사용
        ("task_8", 1100, 550, TaskType.REASONING, "claude-3-sonnet"),
        ("task_9", 1300, 650, TaskType.REASONING, "claude-3-sonnet"),
    ]

    for task_id, input_tokens, output_tokens, task_type, model in usage_data:
        evaluator.token_tracker.track_usage(
            task_id=task_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task_type=task_type.value,
            model=model
        )

    # 🎯 새로운 고급 API 사용
    cost_breakdown = evaluator.token_tracker.get_cost_breakdown_by_model()

    print("✓ 모델별 비용 분석:")

    total_cost = 0
    for model, stats in cost_breakdown.items():
        print(f"\n  [{model}]")
        print(f"    - 총 비용: ${stats['total_cost']:.4f}")
        print(f"    - 작업 수: {stats['total_tasks']}")
        print(f"    - 작업당 평균 비용: ${stats['avg_cost_per_task']:.4f}")
        print(f"    - 비용 중앙값: ${stats['median_cost']:.4f}")
        print(f"    - 비용 범위: ${stats['min_cost']:.4f} ~ ${stats['max_cost']:.4f}")
        print(f"    - 비용 표준편차: ${stats['std_cost']:.4f}")
        print(f"    - 총 토큰 수: {stats['total_tokens']:,}")
        print(f"    - 입력 토큰: {stats['total_input_tokens']:,}")
        print(f"    - 출력 토큰: {stats['total_output_tokens']:,}")
        print(f"    - 작업당 평균 토큰: {stats['avg_tokens_per_task']:.0f}")
        print(f"    - 1K 토큰당 비용: ${stats['cost_per_1k_tokens']:.4f}")

        total_cost += stats['total_cost']

    # 💡 비용 최적화 제안
    print(f"\n💡 비용 최적화 분석:")
    print(f"  • 전체 비용: ${total_cost:.4f}")

    # 가장 비싼 모델 찾기
    most_expensive = max(cost_breakdown.items(), key=lambda x: x[1]['total_cost'])
    cheapest = min(cost_breakdown.items(), key=lambda x: x[1]['avg_cost_per_task'])

    print(f"  • 가장 비용이 많이 든 모델: {most_expensive[0]} (${most_expensive[1]['total_cost']:.4f})")
    print(f"  • 작업당 가장 저렴한 모델: {cheapest[0]} (${cheapest[1]['avg_cost_per_task']:.4f})")

    # 최적화 제안
    if most_expensive[1]['total_cost'] > total_cost * 0.5:
        print(f"\n  ⚠️  {most_expensive[0]}이(가) 전체 비용의 50% 이상을 차지합니다.")
        print(f"      단순 작업은 더 저렴한 모델로 전환하는 것을 고려하세요.")


def demo_tool_usage_patterns(evaluator):
    """Demo 5: 도구 사용 패턴 분석"""
    print_section("5. ToolCallAnalyzer.get_tool_usage_patterns()")

    # 다양한 도구 사용 패턴 시뮬레이션
    tool_executions = [
        # 효율적인 도구 사용
        {
            "task_id": "task_1",
            "tool_calls": [
                {"tool_name": "search", "success": True, "duration": 0.5},
                {"tool_name": "calculator", "success": True, "duration": 0.1},
            ]
        },
        # 중복 호출이 있는 경우
        {
            "task_id": "task_2",
            "tool_calls": [
                {"tool_name": "database", "success": True, "duration": 1.2},
                {"tool_name": "database", "success": True, "duration": 1.1},  # 중복
                {"tool_name": "api_call", "success": True, "duration": 0.8},
            ]
        },
        # 실패가 있는 경우
        {
            "task_id": "task_3",
            "tool_calls": [
                {"tool_name": "api_call", "success": False, "duration": 0.3},
                {"tool_name": "api_call", "success": True, "duration": 0.9},  # 재시도 성공
                {"tool_name": "parser", "success": True, "duration": 0.2},
            ]
        },
        # 많은 도구를 사용하는 복잡한 작업
        {
            "task_id": "task_4",
            "tool_calls": [
                {"tool_name": "search", "success": True, "duration": 0.6},
                {"tool_name": "database", "success": True, "duration": 1.5},
                {"tool_name": "calculator", "success": True, "duration": 0.1},
                {"tool_name": "api_call", "success": True, "duration": 0.7},
                {"tool_name": "parser", "success": True, "duration": 0.3},
                {"tool_name": "validator", "success": True, "duration": 0.2},
            ]
        },
        # 간단한 작업
        {
            "task_id": "task_5",
            "tool_calls": [
                {"tool_name": "calculator", "success": True, "duration": 0.1},
            ]
        },
    ]

    for execution in tool_executions:
        evaluator.tool_analyzer.analyze_execution(
            task_id=execution["task_id"],
            tool_calls=execution["tool_calls"]
        )

    # 🎯 새로운 고급 API 사용
    usage_patterns = evaluator.tool_analyzer.get_tool_usage_patterns()

    print("✓ 도구 사용 패턴 분석:")
    print(f"  • 총 작업 수: {usage_patterns['total_tasks']}")
    print(f"  • 총 도구 호출 수: {usage_patterns['total_tool_calls']}")

    # 패턴 분석
    pa = usage_patterns['pattern_analysis']
    print(f"\n  📊 패턴 분석:")
    print(f"    - 작업당 평균 도구 수: {pa['avg_tools_per_task']:.2f}")
    print(f"    - 작업당 중앙값 도구 수: {pa['median_tools_per_task']:.2f}")
    print(f"    - 최대 도구 사용 (단일 작업): {pa['max_tools_in_single_task']}")
    print(f"    - 최소 도구 사용 (단일 작업): {pa['min_tools_in_single_task']}")
    print(f"    - 평균 효율성: {pa['avg_efficiency']:.2f}%")
    print(f"    - 중복 호출이 있는 작업: {pa['tasks_with_redundancy']}")
    print(f"    - 실패가 있는 작업: {pa['tasks_with_failures']}")

    # 사용 분포
    print(f"\n  📈 사용 분포:")
    for range_key, count in usage_patterns['usage_distribution'].items():
        print(f"    - {range_key}: {count}개 작업")

    # 효율성 분포
    print(f"\n  ⚡ 효율성 분포:")
    for eff_range, count in usage_patterns['efficiency_distribution'].items():
        print(f"    - {eff_range}: {count}개 작업")

    # 중복 및 실패 영향
    print(f"\n  🔄 중복 영향:")
    print(f"    - 총 중복 호출: {usage_patterns['redundancy_impact']['total_redundant']}")
    print(f"    - 작업당 평균 중복: {usage_patterns['redundancy_impact']['avg_redundant_per_task']:.2f}")

    print(f"\n  ❌ 실패 영향:")
    print(f"    - 총 실패 호출: {usage_patterns['failure_impact']['total_failed']}")
    print(f"    - 작업당 평균 실패: {usage_patterns['failure_impact']['avg_failed_per_task']:.2f}")

    # 💡 최적화 제안
    print("\n💡 최적화 제안:")
    if usage_patterns['redundancy_impact']['total_redundant'] > 0:
        print("  ⚠️  중복 도구 호출이 감지되었습니다. 캐싱 메커니즘을 고려하세요.")
    if usage_patterns['failure_impact']['total_failed'] > 0:
        print("  ⚠️  실패한 도구 호출이 있습니다. 재시도 로직과 에러 처리를 개선하세요.")
    if pa['avg_tools_per_task'] > 5:
        print("  ⚠️  작업당 평균 도구 수가 높습니다. 워크플로우 단순화를 고려하세요.")


def demo_critical_path_analysis(evaluator):
    """Demo 6: 워크플로우 Critical Path 분석"""
    print_section("6. WorkflowExecutionTracker.get_critical_path_analysis()")

    # 여러 워크플로우 실행 시뮬레이션
    workflows = [
        # Workflow 1
        [
            ("initialize", "node", True, 0.3),
            ("fetch_data", "node", True, 1.5),
            ("process", "node", True, 2.8),
            ("validate", "node", True, 0.6),
            ("finalize", "node", True, 0.4),
        ],
        # Workflow 2
        [
            ("initialize", "node", True, 0.4),
            ("fetch_data", "node", True, 1.8),
            ("process", "node", True, 3.2),  # 더 느림
            ("validate", "node", False, 0.5),  # 실패
            ("retry_validate", "node", True, 0.7),
            ("finalize", "node", True, 0.5),
        ],
        # Workflow 3
        [
            ("initialize", "node", True, 0.2),
            ("fetch_data", "node", True, 1.2),
            ("process", "node", True, 2.5),
            ("validate", "node", True, 0.4),
            ("finalize", "node", True, 0.3),
        ],
    ]

    for workflow_id, steps in enumerate(workflows, 1):
        for step_name, step_type, success, execution_time in steps:
            evaluator.workflow_tracker.track_step(
                task_id=f"workflow_{workflow_id}",
                step_name=step_name,
                step_type=step_type,
                success=success,
                execution_time=execution_time,
                framework="langgraph"
            )

    # 🎯 새로운 고급 API 사용
    critical_path = evaluator.workflow_tracker.get_critical_path_analysis()

    print("✓ Critical Path 분석:")
    print(f"  • 총 워크플로우 수: {critical_path['total_workflows']}")
    print(f"  • 총 단계 수: {critical_path['total_steps']}")

    # 병목 지점
    print(f"\n  🚨 Top 3 병목 지점:")
    for i, bottleneck in enumerate(critical_path['bottlenecks'][:3], 1):
        print(f"\n    {i}. {bottleneck['step_name']}")
        print(f"       - 평균 실행 시간: {bottleneck['avg_time']:.3f}s")
        print(f"       - 중앙값: {bottleneck['median_time']:.3f}s")
        print(f"       - 범위: {bottleneck['min_time']:.3f}s ~ {bottleneck['max_time']:.3f}s")
        print(f"       - 표준편차: {bottleneck['std_time']:.3f}s")
        print(f"       - 성공률: {bottleneck['success_rate']:.2f}%")
        print(f"       - 실행 횟수: {bottleneck['execution_count']}")

    # 워크플로우 통계
    ws = critical_path['workflow_statistics']
    print(f"\n  📊 워크플로우 전체 통계:")
    print(f"    - 평균 총 실행 시간: {ws['avg_total_time']:.3f}s")
    print(f"    - 중앙값 총 실행 시간: {ws['median_total_time']:.3f}s")
    print(f"    - 범위: {ws['min_total_time']:.3f}s ~ {ws['max_total_time']:.3f}s")
    print(f"    - 평균 성공률: {ws['avg_success_rate']:.2f}%")

    # 병렬화 기회
    if critical_path['parallelization_opportunities']:
        print(f"\n  ⚡ 병렬화 기회:")
        for opp in critical_path['parallelization_opportunities']:
            print(f"    - {opp['description']}")
            print(f"      유형: {opp['type']}, 횟수: {opp['count']}")

    # 최적화 권장사항
    print(f"\n  💡 최적화 권장사항:")
    for i, recommendation in enumerate(critical_path['optimization_recommendations'], 1):
        print(f"    {i}. {recommendation}")


def demo_interaction_patterns(evaluator):
    """Demo 7: 에이전트 상호작용 패턴 분석"""
    print_section("7. AgentCoordinationTracker.get_interaction_patterns()")

    # Hub 패턴 시뮬레이션 (중앙 조정자)
    print("  시나리오: 멀티 에이전트 시스템 (Hub 패턴)")

    interactions = [
        # Orchestrator가 작업을 분배
        ("orchestrator", "research_agent", "delegation", True),
        ("orchestrator", "analysis_agent", "delegation", True),
        ("orchestrator", "writing_agent", "delegation", True),

        # 각 에이전트가 결과를 보고
        ("research_agent", "orchestrator", "communication", True),
        ("analysis_agent", "orchestrator", "communication", True),
        ("writing_agent", "orchestrator", "communication", True),

        # Orchestrator가 추가 작업 요청
        ("orchestrator", "writing_agent", "delegation", True),

        # 최종 결과
        ("writing_agent", "orchestrator", "communication", True),
    ]

    for from_agent, to_agent, interaction_type, success in interactions:
        evaluator.agent_coordination_tracker.track_interaction(
            task_id="multi_agent_task_1",
            from_agent=from_agent,
            to_agent=to_agent,
            interaction_type=interaction_type,
            success=success
        )

    # 🎯 새로운 고급 API 사용
    patterns = evaluator.agent_coordination_tracker.get_interaction_patterns()

    print("\n✓ 상호작용 패턴 분석:")
    print(f"  • 총 상호작용: {patterns['total_interactions']}")
    print(f"  • 총 에이전트 수: {patterns['total_agents']}")
    print(f"  • 감지된 패턴: {patterns['pattern_type'].upper()}")
    print(f"  • 패턴 신뢰도: {patterns['pattern_confidence']:.2f}%")
    print(f"  • 성공률: {patterns['success_rate']:.2f}%")

    if patterns['hub_agent']:
        print(f"  • Hub 에이전트: {patterns['hub_agent']}")

    # 에이전트 역할 분석
    print(f"\n  👥 에이전트 역할:")
    for agent, info in patterns['agent_roles'].items():
        role_emoji = {
            'producer': '📤',
            'consumer': '📥',
            'coordinator': '🔄'
        }.get(info['role'], '❓')

        print(f"    {role_emoji} {agent}: {info['role']}")
        print(f"       - 송신: {info['sends']}, 수신: {info['receives']}, 총: {info['total_interactions']}")

    # 상호작용 타입 분포
    print(f"\n  📊 상호작용 타입 분포:")
    for interaction_type, count in patterns['interaction_type_distribution'].items():
        print(f"    - {interaction_type}: {count}회")

    # Top 에이전트 페어
    print(f"\n  🔝 Top 상호작용 페어:")
    for i, pair_info in enumerate(patterns['top_agent_pairs'][:5], 1):
        print(f"    {i}. {pair_info['pair']}: {pair_info['count']}회")

    # 패턴 특성
    pc = patterns['pattern_characteristics']
    print(f"\n  🎯 패턴 특성:")
    print(f"    설명: {pc['description']}")
    print(f"\n    강점:")
    for strength in pc['strengths']:
        print(f"      ✓ {strength}")
    print(f"\n    약점:")
    for weakness in pc['weaknesses']:
        print(f"      ⚠ {weakness}")
    print(f"\n    권장사항:")
    print(f"      💡 {pc['recommendation']}")


def main():
    """메인 실행 함수"""
    print("\n" + "=" * 80)
    print("  Level 2 Advanced: 7가지 고급 API 메서드 종합 데모")
    print("  Agent Evaluator v0.5.0")
    print("=" * 80)

    # 기본 evaluator 생성
    evaluator = PerformanceMonitor()

    # 1. 환각 유형별 분석
    evaluator = demo_hallucination_by_type()

    # 2. 품질 차원별 분석
    demo_quality_by_dimension(evaluator)

    # 3. Task 타입별 지연시간
    demo_latency_by_type(evaluator)

    # 4. 모델별 비용 분석
    demo_cost_breakdown_by_model(evaluator)

    # 5. 도구 사용 패턴
    demo_tool_usage_patterns(evaluator)

    # 6. Critical Path 분석
    demo_critical_path_analysis(evaluator)

    # 7. 상호작용 패턴
    demo_interaction_patterns(evaluator)

    # 결과 저장
    print_section("💾 결과 저장")
    filename = f"{FILE_PREFIX}advanced_api_methods.json"
    evaluator.save_to_file(filename)
    print(f"✓ 저장 완료: {filename}")
    print(f"✓ Dashboard에서 확인 가능")

    # 최종 요약
    print_section("🎉 데모 완료")
    print("7가지 고급 API 메서드를 모두 시연했습니다:")
    print("  ✓ 1. HallucinationDetector.get_hallucination_by_type()")
    print("  ✓ 2. ResponseQualityEvaluator.get_quality_by_dimension()")
    print("  ✓ 3. LatencyTracker.get_latency_by_type()")
    print("  ✓ 4. TokenEconomyTracker.get_cost_breakdown_by_model()")
    print("  ✓ 5. ToolCallAnalyzer.get_tool_usage_patterns()")
    print("  ✓ 6. WorkflowExecutionTracker.get_critical_path_analysis()")
    print("  ✓ 7. AgentCoordinationTracker.get_interaction_patterns()")

    print("\n💡 이 API들을 활용하여:")
    print("   • 더 깊이 있는 성능 분석")
    print("   • 세밀한 비용 최적화")
    print("   • 효과적인 병목 지점 탐지")
    print("   • 에이전트 협업 패턴 이해")
    print("   를 수행할 수 있습니다.")

    print("\n다음 단계:")
    print("  → Dashboard에서 결과 확인: streamlit run Dashboard/app.py")
    print("  → level_3_production/ 예제들을 통해 프로덕션 환경에서의 활용법 확인")
    print(f"  → 저장된 결과: {filename}")


if __name__ == "__main__":
    main()
