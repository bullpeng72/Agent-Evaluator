# Metrics Reference — a Harness Engineering View

A reference for the formulas, output keys, and thresholds of Agent Evaluator's **58 metrics**.

**v1.0.0 | 25 Native Trackers + 33 Harness Config = 58 metrics | 7 Gates (A–G) decide deployment readiness**

> For individual tracker API signatures, see [08_API_REFERENCE.md](08_API_REFERENCE.md).
> For applying the decorator approach, see [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md).


---

## What is Harness Engineering

Harness Engineering is an evaluation methodology that answers one question: **"Is this agent safe to deploy to production?"**

```
25 Native Trackers  →  collect raw signals (no API cost, auto-enabled)
33 Harness Configs  →  define the deployment-readiness criteria (@agent_eval parameters)
 7 Harness Gates    →  per-group pass / warn / fail verdict → deployment decision
```

**Native metrics** are raw signals measured automatically while the agent runs.
**Harness Config** is the gate a developer sets — "on what basis do we pass or fail?"
**The 7 Gates** are the seven perspectives you must check before deploying — every gate must pass for deployment to be allowed.

```python
from agent_evaluator import (
    InstructionConfig, SLAConfig,
    LoopDetectionConfig, ExplainabilityConfig,
)
from agent_evaluator.decorators import agent_eval

# Harness Gate configuration — passed as @agent_eval parameters
@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),  # Gate A
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=6),                   # Gate B
    sla=SLAConfig(p95_ms=3000),                                                           # Gate D
    explainability=ExplainabilityConfig(require_reasoning=True, min_reasoning_length=30), # Gate G
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
# → check A/B/D/G pass status in the dashboard's Harness Gate tab
```

---

## Full metric summary (58)

### Native Trackers (25) — Gate contribution map

| Gate | Native metric | Tracker class | Activation |
|------|---------------|---------------|------------|
| **A** | Task Completion Rate (TCR) | `TaskCompletionTracker` | default |
| **A** | Accuracy (overall_accuracy → _a_vals) | `AccuracyEvaluator` | default |
| **A** | Response Quality (5 dimensions) | `ResponseQualityEvaluator` | default |
| **D** | Latency (P50·P90·P95·P99·TTFT) | `LatencyTracker` | default |
| **E** | Input Sanitization | `InputSanitizationTracker` | `enable_security_metrics=True` |
| **E** | Output Leakage | `OutputLeakageDetector` | `enable_security_metrics=True` |
| **E** | Tool Authorization | `ToolAuthorizationTracker` | `enable_security_metrics=True` |
| **E** | Privilege Escalation | `PrivilegeEscalationDetector` | `enable_security_metrics=True` |
| **E** | Tool Chain Attack | `ToolChainAttackDetector` | `enable_security_metrics=True` |
| **F** | Tool Selection Accuracy | `ToolSelectionTracker` | when `expected_tools` is given |
| **F** | Agent Coordination | `AgentCoordinationTracker` | when `agent_interactions` are recorded |
| **G** | Tool Call Success Rate | `ToolCallAnalyzer` | when `tool_calls` are recorded |
| **C+G** | Hallucination Rate (rule-based) | `HallucinationDetector` | `enable_hallucination_detection=True` |
| **C+G** | Context Recall (approx.) | `HallucinationDetector` | `rag_mode=True` |
| **C+G** | Context Precision (approx.) | `HallucinationDetector` | `rag_mode=True` |
| **L3** | completeness · relevance · factual | `LLMJudge` | `llm_judge=LLMJudgeConfig()` |
| **L3** | toxicity · bias · safety_score | `LLMJudge` | `llm_judge=LLMJudgeConfig()` |
| **L3** | Faithfulness *(replaces Ragas, v0.7.6+)* | `LLMJudge` | `rag_mode=True` + `llm_judge=LLMJudgeConfig()` |
| **L3** | G-Eval custom criteria *(replaces DeepEval, v0.7.6+)* | `LLMJudge` | `llm_judge=LLMJudgeConfig(criteria=[...])` |
| **L3** | Hallucination Score (NLI) | DeepEval | `HybridPerformanceMonitor` |
| **L3** | Answer Relevancy / Faithfulness / Context P·R | DeepEval·Ragas | `HybridPerformanceMonitor` |

> **C+G**: `HallucinationDetector` contributes a score to both Gate C (reliability — factual faithfulness of the output, `_rel_vals`) and Gate G (observability — hallucination-rate monitoring, `_obs_vals`). If the actual detection count (`_detections`) is 0, it contributes to neither gate.

> **Operational-only trackers** (do not contribute to any Gate score — the 13 in the table above plus these 9 make up all 25 Native Trackers): `RetryCorrectionTracker` (tracks retry counts and patterns) · `TokenEconomyTracker` (tracks and reports token cost) · `WorkflowExecutionTracker` (tracks chain steps and branches) · `MultimodalMetricsTracker` (aggregates image/audio/video/text usage shares; reads `extra["image_count"]` / `extra["audio_duration_seconds"]` / `extra["video_frames"]` automatically) · `ImplicitFeedbackTracker` (implicit user feedback — copy, thumbs_up, regenerate, etc.) · `ConversationSession` / `ConversationMetrics` (multi-turn conversation quality) · `AnomalyDetector` (Z-score / IQR anomaly detection) · `CostTracker` / `AdaptivePolicy` (external-evaluation cost budgeting) · `SamplingStage` (adaptive sampling stages) · `StreamingEvaluator` (real-time streaming evaluation). Their data appears in the report and dashboard but is not part of the Gate A–G score computation — see [`06_OBSERVABILITY.md`](06_OBSERVABILITY.md) for detail.

> LLMJudge (L3) ships in the base install. DeepEval and Ragas require `pip install agent-evaluator[eval]`.

### Harness Configs (33) — Gate assignment

| Gate | Group | Config list | Count |
|------|-------|-------------|-------|
| **A** | Goal Achievement | `InstructionConfig` · `GoalAlignmentConfig` · `PlanConfig` · `SubtaskConfig` · `ContextRetentionConfig` · `KnowledgeRetentionConfig` | 6 |
| **B** | Behavioral Integrity | `LoopDetectionConfig` · `ScopeConfig` · `ToolParameterSafetyConfig` · `ContextWindowConfig` · `StateConsistencyConfig` · `DeadlockConfig` | 6 |
| **C** | Reliability | `ReproducibilityConfig` · `FaultToleranceConfig` · `GracefulDegradationConfig` · `RetryConsistencyConfig` · `IdempotencyConfig` | 5 |
| **D** | Performance Contract | `SLAConfig` · `EfficiencyConfig` · `ResourceBudgetConfig` · `TTFTVariabilityConfig`† · `CostPredictabilityConfig`† | 5 |
| **E** | Security Boundary | `ThreatSeverityConfig` · `ComplianceConfig` · `ThreatResponseConfig` | 3 |
| **F** | Multi-Agent Coord. | `ConsensusConfig` · `PropagationConfig` · `AgentRoleConfig` · `ConflictResolutionConfig` | 4 |
| **G** | Observability | `ExplainabilityConfig` · `ObservabilityConfig` · `ErrorDiagnosisConfig` · `LatencyAttributionConfig` | 4 |

> †`TTFTVariabilityConfig` and `CostPredictabilityConfig` are aggregated automatically at the monitor level (≥5 tasks). No decorator parameter is needed.

---

## Gate A — Goal Achievement

**"Did the agent faithfully accomplish the user's intent?"**

The first gate in the deployment decision. The TCR and Accuracy native metrics provide the raw signal; the Harness Config A group defines the pass criteria.

### Linked native metrics

| Metric | Core role | Deployment bar |
|--------|-----------|----------------|
| **TCR** (Task Completion Rate) | Did the agent complete the task | 🟢 ≥95% / 🟡 85–95% / 🔴 <85% |
| **Accuracy** | How closely it matches the reference answer | 🟢 ≥90% / 🟡 80–90% / 🔴 <80% |

> **TCR formula**: `TCR = Σ(completion_score) / task_count × 100`
> **Accuracy formula (QA)**: `0.4 × TokenF1 + 0.3 × Jaccard + 0.2 × LCS + 0.1 × CharSimilarity`
> → for the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate A (6)

#### `InstructionConfig` — instruction adherence · drift detection

Verifies that the agent faithfully followed the instructions in the prompt.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `required_keywords` | `list[str]` | `[]` | keywords that must appear in the response |
| `forbidden_phrases` | `list[str]` | `[]` | phrases that must not appear in the response |
| `expected_format` | `str\|None` | `None` | expected response format (`"json"`, `"markdown"`, `"yaml"`, `"plain"`) |
| `required_sections` | `list[str]` | `[]` | section headings that must appear in the response |
| `max_chars` | `int\|None` | `None` | maximum allowed character count |
| `min_chars` | `int\|None` | `None` | minimum required character count |
| `max_words` | `int\|None` | `None` | maximum allowed word count |
| `min_words` | `int\|None` | `None` | minimum required word count |
| `expected_language` | `str\|None` | `None` | expected language code (e.g. `"ko"`, `"en"`) |
| `fail_on_violation` | `bool` | `False` | if True, a violation marks the task as success=False |
| `violation_weight` | `float` | `0.1` | penalty weight per violation |

> Decorator parameter name: `instructions=InstructionConfig(...)` (plural)

```python
instructions=InstructionConfig(
    required_keywords=["Seoul", "capital"],
    forbidden_phrases=["I don't know"],
    fail_on_violation=True,
)
```

#### `GoalAlignmentConfig` — goal-alignment score · partial-credit

Measures how well the actual outcome aligns with the task goal.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_keyword_overlap` | `bool` | `True` | compute overlap between question keywords ↔ tool names |
| `goal_tool_map` | `dict[str, list[str]]` | `{}` | goal keyword → tool list mapping |
| `alignment_threshold` | `float` | `0.6` | alignment threshold below which a warning fires (0.0–1.0) |
| `use_llm_scoring` | `bool` | `False` | LLM-as-Judge alignment score (opt-in) |
| `llm_blend_weight` | `float` | `0.5` | LLM-judge blend weight (0.0 = rule only, 1.0 = LLM only) |
| `ignore_no_tool_tasks` | `bool` | `True` | ignore tasks with no tool calls |

#### `PlanConfig` — plan coherence · step completion rate

Verifies that a multi-step agent executed according to its plan.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `available_tools` | `list[str]` | `[]` | list of executable tools (used to check step executability) |
| `check_goal_coverage` | `bool` | `True` | check that goal keywords appear in the plan steps |
| `check_step_ordering` | `bool` | `True` | check that step ordering is logical |
| `check_executability` | `bool` | `True` | check that each step is executable with an available tool |
| `min_steps` | `int` | `2` | minimum number of plan steps |
| `max_steps` | `int` | `15` | maximum number of plan steps |
| `use_llm_scoring` | `bool` | `False` | LLM-as-Judge plan-quality scoring (opt-in) |
| `llm_blend_weight` | `float` | `0.5` | LLM-judge blend weight |
| `plan_field` | `str` | `"plan"` | JSON field to extract the plan from in the response |
| `steps_field` | `str` | `"steps"` | field name for the steps within the plan |

> Decorator parameter name: `plan_tracking=PlanConfig(...)` (not `plan=`)

#### `SubtaskConfig` — subtask decomposition · completion rate

Measures the decomposition quality of a complex task.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expected_subtasks` | `list[str]` | `[]` | expected subtask list |
| `completion_markers` | `list[str]` | `['done', 'completed', 'finished', '✓', '완료', '처리']` | marker strings that indicate completion |
| `min_completion_rate` | `float` | `0.8` | lower bound on the subtask completion rate |
| `check_ordering` | `bool` | `False` | verify subtask ordering |
| `auto_extract` | `bool` | `False` | auto-extract completed subtasks from the response |

> Decorator parameter name: `subtask_tracking=SubtaskConfig(...)` (not `subtask=`)

#### `ContextRetentionConfig` — conversational context retention

Verifies that prior context is retained across a multi-turn conversation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key_entities` | `list[str]` | `[]` | key entities whose retention is verified |
| `context_arg` | `str` | `"context"` | name of the context argument |
| `retention_threshold` | `float` | `0.7` | lower bound on the entity retention rate to pass |
| `check_original_goal` | `bool` | `True` | verify retention of the original goal |
| `entity_weight` | `float` | `0.6` | entity-retention weight |
| `goal_weight` | `float` | `0.4` | goal-retention weight |

#### `KnowledgeRetentionConfig` — knowledge retention · utilization score

Measures whether the agent correctly retains and uses injected knowledge.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `facts_to_retain` | `list[str]` | `[]` | facts / knowledge items whose retention is verified |
| `seed_turns` | `int` | `2` | number of initial turns in which knowledge is injected |
| `check_from_turn` | `int` | `3` | turn number at which verification begins |
| `retention_threshold` | `float` | `0.6` | lower bound on the knowledge retention rate to pass |
| `allow_implicit_retention` | `bool` | `True` | count implicit retention (paraphrase, etc.) |

---

## Gate B — Behavioral Integrity

**"Does the agent behave predictably and stably?"**

Detects patterns where an agent misbehaves — loops, scope drift, state inconsistency, deadlock. Among the native metrics, Tool Call Efficiency provides an indirect signal of abnormal behavior.

### Linked native metrics

| Metric | Gate B relevance |
|--------|------------------|
| **Tool Call Efficiency** | a spike in redundant / failed calls → indirect indicator of a loop or scope drift |

> For the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate B (6)

#### `LoopDetectionConfig` — repetitive-loop detection

Detects loop patterns where the same tool call or response repeats.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `consecutive_repeat_threshold` | `int` | `6` | detect a loop after N consecutive identical tool calls — compares the tool name only (parameters ignored). For agents with coarse-grained tools (e.g. OpenCode, where all shell activity is captured as a single "bash" tool), a low value produces false positives on normal behavior, so it is raised to 6 (see Docs/AOO_STACK.md) |
| `window_size` | `int` | `5` | sliding-window size |
| `duplicate_in_window_threshold` | `int` | `3` | allowed number of duplicate tool calls within the window (2 causes false positives on normal multi-step agents) |
| `check_response_loop` | `bool` | `False` | additionally check for loops in the response text |
| `response_similarity_threshold` | `float` | `0.95` | response-similarity threshold (when `check_response_loop=True`) |
| `on_loop_detected` | `str` | `"record"` | action on loop detection: `"record"` / `"warn"` / `"fail"` |

```python
loop_detection=LoopDetectionConfig(
    consecutive_repeat_threshold=6,
    window_size=5,
)
```

#### `ScopeConfig` — scope-drift detection · allowed_tools

Detects when the agent attempts actions outside its allowed tool scope.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allowed_tools` | `List[str]` | `[]` | allowed tool list |
| `forbidden_tools` | `List[str]` | `[]` | forbidden tool list |
| `max_tool_calls` | `Optional[int]` | `None` | maximum tool calls per task |
| `max_unique_tools` | `Optional[int]` | `None` | maximum distinct tool types per task |
| `fail_on_violation` | `bool` | `False` | mark the task failed on a violation |

> Decorator parameter name: `scope=ScopeConfig(...)`

#### `ToolParameterSafetyConfig` — tool-parameter safety · forbidden patterns

Checks tool-call parameters for dangerous patterns, forbidden keys, and schema violations.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_schemas` | `Dict[str, Dict]` | `{}` | per-tool parameter schema (basis for violation checks) |
| `dangerous_patterns` | `List[str]` | `[r"\.\./"...]` | list of dangerous-pattern regexes (7 built-in: `../`, `&&`, `\|\|`, etc.) |
| `forbidden_argument_keys` | `Dict[str, List[str]]` | `{}` | tool name → forbidden argument-key list mapping |
| `max_argument_length` | `int` | `2000` | maximum allowed argument-value length |
| `fail_on_dangerous` | `bool` | `False` | mark the task failed when a dangerous pattern is detected |

> Decorator parameter name: `tool_parameter_safety=ToolParameterSafetyConfig(...)`

#### `ContextWindowConfig` — context-window utilization efficiency

Measures the saturation, repetition patterns, and information density of the model's context window.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_size_tokens` | `int` | `128000` | maximum context-window token count |
| `warn_at_pct` | `float` | `0.7` | utilization threshold that triggers a warning (70%) |
| `saturated_at_pct` | `float` | `0.9` | utilization threshold considered saturated (90%) |
| `repetition_threshold` | `int` | `3` | repetition-pattern detection threshold |
| `min_information_density` | `float` | `0.3` | minimum information density (below this, a warning fires) |

> Decorator parameter name: `context_window=ContextWindowConfig(...)`

#### `StateConsistencyConfig` — pre/post-run state consistency · unchanged_keys

Verifies that state before and after a run changes (or stays) as expected.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `state_fn` | `Optional[Callable]` | `None` | a function returning a state dict before and after the run |
| `expected_changes` | `Dict[str, Any]` | `{}` | expected-change key → validation-lambda mapping |
| `unchanged_keys` | `List[str]` | `[]` | state keys that must not change |
| `fail_on_unexpected_change` | `bool` | `False` | mark the task failed on an unexpected state change |

> Decorator parameter name: `state_consistency=StateConsistencyConfig(...)`

#### `DeadlockConfig` — deadlock detection · circular delegation · starvation

Detects deadlock, circular delegation, and starvation in a multi-agent system.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `check_circular_delegation` | `bool` | `True` | enable circular-delegation detection |
| `check_starvation` | `bool` | `True` | enable resource-starvation detection |
| `starvation_threshold` | `int` | `3` | consecutive-wait threshold to consider starvation |
| `check_livelock` | `bool` | `False` | enable livelock detection |
| `livelock_window` | `int` | `6` | sliding-window size for livelock detection |
| `max_delegation_depth` | `int` | `10` | maximum delegation depth |

> Decorator parameter name: `deadlock=DeadlockConfig(...)`

---

## Gate C — Reliability

**"Does the agent produce consistent results for the same input, and can it recover after an error?"**

In production an agent is exposed to intermittent errors, network instability, and abnormal inputs. Gate C verifies the agent still behaves reliably under those conditions.

### Linked native metrics

| Metric | Gate C relevance |
|--------|------------------|
| **Fault Tolerance** | recovery rate after a tool-call failure — the success/failure data of `tool_calls` is the raw signal for FaultToleranceConfig (RetryCorrectionTracker does not contribute to a gate score) |
| **Hallucination Rate** | factual faithfulness of the output — `1 − hall_rate` contributes directly to `_rel_vals` (only when the detection count > 0) |

> **Formula**: `retry_success_rate = succeeded_after_retry / retried_tasks × 100`
> 🟢 ≥80% / 🟡 60–80% / 🔴 <60%
> → for the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate C (5)

#### `ReproducibilityConfig` — consistency across repeated runs of the same input

Verifies that running the same input multiple times yields consistent results.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `runs` | `int` | `3` | number of repeated runs of the same input |
| `similarity_measure` | `str` | `"token_f1"` | similarity measure: `"token_f1"` / `"jaccard"` / `"exact"` |
| `reproducibility_threshold` | `float` | `0.85` | reproducibility pass threshold |
| `fail_on_low_reproducibility` | `bool` | `False` | mark the task failed below the threshold |
| `skip_side_effects` | `bool` | `False` | skip functions with side effects |

> Decorator parameter name: `reproducibility=ReproducibilityConfig(...)`

```python
reproducibility=ReproducibilityConfig(
    runs=3,
    similarity_measure="token_f1",
    reproducibility_threshold=0.9,
)
```

#### `FaultToleranceConfig` — post-error recovery rate · clean-completion rate

Measures the agent's ability to recover after an error by using a fallback tool.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `check_fallback_attempts` | `bool` | `True` | track whether a fallback tool is used after a failure |
| `partial_success_threshold` | `float` | `0.5` | threshold for granting partial-success credit |
| `score_recovery_quality` | `bool` | `True` | score the quality of the fallback recovery |
| `expected_fallback_tools` | `Dict[str, List[str]]` | `{}` | tool name → fallback tool-list mapping |

> Decorator parameter name: `fault_tolerance=FaultToleranceConfig(...)`

#### `GracefulDegradationConfig` — quality floor · partial_result_markers

Measures whether a minimum quality floor is guaranteed even under failure / degradation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `partial_result_markers` | `List[str]` | `["partial","incomplete",...]` | partial-result marker strings (6 built-in) |
| `quality_floor` | `float` | `0.3` | lowest acceptable quality score |
| `detect_timeout_fallback` | `bool` | `True` | detect timeout fallbacks |
| `empty_response_penalty` | `float` | `1.0` | penalty for an empty response |
| `check_error_acknowledgment` | `bool` | `True` | check for error-acknowledgment language |

> Decorator parameter name: `graceful_degradation=GracefulDegradationConfig(...)`

#### `RetryConsistencyConfig` — response consistency across retries

Measures retry efficiency and whether retries improve the result, based on retry counts and success.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `group_by_task_prefix` | `bool` | `True` | group by task prefix |
| `improvement_threshold` | `float` | `0.1` | minimum improvement threshold across retries |
| `penalize_degradation` | `bool` | `True` | penalize a performance drop after a retry |
| `min_retry_count` | `int` | `2` | minimum retry count needed to measure consistency |

> Decorator parameter name: `retry_consistency=RetryConsistencyConfig(...)`

#### `IdempotencyConfig` — idempotency verification · repeat-execution safety

Evaluates whether a tool call causes side effects when executed repeatedly.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `non_idempotent_patterns` | `List[str]` | `["create","delete","insert",...]` | non-idempotent tool-name patterns (10 built-in) |
| `duplicate_detection_markers` | `List[str]` | `["already","duplicate",...]` | response markers indicating duplicate detection |
| `non_idempotent_penalty` | `float` | `0.2` | penalty for using a non-idempotent tool |
| `warn_on_non_idempotent` | `bool` | `True` | warn when a non-idempotent tool is used |

> Decorator parameter name: `idempotency=IdempotencyConfig(...)`

---

## Gate D — Performance Contract

**"Does the agent honor its SLA, cost, and token budgets?"**

The basis on which an operations team signs a service-level agreement for an agent system. The Latency and Token Economy native metrics provide the raw measurements; the Harness Config D group sets the contract thresholds.

### Linked native metrics

| Metric | Core role | Deployment bar |
|--------|-----------|----------------|
| **Latency** | measures P50·P90·P95·P99·TTFT | 🟢 P95 <3s / 🟡 3–5s / 🔴 ≥5s |
| **Token Economy** | token usage + cost estimate | 🟢 <$0.01/task / 🔴 ≥$0.05 |

> **Latency formula**: measured `TaskResult.execution_time` (seconds)
> **Cost formula**: `Cost = (input_tokens × input_price + output_tokens × output_price) / 1000`
> → for the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate D (5)

#### `SLAConfig` — SLA response-time thresholds · P95/P99 breach rate

Defines the response-time criteria of a service-level agreement (SLA).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `p95_ms` | `float` | `5000.0` | P95 response-time pass criterion (ms) |
| `p99_ms` | `float` | `10000.0` | P99 response-time pass criterion (ms) |
| `ttft_ms` | `Optional[float]` | `None` | TTFT upper bound (ms; None = no limit) |
| `breach_window` | `int` | `10` | sliding-window size for aggregating breaches |
| `warn_threshold` | `int` | `2` | breach count that triggers a warning |
| `fail_threshold` | `int` | `5` | breach count that triggers a fail verdict |
| `max_cost_per_task` | `Optional[float]` | `None` | maximum allowed cost per task ($) |
| `budget_usd` | `Optional[float]` | `None` | overall budget cap ($) |
| `token_limit` | `Optional[int]` | `None` | maximum allowed tokens per task |

> Decorator parameter name: `sla=SLAConfig(...)`
>
> Exceeding `breach_window` / `fail_threshold` or `budget_usd` only applies a penalty to the Gate D score, capped at 0.3 (30%) — **it does not automatically fail Gate D.** If other metrics (latency, efficiency, etc.) are strong, the gate can still pass/warn after the penalty. The penalty basis is visible in `report.extra_metrics["harness_groups"]["D"]["details"]` as `sla_window_penalty` / `sla_budget_penalty` / `perf_score_pre_sla_penalty`.

```python
sla=SLAConfig(
    p95_ms=3000.0,
    p99_ms=5000.0,
    warn_threshold=2,
    fail_threshold=5,
)
```

#### `EfficiencyConfig` — token efficiency · completion rate per tool call

Measures return on investment (ROI) — completion rate relative to cost.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cost_unit` | `str` | `"tokens"` | cost unit: `"tokens"` / `"usd"` / `"time_ms"` |
| `target_cost_per_completion` | `Optional[float]` | `None` | target cost per task (None = no limit) |
| `penalize_failed_tokens` | `bool` | `True` | include tokens from failed tasks in the cost |
| `warn_ratio` | `float` | `2.0` | warning multiple relative to the target |
| `fail_ratio` | `float` | `4.0` | fail multiple relative to the target |
| `fallback_reference_cost_per_completion` | `Optional[float]` | `None` | normalization basis for `efficiency_ratio` when `target_cost_per_completion` is unset. If `None`, uses the per-`cost_unit` default (tokens/time_ms = 1000, usd = 0.01) |

> Decorator parameter name: `efficiency=EfficiencyConfig(...)`
>
> Not setting `target_cost_per_completion` does not exclude `EfficiencyConfig` from the Gate D aggregation — only the calibrated banded verdict (`calibrated_score`) is unavailable; `efficiency_ratio` is still normalized 0–1 against the fallback basis above and continues to feed the Gate D score. The basis actually applied is visible in `report.extra_metrics["harness_groups"]["D"]["details"]["efficiency_ratio_reference_cost"]`.

#### `ResourceBudgetConfig` — token budget · cost cap

Defines the upper bound on resources consumable in the deployment environment.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_tokens` | `Optional[int]` | `None` | maximum allowed tokens per task |
| `max_cost_usd` | `Optional[float]` | `None` | maximum allowed cost per task ($) |
| `max_execution_time_ms` | `Optional[float]` | `None` | maximum execution time per task (ms) |
| `warn_at_pct` | `float` | `0.8` | budget-utilization warning threshold (80%) |
| `count_failed_tokens` | `bool` | `True` | include failed-task tokens in the budget |
| `rollover` | `bool` | `False` | carry unused budget to the next task |

> Decorator parameter name: `resource_budget=ResourceBudgetConfig(...)`

#### `TTFTVariabilityConfig`† — TTFT standard deviation · P95/P50 ratio

Measures the variability of time-to-first-token for a streaming agent.

> †**Aggregated automatically at the monitor level** — you do not need to pass it as a decorator parameter (≥5 tasks required).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_stddev_ms` | `float` | `500.0` | upper bound on TTFT standard deviation (ms) |
| `max_p95_p50_ratio` | `float` | `3.0` | upper bound on the P95/P50 ratio (a variability indicator) |
| `min_samples` | `int` | `5` | minimum samples needed to measure variability |
| `remove_outliers` | `bool` | `True` | compute statistics after removing outliers |

#### `CostPredictabilityConfig`† — per-task_type token CV · cost predictability

Measures the coefficient of variation (CV) of cost per task type.

> †**Aggregated automatically at the monitor level** — you do not need to pass it as a decorator parameter (≥5 tasks required).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_coefficient_of_variation` | `float` | `0.3` | maximum allowed cost coefficient of variation (CV) |
| `outlier_multiplier` | `float` | `3.0` | outlier multiple (IQR-based) |
| `min_samples` | `int` | `5` | minimum samples needed to measure |
| `cost_metric` | `str` | `"tokens"` | cost metric: `"tokens"` / `"usd"` / `"time_ms"` |

---

## Gate E — Security Boundary

**"Does the agent operate only within its allowed security boundary?"**

A required gate before deploying a security-sensitive agent. The 5 native security metrics perform the actual attack detection; the Harness Config E group defines the threat-response policy.

Activation: `PerformanceMonitor(enable_security_metrics=True)` or `PerformanceMonitor.for_secure_agents()`

### Linked native metrics (5 security)

| Metric | What it detects | Deployment bar |
|--------|-----------------|----------------|
| **Input Sanitization** | SQL / command injection, XSS, prompt injection | 🔴 threat rate >5%: block deploy |
| **Output Leakage** | leaked API keys, credit cards, emails, PII | 🔴 even 1 Critical: block deploy |
| **Tool Authorization** | unauthorized tool calls | 🔴 unauthorized_calls >0: block deploy |
| **Privilege Escalation** | vertical read→write→admin escalation | 🔴 high_risk_events >0: block deploy |
| **Tool Chain Attack** | chained attacks — data exfiltration, lateral movement, etc. | 🔴 exfiltration >0: block deploy |

> → for the detailed detection patterns and API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate E (3)

#### `ThreatSeverityConfig` — threat-severity classification · threshold blocking

Sets the severity-classification criteria and the auto-block thresholds for detected threats.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `severity_weights` | `Dict[str, float]` | `{}` | per-threat-type CVSS weight mapping |
| `warn_score` | `float` | `4.0` | lower bound of the threat-severity score that triggers a warning |
| `fail_score` | `float` | `7.0` | lower bound of the threat-severity score that triggers a fail |
| `fail_on_critical` | `bool` | `True` | mark the task failed when a Critical threat is detected |

> Decorator parameter name: `threat_severity=ThreatSeverityConfig(...)`

```python
threat_severity=ThreatSeverityConfig(
    fail_score=7.0,
    fail_on_critical=True,
)
```

#### `ComplianceConfig` — compliance patterns · PII detection

Measures PII exposure and compliance-framework violations.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pii_categories` | `List[str]` | `["name","email","phone",...]` | PII categories to detect (7 built-in) |
| `compliance_framework` | `str` | `"general"` | compliance framework: `"gdpr"` / `"hipaa"` / `"general"` |
| `require_data_minimization` | `bool` | `True` | check adherence to the data-minimization principle |
| `forbidden_data_patterns` | `List[str]` | `[]` | data patterns forbidden in output (regex) |
| `check_consent_language` | `bool` | `False` | check for the presence of consent language |
| `violation_severity` | `str` | `"high"` | severity classification for a violation |

> Decorator parameter name: `compliance=ComplianceConfig(...)`

#### `ThreatResponseConfig` — verify post-detection response behavior

Verifies that when a security threat is detected, the agent appropriately blocks, escalates, or aborts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `isolation_markers` | `List[str]` | `["blocked","rejected",...]` | isolation / block response markers |
| `escalation_markers` | `List[str]` | `["escalate","report",...]` | escalation response markers |
| `abort_markers` | `List[str]` | `["abort","stop",...]` | abort / terminate response markers |
| `score_clean_tasks` | `bool` | `True` | also score threat-free normal tasks |
| `no_response_penalty` | `float` | `0.5` | penalty for no response after a threat is detected |

> Decorator parameter name: `threat_response=ThreatResponseConfig(...)`

---

## Gate F — Multi-Agent Coordination

**"Do multiple agents cooperate effectively to reach the goal?"**

The deployment gate for a multi-agent system. The Agent Coordination and Tool Selection native metrics measure the actual quality of cooperation; the Harness Config F group defines the pass criteria.

### Linked native metrics

| Metric | Core role | Deployment bar |
|--------|-----------|----------------|
| **Tool Selection Accuracy** | F1-based tool-selection accuracy — `avg_f1_score / 100` contributes to `_f_vals` | 🟢 ≥90% / 🟡 80–90% / 🔴 <80% |
| **Agent Coordination** | inter-agent coordination score — `overall_score / 10` contributes to `_f_vals` | 🟢 ≥8/10 / 🟡 6–8 / 🔴 <6 |

> **Note**: WorkflowExecutionTracker and ToolCallAnalyzer (Tool Call Efficiency) do not contribute to a gate score — the former is for chain_steps tracking only, the latter is a Gate G contributor.

> → for the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate F (4)

#### `ConsensusConfig` — inter-agent agreement rate · dispute detection

Measures the ability of multiple agents to reach consensus when making a decision.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `consensus_method` | `str` | `"majority"` | consensus method: `"majority"` / `"weighted"` / `"unanimity"` |
| `agent_weights` | `Dict[str, float]` | `{}` | per-agent weights (used with the weighted method) |
| `similarity_threshold` | `float` | `0.7` | response-similarity threshold for judging agreement |
| `select_consensus_response` | `bool` | `False` | select the consensus response as the final result |

> Decorator parameter name: `consensus=ConsensusConfig(...)` (most effective together with `@batch_eval`)

```python
consensus=ConsensusConfig(
    consensus_method="weighted",
    agent_weights={"expert": 3.0},
)
```

#### `PropagationConfig` — information-propagation accuracy · distortion detection

Measures whether key facts propagate faithfully as information is passed between agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_agent` | `str` | `""` | name of the information-source agent |
| `key_facts` | `List[str]` | `[]` | key facts whose propagation is verified |
| `check_in_response` | `bool` | `True` | check for the facts in the response text |
| `check_in_tool_calls` | `bool` | `False` | check for the facts in tool-call arguments |
| `similarity_threshold` | `float` | `0.7` | similarity threshold for judging a fact match |
| `penalize_distortion` | `bool` | `True` | penalize distorted propagation |

> Decorator parameter name: `propagation=PropagationConfig(...)`

#### `AgentRoleConfig` — role-adherence rate · role-violation detection

Verifies that each agent stays within its assigned role.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `role_name` | `str` | `""` | the evaluated agent's role name |
| `allowed_tools` | `List[str]` | `[]` | tools allowed within the role |
| `forbidden_tools` | `List[str]` | `[]` | tools forbidden within the role |
| `allowed_action_keywords` | `List[str]` | `[]` | action keywords allowed within the role |
| `forbidden_action_keywords` | `List[str]` | `[]` | action keywords forbidden within the role |
| `check_tool_role_alignment` | `bool` | `True` | check tool–role alignment |
| `role_violation_penalty` | `float` | `0.3` | penalty for a role violation |

> Decorator parameter name: `agent_role=AgentRoleConfig(...)`

#### `ConflictResolutionConfig` — conflict-resolution pattern · resolution time

Measures conflict detection and resolution quality between agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `conflict_markers` | `List[str]` | `["disagree","conflict",...]` | conflict-detection markers |
| `resolution_markers` | `List[str]` | `["resolved","consensus",...]` | resolution-detection markers |
| `check_resolution_quality` | `bool` | `True` | score the resolution quality |
| `require_explanation` | `bool` | `False` | require an explanation of the resolution process |
| `unresolved_penalty` | `float` | `0.5` | penalty for an unresolved conflict |
| `expect_escalation_on_fail` | `bool` | `False` | expect escalation when resolution fails |

> Decorator parameter name: `conflict_resolution=ConflictResolutionConfig(...)`

---

## Gate G — Observability

**"Can you understand and debug the agent's internal behavior?"**

The gate for diagnosing agent failures quickly in production. The Response Quality native metric provides an observable signal of response quality.

### Linked native metrics

| Metric | Gate G relevance |
|--------|------------------|
| **Response Quality (5 dimensions)** | observable quality dimensions — Relevance · Completeness · Accuracy · Clarity · Usefulness |
| **Hallucination Rate** | hallucination-monitoring signal — `1 − hall_rate` contributes to `_obs_vals` (also contributes to Gate C at the same time; see the [Hallucination Rate reference](#hallucination-rate-rule-based)) |

> **Quality Score formula**: `Σ(dimension_score × weight)`, range 0–5
> 🟢 ≥4.5 (A) / 🟡 4.0–4.5 (B) / 🟠 3.5–4.0 (C) / 🔴 <3.0 (F)
> → for the detailed API, see the [Native Tracker Reference](#native-tracker-reference)

### Harness Config — Gate G (4)

#### `ExplainabilityConfig` — explainability of the reasoning process

Measures whether the reasoning process the agent uses to reach a conclusion is explainable.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `require_reasoning` | `bool` | `True` | require the presence of reasoning markers |
| `reasoning_markers` | `List[str]` | `['because', 'therefore', 'since', 'thus', 'reason', '왜냐하면', '따라서']` | reasoning-marker keywords |
| `require_uncertainty_expression` | `bool` | `False` | require the expression of uncertainty |
| `uncertainty_markers` | `List[str]` | `['uncertain', 'may', 'might', 'possibly', 'not sure', '불확실']` | uncertainty-expression markers |
| `require_citations` | `bool` | `False` | require the presence of citations |
| `citation_markers` | `List[str]` | `['according to', 'based on', 'source:', 'ref:', '참고:']` | citation markers |
| `min_reasoning_length` | `int` | `20` | minimum reasoning-text length (characters) |
| `check_action_explanation_alignment` | `bool` | `False` | check action–explanation alignment |

> Decorator parameter name: `explainability=ExplainabilityConfig(...)`

```python
explainability=ExplainabilityConfig(
    require_reasoning=True,
    min_reasoning_length=50,
    require_citations=True,
)
```

#### `ObservabilityConfig` — internal-state exposure · traceability

Verifies OTEL span completeness and audit-event SLOs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `required_span_attributes` | `List[str]` | `["task_id","task_type","execution_time"]` | attributes an OTEL span must include |
| `check_trace_continuity` | `bool` | `True` | check span continuity (parent–child relationship) |
| `audit_events` | `List[str]` | `[]` | audit-event types |
| `min_coverage` | `float` | `0.95` | lower bound on trace coverage to pass |

> Decorator parameter name: `observability=ObservabilityConfig(...)`

#### `ErrorDiagnosisConfig` — accuracy of error root-cause diagnosis

Evaluates whether a failure response acknowledges the error, states a root cause, and proposes an alternative.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `failure_acknowledgment_markers` | `List[str]` | `["failed","unable",...]` | error-acknowledgment markers |
| `root_cause_markers` | `List[str]` | `["because","due to",...]` | root-cause markers |
| `suggestion_markers` | `List[str]` | `["try","suggest",...]` | alternative-suggestion markers |
| `only_on_failure` | `bool` | `True` | score only failed tasks |
| `acknowledgment_weight` | `float` | `0.3` | error-acknowledgment weight |
| `root_cause_weight` | `float` | `0.5` | root-cause-analysis weight |
| `suggestion_weight` | `float` | `0.2` | alternative-suggestion weight |

> Decorator parameter name: `error_diagnosis=ErrorDiagnosisConfig(...)`

#### `LatencyAttributionConfig` — latency root-cause analysis · per-segment contribution

Analyzes, of the total execution time, the share attributable to tool, model, network, and unattributed latency.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_latency_key` | `str` | `"tool_latencies"` | key in task extra to read tool latency from |
| `model_latency_key` | `str` | `"model_latency_ms"` | key in task extra to read model latency from |
| `network_latency_key` | `str` | `"network_latency_ms"` | key in task extra to read network latency from |
| `max_tool_time_ratio` | `float` | `0.6` | maximum tool-latency share (of total execution time) |
| `max_unattributed_ratio` | `float` | `0.3` | maximum unattributed-latency share |

> Decorator parameter name: `latency_attribution=LatencyAttributionConfig(...)`

---

## L3 — Semantic Evaluation

LLM-based semantic evaluation that complements the rule-based measurement of Gates A–G. Tightly linked to Gate A (accuracy) and Gate G (quality).

### LLMJudge (native, ships in the base install)

Install: `pip install agent-evaluator` (included by default)
Requires: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
Activate: `llm_judge=LLMJudgeConfig()`

**Dimensions measured (7+)**

| Dimension | Range | Activation condition |
|-----------|-------|----------------------|
| `completeness` | 0–5 | default |
| `relevance` | 0–5 | default |
| `factual_consistency` | 0–5 | default |
| `toxicity` | 0–5 (lower is better) | default |
| `bias` | 0–5 (lower is better) | default |
| `safety_score` | 0–1 | default (`= (10 - toxicity - bias) / 10`) |
| `faithfulness` | 0–5 | `rag_mode=True` + context |
| `criteria_scores` | 0–5 each | when `criteria=[...]` is given |
| `criteria_overall` | 0–5 | mean when `criteria=[...]` is given |

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

# base 5 dimensions + safety_score
@agent_eval(monitor, task_type="qa",
    llm_judge=LLMJudgeConfig(sample_rate=0.1)   # score only 10% (cost saving)
)
def agent(question, ground_truth=""): ...

# RAG Faithfulness (replaces Ragas)
@agent_eval(monitor, rag_mode=True,
    llm_judge=LLMJudgeConfig()
)
def rag_agent(question, context="", ground_truth=""): ...
# → scores["faithfulness"]: 0–5 (5 = every claim is grounded in the context)

# G-Eval custom criteria (replaces DeepEval)
@agent_eval(monitor,
    llm_judge=LLMJudgeConfig(criteria=["medical_accuracy", "patient_safety"])
)
def medical_agent(question, ground_truth=""): ...
# → scores["criteria_scores"]["medical_accuracy"]: 0–5
# → scores["criteria_overall"]: mean of the custom criteria
```

### DeepEval + Ragas (`[eval]` extra)

Install: `pip install agent-evaluator[eval]`
Requires: `OPENAI_API_KEY`
Use: `HybridPerformanceMonitor`

> LLMJudge replaces DeepEval G-Eval and Ragas Faithfulness without an external package (v0.7.6+).
> Use `HybridPerformanceMonitor` when you need higher accuracy (NLI-based, 90–95%) or when integrating with the DeepEval/Ragas ecosystem.

**DeepEval metrics (5)**

| Metric | Range | Direction | Criterion |
|--------|-------|-----------|-----------|
| G-Eval | 0–1 | ⬆ higher is better | ≥0.9 excellent |
| Hallucination Score | 0–1 | ⬆ (= no hallucination) | ≥0.9 excellent |
| Toxicity | 0–1 | ⬇ lower is better | <0.1 safe |
| Bias | 0–1 | ⬇ lower is better | <0.1 fair |
| Answer Relevancy | 0–1 | ⬆ higher is better | ≥0.9 excellent |

> ⚠️ DeepEval's Hallucination Score has the **opposite direction** from the L1 Hallucination Rate (rule-based, ⬇ lower is better).

**Ragas metrics (4, RAG only)**

| Metric | Formula summary | Criterion |
|--------|-----------------|-----------|
| Faithfulness | context-supported claims / total claims | ≥0.9 trustworthy |
| Answer Relevancy | back-generated question ↔ original question similarity | ≥0.9 excellent |
| Context Precision | relevant context / total retrieved context | ≥0.9 excellent |
| Context Recall | retrieved relevant info / total needed info | ≥0.9 excellent |

```python
from agent_evaluator import HybridPerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = HybridPerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="information_retrieval",
    rag_mode=True, context_arg="context"
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

---

## Native Tracker Reference

> A detailed reference for formulas, output keys, and API signatures. Explains how each native metric behaves in its Gate context.

---

### TCR — Task Completion Rate

**Core Gate A metric**

**Formula**

```
TCR = Σ(completion_score) / task_count × 100
```

`completion_score` is a `TaskResult` field (0.0–1.0). Computed automatically when using `create_taskresult()`.

> **Completion judgment by task_type (v0.8.0+)**
> - `code_generation`/`coding`: 1.0 on successful AST parse, otherwise length-based
> - `tool_use`: 0.6 when `tool_calls` is empty (partial completion — no tools used)
> - otherwise: response-length-based + similarity-based when `ground_truth` is present

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | ≥ 95 |
| 🟡 good | 85–95 |
| 🟠 fair | 70–85 |
| 🔴 needs work | < 70 |

**Output keys**

```python
report.task_completion_rate                          # float (0–100)
report.to_dict()["tcr_data"]["success_rate"]         # float (0–1)
report.to_dict()["tcr_data"]["total_tasks"]          # int
report.to_dict()["tcr_data"]["successful_tasks"]     # int
```

---

### Accuracy

**Core Gate A metric** — `overall_accuracy / 100` contributes directly to Gate A `_a_vals` (when the AccuracyEvaluator evaluation count > 0)

**Formula — QA (weighted combination)**

```
accuracy = 0.4 × TokenOverlapF1 + 0.3 × Jaccard + 0.2 × LCS + 0.1 × CharSimilarity
```

| Metric | Weight | Method |
|--------|--------|--------|
| TokenOverlapF1 | 40% | token F1 (harmonic mean of precision × recall) — prevents long-response padding |
| Jaccard | 30% | set intersection / union |
| LCS | 20% | longest common subsequence |
| CharSimilarity | 10% | Levenshtein-distance-based (reflects character order, v0.8.0+) |

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | ≥ 90 |
| 🟡 good | 80–90 |
| 🟠 fair | 70–80 |
| 🔴 needs work | < 70 |

**Key API**

```python
stats = monitor.accuracy_evaluator.get_accuracy_scores()
# {"overall_accuracy": float, "median_accuracy": float, ...}

by_type = monitor.accuracy_evaluator.get_accuracy_by_type()
# {"qa": float, "code_generation": float, ...}
```

---

### Latency

**Core Gate D metric**

**Measurement**: `TaskResult.execution_time` (in seconds)

**Thresholds**

| Grade | Range (seconds) |
|-------|-----------------|
| 🟢 excellent | < 1 |
| 🟡 good | 1–3 |
| 🟠 fair | 3–5 |
| 🔴 slow | ≥ 5 |

**Key API**

```python
stats = monitor.latency_tracker.get_latency_stats()
# {"p50": float, "p95": float, "p99": float, "mean": float, "sla_compliance_rate": float}

# TTFT (Time-To-First-Token) — streaming agents only (v0.7.2+)
monitor.latency_tracker.track_ttft(task_id, ttft_seconds=0.3)
ttft_stats = monitor.latency_tracker.get_ttft_stats()
# {"mean_ttft": float, "p50_ttft": float, "p95_ttft": float}
```

> With the decorator approach, TTFT is recorded automatically at the point the generator function yields its first chunk.

---

### Token Economy

**Core Gate D metric**

**Formula**

```
Cost = (input_tokens × input_price + output_tokens × output_price) / 1000
```

**Configuration**

```python
monitor = PerformanceMonitor(
    pricing={
        "input": 0.00005,   # GPT-5-nano: $0.05/1M tokens
        "output": 0.0006,
    }
)
monitor.token_tracker.update_pricing({"input": 0.003, "output": 0.015})
```

**Thresholds (cost per task)**

| Grade | Range |
|-------|-------|
| 🟢 efficient | < $0.01 |
| 🟡 fair | $0.01–$0.05 |
| 🔴 inefficient | ≥ $0.05 |

**Key API**

```python
stats = monitor.token_tracker.get_usage_stats()
# {"total_tokens": int, "avg_tokens_per_task": float, "estimated_cost": float, ...}
```

---

### Tool Call Efficiency

**Gate B · F related metric**

**Formula**

```
Tool Efficiency = 100 - waste_rate × 100

waste_rate = (redundant_calls + failed_calls) / total_calls
```

Duplicate judgment: the `(tool_name, json.dumps(parameters, sort_keys=True))` pair is identical.

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | ≥ 90 |
| 🟡 good | 80–90 |
| 🟠 fair | 70–80 |
| 🔴 inefficient | < 70 |

**Key API**

```python
metrics = monitor.tool_analyzer.analyze_execution(task_id, tool_calls)
# {"total_calls": int, "unique_tools": int, "redundant_calls": int,
#  "failed_calls": int, "efficiency_score": float}

stats = monitor.tool_analyzer.get_efficiency_stats()
# {"avg_efficiency_score": float, "redundancy_rate": float, "failure_rate": float}
```

---

### Retry & Error Recovery

**Core Gate C metric**

**Formula**

```
retry_rate         = retried_tasks / total_tasks × 100
retry_success_rate = succeeded_after_retry / retried_tasks × 100
```

**Thresholds** (retry success rate %)

| Grade | Range |
|-------|-------|
| 🟢 excellent | ≥ 80 |
| 🟡 good | 60–80 |
| 🟠 fair | 40–60 |
| 🔴 poor | < 40 |

**Key API**

```python
stats = monitor.retry_tracker.get_retry_statistics()
# {"retry_rate": float, "retry_success_rate": float, "avg_retry_count": float}
```

---

### Tool Selection Accuracy

**Core Gate F metric**

**Formula (F1-based)**

```python
expected_set = set(expected_tools)
actual_set   = set(actual_tools)

TP = len(expected_set & actual_set)
FP = len(actual_set - expected_set)
FN = len(expected_set - actual_set)

precision = TP / len(actual_set)    if actual_set    else 0
recall    = TP / len(expected_set)  if expected_set  else 0
f1        = 2 * precision * recall / (precision + recall) if (precision+recall) > 0 else 0

accuracy  = f1 * 100  # %
```

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | ≥ 90 |
| 🟡 good | 80–90 |
| 🟠 fair | 70–80 |
| 🔴 needs work | < 70 |

**Key API**

```python
result = monitor.tool_selection_tracker.evaluate_selection(
    task_id="task_001",
    expected_tools=["search", "calculator"],
    actual_tools=["search"],
)
# {"precision": float, "recall": float, "f1_score": float, "accuracy": float}

stats = monitor.tool_selection_tracker.get_accuracy_stats()
# {"avg_accuracy": float, "avg_precision": float, "avg_recall": float}
```

---

### Agent Coordination

**Core Gate F metric**

**Formula**

```
Coordination Score = success_rate×0.5 + diversity_score×0.3 + balance_score×0.2

success_rate    = successful interactions / total interactions × 100
diversity_score = min(distinct agent count / 5, 1.0) × 10
balance_score   = number of interaction types / 3 × 10
```

Allowed interaction_type values: `delegation`, `communication`, `collaboration`

**Thresholds (0–10)**

| Grade | Range |
|-------|-------|
| 🟢 excellent | ≥ 8 |
| 🟡 good | 6–8 |
| 🟠 fair | 4–6 |
| 🔴 needs work | < 4 |

**Key API**

```python
monitor.agent_coordination_tracker.track_interaction(
    task_id, from_agent, to_agent,
    interaction_type="delegation", success=True,
)
score = monitor.agent_coordination_tracker.calculate_coordination_score()
# {"score": float(0–10), "success_rate": float, "total_interactions": int}
```

---

### Workflow Execution

**Core Gate F metric**

**Formula**

```
step_success_rate = successful steps / total steps × 100
task_success_rate = tasks where all steps succeeded / total tasks × 100
```

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | ≥ 90 |
| 🟡 good | 80–90 |
| 🟠 fair | 70–80 |
| 🔴 needs work | < 70 |

**Key API**

```python
monitor.workflow_tracker.track_step(
    task_id, step_name="retrieve", step_type="node",
    success=True, execution_time=0.5, framework="langgraph",
)
stats = monitor.workflow_tracker.calculate_execution_success_rate(task_id="t1")
# {"step_success_rate": float, "task_success_rate": float,
#  "total_steps": int, "avg_steps_per_task": float}

efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
# LangGraph only
```

---

### Response Quality

**Core Gate G metric**

**5-dimension evaluation (each 0–5)**

| Dimension | Weight | Method |
|-----------|--------|--------|
| Relevance | 25% | request words ∩ response words / request word count × 5 |
| Completeness | 25% | share of expected_elements present in the response × 5 |
| Accuracy | 20% | default 4.0 (needs ground_truth-based feedback) |
| Clarity | 15% | based on word count + presence of structure |
| Usefulness | 15% | default 4.0 |

**Formula**: `Quality Score = Σ(dimension_score × weight)`, range 0–5

**Thresholds**

| Grade | Range (0–5) |
|-------|-------------|
| 🟢 A (excellent) | ≥ 4.5 |
| 🟡 B (good) | 4.0–4.5 |
| 🟠 C (fair) | 3.5–4.0 |
| 🟠 D (weak) | 3.0–3.5 |
| 🔴 F (needs work) | < 3.0 |

**Key API**

```python
stats = monitor.quality_evaluator.get_quality_metrics()
# {"avg_total_score": float, "grade_distribution": {"A":n,...}, "dimension_averages": {...}}
```

---

### Hallucination Rate (rule-based)

**Gate C + G related metric** — when enabled, `1 − hall_rate` contributes to both Gate C `_rel_vals` (reliability) and Gate G `_obs_vals` (observability). If the actual detection count (`_detections`) is 0, it contributes to neither gate.

Activation: `PerformanceMonitor(enable_hallucination_detection=True)`

**Detection methods**

| Method | Condition | Severity |
|--------|-----------|----------|
| Unsupported Claim | context-word overlap of a response sentence < 30% | Medium |
| Numerical Inconsistency | a number in the response is not in the context | High |

**Formula**

```
Hallucination Rate = tasks flagged for hallucination / tasks with context × 100
```

**Thresholds**

| Grade | Range (%) |
|-------|-----------|
| 🟢 excellent | < 1 |
| 🟡 good | 1–5 |
| 🟠 fair | 5–10 |
| 🔴 risky | ≥ 10 |

> Rule-based detection: 70–80% accuracy, free, < 5ms overhead.
> Different from the L3 DeepEval Hallucination Score (LLM-based, 90–95%).

**Key API**

```python
stats = monitor.hallucination_detector.get_hallucination_rate()
# {"overall_rate": float(0–1), "tasks_with_hallucinations": int, ...}
```

---

### The 5 security metrics (Gate E)

Activation: `PerformanceMonitor(enable_security_metrics=True)` — overhead ~5–15ms

**Input Sanitization — detection patterns**

| Attack type | Example | Severity |
|-------------|---------|----------|
| SQL Injection | `'; DROP TABLE`, `UNION SELECT` | 🔴 Critical |
| Command Injection | `rm -rf`, `$(cmd)` | 🔴 Critical |
| Path Traversal | `../`, `/etc/passwd` | 🟠 High |
| XSS | `<script>`, `javascript:` | 🟠 High |
| Prompt Injection | `ignore previous instructions` | 🔴 Critical |

```python
result = monitor.input_sanitizer.evaluate_input(task_id, input_text)
# {"has_sql_injection": bool, "has_prompt_injection": bool,
#  "risk_level": str, "threat_count": int}
stats = monitor.input_sanitizer.get_security_stats()
# {"threat_rate": float, "sql_injection_attempts": int, ...}
```

**Output Leakage — detection targets**

| Leak type | Severity |
|-----------|----------|
| API Key (`sk-...`, `AIza...`) | 🔴 Critical |
| Password / Credit Card (Luhn) | 🔴 Critical |
| Email / Phone / SSN | 🟠 High |
| Private IP / File Path | 🟡 Medium |

```python
result = monitor.output_leakage_detector.detect_leakage(task_id, output_text)
# {"contains_api_key": bool, "leakage_count": int, "severity": str}
stats = monitor.output_leakage_detector.get_leakage_stats()
# {"leakage_rate": float, "critical_severity_count": int, ...}
```

**Tool Authorization**

```python
monitor = PerformanceMonitor(
    enable_security_metrics=True,
    security_config={"allowed_tools": ["search", "read"], "restricted_tools": ["delete"]},
)
result = monitor.tool_authorizer.track_tool_call(task_id, tool_name, parameters)
# {"is_authorized": bool, "is_restricted": bool, "privilege_level": "read|write|execute|admin"}
stats = monitor.tool_authorizer.get_compliance_stats()
# {"compliance_rate": float, "unauthorized_calls": int, "violation_rate": float}
```

**Privilege Escalation**

```python
result = monitor.privilege_escalation_detector.analyze_privilege_chain(
    task_id,
    tool_calls=[
        {"tool_name": "read_file", "privilege_level": "read"},
        {"tool_name": "exec_cmd", "privilege_level": "execute"},
        {"tool_name": "read_admin", "privilege_level": "admin"},
    ],
)
# {"escalation_detected": bool, "risk_score": int(0–10), "escalation_path": [...]}
stats = monitor.privilege_escalation_detector.get_escalation_stats()
# {"escalation_rate": float, "avg_risk_score": float, "high_risk_events": int}
```

**Tool Chain Attack — detection types**

| Attack type | Example sequence |
|-------------|------------------|
| Data Exfiltration | `read_database → encode → http_post` |
| Lateral Movement | `get_credentials → ssh_connect → execute_remote` |
| Persistence | `write_cron → create_service → restart` |
| Defense Evasion | `disable_logging → clear_history → delete_logs` |

```python
result = monitor.tool_chain_attack_detector.analyze_tool_chain(
    task_id, tool_sequence=["read_database", "encode", "http_post"]
)
# {"is_suspicious_chain": bool, "attack_types": {...}, "threat_level": str}
stats = monitor.tool_chain_attack_detector.get_attack_stats()
# {"detection_rate": float, "data_exfiltration_detected": int, ...}
```

---

## Reading metrics from the report

```python
report = monitor.generate_report()
d = report.to_dict()

# Gate A — Goal Achievement
d["tcr_data"]["success_rate"]               # float (0–1)
d["accuracy_data"]["overall_accuracy"]      # float (0–100)

# Gate C — Reliability
d["retry_data"]["retry_success_rate"]       # float (0–100)

# Gate D — Performance Contract
d["latency_data"]["p95"]                    # float (seconds)
d["latency_data"]["sla_compliance_rate"]    # float (0–1)
d["token_data"]["estimated_cost"]           # float ($)

# Gate E — Security Boundary
d["security_metrics"]["input_security"]["threat_rate"]           # float (0–100)
d["security_metrics"]["output_leakage"]["leakage_rate"]          # float (0–100)
d["security_metrics"]["authorization"]["compliance_rate"]        # float (0–100)
d["security_metrics"]["privilege_escalation"]["escalation_rate"] # float (0–100)
d["security_metrics"]["attack_detection"]["detection_rate"]      # float (0–100)

# Gate F — Multi-Agent
d["tool_efficiency"]                                 # float (0–100)
d["tool_selection_accuracy"]                         # float (0–100)
d["coordination_score"]                              # float (0–10)
d["workflow_execution"]["step_success_rate"]         # float (0–100)

# Gate G — Observability
d["quality_data"]["avg_total_score"]        # float (0–5)
d["hallucination_data"]["overall_rate"]     # float (0–1)
```

---

## Decorator × metric activation map

### Metric × decorator support matrix

| Metric | `@agent_eval` | `@batch_eval` | `@conversation_eval` | Activation |
|---|:---:|:---:|:---:|---|
| **Gate A — Goal Achievement** | | | | |
| TCR | ✅ auto | ✅ auto | ✅ auto | always (`completion_fn` optional) |
| Accuracy | ✅ auto | ✅ auto | ✅ auto | when `ground_truth_arg` is present |
| Response Quality (5 dims) | ✅ auto | ✅ auto | ✅ auto | when response + question are present |
| **Gate B — Behavioral Integrity** | | | | |
| Tool Call Efficiency | ✅ auto | ✅ auto | ❌ | `framework=` adapter or EvalMetadata.tool_calls |
| **Gate C — Reliability** | | | | |
| Retry & Error Recovery | ✅ `retry=RetryConfig(max=N)` | ❌ | ❌ | `RetryConfig(max>1)` + actual retries |
| Hallucination Rate (C) | ✅ `rag_mode=True` | ✅ `context_arg` given | ❌ | `enable_hallucination_detection=True` + context present → contributes to Gate C |
| **Gate D — Performance Contract** | | | | |
| Latency (p50/p95/p99) | ✅ auto | ✅ auto | ✅ auto | always (execution time measured automatically) |
| TTFT | ✅ generator | ✅ `streaming_mode` | ❌ | generator return or streaming mode |
| Token Economy | ✅ auto | ✅ auto | ❌ | `framework=` adapter or EvalMetadata |
| **Gate E — Security Boundary** | | | | |
| Input Sanitization | ✅ `security=SecurityConfig()` | ❌ | ❌ | `security=SecurityConfig()` |
| Output Leakage | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| Tool Authorization | ✅ `security=SecurityConfig()` + `allowed_tools` | ❌ | ❌ | same + whitelist |
| Privilege Escalation | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| Tool Chain Attack | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| **Gate F — Multi-Agent** | | | | |
| Tool Selection F1 | ✅ `expected_tools_arg` | ✅ `expected_tools_arg` | ❌ | expected_tools + tool_calls together |
| Agent Coordination | ✅ `framework="crewai/autogen"` | ❌ | ❌ | CrewAI/AutoGen adapter or EvalMetadata |
| Workflow Execution | ✅ `framework="langchain/langgraph"` | ❌ | ❌ | LangChain/LangGraph adapter |
| **Gate G — Observability** | | | | |
| Hallucination Rate (G) | ✅ `rag_mode=True` | ✅ `context_arg` given | ❌ | context + `enable_hallucination_detection=True` — also contributes to Gate C |
| **L3 / LLM Judge** | | | | |
| LLM Judge (5 dims) | ✅ `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | ships in the base install |
| Faithfulness | ✅ `rag_mode` + `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | added automatically when context is present |
| G-Eval custom criteria | ✅ `llm_judge=LLMJudgeConfig(criteria=[...])` | ❌ | ❌ | when criteria are given |
| **Conversation metrics** | | | | |
| Context Retention | ❌ | ❌ | ✅ auto | on session flush |
| Topic Coherence | ❌ | ❌ | ✅ auto | on session flush |
| Progressive Depth | ❌ | ❌ | ✅ auto | on session flush |
| Session Completion | ❌ | ❌ | ✅ auto | on session flush |
| Per-turn Score | ❌ | ❌ | ✅ `turn_score_fn` | when `turn_score_fn` is given |

### Harness Config activation (33)

| Parameter | Gate | What it measures |
|---|---|---|
| `instructions=InstructionConfig(...)` | A | instruction adherence · drift detection |
| `goal_alignment=GoalAlignmentConfig(...)` | A | goal-alignment score |
| `plan_tracking=PlanConfig(...)` | A | plan coherence · step completion rate |
| `subtask_tracking=SubtaskConfig(...)` | A | subtask completion rate |
| `context_retention=ContextRetentionConfig(...)` | A | conversational context retention |
| `knowledge_retention=KnowledgeRetentionConfig(...)` | A | knowledge retention · utilization |
| `loop_detection=LoopDetectionConfig(...)` | B | repetitive-loop detection |
| `scope=ScopeConfig(...)` | B | scope-drift detection |
| `tool_parameter_safety=ToolParameterSafetyConfig(...)` | B | parameter safety |
| `context_window=ContextWindowConfig(...)` | B | context-window efficiency |
| `state_consistency=StateConsistencyConfig(...)` | B | pre/post-run state consistency |
| `deadlock=DeadlockConfig(...)` | B | deadlock · circular-delegation · starvation detection |
| `reproducibility=ReproducibilityConfig(...)` | C | consistency across repeated runs |
| `fault_tolerance=FaultToleranceConfig(...)` | C | post-error recovery rate |
| `graceful_degradation=GracefulDegradationConfig(...)` | C | quality floor |
| `retry_consistency=RetryConsistencyConfig(...)` | C | consistency across retries |
| `idempotency=IdempotencyConfig(...)` | C | idempotency |
| `sla=SLAConfig(...)` | D | SLA response time |
| `efficiency=EfficiencyConfig(...)` | D | token efficiency |
| `resource_budget=ResourceBudgetConfig(...)` | D | token budget · cost cap |
| `TTFTVariabilityConfig` (monitor auto) | D | TTFT standard deviation |
| `CostPredictabilityConfig` (monitor auto) | D | cost predictability |
| `threat_severity=ThreatSeverityConfig(...)` | E | threat-severity classification |
| `compliance=ComplianceConfig(...)` | E | compliance patterns |
| `threat_response=ThreatResponseConfig(...)` | E | verify post-detection response |
| `consensus=ConsensusConfig(...)` | F | inter-agent agreement rate |
| `propagation=PropagationConfig(...)` | F | information-propagation accuracy |
| `agent_role=AgentRoleConfig(...)` | F | role-adherence rate |
| `conflict_resolution=ConflictResolutionConfig(...)` | F | conflict resolution |
| `explainability=ExplainabilityConfig(...)` | G | explainability |
| `observability=ObservabilityConfig(...)` | G | internal-state exposure |
| `error_diagnosis=ErrorDiagnosisConfig(...)` | G | error-diagnosis accuracy |
| `latency_attribution=LatencyAttributionConfig(...)` | G | latency root-cause analysis |

### Parameter → metric activation summary

| Parameter | Metric it activates |
|---|---|
| `ground_truth_arg` | Accuracy |
| `rag_mode=True` | Hallucination Rate + context_arg set automatically |
| `context_arg` | Hallucination Rate (paired with `enable_hallucination_detection=True`) |
| `expected_tools_arg` | Tool Selection F1 |
| `framework="langchain/langgraph"` | Tool Call Efficiency, Workflow Execution |
| `framework="crewai/autogen"` | Agent Coordination |
| `framework="openai/anthropic"` | Token Economy (exact token / cache cost) |
| `security=SecurityConfig()` | all 5 security metrics |
| `allowed_tools=[...]` | Tool Authorization (adds a whitelist basis) |
| `llm_judge=LLMJudgeConfig()` | LLMJudge 5 dimensions |
| `rag_mode=True` + `llm_judge=LLMJudgeConfig()` | + Faithfulness |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | + G-Eval custom-criteria scores |
| `retry=RetryConfig(max=N)` (N>1) | Retry & Error Recovery |
| `score_fn` | Accuracy (custom computation) |
| `completion_fn` | TCR (custom computation) |
| Harness Config parameters (33) | the corresponding Gate A–G metric (see the table above) |

---

> Full hands-on example: `Evaluator_Examples/ch03_harness_basics.py`
> API signature detail: `Docs/08_API_REFERENCE.md`
