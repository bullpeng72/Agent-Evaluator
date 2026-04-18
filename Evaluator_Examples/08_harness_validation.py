"""
08_harness_validation.py — Harness CI/CD 검증 스크립트
====================================================================
7개 Harness 그룹(A–G)을 최소 커버리지로 검증하고 게이트 결과를
exit code로 반환한다.  CI/CD 파이프라인에서 직접 실행 가능.

  Group A — Goal Achievement      (InstructionConfig, GoalAlignmentConfig)
  Group B — Behavioral Integrity  (LoopDetectionConfig, ScopeConfig)
  Group C — Reliability           (ReproducibilityConfig, RetryConsistencyConfig)
  Group D — Performance Contract  (SLAConfig, ResourceBudgetConfig)
  Group E — Security Boundary     (ThreatSeverityConfig, ComplianceConfig)
  Group F — Multi-Agent Coord.    (ConsensusConfig, AgentRoleConfig)
  Group G — Observability         (ExplainabilityConfig, ObservabilityConfig)

종료 코드:
  0 — 모든 그룹 PASS (또는 WARN)
  1 — 한 개 이상의 그룹 FAIL

의존성:
  pip install agent-evaluator      (외부 extras 불필요)

실행:
  python Evaluator_Examples/08_harness_validation.py
  python Evaluator_Examples/08_harness_validation.py --strict   # WARN도 실패 처리

결과:
  results/harness_validation.json  (+  .html)
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
from agent_evaluator.decorators import agent_eval

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as _s:
        _s.settimeout(0.5)
        if _s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="08-harness-validation")
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
    return json.dumps({"answer": question + "에 대한 검증 답변", "source": "내부 DB"})


# ===========================================================================
# Group B — Behavioral Integrity
# ===========================================================================
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="val_b",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, window_size=5),
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "report"],
        forbidden_tools=["delete_all", "drop_table"],
    ),
)
def _group_b_agent(question: str, ground_truth: str = "") -> str:
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
    return (
        "검증 응답: 이 답변은 내부 지식베이스를 기반으로 작성되었습니다. "
        f"질문 '{question}'에 대해 관측성 추적을 포함한 응답을 반환합니다."
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
    """PASS/WARN/FAIL 요약 출력 후 실패 여부 반환."""
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

    monitor.save_to_file("harness_validation")
    print(f"  결과 저장: {_OUTPUT_DIR}/harness_validation.json")

    report_dict = monitor.generate_report().to_dict()
    harness = report_dict.get("extra_metrics", {}).get("harness_groups", {})

    if not harness:
        print("  ⚠️  harness_groups 데이터 없음 — 평가 설정 확인 필요")
        sys.exit(0)

    should_fail = _print_gate(harness)

    if should_fail:
        mode_label = " (strict)" if _STRICT_MODE else ""
        print(f"\n  Harness Gate 실패{mode_label} — exit 1")
        sys.exit(1)
    else:
        print("\n  Harness Gate 통과 — exit 0")
        sys.exit(0)
