# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 1.0.0 | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Dev environment
pip install -e ".[dev]"
pip install -e ".[sdk]"       # dashboard + OTEL + LLMJudge + PDF (recommended)
pip install -e ".[examples]"  # all examples runnable (sdk + eval)
pip install -e ".[mcp]"       # search_violations MCP server (agent_evaluator.integrations.violation_search_mcp)

# CLI
agent-eval init                                           # API key setup wizard
agent-eval check                                          # config status
agent-eval --version                                      # version info
agent-eval dashboard                                      # FastAPI dashboard (port 8765)
agent-eval gate result.json --tcr 85 --accuracy 70        # CI/CD quality gating
agent-eval gate result.json --baseline-version v2-cot --fail-on-regression 10   # per-version baseline
agent-eval gate result.json --golden-set data/golden_datasets/golden_1.json --fail-on-golden-regression  # golden-set gate, exit 3
agent-eval gate result.json --baseline-result prev_run.json --fail-on-case-regression   # exit 4 if a task passed before & fails now (SPEC-041 P26)
agent-eval gate result.json --max-cost-per-task 0.05       # cost SLO gate: fail if total_cost / task count exceeds $0.05 (SPEC-041 P28)
agent-eval gate result.json --digest                       # also print PM / QA / engineer briefs after the table (SPEC-041 P34)
agent-eval gate result.json --max-review-high 0 --notify slack://hooks.slack.com/services/T/B/X  # exit 4 on HIGH review items; post narrative+regressions+cohort winner
agent-eval diagnose result.json --baseline baseline.json   # Gate regression RCA (not a CI gate, informational only)
agent-eval abtest v1.json v2.json --metric accuracy_score   # statistical A/B (Welch's t-test), not a CI gate
agent-eval abtest v1.json v2.json --sequential --tau 0.05   # mSPRT always-valid inference (safe to peek)
agent-eval abtest v1.json v2.json v3.json                   # 3+ files -> N-way + Benjamini-Hochberg FDR
agent-eval dataset build --source results/ --max-cases 30 # golden dataset
agent-eval dataset promote result.json --min-priority high # HITL review queue -> golden regression cases (P15)
agent-eval dataset health golden.json --against v3.json    # golden-set coverage vs current failure modes + stale/dup cases (SPEC-041 P58)
agent-eval monitor                                        # Arize Phoenix + OTLP
agent-eval opencode install                               # LiveGuardrail OpenCode plugin (--global/--force)
agent-eval opencode install --with-violation-search       # + register search_violations MCP server (requires [mcp] extra)
agent-eval opencode install --with-recommend-fix           # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval opencode install --with-ask-insights            # + register ask_insights MCP server — query a result JSON's insight layer (requires [mcp] extra)
agent-eval opencode upgrade                               # re-copy the plugin .ts after a package update (keeps agent-evaluator.config.json)
agent-eval opencode doctor                                # verify the install works: plugin freshness + Python stdio-bridge round-trip (--json/--no-live/--strict)
agent-eval opencode uninstall                             # remove plugin file + opencode.json mcp entries (run BEFORE pip uninstall; --purge/--dry-run/--yes)
agent-eval claude install                                 # LiveGuardrail Claude Code CLI hooks (--global/--force)
agent-eval claude install --with-violation-search         # + register search_violations MCP server (requires [mcp] extra)
agent-eval claude install --with-recommend-fix             # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval claude install --with-ask-insights              # + register ask_insights MCP server — query a result JSON's insight layer (requires [mcp] extra)
agent-eval claude upgrade                                 # refresh hooks/matchers + deep-merge NEW guardrail_config.json keys (keeps your edits); --with-* re-registers MCP
agent-eval claude doctor                                  # verify the install works: static checks + live hook round-trip (allow/deny/batch-report) + MCP handshake (--json/--no-live/--strict)
agent-eval claude uninstall                               # remove our hooks from settings.json + deregister MCP + delete session state (run BEFORE pip uninstall; --keep-config/--purge/--dry-run/--yes)
agent-eval trend results/ --fail-on-regression            # trend analysis (회귀 시 첫/마지막 run의 lineage.git_commit 사이 코드 diff 자동 첨부, --repo-path)
agent-eval trend results/ --output-json trend.json
agent-eval claims add src/ --developer auto                # open a .aoo/claims.jsonl scope claim
agent-eval claims list                                     # show active claims
agent-eval claims release c-a1b2c3d4                       # release a claim
agent-eval claims audit --ttl-hours 8                      # CI: flag TTL-exceeded/overlapping claims

agent-eval experiment register --gate A --field avg_subtask_completion --predict-delta 0.08 --note "add SubtaskConfig"  # register a hypothesis in .aoo/experiments.jsonl (SPEC-041 P27)
agent-eval experiment list                                 # show open/resolved hypotheses
agent-eval experiment score v3.json --baseline v2.json --persist  # score open hypotheses vs baseline, write verdicts back

agent-eval target set --gate A=0.85 --gate E=0.95 --tcr 90        # pin project SLOs in .aoo/targets.json (SPEC-041 P43)
agent-eval target show                                            # print current targets
# once set: `agent-eval gate` uses them (unless --gate-thresholds given) and every
# "below target" line in the report / insights measures against your bar, not 0.7

agent-eval benchmark set --tcr 78 --gate A=0.75 --label support-rag   # pin an external reference distribution in .aoo/reference.json (SPEC-041 P53)
agent-eval benchmark set --from-results results/                 # build TCR + per-gate percentile distributions from a dir of result JSONs
agent-eval benchmark show                                        # print the current reference
# once set: `insights.reference_frame` reports the run's percentile + gap to the frontier

agent-eval improve plan v3.json --baseline v2.json               # closed loop (SPEC-041 P49): show per-gate proposals
agent-eval improve start v3.json --yes                            # register each proposal as an experiment + write .aoo/improve/*.md stubs
agent-eval improve verify v4.json --baseline v3.json --persist    # score predicted-vs-actual, resolve experiments + append recommendation_outcomes.jsonl
agent-eval improve patch v3.json --repo .                         # emit a unified diff per proposal (prompt file / @agent_eval decorator) — never applies (SPEC-041 P61)

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
├── decorators.py          # agent_eval · batch_eval · conversation_eval · EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder (33 Harness Config는 gates/gate_x/configs.py 정의, 여기선 re-export)
├── gates/                 # Gate 단위 패키지 (A–G 7개)
│   ├── base.py            # 전 Gate 공유 인프라 — _status · _gate_pass_verdict() · evaluate_gate_scores()(HarnessEvaluationGate·QuickEval.gate()·cli/gate.py 공유 판정 루프)
│   ├── shared_metrics.py  # RunningAverage 등 running-aggregate 원시 타입 + Gate별 SharedAgg 클래스
│   ├── live_guardrail.py  # LiveVerdict · LiveGuardrail — 배치 Gate와 동일한 Behavioral/Security 체크를 실행 전 tool call 단위로 동기 호출. check_before_tool_call()/record_tool_call()/record_blocked_attempt() + @tool_guard 데코레이터 + live_guardrail_session() 컨텍스트 매니저
│   │                       #  옵션: live_loop_window · lenient_shell_file_write · protected_write_paths · auth_scan_skip_keys · team_concurrency(TeamConcurrencyConfig) · branch_guard(BranchGuardConfig). 루프 판정은 (도구명 + 정렬 인자 SHA1) 기준. 예외는 전부 fail-open
│   ├── team_concurrency.py # TeamConcurrencyConfig · load_active_claims() · check_scope_claim() · append_claim() · audit_claims() — .aoo/claims.jsonl 스코프 클레임. owner(="auto"면 git user.name)로 자기 클레임 제외
│   ├── branch_guard.py     # BranchGuardConfig · get_current_branch() · is_branch_protected() — 보호 브랜치 직접 커밋/푸시를 LiveGuardrail이 실행 전 차단(fail-open)
│   ├── gate_a_goal/       # configs.py(6 Config) · evaluators.py(eval_instruction_adherence 등) · aggregate.py(TCR+Accuracy 블렌딩+ResponseQuality; details의 avg_goal_alignment/avg_plan_coherence를 Gate B가 진단용 재참조)
│   ├── gate_b_behavioral/ # configs.py(6) · evaluators.py(+_extract_decoded_candidates: base64/hex 위험명령 디코드 후 재매치) · aggregate.py. forbidden_tools/scope_tool_names 매칭은 대소문자 무시
│   ├── gate_c_reliability/# configs.py(5) · evaluators.py · aggregate.py. compute_sla_shared_data(tasks)가 SLA 공유데이터 원천(Gate D 소비); compute()는 (group_dict, shared_raw) 반환 — shared_raw의 hall_rate/avg_llm_faithfulness를 Gate G가 재사용
│   ├── gate_d_performance/# configs.py(5; EfficiencyConfig.fallback_reference_cost_per_completion) · evaluators.py · aggregate.py(SLA 공유데이터는 Gate C에서 전달; details에 perf_score_pre_sla_penalty/sla_window_penalty/sla_budget_penalty)
│   ├── gate_e_security/   # configs.py(3) · evaluators.py(+_PII_PATTERNS) · aggregate.py(5개 보안 트래커 + CVSS + compliance + threat_response)
│   ├── gate_f_multiagent/ # configs.py(4) · evaluators.py · aggregate.py(monitor.py가 위임 호출)
│   └── gate_g_observability/ # configs.py(4) · evaluators.py · aggregate.py. details의 "tool_coverage"는 ToolCallAnalyzer.get_efficiency_stats()["success_rate"](도구 호출 성공률, trace_continuity와 다름). monitor.py는 self.tool_analyzer 전달(self.tool_call_analyzer 아님)
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError hierarchy
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker · TaskResult · EvaluationReport · TaskType
│   │   ├── layer1.py / layer2.py / security.py  # Layer 1/2 + 보안 트래커. pandas/numpy는 TYPE_CHECKING/_LazyModule 지연 로딩(훅 콜드스타트 단축; 실시간 판정 경로엔 pd/np 없음)
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator). agent_version="auto"(git commit+dirty hash 자동 태깅, monitor.agent_version 프로퍼티) · iteration_note · rehydrate_from_storage() · _build_reproducibility_manifest()(model_params/dataset_ref → lineage)
│   │   ├── conversation.py# ConversationSession · ConversationMetrics · ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native) · judge_pairwise()(swap-check 포지션 편향 완화) · self_consistency(task, k=3)(judge 자기일치도)
│   ├── llm_judge_calibration.py  # LLMJudgeCalibration — judge-vs-human 골든셋 일치도(MAE·Pearson·Cohen κ, sklearn 무의존). extra_metrics.judge_calibration에 넣으면 build_insights의 evaluator_trust로 노출
│   ├── live_guardrail_stdio.py   # LiveGuardrail 범용 stdio 브리지(non-Python 호출자용). build_guardrail이 4개 Config + tracker 3종 + 옵션 키 수용; 블록 오타는 그 블록만 스킵. 요청 "id"를 응답에 되돌려 실음(id 매칭, 데스싱크 방지)
│   ├── live_guardrail_report.py  # SQLite 배치 리포트 브리지(다중 세션 동시). tool_calls→TaskResult.tool_calls 승격(Gate G); execution_time/success 옵트인; agent_version 기본 "auto"
│   ├── claude_code_hook.py       # Claude Code CLI 훅(PreToolUse/PostToolUse/SessionEnd)→LiveGuardrail. 호출마다 별도 프로세스라 세션 상태파일(.claude/.agent-evaluator/sessions/<id>.json, <id>=_safe_session_id)에 tool_call 이력을 남기고 매 호출 replay. 예외는 항상 fail-open
│   │                       #  load_config 탐색: <cwd> → walk-up → ~/.claude → DEFAULT. _session_config()가 첫 PreToolUse 설정을 sessions/<id>.config.json에 고정. circuit_breaker_after(기본 5) 연속 차단 시 관찰 전용. 이력은 JSON Lines(append-only). run()은 int 반환(deny=exit 2)
│   ├── opencode_plugin/agent-evaluator.ts  # OpenCode tool.execute.before/after 훅→stdio 브리지. GuardrailSession(circuit breaker · id→resolver pending Map · 5s 타임아웃). 전부 try/catch fail-open. session.idle마다 스냅숏+리포트 upsert(브리지는 세션 내내 유지). 설정은 옆의 agent-evaluator.config.json 얕은 병합
│   ├── violation_search_mcp.py   # search_violations() stdio MCP 서버(옵트인 [mcp]). include_blocked=True로 완전 차단 이력까지. 결과에 recommend_fix() 힌트 첨부
│   ├── recommend_fix_mcp.py      # recommend_fix(gate, metric=, value=) stdio MCP. ontology 정적 지식 조회(Gate A–G 전체), 결과 파일 불필요. metric은 canonical_metric_name()으로 정규화
│   ├── ask_insights_mcp.py       # 결과 JSON의 insight 계층 조회 stdio MCP(--with-ask-insights). insights_summary/insights_readiness/insights_why_failed(task_id)/insights_contrast(task_id)/insights_list(filter)
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   └── dspy_integration.py · pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent — 6개 체크. to_dict()에 event_id/metric. explain_event()는 ontology.anomaly_suggestion_for() 사용
├── ontology/              # 진단/추천 지식 순수 데이터 레지스트리(외부 의존성 없음). metric_registry.py — GATE_GUIDANCE · NATIVE_METRIC_RULES(절대 임계값; tcr/accuracy/hallucination_rate는 퍼센트 0–100) · ANOMALY_METRIC_SUGGESTIONS · COMPONENT_GUIDANCE/component_guidance_for() · _COMPONENT_CONFIG_HINT/config_hint_for() · canonical_metric_name() · anomaly_suggestion_for() · pretty_metric_name(). mast_taxonomy.py — MAST(Cemri et al. 2025) 14개 실패모드, Gate F 전용. failure_taxonomy.py — 단일 에이전트 실패 taxonomy 14개 모드 + classify_failure()(SPEC-041 P55)
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler. dispatch_anomaly_events() · dispatch_gate_result(targets, insights, ...)(gate --notify용, 절대 raise 안 함, per-target {ok,error})
├── storage/               # sqlite_backend.py — save_tasks_to_db/load_tasks_from_db(storage_backend="sqlite" 옵트인) · violation_search(FTS5)/search_violations() · blocked_violations(FTS5, 완전 차단 시도 감사)
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware — flush 스레드에 주기적 이상탐지 스캔 + AlertEngine.dispatch_anomaly_events 자동 연결
├── rca/                   # Gate 회귀 원인진단(RCA) + 개선 이력. 새 판정 공식 없음 — 기존 로직 재사용
│   ├── diagnose.py        # diagnose(current, baseline=None): 감지→원인귀속→교차확인. absolute 모드(baseline 없음)에선 finding["component_shortfalls"](약한 컴포넌트 우선 + NATIVE_METRIC_RULES 처방). newly_unmeasured_gates(baseline엔 점수, current엔 None). _ranking_scale로 접미사별 정렬 보정(반환값 단위는 보존)
│   ├── experiment_metadata.py  # derive_experiment_metadata() — 두 리포트 lineage.git_commit 대조, 순수 git(gh 무의존). changed_files는 git diff --name-only
│   ├── verify.py          # verify_recommendation_outcome() — 조치 후 개선 여부 confirmed/refuted/inconclusive
│   ├── recommendation_tracking.py  # record_/load_/summarize_recommendation_outcomes() — append-only JSONL(.aoo/)
│   ├── improvement_priors.py       # synthesize_priors(experiments, outcomes) — 두 로그를 (gate, change-category)별 confirm-rate/mean-Δ 실적으로 접기(SPEC-041 P57). prior_for()로 조회. 순수 카운팅, 랭킹 없음
│   └── experiments.py     # .aoo/experiments.jsonl 가설 레지스트리. register/load/score/resolve_experiment · recalibrated_delta(). verify.py 위임
├── reporting/             # 출력 표면 전체 지도·정보 계층은 docs/09_OUTPUTS.md. 새 출력 섹션 추가 시 그 문서도 갱신
│   ├── history.py         # scan_history()(형제 결과 JSON 스캔) · trend_summary()(per-Gate first/last/slope + consecutive_decline) · load_change_ledger(). 순수 stdlib
│   ├── insights.py        # build_insights() — 머신 판독 insight 계층. 필드/스키마/phase 히스토리는 §"extra_metrics.insights" 및 Docs/specs/SPEC-041-insight-delivery.md. parse_span_timeline() 등 순수 헬퍼. 절대 raise 안 함
│   └── comprehensive_report.py  # generate_comprehensive_html_report(monitor) / generate_html_from_result_file(rf) — 단일 결과 HTML 리포트(agent-eval gate 저장·대시보드 export 공용) · generate_comparison_html_report(). _build_* 헬퍼가 insights와 동일 내용 렌더. _effective_fail(): not success 또는 acc<0.7 또는 comp<0.4
└── serve/
    ├── server.py          # FastAPI 대시보드. create_app이 results_dir를 Path로 강제
    ├── templates/dashboard2.html.j2  # /dashboard 유일 템플릿. File Compare 탭(group_by · Pairwise Judge · Export HTML) + Improve 탭(baseline 유무로 top_detail_deltas ↔ component_shortfalls 렌더)
    └── routers/           # alerts · anomaly · config · conversation · cost · data · diagnose · export · feedback · golden · stream · transparency · webhook. data.py: list_results/compare_results. diagnose.py: GET /api/diagnose/{file_id}. export.py: GET /html/compare (/html/{file_id}보다 먼저 등록)
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

Gate A–G results stored under `extra_metrics.harness_groups` in JSON result files.
결과 JSON 최상위에 `schema_version`("1.1", SPEC-041 P4.3) — 소비자가 필드 형태 변화에 대응하도록. breaking change 시 major 증가.

**`extra_metrics.insights`** — machine-readable insight layer (L5/L6). `reporting/insights.py::build_insights(current, baseline=None, *, recommendation_log_path=None, experiments_log_path=None, with_experiment_metadata=False, repo_path=".", narrator=None, fixer=None, explainer=None, targets=None, history_dir=None, current_file=None, reference=None, cohort=None, cohort_metric="tcr", partial=False)` re-shapes existing verdicts (`rca.diagnose()`, `utils.confidence`, `ontology.metric_registry`, the `gates/*` aggregates, `rca.recommendation_tracking`/`verify`) into one JSON-serializable dict. **No new scoring formulas. Never raises** — a section that fails to compute is omitted or `null`.

- **Attached / served by:** `monitor.save_to_file()` → `extra_metrics.insights`; `serve/routers/diagnose.py` → `result["insights"]` (dashboard Improve tab); consumed by `cli/gate.py` (`--digest`, `--fail-on-case-regression`, `--max-review-high`, `--notify`). The static HTML report renders the same content via its own `_build_*` helpers (content parity — `insights` is the machine channel).
- **Partial / mid-run (SPEC-041 P50):** `build_insights(current, partial=True)` returns only the cheap baseline-free subset — `detection_mode:"partial"`, `running_verdict{decisive, verdict:ready|not_ready|undecided, pass_rate_ci_pct, gates_below_target, reason}` (Wilson CI on the binary pass-rate vs the TCR target + "all measured gates at bar"), plus `verdict`/`readiness`/`gate_findings`/`failure_clusters`/`security_*`/`calibration`/`narrative`. `PerformanceMonitor.running_insights()` / `.should_early_stop()` → `(stop, running_verdict)` wrap it for early-stop in an eval loop (advisory; caller breaks).
- **Schema is the contract:** `agent_evaluator/schemas/insights.schema.json` (Draft 2020-12; every object `additionalProperties:true` for forward-compat; nullable sections typed `["object"|"array","null"]`). `tests/test_insights_schema.py` validates several scenarios. Result JSON also carries top-level `schema_version` ("1.1"); bump major on a breaking field-shape change.
- **Hooks (opt-in, never auto-applied):** `narrator=Callable[[insights_dict], str]` replaces the deterministic `narrative`; `fixer=Callable[[payload], dict|None]` replaces `recommendations[].proposal`; `explainer=Callable[[payload], dict|None]` replaces `failure_explanations` (claim-level); `targets` (dict from `utils.targets.load_targets()`, or the auto-loaded `.aoo/targets.json`) makes `verdict`/`readiness` measure against the user's per-gate/TCR bar instead of 0.7. Bad return / exception → deterministic fallback.

Provenance (SPEC-041 P51): `verdict.next_actions[]`, `readiness.fix_plan[]` and `recommendations[]` each carry a `derived_from` naming the signal they came from (`{source: failure_cluster|gate_component_shortfall|gate_score|gate_status|security_finding, …}`).

Top-level keys (`build_insights()` output): `schema_version` · `detection_mode` · `verdict` · `narrative` · `narrative_audit` · `briefs` · `readiness` · `reference_frame` · `threshold_sensitivity` · `metric_confidence` · `uncertainty_budget` · `metric_signal` · `judge_robustness` · `evaluator_trust` · `review_queue` · `gate_findings` · `failure_clusters` · `failure_segments` · `failure_triggers` · `failure_taxonomy` · `ablation_hints` · `contrast_pairs` · `failure_explanations` · `failure_lineage` · `regression_attribution` · `improvement_priors` · `recommendations` (`[].proposal` · `[].prior`) · `latency_budget` · `efficiency_opportunities` · `rag_localization` · `slice_analysis` · `metadata_slices` · `multiplicity_audit` · `sample_guidance` · `reproducibility_manifest` · `cost_economics` · `calibration` · `security_findings` · `security_posture` · `score_breakdowns` · `trajectories` · `experiments` · `conversation` · `multiagent` · `eval_set_quality` (`.capability_coverage` · `.contamination` · `.targeted_additions`) · `golden_health` · `eval_representativeness` · `cohort_comparison` · `trace_diffs` · `longitudinal` · `insight_changes` · `freshness` · `change_attribution` · `nondeterminism` · `shared_cause_explanations` · `newly_unmeasured_gates` · `experiment_metadata`.

**Adding / changing an insight section:** (1) add/adjust the `_*_section` in `reporting/insights.py` (pure, never raises, deterministic — seed any RNG); (2) wire it into the `build_insights()` `out` dict (or the post-dict block for sections that read other sections); (3) update `insights.schema.json` + a `tests/test_insights_schema.py` scenario; (4) render it in `comprehensive_report.py` (`_build_*` + both `parts` lists + `_TOC_LABELS`) and, if relevant, the dashboard Improve tab; (5) document the phase in **`Docs/specs/SPEC-041-insight-delivery.md`** (full field-by-field description + phase history lives there, not here).

For the field-by-field description of every key, the `_build_*` render surfaces, the dashboard panels, the CLI wiring, and the P7–P42 phase history, see **`Docs/specs/SPEC-041-insight-delivery.md`**.

### Native Tracker → Gate Score Contribution (`_compute_harness_groups`)

| Tracker | Gate | 기여 방식 | 조건 |
|---------|------|-----------|------|
| `TaskCompletionTracker` | A, C | `_a_vals[0]` (TCR 컴포넌트), `_rel_vals` | always |
| `AccuracyEvaluator` | **A** | `_a_vals[0]` 블렌딩 (`0.6×TCR + 0.4×Accuracy`) | `_evaluations` count > 0 |
| `ResponseQualityEvaluator` | **A** | `_a_vals` 추가 (relevance+completeness 평균 / 5, 0→1 정규화) | quality dims 측정 시 |
| `LatencyTracker` | D | `_perf_vals` | always |
| `TokenEconomyTracker` | — | (gate score 미기여) | 토큰 비용 추적·보고 전용 |
| `HallucinationDetector` | **C + G** | `_rel_vals`, `_obs_vals` | LLM Judge faithfulness 없을 때 폴백 (`1 − rate`) |
| `LLMJudge` (faithfulness) | **C** | `_rel_vals` | per-task faithfulness 기록 시 우선 적용 (`score / 5` 정규화); HallucinationDetector 대체 |
| `RetryCorrectionTracker` | — | (gate score 미기여) | 재시도 횟수·패턴 추적 전용 |
| `ToolCallAnalyzer` | G | `_obs_vals` — `success_rate / 100` (0→1 정규화) | tool_calls 기록 시 |
| `WorkflowExecutionTracker` | — | (gate score 미기여) | chain_steps 추적·분석 전용 |
| Security Trackers (5) | E | `_all_e_scores` | `enable_security_metrics=True` |
| `AgentCoordinationTracker` | F | `_f_vals` — `calculate_coordination_score().overall_score / 10` (0→1 정규화) | agent_interactions 기록 시 |
| `ToolSelectionTracker` | F | `_f_vals` — `avg_f1_score / 100` (0→1 정규화) | expected_tools 지정 시 |

> **Gate A 가중치 구조**: `_a_score = gate_a_tcr_weight × _a_vals[0] + (1 − gate_a_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_a_tcr_weight=0.4` — `PerformanceMonitor(gate_a_tcr_weight=...)` 으로 조정 가능.  
> **Gate B 가중치 구조**: `gate_b_loop_weight > 0.0` 이면 루프 점수에 가중치 부여, `0.0`(기본값)이면 가용 지표 단순 평균.  
> 기본값 `gate_b_loop_weight=0.0` — `PerformanceMonitor(gate_b_loop_weight=...)` 으로 조정 가능.  
> **Gate C 가중치 구조**: `_rel_score = gate_c_tcr_weight × _rel_vals[0] + (1 − gate_c_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_c_tcr_weight=0.4` — `PerformanceMonitor(gate_c_tcr_weight=...)` 으로 조정 가능.  
> Gate B details에 `avg_goal_alignment` / `avg_plan_coherence`가 표시되지만, 이는 Gate A 계산값을 재참조하는 진단용이며 Gate B **점수에는 포함되지 않는다**.  
> **`AgentCoordinationTracker` 스케일**: `calculate_coordination_score().overall_score`는 0–10 스케일 → Gate F에서 `/10`으로 정규화.  
> **`ConsensusConfig.consensus_method`**: `"majority"` = 동의 쌍 비율; `"unanimity"` = 모든 쌍 동의 시만 1.0, 아니면 0.0; `"weighted"` = `agent_weights` 기반 가중 비율.  
> **`eval_conflict_resolution` 충돌 카운팅**: `agent_interactions`가 있으면 interaction 기반으로만 집계, 없으면 response 텍스트 폴백 (이중 카운팅 방지).  
> **RCA 상호참조(Gate F ↔ Gate B)**: Gate F(`gate_f_multiagent`)와 Gate B(`gate_b_behavioral`)는 서로를 참조하지 않는 완전 독립 슬라이스지만, 멀티에이전트 배포에서 둘 다 동시에 낮다면 조율 실패라는 같은 근본원인일 확률이 높다. Gate F 점수가 낮을 때는 `harness_groups.B.details.deadlock_by_type`/`deadlock_count`도 함께 확인할 것 — Gate B의 데드락이 Gate F의 낮은 `avg_conflict_resolution`/`coordination_score`를 설명하는 경우가 흔하다. 반대로 Gate C(신뢰성)와 Gate D(성능)가 동시에 하락했다고 해서 원인이 하나(예: SLA)라고 성급히 가정하지 말 것 — 같은 배포에 여러 변경이 우연히 겹친 경우가 더 흔하므로, `harness_groups.C.details.sla_breach_rate`와 `harness_groups.D.details.sla_window_penalty`/`sla_budget_penalty`를 먼저 대조해 실제로 SLA가 두 Gate 모두의 원인인지부터 확인한다.

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
    judge_model=None,          # auto-determined from API key
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
> the only reserved value.

### Harness Config in Decorator

```python
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    InstructionConfig, LoopDetectionConfig, SLAConfig, ExplainabilityConfig,
)

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### EvalMetadata — Injecting Metadata from Inside the Function

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

### Context Manager

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

# Accessing LLMJudge results from monitor
summary = monitor.llm_judge.get_summary()
# → {"avg_scores": {"overall": float, "criteria_scores": {...}}, "sample_count": int}
```

### create_taskresult Helper

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
#              "threshold": float, "not_measured": bool (score=None일 때만),
#              "insufficient_data_warnings": list[str] (있을 때만)}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}

# Gate별 개별 임계값 + 미측정 Gate 강제 실패(둘 다 기본 False/미지정 시 기존 동작과 100% 동일)
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],
    group_thresholds={"E": 0.95},   # Security는 더 엄격하게 — QuickEval.gate(gate_thresholds=...)/
                                     # CLI --gate-thresholds와 동일 개념을 이 클래스에도 대칭 추가
    strict_required=True,            # required_groups에 명시한 Gate가 score=None(설정 자체를 안 함)이면
                                      # 실패 처리 — 기본값(False)은 "꺼진 Gate는 조용히 통과"인 기존 동작 유지
)
```

> **주의**: `HarnessEvaluationGate.evaluate()`(Python API), `QuickEval.gate()`, `cli/gate.py`(`agent-eval gate`)는
> Gate A-G 임계값 판정을 세 곳에서 각각 호출하는 서로 다른 진입점이다 — `_compute_gate_regressions()`
> (베이스라인 회귀 판정 공식)와 `gates/base.py::evaluate_gate_scores()`(Gate별 score/threshold/status →
> passed 판정 루프)를 셋 다 공유한다. 남은 차이는 진입점별 고유 기능뿐이다(`HarnessEvaluationGate`의
> `strict_required`, CLI의 `--baseline-version`/`--golden-set`). 세 진입점 모두 `score is None`인
> Gate는 기본적으로 통과 처리한다(`HarnessEvaluationGate`는 `strict_required=True`로만 opt-out 가능,
> 나머지 둘은 항상 통과). 판정 루프 자체(`evaluate_gate_scores()`)를 고치면 세 곳 모두 자동으로
> 반영되지만, 진입점별 고유 기능을 바꿀 때는 해당 진입점만 확인하면 된다.

---

## Valid Parameter Reference

### PerformanceMonitor Valid Parameters

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

### @agent_eval Valid Parameters

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

## Gate A Tracker Attribution (Common Mistakes)

| Tracker | Attribution | Notes |
|---------|-------------|-------|
| `TaskCompletionTracker` | Gate A + C | `_a_vals[0]` TCR 컴포넌트 직접 기여 |
| `AccuracyEvaluator` | **Gate A** | `_a_vals[0]` 블렌딩 — `0.6×TCR + 0.4×Accuracy` (별도 항목이 아님) |
| `ResponseQualityEvaluator` | **Gate A** | relevance + completeness 평균 / 5 → `_a_vals` 추가 항목 |
| `HallucinationDetector` | **Gate C + G** | **not** Gate A |

**GoalAlignmentConfig 주의사항**: 기본값 `ignore_no_tool_tasks=True` — 도구 호출이 없는 태스크는 goal_alignment 평가에서 제외된다. QA·대화형 에이전트처럼 tool을 호출하지 않는 경우 `avg_goal_a = None`이 되어 Gate A 점수에 전혀 반영되지 않는다. 비도구 에이전트에 GoalAlignmentConfig를 사용하려면 `ignore_no_tool_tasks=False`로 설정해야 한다.

**AccuracyEvaluator `task_type` 매핑**: `"coding"` → `"code_generation"`으로 자동 정규화되어 AST 비교 평가가 적용된다. 두 값 모두 `_code_accuracy`로 라우팅된다.

---

## Coding Conventions

- **Formatter:** ruff, line-length=100
- **Python target:** 3.8+ (f-string, dataclass, typing)
- **Type hints:** required for all public functions; comment required when using `Any`
- **Docstrings:** include Args / Returns / Example sections
- **Error handling:** optional dependencies via `try/except ImportError`
- **Zero-division:** guard required in all ratio calculations
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
2. **Harness independence** — 33 Configs defined in `gates/gate_x/configs.py`, aggregated in `monitor.py`
3. **Tracker isolation** — each tracker must be independently testable
4. **Minimal side effects** — no `sys.path`, `os.chdir()`, or global state modification
5. **Security metric isolation** — security trackers are opt-in due to performance impact
6. **Serve separation** — `serve/` is optional FastAPI; core logic must not depend on it

---

## Known Dependency Constraints

| Item | Status | Note |
|------|--------|------|
| `ragas>=0.4.0` | ✅ | EvaluationDataset, SingleTurnSample API supported |
| `[crewai,autogen]` pydantic conflict | 🟡 | Silently downgrades to pydantic 2.11.x |
| `arize-phoenix>=15.4.0` | ✅ | pydantic-ai compatibility resolved (previous `<14.7.0` pin removed) |
| `AnswerRelevancy` embeddings | 🟡 | Auto-configured only with OpenAI key |

---

## Testing

**166 files, 4,700+ test functions** in `tests/`.

```bash
pytest  # configured in pyproject.toml (testpaths, cov)
```

Note: `agent_evaluator/utils/transparency_manager.py` contains `TestTransparencyManager` — a **production class**, not a test file.

`agent_evaluator/utils/confidence.py` (SPEC-041 P5·P10·P14·P22) — 단일 run 지표의 신뢰구간·표본 적정성·판정 확신도 순수 함수(stdlib만, numpy 무의존, seed 고정 결정적): `wilson_interval` · `bootstrap_mean_ci` · `bootstrap_diff_ci`(P10) · `welch_t_p`(P22, Welch t-검정 정규근사 p-value, scipy 무의존) · `required_n_for_halfwidth` · `mde_two_proportions`(P10) · `verdict_confidence`(P14: `judge_trust` 인자). 소비: `reporting/comprehensive_report.py` · `reporting/insights.py` · `cli/abtest.py`.

---

## Accuracy Evaluation (AccuracyEvaluator)

| Metric | Weight | Method |
|--------|--------|--------|
| Token Overlap | 40% | F1 token matching |
| Jaccard Similarity | 30% | Set intersection/union |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | Levenshtein |

- `code_generation`/`coding`: 1.0 on successful AST parse
- `tool_use`: 0.6 if `tool_calls` is empty
