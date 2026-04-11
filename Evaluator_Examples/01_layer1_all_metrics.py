"""
01_layer1_all_metrics.py — Layer 1 전체 지표 (Quality + Performance)
====================================================================
외부 의존성 없이 Agent-Evaluator Layer 1 지표 25개 중 6종 트래커를 검증한다.

  - AccuracyEvaluator  : QA / 코드 / RAG 정확도
  - HallucinationDetector : 사실 일관성 점수
  - ResponseQualityEvaluator : 5차원 응답 품질
  - LatencyTracker    : p50/p95/p99 지연시간
  - TokenEconomyTracker : 토큰 사용량 + 비용 추정
  - TaskCompletionTracker : 태스크 완료율 (TCR)

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — 없어도 실행됨)

실행:
    python Evaluator_Examples/01_layer1_all_metrics.py

결과:
    results/01_layer1_all_metrics.json   (+ .html)
    → agent-eval dashboard 로 확인 가능
"""

import random
import time
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel
from agent_evaluator.decorators import agent_eval, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="01-layer1-metrics")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# PerformanceMonitor 초기화
# enable_hallucination_detection=True 로 HallucinationDetector 활성
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=True,
)

# ===========================================================================
# 섹션 1: Quality — QA 정확도 (@agent_eval 데코레이터)
# ===========================================================================
print("\n=== 섹션 1: QA 정확도 ===")

@agent_eval(monitor, task_type="qa", task_id_prefix="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    """단순 QA 에이전트 시뮬레이션."""
    answers = {
        "한국의 수도는?":         "서울입니다.",
        "파이썬을 만든 사람은?":   "귀도 반 로섬입니다.",
        "지구의 위성은?":          "달입니다.",
        "물의 화학식은?":          "H2O입니다.",
        "1+1은?":                  "3입니다.",   # 의도적 오답
    }
    return answers.get(question, "잘 모르겠습니다.")

QA_CASES = [
    ("한국의 수도는?",       "서울"),
    ("파이썬을 만든 사람은?", "귀도 반 로섬"),
    ("지구의 위성은?",        "달"),
    ("물의 화학식은?",        "H2O"),
    ("1+1은?",               "2"),   # 오답 케이스
]

for question, gt in QA_CASES:
    result = qa_agent(question, ground_truth=gt)
    print(f"  Q: {question:<25s}  응답: {result}")

print("  QA 정확도 기록 완료 (5건)")

# ===========================================================================
# 섹션 2: Quality — 코드 / RAG 정확도
# ===========================================================================
print("\n=== 섹션 2: 코드 & RAG 정확도 ===")

@agent_eval(monitor, task_type="code_generation", task_id_prefix="code")
def code_agent(question: str, ground_truth: str = "") -> str:
    """코드 생성 에이전트 시뮬레이션."""
    if "피보나치" in question:
        return "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)"
    return "print('hello world')"

@agent_eval(monitor, task_type="information_retrieval",
            task_id_prefix="rag", context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    """RAG 에이전트 시뮬레이션 (context에서 답 추출)."""
    return context[:120] if context else "컨텍스트가 없습니다."

code_agent("피보나치 수열 함수를 파이썬으로 작성해줘",
           ground_truth="def fib(n):\n    if n<=1: return n\n    return fib(n-1)+fib(n-2)")
print("  코드 정확도 기록 완료")

rag_agent(
    "서울의 주요 특징은?",
    context="서울은 대한민국의 수도이자 최대 도시로, 약 1,000만 명의 인구가 살고 있습니다.",
    ground_truth="서울은 대한민국의 수도",
)
print("  RAG 정확도 기록 완료")

# ===========================================================================
# 섹션 3: Quality — 할루시네이션 탐지
# ===========================================================================
print("\n=== 섹션 3: 할루시네이션 탐지 ===")

HALLUCINATION_CASES = [
    # (question, context, response, ground_truth)
    # ① 사실 일치 — 탐지 없음
    (
        "파리는 어느 나라 수도?",
        "파리는 프랑스의 수도이며 약 200만 명이 거주하는 유럽의 주요 도시입니다.",
        "파리는 프랑스의 수도이며 약 200만 명이 거주하는 유럽의 주요 도시입니다.",
        "프랑스",
    ),
    # ② 수치 불일치 — numerical_inconsistency 탐지 (1879 ≠ context의 1879 맞지만 국적이 다름)
    (
        "아인슈타인의 출생 연도와 출생지는?",
        "알베르트 아인슈타인은 1879년 독일 울름에서 태어난 물리학자입니다.",
        "아인슈타인은 1865년 미국 뉴욕 맨해튼에서 태어났으며 어린 시절을 보스턴에서 보냈습니다.",  # 연도·장소 모두 오류
        "1879년, 독일 울름",
    ),
    # ③ 내용 불일치 — unsupported_claim 탐지 (문장이 충분히 길어야 함)
    (
        "광합성이란 무엇인가?",
        "광합성은 식물이 태양 빛 에너지를 이용해 이산화탄소와 물로 포도당을 합성하는 생화학 과정입니다.",
        "광합성은 동물이 먹이를 섭취하여 산소를 생성하고 에너지를 저장하는 신진대사 과정을 의미합니다.",  # 식물→동물, 완전 반대 설명
        "식물이 빛으로 포도당 합성",
    ),
    # ④ 수치 불일치 추가 — 인구수 오류
    (
        "서울의 인구는?",
        "서울특별시의 인구는 약 950만 명으로 대한민국 최대 도시입니다.",
        "서울의 인구는 약 3200만 명으로 세계에서 두 번째로 큰 도시입니다.",  # 수치 오류
        "950만 명",
    ),
]

for q, ctx, resp, gt in HALLUCINATION_CASES:
    result = create_taskresult(
        task_id=f"hall_{hash(q) % 10000:04d}",
        question=q,
        response=resp,
        ground_truth=gt,
        context=ctx,
        execution_time=round(random.uniform(0.5, 2.0), 3),
        task_type="information_retrieval",
        tokens_used={"input": 120, "output": 40, "total": 160},
    )
    monitor.record_task(result)
    print(f"  할루시네이션 탐지: {q[:25]:<26s}  score={result.accuracy_score:.2f}")

# ===========================================================================
# 섹션 4: Quality — 응답 품질 (5차원)
# ===========================================================================
print("\n=== 섹션 4: 응답 품질 (5차원) ===")

QUALITY_CASES = [
    ("고품질 응답",  "파이썬은 간결하고 읽기 쉬운 문법으로 설계된 고급 프로그래밍 언어입니다. 다양한 라이브러리 생태계와 커뮤니티 지원 덕분에 데이터 과학, 웹 개발, 자동화 분야에서 폭넓게 사용됩니다."),
    ("중간 품질",   "파이썬은 프로그래밍 언어입니다. 사용하기 쉽습니다."),
    ("저품질 응답", "몰라요."),
]

for label, resp in QUALITY_CASES:
    result = create_taskresult(
        task_id=f"qual_{label[:4]}",
        question="파이썬이란 무엇인가요?",
        response=resp,
        ground_truth="파이썬은 간결한 문법의 고급 프로그래밍 언어",
        execution_time=round(random.uniform(0.3, 1.5), 3),
        task_type="qa",
        tokens_used={"input": 80, "output": len(resp.split()), "total": 80 + len(resp.split())},
    )
    monitor.record_task(result)
    print(f"  [{label}] acc={result.accuracy_score:.2f}  len={len(resp)}자")

# ===========================================================================
# 섹션 5: Performance — 지연시간 분포 (p50/p95/p99)
# ===========================================================================
print("\n=== 섹션 5: 지연시간 분포 ===")

# 정규 분포에 이상치 추가하여 현실적 지연 패턴 생성
latencies = [random.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]  # 이상치 2개
latencies = [max(0.1, lat) for lat in latencies]

for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"perf_{i:03d}",
        question="지연시간 테스트 쿼리",
        response="응답 완료",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
        tokens_used={"input": 50, "output": 20, "total": 70},
    )
    monitor.record_task(result)

report = monitor.generate_report()
em = report.to_dict().get("efficiency_metrics", {})
lat_stats = em.get("latency", {})
print(f"  p50 = {float(lat_stats.get('p50', 0)):.2f}s")
print(f"  p95 = {float(lat_stats.get('p95', 0)):.2f}s")
print(f"  p99 = {float(lat_stats.get('p99', 0)):.2f}s")
print(f"  avg = {float(lat_stats.get('mean', 0)):.2f}s")

# ===========================================================================
# 섹션 6: Performance — 토큰 경제성 + 비용 추정
# ===========================================================================
print("\n=== 섹션 6: 토큰 경제성 & 비용 ===")

TOKEN_MODELS = [
    ("gpt-4o",       {"input": 800, "output": 200, "total": 1000, "model": "gpt-4o"}),
    ("claude-3",     {"input": 600, "output": 150, "total": 750,  "model": "claude-3-sonnet"}),
    ("gpt-4o-mini",  {"input": 400, "output": 100, "total": 500,  "model": "gpt-4o-mini"}),
]

for model_name, tokens in TOKEN_MODELS:
    result = create_taskresult(
        task_id=f"tok_{model_name}",
        question="토큰 비용 테스트",
        response="응답 내용",
        ground_truth="응답",
        execution_time=round(random.uniform(1.0, 3.0), 3),
        task_type="qa",
        tokens_used=tokens,
    )
    monitor.record_task(result)
    print(f"  [{model_name:<12s}] 총 {tokens['total']:4d} 토큰")

tok_em = monitor.generate_report().to_dict().get("efficiency_metrics", {})
tok_report = tok_em.get("tokens", {})
total_tok = tok_report.get("total_tokens", 0)
print(f"  누적 토큰: {int(total_tok):,}")
cost = tok_report.get("total_cost")
if cost:
    print(f"  예상 비용: ${float(cost):.4f} USD")

# ===========================================================================
# 섹션 7: Performance — TCR (태스크 완료율)
# ===========================================================================
print("\n=== 섹션 7: 태스크 완료율 (TCR) ===")

SUCCESS_RATE = 0.85   # 시뮬레이션: 85% 성공

for i in range(20):
    is_success = random.random() < SUCCESS_RATE
    result = create_taskresult(
        task_id=f"tcr_{i:03d}",
        question=f"태스크 {i:02d}번",
        response="성공" if is_success else "",
        ground_truth="성공",
        execution_time=round(random.uniform(0.3, 2.0), 3),
        task_type="qa",
        tokens_used={"input": 40, "output": 10, "total": 50},
    )
    monitor.record_task(result)

final_report = monitor.generate_report()
tcr_val = final_report.to_dict().get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0)
tcr = tcr_val / 100
print(f"  TCR = {tcr:.1%}  (목표: {SUCCESS_RATE:.0%})")

# ===========================================================================
# 최종 리포트 & 저장
# ===========================================================================
print("\n=== 최종 리포트 ===")

report_dict = final_report.to_dict()
total_tasks = report_dict.get("total_tasks", 0)
am  = report_dict.get("accuracy_metrics", {})
em  = report_dict.get("efficiency_metrics", {})
acc = am.get("accuracy_scores", {}).get("overall_accuracy", 0) / 100
avg_lat = em.get("latency", {}).get("mean", 0)
tcr = am.get("tcr", {}).get("tcr", 0) / 100

print(f"  총 태스크 : {total_tasks}건")
print(f"  평균 정확도: {acc:.2%}")
print(f"  평균 지연  : {avg_lat:.2f}s")
print(f"  TCR       : {tcr:.1%}")

monitor.save_to_file("01_layer1_all_metrics")
print(f"\n결과 저장 완료: results/01_layer1_all_metrics.json")
print("확인: agent-eval dashboard --results results/")

# ===========================================================================
# 부록: RAG 골든 데이터셋 파일 로드 → 배치 평가
# ===========================================================================
# RAG 평가는 실제 프로덕션에서 미리 준비된 골든 데이터셋(QA 쌍)으로 수행한다.
# data/golden_datasets/rag_candidates.json → 로드 → 배치 평가 → 결과 저장
# (대시보드 케이스 검토 탭에서 승인된 케이스가 이 파일을 구성)
# ===========================================================================
print("\n=== 부록: RAG 골든 데이터셋 배치 평가 ===")

import json  # noqa: E402 (섹션 구분을 위해 여기서 import)

_GOLDEN_FILE = _PROJECT_ROOT / "data" / "golden_datasets" / "rag_candidates.json"

if _GOLDEN_FILE.exists():
    rag_golden = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    monitor_rag = PerformanceMonitor(output_dir=_OUTPUT_DIR, enable_hallucination_detection=True)

    @agent_eval(monitor_rag, task_type="information_retrieval",
                task_id_prefix="rag_golden", context_arg="context")
    def rag_agent_golden(question: str, context: str = "", ground_truth: str = "") -> str:
        """골든 데이터셋 기반 RAG 에이전트 (시뮬레이션)."""
        # 실제 에이전트 호출로 교체:
        #   return real_rag_agent(question, context)
        ctx = context or ""
        if ctx and ground_truth:
            # 컨텍스트가 있으면 ground_truth 키워드 포함 응답 시뮬레이션
            return ctx[:80] + " " + ground_truth[:30]
        return "관련 정보를 찾을 수 없습니다."

    for case in rag_golden:
        rag_agent_golden(
            question=case["question"],
            context=case.get("context", ""),
            ground_truth=case.get("ground_truth", ""),
        )

    rag_report = monitor_rag.generate_report().to_dict()
    rag_acc = rag_report.get("accuracy_metrics", {}).get("accuracy_scores", {}).get("overall_accuracy", 0)
    print(f"  골든 케이스 {len(rag_golden)}건 평가 완료  평균 정확도: {rag_acc:.1f}%")
    monitor_rag.save_to_file("01_rag_golden_eval")
    print(f"  저장: results/01_rag_golden_eval.json")
else:
    print(f"  ※ {_GOLDEN_FILE} 없음 — 06_operational.py 먼저 실행하거나 agent-eval dashboard에서 케이스 승인 후 병합하세요.")
