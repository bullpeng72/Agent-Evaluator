"""
ch18_cicd_gate.py — Harness CI/CD 검증 게이트
====================================================================
Book Chapter 18 — CI/CD 품질 게이팅

⚙️  자동화 전용 스크립트 — CI/CD 파이프라인에서 직접 호출하는 용도.
    사람이 읽는 교육용 예제는 ch03_harness_basics.py 를 참조하세요.

역할:
  - 7개 Gate 각 1개 Config씩 최소 검증 (총 7개 에이전트)
  - PASS/WARN/FAIL 판정 후 exit 0 또는 exit 1 반환
  - --strict 플래그: WARN도 FAIL로 처리 (배포 전 강화 검증)
  - JSON 한 줄 요약: CI 로그에서 파싱하기 쉬운 구조

08_harness_eval.py 와의 차이:
  ┌───────────────────────┬──────────────────┬─────────────────────┐
  │ 항목                   │ 08_harness_eval  │ ch18_cicd_gate      │
  ├───────────────────────┼──────────────────┼─────────────────────┤
  │ 목적                   │ 교육·시연        │ CI/CD 자동화         │
  │ Config 수              │ 33개 전부        │ 7개 (Gate당 1개)     │
  │ FAIL 역케이스          │ ✅ 포함          │ ❌ 없음 (PASS만)     │
  │ 실행 시간              │ ~15초            │ ~3초                │
  │ exit code              │ 없음             │ 0 (통과) / 1 (실패) │
  │ --strict               │ 없음             │ ✅ 지원              │
  └───────────────────────┴──────────────────┴─────────────────────┘

CI/CD 통합 예시:
  # GitHub Actions
  - name: Harness Gate
    run: |
      python Evaluator_Examples/ch18_cicd_gate.py
      python Evaluator_Examples/ch18_cicd_gate.py --strict   # WARN도 차단

  # agent-eval CLI (권장)
  agent-eval gate results/ch18_cicd_gate.json --tcr 80

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch18_cicd_gate.py
    python Evaluator_Examples/ch18_cicd_gate.py --strict

결과:
    results/ch18_cicd_gate.json
    → 전체 통합 예제: Evaluator_Examples/ch26_harness_full.py (Gate A–G 전체 연결)
"""

import json
import socket
import sys
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    setup_otel,
    # Group A
    InstructionConfig,
    GoalAlignmentConfig,
    # Group B
    LoopDetectionConfig,
    ScopeConfig,
    # Group C
    ReproducibilityConfig,
    RetryConsistencyConfig,
    # Group D
    SLAConfig,
    ResourceBudgetConfig,
    # Group E
    ThreatSeverityConfig,
    ComplianceConfig,
    # Group F
    ConsensusConfig,
    AgentRoleConfig,
    # Group G
    ExplainabilityConfig,
    ObservabilityConfig,
)
from agent_evaluator import agent_eval

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as _s:
        _s.settimeout(0.5)
        if _s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch18-cicd-gate")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ── 설정 ──────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
_STRICT_MODE  = "--strict" in sys.argv   # WARN도 실패로 처리

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    enable_transparency=True,           # 투명성 탭: 메트릭 계산 Traces 자동 생성
    use_korean_tokenizer=True,
)

# ── 그룹별 아이콘 ──────────────────────────────────────────────────────────────
_GROUP_ICON = {
    "A": "🎯", "B": "🛡", "C": "🔁", "D": "⚡",
    "E": "🔒", "F": "🤝", "G": "🔭",
}
_GROUP_NAME = {
    "A": "Goal Achievement",
    "B": "Behavioral Integrity",
    "C": "Reliability",
    "D": "Performance Contract",
    "E": "Security Boundary",
    "F": "Multi-Agent Coord.",
    "G": "Observability",
}


# ===========================================================================
# Group A — Goal Achievement
# ===========================================================================
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_a",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["answer", "source"],
        min_chars=10,
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"search": ["web_search"]},
        alignment_threshold=0.5,
    ),
)
def _group_a_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return json.dumps({"answer": question + "에 대한 검증 답변", "source": "내부 DB"})


# ===========================================================================
# Group B — Behavioral Integrity
# ===========================================================================
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="val_b",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=6, window_size=5),
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "report"],
        forbidden_tools=["delete_all", "drop_table"],
    ),
)
def _group_b_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"재무 리포트 조회: {question}"


# ===========================================================================
# Group C — Reliability
# ===========================================================================
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_c",
    reproducibility=ReproducibilityConfig(
        runs=3,
        reproducibility_threshold=0.85,
    ),
    retry_consistency=RetryConsistencyConfig(
        min_retry_count=2,
        penalize_degradation=True,
    ),
)
def _group_c_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"신뢰성 검증 응답: {question}"


# ===========================================================================
# Group D — Performance Contract
# ===========================================================================
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_d",
    sla=SLAConfig(p95_ms=3000),
    resource_budget=ResourceBudgetConfig(
        max_tokens=2000,
        max_cost_usd=0.05,
    ),
)
def _group_d_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    time.sleep(0.05)   # 현실적 지연 시뮬레이션
    return f"성능 검증 응답: {question}"


# ===========================================================================
# Group E — Security Boundary
# ===========================================================================
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_e",
    threat_severity=ThreatSeverityConfig(
        fail_score=7.0,
        fail_on_critical=True,
    ),
    compliance=ComplianceConfig(
        compliance_framework="gdpr",
        require_data_minimization=True,
    ),
)
def _group_e_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"보안 검증 응답: {question}"


# ===========================================================================
# Group F — Multi-Agent Coordination
# ===========================================================================
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="val_f",
    consensus=ConsensusConfig(
        consensus_method="majority",
        similarity_threshold=0.7,
    ),
    agent_role=AgentRoleConfig(
        role_name="coordinator",
        allowed_tools=["search", "summarize"],
    ),
)
def _group_f_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"다중 에이전트 협업 결과: {question}"


# ===========================================================================
# Group G — Observability
# ===========================================================================
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_g",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=20,
    ),
    observability=ObservabilityConfig(
        check_trace_continuity=True,
        min_coverage=0.95,
    ),
)
def _group_g_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    # ExplainabilityConfig는 reasoning_markers("왜냐하면", "따라서" 등) 존재 여부를 검사한다.
    # ObservabilityConfig는 required_span_attributes 커버리지(task_id·task_type·execution_time)를 검사한다.
    return (
        f"검증 응답: 질문 '{question}'을 분석했습니다. "
        "왜냐하면 이 항목이 핵심 관측성 기준과 직결되기 때문입니다. "
        "따라서 내부 지식베이스와 추적 메타데이터를 활용하여 GDPR 원칙에 맞게 응답합니다."
    )


# ===========================================================================
# 실행 — 그룹별 2회 호출 (최소 샘플)
# ===========================================================================
def _run_validation() -> None:
    test_cases = [
        ("분기 재무 실적을 JSON으로 요약해줘", "Q3 매출 15% 성장"),
        ("고객 민감 정보 접근 정책을 확인해줘", "GDPR 준수"),
    ]
    fns = [
        _group_a_agent,
        _group_b_agent,
        _group_c_agent,
        _group_d_agent,
        _group_e_agent,
        _group_f_agent,
        _group_g_agent,
    ]
    for fn in fns:
        for q, gt in test_cases:
            fn(q, ground_truth=gt)


# ===========================================================================
# 게이트 평가 및 종료 코드
# ===========================================================================
def _print_gate(harness: dict) -> bool:
    """PASS/WARN/FAIL 요약 출력 후 실패 여부 반환.

    이 함수는 이미 계산된 고정 기준(0.7/0.5) status를 그대로 읽어 출력만 한다 —
    Gate별로 다른 커스텀 임계값을 직접 비교·판정해야 한다면(예: Security는 0.95,
    나머지는 0.7), 이 로직을 손수 구현하지 말고 `HarnessEvaluationGate` 또는
    `gates/base.py::evaluate_gate_scores()`를 쓸 것 — 세 개의 공식 판정 경로
    (`HarnessEvaluationGate.evaluate()`/`QuickEval.gate()`/`cli/gate.py
    --gate-thresholds`)가 공유하는 동일 정본 함수다.
    """
    overall = harness.get("overall", {})
    gate    = (overall.get("gate") or "unknown").upper()
    score   = overall.get("score")
    pct     = f"{score*100:.1f}%" if score is not None else "n/a"

    print("\n" + "═" * 60)
    print(f"  🏁 HARNESS GATE  ·  전체: {gate}  ({pct})")
    print("─" * 60)

    failed_groups: list = []
    warned_groups: list = []

    for gk in "ABCDEFG":
        gv = harness.get(gk)
        if gv is None:
            continue
        g_gate  = (gv.get("gate") or "unknown").upper()
        g_score = gv.get("score")
        g_pct   = f"{g_score*100:.1f}%" if g_score is not None else " n/a"
        icon    = _GROUP_ICON.get(gk, "·")
        name    = _GROUP_NAME.get(gk, gk)
        badge   = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}.get(g_gate, "❓")
        print(f"  {badge} Group {gk} {icon} {name:<28} {g_pct:>6}  {g_gate}")
        if g_gate == "FAIL":
            failed_groups.append(gk)
        elif g_gate == "WARN":
            warned_groups.append(gk)

    print("═" * 60)

    if failed_groups:
        print(f"  ❌ FAIL 그룹: {', '.join(failed_groups)}")
    if warned_groups:
        print(f"  ⚠️  WARN 그룹: {', '.join(warned_groups)}")

    # strict 모드: WARN도 실패
    if _STRICT_MODE:
        return bool(failed_groups or warned_groups)
    return bool(failed_groups)


if __name__ == "__main__":
    print("Harness CI/CD 검증 시작...")
    _run_validation()

    monitor.save_to_file("ch18_cicd_gate")
    print(f"  결과 저장: {_OUTPUT_DIR}/ch18_cicd_gate.json")

    report_dict = monitor.generate_report().to_dict()
    harness = report_dict.get("extra_metrics", {}).get("harness_groups", {})

    if not harness:
        print("  ⚠️  harness_groups 데이터 없음 — 평가 설정 확인 필요")
        sys.exit(0)

    print()
    print("  ── CI/CD 모드: PASS/FAIL 판정 후 exit code 반환 ─────────────────")

    should_fail = _print_gate(harness)

    if should_fail:
        mode_label = " (strict)" if _STRICT_MODE else ""
        print(f"\n  Harness Gate 실패{mode_label} — exit 1")
        sys.exit(1)
    else:
        print("\n  Harness Gate 통과 — exit 0")
        sys.exit(0)

# ── 전체 시연은 ch26_harness_full.py 참조 ───────────────────────────────────
# 각 Config의 PASS/FAIL 비교, 33개 Config 전체 시연, 역케이스(나쁜 에이전트)는
# python Evaluator_Examples/ch26_harness_full.py 를 실행하세요.
