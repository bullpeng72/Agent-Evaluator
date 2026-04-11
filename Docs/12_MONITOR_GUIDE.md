# `agent-eval monitor` — 운영 모니터링 가이드

OpenTelemetry + Arize Phoenix 기반 프로덕션 실시간 모니터링

**Version**: 0.7.7
**Last Updated**: 2026-04-11
**Status**: ✅ 구현 완료 (v0.7.6)

---

## 목차

1. [포지셔닝 — dashboard vs monitor](#포지셔닝)
2. [아키텍처 개요](#아키텍처)
3. [빠른 시작 — 3단계](#빠른-시작)
4. [CLI 명세](#cli-명세)
5. [모듈 구조](#모듈-구조)
6. [핵심 코드 인터페이스](#핵심-코드-인터페이스)
7. [Phoenix 전송 데이터 상세](#phoenix-전송-데이터)
8. [Phoenix UI 탭별 완전 가이드](#phoenix-ui-탭별-가이드)
9. [Phoenix GraphQL 활용](#phoenix-graphql)
10. [환경 설정 / 의존성](#환경-설정--의존성)
11. [사용 예시](#사용-예시)
12. [대시보드 UI 호환성](#대시보드-ui-호환성)
13. [자주 묻는 질문 (FAQ)](#faq)

---

## 포지셔닝 {#포지셔닝}

### 두 도구의 역할 분리

| 구분 | `agent-eval dashboard` | `agent-eval monitor` |
|------|----------------------|----------------------|
| **대상** | 개발자 · QM | MLOps · 운영팀 |
| **단계** | 개발 · 검증 · 스테이징 | 프로덕션 · 운영 |
| **데이터 소스** | `save_to_file()` JSON | OTLP 스팬 스트림 (실시간) |
| **업데이트 방식** | 폴링 (15초 / --watch) | 스팬 수신 즉시 갱신 |
| **주요 뷰** | 지표 집계 · 태스크 테이블 · 히스토리 | 트레이스 · 스팬 폭포수 · 실시간 오류 |
| **저장** | JSON 파일 (results/) | SQLite (Phoenix 내부) |
| **설치 요건** | `[serve]` extras | `[otel]` extras |
| **실행 방식** | 단일 FastAPI 서버 | Arize Phoenix 서버 + OTEL exporter |

### 의사결정 흐름

```
에이전트 실행
    │
    ├─▶ save_to_file()  ──────────────▶  agent-eval dashboard
    │   (JSON 집계, 항상 동작)            개발·검증 단계 지표 확인
    │
    └─▶ OTLP Span Export (opt-in) ──▶  agent-eval monitor (Phoenix)
        (setup_otel() 호출 시)             프로덕션 실시간 트레이싱
```

---

## 아키텍처 개요 {#아키텍처}

### Phoenix 13.x 포트 구조

> Phoenix 13.x는 **UI + OTLP HTTP를 동일 포트(기본 6006)** 에서 수신한다.
> 별도의 OTLP 포트(4318)가 없다. `setup_otel(endpoint="http://localhost:6006")`로 설정.

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Application                                          │
│                                                             │
│  PerformanceMonitor.record_task()                           │
│       │                                                     │
│       ├─▶ JSON 생성 (기존 경로, 항상)                         │
│       │                                                     │
│       └─▶ OTELProvider (opt-in, setup_otel() 호출 시)       │
│               │                                             │
│               ├─▶ Span: ae.task/{type}/{task_id}            │
│               │     + OpenInference 속성                    │
│               │     + Phoenix Annotation API                │
│               └─▶ (opt-in) Metrics: ae.tcr, ae.latency...  │
│                       │                                     │
└───────────────────────┼─────────────────────────────────────┘
                        │ OTLP/HTTP  → :6006
                        ▼
              ┌─────────────────────────────┐
              │  Arize Phoenix 13.x         │
              │  agent-eval monitor 로 기동  │
              │  http://localhost:6006       │
              │                             │
              │  • Tracing (스팬 목록)       │
              │  • Datasets (골든셋)         │
              │  • Playground (프롬프트 재현)│
              │  • Evaluators (LLM 평가 설정)│
              │  • Prompts (프롬프트 버전)   │
              │  • GraphQL (데이터 조회)     │
              └─────────────────────────────┘
```

### 데이터 흐름

```
record_task(result)
    │
    ├─ [항상]  _update_trackers()  →  JSON 집계 유지
    │
    └─ [OTEL 활성화 시]  _emit_otel_span(result)
           │
           ├─ span name: "ae.task/{task_type}/{task_id}"
           │
           ├─ OpenInference 속성:
           │     openinference.span.kind  (LLM/RETRIEVER/TOOL/AGENT/CHAIN)
           │     input.value              (question 또는 task_id)
           │     output.value             (response 또는 completion_score)
           │     session.id              (monitor 인스턴스별 UUID)
           │     metadata                (JSON: task_type, framework)
           │     llm.token_count.prompt / .completion / .total
           │     llm.model_name
           │     retrieval.documents     (INFORMATION_RETRIEVAL만, 최대 4096자)
           │
           ├─ Agent Evaluator 속성:
           │     ae.task_id, ae.task_type, ae.success
           │     ae.completion_score, ae.accuracy_score
           │     ae.execution_time, ae.tokens_used
           │     ae.tool_calls_count, ae.attempts, ae.framework
           │
           ├─ 실패 태스크: SpanStatus.ERROR 설정
           │
           └─ span_id 수집 → save_to_file() 시 Annotation API POST
                 accuracy / completion / success (annotator_kind="CODE")

save_to_file()
    └─ _flush_phoenix_annotations()
           ├─ force_flush(3s)   ← span_id가 Phoenix에 도착 대기
           └─ POST /v1/span_annotations
```

---

## 빠른 시작 — 3단계 {#빠른-시작}

> **처음 사용하시나요?** 이 3단계만 따라 하면 Phoenix UI에서 에이전트 실행 결과를 바로 확인할 수 있습니다.

### 단계 1: 설치

```bash
pip install "agent-evaluator[otel]"
```

### 단계 2: Phoenix 서버 기동 (터미널 A)

```bash
agent-eval monitor
# 출력: Phoenix UI → http://localhost:6006  (브라우저 자동 오픈)
```

### 단계 3: 에이전트 실행 (터미널 B)

```python
# my_agent.py
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# ① Phoenix 연결 — 반드시 PerformanceMonitor 생성 전에 호출
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

monitor = PerformanceMonitor(output_dir="results/")

# ② 데코레이터 한 줄이면 자동으로 Phoenix에 전송됩니다
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return "서울입니다."   # 실제 LLM 호출로 교체

# ③ 실행
my_agent("한국의 수도는?", ground_truth="서울")

# ④ 점수 저장 (Phoenix에 Annotation 전송)
monitor.save_to_file("run_001")
```

```bash
python my_agent.py
# 이후 http://localhost:6006 → Tracing 탭에서 결과 확인
```

---

## CLI 명세 {#cli-명세}

### 기본 사용법

```bash
# Phoenix 서버 기동 + 브라우저 자동 오픈
agent-eval monitor

# 포트 지정 (기본 6006)
agent-eval monitor --port 6006

# 브라우저 자동 오픈 비활성화
agent-eval monitor --no-open

# 기존 Phoenix 서버에 연결 (자체 기동 안 함)
agent-eval monitor --attach http://localhost:6006

# 환경 상태 확인 (설치 여부, 포트 상태)
agent-eval monitor --check
```

### 옵션 상세

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | `6006` | Phoenix UI / OTLP HTTP 포트 (Phoenix 13.x: 동일 포트) |
| `--host` | `localhost` | Phoenix 바인딩 호스트 |
| `--no-open` | (플래그) | 브라우저 자동 오픈 비활성화 |
| `--attach <url>` | — | 자체 기동 없이 기존 Phoenix에 연결 |
| `--check` | (플래그) | 설치 상태 및 포트 점유 확인 |
| `--working-dir <path>` | `./` | Phoenix DB 저장 디렉토리 |

### 실행 시 터미널 출력 예시

```
  ┌─────────────────────────────────────────────────────────┐
  │  Agent Evaluator — 운영 모니터링                        │
  ├─────────────────────────────────────────────────────────┤
  │  Phoenix UI      http://localhost:6006                  │
  │  OTLP HTTP       http://localhost:6006                  │
  ├─────────────────────────────────────────────────────────┤
  │  에이전트 코드에 아래를 추가하세요:                      │
  │                                                         │
  │  from agent_evaluator import setup_otel                 │
  │  setup_otel(endpoint="http://localhost:6006")           │
  └─────────────────────────────────────────────────────────┘
```

### `--check` 출력 예시

```
  패키지 상태
  ──────────────────────────────────────────────────────
  ✅  arize-phoenix                         설치됨 (13.x.x)
  ✅  opentelemetry-sdk                     설치됨
  ✅  opentelemetry-exporter-otlp-proto-http  설치됨

  포트 상태  (Phoenix 13.x: UI + OTLP HTTP 동일 포트)
  ──────────────────────────────────────────────────────
  ✅  포트 6006   (Phoenix UI / OTLP HTTP) — 사용 가능
  ✅  포트 4317   (OTLP gRPC)             — 사용 가능
```

---

## 모듈 구조 {#모듈-구조}

```
agent_evaluator/
├── core/
│   └── otel/                          ← OTEL 서브패키지
│       ├── __init__.py                # setup_otel(), get_provider(), get_metrics()
│       ├── provider.py                # OTELProvider (TracerProvider 래퍼)
│       └── metrics.py                 # OTELMetrics (MeterProvider 래퍼, 기본 비활성)
│
└── cli/
    └── monitor.py                     # agent-eval monitor 구현
```

---

## 핵심 코드 인터페이스 {#핵심-코드-인터페이스}

### `setup_otel()` — 공개 API

```python
from agent_evaluator import setup_otel

setup_otel(
    endpoint="http://localhost:6006",   # Phoenix 13.x 기본 포트 (UI + OTLP 동일)
    service_name="my-agent",           # Phoenix UI 서비스 이름
    enabled=True,                      # False 시 no-op (CI 환경 등)
    enable_metrics=False,              # Phoenix는 /v1/metrics 미지원 — Grafana 등에서만 사용
)
```

### `OTELProvider` — `core/otel/provider.py`

주요 메서드:

| 메서드 | 설명 |
|--------|------|
| `span(name, attributes)` | context manager형 스팬. 실패/미활성화 시 no-op |
| `force_flush(timeout_ms=5000)` | BatchSpanProcessor 큐 즉시 플러시 |
| `enabled` (property) | OTEL 활성화 여부 |
| `base_endpoint` (property) | OTLP 수신 서버 URL (비활성화 시 None) |

### `OTELMetrics` — `core/otel/metrics.py`

> **주의**: `enable_metrics=False`가 기본값. Phoenix 13.x는 `/v1/metrics`를 지원하지 않아
> 405 오류가 발생한다. Grafana 등 별도 OTLP 메트릭 수신기가 있을 때만 활성화.

발행 지표:

| 지표 | 종류 | 설명 | 전송 시점 |
|------|------|------|----------|
| `ae.latency_seconds` | histogram | 태스크 실행 시간 | record_task() 마다 |
| `ae.accuracy` | gauge | 정확도 (0–1) | record_task() 마다 |
| `ae.tokens_total` | counter | 누적 토큰 수 | record_task() 마다 |
| `ae.error_rate` | gauge | 오류율 (0 또는 100) | record_task() 마다 |
| `ae.tcr` | gauge | 태스크 완료율 (%) | save_to_file() 1회 |

---

## Phoenix 전송 데이터 {#phoenix-전송-데이터}

### Phoenix Traces 탭

각 `record_task()` 호출마다 하나의 스팬이 전송된다.

| Phoenix 컬럼 | OTEL 속성 | 값 예시 |
|-------------|-----------|--------|
| **Name** | 스팬 이름 | `ae.task/qa/task_001` |
| **Kind** | `openinference.span.kind` | `LLM` / `RETRIEVER` / `TOOL` / `AGENT` / `CHAIN` |
| **Input** | `input.value` | 질문 텍스트 |
| **Output** | `output.value` | 응답 텍스트 |
| **Status** | SpanStatus | OK (성공) / ERROR (실패) |
| **Latency** | 스팬 duration | execution_time 기반 |

### TaskType → span kind 매핑

| TaskType | span kind |
|----------|-----------|
| `qa`, `code_generation`, `coding`, `creative` | `LLM` |
| `information_retrieval` | `RETRIEVER` |
| `tool_use` | `TOOL` |
| `planning` | `AGENT` |
| `data_analysis`, `document_creation`, `reasoning` | `CHAIN` |

### Phoenix Sessions 탭

`session.id` 속성으로 그룹핑. 하나의 `PerformanceMonitor` 인스턴스 = 하나의 세션 UUID.

### Phoenix Annotations (점수 전송)

`save_to_file()` 호출 시 `/v1/span_annotations` API로 전송:

| Evaluator 이름 | 점수 범위 | 레이블 |
|----------------|-----------|--------|
| `accuracy` | 0.0–1.0 | pass (≥0.5) / fail (<0.5) |
| `completion` | 0.0–1.0 | pass / fail |
| `success` | 1.0 (성공) / 0.0 (실패) | pass / fail |

> **어디서 확인하나?** → Tracing 탭 → 스팬 클릭 → 우측 **"Annotations"** 섹션.
> 상단 메뉴의 "Evaluators" 탭이 아닙니다. (자세한 내용은 [FAQ](#faq) 참고)

### `tokens_used` 타입별 처리

| 타입 | 처리 방식 |
|------|----------|
| `dict` (`{"input": 400, "output": 100, "model": "gpt-4o"}`) | input/output 분리 전송 |
| `int` (e.g. `500`) | 80% prompt / 20% completion으로 근사 분할 |
| `None` / `0` | 토큰 0으로 전송 |

---

## Phoenix UI 탭별 완전 가이드 {#phoenix-ui-탭별-가이드}

> Phoenix UI를 처음 열면 왼쪽 사이드메뉴에 여러 탭이 있습니다.
> 각 탭이 무엇을 보여주는지, Agent-Evaluator와 어떻게 연결되는지 설명합니다.

### 탭 한눈에 보기

| 탭 이름 | 한 줄 설명 | Agent-Evaluator 연동 |
|---------|-----------|---------------------|
| **Tracing** | 에이전트 실행 내역 (스팬 목록) | `record_task()` → 자동 전송 |
| **Datasets** | 골든 데이터셋 관리 | `GoldenSetBuilder` + GraphQL |
| **Playground** | 프롬프트 재현·수정 도구 | `llm.prompts` 속성 전송 시 |
| **Evaluators** | LLM 자동 평가 템플릿 설정 | 직접 설정 필요 (자동 연동 아님) |
| **Prompts** | 프롬프트 버전 관리 | REST POST `/v1/prompts` |
| **GraphQL** | 데이터 직접 조회 UI | 모든 데이터 조회 가능 |

---

### 1. Tracing 탭 — 에이전트 실행 기록

**한 줄 요약**: `record_task()`를 호출할 때마다 여기에 한 줄씩 기록됩니다.

**보이는 것:**
- 스팬 이름 (예: `ae.task/qa/task_001`)
- 성공/실패 상태, 실행 시간, 입력/출력 텍스트

**에이전트 점수(Annotations) 확인 방법:**

```
Tracing 탭
  └─ 스팬 목록에서 원하는 스팬 클릭
       └─ 우측 상세 패널
            └─ "Annotations" 섹션
                 ├─ accuracy: 0.85 (pass)
                 ├─ completion: 0.90 (pass)
                 └─ success: 1.0 (pass)
```

> Annotations는 `save_to_file()` 호출 후 약 3초 뒤에 나타납니다.
> `monitor.save_to_file("filename")` 를 꼭 호출해야 합니다.

**프로젝트별 스팬 분리:**

Phoenix에는 여러 에이전트/프로젝트의 스팬이 섞일 수 있습니다.
`setup_otel(service_name="프로젝트명")`으로 지정하면 Phoenix UI 상단 드롭다운에서 프로젝트를 선택할 수 있습니다.

---

### 2. Datasets 탭 — 골든 데이터셋 관리

**한 줄 요약**: 평가에 쓸 "정답이 있는 질문 모음"을 저장하고 관리합니다.

**어떻게 만들어지나?**

Agent-Evaluator의 `GoldenSetBuilder`로 추출한 케이스를 Phoenix에 업로드하면 이 탭에 표시됩니다.

```python
from agent_evaluator.datasets import GoldenSetBuilder

builder = GoldenSetBuilder(monitor)
# 점수 0.8 이상 태스크를 골든셋으로 추출
cases = builder.extract_from_monitor(min_score=0.8)
# Phoenix에 업로드
builder.push_to_phoenix(cases, dataset_name="qa-golden-v1")
```

또는 GraphQL로 직접 생성할 수 있습니다 (→ [GraphQL 섹션](#phoenix-graphql) 참고).

**데이터셋을 어떻게 활용하나?**

Phoenix Playground에서 데이터셋을 선택해 프롬프트를 일괄 테스트하거나,
Evaluators 탭과 연결해 자동 채점할 수 있습니다.

---

### 3. Playground 탭 — 프롬프트 재현 도구

**한 줄 요약**: 특정 스팬의 입력/출력을 가져와서 프롬프트를 수정·재시도해 볼 수 있는 인터랙티브 도구입니다.

**Agent-Evaluator와 연동 방법:**

`llm.prompts` 속성을 스팬에 포함하면 Playground에서 해당 스팬을 재현할 수 있습니다.

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval, EvalMetadata

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = "서울입니다."
    # llm.prompts 속성 추가 → Playground 재현 가능
    return response, EvalMetadata(
        extra={
            "llm.prompts": [
                {"role": "user", "content": question}
            ]
        }
    )
```

**주의**: `llm.prompts`가 없으면 Playground 탭에서 "No prompt data" 메시지가 표시됩니다.

---

### 4. Evaluators 탭 — LLM 자동 평가 설정

**한 줄 요약**: Phoenix 자체 LLM Evaluator 템플릿(예: "답변이 관련성이 있나?")을 설정하는 곳입니다.

> ⚠️ **자주 하는 오해**: Agent-Evaluator의 `accuracy`/`completion`/`success` 점수는
> **이 탭에 표시되지 않습니다**.
> 이 점수들은 Tracing 탭 → 스팬 상세 → "Annotations" 섹션에 있습니다.

**Evaluators 탭이란?**

Phoenix에 내장된 LLM Judge 기능입니다.
"이 응답이 질문과 관련 있나요?" 같은 평가 기준을 Phoenix에 등록하면,
Phoenix가 알아서 새 스팬마다 LLM으로 점수를 매겨줍니다.

**현재 Agent-Evaluator 연동 상태:**

Agent-Evaluator는 자체 `accuracy`/`completion`/`success`를 Annotation으로 전송합니다.
Phoenix Evaluators 탭에 기본 항목이 없으면 직접 템플릿을 추가해야 합니다.

**Evaluators 탭에 항목 추가 방법 (Phoenix UI 직접):**

1. `http://localhost:6006` → 왼쪽 **"Evaluators"** 탭 클릭
2. **"+ New Evaluator"** 버튼 클릭
3. 평가 기준 선택 (예: Hallucination, Q&A Correctness 등)
4. LLM 모델 연결 (OpenAI API 키 필요)
5. 트레이스 데이터에 자동 적용

> **초보자 팁**: Evaluators 탭을 반드시 사용할 필요는 없습니다.
> Agent-Evaluator 자체 점수(Annotations)만으로도 충분한 평가가 가능합니다.

---

### 5. Prompts 탭 — 프롬프트 버전 관리

**한 줄 요약**: 프롬프트 텍스트를 버전별로 저장하고 관리하는 저장소입니다.

**Agent-Evaluator에서 프롬프트 등록:**

```python
import requests

# Phoenix REST API로 프롬프트 등록
response = requests.post("http://localhost:6006/v1/prompts", json={
    "name": "qa-system-prompt",
    "version": "v1.0",
    "template": "당신은 정확한 답변을 제공하는 AI 어시스턴트입니다.\n질문: {question}\n답변:",
    "tags": ["production", "qa"],
})
print(response.json())  # {"id": "prompt-xxx", "name": "qa-system-prompt", ...}
```

**언제 필요한가?**

프롬프트 변경이 성능에 어떤 영향을 주는지 A/B 비교를 하거나,
팀원들이 같은 프롬프트를 공유해야 할 때 사용합니다.

---

### 6. GraphQL 탭 — 데이터 직접 조회

**한 줄 요약**: Phoenix에 저장된 모든 데이터를 SQL처럼 직접 조회할 수 있는 인터페이스입니다.

> 자세한 내용은 다음 섹션 [Phoenix GraphQL 활용](#phoenix-graphql)에서 다룹니다.

---

## Phoenix GraphQL 활용 {#phoenix-graphql}

> **GraphQL이 처음이신가요?**
> GraphQL은 "원하는 데이터만 정확하게 요청하는 쿼리 언어"입니다.
> Phoenix의 모든 데이터(트레이스, 데이터셋, 평가 결과 등)를 자유롭게 조회할 수 있습니다.

### GraphQL UI 접속

Phoenix 서버가 실행 중이면 브라우저에서 바로 접속할 수 있습니다.
별도 로그인이나 인증이 필요 없습니다.

```
http://localhost:6006/graphql
```

접속하면 **Strawberry GraphiQL** UI가 열립니다.
왼쪽에 쿼리를 입력하고 ▶ 버튼을 누르면 오른쪽에 결과가 나타납니다.

---

### 준비된 쿼리 5가지

아래 쿼리를 GraphiQL UI에 붙여넣기해 바로 사용할 수 있습니다.

#### 쿼리 1: 프로젝트 목록 조회

어떤 서비스/프로젝트가 Phoenix에 데이터를 보내고 있는지 확인합니다.

```graphql
query {
  projects {
    edges {
      node {
        id
        name
        traceCount
        spanCount
        createdAt
      }
    }
  }
}
```

**결과 예시:**
```json
{
  "data": {
    "projects": {
      "edges": [
        {
          "node": {
            "id": "UHJvamVjdDox",
            "name": "my-agent",
            "traceCount": 42,
            "spanCount": 156,
            "createdAt": "2026-04-08T10:00:00Z"
          }
        }
      ]
    }
  }
}
```

---

#### 쿼리 2: 스팬 목록 + 평가 점수 조회

특정 프로젝트의 최근 스팬과 Annotation 점수를 함께 조회합니다.

```graphql
query GetSpansWithAnnotations($projectName: String!) {
  project(name: $projectName) {
    spans(first: 20) {
      edges {
        node {
          spanId
          name
          statusCode
          latencyMs
          input {
            value
          }
          output {
            value
          }
          spanAnnotations {
            name
            score
            label
          }
        }
      }
    }
  }
}
```

**변수 설정** (UI 하단 Variables 패널에 입력):
```json
{
  "projectName": "my-agent"
}
```

---

#### 쿼리 3: 데이터셋 목록 조회

Phoenix에 저장된 골든 데이터셋 목록을 확인합니다.

```graphql
query {
  datasets {
    edges {
      node {
        id
        name
        description
        exampleCount
        createdAt
      }
    }
  }
}
```

---

#### 쿼리 4: 데이터셋 생성 (Mutation)

새 골든 데이터셋을 GraphQL로 직접 생성합니다.

```graphql
mutation CreateDataset {
  createDataset(
    name: "qa-golden-v2"
    description: "QA 평가용 골든셋 v2"
  ) {
    dataset {
      id
      name
    }
  }
}
```

---

#### 쿼리 5: 데이터셋에 예시 추가

위에서 만든 데이터셋에 질문-정답 쌍을 추가합니다.

```graphql
mutation AddDatasetExamples($datasetId: GlobalID!) {
  addSpansToDataset(
    datasetId: $datasetId
    spanIds: []
    examples: [
      {
        input: { question: "한국의 수도는?" }
        output: { answer: "서울" }
        metadata: { source: "manual", difficulty: "easy" }
      }
    ]
  ) {
    dataset {
      id
      name
      exampleCount
    }
  }
}
```

---

### Python에서 GraphQL 호출

UI 말고 코드에서 직접 GraphQL을 호출할 수도 있습니다.

```python
import requests

PHOENIX_URL = "http://localhost:6006"

def query_phoenix(query: str, variables: dict = None) -> dict:
    """Phoenix GraphQL 엔드포인트 호출 헬퍼."""
    response = requests.post(
        f"{PHOENIX_URL}/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


# 프로젝트 목록 조회
result = query_phoenix("""
    query {
        projects {
            edges {
                node { id name traceCount }
            }
        }
    }
""")

for edge in result["data"]["projects"]["edges"]:
    project = edge["node"]
    print(f"프로젝트: {project['name']}  (트레이스: {project['traceCount']}개)")
```

---

### GraphQL vs REST — 언제 무엇을 쓰나?

| 작업 | 방법 | 엔드포인트 |
|------|------|-----------|
| 스팬 전송 (에이전트 실행 기록) | REST (OTLP) | OTLP/HTTP 자동 처리 |
| Annotation 점수 전송 | REST | `POST /v1/span_annotations` |
| 프롬프트 등록 | REST | `POST /v1/prompts` |
| 프로젝트 목록 조회 | **GraphQL** | `POST /graphql` |
| 데이터셋 생성·조회 | **GraphQL** | `POST /graphql` |
| Evaluators 구성 | **GraphQL** | `POST /graphql` |
| 스팬+Annotation 함께 조회 | **GraphQL** | `POST /graphql` |

> **한 줄 원칙**: 데이터를 "쓸 때"는 REST, "읽거나 만들 때"는 GraphQL이 편리합니다.

---

## 환경 설정 / 의존성 {#환경-설정--의존성}

### 설치

```bash
pip install "agent-evaluator[otel]"
```

포함 패키지:
- `opentelemetry-sdk>=1.20.0,<2.0.0`
- `opentelemetry-exporter-otlp-proto-http>=1.20.0,<2.0.0`
- `arize-phoenix>=0.11.0`

### 환경변수 (선택)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PHOENIX_PORT` | `6006` | Phoenix 서버 포트 (agent-eval monitor 기동 시 자동 설정) |
| `OTEL_SERVICE_NAME` | `agent-evaluator` | Phoenix UI 서비스 이름 |

---

## 사용 예시 {#사용-예시}

### 기본 패턴

```bash
# 터미널 1 — Phoenix 서버 기동
agent-eval monitor

# 터미널 2 — 에이전트 실행
python my_agent.py
```

```python
# my_agent.py
from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel
from agent_evaluator.decorators import agent_eval

# OTEL 활성화 (agent-eval monitor 실행 후)
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

monitor = PerformanceMonitor(output_dir="results/")

# 데코레이터 방식 (권장) — record_task + OTEL 스팬 자동 발행
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("대한민국의 수도는?", ground_truth="서울")
# → ae.task/qa/{task_id} 스팬 Phoenix에 전송

monitor.save_to_file("run")
# → results/run.json + .html 저장
# → Phoenix Annotation API로 accuracy/completion/success 전송

# 수동 기록 방식 (저수준)
result = create_taskresult(
    task_id="task_001",
    question="대한민국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.2,
    task_type="qa",
    tokens_used={"input": 200, "output": 50, "total": 250},
)
monitor.record_task(result)
# → ae.task/qa/task_001 스팬 Phoenix에 전송
```

### `evaluation_session`과 함께

```python
from agent_evaluator import PerformanceMonitor, evaluation_session, setup_otel
from agent_evaluator.decorators import agent_eval

setup_otel(endpoint="http://localhost:6006")

with evaluation_session("run_2026_04_01") as monitor:
    # ae.session 루트 스팬 시작 (openinference.span.kind="CHAIN")

    @agent_eval(monitor, task_type="qa")
    def my_agent(question: str, ground_truth: str = "") -> str:
        return llm.invoke(question)

    for task in tasks:
        my_agent(task["question"], ground_truth=task.get("answer", ""))
        # 각 호출 → ae.task/{type}/{id} 자식 스팬 자동 발행
# 세션 종료: JSON 저장 + Phoenix Annotation API 전송
```

### eval_context — 데코레이터를 붙일 수 없는 외부 함수

```python
from agent_evaluator.decorators import eval_context

with evaluation_session("run_2026_04_01") as monitor:
    for task in tasks:
        with eval_context(monitor, task_type="qa",
                          question=task["question"],
                          ground_truth=task.get("answer", "")) as ctx:
            ctx.response = external_agent.run(task["question"])
        # 각 task → ae.task/{type}/{id} 자식 스팬
# 세션 종료: JSON 저장 + Phoenix Annotation API 전송
```

### Phoenix 미실행 시 자동 비활성화 패턴 (예제 파일 표준)

```python
def _try_setup_otel(service_name: str) -> None:
    """Phoenix가 실행 중이면 OTEL 활성화. 미실행 시 무시."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("localhost", 6006)) != 0:
            return  # Phoenix 미실행 — no-op
    from agent_evaluator import setup_otel
    setup_otel(endpoint="http://localhost:6006", service_name=service_name)
    print(f"  Phoenix 모니터링 활성화 — http://localhost:6006")

_try_setup_otel("my-service")
```

### 기존 Phoenix 서버(팀 공용)에 연결

```bash
# 자체 기동 없이 팀 Phoenix 서버에 연결
agent-eval monitor --attach http://phoenix.internal:6006
```

```python
# 에이전트 코드에서
setup_otel(endpoint="http://phoenix.internal:6006")
```

### CI/CD 환경 — OTEL 비활성화

```python
import os
from agent_evaluator import setup_otel

if os.getenv("CI") != "true":
    setup_otel(endpoint="http://localhost:6006")
# CI에서는 setup_otel() 미호출 → OTEL no-op, JSON 저장은 정상 동작
```

---

## 대시보드 UI 호환성 {#대시보드-ui-호환성}

OTEL 활성화 여부와 관계없이 `agent-eval dashboard` 탭은 모두 정상 동작한다.
OTEL 스팬은 JSON 생성 로직과 완전히 독립된 추가 경로다.

| 탭 | OTEL 영향 | 데이터 소스 |
|----|-----------|------------|
| 📊 Overview | 없음 | JSON |
| 🎯 품질 | 없음 | JSON |
| 💬 멀티턴 대화 | 없음 | JSON |
| ⚡ 성능 | 없음 | JSON |
| 🤖 에이전틱 | 없음 | JSON |
| 🔒 보안 | 없음 | JSON |
| 🔍 인사이트 | 없음 | JSON |
| 📡 실시간 | 없음 | StreamingEvaluator |
| 🔔 알림 | 없음 | AlertEngine |
| 👍 사용자 반응 | 없음 | ImplicitFeedbackTracker |
| 🚨 이상 감지 | 없음 | AnomalyDetector |
| 💰 평가 비용 | 없음 | CostTracker |
| 🌟 골든 데이터셋 | 없음 | GoldenSetBuilder |
| 🔬 투명성 | 없음 | TestTransparencyManager |

Phoenix UI에서는 별도로:
- **Tracing**: 실시간 스팬 목록 + 폭포수 뷰
- **Sessions**: monitor 인스턴스별 그룹핑
- **Evaluations**: accuracy / completion / success 점수 분포 (Tracing 탭 → Annotations)
- **Metrics**: latency 히스토그램, token 사용량 (`enable_metrics=True` 시)

---

## 자주 묻는 질문 (FAQ) {#faq}

### Q1. "Evaluators 탭에 아무것도 없어요. 평가 점수가 안 보여요."

**원인**: Evaluators 탭 ≠ Agent-Evaluator 점수.

Agent-Evaluator의 `accuracy`/`completion`/`success` 점수는 **Span Annotations**으로 전송됩니다.
Phoenix의 Evaluators 탭은 Phoenix 자체 LLM Judge 템플릿을 설정하는 별도 기능입니다.

**점수 확인 경로**:
```
Tracing 탭 → 스팬 클릭 → 우측 패널 → "Annotations" 섹션
```

**Evaluators 탭이 비어있는 것은 정상**입니다. 필요하면 Phoenix에서 직접 LLM Evaluator를 설정하세요.

---

### Q2. "save_to_file()을 호출했는데 Annotations이 안 보여요."

가능한 원인 두 가지:

1. **스팬이 아직 Phoenix에 도착하지 않은 경우** — `save_to_file()` 전에 짧은 대기가 필요합니다:

```python
import time
monitor.save_to_file("run")   # 내부적으로 3초 force_flush 대기
# 그래도 안 보이면 10초 후 새로고침
```

2. **스팬 ID 수집이 안 된 경우** — `setup_otel()`을 `PerformanceMonitor` **생성 전**에 호출했는지 확인하세요:

```python
# ✅ 올바른 순서
setup_otel(endpoint="http://localhost:6006")
monitor = PerformanceMonitor(output_dir="results/")

# ❌ 잘못된 순서 (OTEL 미연결)
monitor = PerformanceMonitor(output_dir="results/")
setup_otel(endpoint="http://localhost:6006")  # 이미 monitor 생성 후라 스팬 ID 수집 안됨
```

---

### Q3. "Phoenix GraphQL에서 데이터를 조회하면 비어있어요."

1. 에이전트를 실행하고 `save_to_file()`을 호출했는지 확인
2. `setup_otel(service_name="xxx")`의 서비스 이름과 Phoenix UI의 프로젝트 이름이 일치하는지 확인
3. GraphQL 쿼리에서 `projectName` 변수를 올바르게 설정했는지 확인

---

### Q4. "대시보드(agent-eval dashboard)와 모니터(agent-eval monitor)를 동시에 써도 되나요?"

**예, 완전히 독립입니다.** 두 도구는 데이터 경로가 다릅니다.

- `agent-eval dashboard`: `results/*.json` 파일을 읽음
- `agent-eval monitor`: OTLP HTTP로 전송된 스팬을 Phoenix DB에 저장

둘 다 동시에 실행해도 서로 영향을 주지 않습니다.

---

### Q5. "agent-eval monitor가 이미 실행 중인데 또 기동하면 어떻게 되나요?"

포트 6006이 이미 사용 중이면 오류가 발생합니다.
기존 프로세스를 종료하고 재기동하거나, `--attach` 옵션으로 기존 서버에 연결하세요:

```bash
# 기존 서버 종료
lsof -ti :6006 | xargs kill -9

# 재기동
agent-eval monitor

# 또는 기존 서버 유지하고 연결만
agent-eval monitor --attach http://localhost:6006
```

---

### Q6. "Phoenix GraphQL UI URL은 어디인가요?"

```
http://localhost:6006/graphql
```

브라우저에서 직접 열면 GraphiQL 인터랙티브 UI가 나타납니다.
인증 없이 바로 쿼리를 실행할 수 있습니다.

---

### 운영자용 빠른 참조

| 확인 항목 | 방법 |
|-----------|------|
| 에이전트 실행 기록 | Phoenix → Tracing 탭 |
| 특정 스팬의 정확도/완료율 점수 | Tracing → 스팬 클릭 → Annotations 섹션 |
| 실시간 오류 스팬 | Tracing → Status 필터 = ERROR |
| 세션별 묶어보기 | Phoenix → Sessions 탭 |
| 골든 데이터셋 현황 | Phoenix → Datasets 탭 |
| 데이터 직접 조회 | `http://localhost:6006/graphql` |
| Phoenix 연결 확인 | `agent-eval monitor --check` |
| 서버 재기동 | `lsof -ti :6006 \| xargs kill -9 && agent-eval monitor` |
