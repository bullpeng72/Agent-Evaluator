# Getting Started

The shortest path from installing Agent Evaluator to your first evaluation, saving results, and launching the dashboard.

**v1.0.0 | Python 3.8+**

---

## Table of Contents

1. [Installation](#installation)
2. [Decorator approach — recommended](#decorator-approach--recommended)
3. [Low-level direct recording (escape hatch)](#low-level-direct-recording-escape-hatch)
4. [Context manager pattern (escape hatch)](#context-manager-pattern-escape-hatch)
5. [Result output path — zero configuration](#result-output-path--zero-configuration)
6. [Launching the dashboard](#launching-the-dashboard)
7. [Enabling security / agentic metrics](#enabling-security--agentic-metrics)
8. [CI/CD quality gating](#cicd-quality-gating)
9. [Real-time production monitoring](#real-time-production-monitoring)
10. [Next steps](#next-steps)

---

## Installation

```bash
# Base install — core evaluation engine (LLMJudge included)
pip install agent-evaluator

# Dashboard + OTEL + PDF (recommended for production)
pip install "agent-evaluator[sdk]"

# Run every example — sdk + deepeval/ragas/langchain
pip install "agent-evaluator[examples]"

# Real-time guardrail — OpenCode + MCP integration (search_violations · recommend_fix)
pip install "agent-evaluator[mcp]"

# Framework integration (when your agent uses that framework)
pip install "agent-evaluator[langchain]"   # LangChain/LangGraph
pip install "agent-evaluator[eval]"        # DeepEval + Ragas
pip install "agent-evaluator[full]"        # everything (⚠️ includes crewai/autogen, 10 min+)
```

> **Python 3.8–3.13** supported. numpy and pandas are installed automatically.
> The dashboard (`agent-eval dashboard`), Phoenix monitoring (`agent-eval monitor`), and PDF processing require the `[sdk]` extra.
> For the full extras matrix organized into five categories, see [the Installation section of README.md](../README.md#installation).

---

## Decorator approach — recommended

Add a single decorator line to your agent function and evaluation is applied automatically.

### 1. @agent_eval (single call)

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# One TaskResult is recorded automatically on each call
my_agent("What is the capital of Korea?", ground_truth="Seoul")
```

### 2. @batch_eval (bulk processing)

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa", concurrency=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

### 3. @conversation_eval (multi-turn conversations)

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

chat_agent("Hi", sid="user_1")
chat_agent("What's the weather?", sid="user_1")
flush_conversation("user_1")   # explicitly end the session and record metrics
```

### QuickEval — one-line factory

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                          # task_type="qa"
def my_agent(question, ground_truth=""): ...

@eval.rag                         # task_type="information_retrieval" + hallucination
def rag_agent(question, context="", ground_truth=""): ...

eval.save()                       # quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)    # CI/CD gating
```

Shortcut decorators: `qa`, `tool_use`, `rag`, `code`, `reasoning`, `planning`, `data_analysis`, `creative`, `multi_agent`, `secure`, `streaming`

---

## Low-level direct recording (escape hatch)

> **Use this only when a decorator cannot be applied.** For external library functions, lambdas, dynamic dispatch, and so on. For ordinary agent evaluation, prefer the decorator approach above.

`create_taskresult()` computes scores automatically from question/response/ground_truth.

```python
from agent_evaluator import create_taskresult, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

result = create_taskresult(
    task_id="task_001",
    question="What is the capital of Korea?",
    response="It is Seoul.",
    ground_truth="Seoul",
    execution_time=0.8,
    task_type="qa",        # qa | code_generation | data_analysis | ...
)

monitor.record_task(result)
monitor.save_to_file("eval")
```

Multiple tasks can be recorded via method chaining.

```python
monitor.record_task(r1).record_task(r2).record_task(r3)
report = monitor.generate_report()
```

---

## Context manager pattern (escape hatch)

> Use this in **external code where a decorator cannot be applied**. For ordinary agent functions, use the `@agent_eval` decorator.

`eval_context` provides the same evaluation as `@agent_eval` in a `with` block.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import eval_context

monitor = PerformanceMonitor(output_dir="results/")

with eval_context(monitor, task_type="qa",
                  question="What is the capital of Korea?", ground_truth="Seoul") as ctx:
    ctx.response = external_lib.call("What is the capital of Korea?")

monitor.save_to_file("eval")
# saves results/eval.json + .html automatically
```

Async agents are supported too.

```python
async with eval_context(monitor, task_type="qa", question=q) as ctx:
    ctx.response = await async_external.call(q)
```

Use `evaluation_session` when you want automatic per-session saving.

```python
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("output_filename") as monitor:
    for item in dataset:
        with eval_context(monitor, task_type="qa",
                          question=item["question"],
                          ground_truth=item["answer"]) as ctx:
            ctx.response = external_agent.run(item["question"])
# on block exit, results/output_filename.json + .html are saved automatically
```

---

## Result output path — zero configuration

Results are saved to the right place automatically, with no extra configuration.

### Automatic path detection order

| Priority | Method |
|---------|--------|
| 1 | Environment variable `AGENT_EVALUATOR_OUTPUT_DIR` (highest priority) |
| 2 | Environment variable `AGENT_EVALUATOR_ROOT` (project root override) |
| 3 | `results/` under the Git repository root |
| 4 | `results/` under the current working directory (fallback) |

```python
# Check the currently detected paths
from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir

print("Project root:", find_project_root())
print("Results directory:", get_evaluation_results_dir())
```

### Explicit path override

```bash
# Set the results directory directly (highest priority)
export AGENT_EVALUATOR_OUTPUT_DIR=/path/to/results

# Set the project root
export AGENT_EVALUATOR_ROOT=/path/to/my/project
```

```python
import os
os.environ['AGENT_EVALUATOR_ROOT'] = '/path/to/my/project'
monitor.save_to_file("my_evaluation")
# → /path/to/my/project/results/my_evaluation.json (+ .html)
```

### Automatic result-file registry

Each `save_to_file()` call registers the file in `~/.agent_evaluator/registry.json` automatically. The dashboard uses this to discover file locations.

### Auto-save (auto_save)

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,      # save every 10 records
    auto_save_filename="auto_checkpoint",
)

# The same applies to QuickEval
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
```

---

## Launching the dashboard

The dashboard loads JSON files from the `results/` directory. **Save your evaluation results to a file first**, then launch it.

```python
# Option A: save_to_file()
monitor.save_to_file("eval")     # creates results/eval.json + .html

# Option B: auto_save
monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# Option C: QuickEval
eval = QuickEval("results/")
eval.save()                      # results/quickeval.json + .html
```

```bash
# Default launch (port 8765, opens the browser automatically)
agent-eval dashboard

# Options
agent-eval dashboard --port 8765 --watch     # set port + watch files
agent-eval dashboard --no-open               # do not open the browser automatically
agent-eval dashboard --offline               # cache CDN assets locally
```

---

## Enabling security / agentic metrics

```python
# Security metrics (Layer 2 Security)
monitor = PerformanceMonitor.for_secure_agents(
    output_dir="results/",
    security_config={
        "allowed_tools": ["search", "read"],
        "restricted_tools": ["delete", "execute"],
    },
)

# RAG evaluation (hallucination detection enabled by default)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
```

---

## CI/CD quality gating

```bash
# Exit 1 if TCR < 85% or Accuracy < 70%
agent-eval gate results/eval.json --tcr 85 --accuracy 70
```

```python
# Gating from code
eval.gate(tcr=85, accuracy=70)                    # sys.exit(1) on failure
passed = eval.gate(tcr=80, accuracy=65, raise_on_fail=False)  # returns bool
```

---

## Real-time production monitoring

Trace production spans in real time with Phoenix + OpenTelemetry. **`setup_otel()` must be called before the PerformanceMonitor is created.**

```bash
# Terminal 1 — start the Phoenix server
agent-eval monitor                           # UI: http://localhost:6006
agent-eval monitor --check                   # check the installation
```

```python
# Terminal 2 — agent code
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")  # ← must come first
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("What is the capital of Korea?", ground_truth="Seoul")
# → OTLP spans are sent automatically → view them live in the Phoenix Tracing tab
```

---

## Next steps

| Goal | Document |
|------|----------|
| All 58 metrics in detail (25 Native + 33 Harness Config) | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| Full decorator parameters + framework integration | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| Golden dataset construction · Korean RAG evaluation | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| Quality threshold configuration · CI/CD integration | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Dashboard tabs in detail · Phoenix monitoring | [06_OBSERVABILITY.md](06_OBSERVABILITY.md) |
| Docker · per-environment configuration · performance tuning | [07_OPERATIONS.md](07_OPERATIONS.md) |
| Full API reference | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
| Result JSON · report · CLI · dashboard · AI-runtime output taxonomy | [09_OUTPUTS.md](09_OUTPUTS.md) |
| Runnable example files | [Evaluator_Examples/](../Evaluator_Examples/) |
