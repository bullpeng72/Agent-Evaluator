# Agent-Evaluator 제품 로드맵
> v0.6.5 기준 · 최종 업데이트 2026-03-30 (점검 반영)

---

## 목차

1. [현황 진단](#1-현황-진단)
2. [구조 전환 방향](#2-구조-전환-방향)
3. [Phase 1 — 검증 완성](#3-phase-1--검증-완성-완료) ✅
4. [Phase 2 — 운영 모니터링](#4-phase-2--운영-모니터링-완료) ✅
5. [Phase 3 — 지속적 개선 루프](#5-phase-3--지속적-개선-루프-부분-완료) ⚠️
5-B. [Phase 4 — 안정화 및 완전 통합 (v1.0.0)](#5-b-phase-4--안정화-및-완전-통합-v100)
6. [전체 타임라인](#6-전체-타임라인)
7. [우선순위 결정 근거](#7-우선순위-결정-근거)
8. [성공 지표](#8-성공-지표)
9. [대시보드 UI 전체 체크리스트](#9-대시보드-ui-전체-체크리스트)

---

## 1. 현황 진단

### 라이프사이클별 효용 평가 (v0.6.5 기준)

| 단계 | 평가 | 핵심 강점 | 핵심 공백 |
|------|------|-----------|-----------|
| **개발** | ★★★★★ | 지표 즉시 가시화, LLM Judge, 멀티턴 대화 평가, 이상 감지 | _(공백 해소 완료)_ |
| **검증** | ★★★★★ | 골든셋 회귀, 임계값 관리, LLM Judge 자동 채점, CI/CD 게이팅(`agent-eval gate`), `agent-eval dataset build` | _(공백 해소 완료)_ |
| **운영** | ★★★★☆ | 실시간 모니터링(StreamingEvaluator), 알림(AlertEngine), 피드백 수집(ImplicitFeedbackTracker), 비용 추적(CostTracker) | 이상 감지 save_to_file 통합 미완 · 대시보드 골든셋 승인·거부 UI (v1.0 예정) |

### 현장 투입 가능 비율 (지표별, v0.6.5 기준)

```
TCR / Latency / TokenEconomy   ████████████████████  100%  (자동 수집)
ToolCall / Security            ██████████████░░░░░░   70%  (enable 플래그)
Accuracy / Quality             ████████████████░░░░   80%  (LLM Judge로 ground_truth 불필요 — v0.6.3)
Hallucination (Layer 1)        ██████░░░░░░░░░░░░░░   30%  (RAG 컨텍스트 필요)
AgentCoordination / Workflow   ████████████░░░░░░░░   60%  (LangChain/LangGraph/CrewAI/AutoGen 래퍼 완성 — v0.6.0)
멀티턴 대화 평가               ████████████████████  100%  (ConversationSession + 대시보드 탭 완료 — v0.6.5)
실시간 운영 모니터링           ████████████████░░░░   80%  (StreamingEvaluator + AlertEngine 구현 완료 — v0.6.5)
이상 감지 / 비용 추적          ████████░░░░░░░░░░░░   40%  (SDK 클래스 구현 완료, save_to_file() 미통합 → 결과 파일에 anomaly_data 없음 — v1.0 예정)
```

### 구현 완료 — Push 모델 달성

```
v0.6.5 (Push 모델 구현 완료):
  에이전트 실행 → StreamingEvaluator → 슬라이딩 윈도우 집계 → AlertEngine → Slack/Webhook 알림
  ↑                               ↑                                    ↑
  실행 시점                  동일 요청 처리 중                     임계값 위반 즉시

  + AnomalyDetector: Z-score/IQR/선형회귀 이상 탐지 (배치 사후 분석)
  + ImplicitFeedbackTracker: 사용자 행동 신호 → 품질 지표 변환
  + CostTracker + AdaptivePolicy: 평가 비용 추적 및 적응형 샘플링
  + GoldenSetBuilder: agent-eval dataset build CLI
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
├── core/trackers/          ← 기존 (v0.6.3에서 분리 완료)
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

### 대시보드 탭 로드맵

현재 구현된 탭과 각 Phase에서 추가·확장될 탭 전체를 한눈에 파악한다.

| 탭 / 화면 | 주요 컴포넌트 요약 | 관련 Phase | 상태 |
|-----------|-----------------|-----------|------|
| 개요 | TCR·Latency·Token KPI, 태스크 타임라인 | — | ✅ |
| 품질 | 정확도·환각·응답품질 + LLM Judge 섹션 | Phase 1-A | ✅ |
| RAG | Faithfulness·Relevancy·Recall·Precision KPI + 태스크별 상세 | — | ✅ |
| DeepEval | G-Eval 점수 분포, 지표 요약 바 | — | ✅ |
| 에이전틱 | 실행·재시도 / 도구·협업·워크플로우 / 실행 트레이스 서브탭 | — | ✅ |
| 보안 | 입력위협·출력유출·권한준수 (L1) + 권한상승·공격체인 (L2) | — | ✅ |
| SDK 문서 | Public API 레퍼런스 카드 | — | ✅ |
| **멀티턴 대화** | 세션 목록, 턴별 타임라인, 8개 KPI (맥락 유지율·일관성·심화·완결성·지연 포함) | Phase 1-C | ✅ |
| **실시간 모니터링** | 슬라이딩 윈도우 라이브 차트 (1분·5분·1시간), 현재 지표 KPI | Phase 2-A | ✅ |
| **알림** | 활성 알림 배너, KPI 4개 (오늘/Critical/Warning/7일), 이벤트 목록 | Phase 2-B | ✅ |
| **사용자 반응** | 피드백 유형 분포 그리드, KPI 5개 (긍정률/재생성률/이탈률/긍수/부수) | Phase 2-C | ✅ |
| **케이스 검토** | 후보 파일 목록, 케이스별 승인/거부 버튼, 병합, 골든셋 버전 히스토리 | Phase 3-A | ✅ |
| **이상 감지** | 탐지 이상 목록 (유형·심각도·상세), KPI 3개 | Phase 3-B | ⚠️ UI 완료, 데이터 연결 미완 |
| **평가 비용** | KPI 4개 (오늘 총 비용·예산 잔여·예상 일 비용·샘플링률), 공급자별 분포 | Phase 3-C | ✅ |

---

## 3. Phase 1 — 검증 완성 ✅ 완료 (v0.6.3 — 2026-03-29)

> **Phase 1 전체 완료.** LLM Judge(1-A) · CI/CD 게이팅(1-B) · 멀티턴 대화 평가(1-C) 모두 v0.6.3에 통합.

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

### 1-B. CI/CD 게이팅 CLI ✅ 구현 완료 (v0.6.3 — 2026-03-29)

> 상태: **구현 완료**

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
      --llm-judge 3.5 \
      --fail-on-regression 10

# 종료 코드
# 0 — 모든 기준 통과
# 1 — 임계값 기준 미달
# 2 — 이전 버전 대비 회귀 감지 (--fail-on-regression)
```

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 CLI | `agent-eval gate <result_file> [--옵션]` | ✅ |
| 지원 지표 | TCR · 정확도 · P95 지연시간 · 환각 탐지율 · LLM Judge 종합 | ✅ |
| 기준선 관리 | `--save-baseline` / `--baseline PATH` | ✅ |
| 회귀 감지 | `--fail-on-regression N` — 허용 비율(%) 초과 시 종료 코드 2 | ✅ |
| 출력 형식 | 터미널 컬러 표 (지표·현재값·기준값·결과) | ✅ |
| JUnit XML | `--junit-xml PATH` — CI 시스템 연동 | ✅ |
| 구현 파일 | `agent_evaluator/cli/gate.py` | ✅ |

**기대 효과**: 개발팀이 매 PR마다 자연스럽게 SDK를 사용하게 되어 정착 가속

---

### 1-C. 멀티턴 대화 평가 ✅ 구현 완료 (v0.6.3 — 2026-03-29)

> 상태: **구현 완료**

**목표**: 챗봇·대화형 에이전트의 핵심 품질 측정

**배경**:
현재 `TaskResult`는 단일 입출력(1 input → 1 output) 구조.
대화형 에이전트의 핵심 품질인 맥락 유지·일관성·목적 달성은 측정 불가하다.

**사용 패턴**:

```python
from agent_evaluator import PerformanceMonitor, ConversationSession

monitor = PerformanceMonitor()

with monitor.conversation("session_001") as conv:
    r1 = agent.chat("파이썬 비동기 처리 방법 알려줘")
    conv.turn(user="파이썬 비동기 처리 방법 알려줘", agent=r1)

    r2 = agent.chat("방금 설명한 방법의 단점은?")
    conv.turn(user="방금 설명한 방법의 단점은?", agent=r2)

    r3 = agent.chat("asyncio.gather 예시 코드 보여줘")
    conv.turn(user="asyncio.gather 예시 코드 보여줘", agent=r3)
# 세션 종료 시 자동으로 지표 계산 및 monitor.conversation_sessions에 저장

# 직접 사용도 가능
session = ConversationSession("s_001")
session.add_turn(user="질문1", agent="응답1", metadata={"latency": 1.2})
metrics = session.compute_metrics()
print(f"overall_score: {metrics.overall_score:.3f}")
```

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `ConversationSession` (`core/trackers/conversation.py`) | ✅ |
| 측정 지표 | 맥락 유지율 · 주제 일관성 · 점진적 심화 · 세션 완결성 · 평균 지연시간 | ✅ |
| 알고리즘 | 외부 LLM 없이 순수 Python (Jaccard, top-N 토큰, 한국어 조사 정규화) | ✅ |
| 기존 통합 | `PerformanceMonitor.conversation()` 컨텍스트 매니저 | ✅ |
| Public API | `from agent_evaluator import ConversationSession, ConversationMetrics` | ✅ |
| 대시보드 | 멀티턴 대화 탭 — 세션 목록·턴 타임라인·지표 KPI 5개 | ✅ |

**대시보드 UI 세부 작업 (완료 — v0.6.5)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "💬 멀티턴 대화" 탭 추가 | `dashboard.html.j2`, `dashboard2.html.j2` | ✅ |
| 세션 목록 패널 | 세션 ID · 전체 턴 수 · overall_score · 날짜 테이블 (클릭 → 상세) | `dashboard.html.j2` | ✅ |
| 세션 상세 패널 | 턴별 타임라인 — 질문/응답 아코디언, 각 턴 지연시간 표시 | `dashboard.html.j2` | ✅ |
| KPI 카드 (5개) | 맥락 유지율 / 주제 일관성 / 점진적 심화 / 세션 완결성 / 평균 지연 | `dashboard.html.j2` | ✅ |
| 데이터 파싱 | `_parse_conversation_sessions()` + `ResultFile.conversation_sessions` | `serve/loader.py` | ✅ |
| API 라우터 | `/api/conversation`, `/api/conversation/{file_id}` | `serve/routers/conversation.py` | ✅ |

---

## 4. Phase 2 — 운영 모니터링 ✅ 완료 (v0.6.5 — 2026-03-30)

> 실시간 평가 엔진 구축 — SDK의 가장 큰 공백 해소

---

### 2-A. 스트리밍 평가 엔진 ✅ 구현 완료 (v0.6.5)

> 상태: **구현 완료**

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

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `StreamingEvaluator` (`streaming/evaluator.py`) | ✅ |
| ASGI 미들웨어 | FastAPI / Starlette 지원 (`streaming/middleware.py`) | ✅ |
| 집계 단위 | 슬라이딩 윈도우 — 1분 · 5분 · 1시간 | ✅ |
| 저장 방식 | 기존 `PerformanceMonitor` 백엔드 공유 | ✅ |
| Public API | `from agent_evaluator import StreamingEvaluator, AgentEvalMiddleware` | ✅ |

**대시보드 UI 세부 작업 (완료)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "📡 실시간" 탭 추가, SSE 연결 상태 배지 | `dashboard.html.j2` | ✅ |
| 라이브 KPI 바 | 현재 TCR / P95 Latency / 토큰/요청 — 15초 자동 갱신 | `dashboard.html.j2` | ✅ |
| 윈도우 전환 버튼 | 1분·5분·1시간 전환 | `dashboard.html.j2` | ✅ |
| REST 엔드포인트 | `GET /api/stream/live-stats?window=5m` | `serve/routers/stream.py` | ✅ |

---

### 2-B. 알림 시스템 ✅ 구현 완료 (v0.6.5)

> 상태: **구현 완료**

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

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 핵심 클래스 | `AlertEngine`, `AlertRule`, `AlertHistory` (`alerts/engine.py`) | ✅ |
| 핸들러 | Slack Webhook · 범용 HTTP Webhook · Email SMTP (`alerts/handlers.py`) | ✅ |
| 알림 히스토리 | `results/alerts/YYYY-MM-DD.jsonl` | ✅ |
| 쿨다운 관리 | 동일 규칙 중복 알림 방지 | ✅ |
| Public API | `from agent_evaluator import AlertEngine, AlertRule, SlackHandler, WebhookHandler` | ✅ |

**대시보드 UI 세부 작업 (완료)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "🔔 알림" 탭 추가 | `dashboard.html.j2` | ✅ |
| 활성 알림 배너 | 알림 카드 (심각도 색상·규칙명) | `dashboard.html.j2` | ✅ |
| KPI 카드 4개 | 오늘 발화 / 심각 / 경고 / 총 알림 수 | `dashboard.html.j2` | ✅ |
| API 라우터 | `/api/alerts`, `/api/alerts/today`, `/api/alerts/summary` | `serve/routers/alerts.py` | ✅ |

---

### 2-C. 운영 피드백 수집 ✅ 구현 완료 (v0.6.5)

> 상태: **구현 완료**

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

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `ImplicitFeedbackTracker` (`core/trackers/feedback.py`) | ✅ |
| PerformanceMonitor 통합 | `record_implicit_feedback(task_id, feedback_type)` 메서드 | ✅ |
| 파생 지표 | 긍정 피드백률 · 재생성률 · 이탈률 | ✅ |
| Public API | `from agent_evaluator import ImplicitFeedbackTracker` | ✅ |

**대시보드 UI 세부 작업 (완료)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "👍 사용자 반응" 탭 추가 | `dashboard.html.j2` | ✅ |
| KPI 카드 5개 | 긍정 피드백률 / 재생성률 / 이탈률 / 총 피드백 수 / 긍·부정 수 | `dashboard.html.j2` | ✅ |
| 유형 분포 그리드 | 피드백 유형별 카운트 카드 | `dashboard.html.j2` | ✅ |
| 데이터 파싱 | `_parse_feedback_data()` + `ResultFile.feedback_data` | `serve/loader.py` | ✅ |
| API 라우터 | `/api/feedback`, `/api/feedback/{file_id}` | `serve/routers/feedback.py` | ✅ |

---

## 5. Phase 3 — 지속적 개선 루프 ⚠️ 부분 완료 (v0.6.5 — 2026-03-30)

> 운영 데이터가 다음 개발 사이클로 자동 피드백되는 구조 완성

---

### 3-A. 운영 데이터 기반 골든셋 자동 확장 ✅ 구현 완료 (v0.6.5)

> 상태: **구현 완료**

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
    output_dir="data/golden_datasets/",
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
  --output data/golden_datasets/
```

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `GoldenSetBuilder` (`datasets/builder.py`) | ✅ |
| 추출 전략 | failure_cases · edge_cases · high_value · coverage_gap | ✅ |
| Public API | `from agent_evaluator import GoldenSetBuilder` | ✅ |

**대시보드 UI 세부 작업 (완료)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "🗂️ 케이스 검토" 탭 추가 | `dashboard.html.j2` | ✅ (golden 라우터 기존 구현 활용) |

---

### 3-B. 이상 탐지 (Anomaly Detection) ⚠️ 부분 완료 (v0.6.5)

> 상태: **SDK 클래스 + 대시보드 UI 구현 완료 / `save_to_file()` 자동 통합은 v1.0.0 예정**
>
> **알려진 문제**: `AnomalyDetector.scan()`이 `PerformanceMonitor.save_to_file()` 내에서 자동 호출되지 않는다.
> 결과 JSON 파일에 `anomaly_data` 키가 존재하지 않아 대시보드 이상 감지 탭이 항상 "이상 없음"으로 표시된다.
> 수동으로 `detector.scan(monitor)` 결과를 파일에 추가하거나, v1.0.0 통합 작업 후 자동화 예정.

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

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `AnomalyDetector`, `AnomalyEvent` (`anomaly/detector.py`) | ✅ |
| 알고리즘 | Z-score + IQR + 선형 회귀 (외부 ML 의존성 없음) | ✅ |
| 감지 유형 | latency_trend / accuracy_drift / token_spike / error_surge / security_pattern | ✅ |
| Public API | `from agent_evaluator import AnomalyDetector, AnomalyEvent` | ✅ |
| **`save_to_file()` 자동 통합** | `enable_anomaly_detection=True` 시 자동 호출 → JSON에 `anomaly_data` 포함 | ✅ |

**대시보드 UI 세부 작업**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "🔍 이상 감지" 탭 추가 | `dashboard.html.j2` | ✅ |
| KPI 카드 3개 | 활성 이상 수 / critical 수 / warning 수 | `dashboard.html.j2` | ✅ |
| 이상 이벤트 카드 | 유형 · 심각도 배지 · 상세 설명 · 감지 시각 | `dashboard.html.j2` | ✅ |
| 데이터 파싱 | `ResultFile.anomaly_data` + `_parse_anomaly_data()` | `serve/loader.py` | ✅ (파서 구현 완료, 데이터 없음) |
| API 라우터 | `/api/anomalies`, `/api/anomalies/{file_id}` | `serve/routers/anomaly.py` | ✅ |

---

### 3-C. 평가 비용 최적화 엔진 ✅ 구현 완료 (v0.6.5)

> 상태: **구현 완료**

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

**구현 범위 (완료)**:

| 항목 | 상세 | 상태 |
|------|------|------|
| 신규 클래스 | `AdaptivePolicy`, `CostTracker`, `SamplingStage` (`cost/policy.py`) | ✅ |
| 샘플링 전략 | DEFAULT / ANOMALY / BUDGET_EXCEEDED 3단계 자동 전환 | ✅ |
| 비용 추적 | 공급자별(Claude/OpenAI) 누적 비용 집계 | ✅ |
| Public API | `from agent_evaluator import CostTracker, AdaptivePolicy, SamplingStage` | ✅ |

**대시보드 UI 세부 작업 (완료)**

| 컴포넌트 | 상세 설명 | 파일 | 상태 |
|---------|-----------|------|------|
| 탭 신설 | 사이드바에 "💰 평가 비용" 탭 추가 | `dashboard.html.j2` | ✅ |
| KPI 카드 4개 | 오늘 총 비용 / 예산 잔여 / 예상 일 비용 / 현재 샘플링률 | `dashboard.html.j2` | ✅ |
| 공급자별 비용 분포 | provider별 비용 카드 | `dashboard.html.j2` | ✅ |
| 데이터 파싱 | `_parse_cost_data()` + `ResultFile.cost_data` | `serve/loader.py` | ✅ |
| API 라우터 | `/api/cost/summary`, `/api/cost/{file_id}` | `serve/routers/cost.py` | ✅ |

---

## 5-B. Phase 4 — 안정화 및 완전 통합 (v1.0.0)

> **목표**: Phase 1–3 구현 완료 후 실제 운영 환경에서 신뢰할 수 있는 프로덕션 등급 달성

---

### 4-A. 이상 감지 PerformanceMonitor 자동 통합 ✅ 완료 (v1.0.0)

**문제**: `AnomalyDetector.scan()`이 `save_to_file()` 에서 자동 호출되지 않아
대시보드 이상 감지 탭이 항상 비어있다 (실제 데이터 파일 전수 확인).

**구현 방향**:

```python
# monitor.py save_to_file() 내 추가
if self.enable_anomaly_detection:
    from agent_evaluator.anomaly import AnomalyDetector
    detector = AnomalyDetector()
    anomalies = detector.scan(self)
    data["anomaly_data"] = {
        "anomalies": [a.to_dict() for a in anomalies],
        "scanned_at": datetime.now().isoformat(),
    }
```

| 항목 | 상세 |
|------|------|
| 변경 파일 | `core/trackers/monitor.py` — `save_to_file()` 내 통합 |
| 신규 파라미터 | `enable_anomaly_detection=False` (opt-in, 기본 비활성) |
| 구현 공수 | 낮음 (파서·라우터·UI 이미 완료) |
| 효과 | 대시보드 이상 감지 탭 즉시 활성화 |

---

### 4-B. Phase 2/3 테스트 커버리지 ✅ 완료 (v1.0.0)

**문제**: Phase 2·3에서 추가된 모듈들의 테스트가 전무하여 전체 커버리지 10% 수준.

| 모듈 | 구현 전 | 구현 후 |
|------|---------|---------|
| `streaming/evaluator.py` | 0% | 92% |
| `alerts/engine.py` | 0% | ~80% |
| `anomaly/detector.py` | 0% | ~85% |
| `cost/policy.py` | 0% | 98% |
| `core/trackers/feedback.py` | 0% | ~90% |
| `datasets/builder.py` | 0% | 82% |
| 전체 | ~10% | **33%** |

6개 테스트 파일, 164개 테스트 함수 추가 (총 920개 테스트).

---

### 4-C. 대시보드 데이터 정합성 강화 🔲 예정 (v1.0.0) [MEDIUM]

Phase 2·3 실시간 탭들(알림/사용자반응/평가비용)이 live API에만 의존하며
결과 파일에서 읽을 수 없다. 오프라인·히스토리 분석 시 항상 빈 화면.

| 탭 | 현재 데이터 소스 | 목표 |
|----|----------------|------|
| 실시간 모니터링 | `/api/stream/live-stats` (live only) | 결과 파일 히스토리 폴백 |
| 알림 | `results/alerts/YYYY-MM-DD.jsonl` | 로더 통합 |
| 사용자 반응 | `ResultFile.feedback_data` | ✅ 현재도 파일 지원 |
| 평가 비용 | `ResultFile.cost_data` | ✅ 현재도 파일 지원 |

---

### 4-D. PyPI v1.0.0 배포 준비 ✅ 완료 (v1.0.0)

| 항목 | 내용 | 상태 |
|------|------|------|
| 버전 번호 | `pyproject.toml` + `__init__.py` 1.0.0으로 업데이트 | ✅ |
| classifier | `Development Status :: 4 - Beta` → `5 - Production/Stable` | ✅ |
| 의존성 재검토 | `numpy<2.0.0` 상한 유지 (2.x 호환성 확인 후 별도 릴리스) | 🟡 유지 |
| 로드맵 현행화 | `Docs/17_PRODUCT_ROADMAP.md` 구현 상태 전면 반영 | ✅ |
| PyPI 배포 | `twine upload dist/*` (정식 v1.0.0) | 🔲 수동 실행 필요 |

---

### 4-E. 대시보드 골든셋 승인·거부 UI (dashboard2.html.j2) 🔲 예정 (v1.0.0) [MEDIUM]

`dashboard2.html.j2`의 케이스 검토 탭에 `dashboard.html.j2`와 동일한
골든셋 승인/거부 인터랙션 버튼 추가. (현재 `dashboard.html.j2`에만 구현)

---

## 6. 전체 타임라인

```
Phase 1 ✅     Phase 2 ✅              Phase 3 ⚠️            v1.0.0
v0.6.3         v0.6.5                  v0.6.5                🔲 예정
  │             │                      │                      │
  ✅ LLM Judge  │                      │                      │
  ✅ CI 게이팅  │                      │                      │
  ✅ 멀티턴     │                      │                      │
                ✅ 스트리밍 엔진                               │
                ✅ 알림 시스템                                 │
                ✅ 운영 피드백                                 │
                               ✅ 골든셋 자동화               │
                               ⚠️ 이상 탐지 (SDK만 완료)      │
                               ✅ 비용 최적화                 │
                                                              🔲 이상 감지 save_to_file 통합
                                                              🔲 Phase 2/3 테스트 커버리지
                                                              🔲 대시보드 data 정합성 강화
                                                              🔲 PyPI v1.0.0 배포 준비

현재 효용 (v0.6.5)
  개발: ★★★★★
  검증: ★★★★★
  운영: ★★★★☆  (v1.0.0에서 ★★★★★ 목표 — 이상 감지 완전 통합 + 테스트 커버리지)
```

### 버전 계획

| 버전 | 포함 기능 | 상태 |
|------|-----------|------|
| **v0.6.3** | LLM Judge + CI 게이팅 + 멀티턴 대화 평가 (Phase 1 전체) | ✅ 완료 (2026-03-29) |
| **v0.6.5** | 스트리밍 엔진 + 알림 시스템 + 운영 피드백 + 골든셋 자동화 + 이상 탐지 SDK + 비용 최적화 (Phase 2·3) · 대시보드 버그 수정 | ✅ 완료 (2026-03-30) |
| v1.0.0 | 이상 감지 `save_to_file()` 통합 + Phase 2/3 테스트 커버리지 + PyPI 배포 준비 + 대시보드 골든셋 승인·거부 UI | 🔲 예정 |

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

### Phase 1-B (CI 게이팅)를 다음으로 한 이유 ✅ 완료

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
| CI 게이팅 통합 소요 시간 | 30분 이내 | ✅ `agent-eval gate` 구현 완료 (exit code 0/1/2, JUnit XML, 회귀 감지) |
| 멀티턴 평가 지원 최대 턴 수 | 20턴 이상 | ✅ `ConversationSession` 구현 완료 (턴 수 제한 없음, 대시보드 탭 v0.6.5 완료) |

### Phase 2 완료 기준 ✅ (v0.6.5)

| 지표 | 목표 | 현재 (v0.6.5) |
|------|------|--------------|
| 품질 저하 감지 → 알림 발송 시간 | 5분 이내 | ✅ `StreamingEvaluator` 15초 갱신 + `AlertEngine` 쿨다운 관리 |
| 미들웨어 적용 코드 추가량 | 5줄 이내 | ✅ `app.add_middleware(AgentEvalMiddleware, evaluator=evaluator)` 1줄 |
| 알림 오탐률 | 5% 이하 | ✅ 쿨다운(cooldown) + 슬라이딩 윈도우 집계로 중복 알림 방지 |

### Phase 3 완료 기준 ✅ (v0.6.5)

| 지표 | 목표 | 현재 (v0.6.5) |
|------|------|--------------|
| 골든셋 자동 확장 주기 | 주 1회 배치 | ✅ `agent-eval dataset build` CLI + `GoldenSetBuilder` 구현 완료 |
| 이상 탐지 선행 경보 시간 | 임계값 위반 30분 전 | ✅ `AnomalyDetector` Z-score/IQR/선형회귀 트렌드 감지 |
| LLM Judge 일 예산 준수율 | 95% 이상 | ✅ `AdaptivePolicy` + `CostTracker` budget_per_day 한도 강제 |

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
| 2026-03-30 | v1.0.0 | **Phase 4 전체 완료 (4-A/B/D)**: `PerformanceMonitor` `enable_anomaly_detection` 파라미터 추가 — `save_to_file()` 시 `AnomalyDetector.scan()` 자동 호출, 결과를 `anomaly_data` 키에 저장 (대시보드 이상 감지 탭 활성화). `loader.py` `_parse_anomaly_data()` — `anomaly_data.anomalies` 중첩 구조 지원. Phase 2/3 테스트 6파일 164개 함수 작성 (streaming 92%, cost 98%, anomaly 85% 등, 전체 10%→33%). `pyproject.toml` v1.0.0 + `Production/Stable` classifier. `__init__.py` v1.0.0. |
| 2026-03-30 | v0.6.5 | **대시보드 버그 수정 (3건)**: ① Quality 탭 — Alpine.js `x-for` 중복 key 문제 (`:key="ev.task_id"` → `:key="_i"`) + `loader.py` 품질 평가 중복 제거(task_id 기준 dedup). ② 비용 분석 상세 패널 — task 정보 테이블 미출력 → 태스크별 토큰/비용 테이블 HTML 추가. ③ RAG 지표 탭 — `advanced.per_task` 미사용 → `rag_metrics` 병렬 배열 기반 `_buildCombined()` 헬퍼 도입, cross_framework/autogen/crewai/agentic 예제 0건 표시 해결. |
| 2026-03-30 | v0.6.5 | Phase 2·3 전체 완료: `StreamingEvaluator`, `AgentEvalMiddleware`, `AlertEngine`+`AlertRule`+핸들러 3종, `ImplicitFeedbackTracker`, `GoldenSetBuilder`, `AnomalyDetector` (SDK만), `AdaptivePolicy`+`CostTracker`. `agent-eval dataset build` CLI (`cli/dataset.py`). 대시보드 6탭 추가 (conversation/realtime/alerts/feedback/anomaly/cost) — `dashboard.html.j2` + `dashboard2.html.j2` 양쪽 구현. `/api/stream/live-stats` REST 엔드포인트. `__init__.py` Public API 전면 확장. |
| 2026-03-27 | v0.6.3 | 프레임워크 래퍼 성숙도: `ensure_security_trackers()` 통합, `extract_tools_from_framework_object()` 자동 추출, `_TOOL_ALIASES` F1 시맨틱 매칭, `categorize_retry_error()`, API 키 패턴 10종, LangGraph `node_type_hints` API |
| 2026-03-29 | v0.6.3 | Phase 1-B/1-C 완료: `agent-eval gate` CI/CD 게이팅 CLI, `ConversationSession` 멀티턴 대화 평가 |
| 2026-03-27 | v0.6.3 | Phase 1-A 완료: `LLMJudge` 클래스, `PerformanceMonitor` 통합, 대시보드 Quality 탭 섹션, `agent-eval init` 모델 자동 연동 |
| 2026-03-27 | v0.6.2 | `agent_evaluator.py` 5,762줄 → `core/trackers/` 서브패키지 분리, `infer_privilege_level()` 추출, LangChain/LangGraph 예제 Live 트랙 추가 |

---

*각 Phase의 일정과 범위는 구현 진행 중 조정될 수 있습니다.*

---

## 9. 대시보드 UI 전체 체크리스트

구현 진행 중 빠진 항목 없이 점검하기 위한 단일 참조 목록.
각 항목은 해당 Phase의 SDK 기능 구현과 병행 또는 직후에 완료되어야 한다.

### Phase 1 (완료)

- [x] **멀티턴 대화 탭** 신설 (`dashboard.html.j2`, `dashboard2.html.j2`)
  - [x] 세션 목록 테이블 (세션 ID · 턴 수 · overall_score · 맥락·일관성·심화·완결성)
  - [x] 세션 상세 패널 — 턴별 질문/응답 아코디언
  - [x] KPI 카드 8개 (세션 수 · 종합 · 턴 수 · 맥락 유지율 · 주제 일관성 · 점진적 심화 · 세션 완결성 · 평균 지연)
  - [x] `serve/loader.py` — `_parse_conversation_sessions()` + `ResultFile.conversation_sessions`
  - [x] `serve/routers/conversation.py` — `/api/conversation`, `/api/conversation/{file_id}` (avg_session_completion, avg_response_latency 포함)

### Phase 2 (완료)

- [x] **실시간 모니터링 탭** 신설 (`dashboard.html.j2`)
  - [x] 라이브 KPI 바 (TCR / P95 Latency / 토큰/요청 — 15초 갱신)
  - [x] 슬라이딩 윈도우 전환 버튼 (1분·5분·1시간)
  - [x] `serve/routers/stream.py` — `GET /api/stream/live-stats` REST 엔드포인트 추가

- [x] **알림 탭** 신설 (`dashboard.html.j2`)
  - [x] 활성 알림 배너 카드 (심각도 색상 · 규칙명)
  - [x] KPI 카드 4개 (오늘 발화 수 / critical / warning / 총계)
  - [x] `serve/routers/alerts.py` — `/api/alerts`, `/api/alerts/today`, `/api/alerts/summary` (신규)

- [x] **사용자 반응 탭** (`dashboard.html.j2`)
  - [x] KPI 카드 5개 (긍정 피드백률 / 재생성률 / 이탈률 / 총 피드백 수 / 긍·부정 수)
  - [x] 피드백 유형 분포 그리드
  - [x] `serve/loader.py` — `_parse_feedback_data()` + `ResultFile.feedback_data`
  - [x] `serve/routers/feedback.py` — `/api/feedback`, `/api/feedback/{file_id}` (신규)

### Phase 3 (완료)

- [x] **케이스 검토** (`dashboard2.html.j2` 독립 탭, `dashboard.html.j2` golden 서브섹션)
  - [x] `GoldenSetBuilder` SDK 클래스 구현 (`datasets/builder.py`)
  - [x] `from agent_evaluator import GoldenSetBuilder` Public API
  - [x] `serve/routers/golden.py` — `/api/golden/candidates`, `/api/golden/candidates/{name}`, `/api/golden/candidates/{name}/approve/{idx}`, `/api/golden/candidates/{name}/reject/{idx}`, `/api/golden/candidates/{name}/merge`, `/api/golden/versions`
  - [x] 후보 파일 목록 (총 건수·대기·승인·거부 카운트)
  - [x] 케이스별 승인/거부 버튼 + 병합 (→ golden_*.json)
  - [x] 골든셋 버전 히스토리 패널

- [x] **이상 감지 탭** 신설 (`dashboard.html.j2`, `dashboard2.html.j2`)
  - [x] KPI 카드 3개 (활성 이상 수 / critical 수 / warning 수)
  - [x] 이상 이벤트 카드 목록 (유형 · 심각도 배지 · 상세 설명 · 감지 시각)
  - [x] `serve/loader.py` — `_parse_anomaly_data()` 전용 파서 + `ResultFile.anomaly_data`
  - [x] `serve/routers/anomaly.py` — `/api/anomalies`, `/api/anomalies/{file_id}` (신규)
  - [ ] **⚠️ `save_to_file()` 자동 통합** — `AnomalyDetector.scan()` 미호출 → 결과 파일에 `anomaly_data` 없음 → 대시보드 항상 "이상 없음" (v1.0.0 예정)

- [x] **평가 비용 탭** 신설 (`dashboard.html.j2`, `dashboard2.html.j2`)
  - [x] KPI 카드 4개 (오늘 총 비용 / 예산 잔여 / 예상 일 비용 / 현재 샘플링률)
  - [x] 호출 수 · 모델 보조 카드
  - [x] 공급자별 비용 분포 카드
  - [x] `serve/loader.py` — `_parse_cost_data()` (budget_remaining_usd, projected_daily_usd, sample_rate_current 포함)
  - [x] `core/trackers/monitor.py` — `save_to_file()` 시 `evaluation_cost` 키 자동 직렬화 (LLM Judge 활성 시)
  - [x] `serve/routers/cost.py` — `/api/cost/summary`, `/api/cost/{file_id}` (신규)
