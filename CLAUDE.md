# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator**는 **Harness Engineering** 기반 AI 에이전트 배포 준비도 평가 SDK다.
단순 정확도 측정을 넘어 **7개 Harness Gate(A–G)로 에이전트가 프로덕션에 배포할 준비가 됐는지** 종합 판정한다.

- **Gate A** — Goal Achievement: 지시 이행률·목표 정렬·계획 일관성·컨텍스트 유지
- **Gate B** — Behavioral Integrity: 루프 탐지·범위 일탈·도구 안전성·상태 일관성
- **Gate C** — Reliability: 재현 가능성·오류 복구율·품질 하한·멱등성
- **Gate D** — Performance Contract: SLA·토큰 효율·TTFT 변동성·비용 예측
- **Gate E** — Security Boundary: 위협 심각도·규정 준수·위협 대응
- **Gate F** — Multi-Agent Coordination: 합의율·정보 전파·역할 준수·충돌 해결
- **Gate G** — Observability: 추론 설명·상태 추적·오류 진단·지연 분석

**25개 Native Trackers + 33개 Harness Config = 58개 지표**를 3개 레이어(Foundation / Agentic / Hybrid)로 측정한다.

- **Version:** 0.8.2 (Beta)
- **Python:** 3.8+
- **License:** MIT
- **Author:** Sungwoo Kim

---

## Common Commands

```bash
# 개발 환경 설치 (기본 설치에 LLMJudge · 대시보드 · OTEL · PDF 포함)
pip install -e ".[dev]"

# ── 예제 실행 ────────────────────────────────────────────────────────────────
# 예제 01~08: 기본 설치만으로 실행 (추가 설치 불필요)
# 예제 07 (Phoenix Hybrid): eval extra 필요
pip install -e ".[examples]"          # 모든 예제 실행 가능 (기본 + eval)

# ── 프레임워크 확장 (사용자 에이전트 코드가 필요로 할 때만 설치) ────────────
pip install -e ".[eval]"              # DeepEval / Ragas 외부 평가 라이브러리
pip install -e ".[langchain]"         # LangChain / LangGraph 통합
pip install -e ".[dspy]"              # DSPy 통합 (dspy-ai)
pip install -e ".[pydanticai]"        # PydanticAI 통합 (pydantic-ai)
pip install -e ".[crewai]"            # CrewAI 단독 (무거움 — 전이 의존성 100개+)
pip install -e ".[autogen]"           # AutoGen 단독 (무거움, 단독 격리)
pip install -e ".[full]"              # 전체 (⚠️ crewai/autogen 포함, 10분+ 소요)

# ── CLI (pip install 후 바로 사용 가능) ──────────────────────────────────────
agent-eval init          # 대화형 API 키 설정 마법사
agent-eval check         # 현재 설정 상태 출력
agent-eval dashboard     # FastAPI 대시보드 실행 (기본 포트 8765)
agent-eval gate result.json --tcr 85 --accuracy 70   # CI/CD 품질 게이팅
agent-eval dataset build results/ --min-score 0.8    # 골든 데이터셋 자동 추출
agent-eval monitor                                   # Arize Phoenix 서버 기동 + OTLP 스팬 수신
agent-eval monitor --port 6006                       # Phoenix 포트 지정 (기본: 6006)
agent-eval monitor --check                           # OTEL 패키지 및 포트 점유 상태 확인
agent-eval trend results/                            # 최근 10개 결과 파일 TCR·정확도 추세 분석
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

### 58개 지표 = 25 Native Trackers + 33 Harness Config Dataclasses

```
Layer 1 — Foundation Metrics (native, no external deps)
  TaskCompletionTracker     → Task Completion Rate (TCR)
  AccuracyEvaluator         → QA / Code / General accuracy (Token F1 · Jaccard · LCS · Levenshtein)
  HallucinationDetector     → Fact consistency scoring
  ResponseQualityEvaluator  → 5-dimension quality assessment
  LatencyTracker            → Percentile-based latency (P50 · P90 · P95 · P99 · TTFT)
  TokenEconomyTracker       → Token usage + cost estimation

Layer 2 — Agentic Metrics (native, no external deps)
  ToolCallAnalyzer          → Tool usage patterns
  RetryCorrectionTracker    → Retry behavior
  ToolSelectionTracker      → F1-based tool selection accuracy
  AgentCoordinationTracker  → Multi-agent interaction
  WorkflowExecutionTracker  → Workflow success/branching
  InputSanitizationTracker  → Security: input injection detection (40+ patterns)
  OutputLeakageDetector     → Security: sensitive data in output
  ToolAuthorizationTracker  → Security: unauthorized tool use
  PrivilegeEscalationDetector → Security: privilege abuse
  ToolChainAttackDetector   → Security: chained attack patterns

Layer 3 — Hybrid Evaluation (requires optional deps)
  HybridPerformanceMonitor  → Layer 1+2 + external metric adapters
  DeepEvalAdapter           → DeepEval library integration
  RagasAdapter              → RAGAS RAG evaluation
  LLMJudge (native)         → faithfulness + judge_criteria (G-Eval/Ragas 대체)
    • 5차원: completeness · relevance · factual_consistency · toxicity · bias
    • RAG: faithfulness (rag_mode=True + context 시 자동 추가)
    • G-Eval: criteria_scores / criteria_overall (judge_criteria=[...] 시 자동 추가)

Harness Engineering — 33 Config Dataclasses, 7 Gate Groups (A–G)
  → 데코레이터 파라미터로 전달, PerformanceMonitor가 자동 집계
  → 대시보드 Harness Gate 탭에서 그룹별 통과/경고/실패 시각화
```

### Harness Config Groups (7개 Gate, 33개 Config)

```
Group A — Goal Achievement (6)
  InstructionConfig         → 지시 이행률 · 이탈 감지
  GoalAlignmentConfig       → 목표 정렬 점수 · 부분 달성 인정
  PlanConfig                → 계획 일관성 · 단계 완주율
  SubtaskConfig             → 하위 태스크 분해·완료율
  ContextRetentionConfig    → 대화 컨텍스트 유지율
  KnowledgeRetentionConfig  → 지식 보존·활용 점수

Group B — Behavioral Integrity (6)
  LoopDetectionConfig       → 반복 루프 탐지 · 루프 임계값
  ScopeConfig               → 범위 일탈 감지 · allowed_actions
  ToolParameterSafetyConfig → 도구 파라미터 안전성 · 금지 패턴
  ContextWindowConfig       → 컨텍스트 창 활용 효율
  StateConsistencyConfig    → 실행 전후 상태 일관성 · unchanged_keys
  DeadlockConfig            → 교착 탐지 · circular delegation · starvation

Group C — Reliability (5)
  ReproducibilityConfig     → 동일 입력 반복 실행 일관성
  FaultToleranceConfig      → 오류 후 복구율 · 정상 완료 비율
  GracefulDegradationConfig → 품질 하한 · partial_result_markers
  RetryConsistencyConfig    → 재시도 간 응답 일관성
  IdempotencyConfig         → 멱등성 검증 · 중복 실행 안전성

Group D — Performance Contract (5)
  SLAConfig                 → SLA 응답시간 임계값 · P95/P99 위반율
  EfficiencyConfig          → 토큰 효율 · 도구 호출 대비 완료율
  ResourceBudgetConfig      → 토큰 예산 · 비용 상한
  TTFTVariabilityConfig     → TTFT 표준편차 · P95/P50 비율 (monitor 수준 자동 집계)
  CostPredictabilityConfig  → task_type별 토큰 CV · 비용 예측 가능성 (monitor 수준 자동 집계)

Group E — Security Boundary (3)
  ThreatSeverityConfig      → 위협 심각도 분류 · 임계값 차단
  ComplianceConfig          → 규정 준수 패턴 · 금지 키워드
  ThreatResponseConfig      → 위협 탐지 후 대응 행동 검증

Group F — Multi-Agent Coordination (4)
  ConsensusConfig           → 에이전트 간 합의율 · 분쟁 탐지
  PropagationConfig         → 정보 전파 정확도 · 왜곡 감지
  AgentRoleConfig           → 역할 준수율 · 역할 위반 탐지
  ConflictResolutionConfig  → 충돌 해결 패턴 · 해결 시간

Group G — Observability (4)
  ExplainabilityConfig      → 추론 과정 설명 가능성
  ObservabilityConfig       → 내부 상태 노출 · 추적 가능성
  ErrorDiagnosisConfig      → 오류 원인 진단 정확도
  LatencyAttributionConfig  → 지연 원인 분석 · 구간별 기여도
```

### Module Layout

```
agent_evaluator/
├── decorators.py            # agent_eval · batch_eval · conversation_eval · EvalDecorator · EvalMetadata
│                            # 33개 Harness Config 데이터클래스 정의 포함
│                            # RetryConfig · LLMJudgeConfig · SecurityConfig (데코레이터 유틸 3종)
├── quick_eval.py            # QuickEval — 원스톱 평가 Facade (v0.7.1+)
├── core/
│   ├── agent_evaluator.py   # re-export facade — trackers/ 분리 완료
│   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   ├── monitor_context.py   # Context managers
│   ├── otel/                # OpenTelemetry 통합 (기본 설치에 포함)
│   │   ├── provider.py      # OTELProvider — TracerProvider 설정
│   │   └── metrics.py       # OTELMetrics — 메트릭 익스포터 (opt-in)
│   └── trackers/            # 트래커 서브패키지
│       ├── base.py          # BaseTracker, TaskResult, EvaluationReport, TaskType
│       ├── layer1.py        # Layer 1: TaskCompletion·Accuracy·Hallucination·Quality·Latency·TokenEconomy
│       ├── layer2.py        # Layer 2: ToolCall·Retry·ToolSelection·Coordination·Workflow
│       ├── security.py      # Layer 2 보안: InputSanitization·OutputLeakage·ToolAuth·Escalation·ChainAttack
│       ├── conversation.py  # ConversationSession·ConversationMetrics·ConversationTurn
│       ├── feedback.py      # ImplicitFeedbackTracker
│       └── monitor.py       # PerformanceMonitor (중앙 오케스트레이터 + Harness 집계)
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
│   ├── llm_judge.py         # LLMJudge — LLM-as-Judge 평가 엔진 (기본 설치에 포함)
│   ├── metric_adapters.py   # DeepEval/Ragas adapters
│   └── framework_integrations.py
├── helpers/
│   └── taskresult_helpers.py  # create_taskresult(), token extraction utils
├── reporting/
│   └── comprehensive_report.py  # Harness Gate A–G 중심 HTML/text 리포트 생성
│                                 # generate_html_from_result_file(rf) — export 라우터 전용
├── datasets/
│   ├── builder.py           # GoldenSetBuilder — 골든 데이터셋 자동 확장
│   ├── korean_rag_dataset_generator.py
│   └── korean_rag_evaluator.py
├── serve/                   # FastAPI 대시보드 서버 (기본 설치에 포함)
│   ├── server.py            # FastAPI app 진입점
│   ├── loader.py            # 평가 결과 로더 (parse_file · load_results)
│   ├── watcher.py           # 파일 변경 감시 (--watch)
│   ├── templates/
│   │   ├── dashboard2.html.j2   # Harness Gate 대시보드 (Alpine.js + Plotly, Nav 3단 계층)
│   │   └── slides.html.j2       # Harness Gate 슬라이드 (Reveal.js, 14슬라이드 Gate A–G)
│   └── routers/             # API 라우터 13개
├── cli/
│   ├── main.py              # agent-eval CLI 진입점
│   ├── gate.py              # agent-eval gate — CI/CD 품질 게이팅
│   ├── trend.py             # agent-eval trend — 순차 실행 결과 추세 분석
│   └── dataset.py           # dataset 서브커맨드 (build)
├── utils/
│   ├── dashboard_integration.py  # Dashboard storage path helper
│   ├── data_registry.py     # 평가 결과 데이터 레지스트리
│   ├── path_helpers.py      # 결과 디렉토리 경로 헬퍼
│   └── transparency_manager.py  # TestTransparencyManager 프로덕션 클래스
├── exceptions.py            # SDK 예외 계층
├── config.py                # 환경변수 설정 로더 (load_env, get_settings)
└── __init__.py              # Public API surface

Evaluator_Examples/          # 실제 사용 예시 (패키지 외부, 9개 파일)
├── 01_layer1_all_metrics.py      # Layer 1 전체 — Accuracy·Hallucination·Quality·Latency·Token·TCR
├── 02_layer2_agentic_security.py # Layer 2 전체 — ToolCall·Retry·Coordination·Workflow·Security·대화
├── 03_framework_adapters.py      # 프레임워크 어댑터 — LangChain·LangGraph·CrewAI·AutoGen + 크로스 파이프라인
├── 04_decorator_quickeval.py     # 데코레이터 전체 API — @agent_eval·@batch_eval·@conversation_eval·QuickEval·LLMJudge
├── 05_streaming_alerts.py        # 실시간 — StreamingEvaluator·ImplicitFeedback·AlertEngine·SimpleTaskAlertRule
├── 06_operational.py             # 운영 인프라 — AnomalyDetector·CostTracker·GoldenSetBuilder·evaluation_session
├── 07_phoenix_hybrid.py          # Phoenix OTEL — Tracing·Datasets·Playground·GraphQL + DeepEval·Ragas(opt-in)
├── 08_harness_eval.py            # Harness Engineering — 7개 Gate(A-G) · 33개 Config 실전 평가
└── 08_harness_validation.py      # Harness Config 파라미터 검증 · 경계 케이스 테스트
# 기존 21개 예제: Evaluator_Examples/.deprecated/ 에 보존

scripts/
└── phoenix_check.py         # Phoenix 통합 자동 점검 — GraphQL 역조회로 pass/fail 판정

Docs/
├── 01_GETTING_STARTED.md    # 설치·첫 평가·대시보드 최단 경로
├── 02_METRICS_GUIDE.md      # 58개 지표 공식·출력키·임계값 (Harness Gate A–G 중심)
├── 03_INTEGRATION_GUIDE.md  # 프레임워크 통합 가이드
├── 04_DATA_GUIDE.md         # 골든 데이터셋·결과 파일 구조
├── 05_QUALITY_GATE.md       # CI/CD 품질 게이팅 가이드
├── 06_OBSERVABILITY.md      # OTEL·Phoenix 관측가능성
├── 07_OPERATIONS.md         # 운영 인프라·비용 관리
└── 08_API_REFERENCE.md      # 전체 Public API 문서
```

---

## Key Classes

### `QuickEval`
원스톱 평가 Facade — `PerformanceMonitor` + `EvalDecorator` 를 1~2줄로 시작.

```python
from agent_evaluator import QuickEval

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
# 재시도: @eval.with_retry(task_type="qa", retry=RetryConfig(max=3))
```

### PerformanceMonitor vs HybridPerformanceMonitor 선택 가이드

| 항목 | `PerformanceMonitor` | `HybridPerformanceMonitor` |
|------|---------------------|---------------------------|
| 외부 의존성 | 없음 (Layer 1+2 native + Harness) | DeepEval / Ragas 필요 (`[eval]` extra) |
| LLM Judge | ✅ 내장 (`llm_judge=LLMJudgeConfig()`) | ✅ 동일 |
| Faithfulness | ✅ 내장 (`rag_mode=True`) | ✅ + Ragas 방식도 가능 |
| G-Eval | ✅ 내장 (`judge_criteria=[...]`) | ✅ + DeepEval 방식도 가능 |
| Harness Config | ✅ 33개 Config 전부 지원 | ✅ 동일 |
| 추천 상황 | 대부분의 프로덕션 환경 | DeepEval/Ragas 생태계와 통합 시 |

> **권장**: 신규 프로젝트는 `PerformanceMonitor`로 시작.

### `PerformanceMonitor`
중앙 오케스트레이터. 모든 트래커와 Harness Config 집계를 내부에서 구성.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 False (성능 영향)
    enable_security_metrics=False,         # 기본값 False
    # LLM Judge (opt-in)
    enable_llm_judge=False,                # True 이면 모든 태스크에 LLM 채점 적용
    judge_model=None,                      # None → API 키 기반 자동 결정
    judge_sample_rate=0.1,                 # 10%만 채점 (비용 절감)
    judge_criteria=None,                   # G-Eval 커스텀 기준 ["medical_accuracy", ...]
    # 자동 저장
    auto_save=False,
    auto_save_interval=10,
    auto_save_filename="auto_save",
)
monitor.record_task(task_result)           # PerformanceMonitor 반환 — 메서드 체이닝 가능
report = monitor.generate_report()
monitor.save_to_file("evaluation")        # JSON + HTML 자동 생성

# 팩토리 classmethods
monitor_rag = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
monitor_sec = PerformanceMonitor.for_secure_agents(output_dir="results/")
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

# 직렬화 / 역직렬화
d = result.to_dict()
result2 = TaskResult.from_dict(d)      # ISO-8601 timestamp 자동 변환
result3 = TaskResult.from_json(json_str)
```

### `TaskType` (Enum)
`QA`, `DATA_ANALYSIS`, `CODE_GENERATION`, `DOCUMENT_CREATION`, `INFORMATION_RETRIEVAL`,
`REASONING`, `CREATIVE`, `CODING`, `PLANNING`, `TOOL_USE`

### `evaluation_session` / `async_evaluation_session` (Context Managers)
```python
with evaluation_session("output_filename") as monitor:
    result = agent.run(task)
    monitor.record_task(result)
# 세션 종료 시 자동 저장 (예외 발생 시에도 안전)

async with async_evaluation_session("output_filename") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

### `LLMJudge` — Safety / Faithfulness / G-Eval
LLM-as-Judge 채점 엔진. ground_truth 없이 최대 7+개 차원으로 자동 채점.

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(
    model="claude-haiku-4-5-20251001",  # None → API 키 기반 자동 결정
    sample_rate=0.1,
    judge_criteria=["medical_accuracy", "citation_quality"],  # G-Eval 대체
)

# 기본 5차원 채점
result = judge.judge("t1", question="...", response="...")
result["scores"]["overall"]        # 품질 3차원 평균
result["scores"]["safety_score"]   # (10 - toxicity - bias) / 10

# RAG faithfulness (context 전달 시 자동 추가)
result = judge.judge("t2", question="...", response="...", context="검색된 문서...")
result["scores"]["faithfulness"]   # 0–5

# G-Eval 커스텀 기준
result["scores"]["criteria_scores"]   # {"medical_accuracy": 4, "citation_quality": 5}
result["scores"]["criteria_overall"]  # 커스텀 기준 평균

# 데코레이터에서 직접 사용
from agent_evaluator.decorators import LLMJudgeConfig
@agent_eval(monitor, rag_mode=True, llm_judge=LLMJudgeConfig(criteria=["safety", "evidence_based"]))
def rag_agent(question, context="", ground_truth=""): ...
```

### Harness Config 데코레이터 사용법

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig,     # Group A
    LoopDetectionConfig, StateConsistencyConfig, DeadlockConfig,  # Group B
    FaultToleranceConfig, GracefulDegradationConfig,  # Group C
    SLAConfig, EfficiencyConfig,                # Group D
    ThreatSeverityConfig, ComplianceConfig,     # Group E
    ConsensusConfig, AgentRoleConfig,           # Group F
    ExplainabilityConfig, ObservabilityConfig,  # Group G
)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa",
    instruction=InstructionConfig(required_keywords=["서울"], strict=True),
    loop_detection=LoopDetectionConfig(max_loop_count=3, loop_threshold=0.85),
    sla=SLAConfig(max_response_time=5.0, p95_threshold=3.0),
    explainability=ExplainabilityConfig(min_reasoning_steps=2),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### Framework-Specific Decorators
`agent_eval(framework=...)` 파라미터로 21개 프레임워크의 응답에서 메타데이터를 자동 추출한다.

```python
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# 지원 프레임워크 (21개): langchain, langgraph, crewai, autogen, dspy, pydanticai,
# anthropic, openai, gemini, llamaindex, haystack, vertexai, ollama, cohere,
# groq, mistral, bedrock, smolagents, semantic_kernel, vllm, huggingface
```

### `ConversationSession` (멀티턴 대화 평가)
```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn

session = ConversationSession(session_id="conv_001")
session.add_turn(user_input="안녕하세요", agent_response="안녕하세요!")
metrics: ConversationMetrics = session.compute_metrics()
# metrics.turn_count, .overall_score, .context_retention, .topic_coherence,
# .progressive_depth, .session_completion, .avg_turn_latency

# monitor와 통합 (권장)
with monitor.conversation("session_id") as conv:
    conv.turn(user="안녕하세요", agent="안녕하세요!", metadata={"latency": 0.3})

# @conversation_eval 데코레이터
@conversation_eval(monitor, max_turns=20)
def chatbot(session_id: str, question: str, ground_truth: str = "") -> str: ...
```

### `SimpleTaskAlertRule`
`StreamingEvaluator` 없이 `TaskResult` 기반으로 동작하는 경량 알림 규칙.

```python
from agent_evaluator import SimpleTaskAlertRule

rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)

@agent_eval(monitor, task_type="qa", alert_rules=[rule])
def agent(question, ground_truth=""): ...
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

    # LLM Judge (기본 설치에 포함)
    LLMJudge,

    # Decorator Config Dataclasses (v0.8.1+)
    RetryConfig, LLMJudgeConfig, SecurityConfig,

    # Harness Config — Group A: Goal Achievement
    InstructionConfig, GoalAlignmentConfig, PlanConfig, SubtaskConfig,
    ContextRetentionConfig, KnowledgeRetentionConfig,

    # Harness Config — Group B: Behavioral Integrity
    LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig,
    ContextWindowConfig, StateConsistencyConfig, DeadlockConfig,

    # Harness Config — Group C: Reliability
    ReproducibilityConfig, FaultToleranceConfig, GracefulDegradationConfig,
    RetryConsistencyConfig, IdempotencyConfig,

    # Harness Config — Group D: Performance Contract
    SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
    TTFTVariabilityConfig, CostPredictabilityConfig,

    # Harness Config — Group E: Security Boundary
    ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig,

    # Harness Config — Group F: Multi-Agent Coordination
    ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig,

    # Harness Config — Group G: Observability
    ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig, LatencyAttributionConfig,

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
2. **Harness 독립성** — 33개 Harness Config는 decorators.py 단일 파일에서 정의 + monitor.py에서 집계
3. **트래커 분리** — 각 트래커는 독립적으로 테스트 가능해야 함
4. **side-effect 최소화** — 라이브러리 코드에서 `sys.path`, `os.chdir()`, 전역 state 변경 금지
5. **보안 지표 격리** — 보안 트래커는 성능에 영향을 주므로 opt-in
6. **serve 분리** — `agent_evaluator/serve/`는 선택적 FastAPI 서버이며 핵심 평가 로직이 의존해선 안 됨

---

## Dependency Constraints (Known)

| 항목 | 상태 | 설명 |
|------|------|------|
| `ragas>=0.4.0` | ✅ 지원 | 0.4.x API(EvaluationDataset, SingleTurnSample) 완전 지원. `datasets>=4.0.0,<6.0.0` 함께 적용 |
| `[crewai,autogen]`/`[full]` pydantic 충돌 | 🟡 허용 | crewai(pydantic<2.12) + pyautogen(pydantic>=2.12 선호) 동시 설치 시 pydantic 2.11.x로 silent downgrade |
| `pyautogen>=0.3.0` 0.4+ async API | 🟡 부분 지원 | 0.4+(autogen-agentchat 0.4+)는 async API → `@agent_eval(framework="autogen")`으로 async 함수 래핑 권장 |
| `AnswerRelevancy` embeddings | 🟡 조건부 | OpenAI API 키 있을 때만 자동 설정. Anthropic-only 환경에서는 AnswerRelevancy 지표 제외됨 |

---

## Testing

`tests/` 디렉토리에 **53개 파일, 2,465개+ 테스트 함수** 존재.

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
코어 + SDK 자체 기능(LLMJudge · 대시보드 · OTEL · PDF)이 모두 포함됩니다.

- `numpy>=1.20.0,<3.0.0` — 수치 연산
- `pandas>=1.3.0,<4.0.0` — 지표 집계
- `python-dotenv>=0.19.0,<2.0.0` — 환경변수 관리
- `openai>=1.0.0,<3.0.0` + `anthropic>=0.20.0,<1.0.0` — LLMJudge 엔진
- `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — 웹 대시보드
- `opentelemetry-sdk>=1.20.0` + `opentelemetry-exporter-otlp-proto-http>=1.20.0` + `arize-phoenix>=7.0.0` — OTEL 모니터링
- `pdfplumber>=0.10.0,<1.0.0` — 한국어 RAG PDF 처리

### 선택 extras
- `[examples]` — 기본 + eval 묶음. 예제 01~08은 기본만 필요, 07은 eval 추가 필요
- `[eval]` — `deepeval>=3.0.0,<4.0.0` + `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` + `langchain>=1.0.0` + `langchain-openai>=0.1.0`
- `[langchain]` — `langchain>=1.0.0,<3.0.0` + `langchain-core/openai/anthropic>=1.0.0` + `langgraph>=1.0.0`
- `[dspy]` — `dspy-ai>=2.0.0`
- `[pydanticai]` — `pydantic-ai>=1.0.0,<2.0.0`
- `[crewai]` — `crewai>=1.0.0,<2.0.0` — 무거움 (전이 의존성 100개+), 단독 격리
- `[autogen]` — `pyautogen>=0.3.0,<1.0.0` + `autogen-agentchat/core>=0.4.0` — 무거움, 단독 격리
- `[full]` — 기본+eval+langchain+dspy+pydanticai+crewai+autogen 전체 (⚠️ 10분+ 소요)
- `[dev]` — `pytest` + `pytest-cov` + `pytest-asyncio` + `ruff` + `mypy` + `build` + `twine` + `pre-commit`

> ⚠️ **프레임워크 extras 주의**: SDK 어댑터는 duck typing/try-except로 동작하므로 설치 불필요. 이 extras는 **사용자의 에이전트 코드**가 해당 프레임워크를 필요로 할 때 설치.

---

## Accuracy Evaluation Strategy

`AccuracyEvaluator`가 사용하는 QA 정확도 계산 방식:

| 지표 | 가중치 | 방식 |
|------|--------|------|
| Token Overlap | 40% | F1 기반 토큰 매칭 (정밀도-재현율 조화평균) |
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

### v0.8.2 (2026-04-17) — Harness Config 33개 양식 통일 · 대시보드 UI 개선

- Harness Config 카드 33개 아이콘·수식·임계값 배지 양식 통일; `08_harness_eval.py` 예제 추가
- 대시보드 Nav 3단 계층 재편; Gate 상관 히트맵(7×7 Pearson) · 실패 연쇄 추적 추가
- HTML 리포트 Gate A–G 중심 전면 재편; CSV export Gate 컬럼 16개 추가
- 그룹 분류 수정: StateConsistencyConfig·DeadlockConfig Group F→B 이동
- 테스트 파일 2개 추가 (52개 파일, 2,465개+)

### v0.8.1 (2026-04-14) — 데코레이터 파라미터 구조화

- `RetryConfig` · `LLMJudgeConfig` · `SecurityConfig` 3개 구조체 도입; 개별 파라미터 제거
- `enable_hallucination` → `enable_hallucination_detection` 이름 통일
- 테스트 548개 추가; 파일 72→49개 리구조화

### v0.8.0 (2026-04-13) — 정확도 지표 전면 개선

- Token Overlap F1(조화평균) 교체; Char Similarity Levenshtein 통일
- task_type 인식 completion_score: code_generation AST 파싱, tool_use 미사용 시 0.6

### v0.7.9 (2026-04-13) — RunTrendAnalyzer · arize-phoenix 호환 수정

- `RunTrendAnalyzer` + `agent-eval trend` — 추세 분석 · `--fail-on-regression` CI/CD 연동
- arize-phoenix 버전 제약 충돌 수정

### v0.7.8 (2026-04-12) — SDK 기본 내장

- `pip install agent-evaluator` 단독으로 LLMJudge · 대시보드 · OTEL 사용 가능

### v0.7.7 (2026-04-11) — 데코레이터 버그 수정 · 스레드 안전성

- `agent_eval` preset 파라미터 미적용 버그 수정; Layer 2 트래커 5개 `threading.Lock` 추가

### v0.7.6 (2026-04-10) — LLMJudge G-Eval/Ragas 대체

- `judge_criteria` G-Eval 커스텀 채점; `rag_mode=True` 시 `faithfulness` 자동 추가

### v0.7.0–v0.7.5 (2026-04-01~09) — OTEL/Phoenix · 3종 데코레이터 · QuickEval

- `agent-eval monitor` CLI · Arize Phoenix 실시간 모니터링
- 3종 데코레이터 완성(`agent_eval`·`batch_eval`·`conversation_eval`) · `QuickEval` Facade
- 21개 프레임워크 어댑터 · 보안 트래커 실동작 버그 수정(CRITICAL)

### v0.6.x (2026-03-21~04-01) — SDK 안정화

- LangChain/LangGraph/CrewAI/AutoGen · FastAPI 대시보드 · LLMJudge · ConversationSession

### v0.2.x–v0.5.x — 초기 구현

- Layer 1/2/3 트래커 25개 · `evaluation_session` 초기 구현
