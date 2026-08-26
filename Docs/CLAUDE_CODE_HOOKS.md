# Claude Code CLI Hooks — Real-Time LiveGuardrail

`agent-eval claude install` wires the same `LiveGuardrail` engine used by the
[OpenCode integration](AOO_STACK.md) into [Claude Code](https://claude.com/claude-code) CLI's own
`PreToolUse`/`PostToolUse`/`SessionEnd` hooks — a tool call gets checked *before* it executes (real-time
Gate B/E), and the whole session folds into the normal batch Gate A–G pipeline once it ends.

No new detection logic is involved — exactly the same Behavioral Integrity (loop detection, scope,
tool-parameter safety) and Security Boundary evaluators that power Gates B/E in batch mode, called
synchronously per tool call instead.

> **Status**: implemented and covered by 40 unit/integration tests (`tests/test_claude_code_hook.py`,
> `tests/test_cli_claude.py`) exercising the full install → block → record → batch-save flow against
> crafted hook payloads. Unlike [AOO_STACK.md](AOO_STACK.md)'s OpenCode integration, this has **not**
> been live-verified against a real, running Claude Code session yet — treat the
> [known limitations](#known-limitations) below as unconfirmed-in-the-wild until it has been.

## Why a per-invocation replay, not a resident process

OpenCode's plugin can hold one long-lived Python subprocess open for an entire session
(`live_guardrail_stdio.py`, a request/response loop over stdin/stdout). Claude Code's hook model is
different: each `PreToolUse`/`PostToolUse`/`SessionEnd` firing spawns a **separate OS process** with no
shared memory — confirmed against Claude Code's own hook documentation, not assumed.

So a resident-process bridge doesn't fit here. Instead, each hook invocation:

1. Reads the session's confirmed tool-call history back from a small JSON file.
2. Builds a fresh `LiveGuardrail` and replays that history through `record_tool_call()` (a normal public
   method — `LiveGuardrail` itself has no new code for this) to reconstruct its judgment state.
3. Runs the actual check/record for *this* call.
4. Writes the updated history back to the file.

```
Claude Code CLI                                   Python (spawned fresh per hook call)
┌──────────────────────┐  stdin (one JSON obj)  ┌────────────────────────────────────────┐
│ PreToolUse hook       │───────────────────────►│ claude_code_hook.py                    │
│  (Bash|Edit|Write)    │◄───────────────────────│  replay history → check_before_tool_call│
└──────────────────────┘  stdout (allow/deny)    │  → gates/live_guardrail.py (SPEC-019)   │
┌──────────────────────┐                         └────────────────────────────────────────┘
│ PostToolUse hook      │───────────────────────► same module → record_tool_call(), appends
│  (Bash|Edit|Write)    │                          the confirmed call to the session state file
└──────────────────────┘
┌──────────────────────┐                         ┌────────────────────────────────────────┐
│ SessionEnd hook       │───────────────────────►│ same module → replay full history →     │
│  (matcher "*")        │                         │  live_guardrail_report.record_and_save()│
└──────────────────────┘                          │  (identical batch bridge OpenCode uses) │
                                                   └────────────────────────────────────────┘
```

State lives under the project (or `~/.claude/` with `--global`):

```
.claude/.agent-evaluator/
├── guardrail_config.json               # your edited copy of the LiveGuardrail config
└── sessions/
    ├── <session_id>.json               # confirmed tool_call history (deleted at SessionEnd)
    └── <session_id>.blocked.json       # blocked-attempt audit trail (deleted at SessionEnd)
```

**`SessionEnd`'s matcher is not a tool-name matcher** — it filters by session-end *reason*
(`clear`/`logout`/`prompt_input_exit`/...), unlike `PreToolUse`/`PostToolUse` which filter by tool name.
`agent-eval claude install` registers `PreToolUse`/`PostToolUse` with `"Bash|Edit|Write"` and
`SessionEnd` with `"*"` (match all reasons) — reusing the tool-name matcher for `SessionEnd` would mean
the batch-save hook silently never fires. This was actually caught by running the install → hook flow
end-to-end during development, not by reading the docs alone, and has a regression test
(`test_all_three_events_registered_with_correct_matchers`).

## Setup

```bash
pip install agent-evaluator   # or from a repo checkout: pip install -e .

agent-eval claude install                              # .claude/settings.json (project-local, default)
# or: agent-eval claude install --global                # ~/.claude/settings.json
# or: agent-eval claude install --force                 # reset guardrail_config.json to defaults
# or: agent-eval claude install --with-violation-search  # + register the search_violations MCP server
# or: agent-eval claude install --with-recommend-fix      # + register the recommend_fix MCP server
```

`agent-eval claude install` **merges** into `.claude/settings.json` rather than overwriting it — if you
already have other hooks registered there, they're preserved. Re-running install doesn't duplicate hook
entries. This is a real difference from the OpenCode installer (a simple file copy): Claude Code's
`settings.json` is a shared file a user may already be customizing, so a blind overwrite would be
destructive.

Unlike the OpenCode plugin, no file needs to be copied for the hook script itself — Claude Code just
shells out to the installed package (`python -m agent_evaluator.integrations.claude_code_hook`) directly,
with the current interpreter's absolute path baked into `settings.json`. The only file `install` writes
that you're expected to edit is `guardrail_config.json`.

## Default guardrail config

```json
{
  "loop_detection": {"consecutive_repeat_threshold": 6, "on_loop_detected": "fail"},
  "scope": {"forbidden_tools": ["WebFetch"], "fail_on_violation": true},
  "tool_parameter_safety": {
    "dangerous_patterns": ["\\.\\./", "&&", "\\|\\|", ";.*rm\\s", "\\brm\\s+\\S", "__import__", "eval\\(", "exec\\("],
    "scope_tool_names": ["Bash"],
    "fail_on_dangerous": true
  },
  "output_dir": "results/claude_code_live_guardrail"
}
```

Same principle as the OpenCode plugin's `GUARDRAIL_CONFIG` (`consecutive_repeat_threshold: 6` because
loop detection compares tool *names* only — see [AOO_STACK.md](AOO_STACK.md) for the false-positive story
that motivated the SDK-wide default), adapted to Claude Code's own tool naming (`"Bash"`, not the
lowercase `"bash"` OpenCode uses). `output_dir` isn't a `LiveGuardrail` constructor argument — it's read
by the hook bridge itself and popped before building the guardrail.

Edit the installed copy at `.claude/.agent-evaluator/guardrail_config.json`, not the package default —
`agent-eval claude install --force` resets it and discards your edits. The keys accepted are whatever
`live_guardrail_stdio.build_guardrail()` understands: `loop_detection`, `deadlock`, `scope`,
`tool_parameter_safety` (Gate B configs), plus `tool_authorization`, `privilege_escalation`,
`tool_chain_attack` (Gate E tracker constructor kwargs).

## Known limitations

- **No `team_concurrency`/`branch_guard` support yet.** These are `LiveGuardrail` constructor arguments,
  but `live_guardrail_stdio.build_guardrail()` — reused here rather than duplicated — doesn't handle
  them. Using `LiveGuardrail` directly in Python (see the `tool_guard`/`live_guardrail_session()` example
  in [AOO_STACK.md](AOO_STACK.md#why-a-subprocess-bridge)) is the only way to get those checks today.
- **Per-call history replay cost grows with session length.** Every `PreToolUse`/`PostToolUse` call
  replays the *entire* confirmed history for that session through `record_tool_call()` before doing its
  own check — so total replay work across an *n*-call session is O(n²). This hasn't been benchmarked
  against a real long Claude Code session; for the tool-call counts a single coding session typically
  produces (tens, not thousands) it's expected to be a non-issue, but it isn't a validated claim.
- **No cleanup on abnormal termination.** `SessionEnd` is the only place session state files get deleted.
  If Claude Code is killed hard (`kill -9`, crash) mid-session, `.claude/.agent-evaluator/sessions/
  <session_id>.json` and `.blocked.json` are left behind — harmless (they're just replay input for a
  `session_id` that won't return), but they won't self-clean. Delete `.claude/.agent-evaluator/sessions/`
  manually if this matters to you.
- **Exceptions fail open, not closed.** A bug in the hook bridge itself returns "no decision" (allow)
  rather than blocking every subsequent tool call — deliberate, matching `tool_guard(fail_closed=False)`'s
  default elsewhere in this SDK, but means a broken bridge degrades to "no real-time guardrail" silently
  rather than loudly.
- **Not yet live-verified end-to-end against a real Claude Code session** (see the status note above) —
  only against crafted hook payloads in tests and a manual temp-directory run during development.

## Related docs

- [`AOO_STACK.md`](AOO_STACK.md) — the OpenCode integration this reuses the same `LiveGuardrail` engine
  from; also documents the `tool_guard`/`live_guardrail_session()` in-process pattern, team scope claims,
  branch guard, and the `search_violations`/`recommend_fix` MCP servers registered by `--with-*` flags
  here too.
- `agent_evaluator/gates/live_guardrail.py` — the actual Gate B/E judgment logic (SPEC-019).
- `agent_evaluator/integrations/claude_code_hook.py` — this bridge's implementation.
- `agent_evaluator/integrations/live_guardrail_stdio.py` — `build_guardrail()`, reused here to construct
  `LiveGuardrail` from the same JSON config shape as the OpenCode stdio bridge.
- `agent_evaluator/integrations/live_guardrail_report.py` — `record_and_save()`, reused here for the
  `SessionEnd` batch save.
