# Chapter 12. 데코레이터 완전 정복

이 챕터에서 배우는 것: Agent-Evaluator SDK의 핵심 인터페이스인 데코레이터 시스템을 완벽하게 이해한다. 비즈니스 로직과 평가 코드를 어떻게 깔끔하게 분리하는지, 상황별로 어떤 데코레이터를 선택해야 하는지, 그리고 RAG·멀티에이전트·스트리밍 같은 실전 시나리오에서 데코레이터를 어떻게 조합하는지를 단계적으로 익힌다.

> 📖 **관련 레퍼런스**
> - **[Appendix E — 에러 코드 & 트러블슈팅](../Appendix/E_에러코드_트러블슈팅.md)**: 데코레이터 적용 후 발생하는 오류 코드별 원인과 해결책
> - **[Chapter 11 — 평가 데이터 설계](Chapter_11_평가데이터_설계.md)**: 데코레이터에 전달할 `ground_truth`와 `task_type`을 어떻게 설계할지 → **먼저 읽기 권장**
> - **[Appendix I — 지표 비교 분석 및 선택 가이드](../Appendix/I_지표_비교분석_선택가이드.md)**: `task_type` 선택이 정확도 계산에 미치는 영향

> ⭐ **새 프로젝트를 시작한다면**: 데코레이터 API를 배우기 전에 이 챕터 마지막의 **[§12.12 데코레이터 친화적 설계 원칙](#1212-데코레이터-친화적-에이전트-함수-설계-원칙)**을 먼저 읽어라. 처음부터 올바르게 설계하면 나중에 평가를 붙이는 비용이 0이 된다.

---

## 12.1 왜 데코레이터인가 — SDK 설계 철학

### 데코레이터란 무엇인가

Python에서 데코레이터(`@`)는 함수 위에 붙여서 그 함수의 동작을 변경하거나 감싸는 문법이다. Agent-Evaluator SDK에서 `@agent_eval(monitor, task_type="qa")`를 에이전트 함수 위에 붙이면, 함수 코드를 한 줄도 수정하지 않고 자동 측정 + 기록 + Gate 판정이 추가된다.

```python
# 에이전트 함수 — 비즈니스 로직만 담는다
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# @agent_eval을 붙이면 → 동일 코드에 평가가 삽입된다
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

이 챕터에서 다루는 SDK 3종 데코레이터:
- `@agent_eval` — 단일 에이전트 함수. 가장 기본
- `@batch_eval` — 질문 목록을 한 번에 배치 평가
- `@conversation_eval` — 챗봇처럼 여러 턴이 이어지는 멀티턴 대화 평가

### 비즈니스 로직과 평가 코드의 분리

좋은 평가 프레임워크는 에이전트 코드를 최대한 건드리지 않아야 한다. 평가를 추가하기 위해 핵심 비즈니스 로직을 리팩토링하거나, 에이전트 함수마다 동일한 보일러플레이트를 반복하는 것은 유지보수 부채를 쌓는 일이다.

데코레이터 없이 에이전트 함수 하나를 평가하려면 다음과 같은 코드가 필요하다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
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

- 데코레이터 없이 평가하려면 `execution_time`, `accuracy_score`, `task_id`, `tokens_used` 등 11개 필수 필드를 직접 채워야 한다
- `accuracy_score` 계산 로직(TokenF1·Jaccard·LCS)을 매 함수마다 구현하면 일관성이 떨어지고 유지보수 부채가 쌓인다
- 에이전트 함수가 늘어날수록 이 보일러플레이트 코드가 기하급수적으로 증가하여 비즈니스 로직보다 평가 코드가 더 많아진다

문제는 명확하다. `execution_time` 측정을 빠뜨리면 0이 기록되고, `accuracy_score` 계산 로직을 매번 구현해야 하며, 에이전트 함수가 늘어날수록 이 코드가 기하급수적으로 증가한다.

데코레이터 방식은 이 모든 것을 한 줄로 해결한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
# 데코레이터 방식 — 비즈니스 로직만 남는다
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)  # 비즈니스 로직만
```

- `@agent_eval(monitor, task_type="qa")`를 함수 위에 붙이는 것만으로 TaskResult 생성부터 monitor 기록까지 전 과정이 자동화된다
- 함수 시그니처에 `ground_truth: str = ""`를 포함하면 데코레이터가 자동으로 인식해 accuracy_score를 계산한다
- 동기·비동기·제너레이터(스트리밍) 함수를 모두 자동 감지해 처리하므로 함수 타입에 무관하게 동일하게 적용된다

데코레이터가 자동으로 처리하는 항목:

| 항목 | 처리 방법 |
|------|----------|
| `execution_time` | `time.perf_counter()` 나노초 측정 |
| `success` / `completion_score` | task_type 인식 자동 계산 — `code_generation`은 AST 파싱, `tool_use`는 도구 호출 여부, 기타는 길이 기반 |
| `accuracy_score` | `ground_truth` vs 반환값 4-way 가중치 계산 |
| `task_id` | UUID 기반 자동 생성 |
| `tokens_used` | `framework=` 어댑터 또는 EvalMetadata 자동 추출 |
| `monitor.record_task()` | 측정 완료 후 자동 호출 |

### 데코레이터 선택이 Gate 판정에 미치는 영향

데코레이터의 `task_type`과 Harness Config 선택은 QA 관리자가 보는 Gate A–G 판정에 직접 영향을 준다.

| 개발자 선택 | Tracker 동작 | QA 관리자가 보는 Gate 결과 |
|-----------|------------|------------------------|
| `task_type="qa"` | AccuracyEvaluator F1 기반 계산 | Gate A 정확도 점수 |
| `task_type="tool_use"` | ToolCallAnalyzer 활성화 | Gate B 행동무결성 점수 추가 |
| `sla=SLAConfig(p95_ms=2000, fail_threshold=3)` | LatencyTracker P95 감시, 위반 3회 누적 시 FAIL 처리 | Gate D WARN/FAIL + TCR 하락 |
| `security=SecurityConfig()` | InputSanitizationTracker 등 5종 임시 활성 | Gate E 보안경계 점수 추가 |
| `llm_judge=LLMJudgeConfig()` | LLMJudge 5차원 기본 채점 (+ RAG 시 faithfulness) | Gate G 운영관측성 점수 추가 |

> 📋 **QA 관리자와의 협업**: Config 임계값을 처음 설정할 때는 `fail_on_violation=False`(관찰 모드)로 시작한 뒤 데이터를 QA 관리자와 공유하세요. 임계값 협의 후 `True`로 전환하면 배포 차단이 활성화됩니다. 상세 협업 워크플로우 → [Chapter 3 §3.5](../Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md) / Config 임계값 설정 기준 → [Chapter 14](../Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md)

### 데코레이터 방식 vs 수동 PerformanceMonitor 방식

수동으로 `PerformanceMonitor.record_task(result)`를 호출해도 기본 측정은 가능하다. 그러나 Harness Config(`SLAConfig`, `InstructionConfig` 등)를 데코레이터 없이 전달하려면 추가 코드가 필요하며, 무엇보다 **배포 기준이 에이전트 함수와 분리**된다는 구조적 문제가 생긴다.

| 항목 | 데코레이터 방식 | 수동 방식 |
|------|--------------|---------|
| 배포 기준 위치 | 에이전트 함수 바로 위 (코드로 선언) | 별도 파일·문서에 분산 |
| Harness Gate 자동 판정 | 자동 (Config 전달로 활성화) | 수동 Config 전달 코드 필요 |
| 보일러플레이트 | 없음 | execution_time·task_id 등 직접 작성 |
| 코드 리뷰 가시성 | Config가 함수와 함께 변경 이력에 포함 | 기준 변경이 별도 커밋으로 분리될 가능성 |

---

## 12.2 에이전트 유형별 데코레이터 선택 가이드

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

**`@agent_eval` vs `QuickEval` — 언제 무엇을 쓸까?**

| 상황 | 권장 | 이유 |
|------|------|------|
| 처음 평가를 시작하고 싶다 | `QuickEval` | `PerformanceMonitor` 생성 없이 2줄로 시작 가능 |
| 에이전트 1~2개에 평가 추가 | `@agent_eval` | monitor를 직접 제어하며 세밀한 Harness Config 적용 |
| 에이전트 3개 이상에 동일 설정 공유 | `EvalDecorator` | 설정 1회 정의 → 모든 에이전트 자동 전파 |
| Harness Config를 최대한 활용하고 싶다 | `@agent_eval` | Config 파라미터를 직접 붙여 Gate 판정 세밀 제어 |
| CI/CD 게이팅이 목표 | `QuickEval` | `.gate(tcr=85, accuracy=70)` 한 줄로 완성 |

---

## 12.3 @agent_eval — 단일 태스크 평가

`@agent_eval`은 단일 에이전트 함수에 평가를 삽입하는 가장 기본적인 방법이다. 동기, 비동기, 제너레이터(스트리밍) 함수를 모두 자동 감지하여 처리한다.

### 기본 사용법

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 1 — @agent_eval 기본 사용법
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

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

LangChain·OpenAI·Anthropic 같은 프레임워크는 응답 객체에 토큰 수, 도구 호출 목록 등 풍부한 메타데이터를 담아 반환한다. `framework=` 파라미터를 지정하면 데코레이터가 해당 SDK 응답 객체를 자동으로 파싱해 `tokens_used`, `tool_calls` 등의 필드를 채운다. 별도 추출 코드를 작성하지 않아도 된다.

지원 프레임워크(21개): `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`, `anthropic`, `openai`, `gemini`, `llamaindex`, `haystack`, `vertexai`, `ollama`, `cohere`, `groq`, `mistral`, `bedrock`, `smolagents`, `semantic_kernel`, `vllm`, `huggingface`

`framework=` 파라미터를 지정하면 해당 SDK 응답 객체에서 토큰 수, 도구 호출 기록 등을 자동 추출한다. 이때 함수가 SDK 응답 **객체 전체**를 반환해야 한다는 점이 핵심이다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
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

- `framework=` 지정 시 함수가 **문자열이 아닌 SDK 응답 객체 전체**를 반환해야 토큰 수, 도구 호출 등이 자동 추출된다
- `framework="anthropic"`은 `usage.input_tokens` / `usage.output_tokens`와 캐시 토큰(`cache_read_input_tokens`)을 자동 파싱한다
- `framework="openai"`는 `choices[0].message.tool_calls`와 `usage.total_tokens`를 자동 파싱한다
- 응답 객체가 아닌 문자열을 반환하면 토큰 추출은 실패하지만 기본 평가(accuracy, latency)는 정상 동작한다

`framework=`를 생략하면 `auto_detect_framework=True`(기본값)가 응답 객체의 속성을 분석해 프레임워크를 자동 감지한다. `response.choices + response.usage` → openai, `response.content + response.model` → anthropic 등 12개 속성 기반으로 동작한다.

4개 프레임워크(LangChain, LangGraph, CrewAI, AutoGen)를 mock 응답 객체로 한 파일에서 비교하는 완전한 예제는 `ch13_frameworks.py`를 참조한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 1 — LangChain duck-typing 어댑터
from types import SimpleNamespace
from agent_evaluator.decorators import agent_eval

def _make_langchain_response(answer, tools, tokens):
    steps = [(SimpleNamespace(tool=t, tool_input="query"), f"{t} 결과") for t in tools]
    return SimpleNamespace(
        output=answer,
        intermediate_steps=steps,           # ← tool_calls 자동 추출
        usage_metadata={"input_tokens": tokens["input"], "output_tokens": tokens["output"]},
    )

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="lc")
def langchain_agent(question: str, ground_truth: str = ""):
    return _make_langchain_response(
        answer="LangChain 검색 결과입니다.",
        tools=["web_search", "calculator", "wikipedia"],
        tokens={"input": 350, "output": 120},
    )
```

- 실제 LangChain SDK 없이 동일한 구조의 `SimpleNamespace` 객체를 사용해도 어댑터가 정상 동작한다 — duck typing 방식
- `intermediate_steps`에서 `tool_calls`를 자동 추출, `usage_metadata`에서 `tokens_used`를 자동 추출
- `ch13_frameworks.py` 섹션 5에서 LangGraph → LangChain → CrewAI 크로스 프레임워크 파이프라인을 하나의 `monitor`로 통합 평가하는 패턴을 확인할 수 있다


### rag_mode=True — RAG 전용 자동 설정

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,    # ← 이 하나로 context_arg + hallucination 자동 활성
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(f"Context: {context}\n\nQuestion: {question}")
```

- `rag_mode=True` 하나로 `context_arg="context"` 설정, `HallucinationDetector` 활성화, LLMJudge와 함께 사용 시 `faithfulness` 차원 자동 추가가 모두 이루어진다
- 함수 시그니처에 `context: str = ""` 파라미터가 있어야 데코레이터가 컨텍스트를 자동으로 추출해 HallucinationDetector에 전달한다
- `task_type="information_retrieval"`과 함께 사용하는 것을 권장한다. `rag_mode=True`를 지정하면 task_type도 자동으로 설정된다

`rag_mode=True`가 자동으로 하는 일: (1) `context_arg="context"` 설정, (2) 내부적으로 hallucination 감지 활성화(데코레이터 레벨), (3) `HallucinationDetector`에 context를 전달해 일관성 점수 계산. `llm_judge=LLMJudgeConfig()`와 함께 사용 시 `faithfulness` 차원도 자동 추가된다.

### security=SecurityConfig() — 보안 검사 임시 활성

```python
# 출처: Evaluator_Examples/ch12_decorators.py — SecurityConfig
from agent_evaluator.decorators import agent_eval, SecurityConfig

@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def risky_agent(question: str, ground_truth: str = "") -> str:
    return agent.invoke(question)
# 5종 보안 트래커 임시 활성: InputSanitization, OutputLeakage,
# ToolAuthorization, PrivilegeEscalation, ToolChainAttack
# finally 블록에서 원래 설정으로 자동 복원
```

- `security=SecurityConfig()`는 5종 보안 트래커를 **해당 호출에만** 임시 활성화하는 temp-override 패턴이다. `finally` 블록에서 원래 상태로 자동 복원된다
- `SecurityConfig(allowed_tools=["search", "read"])`처럼 허용 도구 목록을 지정할 수 있다. 목록 외 도구 호출이 감지되면 `ToolAuthorizationTracker`에 기록된다
- 전체 monitor에 항상 보안 지표를 켜려면 `PerformanceMonitor(enable_security_metrics=True)`를 사용한다

### llm_judge=LLMJudgeConfig() — LLM-as-Judge 채점

```python
# 출처: Evaluator_Examples/ch12_decorators.py — LLMJudgeConfig
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),  # 채점에 사용할 LLM
)
def careful_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# LLM Judge가 5차원 기본 평가: completeness, relevance, factual_consistency, toxicity, bias
# rag_mode=True 시 faithfulness 차원 자동 추가 (6차원), LLMJudgeConfig(criteria=[...]) 지정 시 추가 확장
# 결과는 task.llm_judge["scores"]에 저장되어 대시보드에서 확인 가능 (llm_judge는 TaskResult 직접 필드)
```

- `LLMJudgeConfig(model=None)`이면 환경 변수에 있는 API 키를 기반으로 모델을 자동 결정한다 (`ANTHROPIC_API_KEY` → claude, `OPENAI_API_KEY` → gpt)
- `LLMJudgeConfig(sample_rate=0.1)`을 지정하면 전체 호출의 10%만 LLM 채점을 실행해 비용을 절감한다
- `LLMJudgeConfig(criteria=["medical_accuracy", "citation_quality"])`처럼 커스텀 기준을 추가하면 `criteria_scores` 키로 각 기준별 점수가 기록된다

### 모든 파라미터를 활용한 완전한 예시

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 3 — EvalMetadata 튜플 반환 (우선순위: EvalMetadata > score_fn)
from agent_evaluator import PerformanceMonitor, SimpleTaskAlertRule, AlertRuleBuilder
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig, RetryConfig

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
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),  # LLM Judge 채점 활성
    enable_anomaly_detection=True,  # 이상 탐지 활성
    sample_rate=0.5,              # 50%만 기록 (고트래픽용)
    flush_every=50,               # 50회마다 자동 저장
    alert_rules=[slow_alert, accuracy_alert],
    timeout=15.0,                 # 15초 초과 시 강제 중단
    retry=RetryConfig(max=2),     # 실패 시 최대 2회 재시도
    preset="production",          # preset 시스템 적용
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}]
    )
```

- `preset="production"`을 지정하면 `flush_every=50`, `sample_rate=0.1`, `enable_anomaly_detection=True`가 자동으로 적용된다
- `timeout=15.0`으로 최대 실행 시간을 제한할 수 있으며, 초과 시 `TimeoutError`가 발생하고 `success=False`로 기록된다
- `alert_rules=[...]` 목록에 여러 규칙을 넣으면 태스크 완료 후 순서대로 평가된다. `cooldown` 설정으로 동일 규칙의 연속 발화를 방지한다

---

## 12.4 @batch_eval — 대량 데이터셋 평가

질문 목록을 한 번에 평가해야 할 때 사용한다. 루프를 직접 작성하지 않고, 배치 전체를 한 번의 함수 정의로 처리한다.

### 기본 사용법

```python
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import batch_eval

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

- `@batch_eval`은 `questions` 리스트를 받아 각 항목에 대해 자동으로 TaskResult를 생성한다. 직접 루프를 작성할 필요가 없다
- `ground_truths` 파라미터명은 `ground_truths`, `expected`, `answers` 등 여러 키워드를 자동 인식한다
- `task_id_prefix`를 지정하면 `prefix_0`, `prefix_1`, ... 형식으로 task_id가 생성되어 결과를 그룹별로 구분할 수 있다

### concurrency=N — 병렬 처리

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 6 — @batch_eval (concurrency + DataFrame)
@batch_eval(
    monitor,
    task_type="qa",
    concurrency=4,      # 최대 4개 동시 실행 (>0이면 ThreadPoolExecutor/asyncio.gather 사용)
)
async def concurrent_batch(questions: list, ground_truths: list = None) -> list:
    tasks = [async_llm.ainvoke(q) for q in questions]
    return await asyncio.gather(*tasks)
# 100개 질문을 4개씩 병렬 처리 → 처리 속도 약 4배 향상
```

- `concurrency=4`를 지정하면 `asyncio.gather()` 또는 `ThreadPoolExecutor`를 사용해 최대 4개의 항목을 동시에 처리한다
- 비동기 함수(`async def`)에는 `asyncio.gather()`가, 동기 함수에는 `ThreadPoolExecutor`가 자동으로 선택된다
- `concurrency`를 너무 높게 설정하면 LLM API rate limit에 걸릴 수 있다. 일반적으로 4~8이 안정적인 범위다

### return_format="dataframe" — 분석용 DataFrame

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
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
# 출처: Evaluator_Examples/ch12_decorators.py — 예제 코드
# 낮은 정확도 케이스 필터링
low_accuracy = df[df["accuracy_score"] < 0.7]
print(f"개선 필요 케이스: {len(low_accuracy)}개")

# 오류 발생 케이스 분석
error_cases = df[df["has_error"] == True]
print(f"평균 실행시간(오류): {error_cases['execution_time'].mean():.2f}초")

# 느린 케이스 식별
slow_cases = df[df["execution_time"] > 5.0]
```

- `return_format="dataframe"` 결과의 컬럼은 task_id, accuracy_score, completion_score, execution_time, tokens_total 등 모든 TaskResult 필드를 포함한다
- pandas의 필터링과 집계 기능을 그대로 활용할 수 있어 품질 분포 파악, 이상치 탐색, CSV 저장이 편리하다
- DataFrame 결과를 `GoldenSetBuilder`의 소스 데이터로 연결하면 낮은 정확도 케이스를 골든 데이터셋의 `failure_cases` 전략으로 자동 추출할 수 있다

### 기타 유용한 파라미터

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 6 — batch_eval 옵션
@batch_eval(
    monitor,
    task_type="qa",
    item_timeout=30.0,              # 항목당 최대 30초
    on_item_error=lambda e, q: print(f"오류: {q[:30]}... → {e}"),
    flush_every=50,                 # 50건마다 자동 저장
)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

- `item_timeout=30.0`은 항목 하나에 대한 최대 허용 시간이다. 초과한 항목은 `success=False`, `errors=["timeout"]`으로 기록된다
- `on_item_error` 콜백은 항목 처리 중 예외 발생 시 호출된다. 시그니처는 `(exception, question) -> None`이다
- `flush_every=50`은 50건 처리마다 `save_to_file()`을 자동 호출해 장시간 배치 실행 중 데이터 유실을 방지한다

> 📋 **QA 관리자 TIP**: `return_format="dataframe"`과 `concurrency=N`을 함께 사용하면 병렬 실행 후 pandas DataFrame으로 품질 분포를 파악할 수 있다. CI 파이프라인에서 골든 데이터셋 100개를 배치로 돌리고 DataFrame 결과를 CSV로 저장하면 품질 트렌드를 추적하기 좋다. 입력 순서 섞기가 필요하면 호출 전에 `random.shuffle(questions)`으로 처리한다. `shuffle=`·`streaming_mode=` 파라미터는 존재하지 않는다.

---

## 12.5 @conversation_eval — 멀티턴 대화 평가

챗봇이나 고객 상담 에이전트처럼 여러 번의 대화가 이어지는 시나리오를 평가한다. `session_id`가 같은 호출을 하나의 세션으로 묶어 대화 전용 지표를 계산한다.

### 기본 사용법

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 7 — @conversation_eval
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import conversation_eval, flush_conversation

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

- `session_id_arg="sid"`는 함수 파라미터 중 세션 ID로 사용할 인수 이름을 지정한다. 같은 sid 값으로 호출된 모든 턴이 하나의 세션으로 묶인다
- `max_turns=10`에 도달하면 자동으로 `flush_conversation()`이 호출되어 `ConversationMetrics`가 계산된다
- `flush_conversation(session_id)`를 명시적으로 호출하면 세션을 강제 종료하고 지표를 즉시 기록할 수 있다

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
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 7 — @conversation_eval 고급
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import conversation_eval, flush_conversation

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

### ConversationSession 직접 사용 — 데코레이터 없이 대화 지표 계산

`@conversation_eval`이 내부에서 관리하는 `ConversationSession`을 직접 인스턴스화하면, 데코레이터 없이도 동일한 8가지 대화 지표를 계산할 수 있다. 독립 스크립트·배치 분석·커스텀 파이프라인에 적합하다.

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 추가 — ConversationSession 직접 사용
from agent_evaluator import ConversationSession, ConversationMetrics

# ── 패턴 1: 직접 생성 + add_turn() ──────────────────────────────────────────
session = ConversationSession("cs_demo_001")
session.add_turn(
    user="안녕하세요. 파이썬 학습을 시작하고 싶어요.",
    agent="반갑습니다! 파이썬은 배우기 쉬운 언어입니다. 변수와 자료형부터 시작하면 좋습니다.",
    metadata={"latency": 0.42},
)
session.add_turn(
    user="변수와 자료형이란 정확히 무엇인가요?",
    agent="변수는 값을 저장하는 공간이고, 자료형은 정수·문자열·리스트 등 값의 종류입니다.",
    metadata={"latency": 0.38},
)
session.add_turn(
    user="리스트와 딕셔너리의 차이는 무엇인가요?",
    agent="리스트는 순서가 있는 값의 모음이고, 딕셔너리는 키-값 쌍으로 이루어진 매핑 자료형입니다.",
    metadata={"latency": 0.45},
)

metrics: ConversationMetrics = session.compute_metrics()
print(f"turn_count        : {metrics.turn_count}")
print(f"overall_score     : {metrics.overall_score:.3f}")    # 4개 지표 평균
print(f"context_retention : {metrics.context_retention:.3f}")
print(f"topic_coherence   : {metrics.topic_coherence:.3f}")
print(f"progressive_depth : {metrics.progressive_depth:.3f}")
print(f"session_completion: {metrics.session_completion:.3f}")
print(f"avg_turn_latency  : {metrics.avg_turn_latency:.3f}s")
print(f"score_stddev      : {metrics.score_stddev:.3f}")     # 지표 간 균형 편차

# ── 패턴 2: PerformanceMonitor 컨텍스트 매니저 ──────────────────────────────
# with 블록 종료 시 자동으로 compute_metrics() + monitor.record_task() 호출
with monitor.conversation("cs_demo_002") as conv:
    conv.turn(user="머신러닝이란 무엇인가요?",
              agent="머신러닝은 데이터로부터 패턴을 학습하는 AI 기술입니다.")
    conv.turn(user="지도학습과 비지도학습의 차이는?",
              agent="지도학습은 정답 레이블이 있는 데이터로, 비지도학습은 레이블 없이 패턴만으로 학습합니다.")
    conv.turn(user="실무에서 가장 많이 쓰이는 알고리즘은?",
              agent="분류에는 랜덤포레스트·XGBoost, 회귀에는 선형회귀, 군집에는 K-Means가 널리 쓰입니다.")
# → 3턴 자동 집계 + monitor에 TaskResult로 기록됨
```

**`@conversation_eval` vs `ConversationSession` 직접 사용 비교**

| 항목 | `@conversation_eval` | `ConversationSession` 직접 |
|------|---------------------|--------------------------|
| session_id 관리 | 파라미터로 자동 추적 | 직접 지정 |
| 턴 추가 방식 | 함수 호출마다 자동 누적 | `add_turn()` 명시 호출 |
| flush 시점 | `max_turns` 도달 또는 `flush_conversation()` | `compute_metrics()` 호출 시 |
| monitor 연동 | 자동 `record_task()` | 컨텍스트 매니저(`with monitor.conversation()`) 사용 |
| 적합 상황 | 실시간 챗봇·API 서버 | 배치 분석·테스트 스크립트·커스텀 파이프라인 |

- `add_turn()`은 메서드 체이닝을 지원하므로 `session.add_turn(...).add_turn(...)`으로 이어 쓸 수 있다
- `metadata={"latency": 0.42}` 형태로 턴별 레이턴시를 전달하면 `avg_turn_latency` 지표에 자동 반영된다
- `score_stddev`는 4개 지표(context_retention·topic_coherence·progressive_depth·session_completion) 간의 표준편차로, 0에 가까울수록 균형 잡힌 대화 성능을 의미한다

---

## 12.6 eval_context — 데코레이터를 쓸 수 없을 때

외부 라이브러리의 콜백으로 에이전트가 실행되거나, 복잡한 조건부 로직 때문에 함수 데코레이터를 붙이기 어려울 때 사용하는 with 블록 패턴이다.

```python
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
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

- `eval_context`는 `with` 블록으로 평가를 감싸는 패턴으로, 데코레이터를 붙일 수 없는 외부 API 콜백이나 이벤트 핸들러에서 사용한다
- `ctx.response`에 결과를 할당하면 블록 종료 시 자동으로 TaskResult가 생성되어 monitor에 기록된다
- `ctx.chunk_step(chunk)`는 스트리밍 응답에서 첫 청크 수신 시각을 TTFT(Time-To-First-Token)로 자동 기록한다

> 👨‍💻 **개발자 TIP**: LangChain의 `on_llm_end` 콜백, FastAPI 라우터 내부, 또는 서드파티 프레임워크의 이벤트 핸들러처럼 함수 시그니처를 마음대로 바꿀 수 없는 상황에서 `eval_context`가 유일한 선택지가 된다.

---

## 12.7 EvalDecorator & QuickEval — 팩토리 패턴

### EvalDecorator — 공통 설정 재사용

여러 에이전트 함수에 동일한 `framework`, `alert_rules`, `flush_every` 설정을 적용해야 할 때, `EvalDecorator` 인스턴스를 하나 만들어 공유한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — LLMJudgeConfig
from agent_evaluator.decorators import EvalDecorator, LLMJudgeConfig
from agent_evaluator import PerformanceMonitor, AlertRuleBuilder

monitor = PerformanceMonitor("results/")

# 공통 설정을 한 번만 정의
eval = EvalDecorator(
    monitor,
    framework="openai",
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),
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

- `EvalDecorator`는 공통 설정을 한 번 정의하고 여러 에이전트 함수에 재사용할 수 있는 팩토리 패턴이다
- `.qa`, `.rag`, `.tool_use` 등 단축 속성으로 task_type별 설정을 간결하게 적용할 수 있다
- `framework=`, `alert_rules=`, `flush_every=` 등 공통 설정은 `EvalDecorator` 생성 시 한 번만 지정하면 모든 하위 데코레이터에 자동 전파된다

`EvalDecorator`의 단축 속성 11종: `.qa`, `.rag`, `.tool_use`, `.code`, `.reasoning`, `.planning`, `.data_analysis`, `.creative`, `.multi_agent`, `.secure`, `.streaming`

### QuickEval — 원스톱 Facade

`QuickEval`은 `PerformanceMonitor` + `EvalDecorator`를 1~2줄로 시작할 수 있게 해주는 최상위 Facade다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — QuickEval 평가
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

- `QuickEval("results/")`은 내부적으로 `PerformanceMonitor`와 `EvalDecorator`를 생성한다. 별도로 monitor를 만들 필요가 없다
- `.for_rag()`, `.for_security()`, `.for_llm_judge()` 팩토리 메서드는 목적에 맞는 설정이 사전 적용된 `QuickEval` 인스턴스를 반환한다
- 단축 속성(`.qa`, `.rag` 등)으로 에이전트를 등록하면 내부적으로 `@agent_eval`이 적용된다

### QuickEval 전체 워크플로우

```python
# 출처: Evaluator_Examples/ch12_decorators.py — QuickEval 평가
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

- `eval.save()`는 `results/quickeval.json`과 `quickeval.html`을 함께 생성한다
- `eval.gate(tcr=85, accuracy=70)`은 기준 미달 시 `sys.exit(1)`을 호출해 CI/CD 파이프라인을 중단시킨다
- `eval.summary()`는 accuracy, p95_latency, total_cost_usd 등 핵심 지표를 dict로 반환한다

---

## 12.8 고급 기능

### preset 시스템

자주 쓰는 설정 조합을 이름으로 지정한다:

| preset | 주요 설정 | 용도 |
|--------|-----------|------|
| `"production"` | `flush_every=50`, `sample_rate=0.1`, `enable_anomaly_detection=True` | 프로덕션 안정 운영 |
| `"development"` | `llm_judge=LLMJudgeConfig()`, `flush_every=5`, `sample_rate=1.0` | 개발/디버깅 |
| `"testing"` | 경량 설정, 빠른 실행 | 유닛 테스트 |
| `"canary"` | 카나리 배포 최적화 | 일부 트래픽 평가 |

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
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

- preset은 자주 사용하는 설정 조합에 이름을 붙인 것이다. `"production"` preset은 비용 절감과 안정성을 위한 설정이 미리 정의되어 있다
- preset을 지정하면서 개별 파라미터를 추가로 지정할 수 있다. 개별 파라미터가 preset보다 우선 적용된다
- 잘못된 preset 이름을 지정하면 `UserWarning`이 발생하고 기본 설정으로 동작한다

### sample_condition — 조건부 샘플링

`sample_rate`와 독립적으로 동작하는 조건 기반 샘플링:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
# 오류가 발생한 케이스만 기록 (디버깅용)
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kwargs: kwargs.get("ground_truth", "") != "",
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `sample_condition` lambda의 시그니처는 `(args, kwargs) -> bool`이다. `True`를 반환하면 해당 호출을 기록하고, `False`이면 건너뛴다
- `sample_rate`와 함께 사용하면 AND 조건으로 동작한다. 조건 충족 후 추가로 `sample_rate` 확률로 샘플링한다
- 오류가 발생한 케이스만 기록하거나, 특정 사용자 그룹만 추적하는 등 세밀한 샘플링 전략을 구현할 수 있다

### on_record — TaskResult 후처리

`monitor.record_task()` 직전에 실행되는 콜백으로 TaskResult를 보강하거나 교체할 수 있다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
import dataclasses

def add_model_info(task_result):
    """모델명과 버전 정보를 extra에 추가"""
    new_extra = {**task_result.extra, "model": "gpt-4o-mini", "version": "2.0"}
    return dataclasses.replace(task_result, extra=new_extra)

@agent_eval(monitor, task_type="qa", on_record=add_model_info)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `on_record` 콜백은 `TaskResult`를 받아 수정된 `TaskResult`를 반환하거나 `None`을 반환할 수 있다. `None` 반환 시 원본 TaskResult가 그대로 사용된다
- `TaskResult`는 `frozen=True`이므로 `dataclasses.replace()`로 새 인스턴스를 생성해 필드를 변경해야 한다
- 모델 버전, A/B 그룹, 실험 ID 등 외부 메타데이터를 `extra` 필드에 주입하는 용도로 주로 활용한다

### AlertRuleBuilder — 전체 팩토리 메서드

`AlertRuleBuilder`는 5종의 빌트인 팩토리로 자주 쓰는 알림 규칙을 간결하게 생성한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 알림 시스템
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

- `AlertRuleBuilder`의 팩토리 메서드는 자주 쓰는 알림 패턴을 한 줄로 생성한다. 직접 `SimpleTaskAlertRule`을 작성하는 것보다 간결하다
- `cooldown` 파라미터로 동일 규칙이 연속으로 발화되지 않도록 최소 간격(초)을 지정할 수 있다
- `severity="critical"`이면 핸들러 호출 후 로그에도 CRITICAL 레벨로 기록된다

### SimpleTaskAlertRule 고급 설정

`SimpleTaskAlertRule`은 복합 조건, dry_run, 클래스 레벨 쿨다운을 지원한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py — 알림 시스템
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

### RetryConfig — 재시도 + jitter

```python
# 출처: Evaluator_Examples/ch12_decorators.py — RetryConfig
from agent_evaluator.decorators import agent_eval, RetryConfig

@agent_eval(
    monitor,
    task_type="qa",
    retry=RetryConfig(
        max=3,
        jitter_type="full",            # "full" / "decorrelated" / "none"
        max_delay=30.0,                # 최대 대기 시간 상한 (초)
        should_retry=lambda e: isinstance(e, RateLimitError),  # 재시도 조건
    ),
)
def rate_limited_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 12.9 개발자 실전 패턴 모음

### RAG 에이전트 평가 완전 예시

```python
# 출처: Evaluator_Examples/ch12_decorators.py — QuickEval 평가
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
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor, EvalMetadata
from agent_evaluator.decorators import agent_eval

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
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

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

## 12.10 파라미터 × 지표 완전 매핑 — 종합 레퍼런스

실전에서 가장 자주 받는 질문은 "어떤 파라미터를 써야 어떤 지표가 켜지나요?"다. 이 절은 그 질문에 대한 완전한 답이다.

### 지표 × 데코레이터 지원 매트릭스

@@HTML_START@@
<table class="mm-table">
  <thead>
    <tr>
      <th>지표</th>
      <th>@agent_eval</th>
      <th>@batch_eval</th>
      <th>@conversation_eval</th>
    </tr>
  </thead>
  <tbody>
    <tr class="mm-gate-row"><td colspan="4">Gate A–D — 기반 지표</td></tr>
    <tr><td>TCR (태스크 완료율)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Accuracy (정확도)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Hallucination (환각 탐지)</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Quality (응답 품질 5차원)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Latency (지연 시간 + TTFT)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Token Economy (토큰·비용)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr class="mm-gate-row"><td colspan="4">Gate B·F — 에이전틱 지표</td></tr>
    <tr><td>Tool Call (도구 호출 패턴)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Retry / Correction (재시도)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Tool Selection F1</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Agent Coordination (멀티에이전트)</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Workflow Execution</td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr class="mm-gate-row"><td colspan="4">Gate E — 보안 지표</td></tr>
    <tr><td>Input Sanitization</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td></tr>
    <tr><td>Output Leakage</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td></tr>
    <tr><td>Tool Authorization</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td></tr>
    <tr><td>Privilege Escalation</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td></tr>
    <tr><td>Tool Chain Attack</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td></tr>
    <tr class="mm-gate-row"><td colspan="4">Gate G — LLM Judge &nbsp;<small style="font-weight:400;text-transform:none;letter-spacing:0">(llm_judge=LLMJudgeConfig(), 기본 설치 포함)</small></td></tr>
    <tr><td>Completeness</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>Relevance</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>Factual Consistency</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>Toxicity</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>Bias</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>safety_score</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>Faithfulness (RAG, v0.7.6+)</td><td><span class="mm-rag">✅ rag+judge</span></td><td><span class="mm-rag">✅ rag+judge</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr><td>G-Eval 커스텀 (v0.7.6+)</td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-opt">✅ opt-in</span></td><td><span class="mm-na">N/A</span></td></tr>
    <tr class="mm-gate-row"><td colspan="4">대화 지표 &nbsp;<small style="font-weight:400;text-transform:none;letter-spacing:0">(@conversation_eval 전용)</small></td></tr>
    <tr><td>Turn Count</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Overall Score</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Context Retention</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Topic Coherence</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Progressive Depth</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Session Completion</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Avg Turn Latency</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
    <tr><td>Turn Scores</td><td><span class="mm-na">N/A</span></td><td><span class="mm-na">N/A</span></td><td><span class="mm-ok">✅</span></td></tr>
  </tbody>
</table>
<p style="font-size:0.8rem;color:#555;margin-top:-10px">
  <strong>opt-in</strong> = 기본 비활성 — 파라미터 또는 monitor 설정으로 활성화 필요 &nbsp;|&nbsp;
  <strong>rag+judge</strong> = <code>rag_mode=True</code> + <code>llm_judge=LLMJudgeConfig()</code> 조합 필요
</p>
@@HTML_END@@

---

### `@agent_eval` 파라미터 → 지표 활성화 맵

| 파라미터 | 활성화되는 지표 | 비고 |
|---------|--------------|------|
| `task_type="qa"` | Accuracy (QA 모드) | 문자열·Enum 혼용 가능 |
| `task_type="tool_use"` | Tool Call + Tool Selection F1 | Tool 지표 자동 활성 |
| `task_type="information_retrieval"` | Hallucination 보조 입력 준비 | rag_mode 함께 쓸 것 |
| `rag_mode=True` | Hallucination + IR task_type 자동 | context_arg도 자동 설정; + faithfulness (llm_judge 조합 시, v0.7.6+) |
| `context_arg="context"` | Hallucination 컨텍스트 공급 | rag_mode 없이도 사용 가능 |
| `security=SecurityConfig()` | 보안 5종 모두 (temp-override) | finally에서 복원 |
| `llm_judge=LLMJudgeConfig()` | Completeness · Relevance · Factual Consistency · Toxicity · Bias · safety_score | 기본 설치에 포함, temp-override |
| `llm_judge=LLMJudgeConfig(model="claude-...")` | LLM Judge 모델 지정 | None이면 API 키 기반 자동 |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | G-Eval 커스텀 기준 추가 (v0.7.6+) | criteria_scores / criteria_overall 키로 결과 |
| `enable_hallucination_detection=True` | Hallucination 단독 (temp-override) | rag_mode보다 세밀한 제어 |
| `enable_anomaly_detection=True` | AnomalyDetector 임시 활성 | finally에서 복원 |
| `framework="langchain"` | tool_calls · chain_steps · tokens_used 자동 추출 | 21개 프레임워크 지원 |
| `score_fn=my_fn` | Accuracy 완전 대체 | (response, ground_truth) → float |
| `flush_every=N` | N회마다 save_to_file() 자동 | |
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
# 출처: Evaluator_Examples/ch12_decorators.py — LLMJudgeConfig
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(monitor, rag_mode=True,
            llm_judge=LLMJudgeConfig())
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.get(question)
    return llm.generate(question, docs)
# → Hallucination, Faithfulness (LLM Judge), Accuracy, Quality, Latency
```

#### 3. 도구 사용 에이전트
```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
from agent_evaluator import EvalMetadata
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="tool_use", framework="langchain")
def tool_agent(question: str, ground_truth: str = "") -> str:
    result = agent_executor.invoke({"input": question})
    return result["output"]
# → Tool Call 패턴, Tool Selection F1, Retry/Correction, TCR
```

#### 4. 보안 에이전트
```python
# 출처: Evaluator_Examples/ch12_decorators.py — SecurityConfig
from agent_evaluator.decorators import agent_eval, SecurityConfig

@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return agent.process(question)
# → Input Sanitization, Output Leakage, Tool Auth, Privilege Escalation, Chain Attack
```

#### 5. 멀티에이전트 시스템
```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
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
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = ""):
    for chunk in llm.stream(question):
        yield chunk  # ← 첫 yield = TTFT 자동 기록
# → Latency + TTFT, Quality, TCR
```

#### 7. 배치 처리
```python
# 출처: Evaluator_Examples/ch12_decorators.py — 데코레이터 사용
@batch_eval(monitor, task_type="qa",
            concurrency=5)          # concurrency=N → 병렬 처리
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.ask(q) for q in questions]
# → 전체 Gate A-G 지표 + DataFrame 반환
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 6 — batch_eval 병렬
```

#### 8. LLM Judge + G-Eval 커스텀
```python
# 출처: Evaluator_Examples/ch12_decorators.py — LLMJudgeConfig
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(monitor, task_type="qa",
            llm_judge=LLMJudgeConfig(criteria=["medical_accuracy", "citation_quality"]))
def medical_agent(question: str, ground_truth: str = "") -> str:
    return medical_llm.ask(question)
# → Completeness·Relevance·Factual Consistency + criteria_scores {"medical_accuracy": 4, ...}
```

---

## 이 챕터의 핵심

- **데코레이터는 비즈니스 로직을 건드리지 않는다.** `@agent_eval(monitor, task_type="qa")`를 함수 위에 붙이는 것만으로 11개 TaskResult 필드가 자동으로 채워지고 PerformanceMonitor에 기록된다.
- **상황별 데코레이터 선택**: 단일 함수 → `@agent_eval`, 대량 배치 → `@batch_eval`, 멀티턴 → `@conversation_eval`, 데코레이터 불가 → `eval_context`, 설정 공유 → `EvalDecorator`, 빠른 시작 → `QuickEval`.
- **`rag_mode=True`, `security=SecurityConfig()`, `llm_judge=LLMJudgeConfig()`**는 temp-override 패턴으로 동작하여 해당 호출에만 지표를 임시 활성화하고 `finally`에서 원래 상태로 복원한다.
- **`flush_every`와 `alert_rules`**는 모든 데코레이터(`@agent_eval`, `@batch_eval`, `@conversation_eval`, `EvalDecorator`)에 동일한 API로 적용된다.
- **`QuickEval.gate(tcr=85, accuracy=70)`**으로 CI/CD 파이프라인에 품질 게이트를 삽입하여 기준 미달 배포를 자동으로 차단할 수 있다.

---

## 실전 예제

이 챕터에서 다룬 `@agent_eval`, `@batch_eval`, `@conversation_eval`, `QuickEval`, `EvalMetadata`, `eval_context`, `ConversationSession` 직접 사용 전체를 한 파일에서 실행할 수 있다.

**기본 예제**: `Evaluator_Examples/ch12_decorators.py`

**핵심 코드**

**섹션 2 — 커스텀 score_fn / completion_fn**

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 2
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

**섹션 5 — retry=RetryConfig(max=3) + flush_every + alert_rules 조합**

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 5
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

from agent_evaluator.decorators import agent_eval, RetryConfig

@agent_eval(
    monitor, task_type="qa",
    retry=RetryConfig(max=3, on=(ValueError,)),  # ValueError 발생 시만 최대 3회 재시도
    flush_every=5,               # 5건마다 save_to_file() 자동 호출
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

- `retry=RetryConfig(max=3, on=(ValueError,))`로 특정 예외만 재시도한다. `on=` 파라미터는 `RetryConfig` 내부에 있으며 독립적인 `retry_on=` 파라미터는 존재하지 않는다. `attempts` 필드에 실제 시도 횟수가 기록되어 RetryCorrectionTracker에 전달된다
- `flush_every=5`는 5번째 호출마다 `save_to_file()`을 자동 호출한다. 장시간 실행 시 데이터 유실을 방지한다
- `alert_rules=[...]`는 각 태스크 완료 후 즉시 규칙을 평가한다. `slow_alert` 조건(execution_time > 3.0)이 충족되면 handler가 호출된다

**섹션 6 — @batch_eval + return_format="dataframe"**

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 6
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
    flush_every=5,
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
- `on_batch_complete=lambda r: ...` 콜백은 전체 배치가 완료된 후 호출된다
- `shuffle`, `shuffle_seed` 파라미터는 `batch_eval`에 존재하지 않는다. 입력 순서를 섞으려면 호출 전에 Python 리스트를 직접 `random.shuffle()`로 처리한다

```bash
python ch12_decorators.py

agent-eval dashboard results/
```

**예제 구성**

| 섹션 | 다루는 기능 |
|------|-----------|
| 섹션 1 | `@agent_eval` 기본 패턴 (task_type·score_fn·completion_fn) |
| 섹션 2 | 커스텀 `score_fn` / `completion_fn` |
| 섹션 3 | `EvalMetadata` 튜플 반환 — score_fn 우선순위 실증 |
| 섹션 4 | `get_eval_ctx()` 스레드 로컬 — 데코레이터 내부에서 메타데이터 주입 |
| 섹션 5 | `retry=RetryConfig(max=3)` + `flush_every` + `alert_rules` 조합 |
| 섹션 6 | `@batch_eval` — `on_batch_complete` 콜백 · `DataFrame` 반환 · concurrent 배치 |
| 섹션 7 | `@conversation_eval` — 자동/수동 flush 2패턴 |
| 섹션 8 | `QuickEval` Facade — `gate()` · `summary()` · `save()` |
| 섹션 추가 | `ConversationSession` 직접 사용 — `add_turn()` + `compute_metrics()` + `monitor.conversation()` 컨텍스트 매니저 |

**실행 결과 (v0.9.1 기준)**

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

---

## 12.11 Harness Config와 데코레이터 통합

> **이 절에서 배우는 것**: 데코레이터 파라미터에 Harness Config를 연결해 "배포 기준"을 에이전트 함수에 직접 선언하는 방법을 익힌다. 측정(Tracker) + 기준(Config) + 판정(Gate)을 하나의 데코레이터에서 완성한다.

### Harness Engineering 관점: 에이전트가 자신의 배포 기준을 소유한다

데코레이터는 단순한 평가 삽입 도구가 아니다. **배포 기준을 에이전트 함수 바로 옆에 코드로 선언하는 메커니즘**이다.

```python
# 이 함수는 "나는 p95 응답이 3초 이내여야 하고, 반드시 '답변' 키워드를 포함해야 한다"는
# 배포 기준을 스스로 알고 있다.
@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=["답변"], fail_on_violation=True),
    sla=SLAConfig(p95_ms=3000),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

기준이 외부 설정 파일이나 QA 관리자 문서에 흩어져 있으면, 에이전트 코드를 수정할 때 기준도 함께 업데이트해야 한다는 사실을 놓치기 쉽다. 데코레이터에 Config를 붙이면 **에이전트 함수 = 로직 + 배포 기준**이 한 단위가 된다. 이것이 Harness Engineering의 핵심 원칙이다.

반면 수동으로 `PerformanceMonitor`만 사용하면 측정은 되지만 기준 자동 판정(Gate PASS/WARN/FAIL)은 동작하지 않는다. Harness Config는 반드시 데코레이터 또는 `monitor.record_task()` 이전에 Config 인스턴스로 전달되어야 Gate 판정에 반영된다.

### 12.11.1 Harness Config 파라미터 — 단계적 추가 가이드

처음 Harness Config를 적용할 때는 한꺼번에 넣지 말고 단계적으로 추가한다.

**1단계 — 기본 측정만 (Config 없음)**
```python
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# → Accuracy, Latency, TCR 자동 측정. Gate 판정 기준은 없음.
```

**2단계 — Gate A 기준 추가 (지시 이행)**
```python
@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["서울"], fail_on_violation=False),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# → fail_on_violation=False: 위반 시 경고만, 아직 배포 차단 없음. 데이터 축적 단계.
```

**3단계 — Gate D 기준 추가 (성능 계약) + 차단 활성**
```python
@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["서울"], fail_on_violation=True),
    sla=SLAConfig(p95_ms=3000),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# → 기준 위반 시 TaskResult.success=False → TCR 하락 → Gate FAIL 가능
```

> 📋 **QA 관리자와 협업 포인트**: `fail_on_violation=False`로 1~2주 데이터를 쌓은 뒤 QA 관리자와 임계값을 협의하고, 합의된 시점에 `True`로 전환한다.

각 Harness Config는 `@agent_eval` 데코레이터에 **이름 있는 개별 파라미터**로 전달한다. Config 종류마다 파라미터명이 다르다 (예: `instructions=`, `sla=`, `threat_severity=`).

```python
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 Gate A·D — 데코레이터 Config 통합 예제
# 출처: Evaluator_Examples/ch12_decorators.py, 섹션 1 — Harness Config 기본
from agent_evaluator import (
    PerformanceMonitor,
    InstructionConfig, SLAConfig, ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(        # Gate A — 목표달성
        required_keywords=["답변"],        # 응답에 포함되어야 할 키워드
        fail_on_violation=True,
    ),
    sla=SLAConfig(                         # Gate D — 성능계약
        p95_ms=3000,                       # P95 응답시간 3초 이하 (밀리초 단위)
        max_cost_per_task=0.01,
    ),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

`InstructionConfig(fail_on_violation=True)`로 설정하면 기준 위반 시 해당 태스크의 `TaskResult.success`가 `False`로 강제 설정된다. TCR 계산에 반영되어 Gate 판정에 영향을 준다. `SLAConfig`의 시간 기준은 `p95_ms` (밀리초)로 지정하며, `max_p95_latency` (초) 파라미터는 존재하지 않는다.

### 12.11.2 에이전트 유형별 최소 Config 세트

| 에이전트 유형 | 핵심 Config | 선택 Config |
|-------------|------------|------------|
| **기본 QA** | `InstructionConfig` | `SLAConfig` |
| **RAG 에이전트** | `InstructionConfig`, `ReproducibilityConfig` | `FaultToleranceConfig` |
| **도구 사용 에이전트** | `InstructionConfig`, `ScopeConfig`, `SLAConfig` | `LoopDetectionConfig` |
| **보안 민감 에이전트** | `InstructionConfig`, `ThreatSeverityConfig`, `ComplianceConfig` | `ThreatResponseConfig` |
| **멀티에이전트** | `InstructionConfig`, `DeadlockConfig`, `SLAConfig` | `ConsensusConfig` |
| **프로덕션 전체** | 위 전체 조합 | `ObservabilityConfig`, `ErrorDiagnosisConfig` |

### 12.11.3 `RetryConfig`, `LLMJudgeConfig`, `SecurityConfig` 구조화 파라미터

v0.8.1에서 도입된 3종 구조화 Config는 기존 개별 파라미터를 데이터클래스로 묶은 것이다. Harness Config(InstructionConfig 등)와 달리 이 3종은 배포 기준이 아니라 데코레이터 **실행 동작**(재시도·LLM 채점·보안 임시 활성)을 제어한다.

```python
# 출처: Evaluator_Examples/ch12_decorators.py — RetryConfig · LLMJudgeConfig · SecurityConfig
from agent_evaluator.decorators import RetryConfig, LLMJudgeConfig, SecurityConfig

@agent_eval(
    monitor,
    task_type="qa",
    # 재시도 설정 (실행 동작)
    retry=RetryConfig(
        max=3,
        delay=1.0,
        backoff=2.0,
    ),
    # LLM Judge 설정 (Gate G 운영관측성)
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        criteria=["medical_accuracy", "citation_quality"],  # G-Eval 대체
    ),
    # 보안 설정 (Gate E 보안경계)
    security=SecurityConfig(
        allowed_tools=["search", "read"],
    ),
)
def medical_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 12.11.4 데코레이터 + Harness Gate 전체 패턴

측정(데코레이터) + 기준(Config) + 판정(Gate)을 하나의 워크플로우로 연결한다.

```python
# 출처: Evaluator_Examples/ch12_decorators.py — PerformanceMonitor + @agent_eval 통합
from agent_evaluator import (
    PerformanceMonitor, QuickEval,
    InstructionConfig, SLAConfig, ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval, RetryConfig, LLMJudgeConfig, SecurityConfig

# ── 방법 A: PerformanceMonitor + @agent_eval (세밀한 제어) ──
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,   # Gate E
    enable_llm_judge=True,         # Gate G
    judge_sample_rate=0.1,
)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=["답변"], fail_on_violation=True),
    sla=SLAConfig(p95_ms=3000, max_cost_per_task=0.01),  # 밀리초 단위
    threat_severity=ThreatSeverityConfig(warn_score=4.0, fail_score=7.0, fail_on_critical=True),
    retry=RetryConfig(max=2),
    llm_judge=LLMJudgeConfig(criteria=["factual_accuracy"]),
    security=SecurityConfig(allowed_tools=["search"]),
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 평가 실행
for q, gt in test_dataset:
    production_agent(q, ground_truth=gt)

# Harness Gate — 배포 최종 판정
from agent_evaluator import HarnessEvaluationGate

report = monitor.generate_report()
d = report.to_dict()
print(f"Gate A TCR: {d.get('accuracy_metrics', {}).get('tcr', {}).get('tcr', 0):.1%}")
print(f"Gate D p95: {d.get('efficiency_metrics', {}).get('latency', {}).get('p95', 0):.2f}s")
gate = HarnessEvaluationGate(report)
gate.enforce()  # 기준 미달 시 sys.exit(1)

# ── 방법 B: QuickEval (빠른 시작) ──
eval = QuickEval.for_security("results/")  # Gate E 강화 설정

@eval.qa
def simple_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in test_dataset:
    simple_agent(q, ground_truth=gt)

eval.gate(tcr=85, accuracy=70)
eval.save()
```

> 📖 **더 깊이**: Group별 Config 전체 파라미터는 → **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)** §Part 2 Harness Config 레퍼런스 참조.

---

## 12.12 데코레이터 친화적 에이전트 함수 설계 원칙

> **이 섹션은 새 프로젝트를 시작할 때 읽어야 한다.** 이미 기존 프로젝트에 이식하는 경우라면 Ch24.8b를 먼저 읽고 와도 된다.

처음부터 agent-evaluator와 함께 개발할 때, 에이전트 함수를 어떻게 설계하느냐에 따라 나중에 평가를 붙이는 비용이 크게 달라진다. 이 섹션은 그 설계 원칙을 정리한다.

이 원칙들은 "데코레이터를 쓰기 위한 규칙"이 아니다. **데코레이터가 가정하는 구조를 처음부터 가지는 함수를 만드는 방법**이다. 이 원칙을 따르면 `@agent_eval` 한 줄이 항상 성립한다.

---

### 원칙 1: 에이전트 함수는 `str`을 반환한다

`@agent_eval` 데코레이터는 함수의 반환값을 `TaskResult.response: str`로 캡처한다. 이 값이 accuracy scoring(Token F1·Jaccard·LCS·Levenshtein)의 입력이 된다.

```python
# ✗ 이렇게 설계하면 나중에 이식 비용이 발생한다
def qa_agent(question: str) -> dict:
    return {"answer": "...", "sources": [...], "confidence": 0.9}

# ✅ 데코레이터 친화적 설계
def qa_agent(question: str, ground_truth: str = "") -> str:
    result = _internal_rag(question)
    return result["answer"]                     # 평가할 텍스트만 반환
```

**평가 메타데이터를 함께 전달해야 하는 경우**: `EvalMetadata`를 함께 반환한다. 반환값은 `str`로 유지하고, 레이턴시·도구 호출 기록 같은 추가 정보는 두 번째 값으로 전달한다.

```python
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    result = _internal_rag(question)
    # (str, EvalMetadata) 튜플로 반환 — 데코레이터가 자동으로 분리해서 처리한다
    return result["answer"], EvalMetadata(
        latency_ms=result["latency_ms"],
        tool_calls=result["tool_calls"],
        extra={"confidence": result["confidence"], "sources": result["sources"]},
    )
```

---

### 원칙 2: 표준 시그니처를 따른다

`@agent_eval` 계열 데코레이터는 특정 파라미터명을 자동 인식한다. 표준 시그니처를 따르면 데코레이터가 파라미터를 자동으로 매핑한다.

```python
# 단일 태스크 — 표준 시그니처
def my_agent(question: str, ground_truth: str = "") -> str: ...

# RAG 에이전트 — context 파라미터 추가
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str: ...

# 멀티턴 — conversation_eval은 session_id 필요
def chat_agent(session_id: str, question: str, ground_truth: str = "") -> str: ...
```

| 파라미터 | 위치 | 자동 인식 | 용도 |
|----------|------|----------|------|
| `question: str` | 첫 번째 | ✅ | 평가 입력 (task.input) |
| `context: str = ""` | 중간 (선택) | ✅ RAG 모드 시 | 검색된 문서 (faithfulness 평가) |
| `ground_truth: str = ""` | **마지막** | ✅ | 정답 레이블 (accuracy 계산) |

`ground_truth`가 마지막이어야 하는 이유: 데코레이터가 키워드 인자로 주입하므로 위치는 중요하지 않지만, 호출부에서 `agent(question, ground_truth=gt)` 패턴이 일관되게 동작하도록 마지막에 두는 것이 관례다.

---

### 원칙 3: 하나의 함수 = 하나의 평가 단위

에이전트 함수는 하나의 의미 있는 동작만 수행해야 한다. 여러 동작이 하나의 함수에 합쳐지면, 어느 부분이 실패했는지 알 수 없다.

```python
# ✗ 두 가지 동작이 합쳐진 함수 — 실패 원인 추적 불가
@agent_eval(monitor, task_type="document_creation")
def generate_full_lecture(topic: str, ground_truth: str = "") -> str:
    outline = outline_agent(topic)         # 동작 1
    content = content_writer(outline)      # 동작 2
    return content                         # outline 실패인지 content 실패인지 모름

# ✅ 각 동작을 별도 함수로 — 실패 지점 특정 가능
@agent_eval(monitor, task_type="planning")
def outline_agent(topic: str, ground_truth: str = "") -> str:
    return llm.invoke(OUTLINE_PROMPT.format(topic=topic))

@agent_eval(monitor, task_type="document_creation")
def content_writer(outline: str, ground_truth: str = "") -> str:
    return llm.invoke(CONTENT_PROMPT.format(outline=outline))
```

**예외**: 원자성이 과도하게 세분화되면 집계가 의미를 잃는다. 토큰 하나하나를 함수로 만들지 말 것. "하나의 의미 있는 동작"이 기준이다 (→ Ch22.7 원자성 원칙 참조).

---

### 원칙 4: 같은 입력으로 여러 번 호출해도 안전하게 설계한다

데코레이터는 내부적으로 함수를 래핑한다. 재시도 설정(`RetryConfig`)이나 배치 평가에서 같은 함수가 여러 번 호출될 수 있다. 이때 함수 안에서 전역 변수나 외부 파일·DB를 수정하는 부작용이 있으면, 호출 횟수만큼 부작용이 중복 발생한다.

```python
# ✗ 부작용이 있는 함수 — 같은 입력으로 두 번 호출하면 문제 발생
_call_count = 0
@agent_eval(monitor, task_type="qa")
def counter_agent(question: str, ground_truth: str = "") -> str:
    global _call_count
    _call_count += 1              # 평가 재시도 시 카운터가 이중으로 증가
    return llm.invoke(question)

# ✅ 부작용을 함수 외부로 분리 — 함수 자체는 입력만 받아 출력만 반환
@agent_eval(monitor, task_type="qa")
def pure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)   # 같은 입력 → 같은 동작, 부작용 없음

# 호출 횟수 집계 등 부작용은 데코레이터 외부에서 관리
```

**실무 기준**: "이 함수를 지금 상태에서 10번 연속 호출해도 DB나 파일이 망가지지 않는가?" — YES이면 안전한 설계다.

---

### 원칙 5: 실패를 예외로, 빈 문자열을 반환하지 않는다

`@agent_eval`은 빈 문자열(`""`) 반환을 "완료했지만 빈 응답"으로 해석한다. 실패는 예외를 발생시켜야 한다. 그래야 `TaskResult.has_error=True`로 기록되고 Gate C(FaultTolerance)가 올바르게 측정된다.

```python
# ✗ 실패를 빈 문자열로 반환 — Gate C가 실패를 감지하지 못함
@agent_eval(monitor, task_type="qa")
def fragile_agent(question: str, ground_truth: str = "") -> str:
    try:
        return llm.invoke(question)
    except Exception:
        return ""                 # 데코레이터는 "완료"로 기록 — TCR이 부풀려짐

# ✅ 실패는 예외로 전파 — 데코레이터가 자동으로 has_error=True 처리
@agent_eval(monitor, task_type="qa")
def robust_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)   # 예외 발생 시 그대로 전파
    # 데코레이터가 캡처 → TaskResult(has_error=True, error_message=str(e)) 기록
```

---

### 원칙 6: 클래스 메서드보다 평가 전용 함수를 분리하는 것이 낫다

`@agent_eval`을 클래스 메서드에 직접 붙이는 것은 기술적으로는 동작한다. 하지만 현실적인 문제가 있다. `monitor`는 보통 클래스가 정의될 때가 아니라 프로그램이 실행될 때 만들어진다. 클래스 정의 시점에 `@agent_eval(monitor, ...)` 문법을 쓰려면 `monitor`가 이미 존재해야 하는데, 클래스 파일 상단에서 `monitor`를 만드는 것은 전역 상태를 만드는 나쁜 설계다.

```python
# ✗ 클래스 정의 시 monitor 전역 참조가 필요 — 테스트와 재사용이 어려워짐
monitor = PerformanceMonitor("results/")  # 파일 상단 전역 생성

class QAAgent:
    @agent_eval(monitor, task_type="qa")  # 전역 monitor에 의존
    def answer(self, question: str, ground_truth: str = "") -> str:
        return self.llm.invoke(question)

# ✅ 평가용 함수는 인스턴스 생성 후 분리해서 만든다
class QAAgent:
    def answer(self, question: str) -> str:     # 기존 인터페이스 유지
        return self.llm.invoke(question)

    def make_eval_fn(self, monitor: PerformanceMonitor):
        """이 인스턴스를 평가할 함수를 반환한다."""
        agent = self
        @agent_eval(monitor, task_type="qa")
        def _eval_answer(question: str, ground_truth: str = "") -> str:
            return agent.answer(question)       # 인스턴스를 클로저로 캡처
        return _eval_answer

# 사용: qa = QAAgent(); eval_fn = qa.make_eval_fn(monitor)
```

이 패턴은 기존 클래스 인터페이스를 건드리지 않으면서, `monitor`를 원하는 시점에 주입할 수 있다는 장점이 있다.

---

### 설계 원칙 요약

| 원칙 | 핵심 규칙 | 위반 시 비용 |
|------|----------|-------------|
| 1. str 반환 | `-> str`, 추가 정보는 `EvalMetadata` 튜플 반환 | 이식 시 래퍼 + 클로저 필요 |
| 2. 표준 시그니처 | `(question, ..., ground_truth="") -> str` | 데코레이터 파라미터 수동 지정 필요 |
| 3. 원자성 | 함수 1개 = 동작 1개 | 실패 원인 추적 불가 |
| 4. 반복 호출 안전성 | 부작용(전역 변수·파일·DB 수정) 함수 외부로 분리 | 재시도/배치 평가에서 부작용 중복 발생 |
| 5. 예외 전파 | 실패는 `raise`, `""` 반환 금지 | TCR 부풀림, Gate C 측정 무력화 |
| 6. 평가 함수 분리 | 클래스 메서드에 직접 붙이기보다 평가 전용 함수 생성 | 전역 monitor 의존, 테스트 어려움 |

> 이 원칙들은 새 프로젝트에서 데코레이터 비용을 제로로 만드는 설계 가이드다. 기존 프로젝트 이식 방법은 → **[Part VI Ch24](../Part_VI_실전이식가이드/Chapter_24_첫번째_이식.md)** 참조.
