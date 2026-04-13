# Chapter 02: Agent-Evaluator 첫 시작

> 좋은 도구는 처음 사용하는 순간부터 작동해야 한다.

---

## 2.1 설치 — 용도별 extras 선택 가이드

Agent-Evaluator는 v0.7.8부터 기본 설치(`pip install agent-evaluator`)에 SDK 전체 기능이 포함됩니다. LLM Judge 엔진, FastAPI 대시보드, OTEL 모니터링, PDF 처리를 별도 설치 없이 바로 사용할 수 있습니다.

### 기본 설치에 포함된 기능

| 기능 | 패키지 |
|---|---|
| Layer 1+2 네이티브 지표 | numpy, pandas, python-dotenv |
| LLM Judge 엔진 | openai, anthropic |
| FastAPI 대시보드 | fastapi, uvicorn, jinja2, python-multipart |
| OTEL 모니터링 | opentelemetry-sdk, arize-phoenix |
| PDF 처리 | pdfplumber |

### 별도 설치가 필요한 extras

| extras | 포함 패키지 | 사용 시기 |
|---|---|---|
| `[eval]` | deepeval, ragas, datasets | Layer 3 외부 평가 도구 연동 |
| `[langchain]` | langchain, langchain-core, langgraph | LangChain/LangGraph 프레임워크 사용 시 |
| `[dspy]` | dspy-ai | DSPy 프로그램 평가 |
| `[pydanticai]` | pydantic-ai | PydanticAI Agent 평가 |
| `[crewai]` | crewai | CrewAI (전이 의존성 100개+, 단독 설치 권장) |
| `[autogen]` | pyautogen, autogen-agentchat | AutoGen (무거움, 단독 설치 권장) |
| `[examples]` | 기본 + eval 묶음 | 모든 예제 실행 |
| `[full]` | 위 전체 | 모든 기능 (설치 10분+ 소요) |

```bash
# 기본 설치 — LLMJudge · 대시보드 · OTEL 모니터링 · PDF 포함 (권장)
pip install agent-evaluator

# LangChain 프레임워크 통합
pip install "agent-evaluator[langchain]"

# DeepEval/Ragas 외부 평가 도구 연동
pip install "agent-evaluator[eval]"

# 모든 예제 실행
pip install "agent-evaluator[examples]"

# 전체 설치 (⚠️ crewai/autogen 포함, 10분+)
pip install "agent-evaluator[full]"

# 설치 확인
agent-eval --version
# → agent-evaluator 0.8.0
```

> 👨‍💻 **개발자 TIP**: `[crewai]`와 `[autogen]`은 의존성이 무거워 단독 extras로 분리되어 있습니다. CrewAI와 AutoGen을 동시에 설치하면 pydantic 버전 충돌이 발생할 수 있으므로, 필요한 경우에만 하나씩 설치하세요.

---

## 2.2 환경 변수 설정 (.env 파일 패턴)

Agent-Evaluator는 소스 코드에 API 키를 하드코딩하지 않는 것을 원칙으로 합니다. 프로젝트 루트에 `.env` 파일을 만들어 관리하는 것을 권장합니다.

```bash
# .env (프로젝트 루트에 생성)

# LLM API 키 (Layer 3 LLM Judge 사용 시 필요)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 결과 저장 경로 (생략 시 자동 감지)
# AGENT_EVALUATOR_OUTPUT_DIR=/path/to/results
# AGENT_EVALUATOR_ROOT=/path/to/project
```

`.env` 파일을 로드하는 방법은 두 가지입니다.

```python
# 방법 1: SDK가 자동 로드 (권장)
from agent_evaluator import load_env
load_env()  # 프로젝트 루트의 .env 자동 탐지 후 로드

# 방법 2: python-dotenv 직접 사용
from dotenv import load_dotenv
load_dotenv()
```

**저장 경로 자동 감지**: `output_dir`를 별도로 지정하지 않으면 SDK가 다음 순서로 경로를 자동 결정합니다.

1. 환경 변수 `AGENT_EVALUATOR_OUTPUT_DIR` (최우선)
2. 환경 변수 `AGENT_EVALUATOR_ROOT` 아래 `results/`
3. Git 저장소 루트 아래 `results/`
4. 현재 작업 디렉토리 아래 `results/` (폴백)

Git 저장소에서 작업한다면 별도 설정 없이도 항상 올바른 위치에 저장됩니다.

> 📋 **QA 관리자 TIP**: `.env` 파일은 `.gitignore`에 반드시 추가하세요. API 키가 저장소에 노출되면 심각한 보안 문제가 발생할 수 있습니다. `.env.example` 파일을 만들어 팀원이 필요한 변수 목록을 알 수 있도록 공유하는 것을 권장합니다.

> 📖 **더 깊이 알고 싶다면**: 지원되는 환경변수 전체 목록과 각 변수의 동작 방식은 **[Appendix C — 환경변수 & 설정 레퍼런스](../Appendix/C_환경변수_설정_레퍼런스.md)**를 참조하세요.

---

## 2.3 5분 안에 첫 평가 실행하기

가장 짧은 코드로 첫 평가를 실행해보겠습니다. `QuickEval`은 모니터 초기화, 데코레이터 설정, 결과 저장을 하나의 인터페이스로 통합한 원스톱 Facade입니다.

```python
# quick_start.py
from agent_evaluator import QuickEval

# 1. QuickEval 초기화 (output_dir 생략 시 자동 감지)
eval = QuickEval("results/")

# 2. 평가할 에이전트 함수에 데코레이터 적용
@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 로직 (여기서는 간단한 예시)
    answers = {
        "한국의 수도는?": "서울입니다.",
        "파이썬 창시자는?": "귀도 반 로섬입니다.",
    }
    return answers.get(question, "모르겠습니다.")

# 3. 평가 실행
my_agent("한국의 수도는?", ground_truth="서울")
my_agent("파이썬 창시자는?", ground_truth="귀도 반 로섬")
my_agent("우주의 나이는?", ground_truth="138억 년")

# 4. 결과 저장 및 확인
eval.save()  # results/quickeval.json + results/quickeval.html 생성
print(eval.summary())
```

실행하면 터미널에 다음과 같은 출력이 나타납니다.

```
{
  "task_completion_rate": 0.667,
  "accuracy": 0.823,
  "p95_latency": 0.003,
  "total_cost_usd": 0.0,
  "quality_avg": 0.756
}
```

평가 결과 파일이 `results/quickeval.json`과 `results/quickeval.html`로 저장됩니다. HTML 파일을 브라우저에서 열면 시각화된 리포트를 확인할 수 있습니다.

> 👨‍💻 **개발자 TIP**: `@eval.qa`는 `task_type="qa"`로 설정된 단축 데코레이터입니다. 이 외에도 `@eval.rag`, `@eval.tool_use`, `@eval.code`, `@eval.reasoning`, `@eval.planning` 등의 단축 데코레이터가 제공됩니다. 에이전트의 성격에 맞는 task_type을 선택하면 해당 유형에 최적화된 지표가 활성화됩니다.

---

## 2.4 SDK 3-레이어 구조 한눈에 보기

Agent-Evaluator의 25개 지표는 세 개의 레이어로 구성됩니다. 레이어별로 활성화 조건과 외부 의존성이 다릅니다.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3 — 하이브리드 평가 (opt-in, 외부 의존성 필요)      │
│  DeepEvalAdapter, RagasAdapter                           │
│  → [eval] extras 설치 + API 키 필요                      │
├─────────────────────────────────────────────────────────┤
│  Layer 2 — 에이전틱 + 보안 지표 (조건부 활성)              │
│  ToolCallAnalyzer, RetryCorrectionTracker,               │
│  ToolSelectionTracker, AgentCoordinationTracker,         │
│  WorkflowExecutionTracker                                │
│  + 보안 5종: Input/Output/Auth/Escalation/ChainAttack   │
│  → enable_security_metrics=True 로 보안 지표 활성화       │
├─────────────────────────────────────────────────────────┤
│  Layer 1 — 기반 지표 6종 (항상 자동 활성, LLM 불필요)      │
│  TaskCompletionTracker  → Task Completion Rate (TCR)    │
│  AccuracyEvaluator      → QA / Code 정확도               │
│  HallucinationDetector  → 사실 일관성 점수                │
│  ResponseQualityEvaluator → 5차원 품질 평가               │
│  LatencyTracker         → 백분위수 기반 레이턴시           │
│  TokenEconomyTracker    → 토큰 사용량 + 비용 추정          │
└─────────────────────────────────────────────────────────┘
```

### Layer 1: 기반 지표 6종 (항상 자동 활성)

Layer 1은 `PerformanceMonitor`를 생성하는 즉시 자동으로 활성화됩니다. 외부 API 호출이 없으며, 모든 계산이 로컬에서 밀리초 단위로 완료됩니다.

| 트래커 | 측정 지표 | 출력 키 |
|---|---|---|
| TaskCompletionTracker | 작업 완료율 (TCR) | `task_completion_rate` |
| AccuracyEvaluator | F1/LCS/Jaccard 기반 정확도 | `accuracy` |
| HallucinationDetector | 사실 일관성 점수 | `hallucination_score` |
| ResponseQualityEvaluator | 관련성/일관성/명확성/완전성/유용성 | `response_quality` |
| LatencyTracker | p50/p95/p99 레이턴시 | `latency_p50`, `latency_p95` |
| TokenEconomyTracker | 토큰 사용량 + 비용 추정 | `tokens_used`, `estimated_cost` |

### Layer 2: 에이전틱 + 보안 지표 (조건부 활성)

Layer 2는 도구 호출, 멀티에이전트 협업, 워크플로우 등 에이전트 고유의 동작을 측정합니다. `TaskResult`에 `tool_calls`, `agent_interactions` 등 에이전틱 데이터가 포함될 때 자동으로 계산됩니다.

보안 지표 5종은 성능에 영향을 줄 수 있어 기본적으로 비활성화되어 있습니다. `enable_security_metrics=True`로 명시적으로 활성화해야 합니다.

```python
# 보안 지표 활성화
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True
)

# 또는 팩토리 메서드 사용 (보안에 최적화된 설정)
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

### Layer 3: 외부 평가 도구 (opt-in)

Layer 3는 DeepEval, Ragas 등 외부 평가 라이브러리와 연동합니다. `[eval]` extras를 설치하고 `HybridPerformanceMonitor`를 사용하면 됩니다.

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_deepeval=True,    # DeepEval 지표 활성
    enable_ragas=True,       # Ragas 지표 활성
)
```

---

## 2.5 세 가지 결과 출력 시나리오

Agent-Evaluator는 평가 결과를 세 가지 방식으로 출력할 수 있습니다. 상황에 따라 적합한 방식을 선택하면 됩니다.

### 시나리오 ① 터미널 출력 — 빠른 확인

개발 중 빠르게 결과를 확인할 때 사용합니다. 별도 서버나 파일이 필요 없습니다.

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(output_dir="results/")

# 태스크 기록
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",
)
monitor.record_task(result)

# 리포트 생성 및 터미널 출력
report = monitor.generate_report()
import json
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
```

출력 예시:

```json
{
  "summary": {
    "total_tasks": 1,
    "task_completion_rate": 1.0,
    "accuracy": 0.923,
    "response_quality": 0.812,
    "latency_p95": 0.8,
    "tokens_used_total": 0
  },
  "layer1": {
    "task_completion": {"rate": 1.0, "successful": 1, "failed": 0},
    "accuracy": {"overall": 0.923, "token_overlap_f1": 0.941},
    ...
  }
}
```

### 시나리오 ② 대시보드 — 시각화 UI

팀 내 공유나 지속적인 품질 모니터링에 적합합니다. JSON 파일을 저장한 후 로컬 FastAPI 서버로 시각화합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 로직
    return llm.invoke(question)

# 여러 케이스 평가
test_cases = [
    ("한국의 수도는?", "서울"),
    ("파이썬 창시자는?", "귀도 반 로섬"),
    ("HTTP 상태 코드 404는?", "찾을 수 없음"),
]
for question, answer in test_cases:
    my_agent(question, ground_truth=answer)

# JSON + HTML 파일 저장
monitor.save_to_file("evaluation")
# → results/evaluation_evaluation.json
# → results/evaluation_report.html
```

파일이 저장되면 별도 터미널에서 대시보드를 실행합니다.

```bash
# 대시보드는 기본 설치에 포함 — 바로 실행 가능
agent-eval dashboard results/ --watch

# → http://localhost:8765 에서 브라우저로 확인
# --watch 옵션: results/ 폴더에 새 JSON이 추가되면 자동 반영
```

대시보드는 품질, 성능, 에이전틱, 보안, 비용 등 9개 탭으로 구성됩니다. 여러 평가 파일을 비교하거나, 시계열로 품질 추이를 확인할 수 있습니다.

### 시나리오 ③ OTEL Phoenix — 실시간 운영 모니터링

프로덕션 환경에서 에이전트 실행을 실시간으로 추적할 때 사용합니다. OpenTelemetry 기반으로 스팬을 자동 발행하고, Arize Phoenix UI에서 분산 트레이싱을 확인합니다.

**터미널 1 — Phoenix 서버 기동:**

```bash
# OTEL 모니터링은 기본 설치에 포함 — 바로 Phoenix 서버 시작 가능
# Phoenix 서버 시작 (UI: http://localhost:6006)
agent-eval monitor

# 포트 지정 시
agent-eval monitor --port 6006

# 설치 상태 확인
agent-eval monitor --check
```

**터미널 2 — 에이전트 코드:**

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# setup_otel()은 PerformanceMonitor 생성 전에 반드시 호출
setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-qa-agent"
)

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 호출 시 OTLP 스팬 자동 전송 → Phoenix Tracing 탭에서 실시간 확인
my_agent("한국의 수도는?", ground_truth="서울")
```

에이전트가 실행될 때마다 Phoenix의 Tracing 탭에 스팬이 실시간으로 쌓입니다. 각 스팬에는 `ae.tcr`, `ae.accuracy`, `ae.execution_time`, `ae.tool_calls`, `ae.framework` 등의 속성이 포함되어 있어 Agent-Evaluator 지표를 Phoenix에서 바로 확인할 수 있습니다.

> 👨‍💻 **개발자 TIP**: `setup_otel()`의 endpoint에는 경로(`/v1/traces`)를 붙이지 마세요. SDK가 내부적으로 올바른 엔드포인트 경로를 구성합니다. 올바른 형식: `"http://localhost:6006"`. 잘못된 형식: `"http://localhost:6006/v1/traces"`.

---

## 2.6 언제 어느 출력을 쓰는가 — 상황별 결정표

세 가지 출력 방식 중 어떤 것을 사용해야 하는지는 상황에 따라 다릅니다.

| 상황 | 권장 방법 | 이유 |
|---|---|---|
| 개발 중 빠른 검증 | 터미널 출력 (`generate_report()`) | 추가 설치 불필요, 즉각적인 피드백 |
| 팀 리뷰 또는 결과 공유 | 대시보드 (`save_to_file` + `agent-eval dashboard`) | 시각화 UI, 여러 파일 비교 가능 |
| CI/CD 파이프라인 게이팅 | CLI (`agent-eval gate`) | 임계값 미달 시 `exit 1` 반환, 자동화 적합 |
| 프로덕션 실시간 모니터링 | OTEL Phoenix (`setup_otel` + `agent-eval monitor`) | 분산 트레이싱, 실시간 이상 탐지 |
| 배치 오프라인 평가 | `evaluation_session` 컨텍스트 매니저 | 대량 데이터셋 안전 처리, 예외 시 자동 저장 |
| 에이전트 A/B 비교 | `QuickEval.compare(other)` | 두 버전 지표 통계 비교 |

### CI/CD 게이팅 예시

```bash
# GitHub Actions 또는 Jenkins에서
python run_evaluation.py        # 평가 실행 → results/eval.json 생성
agent-eval gate results/evaluation_evaluation.json --tcr 85 --accuracy 70
# TCR < 85% 또는 Accuracy < 70% 이면 exit 1 → 파이프라인 중단
```

### QuickEval로 A/B 비교

```python
from agent_evaluator import QuickEval

# 버전 A 평가
eval_a = QuickEval("results/version_a/")

@eval_a.qa
def agent_v1(question: str, ground_truth: str = "") -> str:
    return model_v1.invoke(question)

for q, gt in test_dataset:
    agent_v1(q, ground_truth=gt)
eval_a.save("v1")

# 버전 B 평가
eval_b = QuickEval("results/version_b/")

@eval_b.qa
def agent_v2(question: str, ground_truth: str = "") -> str:
    return model_v2.invoke(question)

for q, gt in test_dataset:
    agent_v2(q, ground_truth=gt)
eval_b.save("v2")

# 비교
comparison = eval_a.compare(eval_b)
print(comparison)
```

---

> **이 챕터의 핵심**
>
> - v0.7.8부터 기본 설치(`pip install agent-evaluator`)에 LLM Judge · 대시보드 · OTEL 모니터링 · PDF가 포함됩니다. 프레임워크별 통합이 필요하면 `[langchain]`, DeepEval/Ragas가 필요하면 `[eval]`을 추가 설치하세요.
> - API 키는 `.env` 파일로 관리하고, Git에 커밋하지 마세요. Layer 1+2 네이티브 지표 16개는 API 키 없이 동작합니다.
> - `QuickEval`을 사용하면 2줄로 첫 평가를 시작할 수 있습니다.
> - 3-레이어 구조에서 Layer 1은 항상 자동 활성, Layer 2 보안 지표는 `enable_security_metrics=True`로 활성화, Layer 3는 외부 패키지 설치 후 opt-in입니다.
> - `setup_otel()`은 반드시 `PerformanceMonitor` 생성 전에 호출하고, endpoint에 경로를 붙이지 마세요: `"http://localhost:6006"`.

---

## 실전 예제

챕터 2에서 설명한 첫 시작 과정을 `04_decorator_quickeval.py`로 바로 체험할 수 있다. `QuickEval` 2줄 시작, `@eval.qa` 데코레이터, `eval.save()`와 `eval.gate()`를 한 파일에서 모두 확인한다.

**파일**: `Evaluator_Examples/04_decorator_quickeval.py`

**핵심 코드 (출처: `Evaluator_Examples/04_decorator_quickeval.py`)**

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 1 — @agent_eval 기본 사용
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 로직 위치
    return "에이전트 응답 텍스트"

# 호출하면 자동으로 AccuracyEvaluator + LatencyTracker + TCR 집계
my_agent("한국의 수도는?", ground_truth="서울")

# 보고서 저장 (JSON + HTML 동시 생성)
monitor.save_to_file("my_first_eval")
```

- `@agent_eval`은 함수 실행 시간을 자동 측정하고 LatencyTracker에 기록한다
- `ground_truth`를 전달하면 AccuracyEvaluator가 TokenF1·Jaccard·LCS·Char Similarity 4종 혼합으로 정확도를 계산한다
- `save_to_file("name")`은 `results/name.json`과 `results/name.html` 두 파일을 생성한다

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 8 — QuickEval 원스톱 Facade
from agent_evaluator import QuickEval

# PerformanceMonitor + EvalDecorator를 1줄로 설정
eval_qe = QuickEval("results/")

@eval_qe.qa  # task_type="qa" 단축 데코레이터
def qa_agent(question: str, ground_truth: str = "") -> str:
    return "QA 에이전트 응답"

@eval_qe.rag  # task_type="information_retrieval" + context_arg="context"
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return "RAG 에이전트 응답"

# 여러 태스크 실행
qa_agent("수도는?", ground_truth="서울")
qa_agent("인구는?", ground_truth="5천만")

# CI/CD 게이팅 — TCR 85% 미달 시 sys.exit(1)
eval_qe.gate(tcr=85, accuracy=70)

# JSON + HTML 저장
eval_qe.save()
```

- `QuickEval`은 `PerformanceMonitor`와 `EvalDecorator`를 내부에서 조합한 Facade 클래스다
- `@eval_qe.qa`, `@eval_qe.rag` 등 11종의 단축 데코레이터로 태스크 유형별 설정을 자동 적용한다
- `gate(tcr=85)`는 TCR이 85% 미만이면 `sys.exit(1)`을 호출해 CI/CD 파이프라인을 중단시킨다

```bash
pip install agent-evaluator       # 기본 설치 (LLMJudge·대시보드·OTEL 포함)
python Evaluator_Examples/04_decorator_quickeval.py
agent-eval dashboard results/     # http://localhost:8765
```

**첫 시작 4단계와 예제 매핑**

| 단계 | 코드 | 예제 파일·섹션 |
|------|------|---------------|
| 1. 설치 | `pip install agent-evaluator` | — |
| 2. QuickEval 생성 | `eval = QuickEval("results/")` | 04_decorator_quickeval, 섹션 1 |
| 3. 데코레이터 적용 | `@eval.qa` / `@eval.rag` | 04_decorator_quickeval, 섹션 1~3 |
| 4. 저장·게이팅 | `eval.save()` / `eval.gate(tcr=80)` | 04_decorator_quickeval, 섹션 7~8 |

**실행 결과 (v0.8.0 기준)**

```
=== 04. 데코레이터 · QuickEval 종합 예제 ===
QuickEval("results/"): 초기화 완료

섹션 1: @eval.qa 기본
  14개 태스크 | TCR=57.1% | avg_accuracy=0.712

섹션 7: eval.gate(tcr=80, accuracy=70)
  ❌ 게이팅 실패 — TCR 57.1% < 80.0%
  (--tcr 50으로 완화 시 ✅ 통과)

결과 저장: results/quickeval.json + results/quickeval.html
```

> **2줄 시작 코드**: `eval = QuickEval("results/")` 한 줄로 `PerformanceMonitor` + `EvalDecorator`가 모두 설정된다. API 키 없이도 Layer 1+2 16개 지표를 측정하며, `ANTHROPIC_API_KEY` 설정 시 LLMJudge가 자동 활성화된다.
