# 🔌 프레임워크 통합 가이드

LangChain, LangGraph, CrewAI, AutoGen 통합 방법

# 프레임워크 통합 가이드

> 🔌 LangChain, LangGraph, CrewAI, AutoGen과 Agent Evaluator 통합 완벽 가이드

## 버전 정보

**현재 버전:** v0.6.0

**최종 업데이트:** 2026-03-23

이 문서는 주요 AI Agent 프레임워크에 Agent Evaluator를 통합하는 방법을 상세히 설명합니다.

**주요 기능:**

  * 🎯 **Layer 1 메트릭** : TCR, Accuracy, Cost 자동 추적
  * 🚀 **Layer 2 메트릭** : Tool Selection, Agent Coordination, Workflow Execution 자동 평가
  * 🔧 **프레임워크별 최적화** : 최적화된 콜백/래퍼 클래스
  * 📊 **실시간 모니터링** : 리포트 생성

## 호환성 및 요구사항

### 필수 및 권장 버전

**Agent Evaluator v0.6.0** 호환성 정보:

구분 | 패키지 | 버전 요구사항 | 설치 명령
---|---|---|---
**필수** | Python | 3.8+ | -
**필수** | Agent Evaluator | 0.6.0 | `pip install agent-evaluator`
**선택 (프레임워크)** | CrewAI | 1.0.0+ | `pip install crewai`
**선택 (프레임워크)** | LangChain | 1.0.0+ | `pip install langchain`
**선택 (프레임워크)** | LangGraph | 1.0.0+ | `pip install langgraph`
**선택 (프레임워크)** | AutoGen | autogen-agentchat/core ≥0.4.0 | `pip install autogen-agentchat autogen-core`
**선택 (고급 메트릭)** | DeepEval | 0.20.0+ | `pip install deepeval`
**선택 (RAG 평가)** | Ragas | 0.4.0+ | `pip install ragas`  
  
### 설치 방법

**기본 설치** (Layer 1 메트릭)

```bash
    [](<#cb1-1>)pip install agent-evaluator
```

**고급 메트릭 포함** (Layer 3)

```bash
    [](<#cb2-1>)pip install agent-evaluator deepeval ragas
```

**프레임워크별 설치**

```bash
    [](<#cb3-1>)# CrewAI + Agent Evaluator
    [](<#cb3-2>)pip install crewai agent-evaluator
    [](<#cb3-3>)
    [](<#cb3-4>)# LangChain + Agent Evaluator
    [](<#cb3-5>)pip install langchain langchain-openai agent-evaluator
    [](<#cb3-6>)
    [](<#cb3-7>)# AutoGen + Agent Evaluator
    [](<#cb3-8>)pip install autogen-agentchat autogen-core agent-evaluator
```

### 호환성 참고사항

  * **Python 3.8+** 필수 (3.12까지 테스트 완료)
  * **프레임워크** : CrewAI, LangChain, LangGraph, AutoGen 모두 지원
  * **고급 메트릭** : DeepEval (0.20.0+), Ragas (0.4.0+) 선택 설치
  * **의존성** : numpy (1.20.0+), pandas (1.3.0+) 자동 설치

* * *

## 목차

  * [1\. LangChain 통합](<#langchain-통합>)
  * [2\. LangGraph 통합](<#langgraph-통합>)
  * [3\. CrewAI 통합](<#crewai-통합>)
  * [4\. AutoGen 통합](<#autogen-통합>)
  * [5\. 프레임워크 비교](<#프레임워크-비교>)
  * [6\. Layer 2 메트릭 자동 추적](<#layer-2-메트릭-자동-추적>)
  * [7\. 모범 사례](<#모범-사례>)
  * [💻 개발자 가이드 (Developer Guide)](<#dev-guide>)
    * [8.1 실전 구현 가이드](<#dev-implementation>)
    * [8.2 성능 최적화](<#dev-performance>)
    * [8.3 디버깅 및 문제 해결](<#dev-debugging>)
    * [8.4 프로덕션 배포](<#dev-production>)
    * [8.5 고급 활용](<#dev-advanced>)

* * *

## 1\. LangChain 통합

**✨ LangChainEvaluator** \- LangChain 전용 평가 클래스

Layer 1/2/3 완전 지원, 동적 계산, 자동 Tool Selection 및 Workflow 추적

```python
    from agent_evaluator.integrations import LangChainEvaluator
    evaluator = LangChainEvaluator(agent, enable_layer2=True)
```

자세한 내용은 [API Reference](<API_REFERENCE.html#langchain-evaluator>)를 참고하세요.

### 1.1 LangChain 소개

**LangChain** 은 LLM 기반 애플리케이션 개발을 위한 프레임워크입니다.

**주요 특징**

  * ⛓️ **체인** : 여러 단계를 연결
  * 🧠 **메모리** : 대화 기록 유지
  * 🔧 **도구** : 다양한 도구 통합
  * 🤖 **에이전트** : 자율적 의사결정

### 1.2 설치

```bash
    [](<#cb5-1>)pip install langchain langchain-openai agent-evaluator
```

### 1.3 콜백 기반 통합

Agent Evaluator는 `LangChainEvaluator` 클래스를 제공하여 LangChain의 실행을 자동으로 추적합니다.

#### 주요 콜백 메서드

```python
    [](<#cb6-1>)class LangChainEvaluator:
    [](<#cb6-2>)    """LangChain용 평가 콜백 핸들러"""
    [](<#cb6-3>)
    [](<#cb6-4>)    def on_chain_start(self, serialized, inputs, **kwargs):
    [](<#cb6-5>)        """체인 시작 - 타이머 및 메트릭 초기화"""
    [](<#cb6-6>)
    [](<#cb6-7>)    def on_llm_start(self, serialized, prompts, **kwargs):
    [](<#cb6-8>)        """LLM 호출 시작 - 입력 토큰 추정"""
    [](<#cb6-9>)
    [](<#cb6-10>)    def on_llm_end(self, response: LLMResult, **kwargs):
    [](<#cb6-11>)        """LLM 호출 완료 - 토큰 사용량 기록"""
    [](<#cb6-12>)
    [](<#cb6-13>)    def on_agent_action(self, action: AgentAction, **kwargs):
    [](<#cb6-14>)        """도구 호출 - Tool Selection 추적"""
    [](<#cb6-15>)
    [](<#cb6-16>)    def on_tool_end(self, output: str, **kwargs):
    [](<#cb6-17>)        """도구 호출 완료"""
    [](<#cb6-18>)
    [](<#cb6-19>)    def on_chain_error(self, error: Exception, **kwargs):
    [](<#cb6-20>)        """에러 발생 - 에러 기록"""
    [](<#cb6-21>)
    [](<#cb6-22>)    def on_chain_end(self, outputs, **kwargs):
    [](<#cb6-23>)        """체인 완료 - TaskResult 생성 및 기록"""
```

### 1.4 기본 사용법

```python
    [](<#cb7-1>)from langchain.agents import AgentExecutor, create_openai_functions_agent
    [](<#cb7-2>)from langchain_openai import ChatOpenAI
    [](<#cb7-3>)from langchain.tools import Tool
    [](<#cb7-4>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb7-5>)from agent_evaluator import PerformanceMonitor, TaskType
    [](<#cb7-6>)
    [](<#cb7-7>)# 1. Monitor 생성
    [](<#cb7-8>)monitor = PerformanceMonitor(
    [](<#cb7-9>)    pricing={"input": 0.003, "output": 0.015}
    [](<#cb7-10>))
    [](<#cb7-11>)
    [](<#cb7-12>)# 2. Callback 생성
    [](<#cb7-13>)evaluator = LangChainEvaluator(agent,
    [](<#cb7-14>)    monitor,
    [](<#cb7-15>)    task_type=TaskType.QA.value
    [](<#cb7-16>))
    [](<#cb7-17>)
    [](<#cb7-18>)# 3. LLM 및 도구 설정
    [](<#cb7-19>)llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    [](<#cb7-20>)
    [](<#cb7-21>)def search(query: str) -> str:
    [](<#cb7-22>)    """검색 도구"""
    [](<#cb7-23>)    return f"Search results for: {query}"
    [](<#cb7-24>)
    [](<#cb7-25>)tools = [
    [](<#cb7-26>)    Tool(name="Search", func=search, description="Search for information")
    [](<#cb7-27>)]
    [](<#cb7-28>)
    [](<#cb7-29>)# 4. Agent 생성 및 실행
    [](<#cb7-30>)from langchain import hub
    [](<#cb7-31>)prompt = hub.pull("hwchase17/openai-functions-agent")
    [](<#cb7-32>)agent = create_openai_functions_agent(llm, tools, prompt)
    [](<#cb7-33>)agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    [](<#cb7-34>)
    [](<#cb7-35>)# 5. 콜백과 함께 실행
    [](<#cb7-36>)result = agent_executor.invoke(
    [](<#cb7-37>)    {"input": "What is the capital of France?"},
    [](<#cb7-38>)    config={"callbacks": [callback]}
    [](<#cb7-39>))
    [](<#cb7-40>)
    [](<#cb7-41>)# 6. 리포트 확인
    [](<#cb7-42>)monitor.print_summary()
```

### 1.5 Layer 2: Tool Selection 자동 평가

LangChain 콜백은 **Tool Selection** 메트릭을 자동으로 평가할 수 있습니다.

```json
    [](<#cb8-1>)# Golden Dataset에서 expected_tools 로드
    [](<#cb8-2>)expected_tools = ["search", "calculator", "python_repl"]
    [](<#cb8-3>)
    [](<#cb8-4>)# Layer 2 자동 평가 활성화
    [](<#cb8-5>)evaluator = LangChainEvaluator(agent,
    [](<#cb8-6>)    monitor,
    [](<#cb8-7>)    task_type=TaskType.TOOL_USE.value,
    [](<#cb8-8>)    expected_tools=expected_tools  # 🆕 Tool Selection 자동 평가
    [](<#cb8-9>))
    [](<#cb8-10>)
    [](<#cb8-11>)# Agent 실행
    [](<#cb8-12>)result = agent_executor.invoke(
    [](<#cb8-13>)    {"input": "What is 25 * 4?"},
    [](<#cb8-14>)    config={"callbacks": [callback]}
    [](<#cb8-15>))
    [](<#cb8-16>)
    [](<#cb8-17>)# Tool Selection 통계 확인
    [](<#cb8-18>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb8-19>)print(f"Tool Selection Accuracy: {stats['avg_accuracy']:.1f}%")
    [](<#cb8-20>)print(f"Precision: {stats['avg_precision']:.1f}%")
    [](<#cb8-21>)print(f"Recall: {stats['avg_recall']:.1f}%")
    [](<#cb8-22>)print(f"F1 Score: {stats['avg_f1_score']:.1f}%")
```

**자동 추적 메커니즘:**

  1. `on_agent_action()`: 에이전트가 도구를 선택할 때마다 호출
  2. 선택된 도구 이름을 `self.tool_calls` 리스트에 저장
  3. `on_chain_end()`: 체인 완료 시 `expected_tools`와 비교하여 자동 평가
  4. `monitor.tool_selection_tracker.evaluate_selection()` 호출

### 1.6 헬퍼 클래스: LangChainEvaluator

간편한 사용을 위한 래퍼 클래스:

```python
    [](<#cb9-1>)from agent_evaluator.integrations import LangChainEvaluator
    [](<#cb9-2>)
    [](<#cb9-3>)# Evaluator 생성
    [](<#cb9-4>)evaluator = LangChainEvaluator(monitor)
    [](<#cb9-5>)
    [](<#cb9-6>)# Agent 실행 (콜백 자동 추가)
    [](<#cb9-7>)result = evaluator.run(agent_executor, "What is AI?")
    [](<#cb9-8>)
    [](<#cb9-9>)# 리포트 생성
    [](<#cb9-10>)report = evaluator.get_report()
```

### 1.7 실전 예제: RAG 시스템 평가

```python
    [](<#cb10-1>)from langchain_openai import OpenAIEmbeddings
    [](<#cb10-2>)from langchain.vectorstores import Chroma
    [](<#cb10-3>)from langchain.chains import RetrievalQA
    [](<#cb10-4>)from langchain.text_splitter import RecursiveCharacterTextSplitter
    [](<#cb10-5>)from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback
    [](<#cb10-6>)from hybrid_monitor import create_monitor
    [](<#cb10-7>)
    [](<#cb10-8>)# 1. RAG 프로파일 Monitor 생성 (RAGAS 메트릭 포함)
    [](<#cb10-9>)monitor = create_monitor(profile="rag")
    [](<#cb10-10>)
    [](<#cb10-11>)# 2. 문서 로드 및 벡터 스토어 생성
    [](<#cb10-12>)documents = [
    [](<#cb10-13>)    "Paris is the capital of France.",
    [](<#cb10-14>)    "France is located in Western Europe.",
    [](<#cb10-15>)    "The Eiffel Tower is in Paris."
    [](<#cb10-16>)]
    [](<#cb10-17>)
    [](<#cb10-18>)text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
    [](<#cb10-19>)splits = text_splitter.create_documents(documents)
    [](<#cb10-20>)
    [](<#cb10-21>)embeddings = OpenAIEmbeddings()
    [](<#cb10-22>)vectorstore = Chroma.from_documents(splits, embeddings)
    [](<#cb10-23>)
    [](<#cb10-24>)# 3. RAG 체인 생성
    [](<#cb10-25>)llm = ChatOpenAI(model="gpt-4o-mini")
    [](<#cb10-26>)qa_chain = RetrievalQA.from_chain_type(
    [](<#cb10-27>)    llm=llm,
    [](<#cb10-28>)    chain_type="stuff",
    [](<#cb10-29>)    retriever=vectorstore.as_retriever(search_kwargs={"k": 3})
    [](<#cb10-30>))
    [](<#cb10-31>)
    [](<#cb10-32>)# 4. Callback 생성
    [](<#cb10-33>)evaluator = LangChainEvaluator(agent,
    [](<#cb10-34>)    monitor,
    [](<#cb10-35>)    task_type=TaskType.INFORMATION_RETRIEVAL.value
    [](<#cb10-36>))
    [](<#cb10-37>)
    [](<#cb10-38>)# 5. 실행
    [](<#cb10-39>)result = qa_chain.invoke(
    [](<#cb10-40>)    {"query": "What is the capital of France?"},
    [](<#cb10-41>)    config={"callbacks": [callback]}
    [](<#cb10-42>))
    [](<#cb10-43>)
    [](<#cb10-44>)# 6. RAGAS 메트릭 포함 고급 평가
    [](<#cb10-45>)# (HybridPerformanceMonitor가 자동으로 RAGAS 계산)
    [](<#cb10-46>)hybrid_report = monitor.generate_hybrid_report()
    [](<#cb10-47>)print(f"Faithfulness: {hybrid_report.advanced_metrics_summary.get('ragas_faithfulness', {}).get('mean', 0):.3f}")
    [](<#cb10-48>)print(f"Context Precision: {hybrid_report.advanced_metrics_summary.get('ragas_context_precision', {}).get('mean', 0):.3f}")
```

* * *

## 2\. LangGraph 통합

**✨ LangGraphEvaluator** \- LangGraph 전용 평가 클래스

노드별 자동 추적, Workflow Execution 메트릭, Layer 1/2/3 완전 지원

```python
    from agent_evaluator.integrations import LangGraphEvaluator
    evaluator = LangGraphEvaluator(enable_layer2=True)
    evaluator.add_node("step1", your_function)
```

자세한 내용은 [API Reference](<API_REFERENCE.html#langgraph-evaluator>)를 참고하세요.

### 2.1 LangGraph 소개

**LangGraph** 는 LangChain의 고급 워크플로우 프레임워크로, 상태 기반 그래프를 사용합니다.

**주요 특징**

  * 📊 **StateGraph** : 상태 기반 그래프 실행
  * 🔄 **순환 그래프** : 복잡한 워크플로우 지원
  * 🎯 **조건부 분기** : 동적 경로 선택
  * 🧩 **노드/엣지** : 명시적 워크플로우 정의

### 2.2 설치

```bash
    [](<#cb11-1>)pip install langgraph
    [](<#cb11-2>)pip install agent-evaluator
```

### 2.3 래퍼 기반 통합

Agent Evaluator는 `LangGraphEvaluator` 클래스를 제공하여 LangGraph 워크플로우를 래핑합니다.

#### 주요 메서드

```python
    [](<#cb12-1>)class LangGraphEvaluator:
    [](<#cb12-2>)    """LangGraph 워크플로우에 평가 기능 통합"""
    [](<#cb12-3>)
    [](<#cb12-4>)    def _start_node(self, state: AgentState):
    [](<#cb12-5>)        """시작 노드 - 평가 데이터 초기화"""
    [](<#cb12-6>)
    [](<#cb12-7>)    def add_node(self, name: str, func):
    [](<#cb12-8>)        """커스텀 노드 추가 (자동 래핑)"""
    [](<#cb12-9>)
    [](<#cb12-10>)    def _wrap_node_for_tracking(self, node_name: str, func):
    [](<#cb12-11>)        """노드를 래핑하여 Workflow Execution 추적"""
    [](<#cb12-12>)
    [](<#cb12-13>)    def add_edge(self, from_node: str, to_node: str):
    [](<#cb12-14>)        """엣지 추가"""
    [](<#cb12-15>)
    [](<#cb12-16>)    def _end_node(self, state: AgentState):
    [](<#cb12-17>)        """종료 노드 - TaskResult 생성 및 기록"""
    [](<#cb12-18>)
    [](<#cb12-19>)    def compile_and_run(self, initial_state: dict):
    [](<#cb12-20>)        """워크플로우 컴파일 및 실행"""
```

### 2.4 기본 사용법

```python
    [](<#cb13-1>)from agent_evaluator.integrations import LangGraphEvaluator
    [](<#cb13-2>)from agent_evaluator import PerformanceMonitor, TaskType
    [](<#cb13-3>)
    [](<#cb13-4>)# 1. Monitor 생성
    [](<#cb13-5>)monitor = PerformanceMonitor()
    [](<#cb13-6>)
    [](<#cb13-7>)# 2. Workflow 생성
    [](<#cb13-8>)evaluator = LangGraphEvaluator(
    [](<#cb13-9>)    monitor,
    [](<#cb13-10>)    task_type=TaskType.QA.value
    [](<#cb13-11>))
    [](<#cb13-12>)
    [](<#cb13-13>)# 3. 커스텀 노드 정의
    [](<#cb13-14>)def retrieval_node(state):
    [](<#cb13-15>)    """검색 노드"""
    [](<#cb13-16>)    messages = state["messages"]
    [](<#cb13-17>)    # 검색 로직
    [](<#cb13-18>)    state["messages"].append(f"Retrieved context for: {messages[0]}")
    [](<#cb13-19>)    state["next_step"] = "generation"
    [](<#cb13-20>)    return state
    [](<#cb13-21>)
    [](<#cb13-22>)def generation_node(state):
    [](<#cb13-23>)    """생성 노드"""
    [](<#cb13-24>)    messages = state["messages"]
    [](<#cb13-25>)    # 생성 로직
    [](<#cb13-26>)    state["messages"].append("Generated response")
    [](<#cb13-27>)    state["next_step"] = "end"
    [](<#cb13-28>)    return state
    [](<#cb13-29>)
    [](<#cb13-30>)# 4. 노드 및 엣지 추가
    [](<#cb13-31>)workflow.add_node("retrieval", retrieval_node)
    [](<#cb13-32>)workflow.add_node("generation", generation_node)
    [](<#cb13-33>)
    [](<#cb13-34>)workflow.add_edge("start", "retrieval")
    [](<#cb13-35>)workflow.add_edge("retrieval", "generation")
    [](<#cb13-36>)workflow.add_edge("generation", "end")
    [](<#cb13-37>)
    [](<#cb13-38>)# 5. 실행
    [](<#cb13-39>)result = workflow.compile_and_run({
    [](<#cb13-40>)    "messages": ["What is AI?"],
    [](<#cb13-41>)    "next_step": "start"
    [](<#cb13-42>)})
    [](<#cb13-43>)
    [](<#cb13-44>)# 6. 리포트 확인
    [](<#cb13-45>)monitor.print_summary()
```

### 2.5 Layer 2: Workflow Execution 자동 추적

LangGraph는 **Workflow Execution** 메트릭을 자동으로 추적합니다.

```json
    [](<#cb14-1>)# Layer 2 자동 추적 활성화
    [](<#cb14-2>)evaluator = LangGraphEvaluator(
    [](<#cb14-3>)    monitor,
    [](<#cb14-4>)    task_type=TaskType.QA.value,
    [](<#cb14-5>)    enable_workflow_tracking=True,  # 🆕 Workflow Execution 자동 추적
    [](<#cb14-6>)    expected_workflow_steps=["retrieval", "generation", "validation"]
    [](<#cb14-7>))
    [](<#cb14-8>)
    [](<#cb14-9>)# 노드 추가 (자동으로 래핑됨)
    [](<#cb14-10>)workflow.add_node("retrieval", retrieval_node)
    [](<#cb14-11>)workflow.add_node("generation", generation_node)
    [](<#cb14-12>)workflow.add_node("validation", validation_node)
    [](<#cb14-13>)
    [](<#cb14-14>)# 워크플로우 실행
    [](<#cb14-15>)result = workflow.compile_and_run({"messages": ["input"]})
    [](<#cb14-16>)
    [](<#cb14-17>)# Workflow Execution 통계 확인
    [](<#cb14-18>)stats = monitor.workflow_tracker.calculate_execution_success_rate(framework="langgraph")
    [](<#cb14-19>)print(f"Step Success Rate: {stats['step_success_rate']:.1f}%")
    [](<#cb14-20>)print(f"Task Success Rate: {stats['task_success_rate']:.1f}%")
    [](<#cb14-21>)print(f"Total Steps: {stats['total_steps']}")
    [](<#cb14-22>)print(f"Successful Steps: {stats['successful_steps']}")
    [](<#cb14-23>)
    [](<#cb14-24>)# 그래프 순회 효율성 (LangGraph 전용)
    [](<#cb14-25>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
    [](<#cb14-26>)print(f"Graph Traversal Efficiency: {efficiency['efficiency']:.1f}%")
    [](<#cb14-27>)print(f"Nodes Executed: {efficiency['nodes_executed']}")
    [](<#cb14-28>)print(f"Avg Node Time: {efficiency['avg_node_time']:.3f}s")
```

**자동 추적 메커니즘:**

  1. `add_node()`: 노드 추가 시 `_wrap_node_for_tracking()`으로 자동 래핑
  2. 래핑된 노드는 실행 전후에 시간 측정
  3. `monitor.workflow_tracker.track_step()` 자동 호출
  4. 각 단계의 성공/실패, 실행 시간 기록
  5. `state["evaluation_data"]["workflow_steps"]`에도 기록

### 2.6 실전 예제: RAG 워크플로우

```python
    [](<#cb15-1>)from langgraph.graph import StateGraph, END
    [](<#cb15-2>)from typing import TypedDict
    [](<#cb15-3>)
    [](<#cb15-4>)class RAGState(TypedDict):
    [](<#cb15-5>)    query: str
    [](<#cb15-6>)    context: list
    [](<#cb15-7>)    answer: str
    [](<#cb15-8>)    evaluation_data: dict
    [](<#cb15-9>)
    [](<#cb15-10>)# 워크플로우 생성
    [](<#cb15-11>)evaluator = LangGraphEvaluator(
    [](<#cb15-12>)    monitor,
    [](<#cb15-13>)    enable_workflow_tracking=True
    [](<#cb15-14>))
    [](<#cb15-15>)
    [](<#cb15-16>)def retrieval(state):
    [](<#cb15-17>)    # Vector DB에서 검색
    [](<#cb15-18>)    state["context"] = ["context1", "context2"]
    [](<#cb15-19>)    return state
    [](<#cb15-20>)
    [](<#cb15-21>)def rerank(state):
    [](<#cb15-22>)    # 컨텍스트 재정렬
    [](<#cb15-23>)    state["context"] = sorted(state["context"])
    [](<#cb15-24>)    return state
    [](<#cb15-25>)
    [](<#cb15-26>)def generation(state):
    [](<#cb15-27>)    # 답변 생성
    [](<#cb15-28>)    state["answer"] = f"Answer based on {len(state['context'])} contexts"
    [](<#cb15-29>)    return state
    [](<#cb15-30>)
    [](<#cb15-31>)# 노드 추가
    [](<#cb15-32>)workflow.add_node("retrieval", retrieval)
    [](<#cb15-33>)workflow.add_node("rerank", rerank)
    [](<#cb15-34>)workflow.add_node("generation", generation)
    [](<#cb15-35>)
    [](<#cb15-36>)# 엣지 추가
    [](<#cb15-37>)workflow.add_edge("start", "retrieval")
    [](<#cb15-38>)workflow.add_edge("retrieval", "rerank")
    [](<#cb15-39>)workflow.add_edge("rerank", "generation")
    [](<#cb15-40>)workflow.add_edge("generation", "end")
    [](<#cb15-41>)
    [](<#cb15-42>)# 실행
    [](<#cb15-43>)result = workflow.compile_and_run({"query": "What is AI?"})
```

* * *

## 3\. CrewAI 통합

**✨ CrewAIEvaluator** \- CrewAI 전용 평가 클래스

Layer 1/2/3 완전 지원, Agent Coordination 자동 추적, Golden Dataset 지원, Manual Tracking APIs

```python
    from agent_evaluator.integrations import CrewAIEvaluator
    evaluator = CrewAIEvaluator(crew, enable_layer2=True)
    result = evaluator.kickoff()
```

자세한 내용은 [API Reference](<API_REFERENCE.html#crewai-evaluator>)를 참고하세요.

### 3.1 CrewAI 소개

**CrewAI** 는 멀티 에이전트 협업을 위한 프레임워크입니다.

**주요 특징**

  * 🤝 **멀티 에이전트** : 역할 기반 에이전트 협업
  * 🎯 **작업 분배** : 자동 작업 할당
  * 🔄 **순차/병렬 실행** : 유연한 실행 전략
  * 🧰 **도구 통합** : 다양한 도구 사용

### 3.2 설치

```bash
    [](<#cb16-1>)pip install crewai crewai-tools agent-evaluator
```

### 3.3 래퍼 기반 통합

Agent Evaluator는 `CrewAIEvaluator` 클래스를 제공하여 CrewAI Crew를 래핑합니다.

#### 주요 메서드

```python
    [](<#cb17-1>)class CrewAIEvaluator:
    [](<#cb17-2>)    """CrewAI에 평가 기능 통합"""
    [](<#cb17-3>)
    [](<#cb17-4>)    def kickoff(self, inputs: dict = None):
    [](<#cb17-5>)        """Crew 실행 및 평가
    [](<#cb17-6>)
    [](<#cb17-7>)        - 실행 시간 자동 측정
    [](<#cb17-8>)        - 토큰 사용량 추정
    [](<#cb17-9>)        - 도구 호출 추출
    [](<#cb17-10>)        - TaskResult 자동 생성
    [](<#cb17-11>)        """
    [](<#cb17-12>)
    [](<#cb17-13>)    def _estimate_tokens(self, result):
    [](<#cb17-14>)        """토큰 사용량 추정"""
    [](<#cb17-15>)
    [](<#cb17-16>)    def _extract_tool_calls(self):
    [](<#cb17-17>)        """도구 호출 정보 추출"""
    [](<#cb17-18>)
    [](<#cb17-19>)    def _track_agent_interactions_start(self, task_id: str):
    [](<#cb17-20>)        """Agent Coordination 추적 시작"""
    [](<#cb17-21>)
    [](<#cb17-22>)    def _track_agent_interactions_end(self, task_id: str):
    [](<#cb17-23>)        """Agent Coordination 추적 완료"""
```

### 3.4 기본 사용법

```python
    [](<#cb18-1>)from crewai import Agent, Task, Crew, Process
    [](<#cb18-2>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb18-3>)from agent_evaluator import PerformanceMonitor, TaskType
    [](<#cb18-4>)
    [](<#cb18-5>)# 1. Monitor 생성
    [](<#cb18-6>)monitor = PerformanceMonitor(
    [](<#cb18-7>)    pricing={"input": 0.003, "output": 0.015}
    [](<#cb18-8>))
    [](<#cb18-9>)
    [](<#cb18-10>)# 2. Agent 정의
    [](<#cb18-11>)researcher = Agent(
    [](<#cb18-12>)    role='Researcher',
    [](<#cb18-13>)    goal='Research and gather information',
    [](<#cb18-14>)    backstory='Expert researcher with attention to detail',
    [](<#cb18-15>)    verbose=True
    [](<#cb18-16>))
    [](<#cb18-17>)
    [](<#cb18-18>)writer = Agent(
    [](<#cb18-19>)    role='Writer',
    [](<#cb18-20>)    goal='Write engaging content',
    [](<#cb18-21>)    backstory='Creative writer with storytelling skills',
    [](<#cb18-22>)    verbose=True
    [](<#cb18-23>))
    [](<#cb18-24>)
    [](<#cb18-25>)# 3. Task 정의
    [](<#cb18-26>)research_task = Task(
    [](<#cb18-27>)    description='Research about AI trends in 2024',
    [](<#cb18-28>)    agent=researcher,
    [](<#cb18-29>)    expected_output='Detailed research report'
    [](<#cb18-30>))
    [](<#cb18-31>)
    [](<#cb18-32>)writing_task = Task(
    [](<#cb18-33>)    description='Write a blog post based on research',
    [](<#cb18-34>)    agent=writer,
    [](<#cb18-35>)    expected_output='Engaging blog post',
    [](<#cb18-36>)    context=[research_task]
    [](<#cb18-37>))
    [](<#cb18-38>)
    [](<#cb18-39>)# 4. Crew 생성
    [](<#cb18-40>)crew = Crew(
    [](<#cb18-41>)    agents=[researcher, writer],
    [](<#cb18-42>)    tasks=[research_task, writing_task],
    [](<#cb18-43>)    process=Process.sequential,
    [](<#cb18-44>)    verbose=True
    [](<#cb18-45>))
    [](<#cb18-46>)
    [](<#cb18-47>)# 5. CrewAIEvaluator로 래핑
    [](<#cb18-48>)evaluator = CrewAIEvaluator(
    [](<#cb18-49>)    crew,
    [](<#cb18-50>)    monitor,
    [](<#cb18-51>)    task_type=TaskType.DOCUMENT_CREATION.value
    [](<#cb18-52>))
    [](<#cb18-53>)
    [](<#cb18-54>)# 6. 실행 (자동 평가)
    [](<#cb18-55>)result = evaluated_crew.kickoff()
    [](<#cb18-56>)
    [](<#cb18-57>)# 7. 리포트 확인
    [](<#cb18-58>)monitor.print_summary()
    [](<#cb18-59>)monitor.save_to_file("crew_evaluation.json")
```

### 3.5 Layer 2: Agent Coordination 자동 추적

CrewAI는 **Agent Coordination** 메트릭을 자동으로 추적할 수 있습니다.

```json
    [](<#cb19-1>)# Golden Dataset에서 expected_agents 로드
    [](<#cb19-2>)expected_agents = ["researcher", "writer", "reviewer"]
    [](<#cb19-3>)
    [](<#cb19-4>)# Layer 2 자동 추적 활성화
    [](<#cb19-5>)evaluator = CrewAIEvaluator(
    [](<#cb19-6>)    crew,
    [](<#cb19-7>)    monitor,
    [](<#cb19-8>)    task_type=TaskType.DOCUMENT_CREATION.value,
    [](<#cb19-9>)    enable_coordination_tracking=True,  # 🆕 Agent Coordination 자동 추적
    [](<#cb19-10>)    expected_agents=expected_agents
    [](<#cb19-11>))
    [](<#cb19-12>)
    [](<#cb19-13>)# Crew 실행
    [](<#cb19-14>)result = evaluated_crew.kickoff()
    [](<#cb19-15>)
    [](<#cb19-16>)# Agent Coordination 통계 확인
    [](<#cb19-17>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb19-18>)print(f"Coordination Score: {score_data['score']:.1f}/10")
    [](<#cb19-19>)print(f"Success Rate: {score_data['success_rate']:.1f}%")
    [](<#cb19-20>)print(f"Total Interactions: {score_data['total_interactions']}")
    [](<#cb19-21>)print(f"Unique Agents: {score_data['unique_agents']}")
    [](<#cb19-22>)
    [](<#cb19-23>)# Delegation 성공률
    [](<#cb19-24>)delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()
    [](<#cb19-25>)print(f"Delegation Success Rate: {delegation_rate:.1f}%")
```

**자동 추적 메커니즘:**

  1. `_track_agent_interactions_start()`: Crew 실행 시작 시 호출
  2. Crew의 agents 리스트에서 에이전트 이름 추출
  3. 순차적 에이전트 간 상호작용 시뮬레이션 (delegation, collaboration)
  4. `monitor.agent_coordination_tracker.track_interaction()` 호출
  5. `_track_agent_interactions_end()`: Crew 실행 완료 시 모든 상호작용 기록

### 3.6 헬퍼 클래스: CrewAIEvaluator

```python
    [](<#cb20-1>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb20-2>)
    [](<#cb20-3>)# Evaluator 생성
    [](<#cb20-4>)evaluator = CrewAIEvaluator(monitor)
    [](<#cb20-5>)
    [](<#cb20-6>)# 평가 기능이 통합된 Crew 생성
    [](<#cb20-7>)evaluated_crew = evaluator.create_evaluated_crew(
    [](<#cb20-8>)    agents=[researcher, writer],
    [](<#cb20-9>)    tasks=[research_task, writing_task],
    [](<#cb20-10>)    process=Process.sequential
    [](<#cb20-11>))
    [](<#cb20-12>)
    [](<#cb20-13>)# 실행
    [](<#cb20-14>)result = evaluated_crew.kickoff()
```

### 3.7 실전 예제: 멀티 에이전트 뉴스레터 생성

```python
    [](<#cb21-1>)from crewai import Agent, Task, Crew, Process
    [](<#cb21-2>)from crewai.tools import SerperDevTool, ScrapeWebsiteTool
    [](<#cb21-3>)from agent_evaluator.integrations import CrewAIEvaluator
    [](<#cb21-4>)from hybrid_monitor import create_monitor
    [](<#cb21-5>)from agent_evaluator import TaskType
    [](<#cb21-6>)
    [](<#cb21-7>)# 1. Balanced 프로파일 Monitor 생성
    [](<#cb21-8>)monitor = create_monitor(profile="balanced")
    [](<#cb21-9>)
    [](<#cb21-10>)# 2. 도구 설정
    [](<#cb21-11>)search_tool = SerperDevTool()
    [](<#cb21-12>)scrape_tool = ScrapeWebsiteTool()
    [](<#cb21-13>)
    [](<#cb21-14>)# 3. 에이전트 정의
    [](<#cb21-15>)researcher = Agent(
    [](<#cb21-16>)    role='Tech Researcher',
    [](<#cb21-17>)    goal='Find and analyze latest AI news',
    [](<#cb21-18>)    backstory='Expert in AI trends',
    [](<#cb21-19>)    tools=[search_tool, scrape_tool],
    [](<#cb21-20>)    verbose=True
    [](<#cb21-21>))
    [](<#cb21-22>)
    [](<#cb21-23>)analyst = Agent(
    [](<#cb21-24>)    role='Content Analyst',
    [](<#cb21-25>)    goal='Analyze and summarize information',
    [](<#cb21-26>)    backstory='Skilled at extracting key insights',
    [](<#cb21-27>)    verbose=True
    [](<#cb21-28>))
    [](<#cb21-29>)
    [](<#cb21-30>)writer = Agent(
    [](<#cb21-31>)    role='Newsletter Writer',
    [](<#cb21-32>)    goal='Write engaging newsletter',
    [](<#cb21-33>)    backstory='Creative technical writer',
    [](<#cb21-34>)    verbose=True
    [](<#cb21-35>))
    [](<#cb21-36>)
    [](<#cb21-37>)# 4. 작업 정의
    [](<#cb21-38>)research = Task(
    [](<#cb21-39>)    description='Research AI news from this week',
    [](<#cb21-40>)    agent=researcher,
    [](<#cb21-41>)    expected_output='List of 5 important AI news items'
    [](<#cb21-42>))
    [](<#cb21-43>)
    [](<#cb21-44>)analysis = Task(
    [](<#cb21-45>)    description='Analyze the news and identify key themes',
    [](<#cb21-46>)    agent=analyst,
    [](<#cb21-47>)    expected_output='Summary of key themes and trends',
    [](<#cb21-48>)    context=[research]
    [](<#cb21-49>))
    [](<#cb21-50>)
    [](<#cb21-51>)writing = Task(
    [](<#cb21-52>)    description='Write a newsletter based on the analysis',
    [](<#cb21-53>)    agent=writer,
    [](<#cb21-54>)    expected_output='Engaging newsletter (500 words)',
    [](<#cb21-55>)    context=[analysis]
    [](<#cb21-56>))
    [](<#cb21-57>)
    [](<#cb21-58>)# 5. Crew 생성 및 평가 통합
    [](<#cb21-59>)crew = Crew(
    [](<#cb21-60>)    agents=[researcher, analyst, writer],
    [](<#cb21-61>)    tasks=[research, analysis, writing],
    [](<#cb21-62>)    process=Process.sequential,
    [](<#cb21-63>)    verbose=True
    [](<#cb21-64>))
    [](<#cb21-65>)
    [](<#cb21-66>)evaluator = CrewAIEvaluator(
    [](<#cb21-67>)    crew,
    [](<#cb21-68>)    monitor,
    [](<#cb21-69>)    task_type=TaskType.DOCUMENT_CREATION.value,
    [](<#cb21-70>)    enable_coordination_tracking=True
    [](<#cb21-71>))
    [](<#cb21-72>)
    [](<#cb21-73>)# 6. 실행
    [](<#cb21-74>)result = evaluated_crew.kickoff()
    [](<#cb21-75>)
    [](<#cb21-76>)print(f"\n✅ Newsletter created successfully!")
    [](<#cb21-77>)print(f"\n📰 Newsletter:\n{result}\n")
    [](<#cb21-78>)
    [](<#cb21-79>)# 7. 하이브리드 리포트 생성
    [](<#cb21-80>)hybrid_report = monitor.generate_hybrid_report()
    [](<#cb21-81>)monitor.print_summary()
```

* * *

## 4\. AutoGen 통합

**✨ AutoGenEvaluator** \- AutoGen 전용 평가 클래스

메서드 래핑, Agent Coordination 자동 추적, Layer 1/2/3 완전 지원

```python
    from agent_evaluator.integrations import AutoGenEvaluator
    evaluator = AutoGenEvaluator(assistant, enable_layer2=True)
    user_proxy.initiate_chat(evaluator.agent, message="Hello")
```

자세한 내용은 [API Reference](<API_REFERENCE.html#autogen-evaluator>)를 참고하세요.

### 4.1 AutoGen 소개

**AutoGen** 은 Microsoft에서 개발한 대화형 에이전트 프레임워크입니다.

**주요 특징**

  * 💬 **대화형** : 자연스러운 대화 흐름
  * 🤖 **다중 에이전트** : 에이전트 간 협업
  * 🔧 **도구 실행** : 코드 실행 및 도구 사용
  * 🎭 **역할 기반** : 사용자/어시스턴트 역할

### 4.2 설치

```bash
    [](<#cb22-1>)pip install autogen-agentchat autogen-core  # 0.4.0+ 권장
    [](<#cb22-2>)pip install agent-evaluator
```

### 4.3 래퍼 기반 통합

Agent Evaluator는 `AutoGenEvaluator` 클래스를 제공하여 AutoGen Agent를 래핑합니다.

#### 주요 메서드

```python
    [](<#cb23-1>)class AutoGenEvaluator:
    [](<#cb23-2>)    """AutoGen Agent에 평가 기능 통합"""
    [](<#cb23-3>)
    [](<#cb23-4>)    def _evaluated_generate_reply(self, messages, sender, **kwargs):
    [](<#cb23-5>)        """평가가 통합된 응답 생성
    [](<#cb23-6>)
    [](<#cb23-7>)        - 원본 generate_reply() 메서드 래핑
    [](<#cb23-8>)        - 실행 시간 자동 측정
    [](<#cb23-9>)        - 토큰 사용량 추정
    [](<#cb23-10>)        - TaskResult 자동 생성
    [](<#cb23-11>)        """
    [](<#cb23-12>)
    [](<#cb23-13>)    def _estimate_tokens(self, messages, reply):
    [](<#cb23-14>)        """토큰 사용량 추정"""
```

### 4.4 기본 사용법

```python
    [](<#cb24-1>)import autogen
    [](<#cb24-2>)from agent_evaluator.integrations import AutoGenEvaluator
    [](<#cb24-3>)from agent_evaluator import PerformanceMonitor, TaskType
    [](<#cb24-4>)
    [](<#cb24-5>)# 1. Monitor 생성
    [](<#cb24-6>)monitor = PerformanceMonitor(
    [](<#cb24-7>)    pricing={"input": 0.003, "output": 0.015}
    [](<#cb24-8>))
    [](<#cb24-9>)
    [](<#cb24-10>)# 2. LLM 설정
    [](<#cb24-11>)config_list = [{
    [](<#cb24-12>)    "model": "gpt-4o-mini",
    [](<#cb24-13>)    "api_key": "your-api-key"
    [](<#cb24-14>)}]
    [](<#cb24-15>)
    [](<#cb24-16>)llm_config = {
    [](<#cb24-17>)    "config_list": config_list,
    [](<#cb24-18>)    "temperature": 0.7,
    [](<#cb24-19>)}
    [](<#cb24-20>)
    [](<#cb24-21>)# 3. Agent 생성
    [](<#cb24-22>)assistant = autogen.AssistantAgent(
    [](<#cb24-23>)    name="assistant",
    [](<#cb24-24>)    llm_config=llm_config,
    [](<#cb24-25>)    system_message="You are a helpful AI assistant."
    [](<#cb24-26>))
    [](<#cb24-27>)
    [](<#cb24-28>)user_proxy = autogen.UserProxyAgent(
    [](<#cb24-29>)    name="user_proxy",
    [](<#cb24-30>)    human_input_mode="NEVER",
    [](<#cb24-31>)    max_consecutive_auto_reply=10,
    [](<#cb24-32>)    code_execution_config={"use_docker": False}
    [](<#cb24-33>))
    [](<#cb24-34>)
    [](<#cb24-35>)# 4. AutoGenEvaluator로 래핑
    [](<#cb24-36>)evaluator = AutoGenEvaluator(
    [](<#cb24-37>)    assistant,
    [](<#cb24-38>)    monitor,
    [](<#cb24-39>)    task_type=TaskType.QA.value
    [](<#cb24-40>))
    [](<#cb24-41>)
    [](<#cb24-42>)# 5. 대화 실행
    [](<#cb24-43>)chat_result = user_proxy.initiate_chat(
    [](<#cb24-44>)    evaluated_assistant.agent,
    [](<#cb24-45>)    message="What are the latest trends in AI?"
    [](<#cb24-46>))
    [](<#cb24-47>)
    [](<#cb24-48>)# 6. 리포트 확인
    [](<#cb24-49>)monitor.print_summary()
```

### 4.5 헬퍼 클래스: AutoGenEvaluator

```python
    [](<#cb25-1>)from agent_evaluator.integrations import AutoGenEvaluator
    [](<#cb25-2>)
    [](<#cb25-3>)# Evaluator 생성
    [](<#cb25-4>)evaluator = AutoGenEvaluator(monitor)
    [](<#cb25-5>)
    [](<#cb25-6>)# 평가 기능이 통합된 Agent 생성
    [](<#cb25-7>)evaluated_assistant = evaluator.create_evaluated_agent(
    [](<#cb25-8>)    assistant,
    [](<#cb25-9>)    task_type=TaskType.QA.value
    [](<#cb25-10>))
    [](<#cb25-11>)
    [](<#cb25-12>)# 사용
    [](<#cb25-13>)chat_result = user_proxy.initiate_chat(
    [](<#cb25-14>)    evaluated_assistant.agent,
    [](<#cb25-15>)    message="What is AI?"
    [](<#cb25-16>))
```

### 4.6 실전 예제: 코드 생성 평가

```python
    [](<#cb26-1>)import autogen
    [](<#cb26-2>)from agent_evaluator.integrations import AutoGenEvaluator
    [](<#cb26-3>)from agent_evaluator import PerformanceMonitor, TaskType
    [](<#cb26-4>)
    [](<#cb26-5>)# Monitor 생성
    [](<#cb26-6>)monitor = PerformanceMonitor()
    [](<#cb26-7>)
    [](<#cb26-8>)# 코드 실행 에이전트
    [](<#cb26-9>)code_executor = autogen.UserProxyAgent(
    [](<#cb26-10>)    name="code_executor",
    [](<#cb26-11>)    human_input_mode="NEVER",
    [](<#cb26-12>)    code_execution_config={
    [](<#cb26-13>)        "work_dir": "coding",
    [](<#cb26-14>)        "use_docker": False
    [](<#cb26-15>)    }
    [](<#cb26-16>))
    [](<#cb26-17>)
    [](<#cb26-18>)# 코더 에이전트
    [](<#cb26-19>)coder = autogen.AssistantAgent(
    [](<#cb26-20>)    name="coder",
    [](<#cb26-21>)    llm_config=llm_config,
    [](<#cb26-22>)    system_message="You are an expert Python programmer."
    [](<#cb26-23>))
    [](<#cb26-24>)
    [](<#cb26-25>)# 평가 통합
    [](<#cb26-26>)evaluator = AutoGenEvaluator(
    [](<#cb26-27>)    coder,
    [](<#cb26-28>)    monitor,
    [](<#cb26-29>)    task_type=TaskType.CODE_GENERATION.value
    [](<#cb26-30>))
    [](<#cb26-31>)
    [](<#cb26-32>)# 코드 생성 작업 실행
    [](<#cb26-33>)chat_result = code_executor.initiate_chat(
    [](<#cb26-34>)    evaluated_coder.agent,
    [](<#cb26-35>)    message="Write a function to calculate fibonacci numbers"
    [](<#cb26-36>))
    [](<#cb26-37>)
    [](<#cb26-38>)# 리포트 확인
    [](<#cb26-39>)monitor.print_summary()
```

* * *

## 5\. 프레임워크 비교

### 5.1 통합 방식 비교

프레임워크 | 통합 방식 | 주요 클래스 | Layer 2 메트릭  
---|---|---|---  
**LangChain** | 콜백 기반 | `LangChainEvaluator` | Tool Selection  
**LangGraph** | 래퍼 기반 | `LangGraphEvaluator` | Workflow Execution  
**CrewAI** | 래퍼 기반 | `CrewAIEvaluator` | Agent Coordination  
**AutoGen** | 래퍼 기반 | `AutoGenEvaluator` | -  
  
### 5.2 자동 추적 기능

프레임워크 | Layer 1 자동 추적 | Layer 2 자동 추적  
---|---|---  
**LangChain** | ✅ TCR, Cost, Latency, Tokens | ✅ Tool Selection (콜백)  
**LangGraph** | ✅ TCR, Cost, Latency, Tokens | ✅ Workflow Execution (래핑)  
**CrewAI** | ✅ TCR, Cost, Latency, Tokens | ✅ Agent Coordination (래핑)  
**AutoGen** | ✅ TCR, Cost, Latency, Tokens | ⚠️ 수동 추적 필요  
  
### 5.3 기능 비교

기능 | LangChain | LangGraph | CrewAI | AutoGen  
---|---|---|---|---  
**멀티 에이전트** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐  
**대화형** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐  
**RAG** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐  
**도구 통합** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐  
**워크플로우** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐  
**코드 실행** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐  
  
### 5.4 평가 메트릭 권장 사항

#### LangChain

  * ✅ **Layer 1** : TCR, Accuracy, Cost, Latency
  * 🎯 **Layer 2** : Tool Selection (콜백 자동 추적)
  * 📊 **고급** : RAGAS (RAG 시스템)
  * 🏆 **추천 프로파일** : `rag`, `balanced`

#### LangGraph

  * ✅ **Layer 1** : TCR, Accuracy, Cost, Latency
  * 🎯 **Layer 2** : Workflow Execution (노드 래핑 자동 추적)
  * 📊 **고급** : 그래프 순회 효율성
  * 🏆 **추천 프로파일** : `balanced`, `comprehensive`

#### CrewAI

  * ✅ **Layer 1** : TCR, Accuracy, Cost, Latency
  * 🎯 **Layer 2** : Agent Coordination (상호작용 자동 추적)
  * 📊 **고급** : G-Eval, Toxicity (멀티 에이전트 출력)
  * 🏆 **추천 프로파일** : `balanced`, `comprehensive`

#### AutoGen

  * ✅ **Layer 1** : TCR, Accuracy, Cost, Latency
  * 🎯 **Layer 2** : 수동 추적 권장
  * 📊 **고급** : Answer Relevancy, Coherence
  * 🏆 **추천 프로파일** : `balanced`, `lightweight`

* * *

## 6\. Layer 2 메트릭 자동 추적

### 6.1 개요

Agent Evaluator는 프레임워크별로 **Layer 2 메트릭** 을 자동으로 추적합니다:

메트릭 | 설명 | 프레임워크 | 추적 방식  
---|---|---|---  
**Tool Selection** | 도구 선택 정확도 (Precision, Recall, F1) | LangChain | 콜백 (`on_agent_action`)  
**Agent Coordination** | 에이전트 간 협업 품질 (0-10 점수) | CrewAI | 래퍼 (`_track_agent_interactions`)  
**Workflow Execution** | 워크플로우 실행 성공률 (%) | LangGraph | 래퍼 (`_wrap_node_for_tracking`)  
  
### 6.2 Tool Selection (LangChain)

**자동 추적 메커니즘:**

```python
    [](<#cb27-1>)# agent_evaluator/integrations/__init__.py
    [](<#cb27-2>)class LangChainEvaluator:
    [](<#cb27-3>)    def __init__(self, monitor, expected_tools=None):
    [](<#cb27-4>)        self.expected_tools = expected_tools
    [](<#cb27-5>)        self.tool_calls = []
    [](<#cb27-6>)
    [](<#cb27-7>)    def on_agent_action(self, action: AgentAction, **kwargs):
    [](<#cb27-8>)        """도구 호출 시 자동 기록"""
    [](<#cb27-9>)        self.tool_calls.append({
    [](<#cb27-10>)            "tool_name": action.tool,
    [](<#cb27-11>)            "parameters": {"input": str(action.tool_input)},
    [](<#cb27-12>)            "success": True,
    [](<#cb27-13>)            "duration": 0.01
    [](<#cb27-14>)        })
    [](<#cb27-15>)
    [](<#cb27-16>)    def on_chain_end(self, outputs, **kwargs):
    [](<#cb27-17>)        """체인 완료 시 자동 평가"""
    [](<#cb27-18>)        if self.expected_tools:
    [](<#cb27-19>)            actual_tools = [tool["tool_name"] for tool in self.tool_calls]
    [](<#cb27-20>)            self.monitor.tool_selection_tracker.evaluate_selection(
    [](<#cb27-21>)                task_id=self.current_task_id,
    [](<#cb27-22>)                expected_tools=self.expected_tools,
    [](<#cb27-23>)                actual_tools=actual_tools
    [](<#cb27-24>)            )
```

**사용 예제:**

```json
    [](<#cb28-1>)# Golden Dataset에서 expected_tools 로드
    [](<#cb28-2>)golden_dataset = {
    [](<#cb28-3>)    "task_1": {"expected_tools": ["search", "calculator"]},
    [](<#cb28-4>)    "task_2": {"expected_tools": ["python_repl", "file_read"]}
    [](<#cb28-5>)}
    [](<#cb28-6>)
    [](<#cb28-7>)# 각 task마다 expected_tools 전달
    [](<#cb28-8>)for task_id, data in golden_dataset.items():
    [](<#cb28-9>)    evaluator = LangChainEvaluator(agent,
    [](<#cb28-10>)        monitor,
    [](<#cb28-11>)        expected_tools=data["expected_tools"]
    [](<#cb28-12>)    )
    [](<#cb28-13>)    result = agent_executor.invoke(
    [](<#cb28-14>)        {"input": data["query"]},
    [](<#cb28-15>)        config={"callbacks": [callback]}
    [](<#cb28-16>)    )
    [](<#cb28-17>)
    [](<#cb28-18>)# 전체 통계 확인
    [](<#cb28-19>)stats = monitor.tool_selection_tracker.get_accuracy_stats()
    [](<#cb28-20>)print(f"Overall Tool Selection Accuracy: {stats['avg_accuracy']:.1f}%")
    [](<#cb28-21>)print(f"Precision: {stats['avg_precision']:.1f}%")
    [](<#cb28-22>)print(f"Recall: {stats['avg_recall']:.1f}%")
    [](<#cb28-23>)print(f"F1 Score: {stats['avg_f1_score']:.1f}%")
```

### 6.3 Agent Coordination (CrewAI)

**자동 추적 메커니즘:**

```python
    [](<#cb29-1>)# agent_evaluator/integrations/__init__.py
    [](<#cb29-2>)class CrewAIEvaluator:
    [](<#cb29-3>)    def kickoff(self, inputs=None):
    [](<#cb29-4>)        if self.enable_coordination_tracking:
    [](<#cb29-5>)            self._track_agent_interactions_start(task_id)
    [](<#cb29-6>)
    [](<#cb29-7>)        result = self.crew.kickoff(inputs=inputs)
    [](<#cb29-8>)
    [](<#cb29-9>)        if self.enable_coordination_tracking:
    [](<#cb29-10>)            self._track_agent_interactions_end(task_id)
    [](<#cb29-11>)
    [](<#cb29-12>)    def _track_agent_interactions_start(self, task_id: str):
    [](<#cb29-13>)        """Crew의 agents 리스트에서 상호작용 추출"""
    [](<#cb29-14>)        agent_names = [agent.role for agent in self.crew.agents]
    [](<#cb29-15>)
    [](<#cb29-16>)        # 순차적 상호작용 시뮬레이션
    [](<#cb29-17>)        for i in range(len(agent_names) - 1):
    [](<#cb29-18>)            from_agent = agent_names[i]
    [](<#cb29-19>)            to_agent = agent_names[i + 1]
    [](<#cb29-20>)            interaction_type = "delegation" if i == 0 else "collaboration"
    [](<#cb29-21>)
    [](<#cb29-22>)            self.agent_interactions.append({
    [](<#cb29-23>)                "from_agent": from_agent,
    [](<#cb29-24>)                "to_agent": to_agent,
    [](<#cb29-25>)                "interaction_type": interaction_type,
    [](<#cb29-26>)                "success": True
    [](<#cb29-27>)            })
    [](<#cb29-28>)
    [](<#cb29-29>)    def _track_agent_interactions_end(self, task_id: str):
    [](<#cb29-30>)        """Monitor의 AgentCoordinationTracker에 기록"""
    [](<#cb29-31>)        for interaction in self.agent_interactions:
    [](<#cb29-32>)            self.monitor.agent_coordination_tracker.track_interaction(
    [](<#cb29-33>)                task_id=task_id,
    [](<#cb29-34>)                from_agent=interaction["from_agent"],
    [](<#cb29-35>)                to_agent=interaction["to_agent"],
    [](<#cb29-36>)                interaction_type=interaction["interaction_type"],
    [](<#cb29-37>)                success=interaction["success"],
    [](<#cb29-38>)                context={"framework": "crewai"}
    [](<#cb29-39>)            )
```

**사용 예제:**

```json
    [](<#cb30-1>)# 에이전트 간 상호작용 자동 추적
    [](<#cb30-2>)evaluator = CrewAIEvaluator(
    [](<#cb30-3>)    crew,
    [](<#cb30-4>)    monitor,
    [](<#cb30-5>)    enable_coordination_tracking=True,
    [](<#cb30-6>)    expected_agents=["researcher", "writer", "reviewer"]
    [](<#cb30-7>))
    [](<#cb30-8>)
    [](<#cb30-9>)result = evaluated_crew.kickoff()
    [](<#cb30-10>)
    [](<#cb30-11>)# Coordination 점수 확인
    [](<#cb30-12>)score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    [](<#cb30-13>)print(f"Coordination Score: {score_data['score']:.1f}/10")
    [](<#cb30-14>)print(f"Success Rate: {score_data['success_rate']:.1f}%")
    [](<#cb30-15>)print(f"Total Interactions: {score_data['total_interactions']}")
    [](<#cb30-16>)
    [](<#cb30-17>)# Delegation 성공률
    [](<#cb30-18>)delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()
    [](<#cb30-19>)print(f"Delegation Success Rate: {delegation_rate:.1f}%")
```

### 6.4 Workflow Execution (LangGraph)

**자동 추적 메커니즘:**

```python
    [](<#cb31-1>)# agent_evaluator/integrations/__init__.py
    [](<#cb31-2>)class LangGraphEvaluator:
    [](<#cb31-3>)    def add_node(self, name: str, func):
    [](<#cb31-4>)        if self.enable_workflow_tracking:
    [](<#cb31-5>)            wrapped_func = self._wrap_node_for_tracking(name, func)
    [](<#cb31-6>)            self.workflow.add_node(name, wrapped_func)
    [](<#cb31-7>)
    [](<#cb31-8>)    def _wrap_node_for_tracking(self, node_name: str, func):
    [](<#cb31-9>)        """노드를 래핑하여 실행 시간 및 성공/실패 추적"""
    [](<#cb31-10>)        def wrapped(state: AgentState):
    [](<#cb31-11>)            start_time = time.time()
    [](<#cb31-12>)            success = True
    [](<#cb31-13>)            error = None
    [](<#cb31-14>)
    [](<#cb31-15>)            try:
    [](<#cb31-16>)                result = func(state)
    [](<#cb31-17>)            except Exception as e:
    [](<#cb31-18>)                success = False
    [](<#cb31-19>)                error = str(e)
    [](<#cb31-20>)                result = state
    [](<#cb31-21>)
    [](<#cb31-22>)            execution_time = time.time() - start_time
    [](<#cb31-23>)
    [](<#cb31-24>)            # WorkflowExecutionTracker에 기록
    [](<#cb31-25>)            self.monitor.workflow_tracker.track_step(
    [](<#cb31-26>)                task_id=self.current_task_id,
    [](<#cb31-27>)                step_name=node_name,
    [](<#cb31-28>)                step_type="node",
    [](<#cb31-29>)                success=success,
    [](<#cb31-30>)                execution_time=execution_time,
    [](<#cb31-31>)                framework="langgraph",
    [](<#cb31-32>)                metadata={"error": error} if error else {}
    [](<#cb31-33>)            )
    [](<#cb31-34>)
    [](<#cb31-35>)            # state에도 기록
    [](<#cb31-36>)            if "evaluation_data" in result:
    [](<#cb31-37>)                result["evaluation_data"]["workflow_steps"].append({
    [](<#cb31-38>)                    "step_name": node_name,
    [](<#cb31-39>)                    "success": success,
    [](<#cb31-40>)                    "execution_time": execution_time
    [](<#cb31-41>)                })
    [](<#cb31-42>)
    [](<#cb31-43>)            return result
    [](<#cb31-44>)
    [](<#cb31-45>)        return wrapped
```

**사용 예제:**

```json
    [](<#cb32-1>)# 워크플로우 단계 자동 추적
    [](<#cb32-2>)evaluator = LangGraphEvaluator(
    [](<#cb32-3>)    monitor,
    [](<#cb32-4>)    enable_workflow_tracking=True,
    [](<#cb32-5>)    expected_workflow_steps=["retrieval", "generation", "validation"]
    [](<#cb32-6>))
    [](<#cb32-7>)
    [](<#cb32-8>)# 노드 추가 (자동으로 래핑됨)
    [](<#cb32-9>)workflow.add_node("retrieval", retrieval_func)
    [](<#cb32-10>)workflow.add_node("generation", generation_func)
    [](<#cb32-11>)workflow.add_node("validation", validation_func)
    [](<#cb32-12>)
    [](<#cb32-13>)# 실행
    [](<#cb32-14>)result = workflow.compile_and_run({"messages": ["input"]})
    [](<#cb32-15>)
    [](<#cb32-16>)# Workflow 통계 확인
    [](<#cb32-17>)stats = monitor.workflow_tracker.calculate_execution_success_rate(framework="langgraph")
    [](<#cb32-18>)print(f"Step Success Rate: {stats['step_success_rate']:.1f}%")
    [](<#cb32-19>)print(f"Task Success Rate: {stats['task_success_rate']:.1f}%")
    [](<#cb32-20>)print(f"Total Steps: {stats['total_steps']}")
    [](<#cb32-21>)
    [](<#cb32-22>)# 그래프 순회 효율성
    [](<#cb32-23>)efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
    [](<#cb32-24>)print(f"Graph Traversal Efficiency: {efficiency['efficiency']:.1f}%")
    [](<#cb32-25>)print(f"Nodes Executed: {efficiency['nodes_executed']}")
```

### 6.5 Layer 2 메트릭 임계값 설정

```python
    [](<#cb33-1>)# 임계값 설정
    [](<#cb33-2>)monitor.thresholds = {
    [](<#cb33-3>)    # Layer 1
    [](<#cb33-4>)    'tcr': 90.0,
    [](<#cb33-5>)    'accuracy': 85.0,
    [](<#cb33-6>)    'cost': 0.10,
    [](<#cb33-7>)    'latency': 3.0,
    [](<#cb33-8>)    # Layer 2
    [](<#cb33-9>)    'tool_selection_accuracy': 80.0,  # 🆕
    [](<#cb33-10>)    'agent_coordination': 7.0,  # 🆕 0-10 척도
    [](<#cb33-11>)    'workflow_execution': 90.0  # 🆕
    [](<#cb33-12>)}
    [](<#cb33-13>)
    [](<#cb33-14>)# 임계값 비교
    [](<#cb33-15>)comparison = monitor.compare_with_thresholds()
    [](<#cb33-16>)
    [](<#cb33-17>)# Layer 2 메트릭만 필터링
    [](<#cb33-18>)for metric, data in comparison.items():
    [](<#cb33-19>)    if data.get('layer') == 'Layer 2':
    [](<#cb33-20>)        status_icon = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb33-21>)        print(f"{status_icon} {data['name']}: {data['value']:.1f}{data['unit']} (threshold: {data['threshold']}{data['unit']})")
```

* * *

## 7\. 모범 사례

### 7.1 통합 체크리스트

  * Monitor 초기화 (적절한 pricing 설정)
  * 프레임워크별 래퍼/콜백 클래스 선택
  * Layer 2 자동 추적 활성화 (expected_tools, expected_agents 등)
  * Golden Dataset 준비 (expected values)
  * 에러 핸들링 구현
  * 주기적인 리포트 생성
  * 임계값 설정 및 비교

### 7.2 성능 최적화 팁

  1. **콜백 vs 래퍼** :

     * LangChain: 콜백 기반 (낮은 오버헤드)
     * CrewAI/AutoGen: 래퍼 기반 (투명한 통합)
  2. **Layer 2 샘플링** :

``` [](<#cb34-1>)import random
         [](<#cb34-2>)enable_layer2 = (random.random() < 0.1)  # 10%만 Layer 2 평가
         [](<#cb34-3>)evaluator = LangChainEvaluator(agent,
         [](<#cb34-4>)    monitor,
         [](<#cb34-5>)    expected_tools=expected_tools if enable_layer2 else None
         [](<#cb34-6>))
```

  3. **비동기 처리** :

     * Layer 1 메트릭은 동기적으로 추적
     * 고급 메트릭(DeepEval, RAGAS)은 비동기로 평가

### 7.3 문제 해결

**문제: 토큰 수가 정확하지 않음** \- **해결** : LLM 응답에서 `usage` 정보 추출

```python
    [](<#cb35-1>)# LangChain 콜백에서
    [](<#cb35-2>)def on_llm_end(self, response: LLMResult, **kwargs):
    [](<#cb35-3>)    if response.llm_output:
    [](<#cb35-4>)        token_usage = response.llm_output.get("token_usage", {})
    [](<#cb35-5>)        self.tokens_used["input"] = token_usage.get("prompt_tokens", 0)
    [](<#cb35-6>)        self.tokens_used["output"] = token_usage.get("completion_tokens", 0)
```

**문제: CrewAI에서 에이전트 상호작용을 정확히 추적할 수 없음** \- **해결** : CrewAI는 내부 로그를 제공하지 않으므로 순차적 상호작용 시뮬레이션 사용 - 더 정확한 추적을 위해서는 CrewAI의 커스텀 콜백 구현 필요

**문제: Layer 2 메트릭이 너무 느림** \- **해결** : 샘플링 사용 또는 배치 평가

```json
    [](<#cb36-1>)# 10개마다 한 번만 Layer 2 평가
    [](<#cb36-2>)if task_count % 10 == 0:
    [](<#cb36-3>)    evaluator = CrewAIEvaluator(
    [](<#cb36-4>)        crew,
    [](<#cb36-5>)        monitor,
    [](<#cb36-6>)        enable_coordination_tracking=True
    [](<#cb36-7>)    )
```

* * *

* * *

## 💻 개발자 가이드 (Developer Guide)

### 🎯 가이드 개요

이 가이드는 **개발자(Developer)** 가 Agent Evaluator를 **프레임워크와 통합하여 실전에서 활용** 하는 방법을 제공합니다. 

**학습 목표:**

  * ✅ 프레임워크별 실전 통합 구현
  * ✅ 성능 최적화 및 오버헤드 최소화
  * ✅ 효과적인 디버깅 및 문제 해결
  * ✅ 프로덕션 환경 배포 전략
  * ✅ 고급 기능 활용 (커스텀 메트릭, 분산 추적)

### 8.1 실전 구현 가이드

#### 8.1.1 프레임워크별 통합 체크리스트

**🔗 LangChain 통합 체크리스트**

단계 | 작업 | 코드 예시 | 확인 사항  
---|---|---|---  
1\. 설치 | 필수 패키지 설치 | `pip install langchain agent-evaluator` | 버전 호환성  
2\. Monitor 생성 | Monitor 인스턴스 초기화 | `monitor = Monitor()` | -  
3\. Callback 생성 | AdvancedLangChainCallback 생성 | `callback = AdvancedLangChainCallback(monitor)` | Monitor 전달 확인  
4\. 통합 | Agent/Chain에 Callback 추가 | `agent.invoke(input, callbacks=[callback])` | 모든 호출에 적용  
5\. 검증 | 메트릭 수집 확인 | `metrics = monitor.calculate_metrics()` | 모든 메트릭 값 존재  
  
**🕸️ LangGraph 통합 체크리스트**

단계 | 작업 | 코드 예시 | 확인 사항  
---|---|---|---  
1\. 설치 | LangGraph 설치 | `pip install langgraph` | -  
2\. 그래프 정의 | StateGraph 생성 | `graph = StateGraph(AgentState)` | State 타입 정의  
3\. Callback 통합 | 컴파일 시 Callback 설정 | `app = graph.compile()` | -  
4\. 실행 | invoke 시 Callback 전달 | `app.invoke(input, {"callbacks": [callback]})` | -  
5\. 검증 | 워크플로우 메트릭 확인 | `monitor.calculate_metrics()["layer2_metrics"]` | workflow_efficiency  
  
**🚢 CrewAI 통합 체크리스트**

단계 | 작업 | 코드 예시 | 확인 사항  
---|---|---|---  
1\. 설치 | CrewAI 설치 | `pip install crewai` | -  
2\. Agent 정의 | Agent 생성 (role, goal, backstory) | `Agent(role="...", goal="...")` | 명확한 역할 정의  
3\. Task 정의 | Task 생성 (description, agent) | `Task(description="...", agent=agent)` | Agent 할당  
4\. Crew 생성 | Crew 구성 및 Monitor 설정 | `Crew(agents=[...], tasks=[...], monitor=monitor)` | Monitor 전달  
5\. 검증 | Coordination 메트릭 확인 | `monitor.calculate_metrics()["layer2_metrics"]["agent_coordination_score"]` | > 3.0  
  
**🤖 AutoGen 통합 체크리스트**

단계 | 작업 | 코드 예시 | 확인 사항  
---|---|---|---  
1\. 설치 | AutoGen 설치 | `pip install autogen-agentchat autogen-core` | -
2\. Agent 정의 | AssistantAgent, UserProxyAgent 생성 | `AssistantAgent(name="...")` | llm_config 설정  
3\. Monitor 통합 | register_reply 오버라이드 | `agent.register_reply(...)` | 모든 메시지 추적  
4\. 실행 | initiate_chat 실행 | `user_proxy.initiate_chat(assistant, message="...")` | -  
5\. 검증 | Communication Overhead 확인 | `monitor.calculate_metrics()["layer2_metrics"]["communication_overhead"]` | < 20%  
  
#### 8.1.2 공통 구현 패턴

**패턴 1: Monitor 싱글톤 패턴**

```python
    # 싱글톤으로 Monitor 관리 (전역 상태 공유)
    class MonitorManager:
        _instance = None
        _monitor = None
    
        @classmethod
        def get_monitor(cls):
            """싱글톤 Monitor 인스턴스 반환"""
            if cls._instance is None:
                cls._instance = cls()
                cls._monitor = Monitor()
            return cls._monitor
    
        @classmethod
        def reset(cls):
            """테스트 후 초기화"""
            cls._instance = None
            cls._monitor = None
    
    # 사용 예시
    monitor = MonitorManager.get_monitor()
    callback = AdvancedLangChainCallback(monitor)
    
    # 테스트 후 초기화
    MonitorManager.reset()
```

**패턴 2: Context Manager 패턴**

```python
    # 자동 시작/종료 관리
    from contextlib import contextmanager
    from datetime import datetime
    
    @contextmanager
    def track_agent_task(monitor, task_id: str, task_type: str):
        """Agent 작업 자동 추적"""
        task_data = {
            "task_id": task_id,
            "task_type": task_type,
            "start_time": datetime.now()
        }
    
        monitor.start_task(task_data)
    
        try:
            yield monitor
        except Exception as e:
            # 실패 기록
            monitor.end_task(
                task_id=task_id,
                success=False,
                error=str(e)
            )
            raise
        else:
            # 성공 기록
            monitor.end_task(
                task_id=task_id,
                success=True
            )
    
    # 사용 예시
    with track_agent_task(monitor, "task_001", "code_generation") as mon:
        result = agent.invoke({"input": "Generate Python code..."})
        # 자동으로 성공/실패 기록됨
```

**패턴 3: Decorator 패턴**

```python
    # 함수 데코레이터로 자동 추적
    from functools import wraps
    
    def track_agent_function(monitor, task_type: str):
        """함수 실행 자동 추적 데코레이터"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                task_id = f"{func.__name__}_{datetime.now().timestamp()}"
    
                with track_agent_task(monitor, task_id, task_type):
                    return func(*args, **kwargs)
    
            return wrapper
        return decorator
    
    # 사용 예시
    @track_agent_function(monitor, "data_analysis")
    def analyze_data(data):
        """데이터 분석 함수"""
        return agent.invoke({"input": f"Analyze: {data}"})
    
    # 호출 시 자동으로 추적됨
    result = analyze_data("sales_data.csv")
```

#### 8.1.3 에러 처리 전략

**전략 1: Graceful Degradation (점진적 저하)**

```python
    # Monitor 실패 시에도 Agent는 정상 작동
    def safe_monitor_operation(func):
        """Monitor 작업을 안전하게 실행"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Monitor 오류는 로깅만 하고 계속 진행
                logger.warning(f"Monitor operation failed: {e}")
                return None
        return wrapper
    
    class SafeMonitor:
        def __init__(self, monitor):
            self.monitor = monitor
    
        @safe_monitor_operation
        def start_task(self, *args, **kwargs):
            return self.monitor.start_task(*args, **kwargs)
    
        @safe_monitor_operation
        def end_task(self, *args, **kwargs):
            return self.monitor.end_task(*args, **kwargs)
    
    # 사용 예시
    safe_monitor = SafeMonitor(monitor)
    safe_monitor.start_task({"task_id": "task_001"})  # 실패해도 예외 없음
```

**전략 2: Retry 메커니즘**

```python
    # Monitor 작업 재시도
    from tenacity import retry, stop_after_attempt, wait_exponential
    
    class ResilientMonitor:
        def __init__(self, monitor):
            self.monitor = monitor
    
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10)
        )
        def save_to_file(self, filename: str):
            """파일 저장 재시도 (최대 3회)"""
            return self.monitor.save_to_file(filename)
    
    # 사용 예시
    resilient_monitor = ResilientMonitor(monitor)
    resilient_monitor.save_to_file("results.json")  # 실패 시 자동 재시도
```

**전략 3: Fallback 메커니즘**

```python
    # 기본값 제공
    def get_metrics_safe(monitor, default=None):
        """메트릭 안전하게 가져오기"""
        try:
            return monitor.calculate_metrics()
        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            # 기본값 반환
            return default or {
                "layer1_metrics": {},
                "layer2_metrics": {},
                "error": str(e)
            }
    
    # 사용 예시
    metrics = get_metrics_safe(monitor, default={"layer1_metrics": {"tcr": 0.0}})
```

### 8.2 성능 최적화

#### 8.2.1 메트릭 수집 오버헤드 최소화

**오버헤드 측정**

시나리오 | Monitor 없음 | Monitor 있음 | 오버헤드 | 허용 범위  
---|---|---|---|---  
단순 Chain (3 steps) | 1.2초 | 1.25초 | +4% | ✅ < 5%  
복잡한 Agent (10 tools) | 5.8초 | 6.1초 | +5% | ✅ < 10%  
멀티 Agent (5 agents) | 12.3초 | 13.2초 | +7% | ✅ < 10%  
대량 배치 (100 tasks) | 120초 | 135초 | +12% | ⚠️ > 10%  
  
**최적화 기법 1: 샘플링**

```python
    # 모든 요청을 추적하지 않고 일부만 샘플링
    import random
    
    class SamplingMonitor:
        def __init__(self, monitor, sample_rate=0.1):
            """
            sample_rate: 0.0 ~ 1.0 (0.1 = 10% 샘플링)
            """
            self.monitor = monitor
            self.sample_rate = sample_rate
    
        def should_track(self):
            """확률적으로 추적 여부 결정"""
            return random.random() < self.sample_rate
    
        def start_task(self, *args, **kwargs):
            if self.should_track():
                return self.monitor.start_task(*args, **kwargs)
    
        def end_task(self, *args, **kwargs):
            if self.should_track():
                return self.monitor.end_task(*args, **kwargs)
    
    # 사용 예시
    sampling_monitor = SamplingMonitor(monitor, sample_rate=0.1)  # 10%만 추적
    # → 오버헤드 12% → 1.2%로 감소
```

**최적화 기법 2: 비동기 수집**

```python
    # 메트릭 수집을 백그라운드 스레드에서 처리
    import threading
    import queue
    
    class AsyncMonitor:
        def __init__(self, monitor):
            self.monitor = monitor
            self.task_queue = queue.Queue()
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()
    
        def _worker(self):
            """백그라운드 작업 처리"""
            while True:
                try:
                    task = self.task_queue.get(timeout=1)
                    if task is None:
                        break
    
                    # 실제 Monitor 작업 수행
                    method, args, kwargs = task
                    method(*args, **kwargs)
    
                    self.task_queue.task_done()
                except queue.Empty:
                    continue
    
        def start_task(self, *args, **kwargs):
            """비동기로 task 시작 (즉시 반환)"""
            self.task_queue.put((self.monitor.start_task, args, kwargs))
    
        def end_task(self, *args, **kwargs):
            """비동기로 task 종료 (즉시 반환)"""
            self.task_queue.put((self.monitor.end_task, args, kwargs))
    
        def shutdown(self):
            """종료 대기"""
            self.task_queue.join()  # 모든 작업 완료 대기
            self.task_queue.put(None)  # 종료 신호
            self.worker_thread.join()
    
    # 사용 예시
    async_monitor = AsyncMonitor(monitor)
    async_monitor.start_task({"task_id": "task_001"})  # 즉시 반환
    # ... Agent 실행 ...
    async_monitor.end_task(task_id="task_001")  # 즉시 반환
    async_monitor.shutdown()  # 프로그램 종료 시
```

**최적화 기법 3: 배치 처리**

```python
    # 메트릭을 모아서 한 번에 저장
    class BatchMonitor:
        def __init__(self, monitor, batch_size=10):
            self.monitor = monitor
            self.batch_size = batch_size
            self.task_buffer = []
    
        def add_task(self, task_data):
            """Task를 버퍼에 추가"""
            self.task_buffer.append(task_data)
    
            # 버퍼가 가득 차면 저장
            if len(self.task_buffer) >= self.batch_size:
                self.flush()
    
        def flush(self):
            """버퍼의 모든 task를 한 번에 저장"""
            if not self.task_buffer:
                return
    
            for task in self.task_buffer:
                self.monitor.add_task(task)
    
            self.task_buffer.clear()
    
        def __del__(self):
            """객체 소멸 시 남은 task 저장"""
            self.flush()
    
    # 사용 예시
    batch_monitor = BatchMonitor(monitor, batch_size=10)
    for i in range(100):
        batch_monitor.add_task({"task_id": f"task_{i}"})
        # 10개마다 자동으로 저장됨
    batch_monitor.flush()  # 남은 것 저장
```

#### 8.2.2 메모리 최적화

**문제: 대량 작업 시 메모리 증가**

작업 수 | 메모리 사용량 | 문제점  
---|---|---  
100 | 50 MB | -  
1,000 | 500 MB | -  
10,000 | 5 GB | ⚠️ 메모리 부족  
100,000 | 50 GB | ❌ OOM (Out of Memory)  
  
**해결책: 주기적 파일 저장 및 메모리 클리어**

```python
    # 일정 주기마다 파일에 저장하고 메모리 정리
    class StreamingMonitor:
        def __init__(self, monitor, output_dir="./evaluation_results", flush_interval=100):
            self.monitor = monitor
            self.output_dir = output_dir
            self.flush_interval = flush_interval
            self.task_count = 0
            self.file_count = 0
    
        def add_task(self, task_data):
            """Task 추가"""
            self.monitor.add_task(task_data)
            self.task_count += 1
    
            # flush_interval마다 저장 및 클리어
            if self.task_count >= self.flush_interval:
                self.flush()
    
        def flush(self):
            """현재 데이터를 파일에 저장하고 메모리 클리어"""
            filename = f"{self.output_dir}/batch_{self.file_count:04d}.json"
            self.monitor.save_to_file(filename)
    
            # Monitor 초기화 (메모리 클리어)
            self.monitor = Monitor()
    
            self.file_count += 1
            self.task_count = 0
    
            print(f"✓ Saved {filename}, memory cleared")
    
    # 사용 예시
    streaming_monitor = StreamingMonitor(monitor, flush_interval=1000)
    for i in range(10000):
        streaming_monitor.add_task({"task_id": f"task_{i}"})
        # 1000개마다 자동 저장 및 메모리 클리어
    streaming_monitor.flush()  # 마지막 남은 것 저장
    # → 메모리 사용량: 50 GB → 500 MB (1/100)
```

#### 8.2.3 성능 프로파일링

```python
    # Monitor 성능 측정
    import time
    from contextlib import contextmanager
    
    class ProfiledMonitor:
        def __init__(self, monitor):
            self.monitor = monitor
            self.timings = {}
    
        @contextmanager
        def profile(self, operation):
            """작업 시간 측정"""
            start = time.time()
            try:
                yield
            finally:
                elapsed = time.time() - start
                if operation not in self.timings:
                    self.timings[operation] = []
                self.timings[operation].append(elapsed)
    
        def start_task(self, *args, **kwargs):
            with self.profile("start_task"):
                return self.monitor.start_task(*args, **kwargs)
    
        def end_task(self, *args, **kwargs):
            with self.profile("end_task"):
                return self.monitor.end_task(*args, **kwargs)
    
        def calculate_metrics(self, *args, **kwargs):
            with self.profile("calculate_metrics"):
                return self.monitor.calculate_metrics(*args, **kwargs)
    
        def print_stats(self):
            """성능 통계 출력"""
            print("=== Monitor Performance Stats ===")
            for operation, times in self.timings.items():
                avg = sum(times) / len(times)
                total = sum(times)
                count = len(times)
                print(f"{operation}:")
                print(f"  Count: {count}")
                print(f"  Total: {total:.3f}s")
                print(f"  Average: {avg:.3f}s")
                print(f"  Min: {min(times):.3f}s")
                print(f"  Max: {max(times):.3f}s")
    
    # 사용 예시
    profiled_monitor = ProfiledMonitor(monitor)
    # ... 평가 실행 ...
    profiled_monitor.print_stats()
    # === Monitor Performance Stats ===
    # start_task:
    #   Count: 100
    #   Total: 0.523s
    #   Average: 0.005s
    # calculate_metrics:
    #   Count: 1
    #   Total: 0.234s
    #   Average: 0.234s
```

### 8.3 디버깅 및 문제 해결

#### 8.3.1 디버깅 모드 활성화

```python
    # 상세 로깅 설정
    import logging
    
    # 1. Monitor 디버깅 로그 활성화
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Agent Evaluator 로거
    logger = logging.getLogger("agent_evaluator")
    logger.setLevel(logging.DEBUG)
    
    # 2. 프레임워크별 디버깅
    # LangChain
    from langchain.globals import set_debug
    set_debug(True)  # 모든 Chain 실행 로깅
    
    # LangGraph
    # (내부적으로 LangChain 사용, 동일하게 적용됨)
    
    # CrewAI
    crew = Crew(
        agents=[...],
        tasks=[...],
        verbose=True  # 상세 로그 출력
    )
    
    # AutoGen
    assistant = AssistantAgent(
        name="assistant",
        llm_config=llm_config,
        verbose=True  # 대화 내용 출력
    )
```

#### 8.3.2 일반적인 문제 및 해결책

문제 | 증상 | 원인 | 해결책  
---|---|---|---  
🔴 메트릭이 0 | `tcr: 0.0, accuracy: 0.0` | Callback이 호출되지 않음 | `callbacks=[callback]` 확인  
🟠 Task가 기록 안 됨 | `monitor.tasks == []` | `start_task()` 누락 | 시작/종료 쌍 확인  
🟡 토큰 수가 0 | `input_tokens: 0` | LLM Callback 미연결 | `on_llm_start()` 호출 확인  
🟢 Layer 2 메트릭 없음 | `layer2_metrics: {}` | 도구/에이전트 정보 누락 | `on_tool_start()` 확인  
🔵 메모리 누수 | 메모리 계속 증가 | Monitor 초기화 안 함 | 주기적으로 `save_to_file()` \+ 새 Monitor  
⚫ 느린 성능 | 실행 시간 2배 증가 | 동기 I/O 병목 | AsyncMonitor 사용  
  
#### 8.3.3 문제 해결 체크리스트

**Step 1: 기본 설정 확인**

```python
    # 디버깅 체크리스트
    def debug_monitor_setup(monitor, callback):
        """Monitor 설정 검증"""
        print("=== Monitor Setup Debug ===")
    
        # 1. Monitor 인스턴스 확인
        print(f"✓ Monitor instance: {monitor}")
        print(f"  Tasks: {len(monitor.tasks)}")
    
        # 2. Callback 연결 확인
        print(f"✓ Callback instance: {callback}")
        print(f"  Monitor: {callback.monitor}")
    
        # 3. 테스트 작업 추가
        test_task = {"task_id": "test", "task_type": "test"}
        monitor.start_task(test_task)
        monitor.end_task(task_id="test", success=True)
    
        # 4. 메트릭 계산 가능 확인
        try:
            metrics = monitor.calculate_metrics()
            print(f"✓ Metrics calculated: {list(metrics.keys())}")
        except Exception as e:
            print(f"❌ Metrics calculation failed: {e}")
    
        print("=== Debug Complete ===")
    
    # 사용 예시
    debug_monitor_setup(monitor, callback)
```

**Step 2: 프레임워크별 확인**

```python
    # LangChain 디버깅
    def debug_langchain_integration(agent, callback):
        """LangChain 통합 검증"""
        print("=== LangChain Integration Debug ===")
    
        # 1. Callback 등록 확인
        test_input = {"input": "Hello"}
        result = agent.invoke(test_input, callbacks=[callback])
    
        # 2. Callback 호출 횟수 확인
        print(f"  on_llm_start called: {callback.on_llm_start_count}")
        print(f"  on_tool_start called: {callback.on_tool_start_count}")
    
        # 3. Monitor에 데이터 기록 확인
        print(f"  Tasks recorded: {len(callback.monitor.tasks)}")
    
        return result
    
    # 사용 예시
    debug_langchain_integration(agent, callback)
```

#### 8.3.4 로깅 전략

```python
    # 구조화된 로깅
    import json
    import logging
    
    class StructuredLogger:
        def __init__(self, name="agent_evaluator"):
            self.logger = logging.getLogger(name)
    
        def log_task(self, level, task_id, event, **kwargs):
            """작업 이벤트 로깅"""
            log_data = {
                "task_id": task_id,
                "event": event,
                **kwargs
            }
            self.logger.log(level, json.dumps(log_data))
    
        def log_metric(self, metric_name, value, **kwargs):
            """메트릭 로깅"""
            log_data = {
                "type": "metric",
                "name": metric_name,
                "value": value,
                **kwargs
            }
            self.logger.info(json.dumps(log_data))
    
    # 사용 예시
    logger = StructuredLogger()
    logger.log_task(logging.INFO, "task_001", "start", task_type="code_generation")
    logger.log_metric("tcr", 0.85, stage="production")
    
    # 로그 출력:
    # {"task_id": "task_001", "event": "start", "task_type": "code_generation"}
    # {"type": "metric", "name": "tcr", "value": 0.85, "stage": "production"}
```

### 8.4 프로덕션 배포

#### 8.4.1 배포 전 체크리스트

카테고리 | 체크 항목 | 확인 방법 | 상태  
---|---|---|---  
🔧 설정 | 환경 변수 설정 | `OPENAI_API_KEY` 등 확인 | [ ]  
🔧 설정 | Monitor 샘플링 설정 | `sample_rate=0.1` 적용 | [ ]  
📊 메트릭 | 임계값 설정 | `thresholds.json` 준비 | [ ]  
📊 메트릭 | Golden Dataset | 최소 30개 샘플 준비 | [ ]  
🚀 성능 | 오버헤드 측정 | < 10% 확인 | [ ]  
🚀 성능 | 메모리 사용량 | < 1GB 확인 | [ ]  
🔍 모니터링 | 로깅 설정 | INFO 레벨 설정 | [ ]  
🔍 모니터링 | 알림 설정 | Slack/Email 통합 | [ ]  
🛡️ 에러 처리 | Graceful Degradation | Monitor 실패 시 계속 작동 | [ ]  
🛡️ 에러 처리 | Retry 메커니즘 | 파일 저장 재시도 | [ ]  
  
#### 8.4.2 프로덕션 설정 예시

```python
    # 프로덕션 환경 설정
    import os
    from pathlib import Path
    
    class ProductionConfig:
        """프로덕션 환경 설정"""
    
        # 환경 변수
        ENV = os.getenv("ENV", "production")
    
        # Monitor 설정
        SAMPLE_RATE = float(os.getenv("MONITOR_SAMPLE_RATE", "0.1"))  # 10% 샘플링
        BATCH_SIZE = int(os.getenv("MONITOR_BATCH_SIZE", "100"))
    
        # 파일 저장
        OUTPUT_DIR = Path(os.getenv("MONITOR_OUTPUT_DIR", "./evaluation_results"))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
        # 임계값
        THRESHOLDS_FILE = os.getenv("THRESHOLDS_FILE", "thresholds/production/layer1_thresholds.json")
    
        # 로깅
        LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
        # 알림
        SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
    
        @classmethod
        def create_monitor(cls):
            """프로덕션용 Monitor 생성"""
            monitor = Monitor()
    
            # 샘플링 적용
            monitor = SamplingMonitor(monitor, sample_rate=cls.SAMPLE_RATE)
    
            # 비동기 처리
            monitor = AsyncMonitor(monitor)
    
            # 배치 처리
            monitor = BatchMonitor(monitor, batch_size=cls.BATCH_SIZE)
    
            # 에러 처리
            monitor = SafeMonitor(monitor)
    
            return monitor
    
    # 사용 예시
    config = ProductionConfig()
    monitor = config.create_monitor()
```

#### 8.4.3 모니터링 및 알림

```python
    # 메트릭 임계값 위반 시 알림
    import requests
    
    class MetricAlerter:
        def __init__(self, slack_webhook_url):
            self.slack_webhook = slack_webhook_url
    
        def check_and_alert(self, metrics, thresholds):
            """임계값 확인 및 알림"""
            violations = []
    
            # Layer 1 메트릭 확인
            layer1 = metrics.get("layer1_metrics", {})
    
            if layer1.get("task_completion_rate", 0) < thresholds.get("tcr", 85):
                violations.append({
                    "metric": "TCR",
                    "value": layer1["task_completion_rate"],
                    "threshold": thresholds["tcr"],
                    "severity": "critical"
                })
    
            # 위반 발생 시 알림 전송
            if violations:
                self.send_slack_alert(violations)
    
        def send_slack_alert(self, violations):
            """Slack 알림 전송"""
            message = "🚨 *Metric Threshold Violated*
    
    "
    
            for v in violations:
                message += f"• *{v['metric']}*: {v['value']:.1f}% < {v['threshold']}% (Severity: {v['severity']})
    "
    
            requests.post(
                self.slack_webhook,
                json={"text": message}
            )
    
    # 사용 예시
    alerter = MetricAlerter(slack_webhook_url=config.SLACK_WEBHOOK)
    metrics = monitor.calculate_metrics()
    thresholds = {"tcr": 85, "accuracy": 80}
    alerter.check_and_alert(metrics, thresholds)
```

### 8.5 고급 활용

#### 8.5.1 커스텀 메트릭 추가

```python
    # 비즈니스 메트릭 추가
    class CustomMetricsMonitor(Monitor):
        def __init__(self):
            super().__init__()
            self.business_metrics = {}
    
        def track_business_metric(self, name, value):
            """비즈니스 메트릭 추적"""
            if name not in self.business_metrics:
                self.business_metrics[name] = []
            self.business_metrics[name].append(value)
    
        def calculate_metrics(self):
            """기본 메트릭 + 커스텀 메트릭"""
            metrics = super().calculate_metrics()
    
            # 커스텀 메트릭 추가
            metrics["business_metrics"] = {}
            for name, values in self.business_metrics.items():
                metrics["business_metrics"][name] = {
                    "mean": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0
                }
    
            return metrics
    
    # 사용 예시
    custom_monitor = CustomMetricsMonitor()
    custom_monitor.track_business_metric("revenue_generated", 125.50)
    custom_monitor.track_business_metric("user_satisfaction", 4.5)
    metrics = custom_monitor.calculate_metrics()
    print(metrics["business_metrics"])
    # {
    #   "revenue_generated": {"mean": 125.5, "min": 125.5, "max": 125.5},
    #   "user_satisfaction": {"mean": 4.5, "min": 4.5, "max": 4.5}
    # }
```

#### 8.5.2 분산 추적 (Distributed Tracing)

```bash
    # OpenTelemetry 통합
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    
    # OpenTelemetry 설정
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    
    # Span Exporter 추가 (예: Jaeger, Zipkin)
    span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    trace.get_tracer_provider().add_span_processor(span_processor)
    
    class TracedMonitor(Monitor):
        def __init__(self):
            super().__init__()
            self.tracer = tracer
    
        def start_task(self, task_data):
            """Task 시작 시 Span 생성"""
            with self.tracer.start_as_current_span("agent_task") as span:
                span.set_attribute("task.id", task_data.get("task_id"))
                span.set_attribute("task.type", task_data.get("task_type"))
    
                result = super().start_task(task_data)
    
                return result
    
        def end_task(self, task_id, success=True, **kwargs):
            """Task 종료 시 Span 종료"""
            with self.tracer.start_as_current_span("agent_task_end") as span:
                span.set_attribute("task.id", task_id)
                span.set_attribute("task.success", success)
    
                result = super().end_task(task_id, success, **kwargs)
    
                return result
    
    # 사용 예시
    traced_monitor = TracedMonitor()
    # → Jaeger/Zipkin에서 분산 추적 가능
```

#### 8.5.3 멀티 프레임워크 통합

```python
    # 여러 프레임워크를 동시에 사용하는 경우
    class MultiFrameworkMonitor:
        def __init__(self):
            self.monitor = Monitor()
    
            # 각 프레임워크별 Callback
            self.langchain_callback = AdvancedLangChainCallback(self.monitor)
            self.crewai_config = {"monitor": self.monitor}
    
        def use_langchain(self, agent, input_data):
            """LangChain Agent 사용"""
            return agent.invoke(input_data, callbacks=[self.langchain_callback])
    
        def use_crewai(self, crew, task_input):
            """CrewAI 사용"""
            return crew.kickoff(inputs=task_input)
    
        def get_metrics(self):
            """전체 메트릭 (LangChain + CrewAI 통합)"""
            return self.monitor.calculate_metrics()
    
    # 사용 예시
    multi_monitor = MultiFrameworkMonitor()
    
    # LangChain 작업
    langchain_result = multi_monitor.use_langchain(langchain_agent, {"input": "..."})
    
    # CrewAI 작업
    crewai_result = multi_monitor.use_crewai(crew, {"task": "..."})
    
    # 통합 메트릭
    metrics = multi_monitor.get_metrics()
    # → LangChain + CrewAI 작업이 모두 포함된 메트릭
```

**✅ 개발자 핵심 원칙**

  1. **점진적 통합** : 작은 부분부터 시작 → 전체 확대
  2. **오버헤드 최소화** : 샘플링/비동기/배치 처리 활용
  3. **Graceful Degradation** : Monitor 실패 시에도 Agent는 정상 작동
  4. **철저한 로깅** : 디버깅 정보 충분히 남기기
  5. **프로덕션 준비** : 배포 전 체크리스트 완료
  6. **지속적 모니터링** : 메트릭 추세 관찰 및 알림 설정
  7. **문서화** : 설정/트러블슈팅 문서 작성

**⚠️ 주의사항**

  * ❌ **프로덕션에서 DEBUG 로깅 금지** : 성능 저하 및 로그 폭증
  * ❌ **동기 I/O 남발 금지** : 파일 저장은 비동기/배치로 처리
  * ❌ **메모리 누수 주의** : 대량 작업 시 주기적으로 파일 저장 + 클리어
  * ❌ **에러 무시 금지** : try-except로 감싸되 반드시 로깅

* * *

## 참고 자료

  * [LangChain 문서](<https://python.langchain.com/>)
  * [LangGraph 문서](<https://langchain-ai.github.io/langgraph/>)
  * [CrewAI 문서](<https://docs.crewai.com/>)
  * [AutoGen 문서](<https://microsoft.github.io/autogen/>)
  * [메트릭 가이드](<05_METRICS_GUIDE.md>)
  * [Golden Dataset 가이드](<04_GOLDEN_DATASET.md>)
