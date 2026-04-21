"""
ch01_first_eval.py — Layer 1 기초 지표 (정확도·품질·할루시네이션·TCR)
=======================================================================
Book Chapter 01 — AI에이전트 평가란 무엇인가

  AccuracyEvaluator       : QA / 코드 / RAG 정확도
  ResponseQualityEvaluator: 5차원 응답 품질
  HallucinationDetector   : 사실 일관성 점수
  TaskCompletionTracker   : 태스크 완료율 (TCR)

의존성:
    필수: pip install agent-evaluator
    선택: agent-eval monitor   (Phoenix OTEL 시각화)

실행:
    python Evaluator_Examples/ch01_first_eval.py

결과:
    results/ch01_first_eval.json  (+ .html)
    → agent-eval dashboard --results results/
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/01_layer1_all_metrics.py
"""

import random
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel
from agent_evaluator.decorators import agent_eval

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch01-first-eval")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=True,
    enable_transparency=True,
)

# ===========================================================================
# 섹션 1: QA 정확도
# ===========================================================================
print("\n=== 섹션 1: QA 정확도 ===")

@agent_eval(monitor, task_type="qa", task_id_prefix="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    answers = {
        "한국의 수도는?":         "서울입니다.",
        "파이썬을 만든 사람은?":   "귀도 반 로섬입니다.",
        "지구의 위성은?":          "달입니다.",
        "물의 화학식은?":          "H2O입니다.",
        "1+1은?":                  "3입니다.",
    }
    return answers.get(question, "잘 모르겠습니다.")

QA_CASES = [
    ("한국의 수도는?",       "서울"),
    ("파이썬을 만든 사람은?", "귀도 반 로섬"),
    ("지구의 위성은?",        "달"),
    ("물의 화학식은?",        "H2O"),
    ("1+1은?",               "2"),
]

for question, gt in QA_CASES:
    qa_agent(question, ground_truth=gt)
    print(f"  Q: {question:<25s}  완료")

# ===========================================================================
# 섹션 2: 코드 / RAG 정확도
# ===========================================================================
print("\n=== 섹션 2: 코드 & RAG 정확도 ===")

@agent_eval(monitor, task_type="code_generation", task_id_prefix="code")
def code_agent(question: str, ground_truth: str = "") -> str:
    if "피보나치" in question:
        return "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)"
    return "print('hello world')"

@agent_eval(monitor, task_type="information_retrieval",
            task_id_prefix="rag", context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
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
# 섹션 3: 응답 품질 5차원 (ResponseQualityEvaluator)
# ===========================================================================
print("\n=== 섹션 3: 응답 품질 5차원 ===")

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
# 섹션 4: 할루시네이션 탐지
# ===========================================================================
print("\n=== 섹션 2: 할루시네이션 탐지 ===")

HALLUCINATION_CASES = [
    (
        "파리는 어느 나라 수도?",
        "파리는 프랑스의 수도이며 약 200만 명이 거주하는 유럽의 주요 도시입니다.",
        "파리는 프랑스의 수도이며 약 200만 명이 거주하는 유럽의 주요 도시입니다.",
        "프랑스",
    ),
    (
        "아인슈타인의 출생 연도와 출생지는?",
        "알베르트 아인슈타인은 1879년 독일 울름에서 태어난 물리학자입니다.",
        "아인슈타인은 1865년 미국 뉴욕 맨해튼에서 태어났으며 어린 시절을 보스턴에서 보냈습니다.",
        "1879년, 독일 울름",
    ),
    (
        "광합성이란 무엇인가?",
        "광합성은 식물이 태양 빛 에너지를 이용해 이산화탄소와 물로 포도당을 합성하는 생화학 과정입니다.",
        "광합성은 동물이 먹이를 섭취하여 산소를 생성하고 에너지를 저장하는 신진대사 과정을 의미합니다.",
        "식물이 빛으로 포도당 합성",
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
# 섹션 5: 태스크 완료율 (TCR)
# ===========================================================================
print("\n=== 섹션 3: 태스크 완료율 (TCR) ===")

SUCCESS_RATE = 0.85

for i in range(20):
    is_success = random.random() < SUCCESS_RATE
    result = create_taskresult(
        task_id=f"tcr_{i:03d}",
        question=f"태스크 {i:02d}번",
        response=f"태스크 {i:02d}번에 대한 성공적인 처리 결과입니다." if is_success else "",
        ground_truth="처리 결과",
        execution_time=round(random.uniform(0.3, 2.0), 3),
        task_type="qa",
        tokens_used={"input": 40, "output": 10, "total": 50},
    )
    monitor.record_task(result)

# ===========================================================================
# 최종 리포트
# ===========================================================================
print("\n=== 최종 리포트 ===")

report = monitor.generate_report().to_dict()
total_tasks = report.get("total_tasks", 0)
am  = report.get("accuracy_metrics", {})
acc = am.get("accuracy_scores", {}).get("overall_accuracy", 0) / 100
tcr = am.get("tcr", {}).get("tcr", 0) / 100

print(f"  총 태스크 : {total_tasks}건")
print(f"  평균 정확도: {acc:.2%}")
print(f"  TCR       : {tcr:.1%}")

monitor.save_to_file("ch01_first_eval")
print("\n결과 저장 완료: results/ch01_first_eval.json")
print("확인: agent-eval dashboard --results results/")
