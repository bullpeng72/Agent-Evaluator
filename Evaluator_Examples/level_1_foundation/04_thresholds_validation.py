#!/usr/bin/env python3
"""
Level 1 Foundation - Example 04: Thresholds & Validation
==========================================================

🎯 목표: 임계값 시스템 마스터

📚 학습 내용:
1. thresholds 설정 (Layer 1, 2, 3 전체)
2. compare_with_thresholds() - 실시간 비교
3. Pass/Fail 판정
4. 임계값 최적화 전략

🔍 Dashboard 확인:
- 📊 Overview 탭: Pass/Fail 상태
- 💡 Insights 탭: 임계값 기반 경고
- 📝 데이터편집 > 임계값 설정: GUI로 조정

⏱️ 예상 소요 시간: 12분
💰 비용: 무료

실행 방법:
    python level_1_foundation/04_thresholds_validation.py
"""

from agent_evaluator import PerformanceMonitor, create_taskresult

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L1-04]_"


def main():
    """Thresholds & Validation - 임계값 시스템 마스터"""

    print("=" * 70)
    print("🎯 Level 1 Foundation - Thresholds & Validation")
    print("=" * 70)


    # ========================================================================
    # Step 1: 임계값이란 무엇인가?
    # ========================================================================
    print("\n" + "=" * 70)
    print("❓ 임계값 (Thresholds)이란?")
    print("=" * 70)

    print("""
임계값 (Thresholds)은 각 지표의 **합격 기준**입니다.

📌 목적:
1. 품질 게이트 (Quality Gate) - 배포 가능 여부 판단
2. 자동 경고 - 기준 미달 시 알림
3. 지속적 개선 - 성능 추적 및 목표 설정

📌 예시:
- TCR ≥ 90% → 합격 (Pass)
- TCR < 90% → 불합격 (Fail) → 배포 중단

📌 적용 분야:
- 개발 환경: 느슨한 기준 (실험용)
- Staging 환경: 중간 기준 (테스트용)
- Production 환경: 엄격한 기준 (실제 서비스)
    """)


    # ========================================================================
    # Step 2: 임계값 설정 (Layer 1)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 2: 임계값 설정 (Layer 1)")
    print("=" * 70)

    # Hallucination detection 활성화
    monitor = PerformanceMonitor(enable_hallucination_detection=True)

    # Layer 1 임계값 설정
    monitor.thresholds = {
        # ========== 높을수록 좋은 지표 (≥) ==========
        'tcr': 90.0,                    # TCR ≥ 90%
        'accuracy': 85.0,               # Accuracy ≥ 85%
        'quality': 7.0,                 # Quality ≥ 7/10
        'retry_success_rate': 70.0,    # Retry Success ≥ 70%
        'tool_efficiency': 80.0,        # Tool Efficiency ≥ 80%

        # ========== 낮을수록 좋은 지표 (≤) ==========
        'hallucination': 5.0,           # Hallucination ≤ 5%
        'latency': 3.0,                 # Latency ≤ 3초
        'cost_per_task': 0.10,          # Cost ≤ $0.10
    }

    print("✅ Layer 1 임계값 설정 완료:")
    print("-" * 70)
    print("높을수록 좋은 지표 (≥):")
    print(f"  - TCR: ≥ {monitor.thresholds['tcr']}%")
    print(f"  - Accuracy: ≥ {monitor.thresholds['accuracy']}%")
    print(f"  - Quality: ≥ {monitor.thresholds['quality']}/10")
    print(f"  - Retry Success: ≥ {monitor.thresholds['retry_success_rate']}%")
    print(f"  - Tool Efficiency: ≥ {monitor.thresholds['tool_efficiency']}%")
    print("")
    print("낮을수록 좋은 지표 (≤):")
    print(f"  - Hallucination: ≤ {monitor.thresholds['hallucination']}%")
    print(f"  - Latency: ≤ {monitor.thresholds['latency']}초")
    print(f"  - Cost per Task: ≤ ${monitor.thresholds['cost_per_task']}")


    # ========================================================================
    # Step 3: 테스트 데이터 생성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 3: 테스트 데이터 생성")
    print("=" * 70)

    test_cases = [
        {
            "question": "대한민국의 수도는?",
            "response": "대한민국의 수도는 서울입니다.",
            "ground_truth": "서울",
            "context": "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다."
        },
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
            "question": "광합성의 산물은?",
            "response": "광합성의 산물은 포도당과 산소입니다.",
            "ground_truth": "포도당과 산소",
            "context": "광합성은 빛 에너지를 이용해 이산화탄소와 물로부터 포도당과 산소를 만드는 과정입니다."
        },
        {
            "question": "물의 끓는점은?",
            "response": "물의 끓는점은 섭씨 100도입니다.",
            "ground_truth": "100도",
            "context": "물은 1기압에서 섭씨 100도에서 끓습니다."
        },
    ]

    print(f"📝 {len(test_cases)}개 테스트 케이스 생성 중...")

    for idx, test in enumerate(test_cases, 1):
        task = create_taskresult(
            task_id=f"threshold_test_{idx:03d}",
            task_type="qa",
            question=test["question"],
            response=test["response"],
            ground_truth=test["ground_truth"],
            execution_time=1.0 + (idx * 0.2),
        )

        monitor.record_task(
            task,
            context=test["context"],
            response=test["response"],
            ground_truth=test["ground_truth"]
        )

    print(f"✓ {len(test_cases)}개 Task 기록 완료")


    # ========================================================================
    # Step 4: 임계값 비교 (compare_with_thresholds)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 4: 임계값 비교 (실시간 검증)")
    print("=" * 70)

    comparison = monitor.compare_with_thresholds()

    print("\n✅ 임계값 비교 결과:")
    print("-" * 70)

    # Pass/Fail 카운트
    pass_count = sum(1 for metric in comparison.values() if metric['status'] == 'pass')
    fail_count = sum(1 for metric in comparison.values() if metric['status'] == 'fail')
    total_count = len(comparison)

    for metric_key, result in comparison.items():
        status_icon = "✅" if result['status'] == 'pass' else "❌"
        direction = "≥" if result['direction'] == 'higher' else "≤"

        print(f"{status_icon} {result['name']}")
        print(f"   실제 값: {result['value']:.2f}{result['unit']}")
        print(f"   임계값: {direction} {result['threshold']:.2f}{result['unit']}")
        print(f"   상태: {result['status'].upper()}")
        print("")

    # 전체 판정
    overall_pass = fail_count == 0

    print("=" * 70)
    print(f"📊 전체 평가 결과:")
    print(f"  - 합격: {pass_count}/{total_count}")
    print(f"  - 불합격: {fail_count}/{total_count}")
    print(f"  - 최종 판정: {'✅ PASS' if overall_pass else '❌ FAIL'}")
    print("=" * 70)


    # ========================================================================
    # Step 5: 임계값 최적화 전략
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 5: 임계값 최적화 전략")
    print("=" * 70)

    print("""
📊 임계값 설정 Best Practice:

1. 데이터 기반 설정
   - 최소 100개 Task 평가 후 설정
   - P90 또는 P95 백분위수 사용
   - 점진적 강화 (처음부터 높지 않게)

2. 환경별 차등 적용
   - Dev: TCR ≥ 70% (실험 허용)
   - Staging: TCR ≥ 85% (안정성 확인)
   - Prod: TCR ≥ 95% (높은 품질)

3. 지표별 우선순위
   - 필수 지표: TCR, Hallucination (반드시 통과)
   - 권장 지표: Accuracy, Quality (가이드라인)
   - 참고 지표: Latency, Cost (최적화 목표)

4. 지속적 개선
   - 매월 검토 및 조정
   - 성능 향상 시 임계값 상향
   - 새로운 지표 추가

5. 예외 처리
   - 특정 TaskType은 별도 기준
   - 신규 기능은 낮은 기준 시작
   - 점진적 강화 로드맵
    """)


    # ========================================================================
    # Step 7: Dashboard에서 임계값 관리
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 7: Dashboard에서 임계값 관리")
    print("=" * 70)

    print("""
Dashboard를 사용한 임계값 관리:

1. 임계값 설정 페이지
   📝 데이터편집 > 임계값 설정

2. 시각적 조정
   - 슬라이더로 간편 조정
   - Layer 1, 2, 3 탭 분리
   - 실시간 영향 확인

3. 히스토리 관리
   - 버전 관리 (스냅샷)
   - 변경 이력 추적
   - 롤백 기능

4. 비교 분석
   - 여러 임계값 세트 비교
   - A/B 테스트
   - 최적 기준 찾기
    """)


    # ========================================================================
    # Step 8: 결과 저장 및 Exit Code 설정
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 8: 결과 저장 및 Exit Code 설정")
    print("=" * 70)

    # 결과 저장
    filename = f"{FILE_PREFIX}thresholds_validation_result.json"
    monitor.save_to_file(filename)
    print(f"✓ 결과 저장: {filename}")

    # 최종 판정
    if overall_pass:
        print("\n✅ PASS: 모든 임계값 기준 충족")
        print("   → 모든 지표가 기준을 만족합니다")
    else:
        print("\n❌ FAIL: 일부 임계값 기준 미달")
        print(f"   → 불합격 지표: {fail_count}개")

        # 불합격 지표 상세
        print("\n   불합격 지표 상세:")
        for metric_key, result in comparison.items():
            if result['status'] == 'fail':
                direction = "≥" if result['direction'] == 'higher' else "≤"
                print(f"   - {result['name']}: {result['value']:.2f} "
                      f"(기준: {direction} {result['threshold']:.2f})")


    # ========================================================================
    # 요약
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 Thresholds & Validation 학습 완료!")
    print("=" * 70)

    print("\n📚 학습한 내용:")
    print("-" * 70)
    print("1. 임계값 (Thresholds) 개념")
    print("   → 품질 게이트, 합격 기준")
    print("")
    print("2. 임계값 설정")
    print("   → monitor.thresholds = {...}")
    print("")
    print("3. 임계값 비교")
    print("   → compare_with_thresholds()")
    print("")
    print("4. Pass/Fail 판정")
    print("   → 자동 경고 및 배포 차단")
    print("")
    print("5. 최적화 전략")
    print("   → 데이터 기반, 환경별 차등")

    print("\n🎯 핵심 포인트:")
    print("-" * 70)
    print("✅ 임계값은 품질 게이트의 핵심")
    print("✅ 환경별로 다른 기준 적용")
    print("✅ Dashboard에서 시각적 관리")

    print("\n✅ Level 1 Foundation 완료!")
    print("   다음은 Level 2 Advanced로 넘어갑니다.")


if __name__ == "__main__":
    main()
