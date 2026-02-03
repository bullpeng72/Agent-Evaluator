#!/usr/bin/env python3
"""
Level 2 Advanced - Example 03: RAG System 완전 평가
====================================================

🎯 목표: RAG 시스템 전체 평가 (Retrieval + Generation)

📚 학습 내용:
1. RAG 파이프라인 구성 (Retrieval → Generation)
2. Ragas 4대 지표 완전 활용
   - Faithfulness: 생성 답변의 컨텍스트 충실도
   - Context Recall: 검색된 컨텍스트의 정답 포함도
   - Context Precision: 검색 정확도
   - Answer Relevancy: 답변의 질문 관련성
3. Retrieval 품질 vs Generation 품질 분리 분석
4. RAG 시스템 최적화 전략

🔍 Dashboard 확인:
- 🔬 Advanced 탭: Ragas 4대 지표
- 📊 Overview: Retrieval/Generation 분리 분석

⏱️ 예상 소요 시간: 25분
💰 비용: ~$0.10-0.20 (5개 Task 기준, gpt-4o-mini 사용)

⚠️  주의사항:
- OpenAI API 키 필요 (.env 파일 또는 환경 변수)
- pip install ragas langchain-openai 필요

실행 방법:
    python level_2_advanced/03_rag_system.py
"""

import os
from dotenv import load_dotenv
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir

# 🔧 ragas 의존성 문제 해결 (check_dependencies보다 먼저 설정 필요)
# agent_evaluator 라이브러리 내부에서도 설정하지만, 예제 파일에서 직접 import할 때를 위해 명시
os.environ.setdefault('GIT_PYTHON_REFRESH', 'quiet')

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L2-03]_"


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
        return False

    print(f"✅ OpenAI API 키 확인됨: {api_key[:10]}...")

    # 2. 라이브러리 확인
    missing_libs = []

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


def simulate_retrieval(question: str, knowledge_base: list) -> list:
    """
    간단한 키워드 기반 검색 시뮬레이션
    실제로는 Vector DB (FAISS, Pinecone 등) 사용
    """
    # 키워드 매칭으로 관련 문서 검색
    question_lower = question.lower()

    # 각 문서에 점수 부여
    scored_docs = []
    for doc in knowledge_base:
        score = 0
        doc_lower = doc.lower()

        # 간단한 키워드 매칭
        keywords = question_lower.split()
        for keyword in keywords:
            if keyword in doc_lower:
                score += 1

        if score > 0:
            scored_docs.append((score, doc))

    # 점수순 정렬 후 상위 3개 반환
    scored_docs.sort(reverse=True, key=lambda x: x[0])
    return [doc for _, doc in scored_docs[:3]]


def simulate_generation(question: str, context: list) -> str:
    """
    LLM 생성 시뮬레이션
    실제로는 OpenAI/Anthropic API 사용
    """
    # 컨텍스트 결합
    context_text = "\n".join(context)

    # 간단한 규칙 기반 생성 (실제로는 LLM 호출)
    question_lower = question.lower()

    if "수도" in question_lower and "서울" in context_text:
        return "대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 대도시로, 약 1천만 명의 인구가 살고 있습니다."

    elif "한글" in question_lower and "세종" in context_text:
        return "한글은 조선시대 세종대왕께서 1443년에 창제하셨습니다. 훈민정음이라는 이름으로 반포되었습니다."

    elif "목성" in question_lower and "태양계" in context_text:
        return "태양계에서 가장 큰 행성은 목성입니다. 목성은 지구 질량의 약 318배에 달합니다."

    elif "광합성" in question_lower and "식물" in context_text:
        return "광합성의 산물은 포도당과 산소입니다. 식물은 빛 에너지를 이용해 이산화탄소와 물로부터 포도당을 합성합니다."

    elif "dna" in question_lower.lower() and "유전" in context_text:
        return "DNA는 생명체의 유전 정보를 담고 있는 분자입니다. 이중나선 구조를 가지며 A, T, G, C 네 가지 염기로 구성됩니다."

    else:
        # 컨텍스트 기반 기본 응답
        if context:
            return f"관련 정보를 바탕으로 답변하면: {context[0][:100]}"
        else:
            return "죄송합니다. 해당 질문에 대한 정보를 찾을 수 없습니다."


def main():
    """RAG 시스템 완전 평가"""

    print("=" * 70)
    print("🎯 Level 2 Advanced - RAG System 완전 평가")
    print("=" * 70)


    # ========================================================================
    # Step 1: 환경 확인
    # ========================================================================
    if not check_dependencies():
        print("\n⚠️  환경 설정 후 다시 실행하세요.")
        return


    # ========================================================================
    # Step 2: HybridPerformanceMonitor 생성 (Ragas 전용)
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 2: HybridPerformanceMonitor 생성")
    print("=" * 70)

    from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor

    print("\n🔧 Monitor 생성 중 (Ragas 전용)...")

    # 🎯 개선: path_helpers로 자동 경로 감지
    results_dir = get_evaluation_results_dir()
    monitor = HybridPerformanceMonitor(
        output_dir=str(results_dir),
        use_deepeval=False,  # DeepEval 비활성화
        use_ragas=True,      # Ragas만 활성화 (RAG 전용)
        enable_hallucination_detection=True  # Layer 1 환각 탐지도 활성화
    )

    print("✅ HybridPerformanceMonitor 생성 완료!")
    print(f"  활성화된 Provider: {', '.join(monitor.enabled_providers)}")


    # ========================================================================
    # Step 3: Ragas 4대 지표 이해
    # ========================================================================
    print("\n" + "=" * 70)
    print("📚 Step 3: Ragas 4대 지표 이해")
    print("=" * 70)

    print("""
🔬 Ragas Metrics (RAG 전용):

1. Faithfulness (충실도) - Generation 평가
   - 생성된 답변이 검색된 컨텍스트에 얼마나 충실한가?
   - 환각(Hallucination) 탐지의 핵심 지표
   - 범위: 0.0 ~ 1.0 (높을수록 좋음)
   - 목표: > 0.9

2. Context Recall (컨텍스트 재현율) - Retrieval 평가
   - 검색된 컨텍스트가 정답(ground_truth)을 포함하는가?
   - 검색 품질의 핵심 지표
   - 범위: 0.0 ~ 1.0 (높을수록 좋음)
   - 목표: > 0.8

3. Context Precision (컨텍스트 정밀도) - Retrieval 평가
   - 검색된 컨텍스트가 얼마나 정확하고 불필요한 정보가 없는가?
   - 검색 정확도 지표
   - 범위: 0.0 ~ 1.0 (높을수록 좋음)
   - 목표: > 0.8

4. Answer Relevancy (답변 관련성) - Generation 평가
   - 생성된 답변이 질문과 얼마나 관련 있는가?
   - 답변 품질의 핵심 지표
   - 범위: 0.0 ~ 1.0 (높을수록 좋음)
   - 목표: > 0.9

📊 RAG 파이프라인 분석:
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  Question   │ ───→ │  Retrieval   │ ───→ │ Generation  │
└─────────────┘      └──────────────┘      └─────────────┘
                            ↓                      ↓
                     Context Recall         Faithfulness
                     Context Precision      Answer Relevancy

💡 최적화 전략:
- Context Recall 낮음 → Retrieval 개선 (임베딩, 청크 크기)
- Faithfulness 낮음 → Generation 개선 (프롬프트, 모델)
    """)


    # ========================================================================
    # Step 4: Knowledge Base 구성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📚 Step 4: Knowledge Base 구성")
    print("=" * 70)

    knowledge_base = [
        "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다.",
        "부산은 대한민국 제2의 도시로, 항구 도시로 유명합니다.",
        "한글은 1443년 조선 제4대 왕인 세종대왕이 창제한 문자입니다.",
        "훈민정음은 한글의 원래 이름으로, 백성을 가르치는 바른 소리라는 뜻입니다.",
        "목성은 태양계에서 가장 큰 행성으로, 지구 질량의 약 318배입니다.",
        "토성은 아름다운 고리로 유명한 행성입니다.",
        "광합성은 식물이 빛 에너지를 이용해 포도당과 산소를 만드는 과정입니다.",
        "식물의 엽록소는 빛 에너지를 흡수하여 화학 에너지로 변환합니다.",
        "DNA는 생명체의 유전 정보를 담고 있는 이중나선 구조의 분자입니다.",
        "RNA는 DNA의 정보를 단백질로 전달하는 역할을 합니다.",
    ]

    print(f"✓ Knowledge Base: {len(knowledge_base)}개 문서")


    # ========================================================================
    # Step 5: RAG 테스트 케이스 준비
    # ========================================================================
    print("\n" + "=" * 70)
    print("📝 Step 5: RAG 테스트 케이스")
    print("=" * 70)

    test_cases = [
        {
            "question": "대한민국의 수도는 어디인가요?",
            "ground_truth": "서울"
        },
        {
            "question": "한글을 창제한 사람은 누구인가요?",
            "ground_truth": "세종대왕"
        },
        {
            "question": "태양계에서 가장 큰 행성은 무엇인가요?",
            "ground_truth": "목성"
        },
        {
            "question": "광합성의 산물은 무엇인가요?",
            "ground_truth": "포도당과 산소"
        },
        {
            "question": "DNA의 구조는 어떻게 생겼나요?",
            "ground_truth": "이중나선 구조"
        },
    ]

    print(f"✓ {len(test_cases)}개 테스트 케이스 준비 완료")


    # ========================================================================
    # Step 6: RAG 파이프라인 실행 및 평가
    # ========================================================================
    print("\n" + "=" * 70)
    print("🚀 Step 6: RAG 파이프라인 실행")
    print("=" * 70)

    print("\n⚠️  주의: API 호출이 발생하여 시간이 걸립니다 (약 1-2분)")
    print("   비용: ~$0.10-0.20 (5 tasks × ~$0.02-0.04)")
    print("")

    from agent_evaluator import create_taskresult

    for idx, test in enumerate(test_cases, 1):
        print(f"\n{'='*70}")
        print(f"📝 Task {idx}/{len(test_cases)}: {test['question']}")
        print(f"{'='*70}")

        # Step 6.1: Retrieval (검색)
        print("\n🔍 Step 1: Retrieval...")
        retrieved_contexts = simulate_retrieval(test["question"], knowledge_base)

        print(f"  검색된 문서: {len(retrieved_contexts)}개")
        for i, ctx in enumerate(retrieved_contexts, 1):
            print(f"    [{i}] {ctx[:60]}...")

        # Step 6.2: Generation (생성)
        print("\n✍️  Step 2: Generation...")
        response = simulate_generation(test["question"], retrieved_contexts)
        print(f"  생성된 답변: {response[:100]}...")

        # Step 6.3: TaskResult 생성
        context_text = "\n\n".join(retrieved_contexts)

        task = create_taskresult(
            task_id=f"rag_{idx:03d}",
            task_type="qa",
            question=test["question"],
            response=response,
            ground_truth=test["ground_truth"],
            execution_time=1.5,
        )

        # Step 6.4: Layer 1 + Ragas 평가
        print("\n📊 Step 3: 평가...")
        print(f"  ✓ Layer 1: Accuracy={task.accuracy_score:.3f}")
        print(f"  ⏳ Ragas 평가 중... (API 호출)")

        monitor.record_task(
            task,
            input_text=test["question"],
            output_text=response,
            expected_output=test["ground_truth"],
            retrieved_context=retrieved_contexts
        )

        print(f"  ✅ 평가 완료")

    print(f"\n✅ {len(test_cases)}개 RAG Task 평가 완료!")


    # ========================================================================
    # Step 7: Ragas 결과 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 7: Ragas 결과 분석")
    print("=" * 70)

    rag_summary = monitor.get_rag_metrics_summary()

    if rag_summary:
        print("\n🔬 Ragas 4대 지표 결과:")
        print("-" * 70)

        # Faithfulness
        if rag_summary.get('faithfulness'):
            faithfulness = rag_summary['faithfulness'].get('avg', 0)
            print(f"\n1. Faithfulness (충실도): {faithfulness:.3f}")
            if faithfulness > 0.9:
                print("   ✅ 우수: 환각 없이 컨텍스트에 충실")
            elif faithfulness > 0.7:
                print("   ⚠️  주의: 일부 환각 가능성")
            else:
                print("   ❌ 개선 필요: 프롬프트 또는 모델 개선")

        # Context Recall
        if rag_summary.get('context_recall'):
            recall = rag_summary['context_recall'].get('avg', 0)
            print(f"\n2. Context Recall (재현율): {recall:.3f}")
            if recall > 0.8:
                print("   ✅ 우수: 검색이 정답을 잘 포함")
            elif recall > 0.6:
                print("   ⚠️  주의: 검색 품질 개선 필요")
            else:
                print("   ❌ 개선 필요: 임베딩 또는 청크 크기 조정")

        # Context Precision
        if rag_summary.get('context_precision'):
            precision = rag_summary['context_precision'].get('avg', 0)
            print(f"\n3. Context Precision (정밀도): {precision:.3f}")
            if precision > 0.8:
                print("   ✅ 우수: 불필요한 정보 최소화")
            elif precision > 0.6:
                print("   ⚠️  주의: 검색 정확도 개선 필요")
            else:
                print("   ❌ 개선 필요: 검색 알고리즘 개선")

        # Answer Relevancy
        if rag_summary.get('answer_relevancy'):
            relevancy = rag_summary['answer_relevancy'].get('avg', 0)
            print(f"\n4. Answer Relevancy (관련성): {relevancy:.3f}")
            if relevancy > 0.9:
                print("   ✅ 우수: 질문에 정확히 답변")
            elif relevancy > 0.7:
                print("   ⚠️  주의: 답변 품질 개선 필요")
            else:
                print("   ❌ 개선 필요: 프롬프트 개선")


    # ========================================================================
    # Step 8: Retrieval vs Generation 분리 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("🔬 Step 8: Retrieval vs Generation 분리 분석")
    print("=" * 70)

    if rag_summary:
        # Retrieval 품질
        retrieval_score = (
            rag_summary.get('context_recall', {}).get('avg', 0) * 0.6 +
            rag_summary.get('context_precision', {}).get('avg', 0) * 0.4
        )

        # Generation 품질
        generation_score = (
            rag_summary.get('faithfulness', {}).get('avg', 0) * 0.6 +
            rag_summary.get('answer_relevancy', {}).get('avg', 0) * 0.4
        )

        print(f"\n📊 종합 분석:")
        print(f"  - Retrieval 품질: {retrieval_score:.3f}")
        print(f"  - Generation 품질: {generation_score:.3f}")

        print(f"\n💡 최적화 우선순위:")
        if retrieval_score < generation_score:
            print("  → Retrieval 개선 우선")
            print("    • 임베딩 모델 업그레이드")
            print("    • 청크 크기 및 오버랩 조정")
            print("    • 하이브리드 검색 (키워드 + 벡터)")
        else:
            print("  → Generation 개선 우선")
            print("    • 프롬프트 엔지니어링")
            print("    • 모델 업그레이드 (gpt-4)")
            print("    • Few-shot 예제 추가")


    # ========================================================================
    # Step 9: 결과 저장
    # ========================================================================
    print("\n" + "=" * 70)
    print("💾 Step 9: 결과 저장")
    print("=" * 70)

    filename = f"{FILE_PREFIX}rag_system_result.json"
    monitor.save_to_file(filename)

    print(f"✓ 저장 완료: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")


    # ========================================================================
    # Step 10: RAG 최적화 전략
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎯 Step 10: RAG 최적화 전략")
    print("=" * 70)

    print("""
🔧 RAG 최적화 체크리스트:

【Retrieval 최적화】
□ 임베딩 모델 선택
  - OpenAI text-embedding-3-large
  - Cohere embed-v3
  - 도메인 특화 파인튜닝

□ 청크 전략
  - 청크 크기: 200-500 토큰
  - 오버랩: 10-20%
  - 의미 단위 분할 (문단, 문장)

□ 검색 전략
  - 하이브리드 검색 (키워드 + 벡터)
  - Re-ranking (Cohere, CrossEncoder)
  - Query expansion (동의어, 번역)

【Generation 최적화】
□ 프롬프트 엔지니어링
  - 명확한 지시사항
  - Few-shot 예제
  - 컨텍스트 활용 강조

□ 모델 선택
  - gpt-4o-mini: 비용 효율적
  - gpt-4o: 최고 품질
  - Claude Sonnet: 긴 컨텍스트

□ 후처리
  - 환각 탐지 및 필터링
  - 답변 검증
  - 소스 인용

【모니터링】
□ Ragas 지표 주기적 측정
□ A/B 테스트로 개선 효과 검증
□ 실패 케이스 분석 및 개선
    """)


    # ========================================================================
    # Dashboard 확인 안내
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 RAG System 평가 완료!")
    print("=" * 70)

    print("""
📊 Dashboard에서 확인하기:

1. Dashboard 실행:
   cd Dashboard
   streamlit run streamlit_dashboard.py

2. 파일 선택:
   → rag_system_result.json

3. 확인할 탭:
   📊 Overview: RAG 전체 성능
   🔬 Advanced: Ragas 4대 지표 상세
   💡 Insights: Retrieval/Generation 분리 분석

4. 분석 포인트:
   - Faithfulness vs Context Recall 비교
   - Retrieval 품질 vs Generation 품질
   - 개선 우선순위 파악
    """)

    print("\n✅ 다음 예제: level_3_production/01_framework_crewai.py")
    print("   → CrewAI 프레임워크 통합")


if __name__ == "__main__":
    main()
