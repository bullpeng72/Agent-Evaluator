# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 0.9.8 (Beta) | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

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
agent-eval gate result.json --baseline-version v2-cot --fail-on-regression 10   # per-version baseline (SPEC-025)
agent-eval gate result.json --golden-set data/golden_datasets/golden_1.json --fail-on-golden-regression  # golden-set gate, exit 3 (SPEC-025)
agent-eval dataset build --source results/ --max-cases 30 # golden dataset
agent-eval monitor                                        # Arize Phoenix + OTLP
agent-eval opencode install                               # LiveGuardrail OpenCode plugin (--global/--force)
agent-eval opencode install --with-violation-search       # + register search_violations MCP server (requires [mcp] extra)
agent-eval trend results/ --fail-on-regression            # trend analysis
agent-eval trend results/ --output-json trend.json

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

### Key Files

```
agent_evaluator/
├── decorators.py          # agent_eval · batch_eval · conversation_eval + Harness Config dataclasses
│                          # (SPEC-000 완료(2026-07-02) — 33개 Config 전부 gates/gate_x/configs.py로
│                          #  이관, decorators.py에는 re-export만 남음)
│                          # EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder
├── gates/                 # SPEC-000: Gate 단위 패키지 (Strangler Fig 이관 완료 — A~G 전체 7개 Gate)
│   ├── base.py            # 전 Gate 공유 인프라 — _min_sample_warning · _status · _g
│   ├── shared_metrics.py  # SPEC-018: RunningAverage 등 7개 running-aggregate 원시 타입 + Gate별 8개 SharedAgg 클래스
│   ├── live_guardrail.py  # SPEC-019: LiveVerdict · LiveGuardrail — 배치 Gate와 동일한 Behavioral/Security
│   │                       #  체크를 실행 전 단일 tool call 단위로 동기 호출
│   │                       #  SPEC-030: record_blocked_attempt() — check_before_tool_call()이 block=True를
│   │                       #  반환한 시도를 호출자가 명시적으로 감사 이력(blocked_violations)에 기록
│   │                       #  SPEC-031: record_tool_call(output=...) — success/exit_code/stdout/stderr
│   │                       #  옵트인 전달, max_tool_output_chars로 truncate. 미지정 시 회귀 없음
│   │                       #  SPEC-032: team_concurrency=TeamConcurrencyConfig(...) — 생성자 시점 1회
│   │                       #  로드한 .aoo/claims.jsonl로 read/edit/write 스코프 겹침 자동 차단
│   │                       #  (bash 제외), refresh_team_claims()로 수동 재조회
│   │                       #  SPEC-035: branch_guard=BranchGuardConfig(...) — 생성자 시점 1회 조회한
│   │                       #  현재 git 브랜치가 protected_branches(기본 main/master)이거나
│   │                       #  require_branch_prefix와 불일치하면 git commit/push 자동 차단(fail-open)
│   ├── team_concurrency.py # SPEC-032: TeamConcurrencyConfig · load_active_claims() · check_scope_claim()·
│   │                       #  append_claim() — Evaluator_Examples/ch28_local_ade_loop.py 예제 전용
│   │                       #  코드였던 클레임 로그 파싱 로직을 재해석 없이 SDK로 승격
│   │                       #  SPEC-034: audit_claims() — load_active_claims()/_scopes_overlap() 재사용해
│   │                       #  TTL 초과·겹치는 active 클레임을 CI가 소비할 위반 리스트로 반환(sys.exit 없음)
│   │                       #  SPEC-036: TeamConcurrencyConfig.owner — 지정 시 developer==owner인
│   │                       #  자기 자신의 클레임을 충돌 후보에서 제외(미지정 시 옛 동작 그대로 보존)
│   ├── branch_guard.py     # SPEC-035: BranchGuardConfig · get_current_branch() · is_branch_protected() ·
│   │                       #  matches_git_mutation() — Ch28 §28.2 "전용 브랜치" 그라운드 룰(지금까지
│   │                       #  체크리스트로만 존재)을 LiveGuardrail이 실행 전 자동으로 강제
│   ├── gate_a_goal/       # Gate A(Goal Achievement) — 완료
│   │   ├── configs.py      # InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig ·
│   │   │                   # ContextRetentionConfig · KnowledgeRetentionConfig
│   │   ├── evaluators.py   # eval_instruction_adherence · eval_goal_alignment · eval_plan_coherence ·
│   │   │                   # eval_context_retention · eval_subtask_completion · eval_knowledge_retention
│   │   │                   # (+ Gate A 전용 private 헬퍼: _is_fact_retained_in_text · _kr_strip_particle 등)
│   │   └── aggregate.py    # Gate A 집계 로직 (TCR+AccuracyEvaluator 블렌딩+ResponseQualityEvaluator;
│   │                       #  details에 avg_goal_alignment/avg_plan_coherence 노출 — Gate B가 진단용 재참조)
│   ├── gate_b_behavioral/ # Gate B(Behavioral Integrity) — 완료
│   │   ├── configs.py      # LoopDetectionConfig · StateConsistencyConfig · DeadlockConfig ·
│   │   │                   # ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig
│   │   ├── evaluators.py   # eval_loop_detection · eval_state_consistency · eval_deadlock · eval_scope ·
│   │   │                   # eval_tool_parameter_safety · eval_context_window (+ _normalize_agent_interactions)
│   │   │                   # SPEC-033: _extract_decoded_candidates() — ToolParameterSafetyConfig
│   │   │                   #  (decode_encodings=True) 옵트인 시 base64/hex로 인코딩된 위험 명령을
│   │   │                   #  디코드해 기존 dangerous_patterns로 재매치(새 탐지 규칙 아님, printable
│   │   │                   #  90% 필터로 오탐 방지, max_depth=2까지 재귀)
│   │   └── aggregate.py    # Gate B 집계 로직 (loop+state_consistency+deadlock+scope+tps+context_window;
│   │                       #  avg_goal_alignment/avg_plan_coherence는 Gate A에서 파라미터로 전달받아 진단용 재참조)
│   ├── gate_c_reliability/ # Gate C(Reliability) — 완료
│   │   ├── configs.py      # ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig ·
│   │   │                   # RetryConsistencyConfig · IdempotencyConfig
│   │   ├── evaluators.py   # eval_fault_tolerance · compute_reproducibility_score · eval_graceful_degradation ·
│   │   │                   # eval_retry_consistency · eval_idempotency
│   │   └── aggregate.py    # Gate C 집계 로직 (TCR+SLA breach+reproducibility+fault_tolerance+
│   │                       #  graceful_degradation+retry_consistency+idempotency+LLM faithfulness/hallucination).
│   │                       #  compute_sla_shared_data(tasks)가 SLA 공유 데이터(Gate D가 소비)의 원천;
│   │                       #  compute()는 (group_dict, shared_raw) 튜플 반환 — shared_raw에 반올림 없는
│   │                       #  hall_rate/avg_llm_faithfulness를 담아 Gate G가 재사용
│   ├── gate_g_observability/ # Gate G(Observability) — 완료
│   │   ├── configs.py      # ObservabilityConfig · ExplainabilityConfig · ErrorDiagnosisConfig ·
│   │   │                   # LatencyAttributionConfig
│   │   ├── evaluators.py   # eval_observability · eval_explainability · eval_error_diagnosis ·
│   │   │                   # eval_latency_attribution
│   │   └── aggregate.py    # Gate G 집계 로직 (tool_coverage+hallucination+observability+
│   │                       #  explainability+error_diagnosis+latency_attribution). hall_rate/
│   │                       #  avg_llm_faithfulness는 Gate C의 shared_raw를 파라미터로 전달받음.
│   │                       #  monitor.py는 self.tool_analyzer(ToolCallAnalyzer)를 전달 — SPEC-011에서
│   │                       #  이전의 존재하지 않는 속성명(self.tool_call_analyzer) 오탈자를 수정,
│   │                       #  도구 호출이 있는 세션에서 tool_coverage가 처음으로 실제 값을 반환함
│   ├── gate_f_multiagent/ # Gate F(Multi-Agent Coordination) — 완료
│   │   ├── configs.py      # ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig
│   │   ├── evaluators.py   # eval_consensus · eval_propagation · eval_role_adherence · eval_conflict_resolution
│   │   └── aggregate.py    # Gate F 집계 로직 (monitor.py가 위임 호출)
│   ├── gate_e_security/   # Gate E(Security Boundary) — 완료
│   │   ├── configs.py      # ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig
│   │   ├── evaluators.py   # eval_threat_severity · eval_compliance · eval_threat_response (+ _PII_PATTERNS)
│   │   └── aggregate.py    # Gate E 집계 로직 (5개 보안 트래커 + CVSS + compliance + threat_response)
│   └── gate_d_performance/ # Gate D(Performance Contract) — 완료
│       ├── configs.py      # SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig
│       ├── evaluators.py   # eval_sla · eval_efficiency · eval_resource_budget
│       └── aggregate.py    # Gate D 집계 로직 (latency+efficiency+budget+TTFT+cost predictability;
│                           #  SLA 공유 데이터는 gate_c_reliability.aggregate.compute_sla_shared_data()에서 전달받음)
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError hierarchy
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker, TaskResult, EvaluationReport, TaskType
│   │   ├── layer1.py      # Layer 1 trackers
│   │   ├── layer2.py      # Layer 2 trackers
│   │   ├── security.py    # Security trackers
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator) · SPEC-026:
│   │   │                  #  rehydrate_from_storage() — SQLite 이력 재생으로 재시작 생존 이상탐지 기준선
│   │   │                  #  SPEC-027: agent_version="auto" — 캐싱된 self._git_commit 앞 8자 +
│   │   │                  #  미커밋 변경(git diff HEAD) 해시 접미사로 자동 태깅, 읽기 전용
│   │   │                  #  monitor.agent_version 프로퍼티로 최종 해석값 노출
│   │   │                  #  SPEC-029: iteration_note — agent_version="auto"의 불투명한 dirty-hash
│   │   │                  #  태그에 사람이 읽을 수 있는 한 줄 메모를 붙임. _build_lineage()가
│   │   │                  #  extra_metrics.lineage.iteration_note로 그대로 실어 보냄(새 계산 없음)
│   │   ├── conversation.py# ConversationSession, ConversationMetrics, ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas integration)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native) · SPEC-025: judge_pairwise() — A/B 응답 맞대결
│   │                       #  (swap-check로 포지션 편향 완화), self.pairwise_results에 별도 축적
│   ├── llm_judge_calibration.py  # SPEC-022: LLMJudgeCalibration — judge-vs-human 골든셋 일치도
│   │                       #  (MAE · Pearson · Cohen's weighted kappa, scikit-learn 무의존 자체 구현)
│   ├── live_guardrail_stdio.py   # SPEC-019: LiveGuardrail용 범용 stdio 브리지 (non-Python 호출자용)
│   ├── live_guardrail_report.py  # SPEC-019: SQLite 기반 배치 리포트 브리지 (다중 세션 동시 기록)
│   │                       #  SPEC-028: tool_calls를 TaskResult.tool_calls로 승격(Gate G) ·
│   │                       #  execution_time/success 옵트인 필드(Gate D/A, success 미지정 시
│   │                       #  completion_score=0.5 중립값 — None은 TaskResult 검증에 막혀 불가) ·
│   │                       #  agent_version 기본값 "auto"(SPEC-027 자동 태깅 연결)
│   ├── violation_search_mcp.py   # SPEC-024: search_violations() 도구 1개를 노출하는 stdio MCP 서버
│   │                       #  (옵트인 `pip install "agent-evaluator[mcp]"`) — opencode mcp add로 등록
│   │                       #  SPEC-030: include_blocked=True로 호출 — 도구 docstring이 원래
│   │                       #  약속한 "차단된 이력" 검색을 실제로 이행, [차단됨]/[관찰됨] 접두어
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   ├── dspy_integration.py
│   └── pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent — 6개 체크(SPEC-026: feedback_negativity
│                          #  6번째로 추가, monitor.feedback_tracker의 is_positive 신호 재사용)
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler
│                          # SPEC-026: dispatch_anomaly_events() — AnomalyEvent를 type별 캐시된
│                          #  AlertRule(self._anomaly_rules, evaluate()의 self._rules와 분리)로 발송
├── storage/               # SPEC-016: sqlite_backend.py — save_tasks_to_db · load_tasks_from_db
│                          # (PerformanceMonitor(storage_backend="sqlite") 옵트인 대안, 기본값 "json")
│                          # SPEC-024: violation_search(FTS5, additive) + search_violations() —
│                          #  Gate B/E 위반 이력 전문 검색(ctx의 OpenCode 세션 미색인 한계 우회)
│                          # SPEC-030: blocked_violations(FTS5, additive) — 완전 차단돼 tasks/
│                          #  violation_search 어디에도 안 남는 시도의 감사 이력. search_violations
│                          #  (..., include_blocked=True)로 관찰 모드 위반과 함께 조회(blocked 필드로 구분)
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware — SPEC-026: anomaly_detector/
│                          #  anomaly_scan_interval/anomaly_alert_handler로 기존 flush 스레드에
│                          #  주기적 이상탐지 스캔 + AlertEngine.dispatch_anomaly_events 자동 연결
├── cli/main.py            # CLI entry point (subcommands: init·check·version·dashboard·gate·dataset·monitor·opencode·trend)
│                          # opencode install --with-violation-search(SPEC-024): search_violations
│                          #  MCP 서버 자동 등록(옵트인)
│                          # gate --baseline-version/--golden-set/--fail-on-golden-regression(SPEC-025):
│                          #  버전별 독립 baseline + 골든셋 회귀 게이트(exit 3)
├── reporting/
│   └── comprehensive_report.py  # generate_comprehensive_html_report(monitor)·
│                          #  generate_html_from_result_file(rf) — 단일 결과 HTML 리포트
│                          #  (agent-eval gate 저장/대시보드 export_html 공용).
│                          #  SPEC-025: generate_comparison_html_report(compare_result) —
│                          #  compare_results()의 반환 dict를 그대로 렌더링(새 비교 로직 없음)
└── serve/
    ├── server.py          # FastAPI dashboard (108 routes)
    ├── templates/
    │   └── dashboard2.html.j2  # `/dashboard` 라우트(유지 대상 — dashboard.html.j2는 레거시,
    │                      #  마이그레이션 후 삭제 예정). File Compare 탭: SPEC-025 group_by
    │                      #  드롭다운·⚖️ Pairwise Judge 서브탭·📄 Export HTML 버튼
    │                      #  SPEC-029: Metric Comparison 표 상단에 agent_version/iteration_note
    │                      #  메타데이터 행 — 새 API 호출 없이 이미 로드된 compareData에서 직접 렌더링
    └── routers/           # alerts · anomaly · config · conversation · cost · data · export
                           # feedback · golden · stream · transparency · webhook
                           # data.py: list_results(prompt_version=/agent_version=)·
                           #  compare_results(group_by=/pairwise=)(SPEC-025)
                           # export.py: GET /html/compare(SPEC-025) — ids 또는 group_by +
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

> **`agent_version="auto"` (SPEC-027)**: reserved sentinel — resolves to the current git commit's short
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

# SPEC-006: async path + concurrency/backoff (max_concurrent_judge_calls=5, max_retries=3 defaults)
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
# result: {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}
```

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
prompt_version, agent_version
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
2. **Harness independence** — 33 Configs defined in `decorators.py`, aggregated in `monitor.py`
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

**91 files, 3,486+ test functions** in `tests/`.

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
