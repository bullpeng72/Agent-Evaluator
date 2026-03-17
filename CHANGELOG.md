# Changelog

All notable changes to `agent-evaluator` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.2] — 2026-03-17

### Added
- **SDK 레퍼런스 페이지 (`/sdk-docs`)** — Agent 평가용 Python SDK 전체 레퍼런스. PerformanceMonitor·TaskResult·TaskType·Layer 1/2/3 트래커·프레임워크 통합 문서화
- **UI API / SDK API 버튼 분리** — 대시보드 헤더의 단일 API 버튼을 `📡 UI API` (Swagger) 와 `📖 SDK` (/sdk-docs) 로 분리
- **CLI 웰컴 화면** — `agent-eval` 인수 없이 실행 시 API 키 현황 프로그레스 바 + 명령어 목록 표시
- **컬러 도움말** — `ColoredHelpFormatter` 적용. TTY에서 섹션 헤더 bold, 플래그 yellow, 예시 green, 환경변수 cyan

### Changed
- **`agent-eval --version`** — `version` 서브커맨드를 표준 `--version` 플래그로 변경
- **브라우저 자동 오픈 기본값 활성화** — `agent-eval serve` 실행 시 `--open` 기본값 `True`
- **`__init__.py` 버전 동기화** — `0.5.0` → `0.5.2` (pyproject.toml 불일치 수정)

### Fixed
- **결과 경로 통일** — `path_helpers.get_evaluation_results_dir()` 이 `results/` 로 통일. Dashboard/data/ 경로 잔존 제거
- **golden dataset 경로** — `serve/routers/golden.py` 에서 stale Streamlit 경로 제거

---

## [0.5.1] — 2026-03-17

### Added
- **FastAPI 대시보드 (`agent-eval serve`)** — Streamlit 완전 대체. Alpine.js + Plotly.js 기반 SPA, 24개 API 라우트
- **OAS 3.1 API 문서** — Swagger UI (`/api/docs`) + Redoc (`/api/redoc`), 헤더에 API 버튼 추가
- **상관관계 히트맵** — 4×4 Pearson 상관 행렬 (정확도·지연시간·토큰수·완료율) Plotly heatmap
- **보안 이벤트 타임라인** — L1/L2 보안 이벤트 scatter 차트
- **Agent 네트워크 그래프** — 멀티에이전트 협업 네트워크 시각화 (Pan/Zoom/Scroll 지원)

### Fixed
- **Ragas 지표 경로 불일치 수정** — `loader.py`가 per-task `advanced_metrics`에서 `ragas_*` 키를 자동 수집해 `rag_metrics` 재구성. `has_rag=True` 정상 작동
- **ragas_ 키 접두어 불일치 수정** — 로더 빌드 시 `ragas_faithfulness` → `faithfulness` 키 정규화 (대시보드 Ragas 탭 표시 정상화)
- **Layer 3 per-task 메트릭 표시 오류 수정** — 템플릿 `t.metrics||{}` → `t.metrics||t` 교정
- **Plotly 차트 높이 상속 수정** — `.cbox .js-plotly-plot{height:200px!important}` → `100%!important`
- **`serve` CLI 결과 디렉토리 자동 탐지** — `./results`가 비어있을 때 `path_helpers.get_evaluation_results_dir()` 폴백 정상 동작

### Changed
- `server.py`: `openapi_version="3.1.0"`, `redoc_url="/api/redoc"` 추가

---

## [0.5.0] — 2024-XX-XX (Beta)

### Added
- **20 evaluation metrics** across three layers: foundation, agentic, and hybrid
- **Layer 1 — Foundation Metrics** (6): TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector, ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker
- **Layer 2 — Agentic Metrics** (9): ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker, AgentCoordinationTracker, WorkflowExecutionTracker + 5 security trackers
- **Layer 3 — Hybrid Evaluation**: HybridPerformanceMonitor with DeepEval, Ragas, LangSmith adapters
- Framework integrations: LangChain, CrewAI, LangGraph, AutoGen
- LLM helpers: `LLMHelper` (OpenAI), `ClaudeHelper` (Anthropic)
- Context manager API: `evaluation_session`, `hybrid_evaluation_session`
- Automatic JSON + HTML report generation
- Korean RAG dataset generator and evaluator
- Streamlit dashboard (in `Evaluator_Examples/Dashboard/`)

### Changed
- Migrated build system: `setuptools` → `hatchling`
- Fixed `pandas` version pin: `>=1.3.0` → `>=1.3.0,<3.0.0`
- Added missing optional deps: `PyPDF2`, `pdfplumber` (now in `[datasets]` extra)
- Added `CHANGELOG.md`, `LICENSE`, `.env.example`

---

## [0.1.0] — Initial Release

- Core `PerformanceMonitor` with basic task completion and accuracy metrics
