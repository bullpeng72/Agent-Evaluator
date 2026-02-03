#!/usr/bin/env python3
"""
Level 2 Advanced - Example 01: Golden Dataset 자동 평가
=======================================================

🎯 목표: Golden Dataset 기반 완전 자동 평가 마스터

📚 학습 내용:
1. Golden Dataset JSON 구조 이해
2. evaluate_with_golden_dataset() 사용
3. Layer 1 + Layer 2 자동 평가
4. expected_tools를 통한 Tool Selection 평가
5. 대량 평가 자동화

🔍 Dashboard 확인:
- 📊 Overview: 자동 평가 결과
- 🎯 Core Metrics: 자동 계산된 지표
- 🤖 Agentic AI: Tool Selection 자동 평가
- 💡 Insights: 추천사항

⏱️ 예상 소요 시간: 15분
💰 비용: 무료 (Layer 1+2만 사용)

실행 방법:
    python level_2_advanced/01_golden_dataset.py
"""

import json
from pathlib import Path
from agent_evaluator import PerformanceMonitor

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L2-01]_"


def create_sample_golden_dataset(output_path: str):
    """샘플 Golden Dataset 생성"""

    golden_dataset = {
        "dataset_id": "sample_qa_dataset_001",
        "source_document": "Sample QA Collection",
        "created_at": "2024-12-10",
        "total_qa_pairs": 10,
        "metadata": {
            "dataset_name": "Sample QA Dataset",
            "version": "1.0",
            "description": "자동 평가를 위한 샘플 Golden Dataset"
        },
        "qa_pairs": [
            {
                "qa_id": "qa_001",
                "question": "대한민국의 수도는 어디인가요?",
                "answer": "대한민국의 수도는 서울입니다.",
                "context": "서울은 대한민국의 수도이며, 약 1천만 명의 인구가 살고 있습니다. 한강을 중심으로 발전한 대도시입니다.",
                "ground_truth": "서울",
                "expected_tools": ["search", "knowledge_base"],  # Layer 2: Tool Selection
                "task_type": "qa"
            },
            {
                "qa_id": "qa_002",
                "question": "한글을 창제한 사람은 누구인가요?",
                "answer": "한글은 조선시대 세종대왕께서 창제하셨습니다.",
                "context": "한글은 1443년 조선 제4대 왕인 세종대왕이 창제한 문자입니다.",
                "ground_truth": "세종대왕",
                "expected_tools": ["search", "knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_003",
                "question": "태양계에서 가장 큰 행성은?",
                "answer": "태양계에서 가장 큰 행성은 목성입니다.",
                "context": "목성은 태양계에서 가장 큰 행성으로, 지구 질량의 약 318배이며 가스 행성입니다.",
                "ground_truth": "목성",
                "expected_tools": ["search", "knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_004",
                "question": "물의 끓는점은 몇 도인가요?",
                "answer": "물은 1기압에서 섭씨 100도에서 끓습니다.",
                "context": "물은 1기압에서 섭씨 100도(화씨 212도)에서 끓는점을 가집니다.",
                "ground_truth": "섭씨 100도",
                "expected_tools": ["knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_005",
                "question": "광합성의 주요 산물은 무엇인가요?",
                "answer": "광합성의 주요 산물은 포도당과 산소입니다.",
                "context": "광합성은 빛 에너지를 이용해 이산화탄소와 물로부터 포도당과 산소를 만드는 과정입니다.",
                "ground_truth": "포도당과 산소",
                "expected_tools": ["knowledge_base", "search"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_006",
                "question": "피타고라스 정리는 무엇인가요?",
                "answer": "피타고라스 정리는 직각삼각형에서 빗변의 제곱이 두 직각변의 제곱의 합과 같다는 정리입니다.",
                "context": "피타고라스 정리(a² + b² = c²)는 직각삼각형의 세 변 사이의 관계를 나타냅니다.",
                "ground_truth": "a² + b² = c²",
                "expected_tools": ["calculator", "knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_007",
                "question": "DNA는 무엇의 약자인가요?",
                "answer": "DNA는 Deoxyribonucleic Acid의 약자입니다.",
                "context": "DNA(Deoxyribonucleic Acid)는 생명체의 유전 정보를 담고 있는 분자입니다.",
                "ground_truth": "Deoxyribonucleic Acid",
                "expected_tools": ["knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_008",
                "question": "지구의 자전 주기는?",
                "answer": "지구는 약 24시간(정확히는 23시간 56분)에 한 바퀴 자전합니다.",
                "context": "지구의 자전 주기는 23시간 56분 4초로, 이를 항성일이라고 합니다.",
                "ground_truth": "24시간",
                "expected_tools": ["knowledge_base", "search"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_009",
                "question": "빛의 속도는 얼마인가요?",
                "answer": "빛의 속도는 진공에서 약 초당 30만 킬로미터입니다.",
                "context": "빛의 속도는 진공에서 정확히 299,792,458 m/s입니다.",
                "ground_truth": "299,792,458 m/s",
                "expected_tools": ["knowledge_base"],
                "task_type": "qa"
            },
            {
                "qa_id": "qa_010",
                "question": "인터넷은 언제 발명되었나요?",
                "answer": "인터넷의 전신인 ARPANET은 1969년에 개발되었습니다.",
                "context": "ARPANET은 1969년 미국 국방부 고등연구계획국에서 개발한 네트워크로, 현대 인터넷의 시초입니다.",
                "ground_truth": "1969년",
                "expected_tools": ["search", "knowledge_base"],
                "task_type": "qa"
            }
        ]
    }

    # 파일 저장
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(golden_dataset, f, ensure_ascii=False, indent=2)

    return output_file


def my_agent(question: str):
    """
    평가할 Agent 함수 (시뮬레이션)

    실제 환경에서는 여기에 LLM 호출 코드를 넣습니다:
    - OpenAI API 호출
    - LangChain Agent 실행
    - CrewAI Task 실행
    """

    # 시뮬레이션: 질문에 따라 다른 응답
    responses = {
        "수도": {
            "answer": "대한민국의 수도는 서울입니다.",
            "latency": 1.2,
            "tool_calls": [
                {"name": "search", "success": True, "duration": 0.5},
                {"name": "knowledge_base", "success": True, "duration": 0.3}
            ]
        },
        "한글": {
            "answer": "한글은 조선시대 세종대왕께서 창제하셨습니다.",
            "latency": 0.9,
            "tool_calls": [
                {"name": "knowledge_base", "success": True, "duration": 0.4}
            ]
        },
        "행성": {
            "answer": "태양계에서 가장 큰 행성은 목성입니다.",
            "latency": 1.1,
            "tool_calls": [
                {"name": "search", "success": True, "duration": 0.6}
            ]
        },
        "끓는점": {
            "answer": "물은 1기압에서 섭씨 100도에서 끓습니다.",
            "latency": 0.8,
            "tool_calls": [
                {"name": "knowledge_base", "success": True, "duration": 0.3}
            ]
        },
        "광합성": {
            "answer": "광합성의 주요 산물은 포도당과 산소입니다.",
            "latency": 1.0,
            "tool_calls": [
                {"name": "knowledge_base", "success": True, "duration": 0.4},
                {"name": "search", "success": True, "duration": 0.2}
            ]
        },
    }

    # 키워드 매칭으로 응답 선택
    for keyword, response in responses.items():
        if keyword in question:
            return response

    # 기본 응답
    return {
        "answer": "잘 모르겠습니다.",
        "latency": 0.5,
        "tool_calls": [
            {"name": "search", "success": False, "duration": 0.2}
        ]
    }


def main():
    """Golden Dataset 자동 평가 실습"""

    print("=" * 70)
    print("🎯 Level 2 Advanced - Golden Dataset 자동 평가")
    print("=" * 70)


    # ========================================================================
    # Step 1: Golden Dataset 구조 이해
    # ========================================================================
    print("\n" + "=" * 70)
    print("📚 Step 1: Golden Dataset JSON 구조")
    print("=" * 70)

    print("""
Golden Dataset은 다음 구조를 가집니다:

{
  "dataset_name": "데이터셋 이름",
  "version": "1.0",
  "qa_pairs": [
    {
      "qa_id": "qa_001",                          # 고유 ID
      "question": "질문",                         # 평가할 질문
      "answer": "정답 예시",                      # 참고용 답변
      "context": "컨텍스트",                      # Hallucination 탐지용
      "ground_truth": "정답",                     # Accuracy 계산용
      "expected_tools": ["tool1", "tool2"],      # Layer 2: Tool Selection
      "task_type": "qa"                          # Task 유형
    }
  ]
}

📌 필수 필드:
- qa_id, question, ground_truth

📌 선택 필드:
- context: Hallucination 탐지 시 사용
- expected_tools: Tool Selection Accuracy 계산 시 사용 (Layer 2)
- answer: 참고용 (평가에 직접 사용 안 됨)
    """)


    # ========================================================================
    # Step 2: 샘플 Golden Dataset 생성
    # ========================================================================
    print("\n" + "=" * 70)
    print("📝 Step 2: 샘플 Golden Dataset 생성")
    print("=" * 70)

    dataset_path = "Dashboard/data/golden_datasets/sample_auto_eval_dataset.json"
    dataset_file = create_sample_golden_dataset(dataset_path)

    print(f"✓ Golden Dataset 생성 완료")
    print(f"  파일: {dataset_file}")
    print(f"  QA 쌍: 10개")
    print(f"  Layer 2 필드 포함: expected_tools")


    # ========================================================================
    # Step 3: Monitor 생성 및 임계값 설정
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Step 3: Monitor 생성 및 임계값 설정")
    print("=" * 70)

    monitor = PerformanceMonitor()

    # 임계값 설정
    monitor.thresholds = {
        # Layer 1
        'tcr': 90.0,
        'accuracy': 85.0,
        'hallucination': 5.0,

        # Layer 2
        'tool_selection_accuracy': 80.0,  # Tool Selection F1 Score
    }

    print("✓ 임계값 설정 완료:")
    print(f"  TCR ≥ {monitor.thresholds['tcr']}%")
    print(f"  Accuracy ≥ {monitor.thresholds['accuracy']}%")
    print(f"  Hallucination ≤ {monitor.thresholds['hallucination']}%")
    print(f"  Tool Selection ≥ {monitor.thresholds['tool_selection_accuracy']}%")


    # ========================================================================
    # Step 4: 자동 평가 실행
    # ========================================================================
    print("\n" + "=" * 70)
    print("🚀 Step 4: 자동 평가 실행")
    print("=" * 70)

    print("\n📝 evaluate_with_golden_dataset() 실행 중...")
    print("-" * 70)

    # 🎯 핵심: evaluate_with_golden_dataset()
    # - agent_fn: 평가할 함수
    # - dataset_path: Golden Dataset JSON 경로
    # - enable_layer2_metrics: Layer 2 평가 활성화
    # - verbose: 진행 상황 출력

    results = monitor.evaluate_with_golden_dataset(
        agent_fn=my_agent,
        dataset_path=str(dataset_file),
        enable_layer2_metrics=True,  # Layer 2: Tool Selection 평가
        verbose=True
    )


    # ========================================================================
    # Step 5: 결과 분석
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 5: 평가 결과 분석")
    print("=" * 70)

    print(f"\n✅ 자동 평가 완료!")
    print(f"  총 평가: {results['total_evaluated']}개")

    print(f"\n📊 Layer 1 Metrics (Native):")
    print(f"  - TCR: {results['layer1_metrics']['tcr']:.1f}%")
    print(f"  - Accuracy: {results['layer1_metrics']['accuracy']:.1f}%")
    print(f"  - Hallucination Rate: {results['layer1_metrics']['hallucination_rate']:.1f}%")

    if results.get('layer2_metrics'):
        print(f"\n🤖 Layer 2 Metrics (Agentic AI):")
        print(f"  - Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")
        print(f"  - Tool Selection F1: {results['layer2_metrics']['tool_selection_f1']:.3f}")

    # Pass/Fail 결과
    if results.get('pass_fail'):
        print(f"\n✓ Pass/Fail 판정:")
        pass_count = sum(1 for r in results['pass_fail'].values() if r['status'] == 'pass')
        total_count = len(results['pass_fail'])

        print(f"  - 합격: {pass_count}/{total_count}")

        for metric_key, result in results['pass_fail'].items():
            status_icon = "✅" if result['status'] == 'pass' else "❌"
            print(f"  {status_icon} {result['name']}: {result['value']:.1f} "
                  f"(기준: {result['threshold']:.1f})")


    # ========================================================================
    # Step 6: 상세 통계
    # ========================================================================
    print("\n" + "=" * 70)
    print("📈 Step 6: 상세 통계")
    print("=" * 70)

    # TCR 상세
    tcr_data = monitor.tcr_tracker.calculate_tcr()
    print(f"\n📊 TCR 상세:")
    print(f"  - 완전 성공: {tcr_data['full_success']}개")
    print(f"  - 부분 성공: {tcr_data['partial_success']}개")
    print(f"  - 실패: {tcr_data['failures']}개")

    # Accuracy 상세
    acc_data = monitor.accuracy_evaluator.get_accuracy_scores()
    if acc_data:
        print(f"\n✅ Accuracy 상세:")
        print(f"  - 평균 정확도: {acc_data.get('overall_accuracy', 0):.1f}%")
        print(f"  - 평가 개수: {len(monitor.accuracy_evaluator.evaluations)}개")

    # Latency 상세
    lat_data = monitor.latency_tracker.get_latency_stats()
    if lat_data:
        print(f"\n⏱️ Latency 상세:")
        print(f"  - 평균: {lat_data.get('avg', 0):.2f}초")
        print(f"  - P95: {lat_data.get('p95', 0):.2f}초")


    # ========================================================================
    # Step 7: 결과 저장
    # ========================================================================
    print("\n" + "=" * 70)
    print("💾 Step 7: 결과 저장")
    print("=" * 70)

    filename = f"{FILE_PREFIX}golden_dataset_auto_eval_result.json"
    monitor.save_to_file(filename)

    print(f"✓ 저장 완료: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")


    # ========================================================================
    # Step 8: 실전 활용 팁
    # ========================================================================
    print("\n" + "=" * 70)
    print("💡 Step 8: 실전 활용 팁")
    print("=" * 70)

    print("""
✅ Golden Dataset 자동 평가 Best Practice:

1. Dataset 준비:
   - 최소 50개 이상의 QA 쌍 권장
   - 다양한 난이도 포함
   - ground_truth는 정확하게 작성

2. Agent 함수 작성:
   def my_agent(question: str):
       # 실제 LLM 호출
       response = openai.ChatCompletion.create(...)
       return {
           "answer": response.text,
           "latency": execution_time,
           "tool_calls": [...],  # Layer 2 평가용
       }

3. 대량 평가:
   - 100+ QA 쌍으로 통계적 신뢰도 확보
   - 배치 평가로 시간 절약
   - 결과를 Dashboard에서 시각화

4. CI/CD 통합:
   - GitHub Actions에서 자동 평가
   - Threshold 기반 Pass/Fail
   - PR마다 평가 실행

5. 점진적 개선:
   - 실패 케이스 분석
   - Golden Dataset 확장
   - Threshold 조정
    """)


    # ========================================================================
    # Dashboard 확인 안내
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 Golden Dataset 자동 평가 완료!")
    print("=" * 70)

    print("""
📊 Dashboard에서 확인하기:

1. Dashboard 실행:
   cd Dashboard
   streamlit run streamlit_dashboard.py

2. 파일 선택:
   → golden_dataset_auto_eval_result.json

3. 확인할 탭:
   📊 Overview: 전체 통계 (10 Tasks)
   🎯 Core Metrics: Layer 1 상세
   🤖 Agentic AI: Tool Selection 결과
   💡 Insights: 개선 추천사항

4. 데이터편집 페이지:
   📝 Golden Dataset 편집
   📝 임계값 조정
   📝 버전 관리
    """)

    print("\n✅ 다음 예제: 02_layer3_hybrid.py")
    print("   → HybridMonitor로 DeepEval + Ragas 사용")


if __name__ == "__main__":
    main()
