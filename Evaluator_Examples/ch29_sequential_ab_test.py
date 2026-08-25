"""
ch29_sequential_ab_test.py — Always-Valid A/B 테스트 (mSPRT)
=================================================================
Book Chapter 29 — 반복 확인에도 안전한 A/B 테스트

ch17(주간 리뷰)의 섹션 2는 매주 ``ab_test()``(Welch's t-test)를 새로 호출해
전주 대비 유의성을 확인한다 — 이게 바로 "peeking(반복 확인)" 상황이다. 고정
표본 크기를 가정하는 일반 t-검정은 데이터가 쌓이는 도중 몇 번이고 유의성을
확인하면 실제 위양성률이 명목 5%보다 훨씬 커진다(최적 정지 편향). 이 챕터는
Johari et al.(2015) *"Always Valid Inference"* 의 mSPRT를 구현한
``QuickEval.ab_test_sequential()``로 이 문제를 피하는 법을 보여준다.

  섹션 1: 문제 재현 — 반복 확인이 왜 위험한가
  섹션 2: ab_test_sequential() 기본 사용법
  섹션 3: tau(혼합 사전분포 스케일) 고르는 법 — 암묵적 기본값 없음
  섹션 4: 실제로 몇 번을 확인해도 안전한지 직접 검증

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch29_sequential_ab_test.py

결과:
    results/ch29_variant_a.json, ch29_variant_b.json
"""

import random
from pathlib import Path

from agent_evaluator import QuickEval, create_taskresult

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = str(_PROJECT_ROOT / "results")

# ===========================================================================
# 섹션 1: 문제 재현 — 반복 확인이 왜 위험한가
# ===========================================================================
print("=== 섹션 1: 반복 확인(peeking)이 왜 위험한가 ===")
print("""
  두 그룹이 실제로는 동일한 분포(효과 없음)여도, 데이터가 쌓이는 도중
  ab_test()를 10번·20번 반복 호출해 매번 "p < 0.05인가?"를 확인하면,
  그중 단 한 번이라도 우연히 유의하게 나올 확률이 명목 alpha(5%)보다
  훨씬 높아진다 — "언젠가 유리해 보이는 순간에 멈추는" 최적 정지 편향 때문이다.

  실제로 이 SDK를 개발하며 몬테카를로로 검증한 결과:
    - 순진한 반복 t-검정 500회 반복 × 20회 peeking → 경험적 위양성률 22.0%
    - mSPRT(이 챕터의 주제) 동일 조건                → 경험적 위양성률  0.0%
  (검증 코드: tests/test_phase7_msprt_sequential_ab_test.py)
""")

# ===========================================================================
# 섹션 2: ab_test_sequential() 기본 사용법
# ===========================================================================
print("=== 섹션 2: ab_test_sequential() 기본 사용법 ===")

random.seed(42)


def _make_variant(name: str, base_accuracy: float, n: int) -> QuickEval:
    qe = QuickEval(_OUTPUT_DIR)
    for i in range(n):
        score = max(0.0, min(1.0, base_accuracy + random.uniform(-0.08, 0.08)))
        qe._monitor.record_task(create_taskresult(
            task_id=f"{name}_{i:03d}",
            question=f"질문 {i}", response="응답", ground_truth="응답",
            accuracy_score=score, execution_time=1.0, task_type="qa",
        ))
    qe.save()
    return qe


variant_a = _make_variant("ch29_variant_a", base_accuracy=0.70, n=60)   # 기존 프롬프트
variant_b = _make_variant("ch29_variant_b", base_accuracy=0.78, n=60)   # 새 프롬프트

# tau: "감지하고 싶은 효과 크기의 스케일" — 여기서는 8pp(0.08) 정도의 차이를
# 감지하고 싶다고 가정. direction(Guardrail Metric)과 같은 이유로 암묵적
# 기본값이 없다 — 반드시 명시해야 한다.
result = variant_b.ab_test_sequential(variant_a, metric="accuracy_score", tau=0.08)

print(f"  Variant A(기존) 평균: {result['other_mean']:.4f}")
print(f"  Variant B(신규) 평균: {result['self_mean']:.4f}")
print(f"  차이(delta):          {result['delta']:+.4f}")
print(f"  always-valid p-value: {result['always_valid_p_value']}")
print(f"  유의미 여부:          {'있음 — 지금 결론 내려도 안전' if result['significant'] else '없음(계속 관찰)'}")

# ===========================================================================
# 섹션 3: tau 고르는 법
# ===========================================================================
print("\n=== 섹션 3: tau(혼합 사전분포 스케일) 고르는 법 ===")
print("""
  tau는 "이 정도 효과가 있을 거라 기대한다"는 사전 지식을 나타낸다.

    - 통계적 유효성(위양성률 통제)은 tau 값과 **무관하게 항상 성립**한다.
    - tau가 실제 효과 크기와 동떨어지면 **검정력만** 떨어진다 — 판정이
      늦어질 뿐, 틀린 결론을 내리지는 않는다.
    - 시작점: 감지하고 싶은 최소 효과 크기(예: "5pp 이상 차이면 의미있다")를
      그대로 tau로 쓴다. 원본 지표의 표준편차 0.1~1배 사이가 흔한 범위다.

  섹션 2의 데이터(60건, 8pp 차이)는 신호가 너무 강해서 tau를 뭘 줘도 p가
  거의 0으로 뭉개진다 — tau의 효과가 잘 안 보인다. 대신 폐형해 공식을 직접
  호출하는 작은 워크드 예제(theta_hat=1.0, variance=0.05 고정)로 tau만 바꿔가며
  곡선을 보여준다. tau가 관측된 효과와 비슷할수록(여기서는 tau≈1.0 부근)
  증거가 강해진다 — 단조 증가/감소가 아니라 "맞는 지점에서 최댓값을 갖는
  곡선"이라는 게 핵심이다. tau가 너무 작으면(사전분포가 0 근처에 지나치게
  집중) 너무 크면(사전분포가 지나치게 퍼짐) 둘 다 증거가 약해진다.
""")
from agent_evaluator.quick_eval import _always_valid_p_value  # 내부 헬퍼 — 곡선 시연용

theta_hat, variance = 1.0, 0.05
for tau in (0.01, 0.2, 1.0, 5.0, 100.0):
    p = _always_valid_p_value(theta_hat, variance, tau)
    print(f"    tau={tau:<6} → p={p:.6f}")

# ===========================================================================
# 섹션 4: 실제로 몇 번을 확인해도 안전한지 직접 검증
# ===========================================================================
print("\n=== 섹션 4: 데이터가 쌓이는 도중 반복 확인해도 안전한가 ===")
print("""
  아래는 태스크가 10건씩 쌓일 때마다 결과를 다시 확인하는 상황을 재현한다 —
  ab_test()였다면 여러 번 확인할수록 위양성 위험이 커지지만, ab_test_sequential()
  은 몇 번을 확인하든 그 시점의 always-valid p-value가 alpha 이하이면 그대로
  신뢰할 수 있다(Ville's maximal inequality).
""")

qe_stream_a = QuickEval(_OUTPUT_DIR)
qe_stream_b = QuickEval(_OUTPUT_DIR)
for i in range(60):
    score_a = max(0.0, min(1.0, 0.70 + random.uniform(-0.08, 0.08)))
    score_b = max(0.0, min(1.0, 0.78 + random.uniform(-0.08, 0.08)))
    qe_stream_a._monitor.record_task(create_taskresult(
        task_id=f"stream_a_{i:03d}", question="q", response="r",
        accuracy_score=score_a, execution_time=1.0, task_type="qa",
    ))
    qe_stream_b._monitor.record_task(create_taskresult(
        task_id=f"stream_b_{i:03d}", question="q", response="r",
        accuracy_score=score_b, execution_time=1.0, task_type="qa",
    ))
    if (i + 1) % 10 == 0:
        r = qe_stream_b.ab_test_sequential(qe_stream_a, metric="accuracy_score", tau=0.08)
        p = r["always_valid_p_value"]
        p_str = f"{p:.4f}" if p is not None else "n/a"
        flag = "  ← 이 시점부터 신뢰 가능" if r["significant"] else ""
        print(f"    n={i + 1:>3}  p={p_str}{flag}")

print("\n결과 저장 완료: results/ch29_variant_a.json, ch29_variant_b.json")
print("확인: agent-eval dashboard results/")
