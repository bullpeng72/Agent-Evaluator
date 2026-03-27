# Agent-Evaluator 제품 로드맵
> v0.6.3 기준 · 최종 업데이트 2026-03-27

---

## 목차

1. [현황 진단](#1-현황-진단)
2. [구조 전환 방향](#2-구조-전환-방향)
3. [Phase 1 — 검증 완성](#3-phase-1--검증-완성-4-6주)
4. [Phase 2 — 운영 모니터링](#4-phase-2--운영-모니터링-6-8주)
5. [Phase 3 — 지속적 개선 루프](#5-phase-3--지속적-개선-루프-8-12주)
6. [전체 타임라인](#6-전체-타임라인)
7. [우선순위 결정 근거](#7-우선순위-결정-근거)
8. [성공 지표](#8-성공-지표)

---

## 1. 현황 진단

### 라이프사이클별 효용 평가 (v0.6.3 기준)

| 단계 | 평가 | 핵심 강점 | 핵심 공백 |
|------|------|-----------|-----------|
| **개발** | ★★★★☆ | 지표 즉시 가시화, LLM Judge로 ground_truth 불필요 | 멀티턴·스트리밍 미지원 |
| **검증** | ★★★★☆ | 골든셋 회귀, 임계값 관리, LLM Judge 자동 채점 | CI 자동 통과/실패 미지원 |
| **운영** | ★★☆☆☆ | 배치 사후 분석, 보안 감사 | 실시간 모니터링·알림 전무 |

### 현장 투입 가능 비율 (지표별, v0.6.3 기준)

```
TCR / Latency / TokenEconomy   ████████████████████  100%  (자동 수집)
ToolCall / Security            ██████████████░░░░░░   70%  (enable 플래그)
Accuracy / Quality             ████████████████░░░░   80%  (LLM Judge로 ground_truth 불필요 — v0.6.3 개선)
Hallucination (Layer 1)        ██████░░░░░░░░░░░░░░   30%  (RAG 컨텍스트 필요)
AgentCoordination / Workflow   ████░░░░░░░░░░░░░░░░   20%  (프레임워크 래퍼 필요)
멀티턴 대화 평가               ░░░░░░░░░░░░░░░░░░░░    0%  (미구현 — Phase 1-C)
실시간 운영 모니터링           ░░░░░░░░░░░░░░░░░░░░    0%  (미구현 — Phase 2)
```

### 근본 원인 — 측정 시점의 구조적 한계

```
현재 (Pull 모델):
  에이전트 실행 → 결과 저장 → 파일 기록 → 대시보드 열람
  ↑                                              ↑
  실행 시점                               수 분 ~ 수 시간 후

목표 (Push 모델):
  에이전트 실행 → 즉시 평가 → 임계값 비교 → 이상 감지 → 알림
  ↑                               ↑
  실행 시점                    동일 요청 처리 중
```

---

## 2. 구조 전환 방향

### 핵심 설계 원칙

1. **기존 API 완전 보존** — `record_task()`, `monitor.task()` 등 현재 인터페이스 변경 없음
2. **opt-in 방식** — 새 기능은 모두 플래그 또는 별도 임포트로 활성화
3. **비용 통제 우선** — LLM 기반 평가는 샘플링 정책 필수 적용
4. **레이어 독립성 유지** — Layer 1/2는 외부 의존성 없이 동작 유지

### 신규 모듈 구조 (전체 완성 시)

```
agent_evaluator/
├── core/trackers/          ← 기존 (v0.6.2에서 분리 완료)
├── streaming/              ← Phase 2 신규
│   ├── evaluator.py        ← StreamingEvaluator
│   └── middleware.py       ← FastAPI/ASGI 미들웨어
├── alerts/                 ← Phase 2 신규
│   ├── engine.py           ← AlertEngine, AlertRule
│   └── handlers.py         ← Slack, Webhook, Email
├── anomaly/                ← Phase 3 신규
│   └── detector.py         ← AnomalyDetector
├── datasets/               ← Phase 3 확장
│   ├── builder.py          ← GoldenSetBuilder (신규)
│   └── korean_rag_*.py     ← 기존 유지
└── integrations/
    └── llm_judge.py        ← ✅ Phase 1-A 구현 완료 (v0.6.3)
```

---

## 3. Phase 1 — 검증 완성 (4~6주)

> 현재 가장 강한 구간인 "검증"을 실무 투입 가능 수준으로 완성

---

### 1-A. LLM-as-Judge 평가 엔진 ✅ 구현 완료 (v0.6.3)

**목표**: `ground_truth` 없이도 응답 품질을 자동 채점

**배경**:
현장 에이전트의 90%는 정해진 정답이 없는 개방형 질의를 처리한다.
기존 SDK는 `ground_truth` 없으면 `accuracy = 0`, `quality` 점수도 신뢰 불가한 상태.
LLM Judge가 없으면 오픈도메인 에이전트에는 TCR/Latency/Token 3개 지표만 유효하다.

**사용 패턴**:

```python
# Before — ground_truth 필수
monitor.accuracy_evaluator.add_evaluation(
    task_id="t1",
    ground_truth="서울",   # 없으면 측정 불가
    prediction=response,
)

# After — LLM이 judge 역할 (v0.6.3)
monitor = PerformanceMonitor(
    enable_llm_judge=True,
    # judge_model 생략 → agent-eval init 설정(OPENAI_MODEL/ANTHROPIC_MODEL) 자동 반영
    judge_sample_rate=0.1,      # 10% 샘플링 (비용 제어)
    judge_budget_per_day=5.0,   # 일 $5 한도
)
with monitor.task("t1", "qa", question=question) as t:
    t.response = agent.run(question)
    # ground_truth 없어도 judge가 3차원 자동 채점
    # → completeness(완결성), relevance(관련성), factual_consistency(사실 일관성)
```

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `LLMJudge` (`integrations/llm_judge.py`) | ✅ |
| 평가 차원 | 완결성(0-5) · 관련성(0-5) · 사실 일관성(0-5) | ✅ |
| 지원 모델 | Claude (Haiku/Sonnet) · OpenAI (gpt-4o-mini/gpt-4o) | ✅ |
| 비용 제어 | `judge_sample_rate` · `budget_per_day` 한도 | ✅ |
| init 연동 | `agent-eval init` 모델 설정 자동 반영 (`OPENAI_MODEL`/`ANTHROPIC_MODEL`) | ✅ |
| PerformanceMonitor 통합 | `enable_llm_judge`, `judge_model`, `judge_sample_rate`, `judge_budget_per_day` 파라미터 | ✅ |
| record_task() 자동 트리거 | question+response 있을 때 sample_rate 기반 자동 호출 | ✅ |
| TaskResult 직렬화 | `TaskResult.llm_judge`, `TaskResult.context` 필드 추가 → JSON 자동 포함 | ✅ |
| 대시보드 | Quality 탭 "LLM Judge 점수" 섹션 (KPI 4개 + 태스크별 테이블) | ✅ |
| loader.py | `LLMJudgeData` 데이터클래스 + `_parse_llm_judge()` 파서 | ✅ |
| Public API | `from agent_evaluator import LLMJudge` 직접 사용 가능 | ✅ |

**실제 구현 시 변경사항 (계획 대비)**:

| 항목 | 계획 | 실제 |
|------|------|------|
| 구현 위치 | `LLMEvaluationHelper` 확장 | 독립 클래스 `LLMJudge` — 더 나은 분리 |
| 기본 모델 | `claude-haiku-4-5-20251001` 하드코딩 | `None` → `agent-eval init` 설정 자동 감지 |
| 릴리스 버전 | v0.7.0 예정 | v0.6.3으로 조기 출시 |

**효과**: Accuracy/Quality 지표 현장 투입 가능 비율 40% → 80% 향상

---

### 1-B. CI/CD 게이팅 CLI

> 상태: **미구현** (다음 구현 대상)

**목표**: 평가 결과가 자동으로 릴리스 차단 기준이 되도록

**배경**:
검증 결과가 파일로만 저장되고 CI 파이프라인과 연결되지 않으면
형식적 QA에 그친다. 실제로 품질 기준 미달 시 배포가 차단되어야 한다.

**사용 패턴**:

```bash
# GitHub Actions / GitLab CI / Jenkins 통합
- name: Agent Quality Gate
  run: |
    python run_eval_suite.py --output results/ci_run.json
    agent-eval gate results/ci_run.json \
      --tcr 85 \
      --accuracy 70 \
      --p95-latency 3.0 \
      --hallucination 5 \
      --fail-on-regression 10

# 종료 코드
# 0 — 모든 기준 통과
# 1 — 임계값 기준 미달
# 2 — 이전 버전 대비 회귀 감지 (--fail-on-regression)
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 CLI | `agent-eval gate <result_file> [--옵션]` |
| 기준선 관리 | `results/baseline.json` 자동 저장 (브랜치별) |
| 회귀 감지 | `(현재 - 기준선) / 기준선 > 임계값` |
| 출력 형식 | 터미널 표 + JUnit XML (CI 시스템 호환) |
| 설정 파일 | `.agent-eval-gate.yaml` (프로젝트 루트) |

**기대 효과**: 개발팀이 매 PR마다 자연스럽게 SDK를 사용하게 되어 정착 가속

---

### 1-C. 멀티턴 대화 평가

> 상태: **미구현**

**목표**: 챗봇·대화형 에이전트의 핵심 품질 측정

**배경**:
현재 `TaskResult`는 단일 입출력(1 input → 1 output) 구조.
대화형 에이전트의 핵심 품질인 맥락 유지·일관성·목적 달성은 측정 불가하다.

**사용 패턴**:

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor()

with monitor.conversation("session_001") as conv:
    r1 = agent.chat("파이썬 비동기 처리 방법 알려줘")
    conv.turn(user="파이썬 비동기 처리 방법 알려줘", agent=r1)

    r2 = agent.chat("방금 설명한 방법의 단점은?")
    conv.turn(user="방금 설명한 방법의 단점은?", agent=r2)

    r3 = agent.chat("asyncio.gather 예시 코드 보여줘")
    conv.turn(user="asyncio.gather 예시 코드 보여줘", agent=r3)

# 자동 측정 지표
# - context_retention   : 이전 턴 내용을 후속 응답에 참조하는 비율
# - topic_coherence     : 대화 주제 일관성 (벗어남 감지)
# - progressive_depth   : 후속 질문이 이전 답변 위에 쌓이는지
# - session_completion  : 사용자의 대화 목적 달성 추정
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `ConversationSession` (`core/trackers/conversation.py`) |
| 측정 지표 | 맥락 유지율 · 주제 일관성 · 점진적 심화 · 세션 완결성 |
| 기존 통합 | `PerformanceMonitor.conversation()` 컨텍스트 매니저 |
| 대시보드 | "대화 세션" 탭 신규 추가 |

---

## 4. Phase 2 — 운영 모니터링 (6~8주)

> 실시간 평가 엔진 구축 — SDK의 가장 큰 공백 해소

---

### 2-A. 스트리밍 평가 엔진

> 상태: **미구현**

**목표**: 에이전트 실행 중 실시간 품질 측정

**배경**:
현재는 실행 완료 후 파일 저장 → 대시보드 확인 순서.
운영 모니터링은 요청마다 즉시 평가가 필요하며,
문제 발생 시 분 단위 인지가 아닌 초 단위 인지가 요구된다.

**사용 패턴**:

```python
from agent_evaluator.streaming import StreamingEvaluator, AgentEvalMiddleware

evaluator = StreamingEvaluator(
    monitor=monitor,
    flush_interval=60,          # 60초마다 지표 집계 및 저장
    alert_handler=alert_engine, # Phase 2-B와 연동
)

# FastAPI 미들웨어로 기존 코드 변경 없이 삽입
app.add_middleware(
    AgentEvalMiddleware,
    evaluator=evaluator,
    sample_rate=1.0,            # TCR/Latency/Token: 100%
    judge_sample_rate=0.05,     # LLM Judge: 5% (비용 제어)
)

# 각 요청마다 자동 처리
# 1. execution_time 측정 (미들웨어 레벨)
# 2. token_usage 수집 (API 응답 헤더)
# 3. TCR 슬라이딩 윈도우 업데이트
# 4. 임계값 비교 → 위반 시 AlertEngine 호출
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `StreamingEvaluator` (`streaming/evaluator.py`) |
| ASGI 미들웨어 | FastAPI / Starlette 지원 (`streaming/middleware.py`) |
| 집계 단위 | 슬라이딩 윈도우 — 1분 · 5분 · 1시간 |
| 저장 방식 | 기존 `PerformanceMonitor` 백엔드 공유 |
| 의존성 추가 | `[streaming]` extras (`starlette`, `asyncio`) |

---

### 2-B. 알림 시스템

> 상태: **미구현**

**목표**: 품질 임계값 위반 시 즉시 알림

**배경**:
현재는 대시보드를 능동적으로 열어봐야만 문제를 알 수 있다.
운영 환경에서는 이상 발생 → 자동 알림 → 조치 흐름이 필수다.

**사용 패턴**:

```python
from agent_evaluator.alerts import AlertEngine, SlackHandler, WebhookHandler

alert_engine = AlertEngine(monitor)

alert_engine.add_rule(
    name="TCR 급락",
    condition=lambda m: m.tcr_5min < 70,
    cooldown=300,                          # 5분 쿨다운 (중복 알림 방지)
    handler=SlackHandler(
        webhook_url=os.getenv("SLACK_WEBHOOK")
    ),
    severity="critical",
)
alert_engine.add_rule(
    name="P95 지연 초과",
    condition=lambda m: m.p95_latency > 5.0,
    handler=WebhookHandler(url=os.getenv("PAGERDUTY_URL")),
    severity="warning",
)
alert_engine.add_rule(
    name="보안 위협 급증",
    condition=lambda m: m.security_threat_rate_1h > 5,
    handler=SlackHandler(webhook_url=os.getenv("SLACK_SEC_CHANNEL")),
    severity="critical",
)
```

**알림 메시지 예시 (Slack)**:

```
🚨 [CRITICAL] Agent-Evaluator 알림
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
규칙: TCR 급락
현재: TCR 5분 평균 62.3%  (기준: 70%)
추세: 최근 15분 연속 하락 ↓
영향: 마지막 23개 요청 중 9개 실패
시각: 2026-03-27 14:32:11 KST
대시보드: http://localhost:8766/dashboard
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 핵심 클래스 | `AlertEngine`, `AlertRule`, `AlertHistory` |
| 핸들러 (v1) | Slack Webhook · 범용 HTTP Webhook |
| 핸들러 (v2) | Email · PagerDuty · Teams |
| 알림 히스토리 | `results/alerts/YYYY-MM-DD.jsonl` |
| 대시보드 | "알림" 탭 신규 추가 (규칙 관리 + 히스토리) |
| 쿨다운 관리 | 동일 규칙 중복 알림 방지 |

---

### 2-C. 운영 피드백 수집

> 상태: **미구현**

**목표**: 사용자 행동 신호를 품질 지표로 변환

**배경**:
가장 신뢰 가능한 품질 신호는 사용자 행동 데이터.
"재생성 요청"은 불만족 신호, "복사"는 만족 신호로 해석할 수 있다.
이 신호들을 수집하면 ground_truth 없이도 품질 추이를 추적할 수 있다.

**사용 패턴**:

```python
# 애플리케이션 레이어에서 피드백 수집
monitor.record_implicit_feedback(
    task_id="t_001",
    feedback_type="regenerate",    # 불만족 신호
)
monitor.record_implicit_feedback(
    task_id="t_002",
    feedback_type="copy",          # 만족 신호
)
monitor.record_implicit_feedback(
    task_id="t_003",
    feedback_type="thumbs_up",     # 명시적 긍정
)

# 지원 피드백 유형
# 긍정: copy, thumbs_up, share, save, follow_up_depth
# 부정: regenerate, thumbs_down, abandon, correction
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `ImplicitFeedbackTracker` (`core/trackers/feedback.py`) |
| 연결 방식 | `task_id` 기준으로 기존 TaskResult와 연결 |
| 파생 지표 | 긍정 피드백률 · 재생성률 · 이탈률 |
| 대시보드 | "사용자 반응" 섹션 추가 |

---

## 5. Phase 3 — 지속적 개선 루프 (8~12주)

> 운영 데이터가 다음 개발 사이클로 자동 피드백되는 구조 완성

---

### 3-A. 운영 데이터 기반 골든셋 자동 확장

> 상태: **미구현**

**목표**: 수동 골든셋 관리 → 운영 트래픽 기반 자동 확장

**배경**:
현재 골든셋은 초기에 수동으로 만들고 이후 업데이트가 거의 없다.
실제 트래픽 패턴이 골든셋에 반영되지 않으면 회귀 테스트의 커버리지가 낮아진다.
운영에서 발생한 실패 케이스와 엣지 케이스를 자동으로 수집해
다음 검증 사이클에 반영해야 한다.

**사용 패턴**:

```python
from agent_evaluator.datasets import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/daily/",
    output_dir="results/golden_datasets/",
)

new_cases = builder.extract(
    strategies=[
        "failure_cases",     # 실패 태스크 → 회귀 테스트 소재
        "edge_cases",        # 이상치 (비정상 길이, 특수문자 등)
        "high_value",        # 긍정 피드백 높은 케이스 → 유지 기준
        "coverage_gap",      # 기존 골든셋 미커버 유형
    ],
    max_cases=50,
    require_human_review=True,   # 자동 추출 후 사람 검토 필수
)

builder.merge_to_golden(new_cases, version="v2.1")
```

```bash
# CLI
agent-eval dataset build \
  --source results/daily/ \
  --strategy failure_cases edge_cases \
  --max-cases 50 \
  --output results/golden_datasets/
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `GoldenSetBuilder` (`datasets/builder.py`) |
| 추출 전략 | failure_cases · edge_cases · high_value · coverage_gap |
| CLI | `agent-eval dataset build` |
| 검토 UI | 대시보드 내 "케이스 검토" 탭 (승인/거부) |
| 버전 관리 | 골든셋 버전 태깅 + 히스토리 추적 |

---

### 3-B. 이상 탐지 (Anomaly Detection)

> 상태: **미구현**

**목표**: 임계값 기반 → 추세 기반 조기 이상 감지

**배경**:
임계값 알림은 이미 악화된 후 알림이 발생한다.
"P95 지연이 72시간 연속 상승 중"처럼 아직 임계값을 넘지 않았지만
악화 방향이 명확할 때 조기 경보가 필요하다.

**사용 패턴**:

```python
from agent_evaluator.anomaly import AnomalyDetector

detector = AnomalyDetector(
    baseline_window="7d",    # 7일 기준선
    detection_window="1h",   # 1시간 단위 감지
)

anomalies = detector.scan(monitor)
# 반환 예시:
# [
#   {"type": "latency_trend",   "severity": "warning",
#    "detail": "P95 지연 72시간 연속 상승 (+23%)"},
#   {"type": "accuracy_drift",  "severity": "critical",
#    "detail": "코딩 태스크 정확도 기준선 대비 -18%"},
#   {"type": "token_spike",     "severity": "warning",
#    "detail": "평균 토큰 사용량 3시간 전 대비 +45%"},
# ]
```

**감지 유형**:

| 유형 | 알고리즘 | 설명 |
|------|---------|------|
| `latency_trend` | 선형 회귀 | 지속적 상승/하락 추세 |
| `accuracy_drift` | Z-score | 기준선 대비 통계적 유의한 변화 |
| `token_spike` | IQR | 급격한 토큰 사용량 이상 |
| `error_surge` | 비율 변화 | 오류율 급증 |
| `security_pattern` | 빈도 분석 | 특정 공격 패턴 급증 |

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `AnomalyDetector` (`anomaly/detector.py`) |
| 알고리즘 | Z-score + IQR + 선형 회귀 (외부 ML 의존성 없음) |
| Phase 2 연동 | AlertEngine과 연결 → 이상 감지 시 자동 알림 |
| 대시보드 | "이상 감지" 패널 추가 |

---

### 3-C. 평가 비용 최적화 엔진

> 상태: **미구현**

**목표**: LLM 기반 평가 비용을 예측·제어하며 적응형 샘플링 적용

**배경**:
LLM-as-Judge, DeepEval 등 외부 평가는 호출 비용이 발생한다.
이상 감지 시 평가 밀도를 높이고, 정상 상태에서는 낮춰
예산 범위 내에서 최대 품질 정보를 얻어야 한다.

**사용 패턴**:

```python
from agent_evaluator.cost import AdaptivePolicy

monitor = PerformanceMonitor(
    enable_llm_judge=True,
    evaluation_policy=AdaptivePolicy(
        default_sample_rate=0.1,   # 평상시: 10%만 LLM Judge 호출
        anomaly_sample_rate=1.0,   # 이상 감지 시: 100% 전환
        budget_per_day=5.0,        # 일 $5 예산 한도
        alert_at=0.8,              # 예산 80% 소진 시 경고
    ),
)

# 비용 현황 확인
report = monitor.generate_report()
print(report.evaluation_cost)
# → {
#     "llm_judge":          "$0.42",
#     "deepeval":           "$1.20",
#     "total_today":        "$1.62",
#     "budget_remaining":   "$3.38",
#     "projected_daily":    "$3.89",
#     "sample_rate_current": 0.1
#   }
```

**구현 범위**:

| 항목 | 상세 |
|------|------|
| 신규 클래스 | `AdaptivePolicy`, `CostTracker` (`cost/policy.py`) |
| 샘플링 전략 | 기본·이상감지·예산초과 3단계 자동 전환 |
| 비용 추적 | 공급자별(Claude/OpenAI) 누적 비용 집계 |
| 대시보드 | "평가 비용" 탭 추가 (일별 추이 + 예산 잔여) |

---

## 6. 전체 타임라인

```
완료           Phase 1                Phase 2               Phase 3
v0.6.3         v0.7.x                 v0.8.x                v0.9.x
  │    4~6주    │       6~8주          │      8~12주          │
  │             │                      │                      │
  ✅ LLM Judge  │                      │                      │
  ├─ CI 게이팅 ─┤                      │                      │
  ├─ 멀티턴   ─┤                      │                      │
  │             ├─ 스트리밍 엔진 ──────┤                      │
  │             ├─ 알림 시스템   ──────┤                      │
  │             ├─ 운영 피드백   ──────┤                      │
  │             │                      ├─ 골든셋 자동화 ──────┤
  │             │                      ├─ 이상 탐지     ──────┤
  │             │                      ├─ 비용 최적화   ──────┤
  │
현재 효용 (v0.6.3)
  개발: ★★★★☆   Phase 1 완료 후        Phase 2 완료 후       Phase 3 완료 후
  검증: ★★★★☆   개발 ★★★★☆           개발 ★★★★☆           개발 ★★★★★
  운영: ★★☆☆☆   검증 ★★★★★           검증 ★★★★★           검증 ★★★★★
                 운영 ★★★☆☆           운영 ★★★★☆           운영 ★★★★★
```

### 버전 계획

| 버전 | 포함 기능 | 상태 |
|------|-----------|------|
| ~~v0.7.0~~ → **v0.6.3** | LLM Judge | ✅ 완료 (조기 출시) |
| v0.7.0 | CI 게이팅 (`agent-eval gate`) | 🔲 미구현 |
| v0.7.1 | 멀티턴 대화 평가 | 🔲 미구현 |
| v0.8.0 | 스트리밍 엔진 + 알림 시스템 | 🔲 미구현 |
| v0.8.1 | 운영 피드백 수집 | 🔲 미구현 |
| v0.9.0 | 골든셋 자동화 + 이상 탐지 | 🔲 미구현 |
| v0.9.1 | 비용 최적화 엔진 | 🔲 미구현 |
| v1.0.0 | 전체 통합 + API 안정화 | 🔲 미구현 |

---

## 7. 우선순위 결정 근거

### Phase 1-A (LLM Judge)를 최우선으로 한 이유 ✅ 완료

```
기존 SDK 투입 가능 범위 (ground_truth 기준):
  QA 챗봇 (고정 FAQ)         █████░░░░░  ~20%
  RAG 기반 문서 검색          ███████░░░  ~35%
  코드 생성 (테스트 케이스)   ████████░░  ~40%
  일반 대화형 에이전트        █░░░░░░░░░  ~5%

LLM Judge 적용 후 (v0.6.3):
  모든 케이스                 ████████░░  ~80%
  (비용 샘플링 적용 시)
```

단일 기능으로 SDK 적용 범위가 가장 크게 확대되었으며,
오픈도메인 에이전트 팀의 진입 장벽을 낮췄다.

### Phase 1-B (CI 게이팅)를 다음으로 하는 이유

CI 파이프라인에 통합되면 개발팀이 **매 PR마다 자연스럽게 SDK를 사용**하게 된다.
사용이 정착되어야 Phase 2, 3에서 필요한 운영 데이터가 축적된다.
사용자 정착 없이 Phase 2 운영 기능을 구현해도 실제 사용이 없을 위험이 있다.

### Phase 2보다 Phase 1을 먼저 하는 이유

```
Phase 1이 없을 때 Phase 2를 구현하면:
  실시간 알림이 오지만 → 알림 내용이 "TCR 62%" 뿐
  → "왜 낮아졌는지" 원인 분석 불가
  → 알림 받아도 조치 방법 모름

Phase 1 완료 후 Phase 2:
  실시간 알림 → "TCR 62%, 코딩 태스크 LLM Judge 점수 -30%"
  → 코딩 태스크 프롬프트 문제로 빠른 원인 특정
```

---

## 8. 성공 지표

### Phase 1 완료 기준

| 지표 | 목표 | 현재 (v0.6.3) |
|------|------|--------------|
| LLM Judge 적용 후 유효 지표 수 | 3개 → 8개 이상 | ✅ TCR/Latency/Token + completeness/relevance/factual_consistency/quality/accuracy = 8개 달성 |
| CI 게이팅 통합 소요 시간 | 30분 이내 | 🔲 미구현 |
| 멀티턴 평가 지원 최대 턴 수 | 20턴 이상 | 🔲 미구현 |

### Phase 2 완료 기준

| 지표 | 목표 |
|------|------|
| 품질 저하 감지 → 알림 발송 시간 | 5분 이내 |
| 미들웨어 적용 코드 추가량 | 5줄 이내 |
| 알림 오탐률 | 5% 이하 |

### Phase 3 완료 기준

| 지표 | 목표 |
|------|------|
| 골든셋 자동 확장 주기 | 주 1회 배치 |
| 이상 탐지 선행 경보 시간 | 임계값 위반 30분 전 |
| LLM Judge 일 예산 준수율 | 95% 이상 |

### 전체 완성(v1.0.0) 기준

| 라이프사이클 단계 | 목표 |
|-----------------|----------|
| 개발 | ★★★★★ |
| 검증 | ★★★★★ |
| 운영 | ★★★★★ |
| **투입 가능 에이전트 범위** | **현재 80% → 85% 이상** |

---

## 부록 — 구현 이력

| 날짜 | 버전 | 구현 내용 |
|------|------|-----------|
| 2026-03-27 | v0.6.3 | Phase 1-A 완료: `LLMJudge` 클래스, `PerformanceMonitor` 통합, 대시보드 Quality 탭 섹션, `agent-eval init` 모델 자동 연동 |
| 2026-03-27 | v0.6.2 | `agent_evaluator.py` 5,762줄 → `core/trackers/` 서브패키지 분리, `infer_privilege_level()` 추출, LangChain/LangGraph 예제 Live 트랙 추가 |

---

*각 Phase의 일정과 범위는 구현 진행 중 조정될 수 있습니다.*
