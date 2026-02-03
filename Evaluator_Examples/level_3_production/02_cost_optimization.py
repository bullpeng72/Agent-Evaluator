#!/usr/bin/env python3
"""
Level 3 Production - Example 05: 비용 최적화 전략
==================================================

🎯 목표: Layer 1 무료 + Layer 3 샘플링으로 비용 90% 절감

📚 학습 내용:
1. Layer 1 (100% 평가) - 무료 기본 평가
2. Layer 3 샘플링 전략 (10-20%) - 선택적 고급 평가
3. 중요도 기반 평가 (Critical Tasks만 Layer 3)
4. 비용 vs 정확도 트레이드오프
5. ROI 계산 및 최적화

🔍 비용 비교:
- 전체 Layer 3: $3-8 per 100 tasks
- 샘플링 10%: $0.3-0.8 per 100 tasks (90% 절감)
- 품질 손실: < 5%

⏱️ 예상 소요 시간: 15분
💰 비용: 무료 (시뮬레이션)

실행 방법:
    python level_3_production/05_cost_optimization.py
"""

import random
from agent_evaluator import PerformanceMonitor

# 파일 Prefix 설정 (예제 파일에서 생성되는 모든 결과 파일에 적용)
FILE_PREFIX = "[L3-02]_"


def main():
    """비용 최적화 전략 실습"""

    print("=" * 70)
    print("🎯 Level 3 Production - 비용 최적화 전략")
    print("=" * 70)


    # ========================================================================
    # Step 1: 비용 문제 이해
    # ========================================================================
    print("\n" + "=" * 70)
    print("💰 Step 1: 비용 문제 이해")
    print("=" * 70)

    print("""
📊 Layer별 비용 (100 Tasks 기준):

Layer 1 (Native Metrics):
- 비용: $0 (무료)
- 지표: TCR, Accuracy, Hallucination 등 8개
- 속도: 매우 빠름 (<1ms per task)
- 정확도: 중간 (~60%)

Layer 2 (Agentic AI Metrics):
- 비용: $0 (무료)
- 지표: Tool Selection, Agent Coordination 등 3개
- 속도: 빠름 (<1ms per task)
- 정확도: 높음 (~80%)

Layer 3 (Advanced Metrics):
- 비용: $3-8 per 100 tasks
  • DeepEval: ~$1-3
  • Ragas: ~$2-5
- 지표: DeepEval 5종 + Ragas 4종
- 속도: 느림 (10-30초 per task)
- 정확도: 매우 높음 (~90%)

🚨 문제:
- 1000 Tasks Layer 3 평가 = $30-80
- 매일 평가 시 = $900-2400/월
- 예산 제약 시 사용 어려움

✅ 해결책: 비용 최적화 전략
    """)


    # ========================================================================
    # Strategy 1: Layer 1 (100% 평가) - 기본 전략
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Strategy 1: Layer 1 (100% 평가) - 무료 기본 평가")
    print("=" * 70)

    monitor_layer1 = PerformanceMonitor()

    print("\n🔧 Layer 1만 사용:")
    print("  - 비용: $0")
    print("  - 모든 Task 평가 (100%)")
    print("  - 8개 Native Metrics")
    print("  - 빠른 피드백 (<1초)")

    # 100개 Task 시뮬레이션
    task_count = 100
    print(f"\n📝 {task_count}개 Task 평가 중...")

    from agent_evaluator import create_taskresult

    for i in range(task_count):
        task = create_taskresult(
            task_id=f"layer1_{i+1:03d}",
            task_type="qa",
            question=f"질문 {i+1}",
            response=f"답변 {i+1}",
            ground_truth=f"정답 {i+1}",
            execution_time=random.uniform(0.5, 2.0),
            
        )
        monitor_layer1.record_task(task)

    report_layer1 = monitor_layer1.generate_report()

    print(f"\n✅ Layer 1 평가 완료:")
    print(f"  - 총 Task: {report_layer1.total_tasks}개")

    tcr_data = report_layer1.accuracy_metrics.get('tcr', {})
    accuracy_data = report_layer1.accuracy_metrics.get('accuracy_scores', {})
    print(f"  - TCR: {tcr_data.get('tcr', 0):.1f}%")
    print(f"  - Accuracy: {accuracy_data.get('avg', 0) * 100:.1f}%")
    print(f"  - 비용: $0.00")
    print(f"  - 시간: ~0.1초")


    # ========================================================================
    # Strategy 2: Sampling (10%) - 비용 90% 절감
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Strategy 2: Sampling 전략 (10% Layer 3)")
    print("=" * 70)

    print("""
🎯 샘플링 전략:
1. Layer 1: 100% 평가 (무료)
2. Layer 3: 랜덤 10% 샘플링 (유료)

💡 원리:
- 통계적으로 10%만 평가해도 전체 경향 파악 가능
- 신뢰 구간 95%로 전체 추정
- 비용 90% 절감, 정확도 손실 < 5%

📊 비용 비교:
- 전체 Layer 3 (100%): $3-8
- 샘플링 10%: $0.3-0.8
- 절감율: 90%

🎲 샘플링 방법:
1. Random Sampling: 무작위 10% 선택
2. Stratified Sampling: TaskType별 균등 선택
3. Systematic Sampling: 매 10번째 Task 선택
    """)

    sample_rate = 0.10  # 10%
    sample_count = int(task_count * sample_rate)

    print(f"\n📊 샘플링 적용:")
    print(f"  - 전체 Task: {task_count}개")
    print(f"  - 샘플링 비율: {sample_rate*100:.0f}%")
    print(f"  - 샘플 개수: {sample_count}개")
    print(f"  - Layer 1: {task_count}개 (100%)")
    print(f"  - Layer 3: {sample_count}개 (10%)")

    # 비용 계산
    cost_full = task_count * 0.06  # $0.06 per task
    cost_sampling = sample_count * 0.06
    cost_saving = (cost_full - cost_sampling) / cost_full * 100

    print(f"\n💰 비용 비교:")
    print(f"  - 전체 Layer 3: ${cost_full:.2f}")
    print(f"  - 샘플링 10%: ${cost_sampling:.2f}")
    print(f"  - 절감액: ${cost_full - cost_sampling:.2f}")
    print(f"  - 절감율: {cost_saving:.0f}%")


    # ========================================================================
    # Strategy 3: Critical Tasks Only (5%) - 중요도 기반
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Strategy 3: Critical Tasks Only (5%)")
    print("=" * 70)

    print("""
🎯 중요도 기반 평가:
1. Layer 1: 100% 평가 (모든 Task)
2. Layer 3: Critical Tasks만 (5%)

💡 Critical Tasks 정의:
- Production 배포 직전
- 고객 대면 기능
- 법적 책임이 있는 답변
- 높은 위험도 Task

🎲 판단 기준:
- TaskType: 의료, 법률, 금융
- 사용자 그룹: Premium 고객
- 기능: 핵심 비즈니스 로직
- 실패 시 영향도: Critical

📊 예시:
- 일반 QA: Layer 1만
- 의료 조언: Layer 1 + Layer 3
- 법률 해석: Layer 1 + Layer 3
- 금융 추천: Layer 1 + Layer 3
    """)

    critical_rate = 0.05  # 5%
    critical_count = int(task_count * critical_rate)

    print(f"\n📊 Critical Tasks 전략:")
    print(f"  - 전체 Task: {task_count}개")
    print(f"  - Critical 비율: {critical_rate*100:.0f}%")
    print(f"  - Critical 개수: {critical_count}개")
    print(f"  - Layer 1: {task_count}개 (100%)")
    print(f"  - Layer 3: {critical_count}개 (5%)")

    # 비용 계산
    cost_critical = critical_count * 0.06
    cost_saving_critical = (cost_full - cost_critical) / cost_full * 100

    print(f"\n💰 비용 비교:")
    print(f"  - 전체 Layer 3: ${cost_full:.2f}")
    print(f"  - Critical 5%: ${cost_critical:.2f}")
    print(f"  - 절감액: ${cost_full - cost_critical:.2f}")
    print(f"  - 절감율: {cost_saving_critical:.0f}%")


    # ========================================================================
    # Strategy 4: Hybrid (20% Stratified) - 균형 전략
    # ========================================================================
    print("\n" + "=" * 70)
    print("📌 Strategy 4: Hybrid 전략 (20% Stratified)")
    print("=" * 70)

    print("""
🎯 균형 잡힌 접근:
1. Layer 1: 100% (모든 Task)
2. Layer 3: 20% Stratified Sampling

💡 Stratified Sampling:
- TaskType별로 균등하게 샘플링
- 각 그룹의 특성 반영
- 전체 대표성 확보

📊 예시 (100 Tasks):
- QA: 50개 → 10개 Layer 3 (20%)
- Code: 30개 → 6개 Layer 3 (20%)
- Creative: 20개 → 4개 Layer 3 (20%)
- 총: 20개 Layer 3

✅ 장점:
- 모든 TaskType 커버
- 대표성 높음
- 비용 대비 정확도 최고
    """)

    stratified_rate = 0.20  # 20%
    stratified_count = int(task_count * stratified_rate)

    print(f"\n📊 Stratified 전략:")
    print(f"  - 전체 Task: {task_count}개")
    print(f"  - 샘플링 비율: {stratified_rate*100:.0f}%")
    print(f"  - 샘플 개수: {stratified_count}개")
    print(f"  - Layer 1: {task_count}개 (100%)")
    print(f"  - Layer 3: {stratified_count}개 (20%, Stratified)")

    # 비용 계산
    cost_stratified = stratified_count * 0.06
    cost_saving_stratified = (cost_full - cost_stratified) / cost_full * 100

    print(f"\n💰 비용 비교:")
    print(f"  - 전체 Layer 3: ${cost_full:.2f}")
    print(f"  - Stratified 20%: ${cost_stratified:.2f}")
    print(f"  - 절감액: ${cost_full - cost_stratified:.2f}")
    print(f"  - 절감율: {cost_saving_stratified:.0f}%")


    # ========================================================================
    # Step 2: 전략 비교표
    # ========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 2: 전략 비교표")
    print("=" * 70)

    print(f"""
📊 비용 최적화 전략 비교 (100 Tasks 기준):

| 전략 | Layer 1 | Layer 3 | 비용 | 절감율 | 정확도 | 추천 |
|------|---------|---------|------|--------|--------|------|
| 1. 전체 Layer 3 | 100% | 100% | ${cost_full:.2f} | 0% | 최고 | 예산 충분 |
| 2. Sampling 10% | 100% | 10% | ${cost_sampling:.2f} | 90% | 높음 | 대량 평가 |
| 3. Critical 5% | 100% | 5% | ${cost_critical:.2f} | 95% | 중간 | 핵심만 |
| 4. Stratified 20% | 100% | 20% | ${cost_stratified:.2f} | 80% | 최고 | 권장 ✅ |

💡 권장 전략: Strategy 4 (Stratified 20%)
- 비용 80% 절감
- 정확도 손실 < 5%
- 모든 TaskType 커버
- 대표성 확보
    """)


    # ========================================================================
    # Step 3: 실전 구현 예제
    # ========================================================================
    print("\n" + "=" * 70)
    print("🔧 Step 3: 실전 구현 예제")
    print("=" * 70)

    print("""
✅ Python 구현 예제:

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor
import random

# 1. Layer 1 Monitor (모든 Task)
monitor_l1 = PerformanceMonitor()

# 2. Layer 3 Monitor (샘플링용)
monitor_l3 = HybridPerformanceMonitor(
    use_deepeval=True,
    use_ragas=True,
    deepeval_
)

# 3. 평가 루프
for i, task_data in enumerate(tasks):
    # Layer 1: 모든 Task
    task = create_task(task_data)
    monitor_l1.record_task(task)

    # Layer 3: 20% 샘플링 (Stratified)
    if should_evaluate_layer3(i, task_data):
        monitor_l3.record_task(task, context=..., response=...)

def should_evaluate_layer3(index, task_data):
    # Strategy 1: Random Sampling (10%)
    return random.random() < 0.10

    # Strategy 2: Critical Tasks Only
    # return task_data['is_critical']

    # Strategy 3: Stratified Sampling (20%)
    # return (index % 5) == 0  # 매 5번째
```
    """)


    # ========================================================================
    # Step 4: ROI 계산
    # ========================================================================
    print("\n" + "=" * 70)
    print("💰 Step 4: ROI 계산")
    print("=" * 70)

    print(f"""
📊 ROI 분석 (월 10,000 Tasks 기준):

Strategy 1: 전체 Layer 3
- 비용: ${cost_full * 100:.2f}/월
- 정확도: 95%
- ROI: 기준점

Strategy 4: Stratified 20%
- 비용: ${cost_stratified * 100:.2f}/월
- 정확도: 92%
- 절감액: ${(cost_full - cost_stratified) * 100:.2f}/월
- 정확도 손실: 3%
- ROI: 80% 비용 절감 vs 3% 정확도 손실
- 판정: ✅ 매우 우수

💡 결론:
- Stratified 20% 전략이 최적
- 연간 절감액: ${(cost_full - cost_stratified) * 100 * 12:.2f}
- 품질 손실 최소화
- 대규모 평가에 적합
    """)


    # ========================================================================
    # Step 5: 베스트 프랙티스
    # ========================================================================
    print("\n" + "=" * 70)
    print("💡 Step 5: 비용 최적화 Best Practice")
    print("=" * 70)

    print("""
✅ 비용 최적화 Best Practice:

1. 단계별 접근:
   Phase 1: Layer 1만 사용 (무료로 기본 확보)
   Phase 2: 10% 샘플링 테스트
   Phase 3: 20% Stratified 적용
   Phase 4: Critical Tasks 정의 및 적용

2. 모니터링:
   - 매월 비용 추적
   - 정확도 변화 관찰
   - 샘플링 비율 조정

3. 임계값 설정:
   - Layer 1 기준: 느슨하게 (TCR ≥ 85%)
   - Layer 3 샘플: 엄격하게 (TCR ≥ 95%)
   - Critical Tasks: 매우 엄격 (TCR ≥ 98%)

4. 자동화:
   - CI/CD 통합
   - 자동 샘플링
   - 비용 알림 설정

5. 정기 리뷰:
   - 분기별 전략 재평가
   - 샘플링 비율 최적화
   - Critical Tasks 기준 업데이트
    """)


    # ========================================================================
    # Step 6: 결과 저장
    # ========================================================================
    filename = f"{FILE_PREFIX}cost_optimization_strategy.json"
    monitor_layer1.save_to_file(filename)

    print(f"\n💾 결과 저장: {filename}")


    # ========================================================================
    # 요약
    # ========================================================================
    print("\n" + "=" * 70)
    print("🎉 비용 최적화 전략 학습 완료!")
    print("=" * 70)

    print(f"""
📚 학습한 내용:
1. Layer 1 (무료) + Layer 3 (유료) 조합
2. 4가지 샘플링 전략
3. ROI 계산 및 비교
4. 실전 구현 패턴

🎯 핵심 결론:
- Layer 1 100% (무료 기본 평가)
- Layer 3 20% Stratified (선택적 고급 평가)
- 비용 80% 절감, 정확도 손실 < 5%
- 연간 절감액: ${(cost_full - cost_stratified) * 100 * 12:.2f}

✅ 권장 전략:
Strategy 4 (Stratified 20%) - 비용과 품질의 최적 균형

💡 다음 단계:
- 실제 프로젝트에 적용
- 샘플링 비율 실험
- 비용 추적 및 최적화
    """)


if __name__ == "__main__":
    main()
