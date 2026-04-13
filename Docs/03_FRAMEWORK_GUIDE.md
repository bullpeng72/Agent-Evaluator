# 프레임워크 통합 가이드

LangChain · LangGraph · CrewAI · AutoGen 연동 참조 문서

**v0.7.9 | Python 3.8+**

---

## 목차

1. [호환성 및 설치](#호환성-및-설치)
2. [프레임워크 프로필](#프레임워크-프로필)
3. [프레임워크별 빠른 시작](#프레임워크별-빠른-시작)
4. [지표 지원 매트릭스 (25개)](#지표-지원-매트릭스-25개)
5. [토큰 측정 정확도 비교](#토큰-측정-정확도-비교)
6. [보안 지표 추가 (공통)](#보안-지표-추가-공통)
7. [멀티턴 대화 평가 (공통)](#멀티턴-대화-평가-공통)
8. [제한사항 및 주의사항](#제한사항-및-주의사항)
9. [프레임워크 선택 가이드](#프레임워크-선택-가이드)

---

## 호환성 및 설치

### 버전 요구사항

| 패키지 | 최소 버전 | 설치 |
|--------|----------|------|
| Python | 3.8+ | — |
| agent-evaluator | 0.7.9 | `pip install agent-evaluator` |
| LangChain | 1.0.0+ | `pip install agent-evaluator[langchain]` |
| LangGraph | 1.0.0+ | `pip install agent-evaluator[langchain]` |
| CrewAI | 1.0.0+ | `pip install agent-evaluator[crewai]` |
| AutoGen (agentchat) | 0.4.0+ | `pip install agent-evaluator[autogen]` |
| DeepEval | 0.20.0+ | `pip install agent-evaluator[eval]` |
| Ragas | 0.4.0+ | `pip install agent-evaluator[eval]` |

```bash
# 프레임워크별 단독 설치
pip install "agent-evaluator[langchain]"   # LangChain + LangGraph
pip install "agent-evaluator[crewai]"      # CrewAI
pip install "agent-evaluator[autogen]"     # AutoGen

# 전체 설치 (crewai/autogen 포함, 10분+)
pip install "agent-evaluator[full]"
```

### 프레임워크 가용성 확인

```python
from agent_evaluator.integrations.framework_integrations import (
    check_framework_availability,
    get_installation_instructions,
    print_framework_status,
)

print_framework_status()                           # 전체 설치 현황
avail = check_framework_availability("langchain")  # {"langchain": bool}
print(get_installation_instructions("crewai"))     # 설치 안내
```

---

## 프레임워크 프로필

| 프레임워크 | 아키텍처 | 추적 방식 | 토큰 정확도 | 멀티에이전트 | 전체 커버리지 |
|-----------|---------|----------|------------|------------|-------------|
| 🟢 **LangChain** | Chain + Agent | 콜백 핸들러 (실시간) | ✅ 실제값 | ✗ 단일 | ~82% (~21개) |
| 🟠 **LangGraph** | 상태 머신 / DAG | stream() 노드 래핑 | 🔶 부분 | 🔶 노드 전환 | ~82% (~21개) |
| 🔵 **CrewAI** | 역할 기반 멀티에이전트 | Pre/Post 래핑 | ✗ 0 고정 | ✅ | ~78% (~20개) |
| 🟣 **AutoGen** | 대화형 멀티에이전트 | async-first (0.4+) | 🔶 tiktoken | ✅ | ~80% (~20개) |

---

## 프레임워크별 빠른 시작

> **권장 패턴 (v0.7.2+)**
> - `@agent_eval(monitor, framework=...)` 데코레이터 — 응답에서 token/tool 자동 추출
> - `create_taskresult()` 헬퍼 — 수동 기록 시 점수 자동 계산
> - 팩토리 메서드: `PerformanceMonitor.for_rag_evaluation()` / `for_secure_agents()`

---

### 🟢 LangChain

**방법 1 — 데코레이터 (권장)**

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    # LangChain 응답 객체를 그대로 반환 — token_usage 자동 추출
    return agent_executor.invoke({"input": question})
```

또는 프레임워크 전용 데코레이터:

```python
from agent_evaluator.integrations import langchain_eval

@langchain_eval(monitor, task_type="qa")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
```

**수동 기록 (저수준 — 데코레이터 불가 시 탈출구)**

```python
import dataclasses
from agent_evaluator import create_taskresult
from agent_evaluator.decorators import eval_context

# eval_context — 외부 함수 / 복잡한 흐름에 적합
with eval_context(monitor, task_type="qa", question=query, ground_truth=expected) as ctx:
    ctx.response = agent_executor.invoke({"input": query})["output"]

# 또는 create_taskresult() + record_task() 직접 사용
task = create_taskresult(
    task_id="lc_001", question=query, response=response["output"],
    ground_truth=expected, execution_time=elapsed, task_type="qa",
)
monitor.record_task(dataclasses.replace(task, framework="langchain"))
```

**자동 추출**: 실제 토큰 수 (`llm_output.token_usage`), 도구 호출 (`AgentAction`), 재시도 (`on_retry`), 실행 시간

---

### 🟠 LangGraph

**방법 1 — 데코레이터 (권장)**

```python
from agent_evaluator.integrations import langgraph_eval

monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@langgraph_eval(monitor, task_type="qa")
def lg_agent(question: str, ground_truth: str = "") -> str:
    # LangGraph AIMessage 응답 반환 — usage_metadata 자동 추출
    result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content
```

**자동 추출**: 노드별 실측 타이밍, 노드 전환 (AgentCoordination), Workflow Execution, 토큰 (`AIMessage.usage_metadata`)

---

### 🔵 CrewAI

**방법 1 — 데코레이터 (권장)**

```python
from agent_evaluator.integrations import crewai_eval

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

@crewai_eval(monitor, task_type="qa")
def run_crew(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return result.raw  # CrewAI CrewOutput → 자동 파싱
```

**자동 추출**: Agent Coordination, Tool Selection
**주의**: 토큰 수 0 고정 (CrewAI SDK 미노출) — `dataclasses.replace(task, tokens_used={...})`로 수동 설정

---

### 🟣 AutoGen

**방법 1 — 데코레이터 (권장, 0.4+ async)**

```python
from agent_evaluator.integrations import autogen_eval

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

@autogen_eval(monitor, task_type="qa")
async def run_autogen(question: str, ground_truth: str = "") -> str:
    result = await team.run(task=question)
    return result.messages[-1].content
```

**자동 추출**: 에이전트 메시지 교환 (AgentCoordination), 도구 호출 (ToolCallEvent), 토큰 (tiktoken)

---

## 지표 지원 매트릭스 (25개)

### Layer 1 — Foundation (6개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 1 | **TCR** | ✅ 예외 기반 | ✅ 콜백 기반 | ✅ 노드 오류 기반 | ✅ 예외 기반 |
| 2 | **Accuracy** | ✅ ground_truth 제공 시 | ✅ | ✅ run(ground_truth=...) | ✅ set_ground_truth() 후 |
| 3 | **Hallucination** | ✅ tasks_output 자동 | 🔶 Retriever 사용 시 | 🔶 ToolMessage 컨텍스트 | 🔶 도구 결과 컨텍스트 |
| 4 | **Response Quality** | ✅ question/response 제공 시 | ✅ | ✅ | ✅ |
| 5 | **Latency** | 🔶 전체 시간 균등 분배 | ✅ on_chain_end 실측 | ✅ 노드별 실측 | 🔶 team.run() 총 시간 |
| 6 | **Token Economy** | ✗ SDK 미노출 (수동 필요) | ✅ LLM 실제 token_usage | 🔶 AIMessage.usage_metadata | 🔶 tiktoken 우선 |

### Layer 2 — Agentic (5개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 7  | **Tool Call Efficiency** | 🔶 agents 속성 추론 | ✅ on_agent_action 실측 | 🔶 ToolMessage 파싱 | ✅ ToolCallEvent 기반 |
| 8  | **Retry & Recovery** | 🔶 attempts=1 고정 | ✅ on_retry 자동 | 🔶 attempts=1 고정 | 🔶 attempts=1 고정 |
| 9  | **Tool Selection Accuracy** | ✅ expected_tools vs 실행 F1 | ✅ expected_tools vs AgentAction | ✅ ToolMessage 기반 | ✅ ToolCallEvent 기반 |
| 10 | **Agent Coordination** | ✅ Hierarchical/Sequential 추론 | ✗ 단일 에이전트 미지원 | ✅ 노드 전환 감지 | ✅ on_messages() sender 추적 |
| 11 | **Workflow Execution** | 🔶 태스크명 키워드 추론 | 🔶 도구 호출 = 스텝 | ✅ 노드 실행 = 스텝 (실측) | 🔶 메시지 히스토리 기반 |

### Layer 2 — Security (5개)

> 모든 프레임워크에서 수동 호출 필요 (`enable_security_metrics=True`)

| # | 지표 | CrewAI | LangChain | LangGraph | AutoGen |
|---|------|--------|-----------|-----------|---------|
| 12 | **Input Sanitization** | 🔧 | 🔧 | 🔧 | 🔧 |
| 13 | **Output Leakage** | 🔧 | 🔧 | 🔧 | 🔧 |
| 14 | **Tool Authorization** | 🔧 | 🔧 | 🔧 | 🔧 |
| 15 | **Privilege Escalation** | 🔧 | 🔧 | 🔧 | 🔧 |
| 16 | **Tool Chain Attack** | 🔧 | 🔧 | 🔧 | 🔧 |

🔧 = `enable_security_metrics=True` + 직접 API 호출 필요

### Layer 3 — Hybrid (9개)

> `pip install agent-evaluator[eval]` + `OPENAI_API_KEY`
> 모든 프레임워크에서 `HybridPerformanceMonitor` 사용 시 동일하게 수집

| # | 지표 | 비고 |
|---|------|------|
| 17 | **G-Eval** | ✅ 전 프레임워크 |
| 18 | **Hallucination (DeepEval)** | ✅ retrieved_context 필요 |
| 19 | **Toxicity** | ✅ 전 프레임워크 |
| 20 | **Bias** | ✅ 전 프레임워크 |
| 21 | **Answer Relevancy (DeepEval)** | ✅ 전 프레임워크 |
| 22 | **Faithfulness (Ragas)** | ✅ retrieved_context 필요 |
| 23 | **Answer Relevancy (Ragas)** | ✅ retrieved_context 필요 |
| 24 | **Context Precision (Ragas)** | ✅ retrieved_context 필요 |
| 25 | **Context Recall (Ragas)** | ✅ retrieved_context 필요 |

**범례**: ✅ 자동 지원 | 🔶 부분/추정 | 🔧 수동 호출 | ✗ 미지원

---

## 토큰 측정 정확도 비교

| 프레임워크 | 측정 방식 | 정확도 |
|-----------|----------|--------|
| 🟢 LangChain | `llm_output["token_usage"]` (API 실제값) | ✅ 정확 |
| 🟣 AutoGen | tiktoken 우선 → 한/영 휴리스틱 fallback | 🔶 tiktoken 설치 시 정확 |
| 🟠 LangGraph | `AIMessage.usage_metadata` (LC LLM 사용 시) | 🔶 부분 수집 |
| 🔵 CrewAI | 초기값 0 고정 | ✗ 미수집 |

> **CrewAI 비용 측정**: `dataclasses.replace(task, tokens_used={"input": N, "output": M, "total": N+M})`으로 수동 설정하세요.

---

## 보안 지표 추가 (공통)

```python
# 방법 1: 데코레이터 security_mode (임시 활성, 권장)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa", security_mode=True)
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 방법 2: 팩토리 메서드 (영구 활성)
monitor = PerformanceMonitor.for_secure_agents(
    security_config={
        "allowed_tools": ["web_search", "db_lookup"],
        "restricted_tools": ["rm_rf", "system_exec"],
    },
    output_dir="results/",
)

# 방법 3: 독립 헬퍼 함수 (monitor 없이)
from agent_evaluator.helpers.taskresult_helpers import (
    validate_input_security,
    check_output_leakage,
)
input_result  = validate_input_security(user_input)   # {"is_safe": bool, "threats": [...]}
output_result = check_output_leakage(agent_response)  # {"has_leakage": bool, "leaked_types": [...]}
```

---

## 멀티턴 대화 평가 (공통)

v0.7.3부터 수동으로 세션을 관리하는 패턴 대신 데코레이터를 사용하는 것이 권장됩니다. `PerformanceMonitor`와 연동하여 자동으로 턴을 누적하고 지표를 계산합니다.

```python
from agent_evaluator import PerformanceMonitor, conversation_eval, flush_conversation

monitor = PerformanceMonitor("results/")

@conversation_eval(
    monitor,
    session_id_arg="sid",        # 세션 ID 파라미터 이름
    max_turns=10,                # 10턴 초과 시 자동 종료
    on_flush=lambda metrics, sid: print(f"세션 {sid} 종료: {metrics.overall_score:.2f}")
)
def chatbot_agent(user_message, sid="default"):
    # 실제 에이전트 호출 로직
    return response

# 1. 턴 호출 (자동 누적)
chatbot_agent("안녕하세요", sid="user_123")
chatbot_agent("서울 날씨 알려줘", sid="user_123")

# 2. 세션 명시적 종료 및 기록
flush_conversation("user_123")
```

데코레이터를 사용할 수 없는 복잡한 스크립트 환경에서는 컨텍스트 매니저 패턴을 사용합니다.

```python
# 컨텍스트 매니저 방식 (v0.6.3+)
with monitor.conversation("session_002") as conv:
    for user_msg in ["안녕", "누구니?"]:
        response = chatbot.respond(user_msg, history=conv.history)
        conv.turn(user=user_msg, agent=response, metadata={"latency": 0.5})
```

---

## 제한사항 및 주의사항

| 프레임워크 | 항목 | 원인 | 권장 대안 |
|-----------|------|------|----------|
| 🔵 CrewAI | 토큰 수 0 고정 | SDK 미노출 | `dataclasses.replace(task, tokens_used={...})` |
| 🔵 CrewAI | 도구 실행 시간 추정 | 내부 타이밍 접근 불가 | 허용 오차 내 사용 |
| 🟢 LangChain | Agent Coordination 미지원 | 단일 에이전트 | CrewAI 또는 AutoGen으로 교체 |
| 🟠 LangGraph | Token Economy 부분 수집 | LC LLM 미사용 시 | LangChain 통합 LLM 사용 |
| 🟣 AutoGen | 0.3.x 지원 제한 | async API 전환 | 0.4+ async API 또는 수동 `record_task()` |
| CrewAI/LangGraph | Retry attempts=1 고정 | 재시도 카운트 내부 은닉 | `retry_tracker.track_attempts()` 수동 호출 |

### `AgentCoordinationTracker` interaction_type 정규화

허용 canonical 값: `delegation`, `communication`, `collaboration`

자동 정규화 규칙 (v0.6.3+):

| 입력값 | 정규화 결과 |
|--------|------------|
| `task_delegation`, `handoff` | → `delegation` |
| `result_sharing`, `feedback`, `broadcast` | → `communication` |
| `coordination` | → `collaboration` |

그 외 알 수 없는 타입은 `delegation`으로 fallback + `WARNING` 로그 출력.

---

## 프레임워크 선택 가이드

| 사용 목적 | 권장 | 이유 |
|----------|------|------|
| 정확한 비용 추적 | 🟢 **LangChain** | 유일하게 실제 토큰 수 자동 수집 |
| 멀티에이전트 협업 분석 | 🔵 **CrewAI** | Agent Coordination + Tool Selection 자동 추적 |
| 복잡한 DAG / 상태 머신 | 🟠 **LangGraph** | 노드별 실측 타이밍 + Workflow Execution 자동 추적 |
| 대화형 에이전트 간 상호작용 | 🟣 **AutoGen** | 메시지 교환 자동 추적 (`run_sync()` 동기 래퍼 제공) |
| 전체 25개 지표 최대 커버리지 | 🟢 **LangChain** / 🟠 **LangGraph** | 공동 최고 ~82% |
| RAG 평가 | 🟢 **LangChain** + Layer 3 | `for_rag_evaluation()` + DeepEval/Ragas |
| 보안 중심 평가 | 전 프레임워크 | `for_secure_agents()` — 보안 5개 트래커 일괄 활성화 |

---

*Updated: 2026-04-13 (v0.7.9) | MIT License*
