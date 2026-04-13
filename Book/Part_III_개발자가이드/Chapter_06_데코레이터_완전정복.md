# Chapter 6. 데코레이터 완전 정복

이 챕터에서 배우는 것: Agent-Evaluator SDK의 핵심 인터페이스인 데코레이터 시스템을 완벽하게 이해한다. 비즈니스 로직과 평가 코드를 어떻게 깔끔하게 분리하는지, 상황별로 어떤 데코레이터를 선택해야 하는지, 그리고 RAG·멀티에이전트·스트리밍 같은 실전 시나리오에서 데코레이터를 어떻게 조합하는지를 단계적으로 익힌다.

---

## 6.1 왜 데코레이터인가 — SDK 설계 철학

### 비즈니스 로직과 평가 코드의 분리

좋은 평가 프레임워크는 에이전트 코드를 최대한 건드리지 않아야 한다. 평가를 추가하기 위해 핵심 비즈니스 로직을 리팩토링하거나, 에이전트 함수마다 동일한 보일러플레이트를 반복하는 것은 유지보수 부채를 쌓는 일이다.

데코레이터 없이 에이전트 함수 하나를 평가하려면 다음과 같은 코드가 필요하다:

```python
# 데코레이터 없는 방식 — 매 함수마다 반복해야 하는 코드
import time
from datetime import datetime
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType

monitor = PerformanceMonitor("results/")

def run_and_evaluate(question: str, ground_truth: str) -> str:
    start = time.perf_counter()
    success = True
    response = ""
    errors = []

    try:
        response = my_agent(question)  # 실제 에이전트 호출
    except Exception as e:
        success = False
        errors.append(str(e))

    elapsed = time.perf_counter() - start

    result = TaskResult(
        task_id=f"task_{int(time.time())}",   # 직접 ID 생성
        task_type=TaskType.QA,
        success=success,
        completion_score=1.0 if success else 0.0,
        accuracy_score=0.0,          # 직접 계산해야 함
        execution_time=elapsed,
        tokens_used={"total": 0},    # dict 형식 필수; 프레임워크별로 직접 추출해야 함
        tool_calls=[],
        attempts=1,
        errors=errors,
        timestamp=datetime.utcnow(),
    )
    monitor.record_task(result)
    return response
```

문제는 명확하다. `execution_time` 측정을 빠뜨리면 0이 기록되고, `accuracy_score` 계산 로직을 매번 구현해야 하며, 에이전트 함수가 늘어날수록 이 코드가 기하급수적으로 증가한다.

데코레이터 방식은 이 모든 것을 한 줄로 해결한다:

```python
# 데코레이터 방식 — 비즈니스 로직만 남는다
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)  # 비즈니스 로직만
```

데코레이터가 자동으로 처리하는 항목:

| 항목 | 처리 방법 |
|------|----------|
| `execution_time` | `time.perf_counter()` 나노초 측정 |
| `success` / `completion_score` | task_type 인식 자동 계산 — `code_generation`은 AST 파싱, `tool_use`는 도구 호출 여부, 기타는 길이 기반 |
| `accuracy_score` | `ground_truth` vs 반환값 4-way 가중치 계산 |
| `task_id` | UUID 기반 자동 생성 |
| `tokens_used` | `framework=` 어댑터 또는 EvalMetadata 자동 추출 |
| `monitor.record_task()` | 측정 완료 후 자동 호출 |

---

## 6.2 에이전트 유형별 데코레이터 선택 가이드

상황에 맞는 데코레이터를 고르는 6행 결정 테이블:

| 상황 | 권장 데코레이터 | 이유 |
|------|--------------|------|
| 단일 함수, 질문 1건씩 처리 | `@agent_eval` | 가장 기본. 단일 호출 1건 = TaskResult 1개 |
| 질문 목록(list)을 한꺼번에 평가 | `@batch_eval` | 루프 없이 배치 전체 처리 + DataFrame 반환 |
| 챗봇 / 멀티턴 대화 | `@conversation_eval` | 맥락 유지율, 주제 일관성 등 대화 전용 지표 |
| 외부 콜백 등 함수에 데코레이터 못 붙일 때 | `eval_context` | 데코레이터 패턴이 불가한 상황의 탈출구 |
| 여러 에이전트에 동일 설정 반복 적용 | `EvalDecorator` | 공통 설정 1회 정의 → 모든 에이전트 자동 전파 |
| 가장 빠른 시작 / 최소 코드 | `QuickEval` | 1줄 시작, `.qa` `.rag` `.tool_use` 단축 속성 |

> 👨‍💻 **개발자 TIP**: `QuickEval`과 `EvalDecorator`는 팩토리(Factory)다. 내부적으로 `@agent_eval`, `@batch_eval`, `@conversation_eval`을 생성한다. 프레임워크 설정이나 알림 규칙을 여러 에이전트에서 공유해야 한다면 `EvalDecorator` 또는 `QuickEval`을 사용하고, 단일 에이전트에 빠르게 붙이려면 `@agent_eval`을 직접 사용한다.

---

## 6.3 @agent_eval — 단일 태스크 평가

`@agent_eval`은 단일 에이전트 함수에 평가를 삽입하는 가장 기본적인 방법이다. 동기, 비동기, 제너레이터(스트리밍) 함수를 모두 자동 감지하여 처리한다.

### 기본 사용법

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 호출 — 내부적으로 평가가 자동 실행됨
answer = my_agent("한국의 수도는?", ground_truth="서울")
```

### task_type 10종

`task_type`은 어떤 평가 지표를 활성화할지 결정한다:

| task_type | 설명 | 주요 활성 지표 |
|-----------|------|--------------|
| `"qa"` | 질의응답 | Accuracy (4-way), TCR |
| `"tool_use"` | 도구 호출 에이전트 | Tool Call Analyzer, Tool Selection F1 |
| `"information_retrieval"` | RAG / 문서 검색 | Hallucination (context 필요) |
| `"code_generation"` | 코드 생성 | AST 비교 기반 Accuracy |
| `"reasoning"` | 추론 태스크 | Multi-step chain 분석 |
| `"planning"` | 계획 수립 | Workflow Execution Tracker |
| `"data_analysis"` | 데이터 분석 | Accuracy + Quality |
| `"creative"` | 창의적 생성 | Quality 5차원 평가 |
| `"coding"` | 코딩 태스크 | AST 비교 기반 Accuracy |
| `"document_creation"` | 문서 작성 | Quality + Completeness |

### framework= 파라미터 — 21개 어댑터

`framework=` 파라미터를 지정하면 해당 SDK 응답 객체에서 토큰 수, 도구 호출 기록 등을 자동 추출한다. 이때 함수가 SDK 응답 **객체 전체**를 반환해야 한다는 점이 핵심이다:

```python
# LangChain — 응답 객체 전체 반환
@agent_eval(monitor, task_type="qa", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# OpenAI — completion 객체 전체 반환
@agent_eval(monitor, task_type="qa", framework="openai")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}]
    )

# Anthropic — Messages 객체 전체 반환
@agent_eval(monitor, task_type="qa", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": question}]
    )
```

`framework=`를 생략하면 `auto_detect_framework=True`(기본값)가 응답 객체의 속성을 분석해 프레임워크를 자동 감지한다. `response.choices + response.usage` → openai, `response.content + response.model` → anthropic 등 12개 속성 기반으로 동작한다.

### rag_mode=True — RAG 전용 자동 설정

```python
@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,    # ← 이 하나로 context_arg + hallucination 자동 활성
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(f"Context: {context}\n\nQuestion: {question}")
```

`rag_mode=True`가 자동으로 하는 일: (1) `context_arg="context"` 설정, (2) 내부적으로 hallucination 감지 활성화(데코레이터 레벨), (3) `HallucinationDetector`에 context를 전달해 일관성 점수 계산. `enable_llm_judge=True`와 함께 사용 시 `faithfulness` 차원도 자동 추가된다.

### security_mode=True — 보안 검사 임시 활성

```python
@agent_eval(monitor, task_type="qa", security_mode=True)
def risky_agent(question: str, ground_truth: str = "") -> str:
    return agent.invoke(question)
# 5종 보안 트래커 임시 활성: InputSanitization, OutputLeakage,
# ToolAuthorization, PrivilegeEscalation, ToolChainAttack
# finally 블록에서 원래 설정으로 자동 복원
```

### enable_llm_judge=True — LLM-as-Judge 채점

```python
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",  # 채점에 사용할 LLM
)
def careful_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# LLM Judge가 5차원 기본 평가: completeness, relevance, factual_consistency, toxicity, bias
# rag_mode=True 시 faithfulness 차원 자동 추가 (6차원), judge_criteria 지정 시 추가 확장
# 결과는 TaskResult.extra["llm_judge"]에 저장되어 대시보드에서 확인 가능
```

### 모든 파라미터를 활용한 완전한 예시

```python
from agent_evaluator import (
    agent_eval, PerformanceMonitor, SimpleTaskAlertRule, AlertRuleBuilder
)

monitor = PerformanceMonitor(output_dir="results/")

# 알림 규칙 정의
slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)
accuracy_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.7,
    handler=lambda msg, tr: send_slack(msg),
    cooldown=300,
)

@agent_eval(
    monitor,
    task_type="qa",
    framework="openai",           # 프레임워크 자동 메타데이터 추출
    rag_mode=False,               # RAG 모드 (기본: False)
    security_mode=False,          # 보안 검사 (기본: False)
    enable_llm_judge=True,        # LLM Judge 채점 활성
    judge_model="claude-sonnet-4-6",
    enable_anomaly_detection=True,  # 이상 탐지 활성
    sample_rate=0.5,              # 50%만 기록 (고트래픽용)
    flush_every=50,               # 50회마다 자동 저장
    flush_filename="periodic_save",
    alert_rules=[slow_alert, accuracy_alert],
    timeout=15.0,                 # 15초 초과 시 강제 중단
    max_retries=2,                # 실패 시 최대 2회 재시도
    preset="production",          # preset 시스템 적용
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}]
    )
```

---

## 6.4 @batch_eval — 대량 데이터셋 평가

질문 목록을 한 번에 평가해야 할 때 사용한다. 루프를 직접 작성하지 않고, 배치 전체를 한 번의 함수 정의로 처리한다.

### 기본 사용법

```python
from agent_evaluator import batch_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

@batch_eval(monitor, task_type="qa")
def batch_agent(questions: list, ground_truths: list = None) -> list:
    # questions 목록의 각 항목에 대해 응답 생성
    return [llm.invoke(q) for q in questions]

# 100개 케이스 배치 평가
questions = [f"질문 {i}" for i in range(100)]
ground_truths = [f"정답 {i}" for i in range(100)]
responses = batch_agent(questions=questions, ground_truths=ground_truths)
# → TaskResult 100개 자동 기록
```

### concurrent=True — 병렬 처리

```python
@batch_eval(
    monitor,
    task_type="qa",
    concurrent=True,
    max_concurrent=4,   # 최대 4개 동시 실행
)
async def concurrent_batch(questions: list, ground_truths: list = None) -> list:
    tasks = [async_llm.ainvoke(q) for q in questions]
    return await asyncio.gather(*tasks)
# 100개 질문을 4개씩 병렬 처리 → 처리 속도 약 4배 향상
```

### return_format="dataframe" — 분석용 DataFrame

```python
@batch_eval(monitor, task_type="qa", return_format="dataframe")
def batch_agent_df(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

df = batch_agent_df(questions, ground_truths)
# 컬럼: task_id, question, response, ground_truth, accuracy_score,
#        completion_score, execution_time, tokens_total, tokens_input,
#        tokens_output, framework, tool_call_count, has_error, attempts, timestamp
```

DataFrame 활용 예시:

```python
# 낮은 정확도 케이스 필터링
low_accuracy = df[df["accuracy_score"] < 0.7]
print(f"개선 필요 케이스: {len(low_accuracy)}개")

# 오류 발생 케이스 분석
error_cases = df[df["has_error"] == True]
print(f"평균 실행시간(오류): {error_cases['execution_time'].mean():.2f}초")

# 느린 케이스 식별
slow_cases = df[df["execution_time"] > 5.0]
```

### 기타 유용한 파라미터

```python
@batch_eval(
    monitor,
    task_type="qa",
    shuffle=True,                   # 처리 전 순서 무작위 섞기
    item_timeout=30.0,              # 항목당 최대 30초
    on_item_error=lambda e, q: print(f"오류: {q[:30]}... → {e}"),
    flush_every=50,                 # 50건마다 자동 저장
    flush_filename="batch_checkpoint",
    streaming_mode=True,            # 대용량 배치 메모리 절약
)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

> 📋 **QA 관리자 TIP**: `return_format="dataframe"`과 `shuffle=True`를 함께 사용하면 순서 편향 없이 랜덤 샘플의 품질 분포를 파악할 수 있다. CI 파이프라인에서 골든 데이터셋 100개를 배치로 돌리고 DataFrame 결과를 CSV로 저장하면 품질 트렌드를 추적하기 좋다.

---

## 6.5 @conversation_eval — 멀티턴 대화 평가

챗봇이나 고객 상담 에이전트처럼 여러 번의 대화가 이어지는 시나리오를 평가한다. `session_id`가 같은 호출을 하나의 세션으로 묶어 대화 전용 지표를 계산한다.

### 기본 사용법

```python
from agent_evaluator import conversation_eval, flush_conversation, PerformanceMonitor

monitor = PerformanceMonitor("results/")

@conversation_eval(
    monitor,
    session_id_arg="sid",    # session_id로 사용할 파라미터 이름
    max_turns=10,            # 최대 턴 수
)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

# 동일 sid 호출 시 턴 자동 누적
chat_agent("안녕하세요", sid="user_001")
chat_agent("오늘 날씨 어때?", sid="user_001")
chat_agent("서울 날씨 알려줘", sid="user_001")

# 세션 명시적 종료 — ConversationMetrics 계산 후 기록
flush_conversation("user_001")
```

### 8가지 대화 지표

`flush_conversation()` 또는 `max_turns` 도달 시 자동 계산되는 지표:

| 지표 | 설명 |
|------|------|
| `turn_count` | 총 대화 턴 수 |
| `overall_score` | 아래 지표들의 종합 점수 (0~1) |
| `context_retention` | 이전 대화 내용을 얼마나 기억하는가 (0~1) |
| `topic_coherence` | 대화 주제의 일관성 (0~1) |
| `progressive_depth` | 대화가 깊어지는 정도 (0~1) |
| `session_completion` | 세션 목표 달성률 (0~1) |
| `avg_turn_latency` | 평균 응답 지연 시간 (초) |
| `turn_scores` | 턴별 개별 점수 목록 |

### 고급 옵션과 챗봇 완전 예시

```python
from agent_evaluator import conversation_eval, flush_conversation, PerformanceMonitor

monitor = PerformanceMonitor("results/")

def on_turn_callback(session_id: str, user: str, response: str, metadata: dict):
    """각 턴 완료 시 호출되는 콜백 — 시그니처: (session_id, user, response, metadata)"""
    print(f"  [{session_id}] 사용자: {user[:30]}... → 응답: {response[:50]}...")

@conversation_eval(
    monitor,
    session_id_arg="session_id",
    max_turns=20,
    on_turn=on_turn_callback,
    flush_every=5,               # 5턴마다 중간 저장
    flush_filename="conv_checkpoint",
)
def customer_service_agent(
    question: str,
    session_id: str = "default"
) -> str:
    history = get_conversation_history(session_id)
    response = llm.invoke(
        f"대화 이력:\n{history}\n\n고객 질문: {question}"
    )
    save_conversation_history(session_id, question, response)
    return response

# 고객 상담 시뮬레이션
sessions = ["session_A", "session_B", "session_C"]
for sid in sessions:
    customer_service_agent("환불 정책이 어떻게 되나요?", session_id=sid)
    customer_service_agent("구매한 지 2주가 됐는데 가능한가요?", session_id=sid)
    customer_service_agent("온라인 구매도 해당되나요?", session_id=sid)
    flush_conversation(sid)

monitor.save_to_file("chatbot_eval")
```

---

## 6.6 eval_context — 데코레이터를 쓸 수 없을 때

외부 라이브러리의 콜백으로 에이전트가 실행되거나, 복잡한 조건부 로직 때문에 함수 데코레이터를 붙이기 어려울 때 사용하는 with 블록 패턴이다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import eval_context

monitor = PerformanceMonitor("results/")

# 기본 사용법
with eval_context(
    monitor,
    task_type="qa",
    question="한국의 수도는?",
    ground_truth="서울",
) as ctx:
    # 데코레이터를 붙일 수 없는 외부 함수 호출
    ctx.response = some_external_api.call("한국의 수도는?")
# 블록 종료 시 자동으로 TaskResult 생성 및 기록

# timeout 파라미터
with eval_context(monitor, task_type="qa", timeout=10.0) as ctx:
    ctx.response = slow_api.call(question)  # 10초 초과 시 TimeoutError

# chunk_step() — 스트리밍 TTFT(Time-To-First-Token) 자동 측정
with eval_context(monitor, task_type="qa") as ctx:
    for i, chunk in enumerate(streaming_api.stream(question)):
        ctx.chunk_step(chunk)    # 첫 번째 chunk에서 TTFT 자동 기록
        ctx.response = (ctx.response or "") + chunk
```

> 👨‍💻 **개발자 TIP**: LangChain의 `on_llm_end` 콜백, FastAPI 라우터 내부, 또는 서드파티 프레임워크의 이벤트 핸들러처럼 함수 시그니처를 마음대로 바꿀 수 없는 상황에서 `eval_context`가 유일한 선택지가 된다.

---

## 6.7 EvalDecorator & QuickEval — 팩토리 패턴

### EvalDecorator — 공통 설정 재사용

여러 에이전트 함수에 동일한 `framework`, `alert_rules`, `flush_every` 설정을 적용해야 할 때, `EvalDecorator` 인스턴스를 하나 만들어 공유한다:

```python
from agent_evaluator.decorators import EvalDecorator
from agent_evaluator import PerformanceMonitor, AlertRuleBuilder

monitor = PerformanceMonitor("results/")

# 공통 설정을 한 번만 정의
eval = EvalDecorator(
    monitor,
    framework="openai",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    alert_rules=[
        AlertRuleBuilder.when_accuracy_below(0.7,
            handler=lambda msg, tr: send_slack(msg))
    ],
    flush_every=20,
)

# 단축 속성으로 여러 에이전트에 적용
@eval.qa
def qa_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}])

@eval.tool_use
def tool_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

`EvalDecorator`의 단축 속성 11종: `.qa`, `.rag`, `.tool_use`, `.code`, `.reasoning`, `.planning`, `.data_analysis`, `.creative`, `.multi_agent`, `.secure`, `.streaming`

### QuickEval — 원스톱 Facade

`QuickEval`은 `PerformanceMonitor` + `EvalDecorator`를 1~2줄로 시작할 수 있게 해주는 최상위 Facade다:

```python
from agent_evaluator import QuickEval

# 기본 시작
eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 용도별 팩토리 메서드
rag_eval = QuickEval.for_rag("results/")       # hallucination_detection=True 자동
sec_eval = QuickEval.for_security("results/")  # enable_security_metrics=True 자동
judge_eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### QuickEval 전체 워크플로우

```python
from agent_evaluator import QuickEval

# 1단계: QuickEval 초기화
eval = QuickEval(
    "results/",
    auto_save=True,
    auto_save_interval=10,  # 10건마다 자동 저장
)

# 2단계: 에이전트 등록
@eval.qa
def agent_v1(question: str, ground_truth: str = "") -> str:
    return llm_v1.invoke(question)

@eval.qa
def agent_v2(question: str, ground_truth: str = "") -> str:
    return llm_v2.invoke(question)

# 3단계: 데이터셋으로 평가 실행
for question, answer in test_dataset:
    agent_v1(question, ground_truth=answer)
    agent_v2(question, ground_truth=answer)

# 4단계: 결과 저장
eval.save()   # results/quickeval.json + quickeval.html

# 5단계: 요약 확인
summary = eval.summary()
print(f"정확도: {summary['accuracy']:.1%}")
print(f"p95 지연: {summary['p95_latency']:.2f}초")
print(f"총 비용: ${summary['total_cost_usd']:.4f}")

# 6단계: CI/CD 게이팅
eval.gate(tcr=85, accuracy=70)  # 기준 미달 시 sys.exit(1)

# 7단계: 두 버전 비교
eval_a = QuickEval("results/v1/")
eval_b = QuickEval("results/v2/")
# 각각 평가 실행 후...
comparison = eval_a.compare(eval_b)
ab_result = eval_a.ab_test(eval_b)  # t-검정 p-value (scipy 설치 시)
print(f"통계적 유의성: p={ab_result.get('p_value', 'N/A')}")
```

---

## 6.8 고급 기능

### preset 시스템

자주 쓰는 설정 조합을 이름으로 지정한다:

| preset | 주요 설정 | 용도 |
|--------|-----------|------|
| `"production"` | `flush_every=50`, `sample_rate=0.1`, `enable_anomaly_detection=True` | 프로덕션 안정 운영 |
| `"development"` | `enable_llm_judge=True`, `flush_every=5`, `sample_rate=1.0` | 개발/디버깅 |
| `"testing"` | 경량 설정, 빠른 실행 | 유닛 테스트 |
| `"canary"` | 카나리 배포 최적화 | 일부 트래픽 평가 |

```python
# 프로덕션 preset
@agent_eval(monitor, task_type="qa", preset="production")
def prod_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 개발 preset — LLM Judge + 자동 프레임워크 감지
@agent_eval(monitor, task_type="qa", preset="development")
def dev_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 잘못된 preset 지정 시 경고
@agent_eval(monitor, task_type="qa", preset="PROD")  # 잘못된 이름
def agent(question: str, ground_truth: str = "") -> str: ...
# UserWarning: Unknown preset 'PROD'.
# Valid presets: ['production', 'development', 'testing', 'canary']
```

### sample_condition — 조건부 샘플링

`sample_rate`와 독립적으로 동작하는 조건 기반 샘플링:

```python
# 오류가 발생한 케이스만 기록 (디버깅용)
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kwargs: kwargs.get("ground_truth", "") != "",
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### on_record — TaskResult 후처리

`monitor.record_task()` 직전에 실행되는 콜백으로 TaskResult를 보강하거나 교체할 수 있다:

```python
import dataclasses

def add_model_info(task_result):
    """모델명과 버전 정보를 extra에 추가"""
    new_extra = {**task_result.extra, "model": "gpt-4o-mini", "version": "2.0"}
    return dataclasses.replace(task_result, extra=new_extra)

@agent_eval(monitor, task_type="qa", on_record=add_model_info)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### AlertRuleBuilder — 전체 팩토리 메서드

`AlertRuleBuilder`는 5종의 빌트인 팩토리로 자주 쓰는 알림 규칙을 간결하게 생성한다:

```python
from agent_evaluator import AlertRuleBuilder

# 정확도 임계값 알림
accuracy_rule = AlertRuleBuilder.when_accuracy_below(
    threshold=0.7,
    handler=lambda msg, tr: send_slack_alert(msg),
    cooldown=300,       # 5분 쿨다운
)

# 레이턴시 임계값 알림
latency_rule = AlertRuleBuilder.when_latency_above(
    threshold_seconds=5.0,      # 5초 초과
    handler=lambda msg, tr: page_oncall(msg),
    severity="critical",
    cooldown=60,
)

# TCR 임계값 알림
tcr_rule = AlertRuleBuilder.when_completion_below(
    threshold=0.8,
    handler=lambda msg, tr: log_to_datadog(msg),
)

# 오류 발생 알림
error_rule = AlertRuleBuilder.when_error(
    handler=lambda msg, tr: print(f"ERROR: {tr.errors}"),
    severity="critical",
)

# 도구 호출 과다 알림
tool_rule = AlertRuleBuilder.when_tool_calls_exceed(
    max_calls=10,
    handler=lambda msg, tr: log_warning(msg),
)

# 모든 규칙을 데코레이터에 적용
@agent_eval(monitor, task_type="tool_use",
            alert_rules=[accuracy_rule, latency_rule, error_rule, tool_rule])
def agent(question: str, ground_truth: str = "") -> str: ...
```

### SimpleTaskAlertRule 고급 설정

`SimpleTaskAlertRule`은 복합 조건, dry_run, 클래스 레벨 쿨다운을 지원한다:

```python
from agent_evaluator import SimpleTaskAlertRule

# 복합 조건 (accuracy 낮음 + latency 높음)
complex_rule = SimpleTaskAlertRule(
    name="high_risk_failure",
    condition=lambda tr: tr.accuracy_score < 0.5 and tr.execution_time > 3.0,
    handler=lambda msg, tr: escalate(msg, tr),
    severity="critical",
    cooldown=120,
    compound_conditions=[
        {"field": "tokens_used", "op": "gt", "value": 1000},
        {"field": "attempts", "op": "gt", "value": 1},
    ],
)

# dry_run — 핸들러 실행 없이 조건만 검사
result = complex_rule.dry_run(task_result)
print(f"조건 충족: {result}")  # True/False

# 클래스 레벨 쿨다운 (같은 이름의 모든 인스턴스 공유)
SimpleTaskAlertRule.class_level_cooldown["slow_response"] = 300
```

### agent_eval_with_retry — 재시도 + jitter

```python
from agent_evaluator import agent_eval_with_retry

@agent_eval_with_retry(
    monitor,
    task_type="qa",
    max_retries=3,
    jitter_type="full",           # "full" / "decorrelated" / "none"
    max_delay=30.0,               # 최대 대기 시간 상한 (초)
    should_retry=lambda e: isinstance(e, RateLimitError),  # 재시도 조건
)
def rate_limited_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 6.9 개발자 실전 패턴 모음

### RAG 에이전트 평가 완전 예시

```python
from agent_evaluator import QuickEval

eval = QuickEval.for_rag("results/")

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.invoke(question)
    context_text = "\n".join([d.page_content for d in docs])
    response = llm.invoke(f"Context:\n{context_text}\n\nQ: {question}")
    return response

# 평가 실행
test_data = [
    ("한국의 GDP는?", "한국의 GDP는 약 1.7조 달러이다.", "1.7조 달러"),
    ("서울 인구는?", "서울의 인구는 약 950만 명이다.", "950만 명"),
]

for question, context, answer in test_data:
    rag_agent(question, context=context, ground_truth=answer)

eval.save()
eval.gate(tcr=80, accuracy=65)
```

### 멀티에이전트 협력 평가 예시

```python
from agent_evaluator import agent_eval, PerformanceMonitor, EvalMetadata

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="tool_use", framework="crewai")
def multi_agent_task(question: str, ground_truth: str = "") -> tuple:
    result = crew.kickoff(inputs={"topic": question})

    # 멀티에이전트 교환 기록 수동 주입
    total_tokens = result.token_usage.get("total_tokens", 0) if hasattr(result, "token_usage") else 0
    metadata = EvalMetadata(
        agent_interactions=[
            {"from": "researcher", "to": "writer", "message": "research_done"},
            {"from": "writer", "to": "reviewer", "message": "draft_ready"},
        ],
        chain_steps=[
            {"name": "research", "success": True},
            {"name": "write", "success": True},
            {"name": "review", "success": True},
            {"name": "finalize", "success": True},
        ],
        tokens_used={"total": total_tokens},  # dict 형식 필수: {"input": n, "output": n, "total": n}
    )
    return result.raw, metadata

multi_agent_task("AI 트렌드 2026 보고서", ground_truth="보고서 완성")
```

### 스트리밍 에이전트 평가 예시

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = ""):
    """제너레이터 함수 — 첫 번째 yield 시점이 TTFT로 자동 기록"""
    full_response = ""
    for chunk in llm.stream(question):
        content = chunk.content if hasattr(chunk, "content") else str(chunk)
        full_response += content
        yield content  # ← 첫 yield 시점 = TTFT 자동 측정

# 스트리밍 응답 소비
for token in streaming_agent("한국의 역사를 설명해줘", ground_truth="조선 건국..."):
    print(token, end="", flush=True)
print()

# TTFT 통계 확인
ttft_stats = monitor.latency_tracker.get_ttft_stats()
print(f"평균 TTFT: {ttft_stats.get('mean', 0):.3f}초")
```

---

## 6.10 파라미터 × 지표 완전 매핑 — 종합 레퍼런스

실전에서 가장 자주 받는 질문은 "어떤 파라미터를 써야 어떤 지표가 켜지나요?"다. 이 절은 그 질문에 대한 완전한 답이다.

### 지표 × 데코레이터 지원 매트릭스

```
지표                            @agent_eval  @batch_eval  @conversation_eval
─────────────────────────────────────────────────────────────────────────────
[Layer 1 — 기반 지표]
TCR (태스크 완료율)                  ✅           ✅              ✅
Accuracy (정확도)                    ✅           ✅              ✅
Hallucination (환각 탐지)     ✅(opt-in)   ✅(opt-in)          ✅
Quality (응답 품질 5차원)             ✅           ✅              ✅
Latency (지연 시간 + TTFT)           ✅           ✅              ✅
Token Economy (토큰·비용)            ✅           ✅              ✅

[Layer 2-A — 에이전틱 지표]
Tool Call (도구 호출 패턴)            ✅           ✅              ✅
Retry/Correction (재시도)            ✅           ✅              ✅
Tool Selection F1                    ✅           ✅              ✅
Agent Coordination (멀티에이전트)     ✅           ✅              ✅
Workflow Execution                   ✅           ✅              ✅

[Layer 2-B — 보안 지표]
Input Sanitization            ✅(opt-in)   ✅(opt-in)       ✅(opt-in)
Output Leakage               ✅(opt-in)   ✅(opt-in)       ✅(opt-in)
Tool Authorization           ✅(opt-in)   ✅(opt-in)       ✅(opt-in)
Privilege Escalation         ✅(opt-in)   ✅(opt-in)       ✅(opt-in)
Tool Chain Attack            ✅(opt-in)   ✅(opt-in)       ✅(opt-in)

[Layer 3 — LLM Judge]  (enable_llm_judge=True, 기본 설치에 포함)
Completeness                  ✅(opt-in)   ✅(opt-in)          N/A
Relevance                     ✅(opt-in)   ✅(opt-in)          N/A
Factual Consistency           ✅(opt-in)   ✅(opt-in)          N/A
Toxicity                      ✅(opt-in)   ✅(opt-in)          N/A
Bias                          ✅(opt-in)   ✅(opt-in)          N/A
safety_score                  ✅(opt-in)   ✅(opt-in)          N/A
Faithfulness (RAG, v0.7.6+) ✅(rag+judge) ✅(rag+judge)       N/A
G-Eval 커스텀 (v0.7.6+)       ✅(opt-in)   ✅(opt-in)          N/A

[대화 지표]  (@conversation_eval 전용)
Turn Count                        N/A          N/A              ✅
Overall Score                     N/A          N/A              ✅
Context Retention                 N/A          N/A              ✅
Topic Coherence                   N/A          N/A              ✅
Progressive Depth                 N/A          N/A              ✅
Session Completion                N/A          N/A              ✅
Avg Turn Latency                  N/A          N/A              ✅
Turn Scores                       N/A          N/A              ✅
```

> **opt-in** = 기본 비활성. 파라미터 또는 monitor 설정으로 활성화 필요.

---

### `@agent_eval` 파라미터 → 지표 활성화 맵

| 파라미터 | 활성화되는 지표 | 비고 |
|---------|--------------|------|
| `task_type="qa"` | Accuracy (QA 모드) | 문자열·Enum 혼용 가능 |
| `task_type="tool_use"` | Tool Call + Tool Selection F1 | Tool 지표 자동 활성 |
| `task_type="information_retrieval"` | Hallucination 보조 입력 준비 | rag_mode 함께 쓸 것 |
| `rag_mode=True` | Hallucination + IR task_type 자동 | context_arg도 자동 설정; + faithfulness (enable_llm_judge 조합 시, v0.7.6+) |
| `context_arg="context"` | Hallucination 컨텍스트 공급 | rag_mode 없이도 사용 가능 |
| `security_mode=True` | 보안 5종 모두 (temp-override) | finally에서 복원 |
| `enable_llm_judge=True` | Completeness · Relevance · Factual Consistency · Toxicity · Bias · safety_score | 기본 설치에 포함, temp-override |
| `judge_model="claude-..."` | LLM Judge 모델 지정 | None이면 API 키 기반 자동 |
| `judge_criteria=[...]` | G-Eval 커스텀 기준 추가 (v0.7.6+) | criteria_scores / criteria_overall 키로 결과 |
| `enable_hallucination=True` | Hallucination 단독 (temp-override) | rag_mode보다 세밀한 제어 |
| `enable_anomaly_detection=True` | AnomalyDetector 임시 활성 | finally에서 복원 |
| `framework="langchain"` | tool_calls · chain_steps · tokens_used 자동 추출 | 21개 프레임워크 지원 |
| `score_fn=my_fn` | Accuracy 완전 대체 | (response, ground_truth) → float |
| `flush_every=N` | N회마다 save_to_file() 자동 | flush_filename으로 파일명 지정 |
| `alert_rules=[rule]` | SimpleTaskAlertRule 조건 즉시 평가 | 조건 충족 시 handler 호출 |
| `sample_rate=0.1` | 10% 태스크만 기록 | 고빈도 운영 환경 비용 절감 |

---

### 데이터 소스 우선순위 (5단계)

데코레이터가 `tool_calls`, `tokens_used`, `execution_time` 등을 채울 때 다음 우선순위로 소스를 탐색한다.

```
1순위: EvalMetadata 명시적 반환
       └─ return response, EvalMetadata(tool_calls=[...], tokens_used={"total": 1500})

2순위: eval_context 컨텍스트 매니저
       └─ with eval_context(monitor, "qa") as ctx: ctx.tokens_used = {"total": 1500}

3순위: framework= 어댑터 자동 추출
       └─ @agent_eval(monitor, framework="langchain")
          → LangChain AIMessage.usage_metadata 자동 파싱

4순위: auto_detect_framework=True (기본 활성)
       └─ 반환값 속성 12개 기반 프레임워크 자동 감지

5순위: 인수 이름 추출 (fallback)
       └─ ground_truth= 인수 자동 감지
          (ground_truth, expected, reference, answer 키워드 인식)
```

**실전 팁**: EvalMetadata를 명시적으로 반환하면 100% 정확하게 지표를 제어할 수 있다. 프레임워크 자동 감지는 편리하지만 응답 객체 구조가 변경될 경우 추출 실패 가능성이 있다.

---

### 에이전트 유형별 권장 설정

#### 1. QA 에이전트
```python
@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.ask(question)
# → Accuracy (F1+Jaccard+LCS+Char), Quality 5차원, Latency, TCR
```

#### 2. RAG 에이전트
```python
@agent_eval(monitor, rag_mode=True,
            enable_llm_judge=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.get(question)
    return llm.generate(question, docs)
# → Hallucination, Faithfulness (LLM Judge), Accuracy, Quality, Latency
```

#### 3. 도구 사용 에이전트
```python
from agent_evaluator import agent_eval, EvalMetadata

@agent_eval(monitor, task_type="tool_use", framework="langchain")
def tool_agent(question: str, ground_truth: str = "") -> str:
    result = agent_executor.invoke({"input": question})
    return result["output"]
# → Tool Call 패턴, Tool Selection F1, Retry/Correction, TCR
```

#### 4. 보안 에이전트
```python
@agent_eval(monitor, task_type="qa", security_mode=True)
def secure_agent(question: str, ground_truth: str = "") -> str:
    return agent.process(question)
# → Input Sanitization, Output Leakage, Tool Auth, Privilege Escalation, Chain Attack
```

#### 5. 멀티에이전트 시스템
```python
@agent_eval(monitor, task_type="tool_use")
def multi_agent(question: str, ground_truth: str = ""):
    result = crew.kickoff({"topic": question})
    total_tokens = result.token_usage.get("total_tokens", 0) if hasattr(result, "token_usage") else 0
    metadata = EvalMetadata(
        agent_interactions=[
            {"from": "researcher", "to": "writer", "message": "done"},
        ],
        tokens_used={"total": total_tokens},  # dict 형식 필수
    )
    return result.raw, metadata
# → Agent Coordination, Workflow Execution, Tool Call, TCR
```

#### 6. 스트리밍 에이전트 (TTFT 측정)
```python
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = ""):
    for chunk in llm.stream(question):
        yield chunk  # ← 첫 yield = TTFT 자동 기록
# → Latency + TTFT, Quality, TCR
```

#### 7. 배치 처리
```python
@batch_eval(monitor, task_type="qa",
            concurrent=True, max_concurrent=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.ask(q) for q in questions]
# → 전체 Layer 1/2 지표 + DataFrame 반환
```

#### 8. LLM Judge + G-Eval 커스텀
```python
@agent_eval(monitor, task_type="qa",
            enable_llm_judge=True,
            judge_criteria=["medical_accuracy", "citation_quality"])
def medical_agent(question: str, ground_truth: str = "") -> str:
    return medical_llm.ask(question)
# → Completeness·Relevance·Factual Consistency + criteria_scores {"medical_accuracy": 4, ...}
```

---

## 이 챕터의 핵심

- **데코레이터는 비즈니스 로직을 건드리지 않는다.** `@agent_eval(monitor, task_type="qa")`를 함수 위에 붙이는 것만으로 11개 TaskResult 필드가 자동으로 채워지고 PerformanceMonitor에 기록된다.
- **상황별 데코레이터 선택**: 단일 함수 → `@agent_eval`, 대량 배치 → `@batch_eval`, 멀티턴 → `@conversation_eval`, 데코레이터 불가 → `eval_context`, 설정 공유 → `EvalDecorator`, 빠른 시작 → `QuickEval`.
- **`rag_mode=True`, `security_mode=True`, `enable_llm_judge=True`**는 temp-override 패턴으로 동작하여 해당 호출에만 지표를 임시 활성화하고 `finally`에서 원래 상태로 복원한다.
- **`flush_every`와 `alert_rules`**는 모든 데코레이터(`@agent_eval`, `@batch_eval`, `@conversation_eval`, `EvalDecorator`)에 동일한 API로 적용된다.
- **`QuickEval.gate(tcr=85, accuracy=70)`**으로 CI/CD 파이프라인에 품질 게이트를 삽입하여 기준 미달 배포를 자동으로 차단할 수 있다.

---

## 실전 예제

이 챕터에서 다룬 `@agent_eval`, `@batch_eval`, `@conversation_eval`, `QuickEval`, `EvalMetadata`, `eval_context` 전체를 한 파일에서 실행할 수 있다.

**파일**: `Evaluator_Examples/04_decorator_quickeval.py`

**핵심 코드 (출처: `Evaluator_Examples/04_decorator_quickeval.py`)**

**섹션 2 — 커스텀 score_fn / completion_fn**

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 2
from agent_evaluator.decorators import agent_eval

def keyword_score(response: str, ground_truth: str) -> float:
    """응답에 핵심 키워드가 포함되면 가점."""
    keywords = ground_truth.lower().split()
    matches = sum(1 for kw in keywords if kw in response.lower())
    return min(1.0, matches / max(len(keywords), 1))

@agent_eval(
    monitor, task_type="qa",
    score_fn=keyword_score,                               # 정확도 계산 함수 교체
    completion_fn=lambda r, gt: 1.0 if len(r) > 10 else 0.5,  # 완료 판정 함수 교체
    task_id_prefix="score_fn",
)
def scored_agent(question: str, ground_truth: str = "") -> str:
    return "서울은 대한민국의 수도이자 최대 도시입니다. — 답변 완료"

scored_agent("한국의 수도에 대해 설명해줘", ground_truth="서울 대한민국 수도")
```

- `score_fn(response, ground_truth) -> float`를 지정하면 기본 AccuracyEvaluator(TokenF1·Jaccard·LCS) 대신 커스텀 함수로 accuracy_score를 계산한다
- `completion_fn(response, ground_truth) -> float`를 지정하면 기본 길이 기반 completion_score 대신 커스텀 완료 판정을 사용한다
- **우선순위**: EvalMetadata > score_fn > 자동 계산

**섹션 5 — max_retries + flush_every + alert_rules 조합**

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 5
from agent_evaluator import SimpleTaskAlertRule
from agent_evaluator.decorators import agent_eval

slow_alert = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=0,
)

_retry_count = {"n": 0}

@agent_eval(
    monitor, task_type="qa",
    max_retries=3,               # 최대 3회 재시도
    retry_on=(ValueError,),      # ValueError 발생 시만 재시도
    delay=0.0,                   # 재시도 간격 0초 (실제: 0.5~2.0 권장)
    flush_every=5,               # 5건마다 save_to_file() 자동 호출
    flush_filename="periodic",
    alert_rules=[slow_alert],    # 태스크 완료 후 즉시 알림 평가
    task_id_prefix="retry",
)
def flaky_agent(question: str, ground_truth: str = "") -> str:
    _retry_count["n"] += 1
    if _retry_count["n"] < 3:
        raise ValueError(f"임시 오류 (시도 {_retry_count['n']})")
    return "3번째 성공!"

result = flaky_agent("재시도 테스트", ground_truth="성공")
print(f"결과: {result}  (시도횟수: {_retry_count['n']})")
```

- `max_retries=3` + `retry_on=(ValueError,)`로 특정 예외만 재시도한다. `attempts` 필드에 실제 시도 횟수가 기록되어 RetryCorrectionTracker에 전달된다
- `flush_every=5`는 5번째 호출마다 `save_to_file(flush_filename)`을 자동 호출한다. 장시간 실행 시 데이터 유실을 방지한다
- `alert_rules=[...]`는 각 태스크 완료 후 즉시 규칙을 평가한다. `slow_alert` 조건(execution_time > 3.0)이 충족되면 handler가 호출된다

**섹션 6 — @batch_eval + return_format="dataframe"**

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 6
from agent_evaluator.decorators import batch_eval

BATCH_DATA = [
    ("TCP와 UDP의 차이점은?",  "TCP: 연결 지향, UDP: 비연결"),
    ("REST API란?",            "HTTP 기반 아키텍처 스타일"),
    ("Git rebase란?",          "커밋 히스토리 재작성"),
]

@batch_eval(
    monitor, task_type="qa",
    task_id_prefix="batch",
    return_format="dataframe",    # pandas DataFrame으로 결과 반환
    shuffle=True, shuffle_seed=42,
    flush_every=5, flush_filename="batch_periodic",
    on_batch_complete=lambda r: print(f"배치 완료: {len(r)}건"),
)
def qa_batch(questions: list, ground_truths: list = None) -> list:
    return [f"{q}에 대한 배치 응답" for q in questions]

df = qa_batch(
    questions=[q for q, _ in BATCH_DATA],
    ground_truths=[gt for _, gt in BATCH_DATA],
)
if hasattr(df, "shape"):
    print(f"DataFrame: {df.shape}")  # (3, N)
    print(df[["task_id", "accuracy_score", "execution_time"]].to_string())
```

- `return_format="dataframe"`이면 `@batch_eval`이 pandas DataFrame을 반환한다. 컬럼에 task_id, accuracy_score, execution_time, completion_score 등 모든 TaskResult 필드가 포함된다
- `shuffle=True, shuffle_seed=42`로 입력 순서를 섞어 배치 평가 편향을 줄인다
- `on_batch_complete=lambda r: ...` 콜백은 전체 배치가 완료된 후 호출된다

```bash
python 04_decorator_quickeval.py

agent-eval dashboard results/
```

**예제 구성**

| 섹션 | 다루는 기능 |
|------|-----------|
| 섹션 1 | `@agent_eval` 기본 패턴 (task_type·score_fn·completion_fn) |
| 섹션 2 | 커스텀 `score_fn` / `completion_fn` |
| 섹션 3 | `EvalMetadata` 튜플 반환 — score_fn 우선순위 실증 |
| 섹션 4 | `get_eval_ctx()` 스레드 로컬 — 데코레이터 내부에서 메타데이터 주입 |
| 섹션 5 | `max_retries` + `flush_every` + `alert_rules` 조합 |
| 섹션 6 | `@batch_eval` — `on_batch_complete` 콜백 · `DataFrame` 반환 · concurrent 배치 |
| 섹션 7 | `@conversation_eval` — 자동/수동 flush 2패턴 |
| 섹션 8 | `QuickEval` Facade — `gate()` · `summary()` · `save()` |

**실행 결과 (v0.8.0 기준)**

```
=== 섹션 3: EvalMetadata 튜플 반환 ===
  EvalMetadata(0.92) > score_fn(0.1) 우선순위 확인  반환값 타입: str

=== 섹션 6: @batch_eval 고급 ===
  DataFrame: (5, 16)  컬럼: ['task_id', 'task_type', 'success', ...]
  concurrent 배치: 3건 완료

=== 섹션 8: QuickEval Facade ===
  gate() 실패 (코드 1) — Accuracy 14.1% < 요구 30%  ← 의도적 임계값 도전
  summary(): tcr=56.2%  accuracy=14.1%

=== 최종 리포트 ===
  PerformanceMonitor 기록: 14건  TCR: 57.1%
결과 저장 완료: results/04_decorator_quickeval.json
```

> **`EvalMetadata` 우선순위 규칙**: 함수가 `(response, EvalMetadata(accuracy=0.92))` 튜플을 반환하면, `score_fn`이 지정돼 있어도 `EvalMetadata.accuracy_score`가 최종값으로 사용된다. 이 동작을 섹션 3에서 직접 확인할 수 있다.
