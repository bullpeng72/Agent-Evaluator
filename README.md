# Agent Evaluator

[![PyPI version](https://img.shields.io/pypi/v/agent-evaluator.svg)](https://pypi.org/project/agent-evaluator/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.9.2-green.svg)](https://github.com/bullpeng72/Agent-Evaluator)

**Harness Engineering evaluation SDK that judges AI agent deployment readiness through 7 Gates**

It asks not just "Does the agent work well?" but **"Is the agent ready for production deployment?"**
Goal Achievement (A) · Behavioral Integrity (B) · Reliability (C) · Performance Contract (D) · Security Boundary (E) · Multi-Agent Coordination (F) · Observability (G) —
**7 Harness Gates comprehensively determine agent deployment readiness**.

One decorator line auto-recognizes **21 frameworks** including LangChain · CrewAI · AutoGen,
and measures **58 metrics (25 Native Trackers + 33 Harness Config)** without code modification.

---

## Harness Engineering — Judging AI Agent Deployment Readiness Through 7 Gates

Evaluates agents based on **deployment readiness** rather than simple accuracy measurement.
Pass 33 Harness Configs as decorator parameters and `PerformanceMonitor` auto-aggregates to determine PASS/WARN/FAIL for each of the 7 Gates.

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig,          # Gate A — Goal Achievement
    LoopDetectionConfig, StateConsistencyConfig,      # Gate B — Behavioral Integrity
    FaultToleranceConfig, GracefulDegradationConfig,  # Gate C — Reliability
    SLAConfig, EfficiencyConfig,                      # Gate D — Performance Contract
    ThreatSeverityConfig, ComplianceConfig,           # Gate E — Security Boundary
    ConsensusConfig, AgentRoleConfig,                 # Gate F — Multi-Agent Coordination
    ExplainabilityConfig, ObservabilityConfig,        # Gate G — Observability
)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

monitor.save_to_file("eval")   # eval.json + eval.html — includes Gate A–G judgments
```

| Gate | Area | Judgment Criteria | Harness Config (count) |
|------|------|-------------------|----------------------|
| **A** 🟢 | **Goal Achievement** | Instruction compliance · goal alignment · plan consistency · context retention | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig **(6)** |
| **B** 🔵 | **Behavioral Integrity** | Loop detection · scope deviation · tool safety · state consistency · deadlock detection | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig **(6)** |
| **C** 🟡 | **Reliability** | Reproducibility · error recovery rate · quality floor · idempotency | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig **(5)** |
| **D** 🔵 | **Performance Contract** | SLA compliance · token efficiency · TTFT variability · cost predictability | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig **(5)** |
| **E** 🔴 | **Security Boundary** | Threat severity · compliance · threat response behavior | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig **(3)** |
| **F** 🟣 | **Multi-Agent Coordination** | Inter-agent consensus · information propagation accuracy · role compliance · conflict resolution | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig **(4)** |
| **G** 🩵 | **Observability** | Reasoning explainability · internal state tracking · error diagnosis · latency attribution | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig **(4)** |

Each Gate receives raw measurements from **25 Native Trackers** (6 Layer 1 foundation metrics + 10 Layer 2 agentic metrics + 5 security metrics + LLMJudge) and aggregates them.

> Full practical examples: `Evaluator_Examples/ch03_harness_basics.py` | Dashboard: `agent-eval dashboard`

---

## Why Decorators?

```python
# ❌ Traditional approach — direct agent code modification, boilerplate required
import time, uuid
from datetime import datetime

def my_agent(question, ground_truth):
    start = time.time()
    response = llm.invoke(question)
    elapsed = time.time() - start

    task = TaskResult(
        task_id=str(uuid.uuid4()), task_type="qa", success=True,
        completion_score=1.0,
        accuracy_score=compute_accuracy(response, ground_truth),  # manual calculation
        execution_time=elapsed,                                    # manual measurement
        tokens_used=extract_tokens(response),                      # varies by framework
        tool_calls=[], attempts=1, errors=[], timestamp=datetime.now(),
        question=question, response=str(response), ground_truth=ground_truth,
    )
    monitor.record_task(task)
    return response
```

```python
# ✅ Decorator approach — one line added, agent code unchanged
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                                   # this one line is all it takes
def my_agent(question, ground_truth=""):
    return llm.invoke(question)            # agent logic unchanged
```

Decorators are **non-invasive**. The original function's signature, return value, and exception handling remain unchanged. After measurement, the original return value is passed directly to the caller.

---

## How Decorators Work

```
Caller
  │
  ▼
@agent_eval / @batch_eval / @conversation_eval
  │
  ├─ [1] Start execution time measurement
  ├─ [2] Execute original function
  ├─ [3] Apply framework adapter   ← auto-extract tool_calls · chain_steps · tokens_used
  ├─ [4] Merge EvalMetadata        ← when function returns (response, EvalMetadata(...))
  ├─ [5] Auto-build TaskResult     ← 24 fields completed
  ├─ [6] Call PerformanceMonitor.record_task()
  │       ├─ Layer 1: TCR · Accuracy · Hallucination · Quality · Latency · Token
  │       ├─ Layer 2: Tool · Retry · Coordination · Workflow · Security (5 types)
  │       ├─ Layer 3: LLMJudge · DeepEval · Ragas  (opt-in)
  │       └─ Harness: auto-aggregate 33 Configs → Gate A–G pass/warn/fail judgment
  │
  └─ [7] Return original value to caller unchanged
```

---

## Installation

```bash
# Base install — LLMJudge engine (openai + anthropic) · core metrics only
pip install agent-evaluator

# ── SDK features (dashboard · OTEL monitoring · PDF) ────────────────────────
pip install "agent-evaluator[serve]"              # agent-eval dashboard (FastAPI + uvicorn)
pip install "agent-evaluator[otel]"               # agent-eval monitor (Phoenix + OTEL)
pip install "agent-evaluator[pdf]"                # Korean RAG PDF processing
pip install "agent-evaluator[sdk]"                # serve + otel + pdf bundle (recommended)

# ── Running Evaluator_Examples/ ─────────────────────────────────────────────
pip install "agent-evaluator[examples]"           # all examples runnable (sdk + eval)

# ── Framework extensions (when your agent code needs them) ──────────────────
# agent-evaluator itself works fully without these packages (duck typing)
pip install "agent-evaluator[eval]"               # DeepEval ≥3.0 + Ragas ≥0.4 (external eval)
pip install "agent-evaluator[langchain]"          # LangChain ≥1.0 / LangGraph ≥1.0
pip install "agent-evaluator[dspy]"               # DSPy ≥2.0
pip install "agent-evaluator[pydanticai]"         # PydanticAI ≥1.0
pip install "agent-evaluator[crewai]"             # CrewAI ≥1.0 (heavy — 100+ transitive deps)
pip install "agent-evaluator[autogen]"            # AutoGen ≥0.3 (heavy)

# ── Convenience bundles ──────────────────────────────────────────────────────
pip install "agent-evaluator[full]"               # All (⚠️ includes crewai/autogen, 10+ min)

# ── pipx global install ──────────────────────────────────────────────────────
# zsh requires quotes around extras
pipx install 'agent-evaluator[sdk]'              # dashboard + monitor + PDF all available
```

---

## 3 Decorator Types

Agent Evaluator's evaluation interface consists of exactly **3 types** based on call patterns.

| Decorator | Call Pattern | Use Scenario |
|-----------|-------------|-------------|
| `@agent_eval` | 1 function call = 1 TaskResult | Single QA · tool call · RAG · security check |
| `@batch_eval` | 1 function call = N TaskResults | Dataset batch evaluation · benchmarks |
| `@conversation_eval` | N function calls = 1 TaskResult | Multi-turn conversation · chatbot session |

---

### Decorator 1: `@agent_eval`

**1 call → 1 TaskResult**. Supports sync · async · generator · retry.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval, RetryConfig, SecurityConfig, LLMJudgeConfig

monitor = PerformanceMonitor("results/")

# Basic — QA evaluation
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Async function — same decorator
@agent_eval(monitor, task_type="qa")
async def async_agent(question: str, ground_truth: str = "") -> str:
    return await async_llm.invoke(question)

# Built-in retry — retry policy via RetryConfig, attempts field auto-recorded
@agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3, delay=1.0, backoff=2.0))
def robust_agent(question: str, ground_truth: str = "") -> str:
    return unreliable_llm.invoke(question)

# RAG agent — one rag_mode=True enables context + hallucination automatically
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return retrieval_llm.invoke(question, context)

# Security check — temporarily enables 5 security trackers for this call
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# LLM framework adapter — auto-extracts tool_calls · tokens_used
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return executor.invoke({"input": question})
```

**`@agent_eval` Key Parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `task_type` | `"qa"` | Task type (qa · tool_use · information_retrieval · code_generation · etc.) |
| `framework` | `"native"` | Framework adapter (21 supported) |
| `question_arg` | `"question"` | Question argument name |
| `ground_truth_arg` | `"ground_truth"` | Ground truth argument name |
| `context_arg` | `None` | RAG context argument name |
| `expected_tools_arg` | `None` | Expected tool list argument name (auto-calculates Tool Selection F1) |
| `score_fn` | `None` | Custom accuracy function `(response, gt) → float` |
| `rag_mode` | `False` | Shorthand to enable context_arg + hallucination |
| `retry` | `None` | `RetryConfig` instance — retry policy (max · delay · backoff · jitter_type · etc.) |
| `security` | `None` | `SecurityConfig` instance — temporarily enables security metrics for this call |
| `llm_judge` | `None` | `LLMJudgeConfig` instance — temporarily enables LLM Judge for this call |
| `enable_hallucination_detection` | `False` | Temporarily enables Hallucination Detection for this call |
| `enable_anomaly_detection` | `False` | Temporarily enables AnomalyDetector for this call |
| `timeout` | `None` | Maximum execution time (seconds) |
| `sample_rate` | `1.0` | Recording sampling rate |
| `on_record` | `None` | Pre-record callback (can replace TaskResult) |
| `alert_rules` | `[]` | Conditional alert rule list |
| `flush_every` | `0` | Auto `save_to_file()` every N tasks |
| `preset` | `None` | Predefined configuration bundle |

---

### Decorator 2: `@batch_eval`

**1 call → N TaskResults**. Takes a list of questions and creates independent evaluation records per item.

```python
from agent_evaluator.decorators import batch_eval

# Basic — list input, list return
@batch_eval(monitor, task_type="qa")
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

# DataFrame return — includes accuracy_score · execution_time · tokens_total · etc.
@batch_eval(monitor, task_type="qa", return_format="dataframe")
def batch_agent_df(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

# Parallel execution (async function) — asyncio.gather based
@batch_eval(monitor, task_type="qa", concurrent=True, max_concurrent=4)
async def parallel_agent(questions: list, ground_truths: list = None) -> list:
    return await asyncio.gather(*[async_llm.invoke(q) for q in questions])

# Progress callback — for large batch monitoring
@batch_eval(
    monitor,
    task_type="qa",
    return_format="tuple",                              # returns (responses, task_results)
    on_batch_progress=lambda done, total: print(f"{done}/{total}"),
    flush_every=100,                                    # intermediate save every 100 tasks
)
def large_batch(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]

responses, task_results = large_batch(questions, ground_truths)
```

**`@batch_eval` Key Parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `questions_arg` | `"questions"` | Question list argument name |
| `ground_truths_arg` | `"ground_truths"` | Ground truth list argument name |
| `return_format` | `"list"` | Return format: `"list"` · `"tuple"` · `"dataframe"` |
| `concurrent` | `False` | Parallel item execution for async functions |
| `max_concurrent` | `0` | Concurrency limit (0 = unlimited) |
| `shuffle` | `False` | Randomize processing order |
| `item_timeout` | `None` | Max processing time per item (seconds) |
| `on_batch_progress` | `None` | Progress callback `(completed, total) → None` |
| `on_batch_complete` | `None` | Batch completion callback `(results) → None` |
| `on_item_error` | `None` | Item failure callback `(index, question, error) → None` |
| `streaming_mode` | `False` | Memory-efficient streaming processing |

---

### Decorator 3: `@conversation_eval`

**N calls → 1 TaskResult**. Repeated calls with the same `session_id` accumulate turns internally. The session ends and metrics are calculated when `max_turns` is reached or `flush_conversation()` is called.

```python
from agent_evaluator.decorators import conversation_eval

# Basic — auto-accumulate per session_id, auto-flush on max_turns
@conversation_eval(monitor, session_id_arg="session_id", max_turns=5)
def chat(question: str, session_id: str = "default") -> str:
    return llm.invoke(question)

# Usage — repeated calls with the same session_id
chat("How do I handle async Python?", session_id="conv_001")
chat("What are the downsides of that approach?", session_id="conv_001")
chat("Show me an asyncio.gather example.", session_id="conv_001")
# → auto-flush at 5 turns: context_retention · topic_coherence · progressive_depth calculated

# Manual flush — end session at desired point
from agent_evaluator.decorators import flush_conversation
flush_conversation("conv_001")

# Per-turn callback + session score function
@conversation_eval(
    monitor,
    max_turns=10,
    on_turn=lambda sid, user, resp, meta: print(f"[{sid}] {user[:20]}…"),
    session_score_fn=lambda metrics: metrics.overall_score * 100,
    flush_every=3,                    # auto save_to_file() every 3 sessions
)
def advanced_chat(question: str, session_id: str = "s1") -> str:
    return llm.invoke(question)
```

Metrics measured by `@conversation_eval`:

| Metric | Description |
|--------|-------------|
| `turn_count` | Cumulative conversation turns |
| `overall_score` | Session overall score (0–1) |
| `context_retention` | Degree to which prior turn context is reflected in subsequent responses |
| `topic_coherence` | Topic consistency throughout the conversation |
| `progressive_depth` | Degree to which information density increases as conversation deepens |
| `session_completion` | Goal conversation completion |
| `avg_turn_latency` | Average response time per turn |
| `turn_scores` | Quality scores per turn (Optional) |

**`@conversation_eval` Key Parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `session_id_arg` | `"session_id"` | Session ID argument name |
| `user_arg` | `"question"` | User message argument name |
| `max_turns` | `None` | Max turns (auto-flush on reach) |
| `max_turns_exceeded_action` | `"flush"` | Action on exceed: `"flush"` · `"warn"` · `"error"` |
| `flush_on_error` | `True` | Auto-flush session on exception |
| `on_turn` | `None` | Turn completion callback `(sid, user, response, meta) → None` |
| `on_flush` | `None` | Session end callback `(metrics, session_id) → None` |
| `session_score_fn` | `None` | Session overall score function `(ConversationMetrics) → float` |
| `turn_score_fn` | `None` | Per-turn score function `(user, response, meta) → float` |
| `load_previous_session` | `False` | Resume from previous session |
| `max_session_seconds` | `None` | Auto-flush timer for inactive sessions (seconds) |

---

## EvalDecorator — Unified Factory for All 3 Types

Define common configuration (monitor, framework, model_name, etc.) **once** and reuse it across all 3 decorator types.

```python
from agent_evaluator.decorators import EvalDecorator

# Define common config once
dec = EvalDecorator(
    monitor,
    framework="langchain",
    model_name="gpt-4o-mini",
    flush_every=10,
    alert_rules=[slow_rule, error_rule],
)

# ── agent_eval family ──────────────────────────────────
@dec(task_type="qa")                                   # direct agent_eval call
def qa_agent(question, ground_truth=""): ...

@dec.with_retry(task_type="qa", retry=RetryConfig(max=3))  # with retry
def robust_agent(question, ground_truth=""): ...

# ── batch_eval ─────────────────────────────────────────
@dec.batch(task_type="qa", return_format="dataframe")
def batch_agent(questions, ground_truths=None): ...

# ── conversation_eval ───────────────────────────────────
@dec.conversation(session_id_arg="sid", max_turns=5)
def chat(question, sid="s1"): ...

# ── task_type shorthand attributes (same API as QuickEval) ─────
@dec.qa             # task_type="qa"
@dec.tool_use       # task_type="tool_use"
@dec.rag            # task_type="information_retrieval" + rag_mode=True
@dec.code           # task_type="code_generation"
@dec.reasoning      # task_type="reasoning"
@dec.secure         # task_type="qa" + security=SecurityConfig()
```

---

## QuickEval — One-Line Start Facade

One-stop entry point that configures `PerformanceMonitor` + `EvalDecorator` in one line.

```python
from agent_evaluator import QuickEval

# Basic initialization
eval = QuickEval("results/")

# Purpose-specific factories — auto-configure relevant options
eval = QuickEval.for_rag("results/")               # hallucination_detection=True by default
eval = QuickEval.for_security("results/")          # enable_security_metrics=True by default
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 11 decorator shorthand attributes
@eval.qa            @eval.tool_use      @eval.rag
@eval.code          @eval.reasoning     @eval.planning
@eval.data_analysis @eval.creative      @eval.multi_agent
@eval.secure        @eval.streaming

# Batch · conversation decorators with same interface
@eval.batch(task_type="qa", return_format="dataframe")
def batch_agent(questions, ground_truths=None): ...

@eval.conversation(session_id_arg="sid", max_turns=5)
def chat(question, sid="s1"): ...

# Save results · gating
eval.save()                                        # results/*.json + *.html
eval.gate(tcr=85, accuracy=70, hallucination=5)    # CI/CD gate
eval.summary()                                     # print key metric summary
eval.export_to_dataframe()                         # return pd.DataFrame
```

---

## eval_context — Escape Hatch When Decorators Can't Be Used

Use when you can't attach a decorator to code — external library functions, lambdas, dynamic calls, etc. Performs the same evaluation as `@agent_eval`.

```python
from agent_evaluator.decorators import eval_context, get_eval_ctx

# Basic — auto record_task() on with block exit
with eval_context(monitor, task_type="qa",
                  question="What is the capital of South Korea?", ground_truth="Seoul") as ctx:
    ctx.response = external_lib.call("What is the capital of South Korea?")

# Inject additional metadata via get_eval_ctx()
with eval_context(monitor, task_type="tool_use", question=q) as ctx:
    result = external_agent.run(q)
    ctx.response = result["output"]
    ec = get_eval_ctx()
    if ec:
        ec.framework = "langchain"
        ec.chain_steps = parse_steps(result)

# Async
async with eval_context(monitor, task_type="qa", question=q) as ctx:
    ctx.response = await async_external.call(q)
```

---

## EvalMetadata — Injecting Additional Metadata

Available in all 3 decorator types. Change the return value to `(response, EvalMetadata(...))` tuple to override auto-extracted results.

```python
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="tool_use")
def agent(question, ground_truth=""):
    response = llm.invoke(question)
    return response, EvalMetadata(
        accuracy_score=0.95,                        # directly set custom score
        tool_calls=["search", "calculator"],        # tool call list
        tokens_used={"input": 120, "output": 80},
        chain_steps=["search", "parse", "answer"],
        agent_interactions=[("planner", "executor", "task_complete")],
    )
```

Use `TurnMetadata` in `@conversation_eval`.

```python
from agent_evaluator.decorators import TurnMetadata

@conversation_eval(monitor, max_turns=5)
def chat(question: str, session_id: str = "s1") -> str:
    response = llm.invoke(question)
    return response, TurnMetadata(
        model="gpt-4o-mini",
        tokens={"input": 50, "output": 30},
        tool_calls=["search"],
    )
```

---

## Auto-Recognition of 21 Frameworks

The `framework=` parameter auto-extracts `tool_calls`, `chain_steps`, `tokens_used`, etc. from response objects.
All 3 decorator types support the same `framework=` parameter.

```python
# Explicit specification — IDE autocomplete supported (FrameworkLiteral type hint)
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question, ground_truth=""): ...

# Auto-detection (enabled by default — auto_detect_framework=True)
@agent_eval(monitor, task_type="qa")
def auto_agent(question, ground_truth=""): ...

# Applies equally to batch_eval · conversation_eval
@batch_eval(monitor, task_type="qa", framework="openai")
def batch_agent(questions, ground_truths=None): ...

@conversation_eval(monitor, max_turns=5, framework="anthropic")
def chat(question, session_id="s1"): ...

# Query framework adapter info
from agent_evaluator.decorators import get_framework_info
info = get_framework_info("langchain")
# → {"name": "LangChain", "extras": "langchain",
#    "extracts": ["tool_calls", "chain_steps"], "async_supported": True, ...}
```

### Full Adapter List

> **Note**: `framework=` parameter and adapters work via **duck typing** — agent-evaluator itself works fully without the framework package installed. The "Required extras" column shows packages needed **when your agent code** imports the framework.

| Identifier | Name | Required Extras | Auto-extracted Fields | Async |
|------------|------|----------------|----------------------|-------|
| `langchain` | LangChain | `[langchain]`¹ | `tool_calls` · `chain_steps` | ✅ |
| `langgraph` | LangGraph | `[langchain]`¹ | `state_transitions` · `graph_traversal` · `tool_calls` · `chain_steps` | ✅ |
| `crewai` | CrewAI | `[crewai]`¹ | `agent_interactions` | ❌ |
| `autogen` | AutoGen | `[autogen]`¹ | `conversation_turns` · `tokens_used` | ✅ |
| `dspy` | DSPy | `[dspy]` | `chain_steps` · `tokens_used` | ❌ |
| `pydanticai` | PydanticAI | `[pydanticai]` | `chain_steps` · `tokens_used` | ✅ |
| `anthropic` | Anthropic | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `openai` | OpenAI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `gemini` | Google Gemini | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `vertexai` | Vertex AI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `cohere` | Cohere | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `groq` | Groq | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `mistral` | Mistral AI | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `bedrock` | AWS Bedrock | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `ollama` | Ollama | `[llm]` | `tool_calls` · `tokens_used` | ❌ |
| `llamaindex` | LlamaIndex | `[llm]` | `chain_steps` | ✅ |
| `haystack` | Haystack | `[llm]` | `chain_steps` | ✅ |
| `semantic_kernel` | Semantic Kernel | `[llm]` | `chain_steps` · `tokens_used` | ✅ |
| `smolagents` | HuggingFace smolagents | `[llm]` | `tool_calls` · `chain_steps` | ❌ |
| `vllm` | vLLM | `[llm]` | `tool_calls` · `tokens_used` | ✅ |
| `huggingface` | HuggingFace | `[llm]` | `chain_steps` · `tool_calls` | ❌ |

¹ **User framework extras** — agent-evaluator itself works without these packages. The `@agent_eval(framework="langchain")` decorator works via duck typing so installation is not required for agent-evaluator. Install only when your agent code directly imports the framework.

---

### Orchestration Frameworks

#### LangChain

Auto-extracts tool calls and chain steps from `intermediate_steps` in `AgentExecutor.invoke()` results.

```python
from langchain.agents import AgentExecutor
from agent_evaluator.decorators import agent_eval

# intermediate_steps → tool_calls + chain_steps auto-conversion
# usage_metadata / response_metadata.token_usage → tokens_used auto-extraction
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def lc_agent(question: str, ground_truth: str = "") -> str:
    result = agent_executor.invoke({"input": question})
    return result  # return dict as-is — text auto-extracted from "output" key

# Framework-specific alias (agent_evaluator.integrations)
from agent_evaluator.integrations import langchain_eval

@langchain_eval(monitor, task_type="tool_use")
def lc_agent2(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})
```

#### LangGraph

Extracts state transitions · graph paths · tool calls from `messages` array in graph execution results.
Graph metadata is also auto-collected if `__metadata__` key is present.

```python
from langgraph.graph import StateGraph
from agent_evaluator.decorators import agent_eval

# messages → state_transitions + graph_traversal
# ToolMessage / AIMessage → chain_steps + timestamp-based execution time
@agent_eval(monitor, task_type="tool_use", framework="langgraph")
def lg_agent(question: str, ground_truth: str = "") -> str:
    result = graph.invoke({"messages": [("user", question)]})
    return result  # "messages"[-1].content auto-extracted

from agent_evaluator.integrations import langgraph_eval

@langgraph_eval(monitor, task_type="tool_use")
def lg_agent2(question: str, ground_truth: str = "") -> str:
    return graph.invoke({"messages": [("user", question)]})
```

#### CrewAI

Extracts inter-agent interactions from `tasks_output` in `Crew.kickoff()` results.
Supports `output_pydantic` / `output_format` (v2.x) fields.

```python
from crewai import Crew, Agent, Task
from agent_evaluator.decorators import agent_eval

# tasks_output → agent_interactions auto-conversion
# Note: CrewAI does not support async — use synchronous functions only
@agent_eval(monitor, task_type="tool_use", framework="crewai")
def crew_agent(question: str, ground_truth: str = "") -> str:
    result = crew.kickoff(inputs={"topic": question})
    return str(result)

from agent_evaluator.integrations import crewai_eval

@crewai_eval(monitor, task_type="tool_use")
def crew_agent2(question: str, ground_truth: str = "") -> str:
    return str(crew.kickoff(inputs={"topic": question}))
```

#### AutoGen

Extracts conversation turns and cost information from `chat_result.messages` / `chat_history`.
For AutoGen 0.4+ async API, use the `autogen_eval_async` dedicated decorator.

```python
from autogen import ConversableAgent
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import autogen_eval, autogen_eval_async

# messages/chat_history → conversation_turns
# cost/usage_summary → tokens_used
@agent_eval(monitor, task_type="qa", framework="autogen")
def autogen_agent(question: str, ground_truth: str = "") -> str:
    result = assistant.initiate_chat(user_proxy, message=question, max_turns=3)
    return result.summary

# AutoGen 0.4+ async API dedicated
@autogen_eval_async(monitor, task_type="qa")
async def autogen_agent_async(question: str, ground_truth: str = "") -> str:
    result = await team.run(task=question)
    return result.messages[-1].content
```

---

### LLM Providers

#### OpenAI

Auto-extracts `choices[0].message.tool_calls` and `usage.total_tokens` from `ChatCompletion` responses.
Also supports Assistants API `required_action`.

```python
import openai
from agent_evaluator.decorators import agent_eval

client = openai.OpenAI()

@agent_eval(monitor, task_type="tool_use", framework="openai")
def gpt_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )  # return ChatCompletion object as-is — choices[0].message.content auto-extracted
```

#### Anthropic

Extracts `content[].tool_use` and `usage.input_tokens/output_tokens` from `Message` responses.
Cache tokens (`cache_creation_input_tokens`, `cache_read_input_tokens`, SDK ≥0.29) also supported.

```python
import anthropic
from agent_evaluator.decorators import agent_eval

client = anthropic.Anthropic()

@agent_eval(monitor, task_type="tool_use", framework="anthropic")
def claude_agent(question: str, ground_truth: str = "") -> str:
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
        tools=[...],
    )  # return Message object as-is — content[0].text auto-extracted
```

#### Google Gemini / Vertex AI

Extracts `candidates[0].content.parts[].function_call` and `usage_metadata` from `GenerateContentResponse`.

```python
import google.generativeai as genai
from agent_evaluator.decorators import agent_eval

model = genai.GenerativeModel("gemini-1.5-flash")

@agent_eval(monitor, task_type="tool_use", framework="gemini")
def gemini_agent(question: str, ground_truth: str = "") -> str:
    return model.generate_content(question)  # return GenerateContentResponse as-is

# Vertex AI uses the same response structure — framework="vertexai"
@agent_eval(monitor, task_type="tool_use", framework="vertexai")
def vertex_agent(question: str, ground_truth: str = "") -> str:
    return vertex_model.generate_content(question)
```

#### Cohere

Extracts `tool_calls` and `meta.tokens` from `NonStreamedChatResponse`.
Streaming responses (`finish_reason` attribute) also auto-detected.

```python
import cohere
from agent_evaluator.decorators import agent_eval

co = cohere.Client()

@agent_eval(monitor, task_type="tool_use", framework="cohere")
def cohere_agent(question: str, ground_truth: str = "") -> str:
    return co.chat(message=question, tools=[...])
```

#### Groq

OpenAI-compatible API structure — extracts `tool_calls` and `usage`.
Cache tokens (`cache_creation_input_tokens`, `cache_read_input_tokens`, v0.9+) also supported.

```python
from groq import Groq
from agent_evaluator.decorators import agent_eval

client = Groq()

@agent_eval(monitor, task_type="tool_use", framework="groq")
def groq_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": question}],
    )
```

#### Mistral AI

Extracts `tool_calls` and `usage` from `ChatCompletionResponse`.
Legacy `function_call` field also supported.

```python
from mistralai import Mistral
from agent_evaluator.decorators import agent_eval

client = Mistral()

@agent_eval(monitor, task_type="tool_use", framework="mistral")
def mistral_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": question}],
    )
```

#### AWS Bedrock

Branches handling of Titan / Mistral on Bedrock / Claude responses based on `model_id` from Bedrock Converse API responses.

```python
import boto3
from agent_evaluator.decorators import agent_eval

client = boto3.client("bedrock-runtime", region_name="us-east-1")

@agent_eval(monitor, task_type="tool_use", framework="bedrock")
def bedrock_agent(question: str, ground_truth: str = "") -> str:
    return client.converse(
        modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
        messages=[{"role": "user", "content": [{"text": question}]}],
    )
```

#### Ollama

Extracts `tool_calls` and `prompt_eval_count` / `eval_count` from `ollama.chat()` / `ollama.generate()` responses.
Note: Ollama does not support async.

```python
import ollama
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa", framework="ollama")
def ollama_agent(question: str, ground_truth: str = "") -> str:
    return ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": question}],
    )
```

---

### AI Frameworks

#### DSPy

Extracts chain steps from `_completions` attribute of `dspy.Prediction`.
Full LM history multi-step also supported. Note: DSPy does not support async.

```python
import dspy
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import dspy_eval

lm = dspy.LM("openai/gpt-4o-mini")
dspy.configure(lm=lm)

@agent_eval(monitor, task_type="qa", framework="dspy")
def dspy_agent(question: str, ground_truth: str = "") -> str:
    predictor = dspy.Predict("question -> answer")
    return predictor(question=question)  # Prediction object → .answer auto-extracted

@dspy_eval(monitor, task_type="qa")
def dspy_agent2(question: str, ground_truth: str = "") -> str:
    return dspy.ChainOfThought("question -> answer")(question=question)
```

#### PydanticAI

Extracts chain steps from `RunResult.all_messages()` (preferred) or `.messages` (fallback).
Finely extracts `ToolCallPart` / `ToolReturnPart` / `TextPart`.

```python
from pydantic_ai import Agent
from agent_evaluator.decorators import agent_eval
from agent_evaluator.integrations import pydanticai_eval

agent = Agent("openai:gpt-4o-mini", system_prompt="...")

@agent_eval(monitor, task_type="qa", framework="pydanticai")
async def pydantic_agent(question: str, ground_truth: str = "") -> str:
    result = await agent.run(question)
    return result  # RunResult object → .data auto-extracted

@pydanticai_eval(monitor, task_type="qa")
async def pydantic_agent2(question: str, ground_truth: str = "") -> str:
    return await agent.run(question)
```

#### LlamaIndex

Extracts chain steps from `Response.source_nodes`.
`ToolOutput` from `AgentChatResponse.sources` also supported.

```python
from llama_index.core import VectorStoreIndex
from agent_evaluator.decorators import agent_eval

index = VectorStoreIndex.from_documents([...])
query_engine = index.as_query_engine()

# source_nodes → chain_steps (with score + metadata)
@agent_eval(monitor, task_type="information_retrieval", framework="llamaindex", rag_mode=True)
def llamaindex_agent(question: str, ground_truth: str = "") -> str:
    return query_engine.query(question)
```

#### Haystack

Extracts retriever / generator / reader / embedder / ranker from pipeline component output dict as `chain_steps`.

```python
from haystack import Pipeline
from agent_evaluator.decorators import agent_eval

pipeline = Pipeline()
# ... add components ...

# Component output dict → chain_steps
@agent_eval(monitor, task_type="information_retrieval", framework="haystack", rag_mode=True)
def haystack_agent(question: str, ground_truth: str = "") -> str:
    return pipeline.run({"query": question})
```

#### Semantic Kernel

Auto-extracts tokens from OpenAI / Anthropic backends via `inner_content`.
`function_name` + `plugin_name` → `"Plugin.function"` format tool calls also supported.

```python
import semantic_kernel as sk
from agent_evaluator.decorators import agent_eval

kernel = sk.Kernel()

# inner_content → tokens_used (auto-detects OpenAI/Anthropic backend)
@agent_eval(monitor, task_type="tool_use", framework="semantic_kernel")
async def sk_agent(question: str, ground_truth: str = "") -> str:
    result = await kernel.invoke(plugin_name, function_name, input=question)
    return str(result)
```

#### HuggingFace smolagents

Normalizes `ToolCall` step list for success/failure status and input values, extracting as `tool_calls` + `chain_steps`.
Note: smolagents does not support async.

```python
from smolagents import CodeAgent, HfApiModel
from agent_evaluator.decorators import agent_eval

model = HfApiModel()
agent = CodeAgent(tools=[...], model=model)

@agent_eval(monitor, task_type="tool_use", framework="smolagents")
def smol_agent(question: str, ground_truth: str = "") -> str:
    return agent.run(question)
```

#### vLLM

OpenAI-compatible API — extracts `choices[0].message.tool_calls` and `usage.total_tokens`.

```python
from openai import OpenAI  # vLLM uses OpenAI-compatible client
from agent_evaluator.decorators import agent_eval

client = OpenAI(base_url="http://localhost:8000/v1", api_key="vllm")

@agent_eval(monitor, task_type="qa", framework="vllm")
def vllm_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="meta-llama/Llama-3.2-3B-Instruct",
        messages=[{"role": "user", "content": question}],
    )
```

#### HuggingFace

Extracts chain steps from `generated_text` in `pipeline()` results, and tool calls from `actions` / `tool_calls` fields.
Note: HuggingFace does not support async.

```python
from transformers import pipeline
from agent_evaluator.decorators import agent_eval

pipe = pipeline("text-generation", model="Qwen/Qwen2.5-1.5B-Instruct")

@agent_eval(monitor, task_type="qa", framework="huggingface")
def hf_agent(question: str, ground_truth: str = "") -> str:
    return pipe(question, max_new_tokens=200)
```

---

### Auto-Detection (`auto_detect_framework=True`)

When `auto_detect_framework=True` (default), the framework is auto-detected by inspecting attributes of the returned object.

| Detection Condition | Detected Framework |
|--------------------|-------------------|
| `stop_reason` attribute present (no choices) | `anthropic` |
| `choices` + `usage` attributes present | `openai` |
| `candidates` + `usage_metadata` attributes present | `gemini` |
| `meta.tokens` attribute present (no choices) | `cohere` |
| `x_groq` attribute present | `groq` |
| `choices[0].finish_reason` == `"stop"` + mistral hint | `mistral` |
| `ResponseMetadata` + bedrock hint | `bedrock` |
| `step_results` attribute present | `smolagents` |
| `completions` attribute + DSPy type name | `dspy` |
| `all_messages` callable present | `pydanticai` |

```python
# Omit framework= → auto-detection (default)
@agent_eval(monitor, task_type="qa")
def auto_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # OpenAI → auto-detected as "openai"

# Explicitly disable auto-detection (fixed framework= takes priority)
@agent_eval(monitor, task_type="qa", framework="openai", auto_detect_framework=False)
def fixed_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)
```

---

## 58 Metrics and Decorator Activation Conditions

### Layer 1 — Foundation Metrics (auto-activated with basic decorator)

| Metric | Class | Decorator Automation | Key Outputs |
|--------|-------|---------------------|-------------|
| **Task Completion Rate** | `TaskCompletionTracker` | Always active | `tcr` · `full_success` · `partial_success` · `failures` |
| **Accuracy** | `AccuracyEvaluator` | Always active (default algorithm if no `score_fn`) | `overall_accuracy` · `median_accuracy` · `std_accuracy` |
| **Response Quality** | `ResponseQualityEvaluator` | Auto when response + request present | `dimension_scores` · `total_score` (0–5) · `grade` |
| **Latency** | `LatencyTracker` | Auto measures function execution time | `mean` · `p50` · `p90` · `p95` · `p99` · `std` |
| **Token Economy** | `TokenEconomyTracker` | Framework adapter auto-extraction | `total_tokens` · `total_cost` · `estimated_monthly_cost` |
| **Hallucination** | `HallucinationDetector` | `rag_mode=True` or `enable_hallucination_detection=True` | `hallucination_rate` · `unsupported_claims_count` · `by_severity` |

Accuracy calculation: Token Overlap(40%) + Jaccard Similarity(30%) + LCS(20%) + Char Similarity(10%)

### Layer 2-A — Agentic Metrics (activated when tool_calls · chain_steps auto-extracted)

| Metric | Class | Activation Condition | Key Outputs |
|--------|-------|---------------------|-------------|
| **Tool Call Analysis** | `ToolCallAnalyzer` | `tool_calls` auto-extracted or EvalMetadata | `efficiency_score` · `redundancy_rate` · `failure_rate` |
| **Retry & Correction** | `RetryCorrectionTracker` | `retry=RetryConfig(max=N)` parameter or `attempts` field | `retry_rate` · `first_attempt_success_rate` · `correction_success_rate` |
| **Tool Selection F1** | `ToolSelectionTracker` | `expected_tools_arg` parameter specified | `precision` · `recall` · `f1_score` |
| **Agent Coordination** | `AgentCoordinationTracker` | `agent_interactions` auto-extracted | `score` · `pattern_type` · `unique_agents` |
| **Workflow Execution** | `WorkflowExecutionTracker` | `chain_steps` · `state_transitions` auto-extracted | `step_success_rate` · `task_success_rate` · `bottlenecks` |

### Layer 2-B — Security Metrics (`security=SecurityConfig()` or Monitor global setting)

| Metric | Class | Detection Target | Key Outputs |
|--------|-------|-----------------|-------------|
| **Input Sanitization** | `InputSanitizationTracker` | SQL Injection · Command Injection · XSS · Prompt Injection (40 patterns) | `risk_level` · `threat_count` · `threat_rate` |
| **Output Leakage** | `OutputLeakageDetector` | API keys · passwords · credit cards · personal info | `severity` · `leakage_count` · `leakage_rate` |
| **Tool Authorization** | `ToolAuthorizationTracker` | Unauthorized tool use · dangerous parameters | `compliance_rate` · `violation_rate` · `unauthorized_calls` |
| **Privilege Escalation** | `PrivilegeEscalationDetector` | guest→admin privilege escalation chain | `risk_score` (0–10) · `escalation_detected` · `escalation_path` |
| **Tool Chain Attack** | `ToolChainAttackDetector` | Data exfiltration · lateral movement · persistence attack chains | `confidence` (0–1) · `attack_types` · `is_suspicious_chain` |

Security metric activation methods:

```python
from agent_evaluator.decorators import SecurityConfig

# Method A: temporarily activate for a specific function (this call only)
@agent_eval(monitor, task_type="qa", security=SecurityConfig())
def secure_agent(question, ground_truth=""): ...

# Method B: Monitor global setting (applies to all record_task calls)
monitor = PerformanceMonitor("results/", enable_security_metrics=True)
```

### Layer 3 — Hybrid Evaluation (external libraries)

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    use_deepeval=True,    # pip install "agent-evaluator[eval]"
    use_ragas=True,
    output_dir="results/",
)

# HybridPerformanceMonitor inherits PerformanceMonitor — all 3 decorator types work identically
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True, context_arg="context")
def rag_agent(question, context="", ground_truth=""): ...
```

| Provider | Metrics | Condition |
|----------|---------|-----------|
| **LLMJudge** *(v0.7.5+)* | completeness · relevance · factual · toxicity · bias | Included in base install · `llm_judge=LLMJudgeConfig()` |
| **LLMJudge** *(v0.7.6+)* | + **faithfulness** (RAG) · **custom criteria (G-Eval)** | `rag_mode=True` + `llm_judge=LLMJudgeConfig(criteria=[...])` |
| **DeepEval** | Hallucination(NLI) · Answer Relevancy (LLM) | `pip install "agent-evaluator[eval]"` |
| **Ragas** | Faithfulness · Answer Relevancy · Context Precision · Context Recall (LLM) | same + `context` field required |

### Harness Engineering — 33 Configs, 7 Gate Groups (A–G)

Pass Harness Configs as `@agent_eval` decorator parameters and `PerformanceMonitor` auto-aggregates them. Visualize group-level pass/warn/fail in the dashboard **Harness Gate** tab.

```python
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig, PlanConfig,   # Group A
    LoopDetectionConfig, StateConsistencyConfig,           # Group B
    FaultToleranceConfig, GracefulDegradationConfig,       # Group C
    SLAConfig, EfficiencyConfig,                           # Group D
    ThreatSeverityConfig, ComplianceConfig,                # Group E
    ConsensusConfig, AgentRoleConfig,                      # Group F
    ExplainabilityConfig, ObservabilityConfig,             # Group G
)

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

| Group | Area | Config (count) |
|-------|------|---------------|
| **A** | Goal Achievement | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig **(6)** |
| **B** | Behavioral Integrity | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig **(6)** |
| **C** | Reliability | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig **(5)** |
| **D** | Performance Contract | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig **(5)** |
| **E** | Security Boundary | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig **(3)** |
| **F** | Multi-Agent Coord. | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig **(4)** |
| **G** | Observability | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig **(4)** |

> **Note**: `TTFTVariabilityConfig` · `CostPredictabilityConfig` are auto-aggregated at monitor level (≥5 tasks with `ttft_ms` extra and token CV per task_type). No decorator parameter needed.

Full practical example: `Evaluator_Examples/ch03_harness_basics.py`

---

## CI/CD Quality Gating

### Directly in Code

```python
eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""): ...

# After evaluation
eval.gate(tcr=85, accuracy=70, quality=3.5, hallucination=5)
# sys.exit(1) if thresholds not met — CI pipeline fails
```

### CLI (GitHub Actions)

```yaml
- name: Run Evaluation
  run: python eval_suite.py --output results/ci.json

- name: Quality Gate
  run: |
    agent-eval gate results/ci.json \
      --tcr 85 --accuracy 70 --p95-latency 3.0 --hallucination 5
```

`agent-eval gate` options:

| Option | Description |
|--------|-------------|
| `--tcr N` | Minimum Task Completion Rate (%) |
| `--accuracy N` | Minimum accuracy (%) |
| `--p95-latency N` | Maximum P95 latency (seconds) |
| `--hallucination N` | Maximum hallucination detection rate (%) |
| `--llm-judge N` | Minimum LLM Judge overall score (0–5) |
| `--fail-on-regression N` | Allowed drop ratio vs. previous baseline (%) |
| `--junit-xml PATH` | JUnit XML output (CI integration) |

**Exit codes:** `0` = all passed / `1` = threshold not met / `2` = regression detected

---

## Conditional Alerts

All 3 decorator types support the same `alert_rules=` API.

```python
from agent_evaluator.decorators import AlertRuleBuilder

slow_rule  = AlertRuleBuilder.when_latency_above(3.0,  handler=lambda msg, tr: print(f"[SLOW] {msg}"))
error_rule = AlertRuleBuilder.when_accuracy_below(0.7, handler=lambda msg, tr: send_slack(msg))
fail_rule  = AlertRuleBuilder.when_completion_below(0.8, handler=lambda msg, tr: send_alert(msg))

# Applies equally to all 3 decorator types
@agent_eval(monitor,      task_type="qa", alert_rules=[slow_rule, error_rule])
def agent(question, ground_truth=""): ...

@batch_eval(monitor,      task_type="qa", alert_rules=[slow_rule])
def batch_agent(questions, ground_truths=None): ...

@conversation_eval(monitor, max_turns=5,  alert_rules=[fail_rule])
def chat(question, session_id="s1"): ...
```

---

## Periodic Auto-Save (`flush_every`)

Results are preserved even if the process exits mid-run. All 3 decorator types supported.

```python
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question, ground_truth=""): ...

@batch_eval(monitor, task_type="qa", flush_every=5)
def batch_agent(questions, ground_truths=None): ...

# Same in QuickEval
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
```

---

## preset — Environment-Specific Configuration Bundles

All 3 decorator types support the same `preset=` parameter.

| preset | Auto-applied Settings | Environment |
|--------|----------------------|-------------|
| `"production"` | `flush_every=50` · `enable_anomaly_detection=True` · `sample_rate=0.1` | Production server |
| `"development"` | `llm_judge=LLMJudgeConfig()` · `auto_detect_framework=True` | Development · debugging |
| `"testing"` | `sample_rate=1.0` · `timeout=10.0` | Unit testing |
| `"canary"` | `sample_rate=0.01` · `flush_every=100` | Canary deployment |

```python
@agent_eval(monitor,      task_type="qa", preset="production")
@batch_eval(monitor,      task_type="qa", preset="testing")
@conversation_eval(monitor, max_turns=5,  preset="development")
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `agent-eval init` | Interactive API key setup wizard |
| `agent-eval check` | Check current configuration and API keys |
| `agent-eval dashboard [dir]` | Run FastAPI dashboard web server |
| `agent-eval gate <result.json>` | CI/CD quality gating |
| `agent-eval trend <dir>` | Analyze TCR · accuracy trends across sequential results (regression detection) |
| `agent-eval dataset build <dir>` | Auto-extract golden dataset from production results |
| `agent-eval monitor` | Arize Phoenix + OTEL real-time monitoring |
| `agent-eval --version` | Print package version |

---

## Evaluation Result Output Scenarios

Metrics collected by decorators can be output in **three ways**.

| Scenario | Purpose | Additional Work |
|----------|---------|----------------|
| Terminal output | Immediate check · debugging | None |
| FastAPI dashboard | Visualization during development · validation | Run CLI after `save_to_file()` |
| Phoenix OTEL | Production real-time monitoring | Declare `setup_otel()` then run `agent-eval monitor` in separate terminal |

### Scenario 1 — Terminal Output

Immediately check results with `generate_report()` after decorator execution.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# Terminal output — generate_report() then to_json() or to_dict()
report = monitor.generate_report()
print(report.to_json(indent=2))
# → {"accuracy_metrics": {...}, "efficiency_metrics": {...}, "quality_metrics": {...}}
```

### Scenario 2 — FastAPI Dashboard

`save_to_file()` writes JSON to `results/`, and `agent-eval dashboard` reads it.

```python
# Method A: manual save after run
monitor.save_to_file("eval")          # creates results/eval.json + .html

# Method B: auto_save — auto-saves every N tasks
monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# Method C: QuickEval
eval = QuickEval("results/")
@eval.qa
def my_agent(q, ground_truth=""): ...
eval.save()                           # results/quickeval.json + .html
```

```bash
# Requires [serve] extra: pip install "agent-evaluator[serve]" or "agent-evaluator[sdk]"
agent-eval dashboard results/ --watch        # auto-refresh on file change
```

| URL | Content |
|-----|---------|
| `http://localhost:8765` | Main dashboard |
| `http://localhost:8765/slides` | Presentation slide view |
| `http://localhost:8765/api/docs` | Swagger API documentation |

### Scenario 3 — Phoenix Real-time Monitoring (OTEL)

`setup_otel()` must be called **before creating PerformanceMonitor**. All subsequent `record_task()` calls will automatically emit OTLP spans.

```bash
# Requires [otel] extra: pip install "agent-evaluator[otel]" or "agent-evaluator[sdk]"
agent-eval monitor                           # http://localhost:6006
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

# OTLP spans auto-sent on call → immediately visible in Phoenix Tracing tab
my_agent("What is the capital of South Korea?", ground_truth="Seoul")
```

Real-time monitoring available across 4 menus: Tracing · Evaluators · Datasets · Prompts.

---

## Public API

```python
from agent_evaluator import (
    PerformanceMonitor,            # evaluation orchestrator
    QuickEval,                     # one-stop facade
    HybridPerformanceMonitor,      # monitor with Layer 3
    TaskResult, TaskType, EvaluationReport,
    create_taskresult,
    evaluation_session, async_evaluation_session,
    ConversationSession, ConversationMetrics, ConversationTurn,
    LLMJudge,
    SimpleTaskAlertRule, AlertRuleBuilder,
)

from agent_evaluator.decorators import (
    # ── 3 core decorators ─────────────────────────
    agent_eval,           # single task (1 call → 1 TaskResult)
    batch_eval,           # batch evaluation (1 call → N TaskResults)
    conversation_eval,    # multi-turn conversation (N calls → 1 TaskResult)

    # ── unified factory & escape hatch ────────────
    EvalDecorator,        # common config factory for all 3 types
    eval_context,         # context manager when decorators can't be used

    # ── metadata & utilities ──────────────────────
    EvalMetadata,         # additional metadata for agent_eval / batch_eval
    TurnMetadata,         # per-turn metadata for conversation_eval
    get_eval_ctx,         # access thread-local evaluation context
    FrameworkLiteral,     # type hint for 21 frameworks
    get_framework_info,   # query framework adapter info
    AlertRuleBuilder,     # alert rule factory
    flush_conversation,   # manually end conversation session
    flush_all_conversations,
)
```

---

## Example Guide

Consists of 26 files based on book chapters. Each file is independently runnable.

### Example Dependencies

| Example | Chapter | Content | Optional |
|---------|---------|---------|---------|
| `ch01_first_eval.py` | Ch01 | Layer 1 basics — accuracy · hallucination · TCR | — |
| `ch02_quickstart.py` | Ch02 | QuickEval 5-minute first evaluation | — |
| `ch03_harness_basics.py` | Ch03 | Harness Gate A–G 7-gate overview | `agent-eval monitor` |
| `ch04_group_a.py` | Ch04 | Gate A: Goal Achievement (6 Configs) | — |
| `ch05_group_b.py` | Ch05 | Gate B: Behavioral Integrity (6 Configs) | — |
| `ch06_group_c.py` | Ch06 | Gate C: Reliability (5 Configs) | — |
| `ch07_group_d.py` | Ch07 | Gate D: Performance Contract (5 Configs) | — |
| `ch08_group_e.py` | Ch08 | Gate E: Security Boundary (3 Configs) | — |
| `ch09_group_f.py` | Ch09 | Gate F: Multi-Agent Coordination (4 Configs) | — |
| `ch10_group_g.py` | Ch10 | Gate G: Observability + AnomalyDetector · CostTracker | — |
| `ch11_eval_data.py` | Ch11 | Evaluation data design — GoldenSetBuilder · evaluation_session | — |
| `ch12_decorators.py` | Ch12 | Decorators mastery — @agent_eval · @batch_eval · QuickEval · LLMJudge | — |
| `ch13_frameworks.py` | Ch13 | Framework integration — LangChain · LangGraph · CrewAI · AutoGen | `agent-evaluator[langchain]` (optional) |
| `ch14_thresholds.py` | Ch14 | Threshold configuration and quality standards | — |
| `ch15_dashboard.py` | Ch15 | Dashboard visualization — QuickEval · AnomalyDetector · CostTracker data generation | `agent-eval dashboard` |
| `ch16_alerts.py` | Ch16 | Alert system — StreamingEvaluator · AlertEngine · SimpleTaskAlertRule | `SLACK_WEBHOOK_URL` (Mock if not set) |
| `ch17_weekly_review.py` | Ch17 | Weekly/monthly quality review automation | — |
| `ch18_cicd_gate.py` | Ch18 | CI/CD quality gating — Harness minimal verification · exit 0/1 | — |
| `ch19_phoenix.py` | Ch19 | Phoenix OTEL — Tracing · Datasets · GraphQL + DeepEval · Ragas | `agent-evaluator[eval]` + `OPENAI_API_KEY` (optional) |
| `ch20_deployment.py` | Ch20 | Production deployment strategy — v1 vs v2 Gate score comparison | — |
| `ch21_pipeline.py` | Ch21 | Comprehensive production pipeline — dev→CI→ops→improvement 4 stages | — |
| `ch22_project_analysis.py` | Ch22 | Existing project analysis — topology · LLM enumeration · risk prioritization | — |
| `ch23_gate_mapping.py` | Ch23 | Gate mapping strategy — failure mode catalog → Config translation + weight design | — |
| `ch24_quickeval_entry.py` | Ch24 | First migration — invasiveness Level 0/1 patterns + first measurements | — |
| `ch25_harness_full.py` | Ch25 | Full integration — central monitor + adapters + security scan + Gate F bug discovery | — |
| `ch26_cicd_weekly.py` | Ch26 | CI/CD completion — golden dataset · trend analysis · weekly review · cost drift | — |

### Running Examples

```bash
cd Evaluator_Examples

python ch01_first_eval.py      # Layer 1 basics — Accuracy · Hallucination · Quality · Latency · Token · TCR
python ch02_quickstart.py      # QuickEval 5-minute first evaluation
python ch03_harness_basics.py  # Harness Gate A–G overview — 7 Gates · 33 Configs
python ch04_group_a.py         # Gate A: Goal Achievement — InstructionConfig · GoalAlignmentConfig · etc.
python ch05_group_b.py         # Gate B: Behavioral Integrity — LoopDetectionConfig · StateConsistencyConfig · etc.
python ch06_group_c.py         # Gate C: Reliability — ReproducibilityConfig · FaultToleranceConfig · etc.
python ch07_group_d.py         # Gate D: Performance Contract — SLAConfig · TTFTVariabilityConfig · etc.
python ch08_group_e.py         # Gate E: Security Boundary — ThreatSeverityConfig · ComplianceConfig · etc.
python ch09_group_f.py         # Gate F: Multi-Agent Coordination — ConsensusConfig · AgentRoleConfig · etc.
python ch10_group_g.py         # Gate G: Observability + AnomalyDetector · CostTracker
python ch11_eval_data.py       # Evaluation data design — GoldenSetBuilder · evaluation_session
python ch12_decorators.py      # Decorators mastery — @agent_eval · @batch_eval · QuickEval · LLMJudge
python ch13_frameworks.py      # Framework integration — LangChain · LangGraph · CrewAI · AutoGen
python ch14_thresholds.py      # Threshold configuration and quality standards
python ch15_dashboard.py       # Dashboard visualization data generation
python ch16_alerts.py          # Alert system — StreamingEvaluator · AlertEngine
python ch17_weekly_review.py   # Weekly/monthly quality review automation
python ch18_cicd_gate.py       # CI/CD quality gating
python ch19_phoenix.py         # Phoenix OTEL + DeepEval · Ragas (opt-in)
python ch20_deployment.py      # Production deployment strategy
python ch21_pipeline.py        # Comprehensive production pipeline
python ch22_project_analysis.py  # Existing project analysis — 4 stages
python ch23_gate_mapping.py    # Gate mapping strategy
python ch24_quickeval_entry.py # First migration — Level 0/1 invasiveness
python ch25_harness_full.py    # Full integration pipeline
python ch26_cicd_weekly.py     # CI/CD completion + weekly review

# ── Infrastructure ──────────────────────────────────────────────────────────
agent-eval monitor             # Start Phoenix server (http://localhost:6006)
agent-eval dashboard --watch   # Dashboard (http://localhost:8765)
```

> Legacy 11 examples (01–08, 09, 10) are preserved in `Evaluator_Examples/.deprecated/`.

---

## Project Structure

```
agent-evaluator/
├── agent_evaluator/
│   ├── decorators.py            # agent_eval · batch_eval · conversation_eval
│   │                            # EvalDecorator · eval_context · EvalMetadata · TurnMetadata
│   ├── quick_eval.py            # QuickEval — one-stop facade
│   ├── core/
│   │   ├── trackers/
│   │   │   ├── base.py          # TaskResult · EvaluationReport · TaskType
│   │   │   ├── layer1.py        # 6 Foundation metrics
│   │   │   ├── layer2.py        # 5 Agentic metrics
│   │   │   ├── security.py      # 5 Security metrics (Layer 2-B)
│   │   │   ├── monitor.py       # PerformanceMonitor (orchestrator)
│   │   │   ├── conversation.py  # ConversationSession · ConversationMetrics
│   │   │   └── feedback.py      # ImplicitFeedbackTracker
│   │   ├── otel/                # OpenTelemetry integration ([otel] extra)
│   │   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   │   └── monitor_context.py   # evaluation_session · async_evaluation_session
│   ├── integrations/
│   │   ├── llm_judge.py         # LLMJudge
│   │   └── metric_adapters.py   # DeepEval · Ragas adapters
│   ├── serve/                   # FastAPI dashboard ([serve] extra)
│   ├── cli/                     # agent-eval CLI
│   ├── alerts/                  # AlertEngine · SimpleTaskAlertRule
│   ├── anomaly/                 # AnomalyDetector
│   ├── cost/                    # CostTracker · AdaptivePolicy
│   └── datasets/                # GoldenSetBuilder
│
├── Evaluator_Examples/          # 26 example files (ch01~ch26, legacy 11 preserved in .deprecated/)
├── tests/                       # 2,465+ test functions, 51 files
└── pyproject.toml
```

---

## Dependency Specification

**Packages included in base install** (`pip install agent-evaluator`)

| Package | Version Range | Purpose |
|---------|--------------|---------|
| `numpy` | ≥1.20.0, <3.0.0 | Numerical computation |
| `pandas` | ≥1.3.0, <4.0.0 | Metric aggregation |
| `python-dotenv` | ≥0.19.0, <2.0.0 | Environment variable management |
| `openai` | ≥2.0.0, <3.0.0 | LLMJudge engine |
| `anthropic` | ≥0.20.0, <1.0.0 | LLMJudge engine |

**SDK extras** (`pip install "agent-evaluator[sdk]"` — recommended for full CLI use)

| Extra | Package | Version Range | Purpose |
|-------|---------|--------------|---------|
| `[serve]` | `fastapi` | ≥0.110.0, <1.0.0 | `agent-eval dashboard` |
| `[serve]` | `uvicorn[standard]` | ≥0.29.0, <1.0.0 | `agent-eval dashboard` |
| `[serve]` | `jinja2` | ≥3.1.0, <4.0.0 | `agent-eval dashboard` |
| `[serve]` | `python-multipart` | ≥0.0.9, <1.0.0 | `agent-eval dashboard` |
| `[otel]` | `opentelemetry-sdk` | ≥1.20.0, <2.0.0 | `agent-eval monitor` |
| `[otel]` | `opentelemetry-exporter-otlp-proto-http` | ≥1.20.0, <2.0.0 | `agent-eval monitor` |
| `[otel]` | `arize-phoenix` | ≥14.0.0, <14.7.0 | Phoenix real-time monitoring² |
| `[pdf]` | `pdfplumber` | ≥0.10.0, <1.0.0 | Korean RAG PDF processing |
| **`[sdk]`** | serve + otel + pdf | — | **All CLI features (recommended)** |

² `arize-phoenix` upper bound `<14.7.0` — 14.7.0+ pulls pydantic-ai metapackage (170+ packages).

**Optional extras** (see [## Installation](#installation) for install commands)

| Extra | Key Packages | Install Time | Notes |
|-------|-------------|-------------|-------|
| `[examples]` | sdk + eval | heavy | Examples 01–06: base only · 07: eval additionally required |
| `[eval]` | deepeval ≥3.0, <4.0 · ragas ≥0.4, <2.0 · datasets ≥4.0, <6.0 | heavy | DeepEval/Ragas external evaluation |
| `[langchain]` | langchain ≥1.0, langgraph ≥1.0 | medium | For user LangChain agent code¹ |
| `[dspy]` | dspy-ai ≥2.0 | medium | For user DSPy agent code¹ |
| `[pydanticai]` | pydantic-ai ≥1.0, <2.0 | fast | For user PydanticAI agent code¹ |
| `[crewai]` | crewai ≥1.0, <2.0 | heavy (isolated) | For user CrewAI agent code¹ |
| `[autogen]` | pyautogen ≥0.3, autogen-agentchat ≥0.4 | heavy (isolated) | For user AutoGen agent code¹ |
| `[full]` | sdk + eval + langchain + dspy + pydanticai + crewai + autogen | very heavy | ⚠️ 10+ min, for full CI compatibility testing |
| `[dev]` | pytest · pytest-cov · ruff · mypy · build · twine | fast | Development environment |

¹ agent-evaluator itself works fully without these packages (duck typing). Install only when your agent code directly imports the framework.

---

## Development Environment

```bash
git clone https://github.com/bullpeng72/Agent-Evaluator.git
cd Agent-Evaluator
pip install -e ".[dev]"

pytest                          # run tests (2,465+)
ruff check agent_evaluator/    # lint
ruff format agent_evaluator/   # format
mypy agent_evaluator/          # type check
```

---

## Changelog

### v0.9.2 (2026-05-15) — GPT-5 Standardization · Token Parameter Modernization

- ✨ **GPT-5 Standardization**: Set `gpt-5-nano` as the default OpenAI model project-wide, including library config and all 26 examples.
- 🔧 **Modern Token Parameters**: Implemented `max_completion_tokens` for OpenAI API calls (GPT-5 compatible) while maintaining `max_tokens` for Anthropic.
- 📝 **Example Modernization**: Updated all 26 `Evaluator_Examples/` with OpenAI SDK snippets and latest model IDs (`gpt-5-nano`).
- 🔧 **Pricing Update**: Refined cost estimation for `gpt-5-nano` ($0.05/$0.40 per 1M tokens) in `llm_judge.py` and documentation.
- 🔧 **Environment Templates**: Modernized `.env.example` to accurately map all 26 book chapter examples to required variables.

### v0.9.1 (2026-04-27) — Dependency restructure · pip resolver optimization

- 🔧 `pyproject.toml` dependency restructure: reduced base install to 5 core packages, split fastapi · otel · pdfplumber into `[serve]` · `[otel]` · `[pdf]` · `[sdk]` extras
- 🔧 `arize-phoenix>=14.0.0,<14.7.0` upper bound fixed — prevents pydantic-ai metapackage (170+ packages) from auto-installing from 14.7.0+, `[sdk]` package count 170→90
- 🔧 `openai>=2.0.0,<3.0.0`, `langchain-openai>=1.0.0,<2.0.0`, `langchain-anthropic>=1.0.0,<2.0.0` range narrowed — minimizes pip resolver search space (openai candidates 277→37)
- 📝 Updated Docs example file references (21→26, ch01/ch02 filename corrections)

### v0.8.5 (2026-04-23) — SDK bug fixes

- Fixed silent `TypeError` suppression bug for dict-type `tokens_used` in `eval_efficiency()`
- Fixed `EfficiencyConfig` `cost_unit`/`target_cost_per_completion` design error (USD→tokens scale)
- `CostPredictabilityConfig` — isolated CV by separating `task_type` per agent, Gate D 0.640→0.876
- `ch10_group_g.py` — fixed `EvalMetadata(extra={...})` injection path, Gate G warn→pass

### v0.8.4 (2026-04-21) — Example files fully reorganized into chapter-based structure

- Example files fully reorganized from 11 → 17 `chXX_topic.py` chapter-based naming
- Added missing trackers to `ch05`, `ch07`, `ch10`, `ch02` (WorkflowExecution · Latency · TokenEconomy · AnomalyDetector · CostTracker)
- Synchronized Phoenix `service_name` and result filenames to chapter numbers
- Fixed missing `create_taskresult` import bug in `ch05_group_b.py`

### v0.8.3 (2026-04-21) — LLMJudge stability · Gate improvements · Security tracker expansion

- Auto-disable LLMJudge on consecutive errors (3 consecutive failures → restored via `reset_errors()`)
- Store `None` instead of `0` when `faithfulness` is missing — prevents score pollution
- Introduced `AGENT_EVALUATOR_JUDGE_PROVIDER` env var (`auto` / `openai` / `anthropic`)
- Added `llm_blend_weight` to `GoalAlignmentConfig` · `PlanConfig` (LLM-rule blend ratio, default 0.5)
- Added `LLMJudge.ajudge()` async method
- Fixed `LLMJudgeConfig.sample_rate` decorator propagation bug
- `agent-eval gate --min-gate-score / --group-weights` — weighted composite Gate A–G score judgment
- `agent-eval trend` cost trend analysis (`total_cost`, `--fail-on-regression` integration)
- `OutputLeakageDetector(excluded_unix_paths=[...])` — customizable system path exclusion list
- Added `sample_rate` parameter to security trackers (high-traffic performance optimization)
- Added `deadlock_by_type` classification to Group B · `insufficient_data_warnings` to Gate D
- `LLMJudge(escalation_model=..., escalation_threshold=2.5)` — multi-model auto-escalation

### v0.8.2 (2026-04-17) — Harness Config 33 unified format · Dashboard UI improvements

- Unified icon · formula · threshold badge format for all 33 Harness Config cards; added `08_harness_eval.py` example
- Dashboard Nav reorganized into 3-tier hierarchy; added Gate correlation heatmap (7×7 Pearson) · failure cascade tracking
- HTML report fully reorganized around Gate A–G; added 16 Gate columns to CSV export
- Group classification fix: StateConsistencyConfig · DeadlockConfig moved Group F→B
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
