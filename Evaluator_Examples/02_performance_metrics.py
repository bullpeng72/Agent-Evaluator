"""
성능 지표 검증 예제 — Agent Evaluator
======================================

커버 지표 (성능 카테고리):
  Layer 1  │ Task Completion Rate  (TCR · full/partial/failure 분류 · 벤치마크 비교)
           │ Latency Tracking      (p50 · p95 · p99 · 병목 탐지 · SLA 준수)
           │ Token Economy         (입출력 토큰 비율 · 비용 추정 · 월간 예측)

실행:
    python 02_performance_metrics.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent_evaluator import PerformanceMonitor, TaskResult

# ────────────────────────────────────────────────────────────────────────────────
# 태스크 시나리오 정의
# ────────────────────────────────────────────────────────────────────────────────

# (task_type, completion_profile, latency_profile, token_profile)
# completion_profile: "high"(>0.9 success), "medium"(~0.7), "low"(<0.5)
# latency_profile: "fast"(<1s), "normal"(1-3s), "slow"(5-15s), "timeout"(>15s)
# token_profile: "small"(<500), "medium"(500-2000), "large"(>2000)

TASK_SCENARIOS = [
    # ─── 빠른 QA 태스크 ─────────────────────────────────────────────────────
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "normal", "small"),
    ("qa",              "medium", "normal", "small"),
    ("qa",              "high",   "fast",   "small"),
    ("qa",              "high",   "fast",   "medium"),
    ("qa",              "high",   "normal", "small"),
    ("qa",              "medium", "slow",   "medium"),
    # ─── 데이터 분석 태스크 ──────────────────────────────────────────────────
    ("data_analysis",   "high",   "normal", "medium"),
    ("data_analysis",   "high",   "slow",   "large"),
    ("data_analysis",   "medium", "slow",   "large"),
    ("data_analysis",   "high",   "normal", "medium"),
    ("data_analysis",   "low",    "slow",   "medium"),
    ("data_analysis",   "high",   "normal", "large"),
    # ─── 코드 생성 태스크 ────────────────────────────────────────────────────
    ("code_generation", "high",   "slow",   "large"),
    ("code_generation", "high",   "normal", "medium"),
    ("code_generation", "medium", "slow",   "large"),
    ("code_generation", "high",   "slow",   "large"),
    ("code_generation", "high",   "normal", "medium"),
    ("code_generation", "low",    "slow",   "medium"),
    ("code_generation", "high",   "slow",   "large"),
    # ─── 추론 태스크 ─────────────────────────────────────────────────────────
    ("reasoning",       "high",   "normal", "medium"),
    ("reasoning",       "high",   "slow",   "large"),
    ("reasoning",       "medium", "normal", "medium"),
    ("reasoning",       "high",   "slow",   "large"),
    ("reasoning",       "low",    "slow",   "large"),
    ("reasoning",       "high",   "normal", "medium"),
    # ─── 문서 생성 태스크 ────────────────────────────────────────────────────
    ("document_creation", "high",  "slow",   "large"),
    ("document_creation", "high",  "normal", "large"),
    ("document_creation", "medium","slow",   "large"),
    ("document_creation", "high",  "slow",   "large"),
    # ─── 정보 검색 태스크 ────────────────────────────────────────────────────
    ("information_retrieval", "high",   "fast",   "small"),
    ("information_retrieval", "high",   "fast",   "medium"),
    ("information_retrieval", "medium", "normal", "medium"),
    ("information_retrieval", "high",   "fast",   "small"),
    # ─── 계획 수립 태스크 ────────────────────────────────────────────────────
    ("planning",        "high",   "slow",   "large"),
    ("planning",        "medium", "slow",   "medium"),
    ("planning",        "high",   "slow",   "large"),
    ("planning",        "high",   "normal", "medium"),
    # ─── 도구 사용 태스크 ────────────────────────────────────────────────────
    ("tool_use",        "high",   "normal", "medium"),
    ("tool_use",        "medium", "slow",   "medium"),
    ("tool_use",        "high",   "normal", "small"),
    ("tool_use",        "low",    "timeout","large"),
    ("tool_use",        "high",   "normal", "medium"),
    # ─── 크리에이티브 태스크 ─────────────────────────────────────────────────
    ("creative",        "high",   "slow",   "large"),
    ("creative",        "medium", "slow",   "large"),
    ("creative",        "high",   "normal", "medium"),
]


def _gen_latency(profile: str, rng: random.Random) -> float:
    if profile == "fast":
        return round(rng.uniform(0.15, 0.80), 3)
    elif profile == "normal":
        return round(rng.uniform(1.0, 3.5), 3)
    elif profile == "slow":
        return round(rng.uniform(4.5, 12.0), 3)
    else:  # timeout
        return round(rng.uniform(15.0, 30.0), 3)


def _gen_tokens(profile: str, rng: random.Random) -> dict:
    if profile == "small":
        inp = rng.randint(50, 250)
        out = rng.randint(30, 150)
    elif profile == "medium":
        inp = rng.randint(250, 1000)
        out = rng.randint(150, 800)
    else:  # large
        inp = rng.randint(1000, 4000)
        out = rng.randint(600, 2500)
    return {"input": inp, "output": out, "total": inp + out}


def _gen_completion(profile: str, rng: random.Random) -> tuple:
    """Returns (success, completion_score, accuracy_score, partial)"""
    if profile == "high":
        score = round(rng.uniform(0.85, 1.0), 3)
        acc = round(rng.uniform(0.78, 0.97), 3)
        return True, score, acc, False
    elif profile == "medium":
        score = round(rng.uniform(0.55, 0.80), 3)
        acc = round(rng.uniform(0.50, 0.78), 3)
        partial = rng.random() < 0.6
        return partial, score, acc, partial
    else:  # low
        score = round(rng.uniform(0.10, 0.50), 3)
        acc = round(rng.uniform(0.10, 0.45), 3)
        return False, score, acc, False


def run_performance_evaluation():
    print("\n" + "=" * 70)
    print("  성능 지표 평가 — Agent Evaluator")
    print("  Coverage: Task Completion · Latency · Token Economy")
    print("=" * 70)

    rng = random.Random(1234)

    # GPT-4o-mini 수준 pricing
    monitor = PerformanceMonitor(
        pricing={"input": 0.00015, "output": 0.0006},  # per 1K tokens
        enable_hallucination_detection=True,
        output_dir=str(project_root / "results"),
    )

    base_time = datetime.now() - timedelta(hours=4)

    type_counts: dict = {}
    for idx, (task_type, comp_prof, lat_prof, tok_prof) in enumerate(TASK_SCENARIOS):
        n = type_counts.get(task_type, 0) + 1
        type_counts[task_type] = n
        task_id = f"perf_{task_type[:4]}_{n:03d}"

        success, completion, accuracy, partial = _gen_completion(comp_prof, rng)
        exec_time = _gen_latency(lat_prof, rng)
        tokens = _gen_tokens(tok_prof, rng)

        errors = []
        if not success and not partial:
            errors = [f"{task_type}_execution_failed"]
        elif lat_prof == "timeout":
            errors = ["timeout_exceeded"]

        attempts = 1
        if comp_prof in ("low", "medium") and rng.random() < 0.4:
            attempts = rng.randint(2, 3)

        task = TaskResult(
            task_id=task_id,
            task_type=task_type,
            success=success,
            completion_score=completion,
            accuracy_score=accuracy,
            execution_time=exec_time,
            tokens_used=tokens,
            tool_calls=[],
            attempts=attempts,
            errors=errors,
            timestamp=base_time + timedelta(minutes=idx * 5),
            framework="native",
        )

        request_text = f"{task_type} 태스크 #{n}: 관련 작업을 수행하세요"
        response_text = "완료된 결과입니다." if success else "처리 중 오류가 발생했습니다."
        ground_truth_text = f"expected_output_{task_id}"

        monitor.record_task(
            task,
            ground_truth=ground_truth_text,
            context=ground_truth_text,
            request=request_text,
            response=response_text,
        )

        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=response_text,
            request=request_text,
            expected_elements=[ground_truth_text],
            ground_truth=ground_truth_text,
        )

        if task_type in ("qa", "information_retrieval"):
            monitor.record_rag_metrics(
                faithfulness=round(min(accuracy * rng.uniform(0.85, 1.05), 1.0), 3),
                answer_relevancy=round(min(accuracy * rng.uniform(0.90, 1.10), 1.0), 3),
                context_precision=round(min(completion * rng.uniform(0.80, 1.00), 1.0), 3),
                context_recall=round(min(completion * rng.uniform(0.75, 1.05), 1.0), 3),
            )

    # ─── SLA 임계값 검사 ─────────────────────────────────────────────────────
    sla_targets = {
        "p50": 3.0,   # 3초
        "p95": 10.0,  # 10초
        "p99": 20.0,  # 20초
        "mean": 5.0,  # 5초
    }

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[P]_performance_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)

    # ─── 결과 출력 ────────────────────────────────────────────────────────────
    tcr_data    = report.accuracy_metrics.get("tcr", {})
    latency_data = report.efficiency_metrics.get("latency", {})
    token_data  = report.efficiency_metrics.get("tokens", {})
    retry_data  = report.efficiency_metrics.get("retries", {})

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개")
    print(f"  저장 위치: {saved_path}")

    total_tasks = report.total_tasks

    print(f"\n  [Task Completion Rate]")
    if tcr_data:
        tcr_val = tcr_data.get("tcr", 0)
        full    = tcr_data.get("full_success", 0)
        partial = tcr_data.get("partial_success", 0)
        fail    = tcr_data.get("failures", 0)
        bench   = monitor.tcr_tracker.get_benchmark_status(tcr_val)
        print(f"    TCR (전체):    {tcr_val:.1f}%")
        print(f"    완전 성공:     {full}/{total_tasks}건")
        print(f"    부분 성공:     {partial}/{total_tasks}건")
        print(f"    실패:          {fail}/{total_tasks}건")
        print(f"    벤치마크:      {bench}")

    print(f"\n  [Latency (초)]")
    if latency_data:
        # latency_data: {'all': {...}, 'qa': {...}, ...} 또는 flat dict
        lat = latency_data.get("all", latency_data)
        if not isinstance(lat, dict) or "p50" not in lat:
            # try first value that has p50
            for v in latency_data.values():
                if isinstance(v, dict) and "p50" in v:
                    lat = v
                    break
        print(f"    p50:  {lat.get('p50', 0):.2f}s")
        print(f"    p95:  {lat.get('p95', 0):.2f}s")
        print(f"    p99:  {lat.get('p99', 0):.2f}s")
        print(f"    평균: {lat.get('mean', 0):.2f}s")
        bottleneck = lat.get("slowest_type", lat.get("bottleneck", ""))
        if bottleneck:
            print(f"    최고 지연 타입: {bottleneck}")

    sla_check = monitor.latency_tracker.check_sla_compliance(sla_targets)
    if sla_check:
        violations = [k for k, v in sla_check.items()
                      if isinstance(v, dict) and not v.get("compliant", True)]
        print(f"    SLA 위반: {violations if violations else '없음'}")

    print(f"\n  [Token Economy]")
    if token_data:
        dist = token_data.get("token_distribution", {})
        in_ratio  = dist.get("input_ratio", 0)
        out_ratio = dist.get("output_ratio", 0)
        print(f"    총 토큰:        {token_data.get('total_tokens', 0):,}")
        print(f"    총 비용:        ${token_data.get('total_cost', 0):.4f}")
        print(f"    태스크당 비용:  ${token_data.get('avg_cost_per_task', 0):.5f}")
        print(f"    월간 예상 비용: ${token_data.get('estimated_monthly_cost', 0):.2f}")
        print(f"    입출력 비율:    입력 {in_ratio*100:.0f}% / 출력 {out_ratio*100:.0f}%")

    print(f"\n  [Retry & Correction]")
    if retry_data:
        print(f"    재시도율:       {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률:  {retry_data.get('first_attempt_success_rate', 0):.1f}%")
        print(f"    최종 성공률:    {retry_data.get('eventual_success_rate', 0):.1f}%")

    if report.alerts:
        print(f"\n  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:4]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")

    if report.recommendations:
        print(f"\n  [Recommendations — {len(report.recommendations)}건]")
        for r in report.recommendations[:3]:
            print(f"    → [{r.get('priority','').upper()}] {r.get('title', r.get('area', ''))}")

    print(f"{'─'*70}\n")
    return saved_path


if __name__ == "__main__":
    run_performance_evaluation()
