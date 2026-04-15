# 빠른 시작 가이드

Agent Evaluator를 5분 안에 첫 평가까지 완성하는 최단 경로

**v0.8.1 | Python 3.8+**

---

## 목차

1. [설치](#설치)
2. [데코레이터 방식 — 권장](#데코레이터-방식--권장)
3. [헬퍼로 간편하게](#헬퍼로-간편하게)
4. [컨텍스트 매니저 패턴](#컨텍스트-매니저-패턴)
5. [대시보드 실행](#대시보드-실행)
6. [보안·에이전틱 지표 활성화](#보안에이전틱-지표-활성화)
7. [CI/CD 품질 게이팅](#cicd-품질-게이팅)
8. [실시간 운영 모니터링](#실시간-운영-모니터링-v073)
9. [다음 단계](#다음-단계)

---

## 설치

```bash
# 기본 설치 — LLMJudge · 대시보드 · OTEL 모니터링 · PDF 포함
pip install agent-evaluator

# 모든 예제 실행
pip install "agent-evaluator[examples]"

# 프레임워크 통합 (사용자 에이전트가 해당 프레임워크를 사용하는 경우)
pip install "agent-evaluator[langchain]"   # LangChain/LangGraph
pip install "agent-evaluator[eval]"        # DeepEval + Ragas
pip install "agent-evaluator[full]"        # 전체 (⚠️ crewai/autogen 포함, 10분+)
```

> **Python 3.8–3.13** 지원. numpy, pandas는 자동 설치됩니다.

---

## 데코레이터 방식 — 권장

에이전트 함수에 데코레이터 한 줄만 추가하면 자동으로 평가가 적용됩니다. 용도에 따라 **3개의 핵심 데코레이터**가 제공됩니다.

### 1. @agent_eval (단일 호출)

가장 일반적인 에이전트 호출 평가에 사용합니다.

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 실행 시 자동으로 TaskResult 1개가 기록됨
my_agent("한국의 수도는?", ground_truth="서울")
```

### 2. @batch_eval (대량 처리)

리스트 형태의 입력을 받아 일괄 평가할 때 사용합니다.

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa")
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

### 3. @conversation_eval (멀티턴 대화)

연속적인 대화 세션의 맥락 유지율 등을 평가합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

# 동일 sid 호출 시 턴 자동 누적
chat_agent("안녕", sid="user_1")
chat_agent("날씨 알려줘", sid="user_1")

# 세션 명시적 종료 및 지표 기록
flush_conversation("user_1")
```

> **QuickEval**: 위 데코레이터들을 더 짧게 설정하고 싶다면 `eval = QuickEval("results/")` 팩토리를 사용하세요. (`@eval.qa`, `@eval.rag` 등 지원)

---

## 저수준 직접 기록 (탈출구)

> **데코레이터를 붙일 수 없는 경우에만 사용하세요.** 외부 라이브러리 함수, lambda, 동적 호출 등 일반적인 에이전트 평가는 앞 섹션의 데코레이터 방식을 권장합니다.

`create_taskresult()`는 question/response/ground_truth로 점수를 자동 계산합니다.

```python
from agent_evaluator import create_taskresult, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

# 점수 자동 계산 — accuracy_score, completion_score 불필요
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",        # qa | code_generation | data_analysis | ...
)

monitor.record_task(result)
monitor.save_to_file("eval")
```

여러 태스크를 메서드 체이닝으로 기록할 수 있습니다.

```python
monitor.record_task(r1).record_task(r2).record_task(r3)
report = monitor.generate_report()
```

---

## 컨텍스트 매니저 패턴 (탈출구)

> **데코레이터를 붙일 수 없는 외부 코드**에서 사용합니다. 일반적인 에이전트 함수는 `@agent_eval` 데코레이터를 사용하세요.

`eval_context`는 `@agent_eval`과 동일한 평가를 with 블록으로 제공합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import eval_context

monitor = PerformanceMonitor(output_dir="results/")

# eval_context — 외부 함수 / 데코레이터 불가 시 1건씩 기록
with eval_context(monitor, task_type="qa",
                  question="한국의 수도는?", ground_truth="서울") as ctx:
    ctx.response = external_lib.call("한국의 수도는?")

monitor.save_to_file("eval")
# 자동으로 results/eval.json + .html 저장
```

비동기 에이전트도 지원합니다.

```python
async with eval_context(monitor, task_type="qa", question=q) as ctx:
    ctx.response = await async_external.call(q)
```

`evaluation_session`은 세션 단위 자동 저장이 필요할 때 사용합니다. 내부에서 `eval_context`와 함께 사용하면 각 태스크가 자동으로 기록됩니다.

```python
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("output_filename") as monitor:
    for item in dataset:
        with eval_context(monitor, task_type="qa",
                          question=item["question"],
                          ground_truth=item["answer"]) as ctx:
            ctx.response = external_agent.run(item["question"])
# 블록 종료 시 results/output_filename.json + .html 자동 저장 (예외 발생 시에도 안전)
```

---

## 대시보드 실행

대시보드는 `results/` 디렉토리의 JSON 파일을 로드합니다. **먼저 평가 결과를 파일로 저장한 후** 실행하세요.

```python
# 방법 A: 데코레이터 실행 후 save_to_file()
monitor.save_to_file("eval")     # results/eval.json + .html 생성

# 방법 B: auto_save — N건마다 자동 저장
monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# 방법 C: QuickEval
eval = QuickEval("results/")
eval.save()                      # results/quickeval.json + .html
```

```bash
# 기본 실행 (포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 옵션
agent-eval dashboard --port 8080 --watch     # 포트 지정 + 파일 감시
agent-eval dashboard --no-open               # 브라우저 자동 오픈 비활성화
agent-eval dashboard --offline               # CDN 에셋 로컬 캐시
```

---

## 보안·에이전틱 지표 활성화

```python
# 보안 지표 (Layer 2 Security)
monitor = PerformanceMonitor.for_secure_agents(
    output_dir="results/",
    security_config={
        "allowed_tools": ["search", "read"],
        "restricted_tools": ["delete", "execute"],
    },
)

# RAG 평가 (Hallucination 탐지 기본 활성)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
```

---

## CI/CD 품질 게이팅

```bash
# TCR 85% + Accuracy 70% 미만이면 exit 1 반환
agent-eval gate results/eval.json --tcr 85 --accuracy 70
```

---

## 실시간 운영 모니터링 (v0.7.6)

Phoenix + OpenTelemetry로 프로덕션 스팬을 실시간 추적합니다. **`setup_otel()`을 PerformanceMonitor 생성 전에 호출해야 합니다.**

```bash
# 터미널 1 — Phoenix 서버 기동 (기본 설치에 포함)
agent-eval monitor                           # UI: http://localhost:6006
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

```bash
# 설치 상태 확인
agent-eval monitor --check
```

> 자세한 내용: [12_MONITOR_GUIDE.md](12_MONITOR_GUIDE.md)

---

## 다음 단계

| 목적 | 문서 |
|------|------|
| 25개 지표 상세 (공식·출력키·임계값) | [02_METRICS_REFERENCE.md](02_METRICS_REFERENCE.md) |
| 프레임워크 통합 (LangChain/CrewAI/AutoGen/LangGraph) | [03_FRAMEWORK_GUIDE.md](03_FRAMEWORK_GUIDE.md) |
| 골든 데이터셋 구성 | [04_GOLDEN_DATASET_GUIDE.md](04_GOLDEN_DATASET_GUIDE.md) |
| 품질 임계값 설정 | [05_THRESHOLD_GUIDE.md](05_THRESHOLD_GUIDE.md) |
| 전체 API 레퍼런스 | [07_API_REFERENCE.md](07_API_REFERENCE.md) |
| 대시보드 UI 상세 | [08_DASHBOARD_GUIDE.md](08_DASHBOARD_GUIDE.md) |
| 실시간 모니터링 (Phoenix + OTEL) | [12_MONITOR_GUIDE.md](12_MONITOR_GUIDE.md) |
| 사용 예제 파일 | [Evaluator_Examples/](../Evaluator_Examples/) |
