# 데코레이터 가이드

에이전트 코드에 평가를 적용하는 실전 개발자 레퍼런스

**Version**: 0.7.3  
**최종 업데이트**: 2026-04-07

---

## 목차

1. [3가지 데코레이터 방식 한눈에 보기](#1-3가지-데코레이터-방식-한눈에-보기)
2. [데코레이터 내부 동작 원리](#2-데코레이터-내부-동작-원리)
3. [방식 1 — `agent_eval`](#3-방식-1--agent_eval)
4. [방식 2 — `QuickEval` / `EvalDecorator`](#4-방식-2--quickeval--evaldecorator)
5. [방식 3 — `conversation_eval`](#5-방식-3--conversation_eval)
6. [메타데이터 주입 — `EvalMetadata` & `get_eval_ctx()`](#6-메타데이터-주입--evalmetadata--get_eval_ctx)
7. [지표별 커버리지](#7-지표별-커버리지)
8. [프레임워크별 커버리지](#8-프레임워크별-커버리지)
9. [Dashboard / Phoenix UI 커버리지](#9-dashboard--phoenix-ui-커버리지)
10. [프로덕션 설정](#10-프로덕션-설정)
11. [전체 파라미터 레퍼런스](#11-전체-파라미터-레퍼런스)

---

## 1. 3가지 데코레이터 방식 한눈에 보기

```
┌──────────────────┬──────────────────────────────────┬─────────────────────────────┐
│ 방식              │ 언제 사용                          │ 코드 한 줄                   │
├──────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ agent_eval       │ 단일 호출 에이전트 함수             │ @agent_eval(monitor)         │
│ QuickEval        │ 빠른 시작 / 다수 에이전트 한 파일   │ eval = QuickEval("results/") │
│ conversation_eval│ 멀티턴 대화 에이전트               │ @conversation_eval(monitor)  │
└──────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

### 최소 설치

```bash
pip install agent-evaluator          # Layer 1+2 (외부 의존성 없음)
pip install "agent-evaluator[llm]"   # + LLM Judge (OpenAI/Anthropic)
pip install "agent-evaluator[otel]"  # + Phoenix 실시간 모니터링
```

### 공통 임포트

```python
from agent_evaluator import PerformanceMonitor, QuickEval
from agent_evaluator.decorators import (
    agent_eval,
    agent_eval_async,          # agent_eval과 동일 — async 함수용 명시적 alias
    agent_eval_with_retry,     # agent_eval과 동일 — max_retries 강조용 alias
    conversation_eval,
    flush_conversation,
    EvalMetadata,
    get_eval_ctx,
)
from agent_evaluator.integrations import (
    langchain_eval, langgraph_eval,   # 프레임워크 전용 alias
    crewai_eval, autogen_eval,
    openai_eval, anthropic_eval,
)
```

---

## 2. 데코레이터 내부 동작 원리

### 실행 흐름

```
함수 호출
   │
   ├─ sample_rate / sample_condition 체크 → 미충족 시 실행만 하고 평가 생략
   │
   ├─ 실행 시작 시각 기록
   │
   ├─ 원본 함수 실행 (max_retries 설정 시 재시도 루프)
   │    ├─ 예외 발생 → has_error=True, error_message 기록 → 재시도 또는 종료
   │    └─ 정상 반환
   │         ├─ (response, EvalMetadata) 튜플 감지 → metadata 분리
   │         └─ 일반 값 → response로 처리
   │
   ├─ framework 어댑터 적용 (response 객체에서 tool_calls / chain_steps 자동 추출)
   │    └─ auto_detect_framework=True 이면 응답 타입으로 프레임워크 자동 감지
   │
   ├─ get_eval_ctx() 스레드로컬 값 병합
   │
   ├─ TaskResult 생성 (create_taskresult)
   │    └─ accuracy_score / completion_score 자동 계산
   │
   ├─ monitor.record_task(task_result)
   │    ├─ Layer 1 트래커 (TCR, Latency, Token, Quality, Accuracy, Hallucination)
   │    ├─ Layer 2 트래커 (Tool, Retry, Workflow, Coordination — 필드 존재 시)
   │    ├─ OTEL 스팬 발행 (setup_otel() 호출된 경우)
   │    │    ├─ 부모 스팬 (task_type → span kind 매핑)
   │    │    └─ tool_calls 자식 스팬 (kind=TOOL, 항상 발행)
   │    └─ on_record 콜백
   │
   └─ 원본 response 반환 (호출자에게 EvalMetadata는 보이지 않음)
```

### 메타데이터 병합 우선순위

동일 필드가 여러 곳에서 설정될 때 우선순위:

```
EvalMetadata (튜플 반환)  >  get_eval_ctx() 설정  >  framework 어댑터 자동 추출
```

`accuracy_score`는 `EvalMetadata`가 명시하면 우선 적용되고, `score_fn`은 무시됩니다.

```python
# EvalMetadata(accuracy_score=0.95) vs score_fn=lambda: 0.1
# → 최종 accuracy_score = 0.95  (EvalMetadata 우선)
```

---

## 3. 방식 1 — `agent_eval`

가장 범용적인 방식. sync/async 함수 모두 자동 감지.

### 기본 QA

```python
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 호출
answer = qa_agent("한국의 수도는?", ground_truth="서울")
```

### async 에이전트

```python
@agent_eval(monitor, task_type="qa")            # sync/async 자동 감지
async def async_agent(question: str, ground_truth: str = "") -> str:
    return await llm.ainvoke(question)
```

### 파라미터 이름 커스터마이징

```python
@agent_eval(
    monitor,
    task_type="information_retrieval",
    question_arg="query",          # 기본값: "question"
    ground_truth_arg="expected",   # 기본값: "ground_truth"
    task_id_prefix="search",
)
def search_agent(query: str, expected: str = "") -> str:
    return retriever.get(query)
```

### RAG + 할루시네이션 감지

```python
# 방법 A: rag_mode=True (한 줄)
@agent_eval(monitor, rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})

# 방법 B: context_arg 명시
@agent_eval(
    monitor,
    task_type="information_retrieval",
    context_arg="context",
    enable_hallucination=True,      # 이 데코레이터에서만 임시 활성
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...
```

### Tool Use 에이전트

```python
@agent_eval(
    monitor,
    task_type="tool_use",
    expected_tools_arg="expected_tools",   # ToolSelectionTracker F1 활성
)
def tool_agent(
    question: str,
    expected_tools: list = None,
    ground_truth: str = "",
) -> str:
    ctx = get_eval_ctx()
    result = agent_executor.invoke({"input": question})
    # tool_calls 직접 주입 (자동 추출 안 될 때)
    ctx.tool_calls = [
        {"tool_name": "web_search", "arguments": {"q": question}, "result": "...", "success": True},
    ]
    return result["output"]

tool_agent("검색해줘", expected_tools=["web_search", "calculator"], ground_truth="답변")
```

### 내장 재시도

```python
@agent_eval(
    monitor,
    task_type="qa",
    max_retries=3,
    retry_on=(ConnectionError, TimeoutError),
    delay=1.0,
    backoff=2.0,           # 지수 백오프
    jitter_type="full",    # "full" | "decorrelated" | "none"
    max_delay=30.0,
)
def fragile_agent(question: str, ground_truth: str = "") -> str:
    return unstable_llm.invoke(question)
```

### 에러 자동 기록

```python
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    if is_invalid(question):
        raise ValueError("잘못된 입력")   # has_error=True 자동 기록 후 예외 재발생
    return llm.invoke(question)

try:
    agent("잘못된 질문", ground_truth="")
except ValueError:
    pass  # 평가 기록은 이미 됨
```

### enabled 플래그 (환경별 On/Off)

```python
EVAL_ON = os.getenv("AGENT_EVAL_ENABLED", "true").lower() == "true"

@agent_eval(monitor, task_type="qa", enabled=EVAL_ON)
def agent(question: str, ground_truth: str = "") -> str: ...
```

### 샘플링 (프로덕션 트래픽 부분 평가)

```python
# 10% 확률로만 평가
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def agent(question: str, ground_truth: str = "") -> str: ...

# 조건부 샘플링
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kw: kw.get("priority") == "high",
)
def agent(question: str, priority: str = "normal", ground_truth: str = "") -> str: ...
```

### 스트리밍 generator

```python
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = "") -> Iterator[str]:
    for chunk in llm.stream(question):
        yield chunk
    # 마지막에 EvalMetadata yield (선택)
    yield EvalMetadata(tokens_used={"input": 100, "output": 50})
```

---

## 4. 방식 2 — `QuickEval` / `EvalDecorator`

여러 에이전트를 한 파일에서 빠르게 시작할 때 권장.

### 기본 사용

```python
eval = QuickEval("results/")

@eval.qa                         # 괄호 없이 사용
def qa_agent(question, ground_truth=""): ...

@eval.tool_use                   # tool_use 자동 설정
def tool_agent(question, ground_truth=""): ...

@eval.rag                        # context_arg="context" 자동 설정
def rag_agent(question, context="", ground_truth=""): ...

@eval.qa(score_fn=my_fn)         # 괄호 + kwargs 혼용
def custom_agent(question, ground_truth=""): ...
```

### 단축 속성 전체 목록

| 속성 | task_type | 자동 설정 |
|------|-----------|----------|
| `.qa` | `"qa"` | — |
| `.tool_use` | `"tool_use"` | — |
| `.rag` | `"information_retrieval"` | `context_arg="context"` |
| `.code` | `"code_generation"` | — |
| `.reasoning` | `"reasoning"` | — |
| `.planning` | `"planning"` | — |
| `.data_analysis` | `"data_analysis"` | — |
| `.creative` | `"creative"` | — |
| `.multi_agent` | `"tool_use"` | — |
| `.security` | `"tool_use"` | 보안 트래커 임시 활성 |
| `.streaming` | `"qa"` | generator 자동 감지 |
| `.batch` | — | `batch_eval` 래핑 |
| `.chat` | — | `conversation_eval` 래핑 |

### 팩토리 메서드

```python
# RAG 전용 — hallucination_detection 기본 활성
eval = QuickEval.for_rag("results/")

# 보안 전용 — 보안 트래커 기본 활성
eval = QuickEval.for_security("results/")

# LLM Judge — judge_model 자동 설정
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 회귀 탐지 — baseline 비교
eval = QuickEval.for_regression_eval("results/", baseline_file="baseline.json")
```

### gate() — CI/CD 품질 게이팅

```python
eval.save()
eval.gate(
    tcr=85,          # Task Completion Rate 최소 85%
    accuracy=70,     # 정확도 최소 70%
    quality=3.0,     # 품질 점수 최소 3.0/5.0
)
# 미달 시 sys.exit(1)
```

### auto_save (대시보드 실시간 반영)

```python
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
# 10건마다 자동으로 save_to_file() 호출
```

---

## 5. 방식 3 — `conversation_eval`

멀티턴 대화 에이전트 전용. 세션 단위로 context_retention, topic_coherence 등을 자동 계산.

### 기본 사용

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",    # 기본값: "session_id"
    user_arg="question",     # 기본값: "question"
    max_turns=10,            # 최대 턴 수 (초과 시 자동 flush)
)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(sid, question)

# 호출
chat_agent("안녕하세요", sid="user_001")
chat_agent("오늘 날씨는?", sid="user_001")
chat_agent("감사합니다", sid="user_001")

# 명시적 종료 (max_turns 미도달 시)
flush_conversation("user_001")
```

### async 대화

```python
@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
async def async_chat(question: str, sid: str = "session") -> str:
    return await async_chatbot.chat(sid, question)
```

### 계산되는 지표

| 지표 | 설명 |
|------|------|
| `context_retention` | 이전 턴 내용을 응답에 반영하는 비율 |
| `topic_coherence` | 대화 주제 일관성 |
| `progressive_depth` | 대화가 깊어지는 정도 |
| `session_completion` | 세션 완료율 |
| `avg_turn_latency` | 평균 턴 응답 시간 |
| `overall_score` | 위 지표 종합 점수 |

### 콜백

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    on_flush=lambda sid: print(f"세션 {sid} 종료"),
    on_turn=lambda sid, q, resp, _: log_turn(sid, q, resp),
    session_score_fn=lambda metrics: metrics.context_retention * 0.6 + metrics.topic_coherence * 0.4,
)
def chat_agent(question: str, sid: str = "") -> str: ...
```

---

## 6. 메타데이터 주입 — `EvalMetadata` & `get_eval_ctx()`

Layer 2 트래커 (Tool, Workflow, Coordination, Retry)를 활성화하려면 `tool_calls`, `chain_steps`, `agent_interactions`, `attempts` 필드를 채워야 합니다.

두 가지 방법이 있습니다.

### 방법 A — `EvalMetadata` 튜플 반환

응답 객체를 수정할 수 없거나 함수 종료 후 한 번에 메타데이터를 주입할 때 사용.

```python
@agent_eval(monitor, task_type="tool_use")
def agent(question: str, ground_truth: str = "") -> tuple:
    result = executor.invoke(question)
    return result["output"], EvalMetadata(
        attempts=2,
        framework="langchain",
        tool_calls=[
            {"tool_name": "web_search", "arguments": {"q": question}, "result": "...", "success": True},
            {"tool_name": "summarizer",  "arguments": {"text": "..."}, "result": "...", "success": True},
        ],
        chain_steps=[
            {"name": "search",    "success": True, "execution_time": 0.3},
            {"name": "summarize", "success": True, "execution_time": 0.1},
        ],
        agent_interactions=[
            {"from_agent": "router", "to_agent": "search_agent", "type": "delegation", "success": True},
        ],
        tokens_used={"input": 200, "output": 80, "total": 280},
    )

# 호출자는 str만 받음 (EvalMetadata는 내부에서 소비)
answer = agent("AI 뉴스 검색해줘", ground_truth="최신 AI 트렌드")
```

### 방법 B — `get_eval_ctx()` 실행 중 주입

함수 실행 도중 점진적으로 메타데이터를 채울 때 사용. ContextVar 기반으로 async 환경에서도 안전.

```python
@agent_eval(monitor, task_type="tool_use")
def agent(question: str, ground_truth: str = "") -> str:
    ctx = get_eval_ctx()

    # 도구 실행
    search_result = web_search(question)
    ctx.tool_calls = [
        {"tool_name": "web_search", "arguments": {"q": question},
         "result": search_result, "success": True},
    ]

    # 추론 단계
    ctx.chain_steps = [
        {"name": "search",    "success": True},
        {"name": "synthesis", "success": True},
    ]

    # 에이전트 위임
    ctx.agent_interactions = [
        {"from_agent": "orchestrator", "to_agent": "search_agent",
         "message_type": "task_delegation", "success": True},
    ]

    return synthesize(search_result)
```

### `EvalMetadata` 전체 필드

```python
@dataclass
class EvalMetadata:
    # Layer 2 트래커 활성화 필드
    tool_calls: Optional[List[Dict]]         = None  # ToolCallAnalyzer
    expected_tools: Optional[List[str]]      = None  # ToolSelectionTracker (tool_calls와 함께)
    chain_steps: Optional[List[Dict]]        = None  # WorkflowExecutionTracker
    agent_interactions: Optional[List[Dict]] = None  # AgentCoordinationTracker
    attempts: Optional[int]                  = None  # RetryCorrectionTracker

    # LangGraph 전용
    graph_traversal: Optional[Dict]          = None
    state_transitions: Optional[List[Dict]]  = None

    # 점수 override (score_fn보다 우선)
    accuracy_score: Optional[float]          = None
    completion_score: Optional[float]        = None

    # 식별
    framework: Optional[str]                 = None
    model_name: Optional[str]                = None
    tokens_used: Optional[Dict[str, int]]    = None  # {"input": N, "output": N, "total": N}

    # RAG
    context: Optional[str]                   = None  # HallucinationDetector용
    ground_truth: Optional[str]              = None  # 런타임 override

    # 기타
    partial_reason: Optional[str]            = None
    errors: Optional[List[str]]              = None
    execution_time: Optional[float]          = None
    conversation_turns: Optional[List[Dict]] = None  # AutoGen
    llm_judge: Optional[Dict]               = None
    extra: Optional[Dict]                    = None  # TaskResult.extra로 전달
```

---

## 7. 지표별 커버리지

### Layer 1 — 항상 활성 (외부 의존성 없음)

| 지표 | 트래커 | 활성 조건 | 데코레이터 파라미터 |
|------|--------|----------|-------------------|
| Task Completion Rate (TCR) | `TaskCompletionTracker` | 항상 | — |
| QA 정확도 | `AccuracyEvaluator` | `ground_truth` 있을 때 | — |
| 응답 품질 (5차원) | `ResponseQualityEvaluator` | 항상 | — |
| 레이턴시 P50/P95/P99 | `LatencyTracker` | 항상 | — |
| 토큰 사용량 / 비용 | `TokenEconomyTracker` | `tokens_used` 필드 | — |
| 할루시네이션 탐지 | `HallucinationDetector` | `context` 필드 + opt-in | `rag_mode=True` 또는 `context_arg=` |
| TTFT (첫 토큰 시간) | `LatencyTracker.track_ttft()` | generator 반환 시 자동 | — |

### Layer 2 — TaskResult 필드 존재 시 자동 활성

| 지표 | 트래커 | 활성 조건 |
|------|--------|----------|
| 도구 호출 패턴 | `ToolCallAnalyzer` | `tool_calls` 리스트 (len > 0) |
| 도구 선택 F1 | `ToolSelectionTracker` | `tool_calls` + `expected_tools` |
| 재시도 / 오류 수정 | `RetryCorrectionTracker` | `attempts > 1` |
| 워크플로우 단계 | `WorkflowExecutionTracker` | `chain_steps` 리스트 (len > 0) |
| 멀티에이전트 조율 | `AgentCoordinationTracker` | `agent_interactions` 리스트 (len > 0) |

### Layer 2 보안 — opt-in

```python
# PerformanceMonitor 수준 영구 활성
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

# 개별 데코레이터 임시 활성
@agent_eval(monitor, task_type="tool_use", security_mode=True)
def agent(...): ...
```

| 지표 | 트래커 | 탐지 대상 |
|------|--------|----------|
| 입력 인젝션 탐지 | `InputSanitizationTracker` | SQL injection, prompt injection, XSS, path traversal |
| 출력 유출 탐지 | `OutputLeakageDetector` | API 키, 개인정보, 시스템 경로 |
| 도구 권한 탐지 | `ToolAuthorizationTracker` | 미허가 도구 사용 |
| 권한 상승 탐지 | `PrivilegeEscalationDetector` | 권한 남용 패턴 |
| 도구 체인 공격 | `ToolChainAttackDetector` | 연쇄 공격 패턴 |

### 필드 → 트래커 활성화 요약

```
tool_calls = [...]               → ToolCallAnalyzer
tool_calls + expected_tools      → ToolSelectionTracker (F1)
attempts = 3                     → RetryCorrectionTracker
chain_steps = [...]              → WorkflowExecutionTracker
agent_interactions = [...]       → AgentCoordinationTracker
context = "..."                  → HallucinationDetector (opt-in)
tokens_used = {"input":N, ...}   → TokenEconomyTracker (비용 계산)
```

---

## 8. 프레임워크별 커버리지

### 자동 추출 방식

```python
# 방법 A: framework= 파라미터 명시
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def agent(question, ground_truth=""):
    return agent_executor.invoke({"input": question})

# 방법 B: 전용 decorator alias
from agent_evaluator.integrations import langchain_eval

@langchain_eval(monitor, task_type="tool_use")
def agent(question, ground_truth=""):
    return agent_executor.invoke({"input": question})

# 방법 C: 자동 감지 (기본 활성, auto_detect_framework=True)
@agent_eval(monitor, task_type="tool_use")
def agent(question, ground_truth=""):
    return agent_executor.invoke({"input": question})
    # 반환 객체가 dict + "intermediate_steps" → langchain 자동 감지
```

### 프레임워크별 자동 추출 필드

| 프레임워크 | 어댑터 | 자동 추출 |
|-----------|--------|----------|
| LangChain | `langchain_eval` | `intermediate_steps` → `tool_calls` + `chain_steps` |
| LangGraph | `langgraph_eval` | `messages` → `state_transitions` + `graph_traversal` + `tool_calls` |
| CrewAI | `crewai_eval` | `tasks_output` → `agent_interactions` |
| AutoGen | `autogen_eval` | `conversation_history` → `conversation_turns` + 실행시간 |
| DSPy | `dspy_eval` | `_completions` → `chain_steps` + 토큰 |
| PydanticAI | `pydanticai_eval` | `RunResult.usage()` → `tokens_used` + `tool_calls` |
| OpenAI SDK | `openai_eval` | `choices[0].message.tool_calls` + `usage.total_tokens` |
| Anthropic SDK | `anthropic_eval` | `content[].tool_use` + `usage.input/output_tokens` |
| Gemini | `gemini_eval` | `candidates[0].content.parts[].function_call` + `usage_metadata` |
| LlamaIndex | `llamaindex_eval` | `source_nodes` → `chain_steps` |
| Haystack | `haystack_eval` | 파이프라인 컴포넌트 출력 → `chain_steps` |

### LangChain 실제 적용 예시

```python
from langchain.agents import AgentExecutor, create_openai_tools_agent
from agent_evaluator.integrations import langchain_eval

monitor = PerformanceMonitor(output_dir="results/")

@langchain_eval(monitor, task_type="tool_use")
def run_agent(question: str, ground_truth: str = "") -> dict:
    return agent_executor.invoke({"input": question})
    # 반환 dict의 intermediate_steps에서 tool_calls, chain_steps 자동 추출
```

### LangGraph 실제 적용 예시

```python
from agent_evaluator.integrations import langgraph_eval

@langgraph_eval(monitor, task_type="reasoning")
def run_graph(question: str, ground_truth: str = "") -> dict:
    return graph.invoke({"messages": [HumanMessage(content=question)]})
    # messages 리스트에서 state_transitions, graph_traversal 자동 추출
```

### OpenAI SDK 직접 호출 예시

```python
from agent_evaluator.integrations import openai_eval
import openai

@openai_eval(monitor, task_type="tool_use")
def call_openai(question: str, ground_truth: str = "") -> object:
    return openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )
    # ChatCompletion 객체에서 tool_calls + tokens 자동 추출
    # 호출자에게는 ChatCompletion 객체 그대로 반환
```

### Anthropic SDK 직접 호출 예시

```python
from agent_evaluator.integrations import anthropic_eval
import anthropic

@anthropic_eval(monitor, task_type="tool_use")
def call_claude(question: str, ground_truth: str = "") -> object:
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )
    # content[].tool_use + usage.input/output_tokens 자동 추출
```

---

## 9. Dashboard / Phoenix UI 커버리지

### Phoenix (실시간 모니터링)

Phoenix는 OTEL 스팬으로 데이터를 수신합니다.

```python
from agent_evaluator import setup_otel

# 스크립트 시작 시 1회 호출
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

# 이후 모든 monitor.record_task() 에서 자동으로 스팬 발행
```

**CLI로 Phoenix 서버 시작:**
```bash
agent-eval monitor         # http://localhost:6006
agent-eval monitor --check # OTEL 패키지 설치 여부 확인
```

#### Phoenix 탭별 커버리지

| 탭 | 표시 데이터 | 활성 조건 |
|----|------------|----------|
| **Tracing** | 에이전트 실행 스팬 트리 | 항상 |
| **Tracing > Tool spans** | 도구 호출 자식 스팬 | `tool_calls` 필드 존재 시 자동 |
| **Evaluators** | accuracy, completion, hallucination, quality 점수 | `annotator_kind="LLM"` 자동 설정 |
| **Datasets & Experiments** | 골든 데이터셋 업로드 | `GoldenSetBuilder.push_to_phoenix()` |
| **Prompts** | 프롬프트 버전 관리 | `setup_otel()` 호출 후 자동 |

#### span kind 매핑

| task_type | OTEL span kind | Phoenix 분류 |
|-----------|---------------|-------------|
| `qa`, `code_generation`, `creative` | `LLM` | LLM spans |
| `tool_use` | `TOOL` | Tool spans |
| `information_retrieval` | `RETRIEVER` | Retrieval spans |
| `planning` | `AGENT` | Agent spans |
| `data_analysis`, `reasoning` | `CHAIN` | Chain spans |

#### tool_calls → Tool spans 자식 스팬

`tool_calls`가 있으면 각 도구 호출이 Phoenix에 자식 스팬으로 자동 발행됩니다:

```
ae.task/tool_use/task_001  (parent, kind=TOOL)
 ├─ ae.tool/task_001/web_search    (child, kind=TOOL, tool.name="web_search")
 └─ ae.tool/task_001/calculator    (child, kind=TOOL, tool.name="calculator")
```

### 내장 대시보드 (FastAPI)

```bash
agent-eval dashboard       # http://localhost:8765
```

| 섹션 | 표시 데이터 |
|------|------------|
| Overview | TCR, 평균 정확도, 평균 지연 시간, 총 비용 |
| Task List | 태스크별 accuracy, latency, tokens, framework |
| Frameworks | 프레임워크별 집계 지표 |
| Timeline | 시간대별 성능 추이 |
| LLM Judge | completeness, relevance, factual_consistency 분포 |
| Anomaly | 이상 탐지 이벤트 목록 |
| Cost | 모델별·기간별 비용 분석 |
| Sessions | 멀티턴 대화 세션 목록 |
| Alerts | 알림 이력 |
| Export | JSON/Excel/HTML 내보내기 |

---

## 10. 프로덕션 설정

### 프리셋

```python
# production: 10% 샘플링, 30초 타임아웃, 50건마다 저장
@agent_eval(monitor, task_type="qa", preset="production")
def agent(...): ...

# development: 100% 샘플링, LLM Judge 활성
@agent_eval(monitor, task_type="qa", preset="development")
def agent(...): ...

# testing: 10% 샘플링, 60초 타임아웃
@agent_eval(monitor, task_type="qa", preset="testing")
def agent(...): ...

# canary: 5% 샘플링, 이상 감지 활성
@agent_eval(monitor, task_type="qa", preset="canary")
def agent(...): ...
```

| 프리셋 | sample_rate | timeout | flush_every | 특이 사항 |
|--------|------------|---------|-------------|----------|
| `production` | 0.1 | 30s | 50 | 이상 감지 + LLM Judge 활성 |
| `development` | 1.0 | None | 1 | 모든 기능 활성 |
| `testing` | 0.1 | 60s | 5 | — |
| `canary` | 0.05 | 30s | 50 | 이상 감지 활성 |

### 경량 알림 규칙

```python
from agent_evaluator import SimpleTaskAlertRule, AlertRuleBuilder

# 직접 생성
slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: slack_notify(msg),
    severity="warning",
    cooldown=60,
)

# 팩토리 메서드
low_acc_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.5,
    handler=lambda msg, tr: pagerduty_alert(msg),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[slow_alert, low_acc_alert])
def agent(question, ground_truth=""): ...
```

### 자동 주기 저장

```python
# N번 호출마다 save_to_file() 자동 실행
@agent_eval(monitor, task_type="qa", flush_every=10, flush_filename="periodic_save")
def agent(question, ground_truth=""): ...

# PerformanceMonitor 수준 자동 저장
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,
    auto_save_filename="auto_save",
)
```

### LLM Judge (Ground Truth 없이 채점)

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",  # 또는 "gpt-4o-mini"
)

@agent_eval(monitor, task_type="qa")
def agent(question, ground_truth=""): ...
# completeness, relevance, factual_consistency 자동 채점
```

---

## 11. 전체 파라미터 레퍼런스

### `agent_eval` 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `monitor` | `PerformanceMonitor` | (필수) | 결과를 기록할 모니터 인스턴스 |
| `task_type` | `str` | `"qa"` | 태스크 유형 (`"qa"`, `"tool_use"`, `"information_retrieval"`, `"code_generation"`, `"reasoning"`, `"planning"`, `"data_analysis"`, `"creative"`) |
| `question_arg` | `str` | `"question"` | 질문 파라미터 이름 |
| `ground_truth_arg` | `str` | `"ground_truth"` | 정답 파라미터 이름 |
| `context_arg` | `str` | `None` | RAG context 파라미터 이름 |
| `expected_tools_arg` | `str` | `None` | expected_tools 파라미터 이름 |
| `task_id_arg` | `str` | `None` | task_id 파라미터 이름 |
| `task_id_prefix` | `str` | `"task"` | 자동 생성 task_id 접두어 |
| `task_id_fn` | `Callable` | `None` | `(args, kwargs) → str` 커스텀 task_id 생성 함수 |
| `framework` | `str` | `"native"` | 프레임워크 식별자 |
| `model_name` | `str` | `""` | LLM 모델명 |
| `score_fn` | `Callable` | `None` | `(response, ground_truth) → float` 커스텀 정확도 함수 |
| `completion_fn` | `Callable` | `None` | `(response, ground_truth) → float` 커스텀 완료 점수 함수 |
| `sample_rate` | `float` | `1.0` | 평가 샘플링 비율 (0.0–1.0) |
| `sample_condition` | `Callable` | `None` | `(args, kwargs) → bool` 조건부 샘플링 |
| `max_retries` | `int` | `1` | 최대 재시도 횟수 (1=재시도 없음) |
| `retry_on` | `tuple` | `(Exception,)` | 재시도할 예외 타입 |
| `delay` | `float` | `0.0` | 재시도 초기 대기 시간(초) |
| `backoff` | `float` | `1.0` | 재시도 대기 시간 배율 |
| `jitter_type` | `str` | `"full"` | 재시도 지터 타입 (`"full"`, `"decorrelated"`, `"none"`) |
| `max_delay` | `float` | `60.0` | 최대 대기 시간(초) |
| `should_retry` | `Callable` | `None` | `(exc) → bool` 재시도 여부 결정 함수 |
| `on_retry` | `Callable` | `None` | `(attempt, error_msg) → None` 재시도 시 콜백 |
| `timeout` | `float` | `None` | 함수 실행 타임아웃(초) |
| `enabled` | `bool` | `True` | `False`이면 평가 없이 원본 함수만 실행 |
| `dry_run` | `bool` | `False` | `True`이면 설정 검증만 하고 기록 안 함 |
| `on_record` | `Callable` | `None` | `(TaskResult) → Optional[TaskResult]` 기록 직전 콜백 |
| `on_error` | `Callable` | `None` | `(TaskResult) → None` 에러 발생 시 콜백 |
| `custom_parser` | `Callable` | `None` | `(response) → Optional[EvalMetadata]` 커스텀 파서 |
| `alert_rules` | `list` | `None` | `SimpleTaskAlertRule` 목록 |
| `flush_every` | `int` | `None` | N번 호출마다 `save_to_file()` 자동 실행 |
| `flush_filename` | `str` | `"auto_save"` | flush 시 파일명 |
| `auto_detect_framework` | `bool` | `True` | 응답 타입으로 프레임워크 자동 감지 |
| `rag_mode` | `bool` | `False` | `True`이면 `context_arg="context"` + hallucination 자동 설정 |
| `security_mode` | `bool` | `False` | `True`이면 보안 트래커 임시 활성 |
| `enable_hallucination` | `bool` | `False` | 이 데코레이터에서만 hallucination detection 활성 |
| `enable_llm_judge` | `bool` | `False` | 이 데코레이터에서만 LLM Judge 활성 |
| `judge_model` | `str` | `None` | LLM Judge 모델명 |
| `enable_anomaly_detection` | `bool` | `False` | 이 데코레이터에서만 이상 감지 활성 |
| `preset` | `str` | `None` | 사전 정의 파라미터 묶음 (`"production"`, `"development"`, `"testing"`, `"canary"`) |
| `allow_duplicate_task_ids` | `bool` | `True` | `False`이면 중복 task_id 시 경고 |

### `conversation_eval` 주요 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `session_id_arg` | `"session_id"` | 세션 ID 파라미터 이름 |
| `user_arg` | `"question"` | 사용자 입력 파라미터 이름 |
| `max_turns` | `None` | 최대 턴 수 (초과 시 자동 flush) |
| `max_session_seconds` | `None` | 세션 최대 시간(초) |
| `session_score_fn` | `None` | `(ConversationMetrics) → float` |
| `turn_score_fn` | `None` | `(question, response, ctx) → float` |
| `on_flush` | `None` | `(session_id) → None` 세션 종료 시 콜백 |
| `on_turn` | `None` | `(sid, q, resp, ctx) → None` 매 턴 콜백 |
| `flush_every` | `0` | N턴마다 자동 저장 (0=비활성) |

---

*예제 파일: `Evaluator_Examples/18_decorator_eval.py` ~ `21_layer2_agentic_eval.py`*
