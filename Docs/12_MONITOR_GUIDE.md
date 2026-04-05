# `agent-eval monitor` — 운영 모니터링 가이드

OpenTelemetry + Arize Phoenix 기반 프로덕션 실시간 모니터링

**Version**: 0.7.2
**Last Updated**: 2026-04-05
**Status**: ✅ 구현 완료 (v0.7.2)

---

## 목차

1. [포지셔닝 — dashboard vs monitor](#포지셔닝)
2. [아키텍처 개요](#아키텍처)
3. [CLI 명세](#cli-명세)
4. [모듈 구조](#모듈-구조)
5. [핵심 코드 인터페이스](#핵심-코드-인터페이스)
6. [Phoenix 전송 데이터 상세](#phoenix-전송-데이터)
7. [환경 설정 / 의존성](#환경-설정--의존성)
8. [사용 예시](#사용-예시)
9. [대시보드 UI 호환성](#대시보드-ui-호환성)

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
              │  • Traces (스팬 목록)        │
              │  • Sessions (세션 그룹)      │
              │  • Evaluations (점수 차트)   │
              │  • Metrics (집계 차트)       │
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

### Phoenix Evaluations 탭 (Annotations)

`save_to_file()` 호출 시 `/v1/span_annotations` API로 전송:

| Evaluator 이름 | 점수 범위 | 레이블 |
|----------------|-----------|--------|
| `accuracy` | 0.0–1.0 | pass (≥0.5) / fail (<0.5) |
| `completion` | 0.0–1.0 | pass / fail |
| `success` | 1.0 (성공) / 0.0 (실패) | pass / fail |

### `tokens_used` 타입별 처리

| 타입 | 처리 방식 |
|------|----------|
| `dict` (`{"input": 400, "output": 100, "model": "gpt-4o"}`) | input/output 분리 전송 |
| `int` (e.g. `500`) | 80% prompt / 20% completion으로 근사 분할 |
| `None` / `0` | 토큰 0으로 전송 |

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
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType, setup_otel
import datetime

# OTEL 활성화 (agent-eval monitor 실행 후)
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

monitor = PerformanceMonitor()

result = TaskResult(
    task_id="task_001",
    task_type=TaskType.QA,
    success=True,
    completion_score=0.9,
    accuracy_score=0.85,
    execution_time=1.2,
    tokens_used={"input": 200, "output": 50, "model": "claude-sonnet-4-6"},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.datetime.now(),
)

monitor.record_task(result)
# → JSON 집계 유지 (기존 동작)
# → ae.task/qa/task_001 스팬 Phoenix에 전송 (신규)

monitor.save_to_file("results/run")
# → JSON/HTML 저장
# → Phoenix Annotation API로 accuracy/completion/success 전송
```

### `evaluation_session`과 함께

```python
from agent_evaluator import evaluation_session, setup_otel

setup_otel(endpoint="http://localhost:6006")

with evaluation_session("run_2026_04_01") as monitor:
    # ae.session 루트 스팬 시작 (openinference.span.kind="CHAIN")
    for task in tasks:
        result = agent.run(task)
        monitor.record_task(result)
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
- **Traces**: 실시간 스팬 목록 + 폭포수 뷰
- **Sessions**: monitor 인스턴스별 그룹핑
- **Evaluations**: accuracy / completion / success 점수 분포
- **Metrics**: latency 히스토그램, token 사용량 (enable_metrics=True 시)
