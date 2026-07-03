# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 0.9.6 (Beta) | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Dev environment
pip install -e ".[dev]"
pip install -e ".[sdk]"       # dashboard + OTEL + LLMJudge + PDF (recommended)
pip install -e ".[examples]"  # all examples runnable (sdk + eval)

# CLI
agent-eval init                                           # API key setup wizard
agent-eval check                                          # config status
agent-eval --version                                      # version info
agent-eval dashboard                                      # FastAPI dashboard (port 8765)
agent-eval gate result.json --tcr 85 --accuracy 70        # CI/CD quality gating
agent-eval dataset build results/ --min-score 0.8         # golden dataset
agent-eval monitor                                        # Arize Phoenix + OTLP
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
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator)
│   │   ├── conversation.py# ConversationSession, ConversationMetrics, ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas integration)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native)
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   ├── dspy_integration.py
│   └── pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler
├── storage/               # SPEC-016: sqlite_backend.py — save_tasks_to_db · load_tasks_from_db
│                          # (PerformanceMonitor(storage_backend="sqlite") 옵트인 대안, 기본값 "json")
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware
├── cli/main.py            # CLI entry point (subcommands: init·check·version·dashboard·gate·dataset·monitor·trend)
└── serve/
    ├── server.py          # FastAPI dashboard (108 routes)
    └── routers/           # alerts · anomaly · config · conversation · cost · data · export
                           # feedback · golden · stream · transparency · webhook
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

## SDK Fixed Facts (Authoritative Reference)

- Native Trackers: **25** | Harness Configs: **33** | Gates: **7** (A–G)
- Version: **v0.9.6** (Beta) | Python: **3.8+**
- Tests: **75 files**, **3,127+** test functions
- Dashboard: **108** API routes (FastAPI)
- `from agent_evaluator import agent_eval` — correct import path  
  `from agent_evaluator.decorators import agent_eval` — internal module (direct import discouraged)
- Tracker count per Gate: A=3, B=0, C=2, D=1, E=5, F=2, G=1 (14 gate-contributing + 11 operational = 25)
- HallucinationDetector attribution: conceptually Gate C (Reliability) | SDK score contribution: Gate C (`_rel_vals`) + Gate G (`_obs_vals`)
- AccuracyEvaluator attribution: Gate A `_a_vals[0]` 블렌딩 (`0.6×TCR + 0.4×Accuracy`) — 별도 항목 추가가 아닌 TCR 컴포넌트에 혼합
- **PlanConfig defaults**: `max_steps=15`, `min_steps=2` (decorators.py lines 427-428)
- **PlanConfig supported JSON formats**: `{"steps": [...]}` or `{"plan": [...]}` (plan key must be a direct list)  
  ❌ `{"plan": {"steps": [...]}}` nested dict structure cannot be parsed
- **Gate G aggregation**: if `_obs_vals` is empty, Gate G `score=None` (excluded from aggregation, not a fail)
- **`report.to_dict()["extra_metrics"]`**: contains `harness_groups` and `lineage` (SPEC-007) — no `llm_judge` key  
  LLMJudge results: `monitor.llm_judge.get_summary()` → `avg_scores` → `criteria_scores`
- **HarnessEvaluationGate location**: `agent_evaluator/quick_eval.py`  
  `gate.evaluate()` takes no arguments. Returns: `{passed, groups, violations, summary}`
- **SLAConfig dual contribution**: Gate D Config, but breach_rate also contributes to Gate C `_rel_vals`  
  Gate D score requires `LatencyTracker` measured P95 > 0 (`_perf_vals` must be populated)
- **SPEC-007 — lineage capture**: `extra_metrics.lineage` always present in `save_to_file` output (task 유무 무관) —
  `sdk_version`(자동), `git_commit`(인스턴스 생성 시 1회 캐싱, 비-git 환경이면 `None`), `prompt_version`/`agent_version`
  (`PerformanceMonitor(...)` 생성자 파라미터, 기본 `None`), `judge_model_snapshot`(judge 사용 시 provider가 실제
  반환한 모델 스냅샷, `LLMJudge._call_claude`/`_call_openai`의 응답 객체 `.model` 필드에서 추출 — 없으면
  `judge.model` 설정값으로 폴백).
- **TTFTVariabilityConfig · CostPredictabilityConfig**: set at `PerformanceMonitor` level, not `@agent_eval` parameters  
  `PerformanceMonitor(ttft_variability_config=..., cost_predictability_config=...)`
- **SPEC-002 — universal min-sample guard**: every Gate (A–G) now exposes `details["insufficient_data_warnings"]`
  (previously Gate D only). Default threshold `min_samples_default=3` (`PerformanceMonitor(min_samples_default=...)`);
  Gate D's own TTFT/Cost/SLA thresholds (5) are unchanged. The shared SLA warning is computed once and appears
  identically in both Gate C and Gate D.
- **SPEC-012 — event-based min-sample guard**: Gate F `coordination_score`/`avg_tool_selection_f1` (denominators
  `total_interactions`/`total_evaluations`) and Gate G `tool_coverage` (denominator `total_calls`) also warn via
  `_min_sample_warning(..., unit="interactions"|"evaluations"|"calls")` — same `min_samples_default` contract,
  distinct unit wording so these don't read as task-count warnings.
- **SPEC-011 — tool_coverage attribute fix**: `monitor.py` previously passed a non-existent attribute name
  (`self.tool_call_analyzer`) into Gate G's aggregate call; the real attribute is `self.tool_analyzer`. Fixed —
  `tool_coverage` now actually computes for sessions with recorded `tool_calls` (previously always `None`).
- **SPEC-004 — streaming retention mode (Partially Implemented)**: `PerformanceMonitor(retention_mode="full"|"windowed", window_size=10000)`.
  Default `"full"` is unchanged. In `"windowed"` mode, `self.tasks` behaves like `deque(maxlen=window_size)`;
  only Gate A/C's TCR component gets a true running aggregate (`_RunningTCRView`) that keeps reflecting
  evicted tasks — all other Gate metrics still recompute from the windowed task list only (reduced REQ-2
  scope, documented in `Docs/specs/SPEC-004-streaming-retention-mode.md`). `get_report_by_type`/
  `get_report_by_framework`/`export_by_framework`/`register_aggregator` emit a `UserWarning` every call
  in windowed mode.
- **SPEC-009 — structured signal evaluation**: `gates/gate_f_multiagent/evaluators.py`'s `eval_consensus`/
  `eval_role_adherence`/`eval_propagation` now prefer structured `agent_interactions`/`tool_calls` data over
  text-heuristic matching when available (each returns a new diagnostic `"signal_source": "structured"|"text_fallback"`
  key; Gate score itself is unaffected). Falls back to the pre-existing text matching 100% unchanged when
  structured fields are absent — this is the only byte-diff-safe path; structured-mode scoring is intentionally
  NOT guaranteed identical to legacy text-matching output (see SPEC-009 REQ-5).
- **SPEC-008 — compliance framework expansion**: `ComplianceConfig.compliance_framework` now supports
  `"pci_dss"` (`pci_dss:cardholder_data_exposure` — PAN via existing `_PII_PATTERNS["credit_card"]` +
  new CVV/expiry-date patterns) and `"soc2"` (`soc2:trust_service_violation` — access-control-bypass
  keyword set) alongside the existing `"hipaa"`/`"gdpr"`/`"general"`. `__post_init__` now emits a
  `UserWarning` for any other value (previously silently fell back to generic PII scanning with no
  signal to the user). New `_VIOLATION_PENALTIES` weights: `pci_dss=0.38`, `soc2=0.28`.
- **SPEC-010 — CI/CD baseline gate (Harness Gate A–G regression)**: `agent_evaluator/quick_eval.py`
  gained shared helpers `_compute_gate_regressions()`/`_normalize_gate_score_dict()`, used by both
  `HarnessEvaluationGate.evaluate(baseline=None, regression_threshold=0.05)` (Python API) and
  `agent_evaluator/cli/gate.py`'s `--fail-on-regression` (CLI) so both share one regression
  definition. The CLI's flat-metric (`tcr`/`accuracy`/etc.) baseline system already existed
  (`--baseline`/`--save-baseline`/`--fail-on-regression`) — this spec extended it to also cover
  Harness Gate A–G scores (`baseline.json`'s new `"gate_scores"` key, backward-compatible with
  older baseline files that lack it). `baseline` omitted → `"regressions"` key doesn't appear in
  `evaluate()`'s result at all (byte-for-byte unchanged from pre-SPEC-010 behavior).
- **SPEC-013 — dashboard loader incremental cache**: `serve/loader.py::load_results(results_dir,
  previous=None)` — when `previous` (a prior `ResultSet`) is given, files whose `path.stat().st_mtime`
  matches the cached `ResultFile.mtime` (new field, SPEC-013) skip `parse_file()` entirely and reuse
  the cached object by identity. `serve/routers/data.py::list_results()`'s watch-mode
  unconditional-reload and `serve/server.py::reload_results()` (FileWatcher callback) both now pass
  `previous=`the existing `app.state.result_set` — the per-request "reparse everything" cost in
  watch mode is now "reparse only what changed." `previous` omitted → identical to pre-SPEC-013
  behavior.
- **SPEC-014 — generate_report() caching**: `PerformanceMonitor.generate_report(force_recompute=False)`
  short-circuits to a cached `EvaluationReport` when `self._report_cache_dirty` is `False` (set/read
  under `self._lock`), skipping `_compute_harness_groups()` and the rest of the (renamed)
  `_generate_report_uncached()` entirely. `record_task()` sets the dirty flag at the end of its
  existing lock block. **Invariant**: any code path that mutates an already-recorded `TaskResult`
  in place (not through `record_task()`) must call `monitor.invalidate_report_cache()` afterward, or
  `generate_report()` can silently return a stale report. Currently wired at 5 sites: BUG-E6's
  threat_severity/threat_response post-record re-eval and SPEC-006's async judge patch (both in
  `decorators.py`, matching the spec's Context), plus 3 more found only while implementing —
  `PerformanceMonitor.reset()`, `flush()`, and `export_by_framework()` (which temporarily swaps
  `self.tasks` to a filtered subset and back). If you add a new post-record mutation site, wire this
  in too. `force_recompute=True` bypasses the cache unconditionally.
- **SPEC-015 — alert handler retry/backoff & storm suppression**: `alerts/engine.py` gained
  `_send_with_retry(handler, event, max_retries=3)` (1s/2s/4s backoff, same pattern as SPEC-006's
  `LLMJudge._call_with_retry()`), wrapping the `rule.handler.send(event)` call that previously
  swallowed all exceptions at `debug` level with zero retry. `AlertEngine.get_failed_send_count()`/
  `get_suppressed_count()` expose failure/suppression counts. `AlertEngine(async_dispatch=False)`
  (default — unchanged synchronous behavior, all 21 pre-existing `test_alerts_engine.py` tests pass
  unmodified) — `True` dispatches `_dispatch()` (retry included) on a daemon thread so `evaluate()`
  doesn't block on network I/O. `rule.mark_fired()` still fires before dispatch regardless of
  success (unchanged — avoids hammering an already-broken handler). `AlertEngine(
  max_alerts_per_window=None, window_seconds=60)` (default `None` = disabled) — when set, alerts
  beyond the trailing-window cap still get recorded to `AlertHistory` but their `handler.send()`
  dispatch is skipped ("alert storm" suppression).
- **SPEC-016 — SQLite storage backend**: `PerformanceMonitor(storage_backend: Literal["json",
  "sqlite"] = "json")` — default `"json"` is byte-for-byte unchanged `save_to_file()` behavior.
  `"sqlite"` redirects `save_to_file()` to `agent_evaluator/storage/sqlite_backend.py::
  save_tasks_to_db()`, which upserts (`INSERT ... ON CONFLICT(task_id) DO UPDATE`) each task by
  `task_id` instead of re-serializing the entire task history every call, with `PRAGMA
  journal_mode=WAL` for safe multi-writer concurrent access. Schema is intentionally minimal —
  a few scalar columns (`task_id` PK, `task_type`, `success`, `timestamp`) for queryability plus
  one `data_json` column holding the full `TaskResult.to_dict()` blob, reusing the existing
  `TaskResult.to_dict()`/`from_dict()` round-trip helpers (`core/trackers/base.py`) instead of
  mapping every field to its own column — future `TaskResult` fields don't require a schema
  migration. A `schema_version` table raises `RuntimeError` on version mismatch (no auto-migration).
  `load_tasks_from_db(path) -> List[TaskResult]` reconstructs tasks for offline analysis; the
  dashboard (`serve/loader.py`) does NOT read `.db` files — it's JSON-only, unchanged.
- **SPEC-017 — supply chain hygiene**: `.github/workflows/ci.yml` runs `pytest` across a Python
  3.8–3.13 matrix (hard-block) plus `ruff check`/`mypy` (deliberately `continue-on-error: true` —
  a baseline check at introduction time found 4,063 pre-existing ruff findings and 305 mypy errors,
  so making them hard-block would fail CI on day one for unrelated debt; tighten this once that
  backlog is cleaned up separately). `.github/workflows/security.yml` runs `pip-audit` the same way
  (report-only; baseline found 20 known vulnerabilities in the dev environment) on push/PR/weekly
  schedule, plus a separate `sbom` job that only runs on `v*` tag pushes and uploads a CycloneDX
  JSON SBOM as a build artifact. `.github/dependabot.yml` covers both `pip` and `github-actions`
  ecosystems (weekly). `.pre-commit-config.yaml` finally wires up the `pre-commit` dev dependency
  that was declared in `pyproject.toml` but had zero effect (no config file existed). `SECURITY.md`
  added. None of this touches the existing manual release process (`python -m build` / `twine
  upload`). **Caveat**: `pre-commit run --all-files` was NOT run destructively across the repo as
  part of this work — doing so during implementation reformatted 199 tracked files repo-wide as an
  unintended side effect, which had to be recovered via `git stash` + precise reapplication of the
  actual SPEC-015/016 edits. A full-repo reformat, if wanted, should be its own separate, deliberate PR.
- **SPEC-018 — Gate running-aggregate shared_metrics layer**: extends SPEC-004's `_running_tcr_agg`/
  `_RunningTCRView` pattern (previously the *only* Gate metric with true full-history behavior under
  `retention_mode="windowed"`) to all 7 Gates A-G (Phase 0-7, fully complete). New
  `agent_evaluator/gates/shared_metrics.py` has 7 generic accumulator primitives (`RunningAverage`/
  `RunningSum`/`RunningWindow`/`RunningLastValue`/`MonotonicFlag`/`RunningCount`/
  `RunningCategoryCounter`) plus 8 per-Gate agg classes (`GateESharedAgg`/`GateFSharedAgg`/
  `GateGSharedAgg`/`GateBSharedAgg`/`GateASharedAgg`/`GateCSharedAgg`/`GateCRetryConsistencyAgg`/
  `GateDSharedAgg`). Each `gates/gate_x/aggregate.py::compute()` gained an optional trailing
  `shared_running: Optional[dict] = None` param — `None` (default, "full" mode) is byte-identical to
  pre-SPEC-018 behavior; windowed mode passes a `.snapshot()` from the corresponding agg class,
  updated in `record_task()`'s existing lock block right after the security-tracker enrichment step
  (the enrichment runs *after* the TCR agg update, so any new Gate-agg `.update()` call must go after
  enrichment too, or it'll aggregate the pre-enriched `task_result` — this exact ordering bug was
  caught and fixed during Gate E's implementation via the full-vs-windowed cross-check test).
  Also fixed a pre-existing display bug while migrating Gate C: `sla_breach_count` used to show
  `None` whenever the *windowed* task subset had no SLA-tagged tasks, even if full history did —
  now gated on a full-history count (`sla_n`) instead, with zero behavior change in "full" mode.
  `SPEC-001` is unrelated to this work despite SPEC-004 citing it as a prerequisite — SPEC-001 is
  actually about deduplicating `monitor.py`'s live Gate-scoring formulas against `serve/loader.py`'s
  legacy-JSON fallback formulas, a separate problem never implemented standalone (folded into
  SPEC-000).
  **Phase 7 (2026-07-03, separate user approval)** implemented the two items originally deferred as
  requiring an approximation trade-off:
  - **Gate C `retry_consistency`**: `GateCRetryConsistencyAgg` tracks per-task-id-prefix state
    (score sum/count + the string-min/max task-id entries' accuracy/config, replicating the
    original's sort-then-`[0]`/`[-1]` logic) in an `OrderedDict` capped at `_MAX_PREFIXES=5000` —
    exceeding the cap evicts the least-recently-touched prefix (LRU), dropping its contribution from
    the final average. `evicted_count` exposes whether the approximation actually fired. Passed to
    `gate_c_reliability.aggregate.compute()` via a separate `retry_consistency_shared` param (not
    folded into Gate C's main `shared_running`) specifically so this one approximated metric stays
    visually distinct from the other four exact ones in the diff.
  - **Gate D**: `GateDSharedAgg` splits into an exact half and an approximate half. efficiency
    (calibrated_score/efficiency_ratio, per cost-unit) and resource_budget (rollover-mode cumulative
    sums vs per-task-config sums, non-rollover budget_score average, most-recent `_config` via
    `RunningLastValue`) are **exact** — same simple running-average/running-sum pattern as every
    other Gate. ttft_variability (stddev + p50/p95 + IQR outlier removal) and cost_predictability
    (per-task-type CV with mean±k·std outlier filtering) are **not** exactly reproducible in O(1)
    memory, so they're computed from a bounded sliding sample (`_RESERVOIR_SIZE=2000` raw values,
    independent of `window_size`) instead — identical math to the original, just over a recency-based
    sample rather than the full history once that history exceeds 2000 points. p95 latency itself
    needed zero changes: `latency_tracker` (`_latencies`/`_ttft_records`) is a plain unbounded list,
    never capped by `retention_mode` in the first place, so it already reflected full history (same
    situation as Gate G/C's `hallucination_rate`, discovered during Phase 3).
  Neither cap (`_MAX_PREFIXES`, `_RESERVOIR_SIZE`) is exposed as a `PerformanceMonitor` constructor
  parameter — they're hardcoded constants sized for typical usage; parameterizing them would be a
  separate follow-up if a session's prefix cardinality or raw-value volume genuinely needs tuning.

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

**75 files, 3,127+ test functions** in `tests/`.

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
