# Chapter 19. OpenTelemetry와 Phoenix 실시간 모니터링

> **이 챕터에서 배우는 것**
> - OpenTelemetry(OTEL)가 무엇인지, 에이전트 평가에 적용하는 이유
> - `setup_otel()` 올바른 호출 순서 — 이 순서를 틀리면 스팬이 발행되지 않는다
> - `agent-eval monitor` CLI로 Phoenix 서버를 기동하고 첫 트레이스를 보는 2-터미널 패턴
> - Phoenix 4개 탭(Tracing, Evaluators, Datasets & Experiments, Prompts) 완전 활용법
> - 25개 스팬 속성(`ae.*`)을 활용한 필터링과 분석
> - OTEL이 Gate G(Observability)를 프로덕션에서 실시간으로 구현하는 인프라인 이유

---

## 19.1 OpenTelemetry 개념 — 에이전트 평가에 적용하는 이유

**OpenTelemetry(OTEL)**는 분산 시스템의 관찰 가능성(Observability)을 위한 오픈 표준이다. CNCF(Cloud Native Computing Foundation)가 관리하며, 벤더에 종속되지 않는 SDK와 프로토콜을 제공한다. 원래는 마이크로서비스의 분산 추적을 위해 만들어졌지만, AI 에이전트 평가에도 자연스럽게 들어맞는다.

> **Harness Engineering 관점**: OTEL은 단순한 로깅 도구가 아니다. **Gate G(Observability)**를 프로덕션 환경에서 실시간으로 구현하는 인프라다. `ExplainabilityConfig`(추론 설명 가능성), `LatencyAttributionConfig`(지연 원인 분석)처럼 오프라인 평가에서 측정한 Gate G 지표를, OTEL 스팬을 통해 배포 후에도 지속적으로 추적할 수 있다. **"측정 → 감지 → 대응"** 루프가 완성된다.
>
> | Gate G Config | OTEL 스팬에서의 역할 |
> |---------------|---------------------|
> | `ExplainabilityConfig` | `ae.reasoning_steps` 속성 — 각 스팬에서 추론 단계 기록 |
> | `LatencyAttributionConfig` | 자식 스팬(child span) 워터폴 — 지연 원인 구간별 추적 |
> | `ObservabilityConfig` | `ae.*` 속성 25개 — 에이전트 내부 상태 실시간 노출 |
> | `ErrorDiagnosisConfig` | 스팬 status=ERROR + `ae.has_error` — 오류 원인 즉시 진단 |

### 핵심 개념 4가지

**Span — 에이전트 1회 실행의 기록 단위**

스팬(Span)은 "어떤 작업이 언제 시작해서 언제 끝났는가"를 기록하는 단위다. 에이전트가 질문을 받아 응답을 반환하는 과정이 하나의 스팬이다. 스팬에는 시작 시각, 종료 시각, 그리고 수십 개의 속성(Attribute — 키-값 쌍)이 기록된다. Agent-Evaluator에서는 `record_task()` 1회 호출 = 1개 스팬이다.

예를 들어 "한국의 수도는?" 이라는 질문에 에이전트가 답하면, `ae.accuracy_score=0.95`, `ae.execution_time=1.23` 같은 속성이 스팬에 자동으로 담긴다.

**Trace — 연결된 Span들의 집합**

에이전트가 여러 도구를 호출하면 루트 스팬 아래 자식 스팬들이 트리 구조를 이룬다. 이 전체가 하나의 트레이스(Trace)다. Phoenix Tracing 탭에서는 이 트리를 "워터폴(Waterfall)" 뷰로 시각화한다.

```
사용자 요청
    └── 에이전트 호출 (루트 스팬, ~2.3초)
            ├── search_web (자식 스팬, ~0.8초)
            ├── summarize  (자식 스팬, ~1.1초)
            └── 응답 생성  (자식 스팬, ~0.4초)
```

**OTLP — Phoenix에 스팬을 전송하는 프로토콜**

OTLP(OpenTelemetry Protocol)는 스팬을 수신 서버로 전송하는 표준 프로토콜이다. HTTP 또는 gRPC를 통해 전송한다. Agent-Evaluator는 OTLP/HTTP로 Arize Phoenix에 스팬을 전송한다. Phoenix 기본 포트 6006이 UI와 OTLP HTTP를 동시에 처리한다.

**Exporter — OTLP 전송 담당**

`OTELProvider`(`agent_evaluator/core/otel/provider.py`)가 내부에서 `BatchSpanProcessor`와 `OTLPSpanExporter`를 구성해 스팬을 수집하고 Phoenix로 전송한다. 사용자는 `setup_otel()`만 호출하면 된다. 메트릭 익스포터가 필요하면 `OTELMetrics`(`core/otel/metrics.py`)를 별도로 활성화한다.

### 에이전트 평가와 OTEL의 자연스러운 결합

에이전트 평가 데이터는 OTEL 스팬과 구조가 거의 동일하다.

| 에이전트 평가 개념 | OTEL 개념 |
|-----------------|-----------|
| 태스크 1회 실행 | 스팬(Span) |
| 평가 세션 전체 | 트레이스(Trace) |
| 정확도, 완료율, 레이턴시 | 스팬 속성(Attribute) |
| 도구 호출 단계 | 자식 스팬(Child Span) |

Agent-Evaluator에서 `record_task()`를 호출하면, 이미 계산된 25개 지표가 그대로 스팬 속성으로 변환되어 Phoenix에 전송된다. 코드를 따로 바꿀 필요가 없다.

### 관측가능성 루프 — 측정 → 감지 → 대응

OTEL이 에이전트 품질 유지에 기여하는 방식은 단순한 로그 수집이 아니다. **측정 → 감지 → 대응** 루프를 형성한다.

1. **측정**: `record_task()` 호출마다 정확도·레이턴시·보안 위협 등 25개 속성이 스팬으로 Phoenix에 전송된다
2. **감지**: Phoenix Tracing 탭 필터(`ae.accuracy_score < 0.5`, `ae.security_threat_detected == "true"`)로 이상 징후를 즉시 포착한다
3. **대응**: Tracing → Playground에서 실패 스팬을 재현하고 프롬프트를 수정해 다음 배포에 반영한다

이 루프가 Gate G(Observability)를 오프라인 평가에서 프로덕션 실시간 감시로 확장한다.

---

## 19.2 setup_otel() — 올바른 설정 순서 (핵심!)

이것이 가장 중요한 내용이다. `setup_otel()`은 반드시 `PerformanceMonitor` 또는 `QuickEval` 생성 **전에** 호출해야 한다. 순서가 바뀌면 OTEL이 활성화되지 않고, Phoenix에 스팬이 전혀 전송되지 않는다.

### 올바른 순서

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — QuickEval 평가
from agent_evaluator import setup_otel, QuickEval, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# ① 가장 먼저: setup_otel() 호출
#   endpoint는 "http://localhost:6006" — /v1/traces 경로를 붙이지 말 것
#   arize-phoenix>=7.0.0,<15.0.0 / opentelemetry-sdk>=1.20.0 기본 설치에 포함
setup_otel(
    endpoint="http://localhost:6006",   # Phoenix: UI + OTLP HTTP 동일 포트 (기본 6006)
    service_name="my-qa-agent",         # Phoenix 좌측 사이드바 프로젝트명으로 표시됨
    enable_metrics=False                # Phoenix는 /v1/metrics 미지원 — False 권장
)

# ② 그 다음: PerformanceMonitor 또는 QuickEval 생성
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_otel_child_spans=True        # chain_steps를 자식 스팬으로 발행 (선택)
)

# QuickEval 사용 시에도 동일한 순서
# setup_otel(...)    ← 반드시 먼저
# eval = QuickEval("results/")
```

### QuickEval과 함께 사용하는 완전한 예제

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — QuickEval 평가
from agent_evaluator import setup_otel, QuickEval

# ① OTEL 설정 — 이 한 줄이 먼저
setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-qa-agent",
)

# ② QuickEval 생성
eval = QuickEval("results/")

# ③ 데코레이터 적용
@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)   # 실제 LLM 호출로 교체

# ④ 실행 — 각 호출마다 OTLP 스팬이 자동으로 Phoenix에 전송됨
my_agent("한국의 수도는?", ground_truth="서울")
my_agent("Python을 만든 사람은?", ground_truth="귀도 반 로섬")

# ⑤ 저장 및 Phoenix Annotation 전송
eval.save()
```

### 잘못된 순서 (이렇게 하면 스팬이 전송되지 않음)

```python
# 잘못된 예 — PerformanceMonitor를 먼저 만들면 OTEL이 등록되지 않음
monitor = PerformanceMonitor("results/")  # 여기서 이미 OTEL 없이 초기화됨
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")  # 늦음!
```

> ⚙️ **DevOps TIP**: `setup_otel()`은 모듈의 최상단, 모든 import 바로 다음에 위치시켜라. 미들웨어 설정처럼 "가장 먼저 실행되어야 하는 코드"로 취급하면 실수를 방지할 수 있다.

---

## 19.3 agent-eval monitor — 2-터미널 패턴

Phoenix를 로컬에서 실행하는 가장 간단한 방법은 `agent-eval monitor` 명령어다. Phoenix 서버 기동과 OTLP 엔드포인트 설정을 한 번에 처리한다.

### 2-터미널 패턴

**터미널 A — Phoenix 서버 기동**

```bash
# Phoenix 서버 시작 (기본 포트 6006)
agent-eval monitor

# 실행 후 출력:
#   Phoenix UI      http://localhost:6006
#   OTLP HTTP       http://localhost:6006
#   에이전트 코드에 아래를 추가하세요:
#     from agent_evaluator import setup_otel
#     setup_otel(endpoint="http://localhost:6006")

# 포트 변경
agent-eval monitor --port 6007

# 브라우저 자동 오픈 없이 서버만 기동
agent-eval monitor --no-open
```

**터미널 B — 에이전트 실행**

```bash
python my_agent_eval.py
# 실행 후 http://localhost:6006 → Tracing 탭에서 결과 확인
```

**접속**: 브라우저에서 `http://localhost:6006` 열기

### 설치 상태 확인

Phoenix를 처음 사용하거나 문제가 생겼을 때, `--check` 옵션으로 설치 상태와 포트 점유 여부를 확인한다.

```bash
agent-eval monitor --check

# 출력 예시:
#   패키지 상태
#   ──────────────────────────────────────────────────────
#   ✅  arize-phoenix                                    설치됨 (14.x.x)
#   ✅  opentelemetry-sdk                               설치됨
#   ✅  opentelemetry-exporter-otlp-proto-http          설치됨
#
#   포트 상태  (Phoenix 13.x: UI + OTLP HTTP 동일 포트)
#   ──────────────────────────────────────────────────────
#   ✅  포트 6006   (Phoenix UI / OTLP HTTP) — 사용 가능
#   ✅  포트 4317   (OTLP gRPC)             — 사용 가능
```

### CLI 옵션 전체

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | `6006` | Phoenix UI + OTLP HTTP 포트 |
| `--host` | `localhost` | Phoenix 바인딩 호스트 |
| `--no-open` | — | 브라우저 자동 오픈 비활성화 |
| `--attach <url>` | — | 자체 기동 없이 기존 Phoenix에 연결 |
| `--check` | — | OTEL 패키지 설치 상태 및 포트 점유 확인 |
| `--working-dir <path>` | Phoenix 자동 결정(`~/.phoenix`) | Phoenix DB 저장 디렉토리 |
| `--sync-datasets <glob>` | — | 골든셋 JSON 파일을 Phoenix Datasets로 업로드 |
| `--reset` | — | Phoenix DB 초기화 (모든 트레이스·데이터셋 삭제) |
| `--yes` / `-y` | — | `--reset` 확인 프롬프트 생략 |

---

## 19.4 Phoenix 4개 탭 완전 활용법

`http://localhost:6006`을 브라우저에서 열면 Phoenix UI가 표시된다. 왼쪽 사이드바에 탭들이 있다. 처음 접속하면 Tracing 탭이 비어 있는데, 에이전트를 실행해 스팬을 전송하면 수 초 내에 데이터가 나타난다. 각 탭이 무엇을 보여주는지, Agent-Evaluator와 어떻게 연결되는지 살펴본다.

### Tracing 탭 — 에이전트 실행 기록의 핵심

Tracing 탭은 Phoenix의 핵심이다. `record_task()`를 호출할 때마다 여기에 한 줄씩 기록된다. 스팬 이름, 성공/실패 상태, 실행 시간, 입력/출력 텍스트를 한눈에 볼 수 있다.

**실패 케이스 추출 — 필터 활용**

```
# 정확도 낮은 케이스
ae.accuracy_score < 0.6

# RAG 태스크만 보기
ae.task_type == "information_retrieval"

# 보안 위협 탐지
ae.security_threat_detected == "true"

# 느린 호출
ae.execution_time > 5.0

# LangChain 프레임워크
ae.framework == "langchain"

# 도구 3회 이상 호출
ae.tool_calls_count >= 3
```

**개별 스팬 클릭 → 25개 속성 전체 확인**

특정 스팬을 클릭하면 우측 상세 패널에서 모든 속성을 볼 수 있다.

```
ae.task_id           = "task_001"
ae.task_type         = "qa"
ae.accuracy_score    = 0.87
ae.execution_time    = 1.23
ae.tokens_used       = 850
ae.tool_calls_count  = 3
ae.tool_names        = '["search_web", "calculator", "summarize"]'
input.value          = "한국의 GDP는?"
output.value         = "2023년 기준 약 1조 7천억 달러입니다."
```

**child spans — 자식 스팬 워터폴 뷰**

`enable_otel_child_spans=True` 설정 시, `chain_steps`가 자식 스팬으로 발행되어 도구 호출 흐름을 워터폴로 확인할 수 있다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — PerformanceMonitor 설정
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval, EvalMetadata

setup_otel(endpoint="http://localhost:6006", service_name="multi-tool-agent")

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_otel_child_spans=True   # 자식 스팬 활성화
)

@agent_eval(monitor, task_type="tool_use")
def multi_tool_agent(question: str, ground_truth: str = "") -> tuple:
    weather = weather_api(question)
    restaurants = restaurant_search(question)
    summary = summarize(weather, restaurants)
    return summary, EvalMetadata(
        tool_calls=["weather_api", "restaurant_search", "summarize"],
        extra={
            "chain_steps": [
                {"name": "weather_api",       "duration": 0.6},
                {"name": "restaurant_search", "duration": 1.4},
                {"name": "summarize",         "duration": 0.8},
            ]
        }
    )
# Phoenix에서 3개의 자식 스팬이 워터폴로 표시됨
```

- `enable_otel_child_spans=True`를 설정하면 `chain_steps` 항목이 각각 자식 스팬으로 발행되어 Phoenix에서 워터폴 뷰로 확인할 수 있다
- `chain_steps`의 `duration` 값이 자식 스팬의 실행 시간으로 표시되어 어느 도구 호출이 병목인지 즉시 파악된다
- 루트 스팬 아래 자식 스팬 트리가 생성되므로 도구 호출 순서와 전체 레이턴시 구성을 시각적으로 분석할 수 있다

**에이전트 점수(Annotations) 확인**

`save_to_file()` 호출 후 약 3초 뒤, 스팬 상세 패널의 "Annotations" 섹션에서 accuracy, completion, success 점수를 확인할 수 있다.

```
Tracing 탭
  └─ 스팬 클릭
       └─ 우측 상세 패널 → "Annotations" 섹션
            ├─ accuracy:   0.85 (pass)
            ├─ completion: 0.90 (pass)
            └─ success:    1.0  (pass)
```

> 📋 **QA 관리자 TIP**: Tracing 탭에서 `ae.accuracy_score < 0.5`로 필터링하면 실패 케이스만 추출된다. 이 케이스들을 검토해 프롬프트 개선 우선순위를 정하면 된다.

---

### Evaluators 탭 — LLM Judge 결과와 평가 템플릿

Evaluators 탭에는 두 가지 역할이 있다.

**역할 1 — Phoenix 자체 LLM Evaluator 템플릿 설정**

Phoenix에 내장된 LLM Judge 기능이다. "이 응답이 질문과 관련 있나요?" 같은 평가 기준을 등록하면 Phoenix가 새 스팬마다 LLM으로 점수를 자동으로 매긴다.

1. `http://localhost:6006` → 왼쪽 "Evaluators" 탭 클릭
2. "+ New Evaluator" 버튼 클릭
3. 평가 기준 선택 (Hallucination, Q&A Correctness 등)
4. LLM 모델 연결 (OpenAI API 키 필요)
5. 트레이스 데이터에 자동 적용

**역할 2 — 과거 트레이스 재평가**

기존에 수집된 트레이스를 새로운 평가 기준으로 일괄 재평가할 수 있다. 지난주 수집된 데이터를 더 엄격한 기준으로 다시 채점하는 것이 가능하다.

Agent-Evaluator의 LLMJudge와 함께 사용하면 시너지가 생긴다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — QuickEval 평가
from agent_evaluator import QuickEval, setup_otel

setup_otel(endpoint="http://localhost:6006", service_name="llm-judge-demo")

eval = QuickEval.for_llm_judge(
    "results/",
    model="claude-sonnet-4-6"
)

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

---

### Datasets & Experiments 탭 — 골든 데이터셋 버전 관리

Datasets & Experiments 탭에서는 골든 데이터셋을 Phoenix에서 직접 관리한다. `GoldenSetBuilder`로 추출한 케이스를 이 탭에 업로드하면 버전 관리가 가능해진다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — GoldenSetBuilder 골든셋
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",
    output_dir="data/golden_datasets/",
)

# 프로덕션 결과에서 고품질 케이스 추출
candidates = builder.extract(
    strategies=["high_value", "failure_cases"],
    max_cases=100,
)
approved = [c for c in candidates if c.get("accuracy_score", 0) >= 0.8]

# Phoenix Datasets 탭에 업로드 (1-call 래퍼)
builder.push_to_phoenix(
    cases=approved,
    dataset_name="golden_v2_2026_04"
)
```

- `GoldenSetBuilder.extract()`는 `high_value`(높은 정확도)와 `failure_cases`(실패 케이스) 전략으로 회귀 테스트에 가치 있는 케이스를 자동으로 선별한다
- `accuracy_score >= 0.8` 필터로 낮은 품질 케이스를 제외해 골든 데이터셋의 신뢰도를 유지한다
- `push_to_phoenix()`로 업로드된 데이터셋은 Phoenix Datasets 탭에서 버전 관리되며 과거 버전과 비교할 수 있다

Phoenix Datasets 탭에서 볼 수 있는 정보:
- 데이터셋 이름 및 버전 (`dataset.version`)
- 레코드 수 (`dataset.record_count`)
- 각 레코드의 input/output/ground_truth
- 과거 버전과의 비교(diff)

---

### Prompts 탭 — 실패 케이스 프롬프트 재현

Prompts 탭은 프롬프트 템플릿을 관리하고 Playground에서 재현할 수 있는 도구다.

**Playground 활용 워크플로우**

1. Tracing 탭에서 낮은 점수를 받은 스팬 선택
2. "Open in Playground" 클릭
3. 프롬프트 수정 후 재실행
4. 원본 응답과 비교

`llm.prompts` 속성을 스팬에 포함하면 Playground에서 해당 스팬을 재현할 수 있다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — PerformanceMonitor 설정
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval, EvalMetadata

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = call_llm(question)
    # llm.prompts 속성 추가 → Playground 재현 가능
    return response, EvalMetadata(
        extra={
            "llm.prompts": [
                {"role": "user",      "content": question},
                {"role": "assistant", "content": response}
            ]
        }
    )
```

- `EvalMetadata(extra={"llm.prompts": [...]})` 형식으로 프롬프트를 포함하면 Phoenix Prompts 탭의 Playground에서 해당 스팬을 재실행할 수 있다
- `role`/`content` 구조는 OpenAI 채팅 메시지 형식과 동일하므로 기존 프롬프트 코드를 그대로 활용할 수 있다
- 낮은 점수를 받은 스팬을 Playground에서 열어 프롬프트를 수정·재실행하면 수정 전후 응답을 나란히 비교할 수 있다

프롬프트 버전 관리가 필요한 경우, Phoenix REST API로 직접 등록할 수 있다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — 예제 코드
import requests

response = requests.post("http://localhost:6006/v1/prompts", json={
    "name": "qa-system-prompt-v2",
    "version": "v2.0",
    "template": "당신은 정확하고 간결한 답변을 제공하는 전문 AI입니다.\n질문: {question}\n답변:",
    "tags": ["production", "qa"],
})
```

---

## 19.5 25개 스팬 속성 (ae.*) 활용법

Agent-Evaluator는 `record_task()` 호출마다 다음 속성들을 스팬에 자동으로 포함한다.

| 속성명 | 타입 | 설명 |
|--------|------|------|
| `ae.task_id` | str | 태스크 고유 ID |
| `ae.task_type` | str | qa / tool_use / information_retrieval 등 |
| `ae.framework` | str | langchain / openai / anthropic 등 |
| `ae.completion_score` | float | 완료율 (0.0 ~ 1.0) |
| `ae.accuracy_score` | float | 정확도 (0.0 ~ 1.0) |
| `ae.execution_time` | float | 응답 시간 (초) |
| `ae.tokens_used` | int | 총 토큰 수 |
| `ae.tool_calls_count` | int | 도구 호출 횟수 |
| `ae.tool_names` | str | 도구 이름 JSON 배열 |
| `ae.hallucination_detected` | bool | 환각 탐지 여부 |
| `ae.security_threat_detected` | bool | 보안 위협 탐지 여부 |
| `ae.anomaly_detection_enabled` | bool | 이상 탐지 활성화 여부 |
| `ae.attempts` | int | 시도 횟수 (재시도 포함) |
| `input.value` | str | 입력 텍스트 (질문) |
| `output.value` | str | 출력 텍스트 (응답) |
| `openinference.span.kind` | str | AGENT / LLM / TOOL / CHAIN / RETRIEVER |
| `llm.prompts` | str | 프롬프트 JSON 배열 (Playground 연동) |
| `dataset.id` | str | 연동된 데이터셋 ID |
| `dataset.version` | str | 데이터셋 버전 |
| `dataset.record_count` | int | 데이터셋 레코드 수 |
| `session.id` | str | 모니터 인스턴스별 UUID |
| `llm.token_count.prompt` | int | 프롬프트 토큰 수 |
| `llm.token_count.completion` | int | 컴플리션 토큰 수 |
| `llm.token_count.total` | int | 총 토큰 수 |
| `llm.model_name` | str | 사용된 모델 이름 |

### TaskType별 span.kind 매핑

| TaskType | span kind |
|----------|-----------|
| `qa`, `code_generation`, `creative` | `LLM` |
| `information_retrieval` | `RETRIEVER` |
| `tool_use` | `TOOL` |
| `planning` | `AGENT` |
| `data_analysis`, `reasoning` | `CHAIN` |

---

## 19.6 외부 모니터링 도구 연동 개요

### Grafana 연동

Phoenix의 OTLP 데이터를 Grafana에서 시각화하려면, Grafana의 Tempo(추적)와 Prometheus(메트릭) 데이터소스를 구성해야 한다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — OpenTelemetry 설정
# Grafana Tempo로 스팬 전송
setup_otel(
    endpoint="http://grafana-tempo:4318",  # Tempo OTLP HTTP 포트
    service_name="my-agent",
    enable_metrics=True  # Prometheus로 메트릭도 전송
)
```

- `endpoint`를 Grafana Tempo의 OTLP HTTP 포트(4318)로 변경하는 것만으로 Phoenix 대신 Grafana로 스팬을 전송할 수 있다
- `enable_metrics=True`를 설정하면 Prometheus 형식 메트릭도 함께 익스포트되어 Grafana 대시보드에서 시각화 가능하다

```yaml
# docker-compose.yml — Grafana + Tempo + Prometheus 스택
services:
  tempo:
    image: grafana/tempo:latest
    ports:
      - "4318:4318"  # OTLP HTTP
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
```

- Tempo는 트레이스(스팬) 저장소, Grafana는 시각화 레이어로 역할이 분리된다
- 기업 내부에 이미 Grafana 스택이 있다면 Phoenix 없이 바로 이 구성으로 연동할 수 있다

### Datadog 연동

Datadog은 OTLP 엔드포인트를 지원하므로, `setup_otel()`의 endpoint만 변경하면 된다.

```python
setup_otel(
    endpoint="http://datadog-agent:4318",  # Datadog Agent OTLP 포트
    service_name="my-agent",
)
```

- Datadog Agent가 OTLP 수신을 활성화하면 `setup_otel()`의 endpoint만 변경하는 것으로 스팬이 Datadog APM으로 전송된다
- `service_name`이 Datadog 서비스 카탈로그의 서비스명으로 등록되므로 일관된 이름을 사용해야 한다

```yaml
# datadog.yaml
otlp_config:
  receiver:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"
```

- `otlp_config.receiver.protocols.http`를 활성화해야 OTLP/HTTP 형식 스팬을 수신할 수 있다
- 기업 환경에서 이미 Datadog을 사용 중이라면 Phoenix 없이 바로 이 설정으로 에이전트 트레이스를 통합할 수 있다

### 기업 내부 Jaeger/Zipkin 연동

Jaeger나 Zipkin도 OTLP를 지원한다. 엔드포인트만 변경하면 된다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — OpenTelemetry 설정
# Jaeger
setup_otel(
    endpoint="http://jaeger:4318",
    service_name="my-agent",
)

# Zipkin은 별도 exporter 필요 (opentelemetry-exporter-zipkin 패키지)
```

> ⚙️ **DevOps TIP**: 외부 OTEL 도구로 전환할 때, Phoenix 로컬 환경에서 먼저 스팬 구조가 올바른지 검증한 다음 프로덕션 도구로 전환하라. 스팬 속성이 제대로 전송되는지 확인하는 것이 우선이다.

---

## [이 챕터의 핵심]

- **OTEL = Gate G(Observability)의 프로덕션 구현체.** 오프라인 평가로 측정한 `ExplainabilityConfig`·`LatencyAttributionConfig`·`ObservabilityConfig` 지표를, OTEL 스팬을 통해 배포 후에도 실시간으로 추적한다. **측정 → 감지 → 대응** 루프가 완성된다.

- **OpenTelemetry는 에이전트 평가와 자연스럽게 결합된다.** `record_task()` 1회 = 1개 스팬이며, 25개 평가 지표가 스팬 속성으로 자동 변환되어 Phoenix로 전송된다.

- **`setup_otel()` 순서가 전부다.** 반드시 `PerformanceMonitor` 또는 `QuickEval` 생성 전에 호출해야 한다. endpoint는 `"http://localhost:6006"` — `/v1/traces` 경로를 붙이지 않는다.

- **2-터미널 패턴으로 시작하라.** 터미널 A에서 `agent-eval monitor`(기본 포트 6006)로 Phoenix 기동, 터미널 B에서 에이전트 실행. `http://localhost:6006` Tracing 탭에서 수 초 내 스팬 확인 가능. `agent-eval monitor --check`으로 OTEL 패키지와 포트 상태를 사전 확인한다.

- **Phoenix 4개 탭의 역할**: Tracing(실행 기록 + 필터), Evaluators(LLM Judge 설정), Datasets & Experiments(골든셋 관리), Prompts(프롬프트 재현 + Playground).

- **Tracing 탭 필터**로 실패 케이스를 빠르게 추출하라. `ae.accuracy_score < 0.5`, `ae.hallucination_detected == "true"`, `ae.framework == "langchain"` 같은 필터 표현식을 활용한다.

- **arize-phoenix 버전**: `>=7.0.0,<15.0.0`. `opentelemetry-sdk>=1.20.0` 및 `opentelemetry-exporter-otlp-proto-http>=1.20.0`이 기본 설치에 포함된다. `agent-eval monitor --check`으로 설치 여부를 즉시 확인할 수 있다.

---

## 실전 예제

`ch19_phoenix.py`는 `setup_otel()` → `PerformanceMonitor` 순서, Phoenix 프로젝트 분리, DeepEval·Ragas 어댑터 통합까지 Phoenix OTEL 연동의 전체 흐름을 한 파일에서 보여준다. API 키 없이 mock 모드로 실행하면 `setup_otel()` 없이 평가 결과만 확인할 수 있다.

**기본 예제**: `Evaluator_Examples/ch19_phoenix.py`

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — Phoenix 실행 여부 확인 + OTEL 설정
import socket
from agent_evaluator import setup_otel, PerformanceMonitor

_PHOENIX_URL = "http://localhost:6006"  # /v1/traces 경로는 SDK가 자동 추가

def _phoenix_running() -> bool:
    """Phoenix 서버가 실행 중인지 포트 확인"""
    try:
        with socket.create_connection(("localhost", 6006), timeout=2):
            return True
    except OSError:
        return False

# Phoenix가 실행 중일 때만 OTEL 설정 — PerformanceMonitor 생성 전에 호출
if _phoenix_running():
    setup_otel(
        endpoint=_PHOENIX_URL,          # base URL만 전달 — /v1/traces는 자동 추가
        service_name="my-agent-service",
        enable_metrics=False,           # Phoenix는 /v1/metrics 미지원
    )
    print("Phoenix OTEL 연결 완료")
else:
    print("Phoenix 미실행 — OTEL 없이 계속")

# setup_otel() 이후에 monitor 생성해야 OTLP 스팬이 자동 발행됨
monitor = PerformanceMonitor(output_dir="results/")
```

- `setup_otel()`은 반드시 `PerformanceMonitor()` 생성 **이전**에 호출해야 한다 — 순서가 바뀌면 스팬이 Phoenix로 전송되지 않는다
- `_phoenix_running()`으로 서버 실행 여부를 확인해 Phoenix 없는 환경에서도 코드가 정상 동작하게 한다
- `agent-eval monitor` CLI를 실행하면 Phoenix 서버 기동과 OTLP 수신 설정이 자동으로 완료된다

```python
# 출처: Evaluator_Examples/ch19_phoenix.py, 섹션 1 — Tracing·Playground 스팬 전송
from agent_evaluator.decorators import agent_eval, EvalMetadata

@agent_eval(
    monitor,
    task_type="information_retrieval",
    question_arg="question",
    ground_truth_arg="ground_truth",
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> tuple:
    # RAG 에이전트 실행
    response = f"{question}에 대한 답변 (컨텍스트 기반)"
    
    return response, EvalMetadata(
        extra={
            # Phoenix Playground 탭에서 프롬프트 확인 가능
            "llm.prompts": [
                f"시스템: 당신은 QA 에이전트입니다.\n사용자: {question}\n컨텍스트: {context}"
            ],
            # Phoenix Datasets 탭 연동
            "dataset.id": "rag_golden_v1",
            "dataset.record_count": 100,
        }
    )

rag_agent("양자 컴퓨터란?", context="양자 컴퓨터는...", ground_truth="양자역학 원리 활용 컴퓨터")
# → Phoenix Tracing 탭에서 스팬 확인 가능
# → Playground 탭에서 프롬프트 재실행 가능
```

- `EvalMetadata(extra={"llm.prompts": [...]})` 속성을 추가하면 Phoenix의 Playground 탭에서 실제 프롬프트를 조회하고 재실행할 수 있다
- `"dataset.id"` 속성으로 Phoenix Datasets 탭에 평가 데이터를 연결할 수 있다
- 모든 `record_task()` 호출은 OTLP 스팬으로 자동 변환되어 Phoenix Tracing 탭에 표시된다

```bash
# 터미널 A: Phoenix 서버 기동
agent-eval monitor

# 터미널 B: 예제 실행 (ANTHROPIC_API_KEY 있으면 자동으로 Phoenix 연결)
python Evaluator_Examples/ch19_phoenix.py

# Phoenix UI 확인
open http://localhost:6006
```

- 터미널 A의 `agent-eval monitor`를 먼저 실행한 뒤 터미널 B에서 에이전트를 실행해야 스팬이 Phoenix에 전달된다
- `ANTHROPIC_API_KEY`가 없으면 mock 모드로 실행되어 Phoenix 연결 없이도 평가 결과를 로컬에서 확인할 수 있다
- 실행 후 `http://localhost:6006` Tracing 탭에서 스팬이 수신됐는지 즉시 확인할 수 있다

**예제 구성**

| 섹션 | 내용 | Phoenix UI 탭 |
|------|------|---------------|
| 섹션 1 | `setup_otel()` 설정 + `PerformanceMonitor` / `HybridPerformanceMonitor` 초기화 | — (설정) |
| 섹션 2 | Tracing — OTLP 스팬 발행 + Playground `llm.prompts` | Tracing 탭 |
| 섹션 3 | Datasets — `GoldenSetBuilder.push_to_phoenix()` | Datasets 탭 |
| 섹션 4 | Prompts — REST API 등록 | Prompts 탭 |
| 섹션 5 | GraphQL — 프로젝트·스팬·데이터셋 조회 | — |
| 섹션 추가 | `DeepEvalAdapter` + `RagasAdapter` 직접 사용 — `HybridPerformanceMonitor` 없이 단건 평가 | — |

**실행 결과 (v0.9.1 기준, mock 모드)**

```
=== ch19. Phoenix OTEL 예제 ===
[mock 모드] ANTHROPIC_API_KEY 미설정 — Phoenix 연결 없이 실행
setup_otel: 비활성 (API 키 필요)

섹션 2: 기본 평가 (3개 태스크)
  TCR=66.7% | avg_accuracy=0.723

섹션 3: DeepEval 어댑터
  [mock] deepeval 미설치 — advanced_metrics 데모 패치 적용
  advanced_metrics: {"deepeval_score": 0.85, "answer_relevancy": 0.91}

섹션 4: Ragas 어댑터
  [mock] ragas 미설치 — rag_metrics 데모 패치 적용
  rag_metrics: {"faithfulness": 0.89, "context_precision": 0.76}

대시보드 외부 평가 탭: advanced_metrics 3건 표시
```

> **`setup_otel()` 순서 엄수**: `setup_otel(endpoint="http://localhost:6006")`은 반드시 `PerformanceMonitor(...)` 또는 `QuickEval(...)` 생성 전에 호출해야 한다. 순서를 틀리면 스팬이 Phoenix에 전송되지 않는다. `ch19_phoenix.py` 섹션 1의 코드 순서를 템플릿으로 사용한다.

**DeepEvalAdapter + RagasAdapter 직접 사용**

`HybridPerformanceMonitor`가 내부에서 관리하는 두 어댑터를 직접 인스턴스화하면, `record_task()` 루프 없이 단건 평가를 즉시 실행할 수 있다. 커스텀 파이프라인이나 테스트 환경에 적합하다.

> **사전 조건**: `pip install "agent-evaluator[eval]"` + `OPENAI_API_KEY`

**EvaluationContext — 어댑터 공통 입력 데이터클래스:**

두 어댑터는 모두 `EvaluationContext` 인스턴스를 입력으로 받는다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `input_text` | str | ✅ | 사용자 질문 또는 프롬프트 |
| `output_text` | str | ✅ | 에이전트 응답 |
| `expected_output` | str | — | 정답 또는 기대 응답 (ContextRecall 등에 사용) |
| `retrieved_context` | list[str] | — | RAG 검색 문서 목록 — RagasAdapter 실행 필수 |
| `quality_criteria` | str | — | G-Eval 평가 기준 설명 (DeepEvalAdapter의 G-Eval에 사용) |
| `task_type` | str | — | `"qa"` / `"information_retrieval"` 등 태스크 유형 |
| `metadata` | dict | — | 임의 추가 정보 |

```python
# 출처: Evaluator_Examples/ch19_phoenix.py, 섹션 추가 — 어댑터 직접 사용
from agent_evaluator.integrations.metric_adapters import (
    DeepEvalAdapter, RagasAdapter, EvaluationContext,
)

# ── DeepEvalAdapter — G-Eval·Hallucination·Toxicity·Bias·AnswerRelevancy ──
deepeval_adapter = DeepEvalAdapter(model="gpt-4o-mini", threshold=0.5)
if deepeval_adapter.is_available():
    ctx = EvaluationContext(
        input_text="서울의 인구는 얼마인가요?",
        output_text="서울의 인구는 약 950만 명으로, 대한민국 최대 도시입니다.",
        expected_output="약 950만 명",
        task_type="qa",
        quality_criteria="factual accuracy",   # G-Eval 기준
    )
    result = deepeval_adapter.evaluate(ctx)
    # result["g_eval_score"]        → 0.0~1.0  (커스텀 기준 종합)
    # result["hallucination_score"] → 0.0~1.0  (retrieved_context 전달 시 활성)
    # result["toxicity_score"]      → 0.0~1.0  (독성 탐지)
    # result["bias_score"]          → 0.0~1.0  (편향 탐지)

# ── RagasAdapter — Faithfulness·ContextPrecision·AnswerRelevancy·ContextRecall ──
ragas_adapter = RagasAdapter(llm_model="gpt-4o-mini")
if ragas_adapter.is_available():
    ctx_rag = EvaluationContext(
        input_text="아인슈타인의 출생 연도는?",
        output_text="알베르트 아인슈타인은 1879년에 태어났습니다.",
        expected_output="1879년",
        retrieved_context=[                     # RAG 컨텍스트 — 필수
            "알베르트 아인슈타인은 1879년 3월 14일 독일 울름에서 태어났습니다.",
            "아인슈타인은 특수상대성이론과 일반상대성이론을 발표했습니다.",
        ],
        task_type="information_retrieval",
    )
    result = ragas_adapter.evaluate(ctx_rag)
    # result["ragas_faithfulness"]      → 0.0~1.0  (응답이 컨텍스트에 근거하는 정도)
    # result["ragas_context_precision"] → 0.0~1.0  (검색된 컨텍스트의 정확도)
    # result["ragas_answer_relevancy"]  → 0.0~1.0  (OpenAI 임베딩 있을 때만 활성)
    # result["ragas_context_recall"]    → 0.0~1.0  (expected_output 있을 때만 활성)
```

**직접 사용 vs `HybridPerformanceMonitor` 비교**

| 항목 | 어댑터 직접 사용 | `HybridPerformanceMonitor` |
|------|----------------|---------------------------|
| 설정 | `DeepEvalAdapter()` / `RagasAdapter()` 인스턴스화 | `use_deepeval=True, use_ragas=True` 플래그 |
| 평가 단위 | 단건 `evaluate(EvaluationContext(...))` | `record_task()` 호출마다 자동 채점 |
| 결과 경로 | 반환 dict에서 직접 접근 | `report["advanced_metrics_summary"]` |
| Phoenix 연동 | 직접 스팬 속성 추가 필요 | `record_task()` 호출 시 자동 OTEL 스팬 |
| 적합 상황 | 커스텀 파이프라인·단위 테스트 | 대량 평가·대시보드 통합·프로덕션 |

- `RagasAdapter.evaluate()`는 `retrieved_context`가 없으면 빈 dict(`{}`)를 반환한다 — RAG 태스크에만 적용된다
- `DeepEvalAdapter`는 `is_available()`이 `False`이면 `None`을 반환한다 (`{}` 빈 결과와 구별)
- 어댑터 직접 사용 시 `[eval]` extra가 반드시 설치되어 있어야 한다: `pip install "agent-evaluator[eval]"`

**CI/CD 검증 스크립트의 Phoenix 연동 패턴**

`ch18_cicd_gate.py`는 Phoenix 포트를 소켓으로 확인한 뒤 조건부로 OTEL을 활성화한다. Phoenix가 없는 CI 환경에서도 Gate 판정은 정상 동작하며, Phoenix가 있으면 스팬이 자동 전송된다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — Phoenix 조건부 연결 + CI/CD Gate 판정
import socket, sys
from agent_evaluator import PerformanceMonitor, setup_otel

# Phoenix 포트 확인 — CI 환경에서는 보통 미실행 (스킵해도 Gate 판정은 정상)
try:
    with socket.socket() as _s:
        _s.settimeout(0.5)
        if _s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="harness-validation")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass   # Phoenix 없으면 OTEL 없이 계속 — Gate 판정에는 영향 없음

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,
    enable_transparency=True,   # Phoenix 연결 시 투명성 Traces 자동 전송
)

# ... 에이전트 등록 및 실행 ...

# Gate 판정 — Phoenix 연결 여부와 무관하게 동작
report_dict = monitor.generate_report().to_dict()
harness = report_dict.get("extra_metrics", {}).get("harness_groups", {})
gate = (harness.get("overall", {}).get("gate") or "unknown").upper()

if gate == "FAIL":
    print("❌ Harness Gate FAIL — exit 1")
    sys.exit(1)
print("✅ Harness Gate PASS — exit 0")
sys.exit(0)
# → Phoenix 없어도 Gate 판정 정상 / Phoenix 있으면 모든 스팬이 대시보드에 기록됨
```

```bash
# 2-터미널 패턴: Phoenix + CI/CD 검증 동시 운영
# 터미널 1: agent-eval monitor          # Phoenix 서버 기동
# 터미널 2: python Evaluator_Examples/ch18_cicd_gate.py  # OTEL 자동 활성화
python Evaluator_Examples/ch18_cicd_gate.py           # Phoenix 없이도 동작
python Evaluator_Examples/ch18_cicd_gate.py --strict  # WARN도 차단
```

- Phoenix 없는 환경(CI 서버)에서도 Gate 판정은 정상 동작하므로 OTEL 연결 여부와 무관하게 CI/CD 파이프라인에 적용할 수 있다
- `--strict` 옵션을 추가하면 WARN 상태 Gate도 FAIL로 처리해 프로덕션 배포 전 강화 검증에 활용할 수 있다
- 로컬 개발 시 터미널 1에서 Phoenix를 기동하면 Gate 판정 결과가 Phoenix Tracing 탭에도 실시간으로 기록된다
