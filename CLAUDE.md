# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.7.2 (Beta)
- **Python:** 3.8+
- **License:** MIT
- **Author:** Sungwoo Kim

---

## Common Commands

```bash
# 개발 환경 설치
pip install -e ".[dev]"

# 선택적 의존성 포함 설치
pip install -e ".[llm,serve]"          # 가장 빠른 실용 구성
pip install -e ".[langchain,serve]"    # LangChain/LangGraph 포함
pip install -e ".[eval]"               # DeepEval/Ragas 평가
pip install -e ".[crewai]"            # CrewAI 단독 (무거움)
pip install -e ".[autogen]"           # AutoGen 단독 (무거움)
pip install -e ".[dspy]"              # DSPy 통합 (dspy-ai)
pip install -e ".[pydanticai]"        # PydanticAI 통합 (pydantic-ai)
pip install -e ".[all]"               # crewai/autogen 제외 전체 (권장)
pip install -e ".[full]"              # 진짜 전체 (⚠️ 10분+ 소요)

# --- CLI (pip install 후 바로 사용 가능) ---
agent-eval init          # 대화형 API 키 설정 마법사
agent-eval check         # 현재 설정 상태 출력
agent-eval dashboard     # FastAPI 대시보드 실행 (기본 포트 8765)  [개발·검증 단계]
agent-eval gate result.json --tcr 85 --accuracy 70   # CI/CD 품질 게이팅
agent-eval dataset build results/ --min-score 0.8    # 골든 데이터셋 자동 추출
agent-eval monitor                                   # Arize Phoenix 서버 기동 + OTLP 스팬 수신 설정 (운영 실시간 모니터링)
agent-eval monitor --port 6006                       # Phoenix 포트 지정 (기본: 6006)
agent-eval monitor --check                           # OTEL 패키지 설치 여부 및 포트 점유 상태 확인
# 예제 실행 시 자동으로 Phoenix에 연결 → 프로젝트별 Tracing·Evaluators·Datasets·Prompts 확인 가능
# (pip install "agent-evaluator[otel]" 또는 "[full]" 필요)
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
  LangSmithAdapter          → LangSmith tracing data
```

### Module Layout

```
agent_evaluator/
├── core/
│   ├── agent_evaluator.py   # re-export facade — trackers/ 분리 완료
│   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   ├── monitor_context.py   # Context managers
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
│   ├── crewai_integration.py
│   ├── langchain_integration.py
│   ├── langgraph_integration.py
│   ├── autogen_integration.py
│   ├── llm_helpers.py       # LLMEvaluationHelper, AnthropicEvaluationHelper
│   ├── llm_judge.py         # LLMJudge — LLM-as-Judge 평가 엔진 (opt-in, [llm] extra)
│   ├── metric_adapters.py   # DeepEval/Ragas/LangSmith adapters
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
│   ├── main.py              # agent-eval CLI 진입점 (init/check/dashboard/gate/dataset)
│   ├── gate.py              # agent-eval gate — CI/CD 품질 게이팅
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

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 17개 플랫 파일)
├── 01_quality_eval.py       # 품질 지표 — Accuracy, Hallucination, Quality, RAG
├── 02_performance_eval.py   # 성능 지표 — TCR, Latency, Token Economy
├── 03_agentic_eval.py       # 에이전틱 지표 — Tool Call, Coordination, Workflow
├── 04_security_eval.py      # 보안 지표 — Input Sanitization, Leakage, Auth, Escalation
├── 05_hybrid_eval.py        # 하이브리드 평가 — DeepEval, Ragas, LangSmith 통합
├── 06_langchain_eval.py     # LangChain 프레임워크 통합 예제
├── 07_langgraph_eval.py     # LangGraph 프레임워크 통합 예제
├── 08_crewai_eval.py        # CrewAI 프레임워크 통합 예제
├── 09_autogen_eval.py       # AutoGen 프레임워크 통합 예제
├── 10_cross_framework_eval.py # 멀티 프레임워크 비교 평가
├── 11_streaming_eval.py     # 실시간 스트리밍 평가 + 사용자 반응(ImplicitFeedback)
├── 12_alerting_eval.py      # 알림 엔진 예제
├── 13_golden_set_build.py   # GoldenSetBuilder — 케이스 추출·저장·병합
├── 14_anomaly_cost_eval.py  # 이상 감지 + 비용 추적 + AdaptivePolicy
├── 15_conversation_eval.py  # 멀티턴 대화 평가 — ConversationSession
├── 16_dashboard_demo.py     # FastAPI 대시보드 통합 데모 — save_to_file + Phoenix OTEL
└── 17_phoenix_verification.py # Phoenix 4개 메뉴 통합 데모 — Tracing·Evaluators·Datasets·Prompts

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

# 단축 데코레이터: qa, tool_use, rag, code, reasoning, planning, data_analysis, creative, chat, batch
# 직접 호출: @eval(task_type="qa", score_fn=my_fn)
# 재시도: @eval.with_retry(task_type="qa", max_retries=3)
```

### `PerformanceMonitor`
중앙 오케스트레이터. 모든 트래커를 내부에서 구성.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 False (성능 영향)
    enable_security_metrics=False,         # 기본값 False
    # 자동 저장 (Task 2)
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
```

### Framework Factory Functions
```python
crew = create_evaluated_crew(tasks, agents, monitor=monitor)
agent = create_evaluated_langchain_agent(llm, tools, monitor=monitor)
graph = create_evaluated_langgraph(graph, monitor=monitor)
agent = create_evaluated_autogen_agent(config, monitor=monitor)
```

### Framework-Specific Decorators
각 프레임워크에 최적화된 `@agent_eval` 별칭. 프레임워크 응답에서 메타데이터를 자동 추출한다.

```python
from agent_evaluator.integrations import (
    # Agent 프레임워크
    langchain_eval,   # intermediate_steps → tool_calls/chain_steps
    langgraph_eval,   # messages → state_transitions/graph_traversal/tool_calls
    crewai_eval,      # tasks_output → agent_interactions
    autogen_eval,     # messages/chat_history → conversation_turns
    dspy_eval,        # _completions → chain_steps + token usage
    pydanticai_eval,  # RunResult.usage() → tokens_used
    # LLM SDK (v0.7.2+)
    anthropic_eval,   # content[].tool_use → tool_calls + usage tokens
    openai_eval,      # choices[0].message.tool_calls + usage.total_tokens
    gemini_eval,      # candidates[0].content.parts[].function_call + usage_metadata
    llamaindex_eval,  # source_nodes → chain_steps + metadata tokens
    haystack_eval,    # pipeline component outputs → chain_steps
)

@langchain_eval(monitor)
def my_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# 또는 QuickEval 에서 framework= 파라미터로 직접 지정
@eval(task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str: ...
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

    # Multi-turn Conversation Evaluation (Phase 1-C)
    ConversationSession, ConversationMetrics, ConversationTurn,

    # LLM Judge (opt-in, requires [llm] extra)
    LLMJudge,

    # LLM Helpers
    LLMHelper, ClaudeHelper,  # aliases for LLMEvaluationHelper, AnthropicEvaluationHelper

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
| `[frameworks]`/`[full]` pydantic 충돌 | 🟡 허용 | crewai(pydantic<2.12) + pyautogen(pydantic>=2.12 선호) 동시 설치 시 pydantic 2.11.x로 silent downgrade. 기능 동작은 정상이나 autogen 최신 기능 일부 제한 가능 |
| `pyautogen>=0.3.0` 0.4+ async API | 🟡 부분 지원 | 0.4+(autogen-agentchat 0.4+)는 async API로 전환 → generate_reply wrapping 불가. UserWarning으로 안내하며 수동 `monitor.record_task()` 사용 필요 |
| `AnswerRelevancy` embeddings | 🟡 조건부 | OpenAI API 키 있을 때만 자동 설정. Anthropic-only 환경에서는 AnswerRelevancy 지표 제외됨 |

## Known Technical Debt

| 우선순위 | 항목 | 위치 |
|---------|------|------|
| 🟡 Medium | ~9곳에서 bare `except Exception:` 로 에러 무시 | `core/trackers/monitor.py` |
| 🟡 Medium | `_check_patterns()`, `_is_subsequence()` 중복 구현 가능성 확인 필요 | `core/trackers/` |

---

## Testing

`tests/` 디렉토리에 59개 파일, 1,769개+ 테스트 함수 존재.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

커버리지 현황 (v0.7.0 기준):
- `base.py`: 92% | `layer1.py`: 84% | `layer2.py`: 95%
- `hybrid_monitor.py`: 61% | `monitor.py`: 41% | `taskresult_helpers.py`: 89% | 전체: 33%

주의: `agent_evaluator/utils/transparency_manager.py`는 테스트 파일이 **아님** — `TestTransparencyManager`라는 프로덕션 클래스임.

---

## Dependencies

### Core (항상 설치됨)
- `numpy>=1.20.0,<3.0.0`
- `pandas>=1.3.0,<4.0.0`
- `python-dotenv>=0.19.0,<2.0.0`

### Optional (단위 extras)
- `[llm]` — `openai>=1.0.0,<3.0.0` + `anthropic>=0.20.0,<1.0.0` — 빠름
- `[langchain]` — `langchain>=1.0.0,<3.0.0` + `langchain-core/openai/anthropic>=1.0.0` + `langgraph>=1.0.0` — 중간
- `[crewai]` — `crewai>=1.0.0,<2.0.0` — 무거움 (전이 의존성 100개+), 단독 격리
- `[autogen]` — `pyautogen>=0.3.0,<1.0.0` + `autogen-agentchat/core>=0.4.0` — 무거움, 단독 격리
- `[eval]` — `deepeval>=3.0.0,<4.0.0` + `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` + `langchain>=0.2.0`
- `[dspy]` — `dspy-ai>=2.0.0` — DSPy 프로그램 평가 (`DSPyEvaluator`, `dspy_eval`)
- `[pydanticai]` — `pydantic-ai>=0.0.13` — PydanticAI Agent 평가 (`PydanticAIEvaluator`, `pydanticai_eval`)
- `[serve]` — `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — 빠름
- `[pdf]` — `pypdf>=3.0.0,<7.0.0` + `pdfplumber>=0.10.0,<1.0.0` — 빠름

### Optional (조합 편의 extras)
- `[frameworks]` — `langchain` + `crewai` + `autogen` 한 번에 (기존 호환, 무거움)
- `[all]` — crewai/autogen/otel **제외** 전체 (권장, 합리적 설치 시간) — `pip install agent-evaluator[all]`
- `[full]` — crewai/autogen/otel 포함 진짜 전체 (⚠️ 10분+ 소요) — `pip install agent-evaluator[full]`

### Dev (개발 환경)
- `[dev]` — `pytest` + `pytest-cov` + `pytest-asyncio` + `ruff` + `mypy` + `build` + `twine` + `pre-commit`

---

## Accuracy Evaluation Strategy

`AccuracyEvaluator`가 사용하는 QA 정확도 계산 방식:

| 지표 | 가중치 | 방식 |
|------|--------|------|
| Token Overlap | 40% | F1 기반 토큰 매칭 |
| Jaccard Similarity | 30% | 집합 교집합/합집합 |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | 문자 수준 유사도 |

코드 정확도: AST 비교 → 정규화 비교 순으로 fallback.

---

## Security Metrics Patterns

`InputSanitizationTracker`가 탐지하는 패턴:
- SQL Injection, Command Injection, Path Traversal, XSS, Prompt Injection

✅ `OutputLeakageDetector` 파일 경로 패턴 — 시스템 경로(`/usr/`, `/bin/`, `/lib/` 등) 제외 처리로 false-positive 개선 완료 (v0.6.3).

---

## 📝 변경 이력

### v0.7.2 (2026-04-05) — 데코레이터 종합 개선 · 21개 프레임워크 어댑터 · QuickEval Facade · 대시보드 API 확장

**데코레이터 API 완성 (agent_eval · batch_eval · eval_context · conversation_eval · EvalDecorator)**

- **`agent_eval` 단축 파라미터** — `rag_mode=True` (context_arg + hallucination + IR 자동), `security_mode=True` (보안 메트릭 임시 활성), `enable_llm_judge` / `judge_model` (LLM Judge 임시), `enable_anomaly_detection` (이상 감지 임시), `enable_hallucination` (hallucination 임시) — 모두 temp-override 패턴으로 finally에서 복원
- **`EvalDecorator` 인스턴스 모드 파라미터** — `__init__`에 위 5개 파라미터 추가; `_defaults`에 저장 → `.batch()`/`.context()`/`.__call__()` 자동 전파
- **`EvalDecorator` 단축 속성** — `.qa` / `.tool_use` / `.rag` / `.code` / `.reasoning` / `.planning` / `.data_analysis` / `.creative` / `.multi_agent` / `.secure` 10개 `@property`; `QuickEval`과 API 일관성
- **`batch_eval` 심화** — `concurrent=True`/`max_concurrent`, `shuffle`, `item_timeout`, `strict_types`, `on_item_error`, `return_format`("list"/"tuple"/"dataframe"), `streaming_mode`, `allow_duplicate_task_ids`; DataFrame에 tokens_total/input/output, framework, tool_call_count, has_error, attempts, timestamp 추가
- **`eval_context` 심화** — `timeout`, `ttft_seconds`, `chunk_step()` (스트리밍 청크 기록 + 첫 청크 TTFT 자동), `auto_task_id`, `depth` property (중첩 깊이 ContextVar), `MAX_NESTING_DEPTH` 상한
- **`conversation_eval` 심화** — `participant_id_arg`, `max_turns_exceeded_action`, `load_previous_session`, `flush_every`/`flush_filename`, `on_session_timeout`, `on_turn`, `session_score_fn`, `turn_score_fn`; async generator 지원
- **`agent_eval_with_retry` 심화** — `jitter_type`("full"/"decorrelated"/"none"), `max_delay`, `should_retry` callable, `alert_rules`, `flush_every`
- **Generator TTFT 자동 기록** — `gen_wrapper`/`agen_wrapper`에서 첫 비-EvalMetadata 청크 yield 시점 → `latency_tracker.track_ttft()` 자동 연동
- **`on_record` 교체** — `on_record` 가 `TaskResult` 반환 시 원본 교체; completion/accuracy score [0,1] clamp
- **`sample_condition`** — `(args, kwargs) → bool` 조건부 샘플링; `sample_rate`와 독립

**QuickEval Facade**

- **원스톱 시작** — `QuickEval("results/")` 1줄로 PerformanceMonitor + EvalDecorator 구성; `for_rag()` / `for_security()` / `for_llm_judge()` / `for_regression_eval()` 팩토리
- **`gate()`** — tcr/accuracy/quality/hallucination 임계값; config_file JSON 로드; 비활성 트래커 UserWarning
- **`summary()`** — p95_latency, total_cost_usd, quality_avg, hallucination_rate 포함
- **`compare(other)` / `ab_test(other)`** — 두 인스턴스 지표 비교; t-검정 p-value (scipy 있을 때)
- **`from_config(yaml_file)` / `replay(results_file)` / `export_to_dataframe()`**
- **`@eval.cached(ttl=3600)`** — TTL 기반 응답 캐싱; async 함수 자동 감지
- **`watch(directory, callback)`** — 디렉토리 감시 + 신규 JSON 자동 replay; `max_watched_files` 상한
- **`generate_gate_config(filepath)`** — 현재 지표 기반 95% 임계값 자동 제안
- **단축 데코레이터** — `.qa` / `.tool_use` / `.rag` / `.code` / `.reasoning` / `.planning` / `.data_analysis` / `.creative` / `.streaming` / `.multi_agent` / `.security`; `alert_rules`/`flush_every`/`flush_filename` 전역 설정 → 모든 단축 데코레이터 자동 적용
- **`__repr__` 버그 수정** — `tcr_tracker` 없을 때 `AttributeError` → `tasks=0` 안전 반환

**21개 프레임워크 어댑터**

- **LangChain/LangGraph** — `usage_metadata` + `response_metadata.token_usage` 다중 메시지 누산; `ToolMessage`/`AIMessage` chain_steps + 타임스탬프 기반 실행 시간
- **CrewAI** — `token_usage`/`usage_metrics`/`usage` 딕셔너리 토큰 집계; `output_pydantic` / `output_format` (v2.x) 지원
- **AutoGen** — `timestamp`/`created_at` 기반 턴별 실행 시간; `autogen_eval_async` 비동기 전용 데코레이터 (0.4+ async API)
- **DSPy** — `_completions`/`completions` 속성 기반 자동 감지; LM history multi-step chain_steps; `tool_calls`/`actions` 추출
- **PydanticAI** — `all_messages()` 우선 / `.messages` fallback; `ToolCallPart`/`ToolReturnPart`/`TextPart` 세분화; 속성 기반 자동 감지
- **Anthropic** — `content[].tool_use` + `usage.input_tokens/output_tokens`; 캐시 토큰(cache_creation/cache_read, SDK ≥0.29) 추출
- **OpenAI** — `choices[0].message.tool_calls` + `usage.total_tokens`; Assistants API `required_action`; 스트리밍 `choice.delta` fallback
- **Gemini/VertexAI** — `candidates[0].content.parts[].function_call` + `usage_metadata`
- **LlamaIndex/Haystack** — `source_nodes` → chain_steps; 파이프라인 컴포넌트 출력 dict → chain_steps
- **Cohere/Groq/Mistral/Bedrock/smolagents/SemanticKernel/Ollama/vLLM/HuggingFace** — 각 SDK 전용 metadata 추출 + 캐시 토큰/function_call 구버전 호환
- **`_auto_detect_framework()`** — 12개 속성 기반 자동 감지 (anthropic/openai/gemini/cohere/groq/mistral/bedrock/smolagents/vllm/huggingface/dspy/pydanticai); `auto_detect_framework=True` 기본 활성
- **`FrameworkLiteral`** — 21개 프레임워크 Literal 타입 힌트; `agent_eval()` + `EvalDecorator.__init__()` 적용; 최상위 export; IDE 자동완성 지원
- **`_safe_adapter_call()`** — 중앙 어댑터 에러 핸들러; 실패 시 logger.debug + None 반환
- **`_FRAMEWORK_ADAPTER_META`** — 21개 어댑터 메타데이터 레지스트리; `get_framework_info(framework)` 조회 함수 최상위 export

**PerformanceMonitor 심화**

- **`reset(keep_config=True)`** / **`snapshot()`** / **`compare_with_snapshot(snap)`** / **`restore_from_snapshot()`** — 초기화·스냅샷·비교·복원 사이클
- **`clone()`** / **`merge(other)`** — 설정 복제 / 두 모니터 태스크 병합
- **`filter_tasks()`** / **`aggregate_metrics(since, until, by)`** / **`get_timeseries_metrics(metric, granularity)`** — 필터링·집계·시계열
- **`export_to_dataframe(include_fields=None)`** / **`export_to_wandb()`** / **`export_to_mlflow()`** — DataFrame·W&B·MLflow 내보내기
- **`compare(other)`** / **`compare_models()`** / **`analyze()`** — 모니터 비교·모델별 비용·병목 분석·최적화 권고
- **`register_aggregator()` / `run_aggregator()` / `list_aggregators()`** — 사용자 정의 집계 함수 레지스트리
- **`enabled_security_trackers`** — 선택적 보안 트래커 활성화 리스트
- **`MultimodalMetricsTracker` 자동 연동** — `extra.image_count`/`audio_duration_seconds`/`video_frames` 자동 트리거
- **`enable_otel_child_spans=True`** — chain_steps 각 항목을 별도 OTEL 자식 스팬으로 발행
- **`enable_compression(algorithm)`** — save_to_file 시 gzip/bz2 추가 압축

**새 지표 · 트래커**

- **`LatencyTracker.track_ttft()` / `get_ttft_stats()`** — TTFT(Time-To-First-Token) 기록·통계; task_type 필터
- **`TokenEconomyTracker.get_cost_breakdown_by_framework()`** — 프레임워크별 비용 집계
- **`ToolSelectionTracker.get_f1_by_tool()`** — 도구별 F1/Precision/Recall
- **`AgentCoordinationTracker.get_network_topology()`** — hub/chain/mesh 패턴 + 밀도 + 허브 노드
- **`AnomalyDetector.explain_event()` / `scan_with_explain()`** — 이상 원인 설명 + 권고사항
- **`CostTracker.learn_cost_model(tasks)` / `auto_price_map`** — 태스크 데이터 기반 비용 자동 학습
- **`LLM Judge back-propagation`** — `_build_and_record()` 완료 후 monitor.tasks에서 enriched TaskResult 재조회 → decorator 반환값에 llm_judge(completeness/relevance/factual_consistency) 포함
- **`ConversationMetrics.turn_scores`** — 턴별 품질 점수 Optional[Dict[int, float]]
- **`partial_reason` 자동 생성** — 예외 발생 시 "execution_error", 빈 응답 시 "empty_response" 자동 설정
- **`GoldenSetBuilder.push_to_phoenix(cases, dataset_name)`** — merge_to_golden() + upload_to_phoenix() 1-call 래퍼

**AlertRuleBuilder · 알림 심화**

- **`AlertRuleBuilder`** — `SimpleTaskAlertRule` 팩토리; `when_accuracy_below()` / `when_latency_above()` / `when_completion_below()` / `when_error()` / `when_tool_calls_exceed()` 5개 정적 메서드
- **`SimpleTaskAlertRule.dry_run(task_result)`** — 핸들러 미실행 조건 검증
- **`SimpleTaskAlertRule.class_level_cooldown`** — 동일 name 인스턴스 공유 쿨다운
- **`compound_conditions`** — `[{"field", "op", "value"}]` 형식 복합 조건
- **`agent_eval`에 `alert_rules=[]` 통합** — `batch_eval`/`eval_context`/`EvalDecorator`/`agent_eval_with_retry` 동일 API

**AGENT_EVAL_PRESETS**

- **`"production"`** — `flush_every: 50` + `enable_anomaly_detection: True`
- **`"development"`** — `enable_llm_judge: True` + `auto_detect_framework: True`
- **`"testing"` / `"canary"`** — 경량 평가 / 카나리 배포 최적 설정
- **유효성 검사 경고 개선** — 알 수 없는 preset 입력 시 유효 목록 + 예시 코드 포함 경고; stacklevel=2

**대시보드 API 확장 (50+ 엔드포인트)**

- **태스크** — `/tasks/{id}` (llm_judge/streaming_steps/chunk_count 추가), `/tasks/search`, `/tasks/filter` (eq/ne/gt/gte/lt/lte/contains/in + AND/OR), `/tasks/bulk-tag`
- **집계·분석** — `/frameworks` (프레임워크별 집계), `/distributions`, `/timeline`, `/aggregate`, `/aggregate/extra`, `/heatmap/{metric}`, `/metrics/{metric_name}`
- **LLM Judge** — `/llm_judge` (min/max_score 필터 + skip/limit + 집계 평균)
- **비교·랭킹** — `/api/compare` (detailed task diff), `/api/leaderboard`, `/api/results` sort_by/sort_desc
- **세션** — `/sessions` (include_turns=True → metadata.tool_calls/model_name/tokens_used 최상위 노출), `/conversation/{session_id}`
- **비용·이상** — `/cost/breakdown`, `/cost/trend`, `/anomaly`, `/anomaly/explain/{event_id}`
- **내보내기·기타** — `/export/excel`, `/api/compare`, WebSocket `/api/ws/events`, SSE `/stream/tasks/{id}` + `/stream/filtered/{id}`, `/cache/stats`, `/rate-limit/status`, `/version`
- **CRUD** — `DELETE /results/{id}` (soft/hard), `POST /golden/candidates/{name}/bulk-approve`, 알림 규칙 파일 영구 저장
- **`/api/health`** OTEL 동적 감지; `/api/stats` 전체 통계

**기타**

- **`ResponseCache`** — TTL 기반 in-memory LRU 캐시; hits/misses/hit_rate 통계
- **`format_error_context()`** — 오류 메시지 컨텍스트 포맷터
- **`ValidationError(context=...)` / `InvalidOperationError(context=...)`** — context Dict 필드 추가
- **`monitor.configure_suspicious_patterns()` / `evaluate_suspicious_patterns()`** — 의심 패턴 탐지
- **테스트** — 55개 파일, 1,634개+ 테스트 함수

### v0.7.1 (2026-04-03) — 데코레이터 커버리지 확대 · 편의성 개선

- **`QuickEval`** 원스톱 Facade — `PerformanceMonitor` + `EvalDecorator` 를 1줄로 시작; `for_rag()`, `for_security()`, `for_llm_judge()` 팩토리 메서드; `gate()`, `summary()`, `save()` 제공
- **`QuickEval.__repr__` 버그 수정** — `tcr_tracker` 없을 때 `AttributeError` → `tasks=0` 안전 반환
- **프레임워크 전용 데코레이터** — `langchain_eval`, `langgraph_eval`, `crewai_eval`, `autogen_eval`, `dspy_eval`, `pydanticai_eval` (`agent_evaluator.integrations`)
- **`_FRAMEWORK_ADAPTERS`** 레지스트리 — `framework=` 파라미터에 따라 응답에서 `tool_calls`/`chain_steps`/`state_transitions` 자동 추출
- **`SimpleTaskAlertRule`** — `StreamingEvaluator` 불필요한 경량 `TaskResult` 기반 알림 규칙; `agent_eval`, `batch_eval`, `eval_context`, `EvalDecorator` 에 `alert_rules=` 파라미터로 통합
- **`flush_every`** — `agent_eval`, `batch_eval` 에 N호출마다 `save_to_file()` 자동 실행 파라미터 추가
- **`auto_save`** — `PerformanceMonitor` 에 N건마다 자동 저장 기능 추가 (`auto_save=True`, `auto_save_interval=10`)
- **`_normalize_task_type()`** — `TaskType.QA` Enum과 `"qa"` 문자열 혼용 지원
- **DSPy / PydanticAI 통합** — `DSPyEvaluator`, `DSPyMetricAdapter`, `PydanticAIEvaluator`, `PydanticAITokenExtractor` 신규; `[dspy]`, `[pydanticai]` extras 추가
- **`batch_eval` / `conversation_eval` / `eval_context` / `EvalDecorator`** — `alert_rules`, `flush_every` 파라미터 API 일관성 적용
- **`Evaluator_Examples/20_quickeval_demo.py`** — 신규 예제 (7섹션)
- **테스트** — 4개 파일 신규 추가 (QuickEval, SimpleTaskAlertRule, framework adapters, auto_save/flush_every)

### v0.7.0 (2026-04-01) — 운영 실시간 모니터링 (Phoenix + OTEL)

- **`agent-eval monitor`** CLI — Arize Phoenix 서버 기동 + OTLP 스팬 수신 설정
- **`setup_otel(endpoint, service_name, enable_metrics=False)`** 공개 API
- **`[otel]` extras** — `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `arize-phoenix` 패키지 그룹 신규
- **`[full]` extras** — otel 패키지 포함으로 업데이트
- **`_emit_otel_span()`** — `PerformanceMonitor.record_task()` 시 OTLP 스팬 자동 발행
- **예제 OTEL 통합** — 17개 예제 파일 모두 Phoenix 자동 연결 (`_try_setup_otel()`)
- **`17_phoenix_verification.py`** 신규 — Phoenix 4개 메뉴(Tracing·Evaluators·Datasets·Prompts) 통합 데모
- **Phoenix 프로젝트 분리** — `OTELProvider` Resource 속성을 `openinference.project.name`으로 수정 → 예제별 독립 프로젝트 생성 (기존 `project.name` 오기 수정)
- **실제 LLM 경로 추가** (06~09) — `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 환경변수 감지 시 실제 API 호출 (`gpt-4o-mini` 기본)
- **알림 핸들러 env-var gating** (12) — `SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_URL` 설정 시 실제 핸들러, 미설정 시 Mock 자동 사용
- **버그 수정**: OTEL 스팬 속성 None 방어 (`ae.framework` 등), metrics 기본 비활성화 (Phoenix `/v1/metrics` 미지원)

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
