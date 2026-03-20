# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.5.6 (Beta)
- **Python:** 3.8+
- **License:** MIT
- **Author:** Sungwoo Kim

---

## Common Commands

```bash
# 개발 환경 설치
pip install -e ".[dev]"

# 선택적 의존성 포함 설치
pip install -e ".[eval,frameworks,llm]"
pip install -e ".[all]"

# --- CLI (pip install 후 바로 사용 가능) ---
agent-eval init          # 대화형 API 키 설정 마법사
agent-eval check         # 현재 설정 상태 출력
agent-eval --version     # 버전 출력

# 테스트 실행 (tests/ 디렉토리 없음 — 아직 생성 필요)
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
agent-eval serve                        # 기본 포트 8765, 브라우저 자동 오픈
agent-eval serve --port 8080 --watch    # 포트 지정 + 파일 변경 자동 갱신
agent-eval serve --no-open              # 브라우저 자동 오픈 비활성화
agent-eval serve --offline              # CDN 에셋 로컬 캐시 (인터넷 없이 실행)
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
│   ├── agent_evaluator.py   # 모든 16개 트래커 + PerformanceMonitor (5,409줄 — 분리 예정)
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
│   └── test_transparency_manager.py  # ⚠️ 프로덕션 클래스 (테스트 파일 아님)
├── examples/
│   └── example_runner.py    # ExampleRunner base class
├── config.py                # 환경변수 설정 로더 (load_env, get_settings)
└── __init__.py              # Public API surface

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 5개 플랫 파일)
├── 01_quality_metrics.py    # 품질 지표 — Accuracy, Hallucination, Quality, RAG
├── 02_performance_metrics.py # 성능 지표 — TCR, Latency, Token Economy
├── 03_agentic_metrics.py    # 에이전틱 지표 — Tool Call, Coordination, Workflow
├── 04_security_metrics.py   # 보안 지표 — Input Sanitization, Leakage, Auth, Escalation
└── 05_hybrid_metrics.py     # 하이브리드 평가 — DeepEval, Ragas, LangSmith 통합
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
monitor.record_task(task_result)
report = monitor.generate_report()
monitor.save_to_file("evaluation")  # JSON + HTML 자동 생성
```

### `TaskResult`
단일 태스크 실행 결과를 담는 dataclass (18개 필드).

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
```

### `TaskType` (Enum)
`QA`, `DATA_ANALYSIS`, `CODE_GENERATION`, `DOCUMENT_CREATION`, `INFORMATION_RETRIEVAL`,
`REASONING`, `CREATIVE`, `CODING`, `PLANNING`, `TOOL_USE`

### `evaluation_session` (Context Manager)
```python
with evaluation_session("output_filename") as monitor:
    result = agent.run(task)
    monitor.record_task(result)
# 세션 종료 시 자동 저장 (예외 발생 시에도 안전)
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
    create_taskresult, evaluation_session, hybrid_evaluation_session,

    # LLM Helpers
    LLMHelper, ClaudeHelper,  # aliases for LLMEvaluationHelper, AnthropicEvaluationHelper

    # Transparency Subsystem
    TestTransparencyManager, AnnotationType, TestStepStatus,

    # Config Helpers
    load_env, get_settings, init_from_app,

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

## Known Technical Debt

| 우선순위 | 항목 | 위치 |
|---------|------|------|
| 🔴 High | `agent_evaluator.py` 5,409줄 단일 파일 — trackers/ 분리 필요 | `core/agent_evaluator.py` |
| 🔴 High | 테스트 없음 — `tests/` 디렉토리 미존재 | 프로젝트 전체 |
| 🔴 High | `import re` 9회 함수 내부에서 임포트 → 모듈 상단으로 이동 필요 | `core/agent_evaluator.py` |
| 🔴 High | `os.chdir()` 라이브러리 코드 내 사용 → `importlib` 방식으로 교체 필요 | `utils/dashboard_integration.py:44,82` |
| 🟡 Medium | ~14곳에서 bare `except Exception:` 로 에러 무시 | 여러 파일 |
| 🟡 Medium | `_check_patterns()`, `_is_subsequence()` 중복 구현 | `core/agent_evaluator.py` |
| ✅ Fixed | `pandas>=1.3.0` 상한선 없음 → `<3.0.0` 추가 완료 | `pyproject.toml` |
| ✅ Fixed | `PyPDF2`, `pdfplumber` `pyproject.toml` 미등록 → `[all]` extra에 포함 완료 | `pyproject.toml` |
| ✅ Fixed | `warnings.filterwarnings('ignore')` 전역 적용 → 카테고리/모듈 타겟 필터로 교체 완료 | `integrations/metric_adapters.py` |

---

## Testing

현재 `tests/` 디렉토리가 없음. 새 테스트 작성 시:

```bash
mkdir tests/
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

테스트 우선순위:
1. `AccuracyEvaluator._qa_accuracy()` — LCS 알고리즘 정확성
2. `HallucinationDetector.detect_hallucination()`
3. `InputSanitizationTracker.evaluate_input()` — 보안 패턴 매칭
4. `OutputLeakageDetector.detect_leakage()`
5. `PerformanceMonitor.generate_report()` — 집계 파이프라인

주의: `agent_evaluator/utils/test_transparency_manager.py`는 테스트 파일이 **아님** — `TestTransparencyManager`라는 프로덕션 클래스임.

---

## Dependencies

### Core (항상 설치됨)
- `numpy>=1.20.0,<2.0.0`
- `pandas>=1.3.0,<3.0.0`
- `python-dotenv>=0.19.0,<2.0.0`

### Optional (extras)
- `[llm]` — `openai>=1.0.0,<3.0.0` + `anthropic>=0.20.0,<1.0.0` — `pip install agent-evaluator[llm]`
- `[frameworks]` — `langchain>=0.1.0,<3.0.0` + `langgraph` + `crewai` + `pyautogen` — `pip install agent-evaluator[frameworks]`
- `[eval]` — `deepeval>=0.20.0,<4.0.0` + `ragas>=0.1.0,<2.0.0` + `langchain` — `pip install agent-evaluator[eval]`
- `[serve]` — `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — `pip install agent-evaluator[serve]`
- `[all]` — 위 모든 것 + `PyPDF2>=3.0.0` + `pdfplumber>=0.10.0` — `pip install agent-evaluator[all]`

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

⚠️ `OutputLeakageDetector`의 generic 패턴 `[a-zA-Z0-9]{32,}`은 false-positive 높음 — 개선 필요.

---

## 📝 변경 이력

### v0.5.6 (2026-03-20) — `datasets` 의존성 상한 추가 및 pipx 설치 오류 수정

- 🐛 `pyproject.toml` `[eval]`·`[all]` extra에 `datasets>=2.14.0` 상한 추가 — ragas/crewai 전이 의존성이 구버전 `datasets` 소스 빌드를 시도해 발생하는 `FileNotFoundError: DESCRIPTION.rst` 수정
- 🔧 `server.py` — deprecated `on_event` → `asynccontextmanager` lifespan 방식으로 리팩터

### v0.5.5 (2026-03-20) — CLI/대시보드/지표 문서 오류 수정 및 Public API 보완

- 🔧 `--share` 옵션 설명 수정 — ngrok 불필요, `host=0.0.0.0` 바인딩으로 정정 (`Docs/13_DEPLOYMENT_GUIDE.md`)
- 🔧 `ResponseQuality.total_score` 범위 수정 — `(0–10)` → `(0–5)` (API 반환값 기준) + `grade` 필드 추가 (`README.md`)
- 📝 CLAUDE.md Public API에 Transparency 서브시스템(`TestTransparencyManager`, `AnnotationType`, `TestStepStatus`) 및 Config 헬퍼(`load_env`, `get_settings`, `init_from_app`) 누락 항목 추가
- 📝 README.md 프로젝트 트리에 `utils/test_transparency_manager.py` 추가
- 📝 Docs/04_LEARNING_GUIDE.md, Docs/01_README.md 최종 업데이트 날짜 2026-03-19 → 2026-03-20

### v0.5.4 (2026-03-20) — DEEPEVAL_API_KEY 제거 및 문서·SDK 레퍼런스 정비

- 🔧 `DEEPEVAL_API_KEY` 제거 — 실제 코드에서 미사용, `config.py`·`cli/main.py`·`README` 전파 제거
- 🔧 `evaluation_session` 시그니처 오류 수정 (async → sync @contextmanager)
- 🔧 `ResponseQualityEvaluator` 6차원 → 5차원 수정 (안전성 제거, 가중치 명시)
- 📝 `sdk_docs.html.j2` 16개 트래커 API 명세 전면 추가 — TaskResult/TaskType/create_taskresult 오류 수정
- 📝 README 연도 2024 → 2026, 예시 파일명 현행화
- 📝 `results/` 예시 데이터 git 추적 추가
- 🗑️ `verify_installation.py` 삭제 (미사용, 구식 Streamlit 참조 포함)
- 🗑️ `Docs/Metrics/` 개별 지표 파일 삭제 (06_METRICS_GUIDE.md 통합)
- ✨ `agent_evaluator/py.typed` 추가 (PEP 561)
