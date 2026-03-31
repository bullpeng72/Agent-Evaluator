# AI Agent 평가 프레임워크 비교 분석

**Version**: 0.6.7
**Last Updated**: 2026-03-31
**기준 버전**: 각 프레임워크 2025–2026년 최신 릴리스 기준
**분석 목적**: 개발자가 서비스 코드 외에 작성해야 하는 코드량 / 자동화 수준 비교

---

## 대상 프레임워크

| 프레임워크 | 유형 | 최신 버전 (2025–2026) | 주력 기능 |
|-----------|------|----------------------|---------|
| **LangSmith** | SaaS + 셀프호스트 | SDK ≥0.4.25 / Self-Hosted v0.12 (2025.10) | LangChain 생태계 관측 |
| **Ragas** | OSS 라이브러리 | v0.4.3 (2026.01) | RAG + 에이전트 평가 |
| **DeepEval** | OSS + SaaS (Confident AI) | v3.8.9 (2026.03) | LLM 단위 테스트 |
| **Arize Phoenix** | OSS + Cloud | v8.x+ (2025.11) | LLM 관측가능성 (OTEL 기반) |
| **Evidently AI** | OSS + Cloud | v0.7.17+ (2025) | ML/LLM 모니터링 |
| **Braintrust** | SaaS + OSS SDK | v0.5.2 (2025) | LLM 실험 + 에이전트 관측 |
| **Helicone** | SaaS + OSS | 시맨틱 버전 없음 (활발 유지) | LLM 프록시 + 비용 관측 |
| **W&B Weave** | SaaS + OSS SDK | v0.72+ (2025) | 에이전트 평가 + 실험 관리 |
| **Agent Evaluator** | OSS SDK | v0.6.7 (2026.04) | Agentic AI 전문 평가 |

---

## 1. OpenTelemetry (OTEL) 지원 현황

### OTEL 지원 수준 비교

| 프레임워크 | OTEL 지원 | 역할 | 비고 |
|-----------|----------|------|------|
| **LangSmith** | ✅ 완전 네이티브 | Exporter + Collector | `langsmith>=0.4.25`에서 GA. OTLP 포맷 수신 |
| **Ragas** | ⚠️ 간접 지원 | 없음 (메트릭 계산 라이브러리) | Phoenix/Langfuse 등 OTEL 플랫폼과 연동 |
| **DeepEval** | ✅ 완전 지원 | OTLP 엔드포인트 | `https://otel.confident-ai.com`로 스팬 전송 |
| **Arize Phoenix** | ✅ 핵심 아키텍처 | Collector + UI | OpenInference = OTEL 시맨틱 컨벤션 확장 |
| **Evidently AI** | ✅ Tracely 통해 지원 | Tracely가 OTEL 기반 | 별도 `tracely` 패키지 필요 |
| **Braintrust** | ✅ 호환 모드 | OTLP 수신 | `BRAINTRUST_OTEL_COMPAT=true` 환경변수 설정 |
| **Helicone** | ⚠️ 부분 지원 | Consumer (OpenLLMetry 경유) | 프록시가 주력; OTEL은 보조 경로 |
| **W&B Weave** | ✅ 완전 인제스트 | Collector | 언어 무관 OTLP 데이터 직접 수신 |
| **Agent Evaluator** | ❌ 미지원 | 해당 없음 | 알고리즘 기반 SDK — OTEL 트레이서 아님 |

### OTEL 통합 코드 예시

**LangSmith (OTEL 네이티브)**
```python
# langsmith>=0.4.25 — OTLP 직접 export
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from langsmith.otel import LangSmithOTLPSpanExporter

exporter = LangSmithOTLPSpanExporter(api_key="ls-...")
# 기존 TracerProvider에 plugging만 하면 LangSmith가 수신
```

**Arize Phoenix (OTEL 기반 설계)**
```python
from phoenix.otel import register

tracer_provider = register(
    auto_instrument=True,   # 설치된 OpenInference 패키지 전체 자동 계측
    batch=True,
    project_name="my-agent",
    endpoint="http://localhost:6006/v1/traces",  # 로컬 Phoenix 서버
)
# → LangChain, CrewAI, OpenAI, LlamaIndex, DSPy 등 자동 추적 시작
```

**Braintrust (OTEL 호환 모드)**
```python
import os
os.environ["BRAINTRUST_OTEL_COMPAT"] = "true"
os.environ["BRAINTRUST_API_KEY"] = "bt-..."
# 기존 OpenTelemetry TracerProvider 그대로 사용 — 스팬이 Braintrust로 전송됨
```

**Evidently (Tracely)**
```python
from tracely import init_tracing, trace_event

init_tracing(
    address="https://app.evidently.cloud",
    api_key="YOUR_KEY",
    project_id="YOUR_PROJECT_ID",
)

@trace_event()                  # OTEL span으로 감싸짐
def my_agent_call(question: str) -> str:
    return agent.run(question)
```

---

## 2. 실시간 데이터 수집 (Real-Time Collection)

| 프레임워크 | 실시간 지원 | 방식 | 제한 사항 |
|-----------|-----------|------|---------|
| **LangSmith** | ✅ | Pending runs — 에이전트 실행 중 UI 반영 | SaaS 전송 필요 |
| **Ragas** | ❌ | 배치/오프라인 전용 | 실행 후 데이터셋 구성 → 평가 |
| **DeepEval** | ✅ | Confident AI Cloud 스트리밍 | 로컬 실행은 배치 |
| **Arize Phoenix** | ✅ | OTEL span 수신 즉시 UI 반영 | 로컬 서버(`px.launch_app()`) |
| **Evidently AI** | ✅ | Tracely → Evidently Cloud 스트리밍 | Cloud 계정 필요 |
| **Braintrust** | ✅ | 온라인 스코어러 — 프로덕션 트레이스 자동 채점 | SaaS 전송 필요 |
| **Helicone** | ✅ | 프록시 경유 즉시 로깅 | LLM 호출만 (에이전트 로직 별도) |
| **W&B Weave** | ✅ | Online Evaluations — 라이브 트레이스 자동 채점 | SaaS 전송 필요 |
| **Agent Evaluator** | ❌ | `--watch` 파일 감시 (저장 후 반영) | 실행 중 스트리밍 없음 |

---

## 3. 데이터 수집 방법 상세

### 3.1 LangSmith

| 방법 | 코드량 | 대상 |
|------|--------|------|
| 환경변수 (`LANGCHAIN_TRACING_V2=true`) | 2줄 | LangChain/LangGraph 사용 앱 |
| `@traceable` 데코레이터 | 함수당 1줄 | 임의 Python 함수 |
| OTLP exporter | ~10줄 | 기존 OTEL 파이프라인 연결 |
| LangSmith Fetch CLI | 설정 없음 | IDE/터미널에서 트레이스 조회 |

```python
# LangChain 사용 시 — 환경변수만으로 완료
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "ls-..."

# 일반 Python 함수
from langsmith import traceable

@traceable
def my_agent_step(query: str) -> str:
    return llm.invoke(query)
```

### 3.2 Ragas

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `SingleTurnSample` / `MultiTurnSample` 직접 구성 | 많음 | 모든 케이스 (수동) |
| `ragas evaluate` CLI | 중간 | 파이프라인 배치 평가 |
| LangChain/LlamaIndex 어댑터 | 적음 | 해당 프레임워크 사용 시 |

```python
from ragas.dataset_schema import SingleTurnSample, MultiTurnSample
from ragas.messages import HumanMessage, AIMessage, ToolCall, ToolMessage

# 에이전트 평가 — 개발자가 모든 데이터를 직접 구성해야 함
sample = MultiTurnSample(
    user_input=[
        HumanMessage(content="가장 가까운 약국 찾아줘"),
        AIMessage(content="검색 도구를 사용합니다", tool_calls=[
            ToolCall(name="search_places", args={"query": "pharmacy nearby"})
        ]),
        ToolMessage(content='[{"name":"CVS","distance":"0.3km"}]'),
        AIMessage(content="0.3km 거리의 CVS 약국이 있습니다."),
    ],
    reference_tool_calls=[ToolCall(name="search_places", args={"query": "pharmacy"})],
    reference="가장 가까운 약국 위치를 정확히 안내했는지 확인",
)
```

### 3.3 DeepEval

| 방법 | 코드량 | 대상 |
|------|--------|------|
| OTLP 엔드포인트 (`otel.confident-ai.com`) | ~5줄 | 기존 OTEL 파이프라인 |
| `instrument_crewai()` / `instrument_langchain()` | 1줄 | 지원 프레임워크 |
| `@deepeval.trace` 데코레이터 | 함수당 1줄 | 임의 Python 함수 |
| pytest 통합 (`deepeval test run`) | 설정 없음 | CI/CD 배치 평가 |

```python
# CrewAI 자동 계측 — 1줄로 완료
from deepeval.integrations import instrument_crewai
instrument_crewai()

# 또는 직접 테스트
from deepeval import evaluate
from deepeval.metrics import TaskCompletionMetric
from deepeval.test_case import LLMTestCase

test_case = LLMTestCase(
    input="약 처방전 정보 추출해줘",
    actual_output=agent_output,
    tools_called=[{"name": "extract_text", "output": "..."}],
)
evaluate([test_case], [TaskCompletionMetric(threshold=0.7)])
```

### 3.4 Arize Phoenix

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `register(auto_instrument=True)` | 5줄 | 지원 프레임워크 전체 자동 |
| 개별 `openinference-instrumentation-*` 패키지 | 2줄/패키지 | 선택적 계측 |
| 표준 OTEL span | ~10줄 | 커스텀 로직 |

```python
import phoenix as px
from phoenix.otel import register

px.launch_app()  # 로컬 Phoenix 서버 시작 (포트 6006)

register(
    auto_instrument=True,  # LangChain, OpenAI, CrewAI, DSPy 등 자동 패칭
    project_name="my-agent",
)
# → 이것으로 수집 완료. 이후 코드 변경 불필요
```

지원 프레임워크 (2025 기준):
`openai`, `langchain`, `crewai`, `llamaindex`, `dspy`, `haystack`, `mistralai`,
`anthropic`, `bedrock`, `vertexai`, `groq`, `smolagents`, `mastra`, `vercel-ai-sdk`

### 3.5 Evidently AI

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `init_tracing()` + `@trace_event` | ~10줄 | 라이브 서비스 |
| `create_trace_event()` 컨텍스트 매니저 | ~5줄/블록 | 세밀한 span 제어 |
| pandas DataFrame 배치 평가 | 많음 | 오프라인 배치 |

```python
from tracely import init_tracing, trace_event

init_tracing(
    address="http://localhost:8080",  # 셀프호스트 Evidently 서버
    api_key="YOUR_KEY",
    project_id="proj-uuid",
)

@trace_event(span_name="agent_run")
def run_agent(query: str) -> str:
    return my_agent.invoke(query)
```

### 3.6 Braintrust

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `braintrust.auto_instrument()` | 1줄 | Python 전체 자동 (v0.5.2+) |
| `BraintrustSpanProcessor` | ~5줄 | 기존 OTEL TracerProvider 연결 |
| OTLP 호환 모드 | 환경변수 2개 | 언어 무관 |
| AI Proxy (URL 변경) | 1줄 | LLM 호출 레벨 |

```python
import braintrust
braintrust.auto_instrument()  # v0.5.2+ — 모든 것을 자동 추적

# 또는 세밀한 제어
with braintrust.start_span("agent-reasoning") as span:
    result = llm.generate(prompt)
    span.log(output=result, metadata={"step": "reasoning"})
```

지원 프레임워크: OpenAI Agents SDK, LangGraph, CrewAI, AutoGen, Google ADK,
Mastra, PydanticAI, DSPy, Instructor, Vercel AI SDK, Claude Agent SDK

### 3.7 Helicone

| 방법 | 코드량 | 대상 |
|------|--------|------|
| 프록시 (base_url 변경) | 1줄 | LLM 호출 전체 자동 |
| 세션 헤더 추가 | 3–5줄 | 멀티스텝 에이전트 그룹화 |
| OpenLLMetry 비동기 | ~10줄 | 프록시 외부 경로 |
| LiteLLM 콜백 | 1줄 | LiteLLM 사용 시 |

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://oai.helicone.ai/v1",   # 유일한 변경
    default_headers={
        "Helicone-Auth": "Bearer HELICONE_API_KEY",
        # 에이전트 세션 그룹화 (선택)
        "Helicone-Session-Id": "session-abc-123",
        "Helicone-Session-Path": "/agent/search/step1",
        "Helicone-Session-Name": "My Drug Search Agent",
    }
)
# → 모든 LLM 호출이 자동 로깅됨
```

### 3.8 W&B Weave

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `weave.init()` + `@weave.op()` | 초기화 1줄 + 함수당 1줄 | Python 함수 |
| OTEL 인제스트 | 환경변수 | 언어 무관 |
| MCP 자동 패칭 | 1줄 | FastMCP / ClientSession |
| 프레임워크 통합 | ~3줄 | OpenAI SDK, LangChain 등 |

```python
import weave
weave.init("my-agent-project")  # 프로젝트 초기화

@weave.op()                      # 모든 입출력/레이턴시/토큰 자동 기록
def search_and_synthesize(query: str) -> str:
    contexts = retriever.get(query)
    return llm.generate(query, contexts)

# MCP 서버 자동 추적
weave.init("mcp-project")
# FastMCP, ClientSession이 자동 패칭됨
```

### 3.9 Agent Evaluator

| 방법 | 코드량 | 대상 |
|------|--------|------|
| `TaskResult` 직접 구성 | ~10줄/태스크 | 모든 에이전트 |
| `create_taskresult()` 헬퍼 | ~5줄 | LLM 응답에서 자동 추출 |
| Framework factory | 1줄 | CrewAI, LangChain, LangGraph, AutoGen |
| `evaluation_session` 컨텍스트 매니저 | ~5줄 | 세션 단위 자동 저장 |

```python
from agent_evaluator import PerformanceMonitor, create_taskresult, create_evaluated_crew

# 방법 1: create_taskresult() 헬퍼 사용 (권장)
# TaskResult 필수 필드(11개)를 자동 계산해 생성
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,    # 보안 지표 활성화
    enable_hallucination_detection=True,
)
result = create_taskresult(
    task_id="task_001",
    question="가장 가까운 약국 찾아줘",
    response=agent_output,
    ground_truth="CVS 약국, 0.3km 거리",
    execution_time=1.23,
    task_type="qa",
)
monitor.record_task(result)  # 메서드 체이닝 가능: .record_task(t1).record_task(t2)

# Tool 선택 정확도 (ToolSelectionTracker 직접 호출)
monitor.tool_selection_tracker.evaluate_selection(
    task_id="task_001",
    expected_tools=["search"],
    actual_tools=["search"],  # 실제 에이전트가 호출한 도구 목록
)

# 방법 2: CrewAI factory (crew 객체 래핑 — 1줄 계측)
evaluator = create_evaluated_crew(my_crew, monitor=monitor)
```

---

## 4. 지표 구성 (Metric Configuration)

### 4.1 내장 지표 목록

| 프레임워크 | 범용 품질 지표 | Agentic 전용 지표 | 보안 지표 | LLM 없이 계산 가능 |
|-----------|-------------|-----------------|---------|-----------------|
| **LangSmith** | Correctness, Hallucination, Criteria | Multi-Turn Goal, Trajectory (2025) | 없음 | ❌ (LLM 판단자) |
| **Ragas** | Faithfulness, AnswerRelevancy, ContextPrecision/Recall | ToolCallAccuracy, ToolCallF1, AgentGoalAccuracy (2024+) | 없음 | ❌ |
| **DeepEval** | 14개+ (Hallucination, Bias, Toxicity 등) | TaskCompletion, ToolCorrectness, PlanQuality, AgentGoalSuccessRate (2025) | 일부 (Red-team) | 일부 (BLEU, ROUGE) |
| **Arize Phoenix** | Hallucination, QA Correctness, Toxicity, Relevance | FunctionCalling, PathConvergence, Planning (2025) | 없음 | ❌ |
| **Evidently AI** | 100개+ (텍스트 품질, 드리프트 등) | 없음 (일반 지표를 span에 적용) | 없음 | ✅ 대부분 |
| **Braintrust** | Levenshtein, Factuality, Moderation, Summary | Online scorers (커스텀) | 없음 | 일부 |
| **Helicone** | Cost, Latency, Error Rate, Throughput | Session tracing (인프라 수준) | 없음 | ✅ (계산 자체 없음) |
| **W&B Weave** | Online Scorers (커스텀 + LLM-judge) | MCP tracing, Multi-agent spans, A2A | Guardrails (2025) | 일부 |
| **Agent Evaluator** | TCR, Accuracy, Hallucination, Quality, Latency, Token | ToolSelection F1, ToolEfficiency, Retry, MultiAgent, Workflow | **5종 전용** (Sanitization, Leakage, Authorization, Privilege, ChainAttack) | ✅ **전부** |

### 4.2 Agentic AI 지표 세부 비교

| 지표 | LangSmith | Ragas | DeepEval | Phoenix | Evidently | Braintrust | Helicone | W&B | **Agent Evaluator** |
|-----|:---------:|:-----:|:--------:|:-------:|:---------:|:----------:|:--------:|:---:|:-------------------:|
| Tool 선택 정확도 (F1) | ❌ | ✅ ToolCallF1 | ✅ ToolCorrectness | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `ToolSelectionTracker` |
| Tool 효율성 / 불필요 호출 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `ToolCallAnalyzer` |
| 재시도 / 자기수정 패턴 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `RetryCorrectionTracker` |
| 멀티에이전트 협업 품질 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `AgentCoordinationTracker` |
| 워크플로우 퍼널 / 분기 | ✅ (LangGraph) | ❌ | ❌ | 부분 | ❌ | 부분 | ❌ | 부분 | ✅ `WorkflowExecutionTracker` |
| Agent 목표 달성 | ✅ Multi-Turn | ✅ AgentGoalAccuracy | ✅ TaskCompletion | ✅ Planning | ❌ | 커스텀 | ❌ | 커스텀 | ✅ TCR 기반 |
| 프롬프트 인젝션 탐지 | ❌ | ❌ | ⚠️ Red-team | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `InputSanitizationTracker` |
| 출력 정보 유출 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `OutputLeakageDetector` |
| 권한 상승 탐지 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `PrivilegeEscalationDetector` |
| Tool 체인 공격 탐지 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `ToolChainAttackDetector` |
| 허가되지 않은 Tool 사용 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ `ToolAuthorizationTracker` |

---

## 5. 지표 계산 방식 및 비용

### 5.1 LLM API 의존성

```
LangSmith    ❌ LLM 판단자 기반 (모든 품질 지표)
             → 평가 1,000건당 $2–10 추가 비용

Ragas        ❌ LLM 판단자가 기본 동작 방식
             → non_llm 서브셋(BLEU 등)은 LLM 불필요하나 매우 제한적
             → 평가 1,000건당 $5–20

DeepEval     ⚠️ 혼합
             → GEval, Hallucination, Faithfulness: LLM 필요
             → BLEU, ROUGE, Levenshtein: LLM 불필요
             → 평가 1,000건당 $3–15

Arize Phoenix ❌ Evaluator가 LLM 기반 (LiteLLM로 모델 선택 가능)
             → 평가 1,000건당 $3–10

Evidently AI  ✅ 대부분 통계/룰 기반
             → 텍스트 품질(감성, 독성): 사전훈련 모델 사용
             → LLM-as-judge는 선택적

Braintrust   ⚠️ Levenshtein/모듈러: 무료, Factuality: LLM 필요
             → 사용자가 스코어러 구현 방식 선택

Helicone     ✅ 비용/레이턴시/오류율만 — LLM 계산 없음

W&B Weave    ⚠️ Online Scorers: LLM 판단자 기반 (선택)
             → 커스텀 스코어러로 LLM 없이도 가능

Agent Evaluator ✅ 16개 네이티브 지표 전부 LLM 없이 계산
             → 알고리즘 기반: LCS, F1, 패턴 매칭, 통계
             → Layer 3 (9개)는 DeepEval/Ragas LLM 사용 (선택)
             → 네이티브 지표 추가 API 비용 $0
```

### 5.2 계산 비용 비교 (1,000 태스크 기준)

| | 추가 LLM 비용 | 오프라인 실행 | 계산 지연 |
|---|---|---|---|
| LangSmith | $2–10 | ❌ | 수 초 (API 왕복) |
| Ragas | $5–20 | ❌ | 수 초~분 |
| DeepEval | $3–15 | 부분 | 수 초 |
| Arize Phoenix | $3–10 | ✅ (로컬 서버) | 수 초 |
| Evidently AI | $0 | ✅ | 밀리초~초 |
| Braintrust | 선택적 | 부분 | 선택적 |
| Helicone | $0 | ❌ | 없음 (집계만) |
| W&B Weave | 선택적 | 부분 | 선택적 |
| **Agent Evaluator** | **$0** | **✅** | **밀리초** |

---

## 6. 대시보드 (Dashboard)

| 프레임워크 | 유형 | 주요 뷰 | 에이전트 전용 뷰 | 셀프호스트 | 비용 |
|-----------|------|---------|---------------|----------|------|
| **LangSmith** | SaaS | 트레이스 뷰어, 실험 비교, 피드백 집계 | Multi-turn 대화 뷰, Insights Agent | ✅ (Self-Hosted v0.12) | $39/월~ |
| **Ragas** | 없음 | — (외부 플랫폼 의존) | — | — | Ragas.io SaaS 별도 |
| **DeepEval** | SaaS (Confident AI) | 테스트 결과 히스토리, 회귀 탐지 | 에이전트 트레이스 뷰 | ❌ | 무료(500 runs) / $49/월~ |
| **Arize Phoenix** | OSS UI | 트레이스 탐색기, RAG 평가, 클러스터링 | OTEL span 트리 뷰 | ✅ (`px.launch_app()`) | 무료 / Cloud 유료 |
| **Evidently AI** | OSS + Cloud | HTML 리포트, 드리프트 대시보드 | 없음 (span별 일반 지표) | ✅ | $99/월~ |
| **Braintrust** | SaaS | 실험 비교, 트레이스 뷰, 점수 분포 | Workflow span 뷰 | ❌ | 무료(1,000 로그) / $100/월~ |
| **Helicone** | SaaS + OSS | 비용/레이턴시/오류율, 사용자별 분석 | Session 트리 뷰 | ✅ | 무료(10,000 요청) / $20/월~ |
| **W&B Weave** | SaaS | 실험 비교, 트레이스 뷰 | Multi-agent span 트리, MCP 뷰 | ❌ | 무료(개인) / $50/월/좌석~ |
| **Agent Evaluator** | OSS 로컬 | 9탭 대시보드 (품질·멀티턴대화·성능·에이전틱·보안·이상감지·평가비용·골든데이터셋·투명성) | 도구선택/워크플로우/재시도/멀티에이전트/보안 전용 탭 | ✅ (완전 로컬) | **무료** |

---

## 7. 개발자 필요 작업 종합 분석

### 7.1 전체 파이프라인 구현 작업 분류

**A. 지표 구성** — 어떤 지표를 평가할지 정의하는 코드

| | 작업 내용 | 줄 수 |
|---|---|---|
| LangSmith | LLM-judge 평가자 함수 작성 | 10–30줄 |
| Ragas | 지표 선택 (`from ragas.metrics import ...`) | 3–5줄 |
| DeepEval | 지표 인스턴스 생성 (`MetricClass(threshold=...)`) | 3–5줄 |
| Arize Phoenix | 평가 템플릿 선택 또는 프롬프트 작성 | 5–20줄 |
| Evidently AI | Descriptor 정의 + ColumnMapping | 10–30줄 |
| Braintrust | Scorer 함수 직접 구현 | 10–30줄 |
| Helicone | 없음 (인프라 지표만) | 0줄 |
| W&B Weave | Scorer 클래스 구현 | 10–30줄 |
| **Agent Evaluator** | `enable_*=True` 플래그 설정 | **1–3줄** |

**B. 데이터 수집** — 에이전트 실행 데이터를 수집하는 계측 코드

| | 작업 내용 | 줄 수 |
|---|---|---|
| LangSmith | 환경변수 또는 `@traceable` 데코레이터 | 2–5줄 |
| Ragas | 데이터셋 전체 수동 구성 (`MultiTurnSample`) | **30–100줄** |
| DeepEval | `LLMTestCase` 구성 또는 `instrument_*()` | 5–20줄 |
| Arize Phoenix | `register(auto_instrument=True)` | **5줄** |
| Evidently AI | `init_tracing()` + `@trace_event` | 10–15줄 |
| Braintrust | `auto_instrument()` 또는 `@traced` | 1–5줄 |
| Helicone | base_url 변경 1줄 | **1줄** |
| W&B Weave | `weave.init()` + `@weave.op()` | 1줄 + 함수당 1줄 |
| **Agent Evaluator** | `TaskResult` 구성 또는 factory 함수 | 5–15줄 |

**C. 지표 계산** — 실제 계산 실행 코드

| | 작업 내용 | 줄 수 |
|---|---|---|
| LangSmith | `client.evaluate()` 또는 UI에서 평가자 연결 | 5–10줄 |
| Ragas | `evaluate(dataset, metrics=[...])` | 3–5줄 |
| DeepEval | `evaluate([test_case], [metric])` | 3–5줄 |
| Arize Phoenix | `llm_classify()` 또는 Phoenix UI에서 실행 | 10–20줄 |
| Evidently AI | `Report(metrics=[...]).run()` | 5–10줄 |
| Braintrust | `Eval("project", data=..., task=..., scores=[...])` | 5–10줄 |
| Helicone | 없음 (자동 집계) | **0줄** |
| W&B Weave | `Evaluation(...).evaluate()` | 5–10줄 |
| **Agent Evaluator** | `monitor.generate_report()` | **1줄** |

**D. 대시보드** — 결과 시각화 작업

| | 작업 내용 | 줄 수 |
|---|---|---|
| LangSmith | 없음 (SaaS 자동) | 0줄 |
| Ragas | pandas로 직접 시각화 또는 외부 플랫폼 연동 | 20–50줄 |
| DeepEval | Confident AI 로그인 (`deepeval login`) | 1줄 |
| Arize Phoenix | `px.launch_app()` 1줄 | **1줄** |
| Evidently AI | HTML 리포트 자동 생성 | 3–5줄 |
| Braintrust | 없음 (SaaS 자동) | 0줄 |
| Helicone | 없음 (SaaS 자동) | 0줄 |
| W&B Weave | 없음 (SaaS 자동) | 0줄 |
| **Agent Evaluator** | `agent-eval dashboard` CLI 1줄 | **1줄** |

### 7.2 총 개발 작업량 시각화

```
개발자 코드 작업 부담 (낮을수록 좋음)
────────────────────────────────────────────────────
Helicone        █░░░░░░░░░  (LLM 호출만 추적; 품질 평가 없음)
Arize Phoenix   ██░░░░░░░░  (OTEL 자동화 우수; LLM 판단자 필요)
LangSmith       ██░░░░░░░░  (LangChain 사용 시; 커스텀 에이전트는 증가)
DeepEval        ███░░░░░░░  (TestCase 구성 필요; 에이전트 지표 추가됨)
Braintrust      ███░░░░░░░  (auto_instrument 우수; Scorer 직접 구현)
W&B Weave       ████░░░░░░  (weave.op 간결; Scorer 구현 필요)
Agent Evaluator ████░░░░░░  (TaskResult 구성 필요; 이후 자동)
Evidently AI    █████░░░░░  (DataFrame 준비 + Descriptor 정의)
Ragas           ███████░░░  (데이터셋 전체 수동 구성 — 가장 많음)
────────────────────────────────────────────────────
```

> **주의**: Helicone/LangSmith의 낮은 코드량은 LLM 인프라 관측에 특화된 결과임.
> Agentic AI 품질 평가(tool selection, retry, security)를 포함하면 모두 코드량이 크게 증가함.

### 7.3 에이전트 프레임워크별 자동 계측 지원

| 프레임워크 | LangChain | LangGraph | CrewAI | AutoGen | OpenAI Agents | Claude Agent SDK | PydanticAI | DSPy |
|-----------|:---------:|:---------:|:------:|:-------:|:------------:|:----------------:|:----------:|:----:|
| LangSmith | ✅ 자동 | ✅ 자동 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Ragas | ✅ 어댑터 | 부분 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| DeepEval | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Phoenix | ✅ 자동 | ✅ 자동 | ✅ 자동 | ❌ | ✅ | ✅ | ❌ | ✅ |
| Braintrust | ✅ 콜백 | ✅ 콜백 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| W&B Weave | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| **Agent Evaluator** | ✅ factory | ✅ factory | ✅ factory | ✅ factory | ❌ | ❌ | ❌ | ❌ |

> **v0.6.7 기준**: LangChain ≥1.0 / LangGraph ≥1.0 / CrewAI ≥1.0 / AutoGen 0.4+ (async-first) 최신 API 완전 지원. 4개 프레임워크 모두 16개 네이티브 지표 + 9개 Layer3 하이브리드 = 25개 지표 체계 적용 (프레임워크별 커버리지: LangChain ~82%, LangGraph ~82%, AutoGen ~80%, CrewAI ~78%).

---

## 8. 포지셔닝 맵

```
                    품질 평가 깊이
                         ↑
              Ragas       DeepEval
          (RAG 특화)    (14+ 지표)
                              Agent Evaluator
                            (16개 네이티브+9개 Layer3=25지표, 보안·Agentic 포함)
──────────────────────────────────────────────── → 에이전트 특화도
 Helicone    Evidently   LangSmith    Arize Phoenix
(인프라만)  (ML모니터링)  (트레이싱)   (OTEL+품질)

                    Braintrust
                  W&B Weave
                (실험 관리+관측)
                         ↓
                   인프라 관측
```

---

## 9. 선택 가이드

| 상황 | 추천 |
|------|------|
| LangChain/LangGraph를 사용하며 빠른 트레이싱이 필요 | **LangSmith** |
| RAG 파이프라인의 faithfulness/recall 정밀 측정 | **Ragas** |
| CI/CD에서 LLM 단위 테스트를 pytest처럼 실행 | **DeepEval** |
| OTEL 기반 인프라에 통합, 로컬 셀프호스트 대시보드 필요 | **Arize Phoenix** |
| LLM 비용/레이턴시 실시간 모니터링, 최소 코드 | **Helicone** |
| 실험 관리 + 에이전트 트레이싱 + 팀 협업 | **Braintrust** 또는 **W&B Weave** |
| 프로덕션 ML 모델 드리프트 + LLM 품질 통합 모니터링 | **Evidently AI** |
| **에이전트 보안 검증** (프롬프트 인젝션, 권한 상승 등) | **Agent Evaluator** |
| **Agentic 행동 분석** (tool 선택 F1, retry, 멀티에이전트) | **Agent Evaluator** |
| **추가 API 비용 없이 16개 네이티브 지표 측정** | **Agent Evaluator** |
| **데이터 외부 유출 없는 완전 로컬 평가** | **Agent Evaluator** |

---

## 10. Agent Evaluator 차별점 요약

### 유일하게 제공하는 것
1. **Agentic 보안 지표 5종** — 업계 어디에도 없는 지표 (프롬프트 인젝션, 출력 유출, 권한 상승, Tool 체인 공격, 비인가 Tool 사용)
2. **Retry/자기수정 분석** — 에이전트가 얼마나 스스로 오류를 수정하는지 (LangChain `on_retry`, AutoGen `is_error=True`, LangGraph/CrewAI 실패 노드·태스크 감지)
3. **Tool Selection F1** — Tool 선택 정밀도/재현율 기반 정량 평가 (DeepEval과 달리 LLM 불필요)
4. **LLM 없이 16개 네이티브 지표 계산** — $0 추가 비용 (Layer 3 하이브리드 9개는 선택적); LangChain/LangGraph/CrewAI/AutoGen 4개 프레임워크 전체 지원 (커버리지: LangChain ~82%, LangGraph ~82%, AutoGen ~80%, CrewAI ~78%)
5. **완전 로컬 대시보드** — 평가 데이터가 외부로 나가지 않음
6. **RAG 컨텍스트 자동 수집** — `HallucinationDetector`가 LangChain retriever, LangGraph ToolMessage, CrewAI 중간 태스크, AutoGen 도구 결과에서 컨텍스트를 자동 연결해 faithfulness 측정

### 현재 없는 것 (개선 기회)
1. **실시간 span 트레이싱** — LangSmith/Phoenix처럼 실행 중 UI 반영 불가
2. **OTEL 연동** — 기존 OTEL 파이프라인에서 데이터를 수신하거나 내보내는 기능 없음
3. **의미론적 LLM 판단자** — Ragas의 Faithfulness 같은 의미 기반 평가 불가 (Adapter로 연동은 가능)
4. **SaaS 팀 협업** — 팀 대시보드 공유, 실험 비교 히스토리 없음
5. **범용 에이전트 프레임워크 자동 계측** — OpenAI Agents SDK, Claude Agent SDK, PydanticAI 등 미지원

---

*참조 출처: LangSmith Changelog (2025.10), Ragas v0.4.3 Docs (2026.01), DeepEval Changelog 2025, Arize Phoenix 2024-in-Review, Evidently AI Tracely, Braintrust Changelog v0.5.2, Helicone Sessions Docs, W&B Weave OTEL Docs*
