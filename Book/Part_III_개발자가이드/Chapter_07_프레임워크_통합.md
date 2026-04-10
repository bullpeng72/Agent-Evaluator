# Chapter 7. 21개 프레임워크 통합

이 챕터에서 배우는 것: Agent-Evaluator SDK가 LangChain, CrewAI, AutoGen, DSPy, Anthropic, OpenAI 등 21개 프레임워크와 어떻게 통합되는지를 이해한다. `framework=` 파라미터 하나가 내부적으로 어떤 자동 추출 메커니즘을 작동시키는지, 각 프레임워크의 설치 방법과 주요 자동 추출 항목을 파악하고, 팀 상황에 맞는 프레임워크를 선택하는 기준을 배운다.

---

## 7.1 framework= 파라미터의 동작 원리

`@agent_eval(monitor, task_type="qa", framework="langchain")`처럼 `framework=`를 지정하면 데코레이터가 에이전트 함수의 반환값을 해당 프레임워크의 응답 객체로 간주하고 다음 항목들을 자동으로 추출한다:

- **`tokens_used`**: LLM API 실제 토큰 수 (TokenEconomyTracker에 전달)
- **`tool_calls`**: 사용된 도구 목록 (ToolCallAnalyzer, ToolSelectionTracker에 전달)
- **`chain_steps`**: 체인/노드 실행 단계 (WorkflowExecutionTracker에 전달)
- **`state_transitions`**: 상태 전이 시퀀스 (AgentCoordinationTracker에 전달)

이 과정이 `_FRAMEWORK_ADAPTERS` 레지스트리에 등록된 21개 어댑터 함수를 통해 이루어진다. 각 어댑터는 해당 프레임워크 고유의 응답 구조를 파악하고 SDK 내부 형식으로 변환한다.

### auto_detect_framework — 프레임워크 자동 감지

`framework=`를 명시하지 않아도 `auto_detect_framework=True`(기본값)가 응답 객체의 속성을 분석해 프레임워크를 자동 감지한다:

```python
from agent_evaluator import agent_eval, PerformanceMonitor

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

---

## 7.2 LangChain / LangGraph

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

**자동 추출 항목**: `usage_metadata` + `response_metadata.token_usage` 다중 메시지 누산, `ToolMessage` / `AIMessage`에서 chain_steps 추출, 타임스탬프 기반 실행 시간.

### LangGraph — 상태 머신 통합

LangGraph는 노드 단위 실행이 특징이다. Agent-Evaluator는 각 노드 전환을 `state_transitions`로 자동 캡처한다:

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
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

**자동 추출 항목**: 노드별 실측 타이밍, 노드 전환(AgentCoordination), Workflow Execution, `AIMessage.usage_metadata` 토큰.

---

## 7.3 CrewAI

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

**자동 추출 항목**: Agent Coordination (역할별 교환), Tool Selection F1. **주의**: CrewAI SDK가 토큰 수를 외부에 노출하지 않아 `tokens_used=0`으로 기록된다. 정확한 비용 측정이 필요하면 `EvalMetadata`를 통해 수동으로 주입한다:

```python
@crewai_eval(monitor, task_type="tool_use")
def run_crew(question: str, ground_truth: str = "") -> tuple:
    result = crew.kickoff(inputs={"topic": question})
    # 토큰 수 수동 주입
    meta = EvalMetadata(tokens_used={"input": 800, "output": 400, "total": 1200})
    return result.raw, meta
```

---

## 7.4 AutoGen

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

**자동 추출 항목**: 에이전트 메시지 교환(`agent_interactions`), `ToolCallEvent` 기반 도구 호출, tiktoken 기반 토큰 수 추정.

> 👨‍💻 **개발자 TIP**: AutoGen 0.4+의 async API 때문에 `@autogen_eval`로 래핑된 함수는 반드시 `async def`여야 한다. 동기 컨텍스트에서 호출할 때는 `asyncio.run()`을 사용한다. CrewAI와 AutoGen은 pydantic 버전 충돌이 발생할 수 있어 별도 가상환경에 격리하는 것을 권장한다.

---

## 7.5 DSPy / PydanticAI

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

**자동 추출**: `all_messages()` 우선 / `.messages` fallback, `ToolCallPart` / `ToolReturnPart` / `TextPart` 세분화 추출.

---

## 7.6 Anthropic / OpenAI / Gemini

직접 LLM API를 호출하는 패턴은 프레임워크 없이도 SDK와 통합된다.

### Anthropic — 캐시 토큰까지 추출

```python
import anthropic
from agent_evaluator import agent_eval, PerformanceMonitor

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

**자동 추출**: `content[].tool_use` (도구 호출), `usage.input_tokens` / `usage.output_tokens`, 캐시 토큰(`cache_creation_input_tokens` / `cache_read_input_tokens`, SDK ≥0.29).

### OpenAI

```python
from openai import OpenAI
from agent_evaluator import agent_eval, PerformanceMonitor

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

**자동 추출**: `choices[0].message.tool_calls`, `usage.total_tokens` / `usage.prompt_tokens` / `usage.completion_tokens`.

### Gemini

```python
import os
import google.generativeai as genai
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

@agent_eval(monitor, task_type="qa", framework="gemini")
def gemini_agent(question: str, ground_truth: str = "") -> object:
    return model.generate_content(question)  # GenerateContentResponse 전체 반환

gemini_agent("한국의 전통 음식 5가지를 알려줘", ground_truth="비빔밥, 김치...")
```

**자동 추출**: `candidates[0].content.parts[].function_call` (도구 호출), `usage_metadata` (토큰).

---

## 7.7 기타 프레임워크 간략 소개

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

## 7.8 프레임워크 선택 가이드

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

보안 지표: 모든 프레임워크 동일 (`enable_security_metrics=True` 또는 `security_mode=True`)

> 📋 **QA 관리자 TIP**: 평가 데이터의 신뢰성을 위해 토큰 비용 측정이 중요하다면 LangChain 또는 직접 API 호출(Anthropic/OpenAI) 방식을 선택해야 한다. CrewAI의 경우 EvalMetadata로 토큰을 수동 주입하지 않으면 `total_cost_usd=0`으로 기록되어 비용 분석이 불가능하다.

### 설치 조합 권장 가이드

```bash
# 대부분의 경우 — 경량 + 실용적
pip install "agent-evaluator[llm,serve]"

# LangChain 생태계 사용 시
pip install "agent-evaluator[langchain,serve]"

# 벤치마크 / 고급 평가 필요 시
pip install "agent-evaluator[eval]"   # DeepEval + Ragas

# crewai/autogen 격리 설치 (의존성 충돌 방지)
pip install "agent-evaluator[crewai]"   # 별도 가상환경
pip install "agent-evaluator[autogen]"  # 별도 가상환경

# 대부분 다 필요할 때 (권장 전체 구성)
pip install "agent-evaluator[all]"   # crewai/autogen/otel 제외 전체
```

---

## 이 챕터의 핵심

- **`framework=` 파라미터는 응답 객체 → SDK 내부 형식 변환기**다. 함수가 문자열이 아닌 SDK 응답 객체 전체를 반환해야 토큰 수, 도구 호출, 체인 단계가 자동 추출된다.
- **`auto_detect_framework=True`(기본값)**으로 12개 속성을 분석해 프레임워크를 자동 감지하므로, `framework=`를 명시하지 않아도 동작한다. 단, 정확도를 위해 명시 권장.
- **토큰 측정 정확도**는 LangChain > OpenAI/Anthropic > AutoGen(tiktoken) > CrewAI(0 고정) 순이다. CrewAI 비용 측정이 필요하면 `EvalMetadata`로 수동 주입한다.
- **CrewAI와 AutoGen은 무거운 의존성**으로 pydantic 버전 충돌이 발생할 수 있다. 별도 가상환경에 격리하거나 `[all]` extras를 사용한다.
- **프레임워크 선택 기준**: 빠른 프로토타입 → CrewAI, 기존 LangChain → LangChain/LangGraph, 타입 안전 → PydanticAI, ML 최적화 → DSPy, 완전한 제어 → 직접 API 호출.
