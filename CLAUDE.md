# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.6.3 (Beta)
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
agent-eval dashboard     # FastAPI 대시보드 실행 (기본 포트 8765)
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

# 대시보드 실행 (FastAPI, v0.5.2+)
agent-eval dashboard                        # 기본 포트 8765, 브라우저 자동 오픈
agent-eval dashboard --port 8080 --watch    # 포트 지정 + 파일 변경 자동 갱신
agent-eval dashboard --no-open              # 브라우저 자동 오픈 비활성화
agent-eval dashboard --offline              # CDN 에셋 로컬 캐시 (인터넷 없이 실행)
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
│   ├── agent_evaluator.py   # re-export facade (34줄) — trackers/ 분리 완료
│   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   └── monitor_context.py   # Context managers
├── integrations/
│   ├── crewai_integration.py
│   ├── langchain_integration.py
│   ├── langgraph_integration.py
│   ├── autogen_integration.py
│   ├── llm_helpers.py       # LLMEvaluationHelper, AnthropicEvaluationHelper
│   ├── metric_adapters.py   # DeepEval/Ragas/LangSmith adapters
│   └── framework_integrations.py
├── helpers/
│   └── taskresult_helpers.py  # create_taskresult(), token extraction utils
├── reporting/
│   └── comprehensive_report.py  # HTML/text report generation
├── datasets/
│   ├── korean_rag_dataset_generator.py
│   └── korean_rag_evaluator.py
├── serve/                   # FastAPI 대시보드 서버 (v0.5.2+)
│   ├── server.py            # FastAPI app 진입점
│   ├── loader.py            # 평가 결과 로더
│   ├── watcher.py           # 파일 변경 감시 (--watch)
│   └── routers/             # API 라우터 (data, export, golden, stream, transparency, config, webhook)
├── cli/
│   └── main.py              # agent-eval CLI 진입점
├── utils/
│   ├── dashboard_integration.py  # Dashboard storage path helper
│   ├── data_registry.py     # 평가 결과 데이터 레지스트리
│   ├── path_helpers.py      # 결과 디렉토리 경로 헬퍼
│   └── transparency_manager.py  # TestTransparencyManager 프로덕션 클래스
├── examples/
│   └── example_runner.py    # ExampleRunner base class
├── config.py                # 환경변수 설정 로더 (load_env, get_settings)
└── __init__.py              # Public API surface

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 10개 플랫 파일)
├── 01_quality_eval.py       # 품질 지표 — Accuracy, Hallucination, Quality, RAG
├── 02_performance_eval.py   # 성능 지표 — TCR, Latency, Token Economy
├── 03_agentic_eval.py       # 에이전틱 지표 — Tool Call, Coordination, Workflow
├── 04_security_eval.py      # 보안 지표 — Input Sanitization, Leakage, Auth, Escalation
├── 05_hybrid_eval.py        # 하이브리드 평가 — DeepEval, Ragas, LangSmith 통합
├── 06_langchain_eval.py     # LangChain 프레임워크 통합 예제
├── 07_langgraph_eval.py     # LangGraph 프레임워크 통합 예제
├── 08_crewai_eval.py        # CrewAI 프레임워크 통합 예제
├── 09_autogen_eval.py       # AutoGen 프레임워크 통합 예제
└── 10_cross_framework_eval.py # 멀티 프레임워크 비교 평가
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
# metrics.coherence_score, .context_retention_score, .avg_response_quality, ...
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
| ✅ Fixed | `agent_evaluator.py` 5,501줄 단일 파일 — `core/trackers/` 서브패키지 분리 완료 | `core/agent_evaluator.py` |
| ✅ Fixed | 테스트 없음 — `tests/` 31개 파일, 756개 테스트 함수 작성 완료 (커버리지 10%) | `tests/` |
| ✅ Fixed | `import re` 9회 함수 내부에서 임포트 → 모듈 상단으로 이동 완료 | `core/trackers/monitor.py` |
| ✅ Fixed | `os.chdir()` 라이브러리 코드 내 사용 → 제거 완료 | `utils/dashboard_integration.py` |
| 🟡 Medium | ~9곳에서 bare `except Exception:` 로 에러 무시 | `core/trackers/monitor.py` |
| 🟡 Medium | `_check_patterns()`, `_is_subsequence()` 중복 구현 가능성 확인 필요 | `core/trackers/` |
| ✅ Fixed | `pandas>=1.3.0` 상한선 없음 → `<3.0.0` 추가 완료 | `pyproject.toml` |
| ✅ Fixed | `PyPDF2` deprecated → `pypdf>=3.0.0,<7.0.0` 으로 교체 완료 (`pdfplumber` 유지) | `pyproject.toml` |
| ✅ Fixed | `warnings.filterwarnings('ignore')` 전역 적용 → 카테고리/모듈 타겟 필터로 교체 완료 | `integrations/metric_adapters.py` |

---

## Testing

`tests/` 디렉토리에 31개 파일, 756개 테스트 함수 존재.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

주요 테스트 파일 (29개):
- `tests/test_accuracy_evaluator.py`, `test_hallucination_detector.py`, `test_input_sanitization.py`, `test_performance_monitor.py` (기존)
- `tests/test_task_ids_dedup.py` — Round 62: _task_ids 중복 방지 (36개)
- `tests/test_latency_cache_and_tool_patterns.py` — Round 62: LatencyTracker 캐시 + ToolCallAnalyzer (20개)
- `tests/test_api_fixes_r63_r65.py` — Round 63–65: API 수정 검증 (22개)
- `tests/test_monitor_coverage_r68.py` — Round 68: PerformanceMonitor 커버리지 (52개)
- `tests/test_hybrid_monitor_coverage_r68.py` — Round 68: HybridPerformanceMonitor 커버리지 (33개)
- `tests/test_base_and_layer1_coverage_r68.py` — Round 68: base.py/layer1.py 커버리지 (78개)
- `tests/test_taskresult_helpers_r69.py` — Round 69: taskresult_helpers.py 커버리지 (109개)

커버리지 현황 (Round 69 기준):
- `base.py`: 92% | `layer1.py`: 84% | `layer2.py`: 95%
- `hybrid_monitor.py`: 61% | `monitor.py`: 41% | `taskresult_helpers.py`: 89% | 전체: 10%

주의: `agent_evaluator/utils/test_transparency_manager.py`는 테스트 파일이 **아님** — `TestTransparencyManager`라는 프로덕션 클래스임.

---

## Dependencies

### Core (항상 설치됨)
- `numpy>=1.20.0,<2.0.0`
- `pandas>=1.3.0,<3.0.0`
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

### v0.6.3 (2026-03-29) — SDK 안정화 — Security Tracker 캡슐화 · rag_metrics 스레드 안전성 · golden_datasets 보호 (Round 35)

#### 🔒 Security Tracker 캡슐화 (5개 — Round 34 패턴 완전 적용)
- `security.py` — `InputSanitizationTracker.evaluations`, `OutputLeakageDetector.detections`, `ToolAuthorizationTracker.tool_calls`, `PrivilegeEscalationDetector.escalation_events`, `ToolChainAttackDetector.detections` → private `_xxx` + `@property` (shallow copy) + setter (load_from_file 호환)

#### 🐛 `rag_metrics` property — thread-safety 수정 (Round 35)
- `monitor.py` — `rag_metrics` property: `return self._rag_metrics` (직접 참조) → `return {k: list(v) for k, v in self._rag_metrics.items()}` (shallow copy)
- 이전: `monitor.rag_metrics['key'].append(...)` 로 `_lock` 우회 가능 → 이후: 복사본 반환으로 내부 상태 보호

#### 🔒 `golden_datasets` 캡슐화 (Round 35)
- `monitor.py` — `self.golden_datasets` → `self._golden_datasets` (private) + `@property` + setter
- `load_golden_dataset()` 반환값도 `list(self._golden_datasets)` 복사본으로 변경

#### 📝 `record_task()` docstring 수정 (Round 35)
- `monitor.py` — `Returns: None.` → `Returns: PerformanceMonitor: self, enabling method chaining` (Round 34 변경 후 docstring 불일치 수정)

### v0.6.3 (2026-03-29) — SDK 안정화 — Tracker 캡슐화 전면 강화 · 메서드 체이닝 · thresholds 타입 검증 (Round 34)

#### 🔒 Tracker 내부 상태 캡슐화 (9개 Tracker + ConversationSession)
- `layer1.py` — `TaskCompletionTracker.tasks`, `ResponseQualityEvaluator.evaluations`, `LatencyTracker.latencies`, `TokenEconomyTracker.usage_log` → private `_xxx` + `@property` (shallow copy) + setter (load_from_file 호환)
- `layer1.py` — `HallucinationDetector.detections` setter 추가 (load_from_file 회귀 수정 — 기존 세터 없어 직접 할당 실패하던 버그)
- `layer2.py` — `ToolCallAnalyzer.executions`, `RetryCorrectionTracker.attempts`, `ToolSelectionTracker.selections`, `AgentCoordinationTracker.interactions`, `WorkflowExecutionTracker.executions` → 동일 패턴 적용
- `conversation.py` — `ConversationSession.turns` → private `_turns` + `@property` + setter

#### ✨ `PerformanceMonitor.record_task()` 메서드 체이닝 지원 (Round 34)
- `monitor.py` — `record_task()` 반환 타입 `None` → `PerformanceMonitor`; `return self` 추가
- 이제 `monitor.record_task(t1).record_task(t2).generate_report()` 체이닝 가능

#### 🐛 `thresholds` 타입 안전성 (Round 34)
- `monitor.py` — `self.thresholds` → `self._thresholds` (private) + `@property` + `@thresholds.setter` 추가
- setter에서 dict 타입 검증 + 값이 숫자인지 검증 → `ValidationError` (기존: 잘못된 타입 조용히 수락)

### v0.6.3 (2026-03-29) — SDK 안정화 — hash 버그 수정 · 원자적 쓰기 · EvaluationReport 의미론 · update_pricing (Round 33)

#### 🐛 `TaskResult.__hash__` TypeError 수정 (CRITICAL)
- `base.py` — `frozen=True` 자동 생성 `__hash__`가 `tokens_used: Dict`·`tool_calls: List` unhashable 필드로 항상 `TypeError` 발생 → `__hash__` 명시 override: `return hash(self.task_id)`
- `base.py` — `__hash__` 추가 시 `__post_init__` 검증 코드가 unreachable에 위치하는 회귀 버그 동시 수정 (validation 복원)

#### 🐛 `save_to_file()` 원자적 쓰기 (Round 33)
- `monitor.py` — `import tempfile` 추가
- `monitor.py` — JSON 저장: `open(filename, 'w')` → `tempfile.mkstemp()` + `os.replace()` (프로세스 종료 시 파일 손상 방지)
- `monitor.py` — HTML 저장: 동일 원자적 쓰기 패턴 적용

#### ✨ `EvaluationReport.__eq__` 의미론적 비교 (Round 33)
- `base.py` — `EvaluationReport.__eq__()` 추가: `timestamp` 제외 데이터 필드만 비교 (JSON 왕복 후 `==` 일관성 보장)

#### ✨ `TokenEconomyTracker.update_pricing()` 추가 (Round 33)
- `layer1.py` — `update_pricing(pricing)` 메서드 추가: 생성 후 가격 변경 가능, `__init__`과 동일한 검증 적용

#### 🐛 `AccuracyEvaluator.reset()` 캐시 무효화 순서 수정 (Round 33)
- `layer1.py` — `reset()` 내 `_cached_avg = None`을 `_evaluations.clear()` 이전으로 이동 (스레드 경쟁 조건 차단)

### v0.6.3 (2026-03-29) — SDK 안정화 — flush 버그 수정 · 직렬화 완전성 · 타입 안전성

#### 🐛 flush() 다중 버그 수정 + 스레드 안전성 (Round 32 — SDK 관점 평가 3차)
- `monitor.py` — `flush()` `hallucination_detector.detections.clear()` no-op 버그 수정 → `reset()` 사용
- `monitor.py` — `flush()` 전체 트래커 클리어를 직접 속성 접근 → `reset()` 메서드로 통일 (일관성·유지보수성)
- `monitor.py` — `reset()` 내 트래커 초기화를 `with self._lock:` 보호 영역으로 이동 (스레드 안전성)
- `monitor.py` — `_iter_trackers()` 반환 타입 `-> Iterator[BaseTracker]` 추가 (mypy/pyright 지원)
- `monitor.py` — `compare_with_thresholds()` 임계값 타입 검증 추가: 숫자가 아닌 값 → `ValidationError` (런타임 에러 위치 명확화)
- `monitor.py` — typing import에 `Iterator` 추가

#### ✨ 직렬화 완전성 (Round 32)
- `base.py` — `EvaluationReport.from_dict()` / `from_json()` classmethods 추가 (to_dict/to_json 역방향 지원)
- `conversation.py` — `ConversationMetrics.from_dict()` classmethod 추가 (to_dict 역방향 지원)
- `conversation.py` — `import dataclasses` 추가

#### 🐛 타입 힌트 수정 (Round 32)
- `helpers/taskresult_helpers.py` — `calculate_completion_score()` `ground_truth: str = None` → `ground_truth: Optional[str] = None` (mypy 에러 수정)

### v0.6.3 (2026-03-29) — SDK 안정화 — 불변성 · 팩토리 API · 직렬화 · 스레드 안전성

#### ✨ SDK API 강화 (Round 31 — SDK 관점 평가 2차)
- `base.py` — `TaskResult` → `@dataclass(frozen=True)`: 기록된 태스크 불변성 보장, `__post_init__` 내 `object.__setattr__` 사용
- `base.py` — `TaskResult.from_dict()` / `from_json()` classmethods 추가: JSON 직렬화 → 역직렬화 완전 지원, ISO-8601 timestamp 자동 변환
- `monitor.py` — `PerformanceMonitor.for_rag_evaluation()` 팩토리 classmethod 추가 (hallucination 기본 활성화)
- `monitor.py` — `PerformanceMonitor.for_secure_agents()` 팩토리 classmethod 추가 (security 기본 활성화)
- `hybrid_monitor.py` — `HybridPerformanceMonitor.__init__()` `**parent_kwargs` 추가: `pricing`, `model_name`, `enable_llm_judge` 등 부모 인자 전달 가능 (LSP 준수)
- `hybrid_monitor.py` — `ExtendedTaskResult` → `@dataclass(frozen=True)`: 부모와 일관성
- `conversation.py` — `ConversationTurn.__repr__()` 추가 (40자 미리보기)
- `conversation.py` — `ConversationMetrics.__repr__()` / `__str__()` 추가 (디버깅·로깅 친화적 출력)

#### 🐛 불변성 관련 버그 수정 (Round 31)
- `monitor.py` — `record_task()` deprecated params 처리: 직접 필드 대입 → `dataclasses.replace()` (frozen 호환)
- `monitor.py` — LLM Judge 블록을 `with self._lock:` 이전으로 이동: judge 결과를 `dataclasses.replace()`로 적용 후 tcr_tracker에 저장
- `monitor.py` — `flush()` `self.accuracy_evaluator.evaluations.clear()` → `self.accuracy_evaluator.reset()` (property 복사본 clear 버그 수정)
- `layer1.py` — `AccuracyEvaluator.evaluations` property: `return self._evaluations` → `return list(self._evaluations)` (외부 변경으로부터 내부 상태 보호)
- `monitor.py` — `generate_report()` 0-태스크 호출 시 `logger.warning()` 추가
- `monitor.py` — `record_task()` docstring에 deprecated params 마이그레이션 가이드 추가

### v0.6.3 (2026-03-29) — SDK 안정화 — 스레드 안전성 · API 일관성 · 보안 tracker 완전성

#### 🐛 보안 tracker API 완전성 (Round 22–23)
- `security.py` — `InputSanitizationTracker.get_security_stats()` 빈 상태 완전한 10-키 구조 반환 (Round 22)
- `security.py` — `OutputLeakageDetector.get_leakage_stats()` 빈 상태 완전한 13-키 구조 반환 (Round 23)
- `security.py` — `ToolAuthorizationTracker.get_compliance_stats()` 빈 상태 완전한 9-키 구조 반환 (Round 23)
- `security.py` — `PrivilegeEscalationDetector.get_escalation_stats()` 빈 상태 완전한 6-키 구조 반환 (Round 23)
- `security.py` — `ToolChainAttackDetector.get_attack_stats()` 빈 상태 완전한 8-키 구조 반환 (Round 23)

#### 🐛 계산 정확도 (Round 22–23)
- `monitor.py` — `_has_score` 조건에서 `!= 0.0` 제거: `accuracy_score=0.0`을 재평가 트리거로 오인하던 버그 수정 (Round 22)
- `monitor.py` — retry 합성 로그 `"duration": 1.0` 하드코딩 → `execution_time / attempts` 실제 비율로 교체 (Round 23)
- `layer1.py` — `HallucinationDetector.__repr__()` indicator 개수 기반 오계산 → `hallucination_score` 평균으로 수정 (Round 23)

#### 🐛 타입 안전성 (Round 22–23)
- `monitor.py` — `compare_with_thresholds()` 품질 점수 키 존재 여부 명시적 검증 추가 (Round 22)
- `monitor.py` — `response or` falsy 패턴 → `response if response is not None else` 명시적 None 검사 (Round 22)
- `layer1.py` — `evaluate_response()` 시그니처 `expected_elements: List[str]` → `Optional[List[str]] = None` (Round 23)

#### 🔒 스레드 안전성
- `monitor.py` — `record_task()` 전체 트래커 뮤테이션 블록 `with self._lock:` 보호 (동시 write race 방지)
- `monitor.py` — `record_rag_metrics()` / `rag_metrics` → `_rag_metrics` private + 읽기 전용 property
- `monitor.py` — `reset()` 내 `_rag_metrics.clear()` / `golden_datasets.clear()` lock 보호
- `monitor.py` — `compare_with_thresholds()` RAG 메트릭 읽기 lock 스냅샷으로 보호

#### 🐛 기타 버그 수정
- `monitor.py` — `reset()` 내 `conversation_sessions.clear()` 누락 수정 (CI 루프 세션 데이터 오염)
- `monitor.py` — `compare_with_thresholds()` RAG status: `threshold=0.0` + 데이터 없음 → 'pass' 오류 → 'pending' 우선 반환
- `monitor.py` — retry 중복 방지 set에서 `task_id=None` 항목 필터링
- `layer1.py` — `evaluate_response()` `expected_elements=None` 전달 시 TypeError 수정 (`or []` guard)
- `layer1.py` — `TokenEconomyTracker.__init__()` 필수 키 존재 + `isinstance` 숫자 타입 검증 (KeyError / TypeError → ValidationError)
- `layer1.py` — `AccuracyEvaluator.record_score()` 추가: `_cached_avg` 캐시 무효화 보장
- `layer1.py` — `AccuracyEvaluator.get_accuracy_scores()` 빈 상태 7개 키 완전 일치 + `dropna()` NaN 필터링
- `layer1.py` — `AccuracyEvaluator.__repr__()` accuracy=None 항목 분모 제외
- `layer1.py` — `HallucinationDetector.get_hallucination_rate()` 빈 상태 키 구조 완전 일치
- `layer1.py` — `HallucinationDetector.detections` → `_detections` private; 읽기 전용 property + 얕은 복사 반환
- `layer2.py` — `ToolCallAnalyzer.get_efficiency_stats()` 빈 상태 `avg_efficiency_score: 100.0` → `0.0` (미측정 ≠ 완벽) + all-None NaN 방지
- `layer2.py` — `analyze_execution()` 도달 불가 `else: efficiency_score = 100.0` dead code 제거

#### 🐛 지표 계산 정확도 (Round 24–25)
- `layer1.py` — `ResponseQualityEvaluator.evaluate_response()` `completeness`: 예상 요소 없을 때 `1.0` 고정 → 응답 길이 기반 휴리스틱 `min(word_count/150, 1.0)` (Round 24)
- `layer1.py` — `get_quality_metrics()` `total_score` NaN guard: `dropna().mean()` + `pd.isna()` 체크 (Round 25)
- `layer1.py` — `TokenEconomyTracker.get_usage_by_type()` multi-level DataFrame 컬럼 → `"_".join(col)` flatten 후 `to_dict("index")` (Round 25)
- `layer2.py` — `ToolCallAnalyzer.get_tool_usage_patterns()` `avg_call_duration` dropna + `notna().any()` guard (Round 24)

#### 🐛 직렬화·repr 수정 (Round 26–27)
- `base.py` — `EvaluationReport.to_dict()` `dataclasses.asdict()` datetime 미변환 → 재귀 `_convert()` 헬퍼로 ISO-8601 직렬화 (Round 26)
- `layer1.py` — `HallucinationDetector.__repr__()` 잘못된 키 `"hallucination_score"` → `"hallucination_rate"` 수정 (repr 항상 0.0 표시 버그) (Round 27)
- `layer2.py` — `get_tool_usage_patterns()` 미사용 변수 `all_tools = []` dead code 제거 (Round 27)

#### 🐛 sentinel 값·API 일관성 (Round 28–30)
- `conversation.py` — `_compute_context_retention()` 이전 턴 top 토큰 없을 때 `1.0` 추가 → 해당 턴 제외(skip), fallback `else 1.0` → `else 0.5` (미측정 중립) (Round 28)
- `layer2.py` — `get_delegation_success_rate()` `d["success"]` → `d.get("success", False)` KeyError 방어 (Round 29)
- `layer1.py` — `AccuracyEvaluator.__repr__()` `e["accuracy"]` → `e.get("accuracy")` 키 접근 일관성 (Round 29)
- `conversation.py` — `ConversationSession.__exit__()` 반환 타입 `None` → `bool`, 명시적 `return False` 추가 (Round 29)
- `conversation.py` — `compute_metrics()` `ValueError` → `InvalidOperationError` (SDK 예외 계층 사용) (Round 29)
- `conversation.py` — `compute_metrics()` 내 stddev 계산 `/ 4.0` 하드코딩 → `/ len(component_scores)` (Round 29)

### v0.6.2 (2026-03-27) — 대시보드 보안 L1/L2 상세 패널 + 에이전틱·품질 탭 개선

- ✨ 대시보드 보안 L1 도구 권한 — `tracking_active` 플래그 도입: 추적 미활성 경고 배너·점선 KPI 카드·태스크별 폴백 테이블
- ✨ 대시보드 보안 L1 도구 권한 — 상세 패널: 개별 auth 레코드 테이블(6열) ↔ 태스크별 도구 호출 테이블 분기 표시
- ✨ 대시보드 보안 L2 권한상승·공격탐지 — L1과 동일한 미활성 패턴 적용 (경고 배너, 그레이 KPI, 태스크 폴백)
- ✨ 대시보드 보안 L2 상세 패널 — 상승 이벤트(초기권한·최대권한·위험도·경로) + 공격 체인(체인길이·패턴·신뢰도) 테이블 재설계
- 🐛 L2 요약 통계 카드 가로 레이아웃 — Alpine.js `x-show`+flex 충돌 → `<template x-if>`로 교체
- 🐛 `loader.py` L1/L2 `tracking_active` 탐지 로직 추가 (`total_tool_calls=0` & 태스크 도구 호출 있음 → `False`)
- 🐛 품질 탭 환각 탐지 Layer 1/3 분리 + `TaskResult` raw content 필드 추가
- 🐛 보안·에이전틱 탭 차트 경로 오류 3건 수정 + KPI 산출식·설명 개선
- 🔧 SDK 문서 탭 Layer 1 카드 grid 레이아웃 적용
- 🔧 DeepEval 상세 테이블 헤더 명확화
- ✨ `agent-eval dashboard` 명령어 추가 (Dev Dashboard)
- ✨ 지표 비교 테이블 — 레이더 6축 전체 포함 + 3섹션 구조
- 🔧 파일 비교 레이더를 에이전트 역량 레이더와 동일 관점(6축)으로 통일

### v0.6.1 (2026-03-23) — 보안 탭 감사 수정 + 에이전틱/대시보드 개선 일괄 배포

- 🐛 `loader.py` — `file_path_leaks` 누락 수정 (`OutputLeakageDetector.contains_file_path` → 8번째 유출 유형 집계)
- ✨ 대시보드 보안 탭 — 출력 유출 유형 7개 → 8개 (File Path 카드 추가), L1/L2 레이어 레이블 추가
- 🔧 보안 종합 점수 툴팁 — `"가중 평균"` → `"단순 평균"` (실제 구현과 일치)
- 🔧 에이전틱 탭명 재설계: `기본` → `⚡ 실행·재시도`, `심화` → `🎯 도구·협업·흐름`, `통합` → `🔍 실행 트레이스`
- ✨ 에이전틱 Tool 선택·멀티에이전트·워크플로우 탭 — KPI 클릭 시 계산식 + 상세 패널
- 🐛 `avg_retry_time` 분모 버그 수정, `overall_retry_rate` 복붙 버그 수정
- 🐛 `frameworkDist()` 분모 버그 수정 (`data.total_tasks` → `tasks.length`)
- ✨ 에이전틱 역량 레이더 — 꼭지점 설명·공식 카드 우측 1열 배치

### v0.6.0-post (2026-03-23) — 대시보드 전면 개선 (품질·RAG·DeepEval·에이전틱·보안 탭)

#### 핵심 지표 파이프라인 수정
- 🐛 `HallucinationDetector.detect_hallucination()` — `request` 파라미터 추가, detection dict에 `"question"` 저장 → 상세 화면에 질문 표시
- 🐛 `HybridPerformanceMonitor.record_task()` — `request=input_text` 전파 누락 수정
- 🐛 `PerformanceMonitor.record_task()` — `request=request` 를 `detect_hallucination()` 호출에 전달
- 🐛 `avg_retry_time` — 전체 태스크로 나누던 버그 수정 → `df[df["total_attempts"]>1]` 필터 후 평균
- 🐛 `overall_retry_rate` — `retry_rate` 복붙 버그 수정 → `(total_retries/total_attempts)*100` 올바른 공식
- 🔧 `RetryCorrectionTracker.track_attempts()` — `task_type` 파라미터 추가 (태스크 유형 분포 차트)

#### 대시보드 Quality 탭
- 🔧 품질 점수 스케일 `/10` → `/5` 통일 (ResponseQualityEvaluator 실제 범위 반영)
- 🔧 환각 게이지 공식 수정: `(hall/30)*100` → `Math.min(100, hall)` (항상 100% 표시 버그 수정)
- 🔧 환각 유형별 분류 — 확장 가능한 상세 패널 추가 (질문·컨텍스트·심각도 표시)
- 🔧 G-Eval 단일 점수 기반 vs ResponseQualityEvaluator 개별 측정 설명 노트 추가
- 🔧 차원별 의미 설명 (relevance / completeness / clarity / accuracy / usefulness)

#### 대시보드 RAG 탭
- ✨ Ragas Overall Score KPI 카드 추가 (기본·심화 공통)
- 🔧 수직 레이아웃으로 재구성: 📖 지표 설명 → 차트 → 태스크별 상세
- 🔧 4개 지표 설명 카드 추가 (Faithfulness / Answer Relevancy / Context Recall / Context Precision / Overall)
- 🔧 KPI sub-text: `N건 평가` → `N건 | min X / max X` (범위 표시)
- 🔧 호버 툴팁 소수점 수정: `0.6666667` → `0.667` (`hovertemplate:'%{y:.3f}'`)
- 🔧 태스크별 RAG 상세 테이블 컬럼 정렬 수정 (flex + 고정 width)

#### 대시보드 DeepEval 탭
- 🔧 KPI 카드에서 Ragas 지표(`ragas_*`) 제거 → DeepEval 전용 지표만 표시
- 🔧 지표 요약 바에서 Ragas 지표 제거 (양쪽 티어 모두)
- 🔧 수직 레이아웃으로 재구성: 📖 지표 설명 → G-Eval 분포 → 지표 요약
- 🔧 DeepEval 미설치 배너 제거 → "지표 없음" 메시지로 통일

#### 대시보드 에이전틱 탭 전면 개선
- 🔧 탭 이름 재설계: `기본` → `⚡ 실행·재시도`, `심화` → `🎯 도구·협업·흐름`, `통합` → `🔍 실행 트레이스`
- 🔧 재시도 탭 — 컬럼 정렬: `<table>` → flexbox `drow` 패턴으로 교체 (Alpine.js `:style` 오버라이드 버그 해결)
- ✨ Tool 선택 탭 — KPI 클릭 시 계산식 + 태스크 상세 패널 (Alpine.js x-data 기반)
- ✨ 멀티에이전트 탭 — KPI 클릭 시 계산식 + 인터랙션 상세 패널
- ✨ 워크플로우 탭 — KPI 클릭 시 계산식 + 단계별 상세 패널 (5개 KPI: 단계수·성공단계·단계성공률·태스크수·태스크완료율)
- 🔧 워크플로우 퍼널 차트 — 막대 순서 재정렬: 단계 그룹 / 태스크 그룹으로 묶기
- 🔧 `🏗️ 프레임워크 정보` — 통합 탭 → 심화-워크플로우 탭으로 이동
- 🐛 `frameworkDist()` 분모 버그 수정: `data.total_tasks` → `tasks.length` (직접 등록 태스크와의 불일치 해결)
- ✨ 에이전틱 역량 레이더 — 각 꼭지점 설명·공식 카드 우측 1열 배치 (레이더 좌측 + 설명 우측 레이아웃)

#### 대시보드 보안 탭 개선
- 🐛 `loader.py` `_parse_security_l1()` — `file_path_leaks` 누락 수정 (`contains_file_path` 카운트 추가)
- ✨ 출력 유출 유형 7개 → 8개 확장: File Path 카드 추가 (tracker 실제 탐지 유형과 일치)
- ✨ 입력 위협 — `위협 이벤트` KPI 추가 (유형별 합산, 중복 허용) / `위협 입력` KPI 병행 표시 (태스크 기준 중복 제거)
- 🔧 보안 종합 요약 카드 — L1/L2 레이어 레이블 추가 (입력위협·출력유출·권한준수=L1, 권한상승·공격체인=L2)
- 🐛 보안 종합 점수 툴팁 — `"가중 평균"` → `"단순 평균"` (실제 구현과 일치)

### v0.6.0 (2026-03-21) — 4개 프레임워크 완전 지원 + ragas 0.4.x + 의존성 재설계

#### 프레임워크 최신 버전 완전 지원 (LangChain 1.2.x / LangGraph 1.1.x / CrewAI 1.11.x / AutoGen 0.7.x)
- ✨ LangChain — `agent.invoke(config={"callbacks":[...]})` (LCEL Runnable), Chat 모델 토큰 멀티 포맷 통합, `langchain>=1.0.0` 상향
- ✨ LangGraph — `from_compiled()` 기존 그래프 직접 래핑, `stream()` 전환으로 노드별 실측 타이밍 수집, `START` import 추가
- ✨ CrewAI — `result.raw` / `crew.usage_metrics` / `result.tasks_output` 기반 실측 추적, `kickoff_async()` 지원, `crewai>=1.0.0` 상향
- ✨ AutoGen — async-first 재설계, `on_messages()` + `team.run()` 통합, `ToolCallRequestEvent`/`ToolCallExecutionEvent` 기반 도구 추적, `run_sync()` 동기 래퍼 추가

#### 지표 커버리지 전면 확대 (4개 프레임워크 공통)
- ✨ `HallucinationDetector` — RAG 컨텍스트 자동 수집·연결 (LangChain retriever, LangGraph ToolMessage, CrewAI 중간 태스크, AutoGen 도구 결과)
- ✨ `AgentCoordinationTracker` — LangGraph 노드 전환 감지 → from/to 쌍 자동 기록
- ✨ `RetryCorrectionTracker` — LangChain `on_retry`, AutoGen `is_error=True` 도구 실패, LangGraph/CrewAI 실패 노드·태스크 감지
- ✨ `ResponseQualityEvaluator` — 4개 프레임워크 모두 request/response 기반 5차원 자동 연결
- ✨ `ToolCallAnalyzer` + `ToolSelectionTracker` — 4개 프레임워크 `_record_layer2()` 전면 연결
- ✨ `TokenEconomy` model_name 추적 — `on_chat_model_start` / `model_client.total_usage()` / tiktoken fallback
- ✨ 보안 트래커 opt-in — `enable_security=True` 플래그로 `InputSanitizationTracker` / `OutputLeakageDetector` / `ToolAuthorizationTracker` / `PrivilegeEscalationDetector` / `ToolChainAttackDetector` 전체 자동 초기화 (4개 프레임워크 + `create_evaluated_*` 편의 함수 전파)
- 🔧 `generate_report()` — ResponseQuality·Hallucination·ToolCallAnalyzer·PrivilegeEscalation·ToolChainAttack·Retry 통계 균일 출력

#### ragas 0.4.x 및 의존성 구조 재설계
- ✨ `RagasAdapter` — ragas 0.4.x API 완전 지원 (`EvaluationDataset`/`SingleTurnSample`, 클래스 인스턴스 방식, 필드명 전면 변경)
- 🔧 `pyproject.toml` — `[all]`에서 crewai·pyautogen 분리, `[langchain]`/`[crewai]`/`[autogen]`/`[pdf]`/`[full]` 단위 extras 추가
- 🔧 `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` 상한 조정
- 🐛 pydantic silent downgrade 경고 문서화, deprecated `PyPDF2` → `pypdf>=3.0.0,<7.0.0` 교체
- 🐛 `serve/routers/golden.py` 한국어 어미 필터 오버필터링 수정 (`_is_bad_token()`, `_SUBJ_PARTICLES`)
- 🔧 `server.py` deprecated `on_event` → `asynccontextmanager` lifespan 방식

### v0.5.x (2026-03-20) — 초기 안정화 및 문서·의존성 정비

- ✨ `py.typed` 추가 (PEP 561 타입 스텁 선언)
- ✨ FastAPI 대시보드 서버(`agent-eval serve`) 초기 구현 — 포트 지정·파일 변경 감시·오프라인 모드
- ✨ `agent-eval init` / `check` CLI 명령어 추가
- 🔧 `ResponseQualityEvaluator` 6차원 → 5차원 정리 (안전성 제거, 가중치 명시), `total_score` 범위 `(0–10)` → `(0–5)` 수정
- 🔧 `evaluation_session` 시그니처 수정 (async → sync @contextmanager)
- 🔧 `DEEPEVAL_API_KEY` 전 코드베이스에서 제거 (미사용 환경변수)
- 🔧 Public API에 `TestTransparencyManager` / `AnnotationType` / `TestStepStatus` / `load_env` / `get_settings` / `init_from_app` 추가
- 🔧 `datasets` 의존성 상한 추가 — `FileNotFoundError: DESCRIPTION.rst` 설치 오류 수정
- 🔧 LangGraph `AIMessage.usage_metadata` 토큰 추출 + `ToolMessage` 파싱 도구 추적
- 🔧 AutoGen tiktoken 우선 토큰 추정 + 한/영 휴리스틱 fallback
- 🐛 `sdk_docs.html.j2` TaskResult/TaskType/create_taskresult API 명세 오류 수정
- 🗑️ `verify_installation.py` 삭제, `Docs/Metrics/` 개별 파일 → `06_METRICS_GUIDE.md` 통합
- 📝 `FRAMEWORK_METRICS_MAP.md` 추가, `tests/` 33개 테스트 함수 현행화
