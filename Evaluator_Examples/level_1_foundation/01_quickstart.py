#!/usr/bin/env python3
"""
Level 1 Foundation - Example 01: Quick Start
==============================================

🎯 목표: 5분 안에 첫 평가 완료

📚 학습 내용:
1. PerformanceMonitor 생성
2. TaskResult 생성 (create_taskresult 사용)
3. record_task()로 기록
4. generate_report()로 리포트 생성
5. save_to_file()로 저장

🔍 Dashboard 확인:
- 📊 Overview 탭: 기본 통계
- 🎯 Core Metrics 탭: TCR, Accuracy

⏱️ 예상 소요 시간: 5분
💰 비용: 무료 (Layer 1만 사용)

실행 방법:
    python level_1_foundation/01_quickstart.py
"""

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir, get_dashboard_dir

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L1-01]_"


def main():
    """5분 Quick Start - 기본 워크플로우 학습"""

    print("=" * 70)
    print("🚀 Level 1 Foundation - Quick Start")
    print("=" * 70)

    # ========================================================================
    # Step 1: PerformanceMonitor 생성 (path_helpers 활용)
    # ========================================================================
    print("\n✅ Step 1: PerformanceMonitor 생성")
    print("-" * 70)

    # 🎯 개선: path_helpers 사용으로 자동 경로 감지
    # - get_evaluation_results_dir(): 자동으로 Dashboard/data/evaluation_results 찾기
    # - 프로젝트 루트를 자동 감지하므로 어디서 실행해도 동작
    results_dir = get_evaluation_results_dir()
    monitor = PerformanceMonitor(
        output_dir=str(results_dir),
        enable_hallucination_detection=True
    )

    print("✓ Monitor 생성 완료!")
    print(f"  - 데이터 저장 위치: {monitor.output_dir}")
    print(f"  - path_helpers로 자동 감지: ✅")
    print(f"  - Hallucination 탐지: {'활성화' if monitor.enable_hallucination_detection else '비활성화'}")


    # ========================================================================
    # Step 2: 간단한 AI Agent 시뮬레이션
    # ========================================================================
    print("\n✅ Step 2: AI Agent 실행 (시뮬레이션)")
    print("-" * 70)

    # 실제 환경에서는 여기에 LLM 호출 코드가 들어갑니다
    # 예: response = openai.ChatCompletion.create(...)

    questions_and_answers = [
        {
            "question": "대한민국의 수도는 어디인가요?",
            "response": "대한민국의 수도는 서울입니다.",
            "ground_truth": "서울",
            "execution_time": 1.2,
            "context": "대한민국의 수도는 서울이며, 한강이 도시를 가로지릅니다."
        },
        {
            "question": "한글을 창제한 사람은 누구인가요?",
            "response": "한글은 조선시대 세종대왕께서 창제하셨습니다.",
            "ground_truth": "세종대왕",
            "execution_time": 0.9,
            "context": "한글은 1443년 조선 제4대 왕인 세종대왕이 창제한 문자입니다."
        },
        {
            "question": "태양계에서 가장 큰 행성은?",
            "response": "태양계에서 가장 큰 행성은 목성입니다.",
            "ground_truth": "목성",
            "execution_time": 1.0,
            "context": "목성은 태양계에서 가장 큰 행성으로, 지구 질량의 약 318배입니다."
        },
    ]

    print(f"📝 {len(questions_and_answers)}개 질문 평가 중...")


    # ========================================================================
    # Step 3: TaskResult 생성 및 기록 (동적 계산)
    # ========================================================================
    print("\n✅ Step 3: TaskResult 생성 및 기록")
    print("-" * 70)

    for idx, qa in enumerate(questions_and_answers, 1):
        # 🎯 핵심: create_taskresult()로 동적 계산
        # - completion_score: 자동 계산 (길이, 에러 여부 기반)
        # - accuracy_score: 자동 계산 (4가지 유사도 메트릭 조합)
        # - tokens: 자동 추정 (텍스트 길이 기반)

        task = create_taskresult(
            task_id=f"qa_{idx:03d}",
            task_type="qa",
            question=qa["question"],
            response=qa["response"],
            ground_truth=qa["ground_truth"],
            execution_time=qa["execution_time"]
        )

        # 기록
        monitor.record_task(task)

        print(f"  {idx}. Task {task.task_id}: "
              f"Accuracy={task.accuracy_score:.2f}, "
              f"Latency={task.execution_time:.1f}s")

    print(f"\n✓ {len(questions_and_answers)}개 Task 기록 완료!")


    # ========================================================================
    # Step 4: 리포트 생성
    # ========================================================================
    print("\n✅ Step 4: 평가 리포트 생성")
    print("-" * 70)

    report = monitor.generate_report()

    print(f"\n📊 평가 결과 요약:")
    print(f"  - 총 평가: {report.total_tasks}개")

    # accuracy_metrics 내부 dict에서 값 추출
    tcr_data = report.accuracy_metrics.get('tcr', {})
    accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
    hallucination_data = report.accuracy_metrics.get('hallucination', {})

    print(f"  - TCR (작업 완료율): {tcr_data.get('tcr', 0):.1f}%")
    print(f"  - Accuracy (정확도): {accuracy_data.get('avg', 0) * 100:.1f}%")
    print(f"  - Hallucination Rate: {hallucination_data.get('rate', 0):.1f}%")

    # efficiency_metrics에서 값 추출
    latency_data = report.efficiency_metrics.get('latency', {})
    print(f"  - 평균 Latency: {latency_data.get('avg', 0):.2f}초")


    # ========================================================================
    # Step 5: 파일로 저장 (Dashboard에서 확인용)
    # ========================================================================
    print("\n✅ Step 5: 결과 저장")
    print("-" * 70)

    filename = f"{FILE_PREFIX}quickstart_example_result.json"
    monitor.save_to_file(filename)

    print(f"✓ 저장 완료: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")


    # ========================================================================
    # Step 6: Dashboard 확인 안내
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 Quick Start 완료!")
    print("=" * 70)

    print("\n📊 Dashboard에서 결과 확인하기:")
    print("-" * 70)
    print("1. Dashboard 실행:")
    print("   cd Dashboard")
    print("   streamlit run streamlit_dashboard.py")
    print("")
    print("2. Dashboard에서 확인할 탭:")
    print("   📊 Overview: 전체 요약 통계")
    print("   🎯 Core Metrics: TCR, Accuracy, Hallucination 상세")
    print("   ⚡ Performance: Latency, Cost 분석")
    print("")
    print("3. 파일 선택:")
    print(f"   {filename} 선택")
    print("")

    print("✅ 다음 예제: 02_layer1_trackers.py")
    print("   → 11개 Tracker의 역할과 사용법 마스터")


if __name__ == "__main__":
    main()
