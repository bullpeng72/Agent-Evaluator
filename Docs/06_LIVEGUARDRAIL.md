# LiveGuardrail — Real-Time Guardrail Reference

`LiveGuardrail` (`agent_evaluator.gates.live_guardrail`) runs the same Behavioral Integrity (Gate B —
loop detection, deadlock, scope, tool-parameter safety) and Security Boundary (Gate E — tool
authorization, privilege escalation, tool-chain attack) evaluators that score Gates B/E in a batch
`@agent_eval` run, but synchronously, **before** a tool call executes — so a dangerous call can be
stopped instead of only scored after the fact.

It is a single Python class with no framework dependency. Two first-party integrations wire it into a
specific host ([`07_CLAUDE_CODE_HOOKS.md`](07_CLAUDE_CODE_HOOKS.md), [`08_AOO_STACK.md`](08_AOO_STACK.md) for
OpenCode) — but `LiveGuardrail` itself is general-purpose: any Python agent loop can use it directly.
This document covers the class itself, all three ways to call it, and the v1.1.0 hardening that makes a
blocked call durable and discoverable even with no host present.

## Three usage modes

| Mode | Who calls what | When to use it |
|------|-----------------|-----------------|
| **Host-integrated** | Claude Code CLI hooks / OpenCode plugin call `LiveGuardrail` for you at every tool call and persist the audit trail automatically | You're already running Claude Code or OpenCode — see [`07_CLAUDE_CODE_HOOKS.md`](07_CLAUDE_CODE_HOOKS.md) / [`08_AOO_STACK.md`](08_AOO_STACK.md) |
| **`tool_guard()` + `live_guardrail_session()`** | You decorate your own tool functions; the decorator handles check → execute → record automatically inside a session context manager | A custom Python agent loop, no host process watching it |
| **Raw API** (`check_before_tool_call()` / `record_tool_call()` / `record_blocked_attempt()`) | You call each step yourself | Full manual control — e.g. the call site isn't a simple function call, or you need custom recording logic |

All three modes share one property that matters for what follows: **nothing is durable unless something
explicitly writes it down.** `check_before_tool_call()` is a pure decision function — SPEC-030's design
choice — it never records anything itself, by design (so speculative/probe calls don't pollute the audit
trail). Recording is always a separate, explicit step.

### Mode 2 in full

```python
from agent_evaluator.gates.live_guardrail import (
    LiveGuardrail, tool_guard, live_guardrail_session, GuardrailBlockedError,
    ScopeConfig,
)

guardrail = LiveGuardrail(scope=ScopeConfig(forbidden_tools=["webfetch"], fail_on_violation=True))

@tool_guard()
def bash(command: str) -> str:
    return run_shell(command)

with live_guardrail_session(guardrail, task_id="session-1"):
    try:
        bash("rm -rf /")
    except GuardrailBlockedError as e:
        print(f"blocked (Gate {e.verdict.gate}): {e.verdict.reason}")
```

`tool_guard()` wraps the check → execute → record cycle around any function; `live_guardrail_session()`
is a `contextvars`-based context manager so `tool_guard`-decorated calls inside the `with` block
automatically find the active `guardrail`/`task_id` without threading them through every call.

### Mode 3 in full

```python
verdict = guardrail.check_before_tool_call(task_id, "bash", {"command": "rm -rf /"})
if verdict.block:
    entry = guardrail.record_blocked_attempt(task_id, "bash", verdict, tool_input={"command": "rm -rf /"})
    raise GuardrailBlockedError(verdict)
result = run_shell(...)
guardrail.record_tool_call(task_id, "bash", {"command": "..."}, {"success": True})
```

## Core API

| Method | Purpose |
|--------|---------|
| `check_before_tool_call(task_id, tool_name, parameters) -> LiveVerdict` | Pure decision — `block: bool`, `gate: "B"\|"E"\|None`, `reason: str\|None`. Never records anything. |
| `record_tool_call(task_id, tool_name, parameters, output=None)` | Records a call that was allowed and actually executed. Feeds Gate B/E's live judgment state and (via `to_task_extra()`) Gate G's tool-call log. |
| `record_blocked_attempt(task_id, tool_name, verdict, *, tool_input=None, arg_excerpt=None, arg_sha256=None)` | Explicit opt-in audit record for a blocked call. Completely separate from `record_tool_call()` — never affects Gate B/E scoring (see [Why blocked attempts never move Gate scores](#why-blocked-attempts-never-move-gate-scores)). |
| `snapshot()` / `to_task_extra()` | The current session's Gate B/E judgment as a dict, in the shape `TaskResult.extra` expects — the bridge into a normal batch `PerformanceMonitor.record_task()` call. Always includes `tool_calls` and `blocked_attempts` (empty lists if none). |
| `refresh_team_claims()` | Re-reads `.aoo/claims.jsonl` mid-session (team-concurrency scope checks). |

`tool_guard(tool_name=None, *, audit_blocked=True, fail_closed=False, capture_output=None, fault_injection=None)` —
decorator; `live_guardrail_session(guardrail, task_id, *, audit_log_path=None)` — context manager. Both
in `agent_evaluator.gates.live_guardrail`.

### Why blocked attempts never move Gate scores

`record_blocked_attempt()`'s list (`self._blocked_attempts`) is entirely separate from the list Gate B/E
scoring reads (`self._tool_calls`) — a blocked call, by definition, never executed, so it cannot be scored
as a tool-use outcome. This is deliberate and has a real consequence you should know about: **a session
can show all-green Gate B/E scores while still having had a call blocked** — the score genuinely doesn't
know. Section [Discovery & Durability Hardening](#discovery--durability-hardening-v110) below is the
answer to "then how would anyone find out."

## Discovery & Durability Hardening (v1.1.0)

Claude Code and OpenCode's own host bridges already give you two things for free: a host process that
calls `record_blocked_attempt()` for every block (so an audit row always exists), and a visible in-host
message the moment it happens. **Mode 2/3 (a bare Python agent loop with no host) have neither by
default** — before 1.1.0, `tool_guard()`'s `audit_blocked` defaulted to `False`, so a blocked call left
literally no trace anywhere unless the calling code went out of its way to record one. A silent
`except GuardrailBlockedError: pass` made the block disappear completely.

v1.1.0 closes this with four independent layers — each one assumes the layer above it failed (the
calling agent's own error handling is silent, or there's no host at all), so they don't depend on each
other:

### 1 — Recording is on by default now

`tool_guard(audit_blocked=True)` is now the default (was `False`). The cost of always recording is close
to zero — `record_blocked_attempt()` is an in-memory list append plus a short PII-redacted excerpt
computation, no file or network I/O — so there was no real trade-off in leaving it off. As of 1.1.0, the
same call also passes `tool_input` through, so the audit entry carries a captured `arg_excerpt` the way
the Claude Code / OpenCode host bridges already did (previously `tool_guard`'s own recording call omitted
it, so even an explicitly-audited block had no excerpt).

```python
@tool_guard()  # audit_blocked=True by default since 1.1.0 — no need to pass it explicitly
def bash(command: str) -> str: ...
```

### 2 — Durable even if the session crashes

`live_guardrail_session(guardrail, task_id, audit_log_path=...)` flushes any `blocked_attempts` recorded
during that `with` block to an append-only JSON Lines file **on exit — success or exception** (`finally`).
This is the host-less equivalent of what the Claude Code hook's `SessionEnd` / OpenCode's
`session.idle` do automatically: a durable record even when the calling code's own exception handling
around `GuardrailBlockedError` is completely silent.

```python
with live_guardrail_session(
    guardrail, task_id="session-1",
    audit_log_path=".agent-evaluator/sessions/session-1.blocked.json",
):
    ...  # your agent loop — its error handling can be sloppy, this still gets written
```

Re-entering the same `guardrail` in a second `with` block only flushes entries recorded *during that
block* (an internal length watermark) — nothing is duplicated across sessions sharing one instance. The
write is best-effort and never raises: a broken path or a permissions error is swallowed, matching
`LiveGuardrail`'s fail-open policy everywhere else.

### 3 — An out-of-band signal independent of the agent process

`LiveGuardrail(on_block=...)` fires a callback the instant a block is recorded — **on a daemon background
thread, with every exception from the callback swallowed**. This is the layer that doesn't even trust the
calling process to still be running by the time anyone looks — a webhook lands in Slack/ops regardless of
what the agent code does next.

```python
from agent_evaluator.gates.live_guardrail import LiveGuardrail, webhook_on_block

guardrail = LiveGuardrail(
    ...,
    on_block=webhook_on_block(os.environ["SLACK_WEBHOOK_URL"], timeout=3.0),
)
```

`webhook_on_block(url, *, headers=None, timeout=3.0)` is a small convenience factory — POSTs the
blocked-attempt payload (`tool_name`, `gate`, `reason`, `task_id`, and `arg_excerpt` if captured) as JSON.
Pass any other callable for a custom sink (a queue, a different alerting channel, a log line) — the
same background-thread + exception-swallow wrapper (`_dispatch_on_block`) applies uniformly no matter
what the callback does, so a slow or broken endpoint never adds latency to, or crashes, the blocked
call's caller.

> **This is a different mechanism from the `AGENT_EVALUATOR_ALERT_WEBHOOK_URL` Slack alert** already
> documented in [`08_AOO_STACK.md`](08_AOO_STACK.md#blocked-attempt-slack-alerts-opt-in). That one is
> session-end, aggregated (one message per session), and shared by both host bridges — it fires only if
> `record_and_save()` actually runs. `on_block` fires per-block, immediately, from inside `LiveGuardrail`
> itself, independent of whether *any* session-end code ever executes — the layer for when there's no
> bridge at all.

### 4 — Finding out without already knowing what to look for

Even with 1–3 in place, someone still has to go look. Before 1.1.0, every lookup path
(`search_violations()`, `agent-eval {claude,opencode} violations "<query>"`) required a keyword you
already suspected — there was no "just show me what's there" mode. Passing a wildcard-style query
(`"*"`, `""`) did not work either — FTS5 has no "match everything," so those silently return nothing.

- **`list_violations()`** (`agent_evaluator.storage.sqlite_backend`) — a plain `SELECT … ORDER BY
  timestamp DESC`, no `MATCH` at all. `since` / `gate` / `tool_name` / `limit` to narrow.
- **CLI**: `agent-eval {claude,opencode} violations` with **no query** now browses recent history
  (`--since`, `--gate`); passing a query still does the original keyword search — fully backward
  compatible.
- **MCP**: a new `list_violations(limit=20, since=None, gate=None)` tool sits alongside
  `search_violations`/`show_violation` as the keyword-free entry point in the three-step discovery chain
  (`list_violations` → `search_violations` → `show_violation`).
- **`agent-eval {claude,opencode} doctor`** now proactively reports the audit DB's row count and most
  recent timestamp (a `violation/blocked-attempt audit` check) — you don't have to already suspect
  something was blocked to find out; `doctor` tells you.
- **The HTML report** (`insights.blocked_attempts_audit`, [`13_OUTPUTS.md`](13_OUTPUTS.md) §"Blocked
  Attempts") surfaces `extra.blocked_attempts` directly in the report a `PerformanceMonitor` run already
  produces — an above-the-fold banner (`⚠ N tool call(s) blocked this run`) plus a full section in the
  Governance evidence group, auto-opened. This works identically whether the tasks came from a
  live-guardrail host bridge (`SessionEnd`) **or** a plain batch `@agent_eval` run whose tool code used
  `tool_guard()` + `EvalMetadata(extra=guardrail.to_task_extra())` — the report code never special-cases
  the origin. It is passive discovery, not a new lookup you have to run: if you already open the report
  to check Gate scores, the blocked-attempt signal is right there even though it never affects those
  scores.

## Config reference — `blocked_attempt_capture`

Passed to `LiveGuardrail(blocked_attempt_capture={...})` (or the equivalent key in
`guardrail_config.json` / `agent-evaluator.config.json` for the host bridges).

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `True` | Off restores the pre-SPEC-041 shape (`tool_name`/`gate`/`reason` only, no excerpt). |
| `max_chars` | `500` (was `240` before 1.1.0) | The capture/display budget the CLI list/search views and MCP tools show. |
| `report_max_chars` | opt-in; omitted = equals `max_chars` | (1.1.0) A separate, longer ceiling reserved for the HTML report and `blocked-detail`/`show_violation` deep-dive. Capture always stores at the **larger** of the two — a narrowed `max_chars` you set explicitly is never silently widened just because a default `report_max_chars` exists. |
| `redact_pii` | `True` | Best-effort PII redaction on the captured excerpt before storage. |

Capture happens once, at block time, at the larger ceiling; each output surface (CLI/MCP list-and-search
vs. the HTML report vs. `blocked-detail`) trims its own copy down for display —
`agent_evaluator.integrations._blocked_detail.truncate_excerpt()` is the shared helper for the
scannable-list case. The report and `blocked-detail`/`show_violation` show the full captured value.

## Related docs

- [`07_CLAUDE_CODE_HOOKS.md`](07_CLAUDE_CODE_HOOKS.md) — the Claude Code CLI hook integration (host-integrated
  mode).
- [`08_AOO_STACK.md`](08_AOO_STACK.md) — the OpenCode + Ollama integration (host-integrated mode), plus the
  session-end Slack alert, team scope claims, and `search_violations`/`recommend_fix`/`ask_insights` MCP
  servers.
- [`09_OPENCODE_VS_CLAUDE_CODE.md`](09_OPENCODE_VS_CLAUDE_CODE.md) — side-by-side comparison of the two host
  integrations.
- [`15_CTX_SESSION_SEARCH.md`](15_CTX_SESSION_SEARCH.md) — where `ctx` (optional, personal session search) fits
  relative to `search_violations`/`list_violations` for a blocked command specifically.
- [`13_OUTPUTS.md`](13_OUTPUTS.md) — the full output-surface map, including `insights.blocked_attempts_audit`
  and the MCP tool table.
- `Docs/specs/SPEC-019-live-guardrail-api.md` — original `LiveGuardrail` design.
- `Docs/specs/SPEC-030-blocked-attempt-audit-trail.md` — the `record_blocked_attempt()` /
  `blocked_violations` audit-trail design this document builds on.
- `Docs/specs/SPEC-039-decorator-architecture-fixes.md` — `tool_guard`/`live_guardrail_session()` design.
- `agent_evaluator/gates/live_guardrail.py` — the implementation (SPEC-019, hardened through SPEC-045).
