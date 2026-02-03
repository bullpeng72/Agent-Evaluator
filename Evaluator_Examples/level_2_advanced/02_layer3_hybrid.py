#!/usr/bin/env python3
"""
Level 2 Advanced - Example 05: Layer 3 Hybrid Monitor
======================================================

🎯 목표: HybridPerformanceMonitor로 DeepEval + Ragas 사용

📚 학습 내용:
1. HybridPerformanceMonitor 생성 및 설정
2. DeepEval 5종 메트릭 (G-Eval, Hallucination, Toxicity, Bias, Answer Relevancy)
3. Ragas 4종 메트릭 (Faithfulness, Context Recall, Precision, Answer Relevancy)
4. Layer 1 + Layer 3 통합 평가
5. 비용 관리 전략

🔍 Dashboard 확인:
- 🔬 Advanced 탭: DeepEval + Ragas 지표
- 📊 Overview: Layer 1 + Layer 3 통합

⏱️ 예상 소요 시간: 20분
💰 비용: ~$0.05-0.15 (10개 Task 기준, gpt-4o-mini 사용)

⚠️  주의사항:
- OpenAI API 키 필요 (.env 파일 또는 환경 변수)
- pip install deepeval ragas langchain-openai 필요

실행 방법:
    python level_2_advanced/05_layer3_hybrid.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 🔧 ragas 의존성 문제 해결 (check_dependencies보다 먼저 설정 필요)
# agent_evaluator 라이브러리 내부에서도 설정하지만, 예제 파일에서 직접 import할 때를 위해 명시
os.environ.setdefault('GIT_PYTHON_REFRESH', 'quiet')

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L2-02]_"


def check_dependencies():
    """필수 라이브러리 및 API 키 확인"""
    print("=" * 70)
    print("🔍 환경 확인")
    print("=" * 70)

    # 1. OpenAI API 키 확인
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("\n❌ OpenAI API 키가 설정되지 않았습니다.")
        print("\n설정 방법:")
        print("1. .env 파일에 추가:")
        print('   OPENAI_API_KEY="your-key-here"')
        print("\n2. 또는 환경 변수로 설정:")
        print('   export OPENAI_API_KEY="your-key-here"')
        print("\n⚠️  Layer 3 메트릭은 API 키 없이 사용할 수 없습니다.")
        print("   Layer 1 메트릭만 사용하려면 PerformanceMonitor를 사용하세요.")
        return False

    print(f"✅ OpenAI API 키 확인됨: {api_key[:10]}...")

    # 2. 라이브러리 확인
    missing_libs = []

    try:
        import deepeval
        print(f"✅ deepeval 설치됨 (v{deepeval.__version__})")
    except ImportError:
        missing_libs.append("deepeval")
        print("❌ deepeval 설치 필요")

    try:
        import ragas
        print(f"✅ ragas 설치됨 (v{ragas.__version__})")
    except ImportError:
        missing_libs.append("ragas")
        print("❌ ragas 설치 필요")

    try:
        from langchain_openai import ChatOpenAI
        print("✅ langchain-openai 설치됨")
    except ImportError:
        missing_libs.append("langchain-openai")
        print("❌ langchain-openai 설치 필요")

    if missing_libs:
        print(f"\n❌ 다음 라이브러리를 설치하세요:")
        print(f"   pip install {' '.join(missing_libs)}")
        return False

    print("\n✅ 모든 종속성 확인 완료!")
    return True


def main():
    """HybridPerformanceMonitor 실습"""

    print("=" * 70)
    print("🎯 Level 2 Advanced - Layer 3 Hybrid Monitor")
    print("=" * 70)


    # ========================================================================
    # Step 1: 환경 확인
    # ========================================================================
    if not check_dependencies():
        print("\n⚠️  환경 설정 후 다시 실행하세요.")
        return


    # ========================================================================
    # Step 2: HybridPerformanceMonitor 생성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 2: HybridPerformanceMonitor 생성")
    print("=" * 70)

    from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor

    print("\n🔧 Monitor 생성 중...")
    print("-" * 70)

    # HybridPerformanceMonitor 생성
    # - use_deepeval: DeepEval 활성화 (G-Eval, Hallucination, Toxicity 등)
    # - use_ragas: Ragas 활성화 (Faithfulness, Context Recall 등)
    # - deepeval_model: 평가에 사용할 모델 (비용 절감을 위해 gpt-4o-mini 사용)
    # - ragas_model: 평가에 사용할 모델

    monitor = HybridPerformanceMonitor(
        use_deepeval=True,
        use_ragas=True,
        enable_hallucination_detection=True  # Layer 1 환각 탐지도 활성화
    )

    print("\n✅ HybridPerformanceMonitor 생성 완료!")
    print(f"  활성화된 Provider: {', '.join(monitor.enabled_providers)}")


    # ========================================================================
    # Step 3: Layer 3 Metrics 이해
    # ========================================================================
    print("\n" + "=" * 70)
    print("📚 Step 3: Layer 3 Metrics 이해")
    print("=" * 70)

    print("""
🔬 DeepEval Metrics (5종):

1. G-Eval
   - LLM을 평가자로 사용한 전반적 품질 평가
   - Coherence, Consistency, Fluency, Relevance 종합
   - 사용: 오픈엔디드 질문, 창작 콘텐츠

2. Hallucination Score
   - 컨텍스트 충실도 평가 (의미론적 환각 탐지)
   - Layer 1의 룰 기반보다 정확
   - 사용: RAG 시스템, 문서 기반 QA

3. Toxicity Score
   - 유해 콘텐츠 탐지 (욕설, 공격적 표현)
   - 사용: 고객 대응 챗봇, 공개 플랫폼

4. Bias Score
   - 편향성 탐지 (성별, 인종, 나이, 직업 등)
   - 사용: HR AI, 교육 콘텐츠

5. Answer Relevancy
   - 답변이 질문과 얼마나 관련 있는지
   - 사용: QA 시스템, 검색 기반 답변

🔬 Ragas Metrics (4종) - RAG 전용:

1. Faithfulness
   - 답변이 컨텍스트에 사실적으로 일치하는지
   - 핵심 RAG 메트릭

2. Context Recall
   - 검색된 컨텍스트가 정답을 포함하는지
   - 검색 품질 평가

3. Context Precision
   - 검색된 컨텍스트의 정확도
   - 불필요한 정보 최소화

4. Answer Relevancy
   - 질문에 대한 답변의 관련성
   - DeepEval과 유사하지만 RAG 특화

💰 비용 (gpt-4o-mini 기준):
- DeepEval: ~$0.01-0.03 per task
- Ragas: ~$0.02-0.05 per task
- 총: ~$0.03-0.08 per task

📊 비교:
- Layer 1 (Native): 무료, 빠름 (~60% 정확도)
- Layer 3 (Hybrid): 비용, 느림 (~90% 정확도)
    """)


    # ========================================================================
    # Step 4: 테스트 데이터 준비
    # ========================================================================
    print("\n" + "=" * 70)
    print("📝 Step 4: 테스트 데이터 준비")
    print("=" * 70)

    test_cases = [
        {
            "question": "대한민국의 수도는 어디인가요?",
            "response": "대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 대도시입니다.",
            "context": "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다.",
            "ground_truth": "서울"
        },
        {
            "question": "한글을 창제한 사람은?",
            "response": "한글은 조선시대 세종대왕께서 1443년에 창제하셨습니다.",
            "context": "한글은 1443년 조선 제4대 왕인 세종대왕이 창제한 문자입니다.",
            "ground_truth": "세종대왕"
        },
        {
            "question": "태양계에서 가장 큰 행성은?",
            "response": "태양계에서 가장 큰 행성은 목성입니다.",
            "context": "목성은 태양계에서 가장 큰 행성으로, 지구 질량의 약 318배입니다.",
            "ground_truth": "목성"
        },
    ]

    print(f"✓ {len(test_cases)}개 테스트 케이스 준비 완료")


    # ========================================================================
    # Step 5: Layer 1 + Layer 3 통합 평가
    # ========================================================================
    print("\n" + "=" * 70)
    print("🚀 Step 5: Layer 1 + Layer 3 통합 평가")
    print("=" * 70)

    print("\n⚠️  주의: API 호출이 발생하여 시간이 걸립니다 (약 30-60초)")
    print("   비용: ~$0.09-0.24 (3 tasks × ~$0.03-0.08)")
    print("")

    from agent_evaluator import create_taskresult

    for idx, test in enumerate(test_cases, 1):
        print(f"\n평가 {idx}/{len(test_cases)}: {test['question'][:30]}...")

        # Layer 1: TaskResult 생성
        task = create_taskresult(
            task_id=f"hybrid_{idx:03d}",
            task_type="qa",
            question=test["question"],
            response=test["response"],
            ground_truth=test["ground_truth"],
            execution_time=1.2,
        )

        # Layer 1 + Layer 3: 통합 기록
        # - Layer 1: 자동 계산 (TCR, Accuracy, Hallucination 등)
        # - Layer 3: API 호출 (DeepEval, Ragas)
        monitor.record_task(
            task,
            input_text=test["question"],
            output_text=test["response"],
            expected_output=test["ground_truth"]
        )

        print(f"  ✓ Layer 1 완료: Accuracy={task.accuracy_score:.3f}")
        print(f"  ⏳ Layer 3 평가 중... (API 호출)")


    print(f"\n✅ {len(test_cases)}개 Task 평가 완료!")


    # ========================================================================
    # Step 6: 결과 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 6: 평가 결과 분석")
    print("=" * 70)

    report = monitor.generate_report()

    print(f"\n📊 Layer 1 Metrics (Native - 무료):")
    tcr_data = report.accuracy_metrics.get('tcr', {})
    accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
    hallucination_data = report.accuracy_metrics.get('hallucination', {})
    print(f"  - TCR: {tcr_data.get('tcr', 0):.1f}%")
    print(f"  - Accuracy: {accuracy_data.get('avg', 0) * 100:.1f}%")
    print(f"  - Hallucination Rate: {hallucination_data.get('rate', 0):.1f}%")

    # RAG 메트릭 요약 (Layer 3)
    rag_summary = monitor.get_rag_metrics_summary()

    if rag_summary:
        print(f"\n🔬 Layer 3 Metrics (Advanced - 유료):")

        if rag_summary.get('faithfulness'):
            print(f"  - Faithfulness: {rag_summary['faithfulness'].get('avg', 0):.3f}")

        if rag_summary.get('answer_relevancy'):
            print(f"  - Answer Relevancy: {rag_summary['answer_relevancy'].get('avg', 0):.3f}")

        if rag_summary.get('context_recall'):
            print(f"  - Context Recall: {rag_summary['context_recall'].get('avg', 0):.3f}")

        if rag_summary.get('context_precision'):
            print(f"  - Context Precision: {rag_summary['context_precision'].get('avg', 0):.3f}")


    # ========================================================================
    # Step 7: 비용 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("💰 Step 7: 비용 분석")
    print("=" * 70)

    token_data = monitor.token_tracker.get_usage_stats()

    print(f"\n💰 비용 요약:")
    print(f"  - Layer 1: $0.00 (무료)")
    print(f"  - Layer 3 (추정): ~${len(test_cases) * 0.06:.2f}")
    print(f"  - Task당 평균: ~$0.06")
    print(f"  - 총 Task: {len(test_cases)}개")

    print(f"\n📊 토큰 사용량:")
    print(f"  - 총 토큰: {token_data.get('total_tokens', 0):,}개")
    print(f"  - 총 비용: ${token_data.get('total_cost', 0):.4f}")


    # ========================================================================
    # Step 8: 결과 저장
    # ========================================================================
    print("\n" + "=" * 70)
    print("💾 Step 8: 결과 저장")
    print("=" * 70)

    filename = f"{FILE_PREFIX}layer3_hybrid_result.json"
    monitor.save_to_file(filename)

    print(f"✓ 저장 완료: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")


    # ========================================================================
    # Step 9: Layer 1 vs Layer 3 비교
    # ========================================================================
    print("\n" + "=" * 70)
    print("📈 Step 9: Layer 1 vs Layer 3 비교")
    print("=" * 70)

    print("""
📊 Layer 1 (Native) vs Layer 3 (Hybrid):

| 항목 | Layer 1 | Layer 3 |
|------|---------|---------|
| 비용 | 무료 | ~$0.03-0.08/task |
| 속도 | 빠름 (<1ms) | 느림 (10-30초/task) |
| 정확도 | 중간 (~60%) | 높음 (~90%) |
| API 키 | 불필요 | OpenAI 필요 |
| 사용 | 대량 평가 | 중요 Task |

🎯 전략:
1. Layer 1로 전체 평가 (100%)
2. Layer 3로 샘플 평가 (10-20%)
3. 중요 Task만 Layer 3 적용

💡 ROI:
- Layer 1: 무료, 기본 품질 확보
- Layer 3: 비용 대비 정확도 20-30% 향상
- 샘플링: 비용 90% 절감, 품질 손실 < 5%
    """)


    # ========================================================================
    # Dashboard 확인 안내
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 Layer 3 Hybrid 평가 완료!")
    print("=" * 70)

    print("""
📊 Dashboard에서 확인하기:

1. Dashboard 실행:
   cd Dashboard
   streamlit run streamlit_dashboard.py

2. 파일 선택:
   → layer3_hybrid_result.json

3. 확인할 탭:
   📊 Overview: Layer 1 + Layer 3 통합
   🔬 Advanced: DeepEval, Ragas 상세
   ⚡ Performance: 비용 분석

4. 비교 분석:
   - Layer 1 전용 결과와 비교
   - 정확도 향상 확인
   - 비용 대비 효과 분석
    """)

    print("\n✅ 다음 예제: 03_rag_system.py")
    print("   → RAG 시스템 완전 평가 (Ragas 4대 지표)")


if __name__ == "__main__":
    main()
