#!/usr/bin/env python3
"""
Level 1 Foundation - Example 03: TaskResult Helpers (동적 계산)
================================================================

🎯 목표: 하드코딩 없이 실제 값을 동적으로 계산

📚 학습 내용:
1. calculate_completion_score() - 완료도 자동 계산
2. calculate_accuracy_score() - 정확도 자동 계산 (4가지 유사도)
3. estimate_tokens() - 토큰 수 추정
4. extract_tokens_from_openai() - OpenAI API 응답 파싱
5. create_taskresult() - 완전 자동 생성

🎓 Best Practice:
❌ 나쁜 예: accuracy_score=0.85  # 하드코딩
✅ 좋은 예: calculate_accuracy_score(response, ground_truth)

🔍 Dashboard 확인:
- 🎯 Core Metrics 탭: 동적 계산된 정확한 지표

⏱️ 예상 소요 시간: 10분
💰 비용: 무료

실행 방법:
    python level_1_foundation/03_taskresult_helpers.py
"""

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.helpers.taskresult_helpers import (
    calculate_completion_score,
    calculate_accuracy_score,
    estimate_tokens,
    normalize_text,
    extract_tokens_from_openai,
    extract_tokens_from_langchain,
)
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L1-03]_"


def main():
    """TaskResult Helpers - 동적 계산 함수 마스터"""

    print("=" * 70)
    print("🎯 Level 1 Foundation - TaskResult Helpers (동적 계산)")
    print("=" * 70)


    # ========================================================================
    # 왜 동적 계산이 중요한가?
    # ========================================================================
    print("\n" + "=" * 70)
    print("❓ 왜 동적 계산이 중요한가?")
    print("=" * 70)

    print("""
❌ 하드코딩의 문제점:
1. 평가 정확도 낮음 - 실제 값과 다름
2. 유지보수 어려움 - 매번 수동으로 계산
3. 일관성 없음 - 평가자마다 다른 기준
4. 신뢰성 낮음 - 검증 불가능

✅ 동적 계산의 장점:
1. 정확한 평가 - 실제 값을 자동 계산
2. 자동화 가능 - 대량 평가에 적합
3. 일관성 보장 - 항상 동일한 기준
4. 재현 가능 - 결과 검증 가능
    """)


    # ========================================================================
    # Helper 1: calculate_completion_score() - 완료도 계산
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Helper 1/5: calculate_completion_score()")
    print("=" * 70)
    print("역할: 작업 완료도 점수 계산 (0.0 ~ 1.0)")
    print("고려 요소:")
    print("  - 응답 길이")
    print("  - 에러 발생 여부")
    print("  - ground_truth와의 유사도 (제공 시)")
    print("")

    # Case 1: 정상 응답
    response_normal = "대한민국의 수도는 서울입니다."
    score_1 = calculate_completion_score(
        response=response_normal,
        expected_min_length=10,
        has_error=False
    )
    print(f"Case 1: 정상 응답")
    print(f"  Response: {response_normal}")
    print(f"  Completion Score: {score_1:.2f}")

    # Case 2: 짧은 응답
    response_short = "서울"
    score_2 = calculate_completion_score(
        response=response_short,
        expected_min_length=50,
        has_error=False
    )
    print(f"\nCase 2: 짧은 응답 (부분 점수)")
    print(f"  Response: {response_short}")
    print(f"  Completion Score: {score_2:.2f}")

    # Case 3: 에러 발생
    score_3 = calculate_completion_score(
        response="",
        expected_min_length=10,
        has_error=True
    )
    print(f"\nCase 3: 에러 발생")
    print(f"  Response: (없음)")
    print(f"  Completion Score: {score_3:.2f}")


    # ========================================================================
    # Helper 2: calculate_accuracy_score() - 정확도 계산
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Helper 2/5: calculate_accuracy_score()")
    print("=" * 70)
    print("역할: 정확도 계산 (4가지 유사도 메트릭 조합)")
    print("메트릭 가중치:")
    print("  - Token Overlap Ratio: 40%")
    print("  - Jaccard Similarity: 30%")
    print("  - LCS (Longest Common Subsequence): 20%")
    print("  - Character Similarity: 10%")
    print("")

    # Case 1: 완전 일치
    response_1 = "서울"
    ground_truth_1 = "서울"
    acc_1 = calculate_accuracy_score(response_1, ground_truth_1)
    print(f"Case 1: 완전 일치")
    print(f"  Response: {response_1}")
    print(f"  Ground Truth: {ground_truth_1}")
    print(f"  Accuracy: {acc_1:.3f} (100%)")

    # Case 2: 부분 일치
    response_2 = "대한민국의 수도는 서울입니다."
    ground_truth_2 = "서울"
    acc_2 = calculate_accuracy_score(response_2, ground_truth_2)
    print(f"\nCase 2: 부분 일치")
    print(f"  Response: {response_2}")
    print(f"  Ground Truth: {ground_truth_2}")
    print(f"  Accuracy: {acc_2:.3f}")

    # Case 3: 유사하지만 다른 표현
    response_3 = "한국의 수도는 Seoul이에요"
    ground_truth_3 = "서울"
    acc_3 = calculate_accuracy_score(response_3, ground_truth_3)
    print(f"\nCase 3: 유사하지만 다른 표현")
    print(f"  Response: {response_3}")
    print(f"  Ground Truth: {ground_truth_3}")
    print(f"  Accuracy: {acc_3:.3f}")

    # Case 4: 완전히 다름
    response_4 = "평양"
    ground_truth_4 = "서울"
    acc_4 = calculate_accuracy_score(response_4, ground_truth_4)
    print(f"\nCase 4: 완전히 다름")
    print(f"  Response: {response_4}")
    print(f"  Ground Truth: {ground_truth_4}")
    print(f"  Accuracy: {acc_4:.3f}")


    # ========================================================================
    # Helper 3: estimate_tokens() - 토큰 수 추정
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Helper 3/5: estimate_tokens()")
    print("=" * 70)
    print("역할: 텍스트 길이 기반 토큰 수 추정")
    print("추정 방식:")
    print("  - 영어: 문자 수 / 4")
    print("  - 한국어: 문자 수 / 2")
    print("  - 혼합: 언어별 비율 고려")
    print("")

    # 영어 텍스트
    text_en = "The capital of South Korea is Seoul."
    tokens_en = estimate_tokens(text_en)
    print(f"영어 텍스트:")
    print(f"  Text: {text_en}")
    print(f"  Length: {len(text_en)} chars")
    print(f"  Estimated Tokens: {tokens_en}")

    # 한국어 텍스트
    text_kr = "대한민국의 수도는 서울입니다."
    tokens_kr = estimate_tokens(text_kr)
    print(f"\n한국어 텍스트:")
    print(f"  Text: {text_kr}")
    print(f"  Length: {len(text_kr)} chars")
    print(f"  Estimated Tokens: {tokens_kr}")

    # 긴 텍스트
    text_long = """
    서울은 대한민국의 수도이자 최대 도시입니다.
    약 1천만 명의 인구가 살고 있으며, 한강을 중심으로 발전했습니다.
    조선시대의 5대 궁궐이 있으며, 현대와 전통이 공존하는 도시입니다.
    """
    tokens_long = estimate_tokens(text_long)
    print(f"\n긴 텍스트:")
    print(f"  Length: {len(text_long)} chars")
    print(f"  Estimated Tokens: {tokens_long}")


    # ========================================================================
    # Helper 4: create_taskresult() - 완전 자동 생성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Helper 4/5: create_taskresult()")
    print("=" * 70)
    print("역할: 모든 필드를 동적으로 계산하여 TaskResult 생성")
    print("자동 계산 항목:")
    print("  - completion_score: calculate_completion_score() 사용")
    print("  - accuracy_score: calculate_accuracy_score() 사용")
    print("  - tokens_used: estimate_tokens() 사용")
    print("  - success: 자동 판정")
    print("")

    # Example 1: 기본 사용
    task_1 = create_taskresult(
        task_id="auto_001",
        task_type="qa",
        question="대한민국의 수도는?",
        response="대한민국의 수도는 서울입니다.",
        ground_truth="서울",
        execution_time=1.2
    )

    print(f"✅ Example 1: 기본 사용")
    print(f"  Task ID: {task_1.task_id}")
    print(f"  Completion Score: {task_1.completion_score:.2f} (자동 계산)")
    print(f"  Accuracy Score: {task_1.accuracy_score:.3f} (자동 계산)")
    print(f"  Tokens Used: {task_1.tokens_used} (자동 추정)")
    print(f"  Success: {task_1.success}")

    # Example 2: Context 포함 (Hallucination 탐지용)
    task_2 = create_taskresult(
        task_id="auto_002",
        task_type="qa",
        question="서울의 인구는?",
        response="서울의 인구는 약 1천만 명입니다.",
        ground_truth="1천만 명",
        execution_time=0.9,
    )

    print(f"\n✅ Example 2: Context 포함")
    print(f"  Task ID: {task_2.task_id}")
    print(f"  Accuracy Score: {task_2.accuracy_score:.3f}")
    print(f"  Context 제공: Yes (Hallucination 탐지 가능)")


    # ========================================================================
    # 실전 예제: Monitor와 통합
    # ========================================================================
    print("\n" + "=" * 70)
    print("🚀 실전 예제: Monitor와 통합")
    print("=" * 70)

    monitor = PerformanceMonitor()

    # 여러 Task 자동 생성 및 기록
    qa_pairs = [
        {
            "question": "한글을 만든 사람은?",
            "response": "한글은 세종대왕이 창제했습니다.",
            "ground_truth": "세종대왕",
            "context": "한글은 1443년 조선 제4대 왕인 세종대왕이 창제한 문자입니다."
        },
        {
            "question": "태양계에서 가장 큰 행성은?",
            "response": "태양계에서 가장 큰 행성은 목성입니다.",
            "ground_truth": "목성",
            "context": "목성은 태양계에서 가장 큰 행성으로, 지구 질량의 약 318배입니다."
        },
        {
            "question": "광합성의 주요 산물은?",
            "response": "광합성의 주요 산물은 포도당과 산소입니다.",
            "ground_truth": "포도당과 산소",
            "context": "광합성은 빛 에너지를 이용해 이산화탄소와 물로부터 포도당과 산소를 만드는 과정입니다."
        },
    ]

    print("\n📝 3개 Task 자동 생성 및 평가:")
    for idx, qa in enumerate(qa_pairs, 1):
        # 🎯 핵심: create_taskresult()로 완전 자동 생성
        task = create_taskresult(
            task_id=f"helper_{idx:03d}",
            task_type="qa",
            question=qa["question"],
            response=qa["response"],
            ground_truth=qa["ground_truth"],
            execution_time=1.0 + (idx * 0.2),
        )

        # 기록
        monitor.record_task(
            task,
            response=qa["response"],
            ground_truth=qa["ground_truth"]
        )

        print(f"  {idx}. {task.task_id}: Acc={task.accuracy_score:.3f}, "
              f"Tokens={task.tokens_used['total']}")

    # 리포트 생성
    report = monitor.generate_report()
    print(f"\n✅ 평가 결과:")
    print(f"  - 총 평가: {report.total_tasks}개")

    # 중첩 dict에서 값 추출
    tcr_data = report.accuracy_metrics.get('tcr', {})
    accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
    print(f"  - TCR: {tcr_data.get('tcr', 0):.1f}%")
    print(f"  - Accuracy: {accuracy_data.get('avg', 0) * 100:.1f}%")


    # ========================================================================
    # 잘못된 사용 예제 (비교용)
    # ========================================================================
    print("\n" + "=" * 70)
    print("❌ 잘못된 사용 예제 (하드코딩)")
    print("=" * 70)

    print("""
# ❌ 나쁜 예: 하드코딩
from agent_evaluator import TaskResult, TaskType
from datetime import datetime

task_bad = TaskResult(
    task_id="bad_001",
    task_type=TaskType.QA.value,
    success=True,
    completion_score=1.0,              # ❌ 하드코딩!
    accuracy_score=0.85,               # ❌ 하드코딩!
    execution_time=1.5,
    tokens_used={"input": 100, "output": 50},  # ❌ 추정값
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now()
)

문제점:
1. completion_score=1.0 → 실제 완료도가 아닐 수 있음
2. accuracy_score=0.85 → 실제 정확도 계산 없음
3. tokens_used → 추정값, 실제 API 응답과 다름
4. 유지보수 어려움, 일관성 없음
    """)

    print("\n" + "=" * 70)
    print("✅ 올바른 사용 예제 (동적 계산)")
    print("=" * 70)

    print("""
# ✅ 좋은 예: 동적 계산
from agent_evaluator import create_taskresult

task_good = create_taskresult(
    task_id="good_001",
    task_type="qa",
    question="한국의 수도는?",
    response="대한민국의 수도는 서울입니다.",
    ground_truth="서울",
    execution_time=1.2
)

장점:
1. completion_score → 자동 계산 (길이, 유사도 기반)
2. accuracy_score → 4가지 유사도 메트릭 조합
3. tokens_used → 실제 텍스트 기반 추정
4. 일관성 보장, 재현 가능
    """)


    # ========================================================================
    # 요약
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 TaskResult Helpers 학습 완료!")
    print("=" * 70)

    print("\n📚 학습한 Helper 함수:")
    print("-" * 70)
    print("1. calculate_completion_score()")
    print("   → 완료도 자동 계산 (길이, 에러, 유사도)")
    print("")
    print("2. calculate_accuracy_score()")
    print("   → 정확도 자동 계산 (4가지 유사도 메트릭)")
    print("")
    print("3. estimate_tokens()")
    print("   → 토큰 수 추정 (텍스트 길이 기반)")
    print("")
    print("4. create_taskresult()")
    print("   → TaskResult 완전 자동 생성 (모든 필드 동적 계산)")

    print("\n🎯 핵심 교훈:")
    print("-" * 70)
    print("❌ 하드코딩 → 부정확, 유지보수 어려움")
    print("✅ 동적 계산 → 정확, 자동화 가능, 일관성 보장")

    print("\n✅ 다음 예제: 04_thresholds_validation.py")
    print("   → 임계값 설정 및 Pass/Fail 판정")


if __name__ == "__main__":
    main()
