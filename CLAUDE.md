# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.6.7 (Beta)
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
pip install -e ".[all]"               # crewai/autogen 제외 전체 (권장)
pip install -e ".[full]"              # 진짜 전체 (⚠️ 10분+ 소요)

# --- CLI (pip install 후 바로 사용 가능) ---
agent-eval init          # 대화형 API 키 설정 마법사
agent-eval check         # 현재 설정 상태 출력
agent-eval dashboard     # FastAPI 대시보드 실행 (기본 포트 8765)  [개발·검증 단계]
agent-eval gate result.json --tcr 85 --accuracy 70   # CI/CD 품질 게이팅
agent-eval dataset build results/ --min-score 0.8    # 골든 데이터셋 자동 추출
agent-eval monitor                                   # 운영 실시간 모니터링 Phoenix + OTEL (v0.7.x 예정)
agent-eval monitor --check                           # OTEL 설치 상태 및 포트 점유 확인
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
│   └── routers/             # API 라우터 11개 (alerts, anomaly, config, conversation, cost, data, export, feedback, golden, stream, transparency, webhook)
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

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 15개 플랫 파일)
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
└── 15_conversation_eval.py  # 멀티턴 대화 평가 — ConversationSession
```

---

## Key Classes

### `PerformanceMonitor`
중앙 오케스트레이터. 모든 트래커를 내부에서 구성.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 False (성능 영향)
    enable_security_metrics=False,         # 기본값 False
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

`tests/` 디렉토리에 36개 파일, 920개 테스트 함수 존재.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

커버리지 현황 (v0.6.7 기준):
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
- `[eval]` — `deepeval>=0.20.0,<4.0.0` + `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` + `langchain>=0.2.0`
- `[serve]` — `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — 빠름
- `[pdf]` — `pypdf>=3.0.0,<7.0.0` + `pdfplumber>=0.10.0,<1.0.0` — 빠름

### Optional (조합 편의 extras)
- `[frameworks]` — `langchain` + `crewai` + `autogen` 한 번에 (기존 호환, 무거움)
- `[all]` — crewai/autogen **제외** 전체 (권장, 합리적 설치 시간) — `pip install agent-evaluator[all]`
- `[full]` — crewai/autogen 포함 진짜 전체 (⚠️ 10분+ 소요) — `pip install agent-evaluator[full]`

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

### v0.6.7 (2026-04-01) — Python 3.13 지원 · 의존성 상한 완화 · 대시보드 버그 수정

- `numpy<3.0.0`, `pandas<4.0.0` 상한 완화 — Python 3.13 wheel 지원
- `pyproject.toml` classifier `Python :: 3.13` 추가, pipx 소스 빌드 실패 해결
- `serve/server.py` Starlette 1.0 `TemplateResponse` API 시그니처 변경 대응 (`name, context` → `request, name, context`) — `agent-eval dashboard` 접속 시 `TypeError: unhashable type: 'dict'` 수정

---

### v0.6.6 (2026-03-31) — Docs 체계 재조정 · 내보내기 버그 수정 · SDK HTML 리포트 개선

- Docs 통합: 8개 → 3개 (`02_METRICS_REFERENCE.md`, `03_FRAMEWORK_GUIDE.md`, `01_QUICK_START.md` 신규)
- `serve/routers/export.py`: HTML 내보내기 TypeError 수정, 태스크 테이블 컬럼명, Hallucination 백분율, CSV 컬럼 9→23개 확장
- `reporting/comprehensive_report.py`: `success_rate` 백분율 변환, 에이전틱 빈 상태, 버전 동적 참조 수정
- `slides.html.j2` JavaScript SyntaxError 수정 — 빈 슬라이드 렌더링 버그 완전 해결
- Lectures 6개 파일 — 명령어·메서드명·필드명 전면 정정

---

### v0.6.5 (2026-03-30) — golden_datasets 위치 재설계 · 이상 감지 파이프라인 완성

- `results/golden_datasets/` → `data/golden_datasets/` 이동 (평가 산출물↔영구 자산 분리)
- `save_to_file()`: `AnomalyDetector.scan()` 결과를 `anomaly_data` 키로 저장 — 대시보드 이상 감지 탭 데이터 연결
- `serve/loader.py` `_parse_anomaly_data()` 중첩 구조 읽기 수정
- `15_conversation_eval.py` 예제 신규 추가 — `ConversationSession` 멀티턴 대화 평가
- 테스트 920개, 36개 파일 (Phase 2/3 신규 6개 파일 추가)

---

### v0.6.0 – v0.6.3 (2026-03-21 ~ 29) — SDK 안정화 + 프레임워크 통합 + 대시보드 초기 안정화

- LangChain / LangGraph / CrewAI / AutoGen 4개 프레임워크 완전 지원
- `RagasAdapter` ragas 0.4.x API 완전 지원, extras 단위 재설계
- FastAPI 대시보드 + `agent-eval dashboard` CLI + 오프라인 모드
- 트래커 캡슐화 강화 (`_xxx` private + `@property`), `record_task()` 메서드 체이닝, 스레드 안전성
- `TaskResult.__hash__` 수정, `save_to_file()` 원자적 쓰기, `from_dict/from_json` 역직렬화 추가
- `PerformanceMonitor.for_rag_evaluation()`, `for_secure_agents()` 팩토리 추가
- `LLMJudge` — LLM-as-Judge 평가 엔진 (ground_truth 없이 3차원 자동 채점)

### v0.2.x – v0.5.x — 초기 구현

- Layer 1/2/3 트래커 25개, `ConversationSession`, `evaluation_session`, `TestTransparencyManager` 초기 구현
