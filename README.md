# Agent Evaluator

[![PyPI version](https://img.shields.io/pypi/v/agent-evaluator.svg)](https://pypi.org/project/agent-evaluator/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/bullpeng72/Agent-Evaluator)

**Harness Engineering evaluation SDK that judges AI agent deployment readiness through 7 Gates.**

It asks not just "does the agent work well?" but **"is the agent ready for production?"** One decorator
line auto-recognizes **24 frameworks** (LangChain, CrewAI, AutoGen, …) and measures **58 metrics
(25 Native Trackers + 33 Harness Config)** without touching your agent code — then aggregates them into
7 Gate pass/warn/fail judgments, a root-cause diagnosis engine for regressions, and statistically valid
A/B testing.

```bash
pip install agent-evaluator
```

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)          # your agent code — unchanged

my_agent("What is the capital of South Korea?", ground_truth="Seoul")

eval.save()                                        # results/quickeval.json + .html
eval.gate(tcr=85, accuracy=70, hallucination=5)    # CI/CD gate — sys.exit(1) if unmet
```

---

## The 7 Harness Gates

| Gate | Area | Judgment Criteria | Harness Config (count) |
|------|------|-------------------|----------------------|
| **A** 🟢 | **Goal Achievement** | Instruction compliance · goal alignment · plan consistency · context retention | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig **(6)** |
| **B** 🔵 | **Behavioral Integrity** | Loop detection · scope deviation · tool safety · state consistency · deadlock detection | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig **(6)** |
| **C** 🟡 | **Reliability** | Reproducibility · error recovery rate · hallucination faithfulness · quality floor · idempotency | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig **(5)** |
| **D** 🔵 | **Performance Contract** | SLA compliance · token efficiency · TTFT variability · cost predictability | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig **(5)** |
| **E** 🔴 | **Security Boundary** | Threat severity · compliance · threat response behavior | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig **(3)** |
| **F** 🟣 | **Multi-Agent Coordination** | Inter-agent consensus · information propagation accuracy · role compliance · conflict resolution | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig **(4)** |
| **G** 🩵 | **Observability** | Reasoning explainability · internal state tracking · error diagnosis · latency attribution | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig **(4)** |

Pass any of the 33 Configs above as `@agent_eval`/`@batch_eval`/`@conversation_eval` parameters and
`PerformanceMonitor` auto-aggregates each Gate's pass/warn/fail from the underlying trackers — no
separate scoring pass needed.

```python
@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),   # Gate A
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=6),                    # Gate B
    sla=SLAConfig(p95_ms=3000),                                                            # Gate D
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

Full Gate reference: [`Docs/05_QUALITY_GATE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/05_QUALITY_GATE.md) · Runnable walkthrough:
[`Evaluator_Examples/ch03_harness_basics.py`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Evaluator_Examples/ch03_harness_basics.py)

---

## What's Inside

- **3 decorator types** — `@agent_eval` (1 call → 1 result), `@batch_eval` (1 call → N results),
  `@conversation_eval` (N calls → 1 multi-turn result). All non-invasive: your function's signature,
  return value, and exceptions are untouched. → [`Docs/01_GETTING_STARTED.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/01_GETTING_STARTED.md)
- **24 framework adapters** — `framework="langchain"`/`"crewai"`/`"anthropic"`/`"openai"`/… auto-extracts
  `tool_calls`/`chain_steps`/`tokens_used` from the framework's native response object (duck typing —
  works without agent-evaluator importing the framework itself). → [`Docs/03_INTEGRATION_GUIDE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/03_INTEGRATION_GUIDE.md)
- **58 metrics** — 25 Native Trackers (accuracy, hallucination, latency, tool efficiency, 5 security
  trackers, …) + the 33 Harness Configs above. → [`Docs/02_METRICS_GUIDE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/02_METRICS_GUIDE.md)
  or the in-app **SDK Reference** (`agent-eval dashboard` → `/sdk-docs`)
- **CI/CD quality gating** — `agent-eval gate result.json --tcr 85 --accuracy 70`, plus baseline
  regression detection, per-version baselines, and golden-set regression gating.
  → [`Docs/05_QUALITY_GATE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/05_QUALITY_GATE.md)
- **Root-cause diagnosis (RCA)** — `agent-eval diagnose` / `agent_evaluator.rca.diagnose()` automates
  detect → attribute → cross-reference for a Gate regression, and links Gate F findings to the MAST
  failure-mode taxonomy (Cemri et al., NeurIPS 2025). Candidates and evidence only — HOTL, never a
  verdict. → [`Evaluator_Examples/ch28_rca_diagnosis.py`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Evaluator_Examples/ch28_rca_diagnosis.py)
- **Statistically valid A/B testing** — `agent-eval abtest` auto-selects Welch's t-test (2 files),
  mSPRT always-valid inference (`--sequential`, safe under repeated peeking), or N-way + FDR correction
  (3+ files). → [`Evaluator_Examples/ch29_sequential_ab_test.py`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Evaluator_Examples/ch29_sequential_ab_test.py)
- **Real-time guardrail (AOO stack)** — `LiveGuardrail` blocks a single tool call *before* it executes
  (Gate B/E), with a reference [OpenCode](https://opencode.ai) plugin (`agent-eval opencode install`)
  and native [Claude Code](https://claude.com/claude-code) CLI hooks (`agent-eval claude install`).
  → [`Docs/AOO_STACK.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/AOO_STACK.md) ·
  [`Docs/CLAUDE_CODE_HOOKS.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/CLAUDE_CODE_HOOKS.md)
- **Dashboard** — `agent-eval dashboard` (FastAPI): Harness Gate breakdown, File Compare with pairwise
  LLM Judge, anomaly/cost tracking, and a 🔧 Improve tab surfacing the RCA engine.

---

## Installation

Extras are organized into **5 categories by intent** — pick the one(s) that match what you're trying
to do. Every category is additive and independent; combine as needed.

| # | Category | Install | What it adds |
|---|----------|---------|---------------|
| **1** | **Base measurement + diagnosis** | `pip install agent-evaluator` | 25 trackers · 33 Harness Config · 7 Gates · LLMJudge · **RCA diagnosis engine** (`agent_evaluator.rca`/`ontology`, no extra deps needed) · CLI (`gate`/`diagnose`/`abtest`/`claims`/`trend`/`dataset`) |
| **2** | **SDK — dashboard + monitoring** | `pip install "agent-evaluator[sdk]"` | FastAPI dashboard (`serve`), Phoenix/OTEL (`otel`), Korean RAG PDF processing (`pdf`+`korean`) — recommended for most users |
| **3** | **Real-time guardrail — OpenCode/Claude Code + MCP** | `pip install "agent-evaluator[mcp]"` | `search_violations` + `recommend_fix` MCP servers so OpenCode, Claude Code (or another MCP client) can call them as tools during a live session — the underlying functions already work without this (used directly by `agent-eval diagnose`); this only wires up the MCP protocol layer |
| **4** | **Your agent's framework** | `pip install "agent-evaluator[langchain]"` (or `[crewai]`/`[autogen]`/`[dspy]`/`[pydanticai]`/`[eval]`) | Packages your *agent code* imports directly — agent-evaluator itself works without them via duck typing; install only what you actually use |
| **5** | **Examples / full / dev** | `pip install "agent-evaluator[examples]"` | Everything needed to run `Evaluator_Examples/` with real (non-mock) DeepEval/Ragas/dashboard/Phoenix output. `[full]` = category 4's frameworks all at once (⚠️ 10+ min install); `[dev]` = contributor tooling |

Single-feature extras that don't fit the 5 categories above: `[export]` (dashboard Parquet/Excel),
`[wandb]`, `[mlflow]`. Full package-by-package breakdown: [`pyproject.toml`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/pyproject.toml).

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `agent-eval init` / `check` | Interactive API key setup / configuration status |
| `agent-eval dashboard [dir]` | FastAPI dashboard web server |
| `agent-eval gate <result.json>` | CI/CD quality gating |
| `agent-eval diagnose <result.json>` | Root-cause diagnosis for a Gate regression |
| `agent-eval abtest <files...>` | Statistical A/B / N-way comparison |
| `agent-eval trend <dir>` | Regression detection across sequential results |
| `agent-eval dataset build <dir>` | Auto-extract golden dataset from production results |
| `agent-eval monitor` | Arize Phoenix + OTEL real-time monitoring |
| `agent-eval opencode install` | Install the LiveGuardrail OpenCode plugin |
| `agent-eval claude install` | Install the LiveGuardrail Claude Code CLI hooks |
| `agent-eval claims add\|list\|release\|audit` | Team scope-claim management (`.aoo/claims.jsonl`) |

---

## Examples

31 standalone, book-chapter-based files in [`Evaluator_Examples/`](https://github.com/bullpeng72/Agent-Evaluator/tree/Agent-Evaluator/Evaluator_Examples/) (`ch01`–`ch31`),
covering everything from a first evaluation to the full RCA/A/B-testing improvement loop:

```bash
pip install "agent-evaluator[examples]"
cd Evaluator_Examples && python ch01_first_eval.py   # ... through ch31_recommendation_tracking.py
```

---

## Project Structure

```
agent_evaluator/
├── decorators.py       # agent_eval · batch_eval · conversation_eval · QuickEval facade (quick_eval.py)
├── gates/               # Gate A–G scoring (gate_a_goal/ … gate_g_observability/) + LiveGuardrail
├── core/trackers/       # 25 Native Trackers (Layer 1 foundation · Layer 2 agentic/security) + monitor.py
├── rca/                  # diagnose() — Gate regression root-cause diagnosis + recommendation tracking
├── ontology/              # GATE_GUIDANCE / MAST failure-mode taxonomy (Gate F)
├── integrations/         # LLMJudge · DeepEval/Ragas adapters · MCP servers
├── serve/                # FastAPI dashboard ([serve] extra)
├── cli/                  # agent-eval CLI (gate, diagnose, abtest, trend, claims, opencode, claude, monitor, dataset)
└── reporting/             # comprehensive_report.py — self-contained HTML report generation

Evaluator_Examples/       # 31 example files (ch01–ch31)
tests/                    # 3,900+ test functions
```

---

## Changelog

**v1.0.0** (2026-08-25) — First stable release.

Beta version history: [`CHANGELOG.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/CHANGELOG.md)

---

## Documentation

| | |
|---|---|
| [`Docs/01_GETTING_STARTED.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/01_GETTING_STARTED.md) | Decorators, QuickEval, first evaluation |
| [`Docs/02_METRICS_GUIDE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/02_METRICS_GUIDE.md) | All 58 metrics — formulas, activation conditions |
| [`Docs/03_INTEGRATION_GUIDE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/03_INTEGRATION_GUIDE.md) | 24 framework adapters, auto-detection |
| [`Docs/04_DATA_GUIDE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/04_DATA_GUIDE.md) | Golden datasets, evaluation data design |
| [`Docs/05_QUALITY_GATE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/05_QUALITY_GATE.md) | Harness Gates, CI/CD gating, RCA diagnosis |
| [`Docs/06_OBSERVABILITY.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/06_OBSERVABILITY.md) | Dashboard, alerts, anomaly detection |
| [`Docs/07_OPERATIONS.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/07_OPERATIONS.md) | Production deployment, monitoring |
| [`Docs/08_API_REFERENCE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/08_API_REFERENCE.md) | Full public API reference |
| [`Docs/AOO_STACK.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/AOO_STACK.md) | Real-time guardrail, OpenCode + Ollama integration |
| [`Docs/CLAUDE_CODE_HOOKS.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/CLAUDE_CODE_HOOKS.md) | Real-time guardrail via native Claude Code CLI hooks |
| [`Docs/OPENCODE_VS_CLAUDE_CODE.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/OPENCODE_VS_CLAUDE_CODE.md) | OpenCode vs Claude Code integration — detailed comparison |
| [`Docs/CTX_SESSION_SEARCH.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/Docs/CTX_SESSION_SEARCH.md) | Optional cross-session search workflows (`ctx`) |
| [`CHANGELOG.md`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/CHANGELOG.md) | Version history |

Also available in-app once the dashboard is running: `agent-eval dashboard` → **SDK Reference**
(`/sdk-docs`) and **REST API** (`/api/docs`).

---

## Development

```bash
git clone https://github.com/bullpeng72/Agent-Evaluator.git
cd Agent-Evaluator
pip install -e ".[dev]"

pytest                          # run tests
ruff check agent_evaluator/    # lint
mypy agent_evaluator/          # type check
```

## License

MIT — see [`LICENSE`](https://github.com/bullpeng72/Agent-Evaluator/blob/Agent-Evaluator/LICENSE).
