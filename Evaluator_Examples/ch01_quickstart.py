"""
ch01_quickstart.py — 5분 안에 시작하는 첫 에이전트 평가
==========================================================
Book Chapter 01 — AI에이전트 평가란 무엇인가

QuickEval 원스톱 Facade로 에이전트를 3줄로 평가한다.
평가 결과가 어떻게 생성되고, 어디서 확인하는지 보여준다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch01_quickstart.py

결과:
    results/ch01_quickstart.json  (+ .html)
    → agent-eval dashboard --results results/
"""

import random
from pathlib import Path

from agent_evaluator import QuickEval, setup_otel

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch01-quickstart")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# QuickEval — 원스톱 평가 Facade
eval = QuickEval(_OUTPUT_DIR)

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    """평가 대상 에이전트 (실제 에이전트로 교체하세요)."""
    answers = {
        "한국의 수도는?":      "서울입니다.",
        "파이썬을 만든 사람은?": "귀도 반 로섬입니다.",
        "지구의 위성은?":       "달입니다.",
        "물의 화학식은?":       "H₂O입니다.",
        "1+1은?":              "3입니다.",   # 의도적 오답
    }
    return answers.get(question, "잘 모르겠습니다.")

# 평가 케이스 실행
QA_CASES = [
    ("한국의 수도는?",       "서울"),
    ("파이썬을 만든 사람은?", "귀도 반 로섬"),
    ("지구의 위성은?",        "달"),
    ("물의 화학식은?",        "H2O"),
    ("1+1은?",               "2"),
]

print("\n=== Ch01 첫 에이전트 평가 ===")
for question, gt in QA_CASES:
    result = my_agent(question, ground_truth=gt)
    print(f"  Q: {question:<25s}  응답: {result}")

# 결과 저장 + CI/CD 품질 게이팅
eval.save("ch01_quickstart")
print("\n결과 저장 완료: results/ch01_quickstart.json")
print("확인: agent-eval dashboard --results results/")
print("\n── CI/CD 품질 게이팅 (TCR ≥ 70%, accuracy ≥ 60%) ──")
try:
    eval.gate(tcr=70, accuracy=60)
    print("  ✅ 품질 게이트 통과")
except SystemExit:
    print("  ❌ 품질 게이트 실패 — 임계값 미달")
