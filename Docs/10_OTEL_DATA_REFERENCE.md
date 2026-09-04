# OpenTelemetry Data Reference

Everything Agent-Evaluator puts on the wire when OpenTelemetry export is enabled: the
spans, their attributes, the metrics, the Phoenix REST annotations, the transport, and
what a non-Phoenix backend does and does not understand.

**v1.0.2 | Python 3.8+** — companion to [`06_OBSERVABILITY.md`](06_OBSERVABILITY.md)
(dashboard + `agent-eval monitor` walkthrough).

---

## Table of Contents

1. [What emits, and when](#1-what-emits-and-when)
2. [Transport and wire format](#2-transport-and-wire-format)
3. [Span hierarchy](#3-span-hierarchy)
4. [Task span attributes](#4-task-span-attributes)
5. [Tool span attributes](#5-tool-span-attributes)
6. [Step span attributes](#6-step-span-attributes)
7. [Session span attributes](#7-session-span-attributes)
8. [Span status and timing](#8-span-status-and-timing)
9. [Metrics](#9-metrics)
10. [Phoenix annotations (REST, not OTLP)](#10-phoenix-annotations-rest-not-otlp)
11. [Experiment and dataset context](#11-experiment-and-dataset-context)
12. [Model-name resolution](#12-model-name-resolution)
13. [TaskType to span kind](#13-tasktype-to-span-kind)
14. [Attribute size limit](#14-attribute-size-limit)
15. [Failure isolation](#15-failure-isolation)
16. [Portability to non-Phoenix backends](#16-portability-to-non-phoenix-backends)
17. [Version and Python constraints](#17-version-and-python-constraints)
18. [Enabling and disabling](#18-enabling-and-disabling)
19. [Worked example](#19-worked-example)

---

## 1. What emits, and when

OpenTelemetry export is **opt-in**. Nothing is sent unless `setup_otel()` is called
**before** the `PerformanceMonitor` is constructed:

```python
from agent_evaluator import setup_otel, PerformanceMonitor
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor(output_dir="results/")
```

If `opentelemetry-sdk` is not installed, or `setup_otel()` is not called, every export
path is a silent no-op and the JSON result file is written exactly as before.

| Trigger | What is emitted | Code |
|---------|-----------------|------|
| `monitor.record_task(task)` (also via `@agent_eval`, `batch_eval`) | one **task span** + one **tool span per `tool_calls` entry** + (opt-in) one **step span per `chain_steps` entry**; queues per-task annotations; records the per-task metrics | `core/trackers/monitor.py::_emit_otel_span` |
| `with evaluation_session(...) as monitor:` / `hybrid_evaluation_session` / `async_evaluation_session` | one **session root span** wrapping the whole block | `core/monitor_context.py::_otel_ctx` |
| `monitor.save_to_file(...)` (also `auto_save`) | flushes the span batch, then POSTs **span / trace / session annotations** to Phoenix; sends the session-level `ae.tcr` metric | `_flush_phoenix_annotations`, `save_to_file` |
| `monitor.begin_experiment(name, ...)` | POSTs to Phoenix `/v1/experiments`; every later task span then carries `ae.experiment_id` / `ae.experiment_name` | `begin_experiment` |
| `QuickEval(...).replay(file)` / `.watch(dir)`, `PerformanceMonitor.load_from_file`, `monitor.rehydrate_from_storage(db)` | re-plays saved `TaskResult`s through `record_task()` → re-emits spans (see [§19](#19-worked-example) note on timing) | — |

---

## 2. Transport and wire format

### Traces

- Exporter: `OTLPSpanExporter` (`opentelemetry.exporter.otlp.proto.http`), **OTLP/HTTP + protobuf**.
- Endpoint: `{endpoint}/v1/traces` — the standard OTLP/HTTP path. `setup_otel(endpoint="http://host:4318")` → `http://host:4318/v1/traces`.
- Processor: `BatchSpanProcessor` (async, batched). `provider.force_flush(timeout_ms=…)` is called at the start of `save_to_file()`'s annotation flush.
- Header: `x-phoenix-project-name: <service_name>` — a Phoenix routing hint; harmless and ignored by other backends.

### Resource attributes (attached to every span)

| Attribute | Value | Standard? |
|-----------|-------|-----------|
| `service.name` | `service_name` (default `"agent-evaluator"`) | OTel standard |
| `openinference.project.name` | `service_name` | OpenInference (Arize) — Phoenix project routing |

### Metrics

- Exporter: `OTLPMetricExporter` → `{endpoint}/v1/metrics` (standard OTLP/HTTP path).
- Reader: `PeriodicExportingMetricReader`, `export_interval_millis = 15_000` (batch every 15 s).
- **Off by default.** Enable with `setup_otel(..., enable_metrics=True)`. Phoenix does not accept `/v1/metrics` (returns HTTP 405) — point metrics at Grafana / an OpenTelemetry Collector / any OTLP metrics receiver.

### Annotations

Not OpenTelemetry at all — plain HTTP `POST` to Phoenix REST endpoints. See [§10](#10-phoenix-annotations-rest-not-otlp).

---

## 3. Span hierarchy

```
ae.session/{label}                         (CHAIN)   -- only inside evaluation_session()/…; wraps the block
└─ ae.task/{task_type}/{task_id}           (LLM|RETRIEVER|TOOL|AGENT|CHAIN)   -- one per record_task()
   ├─ ae.tool/{task_id}/{tool_name}        (TOOL)    -- one per result.tool_calls entry; always
   └─ ae.step/{task_id}/{step_name}        (CHAIN)   -- one per result.chain_steps entry; only if enable_otel_child_spans=True
```

| Span | Name | `openinference.span.kind` | Emitted |
|------|------|---------------------------|---------|
| Session root | `ae.session/{label}` or `ae.session` | `CHAIN` | only via the `evaluation_session()` family of context managers |
| Task | `ae.task/{task_type}/{task_id}` | per [§13](#13-tasktype-to-span-kind) map (default `LLM`) | every `record_task()` |
| Tool | `ae.tool/{task_id}/{tool_name}` | `TOOL` | for each `dict` in `result.tool_calls` — **no flag needed** |
| Step | `ae.step/{task_id}/{step_name}` | `CHAIN` | only when `PerformanceMonitor(enable_otel_child_spans=True)`, for each `result.chain_steps` (or `extra["streaming_steps"]`) entry |

`task_type` in the span name is the lower-cased short label (`TaskType.QA` → `qa`).

---

## 4. Task span attributes

### OpenInference standard (what Phoenix UI columns / charts read)

| Attribute | Value |
|-----------|-------|
| `openinference.span.kind` | `LLM` / `RETRIEVER` / `TOOL` / `AGENT` / `CHAIN` — from [§13](#13-tasktype-to-span-kind) |
| `input.value` | `result.question` (falls back to `task_id`) |
| `output.value` | `result.response` (falls back to `str(completion_score)`) |
| `input.mime_type` / `output.mime_type` | `"text/plain"` — set only when `input.value` is non-empty |
| `session.id` | `monitor._otel_session_id` (`"{session_label}_{uid}"`, or just `uid`) |
| `metadata` | JSON string: `{"task_type", "framework"?, "partial_reason"?}` |
| `llm.token_count.prompt` | `tokens_used["input"]`; for an integer `tokens_used`, an 80 % split of the total |
| `llm.token_count.completion` | `tokens_used["output"]`; for an integer `tokens_used`, the remaining 20 % |
| `llm.token_count.total` | prompt + completion |
| `llm.model_name` | resolved + aliased model name — see [§12](#12-model-name-resolution) |
| `llm.prompts` | JSON `[{"role":"user","content":<question>}, {"role":"assistant","content":<ground_truth>}?]` — set only when `input.value` is non-empty; `assistant` entry only when `ground_truth` is present |
| `retrieval.documents` | JSON `[{"document.id":"0","document.content":<context, truncated>}]` — **`information_retrieval` task type only**, and only when `result.context` is set |

### Agent-Evaluator native (`ae.*`)

| Attribute | Type | Value |
|-----------|------|-------|
| `ae.task_id` | str | `result.task_id` |
| `ae.task_type` | str | full enum spelling, e.g. `"TaskType.QA"` |
| `ae.success` | bool | `result.success` |
| `ae.completion_score` | float | `result.completion_score` (0–1) |
| `ae.accuracy_score` | float | `result.accuracy_score` (0–1) |
| `ae.execution_time` | float | seconds |
| `ae.tokens_used` | int | prompt + completion |
| `ae.tool_calls_count` | int | `len(result.tool_calls)` |
| `ae.attempts` | int | `result.attempts` (retry count) |
| `ae.framework` | str | `result.framework` or `"native"` |
| `ae.anomaly_detection_enabled` | bool | `monitor.enable_anomaly_detection` |
| `ae.source` | str | `monitor.session_label` — set only when a label was given |
| `ae.question` / `ae.response` / `ae.ground_truth` | str | full text, truncated to [§14](#14-attribute-size-limit) |

### Conditional (only when the corresponding feature ran)

| Attribute | When | Value |
|-----------|------|-------|
| `ae.hallucination_rate` | hallucination detection enabled and ≥ 1 evaluation | `HallucinationDetector.get_hallucination_rate()["overall_rate"]` (0–1, lower is better) |
| `ae.quality_score` | `ResponseQualityEvaluator` has ≥ 1 evaluation | `avg_total_score / 10`, capped at 1.0, rounded to 4 dp |
| `ae.llm_judge_score` | `result.llm_judge` dict present | `overall` / `score` / `avg_score`, rounded to 4 dp |
| `ae.llm_judge_completeness` / `ae.llm_judge_relevance` / `ae.llm_judge_factual` | same, per sub-key | rounded to 4 dp |
| `ae.security_events_count` | `result.security_metrics` dict present | `inputs_with_threats + outputs_with_leakage + unauthorized_calls` |
| `ae.tool_names` | `result.tool_calls` non-empty | JSON array of tool-name strings |
| `ae.experiment_id` / `ae.experiment_name` | after `monitor.begin_experiment(...)` | the Phoenix experiment id / name |
| `dataset.id` | a Phoenix dataset id was recorded on the monitor | that id |
| `dataset.version` / `dataset.record_count` | golden datasets were loaded onto the monitor | most-recent dataset name / count |

---

## 5. Tool span attributes

`ae.tool/{task_id}/{tool_name}` — one per `dict` entry in `result.tool_calls`.

| Attribute | Value |
|-----------|-------|
| `openinference.span.kind` | `"TOOL"` |
| `tool.name` | `tool_call["tool_name"] \|\| ["tool"] \|\| ["name"] \|\| "tool_{i}"` |
| `input.value` | `tool_call["arguments"] \|\| ["args"]` — JSON if a dict, else `str()`; truncated to [§14](#14-attribute-size-limit) |
| `output.value` | `tool_call["result"] \|\| ["output"]` — `str()`, truncated |
| `ae.task_id` | parent task id |
| `ae.tool_index` | int, position in `tool_calls` |
| `session.id` | `monitor._otel_session_id` |

**Status:** `StatusCode.ERROR, "tool call failed"` when `tool_call.get("success", True)` is `False`.

**Timing:** tool spans are laid out evenly across the parent task's execution window
(`parent_start + index * (exec_time / n_tools)`), preserving call order.

---

## 6. Step span attributes

`ae.step/{task_id}/{step_name}` — **only** when `PerformanceMonitor(enable_otel_child_spans=True)`,
one per entry in `result.chain_steps` (or `result.extra["streaming_steps"]`).

| Attribute | Value |
|-----------|-------|
| `openinference.span.kind` | `"CHAIN"` |
| `ae.task_id` | parent task id |
| `ae.step_index` | int |
| `ae.step_name` | `step["name"] \|\| step["type"] \|\| "step_{i}"` |
| `ae.step_type` | `step.get("type", "step")` |
| `ae.step_success` | `bool(step.get("success", True))` |
| `ae.execution_time` | `float(step["execution_time"] \|\| step["timestamp"] \|\| 0.0)` |
| `input.value` / `output.value` | `step["input"]` / `step["output"]` if present, truncated to [§14](#14-attribute-size-limit) |

---

## 7. Session span attributes

`ae.session/{label}` (or `ae.session` if no label) — created by `evaluation_session()`,
`hybrid_evaluation_session()`, `async_evaluation_session()`. Wraps the whole `with`
block; the block's `save_to_file()` runs on exit (even on exception).

| Attribute | Value |
|-----------|-------|
| `openinference.span.kind` | `"CHAIN"` |
| `ae.session_file` | the output filename passed to the context manager |
| `ae.source` | the session label |
| `session.id` | `monitor._otel_session_id` |

---

## 8. Span status and timing

- **Error status.** A task span whose `result.success` is `False` gets
  `StatusCode.ERROR, "task failed"`. A tool span whose `tool_call["success"]` is `False`
  gets `StatusCode.ERROR, "tool call failed"`. These feed Phoenix's
  "Traces with errors" / "LLM span errors" / "Tool span errors" panels.
- **Start time is back-calculated.** Each span is started at `now − execution_time`
  (nanoseconds), not at `result.timestamp`. This keeps spans inside Phoenix's
  "Last 15 min" style time filters and makes the latency charts reflect the real
  per-task duration even when the `TaskResult` carries a simulated / historical
  timestamp. A consequence: **replayed** results (`QuickEval.replay`, `load_from_file`,
  `rehydrate_from_storage`) are timestamped at replay time, not their original run time.

---

## 9. Metrics

Opt-in: `setup_otel(..., enable_metrics=True)`. Batch-exported every 15 s to
`{endpoint}/v1/metrics`. Phoenix has no metrics endpoint — use Grafana / a Collector.

| Metric | Instrument | Unit | Attributes | Cadence |
|--------|-----------|------|------------|---------|
| `ae.tcr` | gauge (`up_down_counter`) | % (0–100) | none | **session-level** — sent once, at the end of `save_to_file()` |
| `ae.accuracy` | gauge (`up_down_counter`) | 0–1 | `task_type`, `framework` | per task |
| `ae.latency_seconds` | histogram | seconds | `task_type`, `framework` | per task |
| `ae.tokens_total` | counter | tokens | `task_type`, `framework` | per task |
| `ae.error_rate` | gauge (`up_down_counter`) | `0.0` on success / `100.0` on failure | `task_type`, `framework` | per task |

`ae.tcr` is deliberately session-scoped (from `tcr_tracker.calculate_tcr()["tcr"]`) to
avoid a per-task-sum artefact.

---

## 10. Phoenix annotations (REST, not OTLP)

On `save_to_file()`, the per-task scores are pushed to Phoenix at three levels. This is
**Phoenix-specific REST**, not part of OTLP.

### Endpoint probe (guards the whole block)

`GET {endpoint}/arize_phoenix_version`, once per base URL, cached:

| Probe result | Behaviour |
|--------------|-----------|
| `phoenix` (HTTP 2xx) | full retry treatment below |
| `unknown` (other HTTP status — a proxy, a future Phoenix that moved the route) | each tier is attempted **once**, no backoff |
| `unreachable` (connection error) | annotation POSTs are **skipped entirely** (traces/metrics already went out over OTLP) |

### Per task — `POST /v1/span_annotations?sync=true` **and** `POST /v1/trace_annotations?sync=true`

`annotator_kind: "CODE"` (all deterministic computed values).

| Annotation name | Score | Label rule |
|-----------------|-------|-----------|
| `accuracy` | `result.accuracy_score` (0–1) | `pass` if ≥ 0.5, else `fail` |
| `completion` | `result.completion_score` (0–1) | `pass` / `fail` |
| `success` | `1.0` / `0.0` | `pass` / `fail` |
| `hallucination` | hallucination score (0–1) — **omitted if not measured** | `pass` if ≤ 0.3, else `fail` |
| `quality` | response-quality score (0–1) — **omitted if not measured** | `pass` / `fail` |
| `latency_s` | `execution_time` in seconds | `ok` (no direction) |
| `tool_calls` | number of tool calls | `ok` |
| `attempts` | retry-attempt count | `ok` |

### Per session — `POST /v1/session_annotations?sync=true`

One rollup row per metric, the mean over the session's tasks:
`session_accuracy`, `session_completion`, `session_pass_rate`, `session_latency_s`,
`session_hallucination`, `session_quality`. Same `annotator_kind` and label rules.

### Delivery mechanics

- `?sync=true` — Phoenix processes synchronously so the response is decisive.
- **HTTP 404** (span/trace/session not yet indexed by Phoenix's async ingest) → retry on an
  exponential backoff. Default `0.5, 1, 2, 4` s; override with
  `AGENT_EVAL_PHOENIX_ANNOTATION_RETRY_DELAYS="1,2,4,8,16"`.
- **Non-404 HTTP error** (e.g. 422) → no retry, log and stop that tier.
- **Connection error** → give up after 2 attempts.
- The three tiers are posted **independently** — one failing does not block the others.
  If the span POST succeeds, trace and session are posted without retry (indexing is
  already confirmed).

---

## 11. Experiment and dataset context

- `monitor.begin_experiment(name, dataset_id=None, description="", phoenix_endpoint=...)`
  → `POST {phoenix_endpoint}/v1/experiments`. On success it stores
  `_phoenix_experiment_id` / `_phoenix_experiment_name` / `_phoenix_dataset_id`, and
  every subsequent task span carries `ae.experiment_id` / `ae.experiment_name`
  (+ `dataset.id` if a dataset was linked). Returns `None` and no-ops on any failure.
- `GoldenSetBuilder.upload_to_phoenix(...)` / `.push_to_phoenix(...)` and
  `agent-eval monitor --sync-datasets '<glob>'` upload golden-set JSON via Phoenix's
  **GraphQL** `createDataset` mutation (`{phoenix_endpoint}/graphql`).
- `agent-eval monitor` polls `GET {ui_url}/v1/projects` in a background thread to print a
  `[new] project` line when one appears.

All of the above are Phoenix REST/GraphQL, not OTLP.

---

## 12. Model-name resolution

`llm.model_name` on a task span is resolved in this order, then run through an alias map
so Phoenix's LiteLLM cost table can price it:

1. `tokens_used["model"]` (per-task, e.g. via `create_taskresult(model_name=...)` or `EvalMetadata(tokens_used={"model": ...})`)
2. `PerformanceMonitor(model_name=...)` (session-wide)
3. `"ae/unspecified"` (fallback — **not priceable**, so Cost / "Top models by cost" panels stay empty)

Alias map (`_PHOENIX_MODEL_ALIAS`):

| Given | Sent as |
|-------|---------|
| `claude-opus-4-6` | `claude-3-opus-20240229` |
| `claude-sonnet-4-6` | `claude-3-5-sonnet-20241022` |
| `claude-haiku-4-5`, `claude-haiku-4-5-20251001` | `claude-3-5-haiku-20241022` |
| `gpt-4o-mini-2024-07-18` | `gpt-4o-mini` |
| `gpt-4o-2024-11-20`, `gpt-4o-2024-08-06` | `gpt-4o` |

Anything not in the map is passed through unchanged.

---

## 13. TaskType to span kind

`_OTEL_SPAN_KIND_MAP`:

| `task_type` | `openinference.span.kind` |
|-------------|---------------------------|
| `qa`, `code_generation`, `coding`, `creative`, `document_creation`, `reasoning` | `LLM` |
| `information_retrieval` | `RETRIEVER` |
| `tool_use` | `TOOL` |
| `planning` | `AGENT` |
| `data_analysis` | `CHAIN` |
| anything else (`multi_agent`, `streaming`, unmapped) | `LLM` (default) |

---

## 14. Attribute size limit

`_OTEL_ATTR_MAX_LEN = 4096` characters. Applied to `ae.question`, `ae.response`,
`ae.ground_truth`, tool-span `input.value` / `output.value`, step-span
`input.value` / `output.value`, and the `retrieval.documents` document content.
Other attributes (`input.value` / `output.value` on the task span itself, `llm.prompts`,
`metadata`) are sent whole.

---

## 15. Failure isolation

Every OTEL path is wrapped so a telemetry problem can never break evaluation:

- Provider / metrics setup failure → the wrapper switches to no-op mode (`logger.warning`).
- Per-span attribute set, child-span emit, status set → each in its own `try/except` → `logger.debug`, span still closes.
- Annotation POST → caught, retried per [§10](#10-phoenix-annotations-rest-not-otlp), then `logger.warning` and move on.
- `opentelemetry-sdk` not installed, or `setup_otel()` never called → `get_provider()` / `get_metrics()` return `None` and `_emit_otel_span()` returns immediately.

The JSON result file is written on the same code path regardless of any OTEL outcome.

---

## 16. Portability to non-Phoenix backends

`setup_otel()` uses the **standard OTLP/HTTP exporters**. Point `endpoint` at any
OTLP/HTTP receiver (Jaeger, Grafana Tempo, Datadog, Honeycomb, New Relic, an
OpenTelemetry Collector) and traces + metrics flow **with no code change**:

```python
setup_otel(endpoint="http://otel-collector:4318", service_name="my-agent",
           enable_metrics=True)
```

| Layer | Portability |
|-------|-------------|
| Span tree, parent/child, `status=ERROR`, timings, `service.name`, all `ae.*` values, the 5 metrics | **Fully standard** — every OTLP backend ingests and renders it |
| `openinference.span.kind`, `input.value` / `output.value`, `llm.token_count.*`, `llm.model_name`, `llm.prompts`, `retrieval.documents`, `session.id`, `metadata` | **OpenInference** semantic conventions — **not** OTel's `gen_ai.*`. Delivered as plain attributes everywhere; only Phoenix / Arize give them dedicated LLM UI. A backend keyed on `gen_ai.*` will not auto-classify these as LLM spans. |
| `x-phoenix-project-name` header, `openinference.project.name` resource attr | Phoenix routing hints — ignored (harmless) elsewhere |
| Evaluation-score annotations (`/v1/span_annotations`, `/v1/trace_annotations`, `/v1/session_annotations`), `/v1/experiments`, `/v1/datasets`, `/v1/prompts`, `/graphql`, `/v1/projects` | **Phoenix REST/GraphQL only** — not OTLP. The `/arize_phoenix_version` probe ([§10](#10-phoenix-annotations-rest-not-otlp)) makes the SDK skip the annotation POSTs against a non-Phoenix endpoint. To keep scores elsewhere, read them from the `save_to_file()` JSON and push them yourself. |

---

## 17. Version and Python constraints

| Package | Pin (in `pyproject.toml`, extras `otel` / `sdk` / `examples` / `full`) |
|---------|------------------------|
| `opentelemetry-sdk` | `>=1.20.0,<2.0.0` |
| `opentelemetry-exporter-otlp-proto-http` | `>=1.20.0,<2.0.0` |
| `arize-phoenix` (Python 3.12+) | `>=15.4.0,<21.0.0` — Phoenix v20 is allowed; with `openai<3.0.0` the resolver lands on `arize-phoenix 20.3.x`. v20's breaking changes (inferences / embeddings / UMAP removal) do not touch the OTLP or annotation surface. |
| `arize-phoenix` (Python 3.10 / 3.11) | `>=15.4.0,<19.0.0` — Phoenix **19.11+ and all 20.x require Python 3.12**: `phoenix.trace.dsl.filter._FilterBindings` is a frozen dataclass whose `boolean_names` field defaults to `MappingProxyType({})`, which CPython < 3.12 rejects as a "mutable default" at import — the Phoenix server / `agent-eval monitor` crash on startup. (`MappingProxyType` became hashable in Python 3.12, gh-87995.) |
| `arize-phoenix` (Python 3.8 / 3.9) | not installed — the line is marker-dropped because `arize-phoenix>=17` needs `arize-phoenix-otel` (Python ≥ 3.10). Only `opentelemetry-*` install; `setup_otel()` to a remote / Docker Phoenix or any other OTLP backend still works. |

Phoenix serves the UI and the OTLP/HTTP trace receiver on the **same port** (default
6006); the OTLP **gRPC** receiver is on 4317. Phoenix does **not** implement `/v1/metrics`
(HTTP 405).

---

## 18. Enabling and disabling

```python
from agent_evaluator import setup_otel

# Default: Phoenix on localhost, traces only
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

# Any OTLP backend + metrics
setup_otel(endpoint="http://otel-collector:4318", service_name="my-agent",
           enable_metrics=True)

# Explicit no-op (CI): just don't call setup_otel(), or
setup_otel(enabled=False)
```

- `setup_otel()` **must** run before `PerformanceMonitor(...)` is constructed.
- Child step spans: `PerformanceMonitor(enable_otel_child_spans=True)`.
- Per-viewer auto-reload of new Phoenix projects: a browser-console snippet is in
  [`06_OBSERVABILITY.md` §7](06_OBSERVABILITY.md).

---

## 19. Worked example

```python
from agent_evaluator import setup_otel, PerformanceMonitor, create_taskresult

setup_otel(endpoint="http://localhost:6006", service_name="demo")
monitor = PerformanceMonitor(output_dir="results/", model_name="claude-haiku-4-5-20251001")

task = create_taskresult(
    task_id="t1", question="Capital of France?", response="Paris.",
    ground_truth="Paris", execution_time=0.8, task_type="qa",
    tokens_used={"input": 40, "output": 3, "total": 43},
    tool_calls=[{"tool_name": "web_search", "arguments": {"q": "capital france"},
                 "result": "Paris", "success": True}],
)
monitor.record_task(task)      # -> 1 task span + 1 tool span, annotations queued, metrics recorded
monitor.save_to_file("demo")   # -> flush spans; POST span/trace/session annotations
```

On the wire:

**Span `ae.task/qa/t1`** (kind `LLM`, status `OK`, started at `now − 0.8 s`):
`input.value="Capital of France?"`, `output.value="Paris."`,
`llm.model_name="claude-3-5-haiku-20241022"` (aliased),
`llm.token_count.prompt=40 / .completion=3 / .total=43`,
`session.id="<uid>"`, `ae.success=true`, `ae.accuracy_score≈1.0`,
`ae.execution_time=0.8`, `ae.tool_calls_count=1`, `ae.framework="native"`,
`ae.question` / `ae.response` / `ae.ground_truth`, `ae.tool_names='["web_search"]'`,
`llm.prompts='[{"role":"user",...},{"role":"assistant","content":"Paris"}]'`,
`metadata='{"task_type":"qa"}'`.

**Child span `ae.tool/t1/web_search`** (kind `TOOL`, status `OK`):
`tool.name="web_search"`, `input.value='{"q": "capital france"}'`,
`output.value="Paris"`, `ae.task_id="t1"`, `ae.tool_index=0`.

**Annotations** (`annotator_kind="CODE"`) — on `save_to_file()`, to
`/v1/span_annotations`, `/v1/trace_annotations`, and (rolled up)
`/v1/session_annotations`: `accuracy`, `completion`, `success`, `latency_s`,
`tool_calls`, `attempts` (+ `session_*` variants). `hallucination` / `quality` are
omitted because neither evaluator ran.

**Metrics** (only if `enable_metrics=True`): `ae.accuracy`, `ae.latency_seconds`,
`ae.tokens_total`, `ae.error_rate` per task; `ae.tcr` once at `save_to_file()`.

---

## See also

| Topic | Doc |
|-------|-----|
| End-to-end runnable example — a local **Ollama** model streaming real spans / metrics / annotations to Phoenix, all 7 Gates + JSON + HTML + dashboard | [`../Evaluator_Examples/ch32_ollama_realtime.py`](../Evaluator_Examples/ch32_ollama_realtime.py) |
| Dashboard, `agent-eval monitor` walkthrough, Phoenix per-tab guide | [`06_OBSERVABILITY.md`](06_OBSERVABILITY.md) |
| Result JSON / HTML report / CLI / dashboard output taxonomy | [`09_OUTPUTS.md`](09_OUTPUTS.md) |
| Install variants, per-environment config | [`07_OPERATIONS.md`](07_OPERATIONS.md) |
| `setup_otel()` / `PerformanceMonitor` API | [`08_API_REFERENCE.md`](08_API_REFERENCE.md) |
