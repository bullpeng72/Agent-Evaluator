"""
ch14_thresholds.py — 임계값 설정과 품질 기준 수립
==================================================
Book Chapter 14 — 임계값 설정과 품질 기준 수립

에이전트 유형별 KPI 임계값을 설정하고, 데이터 기반으로 자동 생성하며,
HarnessEvaluationGate로 배포 판정을 자동화하는 패턴을 시연한다.

  섹션 1: generate_gate_config() — 현재 결과 기반 임계값 자동 생성
  섹션 2: HarnessEvaluationGate — Gate별 임계값 선언 및 pass/fail 시뮬레이션
  섹션 3: SimpleTaskAlertRule — 임계값 기반 실시간 알림 연동
  섹션 4: 에이전트 유형별 임계값 프로파일 비교

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch14_thresholds.py

결과:
    results/ch14_thresholds.json  (+ .html)
    results/ch14_gate_config.json  (자동 생성 임계값)
"""

import socket
from pathlib import Path

from agent_evaluator import (
    QuickEval,
    PerformanceMonitor,
    SimpleTaskAlertRule,
    create_taskresult,
    setup_otel,
    SLAConfig,
    ResourceBudgetConfig,
    InstructionConfig,
    ThreatSeverityConfig,
    ComplianceConfig,
)
from agent_evaluator import agent_eval

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch14-thresholds")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 섹션 1: generate_gate_config() — 현재 결과 기반 임계값 자동 생성
# ===========================================================================
print("\n=== 섹션 1: generate_gate_config() — 데이터 기반 임계값 자동 생성 ===")

eval_qe = QuickEval(_OUTPUT_DIR)

# 시뮬레이션용 샘플 에이전트 (실제 환경에서는 실제 에이전트 함수로 교체)
@eval_qe.qa
def sample_qa_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    import random
    answers = {
        "한국의 수도?": "서울입니다.",
        "파이썬 창시자?": "귀도 반 로섬입니다.",
        "지구 자전 주기?": "약 24시간입니다.",
        "수소 원소 기호?": "H입니다.",
        "빛의 속도?": "약 30만 km/s입니다.",
    }
    base = answers.get(question, "모르겠습니다.")
    if random.random() < 0.1:
        return "잘 모르겠습니다."
    return base

CALIBRATION_DATASET = [
    ("한국의 수도?",    "서울"),
    ("파이썬 창시자?",  "귀도 반 로섬"),
    ("지구 자전 주기?", "24시간"),
    ("수소 원소 기호?", "H"),
    ("빛의 속도?",      "30만 km/s"),
    ("한국의 수도?",    "서울"),
    ("파이썬 창시자?",  "귀도 반 로섬"),
    ("지구 자전 주기?", "24시간"),
    ("수소 원소 기호?", "H"),
    ("빛의 속도?",      "30만 km/s"),
]

print(f"  캘리브레이션 케이스 {len(CALIBRATION_DATASET)}건 실행 중...")
for q, gt in CALIBRATION_DATASET:
    sample_qa_agent(q, ground_truth=gt)

# 현재 성능 기반 임계값 자동 생성 (95% 수준)
gate_config_path = str(_PROJECT_ROOT / "results" / "ch14_gate_config.json")
config = eval_qe.generate_gate_config(gate_config_path)
print(f"\n  생성된 임계값 (95% 수준 기반):")
for k, v in config.items():
    if k not in ("generated_at", "based_on_tasks"):
        print(f"    {k:20s}: {v}")
print(f"  기준 샘플 수: {config.get('based_on_tasks', '?')}건")
print(f"  저장 위치:   {gate_config_path}")
print(f"\n  CI/CD 활용:")
print(f"    agent-eval gate results/eval.json --tcr {config.get('tcr', 85):.1f} --accuracy {config.get('accuracy', 70):.1f}")

# ===========================================================================
# 섹션 2: HarnessEvaluationGate — Gate별 임계값 선언 및 pass/fail 시뮬레이션
# ===========================================================================
print("\n=== 섹션 2: HarnessEvaluationGate — Gate별 임계값 선언 및 판정 ===")

# ---- 2-A: 정상 에이전트 시나리오 (PASS 예상) ----
monitor_pass = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

sla_cfg = SLAConfig(
    p95_ms=5000,
    max_cost_per_task=0.05,
)
budget_cfg = ResourceBudgetConfig(
    max_tokens=2000,
    max_cost_usd=10.0,
)
instruction_cfg = InstructionConfig(
    required_keywords=["완료"],
    fail_on_violation=False,
)

@agent_eval(monitor_pass, task_type="qa",
            sla=sla_cfg, resource_budget=budget_cfg, instructions=instruction_cfg)
def good_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"처리 완료: {question}"

PASS_CASES = [
    ("서울의 특징?", "수도"),
    ("파이썬이란?",  "언어"),
    ("HTTP란?",      "프로토콜"),
]
for q, gt in PASS_CASES:
    good_agent(q, ground_truth=gt)

report_pass = monitor_pass.generate_report()
d_pass = report_pass.to_dict()
harness_pass = d_pass.get("extra_metrics", {}).get("harness_groups", {})
print(f"\n  [정상 에이전트] Gate 판정:")
for g in ["A", "D"]:
    gd = harness_pass.get(g, {})
    if isinstance(gd, dict) and gd.get("score") is not None:
        print(f"    Gate {g}: score={gd['score']:.3f} → {gd.get('status', 'n/a')}")

# ---- 2-B: 엄격한 임계값 시나리오 (FAIL 유도) ----
monitor_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

strict_sla = SLAConfig(
    p95_ms=100,           # 100ms — 매우 엄격
    max_cost_per_task=0.00001,
)
strict_budget = ResourceBudgetConfig(
    max_tokens=5,
    max_cost_usd=0.0001,
)

@agent_eval(monitor_fail, task_type="qa",
            sla=strict_sla, resource_budget=strict_budget)
def slow_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    import time
    time.sleep(0.01)
    return f"느린 응답: {question}"

for q, gt in PASS_CASES:
    slow_agent(q, ground_truth=gt)

report_fail = monitor_fail.generate_report()
d_fail = report_fail.to_dict()
harness_fail = d_fail.get("extra_metrics", {}).get("harness_groups", {})
print(f"\n  [엄격 임계값] Gate 판정:")
for g in ["A", "D"]:
    gd = harness_fail.get(g, {})
    if isinstance(gd, dict) and gd.get("score") is not None:
        print(f"    Gate {g}: score={gd['score']:.3f} → {gd.get('status', 'n/a')}")

# ===========================================================================
# 섹션 3: SimpleTaskAlertRule — 임계값 기반 실시간 알림 연동
# ===========================================================================
print("\n=== 섹션 3: SimpleTaskAlertRule — 임계값 기반 알림 ===")

alert_log = []

latency_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 2.0,
    handler=lambda msg, tr: alert_log.append(
        {"rule": "slow_response", "task_id": tr.task_id, "latency": tr.execution_time}
    ),
    severity="warning",
    cooldown=0,
)
accuracy_alert = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: (tr.accuracy_score or 0) < 0.3,
    handler=lambda msg, tr: alert_log.append(
        {"rule": "low_accuracy", "task_id": tr.task_id, "accuracy": tr.accuracy_score}
    ),
    severity="error",
    cooldown=0,
)

monitor_alert = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

@agent_eval(monitor_alert, task_type="qa",
            alert_rules=[latency_alert, accuracy_alert])
def monitored_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    import time, random
    if random.random() < 0.3:
        time.sleep(2.5)
        return "느린 응답"
    if random.random() < 0.2:
        return "틀린 답변 xyz"
    return f"정확한 답변: {question}"

ALERT_CASES = [
    ("질문 A", "답변 A"),
    ("질문 B", "답변 B"),
    ("질문 C", "답변 C"),
    ("질문 D", "답변 D"),
    ("질문 E", "답변 E"),
]
for q, gt in ALERT_CASES:
    monitored_agent(q, ground_truth=gt)

print(f"  발생한 알림: {len(alert_log)}건")
for a in alert_log[:3]:
    print(f"    [{a['rule']}] task={a['task_id']}")

# ===========================================================================
# 섹션 4: 에이전트 유형별 임계값 프로파일
# ===========================================================================
print("\n=== 섹션 4: 에이전트 유형별 임계값 프로파일 ===")

THRESHOLD_PROFILES = {
    "QA 챗봇": {
        "tcr": 85, "accuracy": 70, "quality": 3.5,
        "p95_ms": 5000, "hallucination_rate": 5,
    },
    "RAG 검색": {
        "tcr": 88, "accuracy": 75, "quality": 3.8,
        "p95_ms": 4000, "hallucination_rate": 3,
    },
    "Tool Use": {
        "tcr": 80, "accuracy": 65, "quality": 3.2,
        "p95_ms": 10000, "hallucination_rate": 8,
    },
    "Security Agent": {
        "tcr": 95, "accuracy": 80, "quality": 4.0,
        "p95_ms": 3000, "hallucination_rate": 1,
    },
    "Conversation": {
        "tcr": 82, "accuracy": 68, "quality": 3.5,
        "p95_ms": 6000, "hallucination_rate": 5,
    },
}

print(f"  {'에이전트 유형':<16} {'TCR':>6} {'Acc':>6} {'Q':>5} {'P95':>8} {'Hallu':>6}")
print(f"  {'-'*55}")
for agent_type, thresholds in THRESHOLD_PROFILES.items():
    print(
        f"  {agent_type:<16} "
        f"{thresholds['tcr']:>5}% "
        f"{thresholds['accuracy']:>5}% "
        f"{thresholds['quality']:>5.1f} "
        f"{thresholds['p95_ms']:>6}ms "
        f"{thresholds['hallucination_rate']:>5}%"
    )

print(f"\n  보안 에이전트는 TCR 95%, Accuracy 80% — 가장 엄격한 기준 적용")
print(f"  Tool Use 에이전트는 P95 10,000ms 허용 — 도구 실행 지연 감안")

# ===========================================================================
# 최종 저장
# ===========================================================================
monitor_alert.save_to_file("ch14_thresholds")
print("\n결과 저장 완료: results/ch14_thresholds.json")
print("확인: agent-eval dashboard --results results/")
