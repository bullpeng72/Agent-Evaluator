"""
ch24_gate_mapping.py — Gate 매핑 전략: 실패 모드에서 Config로
=============================================================
Book Chapter 24 — Gate 매핑 전략

실패 모드 카탈로그 3문항 → Gate Config 번역 과정을 단계별로 실습한다.
범용 매핑 테이블을 먼저 보고, Lecture_forge 실제 사례로 검증한다.

  섹션 1: 실패 모드 카탈로그 — 3문항 방법론
  섹션 2: 범용 매핑 테이블 적용 실습
  섹션 3: Gate Config 데코레이터 적용 — Gate A / B / D / E / F
  섹션 4: Gate 가중치 설계
  섹션 5: 측정 결과 확인

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch24_gate_mapping.py

결과:
    results/ch24_gate_mapping.json  (+ .html)
"""

import random
import time
from pathlib import Path

from agent_evaluator import (
    # Gate A
    GoalAlignmentConfig,
    InstructionConfig,
    # Gate B
    LoopDetectionConfig,
    ScopeConfig,
    StateConsistencyConfig,
    # Gate C
    FaultToleranceConfig,
    GracefulDegradationConfig,
    ReproducibilityConfig,
    # Gate D
    CostPredictabilityConfig,
    EfficiencyConfig,
    ResourceBudgetConfig,
    SLAConfig,
    # Gate E
    ComplianceConfig,
    ThreatResponseConfig,
    ThreatSeverityConfig,
    # Gate F
    AgentRoleConfig,
    ConflictResolutionConfig,
    ConsensusConfig,
    PropagationConfig,
    # Gate G
    ErrorDiagnosisConfig,
    ExplainabilityConfig,
    ObservabilityConfig,
    PerformanceMonitor,
    QuickEval,
    create_taskresult,
    setup_otel,
)
from agent_evaluator import agent_eval

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")


def _tcr(report):
    return report.to_dict()['accuracy_metrics']['tcr']['tcr']

def _acc(report):
    return float(report.to_dict()['accuracy_metrics']['accuracy_scores']['overall_accuracy'])

def _p95(report):
    return float(report.to_dict()['efficiency_metrics']['latency']['p95'])

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006",
                       service_name="ch23-gate-mapping")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

print("=" * 60)
print("  Ch24: Gate 매핑 전략 — 실패 모드에서 Config로")
print("=" * 60)

# ===========================================================================
# 섹션 1: 실패 모드 카탈로그 — 3문항 방법론
# ===========================================================================
print("\n=== 섹션 1: 실패 모드 카탈로그 3문항 ===")

print("""
  Gate부터 시작하지 않는다. 실패 모드부터 시작한다.

  ┌─────────────────────────────────────────────────────────┐
  │  질문 1: "이 시스템이 완전히 망가진다면 어떻게 망가지는가?"  │
  │  질문 2: "품질이 몰래 떨어진다면 어떤 증상으로 나타나는가?" │
  │  질문 3: "이 시스템이 뚫린다면 어떤 경로로 뚫리는가?"       │
  └─────────────────────────────────────────────────────────┘
""")

# 가상 프로젝트: 고객 지원 자동화 시스템 (범용 예시)
print("  [범용 예시] 고객 지원 자동화 시스템 — 실패 모드 카탈로그\n")

FAILURE_CATALOG = [
    {
        "질문": "Q1",
        "실패_모드": "FAQ 에이전트가 관련 없는 답변을 반환해도 아무도 모름",
        "증상": "사용자 재문의율 상승, CSAT 하락",
        "gate": "A",
        "config": "GoalAlignmentConfig(alignment_threshold=0.7)",
    },
    {
        "질문": "Q1",
        "실패_모드": "티켓 분류 루프 — 에이전트가 같은 티켓을 계속 재처리",
        "증상": "처리 시간 폭발, API 비용 급증",
        "gate": "B",
        "config": "LoopDetectionConfig(consecutive_repeat_threshold=2)",
    },
    {
        "질문": "Q2",
        "실패_모드": "RAG 검색 품질 하락 — 오래된 문서가 최상위 검색",
        "증상": "같은 질문에 대한 답변 일관성 하락",
        "gate": "C",
        "config": "ReproducibilityConfig(reproducibility_threshold=0.85)",
    },
    {
        "질문": "Q2",
        "실패_모드": "응답 시간 P95가 SLA 초과",
        "증상": "느린 응답에 대한 사용자 불만",
        "gate": "D",
        "config": "SLAConfig(p95_ms=3000, p99_ms=5000)",
    },
    {
        "질문": "Q3",
        "실패_모드": "사용자가 '이 티켓 무시해줘' 삽입 시 티켓 건너뜀",
        "증상": "특정 티켓 미처리",
        "gate": "E",
        "config": "ThreatSeverityConfig(fail_on_critical=True)",
    },
    {
        "질문": "Q1",
        "실패_모드": "2단계 에이전트(분류→답변)에서 우선순위 정보 소실",
        "증상": "긴급 티켓이 일반 티켓과 동일하게 처리",
        "gate": "F",
        "config": "PropagationConfig(key_facts=['priority', 'tier'])",
    },
    {
        "질문": "Q2",
        "실패_모드": "어떤 에이전트에서 느려지는지 파악 불가",
        "증상": "전체 지연은 보이지만 병목 위치 모름",
        "gate": "G",
        "config": "ObservabilityConfig(check_trace_continuity=True)",
    },
]

for item in FAILURE_CATALOG:
    print(f"  [{item['질문']}] Gate {item['gate']} ← {item['실패_모드']}")
    print(f"         증상: {item['증상']}")
    print(f"         → {item['config']}\n")

# ===========================================================================
# 섹션 2: 범용 매핑 테이블
# ===========================================================================
print("\n=== 섹션 2: 범용 매핑 테이블 ===")

print("""
  실패 모드 유형 → Gate 매핑 규칙:

  ┌──────────────────────────────┬────────┬──────────────────────────────────┐
  │ 실패 모드 유형               │ Gate   │ 1차 Config                       │
  ├──────────────────────────────┼────────┼──────────────────────────────────┤
  │ 목표 미달성 (성공 기준 없음) │ A      │ GoalAlignmentConfig              │
  │ 지시 무시 / 탈선             │ A      │ InstructionConfig                │
  │ 무한 루프 / 과도한 반복      │ B      │ LoopDetectionConfig              │
  │ 범위 일탈 (허가 외 동작)     │ B      │ ScopeConfig                      │
  │ 상태 불일치                  │ B      │ StateConsistencyConfig           │
  │ 동일 입력 다른 결과          │ C      │ ReproducibilityConfig            │
  │ 오류 시 전체 중단            │ C      │ FaultToleranceConfig             │
  │ 품질 하한선 없음             │ C      │ GracefulDegradationConfig        │
  │ 응답 시간 SLA 초과           │ D      │ SLAConfig                        │
  │ 토큰/비용 폭발               │ D      │ ResourceBudgetConfig             │
  │ 비용 예측 불가               │ D      │ CostPredictabilityConfig         │
  │ 프롬프트 인젝션              │ E      │ ThreatSeverityConfig             │
  │ 민감 정보 출력 포함          │ E      │ ComplianceConfig                 │
  │ 정보 전파 왜곡               │ F      │ PropagationConfig                │
  │ 에이전트 역할 위반           │ F      │ AgentRoleConfig                  │
  │ 합의 실패                    │ F      │ ConsensusConfig                  │
  │ 추론 불투명                  │ G      │ ExplainabilityConfig             │
  │ 병목 위치 파악 불가          │ G      │ ObservabilityConfig              │
  │ 오류 원인 진단 불가          │ G      │ ErrorDiagnosisConfig             │
  └──────────────────────────────┴────────┴──────────────────────────────────┘
""")

# ===========================================================================
# 섹션 3: Gate Config 데코레이터 적용
# ===========================================================================
print("\n=== 섹션 3: Gate Config 데코레이터 적용 ===")

print("""
  Gate Config는 @agent_eval 데코레이터에 전달한다.
  PerformanceMonitor는 공유 저장소 역할만 하고,
  Config는 각 에이전트 함수 단위로 지정한다.

  monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

  # Gate A + B + D + F 적용 예시
  @agent_eval(monitor, task_type="qa",
      instructions=InstructionConfig(required_keywords=["학습목표"]),
      loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
      sla=SLAConfig(p95_ms=120_000),
      propagation=PropagationConfig(key_facts=["audience_level"]),
  )
  def content_writer_agent(question: str, ground_truth: str = "") -> str: ...
""")

# 중앙 모니터 (Gate Config 없이 — 데코레이터에서 전달)
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    use_korean_tokenizer=True,
)


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="ch24_goal",
    instructions=InstructionConfig(
        required_keywords=["학습목표"],
        fail_on_violation=True,
    ),
    goal_alignment=GoalAlignmentConfig(alignment_threshold=0.75),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def goal_aligned_writer(question: str, ground_truth: str = "") -> str:
    """Gate A — 목표 달성 에이전트."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(0.2 + random.uniform(0, 0.3))
    return f"학습목표: {ground_truth}에 대한 내용입니다. {question}을 다음과 같이 설명합니다."


@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="ch24_loop",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    scope=ScopeConfig(allowed_tools=["search", "write", "revise"]),
)
def loop_safe_writer(question: str, ground_truth: str = "") -> str:
    """Gate B — 루프 안전 에이전트."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(0.2 + random.uniform(0, 0.3))
    return f"search → write → revise 순으로 처리: {question}"


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="ch24_sla",
    sla=SLAConfig(p95_ms=3_000),
    resource_budget=ResourceBudgetConfig(max_tokens=5_000, max_cost_usd=0.01),
)
def sla_bounded_agent(question: str, ground_truth: str = "") -> str:
    """Gate D — SLA 및 비용 경계 에이전트."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(0.1 + random.uniform(0, 0.2))
    return f"효율적으로 처리: {question}"


SECTION_QA = [
    ("FastAPI 기초 개요",   "FastAPI 핵심 개념 이해"),
    ("라우터와 엔드포인트",  "REST API 엔드포인트 설계"),
    ("의존성 주입 패턴",     "의존성 주입으로 재사용"),
]

print("  Gate A — 목표 달성 에이전트 3건:")
for q, gt in SECTION_QA:
    answer = goal_aligned_writer(q, ground_truth=gt)
    print(f"  ✅ {q[:22]:<22}  → '{answer[:45]}...'")

print("\n  Gate B — 루프 안전 에이전트 3건:")
for q, gt in SECTION_QA:
    answer = loop_safe_writer(q, ground_truth=gt)
    print(f"  ✅ {q[:22]:<22}  → '{answer[:45]}...'")

print("\n  Gate D — SLA 경계 에이전트 3건:")
for q, gt in SECTION_QA:
    answer = sla_bounded_agent(q, ground_truth=gt)
    print(f"  ✅ {q[:22]:<22}  → '{answer[:45]}...'")

# ===========================================================================
# 섹션 4: Gate 가중치 설계
# ===========================================================================
print("\n\n=== 섹션 4: Gate 가중치 설계 ===")

print("""
  기본 가중치(1.0)를 변경해야 하는 기준:

  ┌──────────────────────────────────────────────────────────┐
  │ 가중치 >1.0 (높임)                                       │
  │  · 사업적 손실이 직접 발생하는 실패 (E, F, D)            │
  │  · 탐지가 어려운 무음 실패 (F propagation, C repro)      │
  │                                                          │
  │ 가중치 <1.0 (낮춤)                                       │
  │  · 이미 외부 시스템이 커버하는 영역                      │
  │  · 초기 단계에서 아직 측정 데이터가 충분하지 않은 Gate   │
  └──────────────────────────────────────────────────────────┘

  Lecture_forge 가중치 결정:

  Gate A × 2.0  — 강의 품질이 핵심 상품 가치 (목표 달성 = 비즈니스 목표)
  Gate B × 1.5  — 루프 = 비용 폭발 위험
  Gate C × 1.0  — 기본값 유지 (기존 QualityEvaluator가 부분 커버)
  Gate D × 1.2  — $0.035 비용 목표 있음
  Gate E × 3.0  — 외부 PDF 입력 = 최고 위험 (프롬프트 인젝션)
  Gate F × 1.5  — audience_level 전파 무음 실패
  Gate G × 1.0  — 기본값 유지

  CI/CD에서 가중치 게이팅:
  $ agent-eval gate results/eval.json --group-weights A:2.0,E:3.0,F:1.5,D:1.2
""")

GATE_WEIGHTS = {"A": 2.0, "B": 1.5, "C": 1.0, "D": 1.2, "E": 3.0, "F": 1.5, "G": 1.0}
total_weight = sum(GATE_WEIGHTS.values())
print(f"  총 가중치 합: {total_weight:.1f}")
for gate, w in GATE_WEIGHTS.items():
    bar = "█" * int(w * 4)
    print(f"  Gate {gate}: {w:.1f}  {bar}")

# ===========================================================================
# 섹션 5: 측정 결과 확인
# ===========================================================================
print("\n\n=== 섹션 5: 측정 결과 확인 ===")

report = monitor.generate_report()
print(f"  TCR:        {_tcr(report):.1f}%")
print(f"  Accuracy:   {_acc(report):.1f}%")
print(f"  P95:        {_p95(report):.2f}초")
print(f"  총 태스크:   {report.total_tasks}건")

monitor.save_to_file("ch24_gate_mapping")
print("\n결과 저장 완료: results/ch24_gate_mapping.json")
print("확인: agent-eval dashboard results/")

print("""
=== Ch24 Gate 매핑 완료 요약 ===

  방법론:   실패 모드 3문항 → 범용 매핑 테이블 → Gate Config
  핵심 원칙: Gate부터 시작하지 않는다 — 실패 모드부터 시작한다
  Config 위치: @agent_eval 데코레이터 (PerformanceMonitor가 아님)

  Lecture_forge 매핑 결과:
    Gate E × 3.0  → PDF 외부 입력 최우선
    Gate A × 2.0  → 강의 품질 = 비즈니스 목표
    Gate B × 1.5  → 루프 = 비용 폭발
    Gate F × 1.5  → audience_level 전파 무음 실패

  다음 단계: Ch25 첫 번째 이식 — 30분 안에 첫 숫자 얻기
""")
