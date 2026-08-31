# ctx session search — an optional personal workflow (no Agent-Evaluator dependency)

`ctx` (https://github.com/ctxrs/ctx) is a separate open-source CLI that indexes and searches, locally,
the past sessions of several coding-agent tools (Claude Code, OpenCode, etc.). None of Agent-Evaluator's
Gate scoring, LiveGuardrail, RCA (`diagnose`), or A/B (`abtest`) depends on ctx — this document records
**3 personal helper workflows that a human pivots to manually, only when needed**, for those four features.

> **Scope**: real-time (in-session) context enrichment was reviewed and rejected — see
> [What this does not do](#what-this-does-not-do-out-of-scope--with-reasons). What remains here is 3
> cross-session, retrospective investigation uses only.

---

## Pre-verified facts (measured in this project, as of 2026-08-26)

- ctx already indexes this project's Claude Code sessions (source `~/.claude/projects`, provider
  `claude`) — 211 sessions / 108,301 events per this environment's `ctx status`.
- **Note this is a different provider from the constraint already live-verified in
  [AOO_STACK.md's "ctx self-correction feedback loop" section](AOO_STACK.md#ctx-self-correction-feedback-loop)**:
  that section found that ctx's (v0.19.0) **OpenCode** importer pulls only session **metadata (title,
  token count)** and not the actual message / tool_call content (which is why `search_violations` fills
  that gap). Querying this project's local index (`~/.ctx/work.sqlite`) directly via SQL to write this
  document showed that **the Claude Code importer is different** — `tool_call` / `message` events
  contain the actual command text and conversation transcript (not just metadata).
- Still, **not everything is stored in full** — the `content_retention` value varies per event:
  - `message` (conversation transcript): roughly half is retained in full as `full_text`, the rest untagged.
  - `tool_call` (executed command): a command preview is present, but there is no `full_text` label at all (there is a length cap).
  - `tool_output` (stdout/stderr result): no `full_text` at all — `metadata_only` / a preview on failure only.
  - **Conclusion**: usable to search for and confirm "which prompt / command wrote this code," but
    **do not expect to reconstruct a tool's full stdout via ctx** — if you need that, use
    Agent-Evaluator's own `record_tool_call(output=...)` / `search_violations` (SPEC-031/024).
  - This result can change if the ctx version / config changes — do not trust it as is without re-verifying.

## Prerequisites

- ctx CLI/MCP must already be installed and indexed (check with `ctx status`). If not installed, see
  https://github.com/ctxrs/ctx — **it is not a pip-install target of Agent-Evaluator** (it is not
  included in any `pip install agent-evaluator[...]` extra).
- If ctx is connected as an MCP server inside a Claude Code session, you can request its
  `search` / `show_event` / `show_session` / `sources` / `sql` / `status` tools directly in the
  conversation. To use the CLI directly: `ctx search` / `ctx show session` / `ctx blame`.

---

## Workflow A — Gate regression → git commit → source-session trace-back

For when `agent-eval diagnose` has named a candidate regression cause and you want to see the actual
conversation — "who actually wrote that code, and with what reasoning."

1. Run `agent-eval diagnose results/latest.json --baseline results/baseline.json --show-diff` to see
   the candidate regression cause and the related git commit.
   ([05_QUALITY_GATE.md §8](05_QUALITY_GATE.md#8-gate-regression-root-cause-diagnosis-agent-eval-diagnose))
2. Narrow down the files/lines the named commit touched with `git show <commit> --stat`.
3. Find the session that wrote those lines with `ctx blame file <path> --lines <start:end>` (or the
   same query via the ctx MCP tool inside a Claude Code session).
4. Read the actual conversation of that session with `ctx show session <id>` — per the constraint
   above, don't expect a tool's full stdout; use it to confirm which prompt / reasoning (message text)
   wrote that code.
5. This whole process is a **retrospective investigation a human runs manually**. `diagnose` does not
   call ctx automatically — the HOTL principle and the "external-dependency-free core" principle stand.

Because `agent_version="auto"` auto-tags the git commit SHA at session-run time, a session instrumented
with Agent-Evaluator already has the commit info inside the `diagnose` result — the only point ctx is
needed is tracing back "who wrote that commit, in which conversation."

---

## Workflow B — Mining golden-set raw material (from uninstrumented past sessions)

`agent-eval dataset build --source results/` (`GoldenSetBuilder`) only sees sessions already
instrumented with `PerformanceMonitor`. For when you want to find good/bad cases in an ordinary Claude
Code conversation that ran without `@agent_eval`.

1. Explore candidate sessions with `ctx search "<keyword>"` (or the ctx MCP `search` tool inside a
   Claude Code session).
2. Open a candidate session with `ctx show session <id>` and have a human confirm/excerpt the
   question / answer / context.
3. Add the excerpt as an entry to `data/golden_datasets/*.json` **by hand**, matching the
   [QAPair structure in 04_DATA_GUIDE.md](04_DATA_GUIDE.md#2-qapair-structure)
   (`qa_id` / `question` / `answer` / `context` / `ground_truth` / `metadata`). There is no link that
   feeds ctx results automatically into the `GoldenSetBuilder` pipeline — none was built, and none is
   currently planned.
4. From there, follow the existing pipeline as is. On the same principle as
   `GoldenSetBuilder.extract(require_human_review=True)` being the default, a candidate mined via ctx
   must also go through human review before it is confirmed.

---

## Workflow C — Finding A/B comparison candidates

`agent-eval abtest` only compares two result JSONs already in `results/` statistically — it does not
find "two runs worth comparing" for you.

1. Use `ctx search` to find candidate pairs of sessions that repeated the same task at a different
   time / with a different setup.
2. Have a human confirm the two sessions are actually comparable (same task, different prompt/setup).
3. Once confirmed, either re-instrument the two runs properly via `@agent_eval` / `PerformanceMonitor`
   with different `prompt_version` / `agent_version`, or — if a result JSON already exists — verify
   statistically with `agent-eval abtest v1.json v2.json --metric accuracy_score`.

---

## What this does not do (out of scope — with reasons)

- **Real-time hook context enrichment (immediate RCA lookup, context right after a LiveGuardrail
  block)** — reviewed and rejected. Claude Code's official docs state that the hook-time
  `transcript_path` "may be missing the latest turn, so mid-turn references are not recommended," and
  ctx is an offline tool that only indexes after a session ends, so it can't be used inside a real-time
  hook anyway. Real-time block context is considered sufficiently covered by the
  `{tool_name, gate, reason, detail}` that `LiveGuardrail` already records.
- **Adding ctx as a dependency of the Agent-Evaluator core** — conflicts with the "layer independence /
  external-dependency-free core" principle. All 3 workflows documented here are personal-tool workflows
  a human pivots to manually, and no Agent-Evaluator code calls ctx.
- **Auto-wiring ctx results into the pipeline** (auto-extending `diagnose --show-diff`, auto-adding a
  `GoldenSetBuilder` source, etc.) — no code change. The justification was judged still insufficient
  (revisit if it becomes necessary).

---

| Goal | Document |
|------|----------|
| Gate-regression root-cause diagnosis | [05_QUALITY_GATE.md §8](05_QUALITY_GATE.md#8-gate-regression-root-cause-diagnosis-agent-eval-diagnose) |
| Golden-dataset structure | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| Statistical A/B testing | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
| The existing live verification of the OpenCode LiveGuardrail + ctx feedback loop | [AOO_STACK.md](AOO_STACK.md#ctx-self-correction-feedback-loop) |
