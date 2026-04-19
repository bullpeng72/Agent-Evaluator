# Chapter 21. 종합 실무 파이프라인

> **이 챕터에서 배우는 것**
> - 개발 → CI → 프로덕션 → 주간 회귀 전체 사이클을 한 그림으로 이해하기
> - 1인 개발자부터 대규모 팀까지 팀 규모별 도입 로드맵
> - 프로덕션 품질 사고 발생 시 즉각 대응 런북(Runbook)
> - Agent-Evaluator 도입 성과를 측정하는 지표 체계
> - 더 발전하기 위한 다음 단계

> **독자별 읽기 가이드**  
> - **👨‍💻 개발자**: §21.1(전체 사이클) → §21.2(팀 규모별 로드맵) 순서로 읽으면 현재 팀 상황에서 어디서부터 시작할지 경로를 찾을 수 있습니다.  
> - **📋 QA 관리자**: §21.1(전체 사이클 이해) → §21.3(품질 사고 런북) → §21.4(도입 성과 지표) 순서로 읽으면 운영 체계 수립과 성과 측정 방법을 파악할 수 있습니다.  
> - **⚙️ DevOps/MLOps**: §21.1 파이프라인 다이어그램 → §21.2 로드맵 중심으로 읽으면 인프라 구성 범위를 결정할 수 있습니다.  
> - **이 챕터는 Part III(개발자 구현)과 Part IV(QA 기준 수립)가 합쳐지는 지점입니다.** 두 파트를 먼저 읽은 뒤 이 챕터로 돌아오면 가장 빠르게 이해됩니다.

---

## 21.1 개발 → CI → 프로덕션 → 주간 회귀 전체 사이클

앞의 챕터에서 각 단계를 개별적으로 살펴봤다. 이제 이 모든 것을 하나의 파이프라인으로 연결하자.

### 전체 파이프라인 흐름

```
[1. 개발]          [2. PR / CI]        [3. 프로덕션]       [4. 주간 회귀]
   │                    │                    │                    │
   ▼                    ▼                    ▼                    ▼
@eval.qa           골든 데이터셋          10% 샘플링           골든 데이터셋
로컬 실행          100개 평가             실시간 스팬          전수 평가
Phoenix            agent-eval gate       Phoenix              compare()로
로컬 연결          PR 코멘트 게시         내부 서버            트렌드 분석
                   임계값 검사            AnomalyDetector      리포트 발송
```

### 단계별 코드 예시

**1단계: 개발 환경**

```python
# dev/run_dev.py
from agent_evaluator import setup_otel, QuickEval

# 로컬 Phoenix 연결 시도 (없어도 동작)
try:
    setup_otel(endpoint="http://localhost:6006", service_name="dev-qa-agent")
    print("Phoenix에 연결되었습니다: http://localhost:6006")
except Exception:
    print("Phoenix 없이 실행합니다. (agent-eval monitor 실행 후 재시도)")

eval = QuickEval("results/", preset="development")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

if __name__ == "__main__":
    agent("한국의 수도는?", ground_truth="서울")
    agent("Python을 만든 사람은?", ground_truth="귀도 반 로섬")
    eval.save()
    print(eval.summary())
```

**2단계: CI 평가 스크립트**

```python
# ci/run_evaluation.py
import json
import sys
from agent_evaluator import QuickEval

def main():
    eval = QuickEval("results/", preset="testing")

    @eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return call_llm(question)

    with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
        dataset = json.load(f)

    for pair in dataset["qa_pairs"][:100]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    eval.save()
    summary = eval.summary()
    print(f"TCR: {summary.get('tcr', 0):.1f}%")
    print(f"Accuracy: {summary.get('accuracy_avg', 0) * 100:.1f}%")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**3단계: 프로덕션 에이전트**

```python
# production/agent.py
import os
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval
from agent_evaluator import SimpleTaskAlertRule

# 내부 Phoenix 서버 연결
otel_endpoint = os.getenv("OTEL_ENDPOINT", "http://phoenix:6006")
setup_otel(endpoint=otel_endpoint, service_name="prod-qa-agent")

monitor = PerformanceMonitor(
    output_dir=os.getenv("EVAL_OUTPUT_DIR", "results/"),
    enable_security_metrics=True,
    auto_save=True,
    auto_save_interval=50,
)

# 품질 저하 즉시 알림 규칙
alert_rule = SimpleTaskAlertRule(
    name="accuracy_drop",
    condition=lambda tr: tr.accuracy_score < 0.5,
    handler=lambda msg, tr: send_slack_alert(f"[ALERT] {msg} — task: {tr.task_id}"),
    severity="warning",
    cooldown=300,  # 5분 쿨다운
)

@agent_eval(
    monitor,
    task_type="qa",
    sample_rate=0.1,              # 10% 샘플링
    flush_every=50,               # 50회마다 저장
    alert_rules=[alert_rule],
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

**4단계: 주간 회귀 스크립트**

```python
# scripts/weekly_regression.py
"""매주 월요일 실행: 전체 골든 데이터셋으로 회귀 테스트 + 트렌드 분석"""
import json
from datetime import datetime
from agent_evaluator import QuickEval

def run_weekly_regression():
    current_eval = QuickEval("results/weekly/")

    @current_eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return call_llm(question)

    with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"[{datetime.now()}] 주간 회귀 테스트 시작 — {len(dataset['qa_pairs'])}개 케이스")

    for pair in dataset["qa_pairs"]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    current_eval.save()

    # 이전 주 결과와 비교
    try:
        prev_eval = QuickEval("results/weekly_prev/")
        comparison = current_eval.compare(prev_eval)
        print(f"TCR 변화: {comparison.get('tcr_delta', 0):+.1f}%")
        print(f"Accuracy 변화: {comparison.get('accuracy_delta', 0):+.2f}")
    except Exception:
        print("이전 주 결과 없음 — 첫 실행입니다.")

    # 임계값 게이팅
    passed = current_eval.gate(
        tcr=80, accuracy=70,
        raise_on_fail=False
    )
    if not passed:
        send_slack_alert("주간 회귀 테스트 실패 — 품질 저하 감지")

if __name__ == "__main__":
    run_weekly_regression()
```

---

## 21.2 팀 규모별 도입 로드맵

모든 팀이 처음부터 완전한 파이프라인을 구축할 필요는 없다. 팀 규모에 맞게 단계적으로 도입하는 것이 현실적이다.

### 1인 개발자 — 1일 도입

목표: 기본 평가 + CI 게이팅

**1시간 안에 완료**:

```bash
pip install agent-evaluator
```

```python
# evaluate.py — 5줄로 시작
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

my_agent("질문1", ground_truth="정답1")
my_agent("질문2", ground_truth="정답2")
eval.save()
eval.gate(tcr=80, accuracy=70)  # 실패 시 sys.exit(1)
```

```yaml
# .github/workflows/gate.yml — 10줄 CI
name: Quality Gate
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install agent-evaluator
      - run: python evaluate.py
      - run: agent-eval gate results/quickeval.json --tcr 80
```

완료 후 얻는 것: 기본 평가 자동화 + CI 게이팅

---

### 소규모 팀 2~5인 — 1주 도입

목표: 알림 + 대시보드 + 회귀 방지

**Day 1~2: 골든 데이터셋 구축**

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# 50개 케이스 수집
for pair in existing_qa_pairs[:50]:
    agent(pair["question"], ground_truth=pair["answer"])

eval.save()
# 높은 점수 케이스 자동 추출
```

```bash
# 골든 데이터셋 자동 빌드 (고가치 케이스 + 실패 케이스 추출)
agent-eval dataset build --source results/ --strategy high_value failure_cases
```

**Day 3: 알림 규칙 설정**

```python
from agent_evaluator import SimpleTaskAlertRule, QuickEval

def send_slack(msg, tr):
    import requests
    import os
    url = os.getenv("SLACK_WEBHOOK_URL")
    if url:
        requests.post(url, json={"text": f"[QA Alert] {msg}"})

accuracy_alert = SimpleTaskAlertRule(
    name="accuracy_drop",
    condition=lambda tr: tr.accuracy_score < 0.6,
    handler=send_slack,
    severity="warning",
    cooldown=300,
)

eval = QuickEval("results/")

@eval(task_type="qa", alert_rules=[accuracy_alert])
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

**Day 4~5: 대시보드 + 주간 리뷰**

```bash
# 대시보드 실행
agent-eval dashboard results/

# 주간 리뷰 스크립트 cron 등록
# 매주 월요일 09:00: python scripts/weekly_regression.py
```

완료 후 얻는 것: 품질 저하 즉시 알림 + 대시보드 시각화 + 주간 회귀 방지

> 📋 **QA 관리자 TIP**: 골든 데이터셋은 처음에 50개로 시작해서 매주 10~20개씩 추가하라. 회귀 케이스(한 번이라도 실패한 케이스)를 반드시 포함시켜라.

---

### 중·대규모 팀 — 1개월 도입

목표: 프로덕션 실시간 모니터링 + 완전한 CI/CD 통합

**Week 1: Phoenix 내부 서버 구축**

```bash
# 내부 서버에 Phoenix 배포
docker run -d \
  --name phoenix \
  -p 6006:6006 \
  -v /data/phoenix:/data \
  arizephoenix/phoenix:latest

# 에이전트에서 내부 Phoenix 연결
# setup_otel(endpoint="http://phoenix.internal:6006", service_name="prod-agent")
```

**Week 2: GitHub Actions CI/CD 완전 통합**

```yaml
# .github/workflows/agent-quality-gate.yml (Chapter 18 참조)
# PR → 평가 → gate → PR 코멘트 자동 게시
```

**Week 3: 5-규칙 알림 + 이상 감지**

```python
from agent_evaluator import PerformanceMonitor, SimpleTaskAlertRule
from agent_evaluator.anomaly import AnomalyDetector

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,
    auto_save=True,
    auto_save_interval=50,
)

# 5개 알림 규칙
rules = [
    SimpleTaskAlertRule("low_accuracy",    lambda tr: tr.accuracy_score < 0.5,     handler=slack_alert, cooldown=300),
    SimpleTaskAlertRule("slow_response",   lambda tr: tr.execution_time > 10.0,    handler=slack_alert, cooldown=60),
    SimpleTaskAlertRule("high_tokens",     lambda tr: tr.tokens_used > 5000,       handler=slack_alert, cooldown=120),
    SimpleTaskAlertRule("task_failure",    lambda tr: not tr.success,              handler=pagerduty_alert, cooldown=60),
    SimpleTaskAlertRule("security_threat", lambda tr: bool(tr.errors),             handler=security_alert, cooldown=30),
]
```

**Week 4: 전담 QA 운영 루틴 확립**

매일 09:00: Phoenix Tracing 대시보드 확인 (전날 실패 케이스)
매주 월요일: 주간 회귀 자동 실행 + 팀 리뷰
매월 1일: 골든 데이터셋 갱신 + 임계값 재검토

완료 후 얻는 것: 프로덕션 실시간 모니터링 + CI/CD 완전 자동화 + 품질 트렌드 관리

> ⚙️ **DevOps TIP**: 1개월 로드맵에서 가장 중요한 것은 Phoenix 내부 서버의 데이터 영속화다. `--working-dir` 옵션으로 SQLite DB 저장 경로를 지정하고, 주기적 백업을 설정하라.

---

## 21.3 프로덕션 품질 사고 대응 런북 (Runbook)

품질 사고는 반드시 발생한다. 중요한 것은 발견했을 때 체계적으로 대응하는 것이다.

### Severity 1 — Critical (서비스에 즉각적 영향)

**트리거**: TCR이 60% 이하로 떨어지거나, 보안 위협이 연속 5건 이상 탐지되는 경우.

```
대응 절차 (목표: 30분 이내 해결 또는 롤백)

Step 1. 즉시 알림 확인 (0~5분)
  - Slack #critical-alerts 채널 확인
  - 알림 내용: task_id, accuracy_score, 오류 메시지

Step 2. Phoenix Tracing에서 실패 스팬 필터 (5~10분)
  - 필터: ae.accuracy_score < 0.5
  - 가장 최근 실패 케이스 10개 검토
  - input.value와 output.value 비교

Step 3. 원인 분석 (10~20분)
  - 모델 변경 여부 확인 (배포 로그 조회)
  - 프롬프트 변경 여부 확인 (Git 커밋 로그)
  - 데이터 분포 변화 여부 (새로운 유형의 질문 급증?)
  - 외부 API 장애 여부 (LLM 공급자 상태 페이지)

Step 4. 이전 버전 롤백 또는 핫픽스 (20~30분)
  - 원인이 코드 변경이면: 이전 버전으로 롤백
  - 원인이 프롬프트면: 이전 프롬프트로 즉시 복구
  - 원인이 외부 장애면: 대기 또는 폴백 모델 전환

Step 5. 회귀 케이스 골든 데이터셋 추가 (사후)
  agent-eval dataset build --source results/ --strategy failure_cases  # 실패 케이스 추출
  # 수동으로 검토 후 골든 데이터셋에 추가
```

```python
# 긴급 진단 스크립트
import json

with open("results/latest.json", encoding="utf-8") as f:
    data = json.load(f)

# 최근 1시간 실패 케이스
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(hours=1)).isoformat()

failures = [
    t for t in data.get("tasks", [])
    if t.get("accuracy_score", 1.0) < 0.5
    and t.get("timestamp", "") >= cutoff
]

print(f"최근 1시간 실패 케이스: {len(failures)}개")
for f in failures[:5]:
    print(f"  [{f.get('task_id')}] {f.get('question', '')[:50]}...")
    print(f"  응답: {f.get('response', '')[:100]}...")
    print(f"  정확도: {f.get('accuracy_score', 0):.2f}")
```

### Severity 2 — Warning (점진적 품질 저하)

**트리거**: 주간 회귀 테스트에서 TCR이 전주 대비 5% 이상 하락하거나, Phoenix Evaluators에서 LLM Judge 점수 트렌드가 3주 연속 하락하는 경우.

```
대응 절차 (목표: 1주 이내 개선)

Step 1. 주간 리뷰에서 발견 (월요일)
  compare()로 어느 시점부터 하락했는지 확인

Step 2. 하락 구간 분석
  - Phoenix Tracing에서 해당 기간 필터링
  - 어떤 task_type에서 하락했는가?
  - 특정 키워드/도메인에서 집중적으로 실패하는가?

Step 3. 프롬프트 개선 사이클
  - 실패 케이스 프롬프트를 Phoenix Playground에서 재현
  - 개선된 프롬프트로 실험
  - 골든 데이터셋에서 검증
  - PR 제출 → CI 게이팅 통과 확인

Step 4. 임계값 재검토
  - 하락이 의도된 변화라면 임계값 조정
  - 하락이 버그라면 코드 수정
```

```python
# compare()로 트렌드 분석
from agent_evaluator import QuickEval

current = QuickEval("results/weekly/current/")
previous = QuickEval("results/weekly/previous/")

comparison = current.compare(previous)
print("지표 변화:")
for metric, delta in comparison.items():
    sign = "+" if delta > 0 else ""
    print(f"  {metric}: {sign}{delta:.2f}")
```

---

## 21.4 Agent-Evaluator 도입 성과 측정

도입의 효과를 객관적으로 측정하기 위한 지표 체계다.

### 도입 전후 비교 지표

| 지표 | 도입 전 | 도입 후 목표 | 측정 방법 |
|------|---------|------------|----------|
| 평가 사이클 시간 | 수동 평가 2~3일 | 자동화 30분 이내 | CI 파이프라인 실행 시간 |
| 프로덕션 품질 사고 | 월 N건 (주관적) | 30% 감소 | 알림 횟수 추적 |
| 모델 교체 의사결정 | 2~3주 (직관) | 1~2일 (데이터 기반) | compare() 결과 활용 |
| 골든 데이터셋 크기 | 0개 | 월 50개 증가 | 데이터셋 레코드 수 |
| 배포 롤백 횟수 | 월 N회 | 50% 감소 | 배포 로그 |

### 정량 지표 추출 코드

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
summary = eval.summary()

metrics = {
    "tcr": summary.get("tcr", 0),
    "accuracy_avg": summary.get("accuracy_avg", 0) * 100,
    "p95_latency": summary.get("p95_latency", 0),
    "total_cost_usd": summary.get("total_cost_usd", 0),
    "quality_avg": summary.get("quality_avg", 0),
    "hallucination_rate": summary.get("hallucination_rate", 0) * 100,
}

print("=== 도입 성과 지표 ===")
for k, v in metrics.items():
    print(f"{k}: {v:.2f}")
```

---

## 21.5 다음 단계 — 더 발전하기

Agent-Evaluator의 핵심 기능을 익혔다면, 다음 단계로 확장할 수 있다.

### Phoenix 커스텀 Evaluator 추가

Phoenix Evaluators 탭에서 팀 고유의 평가 기준을 추가한다.

```
예: "응답이 회사 정책에 부합하는가?"
    "고객 서비스 톤앤매너를 유지하는가?"
    "개인정보를 노출하지 않았는가?"
```

### 멀티모달 에이전트 평가

이미지, 오디오, 비디오를 처리하는 에이전트도 평가할 수 있다.

```python
from agent_evaluator.decorators import agent_eval, EvalMetadata

@agent_eval(monitor, task_type="qa")
def vision_agent(question: str, image_path: str, ground_truth: str = "") -> tuple:
    response = call_vision_llm(question, image_path)
    return response, EvalMetadata(
        extra={
            "image_count": 1,
            "image_path": image_path,
        }
    )
```

### DSPy로 프롬프트 자동 최적화 연계

```python
from agent_evaluator import QuickEval
import dspy

# DSPy 프로그램과 Agent-Evaluator 연동
eval = QuickEval("results/")

@eval(task_type="qa", framework="dspy")
def dspy_agent(question: str, ground_truth: str = "") -> str:
    return dspy_program(question=question).answer
```

DSPy의 최적화 결과를 Agent-Evaluator로 평가하고, 골든 데이터셋에서 검증하는 사이클을 자동화할 수 있다.

### 커스텀 Tracker 개발

팀 고유의 지표가 필요하다면 `BaseTracker`를 상속해 커스텀 트래커를 만들 수 있다.

```python
from agent_evaluator.core.trackers.base import BaseTracker, TaskResult

class CustomerSatisfactionTracker(BaseTracker):
    """고객 만족도 추정 트래커 (응답 길이, 완성도 기반)"""

    def record(self, result: TaskResult) -> None:
        # 응답 길이 기반 만족도 추정 로직
        response_len = len(result.errors[0] if result.errors else "")
        estimated_satisfaction = min(1.0, result.accuracy_score * 1.2)
        self.metrics["satisfaction_scores"].append(estimated_satisfaction)

    def get_summary(self) -> dict:
        scores = self.metrics.get("satisfaction_scores", [])
        return {
            "avg_satisfaction": sum(scores) / len(scores) if scores else 0,
            "sample_count": len(scores),
        }
```

---

## 에필로그 — 품질은 결국 습관이다

이 책을 통해 AI 에이전트 평가의 3개 레이어(기반, 에이전틱, 하이브리드)와 58개 지표(25 Native + 33 Harness Config), CI/CD 통합, 프로덕션 모니터링까지 살펴봤다. 마지막으로 가장 중요한 이야기를 하고 싶다.

### AI 에이전트 평가는 도구가 아니라 문화다

Agent-Evaluator는 도구다. 도구는 잘못 쓰면 소음만 만들어낸다. 중요한 것은 팀이 "우리 에이전트의 품질을 어떻게 정의하고, 어떻게 측정하고, 어떻게 개선할 것인가"에 대해 끊임없이 대화하는 문화다.

처음에는 `QuickEval` 한 줄로 시작해도 된다. 중요한 것은 시작하는 것이다.

```python
# 이것만으로도 충분한 시작이다
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question, ground_truth=""):
    return call_llm(question)

my_agent("첫 번째 질문", ground_truth="첫 번째 정답")
eval.save()
```

### 측정하지 않으면 개선할 수 없다

소프트웨어 엔지니어링에서 유명한 격언이 있다. "You can't improve what you can't measure." 측정하지 않으면 개선할 수 없다. AI 에이전트 품질도 마찬가지다.

오늘 배포한 에이전트가 어제보다 나아졌는지, 지난달보다 나아졌는지 알 수 있는가? 모델을 교체했을 때 실제로 더 좋아졌는지 데이터로 증명할 수 있는가? 프롬프트를 수정했을 때 어떤 케이스에서 개선되고 어떤 케이스에서 후퇴했는지 파악하고 있는가?

이 질문에 "예"라고 답할 수 있는 팀과 "모르겠다"고 답하는 팀의 차이는 시간이 지날수록 커진다.

### Agent-Evaluator를 시작점으로, 팀만의 평가 문화 만들기

모든 팀의 에이전트는 다르다. 고객 서비스 에이전트와 코드 생성 에이전트의 "품질"은 다르게 정의된다. Agent-Evaluator의 58개 지표(25 Native + 33 Harness Config)는 시작점이다. 여기서 팀 고유의 기준을 추가하고, 골든 데이터셋을 쌓고, 임계값을 조정하면서 팀만의 평가 문화를 만들어가라.

한 달 후, 당신의 팀은 이렇게 말할 수 있을 것이다.

"우리 에이전트의 정확도는 지난달 대비 12% 개선됐고, P95 레이턴시는 0.8초 줄었으며, 보안 위협 탐지 0건을 유지하고 있습니다."

그것이 AI 에이전트 품질 문화의 완성이다.

---

## [이 챕터의 핵심]

- **전체 사이클**은 4단계로 구성된다. 개발(로컬 QuickEval), CI(골든 데이터셋 100개 + gate), 프로덕션(10% 샘플링 + 실시간 스팬), 주간 회귀(전수 평가 + compare()). 각 단계를 연결하면 완전한 품질 파이프라인이 된다.

- **팀 규모별 도입**: 1인은 1일 안에 QuickEval + GitHub Actions로 시작한다. 소규모 팀은 1주에 골든 데이터셋 + 알림 + 대시보드를 추가한다. 대규모 팀은 1개월에 Phoenix 내부 서버 + CI/CD 완전 통합 + 전담 QA 루틴을 구축한다.

- **런북은 사전에 준비하라.** Severity 1 사고는 반드시 발생한다. "Phoenix에서 필터링 → 원인 분석 → 롤백 또는 핫픽스 → 회귀 케이스 추가"의 30분 대응 절차를 팀이 공유해야 한다.

- **성과 측정** 지표: 평가 사이클 시간, 프로덕션 사고 건수, 모델 교체 의사결정 속도, 골든 데이터셋 크기. 이 4가지를 정기적으로 추적하면 도입 효과를 객관적으로 증명할 수 있다.

- **품질은 도구가 아니라 습관이다.** Agent-Evaluator는 시작점이다. `QuickEval` 한 줄로 시작해서, 팀 고유의 지표와 기준을 추가하고, 골든 데이터셋을 쌓아가는 과정이 진짜 AI 에이전트 품질 문화다.

---

## 21.7 드리프트 → 재보정 파이프라인

AI 에이전트는 배포 후에도 조용히 성능이 변한다. 모델이 업데이트되거나, 데이터가 달라지거나, 사용 패턴이 변하면 지표가 서서히 하락한다. 이것이 **드리프트(Drift)**다. 단순 모니터링으로는 부족하다. **드리프트를 감지하고 → 원인을 진단하고 → 자동으로 재보정(Recalibration)**하는 파이프라인이 필요하다.

### 4가지 드리프트 유형과 감지 신호

| 드리프트 유형 | 정의 | 감지 신호 (Harness Group) | agent-eval 지표 |
|------------|------|--------------------------|----------------|
| **데이터 드리프트** | 입력 분포 변화 | Group A — TCR 점진적 하락 | `AccuracyEvaluator` score 추세 |
| **개념 드리프트** | 정답의 기준 변화 | Group A — HallucinationRate 상승 | `HallucinationDetector` 추세 |
| **모델 드리프트** | 모델 버전 업데이트 | Group C — Reproducibility 하락 | `RetryCorrectionTracker` 재시도율 |
| **운영 드리프트** | 인프라/부하 변화 | Group D — P95 지연 상승 | `LatencyTracker` P95 추세 |

### 드리프트 감지 파이프라인

```python
# drift_detection.py — 매일 cron으로 실행
from agent_evaluator.cli.trend import RunTrendAnalyzer
import json

analyzer = RunTrendAnalyzer(results_dir="results/", window=14)  # 최근 14일
trends = analyzer.analyze()

# 드리프트 판정 기준
drift_signals = []

if trends.get("accuracy_slope", 0) < -0.02:    # 주당 2% 이상 정확도 하락
    drift_signals.append(("concept_drift", "AccuracyEvaluator", trends["accuracy_slope"]))

if trends.get("tcr_slope", 0) < -0.03:          # 주당 3% 이상 TCR 하락
    drift_signals.append(("data_drift", "TaskCompletionTracker", trends["tcr_slope"]))

if trends.get("p95_latency_slope", 0) > 0.5:   # P95 지연 주당 0.5초 이상 상승
    drift_signals.append(("operational_drift", "LatencyTracker", trends["p95_latency_slope"]))

if drift_signals:
    print(f"🚨 드리프트 감지: {len(drift_signals)}개 신호")
    for drift_type, tracker, slope in drift_signals:
        print(f"   [{drift_type}] {tracker}: slope={slope:+.3f}/week")
    # Slack/이메일 알림 발송
    send_drift_alert(drift_signals)
else:
    print("✅ 드리프트 없음 — 지표 안정")
```

```bash
# 주간 자동 드리프트 감지 (cron)
agent-eval trend results/ --window 14 --fail-on-regression --output-json drift_report.json

# 드리프트 발견 시 임계값 재보정 트리거
if [ $? -ne 0 ]; then
    python scripts/recalibrate_thresholds.py --report drift_report.json
fi
```

### 임계값 재보정 — Wilson Score Interval 적용

드리프트 이후 새 기준선(baseline)을 재설정할 때, 최근 데이터로 Wilson Score 기반 신뢰구간 임계값을 재계산한다:

```python
# recalibrate_thresholds.py
import json
import math

def wilson_lower_bound(successes: int, trials: int, z: float = 1.96) -> float:
    """최근 N회 실행에서 95% 신뢰구간 하한 계산"""
    if trials == 0:
        return 0.0
    p = successes / trials
    denom = 1 + z**2 / trials
    center = p + z**2 / (2 * trials)
    spread = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2))
    return (center - spread) / denom

def recalibrate_from_recent(results_dir: str, window: int = 30) -> dict:
    """최근 window일 결과로 새 임계값 계산"""
    # 최근 결과 로드
    recent_results = load_recent_results(results_dir, days=window)
    
    successes = sum(1 for r in recent_results if r.get("task_completion_rate", 0) >= 0.8)
    trials = len(recent_results)
    
    new_tcr_threshold = wilson_lower_bound(successes, trials) - 0.05  # 5% 마진
    
    print(f"재보정 결과: trials={trials}, TCR 새 임계값={new_tcr_threshold:.1%}")
    return {"tcr": new_tcr_threshold, "recalibrated_at": "2026-04-17"}
```

---

## 21.8 자기개선 루프 — 평가 → 진단 → 개선 3단계

최고 수준의 AI 시스템은 평가 결과를 다시 학습에 활용한다. 이것이 **자기개선 루프(Self-Improvement Loop)**다. Agent-Evaluator의 데이터를 기반으로 프롬프트·파인튜닝·Config을 자동으로 개선하는 3단계 파이프라인을 구성할 수 있다.

```
Stage 1: 지표 하락 감지          Stage 2: 원인 귀속              Stage 3: 개선 액션
─────────────────────         ─────────────────────────      ──────────────────────────
RunTrendAnalyzer              Group별 Tracker 드릴다운         결과에 따른 액션 선택
  ↓                              ↓                              ↓
TCR 하락 감지                  어느 Group이 낮은가?           Group A 낮음 → 프롬프트 개선
정확도 하락 감지               어느 Tracker가 낮은가?         Group D 높음 → 인프라 확장
P95 지연 상승 감지             실패 케이스 패턴 분석           Group E 위반 → 보안 Config 강화
```

### Stage 1 — 지표 하락 감지 (RunTrendAnalyzer)

```python
from agent_evaluator.cli.trend import RunTrendAnalyzer

# 매주 실행 — 최근 4주 추세 분석
analyzer = RunTrendAnalyzer(results_dir="results/", window=28)
trends = analyzer.analyze()

print(f"TCR 추세: {trends.get('tcr_slope', 0):+.3f}/week")
print(f"정확도 추세: {trends.get('accuracy_slope', 0):+.3f}/week")
print(f"P95 지연 추세: {trends.get('p95_latency_slope', 0):+.3f}s/week")

# 개선 필요 여부 판정
needs_improvement = (
    trends.get("tcr_slope", 0) < -0.01 or      # TCR 주당 1% 이상 하락
    trends.get("accuracy_slope", 0) < -0.01     # 정확도 주당 1% 이상 하락
)
```

### Stage 2 — 원인 귀속 (Group별 Tracker 드릴다운)

```python
from agent_evaluator import PerformanceMonitor
import json

# 최근 실패 케이스 로드
with open("results/latest_eval.json") as f:
    eval_data = json.load(f)

tasks = eval_data.get("tasks", [])
failed = [t for t in tasks if not t.get("success", True)]

# Group별 실패 분포 분석
group_failures = {
    "A_목표달성": sum(1 for t in failed if t.get("accuracy_score", 1.0) < 0.5),
    "B_행동무결성": sum(1 for t in failed if len(t.get("tool_calls", [])) == 0 and t.get("task_type") == "tool_use"),
    "D_성능계약": sum(1 for t in failed if t.get("execution_time", 0) > 5.0),
    "E_보안경계": sum(1 for t in failed if t.get("security_violations", 0) > 0),
}

dominant_group = max(group_failures, key=group_failures.get)
print(f"주요 실패 원인: {dominant_group} ({group_failures[dominant_group]}건)")

# 실패 케이스 패턴 추출
failure_patterns = []
for t in failed:
    if t.get("accuracy_score", 1.0) < 0.5:
        failure_patterns.append({
            "question": t.get("question", ""),
            "response": t.get("response", ""),
            "ground_truth": t.get("ground_truth", ""),
            "accuracy": t.get("accuracy_score"),
        })

print(f"분석할 실패 패턴: {len(failure_patterns)}개")
```

### Stage 3 — 개선 액션

원인 귀속 결과에 따라 세 가지 개선 경로 중 하나를 선택한다:

```python
def select_improvement_action(dominant_group: str, failure_patterns: list) -> str:
    """Group별 진단 결과에 따라 개선 액션 선택"""
    
    if dominant_group == "A_목표달성":
        # 프롬프트 개선 — 실패 케이스에서 패턴 추출
        print("→ 액션: 프롬프트 개선")
        print("  1. 실패 케이스 10개를 프롬프트 엔지니어에게 전달")
        print("  2. Few-shot 예시 업데이트")
        print("  3. System prompt에 실패 패턴 대응 지침 추가")
        return "prompt_improvement"
    
    elif dominant_group == "D_성능계약":
        # 인프라 확장 — SLA 위반이 주원인
        print("→ 액션: 인프라 확장 또는 모델 경량화")
        print("  1. 현재 P95: 조회 후 SLAConfig max_p95 재협의")
        print("  2. 응답 캐싱 레이어 검토")
        print("  3. 모델 → 더 빠른 버전으로 교체 검토 (품질 희생 최소화)")
        return "infra_scaling"
    
    elif dominant_group == "E_보안경계":
        # Config 강화 — 보안 위반이 주원인
        print("→ 액션: ThreatSeverityConfig 강화")
        print("  1. max_severity_level 하향 조정 ('medium' → 'low')")
        print("  2. fail_on_violation=True 확인")
        print("  3. InputSanitizationTracker 패턴 업데이트")
        return "security_hardening"
    
    else:
        print(f"→ 액션: {dominant_group} 전문가 리뷰 요청")
        return "manual_review"


# 자기개선 루프 실행
action = select_improvement_action(dominant_group, failure_patterns)
print(f"\n📋 개선 계획 수립 완료: {action}")
print(f"   다음 평가 주기에서 개선 효과 측정 예정")
```

### 자기개선 루프 KPI

개선 루프를 운영하면 아래 지표로 효과를 측정한다:

| KPI | 측정 방법 | 목표 |
|-----|---------|------|
| 드리프트 감지 시간 (MTTD) | 하락 발생 → 감지까지 평균 일수 | < 3일 |
| 개선 적용 시간 (MTTR) | 감지 → 배포까지 평균 일수 | < 7일 |
| 루프당 TCR 개선 | 개선 전후 TCR 변화 | +5% 이상 |
| 재발률 | 동일 원인 재발생 비율 | < 10% |

```python
# 자기개선 KPI 측정
from agent_evaluator.cli.trend import RunTrendAnalyzer

# 개선 전 기준선
before_trends = RunTrendAnalyzer("results/before_improvement/", window=14).analyze()
# 개선 후 측정
after_trends = RunTrendAnalyzer("results/after_improvement/", window=14).analyze()

tcr_improvement = after_trends.get("tcr_mean", 0) - before_trends.get("tcr_mean", 0)
accuracy_improvement = after_trends.get("accuracy_mean", 0) - before_trends.get("accuracy_mean", 0)

print(f"개선 효과:")
print(f"  TCR: {before_trends.get('tcr_mean', 0):.1%} → {after_trends.get('tcr_mean', 0):.1%} ({tcr_improvement:+.1%})")
print(f"  정확도: {before_trends.get('accuracy_mean', 0):.1%} → {after_trends.get('accuracy_mean', 0):.1%} ({accuracy_improvement:+.1%})")
```

---

## 실전 예제

이 챕터의 종합 파이프라인은 `Evaluator_Examples/` 7개 파일 전체를 순서대로 실행하면 재현된다. 각 파일이 개발 → CI → 프로덕션 → 주간 리뷰 사이클의 한 단계를 담당한다.

**파일**: `Evaluator_Examples/01_layer1_all_metrics.py` ~ `07_phoenix_hybrid.py` 전체

**핵심 코드 (출처: `Evaluator_Examples/01~07_*.py` 종합)**

```python
# 출처: Evaluator_Examples/07_phoenix_hybrid.py + 01_layer1_all_metrics.py — 전체 파이프라인 초기화
import socket, os
from agent_evaluator.core.otel.provider import setup_otel
from agent_evaluator import PerformanceMonitor, QuickEval

# 1단계: Phoenix OTEL 설정 (PerformanceMonitor 생성 전)
if socket.create_connection(("localhost", 6006), timeout=2):
    setup_otel(endpoint="http://localhost:6006", service_name="prod-agent")

# 2단계: 모니터 초기화
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    enable_llm_judge=bool(os.getenv("ANTHROPIC_API_KEY")),
    judge_criteria=["accuracy", "safety", "helpfulness"],
    auto_save=True,
    auto_save_interval=100,
)
```

- 전체 파이프라인의 첫 단계는 OTEL 설정 → 모니터 초기화 순서를 지키는 것이다
- `enable_hallucination_detection`, `enable_security_metrics`는 기본값이 `False`이므로 명시적으로 활성화해야 한다
- `judge_criteria`로 G-Eval 스타일 커스텀 평가 기준을 지정하면 LLMJudge가 해당 기준으로 채점한다

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py + 05_streaming_alerts.py — 데코레이터 + 알림 통합
from agent_evaluator import agent_eval, SimpleTaskAlertRule, EvalMetadata
from agent_evaluator.alerts.handlers import AlertRuleBuilder
import json
from pathlib import Path

alert_log = Path("results/alerts.jsonl")

# 알림 규칙 설정
slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: alert_log.open("a").write(
        json.dumps({"rule": "slow", "task": tr.task_id}) + "\n"
    ),
    severity="warning",
    cooldown=60,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    alert_rules=[slow_alert],
    flush_every=50,              # 50건마다 자동 저장
)
def production_agent(question: str, context: str = "", ground_truth: str = "") -> tuple:
    response = f"답변: {question}"
    return response, EvalMetadata(
        tool_calls=["retriever", "llm"],
        expected_tools=["retriever", "llm"],
        extra={"llm.prompts": [f"Q: {question}\nCtx: {context}"]},
    )
```

- `alert_rules`, `flush_every`, `EvalMetadata`를 하나의 데코레이터에 조합해 알림·자동저장·Group B-G 지표를 동시에 처리한다
- `flush_every=50`은 50건마다 `save_to_file()`을 자동 호출해 데이터 손실 위험을 최소화한다

```python
# 출처: Evaluator_Examples/06_operational.py — 골든셋 + 추세 분석 + CI 게이팅
from agent_evaluator.datasets.builder import GoldenSetBuilder
import subprocess

# 골든 데이터셋 자동 관리
builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")

# CLI를 통한 추세 분석 및 CI 게이팅 (subprocess 또는 셸 스크립트에서)
result = subprocess.run(
    ["agent-eval", "trend", "results/", "--fail-on-regression", "--window", "5",
     "--output-json", "trend_report.json"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"[CI FAIL] 품질 회귀 감지:\n{result.stdout}")
    raise SystemExit(1)

# 최종 게이팅
gate_result = subprocess.run(
    ["agent-eval", "gate", "results/ci_evaluation.json",
     "--tcr", "85", "--accuracy", "70"],
    capture_output=True, text=True
)
print(f"게이트 결과: {'통과' if gate_result.returncode == 0 else '실패'}")
```

- `GoldenSetBuilder`는 프로덕션 결과에서 고품질/실패/엣지 케이스를 자동으로 발굴해 다음 회귀 테스트에 활용한다
- `agent-eval trend`와 `agent-eval gate`를 순서대로 실행하면 추세(장기)와 기준치(현재) 양방향을 모두 검사하는 완전한 CI/CD 파이프라인이 완성된다
- 이 패턴이 Ch01~Ch15에서 다룬 모든 기능(Group A-G 지표, 데코레이터, Phoenix OTEL, 알림, 이상 탐지, 골든셋)을 하나로 통합한 종합 파이프라인이다

```bash
# 전체 파이프라인 실행 (개발 단계 시뮬레이션)
python Evaluator_Examples/01_layer1_all_metrics.py   # Group A-D 기반 지표
python Evaluator_Examples/02_layer2_agentic_security.py  # Group B-E 에이전틱·보안
python Evaluator_Examples/03_framework_adapters.py   # 프레임워크 통합
python Evaluator_Examples/04_decorator_quickeval.py  # 데코레이터·QuickEval

# CI/CD 게이팅
agent-eval gate results/*.json --tcr 40 --accuracy 60

# 운영 단계
python Evaluator_Examples/05_streaming_alerts.py     # 실시간 알림
python Evaluator_Examples/06_operational.py          # 운영 인프라

# Phoenix OTEL (API 키 있을 때)
agent-eval monitor &
python Evaluator_Examples/07_phoenix_hybrid.py

# 주간 추이 분석
agent-eval trend results/ --window 10 --output-json weekly.json

# 대시보드 종합 확인
agent-eval dashboard results/
```

**7개 예제 파이프라인 매핑**

| 파일 | 파이프라인 단계 | 핵심 출력 |
|------|---------------|-----------|
| 01_layer1_all_metrics | 개발: Group A-D 검증 | TCR=43.1%, 54개 태스크, p95=5.20s |
| 02_layer2_agentic_security | 개발: Group B-E·보안 검증 | 3개 보안 위협, 14개 태스크 |
| 03_framework_adapters | 통합 테스트: 프레임워크 비교 | 24개 태스크, 4개 프레임워크 TCR 비교 |
| 04_decorator_quickeval | CI: 데코레이터·QuickEval | TCR=57.1%, gate() 실패/성공 |
| 05_streaming_alerts | 운영: 실시간 알림 | alert JSONL, feedback 추적 |
| 06_operational | 운영: 인프라 종합 | AnomalyDetector, CostTracker, GoldenSet |
| 07_phoenix_hybrid | 운영: OTEL·외부 평가 | Phoenix 스팬, DeepEval/Ragas 연동 |

**전체 파이프라인 실행 결과 요약 (v0.8.2 기준)**

```
=== 종합 파이프라인 실행 결과 ===

총 태스크: 01(54) + 02(14) + 03(24) + 04(14) + 05(N) + 06(28) + 07(3) = 137+건
전체 평균 TCR: ~48%  |  전체 평균 정확도: ~0.66

CI 게이트 (--tcr 40 --accuracy 60): ✅ 통과
주간 트렌드: TCR +1.2%, 정확도 +0.008 (개선 중)
보안 위협: 3건 탐지 (02_layer2 기준)
골든 데이터셋: 12개 케이스 추출 (06_operational 기준)

대시보드: http://localhost:8765 — 전체 결과 통합 조회 가능
Phoenix: http://localhost:6006 — OTEL 스팬 시각화 (API 키 필요)
```

> **팀 규모별 시작점**: 1인 개발자는 `04_decorator_quickeval.py`만 실행하고 `agent-eval gate`를 GitHub Actions에 등록하는 것으로 하루 안에 시작할 수 있다. 소규모 팀은 01~06을 순차로 도입하고, 대규모 팀은 07_phoenix_hybrid까지 포함한 전체 파이프라인을 운영한다.
