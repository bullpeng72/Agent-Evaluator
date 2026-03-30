# 🤖 Framework × Metrics Support Map

Agent Evaluator가 지원하는 4개 프레임워크별 지표 커버리지 현황

CrewAI · LangChain · LangGraph · AutoGen | Version 0.6.3 | 2026-03-30

---

## 목차

1. [범례 및 설치](#범례-및-설치)
2. [프레임워크 프로필](#프레임워크-프로필)
3. [지표 지원 매트릭스 (전체 25개)](#지표-지원-매트릭스-전체-25개)
4. [토큰 측정 정확도 비교](#토큰-측정-정확도-비교)
5. [프레임워크별 빠른 시작](#프레임워크별-빠른-시작)
6. [구현 참고사항 및 제한](#구현-참고사항-및-제한)

---

## 범례 및 설치

| 기호 | 의미 |
|------|------|
| ✅ | **자동 지원** — 통합 클래스가 자동으로 수집 |
| 🔶 | **부분 지원** — 수집되나 추정값 또는 정확도 제한 |
| 🔧 | **수동 호출** — `enable_security_metrics=True` + 직접 API 호출 필요 |
| ✗  | **미지원** — 해당 통합에서 구현되지 않음 |

### 설치 명령어

| 프레임워크 | 설치 | 통합 클래스 | 팩토리 함수 |
|-----------|------|------------|------------|
| 🔵 CrewAI    | `pip install agent-evaluator[crewai]`    | `CrewAIEvaluator`    | `create_evaluated_crew()` |
| 🟢 LangChain | `pip install agent-evaluator[langchain]` | `LangChainEvaluator` | `create_evaluated_langchain_agent()` |
| 🟠 LangGraph | `pip install agent-evaluator[langchain]` | `LangGraphEvaluator` | `create_evaluated_langgraph()` |
| 🟣 AutoGen   | `pip install agent-evaluator[autogen]`   | `AutoGenEvaluator`   | `create_evaluated_autogen_agent()` |

> **프레임워크 가용성 확인:**
> ```python
> from agent_evaluator.integrations.framework_integrations import (
>     check_framework_availability, get_installation_instructions, print_framework_status
> )
> print_framework_status()                            # 전체 설치 현황 출력
> avail = check_framework_availability("langchain")   # 특정 프레임워크 확인
> print(get_installation_instructions("crewai"))      # 설치 안내 메시지
> ```

---

## 프레임워크 프로필

### 🔵 CrewAI

| 항목 | 내용 |
|------|------|
| 아키텍처 | 역할 기반 멀티에이전트 |
| 추적 방식 | Pre/Post 실행 래핑 |
| 토큰 계산 | 추정값 (0으로 초기화) — 수동 설정 필요 |
| 도구 추적 | agents 속성 추론 |
| 멀티에이전트 | ✅ 지원 |
| 전체 지표 커버리지 | **~78%** (25개 중 ~20개) |

### 🟢 LangChain

| 항목 | 내용 |
|------|------|
| 아키텍처 | Chain + Agent 기반 |
| 추적 방식 | 콜백 핸들러 (실시간) |
| 토큰 계산 | ✅ LLM 실제 응답값 |
| 도구 추적 | ✅ AgentAction 실시간 |
| 멀티에이전트 | ✗ 단일 에이전트 |
| 전체 지표 커버리지 | **~82%** (25개 중 ~21개) |

### 🟠 LangGraph

| 항목 | 내용 |
|------|------|
| 아키텍처 | 상태 머신 / 그래프 |
| 추적 방식 | stream() 기반 노드 래핑 (per-node 실측 타이밍) |
| 토큰 계산 | 🔶 AIMessage.usage_metadata (LC LLM 사용 시) |
| 도구 추적 | 🔶 ToolMessage 파싱 (LC LLM 사용 시) |
| 멀티에이전트 | 🔶 노드 전환 기반 부분 지원 |
| 전체 지표 커버리지 | **~82%** (25개 중 ~21개) |

### 🟣 AutoGen

| 항목 | 내용 |
|------|------|
| 아키텍처 | 대화형 멀티에이전트 |
| 추적 방식 | on_messages() / team.run() 통합 (async-first, 0.4+) |
| 토큰 계산 | 🔶 tiktoken 우선, 한/영 휴리스틱 fallback |
| 도구 추적 | ✅ ToolCallRequestEvent/ToolCallExecutionEvent 기반 (0.4+) |
| 멀티에이전트 | ✅ 메시지 기반 |
| 전체 지표 커버리지 | **~80%** (25개 중 ~20개) |

---

## 지표 지원 매트릭스 (전체 25개)

### 🎯 Layer 1 — Foundation 지표 (6개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 1 | **Task Completion Rate (TCR)**<br>완전/부분/실패 분류 · success 필드 | ✅ 예외 기반 자동 | ✅ 콜백 기반 자동 | ✅ 노드 오류 기반 | ✅ 예외 기반 자동 |
| 2 | **Accuracy**<br>Token Overlap·Jaccard·LCS·Char 유사도 | ✅ ground_truth 제공 시 | ✅ ground_truth 제공 시 | ✅ run(ground_truth=...) 제공 시 자동 | ✅ set_ground_truth() 후 자동 |
| 3 | **Hallucination Detection**<br>규칙 기반 사실 일관성 검사 | ✅ tasks_output에서 자동 수집 | 🔶 on_retriever_end 콜백 시 (Retriever 미사용 시 수집 불가) | 🔶 ToolMessage 컨텍스트 자동 수집 | 🔶 도구 결과 컨텍스트 자동 수집 |
| 4 | **Response Quality (5-dim)**<br>relevance·completeness·accuracy·clarity·usefulness | ✅ question/response 제공 시 자동 연결 | ✅ question/response 제공 시 자동 연결 | ✅ question/response 제공 시 자동 연결 | ✅ question/response 제공 시 자동 연결 |
| 5 | **Latency**<br>p50·p95·p99·mean·SLA 준수율 | 🔶 전체 시간 ÷ 태스크 수 균등 분배 (추정) | ✅ 콜백 on_chain_end 실측 | ✅ 노드별 실측 + 총 시간 | 🔶 team.run() 총 시간 (도구 레벨 타이밍 추정) |
| 6 | **Token Economy**<br>입출력 비율·비용 추정·월간 예측 | ✗ SDK 미노출 (수동 설정 필요) | ✅ LLM 실제 응답 token_usage | 🔶 AIMessage.usage_metadata (LC LLM 시) | 🔶 tiktoken 우선, 한/영 휴리스틱 fallback |

### 🤖 Layer 2 — Agentic 지표 (5개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 7  | **Tool Call Efficiency**<br>효율성 점수·중복 호출·실패율 | 🔶 agents 속성에서 도구 추론 | ✅ on_agent_action/tool_end/tool_error 실측 | 🔶 ToolMessage 파싱 (LC LLM 시) | ✅ ToolCallRequestEvent/ToolCallExecutionEvent 기반 |
| 8  | **Retry & Error Recovery**<br>재시도율·첫 시도 성공률·수정 성공률 | 🔶 attempts=1 고정 | ✅ on_retry 콜백 자동, attempts=1+count | 🔶 attempts=1 고정 | 🔶 attempts=1 고정 |
| 9  | **Tool Selection Accuracy**<br>Precision·Recall·F1 (기대 vs 실제 도구) | ✅ expected_tools vs 실행 도구 F1 | ✅ expected_tools vs AgentAction F1 | ✅ expected_tools 제공 시 자동 (ToolMessage 기반) | ✅ ToolCallEvent 기반 자동 추적 |
| 10 | **Agent Coordination**<br>협업 점수·패턴(Hub/Chain/Mesh)·성공률 | ✅ Hierarchical/Sequential 패턴 추론 | ✗ 단일 에이전트 — 멀티 미지원 | ✅ 노드 전환 감지 → from/to 쌍 자동 기록 | ✅ on_messages() sender 추적 |
| 11 | **Workflow Execution**<br>단계 성공률·태스크 성공률·총 단계 수 | 🔶 태스크명 키워드 추론 (실행 상태 미확인) | 🔶 도구 호출 = 스텝 (실측 타이밍) | ✅ 노드 실행 = 스텝 (실측 타이밍) | 🔶 메시지 히스토리 기반 자동 추적 |

### 🛡 Layer 2 — Security 지표 (5개)

> `enable_security_metrics=True` 필요 (또는 `PerformanceMonitor.for_secure_agents()` 사용). 모든 프레임워크에서 수동 호출.
> 모니터 없이 단독 사용 시: `validate_input_security(text)` / `check_output_leakage(text)` (from `agent_evaluator.helpers.taskresult_helpers`)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 12 | **Input Sanitization**<br>SQL·Command·Path·XSS·Prompt Injection 탐지 | 🔧 `monitor.input_sanitizer.evaluate_input()` | 🔧 동일 | 🔧 동일 | 🔧 동일 |
| 13 | **Output Leakage**<br>API Key·Password·Credit Card·Email·File Path 유출 탐지 | 🔧 `monitor.output_leakage_detector.detect_leakage()` | 🔧 동일 | 🔧 동일 | 🔧 동일 |
| 14 | **Tool Authorization**<br>Whitelist/Blacklist · Privilege Level 검증 | 🔧 `monitor.tool_authorizer.track_tool_call()` | 🔧 동일 | 🔧 동일 | 🔧 동일 |
| 15 | **Privilege Escalation**<br>read→write→admin 권한 상승 체인 분석 | 🔧 `monitor.privilege_escalation_detector.analyze_privilege_chain()` | 🔧 동일 | 🔧 동일 | 🔧 동일 |
| 16 | **Tool Chain Attack**<br>data_exfil · lateral_movement · persistence · evasion | 🔧 `monitor.tool_chain_attack_detector.analyze_tool_chain()` | 🔧 동일 | 🔧 동일 | 🔧 동일 |

### 🧪 Layer 3 — Hybrid 지표 (9개)

> `pip install agent-evaluator[eval]` + `OPENAI_API_KEY` 필요
> 모든 프레임워크에서 `HybridPerformanceMonitor` 사용 시 동일하게 수집 가능

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 17 | **G-Eval (DeepEval)**<br>LLM 기반 사용자 정의 품질 기준 평가 | ✅ | ✅ | ✅ | ✅ |
| 18 | **Hallucination (DeepEval)**<br>의미론적 환각 탐지 — LLM 비교 판단 | ✅ retrieved_context 필요 | ✅ | ✅ | ✅ |
| 19 | **Toxicity (DeepEval)**<br>독성 콘텐츠 탐지 · 0=무독성 | ✅ | ✅ | ✅ | ✅ |
| 20 | **Bias (DeepEval)**<br>편향 탐지 · 0=무편향 | ✅ | ✅ | ✅ | ✅ |
| 21 | **Answer Relevancy (DeepEval)**<br>질문-답변 관련성 · LLM 판단 | ✅ | ✅ | ✅ | ✅ |
| 22 | **Faithfulness (Ragas)**<br>검색 문서 충실도 — RAG Generation 품질 | ✅ retrieved_context 필요 | ✅ | ✅ | ✅ |
| 23 | **Answer Relevancy (Ragas)**<br>RAG 답변 관련성 | ✅ retrieved_context 필요 | ✅ | ✅ | ✅ |
| 24 | **Context Precision (Ragas)**<br>검색 정밀도 | ✅ retrieved_context 필요 | ✅ | ✅ | ✅ |
| 25 | **Context Recall (Ragas)**<br>검색 재현율 | ✅ retrieved_context 필요 | ✅ | ✅ | ✅ |

---

## 토큰 측정 정확도 비교

| 프레임워크 | 측정 방식 | 정확도 | 비고 |
|-----------|----------|--------|------|
| 🟢 LangChain | LLM API 응답의 `llm_output["token_usage"]` | **✅ 실제값** | on_llm_end 콜백으로 실시간 수집 |
| 🟣 AutoGen   | tiktoken 우선 → 한/영 휴리스틱 fallback | **🔶 추정 (tiktoken 시 정확)** | tiktoken 설치 시 정확. 미설치 시 한국어 오차 있음 |
| 🔵 CrewAI    | 초기값 `{"input": 0, "output": 0}` | **✗ 미수집** | CrewAI SDK에서 토큰 미노출. `dataclasses.replace(task, tokens_used={...})` 로 수동 설정 |
| 🟠 LangGraph | `AIMessage.usage_metadata` (LC LLM 사용 시) | **🔶 부분 수집** | LangChain 통합 LLM 사용 시 자동 추출. 그 외는 0 |

> **⚠️ Token Economy 지표 활용 시 주의**
> CrewAI 사용 시 토큰 비용 계산이 0으로 보고됩니다. 정확한 비용 측정이 필요하면 LangChain을 사용하거나
> `task = dataclasses.replace(task, tokens_used={"input": N, "output": M, "total": N+M})` 으로 직접 설정하세요.
> LangGraph는 LangChain 통합 LLM 사용 시 자동 추출됩니다.

---

## 프레임워크별 빠른 시작

> **v0.6.3+ 권장 패턴:**
> - `create_taskresult()` 헬퍼로 TaskResult 생성 (자동 점수 계산)
> - 프레임워크 특화 필드는 `dataclasses.replace()` 로 추가 (frozen dataclass)
> - `PerformanceMonitor.for_rag_evaluation()` / `for_secure_agents()` 팩토리 사용

### 🔵 CrewAI

```python
import dataclasses
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.crewai_integration import (
    CrewAIEvaluator, create_evaluated_crew
)
from agent_evaluator.integrations.framework_integrations import (
    check_framework_availability, get_installation_instructions
)

# 프레임워크 가용성 확인
if not check_framework_availability("crewai").get("crewai"):
    print(get_installation_instructions("crewai"))

# 보안 지표 포함 모니터 (팩토리 사용)
monitor = PerformanceMonitor.for_secure_agents(
    output_dir="results/",
    enable_hallucination_detection=True,
)

# 팩토리 방식
crew = create_evaluated_crew(
    tasks=my_tasks,
    agents=my_agents,
    monitor=monitor,
)
result = crew.kickoff()

# 수동 방식: create_taskresult() + dataclasses.replace()
task = create_taskresult(
    task_id="crew_001",
    question=input_text,
    response=result.raw,
    ground_truth=expected_answer,
    execution_time=elapsed,
    task_type="qa",
)
task = dataclasses.replace(
    task,
    tokens_used={"input": N, "output": M, "total": N+M},  # 수동 설정
    framework="crewai",
)
monitor.record_task(task)
```

### 🟢 LangChain

```python
import dataclasses
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.langchain_integration import (
    LangChainEvaluator, AdvancedLangChainCallback,
    create_evaluated_langchain_agent,
)

# RAG 평가용 모니터 (팩토리 사용 — hallucination 기본 활성화)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# 콜백 방식 (실시간 토큰·도구 추적)
callback = AdvancedLangChainCallback(monitor=monitor, task_id="task_001")
response = agent.run(input_text, callbacks=[callback])

# 수동 방식: create_taskresult() + dataclasses.replace()
task = create_taskresult(
    task_id="lc_001",
    question=input_text,
    response=response,
    ground_truth=expected,
    execution_time=elapsed,
    task_type="qa",
)
task = dataclasses.replace(task, framework="langchain")
monitor.record_task(task)

# 팩토리 방식
agent = create_evaluated_langchain_agent(llm, tools, monitor=monitor)
```

### 🟠 LangGraph

```python
import dataclasses
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.langgraph_integration import (
    LangGraphEvaluator, create_evaluated_langgraph,
)

monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# 기존 컴파일 그래프 직접 래핑 (from_compiled 방식, v0.6.0+)
graph = create_evaluated_langgraph(
    my_compiled_graph,   # 컴파일된 그래프를 첫 번째 인자로 전달
    monitor=monitor,
    enable_layer2=True,  # 노드 래핑 활성화
)
# stream() 기반으로 노드별 실측 타이밍 + 노드 전환 자동 수집
result = graph.run(
    initial_state={"messages": [HumanMessage(content=query)]},
    ground_truth=expected_answer,
)
# LangChain 통합 LLM 사용 시 AIMessage.usage_metadata 토큰 자동 추출
# 그 외: dataclasses.replace(task, tokens_used={...}) 로 수동 설정
```

### 🟣 AutoGen

```python
import dataclasses
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.autogen_integration import (
    AutoGenEvaluator, create_evaluated_autogen_agent,
)

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

# async-first 재설계 (0.4+): on_messages() / team.run() 통합
evaluator = AutoGenEvaluator(agent=assistant, monitor=monitor)
evaluator.set_ground_truth(expected_answer)

# 멀티에이전트 협업 + 워크플로우 자동 추적
# → on_messages() sender 기반 에이전트 상호작용 기록
# → ToolCallRequestEvent/ToolCallExecutionEvent 기반 도구 추적 (v0.6.0+)
# Token Economy: tiktoken 설치 시 정확한 값, 미설치 시 휴리스틱 fallback
# 0.3.x: generate_reply 래핑 불가 → UserWarning 후 수동 record_task() 권고

# 동기 실행 래퍼 (async 환경이 아닐 때)
result = evaluator.run_sync(task_input)
```

### 🛡 보안 지표 추가 (모든 프레임워크 공통)

```python
# 방법 1: 팩토리 메서드 (권장)
monitor = PerformanceMonitor.for_secure_agents(
    security_config={
        "allowed_tools": ["web_search", "db_lookup"],
        "blocked_tools": ["rm_rf", "system_exec"],
    },
    output_dir="results/",
)

# 방법 2: 직접 초기화
monitor = PerformanceMonitor(enable_security_metrics=True, output_dir="results/")

# 프레임워크 통합 실행 후 별도 보안 트래커 호출
monitor.input_sanitizer.evaluate_input(task_id, user_input)
monitor.output_leakage_detector.detect_leakage(task_id, agent_output)
monitor.tool_authorizer.track_tool_call(task_id, tool_name, tool_args)
monitor.privilege_escalation_detector.analyze_privilege_chain(task_id, tool_calls)
monitor.tool_chain_attack_detector.analyze_tool_chain(task_id, tool_sequence)

# 방법 3: 모니터 없이 단독 사용 (v0.6.3+)
from agent_evaluator.helpers.taskresult_helpers import (
    validate_input_security, check_output_leakage
)
input_result  = validate_input_security(user_input)   # {"is_safe": bool, "threats": [...]}
output_result = check_output_leakage(agent_response)  # {"has_leakage": bool, "leaked_types": [...]}
```

### 📊 멀티턴 대화 평가 (v0.6.3+, 모든 프레임워크 공통)

```python
from agent_evaluator import ConversationSession, ConversationMetrics

session = ConversationSession(session_id="conv_001")
session.add_turn(user="파이썬 비동기 처리 방법은?", agent="asyncio를 사용합니다.")
session.add_turn(user="gather와 wait의 차이는?", agent="gather는 결과를 리스트로 반환...")

metrics: ConversationMetrics = session.compute_metrics()
# metrics.context_retention  — 맥락 유지율 (0–1)
# metrics.topic_coherence    — 주제 일관성 (0–1)
# metrics.progressive_depth  — 점진적 심화 (0–1)
# metrics.session_completion — 세션 완결성 (0–1)
# metrics.overall_score      — 종합 점수 (0–1)
# metrics.turn_count         — 총 턴 수
```

### 🔬 투명성 추적 (v0.6.3+)

```python
# enable_transparency=True 로 초기화 시 save_to_file() 호출 때 자동 생성:
# results/traces/     — 지표 계산 단계별 추적 (TCR·Accuracy·Latency 등)
# results/audit_logs/ — 파일 저장·리포트 생성 감사 로그
# results/annotations/— 수동 주석 (대시보드 UI 또는 직접 API 호출)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_transparency=True,
)
```

---

## 구현 참고사항 및 제한

### ⚠️ 프레임워크별 주요 제한사항

| 프레임워크 | 제한 항목 | 원인 | 권장 대안 |
|-----------|----------|------|----------|
| 🔵 CrewAI | 토큰 수 0으로 고정 | CrewAI SDK가 토큰 정보를 반환하지 않음 | `dataclasses.replace(task, tokens_used={...})` 수동 설정 |
| 🔵 CrewAI | 도구 실행 시간 추정값 | 내부 도구 실행 타이밍 접근 불가 | 허용 오차 내 사용 가능 |
| 🟢 LangChain | Agent Coordination 미지원 | 단일 에이전트 아키텍처 | CrewAI 또는 AutoGen으로 교체 |
| 🟠 LangGraph | Token Economy 부분 수집 | LangChain LLM 미사용 시 토큰 접근 불가 | LangChain 통합 LLM 사용 또는 수동 설정 |
| 🟠 LangGraph | 도구 추적 부분 지원 | ToolMessage 기반 — LangChain LLM 통합 필요 | LangChain 통합 LLM 사용 시 자동 추출 |
| 🟣 AutoGen | 0.3.x generate_reply 미지원 | 0.4+ async API 전환으로 generate_reply 래핑 불가 | UserWarning 안내, 수동 `monitor.record_task()` 사용 또는 0.4+ async API 사용 |
| CrewAI / LangGraph | Retry 부분 추적 (attempts=1 고정) | 재시도 카운트가 프레임워크 내부에 은닉 | `retry_tracker.track_attempts()` 수동 호출 (\* LangChain은 on_retry 자동 추적) |
| 🟣 AutoGen | Retry 부분 추적 (is_error=True 도구 실패 감지) | async API 전환 후 재시도 카운트 미노출 | `retry_tracker.track_attempts()` 수동 호출 |

### ⚠️ `AgentCoordinationTracker.track_interaction()` interaction_type

허용 canonical 타입: `delegation`, `communication`, `collaboration`

v0.6.3+에서 다음 별칭이 경고 없이 자동 정규화됩니다:

| 입력값 | 정규화 결과 |
|--------|------------|
| `task_delegation`, `handoff` | → `delegation` |
| `result_sharing`, `feedback`, `broadcast` | → `communication` |
| `coordination` | → `collaboration` |

그 외 알 수 없는 타입은 `delegation`으로 fallback 정규화되며 `WARNING` 로그가 출력됩니다.

### 🎯 프레임워크 선택 가이드

| 사용 목적 | 권장 프레임워크 | 이유 |
|----------|--------------|------|
| 정확한 비용 추적 | 🟢 **LangChain** | 유일하게 실제 토큰 수를 자동 수집 |
| 멀티에이전트 협업 분석 | 🔵 **CrewAI** | Agent Coordination + Tool Selection 자동 추적 |
| 복잡한 상태 머신 / DAG 워크플로우 | 🟠 **LangGraph** | 노드별 실측 타이밍 + Workflow Execution 자동 추적 |
| 대화형 에이전트 간 상호작용 분석 | 🟣 **AutoGen** | 에이전트 메시지 교환 자동 추적 (async-first; `run_sync()` 동기 래퍼 제공) |
| 전체 25개 지표 최대 커버리지 | 🟢 **LangChain** / 🟠 **LangGraph** | 공동 최고 ~82% (~21개) — LangChain: Token Economy ✅ 실제값 + Retry ✅ 자동, LangGraph: Latency ✅ 노드별 실측 |
| RAG 평가 최적화 | 🟢 **LangChain** + Layer 3 | `PerformanceMonitor.for_rag_evaluation()` + DeepEval/Ragas 통합 |
| 보안 중심 평가 | 전 프레임워크 | `PerformanceMonitor.for_secure_agents()` — 5개 보안 트래커 일괄 활성화 |

---

*Updated: 2026-03-30 (v0.6.3 — SDK 안정화 · 팩토리 API · interaction_type 별칭 · ConversationSession) | MIT License | Python 3.8+*
