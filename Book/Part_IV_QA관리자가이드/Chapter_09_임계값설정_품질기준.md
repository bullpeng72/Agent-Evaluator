# Chapter 9. 임계값 설정과 품질 기준 수립

> **이 챕터에서 배우는 것**
> - 좋은 임계값이란 무엇인지, 어떤 기준으로 설정해야 하는지 이해한다
> - 에이전트 유형별로 어떤 KPI를 어느 수준으로 관리해야 하는지 파악한다
> - `generate_gate_config()`로 데이터 기반 임계값을 자동 생성하는 방법을 익힌다
> - Warning / Error / Critical 3계층 알림 체계를 설계하고, 품질 SLA를 문서화한다
> - 초기 배포 후 2주 캘리브레이션 프로세스를 적용한다

---

## 9.1 좋은 임계값의 조건

임계값(Threshold)은 에이전트 품질 관리의 핵심 도구다. 그런데 임계값을 설정한다는 것은 생각보다 섬세한 작업이다. 너무 엄격하면 팀 전체가 알림 폭발에 지치고, 너무 느슨하면 진짜 문제를 놓친다.

### 너무 엄격한 임계값의 문제

TCR 임계값을 95%로 설정했다고 가정하자. 에이전트가 하루 1,000건을 처리하는데 50건만 실패해도 알림이 울린다. 그 50건 중 40건은 사용자가 입력을 잘못한 경우다. 결국 팀은 매일 수십 개의 알림을 받고, 대부분 무의미하다는 것을 알게 된다. 이른바 **알림 피로(Alert Fatigue)** 상태가 된다. 알림 피로 상태에서는 정말 중요한 알림이 와도 무시하게 된다.

### 너무 느슨한 임계값의 문제

반대로 TCR 임계값을 50%로 설정하면 에이전트가 절반 이상 실패하는 상황에서야 알림이 온다. 이미 사용자 불만이 쌓이고 서비스 신뢰가 떨어진 상태다. 진짜 문제를 놓치는 것은 알림이 없는 것보다 더 위험하다. 알림이 있다는 믿음 때문에 팀이 안심하고 있기 때문이다.

### 데이터 기반 임계값 vs 직관 기반 임계값

처음 서비스를 시작할 때는 데이터가 없다. 이때는 업계 일반 기준을 출발점으로 삼는 것이 좋다. Agent-Evaluator가 제공하는 기본 권장값은 수백 개의 프로덕션 에이전트를 분석한 결과다.

그러나 데이터가 쌓이기 시작하면 반드시 **데이터 기반으로 전환**해야 한다. 내 에이전트의 실제 성능 분포를 보고, 하위 5~10%를 걸러내는 수준으로 임계값을 설정하는 것이 현실적이다. `generate_gate_config()`가 바로 이 역할을 한다 — 현재 결과의 95% 수준을 자동으로 계산해준다.

**임계값 설정의 3가지 원칙:**

1. **보수적으로 시작하라** — 처음에는 느슨하게, 데이터가 쌓이면 점진적으로 강화
2. **측정 대상을 명확히 하라** — Latency는 평균이 아닌 P95 기준, Quality는 5점 척도
3. **정기적으로 갱신하라** — 월 1회 이상 실제 데이터 기반으로 재검토

---

## 9.2 에이전트 유형별 KPI 기준표

에이전트의 목적에 따라 어떤 지표를 중점적으로 관리해야 하는지가 다르다. 아래 표는 5가지 주요 에이전트 유형별 권장 임계값과 측정 방법을 정리한 것이다.

| 에이전트 유형 | TCR | Accuracy | Quality (0~5) | P95 Latency | Hallucination |
|-------------|-----|----------|---------------|-------------|---------------|
| **QA 챗봇** | ≥ 85% | ≥ 70% | ≥ 3.5 | ≤ 5초 | ≤ 5% |
| **RAG 검색** | ≥ 88% | ≥ 75% | ≥ 3.8 | ≤ 4초 | ≤ 3% (필수) |
| **Tool Use** | ≥ 80% | ≥ 65% | ≥ 3.2 | ≤ 10초 | ≤ 8% |
| **Security Agent** | ≥ 95% | ≥ 80% | ≥ 4.0 | ≤ 3초 | ≤ 1% |
| **Conversation** | ≥ 82% | ≥ 68% | ≥ 3.5 | ≤ 6초 | ≤ 5% |

**측정 방법 및 주의사항:**

- **TCR (Task Completion Rate):** `completion_score ≥ 0.8`인 태스크 비율. 단순 성공/실패가 아닌 부분 완료(0.3~0.8)도 구분한다.
- **Accuracy:** Token Overlap 40% + Jaccard 30% + LCS 20% + Char 10% 가중 평균. `ground_truth` 파라미터가 있을 때만 의미 있다.
- **Quality:** 5개 차원(Relevance, Completeness, Accuracy, Clarity, Usefulness) 평균. 10점 척도가 아님에 주의.
- **P95 Latency:** 상위 5% 느린 케이스의 응답시간. 평균값에 속지 말 것 — 평균 2초여도 P95가 15초일 수 있다.
- **Hallucination:** `enable_hallucination_detection=True` 또는 `rag_mode=True` 설정 시에만 수집된다. 기본적으로 비활성이다.

**Tool Use 에이전트의 추가 지표:**

도구를 많이 쓰는 에이전트는 Layer 2 지표도 함께 관리해야 한다.

| 지표 | 권장값 | 설명 |
|------|--------|------|
| Tool Selection F1 | ≥ 80% | 올바른 도구를 얼마나 잘 선택하는가 |
| Retry Success Rate | ≥ 60% | 실패 후 재시도 성공률 |
| Workflow Execution | ≥ 80% | 워크플로우 단계 완료율 |

📋 **QA 관리자 TIP:** 에이전트가 여러 유형을 동시에 처리한다면 가장 엄격한 기준을 전체에 적용하지 말 것. `task_type` 별로 별도 임계값 파일을 관리하는 것이 현실적이다.

---

## 9.3 임계값 자동 제안 — generate_gate_config()

새 에이전트를 배포하거나 처음 임계값을 설정할 때 가장 흔히 하는 실수는 "느낌상" 숫자를 정하는 것이다. 더 나은 방법은 충분한 평가를 먼저 실행한 후 현재 성능 분포를 기반으로 임계값을 자동 생성하는 것이다.

`generate_gate_config()`는 현재 결과의 **95% 수준**을 임계값으로 자동 제안한다. 즉, 현재 에이전트가 달성하는 성능에서 약간의 여유를 둔 현실적인 기준을 만들어준다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 충분한 케이스 실행 (최소 50개 권장)
for q, gt in test_dataset:
    agent(q, ground_truth=gt)

# 현재 결과 기반으로 임계값 자동 생성
eval.generate_gate_config("gate_config.json")
```

생성된 `gate_config.json` 예시:

```json
{
  "tcr": 87.3,
  "accuracy": 74.1,
  "quality": 3.8,
  "hallucination": 3.2,
  "p95_latency": 4.2,
  "generated_at": "2026-04-09T09:00:00",
  "based_on_tasks": 150
}
```

이 파일을 CI/CD에서 바로 활용할 수 있다:

```bash
# CLI에서 파일 기반 게이팅
agent-eval gate results/eval.json --config gate_config.json
```

**환경별로 다른 임계값 파일 관리:**

개발, 스테이징, 운영 환경은 요구 수준이 다르다. 파일을 별도로 유지하고 환경 변수로 선택하는 것이 좋다.

```bash
# 환경변수 DEPLOY_ENV에 따라 임계값 파일 선택
agent-eval gate results/eval.json --config gate_config.${DEPLOY_ENV}.json
```

| 환경 | TCR | Accuracy | Hallucination | P95 Latency |
|------|-----|----------|---------------|-------------|
| Dev | ≥ 70% | ≥ 55% | ≤ 15% | ≤ 15초 |
| Staging | ≥ 80% | ≥ 65% | ≤ 8% | ≤ 8초 |
| Prod | ≥ 85% | ≥ 70% | ≤ 5% | ≤ 5초 |

📋 **QA 관리자 TIP:** `generate_gate_config()`는 최소 50개 이상의 태스크 결과가 있을 때 의미 있는 값을 제안한다. 초기에는 위 환경별 권장값을 수동으로 설정하고, 2주 후 실데이터로 갱신하라.

---

## 9.4 Warning / Error / Critical 3계층 알림 설계

모든 문제가 동일한 긴급도를 갖지 않는다. "응답 품질이 조금 낮다"와 "서비스가 완전히 멈췄다"는 다른 수준의 대응이 필요하다. 3계층 알림 체계는 이 차이를 명확히 한다.

### Warning (경고) — 주의 필요, 서비스 계속 가능

성능이 정상 범위를 벗어나기 시작했지만 사용자 경험에 즉각적 영향은 없는 상태다. 조사는 필요하지만 서비스를 중단할 수준은 아니다.

- **예시:** Accuracy가 70%→65%로 하락, P95 Latency가 5초→7초로 증가
- **대응 시간 SLA:** 24시간 이내 원인 파악
- **알림 채널:** Slack #monitoring 채널 (조용한 알림)
- **쿨다운:** 300초 (5분) — 같은 문제로 5분에 한 번만 알림

### Error (오류) — 즉시 조사 필요

품질이 허용 범위 아래로 떨어진 상태. 사용자 일부가 나쁜 경험을 겪고 있을 가능성이 높다.

- **예시:** Accuracy 55% 미만, 재시도율 40% 초과, 보안 위협 탐지
- **대응 시간 SLA:** 4시간 이내 조치
- **알림 채널:** Slack #alerts + 온콜 담당자 DM
- **쿨다운:** 60초 — 지속 문제라면 1분마다 알림

### Critical (위험) — 서비스 중단 검토

서비스 전체가 정상 동작하지 않거나, 보안 사고가 발생한 상태다.

- **예시:** TCR 50% 미만, 권한 상승 탐지, 연속 실패 10건 이상
- **대응 시간 SLA:** 30분 이내 조치, 즉시 에스컬레이션
- **알림 채널:** Slack #incidents + 전화/PagerDuty
- **쿨다운:** 30초 — 위험 상황은 자주 알림

**3계층 임계값 예시표:**

| 지표 | Warning | Error | Critical |
|------|---------|-------|---------|
| accuracy_score | < 0.70 | < 0.55 | < 0.40 |
| execution_time (P95) | > 5초 | > 10초 | > 30초 |
| completion_score | < 0.80 | < 0.60 | < 0.40 |
| hallucination_rate | > 5% | > 15% | > 30% |
| 보안 위협 (privilege_escalation) | 1건 | 3건 | 1건 (즉시) |

📋 **QA 관리자 TIP:** Critical 알림은 절대 쿨다운을 길게 설정하지 말 것. 권한 상승(privilege_escalation) 탐지는 쿨다운 없이 매번 알림을 보내는 것이 원칙이다.

---

## 9.5 품질 SLA 문서 작성 가이드

임계값 설정이 끝났다면, 이를 팀 전체가 동의한 **SLA(Service Level Agreement) 문서**로 공식화해야 한다. SLA 문서가 없으면 "왜 이게 문제냐"는 논쟁이 반복된다.

### SLA 문서 템플릿

```markdown
# [서비스명] AI 에이전트 품질 SLA — v1.0
작성일: 2026-04-09 | 검토주기: 월 1회

## 1. 적용 범위
- 서비스: [서비스명]
- 에이전트 유형: QA / RAG / Tool Use
- 적용 환경: 운영(Prod)

## 2. 핵심 품질 지표 및 목표

| 지표 | 목표값 | 측정 방법 | 측정 도구 |
|------|--------|----------|---------|
| 태스크 완료율 (TCR) | ≥ 85% | completion_score ≥ 0.8 비율 | Agent-Evaluator |
| 응답 정확도 | ≥ 70% | Token F1 + Jaccard 혼합 | Agent-Evaluator |
| 응답 품질 | ≥ 3.5/5.0 | 5차원 품질 평가 | Agent-Evaluator |
| P95 응답시간 | ≤ 5초 | 95 백분위수 | Agent-Evaluator |
| 환각 발생률 | ≤ 5% | HallucinationDetector | Agent-Evaluator |
| 일일 비용 | ≤ $50 | TokenEconomyTracker | Agent-Evaluator |

## 3. 알림 계층 및 대응 SLA

| 계층 | 조건 | 알림 채널 | 대응 시간 |
|------|------|---------|---------|
| Warning | 지표 목표의 90% 이하 | Slack #monitoring | 24시간 |
| Error | 지표 목표의 75% 이하 | Slack #alerts + DM | 4시간 |
| Critical | 지표 목표의 50% 이하 | Slack #incidents + 전화 | 30분 |

## 4. 리뷰 주기

| 주기 | 내용 | 담당 |
|------|------|------|
| 매일 | 대시보드 5분 점검 | 온콜 담당자 |
| 매주 | 주간 품질 리뷰 + 전주 대비 분석 | QA 매니저 |
| 매월 | 임계값 재검토 + SLA 갱신 | QA 매니저 + 개발팀 |
| 분기 | 골든 데이터셋 재검토 | QA + 개발 |
```

📋 **QA 관리자 TIP:** SLA 문서는 팀 위키(Confluence, Notion 등)에 올리고, 매월 리뷰 시 버전을 올려라. 변경 이력이 남아야 나중에 "언제부터 기준이 바뀌었나"를 추적할 수 있다.

---

## 9.6 초기 배포 후 2주 캘리브레이션 프로세스

임계값을 처음 설정했다고 끝이 아니다. 실제 트래픽을 맞이하면 예상치 못한 패턴이 나타난다. 초기 2주는 **캘리브레이션 기간**으로 설정하고, 느슨한 임계값으로 데이터를 수집하는 것이 현명하다.

### 1주차: 느슨한 임계값으로 기준 데이터 수집

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 1주차: 느슨한 임계값 + 자동 저장
monitor = PerformanceMonitor(
    output_dir="results/week1/",
    auto_save=True,
    auto_save_interval=50,
)

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 운영 환경에서 실제 트래픽 평가
# 1주일 후 → results/week1/ 에 충분한 데이터 축적
```

1주차에는 알림도 최소화한다. 경고 임계값을 실제 목표보다 20~30% 낮게 설정해서 알림 폭발을 방지한다.

### 2주차: generate_gate_config()로 기준 갱신

```python
from agent_evaluator import QuickEval

# 1주차 데이터 기반으로 기준 생성
eval_week1 = QuickEval("results/week1/")
# week1 결과를 replay하여 분석
eval_week1.replay("results/week1/auto_save_latest.json")

# 95% 수준으로 임계값 자동 생성
eval_week1.generate_gate_config("gate_config_v1.json")

print("생성된 임계값:")
import json
with open("gate_config_v1.json") as f:
    config = json.load(f)
    for k, v in config.items():
        print(f"  {k}: {v}")
```

### 이후: 월 1회 정기 갱신

임계값은 살아있는 문서다. 모델이 바뀌고, 사용자 패턴이 바뀌고, 서비스 규모가 커지면 기준도 함께 진화해야 한다.

```
매월 1일 — generate_gate_config() 실행
         — 새 임계값 팀 리뷰 (5분 동기 미팅)
         — gate_config_prod.json 업데이트
         — SLA 문서 버전 업
```

📋 **QA 관리자 TIP:** 임계값이 갑자기 크게 달라졌다면 에이전트 성능이 바뀐 것인지, 평가 방식이 바뀐 것인지 확인하라. 두 달치 `gate_config.json`을 비교해서 갑작스러운 변화가 있으면 원인을 추적해야 한다.

---

## 이 챕터의 핵심

- **임계값은 "느슨하게 시작, 데이터로 강화"** — 처음에는 업계 기준으로 시작하고, 2주 후 `generate_gate_config()`로 실데이터 기반으로 전환한다
- **에이전트 유형마다 다른 KPI** — QA 챗봇은 Accuracy, RAG는 Hallucination, Tool Use는 Retry Success Rate를 중점 관리한다
- **3계층 알림 설계** — Warning(24시간)/Error(4시간)/Critical(30분)로 긴급도를 명확히 구분하고 각 계층별 대응 SLA를 정한다
- **SLA 문서화** — 임계값은 팀 합의 문서로 공식화하고 월 1회 리뷰해야 "기준이 뭐냐"는 논쟁이 사라진다
- **2주 캘리브레이션** — 신규 배포 후 1주는 느슨하게 데이터 수집, 2주차에 실데이터 기반 임계값으로 갱신하는 루틴을 따른다
