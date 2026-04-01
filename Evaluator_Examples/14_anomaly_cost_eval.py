"""
이상 탐지 · 비용 제어 · LLM 보조 평가 예제 — Agent Evaluator v0.6.7 Phase 3-B/3-C
===================================================================================

운영 에이전트의 지표 이상(이상 탐지)을 감지하고,
비용 예산과 샘플링 전략을 동적으로 조정합니다.

커버 기능 (Phase 3-B · Phase 3-C):
  Phase 3-B  │ enable_anomaly_detection=True  — save_to_file() 시 자동 이상 탐지
             │   결과 JSON "anomaly_data" 키 → 대시보드 "이상 감지" 탭 표시
             │ AnomalyDetector  — 5가지 이상 탐지 알고리즘 (직접 사용 시연)
             │   latency_trend · accuracy_drift · token_spike
             │   error_surge · security_pattern
  Phase 3-C  │ CostTracker      — 공급자별 · 평가 유형별 비용 추적
             │ AdaptivePolicy   — 예산 기반 동적 샘플링 전략
             │   DEFAULT → ANOMALY → BUDGET_EXCEEDED 단계 전환
  LLM Helper │ LLMHelper(별칭)  — LLMEvaluationHelper — LLM 보조 평가 래퍼

핵심 시나리오:
  1. PerformanceMonitor(enable_anomaly_detection=True) 로 자동 탐지 활성화
  2. 정상 구간 (50개 태스크) → save_to_file() anomaly_data: 이상 없음
  3. 이상 유발 구간 (10개 태스크) → 지연 급등 + 정확도 하락
  4. save_to_file() 시 AnomalyDetector 자동 실행 → anomaly_data JSON 저장
  5. AnomalyDetector.scan() 직접 호출 시연 (5가지 알고리즘 결과 출력)
  6. AdaptivePolicy.enter_anomaly_mode() → 샘플링률 100% 전환
  7. CostTracker.record() → 비용 누적 추적
  8. 예산 초과 시 AdaptivePolicy BUDGET_EXCEEDED 단계 전환

실행:
    python 14_anomaly_cost_eval.py    # API 키 불필요 (LLM 호출 없음)
"""

from __future__ import annotations

import dataclasses
import random
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    AnomalyDetector,
    CostTracker,
    AdaptivePolicy,
    LLMHelper,       # alias for LLMEvaluationHelper
    ClaudeHelper,    # alias for AnthropicEvaluationHelper
)
from agent_evaluator.cost.policy import SamplingStage


# ─── 태스크 시뮬레이션 헬퍼 ──────────────────────────────────────────────────
def _record_tasks(
    monitor: PerformanceMonitor,
    rng: random.Random,
    n: int,
    *,
    success_rate: float = 0.90,
    latency_range: tuple = (0.3, 1.0),
    accuracy_range: tuple = (0.78, 0.95),
    token_range: tuple = (100, 400),
    phase: str = "normal",
) -> None:
    """지정된 파라미터로 태스크 배치를 기록."""
    for i in range(n):
        success = rng.random() < success_rate
        exec_t  = rng.uniform(*latency_range)
        tokens  = rng.randint(*token_range)
        acc     = rng.uniform(*accuracy_range) if success else rng.uniform(0.1, 0.35)
        task_id = f"{phase}_{i+1:04d}"
        task = create_taskresult(
            task_id=task_id,
            question="평가 질문 예시",
            response="응답 예시" if success else "오류",
            ground_truth="정답 예시",
            execution_time=exec_t,
            task_type="qa",
            has_error=not success,
        )
        monitor.record_task(task)


def run_anomaly_cost_evaluation():
    print("\n" + "=" * 72)
    print("  이상 탐지 · 비용 제어 — Agent Evaluator v0.6.7")
    print("  Phase 3-B: AnomalyDetector  ·  Phase 3-C: CostTracker + AdaptivePolicy")
    print("=" * 72)

    rng = random.Random(20250404)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────
    # Phase 3-B: AnomalyDetector 시연
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*72}")
    print(f"  [Phase 3-B] AnomalyDetector")
    print(f"  {'─'*72}")

    # baseline_window=30: 처음 30개로 기준선 학습, detection_window=10: 최근 10개 비교
    detector = AnomalyDetector(baseline_window=30, detection_window=10)

    # enable_anomaly_detection=True: save_to_file() 시 AnomalyDetector 자동 실행
    # → 결과 JSON "anomaly_data" 키에 저장 → 대시보드 "이상 감지" 탭 표시
    monitor = PerformanceMonitor(
        output_dir=str(results_dir),
        enable_security_metrics=True,
        enable_anomaly_detection=True,
        anomaly_baseline_window=30,
        anomaly_detection_window=10,
    )

    # ── 구간 1: 정상 기준선 (50개) ──────────────────────────────────────
    # baseline_window(30) + detection_window(10) + 여유 = 50개 기록
    # AnomalyDetector는 accuracy_evaluator.evaluations / token_tracker.usage_log를
    # 직접 읽으므로 record_task() 외에 token tracker를 명시 호출
    # accuracy: 성공 태스크 → response==ground_truth → 1.0, 실패 → 다른 텍스트 → ~0.0
    print(f"\n  [구간 1] 정상 기준선 50개 기록")
    for i in range(50):
        task_id = f"base_{i+1:04d}"
        success = rng.random() < 0.92
        exec_t = round(rng.uniform(0.3, 0.8), 3)
        tokens_in  = rng.randint(100, 300)
        tokens_out = rng.randint(50, 150)
        # 성공/실패에 따라 응답 변경 → 정확도 분포에 자연스러운 분산 생성
        response = "정상 응답입니다" if success else "잘 모르겠습니다"
        task = create_taskresult(
            task_id=task_id,
            question="정상 평가 질문",
            response=response,
            ground_truth="정상 응답입니다",
            execution_time=exec_t,
            task_type="qa",
            has_error=not success,
        )
        # 실제 토큰 값을 task에 직접 설정 → record_task()가 정확한 값으로 token_tracker 업데이트
        task = dataclasses.replace(
            task, tokens_used={"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out}
        )
        monitor.record_task(task)

    anomalies_base = detector.scan(monitor)
    print(f"  기준선 이상 탐지: {len(anomalies_base)}건 (예상: 0건)")

    # ── 구간 2: 이상 유발 (정확히 detection_window=10개) ─────────────────
    # baseline = tasks[-30:-10] → 50개 중 indices 20-39 (모두 정상)
    # recent   = tasks[-10:]    → 이상 태스크 0-9
    print(f"\n  [구간 2] 이상 유발 구간 10개 기록")
    print(f"    - 지연 선형 급등 (0.5s → 2.0~3.7s, slope≈0.17)")
    print(f"    - 정확도 급락 (0.87 → ~0.05 낮은 유사도)")
    print(f"    - 오류율 급등 (8% → 70%)")
    print(f"    - 토큰 급증 (200 → 800~1300)")

    for i in range(10):
        task_id = f"anomaly_{i+1:04d}"
        success = rng.random() < 0.30   # 70% 오류
        exec_t = round(2.0 + i * 0.17 + rng.uniform(0, 0.2), 3)
        tokens_in  = rng.randint(600, 1000)
        tokens_out = rng.randint(200, 400)
        task = create_taskresult(
            task_id=task_id,
            question="이상 유발 질문 — 완전히 다른 내용",
            response="알 수 없음" if not success else "부분적으로 틀린 내용",
            ground_truth="정상 응답입니다",
            execution_time=exec_t,
            task_type="reasoning",
            has_error=not success,
        )
        # 실제 토큰 값을 task에 직접 설정 — token_spike 탐지를 위해 대량 토큰 주입
        # accuracy_drift: response vs ground_truth 텍스트 불일치 → accuracy ≈ 0.0 자동 계산
        task = dataclasses.replace(
            task, tokens_used={"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out}
        )
        monitor.record_task(task)

    # 보안 이상 시뮬레이션
    for j in range(8):
        monitor.input_sanitizer.evaluate_input(
            task_id=f"sec_anom_{j:03d}",
            input_text="'; DROP TABLE tasks; SELECT * FROM agents; --",
        )

    # AnomalyDetector.scan() — 5가지 알고리즘 동시 실행
    anomalies = detector.scan(monitor)
    print(f"\n  AnomalyDetector.scan() 결과: {len(anomalies)}개 이상 탐지")

    type_counts: dict[str, int] = {}
    for ev in anomalies:
        type_counts[ev.type] = type_counts.get(ev.type, 0) + 1

    for anom_type, cnt in sorted(type_counts.items()):
        sev_icons = [("🔴" if e.severity == "critical" else "🟡") for e in anomalies if e.type == anom_type]
        print(f"    [{sev_icons[0]} {anom_type}] {cnt}건")
        sample = next(e for e in anomalies if e.type == anom_type)
        print(f"       {sample.detail[:70]}")
        print(f"       알고리즘={sample.algorithm}  값={sample.value:.4f}  임계={sample.threshold:.4f}")

    # AnomalyEvent.to_dict() 확인
    if anomalies:
        anom_dict = anomalies[0].to_dict()
        print(f"\n  AnomalyEvent.to_dict() 키: {list(anom_dict.keys())}")

    # ─────────────────────────────────────────────────────────────────────
    # Phase 3-C: CostTracker 시연
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*72}")
    print(f"  [Phase 3-C] CostTracker — 공급자별 · 유형별 비용 추적")
    print(f"  {'─'*72}")

    # 예산 $0.50/일 설정, 80%($0.40) 도달 시 경보
    cost_tracker = CostTracker(budget_per_day=0.50, alert_at=0.80)

    # 다양한 평가 비용 기록 시뮬레이션
    # 총 비용이 $0.50 * 80% = $0.40 초과해야 경보 발생 (합계 ≈ $0.46)
    cost_records = [
        # (provider, model, cost_usd, input_tok, output_tok, eval_type)
        ("anthropic", "claude-3-5-sonnet", 0.0045, 1500, 300, "llm_judge"),
        ("openai",    "gpt-4o-mini",       0.0120, 800,  200, "deepeval"),
        ("anthropic", "claude-3-5-sonnet", 0.0380, 1200, 250, "llm_judge"),
        ("openai",    "gpt-4o-mini",       0.0090, 600,  150, "ragas"),
        ("anthropic", "claude-3-haiku",    0.0080, 400,  100, "llm_judge"),
        ("openai",    "gpt-4o-mini",       0.0150, 900,  200, "deepeval"),
        ("anthropic", "claude-3-5-sonnet", 0.0520, 1800, 350, "llm_judge"),
        ("openai",    "gpt-4o",            0.1200, 2000, 500, "deepeval"),
        ("anthropic", "claude-3-5-sonnet", 0.0410, 1400, 280, "llm_judge"),
        ("openai",    "gpt-4o-mini",       0.0100, 700,  180, "ragas"),
        # 추가 기록 — 예산 $0.40 경보 임계 초과를 위해
        ("anthropic", "claude-3-5-sonnet", 0.0450, 2000, 400, "llm_judge"),
        ("openai",    "gpt-4o",            0.0500, 1500, 300, "deepeval"),
    ]

    print(f"\n  비용 기록 ({len(cost_records)}건):")
    for provider, model, cost, inp, out, eval_type in cost_records:
        cost_tracker.record(
            provider=provider,
            model=model,
            cost_usd=cost,
            input_tokens=inp,
            output_tokens=out,
            evaluation_type=eval_type,
        )
        is_alert = cost_tracker.is_budget_alert()
        is_exceeded = cost_tracker.is_budget_exceeded()
        today = cost_tracker.get_today_cost()
        status = "🔴 초과" if is_exceeded else ("🟡 경보" if is_alert else "🟢 정상")
        print(f"    {provider:<12} {model:<26} ${cost:.4f}  "
              f"누계=${today:.4f}  {status}")

    daily_stats = cost_tracker.get_daily_stats()
    print(f"\n  CostTracker 일일 통계:")
    print(f"    오늘 합계   : ${daily_stats['today_total_usd']:.4f}")
    print(f"    예산 한도   : ${daily_stats['budget_per_day']:.2f}")
    print(f"    예산 잔여   : ${daily_stats['budget_remaining_usd']:.4f}")
    print(f"    예산 경보   : {daily_stats['budget_alert']}")
    print(f"    예산 초과   : {daily_stats['budget_exceeded']}")
    print(f"    호출 횟수   : {daily_stats['today_call_count']}건")
    print(f"    공급자별   :")
    for prov, amt in daily_stats.get("by_provider", {}).items():
        print(f"      {prov:<14}: ${amt:.4f}")
    print(f"    평가유형별  :")
    for etype, amt in daily_stats.get("by_evaluation_type", {}).items():
        print(f"      {etype:<14}: ${amt:.4f}")

    # ─────────────────────────────────────────────────────────────────────
    # Phase 3-C: AdaptivePolicy 시연
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*72}")
    print(f"  [Phase 3-C] AdaptivePolicy — 동적 샘플링 전략")
    print(f"  {'─'*72}")

    policy = AdaptivePolicy(
        default_sample_rate=0.10,   # 기본: 10% 샘플링
        anomaly_sample_rate=1.00,   # 이상 탐지 시: 100% 샘플링
        budget_per_day=0.50,
        alert_at=0.80,
    )

    # 단계 1: DEFAULT 모드
    print(f"\n  [단계 1] DEFAULT 모드 — 기본 샘플링")
    status = policy.get_status()
    print(f"    단계    : {status['stage']}")
    print(f"    샘플링률: {policy.current_sample_rate * 100:.0f}%")
    print(f"    현재 단계: {policy.current_stage}")
    assert policy.current_stage == SamplingStage.DEFAULT

    # 단계 2: ANOMALY 모드 — 이상 탐지 시 전환
    print(f"\n  [단계 2] ANOMALY 모드 — 이상 탐지 시 100% 샘플링 전환")
    if anomalies:
        reason = f"{len(anomalies)}개 이상 탐지: {anomalies[0].type}"
    else:
        reason = "테스트 이상 시뮬레이션"
    policy.enter_anomaly_mode(reason=reason)
    status = policy.get_status()
    print(f"    단계    : {status['stage']}")
    print(f"    샘플링률: {policy.current_sample_rate * 100:.0f}%  (이상 대응)")
    print(f"    전환 이유: {reason}")
    assert policy.current_stage == SamplingStage.ANOMALY
    assert policy.current_sample_rate == 1.0

    # 단계 3: 정상 복귀
    print(f"\n  [단계 3] 정상 복귀 — exit_anomaly_mode()")
    policy.exit_anomaly_mode()
    print(f"    단계    : {policy.current_stage}")
    print(f"    샘플링률: {policy.current_sample_rate * 100:.0f}%")
    assert policy.current_stage == SamplingStage.DEFAULT

    # 단계 4: 예산 초과 → BUDGET_EXCEEDED
    print(f"\n  [단계 4] 예산 초과 시뮬레이션 — BUDGET_EXCEEDED")
    # 정책 내부 cost_tracker에 고비용 기록하여 예산 초과 유도
    policy.cost_tracker.record(
        provider="anthropic", model="claude-opus-4",
        cost_usd=0.60,  # 예산 $0.50 초과
        evaluation_type="llm_judge",
    )
    policy.check_budget()
    status = policy.get_status()
    print(f"    단계    : {status['stage']}")
    print(f"    샘플링률: {policy.current_sample_rate * 100:.0f}%  (예산 초과 → 중단)")
    if policy.current_stage == SamplingStage.BUDGET_EXCEEDED:
        print(f"    ✅ BUDGET_EXCEEDED 정상 전환")

    # 단계 이력 확인
    stage_history = status.get("stage_history", [])
    print(f"\n  단계 전환 이력: {len(stage_history)}건")
    for h in stage_history:
        print(f"    → {h.get('stage', '?')}  사유: {h.get('reason', '')[:50]}")

    # ─────────────────────────────────────────────────────────────────────
    # LLMHelper / ClaudeHelper API 구조 시연
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*72}")
    print(f"  [LLMHelper / ClaudeHelper] API 구조 시연")
    print(f"  (실제 LLM 호출 없음 — 클래스 구조 확인용)")
    print(f"  {'─'*72}")

    new_monitor = PerformanceMonitor(output_dir=str(results_dir))

    # LLMHelper = LLMEvaluationHelper alias
    llm_helper = LLMHelper(monitor=new_monitor)
    print(f"\n  LLMHelper(monitor=monitor)")
    print(f"    타입   : {type(llm_helper).__name__}")
    print(f"    monitor: {type(llm_helper.monitor).__name__}")

    # ClaudeHelper = AnthropicEvaluationHelper alias
    claude_helper = ClaudeHelper(monitor=new_monitor)
    print(f"\n  ClaudeHelper(monitor=monitor)")
    print(f"    타입   : {type(claude_helper).__name__}")

    # 실제 사용 패턴 (API 키 있을 때)
    print(f"\n  실제 사용 패턴:")
    print(f"    from agent_evaluator import LLMHelper, ClaudeHelper")
    print(f"    helper = ClaudeHelper(monitor=monitor)")
    print(f"    # API 키 설정 후: helper.evaluate_with_llm(task_result=task)")

    # ─────────────────────────────────────────────────────────────────────
    # 통합 요약 리포트 저장
    # ─────────────────────────────────────────────────────────────────────
    report = monitor.generate_report()
    fname = f"[AN]_anomaly_cost_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    # save_to_file()이 enable_anomaly_detection=True이므로 자동으로 AnomalyDetector.scan() 호출
    # → 결과 파일 "anomaly_data.anomalies" 키에 저장 → 대시보드 이상 감지 탭 표시
    saved = monitor.save_to_file(fname)
    print(f"\n  📄 리포트 저장: {saved}")

    # Phase 3-C 비용 데이터를 결과 JSON에 통합 (standalone CostTracker → evaluation_cost)
    import json as _json, tempfile as _tempfile, os as _os
    with open(saved, encoding="utf-8") as _f:
        _saved_data = _json.load(_f)

    _daily = cost_tracker.get_daily_stats()
    # 공급자별 기록에서 비용 기준 대표 모델 추출
    _by_model: dict = {}
    for _r in cost_tracker.get_all_records():
        _m = _r.get("model", "unknown")
        _by_model[_m] = _by_model.get(_m, 0.0) + _r.get("cost_usd", 0.0)
    _primary_model = max(_by_model, key=_by_model.get) if _by_model else ""

    _saved_data["evaluation_cost"] = {
        "total_usd": _daily["today_total_usd"],
        "call_count": _daily["today_call_count"],
        "model": _primary_model,
        "by_provider": _daily["by_provider"],
        "by_evaluation_type": _daily.get("by_evaluation_type", {}),
        "budget_per_day": _daily["budget_per_day"],
        "budget_remaining_usd": _daily["budget_remaining_usd"],
        "sample_rate_current": policy.current_sample_rate,
        "projected_daily_usd": _daily["today_total_usd"],
    }
    _tmp_fd, _tmp_path = _tempfile.mkstemp(suffix=".json")
    try:
        with _os.fdopen(_tmp_fd, "w", encoding="utf-8") as _ftmp:
            _json.dump(_saved_data, _ftmp, ensure_ascii=False, indent=2)
        _os.replace(_tmp_path, saved)
    except Exception:
        _os.unlink(_tmp_path)
        raise
    print(f"  💰 evaluation_cost 주입 완료: ${_daily['today_total_usd']:.4f} / {len(_daily['by_provider'])}개 공급자")
    _ad = _saved_data.get("anomaly_data", {})
    _saved_anomalies = _ad.get("anomalies", [])
    print(f"  📊 결과 파일 anomaly_data: {len(_saved_anomalies)}개 이상 기록됨")
    print(f"     → 대시보드 '이상 감지' 탭에서 확인하세요.")

    # ── 검증 테이블 ───────────────────────────────────────────────────────
    today_cost = cost_tracker.get_today_cost()
    has_accuracy  = any(a.type == "accuracy_drift" for a in anomalies)
    has_error     = any(a.type == "error_surge"    for a in anomalies)
    has_token_spk = any(a.type == "token_spike"    for a in anomalies)

    checks = [
        ("기준선 이상 탐지 없음",        f"{len(anomalies_base)}건",   len(anomalies_base) == 0),
        ("이상 유발 후 탐지 있음",        f"{len(anomalies)}건",        len(anomalies) > 0),
        ("accuracy_drift 탐지",           str(has_accuracy),             has_accuracy),
        ("error_surge 탐지",              str(has_error),                has_error),
        ("token_spike 탐지",              str(has_token_spk),            has_token_spk),
        ("결과 파일 anomaly_data 포함",   f"{len(_saved_anomalies)}건",  len(_saved_anomalies) > 0),
        ("CostTracker 비용 누적",         f"${today_cost:.4f}",          today_cost > 0),
        ("예산 경보 발생",                str(daily_stats["budget_alert"]), daily_stats["budget_alert"]),
        ("ANOMALY 단계 전환 확인",        "성공",                        True),
        ("BUDGET_EXCEEDED 전환 확인",     str(policy.current_stage),
         policy.current_stage == SamplingStage.BUDGET_EXCEEDED),
        ("LLMHelper 초기화",              type(llm_helper).__name__,     llm_helper is not None),
    ]

    print(f"\n  {'═'*68}")
    print(f"  {'검증 항목':<32} {'실측값':<20} 결과")
    print(f"  {'─'*68}")
    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<32} {str(actual):<20} {mark}")
    print(f"  {'═'*68}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    return saved


if __name__ == "__main__":
    run_anomaly_cost_evaluation()
