"""
ch27_cicd_weekly.py — CI/CD 완성: 자동화로 지속 가능하게 만들기
================================================================
Book Chapter 27 — CI/CD 완성

골든 데이터셋 재현 평가, 8주 추세 분석, 주간 리뷰 자동화를
단계별로 실습한다. Gate D 비용 추세에서 숨겨진 드리프트를 발견한다.

  섹션 1: CI/CD 파이프라인 구조 — 3단계 자동화
  섹션 2: 골든 데이터셋 재현 평가 시뮬레이션
  섹션 3: RunTrendAnalyzer — 8주 추세 분석
  섹션 4: Gate D 비용 드리프트 발견
  섹션 5: 주간 리뷰 자동화 — 이상 감지 + 알림

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch27_cicd_weekly.py

결과:
    results/ch27_cicd_weekly.json  (+ .html)
"""

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    QuickEval,
    create_taskresult,
    setup_otel,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")


def _tcr(report):
    return report.to_dict()['accuracy_metrics']['tcr']['tcr']

def _acc(report):
    return float(report.to_dict()['accuracy_metrics']['accuracy_scores']['overall_accuracy'])

def _p95(report):
    return float(report.to_dict()['efficiency_metrics']['latency']['p95'])

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006",
                       service_name="ch26-cicd-weekly")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

print("=" * 60)
print("  Ch27: CI/CD 완성 — 자동화로 지속 가능하게 만들기")
print("=" * 60)

# ===========================================================================
# 섹션 1: CI/CD 파이프라인 구조
# ===========================================================================
print("\n=== 섹션 1: CI/CD 파이프라인 3단계 구조 ===")

print("""
  ┌──────────────────────────────────────────────────────────────┐
  │  1단계: PR 검증 (모든 PR에서 실행, ~3분)                    │
  │    골든 데이터셋 50건 재현 평가 → Gate 점수 확인             │
  │    agent-eval gate result.json --tcr 85 --accuracy 70        │
  │    실패 시: PR 차단                                           │
  ├──────────────────────────────────────────────────────────────┤
  │  2단계: 야간 전체 평가 (main 브랜치, 매일 02:00)            │
  │    골든 데이터셋 200건 전체 실행                             │
  │    결과를 results/ 에 날짜별 저장                            │
  │    이상 감지 시 Slack 알림                                   │
  ├──────────────────────────────────────────────────────────────┤
  │  3단계: 주간 리뷰 (매주 월요일 09:00)                       │
  │    최근 8주 추세 분석 (RunTrendAnalyzer)                     │
  │    회귀 감지 → 이슈 생성                                     │
  │    개선 추세 → 임계값 자동 상향 제안                         │
  └──────────────────────────────────────────────────────────────┘
""")

print("""
  [도서 보완] GitHub Actions 설정 예시 (.github/workflows/agent-eval.yml)
  ──────────────────────────────────────────────────────────────
  name: AI Agent Quality Gate
  on: [pull_request]
  
  jobs:
    eval:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - name: Set up Python
          uses: actions/setup-python@v5
          with: {python-version: '3.10'}
          
        - name: Install dependencies
          run: pip install agent-evaluator[llm]
          
        - name: Run Evaluation
          env:
            OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          run: python tests/run_eval_suite.py --output results/pr-eval.json
          
        - name: Quality Gate
          run: |
            agent-eval gate results/pr-eval.json \\
              --tcr 85 --accuracy 70 --p95-latency 3.0 \\
              --junit-xml results/junit.xml
              
        - name: Publish Test Report
          uses: mikepenz/action-junit-report@v4
          if: always()
          with: {report_paths: 'results/junit.xml'}
  ──────────────────────────────────────────────────────────────
""")

# ===========================================================================
# 섹션 2: 골든 데이터셋 재현 평가 시뮬레이션
# ===========================================================================
print("\n=== 섹션 2: 골든 데이터셋 재현 평가 ===")

print("""  골든 데이터셋: 프로덕션에서 "좋은 결과"로 검증된 질문-정답 쌍
  GoldenSetBuilder가 TCR=1.0, Accuracy>=0.8인 결과를 자동 추출한다.
""")

GOLDEN_DATASET = [
    {"id": "golden_001", "question": "FastAPI 라우터 정의 방법", "ground_truth": "APIRouter"},
    {"id": "golden_002", "question": "Pydantic 모델 정의",       "ground_truth": "BaseModel"},
    {"id": "golden_003", "question": "의존성 주입 방법",         "ground_truth": "Depends"},
    {"id": "golden_004", "question": "비동기 엔드포인트 작성법", "ground_truth": "async def"},
    {"id": "golden_005", "question": "미들웨어 추가 방법",       "ground_truth": "add_middleware"},
    {"id": "golden_006", "question": "예외 핸들러 등록",         "ground_truth": "exception_handler"},
    {"id": "golden_007", "question": "백그라운드 태스크 실행",   "ground_truth": "BackgroundTasks"},
    {"id": "golden_008", "question": "WebSocket 엔드포인트",     "ground_truth": "WebSocket"},
    {"id": "golden_009", "question": "파일 업로드 처리",         "ground_truth": "UploadFile"},
    {"id": "golden_010", "question": "응답 모델 설정",           "ground_truth": "response_model"},
]

# CI PR 검증 시뮬레이션
ci_monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
print("  PR 검증 — 골든 데이터셋 10건 재현 평가:")
for item in GOLDEN_DATASET:
    # 실제 환경에서는 여기서 실제 에이전트를 호출
    answer = f"{item['ground_truth']}를 사용해 {item['question']}을 구현합니다."
    exec_time = 0.3 + random.uniform(0, 0.5)

    result = create_taskresult(
        task_id=item["id"],
        question=item["question"],
        response=answer,
        ground_truth=item["ground_truth"],
        execution_time=exec_time,
        task_type="qa",
        metadata={"source": "golden_dataset", "ci_run": True},
    
        use_korean_tokenizer=True,
    )
    ci_monitor.record_task(result)

ci_report = ci_monitor.generate_report()
tcr_pass    = _tcr(ci_report) >= 85
acc_pass    = _acc(ci_report) >= 70

print(f"\n  TCR:      {_tcr(ci_report):.1f}%  {'✅ PASS' if tcr_pass else '❌ FAIL'} (임계값: 85%)")
print(f"  Accuracy: {_acc(ci_report):.1f}%  {'✅ PASS' if acc_pass else '❌ FAIL'} (임계값: 70%)")
print(f"  P95:      {_p95(ci_report):.2f}초")

gate_cmd = "agent-eval gate results/ch27_cicd_weekly.json --tcr 85 --accuracy 70"
overall = "✅ PR 통과 — 머지 허용" if (tcr_pass and acc_pass) else "❌ PR 차단 — 품질 기준 미달"
print(f"\n  $ {gate_cmd}")
print(f"  → {overall}")

# ===========================================================================
# 섹션 3: RunTrendAnalyzer — 8주 추세 분석
# ===========================================================================
print("\n\n=== 섹션 3: RunTrendAnalyzer — 8주 추세 분석 ===")

print("""  8주치 결과 파일을 생성하고 추세를 분석한다.
  RunTrendAnalyzer는 results/ 디렉토리의 파일을 시간순으로 읽어
  TCR·Accuracy·P95·비용의 추세를 계산한다.
""")

# 8주치 결과 시뮬레이션 데이터 생성
WEEKLY_DATA = []
base_date = datetime(2026, 2, 24)  # 8주 전

for week_idx in range(8):
    week_date = base_date + timedelta(weeks=week_idx)
    filename = f"weekly_{week_date.strftime('%Y%m%d')}"

    # 드리프트 시뮬레이션:
    # - TCR: 안정적 (90–95%)
    # - Accuracy: 완만한 상승 (70% → 80%)
    # - 비용: 8.6% 증가 (0.033 → 0.036) ← Gate D 이슈
    tcr_val      = 90 + random.uniform(0, 5)
    accuracy_val = 70 + (week_idx * 1.4) + random.uniform(-1, 1)
    cost_usd     = 0.033 + (week_idx * 0.0004) + random.uniform(-0.0002, 0.0002)
    p95_sec      = 85 + random.uniform(-5, 10)

    WEEKLY_DATA.append({
        "week":     week_idx + 1,
        "date":     week_date.strftime("%Y-%m-%d"),
        "filename": filename,
        "tcr":      round(tcr_val, 1),
        "accuracy": round(accuracy_val, 1),
        "cost_usd": round(cost_usd, 5),
        "p95_sec":  round(p95_sec, 1),
    })

print("  8주 추세 데이터:")
print(f"  {'주차':<6} {'날짜':<12} {'TCR':>6} {'Accuracy':>10} {'비용(USD)':>12} {'P95(초)':>8}")
print(f"  {'-'*6} {'-'*12} {'-'*6} {'-'*10} {'-'*12} {'-'*8}")
for w in WEEKLY_DATA:
    cost_trend = "↑" if w["week"] > 4 and w["cost_usd"] > WEEKLY_DATA[0]["cost_usd"] * 1.05 else " "
    print(f"  W{w['week']:<5} {w['date']:<12} {w['tcr']:>5.1f}% {w['accuracy']:>9.1f}% {w['cost_usd']:>11.5f} {cost_trend} {w['p95_sec']:>7.1f}")

# ===========================================================================
# 섹션 4: Gate D 비용 드리프트 발견
# ===========================================================================
print("\n\n=== 섹션 4: Gate D 비용 드리프트 발견 ===")

first_week_cost = WEEKLY_DATA[0]["cost_usd"]
last_week_cost  = WEEKLY_DATA[-1]["cost_usd"]
cost_increase_pct = (last_week_cost - first_week_cost) / first_week_cost * 100

print(f"""
  Gate D CostPredictabilityConfig 경고:

  W1 평균 비용: ${first_week_cost:.5f}
  W8 평균 비용: ${last_week_cost:.5f}
  변화율:       +{cost_increase_pct:.1f}% (8주간)

  → 로그 추적 결과: RAG_MAX_CONTEXT_TOKENS 설정이
    6000 → 8000으로 변경된 W4 커밋에서 비용 상승 시작

  이 드리프트는 TCR이나 Accuracy만 보면 보이지 않는다.
  Gate D의 비용 추세 분석이 없었다면 계속 누적됐을 것이다.

  조치: RAG_MAX_CONTEXT_TOKENS를 6000으로 복원하거나
        ResourceBudgetConfig(max_cost_usd=0.04)로 임계값 업데이트
""")

# RunTrendAnalyzer 시뮬레이션
print("  $ agent-eval trend results/ --window 8 --fail-on-regression")

tcr_values  = [w["tcr"] for w in WEEKLY_DATA]
acc_values  = [w["accuracy"] for w in WEEKLY_DATA]
cost_values = [w["cost_usd"] for w in WEEKLY_DATA]

tcr_regression  = (tcr_values[-1] - tcr_values[0]) < -3.0
acc_regression  = (acc_values[-1] - acc_values[0]) < -3.0
cost_regression = (cost_values[-1] - cost_values[0]) / cost_values[0] > 0.05

print(f"""
  추세 분석 결과:
  TCR:      {tcr_values[0]:.1f}% → {tcr_values[-1]:.1f}%  {'⚠️  REGRESSION' if tcr_regression else '✅ 안정'}
  Accuracy: {acc_values[0]:.1f}% → {acc_values[-1]:.1f}%  {'⚠️  REGRESSION' if acc_regression else '✅ 개선 추세'}
  비용:     ${cost_values[0]:.5f} → ${cost_values[-1]:.5f}  {'⚠️  DRIFT 감지' if cost_regression else '✅ 안정'}

  any_regression: {tcr_regression or acc_regression or cost_regression}
  exit code: {'1 (CI 실패)' if (tcr_regression or acc_regression or cost_regression) else '0 (통과)'}
""")

# ===========================================================================
# 섹션 5: 주간 리뷰 자동화
# ===========================================================================
print("\n=== 섹션 5: 주간 리뷰 자동화 ===")

print("""  weekly_review.py (cron: 매주 월요일 09:00)
  ─────────────────────────────────────────────────────────
  from agent_evaluator.cli.trend import RunTrendAnalyzer

  analyzer = RunTrendAnalyzer(results_dir="results/", window=8)
  report   = analyzer.analyze()

  if report.any_regression:
      send_slack_alert(
          channel="#ai-ops",
          message=f"⚠️ 품질 회귀 감지\\n"
                  f"TCR slope: {report.tcr_trend.slope:+.2f}/run\\n"
                  f"Accuracy slope: {report.accuracy_trend.slope:+.2f}/run",
      )
      create_github_issue(
          title=f"[자동] 품질 회귀 감지 — {datetime.now():%Y-%m-%d}",
          body=str(report.to_dict()),
      )
  else:
      print("✅ 품질 지표 정상 — 다음 주 리뷰 예정")

  # 비용 드리프트 별도 확인 (report.any_regression과 분리 — cost_trend만 개별 체크)
  if report.cost_trend and report.cost_trend.any_regression:
      send_slack_alert(
          channel="#ai-cost",
          message=f"💰 비용 드리프트 감지: slope {report.cost_trend.slope:+.4f}$/run (8주간)\\n"
                  f"RAG_MAX_CONTEXT_TOKENS 설정 확인 권장",
      )
""")

# 실제 주간 리뷰 결과를 ch26 결과에 기록
weekly_monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

for w in WEEKLY_DATA:
    result = create_taskresult(
        task_id=f"weekly_w{w['week']:02d}",
        question=f"W{w['week']} 주간 품질 검증 ({w['date']})",
        response=f"TCR={w['tcr']}%, Accuracy={w['accuracy']}%, Cost=${w['cost_usd']}",
        ground_truth="품질 기준 충족",
        execution_time=w["p95_sec"] / 10,
        task_type="qa",
        metadata={
            "week":          w["week"],
            "date":          w["date"],
            "tcr":           w["tcr"],
            "accuracy":      w["accuracy"],
            "cost_usd":      w["cost_usd"],
            "p95_sec":       w["p95_sec"],
            "cost_drift_pct": round((w["cost_usd"] - WEEKLY_DATA[0]["cost_usd"]) /
                                    WEEKLY_DATA[0]["cost_usd"] * 100, 1),
        },
    
        use_korean_tokenizer=True,
    )
    weekly_monitor.record_task(result)

weekly_report = weekly_monitor.generate_report()
print(f"  8주 요약 리포트:")
print(f"  총 주간 평가: {weekly_report.total_tasks}건")
print(f"  평균 TCR:     {_tcr(weekly_report):.1f}%")
print(f"  평균 Accuracy: {_acc(weekly_report):.1f}%")
print(f"  비용 드리프트: +{cost_increase_pct:.1f}% (W1→W8)")

_wp = weekly_monitor.save_to_file("ch27_cicd_weekly")

# ── 개선된 리포트: 대상별 브리프를 주간 리뷰 메시지로 그대로 쓴다 ────────────
# save_to_file()이 결과 JSON에 쓴 extra_metrics.insights.briefs는 PM·QA·엔지니어
# 각각에게 보낼 3줄 요약이다 — 주간 리뷰 코멘트/슬랙 메시지에 그대로 붙인다.
_ins = (json.loads(Path(_wp).read_text(encoding="utf-8"))
        .get("extra_metrics", {}).get("insights", {}))
_br = _ins.get("briefs") or {}
if _br:
    print("\n  ── insights.briefs (주간 리뷰용 대상별 요약) ──")
    print(f"  PM  : {_br.get('pm', '')}")
    print(f"  QA  : {_br.get('qa', '')}")
    for _line in (_br.get("engineer") or [])[:3]:
        print(f"  ENG : {_line}")
_lg = _ins.get("longitudinal") or {}
_rf = _lg.get("recurring_failures") or []
if _rf:
    print(f"  만성 실패({len(_rf)}건): "
          + ", ".join(f"{x.get('signature')}({x.get('status')})" for x in _rf[:3]))
print("\n  실무 주간 CI:")
print("    agent-eval gate results/ch27_cicd_weekly.json --tcr 80 --digest \\")
print("      --notify slack://hooks.slack.com/services/T/B/X")
print("    agent-eval trend results/ --fail-on-regression")
print("\n결과 저장 완료: results/ch27_cicd_weekly.json  (+ .html)")
print("확인: agent-eval dashboard results/")

print("""
=== Ch27 CI/CD 완성 요약 ===

  3단계 자동화:
    PR 검증    → 골든 데이터셋 50건, ~3분, 실패 시 차단
    야간 평가  → 전체 200건, 이상 감지 시 Slack 알림
    주간 리뷰  → 8주 추세, 회귀 감지 시 이슈 자동 생성

  발견한 드리프트:
    Gate D 비용: +8.6% (8주간) ← RAG_MAX_CONTEXT_TOKENS 6000→8000
    any_regression: TCR/Accuracy는 정상, 비용만 드리프트
    → TCR·Accuracy만 모니터링했다면 영원히 몰랐을 것

  Part VI 완료 — 분석 → 매핑 → 1단계 이식 → 2단계 이식 → CI/CD 자동화
""")
