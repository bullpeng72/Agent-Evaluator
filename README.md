# Agent Evaluator

[![PyPI version](https://img.shields.io/pypi/v/agent-evaluator.svg)](https://pypi.org/project/agent-evaluator/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.8.2-green.svg)](https://github.com/bullpeng72/Agent-Evaluator)

**AI 에이전트 배포 준비도를 7개 Gate로 판정하는 Harness Engineering 평가 SDK**

에이전트가 "잘 동작하는가?"를 넘어 **"프로덕션에 배포할 준비가 됐는가?"** 를 묻습니다.
목표 달성(A) · 행동 무결성(B) · 신뢰성(C) · 성능 계약(D) · 보안 경계(E) · 멀티에이전트 조율(F) · 관측 가능성(G) —
**7개 Harness Gate가 에이전트의 배포 준비도를 종합 판정**합니다.

데코레이터 한 줄로 LangChain · CrewAI · AutoGen 등 **21개 프레임워크**를 자동 인식하고,
**58개 지표(25 Native Trackers + 33 Harness Config)**를 코드 수정 없이 측정합니다.

---

## Harness Engineering — 7개 Gate로 AI 에이전트 배포 준비도 판정

단순 정확도 측정이 아닌 **배포 준비도(deployment readiness)** 를 기준으로 에이전트를 평가합니다.
33개 Harness Config를 데코레이터 파라미터로 전달하면, `PerformanceMonitor`가 자동 집계해 7개 Gate의 PASS/WARN/FAIL을 판정합니다.

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig,          # Gate A — 목표 달성
    LoopDetectionConfig, StateConsistencyConfig,      # Gate B — 행동 무결성
    FaultToleranceConfig, GracefulDegradationConfig,  # Gate C — 신뢰성
    SLAConfig, EfficiencyConfig,                      # Gate D — 성능 계약
    ThreatSeverityConfig, ComplianceConfig,           # Gate E — 보안 경계
    ConsensusConfig, AgentRoleConfig,                 # Gate F — 멀티에이전트 조율
    ExplainabilityConfig, ObservabilityConfig,        # Gate G — 관측 가능성
)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa",
    instruction=InstructionConfig(required_keywords=["서울"], strict=True),
    loop_detection=LoopDetectionConfig(max_loop_count=3, loop_threshold=0.85),
    sla=SLAConfig(max_response_time=5.0, p95_threshold=3.0),
    explainability=ExplainabilityConfig(min_reasoning_steps=2),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

monitor.save_to_file("eval")   # eval.json + eval.html — Gate A–G 판정 포함
```

| Gate | 영역 | 판정 기준 | Harness Config (개수) |
|------|------|-----------|----------------------|
| **A** 🟢 | **Goal Achievement** | 지시 이행률 · 목표 정렬 · 계획 일관성 · 컨텍스트 유지 | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig **(6)** |
| **B** 🔵 | **Behavioral Integrity** | 루프 탐지 · 범위 일탈 · 도구 안전성 · 상태 일관성 · 교착 탐지 | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig **(6)** |
| **C** 🟡 | **Reliability** | 재현 가능성 · 오류 복구율 · 품질 하한 · 멱등성 | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig **(5)** |
| **D** 🔵 | **Performance Contract** | SLA 준수율 · 토큰 효율 · TTFT 변동성 · 비용 예측 가능성 | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig **(5)** |
| **E** 🔴 | **Security Boundary** | 위협 심각도 · 규정 준수 · 위협 대응 행동 | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig **(3)** |
| **F** 🟣 | **Multi-Agent Coordination** | 에이전트 간 합의율 · 정보 전파 정확도 · 역할 준수 · 충돌 해결 | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig **(4)** |
| **G** 🩵 | **Observability** | 추론 설명 가능성 · 내부 상태 추적 · 오류 진단 · 지연 원인 분석 | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig **(4)** |

각 Gate는 **25개 Native Tracker**(Layer 1 기반 지표 6개 + Layer 2 에이전틱 지표 10개 + 보안 지표 5개 + LLMJudge)로부터 원시 측정값을 받아 집계됩니다.

> 전체 실전 예제: `Evaluator_Examples/08_harness_eval.py` | 대시보드: `agent-eval dashboard`

---

## 왜 데코레이터인가?

```python
# ❌ 기존 방식 — 에이전트 코드를 직접 수정, 보일러플레이트 작성 필요
import time, uuid
from datetime import datetime

def my_agent(question, ground_truth):
    start = time.time()
    response = llm.invoke(question)
    elapsed = time.time() - start

    task = TaskResult(
        task_id=str(uuid.uuid4()), task_type="qa", success=True,
        completion_score=1.0,
        accuracy_score=compute_accuracy(response, ground_truth),  # 직접 계산
        execution_time=elapsed,                                    # 직접 측정
        tokens_used=extract_tokens(response),                      # 프레임워크마다 다름
        tool_calls=[], attempts=1, errors=[], timestamp=datetime.now(),
        question=question, response=str(response), ground_truth=ground_truth,
    )
    monitor.record_task(task)
    return response
```

```python
# ✅ 데코레이터 방식 — 한 줄 추가, 에이전트 코드 무수정
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                                   # 이 한 줄이 전부
def my_agent(question, ground_truth=""):
    return llm.invoke(question)            # 에이전트 로직 그대로 유지
```

데코레이터는 **비침습적(non-invasive)**입니다. 원본 함수의 시그니처·반환값·예외 처리가 변경되지 않으며, 측정이 끝나면 원래 반환값이 그대로 호출자에게 전달됩니다.

---

## 데코레이터 동작 원리

```
호출자
  │
  ▼
@agent_eval / @batch_eval / @conversation_eval
  │
  ├─ [1] 실행 시간 측정 시작
  ├─ [2] 원본 함수 실행
  ├─ [3] 프레임워크 어댑터 적용   ← tool_calls · chain_steps · tokens_used 자동 추출
  ├─ [4] EvalMetadata 병합        ← 함수가 (response, EvalMetadata(...)) 반환 시
  ├─ [5] TaskResult 자동 구성     ← 24개 필드 완성
  ├─ [6] PerformanceMonitor.record_task() 호출
  │       ├─ Layer 1: TCR · Accuracy · Hallucination · Quality · Latency · Token
  │       ├─ Layer 2: Tool · Retry · Coordination · Workflow · Security (5종)
  │       ├─ Layer 3: LLMJudge · DeepEval · Ragas  (opt-in)
  │       └─ Harness: 33개 Config 자동 집계 → Gate A–G 통과/경고/실패 판정
  │
  └─ [7] 원본 반환값 그대로 호출자에게 전달
```

---

## 설치

```bash
# 기본 설치 — LLMJudge · 대시보드 · OTEL 모니터링 · PDF 포함 (sdk 기본 내장)
pip install agent-evaluator

# ── Evaluator_Examples/ 예제 실행 ─────────────────────────────────────────
pip install "agent-evaluator[examples]"           # 모든 예제 실행 가능 (기본 + eval)

# ── 프레임워크 확장 (사용자 에이전트 코드가 필요로 하는 경우) ──────────────
# agent-evaluator 자체는 아래 패키지 없이도 완전히 동작 (duck typing 방식)
pip install "agent-evaluator[eval]"               # DeepEval ≥3.0 + Ragas ≥0.4 (외부 평가)
pip install "agent-evaluator[langchain]"          # LangChain ≥1.0 / LangGraph ≥1.0
pip install "agent-evaluator[dspy]"               # DSPy ≥2.0
pip install "agent-evaluator[pydanticai]"         # PydanticAI ≥1.0
pip install "agent-evaluator[crewai]"             # CrewAI ≥1.0 (무거움 — 전이 의존성 100개+)
pip install "agent-evaluator[autogen]"            # AutoGen ≥0.3 (무거움)

# ── 조합 편의 ──────────────────────────────────────────────────────────────
pip install "agent-evaluator[full]"               # 전체 (⚠️ crewai/autogen 포함, 10분+ 소요)
```

---

## 3가지 데코레이터

Agent Evaluator의 평가 인터페이스는 호출 패턴에 따라 정확히 **3종**으로 구성됩니다.

| 데코레이터 | 호출 패턴 | 사용 시나리오 |
|-----------|---------|-------------|
| `@agent_eval` | 함수 1회 호출 = TaskResult 1건 | 단일 QA · 도구 호출 · RAG · 보안 검사 |
| `@batch_eval` | 함수 1회 호출 = TaskResult N건 | 데이터셋 일괄 평가 · 벤치마크 |
| `@conversation_eval` | 함수 N회 호출 = TaskResult 1건 | 멀티턴 대화 · 챗봇 세션 |

---

### 데코레이터 1: `@agent_eval`

**1번 호출 → 1개 TaskResult**. 동기·비동기·제너레이터·재시도를 모두 지원합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval, RetryConfig, SecurityConfig, LLMJudgeConfig

monitor = PerformanceMonitor("results/")

# 기본 — QA 평가
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 비동기 함수 — 동일한 데코레이터 사용
@agent_eval(monitor, task_type="qa")
async def async_agent(question: str, ground_truth: str = "") -> str:
    return await async_llm.invoke(question)

# 재시도 내장 — RetryConfig 로 재시도 정책 구성, attempts 필드 자동 기록
@agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3, delay=1.0, backoff=2.0))
def robust_agent(question: str, ground_truth: str = "") -> str:
    return unreliable_llm.invoke(question)

# RAG 에이전트 — rag_mode=True 하나로 context + hallucination 자동 활성
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return retrieval_llm.invoke(question, context)

# 보안 검사 — security=SecurityConfig() 로 5개 보안 트래커 임시 활성
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# LLM 프레임워크 어댑터 — tool_calls · tokens_used 자동 추출
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return executor.invoke({"input": question})
```

**`@agent_eval` 주요 파라미터**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `task_type` | `"qa"` | 태스크 유형 (qa · tool_use · information_retrieval · code_generation 등) |
| `framework` | `"native"` | 프레임워크 어댑터 (21종 지원) |
| `question_arg` | `"question"` | 질문 인자명 |
| `ground_truth_arg` | `"ground_truth"` | 정답 인자명 |
| `context_arg` | `None` | RAG 컨텍스트 인자명 |
| `expected_tools_arg` | `None` | 기대 툴 목록 인자명 (Tool Selection F1 자동 계산) |
| `score_fn` | `None` | 커스텀 정확도 계산 함수 `(response, gt) → float` |
| `rag_mode` | `False` | context_arg + hallucination 자동 활성 단축 설정 |
| `retry` | `None` | `RetryConfig` 인스턴스 — 재시도 정책 (max · delay · backoff · jitter_type 등) |
| `security` | `None` | `SecurityConfig` 인스턴스 — 보안 지표 이 호출에만 임시 활성 |
| `llm_judge` | `None` | `LLMJudgeConfig` 인스턴스 — LLM Judge 이 호출에만 임시 활성 |
| `enable_hallucination_detection` | `False` | Hallucination Detection 이 호출에만 임시 활성 |
| `enable_anomaly_detection` | `False` | AnomalyDetector 이 호출에만 임시 활성 |
| `timeout` | `None` | 최대 실행 시간(초) |
| `sample_rate` | `1.0` | 기록 샘플링 비율 |
| `on_record` | `None` | 기록 직전 콜백 (TaskResult 교체 가능) |
| `alert_rules` | `[]` | 조건부 알림 규칙 목록 |
| `flush_every` | `0` | N건마다 자동 `save_to_file()` |
| `preset` | `None` | 사전 정의 설정 묶음 |

---

### 데코레이터 2: `@batch_eval`

**1번 호출 → N개 TaskResult**. 질문 리스트를 받아 건별로 독립된 평가 레코드를 생성합니다.

```python
from agent_evaluator.decorators import batch_eval

# 기본 — 리스트 입력, 리스트 반환
@batch_eval(monitor, task_type="qa")
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

# DataFrame 반환 — accuracy_score · execution_time · tokens_total 등 포함
@batch_eval(monitor, task_type="qa", return_format="dataframe")
def batch_agent_df(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

# 병렬 실행 (async 함수) — asyncio.gather 기반
@batch_eval(monitor, task_type="qa", concurrent=True, max_concurrent=4)
async def parallel_agent(questions: list, ground_truths: list = None) -> list:
    return await asyncio.gather(*[async_llm.invoke(q) for q in questions])

# 진행률 콜백 — 대규모 배치 모니터링
@batch_eval(
    monitor,
    task_type="qa",
    return_format="tuple",                              # (responses, task_results) 반환
    on_batch_progress=lambda done, total: print(f"{done}/{total}"),
    flush_every=100,                                    # 100건마다 중간 저장
)
def large_batch(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

responses, task_results = large_batch(questions, ground_truths)
```

**`@batch_eval` 주요 파라미터**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `questions_arg` | `"questions"` | 질문 리스트 인자명 |
| `ground_truths_arg` | `"ground_truths"` | 정답 리스트 인자명 |
| `return_format` | `"list"` | 반환 형식: `"list"` · `"tuple"` · `"dataframe"` |
| `concurrent` | `False` | async 함수 항목별 병렬 실행 |
| `max_concurrent` | `0` | 병렬 상한 (0 = 무제한) |
| `shuffle` | `False` | 처리 순서 무작위화 |
| `item_timeout` | `None` | 항목별 최대 처리 시간(초) |
| `on_batch_progress` | `None` | 진행률 콜백 `(completed, total) → None` |
| `on_batch_complete` | `None` | 배치 완료 콜백 `(results) → None` |
| `on_item_error` | `None` | 항목 실패 콜백 `(index, question, error) → None` |
| `streaming_mode` | `False` | 메모리 효율적 스트리밍 처리 |

---

### 데코레이터 3: `@conversation_eval`

**N번 호출 → 1개 TaskResult**. 동일 `session_id`로 반복 호출하면 내부에서 턴을 누적하다가 `max_turns` 도달 또는 `flush_conversation()` 호출 시 세션을 종료하고 지표를 계산합니다.

```python
from agent_evaluator.decorators import conversation_eval

# 기본 — session_id별 자동 누적, max_turns 도달 시 자동 flush
@conversation_eval(monitor, session_id_arg="session_id", max_turns=5)
def chat(question: str, session_id: str = "default") -> str:
    return llm.invoke(question)

# 사용 — 동일 session_id로 반복 호출
chat("파이썬 비동기 처리 방법 알려줘", session_id="conv_001")
chat("방금 설명한 방법의 단점은?",      session_id="conv_001")
chat("asyncio.gather 예시 코드 보여줘", session_id="conv_001")
# → 5턴 도달 시 자동 flush: context_retention · topic_coherence · progressive_depth 계산

# 수동 flush — 원하는 시점에 세션 종료
from agent_evaluator.decorators import flush_conversation
flush_conversation("conv_001")

# 턴별 콜백 + 세션 스코어 함수
@conversation_eval(
    monitor,
    max_turns=10,
    on_turn=lambda sid, user, resp, meta: print(f"[{sid}] {user[:20]}…"),
    session_score_fn=lambda metrics: metrics.overall_score * 100,
    flush_every=3,                    # 세션 3개마다 save_to_file() 자동 호출
)
def advanced_chat(question: str, session_id: str = "s1") -> str:
    return llm.invoke(question)
```

`@conversation_eval`이 측정하는 지표:

| 지표 | 설명 |
|------|------|
| `turn_count` | 누적 대화 턴 수 |
| `overall_score` | 세션 종합 점수 (0–1) |
| `context_retention` | 이전 턴 맥락이 후속 응답에 반영된 정도 |
| `topic_coherence` | 대화 전반의 주제 일관성 |
| `progressive_depth` | 대화가 심화될수록 정보 밀도가 높아지는 정도 |
| `session_completion` | 목표 대화 완성도 |
| `avg_turn_latency` | 턴별 평균 응답 시간 |
| `turn_scores` | 턴별 품질 점수 (Optional) |

**`@conversation_eval` 주요 파라미터**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `session_id_arg` | `"session_id"` | 세션 ID 인자명 |
| `user_arg` | `"question"` | 사용자 메시지 인자명 |
| `max_turns` | `None` | 최대 턴 수 (도달 시 자동 flush) |
| `max_turns_exceeded_action` | `"flush"` | 초과 시 동작: `"flush"` · `"warn"` · `"error"` |
| `flush_on_error` | `True` | 예외 발생 시 세션 자동 flush |
| `on_turn` | `None` | 턴 완료 콜백 `(sid, user, response, meta) → None` |
| `on_flush` | `None` | 세션 종료 콜백 `(metrics, session_id) → None` |
| `session_score_fn` | `None` | 세션 종합 점수 함수 `(ConversationMetrics) → float` |
| `turn_score_fn` | `None` | 턴별 점수 함수 `(user, response, meta) → float` |
| `load_previous_session` | `False` | 이전 세션 이어받기 |
| `max_session_seconds` | `None` | 비활성 세션 자동 flush 타이머(초) |

---

## EvalDecorator — 3종 통합 팩토리

공통 설정(monitor, framework, model_name 등)을 **한 번만 정의**하고 3종 데코레이터 모두에 재사용합니다.

```python
from agent_evaluator.decorators import EvalDecorator

# 공통 설정 한 번 정의
dec = EvalDecorator(
    monitor,
    framework="langchain",
    model_name="gpt-4o-mini",
    flush_every=10,
    alert_rules=[slow_rule, error_rule],
)

# ── agent_eval 계열 ──────────────────────────────────
@dec(task_type="qa")                                   # agent_eval 직접 호출
def qa_agent(question, ground_truth=""): ...

@dec.with_retry(task_type="qa", retry=RetryConfig(max=3))  # 재시도 포함
def robust_agent(question, ground_truth=""): ...

# ── batch_eval ───────────────────────────────────────
@dec.batch(task_type="qa", return_format="dataframe")
def batch_agent(questions, ground_truths=None): ...

# ── conversation_eval ────────────────────────────────
@dec.conversation(session_id_arg="sid", max_turns=5)
def chat(question, sid="s1"): ...

# ── task_type 단축 속성 (QuickEval과 동일한 API) ─────
@dec.qa             # task_type="qa"
@dec.tool_use       # task_type="tool_use"
@dec.rag            # task_type="information_retrieval" + rag_mode=True
@dec.code           # task_type="code_generation"
@dec.reasoning      # task_type="reasoning"
@dec.secure         # task_type="qa" + security=SecurityConfig()
```

---

## QuickEval — 1줄 시작 Facade

`PerformanceMonitor` + `EvalDecorator`를 1줄로 구성하는 원스톱 진입점입니다.

```python
from agent_evaluator import QuickEval

# 기본 초기화
eval = QuickEval("results/")

# 용도별 팩토리 — 관련 옵션 자동 설정
eval = QuickEval.for_rag("results/")               # hallucination_detection=True 기본 활성
eval = QuickEval.for_security("results/")          # enable_security_metrics=True 기본 활성
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 데코레이터 단축 속성 11종
@eval.qa            @eval.tool_use      @eval.rag
@eval.code          @eval.reasoning     @eval.planning
@eval.data_analysis @eval.creative      @eval.multi_agent
@eval.secure        @eval.streaming

# 배치 · 대화 데코레이터도 동일 인터페이스
@eval.batch(task_type="qa", return_format="dataframe")
def batch_agent(questions, ground_truths=None): ...

@eval.conversation(session_id_arg="sid", max_turns=5)
def chat(question, sid="s1"): ...

# 결과 저장 · 게이팅
eval.save()                                        # results/*.json + *.html
eval.gate(tcr=85, accuracy=70, hallucination=5)    # CI/CD 게이트
eval.summary()                                     # 주요 지표 요약 출력
eval.export_to_dataframe()                         # pd.DataFrame 반환
```

---

## eval_context — 데코레이터 불가 시 탈출구

외부 라이브러리 함수, lambda, 동적 호출 등 **데코레이터를 붙일 수 없는 코드**에서 사용합니다. `@agent_eval`과 동일한 평가를 수행합니다.

```python
from agent_evaluator.decorators import eval_context, get_eval_ctx

# 기본 — with 블록 종료 시 자동 record_task()
with eval_context(monitor, task_type="qa",
                  question="한국의 수도는?", ground_truth="서울") as ctx:
    ctx.response = external_lib.call("한국의 수도는?")

# get_eval_ctx() 로 추가 메타데이터 주입
with eval_context(monitor, task_type="tool_use", question=q) as ctx:
    result = external_agent.run(q)
    ctx.response = result["output"]
    ec = get_eval_ctx()
    if ec:
        ec.framework = "langchain"
        ec.chain_steps = parse_steps(result)

# 비동기
async with eval_context(monitor, task_type="qa", question=q) as ctx:
    ctx.response = await async_external.call(q)
```

---

## EvalMetadata — 추가 메타데이터 주입

3종 데코레이터 모두에서 사용 가능합니다. 반환값을 `(response, EvalMetadata(...))` 튜플로 바꾸면 자동 추출 결과를 덮어쓸 수 있습니다.

```python
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def agent(question, ground_truth=""):
    response = llm.invoke(question)
    return response, EvalMetadata(
        accuracy_score=0.95,                        # 커스텀 점수 직접 지정
        tool_calls=["search", "calculator"],        # 툴 호출 목록
        tokens_used={"input": 120, "output": 80},
        chain_steps=["search", "parse", "answer"],
        agent_interactions=[("planner", "executor", "task_complete")],
    )
```

`@conversation_eval`에서는 `TurnMetadata`를 사용합니다.

```python
from agent_evaluator.decorators import TurnMetadata

@conversation_eval(monitor, max_turns=5)
def chat(question: str, session_id: str = "s1") -> str:
    response = llm.invoke(question)
    return response, TurnMetadata(
        model="gpt-4o-mini",
        tokens={"input": 50, "output": 30},
        tool_calls=["search"],
    )
```

---

## 21개 프레임워크 자동 인식

`framework=` 파라미터 하나로 응답 객체에서 `tool_calls`, `chain_steps`, `tokens_used` 등을 자동 추출합니다.
3종 데코레이터 모두 동일한 `framework=` 파라미터를 지원합니다.

```python
# 명시적 지정 — IDE 자동완성 지원 (FrameworkLiteral 타입 힌트)
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question, ground_truth=""): ...

# 자동 감지 (기본 활성 — auto_detect_framework=True)
@agent_eval(monitor, task_type="qa")
def auto_agent(question, ground_truth=""): ...

# batch_eval · conversation_eval에도 동일하게 적용
@batch_eval(monitor, task_type="qa", framework="openai")
def batch_agent(questions, ground_truths=None): ...

@conversation_eval(monitor, max_turns=5, framework="anthropic")
def chat(question, session_id="s1"): ...

# 프레임워크 어댑터 정보 조회
from agent_evaluator.decorators import get_framework_info
info = get_framework_info("langchain")
# → {"name": "LangChain", "extras": "langchain",
#    "extracts": ["tool_calls", "chain_steps"], "async_supported": True, ...}
```

### 어댑터 전체 목록

> **참고**: `framework=` 파라미터와 어댑터는 **duck typing** 방식으로 동작 — agent-evaluator 자체는 해당 프레임워크 패키지 없이도 완전히 동작한다. "필요 extras" 열은 **사용자의 에이전트 코드**가 해당 프레임워크를 import할 때 필요한 패키지다.

| 식별자 | 이름 | 필요 extras | 자동 추출 필드 | async |
|--------|------|------------|--------------|-------|
| `langchain` | LangChain | `[langchain]`¹ | `tool_calls` · `chain_steps` | ✅ |
| `langgraph` | LangGraph | `[langchain]`¹ | `state_transitions` · `graph_traversal` · `tool_calls` · `chain_steps` | ✅ |
| `crewai` | CrewAI | `[crewai]`¹ | `agent_interactions` | ❌ |
| `autogen` | AutoGen | `[autogen]`¹ | `conversation_turns` · `tokens_used` | ✅ |
| `dspy` | DSPy | `[dspy]` | `chain_steps` · `tokens_used` | ❌ |
| `pydanticai` | PydanticAI | `[pydanticai]` | `chain_steps` · `tokens_used` | ✅ |
| `anthropic` | Anthropic | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `openai` | OpenAI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `gemini` | Google Gemini | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `vertexai` | Vertex AI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `cohere` | Cohere | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `groq` | Groq | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `mistral` | Mistral AI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `bedrock` | AWS Bedrock | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `ollama` | Ollama | `[llm]` | `tool_calls` · `tokens_used` | ❌ |
| `llamaindex` | LlamaIndex | `[llm]` | `chain_steps` | ✅ |
| `haystack` | Haystack | `[llm]` | `chain_steps` | ✅ |
| `semantic_kernel` | Semantic Kernel | `[llm]` | `chain_steps` · `tokens_used` | ✅ |
| `smolagents` | HuggingFace smolagents | `[llm]` | `tool_calls` · `chain_steps` | ❌ |
| `vllm` | vLLM | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `huggingface` | HuggingFace | `[llm]` | `chain_steps` · `tool_calls` | ❌ |

¹ **사용자 프레임워크 extras** — agent-evaluator 자체는 이 패키지 없이 동작. `@agent_eval(framework="langchain")` 데코레이터는 duck typing으로 작동하므로 agent-evaluator 설치 시에는 불필요. 사용자의 에이전트 코드가 해당 프레임워크를 직접 import할 때만 설치.

---

### 오케스트레이션 프레임워크

#### LangChain

`AgentExecutor.invoke()` 결과의 `intermediate_steps`에서 툴 호출과 체인 단계를 자동 추출합니다.

```python
from langchain.agents import AgentExecutor
from agent_evaluator.decorators import agent_eval

# intermediate_steps → tool_calls + chain_steps 자동 변환
# usage_metadata / response_metadata.token_usage → tokens_used 자동 추출
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    result = agent_executor.invoke({"input": question})
    return result  # dict 그대로 반환 — "output" 키에서 텍스트 자동 추출

# 프레임워크 전용 별칭 (agent_evaluator.integrations)
from agent_evaluator.integrations import langchain_eval

@langchain_eval(monitor, task_type="tool_use")
def lc_agent2(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
```

#### LangGraph

그래프 실행 결과의 `messages` 배열에서 상태 전이·그래프 경로·툴 호출을 추출합니다.
`__metadata__` 키가 있으면 그래프 메타데이터도 자동 수집합니다.

```python
from langgraph.graph import StateGraph
from agent_evaluator.decorators import agent_eval

# messages → state_transitions + graph_traversal
# ToolMessage / AIMessage → chain_steps + 타임스탬프 기반 실행 시간
@agent_eval(monitor, task_type="tool_use", framework="langgraph")
def lg_agent(question: str, ground_truth: str = "") -> str:
    result = graph.invoke({"messages": [("user", question)]})
    return result  # "messages"[-1].content 자동 추출

from agent_evaluator.integrations import langgraph_eval

@langgraph_eval(monitor, task_type="tool_use")
def lg_agent2(question: str, ground_truth: str = "") -> str:
    return graph.invoke({"messages": [("user", question)]})
```

#### CrewAI

`Crew.kickoff()` 결과의 `tasks_output`에서 에이전트 간 상호작용을 추출합니다.
`output_pydantic` / `output_format` (v2.x) 필드를 지원합니다.

```python
from crewai import Crew, Agent, Task
from agent_evaluator.decorators import agent_eval

# tasks_output → agent_interactions 자동 변환
# 주의: CrewAI는 async 미지원 — 동기 함수로만 사용
@agent_eval(monitor, task_type="tool_use", framework="crewai")
def crew_agent(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return str(result)

from agent_evaluator.integrations import crewai_eval

@crewai_eval(monitor, task_type="tool_use")
def crew_agent2(question: str, ground_truth: str = "") -> str:
    return str(crew.kickoff(inputs={"topic": question}))
```

#### AutoGen

`chat_result.messages` / `chat_history`에서 대화 턴과 비용 정보를 추출합니다.
AutoGen 0.4+ async API는 `autogen_eval_async` 전용 데코레이터를 사용합니다.

```python
from autogen import ConversableAgent
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import autogen_eval, autogen_eval_async

# messages/chat_history → conversation_turns
# cost/usage_summary → tokens_used
@agent_eval(monitor, task_type="qa", framework="autogen")
def autogen_agent(question: str, ground_truth: str = "") -> str:
    result = assistant.initiate_chat(user_proxy, message=question, max_turns=3)
    return result.summary

# AutoGen 0.4+ async API 전용
@autogen_eval_async(monitor, task_type="qa")
async def autogen_agent_async(question: str, ground_truth: str = "") -> str:
    result = await team.run(task=question)
    return result.messages[-1].content
```

---

### LLM 공급자

#### OpenAI

`ChatCompletion` 응답의 `choices[0].message.tool_calls`와 `usage.total_tokens`를 자동 추출합니다.
Assistants API의 `required_action`도 지원합니다.

```python
import openai
from agent_evaluator.decorators import agent_eval

client = openai.OpenAI()

@agent_eval(monitor, task_type="tool_use", framework="openai")
def gpt_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )  # ChatCompletion 객체 그대로 반환 — choices[0].message.content 자동 추출
```

#### Anthropic

`Message` 응답의 `content[].tool_use`와 `usage.input_tokens/output_tokens`를 추출합니다.
캐시 토큰(`cache_creation_input_tokens`, `cache_read_input_tokens`, SDK ≥0.29)도 지원합니다.

```python
import anthropic
from agent_evaluator.decorators import agent_eval

client = anthropic.Anthropic()

@agent_eval(monitor, task_type="tool_use", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )  # Message 객체 그대로 반환 — content[0].text 자동 추출
```

#### Google Gemini / Vertex AI

`GenerateContentResponse`의 `candidates[0].content.parts[].function_call`과 `usage_metadata`를 추출합니다.

```python
import google.generativeai as genai
from agent_evaluator.decorators import agent_eval

model = genai.GenerativeModel("gemini-1.5-flash")

@agent_eval(monitor, task_type="tool_use", framework="gemini")
def gemini_agent(question: str, ground_truth: str = "") -> str:
    return model.generate_content(question)  # GenerateContentResponse 그대로 반환

# Vertex AI는 동일한 응답 구조 — framework="vertexai"
@agent_eval(monitor, task_type="tool_use", framework="vertexai")
def vertex_agent(question: str, ground_truth: str = "") -> str:
    return vertex_model.generate_content(question)
```

#### Cohere

`NonStreamedChatResponse`의 `tool_calls`와 `meta.tokens`를 추출합니다.
스트리밍 응답(`finish_reason` 속성)도 자동 감지합니다.

```python
import cohere
from agent_evaluator.decorators import agent_eval

co = cohere.Client()

@agent_eval(monitor, task_type="tool_use", framework="cohere")
def cohere_agent(question: str, ground_truth: str = "") -> str:
    return co.chat(message=question, tools=[...])
```

#### Groq

OpenAI 호환 API 구조 — `tool_calls`와 `usage`를 추출합니다.
캐시 토큰(`cache_creation_input_tokens`, `cache_read_input_tokens`, v0.9+)도 지원합니다.

```python
from groq import Groq
from agent_evaluator.decorators import agent_eval

client = Groq()

@agent_eval(monitor, task_type="tool_use", framework="groq")
def groq_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": question}],
    )
```

#### Mistral AI

`ChatCompletionResponse`의 `tool_calls`와 `usage`를 추출합니다.
구버전 `function_call` 필드도 지원합니다.

```python
from mistralai import Mistral
from agent_evaluator.decorators import agent_eval

client = Mistral()

@agent_eval(monitor, task_type="tool_use", framework="mistral")
def mistral_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": question}],
    )
```

#### AWS Bedrock

Bedrock Converse API 응답에서 `model_id` 기반으로 Titan / Mistral on Bedrock / Claude 응답을 분기 처리합니다.

```python
import boto3
from agent_evaluator.decorators import agent_eval

client = boto3.client("bedrock-runtime", region_name="us-east-1")

@agent_eval(monitor, task_type="tool_use", framework="bedrock")
def bedrock_agent(question: str, ground_truth: str = "") -> str:
    return client.converse(
        modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
        messages=[{"role": "user", "content": [{"text": question}]}],
    )
```

#### Ollama

`ollama.chat()` / `ollama.generate()` 응답의 `tool_calls`와 `prompt_eval_count` / `eval_count`를 추출합니다.
주의: Ollama는 async 미지원입니다.

```python
import ollama
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa", framework="ollama")
def ollama_agent(question: str, ground_truth: str = "") -> str:
    return ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": question}],
    )
```

---

### AI 프레임워크

#### DSPy

`dspy.Prediction`의 `_completions` 속성에서 체인 단계를 추출합니다.
LM history 전체 multi-step도 지원합니다. 주의: DSPy는 async 미지원입니다.

```python
import dspy
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import dspy_eval

lm = dspy.LM("openai/gpt-4o-mini")
dspy.configure(lm=lm)

@agent_eval(monitor, task_type="qa", framework="dspy")
def dspy_agent(question: str, ground_truth: str = "") -> str:
    predictor = dspy.Predict("question -> answer")
    return predictor(question=question)  # Prediction 객체 → .answer 자동 추출

@dspy_eval(monitor, task_type="qa")
def dspy_agent2(question: str, ground_truth: str = "") -> str:
    return dspy.ChainOfThought("question -> answer")(question=question)
```

#### PydanticAI

`RunResult.all_messages()` (우선) 또는 `.messages` (fallback)에서 체인 단계를 추출합니다.
`ToolCallPart` / `ToolReturnPart` / `TextPart`를 세분화해 추출합니다.

```python
from pydantic_ai import Agent
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import pydanticai_eval

agent = Agent("openai:gpt-4o-mini", system_prompt="...")

@agent_eval(monitor, task_type="qa", framework="pydanticai")
async def pydantic_agent(question: str, ground_truth: str = "") -> str:
    result = await agent.run(question)
    return result  # RunResult 객체 → .data 자동 추출

@pydanticai_eval(monitor, task_type="qa")
async def pydantic_agent2(question: str, ground_truth: str = "") -> str:
    return await agent.run(question)
```

#### LlamaIndex

`Response.source_nodes`에서 체인 단계를 추출합니다.
`AgentChatResponse.sources`의 `ToolOutput`도 지원합니다.

```python
from llama_index.core import VectorStoreIndex
from agent_evaluator.decorators import agent_eval

index = VectorStoreIndex.from_documents([...])
query_engine = index.as_query_engine()

# source_nodes → chain_steps (score + metadata 포함)
@agent_eval(monitor, task_type="information_retrieval", framework="llamaindex", rag_mode=True)
def llamaindex_agent(question: str, ground_truth: str = "") -> str:
    return query_engine.query(question)
```

#### Haystack

파이프라인 컴포넌트 출력 dict에서 retriever / generator / reader / embedder / ranker를 `chain_steps`로 추출합니다.

```python
from haystack import Pipeline
from agent_evaluator.decorators import agent_eval

pipeline = Pipeline()
# ... 컴포넌트 추가 ...

# 컴포넌트 출력 dict → chain_steps
@agent_eval(monitor, task_type="information_retrieval", framework="haystack", rag_mode=True)
def haystack_agent(question: str, ground_truth: str = "") -> str:
    return pipeline.run({"query": question})
```

#### Semantic Kernel

`inner_content`에서 OpenAI / Anthropic 백엔드 토큰을 자동 추출합니다.
`function_name` + `plugin_name` → `"Plugin.function"` 형식 툴 호출도 지원합니다.

```python
import semantic_kernel as sk
from agent_evaluator.decorators import agent_eval

kernel = sk.Kernel()

# inner_content → tokens_used (OpenAI/Anthropic 백엔드 자동 감지)
@agent_eval(monitor, task_type="tool_use", framework="semantic_kernel")
async def sk_agent(question: str, ground_truth: str = "") -> str:
    result = await kernel.invoke(plugin_name, function_name, input=question)
    return str(result)
```

#### HuggingFace smolagents

`ToolCall` 스텝 목록에서 성공/실패 여부와 입력값을 정규화해 `tool_calls` + `chain_steps`로 추출합니다.
주의: smolagents는 async 미지원입니다.

```python
from smolagents import CodeAgent, HfApiModel
from agent_evaluator.decorators import agent_eval

model = HfApiModel()
agent = CodeAgent(tools=[...], model=model)

@agent_eval(monitor, task_type="tool_use", framework="smolagents")
def smol_agent(question: str, ground_truth: str = "") -> str:
    return agent.run(question)
```

#### vLLM

OpenAI 호환 API — `choices[0].message.tool_calls`와 `usage.total_tokens`를 추출합니다.

```python
from openai import OpenAI  # vLLM은 OpenAI 호환 클라이언트 사용
from agent_evaluator.decorators import agent_eval

client = OpenAI(base_url="http://localhost:8000/v1", api_key="vllm")

@agent_eval(monitor, task_type="qa", framework="vllm")
def vllm_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="meta-llama/Llama-3.2-3B-Instruct",
        messages=[{"role": "user", "content": question}],
    )
```

#### HuggingFace

`pipeline()` 결과의 `generated_text`에서 체인 단계를, `actions` / `tool_calls` 필드에서 툴 호출을 추출합니다.
주의: HuggingFace는 async 미지원입니다.

```python
from transformers import pipeline
from agent_evaluator.decorators import agent_eval

pipe = pipeline("text-generation", model="Qwen/Qwen2.5-1.5B-Instruct")

@agent_eval(monitor, task_type="qa", framework="huggingface")
def hf_agent(question: str, ground_truth: str = "") -> str:
    return pipe(question, max_new_tokens=200)
```

---

### 자동 감지 (`auto_detect_framework=True`)

`auto_detect_framework=True`(기본값)이면 반환 객체의 속성을 검사해 프레임워크를 자동 판별합니다.

| 감지 조건 | 판별 프레임워크 |
|---------|--------------|
| `stop_reason` 속성 존재 (choices 없음) | `anthropic` |
| `choices` + `usage` 속성 존재 | `openai` |
| `candidates` + `usage_metadata` 속성 존재 | `gemini` |
| `meta.tokens` 속성 존재 (choices 없음) | `cohere` |
| `x_groq` 속성 존재 | `groq` |
| `choices[0].finish_reason` == `"stop"` + mistral 힌트 | `mistral` |
| `ResponseMetadata` + `bedrock` 힌트 | `bedrock` |
| `step_results` 속성 존재 | `smolagents` |
| `completions` 속성 + DSPy 타입명 | `dspy` |
| `all_messages` callable 존재 | `pydanticai` |

```python
# framework= 생략 → 자동 감지 (기본값)
@agent_eval(monitor, task_type="qa")
def auto_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # OpenAI → 자동 "openai" 판별

# 자동 감지 명시적 비활성화 (framework= 고정 우선)
@agent_eval(monitor, task_type="qa", framework="openai", auto_detect_framework=False)
def fixed_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)
```

---

## 58개 지표와 데코레이터 활성화 조건

### Layer 1 — 기초 지표 (기본 데코레이터로 자동 활성)

| 지표 | 클래스 | 데코레이터 자동화 | 주요 출력 |
|------|--------|----------------|---------|
| **Task Completion Rate** | `TaskCompletionTracker` | 항상 활성 | `tcr` · `full_success` · `partial_success` · `failures` |
| **Accuracy** | `AccuracyEvaluator` | 항상 활성 (`score_fn` 없으면 기본 알고리즘) | `overall_accuracy` · `median_accuracy` · `std_accuracy` |
| **Response Quality** | `ResponseQualityEvaluator` | response + request 있으면 자동 | `dimension_scores` · `total_score` (0–5) · `grade` |
| **Latency** | `LatencyTracker` | 함수 실행 시간 자동 측정 | `mean` · `p50` · `p90` · `p95` · `p99` · `std` |
| **Token Economy** | `TokenEconomyTracker` | 프레임워크 어댑터 자동 추출 | `total_tokens` · `total_cost` · `estimated_monthly_cost` |
| **Hallucination** | `HallucinationDetector` | `rag_mode=True` 또는 `enable_hallucination_detection=True` | `hallucination_rate` · `unsupported_claims_count` · `by_severity` |

Accuracy 계산 방식: Token Overlap(40%) + Jaccard Similarity(30%) + LCS(20%) + 문자 유사도(10%)

### Layer 2-A — 에이전틱 지표 (tool_calls · chain_steps 자동 추출 시 활성)

| 지표 | 클래스 | 활성화 조건 | 주요 출력 |
|------|--------|-----------|---------|
| **Tool Call Analysis** | `ToolCallAnalyzer` | `tool_calls` 자동 추출 또는 EvalMetadata | `efficiency_score` · `redundancy_rate` · `failure_rate` |
| **Retry & Correction** | `RetryCorrectionTracker` | `retry=RetryConfig(max=N)` 파라미터 또는 `attempts` 필드 | `retry_rate` · `first_attempt_success_rate` · `correction_success_rate` |
| **Tool Selection F1** | `ToolSelectionTracker` | `expected_tools_arg` 파라미터 지정 | `precision` · `recall` · `f1_score` |
| **Agent Coordination** | `AgentCoordinationTracker` | `agent_interactions` 자동 추출 | `score` · `pattern_type` · `unique_agents` |
| **Workflow Execution** | `WorkflowExecutionTracker` | `chain_steps` · `state_transitions` 자동 추출 | `step_success_rate` · `task_success_rate` · `bottlenecks` |

### Layer 2-B — 보안 지표 (`security=SecurityConfig()` 또는 Monitor 전역 설정)

| 지표 | 클래스 | 탐지 대상 | 주요 출력 |
|------|--------|---------|---------|
| **Input Sanitization** | `InputSanitizationTracker` | SQL Injection · Command Injection · XSS · Prompt Injection (40개 패턴) | `risk_level` · `threat_count` · `threat_rate` |
| **Output Leakage** | `OutputLeakageDetector` | API 키 · 비밀번호 · 신용카드 · 개인정보 | `severity` · `leakage_count` · `leakage_rate` |
| **Tool Authorization** | `ToolAuthorizationTracker` | 비인가 툴 사용 · 위험 파라미터 | `compliance_rate` · `violation_rate` · `unauthorized_calls` |
| **Privilege Escalation** | `PrivilegeEscalationDetector` | guest→admin 권한 상승 체인 | `risk_score` (0–10) · `escalation_detected` · `escalation_path` |
| **Tool Chain Attack** | `ToolChainAttackDetector` | 데이터 유출 · 횡적 이동 · 지속성 공격 체인 | `confidence` (0–1) · `attack_types` · `is_suspicious_chain` |

보안 지표 활성화 방법:

```python
from agent_evaluator.decorators import SecurityConfig

# 방법 A: 특정 함수에만 임시 활성 (이 호출만)
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question, ground_truth=""): ...

# 방법 B: Monitor 전역 설정 (모든 record_task에 적용)
monitor = PerformanceMonitor("results/", enable_security_metrics=True)
```

### Layer 3 — 하이브리드 평가 (외부 라이브러리)

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    use_deepeval=True,    # pip install "agent-evaluator[eval]"
    use_ragas=True,
    output_dir="results/",
)

# HybridPerformanceMonitor는 PerformanceMonitor 상속 — 3종 데코레이터 모두 동일하게 사용
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question, context="", ground_truth=""): ...
```

| 제공자 | 지표 | 조건 |
|--------|------|------|
| **LLMJudge** *(v0.7.5+)* | completeness · relevance · factual · toxicity · bias | 기본 설치에 포함 · `llm_judge=LLMJudgeConfig()` |
| **LLMJudge** *(v0.7.6+)* | + **faithfulness** (RAG) · **커스텀 기준(G-Eval)** | `rag_mode=True` + `llm_judge=LLMJudgeConfig(criteria=[...])` |
| **DeepEval** | Hallucination(NLI) · Answer Relevancy (LLM) | `pip install "agent-evaluator[eval]"` |
| **Ragas** | Faithfulness · Answer Relevancy · Context Precision · Context Recall (LLM) | 동일 + `context` 필드 필요 |

### Harness Engineering — 33개 Config, 7개 Gate Group (A–G)

Harness Config는 `@agent_eval` 데코레이터 파라미터로 전달하며, `PerformanceMonitor`가 자동 집계합니다. 대시보드 **Harness Gate** 탭에서 그룹별 통과/경고/실패를 시각화합니다.

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig, PlanConfig,   # Group A
    LoopDetectionConfig, StateConsistencyConfig,           # Group B
    FaultToleranceConfig, GracefulDegradationConfig,       # Group C
    SLAConfig, EfficiencyConfig,                           # Group D
    ThreatSeverityConfig, ComplianceConfig,                # Group E
    ConsensusConfig, AgentRoleConfig,                      # Group F
    ExplainabilityConfig, ObservabilityConfig,             # Group G
)

@agent_eval(monitor, task_type="qa",
    instruction=InstructionConfig(required_keywords=["서울"], strict=True),
    loop_detection=LoopDetectionConfig(max_loop_count=3),
    sla=SLAConfig(max_response_time=5.0, p95_threshold=3.0),
    explainability=ExplainabilityConfig(min_reasoning_steps=2),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

| Group | 영역 | Config (개수) |
|-------|------|--------------|
| **A** | Goal Achievement | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig **(6)** |
| **B** | Behavioral Integrity | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig **(6)** |
| **C** | Reliability | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig **(5)** |
| **D** | Performance Contract | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig **(5)** |
| **E** | Security Boundary | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig **(3)** |
| **F** | Multi-Agent Coord. | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig **(4)** |
| **G** | Observability | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig **(4)** |

> **Note**: `TTFTVariabilityConfig` · `CostPredictabilityConfig`는 monitor 수준 자동 집계(≥5 tasks with `ttft_ms` extra 및 task_type별 토큰 CV). 데코레이터 파라미터 불필요.

전체 실전 예제: `Evaluator_Examples/08_harness_eval.py`

---

## CI/CD 품질 게이팅

### 코드에서 직접

```python
eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""): ...

# 평가 실행 후
eval.gate(tcr=85, accuracy=70, quality=3.5, hallucination=5)
# 임계값 미달 시 sys.exit(1) — CI 파이프라인 실패 처리
```

### CLI (GitHub Actions)

```yaml
- name: Run Evaluation
  run: python eval_suite.py --output results/ci.json

- name: Quality Gate
  run: |
    agent-eval gate results/ci.json \
      --tcr 85 --accuracy 70 --p95-latency 3.0 --hallucination 5
```

`agent-eval gate` 옵션:

| 옵션 | 설명 |
|------|------|
| `--tcr N` | Task Completion Rate 최소값 (%) |
| `--accuracy N` | 정확도 최소값 (%) |
| `--p95-latency N` | P95 지연시간 최대값 (초) |
| `--hallucination N` | 환각 탐지율 최대값 (%) |
| `--llm-judge N` | LLM Judge 종합 점수 최소값 (0–5) |
| `--fail-on-regression N` | 이전 기준선 대비 허용 하락 비율 (%) |
| `--junit-xml PATH` | JUnit XML 출력 (CI 연동) |

**종료 코드:** `0` = 전체 통과 / `1` = 임계값 미달 / `2` = 회귀 감지

---

## 조건부 알림

3종 데코레이터 모두 동일한 `alert_rules=` API를 지원합니다.

```python
from agent_evaluator.decorators import AlertRuleBuilder

slow_rule  = AlertRuleBuilder.when_latency_above(3.0,  handler=lambda msg, tr: print(f"[SLOW] {msg}"))
error_rule = AlertRuleBuilder.when_accuracy_below(0.7, handler=lambda msg, tr: send_slack(msg))
fail_rule  = AlertRuleBuilder.when_completion_below(0.8, handler=lambda msg, tr: send_alert(msg))

# 3종 데코레이터 모두 동일하게 적용
@agent_eval(monitor,      task_type="qa", alert_rules=[slow_rule, error_rule])
def agent(question, ground_truth=""): ...

@batch_eval(monitor,      task_type="qa", alert_rules=[slow_rule])
def batch_agent(questions, ground_truths=None): ...

@conversation_eval(monitor, max_turns=5,  alert_rules=[fail_rule])
def chat(question, session_id="s1"): ...
```

---

## 주기적 자동 저장 (`flush_every`)

프로세스가 중간에 종료되어도 결과가 보존됩니다. 3종 데코레이터 모두 지원합니다.

```python
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question, ground_truth=""): ...

@batch_eval(monitor, task_type="qa", flush_every=5)
def batch_agent(questions, ground_truths=None): ...

# QuickEval에서도 동일
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
```

---

## preset — 환경별 설정 묶음

3종 데코레이터 모두 동일한 `preset=` 파라미터를 지원합니다.

| preset | 자동 적용 설정 | 환경 |
|--------|-------------|-----|
| `"production"` | `flush_every=50` · `enable_anomaly_detection=True` · `sample_rate=0.1` | 운영 서버 |
| `"development"` | `llm_judge=LLMJudgeConfig()` · `auto_detect_framework=True` | 개발·디버깅 |
| `"testing"` | `sample_rate=1.0` · `timeout=10.0` | 단위 테스트 |
| `"canary"` | `sample_rate=0.01` · `flush_every=100` | 카나리 배포 |

```python
@agent_eval(monitor,      task_type="qa", preset="production")
@batch_eval(monitor,      task_type="qa", preset="testing")
@conversation_eval(monitor, max_turns=5,  preset="development")
```

---

## CLI 명령어

| 명령어 | 설명 |
|--------|------|
| `agent-eval init` | 대화형 API 키 설정 마법사 |
| `agent-eval check` | 현재 설정 상태 및 API 키 확인 |
| `agent-eval dashboard [dir]` | FastAPI 대시보드 웹 서버 실행 |
| `agent-eval gate <result.json>` | CI/CD 품질 게이팅 |
| `agent-eval trend <dir>` | 순차 평가 결과 TCR·정확도 추세 분석 (회귀 감지) |
| `agent-eval dataset build <dir>` | 운영 결과에서 골든 데이터셋 자동 추출 |
| `agent-eval monitor` | Arize Phoenix + OTEL 실시간 모니터링 |
| `agent-eval --version` | 패키지 버전 출력 |

---

## 평가 결과 출력 시나리오

데코레이터로 수집된 지표를 **세 가지 방식**으로 출력할 수 있습니다.

| 시나리오 | 용도 | 추가 작업 |
|----------|------|----------|
| 터미널 출력 | 즉시 확인 · 디버깅 | 없음 |
| FastAPI 대시보드 | 개발·검증 단계 시각화 | `save_to_file()` 후 CLI 실행 |
| Phoenix OTEL | 프로덕션 실시간 모니터링 | `setup_otel()` 선언 후 별도 터미널에서 `agent-eval monitor` |

### 시나리오 1 — 터미널 출력

데코레이터 실행 후 `generate_report()`로 결과를 즉시 확인합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# 터미널 출력 — generate_report() 후 to_json() 또는 to_dict()
report = monitor.generate_report()
print(report.to_json(indent=2))
# → {"accuracy_metrics": {...}, "efficiency_metrics": {...}, "quality_metrics": {...}}
```

### 시나리오 2 — FastAPI 대시보드

`save_to_file()`이 `results/` 에 JSON을 쓰고, `agent-eval dashboard`가 이를 읽습니다.

```python
# 방법 A: 실행 후 수동 저장
monitor.save_to_file("eval")          # results/eval.json + .html 생성

# 방법 B: auto_save — N건마다 자동 저장
monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# 방법 C: QuickEval
eval = QuickEval("results/")
@eval.qa
def my_agent(q, ground_truth=""): ...
eval.save()                           # results/quickeval.json + .html
```

```bash
# 대시보드는 기본 설치에 포함
agent-eval dashboard results/ --watch        # 파일 변경 시 자동 갱신
```

| URL | 내용 |
|-----|------|
| `http://localhost:8765` | 메인 대시보드 |
| `http://localhost:8765/slides` | 발표용 슬라이드 뷰 |
| `http://localhost:8765/api/docs` | Swagger API 문서 |

### 시나리오 3 — Phoenix 실시간 모니터링 (OTEL)

`setup_otel()`을 **PerformanceMonitor 생성 전에** 호출해야 합니다. 이후 모든 `record_task()` 호출에서 OTLP 스팬이 자동 발행됩니다.

```bash
# 터미널 1 — Phoenix 서버 기동 (OTEL은 기본 설치에 포함)
agent-eval monitor                           # http://localhost:6006
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

# 호출 시 OTLP 스팬 자동 전송 → Phoenix Tracing 탭에서 즉시 확인
my_agent("한국의 수도는?", ground_truth="서울")
```

Tracing · Evaluators · Datasets · Prompts 4개 메뉴에서 실시간 확인 가능합니다.

---

## 공개 API

```python
from agent_evaluator import (
    PerformanceMonitor,            # 평가 오케스트레이터
    QuickEval,                     # 원스톱 Facade
    HybridPerformanceMonitor,      # Layer 3 포함 모니터
    TaskResult, TaskType, EvaluationReport,
    create_taskresult,
    evaluation_session, async_evaluation_session,
    ConversationSession, ConversationMetrics, ConversationTurn,
    LLMJudge,
    SimpleTaskAlertRule, AlertRuleBuilder,
)

from agent_evaluator.decorators import (
    # ── 3종 핵심 데코레이터 ──────────────────
    agent_eval,           # 단일 태스크 (1호출 → 1 TaskResult)
    batch_eval,           # 배치 평가   (1호출 → N TaskResult)
    conversation_eval,    # 멀티턴 대화 (N호출 → 1 TaskResult)

    # ── 통합 팩토리 & 탈출구 ─────────────────
    EvalDecorator,        # 3종 공통 설정 팩토리
    eval_context,         # 데코레이터 불가 시 컨텍스트 매니저

    # ── 메타데이터 & 유틸리티 ────────────────
    EvalMetadata,         # agent_eval / batch_eval 추가 메타데이터
    TurnMetadata,         # conversation_eval 턴별 메타데이터
    get_eval_ctx,         # 스레드 로컬 평가 컨텍스트 접근
    FrameworkLiteral,     # 21개 프레임워크 타입 힌트
    get_framework_info,   # 프레임워크 어댑터 정보 조회
    AlertRuleBuilder,     # 알림 규칙 팩토리
    flush_conversation,   # 대화 세션 수동 종료
    flush_all_conversations,
)
```

---

## 예제 가이드

9개 파일로 구성됩니다. 각 파일은 독립 실행 가능합니다.

### 예제별 의존성

| 예제 | 필수 | 선택 |
|------|------|------|
| `01_layer1_all_metrics.py` | `pip install agent-evaluator` | `agent-eval monitor` (Phoenix OTEL) |
| `02_layer2_agentic_security.py` | `pip install agent-evaluator` | `agent-eval monitor` |
| `03_framework_adapters.py` | `pip install agent-evaluator` | `agent-eval monitor`<br>⚠️ 실제 LangChain/CrewAI/AutoGen 패키지 **불필요** — 데코레이터가 duck typing으로 mock 응답 처리 |
| `04_decorator_quickeval.py` | `pip install agent-evaluator` | `agent-eval monitor` |
| `05_streaming_alerts.py` | `pip install agent-evaluator` | `agent-eval monitor`, `SLACK_WEBHOOK_URL` (미설정 시 Mock 핸들러 자동 대체) |
| `06_operational.py` | `pip install agent-evaluator` | `agent-eval monitor` |
| `07_phoenix_hybrid.py` | `pip install agent-evaluator` | `agent-eval monitor` (OTEL 기본 포함)<br>`pip install "agent-evaluator[eval]"` + `OPENAI_API_KEY` (미설정 시 mock 데이터로 대체) |
| `08_harness_eval.py` | `pip install agent-evaluator` | `agent-eval monitor` |
| `08_harness_validation.py` | `pip install agent-evaluator` | — |

### 실행

```bash
cd Evaluator_Examples

python 01_layer1_all_metrics.py        # Layer 1 전체 — Accuracy · Hallucination · Quality · Latency · Token · TCR
python 02_layer2_agentic_security.py   # Layer 2 전체 — Tool · Retry · Coordination · Workflow · 보안 5종 · 대화
python 03_framework_adapters.py        # 프레임워크 어댑터 — LangChain · LangGraph · CrewAI · AutoGen + 크로스 파이프라인
python 04_decorator_quickeval.py       # 데코레이터 전체 API — @agent_eval · @batch_eval · @conversation_eval · QuickEval · LLMJudge
python 05_streaming_alerts.py          # 실시간 — StreamingEvaluator · ImplicitFeedback · AlertEngine · SimpleTaskAlertRule
python 06_operational.py               # 운영 인프라 — AnomalyDetector · CostTracker · GoldenSetBuilder · evaluation_session
python 07_phoenix_hybrid.py            # Phoenix OTEL — Tracing · Datasets · Playground · GraphQL + DeepEval · Ragas (opt-in)
python 08_harness_eval.py              # Harness Engineering — 7개 Gate(A-G) · 33개 Config 실전 평가
python 08_harness_validation.py        # Harness Config 파라미터 검증 · 경계 케이스 테스트

# ── 인프라 ───────────────────────────────────────────────────
agent-eval monitor                     # Phoenix 서버 기동 (http://localhost:6006)
agent-eval dashboard --watch           # 대시보드 (http://localhost:8765)
```

> 구 21개 예제는 `Evaluator_Examples/.deprecated/` 에 보존됩니다.

---

## 프로젝트 구조

```
agent-evaluator/
├── agent_evaluator/
│   ├── decorators.py            # agent_eval · batch_eval · conversation_eval
│   │                            # EvalDecorator · eval_context · EvalMetadata · TurnMetadata
│   ├── quick_eval.py            # QuickEval — 원스톱 Facade
│   ├── core/
│   │   ├── trackers/
│   │   │   ├── base.py          # TaskResult · EvaluationReport · TaskType
│   │   │   ├── layer1.py        # Foundation 지표 6종
│   │   │   ├── layer2.py        # Agentic 지표 5종 (+ 보안 5종)
│   │   │   ├── security.py      # 보안 지표 5종 (Layer 2-B)
│   │   │   ├── monitor.py       # PerformanceMonitor (오케스트레이터)
│   │   │   ├── conversation.py  # ConversationSession · ConversationMetrics
│   │   │   └── feedback.py      # ImplicitFeedbackTracker
│   │   ├── otel/                # OpenTelemetry 통합 ([otel] extras)
│   │   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   │   └── monitor_context.py   # evaluation_session · async_evaluation_session
│   ├── integrations/
│   │   ├── llm_judge.py         # LLMJudge
│   │   └── metric_adapters.py   # DeepEval · Ragas 어댑터
│   ├── serve/                   # FastAPI 대시보드 ([serve] extras)
│   ├── cli/                     # agent-eval CLI
│   ├── alerts/                  # AlertEngine · SimpleTaskAlertRule
│   ├── anomaly/                 # AnomalyDetector
│   ├── cost/                    # CostTracker · AdaptivePolicy
│   └── datasets/                # GoldenSetBuilder
│
├── Evaluator_Examples/          # 예제 9개 파일 (.deprecated/에 구 21개 보존)
├── tests/                       # 2,465개+ 테스트 함수, 53개 파일
└── pyproject.toml
```

---

## 의존성 명세

**기본 설치 포함 패키지** (`pip install agent-evaluator`)

| 패키지 | 버전 범위 | 용도 |
|--------|----------|------|
| `numpy` | ≥1.20.0, <3.0.0 | 수치 연산 |
| `pandas` | ≥1.3.0, <4.0.0 | 지표 집계 |
| `python-dotenv` | ≥0.19.0, <2.0.0 | 환경변수 관리 |
| `openai` | ≥1.0.0, <3.0.0 | LLMJudge 엔진 |
| `anthropic` | ≥0.20.0, <1.0.0 | LLMJudge 엔진 |
| `fastapi` | ≥0.110.0, <1.0.0 | 웹 대시보드 |
| `uvicorn[standard]` | ≥0.29.0, <1.0.0 | 웹 대시보드 |
| `jinja2` | ≥3.1.0, <4.0.0 | 웹 대시보드 |
| `python-multipart` | ≥0.0.9, <1.0.0 | 웹 대시보드 |
| `opentelemetry-sdk` | ≥1.20.0, <2.0.0 | OTEL 모니터링 |
| `opentelemetry-exporter-otlp-proto-http` | ≥1.20.0, <2.0.0 | OTEL 모니터링 |
| `arize-phoenix` | ≥7.0.0 | Phoenix 실시간 모니터링 |
| `pdfplumber` | ≥0.10.0, <1.0.0 | 한국어 RAG PDF 처리 |

**선택 extras** (설치 명령은 [## 설치](#설치) 참조)

| Extra | 주요 패키지 | 설치 시간 | 비고 |
|-------|-----------|----------|------|
| `[examples]` | 기본 + eval | 무거움 | 예제 01~06: 기본만 필요 · 07: eval 추가 필요 |
| `[eval]` | deepeval ≥3.0, <4.0 · ragas ≥0.4, <2.0 · datasets ≥4.0, <6.0 | 무거움 | DeepEval/Ragas 외부 평가 |
| `[langchain]` | langchain ≥1.0, langgraph ≥1.0 | 중간 | 사용자 LangChain 에이전트 코드용¹ |
| `[dspy]` | dspy-ai ≥2.0 | 중간 | 사용자 DSPy 에이전트 코드용¹ |
| `[pydanticai]` | pydantic-ai ≥1.0, <2.0 | 빠름 | 사용자 PydanticAI 에이전트 코드용¹ |
| `[crewai]` | crewai ≥1.0, <2.0 | 무거움 (단독 격리) | 사용자 CrewAI 에이전트 코드용¹ |
| `[autogen]` | pyautogen ≥0.3, autogen-agentchat ≥0.4 | 무거움 (단독 격리) | 사용자 AutoGen 에이전트 코드용¹ |
| `[full]` | 기본 + eval + langchain + dspy + pydanticai + crewai + autogen | 매우 무거움 | ⚠️ 10분+, CI 전체 호환성 검증용 |
| `[dev]` | pytest · pytest-cov · ruff · mypy · build · twine | 빠름 | 개발 환경 |

¹ agent-evaluator 자체는 이 패키지 없이도 완전히 동작 (duck typing). 사용자의 에이전트 코드가 해당 프레임워크를 직접 import할 때만 설치.

---

## 개발 환경

```bash
git clone https://github.com/bullpeng72/Agent-Evaluator.git
cd Agent-Evaluator
pip install -e ".[dev]"

pytest                          # 테스트 실행 (2,465개+)
ruff check agent_evaluator/    # 린트
ruff format agent_evaluator/   # 포맷
mypy agent_evaluator/          # 타입 검사
```

---

## 변경 이력

### v0.8.2 (2026-04-17) — Harness Config 33개 양식 통일 · 대시보드 UI 개선

- Harness Config 카드 33개 아이콘·수식·임계값 배지 양식 통일; `08_harness_eval.py` 예제 추가
- 대시보드 Nav 3단 계층 재편; Gate 상관 히트맵(7×7 Pearson) · 실패 연쇄 추적 추가
- HTML 리포트 Gate A–G 중심 전면 재편; CSV export Gate 컬럼 16개 추가
- 그룹 분류 수정: StateConsistencyConfig·DeadlockConfig Group F→B 이동
- 테스트 파일 2개 추가 (53개 파일, 2,465개+)

### v0.8.1 (2026-04-14) — 데코레이터 파라미터 구조화

- `RetryConfig` · `LLMJudgeConfig` · `SecurityConfig` 3개 구조체 도입; 개별 파라미터 제거
- `enable_hallucination` → `enable_hallucination_detection` 이름 통일
- 테스트 548개 추가; 파일 72→49개 리구조화

### v0.8.0 (2026-04-13) — 정확도 지표 전면 개선

- Token Overlap F1(조화평균) 교체; Char Similarity Levenshtein 통일
- task_type 인식 completion_score: code_generation AST 파싱, tool_use 미사용 시 0.6

### v0.7.9 (2026-04-13) — RunTrendAnalyzer · arize-phoenix 호환 수정

- `RunTrendAnalyzer` + `agent-eval trend` — 추세 분석 · `--fail-on-regression` CI/CD 연동
- arize-phoenix 버전 제약 충돌 수정

### v0.7.8 (2026-04-12) — SDK 기본 내장

- `pip install agent-evaluator` 단독으로 LLMJudge · 대시보드 · OTEL 사용 가능

### v0.7.7 (2026-04-11) — 데코레이터 버그 수정 · 스레드 안전성

- `agent_eval` preset 파라미터 미적용 버그 수정; Layer 2 트래커 5개 `threading.Lock` 추가

### v0.7.6 (2026-04-10) — LLMJudge G-Eval/Ragas 대체

- `judge_criteria` G-Eval 커스텀 채점; `rag_mode=True` 시 `faithfulness` 자동 추가

### v0.7.0–v0.7.5 (2026-04-01~09) — OTEL/Phoenix · 3종 데코레이터 · QuickEval

- `agent-eval monitor` CLI · Arize Phoenix 실시간 모니터링
- 3종 데코레이터 완성(`agent_eval`·`batch_eval`·`conversation_eval`) · `QuickEval` Facade
- 21개 프레임워크 어댑터 · 보안 트래커 실동작 버그 수정(CRITICAL)

### v0.6.x (2026-03-21~04-01) — SDK 안정화

- LangChain/LangGraph/CrewAI/AutoGen · FastAPI 대시보드 · LLMJudge · ConversationSession

### v0.2.x–v0.5.x — 초기 구현

- Layer 1/2/3 트래커 25개 · `evaluation_session` 초기 구현
