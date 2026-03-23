# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a production-ready Python SDK for evaluating AI agents.
25개의 성능 지표를 세 개의 레이어(기본/에이전틱/하이브리드)로 측정한다.

- **Version:** 0.6.0 (Beta)
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
│   ├── agent_evaluator.py   # 모든 16개 트래커 + PerformanceMonitor (5,501줄 — 분리 예정)
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
| 🔴 High | `agent_evaluator.py` 5,501줄 단일 파일 — trackers/ 분리 필요 | `core/agent_evaluator.py` |
| ✅ Fixed | 테스트 없음 — `tests/` 4개 파일, 33개 테스트 함수 작성 완료 | `tests/` |
| 🔴 High | `import re` 9회 함수 내부에서 임포트 → 모듈 상단으로 이동 필요 | `core/agent_evaluator.py` |
| 🔴 High | `os.chdir()` 라이브러리 코드 내 사용 → `importlib` 방식으로 교체 필요 | `utils/dashboard_integration.py:44,82` |
| 🟡 Medium | ~14곳에서 bare `except Exception:` 로 에러 무시 | 여러 파일 |
| 🟡 Medium | `_check_patterns()`, `_is_subsequence()` 중복 구현 | `core/agent_evaluator.py` |
| ✅ Fixed | `pandas>=1.3.0` 상한선 없음 → `<3.0.0` 추가 완료 | `pyproject.toml` |
| ✅ Fixed | `PyPDF2` deprecated → `pypdf>=3.0.0,<7.0.0` 으로 교체 완료 (`pdfplumber` 유지) | `pyproject.toml` |
| ✅ Fixed | `warnings.filterwarnings('ignore')` 전역 적용 → 카테고리/모듈 타겟 필터로 교체 완료 | `integrations/metric_adapters.py` |

---

## Testing

`tests/` 디렉토리에 4개 파일, 33개 테스트 함수 존재.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

현재 테스트 파일:
- `tests/test_accuracy_evaluator.py`
- `tests/test_hallucination_detector.py`
- `tests/test_input_sanitization.py`
- `tests/test_performance_monitor.py`

추가 테스트 필요 항목:
1. `OutputLeakageDetector.detect_leakage()`
2. `ToolCallAnalyzer` / `AgentCoordinationTracker`
3. `PerformanceMonitor.generate_report()` — 집계 파이프라인 end-to-end

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

⚠️ `OutputLeakageDetector`의 generic 패턴 `[a-zA-Z0-9]{32,}`은 false-positive 높음 — 개선 필요.

---

## 📝 변경 이력

### v0.6.0-post (2026-03-23) — 대시보드 품질·RAG·DeepEval 탭 전면 개선

#### 핵심 지표 파이프라인 수정
- 🐛 `HallucinationDetector.detect_hallucination()` — `request` 파라미터 추가, detection dict에 `"question"` 저장 → 상세 화면에 질문 표시
- 🐛 `HybridPerformanceMonitor.record_task()` — `request=input_text` 전파 누락 수정
- 🐛 `PerformanceMonitor.record_task()` — `request=request` 를 `detect_hallucination()` 호출에 전달

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
