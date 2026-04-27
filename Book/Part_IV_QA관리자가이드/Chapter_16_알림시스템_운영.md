# Chapter 16. 알림 시스템 운영

> **이 챕터에서 배우는 것**
> - `AlertRuleBuilder`의 5종 팩토리 메서드로 표준 알림 규칙을 빠르게 설정하는 방법을 익힌다
> - `SimpleTaskAlertRule`로 커스텀 조건 알림을 만들고 단위 테스트로 검증하는 법을 배운다
> - Slack, 이메일, Webhook 핸들러를 실무 수준으로 연결하는 완전한 코드를 확인한다
> - 쿨다운 전략으로 알림 피로를 방지하는 원칙을 이해한다
> - `AnomalyDetector`와 `AdaptivePolicy`로 이상 탐지 및 비용 자동 제어를 구현한다
> - **`StreamingEvaluator`**로 슬라이딩 윈도우 집계 지표를 실시간으로 추적하는 방법을 이해한다
> - `ImplicitFeedbackTracker`로 사용자 암묵적 행동 신호(thumbs_up·regenerate·abandon)를 수집한다

---

> **알림과 Harness Gate의 관계**  
> 알림 규칙은 개별 태스크 이벤트를 감지하고, Harness Gate는 누적 지표를 판정한다. 두 시스템은 같은 데이터를 다른 시간 단위로 본다.
>
> | 알림 규칙 (실시간 이벤트) | 연관 Harness Gate (누적 판정) | Gate 악화 신호 |
> |------------------------|---------------------------|----------------|
> | `when_accuracy_below(0.70)` | **Gate A** 목표달성 | accuracy 누적 평균 < 임계값 |
> | `when_latency_above(5.0)` | **Gate D** 성능계약 | P95 latency SLA 위반율 증가 |
> | `when_completion_below(0.80)` | **Gate A** 목표달성 | TCR 누적 하락 |
> | `when_tool_calls_exceed(10)` | **Gate B** 행동무결성 | 도구 호출 루프 탐지율 증가 |
> | `when_error(...)` | **Gate C** 신뢰성 | 오류 복구율·재시도율 악화 |
> | `보안 위협 탐지` | **Gate E** 보안경계 | 위협 심각도 누적 점수 상승 |
> | `privilege_escalation` | **Gate E** 보안경계 | 즉시 Gate E FAIL 트리거 |
>
> **실무 원칙**: 알림이 반복 발생한다면 Gate 점수 추세를 확인하라. 알림 5회 = Gate 경고(WARN) 예고일 수 있다.

---

## 16.1 AlertRuleBuilder — 5종 팩토리 메서드

`AlertRuleBuilder`는 가장 흔히 필요한 알림 규칙을 한 줄로 생성하는 팩토리 클래스다. 5가지 정적 메서드를 제공한다.

```python
from agent_evaluator import AlertRuleBuilder, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")
```

### when_accuracy_below — 정확도 하한 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
accuracy_rule = AlertRuleBuilder.when_accuracy_below(
    threshold=0.70,              # accuracy_score < 0.70 이면 발동
    handler=lambda msg, tr: print(f"[WARNING] 정확도 하락: {msg}"),
    severity="warning",
    cooldown=300,                # 5분 쿨다운
)
```

- `threshold=0.70`은 0~1.0 스케일의 `accuracy_score` 기준이다 — 대시보드에서 보이는 70%가 아니라 0.70으로 입력한다
- `handler` 람다의 첫 번째 인수 `msg`는 규칙 이름과 현재 값을 포함한 자동 생성 메시지이고, `tr`은 해당 `TaskResult` 객체다
- `cooldown=300`으로 5분 내 동일 규칙이 반복 발동하지 않게 해 알림 피로를 방지한다

### when_latency_above — 응답시간 상한 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
latency_rule = AlertRuleBuilder.when_latency_above(
    threshold_seconds=5.0,       # execution_time > 5.0초 이면 발동
    handler=lambda msg, tr: print(f"[WARNING] 응답 지연: {msg}"),
    severity="warning",
    cooldown=60,                 # 1분 쿨다운
)
```

- `threshold_seconds`는 초 단위로 `execution_time` 필드와 비교한다 — `SLAConfig(p95_ms=5000)`의 5000ms와 동일한 기준을 사용하는 것이 일관성 있다
- 응답 지연 알림은 개별 태스크 수준에서 발동하므로 P95를 넘기기 전에 이상 징후를 조기에 감지할 수 있다
- `cooldown=60`으로 1분마다 알림을 받으면 지연 문제가 지속되는지 빠르게 파악할 수 있다

### when_completion_below — 완료율 하한 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
completion_rule = AlertRuleBuilder.when_completion_below(
    threshold=0.80,              # completion_score < 0.80 이면 발동
    handler=lambda msg, tr: print(f"[ERROR] 완료율 하락: {msg}"),
    severity="error",
    cooldown=120,
)
```

- `completion_score`는 단순 성공/실패가 아니라 0.0~1.0 연속값으로 부분 완료를 표현한다 — `threshold=0.80`은 태스크가 80% 미만 완료된 경우에 발동한다
- `severity="error"`로 설정하면 대시보드 알림 탭에서 Error 수준으로 분류되어 Warning과 구분된다
- TCR과 `completion_score`는 연관이 있으므로 완료율 하락 알림이 자주 발동하면 Gate A TCR을 점검해야 한다

### when_error — 오류 발생 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
error_rule = AlertRuleBuilder.when_error(
    handler=lambda msg, tr: print(f"[ERROR] 태스크 오류: {msg}"),
    severity="error",
    cooldown=60,
)
```

`tr.errors`가 비어 있지 않으면 발동한다. 예외 메시지와 함께 태스크 ID가 핸들러에 전달된다.

### when_tool_calls_exceed — 도구 호출 횟수 상한 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py, 섹션 4 — AlertRuleBuilder 팩토리
tool_rule = AlertRuleBuilder.when_tool_calls_exceed(
    max_calls=10,                # tool_calls 횟수 > 10 이면 발동
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

- `alert_rules`는 리스트로 여러 규칙을 동시에 등록할 수 있다 — 각 태스크가 완료될 때마다 등록된 모든 규칙이 순서대로 평가된다
- 각 규칙의 `cooldown`은 독립적으로 동작하므로 accuracy와 latency 알림이 서로 간섭하지 않는다
- 규칙 수가 늘어나면 `all_rules = [...]` 리스트로 분리해 관리하는 것이 코드 가독성을 높인다

`QuickEval`에서도 동일한 방식으로 적용한다:

```python
# 출처: Evaluator_Examples/ch16_alerts.py — QuickEval 평가
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval(task_type="qa", alert_rules=[accuracy_rule, latency_rule])
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `QuickEval`의 `@eval(...)` 직접 호출 방식에서도 `alert_rules` 파라미터를 동일하게 지원한다
- `@eval.qa`, `@eval.rag` 같은 단축 데코레이터에는 `alert_rules`를 전달할 수 없으므로, 알림이 필요하면 `@eval(task_type="qa", alert_rules=[...])` 형태를 사용한다
- `QuickEval.for_security()`와 같은 팩토리 메서드로 생성한 인스턴스에서도 동일하게 동작한다

---

> **알림 도구 선택 가이드 (초중급자용)**
>
> Agent-Evaluator 알림 시스템에는 세 가지 도구가 있다. 상황에 맞게 골라 쓰면 된다.
>
> | 상황 | 사용할 도구 |
> |------|------------|
> | 정확도·지연·오류·완료율·도구호출 횟수 등 표준 조건 알림 | `AlertRuleBuilder` 팩토리 메서드 |
> | 표준 조건에 없는 커스텀 조건 (토큰 수, 복합 조건 등) | `SimpleTaskAlertRule` |
> | 개별 태스크가 아닌 슬라이딩 윈도우 집계(TCR 평균, P95 추세)로 알림 | `StreamingEvaluator` |
>
> **기본 전략**: `AlertRuleBuilder`로 시작해, 부족한 조건만 `SimpleTaskAlertRule`로 추가하라. `StreamingEvaluator`는 단발 이상이 아닌 "지속적 품질 저하" 트렌드를 잡아야 할 때 추가한다.

## 16.2 SimpleTaskAlertRule — 커스텀 조건 알림

`AlertRuleBuilder`가 제공하지 않는 조건이 필요할 때는 `SimpleTaskAlertRule`로 완전히 커스텀할 수 있다.

```python
from agent_evaluator import SimpleTaskAlertRule
```

### 단일 조건 알림

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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

## 16.3 Slack / 이메일 / Webhook 핸들러 설정

### SLACK_WEBHOOK_URL 환경변수 기반 fallback 패턴

API 키와 마찬가지로 Slack Webhook URL도 코드에 하드코딩하지 않는다. 환경변수가 없으면 콘솔 출력으로 fallback하는 패턴이 안전하다.

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 예제 코드
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
# 출처: Evaluator_Examples/ch16_alerts.py — 예제 코드
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

- SMTP 자격증명은 `os.getenv()`로만 읽어야 하며, 코드에 하드코딩하면 보안 사고로 이어질 수 있다
- `smtp_user`가 없을 때 콘솔 출력으로 fallback하는 패턴을 사용하면 개발 환경에서도 알림 흐름을 테스트할 수 있다
- HTML 본문에 `task_result.task_id`, `accuracy_score`, `execution_time`을 포함하면 이메일만 보고도 어떤 태스크에서 발생한 문제인지 바로 파악할 수 있다

### 완전한 5-규칙 프로덕션 알림 설정 코드

실제 운영 환경에서 바로 사용할 수 있는 완전한 알림 설정 예시다.

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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

- Warning·Error·Critical 3계층으로 규칙을 분리하고 채널도 `#monitoring`, `#alerts`, `#incidents`로 나누면 긴급도에 따라 빠르게 대응할 수 있다
- 규칙 3처럼 `completion_error_handler`에서 Slack과 이메일을 동시에 호출하면 Error 수준 이상은 다중 채널로 알릴 수 있다
- `auto_save_interval=50`으로 설정해 50건마다 파일을 자동 저장하면 대시보드가 알림 이력과 동기화된다

---

## 16.4 쿨다운 전략과 알림 피로 방지

### 알림 피로(Alert Fatigue)란?

**알림 피로**는 너무 많은 알림이 쏟아져 팀이 알림을 무시하게 되는 현상이다. 정확도가 낮아졌을 때 알림이 1초마다 온다면, 팀원은 첫 5분 뒤부터 알림을 끄거나 무시하게 된다. 그러다 실제 Critical 상황이 오면 놓친다. 알림 피로는 알림 시스템 자체를 무력화한다.

**해결책이 쿨다운이다.** 쿨다운은 동일한 규칙이 짧은 시간 안에 반복 발동하지 않도록 막는 대기 시간이다. `cooldown=300`으로 설정하면 같은 규칙이 발동하더라도 300초(5분) 동안은 추가 알림을 보내지 않는다. 이 5분 동안 같은 조건이 10번 발생해도 알림은 1번만 간다.

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

### Harness Gate 관점: 알림 → 배포 차단 에스컬레이션 흐름

알림은 단순한 "알림"이 아니다. Harness Engineering에서는 **임계값 위반을 자동 감지 → 알림 → Gate 점수 악화 → 배포 차단**으로 이어지는 파이프라인의 첫 번째 단계다.

```
[개별 태스크 완료]
       ↓
SimpleTaskAlertRule / AlertRuleBuilder 평가
       ↓
임계값 위반 감지
  ├── Warning → #monitoring 알림 → Gate 점수 추세 모니터링
  ├── Error   → #alerts 알림 → 즉각 조사 + 배포 보류 검토
  └── Critical → #incidents 알림 → 즉각 롤백 또는 중단
       ↓
PerformanceMonitor 누적 → Harness Gate 판정
  ├── Gate A WARN/FAIL → accuracy·TCR 임계값 위반 누적
  ├── Gate D WARN/FAIL → SLA·P95·비용 임계값 위반 누적
  └── Gate E FAIL → 보안 위협 탐지 즉시 (Critical 알림과 동시)
       ↓
agent-eval gate result.json → exit 0 (PASS) / exit 1 (FAIL)
  → CI/CD 배포 파이프라인 차단
```

**핵심 원리**: `SLAConfig(p95_ms=3000)`처럼 임계값을 코드로 선언하면, 해당 임계값을 위반하는 태스크는 자동으로 알림(Warning/Error)을 발생시키고, 누적되면 Gate D FAIL로 이어져 배포가 차단된다. 임계값을 한 곳에서 선언하면 알림과 Gate 판정이 자동으로 연동된다.

---

## 16.5 AnomalyDetector — Z-Score 이상 탐지

알림 규칙은 "특정 값이 임계값을 넘으면" 발동한다. 반면 `AnomalyDetector`는 "최근 패턴과 달라졌을 때" 발동한다. 점진적으로 품질이 나빠지는 케이스는 알림 규칙으로는 잡기 어렵지만 이상 탐지로는 잡힌다.

```python
# 출처: Evaluator_Examples/ch16_alerts.py — AnomalyDetector 이상 탐지
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
# 출처: Evaluator_Examples/ch16_alerts.py — 예제 코드
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

## 16.6 AdaptivePolicy — 예산 초과 시 자동 다운그레이드

비용이 예산을 초과하면 더 저렴한 모델로 자동 전환하는 정책이다. 비용 폭증을 방지하는 마지막 안전망이다.

```python
# 출처: Evaluator_Examples/ch16_alerts.py — CostTracker 비용 추적
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

## 16.7 StreamingEvaluator — 실시간 슬라이딩 윈도우 알림

`SimpleTaskAlertRule`은 개별 태스크가 완료된 직후 조건을 검사하는 경량 알림이다. 반면 **`StreamingEvaluator`**는 슬라이딩 윈도우 단위로 **집계 지표**(TCR, P95, 오류율)를 실시간으로 추적해, 단일 태스크의 이상이 아닌 **트렌드 이상**을 탐지한다.

### 슬라이딩 윈도우 설정

```python
# 출처: Evaluator_Examples/ch16_alerts.py, 섹션 1 — StreamingEvaluator 슬라이딩 윈도우
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.streaming.evaluator import StreamingEvaluator

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,
    anomaly_baseline_window=30,    # 앞 30건을 기준선으로 사용
    anomaly_detection_window=10,   # 이후 10건을 현재 상태와 비교
)

streaming = StreamingEvaluator(monitor=monitor)

# 50건 시뮬레이션: 정상 35건 → 느린 응답 10건 → 오류 5건
PATTERNS = (
    [(0.8, True,  1.0, 200)] * 35 +  # 정상 구간 (기준선)
    [(0.6, True, 10.0, 150)] * 10 +  # 느린 응답 (이상 구간)
    [(0.0, False, 0.1,   0)] *  5    # 오류 구간
)

for i, (acc, success, lat, tok) in enumerate(PATTERNS):
    task_id = f"stream_{i:04d}"
    streaming.record(
        task_id=task_id,
        success=success,
        execution_time=round(lat, 3),
        tokens_used=tok,
        accuracy_score=acc,
        has_error=not success,
    )
    result = create_taskresult(
        task_id=task_id,
        question=f"스트리밍 태스크 {i:03d}",
        response="응답" if success else "",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
    )
    monitor.record_task(result)

# 윈도우별 통계 조회
for window in ["1m", "5m"]:
    stats = streaming.get_stats(window)
    print(f"[{window}] count={stats.get('count', 0)}  "
          f"tcr={stats.get('tcr', 0):.1f}%  "
          f"p95={stats.get('p95_latency', 0):.2f}s  "
          f"err={stats.get('error_rate', 0):.1f}%")
```

- `StreamingEvaluator`는 `monitor`와 연결해 함께 사용한다 — `monitor.record_task()`와 `streaming.record()`를 모두 호출해야 PerformanceMonitor와 슬라이딩 윈도우가 모두 업데이트된다
- `get_stats(window)` 반환값의 `tcr`·`error_rate`는 `0–100` 퍼센트 단위다
- `enable_anomaly_detection=True`를 함께 설정하면 `AnomalyDetector`가 기준선과 현재 구간의 Z-Score를 자동 계산한다

### ImplicitFeedbackTracker — 사용자 암묵적 신호

클릭, 저장, 재생성 같은 사용자 행동 신호를 수집해 품질 프록시로 활용한다:

```python
# 출처: Evaluator_Examples/ch16_alerts.py, 섹션 2 — ImplicitFeedbackTracker — 사용자 암묵적 피드백
# 지원 타입: thumbs_up, thumbs_down, save, share, regenerate, copy, correction, abandon
FEEDBACK_EVENTS = [
    ("stream_0001", "thumbs_up",  {"dwell_time": 8.5}),
    ("stream_0002", "save",       {"format": "pdf"}),
    ("stream_0003", "regenerate", {"reason": "unsatisfied"}),  # 부정 신호
    ("stream_0005", "thumbs_down",{"reason": "wrong_answer"}), # 부정 신호
    ("stream_0007", "abandon",    {"at_position": 0}),         # 부정 신호
]

for task_id, feedback_type, metadata in FEEDBACK_EVENTS:
    monitor.record_implicit_feedback(
        task_id=task_id,
        feedback_type=feedback_type,
        metadata=metadata,
    )

fb_stats = monitor.feedback_tracker.get_stats()
print(f"positive={fb_stats.get('positive_count', 0)}  negative={fb_stats.get('negative_count', 0)}")
```

- `regenerate`·`thumbs_down`·`abandon` 3종이 **부정 신호** — 이 비율이 높으면 Gate A 정확도가 낮더라도 추가적인 품질 경고를 발생시킬 수 있다
- 피드백 통계는 `save_to_file()` 결과의 `feedback` 키에 포함되어 대시보드 "사용자 반응" 탭에 자동 시각화된다
- `monitor.record_implicit_feedback()`은 내부적으로 `ImplicitFeedbackTracker`에 위임한다

📋 **QA 관리자 TIP:** `SimpleTaskAlertRule`(개별 태스크 즉시 알림)과 `StreamingEvaluator`(윈도우 집계 트렌드 알림)를 함께 사용하면 단발성 이상과 지속적 품질 저하를 모두 잡을 수 있다. `AnomalyDetector`는 그 위에 Z-Score 기반 통계적 이상을 추가한다.


## 📋 QA 관리자 포인트: 알림 임계값 설정 기준표

실무에서 바로 사용할 수 있는 권장 임계값과 쿨다운 조합이다.

| 지표 | Warning | Error | 쿨다운 (W/E) | 채널 (W/E) | 연관 Gate |
|------|---------|-------|-------------|-----------|----------|
| accuracy_score | < 0.70 | < 0.55 | 300s / 60s | #monitoring / #alerts | Gate A |
| execution_time | > 5초 | > 10초 | 60s / 30s | #monitoring / #alerts | Gate D |
| completion_score | < 0.80 | < 0.60 | 120s / 60s | #monitoring / #alerts | Gate A |
| tokens_used["total"] | > 3000 | > 6000 | 180s / 60s | #monitoring / #alerts | Gate D |
| attempts (재시도) | ≥ 2 | ≥ 4 | 300s / 120s | #monitoring / #alerts | Gate C |
| 보안 위협 탐지 | 1건 | 3건 | 60s / 즉시 | #alerts / #incidents | Gate E |
| privilege_escalation | 탐지 즉시 | — | 30s | #incidents | Gate E |

**알림 규칙 단위 테스트 체크리스트:**

```python
# 출처: Evaluator_Examples/ch16_alerts.py — 알림 시스템
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
- **SimpleTaskAlertRule + dry_run** — 커스텀 람다 조건으로 어떤 상황이든 알림을 만들 수 있고, `dry_run()`으로 단위 테스트까지 가능하다; `StreamingEvaluator`는 슬라이딩 윈도우 트렌드가 필요할 때 추가한다
- **알림 피로 방지** — 알림이 너무 많으면 팀이 알림을 무시하게 된다; 쿨다운으로 같은 조건의 반복 알림을 억제하고 Warning/Error/Critical 채널을 분리해 긴급도별로 대응한다
- **Warning은 길게, Critical은 짧게** — `warning=300s / error=60s / critical=30s` 기준으로 계층별 쿨다운을 다르게 설정해야 알림 피로 없이 중요한 알림을 놓치지 않는다
- **Harness Gate 자동 연동** — 임계값을 `SLAConfig`, `InstructionConfig` 등 코드로 선언하면 알림과 Gate 판정이 자동 연동된다; 알림 반복 → Gate WARN → Gate FAIL → CI/CD 배포 차단으로 이어지는 파이프라인이 완성된다
- **AnomalyDetector는 알림 규칙의 보완재** — 임계값 기반 알림이 잡지 못하는 "점진적 품질 저하"를 Z-Score로 탐지한다
- **AdaptivePolicy는 비용 안전망** — 일일 예산을 초과하기 전에 더 저렴한 모델로 자동 전환해서 비용 폭증을 방지한다
- **ImplicitFeedbackTracker는 사용자 의도 신호 수집기** — LLM 점수와 별개로 thumbs_down·regenerate·abandon 행동 데이터를 품질 프록시로 활용한다

---

## 실전 예제

`ch16_alerts.py`는 `StreamingEvaluator`, `ImplicitFeedbackTracker`, `AlertEngine`, `SimpleTaskAlertRule`, `AnomalyDetector`를 조합해 실시간 알림 파이프라인과 임계값·통계 기반 이중 알림 구조를 한 파일에서 시연한다.

**기본 예제**: `Evaluator_Examples/ch16_alerts.py`

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch16_alerts.py, 섹션 3 — SimpleTaskAlertRule 경량 알림
from agent_evaluator import SimpleTaskAlertRule, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

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
# 출처: Evaluator_Examples/ch16_alerts.py, 섹션 4 — AlertRuleBuilder 팩토리
from agent_evaluator import AlertRuleBuilder  # decorators.py에 정의, agent_evaluator에서 export
from agent_evaluator.alerts.engine import AlertEngine
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

# 팩토리 메서드로 알림 규칙 생성 — 각 메서드가 SimpleTaskAlertRule을 직접 반환
accuracy_rule = AlertRuleBuilder.when_accuracy_below(
    threshold=0.6,
    handler=jsonl_handler,
    severity="warning",
)

latency_rule = AlertRuleBuilder.when_latency_above(
    threshold_seconds=3.0,
    handler=jsonl_handler,
    severity="critical",
)
```

- `AlertRuleBuilder`의 팩토리 메서드(`when_accuracy_below`, `when_latency_above` 등)로 반복 코드 없이 알림 규칙을 생성한다
- JSONL 형식으로 알림을 기록하면 `agent-eval dashboard`의 알림 탭에서 자동으로 시각화된다
- `dry_run(task_result)`으로 규칙 설정이 올바른지 실제 알림 발화 없이 테스트할 수 있다

```bash
python Evaluator_Examples/ch16_alerts.py
python Evaluator_Examples/ch10_group_g.py
```

**예제 구성**

| 파일 | 섹션 | 내용 | 연관 기능 |
|------|------|------|-----------|
| ch16_alerts | 섹션 1 | `StreamingEvaluator` + `SlidingWindow` | 실시간 윈도우 집계 |
| ch16_alerts | 섹션 2 | `ImplicitFeedbackTracker` | 사용자 반응 추적 → 알림 트리거 |
| ch16_alerts | 섹션 3 | `SimpleTaskAlertRule` 경량 알림 | TaskResult 레벨 즉시 알림 |
| ch16_alerts | 섹션 4 | `AlertRuleBuilder` 팩토리 + JSONL 핸들러 | 표준 알림 규칙 + 파일 기록 |

**실행 결과 (v0.9.1 기준)**

```
# ch16_alerts.py
StreamingEvaluator: 슬라이딩 윈도우 50건 처리
ImplicitFeedback: negative_feedback 3건 수집 → AlertEngine 트리거
[ALERT] accuracy_below_threshold: window_avg=0.42 < threshold=0.7
[ALERT] latency_spike: p95=6.2s > threshold=5.0s
알림 JSONL 저장: results/alerts.jsonl

# ch10_group_g.py
SimpleTaskAlertRule: 5개 규칙 등록 (warning·error·critical)
AnomalyDetector: latency_spike 2건 (Z-Score=2.3, 2.8)
```

> **`dry_run()` 활용**: 알림 규칙을 프로덕션에 배포하기 전에 `rule.dry_run(sample_result)`로 단위 테스트를 실행한다. ch16_alerts.py 섹션 3에서 실제 `dry_run()` 패턴을 확인할 수 있다. 쿨다운은 **Warning이 길고 Critical이 짧도록** — `warning=300`, `error=60`, `critical=30` 기준으로 계층별로 다르게 설정하는 것이 핵심이다 (16.4절 참고).
