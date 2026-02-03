#!/usr/bin/env python3
"""
Level 1 Foundation - Example 06: 고급 메트릭 분석
====================================================

🎯 목표: 기본 Tracker 메서드를 활용한 고급 데이터 분석

📚 학습 내용:
1. AccuracyEvaluator.get_accuracy_by_type() - Task 타입별 정확도
2. HallucinationDetector - 환각 발생 패턴 분석
3. ResponseQualityEvaluator - 품질 메트릭 상세 분석
4. LatencyTracker - 지연시간 통계 및 병목 분석
5. TokenEconomyTracker - 타입별 비용 분석
6. ToolCallAnalyzer - 도구 효율성 패턴 분석

💡 사용 시기:
- 프로덕션 환경에서 상세한 모니터링이 필요할 때
- 대규모 평가에서 Task 타입별, 모델별 성능 비교
- 비용 최적화를 위한 타입별 분석
- 워크플로우 최적화를 위한 패턴 분석

⏱️ 예상 소요 시간: 20분
💰 비용: 무료 (Layer 1만 사용)

실행 방법:
    python level_1_foundation/06_advanced_metrics_analysis.py
"""

from datetime import datetime
from agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TaskType
)

FILE_PREFIX = "[L1-06]_"


def main():
    """고급 메트릭 분석 - 실제 구현된 API 활용"""

    print("=" * 80)
    print("🎯 Level 1 Foundation - 고급 메트릭 분석")
    print("=" * 80)
    print("기본 Tracker 메서드로 고급 데이터 분석을 수행합니다.")
    print("")

    # Monitor 생성
    monitor = PerformanceMonitor(
        enable_hallucination_detection=True
    )

    # ============================================================================
    # 1. AccuracyEvaluator.get_accuracy_by_type() - Task 타입별 정확도
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 1/6: Task 타입별 정확도 분석")
    print("=" * 80)
    print("목적: QA, Document Creation, Code 등 Task 타입별로 정확도를 분리 계산")
    print("")

    # QA Task 평가
    qa_data = [
        ("서울", "대한민국의 수도는 서울입니다."),
        ("세종대왕", "한글은 세종대왕이 창제했습니다."),
        ("1945년", "광복절은 1945년 8월 15일입니다."),
        ("독도", "독도는 대한민국 영토입니다."),
    ]

    for i, (truth, pred) in enumerate(qa_data):
        monitor.accuracy_evaluator.add_evaluation(
            task_id=f"qa_{i:03d}",
            ground_truth=truth,
            prediction=pred,
            task_type=TaskType.QA.value
        )

    # Document Creation Task 평가
    doc_data = [
        ("간단한 요약", "이 문서는 간단하게 요약할 수 있습니다."),
        ("핵심 포인트", "핵심 포인트는 다음과 같습니다."),
        ("전체 개요", "전체적인 개요를 제공합니다."),
    ]

    for i, (truth, pred) in enumerate(doc_data):
        monitor.accuracy_evaluator.add_evaluation(
            task_id=f"doc_{i:03d}",
            ground_truth=truth,
            prediction=pred,
            task_type=TaskType.DOCUMENT_CREATION.value
        )

    # Code Task 평가
    code_data = [
        ("def add(a, b): return a + b", "def add(a, b):\n    return a + b"),
        ("print('hello')", "print('hello')"),
    ]

    for i, (truth, pred) in enumerate(code_data):
        monitor.accuracy_evaluator.add_evaluation(
            task_id=f"code_{i:03d}",
            ground_truth=truth,
            prediction=pred,
            task_type=TaskType.CODE_GENERATION.value
        )

    # Task 타입별 정확도 조회 (✅ 실제 구현됨)
    accuracy_by_type = monitor.accuracy_evaluator.get_accuracy_by_type()

    print("✅ Task 타입별 정확도:")
    for task_type, accuracy in accuracy_by_type.items():
        print(f"  - {task_type}: {accuracy:.1f}%")

    print("\n💡 인사이트:")
    print("  → Task 타입별 정확도 차이를 파악하여 개선이 필요한 영역 식별")
    print("  → 예: QA 90%, Code 75% → Code 생성 개선 필요")


    # ============================================================================
    # 2. HallucinationDetector - 환각 발생 패턴 분석
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 2/6: 환각 발생 패턴 분석")
    print("=" * 80)
    print("목적: 환각 발생률 및 패턴 파악")
    print("")

    # 다양한 환각 케이스
    hallucination_tests = [
        ("hall_001", "서울은 대한민국의 수도입니다.",
         "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다.", False),
        ("hall_002", "부산은 약 340만 명의 인구를 가진 도시입니다.",
         "부산은 약 500만 명의 인구를 가진 도시입니다.", True),
        ("hall_003", "제주도는 화산섬입니다.",
         "제주도는 화산섬이며, 세계 7대 자연경관으로 선정되었습니다.", True),
        ("hall_004", "광복절은 1945년 8월 15일입니다.",
         "광복절은 1948년 8월 15일입니다.", True),
        ("hall_005", "한글은 세종대왕이 창제했습니다.",
         "한글은 세종대왕이 1443년에 창제했습니다.", False),
    ]

    for task_id, context, response, is_hallucination in hallucination_tests:
        result = monitor.hallucination_detector.detect_hallucination(
            task_id, response, context
        )

        icon = "🔴" if result else "✅"
        print(f"  {icon} {task_id}: {'환각 발생' if result else '정상'}")

    # 전체 환각률 조회 (✅ 실제 구현됨)
    hall_stats = monitor.hallucination_detector.get_hallucination_rate()

    print(f"\n✅ 환각 통계:")
    print(f"  - 전체 환각률: {hall_stats.get('overall_rate', 0):.1f}%")
    print(f"  - 환각 발생: {hall_stats.get('tasks_with_hallucinations', 0)}건")
    print(f"  - 총 검사: {hall_stats.get('total_tasks_checked', 0)}건")

    print("\n💡 인사이트:")
    print("  → 환각 발생률을 모니터링하여 프롬프트 개선")
    print("  → 특정 패턴(수치, 날짜 등)에서 환각이 많으면 추가 검증 필요")


    # ============================================================================
    # 3. ResponseQualityEvaluator - 품질 메트릭 상세 분석
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 3/6: 응답 품질 상세 분석")
    print("=" * 80)
    print("목적: Relevance, Completeness, Accuracy 등 품질 차원 분석")
    print("")

    # 다양한 품질의 응답
    quality_tests = [
        {
            "task_id": "quality_high",
            "response": "대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 대도시로, 약 1천만 명의 인구가 살고 있으며, 정치, 경제, 문화의 중심지입니다.",
            "request": "대한민국의 수도는 어디인가요?",
            "elements": ["서울", "수도", "대한민국"],
            "ground_truth": "서울",
            "label": "우수 응답"
        },
        {
            "task_id": "quality_medium",
            "response": "서울이요.",
            "request": "대한민국의 수도는 어디이며, 어떤 특징이 있나요?",
            "elements": ["서울", "수도", "특징", "인구"],
            "ground_truth": "서울",
            "label": "불충분한 응답"
        },
        {
            "task_id": "quality_low",
            "response": "대한민국은 한반도에 위치한 나라입니다.",
            "request": "대한민국의 수도는 어디인가요?",
            "elements": ["서울", "수도"],
            "ground_truth": "서울",
            "label": "관련성 낮은 응답"
        }
    ]

    for test in quality_tests:
        monitor.quality_evaluator.evaluate_response(
            task_id=test["task_id"],
            response=test["response"],
            request=test["request"],
            expected_elements=test["elements"],
            ground_truth=test["ground_truth"]
        )
        print(f"  평가 완료: {test['label']}")

    # 품질 메트릭 조회 (✅ 실제 구현됨)
    quality_metrics = monitor.quality_evaluator.get_quality_metrics()

    print(f"\n✅ 품질 메트릭:")
    print(f"  - 평균 품질 점수: {quality_metrics.get('avg_total_score', 0):.2f}/5.0")

    # dimension_averages에서 각 차원의 평균 추출
    dim_avg = quality_metrics.get('dimension_averages', {})
    print(f"  - Relevance (관련성): {dim_avg.get('relevance', 0):.2f}/5.0")
    print(f"  - Completeness (완전성): {dim_avg.get('completeness', 0):.2f}/5.0")
    print(f"  - Accuracy (정확성): {dim_avg.get('accuracy', 0):.2f}/5.0")
    print(f"  - Clarity (명확성): {dim_avg.get('clarity', 0):.2f}/5.0")
    print(f"  - Usefulness (유용성): {dim_avg.get('usefulness', 0):.2f}/5.0")

    print("\n💡 인사이트:")
    print("  → 각 차원별 강약점을 파악하여 응답 품질 개선")
    print("  → Completeness 낮음 → 더 상세한 정보 제공하도록 프롬프트 조정")


    # ============================================================================
    # 4. LatencyTracker - 지연시간 통계 및 병목 분석
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 4/6: 지연시간 통계 및 병목 분석")
    print("=" * 80)
    print("목적: 응답 시간 분포 및 SLA 준수 여부 확인")
    print("")

    # 다양한 Task 지연시간 기록
    latencies = [
        # QA Tasks (빠름)
        (TaskType.QA.value, [0.8, 0.9, 1.0, 1.1, 0.7, 0.9, 1.2, 0.8]),
        # Document Tasks (중간)
        (TaskType.DOCUMENT_CREATION.value, [2.1, 2.5, 2.3, 2.8, 2.0, 2.4]),
        # Code Tasks (느림)
        (TaskType.CODE_GENERATION.value, [4.5, 5.2, 4.8, 5.5, 4.2])
    ]

    for task_type, times in latencies:
        for i, latency in enumerate(times):
            monitor.latency_tracker.record_latency(
                task_id=f"{task_type}_{i:03d}",
                task_type=task_type,
                total_time=latency,
                breakdown={"processing": latency}
            )

    # 전체 지연시간 통계 (✅ 실제 구현됨)
    latency_stats = monitor.latency_tracker.get_latency_stats()

    print(f"✅ 전체 지연시간 통계:")
    print(f"  - 평균: {latency_stats.get('avg', 0):.2f}초")
    print(f"  - 중간값 (P50): {latency_stats.get('median', 0):.2f}초")
    print(f"  - P95: {latency_stats.get('p95', 0):.2f}초")
    print(f"  - P99: {latency_stats.get('p99', 0):.2f}초")
    print(f"  - 최소: {latency_stats.get('min', 0):.2f}초")
    print(f"  - 최대: {latency_stats.get('max', 0):.2f}초")

    # 병목 분석 (✅ 실제 구현됨)
    bottleneck_analysis = monitor.latency_tracker.analyze_bottlenecks()

    print(f"\n🔍 병목 분석:")
    if bottleneck_analysis.get('bottleneck'):
        print(f"  - 병목 단계: {bottleneck_analysis['bottleneck']}")

    if bottleneck_analysis.get('breakdown_averages'):
        print(f"  - 단계별 평균 시간:")
        for stage, avg_time in bottleneck_analysis['breakdown_averages'].items():
            print(f"    • {stage}: {avg_time:.2f}초")
    else:
        print("  → 상세 분석 데이터 없음")

    print("\n💡 인사이트:")
    print("  → P95, P99로 worst-case 성능 파악")
    print("  → 병목 Task 식별하여 최적화 우선순위 결정")


    # ============================================================================
    # 5. TokenEconomyTracker - 타입별 비용 분석
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 5/6: Task 타입별 비용 분석")
    print("=" * 80)
    print("목적: Task 타입별 토큰 사용량 및 비용 비교")
    print("")

    # 다양한 Task 타입의 토큰 사용량
    token_usage = [
        # QA Tasks (적은 토큰)
        (TaskType.QA.value, [(100, 50), (120, 60), (90, 45), (110, 55), (95, 50)]),
        # Document Tasks (중간 토큰)
        (TaskType.DOCUMENT_CREATION.value, [(300, 200), (350, 250), (280, 180)]),
        # Code Tasks (많은 토큰)
        (TaskType.CODE_GENERATION.value, [(500, 400), (600, 500), (550, 450)])
    ]

    for task_type, usages in token_usage:
        for i, (input_t, output_t) in enumerate(usages):
            monitor.token_tracker.track_usage(
                task_id=f"{task_type}_token_{i:03d}",
                input_tokens=input_t,
                output_tokens=output_t,
                task_type=task_type
            )

    # 전체 토큰 통계 (✅ 실제 구현됨)
    token_stats = monitor.token_tracker.get_usage_stats()

    print(f"✅ 전체 토큰 통계:")
    print(f"  - 총 토큰: {token_stats.get('total_tokens', 0):,}개")
    print(f"  - 입력 토큰: {token_stats.get('total_input_tokens', 0):,}개")
    print(f"  - 출력 토큰: {token_stats.get('total_output_tokens', 0):,}개")
    print(f"  - 총 비용: ${token_stats.get('total_cost', 0):.4f}")
    print(f"  - Task당 평균 비용: ${token_stats.get('avg_cost_per_task', 0):.4f}")

    # Task 타입별 사용량 (✅ 실제 구현됨)
    usage_by_type = monitor.token_tracker.get_usage_by_type()

    print(f"\n📊 Task 타입별 토큰 사용:")
    # get_usage_by_type()은 pandas groupby to_dict() 형식 반환
    # 형식: {('total_tokens', 'sum'): {task_type: value}, ...}

    if usage_by_type:
        # task_type 목록 추출
        task_types = set()
        for key in usage_by_type.keys():
            if isinstance(key, tuple):
                for task_type in usage_by_type[key].keys():
                    task_types.add(task_type)

        for task_type in sorted(task_types):
            total_tokens = usage_by_type.get(('total_tokens', 'sum'), {}).get(task_type, 0)
            avg_tokens = usage_by_type.get(('total_tokens', 'mean'), {}).get(task_type, 0)
            total_cost = usage_by_type.get(('cost', 'sum'), {}).get(task_type, 0)

            print(f"\n  {task_type}:")
            print(f"    - 총 토큰: {total_tokens:,.0f}개")
            print(f"    - 평균/Task: {avg_tokens:,.0f}개")
            print(f"    - 비용: ${total_cost:.4f}")
    else:
        print("  (데이터 없음)")

    print("\n💡 인사이트:")
    print("  → Task 타입별 비용 비중을 파악하여 비용 최적화")
    print("  → 예: Code 생성이 비용의 60% → 더 효율적인 모델 고려")


    # ============================================================================
    # 6. ToolCallAnalyzer - 도구 효율성 패턴 분석
    # ============================================================================
    print("\n" + "=" * 80)
    print("📊 6/6: 도구 사용 효율성 패턴 분석")
    print("=" * 80)
    print("목적: 도구 호출 패턴 및 효율성 분석")
    print("")

    # 다양한 도구 사용 패턴
    tool_patterns = [
        ("efficient_001", [
            {"name": "search", "success": True, "duration": 0.5},
            {"name": "analyze", "success": True, "duration": 1.0}
        ], "효율적"),
        ("redundant_002", [
            {"name": "search", "success": True, "duration": 0.5},
            {"name": "search", "success": True, "duration": 0.6},  # 중복
            {"name": "analyze", "success": True, "duration": 1.0}
        ], "중복 호출"),
        ("failed_003", [
            {"name": "search", "success": True, "duration": 0.5},
            {"name": "database", "success": False, "duration": 0.2},  # 실패
            {"name": "analyze", "success": True, "duration": 1.0}
        ], "일부 실패"),
    ]

    for task_id, tool_calls, label in tool_patterns:
        monitor.tool_analyzer.analyze_execution(task_id, tool_calls)
        print(f"  분석 완료: {label}")

    # 도구 효율성 통계 (✅ 실제 구현됨)
    tool_stats = monitor.tool_analyzer.get_efficiency_stats()

    print(f"\n✅ 도구 효율성 통계:")
    print(f"  - 총 호출: {tool_stats.get('total_calls', 0)}회")
    print(f"  - 성공률: {tool_stats.get('success_rate', 0):.1f}%")
    print(f"  - 중복 호출: {tool_stats.get('redundant_calls', 0)}회")
    print(f"  - 효율성: {tool_stats.get('efficiency', 0):.1f}%")
    print(f"  - 평균 지연시간: {tool_stats.get('avg_duration', 0):.2f}초")

    print("\n💡 인사이트:")
    print("  → 중복 호출이 많으면 캐싱 메커니즘 도입")
    print("  → 실패율이 높은 도구는 대체 도구 고려")
    print("  → 평균 지연시간으로 병목 도구 식별")


    # ============================================================================
    # 결과 저장
    # ============================================================================
    print("\n" + "=" * 80)
    print("💾 결과 저장")
    print("=" * 80)

    filename = f"{FILE_PREFIX}advanced_metrics_analysis.json"
    monitor.save_to_file(filename)
    print(f"✓ 저장 완료: {filename}")


    # ============================================================================
    # 종합 요약
    # ============================================================================
    print("\n" + "=" * 80)
    print("🎉 고급 메트릭 분석 완료!")
    print("=" * 80)

    print("\n📊 학습한 내용:")
    print("-" * 80)
    print("1. AccuracyEvaluator.get_accuracy_by_type()")
    print("   → Task 타입별 정확도 분리 (QA, Document, Code 등)")
    print("")
    print("2. HallucinationDetector.get_hallucination_rate()")
    print("   → 전체 환각 발생률 및 패턴 분석")
    print("")
    print("3. ResponseQualityEvaluator.get_quality_metrics()")
    print("   → 5개 품질 차원 (Relevance, Completeness, Accuracy, Clarity, Usefulness)")
    print("")
    print("4. LatencyTracker 고급 분석")
    print("   → get_latency_stats() - P50/P95/P99 통계")
    print("   → analyze_bottlenecks() - 병목 지점 탐지")
    print("")
    print("5. TokenEconomyTracker.get_usage_by_type()")
    print("   → Task 타입별 토큰 사용량 및 비용 분석")
    print("")
    print("6. ToolCallAnalyzer.get_efficiency_stats()")
    print("   → 도구 사용 패턴 및 효율성 분석")

    print("\n💡 프로덕션 활용:")
    print("-" * 80)
    print("✓ Task 타입별 성능 비교 → 개선이 필요한 영역 식별")
    print("✓ 환각 발생률 모니터링 → 프롬프트 개선")
    print("✓ 품질 차원별 평가 → 응답 품질 개선")
    print("✓ 지연시간 분석 → 병목 제거 및 SLA 준수")
    print("✓ 타입별 비용 분석 → 비용 최적화")
    print("✓ 도구 효율성 → 워크플로우 최적화")

    print("\n✅ 다음 예제:")
    print("   07_conversation_state_tracking.py → 대화 및 상태 전이 추적")


if __name__ == "__main__":
    main()
