"""
ch01_first_eval.py — AI 에이전트 평가, 왜 다른가
=======================================================================
Book Chapter 01 — AI에이전트 평가란 무엇인가

챕터 순서대로 4가지 논점을 직접 실행합니다.

  섹션 1 — assert 기반 테스트의 함정      (§1.4 한계①)
           "의미가 같아도 assert는 실패한다"
           → create_taskresult 로 정확도 점수와 직접 비교

  섹션 2 — RAG 환각 탐지                 (§1.2 사례①)
           "컨텍스트를 벗어난 응답을 자동으로 식별한다"
           → @agent_eval + HallucinationDetector

  섹션 3 — SLA 위반 감지                 (§1.2 사례③)
           "레이턴시 급증을 배포 기준으로 자동 차단한다"
           → @agent_eval + SLAConfig

  섹션 4 — Harness 3요소 종합            (§1.3)
           "Tracker × Config → Gate 배포 판정"
           → InstructionConfig + SLAConfig → 통과/차단 판정

의존성: pip install agent-evaluator
실행:   python Evaluator_Examples/ch01_first_eval.py
결과:   results/ch01_*.json  →  agent-eval dashboard --results results/
"""

import random
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    setup_otel,
    InstructionConfig,
    SLAConfig,
)
from agent_evaluator.decorators import agent_eval

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# Phoenix OTEL 자동 감지 (agent-eval monitor 실행 중이면 연결)
try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch01-why-eval")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass


# ===========================================================================
# 섹션 1 — §1.4 한계①: assert 기반 테스트의 함정
#
# "의미는 같아도 표현이 다르면 assert 실패"
# §1.4 코드 예시:
#   assert result == "서울입니다."
#   → "서울이 한국의 수도입니다", "수도는 서울입니다" 모두 정답인데 하나만 통과
#
# 해결: AccuracyEvaluator의 Token F1·Jaccard·LCS·Char 4중 가중 알고리즘
#       단순 assert 대신 통계적 정확도 분포로 판단
# ===========================================================================
print("\n" + "=" * 62)
print("섹션 1 — assert 기반 테스트의 함정  (§1.4 한계①)")
print("=" * 62)
print("  assert 기반 테스트는 표현이 달라지면 의미가 같아도 실패합니다.")
print("  AccuracyEvaluator는 TokenF1·Jaccard·LCS·Char 4중 알고리즘으로")
print("  의미 거리에 비례한 연속 점수를 계산합니다.\n")
print("  질문: '한국의 수도는?'  정답 기준: '서울'\n")

monitor_s1 = PerformanceMonitor(output_dir=_OUTPUT_DIR)

# §1.4 코드 예시 재현: 의미는 같지만 표현이 다른 응답들
# - assert: 정답 문자열과 정확히 일치해야 통과 → 표현 변형 시 전부 실패
# - AccuracyEvaluator: 토큰 겹침 기반 유사도 → 의미가 가까울수록 높은 점수
GT_CAPITAL = "서울은 대한민국의 수도이자 최대 도시입니다."

CAPITAL_RESPONSES = [
    ("정확 일치",   GT_CAPITAL),
    ("어순 변형",   "대한민국의 수도이자 최대 도시는 서울입니다."),
    ("간결 표현",   "서울이 수도입니다."),
    ("영한 혼용",   "Seoul(서울)이 한국의 수도입니다."),
    ("완전히 오답", "오늘 날씨는 맑고 기온은 25도입니다."),
]

print(f"  {'표현 유형':<12}  {'응답(앞 25자)':<28}  {'assert':^7}  {'정확도':^8}")
print("  " + "-" * 62)

for label, resp in CAPITAL_RESPONSES:
    result = create_taskresult(
        task_id=f"s1_{label[:2]}",
        question="한국의 수도는?",
        response=resp,
        ground_truth=GT_CAPITAL,
        execution_time=0.05,
        task_type="qa",
    )
    monitor_s1.record_task(result)
    naive = "✅" if resp == GT_CAPITAL else "❌"
    preview = resp[:25] + ("…" if len(resp) > 25 else "")
    print(f"  {label:<12}  {preview:<28}  {naive:^7}  {result.accuracy_score:^8.2f}")

print()
print("  결론: assert 기반 → 5건 중 1건만 통과 (정확히 일치할 때만)")
print("        정확도 점수 → 의미 거리에 비례한 연속 값 (0.0 ~ 1.0)")
print("        → '완전히 오답'은 낮고, '어순 변형'은 높게 측정됨")


# ===========================================================================
# 섹션 2 — §1.2 사례①: RAG 환각 탐지
#
# 의료 정보 RAG 에이전트가 컨텍스트를 벗어난 정보를 생성하는 시나리오.
# enable_hallucination_detection=True → HallucinationDetector 자동 동작.
#
# §1.2: "검색된 문서에는 올바른 정보가 있었지만, 에이전트는 문서의 내용을
#        벗어난 정보를 생성했습니다."
#       필요했던 평가: HallucinationDetector — Group C 신뢰성
# ===========================================================================
print("\n" + "=" * 62)
print("섹션 2 — RAG 환각 탐지  (§1.2 사례①)")
print("=" * 62)
print("  §1.2 사례①: 의료 RAG 에이전트가 컨텍스트를 벗어난 복용량을 답했습니다.")
print("  enable_hallucination_detection=True → HallucinationDetector 자동 동작")
print("  컨텍스트와 응답 간 사실 일치도를 Group C(신뢰성) 차원에서 측정합니다.\n")
print("  시나리오: 의약품 복용 안내 RAG 에이전트\n")

monitor_s2 = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=True,  # Group C — HallucinationDetector 활성화
)

# 동일 컨텍스트에 대한 충실 응답 / 환각 응답 / 혼합 응답
CONTEXT_DRUG = (
    "아목시실린은 하루 2회, 식전에 복용합니다. "
    "성인 기준 1회 250mg이며 신장 기능 저하 시 용량을 조절해야 합니다."
)

HALLUCINATION_CASES = [
    (
        "충실한 응답",
        "하루 2회, 식전 복용. 1회 250mg.",
        # 컨텍스트 그대로 → 낮은 환각 점수 (정상)
        "아목시실린은 하루 2회, 식전에 복용합니다. 성인 기준 1회 250mg입니다.",
    ),
    (
        "환각 응답",
        "하루 2회, 식전 복용. 1회 250mg.",
        # 컨텍스트에 없는 정보 생성 → 높은 환각 점수 (위험)
        "하루 4회, 식후 30분에 복용하며 1회 500mg을 복용합니다. "
        "음주 후 복용해도 무방합니다.",
    ),
    (
        "부분 환각",
        "하루 2회, 식전 복용. 1회 250mg.",
        # 일부만 컨텍스트와 일치 → 중간 수준
        "하루 2회 복용합니다. 성인 기준 500mg이며 식후에 복용하세요.",
    ),
]

_s2_responses = iter([resp for _, _, resp in HALLUCINATION_CASES])

@agent_eval(monitor_s2, task_type="information_retrieval",
            task_id_prefix="s2", context_arg="context")
def rag_medical_agent(question: str, context: str = "",
                      ground_truth: str = "") -> str:
    """의료 정보 RAG 에이전트 (환각 시나리오 포함)."""
    # TODO(현업 적용): return llm.invoke(question)  # 실제 LLM 호출로 교체
    return next(_s2_responses)

for label, gt, resp in HALLUCINATION_CASES:
    rag_medical_agent(
        question=f"복용 안내_{label}",
        context=CONTEXT_DRUG,
        ground_truth=gt,
    )
    print(f"  [{label}] 기록 완료 — 응답: {resp[:40]}...")

print()
print("  → 환각 탐지 결과는 results/ch01_first_eval.html Harness Gate C에서 확인")


# ===========================================================================
# 섹션 3 — §1.2 사례③: SLA 위반 감지
#
# 고객 지원 에이전트의 레이턴시 급증 시나리오.
# §1.2: "특정 유형의 질의에서 에이전트가 도구를 평균 12번 호출"
#       "평소 2초 이내 → 피크 타임 30초 이상"
#       필요했던 평가: LatencyTracker + SLAConfig — Group D 성능계약
#
# 여기서는 실행 시간 단축을 위해 ms 단위로 비율만 재현합니다.
#   정상 응답:   10~50ms   (비율상 2초 이내에 해당)
#   SLA 위반:   150~250ms  (비율상 30초 급증에 해당)
#   SLA 기준:   p95 ≤ 100ms
# ===========================================================================
print("\n" + "=" * 62)
print("섹션 3 — SLA 위반 감지  (§1.2 사례③)")
print("=" * 62)
print("  §1.2 사례③: 고객 지원 에이전트가 피크 타임에 30초 이상 응답했습니다.")
print("  SLAConfig(p95_ms=...) 선언 → P95 레이턴시 초과 시 Gate D FAIL 판정")
print("  (예제는 실행 시간 단축을 위해 ms 단위로 비율 재현합니다.)\n")
print("  SLA 기준: P95 100ms 이내  |  정상 15건(10~50ms) + 급증 5건(150~250ms)\n")

monitor_s3 = PerformanceMonitor(output_dir=_OUTPUT_DIR)

sla_cfg = SLAConfig(
    p95_ms=100,            # P95 100ms 이내 (실 서비스라면 2,000ms)
    max_cost_per_task=0.005,
)

# 정상 응답(10~50ms) 15건 + SLA 위반(150~250ms) 5건
_latencies = (
    [random.uniform(0.010, 0.050) for _ in range(15)] +
    [random.uniform(0.150, 0.250) for _ in range(5)]
)
random.shuffle(_latencies)
_lat_iter = iter(_latencies)

@agent_eval(monitor_s3, task_type="qa", task_id_prefix="s3", sla=sla_cfg)
def support_agent(question: str, ground_truth: str = "") -> str:
    """고객 지원 에이전트 — 일부 케이스에서 레이턴시 급증."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(next(_lat_iter))
    return f"{question} 처리 완료되었습니다."

for i in range(20):
    support_agent(f"문의_{i + 1:02d}번", ground_truth="처리 완료")

print("  20건 완료")
print("  → SLA 위반 건수·P95 레이턴시는 results/ch01_sla_eval.html Gate D에서 확인")

monitor_s3.save_to_file("ch01_sla_eval")


# ===========================================================================
# 섹션 4 — §1.3 Harness 3요소 종합: Tracker × Config → Gate 배포 판정
#
# §1.3 코드 예시를 직접 실행합니다:
#   ① Config  — "이 에이전트는 어떤 조건에서 배포될 수 있는가"를 코드로 선언
#   ② Tracker — @agent_eval이 실행마다 지표를 자동 기록
#   ③ Gate    — Config 위반 여부를 종합 판정 → 배포 가능/불가 결정
#
# InstructionConfig: 응답에 '완료' 또는 '처리' 키워드가 없으면 TCR 저하
# SLAConfig: P95 응답 시간이 2,000ms 초과 시 Gate D FAIL
# ===========================================================================
print("\n" + "=" * 62)
print("섹션 4 — Harness 3요소 종합  (§1.3)")
print("=" * 62)
print("  § 1.3의 Tracker × Config × Gate 패턴을 직접 실행합니다.")
print("  ① Config 선언 → ② @agent_eval로 Tracker 자동 수집 → ③ Gate 판정")
print("  InstructionConfig: 키워드 미포함 응답 → TCR 저하 (Group A)")
print("  SLAConfig: P95 응답 초과 → Gate D FAIL (Group D)\n")

monitor_s4 = PerformanceMonitor(output_dir=_OUTPUT_DIR)

# ① Config — 배포 기준을 코드로 선언
instruction_cfg = InstructionConfig(
    required_keywords=["완료", "처리"],  # 응답에 반드시 포함되어야 할 키워드
    fail_on_violation=True,
)
harness_sla_cfg = SLAConfig(
    p95_ms=2000,
    max_cost_per_task=0.01,
)

# ② @agent_eval — Tracker 자동 수집 (실행마다 지표 기록)
@agent_eval(monitor_s4, task_type="qa", task_id_prefix="s4",
            instructions=instruction_cfg, sla=harness_sla_cfg)
def harness_agent(question: str, ground_truth: str = "") -> str:
    """Harness 3요소가 적용된 에이전트."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(random.uniform(0.01, 0.05))
    # 80%는 키워드 충족 / 20%는 미충족 → InstructionConfig 위반 발생
    responses_pass = ["처리 완료되었습니다.", "요청이 처리되었습니다.", "완료하였습니다."]
    responses_fail = ["확인되었습니다.", "알겠습니다."]
    pool = responses_pass * 4 + responses_fail  # 80 / 20 비율
    return random.choice(pool)

HARNESS_CASES = [
    ("주문 처리 요청",  "처리 완료되었습니다."),
    ("환불 신청",       "요청이 처리되었습니다."),
    ("정보 변경",       "완료하였습니다."),
    ("계정 문의",       "처리 완료되었습니다."),
    ("배송 조회",       "완료하였습니다."),
    ("서비스 해지",     "요청이 처리되었습니다."),
    ("포인트 조회",     "완료하였습니다."),
    ("쿠폰 적용",       "처리 완료되었습니다."),
    ("이메일 변경",     "완료하였습니다."),
    ("비밀번호 초기화", "요청이 처리되었습니다."),
]

for q, gt in HARNESS_CASES:
    harness_agent(q, ground_truth=gt)

# ③ Gate — Config 위반 여부 종합 판정
report = monitor_s4.generate_report()
rd     = report.to_dict()
am     = rd.get("accuracy_metrics", {})
tcr    = am.get("tcr", {}).get("tcr", 0)
acc    = am.get("accuracy_scores", {}).get("overall_accuracy", 0)

TCR_THRESHOLD = 80.0
ACC_THRESHOLD = 70.0

tcr_pass = tcr >= TCR_THRESHOLD
acc_pass = acc >= ACC_THRESHOLD
deployable = tcr_pass and acc_pass

print()
print("  [ Gate 판정 결과 ]")
print(f"  TCR    : {tcr:5.1f}%  (기준 {TCR_THRESHOLD:.0f}%)  {'✅ PASS' if tcr_pass else '❌ FAIL'}")
print(f"  정확도 : {acc:5.1f}%  (기준 {ACC_THRESHOLD:.0f}%)  {'✅ PASS' if acc_pass else '❌ FAIL'}")
print()
if deployable:
    print("  → ✅ 배포 가능  — 모든 Harness 기준 통과")
else:
    print("  → ❌ 배포 불가  — Harness 기준 미달 (CI/CD 파이프라인 차단)")
print()
print("  실무에서는 CLI로 자동 판정:")
print("    agent-eval gate results/ch01_first_eval.json --tcr 80 --accuracy 70")
print("    → 기준 미달 시 exit 1 → CI/CD 파이프라인 자동 차단")


# ===========================================================================
# 최종 리포트 저장
# ===========================================================================
print("\n" + "=" * 62)
print("최종 리포트 저장")
print("=" * 62)

monitor_s1.save_to_file("ch01_first_eval")
monitor_s2.save_to_file("ch01_hallucination_eval")
# monitor_s3은 이미 저장 완료
monitor_s4.save_to_file("ch01_harness_eval")

print()
print("  저장된 파일:")
print("    ch01_first_eval.json        — 섹션 1 assert vs 정확도 점수")
print("    ch01_hallucination_eval.json — 섹션 2 환각 탐지 (Group C)")
print("    ch01_sla_eval.json           — 섹션 3 SLA 위반 (Group D)")
print("    ch01_harness_eval.json       — 섹션 4 Gate 배포 판정")
print()
print("  대시보드 확인:")
print("    agent-eval dashboard --results results/")
print()
print("─" * 62)
print("다음: Ch02 — QuickEval 5분 첫 평가  (ch02_quickstart.py)")
print("  이 챕터의 패턴을 @eval.qa 한 줄로 시작합니다.")
print("─" * 62)
