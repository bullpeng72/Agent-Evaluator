# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 1.0.0-rc.1 | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

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
agent-eval diagnose result.json --baseline baseline.json   # Gate regression RCA (not a CI gate, informational only)
agent-eval abtest v1.json v2.json --metric accuracy_score   # statistical A/B (Welch's t-test), not a CI gate
agent-eval abtest v1.json v2.json --sequential --tau 0.05   # mSPRT always-valid inference (safe to peek)
agent-eval abtest v1.json v2.json v3.json                   # 3+ files -> N-way + Benjamini-Hochberg FDR
agent-eval dataset build --source results/ --max-cases 30 # golden dataset
agent-eval monitor                                        # Arize Phoenix + OTLP
agent-eval opencode install                               # LiveGuardrail OpenCode plugin (--global/--force)
agent-eval opencode install --with-violation-search       # + register search_violations MCP server (requires [mcp] extra)
agent-eval opencode install --with-recommend-fix           # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval claude install                                 # LiveGuardrail Claude Code CLI hooks (--global/--force)
agent-eval claude install --with-violation-search         # + register search_violations MCP server (requires [mcp] extra)
agent-eval claude install --with-recommend-fix             # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval trend results/ --fail-on-regression            # trend analysis
agent-eval trend results/ --output-json trend.json
agent-eval claims add src/ --developer auto                # open a .aoo/claims.jsonl scope claim
agent-eval claims list                                     # show active claims
agent-eval claims release c-a1b2c3d4                       # release a claim
agent-eval claims audit --ttl-hours 8                      # CI: flag TTL-exceeded/overlapping claims

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
├── decorators.py          # agent_eval · batch_eval · conversation_eval
│                          # 33개 Harness Config는 gates/gate_x/configs.py에 정의되고 여기는 re-export만 함
│                          # EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder
├── gates/                 # Gate 단위 패키지 — A~G 전체 7개 Gate
│   ├── base.py            # 전 Gate 공유 인프라 — _min_sample_warning · _status · _g ·
│   │                       #  _gate_pass_verdict()(단일 Gate pass/fail 공식) ·
│   │                       #  evaluate_gate_scores()(HarnessEvaluationGate·QuickEval.gate()·
│   │                       #  cli/gate.py가 공유하는 Gate 판정 루프 — 아래 HarnessEvaluationGate 참고)
│   ├── shared_metrics.py  # RunningAverage 등 7개 running-aggregate 원시 타입 + Gate별 8개 SharedAgg 클래스
│   ├── live_guardrail.py  # LiveVerdict · LiveGuardrail — 배치 Gate와 동일한 Behavioral/Security
│   │                       #  체크를 실행 전 단일 tool call 단위로 동기 호출
│   │                       #  record_blocked_attempt() — check_before_tool_call()이 block=True를
│   │                       #  반환한 시도를 호출자가 명시적으로 감사 이력(blocked_violations)에 기록
│   │                       #  record_tool_call(output=...) — success/exit_code/stdout/stderr
│   │                       #  옵트인 전달, max_tool_output_chars로 truncate. 미지정 시 회귀 없음
│   │                       #  team_concurrency=TeamConcurrencyConfig(...) — 생성자 시점 1회
│   │                       #  로드한 .aoo/claims.jsonl로 read/edit/write 스코프 겹침 자동 차단
│   │                       #  (bash 제외), refresh_team_claims()로 수동 재조회
│   │                       #  branch_guard=BranchGuardConfig(...) — 생성자 시점 1회 조회한
│   │                       #  현재 git 브랜치가 protected_branches(기본 main/master)이거나
│   │                       #  require_branch_prefix와 불일치하면 git commit/push 자동 차단(fail-open)
│   │                       #  tool_guard() 데코레이터 + live_guardrail_session() 컨텍스트
│   │                       #  매니저 — 도구 함수에 @tool_guard를 붙이면 세션 블록 안에서 호출될 때
│   │                       #  check_before_tool_call() → 실행 → record_tool_call()이 자동으로
│   │                       #  이어진다(새 탐지 로직 아님, 순수 적용 계층). 차단 시 GuardrailBlockedError
│   │                       #  (.verdict에 판정 담김), audit_blocked=True로 record_blocked_attempt()
│   │                       #  자동 연결, fail_closed=False(기본)면 세션 밖 호출을 RuntimeWarning만
│   │                       #  내고 가드 없이 통과(다른 fail_on_*와 반대로 fail-open이 기본값)
│   ├── team_concurrency.py # TeamConcurrencyConfig · load_active_claims() · check_scope_claim() ·
│   │                       #  append_claim() — .aoo/claims.jsonl 클레임 로그 파싱·기록
│   │                       #  audit_claims() — load_active_claims()/_scopes_overlap() 재사용해
│   │                       #  TTL 초과·겹치는 active 클레임을 CI가 소비할 위반 리스트로 반환(sys.exit 없음)
│   │                       #  TeamConcurrencyConfig.owner — 지정 시 developer==owner인
│   │                       #  자기 자신의 클레임을 충돌 후보에서 제외(미지정 시 옛 동작 그대로 보존)
│   │                       #  owner="auto" 예약 센티널 — resolve_owner()가 LiveGuardrail
│   │                       #  생성 시점에 git config user.name을 1회 조회해 치환(agent_version="auto"와
│   │                       #  동일 패턴), 조회 실패 시 예외 없이 None으로 폴백(기존 동작 유지)
│   ├── branch_guard.py     # BranchGuardConfig · get_current_branch() · is_branch_protected() ·
│   │                       #  matches_git_mutation() — "보호된 브랜치에 직접 커밋 금지" 같은 팀
│   │                       #  그라운드 룰을 LiveGuardrail이 실행 전 자동으로 강제
│   ├── gate_a_goal/       # Gate A(Goal Achievement)
│   │   ├── configs.py      # InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig ·
│   │   │                   # ContextRetentionConfig · KnowledgeRetentionConfig
│   │   ├── evaluators.py   # eval_instruction_adherence · eval_goal_alignment · eval_plan_coherence ·
│   │   │                   # eval_context_retention · eval_subtask_completion · eval_knowledge_retention
│   │   │                   # (+ Gate A 전용 private 헬퍼: _is_fact_retained_in_text · _kr_strip_particle 등)
│   │   └── aggregate.py    # Gate A 집계 로직 (TCR+AccuracyEvaluator 블렌딩+ResponseQualityEvaluator;
│   │                       #  details에 avg_goal_alignment/avg_plan_coherence 노출 — Gate B가 진단용 재참조)
│   ├── gate_b_behavioral/ # Gate B(Behavioral Integrity)
│   │   ├── configs.py      # LoopDetectionConfig · StateConsistencyConfig · DeadlockConfig ·
│   │   │                   # ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig
│   │   ├── evaluators.py   # eval_loop_detection · eval_state_consistency · eval_deadlock · eval_scope ·
│   │   │                   # eval_tool_parameter_safety · eval_context_window (+ _normalize_agent_interactions)
│   │   │                   # _extract_decoded_candidates() — ToolParameterSafetyConfig
│   │   │                   #  (decode_encodings=True) 옵트인 시 base64/hex로 인코딩된 위험 명령을
│   │   │                   #  디코드해 기존 dangerous_patterns로 재매치(새 탐지 규칙 아님, printable
│   │   │                   #  90% 필터로 오탐 방지, max_depth=2까지 재귀)
│   │   └── aggregate.py    # Gate B 집계 로직 (loop+state_consistency+deadlock+scope+tps+context_window;
│   │                       #  avg_goal_alignment/avg_plan_coherence는 Gate A에서 파라미터로 전달받아 진단용 재참조)
│   ├── gate_c_reliability/ # Gate C(Reliability)
│   │   ├── configs.py      # ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig ·
│   │   │                   # RetryConsistencyConfig · IdempotencyConfig
│   │   ├── evaluators.py   # eval_fault_tolerance · compute_reproducibility_score · eval_graceful_degradation ·
│   │   │                   # eval_retry_consistency · eval_idempotency
│   │   └── aggregate.py    # Gate C 집계 로직 (TCR+SLA breach+reproducibility+fault_tolerance+
│   │                       #  graceful_degradation+retry_consistency+idempotency+LLM faithfulness/hallucination).
│   │                       #  compute_sla_shared_data(tasks)가 SLA 공유 데이터(Gate D가 소비)의 원천;
│   │                       #  compute()는 (group_dict, shared_raw) 튜플 반환 — shared_raw에 반올림 없는
│   │                       #  hall_rate/avg_llm_faithfulness를 담아 Gate G가 재사용. sla_window_penalty/
│   │                       #  sla_budget_penalty도 이 함수가 계산해 Gate D로 전달하지만 Gate C 자신의
│   │                       #  details에는 sla_breach_rate/sla_breach_count만 노출되고 두 penalty 값
│   │                       #  자체는 노출되지 않는다 — 역추적하려면 harness_groups.D.details의
│   │                       #  sla_window_penalty/sla_budget_penalty/perf_score_pre_sla_penalty를 볼 것
│   ├── gate_g_observability/ # Gate G(Observability)
│   │   ├── configs.py      # ObservabilityConfig · ExplainabilityConfig · ErrorDiagnosisConfig ·
│   │   │                   # LatencyAttributionConfig
│   │   ├── evaluators.py   # eval_observability · eval_explainability · eval_error_diagnosis ·
│   │   │                   # eval_latency_attribution
│   │   └── aggregate.py    # Gate G 집계 로직 (tool_coverage+hallucination+observability+
│   │                       #  explainability+error_diagnosis+latency_attribution). hall_rate/
│   │                       #  avg_llm_faithfulness는 Gate C의 shared_raw를 파라미터로 전달받음.
│   │                       #  monitor.py는 self.tool_analyzer(ToolCallAnalyzer)를 전달한다 — 과거
│   │                       #  존재하지 않는 속성명(self.tool_call_analyzer)으로 참조하던 오탈자가 있었으니
│   │                       #  새 코드에서 이 이름을 다시 틀리지 않도록 주의. details의 "tool_coverage"는
│   │                       #  실제로는 ToolCallAnalyzer.get_efficiency_stats()["success_rate"](도구 호출
│   │                       #  성공률)다 — trace_continuity 등 "관측 커버리지"와는 다른 개념이므로
│   │                       #  ObservabilityConfig(check_trace_continuity=...)와 혼동하지 말 것
│   ├── gate_f_multiagent/ # Gate F(Multi-Agent Coordination)
│   │   ├── configs.py      # ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig
│   │   ├── evaluators.py   # eval_consensus · eval_propagation · eval_role_adherence · eval_conflict_resolution
│   │   └── aggregate.py    # Gate F 집계 로직 (monitor.py가 위임 호출)
│   ├── gate_e_security/   # Gate E(Security Boundary)
│   │   ├── configs.py      # ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig
│   │   ├── evaluators.py   # eval_threat_severity · eval_compliance · eval_threat_response (+ _PII_PATTERNS)
│   │   └── aggregate.py    # Gate E 집계 로직 (5개 보안 트래커 + CVSS + compliance + threat_response)
│   └── gate_d_performance/ # Gate D(Performance Contract)
│       ├── configs.py      # SLAConfig · EfficiencyConfig(fallback_reference_cost_per_completion —
│       │                   #  target_cost_per_completion 미설정 시 efficiency_ratio 폴백 정규화 기준
│       │                   #  비용. None(기본값)이면 cost_unit별 레거시 하드코딩값 tokens/time_ms=1000.0,
│       │                   #  usd=0.01 유지) · ResourceBudgetConfig · TTFTVariabilityConfig ·
│       │                   #  CostPredictabilityConfig
│       ├── evaluators.py   # eval_sla · eval_efficiency(fallback_reference_cost_per_completion을
│       │                   #  결과의 "_config" 서브딕셔너리에 실어 aggregate.py로 전달) · eval_resource_budget
│       └── aggregate.py    # Gate D 집계 로직 (latency+efficiency+budget+TTFT+cost predictability;
│                           #  SLA 공유 데이터는 gate_c_reliability.aggregate.compute_sla_shared_data()에서
│                           #  전달받음). details에 perf_score_pre_sla_penalty/sla_window_penalty/
│                           #  sla_budget_penalty(SLA 감점 역추적용)·efficiency_ratio_reference_cost
│                           #  (폴백 정규화 경로에서 실제 사용된 기준 비용) 노출
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError hierarchy
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker, TaskResult, EvaluationReport, TaskType
│   │   ├── layer1.py      # Layer 1 trackers
│   │   ├── layer2.py      # Layer 2 trackers
│   │   ├── security.py    # Security trackers
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator)
│   │   │                  #  rehydrate_from_storage() — SQLite 이력 재생으로 재시작 생존 이상탐지 기준선
│   │   │                  #  agent_version="auto" — 캐싱된 self._git_commit 앞 8자 +
│   │   │                  #  미커밋 변경(git diff HEAD) 해시 접미사로 자동 태깅, 읽기 전용
│   │   │                  #  monitor.agent_version 프로퍼티로 최종 해석값 노출
│   │   │                  #  iteration_note — agent_version="auto"의 불투명한 dirty-hash
│   │   │                  #  태그에 사람이 읽을 수 있는 한 줄 메모를 붙임. _build_lineage()가
│   │   │                  #  extra_metrics.lineage.iteration_note로 그대로 실어 보냄(새 계산 없음)
│   │   ├── conversation.py# ConversationSession, ConversationMetrics, ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas integration)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native) · judge_pairwise() — A/B 응답 맞대결
│   │                       #  (swap-check로 포지션 편향 완화), self.pairwise_results에 별도 축적
│   ├── llm_judge_calibration.py  # LLMJudgeCalibration — judge-vs-human 골든셋 일치도
│   │                       #  (MAE · Pearson · Cohen's weighted kappa, scikit-learn 무의존 자체 구현)
│   ├── live_guardrail_stdio.py   # LiveGuardrail용 범용 stdio 브리지 (non-Python 호출자용)
│   ├── live_guardrail_report.py  # SQLite 기반 배치 리포트 브리지 (다중 세션 동시 기록)
│   │                       #  tool_calls를 TaskResult.tool_calls로 승격(Gate G) ·
│   │                       #  execution_time/success 옵트인 필드(Gate D/A, success 미지정 시
│   │                       #  completion_score=0.5 중립값 — None은 TaskResult 검증에 막혀 불가) ·
│   │                       #  agent_version 기본값 "auto"(자동 태깅 연결)
│   ├── claude_code_hook.py       # Claude Code CLI 훅(PreToolUse/PostToolUse/SessionEnd) →
│   │                       #  LiveGuardrail 브리지. Claude Code 훅은 호출마다 별도 프로세스라
│   │                       #  메모리를 공유하지 않으므로(live_guardrail_stdio.py의 상주
│   │                       #  프로세스 모델과 다름), 세션별 상태 파일(.claude/.agent-evaluator/
│   │                       #  sessions/<id>.json)에 확정 tool_call 이력을 남기고 매 호출마다
│   │                       #  record_tool_call()로 재생(replay)해 판정 상태를 복원한다 — 새
│   │                       #  탐지 로직 없음, live_guardrail_stdio.build_guardrail()과
│   │                       #  live_guardrail_report.record_and_save()를 그대로 재사용.
│   │                       #  team_concurrency/branch_guard도 build_guardrail()이 다루는 키라
│   │                       #  guardrail_config.json에 채우면 그대로 지원된다(과거엔 미지원이었으나
│   │                       #  live_guardrail_stdio.py의 _CONFIG_CLASSES에 두 키가 등록되며 해소됨).
│   │                       #  예외는 항상 fail-open(판정 없음 반환) — 브리지 버그가 모든
│   │                       #  도구 호출을 막아버리면 안 되므로.
│   ├── violation_search_mcp.py   # search_violations() 도구 1개를 노출하는 stdio MCP 서버
│   │                       #  (옵트인 `pip install "agent-evaluator[mcp]"`) — opencode mcp add로 등록
│   │                       #  include_blocked=True로 호출하면 완전 차단된("관찰"이 아닌) 이력까지
│   │                       #  함께 검색, [차단됨]/[관찰됨] 접두어로 구분
│   ├── recommend_fix_mcp.py      # recommend_fix(gate, metric=None, value=None) 도구 1개를
│   │                       #  노출하는 stdio MCP 서버(옵트인, violation_search_mcp.py와 나란히
│   │                       #  등록) — ontology.metric_registry(GATE_GUIDANCE/NATIVE_METRIC_RULES/
│   │                       #  ANOMALY_METRIC_SUGGESTIONS)·ontology.mast_taxonomy(Gate F)를 그대로
│   │                       #  읽는 정적 지식 조회, 새 판정 로직 없음. 결과 파일 불필요 —
│   │                       #  rca.diagnose()(Gate F만 처방)와 달리 Gate A-G 전체에 답한다
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   ├── dspy_integration.py
│   └── pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent — 6개 체크(feedback_negativity가
│                          #  monitor.feedback_tracker의 is_positive 신호를 재사용)
├── ontology/              # 진단/추천 지식을 모으는 순수 데이터 레지스트리(PyYAML 등 외부
│                          #  의존성 없이 Python dataclass로 관리, core dependency 원칙 유지)
│                          # metric_registry.py — GATE_GUIDANCE(Gate 7종 라벨+안내문)·
│                          #  NATIVE_METRIC_RULES(절대 임계값 기반)·ANOMALY_METRIC_SUGGESTIONS
│                          #  (AnomalyDetector 상대편차 기반) — comprehensive_report.py의
│                          #  _build_recommendations()와 serve/routers/data.py의
│                          #  explain_anomaly_event()가 소비. rca.diagnose()와는 미연결
│                          #  (Gate F만 mast_taxonomy로 처방을 받음 — 아래 참고)
│                          # mast_taxonomy.py — MAST(Cemri et al., NeurIPS 2025, arXiv:2503.13657)
│                          #  14개 실패모드 원문 시드 데이터, Gate F(다중 에이전트) 전용.
│                          #  rca.diagnose()가 Gate F 감지 시 related_gate_f_metric으로 후보를
│                          #  붙인다(자동 판정 아님, HOTL 원칙상 후보 제시까지만)
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler
│                          # dispatch_anomaly_events() — AnomalyEvent를 type별 캐시된
│                          #  AlertRule(self._anomaly_rules, evaluate()의 self._rules와 분리)로 발송
├── storage/               # sqlite_backend.py — save_tasks_to_db · load_tasks_from_db
│                          # (PerformanceMonitor(storage_backend="sqlite") 옵트인 대안, 기본값 "json")
│                          # violation_search(FTS5) + search_violations() —
│                          #  Gate B/E 위반 이력 전문 검색
│                          # blocked_violations(FTS5) — 완전 차단돼 tasks/
│                          #  violation_search 어디에도 안 남는 시도의 감사 이력. search_violations
│                          #  (..., include_blocked=True)로 관찰 모드 위반과 함께 조회(blocked 필드로 구분)
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware — anomaly_detector/
│                          #  anomaly_scan_interval/anomaly_alert_handler로 기존 flush 스레드에
│                          #  주기적 이상탐지 스캔 + AlertEngine.dispatch_anomaly_events 자동 연결
├── cli/main.py            # CLI entry point (subcommands: init·check·version·dashboard·gate·
│                          #  diagnose·abtest·dataset·monitor·opencode·claude·trend·claims —
│                          #  서브파서는 각각 cli/gate.py·cli/diagnose.py·cli/abtest.py·
│                          #  cli/dataset.py·cli/monitor.py·cli/opencode.py·cli/claude.py·
│                          #  cli/trend.py·cli/claims.py에 위임)
│                          # opencode install --with-violation-search/--with-recommend-fix:
│                          #  각각 search_violations/recommend_fix MCP 서버 자동 등록(옵트인)
│                          # gate --baseline-version/--golden-set/--fail-on-golden-regression:
│                          #  버전별 독립 baseline + 골든셋 회귀 게이트(exit 3)
├── cli/claude.py          # claude install [--global/--force/--with-violation-search/
│                          #  --with-recommend-fix] — .claude/settings.json(또는 --global 시
│                          #  ~/.claude/settings.json)에 PreToolUse/PostToolUse/SessionEnd 훅을
│                          #  병합(기존 훅 보존, 재설치해도 중복 추가 안 됨) + 기본
│                          #  guardrail_config.json 복사. OpenCode installer(cli/opencode.py)와
│                          #  달리 훅 스크립트 자체는 파일 복사가 필요 없음(설치된 패키지를
│                          #  python -m agent_evaluator.integrations.claude_code_hook로 직접
│                          #  호출) — 재설치 보호 대상은 guardrail_config.json 하나뿐.
│                          #  SessionEnd 훅의 matcher는 도구 이름이 아니라 세션종료 사유를
│                          #  필터링하므로 PreToolUse/PostToolUse와 다른 matcher("*")를 쓴다 —
│                          #  실제로 이 차이를 놓쳐 배치저장이 발화 안 하는 회귀를 만들었다가
│                          #  라이브 테스트로 잡은 이력 있음(회귀 방지 테스트 존재).
├── cli/diagnose.py        # diagnose — agent_evaluator.rca.diagnose()를 감싸는 얇은 터미널
│                          #  출력 레이어(새 판정 로직 없음). CI 게이트 아님 — 항상 exit 0
│                          #  (결과 파일을 못 읽을 때만 exit 1), pass/fail 판정하지 않고
│                          #  후보 원인·근거만 출력(HOTL). --show-diff로 lineage.git_commit
│                          #  기반 실제 git diff까지 연결(§rca/ 참고)
├── cli/abtest.py          # abtest — QuickEval.ab_test()/ab_test_nway()/ab_test_sequential()을
│                          #  감싸는 얇은 터미널 레이어(새 통계 로직 없음). CI 게이트 아님 —
│                          #  유의성/효과크기/표본경고만 출력, pass/fail 판정 없음. 결과 JSON
│                          #  파일 2개 → Welch's t-test(--sequential 시 mSPRT), 3개 이상 →
│                          #  N-way + Benjamini-Hochberg FDR 보정으로 자동 전환. 파일 로딩은
│                          #  PerformanceMonitor.load_from_file()로 TaskResult를 복원한 뒤
│                          #  QuickEval._monitor에 주입 — 새 파싱 로직 없음
├── cli/claims.py          # claims add/list/release/audit — append_claim()/load_active_claims()/
│                          #  audit_claims()를 감싸는 얇은 터미널 래퍼, 새 판정 로직 없음
├── rca/                   # Gate 회귀 원인진단(RCA) + 개선 이력 추적 — Media/Book Part VII
│                          #  (Ch28–31)가 다루는 기능의 실제 구현. quick_eval.py/gates/base.py의
│                          #  기존 판정 로직을 재사용할 뿐 새 판정 공식은 만들지 않는다
│                          # diagnose.py — diagnose(current, baseline=None, ...): 3단계
│                          #  (감지→원인귀속→교차확인). _compute_gate_regressions()(기존 baseline
│                          #  회귀 공식) 재사용. Gate C·D 동시 감지 시 SLA 공유데이터로 공유원인
│                          #  체크. Gate F는 ontology.mast_taxonomy로 MAST 후보 추가(§ontology 참고)
│                          # experiment_metadata.py — derive_experiment_metadata(): 두 리포트의
│                          #  extra_metrics.lineage.git_commit을 대조해 순수 git 명령(diff --stat/
│                          #  log)만으로 코드 diff 해석 — gh CLI/GitHub API 미의존
│                          # verify.py — verify_recommendation_outcome(): 조치 적용 후 재평가
│                          #  결과가 실제로 개선됐는지 confirmed/refuted/inconclusive 판정
│                          # recommendation_tracking.py — record_/load_/summarize_
│                          #  recommendation_outcomes(): .aoo/claims.jsonl과 동일한 append-only
│                          #  JSONL 패턴으로 조치 이력 기록
├── reporting/
│   └── comprehensive_report.py  # generate_comprehensive_html_report(monitor)·
│                          #  generate_html_from_result_file(rf) — 단일 결과 HTML 리포트
│                          #  (agent-eval gate 저장/대시보드 export_html 공용).
│                          #  generate_comparison_html_report(compare_result) —
│                          #  compare_results()의 반환 dict를 그대로 렌더링(새 비교 로직 없음)
└── serve/
    ├── server.py          # FastAPI dashboard (111 routes)
    ├── templates/
    │   └── dashboard2.html.j2  # `/dashboard` 라우트(유지 대상 — dashboard.html.j2는 레거시,
    │                      #  마이그레이션 후 삭제 예정). File Compare 탭: group_by
    │                      #  드롭다운·⚖️ Pairwise Judge 서브탭·📄 Export HTML 버튼
    │                      #  Metric Comparison 표 상단에 agent_version/iteration_note
    │                      #  메타데이터 행 — 새 API 호출 없이 이미 로드된 compareData에서 직접 렌더링
    └── routers/           # alerts · anomaly · config · conversation · cost · data · diagnose
                           # export · feedback · golden · stream · transparency · webhook
                           # data.py: list_results(prompt_version=/agent_version=)·
                           #  compare_results(group_by=/pairwise=)
                           # diagnose.py: GET /api/diagnose/{file_id}(rca.diagnose() 호출,
                           #  baseline_id=/regression_threshold=/show_diff=) · GET /api/diagnose/
                           #  (recommendation_outcomes.jsonl 읽기) — 대시보드 🔧 Improve 탭이 소비
                           # export.py: GET /html/compare — ids 또는 group_by +
                           #  선택적 pairwise → generate_comparison_html_report(). `/html/{file_id}`
                           #  보다 먼저 등록해야 정적 경로가 파라미터 경로에 삼켜지지 않는다
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
prompt_version, agent_version, iteration_note
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

**116 files, 3,884+ test functions** in `tests/`.

```bash
pytest  # configured in pyproject.toml (testpaths, cov)
```

Note: `agent_evaluator/utils/transparency_manager.py` contains `TestTransparencyManager` — a **production class**, not a test file.

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
