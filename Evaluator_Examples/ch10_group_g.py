"""
ch10_group_g.py — Gate G: Observability
========================================
Book Chapter 10 — Gate G: Observability

ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig,
LatencyAttributionConfig — 4개 Config 전체 시연.

역케이스(_monitor_g_fail)로 Gate G FAIL 유도 비교도 포함한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch10_group_g.py

결과:
    results/ch10_group_g.json  (+ .html)
    → 전체 33개 Config 통합 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import json
import random
import socket
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    setup_otel,
    AnomalyDetector, AnomalyEvent,
    CostTracker, AdaptivePolicy, SamplingStage,
    # Group G — Observability
    ExplainabilityConfig,
    ObservabilityConfig,
    ErrorDiagnosisConfig,
    LatencyAttributionConfig,
)
from agent_evaluator.decorators import agent_eval, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch10-group-g")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Gate G 전용 monitor
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=False,
    enable_security_metrics=False,
    enable_transparency=True,
)

# ===========================================================================
# 섹션 7: Group G — Observability
# ===========================================================================
print("\n=== 섹션 7: Group G — Observability ===")


@agent_eval(
    monitor,
    task_type="reasoning",
    task_id_prefix="g_explain",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=50,
        reasoning_markers=["왜냐하면", "따라서", "때문에"],
    ),
)
def explainable_agent(question: str, ground_truth: str = "") -> str:
    """추론 설명 가능성 에이전트 (mock) — 사유 포함 응답."""
    return (
        f"[추론] {question}을 分析한 결과: "
        f"왜냐하면 입력에서 핵심 패턴이 발견되었기 때문입니다. "
        f"따라서 적절한 조치를 취했습니다. "
        f"결론: 요청한 작업이 정상적으로 완료되었습니다."
    )


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="g_observe",
    observability=ObservabilityConfig(
        required_span_attributes=["task_id", "task_type", "execution_time"],
        check_trace_continuity=True,
        min_coverage=0.9,
    ),
)
def observable_agent(question: str, ground_truth: str = "") -> str:
    """내부 상태 노출 에이전트 (mock) — 실행 추적 정보 포함."""
    return json.dumps({
        "answer": f"{question}에 대한 답변입니다.",
        "step": "final",
        "confidence": 0.88,
        "source": "knowledge_base",
        "trace": ["input_parse", "knowledge_lookup", "response_gen"],
    })


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="g_error_diag",
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=False,          # 모든 태스크에서 오류 진단 마커 스코어링
        acknowledgment_weight=0.3,
        root_cause_weight=0.5,
        suggestion_weight=0.2,
    ),
)
def error_diagnosing_agent(question: str, ground_truth: str = "") -> str:
    """오류 진단 에이전트 (mock) — 오류 원인 分析 + 해결 방향 제시."""
    return (
        f"[진단] {question}: 시스템 상태를 점검했습니다. "
        f"근본 원인: 입력 패턴과 현재 상태를 분석한 결과 처리 흐름이 확인되었습니다. "
        f"해결 방향: 정상 처리를 완료했으며 필요 시 재시도하세요."
    )


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="g_latency_attr",
    latency_attribution=LatencyAttributionConfig(
        tool_latency_key="tool_latencies",
        model_latency_key="model_latency_ms",
        max_tool_time_ratio=0.6,
    ),
)
def latency_attributed_agent(question: str, ground_truth: str = "") -> tuple:
    """지연 원인 分析 에이전트 (mock) — 구간별 지연 기여도 노출."""
    response = json.dumps({"answer": f"{question}에 대한 응답"})
    return response, EvalMetadata(
        extra={
            "tool_latencies":   120,
            "model_latency_ms": 350,
            "network_ms":       30,
        }
    )


# 섹션 7 실행
OBSERVABILITY_CASES = [
    ("머신러닝 모델의 과적합을 어떻게 방지하나요?", "정규화, 드롭아웃, 데이터 증강"),
    ("데이터베이스 오류가 발생했습니다", "오류 진단 및 복구"),
    ("API 응답 지연 원인을 分析해주세요", "지연 원인 分析"),
    ("추론 과정을 설명해줘", "단계별 추론 설명"),
]

for q, gt in OBSERVABILITY_CASES:
    explainable_agent(q, ground_truth=gt)
    observable_agent(q, ground_truth=gt)
    error_diagnosing_agent(q, ground_truth=gt)
    latency_attributed_agent(q, ground_truth=gt)

print(f"  섹션 7 완료: {len(OBSERVABILITY_CASES) * 4}건 기록")

# ── 역케이스: Gate G FAIL 유도 (ErrorDiagnosisConfig) ────────────────────────
_monitor_g_fail = PerformanceMonitor(output_dir=_OUTPUT_DIR)

@agent_eval(
    _monitor_g_fail, task_type="qa", task_id_prefix="g_fail_diag",
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=False,
        acknowledgment_weight=0.3,
        root_cause_weight=0.5,
        suggestion_weight=0.2,
    ),
)
def _g_fail_agent(question: str, ground_truth: str = "") -> str:
    return f"처리를 시도했으나 완료하지 못했습니다."  # 원인·해결책 전무

for _q in ["데이터베이스 오류를 해결해줘", "네트워크 실패를 복구해줘", "실패 원인을 알려줘"]:
    _g_fail_agent(_q)

_r = _monitor_g_fail.generate_report().to_dict()
_s = (_r.get("extra_metrics") or {}).get("harness_groups", {}).get("G", {})
_pct = f"{_s['score']*100:.1f}%" if _s.get("score") is not None else "n/a"
print(f"  ▶ 역케이스 Gate G: {_pct}  {'FAIL 확인 ✓' if (_s.get('gate','').upper()=='FAIL') else '예상과 다름'}")

# Gate G 점수 출력
_report = monitor.generate_report().to_dict()
_harness = (_report.get("extra_metrics") or {}).get("harness_groups", {})
_gd = _harness.get("G", {})
_score = _gd.get("score")
_status = _gd.get("status", "n/a")
if _score is not None:
    _bar = "█" * int(_score * 10) + "░" * (10 - int(_score * 10))
    print(f"\n  Gate G [Observability          ] {_bar} {_score:.3f} ({_status})")

# ===========================================================================
# 섹션 추가A: 이상 탐지 (AnomalyDetector)
# ===========================================================================
print("\n=== 섹션 추가A: 이상 탐지 (AnomalyDetector) ===")

monitor_anomaly = PerformanceMonitor(output_dir=_OUTPUT_DIR)
detector = AnomalyDetector(baseline_window=25, detection_window=5)

_BASELINE_QA = [
    ("서울의 수도는?",   "대한민국의 수도는 서울입니다",   "서울"),
    ("파이썬 창시자는?", "귀도 반 로섬이 개발했습니다",   "귀도 반 로섬"),
    ("지구의 위성은?",   "달이 지구 주위를 공전합니다",   "달"),
    ("물의 화학식은?",   "H2O가 물의 화학식입니다",       "H2O"),
    ("1+1은?",          "답은 2입니다",                  "2"),
    ("머신러닝이란?",    "AI 분야의 학습 기술입니다",     "AI 기계학습"),
]
for i in range(30):
    q, resp, gt = _BASELINE_QA[i % len(_BASELINE_QA)]
    r = create_taskresult(
        task_id=f"base_{i:03d}",
        question=q, response=resp, ground_truth=gt,
        execution_time=round(random.gauss(1.2, 0.3), 3),
        task_type="qa",
        tokens_used={"input": 100, "output": 40, "total": 140},
    )
    monitor_anomaly.record_task(r)

ANOMALY_CASES = [
    ("오류 급증1",    1.2,  "",     140),
    ("오류 급증2",    1.1,  "",     130),
    ("토큰 폭증",     1.5,  "응답", 5000),
    ("오류 급증3",    1.3,  "",     145),
    ("지연 스파이크", 15.0, "응답", 150),
]
for label, lat, resp, tok in ANOMALY_CASES:
    r = create_taskresult(
        task_id=f"anom_{label[:4]}",
        question=f"이상 케이스: {label}",
        response=resp, ground_truth="정상 응답",
        execution_time=lat, task_type="qa",
        tokens_used={"input": tok, "output": tok // 5, "total": tok + tok // 5},
    )
    monitor_anomaly.record_task(r)
    print(f"  [{label}] lat={lat:.1f}s  tok={tok}  기록 완료")

anomaly_events: list = []
try:
    anomaly_events = detector.scan(monitor_anomaly)
    print(f"\n  이상 탐지 결과: {len(anomaly_events)}건")
    for ev in anomaly_events[:5]:
        print(f"    [{ev.severity}] {ev.type}: {ev.detail[:70]}")
except Exception:
    print("  스캔 완료 (이벤트 없음 또는 데이터 부족)")

try:
    if anomaly_events:
        explanation = detector.explain_event(anomaly_events[0])
        print(f"  explain_event: {str(explanation)[:80]}...")
except Exception:
    pass

# ===========================================================================
# 섹션 추가B: 비용 추적 + 적응형 샘플링 (CostTracker + AdaptivePolicy)
# ===========================================================================
print("\n=== 섹션 추가B: 비용 추적 + 적응형 샘플링 ===")

policy = AdaptivePolicy(
    default_sample_rate=0.1,
    anomaly_sample_rate=1.0,
    budget_per_day=10.0,
    alert_at=0.8,
)
tracker = CostTracker(budget_per_day=10.0, alert_at=0.8)

MODEL_USAGES = [
    ("gpt-4o",         {"input": 800,  "output": 250, "model": "gpt-4o"}),
    ("claude-3-sonnet", {"input": 600,  "output": 200, "model": "claude-3-sonnet"}),
    ("gpt-4o-mini",    {"input": 1200, "output": 400, "model": "gpt-4o-mini"}),
    ("gpt-4o",         {"input": 2000, "output": 500, "model": "gpt-4o"}),
]
_COST_RATES = {
    "gpt-4o":          {"input": 0.005,   "output": 0.015},
    "claude-3-sonnet": {"input": 0.003,   "output": 0.015},
    "gpt-4o-mini":     {"input": 0.00015, "output": 0.0006},
}

monitor_cost = PerformanceMonitor(output_dir=_OUTPUT_DIR)
for model, tokens in MODEL_USAGES:
    result = create_taskresult(
        task_id=f"cost_{model[:8]}",
        question="비용 추적 테스트", response="응답", ground_truth="응답",
        execution_time=1.5, task_type="qa",
        tokens_used=tokens,
    )
    monitor_cost.record_task(result)

    rates = _COST_RATES.get(model, {"input": 0.003, "output": 0.015})
    cost_usd = (tokens["input"] * rates["input"] + tokens["output"] * rates["output"]) / 1000
    provider = "anthropic" if "claude" in model else "openai"
    tracker.record(
        provider=provider, model=model, cost_usd=cost_usd,
        input_tokens=tokens["input"], output_tokens=tokens["output"],
        evaluation_type="agent_call",
    )
    tok_total = tokens["input"] + tokens["output"]
    status = policy.get_status()
    print(f"  [{model:<16s}] tokens={tok_total}  stage={status.get('stage','?')}  rate={status.get('current_sample_rate',0):.0%}  cost=${cost_usd:.4f}")

try:
    today = tracker.get_today_cost()
    print(f"  오늘 비용: ${today:.4f} USD")
    print(f"  예산 알림: {tracker.is_budget_alert()}")
except Exception:
    print(f"  비용 추적 완료 ({len(MODEL_USAGES)}건)")

monitor.save_to_file("ch10_group_g")
print("\n결과 저장 완료: results/ch10_group_g.json")
print("확인: agent-eval dashboard --results results/")
