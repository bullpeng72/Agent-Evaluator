"""
ch03_harness_basics.py — Harness Engineering 기초 (Gate A–G 개요)
=================================================================
Book Chapter 03 — Harness Engineering 기초

7개 Gate의 동작을 한 파일에서 빠르게 확인한다.
각 Gate당 1개 에이전트로 최소 시연 → Gate별 점수 출력.

  Gate A — Goal Achievement   : InstructionConfig
  Gate B — Behavioral Integrity: LoopDetectionConfig
  Gate C — Reliability         : FaultToleranceConfig
  Gate D — Performance Contract: SLAConfig
  Gate E — Security Boundary   : ComplianceConfig
  Gate F — Multi-Agent         : PropagationConfig
  Gate G — Observability       : ExplainabilityConfig

완전한 Gate별 예제는 ch04_group_a.py ~ ch10_group_g.py 참조.
버전 비교 시나리오: ch20_deployment.py

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch03_harness_basics.py

결과:
    results/ch03_harness_basics.json  (+ .html)
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import json
import random
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor, setup_otel,
    InstructionConfig,
    LoopDetectionConfig,
    FaultToleranceConfig,
    SLAConfig,
    ComplianceConfig,
    PropagationConfig,
    ExplainabilityConfig,
)
from agent_evaluator.decorators import agent_eval, RetryConfig, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch03-harness-basics")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    enable_transparency=True,
)

print("\n=== Ch03 Harness Gate A–G 기초 개요 ===")

# Gate A — Goal Achievement
@agent_eval(monitor, task_type="qa", task_id_prefix="a_basic",
    instructions=InstructionConfig(required_keywords=["result", "confidence"], min_chars=20))
def gate_a_agent(question: str, ground_truth: str = "") -> str:
    return json.dumps({"result": f"{question}에 대한 답변", "confidence": 0.92})

# Gate B — Behavioral Integrity
@agent_eval(monitor, task_type="tool_use", task_id_prefix="b_basic",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=2, window_size=5))
def gate_b_agent(question: str, ground_truth: str = "") -> str:
    return f"search → analyze → summarize 순서로 처리: {question}"

# Gate C — Reliability
_c_count = {"n": 0}
@agent_eval(monitor, task_type="tool_use", task_id_prefix="c_basic",
    fault_tolerance=FaultToleranceConfig(check_fallback_attempts=True, partial_success_threshold=0.5),
    retry=RetryConfig(max=2, on=(RuntimeError,), delay=0.0))
def gate_c_agent(question: str, ground_truth: str = "") -> str:
    _c_count["n"] += 1
    if _c_count["n"] % 3 == 1:
        return f"부분 완료(폴백): 캐시 데이터로 응답합니다. {question}"
    return f"정상 처리: {question}"

# Gate D — Performance Contract
@agent_eval(monitor, task_type="qa", task_id_prefix="d_basic",
    sla=SLAConfig(p95_ms=2000, p99_ms=5000))
def gate_d_agent(question: str, ground_truth: str = "") -> tuple:
    t0 = time.perf_counter()
    time.sleep(random.uniform(0.05, 0.2))
    ttft = (time.perf_counter() - t0) * 1000
    return f"SLA 준수 응답: {question}", EvalMetadata(
        extra={"ttft_ms": round(ttft, 1)},
        tokens_used={"input": 80, "output": 150, "total": 230},
    )

# Gate E — Security Boundary
@agent_eval(monitor, task_type="qa", task_id_prefix="e_basic",
    compliance=ComplianceConfig(pii_categories=["email", "phone"], compliance_framework="gdpr"))
def gate_e_agent(question: str, ground_truth: str = "") -> str:
    return f"GDPR 준수 처리: {question}".replace("@", "[마스킹]")

# Gate F — Multi-Agent
@agent_eval(monitor, task_type="multi_agent", task_id_prefix="f_basic",
    propagation=PropagationConfig(key_facts=["project_id", "deadline"], check_in_response=True))
def gate_f_agent(question: str, ground_truth: str = "") -> str:
    return f"project_id: PROJ-001, deadline: 2026-06-30 — {question}"

# Gate G — Observability
@agent_eval(monitor, task_type="reasoning", task_id_prefix="g_basic",
    explainability=ExplainabilityConfig(require_reasoning=True, min_reasoning_length=50,
                                         reasoning_markers=["왜냐하면", "따라서", "때문에"]))
def gate_g_agent(question: str, ground_truth: str = "") -> str:
    return (f"[추론] {question}: 왜냐하면 핵심 패턴이 발견되었기 때문입니다. "
            f"따라서 적절한 조치를 취했습니다.")

# 실행
CASES = [
    ("데이터를 분석해줘", "분석 완료"),
    ("보고서를 작성해줘", "작성 완료"),
    ("현황을 파악해줘",   "파악 완료"),
]

for q, gt in CASES:
    gate_a_agent(q, ground_truth=gt)
    gate_b_agent(q, ground_truth=gt)
    try:
        gate_c_agent(q, ground_truth=gt)
    except Exception:
        pass
    gate_d_agent(q, ground_truth=gt)
    gate_e_agent(q, ground_truth=gt)
    gate_f_agent(q, ground_truth=gt)
    gate_g_agent(q, ground_truth=gt)

# Harness Gate 점수 출력
print("\n=== Harness Gate 점수 ===")
report = monitor.generate_report()
harness = (report.to_dict().get("extra_metrics") or {}).get("harness_groups", {})
labels = {"A": "Goal Achievement", "B": "Behavioral Integrity", "C": "Reliability",
          "D": "Performance Contract", "E": "Security Boundary",
          "F": "Multi-Agent Coordination", "G": "Observability"}
for gk, label in labels.items():
    gd = harness.get(gk, {})
    score = gd.get("score")
    status = gd.get("status", "n/a")
    if score is not None:
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"  Gate {gk} [{label:<28s}] {bar} {score:.3f} ({status})")
    else:
        print(f"  Gate {gk} [{label:<28s}] --- (데이터 없음)")

monitor.save_to_file("ch03_harness_basics")
print("\n결과 저장 완료: results/ch03_harness_basics.json")
print("확인: agent-eval dashboard --results results/")
