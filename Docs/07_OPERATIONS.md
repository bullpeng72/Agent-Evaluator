# Operations Guide

Installation · Docker · per-environment configuration · performance tuning · troubleshooting.

**v1.0.2 | Python 3.8+**

---

## Table of Contents

1. [Installation variants](#1-installation-variants)
2. [Environment configuration](#2-environment-configuration)
3. [AGENT_EVAL_PRESETS — purpose-specific presets](#3-agent_eval_presets--purpose-specific-presets)
4. [Docker deployment](#4-docker-deployment)
5. [Per-environment PerformanceMonitor configuration](#5-per-environment-performancemonitor-configuration)
6. [Performance tuning](#6-performance-tuning)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Installation variants

```bash
# Base install — core evaluation engine (LLMJudge included)
pip install agent-evaluator

# With SDK features — dashboard · OTEL · PDF (recommended for production)
pip install "agent-evaluator[sdk]"

# Run every example — sdk + deepeval/ragas/langchain
pip install "agent-evaluator[examples]"

# Framework integration (only when your agent uses that framework)
pip install "agent-evaluator[langchain]"   # LangChain + LangGraph
pip install "agent-evaluator[eval]"        # DeepEval + Ragas
pip install "agent-evaluator[crewai]"      # CrewAI (heavy — 100+ transitive dependencies)
pip install "agent-evaluator[autogen]"     # AutoGen (heavy, isolated on its own)
pip install "agent-evaluator[full]"        # everything (⚠️ includes crewai/autogen, 10 min+)

# Development environment (install from source)
pip install -e ".[dev]"
```

### Verifying the install

```bash
python -c "from agent_evaluator import PerformanceMonitor, QuickEval; print('OK')"
agent-eval --version
```

---

## 2. Environment configuration

### The .env file

```bash
# .env (do not commit to Git — add it to .gitignore)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Results directory (default: results/)
AGENT_EVALUATOR_OUTPUT_DIR=results/

# Project root override (Git-root auto-detection is the default)
# AGENT_EVALUATOR_ROOT=/path/to/my/project

# Environment tag
ENV=production
LOG_LEVEL=INFO

# LLM Judge provider (v0.8.3+)
# auto: auto-select whichever provider has an API key (default)
# openai | anthropic: prefer a specific provider
AGENT_EVALUATOR_JUDGE_PROVIDER=auto

# Optional: alert webhook
ALERT_WEBHOOK=https://hooks.slack.com/services/...
```

### Setup wizard

```bash
# Interactive API-key setup — generates the .env file automatically
agent-eval init

# Check the current configuration state
agent-eval check
```

### Result-output path auto-detection order

| Priority | Method |
|---------|--------|
| 1 | environment variable `AGENT_EVALUATOR_OUTPUT_DIR` (highest priority) |
| 2 | environment variable `AGENT_EVALUATOR_ROOT` (project root override) |
| 3 | `results/` under the Git repository root |
| 4 | `results/` under the current working directory (fallback) |

```python
# Check the currently detected paths
from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir

print("Project root:", find_project_root())
print("Results directory:", get_evaluation_results_dir())
```

### Debugging configuration

```python
from agent_evaluator.config import load_env, get_settings

load_env()  # load .env
settings = get_settings()
print(settings)  # print the current settings
```

---

## 3. AGENT_EVAL_PRESETS — purpose-specific presets

An explicitly passed parameter always takes precedence over the preset.

| Preset | sample_rate | timeout | flush_every | Other |
|--------|:-----------:|:-------:|:-----------:|-------|
| `production` | 0.1 | 30.0s | 50 | `enable_anomaly_detection=True` · `enable_llm_judge=True` · `allow_duplicate_task_ids=False` |
| `development` | 1.0 | none | 1 | `enable_llm_judge=True` · `auto_detect_framework=True` |
| `testing` | 0.1 | 60.0s | 5 | — |
| `canary` | 0.05 | 30.0s | 50 | `enable_anomaly_detection=True` |
| `performance` | 1.0 | 10.0s | 20 | `enable_anomaly_detection=True` — latency/token-focused, LLM Judge left off for a lighter run |
| `security` | 1.0 | 30.0s | default | a lightweight preset for security-focused scenarios (`security=SecurityConfig()` is not enabled automatically by the preset — set it separately if you need it) |

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/", preset="production")   # production deployment
eval = QuickEval("results/", preset="development")  # full evaluation during dev + LLM Judge
eval = QuickEval("results/", preset="testing")       # testing — minimize external API calls via sampling
eval = QuickEval("results/", preset="canary")        # canary deployment — 5% sampling
eval = QuickEval("results/", preset="performance")   # focused latency/token monitoring
eval = QuickEval("results/", preset="security")      # security scenario — sample_rate=1.0
```

---

## 4. Docker deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir agent-evaluator

COPY agent_evaluator/ ./agent_evaluator/

RUN mkdir -p results/

ENV PYTHONUNBUFFERED=1
ENV ENV=production

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import agent_evaluator; print('OK')" || exit 1

EXPOSE 8765

CMD ["agent-eval", "dashboard", "--port", "8765", "--no-open"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  dashboard:
    build: .
    container_name: agent-evaluator-dashboard
    ports:
      - "8765:8765"
    environment:
      - ENV=${ENV:-production}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - ./results:/app/results          # persist evaluation results
      - ./data:/app/data                # golden dataset
      - ./.env:/app/.env
    command: agent-eval dashboard --port 8765 --no-open
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

```bash
# Run
docker-compose up -d dashboard

# Check logs
docker-compose logs -f dashboard

# Dashboard: http://localhost:8765
```

---

## 5. Per-environment PerformanceMonitor configuration

### Environment-variable summary

| Variable | Dev | Staging | Production |
|----------|-----|---------|------------|
| `ENV` | `development` | `staging` | `production` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` |
| TCR threshold | 70% | 85% | 95% |
| Accuracy threshold | 65% | 80% | 90% |

### Per-environment PerformanceMonitor code

```python
import os
from agent_evaluator import PerformanceMonitor

def get_monitor() -> PerformanceMonitor:
    """Return the optimal Monitor for the environment."""
    env = os.getenv("ENV", "development")

    if env == "production":
        return PerformanceMonitor(
            output_dir="results/",
            enable_security_metrics=True,
            auto_save=True,
            auto_save_interval=50,
        )
    elif env == "staging":
        return PerformanceMonitor(
            output_dir="results/",
            enable_hallucination_detection=True,
            auto_save=True,
            auto_save_interval=20,
        )
    else:  # development
        return PerformanceMonitor(output_dir="results/")
```

---

## 6. Performance tuning

### Long-running evaluations — auto-save

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,         # save every 50 records — prevents OOM
    auto_save_filename="auto_checkpoint",
)
```

### High-traffic production — sampling

```python
from agent_evaluator.decorators import agent_eval

# Evaluate only 10% — a cost/performance balance
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### Periodic saving from the decorator

```python
# Save every 10 calls
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question, ground_truth=""): ...

# The same applies to batch_eval
@batch_eval(monitor, flush_every=5)
def batch_agent(questions, ground_truths=None): ...
```

### Reducing LLM Judge cost

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,
    judge_sample_rate=0.1,     # score only 10% with the LLM Judge (cost saving)
    judge_model="claude-haiku-4-5-20251001",  # a cost-efficient model
)
```

### Bounded memory for an always-on monitor — `retention_mode`

`PerformanceMonitor` keeps every `TaskResult` in memory by default (`retention_mode="full"`). For a
process that records indefinitely, cap it:

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    retention_mode="window",   # keep only the most recent window_size tasks in memory
    window_size=10000,         # default 10000
)
```

Aggregate metrics stay correct (they are running aggregates); only the raw per-task list is trimmed.

### Persistent storage — `storage_backend="sqlite"`

The default `storage_backend="json"` writes one file per `save_to_file()`. For high-volume or
long-running production, opt into the SQLite backend — it upserts tasks into a `.db`, powers the
`search_violations` FTS5 index, and lets a restarted process pick up where it left off:

```python
monitor = PerformanceMonitor(output_dir="results/", storage_backend="sqlite")
# ... records tasks into results/<name>.db ...

# On a later process, replay history so aggregates and — critically — the
# AnomalyDetector baseline are not empty after the restart:
monitor = PerformanceMonitor(output_dir="results/", enable_anomaly_detection=True)
n = monitor.rehydrate_from_storage("results/production.db", limit=500)  # returns tasks replayed
```

> Replay with `enable_llm_judge` / `enable_hallucination_detection` / `enable_security_metrics` **off**
> if you only want to reproduce past history — otherwise already-scored tasks are re-scored (and an
> LLM Judge re-incurs cost).

### PII redaction before storage — `enable_pii_redaction`

Redact PII from task question / response / context before it is written to the result file or the
SQLite store (off by default):

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_pii_redaction=True,
    pii_redaction_categories=["email", "phone", "ssn", "credit_card"],  # None = a sensible default set
)
```

This is independent of the Gate E `ComplianceConfig` PII *detection* — that scores the agent; this
scrubs what you persist.

---

## 7. Troubleshooting

### Common problems and fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: agent_evaluator` | package not installed | `pip install agent-evaluator` |
| `AuthenticationError: Invalid API key` | wrong API key | check `.env`, run `agent-eval check` |
| `FileNotFoundError: results/` | output directory missing | `mkdir -p results/` or set `output_dir` |
| `ImportError: fastapi` | `[sdk]` extra not installed | `pip install "agent-evaluator[sdk]"` |
| `ImportError: opentelemetry` | `[sdk]` extra not installed | `pip install "agent-evaluator[sdk]"` |
| Quality gate always passes | trackers disabled | check `enable_hallucination_detection=True`, etc. |
| Security metrics 0% | `enable_security_metrics` not set | `PerformanceMonitor(enable_security_metrics=True)` |
| Accuracy always 0 | `ground_truth` not passed | add a `ground_truth` parameter to the function args |

### Checking the install state

```bash
agent-eval check

python -c "
from agent_evaluator import PerformanceMonitor, QuickEval
from agent_evaluator.decorators import agent_eval
print('core: OK')

try:
    from agent_evaluator.serve import server
    print('serve: OK')
except ImportError:
    print('serve: NOT installed — pip install \"agent-evaluator[sdk]\"')

try:
    import opentelemetry
    print('otel: OK')
except ImportError:
    print('otel: NOT installed — pip install \"agent-evaluator[sdk]\"')
"
```

### Security metrics not collected

```python
# Correct configuration
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,  # must be set explicitly
)
# Since v0.7.3, the 5 security trackers are invoked automatically on record_task()
```

### Pre-deployment checklist

```bash
# 1. Confirm the package imports
python -c "from agent_evaluator import PerformanceMonitor, QuickEval; print('OK')"

# 2. Check API-key configuration
agent-eval check

# 3. Confirm .env is not tracked by Git
git check-ignore .env   # should print .env

# 4. Check the results directory
ls -la results/

# 5. Quality-gate smoke test
agent-eval gate results/sample.json --tcr 0 --accuracy 0   # always-passes test
```

---

| Goal | Document |
|------|----------|
| Installation · basic usage | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| Quality thresholds · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Dashboard · Phoenix monitoring | [06_OBSERVABILITY.md](06_OBSERVABILITY.md) |
| Full API reference | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
