# Chapter 14. 임계값 설정과 품질 기준 수립

> **이 챕터에서 배우는 것**
> - 좋은 임계값이란 무엇인지, 어떤 기준으로 설정해야 하는지 이해한다
> - 에이전트 유형별로 어떤 KPI를 어느 수준으로 관리해야 하는지 파악한다
> - `generate_gate_config()`로 데이터 기반 임계값을 자동 생성하는 방법을 익힌다
> - Warning / Error / Critical 3계층 알림 체계를 설계하고, 품질 SLA를 문서화한다
> - 초기 배포 후 2주 캘리브레이션 프로세스를 적용한다

> 📖 **관련 레퍼런스**
> - **[Appendix I — 지표 비교 분석 및 선택 가이드](../Appendix/I_지표_비교분석_선택가이드.md)**: 에이전트 유형별 지표 선택 결정 트리 및 비용 프로파일 → §I.6 결정 트리 참조
> - **[Appendix G — AI 품질 평가 이론적 기초](../Appendix/G_AI평가_이론적기초.md)**: 이 챕터의 권장 임계값(TCR≥85%, Accuracy≥70%)이 도출된 이론적 근거 → §G.5 참조
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 각 지표의 권장 임계값 기본값 빠른 조회

---

## 14.0 임계값 설정 전에 알아야 할 것 — 숫자는 어디서 오는가

대시보드와 리포트에 표시되는 모든 숫자는 개발자가 작성한 Tracker + Config로부터 온다. 임계값을 설정하기 전에 이 출처를 이해하면 **"이 숫자가 왜 이 값인가"를 진단**할 수 있다.

```
개발자 코드                     Tracker 측정                QA 관리자가 보는 값
─────────────────────────────────────────────────────────────────────────
@agent_eval(monitor,
  task_type="qa",          →  AccuracyEvaluator       →  Gate A 정확도: 72%
  sla=SLAConfig(                                          Gate D P95: 3.1초
    p95_ms=2000),          →  LatencyTracker P95       →  Gate D: WARN ⚠️
  enable_security=True,    →  InputSanitizationTracker →  Gate E: PASS ✅
)
```

| QA 관리자가 보는 항목 | 원천 Tracker | 개발자 활성화 방법 |
|--------------------|------------|-----------------|
| Gate A — TCR, Accuracy | TaskCompletionTracker, AccuracyEvaluator | 기본 자동 (항상) |
| Gate B — Tool 패턴, 루프 | ToolCallAnalyzer, WorkflowExecutionTracker | `task_type="tool_use"` 또는 tool_calls 데이터 포함 시 |
| Gate C — 환각률, 재시도 | HallucinationDetector, RetryCorrectionTracker | `enable_hallucination_detection=True` |
| Gate D — P95 지연, 비용 | LatencyTracker, TokenEconomyTracker | 기본 자동 (항상) |
| Gate E — 보안 위협 건수 | InputSanitizationTracker 외 4종 | `enable_security_metrics=True` |
| Gate F — 다중에이전트 협업 | AgentCoordinationTracker, ToolSelectionTracker | agent_interactions 데이터 포함 시 |
| Gate G — LLM Judge 점수 | LLMJudge 7차원 | `enable_llm_judge=True` + API 키 |

> **데이터가 없는 Gate**: 담당 Tracker가 비활성이거나 입력 데이터가 없으면 해당 Gate 점수가 표시되지 않는다(회색 처리). "왜 Gate E가 보이지 않나?"라면 개발자에게 `enable_security_metrics=True` 설정을 요청하면 된다.

> 📖 **개발자-QA 협업 워크플로우**: [Chapter 3 §3.5](../Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md) — Tracker 활성화 → 초기 측정 → 임계값 협의 → Config 반영 → CI/CD 자동화의 5단계를 다룬다.

---

## 14.1 좋은 임계값의 조건

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

## 14.2 에이전트 유형별 KPI 기준표

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
- **Accuracy:** TokenOverlapF1 40% + Jaccard 30% + LCS 20% + CharSimilarity(Levenshtein) 10% 가중 평균. `ground_truth` 파라미터가 있을 때만 의미 있다.
- **Quality:** 5개 차원(Relevance, Completeness, Accuracy, Clarity, Usefulness) 평균. 10점 척도가 아님에 주의.
- **P95 Latency:** 상위 5% 느린 케이스의 응답시간. 평균값에 속지 말 것 — 평균 2초여도 P95가 15초일 수 있다.
- **Hallucination:** `enable_hallucination_detection=True` 또는 `rag_mode=True` 설정 시에만 수집된다. 기본적으로 비활성이다.

**Tool Use 에이전트의 추가 지표:**

도구를 많이 쓰는 에이전트는 Group B-G 지표도 함께 관리해야 한다.

| 지표 | 권장값 | 설명 |
|------|--------|------|
| Tool Selection F1 | ≥ 80% | 올바른 도구를 얼마나 잘 선택하는가 |
| Retry Success Rate | ≥ 60% | 실패 후 재시도 성공률 |
| Workflow Execution | ≥ 80% | 워크플로우 단계 완료율 |

📋 **QA 관리자 TIP:** 에이전트가 여러 유형을 동시에 처리한다면 가장 엄격한 기준을 전체에 적용하지 말 것. `task_type` 별로 별도 임계값 파일을 관리하는 것이 현실적이다.

### 14.2.1 어떤 지표 그룹을 활성화할 것인가? — 지표 선택 의사결정 트리

에이전트 유형별 KPI 기준표를 정했다면, 다음 단계는 **어떤 지표 그룹을 활성화할지**를 결정하는 것이다. 아래 의사결정 트리를 순서대로 따라가면 최소 비용으로 최대 커버리지를 얻을 수 있다.

```
[시작]
  │
  ▼
에이전트가 도구를 사용하는가?
  │
  ├─ NO → Group A-D 기반 지표만 활성 (TCR, Accuracy, Quality, Latency, Token, Hallucination*)
  │         *(hallucination은 RAG 경우에만)
  │
  └─ YES ─→ Group A-G 기반 + 에이전틱 지표 활성
              │
              ▼
            에이전트가 민감 데이터/외부 시스템에 접근하는가?
              │
              ├─ NO → Group A-G 기반 + 에이전틱 지표 유지
              │
              └─ YES → Group E 보안 지표 추가
                          enable_security_metrics=True

[계속]
  │
  ▼
Ground truth를 항상 가질 수 있는가?
  │
  ├─ YES → Group A-G 기반 지표로 충분 (낮은 비용)
  │
  └─ NO → LLM Judge 추가 (Group G)
            │
            ▼
          RAG 파이프라인인가?
            │
            ├─ NO → LLM Judge (5차원) + judge_sample_rate=0.1
            │
            └─ YES → LLM Judge (rag_mode=True, faithfulness 추가)
                       OR Ragas (더 정밀한 RAG 평가 필요 시)

[심화]
  │
  ▼
특정 도메인 기준이 필요한가? (의료, 법률, 금융 등)
  │
  └─ YES → judge_criteria=["domain_accuracy", "citation_quality", ...]
             (G-Eval 스타일 커스텀 기준)
```

**코드로 바로 적용:**

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# Case 1: 도구 없는 QA 챗봇 (Group A 기반만)
monitor = PerformanceMonitor(output_dir="results/")

# Case 2: Tool Use 에이전트 (Group A-B)
monitor = PerformanceMonitor(output_dir="results/")
# → 기본적으로 Group B 트래커(ToolCall, Retry 등)는 자동 수집됨

# Case 3: 보안 에이전트 (Group A-B + Group E)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,   # Group E 활성화
)

# Case 4: RAG + LLM Judge (Group A + Group G)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_llm_judge=True,
    judge_sample_rate=0.1,          # 10%만 채점 (비용 절감)
)

@agent_eval(monitor, task_type="information_retrieval",
            rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return retrieval_chain.invoke({"question": question, "context": context})
```

> 📖 **더 깊이**: 레이어 선택의 비용-정밀도 트레이드오프 분석은 → Appendix I §I.7 지표별 비용 프로파일

---

## 14.3 임계값 자동 제안 — generate_gate_config()

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

이 파일을 CI/CD에서 바로 활용할 수 있다. `agent-eval gate`는 임계값을 CLI 인수로 직접 전달한다:

```bash
# 생성된 gate_config.json 값을 읽어 CLI로 전달
TCR=$(python -c "import json; print(json.load(open('gate_config.json'))['tcr'])")
ACC=$(python -c "import json; print(json.load(open('gate_config.json'))['accuracy'])")
agent-eval gate results/eval.json --tcr $TCR --accuracy $ACC
```

**환경별로 다른 임계값 파일 관리:**

개발, 스테이징, 운영 환경은 요구 수준이 다르다. 파일을 별도로 유지하고 환경에 맞게 인수를 전달하는 것이 좋다.

```bash
# 환경별 임계값 적용 예시 (Prod)
agent-eval gate results/eval.json --tcr 85 --accuracy 70 --hallucination 5
# 환경별 임계값 적용 예시 (Dev)
agent-eval gate results/eval.json --tcr 70 --accuracy 55
```

| 환경 | TCR | Accuracy | Hallucination | P95 Latency |
|------|-----|----------|---------------|-------------|
| Dev | ≥ 70% | ≥ 55% | ≤ 15% | ≤ 15초 |
| Staging | ≥ 80% | ≥ 65% | ≤ 8% | ≤ 8초 |
| Prod | ≥ 85% | ≥ 70% | ≤ 5% | ≤ 5초 |

📋 **QA 관리자 TIP:** `generate_gate_config()`는 최소 50개 이상의 태스크 결과가 있을 때 의미 있는 값을 제안한다. 초기에는 위 환경별 권장값을 수동으로 설정하고, 2주 후 실데이터로 갱신하라.

---

## 14.4 Warning / Error / Critical 3계층 알림 설계

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

## 14.5 품질 SLA 문서 작성 가이드

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

## 14.6 초기 배포 후 2주 캘리브레이션 프로세스

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

## 14.7 Harness Config로 임계값을 코드로 선언하기

### 14.7.1 Config-as-Code 전환의 이점

지금까지 `agent-eval gate --tcr 85 --accuracy 70` CLI 파라미터나 `monitor.gate(tcr=85)` 호출로 임계값을 설정했습니다. 이 방식의 문제는 **배포 기준이 코드 외부**에 있다는 것입니다.

Harness Config로 전환하면:

| 기존 방식 | Harness Config 방식 |
|---------|-------------------|
| CLI 파라미터 (`--tcr 85`) | `InstructionConfig(min_completion_rate=0.85)` |
| 코드 외부에 기준 산재 | Git으로 기준 변경 이력 추적 |
| 에이전트 유형별 구분 어려움 | `task_types=["qa"]`로 유형별 기준 분리 |
| 재검토 시 어디를 봐야 하는지 불명확 | 단일 파일에서 전체 기준 조회 가능 |

### 14.7.2 에이전트 유형별 KPI를 Config로 선언

§14.2의 에이전트 유형별 KPI 기준표를 Config 코드로 변환합니다.

```python
from agent_evaluator.decorators import (
    InstructionConfig, ReproducibilityConfig, SLAConfig,
    ThreatSeverityConfig, ComplianceConfig, FaultToleranceConfig,
)

# ── QA 챗봇 ──────────────────────────────────────────────────────────
qa_harness = [
    InstructionConfig(min_completion_rate=0.85, min_accuracy=0.70, fail_on_violation=True),
    SLAConfig(max_p95_latency=5.0, fail_on_violation=True),
]

# ── RAG 검색 ─────────────────────────────────────────────────────────
rag_harness = [
    InstructionConfig(min_completion_rate=0.88, min_accuracy=0.75, fail_on_violation=True),
    SLAConfig(max_p95_latency=4.0, fail_on_violation=True),
    ReproducibilityConfig(min_consistency_rate=0.80, fail_on_violation=False),  # 모니터링만
]

# ── 보안 에이전트 ─────────────────────────────────────────────────────
security_harness = [
    InstructionConfig(min_completion_rate=0.95, min_accuracy=0.80, fail_on_violation=True),
    SLAConfig(max_p95_latency=3.0, fail_on_violation=True),
    ThreatSeverityConfig(max_severity="low", fail_on_violation=True),
    ComplianceConfig(standards=["GDPR"], fail_on_violation=True),
]

# ── 사용 ─────────────────────────────────────────────────────────────
@agent_eval(monitor, task_type="qa", harness_configs=qa_harness)
def qa_agent(question: str, ground_truth: str = "") -> str: ...

@agent_eval(monitor, task_type="information_retrieval",
            harness_configs=rag_harness, rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...
```

### 14.7.3 Wilson Score Interval — 통계적 임계값 설정

§14.3의 `generate_gate_config()`는 "현재 성능의 95% 수준"을 자동 계산합니다. 하지만 샘플 수가 적으면 이 값이 얼마나 신뢰할 수 있는지 알아야 합니다.

**Wilson Score Interval**은 관찰된 TCR이 "진짜 성능 범위" 어디에 있는지 95% 신뢰구간으로 추정합니다.

```python
import math

def wilson_lower_bound(successes: int, trials: int, z: float = 1.96) -> float:
    """Wilson Score 하한 — 보수적 TCR 임계값 추정"""
    if trials == 0:
        return 0.0
    p = successes / trials
    denominator = 1 + z**2 / trials
    center = p + z**2 / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2))
    return (center - margin) / denominator

# 실용 예시 — 동일한 90% TCR, 다른 신뢰구간
print(f"n=20,  TCR=90%:  Wilson 하한 = {wilson_lower_bound(18, 20):.1%}")   # ~72%
print(f"n=100, TCR=90%:  Wilson 하한 = {wilson_lower_bound(90, 100):.1%}")  # ~83%
print(f"n=500, TCR=90%:  Wilson 하한 = {wilson_lower_bound(450, 500):.1%}") # ~87%
```

**임계값 설정에의 적용:**

| 측정 샘플 수 | 전략 | 임계값 설정 |
|------------|------|-----------|
| < 50건 | 보수적: Wilson 하한 사용 | `min_completion_rate = wilson_lower_bound(성공수, n)` |
| 50~200건 | 절충: 관찰값과 Wilson 하한 평균 | `min_completion_rate = (관찰TCR + wilson_하한) / 2` |
| 200건 이상 | 신뢰: 관찰값 - 5% 마진 | `min_completion_rate = 관찰TCR - 0.05` |

```python
# 실무 패턴: 샘플 수에 따른 자동 임계값 결정
def adaptive_threshold(
    successes: int,
    trials: int,
    margin: float = 0.05,
) -> float:
    """샘플 수에 따라 Wilson 하한 또는 관찰값 기반 임계값 반환"""
    if trials < 50:
        return wilson_lower_bound(successes, trials)
    elif trials < 200:
        observed = successes / trials
        wilson = wilson_lower_bound(successes, trials)
        return (observed + wilson) / 2
    else:
        observed = successes / trials
        return max(0.0, observed - margin)

# 2주 캘리브레이션 완료 후 Config 자동 생성
report = monitor.generate_report()
total = int(report.total_tasks)
successful = int(total * report.task_completion_rate / 100)
threshold = adaptive_threshold(successful, total)

instruction_cfg = InstructionConfig(
    min_completion_rate=threshold,
    fail_on_violation=True,
)
print(f"캘리브레이션 임계값: {threshold:.1%} (n={total})")
```

> 📋 **QA 관리자 TIP**: "우리 에이전트 TCR이 90%인데 임계값을 85%로 설정했다"는 것만으로는 충분하지 않습니다. "n=25에서 관찰한 90%는 Wilson 하한이 72%"이므로, 실제로는 72~100% 어딘가에 있습니다. 배포 초기 2주 동안은 Wilson 하한을 사용해 보수적으로 판단하고, 데이터가 200건 이상 쌓이면 관찰값 기반으로 전환하세요.

---

## 이 챕터의 핵심

- **임계값은 "느슨하게 시작, 데이터로 강화"** — 처음에는 업계 기준으로 시작하고, 2주 후 `generate_gate_config()`로 실데이터 기반으로 전환한다
- **에이전트 유형마다 다른 KPI** — QA 챗봇은 Accuracy, RAG는 Hallucination, Tool Use는 Retry Success Rate를 중점 관리한다
- **3계층 알림 설계** — Warning(24시간)/Error(4시간)/Critical(30분)로 긴급도를 명확히 구분하고 각 계층별 대응 SLA를 정한다
- **SLA 문서화** — 임계값은 팀 합의 문서로 공식화하고 월 1회 리뷰해야 "기준이 뭐냐"는 논쟁이 사라진다
- **2주 캘리브레이션** — 신규 배포 후 1주는 느슨하게 데이터 수집, 2주차에 실데이터 기반 임계값으로 갱신하는 루틴을 따른다

---

## 실전 예제

`06_operational.py`의 `AnomalyDetector`와 `CostTracker` 섹션은 임계값 기반 알림과 비용 제어가 실제 코드에서 어떻게 구성되는지 보여준다. 임계값 캘리브레이션과 에이전트 유형별 KPI 설정의 실제 패턴을 확인할 수 있다.

**파일**: `Evaluator_Examples/06_operational.py`

**핵심 코드 (출처: `Evaluator_Examples/06_operational.py`)**

```python
# 출처: Evaluator_Examples/06_operational.py, 섹션 1 — AnomalyDetector 기준선 학습
from agent_evaluator import AnomalyDetector, create_taskresult
import random

# 기준선 태스크 30개 생성 (정상 범위)
baseline_results = []
for i in range(30):
    result = create_taskresult(
        task_id=f"baseline_{i}",
        question="테스트 질문",
        response="정상 응답",
        ground_truth="정상 응답",
        execution_time=random.gauss(1.5, 0.3),  # 평균 1.5초, 표준편차 0.3초
        task_type="qa",
    )
    baseline_results.append(result)

# 이상값 태스크 1개 (명백한 이상)
anomaly_result = create_taskresult(
    task_id="anomaly_001",
    question="테스트 질문",
    response="느린 응답",
    ground_truth="정상 응답",
    execution_time=15.0,  # 평균보다 10배 이상 지연
    task_type="qa",
)

# AnomalyDetector: Z-Score 기반 이상 탐지
detector = AnomalyDetector()
events = detector.scan(baseline_results + [anomaly_result])

for event in events:
    explanation = detector.explain_event(event)
    print(f"이상 감지: {explanation['metric']} — Z-Score {explanation['z_score']:.1f}")
    print(f"임계값: {explanation['threshold']}, 실제값: {explanation['actual_value']}")
```

- `AnomalyDetector`는 Z-Score 통계로 지연시간 스파이크, 정확도 급락, 토큰 급증을 자동 탐지한다
- 기준선 태스크 30개로 정상 범위의 평균(μ)과 표준편차(σ)를 학습한다
- `explain_event()`는 어떤 지표가, 얼마나 벗어났는지를 사람이 읽기 쉬운 형태로 반환한다

```python
# 출처: Evaluator_Examples/06_operational.py, 섹션 2 — CostTracker + AdaptivePolicy
from agent_evaluator import CostTracker, AdaptivePolicy, SamplingStage

# SamplingStage는 Enum (DEFAULT / ANOMALY / BUDGET_EXCEEDED)
# AdaptivePolicy: 이상 감지 상태에 따라 샘플링률 자동 조정
policy = AdaptivePolicy(
    default_sample_rate=0.1,   # 기본: 전체의 10%만 LLM Judge 실행
    anomaly_sample_rate=1.0,   # 이상 감지 시 100% 전수 평가로 전환
    budget_per_day=10.0,       # 일일 LLM API 비용 상한
    alert_at=0.8,              # 예산 80% 도달 시 알림
)

tracker = CostTracker(budget_per_day=10.0, alert_at=0.8)

# LLM Judge 호출 시마다 비용 기록
for i in range(10):
    # 현재 샘플링 비율 기준으로 실행 여부 결정
    if policy.current_sample_rate >= 1.0 or (i % 10 == 0):
        tracker.record(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            cost_usd=0.001,
            input_tokens=200,
            output_tokens=50,
        )

# 이상 감지 발생 시 전수 평가 모드로 전환
policy.enter_anomaly_mode(reason="accuracy 급락 감지")
print(f"이상 모드 전환: sample_rate={policy.current_sample_rate:.0%}")
print(f"오늘 비용: ${tracker.get_today_cost():.4f} USD")
print(f"예산 초과 여부: {tracker.is_budget_exceeded()}")
```

- `AdaptivePolicy`는 평상시 낮은 샘플링률로 비용을 절감하고, 이상 감지 시 `enter_anomaly_mode()`를 호출해 전수 평가로 전환한다
- `SamplingStage`는 `DEFAULT` / `ANOMALY` / `BUDGET_EXCEEDED` 세 상태를 가지는 Enum이다
- `CostTracker.record()`로 비용을 기록하고, `is_budget_exceeded()`로 예산 초과 여부를 확인한다
- `budget_per_day`를 초과하면 `policy.current_sample_rate`가 자동으로 0으로 내려간다

```bash
python Evaluator_Examples/06_operational.py
```

**예제 구성**

| 섹션 | 내용 | 연관 기능 |
|------|------|-----------|
| 섹션 2 | `AnomalyDetector` 이상 탐지 설정 | Z-Score 기반 자동 임계값 계산 |
| 섹션 3 | `CostTracker` + `AdaptivePolicy` | 일일 예산 임계값, 모델 자동 전환 |
| 섹션 4 | `AlertEngine` 규칙 설정 | TCR/정확도/레이턴시 임계값 알림 |
| 섹션 5 | `GoldenSetBuilder` 품질 기준 | `accuracy_score >= 0.85` 캘리브레이션 기준 |

**실행 결과 (v0.8.2 기준)**

```
# 06_operational.py 실행 (28개 태스크)
AnomalyDetector: latency_spike 2건 탐지 (Z-Score > 2.0)
CostTracker: 총 비용 $0.0000 (mock 모드)
AdaptivePolicy: 예산 임계값 $10.00/일 설정
AlertEngine: accuracy_below_threshold 0건, latency_above_5s 0건

TCR=46.1% | 평균 정확도=0.681 | 평균 레이턴시=1.47s
```

> **캘리브레이션 전략**: 신규 에이전트는 첫 2주간 `AnomalyDetector`를 `baseline_window=100`으로 설정하고 데이터를 수집한다. 이후 `generate_gate_config()`가 실제 분포 기반 임계값을 제안한다. 챕터 9에서 설명한 "느슨하게 시작, 데이터로 강화" 패턴이 06_operational.py 섹션 2~3에 그대로 구현되어 있다.
