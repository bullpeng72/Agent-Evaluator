# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 0.9.4 (Beta) | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Dev environment
pip install -e ".[dev]"
pip install -e ".[sdk]"       # dashboard + OTEL + LLMJudge + PDF (recommended)
pip install -e ".[examples]"  # all examples runnable (sdk + eval)

# CLI
agent-eval init                                           # API key setup wizard
agent-eval check                                          # config status
agent-eval version                                        # version info
agent-eval dashboard                                      # FastAPI dashboard (port 8765)
agent-eval gate result.json --tcr 85 --accuracy 70        # CI/CD quality gating
agent-eval dataset build results/ --min-score 0.8         # golden dataset
agent-eval monitor                                        # Arize Phoenix + OTLP
agent-eval trend results/ --fail-on-regression            # trend analysis
agent-eval trend results/ --output-json trend.json

# Quality
pytest
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/

# Build
python -m build
twine upload dist/*
```

---

## Architecture

### 3-Layer Structure

```
Layer 1 — Foundation (no external deps)
  TaskCompletionTracker · AccuracyEvaluator · HallucinationDetector
  ResponseQualityEvaluator · LatencyTracker · TokenEconomyTracker

Layer 2 — Agentic (no external deps)
  ToolCallAnalyzer · RetryCorrectionTracker · ToolSelectionTracker
  AgentCoordinationTracker · WorkflowExecutionTracker
  Security: InputSanitizationTracker · OutputLeakageDetector
           ToolAuthorizationTracker · PrivilegeEscalationDetector · ToolChainAttackDetector

Layer 3 — Hybrid (optional deps: DeepEval / Ragas)
  HybridPerformanceMonitor · DeepEvalAdapter · RagasAdapter
  LLMJudge (native — faithfulness, G-Eval replacement, 5-dim scoring)
```

### Key Files

```
agent_evaluator/
├── decorators.py          # agent_eval · batch_eval · conversation_eval + 33 Harness Config dataclasses
│                          # EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError 계층
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker, TaskResult, EvaluationReport, TaskType
│   │   ├── layer1.py      # Layer 1 trackers
│   │   ├── layer2.py      # Layer 2 trackers
│   │   ├── security.py    # Security trackers
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator)
│   │   ├── conversation.py# ConversationSession, ConversationMetrics, ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas 통합)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native)
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   ├── dspy_integration.py
│   └── pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware
├── cli/main.py            # CLI entry point (subcommands: init·check·version·dashboard·gate·dataset·monitor·trend)
└── serve/
    ├── server.py          # FastAPI dashboard (103 routes)
    └── routers/           # alerts · anomaly · config · conversation · cost · data · export
                           # feedback · golden · stream · transparency · webhook
```

### Harness Gate Config Groups (33 total)

| Gate | Configs |
|------|---------|
| A — Goal Achievement (6) | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig |
| B — Behavioral Integrity (6) | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig |
| C — Reliability (5) | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig |
| D — Performance Contract (5) | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig |
| E — Security Boundary (3) | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig |
| F — Multi-Agent Coordination (4) | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig |
| G — Observability (4) | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig |

Gate A–G results stored under `extra_metrics.harness_groups` in JSON result files.

### Native Tracker → Gate Score Contribution (`_compute_harness_groups`)

| Tracker | Gate | 기여 배열 | 조건 |
|---------|------|----------|------|
| `TaskCompletionTracker` | A, C | `_a_vals`, `_rel_vals` | 항상 |
| `AccuracyEvaluator` | **A** | `_a_vals` | `_evaluations` 건수 > 0 (overall_accuracy / 100 정규화) |
| `LatencyTracker` | D | `_perf_vals` | 항상 |
| `TokenEconomyTracker` | D | `_perf_vals` | 항상 |
| `HallucinationDetector` | **C + G** | `_rel_vals`, `_obs_vals` | LLM Judge faithfulness 없을 때 폴백 (`1 − rate`) |
| `LLMJudge` (faithfulness) | **C** | `_rel_vals` | per-task faithfulness 기록 시 우선 사용 (`score / 5` 정규화); HallucinationDetector 대체 |
| `RetryCorrectionTracker` | C | `_rel_vals` | SLAConfig 설정 시 |
| `ToolCallAnalyzer` | B, G | `_bint_vals`, `_obs_vals` | tool_calls 기록 시 |
| `WorkflowExecutionTracker` | B | `_bint_vals` | chain_steps 기록 시 |
| Security Trackers (5종) | E | `_all_e_scores` | `enable_security_metrics=True` |
| `AgentCoordinationTracker` | F | `_f_vals` | agent_interactions 기록 시 |
| `ToolSelectionTracker` | F | `_f_vals` | expected_tools 지정 시 |
| `ResponseQualityEvaluator` | — | quality_metrics 별도 집계 | Gate 점수 미포함 |

---

## Key Usage Patterns

### QuickEval (one-stop facade)

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""): ...

@eval.rag
def rag_agent(question, context="", ground_truth=""): ...

eval.save()
eval.gate(tcr=85, accuracy=70)  # sys.exit(1) on failure

# Factories
QuickEval.for_rag("results/")
QuickEval.for_security("results/")
QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### PerformanceMonitor

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # default False
    enable_security_metrics=False,         # default False
    enable_llm_judge=False,
    judge_model=None,          # auto-determined from API key
    judge_sample_rate=0.1,
)
monitor.record_task(task_result)
monitor.save_to_file("evaluation")  # JSON + HTML
```

> Use `PerformanceMonitor` for new projects. Use `HybridPerformanceMonitor` only when integrating DeepEval/Ragas.

### Harness Config in Decorator

```python
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    InstructionConfig, LoopDetectionConfig, SLAConfig, ExplainabilityConfig,
)

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### EvalMetadata — 함수 내부에서 메타데이터 주입

```python
from agent_evaluator import agent_eval
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = f"응답: {question}"
    return response, EvalMetadata(
        extra={"ttft_ms": 120.5},
        tokens_used={"input": 50, "output": 100, "total": 150},
    )
```

### ConversationSession

```python
from agent_evaluator import evaluation_session

with evaluation_session("results/eval.json") as monitor:
    task = create_taskresult(task_id="t1", question="...", response="...", execution_time=1.2)
    monitor.record_task(task)
```

### LLMJudge

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.1)
result = judge.judge("t1", question="...", response="...", context="...")
# result["scores"]["overall"] · ["faithfulness"] · ["criteria_overall"]

# LLMJudge 결과 접근 (monitor에서)
summary = monitor.llm_judge.get_summary()
# → {"avg_scores": {"overall": float, "criteria_scores": {...}}, "sample_count": int}
```

### create_taskresult helper

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001", question="...", response="...",
    ground_truth="...", execution_time=1.23, task_type="qa",
)
```

### HarnessEvaluationGate

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()   # 인수 없음
# result: {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}
```

---

## SDK 유효 파라미터 레퍼런스

### PerformanceMonitor 유효 파라미터

```
output_dir, pricing, model_name, session_label
enable_transparency, enable_hallucination_detection, enable_security_metrics
security_config, enabled_security_trackers
enable_llm_judge, judge_model, judge_sample_rate, judge_criteria
judge_budget_per_day, judge_budget_storage_path
judge_max_context_chars, judge_escalation_model, judge_escalation_threshold, judge_seed
use_korean_tokenizer, use_semantic_hallucination, semantic_weight
enable_anomaly_detection, anomaly_baseline_window, anomaly_detection_window
auto_save, auto_save_interval, auto_save_filename
enable_otel_child_spans, ttft_variability_config, cost_predictability_config
```

### @agent_eval 유효 파라미터

```
task_type, question_arg, ground_truth_arg, task_id_prefix, context_arg
expected_tools_arg, expected_tools, framework, model_name
score_fn, completion_fn, task_id_fn, sample_rate
on_record, on_error, timeout, enabled
alert_rules, flush_every, preset
retry (RetryConfig), llm_judge (LLMJudgeConfig), security (SecurityConfig)
custom_parser, enable_hallucination_detection, rag_mode
enable_anomaly_detection, ttft_seconds, alert_error_mode
instructions, loop_detection, goal_alignment, reproducibility, fault_tolerance, plan_tracking
sla, threat_severity, efficiency, state_consistency, deadlock, observability
consensus, scope, context_retention, explainability, subtask_tracking, propagation
agent_role, graceful_degradation, compliance, resource_budget, conflict_resolution
tool_parameter_safety, knowledge_retention, retry_consistency, error_diagnosis, idempotency
threat_response, context_window, latency_attribution
```

---

## SDK 고정 사실 (검증 기준)

- Native Tracker: **25개** | Harness Config: **33개** | Gate: **7개** (A–G)
- 버전: **v0.9.4** (Beta) | Python: **3.8+**
- 테스트: **53개** 파일, **2,400+** 테스트 함수
- 대시보드: **103개** API 라우트 (FastAPI)
- `from agent_evaluator import agent_eval` — 올바른 import 경로  
  `from agent_evaluator.decorators import agent_eval` — 내부 모듈 (직접 import 비권장)
- Gate별 Tracker 수: A=3, B=2, C=2, D=2, E=5, F=2, G=0 (합계 16 + 운영지원 9 = 25)
- HallucinationDetector 귀속: 개념=Gate C(신뢰성) | SDK 집계=Gate C(_rel_vals) + Gate G(_obs_vals)
- AccuracyEvaluator 귀속: Gate A 직접 기여 (_a_vals, 0-100→0-1 정규화)
- **PlanConfig 기본값**: `max_steps=15`, `min_steps=2` (decorators.py 308-309)
- **PlanConfig 지원 JSON 형식**: `{"steps": [...]}` 또는 `{"plan": [...]}` (plan 키가 직접 리스트)  
  ❌ `{"plan": {"steps": [...]}}` 중첩 dict 구조는 파싱 불가
- **Gate G 집계 조건**: `_obs_vals` 빈 배열이면 Gate G `score=None` (집계 제외, fail 아님)
- **report.to_dict()["extra_metrics"]**: `harness_groups`만 포함. `llm_judge` 키 없음  
  LLMJudge 결과 접근: `monitor.llm_judge.get_summary()` → `avg_scores` → `criteria_scores`
- **HarnessEvaluationGate 위치**: `agent_evaluator/quick_eval.py`  
  `gate.evaluate()` 인수 없음. 반환: `{passed, groups, violations, summary}`
- **SLAConfig 이중 기여**: Gate D Config이지만 breach_rate는 Gate C `_rel_vals`에 기여  
  Gate D score는 `LatencyTracker` 실측 P95 > 0 이어야 산출됨 (`_perf_vals` 필요)
- **TTFTVariabilityConfig·CostPredictabilityConfig**: `@agent_eval` 파라미터가 아닌  
  `PerformanceMonitor(ttft_variability_config=..., cost_predictability_config=...)` 수준 설정

---

## Gate A Tracker 귀속 (자주 틀리는 항목)

| Tracker | 귀속 | 비고 |
|---------|------|------|
| `TaskCompletionTracker` | Gate A + C | 직접 기여 |
| `AccuracyEvaluator` | **Gate A** | direct (`_a_vals`) |
| `ResponseQualityEvaluator` | Gate A 연관 | quality_metrics 별도 집계, Gate A **점수 미포함** |
| `HallucinationDetector` | **Gate C + G** | Gate A **아님** |

---

## Coding Conventions

- **Formatter:** ruff, line-length=100
- **Python target:** 3.8+ (f-string, dataclass, typing)
- **Type hints:** required for all public functions; comment required when using `Any`
- **Docstrings:** include Args / Returns / Example sections
- **Error handling:** optional dependencies via `try/except ImportError`
- **Zero-division:** guard required in all ratio calculations
- **NaN handling:** `pd.isna()` check before pandas statistical calculations
- **API keys:** always `os.getenv()`, never hardcode
- **`enable_*` flags:** expensive operations (hallucination, security) default to `False`

---

## Architecture Principles

1. **Layer independence** — Layer 1/2 must operate without external dependencies
2. **Harness independence** — 33 Configs defined in `decorators.py`, aggregated in `monitor.py`
3. **Tracker isolation** — each tracker must be independently testable
4. **Minimal side effects** — no `sys.path`, `os.chdir()`, or global state modification
5. **Security metric isolation** — security trackers are opt-in due to performance impact
6. **Serve separation** — `serve/` is optional FastAPI; core logic must not depend on it

---

## Known Dependency Constraints

| Item | Status | Note |
|------|--------|------|
| `ragas>=0.4.0` | ✅ | EvaluationDataset, SingleTurnSample API supported |
| `[crewai,autogen]` pydantic conflict | 🟡 | Silently downgrades to pydantic 2.11.x |
| `arize-phoenix>=15.4.0` | ✅ | pydantic-ai 호환성 해결됨 (이전 `<14.7.0` 핀 해제) |
| `AnswerRelevancy` embeddings | 🟡 | Auto-configured only with OpenAI key |

---

## Testing

**53 files, 2,400+ test functions** in `tests/`.

```bash
pytest  # configured in pyproject.toml (testpaths, cov)
```

Note: `agent_evaluator/utils/transparency_manager.py` contains `TestTransparencyManager` — a **production class**, not a test file.

---

## Accuracy Evaluation (AccuracyEvaluator)

| Metric | Weight | Method |
|--------|--------|--------|
| Token Overlap | 40% | F1 token matching |
| Jaccard Similarity | 30% | Set intersection/union |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | Levenshtein |

- `code_generation`/`coding`: 1.0 on successful AST parse
- `tool_use`: 0.6 if `tool_calls` is empty
