"""
ch07_group_d.py — Gate D: Performance Contract
===============================================
Book Chapter 07 — Gate D: Performance Contract

SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
TTFTVariabilityConfig, CostPredictabilityConfig — 5개 Config 전체 시연.

EvalMetadata(extra={"ttft_ms": ...}) 주입을 통한 TTFT 변동성 집계와
tokens_used 기반 비용 예측 가능성 집계도 포함한다.

역케이스(_monitor_d_fail)로 Gate D FAIL 유도 비교도 포함한다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch07_group_d.py

결과:
    results/ch07_group_d.json  (+ .html)
    → 전체 33개 Config 통합 예제: Evaluator_Examples/.deprecated/08_harness_eval.py
"""

import random
import socket
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    setup_otel,
    # Group D — Performance Contract
    SLAConfig,
    EfficiencyConfig,
    ResourceBudgetConfig,
    TTFTVariabilityConfig,
    CostPredictabilityConfig,
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
            setup_otel(endpoint="http://localhost:6006", service_name="ch07-group-d")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Gate D 전용 monitor
# — TTFTVariabilityConfig: 각 태스크 extra["ttft_ms"] 를 수집해 std·P95/P50 비율 계산
# — CostPredictabilityConfig: 동일 task_type 내 tokens_used 변동계수(CV) 계산
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_hallucination_detection=False,
    enable_security_metrics=False,
    enable_transparency=True,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5),
)

# ===========================================================================
# 섹션 4: Group D — Performance Contract
# ===========================================================================
print("\n=== 섹션 4: Group D — Performance Contract ===")


@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="d_sla",
    sla=SLAConfig(
        p95_ms=2000,
        p99_ms=5000,
        max_cost_per_task=0.01,
    ),
)
def sla_compliant_agent(question: str, ground_truth: str = "") -> tuple:
    """SLA 준수 에이전트 — TTFT·토큰 사용량을 EvalMetadata로 주입.

    EvalMetadata(extra={"ttft_ms": ...}) 를 함께 반환하면
    PerformanceMonitor 가 TTFTVariabilityConfig 집계에 해당 값을 사용한다.
    """
    _t0 = time.perf_counter()
    time.sleep(random.uniform(0.05, 0.25))  # 첫 토큰 지연 시뮬레이션
    _ttft_ms = (time.perf_counter() - _t0) * 1000
    time.sleep(random.uniform(0.05, 0.15))  # 나머지 생성 지연
    response = f"SLA 준수 응답: {question}"
    _in_tok  = random.randint(85, 110)
    _out_tok = random.randint(165, 200)
    return response, EvalMetadata(
        extra={"ttft_ms": round(_ttft_ms, 1)},
        tokens_used={"input": _in_tok, "output": _out_tok, "total": _in_tok + _out_tok},
    )


@agent_eval(
    monitor,
    task_type="data_analysis",
    task_id_prefix="d_efficiency",
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=200,
        penalize_failed_tokens=True,
    ),
)
def efficient_agent(question: str, ground_truth: str = "") -> tuple:
    """비용 효율 에이전트 — 최소 토큰 사용 + 토큰 수 주입.

    cost_unit="tokens", target=200: 완료당 200 토큰 이하 목표.
    task_type="data_analysis"으로 분리 → CostPredictabilityConfig CV 격리.
    """
    response = f"효율적 답변: {question[:30]}"
    _in_tok  = random.randint(55, 75)
    _out_tok = random.randint(75, 95)
    return response, EvalMetadata(
        tokens_used={"input": _in_tok, "output": _out_tok, "total": _in_tok + _out_tok},
    )


@agent_eval(
    monitor,
    task_type="reasoning",
    task_id_prefix="d_budget",
    resource_budget=ResourceBudgetConfig(
        max_tokens=1000,
        max_cost_usd=0.02,
        warn_at_pct=0.8,
    ),
)
def budget_aware_agent(question: str, ground_truth: str = "") -> tuple:
    """리소스 예산 인식 에이전트 — 토큰 수 주입.

    task_type="reasoning"으로 분리 → CostPredictabilityConfig CV 격리.
    """
    response = f"예산 내 응답: {question}"
    _in_tok  = random.randint(75, 95)
    _out_tok = random.randint(115, 135)
    return response, EvalMetadata(
        tokens_used={"input": _in_tok, "output": _out_tok, "total": _in_tok + _out_tok},
    )


# 섹션 4 실행
PERFORMANCE_CASES = [
    ("현재 날씨는?", "맑음"),
    ("주가 정보를 알려줘", "상승"),
    ("뉴스 요약을 해줘", "요약 완료"),
    ("시스템 상태는?", "정상"),
    ("데이터 통계를 계산해줘", "통계 완료"),
    ("머신러닝 모델 성능은?", "성능 측정"),  # min_samples=5 충족을 위한 6번째
]

for q, gt in PERFORMANCE_CASES:
    sla_compliant_agent(q, ground_truth=gt)
    efficient_agent(q, ground_truth=gt)
    budget_aware_agent(q, ground_truth=gt)

# TTFTVariabilityConfig·CostPredictabilityConfig 집계 흐름 요약:
#   1. 각 d_sla 태스크에서 EvalMetadata(extra={"ttft_ms": X}) 반환
#   2. PerformanceMonitor 가 모든 태스크의 ttft_ms 를 수집
#   3. generate_report() 호출 시 std·P95/P50 비율을 계산 → Gate D sub-score 반영
#   4. tokens_used 는 task_type 별 CV(변동계수) 계산에 사용 → cost predictability

print(f"  섹션 4 완료: {len(PERFORMANCE_CASES) * 3}건 기록 (TTFT·토큰 주입 포함)")

# ── 역케이스: Gate D FAIL 유도 (TTFTVariabilityConfig) ───────────────────────
_monitor_d_fail = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=80.0, max_p95_p50_ratio=1.8, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.15, min_samples=5),
)
_d_ttft = [30, 950, 40, 880, 25, 920, 35]
_d_tokens = [(15, 20), (800, 600), (20, 25), (750, 580), (18, 18), (820, 640), (22, 30)]
_d_idx = [0]

@agent_eval(
    _monitor_d_fail, task_type="qa", task_id_prefix="d_fail_ttft",
    sla=SLAConfig(p95_ms=5000),
    resource_budget=ResourceBudgetConfig(max_tokens=300, max_cost_usd=0.01),
)
def _d_fail_agent(question: str, ground_truth: str = "") -> tuple:
    i = _d_idx[0] % len(_d_ttft)
    _d_idx[0] += 1
    _in, _out = _d_tokens[i]
    return f"응답: {question}", EvalMetadata(
        extra={"ttft_ms": float(_d_ttft[i])},
        tokens_used={"input": _in, "output": _out, "total": _in + _out},
    )

for _q in ["분析해줘", "요약해줘", "검토해줘", "평가해줘", "비교해줘", "정리해줘", "확인해줘"]:
    _d_fail_agent(_q)

_r = _monitor_d_fail.generate_report().to_dict()
_s = (_r.get("extra_metrics") or {}).get("harness_groups", {}).get("D", {})
_pct = f"{_s['score']*100:.1f}%" if _s.get("score") is not None else "n/a"
print(f"  ▶ 역케이스 Gate D: {_pct}  {'FAIL 확인 ✓' if (_s.get('gate','').upper() in ('FAIL','WARN')) else '예상과 다름'}")

# Gate D 점수 출력
_report = monitor.generate_report().to_dict()
_harness = (_report.get("extra_metrics") or {}).get("harness_groups", {})
_gd = _harness.get("D", {})
_score = _gd.get("score")
_status = _gd.get("status", "n/a")
if _score is not None:
    _bar = "█" * int(_score * 10) + "░" * (10 - int(_score * 10))
    print(f"\n  Gate D [Performance Contract   ] {_bar} {_score:.3f} ({_status})")

# ===========================================================================
# 섹션 추가: Layer 1 지연시간 분포 (LatencyTracker)
# ===========================================================================
print("\n=== 섹션 추가A: 지연시간 분포 p50/p95/p99 ===")

import random as _rand

# 정규 분포에 이상치 추가 — 현실적 지연 패턴
# ※ 별도 monitor 사용: 이상치(8.5s, 12.0s)가 Gate D SLA 집계를 오염하지 않도록 분리
_monitor_lat = PerformanceMonitor(output_dir=_OUTPUT_DIR)
latencies = [_rand.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]
latencies = [max(0.1, lat) for lat in latencies]

for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"lat_{i:03d}",
        question="지연시간 측정용 쿼리",
        response="응답 완료",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
        tokens_used={"input": 50, "output": 20, "total": 70},
    )
    _monitor_lat.record_task(result)

_lat_rep = _monitor_lat.generate_report().to_dict().get("efficiency_metrics", {}).get("latency", {})
print(f"  p50={float(_lat_rep.get('p50',0)):.2f}s  p95={float(_lat_rep.get('p95',0)):.2f}s  p99={float(_lat_rep.get('p99',0)):.2f}s")

# ===========================================================================
# 섹션 추가: Layer 1 토큰 경제성 + 비용 추정 (TokenEconomyTracker)
# ===========================================================================
print("\n=== 섹션 추가B: 토큰 경제성 & 비용 추정 ===")

# ※ 별도 monitor 사용: 토큰 데모 태스크가 Gate D 집계를 오염하지 않도록 분리
_monitor_tok = PerformanceMonitor(output_dir=_OUTPUT_DIR)

TOKEN_MODELS = [
    ("gpt-4o",      {"input": 800, "output": 200, "total": 1000, "model": "gpt-4o"}),
    ("claude-3",    {"input": 600, "output": 150, "total": 750,  "model": "claude-3-sonnet"}),
    ("gpt-4o-mini", {"input": 400, "output": 100, "total": 500,  "model": "gpt-4o-mini"}),
]

for model_name, tokens in TOKEN_MODELS:
    result = create_taskresult(
        task_id=f"tok_{model_name}",
        question="토큰 비용 테스트",
        response="응답 내용",
        ground_truth="응답",
        execution_time=round(_rand.uniform(1.0, 3.0), 3),
        task_type="qa",
        tokens_used=tokens,
    )
    _monitor_tok.record_task(result)
    print(f"  [{model_name:<12s}] 총 {tokens['total']:4d} 토큰")

_tok_rep = _monitor_tok.generate_report().to_dict().get("efficiency_metrics", {}).get("tokens", {})
print(f"  누적 토큰: {int(_tok_rep.get('total_tokens', 0)):,}")
if _tok_rep.get("total_cost"):
    print(f"  예상 비용: ${float(_tok_rep['total_cost']):.4f} USD")

monitor.save_to_file("ch07_group_d")
print("\n결과 저장 완료: results/ch07_group_d.json")
print("확인: agent-eval dashboard --results results/")
