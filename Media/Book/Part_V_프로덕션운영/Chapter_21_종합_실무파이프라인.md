# Chapter 21. 종합 실무 파이프라인

> **이 챕터에서 배우는 것**
> - **Harness Engineering의 실전 적용** — 개발 → CI → 운영 → 개선 4단계 파이프라인을 한 그림으로 이해하기
> - 각 단계마다 어떤 Gate가 검문소 역할을 하는지 파악하기
> - 1인 개발자부터 대규모 팀까지 팀 규모별 도입 로드맵
> - 프로덕션 품질 사고 발생 시 즉각 대응 런북(Runbook)
> - Agent-Evaluator 도입 성과를 측정하는 지표 체계
> - 더 발전하기 위한 다음 단계
> - 드리프트 감지와 Wilson Score 기반 임계값 재보정 파이프라인
> - 지표 하락 → Gate 원인 귀속 → 개선 액션 3단계 자기개선 루프

> **독자별 읽기 가이드**  
> - **👨‍💻 개발자**: §21.1(전체 사이클) → §21.2(팀 규모별 로드맵) 순서로 읽으면 현재 팀 상황에서 어디서부터 시작할지 경로를 찾을 수 있습니다.  
> - **📋 QA 관리자**: §21.1(전체 사이클 이해) → §21.3(품질 사고 런북) → §21.4(도입 성과 지표) 순서로 읽으면 운영 체계 수립과 성과 측정 방법을 파악할 수 있습니다.  
> - **⚙️ DevOps/MLOps**: §21.1 파이프라인 다이어그램 → §21.2 로드맵 중심으로 읽으면 인프라 구성 범위를 결정할 수 있습니다.  
> - **이 챕터는 Part III(개발자 구현)과 Part IV(QA 기준 수립)가 합쳐지는 지점입니다.** 두 파트를 먼저 읽은 뒤 이 챕터로 돌아오면 가장 빠르게 이해됩니다.

---

## 21.1 종합 파이프라인 — Harness Engineering의 실제 적용

앞의 챕터에서 각 단계를 개별적으로 살펴봤다. 이제 이 모든 것을 **개발 → CI → 운영 → 개선**이라는 4단계 파이프라인으로 연결하자.

> **Harness Engineering 핵심 원칙**: 단계별 파이프라인은 단순한 실행 순서가 아니다. 각 단계마다 **Gate 검문소**가 있어서 기준 미달 시 다음 단계로 진행을 차단한다. Gate A(목표 달성)와 Gate D(성능 계약)는 **항상 활성화**되는 베이스라인 Gate이며, Gate B·C·E·F·G는 필요에 따라 opt-in으로 추가한다. 배포 우선순위는 **Gate A > D > B > C/E/F > G** 순이다.

### 전체 파이프라인 흐름

@@HTML_START@@
<style>
.pipeline-wrap{margin:20px 0;}
.pipeline-row{display:flex;align-items:stretch;gap:0;}
.phase-card{flex:1;border-radius:10px;padding:16px;position:relative;}
.phase-arrow{display:flex;align-items:center;justify-content:center;flex-direction:column;padding:0 6px;flex-shrink:0;}
.phase-arrow-line{width:32px;height:2px;}
.phase-arrow-head{width:0;height:0;border-top:6px solid transparent;border-bottom:6px solid transparent;}
.phase-num{display:inline-block;border-radius:50%;width:22px;height:22px;text-align:center;line-height:22px;font-weight:700;font-size:12px;margin-right:6px;flex-shrink:0;}
.phase-title{font-weight:700;font-size:14px;margin-bottom:4px;display:flex;align-items:center;}
.phase-timing{font-size:11px;margin-bottom:10px;opacity:.75;}
.step-list{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:5px;}
.step-item{display:flex;gap:7px;align-items:flex-start;font-size:12px;line-height:1.4;}
.step-icon{flex-shrink:0;font-size:13px;margin-top:1px;}
.step-code{font-size:10px;font-family:monospace;border-radius:3px;padding:1px 4px;margin-top:2px;display:inline-block;}
.feedback-row{display:flex;align-items:center;margin-top:8px;padding:8px 16px;background:#f3e5f5;border:1px dashed #ab47bc;border-radius:8px;font-size:12px;color:#4a148c;gap:8px;}
</style>

<div class="pipeline-wrap">
<div class="pipeline-row">

  <!-- ① 개발 -->
  <div class="phase-card" style="background:#e8f5e9;border:2px solid #66bb6a;">
    <div class="phase-title" style="color:#1b5e20;">
      <span class="phase-num" style="background:#1b5e20;color:#fff;">①</span>개발 (로컬)
    </div>
    <div class="phase-timing" style="color:#388e3c;">커밋마다 · 즉시</div>
    <ul class="step-list">
      <li class="step-item" style="color:#1b5e20;"><span class="step-icon">🏷️</span><div><div>@eval.qa 데코레이터 적용</div><div>실행마다 자동 채점</div><span class="step-code" style="background:#c8e6c9;color:#1b5e20;">@eval.qa</span></div></li>
      <li class="step-item" style="color:#1b5e20;"><span class="step-icon">🧪</span><div><div>소수 케이스 로컬 실행</div><div>ground_truth 포함</div></div></li>
      <li class="step-item" style="color:#1b5e20;"><span class="step-icon">💾</span><div><div>results/ 결과 JSON 생성</div><span class="step-code" style="background:#c8e6c9;color:#1b5e20;">eval.save()</span></div></li>
      <li class="step-item" style="color:#1b5e20;"><span class="step-icon">🔍</span><div><div>TCR · 정확도 즉시 점검</div><span class="step-code" style="background:#c8e6c9;color:#1b5e20;">eval.summary()</span></div></li>
      <li class="step-item" style="color:#1b5e20;"><span class="step-icon">🚩</span><div><div><strong>Gate A+D 베이스라인</strong> 항상 활성</div><div>다른 Gate는 opt-in 추가</div></div></li>
    </ul>
  </div>

  <!-- 화살표 1→2 -->
  <div class="phase-arrow">
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-bottom:3px;">PR 제출</div>
    <div style="display:flex;align-items:center;">
      <div class="phase-arrow-line" style="background:#546e7a;"></div>
      <div class="phase-arrow-head" style="border-left:10px solid #546e7a;"></div>
    </div>
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-top:3px;">CI 트리거</div>
  </div>

  <!-- ② PR / CI -->
  <div class="phase-card" style="background:#e3f2fd;border:2px solid #42a5f5;">
    <div class="phase-title" style="color:#0d47a1;">
      <span class="phase-num" style="background:#0d47a1;color:#fff;">②</span>PR / CI
    </div>
    <div class="phase-timing" style="color:#1565c0;">PR마다 · GitHub Actions</div>
    <ul class="step-list">
      <li class="step-item" style="color:#0d47a1;"><span class="step-icon">📋</span><div><div>골든 데이터셋 100개 전수 실행</div></div></li>
      <li class="step-item" style="color:#0d47a1;"><span class="step-icon">💾</span><div><div>CI 결과 JSON 저장</div><span class="step-code" style="background:#bbdefb;color:#0d47a1;">eval.save()</span></div></li>
      <li class="step-item" style="color:#0d47a1;"><span class="step-icon">🚦</span><div><div>Gate 판정</div><span class="step-code" style="background:#bbdefb;color:#0d47a1;">agent-eval gate --tcr 85</span></div></li>
      <li class="step-item" style="color:#0d47a1;"><span class="step-icon">🚫</span><div><div>임계값 미달 → exit 1</div><div>PR 병합 차단</div></div></li>
      <li class="step-item" style="color:#0d47a1;"><span class="step-icon">🚩</span><div><div><strong>Gate A > D > B</strong> 우선 검증</div></div></li>
    </ul>
  </div>

  <!-- 화살표 2→3 -->
  <div class="phase-arrow">
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-bottom:3px;">gate() 통과</div>
    <div style="display:flex;align-items:center;">
      <div class="phase-arrow-line" style="background:#546e7a;"></div>
      <div class="phase-arrow-head" style="border-left:10px solid #546e7a;"></div>
    </div>
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-top:3px;">배포 승인</div>
  </div>

  <!-- ③ 운영 -->
  <div class="phase-card" style="background:#fff3e0;border:2px solid #ffa726;">
    <div class="phase-title" style="color:#e65100;">
      <span class="phase-num" style="background:#e65100;color:#fff;">③</span>운영 (프로덕션)
    </div>
    <div class="phase-timing" style="color:#ef6c00;">24/7 · 10% 샘플링</div>
    <ul class="step-list">
      <li class="step-item" style="color:#e65100;"><span class="step-icon">🎲</span><div><div>10% 랜덤 샘플링 평가</div><span class="step-code" style="background:#ffe0b2;color:#e65100;">sample_rate=0.1</span></div></li>
      <li class="step-item" style="color:#e65100;"><span class="step-icon">💾</span><div><div>50건마다 자동 저장</div><span class="step-code" style="background:#ffe0b2;color:#e65100;">auto_save=True</span></div></li>
      <li class="step-item" style="color:#e65100;"><span class="step-icon">🔔</span><div><div>품질 저하 즉시 슬랙 알림</div><span class="step-code" style="background:#ffe0b2;color:#e65100;">SimpleTaskAlertRule</span></div></li>
      <li class="step-item" style="color:#e65100;"><span class="step-icon">📡</span><div><div>Phoenix 실시간 트레이스</div><div>이상 패턴 자동 감지</div></div></li>
    </ul>
  </div>

  <!-- 화살표 3→4 -->
  <div class="phase-arrow">
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-bottom:3px;">프로덕션 결과</div>
    <div style="display:flex;align-items:center;">
      <div class="phase-arrow-line" style="background:#546e7a;"></div>
      <div class="phase-arrow-head" style="border-left:10px solid #546e7a;"></div>
    </div>
    <div style="font-size:10px;color:#546e7a;white-space:nowrap;margin-top:3px;">회귀 베이스라인</div>
  </div>

  <!-- ④ 개선 -->
  <div class="phase-card" style="background:#ede7f6;border:2px solid #7e57c2;">
    <div class="phase-title" style="color:#311b92;">
      <span class="phase-num" style="background:#311b92;color:#fff;">④</span>개선 (주간 회귀)
    </div>
    <div class="phase-timing" style="color:#4527a0;">매주 월요일 · 전수 평가</div>
    <ul class="step-list">
      <li class="step-item" style="color:#311b92;"><span class="step-icon">📋</span><div><div>골든 데이터셋 전수 평가</div><div>전 케이스 재실행</div></div></li>
      <li class="step-item" style="color:#311b92;"><span class="step-icon">📊</span><div><div>이전 주 지표 변화 측정</div><span class="step-code" style="background:#d1c4e9;color:#311b92;">compare() delta</span></div></li>
      <li class="step-item" style="color:#311b92;"><span class="step-icon">📉</span><div><div>회귀 감지 시 CI 실패</div><span class="step-code" style="background:#d1c4e9;color:#311b92;">agent-eval trend --fail-on-regression</span></div></li>
      <li class="step-item" style="color:#311b92;"><span class="step-icon">⚙️</span><div><div>드리프트 감지 시</div><div>재보정 파이프라인 트리거</div></div></li>
    </ul>
  </div>

</div>

<!-- 피드백 루프 -->
<div class="feedback-row">
  <span style="font-size:16px;">↩️</span>
  <strong>피드백 루프</strong> —
  주간 회귀 결과 → 골든셋 갱신 · 임계값 재보정 → ① 개발 단계로 환류
  <span style="margin-left:auto;font-size:11px;opacity:.7;">점선 화살표: 자동 트리거</span>
</div>
</div>
@@HTML_END@@

### 단계별 코드 예시

> **4단계 요약**: ① 개발(Gate A+D 로컬 검증) → ② CI(Gate A > D > B 순 자동 판정) → ③ 운영(10% 샘플링 + Gate E 보안 실시간 감시) → ④ 개선(Gate 기반 회귀 탐지 + 임계값 재보정)

**1단계: 개발**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
# dev/run_dev.py
from agent_evaluator import setup_otel, QuickEval

# 로컬 Phoenix 연결 시도 (없어도 동작)
try:
    setup_otel(endpoint="http://localhost:6006", service_name="dev-qa-agent")
    print("Phoenix에 연결되었습니다: http://localhost:6006")
except Exception:
    print("Phoenix 없이 실행합니다. (agent-eval monitor 실행 후 재시도)")

eval = QuickEval("results/")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

if __name__ == "__main__":
    agent("한국의 수도는?", ground_truth="서울")
    agent("Python을 만든 사람은?", ground_truth="귀도 반 로섬")
    eval.save()
    print(eval.summary())
```

**2단계: CI**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
# ci/run_evaluation.py
import json
import sys
from agent_evaluator import QuickEval

def main():
    eval = QuickEval("results/")

    @eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return call_llm(question)

    with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
        dataset = json.load(f)

    for pair in dataset["qa_pairs"][:100]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    eval.save()
    summary = eval.summary()
    print(f"TCR: {summary.get('tcr', 0) * 100:.1f}%")
    print(f"Accuracy: {summary.get('accuracy', 0) * 100:.1f}%")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**3단계: 운영 (프로덕션 에이전트)**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 알림 시스템
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

**4단계: 개선 (주간 회귀 + 자기개선 루프)**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
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
        print(f"TCR 변화: {comparison['delta'].get('tcr', 0) * 100:+.1f}%")
        print(f"Accuracy 변화: {comparison['delta'].get('accuracy', 0):+.2f}")
    except Exception:
        print("이전 주 결과 없음 — 첫 실행입니다.")

    # 임계값 게이팅
    result = current_eval.gate(tcr=80, accuracy=70, dry_run=True)
    if not result["passed"]:
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

- 기본 설치 한 줄로 LLMJudge, 대시보드, OTEL이 모두 포함되므로 추가 설치 없이 바로 평가를 시작할 수 있다

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
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

- 10줄 워크플로우로 모든 푸시와 PR에서 품질 게이팅이 자동 실행된다
- `python evaluate.py`에서 `eval.gate()`를 직접 호출하거나 별도 `agent-eval gate` 스텝으로 분리하는 두 방식 모두 동작한다
- TCR 80% 임계값은 처음 시작하기에 적절한 수준이며, 팀이 익숙해지면 서서히 높여가면 된다

완료 후 얻는 것: 기본 평가 자동화 + CI 게이팅

---

### 소규모 팀 2~5인 — 1주 도입

목표: 알림 + 대시보드 + 회귀 방지

**Day 1~2: 골든 데이터셋 구축**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
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

- 50개 케이스부터 시작해 `eval.save()`로 결과 파일을 저장하면 골든 데이터셋 빌드의 소스가 된다

```bash
# 골든 데이터셋 자동 빌드 (높은 점수 케이스 추출)
agent-eval dataset build results/ --min-score 0.85
```

- `--min-score 0.85`로 정확도 85% 이상인 케이스를 골든 데이터셋에 추출한다
- 추출된 케이스는 수동 검토 후 CI 데이터셋에 추가해 회귀 방지에 활용한다

**Day 3: 알림 규칙 설정**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 알림 시스템
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

- `SimpleTaskAlertRule`의 `condition` 람다에서 `tr.accuracy_score`, `tr.execution_time`, `tr.success` 등 TaskResult 필드를 조건으로 활용할 수 있다
- `cooldown=300`으로 5분 이내 중복 알림을 억제해 Slack 채널이 과부하되지 않게 한다
- `handler`에 Slack 웹훅 요청을 넣으면 품질 저하 즉시 팀에 알림이 발송된다

**Day 4~5: 대시보드 + 주간 리뷰**

```bash
# 대시보드 실행
agent-eval dashboard results/

# 주간 리뷰 스크립트 cron 등록
# 매주 월요일 09:00: python scripts/weekly_regression.py
```

- `agent-eval dashboard results/`는 해당 디렉토리의 모든 JSON 결과 파일을 자동으로 로드해 Harness Gate 대시보드를 실행한다
- cron으로 주간 회귀 스크립트를 자동화하면 매주 월요일 팀 리뷰 전에 최신 품질 리포트가 준비된다

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

- `-v /data/phoenix:/data`로 SQLite DB를 호스트 볼륨에 마운트하면 컨테이너를 재시작해도 트레이스 데이터가 보존된다
- 내부 도메인(`phoenix.internal`)을 DNS에 등록하면 에이전트 코드에서 환경 변수 한 줄(`OTEL_ENDPOINT`)만 변경하면 된다

**Week 2: GitHub Actions CI/CD 완전 통합**

```yaml
# .github/workflows/agent-quality-gate.yml (Chapter 18 참조)
# PR → 평가 → gate → PR 코멘트 자동 게시
```

- Chapter 18의 완전한 워크플로우를 그대로 복사해 사용하면 PR 코멘트 자동 게시까지 설정이 완료된다

**Week 3: 5-규칙 알림 + 이상 감지**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — AnomalyDetector 이상 탐지
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

- 5개 규칙을 우선순위별로 구분해 `task_failure`(장애)와 `security_threat`(보안)에는 PagerDuty·보안 전담 핸들러를 연결한다
- `cooldown` 값을 심각도에 따라 다르게 설정하면 보안 위협은 30초마다 빠르게 알리고 토큰 비용은 2분마다 느슨하게 알릴 수 있다
- 리스트 형태로 관리하면 규칙 추가·제거가 쉽고 `@agent_eval(alert_rules=rules)`에 그대로 전달할 수 있다

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
  agent-eval dataset build results/ --min-score 0.5  # 실패 케이스 포함 추출
  # 수동으로 검토 후 골든 데이터셋에 추가
```

- 각 단계에 시간 목표가 명시되어 있어 30분 이내에 해결 또는 롤백 결정을 내릴 수 있는 구조다
- Step 5의 `agent-eval dataset build results/ --min-score 0.5`는 낮은 점수 케이스까지 포함해 사고 원인 케이스를 골든 데이터셋에 추가하고 동일 문제의 재발을 방지한다
- Phoenix Tracing 필터(`ae.accuracy_score < 0.5`)를 미리 즐겨찾기에 저장해두면 사고 시 Step 2를 1분 안에 완료할 수 있다

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 예제 코드
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
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
# compare()로 트렌드 분석
from agent_evaluator import QuickEval

current = QuickEval("results/weekly/current/")
previous = QuickEval("results/weekly/previous/")

comparison = current.compare(previous)
print("지표 변화:")
for metric, delta in comparison["delta"].items():
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
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
from agent_evaluator import QuickEval

eval = QuickEval("results/")
summary = eval.summary()

metrics = {
    "tcr": summary.get("tcr", 0),
    "accuracy": summary.get("accuracy", 0) * 100,
    "p95_latency": summary.get("p95_latency", 0),
    "total_cost_usd": summary.get("total_cost_usd", 0),
    "quality_avg": summary.get("quality_avg", 0),
    "hallucination_rate": summary.get("hallucination_rate", 0),
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
# 출처: Evaluator_Examples/ch21_pipeline.py — 데코레이터 사용
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

- `EvalMetadata(extra={...})`에 이미지 관련 메타데이터를 추가하면 Phoenix 스팬 속성에 포함되어 이미지 유형별 성능 분석이 가능하다
- `task_type="qa"`를 유지하면서 `extra`에 멀티모달 정보를 넣는 방식으로 기존 평가 인프라를 그대로 활용할 수 있다

### DSPy로 프롬프트 자동 최적화 연계

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
from agent_evaluator import QuickEval
import dspy

# DSPy 프로그램과 Agent-Evaluator 연동
eval = QuickEval("results/")

@eval(task_type="qa", framework="dspy")
def dspy_agent(question: str, ground_truth: str = "") -> str:
    return dspy_program(question=question).answer
```

- `framework="dspy"`를 지정하면 DSPy 응답 객체에서 메타데이터를 자동으로 추출해 스팬 속성에 포함한다
- DSPy가 프롬프트를 최적화할 때마다 Agent-Evaluator로 Gate 점수를 비교하면 어느 최적화 버전이 더 나은지 데이터로 확인할 수 있다

DSPy의 최적화 결과를 Agent-Evaluator로 평가하고, 골든 데이터셋에서 검증하는 사이클을 자동화할 수 있다.

### 커스텀 Tracker 개발

팀 고유의 지표가 필요하다면 `BaseTracker`를 상속해 커스텀 트래커를 만들 수 있다.

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 예제 코드
from agent_evaluator import BaseTracker, TaskResult

class CustomerSatisfactionTracker(BaseTracker):
    """고객 만족도 추정 트래커 (응답 길이, 완성도 기반)"""

    def record(self, result: TaskResult) -> None:
        # 응답 길이 기반 만족도 추정 로직
        response_len = len(result.response or "")
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

## 21.6 드리프트 → 재보정 파이프라인

AI 에이전트는 배포 후에도 조용히 성능이 변한다. 모델이 업데이트되거나, 데이터가 달라지거나, 사용 패턴이 변하면 지표가 서서히 하락한다. 이것이 **드리프트(Drift)**다. 단순 모니터링으로는 부족하다. **드리프트를 감지하고 → 원인을 진단하고 → 자동으로 재보정(Recalibration)**하는 파이프라인이 필요하다.

### 4가지 드리프트 유형과 감지 신호

| 드리프트 유형 | 정의 | 감지 신호 (Harness Group) | agent-eval 지표 |
|------------|------|--------------------------|----------------|
| **데이터 드리프트** | 입력 분포 변화 | Gate A — TCR 점진적 하락 | `AccuracyEvaluator` score 추세 |
| **개념 드리프트** | 정답의 기준 변화 | Gate A — HallucinationRate 상승 | `HallucinationDetector` 추세 |
| **모델 드리프트** | 모델 버전 업데이트 | Gate C — Reproducibility 하락 | `RetryCorrectionTracker` 재시도율 |
| **운영 드리프트** | 인프라/부하 변화 | Gate D — P95 지연 상승 | `LatencyTracker` P95 추세 |

### 드리프트 감지 파이프라인

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — RunTrendAnalyzer 추세 분석
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

- `--window 14`로 최근 2주 데이터를 분석해 단기 노이즈를 제거하고 실질적인 드리프트만 감지한다
- `--fail-on-regression`이 `exit 1`을 반환하면 `$?` 체크로 즉시 재보정 스크립트를 트리거할 수 있다
- `--output-json drift_report.json`에 slope 값과 드리프트 방향이 저장되어 재보정 스크립트가 원인 유형을 판단하는 데 활용된다

### 임계값 재보정 — Wilson Score Interval 적용

드리프트 이후 새 기준선(baseline)을 재설정할 때, 최근 데이터로 Wilson Score 기반 신뢰구간 임계값을 재계산한다:

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 예제 코드
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

## 21.7 자기개선 루프 — 평가 → 진단 → 개선 3단계

최고 수준의 AI 시스템은 평가 결과를 다시 학습에 활용한다. 이것이 **자기개선 루프(Self-Improvement Loop)**다. Agent-Evaluator의 데이터를 기반으로 프롬프트·파인튜닝·Config을 자동으로 개선하는 3단계 파이프라인을 구성할 수 있다.

```
Stage 1: 지표 하락 감지          Stage 2: Gate별 원인 귀속        Stage 3: 개선 액션
─────────────────────         ─────────────────────────────   ──────────────────────────
RunTrendAnalyzer              Gate별 Tracker 드릴다운           결과에 따른 액션 선택
  ↓                              ↓                              ↓
TCR 하락 감지                  Gate A: 목표 달성 지표 확인      Gate A 낮음 → 프롬프트 개선
정확도 하락 감지               Gate D: 성능 계약 지표 확인      Gate D 높음 → 인프라 확장
P95 지연 상승 감지             Gate E: 보안 경계 지표 확인      Gate E 위반 → 보안 Config 강화
                               extra_metrics.harness_groups 참조
```

### Stage 1 — 지표 하락 감지 (RunTrendAnalyzer)

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — RunTrendAnalyzer 추세 분석
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
# 출처: Evaluator_Examples/ch21_pipeline.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor
import json

# 최근 실패 케이스 로드
with open("results/latest_eval.json") as f:
    eval_data = json.load(f)

# Gate별 집계 결과는 extra_metrics.harness_groups 키에 저장됨
# 예: eval_data["extra_metrics"]["harness_groups"]["A"]["gate"] → "PASS"/"WARN"/"FAIL"
harness = (eval_data.get("extra_metrics") or {}).get("harness_groups", {})
gate_a_status = (harness.get("A") or {}).get("gate", "?")
gate_d_status = (harness.get("D") or {}).get("gate", "?")
print(f"Gate A(목표달성): {gate_a_status}  Gate D(성능계약): {gate_d_status}")

tasks = eval_data.get("tasks", [])
failed = [t for t in tasks if not t.get("success", True)]

# Gate별 실패 분포 분석
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
# 출처: Evaluator_Examples/ch21_pipeline.py — SLAConfig · ThreatSeverityConfig
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
# 출처: Evaluator_Examples/ch21_pipeline.py — RunTrendAnalyzer 추세 분석
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

**기본 예제**: [`Evaluator_Examples/ch21_pipeline.py`](../../Evaluator_Examples/ch21_pipeline.py)

| 단계 | 섹션 | 내용 |
|------|------|------|
| 개발 | 1단계 | QuickEval + Layer 1 기초 검증 |
| CI   | 2단계 | Harness Gate 판정 + `agent-eval gate` |
| 운영 | 3단계 | 데코레이터 + 알림 + 이상 탐지 + 비용 추적 |
| 개선 | 4단계 | 골든셋 추출 + 추세 분석 + 자기개선 루프 |

```bash
python Evaluator_Examples/ch21_pipeline.py   # 전체 파이프라인 4단계 실행
agent-eval dashboard results/                # 결과 종합 확인
```

> **관련 챕터 예제**: 각 단계의 상세 예제는 해당 챕터에서 확인한다. CI/CD 게이팅 심화는 [Chapter 18 — `ch18_cicd_gate.py`](Chapter_18_CICD_품질게이팅.md), 배포 버전 결정은 [Chapter 20 — `ch20_deployment.py`](Chapter_20_프로덕션_배포전략.md), Phoenix OTEL 연동은 [Chapter 19 — `ch19_phoenix.py`](Chapter_19_Phoenix_OTEL_모니터링.md)에서 확인한다.

**기본 예제**: `Evaluator_Examples/ch21_pipeline.py`

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 전체 파이프라인 초기화
import socket, os
from agent_evaluator import setup_otel, PerformanceMonitor, QuickEval

# 1단계: Phoenix OTEL 설정 (PerformanceMonitor 생성 전)
try:
    socket.create_connection(("localhost", 6006), timeout=2)
    setup_otel(endpoint="http://localhost:6006", service_name="prod-agent")
except OSError:
    pass  # Phoenix 없는 환경에서는 OTEL 없이 동작

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
# 출처: Evaluator_Examples/ch21_pipeline.py, 3단계 — 데코레이터 + 알림 통합
from agent_evaluator import SimpleTaskAlertRule, EvalMetadata
from agent_evaluator.decorators import agent_eval
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

- `alert_rules`, `flush_every`, `EvalMetadata`를 하나의 데코레이터에 조합해 알림·자동저장·Gate B-G 지표를 동시에 처리한다
- `flush_every=50`은 50건마다 `save_to_file()`을 자동 호출해 데이터 손실 위험을 최소화한다

```python
# 출처: Evaluator_Examples/ch21_pipeline.py, 4단계 — 골든셋 + 추세 분석 + CI 게이팅
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
- 이 패턴이 Ch01~Ch15에서 다룬 모든 기능(Gate A-G 지표, 데코레이터, Phoenix OTEL, 알림, 이상 탐지, 골든셋)을 하나로 통합한 종합 파이프라인이다

```bash
# 종합 파이프라인 단일 실행 (개발 → CI → 운영 → 개선 전체)
python Evaluator_Examples/ch21_pipeline.py

# 추세 분석
agent-eval trend results/ --window 10 --output-json weekly.json

# 대시보드 종합 확인
agent-eval dashboard results/
```

**7개 예제 파이프라인 매핑**

| 파일 | 파이프라인 단계 | 핵심 출력 |
|------|---------------|-----------|
| ch01_first_eval | 개발: Gate A-D 검증 | TCR=43.1%, 54개 태스크, p95=5.20s |
| ch05_group_b + ch08_group_e | 개발: Gate B-E·보안 검증 | 3개 보안 위협, 14개 태스크 |
| ch13_frameworks | 통합 테스트: 프레임워크 비교 | 24개 태스크, 4개 프레임워크 TCR 비교 |
| ch12_decorators | CI: 데코레이터·QuickEval | TCR=57.1%, gate() 실패/성공 |
| ch16_alerts | 운영: 실시간 알림 | alert JSONL, feedback 추적 |
| ch10_group_g | 운영: 인프라 종합 | AnomalyDetector, CostTracker, GoldenSet |
| ch19_phoenix | 운영: OTEL·외부 평가 | Phoenix 스팬, DeepEval/Ragas 연동 |

**전체 파이프라인 실행 결과 요약 (v0.9.1 기준)**

```
=== 종합 파이프라인 실행 결과 ===

총 태스크: ch02(54) + ch05+ch08(14) + ch13(24) + ch12(14) + ch16(N) + ch10(28) + ch19(3) = 137+건
전체 평균 TCR: ~48%  |  전체 평균 정확도: ~0.66

CI 게이트 (--tcr 40 --accuracy 60): ✅ 통과
주간 트렌드: TCR +1.2%, 정확도 +0.008 (개선 중)
보안 위협: 3건 탐지 (ch08_group_e 기준)
골든 데이터셋: 12개 케이스 추출 (ch10_group_g 기준)

대시보드: http://localhost:8765 — 전체 결과 통합 조회 가능
Phoenix: http://localhost:6006 — OTEL 스팬 시각화 (API 키 필요)
```

### `ch18_cicd_gate.py` — 종합 파이프라인 CI/CD 게이팅

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — CI/CD 자동화 최소 검증
# 전체 파이프라인의 마지막 단계: 7개 Gate 각 1개 Config로 신속 검증 (실행 ~3초)
import subprocess, sys

def run_harness_gate(strict: bool = False) -> bool:
    """ch18_cicd_gate.py를 실행해 Gate 판정 결과를 반환한다."""
    cmd = ["python", "Evaluator_Examples/ch18_cicd_gate.py"]
    if strict:
        cmd.append("--strict")   # WARN도 FAIL로 처리
    result = subprocess.run(cmd, capture_output=True, text=True)
    summary_line = [l for l in result.stdout.splitlines() if l.startswith("{")]
    if summary_line:
        import json
        summary = json.loads(summary_line[-1])
        print("Gate 요약:", summary)  # {"A": "PASS", "B": "PASS", ...}
    return result.returncode == 0

# 파이프라인 단계별 실행
steps = [
    ("단위 평가",   "python Evaluator_Examples/ch03_harness_basics.py"),
    ("FAIL 검증",   "python Evaluator_Examples/ch04_group_a.py"),
    ("버전 비교",   "python Evaluator_Examples/ch20_deployment.py"),
]
for name, cmd in steps:
    print(f"[{name}] 실행 중...")
    # subprocess.run(cmd.split(), check=True)  # 실제 파이프라인에서 활성화

# 최종 Gate 검증 — FAIL 시 배포 차단
if not run_harness_gate(strict=True):
    print("❌ Harness Gate FAIL — 배포 파이프라인 중단")
    sys.exit(1)
print("✅ Harness Gate PASS — 배포 진행")
```

```bash
python Evaluator_Examples/ch18_cicd_gate.py           # 빠른 Gate 검증 (~3초)
python Evaluator_Examples/ch18_cicd_gate.py --strict  # WARN도 차단
```

### `ch20_deployment.py` — Gate 점수로 배포 버전 결정

두 `PerformanceMonitor`를 독립 인스턴스로 운영해 v1·v2 에이전트의 7개 Gate 점수를 나란히 비교하고, 어느 버전을 배포할지 자동으로 판정한다.

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 독립 monitor로 v1 vs v2 비교
from agent_evaluator import PerformanceMonitor, TTFTVariabilityConfig, CostPredictabilityConfig

# 두 버전의 독립 monitor — 서로 간섭하지 않음
monitor_v1 = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5),
)
monitor_v2 = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5, min_samples=5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5),
)
```

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — Gate별 점수 차이 출력
r1 = monitor_v1.generate_report().to_dict()
r2 = monitor_v2.generate_report().to_dict()
h1 = (r1.get("extra_metrics") or {}).get("harness_groups", {})
h2 = (r2.get("extra_metrics") or {}).get("harness_groups", {})

_BADGE = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}
for gk in "ABCDEFG":
    g1 = ((h1.get(gk) or {}).get("gate") or "?").upper()
    g2 = ((h2.get(gk) or {}).get("gate") or "?").upper()
    s1 = (h1.get(gk) or {}).get("score") or 0.0
    s2 = (h2.get(gk) or {}).get("score") or 0.0
    delta = (s2 - s1) * 100
    arrow = f"+{delta:.1f}%" if delta > 0.5 else (f"{delta:.1f}%" if delta < -0.5 else "  ─")
    print(f"  Gate {gk}  v1={_BADGE[g1]}{s1:.0%}  v2={_BADGE[g2]}{s2:.0%}  {arrow}")
# 예시 출력:
#   Gate A  v1=❌ 32%  v2=✅ 91%  +59.0%
#   Gate D  v1=❌ 41%  v2=✅ 88%  +47.0%
#   Gate E  v1=❌ 25%  v2=✅ 95%  +70.0%
```

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — 배포 결정 자동화
v1_fail = [g for g in "ABCDEFG" if ((h1.get(g) or {}).get("gate") or "?").upper() == "FAIL"]
v2_fail = [g for g in "ABCDEFG" if ((h2.get(g) or {}).get("gate") or "?").upper() == "FAIL"]

if v1_fail:
    print(f"  v1: ❌ 배포 차단 — Gate {v1_fail} FAIL")
if not v2_fail:
    print("  v2: ✅ 배포 승인 — 모든 필수 Gate 통과")

monitor_v1.save_to_file("10_version_v1")
monitor_v2.save_to_file("10_version_v2")
# → results/10_version_v1.json / 10_version_v2.json — 대시보드에서 나란히 비교
```

> **패턴 핵심**: 독립 `PerformanceMonitor` 인스턴스를 버전마다 생성 → 동일 Config로 동일 태스크 실행 → Gate 점수 차이가 버전 개선 근거가 된다.

> **팀 규모별 시작점**: 1인 개발자는 `ch12_decorators.py`만 실행하고 `agent-eval gate`를 GitHub Actions에 등록하는 것으로 하루 안에 시작할 수 있다. 소규모 팀은 ch02~ch13을 순차로 도입하고, 대규모 팀은 ch19_phoenix까지 포함한 전체 파이프라인을 운영한다.

---

## 에필로그 — 품질은 결국 습관이다

이 책을 통해 **Harness Engineering**의 전 과정을 살펴봤다. 3개 레이어(기반, 에이전틱, 하이브리드)와 58개 지표(25 Native Tracker + 33 Harness Config), 7개 Gate(A–G)로 구성된 평가 체계가 개발→CI→운영→개선 4단계 파이프라인의 각 검문소에서 에이전트를 검증하는 방식을 배웠다. 마지막으로 가장 중요한 이야기를 하고 싶다.

### AI 에이전트 평가는 도구가 아니라 문화다

Agent-Evaluator는 도구다. 도구는 잘못 쓰면 소음만 만들어낸다. 중요한 것은 팀이 "우리 에이전트의 품질을 어떻게 정의하고, 어떻게 측정하고, 어떻게 개선할 것인가"에 대해 끊임없이 대화하는 문화다.

처음에는 `QuickEval` 한 줄로 시작해도 된다. 중요한 것은 시작하는 것이다.

```python
# 출처: Evaluator_Examples/ch21_pipeline.py — QuickEval 평가
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

- **전체 사이클은 Harness Engineering의 4단계 파이프라인**이다. ① 개발(Gate A+D 베이스라인 로컬 검증), ② CI(Gate A > D > B 우선순위 자동 판정 · 골든 데이터셋 100개), ③ 운영(Gate E 보안 실시간 감시 · 10% 샘플링 · 실시간 스팬), ④ 개선(Gate 기반 회귀 탐지 · 임계값 재보정 · 자기개선 루프). 각 단계마다 Gate 검문소가 기준 미달 시 다음 단계 진행을 차단한다.

- **팀 규모별 도입**: 1인은 1일 안에 QuickEval + GitHub Actions로 시작한다. 소규모 팀은 1주에 골든 데이터셋 + 알림 + 대시보드를 추가한다. 대규모 팀은 1개월에 Phoenix 내부 서버 + CI/CD 완전 통합 + 전담 QA 루틴을 구축한다.

- **런북은 사전에 준비하라.** Severity 1 사고는 반드시 발생한다. "Phoenix에서 필터링 → 원인 분석 → 롤백 또는 핫픽스 → 회귀 케이스 추가"의 30분 대응 절차를 팀이 공유해야 한다.

- **성과 측정** 지표: 평가 사이클 시간, 프로덕션 사고 건수, 모델 교체 의사결정 속도, 골든 데이터셋 크기. 이 4가지를 정기적으로 추적하면 도입 효과를 객관적으로 증명할 수 있다.

- **드리프트 감지와 재보정** (§21.6): `RunTrendAnalyzer`로 주당 추세 변화율(slope)을 계산하고, `--fail-on-regression`이 `exit 1`을 반환하면 Wilson Score 기반으로 임계값을 재보정한다. 드리프트 감지 시간(MTTD) < 3일을 목표로 한다.

- **자기개선 루프** (§21.7): 지표 하락 감지 → Gate별 원인 귀속 → 프롬프트/인프라/보안 Config 개선 3단계. 루프당 TCR +5% 이상 개선을 KPI로 설정하고, 재발률 10% 이하를 목표로 한다.

- **품질은 도구가 아니라 습관이다.** Agent-Evaluator는 시작점이다. `QuickEval` 한 줄로 시작해서, 팀 고유의 지표와 기준을 추가하고, 골든 데이터셋을 쌓아가는 과정이 진짜 AI 에이전트 품질 문화다.
