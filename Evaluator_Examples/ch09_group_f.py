"""
ch09_group_f.py — Gate F: Multi-Agent Coordination
===================================================
Book Chapter 09 — Gate F: Multi-Agent Coordination

ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig — 4개 Config 전체 시연.

ConsensusConfig는 3개 서브에이전트 응답을 내부에서 시뮬레이션한 뒤
EvalMetadata(extra={"consensus": {...}}) 로 합의 점수를 직접 주입한다.

역케이스(_monitor_f_fail)로 Gate F FAIL 유도 비교도 포함한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch09_group_f.py

결과:
    results/ch09_group_f.json  (+ .html)
    → 전체 33개 Config 통합 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import socket
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    setup_otel,
    agent_eval,
    EvalMetadata,
    # Gate F — Multi-Agent Coordination
    ConsensusConfig,
    PropagationConfig,
    AgentRoleConfig,
    ConflictResolutionConfig,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch09-group-f")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Gate F 전용 monitor
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=False,
    enable_security_metrics=False,
    enable_transparency=True,
    use_korean_tokenizer=True,
)

# ===========================================================================
# 섹션 6: Gate F — Multi-Agent Coordination
# ===========================================================================
print("\n=== 섹션 6: Gate F — Multi-Agent Coordination ===")


# ── 갭 보완: ConsensusConfig 실계산 ───────────────────────────────────────────
# ConsensusConfig는 task.extra["consensus"]["consensus_score"] 에서 점수를 읽는다.
# @agent_eval은 consensus_responses 파라미터를 직접 노출하지 않으므로,
# 함수 내부에서 3개 서브에이전트를 시뮬레이션한 뒤
# EvalMetadata(extra={"consensus": {...}}) 로 미리 계산한 점수를 주입한다.

def _tok_sim(a: str, b: str) -> float:
    """두 문자열의 토큰 집합 Jaccard 유사도."""
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return len(sa & sb) / max(len(sa | sb), 1)


@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_consensus",
    consensus=ConsensusConfig(
        consensus_method="majority",
        similarity_threshold=0.7,
    ),
)
def consensus_agent(question: str, ground_truth: str = "") -> tuple:
    """멀티에이전트 합의 에이전트 — 3개 서브에이전트 응답 수집 후 합의 점수 주입."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    # 3개 독립 서브에이전트 응답 시뮬레이션
    resp_a = f"[에이전트A] {question}: 현재 80% 진행, 일정 정상 궤도입니다."
    resp_b = f"[에이전트B] {question}: 진행률 78%, 일정 준수 중이며 정상 진행입니다."
    resp_c = f"[에이전트C] {question}: 현재 80% 달성, 다음 마일스톤 도달 가능합니다."

    # 쌍별 유사도 계산 (sim_threshold=0.7 기준)
    pairs = [
        ("A", "B", resp_a, resp_b),
        ("A", "C", resp_a, resp_c),
        ("B", "C", resp_b, resp_c),
    ]
    agreement_pairs = []
    agreed_count = 0
    for name_i, name_j, ri, rj in pairs:
        sim = round(_tok_sim(ri, rj), 4)
        agreed = sim >= 0.7
        agreement_pairs.append({"agent_a": name_i, "agent_b": name_j,
                                 "similarity": sim, "agreed": agreed})
        if agreed:
            agreed_count += 1

    consensus_score = agreed_count / len(pairs)

    return resp_a, EvalMetadata(extra={
        "consensus": {
            "consensus_score": round(consensus_score, 4),
            "agreement_pairs": agreement_pairs,
            "dissenting_agents": [],
            "selected_response": resp_a,
            "method": "majority",
        }
    })


@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_propagation",
    propagation=PropagationConfig(
        key_facts=["project_id", "deadline"],
        check_in_response=True,
        similarity_threshold=0.6,
    ),
)
def propagation_agent(question: str, ground_truth: str = "") -> str:
    """멀티에이전트 정보 전파 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"project_id: PROJ-001, deadline: 2026-06-30 — {question} 처리 완료"


@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_role",
    agent_role=AgentRoleConfig(
        role_name="summarizer",
        allowed_tools=["search", "summarize"],
        forbidden_tools=["delete", "write_db"],
        role_violation_penalty=0.3,
    ),
)
def role_bounded_agent(question: str, ground_truth: str = "") -> str:
    """역할 준수 에이전트 (mock) — summarizer 역할."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"[summarizer] 요약 수행: {question}에 대한 핵심 내용 정리 완료"


@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_conflict",
    conflict_resolution=ConflictResolutionConfig(
        unresolved_penalty=0.3,
        check_resolution_quality=True,
    ),
)
def conflict_resolver_agent(question: str, ground_truth: str = "") -> str:
    """충돌 해결 에이전트 (mock)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    if "disagree" in question.lower() or "충돌" in question:
        return f"합의 도달: 에이전트 간 의견 충돌을 resolved하고 최종 결정을 내렸습니다."
    return f"일치된 응답: {question}"


# 섹션 6 실행
COORDINATION_CASES = [
    ("프로젝트 진행 상황을 보고해줘", "보고 완료"),
    ("deadline 내 작업을 완료해줘", "완료"),
    ("결과를 요약해줘", "요약 완료"),
]

for q, gt in COORDINATION_CASES:
    consensus_agent(q, ground_truth=gt)      # 3-에이전트 합의 + 점수 주입
    propagation_agent(q, ground_truth=gt)
    role_bounded_agent(q, ground_truth=gt)
    conflict_resolver_agent(q, ground_truth=gt)

# 추가 충돌 시나리오
conflict_resolver_agent("에이전트 간 disagree 발생 — 충돌 해결 필요", ground_truth="합의")

print(f"  섹션 6 완료: {len(COORDINATION_CASES) * 4 + 1}건 기록")

# ── 역케이스: Gate F FAIL 유도 (PropagationConfig) ───────────────────────────
_monitor_f_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

@agent_eval(
    _monitor_f_fail, task_type="multi_agent", task_id_prefix="f_fail_propagation",
    propagation=PropagationConfig(
        key_facts=["project_id: PRJ-2024", "deadline: 2026-06-30", "budget: 50M"],
        check_in_response=True,
        similarity_threshold=0.7,
    ),
)
def _f_fail_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"작업 완료했습니다. {question}"  # key_facts 전혀 미언급

for _q in ["프로젝트 현황을 보고해줘", "진행 상태를 알려줘", "다음 에이전트에게 전달해줘"]:
    _f_fail_agent(_q)

_r = _monitor_f_fail.generate_report().to_dict()
_s = (_r.get("extra_metrics") or {}).get("harness_groups", {}).get("F", {})
_pct = f"{_s['score']*100:.1f}%" if _s.get("score") is not None else "n/a"
print(f"  ▶ 역케이스 Gate F: {_pct}  {'FAIL 확인 ✓' if (_s.get('status','').upper()=='FAIL') else '예상과 다름'}")

# Gate F 점수 출력
_report = monitor.generate_report().to_dict()
_harness = (_report.get("extra_metrics") or {}).get("harness_groups", {})
_gd = _harness.get("F", {})
_score = _gd.get("score")
_status = _gd.get("status", "n/a")
if _score is not None:
    _bar = "█" * int(_score * 10) + "░" * (10 - int(_score * 10))
    print(f"\n  Gate F [Multi-Agent Coordination] {_bar} {_score:.3f} ({_status})")

monitor.save_to_file("ch09_group_f")
print("\n결과 저장 완료: results/ch09_group_f.json")
print("확인: agent-eval dashboard --results results/")
