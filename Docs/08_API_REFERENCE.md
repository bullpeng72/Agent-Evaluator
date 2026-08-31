# API Reference

Full API documentation for Agent Evaluator v1.0.0.

---

## Version info

- **Version:** v1.0.0
- **Python:** 3.8+
- **Last updated:** 2026-08-31

---

## Table of Contents

1. [Quick start (4 patterns)](#1-quick-start)
2. [Core class API](#2-core-class-api)
3. [Decorator API](#3-decorator-api)
4. [EvalMetadata & get_eval_ctx()](#4-evalmetadata--get_eval_ctx)
5. [Context managers (evaluation_session)](#5-context-managers)
6. [Framework integration](#6-framework-integration)
7. [Security API](#7-security-api)
8. [ConversationSession](#8-conversationsession)
9. [LLMJudge](#9-llmjudge)
10. [Anomaly detection / streaming / alerts](#10-anomaly-detection--streaming--alerts)
11. [Exception classes](#11-exception-classes)
12. [Layer 2 Agentic trackers](#12-layer-2-agentic-trackers)
13. [Hybrid evaluation (Layer 3)](#13-hybrid-evaluation-layer-3)
14. [RCA diagnosis + recommendation history (agent_evaluator.rca / ontology)](#14-rca-diagnosis--recommendation-history-agent_evaluatorrca--ontology)
15. [CLI reference](#15-cli-reference)

---

## 1. Quick start

### Pattern 1 — @agent_eval decorator (recommended)

The standard, most flexible style, with fine-grained control.

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Recorded automatically on each call
agent("What is the capital of Korea?", ground_truth="Seoul")
```

### Pattern 2 — @conversation_eval (multi-turn)

Automatically evaluates the context-retention rate of a multi-turn conversation.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid")
def chat(msg: str, sid: str):
    return chatbot.chat(msg)

chat("Hi", sid="u1")
chat("What's the weather today?", sid="u1")
flush_conversation("u1")
```

### Pattern 3 — @batch_eval (batch processing)

Evaluates a list of questions at once and records the results automatically.

```python
from agent_evaluator.decorators import batch_eval

@batch_eval(monitor, task_type="qa", task_id_prefix="qa_batch")
def qa_batch(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

qa_batch(
    questions=["What is the capital of Korea?", "Who created Python?"],
    ground_truths=["Seoul", "Guido van Rossum"],
)
# → 2 TaskResults are recorded on the monitor
```

### Pattern 4 — QuickEval (convenience factory)

Use it when you want to finish configuration in one line.

```python
from agent_evaluator import QuickEval
eval = QuickEval("results/")

@eval.qa
def agent(q): ...
```

---

## 2. Core class API

### PerformanceMonitor

The central orchestrator. Configures every tracker internally and aggregates the evaluation results.

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",                # output directory (default: "results/")
    enable_hallucination_detection=False, # enable hallucination detection (default: False)
    enable_security_metrics=False,        # enable security metrics (default: False)
    auto_save=False,                      # save automatically every N records (default: False)
    auto_save_interval=10,                # auto-save interval (default: 10)
    auto_save_filename="auto_save",       # auto-save filename
)
```

#### Key methods

| Method | Returns | Description |
|--------|---------|-------------|
| `record_task(result)` | `self` | records a TaskResult. Supports method chaining |
| `generate_report()` | `EvaluationReport` | produces a report from the accumulated metrics |
| `save_to_file(filename, baseline_path=None)` | `str` (path of the saved JSON) | saves JSON + HTML files. With `baseline_path`, the HTML's Gate RCA diagnosis section works in regression-based mode |
| `register_gate(gate_id, compute_fn)` | `None` | registers an independent custom Gate plugin — `compute_fn(tasks, min_samples) -> dict` |
| `compare_with_thresholds()` | `dict` | pass/fail against thresholds (set via `monitor.thresholds = {...}`) |
| `reset(keep_config=True)` | `None` | clears the accumulated tasks |
| `snapshot()` | `dict` | snapshot of the current state |
| `compare_with_snapshot(snap)` | `dict` | compares a snapshot against the current metrics |
| `restore_from_snapshot(snap)` | `None` | restores from a snapshot |
| `clone()` | `PerformanceMonitor` | clones the configuration (without tasks) |
| `merge(other)` | `None` | merges another monitor's tasks |
| `filter_tasks(**kwargs)` | `list` | conditional task filtering |
| `aggregate_metrics(since, until, by)` | `dict` | aggregate metrics by period/criterion |
| `get_timeseries_metrics(metric, granularity)` | `list` | query a time-series metric |
| `export_to_dataframe(include_fields)` | `DataFrame` | export as a pandas DataFrame |
| `export_to_wandb()` | `None` | export to Weights & Biases (requires wandb) |
| `export_to_mlflow()` | `None` | export to MLflow (requires mlflow) |
| `compare(other)` | `dict` | compare metrics against another monitor |
| `analyze()` | `dict` | bottleneck analysis + optimization recommendations |
| `rehydrate_from_storage(path, limit=None)` *(v0.9.8+)* | `int` | replays a SQLite (`storage_backend="sqlite"`) history through a `record_task()` loop — keeps the `AnomalyDetector` baseline alive across a process restart. Returns the number of replayed tasks |
| `agent_version` *(property)* | `Optional[str]` | read-only — the resolved value passed to the constructor (`"auto"` → auto-tag result; a literal string → as is; unset → `None`). No setter |
| `iteration_note` *(constructor parameter)* | `Optional[str]` | attaches a human-readable one-line note to the opaque dirty-hash tag of `agent_version="auto"`. Carried verbatim in `extra_metrics.lineage.iteration_note`, no new computation. Rendered alongside `agent_version` in the dashboard File Compare's Metric Comparison table. Omitting it (default `None`) causes no regression |

> **Caution with `rehydrate_from_storage()`**: replaying with a monitor that has `enable_llm_judge` / `enable_hallucination_detection` / `enable_security_metrics` on **re-scores** the already-scored past tasks (re-incurring cost for the LLM Judge). To reproduce the past history as is, replay with a monitor that has those flags off.

```python
# Once at process start — then start recording new traffic with monitor.record_task(...)
monitor = PerformanceMonitor(output_dir="results/", enable_anomaly_detection=True)
n = monitor.rehydrate_from_storage("results/production_sessions.db", limit=500)
```

> **`agent_version="auto"`**: auto-tags with the first 8 chars of the current git commit SHA.
> If there are uncommitted changes to tracked files (`git diff HEAD`), that diff is hashed and
> appended as a `{commit8}-dirty-{hash6}` suffix — so different code states are distinguished
> automatically even in a local dev loop that runs repeatedly without committing. If git info is
> unavailable (a non-git environment, etc.), it falls back to `None` with no exception.
>
> ```python
> monitor = PerformanceMonitor(output_dir="results/", agent_version="auto")
> monitor.agent_version  # -> "a1b2c3d4" | "a1b2c3d4-dirty-f3a91c" | None
> ```

> **`iteration_note`**: the `-dirty-<hash>` tag itself carries no meaning, so leave a
> human-readable note of what that iteration tried.
>
> ```python
> monitor = PerformanceMonitor(
>     output_dir="results/", agent_version="auto",
>     iteration_note="added an instruction to plan the steps first",
> )
> ```

#### Factory classmethods

```python
# Optimal settings for RAG evaluation (hallucination_detection on by default)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# Optimal settings for security-agent evaluation (security_metrics on by default)
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

---

### TaskResult

An immutable dataclass holding the result of a single task run (`@dataclass(frozen=True)`).

#### Required fields (11)

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | unique task identifier |
| `task_type` | `str \| TaskType` | task type (e.g. `"qa"`) |
| `success` | `bool` | whether it succeeded |
| `completion_score` | `float` | completion score (0.0–1.0) |
| `accuracy_score` | `float` | accuracy score (0.0–1.0) |
| `execution_time` | `float` | execution time (seconds) |
| `tokens_used` | `dict` | token usage `{"total": int, "input": int, "output": int}` |
| `tool_calls` | `list` | list of tool calls |
| `attempts` | `int` | number of attempts |
| `errors` | `list` | list of errors that occurred |
| `timestamp` | `datetime` | time of recording |

#### Optional fields (13)

| Field | Type | Description |
|-------|------|-------------|
| `response` | `str \| None` | agent response text |
| `question` | `str \| None` | input question |
| `ground_truth` | `str \| None` | reference answer |
| `context` | `str \| None` | RAG context |
| `framework` | `str \| None` | framework used (e.g. `"langchain"`) |
| `model_name` | `str \| None` | model used |
| `task_name` | `str \| None` | task name (optional label) |
| `has_error` | `bool` | whether an error occurred |
| `partial_reason` | `str \| None` | reason for partial completion |
| `extra` | `dict` | extra metadata |
| `agent_interactions` | `list` | list of multi-agent exchanges |
| `chain_steps` | `list` | list of chain execution steps |
| `expected_tools` | `list` | expected-tool list (for F1) |

#### Recommended creation — the create_taskresult() helper

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001",
    question="What is the capital of Korea?",
    response="It is Seoul.",
    ground_truth="Seoul",
    execution_time=1.23,
    task_type="qa",
    # optional
    tokens_used={"total": 150, "input": 50, "output": 100},
    tool_calls=[],
    context=None,
    framework="openai",
    model_name="gpt-5-nano",
)
```

`create_taskresult()` computes `accuracy_score` and `completion_score` automatically. The `success`, `attempts`, `errors`, and `timestamp` fields are also given automatic defaults.

#### Serialization / deserialization

```python
d = result.to_dict()
result2 = TaskResult.from_dict(d)       # ISO-8601 timestamp converted automatically
result3 = TaskResult.from_json(json_str)
```

---

### EvaluationReport

The immutable report object returned by `generate_report()`.

```python
report = monitor.generate_report()

# Key properties
report.task_completion_rate     # float (0–100)
report.overall_accuracy         # float (0–100)
report.average_latency          # float (seconds)
report.total_tasks              # int
report.successful_tasks         # int
report.hallucination_rate       # float | None (when enable_hallucination_detection=True)
report.security_incidents       # dict | None (when enable_security_metrics=True)

# Serialization / deserialization
d = report.to_dict()
report2 = EvaluationReport.from_dict(d)
report3 = EvaluationReport.from_json(json_str)

# Equality (semantic comparison excluding timestamp)
assert report == report2
```

---

### TaskType (Enum)

```python
from agent_evaluator import TaskType

TaskType.QA                    # "qa"
TaskType.CODE_GENERATION       # "code_generation"
TaskType.DATA_ANALYSIS         # "data_analysis"
TaskType.DOCUMENT_CREATION     # "document_creation"
TaskType.INFORMATION_RETRIEVAL # "information_retrieval"
TaskType.REASONING             # "reasoning"
TaskType.CREATIVE              # "creative"
TaskType.CODING                # "coding"
TaskType.PLANNING              # "planning"
TaskType.TOOL_USE              # "tool_use"
```

The `task_type` parameter accepts an Enum or a string interchangeably (`TaskType.QA` == `"qa"`).

---

## 3. Decorator API

### agent_eval

The most flexible single-function evaluation decorator. Converts the function's result into a TaskResult automatically and records it on the monitor.

```python
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    task_type="qa",                  # required. TaskType Enum or string
    question_arg="question",         # name of the question parameter (default: "question")
    ground_truth_arg="ground_truth", # name of the reference-answer parameter (default: "ground_truth")
    context_arg=None,                # name of the RAG context parameter
    framework=None,                  # "langchain"|"openai"|"anthropic"|... (24)
    model_name=None,                 # model name
    task_id_prefix=None,             # task_id prefix
    enabled=True,                    # whether the decorator is enabled
    rag_mode=False,                  # auto-sets context_arg + hallucination + IR
    security=None,                   # temporarily enable security metrics (SecurityConfig())
    llm_judge=None,                  # LLM Judge settings (LLMJudgeConfig(model=..., criteria=[...]))
    enable_anomaly_detection=False,  # temporarily enable anomaly detection
    enable_hallucination_detection=False,  # temporarily enable hallucination detection
    alert_rules=[],                  # list of SimpleTaskAlertRule
    flush_every=0,                   # auto-run save_to_file() every N calls (0 = disabled)
    retry=None,                      # retry settings (RetryConfig(max=N, delay=X, backoff=Y))
    on_record=None,                  # TaskResult post-processing callback (TaskResult → TaskResult)
    sample_rate=1.0,                 # sampling rate (0.0–1.0)
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

`rag_mode=True` shortcut example:

```python
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

---

### QuickEval

A one-stop facade that starts `PerformanceMonitor` + `EvalDecorator` in one line.

```python
from agent_evaluator import QuickEval

# Basic
eval = QuickEval("results/")

# Factory methods
eval = QuickEval.for_rag("results/")
eval = QuickEval.for_security("results/")
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
eval = QuickEval.for_regression_eval("results/", baseline_file="baseline.json")

# Load from a YAML config file
eval = QuickEval.from_config("eval_config.yaml")
```

#### Shortcut decorators (properties)

```python
@eval.qa           # task_type="qa"
@eval.rag          # task_type="information_retrieval" + context_arg="context"
@eval.tool_use     # task_type="tool_use"
@eval.code         # task_type="code_generation"
@eval.reasoning    # task_type="reasoning"
@eval.planning     # task_type="planning"
@eval.data_analysis  # task_type="data_analysis"
@eval.creative     # task_type="creative"
@eval.chat         # task_type="qa" (conversational)
@eval.multi_agent  # task_type="tool_use" + multi-agent settings
@eval.security     # security=SecurityConfig()
def agent(question: str, ground_truth: str = "") -> str:
    ...
```

Direct call (custom parameters):

```python
@eval(task_type="qa", framework="anthropic", flush_every=10)
def agent(question: str, ground_truth: str = "") -> str:
    ...
```

#### Key methods

| Method | Description |
|--------|-------------|
| `save()` | saves `quickeval.json` + `quickeval.html` |
| `gate(tcr=None, accuracy=None, quality=None, hallucination=None)` | `sys.exit(1)` if a threshold is missed |
| `summary()` | dict — `task_completion_rate`, `overall_accuracy`, `p95_latency`, `total_cost_usd`, `hallucination_rate`, etc. |
| `compare(other)` | compares the metrics of two QuickEval instances |
| `ab_test(other)` | A/B comparison + t-test p-value (requires scipy) |
| `generate_gate_config(filepath)` | auto-suggests 95% thresholds from the current metrics → saves JSON |
| `export_to_dataframe()` | export as a pandas DataFrame |
| `replay(results_file)` | reloads existing JSON results |
| `watch(directory, callback)` | watches a directory + auto-replays new JSON |

#### auto_save option

```python
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
# save_to_file() is called automatically every 10 records
```

---

### batch_eval

A decorator that takes list inputs and processes them in bulk. It zips `questions[i]` / `ground_truths[i]` / `responses[i]` and records each as an independent `TaskResult`.

```python
from agent_evaluator.decorators import batch_eval

@batch_eval(
    monitor,
    task_type="qa",
    # ── input/output parameter names ─────────────────────────
    questions_arg="questions",        # name of the questions-list parameter (default: "questions")
    ground_truths_arg="ground_truths",# name of the reference-answers-list parameter (default: "ground_truths")
    contexts_arg=None,                # name of the RAG contexts-list parameter (for RAG evaluation)
    expected_tools_arg=None,          # name of the expected_tools-list parameter (for Tool F1)
    # ── task_id generation ───────────────────────────────────
    task_id_prefix="batch",           # prefix for auto-generated task_id → {prefix}_{uuid8}_{i:03d}
    task_id_fn=None,                  # custom task_id generator (index, question, gt) -> str
    # ── framework / model ────────────────────────────────────
    framework="native",               # framework identifier (24 supported)
    model_name="",                    # LLM model name
    # ── custom scoring ───────────────────────────────────────
    score_fn=None,                    # custom accuracy function (response, gt) -> float
    completion_fn=None,               # custom completion function
    # ── callbacks ────────────────────────────────────────────
    on_record=None,                   # per-item post-record callback (task_result) -> None
    on_error=None,                    # callback when the batch function raises
    on_batch_complete=None,           # callback after the whole batch (results_list) -> None
    on_batch_progress=None,           # per-item progress callback (i, total) -> None
    on_item_error=None,               # per-item error callback (exc, index, question) -> None
    # ── execution control ────────────────────────────────────
    concurrency=0,                    # >0 → run items in parallel (ThreadPool / asyncio.gather)
    item_timeout=None,                # per-item timeout (seconds)
    timeout=None,                     # whole-batch timeout (seconds)
    sample_rate=1.0,                  # fraction to evaluate (0.0–1.0)
    enabled=True,                     # if False, bypass the decorator
    # ── save / output ────────────────────────────────────────
    return_format="list",             # "list" | "dataframe"
    flush_every=None,                 # auto-run save_to_file() every N batch calls
    alert_rules=None,                 # list of SimpleTaskAlertRule
    preset=None,                      # "production"|"development"|"testing"|"canary"
    # ── optional evaluation activation ───────────────────────
    enable_hallucination_detection=False,
    enable_anomaly_detection=False,
    security=None,                    # SecurityConfig() — temporarily enable security metrics
    llm_judge=None,                   # LLMJudgeConfig(model=..., criteria=[...])
    custom_parser=None,               # custom response-parsing function
    # ── Harness Config (all 33 supported) ────────────────────
    # instructions=InstructionConfig(...), sla=SLAConfig(...), ...
)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

results = batch_agent(questions, ground_truths=gts)
```

With `return_format="dataframe"`, the DataFrame includes the columns `tokens_total`, `tokens_input`, `tokens_output`, `framework`, `tool_call_count`, `has_error`, `attempts`, `timestamp`.

#### Common usage examples

```python
# RAG batch evaluation
@batch_eval(
    monitor, task_type="information_retrieval",
    contexts_arg="contexts",
    enable_hallucination_detection=True,
)
def rag_batch(questions, contexts=None, ground_truths=None):
    return [rag_chain.invoke({"question": q, "context": c})
            for q, c in zip(questions, contexts)]

# Parallel execution (concurrency=4 → a 4-thread ThreadPool)
@batch_eval(monitor, task_type="qa", concurrency=4, item_timeout=10.0)
def fast_batch(questions, ground_truths=None):
    return [llm.invoke(q) for q in questions]

# LLM Judge + batch save
@batch_eval(
    monitor, task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-haiku-4-5-20251001"),
    flush_every=5,
)
def judged_batch(questions, ground_truths=None):
    return [llm.invoke(q) for q in questions]
```

---

### eval_context

A context-manager-form evaluation decorator. Suited to external functions or complex flows.

```python
from agent_evaluator.decorators import eval_context

with eval_context(
    monitor,
    task_type="qa",
    question="What is the capital of Korea?",
    ground_truth="Seoul",
    timeout=30.0,            # timeout (seconds)
    auto_task_id=True,       # auto-generate task_id
) as ctx:
    ctx.response = external_agent(ctx.question)
    ctx.tokens_used = {"total": 100, "input": 30, "output": 70}
    ctx.tool_calls = [{"tool_name": "search", "success": True}]
    ctx.chunk_step("retrieval", success=True)  # record a streaming-chunk step
```

`ctx.depth` reports the nesting depth. The maximum nesting depth is limited by `eval_context.MAX_NESTING_DEPTH`.

---

### conversation_eval

The multi-turn conversation evaluation decorator.

```python
from agent_evaluator.decorators import conversation_eval

@conversation_eval(
    monitor,
    session_id_arg="session_id",             # name of the session_id parameter
    max_turns_exceeded_action="flush",       # "flush"|"warn"|"error"
    flush_every=0,
    on_session_timeout=None,                 # session-timeout callback
    on_turn=None,                            # per-turn callback (session_id, user, response, metadata)
    session_score_fn=None,                   # session-score function override
    turn_score_fn=None,                      # per-turn score function override
)
def chat_agent(message: str, session_id: str = "s1") -> str:
    return chat_model.invoke(message)
```

Async generators are supported too.

---

### EvalDecorator (instance mode)

The class used internally by `QuickEval`. To use it directly:

```python
from agent_evaluator.decorators import EvalDecorator

decorator = EvalDecorator(
    monitor,
    task_type="qa",
    rag_mode=False,
    security=None,
    llm_judge=None,
    enable_anomaly_detection=False,
    enable_hallucination_detection=False,
)

@decorator.qa           # task_type="qa"
@decorator.tool_use     # task_type="tool_use"
@decorator.rag          # task_type="information_retrieval"
@decorator.secure       # security=SecurityConfig()
def agent(question: str, ground_truth: str = "") -> str:
    ...

# batch and context modes
@decorator.batch(shuffle=True)
def batch_fn(questions, ground_truths=None): ...

with decorator.context("qa", question="question") as ctx:
    ctx.response = external_fn(ctx.question)
```

---

## 4. EvalMetadata & get_eval_ctx()

Two ways to inject evaluation metadata from inside the decorated function.

### Method A — get_eval_ctx() (context injection)

```python
from agent_evaluator.decorators import agent_eval, get_eval_ctx

@agent_eval(monitor, task_type="tool_use")
def tool_agent(question: str, ground_truth: str = "") -> str:
    ctx = get_eval_ctx()
    ctx.tool_calls = [
        {"tool_name": "web_search", "success": True, "duration": 0.5},
        {"tool_name": "summarize", "success": True},
    ]
    ctx.chain_steps = [
        {"step": "retrieve", "success": True},
        {"step": "generate", "success": True},
    ]
    ctx.tokens_used = {"input": 100, "output": 50, "total": 150}
    return "answer"
```

`get_eval_ctx()` returns `None` when called outside the decorator's execution stack.

### Method B — return an EvalMetadata tuple

```python
from agent_evaluator.decorators import agent_eval, EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def agent(question: str, ground_truth: str = "") -> tuple:
    meta = EvalMetadata(
        tool_calls=[{"tool_name": "search", "success": True}],
        tokens_used={"input": 80, "output": 40, "total": 120},
        chain_steps=[{"step": "search", "success": True}],
        agent_interactions=[{"from": "planner", "to": "executor"}],
        model_name="gpt-5-nano",
        framework="openai",
    )
    return "answer", meta
```

When the decorator detects that the return value is a `(str, EvalMetadata)` tuple, it splits it automatically.

---

## 5. Context managers

`evaluation_session` / `async_evaluation_session` provide automatic per-session saving.
On exit from the session block (even on an exception) they save `results/*.json + .html` automatically.

### Recommended — with the @agent_eval decorator

```python
from agent_evaluator import PerformanceMonitor, evaluation_session
from agent_evaluator.decorators import agent_eval

with evaluation_session("output_filename") as monitor:

    @agent_eval(monitor, task_type="qa")
    def my_agent(question: str, ground_truth: str = "") -> str:
        return llm.invoke(question)

    for q, gt in dataset:
        my_agent(q, ground_truth=gt)
# On session exit, results/output_filename.json + .html are saved automatically
# It is saved safely even on an exception
```

### Escape hatch — eval_context (when a decorator cannot be used)

```python
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("output_filename") as monitor:
    for q, gt in dataset:
        with eval_context(monitor, task_type="qa",
                          question=q, ground_truth=gt) as ctx:
            ctx.response = external_agent.run(q)
```

### Low-level — using create_taskresult() directly

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("output_filename") as monitor:
    for q, gt in dataset:
        result = create_taskresult(
            task_id=f"t{i}",
            question=q,
            response=agent.run(q),
            ground_truth=gt,
            execution_time=1.0,
            task_type="qa",
        )
        monitor.record_task(result)
```

### async_evaluation_session (async)

```python
from agent_evaluator import async_evaluation_session
from agent_evaluator.decorators import eval_context

async def run():
    async with async_evaluation_session("async_eval") as monitor:
        for q, gt in dataset:
            async with eval_context(monitor, task_type="qa",
                                    question=q, ground_truth=gt) as ctx:
                ctx.response = await async_agent.run(q)
```

### hybrid_evaluation_session

```python
from agent_evaluator import hybrid_evaluation_session

async with hybrid_evaluation_session("hybrid_eval") as monitor:
    ...
```

---

## 6. Framework integration

For 24 frameworks, `tool_calls`, `chain_steps`, `tokens_used`, `state_transitions`, etc. are extracted automatically from the response object.

### The framework= parameter

```python
from agent_evaluator.decorators import agent_eval

# langchain
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return lc_chain.invoke({"input": question})

# openai
@agent_eval(monitor, task_type="qa", framework="openai")
def openai_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": question}],
    )

# anthropic
@agent_eval(monitor, task_type="qa", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": question}],
    )
```

#### Supported frameworks (24)

| Group | Frameworks |
|-------|------------|
| LLM SDK | `anthropic`, `openai`, `gemini`, `cohere`, `groq`, `mistral`, `ollama`, `vllm`, `huggingface` |
| Orchestration | `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`, `smolagents`, `semantic_kernel` |
| Cloud | `vertexai`, `bedrock` |
| Search/RAG | `llamaindex`, `haystack` |
| Official agent SDKs | `openai_agents`, `google_adk`, `claude_agent_sdk` (auto-detection not supported — specify `framework=`) |

Auto-detection (`auto_detect_framework=True` is on by default):

```python
@agent_eval(monitor, task_type="qa")  # omit framework= → auto-detected from the response's attributes
def agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # openai auto-detected
```

### Framework-specific decorators

```python
from agent_evaluator.integrations import (
    langchain_eval,
    langgraph_eval,
    crewai_eval,
    autogen_eval,
    dspy_eval,
    pydanticai_eval,
)

@langchain_eval(monitor, task_type="qa")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return chain.invoke({"input": question})
```

### Querying framework metadata

```python
from agent_evaluator.decorators import get_framework_info

info = get_framework_info("langchain")
# {"extracts": ["tool_calls", "chain_steps", "tokens_used"], "description": "..."}
```

---

## 7. Security API

Security metrics are disabled by default (`enable_security_metrics=False`). There are three ways to enable them.

### Method 1 — enable permanently on PerformanceMonitor

```python
monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)
# or
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

### Method 2 — enable temporarily via SecurityConfig (decorator)

```python
from agent_evaluator.decorators import agent_eval, SecurityConfig

@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# the monitor's security setting is restored to its original value after the function returns
```

### Method 3 — standalone use

```python
from agent_evaluator.helpers.taskresult_helpers import (
    validate_input_security,
    check_output_leakage,
)

# Input-security validation
result = validate_input_security(user_input)
# returns: {"is_safe": bool, "threats": list, "risk_level": "low"|"medium"|"high"}

# Output-leakage detection
result = check_output_leakage(agent_output)
# returns: {"has_leakage": bool, "leaked_types": list}
```

### Detection patterns

Threat types detected by `InputSanitizationTracker`:

| Type | Description |
|------|-------------|
| `sql_injection` | SQL injection attempt |
| `command_injection` | system-command injection |
| `path_traversal` | directory-traversal attack |
| `xss` | cross-site scripting |
| `prompt_injection` | prompt injection |

### The 5 security trackers

| Class | What it detects |
|-------|-----------------|
| `InputSanitizationTracker` | 5 kinds of input-injection attacks |
| `OutputLeakageDetector` | leaked sensitive info — API keys, passwords, file paths, etc. |
| `ToolAuthorizationTracker` | unauthorized tool calls |
| `PrivilegeEscalationDetector` | privilege-escalation attempts |
| `ToolChainAttackDetector` | chained tool-attack patterns |

#### Key parameters (v0.8.3+)

```python
# Sampling — performance tuning in a high-traffic environment
tracker = InputSanitizationTracker(sample_rate=0.2)   # inspect only 20%
detector = OutputLeakageDetector(sample_rate=0.2)

# Customize the system-path exclusion list (OutputLeakageDetector)
detector = OutputLeakageDetector(
    excluded_unix_paths=["usr/", "bin/", "myapp/", "opt/"]  # default: 8 system prefixes
)

# sample_rate=0.0 skips everything (returns sampled_out: True)
# sample_rate=1.0 inspects everything (default)
```

---

## 8. ConversationSession

The class for multi-turn conversation evaluation.

```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn

session = ConversationSession(session_id="conv_001")
session.add_turn(user_input="Hello", agent_response="Hello!")
session.add_turn(user_input="What's the weather today?", agent_response="It's clear.")

metrics: ConversationMetrics = session.compute_metrics()
```

#### ConversationMetrics properties

| Property | Type | Description |
|----------|------|-------------|
| `turn_count` | `int` | total number of turns |
| `overall_score` | `float` | overall score (0.0–1.0) |
| `context_retention` | `float` | context-retention rate |
| `topic_coherence` | `float` | topic coherence |
| `progressive_depth` | `float` | how the conversation depth progresses |
| `session_completion` | `float` | session-completion rate |
| `avg_turn_latency` | `float \| None` | average turn latency (seconds) |
| `turn_scores` | `dict \| None` | per-turn quality scores `{turn_num: score}` |

### Integration with PerformanceMonitor (recommended)

```python
with monitor.conversation("session_001") as conv:
    for user_msg, agent_response in dialogue:
        conv.turn(
            user=user_msg,
            agent=agent_response,
            metadata={"latency": 0.3, "tokens": 120},
        )
```

---

## 9. LLMJudge

An evaluation engine where an LLM scores directly, without a ground_truth. Ships in the base install.

```python
from agent_evaluator import LLMJudge  # pip install agent-evaluator (included by default)

judge = LLMJudge(
    model="claude-haiku-4-5-20251001",   # default model (fast, low-cost)
    sample_rate=0.1,                      # score only 10%
    budget_per_day=1.0,                   # $1/day cap
    judge_criteria=["medical_accuracy"],  # G-Eval custom criteria (optional)
    # multi-model auto-escalation (v0.8.3+)
    escalation_model="claude-sonnet-4-6", # re-score when the primary score falls short
    escalation_threshold=2.5,             # escalate if overall < 2.5 (0–5 scale)
)

result = judge.judge(
    task_id="t1",
    question="What is the capital of Korea?",
    response="Seoul is the capital of Korea.",
    context="Korea is a country in East Asia.",  # RAG context (optional)
)

result["scores"]["overall"]        # float (0–5) — mean of 3 quality dimensions
result["scores"]["faithfulness"]   # float (0–5) — RAG faithfulness (when context is present)
result.get("escalated")            # True → re-scored with escalation_model
result.get("primary_overall")      # the primary score before escalation
```

#### `LLMJudge` constructor parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `None` (auto) | default scoring model |
| `sample_rate` | `0.1` | scoring rate (0.0–1.0) |
| `budget_per_day` | `None` | daily USD cap |
| `judge_criteria` | `None` | G-Eval custom-criteria list |
| `escalation_model` | `None` | higher model for re-scoring (v0.8.3+) |
| `escalation_threshold` | `2.5` | escalation trigger threshold (v0.8.3+) |
| `max_context_chars` | `4000` | context truncation limit |
| `seed` | `None` | random seed for sampling reproducibility |

### Async scoring — `ajudge()` (v0.8.3+)

A non-blocking call based on `run_in_executor`. Use it in an `asyncio` environment.

```python
import asyncio

result = asyncio.run(judge.ajudge(
    task_id="t1",
    question="What is the capital of Korea?",
    response="It is Seoul.",
))
```

### Auto-disable / recovery on consecutive errors (v0.8.3+)

After 3 consecutive API errors it auto-disables, and subsequent calls return `{"skipped": True}`.

```python
# Check whether it is disabled
judge._disabled_reason  # None = fine; str = the disable reason

# Recover
judge.reset_errors()    # reset the error counter + re-enable
```

### Environment variable — `AGENT_EVALUATOR_JUDGE_PROVIDER` (v0.8.3+)

Specifies which API provider the LLM Judge uses.

```bash
AGENT_EVALUATOR_JUDGE_PROVIDER=auto        # default: auto-select whichever provider has an API key
AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic   # prefer the Anthropic API
AGENT_EVALUATOR_JUDGE_PROVIDER=openai      # prefer the OpenAI API
```

### Pairwise (A/B) comparison — `judge_pairwise()` (v0.9.8+)

An absolute score (`judge()`) is sensitive to the scoring model's day-to-day scale drift. When you need a relative comparison — "is this prompt change better?" — `judge_pairwise()` is more stable.

```python
result = judge.judge_pairwise(
    question="What is the capital of Korea?",
    response_a="It is Seoul.",                    # e.g. the response from prompt v1
    response_b="Seoul is the capital of Korea.",  # e.g. the response from prompt v2
    context="",                                   # optional RAG context
    swap_check=True,                              # default — mitigates position bias
)
result["winner"]      # "a" | "b" | "tie"
result["reasoning"]   # the rationale from the first call (A/B in the original order)
result["swap_check"]  # True → the re-check result with A/B actually swapped
```

With `swap_check=True` (the default) it calls once more with the A/B order swapped — if both calls agree on the winner, that result stands; if they disagree (a position-bias signal), it converges to `"tie"`. To halve the cost, set `swap_check=False`. `sample_rate` sampling is not applied — this is a one-off comparison the caller explicitly requests. Budget-exceeded and consecutive-error auto-disable apply the same as `judge()`, and the verdict history accumulates in `judge.pairwise_results`, separate from `judge.results` (absolute scores).

In the dashboard, `compare_results(detailed=True, pairwise=True)` calls this method for every shared task and aggregates the `win_rate`.

### Version comparison — `prompt_version` / `agent_version` (v0.9.8+)

Tag a result file with `prompt_version` / `agent_version` and the dashboard groups and compares automatically without you picking a file `id` directly.

```python
monitor = PerformanceMonitor(output_dir="results/", prompt_version="v2-cot", agent_version="0.9.10")
```

Passing `agent_version="auto"` auto-tags from the git state — the current commit's short SHA (cached once at construction), with a `-dirty-<hash>` suffix if there are uncommitted changes to tracked files (`None` if git info is unavailable). Use `iteration_note=` to attach a human-readable one-line note to that dirty-hash tag — display only, no effect on scoring.

```bash
GET /api/results?prompt_version=v2-cot                    # filter the list by tag
GET /api/compare?group_by=prompt_version                  # auto-compare the latest file per tag (no ids= needed)
GET /api/compare?group_by=prompt_version&detailed=true&pairwise=true   # + pairwise judge_pairwise() comparison
```

The dashboard's File Compare tab exposes this API directly — the **Group by** dropdown (`prompt_version` / `agent_version`), the **⚖️ Pairwise Judge** sub-tab that appears when two files are selected, and the **📄 Export HTML** button that downloads the comparison as is.

### Integration with QuickEval

```python
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### Integration with agent_eval

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"))
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 10. Anomaly detection / streaming / alerts

### AnomalyDetector

Detects 6 kinds of anomaly with Z-score / IQR / linear regression, without an external ML library: `latency_trend` · `accuracy_drift` · `token_spike` · `error_surge` · `security_pattern` · `feedback_negativity` *(v0.9.8+, a spike in negative implicit feedback)*.

```python
from agent_evaluator import AnomalyDetector, AnomalyEvent

detector = AnomalyDetector(
    baseline_window=100,   # recent task count used to compute the baseline
    detection_window=20,   # recent task count used to compute the current value
)

events = detector.scan(monitor)
# events: List[AnomalyEvent] — reads the in-memory history of monitor.latency_tracker /
# accuracy_evaluator / token_tracker / tcr_tracker / input_sanitizer / feedback_tracker
# (cleared on restart — mitigated by rehydrate_from_storage() below)

event = events[0]
event.type          # "latency_trend" | "accuracy_drift" | "token_spike" | "error_surge" |
                    # "security_pattern" | "feedback_negativity"
event.severity      # "warning" | "critical"
event.detail        # human-readable description
event.algorithm     # "linear_regression" | "z-score" | "iqr" | "ratio"
event.detected_at

# Cause / recommendation explanation
explanation = detector.explain_event(event)
# {"metric", "value", "threshold", "deviation_pct", "severity", "explanation", "suggested_action", "detected_at"}

events_with_explanation = detector.scan_with_explain(monitor)
# [{**event.to_dict(), "explanation": {...}}, ...]
```

> **Restart-surviving baseline (v0.9.8+)**: `AnomalyDetector` only sees the in-memory history — when
> the process restarts, the baseline is empty. Calling `monitor.rehydrate_from_storage(db_path)`
> (requires the SQLite backend) before the scan replays the past history so it can be used as a
> meaningful baseline immediately. See the [PerformanceMonitor](#performancemonitor) section above.

### StreamingEvaluator

Wraps `PerformanceMonitor` and provides real-time sliding-window (1m / 5m / 1h) metrics.

```python
from agent_evaluator.streaming import StreamingEvaluator
from agent_evaluator import AlertEngine, AnomalyDetector

streaming_eval = StreamingEvaluator(
    monitor=monitor,
    flush_interval=60,          # metric aggregation / save interval (seconds)
    alert_handler=AlertEngine(),  # optional — calls evaluate() on each record()
    # v0.9.8+ — adds periodic anomaly detection onto the existing flush thread (no new thread)
    anomaly_detector=AnomalyDetector(baseline_window=200, detection_window=20),
    anomaly_scan_interval=300,  # anomaly_detector scan interval (seconds) — independent of flush_interval
    anomaly_alert_handler=None, # if set, scan results are auto-dispatched via AlertEngine.dispatch_anomaly_events()
)
streaming_eval.start()  # start the background flush (+ anomaly-detection) thread

streaming_eval.record(
    task_id="t1", success=True, execution_time=1.2, tokens_used=150,
)
stats = streaming_eval.get_stats("5m")  # count · tcr · avg_latency · p95_latency · error_rate · avg_tokens

streaming_eval.stop()
```

All three of `anomaly_detector` / `alert_handler` / `anomaly_alert_handler` must be set for an anomaly to actually result in an alert being sent (fully opt-in) — with only `anomaly_detector` set, scan results just accumulate in `streaming_eval._last_anomalies` and are not dispatched.

### AlertEngine & AlertRule

A streaming-only alert engine, lower-level than `SimpleTaskAlertRule` (below, a per-task rule for decorators). It has retry-backoff (exponential 1s/2s/4s), per-rule cooldown, and global alert-storm suppression.

```python
from agent_evaluator import AlertEngine, AlertRule
from agent_evaluator.alerts.handlers import SlackHandler

engine = AlertEngine(
    async_dispatch=False,        # True → dispatch handler.send() on a background thread
    max_alerts_per_window=None,  # global send cap within the trailing window (alert-storm suppression)
    window_seconds=60,
)
engine.add_rule(AlertRule(
    name="TCR drop",
    condition=lambda ev: ev.get_stats("5m")["tcr"] < 70,
    handler=SlackHandler(webhook_url="https://..."),
    cooldown=300,
    severity="critical",
))
engine.evaluate(streaming_eval)  # poll the StreamingEvaluator — send per rule when the condition holds
```

#### `dispatch_anomaly_events()` (v0.9.8+)

Dispatches the results of `AnomalyDetector.scan()` on a path separate from `evaluate()` — it reuses the same cooldown / retry-backoff / alert-storm infrastructure via an `AlertRule` cached per `AnomalyEvent.type`, and is decoupled from the rule list `evaluate()` iterates over, so there is no re-firing accident.

```python
events = AnomalyDetector().scan(monitor)
fired = engine.dispatch_anomaly_events(
    events,
    handler=SlackHandler(webhook_url="https://..."),
    cooldown=300,  # cooldown (seconds) for rules newly cached by this call — no effect on already-cached rules
)
# fired: List[AlertEvent] — only the events that passed the cooldown and were actually sent
```

Configuring `StreamingEvaluator(anomaly_detector=..., alert_handler=engine, anomaly_alert_handler=SlackHandler(...))` makes this call happen automatically (see the StreamingEvaluator section above).

### SimpleTaskAlertRule & AlertRuleBuilder

```python
from agent_evaluator import SimpleTaskAlertRule
from agent_evaluator.alerts import AlertRuleBuilder

# Direct creation
rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)

# Builder factory (recommended)
rule = AlertRuleBuilder.when_latency_above(
    threshold=5.0,
    handler=lambda msg, tr: print(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=60,
)
rule = AlertRuleBuilder.when_accuracy_below(threshold=0.7, handler=my_handler)
rule = AlertRuleBuilder.when_completion_below(threshold=0.8, handler=my_handler)
rule = AlertRuleBuilder.when_error(handler=my_handler)
rule = AlertRuleBuilder.when_tool_calls_exceed(max_calls=10, handler=my_handler)

# dry_run — verify the condition without running the handler
fired = rule.dry_run(task_result)  # bool

# Compound conditions
rule = SimpleTaskAlertRule(
    name="compound_check",
    compound_conditions=[
        {"field": "execution_time", "op": "gt", "value": 3.0},
        {"field": "accuracy_score", "op": "lt", "value": 0.7},
    ],
    handler=my_handler,
)

# Integration with agent_eval
@agent_eval(monitor, task_type="qa", alert_rules=[rule])
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### ImplicitFeedbackTracker

```python
from agent_evaluator import ImplicitFeedbackTracker

tracker = ImplicitFeedbackTracker()
tracker.record(
    task_id="t1",
    feedback_type="thumbs_up",    # positive: copy · thumbs_up · share · save · follow_up_depth
                                   # negative: regenerate · thumbs_down · abandon · correction
    metadata={"source": "web_ui"},  # optional
)
stats = tracker.get_stats()
# {"total": int, "positive_count": int, "negative_count": int, "positive_rate": float,
#  "negative_rate": float, "regenerate_rate": float, "abandon_rate": float,
#  "type_distribution": dict}
```

---

## 11. Exception classes

```python
from agent_evaluator.exceptions import (
    ValidationError,
    InvalidOperationError,
)

# ValidationError — input validation failed
raise ValidationError(
    "task_id must not be empty.",
    context={"task_id": "", "field": "task_id"},
)

# InvalidOperationError — an operation called in an invalid state
raise InvalidOperationError(
    "The monitor is not initialized.",
    context={"monitor_state": "uninitialized"},
)
```

Both classes have a `message` and an optional `context: dict` field.

---

## 12. Layer 2 Agentic trackers

Built into `PerformanceMonitor` and aggregated automatically on `record_task()`. When you need individual access:

### ToolCallAnalyzer

```python
from agent_evaluator import ToolCallAnalyzer

analyzer = ToolCallAnalyzer()
analyzer.record(task_result)
stats = analyzer.get_efficiency_stats()
# {"total_calls": int, "unique_tools": int, "success_rate": float,
#  "avg_calls_per_task": float, "avg_efficiency_score": float,
#  "total_redundant_calls": int, "redundancy_rate": float, "failure_rate": float}
```

### ToolSelectionTracker

```python
from agent_evaluator import ToolSelectionTracker

tracker = ToolSelectionTracker()
tracker.record(task_result)  # requires the expected_tools field
f1_stats = tracker.get_f1_by_tool()
# {"tool_name": {"precision": float, "recall": float, "f1": float}}
```

### AgentCoordinationTracker

```python
from agent_evaluator import AgentCoordinationTracker

tracker = AgentCoordinationTracker()
tracker.record(task_result)
topology = tracker.get_network_topology()
# {"pattern": "hub"|"chain"|"mesh", "density": float, "hub_nodes": list}
```

### WorkflowExecutionTracker

```python
from agent_evaluator import WorkflowExecutionTracker

tracker = WorkflowExecutionTracker()
tracker.record(task_result)
stats = tracker.get_stats()
# {"success_rate": float, "avg_steps": float, "branching_rate": float}
```

### RetryCorrectionTracker

```python
from agent_evaluator import RetryCorrectionTracker

tracker = RetryCorrectionTracker()
tracker.record(task_result)
stats = tracker.get_stats()
# {"avg_attempts": float, "retry_rate": float, "correction_success_rate": float}
```

---

## 13. Hybrid evaluation (Layer 3)

Integration with external evaluation libraries (DeepEval, Ragas). Requires the `[eval]` extra.

```python
from agent_evaluator import HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport
from agent_evaluator.decorators import agent_eval

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,
    use_ragas=True,
)

# Recommended: the decorator approach (rag_mode=True → hallucination + IR enabled automatically)
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})

# Low-level: hybrid_evaluation_session + inject ExtendedTaskResult directly
# (when you need hybrid-only fields such as retrieved_contexts)
from agent_evaluator import hybrid_evaluation_session

async with hybrid_evaluation_session("hybrid_eval") as monitor:
    from agent_evaluator import create_taskresult
    import dataclasses

    base = create_taskresult(
        task_id="hybrid_001",
        question="question",
        response="answer",
        ground_truth="reference",
        execution_time=1.5,
        task_type="information_retrieval",
    )
    result = ExtendedTaskResult(
        **dataclasses.asdict(base),
        retrieved_contexts=["context 1", "context 2"],
    )
    monitor.record_task(result)

report: HybridEvaluationReport = monitor.generate_report()
report.deepeval_scores     # DeepEval metrics
report.ragas_scores        # Ragas metrics
```

### Individual adapters

```python
from agent_evaluator.integrations.metric_adapters import (
    DeepEvalAdapter,
    RagasAdapter,
)

# DeepEval
adapter = DeepEvalAdapter()
scores = adapter.evaluate(question, response, ground_truth)

# Ragas (requires datasets>=4.0.0)
adapter = RagasAdapter()
scores = adapter.evaluate(
    questions=[...],
    responses=[...],
    contexts=[[...]],
    ground_truths=[...],
)
```

---

## 14. RCA diagnosis + recommendation history (agent_evaluator.rca / ontology)

These are submodules not in `agent_evaluator`'s top-level `__all__` — import them directly with `from agent_evaluator.rca import ...` / `from agent_evaluator.ontology import ...`. When a Gate score drops, they automate "why" in three stages (detect → attribute → cross-reference), and, after an action is applied, verify in a closed loop whether it actually improved. The HOTL principle — they present candidates and evidence only; the final judgment is the human's.

```python
from agent_evaluator.rca import diagnose

result = diagnose(
    current,                       # evaluation-result JSON dict (report.to_dict() or json.load())
    baseline=None,                 # if present, regression-based detection; if absent, falls back to detection from the current fail/warn state
    regression_threshold=0.1,      # allowed regression ratio vs the baseline
    violation_db_path=None,        # SQLite DB path — if present, stage 3 (cross-reference) calls search_violations()
    with_experiment_metadata=False,  # True → also attach the actual commit change log between baseline ↔ current, via git diff
    repo_path=".",
)
# result: {detection_mode, detected_gates, multi_gate_note, sla_shared_cause_check,
#          findings: [{gate, current_score, baseline_score, top_detail_deltas,
#                      cross_references, mast_candidates (Gate F only)}],
#          shared_cause_explanations, independently_investigate_gates, experiment_metadata}
```

Verify in a closed loop whether the applied recommendation actually improved things (the append-only JSONL pattern, like `.aoo/claims.jsonl`):

```python
from agent_evaluator.rca import verify_recommendation_outcome, record_recommendation_outcome

# When you only need a one-off verdict
verdict = verify_recommendation_outcome(
    before, after, target_gate="A", improvement_threshold=0.05,
)
# {target_gate, before_score, after_score, gate_delta, verdict: "confirmed"|"refuted"|"inconclusive", ...}

# Verdict + JSONL history logging in one call
record_recommendation_outcome(
    ".aoo/recommendation_outcomes.jsonl",
    recommendation_id="gate-a-instruction-config", target_gate="A",
    before=before, after=after, note="added InstructionConfig required_keywords",
)
```

MAST (Multi-Agent System Failure Taxonomy, Cemri et al. NeurIPS 2025) candidates for Gate F diagnosis:

```python
from agent_evaluator.ontology.mast_taxonomy import mast_failure_modes_for_gate_f_metric

modes = mast_failure_modes_for_gate_f_metric("avg_conflict_resolution")
# related MASTFailureMode(code, category, name, prevalence_pct, description, remediation, ...) candidates
```

CLI: `agent-eval diagnose`; dashboard: the 🔧 Improve tab exposes the same result.

---

## 15. CLI reference

```bash
# API-key setup wizard
agent-eval init

# Check the current configuration
agent-eval check

# FastAPI dashboard (default port 8765)
agent-eval dashboard
agent-eval dashboard --port 9000
agent-eval dashboard --watch   # watch files for changes

# Start the Phoenix monitoring server
agent-eval monitor
agent-eval monitor --port 6006
agent-eval monitor --check     # check the OTEL package install and port

# CI/CD quality gating
agent-eval gate result.json --tcr 85 --accuracy 70
agent-eval gate result.json --tcr 85 --accuracy 70 --llm-judge 3.5 --hallucination 5
agent-eval gate result.json --baseline-version v2-cot --fail-on-regression 10
agent-eval gate result.json --golden-set data/golden_datasets/golden_1.json --fail-on-golden-regression
agent-eval gate result.json --baseline-result prev_run.json --fail-on-case-regression   # exit 4: a case that passed before fails now (SPEC-041 P26)
agent-eval gate result.json --max-cost-per-task 0.05     # cost SLO gate: fail if total_cost / task count exceeds this (P28)
agent-eval gate result.json --max-review-high 0 --notify slack://hooks.slack.com/services/T/B/X   # exit 4 on HIGH review items + post the narrative / regressions / cohort winner
agent-eval gate result.json --digest                     # also print the PM / QA / engineer briefs after the table (P34)
agent-eval gate result.json --target-file .aoo/targets.json   # use the project SLOs (.aoo/targets.json) as thresholds (P43)

# Gate-regression root-cause diagnosis (RCA — detect → attribute → cross-reference, the HOTL principle)
agent-eval diagnose result.json
agent-eval diagnose result.json --baseline baseline.json --show-diff

# Pin project goals / SLOs (.aoo/targets.json — thereafter gate / report / insights judge against this bar, SPEC-041 P43)
agent-eval target set --gate A=0.85 --gate E=0.95 --tcr 90
agent-eval target show

# Pin an external reference distribution (.aoo/reference.json — insights show percentile + gap-to-frontier, P53)
agent-eval benchmark set --tcr 78 --gate A=0.75 --label support-rag
agent-eval benchmark set --from-results results/     # derive TCR / per-gate percentile distributions from a results directory
agent-eval benchmark show

# Improvement-experiment registry (.aoo/experiments.jsonl — register a hypothesis and score it on the next run, P27)
agent-eval experiment register --gate A --field avg_subtask_completion --predict-delta 0.08 --note "add SubtaskConfig"
agent-eval experiment list
agent-eval experiment score v3.json --baseline v2.json --persist

# Closed improvement loop (proposal → experiment/stub → verify → outcomes, SPEC-041 P49/P57/P61)
agent-eval improve plan v3.json --baseline v2.json      # print per-gate proposals
agent-eval improve start v3.json --yes                  # register each proposal as an experiment + write .aoo/improve/*.md stubs
agent-eval improve verify v4.json --baseline v3.json --persist   # score predicted vs actual + resolve experiments
agent-eval improve patch v3.json --repo .               # emit a unified diff per proposal (prompt file / @agent_eval decorator) — never applied (P61)

# Statistical A/B comparison (2 files → Welch's t-test, 3+ → N-way + FDR correction)
# If you first need to find the two runs to compare, see workflow C (optional) in CTX_SESSION_SEARCH.md
agent-eval abtest v1.json v2.json --metric accuracy_score
agent-eval abtest v1.json v2.json --sequential --tau 0.05   # mSPRT always-valid inference
agent-eval abtest v1.json v2.json v3.json                   # N-way

# Golden-dataset auto-extraction / promotion / health
agent-eval dataset build --source results/ --max-cases 30
agent-eval dataset build --source results/ --strategy high_value --output data/golden.json
agent-eval dataset promote result.json --min-priority high     # HITL review queue → golden regression cases (P15)
agent-eval dataset health golden.json --against v3.json        # golden-set coverage vs current failure modes + stale / duplicate cases (P58)

# Trend analysis of sequential evaluation results (TCR / accuracy regression detection)
agent-eval trend results/ --fail-on-regression

# LiveGuardrail OpenCode plugin / Claude Code hook install lifecycle
agent-eval opencode install
agent-eval opencode install --global   # global install
agent-eval opencode install --force    # overwrite an existing install
agent-eval opencode install --with-violation-search   # + register the search_violations MCP server
agent-eval opencode install --with-recommend-fix       # + register the recommend_fix MCP server
agent-eval opencode upgrade            # refresh the plugin .ts after a package update (keeps agent-evaluator.config.json)
agent-eval opencode doctor            # verify the install works (static + Python stdio-bridge round-trip, --json/--no-live/--strict)
agent-eval opencode uninstall         # remove the plugin + opencode.json mcp entries (run before pip uninstall, --purge/--dry-run/--yes)
agent-eval claude install             # install the LiveGuardrail Claude Code CLI hooks (--global/--force, --with-violation-search/--with-recommend-fix/--with-ask-insights)
agent-eval claude upgrade             # refresh hook matchers/interpreters + deep-merge only NEW default keys into guardrail_config.json (keeps your edits)
agent-eval claude doctor             # static checks + live hook round-trip (allow/deny/batch-report) + MCP handshake
agent-eval claude uninstall          # remove our hooks from settings.json + deregister MCP + delete session state (run before pip uninstall)

# .aoo/claims.jsonl team scope-claim management (TeamConcurrencyConfig integration)
agent-eval claims add src/ --developer auto   # open a claim (resolves via git config user.name)
agent-eval claims list                        # list active claims
agent-eval claims release <claim_id>          # release a claim
agent-eval claims audit --ttl-hours 8         # CI: flag TTL-exceeded / overlapping-scope violations (exit 1 on a violation)

# Version info
agent-eval --version
```

---

## Public API summary

Symbols importable directly via `from agent_evaluator import ...`:

```python
# Core classes
PerformanceMonitor, TaskResult, TaskType, EvaluationReport,

# Hybrid
HybridPerformanceMonitor, ExtendedTaskResult, HybridEvaluationReport,

# Helpers & context managers
create_taskresult,
evaluation_session, async_evaluation_session, hybrid_evaluation_session,

# QuickEval facade
QuickEval,

# Multi-turn conversation
ConversationSession, ConversationMetrics, ConversationTurn,

# LLM Judge (included in the base install)
LLMJudge,

# Transparency
TestTransparencyManager, AnnotationType, TestStepStatus,

# Configuration
load_env, get_settings, init_from_app,

# Advanced / custom trackers
BaseTracker, infer_privilege_level,

# Streaming / feedback / anomaly / cost
ImplicitFeedbackTracker,
AnomalyDetector, AnomalyEvent,
CostTracker, AdaptivePolicy, SamplingStage,

# Individual trackers
TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker,
ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
AgentCoordinationTracker, WorkflowExecutionTracker,
InputSanitizationTracker, OutputLeakageDetector,
ToolAuthorizationTracker, PrivilegeEscalationDetector, ToolChainAttackDetector,

# Alerts
SimpleTaskAlertRule,

# Type hints
FrameworkLiteral,   # a Literal type of the 24 frameworks
```

---

*Agent Evaluator v1.0.0 — [GitHub](https://github.com/bullpeng72/Agent-Evaluator) | [example directory](../Evaluator_Examples/)*
