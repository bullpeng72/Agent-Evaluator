# Chapter 13. 21개 프레임워크 통합

이 챕터에서 배우는 것: Agent-Evaluator SDK가 LangChain, CrewAI, AutoGen, DSPy, Anthropic, OpenAI 등 21개 프레임워크와 어떻게 통합되는지를 이해한다. `framework=` 파라미터 하나가 내부적으로 어떤 자동 추출 메커니즘을 작동시키는지, 각 프레임워크의 설치 방법과 주요 자동 추출 항목을 파악하고, 팀 상황에 맞는 프레임워크를 선택하는 기준을 배운다.

---

## 13.1 framework= 파라미터의 동작 원리

`@agent_eval(monitor, task_type="qa", framework="langchain")`처럼 `framework=`를 지정하면 데코레이터가 에이전트 함수의 반환값을 해당 프레임워크의 응답 객체로 간주하고 다음 항목들을 자동으로 추출한다:

- **`tokens_used`**: LLM API 실제 토큰 수 (TokenEconomyTracker에 전달)
- **`tool_calls`**: 사용된 도구 목록 (ToolCallAnalyzer, ToolSelectionTracker에 전달)
- **`chain_steps`**: 체인/노드 실행 단계 (WorkflowExecutionTracker에 전달)
- **`state_transitions`**: 상태 전이 시퀀스 (AgentCoordinationTracker에 전달)

이 과정이 `_FRAMEWORK_ADAPTERS` 레지스트리에 등록된 21개 어댑터 함수를 통해 이루어진다. 각 어댑터는 해당 프레임워크 고유의 응답 구조를 파악하고 SDK 내부 형식으로 변환한다.

### auto_detect_framework — 프레임워크 자동 감지

`framework=`를 명시하지 않아도 `auto_detect_framework=True`(기본값)가 응답 객체의 속성을 분석해 프레임워크를 자동 감지한다:

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

# framework= 생략 — 응답 객체 속성으로 자동 감지
@agent_eval(monitor, task_type="qa")
def smart_agent(question: str, ground_truth: str = "") -> str:
    return any_llm_sdk.call(question)
```

자동 감지 기준 (12개 속성):

| 감지 속성 | 판정 프레임워크 |
|----------|--------------|
| `response.choices + response.usage` | openai |
| `response.content + response.model` (Anthropic 형식) | anthropic |
| `response.candidates` | gemini |
| `response._completions` | dspy |
| `response.all_messages()` 메서드 존재 | pydanticai |
| `response.tool_calls` (HF 형식) | huggingface |
| `response.text + response.meta` | cohere |

### get_framework_info() — 어댑터 메타데이터 조회

```python
from agent_evaluator.decorators import get_framework_info

info = get_framework_info("langchain")
# 반환:
# {
#   "extracts": ["tokens_used", "tool_calls", "chain_steps", "state_transitions"],
#   "description": "LangChain AgentExecutor/RunnableSequence 응답에서 메타데이터 추출",
#   "token_accuracy": "accurate"
# }
```

- `get_framework_info(name)`는 해당 어댑터가 추출하는 항목, 설명, 토큰 정확도를 dict로 반환한다
- `"extracts"` 키의 목록이 비어있거나 `"token_accuracy": "estimated"`이면 해당 프레임워크에서 토큰 수 측정이 부정확할 수 있다
- 지원되지 않는 프레임워크 이름을 입력하면 빈 dict가 반환된다

---

## 13.2 LangChain / LangGraph

LangChain은 Python AI 생태계에서 가장 성숙한 프레임워크다. Agent-Evaluator는 LangChain의 콜백 시스템과 응답 객체에서 정확한 토큰 수와 도구 호출 기록을 추출한다.

### 설치

```bash
pip install "agent-evaluator[langchain]"
# LangChain + LangGraph + langchain-core/openai/anthropic 포함
```

### LangChain 통합 예시

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# LangChain 에이전트 설정
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("user", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

# 데코레이터 적용 — 응답 객체 전체를 반환해야 자동 추출 가능
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> dict:
    # 응답 dict 전체 반환 (output 문자열이 아님)
    return agent_executor.invoke({"input": question})

# 평가 실행
lc_agent("서울의 오늘 날씨는?", ground_truth="맑음, 15도")
lc_agent("파이썬으로 피보나치 수열을 구현해줘", ground_truth="def fibonacci...")

report = monitor.generate_report()
monitor.save_to_file("langchain_eval")
```

- `framework="langchain"` 지정 시 `agent_executor.invoke()` 반환값 전체(`dict`)를 함수가 반환해야 `intermediate_steps`에서 tool_calls가 추출된다
- `usage_metadata`와 `response_metadata.token_usage` 두 경로를 모두 탐색하며, 다중 메시지가 있으면 누산해 `tokens_used`를 계산한다
- `PerformanceMonitor.for_rag_evaluation()`은 hallucination_detection이 활성화된 monitor를 반환한다

**자동 추출 항목**: `usage_metadata` + `response_metadata.token_usage` 다중 메시지 누산, `ToolMessage` / `AIMessage`에서 chain_steps 추출, 타임스탬프 기반 실행 시간.

### LangGraph — 상태 머신 통합

LangGraph는 노드 단위 실행이 특징이다. Agent-Evaluator는 각 노드 전환을 `state_transitions`로 자동 캡처한다:

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from agent_evaluator import PerformanceMonitor
from agent_evaluator.integrations import langgraph_eval

monitor = PerformanceMonitor(output_dir="results/")

@langgraph_eval(monitor, task_type="qa")
def lg_agent(question: str, ground_truth: str = "") -> str:
    # LangGraph AIMessage 응답 — usage_metadata 자동 추출
    result = compiled_graph.invoke(
        {"messages": [HumanMessage(content=question)]}
    )
    return result["messages"][-1]  # AIMessage 객체 반환

lg_agent("보고서 초안 작성해줘", ground_truth="초안 완성")
```

- `@langgraph_eval`은 LangGraph 전용 데코레이터로, 그래프의 노드 전환(`state_transitions`)을 자동으로 캡처한다
- `result["messages"][-1]`처럼 마지막 `AIMessage` 객체를 반환하면 `usage_metadata`에서 토큰 수를 자동 추출한다
- 노드별 실행 시간이 각각 `chain_steps`에 기록되어 WorkflowExecutionTracker로 전달된다

**자동 추출 항목**: 노드별 실측 타이밍, 노드 전환(AgentCoordination), Workflow Execution, `AIMessage.usage_metadata` 토큰.

---

## 13.3 CrewAI

CrewAI는 역할 기반 멀티에이전트 시스템으로, Researcher + Writer + Reviewer 같은 역할을 가진 에이전트들이 협력하는 구조다.

### 설치

```bash
pip install "agent-evaluator[crewai]"
# 주의: 전이 의존성 100개+, 독립 가상환경 권장
```

### CrewAI 통합 예시

```python
from crewai import Crew, Agent, Task, Process
from agent_evaluator import PerformanceMonitor, EvalMetadata
from agent_evaluator.integrations import crewai_eval

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

# CrewAI 구성
researcher = Agent(
    role="Research Analyst",
    goal="정확한 정보를 수집하고 분석한다",
    llm="gpt-4o-mini",
)
writer = Agent(
    role="Content Writer",
    goal="수집된 정보를 명확한 보고서로 작성한다",
    llm="gpt-4o-mini",
)

task1 = Task(description="{topic} 관련 최신 정보를 조사하라", agent=researcher)
task2 = Task(description="조사 결과를 500자 보고서로 작성하라", agent=writer)

crew = Crew(
    agents=[researcher, writer],
    tasks=[task1, task2],
    process=Process.sequential,
)

@crewai_eval(monitor, task_type="tool_use")
def run_crew(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return result  # CrewOutput 객체 전체 반환 — 자동 파싱

run_crew("AI 트렌드 2026", ground_truth="보고서 완성")
monitor.save_to_file("crewai_eval")
```

- `@crewai_eval`은 `crew.kickoff()` 반환값인 `CrewOutput` 객체에서 에이전트 간 교환 기록을 자동 추출한다
- `result` 전체를 반환하면 어댑터가 에이전트 역할별 상호작용을 `agent_interactions` 형식으로 파싱한다
- `PerformanceMonitor.for_secure_agents()`는 보안 지표(`enable_security_metrics=True`)가 활성화된 monitor를 반환한다

**자동 추출 항목**: Agent Coordination (역할별 교환), Tool Selection F1. **주의**: CrewAI SDK가 토큰 수를 외부에 노출하지 않아 `tokens_used=0`으로 기록된다. 정확한 비용 측정이 필요하면 `EvalMetadata`를 통해 수동으로 주입한다:

```python
@crewai_eval(monitor, task_type="tool_use")
def run_crew(question: str, ground_truth: str = "") -> tuple:
    result = crew.kickoff(inputs={"topic": question})
    # 토큰 수 수동 주입
    meta = EvalMetadata(tokens_used={"input": 800, "output": 400, "total": 1200})
    return result.raw, meta
```

- 함수가 `(응답, EvalMetadata)` 튜플을 반환하면 데코레이터가 자동으로 `EvalMetadata`를 분리해 처리한다
- `tokens_used` dict는 `{"input": N, "output": M, "total": T}` 형식이어야 한다
- CrewAI 비용 측정이 필요한 경우 LLM API 응답에서 토큰 수를 직접 읽거나 tiktoken으로 추정해 주입한다

---

## 13.4 AutoGen

AutoGen 0.4+는 async-first API를 채택했다. 복잡한 멀티에이전트 대화를 비동기로 처리하며, Agent-Evaluator는 에이전트 간 메시지 교환에서 `agent_interactions`를 자동 추출한다.

### 설치

```bash
pip install "agent-evaluator[autogen]"
# pyautogen>=0.3.0 + autogen-agentchat/core>=0.4.0
```

### AutoGen 비동기 통합 예시

```python
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from agent_evaluator import PerformanceMonitor
from agent_evaluator.integrations import autogen_eval

monitor = PerformanceMonitor(output_dir="results/")

model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")

@autogen_eval(monitor, task_type="tool_use")
async def run_autogen(question: str, ground_truth: str = "") -> str:
    agent1 = AssistantAgent("assistant_1", model_client=model_client)
    agent2 = AssistantAgent("assistant_2", model_client=model_client)
    team = RoundRobinGroupChat([agent1, agent2], max_turns=3)

    result = await team.run(task=question)
    return result  # TeamRunResult 객체 전체 반환

# 비동기 실행
asyncio.run(run_autogen("멀티에이전트 협업 전략 제안", ground_truth="전략 완성"))
monitor.save_to_file("autogen_eval")
```

- `@autogen_eval`로 래핑된 함수는 반드시 `async def`여야 한다. AutoGen 0.4+는 async-first API를 채택했기 때문이다
- `result` 전체(`TeamRunResult` 객체)를 반환하면 에이전트 간 메시지 교환이 `agent_interactions`로 자동 추출된다
- 토큰 수는 tiktoken으로 추정되므로 실제 API 비용과 약간의 오차가 있을 수 있다

**자동 추출 항목**: 에이전트 메시지 교환(`agent_interactions`), `ToolCallEvent` 기반 도구 호출, tiktoken 기반 토큰 수 추정.

> 👨‍💻 **개발자 TIP**: AutoGen 0.4+의 async API 때문에 `@autogen_eval`로 래핑된 함수는 반드시 `async def`여야 한다. 동기 컨텍스트에서 호출할 때는 `asyncio.run()`을 사용한다. CrewAI와 AutoGen은 pydantic 버전 충돌이 발생할 수 있어 별도 가상환경에 격리하는 것을 권장한다.

---

## 13.5 DSPy / PydanticAI

### DSPy — 프로그래밍 방식 LLM 파이프라인

DSPy는 프롬프트를 코드로 관리하는 독특한 접근 방식을 취한다. `_completions` 속성과 LM history를 기반으로 chain_steps를 추출한다:

```bash
pip install "agent-evaluator[dspy]"
```

```python
import dspy
from agent_evaluator import PerformanceMonitor
from agent_evaluator.integrations import dspy_eval

monitor = PerformanceMonitor("results/")

# DSPy 프로그램 정의
class QASignature(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()

qa_program = dspy.ChainOfThought(QASignature)
dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))

@dspy_eval(monitor, task_type="reasoning")
def dspy_agent(question: str, ground_truth: str = "") -> str:
    result = qa_program(question=question)
    return result  # dspy.Prediction 객체 전체 반환

dspy_agent("태양계에서 가장 큰 행성은?", ground_truth="목성")
```

- `@dspy_eval`은 DSPy `Prediction` 객체의 `_completions` 속성에서 chain_steps를 추출한다
- `result` 전체(`dspy.Prediction`)를 반환해야 LM history와 중간 추론 단계가 자동 파싱된다
- `task_type="reasoning"`은 Multi-step chain 분석을 활성화해 chain_steps 기반 WorkflowExecution 지표를 계산한다

**자동 추출**: `_completions` / `completions` 속성 기반, LM history에서 multi-step chain_steps 구성, `tool_calls` / `actions` 추출.

### PydanticAI — 타입 안전 에이전트

PydanticAI는 Pydantic 기반의 타입 안전한 에이전트 프레임워크다:

```bash
pip install "agent-evaluator[pydanticai]"
```

```python
from pydantic_ai import Agent
from pydantic import BaseModel
from agent_evaluator import PerformanceMonitor
from agent_evaluator.integrations import pydanticai_eval

monitor = PerformanceMonitor("results/")

class AnswerModel(BaseModel):
    answer: str
    confidence: float

pydantic_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=AnswerModel,
    system_prompt="정확한 답변을 제공하는 전문가입니다.",
)

@pydanticai_eval(monitor, task_type="qa")
async def pa_agent(question: str, ground_truth: str = "") -> str:
    result = await pydantic_agent.run(question)
    return result  # AgentRunResult 객체 전체 반환

import asyncio
asyncio.run(pa_agent("파이썬의 GIL이란?", ground_truth="Global Interpreter Lock"))
```

- `@pydanticai_eval`로 래핑된 함수는 `async def`여야 한다. PydanticAI의 `agent.run()`은 코루틴을 반환한다
- `result` 전체(`AgentRunResult` 객체)를 반환해야 `all_messages()`를 통해 대화 이력과 도구 호출이 추출된다
- `result_type=AnswerModel`처럼 Pydantic 모델을 지정하면 구조화된 응답이 자동으로 검증되므로 타입 안전성이 보장된다

**자동 추출**: `all_messages()` 우선 / `.messages` fallback, `ToolCallPart` / `ToolReturnPart` / `TextPart` 세분화 추출.

---

## 13.6 Anthropic / OpenAI / Gemini

직접 LLM API를 호출하는 패턴은 프레임워크 없이도 SDK와 통합된다.

### Anthropic — 캐시 토큰까지 추출

```python
import anthropic
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")
client = anthropic.Anthropic()

@agent_eval(monitor, task_type="qa", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> anthropic.types.Message:
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[
            {
                "name": "web_search",
                "description": "웹에서 정보를 검색합니다",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}
            }
        ],
        messages=[{"role": "user", "content": question}]
    )  # Message 객체 전체 반환

claude_agent("최신 AI 연구 동향은?", ground_truth="GPT-4, Claude 3.5 등")
```

- `framework="anthropic"` 지정 시 함수가 `anthropic.types.Message` 객체 전체를 반환해야 토큰 수와 도구 호출이 자동 추출된다
- `usage.input_tokens` / `usage.output_tokens`와 함께 캐시 토큰(`cache_creation_input_tokens`, `cache_read_input_tokens`)도 자동으로 수집된다 (SDK ≥0.29)
- `content[].tool_use` 블록에서 도구 호출 기록을 추출해 ToolCallAnalyzer에 전달한다

**자동 추출**: `content[].tool_use` (도구 호출), `usage.input_tokens` / `usage.output_tokens`, 캐시 토큰(`cache_creation_input_tokens` / `cache_read_input_tokens`, SDK ≥0.29).

### OpenAI

```python
from openai import OpenAI
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")
client = OpenAI()

@agent_eval(monitor, task_type="tool_use", framework="openai")
def openai_agent(question: str, ground_truth: str = "") -> object:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        tools=[{
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "수학 계산을 수행합니다",
                "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}
            }
        }],
        messages=[{"role": "user", "content": question}]
    )  # ChatCompletion 객체 전체 반환

openai_agent("123 * 456의 값은?", ground_truth="56088")
```

- `framework="openai"` 지정 시 함수가 `ChatCompletion` 객체 전체를 반환해야 tool_calls와 usage가 자동 추출된다
- `choices[0].message.tool_calls`에서 함수 호출 목록이, `usage` 필드에서 `prompt_tokens` / `completion_tokens`가 추출된다
- OpenAI Responses API(`openai.responses.create()`) 응답도 동일한 어댑터로 처리된다

**자동 추출**: `choices[0].message.tool_calls`, `usage.total_tokens` / `usage.prompt_tokens` / `usage.completion_tokens`.

### Gemini

```python
import os
import google.generativeai as genai
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

@agent_eval(monitor, task_type="qa", framework="gemini")
def gemini_agent(question: str, ground_truth: str = "") -> object:
    return model.generate_content(question)  # GenerateContentResponse 전체 반환

gemini_agent("한국의 전통 음식 5가지를 알려줘", ground_truth="비빔밥, 김치...")
```

- `framework="gemini"` 지정 시 `GenerateContentResponse` 전체를 반환해야 도구 호출과 토큰 수가 추출된다
- `candidates[0].content.parts[].function_call`에서 도구 호출이, `usage_metadata`에서 `prompt_token_count` / `candidates_token_count`가 추출된다
- `google.generativeai` SDK와 `google-cloud-aiplatform` (VertexAI) 모두 동일한 어댑터로 처리된다

**자동 추출**: `candidates[0].content.parts[].function_call` (도구 호출), `usage_metadata` (토큰).

---

## 13.7 기타 프레임워크 간략 소개

다음 표는 나머지 지원 프레임워크의 설치 방법과 주요 추출 항목을 정리한 것이다:

| 프레임워크 | 설치 extras | 추출 항목 | 특이사항 |
|-----------|-----------|----------|--------|
| **LlamaIndex** | `pip install llama-index` | `source_nodes` → chain_steps, AgentChatResponse.sources | ToolOutput에서 도구 호출 추출 |
| **Haystack** | `pip install haystack-ai` | 파이프라인 컴포넌트 dict → chain_steps | retriever/reader/embedder → tool_calls 변환 |
| **Cohere** | `pip install cohere` | `documents`, `tool_calls`, `meta.tokens` | |
| **Groq** | `pip install groq` | OpenAI 호환 형식 (`choices`, `usage`) | 거의 OpenAI와 동일 |
| **Mistral** | `pip install mistralai` | `choices[0].message.tool_calls`, `usage` | function_call 구버전 호환 |
| **Ollama** | `pip install ollama` | `message.tool_calls`, `prompt_eval_count` | 로컬 모델 |
| **Bedrock** | AWS SDK 포함 | `usage.inputTokens`, `content[].toolUse` | boto3 응답 구조 |
| **smolagents** | `pip install smolagents` | `logs` 필드에서 agent_steps 추출 | |
| **Semantic Kernel** | `pip install semantic-kernel` | `function_name + plugin_name` → tool_calls | "Plugin.function" 형식 |
| **vLLM** | `pip install vllm` | OpenAI 호환 형식 (`choices`, `usage`) | 고성능 추론 서버 |
| **HuggingFace** | `pip install transformers` | `tool_calls`, `usage` | HF Inference API |
| **VertexAI** | `pip install google-cloud-aiplatform` | Gemini와 동일 구조 | GCP 관리형 서비스 |

---

## 13.8 프레임워크 선택 가이드

프레임워크 선택은 팀의 Python 숙련도, 기존 기술 스택, 그리고 에이전트 아키텍처의 복잡도에 따라 달라진다.

### 생산성 vs 제어력 트레이드오프

```
높은 생산성 (추상화 높음)               낮은 생산성 (추상화 낮음)
        │                                        │
  CrewAI                                   직접 API 호출
  AutoGen            LangGraph              (Anthropic/OpenAI)
        │            LangChain       DSPy           │
        │                │            │             │
  빠른 프로토타입     균형점      프로그래밍    완전한 제어
  역할 기반 설계   최적화 가능    방식 최적화   비용 추적 정확
```

### 팀 배경별 권장표

| 팀 배경 | 1순위 | 2순위 | 이유 |
|---------|------|------|------|
| Python 초심자 + 빠른 프로토타입 | CrewAI | LangChain | 선언적 API, 학습 비용 낮음 |
| LangChain 기존 사용자 | LangChain | LangGraph | 기존 코드 재사용, 전환 비용 없음 |
| 복잡한 상태 관리 필요 | LangGraph | AutoGen | 노드별 상태 제어, DAG 구조 |
| Microsoft 기술 스택 | AutoGen | Semantic Kernel | Azure OpenAI 통합 친화적 |
| ML 엔지니어 / 실험 최적화 | DSPy | PydanticAI | 프롬프트를 코드로 최적화 |
| 타입 안전성 최우선 | PydanticAI | LangChain | Pydantic 기반 런타임 검증 |
| LLM API 직접 제어 | Anthropic/OpenAI | Gemini | 최정확 토큰 측정, 최저 지연 |
| 로컬 모델 / 비용 절감 | Ollama | vLLM | 온프레미스 추론, API 비용 없음 |

### Agent-Evaluator 지표 지원 관점 권장 우선순위

토큰 측정 정확도: LangChain > OpenAI/Anthropic > AutoGen (tiktoken) > LangGraph (부분) > CrewAI (0 고정)

멀티에이전트 지표(AgentCoordination): AutoGen > CrewAI > LangGraph > LangChain (단일 에이전트)

보안 지표: 모든 프레임워크 동일 (`enable_security_metrics=True` 또는 `security=SecurityConfig()`)

> 📋 **QA 관리자 TIP**: 평가 데이터의 신뢰성을 위해 토큰 비용 측정이 중요하다면 LangChain 또는 직접 API 호출(Anthropic/OpenAI) 방식을 선택해야 한다. CrewAI의 경우 EvalMetadata로 토큰을 수동 주입하지 않으면 `total_cost_usd=0`으로 기록되어 비용 분석이 불가능하다.

### 설치 조합 권장 가이드

```bash
# 기본 설치 — LLMJudge · 대시보드 · OTEL · PDF 포함 (권장)
pip install agent-evaluator

# LangChain 생태계 사용 시 (에이전트 코드가 LangChain을 사용하는 경우)
pip install "agent-evaluator[langchain]"

# 벤치마크 / 고급 평가 필요 시
pip install "agent-evaluator[eval]"   # DeepEval + Ragas

# crewai/autogen 격리 설치 (의존성 충돌 방지)
pip install "agent-evaluator[crewai]"   # 별도 가상환경
pip install "agent-evaluator[autogen]"  # 별도 가상환경

# 전체 설치 (⚠️ crewai/autogen 포함, 10분+)
pip install "agent-evaluator[full]"
```

---

## 이 챕터의 핵심

- **`framework=` 파라미터는 응답 객체 → SDK 내부 형식 변환기**다. 함수가 문자열이 아닌 SDK 응답 객체 전체를 반환해야 토큰 수, 도구 호출, 체인 단계가 자동 추출된다.
- **`auto_detect_framework=True`(기본값)**으로 12개 속성을 분석해 프레임워크를 자동 감지하므로, `framework=`를 명시하지 않아도 동작한다. 단, 정확도를 위해 명시 권장.
- **토큰 측정 정확도**는 LangChain > OpenAI/Anthropic > AutoGen(tiktoken) > CrewAI(0 고정) 순이다. CrewAI 비용 측정이 필요하면 `EvalMetadata`로 수동 주입한다.
- **CrewAI와 AutoGen은 무거운 의존성**으로 pydantic 버전 충돌이 발생할 수 있다. 별도 가상환경에 격리하거나 `[full]` extras를 사용한다.
- **프레임워크 선택 기준**: 빠른 프로토타입 → CrewAI, 기존 LangChain → LangChain/LangGraph, 타입 안전 → PydanticAI, ML 최적화 → DSPy, 완전한 제어 → 직접 API 호출.

---

## 실전 예제

`ch13_frameworks.py`는 LangChain, LangGraph, CrewAI, AutoGen 4개 프레임워크를 하나의 파일에서 비교 평가하고, 크로스 프레임워크 파이프라인까지 실행하는 종합 예제다. 각 프레임워크의 `framework=` 파라미터 사용법과 응답 객체 구조 차이를 직접 확인할 수 있다.

**파일**: `Evaluator_Examples/ch13_frameworks.py`

**핵심 코드 (출처: `Evaluator_Examples/ch13_frameworks.py`)**

**섹션 1 — LangChain 어댑터 (`framework="langchain"`)**

```python
# 출처: Evaluator_Examples/ch13_frameworks.py, 섹션 1
from types import SimpleNamespace
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

def _make_langchain_response(answer: str, tools: list, tokens: dict):
    """LangChain AgentExecutor 응답 구조 시뮬레이션."""
    steps = [(SimpleNamespace(tool=t, tool_input="query"), f"{t} 결과") for t in tools]
    return SimpleNamespace(
        output=answer,
        intermediate_steps=steps,   # tool_calls 자동 추출
        usage_metadata={"input_tokens": tokens["input"], "output_tokens": tokens["output"]},  # tokens_used 자동 추출
    )

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="lc")
def langchain_agent(question: str, ground_truth: str = ""):
    return _make_langchain_response(
        answer="LangChain 검색 결과입니다.",
        tools=["web_search", "calculator", "wikipedia"],
        tokens={"input": 350, "output": 120},
    )

langchain_agent("최신 파이썬 버전은?", ground_truth="3.12")
```

- `framework="langchain"` 지정 시 어댑터가 `response.intermediate_steps`에서 tool_calls를, `usage_metadata`에서 tokens_used를 자동 추출한다
- 실제 LangChain SDK 없이 동일한 구조의 객체(`SimpleNamespace`)를 mock으로 사용해도 어댑터가 동작한다 — duck typing 방식
- 추출된 `tool_calls`는 ToolCallAnalyzer, ToolSelectionTracker에, `tokens_used`는 TokenEconomyTracker에 자동 전달된다

**섹션 5 — 크로스 프레임워크 파이프라인**

```python
# 출처: Evaluator_Examples/ch13_frameworks.py, 섹션 5
from types import SimpleNamespace

@agent_eval(monitor, task_type="planning", framework="langgraph", task_id_prefix="pipe_route")
def routing_stage(question: str, ground_truth: str = ""):
    """Stage 1: LangGraph 라우터."""
    return {
        "messages": [SimpleNamespace(content=f"라우팅 완료: {question}", type="ai",
                     response_metadata={"token_usage": {"prompt_tokens": 200, "completion_tokens": 80}})],
        "graph_traversal": {"nodes_visited": ["router", "splitter", "dispatcher"]},
        "state_transitions": [{"from": "router", "to": "splitter", "trigger": "tool_call"}],
    }

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="pipe_search")
def search_stage(question: str, ground_truth: str = ""):
    """Stage 2: LangChain 검색."""
    steps = [(SimpleNamespace(tool="web_search", tool_input="query"), "검색 결과")]
    return SimpleNamespace(
        output=f"검색 결과: {question}",
        intermediate_steps=steps,
        usage_metadata={"input_tokens": 450, "output_tokens": 150},
    )

for task in ["경제 위기 예측 보고서", "신제품 출시 전략"]:
    routing_stage(task, ground_truth="라우팅 완료")
    search_stage(task,   ground_truth="검색 완료")
    print(f"파이프라인 완료: {task}")
```

- 하나의 `monitor`로 LangGraph → LangChain → CrewAI 순서의 파이프라인을 통합 평가한다
- 각 단계마다 다른 `framework=` 파라미터를 사용해도 모두 같은 monitor에 기록된다
- `agent-eval dashboard results/`를 실행하면 파이프라인 전체 태스크가 단일 대시보드에서 비교 가능하다

**섹션 6 — @batch_eval 프레임워크 비교**

```python
# 출처: Evaluator_Examples/ch13_frameworks.py, 섹션 6
from agent_evaluator.decorators import batch_eval

BENCHMARK_QA = [
    ("GDP란?", "국내총생산"),
    ("CPU란?", "중앙처리장치"),
    ("API란?", "응용 프로그램 인터페이스"),
]

@batch_eval(monitor, task_type="qa", task_id_prefix="bench_lc")
def lc_batch(questions: list, ground_truths: list = None) -> list:
    return [f"[LangChain] {q}에 대한 답변" for q in questions]

@batch_eval(monitor, task_type="qa", task_id_prefix="bench_crew")
def crew_batch(questions: list, ground_truths: list = None) -> list:
    return [f"[CrewAI] {q}에 대한 답변" for q in questions]

lc_results   = lc_batch([q for q, _ in BENCHMARK_QA], ground_truths=[gt for _, gt in BENCHMARK_QA])
crew_results = crew_batch([q for q, _ in BENCHMARK_QA], ground_truths=[gt for _, gt in BENCHMARK_QA])
# monitor.generate_report()로 두 프레임워크 TCR/accuracy 비교 가능
```

- 같은 `monitor`에 다른 `task_id_prefix`를 붙여 프레임워크별로 결과를 구분한다
- 대시보드의 `/tasks/filter?task_id_prefix=bench_lc` vs `bench_crew`로 직접 비교 가능하다
- CrewAI는 `tokens_used`가 0으로 고정되는 제약이 있으므로 TokenEconomy 비교에서는 제외한다

```bash
python Evaluator_Examples/ch13_frameworks.py
agent-eval dashboard results/
```

**예제 구성**

| 섹션 | 내용 | 연관 기능 |
|------|------|-----------|
| 섹션 1 | LangChain 에이전트 평가 | `framework="langchain"`, chain_steps 자동 추출 |
| 섹션 2 | LangGraph 워크플로우 평가 | `framework="langgraph"`, state_transitions 자동 추출 |
| 섹션 3 | CrewAI 멀티에이전트 평가 | `framework="crewai"`, agent_interactions 추출 |
| 섹션 4 | AutoGen 대화형 에이전트 평가 | `framework="autogen"`, multi-step 대화 추적 |
| 섹션 5 | 크로스 프레임워크 파이프라인 | 서로 다른 프레임워크 에이전트를 하나의 monitor로 통합 |
| 섹션 6 | 배치 비교 평가 | `@batch_eval`로 4개 프레임워크 동시 벤치마크 |

**실행 결과 (v0.8.4 기준)**

```
=== 03. 프레임워크 어댑터 종합 예제 ===

[섹션 1] LangChain 에이전트
  langchain_research_agent: TCR=75.0%, accuracy=0.821, chain_steps=3
  langchain_qa_agent: TCR=83.3%, accuracy=0.756

[섹션 2] LangGraph 워크플로우
  langgraph_workflow: state_transitions=['start','retrieve','generate','end'], TCR=66.7%

[섹션 3] CrewAI 멀티에이전트
  crewai_team: agent_interactions=4, TCR=50.0%, tokens_used=0 (추적 불가)

[섹션 4] AutoGen 대화형 에이전트
  autogen_conv: attempts=3, TCR=58.3%

[섹션 5] 크로스 프레임워크 파이프라인
  pipeline_result: 4개 프레임워크 순차 실행, 통합 TCR=50.0%

[섹션 6] 배치 비교
  총 24개 태스크 | TCR=50.0% | 평균 정확도=0.643
  최고 프레임워크: langchain (accuracy 0.821)
  최저 프레임워크: crewai (tokens_used 0 — CrewAI 제한)

📊 대시보드: http://localhost:8765
```

> **핵심**: `framework="crewai"`를 지정해도 `tokens_used`는 0으로 고정된다. CrewAI는 토큰 수를 응답 객체에 노출하지 않기 때문이다. 비용 측정이 필요하면 `EvalMetadata(tokens_used=실제값)`으로 수동 주입한다. 반대로 `framework="langchain"`은 `response.usage.total_tokens`를 자동 추출하므로 별도 처리 없이 TokenEconomyTracker에 정확한 값이 전달된다.

**Phoenix OTEL — 프레임워크별 스팬 시각화 (출처: `Evaluator_Examples/ch19_phoenix.py`)**

`setup_otel()` + `framework=` 파라미터를 함께 사용하면 LangChain·CrewAI·AutoGen 각 프레임워크의 tool_calls·agent_interactions가 Phoenix Traces 탭에서 프레임워크별로 구분되어 표시된다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — 프레임워크 통합 + Phoenix 스팬 전송
import socket
from types import SimpleNamespace
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# Phoenix 연결 (있을 때만 활성화)
try:
    with socket.create_connection(("localhost", 6006), timeout=1):
        setup_otel(endpoint="http://localhost:6006", service_name="framework-adapters")
except OSError:
    pass

monitor = PerformanceMonitor(output_dir="results/", enable_transparency=True)

# LangChain 에이전트 — tool_calls·tokens 자동 추출 → Phoenix 스팬으로 전송
@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="lc_phoenix")
def langchain_agent(question: str, ground_truth: str = ""):
    steps = [(SimpleNamespace(tool="web_search", tool_input=question), "검색 결과")]
    return SimpleNamespace(
        output=f"결과: {question}",
        intermediate_steps=steps,
        usage_metadata={"input_tokens": 350, "output_tokens": 120},
    )

langchain_agent("2026 AI 트렌드 분석", ground_truth="분석 완료")
# → Phoenix Traces 탭: service_name="framework-adapters", framework="langchain"
# → span 속성: ae.tool_calls, ae.tokens_used, ae.framework 자동 기록
# → agent-eval monitor 실행 후 http://localhost:6006 에서 확인 가능
```

```bash
# 2-터미널 패턴: Phoenix + 프레임워크 어댑터 동시 실행
# 터미널 1: agent-eval monitor
# 터미널 2: python Evaluator_Examples/ch13_frameworks.py
# → Phoenix Traces 탭에서 LangChain·LangGraph·CrewAI·AutoGen 스팬 비교 가능
```
