"""
ch20_deployment.py — 에이전트 버전 비교 (v1 vs v2)
====================================================================
Book Chapter 20 — 프로덕션 배포전략

Harness Engineering의 실무 핵심 시나리오:
"v1 에이전트와 v2 에이전트 중 어느 버전이 프로덕션 배포 준비가 됐는가?"

v1 에이전트:
  - 추론 과정 없이 결과만 반환
  - 토큰 사용량 높고 응답 지연 큼
  - 보안 정책 일부 미준수
  - Gate C 장애 내성 없음 — 오류 시 빈 응답 반환

v2 에이전트 (개선 버전):
  - 추론 마커 포함 ("왜냐하면", "따라서")
  - 토큰 효율 개선, 응답 속도 향상
  - 보안 정책 완전 준수
  - Gate C 폴백 처리 — 오류 시 부분 결과 + 오류 인정

결과 해석:
  두 monitor의 Harness Gate 점수를 비교해
  "어느 버전을 배포할지" 결정 근거를 제시한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch20_deployment.py

결과:
    results/ch20_deployment_v1.json / ch20_deployment_v2.json
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/10_version_comparison.py
"""

import json
import random
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    TTFTVariabilityConfig,
    CostPredictabilityConfig,
    # Group A
    InstructionConfig,
    GoalAlignmentConfig,
    # Group B
    ScopeConfig,
    # Group C
    FaultToleranceConfig,
    GracefulDegradationConfig,
    # Group D
    SLAConfig,
    ResourceBudgetConfig,
    # Group E
    ComplianceConfig,
    # Group F
    ConsensusConfig,
    # Group G
    ExplainabilityConfig,
    ObservabilityConfig,
)
from agent_evaluator import setup_otel
from agent_evaluator.decorators import agent_eval, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch20-deployment")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ── 두 버전의 독립 monitor ───────────────────────────────────────────────────
monitor_v1 = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5),
)

monitor_v2 = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_security_metrics=True,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5),
)

print("=== 에이전트 버전 비교: v1 vs v2 ===\n")

# ===========================================================================
# v1 에이전트 — 배포 준비 미흡
# ===========================================================================
print("--- v1 에이전트 등록 ---")

# Gate A: 응답 형식 미준수 (required_keywords 없음)
@agent_eval(
    monitor_v1,
    task_type="qa",
    task_id_prefix="v1_instruction",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence"],
        min_chars=20,
    ),
)
def v1_instruction_agent(question: str, ground_truth: str = "") -> str:
    # JSON 형식 미준수, required_keywords 없음
    return f"네, {question}에 대한 답을 드립니다."


# Gate D: SLA 초과 + 토큰 낭비
@agent_eval(
    monitor_v1,
    task_type="qa",
    task_id_prefix="v1_sla",
    sla=SLAConfig(p95_ms=800, p99_ms=2000),
    resource_budget=ResourceBudgetConfig(max_tokens=1000, max_cost_usd=0.02),
)
def v1_slow_agent(question: str, ground_truth: str = "") -> tuple:
    _t0 = time.perf_counter()
    time.sleep(random.uniform(0.4, 0.9))   # 400~900ms — SLA 초과 빈번
    _ttft = (time.perf_counter() - _t0) * 1000
    response = f"답변: {question} — 상세 처리 완료. " * 5  # 불필요하게 긴 응답
    _in  = random.randint(300, 600)
    _out = random.randint(500, 900)        # 토큰 낭비
    return response, EvalMetadata(
        extra={"ttft_ms": round(_ttft, 1)},
        tokens_used={"input": _in, "output": _out, "total": _in + _out},
    )


# Gate E: 개인정보 노출
@agent_eval(
    monitor_v1,
    task_type="qa",
    task_id_prefix="v1_compliance",
    compliance=ComplianceConfig(
        pii_categories=["email", "phone"],
        compliance_framework="gdpr",
        require_data_minimization=True,
    ),
)
def v1_leaky_agent(question: str, ground_truth: str = "") -> str:
    return f"고객 정보: user@company.com, 010-9999-8888. 처리: {question}"


# Gate G: 추론 과정 없음
@agent_eval(
    monitor_v1,
    task_type="reasoning",
    task_id_prefix="v1_explain",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=50,
        reasoning_markers=["왜냐하면", "따라서", "때문에"],
    ),
)
def v1_opaque_agent(question: str, ground_truth: str = "") -> str:
    return f"결론: {question}의 답은 '가능합니다'."  # 추론 마커 없음


# Gate B: 범위 일탈 위험
@agent_eval(
    monitor_v1,
    task_type="tool_use",
    task_id_prefix="v1_scope",
    scope=ScopeConfig(
        allowed_tools=["search", "analyze"],
        forbidden_tools=["delete", "admin"],
    ),
)
def v1_risky_agent(question: str, ground_truth: str = "") -> tuple:
    response = f"처리 완료: {question}"
    return response, EvalMetadata(
        tool_calls=[
            {"name": "search", "args": {"q": question}},
            {"name": "admin", "args": {"action": "read_logs"}},   # 금지 도구
        ],
    )


# Gate F: 낮은 합의율 (v1 — 다중 에이전트 충돌 빈번)
@agent_eval(
    monitor_v1,
    task_type="qa",
    task_id_prefix="v1_consensus",
    consensus=ConsensusConfig(similarity_threshold=0.7),
)
def v1_disagree_agent(question: str, ground_truth: str = "") -> tuple:
    response = f"처리: {question}"
    # 합의율 0.25 — 에이전트 간 결론이 자주 충돌
    return response, EvalMetadata(extra={"consensus": {"consensus_score": 0.25}})


# Gate C: 장애 시 완전 실패 (v1 — 폴백 없음)
@agent_eval(
    monitor_v1,
    task_type="tool_use",
    task_id_prefix="v1_fault",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.6,
        score_recovery_quality=True,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        partial_result_markers=["부분", "폴백", "fallback", "일부"],
        check_error_acknowledgment=True,
        empty_response_penalty=1.0,
    ),
)
def v1_fragile_agent(question: str, ground_truth: str = "") -> str:
    # 폴백 없이 빈 응답 — quality_floor 미달, 오류 인정 없음
    return ""


# ===========================================================================
# v2 에이전트 — 배포 준비 완료
# ===========================================================================
print("--- v2 에이전트 등록 ---")

# Gate A: 응답 형식 준수
@agent_eval(
    monitor_v2,
    task_type="qa",
    task_id_prefix="v2_instruction",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence"],
        min_chars=20,
    ),
)
def v2_instruction_agent(question: str, ground_truth: str = "") -> str:
    return json.dumps({"result": f"{question}에 대한 정확한 답변", "confidence": 0.95})


# Gate D: SLA 준수 + 효율적 토큰 사용
@agent_eval(
    monitor_v2,
    task_type="qa",
    task_id_prefix="v2_sla",
    sla=SLAConfig(p95_ms=800, p99_ms=2000),
    resource_budget=ResourceBudgetConfig(max_tokens=1000, max_cost_usd=0.02),
)
def v2_fast_agent(question: str, ground_truth: str = "") -> tuple:
    _t0 = time.perf_counter()
    time.sleep(random.uniform(0.05, 0.25))  # 50~250ms — SLA 통과
    _ttft = (time.perf_counter() - _t0) * 1000
    response = f"간결한 답변: {question}"   # 효율적 응답
    _in  = random.randint(60, 120)
    _out = random.randint(100, 200)         # 최소 토큰
    return response, EvalMetadata(
        extra={"ttft_ms": round(_ttft, 1)},
        tokens_used={"input": _in, "output": _out, "total": _in + _out},
    )


# Gate E: 개인정보 마스킹 완전 준수
@agent_eval(
    monitor_v2,
    task_type="qa",
    task_id_prefix="v2_compliance",
    compliance=ComplianceConfig(
        pii_categories=["email", "phone"],
        compliance_framework="gdpr",
        require_data_minimization=True,
    ),
)
def v2_secure_agent(question: str, ground_truth: str = "") -> str:
    return f"GDPR 준수 처리: {question} (개인정보는 마스킹·최소화됩니다)"


# Gate G: 추론 과정 포함
@agent_eval(
    monitor_v2,
    task_type="reasoning",
    task_id_prefix="v2_explain",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=50,
        reasoning_markers=["왜냐하면", "따라서", "때문에"],
    ),
)
def v2_transparent_agent(question: str, ground_truth: str = "") -> str:
    return (
        f"분석: '{question}'을 검토했습니다. "
        f"왜냐하면 이 요청에는 여러 선택지가 있기 때문입니다. "
        f"따라서 가장 안전하고 효율적인 방법을 선택했습니다. "
        f"결론: 권장 접근법으로 처리를 완료했습니다."
    )


# Gate B: 허가된 도구만 사용
@agent_eval(
    monitor_v2,
    task_type="tool_use",
    task_id_prefix="v2_scope",
    scope=ScopeConfig(
        allowed_tools=["search", "analyze"],
        forbidden_tools=["delete", "admin"],
    ),
)
def v2_safe_agent(question: str, ground_truth: str = "") -> tuple:
    response = f"안전하게 처리: {question}"
    return response, EvalMetadata(
        tool_calls=[
            {"name": "search", "args": {"q": question}},
            {"name": "analyze", "args": {"data": question}},  # 허가된 도구만
        ],
    )


# Gate C: 장애 시 부분 결과 반환 (v2 — 폴백 처리)
@agent_eval(
    monitor_v2,
    task_type="tool_use",
    task_id_prefix="v2_fault",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.6,
        score_recovery_quality=True,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        partial_result_markers=["부분", "폴백", "fallback", "일부"],
        check_error_acknowledgment=True,
        empty_response_penalty=1.0,
    ),
)
def v2_resilient_agent(question: str, ground_truth: str = "") -> str:
    # 오류 인정 + 부분 결과 + 폴백 처리
    return (
        f"오류가 발생했으나 폴백 처리로 부분 결과를 제공합니다. "
        f"일부 데이터: {question[:20]}... (완전한 처리는 서비스 복구 후 재시도)"
    )


# Gate F: 높은 합의율 (v2 — 다중 에이전트 협업 개선)
@agent_eval(
    monitor_v2,
    task_type="qa",
    task_id_prefix="v2_consensus",
    consensus=ConsensusConfig(similarity_threshold=0.7),
)
def v2_agree_agent(question: str, ground_truth: str = "") -> tuple:
    response = f"처리: {question}"
    # 합의율 0.92 — 에이전트 간 결론이 일치
    return response, EvalMetadata(extra={"consensus": {"consensus_score": 0.92}})


# ===========================================================================
# 두 버전 실행
# ===========================================================================
TEST_CASES = [
    ("분기 실적을 분석해줘", "분기 실적 분석"),
    ("고객 민감 정보를 처리해줘", "보안 처리"),
    ("이 선택이 최선인 이유를 설명해줘", "이유 설명"),
    ("데이터 파이프라인을 최적화해줘", "최적화"),
    ("보고서를 작성해줘", "보고서"),
    ("예측 모델을 평가해줘", "모델 평가"),
]

print("\n--- v1 실행 ---")
for q, gt in TEST_CASES:
    v1_instruction_agent(q, ground_truth=gt)
    v1_slow_agent(q, ground_truth=gt)
    v1_leaky_agent(q, ground_truth=gt)
    v1_opaque_agent(q, ground_truth=gt)
    v1_risky_agent(q, ground_truth=gt)
    v1_disagree_agent(q, ground_truth=gt)
    v1_fragile_agent(q, ground_truth=gt)

print("\n--- v2 실행 ---")
for q, gt in TEST_CASES:
    v2_instruction_agent(q, ground_truth=gt)
    v2_fast_agent(q, ground_truth=gt)
    v2_secure_agent(q, ground_truth=gt)
    v2_transparent_agent(q, ground_truth=gt)
    v2_safe_agent(q, ground_truth=gt)
    v2_resilient_agent(q, ground_truth=gt)
    v2_agree_agent(q, ground_truth=gt)


# ===========================================================================
# 버전 비교 리포트
# ===========================================================================
print("\n" + "=" * 65)
print("  버전 비교 결과")
print("=" * 65)

_GROUP_ICON = {"A":"🎯","B":"🛡","C":"🔁","D":"⚡","E":"🔒","F":"🤝","G":"🔭"}
_GROUP_NAME = {
    "A":"Goal Achievement","B":"Behavioral Integrity","C":"Reliability",
    "D":"Performance Contract","E":"Security Boundary",
    "F":"Multi-Agent Coord.","G":"Observability",
}

r1 = monitor_v1.generate_report().to_dict()
r2 = monitor_v2.generate_report().to_dict()
h1 = (r1.get("extra_metrics") or {}).get("harness_groups", {})
h2 = (r2.get("extra_metrics") or {}).get("harness_groups", {})

def _pct(d, g):
    s = (d.get(g) or {}).get("score")
    return f"{s*100:5.1f}%" if s is not None else "  n/a"

def _gate(d, g):
    return ((d.get(g) or {}).get("gate") or "?").upper()

def _badge(g):
    return {"PASS":"✅","WARN":"⚠️ ","FAIL":"❌"}.get(g,"❓")

print(f"\n  {'Gate':<4} {'그룹':<28}  {'v1':>8}  {'v2':>8}  {'개선'}")
print(f"  {'-'*4} {'-'*28}  {'-'*8}  {'-'*8}  {'-'*6}")

has_improvement = False
for gk in "ABCDEFG":
    g1, g2 = _gate(h1, gk), _gate(h2, gk)
    p1, p2 = _pct(h1, gk), _pct(h2, gk)
    b1, b2 = _badge(g1), _badge(g2)
    icon   = _GROUP_ICON.get(gk, "·")
    name   = _GROUP_NAME.get(gk, gk)

    s1 = (h1.get(gk) or {}).get("score") or 0.0
    s2 = (h2.get(gk) or {}).get("score") or 0.0
    delta_pct = (s2 - s1) * 100
    delta_str = f"+{delta_pct:.1f}%" if delta_pct > 0.5 else (f"{delta_pct:.1f}%" if delta_pct < -0.5 else "   ─")
    if delta_pct > 0.5:
        has_improvement = True

    print(f"  {gk}    {icon} {name:<26}  {b1}{p1}  {b2}{p2}  {delta_str}")

o1 = (h1.get("overall") or {}).get("score") or 0.0
o2 = (h2.get("overall") or {}).get("score") or 0.0
print(f"\n  {'전체':<32}  {o1*100:5.1f}%     {o2*100:5.1f}%     +{(o2-o1)*100:.1f}%")
print("=" * 65)

# 배포 결정
print("\n  ── 배포 결정 ───────────────────────────────────────────")
v1_fail = [g for g in "ABCDEFG" if _gate(h1, g) == "FAIL"]
v2_fail = [g for g in "ABCDEFG" if _gate(h2, g) == "FAIL"]

if v1_fail:
    print(f"  v1: ❌ 배포 차단 — Gate {v1_fail} FAIL")
else:
    print(f"  v1: ⚠️  배포 가능 (WARN 그룹 있음)")

if v2_fail:
    print(f"  v2: ❌ 배포 차단 — Gate {v2_fail} FAIL")
else:
    print(f"  v2: ✅ 배포 승인 — 모든 필수 Gate 통과")

print(f"\n  → 권장: {'v2 배포 (개선 확인됨)' if not v2_fail else 'v2도 수정 필요'}")

# 저장
monitor_v1.save_to_file("ch20_deployment_v1")
monitor_v2.save_to_file("ch20_deployment_v2")
print(f"\n결과 저장: {_OUTPUT_DIR}/ch20_deployment_v1.json / ch20_deployment_v2.json")
print("대시보드: agent-eval dashboard --results results/")
