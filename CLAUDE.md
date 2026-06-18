# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 0.9.5 (Beta) | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

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
agent-eval --version                                      # version info
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
  MultimodalMetricsTracker

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
├── exceptions.py          # AgentEvaluatorError hierarchy
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
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas integration)
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

| Tracker | Gate | 기여 방식 | 조건 |
|---------|------|-----------|------|
| `TaskCompletionTracker` | A, C | `_a_vals[0]` (TCR 컴포넌트), `_rel_vals` | always |
| `AccuracyEvaluator` | **A** | `_a_vals[0]` 블렌딩 (`0.6×TCR + 0.4×Accuracy`) | `_evaluations` count > 0 |
| `ResponseQualityEvaluator` | **A** | `_a_vals` 추가 (relevance+completeness 평균 / 5, 0→1 정규화) | quality dims 측정 시 |
| `LatencyTracker` | D | `_perf_vals` | always |
| `TokenEconomyTracker` | — | (gate score 미기여) | 토큰 비용 추적·보고 전용 |
| `HallucinationDetector` | **C + G** | `_rel_vals`, `_obs_vals` | LLM Judge faithfulness 없을 때 폴백 (`1 − rate`) |
| `LLMJudge` (faithfulness) | **C** | `_rel_vals` | per-task faithfulness 기록 시 우선 적용 (`score / 5` 정규화); HallucinationDetector 대체 |
| `RetryCorrectionTracker` | — | (gate score 미기여) | 재시도 횟수·패턴 추적 전용 |
| `ToolCallAnalyzer` | G | `_obs_vals` — `success_rate / 100` (0→1 정규화) | tool_calls 기록 시 |
| `WorkflowExecutionTracker` | — | (gate score 미기여) | chain_steps 추적·분석 전용 |
| Security Trackers (5) | E | `_all_e_scores` | `enable_security_metrics=True` |
| `AgentCoordinationTracker` | F | `_f_vals` — `calculate_coordination_score().overall_score / 10` (0→1 정규화) | agent_interactions 기록 시 |
| `ToolSelectionTracker` | F | `_f_vals` — `avg_f1_score / 100` (0→1 정규화) | expected_tools 지정 시 |

> **Gate A 가중치 구조**: `_a_score = gate_a_tcr_weight × _a_vals[0] + (1 − gate_a_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_a_tcr_weight=0.4` — `PerformanceMonitor(gate_a_tcr_weight=...)` 으로 조정 가능.  
> **Gate B 가중치 구조**: `gate_b_loop_weight > 0.0` 이면 루프 점수에 가중치 부여, `0.0`(기본값)이면 가용 지표 단순 평균.  
> 기본값 `gate_b_loop_weight=0.0` — `PerformanceMonitor(gate_b_loop_weight=...)` 으로 조정 가능.  
> **Gate C 가중치 구조**: `_rel_score = gate_c_tcr_weight × _rel_vals[0] + (1 − gate_c_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_c_tcr_weight=0.4` — `PerformanceMonitor(gate_c_tcr_weight=...)` 으로 조정 가능.  
> Gate B details에 `avg_goal_alignment` / `avg_plan_coherence`가 표시되지만, 이는 Gate A 계산값을 재참조하는 진단용이며 Gate B **점수에는 포함되지 않는다**.  
> **`AgentCoordinationTracker` 스케일**: `calculate_coordination_score().overall_score`는 0–10 스케일 → Gate F에서 `/10`으로 정규화.  
> **`ConsensusConfig.consensus_method`**: `"majority"` = 동의 쌍 비율; `"unanimity"` = 모든 쌍 동의 시만 1.0, 아니면 0.0; `"weighted"` = `agent_weights` 기반 가중 비율.  
> **`eval_conflict_resolution` 충돌 카운팅**: `agent_interactions`가 있으면 interaction 기반으로만 집계, 없으면 response 텍스트 폴백 (이중 카운팅 방지).

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

### EvalMetadata — Injecting Metadata from Inside the Function

```python
from agent_evaluator import agent_eval
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = f"Answer: {question}"
    return response, EvalMetadata(
        extra={"ttft_ms": 120.5},
        tokens_used={"input": 50, "output": 100, "total": 150},
    )
```

### Context Manager

```python
from agent_evaluator import evaluation_session, create_taskresult

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

# Accessing LLMJudge results from monitor
summary = monitor.llm_judge.get_summary()
# → {"avg_scores": {"overall": float, "criteria_scores": {...}}, "sample_count": int}
```

### create_taskresult Helper

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
result = gate.evaluate()   # no arguments
# result: {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}
```

---

## Valid Parameter Reference

### PerformanceMonitor Valid Parameters

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
gate_a_tcr_weight, gate_c_tcr_weight, gate_b_loop_weight
```

### @agent_eval Valid Parameters

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

## SDK Fixed Facts (Authoritative Reference)

- Native Trackers: **25** | Harness Configs: **33** | Gates: **7** (A–G)
- Version: **v0.9.5** (Beta) | Python: **3.8+**
- Tests: **56 files**, **2,795+** test functions
- Dashboard: **103** API routes (FastAPI)
- `from agent_evaluator import agent_eval` — correct import path  
  `from agent_evaluator.decorators import agent_eval` — internal module (direct import discouraged)
- Tracker count per Gate: A=3, B=0, C=2, D=1, E=5, F=2, G=1 (14 gate-contributing + 11 operational = 25)
- HallucinationDetector attribution: conceptually Gate C (Reliability) | SDK score contribution: Gate C (`_rel_vals`) + Gate G (`_obs_vals`)
- AccuracyEvaluator attribution: Gate A `_a_vals[0]` 블렌딩 (`0.6×TCR + 0.4×Accuracy`) — 별도 항목 추가가 아닌 TCR 컴포넌트에 혼합
- **PlanConfig defaults**: `max_steps=15`, `min_steps=2` (decorators.py lines 427-428)
- **PlanConfig supported JSON formats**: `{"steps": [...]}` or `{"plan": [...]}` (plan key must be a direct list)  
  ❌ `{"plan": {"steps": [...]}}` nested dict structure cannot be parsed
- **Gate G aggregation**: if `_obs_vals` is empty, Gate G `score=None` (excluded from aggregation, not a fail)
- **`report.to_dict()["extra_metrics"]`**: contains `harness_groups` only — no `llm_judge` key  
  LLMJudge results: `monitor.llm_judge.get_summary()` → `avg_scores` → `criteria_scores`
- **HarnessEvaluationGate location**: `agent_evaluator/quick_eval.py`  
  `gate.evaluate()` takes no arguments. Returns: `{passed, groups, violations, summary}`
- **SLAConfig dual contribution**: Gate D Config, but breach_rate also contributes to Gate C `_rel_vals`  
  Gate D score requires `LatencyTracker` measured P95 > 0 (`_perf_vals` must be populated)
- **TTFTVariabilityConfig · CostPredictabilityConfig**: set at `PerformanceMonitor` level, not `@agent_eval` parameters  
  `PerformanceMonitor(ttft_variability_config=..., cost_predictability_config=...)`

---

## Gate A Tracker Attribution (Common Mistakes)

| Tracker | Attribution | Notes |
|---------|-------------|-------|
| `TaskCompletionTracker` | Gate A + C | `_a_vals[0]` TCR 컴포넌트 직접 기여 |
| `AccuracyEvaluator` | **Gate A** | `_a_vals[0]` 블렌딩 — `0.6×TCR + 0.4×Accuracy` (별도 항목이 아님) |
| `ResponseQualityEvaluator` | **Gate A** | relevance + completeness 평균 / 5 → `_a_vals` 추가 항목 |
| `HallucinationDetector` | **Gate C + G** | **not** Gate A |

**GoalAlignmentConfig 주의사항**: 기본값 `ignore_no_tool_tasks=True` — 도구 호출이 없는 태스크는 goal_alignment 평가에서 제외된다. QA·대화형 에이전트처럼 tool을 호출하지 않는 경우 `avg_goal_a = None`이 되어 Gate A 점수에 전혀 반영되지 않는다. 비도구 에이전트에 GoalAlignmentConfig를 사용하려면 `ignore_no_tool_tasks=False`로 설정해야 한다.

**AccuracyEvaluator `task_type` 매핑**: `"coding"` → `"code_generation"`으로 자동 정규화되어 AST 비교 평가가 적용된다. 두 값 모두 `_code_accuracy`로 라우팅된다.

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
| `arize-phoenix>=15.4.0` | ✅ | pydantic-ai compatibility resolved (previous `<14.7.0` pin removed) |
| `AnswerRelevancy` embeddings | 🟡 | Auto-configured only with OpenAI key |

---

## Testing

**56 files, 2,795+ test functions** in `tests/`.

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
