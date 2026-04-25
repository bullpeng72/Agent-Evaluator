# API 레퍼런스

Agent Evaluator v0.8.5 전체 API 문서

---

## 버전 정보

- **버전:** v0.8.5
- **Python:** 3.8+
- **최종 업데이트:** 2026-04-21

---

## 목차

1. [빠른 시작 (4가지 패턴)](#1-빠른-시작)
2. [핵심 클래스 API](#2-핵심-클래스-api)
3. [데코레이터 API](#3-데코레이터-api)
4. [EvalMetadata & get_eval_ctx()](#4-evalmetadata--get_eval_ctx)
5. [컨텍스트 매니저 (evaluation_session)](#5-컨텍스트-매니저)
6. [프레임워크 통합](#6-프레임워크-통합)
7. [보안 API](#7-보안-api)
8. [ConversationSession](#8-conversationsession)
9. [LLMJudge](#9-llmjudge)
10. [이상탐지 / 스트리밍 / 알림](#10-이상탐지--스트리밍--알림)
11. [예외 클래스](#11-예외-클래스)
12. [Layer 2 Agentic 트래커](#12-layer-2-agentic-트래커)
13. [하이브리드 평가 (Layer 3)](#13-하이브리드-평가-layer-3)
14. [CLI 레퍼런스](#14-cli-레퍼런스)

---

## 1. 빠른 시작

### 패턴 1 — @agent_eval 데코레이터 (권장)

가장 유연하고 세밀한 제어가 가능한 표준 방식입니다.

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 호출 시 자동 기록
agent("대한민국의 수도는?", ground_truth="서울")
```

### 패턴 2 — @conversation_eval (멀티턴)

멀티턴 대화의 맥락 유지율을 자동으로 평가합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid")
def chat(msg: str, sid: str):
    return chatbot.chat(msg)

chat("안녕", sid="u1")
chat("오늘 날씨는?", sid="u1")
flush_conversation("u1")
```

### 패턴 3 — @batch_eval (배치 일괄 처리)

질문 리스트를 한 번에 평가하고 결과를 자동으로 기록합니다.

```python
from agent_evaluator.decorators import batch_eval

@batch_eval(monitor, task_type="qa", task_id_prefix="qa_batch")
def qa_batch(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

qa_batch(
    questions=["한국의 수도는?", "Python 창시자는?"],
    ground_truths=["서울", "귀도 반 로섬"],
)
# → 2개의 TaskResult가 monitor에 기록됨
```

### 패턴 4 — QuickEval (편의용 팩토리)

설정을 한 줄로 끝내고 싶을 때 사용합니다.

```python
from agent_evaluator import QuickEval
eval = QuickEval("results/")

@eval.qa
def agent(q): ...
```

---

## 2. 핵심 클래스 API

### PerformanceMonitor

중앙 오케스트레이터. 모든 트래커를 내부에서 구성하고 평가 결과를 집계한다.

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",                # 저장 디렉토리 (기본: "results/")
    enable_hallucination_detection=False, # Hallucination 탐지 활성화 (기본: False)
    enable_security_metrics=False,        # 보안 지표 활성화 (기본: False)
    auto_save=False,                      # N건마다 자동 저장 여부 (기본: False)
    auto_save_interval=10,                # 자동 저장 주기 (기본: 10)
    auto_save_filename="auto_save",       # 자동 저장 파일명
)
```

#### 주요 메서드

| 메서드 | 반환값 | 설명 |
|--------|--------|------|
| `record_task(result)` | `self` | TaskResult 기록. 메서드 체이닝 지원 |
| `generate_report()` | `EvaluationReport` | 누적 지표 기반 보고서 생성 |
| `save_to_file(filename)` | `None` | JSON + HTML 파일 저장 |
| `compare_with_thresholds()` | `dict` | 임계값 대비 통과/실패 여부 (`monitor.thresholds = {...}`로 설정) |
| `reset(keep_config=True)` | `None` | 누적 태스크 초기화 |
| `snapshot()` | `dict` | 현재 상태 스냅샷 |
| `compare_with_snapshot(snap)` | `dict` | 스냅샷과 현재 지표 비교 |
| `restore_from_snapshot(snap)` | `None` | 스냅샷으로 복원 |
| `clone()` | `PerformanceMonitor` | 설정 복제 (태스크 제외) |
| `merge(other)` | `None` | 다른 모니터의 태스크 병합 |
| `filter_tasks(**kwargs)` | `list` | 조건부 태스크 필터링 |
| `aggregate_metrics(since, until, by)` | `dict` | 기간/기준별 지표 집계 |
| `get_timeseries_metrics(metric, granularity)` | `list` | 시계열 지표 조회 |
| `export_to_dataframe(include_fields)` | `DataFrame` | pandas DataFrame으로 내보내기 |
| `export_to_wandb()` | `None` | Weights & Biases 내보내기 (requires wandb) |
| `export_to_mlflow()` | `None` | MLflow 내보내기 (requires mlflow) |
| `compare(other)` | `dict` | 다른 모니터와 지표 비교 |
| `analyze()` | `dict` | 병목 분석 + 최적화 권고 |

#### 팩토리 classmethod

```python
# RAG 평가 최적 설정 (hallucination_detection 기본 활성)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# 보안 에이전트 평가 최적 설정 (security_metrics 기본 활성)
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

---

### TaskResult

단일 태스크 실행 결과를 담는 불변 데이터클래스 (`@dataclass(frozen=True)`).

#### 필수 필드 (11개)

| 필드 | 타입 | 설명 |
|------|------|------|
| `task_id` | `str` | 고유 태스크 식별자 |
| `task_type` | `str \| TaskType` | 태스크 유형 (e.g. `"qa"`) |
| `success` | `bool` | 성공 여부 |
| `completion_score` | `float` | 완료 점수 (0.0–1.0) |
| `accuracy_score` | `float` | 정확도 점수 (0.0–1.0) |
| `execution_time` | `float` | 실행 시간 (초) |
| `tokens_used` | `dict` | 토큰 사용량 `{"total": int, "input": int, "output": int}` |
| `tool_calls` | `list` | 도구 호출 목록 |
| `attempts` | `int` | 시도 횟수 |
| `errors` | `list` | 발생한 오류 목록 |
| `timestamp` | `datetime` | 기록 시각 |

#### 선택 필드 (13개)

| 필드 | 타입 | 설명 |
|------|------|------|
| `response` | `str \| None` | 에이전트 응답 텍스트 |
| `question` | `str \| None` | 입력 질문 |
| `ground_truth` | `str \| None` | 정답 |
| `context` | `str \| None` | RAG 컨텍스트 |
| `framework` | `str \| None` | 사용 프레임워크 (e.g. `"langchain"`) |
| `model_name` | `str \| None` | 사용 모델명 |
| `task_name` | `str \| None` | 태스크 이름 (선택 레이블) |
| `has_error` | `bool` | 오류 발생 여부 |
| `partial_reason` | `str \| None` | 부분 완료 이유 |
| `extra` | `dict` | 추가 메타데이터 |
| `agent_interactions` | `list` | 멀티 에이전트 교환 목록 |
| `chain_steps` | `list` | 체인 실행 단계 목록 |
| `expected_tools` | `list` | 기대 도구 목록 (F1 계산용) |

#### 권장 생성 방법 — create_taskresult() 헬퍼

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
    # 선택
    tokens_used={"total": 150, "input": 50, "output": 100},
    tool_calls=[],
    context=None,
    framework="openai",
    model_name="gpt-4o-mini",
)
```

`create_taskresult()`는 `accuracy_score`와 `completion_score`를 자동 계산한다. `success`, `attempts`, `errors`, `timestamp` 필드도 기본값이 자동 설정된다.

#### 직렬화 / 역직렬화

```python
d = result.to_dict()
result2 = TaskResult.from_dict(d)       # ISO-8601 timestamp 자동 변환
result3 = TaskResult.from_json(json_str)
```

---

### EvaluationReport

`generate_report()`가 반환하는 불변 보고서 객체.

```python
report = monitor.generate_report()

# 주요 속성
report.task_completion_rate     # float (0–100)
report.overall_accuracy         # float (0–100)
report.average_latency          # float (초)
report.total_tasks              # int
report.successful_tasks         # int
report.hallucination_rate       # float | None (enable_hallucination_detection=True 시)
report.security_incidents       # dict | None (enable_security_metrics=True 시)

# 직렬화 / 역직렬화
d = report.to_dict()
report2 = EvaluationReport.from_dict(d)
report3 = EvaluationReport.from_json(json_str)

# 동등 비교 (timestamp 제외 의미론적 비교)
assert report == report2
```

---

### TaskType (Enum)

```python
from agent_evaluator import TaskType

TaskType.QA                    # "qa"
TaskType.CODE_GENERATION       # "code_generation"
TaskType.DATA_ANALYSIS         # "data_analysis"
TaskType.DOCUMENT_CREATION     # "document_creation"
TaskType.INFORMATION_RETRIEVAL # "information_retrieval"
TaskType.REASONING             # "reasoning"
TaskType.CREATIVE              # "creative"
TaskType.CODING                # "coding"
TaskType.PLANNING              # "planning"
TaskType.TOOL_USE              # "tool_use"
```

`task_type` 파라미터는 Enum과 문자열 혼용을 지원한다 (`TaskType.QA` == `"qa"`).

---

## 3. 데코레이터 API

### agent_eval

가장 유연한 단일 함수 평가 데코레이터. 함수 실행 결과를 자동으로 TaskResult로 변환하여 monitor에 기록한다.

```python
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    task_type="qa",                  # 필수. TaskType Enum 또는 문자열
    question_arg="question",         # 질문 파라미터 이름 (기본: "question")
    ground_truth_arg="ground_truth", # 정답 파라미터 이름 (기본: "ground_truth")
    context_arg=None,                # RAG 컨텍스트 파라미터 이름
    framework=None,                  # "langchain"|"openai"|"anthropic"|... 21개
    model_name=None,                 # 모델명
    task_id_prefix=None,             # task_id 접두사
    enabled=True,                    # 데코레이터 활성화 여부
    rag_mode=False,                  # context_arg + hallucination + IR 자동 설정
    security=None,                   # 보안 지표 임시 활성 (SecurityConfig())
    llm_judge=None,                  # LLM Judge 설정 (LLMJudgeConfig(model=..., criteria=[...]))
    enable_anomaly_detection=False,  # 이상 탐지 임시 활성
    enable_hallucination_detection=False,  # Hallucination 탐지 임시 활성
    alert_rules=[],                  # SimpleTaskAlertRule 목록
    flush_every=0,                   # N 호출마다 save_to_file() 자동 실행 (0=비활성)
    retry=None,                      # 재시도 설정 (RetryConfig(max=N, delay=X, backoff=Y))
    on_record=None,                  # TaskResult 후처리 콜백 (TaskResult → TaskResult)
    sample_rate=1.0,                 # 샘플링 비율 (0.0–1.0)
    sample_condition=None,           # (args, kwargs) → bool 조건부 샘플링
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

`rag_mode=True` 단축 예시:

```python
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

---

### QuickEval

`PerformanceMonitor` + `EvalDecorator`를 1줄로 시작하는 원스톱 Facade.

```python
from agent_evaluator import QuickEval

# 기본 생성
eval = QuickEval("results/")

# 팩토리 메서드
eval = QuickEval.for_rag("results/")
eval = QuickEval.for_security("results/")
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
eval = QuickEval.for_regression_eval("results/", baseline_file="baseline.json")

# YAML 설정 파일에서 로드
eval = QuickEval.from_config("eval_config.yaml")
```

#### 단축 데코레이터 (property)

```python
@eval.qa           # task_type="qa"
@eval.rag          # task_type="information_retrieval" + context_arg="context"
@eval.tool_use     # task_type="tool_use"
@eval.code         # task_type="code_generation"
@eval.reasoning    # task_type="reasoning"
@eval.planning     # task_type="planning"
@eval.data_analysis  # task_type="data_analysis"
@eval.creative     # task_type="creative"
@eval.chat         # task_type="qa" (대화형)
@eval.multi_agent  # task_type="tool_use" + 멀티 에이전트 설정
@eval.security     # security=SecurityConfig()
def agent(question: str, ground_truth: str = "") -> str:
    ...
```

직접 호출 (커스텀 파라미터):

```python
@eval(task_type="qa", framework="anthropic", flush_every=10)
def agent(question: str, ground_truth: str = "") -> str:
    ...
```

#### 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `save()` | `quickeval.json` + `quickeval.html` 저장 |
| `gate(tcr=None, accuracy=None, quality=None, hallucination=None)` | 임계값 미달 시 `sys.exit(1)` |
| `summary()` | dict — `task_completion_rate`, `overall_accuracy`, `p95_latency`, `total_cost_usd`, `hallucination_rate` 등 |
| `compare(other)` | 두 QuickEval 인스턴스의 지표 비교 |
| `ab_test(other)` | A/B 비교 + t-검정 p-value (scipy 필요) |
| `generate_gate_config(filepath)` | 현재 지표 기반 95% 임계값 자동 제안 → JSON 저장 |
| `export_to_dataframe()` | pandas DataFrame 내보내기 |
| `replay(results_file)` | 기존 JSON 결과 재로딩 |
| `watch(directory, callback)` | 디렉토리 감시 + 신규 JSON 자동 replay |

#### auto_save 옵션

```python
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
# 10건 기록마다 save_to_file() 자동 호출
```

---

### batch_eval

리스트 입력을 받아 일괄 처리하는 데코레이터. `questions[i]` / `ground_truths[i]` / `responses[i]`를 묶어 각각 독립된 `TaskResult`로 기록한다.

```python
from agent_evaluator.decorators import batch_eval

@batch_eval(
    monitor,
    task_type="qa",
    # ── 입출력 파라미터 이름 ──────────────────────────────────
    questions_arg="questions",        # 질문 리스트 파라미터 이름 (기본: "questions")
    ground_truths_arg="ground_truths",# 정답 리스트 파라미터 이름 (기본: "ground_truths")
    contexts_arg=None,                # RAG context 리스트 파라미터 이름 (RAG 평가 시)
    expected_tools_arg=None,          # expected_tools 리스트 파라미터 이름 (Tool F1 계산 시)
    # ── task_id 생성 ─────────────────────────────────────────
    task_id_prefix="batch",           # 자동 생성 task_id 접두어 → {prefix}_{uuid8}_{i:03d}
    task_id_fn=None,                  # 커스텀 task_id 생성 함수 (index, question, gt) -> str
    # ── 프레임워크 / 모델 ────────────────────────────────────
    framework="native",               # 프레임워크 식별자 (21개 지원)
    model_name="",                    # LLM 모델명
    # ── 채점 커스텀 ─────────────────────────────────────────
    score_fn=None,                    # 커스텀 accuracy 함수 (response, gt) -> float
    completion_fn=None,               # 커스텀 completion 함수
    # ── 콜백 ────────────────────────────────────────────────
    on_record=None,                   # 항목별 기록 후 콜백 (task_result) -> None
    on_error=None,                    # 배치 함수 예외 발생 시 콜백
    on_batch_complete=None,           # 배치 전체 완료 후 콜백 (results_list) -> None
    on_batch_progress=None,           # 항목별 진행 콜백 (i, total) -> None
    on_item_error=None,               # 항목별 오류 콜백 (exc, index, question) -> None
    # ── 실행 제어 ────────────────────────────────────────────
    concurrency=0,                    # >0이면 항목별 병렬 실행 (ThreadPool/asyncio.gather)
    item_timeout=None,                # 항목별 타임아웃 (초)
    timeout=None,                     # 배치 전체 타임아웃 (초)
    sample_rate=1.0,                  # 평가 실행 비율 (0.0–1.0)
    enabled=True,                     # False이면 데코레이터 우회
    # ── 저장 / 출력 ─────────────────────────────────────────
    return_format="list",             # "list" | "dataframe"
    flush_every=None,                 # N 배치 호출마다 save_to_file() 자동 실행
    alert_rules=None,                 # SimpleTaskAlertRule 목록
    preset=None,                      # "production"|"development"|"testing"|"canary"
    # ── 선택적 평가 활성화 ───────────────────────────────────
    enable_hallucination_detection=False,
    enable_anomaly_detection=False,
    security=None,                    # SecurityConfig() — 보안 지표 임시 활성
    llm_judge=None,                   # LLMJudgeConfig(model=..., criteria=[...])
    custom_parser=None,               # 응답 파싱 커스텀 함수
    # ── Harness Config (33개 모두 지원) ─────────────────────
    # instructions=InstructionConfig(...), sla=SLAConfig(...), ...
)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

results = batch_agent(questions, ground_truths=gts)
```

`return_format="dataframe"` 시 DataFrame에는 `tokens_total`, `tokens_input`, `tokens_output`, `framework`, `tool_call_count`, `has_error`, `attempts`, `timestamp` 컬럼이 포함된다.

#### 주요 사용 예시

```python
# RAG 배치 평가
@batch_eval(
    monitor, task_type="information_retrieval",
    contexts_arg="contexts",
    enable_hallucination_detection=True,
)
def rag_batch(questions, contexts=None, ground_truths=None):
    return [rag_chain.invoke({"question": q, "context": c})
            for q, c in zip(questions, contexts)]

# 병렬 실행 (concurrency=4 → ThreadPool 4개)
@batch_eval(monitor, task_type="qa", concurrency=4, item_timeout=10.0)
def fast_batch(questions, ground_truths=None):
    return [llm.invoke(q) for q in questions]

# LLM Judge + 배치 저장
@batch_eval(
    monitor, task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-haiku-4-5-20251001"),
    flush_every=5,
)
def judged_batch(questions, ground_truths=None):
    return [llm.invoke(q) for q in questions]
```

---

### eval_context

컨텍스트 매니저 형태의 평가 데코레이터. 외부 함수나 복잡한 흐름에 적합하다.

```python
from agent_evaluator.decorators import eval_context

with eval_context(
    monitor,
    task_type="qa",
    question="한국의 수도는?",
    ground_truth="서울",
    timeout=30.0,            # 타임아웃 (초)
    auto_task_id=True,       # task_id 자동 생성
) as ctx:
    ctx.response = external_agent(ctx.question)
    ctx.tokens_used = {"total": 100, "input": 30, "output": 70}
    ctx.tool_calls = [{"tool_name": "search", "success": True}]
    ctx.chunk_step("retrieval", success=True)  # 스트리밍 청크 단계 기록
```

`ctx.depth`로 중첩 깊이를 조회할 수 있다. 최대 중첩 깊이는 `eval_context.MAX_NESTING_DEPTH`로 제한된다.

---

### conversation_eval

멀티턴 대화 평가 데코레이터.

```python
from agent_evaluator.decorators import conversation_eval

@conversation_eval(
    monitor,
    session_id_arg="session_id",             # session_id 파라미터 이름
    participant_id_arg=None,                 # 참여자 ID 파라미터
    max_turns_exceeded_action="warn",        # "warn"|"raise"|"ignore"
    load_previous_session=False,             # 이전 세션 이어서 평가
    flush_every=0,
    on_session_timeout=None,                 # 세션 타임아웃 콜백
    on_turn=None,                            # 턴별 콜백 (turn_num, question, response)
    session_score_fn=None,                   # 세션 점수 함수 override
    turn_score_fn=None,                      # 턴별 점수 함수 override
)
def chat_agent(message: str, session_id: str = "s1") -> str:
    return chat_model.invoke(message)
```

비동기 제너레이터도 지원된다.

---

### EvalDecorator (인스턴스 모드)

`QuickEval` 내부에서 사용하는 클래스. 직접 사용 시:

```python
from agent_evaluator.decorators import EvalDecorator

decorator = EvalDecorator(
    monitor,
    task_type="qa",
    rag_mode=False,
    security=None,
    llm_judge=None,
    enable_anomaly_detection=False,
    enable_hallucination_detection=False,
)

@decorator.qa           # task_type="qa"
@decorator.tool_use     # task_type="tool_use"
@decorator.rag          # task_type="information_retrieval"
@decorator.secure       # security=SecurityConfig()
def agent(question: str, ground_truth: str = "") -> str:
    ...

# batch 및 context 모드
@decorator.batch(shuffle=True)
def batch_fn(questions, ground_truths=None): ...

with decorator.context("qa", question="질문") as ctx:
    ctx.response = external_fn(ctx.question)
```

---

## 4. EvalMetadata & get_eval_ctx()

데코레이터 내부 함수에서 평가 메타데이터를 주입하는 두 가지 방법.

### 방법 A — get_eval_ctx() (컨텍스트 주입)

```python
from agent_evaluator.decorators import agent_eval, get_eval_ctx

@agent_eval(monitor, task_type="tool_use")
def tool_agent(question: str, ground_truth: str = "") -> str:
    ctx = get_eval_ctx()
    ctx.tool_calls = [
        {"tool_name": "web_search", "success": True, "duration": 0.5},
        {"tool_name": "summarize", "success": True},
    ]
    ctx.chain_steps = [
        {"step": "retrieve", "success": True},
        {"step": "generate", "success": True},
    ]
    ctx.tokens_used = {"input": 100, "output": 50, "total": 150}
    return "answer"
```

`get_eval_ctx()`는 데코레이터 실행 스택 외부에서 호출하면 `None`을 반환한다.

### 방법 B — EvalMetadata 튜플 반환

```python
from agent_evaluator.decorators import agent_eval, EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def agent(question: str, ground_truth: str = "") -> tuple:
    meta = EvalMetadata(
        tool_calls=[{"tool_name": "search", "success": True}],
        tokens_used={"input": 80, "output": 40, "total": 120},
        chain_steps=[{"step": "search", "success": True}],
        agent_interactions=[{"from": "planner", "to": "executor"}],
        model_name="gpt-4o-mini",
        framework="openai",
    )
    return "answer", meta
```

데코레이터는 반환값이 `(str, EvalMetadata)` 튜플임을 감지하면 자동으로 분리한다.

---

## 5. 컨텍스트 매니저

`evaluation_session` / `async_evaluation_session`은 세션 단위 자동 저장을 제공합니다.
세션 블록 종료 시 (예외 발생 시에도) `results/*.json + .html`을 자동 저장합니다.

### 권장 — @agent_eval 데코레이터와 함께

```python
from agent_evaluator import PerformanceMonitor, evaluation_session
from agent_evaluator.decorators import agent_eval

with evaluation_session("output_filename") as monitor:

    @agent_eval(monitor, task_type="qa")
    def my_agent(question: str, ground_truth: str = "") -> str:
        return llm.invoke(question)

    for q, gt in dataset:
        my_agent(q, ground_truth=gt)
# 세션 종료 시 results/output_filename.json + .html 자동 저장
# 예외 발생 시에도 안전하게 저장됨
```

### 탈출구 — eval_context (데코레이터 불가 시)

```python
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("output_filename") as monitor:
    for q, gt in dataset:
        with eval_context(monitor, task_type="qa",
                          question=q, ground_truth=gt) as ctx:
            ctx.response = external_agent.run(q)
```

### 저수준 — create_taskresult() 직접 사용

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("output_filename") as monitor:
    for q, gt in dataset:
        result = create_taskresult(
            task_id=f"t{i}",
            question=q,
            response=agent.run(q),
            ground_truth=gt,
            execution_time=1.0,
            task_type="qa",
        )
        monitor.record_task(result)
```

### async_evaluation_session (비동기)

```python
from agent_evaluator import async_evaluation_session
from agent_evaluator.decorators import eval_context

async def run():
    async with async_evaluation_session("async_eval") as monitor:
        for q, gt in dataset:
            async with eval_context(monitor, task_type="qa",
                                    question=q, ground_truth=gt) as ctx:
                ctx.response = await async_agent.run(q)
```

### hybrid_evaluation_session

```python
from agent_evaluator import hybrid_evaluation_session

async with hybrid_evaluation_session("hybrid_eval") as monitor:
    ...
```

---

## 6. 프레임워크 통합

21개 프레임워크에 대해 응답 객체에서 `tool_calls`, `chain_steps`, `tokens_used`, `state_transitions` 등을 자동 추출한다.

### framework= 파라미터

```python
from agent_evaluator.decorators import agent_eval

# langchain
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return lc_chain.invoke({"input": question})

# openai
@agent_eval(monitor, task_type="qa", framework="openai")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    )

# anthropic
@agent_eval(monitor, task_type="qa", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": question}],
    )
```

#### 지원 프레임워크 (21개)

| 그룹 | 프레임워크 |
|------|-----------|
| LLM SDK | `anthropic`, `openai`, `gemini`, `cohere`, `groq`, `mistral`, `ollama`, `vllm`, `huggingface` |
| 오케스트레이션 | `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`, `smolagents`, `semantic_kernel` |
| 클라우드 | `vertexai`, `bedrock` |
| 검색/RAG | `llamaindex`, `haystack` |

자동 감지 (`auto_detect_framework=True` 기본 활성):

```python
@agent_eval(monitor, task_type="qa")  # framework= 생략 시 응답 속성으로 자동 감지
def agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # openai 자동 감지
```

### 프레임워크 전용 데코레이터

```python
from agent_evaluator.integrations import (
    langchain_eval,
    langgraph_eval,
    crewai_eval,
    autogen_eval,
    dspy_eval,
    pydanticai_eval,
)

@langchain_eval(monitor, task_type="qa")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return chain.invoke({"input": question})
```

### 프레임워크 메타데이터 조회

```python
from agent_evaluator.decorators import get_framework_info

info = get_framework_info("langchain")
# {"extracts": ["tool_calls", "chain_steps", "tokens_used"], "description": "..."}
```

---

## 7. 보안 API

보안 지표는 기본적으로 비활성화되어 있다 (`enable_security_metrics=False`). 활성화 방법은 세 가지다.

### 방법 1 — PerformanceMonitor 영구 활성

```python
monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)
# 또는
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

### 방법 2 — SecurityConfig 임시 활성 (데코레이터)

```python
from agent_evaluator.decorators import agent_eval, SecurityConfig

@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# 함수 종료 후 monitor의 security 설정을 원래 값으로 복원
```

### 방법 3 — 독립 사용

```python
from agent_evaluator.helpers.taskresult_helpers import (
    validate_input_security,
    check_output_leakage,
)

# 입력 보안 검증
result = validate_input_security(user_input)
# 반환: {"is_safe": bool, "threats": list, "risk_level": "low"|"medium"|"high"}

# 출력 유출 탐지
result = check_output_leakage(agent_output)
# 반환: {"has_leakage": bool, "leaked_types": list}
```

### 탐지 패턴

`InputSanitizationTracker`가 탐지하는 위협 유형:

| 유형 | 설명 |
|------|------|
| `sql_injection` | SQL 주입 시도 |
| `command_injection` | 시스템 명령 주입 |
| `path_traversal` | 디렉토리 탐색 공격 |
| `xss` | 크로스 사이트 스크립팅 |
| `prompt_injection` | 프롬프트 주입 |

### 5개 보안 트래커

| 클래스 | 탐지 대상 |
|--------|----------|
| `InputSanitizationTracker` | 입력 주입 공격 5종 |
| `OutputLeakageDetector` | API 키, 비밀번호, 파일 경로 등 민감 정보 유출 |
| `ToolAuthorizationTracker` | 미승인 도구 호출 |
| `PrivilegeEscalationDetector` | 권한 상승 시도 |
| `ToolChainAttackDetector` | 연쇄 도구 공격 패턴 |

#### 주요 파라미터 (v0.8.3+)

```python
# 샘플링 — 고트래픽 환경에서 성능 최적화
tracker = InputSanitizationTracker(sample_rate=0.2)   # 20%만 검사
detector = OutputLeakageDetector(sample_rate=0.2)

# 시스템 경로 제외 목록 커스터마이즈 (OutputLeakageDetector)
detector = OutputLeakageDetector(
    excluded_unix_paths=["usr/", "bin/", "myapp/", "opt/"]  # 기본: 8개 시스템 접두사
)

# sample_rate=0.0 이면 전부 건너뜀 (sampled_out: True 반환)
# sample_rate=1.0 이면 전수 검사 (기본값)
```

---

## 8. ConversationSession

멀티턴 대화 평가를 위한 클래스.

```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn

session = ConversationSession(session_id="conv_001")
session.add_turn(user_input="안녕하세요", agent_response="안녕하세요!")
session.add_turn(user_input="오늘 날씨는?", agent_response="맑습니다.")

metrics: ConversationMetrics = session.compute_metrics()
```

#### ConversationMetrics 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `turn_count` | `int` | 총 턴 수 |
| `overall_score` | `float` | 전체 점수 (0.0–1.0) |
| `context_retention` | `float` | 컨텍스트 유지율 |
| `topic_coherence` | `float` | 주제 일관성 |
| `progressive_depth` | `float` | 대화 깊이 진행도 |
| `session_completion` | `float` | 세션 완료율 |
| `avg_turn_latency` | `float \| None` | 평균 턴 지연시간 (초) |
| `turn_scores` | `dict \| None` | 턴별 품질 점수 `{turn_num: score}` |

### PerformanceMonitor와 통합 (권장)

```python
with monitor.conversation("session_001") as conv:
    for user_msg, agent_response in dialogue:
        conv.turn(
            user=user_msg,
            agent=agent_response,
            metadata={"latency": 0.3, "tokens": 120},
        )
```

---

## 9. LLMJudge

ground_truth 없이 LLM이 직접 채점하는 평가 엔진. 기본 설치에 포함되어 있다.

```python
from agent_evaluator import LLMJudge  # pip install agent-evaluator (기본 설치에 포함)

judge = LLMJudge(
    model="claude-haiku-4-5-20251001",   # 기본 모델 (빠름·저비용)
    sample_rate=0.1,                      # 10%만 채점
    budget_per_day=1.0,                   # 하루 $1 상한
    judge_criteria=["medical_accuracy"],  # G-Eval 커스텀 기준 (선택)
    # 다중 모델 자동 에스컬레이션 (v0.8.3+)
    escalation_model="claude-sonnet-4-6", # primary 점수 미달 시 재채점
    escalation_threshold=2.5,             # overall < 2.5 이면 에스컬레이션 (0–5 스케일)
)

result = judge.judge(
    task_id="t1",
    question="한국의 수도는?",
    response="서울은 한국의 수도입니다.",
    context="한국은 동아시아의 나라이다.",  # RAG 컨텍스트 (선택)
)

result["scores"]["overall"]        # float (0–5) — 품질 3차원 평균
result["scores"]["faithfulness"]   # float (0–5) — RAG 충실도 (context 있을 때)
result.get("escalated")            # True이면 escalation_model로 재채점된 결과
result.get("primary_overall")      # 에스컬레이션 전 primary 점수
```

#### `LLMJudge` 생성자 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `model` | `None` (자동) | 기본 채점 모델 |
| `sample_rate` | `0.1` | 채점 비율 (0.0–1.0) |
| `budget_per_day` | `None` | 일일 USD 상한 |
| `judge_criteria` | `None` | G-Eval 커스텀 기준 리스트 |
| `escalation_model` | `None` | 재채점 상위 모델 (v0.8.3+) |
| `escalation_threshold` | `2.5` | 에스컬레이션 트리거 임계값 (v0.8.3+) |
| `max_context_chars` | `4000` | 컨텍스트 잘림 한도 |
| `seed` | `None` | 샘플링 재현성용 랜덤 시드 |

### 비동기 채점 — `ajudge()` (v0.8.3+)

`run_in_executor` 기반 non-blocking 호출. `asyncio` 환경에서 사용한다.

```python
import asyncio

result = asyncio.run(judge.ajudge(
    task_id="t1",
    question="한국의 수도는?",
    response="서울입니다.",
))
```

### 연속 오류 자동 비활성화 / 복구 (v0.8.3+)

3회 연속 API 오류 발생 시 자동 비활성화되고 이후 호출은 `{"skipped": True}` 를 반환한다.

```python
# 비활성화 확인
judge._disabled_reason  # None이면 정상, str이면 비활성화 사유

# 복구
judge.reset_errors()    # 오류 카운터 리셋 + 재활성화
```

### 환경변수 — `AGENT_EVALUATOR_JUDGE_PROVIDER` (v0.8.3+)

LLM Judge가 사용할 API 제공자를 지정한다.

```bash
AGENT_EVALUATOR_JUDGE_PROVIDER=auto        # 기본: API 키 보유 제공자 자동 선택
AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic   # Anthropic API 우선 사용
AGENT_EVALUATOR_JUDGE_PROVIDER=openai      # OpenAI API 우선 사용
```

### QuickEval과 통합

```python
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### agent_eval과 통합

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"))
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 10. 이상탐지 / 스트리밍 / 알림

### AnomalyDetector

```python
from agent_evaluator import AnomalyDetector, AnomalyEvent

detector = AnomalyDetector(
    latency_threshold=5.0,      # 초
    accuracy_threshold=0.5,
    window_size=100,
)

events = detector.scan(monitor)
# events: List[AnomalyEvent]

event = events[0]
event.event_type    # "latency_spike" | "accuracy_drop" | ...
event.severity      # "low" | "medium" | "high"
event.timestamp

# 원인 설명
explanation = detector.explain_event(event)
# {"cause": str, "recommendation": str, "affected_tasks": [...]}

events_with_explanation = detector.scan_with_explain(monitor)
```

### StreamingEvaluator

```python
from agent_evaluator.streaming import StreamingEvaluator

streaming_eval = StreamingEvaluator(
    monitor=monitor,
    window_size=50,
    slide_size=10,
)
streaming_eval.process(task_result)
```

### SimpleTaskAlertRule & AlertRuleBuilder

```python
from agent_evaluator import SimpleTaskAlertRule
from agent_evaluator.alerts import AlertRuleBuilder

# 직접 생성
rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)

# 빌더 팩토리 (권장)
rule = AlertRuleBuilder.when_latency_above(
    threshold=5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)
rule = AlertRuleBuilder.when_accuracy_below(threshold=0.7, handler=my_handler)
rule = AlertRuleBuilder.when_completion_below(threshold=0.8, handler=my_handler)
rule = AlertRuleBuilder.when_error(handler=my_handler)
rule = AlertRuleBuilder.when_tool_calls_exceed(max_calls=10, handler=my_handler)

# dry_run — 핸들러 미실행 조건 검증
fired = rule.dry_run(task_result)  # bool

# 복합 조건
rule = SimpleTaskAlertRule(
    name="compound_check",
    compound_conditions=[
        {"field": "execution_time", "op": "gt", "value": 3.0},
        {"field": "accuracy_score", "op": "lt", "value": 0.7},
    ],
    handler=my_handler,
)

# agent_eval과 통합
@agent_eval(monitor, task_type="qa", alert_rules=[rule])
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### ImplicitFeedbackTracker

```python
from agent_evaluator import ImplicitFeedbackTracker

tracker = ImplicitFeedbackTracker()
tracker.record(
    task_id="t1",
    feedback_type="thumbs_up",    # "thumbs_up"|"thumbs_down"|"copy"|"regenerate"
    latency=0.1,
)
stats = tracker.get_stats()
# {"thumbs_up_rate": float, "regenerate_rate": float, ...}
```

---

## 11. 예외 클래스

```python
from agent_evaluator.exceptions import (
    ValidationError,
    InvalidOperationError,
)

# ValidationError — 입력값 검증 실패
raise ValidationError(
    "task_id는 비어 있을 수 없습니다.",
    context={"task_id": "", "field": "task_id"},
)

# InvalidOperationError — 잘못된 상태에서의 작업 호출
raise InvalidOperationError(
    "모니터가 초기화되지 않았습니다.",
    context={"monitor_state": "uninitialized"},
)
```

두 클래스 모두 `message`와 선택적 `context: dict` 필드를 가진다.

---

## 12. Layer 2 Agentic 트래커

`PerformanceMonitor`에 내장되어 `record_task()` 호출 시 자동 집계된다. 개별 접근이 필요한 경우:

### ToolCallAnalyzer

```python
from agent_evaluator import ToolCallAnalyzer

analyzer = ToolCallAnalyzer()
analyzer.record(task_result)
stats = analyzer.get_stats()
# {"total_calls": int, "success_rate": float, "avg_calls_per_task": float}
```

### ToolSelectionTracker

```python
from agent_evaluator import ToolSelectionTracker

tracker = ToolSelectionTracker()
tracker.record(task_result)  # expected_tools 필드 필요
f1_stats = tracker.get_f1_by_tool()
# {"tool_name": {"precision": float, "recall": float, "f1": float}}
```

### AgentCoordinationTracker

```python
from agent_evaluator import AgentCoordinationTracker

tracker = AgentCoordinationTracker()
tracker.record(task_result)
topology = tracker.get_network_topology()
# {"pattern": "hub"|"chain"|"mesh", "density": float, "hub_nodes": list}
```

### WorkflowExecutionTracker

```python
from agent_evaluator import WorkflowExecutionTracker

tracker = WorkflowExecutionTracker()
tracker.record(task_result)
stats = tracker.get_stats()
# {"success_rate": float, "avg_steps": float, "branching_rate": float}
```

### RetryCorrectionTracker

```python
from agent_evaluator import RetryCorrectionTracker

tracker = RetryCorrectionTracker()
tracker.record(task_result)
stats = tracker.get_stats()
# {"avg_attempts": float, "retry_rate": float, "correction_success_rate": float}
```

---

## 13. 하이브리드 평가 (Layer 3)

외부 평가 라이브러리(DeepEval, Ragas)와 통합. `[eval]` extra가 필요하다.

```python
from agent_evaluator import HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport
from agent_evaluator.decorators import agent_eval

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_deepeval=True,
    enable_ragas=True,
)

# 권장: 데코레이터 방식 (rag_mode=True → hallucination + IR 자동 활성)
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})

# 저수준: hybrid_evaluation_session + ExtendedTaskResult 직접 주입
# (retrieved_contexts 등 하이브리드 전용 필드가 필요한 경우)
from agent_evaluator import hybrid_evaluation_session

async with hybrid_evaluation_session("hybrid_eval") as monitor:
    from agent_evaluator import create_taskresult
    import dataclasses

    base = create_taskresult(
        task_id="hybrid_001",
        question="질문",
        response="답변",
        ground_truth="정답",
        execution_time=1.5,
        task_type="information_retrieval",
    )
    result = ExtendedTaskResult(
        **dataclasses.asdict(base),
        retrieved_contexts=["컨텍스트1", "컨텍스트2"],
    )
    monitor.record_task(result)

report: HybridEvaluationReport = monitor.generate_report()
report.deepeval_scores     # DeepEval 지표
report.ragas_scores        # Ragas 지표
```

### 개별 어댑터

```python
from agent_evaluator.integrations.metric_adapters import (
    DeepEvalAdapter,
    RagasAdapter,
)

# DeepEval
adapter = DeepEvalAdapter()
scores = adapter.evaluate(question, response, ground_truth)

# Ragas (requires datasets>=4.0.0)
adapter = RagasAdapter()
scores = adapter.evaluate(
    questions=[...],
    responses=[...],
    contexts=[[...]],
    ground_truths=[...],
)
```

---

## 14. CLI 레퍼런스

```bash
# API 키 설정 마법사
agent-eval init

# 현재 설정 확인
agent-eval check

# FastAPI 대시보드 실행 (기본 포트 8765)
agent-eval dashboard
agent-eval dashboard --port 9000
agent-eval dashboard --watch   # 파일 변경 감시 모드

# Phoenix 모니터링 서버 기동
agent-eval monitor
agent-eval monitor --port 6006
agent-eval monitor --check     # OTEL 패키지 설치 여부 및 포트 확인

# CI/CD 품질 게이팅
agent-eval gate result.json --tcr 85 --accuracy 70
agent-eval gate result.json --tcr 85 --accuracy 70 --quality 0.7

# 골든 데이터셋 자동 추출
agent-eval dataset build results/ --min-score 0.8
agent-eval dataset build results/ --min-score 0.8 --output data/golden.json

# 버전 확인
agent-eval --version
```

---

## 공개 API 요약

`from agent_evaluator import ...`로 바로 임포트 가능한 심볼:

```python
# 핵심 클래스
PerformanceMonitor, TaskResult, TaskType, EvaluationReport,

# 하이브리드
HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport,

# 헬퍼 & 컨텍스트 매니저
create_taskresult,
evaluation_session, async_evaluation_session, hybrid_evaluation_session,

# QuickEval Facade
QuickEval,

# 멀티턴 대화
ConversationSession, ConversationMetrics, ConversationTurn,

# LLM Judge (기본 설치에 포함)
LLMJudge,

# 투명성
TestTransparencyManager, AnnotationType, TestStepStatus,

# 설정
load_env, get_settings, init_from_app,

# 고급 / 커스텀 트래커
BaseTracker, infer_privilege_level,

# 스트리밍 / 피드백 / 이상탐지 / 비용
ImplicitFeedbackTracker,
AnomalyDetector, AnomalyEvent,
CostTracker, AdaptivePolicy, SamplingStage,

# 개별 트래커
TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker,
ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
AgentCoordinationTracker, WorkflowExecutionTracker,
InputSanitizationTracker, OutputLeakageDetector,
ToolAuthorizationTracker, PrivilegeEscalationDetector, ToolChainAttackDetector,

# 알림
SimpleTaskAlertRule,

# 타입 힌트
FrameworkLiteral,   # 21개 프레임워크 Literal 타입
```

---

*Agent Evaluator v0.8.5 — [GitHub](https://github.com/bullpeng72/Agent-Evaluator) | [예제 디렉토리](../Evaluator_Examples/)*
