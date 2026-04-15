# 데코레이터 가이드

에이전트 코드에 평가를 적용하는 실전 개발자 레퍼런스

**Version**: 0.8.1  
**최종 업데이트**: 2026-04-15

---

## 목차

1. [3가지 데코레이터 방식 한눈에 보기](#1-3가지-데코레이터-방식-한눈에-보기)
2. [방식 1 — `@agent_eval`](#2-방식-1--agent_eval)
3. [방식 2 — `@batch_eval`](#3-방식-2--batch_eval)
4. [방식 3 — `@conversation_eval`](#4-방식-3--conversation_eval)
5. [QuickEval — 편의용 팩토리](#5-quickeval--편의용-팩토리)
6. [평가 결과 출력 시나리오](#6-평가-결과-출력-시나리오)
7. [전체 파라미터 레퍼런스](#7-전체-파라미터-레퍼런스)
8. [파라미터 → 지표 활성화 맵](#8-파라미터--지표-활성화-맵)
9. [지표 × 데코레이터 지원 매트릭스](#9-지표--데코레이터-지원-매트릭스)
10. [데이터 소스 우선순위](#10-데이터-소스-우선순위)
11. [리포트에서 지표 읽기](#11-리포트에서-지표-읽기)

---

## 1. 3가지 핵심 데코레이터 방식 한눈에 보기

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

> **Note**: `QuickEval`(`eval = QuickEval()`)은 위 데코레이터들을 더 짧게 설정하기 위한 **팩토리(Factory) 도구**입니다.

---

## 2. 방식 1 — `@agent_eval` (표준)

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

### LLM Judge + Faithfulness (v0.7.6+)

`rag_mode=True`와 `llm_judge=LLMJudgeConfig()`를 함께 쓰면 LLMJudge가 `faithfulness` 차원을 자동으로 추가합니다.  
이는 Ragas `faithfulness` 지표의 **네이티브 대체** 방식으로, `[eval]` extras 설치 없이 동작합니다.

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,          # context_arg="context" + hallucination 활성
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),  # faithfulness 차원 자동 추가
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})

# 결과: task.extra["llm_judge"]["faithfulness"] 자동 기록
```

### G-Eval 커스텀 기준 (`judge_criteria`, v0.7.6+)

서비스 특화 평가 기준을 `judge_criteria` 리스트로 정의합니다. DeepEval의 G-Eval을 네이티브로 대체합니다.

```python
@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6", criteria=["professionalism", "empathy", "clarity"]),  # 커스텀 평가 차원
)
def customer_service_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 결과: task.extra["llm_judge"]["criteria_scores"]
# → {"professionalism": 4.0, "empathy": 4.5, "clarity": 4.8}
# → "criteria_overall": 4.43 (평균)
```

**`judge_criteria` 동작 규칙**
- 기준 이름 → 소문자 + 공백/하이픈 → 언더스코어로 정규화 (`"Code Quality"` → `"code_quality"`)
- 기존 5개 차원(completeness, relevance, factual_consistency, toxicity, bias)에 **추가**됨
- `PerformanceMonitor(judge_criteria=[...])` 또는 `@agent_eval(..., llm_judge=LLMJudgeConfig(criteria=[...]))` 두 가지 설정 지원

---

## 3. 방식 2 — `@batch_eval` (Batch 처리)

대량의 데이터를 한 번에 평가할 때 사용하며, 병렬 실행(`concurrent=True`)을 지원합니다.

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa", concurrent=True, max_concurrent=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

---

## 4. 방식 3 — `@conversation_eval` (멀티턴 대화)

v0.7.3부터 수동 세션 관리를 대체하는 표준 방식입니다. `session_id`를 기반으로 대화 맥락을 누적합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

# 동일 sid 호출 시 턴 자동 누적
chat_agent("안녕하세요", sid="user_1")
chat_agent("날씨 알려줘", sid="user_1")

# 명시적 종료 — ConversationMetrics 계산 후 저장
flush_conversation("user_1")

# ConversationMetrics 8개 출력 필드:
# {
#   "turn_count": 2,              # 총 대화 턴 수
#   "overall_score": 0.85,        # 종합 점수 (0~1)
#   "context_retention": 0.90,    # 이전 대화 기억 유지율 (0~1)
#   "topic_coherence": 0.88,      # 주제 일관성 (0~1)
#   "progressive_depth": 0.72,    # 대화 깊이 향상도 (0~1)
#   "session_completion": 0.95,   # 세션 목표 달성률 (0~1)
#   "avg_turn_latency": 1.23,     # 평균 응답 지연 시간 (초)
#   "turn_scores": {0: 0.9, 1: 0.8}  # 턴별 개별 점수
# }
```

---

## 5. QuickEval — 편의용 팩토리

데코레이터 설정을 더 간결하게 하고 싶을 때 사용합니다.

```python
from agent_evaluator import QuickEval
eval = QuickEval("results/")

@eval.qa  # 내부적으로 @agent_eval(monitor, task_type="qa") 호출
def my_agent(q): ...
```

---

## 6. 평가 결과 출력 시나리오

데코레이터로 수집된 지표를 세 가지 방식으로 출력할 수 있습니다.

### 시나리오 1 — 터미널 출력 (추가 설치 불필요)

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

report = monitor.generate_report()
print(report.to_json(indent=2))
# → {"accuracy_metrics": {"overall_accuracy": 0.87, ...}, "efficiency_metrics": {...}}
```

### 시나리오 2 — FastAPI 대시보드 (기본 설치에 포함)

`save_to_file()`이 JSON을 쓰고, `agent-eval dashboard`가 이를 읽습니다.

```python
# 데코레이터 실행 후
monitor.save_to_file("eval")     # results/eval.json + .html 자동 생성

# 또는 N건마다 자동 저장
monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# QuickEval 사용 시
eval = QuickEval("results/")
eval.save()                      # results/quickeval.json + .html
```

```bash
agent-eval dashboard results/ --watch    # http://localhost:8765
```

### 시나리오 3 — Phoenix OTEL 실시간 모니터링 (기본 설치에 포함)

`setup_otel()`을 **PerformanceMonitor 생성 전**에 호출해야 합니다.

```bash
# 터미널 1 (기본 설치에 OTEL 포함)
agent-eval monitor                       # Phoenix UI: http://localhost:6006
```

```python
# 터미널 2 — 에이전트 코드
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")  # ← 반드시 먼저
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 호출 시 OTLP 스팬 자동 전송 → Phoenix Tracing 탭에서 실시간 확인
my_agent("한국의 수도는?", ground_truth="서울")
```

---

## 7. 전체 파라미터 레퍼런스

### `@agent_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `task_type` | str | `"qa"` | qa / tool_use / information_retrieval / code_generation / reasoning / planning / data_analysis / creative / coding / multi_agent |
| `profile` | str\|None | `None` | EvalConfig 프로파일 이름 (zero-param 모드) |
| `question_arg` | str | `"question"` | 질문이 담긴 함수 인자 이름 |
| `ground_truth_arg` | str | `"ground_truth"` | 정답이 담긴 함수 인자 이름 |
| `context_arg` | str\|None | `None` | RAG 컨텍스트 인자 이름 (`rag_mode=True` 시 자동 `"context"`) |
| `expected_tools_arg` | str\|None | `None` | Tool Selection F1 평가용 기대 도구 리스트 인자 이름 |
| `task_id_prefix` | str | `"task"` | 자동 생성 task_id 접두사 |
| `task_id_fn` | callable\|None | `None` | task_id 생성 함수 `(args, kwargs) → str` |
| `task_id_arg` | str\|None | `None` | task_id를 직접 받는 인자 이름 |
| `framework` | str | `"native"` | 프레임워크 어댑터 지정 (21개 지원) |
| `auto_detect_framework` | bool | `True` | 리턴값에서 프레임워크 자동 감지 |
| `model_name` | str | `""` | 토큰 비용 계산용 모델명 |
| `score_fn` | callable\|None | `None` | 커스텀 accuracy_score 함수 `(response, ground_truth) → float` |
| `completion_fn` | callable\|None | `None` | 커스텀 completion_score 함수 `(response, ...) → float` |
| `custom_parser` | callable\|None | `None` | 커스텀 메타데이터 파서 `(raw_result) → EvalMetadata` |
| `sample_rate` | float | `1.0` | 기록 샘플링 비율 (0.0–1.0) |
| `sample_condition` | callable\|None | `None` | 조건부 샘플링 `(args, kwargs) → bool` |
| `timeout` | float\|None | `None` | 타임아웃(초), 초과 시 TimeoutError |
| `enabled` | bool | `True` | False 이면 데코레이터 완전 비활성화 |
| `retry` | RetryConfig\|None | `None` | 재시도 설정 (`RetryConfig(max=N, delay=X, backoff=Y, ...)`) |
| `retry_on` | tuple | `(Exception,)` | 재시도할 예외 타입 |
| `should_retry` | callable\|None | `None` | 재시도 조건 함수 `(exc, attempt) → bool` |
| `on_retry` | callable\|None | `None` | 재시도 시 콜백 `(exc, attempt)` |
| `on_record` | callable\|None | `None` | 기록 완료 후 콜백 `(TaskResult)` |
| `on_error` | callable\|None | `None` | 오류 시 콜백 `(exc, TaskResult)` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `alert_error_mode` | str | `"log"` | 알림 오류 처리: "log" / "strict" / "ignore" |
| `flush_every` | int\|None | `None` | N회마다 save_to_file() 자동 호출 |
| `allow_duplicate_task_ids` | bool | `True` | 중복 task_id 허용 |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 (production/development/testing/canary) |
| `enable_hallucination_detection` | bool | `False` | HallucinationDetector 임시 활성 |
| `rag_mode` | bool | `False` | context_arg="context" + hallucination + task_type="information_retrieval" 자동 |
| `security` | SecurityConfig\|None | `None` | 보안 5개 트래커 임시 활성 (`SecurityConfig()`) |
| `allowed_tools` | list\|None | `None` | ToolAuthorization 허용 도구 화이트리스트 |
| `llm_judge` | LLMJudgeConfig\|None | `None` | LLMJudge 설정 (`LLMJudgeConfig(model=..., criteria=[...])`) |
| `enable_anomaly_detection` | bool | `False` | AnomalyDetector 임시 활성 |
| `dry_run` | bool | `False` | 기록 없이 TaskResult만 반환 |

### `@batch_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `task_type` | str | `"qa"` | 태스크 유형 |
| `questions_arg` | str | `"questions"` | 질문 리스트 인자 이름 |
| `ground_truths_arg` | str | `"ground_truths"` | 정답 리스트 인자 이름 |
| `contexts_arg` | str\|None | `None` | RAG 컨텍스트 리스트 인자 이름 |
| `expected_tools_arg` | str\|None | `None` | 기대 도구 리스트 인자 이름 |
| `task_id_prefix` | str | `"batch"` | task_id 접두사 |
| `task_id_fn` | callable\|None | `None` | task_id 생성 함수 |
| `framework` | str | `"native"` | 프레임워크 어댑터 |
| `model_name` | str | `""` | 모델명 |
| `score_fn` | callable\|None | `None` | 커스텀 accuracy_score 함수 |
| `completion_fn` | callable\|None | `None` | 커스텀 completion_score 함수 |
| `on_record` | callable\|None | `None` | 건별 기록 완료 콜백 |
| `on_error` | callable\|None | `None` | 건별 오류 콜백 |
| `on_batch_complete` | callable\|None | `None` | 배치 전체 완료 콜백 |
| `on_batch_progress` | callable\|None | `None` | 진행 상황 콜백 `(done, total)` |
| `on_item_error` | callable\|None | `None` | 아이템 오류 처리 `(exc, idx, question) → str` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `flush_every` | int | `0` | N건마다 자동 저장 (0=비활성) |
| `sample_rate` | float | `1.0` | 샘플링 비율 |
| `sample_condition` | callable\|None | `None` | 조건부 샘플링 |
| `timeout` | float\|None | `None` | 전체 배치 타임아웃(초) |
| `item_timeout` | float\|None | `None` | 건별 타임아웃(초) |
| `enabled` | bool | `True` | 비활성화 플래그 |
| `concurrent` | bool | `False` | 병렬 처리 활성 |
| `max_concurrent` | int | `0` | 동시 실행 수 (0=CPU 코어 수) |
| `shuffle` | bool | `False` | 입력 셔플 |
| `shuffle_seed` | int\|None | `None` | 셔플 시드 |
| `strict_types` | bool | `False` | 타입 불일치 시 오류 발생 |
| `return_format` | str | `"list"` | 반환 형식: "list" / "tuple" / "dataframe" |
| `streaming_mode` | bool | `False` | 스트리밍 모드 (TTFT 자동 측정) |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 |

### `@conversation_eval` 파라미터 전체 목록

| 파라미터 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (필수) | 결과를 기록할 모니터 인스턴스 |
| `session_id_arg` | str | `"session_id"` | 세션 ID 인자 이름 |
| `user_arg` | str | `"question"` | 사용자 입력 인자 이름 |
| `question_arg` | str\|None | `None` | user_arg 별칭 |
| `ground_truth_arg` | str | `"ground_truth"` | 정답 인자 이름 |
| `max_turns` | int\|None | `None` | 최대 턴 수 초과 시 자동 flush |
| `max_session_seconds` | float\|None | `None` | 세션 타임아웃(초) |
| `flush_on_error` | bool | `True` | 오류 시 세션 자동 flush |
| `max_turns_exceeded_action` | str | `"flush"` | "flush" / "error" / "ignore" |
| `load_previous_session` | bool | `False` | 이전 세션 이어받기 |
| `participant_id_arg` | str\|None | `None` | 발화자 구분 인자 이름 |
| `sample_rate` | float | `1.0` | 샘플링 비율 |
| `on_flush` | callable\|None | `None` | 세션 flush 완료 콜백 `(ConversationMetrics)` |
| `on_turn` | callable\|None | `None` | 턴 완료 콜백 `(user, response, metadata)` |
| `on_record` | callable\|None | `None` | 기록 완료 콜백 |
| `session_score_fn` | callable\|None | `None` | 커스텀 세션 점수 `(ConversationMetrics) → float` |
| `turn_score_fn` | callable\|None | `None` | 커스텀 턴 점수 `(user, response, metadata) → float` |
| `alert_rules` | list | `[]` | SimpleTaskAlertRule 리스트 |
| `flush_every` | int | `0` | N턴마다 자동 저장 |
| `enabled` | bool | `True` | 비활성화 플래그 |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS 이름 |

---

## 8. 파라미터 → 지표 활성화 맵

각 파라미터가 어떤 지표를 수집하는지 보여주는 매핑 표입니다.

| 파라미터 | 활성화되는 지표/트래커 | 데이터 소스 | 조건 |
|---|---|---|---|
| `ground_truth_arg` | Accuracy | 함수 인자 자동 추출 | 인자 이름 일치 시 항상 |
| `context_arg` | Hallucination Rate | 함수 인자 자동 추출 | `enable_hallucination_detection=True` 또는 `rag_mode=True` 동반 필요 |
| `rag_mode=True` | Hallucination Rate + context_arg="context" 자동 설정 | "context" 인자 자동 추출 | context 인자 존재 시 |
| `expected_tools_arg` | Tool Selection F1 (Precision/Recall/F1) | 함수 인자 자동 추출 | tool_calls 동시 존재 시 |
| `framework="langchain"` | Tool Call Efficiency, Workflow Execution | LangChain 응답 객체 자동 파싱 | LangChain AgentExecutor 응답 |
| `framework="langgraph"` | Workflow Execution, state_transitions | LangGraph 그래프 상태 파싱 | LangGraph 응답 |
| `framework="crewai"` | Tool Call Efficiency, Agent Coordination | CrewAI TaskOutput 파싱 | CrewAI 응답 |
| `framework="autogen"` | Agent Coordination | AutoGen ChatResult 파싱 | AutoGen 응답 |
| `framework="openai"` | Token Economy (정확) | OpenAI usage 속성 파싱 | OpenAI ChatCompletion |
| `framework="anthropic"` | Token Economy + 캐시 토큰 | Anthropic usage 속성 파싱 | Anthropic Message |
| `auto_detect_framework=True` | 프레임워크별 지표 자동 수집 | 리턴값 타입 기반 자동 감지 | 항상 활성 (기본값) |
| `model_name` | Token Economy 비용 정확도 향상 | 파라미터 직접 지정 | tokens_used 존재 시 |
| `score_fn` | Accuracy | 커스텀 함수 계산값 | response + ground_truth 존재 시 |
| `completion_fn` | TCR | 커스텀 함수 계산값 | response 존재 시 |
| `enable_hallucination_detection=True` | Hallucination Rate | context 인자 | context + response 존재 시 |
| `security=SecurityConfig()` | Input Sanitization, Output Leakage, Tool Authorization, Privilege Escalation, Tool Chain Attack (5개) | question + response + tool_calls | 임시 활성 (finally 복원) |
| `allowed_tools=[...]` | Tool Authorization (허용 도구 기준) | 파라미터 화이트리스트 | `security=SecurityConfig()` 동반 |
| `llm_judge=LLMJudgeConfig()` | LLMJudge (completeness/relevance/factual_consistency/toxicity/bias) | question + response | 기본 설치에 포함 (API 키 필요) |
| `rag_mode=True` + `llm_judge=LLMJudgeConfig()` | + Faithfulness | context + response | context 존재 시 자동 추가 |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | + G-Eval 커스텀 기준 점수 | question + response | llm_judge 설정 내 criteria 지정 |
| `retry=RetryConfig(max=N)` (N>1) | Retry & Error Recovery | 재시도 횟수 + 오류 유형 | 실제 재시도 발생 시 |
| `timeout=N` | Latency (타임아웃 에러 포함) | 실행 시간 측정 | 타임아웃 초과 시 completion_score=0 |
| `sample_rate=0.1` | 모든 지표 (10% 샘플만 기록) | — | 샘플 미해당 시 함수는 정상 실행 |
| `sample_condition=fn` | 모든 지표 (조건 충족 건만 기록) | — | fn 반환값 False 시 기록 생략 |
| `enable_anomaly_detection=True` | Anomaly Detection | save_to_file() 시 자동 실행 | 임시 활성 |
| `flush_every=N` | (지표 아님) N회 호출마다 자동 저장 | — | N의 배수 호출 시 |
| `preset="production"` | sample_rate=0.1 + flush_every=50 + enable_anomaly_detection=True | AGENT_EVAL_PRESETS 딕셔너리 | 프리셋 이름 일치 시 |

---

## 9. 지표 × 데코레이터 지원 매트릭스

| 지표 | `@agent_eval` | `@batch_eval` | `@conversation_eval` | 활성 방법 |
|---|:---:|:---:|:---:|---|
| **Layer 1 — 기반 지표** | | | | |
| TCR (Task Completion Rate) | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 (completion_score 자동 계산) |
| Accuracy | ✅ 자동 | ✅ 자동 | ✅ 자동 | `ground_truth_arg` 인자 존재 시 |
| Response Quality (5차원) | ✅ 자동 | ✅ 자동 | ✅ 자동 | response + question 존재 시 자동 |
| Latency (p50/p95/p99) | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 (실행 시간 자동 측정) |
| TTFT | ✅ generator 함수 | ✅ `streaming_mode=True` | ❌ | generator 리턴 또는 스트리밍 모드 |
| Token Economy | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata |
| Hallucination Rate | ✅ `rag_mode=True` | ✅ `context_arg` 지정 | ❌ | context 인자 + `enable_hallucination_detection=True` |
| **Layer 2 — Agentic 지표** | | | | |
| Tool Call Efficiency | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata.tool_calls |
| Retry & Error Recovery | ✅ `retry=RetryConfig(max=N)` | ❌ | ❌ | `RetryConfig(max>1)` + 실제 재시도 발생 |
| Tool Selection F1 | ✅ `expected_tools_arg` | ✅ `expected_tools_arg` | ❌ | expected_tools + tool_calls 동시 존재 |
| Agent Coordination | ✅ `framework="crewai/autogen"` | ❌ | ❌ | CrewAI/AutoGen 어댑터 또는 EvalMetadata |
| Workflow Execution | ✅ `framework="langchain/langgraph"` | ❌ | ❌ | LangChain/LangGraph 어댑터 또는 EvalMetadata |
| **Layer 2 — Security 지표** | | | | |
| Input Sanitization | ✅ `security=SecurityConfig()` | ❌ | ❌ | `security=SecurityConfig()` 임시 활성 |
| Output Leakage | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Authorization | ✅ `security=SecurityConfig()` + `allowed_tools` | ❌ | ❌ | 동일 + 화이트리스트 |
| Privilege Escalation | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Chain Attack | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| **Layer 3 / LLM Judge** | | | | |
| LLM Judge (5차원) | ✅ `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | 기본 설치에 포함 (API 키 필요) |
| Faithfulness (RAG, v0.7.6+) | ✅ `rag_mode` + `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | context 존재 시 자동 추가 |
| G-Eval 커스텀 기준 (v0.7.6+) | ✅ `llm_judge=LLMJudgeConfig(criteria=[...])` | ❌ | ❌ | llm_judge 설정 내 criteria 지정 |
| **대화 지표 (conversation 전용)** | | | | |
| Context Retention | ❌ | ❌ | ✅ 자동 | 세션 flush 시 compute_metrics() |
| Topic Coherence | ❌ | ❌ | ✅ 자동 | 동일 |
| Progressive Depth | ❌ | ❌ | ✅ 자동 | 동일 |
| Session Completion | ❌ | ❌ | ✅ 자동 | 동일 |
| Per-turn Score | ❌ | ❌ | ✅ `turn_score_fn` | `turn_score_fn` 지정 시 |
| **Optional** | | | | |
| Implicit Feedback | ❌ 직접 불가 | ❌ | ❌ | EvalMetadata.extra에 수동 주입 |
| Streaming Window Metrics | ❌ 직접 불가 | ❌ | ❌ | StreamingEvaluator.record() 별도 호출 |
| Anomaly Detection | ✅ `enable_anomaly_detection=True` | ❌ | ❌ | save_to_file() 실행 시 자동 계산 |

> **`@batch_eval` 제한 이유**: Tool Selection/Agent Coordination/Workflow는 단일 호출 맥락에서만 의미 있고, Security/LLM Judge는 배치 처리 비용이 높습니다.

---

## 10. 데이터 소스 우선순위

`_build_and_record()` 내부의 지표 데이터 수집 우선순위입니다.

```
1순위: return (EvalMetadata, result)   — 명시적 주입 (최고 우선순위)
         accuracy_score, completion_score, tokens_used, tool_calls,
         chain_steps, agent_interactions, context, expected_tools, extra

2순위: get_eval_ctx()                  — ContextVar 주입
         with eval_context(...) as ctx: ctx.response = ... 패턴

3순위: 프레임워크 어댑터               — 리턴값 자동 파싱 (21개 프레임워크)
         LangChain, LangGraph, CrewAI, AutoGen, OpenAI, Anthropic 등

4순위: _auto_detect_framework()       — 리턴값 타입 기반 자동 감지
         type(raw).__module__ 분석으로 프레임워크 추정

5순위: 인자 이름 기반 추출             — 파라미터 명세에 따른 자동 추출
         question_arg → question, ground_truth_arg → ground_truth,
         context_arg → context, expected_tools_arg → expected_tools
```

```python
# 1순위: EvalMetadata 명시적 주입 (최고 우선순위)
from agent_evaluator import EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = llm_with_tools.invoke(question)
    return EvalMetadata(
        accuracy_score=0.92,
        tokens_used={"input": 150, "output": 80},
        tool_calls=[{"tool_name": "search", "duration": 0.3, "success": True}],
        extra={"custom_metric": 0.88},
    ), response.content

# 3순위: 프레임워크 어댑터 자동 수집
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
    # tool_calls, chain_steps, tokens_used 자동 추출

# 5순위: 인자 이름 기반 자동 추출
@agent_eval(monitor, task_type="information_retrieval",
            context_arg="context", expected_tools_arg="expected_tools")
def rag_tool_agent(question: str, context: str = "",
                   expected_tools: list = None, ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
    # context → HallucinationDetector
    # expected_tools → ToolSelectionTracker
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

# LLM Judge (llm_judge=LLMJudgeConfig() 시)
task_dict["extra"]["llm_judge"]["completeness"]         # float (0–5)
task_dict["extra"]["llm_judge"]["relevance"]            # float (0–5)
task_dict["extra"]["llm_judge"]["factual_consistency"]  # float (0–5)
task_dict["extra"]["llm_judge"]["faithfulness"]         # float (0–5, RAG 시)
task_dict["extra"]["llm_judge"]["criteria_scores"]      # dict (LLMJudgeConfig(criteria=[...]) 시)

# Conversation (flush 후)
session_dict["context_retention"]   # float (0–1)
session_dict["topic_coherence"]     # float (0–1)
session_dict["progressive_depth"]   # float (0–1)
session_dict["session_completion"]  # float (0–1)
session_dict["overall_score"]       # float (0–1)
```
