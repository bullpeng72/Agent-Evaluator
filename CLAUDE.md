# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based SDK that judges whether an AI agent is ready for production, via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 1.0.1 | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Dev environment
pip install -e ".[dev]"
pip install -e ".[sdk]"       # dashboard + OTEL + LLMJudge + PDF (recommended)
pip install -e ".[examples]"  # all examples runnable (sdk + eval)
pip install -e ".[mcp]"       # search_violations / recommend_fix / ask_insights stdio MCP servers

# CLI — setup & inspection
agent-eval init                                          # API key setup wizard
agent-eval check                                         # config status
agent-eval --version
agent-eval dashboard                                     # FastAPI dashboard (port 8765)
agent-eval monitor                                       # Arize Phoenix + OTLP real-time monitoring

# CLI — CI/CD quality gating (agent-eval gate)
agent-eval gate result.json --tcr 85 --accuracy 70
agent-eval gate result.json --baseline-version v2-cot --fail-on-regression 10       # per-version baseline; exit 2
agent-eval gate result.json --golden-set data/golden_datasets/golden_1.json --fail-on-golden-regression  # exit 3
agent-eval gate result.json --baseline-result prev_run.json --fail-on-case-regression  # exit 4 if a task passed before & fails now (P26)
agent-eval gate result.json --max-cost-per-task 0.05    # cost SLO gate: fail if total_cost / task count exceeds $0.05 (P28)
agent-eval gate result.json --max-review-high 0 --notify slack://hooks.slack.com/services/T/B/X  # exit 4 on HIGH review items; post narrative + regressions + cohort winner
agent-eval gate result.json --digest                    # also print PM / QA / engineer briefs after the table (P34)
# note: if .aoo/targets.json exists (from `agent-eval target set`), `gate` auto-loads it as the thresholds
#       unless --gate-thresholds / --tcr / --accuracy are given explicitly (P43) — there is no --target-file flag

# CLI — diagnosis / comparison (not CI gates — informational)
agent-eval diagnose result.json --baseline baseline.json --show-diff   # Gate-regression RCA
agent-eval abtest v1.json v2.json --metric accuracy_score              # Welch's t-test
agent-eval abtest v1.json v2.json --sequential --tau 0.05              # mSPRT always-valid inference (safe to peek)
agent-eval abtest v1.json v2.json v3.json                             # 3+ files -> N-way + Benjamini-Hochberg FDR
agent-eval trend results/ --fail-on-regression                        # on a regression, auto-attaches the code diff between the first/last run's lineage.git_commit (--repo-path)
agent-eval trend results/ --output-json trend.json

# CLI — golden dataset
agent-eval dataset build --source results/ --max-cases 30
agent-eval dataset promote result.json --min-priority high            # HITL review queue -> golden regression cases (P15)
agent-eval dataset health golden.json --against v3.json               # golden-set coverage vs current failure modes + stale/dup cases (P58)

# CLI — SLOs / reference frame / closed improvement loop
agent-eval target set --gate A=0.85 --gate E=0.95 --tcr 90            # pin project SLOs in .aoo/targets.json (P43)
agent-eval target show
# once set: `agent-eval gate` uses them (unless --gate-thresholds given) and every "below target"
# line in the report / insights measures against your bar, not 0.7
agent-eval benchmark set --tcr 78 --gate A=0.75 --label support-rag   # pin an external reference distribution in .aoo/reference.json (P53)
agent-eval benchmark set --from-results results/                      # build TCR + per-gate percentile distributions from a dir of result JSONs
agent-eval benchmark show
# once set: `insights.reference_frame` reports the run's percentile + gap to the frontier
agent-eval experiment register --gate A --field avg_subtask_completion --predict-delta 0.08 --note "add SubtaskConfig"  # register a hypothesis in .aoo/experiments.jsonl (P27)
agent-eval experiment list
agent-eval experiment score v3.json --baseline v2.json --persist      # score open hypotheses vs baseline, write verdicts back
agent-eval improve plan v3.json --baseline v2.json                    # closed loop (P49): per-gate proposals
agent-eval improve start v3.json --yes                                # register each proposal as an experiment + write .aoo/improve/*.md stubs
agent-eval improve verify v4.json --baseline v3.json --persist        # score predicted-vs-actual, resolve experiments + append recommendation_outcomes.jsonl
agent-eval improve patch v3.json --repo .                             # emit a unified diff per proposal (prompt file / @agent_eval decorator) — never applies (P61)

# CLI — team scope claims (.aoo/claims.jsonl, TeamConcurrencyConfig integration)
agent-eval claims add src/ --developer auto      # open a claim (owner="auto" -> git user.name)
agent-eval claims list
agent-eval claims release c-a1b2c3d4
agent-eval claims audit --ttl-hours 8            # CI: flag TTL-exceeded / overlapping claims (exit 1)

# CLI — LiveGuardrail install lifecycle (both tools: install · upgrade · doctor · uninstall)
agent-eval opencode install [--global] [--force] [--with-violation-search] [--with-recommend-fix] [--with-ask-insights]
agent-eval opencode upgrade     # re-copy the plugin .ts after a package update (keeps agent-evaluator.config.json)
agent-eval opencode doctor      # verify the install works: plugin freshness + Python stdio-bridge round-trip (--json/--no-live/--strict)
agent-eval opencode uninstall   # remove plugin file + opencode.json mcp entries (run BEFORE pip uninstall; --purge/--dry-run/--yes)
agent-eval claude install [--global] [--force] [--with-violation-search] [--with-recommend-fix] [--with-ask-insights]
agent-eval claude upgrade       # refresh hooks/matchers + deep-merge only NEW guardrail_config.json keys (keeps your edits); --with-* re-registers MCP
agent-eval claude doctor        # static checks + live hook round-trip (allow/deny/batch-report) + MCP handshake (--json/--no-live/--strict)
agent-eval claude uninstall     # remove our hooks from settings.json + deregister MCP + delete session state (run BEFORE pip uninstall; --keep-config/--purge/--dry-run/--yes)

# Quality
pytest
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/

# Build
python -m build
twine upload dist/*
```

---

## Architecture

### 3-Layer Structure

```
Layer 1 — Foundation (no external deps)
  TaskCompletionTracker · AccuracyEvaluator · HallucinationDetector
  ResponseQualityEvaluator · LatencyTracker · TokenEconomyTracker
  MultimodalMetricsTracker

Layer 2 — Agentic (no external deps)
  ToolCallAnalyzer · RetryCorrectionTracker · ToolSelectionTracker
  AgentCoordinationTracker · WorkflowExecutionTracker
  Security: InputSanitizationTracker · OutputLeakageDetector
           ToolAuthorizationTracker · PrivilegeEscalationDetector · ToolChainAttackDetector

Layer 3 — Hybrid (optional deps: DeepEval / Ragas)
  HybridPerformanceMonitor · DeepEvalAdapter · RagasAdapter
  LLMJudge (native — faithfulness, G-Eval replacement, 5-dim scoring)
```

**25 Native Tracker inventory** (Layer 1/2 above = 17 Gate-relevant trackers + 8 operational-support trackers below):

```
Operational support (8, no direct Gate score contribution — report/ops only)
  ImplicitFeedbackTracker · ConversationSession · ConversationMetrics · AnomalyDetector
  CostTracker · AdaptivePolicy · SamplingStage · StreamingEvaluator
```

> 7 (Layer 1) + 5 (Layer 2 agentic) + 5 (Layer 2 security) + 8 (operational support) = **25**.
> `LLMJudge` (Layer 3/Hybrid) and `AlertEngine` (`alerts/` — alerting infra, not a tracker) are **not** among
> the 25 — a common miscount. `Media/Book/Appendix/A_58개지표_레퍼런스.md` is the reader-facing enumeration
> of all 25 — keep it in sync with this list.

### Key Files

```
agent_evaluator/
├── decorators.py          # agent_eval · batch_eval · conversation_eval · EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder (the 33 Harness Configs are defined in gates/gate_x/configs.py — re-exported here)
├── gates/                 # per-Gate packages (A–G, 7 total)
│   ├── base.py            # infra shared by every Gate — _status · _gate_pass_verdict() · evaluate_gate_scores() (the score/threshold/status -> passed loop shared by HarnessEvaluationGate · QuickEval.gate() · cli/gate.py)
│   ├── shared_metrics.py  # RunningAverage etc. running-aggregate primitives + per-Gate SharedAgg classes
│   ├── live_guardrail.py  # LiveVerdict · LiveGuardrail — runs the same Behavioral/Security checks as the batch Gate, synchronously per tool call, before execution. check_before_tool_call() / record_tool_call() / record_blocked_attempt() + the @tool_guard decorator + the live_guardrail_session() context manager.
│   │                       #  options: live_loop_window · lenient_shell_file_write · protected_write_paths · auth_scan_skip_keys · team_concurrency(TeamConcurrencyConfig) · branch_guard(BranchGuardConfig). Loop verdict keys on (tool name + SHA1 of sorted args). Every exception fails open.
│   ├── team_concurrency.py # TeamConcurrencyConfig · load_active_claims() · check_scope_claim() · append_claim() · audit_claims() — .aoo/claims.jsonl scope claims. owner (="auto" -> git user.name) excludes your own claims.
│   ├── branch_guard.py     # BranchGuardConfig · get_current_branch() · is_branch_protected() — LiveGuardrail blocks a direct commit/push to a protected branch before it happens (fail-open).
│   ├── gate_a_goal/        # configs.py (6 Config) · evaluators.py (eval_instruction_adherence, etc.) · aggregate.py (blends TCR + Accuracy + ResponseQuality; details.avg_goal_alignment / avg_plan_coherence are re-referenced by Gate B for diagnosis)
│   ├── gate_b_behavioral/  # configs.py (6) · evaluators.py (+_extract_decoded_candidates: decode base64/hex dangerous commands and re-match) · aggregate.py. forbidden_tools / scope_tool_names matching is case-insensitive.
│   ├── gate_c_reliability/ # configs.py (5) · evaluators.py · aggregate.py. compute_sla_shared_data(tasks) is the source of the SLA shared data (consumed by Gate D); compute() returns (group_dict, shared_raw) — shared_raw.hall_rate / avg_llm_faithfulness are reused by Gate G.
│   ├── gate_d_performance/ # configs.py (5; EfficiencyConfig.fallback_reference_cost_per_completion) · evaluators.py · aggregate.py (the SLA shared data is passed in from Gate C; details carry perf_score_pre_sla_penalty / sla_window_penalty / sla_budget_penalty)
│   ├── gate_e_security/    # configs.py (3) · evaluators.py (+_PII_PATTERNS) · aggregate.py (5 security trackers + CVSS + compliance + threat_response)
│   ├── gate_f_multiagent/  # configs.py (4) · evaluators.py · aggregate.py (monitor.py delegates to it)
│   └── gate_g_observability/ # configs.py (4) · evaluators.py · aggregate.py. details.tool_coverage is ToolCallAnalyzer.get_efficiency_stats()["success_rate"] (tool-call success rate, distinct from trace_continuity). monitor.py passes self.tool_analyzer (not self.tool_call_analyzer).
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError hierarchy
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker · TaskResult · EvaluationReport · TaskType
│   │   ├── layer1.py / layer2.py / security.py  # Layer 1/2 + security trackers. pandas/numpy are lazy-loaded via TYPE_CHECKING/_LazyModule (shortens hook cold start; the real-time verdict path has no pd/np).
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator). agent_version="auto" (auto-tags git commit + dirty hash, monitor.agent_version property) · iteration_note · rehydrate_from_storage() · _build_reproducibility_manifest() (model_params / dataset_ref -> lineage)
│   │   ├── conversation.py# ConversationSession · ConversationMetrics · ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native) · judge_pairwise() (swap-check mitigates position bias) · self_consistency(task, k=3) (judge self-agreement)
│   ├── llm_judge_calibration.py  # LLMJudgeCalibration — judge-vs-human golden-set agreement (MAE · Pearson · Cohen κ, no sklearn). Put it in extra_metrics.judge_calibration to surface it as build_insights's evaluator_trust.
│   ├── live_guardrail_stdio.py   # generic LiveGuardrail stdio bridge (for non-Python callers). build_guardrail accepts 4 Configs + 3 trackers + the option keys; a malformed block is skipped, that block only. Echoes the request "id" back in the response (id matching, prevents desync).
│   ├── live_guardrail_report.py  # SQLite batch-report bridge (many sessions concurrently). Promotes tool_calls -> TaskResult.tool_calls (Gate G); execution_time / success are opt-in; agent_version defaults to "auto".
│   ├── claude_code_hook.py       # Claude Code CLI hook (PreToolUse/PostToolUse/SessionEnd) -> LiveGuardrail. Each call is a separate process, so it writes the tool_call history to a session state file (.claude/.agent-evaluator/sessions/<id>.json, <id>=_safe_session_id) and replays it on every call. Exceptions always fail open.
│   │                       #  load_config search: <cwd> -> walk up -> ~/.claude -> DEFAULT. _session_config() pins the first PreToolUse settings in sessions/<id>.config.json. circuit_breaker_after (default 5) consecutive blocks -> observe-only. History is JSON Lines (append-only). run() returns an int (deny = exit 2).
│   ├── opencode_plugin/agent-evaluator.ts  # OpenCode tool.execute.before/after hooks -> stdio bridge. GuardrailSession (circuit breaker · id->resolver pending Map · 5s timeout). All try/catch fail-open. Snapshot + report upsert on every session.idle (the bridge stays alive for the whole session). Config is a shallow merge over the adjacent agent-evaluator.config.json.
│   ├── violation_search_mcp.py   # search_violations() stdio MCP server (opt-in [mcp]). include_blocked=True includes fully-blocked history. Results carry a recommend_fix() hint.
│   ├── recommend_fix_mcp.py      # recommend_fix(gate, metric=, value=) stdio MCP. Static ontology lookup (all of Gate A–G), no result file needed. metric is normalized via canonical_metric_name().
│   ├── ask_insights_mcp.py       # query a result JSON's insight layer, stdio MCP (--with-ask-insights). insights_summary / insights_readiness / insights_why_failed(task_id) / insights_contrast(task_id) / insights_list(filter)
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   └── dspy_integration.py · pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent — 6 checks. to_dict() carries event_id/metric. explain_event() uses ontology.anomaly_suggestion_for().
├── ontology/              # pure data registry of diagnosis / recommendation knowledge (no external deps). metric_registry.py — GATE_GUIDANCE · NATIVE_METRIC_RULES (absolute thresholds; tcr/accuracy/hallucination_rate are percentages 0–100) · ANOMALY_METRIC_SUGGESTIONS · COMPONENT_GUIDANCE/component_guidance_for() · _COMPONENT_CONFIG_HINT/config_hint_for() · canonical_metric_name() · anomaly_suggestion_for() · pretty_metric_name(). mast_taxonomy.py — MAST (Cemri et al. 2025) 14 failure modes, Gate F only. failure_taxonomy.py — single-agent failure taxonomy, 14 modes + classify_failure() (P55).
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator · golden_health.py (P58)
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler. dispatch_anomaly_events() · dispatch_gate_result(targets, insights, ...) (for gate --notify; never raises; per-target {ok, error}).
├── storage/               # sqlite_backend.py — save_tasks_to_db / load_tasks_from_db (storage_backend="sqlite", opt-in) · violation_search(FTS5) / search_violations() · blocked_violations (FTS5, audit of fully-blocked attempts).
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware — periodic anomaly scan on the flush thread + auto-wired AlertEngine.dispatch_anomaly_events.
├── rca/                   # Gate-regression root-cause diagnosis (RCA) + improvement history. No new verdict formulas — reuses existing logic.
│   ├── diagnose.py        # diagnose(current, baseline=None): detect -> attribute -> cross-reference. In absolute mode (no baseline), finding["component_shortfalls"] (weakest components first + NATIVE_METRIC_RULES prescription). newly_unmeasured_gates (scored in baseline, None in current). _ranking_scale corrects per-suffix sorting (return-value units are preserved).
│   ├── experiment_metadata.py  # derive_experiment_metadata() — contrasts the two reports' lineage.git_commit, pure git (no gh). changed_files is git diff --name-only.
│   ├── verify.py          # verify_recommendation_outcome() — whether an action improved things: confirmed / refuted / inconclusive.
│   ├── recommendation_tracking.py  # record_ / load_ / summarize_recommendation_outcomes() — append-only JSONL (.aoo/).
│   ├── improvement_priors.py       # synthesize_priors(experiments, outcomes) — folds the two logs into a per-(gate, change-category) confirm-rate / mean-Δ track record (P57). prior_for() to query. Pure counting, no ranking.
│   └── experiments.py     # .aoo/experiments.jsonl hypothesis registry. register / load / score / resolve_experiment · recalibrated_delta(). Delegates to verify.py.
├── reporting/             # the full output-surface map + information layers live in Docs/09_OUTPUTS.md. Update that doc when adding a new output section.
│   ├── history.py         # scan_history() (scan sibling result JSONs) · trend_summary() (per-Gate first/last/slope + consecutive_decline) · load_change_ledger(). Pure stdlib.
│   ├── insights.py        # build_insights() — the machine-readable insight layer. Fields / schema / phase history are in §"extra_metrics.insights" below and Docs/specs/SPEC-041-insight-delivery.md. parse_span_timeline() etc. are pure helpers. Never raises.
│   └── comprehensive_report.py  # generate_comprehensive_html_report(monitor) / generate_html_from_result_file(rf) — single-result HTML report (shared by `agent-eval gate`'s save and the dashboard export) · generate_comparison_html_report(). The _build_* helpers render the same content as insights. _effective_fail(): not success OR acc<0.7 OR comp<0.4.
└── serve/
    ├── server.py          # FastAPI dashboard. create_app coerces results_dir to a Path. Routes include /dashboard, /sdk-docs, /api/docs.
    ├── templates/dashboard2.html.j2  # the only /dashboard template. File Compare tab (group_by · Pairwise Judge · Export HTML) + Improve tab (renders top_detail_deltas ↔ component_shortfalls depending on whether a baseline is present).
    └── routers/           # alerts · anomaly · config · conversation · cost · data · diagnose · export · feedback · golden · stream · transparency · webhook. data.py: list_results / compare_results. diagnose.py: GET /api/diagnose/{file_id}. export.py: GET /html/compare (registered before /html/{file_id}).
```

### Harness Gate Config Groups (33 total)

| Gate | Configs |
|------|---------|
| A — Goal Achievement (6) | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig |
| B — Behavioral Integrity (6) | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig |
| C — Reliability (5) | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig |
| D — Performance Contract (5) | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig |
| E — Security Boundary (3) | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig |
| F — Multi-Agent Coordination (4) | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig |
| G — Observability (4) | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig |

Gate A–G results are stored under `extra_metrics.harness_groups` in the JSON result file.
The result JSON also carries a top-level `schema_version` (`"1.1"`, SPEC-041 P4.3) so consumers can adapt to field-shape changes — bump the major on a breaking change.

**`extra_metrics.insights`** — machine-readable insight layer (L5/L6). `reporting/insights.py::build_insights(current, baseline=None, *, recommendation_log_path=None, experiments_log_path=None, with_experiment_metadata=False, repo_path=".", narrator=None, fixer=None, explainer=None, targets=None, reference=None, golden_set_path=None, history_dir=None, current_file=None, cohort=None, cohort_metric="tcr", partial=False)` re-shapes existing verdicts (`rca.diagnose()`, `utils.confidence`, `ontology.metric_registry`, the `gates/*` aggregates, `rca.recommendation_tracking`/`verify`) into one JSON-serializable dict. **No new scoring formulas. Never raises** — a section that fails to compute is omitted or `null`.

- **Attached / served by:** `monitor.save_to_file()` → `extra_metrics.insights`; `serve/routers/diagnose.py` → `result["insights"]` (dashboard Improve tab); consumed by `cli/gate.py` (`--digest`, `--fail-on-case-regression`, `--max-review-high`, `--notify`). The static HTML report renders the same content via its own `_build_*` helpers (content parity — `insights` is the machine channel).
- **Partial / mid-run (P50):** `build_insights(current, partial=True)` returns only the cheap baseline-free subset — `detection_mode:"partial"`, `running_verdict{decisive, verdict:ready|not_ready|undecided, pass_rate_ci_pct, gates_below_target, reason}` (Wilson CI on the binary pass-rate vs the TCR target + "all measured gates at bar"), plus `verdict`/`readiness`/`gate_findings`/`failure_clusters`/`security_*`/`calibration`/`narrative`. `PerformanceMonitor.running_insights()` / `.should_early_stop()` → `(stop, running_verdict)` wrap it for early-stop in an eval loop (advisory; the caller breaks).
- **Schema is the contract:** `agent_evaluator/schemas/insights.schema.json` (Draft 2020-12; every object `additionalProperties:true` for forward-compat; nullable sections typed `["object"|"array","null"]`). `tests/test_insights_schema.py` validates several scenarios.
- **Hooks (opt-in, never auto-applied):** `narrator=Callable[[insights_dict], str]` replaces the deterministic `narrative`; `fixer=Callable[[payload], dict|None]` replaces `recommendations[].proposal`; `explainer=Callable[[payload], dict|None]` replaces `failure_explanations` (claim-level); `targets` (dict from `utils.targets.load_targets()`, or the auto-loaded `.aoo/targets.json`) makes `verdict`/`readiness` measure against the user's per-gate/TCR bar instead of 0.7. A bad return / exception → deterministic fallback.

Provenance (P51): `verdict.next_actions[]`, `readiness.fix_plan[]` and `recommendations[]` each carry a `derived_from` naming the signal they came from (`{source: failure_cluster|gate_component_shortfall|gate_score|gate_status|security_finding, …}`).

Top-level keys (`build_insights()` output, ~62): `schema_version` · `detection_mode` · `verdict` · `narrative` · `narrative_audit` · `briefs` · `readiness` · `reference_frame` · `threshold_sensitivity` · `metric_confidence` · `uncertainty_budget` · `metric_signal` · `judge_robustness` · `evaluator_trust` · `review_queue` · `gate_findings` · `failure_clusters` · `failure_segments` · `failure_triggers` · `failure_taxonomy` · `ablation_hints` · `contrast_pairs` · `failure_explanations` · `failure_lineage` · `regression_attribution` · `improvement_priors` · `recommendations` (`[].proposal` · `[].prior`) · `latency_budget` · `efficiency_opportunities` · `rag_localization` · `slice_analysis` · `metadata_slices` · `multiplicity_audit` · `sample_guidance` · `reproducibility_manifest` · `cost_economics` · `calibration` · `security_findings` · `security_posture` · `score_breakdowns` · `trajectories` · `experiments` · `conversation` · `multiagent` · `eval_set_quality` (`.capability_coverage` · `.contamination` · `.targeted_additions`) · `golden_health` · `eval_representativeness` · `cohort_comparison` · `trace_diffs` · `longitudinal` · `insight_changes` · `freshness` · `change_attribution` · `nondeterminism` · `shared_cause_explanations` · `newly_unmeasured_gates` · `experiment_metadata`.

**Adding / changing an insight section:** (1) add/adjust the `_*_section` in `reporting/insights.py` (pure, never raises, deterministic — seed any RNG); (2) wire it into the `build_insights()` `out` dict (or the post-dict block for sections that read other sections); (3) update `insights.schema.json` + a `tests/test_insights_schema.py` scenario; (4) render it in `comprehensive_report.py` (`_build_*` + both `parts` lists + `_TOC_LABELS`) and, if relevant, the dashboard Improve tab; (5) document the phase in **`Docs/specs/SPEC-041-insight-delivery.md`** (the full field-by-field description + phase history live there, not here).

For the field-by-field description of every key, the `_build_*` render surfaces, the dashboard panels, the CLI wiring, and the P7–P62 phase history, see **`Docs/specs/SPEC-041-insight-delivery.md`**.

### Native Tracker → Gate Score Contribution (`_compute_harness_groups`)

| Tracker | Gate | How it contributes | Condition |
|---------|------|--------------------|-----------|
| `TaskCompletionTracker` | A, C | `_a_vals[0]` (the TCR component), `_rel_vals` | always |
| `AccuracyEvaluator` | **A** | blended into `_a_vals[0]` (`0.6×TCR + 0.4×Accuracy`) | `_evaluations` count > 0 |
| `ResponseQualityEvaluator` | **A** | adds to `_a_vals` (mean of relevance + completeness / 5, normalized 0→1) | when quality dims are measured |
| `LatencyTracker` | D | `_perf_vals` | always |
| `TokenEconomyTracker` | — | (no gate-score contribution) | token cost tracking / reporting only |
| `HallucinationDetector` | **C + G** | `_rel_vals`, `_obs_vals` | fallback when there is no LLM Judge faithfulness (`1 − rate`) |
| `LLMJudge` (faithfulness) | **C** | `_rel_vals` | applied first when per-task faithfulness is recorded (`score / 5` normalized); replaces HallucinationDetector |
| `RetryCorrectionTracker` | — | (no gate-score contribution) | retry-count / pattern tracking only |
| `ToolCallAnalyzer` | G | `_obs_vals` — `success_rate / 100` (normalized 0→1) | when tool_calls are recorded |
| `WorkflowExecutionTracker` | — | (no gate-score contribution) | chain_steps tracking / analysis only |
| Security Trackers (5) | E | `_all_e_scores` | `enable_security_metrics=True` |
| `AgentCoordinationTracker` | F | `_f_vals` — `calculate_coordination_score().overall_score / 10` (normalized 0→1) | when agent_interactions are recorded |
| `ToolSelectionTracker` | F | `_f_vals` — `avg_f1_score / 100` (normalized 0→1) | when expected_tools are given |

> **Gate A weighting**: `_a_score = gate_a_tcr_weight × _a_vals[0] + (1 − gate_a_tcr_weight) × mean(the rest)`.
> Default `gate_a_tcr_weight=0.4` — adjustable via `PerformanceMonitor(gate_a_tcr_weight=...)`.
> **Gate B weighting**: if `gate_b_loop_weight > 0.0`, the loop score is weighted; if `0.0` (default), it is a plain mean of the available metrics.
> Default `gate_b_loop_weight=0.0` — adjustable via `PerformanceMonitor(gate_b_loop_weight=...)`.
> **Gate C weighting**: `_rel_score = gate_c_tcr_weight × _rel_vals[0] + (1 − gate_c_tcr_weight) × mean(the rest)`.
> Default `gate_c_tcr_weight=0.4` — adjustable via `PerformanceMonitor(gate_c_tcr_weight=...)`.
> Gate B details show `avg_goal_alignment` / `avg_plan_coherence`, but those re-reference Gate A's computed values for diagnosis and are **not part of the Gate B score**.
> **`AgentCoordinationTracker` scale**: `calculate_coordination_score().overall_score` is on a 0–10 scale → normalized `/10` in Gate F.
> **`ConsensusConfig.consensus_method`**: `"majority"` = fraction of agreeing pairs; `"unanimity"` = 1.0 only if all pairs agree, else 0.0; `"weighted"` = weighted fraction based on `agent_weights`.
> **`eval_conflict_resolution` conflict counting**: if `agent_interactions` are present, count from interactions only; otherwise fall back to response text (prevents double-counting).
> **RCA cross-reference (Gate F ↔ Gate B)**: `gate_f_multiagent` and `gate_b_behavioral` are fully independent slices that do not reference each other, but in a multi-agent deployment, both being low at once is often the same root cause — a coordination failure. When the Gate F score is low, also check `harness_groups.B.details.deadlock_by_type` / `deadlock_count` — a Gate B deadlock frequently explains a low Gate F `avg_conflict_resolution` / `coordination_score`. Conversely, do not assume that a simultaneous Gate C (reliability) + Gate D (performance) drop has a single cause (e.g. SLA) — several unrelated changes coinciding in the same deployment is more common, so first contrast `harness_groups.C.details.sla_breach_rate` against `harness_groups.D.details.sla_window_penalty` / `sla_budget_penalty` to confirm SLA is actually the cause of both.

---

## Key Usage Patterns

### QuickEval (one-stop facade)

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""): ...

@eval.rag
def rag_agent(question, context="", ground_truth=""): ...

eval.save()
eval.gate(tcr=85, accuracy=70)  # sys.exit(1) on failure

# Factories
QuickEval.for_rag("results/")
QuickEval.for_security("results/")
QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### PerformanceMonitor

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # default False
    enable_security_metrics=False,         # default False
    enable_llm_judge=False,
    judge_model=None,          # auto-determined from the API key
    judge_sample_rate=0.1,
)
monitor.record_task(task_result)
monitor.save_to_file("evaluation")  # JSON + HTML
```

> Use `PerformanceMonitor` for new projects. Use `HybridPerformanceMonitor` only when integrating DeepEval/Ragas.

> **`agent_version="auto"`**: reserved sentinel — resolves to the current git commit's short
> SHA (`git rev-parse HEAD`, cached once at `__init__`), with a `-dirty-<hash>` suffix appended when
> tracked files have uncommitted changes (`git diff HEAD`, hashed — distinguishes iterations run without
> committing between them). Falls back to `None` on any git failure. Read the resolved value back via the
> read-only `monitor.agent_version` property (no setter — same "fixed at construction" contract as
> `model_name`). Any other literal string (or `None`, the default) behaves exactly as before — `"auto"` is
> the only reserved value. `iteration_note=` attaches a human-readable one-line note to that dirty-hash
> tag (display only — carried in `lineage.iteration_note`, no effect on scoring).

### Harness Config in a decorator

```python
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    InstructionConfig, LoopDetectionConfig, SLAConfig, ExplainabilityConfig,
)

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=6),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### EvalMetadata — injecting metadata from inside the function

```python
from agent_evaluator import agent_eval
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = f"Answer: {question}"
    return response, EvalMetadata(
        extra={"ttft_ms": 120.5},
        tokens_used={"input": 50, "output": 100, "total": 150},
    )
```

### Context manager

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("results/eval.json") as monitor:
    task = create_taskresult(task_id="t1", question="...", response="...", execution_time=1.2)
    monitor.record_task(task)
```

### LLMJudge

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.1)
result = judge.judge("t1", question="...", response="...", context="...")
# result["scores"]["overall"] · ["faithfulness"] · ["criteria_overall"]

# async path + concurrency/backoff (max_concurrent_judge_calls=5, max_retries=3 defaults)
judge = LLMJudge(model="claude-haiku-4-5-20251001", max_concurrent_judge_calls=5, max_retries=3)
result = await judge.ajudge("t1", question="...", response="...", context="...")
# ajudge() is bounded by an internal asyncio.Semaphore; provider 429s retry with 1s/2s/4s backoff.
# agent_eval's async wrapper uses ajudge() automatically. batch_eval(..., concurrent_judge=True)
# opts into asyncio.gather-based concurrent judge processing (default False = sequential, unchanged).

# Accessing LLMJudge results from the monitor
summary = monitor.llm_judge.get_summary()
# → {"avg_scores": {"overall": float, "criteria_scores": {...}}, "sample_count": int}
```

### create_taskresult helper

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001", question="...", response="...",
    ground_truth="...", execution_time=1.23, task_type="qa",
)
```

### HarnessEvaluationGate

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()   # no arguments
# result: {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool,
#              "threshold": float, "not_measured": bool (only when score=None),
#              "insufficient_data_warnings": list[str] (when present)}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}

# Per-gate thresholds + forced failure of an unmeasured gate
# (with both at their defaults — False / unset — behavior is 100% identical to before)
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],
    group_thresholds={"E": 0.95},   # stricter for Security — the same concept as
                                     # QuickEval.gate(gate_thresholds=...) / CLI --gate-thresholds,
                                     # added symmetrically to this class
    strict_required=True,            # fail if a gate named in required_groups has score=None
                                      # (no Config set at all). The default (False) keeps the
                                      # existing "a disabled gate silently passes" behavior.
)
```

> **Note**: `HarnessEvaluationGate.evaluate()` (Python API), `QuickEval.gate()`, and `cli/gate.py`
> (`agent-eval gate`) are three separate entry points that each invoke the Gate A–G threshold verdict —
> all three share `_compute_gate_regressions()` (the baseline-regression formula) and
> `gates/base.py::evaluate_gate_scores()` (the per-gate score/threshold/status → passed loop). The only
> remaining differences are entry-point-specific features (`HarnessEvaluationGate`'s `strict_required`,
> the CLI's `--baseline-version`/`--golden-set`). All three pass a gate with `score is None` by default
> (`HarnessEvaluationGate` can opt out via `strict_required=True`; the other two always pass). Fixing
> the verdict loop itself (`evaluate_gate_scores()`) propagates to all three automatically; when
> changing an entry-point-specific feature, only that entry point needs checking.

---

## Valid Parameter Reference

### PerformanceMonitor

```
output_dir, pricing, model_name, session_label
enable_transparency, enable_hallucination_detection, enable_security_metrics
security_config, enabled_security_trackers
enable_llm_judge, judge_model, judge_sample_rate, judge_criteria
judge_budget_per_day, judge_budget_storage_path
judge_max_context_chars, judge_escalation_model, judge_escalation_threshold, judge_seed
use_korean_tokenizer, use_semantic_hallucination, semantic_weight
enable_anomaly_detection, anomaly_baseline_window, anomaly_detection_window
auto_save, auto_save_interval, auto_save_filename
enable_otel_child_spans, ttft_variability_config, cost_predictability_config
gate_a_tcr_weight, gate_c_tcr_weight, gate_b_loop_weight
min_samples_default
prompt_version, agent_version, iteration_note, prompt_text, prompt_source_path, config_snapshot, model_params, dataset_ref
retention_mode, window_size
storage_backend
enable_pii_redaction, pii_redaction_categories
```

### @agent_eval

```
task_type, question_arg, ground_truth_arg, task_id_prefix, context_arg
expected_tools_arg, expected_tools, framework, model_name
score_fn, completion_fn, task_id_fn, sample_rate
on_record, on_error, timeout, enabled
alert_rules, flush_every, preset
retry (RetryConfig), llm_judge (LLMJudgeConfig), security (SecurityConfig)
custom_parser, enable_hallucination_detection, rag_mode
enable_anomaly_detection, ttft_seconds, alert_error_mode
instructions, loop_detection, goal_alignment, reproducibility, fault_tolerance, plan_tracking
sla, threat_severity, efficiency, state_consistency, deadlock, observability
consensus, scope, context_retention, explainability, subtask_tracking, propagation
agent_role, graceful_degradation, compliance, resource_budget, conflict_resolution
tool_parameter_safety, knowledge_retention, retry_consistency, error_diagnosis, idempotency
threat_response, context_window, latency_attribution
```

---

## Gate A Tracker Attribution (common mistakes)

| Tracker | Attribution | Notes |
|---------|-------------|-------|
| `TaskCompletionTracker` | Gate A + C | contributes directly to the `_a_vals[0]` TCR component |
| `AccuracyEvaluator` | **Gate A** | blended into `_a_vals[0]` — `0.6×TCR + 0.4×Accuracy` (not a separate term) |
| `ResponseQualityEvaluator` | **Gate A** | mean of relevance + completeness / 5 → an added term in `_a_vals` |
| `HallucinationDetector` | **Gate C + G** | **not** Gate A |

**GoalAlignmentConfig caveat**: the default `ignore_no_tool_tasks=True` — tasks with no tool call are excluded from goal_alignment. For a non-tool agent (QA / conversational), `avg_goal_a = None` and it contributes nothing to the Gate A score. To use GoalAlignmentConfig with a non-tool agent, set `ignore_no_tool_tasks=False`.

**AccuracyEvaluator `task_type` mapping**: `"coding"` is auto-normalized to `"code_generation"` and the AST-comparison evaluation applies. Both values route to `_code_accuracy`.

---

## Coding Conventions

- **Formatter:** ruff, line-length=100
- **Python target:** 3.8+ (f-string, dataclass, typing)
- **Type hints:** required for all public functions; a comment is required when using `Any`
- **Docstrings:** include Args / Returns / Example sections
- **Error handling:** optional dependencies via `try/except ImportError`
- **Zero-division:** a guard is required in every ratio calculation
- **NaN handling:** `pd.isna()` check before pandas statistical calculations
- **API keys:** always `os.getenv()`, never hardcode
- **`enable_*` flags:** expensive operations (hallucination, security) default to `False`
- **Output-message language (SPEC-041):** every message Agent-Evaluator *emits at runtime*
  is **English** — CLI stdout/stderr, HTML report text, `logger.*` / `warnings.warn` /
  exception messages, MCP tool return strings, LiveGuardrail block/remediation text,
  hook messages, dashboard API `detail`/`message`, and any auto-generated
  `partial_reason` / recommendation / alert / insight text. **Exceptions (stay as-is):**
  (a) the *evaluated agent's own content* — task question/response/ground_truth, mock
  responses in demo helpers; (b) Korean-text-processing internals — particle/stopword
  sets and regexes in `gate_a_goal`/`gate_e_security`/`gate_f_multiagent`/`conversation`
  evaluators, the Korean RAG dataset generators (`datasets/`, `serve/routers/golden.py`,
  `korean_rag_*`); (c) source-only text — docstrings, `# comments`, `configs.py` field
  help. New user-facing strings must be written in English.

---

## Architecture Principles

1. **Layer independence** — Layer 1/2 must operate without external dependencies
2. **Harness independence** — the 33 Configs are defined in `gates/gate_x/configs.py`, aggregated in `monitor.py`
3. **Tracker isolation** — each tracker must be independently testable
4. **Minimal side effects** — no `sys.path`, `os.chdir()`, or global state modification
5. **Security metric isolation** — security trackers are opt-in due to performance impact
6. **Serve separation** — `serve/` is optional FastAPI; core logic must not depend on it

---

## Known Dependency Constraints

| Item | Status | Note |
|------|--------|------|
| `ragas>=0.4.0` | ✅ | EvaluationDataset, SingleTurnSample API supported |
| `[crewai,autogen]` pydantic conflict | 🟡 | silently downgrades to pydantic 2.11.x |
| `arize-phoenix>=15.4.0` | ✅ | pydantic-ai compatibility resolved (previous `<14.7.0` pin removed) |
| `AnswerRelevancy` embeddings | 🟡 | auto-configured only with an OpenAI key |

---

## Testing

**170 files, 4,800+ test functions** in `tests/`.

```bash
pytest  # configured in pyproject.toml (testpaths, cov)
```

Note: `agent_evaluator/utils/transparency_manager.py` contains `TestTransparencyManager` — a **production class**, not a test file.

`agent_evaluator/utils/confidence.py` (SPEC-041 P5·P10·P14·P22) — pure functions (stdlib only, no numpy, seed-fixed deterministic) for the confidence interval / sample adequacy / verdict confidence of a single run's metrics: `wilson_interval` · `bootstrap_mean_ci` · `bootstrap_diff_ci` (P10) · `welch_t_p` (P22, Welch t-test normal-approximation p-value, no scipy) · `required_n_for_halfwidth` · `mde_two_proportions` (P10) · `verdict_confidence` (P14: `judge_trust` argument) · `expected_calibration_error` · `brier_score` · `risk_coverage_points` · `pearson_r`. Consumed by `reporting/comprehensive_report.py` · `reporting/insights.py` · `cli/abtest.py`.

---

## Accuracy Evaluation (AccuracyEvaluator)

| Metric | Weight | Method |
|--------|--------|--------|
| Token Overlap | 40% | F1 token matching |
| Jaccard Similarity | 30% | set intersection / union |
| LCS Ratio | 20% | longest common subsequence |
| Char Similarity | 10% | Levenshtein |

- `code_generation`/`coding`: 1.0 on a successful AST parse
- `tool_use`: 0.6 if `tool_calls` is empty
