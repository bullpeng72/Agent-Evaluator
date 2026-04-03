# 데코레이터 가이드

Opik `@track` 스타일로 agent-evaluator를 적용하는 방법, 커버 가능한 지표·프레임워크·UI 범위 종합 정리

**Version**: 0.7.0  
**최종 업데이트**: 2026-04-03 (Gap AJ~AY 구현 반영 — on_retry/on_error 콜백, EvalMetadata errors/execution_time, batch on_batch_complete, TurnMetadata ground_truth, task_id_arg, jitter, eval_context task_id_fn, EvalDecorator update_defaults/for_llm_judge, 스트리밍 EvalMetadata, conversation turn_score_fn/max_session_seconds)

---

## 목차

1. [개요](#1-개요)
2. [설치 및 임포트](#2-설치-및-임포트)
3. [적용 방법 레퍼런스](#3-적용-방법-레퍼런스)
   - 3-1. 기본 QA
   - 3-2. 파라미터 이름 커스터마이징
   - 3-3. RAG + 할루시네이션 감지
   - 3-4. 비동기 에이전트
   - 3-5. LLM API 직접 호출 (OpenAI / Anthropic / Gemini)
   - 3-6. 에러 처리
   - 3-7. `enabled` 플래그
   - 3-8. **`EvalMetadata` 튜플 반환** _(Phase 2)_
   - 3-9. **`get_eval_ctx()` ContextVar 컨텍스트** _(Phase 2)_
   - 3-10. **`@agent_eval_with_retry`** _(Phase 3)_
   - 3-11. **`@conversation_eval`** _(Phase 3)_
   - 3-12. **`@batch_eval`** _(Gap B)_
   - 3-13. **스트리밍 generator 지원** _(Gap E)_
   - 3-14. **`on_record` 콜백** _(Gap H)_
   - 3-15. **클래스 메서드 지원** _(Gap F)_
   - 3-16. 전체 파라미터 레퍼런스
   - 3-17. **`timeout` 파라미터** _(Gap III)_
   - 3-18. **`eval_context` 컨텍스트 매니저** _(Gap IV)_
   - 3-19. **`EvalMetadata.tokens_used` / `model_name`** _(Gap J)_
   - 3-20. **`eval_context` 동적 필드** _(Gap K)_
   - 3-21. **`@batch_eval` eval_ctx + 항목별 `EvalMetadata`** _(Gap L)_
   - 3-22. **`conversation_eval` `on_flush` 콜백** _(Gap M)_
   - 3-23. **`EvalDecorator` 팩토리** _(Gap N)_
   - 3-24. **Cohere SDK 토큰 자동 추출** _(Gap O)_
   - 3-25. **`EvalMetadata.context` / `ground_truth` 동적 override** _(Gap P)_
   - 3-26. **`@batch_eval` `contexts_arg`** _(Gap Q)_
   - 3-27. **`eval_context` `sample_rate` / `enabled`** _(Gap R)_
   - 3-28. **`EvalDecorator` 확장 — `context()` / `for_rag()` / `for_security()`** _(Gap S)_
   - 3-29. **`flush_all_conversations()`** _(Gap S)_
   - 3-30. **`conversation_eval` `session_score_fn`** _(Gap T)_
   - 3-31. **다중 monitor 지원** _(Gap U)_
   - 3-32. **`@batch_eval` `task_id_fn`** _(Gap V)_
   - 3-33. **`@batch_eval` `expected_tools_arg`** _(Gap W)_
   - 3-34. **`@batch_eval` `timeout`** _(Gap X)_
   - 3-35. **`conversation_eval` `on_turn` 콜백** _(Gap Z)_
   - 3-36. **`EvalDecorator.monitor` 프로퍼티** _(Gap AA)_
   - 3-37. **`EvalMetadata` 추가 필드 — `conversation_turns` / `llm_judge`** _(Gap AB/AC)_
   - 3-38. **`conversation_eval` `ground_truth_arg`** _(Gap AD)_
   - 3-39. **`TaskResult.extra` 자유 형식 메타데이터** _(Gap AE)_
   - 3-40. **`EvalDecorator` 컨텍스트 파라미터 확장** _(Gap AI)_
   - 3-41. **`on_retry` 콜백** _(Gap AJ)_
   - 3-42. **`on_error` 콜백** _(Gap AK)_
   - 3-43. **`EvalMetadata.errors` / `execution_time` 직접 주입** _(Gap AN/AO)_
   - 3-44. **`@batch_eval` `on_batch_complete` 콜백** _(Gap AM)_
   - 3-45. **`TurnMetadata.ground_truth`** _(Gap AP)_
   - 3-46. **`task_id_arg` — 함수 파라미터 자동 탐지** _(Gap AQ)_
   - 3-47. **`agent_eval_with_retry` `jitter`** _(Gap AR)_
   - 3-48. **`eval_context` `task_id_fn`** _(Gap AS)_
   - 3-49. **`EvalDecorator.update_defaults()` / `for_llm_judge()`** _(Gap AT/AU)_
   - 3-50. **스트리밍 generator `EvalMetadata` yield 지원** _(Gap AV)_
   - 3-51. **`conversation_eval` `turn_score_fn`** _(Gap AX)_
   - 3-52. **`conversation_eval` `max_session_seconds`** _(Gap AY)_
4. [메타데이터 병합 우선순위](#4-메타데이터-병합-우선순위)
5. [커버 가능한 지표 범위](#5-커버-가능한-지표-범위)
6. [프레임워크별 지원 범위](#6-프레임워크별-지원-범위)
7. [대시보드 UI 커버 범위](#7-대시보드-ui-커버-범위)
8. [Phoenix 모니터링 UI 커버 범위](#8-phoenix-모니터링-ui-커버-범위)
9. [기존 방식과 혼용 패턴](#9-기존-방식과-혼용-패턴)
10. [적용 방식 선택 기준](#10-적용-방식-선택-기준)

---

## 1. 개요

### 설계 철학

기존 agent-evaluator는 `create_taskresult()` + `monitor.record_task()` 를 명시적으로 호출해야 했습니다. 데코레이터 방식은 이 과정을 함수 정의 시점에 한 줄로 위임합니다.

```python
# 기존 방식 — 평가 코드가 비즈니스 로직에 침투
import time
start = time.perf_counter()
response = my_agent(question)
elapsed = time.perf_counter() - start
result = create_taskresult(task_id="task_001", question=question,
                           response=response, ground_truth=gt,
                           execution_time=elapsed, task_type="qa")
monitor.record_task(result)

# 데코레이터 방식 — 비즈니스 로직 원형 유지
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)
```

### 동작 원리

```
my_agent("질문", ground_truth="정답")
        │
        ▼ wrapper 진입
  ① inspect.signature → question / ground_truth / context / expected_tools 추출
  ② task_id 생성 (task_id_fn 또는 uuid8 자동)
  ③ ContextVar _EvalContext 설치 (get_eval_ctx() 접근용, async 안전)
  ④ start = time.perf_counter()
        │
        ▼ 원본 함수 실행
  raw = func(...)           ← 비즈니스 로직 그대로
        │
        ▼ finally 블록 (성공·실패·예외 모두 실행)
  ⑤ elapsed = perf_counter() - start
  ⑥ _split_raw(raw) → (raw_result, EvalMetadata | None) 분리
  ⑦ _extract_response(raw_result) → response 문자열 변환
  ⑧ 토큰·tool_calls 자동 추출 (OpenAI / Anthropic / LangChain)
  ⑨ create_taskresult_from_execution(...)
  ⑩ _apply_overrides(task_result, decorator_params, eval_ctx, eval_meta)
     우선순위: EvalMetadata > eval_ctx > score_fn/completion_fn > 자동 계산
  ⑪ monitor.record_task(task_result)
        │
        ▼ 호출자에게 raw_result 반환 (EvalMetadata 제거됨, 투명)
```

---

## 2. 설치 및 임포트

```bash
pip install agent-evaluator            # 기본 (Layer 1+2)
pip install "agent-evaluator[serve]"   # 대시보드 포함
pip install "agent-evaluator[otel]"    # Phoenix 모니터링 포함
pip install "agent-evaluator[llm]"     # 실제 LLM 통합 (토큰 자동 추출)
```

```python
# 최상위 패키지에서 직접 임포트 (권장)
from agent_evaluator import (
    PerformanceMonitor,
    agent_eval,           # sync/async 자동 감지 데코레이터 (권장)
    agent_eval_async,     # agent_eval 의 하위 호환 별칭
    agent_eval_with_retry,# 재시도 내장 데코레이터 (sync+async 자동 감지)
    batch_eval,           # List[str] 배치 함수 데코레이터
    conversation_eval,    # 멀티턴 대화 데코레이터
    flush_conversation,   # 세션 명시적 종료
    EvalMetadata,         # 튜플 반환 메타데이터 컨테이너 (단일 태스크)
    TurnMetadata,         # 튜플 반환 메타데이터 컨테이너 (conversation_eval 턴별)
    get_eval_ctx,         # ContextVar 기반 컨텍스트 접근자 (async 안전)
    eval_context,         # 데코레이터 없이 with/async with 블록으로 평가 (Gap IV)
    EvalDecorator,        # 팩토리: 공통 monitor/설정 한 번만 지정 (Gap N)
    flush_all_conversations,  # 모든 활성 대화 세션 일괄 flush (Gap S)
)
```

---

## 3. 적용 방법 레퍼런스

### 3-1. 기본 QA

함수에 `question` / `ground_truth` 파라미터가 있으면 자동 인식됩니다.

```python
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)

qa_agent("한국의 수도는?", ground_truth="서울")
```

### 3-2. 파라미터 이름 커스터마이징

파라미터 이름 탐지 우선순위: `question_arg` 지정 이름 → 첫 번째 positional 인자 → 빈 문자열

```python
@agent_eval(
    monitor,
    task_type="information_retrieval",
    question_arg="query",             # "query" → question
    ground_truth_arg="expected",      # "expected" → ground_truth
    task_id_prefix="search",          # task_id 접두어
)
def search_agent(query: str, expected: str = "") -> str:
    return retriever.search(query)
```

### 3-3. RAG 에이전트 — 할루시네이션 감지 자동 활성

```python
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
# enable_hallucination_detection=True 자동 포함

@agent_eval(
    monitor,
    task_type="information_retrieval",
    context_arg="docs",          # docs 파라미터 → HallucinationDetector
    model_name="gpt-4o-mini",    # Phoenix Top-models 차트 표시
)
def rag_agent(question: str, docs: str = "", ground_truth: str = "") -> str:
    return llm.predict(question, context=docs)
```

### 3-4. 비동기 에이전트 — `@agent_eval` 단일 데코레이터로 통합

`@agent_eval` 이 sync/async 함수를 자동 감지합니다. `@agent_eval_async` 는 하위 호환 별칭으로 유지됩니다.

```python
# 권장 — agent_eval 하나로 통일
@agent_eval(monitor, task_type="qa")
async def async_agent(question: str, ground_truth: str = "") -> str:
    return await llm.apredict(question)

# asyncio.gather 동시 실행 — ContextVar 기반으로 ctx 충돌 없음
results = await asyncio.gather(
    async_agent("q1", ground_truth="a1"),
    async_agent("q2", ground_truth="a2"),
    async_agent("q3", ground_truth="a3"),
)

# 하위 호환 — agent_eval_async 도 동일하게 동작 (내부적으로 agent_eval 호출)
@agent_eval_async(monitor, task_type="qa")
async def legacy_async_agent(question: str, ground_truth: str = "") -> str:
    return await llm.apredict(question)
```

> **비동기 안전성**: `get_eval_ctx()` 가 `contextvars.ContextVar` 기반으로 구현되어 있어,
> `asyncio.create_task()` / `asyncio.gather()` 등 동시 코루틴 환경에서도 각 태스크가 독립된 ctx 를 갖습니다.

### 3-5. LLM API 직접 호출 (OpenAI / Anthropic / Gemini) — 토큰 자동 추출

#### OpenAI

```python
@agent_eval(monitor, task_type="qa", model_name="gpt-4o-mini")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    )
    # ChatCompletion 반환 → response·token·tool_calls 자동 추출
```

#### Anthropic (Claude)

```python
@agent_eval(monitor, task_type="qa", model_name="claude-sonnet-4-6")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
    )
    # anthropic.types.Message 반환 → content[0].text + usage.input_tokens/output_tokens 자동 추출
```

#### Google Gemini

```python
import google.generativeai as genai

@agent_eval(monitor, task_type="qa", model_name="gemini-1.5-flash")
def gemini_agent(question: str, ground_truth: str = "") -> str:
    model = genai.GenerativeModel("gemini-1.5-flash")
    return model.generate_content(question)
    # GenerateContentResponse 반환 → candidates[0].content.parts[0].text
    #   + usage_metadata.prompt_token_count / candidates_token_count 자동 추출
```

**반환값 자동 변환 규칙**

| 반환 타입 | response 추출 | 토큰 추출 |
|-----------|--------------|-----------|
| `openai.ChatCompletion` | `choices[0].message.content` | `usage` 자동 파싱 ✅ |
| `anthropic.types.Message` | `content[0].text` | `usage.input_tokens + output_tokens` ✅ 정확 |
| `google.GenerateContentResponse` | `candidates[0].content.parts[0].text` | `usage_metadata` ✅ 정확 |
| `(raw, EvalMetadata)` | EvalMetadata 분리 후 raw 처리 | raw 기준 ✅ |
| LangChain `AIMessage` | `.content` 속성 | 휴리스틱 |
| `dict` | `answer` > `output` > `result` > `text` 순 | `intermediate_steps` 있으면 tool_calls 추출 ✅ |
| `str` | 그대로 | 휴리스틱 |
| 기타 | `str(raw)` | 휴리스틱 |

### 3-6. 에러 처리

예외 발생 시 `finally` 에서 `success=False` 로 기록 후 예외를 다시 던집니다.

```python
@agent_eval(monitor, task_type="qa")
def unstable_agent(question: str, ground_truth: str = "") -> str:
    raise ConnectionError("API 서버 다운")

try:
    unstable_agent("질문")
except ConnectionError:
    pass
# monitor에 success=False, errors=["API 서버 다운"] 자동 기록
```

### 3-7. `enabled` 플래그

```python
import os

@agent_eval(monitor, task_type="qa",
            enabled=os.getenv("AGENT_EVAL_ENABLED", "true") == "true")
def prod_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)
# AGENT_EVAL_ENABLED=false → 원본 함수만 실행, 평가 완전 우회
```

---

### 3-8. `EvalMetadata` 튜플 반환

함수가 `(response_or_raw, EvalMetadata(...))` 를 반환하면 데코레이터가 메타데이터를 분리해 TaskResult 에 병합합니다. 호출자에게는 `response_or_raw` 만 반환됩니다.

`None` 으로 남긴 필드는 자동 계산값을 유지합니다.

**활성화되는 지표**: `attempts`, `framework`, `expected_tools` (Tool Selection F1), `tool_calls`, `agent_interactions` (Agent Coordination), `chain_steps` (Workflow Execution), `graph_traversal`, `state_transitions`, 커스텀 `completion_score` / `accuracy_score`

```python
from agent_evaluator import EvalMetadata

# 내부 재시도 횟수 정확히 기록
@agent_eval(monitor, task_type="qa")
def retry_agent(question: str, ground_truth: str = "") -> str:
    for n in range(1, 4):
        try:
            resp = llm.predict(question)
            return resp, EvalMetadata(attempts=n)
        except Exception:
            if n == 3: raise

# Tool Selection F1 + 프레임워크 + 체인 단계
@agent_eval(monitor, task_type="tool_use")
def lc_tool_agent(question: str, ground_truth: str = "") -> str:
    result = executor.invoke({"input": question})
    steps = result.get("intermediate_steps", [])
    return result["output"], EvalMetadata(
        framework="langchain",
        expected_tools=["search", "calculator"],
        tool_calls=[{"tool": s[0].tool, "input": s[0].tool_input} for s in steps],
        chain_steps=[
            {"name": s[0].tool, "success": True, "execution_time": 0.0}
            for s in steps
        ],
    )

# CrewAI agent_interactions 수동 주입
@agent_eval(monitor, task_type="tool_use")
def crew_agent(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff({"topic": question})
    return str(result), EvalMetadata(
        framework="crewai",
        agent_interactions=[
            {"from_agent": "researcher", "to_agent": "writer",
             "type": "handoff", "success": True},
        ],
    )

# 커스텀 점수 (ROUGE, 도메인 특화 지표 등)
@agent_eval(monitor, task_type="code_generation")
def code_agent(question: str, ground_truth: str = "") -> str:
    response = llm.predict(question)
    return response, EvalMetadata(
        accuracy_score=ast_similarity(response, ground_truth),
        completion_score=1.0 if response.strip() else 0.0,
    )
```

### 3-9. `get_eval_ctx()` — ContextVar 컨텍스트 접근자

반환값 타입을 바꾸고 싶지 않을 때 사용합니다. 데코레이터 실행 중에만 non-None 을 반환합니다.
`contextvars.ContextVar` 기반이므로 `asyncio.gather()` 동시 실행 환경에서도 태스크 간 ctx 충돌이 없습니다.

```python
from agent_evaluator import get_eval_ctx

@agent_eval(monitor, task_type="tool_use")
def lc_agent(question: str, ground_truth: str = "") -> str:
    result = executor.invoke({"input": question})

    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langchain"
        ctx.attempts = retry_state.count
        ctx.chain_steps = [
            {"name": s[0].tool, "success": True, "execution_time": 0.0}
            for s in result.get("intermediate_steps", [])
        ]

    return result["output"]   # 반환 타입 변경 없음

# LangGraph — graph_traversal / state_transitions 주입
@agent_eval(monitor, task_type="planning")
def graph_agent(question: str, ground_truth: str = "") -> str:
    result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})

    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langgraph"
        ctx.graph_traversal = {
            "nodes_visited": ["router", "search", "synthesizer"],
        }
        ctx.state_transitions = [
            {"from": "router", "to": "search", "trigger": "tool_call"},
        ]

    return result["messages"][-1].content
```

> **`EvalMetadata` vs `get_eval_ctx()` 선택 기준**
> - 반환값 타입을 바꿔도 무방하면 → `EvalMetadata` (더 명시적)
> - 반환값 타입을 절대 바꿀 수 없는 경우 (호출자 타입 검사, 기존 파이프라인 연결) → `get_eval_ctx()`

---

### 3-10. `@agent_eval_with_retry`

재시도 로직을 데코레이터에 내장합니다. 실제 `attempts` 카운트와 `errors` 누적 목록을 정확히 기록합니다. **동기·비동기 함수 모두 지원** (자동 감지).

```python
from agent_evaluator import agent_eval_with_retry

# 동기 — 최대 3회 재시도, 지수 백오프
@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=3,
    retry_on=(ConnectionError, TimeoutError),
    delay=1.0,      # 첫 재시도 전 대기 (초)
    backoff=2.0,    # 지수 백오프 계수: 1s → 2s → 4s
)
def fragile_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)
# 1회 성공 → attempts=1 / 3회 만에 성공 → attempts=3, errors=[오류1, 오류2]

# 비동기 — 타입 자동 감지
@agent_eval_with_retry(monitor, task_type="qa", max_retries=3,
                       retry_on=(ConnectionError,), delay=0.5)
async def async_fragile(question: str, ground_truth: str = "") -> str:
    return await llm.apredict(question)

# EvalMetadata 조합 — 재시도 중 chain_steps도 기록
@agent_eval_with_retry(monitor, task_type="tool_use", max_retries=3)
def complex_agent(question: str, ground_truth: str = "") -> tuple:
    result = executor.invoke({"input": question})
    return result["output"], EvalMetadata(
        framework="langchain",
        chain_steps=[...],
    )
```

**파라미터**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `max_retries` | `3` | 최대 시도 횟수 (첫 시도 포함) |
| `retry_on` | `(Exception,)` | 재시도 트리거 예외 타입 튜플 |
| `delay` | `0.0` | 첫 재시도 전 대기 시간 (초) |
| `backoff` | `1.0` | 지수 백오프 계수 (`1.0` = 고정 딜레이) |

나머지 파라미터(`question_arg`, `framework`, `score_fn`, `task_id_fn` 등)는 `@agent_eval` 과 동일합니다.

---

### 3-11. `@conversation_eval` + `flush_conversation`

멀티턴 대화 함수에 `ConversationSession` 기반 세션 평가를 자동 적용합니다. 동일 `session_id` 로 반복 호출하면 턴을 누적하고, 종료 시 `context_retention`, `topic_coherence`, `progressive_depth`, `session_completion` 을 계산해 `monitor` 에 기록합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation, TurnMetadata

# max_turns=5 도달 시 자동 flush
@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
def chat_agent(question: str, sid: str = "default") -> str:
    return llm.predict(question)

chat_agent("안녕하세요", sid="conv_001")
chat_agent("오늘 날씨는?", sid="conv_001")
chat_agent("내일은요?", sid="conv_001")
# max_turns 미도달 → 수동 flush
flush_conversation("conv_001")
# → ConversationSession.compute_metrics() → monitor 기록

# 비동기 — 타입 자동 감지
@conversation_eval(monitor, session_id_arg="sid", max_turns=3)
async def async_chat(question: str, sid: str = "default") -> str:
    return await llm.apredict(question)
```

#### TurnMetadata — 턴별 메타데이터 주입

함수가 `(response, TurnMetadata(...))` 튜플을 반환하면 데코레이터가 메타데이터를 분리해 `ConversationSession.turn()` 에 전달합니다. 호출자에게는 `response` 만 반환됩니다.

```python
from agent_evaluator import TurnMetadata

@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
def chat_agent(question: str, sid: str = "default") -> str:
    result = llm.predict_with_metadata(question)
    return result["text"], TurnMetadata(
        model="gpt-4o-mini",
        tokens={"input": result["input_tokens"], "output": result["output_tokens"],
                "total": result["input_tokens"] + result["output_tokens"]},
        tool_calls=result.get("tool_calls"),  # None = 저장 안 함
        latency=result["latency_sec"],        # None = perf_counter 자동 측정값 사용
        extra={"confidence": result["confidence"]},
    )
```

#### sample_rate — 세션 단위 샘플링

```python
@conversation_eval(monitor, session_id_arg="sid", max_turns=5, sample_rate=0.3)
def chat_agent(question: str, sid: str = "default") -> str:
    return llm.predict(question)
# 세션 최초 생성 시 30% 확률로 기록, 이후 동일 세션의 모든 턴에 동일 적용
```

**파라미터**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `session_id_arg` | `"session_id"` | 세션 ID 파라미터 이름 |
| `user_arg` | `"question"` | 사용자 메시지 파라미터 이름 |
| `max_turns` | `None` | 이 턴 수 도달 시 자동 flush |
| `flush_on_error` | `True` | 예외 발생 시 세션 자동 flush |
| `sample_rate` | `1.0` | 세션 기록 비율 `[0.0, 1.0]`. 세션 생성 시 결정, 이후 모든 턴에 일괄 적용 |
| `enabled` | `True` | `False` 시 원본 함수만 실행 |

---

### 3-12. `@batch_eval`

`List[str]` 를 받아 `List[str]` 를 반환하는 배치 함수에 평가를 자동 적용합니다. `questions[i]` / `ground_truths[i]` / `responses[i]` 를 묶어 각각 독립된 `TaskResult` 로 기록합니다. 총 실행 시간은 배치 크기로 균등 분할됩니다.

```python
from agent_evaluator import batch_eval
from typing import List

@batch_eval(monitor, task_type="qa", task_id_prefix="qa_batch")
def qa_batch(questions: List[str], ground_truths: List[str] = None) -> List[str]:
    return [llm.predict(q) for q in questions]

qa_batch(
    questions=["한국의 수도는?", "Python 창시자는?"],
    ground_truths=["서울", "귀도 반 로섬"],
)
# → 2개의 TaskResult 가 monitor 에 기록됨
# task_id: qa_batch_{uuid8}_000, qa_batch_{uuid8}_001
```

`ground_truths` 를 생략하면 빈 문자열로 처리되어 Task Completion / Response Quality 등 정답 불필요 지표만 기록됩니다.

```python
# 비동기 배치 — 타입 자동 감지
@batch_eval(monitor, task_type="information_retrieval",
            task_id_prefix="search_batch", framework="langchain")
async def async_batch(questions: List[str]) -> List[str]:
    return await asyncio.gather(*(retriever.aget(q) for q in questions))
```

**파라미터**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `questions_arg` | `"questions"` | 질문 리스트 파라미터 이름. 없으면 첫 번째 positional 사용 |
| `ground_truths_arg` | `"ground_truths"` | 정답 리스트 파라미터 이름 |
| `task_id_prefix` | `"batch"` | 접두어 (`{prefix}_{uuid8}_{i:03d}` 형식) |
| `framework` | `"native"` | 프레임워크 식별자 |
| `model_name` | `""` | LLM 모델명 |
| `score_fn` | `None` | `(response, gt) → float` 커스텀 accuracy |
| `completion_fn` | `None` | `(response, gt) → float` 커스텀 completion |
| `sample_rate` | `1.0` | 호출 단위 샘플링 비율. 배치 전체가 평가되거나 건너뜁니다 |
| `enabled` | `True` | `False` 시 원본 함수만 실행 |

---

### 3-13. 스트리밍 generator 지원

`@agent_eval` 이 `yield` 함수(sync)와 `async yield` 함수(async generator)를 자동 감지합니다. 각 chunk 를 호출자에게 그대로 통과(passthrough)시키면서 generator 가 소진된 시점에 모든 chunk 를 합친 문자열로 `TaskResult` 를 기록합니다.

```python
from typing import Iterator, AsyncIterator

# sync generator
@agent_eval(monitor, task_type="qa")
def stream_agent(question: str, ground_truth: str = "") -> Iterator[str]:
    for chunk in llm.stream(question):
        yield chunk
# 호출자: list(stream_agent("질문", ground_truth="답")) → ["안녕", "하세요", "!"]
# monitor: "안녕하세요!" 로 합쳐진 response 기록

# async generator
@agent_eval(monitor, task_type="qa")
async def async_stream_agent(question: str, ground_truth: str = "") -> AsyncIterator[str]:
    async for chunk in llm.astream(question):
        yield chunk
# 호출자: [c async for c in async_stream_agent("질문", ground_truth="답")]
```

> **주의**: generator 가 중도에 버려지면(호출자가 `break` / GC) `finally` 가 즉시 실행되지 않을 수 있습니다. 정상 소진(exhaustion) 케이스에서만 기록이 보장됩니다.

`EvalMetadata`, `get_eval_ctx()`, `sample_rate`, `on_record` 등 모든 기능이 동일하게 적용됩니다.

---

### 3-14. `on_record` 콜백

`monitor.record_task()` 직후에 호출되는 후크 함수입니다. 임계값 알림, 외부 DB 저장, 커스텀 메트릭 집계 등 사이드이펙트를 데코레이터 레벨에서 처리할 때 사용합니다. 콜백 내부 예외는 무시됩니다.

```python
# 정확도 임계값 알림
@agent_eval(
    monitor,
    task_type="qa",
    on_record=lambda tr: slack.alert(f"정확도 저하: {tr.accuracy_score:.2f}")
                         if tr.accuracy_score < 0.5 else None,
)
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)

# 외부 저장소 연동
def save_to_db(task_result):
    db.insert("evaluations", task_result.to_dict())

@agent_eval(monitor, task_type="qa", on_record=save_to_db)
def db_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)
```

`@agent_eval`, `@agent_eval_async`, `@agent_eval_with_retry`, `@batch_eval` 에서 지원합니다.

---

### 3-15. 클래스 메서드 지원

`@agent_eval` 을 클래스 인스턴스 메서드에 적용할 수 있습니다. `self`/`cls` 는 question 탐지에서 자동으로 제외됩니다.

```python
class QAAgent:
    def __init__(self, model: str):
        self.model = model

    @agent_eval(monitor, task_type="qa")
    def answer(self, question: str, ground_truth: str = "") -> str:
        return llm.predict(question, model=self.model)

    @agent_eval(monitor, task_type="information_retrieval",
                question_arg="query", ground_truth_arg="expected")
    def search(self, query: str, expected: str = "") -> str:
        return retriever.search(query)

agent = QAAgent(model="gpt-4o-mini")
agent.answer("한국의 수도는?", ground_truth="서울")
# question="한국의 수도는?" 정확히 추출 (self 오탐 없음)
```

`@staticmethod` 나 `@classmethod` 에도 동일하게 적용됩니다.

---

### 3-16. 전체 파라미터 레퍼런스

`@agent_eval` 파라미터 (`@agent_eval_async` 는 동일한 서명의 별칭):

```python
@agent_eval(
    monitor,                         # PerformanceMonitor 인스턴스 (필수)
    task_type="qa",                  # qa / coding / code_generation / data_analysis
                                     # document_creation / information_retrieval
                                     # reasoning / creative / planning / tool_use

    # 파라미터 추출
    question_arg="question",         # 질문 파라미터 이름 (기본: "question")
    ground_truth_arg="ground_truth", # 정답 파라미터 이름 (기본: "ground_truth")
    context_arg=None,                # RAG context 파라미터 이름
    expected_tools_arg=None,         # expected_tools 파라미터 이름 → ToolSelectionF1 활성

    # 식별
    framework="native",              # 프레임워크 식별자 → 대시보드 분포 차트
    model_name="",                   # LLM 모델명 → Phoenix Top-models 차트
    task_id_prefix="task",           # task_id 접두어
    task_id_fn=None,                 # (args, kwargs) → str 커스텀 task_id 생성

    # 커스텀 점수
    score_fn=None,                   # (response, gt) → float 커스텀 accuracy
    completion_fn=None,              # (response, gt) → float 커스텀 completion

    # 실행 제어
    sample_rate=1.0,                 # 평가 실행 비율 [0.0, 1.0]. 0.1 = 10%만 평가
    on_record=None,                  # (task_result: TaskResult) → None 콜백. 예외 무시
    timeout=None,                    # 함수 최대 실행 시간(초). 초과 시 TimeoutError 발생 후 기록
    enabled=True,                    # False 시 평가 완전 우회
)
def my_agent(question, ground_truth=""):
    ...
```

---

### 3-17. `timeout` 파라미터

함수 실행이 지정된 시간을 초과하면 `TimeoutError` 를 발생시키고 `success=False`, `errors=["exceeded Xs"]` 로 기록합니다.

```python
# sync — ThreadPoolExecutor 로 비차단 타임아웃 (GIL 제한 있음)
@agent_eval(monitor, task_type="qa", timeout=5.0)
def slow_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)   # 5초 초과 시 TimeoutError

try:
    slow_agent("질문", ground_truth="답")
except TimeoutError:
    pass  # monitor에 success=False, errors=["exceeded 5.0s"] 기록됨

# async — asyncio.wait_for 로 코루틴 단위 타임아웃
@agent_eval(monitor, task_type="qa", timeout=3.0)
async def async_slow(question: str, ground_truth: str = "") -> str:
    return await llm.apredict(question)   # 3초 초과 시 asyncio.TimeoutError
```

`@agent_eval_with_retry` 에서도 동일한 `timeout` 파라미터를 지원합니다. 재시도당 각각 독립적으로 타임아웃이 적용됩니다.

> **주의 (sync)**: `concurrent.futures.ThreadPoolExecutor` 로 구현됩니다. GIL-bound 블로킹 연산(pure Python 루프)은 스레드가 취소되지 않아 실제로는 타임아웃 후에도 계속 실행될 수 있습니다. I/O-bound 작업(HTTP 호출, 파일 읽기)에서 효과적입니다.

---

### 3-18. `eval_context` 컨텍스트 매니저

데코레이터를 붙일 수 없는 코드 블록(서드파티 함수 호출, 동적 생성 함수 등)에 평가를 적용합니다. 동기(`with`)와 비동기(`async with`) 모두 지원합니다.

```python
from agent_evaluator import eval_context

# sync
with eval_context(
    monitor,
    task_type="qa",
    question="한국의 수도는?",
    ground_truth="서울",
    task_id_prefix="ctx",
) as ctx:
    ctx.response = third_party_llm.call("한국의 수도는?")
# __exit__ 시 TaskResult 자동 생성 → monitor.record_task() 호출

# async
async with eval_context(
    monitor,
    task_type="information_retrieval",
    question="최신 뉴스는?",
    model_name="gpt-4o-mini",
) as ctx:
    ctx.response = await async_retriever.fetch("최신 뉴스는?")

# score_fn / on_record 도 지원
with eval_context(
    monitor,
    task_type="qa",
    question=q,
    ground_truth=gt,
    score_fn=lambda r, g: 1.0 if g in r else 0.2,
    on_record=lambda tr: log.info(f"recorded {tr.task_id}"),
) as ctx:
    ctx.response = run_external_pipeline(q)
```

**예외 처리**: `with` 블록 내부에서 예외가 발생해도 `success=False`, `errors=[str(exc)]` 로 기록하고 예외를 다시 전파합니다. `ctx.response` 에 설정된 partial content 도 보존됩니다.

**파라미터**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `monitor` | (필수) | `PerformanceMonitor` 인스턴스 |
| `task_type` | `"qa"` | 태스크 유형 |
| `question` | `""` | 질문 문자열 |
| `ground_truth` | `""` | 정답 문자열 |
| `context` | `None` | RAG context (할루시네이션 감지 활성화용) |
| `expected_tools` | `None` | 기대 도구 목록 (Tool Selection F1 활성화용) |
| `framework` | `"native"` | 프레임워크 식별자 |
| `model_name` | `""` | LLM 모델명 |
| `task_id` | 자동 생성 | 명시적 task_id (지정 시 uuid 생성 생략) |
| `task_id_prefix` | `"eval"` | `task_id` 가 None 일 때 자동 생성 접두어 |
| `score_fn` | `None` | `(response, gt) → float` 커스텀 accuracy |
| `completion_fn` | `None` | `(response, gt) → float` 커스텀 completion |
| `on_record` | `None` | `(task_result: TaskResult) → None` 콜백 |

---

### 3-19. `EvalMetadata.tokens_used` / `model_name` — 비표준 LLM 토큰 주입

OpenAI / Anthropic / Gemini / Cohere 외 LLM(로컬 모델, Mistral fine-tune 등)에서 정확한 토큰 수를 주입합니다.

```python
# EvalMetadata 튜플 반환
@agent_eval(monitor, task_type="qa")
def custom_llm(question: str, ground_truth: str = "") -> tuple:
    result = my_llm_client.chat(question)
    return result["text"], EvalMetadata(
        tokens_used={"input": result["prompt_tokens"],
                     "output": result["completion_tokens"],
                     "total": result["total_tokens"]},
        model_name="llama-3-8b-instruct",   # Phoenix Top-models 차트에 표시
    )

# get_eval_ctx() 방식 (반환값 타입 변경 없이)
@agent_eval(monitor, task_type="qa")
def ctx_custom_llm(question: str, ground_truth: str = "") -> str:
    result = my_llm_client.chat(question)
    ctx = get_eval_ctx()
    if ctx:
        ctx.tokens_used = {"input": result["prompt_tokens"],
                           "output": result["completion_tokens"],
                           "total": result["total_tokens"]}
        ctx.model_name = "llama-3-8b-instruct"
    return result["text"]
```

**우선순위**: `EvalMetadata.tokens_used` > eval_ctx.tokens_used > Cohere/Gemini/Anthropic/OpenAI 자동 추출 > 휴리스틱

---

### 3-20. `eval_context` 동적 필드 재설정

`question`, `ground_truth`, `response` 속성을 `with` 블록 내에서 자유롭게 재설정할 수 있습니다. 생성 시점에 알 수 없는 경우 유용합니다.

```python
with eval_context(monitor, task_type="qa") as ctx:
    raw_q = get_next_question_from_queue()
    ctx.question = preprocess(raw_q)   # 블록 내부에서 재설정
    ctx.ground_truth = lookup_gt(raw_q)
    ctx.response = third_party_llm.call(ctx.question)
```

생성자에서 지정한 값은 초기값으로 사용되며, 블록 내에서 재설정하면 __exit__ 시 최종값이 기록됩니다.

---

### 3-21. `@batch_eval` — 항목별 `EvalMetadata` + `get_eval_ctx()`

배치 함수 내부에서 `get_eval_ctx()`가 동작하며, 반환 리스트의 각 항목을 `(response, EvalMetadata)` 튜플로 반환하면 항목별로 다른 메타데이터를 기록할 수 있습니다.

```python
# 항목별 EvalMetadata
@batch_eval(monitor, task_type="tool_use", task_id_prefix="tb")
def tool_batch(questions: List[str]) -> List[tuple]:
    results = []
    for q in questions:
        r = executor.invoke({"input": q})
        steps = r.get("intermediate_steps", [])
        results.append((r["output"], EvalMetadata(
            framework="langchain",
            chain_steps=[{"name": s[0].tool, "success": True,
                          "execution_time": 0.0} for s in steps],
        )))
    return results

# get_eval_ctx() — 배치 전체 공통 메타데이터
@batch_eval(monitor, task_type="qa", task_id_prefix="cb")
def ctx_batch(questions: List[str]) -> List[str]:
    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langchain"   # 모든 항목에 공통 적용
    return [llm.predict(q) for q in questions]
```

---

### 3-22. `@conversation_eval` `on_flush` 콜백

세션이 flush 될 때 호출되는 콜백입니다. `max_turns` 자동 flush와 `flush_conversation()` 수동 flush 모두 트리거됩니다.

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=5,
    on_flush=lambda session_id: slack.alert(f"대화 세션 완료: {session_id}"),
)
def chat(question: str, sid: str = "default") -> str:
    return llm.predict(question)

# 콜백 시그니처: (session_id: str) → None
# 예외 발생 시 무시됨 (평가 기록에 영향 없음)
```

---

### 3-23. `EvalDecorator` 팩토리

동일한 `monitor`와 공통 설정을 공유하는 함수가 많을 때 반복을 줄입니다.

```python
from agent_evaluator import EvalDecorator

# 공통 설정 한 번만
eval = EvalDecorator(
    monitor,
    framework="langchain",
    model_name="gpt-4o-mini",
    sample_rate=0.5,
    on_record=lambda tr: log.info(f"recorded {tr.task_id}"),
)

# 각 함수에 간결하게 적용
@eval(task_type="qa")
def qa_agent(question, ground_truth=""): ...

@eval(task_type="tool_use", expected_tools_arg="expected")
def tool_agent(question, expected=None, ground_truth=""): ...

@eval.with_retry(task_type="qa", max_retries=3, retry_on=(ConnectionError,))
def fragile_agent(question, ground_truth=""): ...

@eval.batch(task_type="qa")
def batch_agent(questions, ground_truths=None): ...

@eval.conversation(session_id_arg="sid", max_turns=5)
def chat(question, sid="default"): ...
```

**공통으로 전달되는 파라미터**: `framework`, `model_name`, `sample_rate`, `enabled`, `on_record`, `score_fn`, `completion_fn`, `task_id_prefix`, `question_arg`, `ground_truth_arg`, `context_arg`, `expected_tools_arg`, `task_id_fn`, `timeout` _(Gap AI)_

**주의**: `conversation_eval`에는 `framework`/`model_name`/`score_fn`/`completion_fn`/`on_record` 등이 전달되지 않습니다 (미지원). `sample_rate`와 `enabled`만 전달됩니다. 전체 지원 매트릭스는 [3-40](#3-40-evaldecorator-컨텍스트-파라미터-확장) 참조.

---

### 3-24. Cohere SDK 토큰 자동 추출

Cohere SDK v5+ (`cohere>=5.0`) 응답 객체를 반환하면 토큰 수와 응답 텍스트가 자동 추출됩니다.

```python
import cohere

co = cohere.ClientV2()

@agent_eval(monitor, task_type="qa", model_name="command-r-plus")
def cohere_agent(question: str, ground_truth: str = ""):
    return co.chat(
        model="command-r-plus",
        messages=[{"role": "user", "content": question}],
    )
    # NonStreamedChatResponse 반환 → text + meta.tokens 자동 추출
    # tokens_used = {"input": N, "output": M, "total": N+M}
```

**반환값 자동 변환 규칙 (업데이트)**

| 반환 타입 | response 추출 | 토큰 추출 |
|-----------|--------------|-----------|
| `openai.ChatCompletion` | `choices[0].message.content` | `usage.prompt_tokens / completion_tokens` ✅ |
| `mistralai.ChatCompletion` | `choices[0].message.content` | `usage.prompt_tokens / completion_tokens` ✅ (OpenAI-호환) |
| `anthropic.types.Message` | `content[0].text` | `usage.input_tokens + output_tokens` ✅ |
| `google.GenerateContentResponse` | `candidates[0].content.parts[0].text` | `usage_metadata` ✅ |
| `cohere.NonStreamedChatResponse` | `.text` | `meta.tokens.input_tokens / output_tokens` ✅ |
| `(raw, EvalMetadata)` | EvalMetadata 분리 후 raw 처리 | EvalMetadata.tokens_used 우선 ✅ |
| LangChain `AIMessage` | `.content` | 휴리스틱 |
| `dict` | `answer > output > result > text` 순 | `intermediate_steps` 있으면 tool_calls 추출 ✅ |
| `str` | 그대로 | 휴리스틱 |
| 기타 | `str(raw)` | 휴리스틱 |

---

### 3-25. `EvalMetadata.context` / `ground_truth` 동적 override

`EvalMetadata` 또는 `get_eval_ctx()` 로 `context` / `ground_truth` 를 함수 실행 시점에 동적으로 재정의할 수 있습니다 (Gap P).

```python
# 경우 1: EvalMetadata 튜플 반환
@agent_eval(monitor, task_type="information_retrieval")
def rag_agent(question: str, ground_truth: str = "원본 정답") -> tuple:
    doc = retriever.search(question)      # 런타임에 context 확정
    response = llm.predict(question, doc)
    return response, EvalMetadata(
        context=doc,                      # 런타임에 확정된 context → 할루시네이션 감지 활성
        ground_truth="동적 정답",          # 런타임 ground_truth 재정의
    )
    # → HallucinationDetector에 doc 전달, accuracy_score = 동적 정답 기준으로 계산

# 경우 2: get_eval_ctx()
@agent_eval(monitor, task_type="information_retrieval")
def rag_agent2(question: str, ground_truth: str = "") -> str:
    ctx = get_eval_ctx()
    doc = retriever.search(question)
    if ctx:
        ctx.context = doc
        ctx.ground_truth = "런타임 정답"
    return llm.predict(question, doc)
```

**우선순위**: `EvalMetadata` > `eval_ctx` > `_resolve_args` (파라미터 탐지)

---

### 3-26. `@batch_eval` `contexts_arg`

배치 함수에서 항목별 RAG context 를 `contexts_arg` 로 지정하면 할루시네이션 감지가 아이템별로 활성화됩니다 (Gap Q).

```python
monitor_rag = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@batch_eval(
    monitor_rag,
    task_type="information_retrieval",
    contexts_arg="contexts",             # List[str] 파라미터 이름
    task_id_prefix="rag_batch",
)
def rag_batch(
    questions: List[str],
    ground_truths: List[str] = None,
    contexts: List[str] = None,          # 항목별 RAG context
) -> List[str]:
    return [llm.predict(q, c) for q, c in zip(questions, contexts or [])]

rag_batch(
    questions=["서울 인구는?", "한국 수도는?"],
    ground_truths=["950만", "서울"],
    contexts=["서울특별시 인구는 약 950만...", "대한민국의 수도는 서울..."],
)
# → 각 TaskResult.context = contexts[i], 할루시네이션 감지 활성화
```

---

### 3-27. `eval_context` `sample_rate` / `enabled`

`eval_context` 컨텍스트 매니저에도 데코레이터와 동일한 `sample_rate` / `enabled` 플래그를 적용할 수 있습니다 (Gap R).

```python
EVAL_ENABLED = os.getenv("AGENT_EVAL_ENABLED", "true").lower() == "true"
SAMPLE_RATE = float(os.getenv("AGENT_EVAL_RATE", "1.0"))

# enabled=False → __enter__ 에서 즉시 _skip=True, 기록 없이 블록 실행
with eval_context(monitor, task_type="qa",
                  question=q, ground_truth=gt,
                  enabled=EVAL_ENABLED,
                  sample_rate=SAMPLE_RATE) as ctx:
    ctx.response = external_llm.call(q)
```

`sample_rate=0.1` 이면 블록 10건 중 1건만 기록됩니다.

---

### 3-28. `EvalDecorator` 확장 — `context()` / `for_rag()` / `for_security()`

`EvalDecorator` 가 세 가지 편의 인터페이스를 추가로 제공합니다 (Gap S).

**`eval.context()` — eval_context 컨텍스트 매니저 반환**

```python
eval = EvalDecorator(monitor, framework="native", model_name="gpt-4o-mini")

with eval.context(task_type="qa", question=q, ground_truth=gt) as ctx:
    ctx.response = external_fn(q)
# → eval_context(monitor, "qa", framework="native", model_name="gpt-4o-mini", ...)
```

공통 설정(framework, model_name, sample_rate 등)이 자동으로 상속됩니다.

**`EvalDecorator.for_rag()` — RAG 최적화 팩토리**

```python
eval_rag = EvalDecorator.for_rag(output_dir="results/")
# → PerformanceMonitor.for_rag_evaluation() 으로 monitor 자동 생성 (hallucination 기본 활성)

@eval_rag(task_type="information_retrieval", context_arg="ctx")
def rag_agent(question, ctx="", ground_truth=""): ...
```

**`EvalDecorator.for_security()` — 보안 최적화 팩토리**

```python
eval_sec = EvalDecorator.for_security(output_dir="results/")
# → PerformanceMonitor.for_secure_agents() 으로 monitor 자동 생성 (보안 지표 기본 활성)

@eval_sec(task_type="tool_use")
def secure_agent(question, ground_truth=""): ...
```

---

### 3-29. `flush_all_conversations()`

프로세스 종료 직전 또는 테스트 클린업 시 모든 활성 `conversation_eval` 세션을 일괄 flush 합니다 (Gap S).

```python
from agent_evaluator import flush_all_conversations

# 방법 1: atexit 등록
import atexit
atexit.register(flush_all_conversations)

# 방법 2: 테스트 teardown
def teardown_module():
    n = flush_all_conversations()
    print(f"flushed {n} sessions")

# 방법 3: 직접 호출 (반환값 = flush 된 세션 수)
n = flush_all_conversations()
```

`flush_conversation(session_id)` 와 달리 세션 ID 를 알 필요 없이 모든 미완료 세션을 한 번에 종료합니다.

---

### 3-30. `conversation_eval` `session_score_fn`

세션 flush 시 `ConversationMetrics` 를 받아 `overall_score` 를 커스터마이징할 수 있습니다 (Gap T).

```python
def my_session_scorer(metrics) -> float:
    """topic_coherence 와 context_retention 을 강조한 커스텀 점수."""
    return 0.6 * metrics.topic_coherence + 0.4 * metrics.context_retention

@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=5,
    session_score_fn=my_session_scorer,  # ConversationMetrics → float
)
def chat(question: str, sid: str = "conv_001") -> str:
    return llm.predict(question)

chat("안녕", sid="conv_001")
chat("날씨?", sid="conv_001")
flush_conversation("conv_001")
# → monitor.conversation_sessions[-1].metrics.overall_score = my_session_scorer(metrics)
```

`session_score_fn` 이 `None` 을 반환하면 자동 계산값이 유지됩니다.

---

### 3-31. 다중 monitor 지원

`@agent_eval` / `@agent_eval_with_retry` / `@batch_eval` / `eval_context` 의 `monitor` 파라미터에 리스트를 전달하면 모든 monitor 에 동시 기록됩니다 (Gap U).

```python
monitor_a = PerformanceMonitor(output_dir="results/project_a/")
monitor_b = PerformanceMonitor(output_dir="results/project_b/")

@agent_eval([monitor_a, monitor_b], task_type="qa", task_id_prefix="shared")
def shared_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)

shared_agent("질문", ground_truth="정답")
# → monitor_a, monitor_b 양쪽에 동일한 TaskResult 기록
```

**활용 패턴**

```python
# A/B 테스트: 두 모니터로 두 모델을 동시 비교
monitor_gpt4   = PerformanceMonitor(output_dir="results/gpt4/")
monitor_claude = PerformanceMonitor(output_dir="results/claude/")

@agent_eval([monitor_gpt4, monitor_claude], task_type="qa")
def dual_record_agent(question, ground_truth=""): ...
```

`eval_context` 에도 동일하게 적용됩니다:

```python
with eval_context([monitor_a, monitor_b], task_type="qa", question=q) as ctx:
    ctx.response = external_fn(q)
```

---

### 3-32. `@batch_eval` `task_id_fn` — 항목별 커스텀 task_id

배치 함수의 각 항목에 커스텀 `task_id` 를 부여합니다 (Gap V). 기본값은 `{prefix}_{uuid8}_{index:03d}` 입니다.

```python
@batch_eval(
    monitor,
    task_type="qa",
    task_id_fn=lambda i, q, gt: f"item_{i}_{q[:6]}",  # (index, question, gt) → str
    task_id_prefix="fallback",  # task_id_fn 예외 시 fallback prefix 로 사용
)
def batch_agent(questions: List[str], ground_truths: List[str] = None) -> List[str]:
    return [llm.predict(q) for q in questions]

batch_agent(["Q1 abcdef", "Q2 xyz"], ground_truths=["A1", "A2"])
# task_id: "item_0_Q1 abc", "item_1_Q2 xyz"
```

**시그니처**: `task_id_fn(index: int, question: str, ground_truth: str) → str`

`task_id_fn` 이 예외를 발생시키면 `{task_id_prefix}_{uuid8}_{index:03d}` 로 자동 fallback 됩니다.

---

### 3-33. `@batch_eval` `expected_tools_arg` — 항목별 기대 도구 리스트

배치 함수의 각 항목에 `expected_tools` 를 주입해 Tool Selection F1 을 항목별로 계산합니다 (Gap W).

```python
@batch_eval(
    monitor,
    task_type="tool_use",
    expected_tools_arg="expected_tools",   # List[List[str]] 파라미터 이름
    task_id_prefix="tool_batch",
)
def tool_batch(
    questions: List[str],
    ground_truths: List[str] = None,
    expected_tools: List[List[str]] = None,   # 항목별 기대 도구 리스트
) -> List[str]:
    return [executor.run(q) for q in questions]

tool_batch(
    questions=["검색해줘", "계산해줘"],
    ground_truths=["결과1", "결과2"],
    expected_tools=[["search"], ["calculator", "search"]],
    # → TaskResult[0].expected_tools = ["search"]
    # → TaskResult[1].expected_tools = ["calculator", "search"]
)
```

---

### 3-34. `@batch_eval` `timeout` — 배치 함수 전체 타임아웃

배치 함수 전체 실행에 타임아웃을 적용합니다 (Gap X). 초과 시 `TimeoutError` 가 발생하고 `success=False` 로 기록됩니다.

```python
@batch_eval(monitor, task_type="qa", timeout=10.0)   # 배치 전체 10초 제한
def slow_batch(questions: List[str]) -> List[str]:
    return [heavy_llm.predict(q) for q in questions]

# async 배치 함수도 동일하게 지원 (asyncio.wait_for 사용)
@batch_eval(monitor, task_type="qa", timeout=5.0)
async def async_slow_batch(questions: List[str]) -> List[str]:
    return [await llm.apredict(q) for q in questions]
```

> **주의**: 타임아웃은 배치 함수 **전체** 에 적용됩니다. 항목별 개별 타임아웃이 필요하면 함수 내부에서 직접 처리하세요.

---

### 3-35. `conversation_eval` `on_turn` 콜백

각 턴이 기록될 때마다 호출되는 콜백입니다 (Gap Z). `on_flush` 는 세션 종료 시 한 번 호출되지만 `on_turn` 은 **매 턴마다** 호출됩니다.

```python
def turn_logger(session_id: str, user: str, agent: str, metadata: dict):
    print(f"[{session_id}] user={user!r} | agent={agent!r} | latency={metadata.get('latency', 0):.3f}s")

@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=5,
    on_turn=turn_logger,  # (session_id, user, agent_response, metadata) → None
)
def chat(question: str, sid: str = "conv_001") -> str:
    return llm.predict(question)
```

**콜백 시그니처**: `(session_id: str, user: str, agent_response: str, metadata: dict) → None`

`metadata` 딕셔너리에는 `latency` (초 단위)와 `ground_truth` (설정된 경우)가 포함됩니다.

예외 발생 시 `logger.debug` 로 무시되며 평가 기록에 영향을 주지 않습니다.

---

### 3-36. `EvalDecorator.monitor` 프로퍼티

`EvalDecorator` 인스턴스에서 내부 `PerformanceMonitor` 에 직접 접근합니다 (Gap AA). `eval.monitor.generate_report()` 처럼 팩토리를 거치지 않고 monitor 를 재사용할 수 있습니다.

```python
eval = EvalDecorator(monitor, framework="langchain")

@eval(task_type="qa")
def qa_agent(question, ground_truth=""): ...

# monitor 직접 접근
report = eval.monitor.generate_report()
eval.monitor.save_to_file("results")

# for_rag / for_security 팩토리와 함께 사용
eval_rag = EvalDecorator.for_rag(output_dir="results/")
eval_rag.monitor.save_to_file("rag_results")  # 내부 monitor 접근
```

---

### 3-37. `EvalMetadata` 추가 필드 — `conversation_turns` / `llm_judge`

`EvalMetadata` 와 `get_eval_ctx()` 에 두 가지 필드가 추가되었습니다 (Gap AB/AC).

**`conversation_turns` — 대화 턴 기록 수동 주입**

`@conversation_eval` 을 사용하지 않고 멀티턴 대화 데이터를 수동으로 주입합니다.

```python
@agent_eval(monitor, task_type="qa")
def multiturn_agent(question: str, history: list = None, ground_truth: str = "") -> tuple:
    response = llm.chat(question, history=history)
    return response, EvalMetadata(
        conversation_turns=[
            {"user": h["user"], "agent": h["assistant"]} for h in (history or [])
        ] + [{"user": question, "agent": response}]
    )
```

**`llm_judge` — LLM Judge 점수 수동 주입**

`enable_llm_judge=True` 없이 외부에서 계산한 LLM Judge 점수를 직접 기록합니다.

```python
@agent_eval(monitor, task_type="qa")
def agent_with_judge(question: str, ground_truth: str = "") -> tuple:
    response = llm.predict(question)
    judge_score = my_llm_judge.evaluate(question, response)   # 외부 LLM Judge
    return response, EvalMetadata(
        llm_judge={
            "completeness": judge_score["completeness"],
            "relevance": judge_score["relevance"],
            "factual_consistency": judge_score["factual_consistency"],
            "overall": judge_score["overall"],
        }
    )
```

`get_eval_ctx()` 방식도 동일하게 지원됩니다:

```python
ctx = get_eval_ctx()
if ctx:
    ctx.conversation_turns = [...]
    ctx.llm_judge = {"overall": 0.92}
```

---

### 3-38. `conversation_eval` `ground_truth_arg`

각 턴의 `ground_truth` 파라미터 이름을 지정합니다 (Gap AD). 지정하면 해당 파라미터 값이 `metadata["ground_truth"]` 로 저장되고 `on_turn` 콜백에도 전달됩니다.

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    ground_truth_arg="expected",   # "expected" 파라미터 → ground_truth 로 매핑
    max_turns=5,
    on_turn=lambda sid, u, a, meta: print(meta.get("ground_truth")),
)
def chat(question: str, expected: str = "", sid: str = "conv_001") -> str:
    return llm.predict(question)

chat("서울의 수도는?", expected="서울", sid="s1")
# → on_turn: meta["ground_truth"] = "서울"
```

기본값은 `"ground_truth"` 입니다 (`ground_truth_arg="ground_truth"` 생략 가능).

---

### 3-39. `TaskResult.extra` — 자유 형식 사용자 메타데이터

`TaskResult` 에 도메인별 임의 메타데이터를 첨부합니다 (Gap AE). 기존 24개 필드에 포함되지 않는 정보를 JSON-직렬화 가능한 딕셔너리로 저장합니다.

```python
# EvalMetadata 튜플 반환
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = llm.predict(question)
    return response, EvalMetadata(
        extra={
            "intent": "product_search",
            "source": "api_v2",
            "ab_variant": "B",
            "user_tier": "premium",
        }
    )

# get_eval_ctx() 방식
@agent_eval(monitor, task_type="tool_use")
def tool_agent(question: str, ground_truth: str = "") -> str:
    ctx = get_eval_ctx()
    if ctx:
        ctx.extra = {"experiment_id": "exp_001", "region": "kr"}
    return executor.run(question)
```

`extra` 는 `TaskResult.to_dict()` / `from_dict()` 왕복 시 그대로 보존되며, `agent-eval dashboard` 의 태스크 상세 테이블에서도 표시됩니다.

---

### 3-40. `EvalDecorator` 컨텍스트 파라미터 확장

`EvalDecorator` 생성 시 `question_arg`, `ground_truth_arg`, `context_arg`, `expected_tools_arg`, `task_id_fn`, `timeout` 을 기본값으로 지정할 수 있습니다 (Gap AI). 이 값들은 `@eval(task_type=...)` 으로 데코레이터를 생성할 때 자동으로 상속됩니다.

```python
eval = EvalDecorator(
    monitor,
    framework="langchain",
    model_name="gpt-4o-mini",
    # Gap AI 추가 파라미터
    question_arg="query",            # 모든 함수의 question 파라미터 이름
    ground_truth_arg="expected",     # 모든 함수의 ground_truth 파라미터 이름
    context_arg="docs",              # 모든 함수의 context 파라미터 이름
    expected_tools_arg="tools",      # 모든 함수의 expected_tools 파라미터 이름
    task_id_fn=lambda args, kw: kw.get("task_id") or f"task_{args[0][:8]}",
    timeout=30.0,                    # 모든 함수에 공통 타임아웃
)

@eval(task_type="information_retrieval")
def rag_agent(query: str, docs: str = "", expected: str = "", tools: list = None):
    return chain.invoke({"query": query, "context": docs})

@eval(task_type="tool_use")
def tool_agent(query: str, tools: list = None, expected: str = ""):
    return executor.run(query)

# 각 함수별 override 도 가능
@eval(task_type="qa", timeout=5.0, question_arg="q")  # 이 함수에서만 timeout=5s
def fast_agent(q: str, expected: str = ""):
    return llm.predict(q)
```

**전달되는 파라미터 전체 목록**

| 파라미터 | `agent_eval` | `with_retry` | `batch` | `conversation` |
|---------|:---:|:---:|:---:|:---:|
| `framework` | ✅ | ✅ | ✅ | — |
| `model_name` | ✅ | ✅ | ✅ | — |
| `sample_rate` | ✅ | ✅ | ✅ | ✅ |
| `enabled` | ✅ | ✅ | ✅ | ✅ |
| `score_fn` | ✅ | ✅ | ✅ | — |
| `completion_fn` | ✅ | ✅ | ✅ | — |
| `on_record` | ✅ | ✅ | ✅ | — |
| `task_id_prefix` | ✅ | ✅ | ✅ | — |
| `question_arg` | ✅ | ✅ | — | — |
| `ground_truth_arg` | ✅ | ✅ | — | — |
| `context_arg` | ✅ | ✅ | — | — |
| `expected_tools_arg` | ✅ | ✅ | — | — |
| `task_id_fn` | ✅ | ✅ | — | — |
| `timeout` | ✅ | ✅ | ✅ | — |
| `on_error` | ✅ | ✅ | — | — |
| `task_id_arg` | ✅ | ✅ | — | — |

---

### 3-41. `on_retry` 콜백 — 재시도 중 실시간 알림

`agent_eval_with_retry` 에서 재시도가 발생할 때마다 호출됩니다 (Gap AJ). `on_record` 는 최종 결과만 받지만 `on_retry` 는 **각 실패마다** 호출됩니다.

```python
retry_log = []

@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=3,
    retry_on=(ConnectionError, TimeoutError),
    delay=1.0,
    on_retry=lambda attempt, error: retry_log.append(f"시도 {attempt}: {error}"),
)
def fragile_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)   # 실패 시 on_retry 콜백 호출 후 재시도
```

**콜백 시그니처**: `(attempt: int, error: str) → None`

- `attempt`: 현재까지 수행한 시도 횟수 (1부터 시작)
- `error`: 예외의 문자열 표현

예외 발생 시 `logger.debug` 로 무시됩니다.

---

### 3-42. `on_error` 콜백 — 에러 전용 알림

`@agent_eval` / `@agent_eval_with_retry` 에서 `has_error=True` 인 경우에만 호출됩니다 (Gap AK). `on_record` 는 성공·실패 모두 호출되므로, 에러만 처리하려면 `on_record` 에서 `task_result.success` 를 확인해야 했습니다. `on_error` 는 이를 단순화합니다.

```python
import logging
alert_log = logging.getLogger("alerts")

@agent_eval(
    monitor,
    task_type="qa",
    on_error=lambda tr: alert_log.warning(
        "평가 실패 — task_id=%s errors=%s", tr.task_id, tr.errors
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)

# on_error 는 has_error=True 일 때만 호출, on_record 는 항상 호출
@agent_eval(
    monitor,
    task_type="qa",
    on_record=lambda tr: metrics.inc("eval.total"),
    on_error=lambda tr: metrics.inc("eval.error"),
)
def dual_callback_agent(question: str, ground_truth: str = "") -> str: ...
```

**콜백 시그니처**: `(task_result: TaskResult) → None`

`task_result.errors` 에 에러 메시지가 담겨 있습니다. 예외 발생 시 무시됩니다.

---

### 3-43. `EvalMetadata.errors` / `execution_time` 직접 주입

**`errors` 직접 주입** _(Gap AN)_ — 수동 재시도 구현 시 에러 목록을 직접 주입합니다. `@agent_eval_with_retry` 를 사용하지 않고 재시도 로직을 직접 구현할 때 유용합니다.

```python
@agent_eval(monitor, task_type="qa")
def manual_retry_agent(question: str, ground_truth: str = "") -> tuple:
    errors = []
    for n in range(1, 4):
        try:
            resp = llm.predict(question)
            return resp, EvalMetadata(attempts=n, errors=errors)
        except ConnectionError as e:
            errors.append(str(e))
    raise RuntimeError("모든 시도 실패")
```

**`execution_time` override** _(Gap AO)_ — 외부 측정값(분산 추적, DB 로그 등)으로 `perf_counter` 측정값을 대체합니다.

```python
@agent_eval(monitor, task_type="qa")
def external_timed_agent(question: str, ground_truth: str = "") -> tuple:
    t0 = tracer.now()
    resp = llm.predict(question)
    return resp, EvalMetadata(
        execution_time=tracer.elapsed_since(t0),  # 분산 추적 측정값
    )
```

`get_eval_ctx()` 방식도 동일하게 지원됩니다:

```python
ctx = get_eval_ctx()
if ctx:
    ctx.errors = ["1차 시도 실패: timeout"]
    ctx.execution_time = distributed_trace.latency
```

---

### 3-44. `@batch_eval` `on_batch_complete` 콜백

배치 함수 내 모든 항목이 기록된 후 `List[TaskResult]` 를 한 번에 받는 콜백입니다 (Gap AM). 현재 `on_record` 는 항목별로 호출되므로, 배치 단위 분석·저장에는 `on_batch_complete` 가 적합합니다.

```python
def batch_reporter(results):
    accs = [r.accuracy_score for r in results]
    print(f"배치 완료 — {len(results)}건, 평균 accuracy={sum(accs)/len(accs):.2f}")
    # DB 저장, Slack 알림 등

@batch_eval(
    monitor,
    task_type="qa",
    on_batch_complete=batch_reporter,   # List[TaskResult] → None
)
def qa_batch(questions, ground_truths=None):
    return [llm.predict(q) for q in questions]
```

**콜백 시그니처**: `(results: List[TaskResult]) → None`

`on_record` 와 달리 항목 수만큼이 아닌 배치 전체에 대해 1회 호출됩니다. 예외 발생 시 무시됩니다.

---

### 3-45. `TurnMetadata.ground_truth`

`@conversation_eval` 로 감싼 함수에서 턴별 `ground_truth` 를 `TurnMetadata` 로 직접 지정합니다 (Gap AP). `ground_truth_arg` 파라미터 기반 추출보다 높은 우선순위를 가집니다.

```python
@conversation_eval(monitor, session_id_arg="sid", max_turns=3,
                   on_turn=lambda s, u, a, m: print(m.get("ground_truth")))
def qa_chat(question: str, sid: str = "default") -> tuple:
    response = llm.predict(question)
    expected = lookup_expected_answer(question)   # 런타임에 확정
    return response, TurnMetadata(
        ground_truth=expected,    # on_turn 콜백에서 metadata["ground_truth"] 로 접근
        model="gpt-4o-mini",
    )
```

`TurnMetadata.ground_truth` 가 설정되면 `ground_truth_arg` 로 추출된 값을 덮어씁니다.

---

### 3-46. `task_id_arg` — 함수 파라미터에서 task_id 자동 탐지

함수에 `task_id` 파라미터가 있을 때 자동으로 이를 task_id 로 사용합니다 (Gap AQ). 기존에는 `task_id_fn=lambda a, kw: kw.get("task_id")` 로 우회해야 했습니다.

```python
@agent_eval(
    monitor,
    task_type="qa",
    task_id_arg="task_id",   # "task_id" 파라미터를 task_id 로 사용
)
def agent(question: str, task_id: str = "", ground_truth: str = "") -> str:
    return llm.predict(question)

agent("질문", task_id="my_explicit_id_001")
# → TaskResult.task_id = "my_explicit_id_001"
```

**우선순위**: `task_id_arg` > `task_id_fn` > 자동 생성 (`{prefix}_{uuid8}`)

`task_id_arg` 로 지정한 파라미터 값이 빈 문자열이거나 None 이면 다음 우선순위로 fallback 됩니다.

---

### 3-47. `agent_eval_with_retry` `jitter`

재시도 딜레이에 무작위 편차를 추가합니다 (Gap AR). 다수의 인스턴스가 동시에 재시도할 때 thundering herd 문제를 방지합니다.

```python
@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=5,
    retry_on=(ConnectionError,),
    delay=2.0,
    backoff=2.0,
    jitter=True,    # 실제 딜레이 = random.uniform(0, delay * backoff^n)
)
def prod_agent(question: str, ground_truth: str = "") -> str:
    return llm.predict(question)
```

`jitter=True` 이면 각 재시도 딜레이가 `random.uniform(0.0, wait)` 로 무작위화됩니다. `jitter=False` (기본)이면 기존 동작(고정 딜레이 × backoff)을 유지합니다.

---

### 3-48. `eval_context` `task_id_fn`

`eval_context` 에 `task_id_fn` 를 지정하면 `__enter__` 시점에 함수를 호출해 task_id 를 생성합니다 (Gap AS). `task_id` 직접 지정이 불가능할 때 유용합니다.

```python
import uuid

with eval_context(
    monitor,
    task_type="qa",
    question="질문",
    task_id_fn=lambda: f"req_{uuid.uuid4().hex[:12]}",  # () → str
) as ctx:
    ctx.response = external_fn("질문")
```

**우선순위**: `task_id` (직접 지정) > `task_id_fn` > `{prefix}_{uuid8}` 자동 생성

---

### 3-49. `EvalDecorator.update_defaults()` / `for_llm_judge()`

**`update_defaults()` — 생성 후 기본값 부분 변경** _(Gap AT)_

```python
eval = EvalDecorator(monitor, model_name="gpt-4o-mini", timeout=30.0)

# 이후 모델 교체 — EvalDecorator 재생성 불필요
eval.update_defaults(model_name="gpt-4-turbo")
eval.update_defaults(timeout=60.0, task_id_prefix="v2")

# 체이닝 지원
eval.update_defaults(framework="langchain").update_defaults(sample_rate=0.5)
```

반환값은 `self` 이므로 체이닝할 수 있습니다. 이후 생성되는 모든 데코레이터에 변경사항이 적용됩니다.

**`for_llm_judge()` — LLM Judge 최적화 팩토리** _(Gap AU)_

```python
eval = EvalDecorator.for_llm_judge(
    output_dir="results/",
    model="gpt-4o-mini",   # LLMJudge 모델
)
# → PerformanceMonitor(enable_llm_judge=True, llm_judge=LLMJudge(model=...)) 자동 생성
# → [llm] extras 필요: pip install "agent-evaluator[llm]"

@eval(task_type="qa")
def agent(question, ground_truth=""): ...
# → completeness / relevance / factual_consistency 자동 채점
```

`[llm]` extras 미설치 시 `logger.debug` 경고 후 `enable_llm_judge=False` 로 graceful fallback 됩니다.

---

### 3-50. 스트리밍 generator `EvalMetadata` yield 지원

`@agent_eval` 로 감싼 generator 함수에서 `EvalMetadata` 를 yield 하면 메타데이터로 처리됩니다 (Gap AV). 호출자에게는 전달되지 않으며(투명), 일반 chunk 처리에는 영향을 주지 않습니다.

```python
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = "") -> Iterator[str]:
    yield "청크1"
    yield "청크2"
    yield "청크3"
    yield EvalMetadata(
        framework="langchain",
        attempts=2,
        chain_steps=[{"name": "retriever", "success": True, "execution_time": 0.3}],
    )
    # EvalMetadata 는 호출자에게 전달되지 않음 — 평가 기록에만 사용

# async generator 도 동일하게 지원
@agent_eval(monitor, task_type="qa")
async def async_streaming(question: str, ground_truth: str = "") -> AsyncIterator[str]:
    async for chunk in llm.astream(question):
        yield chunk
    yield EvalMetadata(model_name="gpt-4o-mini")
```

`get_eval_ctx()` 와 병행 사용 가능하며, `EvalMetadata` yield 가 더 높은 우선순위를 갖습니다.

---

### 3-51. `conversation_eval` `turn_score_fn`

각 턴의 품질을 실시간으로 점수화합니다 (Gap AX). `session_score_fn` 이 세션 전체 완료 시 한 번 호출되는 것과 달리, `turn_score_fn` 은 **매 턴마다** 호출됩니다.

```python
def per_turn_quality(user: str, response: str, metadata: dict) -> float:
    """응답 길이와 ground_truth 일치 여부로 단순 점수화."""
    gt = metadata.get("ground_truth", "")
    if gt and gt in response:
        return 1.0
    return min(len(response) / 200, 0.8)

@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=5,
    turn_score_fn=per_turn_quality,   # (user, response, metadata) → float
    on_turn=lambda s, u, a, m: print(f"턴 점수: {m.get('turn_score'):.2f}"),
)
def chat(question: str, sid: str = "conv_001") -> str:
    return llm.predict(question)
```

**콜백 시그니처**: `(user: str, response: str, metadata: dict) → float`

반환값은 `[0.0, 1.0]` 으로 클램핑되며 `metadata["turn_score"]` 로 저장됩니다. `on_turn` 콜백에서 `metadata["turn_score"]` 로 즉시 접근할 수 있습니다. 예외 발생 시 무시됩니다.

---

### 3-52. `conversation_eval` `max_session_seconds`

마지막 활동 이후 지정한 시간(초)이 경과하면 세션을 자동 flush 합니다 (Gap AY). 장기 실행 서버 환경에서 종료 없이 방치된 세션의 누수를 방지합니다.

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=50,             # 50턴 또는 30분 비활성 시 flush
    max_session_seconds=1800, # 마지막 턴 이후 30분 초과 시 자동 flush
    on_flush=lambda sid: print(f"세션 {sid} 종료 (자동 flush)"),
)
def chat_server(question: str, sid: str = "default") -> str:
    return llm.predict(question)
```

내부적으로 `threading.Timer` 를 사용하며, 각 새 턴이 추가될 때마다 타이머가 재설정됩니다(슬라이딩 윈도우). `flush_conversation()` 또는 `max_turns` 도달 시 타이머가 자동으로 취소됩니다.

> **주의**: `max_session_seconds` 는 마지막 **턴** 이후의 비활성 시간을 기준으로 합니다. 세션 생성 시점이 아닙니다.

---

## 4. 메타데이터 병합 우선순위

`record_task()` 에 전달되는 `TaskResult` 의 각 필드는 다음 순서로 결정됩니다. 높은 순위가 낮은 순위를 덮어씁니다.

```
우선순위 (높은 순)
┌─────────────────────────────────────────────────────────────────────┐
│ 4. EvalMetadata (tuple return)    ← 함수가 (raw, EvalMetadata) 반환 │
│ 3. _EvalContext (get_eval_ctx())  ← 함수 본문에서 ctx.field = val   │
│ 2. score_fn / completion_fn       ← 데코레이터 파라미터             │
│ 1. 자동 계산 (create_taskresult)  ← 유사도·토큰 추출·perf_counter   │
└─────────────────────────────────────────────────────────────────────┘
```

**실용 예시 — EvalMetadata가 score_fn을 덮어씀**

```python
@agent_eval(monitor, score_fn=lambda r, gt: 0.1)   # score_fn = 0.1
def agent(question, ground_truth=""):
    return "정답입니다", EvalMetadata(accuracy_score=0.95)  # EvalMetadata = 0.95

# 최종 accuracy_score = 0.95  (EvalMetadata 우선)
```

**`EvalMetadata` None 기본값 동작 (v0.7.0)**

`EvalMetadata` 의 `attempts` / `framework` 필드 기본값은 `None` 입니다. 명시적으로 지정한 필드만 자동 계산값을 덮어씁니다.

```python
# ✅ 올바른 사용 — accuracy_score만 override, attempts/framework는 자동 계산 유지
return response, EvalMetadata(accuracy_score=0.9)
# attempts = 자동 계산값 유지, framework = decorator 파라미터값 유지

# ⚠️ v0.7.0 이전 방식 (비권장) — 아래처럼 쓰면 attempts=1, framework="native"로 리셋됨
# return response, EvalMetadata(accuracy_score=0.9, attempts=1, framework="native")
```

---

## 5. 커버 가능한 지표 범위

### Layer 1 — Foundation Metrics

| 지표 | 트래커 | 지원 | 조건 |
|------|--------|------|------|
| **Task Completion Rate** | `TaskCompletionTracker` | ✅ 완전 | 항상 |
| **Accuracy Score** | `AccuracyEvaluator` | ✅ 완전 | ground_truth 제공 시 자동 / `score_fn` 또는 `EvalMetadata.accuracy_score` 로 override 가능 |
| **Response Quality** (5차원) | `ResponseQualityEvaluator` | ✅ 완전 | question + response 있으면 자동 트리거 |
| **Latency** | `LatencyTracker` | ✅ 완전 | perf_counter 자동 측정 |
| **Token Economy** | `TokenEconomyTracker` | ✅ 완전 | OpenAI / Anthropic 응답 반환 시 정확, 미반환 시 휴리스틱 |
| **Hallucination Detection** | `HallucinationDetector` | ✅ 완전 | `context_arg` + `enable_hallucination_detection=True` |

### Layer 2 — Agentic Metrics

| 지표 | 트래커 | 지원 | 방법 |
|------|--------|------|------|
| **Tool Call Analysis** | `ToolCallAnalyzer` | ✅ 완전 | OpenAI FC / LangChain result 자동 추출, 또는 `EvalMetadata.tool_calls` |
| **Retry / Correction** | `RetryCorrectionTracker` | ✅ 완전 | `@agent_eval_with_retry` 또는 `EvalMetadata.attempts` |
| **Tool Selection F1** | `ToolSelectionTracker` | ✅ 완전 | `expected_tools_arg` 또는 `EvalMetadata.expected_tools` |
| **Agent Coordination** | `AgentCoordinationTracker` | ✅ 완전 | `EvalMetadata.agent_interactions` 또는 `get_eval_ctx().agent_interactions` |
| **Workflow Execution** | `WorkflowExecutionTracker` | ✅ 완전 | `EvalMetadata.chain_steps` 또는 `get_eval_ctx().chain_steps` |

**보안 지표 (Layer 2)**

| 지표 | 트래커 | 지원 | 조건 |
|------|--------|------|------|
| **Input Sanitization** | `InputSanitizationTracker` | ✅ 완전 | `enable_security_metrics=True` |
| **Output Leakage** | `OutputLeakageDetector` | ✅ 완전 | `enable_security_metrics=True` |
| **Tool Authorization** | `ToolAuthorizationTracker` | ✅ 완전 | tool_calls 있으면 자동, `EvalMetadata.tool_calls` 로 수동 주입 가능 |
| **Privilege Escalation** | `PrivilegeEscalationDetector` | ✅ 완전 | 동일 |
| **Tool Chain Attack** | `ToolChainAttackDetector` | ✅ 완전 | 동일 |

```python
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

@agent_eval(monitor, task_type="tool_use")
def secure_agent(question: str, ground_truth: str = "") -> str:
    ...
```

### Layer 3 — Hybrid Evaluation (외부 라이브러리)

| 지표 | 어댑터 | 지원 |
|------|--------|------|
| DeepEval (G-Eval, RAGAS 등) | `DeepEvalAdapter` | ❌ 구조적 불가 |
| Ragas (Context Precision 등) | `RagasAdapter` | ❌ 구조적 불가 |
| LangSmith 트레이싱 | `LangSmithAdapter` | ❌ 구조적 불가 |

Layer 3 는 `HybridPerformanceMonitor` + `ExtendedTaskResult` 구조로, 데코레이터가 생성하는 `TaskResult` 와 호환되지 않습니다.

### LLM Judge

```python
monitor = PerformanceMonitor(
    enable_llm_judge=True,
    llm_judge=LLMJudge(model="gpt-4o-mini"),
)

@agent_eval(monitor, task_type="qa")
def agent(question, ground_truth=""):
    return llm.predict(question)
# question + response 있으면 자동 트리거 → TaskResult.llm_judge 에 기록
```

### 멀티턴 대화 (ConversationSession)

`@conversation_eval` 로 완전 지원됩니다.

```python
@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
def chat(question, sid="default"):
    return llm.predict(question)
# context_retention, topic_coherence, progressive_depth, session_completion 계산
```

### 지표 범위 요약

```
Layer 1 (6개)    ██████████████████████████ 100%
 ├─ TCR                    ✅ 완전
 ├─ Accuracy               ✅ 완전 + score_fn / EvalMetadata override 가능
 ├─ Response Quality       ✅ 완전 (자동 트리거)
 ├─ Latency                ✅ 완전
 ├─ Token Economy          ✅ 완전 (OpenAI·Anthropic·Gemini 정확 / 기타 휴리스틱)
 └─ Hallucination          ✅ 완전 (context_arg + enable 필요)

Layer 2 (10개)   ██████████████████████████ 100%
 ├─ Tool Call Analysis     ✅ 완전 (자동 추출 + EvalMetadata override)
 ├─ Retry/Correction       ✅ 완전 (@agent_eval_with_retry / EvalMetadata.attempts)
 ├─ Tool Selection F1      ✅ 완전 (expected_tools_arg / EvalMetadata.expected_tools)
 ├─ Agent Coordination     ✅ 완전 (EvalMetadata.agent_interactions / eval_ctx)
 ├─ Workflow Execution     ✅ 완전 (EvalMetadata.chain_steps / eval_ctx)
 ├─ Input Sanitization     ✅ 완전 (보안 enable 필요)
 ├─ Output Leakage         ✅ 완전 (보안 enable 필요)
 ├─ Tool Authorization     ✅ 완전 (tool_calls 있으면 자동)
 ├─ Privilege Escalation   ✅ 완전 (tool_calls 있으면 자동)
 └─ Tool Chain Attack      ✅ 완전 (tool_calls 있으면 자동)

Layer 3 (3개)    ░░░░░░░░░░░░░░░░░░░░░░░░░░   0%  (구조적 한계 — 기존 방식 필요)

ConversationSession          ✅ 완전 (@conversation_eval)
스트리밍 generator           ✅ 완전 (sync yield / async yield 자동 감지, 에러 시 partial 보존)
클래스 메서드               ✅ 완전 (self/cls 자동 skip)
커스텀 점수                  ✅ 완전 (score_fn / EvalMetadata)
on_record 콜백               ✅ 완전 (agent_eval / retry / batch)
timeout                      ✅ 완전 (sync: ThreadPoolExecutor / async: asyncio.wait_for)
eval_context                 ✅ 완전 (with/async with, 동적 필드 재설정 지원)
EvalDecorator 팩토리         ✅ 완전 (공통 설정 재사용, __call__/with_retry/batch/conversation)
비표준 LLM 토큰 주입         ✅ 완전 (EvalMetadata.tokens_used + model_name)
Cohere SDK 토큰 자동 추출    ✅ 완전 (cohere>=5.0, meta.tokens 자동 파싱)
batch per-item EvalMetadata  ✅ 완전 (List[tuple] 반환 + get_eval_ctx() 공통 적용)
on_flush 콜백                ✅ 완전 (conversation_eval, auto/manual flush 모두 트리거)
EvalMetadata.context/gt 재정의 ✅ 완전 (런타임 context/ground_truth 동적 override)
batch_eval contexts_arg      ✅ 완전 (항목별 RAG context 리스트 전달)
eval_context sample_rate/enabled ✅ 완전 (컨텍스트 매니저 수준 샘플링/활성화)
EvalDecorator 확장           ✅ 완전 (context()/for_rag()/for_security() + flush_all_conversations)
conversation_eval score_fn   ✅ 완전 (session_score_fn: ConversationMetrics → float)
다중 monitor 동시 기록       ✅ 완전 (List[PerformanceMonitor] 지원)
LLM Judge                    ✅ 완전 (enable_llm_judge + 자동 트리거)
batch task_id_fn             ✅ 완전 (항목별 커스텀 task_id, fallback 포함)
batch expected_tools_arg     ✅ 완전 (항목별 Tool Selection F1 활성화)
batch timeout                ✅ 완전 (sync: ThreadPoolExecutor / async: asyncio.wait_for)
conversation on_turn         ✅ 완전 (매 턴 콜백, ground_truth 포함)
conversation ground_truth_arg ✅ 완전 (파라미터 이름 커스터마이징)
EvalDecorator.monitor        ✅ 완전 (내부 monitor 직접 접근)
EvalMetadata conversation_turns ✅ 완전 (멀티턴 대화 데이터 수동 주입)
EvalMetadata llm_judge       ✅ 완전 (외부 LLM Judge 점수 수동 주입)
TaskResult.extra             ✅ 완전 (자유 형식 도메인 메타데이터)
EvalDecorator 컨텍스트 파라미터 ✅ 완전 (question_arg/context_arg/task_id_fn/timeout 상속)
on_retry 콜백               ✅ 완전 (agent_eval_with_retry, 매 재시도마다 호출)
on_error 콜백               ✅ 완전 (agent_eval/with_retry, has_error=True 시만 호출)
EvalMetadata.errors          ✅ 완전 (수동 재시도 에러 목록 주입)
EvalMetadata.execution_time  ✅ 완전 (외부 측정값으로 perf_counter 대체)
batch on_batch_complete      ✅ 완전 (배치 전체 완료 후 List[TaskResult] 1회 콜백)
TurnMetadata.ground_truth    ✅ 완전 (턴별 정답 명시, ground_truth_arg 보다 높은 우선순위)
task_id_arg                  ✅ 완전 (함수 파라미터에서 task_id 자동 탐지)
jitter                       ✅ 완전 (agent_eval_with_retry, thundering herd 방지)
eval_context task_id_fn      ✅ 완전 (agent_eval 기능 동등성)
EvalDecorator.update_defaults ✅ 완전 (생성 후 기본값 부분 변경, 체이닝 지원)
EvalDecorator.for_llm_judge  ✅ 완전 (LLM Judge 최적화 팩토리, graceful fallback)
스트리밍 EvalMetadata yield   ✅ 완전 (generator에서 EvalMetadata yield → 메타데이터 주입)
conversation turn_score_fn   ✅ 완전 (매 턴 품질 점수화, metadata["turn_score"] 저장)
conversation max_session_seconds ✅ 완전 (비활성 세션 자동 flush, threading.Timer 슬라이딩 윈도우)
```

---

## 6. 프레임워크별 지원 범위

### 6-1. 직접 LLM 호출 (OpenAI / Anthropic) — ✅ 완전

```python
@agent_eval(monitor, task_type="qa", model_name="gpt-4o-mini")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return openai.chat.completions.create(model="gpt-4o-mini", ...)
```

### 6-2. LangChain invoke / LCEL — ✅ 완전

```python
# LCEL — string 반환
@agent_eval(monitor, task_type="qa")
def lcel_agent(question: str, ground_truth: str = "") -> str:
    return chain.invoke({"question": question})

# AgentExecutor — EvalMetadata로 chain_steps + expected_tools 주입
@agent_eval(monitor, task_type="tool_use",
            framework="langchain", expected_tools_arg="expected")
def lc_agent(question: str, expected=None, ground_truth: str = "") -> str:
    result = executor.invoke({"input": question})
    steps = result.get("intermediate_steps", [])
    return result["output"], EvalMetadata(
        tool_calls=[{"tool": s[0].tool, "input": s[0].tool_input} for s in steps],
        chain_steps=[{"name": s[0].tool, "success": True, "execution_time": 0.0}
                     for s in steps],
    )
```

### 6-3. LangGraph — ✅ 완전 (EvalMetadata / eval_ctx 활용)

```python
@agent_eval(monitor, task_type="planning")
def graph_agent(question: str, ground_truth: str = "") -> str:
    result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})
    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langgraph"
        ctx.graph_traversal = {"nodes_visited": [...]}
        ctx.state_transitions = [{"from": "A", "to": "B", "trigger": "..."}]
    return result["messages"][-1].content
```

### 6-4. CrewAI — ✅ 지원 (EvalMetadata 활용) / 기존 방식도 가능

```python
# 데코레이터 — agent_interactions 수동 주입
@agent_eval(monitor, task_type="tool_use")
def crew_fn(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff({"topic": question})
    return str(result), EvalMetadata(
        framework="crewai",
        agent_interactions=[
            {"from_agent": "researcher", "to_agent": "writer",
             "type": "handoff", "success": True},
        ],
    )

# 기존 방식 — 자동 수집 (create_evaluated_crew)
crew = create_evaluated_crew(tasks, agents, monitor=monitor)
crew.kickoff()
```

> CrewAI의 복잡한 내부 상호작용 자동 수집이 필요하면 `create_evaluated_crew()` 를 권장합니다.

### 6-5. AutoGen — ⚠️ 제한 / 기존 방식 권장

`conversation_turns` 기반 멀티턴 구조입니다. 기본 기록은 가능하지만 자동 내부 수집은 `create_evaluated_autogen_agent()` 만 지원합니다.

### 6-6. 멀티턴 대화 — ✅ 완전 (`@conversation_eval`)

```python
@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
def chat(question: str, sid: str = "conv_001") -> str:
    return llm.predict(question)

chat("안녕", sid="conv_001")
chat("날씨는?", sid="conv_001")
flush_conversation("conv_001")
# context_retention, topic_coherence, progressive_depth, session_completion 기록
```

### 프레임워크 지원 요약

| 프레임워크 / 패턴 | 지원 수준 | 방법 |
|------------------|-----------|------|
| 직접 LLM 호출 (OpenAI/Anthropic/Gemini) | ✅ 완전 | `@agent_eval` |
| LangChain LCEL / invoke | ✅ 완전 | `@agent_eval` + EvalMetadata |
| LangChain AgentExecutor | ✅ 완전 | `@agent_eval` + EvalMetadata (chain_steps) |
| LangGraph | ✅ 완전 | `@agent_eval` + `get_eval_ctx()` (graph_traversal) |
| CrewAI | ✅ 지원 | `@agent_eval` + EvalMetadata (agent_interactions) |
| AutoGen | ⚠️ 부분 | `create_evaluated_autogen_agent()` 권장 |
| 스트리밍 generator (sync/async) | ✅ 완전 | `@agent_eval` (자동 감지) |
| 배치 처리 (List→List) | ✅ 완전 | `@batch_eval` |
| 클래스 메서드 | ✅ 완전 | `@agent_eval` (self/cls 자동 skip) |
| 멀티턴 대화 | ✅ 완전 | `@conversation_eval` |
| 데코레이터 불가 블록 | ✅ 완전 | `eval_context` (with/async with, 동적 필드 재설정) |
| 타임아웃 제어 | ✅ 완전 | `@agent_eval(timeout=N)` |
| 공통 설정 재사용 | ✅ 완전 | `EvalDecorator(monitor, framework=..., model_name=...)` |
| 비표준 LLM 토큰 주입 | ✅ 완전 | `EvalMetadata.tokens_used` + `model_name` |
| Cohere SDK | ✅ 완전 | `@agent_eval` (자동 감지, cohere>=5.0) |
| batch RAG context 항목별 전달 | ✅ 완전 | `@batch_eval(contexts_arg=...)` |
| batch 항목별 커스텀 task_id | ✅ 완전 | `@batch_eval(task_id_fn=fn)` |
| batch 항목별 Tool Selection F1 | ✅ 완전 | `@batch_eval(expected_tools_arg=...)` |
| batch 타임아웃 | ✅ 완전 | `@batch_eval(timeout=N)` |
| 다중 monitor 동시 기록 | ✅ 완전 | `monitor=[m1, m2]` |
| conversation 매 턴 콜백 | ✅ 완전 | `@conversation_eval(on_turn=fn)` |
| conversation ground_truth 파라미터 이름 | ✅ 완전 | `@conversation_eval(ground_truth_arg=...)` |
| HybridMonitor (DeepEval/Ragas) | ❌ 불가 | `HybridPerformanceMonitor` 기존 방식 |

---

## 7. 대시보드 UI 커버 범위

`agent-eval dashboard` — FastAPI + Alpine.js 기반 개발·검증 단계 대시보드

### Overview 탭

| UI 요소 | 표시 | 비고 |
|---------|------|------|
| 총 태스크 수 | ✅ | |
| 평균 완료율 (TCR) | ✅ | |
| 평균 정확도 | ✅ | ground_truth 제공 시 |
| 평균 응답 시간 | ✅ | perf_counter 자동 측정 |
| 총 토큰 비용 (USD) | ✅ | OpenAI / Anthropic 응답 반환 시 정확, 미반환 시 휴리스틱 |
| 프레임워크 분포 도넛 차트 | ✅ | `framework` 파라미터 또는 `EvalMetadata.framework` |
| 태스크 유형별 분포 | ✅ | |
| 시간대별 추이 | ✅ | |

### Quality 탭

| UI 요소 | 표시 | 조건 |
|---------|------|------|
| Accuracy Score KPI | ✅ | ground_truth 제공 / `score_fn` / `EvalMetadata` |
| Quality Score (/5.0) | ✅ | 자동 트리거 |
| Hallucination 건수 | ✅ | `context_arg` + `enable_hallucination_detection=True` |
| Ragas Overall | ❌ | HybridMonitor 전용 |
| 응답 품질 차원 레이더 (5개) | ✅ | |
| 환각 탐지 상세 패널 | ✅ | `context_arg` 설정 시 |
| 태스크 상세 테이블 | ✅ | Q/A/GT 전문 표시 |

### Agentic 탭 — 실행·재시도 서브탭

| UI 요소 | 표시 | 방법 |
|---------|------|------|
| TCR % | ✅ | |
| 재시도율 | ✅ | `@agent_eval_with_retry` 또는 `EvalMetadata.attempts` |
| 첫 시도 성공률 | ✅ | 동일 |
| 평균 재시도 시간 | ✅ | 동일 |
| 태스크별 재시도 상세 | ✅ | `errors` 리스트 자동 누적 |

### Agentic 탭 — 도구·협업·흐름 서브탭

| UI 요소 | 표시 | 방법 |
|---------|------|------|
| Tool Selection F1 | ✅ | `expected_tools_arg` 또는 `EvalMetadata.expected_tools` |
| 멀티에이전트 협업 패널 | ✅ | `EvalMetadata.agent_interactions` |
| 워크플로우 흐름 패널 | ✅ | `EvalMetadata.chain_steps` |
| 단계별 소요 시간 바 차트 | ✅ | `EvalMetadata.chain_steps` (execution_time 포함 시) |
| Tool Call Analysis | ✅ | 자동 추출 또는 `EvalMetadata.tool_calls` |
| 프레임워크 분포 | ✅ | `framework` 파라미터 또는 `EvalMetadata.framework` |
| 에이전트 역량 레이더 | ✅ | Tool Use / Coordination / Workflow / Retry / Security 전체 |

### Agentic 탭 — 실행 트레이스 서브탭

| UI 요소 | 표시 | 방법 |
|---------|------|------|
| 태스크별 실행 타임라인 | ✅ | execution_time 자동 측정 |
| JSON 원본 다운로드 | ✅ | |

### Security 탭

| UI 요소 | 표시 | 조건 |
|---------|------|------|
| 보안 종합 점수 | ✅ | `enable_security_metrics=True` |
| Input Sanitization | ✅ | |
| Output Leakage | ✅ | |
| Tool Authorization | ✅ | tool_calls 있으면 자동 |
| Privilege Escalation | ✅ | tool_calls 있으면 자동 |

### RAG 탭

| UI 요소 | 표시 | 조건 |
|---------|------|------|
| Hallucination Rate | ✅ | `context_arg` + `enable_hallucination_detection=True` |
| Faithfulness | ✅ | 동일 |
| Context Precision / Recall | ❌ | Ragas 어댑터 전용 |

### 공통 기능

CSV 내보내기 ✅ / HTML 리포트 ✅ / 슬라이드 뷰 ✅ / `--watch` 자동 갱신 ✅ / `--offline` ✅ / Q/A/GT 전문 보기 ✅

---

## 8. Phoenix 모니터링 UI 커버 범위

```python
from agent_evaluator import setup_otel
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
```

### Tracing 탭

| UI 컬럼 | 데코레이터 데이터 | 비고 |
|---------|----------------|------|
| Span Name | `ae.task/{task_type}/{task_id}` | ✅ |
| Kind | LLM / RETRIEVER / TOOL / AGENT / CHAIN | ✅ task_type 자동 매핑 |
| Input / Output | question / response | ✅ |
| Latency | execution_time | ✅ start_time 역산 |
| Token Count | input / output / total | ✅ OpenAI·Anthropic·Gemini 정확 / 기타 휴리스틱 |
| Model | `model_name` 파라미터 | ✅ |
| Status | OK / ERROR | ✅ |
| Metadata 탭 | task_type, framework, partial_reason | ✅ framework 이제 정확 |
| Context 탭 (RAG) | retrieval.documents | ✅ `context_arg` 설정 시 |

### Evaluators 탭 (Phoenix Annotations)

| Annotation | 정확도 | 비고 |
|-----------|--------|------|
| accuracy | ✅ 정확 | `score_fn` / `EvalMetadata` override 가능 |
| completion | ✅ 정확 | `completion_fn` / `EvalMetadata` override 가능 |
| success | ✅ | |
| hallucination | ✅ | context_arg 설정 시 |
| quality | ✅ | 자동 트리거 |
| latency | ✅ | |
| tool_calls | ✅ | |
| attempts | ✅ 정확 | `@agent_eval_with_retry` 또는 `EvalMetadata.attempts` 로 실제값 |

### OTEL 속성 현재 동작

| 속성 | 값 | 데코레이터 제어 |
|------|-----|----------------|
| `ae.framework` | 실제 프레임워크명 | `framework` 파라미터 또는 `EvalMetadata.framework` |
| `ae.attempts` | 실제 재시도 횟수 | `@agent_eval_with_retry` 또는 `EvalMetadata.attempts` |
| `ae.tool_calls_count` | 실제 tool call 수 | 자동 추출 또는 `EvalMetadata.tool_calls` 수동 주입 |
| `ae.tokens.*` | 정확한 토큰 수 | OpenAI·Anthropic 응답 자동 파싱, 기타 휴리스틱 |

---

## 9. 기존 방식과 혼용 패턴

### 패턴 A — 계층별 분리

```python
monitor = PerformanceMonitor(output_dir="results/")

# 단순 LLM → 데코레이터
@agent_eval(monitor, task_type="qa")
def qa_agent(question, ground_truth=""): return llm.predict(question)

# 재시도 필요 → retry 데코레이터
@agent_eval_with_retry(monitor, task_type="qa", max_retries=3,
                       retry_on=(ConnectionError,))
def fragile_agent(question, ground_truth=""): return llm.predict(question)

# 멀티턴 → conversation_eval
@conversation_eval(monitor, session_id_arg="sid", max_turns=5)
def chat(question, sid="s1"): return llm.predict(question)

# DeepEval/Ragas → 기존 방식
hybrid = HybridPerformanceMonitor(providers=[MetricProvider.DEEPEVAL])
hybrid.record_task(extended_result)

monitor.save_to_file("combined_results")
```

### 패턴 B — 컨텍스트 매니저 + 데코레이터

```python
with evaluation_session("session_output") as monitor:
    @agent_eval(monitor, task_type="qa")
    def agent(question, ground_truth=""):
        return llm.predict(question)

    agent("질문 1", ground_truth="답 1")
    agent("질문 2", ground_truth="답 2")
# 세션 종료 시 자동 저장
```

### 패턴 C — LangGraph + eval_ctx

```python
@agent_eval(monitor, task_type="planning")
def graph_agent(question, ground_truth=""):
    result = compiled_graph.invoke(...)
    ctx = get_eval_ctx()
    if ctx:
        ctx.framework = "langgraph"
        ctx.graph_traversal = collect_traversal(result)
    return result["messages"][-1].content

# WorkflowExecutionTracker + 프레임워크 분포 차트 모두 활성화
```

---

## 10. 적용 방식 선택 기준

```
에이전트 유형
│
├─ 단순 LLM 호출 (QA / 코드 / 문서)?
│   └─▶ @agent_eval  ← Layer 1 전체 + 보안 지표 커버
│
├─ 재시도 로직 필요?
│   └─▶ @agent_eval_with_retry  ← attempts 정확 기록, 지수 백오프 내장
│
├─ Tool Use + expected_tools 평가?
│   └─▶ @agent_eval(expected_tools_arg=...)
│       또는 EvalMetadata(expected_tools=[...])
│
├─ 프레임워크 내부 단계 기록 (chain_steps / graph_traversal)?
│   ├─ 수동 주입 가능?
│   │   └─▶ EvalMetadata(chain_steps=...) 또는 get_eval_ctx()
│   └─ 자동 수집 필요?
│       └─▶ LangChainEvaluator / create_evaluated_langgraph (기존 방식)
│
├─ CrewAI 멀티에이전트?
│   ├─ interactions 수동 파악 가능?
│   │   └─▶ @agent_eval + EvalMetadata(agent_interactions=...)
│   └─ 자동 수집 필요?
│       └─▶ create_evaluated_crew (기존 방식)
│
├─ 멀티턴 대화?
│   └─▶ @conversation_eval + flush_conversation
│
├─ 배치 처리 (질문 리스트 → 응답 리스트)?
│   └─▶ @batch_eval  ← N개 TaskResult 자동 분리 기록
│
├─ 스트리밍 generator (yield / async yield)?
│   └─▶ @agent_eval  ← 자동 감지, chunk passthrough + 소진 후 기록
│
├─ 클래스 메서드에 적용?
│   └─▶ @agent_eval  ← self/cls 자동 skip, 별도 처리 불필요
│
├─ 기록 후 사이드이펙트 (알림 / DB 저장)?
│   └─▶ @agent_eval(on_record=callback)
│
├─ 실행 시간 제한 필요?
│   └─▶ @agent_eval(timeout=N)  ← 초과 시 TimeoutError + success=False 기록
│
├─ 데코레이터를 붙일 수 없는 코드 블록?
│   └─▶ eval_context(monitor, ...) as ctx:  ← with/async with + 동적 필드 재설정
│
├─ 같은 monitor/설정을 여러 함수에 반복 적용?
│   └─▶ EvalDecorator(monitor, framework=..., model_name=...)
│       └─▶ @eval(task_type) / @eval.with_retry / @eval.batch / @eval.conversation
│
├─ 비표준 LLM 정확한 토큰 수 기록 (Mistral fine-tune, 로컬 모델)?
│   └─▶ EvalMetadata(tokens_used={...}, model_name="...")
│       또는 get_eval_ctx().tokens_used = {...}
│
├─ Cohere SDK (cohere>=5.0) 사용?
│   └─▶ @agent_eval  ← meta.tokens 자동 감지·추출
│
├─ 배치 함수에서 항목별 다른 메타데이터?
│   └─▶ @batch_eval + List[tuple] 반환 (항목별 EvalMetadata)
│       또는 get_eval_ctx() (배치 전체 공통 적용)
│
├─ 대화 세션 완료 후 알림/저장?
│   └─▶ @conversation_eval(on_flush=callback)
│
├─ 대화 세션 전체 점수 커스터마이징?
│   └─▶ @conversation_eval(session_score_fn=fn)  ← ConversationMetrics → float
│
├─ 모든 미완료 대화 세션 일괄 종료?
│   └─▶ flush_all_conversations()  ← atexit 등록 또는 테스트 teardown
│
├─ context / ground_truth 를 런타임에 확정?
│   └─▶ EvalMetadata(context=..., ground_truth=...) 또는 eval_ctx.context = ...
│
├─ 배치 함수에서 항목별 RAG context 전달?
│   └─▶ @batch_eval(contexts_arg="contexts")
│
├─ eval_context 를 조건부로만 평가?
│   └─▶ eval_context(..., sample_rate=0.1, enabled=FLAG) as ctx
│
├─ 같은 데이터를 여러 monitor 에 동시 기록 (A/B 비교)?
│   └─▶ @agent_eval([monitor_a, monitor_b], ...)
│
├─ RAG 에 최적화된 monitor + 데코레이터 한 번에?
│   └─▶ EvalDecorator.for_rag(output_dir)  ← hallucination 기본 활성
│
├─ 보안 에이전트에 최적화된 monitor + 데코레이터?
│   └─▶ EvalDecorator.for_security(output_dir)  ← 보안 지표 기본 활성
│
├─ 데코레이터 없는 코드 블록에서 공통 설정 재사용?
│   └─▶ eval.context(task_type, question=q) as ctx
│
├─ 배치 함수에서 항목별 고정 task_id 부여?
│   └─▶ @batch_eval(task_id_fn=lambda i, q, gt: ...)
│
├─ 배치 함수에서 항목별 Tool Selection F1?
│   └─▶ @batch_eval(expected_tools_arg="expected_tools")
│
├─ 배치 함수 전체 타임아웃 제한?
│   └─▶ @batch_eval(timeout=N)
│
├─ 대화 각 턴마다 실시간 알림/로깅?
│   └─▶ @conversation_eval(on_turn=callback)   ← (session_id, user, agent, meta) → None
│
├─ 대화 함수에서 ground_truth 파라미터 이름이 다름?
│   └─▶ @conversation_eval(ground_truth_arg="expected")
│
├─ EvalDecorator 내부 monitor 접근?
│   └─▶ eval.monitor.generate_report() / eval.monitor.save_to_file(...)
│
├─ 멀티턴 대화 데이터를 TaskResult 에 수동 주입?
│   └─▶ EvalMetadata(conversation_turns=[...])
│
├─ 외부 LLM Judge 점수 수동 주입?
│   └─▶ EvalMetadata(llm_judge={...}) 또는 eval_ctx.llm_judge = {...}
│
├─ 도메인별 임의 메타데이터 첨부 (실험 ID, 사용자 티어 등)?
│   └─▶ EvalMetadata(extra={...}) 또는 eval_ctx.extra = {...}
│       → TaskResult.extra 로 저장, to_dict() 왕복 보존
│
├─ EvalDecorator 로 여러 함수에 question_arg/context_arg/timeout 공통 설정?
│   └─▶ EvalDecorator(monitor, question_arg=..., context_arg=..., timeout=N)
│
├─ EvalDecorator 생성 후 일부 기본값만 변경?
│   └─▶ eval.update_defaults(model_name="gpt-4-turbo", timeout=60.0)  ← 체이닝 지원
│
├─ 재시도 발생 시 즉각적인 알림/로깅?
│   └─▶ @agent_eval_with_retry(on_retry=lambda attempt, err: ...)
│
├─ 에러 발생 시에만 콜백?
│   └─▶ @agent_eval(on_error=lambda tr: alert(tr.errors))  ← has_error=True 시만 호출
│
├─ 수동 재시도 구현에서 errors 기록?
│   └─▶ EvalMetadata(errors=[...]) 또는 eval_ctx.errors = [...]
│
├─ 외부 측정 latency 를 execution_time 으로 사용?
│   └─▶ EvalMetadata(execution_time=trace.latency)
│
├─ 배치 완료 후 일괄 처리 (요약, DB 저장)?
│   └─▶ @batch_eval(on_batch_complete=lambda results: ...)
│
├─ 함수 파라미터 이름이 task_id 인 경우 자동 탐지?
│   └─▶ @agent_eval(task_id_arg="task_id")
│
├─ 재시도 thundering herd 방지 (프로덕션)?
│   └─▶ @agent_eval_with_retry(delay=2.0, backoff=2.0, jitter=True)
│
├─ eval_context 에서 동적 task_id 생성?
│   └─▶ eval_context(..., task_id_fn=lambda: f"req_{uuid4().hex[:8]}")
│
├─ 스트리밍 generator 에서 메타데이터 주입 (반환값 타입 변경 불가)?
│   └─▶ @agent_eval + generator 내 `yield EvalMetadata(...)` (마지막 chunk로)
│
├─ 대화 각 턴의 품질 실시간 점수화?
│   └─▶ @conversation_eval(turn_score_fn=fn)  ← metadata["turn_score"] 저장
│
├─ 장기 실행 서버에서 미완료 세션 자동 정리?
│   └─▶ @conversation_eval(max_session_seconds=1800)  ← 비활성 시 자동 flush
│
├─ LLM Judge 최적화 monitor + 데코레이터 한 번에?
│   └─▶ EvalDecorator.for_llm_judge(output_dir)  ← enable_llm_judge 자동 설정
│
├─ DeepEval / Ragas / LangSmith?
│   └─▶ HybridPerformanceMonitor (기존 방식 필수)
│
└─ 커스텀 점수 (ROUGE / 도메인 특화)?
    └─▶ score_fn 파라미터 또는 EvalMetadata(accuracy_score=...)
```

### 빠른 참조표

| 평가 목적 | 권장 방식 |
|-----------|-----------|
| Layer 1 전체 | `@agent_eval` |
| Layer 2 Tool Call | `@agent_eval` (자동) |
| Layer 2 Retry/Correction | `@agent_eval_with_retry` |
| Layer 2 Tool Selection F1 | `@agent_eval(expected_tools_arg=...)` 또는 `EvalMetadata` |
| Layer 2 Coordination/Workflow | `EvalMetadata` 또는 `get_eval_ctx()` |
| 보안 지표 전체 | `@agent_eval` + `enable_security_metrics=True` |
| LLM Judge | `@agent_eval` + `enable_llm_judge=True` |
| RAG + 할루시네이션 | `@agent_eval(context_arg=...)` + `enable_hallucination_detection=True` |
| 커스텀 점수 | `score_fn` 파라미터 또는 `EvalMetadata.accuracy_score` |
| 멀티턴 대화 | `@conversation_eval` + `flush_conversation` |
| 배치 처리 (List→List) | `@batch_eval` |
| 스트리밍 generator | `@agent_eval` (자동 감지) |
| 클래스 메서드 | `@agent_eval` (self/cls 자동 skip) |
| 기록 후 콜백 | `@agent_eval(on_record=fn)` |
| 재시도 정확 기록 | `@agent_eval_with_retry` |
| 타임아웃 제어 | `@agent_eval(timeout=N)` 또는 `@agent_eval_with_retry(timeout=N)` |
| 데코레이터 불가 블록 | `eval_context(monitor, ...) as ctx` (동적 필드 재설정 가능) |
| 공통 설정 재사용 | `EvalDecorator(monitor, framework=..., model_name=...)` |
| 비표준 LLM 토큰 | `EvalMetadata.tokens_used` + `model_name` |
| Cohere SDK | `@agent_eval` (cohere>=5.0 자동 감지) |
| batch 항목별 메타데이터 | `@batch_eval` + `List[tuple]` 반환 |
| 대화 세션 완료 콜백 | `@conversation_eval(on_flush=fn)` |
| 대화 세션 점수 커스터마이징 | `@conversation_eval(session_score_fn=fn)` |
| 모든 미완료 세션 일괄 종료 | `flush_all_conversations()` |
| context/ground_truth 런타임 재정의 | `EvalMetadata(context=..., ground_truth=...)` |
| batch 항목별 RAG context | `@batch_eval(contexts_arg="contexts")` |
| eval_context 조건부 평가 | `eval_context(..., sample_rate=0.1, enabled=FLAG)` |
| A/B 모니터 동시 기록 | `@agent_eval([monitor_a, monitor_b], ...)` |
| RAG 최적화 팩토리 | `EvalDecorator.for_rag(output_dir)` |
| 보안 최적화 팩토리 | `EvalDecorator.for_security(output_dir)` |
| eval_context + 공통 설정 | `eval.context(task_type, question=q)` |
| batch 항목별 커스텀 task_id | `@batch_eval(task_id_fn=lambda i, q, gt: ...)` |
| batch 항목별 Tool Selection F1 | `@batch_eval(expected_tools_arg="expected_tools")` |
| batch 타임아웃 | `@batch_eval(timeout=N)` |
| conversation 매 턴 콜백 | `@conversation_eval(on_turn=fn)` |
| conversation ground_truth 파라미터 이름 | `@conversation_eval(ground_truth_arg="expected")` |
| EvalDecorator 내부 monitor 접근 | `eval.monitor` |
| 멀티턴 대화 데이터 수동 주입 | `EvalMetadata(conversation_turns=[...])` |
| 외부 LLM Judge 점수 수동 주입 | `EvalMetadata(llm_judge={...})` |
| 도메인 임의 메타데이터 | `EvalMetadata(extra={...})` / `eval_ctx.extra = {...}` |
| EvalDecorator 공통 question_arg/context_arg | `EvalDecorator(monitor, question_arg=..., context_arg=...)` |
| EvalDecorator 기본값 부분 변경 | `eval.update_defaults(model_name=..., timeout=N)` |
| LLM Judge 최적화 팩토리 | `EvalDecorator.for_llm_judge(output_dir)` |
| 재시도 중 실시간 콜백 | `@agent_eval_with_retry(on_retry=fn)` |
| 에러 전용 콜백 | `@agent_eval(on_error=fn)` |
| 에러 목록 직접 주입 | `EvalMetadata(errors=[...])` |
| 외부 측정 execution_time | `EvalMetadata(execution_time=N)` |
| 배치 완료 후 일괄 콜백 | `@batch_eval(on_batch_complete=fn)` |
| 턴별 ground_truth 명시 | `TurnMetadata(ground_truth="expected")` |
| 함수 파라미터로 task_id | `@agent_eval(task_id_arg="task_id")` |
| 재시도 지터 (thundering herd 방지) | `@agent_eval_with_retry(jitter=True)` |
| eval_context 동적 task_id | `eval_context(..., task_id_fn=lambda: ...)` |
| 스트리밍 메타데이터 주입 | `yield EvalMetadata(...)` (generator 내) |
| 대화 턴별 품질 점수 | `@conversation_eval(turn_score_fn=fn)` |
| 비활성 세션 자동 flush | `@conversation_eval(max_session_seconds=N)` |
| Phoenix Tracing | `@agent_eval` + `setup_otel()` |
| DeepEval/Ragas | `HybridPerformanceMonitor` (기존 방식) |
| CI/CD 게이팅 | `monitor.save_to_file()` + `agent-eval gate` |
