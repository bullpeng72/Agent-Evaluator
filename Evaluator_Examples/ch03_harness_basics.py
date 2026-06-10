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
    agent_eval, RetryConfig, EvalMetadata,
)

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
    use_korean_tokenizer=True,
)

print("\n=== Ch03 Harness Gate A–G 기초 개요 ===")

# Gate A — Goal Achievement
@agent_eval(monitor, task_type="qa", task_id_prefix="a_basic",
    instructions=InstructionConfig(required_keywords=["result", "confidence"], min_chars=20))
def gate_a_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return json.dumps({"result": f"{question}에 대한 답변", "confidence": 0.92})

# Gate B — Behavioral Integrity
@agent_eval(monitor, task_type="tool_use", task_id_prefix="b_basic",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=2, window_size=5))
def gate_b_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"search → analyze → summarize 순서로 처리: {question}"

# Gate C — Reliability
_c_count = {"n": 0}
@agent_eval(monitor, task_type="tool_use", task_id_prefix="c_basic",
    fault_tolerance=FaultToleranceConfig(check_fallback_attempts=True, partial_success_threshold=0.5),
    retry=RetryConfig(max=2, on=(RuntimeError,), delay=0.0))
def gate_c_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    _c_count["n"] += 1
    if _c_count["n"] % 3 == 1:
        return f"부분 완료(폴백): 캐시 데이터로 응답합니다. {question}"
    return f"정상 처리: {question}"

# Gate D — Performance Contract
@agent_eval(monitor, task_type="qa", task_id_prefix="d_basic",
    sla=SLAConfig(p95_ms=2000, p99_ms=5000))
def gate_d_agent(question: str, ground_truth: str = "") -> tuple:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"GDPR 준수 처리: {question}".replace("@", "[마스킹]")

# Gate F — Multi-Agent
@agent_eval(monitor, task_type="multi_agent", task_id_prefix="f_basic",
    propagation=PropagationConfig(key_facts=["project_id", "deadline"], check_in_response=True))
def gate_f_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"project_id: PROJ-001, deadline: 2026-06-30 — {question}"

# Gate G — Observability
@agent_eval(monitor, task_type="reasoning", task_id_prefix="g_basic",
    explainability=ExplainabilityConfig(require_reasoning=True, min_reasoning_length=50,
                                         reasoning_markers=["왜냐하면", "따라서", "때문에"]))
def gate_g_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return (f"[추론] {question}: 왜냐하면 핵심 패턴이 발견되었기 때문입니다. "
            f"따라서 적절한 조치를 취했습니다.")

def print_harness_console_report(report):
    """콘솔에 Gate 점수와 주요 지표를 예쁘게 시각화하여 출력한다."""
    data = report.to_dict()
    harness = (data.get("extra_metrics") or {}).get("harness_groups", {})
    
    print("\n" + "═" * 68)
    print(f"  🏁 HARNESS GATE 종합 판정 리포트")
    print("─" * 68)
    print(f"  {'Gate':<4} {'영역 (Domain)':<28} {'상태':^6} {'점수':>8}   {'비주얼'}")
    print(f"  {'-'*4} {'-'*28} {'-'*6} {'-'*8}   {'-'*15}")
    
    icons = {"A":"🎯","B":"🛡","C":"🔁","D":"⚡","E":"🔒","F":"🤝","G":"🔭"}
    names = {"A":"Goal Achievement", "B":"Behavioral Integrity", "C":"Reliability",
             "D":"Performance Contract", "E":"Security Boundary", 
             "F":"Multi-Agent Coord.", "G":"Observability"}
    
    for gk in "ABCDEFG":
        gd = harness.get(gk, {})
        score = gd.get("score")
        gate  = (gd.get("gate") or "n/a").upper()
        name  = names.get(gk, gk)
        icon  = icons.get(gk, "·")
        
        if score is not None:
            status_icon = "✅" if gate == "PASS" else ("⚠️ " if gate == "WARN" else "❌")
            bar_len = int(score * 15)
            bar = "█" * bar_len + "░" * (15 - bar_len)
            print(f"  {gk}    {icon} {name:<26} {status_icon}{gate:^6} {score:>8.3f}   {bar}")
    
    # 요약 지표 추가
    tcr_val = (data.get("accuracy_metrics") or {}).get("tcr", {}).get("tcr", 0.0)
    acc_val = (data.get("accuracy_metrics") or {}).get("accuracy_scores", {}).get("overall_accuracy", 0.0)
    p95_val = (data.get("efficiency_metrics") or {}).get("latency", {}).get("p95", 0.0)
    print("─" * 68)
    print(f"  [요약] TCR: {tcr_val:>5.1f}%  |  "
          f"Acc: {acc_val:>5.1f}%  |  "
          f"P95: {p95_val:>5.3f}s")
    print("═" * 68 + "\n")

# 실행 부분
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
report = monitor.generate_report()
print_harness_console_report(report)

monitor.save_to_file("ch03_harness_basics")
print(f"결과 저장 완료: results/ch03_harness_basics.json")
print("확인: agent-eval dashboard results/")
