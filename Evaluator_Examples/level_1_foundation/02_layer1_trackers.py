#!/usr/bin/env python3
"""
Level 1 Foundation - Example 02: Layer 1 Trackers 완전 가이드
==============================================================

🎯 목표: 11개 Tracker의 역할과 사용법 완전 마스터

📚 학습 내용:
1. TaskCompletionTracker → TCR (작업 완료율)
2. AccuracyEvaluator → Accuracy (정확도)
3. HallucinationDetector → Hallucination Rate (환각 발생률)
4. ResponseQualityEvaluator → Quality Score (품질 점수)
5. LatencyTracker → Latency (응답 시간)
6. TokenEconomyTracker → Cost (비용)
7. ToolCallAnalyzer → Tool Efficiency (도구 효율성)
8. RetryCorrectionTracker → Retry Success Rate (재시도 성공률)
9. ToolSelectionTracker → Tool Selection Accuracy (Layer 2)
10. AgentCoordinationTracker → Agent Coordination (Layer 2)
11. WorkflowExecutionTracker → Workflow Execution (Layer 2)

🔍 Dashboard 확인:
- 🎯 Core Metrics 탭: Layer 1 전체 (1-8)
- ⚡ Performance 탭: Latency, Cost 상세
- 🤖 Agentic AI 탭: Layer 2 (9-11)

⏱️ 예상 소요 시간: 15분
💰 비용: 무료 (Layer 1+2만 사용)

실행 방법:
    python level_1_foundation/02_layer1_trackers.py
"""

from datetime import datetime
from agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TaskType
)

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L1-02]_"


def main():
    """11개 Tracker 완전 가이드"""

    print("=" * 70)
    print("🎯 Level 1 Foundation - 11개 Tracker 마스터")
    print("=" * 70)

    # Monitor 생성
    monitor = PerformanceMonitor()

    # ========================================================================
    # Tracker 1: TaskCompletionTracker → TCR (작업 완료율)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 1/11: TaskCompletionTracker")
    print("=" * 70)
    print("역할: 작업 완료율 (TCR) 계산")
    print("핵심 메서드:")
    print("  - add_task(task)")
    print("  - calculate_tcr(task_type=None)")
    print("  - get_tcr_by_type()")
    print("")

    # 완전 성공 Task
    task_success = TaskResult(
        task_id="task_001",
        task_type=TaskType.QA.value,
        success=True,
        completion_score=1.0,  # 완전 성공
        accuracy_score=0.95,
        execution_time=1.2,
        tokens_used={"input": 50, "output": 30, "total": 80},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now()
    )

    # 부분 성공 Task
    task_partial = TaskResult(
        task_id="task_002",
        task_type=TaskType.QA.value,
        success=True,
        completion_score=0.7,  # 부분 성공 (70%)
        accuracy_score=0.65,
        execution_time=1.5,
        tokens_used={"input": 60, "output": 25, "total": 85},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now()
    )

    # 실패 Task
    task_fail = TaskResult(
        task_id="task_003",
        task_type=TaskType.QA.value,
        success=False,
        completion_score=0.0,  # 실패
        accuracy_score=0.0,
        execution_time=0.5,
        tokens_used={"input": 40, "output": 0, "total": 40},
        tool_calls=[],
        attempts=2,
        errors=["Validation failed", "Retry also failed"],
        timestamp=datetime.now()
    )

    # Tracker에 추가
    monitor.tcr_tracker.add_task(task_success)
    monitor.tcr_tracker.add_task(task_partial)
    monitor.tcr_tracker.add_task(task_fail)

    # TCR 계산
    tcr_data = monitor.tcr_tracker.calculate_tcr()
    print(f"✅ TCR 결과:")
    print(f"  - TCR: {tcr_data['tcr']:.1f}%")
    print(f"  - 완전 성공: {tcr_data['full_success']}개")
    print(f"  - 부분 성공: {tcr_data['partial_success']}개")
    print(f"  - 실패: {tcr_data['failures']}개")
    print(f"  - 성공률: {tcr_data['success_rate']:.1f}%")


    # ========================================================================
    # Tracker 2: AccuracyEvaluator → Accuracy (정확도)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 2/11: AccuracyEvaluator")
    print("=" * 70)
    print("역할: 정확도 계산 (4가지 유사도 메트릭 조합)")
    print("핵심 메서드:")
    print("  - add_evaluation(task_id, ground_truth, prediction, task_type)")
    print("  - get_accuracy_scores()")
    print("  - get_accuracy_by_type()")
    print("")

    # 평가 추가
    monitor.accuracy_evaluator.add_evaluation(
        task_id="qa_001",
        ground_truth="서울",
        prediction="대한민국의 수도는 서울입니다.",
        task_type=TaskType.QA.value
    )

    monitor.accuracy_evaluator.add_evaluation(
        task_id="qa_002",
        ground_truth="세종대왕",
        prediction="한글은 세종대왕이 창제했습니다.",
        task_type=TaskType.QA.value
    )

    # 정확도 조회
    accuracy_data = monitor.accuracy_evaluator.get_accuracy_scores()
    print(f"✅ Accuracy 결과:")
    print(f"  - 전체 정확도: {accuracy_data.get('overall_accuracy', 0):.1f}%")
    print(f"  - 평가 개수: {len(monitor.accuracy_evaluator.evaluations)}개")


    # ========================================================================
    # Tracker 3: HallucinationDetector → Hallucination Rate (환각)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 3/11: HallucinationDetector")
    print("=" * 70)
    print("역할: 환각 발생률 탐지 (문장 단위)")
    print("핵심 메서드:")
    print("  - detect_hallucination(task_id, response, context)")
    print("  - get_hallucination_rate()")
    print("")

    # Good response (환각 없음)
    context_good = "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다."
    response_good = "서울은 대한민국의 수도입니다."

    monitor.hallucination_detector.detect_hallucination(
        task_id="hall_001",
        response=response_good,
        context=context_good
    )

    # Bad response (환각 포함)
    context_bad = "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다."
    response_bad = "서울은 대한민국의 수도이며, 약 2천5백만 명의 인구가 살고 있습니다. GDP는 5조 달러입니다."

    monitor.hallucination_detector.detect_hallucination(
        task_id="hall_002",
        response=response_bad,
        context=context_bad
    )

    # 환각률 조회
    hall_data = monitor.hallucination_detector.get_hallucination_rate()
    print(f"✅ Hallucination 결과:")
    print(f"  - 환각 발생률: {hall_data.get('overall_rate', 0):.1f}%")
    print(f"  - 환각 검출: {hall_data.get('hallucinated_count', 0)}개")
    print(f"  - 총 검사: {hall_data.get('total_detections', 0)}개")


    # ========================================================================
    # Tracker 4: ResponseQualityEvaluator → Quality Score (품질)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 4/11: ResponseQualityEvaluator")
    print("=" * 70)
    print("역할: 응답 품질 평가 (5개 차원)")
    print("핵심 메서드:")
    print("  - evaluate_response(task_id, response, request, expected_elements, ground_truth)")
    print("  - get_quality_metrics()")
    print("")

    # 품질 평가
    monitor.quality_evaluator.evaluate_response(
        task_id="quality_001",
        response="대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 대도시로, 약 1천만 명의 인구가 살고 있습니다.",
        request="대한민국의 수도는 어디인가요?",
        expected_elements=["서울", "수도", "대한민국"],
        ground_truth="서울"
    )

    # 품질 조회
    quality_data = monitor.quality_evaluator.get_quality_metrics()
    print(f"✅ Quality 결과:")
    print(f"  - 평균 품질: {quality_data.get('avg_total_score', 0):.2f}/5.0")
    print(f"  - Relevance (관련성): {quality_data.get('avg_relevance', 0):.2f}")
    print(f"  - Completeness (완전성): {quality_data.get('avg_completeness', 0):.2f}")
    print(f"  - Accuracy (정확성): {quality_data.get('avg_accuracy', 0):.2f}")


    # ========================================================================
    # Tracker 5: LatencyTracker → Latency (응답 시간)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 5/11: LatencyTracker")
    print("=" * 70)
    print("역할: 응답 시간 추적 (P50, P95, P99)")
    print("핵심 메서드:")
    print("  - record_latency(task_id, task_type, total_time, breakdown)")
    print("  - get_latency_stats(task_type=None)")
    print("")

    # Latency 기록
    latencies = [1.2, 0.9, 1.5, 2.1, 0.8, 1.3, 3.5, 1.0, 1.1, 0.7]
    for i, latency in enumerate(latencies):
        monitor.latency_tracker.record_latency(
            task_id=f"lat_{i:03d}",
            task_type=TaskType.QA.value,
            total_time=latency,
            breakdown={"processing": latency}
        )

    # Latency 통계
    lat_data = monitor.latency_tracker.get_latency_stats()
    print(f"✅ Latency 결과:")
    print(f"  - 평균: {lat_data.get('avg', 0):.2f}초")
    print(f"  - 중간값 (P50): {lat_data.get('median', 0):.2f}초")
    print(f"  - P95: {lat_data.get('p95', 0):.2f}초")
    print(f"  - P99: {lat_data.get('p99', 0):.2f}초")
    print(f"  - 최대: {lat_data.get('max', 0):.2f}초")


    # ========================================================================
    # Tracker 6: TokenEconomyTracker → Cost (비용)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 6/11: TokenEconomyTracker")
    print("=" * 70)
    print("역할: 토큰 사용량 및 비용 추적")
    print("핵심 메서드:")
    print("  - track_usage(task_id, input_tokens, output_tokens, task_type)")
    print("  - get_usage_stats()")
    print("  - get_usage_by_type()")
    print("")

    # 토큰 사용량 기록
    monitor.token_tracker.track_usage(
        task_id="token_001",
        input_tokens=100,
        output_tokens=50,
        task_type=TaskType.QA.value
    )

    monitor.token_tracker.track_usage(
        task_id="token_002",
        input_tokens=150,
        output_tokens=80,
        task_type=TaskType.QA.value
    )

    # 토큰 통계
    token_data = monitor.token_tracker.get_usage_stats()
    print(f"✅ Token & Cost 결과:")
    print(f"  - 총 토큰: {token_data.get('total_tokens', 0):,}개")
    print(f"  - 입력 토큰: {token_data.get('total_input_tokens', 0):,}개")
    print(f"  - 출력 토큰: {token_data.get('total_output_tokens', 0):,}개")
    print(f"  - 총 비용: ${token_data.get('total_cost', 0):.4f}")
    print(f"  - Task당 평균 비용: ${token_data.get('avg_cost_per_task', 0):.4f}")


    # ========================================================================
    # Tracker 7: ToolCallAnalyzer → Tool Efficiency (도구 효율성)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 7/11: ToolCallAnalyzer")
    print("=" * 70)
    print("역할: 도구 호출 효율성 분석")
    print("핵심 메서드:")
    print("  - analyze_execution(task_id, tool_calls)")
    print("  - get_efficiency_stats()")
    print("")

    # 도구 호출 분석
    tool_calls_efficient = [
        {"name": "search", "success": True, "duration": 0.5},
        {"name": "calculator", "success": True, "duration": 0.1},
    ]

    tool_calls_inefficient = [
        {"name": "search", "success": True, "duration": 0.5},
        {"name": "search", "success": True, "duration": 0.6},  # 중복
        {"name": "calculator", "success": False, "duration": 0.2},  # 실패
    ]

    monitor.tool_analyzer.analyze_execution("tool_001", tool_calls_efficient)
    monitor.tool_analyzer.analyze_execution("tool_002", tool_calls_inefficient)

    # 효율성 통계
    tool_data = monitor.tool_analyzer.get_efficiency_stats()
    print(f"✅ Tool Efficiency 결과:")
    print(f"  - 총 호출: {tool_data.get('total_calls', 0)}회")
    print(f"  - 성공률: {tool_data.get('success_rate', 0):.1f}%")
    print(f"  - 중복 호출: {tool_data.get('redundant_calls', 0)}회")
    print(f"  - 효율성: {tool_data.get('efficiency', 0):.1f}%")


    # ========================================================================
    # Tracker 8: RetryCorrectionTracker → Retry Success Rate (재시도)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 8/11: RetryCorrectionTracker")
    print("=" * 70)
    print("역할: 재시도 성공률 추적")
    print("핵심 메서드:")
    print("  - track_attempts(task_id, attempts_log)")
    print("  - get_retry_metrics()")
    print("")

    # 재시도 이력 기록
    # Case 1: 1차 성공 (재시도 불필요)
    attempts_1 = [{"attempt": 1, "success": True, "error": None}]

    # Case 2: 2차 성공 (재시도로 복구)
    attempts_2 = [
        {"attempt": 1, "success": False, "error": "Validation failed"},
        {"attempt": 2, "success": True, "error": None}
    ]

    # Case 3: 3차에도 실패
    attempts_3 = [
        {"attempt": 1, "success": False, "error": "Network error"},
        {"attempt": 2, "success": False, "error": "Timeout"},
        {"attempt": 3, "success": False, "error": "Max retries exceeded"}
    ]

    monitor.retry_tracker.track_attempts("retry_001", attempts_1)
    monitor.retry_tracker.track_attempts("retry_002", attempts_2)
    monitor.retry_tracker.track_attempts("retry_003", attempts_3)

    # 재시도 통계
    retry_data = monitor.retry_tracker.get_retry_metrics()
    print(f"✅ Retry 결과:")
    print(f"  - 재시도율: {retry_data.get('retry_rate', 0):.1f}%")
    print(f"  - 1차 성공률: {retry_data.get('first_attempt_success_rate', 0):.1f}%")
    print(f"  - 최종 성공률: {retry_data.get('eventual_success_rate', 0):.1f}%")
    print(f"  - 개선율: {retry_data.get('improvement_rate', 0):.1f}%")


    # ========================================================================
    # Tracker 9-11: Layer 2 (간단히 소개)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Tracker 9-11: Layer 2 Agentic AI Metrics (간단 소개)")
    print("=" * 70)
    print("이 Tracker들은 Level 2 Advanced 예제에서 상세히 다룹니다:")
    print("")
    print("9. ToolSelectionTracker → Tool Selection Accuracy")
    print("   - 올바른 도구 선택 정확도 (Precision, Recall, F1)")
    print("   - Golden Dataset의 expected_tools와 비교")
    print("")
    print("10. AgentCoordinationTracker → Agent Coordination")
    print("    - 멀티 에이전트 협업 품질")
    print("    - CrewAI, AutoGen 통합")
    print("")
    print("11. WorkflowExecutionTracker → Workflow Execution")
    print("    - 워크플로우 실행 성공률")
    print("    - LangGraph 상태 전이 추적")
    print("")
    print("👉 다음 예제에서 계속...")


    # ========================================================================
    # 결과 저장
    # ========================================================================
    print("\n" + "=" * 70)
    print("💾 결과 저장")
    print("=" * 70)

    filename = f"{FILE_PREFIX}layer1_trackers_result.json"
    monitor.save_to_file(filename)
    print(f"✓ 저장 완료: {filename}")


    # ========================================================================
    # 요약
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 Layer 1 Trackers 학습 완료!")
    print("=" * 70)

    print("\n📊 학습한 Tracker 요약:")
    print("-" * 70)
    print("Layer 1 (8개) - 무료, API 키 불필요:")
    print("  1. TaskCompletionTracker → TCR")
    print("  2. AccuracyEvaluator → Accuracy")
    print("  3. HallucinationDetector → Hallucination Rate")
    print("  4. ResponseQualityEvaluator → Quality Score")
    print("  5. LatencyTracker → Latency")
    print("  6. TokenEconomyTracker → Cost")
    print("  7. ToolCallAnalyzer → Tool Efficiency")
    print("  8. RetryCorrectionTracker → Retry Success Rate")
    print("")
    print("Layer 2 (3개) - 무료, 멀티 에이전트 전용:")
    print("  9. ToolSelectionTracker → Tool Selection Accuracy")
    print("  10. AgentCoordinationTracker → Agent Coordination")
    print("  11. WorkflowExecutionTracker → Workflow Execution")

    print("\n✅ 다음 예제: 03_taskresult_helpers.py")
    print("   → 하드코딩 없이 동적으로 지표 계산하는 방법")


if __name__ == "__main__":
    main()
