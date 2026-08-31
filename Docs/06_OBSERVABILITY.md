# Observability Guide

Using the dashboard · Phoenix OTEL real-time monitoring.

**v1.0.0 | Python 3.8+**

---

## Table of Contents

1. [dashboard vs monitor — separation of roles](#1-dashboard-vs-monitor--separation-of-roles)
2. [Launching the dashboard and producing data](#2-launching-the-dashboard-and-producing-data)
3. [Dashboard panels — activation classification](#3-dashboard-panels--activation-classification)
4. [Per-tab detailed guide](#4-per-tab-detailed-guide)
5. [Operational-tab setup guide](#5-operational-tab-setup-guide)
6. [Phoenix OTEL monitoring — quick start](#6-phoenix-otel-monitoring--quick-start)
7. [Phoenix CLI specification](#7-phoenix-cli-specification)
8. [setup_otel() API](#8-setup_otel-api)
9. [Data sent to Phoenix](#9-data-sent-to-phoenix)
10. [Phoenix UI per-tab guide](#10-phoenix-ui-per-tab-guide)
11. [Using Phoenix GraphQL](#11-using-phoenix-graphql)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. dashboard vs monitor — separation of roles

| Aspect | `agent-eval dashboard` | `agent-eval monitor` |
|--------|------------------------|----------------------|
| **Audience** | developers · QM | MLOps · operations |
| **Stage** | development · verification · staging | production · operations |
| **Data source** | `save_to_file()` JSON | OTLP span stream (real-time) |
| **Update method** | polling (15s / --watch) | refreshes as spans arrive |
| **Main views** | metric aggregates · task table | traces · span waterfall · live errors |
| **Storage** | JSON files (results/) | SQLite (internal to Phoenix) |
| **How it runs** | a single FastAPI server | Arize Phoenix server + OTEL exporter |

```
agent runs
    │
    ├─▶ save_to_file()  ──────────────▶  agent-eval dashboard
    │   (JSON aggregate, always on)       check metrics during dev / verification
    │
    └─▶ OTLP Span Export (opt-in) ──▶  agent-eval monitor (Phoenix)
        (when setup_otel() is called)    real-time production tracing
```

---

## 2. Launching the dashboard and producing data

```bash
# Default launch (port 8765, opens the browser automatically)
agent-eval dashboard

# Set the port + auto-refresh on file changes
agent-eval dashboard --port 8765 --watch

# Do not open the browser automatically
agent-eval dashboard --no-open

# Offline mode (cache CDN assets locally)
agent-eval dashboard --offline
```

The dashboard loads JSON files from the `results/` folder automatically. With the `--watch` flag it detects file changes and refreshes live.

### Producing data (save_to_file() required)

**Option A — call save_to_file() directly**

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

monitor.save_to_file("eval")  # creates results/eval.json + results/eval.html
```

**Option B — auto_save (save automatically every N records)**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,
    auto_save_filename="auto_save",
)
```

**Option C — QuickEval.save()**

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

eval.save()  # creates results/quickeval.json + .html automatically
```

---

## 3. Dashboard panels — activation classification

The dashboard exposes 23 top-level tabs (plus a Harness Gate panel rendered inside the Quality /
Reliability tabs). Below the menus are grouped by what it takes to populate them.

### 🟢 Available with the decorator alone (9 tabs + the Harness Gate panel)

Tabs filled automatically just by calling `save_to_file()` after applying `@agent_eval` / `@batch_eval` / `@conversation_eval`.

| Menu | Required configuration |
|------|------------------------|
| 📊 **Overview** | default (always) |
| 📋 **Tasks** | default (always) |
| 💡 **Insights** | default (always) |
| 🎯 **Quality** | default (hallucination: `enable_hallucination_detection=True`) |
| 💬 **Multi-turn Conversation** | `@conversation_eval` |
| ⚡ **Performance** | default (always) |
| 🤖 **Agentic** | `task_type="tool_use"` + `tool_calls` in the response |
| 🔁 **Reproducibility · Stability** | pass Harness Gate C Config (`FaultToleranceConfig`, etc.) |
| 🔒 **Security** | `security=SecurityConfig()` or `enable_security_metrics=True` |
| 🏗 **Harness Gate** | pass Harness Config parameters to `@agent_eval` (rendered inside the Quality / Reliability tabs) |

### 🟡 Available with the decorator + extra work (6)

| Menu | What else is needed |
|------|---------------------|
| 🔬 **External Evaluation (RAG/DeepEval)** | `pip install ".[eval]"` + `HybridPerformanceMonitor` |
| 📡 **Realtime** | create a `StreamingEvaluator` + `record()` + call `_flush()` explicitly |
| 🔔 **Alerts** | `alert_rules=` parameter + write JSONL in the handler |
| 👍 **User Feedback** | call `monitor.record_implicit_feedback()` explicitly |
| 🚨 **Anomaly Detection** | `PerformanceMonitor(enable_anomaly_detection=True)` |
| 💰 **Evaluation Cost** | token cost automatic / LLM-judge cost: `llm_judge=LLMJudgeConfig()` |

### 🔵 Available regardless of the decorator (8)

| Menu | How it works |
|------|--------------|
| 📂 **File Compare** | 2+ `results/*.json` files → pick two in the dropdown. Auto-group by the `prompt_version` / `agent_version` tag via the **Group by** dropdown; with two files selected, the **⚖️ Pairwise Judge** sub-tab (win-rate comparison) and **📄 Export HTML** (download the comparison as a single file) appear — see the ["version comparison" section of `08_API_REFERENCE.md`](08_API_REFERENCE.md#version-comparison--prompt_version--agent_version-v098) |
| 🗂️ **Case Review** | approve / reject candidate cases extracted by `agent-eval dataset build` |
| 📚 **Golden Dataset** | `data/golden_datasets/*.json` or `GoldenSetBuilder` |
| 📤 **Export** | 3 formats: raw JSON / per-task CSV / standalone HTML report |
| 🔍 **Transparency** | `TestTransparencyManager.add_annotation()` audit log |
| 📖 **Metrics Guide** | (static) descriptions, formulas, and interpretation guide for all 58 metrics |
| ⚙️ **Settings** | enter thresholds directly in the dashboard UI (reset on server restart) |
| 🔧 **Improve** | pick Current/Baseline result files → renders the insight layer from `reporting/insights.py::build_insights()` (via `/api/diagnose/{id}`). With a baseline: `top_detail_deltas` (detail metrics that drove the regression) + `rca.diagnose()` MAST candidates; without one: `component_shortfalls` (weak components + prescription). Includes the recommendation history (`recommendation_outcomes.jsonl`) summary and Path to Green (`readiness.fix_plan`) |

---

## 4. Per-tab detailed guide

### Overview tab

- **Total tasks** — the count of all evaluated tasks
- **Average completion rate (TCR)** — the mean task completion rate
- **Average accuracy** — the overall mean from AccuracyEvaluator
- **Average response time** — the mean execution time (seconds)
- **Total token cost** — the cumulative cost estimate (USD)
- Framework-distribution donut chart, task-type-distribution bar chart

### Quality tab

| Card | Value shown | Interpretation |
|------|-------------|----------------|
| Accuracy Score | overall accuracy % | >75% recommended |
| Quality Score | on a `/5.0` scale | >3.5/5.0 recommended |
| Hallucination | hallucination count | closer to 0 is better |

> **Note**: the Quality Score is on a `/5.0` scale, not `/10`.

- **Response-quality-dimension radar**: Relevance / Completeness / Accuracy / Clarity / Usefulness
- **Hallucination-detection panel**: data is collected only when `enable_hallucination_detection=True`

### Agentic tab (3 sub-tabs)

**Execution · Retry sub-tab**
- TCR, retry rate, first-attempt success rate, average retry time KPIs
- Retry-distribution bar chart by task type

**Tools · Coordination · Flow sub-tab**
- Tool Selection F1 (Precision/Recall/F1) panel
- Multi-agent coordination panel (interaction count, coordination patterns)
- Workflow-funnel chart (visualizes bottlenecks by step group)

**Execution-trace sub-tab**
- Full execution-flow timeline per task
- Per-step duration bar chart, failed steps highlighted

### Security tab

Data appears only for evaluations run with `enable_security_metrics=True`.

- **Input-threat panel**: distribution of SQL / Command / XSS / Path / Prompt Injection
- **Output-leakage panel**: 8 types — API Key / Password / Credit Card / Email / Phone / SSN / Internal IP / File Path
- **Authorization / privilege-escalation / attack-chain panels**: per-tracker violation rate / detection rate

### RAG tab

Requires `HybridPerformanceMonitor` + `use_ragas=True`.
Faithfulness / Answer Relevancy / Context Precision / Context Recall KPI cards and line charts.

### DeepEval tab

Requires `HybridPerformanceMonitor` + `use_deepeval=True`.
G-Eval Score / Hallucination / Toxicity / Bias / Answer Relevancy KPI cards.

---

## 5. Operational-tab setup guide

| Tab | Decorator-only? | Required extra action |
|-----|:---:|-----------------------|
| **Realtime** | ❌ | create a `StreamingEvaluator` + `record()` + `_flush()` |
| **Alerts** | ⚠️ semi-automatic | `alert_rules=` + write JSONL in the handler |
| **User Feedback** | ❌ | call `monitor.record_implicit_feedback()` explicitly |
| **Anomaly Detection** | ✅ | `PerformanceMonitor(enable_anomaly_detection=True)` |
| **Evaluation Cost** | ✅ | tokens automatic / LLM-judge cost: `llm_judge=LLMJudgeConfig()` |

### Realtime tab

```python
from agent_evaluator.streaming.evaluator import StreamingEvaluator

monitor = PerformanceMonitor(output_dir="results/")
streaming = StreamingEvaluator(monitor=monitor, window_size=20, flush_interval=30)

result = create_taskresult(...)
monitor.record_task(result)
streaming.record(result)

streaming._flush()         # must be called before saving
monitor.save_to_file("eval")
```

### Alerts tab

The Alerts tab reads `results/alerts/YYYY-MM-DD.jsonl`.

```python
import json
from datetime import date, datetime
from agent_evaluator import SimpleTaskAlertRule, agent_eval
import os

_TODAY_JSONL = f"results/alerts/{date.today()}.jsonl"
os.makedirs("results/alerts", exist_ok=True)

def _write_alert_jsonl(rule_name: str, severity: str, message: str, task_id: str = ""):
    event = {
        "triggered_at": datetime.now().isoformat(),
        "rule_name": rule_name,
        "severity": severity,
        "message": message,
        "task_id": task_id,
    }
    with open(_TODAY_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

slow_rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: _write_alert_jsonl("slow_response", "warning", msg, tr.task_id),
    severity="warning",
)

@agent_eval(monitor, task_type="qa", alert_rules=[slow_rule])
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### User Feedback tab

```python
monitor.record_task(result)

# feedback_type: "thumbs_up" | "thumbs_down" | "follow_up_question" |
#                "task_abandonment" | "retry_request" | "dwell_time"
monitor.record_implicit_feedback(
    task_id=result.task_id,
    feedback_type="thumbs_up",
    metadata={"dwell_time": 8.5, "source": "ui"},
)

monitor.save_to_file("eval")
```

### Anomaly Detection tab

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,
    anomaly_baseline_window=50,
    anomaly_detection_window=10,
)
# AnomalyDetector.scan() runs automatically on save_to_file() — no extra code needed
```

| Detection type | Min tasks | Algorithm |
|----------------|:---:|-----------|
| `latency_trend` | 5+ | linear regression (slope > 0.05s/task) |
| `accuracy_drift` | 5+ | Z-score (deviation from baseline > 2.5σ) |
| `token_spike` | 5+ | IQR (exceeds Q3 + 2×IQR) |
| `error_surge` | detection_window+ | ratio (error rate > 20% AND 2× the baseline) |

---

## 6. Phoenix OTEL monitoring — quick start

> **First time?** Follow these 3 steps and you can watch agent runs live in the Phoenix UI.

### Step 1: install

```bash
# OTEL monitoring — requires the [otel] or [sdk] extra
pip install "agent-evaluator[sdk]"
```

### Step 2: start the Phoenix server (terminal A)

```bash
agent-eval monitor
# output: Phoenix UI → http://localhost:6006
```

### Step 3: run the agent (terminal B)

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# ① must be called before the PerformanceMonitor is created
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("What is the capital of Korea?", ground_truth="Seoul")

# Save the scores (sends Annotations to Phoenix)
monitor.save_to_file("run_001")
```

> `http://localhost:6006` → check the result in the Tracing tab

---

## 7. Phoenix CLI specification

```bash
# Start the Phoenix server + open the browser automatically
agent-eval monitor

# Set the port (default 6006)
agent-eval monitor --port 6006

# Do not open the browser automatically
agent-eval monitor --no-open

# Connect to an existing Phoenix server (do not start one)
agent-eval monitor --attach http://localhost:6006

# Check the environment (installed? port state?)
agent-eval monitor --check
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `6006` | Phoenix UI / OTLP HTTP port (Phoenix 13.x: same port) |
| `--host` | `localhost` | Phoenix bind host |
| `--no-open` | (flag) | do not open the browser automatically |
| `--attach <url>` | — | connect to an existing Phoenix without starting one |
| `--check` | (flag) | check the installation and port occupancy |
| `--working-dir <path>` | Phoenix decides (usually `~/.phoenix`) | Phoenix DB storage directory |
| `--sync-datasets <glob>` | — | upload golden-set JSON files as Phoenix Datasets (glob pattern supported) |
| `--reset` | (flag) | delete all traces / projects / datasets from the Phoenix DB (stop Phoenix first) |
| `--yes` / `-y` | (flag) | skip the `--reset` confirmation prompt |

---

## 8. setup_otel() API

```python
from agent_evaluator import setup_otel

setup_otel(
    endpoint="http://localhost:6006",   # Phoenix 13.x default port (UI + OTLP the same)
    service_name="my-agent",           # service name in the Phoenix UI
    enabled=True,                      # no-op when False (CI environments, etc.)
    enable_metrics=False,              # Phoenix does not support /v1/metrics — use only with Grafana, etc.
)
```

> **Ordering**: `setup_otel()` must be called **before** the `PerformanceMonitor` is created.

### Disabling in a CI/CD environment

```python
import os
from agent_evaluator import setup_otel

if os.getenv("CI") != "true":
    setup_otel(endpoint="http://localhost:6006")
# In CI, setup_otel() is not called → OTEL is a no-op; JSON saving works normally
```

### Auto-disable pattern when Phoenix is not running

```python
def _try_setup_otel(service_name: str) -> None:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("localhost", 6006)) != 0:
            return  # Phoenix not running — no-op
    from agent_evaluator import setup_otel
    setup_otel(endpoint="http://localhost:6006", service_name=service_name)
    print("Phoenix monitoring enabled — http://localhost:6006")

_try_setup_otel("my-service")
```

---

## 9. Data sent to Phoenix

### TaskType → span kind mapping

| TaskType | span kind |
|----------|-----------|
| `qa`, `code_generation`, `coding`, `creative`, `document_creation`, `reasoning` | `LLM` |
| `information_retrieval` | `RETRIEVER` |
| `tool_use` | `TOOL` |
| `planning` | `AGENT` |
| `data_analysis` | `CHAIN` |
| anything else (`multi_agent`, `streaming`, and other unmapped TaskTypes) | `LLM` (default fallback) |

### Phoenix Annotations (score transfer)

Sent to the `/v1/span_annotations` API on `save_to_file()`:

| Evaluator name | Score range | Label |
|----------------|-------------|-------|
| `accuracy` | 0.0–1.0 | pass (≥0.5) / fail (<0.5) |
| `completion` | 0.0–1.0 | pass / fail |
| `success` | 1.0 (success) / 0.0 (failure) | pass / fail |

> **Where to look**: Tracing tab → click a span → the **"Annotations"** section on the right
> (not the "Evaluators" tab in the top menu)

---

## 10. Phoenix UI per-tab guide

### Tracing tab — agent execution records

A row is recorded here on every `record_task()` call.

- span name (e.g. `ae.task/qa/task_001`)
- success/failure status, execution time, input/output text
- **Checking Annotations**: click a span → right panel → "Annotations" section (~3s after save_to_file())

```bash
# Separate spans per project
setup_otel(service_name="project-name")  # selectable from the top dropdown in the Phoenix UI
```

### Datasets tab — golden-dataset management

```python
from agent_evaluator.datasets import GoldenSetBuilder

builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")
cases = builder.extract(strategies=["high_value"], max_cases=50)
builder.push_to_phoenix(cases, dataset_name="qa-golden-v1")
```

### Playground tab — prompt-replay tool

Pull a specific span's input/output to edit and retry the prompt.
Include the `llm.prompts` attribute on the span to make it replayable in the Playground.

```python
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = "It is Seoul."
    return response, EvalMetadata(
        extra={"llm.prompts": [{"role": "user", "content": question}]}
    )
```

### Evaluators tab

> ⚠️ **Common misconception**: Agent-Evaluator's `accuracy` / `completion` / `success` scores are
> **not shown on this tab**. They are in the Tracing tab → span detail → "Annotations" section.
> The Evaluators tab being empty is normal.

### Prompts tab — prompt version control

```python
import requests

response = requests.post("http://localhost:6006/v1/prompts", json={
    "name": "qa-system-prompt",
    "version": "v1.0",
    "template": "You are an AI assistant that provides accurate answers.\nQuestion: {question}\nAnswer:",
})
```

---

## 11. Using Phoenix GraphQL

GraphQL UI: `http://localhost:6006/graphql`

### 5 ready-made queries

**Query 1: list projects**

```graphql
query {
  projects {
    edges {
      node { id name traceCount spanCount createdAt }
    }
  }
}
```

**Query 2: list spans + evaluation scores**

```graphql
query GetSpansWithAnnotations($projectName: String!) {
  project(name: $projectName) {
    spans(first: 20) {
      edges {
        node {
          spanId name statusCode latencyMs
          input { value }
          output { value }
          spanAnnotations { name score label }
        }
      }
    }
  }
}
```

**Query 3: list datasets**

```graphql
query {
  datasets {
    edges {
      node { id name description exampleCount createdAt }
    }
  }
}
```

**Query 4: create a dataset**

```graphql
mutation CreateDataset {
  createDataset(name: "qa-golden-v2" description: "QA evaluation golden set v2") {
    dataset { id name }
  }
}
```

**Query 5: add examples to a dataset**

```graphql
mutation AddDatasetExamples($datasetId: GlobalID!) {
  addSpansToDataset(datasetId: $datasetId spanIds: [] examples: [
    {
      input: { question: "What is the capital of Korea?" }
      output: { answer: "Seoul" }
      metadata: { source: "manual" }
    }
  ]) {
    dataset { id name exampleCount }
  }
}
```

### Calling GraphQL from Python

```python
import requests

def query_phoenix(query: str, variables: dict = None) -> dict:
    response = requests.post(
        "http://localhost:6006/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

result = query_phoenix("""
    query { projects { edges { node { id name traceCount } } } }
""")
```

---

## 12. Troubleshooting

### The dashboard has no data

```bash
ls results/*.json     # check that JSON files exist
python Evaluator_Examples/ch02_quickstart.py
agent-eval dashboard
```

### A specific tab is empty

| Tab | Required configuration |
|-----|------------------------|
| Realtime | `StreamingEvaluator` + `record()` + `_flush()` |
| Alerts | `alert_rules=` parameter + write JSONL in the handler |
| User Feedback | `monitor.record_implicit_feedback()` |
| Anomaly Detection | `enable_anomaly_detection=True` |
| Quality — Hallucination | `enable_hallucination_detection=True` |
| Security | `enable_security_metrics=True` |
| RAG | `HybridPerformanceMonitor` + Ragas data |

### Phoenix Annotations are not visible

1. Confirm `setup_otel()` was called **before** the `PerformanceMonitor` was created
2. Wait ~3s after `save_to_file()`, then refresh
3. Tracing tab → click a span → check the **"Annotations"** section (not the Evaluators tab)

### agent-eval monitor port conflict

```bash
lsof -ti :6006 | xargs kill -9
agent-eval monitor
# or keep the existing server and connect to it
agent-eval monitor --attach http://localhost:6006
```

---

| Goal | Document |
|------|----------|
| Installation · basic usage | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| All 58 metrics in detail | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| Decorators · framework integration | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| Quality thresholds · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Full output taxonomy (JSON · report · CLI · dashboard · AI runtime) | [09_OUTPUTS.md](09_OUTPUTS.md) |
| Docker · per-environment configuration | [07_OPERATIONS.md](07_OPERATIONS.md) |
