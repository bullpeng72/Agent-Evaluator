# Integration Guide

The full decorator API reference · 24 framework integrations · comparison with other evaluation tools.

**v1.0.1 | Python 3.8+**

---

## Table of Contents

1. [The 3 decorator styles](#1-the-3-decorator-styles)
2. [@agent_eval — single call](#2-agent_eval--single-call)
3. [@batch_eval — bulk processing](#3-batch_eval--bulk-processing)
4. [@conversation_eval — multi-turn conversations](#4-conversation_eval--multi-turn-conversations)
5. [QuickEval — convenience factory](#5-quickeval--convenience-factory)
6. [Evaluation-result output scenarios](#6-evaluation-result-output-scenarios)
7. [Full parameter reference](#7-full-parameter-reference)
8. [Parameter → metric activation map](#8-parameter--metric-activation-map)
9. [Metric × decorator support matrix](#9-metric--decorator-support-matrix)
10. [Data-source priority](#10-data-source-priority)
11. [Reading metrics from the report](#11-reading-metrics-from-the-report)
12. [Framework integration](#12-framework-integration)
13. [Metric support matrix (by framework)](#13-metric-support-matrix-by-framework)
14. [Comparison with other evaluation tools](#14-comparison-with-other-evaluation-tools)

---

## 1. The 3 decorator styles

The SDK's standard interface is three decorators, unified by use case.

| Decorator | Use case | One line of code |
|-----------|----------|-----------------|
| `@agent_eval` | single call (single-turn) | `@agent_eval(monitor)` |
| `@batch_eval` | list-based bulk processing (batch) | `@batch_eval(monitor)` |
| `@conversation_eval` | multi-turn conversation session | `@conversation_eval(monitor)` |

> `QuickEval` (`eval = QuickEval()`) is a **factory tool** for configuring the decorators above more concisely.

---

## 2. @agent_eval — single call

The most general-purpose style. It auto-detects and handles both synchronous (`def`) and asynchronous (`async def`) functions.

### Basic usage

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### RAG + hallucination mode

```python
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
```

### LLM Judge + Faithfulness

Using `rag_mode=True` together with `llm_judge=LLMJudgeConfig()` makes LLMJudge add a `faithfulness` dimension automatically.
This is a **native replacement** for the Ragas `faithfulness` metric — it works without the `[eval]` extra.

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"),  # adds the faithfulness dimension automatically
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
```

### G-Eval custom criteria (`criteria`)

Define service-specific evaluation criteria as a `criteria` list. This natively replaces DeepEval's G-Eval.

```python
@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6", criteria=["professionalism", "empathy", "clarity"]),
)
def customer_service_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# result: task.extra["llm_judge"]["criteria_scores"]
# → {"professionalism": 4.0, "empathy": 4.5, "clarity": 4.8}
```

---

## 3. @batch_eval — bulk processing

Use it to evaluate a large amount of data at once. It supports parallel execution (`concurrency=N`).

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa", concurrency=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

---

## 4. @conversation_eval — multi-turn conversations

Accumulates conversational context keyed by `session_id`.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

chat_agent("Hello", sid="user_1")
chat_agent("What's the weather?", sid="user_1")
flush_conversation("user_1")   # compute ConversationMetrics and save

# ConversationMetrics output fields (8):
# turn_count, overall_score, context_retention, topic_coherence,
# progressive_depth, session_completion, avg_turn_latency, turn_scores
```

---

## 5. QuickEval — convenience factory

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                   # task_type="qa"
def my_agent(q, ground_truth=""): ...

@eval.rag                  # task_type="information_retrieval" + hallucination
def rag_agent(q, context="", ground_truth=""): ...

eval.save()                # quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)   # CI/CD gating

# Purpose-specific factories
eval = QuickEval.for_rag("results/")
eval = QuickEval.for_security("results/")
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# Shortcut decorators: qa, tool_use, rag, code, reasoning, planning,
#                      data_analysis, creative, multi_agent, secure, streaming
```

---

## 6. Evaluation-result output scenarios

### Scenario 1 — terminal output

```python
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

report = monitor.generate_report()
print(report.to_json(indent=2))
```

### Scenario 2 — FastAPI dashboard

```python
monitor.save_to_file("eval")     # creates results/eval.json + .html
```

```bash
agent-eval dashboard results/ --watch    # http://localhost:8765
```

### Scenario 3 — Phoenix OTEL real-time monitoring

`setup_otel()` must be called **before the PerformanceMonitor is created**.

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 7. Full parameter reference

> This section lists the common decorator parameters. All 33 Harness Config parameters (`instructions=`, `sla=`, `scope=`, …) are also accepted by every decorator — see [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md#harness-config-activation-33) for the full list.

### `@agent_eval` — all parameters

| Parameter | Type | Default | Role |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (required) | the monitor instance that records results |
| `task_type` | str | `"qa"` | qa / tool_use / information_retrieval / code_generation / reasoning / planning / data_analysis / creative / coding / multi_agent |
| `question_arg` | str | `"question"` | name of the function argument holding the question |
| `ground_truth_arg` | str | `"ground_truth"` | name of the function argument holding the reference answer |
| `context_arg` | str\|None | `None` | name of the RAG context argument (auto-set to `"context"` when `rag_mode=True`) |
| `expected_tools_arg` | str\|None | `None` | name of the argument holding the expected-tool list for Tool Selection F1 |
| `task_id_prefix` | str | `"task"` | prefix for auto-generated task_id values |
| `task_id_fn` | callable\|None | `None` | task_id generator `(args, kwargs) → str` |
| `framework` | str | `"native"` | framework adapter to use (24 supported) |
| `model_name` | str | `""` | model name for token-cost calculation |
| `score_fn` | callable\|None | `None` | custom accuracy_score function `(response, ground_truth) → float` |
| `completion_fn` | callable\|None | `None` | custom completion_score function `(response, ...) → float` |
| `custom_parser` | callable\|None | `None` | custom metadata parser `(raw_result) → EvalMetadata` |
| `sample_rate` | float | `1.0` | record sampling rate (0.0–1.0) |
| `timeout` | float\|None | `None` | timeout (seconds); raises TimeoutError if exceeded |
| `enabled` | bool | `True` | if False, the decorator is fully disabled |
| `retry` | RetryConfig\|None | `None` | retry settings (`RetryConfig(max=N, delay=X, backoff=Y)`) |
| `on_record` | callable\|None | `None` | callback after recording `(TaskResult)` |
| `on_error` | callable\|None | `None` | callback on error `(exc, TaskResult)` |
| `alert_rules` | list | `[]` | list of SimpleTaskAlertRule |
| `flush_every` | int\|None | `None` | call save_to_file() automatically every N records |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS name (production/development/testing/canary) |
| `enable_hallucination_detection` | bool | `False` | temporarily enable HallucinationDetector |
| `rag_mode` | bool | `False` | auto-sets context_arg="context" + hallucination + task_type="information_retrieval" |
| `security` | SecurityConfig\|None | `None` | temporarily enable the 5 security trackers (set a whitelist with `SecurityConfig(allowed_tools=[...])`) |
| `llm_judge` | LLMJudgeConfig\|None | `None` | LLMJudge settings (`LLMJudgeConfig(model=..., criteria=[...])`) |
| `enable_anomaly_detection` | bool | `False` | temporarily enable AnomalyDetector |

### `@batch_eval` — all parameters

| Parameter | Type | Default | Role |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (required) | the monitor instance that records results |
| `task_type` | str | `"qa"` | task type |
| `questions_arg` | str | `"questions"` | name of the questions-list argument |
| `ground_truths_arg` | str | `"ground_truths"` | name of the reference-answers-list argument |
| `contexts_arg` | str\|None | `None` | name of the RAG contexts-list argument |
| `expected_tools_arg` | str\|None | `None` | name of the expected-tool-list argument |
| `framework` | str | `"native"` | framework adapter |
| `score_fn` | callable\|None | `None` | custom accuracy_score function |
| `on_record` | callable\|None | `None` | per-item record-complete callback |
| `on_batch_complete` | callable\|None | `None` | whole-batch complete callback |
| `on_batch_progress` | callable\|None | `None` | progress callback `(done, total)` |
| `on_item_error` | callable\|None | `None` | per-item error handler `(exc, idx, question) → str` |
| `alert_rules` | list | `[]` | list of SimpleTaskAlertRule |
| `flush_every` | int | `0` | save automatically every N items (0 = disabled) |
| `sample_rate` | float | `1.0` | sampling rate |
| `timeout` | float\|None | `None` | whole-batch timeout (seconds) |
| `item_timeout` | float\|None | `None` | per-item timeout (seconds) |
| `enabled` | bool | `True` | disable flag |
| `concurrency` | int | `0` | number of concurrent executions (0 = sequential, N = up to N in parallel) |
| `concurrent_judge` | bool | `False` | opt into asyncio.gather-based concurrent LLM-judge processing |
| `return_format` | str | `"list"` | return format: "list" / "tuple" / "dataframe" |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS name |

### `@conversation_eval` — all parameters

| Parameter | Type | Default | Role |
|---|---|---|---|
| `monitor` | PerformanceMonitor | (required) | the monitor instance that records results |
| `session_id_arg` | str | `"session_id"` | name of the session-id argument |
| `user_arg` | str | `"question"` | name of the user-input argument |
| `ground_truth_arg` | str | `"ground_truth"` | name of the reference-answer argument |
| `max_turns` | int\|None | `None` | auto-flush when the max turn count is exceeded |
| `max_session_seconds` | float\|None | `None` | session timeout (seconds) |
| `flush_on_error` | bool | `True` | auto-flush the session on error |
| `max_turns_exceeded_action` | str | `"flush"` | "flush" / "warn" / "error" |
| `sample_rate` | float | `1.0` | sampling rate |
| `on_flush` | callable\|None | `None` | session-flush-complete callback `(ConversationMetrics)` |
| `on_turn` | callable\|None | `None` | turn-complete callback `(user, response, metadata)` |
| `session_score_fn` | callable\|None | `None` | custom session score `(ConversationMetrics) → float` |
| `turn_score_fn` | callable\|None | `None` | custom turn score `(user, response, metadata) → float` |
| `alert_rules` | list | `[]` | list of SimpleTaskAlertRule |
| `flush_every` | int | `0` | save automatically every N turns |
| `enabled` | bool | `True` | disable flag |
| `preset` | str\|None | `None` | AGENT_EVAL_PRESETS name |

---

## 8. Parameter → metric activation map

| Parameter | Metric / tracker it activates | Condition |
|---|---|---|
| `ground_truth_arg` | Accuracy | always, when the argument name matches |
| `rag_mode=True` | Hallucination Rate + context_arg="context" auto-set | when the context argument is present |
| `expected_tools_arg` | Tool Selection F1 (Precision/Recall/F1) | when tool_calls are also present |
| `framework="langchain"` | Tool Call Efficiency, Workflow Execution | LangChain AgentExecutor response |
| `framework="langgraph"` | Workflow Execution, state_transitions | LangGraph response |
| `framework="crewai"` | Tool Call Efficiency, Agent Coordination | CrewAI response |
| `framework="autogen"` | Agent Coordination | AutoGen ChatResult parsing |
| `framework="openai"` | Token Economy (exact) | OpenAI ChatCompletion |
| `framework="anthropic"` | Token Economy + cache tokens | Anthropic Message |
| `security=SecurityConfig()` | Input Sanitization, Output Leakage, Tool Authorization, Privilege Escalation, Tool Chain Attack (5) | temporarily enabled (restored in finally) |
| `llm_judge=LLMJudgeConfig()` | LLMJudge (completeness/relevance/factual_consistency/toxicity/bias) | API key required |
| `rag_mode=True` + `llm_judge=LLMJudgeConfig()` | + Faithfulness | added automatically when context is present |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | + G-Eval custom-criteria scores | criteria given inside the llm_judge settings |
| `retry=RetryConfig(max=N)` (N>1) | Retry & Error Recovery | when an actual retry occurs |
| `sample_rate=0.1` | all metrics (records only a 10% sample) | when not sampled, the function still runs normally |
| `enable_anomaly_detection=True` | Anomaly Detection | runs automatically on save_to_file() |
| `preset="production"` | sample_rate=0.1 + flush_every=50 + enable_anomaly_detection=True | when the preset name matches |

---

## 9. Metric × decorator support matrix

| Metric | `@agent_eval` | `@batch_eval` | `@conversation_eval` | Activation |
|---|:---:|:---:|:---:|---|
| **Layer 1 — Foundation metrics** | | | | |
| TCR | ✅ auto | ✅ auto | ✅ auto | always |
| Accuracy | ✅ auto | ✅ auto | ✅ auto | when `ground_truth_arg` is present |
| Response Quality (5 dims) | ✅ auto | ✅ auto | ✅ auto | when response + question are present |
| Latency (p50/p95/p99) | ✅ auto | ✅ auto | ✅ auto | always (execution time measured automatically) |
| TTFT | ✅ generator | ✅ `streaming_mode=True` | ❌ | generator return or streaming mode |
| Token Economy | ✅ auto | ✅ auto | ❌ | `framework=` adapter or EvalMetadata |
| Hallucination Rate | ✅ `rag_mode=True` | ✅ `context_arg` given | ❌ | context argument + hallucination enabled |
| **Layer 2 — Agentic metrics** | | | | |
| Tool Call Efficiency | ✅ auto | ✅ auto | ❌ | `framework=` adapter or EvalMetadata.tool_calls |
| Retry & Error Recovery | ✅ `retry=RetryConfig(max=N)` | ❌ | ❌ | `RetryConfig(max>1)` + an actual retry |
| Tool Selection F1 | ✅ `expected_tools_arg` | ✅ `expected_tools_arg` | ❌ | expected_tools + tool_calls together |
| Agent Coordination | ✅ `framework="crewai/autogen"` | ❌ | ❌ | CrewAI/AutoGen adapter |
| Workflow Execution | ✅ `framework="langchain/langgraph"` | ❌ | ❌ | LangChain/LangGraph adapter |
| **Layer 2 — Security metrics** | | | | |
| Input Sanitization | ✅ `security=SecurityConfig()` | ❌ | ❌ | SecurityConfig temporarily enabled |
| Output Leakage | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| Tool Authorization | ✅ `security=SecurityConfig()` + `allowed_tools` | ❌ | ❌ | same + whitelist |
| Privilege Escalation | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| Tool Chain Attack | ✅ `security=SecurityConfig()` | ❌ | ❌ | same |
| **Layer 3 / LLM Judge** | | | | |
| LLM Judge (5 dims) | ✅ `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | ships in the base install (API key required) |
| Faithfulness (RAG) | ✅ `rag_mode` + `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | added automatically when context is present |
| G-Eval custom criteria | ✅ `llm_judge=LLMJudgeConfig(criteria=[...])` | ❌ | ❌ | criteria given inside the llm_judge settings |
| **Conversation metrics (conversation_eval only)** | | | | |
| Context Retention | ❌ | ❌ | ✅ auto | compute_metrics() on flush |
| Topic Coherence | ❌ | ❌ | ✅ auto | same |
| Progressive Depth | ❌ | ❌ | ✅ auto | same |
| Session Completion | ❌ | ❌ | ✅ auto | same |

---

## 10. Data-source priority

```
1: return (EvalMetadata, result)   — explicit injection (highest priority)
2: get_eval_ctx()                  — ContextVar injection (eval_context pattern)
3: framework adapter              — automatic parsing of the return value (24 frameworks)
4: _auto_detect_framework()       — automatic detection based on the return-value type
5: argument-name extraction       — question_arg / ground_truth_arg / context_arg, etc.
```

```python
# Priority 1: explicit EvalMetadata injection
from agent_evaluator import EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = llm_with_tools.invoke(question)
    return EvalMetadata(
        accuracy_score=0.92,
        tokens_used={"input": 150, "output": 80},
        tool_calls=[{"tool_name": "search", "duration": 0.3, "success": True}],
    ), response.content

# Priority 3: framework adapter collects automatically
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
    # tool_calls, chain_steps, tokens_used extracted automatically
```

---

## 11. Reading metrics from the report

```python
report = monitor.generate_report()
d = report.to_dict()

# Layer 1
d["tcr_data"]["success_rate"]              # float (0–1)
d["accuracy_data"]["overall_accuracy"]     # float (0–100)
d["hallucination_data"]["overall_rate"]    # float (0–1)
d["quality_data"]["avg_total_score"]       # float (0–5)
d["latency_data"]["p95"]                   # float (seconds)
d["token_data"]["estimated_cost"]          # float ($)

# Layer 2
d["tool_efficiency"]                       # float (0–100)
d["tool_selection_accuracy"]               # float (0–100)
d["coordination_score"]                    # float (0–10)
d["workflow_execution"]["step_success_rate"] # float (0–100)

# Security
d["security_metrics"]["input_security"]["threat_rate"]           # float (0–100)
d["security_metrics"]["output_leakage"]["leakage_rate"]          # float (0–100)
d["security_metrics"]["authorization"]["compliance_rate"]        # float (0–100)
d["security_metrics"]["privilege_escalation"]["escalation_rate"] # float (0–100)
d["security_metrics"]["attack_detection"]["detection_rate"]      # float (0–100)

# LLM Judge
task_dict["extra"]["llm_judge"]["completeness"]         # float (0–5)
task_dict["extra"]["llm_judge"]["faithfulness"]         # float (0–5, RAG)
task_dict["extra"]["llm_judge"]["criteria_scores"]      # dict

# Conversation (after flush)
session_dict["context_retention"]   # float (0–1)
session_dict["overall_score"]       # float (0–1)
```

---

## 12. Framework integration

> **Core pattern**: `@agent_eval(monitor, framework="<framework name>")` — token / tool metadata is extracted from the response automatically.
> 24 frameworks: `langchain`, `langgraph`, `crewai`, `autogen`, `dspy`, `pydanticai`,
> `anthropic`, `openai`, `gemini`, `llamaindex`, `haystack`, `vertexai`, `ollama`, `cohere`,
> `groq`, `mistral`, `bedrock`, `smolagents`, `semantic_kernel`, `vllm`, `huggingface`,
> `openai_agents`, `google_adk`, `claude_agent_sdk` (the official agent-framework SDK — must specify `framework=` explicitly; auto-detection is not supported)

### Coverage summary for the 4 major frameworks

| Framework | Token accuracy | Multi-agent | Native coverage | Recommended use |
|-----------|----------------|-------------|-----------------|-----------------|
| 🟢 **LangChain** | ✅ actual value | ✗ single | ~82% (~21) | RAG, precise cost tracking |
| 🟠 **LangGraph** | 🔶 partial | 🔶 node transitions | ~82% (~21) | DAG · state machine |
| 🔵 **CrewAI** | ✗ fixed at 0 | ✅ | ~78% (~20) | role-based multi-agent |
| 🟣 **AutoGen** | 🔶 tiktoken | ✅ | ~80% (~20) | conversational multi-agent |

### 🟢 LangChain

```python
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})  # token_usage extracted automatically
```

**Auto-extracted**: actual token counts (`llm_output.token_usage`), tool calls (`AgentAction`), retries (`on_retry`)

### 🟠 LangGraph

```python
from agent_evaluator.integrations import langgraph_eval

@langgraph_eval(monitor, task_type="qa")
def lg_agent(question: str, ground_truth: str = "") -> str:
    result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content
```

**Auto-extracted**: measured per-node timing, node transitions (AgentCoordination), tokens (`AIMessage.usage_metadata`)

### 🔵 CrewAI

```python
from agent_evaluator.integrations import crewai_eval

@crewai_eval(monitor, task_type="qa")
def run_crew(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return result.raw
```

**Note**: token count is fixed at 0 — set it manually with `dataclasses.replace(task, tokens_used={...})`

### 🟣 AutoGen

```python
from agent_evaluator.integrations import autogen_eval

@autogen_eval(monitor, task_type="qa")
async def run_autogen(question: str, ground_truth: str = "") -> str:
    result = await team.run(task=question)
    return result.messages[-1].content
```

**Auto-extracted**: agent message exchanges (AgentCoordination), tool calls (ToolCallEvent), tokens (tiktoken)

### Adding security metrics (common)

```python
# Option 1: SecurityConfig decorator (recommended)
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Option 2: factory method (permanently enabled for the whole monitor)
monitor = PerformanceMonitor.for_secure_agents(
    security_config={
        "allowed_tools": ["web_search", "db_lookup"],
        "restricted_tools": ["rm_rf", "system_exec"],
    },
    output_dir="results/",
)
```

### Multi-turn conversation evaluation (common)

```python
@conversation_eval(
    monitor,
    session_id_arg="sid",
    max_turns=10,
    on_flush=lambda metrics, sid: print(f"session {sid}: {metrics.overall_score:.2f}")
)
def chatbot_agent(user_message, sid="default"):
    return response

chatbot_agent("Hello", sid="user_123")
flush_conversation("user_123")
```

---

## 13. Metric support matrix (by framework)

### Foundation metrics (6)

| # | Metric | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|--------|-----------|-------------|-------------|-----------|
| 1 | **TCR** | ✅ exception-based | ✅ callback-based | ✅ node-error-based | ✅ exception-based |
| 2 | **Accuracy** | ✅ | ✅ | ✅ | ✅ |
| 3 | **Hallucination** | ✅ tasks_output | 🔶 Retriever | 🔶 ToolMessage | 🔶 tool result |
| 4 | **Response Quality** | ✅ | ✅ | ✅ | ✅ |
| 5 | **Latency** | 🔶 evenly divided | ✅ on_chain_end | ✅ measured per node | 🔶 total time |
| 6 | **Token Economy** | ✗ fixed at 0 | ✅ actual token_usage | 🔶 AIMessage | 🔶 tiktoken |

### Agentic metrics (5)

| # | Metric | 🔵 CrewAI | 🟢 LangChain | 🟠 LangGraph | 🟣 AutoGen |
|---|--------|-----------|-------------|-------------|-----------|
| 7 | **Tool Call Efficiency** | 🔶 inferred | ✅ on_agent_action | 🔶 ToolMessage | ✅ ToolCallEvent |
| 8 | **Retry & Recovery** | 🔶 attempts=1 | ✅ on_retry | 🔶 attempts=1 | 🔶 attempts=1 |
| 9 | **Tool Selection F1** | ✅ | ✅ | ✅ | ✅ |
| 10 | **Agent Coordination** | ✅ Hierarchical | ✗ single | ✅ node transitions | ✅ sender |
| 11 | **Workflow Execution** | 🔶 keyword inference | 🔶 tool = step | ✅ node = step | 🔶 message history |

**Legend**: ✅ auto-supported | 🔶 partial / estimated | ✗ not supported

### Limitations summary

| Framework | Item | Recommended workaround |
|-----------|------|------------------------|
| 🔵 CrewAI | token count fixed at 0 | `dataclasses.replace(task, tokens_used={...})` |
| 🟢 LangChain | Agent Coordination not supported | switch to CrewAI/AutoGen |
| 🟣 AutoGen | limited support for 0.3.x | 0.4+ async API or manual `record_task()` |

---

## 14. Comparison with other evaluation tools

### Major evaluation tools at a glance

| Tool | Type | Agentic-specific metrics | Security metrics | Computes without an LLM | Dashboard | Cost |
|------|------|--------------------------|------------------|-------------------------|-----------|------|
| **LangSmith** | SaaS | Multi-Turn Goal, Trajectory | ❌ | ❌ | SaaS | from $39/mo |
| **Ragas** | OSS | ToolCallAccuracy, AgentGoalAccuracy | ❌ | ❌ | external integration | free |
| **DeepEval** | OSS+SaaS | TaskCompletion, ToolCorrectness | partial (red-team) | partial | Confident AI | from $49/mo |
| **Arize Phoenix** | OSS+Cloud | FunctionCalling, Planning | ❌ | ❌ | local/Cloud | free+ |
| **W&B Weave** | SaaS | Multi-agent spans, A2A | Guardrails | partial | SaaS | from $50/mo/seat |
| **Agent Evaluator** | OSS SDK | **11 kinds** | **5 dedicated** | **✅ all** | **local, free** | **$0** |

### Agentic-metric detail comparison

| Metric | LangSmith | Ragas | DeepEval | Phoenix | **Agent Evaluator** |
|--------|:---------:|:-----:|:--------:|:-------:|:-------------------:|
| Tool selection accuracy (F1) | ❌ | ✅ | ✅ | ❌ | ✅ `ToolSelectionTracker` |
| Tool efficiency / redundant calls | ❌ | ❌ | ❌ | ❌ | ✅ `ToolCallAnalyzer` |
| Retry / self-correction patterns | ❌ | ❌ | ❌ | ❌ | ✅ `RetryCorrectionTracker` |
| Multi-agent cooperation quality | ❌ | ❌ | ❌ | ❌ | ✅ `AgentCoordinationTracker` |
| Workflow funnel / branching | ✅ (LangGraph) | ❌ | ❌ | partial | ✅ `WorkflowExecutionTracker` |
| Prompt-injection detection | ❌ | ❌ | ⚠️ red-team | ❌ | ✅ `InputSanitizationTracker` |
| Output-leakage detection | ❌ | ❌ | ❌ | ❌ | ✅ `OutputLeakageDetector` |
| Privilege-escalation detection | ❌ | ❌ | ❌ | ❌ | ✅ `PrivilegeEscalationDetector` |

### Selection guide

| Situation | Recommended tool |
|-----------|------------------|
| Only need LangChain/LangGraph tracing | **LangSmith** |
| Precise RAG faithfulness/recall measurement | **Ragas** |
| LLM unit tests in CI/CD | **DeepEval** |
| OTEL-based infrastructure + local self-hosting | **Arize Phoenix** |
| Agent security verification (prompt injection, privilege escalation) | **Agent Evaluator** |
| Agentic behavior analysis (tool F1, retry, multi-agent) | **Agent Evaluator** |
| Measure all native metrics with no extra API cost | **Agent Evaluator** |

---

| Goal | Document |
|------|----------|
| Installation · basic usage | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| All 58 metrics in detail | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| Golden dataset · Korean RAG | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| Quality thresholds · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Full API reference | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
