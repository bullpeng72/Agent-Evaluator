# Chapter 11. 알림 시스템 운영

> **이 챕터에서 배우는 것**
> - `AlertRuleBuilder`의 5종 팩토리 메서드로 표준 알림 규칙을 빠르게 설정하는 방법을 익힌다
> - `SimpleTaskAlertRule`로 커스텀 조건 알림을 만들고 단위 테스트로 검증하는 법을 배운다
> - Slack, 이메일, Webhook 핸들러를 실무 수준으로 연결하는 완전한 코드를 확인한다
> - 쿨다운 전략으로 알림 피로를 방지하는 원칙을 이해한다
> - `AnomalyDetector`와 `AdaptivePolicy`로 이상 탐지 및 비용 자동 제어를 구현한다

---

## 11.1 AlertRuleBuilder — 5종 팩토리 메서드

`AlertRuleBuilder`는 가장 흔히 필요한 알림 규칙을 한 줄로 생성하는 팩토리 클래스다. 5가지 정적 메서드를 제공한다.

```python
from agent_evaluator import AlertRuleBuilder, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")
```

### when_accuracy_below — 정확도 하한 알림

```python
accuracy_rule = AlertRuleBuilder.when_accuracy_below(
    threshold=0.70,              # accuracy_score < 0.70 이면 발동
    handler=lambda msg, tr: print(f"[WARNING] 정확도 하락: {msg}"),
    severity="warning",
    cooldown=300,                # 5분 쿨다운
)
```

### when_latency_above — 응답시간 상한 알림

```python
latency_rule = AlertRuleBuilder.when_latency_above(
    threshold_seconds=5.0,       # execution_time > 5.0초 이면 발동
    handler=lambda msg, tr: print(f"[WARNING] 응답 지연: {msg}"),
    severity="warning",
    cooldown=60,                 # 1분 쿨다운
)
```

### when_completion_below — 완료율 하한 알림

```python
completion_rule = AlertRuleBuilder.when_completion_below(
    threshold=0.80,              # completion_score < 0.80 이면 발동
    handler=lambda msg, tr: print(f"[ERROR] 완료율 하락: {msg}"),
    severity="error",
    cooldown=120,
)
```

### when_error — 오류 발생 알림

```python
error_rule = AlertRuleBuilder.when_error(
    handler=lambda msg, tr: print(f"[ERROR] 태스크 오류: {msg}"),
    severity="error",
    cooldown=60,
)
```

`tr.errors`가 비어 있지 않으면 발동한다. 예외 메시지와 함께 태스크 ID가 핸들러에 전달된다.

### when_tool_calls_exceed — 도구 호출 횟수 상한 알림

```python
tool_rule = AlertRuleBuilder.when_tool_calls_exceed(
    count=10,                    # tool_calls 횟수 > 10 이면 발동
    handler=lambda msg, tr: print(f"[WARNING] 과도한 도구 호출: {msg}"),
    severity="warning",
    cooldown=180,
)
```

### 데코레이터에 알림 규칙 적용

생성한 규칙을 `alert_rules` 파라미터로 데코레이터에 전달한다.

```python
@agent_eval(monitor, task_type="qa",
            alert_rules=[accuracy_rule, latency_rule, error_rule])
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

`QuickEval`에서도 동일한 방식으로 적용한다:

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval(task_type="qa", alert_rules=[accuracy_rule, latency_rule])
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 11.2 SimpleTaskAlertRule — 커스텀 조건 알림

`AlertRuleBuilder`가 제공하지 않는 조건이 필요할 때는 `SimpleTaskAlertRule`로 완전히 커스텀할 수 있다.

```python
from agent_evaluator import SimpleTaskAlertRule
```

### 단일 조건 알림

```python
# 토큰 사용량이 4,000개를 초과하면 알림
# tokens_used는 Dict[str, int] — {"input": N, "output": M, "total": T} 구조
token_rule = SimpleTaskAlertRule(
    name="high_token_usage",
    condition=lambda tr: tr.tokens_used.get("total", 0) > 4000,
    handler=lambda msg, tr: print(f"[WARNING] 토큰 과다 사용: {tr.task_id}, {tr.tokens_used.get('total', 0)}개"),
    severity="warning",
    cooldown=180,
)
```

### 복합 조건 알림

여러 조건을 동시에 만족할 때만 발동하는 알림을 만들 수 있다.

```python
# accuracy < 0.6 이고 execution_time > 10.0초인 동시에 느리고 부정확한 케이스
slow_and_inaccurate_rule = SimpleTaskAlertRule(
    name="slow_and_inaccurate",
    condition=lambda tr: tr.accuracy_score < 0.6 and tr.execution_time > 10.0,
    handler=lambda msg, tr: print(
        f"[ERROR] 느리고 부정확: task={tr.task_id}, "
        f"accuracy={tr.accuracy_score:.2f}, time={tr.execution_time:.1f}s"
    ),
    severity="error",
    cooldown=60,
)
```

### compound_conditions — 딕셔너리 방식 복합 조건

람다 함수 대신 딕셔너리 형식으로도 복합 조건을 정의할 수 있다.

```python
retry_alert = SimpleTaskAlertRule(
    name="excessive_retries",
    compound_conditions=[
        {"field": "attempts", "op": "gte", "value": 3},
        {"field": "accuracy_score", "op": "lt", "value": 0.5},
    ],
    handler=lambda msg, tr: print(f"[WARNING] 재시도 과다: {msg}"),
    severity="warning",
    cooldown=300,
)
```

### dry_run — 조건 검증 (단위 테스트 활용)

알림 규칙이 올바르게 동작하는지 실제 에이전트를 실행하지 않고 테스트할 수 있다. CI에서 알림 규칙 자체를 테스트하는 데 유용하다.

```python
from agent_evaluator import SimpleTaskAlertRule, create_taskresult

rule = SimpleTaskAlertRule(
    name="low_accuracy_test",
    condition=lambda tr: tr.accuracy_score < 0.70,
    handler=lambda msg, tr: None,
    severity="warning",
)

# 임계값 아래 케이스 — 알림 발동 확인
low_accuracy_task = create_taskresult(
    task_id="test_001",
    question="테스트 질문",
    response="잘못된 응답",
    ground_truth="정확한 답",
    execution_time=1.0,
    task_type="qa",
)
# dry_run: 핸들러 실행 없이 조건만 검사 → True면 알림 발동할 것
assert rule.dry_run(low_accuracy_task) == True

# 임계값 위 케이스 — 알림 미발동 확인
high_accuracy_task = create_taskresult(
    task_id="test_002",
    question="테스트 질문",
    response="서울입니다",
    ground_truth="서울",
    execution_time=0.5,
    task_type="qa",
)
assert rule.dry_run(high_accuracy_task) == False

print("알림 규칙 단위 테스트 통과")
```

### class_level_cooldown — 같은 이름 인스턴스 공유 쿨다운

같은 `name`을 가진 규칙 인스턴스가 여러 개 있을 때 쿨다운을 공유한다. 여러 데코레이터에 같은 규칙을 재사용할 때 알림이 중복 발생하지 않는다.

```python
# 두 에이전트가 같은 이름의 규칙을 사용해도 쿨다운이 공유됨
common_rule = SimpleTaskAlertRule(
    name="shared_accuracy_rule",  # 같은 name → 쿨다운 공유
    condition=lambda tr: tr.accuracy_score < 0.7,
    handler=lambda msg, tr: notify_slack(msg),
    severity="warning",
    cooldown=300,
    class_level_cooldown=True,   # 클래스 수준 쿨다운 활성화
)

@agent_eval(monitor, task_type="qa", alert_rules=[common_rule])
def agent_a(question, ground_truth=""): ...

@agent_eval(monitor, task_type="qa", alert_rules=[common_rule])
def agent_b(question, ground_truth=""): ...
# agent_a와 agent_b 중 어느 쪽이 먼저 발동해도 5분 내 중복 알림 없음
```

---

## 11.3 Slack / 이메일 / Webhook 핸들러 설정

### SLACK_WEBHOOK_URL 환경변수 기반 fallback 패턴

API 키와 마찬가지로 Slack Webhook URL도 코드에 하드코딩하지 않는다. 환경변수가 없으면 콘솔 출력으로 fallback하는 패턴이 안전하다.

```python
import os
import json

def create_slack_handler(channel: str = "#alerts"):
    """환경변수 기반 Slack 핸들러 — 미설정 시 콘솔 출력으로 fallback."""
    slack_url = os.getenv("SLACK_WEBHOOK_URL")

    if slack_url:
        import urllib.request

        def handler(message: str, task_result) -> None:
            payload = {
                "channel": channel,
                "text": f"*[Agent Evaluator Alert]*\n{message}",
                "attachments": [
                    {
                        "color": "danger" if task_result.accuracy_score < 0.5 else "warning",
                        "fields": [
                            {"title": "Task ID", "value": task_result.task_id, "short": True},
                            {"title": "Accuracy", "value": f"{task_result.accuracy_score:.2%}", "short": True},
                            {"title": "Latency", "value": f"{task_result.execution_time:.2f}s", "short": True},
                            {"title": "Task Type", "value": task_result.task_type, "short": True},
                        ],
                    }
                ],
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(slack_url, data=data,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
    else:
        def handler(message: str, task_result) -> None:
            print(f"[MOCK SLACK → {channel}] {message}")

    return handler

# 사용
slack_handler = create_slack_handler("#monitoring")
```

### 이메일 핸들러 (smtplib)

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def create_email_handler(to_address: str):
    """SMTP 기반 이메일 핸들러."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_address = os.getenv("SMTP_FROM", smtp_user)

    def handler(message: str, task_result) -> None:
        if not smtp_user:
            print(f"[MOCK EMAIL → {to_address}] {message}")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Agent Alert] {message[:60]}..."
        msg["From"] = from_address
        msg["To"] = to_address

        body = f"""
        <h3>Agent Evaluator 알림</h3>
        <p>{message}</p>
        <table>
            <tr><td>Task ID</td><td>{task_result.task_id}</td></tr>
            <tr><td>Accuracy</td><td>{task_result.accuracy_score:.2%}</td></tr>
            <tr><td>Latency</td><td>{task_result.execution_time:.2f}s</td></tr>
        </table>
        """
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_address, to_address, msg.as_string())

    return handler
```

### 완전한 5-규칙 프로덕션 알림 설정 코드

실제 운영 환경에서 바로 사용할 수 있는 완전한 알림 설정 예시다.

```python
import os
from agent_evaluator import (
    PerformanceMonitor,
    AlertRuleBuilder,
    SimpleTaskAlertRule,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,
)

slack_handler = create_slack_handler("#monitoring")
slack_critical = create_slack_handler("#incidents")
email_handler = create_email_handler("qa-team@company.com")

# 규칙 1: 정확도 경고 (Warning)
accuracy_warning = AlertRuleBuilder.when_accuracy_below(
    threshold=0.70,
    handler=slack_handler,
    severity="warning",
    cooldown=300,    # 5분
)

# 규칙 2: 응답 지연 경고 (Warning)
latency_warning = AlertRuleBuilder.when_latency_above(
    threshold_seconds=5.0,
    handler=slack_handler,
    severity="warning",
    cooldown=60,     # 1분
)

# 규칙 3: 완료율 오류 (Error) — Slack + 이메일 동시 발송
def completion_error_handler(msg, tr):
    slack_handler(msg, tr)
    email_handler(msg, tr)

completion_error = AlertRuleBuilder.when_completion_below(
    threshold=0.60,
    handler=completion_error_handler,
    severity="error",
    cooldown=60,
)

# 규칙 4: 오류 발생 (Error)
error_alert = AlertRuleBuilder.when_error(
    handler=slack_handler,
    severity="error",
    cooldown=60,
)

# 규칙 5: 재시도 과다 (Critical) — 인시던트 채널 + 이메일
excessive_retry = SimpleTaskAlertRule(
    name="excessive_retry",
    condition=lambda tr: tr.attempts >= 4,
    handler=lambda msg, tr: (
        slack_critical(f"[CRITICAL] 재시도 과다: {msg}", tr),
        email_handler(f"[CRITICAL] {msg}", tr)
    ),
    severity="critical",
    cooldown=30,     # 30초 — Critical은 짧게
)

# 모든 규칙 적용
all_rules = [accuracy_warning, latency_warning, completion_error,
             error_alert, excessive_retry]

@agent_eval(monitor, task_type="qa", alert_rules=all_rules)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 11.4 쿨다운 전략과 알림 피로 방지

쿨다운은 동일한 규칙이 짧은 시간 안에 반복 발동하지 않도록 하는 메커니즘이다. 알림 피로를 막는 핵심 도구다.

### 쿨다운 설정 원칙

**Warning은 길게, Critical은 짧게.**

Warning 알림을 5분에 한 번씩만 받으면 "지금 잠깐 나빠졌나, 계속 나쁜가"를 파악하는 데 충분한 시간이 있다. 반면 Critical 상황에서는 30초~1분 내에 다시 알림이 와야 실제 상황이 지속되고 있다는 것을 알 수 있다.

```
Warning  → cooldown: 300초 (5분) — 5분마다 한 번
Error    → cooldown: 60초 (1분)  — 1분마다 한 번
Critical → cooldown: 30초 (30초) — 30초마다 한 번
```

**초기 배포 후 2주간은 쿨다운을 길게 설정하라.**

신규 에이전트는 초기에 불안정하다. 쿨다운을 짧게 설정하면 배포 첫날 수십 개의 알림이 쏟아져서 팀이 지친다. 2주 캘리브레이션 기간에는 Warning 쿨다운을 `1800초(30분)`까지 늘려도 괜찮다.

### 알림 채널 분리

모든 알림을 하나의 채널에 몰면 중요한 Critical 알림이 Warning 홍수에 묻힌다.

```
#monitoring  → Warning 알림 (조용히 확인)
#alerts      → Error 알림 (온콜 확인)
#incidents   → Critical 알림 (즉시 대응)
```

📋 **QA 관리자 TIP:** Slack 채널 알림 설정에서 `#monitoring`은 "멘션만 알림", `#alerts`는 "모든 메시지 알림", `#incidents`는 "모든 메시지 알림 + 모바일 푸시"로 설정하라. 채널 설정이 잘못되면 중요한 알림을 놓친다.

---

## 11.5 AnomalyDetector — Z-Score 이상 탐지

알림 규칙은 "특정 값이 임계값을 넘으면" 발동한다. 반면 `AnomalyDetector`는 "최근 패턴과 달라졌을 때" 발동한다. 점진적으로 품질이 나빠지는 케이스는 알림 규칙으로는 잡기 어렵지만 이상 탐지로는 잡힌다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 권장: enable_anomaly_detection=True 로 PerformanceMonitor에 통합
# save_to_file() 호출 시 AnomalyDetector.scan()이 자동 실행됨
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,   # ← 이것만 추가
    anomaly_baseline_window=100,     # 기준선 계산 태스크 수 (기본: 100)
    anomaly_detection_window=20,     # 현재값 계산 태스크 수 (기본: 20)
)
```

`save_to_file()`을 호출할 때 자동으로 이상 탐지를 수행하고 결과를 JSON에 포함한다.

```python
monitor.save_to_file("evaluation")  # anomaly_data 자동 포함
```

저장된 JSON의 `anomaly_data` 필드를 대시보드가 읽어 `/api/anomalies` 엔드포인트로 제공한다.

### explain_event — 이상 원인 분석

단순히 "이상 이벤트 발생"이 아니라 원인과 권고사항까지 확인할 수 있다.

```python
# 대시보드 API로 특정 이벤트 상세 분석 (file_id 포함 경로)
import urllib.request, json

file_id = "evaluation"
event_id = "event_20260409_001"
with urllib.request.urlopen(
    f"http://localhost:8765/api/results/{file_id}/anomaly/explain/{event_id}"
) as resp:
    explanation = json.load(resp)

print(f"이상 유형: {explanation['anomaly_type']}")
print(f"원인: {explanation['root_cause']}")
print(f"권고: {explanation['recommendation']}")
```

응답 예시:
```json
{
  "event_id": "event_20260409_001",
  "anomaly_type": "accuracy_drop",
  "metric": "accuracy_score",
  "current_value": 0.52,
  "baseline_mean": 0.78,
  "z_score": 3.1,
  "root_cause": "accuracy_score가 기준선(0.78)보다 3.1 표준편차 낮습니다. 최근 3시간 내 QA 태스크에서 집중 발생.",
  "recommendation": "최근 배포 변경사항 확인, 프롬프트 변경 이력 검토, 입력 데이터 분포 변화 확인 권장"
}
```

📋 **QA 관리자 TIP:** Z-Score 임계값은 내부적으로 2.5로 고정되어 있다. `baseline_window`(기본 100)와 `detection_window`(기본 20)를 조정해 탐지 민감도를 제어할 수 있다. window가 작을수록 최근 데이터에 민감하고, 클수록 장기 추이 기반으로 안정적으로 동작한다.

---

## 11.6 AdaptivePolicy — 예산 초과 시 자동 다운그레이드

비용이 예산을 초과하면 더 저렴한 모델로 자동 전환하는 정책이다. 비용 폭증을 방지하는 마지막 안전망이다.

```python
from agent_evaluator import AdaptivePolicy, SamplingStage, CostTracker

# SamplingStage Enum: DEFAULT / ANOMALY / BUDGET_EXCEEDED
# AdaptivePolicy: 이상 감지·예산 초과 시 샘플링률 자동 전환
policy = AdaptivePolicy(
    default_sample_rate=0.1,     # 평상시 10% 샘플링 — 비용 절감
    anomaly_sample_rate=1.0,     # 이상 감지 시 100% 전수 평가
    budget_per_day=50.0,         # 하루 예산 $50
    alert_at=0.8,                # 예산 80% 도달 시 알림
)

# CostTracker: provider/model별 비용 기록 및 예산 추적
cost_tracker = CostTracker(budget_per_day=50.0, alert_at=0.8)
monitor = PerformanceMonitor(output_dir="results/")

# LLM Judge 호출 시 현재 샘플링 비율 기준으로 실행 여부 결정
import random
for task_id in range(100):
    if random.random() < policy.current_sample_rate:
        cost_tracker.record(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            cost_usd=0.001,
        )

# 예산 소진 시 자동으로 샘플링 비율 0으로 전환
if cost_tracker.is_budget_exceeded():
    print(f"예산 초과 — 오늘 평가 중단: ${cost_tracker.get_today_cost():.2f} USD")

# 이상 감지 시 전수 평가로 전환, 해소 시 기본 모드 복귀
policy.enter_anomaly_mode(reason="accuracy 급락 감지")
print(f"이상 모드: sample_rate={policy.current_sample_rate:.0%}")  # → 100%

policy.exit_anomaly_mode()
print(f"복귀 후: sample_rate={policy.current_sample_rate:.0%}")   # → 10%
```

**`SamplingStage` 상태 전환:**

```
DEFAULT        → 10% 샘플링 (평상시)
ANOMALY        → 100% 전수 평가 (enter_anomaly_mode() 호출 후)
BUDGET_EXCEEDED → 0% 평가 중단 (budget_per_day 초과 시 자동 전환)
```

예산의 80%에 도달하면 알림이 발생하고(`is_budget_alert()`), 초과 시 자동으로 평가를 중단해 당일 비용 폭증을 방지한다.

📋 **QA 관리자 TIP:** `is_budget_alert()` 또는 `is_budget_exceeded()` 호출 결과를 `SimpleTaskAlertRule` 조건에 연결하면 예산 경고를 Slack으로 자동 전달할 수 있다. `enter_anomaly_mode()` 호출이 잦다면 일일 예산을 늘리거나 샘플링 전략을 재검토할 신호다.

---

## 📋 QA 관리자 포인트: 알림 임계값 설정 기준표

실무에서 바로 사용할 수 있는 권장 임계값과 쿨다운 조합이다.

| 지표 | Warning | Error | 쿨다운 (W/E) | 채널 (W/E) |
|------|---------|-------|-------------|-----------|
| accuracy_score | < 0.70 | < 0.55 | 300s / 60s | #monitoring / #alerts |
| execution_time | > 5초 | > 10초 | 60s / 30s | #monitoring / #alerts |
| completion_score | < 0.80 | < 0.60 | 120s / 60s | #monitoring / #alerts |
| tokens_used["total"] | > 3000 | > 6000 | 180s / 60s | #monitoring / #alerts |
| attempts (재시도) | ≥ 2 | ≥ 4 | 300s / 120s | #monitoring / #alerts |
| 보안 위협 탐지 | 1건 | 3건 | 60s / 즉시 | #alerts / #incidents |
| privilege_escalation | 탐지 즉시 | — | 30s | #incidents |

**알림 규칙 단위 테스트 체크리스트:**

```python
# CI에 포함할 알림 규칙 검증 테스트
def test_alert_rules():
    from agent_evaluator import SimpleTaskAlertRule, create_taskresult

    rule = AlertRuleBuilder.when_accuracy_below(
        threshold=0.70,
        handler=lambda msg, tr: None,
        severity="warning",
    )

    # Warning 발동 케이스
    bad_task = create_taskresult(
        task_id="t1", question="q", response="r",
        ground_truth="correct answer here",
        execution_time=1.0, task_type="qa"
    )
    assert rule.dry_run(bad_task), "낮은 accuracy에서 알림이 발동해야 함"

    # Warning 미발동 케이스
    good_task = create_taskresult(
        task_id="t2", question="q", response="correct answer here",
        ground_truth="correct answer here",
        execution_time=0.5, task_type="qa"
    )
    assert not rule.dry_run(good_task), "높은 accuracy에서 알림이 발동하면 안 됨"
```

---

## 이 챕터의 핵심

- **AlertRuleBuilder 5종 팩토리** — `when_accuracy_below`, `when_latency_above`, `when_completion_below`, `when_error`, `when_tool_calls_exceed`로 표준 알림을 한 줄로 설정한다
- **SimpleTaskAlertRule + dry_run** — 커스텀 람다 조건으로 어떤 상황이든 알림을 만들 수 있고, `dry_run()`으로 단위 테스트까지 가능하다
- **Warning은 길게, Critical은 짧게** — 쿨다운을 계층별로 다르게 설정해야 알림 피로 없이 중요한 알림을 놓치지 않는다
- **AnomalyDetector는 알림 규칙의 보완재** — 임계값 기반 알림이 잡지 못하는 "점진적 품질 저하"를 Z-Score로 탐지한다
- **AdaptivePolicy는 비용 안전망** — 일일 예산을 초과하기 전에 더 저렴한 모델로 자동 전환해서 비용 폭증을 방지한다

---

## 실전 예제

`05_streaming_alerts.py`는 `StreamingEvaluator`, `ImplicitFeedbackTracker`, `AlertEngine`을 함께 사용하는 실시간 알림 파이프라인을 보여준다. `06_operational.py`는 `SimpleTaskAlertRule`과 `AnomalyDetector`의 결합을 통해 임계값·통계 기반 이중 알림 구조를 시연한다.

**파일**: `Evaluator_Examples/05_streaming_alerts.py`, `Evaluator_Examples/06_operational.py`

**핵심 코드 (출처: `Evaluator_Examples/05_streaming_alerts.py`)**

```python
# 출처: Evaluator_Examples/05_streaming_alerts.py, 섹션 3 — SimpleTaskAlertRule 경량 알림
from agent_evaluator import SimpleTaskAlertRule, agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

# TaskResult 기반 경량 알림 규칙 정의 (StreamingEvaluator 불필요)
slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,      # 5초 초과 시 발동
    handler=lambda msg, tr: print(f"[SLOW] {msg} — {tr.task_id}"),
    severity="warning",
    cooldown=60,   # 같은 태스크에 60초 내 중복 알림 방지
)

low_accuracy_alert = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: tr.accuracy_score < 0.5,      # 정확도 50% 미만
    handler=lambda msg, tr: print(f"[QUALITY] {msg} — score={tr.accuracy_score:.2f}"),
    severity="critical",
    cooldown=30,
)

@agent_eval(monitor, task_type="qa", alert_rules=[slow_alert, low_accuracy_alert])
def agent(question: str, ground_truth: str = "") -> str:
    import time
    time.sleep(6)   # 의도적으로 느린 응답 시뮬레이션
    return "느린 응답"

# 호출 시 slow_alert 자동 발동
agent("질문", ground_truth="정답")
```

- `SimpleTaskAlertRule`은 `StreamingEvaluator` 없이 `TaskResult` 레벨에서 직접 작동하는 경량 알림이다
- `cooldown` 파라미터로 동일 규칙의 반복 발화를 제어해 알림 피로도(alert fatigue)를 방지한다
- `handler` 함수에서 Slack WebHook, PagerDuty API 호출, 이메일 발송 등 외부 연동을 구현한다

```python
# 출처: Evaluator_Examples/05_streaming_alerts.py, 섹션 4 — AlertRuleBuilder 팩토리
from agent_evaluator.alerts.engine import AlertEngine
from agent_evaluator.alerts.handlers import AlertRuleBuilder
import json
from pathlib import Path

alert_log_path = Path("results/alerts.jsonl")

def jsonl_handler(message: str, task_result) -> None:
    """JSONL 파일에 알림 기록 — 대시보드 알림 탭 연동"""
    record = {
        "timestamp": task_result.timestamp.isoformat() if task_result else "",
        "rule": message.split(":")[0],
        "message": message,
    }
    with open(alert_log_path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# 팩토리 메서드로 알림 규칙 생성
accuracy_rule = (
    AlertRuleBuilder
    .when_accuracy_below(threshold=0.6)
    .with_handler(jsonl_handler)
    .with_severity("warning")
    .build()
)

latency_rule = (
    AlertRuleBuilder
    .when_latency_above(threshold=3.0)
    .with_handler(jsonl_handler)
    .with_severity("critical")
    .build()
)

# dry_run으로 실제 발화 없이 규칙 검증
fired = accuracy_rule.dry_run(task_result)
print(f"알림 발화 여부: {fired}")  # True/False
```

- `AlertRuleBuilder`의 팩토리 메서드(`when_accuracy_below`, `when_latency_above` 등)로 반복 코드 없이 알림 규칙을 생성한다
- JSONL 형식으로 알림을 기록하면 `agent-eval dashboard`의 알림 탭에서 자동으로 시각화된다
- `dry_run(task_result)`으로 규칙 설정이 올바른지 실제 알림 발화 없이 테스트할 수 있다

```bash
python Evaluator_Examples/05_streaming_alerts.py
python Evaluator_Examples/06_operational.py
```

**예제 구성**

| 파일 | 섹션 | 내용 | 연관 기능 |
|------|------|------|-----------|
| 05_streaming_alerts | 섹션 1 | `StreamingEvaluator` + `SlidingWindow` | 실시간 윈도우 집계 |
| 05_streaming_alerts | 섹션 2 | `ImplicitFeedbackTracker` | 사용자 반응 추적 → 알림 트리거 |
| 05_streaming_alerts | 섹션 3 | `AlertEngine` 다채널 알림 | console·webhook·파일 핸들러 |
| 06_operational | 섹션 4 | `SimpleTaskAlertRule` + `AnomalyDetector` | 임계값+Z-Score 이중 감시 |

**실행 결과 (v0.8.0 기준)**

```
# 05_streaming_alerts.py
StreamingEvaluator: 슬라이딩 윈도우 50건 처리
ImplicitFeedback: negative_feedback 3건 수집 → AlertEngine 트리거
[ALERT] accuracy_below_threshold: window_avg=0.42 < threshold=0.7
[ALERT] latency_spike: p95=6.2s > threshold=5.0s
알림 JSONL 저장: results/alerts.jsonl

# 06_operational.py
SimpleTaskAlertRule: 5개 규칙 등록 (warning·error·critical)
AnomalyDetector: latency_spike 2건 (Z-Score=2.3, 2.8)
```

> **`dry_run()` 활용**: 알림 규칙을 프로덕션에 배포하기 전에 `rule.dry_run(sample_result)`로 단위 테스트를 실행한다. 05_streaming_alerts.py 섹션 3에서 실제 `dry_run()` 패턴을 확인할 수 있다. 쿨다운은 `warning=3600`, `error=1800`, `critical=300`으로 계층별로 다르게 설정하는 것이 핵심이다.
