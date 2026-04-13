# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.8.0 (Beta)
- **Python:** 3.8+
- **License:** MIT
- **Author:** Sungwoo Kim

---

## Common Commands

```bash
# 개발 환경 설치
pip install -e ".[dev]"

# ── Group 1: SDK 자체 기능 (LLMJudge · 대시보드 · 모니터 · PDF) ──────────
pip install -e ".[sdk]"               # SDK 전체 묶음 — llm+serve+otel+pdf (운영 권장)

# ── Group 2: Evaluator_Examples/ 예제 실행 ────────────────────────────────
# 예제 01~06: 코어만으로 실행 (추가 설치 불필요)
# 예제 07 (Phoenix Hybrid): llm+otel+eval 필요
pip install -e ".[examples]"          # 모든 예제 실행 가능 (sdk + eval)

# ── Group 3: 프레임워크 확장 ──────────────────────────────────────────────
pip install -e ".[eval]"               # DeepEval / Ragas 외부 평가 라이브러리
pip install -e ".[langchain]"          # LangChain / LangGraph 통합
pip install -e ".[dspy]"              # DSPy 통합 (dspy-ai)
pip install -e ".[pydanticai]"        # PydanticAI 통합 (pydantic-ai)
pip install -e ".[crewai]"            # CrewAI 단독 (무거움 — 전이 의존성 100개+)
pip install -e ".[autogen]"           # AutoGen 단독 (무거움, 단독 격리)

# ── 조합 편의 extras ────────────────────────────────────────────────────
pip install -e ".[full]"              # 전체 (⚠️ crewai/autogen 포함, 10분+ 소요)

# --- CLI (pip install 후 바로 사용 가능) ---
agent-eval init          # 대화형 API 키 설정 마법사
agent-eval check         # 현재 설정 상태 출력
agent-eval dashboard     # FastAPI 대시보드 실행 (기본 포트 8765)  [serve extra 필요]
agent-eval gate result.json --tcr 85 --accuracy 70   # CI/CD 품질 게이팅
agent-eval dataset build results/ --min-score 0.8    # 골든 데이터셋 자동 추출
agent-eval monitor                                   # Arize Phoenix 서버 기동 + OTLP 스팬 수신 설정 (운영 실시간 모니터링)
agent-eval monitor --port 6006                       # Phoenix 포트 지정 (기본: 6006)
agent-eval monitor --check                           # OTEL 패키지 설치 여부 및 포트 점유 상태 확인
# 예제 실행 시 자동으로 Phoenix에 연결 → 프로젝트별 Tracing·Evaluators·Datasets·Prompts 확인 가능
# (기본 설치에 포함 — 별도 extras 불필요)
agent-eval trend results/                            # 최근 10개 결과 파일의 TCR·정확도 추세 분석
agent-eval trend results/ --window 5                 # 최근 5개 파일만 분석
agent-eval trend results/ --fail-on-regression       # 회귀 감지 시 exit 1 (CI/CD 실패 처리)
agent-eval trend results/ --output-json trend.json   # 분석 결과 JSON 저장
agent-eval --version     # 버전 출력

# 테스트 실행
pytest

# 코드 품질
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/

# 빌드 / PyPI 배포
pip install hatchling build twine
python -m build
twine upload --repository testpypi dist/*   # 테스트
twine upload dist/*                          # 실제 배포
```

---

## Architecture

### Three-Layer Evaluation System

```
Layer 1 — Foundation Metrics (native, no external deps)
  TaskCompletionTracker     → Task Completion Rate (TCR)
  AccuracyEvaluator         → QA / Code / General accuracy
  HallucinationDetector     → Fact consistency scoring
  ResponseQualityEvaluator  → 5-dimension quality assessment
  LatencyTracker            → Percentile-based latency
  TokenEconomyTracker       → Token usage + cost estimation

Layer 2 — Agentic Metrics (native, no external deps)
  ToolCallAnalyzer          → Tool usage patterns
  RetryCorrectionTracker    → Retry behavior
  ToolSelectionTracker      → F1-based tool selection accuracy
  AgentCoordinationTracker  → Multi-agent interaction
  WorkflowExecutionTracker  → Workflow success/branching
  InputSanitizationTracker  → Security: input injection detection
  OutputLeakageDetector     → Security: sensitive data in output
  ToolAuthorizationTracker  → Security: unauthorized tool use
  PrivilegeEscalationDetector → Security: privilege abuse
  ToolChainAttackDetector   → Security: chained attack patterns

Layer 3 — Hybrid Evaluation (requires optional deps)
  HybridPerformanceMonitor  → Layer 1+2 + external metric adapters
  DeepEvalAdapter           → DeepEval library integration
  RagasAdapter              → RAGAS RAG evaluation
  LLMJudge (native)         → faithfulness + judge_criteria (G-Eval/Ragas 대체)
```

### Module Layout

```
agent_evaluator/
├── decorators.py            # agent_eval · batch_eval · conversation_eval · EvalDecorator · EvalMetadata
├── quick_eval.py            # QuickEval — 원스톱 평가 Facade (v0.7.1+)
├── core/
│   ├── agent_evaluator.py   # re-export facade — trackers/ 분리 완료
│   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   ├── monitor_context.py   # Context managers
│   ├── otel/                # OpenTelemetry 통합 (v0.7.0+, 기본 설치에 포함)
│   │   ├── provider.py      # OTELProvider — TracerProvider 설정
│   │   └── metrics.py       # OTELMetrics — 메트릭 익스포터 (opt-in)
│   └── trackers/            # 트래커 서브패키지
│       ├── base.py          # BaseTracker, TaskResult, EvaluationReport, TaskType
│       ├── layer1.py        # Layer 1: TaskCompletion·Accuracy·Hallucination·Quality·Latency·TokenEconomy
│       ├── layer2.py        # Layer 2: ToolCall·Retry·ToolSelection·Coordination·Workflow
│       ├── security.py      # Layer 2 보안: InputSanitization·OutputLeakage·ToolAuth·Escalation·ChainAttack
│       ├── conversation.py  # ConversationSession·ConversationMetrics·ConversationTurn
│       ├── feedback.py      # ImplicitFeedbackTracker
│       └── monitor.py       # PerformanceMonitor (중앙 오케스트레이터)
├── anomaly/
│   └── detector.py          # AnomalyDetector — 이상 탐지 (save_to_file 통합)
├── streaming/
│   ├── evaluator.py         # StreamingEvaluator·SlidingWindow
│   └── middleware.py        # 실시간 스트리밍 미들웨어
├── alerts/
│   ├── engine.py            # AlertEngine·AlertRule
│   └── handlers.py          # 알림 핸들러
├── cost/
│   └── policy.py            # CostTracker·AdaptivePolicy·SamplingStage
├── integrations/
│   ├── llm_judge.py         # LLMJudge — LLM-as-Judge 평가 엔진 (opt-in, [llm] extra)
│   ├── metric_adapters.py   # DeepEval/Ragas adapters
│   └── framework_integrations.py
├── helpers/
│   └── taskresult_helpers.py  # create_taskresult(), token extraction utils
├── reporting/
│   └── comprehensive_report.py  # HTML/text report generation
├── datasets/
│   ├── builder.py           # GoldenSetBuilder — 골든 데이터셋 자동 확장
│   ├── korean_rag_dataset_generator.py
│   └── korean_rag_evaluator.py
├── serve/                   # FastAPI 대시보드 서버 (v0.5.2+)
│   ├── server.py            # FastAPI app 진입점
│   ├── loader.py            # 평가 결과 로더
│   ├── watcher.py           # 파일 변경 감시 (--watch)
│   └── routers/             # API 라우터 12개 (alerts, anomaly, config, conversation, cost, data, export, feedback, golden, stream, transparency, webhook)
├── cli/
│   ├── main.py              # agent-eval CLI 진입점 (init/check/dashboard/gate/dataset/monitor/trend)
│   ├── gate.py              # agent-eval gate — CI/CD 품질 게이팅
│   ├── trend.py             # agent-eval trend — 순차 실행 결과 추세 분석 · RunTrendAnalyzer
│   └── dataset.py           # dataset 서브커맨드 (build)
├── utils/
│   ├── dashboard_integration.py  # Dashboard storage path helper
│   ├── data_registry.py     # 평가 결과 데이터 레지스트리
│   ├── path_helpers.py      # 결과 디렉토리 경로 헬퍼
│   └── transparency_manager.py  # TestTransparencyManager 프로덕션 클래스
├── examples/
│   └── example_runner.py    # ExampleRunner base class
├── exceptions.py            # SDK 예외 계층 (ValidationError, InvalidOperationError 등)
├── config.py                # 환경변수 설정 로더 (load_env, get_settings)
└── __init__.py              # Public API surface

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 7개 통합 파일)
├── 01_layer1_all_metrics.py      # Layer 1 전체 — Accuracy·Hallucination·Quality·Latency·Token·TCR
├── 02_layer2_agentic_security.py # Layer 2 전체 — ToolCall·Retry·Coordination·Workflow·Security·대화
├── 03_framework_adapters.py      # 프레임워크 어댑터 — LangChain·LangGraph·CrewAI·AutoGen + 크로스 파이프라인
├── 04_decorator_quickeval.py     # 데코레이터 전체 API — @agent_eval·@batch_eval·@conversation_eval·QuickEval
├── 05_streaming_alerts.py        # 실시간 — StreamingEvaluator·ImplicitFeedback·AlertEngine·SimpleTaskAlertRule
├── 06_operational.py             # 운영 인프라 — AnomalyDetector·CostTracker·GoldenSetBuilder·evaluation_session
└── 07_phoenix_hybrid.py          # Phoenix OTEL — Tracing·Datasets·Playground·GraphQL + DeepEval·Ragas(opt-in)
# 기존 21개 예제: Evaluator_Examples/.deprecated/ 에 보존

scripts/                     # 운영 도구 (live 인프라 필요, pytest 대상 아님)
└── phoenix_check.py         # Phoenix 통합 자동 점검 — GraphQL 역조회로 pass/fail 판정 (CI 헬스체크용)
```

---

## Key Classes

### `QuickEval`
원스톱 평가 Facade — `PerformanceMonitor` + `EvalDecorator` 를 1~2줄로 시작.

```python
from agent_evaluator import QuickEval

# 기본 사용 — 결과 디렉토리만 지정
eval = QuickEval("results/")

@eval.qa                          # task_type="qa"
def agent(question, ground_truth=""): ...

@eval.tool_use                    # task_type="tool_use"
def tool_agent(question, ground_truth=""): ...

@eval.rag                         # task_type="information_retrieval" + context_arg="context"
def rag_agent(question, context="", ground_truth=""): ...

eval.save()                       # quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)    # CI/CD 게이팅 — 실패 시 sys.exit(1)

# 용도별 팩토리
eval = QuickEval.for_rag("results/")              # hallucination_detection=True
eval = QuickEval.for_security("results/")         # enable_security_metrics=True
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 자동 저장 — 10건마다 save_to_file() 자동 호출
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)

# 단축 데코레이터: qa, tool_use, rag, code, reasoning, planning, data_analysis, creative, multi_agent, secure, streaming
# 배치: @eval.batch(task_type="qa")
# 직접 호출: @eval(task_type="qa", score_fn=my_fn)
# 재시도: @eval.with_retry(task_type="qa", max_retries=3)
```

### PerformanceMonitor vs HybridPerformanceMonitor 선택 가이드

| 항목 | `PerformanceMonitor` | `HybridPerformanceMonitor` |
|------|---------------------|---------------------------|
| 외부 의존성 | 없음 (Layer 1+2 native) | DeepEval / Ragas 필요 (`[eval]` extra) |
| 설치 시간 | 빠름 | 느림 (deepeval, ragas, datasets) |
| LLM Judge | ✅ 내장 (`enable_llm_judge=True`) | ✅ 동일 |
| Faithfulness | ✅ 내장 (`rag_mode=True`) | ✅ + Ragas 방식도 가능 |
| G-Eval | ✅ 내장 (`judge_criteria=[...]`) | ✅ + DeepEval 방식도 가능 |
| RAG 평가 | ✅ HallucinationDetector | ✅ + RagasAdapter |
| 추천 상황 | 대부분의 프로덕션 환경 | DeepEval/Ragas 생태계와 통합 시 |

> **권장**: 신규 프로젝트는 `PerformanceMonitor`로 시작하고, DeepEval/Ragas 지표가 명시적으로 필요한 경우에만 `HybridPerformanceMonitor`로 전환.

### `PerformanceMonitor`
중앙 오케스트레이터. 모든 트래커를 내부에서 구성.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 False (성능 영향)
    enable_security_metrics=False,         # 기본값 False
    # LLM Judge (opt-in, [llm] extra)
    enable_llm_judge=False,                # True 이면 모든 태스크에 LLM 채점 적용
    judge_model=None,                      # None → API 키 기반 자동 결정
    judge_sample_rate=0.1,                 # 10%만 채점 (비용 절감)
    judge_criteria=None,                   # G-Eval 커스텀 기준 ["medical_accuracy", ...]
    # 자동 저장
    auto_save=False,                       # True 이면 N건마다 save_to_file() 자동 호출
    auto_save_interval=10,                 # 저장 주기 (기본: 10)
    auto_save_filename="auto_save",        # 저장 파일명
)
monitor.record_task(task_result)           # PerformanceMonitor 반환 — 메서드 체이닝 가능
report = monitor.generate_report()
monitor.save_to_file("evaluation")  # JSON + HTML 자동 생성

# 팩토리 classmethods (용도별 최적 설정 자동 적용)
monitor_rag = PerformanceMonitor.for_rag_evaluation(output_dir="results/")   # hallucination 기본 활성
monitor_sec = PerformanceMonitor.for_secure_agents(output_dir="results/")    # security 기본 활성
```

### `TaskResult`
단일 태스크 실행 결과를 담는 `@dataclass(frozen=True)` (필수 11개 + 선택 13개 = 24개 필드).

```python
from agent_evaluator import create_taskresult

# 권장: create_taskresult() 헬퍼 사용 (점수 자동 계산)
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
)

# 직접 생성 시 필수 필드 (11개):
# task_id, task_type, success, completion_score, accuracy_score,
# execution_time, tokens_used, tool_calls, attempts, errors, timestamp

# 직렬화 / 역직렬화
d = result.to_dict()
result2 = TaskResult.from_dict(d)      # ISO-8601 timestamp 자동 변환
result3 = TaskResult.from_json(json_str)
```

### `EvaluationReport`
`generate_report()`가 반환하는 불변 보고서 객체. `to_dict()` / `from_dict()` 왕복 지원.

```python
report = monitor.generate_report()
d = report.to_dict()
report2 = EvaluationReport.from_dict(d)  # timestamp 제외 의미론적 비교 (__eq__)
report3 = EvaluationReport.from_json(json_str)
```

### `TaskType` (Enum)
`QA`, `DATA_ANALYSIS`, `CODE_GENERATION`, `DOCUMENT_CREATION`, `INFORMATION_RETRIEVAL`,
`REASONING`, `CREATIVE`, `CODING`, `PLANNING`, `TOOL_USE`

### `evaluation_session` / `async_evaluation_session` (Context Managers)
```python
# 동기 (일반 사용)
with evaluation_session("output_filename") as monitor:
    result = agent.run(task)
    monitor.record_task(result)
# 세션 종료 시 자동 저장 (예외 발생 시에도 안전)

# 비동기 (async 에이전트 사용 시)
async with async_evaluation_session("output_filename") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

### `ConversationSession` (멀티턴 대화 평가)
```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn

session = ConversationSession(session_id="conv_001")
session.add_turn(user_input="안녕하세요", agent_response="안녕하세요!")
session.add_turn(user_input="오늘 날씨는?", agent_response="맑습니다.")
metrics: ConversationMetrics = session.compute_metrics()
# metrics.turn_count, .overall_score, .context_retention, .topic_coherence,
# .progressive_depth, .session_completion, .avg_turn_latency

# monitor와 통합 (권장)
with monitor.conversation("session_id") as conv:
    conv.turn(user="안녕하세요", agent="안녕하세요!", metadata={"latency": 0.3})

# @conversation_eval 데코레이터 — on_turn 콜백 시그니처
# on_turn: (session_id: str, user: str, response: str, metadata: dict) → None
@conversation_eval(
    monitor,
    on_turn=lambda session_id, user, response, metadata: print(f"[{session_id}] {user[:20]}"),
    on_flush=lambda metrics, session_id: print(f"세션 완료: {metrics.overall_score}"),
    max_turns=20,
)
def chatbot(session_id: str, question: str, ground_truth: str = "") -> str: ...
```

### `LLMJudge` — Safety / Faithfulness / G-Eval (v0.7.5+, 확장 v0.7.6+)
LLM-as-Judge 채점 엔진. ground_truth 없이 최대 7+개 차원으로 자동 채점.

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(
    model="claude-haiku-4-5-20251001",  # None → API 키 기반 자동 결정
    sample_rate=0.1,                    # 10%만 채점
    judge_criteria=["medical_accuracy", "citation_quality"],  # G-Eval 대체 (v0.7.6+)
)

# 기본 채점 (5차원: completeness·relevance·factual_consistency·toxicity·bias)
result = judge.judge("t1", question="...", response="...")
result["scores"]["overall"]        # 품질 3차원 평균
result["scores"]["safety_score"]   # (10 - toxicity - bias) / 10  (1.0=안전)

# RAG faithfulness (Ragas 대체, v0.7.6+): context 전달 시 자동 추가
result = judge.judge("t2", question="...", response="...", context="검색된 문서...")
result["scores"]["faithfulness"]   # 0–5 (5=모든 주장이 컨텍스트에 근거)

# G-Eval 커스텀 기준 (DeepEval 대체, v0.7.6+): judge_criteria 지정 시 자동 추가
result["scores"]["criteria_scores"]   # {"medical_accuracy": 4, "citation_quality": 5}
result["scores"]["criteria_overall"]  # 커스텀 기준 평균

# 데코레이터에서 직접 사용 (Lazy init — monitor가 enable_llm_judge=False여도 동작)
@agent_eval(monitor, rag_mode=True, enable_llm_judge=True,
            judge_criteria=["safety", "evidence_based"])
def rag_agent(question, context="", ground_truth=""): ...
```

### Framework-Specific Decorators
`agent_eval(framework=...)` 파라미터로 21개 프레임워크의 응답에서 메타데이터를 자동 추출한다.

```python
from agent_evaluator import agent_eval

# framework= 파라미터로 직접 지정 — 응답에서 tool_calls/chain_steps/tokens_used 자동 추출
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# 지원 프레임워크 (21개): langchain, langgraph, crewai, autogen, dspy, pydanticai,
# anthropic, openai, gemini, llamaindex, haystack, vertexai, ollama, cohere,
# groq, mistral, bedrock, smolagents, semantic_kernel, vllm, huggingface
@agent_eval(monitor, task_type="qa", framework="openai")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)

# 또는 QuickEval 에서 framework= 파라미터로 지정
from agent_evaluator import QuickEval
eval = QuickEval("results/")

@eval(task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str: ...

# 프레임워크 어댑터 메타데이터 조회
from agent_evaluator.decorators import get_framework_info
info = get_framework_info("langchain")  # {"extracts": [...], "description": "..."}
```

### `SimpleTaskAlertRule`
`StreamingEvaluator` 없이 `TaskResult` 기반으로 동작하는 경량 알림 규칙.

```python
from agent_evaluator import SimpleTaskAlertRule, agent_eval

rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,  # 60초 쿨다운
)

@agent_eval(monitor, task_type="qa", alert_rules=[rule])
def agent(question, ground_truth=""): ...

# batch_eval / eval_context / EvalDecorator 에도 동일하게 적용 가능
@batch_eval(monitor, alert_rules=[rule])
def batch_agent(questions, ground_truths=None): ...

with eval_context(monitor, "qa", alert_rules=[rule]) as ctx:
    ctx.response = external_fn(question)
```

### `flush_every` (자동 주기 저장)
N번 호출마다 `save_to_file()` 을 자동 실행한다.

```python
@agent_eval(monitor, task_type="qa", flush_every=10, flush_filename="periodic")
def agent(question, ground_truth=""): ...

@batch_eval(monitor, flush_every=5, flush_filename="batch_periodic")
def batch_agent(questions, ground_truths=None): ...
```

---

## Public API (`__init__.py`)

```python
from agent_evaluator import (
    # Core
    PerformanceMonitor, TaskResult, TaskType, EvaluationReport,

    # Hybrid
    HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport,

    # Helpers
    create_taskresult, evaluation_session, async_evaluation_session,
    hybrid_evaluation_session,

    # Multi-turn Conversation Evaluation
    ConversationSession, ConversationMetrics, ConversationTurn,

    # LLM Judge (opt-in, requires [llm] extra)
    LLMJudge,

    # Transparency Subsystem
    TestTransparencyManager, AnnotationType, TestStepStatus,

    # Config Helpers
    load_env, get_settings, init_from_app,

    # Advanced / Custom Tracker Base
    BaseTracker,

    # Security Helper
    infer_privilege_level,

    # Phase 2/3 — Streaming, Feedback, Anomaly, Cost
    ImplicitFeedbackTracker,
    AnomalyDetector, AnomalyEvent,
    CostTracker, AdaptivePolicy, SamplingStage,

    # Individual Trackers (고급 사용자용)
    TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
    ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker,
    ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
    AgentCoordinationTracker, WorkflowExecutionTracker,
    InputSanitizationTracker, OutputLeakageDetector,
    ToolAuthorizationTracker, PrivilegeEscalationDetector, ToolChainAttackDetector,
)
```

---

## Coding Conventions

- **Formatter:** ruff, line-length=100
- **Python target:** 3.8+ (f-string, dataclass, typing)
- **Type hints:** 모든 public 함수에 필수. `Any` 사용 시 주석 필요
- **Docstrings:** Args / Returns / Example 섹션 포함
- **Error handling:** optional 의존성은 `try/except ImportError`로 graceful 처리
- **Zero-division:** 모든 비율 계산에서 분모 0 guard 필수
- **NaN handling:** pandas 통계 계산 전 `pd.isna()` 체크 필수
- **API 키:** 소스 코드에 하드코딩 금지. 반드시 `os.getenv()` 사용
- **`enable_*` 플래그:** 비싼 연산(hallucination, security)은 기본값 `False`

---

## Architecture Principles

1. **레이어 독립성** — Layer 1/2는 외부 의존성 없이 동작해야 함. optional deps는 Layer 3에서만
2. **트래커 분리** — 각 트래커는 독립적으로 테스트 가능해야 함
3. **side-effect 최소화** — 라이브러리 코드에서 `sys.path`, `os.chdir()`, 전역 state 변경 금지
4. **보안 지표 격리** — `InputSanitizationTracker` 등 보안 트래커는 성능에 영향을 주므로 opt-in
5. **serve 분리** — `agent_evaluator/serve/`는 선택적 FastAPI 서버이며 핵심 평가 로직이 의존해선 안 됨

---

## Dependency Constraints (Known)

| 항목 | 상태 | 설명 |
|------|------|------|
| `ragas>=0.4.0` | ✅ 지원 | 0.4.x API(EvaluationDataset, SingleTurnSample) 완전 지원. `datasets>=4.0.0,<6.0.0` 함께 적용 |
| `[crewai,autogen]`/`[full]` pydantic 충돌 | 🟡 허용 | crewai(pydantic<2.12) + pyautogen(pydantic>=2.12 선호) 동시 설치 시 pydantic 2.11.x로 silent downgrade. 기능 동작은 정상이나 autogen 최신 기능 일부 제한 가능 |
| `pyautogen>=0.3.0` 0.4+ async API | 🟡 부분 지원 | 0.4+(autogen-agentchat 0.4+)는 async API → `@agent_eval(framework="autogen")`으로 async 함수 래핑 권장. autogen_eval_async 데코레이터(`agent_evaluator.integrations`) 사용 가능 |
| `AnswerRelevancy` embeddings | 🟡 조건부 | OpenAI API 키 있을 때만 자동 설정. Anthropic-only 환경에서는 AnswerRelevancy 지표 제외됨 |

## Known Technical Debt

| 우선순위 | 항목 | 위치 |
|---------|------|------|
| 🟡 Medium | ~10곳에서 bare `except Exception: pass` 로 에러 무시 (OTEL 속성 빌딩 구간) | `core/trackers/monitor.py` |

---

## Testing

`tests/` 디렉토리에 63개 파일, 1,869개+ 테스트 함수 존재.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

커버리지 현황 (참고치, 실행 환경에 따라 변동):
- `base.py`: 92% | `layer1.py`: 84% | `layer2.py`: 95%
- `hybrid_monitor.py`: 61% | `monitor.py`: 41% | `taskresult_helpers.py`: 89% | 전체: 33%

주의: `agent_evaluator/utils/transparency_manager.py`는 테스트 파일이 **아님** — `TestTransparencyManager`라는 프로덕션 클래스임.

---

## Dependencies

### 기본 설치 (`pip install agent-evaluator`)
코어 + SDK 자체 기능이 모두 포함됩니다.

- `numpy>=1.20.0,<3.0.0` — 수치 연산
- `pandas>=1.3.0,<4.0.0` — 지표 집계
- `python-dotenv>=0.19.0,<2.0.0` — 환경변수 관리
- `openai>=1.0.0,<3.0.0` + `anthropic>=0.20.0,<1.0.0` — LLMJudge 엔진
- `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — 웹 대시보드
- `opentelemetry-sdk>=1.20.0` + `opentelemetry-exporter-otlp-proto-http>=1.20.0` + `arize-phoenix>=7.0.0` — OTEL 모니터링
- `pdfplumber>=0.10.0,<1.0.0` — 한국어 RAG PDF 처리

### 선택 extras
- `[examples]` — 기본 + eval 묶음. 예제 01~06은 기본만 필요, 07은 eval 추가 필요
- `[eval]` — `deepeval>=3.0.0,<4.0.0` + `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` + `langchain>=1.0.0` + `langchain-openai>=0.1.0` — 외부 평가 라이브러리
- `[langchain]` — `langchain>=1.0.0,<3.0.0` + `langchain-core/openai/anthropic>=1.0.0` + `langgraph>=1.0.0` — LangChain/LangGraph 통합, 중간
- `[dspy]` — `dspy-ai>=2.0.0` — DSPy 프로그램 평가 (`DSPyEvaluator`, `dspy_eval`)
- `[pydanticai]` — `pydantic-ai>=1.0.0,<2.0.0` — PydanticAI Agent 평가 (`PydanticAIEvaluator`, `pydanticai_eval`)
- `[crewai]` — `crewai>=1.0.0,<2.0.0` — 무거움 (전이 의존성 100개+), 단독 격리
- `[autogen]` — `pyautogen>=0.3.0,<1.0.0` + `autogen-agentchat/core>=0.4.0` — 무거움, 단독 격리
- `[full]` — 기본+eval+langchain+dspy+pydanticai+crewai+autogen 전체 (⚠️ 10분+ 소요, CI 전체 호환성 검증용)
- `[dev]` — `pytest` + `pytest-cov` + `pytest-asyncio` + `ruff` + `mypy` + `build` + `twine` + `pre-commit`

> ⚠️ **프레임워크 extras 주의**: `[langchain]`, `[crewai]`, `[autogen]`, `[dspy]`, `[pydanticai]`은 agent-evaluator 자체 의존성이 아님. SDK 어댑터는 duck typing/try-except로 동작하므로 설치 불필요. 이 extras는 **사용자의 에이전트 코드**가 해당 프레임워크를 필요로 할 때 설치.

---

## Accuracy Evaluation Strategy

`AccuracyEvaluator`가 사용하는 QA 정확도 계산 방식:

| 지표 | 가중치 | 방식 |
|------|--------|------|
| Token Overlap | 40% | F1 기반 토큰 매칭 |
| Jaccard Similarity | 30% | 집합 교집합/합집합 |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | Levenshtein 거리 기반 (문자 순서 반영) |

코드 정확도: AST 비교 → 정규화 비교 순으로 fallback.

completion_score task_type 인식 (v0.8.0+):
- `code_generation`/`coding`: AST 파싱 성공 시 1.0, 실패 시 길이 기반
- `tool_use`: `tool_calls` 비어 있으면 0.6 (도구 미사용 부분 완료)

---

## Security Metrics Patterns

`InputSanitizationTracker`가 탐지하는 패턴:
- SQL Injection, Command Injection, Path Traversal, XSS, Prompt Injection

✅ `OutputLeakageDetector` 파일 경로 패턴 — 시스템 경로(`/usr/`, `/bin/`, `/lib/` 등) 제외 처리로 false-positive 개선 완료 (v0.6.3).

---

## 📝 변경 이력

### v0.8.0 (2026-04-13) — 정확도 지표 전면 개선 · Token F1 · Char Levenshtein · task_type 인식 TCR

- 🔧 **Token Overlap Recall → F1** — `layer1.py` `_qa_accuracy()` 및 `taskresult_helpers.py` `_token_overlap_ratio()` 의 토큰 중첩 계산을 단순 Recall/max 방식에서 F1(정밀도-재현율 조화평균)으로 교체. 긴 응답에서 불필요한 토큰을 추가해도 점수가 오르지 않도록 개선
- 🔧 **Char Similarity Levenshtein 통일** — `layer1.py`의 집합 기반 문자 유사도(`set(s1) & set(s2)`)를 `taskresult_helpers.py`와 동일한 Levenshtein 거리 기반으로 교체. 문자 순서 반영으로 정밀도 향상 ("abc"/"cba" 구분)
- ✨ **`calculate_completion_score()` task_type 인식** — `task_type="code_generation"`/`"coding"` 시 AST 파싱 성공 여부로 완료 판정; `task_type="tool_use"` 시 `tool_calls` 비어 있으면 부분 완료(0.6) 반환. ground_truth 없는 환경의 TCR 신뢰도 향상
- 🔧 **`create_taskresult_from_execution()` 실행 순서 개선** — tool_calls를 completion_score 계산 전에 먼저 추출해 task_type 인식 완료 판정에 활용
- 🧪 **테스트 8개 추가** — task_type 인식(code_generation AST·markdown fence·tool_use) + F1 토큰 오버랩 회귀 테스트
- 📝 **Book 16개 챕터 + Lectures 5개 실전 코드 삽입** — `Evaluator_Examples/` 7개 파일의 실제 실행 가능한 Python 코드를 각 챕터와 강의에 직접 포함. 모든 코드 블록에 `# 출처: Evaluator_Examples/XX.py, 섹션 N` 출처 표시

### v0.7.9 (2026-04-13) — arize-phoenix 버전 제약 수정 · RunTrendAnalyzer · 정확도 지표 개선

- 🐛 **arize-phoenix 버전 제약 수정** — pyproject.toml의 `arize-phoenix>=7.0.0` 제약이 최신 릴리즈와 충돌하던 문제 수정. 설치 호환성 복구
- ✨ **`RunTrendAnalyzer` + `agent-eval trend` 서브커맨드** — 순차 평가 결과 JSON의 TCR·정확도·P95 지연시간·환각률 추세 분석. 선형 slope 계산으로 지속적 하락 감지. `--fail-on-regression`으로 CI/CD 파이프라인 연동. `--window N`, `--pattern GLOB`, `--slope-threshold`, `--output-json` 옵션 지원. 테스트 24개 추가 (이슈 #1)
- 🔧 **Token Overlap Recall → F1** — `layer1.py` `_qa_accuracy()` 및 `taskresult_helpers.py` `_token_overlap_ratio()` 의 토큰 중첩 계산을 단순 Recall/max 방식에서 F1(정밀도-재현율 조화평균)으로 교체. 긴 응답에서 불필요한 토큰을 추가해도 점수가 오르지 않도록 개선
- 🔧 **Char Similarity Levenshtein 통일** — `layer1.py`의 집합 기반 문자 유사도를 `taskresult_helpers.py`와 동일한 Levenshtein 거리 기반으로 교체. 문자 순서 반영으로 정밀도 향상
- ✨ **`calculate_completion_score()` task_type 인식** — `task_type="code_generation"`/`"coding"` 시 AST 파싱 성공 여부로 완료 판정; `task_type="tool_use"` 시 `tool_calls` 비어 있으면 부분 완료(0.6) 반환. ground_truth 없는 환경의 TCR 신뢰도 향상

### v0.7.8 (2026-04-12) — SDK 기본 내장 · 의존성 extras 현행화

- ✨ **SDK 기본 내장** — `pip install agent-evaluator` 단독 설치로 LLMJudge · 대시보드 · OTEL 모니터링 모두 사용 가능. `[sdk]` extra 불필요
- 🔧 **의존성 extras 현행화** — `pypdf` 제거, `pydantic-ai` 하한 갱신, `[frameworks]` extra 제거, `[all]`에 dspy/pydanticai 추가
- 🔧 **techdebt 제거** — `_lcs_similarity` 삭제, silent except 구간 로그 추가, loader 파서 회귀 테스트 신규
- 📝 **예제 의존성 문서화** — 예제별 의존성 테이블 추가, docstring에 '의존성' 섹션 추가, `[langchain/crewai/autogen]` extras 역할 명시

### v0.7.7 (2026-04-11) — 데코레이터 버그 수정 · 3종 데코레이터 완전 parity · Layer 2 스레드 안전성

- 🐛 **`agent_eval` preset effective 값 미적용 수정** — `_effective_flush_every` / `_effective_enabled` 계산 후 실제 변수에 재할당되지 않던 버그 수정. preset으로 지정한 `flush_every` / `enabled`가 이제 실제 동작에 반영됨
- 🐛 **`completion_fn` ground_truth guard 추가** — `score_fn`은 `and ground_truth` 조건이 있었으나 `completion_fn`에는 누락. `ground_truth` 없을 때 사용자 함수에 빈 문자열/None이 전달되던 문제 수정
- 🐛 **`HybridPerformanceMonitor` advanced_metrics None 역참조 수정** — `advanced_metrics=None`인 TaskResult에서 `.items()` / `in` 호출 시 TypeError 발생 수정 (None guard 3개소 추가)
- ✨ **`conversation_eval` LLM Judge 파라미터 추가** — `enable_llm_judge` / `judge_model` / `judge_criteria` 파라미터 추가. `agent_eval` / `batch_eval`과 완전 parity 달성
- ✨ **`batch_eval` `judge_model` 파라미터 추가** — `enable_llm_judge` / `judge_criteria`만 있고 `judge_model`이 누락되어 있던 문제 수정. `_BATCH_PARAMS` frozenset에도 추가
- ✨ **3종 데코레이터 preset LLM Judge 적용** — `conversation_eval` / `batch_eval`의 preset 처리 블록에 `enable_llm_judge` / `judge_model` / `judge_criteria` 적용 추가. `agent_eval`과 동일한 패턴
- 🔧 **Layer 2 트래커 스레드 안전성** — `ToolCallAnalyzer` · `RetryCorrectionTracker` · `ToolSelectionTracker` · `AgentCoordinationTracker` · `WorkflowExecutionTracker` 5개 트래커에 `threading.Lock` 추가. `_executions` append/read/reset 전 구간 보호

### v0.7.6 (2026-04-10) — LLMJudge 확장 · G-Eval/Ragas 데코레이터 대체 구현 · 데코레이터 호환 지표 22개

- ✨ **`judge_criteria` 파라미터** — `@agent_eval(judge_criteria=["medical_accuracy"])` 로 G-Eval 스타일 커스텀 평가 기준을 LLM Judge에 주입. DeepEval G-Eval을 외부 패키지 없이 대체. `LLMJudge(judge_criteria=[...])`, `PerformanceMonitor(judge_criteria=[...])`, `EvalDecorator(judge_criteria=[...])` 전 계층 지원. 결과: `scores["criteria_scores"]`, `scores["criteria_overall"]`
- ✨ **Faithfulness 차원** — `rag_mode=True + enable_llm_judge=True` 조합 시 context가 있으면 `faithfulness` 점수(0–5) 자동 추가. Ragas LLM-based Faithfulness를 외부 패키지 없이 대체. 5=모든 주장이 컨텍스트에 근거, 0=컨텍스트 무시
- ✨ **Lazy LLMJudge 초기화** — monitor가 `enable_llm_judge=False`로 생성된 경우에도 `@agent_eval(enable_llm_judge=True)` 파라미터만으로 LLMJudge 인스턴스 자동 생성·사용·소멸
- 🔧 **`_build_system_prompt(context_available, judge_criteria)`** — 정적 `_SYSTEM_PROMPT` 대체. context/criteria 조합에 따라 채점 차원 동적 확장 (최대 7+개 차원)
- 🔧 **`max_tokens` 256→512** — 추가 차원(faithfulness + 커스텀 기준) 출력 공간 확보
- 🔧 **`get_summary()` 동적 집계** — 결과에 따라 faithfulness, criteria_scores 차원 자동 포함
- 🗑️ **LangSmith adapter 제거** — `MetricProvider.LANGSMITH`, `LangSmithAdapter` 클래스 삭제. `HybridPerformanceMonitor`의 `use_langsmith` 파라미터 삭제
- 🗑️ **`evaluation_cost` 제거** — `save_to_file()` 출력에서 LLM Judge API 호출 비용 별도 키 삭제 (비용은 `task_result.extra["llm_judge"]["cost_usd"]`로 태스크별 접근)
- 📊 **데코레이터 호환 지표 22개** — StreamingEvaluator(2개), DeepEval NLI Hallucination(1개)만 외부 의존성 필요. 나머지 22개 지표 전부 `@agent_eval` / `@batch_eval` / `@conversation_eval`만으로 구현 가능

### v0.7.5 (2026-04-09) — 대시보드 5개 탭 데이터 수정 · AnomalyDetector 버그 수정 · 예제 현행화

- 🐛 **`AnomalyDetector._get_latencies()` 버그 수정** — `execution_time` 키 읽기 → `total_time`(실제 저장 키)으로 수정, 이상 감지 탭 latency_trend 항상 0 반환 문제 해결
- 🐛 **`AnomalyDetector._get_error_rate()` 버그 수정** — `t.success` 기준 (create_taskresult 항상 True) → `accuracy_score < 0.05 AND completion_score < 0.05` 복합 조건으로 교체, error_surge 감지 복구
- 🔧 **`05_streaming_alerts.py` 대시보드 연동** — `streaming._flush()` 호출(실시간 탭), `monitor.record_implicit_feedback()`(사용자 반응 탭), alert JSONL 기록(알림 탭), `enable_anomaly_detection=True`(이상 감지 탭) 추가
- 🔧 **`06_operational.py` 대시보드 연동** — `evaluation_cost` 키 주입(평가 비용 탭), `enable_anomaly_detection=True`, alert JSONL 기록 추가
- 🔧 **`07_phoenix_hybrid.py` 외부평가 탭 활성화** — `HybridPerformanceMonitor` 연동(API 키 있을 때) + 데모 `advanced_metrics` JSON 패치(API 키 없을 때), `rag_metrics`·`advanced_metrics_summary` 생성
- 📝 **`Docs/12_MONITOR_GUIDE.md` 전면 재작성** — Phoenix UI 탭별 완전 가이드(Tracing·Evaluators·Datasets·Prompts·Experiments·Playground), GraphQL 5개 쿼리 예시, FAQ 6개, Evaluators 탭 오해 해소 섹션 추가

### v0.7.4 (2026-04-08) — 전체 예제 데코레이터 적용 완료 · layer1 버그 수정 · 예제 7개 통합

- ✨ **예제 전체 데코레이터 적용** — `@agent_eval` / `@batch_eval` / `@conversation_eval` 전면 적용 완료
- 🔧 **예제 7개 통합 파일로 재편** — 기존 21개 → `01_layer1` ~ `07_phoenix_hybrid` 7개 통합 (구 파일: `.deprecated/` 보존)
- 🐛 **layer1.py 버그 수정** — 성능 지표 계산 엣지 케이스 수정
- 🔧 **대시보드 템플릿 개선** — `dashboard.html.j2` / `dashboard2.html.j2` / `slides.html.j2` 마이너 개선
- 📝 **문서 현행화** — Docs/ 버전·날짜 갱신

### v0.7.3 (2026-04-07) — 보안 트래커 실동작 · 프레임워크 어댑터 확대 · Phoenix 통합 완성

- **보안 메트릭 실동작 (CRITICAL)** — `record_task()`에서 5개 보안 트래커 누락 호출 버그 수정. `enable_security_metrics=True` 시 InputSanitization·OutputLeakage·ToolAuth·PrivilegeEscalation·ChainAttack 실제 호출
- **프레임워크 어댑터 확대** — AutoGen `agent_interactions`/`state_transitions` (LangGraph 전용 → 3개 프레임워크), Haystack/Semantic Kernel `tool_calls`, PydanticAI/LlamaIndex `tool_calls` 신규
- **Phoenix UI 통합 완성** — Prompts 탭(`llm.prompts` OpenInference 속성), Datasets 탭(`dataset.id`/`version`/`record_count`), `ae.tool_names`/`ae.anomaly_detection_enabled` span 속성 추가
- **대시보드 API** — `security_incidents_count`, `has_multimodal`, `multimodal_task_count` 목록뷰 추가

### v0.7.2 (2026-04-05) — 3종 데코레이터 API 완성 · 21개 프레임워크 어댑터 · QuickEval Facade · 대시보드 API 확장

- **3종 데코레이터 API 완성** — `agent_eval` / `batch_eval` / `conversation_eval` / `EvalDecorator`: `rag_mode`, `security_mode`, `enable_llm_judge`, `enable_anomaly_detection`, `alert_rules`, `flush_every`, `preset`, `sample_condition` 파라미터 일관성 확보. 제너레이터 첫 yield 시점 TTFT 자동 기록
- **QuickEval Facade** — `QuickEval("results/")` 1줄 시작; 팩토리 4종 (`for_rag`, `for_security`, `for_llm_judge`, `for_regression_eval`); `gate()` / `summary()` / `compare()` / `ab_test()` / `export_to_dataframe()` / `@eval.cached(ttl)` / `watch(dir, callback)`; 단축 데코레이터 11종
- **21개 프레임워크 어댑터** — `auto_detect_framework=True` 기본 활성 (12개 속성 기반 자동 감지); `FrameworkLiteral` 타입 힌트; `_FRAMEWORK_ADAPTER_META` 레지스트리; `_safe_adapter_call()` 중앙 에러 핸들러. 각 SDK별 캐시 토큰·구버전 `function_call` 호환
- **PerformanceMonitor 심화** — `reset()` / `snapshot()` / `clone()` / `merge()` / `filter_tasks()` / `aggregate_metrics()` / `export_to_dataframe()` / `export_to_wandb()` / `compare()` / `analyze()` / `register_aggregator()`
- **새 지표** — `LatencyTracker.track_ttft()`, `ToolSelectionTracker.get_f1_by_tool()`, `AgentCoordinationTracker.get_network_topology()`, `AnomalyDetector.explain_event()`, `GoldenSetBuilder.push_to_phoenix()`
- **AlertRuleBuilder** — 팩토리 5종 (`when_accuracy_below` / `when_latency_above` / `when_completion_below` / `when_error` / `when_tool_calls_exceed`); `compound_conditions`; `dry_run()`; `class_level_cooldown`
- **AGENT_EVAL_PRESETS** — `"production"` / `"development"` / `"testing"` / `"canary"` 4종
- **대시보드 API 확장** — 50+ 엔드포인트: `/tasks/filter`, `/frameworks`, `/distributions`, `/timeline`, `/llm_judge`, `/api/leaderboard`, `/cost/breakdown`, `/anomaly/explain/{id}`, `/export/excel`, WebSocket/SSE 스트리밍, `/api/health` OTEL 동적 감지

### v0.7.1 (2026-04-03) — QuickEval Facade · SimpleTaskAlertRule · DSPy/PydanticAI 통합

- **`QuickEval`** — `PerformanceMonitor` + `EvalDecorator` 원스톱 Facade; `for_rag()` / `for_security()` / `for_llm_judge()` 팩토리; `gate()` / `summary()` / `save()`; `tcr_tracker` 없을 때 `AttributeError` 버그 수정
- **`SimpleTaskAlertRule`** — `StreamingEvaluator` 없이 동작하는 경량 `TaskResult` 기반 알림; 3종 데코레이터에 `alert_rules=` 통합
- **`flush_every`** — 3종 데코레이터·`PerformanceMonitor.auto_save` 공통 N건마다 `save_to_file()` 자동 실행
- **DSPy / PydanticAI 통합** — `[dspy]` · `[pydanticai]` extras; `DSPyEvaluator`, `PydanticAIEvaluator`, `autogen_eval_async` 신규
- **`_normalize_task_type()`** — `TaskType.QA` Enum과 `"qa"` 문자열 혼용 지원

### v0.7.0 (2026-04-01) — 운영 실시간 모니터링 (Phoenix + OTEL)

- **`agent-eval monitor`** CLI — Arize Phoenix 서버 기동 + OTLP 스팬 수신 설정 (`--port`, `--check` 옵션)
- **`setup_otel(endpoint, service_name, enable_metrics=False)`** 공개 API; `[otel]` extras 신규
- **`_emit_otel_span()`** — `PerformanceMonitor.record_task()` 시 OTLP 스팬 자동 발행
- **Phoenix 프로젝트 분리** — `openinference.project.name` 속성으로 예제별 독립 프로젝트 생성
- **버그 수정** — OTEL 스팬 속성 None 방어, metrics 기본 비활성화 (Phoenix `/v1/metrics` 미지원)

### v0.6.x (2026-03-21 ~ 04-01) — SDK 안정화 · 프레임워크 통합 · 대시보드

- **프레임워크 통합** — LangChain / LangGraph / CrewAI / AutoGen 4개 완전 지원
- **FastAPI 대시보드** — `agent-eval dashboard` CLI, HTML/CSV 내보내기, 슬라이드 뷰, 오프라인 모드
- **LLMJudge** — ground_truth 없이 completeness · relevance · factual_consistency 3차원 자동 채점
- **멀티턴 대화 평가** — `ConversationSession` 추가 (`15_conversation_eval.py`)
- **골든 데이터셋 재설계** — 경로 `results/golden_datasets/` → `data/golden_datasets/`
- **이상 감지 파이프라인** — `save_to_file()` → `anomaly_data` → 대시보드 연결
- **Ragas 0.4.x** — `EvaluationDataset` / `SingleTurnSample` API 완전 지원
- **Python 3.13 지원** — `numpy<3.0.0`, `pandas<4.0.0` 상한 완화
- **SDK 안정화** — `record_task()` 메서드 체이닝, `TaskResult` 직렬화/역직렬화, 스레드 안전성
- **테스트** — 962개 테스트 함수, 37개 파일

### v0.2.x – v0.5.x — 초기 구현

- Layer 1/2/3 트래커 25개, `ConversationSession`, `evaluation_session`, `TestTransparencyManager` 초기 구현
