"""
ch17_weekly_review.py — 주간·월간 품질 리뷰 자동화
===================================================
Book Chapter 17 — 주간·월간 품질 리뷰

RunTrendAnalyzer로 결과 파일 시계열 추세를 분석하고,
QuickEval.compare() / ab_test()로 전주 대비 회귀를 탐지한다.

  섹션 1: RunTrendAnalyzer — 결과 디렉토리 추세 분석
  섹션 2: QuickEval.replay() + compare() — 전주 대비 변화 비교
  섹션 3: ImplicitFeedbackTracker — 사용자 암묵적 피드백 주간 집계
  섹션 4: 월간 리포트 자동화 패턴

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch17_weekly_review.py

결과:
    results/ch17_weekly_review.json  (+ .html)
    results/ch17_week_a.json, ch17_week_b.json  (비교용 더미 파일)

summary() / compare() API 단위:
    tcr, accuracy   : 퍼센트 값 (0–100)
    avg_latency     : 초 (seconds)
    delta["tcr"]    : 퍼센트 포인트 차이
"""

import json
import random
import socket
from pathlib import Path

from agent_evaluator import (
    ImplicitFeedbackTracker,
    PerformanceMonitor,
    QuickEval,
    create_taskresult,
    setup_otel,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")
_RESULTS_PATH = Path(_OUTPUT_DIR)

try:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch17-weekly-review")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 사전 준비: 비교용 더미 주간 결과 파일 생성
# ===========================================================================
def _make_week_file(filename: str, accuracy_rate: float, n: int = 25):
    """비교용 더미 주간 결과 파일을 생성한다."""
    monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
    for i in range(n):
        is_correct = random.random() < accuracy_rate
        r = create_taskresult(
            task_id=f"{filename}_{i:03d}",
            question=f"질문 {i}",
            response="정확한 응답" if is_correct else "잘 모르겠습니다",
            ground_truth="정확한 응답",
            execution_time=1.2 + random.uniform(0.0, 0.5) if filename.endswith("a") else 1.8 + random.uniform(0.0, 0.8),
            task_type="qa",
            tokens_used={"input": 80, "output": 30, "total": 110},
        
            use_korean_tokenizer=True,
        )
        monitor.record_task(r)
    monitor.save_to_file(filename)

print("  비교용 더미 주간 파일 생성 중...")
_make_week_file("ch17_week_a", accuracy_rate=0.90, n=25)   # 지난 주 — 높은 정확도
_make_week_file("ch17_week_b", accuracy_rate=0.75, n=25)   # 이번 주 — 하락한 정확도
print("  완료: ch17_week_a.json (지난 주), ch17_week_b.json (이번 주)")

# ===========================================================================
# 섹션 1: RunTrendAnalyzer — 결과 디렉토리 추세 분석
# ===========================================================================
print("\n=== 섹션 1: RunTrendAnalyzer — 추세 분석 ===")

try:
    from agent_evaluator.cli.trend import RunTrendAnalyzer

    analyzer = RunTrendAnalyzer(
        results_dir=_OUTPUT_DIR,
        pattern="ch17_week*.json",
        window=10,
        slope_threshold=0.3,
    )
    report = analyzer.analyze()

    print(f"  분석 파일 수: {len(report.runs)}개")
    print(f"  회귀 감지:    {'있음 ⚠️' if report.any_regression else '없음 ✅'}")

    trend_map = {
        "tcr":             report.tcr_trend,
        "accuracy":        report.accuracy_trend,
        "latency":         report.latency_trend,
        "hallucination":   report.hallucination_trend,
        "cost":            report.cost_trend,
    }
    print(f"\n  지표별 추세:")
    for name, trend in trend_map.items():
        if trend is None:
            continue
        direction = "↑" if trend.slope > 0 else "↓" if trend.slope < 0 else "→"
        regression = "REGRESS" if trend.any_regression else "stable "
        print(f"    {name:<16} slope={trend.slope:+.3f}/run  {direction}  [{regression}]")

    if report.any_regression:
        print(f"\n  → CI/CD 연동: agent-eval trend results/ --fail-on-regression")
        print("  → 회귀의 '왜'는 다음 단계다: agent-eval diagnose <current.json> "
              "--baseline <baseline.json>  (Chapter 28 — 세부 지표 원인귀속 + "
              "newly_unmeasured_gates 커버리지 손실 경고)")

except Exception as e:
    print(f"  RunTrendAnalyzer: {e}")

# ===========================================================================
# 섹션 2: QuickEval.replay() + compare() — 전주 대비 변화 비교
# ===========================================================================
print("\n=== 섹션 2: QuickEval.replay() + compare() — 전주 대비 비교 ===")

week_a_file = str(_RESULTS_PATH / "ch17_week_a.json")
week_b_file = str(_RESULTS_PATH / "ch17_week_b.json")

eval_last = QuickEval(_OUTPUT_DIR)
eval_last.replay(week_a_file)
summary_last = eval_last.summary()  # tcr·accuracy는 0~100 퍼센트 단위

eval_this = QuickEval(_OUTPUT_DIR)
eval_this.replay(week_b_file)
summary_this = eval_this.summary()

print(f"\n  [ 지난 주 (week_a) ]")
print(f"    TCR:       {summary_last.get('tcr', 0):.1f}%")
print(f"    Accuracy:  {summary_last.get('accuracy', 0):.1f}%")
print(f"    P95:       {summary_last.get('p95_latency', 0):.2f}초")
print(f"    총 태스크: {summary_last.get('total_tasks', 0)}건")

print(f"\n  [ 이번 주 (week_b) ]")
print(f"    TCR:       {summary_this.get('tcr', 0):.1f}%")
print(f"    Accuracy:  {summary_this.get('accuracy', 0):.1f}%")
print(f"    P95:       {summary_this.get('p95_latency', 0):.2f}초")
print(f"    총 태스크: {summary_this.get('total_tasks', 0)}건")

try:
    # compare()는 {'self': {...}, 'other': {...}, 'delta': {'tcr': N, 'accuracy': N, 'avg_latency': N}} 반환
    comparison = eval_this.compare(eval_last)
    delta = comparison.get("delta", {})

    print(f"\n  [ 전주 대비 변화 (delta) ]")
    tcr_delta      = delta.get("tcr", 0)
    accuracy_delta = delta.get("accuracy", 0)
    latency_delta  = delta.get("avg_latency", 0)
    cost_delta     = delta.get("total_cost_usd", 0)
    print(f"    Accuracy:    {accuracy_delta:+.1f}pp")   # 퍼센트 포인트
    print(f"    TCR:         {tcr_delta:+.1f}pp")
    print(f"    Avg Latency: {latency_delta:+.2f}초")
    print(f"    비용:        {cost_delta:+.4f}$")

    # 회귀 판단 (Chapter 17.3 기준 — 단위: 퍼센트 포인트)
    REGRESSION_THRESHOLDS = {
        "accuracy": -3.0,    # -3pp
        "tcr":      -5.0,    # -5pp
        "latency":  +1.0,    # +1초
    }
    regressions = []
    if accuracy_delta < REGRESSION_THRESHOLDS["accuracy"]:
        regressions.append(f"Accuracy {accuracy_delta:+.1f}pp")
    if tcr_delta < REGRESSION_THRESHOLDS["tcr"]:
        regressions.append(f"TCR {tcr_delta:+.1f}pp")
    if latency_delta > REGRESSION_THRESHOLDS["latency"]:
        regressions.append(f"Avg Latency {latency_delta:+.2f}초")

    if regressions:
        print(f"\n  [!] 회귀 감지: {', '.join(regressions)}")
    else:
        print(f"\n  [OK] 모든 지표 정상 범위")

except Exception as e:
    print(f"  compare(): {e}")

# A/B 테스트 통계적 유의성
# ab_test() → {'self_mean', 'other_mean', 'delta', 'p_value', 'significant', 'sample_sizes'}
try:
    ab_result = eval_this.ab_test(eval_last)
    p_value    = ab_result.get("p_value", 1.0)
    significant = ab_result.get("significant", False)
    sizes      = ab_result.get("sample_sizes", {})
    print(f"\n  [ A/B 통계 유의성 ]")
    print(f"    p-value:      {p_value:.4f}")
    print(f"    유의미 여부:  {'있음 (p<0.05) — 실제 회귀' if significant else '없음 (p≥0.05) — 우연 변동'}")
    print(f"    샘플 수 A/B:  {sizes.get('self', '?')} / {sizes.get('other', '?')}")
except Exception as e:
    print(f"  ab_test(): {e} (scipy 필요: pip install scipy)")

# ===========================================================================
# 섹션 3: ImplicitFeedbackTracker — 사용자 암묵적 피드백 주간 집계
# ===========================================================================
print("\n=== 섹션 3: ImplicitFeedbackTracker — 암묵적 피드백 주간 집계 ===")
# 지원 feedback_type:
#   긍정: copy, follow_up_depth, save, share, thumbs_up
#   부정: regenerate, thumbs_down, abandon, correction

feedback_tracker = ImplicitFeedbackTracker()

FEEDBACK_DATA = [
    # (task_id, feedback_type)
    ("t001", "copy"),
    ("t002", "thumbs_up"),
    ("t003", "regenerate"),    # 부정: 재생성 요청
    ("t004", "copy"),
    ("t005", "save"),
    ("t006", "thumbs_down"),   # 부정: 비추천
    ("t007", "follow_up_depth"),
    ("t008", "regenerate"),    # 부정: 재생성 요청
]

for task_id, fb_type in FEEDBACK_DATA:
    feedback_tracker.record(task_id=task_id, feedback_type=fb_type)

stats = feedback_tracker.get_stats()
print(f"  총 피드백 수:    {stats.get('total', 0)}")
print(f"  긍정 건수:       {stats.get('positive_count', 0)}")
print(f"  부정 건수:       {stats.get('negative_count', 0)}")
print(f"  긍정율:          {stats.get('positive_rate', 0):.1f}%")
print(f"  재생성율:        {stats.get('regenerate_rate', 0):.1f}%  (낮을수록 좋음)")
print(f"  유형 분포:       {stats.get('type_distribution', {})}")

# ===========================================================================
# 섹션 4: 월간 리포트 자동화 패턴
# ===========================================================================
print("\n=== 섹션 4: 월간 리포트 자동화 패턴 ===")

print("""
  [ 월간 자동화 cron 설정 예시 ]

  # 매주 월요일 09:00 — 주간 리뷰
  0 9 * * 1 python ch17_weekly_review.py >> logs/weekly.log 2>&1

  # 매월 1일 09:00 — 월간 추세 분석 (최근 4주)
  0 9 1 * * agent-eval trend results/ --window 4 --output-json monthly_trend.json

  # 회귀 감지 시 CI/CD 차단
  0 9 * * 1 agent-eval trend results/ --fail-on-regression

  [ 월간 리포트 핵심 지표 ]
    - TCR·Accuracy 4주 평균 vs 전월 평균
    - P95 Latency 변동 추이
    - 총 비용 월간 합계
    - 보안 위협 탐지 누적 건수 (Gate E)
    - 골든 데이터셋 갱신 현황
""")

MONTHLY_METRICS = {
    "이번 달 TCR 평균":      "84.2%  (+1.3pp vs 전월)",
    "이번 달 Accuracy 평균": "72.1%  (-0.8pp vs 전월)",
    "P95 Latency 평균":      "2.3초  (+0.1초 vs 전월)",
    "월간 총 비용":           "$8.42 (+$0.51 vs 전월)",
    "보안 위협 감지":         "0건",
    "골든 데이터셋 갱신":     "47건 추가 / 12건 삭제",
}
print(f"  [ 월간 리포트 요약 예시 ]")
for metric, value in MONTHLY_METRICS.items():
    print(f"    {metric:<22}: {value}")

# ===========================================================================
# 최종 저장
# ===========================================================================
monitor_final = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
for q, gt in [("주간 리뷰 테스트", "테스트 완료"), ("월간 집계 테스트", "집계 완료")]:
    monitor_final.record_task(create_taskresult(
        task_id=f"review_{hash(q)%100:03d}",
        question=q, response=gt, ground_truth=gt,
        execution_time=0.1, task_type="qa",
    
        use_korean_tokenizer=True,
    ))

_fp = monitor_final.save_to_file("ch17_weekly_review")

# ── 개선된 리포트: 주간 리뷰 코멘트를 인사이트 계층에서 뽑아 쓴다 ────────────
# 섹션 1~2가 "회귀가 있었는가"를 봤다면, save_to_file()이 쓴
# extra_metrics.insights는 그 판정을 대상별 브리프(briefs)와 만성/재발 실패
# 추적(longitudinal)으로 정리해 둔다 — 사람이 다시 요약할 필요가 없다.
_ins = (json.loads(Path(_fp).read_text(encoding="utf-8"))
        .get("extra_metrics", {}).get("insights", {}))
_br = _ins.get("briefs") or {}
if _br:
    print("\n  ── insights.briefs ──")
    print(f"  PM : {_br.get('pm', '')}")
    print(f"  QA : {_br.get('qa', '')}")
_lg = _ins.get("longitudinal") or {}
if _lg:
    _rf = _lg.get("recurring_failures") or []
    print(f"  longitudinal: 형제 run {_lg.get('runs_scanned', 0)}개 스캔 · "
          f"재발 실패 {len(_rf)}건 · cadence={_lg.get('cadence_days')}일")
print("  CLI: agent-eval diagnose results/ch17_weekly_review.json --baseline <지난주>.json")
print("       agent-eval trend results/ --fail-on-regression")
print("\n결과 저장 완료: results/ch17_weekly_review.json  (+ .html)")
print("확인: agent-eval dashboard results/")
