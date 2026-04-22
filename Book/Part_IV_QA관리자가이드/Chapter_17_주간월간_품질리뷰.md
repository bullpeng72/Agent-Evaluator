# Chapter 17. 주간·월간 품질 리뷰

> **이 챕터에서 배우는 것**
> - 정기 리뷰가 실시간 알림으로는 잡을 수 없는 무엇을 보완하는지 이해한다
> - 주간 품질 리뷰를 5분 안에 자동화하는 스크립트를 작성한다
> - `compare()`와 `ab_test()`로 전주 대비 회귀를 통계적으로 분석하는 방법을 익힌다
> - 골든 데이터셋을 주기별로 갱신하는 실무 루틴을 수립한다
> - Phoenix 대시보드에서 트렌드를 읽는 방법을 파악한다

---

## 17.1 왜 정기 리뷰가 필요한가

실시간 알림과 정기 리뷰는 서로 다른 문제를 해결한다.

**실시간 알림**은 개별 사건을 잡는다. 특정 태스크의 응답시간이 10초를 넘었을 때, 특정 호출에서 보안 위협이 탐지되었을 때 즉각 알려준다. 이벤트 기반이다.

**정기 리뷰**는 트렌드를 잡는다. 2주에 걸쳐 정확도가 78%에서 71%로 조금씩 낮아지는 패턴은 임계값(70%)에 도달하기 전까지는 알림이 발생하지 않는다. 개별 케이스로 보면 각각 정상 범위이지만 전체로 보면 방향이 나쁜 것이다.

**정기 리뷰로만 발견할 수 있는 패턴:**

| 패턴 | 실시간 알림 | 정기 리뷰 |
|------|-----------|---------|
| 임계값 초과 (급격한 하락) | 탐지 가능 | 탐지 가능 |
| 점진적 품질 저하 (주당 -2%) | 놓침 | 탐지 가능 |
| 특정 요일/시간대 패턴 | 놓침 | 탐지 가능 |
| 전주 대비 비용 증가 추이 | 놓침 | 탐지 가능 |
| 모델 업그레이드 효과 측정 | 불가 | 가능 |

정기 리뷰를 자동화하면 추가 공수 없이 이 모든 인사이트를 얻을 수 있다.

> **Harness Gate 연결 관점**: 개별 알림(Chapter 16)이 "나무"라면, 주간 리뷰는 "숲"이다. 각 리뷰 지표가 어느 Gate를 대표하는지 알면, 리뷰 결과를 배포 판단으로 바로 연결할 수 있다.
>
> | 주간 리뷰 지표 | 연관 Harness Gate | 악화 시 배포 판단 |
> |-------------|-----------------|----------------|
> | accuracy 추세 (전주 대비) | **Gate A** 목표달성 | -3% 이상 → 배포 보류 검토 |
> | TCR 추세 | **Gate A** 목표달성 | -5% 이상 → Gate A WARN 예고 |
> | execution_time P95 추세 | **Gate D** 성능계약 | SLA 위반율 상승 → Gate D WARN |
> | 오류율·재시도율 추세 | **Gate C** 신뢰성 | 오류 복구율 하락 → Gate C 악화 |
> | 토큰·비용 추세 | **Gate D** 성능계약 | 예산 초과율 상승 → Gate D WARN |
> | 보안 위협 탐지 누적 | **Gate E** 보안경계 | 1건이라도 → Gate E WARN 즉시 |
>
> 주간 리뷰에서 동일 Gate가 2주 연속 악화 추세이면, 다음 배포 전에 해당 Gate 설정을 개발자와 함께 점검한다.

---

## 17.2 주간 품질 리뷰 — 5분 자동화 스크립트

매주 월요일 아침, 지난 한 주의 평가 결과를 자동으로 분석하는 스크립트다. 코드를 실행하는 것은 개발자가 아니어도 된다 — 결과 요약이 Slack으로 자동 전송된다.

```python
# 출처: Evaluator_Examples/ch17_weekly_review.py, 섹션 2 — QuickEval.replay() + compare() — 전주 대비 변화 비교
"""qa_weekly_review.py — 매주 월요일 자동 실행하는 주간 품질 리뷰 스크립트."""
import json
import os
from datetime import datetime, timedelta
from agent_evaluator import QuickEval

# -------- 설정 --------
RESULTS_DIR = "results/"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
# 이번 주 / 지난 주 결과 파일 경로
THIS_WEEK_FILE = "results/this_week.json"
LAST_WEEK_FILE = "results/last_week.json"
# 회귀 감지 임계값
REGRESSION_THRESHOLD_ACCURACY = -0.03   # -3%
REGRESSION_THRESHOLD_TCR = -0.05        # -5%
REGRESSION_THRESHOLD_LATENCY = 1.0      # +1초
# ----------------------

def send_slack(message: str):
    if SLACK_WEBHOOK_URL:
        import urllib.request
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL, data=data,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    else:
        print(f"[SLACK] {message}")

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== 주간 품질 리뷰 ({today}) ===\n")

    # 이번 주 결과 로드
    eval_this = QuickEval(RESULTS_DIR)
    eval_this.replay(THIS_WEEK_FILE)

    # 이번 주 요약 출력
    summary = eval_this.summary()
    print("[ 이번 주 결과 ]")
    print(f"  TCR:          {summary.get('task_completion_rate', 0)*100:.1f}%")
    print(f"  Accuracy:     {summary.get('accuracy', 0)*100:.1f}%")
    print(f"  Quality:      {summary.get('quality_avg', 0):.2f}/5.0")
    print(f"  P95 Latency:  {summary.get('p95_latency', 0):.2f}초")
    print(f"  Total Cost:   ${summary.get('total_cost_usd', 0):.2f}")
    print(f"  Total Tasks:  {summary.get('total_tasks', 0)}건\n")

    # 전주와 비교
    if os.path.exists(LAST_WEEK_FILE):
        eval_last = QuickEval(RESULTS_DIR)
        eval_last.replay(LAST_WEEK_FILE)

        comparison = eval_this.compare(eval_last)
        print("[ 전주 대비 변화 ]")

        accuracy_delta = comparison.get("accuracy_delta", 0)
        tcr_delta = comparison.get("tcr_delta", 0)
        latency_delta = comparison.get("p95_latency_delta", 0)

        print(f"  Accuracy:    {accuracy_delta:+.1%}")
        print(f"  TCR:         {tcr_delta:+.1%}")
        print(f"  P95 Latency: {latency_delta:+.2f}초\n")

        # 회귀 감지
        regressions = []
        if accuracy_delta < REGRESSION_THRESHOLD_ACCURACY:
            regressions.append(
                f"Accuracy 회귀: {accuracy_delta:+.1%} (기준: {REGRESSION_THRESHOLD_ACCURACY:+.0%})"
            )
        if tcr_delta < REGRESSION_THRESHOLD_TCR:
            regressions.append(
                f"TCR 회귀: {tcr_delta:+.1%} (기준: {REGRESSION_THRESHOLD_TCR:+.0%})"
            )
        if latency_delta > REGRESSION_THRESHOLD_LATENCY:
            regressions.append(
                f"Latency 악화: {latency_delta:+.2f}초 (기준: +{REGRESSION_THRESHOLD_LATENCY}초)"
            )

        # A/B 테스트 통계적 유의성 확인 (scipy 있을 때)
        try:
            ab_result = eval_this.ab_test(eval_last)
            p_value = ab_result.get("p_value", 1.0)
            significant = p_value < 0.05
            print(f"[ 통계적 유의성 ]")
            print(f"  p-value: {p_value:.4f} ({'유의미 (p<0.05)' if significant else '무의미 (p≥0.05)'})\n")
        except Exception:
            significant = None

        # 회귀 감지 시 알림
        if regressions:
            alert_msg = f"*[주간 리뷰 회귀 감지 — {today}]*\n"
            alert_msg += "\n".join(f"  • {r}" for r in regressions)
            if significant is not None:
                alert_msg += f"\n  통계적 유의성: {'있음 (p={p_value:.3f})' if significant else '없음'}"
            send_slack(alert_msg)
            print("[!] 회귀 감지! Slack 알림 전송 완료")
        else:
            ok_msg = (
                f"*[주간 리뷰 정상 — {today}]*\n"
                f"  TCR: {summary.get('task_completion_rate', 0)*100:.1f}%  "
                f"Accuracy: {summary.get('accuracy', 0)*100:.1f}%  "
                f"P95: {summary.get('p95_latency', 0):.1f}초"
            )
            send_slack(ok_msg)
            print("[OK] 정상 범위. Slack 요약 전송 완료")
    else:
        print("[INFO] 지난 주 결과 없음 — 비교 생략")

if __name__ == "__main__":
    main()
```

- `replay()`로 저장된 JSON 파일을 로드해 새 평가 없이도 주간 집계 통계와 비교 결과를 계산할 수 있다
- `compare(eval_last)`는 이번 주와 지난 주의 accuracy·TCR·latency 델타를 반환하고, 회귀 기준을 초과하면 `regressions` 리스트에 추가된다
- Slack Webhook URL이 없을 때는 콘솔 출력으로 fallback되므로 개발 환경에서도 스크립트를 그대로 테스트할 수 있다

**자동 실행 설정 (cron):**

```bash
# 매주 월요일 오전 9시 실행
0 9 * * 1 cd /path/to/project && python qa_weekly_review.py >> logs/weekly_review.log 2>&1
```

- `0 9 * * 1`은 매주 월요일 오전 9시를 의미하는 cron 표현식이다 — 팀 스탠드업 전에 결과가 Slack에 전달되도록 시간을 설정한다
- `>> logs/weekly_review.log 2>&1`로 표준 출력과 오류를 로그 파일에 추가 기록해 실행 이력을 보존한다
- cron 작업은 환경변수를 직접 전달해야 하므로 `SLACK_WEBHOOK_URL`을 crontab에 선언하거나 `.env` 파일로 로드하는 로직을 스크립트에 추가한다

---

## 17.3 전주 대비 회귀 분석 패턴

> 📖 **`compare()` 통계 수식**: `accuracy_delta`, `p95_latency_delta` 등 각 델타 값의 계산 방식과 통계적 해석은 **[Appendix H §H.4](../Appendix/H_알고리즘_수학적_레퍼런스.md)**를 참조하세요.

`compare()` 메서드는 두 `QuickEval` 인스턴스의 지표를 비교해서 델타(변화량)를 반환한다.

### compare() 반환값 구조

```python
from agent_evaluator import QuickEval

eval_this = QuickEval("results/")
eval_this.replay("results/this_week.json")

eval_last = QuickEval("results/")
eval_last.replay("results/last_week.json")

comparison = eval_this.compare(eval_last)

# 주요 필드:
# comparison["accuracy_delta"]        — Accuracy 변화 (예: -0.03 = -3%)
# comparison["tcr_delta"]             — TCR 변화 (예: -0.02 = -2%)
# comparison["p95_latency_delta"]     — P95 Latency 변화 (예: +0.8 = +0.8초)
# comparison["quality_avg_delta"]     — Quality 점수 변화
# comparison["total_cost_usd_delta"]  — 비용 변화 (예: +5.23 = +$5.23)
# comparison["hallucination_rate_delta"] — 환각율 변화
```

- `compare()`는 두 `QuickEval` 인스턴스 모두 `replay()`로 데이터가 로드된 상태에서만 의미 있는 값을 반환한다
- `accuracy_delta = -0.03`은 이번 주 Accuracy가 전주보다 3 퍼센트 포인트 낮아진 것을 의미한다
- `total_cost_usd_delta`로 주간 비용 변화를 추적하면 예산 초과 추세를 조기에 발견할 수 있다

### 회귀 임계값 기준

회귀를 판단하는 기준은 팀마다 다를 수 있지만, 일반적으로 다음을 권장한다:

| 지표 | 회귀 판단 기준 | 이유 |
|------|-------------|------|
| Accuracy | -3% 이상 하락 | 측정 오차 수준이 약 1~2% |
| TCR | -5% 이상 하락 | 일일 변동폭 고려 |
| P95 Latency | +1초 이상 증가 | 사용자 경험에 직접적 영향 |
| Quality | -0.2점 이상 하락 | 5점 척도에서 유의미한 변화 |
| 비용 | +20% 이상 증가 | 예산 계획 영향 |

📋 **QA 관리자 TIP:** `compare()`는 절댓값이 아닌 **비율 변화**를 반환한다. `accuracy_delta = -0.03`은 "이번 주 Accuracy가 전주보다 3 퍼센트 포인트 낮아졌다"는 의미다. 퍼센트 출력 시 `f"{delta:+.1%}"` 형식을 사용하면 `+3.0%` / `-2.5%`처럼 직관적으로 표시된다.

---

## 17.4 A/B 테스트 통계적 유의성

단순히 "이번 주가 전주보다 2% 낮다"는 사실이 의미 있는지는 통계적 유의성을 봐야 한다. 샘플 수가 적으면 2% 차이는 우연일 수 있다.

### ab_test() 반환값 구조

```python
ab_result = eval_this.ab_test(eval_last)

# ab_result["p_value"]        — 유의성 p-값 (0~1)
# ab_result["t_statistic"]    — t-통계량
# ab_result["sample_size_a"]  — 이번 주 태스크 수
# ab_result["sample_size_b"]  — 지난 주 태스크 수
# ab_result["significant"]    — True if p_value < 0.05
```

- `ab_test()`는 내부적으로 `scipy.stats.ttest_ind()`를 사용하므로 `pip install scipy`가 필요하다
- `p_value < 0.05`이면 두 기간의 품질 차이가 통계적으로 유의미하다 — 단순히 `compare()` 델타만 보면 우연한 변동과 실제 회귀를 구분하기 어렵다
- `sample_size_a`와 `sample_size_b`를 함께 확인해 한쪽 기간 샘플이 30건 미만이면 결과 신뢰도가 낮다는 점을 감안해야 한다

### p-value 해석

| p-value | 해석 | 대응 |
|---------|------|------|
| < 0.01 | 매우 유의미 (99% 신뢰) | 반드시 원인 조사 |
| 0.01~0.05 | 유의미 (95% 신뢰) | 원인 조사 권장 |
| 0.05~0.10 | 약한 유의성 | 추이 모니터링 |
| ≥ 0.10 | 유의미하지 않음 | 우연 가능성 높음, 관찰 지속 |

### 충분한 샘플 수 확보

A/B 테스트 통계가 의미 있으려면 최소 30개 이상의 태스크가 필요하다. 주간 태스크 수가 30개 미만이라면 격주 또는 월간 비교로 전환한다.

```python
summary_this = eval_this.summary()
if summary_this.get("total_tasks", 0) < 30:
    print("[WARNING] 샘플 수 부족 — A/B 테스트 결과 신뢰도 낮음")
    print(f"  현재: {summary_this['total_tasks']}개, 권장: 30개 이상")
```

- `summary().get("total_tasks", 0)`으로 현재 평가 파일의 태스크 수를 확인해 A/B 테스트 실행 여부를 판단한다
- 주간 태스크 수가 30건 미만이면 격주 비교 또는 월간 비교로 전환하는 것이 통계적으로 더 신뢰할 수 있다
- 30건 미만 경고를 스크립트에 포함하면 팀이 결과를 과신하지 않도록 방지할 수 있다

📋 **QA 관리자 TIP:** `ab_test()`는 내부적으로 `scipy.stats.ttest_ind()`를 사용한다. scipy가 설치되지 않은 환경에서는 p-value 없이 단순 비교만 반환한다. `pip install scipy`로 설치하면 정확한 통계 검정 결과를 얻을 수 있다.

---

## 17.5 골든 데이터셋 주기별 갱신

골든 데이터셋은 한 번 만들면 끝이 아니다. 서비스가 발전하면 데이터셋도 함께 진화해야 한다. 구식 케이스로 평가하면 현재 에이전트의 실제 성능을 반영하지 못한다.

### 매주: 새로운 우수 케이스 추가

프로덕션에서 이번 주에 높은 점수를 받은 케이스를 골든셋 후보로 추가한다.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/this_week/",      # 평가 결과 디렉토리
    output_dir="data/golden_datasets/",
)

# 이번 주 결과에서 고품질 케이스 추출
# extract()는 source_dir의 JSON 파일들을 자동으로 읽음
candidates = builder.extract(
    strategies=["high_value"],           # accuracy_score ≥ 0.85 케이스
    max_cases=50,
    require_human_review=True,
    min_question_length=10,
)

print(f"이번 주 신규 후보: {len(candidates)}개")

# 후보 저장 (대시보드에서 검토 후 승인)
builder.save_candidates(
    candidates,
    f"candidates_{datetime.now().strftime('%Y%m%d')}.json"
)
```

- `strategies=["high_value"]`는 `accuracy_score >= 0.85`이고 `completion_score >= 0.85`인 케이스를 자동으로 선별한다
- `require_human_review=True`로 설정하면 자동 추출 후 대시보드에서 사람이 검토해 승인할 때까지 골든셋에 반영되지 않는다
- 날짜를 파일명에 포함하면(`YYYY%m%d`) 주차별 후보 파일을 구분해 관리할 수 있다

대시보드에서 후보를 검토한 후 일괄 승인:

```bash
# 대시보드 실행
agent-eval dashboard

# http://localhost:8765 접속
# → Golden Datasets 탭 → Candidates → Bulk Approve
```

- 대시보드 Golden Datasets 탭에서 각 후보 케이스의 질문, 응답, 점수를 확인하고 개별 또는 일괄 승인할 수 있다
- Bulk Approve는 검토된 후보 전체를 골든셋에 한 번에 추가해 주간 루틴을 빠르게 완료할 수 있게 한다
- 승인된 케이스는 다음 분기 회귀 테스트의 기준선이 되므로 신중하게 검토한다

또는 CLI로 직접 추출:

```bash
agent-eval dataset build results/this_week/ --min-score 0.85
```

### 매월: 구식 케이스 검토 및 교체

한 달 이상 지난 케이스는 현재 서비스와 맞지 않을 수 있다. 월간 리뷰 때 오래된 케이스를 점검한다.

```python
import json
from datetime import datetime, timedelta

# 골든셋 로드
with open("data/golden_datasets/golden_v2.json") as f:
    golden_cases = json.load(f)

# 30일 이상 된 케이스 필터
cutoff = datetime.now() - timedelta(days=30)
old_cases = [
    c for c in golden_cases
    if datetime.fromisoformat(c.get("created_at", "2020-01-01")) < cutoff
]

print(f"30일 이상 된 케이스: {len(old_cases)}개")
print("월간 리뷰에서 적절성 검토 권장")

# 검토 후 삭제할 케이스 ID 목록으로 새 버전 생성
cases_to_remove = {"case_001", "case_005"}  # 검토 후 결정
new_golden = [c for c in golden_cases if c["id"] not in cases_to_remove]
print(f"갱신 후 케이스: {len(new_golden)}개")
```

- `created_at` 필드를 기준으로 30일 이상 된 케이스를 자동으로 추려내 월간 검토 작업을 구조화할 수 있다
- 삭제 대상 ID를 `cases_to_remove` 집합으로 관리하면 변경 이력을 코드 커밋 메시지에 남길 수 있다
- 갱신된 케이스 수를 출력해 골든셋 규모가 줄어드는 추세이면 신규 케이스 추출을 늘려야 한다는 신호로 삼는다

### 분기: 전체 데이터셋 재검토

분기마다 골든셋 전체를 현재 에이전트로 재평가해서 점수가 크게 변한 케이스를 찾는다.

```python
import json
from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

# GoldenSetBuilder에는 load_golden() 메서드가 없으므로 직접 JSON 로드
with open("data/golden_datasets/golden_v2.json", encoding="utf-8") as f:
    golden_cases = json.load(f)
if isinstance(golden_cases, dict):
    golden_cases = golden_cases.get("items", golden_cases.get("qa_pairs", []))

eval_q = QuickEval("results/quarterly/")

@eval_q.qa
def agent(question: str, ground_truth: str = "") -> str:
    return production_agent(question)

# 전체 골든셋으로 평가
for case in golden_cases:
    agent(case["question"], ground_truth=case["answer"])

eval_q.save("quarterly_regression")

# 분기 리뷰 임계값: 회귀 테스트는 기준 더 엄격하게
eval_q.gate(tcr=90, accuracy=75)
```

- 골든셋 JSON 구조는 `items` 또는 `qa_pairs` 키를 사용할 수 있으므로 두 경우를 모두 처리하는 `get()` 체인을 사용한다
- 분기 회귀 테스트는 평상시보다 엄격한 임계값(`tcr=90, accuracy=75`)을 사용해 누적된 품질 저하를 확인한다
- `eval_q.gate()`가 exit 1을 반환하면 분기 배포 계획을 재검토해야 한다는 신호다

---

## 17.6 Phoenix 대시보드로 트렌드 읽기

Phoenix(Arize)는 OTEL 스팬을 수집해서 시계열로 시각화한다. `setup_otel()`을 설정해두면 모든 평가 결과가 자동으로 Phoenix에 전송된다.

```python
from agent_evaluator import setup_otel, QuickEval
from agent_evaluator.decorators import agent_eval

# OTEL 설정 — 이 한 줄이 모든 스팬을 Phoenix로 전송
setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-production-agent"
)

eval = QuickEval("results/")
# ... 이후 모든 평가가 Phoenix에 자동 기록
```

- `setup_otel()`은 `PerformanceMonitor` 생성 전에 호출해야 한다 — 순서가 바뀌면 스팬이 Phoenix에 전송되지 않는다
- `service_name`은 Phoenix UI에서 서비스를 구분하는 식별자로 사용된다 — 여러 에이전트를 운영할 때 고유한 이름을 지정한다
- `endpoint`에는 `/v1/traces` 경로를 포함하지 않는다 — SDK가 내부적으로 경로를 붙이므로 이중 경로 오류가 발생한다

### Tracing 탭 — 실패 케이스 추적

Phoenix Tracing 탭의 필터 표현식으로 문제 케이스를 찾는다.

```
# 정확도 낮은 QA 케이스
ae.accuracy_score < 0.7 AND ae.task_type = "qa"

# 지난 7일 내 환각이 탐지된 스팬
ae.hallucination_detected = True

# LangChain에서 5초 이상 걸린 호출
ae.framework = "langchain" AND ae.execution_time > 5.0

# 도구를 5개 이상 호출한 에이전트
ae.tool_calls_count >= 5
```

- `ae.` 접두사는 Agent-Evaluator가 OTEL 스팬에 추가하는 커스텀 속성을 의미한다
- `AND` 연산자로 여러 조건을 결합하면 "느리고 부정확한" 케이스처럼 복합적인 문제 패턴을 정밀하게 찾을 수 있다
- 환각 탐지 필드(`ae.hallucination_detected`)는 `enable_hallucination_detection=True` 또는 `rag_mode=True`가 설정된 태스크에서만 생성된다

실패 케이스를 클릭하면 입력(질문), 출력(응답), 정답, 실행 시간, 토큰 사용량을 한 화면에서 볼 수 있다.

### Evaluators 탭 — LLM Judge 트렌드 시각화

`llm_judge=LLMJudgeConfig()`로 평가한 결과는 Evaluators 탭에서 트렌드 차트로 확인할 수 있다.

- completeness, relevance, factual_consistency 3가지 차원의 주간 트렌드
- 점수 분포 히스토그램으로 "대부분은 괜찮은데 특정 케이스만 나쁜지" 확인

Phoenix에서 주간 트렌드를 읽는 5분 루틴:

1. Tracing 탭 → `ae.accuracy_score < 0.7` 필터 → 이번 주 실패 케이스 카운트 확인
2. Tracing 탭 → 시계열 뷰 → Accuracy와 Latency 추이 확인
3. Evaluators 탭 → LLM Judge 주간 평균 변화 확인
4. Datasets 탭 → 골든셋 테스트 결과 확인

---

## 17.7 QA 운영 주기표 — 완전판

이 표 하나를 팀 위키에 올려두면 누가 언제 무엇을 해야 하는지 명확해진다.

| 주기 | 작업 | 담당 | 도구 | 예상 소요시간 |
|------|------|------|------|-------------|
| **매 배포** | CI 게이팅 통과 확인 | 자동 | GitHub Actions + `agent-eval gate` | 자동 (5분) |
| **매일** | 대시보드 5분 점검 | 온콜 담당자 | 대시보드 `/api/stats`, `/anomaly` | 5분 |
| **매주 월요일** | 주간 리뷰 스크립트 실행 | QA 매니저 | `qa_weekly_review.py` | 자동 (5분) |
| **매주 월요일** | 골든셋 신규 후보 추출 | QA 매니저 | `agent-eval dataset build` | 10분 |
| **매월 1일** | 임계값 재검토 및 갱신 | QA 매니저 | `generate_gate_config()` | 15분 |
| **매월 1일** | SLA 문서 버전 업 | QA 매니저 | 팀 위키 | 10분 |
| **분기 첫째 주** | 골든셋 전체 재검토 | QA + 개발 | GoldenSetBuilder | 2시간 |
| **분기 첫째 주** | 임계값 대폭 재검토 | QA + 개발 | `generate_gate_config()` + 팀 리뷰 | 1시간 |

**자동화 우선순위:**

1. CI 게이팅은 처음부터 완전 자동화 (매 PR마다)
2. 주간 리뷰는 cron으로 자동 실행 + Slack 요약 전송
3. 골든셋 추출은 CLI 명령 하나로 자동화
4. 임계값 갱신과 SLA 문서화만 사람이 검토

---

## 17.8 월간 품질 보고서 작성 가이드

월간 보고서는 팀 전체와 경영진을 위한 커뮤니케이션 도구다. 기술적 세부사항보다 비즈니스 임팩트에 집중해야 한다.

### HTML 보고서 자동 생성

`monitor.save_to_file()` 또는 `eval.save()` 호출 시 JSON과 함께 HTML 보고서가 자동으로 생성된다. 이 HTML 파일은 독립 실행형이므로 이메일에 첨부하거나 팀 위키에 올릴 수 있다.

```python
from agent_evaluator import QuickEval

# 한 달치 결과를 replay
eval_monthly = QuickEval("results/")
eval_monthly.replay("results/april_2026.json")

# HTML 보고서 생성
eval_monthly.save("monthly_report_april_2026")
# → results/monthly_report_april_2026.json
# → results/monthly_report_april_2026.html  ← 이 파일을 공유

print("보고서 생성 완료: results/monthly_report_april_2026.html")
```

- `replay()`로 월간 집계 JSON을 로드한 후 `save()`를 호출하면 JSON과 HTML 보고서가 동시에 생성된다
- HTML 파일은 모든 차트와 지표를 포함한 독립 실행형 파일이므로 별도 서버 없이 이메일 첨부나 팀 위키 업로드로 공유할 수 있다
- 파일명에 연월을 포함(`april_2026`)하면 월별 보고서 이력을 디렉토리에서 쉽게 조회할 수 있다

### 월간 보고서 주요 포함 항목

| 항목 | 출처 | 핵심 질문 |
|------|------|---------|
| 월간 TCR/Accuracy 추세 | `/timeline?granularity=day` | 전월 대비 개선/악화? |
| 비용 추이 | `/cost/trend?granularity=day` | 예산 내에 있는가? |
| 보안 위협 건수 | `/api/stats` → security_incidents_count | 이번 달 위협 건수는? |
| 골든셋 회귀 테스트 결과 | 주간 리뷰 스크립트 출력 | 회귀가 발생했는가? |
| 다음 달 개선 계획 | QA 팀 판단 | 어떤 지표를 개선할 것인가? |

### 월간 보고서 작성 예시 스크립트

```python
"""monthly_report.py — 월간 품질 보고서 자동 생성."""
import os
from datetime import datetime
from agent_evaluator import QuickEval

MONTH = datetime.now().strftime("%Y_%m")
RESULTS_FILE = f"results/monthly_{MONTH}.json"
OUTPUT_NAME = f"monthly_report_{MONTH}"

def main():
    if not os.path.exists(RESULTS_FILE):
        print(f"[ERROR] 결과 파일 없음: {RESULTS_FILE}")
        return

    eval_m = QuickEval("results/")
    eval_m.replay(RESULTS_FILE)

    summary = eval_m.summary()

    print(f"\n=== {MONTH} 월간 품질 보고서 ===")
    print(f"  총 평가 태스크:  {summary.get('total_tasks', 0):,}건")
    print(f"  TCR:            {summary.get('task_completion_rate', 0)*100:.1f}%")
    print(f"  Accuracy:       {summary.get('accuracy', 0)*100:.1f}%")
    print(f"  Quality:        {summary.get('quality_avg', 0):.2f}/5.0")
    print(f"  P95 Latency:    {summary.get('p95_latency', 0):.2f}초")
    print(f"  총 비용:         ${summary.get('total_cost_usd', 0):.2f}")
    print(f"  환각 발생률:     {summary.get('hallucination_rate', 0)*100:.1f}%")

    # HTML 보고서 생성
    eval_m.save(OUTPUT_NAME)
    print(f"\n보고서 저장 완료:")
    print(f"  JSON: results/{OUTPUT_NAME}.json")
    print(f"  HTML: results/{OUTPUT_NAME}.html")

if __name__ == "__main__":
    main()
```

- `MONTH = datetime.now().strftime("%Y_%m")`으로 월별 파일명을 자동 생성해 스크립트를 수정 없이 매달 재사용할 수 있다
- `hallucination_rate`는 `enable_hallucination_detection=True`가 설정된 평가 파일에서만 유의미한 값이 나온다
- 스크립트를 cron에 등록해 매월 1일 자동 실행하면 경영진 보고용 월간 리포트가 사람 개입 없이 생성된다

📋 **QA 관리자 TIP:** 월간 HTML 보고서를 생성한 후 팀 이메일로 공유할 때는 파일을 직접 첨부하는 것이 좋다. HTML 파일 안에 차트를 포함한 모든 데이터가 자기 완결적으로 포함되어 있어서 별도 서버 없이 브라우저에서 바로 열 수 있다.

---

## 이 챕터의 핵심

- **정기 리뷰는 트렌드를 잡는다** — 실시간 알림이 개별 사건을 감지한다면, 주간/월간 리뷰는 점진적 품질 저하와 장기 추이를 발견한다
- **자동화가 핵심** — `qa_weekly_review.py` 스크립트를 cron에 등록해 매주 월요일 자동 실행하고 Slack으로 요약을 받으면 추가 공수 없이 주간 리뷰가 완성된다
- **compare() + ab_test()로 과학적 판단** — 전주 대비 델타를 보고, A/B 테스트 p-value로 변화가 통계적으로 유의미한지 확인해야 알람 피로 없이 정확한 의사결정을 할 수 있다
- **골든셋은 살아있는 자산** — 매주 신규 케이스 추가, 매월 구식 케이스 정리, 분기마다 전체 재검토하는 루틴이 회귀 테스트의 신뢰도를 유지한다
- **QA 운영 주기표** — "매 배포(자동) → 매일(5분) → 매주(자동) → 매월(15분) → 분기(2시간)" 주기표 하나로 전체 QA 운영 체계가 잡힌다

---

## 실전 예제

`ch17_weekly_review.py`는 `RunTrendAnalyzer`·`QuickEval.compare()`·`ImplicitFeedbackTracker`를 조합해 주간/월간 리뷰를 자동화하는 패턴을 보여준다. `agent-eval trend`는 여러 결과 파일에 걸친 시계열 추이를 분석해 주간 리뷰 보고서를 자동화한다.

**기본 예제**: `Evaluator_Examples/ch17_weekly_review.py`

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch17_weekly_review.py, 섹션 1 — RunTrendAnalyzer 추세 분석
from agent_evaluator.cli.trend import RunTrendAnalyzer

analyzer = RunTrendAnalyzer(
    results_dir="results/",
    pattern="*.json",
    window=10,           # 최근 10개 파일 분석
    slope_threshold=0.3, # 이 값 이상의 기울기를 회귀로 판정
)
report = analyzer.analyze()

print(f"분석 파일 수: {len(report.runs)}개")
print(f"회귀 감지:    {'있음' if report.any_regression else '없음'}")

# RunTrendReport는 개별 속성으로 지표를 제공한다
for name, trend in [
    ("tcr",          report.tcr_trend),
    ("accuracy",     report.accuracy_trend),
    ("latency",      report.latency_trend),
    ("cost",         report.cost_trend),
]:
    if trend is None:
        continue
    direction = "↑" if trend.slope > 0 else "↓" if trend.slope < 0 else "→"
    print(f"  {name}: slope={trend.slope:+.3f}/run  {direction}  "
          f"{'[REGRESS]' if trend.is_regression else '[stable]'}")

if report.any_regression:
    import sys
    sys.exit(1)  # CI/CD 파이프라인에서 배포 차단
```

- `RunTrendAnalyzer`는 결과 디렉토리의 JSON 파일들을 수정 시각 순으로 정렬해 최근 N개를 분석한다
- `slope`는 파일 1개당 변화량으로, `accuracy_trend.slope = -3.0`이면 파일마다 정확도가 3pp씩 하락하는 추세다
- `report.any_regression`이 `True`이면 `slope_threshold` 이상의 하락 기울기를 가진 지표가 있다는 의미다

```python
# 출처: Evaluator_Examples/ch17_weekly_review.py, 섹션 2 — QuickEval.compare() 전주 대비 비교
from agent_evaluator import QuickEval

eval_last = QuickEval("results/")
eval_last.replay("results/last_week.json")   # 지난 주 결과 파일 로드

eval_this = QuickEval("results/")
eval_this.replay("results/this_week.json")   # 이번 주 결과 파일 로드

# compare() → {"self": {...}, "other": {...}, "delta": {"tcr": N, "accuracy": N, "avg_latency": N}}
# summary() → {"tcr": N%, "accuracy": N%, "p95_latency": N초, ...}  (tcr·accuracy는 0~100 단위)
comparison = eval_this.compare(eval_last)
delta = comparison["delta"]
print(f"Accuracy:    {delta.get('accuracy', 0):+.1f}pp")    # 퍼센트 포인트
print(f"TCR:         {delta.get('tcr', 0):+.1f}pp")
print(f"Avg Latency: {delta.get('avg_latency', 0):+.2f}초")

# 통계적 유의성 검증 (pip install scipy 필요)
# ab_test() → {"p_value", "significant", "sample_sizes": {"self": N, "other": N}, ...}
ab_result = eval_this.ab_test(eval_last)
print(f"p-value: {ab_result['p_value']:.4f}  "
      f"{'유의미' if ab_result.get('significant') else '무의미'}")
```

- `replay()`는 저장된 JSON 파일을 로드해 새 평가 실행 없이도 통계와 비교 결과를 계산한다
- `compare()["delta"]["accuracy"]`가 음수이면 이번 주 정확도가 전주보다 하락한 것으로, 단위는 퍼센트 포인트(pp)다
- `ab_test()["significant"]`가 `True`이면 차이가 통계적으로 유의미해 우연 변동이 아닌 실제 회귀임을 의미한다

```python
# 출처: Evaluator_Examples/ch17_weekly_review.py, 섹션 3 — ImplicitFeedbackTracker 주간 집계
from agent_evaluator import ImplicitFeedbackTracker

tracker = ImplicitFeedbackTracker()
# 긍정 feedback_type: copy, thumbs_up, save, share, follow_up_depth
# 부정 feedback_type: regenerate, thumbs_down, abandon, correction
tracker.record(task_id="t001", feedback_type="copy")
tracker.record(task_id="t002", feedback_type="regenerate")

# get_stats() → {"total", "positive_count", "negative_count",
#                "positive_rate", "regenerate_rate", "type_distribution"}
stats = tracker.get_stats()
print(f"긍정율:       {stats['positive_rate']:.1f}%")
print(f"재생성율:     {stats['regenerate_rate']:.1f}%")   # 낮을수록 좋음
print(f"유형 분포:    {stats['type_distribution']}")
```

- `feedback_type`은 사전 정의된 유형만 허용된다: `copy`, `thumbs_up`, `save`, `share`, `follow_up_depth`(긍정), `regenerate`, `thumbs_down`, `abandon`, `correction`(부정)
- `regenerate_rate`가 높으면 사용자가 응답에 불만족해 재생성을 자주 요청하고 있음을 의미한다
- `positive_rate`는 전체 피드백 중 긍정 비율로, 주간 추이를 추적하면 품질 인식 변화를 조기 발견할 수 있다

```bash
# 출처: agent-eval trend CLI — 주간·월간 추세 리포트
# results/ 디렉토리의 최근 10개 평가 결과 추세 분석
agent-eval trend results/

# 최근 4주 데이터만 분석
agent-eval trend results/ --window 4

# 추세 분석 결과를 JSON으로 저장 (주간 리포트 자동화)
agent-eval trend results/ --output-json weekly_trend.json

# 연속 하락(회귀) 감지 시 exit 1 반환 — CI 파이프라인 연동
agent-eval trend results/ --fail-on-regression
```

- `agent-eval trend`는 TCR·정확도·P95 지연시간·환각률 4개 지표의 선형 기울기(slope)를 계산해 추세를 판단한다
- `--window N`으로 분석 범위를 지정하면 특정 기간(주간/월간)의 변화만 추적할 수 있다
- `--output-json`으로 저장한 결과를 스크립트로 처리하면 주간 리포트 생성을 완전 자동화할 수 있다

```bash
# 운영 데이터 생성 후 주간 추이 분석
python Evaluator_Examples/ch17_weekly_review.py

# 주간 추이 분석 (results/ 에 쌓인 파일들)
agent-eval trend results/ --window 10 --output-json weekly_trend.json
```

**예제 구성**

| 도구 | 내용 | 주간/월간 리뷰 연결 |
|------|------|---------------------|
| ch10_group_g (섹션 1) | `evaluation_session` 자동 저장 | 매일 JSON 파일 자동 생성 |
| ch11_eval_data (섹션 5) | `GoldenSetBuilder` 케이스 마이닝 | 주간 골든셋 확장 자동화 |
| `agent-eval trend` | slope 기반 추이 분석 | TCR·정확도 하락 자동 감지 |

**실행 결과 (v0.8.4 기준)**

```
# agent-eval trend results/ --window 10
분석 파일: 10개 | 분석 기간: 2026-04-06 ~ 2026-04-13

지표       현재값    변화율    방향
TCR        46.1%    -2.3%    ↓ 회귀 (slope=-0.023)
정확도     0.681    +0.012   ↑ 개선
P95 레이턴시 3.2s   +0.4s    ↓ 회귀 (slope=+0.041)
환각률     0.12     -0.01    ↑ 개선

결론: TCR·레이턴시 회귀 감지 — 주간 리뷰에서 원인 분석 필요
```

> **자동화 패턴**: `agent-eval trend results/ --fail-on-regression`을 매주 월요일 새벽 cron에 등록하면 주간 리뷰 전에 자동으로 회귀 여부를 확인하고, 회귀 감지 시 exit 1로 팀에 알린다. `--output-json`으로 저장된 JSON을 Slack bot에 연결하면 주간 품질 보고서가 자동 발송된다.

---

### `ch16_alerts.py` — 주간 품질 리뷰 데이터 수집

`ImplicitFeedbackTracker`의 주간 집계와 `StreamingEvaluator`의 윈도우 통계를 결합해 주간 리뷰 보고서를 자동 생성한다:

```python
# 출처: Evaluator_Examples/ch17_weekly_review.py, 섹션 3 — ImplicitFeedbackTracker — 사용자 암묵적 피드백 주간 집계
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/", enable_transparency=True)

# 한 주간 수집된 암묵적 피드백 통계 조회
# (monitor.record_implicit_feedback()으로 주간 내내 수집된 데이터 사용)
try:
    fb_stats = monitor.feedback_tracker.get_stats()
    positive = fb_stats.get("positive_count", 0)
    negative = fb_stats.get("negative_count", 0)
    total    = fb_stats.get("total", 0)
    pos_rate = positive / total if total else 0

    print(f"주간 사용자 반응 요약:")
    print(f"  긍정(thumbs_up·save·share): {positive}건 ({pos_rate:.0%})")
    print(f"  부정(regenerate·abandon·thumbs_down): {negative}건 ({1-pos_rate:.0%})")

    # 부정 비율 > 30%이면 품질 검토 필요
    if negative / total > 0.3:
        print("  ⚠️  부정 피드백 30% 초과 — InstructionConfig 재검토 권장")
except Exception:
    print("  피드백 트래커 데이터 없음 — record_implicit_feedback() 호출 필요")

# 주간 save_to_file로 리뷰 보고서 생성
monitor.save_to_file("weekly_review")
```

- `monitor.feedback_tracker.get_stats()`의 `positive_count`는 `thumbs_up`·`save`·`share`·`copy`, `negative_count`는 `regenerate`·`thumbs_down`·`abandon`·`correction`을 집계한다
- 주간 리뷰 시 `save_to_file("weekly_YYYY_WW")`로 주 번호를 포함한 파일명을 사용하면 대시보드에서 주차별 비교가 가능하다
- 부정 피드백 비율 > 30% → Gate A InstructionConfig 파라미터 재검토 신호
- 부정 피드백 비율 > 50% → 전면적 프롬프트 개선 및 Ground Truth 재수집 필요

```bash
python Evaluator_Examples/ch16_alerts.py   # 암묵적 피드백 수집 시연
python Evaluator_Examples/ch10_group_g.py        # AnomalyDetector 주간 이상 탐지 시연
```
