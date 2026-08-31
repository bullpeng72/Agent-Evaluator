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

> **Status**: shipped, and live-verified end-to-end against a real, separate OpenCode + local Ollama
> session — twice in 2026-08 (`1.17.9`, then `1.18.9`) — each time it blocked a live file-deletion
> attempt mid-session and left the file intact. Two rough edges remain (a process-lifecycle race on
> one-shot `opencode run`, no cleanup on a hard `kill -9`) — see
> [Known limitations](#known-limitations) below.

## Why a subprocess bridge

Agent-Evaluator is a Python SDK; OpenCode plugins run on Node/Bun. Rather than reimplementing Gate B/E
logic in TypeScript, the plugin spawns one long-lived Python subprocess per session
(`python -m agent_evaluator.integrations.live_guardrail_stdio`) and exchanges JSON Lines over
stdin/stdout. The plugin itself carries no judgment logic — it's a thin client. The judgment source is
always the Python-side `LiveGuardrail`.

There are actually two bridges with different lifecycles, not one:

```
OpenCode (Node/Bun)                              Python
┌─────────────────────────┐   stdin/stdout   ┌────────────────────────────────────┐
│ agent-evaluator.ts       │◄────────────────►│ live_guardrail_stdio.py            │
│  tool.execute.before     │    JSON Lines    │  → gates/live_guardrail.py         │
│  tool.execute.after      │  (long-lived,    │    (Gate B pure functions +        │
│                          │   whole session) │     Gate E trackers, SPEC-019)     │
│                          │                  └────────────────────────────────────┘
│  session.idle/error      │   stdin/stdout   ┌────────────────────────────────────┐
│  (recordSessionReport)   │◄────────────────►│ live_guardrail_report.py           │
│                          │  (one-shot per   │  → PerformanceMonitor.record_task  │
│                          │   session end)   │    + save_to_file (sqlite upsert)  │
└─────────────────────────┘                   └────────────────────────────────────┘
```

`live_guardrail_stdio.py` (a long-lived request/response loop) handles `tool.execute.before`/`after`
for the whole session; once the session ends (`session.idle`), `live_guardrail_report.py` (a one-shot
process) folds that session's final `extra` into the batch report. They're separate bridges because
their lifecycles differ.

If your agent loop is already Python (i.e. you don't need the OpenCode plugin/subprocess bridge at
all), skip the bridge and call `LiveGuardrail` in-process instead — the `tool_guard` decorator
(`agent_evaluator.gates.live_guardrail`) wraps a tool function with the check → execute → record cycle
automatically inside a `live_guardrail_session()` block:

```python
from agent_evaluator.gates.live_guardrail import (
    LiveGuardrail, tool_guard, live_guardrail_session, GuardrailBlockedError,
)

guardrail = LiveGuardrail(scope=ScopeConfig(forbidden_tools=["webfetch"], fail_on_violation=True))

@tool_guard(audit_blocked=True)
def bash(command: str) -> str:
    return run_shell(command)

with live_guardrail_session(guardrail, task_id="session-1"):
    try:
        bash("rm -rf /")
    except GuardrailBlockedError as e:
        print(f"blocked (Gate {e.verdict.gate}): {e.verdict.reason}")
```

No new detection logic here either — same Gate B/E evaluators, just applied without the OpenCode
plugin/stdio round-trip. `fail_closed=False` (default) means a call outside an active
`live_guardrail_session()` just warns and runs unguarded; pass `fail_closed=True` for environments where
a missed check must be a hard error.

## Setup

```bash
pip install agent-evaluator   # or from a repo checkout: pip install -e .

agent-eval opencode install                       # .opencode/plugin/ (project-local, default)
# or: agent-eval opencode install --global         # ~/.config/opencode/plugin/
# or: agent-eval opencode install --force          # overwrite an existing install
# or: agent-eval opencode install --with-violation-search   # + register the search_violations MCP server
# or: agent-eval opencode install --with-recommend-fix       # + register the recommend_fix MCP server
# or: agent-eval opencode install --with-ask-insights         # + register the ask_insights MCP server

agent-eval opencode doctor      # verify the install actually works: plugin freshness + a live Python
                                # stdio-bridge round-trip (init, benign->allow, dangerous->block)
agent-eval opencode upgrade     # after a package update: re-copy the plugin .ts, never touching
                                # your sibling agent-evaluator.config.json
agent-eval opencode uninstall   # remove the plugin file + opencode.json mcp entries — run BEFORE `pip uninstall`
```

`agent-eval opencode doctor` verifies the installed copy actually registers all three plugin hooks
(`tool.execute.before`, `tool.execute.after`, `event`) and warns if one is missing — a plugin missing
just `tool.execute.after`, say, would still block dangerous calls in real time while silently never
feeding data into the batch report, exactly the kind of half-working state that's hard to notice on your
own.

`agent-eval opencode install` bakes the interpreter that ran the command in as the plugin's default
`PYTHON_BIN`. Override it or the SQLite report location via env vars:

```bash
export AGENT_EVALUATOR_PYTHON=/path/to/venv/bin/python
export AGENT_EVALUATOR_OUTPUT_DIR=results/my_project
```

To adjust the config, put a JSON object in a sibling `agent-evaluator.config.json` next to the installed
plugin (its top-level keys are shallow-merged over the built-in `GUARDRAIL_CONFIG` — SPEC-041). Keep it
in that file, not in the `.ts`: reinstalling / `agent-eval opencode upgrade` overwrites the `.ts` code
but never the `.config.json`. It takes the same
`LoopDetectionConfig`/`DeadlockConfig`/`ScopeConfig`/`ToolParameterSafetyConfig` (Gate B) and
`ToolAuthorizationTracker`/`PrivilegeEscalationDetector`/`ToolChainAttackDetector` (Gate E) fields as
`@agent_eval`.

Once loaded: unsafe tool calls are blocked mid-session with an error the model sees immediately (and
can self-correct on), each session's Gate B/E verdict is upserted into a local SQLite store
(`results/opencode_live_guardrail/opencode_sessions.db` by default — read it back with
`agent_evaluator.storage.sqlite_backend.load_tasks_from_db`), and the verdict is also written back into
the OpenCode session transcript (`noReply: true`, no extra LLM turn) so a memory-indexing agent like
`ctx` can recall past violations in later sessions.

## ctx self-correction feedback loop

The Gate B/E verdict summary computed at `session.idle` isn't just `console.log`ged — it's also written
into the session's actual message history via `client.session.prompt({ body: { noReply: true, ... } })`
(`recordVerdictToTranscript()`). `noReply: true` means it doesn't trigger a new LLM turn, but it still
lands permanently in OpenCode's session store, so a memory-indexing agent like `ctx` can pick it up on
its next pass — letting a later session look up "this tool combination hit a Gate B loop violation last
time" via `ctx search`. The summary spells out which checks were violated
(`loop_detection`/`scope`/`tool_authorization`/...), not just a score — a bare score doesn't tell the
next session's model what to avoid (`summarizeGuardrailResult()`).

An earlier prototype only logged to `console.log`, so this feedback loop silently did nothing — `ctx`
indexes the session message history, not console output. Confirming that the installed
`@opencode-ai/sdk` type declarations support a `noReply` option (`types.gen.d.ts`) fixed it.

Note this loop only closes at `session.idle` — see [Known limitations](#known-limitations) for what
happens when a session ends abnormally instead.

### Why the SQLite backend exists alongside ctx

The feedback loop above depends on `ctx` actually being able to index OpenCode's session content. Live
verification (`ctx` 0.19.0) found its OpenCode importer only pulls in session metadata (title, token
counts), not the actual message/tool-call content (`ctx show session --mode full` surfaced two
lifecycle notifications and no verdict text). Since `live_guardrail_report.py` already persists the full
verdict detail to Agent-Evaluator's own SQLite backend on every `session.idle`, `search_violations`
(below) works around that `ctx` gap by making the same data independently searchable.

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
`results/opencode_live_guardrail/` exactly as for any other run.

> **Note**: `ToolCallAnalyzer.analyze()` treats a tool call with no `success` key as a success by
> default. The `tool.execute.after` hook now captures each call's real result (`exit_code` / `stdout` /
> `success`, SPEC-031) and promotes it into `TaskResult.tool_calls`, so Gate G's success rate is
> accurate for calls that carry that data. A call whose result the plugin could not determine still
> counts as a success — so a session where the plugin's `after` hook never fired can still read
> optimistically.

## Blocked-attempt Slack alerts (opt-in)

A block that only lands in the SQLite audit trail is easy for nobody to ever look at — the same "a
verdict and an enforced consequence are two different things" trap the whole stack is built to close,
just aimed at humans instead of the model this time (Harness Method Ch13 §13.2). Set
`AGENT_EVALUATOR_ALERT_WEBHOOK_URL` and `live_guardrail_report.record_and_save()` sends **one** Slack
message per session that had any blocked attempts, listing each blocked tool/gate/reason:

```bash
export AGENT_EVALUATOR_ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

This fires from the one-shot, session-end batch bridge — not from `tool.execute.before` — so it never
adds latency to the agent's live loop, and repeated blocked attempts within one session collapse into a
single notification instead of spamming one per attempt. It reuses the SDK's existing
`agent_evaluator.alerts.handlers.SlackHandler` (the same one `StreamingEvaluator`'s anomaly alerts use —
no new notification logic), and the webhook URL is read directly by this Python process — it's never
passed through the Node plugin or written into `GUARDRAIL_CONFIG`. A failed send (bad URL, network error)
never blocks the session report from saving.

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
suffix keeps them distinguishable. See [the "Version comparison" section of `Docs/08_API_REFERENCE.md`](08_API_REFERENCE.md#version-comparison--prompt_version--agent_version-v098)
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

## `recommend_fix` MCP server

Opt-in (same `[mcp]` extra): `agent_evaluator.integrations.recommend_fix_mcp` exposes a single stdio MCP
tool, `recommend_fix(gate: str, metric: str | None = None, value: float | None = None)`. Where
`search_violations` answers "what happened before," `recommend_fix` answers "what should I do about
Gate X being bad" — a static lookup over `agent_evaluator.ontology.metric_registry`
(`GATE_GUIDANCE`/`NATIVE_METRIC_RULES`/`ANOMALY_METRIC_SUGGESTIONS`) and, for Gate F, the MAST failure-mode
taxonomy. No result file is required — it works even before the agent under development has been
evaluated once. `agent-eval opencode install --with-recommend-fix` registers it automatically; to
register it manually (or for other MCP clients):

```bash
opencode mcp add agent-evaluator-recommend-fix -- python -m agent_evaluator.integrations.recommend_fix_mcp
```

## `ask_insights` MCP server

Opt-in (same `[mcp]` extra): `agent_evaluator.integrations.ask_insights_mcp` exposes stdio MCP tools
that query a result JSON's `extra_metrics.insights` layer with structured questions —
`insights_summary`, `insights_readiness` (path to green), `insights_why_failed(task_id)`,
`insights_contrast(task_id)` (the failure beside its nearest passing task), and `insights_list(filter)`.
Where `recommend_fix` gives static per-gate advice, `ask_insights` reads *this run's* verdicts.
`agent-eval opencode install --with-ask-insights` registers it automatically:

```bash
opencode mcp add agent-evaluator-ask-insights -- python -m agent_evaluator.integrations.ask_insights_mcp
```

## Known gotchas from live OpenCode validation

The plugin was live-tested end to end against a real OpenCode `1.17.9` + local Ollama `qwen3-coder`
session. That surfaced issues no amount of reading the OpenCode docs would have caught:

**Hook shapes had to be verified against the installed package's own type declarations**, since the
public docs don't enumerate every hook-callback field:
- `session.idle`/`session.error` aren't standalone hooks — there is no such key on the `Hooks`
  interface. Every session lifecycle event arrives through a single `event` hook
  (`event: (input: { event: Event }) => Promise<void>`), where `Event` is a discriminated union on
  `type` (`"session.idle"` / `"session.error"` / `"session.created"` / ...). `agent-evaluator.ts`
  branches on `event.type`.
- `tool.execute.after`'s call arguments live in `input.args`, not `output.args` — `output` is
  `{title, output, metadata}`, the execution *result*, not the arguments. An earlier version read the
  wrong field (silently always `undefined`).
- `input.sessionID` is a required field on both `tool.execute.before`/`after`, not optional — an
  earlier fallback-chain that probed several candidate field names for it is no longer needed.

**`opencode run` hangs forever if stdin is left open** (unrelated to this plugin) — headless
`opencode run "..."` without explicitly closing stdin stalls right after the `init` log. Reproduces even
with `--pure` (all plugins disabled) and in a plain directory, ruling out both the plugin and the
working directory as the cause. Always close stdin for headless/CI invocations:

```bash
opencode run --dir /path/to/project "your message" \
  --dangerously-skip-permissions < /dev/null
```

### Shipped defaults, and why they are what they are

The shipped `GUARDRAIL_CONFIG` (`opencode_plugin/agent-evaluator.ts`) — its rationale is a direct
product of live tuning against OpenCode's coarse tool granularity, but the values changed over SPEC-041.
The authoritative current values are in that file, `CLAUDE_CODE_HOOKS.md` (the symmetric Claude Code
default), and `CHANGELOG.md`. As of 1.0.0:

- **`consecutive_repeat_threshold: 8`** (+ `live_loop_window: 15`, + `circuit_breaker_after: 5`).
  OpenCode routes every shell action through a single `"bash"` tool, so name-only loop detection at a
  low threshold false-positives on a normal `ls → cat → ls` sequence. Loop identity now compares tool
  *name + SHA1 of sorted arguments*, not just the name — but the coarse-`"bash"` risk still argues for a
  high threshold here. `on_loop_detected` is omitted, so the OpenCode default is `"record"` (observe,
  don't block); the Claude Code hook default is `"fail"` because its tools are already fine-grained.
- **`dangerous_patterns`** was trimmed to genuinely destructive commands: `rm -rf` / `-fr`,
  semicolon-chained `rm`, `mkfs`, `dd of=/dev/…`, fork bombs, and pipe-to-shell. Bare `rm <file>` and
  `rm -f` are **not** blocked by the pattern list (too common in normal coding), though
  `ToolAuthorizationTracker`'s hardcoded Gate E backstop still catches `rm -rf`. This is a deliberate
  precision/recall trade — the earlier prototype blocked bare `rm` and produced too many false
  positives.
- **`scope_tool_names: ["bash"]`** scopes the `dangerous_patterns` scan to the actual shell tool, so it
  can't false-positive on an unrelated tool whose *result text* happens to mention a blocked command.

The blacklist approach is still blacklist matching against known bypasses, not an allowlist — live
testing found a model try `-rf` → `-f` → no-flag in sequence, so assume other bypasses remain possible.

**Re-confirmed 2026-08-26** against OpenCode `1.18.9` + local Ollama `qwen3-coder:latest` (a fresh
re-run, not a rerun of the original session): a real `opencode run` session was told to delete a
throwaway file via `rm`. The `tool_use` event in the JSON output stream showed the call itself land as
`status: "error"` with `error: "[agent-evaluator] blocked by Gate B: dangerous tool parameters:
['bash']..."`; the model then ran `ls` to check and reported the file was still there; the file itself
was confirmed intact on disk; and the batch report
(`results/opencode_live_guardrail/opencode_sessions.db`) recorded the blocked `rm` in
`blocked_attempts` while the follow-up `ls` landed correctly in `tool_calls` with real
`stdout`/`exit_code`/`success` (SPEC-031's `output` field working as designed). One thing that did
**not** reproduce this time: the "`opencode run` hangs on open stdin" gotcha documented above — this run
used `--auto --format json` with no explicit `< /dev/null` and completed cleanly (exit 0, no hang).
Unclear whether that's fixed in `1.18.9` or just didn't trigger under these specific flags — not
confirmed either way, so the stdin-close workaround above is left in place rather than removed.

## Known limitations

- **Pipe-closing race on one-shot `opencode run`** (reproduced live): `session.idle` triggers
  `recordSessionReport()`, which spawns a Python subprocess and awaits its response — but `opencode run`
  can start tearing the process down right after printing the final response text, without waiting for
  the `event` hook's async work to finish. This has produced an observed `BrokenPipeError` on the Python
  side from an early-closed stdout pipe. `record_and_save()` (the batch write itself) has already
  completed by that point, so this isn't data loss, but the ctx feedback loop
  (`recordVerdictToTranscript()`) can fail to run if the Node side never gets the confirmation. Expected
  to be far less likely under long-lived modes (`opencode serve`/TUI), though that hasn't been
  separately verified.
- **Process lifecycle**: the `event` hook (`session.idle`/`session.error`) and the `dispose` hook (full
  cleanup on normal plugin unload) both terminate the `live_guardrail_stdio` subprocess. A hard kill of
  the OpenCode process itself (`kill -9`) skips `dispose` too, which can leave a zombie subprocess.
- **`live_guardrail_report` failures don't block the session**: if the batch write fails (e.g. no write
  permission on `output_dir`), the session still ends normally (only a `console.error` is logged) — the
  guardrail's real-time judgment already ran correctly for the whole session, so a report-write failure
  shouldn't be allowed to block the OpenCode session itself.
- **Blocked attempts aren't written to the transcript immediately**: the block reason reaches the
  model in that turn via a thrown error (confirmed working as a self-correction signal — a live model
  recognized and stated that its `rm` attempt "was blocked due to security restrictions"), but the
  transcript write (`client.session.prompt()`) only happens once, at `session.idle`. If the session ends
  abnormally without ever firing `session.idle`, the ctx feedback loop is skipped entirely for that
  session.
- **`GUARDRAIL_CONFIG`'s shipped values are a starting point, not a guarantee**: `dangerous_patterns`
  is blacklist matching against known bypasses, not an allowlist (see [Shipped defaults](#shipped-defaults-and-why-they-are-what-they-are)),
  so assume other bypasses remain possible. Treat the real-time guardrail as defense in depth, not a
  sole control.

## Related docs

- `Docs/specs/SPEC-019-live-guardrail-api.md` — `LiveGuardrail` design.
- `Docs/specs/SPEC-024-local-ade-memory-layer.md` — `search_violations` design.
- `Docs/specs/SPEC-027-git-based-agent-version-tagging.md` — `agent_version="auto"` design.
- `Docs/specs/SPEC-028-aoo-batch-harness-integration.md` — batch Gate A–G integration design.
- `Docs/specs/SPEC-032-team-concurrency-scope-check.md`, `SPEC-034-claim-log-ci-audit.md`,
  `SPEC-035-branch-guard.md`, `SPEC-036-team-concurrency-owner-exclusion.md`,
  `SPEC-037-team-concurrency-owner-auto.md`, `SPEC-038-claims-cli.md` — team-concurrency/branch-guard
  design history.
- `Docs/specs/SPEC-039-decorator-architecture-fixes.md` — `tool_guard`/`live_guardrail_session()` design.
- `Evaluator_Examples/ch22_tool_guard_realtime.py` — runnable example of the `tool_guard` decorator
  pattern used throughout this stack.
- `agent_evaluator/gates/live_guardrail.py` — the actual Gate B/E judgment logic + `tool_calls` exposure
  (SPEC-028 REQ-1).
- `agent_evaluator/integrations/live_guardrail_stdio.py` — the long-lived, protocol-agnostic (not
  OpenCode-specific) stdio bridge used throughout a session.
- [`CTX_SESSION_SEARCH.md`](CTX_SESSION_SEARCH.md) — optional, non-core individual workflows that pivot
  from a Gate regression/golden-set/A-B question into `ctx`'s cross-session search (Claude Code provider
  only — confirms this doc's OpenCode-importer gap does *not* apply the same way there).
- [`CLAUDE_CODE_HOOKS.md`](CLAUDE_CODE_HOOKS.md) — the same `LiveGuardrail` engine wired into Claude Code
  CLI's own hooks instead of an OpenCode plugin.
- [`OPENCODE_VS_CLAUDE_CODE.md`](OPENCODE_VS_CLAUDE_CODE.md) — detailed side-by-side comparison of the
  two integrations.
- `agent_evaluator/integrations/live_guardrail_report.py` — the one-shot, session-end batch-integration
  bridge, with opt-in `success`/`execution_time`/`agent_version` fields (SPEC-028).
- `agent_evaluator/integrations/opencode_plugin/agent-evaluator.ts` — the plugin source itself; its
  header comments record the live-tuning history behind `GUARDRAIL_CONFIG` cited above.
