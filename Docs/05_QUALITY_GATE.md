# Quality Gate Guide

Threshold configuration · quality gating · CI/CD integration.

**v1.0.0 | Python 3.8+**

---

## Table of Contents

1. [Overview](#1-overview)
2. [The 4 gating methods](#2-the-4-gating-methods)
3. [Full list of supported threshold metrics](#3-full-list-of-supported-threshold-metrics)
4. [Recommended values by environment](#4-recommended-values-by-environment)
5. [CI/CD integration](#5-cicd-integration)
6. [Managing threshold files](#6-managing-threshold-files)
7. [Trend analysis (agent-eval trend)](#7-trend-analysis-agent-eval-trend)
8. [Gate-regression root-cause diagnosis (agent-eval diagnose)](#8-gate-regression-root-cause-diagnosis-agent-eval-diagnose)
9. [Defining SLOs and the closed improvement loop](#9-defining-slos-and-the-closed-improvement-loop) — `target` · `benchmark` · `experiment` · `improve`
10. [Domain-specific Harness Config presets](#10-domain-specific-harness-config-presets)
11. [Best Practices](#11-best-practices)

---

## 1. Overview

A **threshold** is the minimum quality bar for an agent.

- **Quality gate** — guarantees a minimum level of performance before deployment
- **CI/CD automation** — stops the pipeline (`sys.exit(1)`) when the evaluation score falls short
- **Regression prevention** — automatically detects a performance drop after a code change

---

## 2. The 4 gating methods

### Method 1 — CLI gate (simplest)

Inspects an evaluation-result JSON file directly. Usable straight from a CI/CD script.

```bash
# Basic: check only TCR and accuracy
agent-eval gate results/eval.json --tcr 85 --accuracy 70

# Composite: check 4 metrics at once
agent-eval gate results/eval.json --tcr 85 --accuracy 70 --llm-judge 3.5 --hallucination 5

# Harness Gate A–G composite-score verdict (v0.8.3+)
agent-eval gate results/eval.json --min-gate-score 0.75

# Per-gate weights — emphasize Security (E) and Goal Achievement (A) 3×
agent-eval gate results/eval.json --min-gate-score 0.75 --group-weights "A:2.0,E:3.0,B:1.0"

# Per-gate minimum scores — judge each gate independently, not as one weighted composite
agent-eval gate results/eval.json --gate-thresholds "A:0.8,E:0.95" --required-gates "A,E" --fail-on-gate-warn
```

Missing any one threshold returns a non-zero exit code.

#### `--min-gate-score` / `--group-weights` in detail

| Option | Format | Description |
|--------|--------|-------------|
| `--min-gate-score` | `float` (0.0–1.0) | minimum weighted average of Gates A–G. exit(1) if below |
| `--group-weights` | `"A:W,B:W,..."` | per-gate weights (equal weighting if omitted). Undefined gates default to 1.0 |

```bash
# e.g. weight Security (E) 3×, Reliability (C) 2×, require overall composite ≥ 0.8
agent-eval gate results/eval.json \
  --min-gate-score 0.80 \
  --group-weights "C:2.0,E:3.0"
```

The composite score is taken from the `extra_metrics.harness_groups.{A-G}.score` fields. Gates with no such data are excluded from the calculation.

#### `--gate-thresholds` / `--required-gates` / `--fail-on-gate-warn` in detail

Unlike `--min-gate-score` / `--group-weights`, which judge on **one weighted composite score**, these three options compare **each of Gates A–G independently** against a threshold — use them when you want a different risk level per gate (e.g. Security at 0.95, everything else at 0.7).

| Option | Format | Description |
|--------|--------|-------------|
| `--gate-thresholds` | `"A:0.8,E:0.95"` | per-gate minimum score. Gates not listed fall back to `--min-gate-score` |
| `--required-gates` | `"A,E"` | restrict which gates `--gate-thresholds` checks (if omitted, all gates with a score are checked) |
| `--fail-on-gate-warn` | flag | treat a gate `warn` status as a failure (default: `warn` still passes) |

> `--required-gates` and `--fail-on-gate-warn` only take effect when `--gate-thresholds` is also given — on their own they do nothing. A gate not in `--required-gates` is silently excluded from the check, not "warned".

For an equivalent verdict from Python code, use [Method 4 — HarnessEvaluationGate](#method-4--harnessevaluationgate-config-as-code-composite-verdict) below — the `agent-eval gate` CLI and `HarnessEvaluationGate` are independent implementations that do not call each other, so they are not perfectly identical.

#### `--baseline-version` — per-version independent baselines (v0.9.8+)

When experimenting with several prompt / agent versions at once, keep an independent baseline per version and track each one's regression separately. If omitted, behavior is 100% identical to the existing single-path `<result_dir>/baseline.json`.

```bash
# Save a baseline for the v2-cot experiment — stored at <result_dir>/baselines/v2-cot.json
agent-eval gate results/run_v2.json --save-baseline --baseline-version v2-cot

# Compare later runs of the same experiment against the v2-cot baseline only (no effect on other versions' baselines)
agent-eval gate results/run_v2_latest.json --baseline-version v2-cot --fail-on-regression 10
```

`--baseline` (an explicit path) takes precedence over `--baseline-version` when both are given.

#### `--golden-set` / `--fail-on-golden-regression` — golden-set regression gate (v0.9.8+)

Verifies that each case in a human-approved golden dataset (the output of `agent-eval dataset build` or the dashboard approval workflow, `data/golden_datasets/golden_*.json`) is **still covered and still passing in the latest run**. Matching is by `task_id` first, falling back to exact `question` text — when merging golden sets, preserve the original `task_id` where possible (the dashboard's `merge_approved()` already does).

> This gate is a **post-hoc analysis** — it inspects an already-produced result JSON without re-running the agent. To "re-run the agent against the golden set to verify it," use the [golden-dataset regression test](#golden-dataset-regression-test) pattern below (re-run + `eval.gate()`) — the two approaches are complementary, not substitutes.

```bash
agent-eval gate results/run_latest.json \
  --golden-set data/golden_datasets/golden_20260705_120000.json \
  --fail-on-golden-regression
# exit 3: golden regression — a missing case (coverage gap) or success=False (quality regression)
```

Passing `--golden-set` without `--fail-on-golden-regression` only reports regressions to stderr and does not affect the exit code (the same convention as other opt-in checks) — the dedicated exit code `3` is returned only when the flag is set. If the golden-set file is missing or fails to parse (a path typo, etc.), it does not pass silently — it fails immediately with exit 1.

#### Case regression · cost SLO · review-queue gate (SPEC-041 P26·P28·P34)

| Option | Format | Description |
|--------|--------|-------------|
| `--baseline-result` + `--fail-on-case-regression` | file path + flag | **exit 4** if a task that passed in the previous run fails now |
| `--max-cost-per-task` | `float` ($) | fail if `total_cost / task count` exceeds this (cost SLO) |
| `--max-review-high` | `int` | **exit 4** if the number of HIGH items in `insights.review_queue` exceeds this |
| `--notify` | `slack://...` \| `webhook://...` | after the verdict, send the narrative + regressions + cohort winner to the target channel (never raises) |
| `--digest` | flag | also print the PM / QA / engineer briefs after the table |

If a `.aoo/targets.json` exists (written by `agent-eval target set`, see [§9.1](#9-defining-slos-and-the-closed-improvement-loop)), `agent-eval gate` loads it automatically and uses those per-gate / TCR values as the thresholds unless you pass `--gate-thresholds` / `--tcr` / `--accuracy` explicitly — no flag needed.

```bash
agent-eval gate result.json \
  --baseline-result results/prev_run.json --fail-on-case-regression \
  --max-cost-per-task 0.05 \
  --max-review-high 0 --notify slack://hooks.slack.com/services/T/B/X \
  --digest
```

---

### Method 2 — QuickEval.gate() (from code)

Handles evaluation and gating in one file.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    agent(q, ground_truth=gt)

# sys.exit(1) if a threshold is missed
eval.gate(tcr=85, accuracy=70, quality=3.5, hallucination=5.0)

# raise_on_fail=False → return a bool instead of exiting
passed = eval.gate(tcr=80, accuracy=65, raise_on_fail=False)
if not passed:
    print("quality bar missed — hold the deployment")

# Auto-generate gate_config.json from the current results (at 95% of the current values)
eval.generate_gate_config("gate_config.json")
```

---

### Method 3 — monitor.thresholds (low-level API)

Use this when you need fine-grained control while using `PerformanceMonitor` directly.

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")
monitor.thresholds = {
    "tcr": 85.0,
    "accuracy": 70.0,
    "latency": 5.0,   # P95, in seconds
}

results = monitor.compare_with_thresholds()
for metric, data in results.items():
    status = "PASS" if data["status"] == "pass" else "FAIL"
    print(f"[{status}] {metric}: {data['value']:.1f} (threshold: {data['threshold']})")
```

Structure returned by `compare_with_thresholds()`:

```python
{
    "tcr": {
        "name": "Task Completion Rate",
        "value": 91.2,
        "threshold": 85.0,
        "status": "pass",   # "pass" | "fail"
        "direction": "higher_is_better",
        "unit": "%",
    },
    "latency": {
        "name": "P95 Latency",
        "value": 6.3,
        "threshold": 5.0,
        "status": "fail",
        "direction": "lower_is_better",
        "unit": "seconds",
    },
}
```

---

### Method 4 — HarnessEvaluationGate (Config-as-Code composite verdict)

Where `agent-eval gate` / `QuickEval.gate()` are numeric-threshold-centric, `HarnessEvaluationGate` is a Python API that **treats the Harness Config declarations themselves as the basis for the verdict**. The results of the 33 Harness Configs declared on `@agent_eval` (`InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig`, etc.) are aggregated into the Gate A–G scores, and this class inspects those scores. Because the Config declarations live in code (Git-tracked), you can trace "why was this bar set" through review history.

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()   # no arguments
# {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool,
#      "threshold": float, "not_measured": bool (only when score=None),
#      "insufficient_data_warnings": list[str] (when present)}},
#  "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}

# CI/CD — sys.exit(1) on failure
gate.enforce()
```

**Per-gate thresholds + forced failure of unmeasured gates** — corresponds to the CLI's `--gate-thresholds` / `--required-gates`.

```python
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],
    group_thresholds={"E": 0.95},   # Security stricter; the rest use min_group_score
    strict_required=True,            # fail if a gate named in required_groups has score=None
                                      # (no Config set at all). The default (False) keeps the same
                                      # "an unmeasured gate silently passes" behavior as
                                      # the CLI / QuickEval.gate()
)
result = gate.evaluate()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_group_score` | `0.7` | minimum acceptable score per gate. Applied to gates not in `group_thresholds` |
| `required_groups` | `None` (all gates with a score) | list of gates to check |
| `fail_on_warn` | `False` | if `True`, a `warn` status is also a failure |
| `group_thresholds` | `None` | per-gate minimum-score dict. Same concept as the CLI `--gate-thresholds` |
| `strict_required` | `False` | fail if a gate named in `required_groups` is unmeasured (`score=None`) |

> ⚠️ The `agent-eval gate` CLI (`--gate-thresholds`), `QuickEval.gate(gate_thresholds=...)`, and `HarnessEvaluationGate` are three separate entry points that each invoke the Gate A–G threshold verdict — all three share `_compute_gate_regressions()` (the baseline-regression formula) and `gates/base.py::evaluate_gate_scores()` (the per-gate score/threshold/status → passed loop). The only remaining differences are entry-point-specific features (`HarnessEvaluationGate`'s `strict_required`, the CLI's `--baseline-version` / `--golden-set`). All three pass a gate with `score=None` (no Config set for that gate at all) by default (only `HarnessEvaluationGate` can turn this off, via `strict_required=True`).

---

## 3. Full list of supported threshold metrics

| Layer | Metric key | Unit | Direction | Recommended (Prod) |
|-------|------------|------|-----------|--------------------|
| Layer 1 | `tcr` | % | higher is better | ≥ 85 |
| Layer 1 | `accuracy` | % | higher is better | ≥ 70 |
| Layer 1 | `hallucination` | % | **lower is better** | ≤ 5 |
| Layer 1 | `quality` | points (0–5) | higher is better | ≥ 3.5 |
| Layer 1 | `latency` | seconds (P95) | **lower is better** | ≤ 5.0 |
| Layer 1 | `cost_per_task` | USD | **lower is better** | ≤ 0.05 |
| Layer 2 | `tool_selection_accuracy` | % (F1) | higher is better | ≥ 80 |
| Layer 2 | `agent_coordination` | % | higher is better | ≥ 75 |
| Layer 2 | `workflow_execution` | % | higher is better | ≥ 80 |
| Layer 2 | `retry_success_rate` | % | higher is better | ≥ 60 |
| Layer 2 (security) | `input_sanitization` | % | higher is better | ≥ 95 |
| Layer 2 (security) | `output_leakage` | % (detection rate) | **lower is better** | ≤ 1 |
| Layer 2 (security) | `authorization` | % | higher is better | ≥ 99 |
| Layer 2 (security) | `privilege_escalation` | count | **lower is better** | 0 |
| Layer 2 (security) | `tool_chain_attack` | count | **lower is better** | 0 |
| Layer 3 (RAG) | `faithfulness` | points (0–1) | higher is better | ≥ 0.80 |
| Layer 3 (RAG) | `answer_relevancy` | points (0–1) | higher is better | ≥ 0.75 |
| Layer 3 (RAG) | `context_recall` | points (0–1) | higher is better | ≥ 0.70 |
| Layer 3 (RAG) | `context_precision` | points (0–1) | higher is better | ≥ 0.70 |

> **Notes**:
> - `latency` is measured at **P95 (95th percentile)**, not the mean.
> - `quality` is on a **0–5 scale**, not 0–10.
> - `hallucination`, `output_leakage`, `privilege_escalation`, and `tool_chain_attack` are better when lower (the "below bar" direction is inverted).

---

## 4. Recommended values by environment

| Metric | Dev | Staging | Prod |
|--------|-----|---------|------|
| `tcr` | ≥ 70% | ≥ 80% | ≥ 85% |
| `accuracy` | ≥ 55% | ≥ 65% | ≥ 70% |
| `hallucination` | ≤ 15% | ≤ 8% | ≤ 5% |
| `quality` | ≥ 2.5 | ≥ 3.0 | ≥ 3.5 |
| `latency` (P95) | ≤ 15s | ≤ 8s | ≤ 5s |
| `cost_per_task` | ≤ 0.20 USD | ≤ 0.10 USD | ≤ 0.05 USD |

Start loose in the dev environment and tighten in stages before a production deployment.

---

## 5. CI/CD integration

### GitHub Actions

```yaml
name: Agent Quality Gate

on:
  push:
    branches: [main, staging]
  pull_request:

jobs:
  quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: pip install agent-evaluator

      - name: Run evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/run_evaluation.py

      - name: Quality Gate
        run: |
          agent-eval gate results/eval.json \
            --tcr 85 \
            --accuracy 70 \
            --llm-judge 3.5 \
            --hallucination 5

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-results
          path: results/
```

### pytest quality gate

```python
# tests/test_quality_gate.py
import pytest
from agent_evaluator import QuickEval

def test_quality_gate():
    eval = QuickEval("results/")

    @eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return my_agent.invoke(question)

    for question, ground_truth in load_test_cases():
        agent(question, ground_truth=ground_truth)

    passed = eval.gate(tcr=80, accuracy=65, raise_on_fail=False)
    assert passed, "Agent did not meet quality thresholds"

def test_latency_gate():
    eval = QuickEval("results/")
    # ... run the evaluation ...
    passed = eval.gate(latency=8.0, raise_on_fail=False)
    assert passed, "P95 latency exceeded the 8s threshold"
```

```bash
pytest tests/test_quality_gate.py -v
```

### GitLab CI

```yaml
evaluate:
  stage: test
  script:
    - pip install agent-evaluator
    - python scripts/run_eval.py
    - agent-eval gate results/eval.json --tcr 85 --accuracy 70
  artifacts:
    paths:
      - results/
    when: always
```

### Golden-dataset regression test

> This pattern **re-runs** the agent to check whether it passes the golden set. To check golden-set
> coverage / pass status from an already-produced result JSON alone (no re-run), use
> `--golden-set` / `--fail-on-golden-regression` (v0.9.8+) from "Method 1 — CLI gate" above.

```python
# tests/test_quality_regression.py
from agent_evaluator import QuickEval

def test_quality_regression(golden_dataset):
    eval = QuickEval("results/")

    @eval.qa
    def agent(question, ground_truth=""):
        return my_agent(question)

    for pair in golden_dataset["qa_pairs"]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    assert eval.gate(tcr=85, accuracy=70, raise_on_fail=False), (
        f"Quality regression detected: {eval.summary()}"
    )
```

---

## 6. Managing threshold files

Rather than hard-coding thresholds in code, manage them in a file so you can separate configuration per environment.

### File creation — automatic

```python
# Auto-generate gate_config.json at 95% of the current results
eval.generate_gate_config("gate_config.json")
```

### File creation — manual

```json
{
  "tcr": 85.0,
  "accuracy": 70.0,
  "quality": 3.5,
  "hallucination": 5.0,
  "latency": 5.0
}
```

### Loading the file from the Python API

`QuickEval.gate(config_file=...)` reads thresholds from a JSON file. The CLI (`agent-eval gate`) has no `--config` flag, so use the Python API.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
eval.gate(config_file="gate_config.json")
# or split per environment
import os
env = os.environ.get("DEPLOY_ENV", "prod")
eval.gate(config_file=f"gate_config.{env}.json")
```

### Loading the file from code (PerformanceMonitor)

```python
import json
from agent_evaluator import PerformanceMonitor

with open("gate_config.json") as f:
    thresholds = json.load(f)

monitor = PerformanceMonitor(output_dir="results/")
monitor.thresholds = thresholds
results = monitor.compare_with_thresholds()
```

---

## 7. Trend analysis (agent-eval trend)

Analyzes the TCR / accuracy trend across sequential run results and stops CI/CD when a regression is detected.

```bash
# Trend analysis of the TCR / accuracy of the last 10 result files
agent-eval trend results/

# Analyze only the last 5 files
agent-eval trend results/ --window 5

# exit 1 on a detected regression (CI/CD failure)
agent-eval trend results/ --fail-on-regression

# Save the analysis result as JSON
agent-eval trend results/ --output-json trend.json
```

---

## 8. Gate-regression root-cause diagnosis (agent-eval diagnose)

The step *after* `agent-eval gate` / `agent-eval trend` catch a regression — it automatically diagnoses "which gate got worse, because of which detail metric, and why" in three stages (detect → attribute → cross-reference). **It is not a CI gate** — it does not judge pass/fail; it only prints human-readable candidate causes and evidence (the HOTL principle). It works even without a baseline, by detecting gates currently in a fail/warn state.

```bash
# No baseline — detect gates currently in a fail/warn state
agent-eval diagnose results/latest.json

# Compare against a baseline — upgrade to regression-based detection
agent-eval diagnose results/latest.json --baseline results/baseline.json

# --show-diff: also show the actual git-commit change log between baseline ↔ current
agent-eval diagnose results/latest.json --baseline results/baseline.json --show-diff

# JSON output (for script integration)
agent-eval diagnose results/latest.json --json
```

The output includes the detection mode (`detection_mode`), the list of detected gates, each gate's `top_detail_deltas` (the detail metrics that moved most vs. the baseline), any related violations if a SQLite violation history exists, and — for Gate F — MAST (Cemri et al., NeurIPS 2025) failure-mode candidates. When Gates C and D are detected together, a check that first verifies whether SLA is the shared cause is also shown.

Python API: `agent_evaluator.rca.diagnose()` — for the detailed signature see the ["RCA diagnosis + recommendation history" section of `08_API_REFERENCE.md`](08_API_REFERENCE.md#14-rca-diagnosis--recommendation-history-agent_evaluatorrca--ontology). The dashboard 🔧 Improve tab visualizes the same result.

> To trace the git commit `--show-diff` points to back to "who wrote it, in which conversation" — an
> optional, core-independent personal tool — see
> [Workflow A in `CTX_SESSION_SEARCH.md`](CTX_SESSION_SEARCH.md#workflow-a--gate-regression--git-commit--source-session-trace-back).

---

## 9. Defining SLOs and the closed improvement loop

Where `gate` / `trend` / `diagnose` judge "can we deploy right now," the commands in this section **pin the baseline itself as a project SLO** and turn the diagnosis into a closed **hypothesis → action → re-verification** loop (SPEC-041 P27·P43·P49·P53·P57).

### 9.1 Pin project goals — `agent-eval target`

```bash
agent-eval target set --gate A=0.85 --gate E=0.95 --tcr 90   # written to .aoo/targets.json
agent-eval target show
```

Once set, `agent-eval gate` uses these values as thresholds unless `--gate-thresholds` is given, and every "below target" line in the report / insights is measured against **your bar**, not 0.7.

### 9.2 External reference distribution — `agent-eval benchmark`

```bash
agent-eval benchmark set --tcr 78 --gate A=0.75 --label support-rag   # a single reference value
agent-eval benchmark set --from-results results/                       # derive a percentile distribution from a results directory
agent-eval benchmark show
```

Once set, `insights.reference_frame` also reports this run's percentile and the gap to the frontier.

### 9.3 Improvement-experiment registry — `agent-eval experiment`

```bash
agent-eval experiment register --gate A --field avg_subtask_completion --predict-delta 0.08 --note "add SubtaskConfig"
agent-eval experiment list
agent-eval experiment score v3.json --baseline v2.json --persist   # score predicted vs actual, record a verdict
```

### 9.4 Closed improvement loop — `agent-eval improve`

```bash
agent-eval improve plan v3.json --baseline v2.json       # print per-gate proposals (component_shortfalls-based if no baseline)
agent-eval improve start v3.json --yes                   # register each proposal as an experiment + write .aoo/improve/*.md stubs
agent-eval improve verify v4.json --baseline v3.json --persist   # score predicted vs actual + resolve experiments + append recommendation_outcomes.jsonl
agent-eval improve patch v3.json --repo .                # emit a unified diff per proposal (prompt file / @agent_eval decorator) — never applied automatically
```

Once the two logs (`.aoo/experiments.jsonl`, `.aoo/recommendation_outcomes.jsonl`) accumulate, `insights.improvement_priors` folds them into a per-(gate, change-category) confirm-rate track record and surfaces it as the confidence of the next proposal.

---

## 10. Domain-specific Harness Config presets

Every domain has a different risk tolerance. Use the presets below as a starting point and adjust the thresholds to your domain.

### Medical AI (strict)

A life- and safety-critical system — a missed detection is worse than a false alarm.

```python
from agent_evaluator import (
    ThreatSeverityConfig, ComplianceConfig, SLAConfig,
    ExplainabilityConfig, FaultToleranceConfig,
)

MEDICAL_HARNESS = dict(
    # Gate E: halve the threat threshold (block even low-severity threats immediately)
    threat_severity=ThreatSeverityConfig(fail_score=4.0, fail_on_critical=True),
    # Gate E: HIPAA compliance + mandatory data minimization
    compliance=ComplianceConfig(
        compliance_framework="hipaa",
        pii_categories=["ssn", "medical_record", "diagnosis", "email", "phone"],
        require_data_minimization=True,
    ),
    # Gate D: strict response latency (a diagnostic-support system must respond fast)
    sla=SLAConfig(p95_ms=2000, p99_ms=4000),
    # Gate G: reasoning always required (for a doctor's review)
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=100,
        reasoning_markers=["왜냐하면", "따라서", "근거", "증거"],
    ),
    # Gate C: recovery required (no system outages allowed)
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.8,  # require ≥ 80% completeness
    ),
)
```

### Financial AI (strict)

Regulatory compliance + cost predictability are key.

```python
from agent_evaluator import (
    ComplianceConfig, SLAConfig, ResourceBudgetConfig,
    CostPredictabilityConfig, ThreatSeverityConfig,
)

FINANCE_HARNESS = dict(
    # Gate E: SOX/PCI-DSS compliance
    compliance=ComplianceConfig(
        compliance_framework="sox",
        pii_categories=["credit_card", "bank_account", "ssn", "tax_id"],
        require_data_minimization=True,
    ),
    # Gate D: very strict SLA (a delayed financial transaction = a loss)
    sla=SLAConfig(p95_ms=1000, p99_ms=2000),
    # Gate D: strict cost budget (control the per-request processing cost)
    resource_budget=ResourceBudgetConfig(max_tokens=800, max_cost_usd=0.005),
    # Gate D: minimize cost variability (budget predictability)
    # pass to the monitor constructor: PerformanceMonitor(cost_predictability_config=...)
    # CostPredictabilityConfig(max_coefficient_of_variation=0.2, min_samples=10)
    threat_severity=ThreatSeverityConfig(fail_score=5.0, fail_on_critical=True),
)
```

### General chatbot (relaxed)

User-experience-centric — fast iteration matters.

```python
from agent_evaluator import (
    SLAConfig, ComplianceConfig, ExplainabilityConfig,
)

CHATBOT_HARNESS = dict(
    # Gate D: generous SLA (a chatbot may take up to 5s)
    sla=SLAConfig(p95_ms=5000, p99_ms=10000),
    # Gate E: basic PII protection only
    compliance=ComplianceConfig(
        pii_categories=["email", "phone"],
        compliance_framework="general",
    ),
    # Gate G: reasoning optional (chatbots prefer concise answers)
    explainability=ExplainabilityConfig(
        require_reasoning=False,
        min_reasoning_length=0,
    ),
)
```

### Preset application pattern

```python
from agent_evaluator.decorators import agent_eval

# Choose the domain
DOMAIN = "medical"  # "medical" | "finance" | "chatbot"
PRESET = {"medical": MEDICAL_HARNESS, "finance": FINANCE_HARNESS, "chatbot": CHATBOT_HARNESS}[DOMAIN]

@agent_eval(monitor, task_type="qa", **PRESET)
def domain_agent(question: str, ground_truth: str = "") -> str:
    return f"domain-specific response: {question}"
```

### Threshold comparison by domain

| Item | Medical | Financial | General chatbot |
|------|---------|-----------|-----------------|
| SLA P95 | 2,000ms | 1,000ms | 5,000ms |
| ThreatSeverity fail_score | 4.0 | 5.0 | 7.0 (default) |
| Reasoning required | ✅ required | recommended | optional |
| PII categories | medical + personal | financial + personal | email · phone |
| Cost budget / request | — | $0.005 | $0.01 |

---

## 11. Best Practices

**Start conservative**
Setting strict thresholds from the outset produces many false failures. Start loose (`tcr: 70`, `accuracy: 55`) and tighten gradually as data accumulates.

**Anchor your baseline with `generate_gate_config()`**
When it is hard to set thresholds by hand, run enough evaluations first and then call `generate_gate_config()`. It auto-computes 95% of the current results.

**Remember latency is measured at P95**
The `latency` threshold applies to P95, not the mean. An agent averaging 2s can still have a P95 of 10s. Set the P95 target based on user experience.

**Quality is on a 0–5 scale**
The `quality` threshold ranges 0–5. `3.5` and above is the typical production bar. Do not confuse it with a 0–10 scale.

**Hallucination and security metrics have an inverted direction**
`hallucination`, `output_leakage`, `privilege_escalation`, and `tool_chain_attack` are better when lower. `compare_with_thresholds()` marks them with `direction: "lower_is_better"`.

**Keep a separate threshold file per environment**
Manage `gate_config.dev.json`, `gate_config.staging.json`, `gate_config.prod.json` separately and select via a CI/CD environment variable.

---

| Goal | Document |
|------|----------|
| Installation · basic usage | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| All 58 metrics in detail | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| Decorators · framework integration | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| Golden dataset · Korean RAG | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| Full output taxonomy (JSON · report · CLI · dashboard · AI runtime) | [09_OUTPUTS.md](09_OUTPUTS.md) |
| Docker · per-environment configuration | [07_OPERATIONS.md](07_OPERATIONS.md) |
| ctx session search (optional personal workflow) | [CTX_SESSION_SEARCH.md](CTX_SESSION_SEARCH.md) |
