# 통합 가이드

데코레이터 API 전체 레퍼런스 · 24개 프레임워크 통합 · 타 평가 도구 비교

**v0.9.10 | Python 3.8+**

---

## 목차

1. [3가지 데코레이터 방식](#1-3가지-데코레이터-방식)
2. [@agent_eval — 단일 호출](#2-agent_eval--단일-호출)
3. [@batch_eval — 대량 처리](#3-batch_eval--대량-처리)
4. [@conversation_eval — 멀티턴 대화](#4-conversation_eval--멀티턴-대화)
5. [QuickEval — 편의용 팩토리](#5-quickeval--편의용-팩토리)
6. [평가 결과 출력 시나리오](#6-평가-결과-출력-시나리오)
7. [전체 파라미터 레퍼런스](#7-전체-파라미터-레퍼런스)
8. [파라미터 → 지표 활성화 맵](#8-파라미터--지표-활성화-맵)
9. [지표 × 데코레이터 지원 매트릭스](#9-지표--데코레이터-지원-매트릭스)
10. [데이터 소스 우선순위](#10-데이터-소스-우선순위)
11. [리포트에서 지표 읽기](#11-리포트에서-지표-읽기)
12. [프레임워크 통합](#12-프레임워크-통합)
13. [지표 지원 매트릭스 (프레임워크별)](#13-지표-지원-매트릭스-프레임워크별)
14. [타 평가 도구와의 비교](#14-타-평가-도구와의-비교)

---

## 1. 3가지 데코레이터 방식

SDK의 표준 인터페이스는 용도에 따라 통합된 3개의 데코레이터입니다.

```
┌──────────────────┬──────────────────────────────────┬─────────────────────────────┐
│ 데코레이터        │ 용도                              │ 코드 한 줄                   │
├──────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ @agent_eval      │ 단일 호출 (Single-turn)            │ @agent_eval(monitor)         │
│ @batch_eval      │ 리스트 기반 대량 처리 (Batch)       │ @batch_eval(monitor)         │
│ @conversation_eval│ 멀티턴 대화 세션 (Multi-turn)      │ @conversation_eval(monitor)  │
└──────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

> `QuickEval`(`eval = QuickEval()`)은 위 데코레이터들을 더 짧게 설정하기 위한 **팩토리(Factory) 도구**입니다.

---

## 2. @agent_eval — 단일 호출

가장 범용적인 방식입니다. 동기(`def`) 및 비동기(`async def`) 함수를 모두 자동으로 감지하여 처리합니다.

### 기본 사용법

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### RAG + 할루시네이션 모드

```python
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
```

### LLM Judge + Faithfulness

`rag_mode=True`와 `llm_judge=LLMJudgeConfig()`를 함께 쓰면 LLMJudge가 `faithfulness` 차원을 자동으로 추가합니다.
이는 Ragas `faithfulness` 지표의 **네이티브 대체** 방식으로, `[eval]` extras 설치 없이 동작합니다.

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),  # faithfulness 차원 자동 추가
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
```

### G-Eval 커스텀 기준 (`judge_criteria`)

서비스 특화 평가 기준을 `judge_criteria` 리스트로 정의합니다. DeepEval의 G-Eval을 네이티브로 대체합니다.

```python
@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6", criteria=["professionalism", "empathy", "clarity"]),
)
def customer_service_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# 결과: task.extra["llm_judge"]["criteria_scores"]
# → {"professionalism": 4.0, "empathy": 4.5, "clarity": 4.8}
```

---

## 3. @batch_eval — 대량 처리

대량의 데이터를 한 번에 평가할 때 사용하며, 병렬 실행(`concurrency=N`)을 지원합니다.

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa", concurrency=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

---

## 4. @conversation_eval — 멀티턴 대화

`session_id`를 기반으로 대화 맥락을 누적합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

chat_agent("안녕하세요", sid="user_1")
chat_agent("날씨 알려줘", sid="user_1")
flush_conversation("user_1")   # ConversationMetrics 계산 후 저장

# ConversationMetrics 8개 출력 필드:
# turn_count, overall_score, context_retention, topic_coherence,
# progressive_depth, session_completion, avg_turn_latency, turn_scores
```

---

## 5. QuickEval — 편의용 팩토리

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                   # task_type="qa"
def my_agent(q, ground_truth=""): ...

@eval.rag                  # task_type="information_retrieval" + hallucination
def rag_agent(q, context="", ground_truth=""): ...

eval.save()                # quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)   # CI/CD 게이팅

# 용도별 팩토리
eval = QuickEval.for_rag("results/")
eval = QuickEval.for_security("results/")
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 단축 데코레이터: qa, tool_use, rag, code, reasoning, planning,
#                  data_analysis, creative, multi_agent, secure, streaming
```

---

## 6. 평가 결과 출력 시나리오

### 시나리오 1 — 터미널 출력

```python
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

report = monitor.generate_report()
print(report.to_json(indent=2))
```

### 시나리오 2 — FastAPI 대시보드

```python
monitor.save_to_file("eval")     # results/eval.json + .html 생성
```

```bash
agent-eval dashboard results/ --watch    # http://localhost:8765
```

### 시나리오 3 — Phoenix OTEL 실시간 모니터링

`setup_otel()`을 **PerformanceMonitor 생성 전**에 호출해야 합니다.

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 7. 전체 파라미터 레퍼런스

### `@agent_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `task_type` | str | `"qa"` | qa / tool_use / information_retrieval / code_generation / reasoning / planning / data_analysis / creative / coding / multi_agent |
| `question_arg` | str | `"question"` | 질문이 담긴 함수 인자 이름 |
| `ground_truth_arg` | str | `"ground_truth"` | 정답이 담긴 함수 인자 이름 |
| `context_arg` | str\|None | `None` | RAG 컨텍스트 인자 이름 (`rag_mode=True` 시 자동 `"context"`) |
| `expected_tools_arg` | str\|None | `None` | Tool Selection F1 평가용 기대 도구 리스트 인자 이름 |
| `task_id_prefix` | str | `"task"` | 자동 생성 task_id 접두사 |
| `task_id_fn` | callable\|None | `None` | task_id 생성 함수 `(args, kwargs) → str` |
| `framework` | str | `"native"` | 프레임워크 어댑터 지정 (24개 지원) |
| `model_name` | str | `""` | 토큰 비용 계산용 모델명 |
| `score_fn` | callable\|None | `None` | 커스텀 accuracy_score 함수 `(response, ground_truth) → float` |
| `completion_fn` | callable\|None | `None` | 커스텀 completion_score 함수 `(response, ...) → float` |
| `custom_parser` | callable\|None | `None` | 커스텀 메타데이터 파서 `(raw_result) → EvalMetadata` |
| `sample_rate` | float | `1.0` | 기록 샘플링 비율 (0.0–1.0) |
| `timeout` | float\|None | `None` | 타임아웃(초), 초과 시 TimeoutError |
| `enabled` | bool | `True` | False 이면 데코레이터 완전 비활성화 |
| `retry` | RetryConfig\|None | `None` | 재시도 설정 (`RetryConfig(max=N, delay=X, backoff=Y)`) |
| `on_record` | callable\|None | `None` | 기록 완료 후 콜백 `(TaskResult)` |
| `on_error` | callable\|None | `None` | 오류 시 콜백 `(exc, TaskResult)` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `flush_every` | int\|None | `None` | N회마다 save_to_file() 자동 호출 |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 (production/development/testing/canary) |
| `enable_hallucination_detection` | bool | `False` | HallucinationDetector 임시 활성 |
| `rag_mode` | bool | `False` | context_arg="context" + hallucination + task_type="information_retrieval" 자동 |
| `security` | SecurityConfig\|None | `None` | 보안 5개 트래커 임시 활성 (`SecurityConfig(allowed_tools=[...])` 로 화이트리스트 설정) |
| `llm_judge` | LLMJudgeConfig\|None | `None` | LLMJudge 설정 (`LLMJudgeConfig(model=..., criteria=[...])`) |
| `enable_anomaly_detection` | bool | `False` | AnomalyDetector 임시 활성 |

### `@batch_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `task_type` | str | `"qa"` | 태스크 유형 |
| `questions_arg` | str | `"questions"` | 질문 리스트 인자 이름 |
| `ground_truths_arg` | str | `"ground_truths"` | 정답 리스트 인자 이름 |
| `contexts_arg` | str\|None | `None` | RAG 컨텍스트 리스트 인자 이름 |
| `expected_tools_arg` | str\|None | `None` | 기대 도구 리스트 인자 이름 |
| `framework` | str | `"native"` | 프레임워크 어댑터 |
| `score_fn` | callable\|None | `None` | 커스텀 accuracy_score 함수 |
| `on_record` | callable\|None | `None` | 건별 기록 완료 콜백 |
| `on_batch_complete` | callable\|None | `None` | 배치 전체 완료 콜백 |
| `on_batch_progress` | callable\|None | `None` | 진행 상황 콜백 `(done, total)` |
| `on_item_error` | callable\|None | `None` | 아이템 오류 처리 `(exc, idx, question) → str` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `flush_every` | int | `0` | N건마다 자동 저장 (0=비활성) |
| `sample_rate` | float | `1.0` | 샘플링 비율 |
| `timeout` | float\|None | `None` | 전체 배치 타임아웃(초) |
| `item_timeout` | float\|None | `None` | 건별 타임아웃(초) |
| `enabled` | bool | `True` | 비활성화 플래그 |
| `concurrency` | int | `0` | 동시 실행 수 (0=순차 처리, N=최대 N개 병렬) |
| `return_format` | str | `"list"` | 반환 형식: "list" / "tuple" / "dataframe" |
| `streaming_mode` | bool | `False` | 스트리밍 모드 (TTFT 자동 측정) |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 |

### `@conversation_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `session_id_arg` | str | `"session_id"` | 세션 ID 인자 이름 |
| `user_arg` | str | `"question"` | 사용자 입력 인자 이름 |
| `ground_truth_arg` | str | `"ground_truth"` | 정답 인자 이름 |
| `max_turns` | int\|None | `None` | 최대 턴 수 초과 시 자동 flush |
| `max_session_seconds` | float\|None | `None` | 세션 타임아웃(초) |
| `flush_on_error` | bool | `True` | 오류 시 세션 자동 flush |
| `max_turns_exceeded_action` | str | `"flush"` | "flush" / "warn" / "error" |
| `sample_rate` | float | `1.0` | 샘플링 비율 |
| `on_flush` | callable\|None | `None` | 세션 flush 완료 콜백 `(ConversationMetrics)` |
| `on_turn` | callable\|None | `None` | 턴 완료 콜백 `(user, response, metadata)` |
| `session_score_fn` | callable\|None | `None` | 커스텀 세션 점수 `(ConversationMetrics) → float` |
| `turn_score_fn` | callable\|None | `None` | 커스텀 턴 점수 `(user, response, metadata) → float` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `flush_every` | int | `0` | N턴마다 자동 저장 |
| `enabled` | bool | `True` | 비활성화 플래그 |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 |

---

## 8. 파라미터 → 지표 활성화 맵

| 파라미터 | 활성화되는 지표/트래커 | 조건 |
|---|---|---|
| `ground_truth_arg` | Accuracy | 인자 이름 일치 시 항상 |
| `rag_mode=True` | Hallucination Rate + context_arg="context" 자동 설정 | context 인자 존재 시 |
| `expected_tools_arg` | Tool Selection F1 (Precision/Recall/F1) | tool_calls 동시 존재 시 |
| `framework="langchain"` | Tool Call Efficiency, Workflow Execution | LangChain AgentExecutor 응답 |
| `framework="langgraph"` | Workflow Execution, state_transitions | LangGraph 응답 |
| `framework="crewai"` | Tool Call Efficiency, Agent Coordination | CrewAI 응답 |
| `framework="autogen"` | Agent Coordination | AutoGen ChatResult 파싱 |
| `framework="openai"` | Token Economy (정확) | OpenAI ChatCompletion |
| `framework="anthropic"` | Token Economy + 캐시 토큰 | Anthropic Message |
| `security=SecurityConfig()` | Input Sanitization, Output Leakage, Tool Authorization, Privilege Escalation, Tool Chain Attack (5개) | 임시 활성 (finally 복원) |
| `llm_judge=LLMJudgeConfig()` | LLMJudge (completeness/relevance/factual_consistency/toxicity/bias) | API 키 필요 |
| `rag_mode=True` + `llm_judge=LLMJudgeConfig()` | + Faithfulness | context 존재 시 자동 추가 |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | + G-Eval 커스텀 기준 점수 | llm_judge 설정 내 criteria 지정 |
| `retry=RetryConfig(max=N)` (N>1) | Retry & Error Recovery | 실제 재시도 발생 시 |
| `sample_rate=0.1` | 모든 지표 (10% 샘플만 기록) | 샘플 미해당 시 함수는 정상 실행 |
| `enable_anomaly_detection=True` | Anomaly Detection | save_to_file() 시 자동 실행 |
| `preset="production"` | sample_rate=0.1 + flush_every=50 + enable_anomaly_detection=True | 프리셋 이름 일치 시 |

---

## 9. 지표 × 데코레이터 지원 매트릭스

| 지표 | `@agent_eval` | `@batch_eval` | `@conversation_eval` | 활성 방법 |
|---|:---:|:---:|:---:|---|
| **Layer 1 — 기반 지표** | | | | |
| TCR | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 |
| Accuracy | ✅ 자동 | ✅ 자동 | ✅ 자동 | `ground_truth_arg` 존재 시 |
| Response Quality (5차원) | ✅ 자동 | ✅ 자동 | ✅ 자동 | response + question 존재 시 |
| Latency (p50/p95/p99) | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 (실행 시간 자동 측정) |
| TTFT | ✅ generator | ✅ `streaming_mode=True` | ❌ | generator 리턴 또는 스트리밍 모드 |
| Token Economy | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata |
| Hallucination Rate | ✅ `rag_mode=True` | ✅ `context_arg` 지정 | ❌ | context 인자 + hallucination 활성 |
| **Layer 2 — Agentic 지표** | | | | |
| Tool Call Efficiency | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata.tool_calls |
| Retry & Error Recovery | ✅ `retry=RetryConfig(max=N)` | ❌ | ❌ | `RetryConfig(max>1)` + 실제 재시도 발생 |
| Tool Selection F1 | ✅ `expected_tools_arg` | ✅ `expected_tools_arg` | ❌ | expected_tools + tool_calls 동시 존재 |
| Agent Coordination | ✅ `framework="crewai/autogen"` | ❌ | ❌ | CrewAI/AutoGen 어댑터 |
| Workflow Execution | ✅ `framework="langchain/langgraph"` | ❌ | ❌ | LangChain/LangGraph 어댑터 |
| **Layer 2 — Security 지표** | | | | |
| Input Sanitization | ✅ `security=SecurityConfig()` | ❌ | ❌ | SecurityConfig 임시 활성 |
| Output Leakage | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Authorization | ✅ `security=SecurityConfig()` + `allowed_tools` | ❌ | ❌ | 동일 + 화이트리스트 |
| Privilege Escalation | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Chain Attack | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| **Layer 3 / LLM Judge** | | | | |
| LLM Judge (5차원) | ✅ `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | 기본 설치에 포함 (API 키 필요) |
| Faithfulness (RAG) | ✅ `rag_mode` + `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | context 존재 시 자동 추가 |
| G-Eval 커스텀 기준 | ✅ `llm_judge=LLMJudgeConfig(criteria=[...])` | ❌ | ❌ | llm_judge 설정 내 criteria 지정 |
| **대화 지표 (conversation 전용)** | | | | |
| Context Retention | ❌ | ❌ | ✅ 자동 | flush 시 compute_metrics() |
| Topic Coherence | ❌ | ❌ | ✅ 자동 | 동일 |
| Progressive Depth | ❌ | ❌ | ✅ 자동 | 동일 |
| Session Completion | ❌ | ❌ | ✅ 자동 | 동일 |

---

## 10. 데이터 소스 우선순위

```
1순위: return (EvalMetadata, result)   — 명시적 주입 (최고 우선순위)
2순위: get_eval_ctx()                  — ContextVar 주입 (eval_context 패턴)
3순위: 프레임워크 어댑터               — 리턴값 자동 파싱 (24개 프레임워크)
4순위: _auto_detect_framework()       — 리턴값 타입 기반 자동 감지
5순위: 인자 이름 기반 추출             — question_arg / ground_truth_arg / context_arg 등
```

```python
# 1순위: EvalMetadata 명시적 주입
from agent_evaluator import EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = llm_with_tools.invoke(question)
    return EvalMetadata(
        accuracy_score=0.92,
        tokens_used={"input": 150, "output": 80},
        tool_calls=[{"tool_name": "search", "duration": 0.3, "success": True}],
    ), response.content

# 3순위: 프레임워크 어댑터 자동 수집
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
    # tool_calls, chain_steps, tokens_used 자동 추출
```

---

## 11. 리포트에서 지표 읽기

```python
report = monitor.generate_report()
d = report.to_dict()

# Layer 1
d["tcr_data"]["success_rate"]              # float (0–1)
d["accuracy_data"]["overall_accuracy"]     # float (0–100)
d["hallucination_data"]["overall_rate"]    # float (0–1)
d["quality_data"]["avg_total_score"]       # float (0–5)
d["latency_data"]["p95"]                   # float (초)
d["token_data"]["estimated_cost"]          # float ($)

# Layer 2
d["tool_efficiency"]                       # float (0–100)
d["tool_selection_accuracy"]               # float (0–100)
d["coordination_score"]                    # float (0–10)
d["workflow_execution"]["step_success_rate"] # float (0–100)

# Security
d["security_metrics"]["input_security"]["threat_rate"]           # float (0–100)
d["security_metrics"]["output_leakage"]["leakage_rate"]          # float (0–100)
d["security_metrics"]["authorization"]["compliance_rate"]        # float (0–100)
d["security_metrics"]["privilege_escalation"]["escalation_rate"] # float (0–100)
d["security_metrics"]["attack_detection"]["detection_rate"]      # float (0–100)

# LLM Judge
task_dict["extra"]["llm_judge"]["completeness"]         # float (0–5)
task_dict["extra"]["llm_judge"]["faithfulness"]         # float (0–5, RAG 시)
task_dict["extra"]["llm_judge"]["criteria_scores"]      # dict

# Conversation (flush 후)
session_dict["context_retention"]   # float (0–1)
session_dict["overall_score"]       # float (0–1)
```

---

## 12. 프레임워크 통합

> **핵심 패턴**: `@agent_eval(monitor, framework="프레임워크명")` — 응답에서 token/tool 메타데이터 자동 추출
> 24개 프레임워크: `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`,
> `anthropic`, `openai`, `gemini`, `llamaindex`, `haystack`, `vertexai`, `ollama`, `cohere`,
> `groq`, `mistral`, `bedrock`, `smolagents`, `semantic_kernel`, `vllm`, `huggingface`,
> `openai_agents`, `google_adk`, `claude_agent_sdk` (공식 에이전트 프레임워크 SDK — `framework=` 명시 필요, 자동 감지 미지원)

### 4개 주요 프레임워크 커버리지 요약

| 프레임워크 | 토큰 정확도 | 멀티에이전트 | Native 커버리지 | 추천 용도 |
|-----------|------------|------------|----------------|---------|
| 🟢 **LangChain** | ✅ 실제값 | ✗ 단일 | ~82% (~21개) | RAG, 정밀 비용 추적 |
| 🟠 **LangGraph** | 🔶 부분 | 🔶 노드 전환 | ~82% (~21개) | DAG · 상태 머신 |
| 🔵 **CrewAI** | ✗ 0 고정 | ✅ | ~78% (~20개) | 역할 기반 멀티에이전트 |
| 🟣 **AutoGen** | 🔶 tiktoken | ✅ | ~80% (~20개) | 대화형 멀티에이전트 |

### 🟢 LangChain

```python
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})  # token_usage 자동 추출
```

**자동 추출**: 실제 토큰 수 (`llm_output.token_usage`), 도구 호출 (`AgentAction`), 재시도 (`on_retry`)

### 🟠 LangGraph

```python
from agent_evaluator.integrations import langgraph_eval

@langgraph_eval(monitor, task_type="qa")
def lg_agent(question: str, ground_truth: str = "") -> str:
    result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content
```

**자동 추출**: 노드별 실측 타이밍, 노드 전환 (AgentCoordination), 토큰 (`AIMessage.usage_metadata`)

### 🔵 CrewAI

```python
from agent_evaluator.integrations import crewai_eval

@crewai_eval(monitor, task_type="qa")
def run_crew(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return result.raw
```

**주의**: 토큰 수 0 고정 — `dataclasses.replace(task, tokens_used={...})`로 수동 설정

### 🟣 AutoGen

```python
from agent_evaluator.integrations import autogen_eval

@autogen_eval(monitor, task_type="qa")
async def run_autogen(question: str, ground_truth: str = "") -> str:
    result = await team.run(task=question)
    return result.messages[-1].content
```

**자동 추출**: 에이전트 메시지 교환 (AgentCoordination), 도구 호출 (ToolCallEvent), 토큰 (tiktoken)

### 보안 지표 추가 (공통)

```python
# 방법 1: SecurityConfig 데코레이터 (권장)
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 방법 2: 팩토리 메서드 (모니터 전역 영구 활성)
monitor = PerformanceMonitor.for_secure_agents(
    security_config={
        "allowed_tools": ["web_search", "db_lookup"],
        "restricted_tools": ["rm_rf", "system_exec"],
    },
    output_dir="results/",
)
```

### 멀티턴 대화 평가 (공통)

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=10,
    on_flush=lambda metrics, sid: print(f"세션 {sid}: {metrics.overall_score:.2f}")
)
def chatbot_agent(user_message, sid="default"):
    return response

chatbot_agent("안녕하세요", sid="user_123")
flush_conversation("user_123")
```

---

## 13. 지표 지원 매트릭스 (프레임워크별)

### Foundation 지표 (6개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 1 | **TCR** | ✅ 예외 기반 | ✅ 콜백 기반 | ✅ 노드 오류 기반 | ✅ 예외 기반 |
| 2 | **Accuracy** | ✅ | ✅ | ✅ | ✅ |
| 3 | **Hallucination** | ✅ tasks_output | 🔶 Retriever | 🔶 ToolMessage | 🔶 도구 결과 |
| 4 | **Response Quality** | ✅ | ✅ | ✅ | ✅ |
| 5 | **Latency** | 🔶 균등 분배 | ✅ on_chain_end | ✅ 노드별 실측 | 🔶 총 시간 |
| 6 | **Token Economy** | ✗ 0 고정 | ✅ 실제 token_usage | 🔶 AIMessage | 🔶 tiktoken |

### Agentic 지표 (5개)

| # | 지표 | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|------|-----------|-------------|-------------|----------|
| 7 | **Tool Call Efficiency** | 🔶 추론 | ✅ on_agent_action | 🔶 ToolMessage | ✅ ToolCallEvent |
| 8 | **Retry & Recovery** | 🔶 attempts=1 | ✅ on_retry | 🔶 attempts=1 | 🔶 attempts=1 |
| 9 | **Tool Selection F1** | ✅ | ✅ | ✅ | ✅ |
| 10 | **Agent Coordination** | ✅ Hierarchical | ✗ 단일 | ✅ 노드 전환 | ✅ sender |
| 11 | **Workflow Execution** | 🔶 키워드 추론 | 🔶 도구=스텝 | ✅ 노드=스텝 | 🔶 메시지 히스토리 |

**범례**: ✅ 자동 지원 | 🔶 부분/추정 | ✗ 미지원

### 제한사항 요약

| 프레임워크 | 항목 | 권장 대안 |
|-----------|------|----------|
| 🔵 CrewAI | 토큰 수 0 고정 | `dataclasses.replace(task, tokens_used={...})` |
| 🟢 LangChain | Agent Coordination 미지원 | CrewAI/AutoGen으로 교체 |
| 🟣 AutoGen | 0.3.x 지원 제한 | 0.4+ async API 또는 수동 `record_task()` |

---

## 14. 타 평가 도구와의 비교

### 주요 평가 도구 한눈에 보기

| 도구 | 유형 | Agentic 전용 지표 | 보안 지표 | LLM 없이 계산 | 대시보드 | 비용 |
|------|------|-----------------|---------|--------------|---------|------|
| **LangSmith** | SaaS | Multi-Turn Goal, Trajectory | ❌ | ❌ | SaaS | $39/월~ |
| **Ragas** | OSS | ToolCallAccuracy, AgentGoalAccuracy | ❌ | ❌ | 외부 연동 | 무료 |
| **DeepEval** | OSS+SaaS | TaskCompletion, ToolCorrectness | 일부(Red-team) | 일부 | Confident AI | $49/월~ |
| **Arize Phoenix** | OSS+Cloud | FunctionCalling, Planning | ❌ | ❌ | 로컬/Cloud | 무료~ |
| **W&B Weave** | SaaS | Multi-agent spans, A2A | Guardrails | 일부 | SaaS | $50/월/좌석~ |
| **Agent Evaluator** | OSS SDK | **11종** | **5종 전용** | **✅ 전부** | **로컬 무료** | **$0** |

### Agentic 지표 상세 비교

| 지표 | LangSmith | Ragas | DeepEval | Phoenix | **Agent Evaluator** |
|-----|:---------:|:-----:|:--------:|:-------:|:-------------------:|
| Tool 선택 정확도 (F1) | ❌ | ✅ | ✅ | ❌ | ✅ `ToolSelectionTracker` |
| Tool 효율성 / 불필요 호출 | ❌ | ❌ | ❌ | ❌ | ✅ `ToolCallAnalyzer` |
| 재시도 / 자기수정 패턴 | ❌ | ❌ | ❌ | ❌ | ✅ `RetryCorrectionTracker` |
| 멀티에이전트 협업 품질 | ❌ | ❌ | ❌ | ❌ | ✅ `AgentCoordinationTracker` |
| 워크플로우 퍼널 / 분기 | ✅ (LangGraph) | ❌ | ❌ | 부분 | ✅ `WorkflowExecutionTracker` |
| 프롬프트 인젝션 탐지 | ❌ | ❌ | ⚠️ Red-team | ❌ | ✅ `InputSanitizationTracker` |
| 출력 정보 유출 탐지 | ❌ | ❌ | ❌ | ❌ | ✅ `OutputLeakageDetector` |
| 권한 상승 탐지 | ❌ | ❌ | ❌ | ❌ | ✅ `PrivilegeEscalationDetector` |

### 선택 가이드

| 상황 | 추천 도구 |
|------|---------|
| LangChain/LangGraph 트레이싱만 필요 | **LangSmith** |
| RAG faithfulness/recall 정밀 측정 | **Ragas** |
| CI/CD에서 LLM 단위 테스트 | **DeepEval** |
| OTEL 기반 인프라 + 로컬 셀프호스트 | **Arize Phoenix** |
| 에이전트 보안 검증 (프롬프트 인젝션, 권한 상승) | **Agent Evaluator** |
| Agentic 행동 분석 (tool F1, retry, 멀티에이전트) | **Agent Evaluator** |
| 추가 API 비용 없이 Native 지표 전체 측정 | **Agent Evaluator** |

---

| 목적 | 문서 |
|------|------|
| 설치 · 기본 사용법 | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| 58개 지표 상세 | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| 골든 데이터셋 · 한국어 RAG | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| 품질 임계값 · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| 전체 API 레퍼런스 | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
