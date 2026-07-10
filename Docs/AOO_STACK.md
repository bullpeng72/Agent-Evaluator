# AOO Stack — Agent-Evaluator + Ollama + OpenCode

AOO is a local, closed-loop agentic dev setup: [OpenCode](https://opencode.ai) (a local coding-agent
CLI) drives a local Ollama model, and Agent-Evaluator's `LiveGuardrail` sits in the middle — checking
every tool call *before* it executes (real-time Gate B/E), then feeding the same session into the
normal batch Gate A–G pipeline once it ends. It's the reference integration for running Agent-Evaluator
as a live guardrail rather than a post-hoc report.

No new detection logic is involved anywhere in this stack — `LiveGuardrail` reuses the exact same
Behavioral Integrity (loop detection, deadlock, scope, tool-parameter safety) and Security Boundary
(tool authorization, privilege escalation, tool-chain attack) evaluators that power Gates B/E in batch
mode, just called synchronously per tool call instead of per session.

> **Prototype status**: live-tested end-to-end against a real OpenCode + local Ollama session — it
> blocked a live `rm -f` deletion attempt mid-session and left the file intact. Design maturity is
> still prototype-level (a process-lifecycle race on one-shot `opencode run`, no cleanup on hard
> `kill -9`). Full design notes and known limitations: [`opencode-plugin/README.md`](../opencode-plugin/README.md).

## Why a subprocess bridge

Agent-Evaluator is a Python SDK; OpenCode plugins run on Node/Bun. Rather than reimplementing Gate B/E
logic in TypeScript, the plugin spawns one long-lived Python subprocess per session
(`python -m agent_evaluator.integrations.live_guardrail_stdio`) and exchanges JSON Lines over
stdin/stdout. The plugin itself carries no judgment logic — it's a thin client.

## Setup

```bash
pip install agent-evaluator   # or from a repo checkout: pip install -e .

agent-eval opencode install                       # .opencode/plugin/ (project-local, default)
# or: agent-eval opencode install --global         # ~/.config/opencode/plugin/
# or: agent-eval opencode install --force          # overwrite an existing install
# or: agent-eval opencode install --with-violation-search   # + register the search_violations MCP server
```

`agent-eval opencode install` bakes the interpreter that ran the command in as the plugin's default
`PYTHON_BIN`. Override it or the SQLite report location via env vars:

```bash
export AGENT_EVALUATOR_PYTHON=/path/to/venv/bin/python
export AGENT_EVALUATOR_OUTPUT_DIR=results/my_project
```

Adjust `GUARDRAIL_CONFIG` at the top of the installed `.opencode/plugin/agent-evaluator.ts` (the copy,
not the package-bundled source — reinstalling overwrites it) — it takes the same
`LoopDetectionConfig`/`DeadlockConfig`/`ScopeConfig`/`ToolParameterSafetyConfig` (Gate B) and
`ToolAuthorizationTracker`/`PrivilegeEscalationDetector`/`ToolChainAttackDetector` (Gate E) fields as
`@agent_eval`.

Once loaded: unsafe tool calls are blocked mid-session with an error the model sees immediately (and
can self-correct on), each session's Gate B/E verdict is upserted into a local SQLite store
(`results/opencode_live_guardrail/opencode_sessions.db` by default — read it back with
`agent_evaluator.storage.sqlite_backend.load_tasks_from_db`), and the verdict is also written back into
the OpenCode session transcript (`noReply: true`, no extra LLM turn) so a memory-indexing agent like
`ctx` can recall past violations in later sessions.

## Batch Gate A–G integration (SPEC-028)

Real-time (per-tool-call, Gate B/E) and batch (per-session, Gate A–G) evaluation are the same pipeline
underneath — the plugin's session-end bridge (`live_guardrail_report.record_and_save()`) calls the
exact same `PerformanceMonitor.record_task()`/`generate_report()` that `@agent_eval`/`QuickEval` use:

- **Gate G (Observability)**: the confirmed tool-call log LiveGuardrail already tracks is included
  automatically.
- **Gate D (Performance Contract)**: the plugin sends each session's actual wall-clock duration
  (session start → `session.idle`), instead of the previous hardcoded `0.0`.
- **Gate A (Goal Achievement)**: with no explicit success signal, `completion_score` defaults to a
  neutral `0.5` rather than a misleadingly perfect `1.0`. Report an automated check (e.g. "did the
  tests pass?") by adding `"success": true|false` to the payload sent to `live_guardrail_report`.
  `agent_version` also defaults to `"auto"` (see below), so distinct local iterations get distinct tags
  even without committing between them.

The result is a normal result file — point `agent-eval gate`/`agent-eval dashboard` at
`results/opencode_live_guardrail/` exactly as for any other run. See
`Evaluator_Examples/ch32_tdd_local_loop.py` (Section 5) for a runnable, end-to-end demonstration.

## Team scope claims — `.aoo/claims.jsonl` (SPEC-032/034/036/037/038)

When multiple sessions (or teammates) touch the same repo concurrently, `TeamConcurrencyConfig`
(passed to `LiveGuardrail`) checks structured-path tool calls (`read`/`edit`/`write` — `bash` is
excluded, since it has no reliable path to parse) against a shared `.aoo/claims.jsonl` log and blocks
overlapping scope claims. `TeamConcurrencyConfig.owner` (and `owner="auto"`, resolved once at
construction via `git config user.name`) excludes a developer's own claims from conflicting with their
own session.

Manage the log directly from the terminal with the `agent-eval claims` subcommand (a thin wrapper
around `append_claim()`/`load_active_claims()`/`audit_claims()` — no new logic):

```bash
agent-eval claims add src/ --developer auto   # open a claim (git identity auto-resolved)
agent-eval claims list                        # show active claims
agent-eval claims release <claim_id>          # release a claim
agent-eval claims audit --ttl-hours 8         # CI: flag TTL-exceeded/overlapping claims (exit 1)
```

`LiveGuardrail`'s checks only cover the agent's own tool calls — a human running `git commit` directly
bypasses them. `scripts/pre_commit_claim_check.py` closes that gap by reusing the same `audit_claims()`
and `BranchGuardConfig`/`get_current_branch()`/`is_branch_protected()` checks as a local pre-commit hook
(wire it up via `.pre-commit-config.yaml` or `.git/hooks/pre-commit` — see the script's docstring).

## `agent_version="auto"` in a fast local loop

`PerformanceMonitor(agent_version="auto")` resolves to the current git commit's short SHA, with a
`-dirty-<hash>` suffix appended when tracked files have uncommitted changes. This matters specifically
for AOO's rhythm — you typically fix code and restart a session without committing between iterations,
so tagging by commit SHA alone would collapse many distinct iterations into one tag. The dirty-hash
suffix keeps them distinguishable. See the main [README's Version-Aware Comparison section](../README.md#version-aware-comparison-v098)
for the general (non-AOO) mechanics.

## `search_violations` MCP server

Opt-in (`pip install "agent-evaluator[mcp]"`): `agent_evaluator.integrations.violation_search_mcp`
exposes a single stdio MCP tool, `search_violations(query: str, include_blocked: bool = False)`, that
full-text searches the same SQLite store (via an additive FTS5 index) for past Gate B/E blocks —
including fully-blocked attempts (`include_blocked=True`) that never made it into a normal result file.
`agent-eval opencode install --with-violation-search` registers it automatically; to register it
manually (or for other MCP clients):

```bash
opencode mcp add agent-evaluator-violations -- python -m agent_evaluator.integrations.violation_search_mcp
```

## Related docs

- [`opencode-plugin/README.md`](../opencode-plugin/README.md) — full design notes, live-verification
  history, and known limitations (Korean).
- `Docs/specs/SPEC-019-live-guardrail-api.md` — `LiveGuardrail` design.
- `Docs/specs/SPEC-024-local-ade-memory-layer.md` — `search_violations` design.
- `Docs/specs/SPEC-027-git-based-agent-version-tagging.md` — `agent_version="auto"` design.
- `Docs/specs/SPEC-028-aoo-batch-harness-integration.md` — batch Gate A–G integration design.
- `Docs/specs/SPEC-032-team-concurrency-scope-check.md`, `SPEC-034-claim-log-ci-audit.md`,
  `SPEC-035-branch-guard.md`, `SPEC-036-team-concurrency-owner-exclusion.md`,
  `SPEC-037-team-concurrency-owner-auto.md`, `SPEC-038-claims-cli.md` — team-concurrency/branch-guard
  design history.
- `Evaluator_Examples/ch30_live_guardrail.py`, `Evaluator_Examples/ch31_team_concurrency.py`,
  `Evaluator_Examples/ch32_tdd_local_loop.py` — runnable examples.
