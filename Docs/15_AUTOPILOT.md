# Harness Autopilot — HITL approval queue & task governance

`agent-eval autopilot` is an optional governance layer built on top of this SDK's own evaluation data —
Gate scores, the `agent-eval gate` decision log, and team scope claims. It gives a team a lightweight
multi-task/multi-team registry, a human-in-the-loop (HITL) approval queue, and an optional phase gate
that can require a human sign-off, a passing Harness Gate verdict, or both, before a task moves to its
next lifecycle phase.

It is **not** a software-delivery methodology, a spec-authoring tool, or a replacement for your
project-management system — it's a thin, file-based layer that connects data this SDK already produces
to a team's own approval process. Everything lives in a project-local `.aoo/` directory (plain
JSON/JSONL files, no database server) and is entirely opt-in — nothing else in the SDK depends on it.

A local dashboard (`agent-eval autopilot dashboard`, port 8766) gives every command below a
browser-based equivalent, so a non-CLI teammate (a PM, a reviewer) can use the approval queue and task
board without touching a terminal.

---

## Install

```bash
agent-eval autopilot install --platform ac    # Claude Code project — or --platform aoo for OpenCode
```

This creates `.aoo/tasks/`, `.aoo/team.json`, and places the companion Skills the install wires up.

```bash
agent-eval autopilot doctor                # health-check the .aoo/ skeleton
agent-eval autopilot doctor --stale-days 7  # also flag an active task stuck in its current phase
```

`doctor` (and the read-only `agent-eval autopilot phase check`) is the only signal that a task's
*declared* phase may have silently fallen behind the actual work — a task with no phase transition in
`--stale-days` days gets flagged.

---

## Task & team registry

A **task** (`.aoo/tasks/<id>.json`) tracks a unit of work through up to 6 owner roles (analysis,
design, development, QA, PM, security) and a lifecycle phase; a **team member** (`.aoo/team.json`)
is a person who can be assigned to one.

```bash
agent-eval autopilot new-task --title "Add RAG citations" --platform ac \
    --analysis alice --development bob

agent-eval autopilot add-member --id alice --name Alice --role analysis

agent-eval autopilot list-tasks              # active tasks only by default; --all also shows archived/cancelled
agent-eval autopilot show-task ST-001        # owners + full phase history
agent-eval autopilot update-task ST-001 --priority high --development carol --by alice
agent-eval autopilot set-task-status ST-001 --status archived --reason "shipped" --by alice

agent-eval autopilot list-members
agent-eval autopilot update-member --id alice --role design --by bob
agent-eval autopilot remove-member --id alice
```

`update-task` / `set-task-status` / `update-member` each accept an optional `--by NAME` to record who
made the change, and an optional expected-timestamp check (used by the dashboard's edit forms) so two
people editing the same record at once can't silently overwrite each other.

---

## The HITL approval queue

An **approval** (`.aoo/approvals.jsonl`) is a reviewable request tied to a task and a phase — for
example, "does this spec pass an EARS-notation review before design starts?" Each approval carries a
checklist; a request only becomes reviewable once every checklist item is `ok`, `pending`, or `flag`
and none carries a `[NEEDS CLARIFICATION: ...]` tag.

```bash
agent-eval autopilot approvals open --task ST-001 --kind spec_review --phase 1 \
    --title "Spec review" --body-file docs/SPEC.md \
    --checklist-item "EARS notation:ok" --checklist-item "Edge cases covered:pending"

agent-eval autopilot approvals list                       # pending only by default
agent-eval autopilot approvals decide ap-a1b2c3d4 --decision approved --by reviewer-1
agent-eval autopilot approvals update ap-a1b2c3d4 --checklist-item "Edge cases covered:ok"
agent-eval autopilot approvals cancel ap-a1b2c3d4 --reason "no longer needed"
```

High-stakes kinds (`deploy`, `release_hold`) default to **`required_approvals=2`** — dual sign-off by
two distinct people — and `approvals open --required-approvals N` can escalate any other kind for a
single request. An approval, once `approved`/`rejected`, is immutable.

### A recurring gate-failure becomes a review automatically

```bash
agent-eval autopilot approvals scan-thresholds
```

If `agent-eval gate --hold-on-undecided` has produced the same "hold for human" reason 5+ times in
`.aoo/decisions.jsonl`, this opens a `threshold_review` approval instead of letting the same signal keep
being ignored. It's idempotent — running it again doesn't duplicate an already-open card.

---

## Phase gates

A task's `current_phase` normally advances freely:

```bash
agent-eval autopilot phase transition --task ST-001 --to 2
```

Two independent, opt-in checks can be attached to any transition:

```bash
# Refuse the transition unless an approval of this kind is approved for the task
agent-eval autopilot phase transition --task ST-001 --to 2 --require-approval spec_review

# Refuse the transition unless the most recent `agent-eval gate --decision-log` run for this
# project is verdict_level == "ready" (or a human explicitly accepted/overrode it)
agent-eval autopilot phase transition --task ST-001 --to 8 --require-gate-ready yes
```

`--require-gate-ready` is the one that ties Autopilot directly to this SDK's own judgment: without it,
a task could reach a "deployed" phase even while the last recorded Gate run says `not_ready`. A human's
explicit `accepted`/`overridden` decision in the ledger always outranks the automated verdict, in either
direction.

Remembering to pass these flags on every transition is easy to forget, so declare them once per phase
instead:

```bash
agent-eval autopilot phase policy set --to 2 --require-approval spec_review
agent-eval autopilot phase policy set --to 8 --require-gate-ready
agent-eval autopilot phase policy show
```

A transition also warns (never blocks) on going backward or skipping a phase — useful for catching an
accidental regression without hard-blocking a deliberate rollback.

---

## Deploy decisions and team scope claims

Autopilot's dashboard and CLI both surface two pieces of state that come from elsewhere in the SDK
rather than from Autopilot itself:

- **The deploy-decision ledger** (`agent-eval decisions list|record`, also reachable as
  `agent-eval autopilot decisions ...`) — who accepted, held, overrode, or rejected a given
  `agent-eval gate --decision-log` run, and why. See
  [`05_QUALITY_GATE.md` §9](05_QUALITY_GATE.md#9-defining-slos-and-the-closed-improvement-loop).
- **Team scope claims** (`agent-eval claims add|list|release|audit`) — which developer is currently
  working in which part of the codebase, to catch two people stepping on the same files. See the
  "Team scope claims" section of [`08_AOO_STACK.md`](08_AOO_STACK.md).

Both have full read/write parity on the Autopilot dashboard's ops page, in addition to their own CLI
commands.

---

## Skill candidate detection

If the same approval-checklist shape keeps recurring across different tasks, that's usually a sign the
underlying review procedure should be written down as a reusable Skill instead of re-typed by hand each
time.

```bash
agent-eval autopilot skills detect                                   # read-only — lists repeated shapes
agent-eval autopilot skills scaffold --name spec-review-checklist    # writes a starter Skills/<name>/SKILL.md
```

`scaffold` writes a skeleton with `TODO` markers for the description and per-step procedure — it is a
starting point for a human to finish, never a finished Skill on its own.

---

## The dashboard

```bash
agent-eval autopilot dashboard   # http://localhost:8766
```

Server-rendered, no JavaScript build step. Four views:

| View | What it's for |
|------|---------------|
| Task board | Create/edit/archive a task, see phase + owners at a glance, a "stuck in phase" badge |
| Team | Add/edit/remove a team member |
| Approvals | Open/decide/update/cancel an approval, run the recurring-failure scan |
| Ops | Team scope claims, deploy-decision ledger, phase policy, rejection-rate self-check, open improvement experiments |

Every CLI action documented above has a corresponding form on one of these four pages — the dashboard
and the CLI operate on the exact same `.aoo/` files, so either one can be used interchangeably at any
point.

### A self-check against rubber-stamping

The ops page tracks the rolling approval rejection rate and flags a warning once 5+ decisions have a 0%
rejection rate — a cheap signal that review may have become a formality rather than a real check.

---

## Related docs

- [`05_QUALITY_GATE.md`](05_QUALITY_GATE.md) — `agent-eval gate`, the decision ledger, targets/SLOs,
  and the closed improvement loop that Autopilot's phase gate reads from.
- [`08_AOO_STACK.md`](08_AOO_STACK.md) — team scope claims in more depth, and the wider local-first
  (Ollama + OpenCode) stack Autopilot is often used alongside.
- [`14_API_REFERENCE.md` §15](14_API_REFERENCE.md#15-cli-reference) — the full CLI command list.
