# Changelog

## v1.0.0 (2026-08-31) — General Availability

First GA release. Public SDK API is `1.0.0-rc4` unchanged — the delta is the completion of
SPEC-041's insight-delivery layer (`reporting/insights.py::build_insights()` is now a ~62-key
machine-readable hub, every section schema-validated against `agent_evaluator/schemas/insights.schema.json`)
plus two further example-report audit passes. No breaking changes.

- ✨ **User-defined targets / SLOs** (P43) — `.aoo/targets.json` via `agent-eval target set`; `agent-eval gate` and every "below target" line now measure against your per-gate / TCR bar, not a fixed 0.7.
- ✨ **Deploy-call robustness** (P44) — `threshold_sensitivity` flags a knife-edge readiness verdict.
- ✨ **Eval-set intelligence** — gap analysis + prompt-contamination check (P45), metric signal / redundancy (P46), golden-set health (P58), eval-set-vs-production representativeness (P54).
- ✨ **Failure understanding** — claim-level failure explanation (P47) and a single-agent failure taxonomy (P55): 14 modes, each with an owner (prompt / config / data / model / infra) and remediation.
- ✨ **Longitudinal intelligence** (P48) — chronic / flapping / recurring failure tracking across sibling runs.
- ✨ **Closed improvement loop** — `agent-eval improve {plan,start,verify,patch}` (P49, P61); improvement priors synthesized from past experiment outcomes (P57).
- ✨ **Partial / mid-run insights** (P50) — `build_insights(partial=True)`, `PerformanceMonitor.running_insights()` / `.should_early_stop()` for advisory early-stop in an eval loop.
- ✨ **Provenance** (P51) — a `derived_from` on every `next_actions` / `fix_plan` / `recommendations` item.
- ✨ **Judge robustness** (P52) and **external reference frame** (P53) — `.aoo/reference.json`, percentile vs an industry / historical baseline.
- ✨ **Statistical rigor** — multiple-comparison audit (P59: Welch p-values + `likely_noise` flags), uncertainty budget (P60: where the confidence gap comes from and the cheapest lever to close it).
- ✨ **Ablation hints** (P56) — the one prompt line / config knob most implicated in each failure mode.
- ✨ **Within-run contrast pairs** (P62) — each worst failure beside its nearest passing task plus a structured diff isolating the likely differentiator.
- ✨ New CLI: `agent-eval benchmark {set,show,clear}`, `agent-eval dataset health`.
- 🐛 **P35 rounds 4–5** — ~30 cross-section coherence fixes from re-auditing the generated example report: Gate A/C/F score-breakdown reconciliation, narrative claim audit, review-queue severity, flaky-fixed failure lineage, cohort "—" for gates a version never measured, and more.
- 📝 SPEC-041 insight-layer field reference moved to `Docs/specs/SPEC-041-insight-delivery.md`; `insights.schema.json` extended for every new section; `CLAUDE.md` Key Files tree compressed to 1–2 lines per entry.

## v1.0.0-rc4 (2026-08-28) — `doctor` global fallback + hook-docs currency

Follow-up to rc3. No public SDK API changes.

- 🐛 `agent-eval opencode doctor` / `agent-eval claude doctor` (without `--global`) no longer report a hard error when there is no project-local install but a healthy global one exists — OpenCode and Claude Code both auto-load / merge the global location, so `doctor` now checks it and notes "global — no project-local install". `❌` is raised only when neither exists.
- 🔧 `agent-eval opencode install`'s tuning tip corrected — the plugin's `consecutive_repeat_threshold` default is 8 (not 6), and loop identity is tool *name + arguments* (SPEC-041), so only N *identical* calls in a row count.
- 📝 `docs/CLAUDE_CODE_HOOKS.md` / `docs/AOO_STACK.md` / `docs/OPENCODE_VS_CLAUDE_CODE.md` currency pass: stale hook-matcher description, out-of-date default `guardrail_config.json` block, and the pre-SPEC-041 config-in-the-`.ts` guidance were corrected; the new `upgrade`/`doctor`/`uninstall` subcommands were added to the install sections.

## v1.0.0-rc3 (2026-08-28) — Integration Install Lifecycle (upgrade · doctor · uninstall)

`agent-eval claude` and `agent-eval opencode` each gain three subcommands for the LiveGuardrail integration lifecycle, backed by a shared helper module (`agent_evaluator/cli/_integration_health.py`) — pure operational layer, no new judgment logic. No public SDK API changes.

- ✨ **`upgrade`** — edit-preserving refresh after a `pip install -U`. Unlike `install --force`: refreshes stale hook matchers and dead interpreter paths; deep-merges only *new* default keys into `guardrail_config.json` (never overwrites your values, prints the added key paths); re-copies the OpenCode `.ts` only when it's stale and never touches `agent-evaluator.config.json`. `--with-violation-search`/`--with-recommend-fix` re-register those MCP servers (remove + add, refreshing the interpreter path).
- ✨ **`doctor`** — verifies the install actually works, not just that files exist. Static: settings/plugin parse, all 3 hooks registered, matcher current, hook interpreter alive and package importable from it, `guardrail_config` builds via `build_guardrail()` (collects skipped-block warnings), MCP servers registered. Live (in a throwaway sandbox dir, `output_dir` redirected so it's hermetic): runs the *real* registered hook command / stdio bridge with synthetic `PreToolUse`/`PostToolUse`/`SessionEnd` payloads and checks that a benign call is allowed, a destructive command / `WebFetch` is denied (exit 2), and a batch report is written with session state cleaned up. MCP: `initialize` + `tools/list` handshake against each registered server. `--json` (CI), `--no-live`, `--strict`. Exit 1 on any error.
- ✨ **`uninstall`** — reverses `install`: removes only our hook entries from `settings.json` (other hooks untouched), deregisters the MCP servers (`claude mcp remove`; OpenCode has no `mcp remove` subcommand, so it edits `opencode.json`'s `mcp` map directly, leaving `.jsonc` for manual editing), and deletes session state. Keeps `guardrail_config.json` / `agent-evaluator.config.json` unless `--purge`. `--dry-run`, `--yes`. Must be run **before** `pip uninstall agent-evaluator` — the `agent-eval` entrypoint disappears with the package.
- 🔧 `claude mcp add` / `opencode mcp add` — an existing registration is now reported as "nothing to change" instead of a warning plus a manual-command hint.
- 📝 `CLAUDE.md` updated (Common Commands, `cli/` architecture notes, new `cli/_integration_health.py` entry); test-function count 4,090+ → 4,120+ (+45 tests, `tests/test_cli_integration_health.py` new).

## v1.0.0-rc2 (2026-08-27) — Packaging / CI Fixes + LiveGuardrail Bridge Parity

Re-tag of `rc.1` with packaging, CI, and real-time-guardrail bridge fixes found during release validation. No public API changes.

- 🐛 `fix(build)` — pinned `hatchling==1.27.0` so the built wheel keeps `Metadata-Version: 2.4` (newer hatchling emits `2.5`, which some PyPI/pip tooling still rejects).
- 🐛 `fix(ci)` — fixed 3 main-branch CI failures surfaced while triaging PR #10; excluded `serve/templates/*.html.j2` from `coverage.run` (Jinja templates were being counted as uncovered source).
- 🔧 `fix(live_guardrail)` — closed AOO/AC LiveGuardrail bridge parity gaps between the OpenCode plugin and the Claude Code hook path.
- 🔧 `chore(deps)` — `actions/setup-python` 6 → 7.
- 📝 `CLAUDE.md` test-file count corrected (112 → 116).

## v1.0.0-rc.1 (2026-08-27) — Improvement Engine (RCA · Statistical A/B · Recommendations) + Structural Unification

First stable release — `Development Status :: 5 - Production/Stable`. Adds a full diagnosis-and-prescription layer on top of the existing measurement SDK, plus several structural unifications that remove long-standing duplication across Gate judgment paths.

- ✨ **RCA engine** (`agent_evaluator.rca`) — `diagnose()` automates the 3-stage root-cause procedure (detect → attribute → cross-reference) behind a Gate regression; shared-cause check for simultaneous Gate C/D drops; Gate F findings link MAST failure-mode candidates. `verify_recommendation_outcome()` + `record_/load_/summarize_recommendation_outcomes()` close the loop with an append-only JSONL history (`.aoo/claims.jsonl` pattern). New `agent-eval diagnose` CLI and dashboard 🔧 Improve tab expose the same diagnosis. HOTL throughout — candidates and evidence only, never a verdict.
- ✨ **Ontology registry** (`agent_evaluator.ontology`) — `metric_registry.py` consolidates Gate/metric remediation guidance previously duplicated across 3 call sites (HTML report, anomaly explanation, and now `recommend_fix`); `mast_taxonomy.py` seeds Gate F with the MAST 14-failure-mode taxonomy (Cemri et al., NeurIPS 2025).
- ✨ **Statistical A/B testing** — `ab_test()` gained an arbitrary `metric` parameter, Cohen's d effect size, sample-size warnings, and Guardrail Metric (OEC, no implicit `direction` default). New `ab_test_nway()` (N-way pairwise + Benjamini-Hochberg FDR correction) and `ab_test_sequential()` (mSPRT always-valid inference — Monte Carlo–validated at 0.0% empirical false-positive rate vs. 22.0% for naive repeated t-testing under peeking). New `agent-eval abtest` CLI auto-selects two-way / sequential / N-way by file count.
- ✨ **MCP tools** — `recommend_fix` (static Gate/metric remediation lookup, no result file required) registers alongside the existing `search_violations` via `agent-eval opencode install --with-recommend-fix`.
- ✨ `PerformanceMonitor.register_gate()` — plug in independent third-party Gates without forking core aggregation.
- 🔧 **Structural unification** — `gates/base.py::evaluate_gate_scores()` is now the single Gate-threshold-judgment loop shared by `HarnessEvaluationGate.evaluate()`, `QuickEval.gate()`, and `cli/gate.py` (previously three independent implementations of the same loop). `"full"` retention mode (the default) is now genuinely single-pass (45 per-Gate loops → 1) via `_build_full_mode_shared_snapshots()`, with no precision loss.
- 🔧 **Contract hardening** — `schemas/harness_groups.schema.json` formalizes the `extra_metrics.harness_groups` output shape with contract tests; `gates/base.py::_measured()` gives every Gate a consistent "not configured" vs. "configured but no data" vs. "measured" state (fixes a Gate E case that conflated the first two); Config `__post_init__` validation gap closed for the 7 configs that lacked it.
- 🐛 Fixed a real scale bug in `get_comparison()`'s `regression_flags.accuracy_dropped` (0–1 threshold compared against a 0–100 value, so it always tripped); `ab_test()`'s t-test corrected from Student's (equal-variance) to Welch's; Gate B's `gate_b_loop_weight>0` with no loop data now surfaces in `insufficient_data_warnings` instead of silently falling back.
- 🌐 Static HTML report / dashboard / CLI output fully localized to English (previously mixed Korean/English); `LoopDetectionConfig.consecutive_repeat_threshold` default raised 3→6 (loop detection compares tool *names* only, so coarse-tool-granularity agents like OpenCode's single `"bash"` tool were hitting false positives on normal usage — found via live OpenCode+Ollama testing).
- 📝 Removed internal-only references (`SPEC-NNN` ticket IDs, `CLAUDE.md` citations) from all reader-facing docs; new Part VII (Ch28–31) in Media/Book covers the full improvement-engine workflow.
- 📦 Install extras reorganized into 5 intent-based categories (base measurement+diagnosis / SDK / real-time guardrail (`[mcp]`) / your agent's framework / examples+full+dev) in `README.md` and `pyproject.toml`'s comments — no extra names, versions, or package contents changed, purely a documentation/discoverability improvement. Fixed a stale `[mcp]` comment that only mentioned `search_violations` (now also documents `recommend_fix`). `README.md` itself trimmed from 1,421 to a concise, link-out-heavy page; full version history moved to this file.

## v0.9.13 (2026-08-19) — Per-Gate CI Thresholds + Gate D Score Auditability

- ✨ `HarnessEvaluationGate` gained `group_thresholds`/`strict_required` for per-Gate CI thresholds, matching `QuickEval.gate()`/CLI parity; `evaluate()` now returns `threshold`/`not_measured`/`insufficient_data_warnings` per group.
- ✨ `EfficiencyConfig.fallback_reference_cost_per_completion` — configurable Gate D score normalization when `target_cost_per_completion` isn't set.
- ✨ Gate D `details` now exposes `sla_window_penalty`/`sla_budget_penalty`/`perf_score_pre_sla_penalty` for score auditability.
- 🐛 Gate C `retry_consistency` group aggregation now sorts by call time instead of random `task_id`, fixing non-deterministic scoring.
- 📝 `Docs/05_QUALITY_GATE.md` gained a `HarnessEvaluationGate` section; Book Ch07 SLA-penalty and `EfficiencyConfig` fallback misconceptions corrected.

## v0.9.12 (2026-08-19) — OpenCode Plugin Hardening + Harness Method Alignment

- ✨ OpenCode plugin: Slack alerting on blocked tool calls (`AGENT_EVALUATOR_ALERT_WEBHOOK_URL`) and install-time hook-registration self-check.
- 🐛 `EvalDecorator.conversation()` multi-monitor data loss now warns instead of failing silently.
- 🐛 `EvaluationReport.summary()` timestamp serialization crash fixed.
- 🐛 `ch02_quickstart.py` accuracy value permanently pinned at 0.0 — fixed.
- 📝 Docs / `Media/Harness_Method` updated to match.

## v0.9.11 (2026-08-18) — Full-Codebase Pylance Type Audit + Several Real Bugs Fixed

- 🧹 Full-codebase Pylance type audit (trackers, gates, decorators, integrations, `serve/`, CLI, examples, OpenCode plugin) — no intended behavior changes.
- 🐛 Several real bugs found along the way: `PerformanceMonitor.session_tcr`, decorator monitor-list iteration, `dspy_integration`, Gate F type mismatch, `serve/` imports, missing `__all__` exports.
- 📝 Example fixes in `ch11`/`ch19`/`ch26`/`ch27`.

## v0.9.10 (2026-08-05) — README/CLAUDE.md Drift Fixes · trend Duplicate Hint Fix

- 📝 README/CLAUDE.md drift fixed (test count, example count, framework adapter table).
- 🐛 `agent-eval trend --fail-on-regression` duplicate hint message fixed.

## v0.9.9 (2026-07-14) — tool_guard Decorator · Decorator Architecture Fixes · Lint Debt Cleanup

- ✨ `tool_guard` decorator (SPEC-039) automates the `LiveGuardrail` check → execute → record cycle.
- 🐛 6 decorator-architecture defects fixed alongside `tool_guard`; example bugs fixed in `ch16`/`ch21`/`ch22`.
- 🧹 Lint debt reduced (4,015 → ~1,100 errors); mypy target raised to Python 3.10.
- 📝 Book Ch22–34 examples reorganized to match the current chapter structure.

## v0.9.8 (2026-07-06) — Version-Aware Comparison · Persistent Anomaly Baseline · AOO ADE Local Dev Loop

- 📊 Version-aware comparison: `prompt_version`/`agent_version` filters, pairwise `LLMJudge.judge_pairwise()` A/B testing (`win_rate`).
- 🧪 CI gating: per-version baselines (`--baseline-version`), golden-set regression gate (`--fail-on-golden-regression`).
- 🔁 Persistent anomaly baseline via `rehydrate_from_storage()`.
- 🔗 AOO stack: batch Gate A/D/G integration for OpenCode, `agent_version="auto"` git tagging — see [`Docs/AOO_STACK.md`](Docs/AOO_STACK.md).
- 🔒 Team-concurrency & branch-guard hardening; new `agent-eval claims add/list/release/audit` CLI.

## v0.9.7 (2026-07-05) — Local ADE Self-Correction Memory Layer

- 🧠 `ToolParameterSafetyConfig.scope_tool_names` scopes dangerous-pattern checks to specific tools, fixing a false-positive block on unrelated calls.
- 🔍 SQLite backend gained an FTS5 `search_violations()` index over past Gate B/E guardrail violations, plus a stdio MCP server exposing it.
- See [`Docs/AOO_STACK.md`](Docs/AOO_STACK.md) for the OpenCode integration these tie into.

## v0.9.6 (2026-07-04) — Real-Time Guardrail API · Gate Package Decomposition · PII Redaction & LLM Judge Trust Tooling

- 🛡️ **`LiveGuardrail`**: new real-time API blocks a single tool call before it executes, reusing the batch Gate B/E checks — see [`Docs/AOO_STACK.md`](Docs/AOO_STACK.md).
- 🐛 Fixed a real pydantic-ai 2.x incompatibility (`.data`/`.usage()` → `.output`) that silently corrupted `PydanticAIEvaluator` records.
- 🏗️ Gate A–G scoring logic decomposed out of the `decorators.py`/`monitor.py` God Objects into `gates/gate_x/*` packages — no behavior change.
- 🔒 Opt-in PII redaction at save time; new `LLMJudgeCalibration` judge-vs-human trust harness.
- 🔌 3 new framework adapters (`openai_agents`, `google_adk`, `claude_agent_sdk` — 24 total); CI, Dependabot, and SQLite storage hardening.

## v0.9.5 (2026-06-02) — CLAUDE.md Rewrite · Import Path Fix · Model Name Modernization

- 📝 CLAUDE.md fully rewritten in English with accurate SDK facts.
- 🔧 Fixed decorator import paths in example files (`ch11`/`ch14`/`ch21`) to the public API.
- 🐛 `judge_result` attachment condition relaxed — Gate C LLM-faithfulness filtering now works correctly.
- ✨ `ToolCallAnalyzer` gained `unique_tools` cumulative aggregation.
- 🐛 Fixed Gate G always-fail bug, LLM Judge token budget, and `PlanConfig` defaults.

## v0.9.4 (2026-05-28) — Parallel Execution Bug Fixes · macOS NFD Filename Fix

- 🐛 `@batch_eval(concurrency=N)` sync path: positional-arg calls silently returned empty strings (missing `kwargs` guard).
- 🐛 async path: `item_timeout` was ignored and `on_item_error` was never invoked on item failure.
- 🐛 sync + async: `contexts_arg`/`expected_tools_arg` were passed whole to every worker instead of sliced per item.
- 🐛 `build_pdf_chapters.py` glob pattern now normalizes to NFD, fixing a macOS filename-matching bug on Korean filenames.

## v0.9.3 (2026-05-23) — Gate Attribution Correction · HTML Report Score Breakdown · harness_groups Serialization Fix

- 🐛 `AccuracyEvaluator` now correctly contributes to Gate A (previously silently omitted).
- 🐛 `HallucinationDetector` now also contributes to Gate C faithfulness, not just Gate G.
- 🐛 HTML report breakdown now shows the Accuracy Score (Gate A) and Hallucination Faithfulness (Gate C) rows.
- 🐛 Gate G `hallucination_rate` display fixed (was off by a factor of 100).
- 🐛 `harness_groups` now serialized to JSON so dashboard exports stop using an approximate fallback formula.

## v0.9.2 (2026-05-15) — GPT-5 Standardization · Token Parameter Modernization

- ✨ `gpt-5-nano` adopted as default OpenAI model across library config and all 26 examples; `max_completion_tokens` implemented for GPT-5 API compatibility.
- 🔧 Pricing updated for `gpt-5-nano` ($0.05/$0.40 per 1M tokens); `.env.example` modernized with per-chapter variable mappings for all 26 book chapters.

## v0.9.1 (2026-04-27) — Dependency Restructure · pip Resolver Optimization

- 🔧 Base install reduced to 5 core packages; `[serve]` · `[otel]` · `[pdf]` · `[sdk]` extras split — `[sdk]` transitive package count reduced from 170 to 90.
- 🔧 `arize-phoenix<14.7.0` upper bound pinned to prevent pydantic-ai metapackage pull (lifted in v0.9.3 — resolved in arize-phoenix v15.4.0); openai/langchain ranges narrowed for faster pip resolution (openai candidates 277→37).

## v0.8.x (2026-04-13~23) — Harness Config Unification · Decorator Refactor · Stability

- ✨ 33 Harness Config unified card format; Dashboard reorganized into 3-tier hierarchy with Gate correlation heatmap (7×7 Pearson) and failure cascade tracking; 16 Gate columns added to CSV export.
- 🔧 `RetryConfig` · `LLMJudgeConfig` · `SecurityConfig` structs introduced; `AGENT_EVALUATOR_JUDGE_PROVIDER` env var added; `LLMJudge` multi-model escalation and auto-disable on consecutive errors.
- 🐛 Accuracy F1 overhaul (Token Overlap → harmonic mean); `EfficiencyConfig` / `CostPredictabilityConfig` calculation bugs fixed; example files reorganized into 26 chapter-based `chXX_*.py` structure.

## v0.7.x (2026-04-01~13) — 3 Decorators · 21 Frameworks · OTEL/Phoenix

- ✨ 3 decorator types completed (`@agent_eval` · `@batch_eval` · `@conversation_eval`) with `QuickEval` one-stop facade; 21 framework adapters (LangChain · CrewAI · AutoGen · OpenAI · Anthropic · etc.).
- ✨ `agent-eval monitor` — Arize Phoenix OTEL real-time monitoring; `agent-eval trend` — regression detection with `--fail-on-regression` CI/CD integration.
- 🐛 Critical security tracker bug fixes; LLMJudge G-Eval custom criteria and `faithfulness` scoring added.

## v0.6.x (2026-03-21~04-01) — SDK Stabilization

- LangChain · LangGraph · CrewAI · AutoGen integration · FastAPI dashboard · LLMJudge · ConversationSession

## v0.2.x–v0.5.x — Initial Implementation

- 25 Layer 1/2/3 trackers · initial `evaluation_session` implementation
