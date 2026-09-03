"""
ch15_dashboard.py — 대시보드 시각화 전용 데이터 생성 + 기동 안내
====================================================================
Book Chapter 15 — 대시보드와 시각화

results/ 디렉토리에 대시보드용 JSON 데이터를 생성한 후
agent-eval dashboard 명령으로 기동하는 전체 흐름을 시연한다.

  섹션 1 — QuickEval으로 기본 평가 데이터 생성 (개요·태스크 목록 탭)
  섹션 2 — PerformanceMonitor + Harness Config (Gate A–G 탭)
  섹션 3 — AnomalyDetector + CostTracker (이상 감지·비용 탭)
  섹션 4 — LLMJudge 활성화 (LLM Judge 탭)
  섹션 5 — 대시보드 API 조회 예시 (requests 선택)
  섹션 6 — 대시보드 기동 안내

실행:
  python Evaluator_Examples/ch15_dashboard.py
  agent-eval dashboard results/ --port 8765
  브라우저: http://localhost:8765
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    QuickEval,
    create_taskresult,
    AnomalyDetector,
    CostTracker,
    SLAConfig,
    InstructionConfig,
    ExplainabilityConfig,
)
from agent_evaluator import agent_eval, setup_otel
from agent_evaluator.config import load_env

load_env()

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
Path(_OUTPUT_DIR).mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch15-dashboard")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ─────────────────────────────────────────────────────────────
# 섹션 1 — QuickEval: 개요·태스크 목록 탭 데이터 생성
# ─────────────────────────────────────────────────────────────
print("=" * 55)
print("섹션 1 — QuickEval 기본 평가 데이터 생성")
print("=" * 55)

QA_CASES = [
    ("한국의 수도는?",          "서울"),
    ("Python의 특징은?",        "인터프리터 언어이며 동적 타이핑을 지원한다"),
    ("REST API란?",             "HTTP 기반 무상태 아키텍처 스타일"),
    ("머신러닝과 딥러닝의 차이?", "딥러닝은 머신러닝의 하위 분야"),
    ("Docker의 장점은?",        "환경 격리와 이식성"),
    ("Git의 장점은?",           "버전 관리와 협업"),
    ("SQL과 NoSQL 차이?",       "스키마 유연성과 수평 확장성"),
    ("마이크로서비스란?",        "독립 배포 가능한 서비스 단위"),
]

eval_q = QuickEval(_OUTPUT_DIR, auto_save=False)

@eval_q.qa
def qa_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    answers = {
        "한국의 수도": "서울입니다",
        "Python": "Python은 인터프리터 기반 동적 타이핑 언어입니다",
        "REST API": "REST는 HTTP 기반 무상태 아키텍처 스타일입니다",
        "머신러닝": "딥러닝은 머신러닝의 하위 분야로 신경망을 사용합니다",
        "Docker": "Docker는 컨테이너로 환경 격리와 이식성을 제공합니다",
        "Git": "Git은 분산 버전 관리 시스템입니다",
        "SQL": "NoSQL은 스키마 유연성과 수평 확장이 용이합니다",
        "마이크로서비스": "마이크로서비스는 독립 배포 가능한 서비스 단위입니다",
    }
    for key, ans in answers.items():
        if key in question:
            return ans
    return f"답변: {question}"

for question, gt in QA_CASES:
    qa_agent(question, ground_truth=gt)

summary = eval_q.summary()
print(f"  TCR:      {summary['tcr']:.1f}%")
print(f"  정확도:    {summary['accuracy']:.1f}%")
print(f"  p95 지연:  {summary['p95_latency']:.3f}s")
eval_q.save("ch15_dashboard_quickeval")
print("  → results/ch15_dashboard_quickeval.json 저장")

# ─────────────────────────────────────────────────────────────
# 섹션 2 — PerformanceMonitor + Harness Config: Gate A–G 탭
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("섹션 2 — Harness Config Gate A–G 데이터 생성")
print("=" * 55)

monitor_h = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

@agent_eval(
    monitor_h,
    task_type="qa",
    task_id_prefix="dash_gate",
    instructions=InstructionConfig(
        required_keywords=["답변", "출처"],
        fail_on_violation=False,
    ),
    sla=SLAConfig(p95_ms=2000),
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=20,
        reasoning_markers=["왜냐하면", "따라서", "근거"],
    ),
)
def harness_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"답변: {question}에 대한 결과입니다 | 출처: 내부 DB | 왜냐하면 최신 데이터를 참조했습니다"

HARNESS_CASES = [
    ("서비스 가용성은?",    "정상"),
    ("오늘 에러율은?",      "0.5%"),
    ("배포 일정은?",        "금요일"),
    ("모델 정확도 현황?",   "87%"),
    ("비용 현황은?",        "$120"),
]

for question, gt in HARNESS_CASES:
    harness_agent(question, ground_truth=gt)

monitor_h.save_to_file("ch15_dashboard_harness")
print("  → results/ch15_dashboard_harness.json 저장")
print("  → 대시보드 'Harness Gate' 탭에서 Gate A–G 점수 확인 가능")

# ─────────────────────────────────────────────────────────────
# 섹션 3 — AnomalyDetector + CostTracker: 이상 감지·비용 탭
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("섹션 3 — AnomalyDetector + CostTracker 데이터 생성")
print("=" * 55)

monitor_a = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
# baseline_window=15: 앞 15개를 기준선으로, detection_window=5: 뒤 5개(이상치 포함)로 탐지
anomaly_detector = AnomalyDetector(baseline_window=15, detection_window=5)
cost_tracker = CostTracker(budget_per_day=5.0)

random.seed(42)
latencies = [random.gauss(0.8, 0.15) for _ in range(18)] + [4.2, 7.8]  # 이상치 2개 (총 20개)

for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"dash_anomaly_{i:03d}",
        question=f"질문 {i}",
        response=f"응답 {i}",
        ground_truth=f"정답 {i}",
        execution_time=round(max(0.1, lat), 3),
        task_type="qa",
        tokens_used={"input": 80, "output": 20, "total": 100},
    
        use_korean_tokenizer=True,
    )
    monitor_a.record_task(result)
    cost_tracker.record("openai", "gpt-5-nano", cost_usd=0.00005)

events = anomaly_detector.scan(monitor_a)
for event in events:
    print(f"  ⚠️  이상 탐지: {event.type} — {event.detail}")

today_cost = cost_tracker.get_today_cost()
budget_exceeded = cost_tracker.is_budget_exceeded()
print(f"  예산 현황: 사용={today_cost:.4f}$ / 한도=5.00$ | {'초과' if budget_exceeded else '정상'}")

monitor_a.save_to_file("ch15_dashboard_anomaly")
print("  → results/ch15_dashboard_anomaly.json 저장")
print("  → 대시보드 '이상 감지' 탭에서 latency_spike 이벤트 확인 가능")

# ─────────────────────────────────────────────────────────────
# 섹션 4 — LLMJudge 활성화: LLM Judge 탭 (API 키 필요)
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("섹션 4 — LLMJudge 탭 (API 키 있을 때만 활성화)")
print("=" * 55)

has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

if has_api:
    monitor_llm = PerformanceMonitor(
        output_dir=_OUTPUT_DIR,
        enable_llm_judge=True,
        judge_sample_rate=1.0,
        use_korean_tokenizer=True,
    )

    @agent_eval(monitor_llm, task_type="qa", task_id_prefix="dash_judge")
    def judge_agent(question: str, ground_truth: str = "") -> str:
        # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
        #   예) return client.chat.completions.create(model="gpt-5-nano",
        #        messages=[{"role":"user","content":question}]).choices[0].message.content
        return f"이 질문에 대한 포괄적이고 근거 있는 답변입니다: {question}"

    for question, gt in QA_CASES[:3]:
        judge_agent(question, ground_truth=gt)

    monitor_llm.save_to_file("ch15_dashboard_judge")
    print("  → results/ch15_dashboard_judge.json 저장")
    print("  → 대시보드 'LLM Judge' 탭에서 completeness·relevance·factual_consistency 확인")
else:
    print("  API 키 없음 — LLMJudge 섹션 건너뜀")
    print("  OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 설정 후 재실행")

# ─────────────────────────────────────────────────────────────
# 섹션 5 — 대시보드 API 조회 예시
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("섹션 5 — 대시보드 API 활용 (agent-eval dashboard 기동 후 사용)")
print("=" * 55)

_API_EXAMPLES = """
# 기동 후 다음 API로 데이터 조회:

# 전체 평가 통계
GET http://localhost:8765/api/stats

# 태스크 목록 (정확도 낮은 것 먼저)
GET http://localhost:8765/api/tasks?sort=accuracy&order=asc

# 정확도 0.5 미만 필터
GET http://localhost:8765/api/tasks/filter?accuracy_lt=0.5

# 이상 감지 이벤트
GET http://localhost:8765/api/anomaly

# 비용 현황
GET http://localhost:8765/api/cost

# Harness Gate 점수
GET http://localhost:8765/api/harness

# HTML 보고서
GET http://localhost:8765/report/ch15_dashboard_harness
"""
print(_API_EXAMPLES)

# ─────────────────────────────────────────────────────────────
# 섹션 6 — 대시보드 기동 안내
# ─────────────────────────────────────────────────────────────
print("=" * 55)
print("섹션 6 — 대시보드 기동")
print("=" * 55)
print()
print("  # 별도 터미널에서 실행")
print("  agent-eval dashboard results/ --port 8765")
print()
print("  # 브라우저 접속")
print("  http://localhost:8765")
print()
print("  # 생성된 JSON 파일 목록")
for f in sorted(Path(_OUTPUT_DIR).glob("ch15_dashboard_*.json")):
    print(f"  ✅ {f}")
print()
print("  # 탭별 데이터 연결")
print("  ├─ 개요·태스크 목록  → ch15_dashboard_quickeval.json")
print("  ├─ Harness Gate A–G → ch15_dashboard_harness.json")
print("  ├─ 이상 감지·비용   → ch15_dashboard_anomaly.json")
print("  └─ LLM Judge        → ch15_dashboard_judge.json (API 키 필요)")
