# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a **Harness Engineering**-based AI agent deployment readiness evaluation SDK.
It goes beyond simple accuracy measurement to comprehensively determine **whether an agent is ready for production deployment** through **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement: Instruction compliance rate · goal alignment · plan consistency · context retention
- **Gate B** — Behavioral Integrity: Loop detection · scope deviation · tool safety · state consistency
- **Gate C** — Reliability: Reproducibility · error recovery rate · quality floor · idempotency
- **Gate D** — Performance Contract: SLA · token efficiency · TTFT variability · cost predictability
- **Gate E** — Security Boundary: Threat severity · compliance · threat response
- **Gate F** — Multi-Agent Coordination: Consensus rate · information propagation · role compliance · conflict resolution
- **Gate G** — Observability: Reasoning explanation · state tracking · error diagnosis · latency analysis

Measures **25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 0.9.1 (Beta)
- **Python:** 3.8+
- **License:** MIT
- **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Development environment setup (dev = tests · linter · build tools)
pip install -e ".[dev]"

# ── Running examples ──────────────────────────────────────────────────────────
# Examples 01–18, 20–26: "[sdk]" extra is sufficient (dashboard · OTEL included)
# Example 19 (Phoenix Hybrid): "[examples]" required (deepeval · ragas · langchain included)
pip install -e ".[sdk]"               # dashboard + OTEL + LLMJudge + PDF
pip install -e ".[examples]"          # all examples runnable (sdk + eval)

# ── Framework extensions (install only when your agent code requires) ─────────
pip install -e ".[eval]"              # DeepEval / Ragas external evaluation libraries
pip install -e ".[langchain]"         # LangChain / LangGraph integration
pip install -e ".[dspy]"              # DSPy integration (dspy-ai)
pip install -e ".[pydanticai]"        # PydanticAI integration (pydantic-ai)
pip install -e ".[crewai]"            # CrewAI standalone (heavy — 100+ transitive deps)
pip install -e ".[autogen]"           # AutoGen standalone (heavy, isolated)
pip install -e ".[full]"              # All (⚠️ includes crewai/autogen, 10+ min)

# ── Optional feature extensions (install only when the feature is needed) ─────
pip install -e ".[korean]"            # kiwipiepy — Korean morpheme analysis precise tokenization
pip install -e ".[semantic]"          # sentence-transformers — semantic-based hallucination detection
pip install -e ".[export]"            # pyarrow + openpyxl — dashboard Parquet/Excel export
pip install -e ".[wandb]"             # wandb — PerformanceMonitor.export_to_wandb()
pip install -e ".[mlflow]"            # mlflow — PerformanceMonitor.export_to_mlflow()

# ── CLI (available immediately after pip install) ─────────────────────────────
agent-eval init          # Interactive API key setup wizard
agent-eval check         # Print current configuration status
agent-eval dashboard     # Run FastAPI dashboard (default port 8765)
agent-eval gate result.json --tcr 85 --accuracy 70   # CI/CD quality gating
agent-eval dataset build results/ --min-score 0.8    # Auto-extract golden dataset
agent-eval monitor                                   # Start Arize Phoenix + OTLP span receiver
agent-eval monitor --port 6006                       # Specify Phoenix port (default: 6006)
agent-eval monitor --check                           # Check OTEL packages and port occupancy
agent-eval trend results/                            # Analyze TCR · accuracy trends (last 10 result files)
agent-eval trend results/ --window 5                 # Analyze last 5 files only
agent-eval trend results/ --fail-on-regression       # Exit 1 on regression detection (CI/CD failure)
agent-eval trend results/ --output-json trend.json   # Save analysis result as JSON
agent-eval --version     # Print version

# Run tests
pytest

# Code quality
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/

# Build / PyPI release
pip install hatchling build twine
python -m build
twine upload --repository testpypi dist/*   # Test release
twine upload dist/*                          # Production release
```

---

## Architecture

### 58 Metrics = 25 Native Trackers + 33 Harness Config Dataclasses

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
  LLMJudge (native)         → faithfulness + judge_criteria (G-Eval/Ragas replacement)
    • 5 dimensions: completeness · relevance · factual_consistency · toxicity · bias
    • RAG: faithfulness (auto-added when rag_mode=True + context)
    • G-Eval: criteria_scores / criteria_overall (auto-added when judge_criteria=[...])

Harness Engineering — 33 Config Dataclasses, 7 Gate Groups (A–G)
  → Passed as decorator parameters; PerformanceMonitor aggregates automatically
  → Gate A–G pass/warn/fail visualized per group in the dashboard Harness Gate tab
  → Gate A–G results stored under `extra_metrics.harness_groups` key in JSON result files (internal naming)
```

### Harness Gate A–G (7 Gates, 33 Configs)

```
Gate A — Goal Achievement (6)
  InstructionConfig         → Instruction compliance rate · deviation detection
  GoalAlignmentConfig       → Goal alignment score · partial achievement credit
  PlanConfig                → Plan consistency · step completion rate
  SubtaskConfig             → Subtask decomposition · completion rate
  ContextRetentionConfig    → Conversational context retention rate
  KnowledgeRetentionConfig  → Knowledge retention · utilization score

Gate B — Behavioral Integrity (6)
  LoopDetectionConfig       → Repetitive loop detection · loop threshold
  ScopeConfig               → Scope deviation detection · allowed_actions
  ToolParameterSafetyConfig → Tool parameter safety · prohibited patterns
  ContextWindowConfig       → Context window utilization efficiency
  StateConsistencyConfig    → Pre/post execution state consistency · unchanged_keys
  DeadlockConfig            → Deadlock detection · circular delegation · starvation

Gate C — Reliability (5)
  ReproducibilityConfig     → Consistency across repeated runs with same input
  FaultToleranceConfig      → Recovery rate after errors · normal completion ratio
  GracefulDegradationConfig → Quality floor · partial_result_markers
  RetryConsistencyConfig    → Response consistency across retries
  IdempotencyConfig         → Idempotency verification · duplicate execution safety

Gate D — Performance Contract (5)
  SLAConfig                 → SLA response time threshold · P95/P99 violation rate
  EfficiencyConfig          → Token efficiency · completion rate vs. tool calls
  ResourceBudgetConfig      → Token budget · cost ceiling
  TTFTVariabilityConfig     → TTFT standard deviation · P95/P50 ratio (auto-aggregated at monitor level)
  CostPredictabilityConfig  → Token CV per task_type · cost predictability (auto-aggregated at monitor level)

Gate E — Security Boundary (3)
  ThreatSeverityConfig      → Threat severity classification · threshold blocking
  ComplianceConfig          → Compliance patterns · prohibited keywords
  ThreatResponseConfig      → Response behavior verification after threat detection

Gate F — Multi-Agent Coordination (4)
  ConsensusConfig           → Inter-agent consensus rate · dispute detection
  PropagationConfig         → Information propagation accuracy · distortion detection
  AgentRoleConfig           → Role compliance rate · role violation detection
  ConflictResolutionConfig  → Conflict resolution patterns · resolution time

Gate G — Observability (4)
  ExplainabilityConfig      → Reasoning process explainability
  ObservabilityConfig       → Internal state exposure · traceability
  ErrorDiagnosisConfig      → Error root cause diagnosis accuracy
  LatencyAttributionConfig  → Latency root cause analysis · per-segment contribution
```

### Module Layout

```
agent_evaluator/
├── decorators.py            # agent_eval · batch_eval · conversation_eval · EvalDecorator · EvalMetadata
│                            # Includes 33 Harness Config dataclass definitions
│                            # RetryConfig · LLMJudgeConfig · SecurityConfig (3 decorator utilities)
├── quick_eval.py            # QuickEval — one-stop evaluation facade (v0.7.1+)
├── core/
│   ├── agent_evaluator.py   # re-export facade — trackers/ split complete
│   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   ├── monitor_context.py   # Context managers
│   ├── otel/                # OpenTelemetry integration (included in base install)
│   │   ├── provider.py      # OTELProvider — TracerProvider setup
│   │   └── metrics.py       # OTELMetrics — metric exporter (opt-in)
│   └── trackers/            # Tracker sub-package
│       ├── base.py          # BaseTracker, TaskResult, EvaluationReport, TaskType
│       ├── layer1.py        # Layer 1: TaskCompletion·Accuracy·Hallucination·Quality·Latency·TokenEconomy
│       ├── layer2.py        # Layer 2: ToolCall·Retry·ToolSelection·Coordination·Workflow
│       ├── security.py      # Layer 2 Security: InputSanitization·OutputLeakage·ToolAuth·Escalation·ChainAttack
│       ├── conversation.py  # ConversationSession·ConversationMetrics·ConversationTurn
│       ├── feedback.py      # ImplicitFeedbackTracker
│       └── monitor.py       # PerformanceMonitor (central orchestrator + Harness aggregation)
├── anomaly/
│   └── detector.py          # AnomalyDetector — anomaly detection (save_to_file integration)
├── streaming/
│   ├── evaluator.py         # StreamingEvaluator·SlidingWindow
│   └── middleware.py        # Real-time streaming middleware
├── alerts/
│   ├── engine.py            # AlertEngine·AlertRule
│   └── handlers.py          # Alert handlers
├── cost/
│   └── policy.py            # CostTracker·AdaptivePolicy·SamplingStage
├── integrations/
│   ├── llm_judge.py         # LLMJudge — LLM-as-Judge evaluation engine (included in base install)
│   ├── metric_adapters.py   # DeepEval/Ragas adapters
│   └── framework_integrations.py
├── helpers/
│   └── taskresult_helpers.py  # create_taskresult(), token extraction utils
├── reporting/
│   └── comprehensive_report.py  # Harness Gate A–G centered HTML/text report generation
│                                 # generate_html_from_result_file(rf) — for export router
├── datasets/
│   ├── builder.py           # GoldenSetBuilder — auto golden dataset expansion
│   ├── korean_rag_dataset_generator.py
│   └── korean_rag_evaluator.py
├── serve/                   # FastAPI dashboard server (included in base install)
│   ├── server.py            # FastAPI app entry point
│   ├── loader.py            # Evaluation result loader (parse_file · load_results)
│   ├── watcher.py           # File change watcher (--watch)
│   ├── templates/
│   │   ├── dashboard2.html.j2   # Harness Gate dashboard (Alpine.js + Plotly, 3-tier Nav)
│   │   └── slides.html.j2       # Harness Gate slides (Reveal.js, 14 slides Gate A–G)
│   └── routers/             # 12 API routers
├── cli/
│   ├── main.py              # agent-eval CLI entry point
│   ├── gate.py              # agent-eval gate — CI/CD quality gating
│   ├── trend.py             # agent-eval trend — sequential result trend analysis
│   └── dataset.py           # dataset subcommand (build)
├── utils/
│   ├── dashboard_integration.py  # Dashboard storage path helper
│   ├── data_registry.py     # Evaluation result data registry
│   ├── path_helpers.py      # Result directory path helpers
│   └── transparency_manager.py  # TestTransparencyManager production class
├── exceptions.py            # SDK exception hierarchy
├── config.py                # Environment variable config loader (load_env, get_settings)
└── __init__.py              # Public API surface

Evaluator_Examples/          # Book chapter-based examples (26 files — ch01~ch26)
├── ch01_first_eval.py        # Ch01 — Layer 1 basics (accuracy · hallucination · TCR)
├── ch02_quickstart.py        # Ch02 — QuickEval 5-minute first evaluation
├── ch03_harness_basics.py    # Ch03 — Harness Gate A–G 7-gate overview
├── ch04_group_a.py           # Ch04 — Gate A: Goal Achievement (6 Configs)
├── ch05_group_b.py           # Ch05 — Gate B: Behavioral Integrity (6 Configs)
├── ch06_group_c.py           # Ch06 — Gate C: Reliability (5 Configs)
├── ch07_group_d.py           # Ch07 — Gate D: Performance Contract (5 Configs)
├── ch08_group_e.py           # Ch08 — Gate E: Security Boundary (3 Configs)
├── ch09_group_f.py           # Ch09 — Gate F: Multi-Agent Coordination (4 Configs)
├── ch10_group_g.py           # Ch10 — Gate G: Observability + AnomalyDetector · CostTracker
├── ch11_eval_data.py         # Ch11 — Evaluation data design (GoldenSetBuilder · evaluation_session)
├── ch12_decorators.py        # Ch12 — Decorators mastery (@agent_eval · @batch_eval · QuickEval · LLMJudge)
├── ch13_frameworks.py        # Ch13 — Framework integration (LangChain · LangGraph · CrewAI · AutoGen)
├── ch14_thresholds.py        # Ch14 — Threshold configuration and quality standards
├── ch15_dashboard.py         # Ch15 — Dashboard visualization (QuickEval · AnomalyDetector · CostTracker data generation)
├── ch16_alerts.py            # Ch16 — Alert system (StreamingEvaluator · AlertEngine · SimpleTaskAlertRule)
├── ch17_weekly_review.py     # Ch17 — Weekly/monthly quality review automation
├── ch18_cicd_gate.py         # Ch18 — CI/CD quality gating (Harness minimal verification · exit 0/1)
├── ch19_phoenix.py           # Ch19 — Phoenix OTEL (Tracing · Datasets · Playground · GraphQL + DeepEval · Ragas)
├── ch20_deployment.py        # Ch20 — Production deployment strategy (v1 vs v2 Gate score comparison)
├── ch21_pipeline.py          # Ch21 — Comprehensive production pipeline (dev→CI→ops→improvement 4 stages)
├── ch22_project_analysis.py  # Ch22 — Existing project analysis (topology · LLM enumeration · metric discovery · risk prioritization)
├── ch23_gate_mapping.py      # Ch23 — Gate mapping strategy (failure mode catalog → Config translation + weight design)
├── ch24_quickeval_entry.py   # Ch24 — First migration (invasiveness Level 0/1 patterns + first measurements)
├── ch25_harness_full.py      # Ch25 — Full integration (central monitor + adapters + security scan + Gate F bug discovery)
└── ch26_cicd_weekly.py       # Ch26 — CI/CD completion (golden dataset · trend analysis · weekly review · cost drift discovery)
# Legacy examples (01–10): preserved in Evaluator_Examples/.deprecated/

scripts/
└── phoenix_check.py         # Phoenix integration auto-check — pass/fail judgment via GraphQL reverse lookup

Docs/
├── 01_GETTING_STARTED.md    # Shortest path to install · first evaluation · dashboard
├── 02_METRICS_GUIDE.md      # 58 metrics formulas · output keys · thresholds (Harness Gate A–G centered)
├── 03_INTEGRATION_GUIDE.md  # Framework integration guide
├── 04_DATA_GUIDE.md         # Golden dataset · result file structure
├── 05_QUALITY_GATE.md       # CI/CD quality gating guide
├── 06_OBSERVABILITY.md      # OTEL · Phoenix observability
├── 07_OPERATIONS.md         # Production infrastructure · cost management
└── 08_API_REFERENCE.md      # Full public API documentation
```

---

## Key Classes

### `QuickEval`
One-stop evaluation facade — starts `PerformanceMonitor` + `EvalDecorator` in 1–2 lines.

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
eval.gate(tcr=85, accuracy=70)    # CI/CD gating — sys.exit(1) on failure

# Purpose-specific factories
eval = QuickEval.for_rag("results/")              # hallucination_detection=True
eval = QuickEval.for_security("results/")         # enable_security_metrics=True
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# Auto-save — save_to_file() called automatically every 10 tasks
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)

# Shorthand decorators: qa, tool_use, rag, code, reasoning, planning, data_analysis, creative, multi_agent, secure, streaming
# Batch: @eval.batch(task_type="qa")
# Direct call: @eval(task_type="qa", score_fn=my_fn)
# With retry: @eval.with_retry(task_type="qa", retry=RetryConfig(max=3))
```

### PerformanceMonitor vs HybridPerformanceMonitor Selection Guide

| Item | `PerformanceMonitor` | `HybridPerformanceMonitor` |
|------|---------------------|---------------------------|
| External dependencies | None (Layer 1+2 native + Harness) | DeepEval / Ragas required (`[eval]` extra) |
| LLM Judge | ✅ built-in (`llm_judge=LLMJudgeConfig()`) | ✅ same |
| Faithfulness | ✅ built-in (`rag_mode=True`) | ✅ + Ragas method also available |
| G-Eval | ✅ built-in (`judge_criteria=[...]`) | ✅ + DeepEval method also available |
| Harness Config | ✅ all 33 Configs supported | ✅ same |
| Recommended for | most production environments | when integrating with DeepEval/Ragas ecosystem |

> **Recommendation**: Start with `PerformanceMonitor` for new projects.

### `PerformanceMonitor`
Central orchestrator. Configures all trackers and Harness Config aggregation internally.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # default False (performance impact)
    enable_security_metrics=False,         # default False
    enable_transparency=False,             # True: auto-generates traces/audit_logs
    # LLM Judge (opt-in)
    enable_llm_judge=False,                # True: LLM scoring applied to all tasks
    judge_model=None,                      # None → auto-determined based on API key
    judge_sample_rate=0.1,                 # score only 10% (cost reduction)
    judge_criteria=None,                   # G-Eval custom criteria ["medical_accuracy", ...]
    # Auto-save
    auto_save=False,
    auto_save_interval=10,
    auto_save_filename="auto_save",
)
monitor.record_task(task_result)           # returns PerformanceMonitor — method chaining
report = monitor.generate_report()
monitor.save_to_file("evaluation")        # auto-generates JSON + HTML

# Factory classmethods
monitor_rag = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
monitor_sec = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

### `TaskResult`
`@dataclass(frozen=True)` holding a single task execution result (11 required + 13 optional = 24 fields).

```python
from agent_evaluator import create_taskresult

# Recommended: use create_taskresult() helper (auto-calculates scores)
result = create_taskresult(
    task_id="task_001",
    question="What is the capital of South Korea?",
    response="Seoul.",
    ground_truth="Seoul",
    execution_time=1.23,
    task_type="qa",
)

# Serialization / Deserialization
d = result.to_dict()
result2 = TaskResult.from_dict(d)      # ISO-8601 timestamp auto-conversion
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
# Auto-saves on session end (safe even on exception)

async with async_evaluation_session("output_filename") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

### `LLMJudge` — Safety / Faithfulness / G-Eval
LLM-as-Judge scoring engine. Auto-scores up to 7+ dimensions without ground truth.

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(
    model="claude-haiku-4-5-20251001",  # None → auto-determined based on API key
    sample_rate=0.1,
    judge_criteria=["medical_accuracy", "citation_quality"],  # G-Eval replacement
)

# Default 5-dimension scoring
result = judge.judge("t1", question="...", response="...")
result["scores"]["overall"]        # average of 3 quality dimensions
result["scores"]["safety_score"]   # (10 - toxicity - bias) / 10

# RAG faithfulness (auto-added when context is provided)
result = judge.judge("t2", question="...", response="...", context="retrieved document...")
result["scores"]["faithfulness"]   # 0–5

# G-Eval custom criteria
result["scores"]["criteria_scores"]   # {"medical_accuracy": 4, "citation_quality": 5}
result["scores"]["criteria_overall"]  # average of custom criteria

# Direct use in decorator
from agent_evaluator.decorators import LLMJudgeConfig
@agent_eval(monitor, rag_mode=True, llm_judge=LLMJudgeConfig(criteria=["safety", "evidence_based"]))
def rag_agent(question, context="", ground_truth=""): ...
```

### Harness Config Decorator Usage

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig,     # Gate A
    LoopDetectionConfig, StateConsistencyConfig, DeadlockConfig,  # Gate B
    FaultToleranceConfig, GracefulDegradationConfig,  # Gate C
    SLAConfig, EfficiencyConfig,                # Gate D
    ThreatSeverityConfig, ComplianceConfig,     # Gate E
    ConsensusConfig, AgentRoleConfig,           # Gate F
    ExplainabilityConfig, ObservabilityConfig,  # Gate G
)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### Framework-Specific Decorators
The `agent_eval(framework=...)` parameter auto-extracts metadata from responses of 21 frameworks.

```python
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# Supported frameworks (21): langchain, langgraph, crewai, autogen, dspy, pydanticai,
# anthropic, openai, gemini, llamaindex, haystack, vertexai, ollama, cohere,
# groq, mistral, bedrock, smolagents, semantic_kernel, vllm, huggingface
```

### `ConversationSession` (Multi-turn Conversation Evaluation)
```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn

session = ConversationSession(session_id="conv_001")
session.add_turn(user_input="Hello", agent_response="Hi there!")
metrics: ConversationMetrics = session.compute_metrics()
# metrics.turn_count, .overall_score, .context_retention, .topic_coherence,
# .progressive_depth, .session_completion, .avg_turn_latency

# Integration with monitor (recommended)
with monitor.conversation("session_id") as conv:
    conv.turn(user="Hello", agent="Hi there!", metadata={"latency": 0.3})

# @conversation_eval decorator
@conversation_eval(monitor, max_turns=20)
def chatbot(session_id: str, question: str, ground_truth: str = "") -> str: ...
```

### `SimpleTaskAlertRule`
Lightweight alert rule operating on `TaskResult` without `StreamingEvaluator`.

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

    # QuickEval — one-stop facade
    QuickEval,

    # Hybrid
    HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport,

    # Helpers
    create_taskresult, evaluation_session, async_evaluation_session,
    hybrid_evaluation_session,

    # OTEL
    setup_otel,

    # Multi-turn Conversation Evaluation
    ConversationSession, ConversationMetrics, ConversationTurn,

    # LLM Judge (included in base install)
    LLMJudge,

    # Decorator Config Dataclasses (v0.8.1+)
    RetryConfig, LLMJudgeConfig, SecurityConfig,

    # Harness Config — Gate A: Goal Achievement
    InstructionConfig, GoalAlignmentConfig, PlanConfig, SubtaskConfig,
    ContextRetentionConfig, KnowledgeRetentionConfig,

    # Harness Config — Gate B: Behavioral Integrity
    LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig,
    ContextWindowConfig, StateConsistencyConfig, DeadlockConfig,

    # Harness Config — Gate C: Reliability
    ReproducibilityConfig, FaultToleranceConfig, GracefulDegradationConfig,
    RetryConsistencyConfig, IdempotencyConfig,

    # Harness Config — Gate D: Performance Contract
    SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
    TTFTVariabilityConfig, CostPredictabilityConfig,

    # Harness Config — Gate E: Security Boundary
    ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig,

    # Harness Config — Gate F: Multi-Agent Coordination
    ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig,

    # Harness Config — Gate G: Observability
    ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig, LatencyAttributionConfig,

    # Transparency Subsystem
    TestTransparencyManager, AnnotationType, TestStepStatus,

    # Config Helpers
    load_env, get_settings, init_from_app,

    # Advanced / Custom Tracker Base
    BaseTracker,

    # Security Helper
    infer_privilege_level,

    # Alerts
    SimpleTaskAlertRule, AlertRuleBuilder,

    # Phase 2/3 — Streaming, Feedback, Anomaly, Cost
    ImplicitFeedbackTracker,
    AnomalyDetector, AnomalyEvent,
    CostTracker, AdaptivePolicy, SamplingStage,

    # Individual Trackers (for advanced users)
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
- **Type hints:** required for all public functions; comment required when using `Any`
- **Docstrings:** include Args / Returns / Example sections
- **Error handling:** optional dependencies handled gracefully with `try/except ImportError`
- **Zero-division:** zero-denominator guard required in all ratio calculations
- **NaN handling:** `pd.isna()` check required before pandas statistical calculations
- **API keys:** never hardcode in source. always use `os.getenv()`
- **`enable_*` flags:** expensive operations (hallucination, security) default to `False`

---

## Architecture Principles

1. **Layer independence** — Layer 1/2 must operate without external dependencies. Optional deps only in Layer 3
2. **Harness independence** — 33 Harness Configs defined in a single decorators.py file + aggregated in monitor.py
3. **Tracker isolation** — each tracker must be independently testable
4. **Minimal side effects** — library code must not modify `sys.path`, `os.chdir()`, or global state
5. **Security metric isolation** — security trackers are opt-in due to performance impact
6. **Serve separation** — `agent_evaluator/serve/` is an optional FastAPI server; core evaluation logic must not depend on it

---

## Dependency Constraints (Known)

| Item | Status | Description |
|------|--------|-------------|
| `ragas>=0.4.0` | ✅ Supported | Full support for 0.4.x API (EvaluationDataset, SingleTurnSample). Applied alongside `datasets>=4.0.0,<6.0.0` |
| `[crewai,autogen]`/`[full]` pydantic conflict | 🟡 Allowed | Simultaneous install of crewai(pydantic<2.12) + pyautogen(prefers pydantic>=2.12) silently downgrades to pydantic 2.11.x |
| `pyautogen>=0.3.0` 0.4+ async API | 🟡 Partial | 0.4+ (autogen-agentchat 0.4+) uses async API → wrap with `@agent_eval(framework="autogen")` for async functions |
| `AnswerRelevancy` embeddings | 🟡 Conditional | Auto-configured only when OpenAI API key is present. AnswerRelevancy metric excluded in Anthropic-only environments |

---

## Testing

`tests/` directory contains **53 files, 2,465+ test functions**.

```bash
# pytest.ini_options in pyproject.toml already configured:
# testpaths = ["tests"]
# addopts = "-v --cov=agent_evaluator --cov-report=html"
pytest
```

Coverage status (reference values, varies by environment):
- `base.py`: 92% | `layer1.py`: 84% | `layer2.py`: 95%
- `hybrid_monitor.py`: 61% | `monitor.py`: 41% | `taskresult_helpers.py`: 89% | overall: 33%

Note: `agent_evaluator/utils/transparency_manager.py` is **not** a test file — it contains `TestTransparencyManager`, a production class.

---

## Dependencies

### Base Install (`pip install agent-evaluator`)
Core evaluation engine only. Dashboard · OTEL · PDF installed separately as extras.

- `numpy>=1.20.0,<3.0.0` — numerical computation
- `pandas>=1.3.0,<4.0.0` — metric aggregation
- `python-dotenv>=0.19.0,<2.0.0` — environment variable management
- `openai>=2.0.0,<3.0.0` + `anthropic>=0.20.0,<1.0.0` — LLMJudge engine

### SDK Feature Extras (v0.9.1+, staged installation)
- `[llm]` — openai + anthropic (LLMJudge only)
- `[serve]` — `fastapi>=0.110.0` + `uvicorn[standard]>=0.29.0` + `jinja2>=3.1.0` + `python-multipart>=0.0.9` — web dashboard
- `[otel]` — `opentelemetry-sdk>=1.20.0` + `arize-phoenix>=14.0.0,<14.7.0` — OTEL monitoring (14.7+ installs pydantic-ai metapackage → 170+ unnecessary packages)
- `[pdf]` — `pdfplumber>=0.10.0,<1.0.0` — Korean RAG PDF processing
- `[sdk]` — llm + serve + otel + pdf bundled **(recommended for production)**

### Optional Extras
- `[examples]` — sdk + eval bundle. All examples (ch01–ch26) runnable
- `[eval]` — `deepeval>=3.0.0,<4.0.0` + `ragas>=0.4.0,<2.0.0` + `datasets>=4.0.0,<6.0.0` + `langchain>=1.0.0` + `langchain-openai>=1.0.0,<2.0.0`
- `[langchain]` — `langchain>=1.0.0,<3.0.0` + `langchain-core/openai/anthropic>=1.0.0` + `langgraph>=1.0.0`
- `[dspy]` — `dspy-ai>=2.0.0`
- `[pydanticai]` — `pydantic-ai>=1.0.0,<2.0.0`
- `[crewai]` — `crewai>=1.0.0,<2.0.0` — heavy (100+ transitive deps), isolated
- `[autogen]` — `pyautogen>=0.3.0,<1.0.0` + `autogen-agentchat/core>=0.4.0` — heavy, isolated
- `[korean]` — `kiwipiepy>=0.17.0` — `AccuracyEvaluator(use_korean_tokenizer=True)` Korean morpheme analysis
- `[semantic]` — `sentence-transformers>=2.7.0,<5.0.0` — `HallucinationDetector(use_semantic_similarity=True)` semantic hallucination detection
- `[export]` — `pyarrow>=10.0.0` + `openpyxl>=3.1.0` — dashboard Parquet/Excel export (HTTP 409 if not installed)
- `[wandb]` — `wandb>=0.17.0` — `PerformanceMonitor.export_to_wandb()` W&B experiment tracking
- `[mlflow]` — `mlflow>=2.0.0` — `PerformanceMonitor.export_to_mlflow()` MLflow experiment tracking
- `[full]` — sdk+eval+langchain+dspy+pydanticai+crewai+autogen all (⚠️ 10+ min)
- `[dev]` — `pytest` + `pytest-cov` + `pytest-asyncio` + `ruff` + `mypy` + `build` + `twine` + `pre-commit`

> ⚠️ **Framework extras note**: SDK adapters work via duck typing/try-except, so installation is not required. These extras are only needed when **your agent code** imports the framework directly.

---

## Accuracy Evaluation Strategy

Accuracy calculation method used by `AccuracyEvaluator`:

| Metric | Weight | Method |
|--------|--------|--------|
| Token Overlap | 40% | F1-based token matching (precision-recall harmonic mean) |
| Jaccard Similarity | 30% | Set intersection/union |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | Levenshtein distance-based (character order preserved) |

Code accuracy: AST comparison → normalized comparison fallback.

completion_score task_type recognition (v0.8.0+):
- `code_generation`/`coding`: 1.0 on successful AST parse, length-based on failure
- `tool_use`: 0.6 if `tool_calls` is empty (partial completion without tool use)

---

## Security Metrics Patterns

Patterns detected by `InputSanitizationTracker`:
- SQL Injection, Command Injection, Path Traversal, XSS, Prompt Injection

✅ `OutputLeakageDetector` file path patterns — false-positive improvement via exclusion of system paths (`/usr/`, `/bin/`, `/lib/`, etc.) complete (v0.6.3).

---

## 📝 Changelog

### v0.9.1 (2026-04-27) — Dependency restructure · pip resolver optimization

- 🔧 `pyproject.toml` dependency restructure: reduced base install to 5 core packages, split fastapi · otel · pdfplumber into `[serve]` · `[otel]` · `[pdf]` · `[sdk]` extras
- 🔧 `arize-phoenix>=14.0.0,<14.7.0` upper bound fixed — prevents pydantic-ai metapackage (170+ packages) auto-install from 14.7.0+, `[sdk]` package count 170→90
- 🔧 `openai>=2.0.0,<3.0.0`, `langchain-openai>=1.0.0,<2.0.0`, `langchain-anthropic>=1.0.0,<2.0.0` range narrowed — minimizes pip resolver search space (openai candidates 277→37)
- 📝 Docs example file references updated (21→26, ch01/ch02 filename corrections)

### v0.8.5 (2026-04-23) — SDK bug fixes

- 🐛 Fixed `TypeError` silent suppression bug when `tokens_used` is dict type in `eval_efficiency()` (`taskresult_helpers.py`)
- 🐛 `ch10_group_g.py` — fixed `latency_attributed_agent` to inject latency data via `EvalMetadata(extra={...})` instead of response text (Gate G warn→pass)
- 🐛 `ch07_group_d.py` — fixed `EfficiencyConfig(cost_unit="tokens", target_cost_per_completion=200)`, isolated `CostPredictabilityConfig` CV by separating `task_type` per agent (Gate D 0.640→0.876)
- 📝 Updated example file count · test file count in docs (19→21 examples, 51→53 test files)
- 📝 Example files 21→26 — added ch22–ch26 (project analysis · gate mapping · first migration · full integration · CI/CD)

### v0.8.4 (2026-04-21) — Example files fully reorganized into chapter-based structure

- 📝 Example files fully reorganized from 11 (layer-based) → 17 (chapter-based): unified `chXX_topic.py` naming
- 🔧 Synchronized Phoenix `service_name` and `save_to_file` output names to chapter numbers
- ✨ `ch05_group_b.py` — added WorkflowExecutionTracker section (3 pipeline scenarios)
- ✨ `ch07_group_d.py` — added LatencyTracker(p50/p95/p99) · TokenEconomyTracker sections
- ✨ `ch10_group_g.py` — added AnomalyDetector(5 anomaly types) · CostTracker + AdaptivePolicy sections
- ✨ `ch02_first_eval.py` — added code/RAG accuracy · ResponseQualityEvaluator sections
- 🐛 Fixed missing `create_taskresult` import in `ch05_group_b.py`
- 📝 Preserved legacy 11 examples in `.deprecated/`

### v0.8.3 (2026-04-21) — LLMJudge stability · Gate improvements · Security tracker expansion

- Auto-disable LLMJudge on consecutive errors (3 consecutive failures → `_disabled_reason` set, restored via `reset_errors()`)
- Store `None` instead of `0` when `faithfulness` is missing — prevents score pollution; `None` excluded from statistical aggregation
- Introduced `AGENT_EVALUATOR_JUDGE_PROVIDER` env var — `auto` / `openai` / `anthropic` selection
- Added `GoalAlignmentConfig.llm_blend_weight` · `PlanConfig.llm_blend_weight` (0.0–1.0, default 0.5)
- Added `LLMJudge.ajudge()` async method — non-blocking call based on `run_in_executor`
- Fixed `LLMJudgeConfig.sample_rate` decorator propagation bug (all 5 call sites connected)
- `agent-eval gate --min-gate-score SCORE --group-weights A:2.0,E:3.0` — weighted composite Gate A–G score judgment
- `agent-eval trend` cost trend analysis — `total_cost` field + `$` unit output, `--fail-on-regression` integration
- `OutputLeakageDetector(excluded_unix_paths=[...])` — dynamic negative lookahead for customizable system path exclusion
- Added `sample_rate` parameter to `InputSanitizationTracker` · `OutputLeakageDetector` — performance optimization for high-traffic environments
- Added `deadlock_by_type` classification to Harness Gate B report (`circular` / `starvation` / `depth_exceeded` / `livelock`)
- Added `insufficient_data_warnings` to Gate D aggregation — warning when TTFT · cost · SLA samples are insufficient
- `LLMJudge(escalation_model=..., escalation_threshold=2.5)` — auto re-score with higher model when primary score is below threshold

### v0.8.2 (2026-04-17) — Harness Config 33 unified format · Dashboard UI improvements

- Unified icon · formula · threshold badge format for all 33 Harness Config cards; added `08_harness_eval.py` example
- Dashboard Nav reorganized into 3-tier hierarchy; added Gate correlation heatmap (7×7 Pearson) · failure cascade tracking
- HTML report fully reorganized around Gate A–G; added 16 Gate columns to CSV export
- Group classification fix: StateConsistencyConfig · DeadlockConfig moved Gate F→B
- Added 2 test files (52 files, 2,465+)

### v0.8.1 (2026-04-14) — Decorator parameter restructuring

- Introduced 3 structs: `RetryConfig` · `LLMJudgeConfig` · `SecurityConfig`; removed individual parameters
- Unified naming: `enable_hallucination` → `enable_hallucination_detection`
- Added 548 tests; restructured 72→49 files

### v0.8.0 (2026-04-13) — Accuracy metrics overhaul

- Replaced Token Overlap with F1 (harmonic mean); unified Char Similarity to Levenshtein
- task_type-aware completion_score: code_generation AST parsing, tool_use returns 0.6 if unused

### v0.7.9 (2026-04-13) — RunTrendAnalyzer · arize-phoenix compatibility fix

- `RunTrendAnalyzer` + `agent-eval trend` — trend analysis · `--fail-on-regression` CI/CD integration
- Fixed arize-phoenix version constraint conflict

### v0.7.8 (2026-04-12) — SDK built-in by default

- `pip install agent-evaluator` alone enables LLMJudge · dashboard · OTEL

### v0.7.7 (2026-04-11) — Decorator bug fixes · thread safety

- Fixed `agent_eval` preset parameter not applied bug; added `threading.Lock` to 5 Layer 2 trackers

### v0.7.6 (2026-04-10) — LLMJudge G-Eval/Ragas replacement

- `judge_criteria` G-Eval custom scoring; auto-adds `faithfulness` when `rag_mode=True`

### v0.7.0–v0.7.5 (2026-04-01~09) — OTEL/Phoenix · 3 decorators · QuickEval

- `agent-eval monitor` CLI · Arize Phoenix real-time monitoring
- Completed 3 decorators (`agent_eval` · `batch_eval` · `conversation_eval`) · `QuickEval` facade
- 21 framework adapters · critical security tracker bug fixes (CRITICAL)

### v0.6.x (2026-03-21~04-01) — SDK stabilization

- LangChain/LangGraph/CrewAI/AutoGen · FastAPI dashboard · LLMJudge · ConversationSession

### v0.2.x–v0.5.x — Initial implementation

- 25 Layer 1/2/3 trackers · initial `evaluation_session` implementation
