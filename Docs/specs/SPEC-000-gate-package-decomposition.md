# SPEC-000: Gate 패키지 전면 분해

**Phase:** P1 (구조 기반) · **상태:** ✅ **완료 (2026-07-02)** — Gate A–G 전체 7개 Gate 이관 완료 · **의존성:** 없음 (다른 모든 구조 스펙의 상위 스펙)
**흡수(subsumes):** [SPEC-001](SPEC-001-gate-aggregation-unification.md)의 REQ-1~4, [SPEC-003](SPEC-003-single-pass-aggregation.md)의 REQ-1~3 — 별도 문서는 유지하되 구현은 이 스펙의 Gate별 이관 작업 안에서 함께 처리한다.

## 진행 상황

| Gate | 상태 | 커밋 |
|---|---|---|
| 공유 인프라(`gates/base.py`) | ✅ 완료 (2026-07-02) | Commit 0 — `_DEFAULT_MIN_SAMPLES`/`_min_sample_warning`/`_status`/`_g`를 monitor.py에서 모듈 레벨로 승격 |
| **F** (Multi-Agent Coordination) | ✅ 완료 (2026-07-02) | Commit 1 — Config 4개(`gates/gate_f_multiagent/configs.py`), eval 함수 4개(`.../evaluators.py`), 집계 로직(`.../aggregate.py`, 4개 task 기반 지표 단일 패스 병합) 이관. `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_base.py`(11건)·`tests/test_gates_gate_f_migration.py`(11건), 기존 `tests/test_gate_f_bugs.py`(27건) 무수정 통과. |
| **E** (Security Boundary) | ✅ 완료 (2026-07-02) | Config 3개(`ThreatSeverityConfig`·`ComplianceConfig`·`ThreatResponseConfig` → `gates/gate_e_security/configs.py`), eval 함수 3개(`eval_threat_severity`·`eval_compliance`·`eval_threat_response` → `.../evaluators.py`, `_PII_PATTERNS`도 함께 이관), 집계 로직(`.../aggregate.py`, 5개 보안 트래커 + CVSS + compliance + threat_response, 로직 변경 없이 위치만 이관) 완료. `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_gate_e_migration.py`(10건), 기존 `tests/test_gate_e_round3.py`(44건)·`tests/test_security_trackers.py`(51건, 도합 108건) 무수정 통과. |
| **D** (Performance Contract) | ✅ 완료 (2026-07-02) | Config 5개(`SLAConfig`·`EfficiencyConfig`·`ResourceBudgetConfig`·`TTFTVariabilityConfig`·`CostPredictabilityConfig` → `gates/gate_d_performance/configs.py`), eval 함수 3개(`eval_sla`·`eval_efficiency`·`eval_resource_budget` → `.../evaluators.py`), 집계 로직(`.../aggregate.py`, latency+efficiency+budget+TTFT+cost predictability) 완료. **SLAConfig 이중 귀속 처리**: SLA 데이터(`_sla_results`/`_sla_window_penalty`/`_sla_budget_penalty`/`_sla_warning`)는 아직 이관되지 않은 Gate C 섹션에서 계속 계산되어 `aggregate.compute()`에 파라미터로 전달되는 임시 공유 방식 채택(Gate C 이관 시 `shared_metrics.py`로 정리 예정). `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_gate_d_migration.py`(12건), 기존 `tests/test_decorators_harness.py`(280건) 무수정 통과. |
| **A** (Goal Achievement) | ✅ 완료 (2026-07-02) | Config 6개(`InstructionConfig`·`GoalAlignmentConfig`·`PlanConfig`·`SubtaskConfig`·`ContextRetentionConfig`·`KnowledgeRetentionConfig` → `gates/gate_a_goal/configs.py`), eval 함수 6개(`eval_instruction_adherence`·`eval_goal_alignment`·`eval_plan_coherence`·`eval_context_retention`·`eval_subtask_completion`·`eval_knowledge_retention` → `.../evaluators.py`, Gate A 전용 private 헬퍼 `_is_subtask_found`·`_is_fact_retained_in_text`·`_kr_strip_particle`·`_GOAL_STOPWORDS`·`_clamp01` 등도 함께 이관 — 다른 Gate와 비공유 확인), 집계 로직(`.../aggregate.py`, TCR+AccuracyEvaluator 블렌딩+ResponseQualityEvaluator) 완료. **Gate A→B 교차 참조 처리**: Gate B가 진단용으로 재참조하는 `avg_goal_alignment`/`avg_plan_coherence`를 `_a_group["details"]`에서 읽어오도록 전환(재계산 제거). 기존 `tests/test_decorators_harness.py`가 Gate A의 private 헬퍼 4종(`_kr_strip_particle`·`_is_fact_retained_in_text`·`_KOREAN_UNITS`·`_KOREAN_PARTICLES_1`)을 직접 import하고 있어 `taskresult_helpers.py`에서 추가 재노출 필요. 신규 테스트 `tests/test_gates_gate_a_migration.py`(16건, Gate A→B 교차 참조 검증 포함), 기존 `tests/test_decorators_harness.py`(280건) 무수정 통과. 전체 스위트 2,894 passed, 회귀 0건. |
| **B** (Behavioral Integrity) | ✅ 완료 (2026-07-02) | Config 6개(`LoopDetectionConfig`·`StateConsistencyConfig`·`DeadlockConfig`·`ScopeConfig`·`ToolParameterSafetyConfig`·`ContextWindowConfig` → `gates/gate_b_behavioral/configs.py`), eval 함수 6개(`eval_loop_detection`·`eval_state_consistency`·`eval_deadlock`·`eval_scope`·`eval_tool_parameter_safety`·`eval_context_window` → `.../evaluators.py`, Gate B 전용 private 헬퍼 `_normalize_agent_interactions`도 함께 이관 — 다른 Gate와 비공유 확인, `_token_overlap_ratio`는 Gate A/F와 공유하므로 `taskresult_helpers.py`에 그대로 두고 import만), 집계 로직(`.../aggregate.py`, loop+state_consistency+deadlock+scope+tool_parameter_safety+context_window) 완료. **Gate A→B 교차 참조 유지**: `avg_goal_alignment`/`avg_plan_coherence`를 monitor.py가 `_a_group["details"]`에서 읽어 `aggregate.compute()`에 파라미터로 전달(SLA의 Gate C→D 공유 패턴과 동일). `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_gate_b_migration.py`(17건, Gate A→B 교차 참조 검증 포함), 기존 `tests/test_decorators_harness.py`(280건)·`tests/test_report_harness_groups.py`(32건) 무수정 통과. 전체 스위트 2,911 passed, 회귀 0건. |
| **C** (Reliability) | ✅ 완료 (2026-07-02) | Config 5개(`ReproducibilityConfig`·`FaultToleranceConfig`·`GracefulDegradationConfig`·`RetryConsistencyConfig`·`IdempotencyConfig` → `gates/gate_c_reliability/configs.py`), eval/compute 함수 5개(`eval_fault_tolerance`·`compute_reproducibility_score`·`eval_graceful_degradation`·`eval_retry_consistency`·`eval_idempotency` → `.../evaluators.py`, `_token_overlap_ratio`는 Gate A/B/F와 공유하므로 import만), 집계 로직(`.../aggregate.py`, TCR+SLA breach+reproducibility+fault_tolerance+graceful_degradation+retry_consistency+idempotency+LLM faithfulness/hallucination) 완료. **SLA 공유 데이터 원천 전환**: 기존에 Gate C 섹션에 인라인되어 있던 SLA 계산을 `gate_c_aggregate.compute_sla_shared_data(tasks)`라는 독립 순수 함수로 분리 — monitor.py가 한 번 호출해 그 결과(`sla_results`/`sla_window_penalty`/`sla_budget_penalty`/`sla_warning`)를 Gate C·D 양쪽 aggregate 호출에 전달(Gate D의 `compute()` 시그니처는 변경 없음). **hall_rate/avg_llm_faithfulness → Gate G(미이관) 공유**: `gate_c_aggregate.compute()`가 `(group_dict, shared_raw)` 튜플을 반환 — `group_dict`는 다른 Gate와 동일하게 JSON 리포트에 그대로 노출되는 `_g()` 형식(이관 전과 완전히 동일), `shared_raw`는 반올림되지 않은 원본값을 담아 이중 반올림에 의한 정밀도 손실 없이 Gate G 섹션이 재사용한다. `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_gate_c_migration.py`(16건, SLA 공유 데이터 파이프라인 검증·hall_rate 공유 검증·LLM faithfulness 기여 검증 포함), 기존 `tests/test_decorators_harness.py`(280건)·`tests/test_report_harness_groups.py`(32건)·`tests/test_gates_gate_d_migration.py`(12건)·`tests/test_min_sample_guard.py`(14건) 무수정 통과. 전체 스위트 2,927 passed, 회귀 0건. |
| **G** (Observability) | ✅ 완료 (2026-07-02) | Config 4개(`ObservabilityConfig`·`ExplainabilityConfig`·`ErrorDiagnosisConfig`·`LatencyAttributionConfig` → `gates/gate_g_observability/configs.py`), eval 함수 4개(`eval_observability`·`eval_explainability`·`eval_error_diagnosis`·`eval_latency_attribution` → `.../evaluators.py`), 집계 로직(`.../aggregate.py`, tool_coverage+hallucination+observability+explainability+error_diagnosis+latency_attribution) 완료. **Gate C→G hall_rate/avg_llm_faithfulness 공유 소비**: Gate C의 `compute()`가 반환하는 shared_raw(반올림 없는 원본값)를 monitor.py가 파라미터로 전달 — LLMJudge faithfulness 활성 시 hallucination fallback을 비활성화하는 이중 반영 방지 로직 그대로 유지. **사전 존재 결함 발견 및 무변경 보존**: `self.tool_call_analyzer`는 `PerformanceMonitor`에 실존하지 않는 속성명(실제는 `self.tool_analyzer`)으로, 이관 전에도 항상 `AttributeError`가 로컬 `try/except`에 삼켜져 `tool_coverage`가 항상 `None`이었던 잠재 버그. 이관 과정에서 속성 접근이 함수 호출 경계 밖으로 노출되며 크래시로 드러났고, `getattr(self, "tool_call_analyzer", None)`으로 동일한 침묵 실패를 재현해 관찰 가능한 동작을 완전히 보존(버그 자체는 이번 스펙 범위 밖 — 별도 이슈로 남겨둠). `decorators.py`/`taskresult_helpers.py`는 원위치에서 re-export. 신규 테스트 `tests/test_gates_gate_g_migration.py`(13건, hall_rate 공유 검증·tool_call_analyzer 결함 보존 검증 포함), 기존 `tests/test_gate_g_bugs.py`(다수)·`tests/test_decorators_harness.py`(280건)·`tests/test_report_harness_groups.py`(32건) 무수정 통과. 전체 스위트 2,940 passed, 회귀 0건. **이 커밋으로 SPEC-000의 Gate A–G 전체 이관이 완료된다(F→E→D→A→B→C→G).** |

## 완료 후 후속 작업 (별도 스펙 권장)

- `Docs/specs/README.md` 백로그에 명시된 "이벤트 기반 지표 min-sample 가드"(Gate F `coordination_score`/`avg_tool_selection_f1`, Gate G `tool_coverage`)는 이번 스펙 범위 밖으로 남아있다.
- ~~Gate G에서 발견된 `self.tool_call_analyzer` 속성 부재 결함~~ → **[SPEC-011](SPEC-011-tool-coverage-attribute-fix.md)로 수정 완료 (2026-07-02)**. `tool_coverage`는 이제 도구 호출이 있는 세션에서 실제 값을 반환한다.
- SLA 공유 데이터(Gate C↔D)와 hall_rate/faithfulness 공유 데이터(Gate C↔G)를 정식 `gates/shared_metrics.py` 모듈로 통합 정리하는 리팩터는 SPEC-001 후속 작업으로 고려 가능(현재는 Gate C의 `compute_sla_shared_data()`와 튜플 반환 방식으로 충분히 해결된 상태).

## Context

- `agent_evaluator/decorators.py` — 9,632줄, top-level 정의 102개. 33개 Harness Config 데이터클래스가 Gate별로 정렬되지 않고 완전히 무작위로 인터리빙되어 있다 (`InstructionConfig(A) → LoopDetectionConfig(B) → GoalAlignmentConfig(A) → ReproducibilityConfig(C) → PlanConfig(A) → SLAConfig(D) → ThreatSeverityConfig(E)...`, 2026-07-02 세션에서 `grep -n "^@dataclasses.dataclass" -A1` 전체 목록으로 직접 확인).
- `agent_evaluator/helpers/taskresult_helpers.py` — 4,632줄, `eval_*` 함수 55개가 Gate/도메인별 그룹핑 없이 평면 나열되어 있다.
- `agent_evaluator/core/trackers/monitor.py::_compute_harness_groups` — 단일 메서드로 ~1,165줄(`monitor.py:2779-3943`, God Method), `for t in tasks` 순회 46회, `serve/loader.py::_compute_harness_groups_fallback`과 수식이 다른 중복 구현.
- `decorators.py`는 top-level에서 `taskresult_helpers.py`/`monitor.py`를 import하지 않고 함수 내부 지역(lazy) import만 사용한다(`decorators.py:5264` 등 30여 곳) — 순환 임포트 리스크를 이미 우회해온 흔적이며, `monitor.py`는 `decorators.py`를 참조하지 않아 역방향 순환은 없다(확인 완료). 새 패키지 구조는 이 단방향 의존을 그대로 보존해야 한다.
- Gate 간 실제 데이터 의존성이 존재한다: Gate A의 `avg_goal_alignment`/`avg_plan_coherence`가 Gate B의 `details`에 진단용으로 재참조되고(`monitor.py:3865-3866`, 스코어링 제외), SLA 데이터가 Gate C와 Gate D 양쪽의 스코어링에 반영된다(`monitor.py:3082`, `:3878`). 완전 독립 슬라이스로 설계하면 안 되고 공유 계층이 필요하다.

## Goals

- Gate 관련 코드(Config/평가 함수/집계 로직)를 Gate 단위 수직 슬라이스 패키지로 재구성해, 어느 파일도 사람이 한 번에 파악하기 버거운 크기(목표: 파일당 1,500줄 이하)를 넘지 않게 한다.
- Gate 간 공유 데이터(TCR, SLA breach, goal_alignment/plan_coherence)를 단일 소스로 계산하는 `shared_metrics` 계층을 도입해, SPEC-001이 지적한 `monitor.py`/`serve/loader.py` 간 중복 수식 문제를 구조적으로 제거한다.
- 각 Gate 이관 시 SPEC-003의 단일 패스 최적화를 함께 적용해, 나중에 다시 손대는 이중 작업을 방지한다.
- 새 Gate/Config 추가 시 표본 가드(SPEC-002)를 빠뜨릴 수 없도록 `GateEvaluator` 계약으로 강제한다.

## Non-Goals

- Gate 점수 산출 공식 자체의 재설계(가중치 변경 등) — 기존 공식을 그대로 옮긴다.
- 대시보드 UI 리디자인.
- Config 33개 필드 자체의 의미 변경 — 위치만 옮긴다.

## Target Package Layout

```
agent_evaluator/
├── gates/
│   ├── __init__.py          # compute_all_gates(tasks=..., report=...) — SPEC-001 REQ-1~4
│   ├── base.py               # GateEvaluator 계약, min_samples 강제(SPEC-002), _min_sample_warning 헬퍼
│   ├── shared_metrics.py     # TCR, SLA breach, goal_alignment, plan_coherence 등 — 여러 Gate가 공유하는 원천값 단일 계산
│   ├── gate_a_goal/
│   │   ├── configs.py         # InstructionConfig, GoalAlignmentConfig, PlanConfig, SubtaskConfig, ContextRetentionConfig, KnowledgeRetentionConfig
│   │   ├── evaluators.py      # eval_instruction_adherence, eval_goal_alignment, eval_plan_coherence, eval_subtask_completion, eval_context_retention, eval_knowledge_retention
│   │   └── aggregate.py       # compute(tasks, shared_metrics) -> GateScore (단일 패스)
│   ├── gate_b_behavioral/    # LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig, ContextWindowConfig, StateConsistencyConfig, DeadlockConfig
│   ├── gate_c_reliability/   # ReproducibilityConfig, FaultToleranceConfig, GracefulDegradationConfig, RetryConsistencyConfig, IdempotencyConfig (+ shared_metrics.sla, .tcr)
│   ├── gate_d_performance/   # SLAConfig, EfficiencyConfig, ResourceBudgetConfig, TTFTVariabilityConfig, CostPredictabilityConfig (+ shared_metrics.sla)
│   ├── gate_e_security/      # ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig
│   ├── gate_f_multiagent/    # ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig
│   └── gate_g_observability/ # ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig, LatencyAttributionConfig
├── decorators.py              # 얇아짐 — gates/*/configs.py를 re-export, agent_eval/batch_eval/conversation_eval 데코레이터 본체만 유지
├── helpers/taskresult_helpers.py  # Gate 이관 완료 후 제거 대상(과도기엔 gates/*/evaluators.py를 재-export하는 얇은 래퍼로 축소)
└── core/trackers/monitor.py   # 얇아짐 — gates.compute_all_gates() 호출부 오케스트레이션만
```

## Requirements

- **REQ-1** (SPEC-001 흡수): `gates/__init__.py::compute_all_gates(tasks=None, report=None, config=None)`가 `monitor.py`와 `serve/loader.py` 양쪽에서 호출되는 유일한 Gate 집계 진입점이 된다. 원본 tracker 데이터가 없는 지표만 `None` 처리, 결측 지표가 하나라도 있으면 해당 Gate에 `"approximated": true`.
- **REQ-2** (SPEC-003 흡수): 각 `gate_x/aggregate.py::compute()`는 태스크 리스트를 **단일 패스**로 순회해 필요한 러닝 합/카운트를 축적한다. 리팩터 전후 `monitor.py`가 산출하던 값과 100% 동일해야 한다(byte-diff 검증).
- **REQ-3** (SPEC-002 흡수): `gates/base.py::GateEvaluator`에 `min_samples` 계약을 두어 새 지표 추가 시 표본 가드를 생략할 수 없게 한다.
- **REQ-4**: `decorators.py`의 기존 공개 import 경로(`from agent_evaluator import InstructionConfig`)는 `gates/gate_a_goal/configs.py`를 re-export하는 형태로 100% 하위호환 유지한다.
- **REQ-5**: Gate 간 교차 참조(A→B 진단용, SLA→C&D 스코어링)는 `gates/shared_metrics.py`에서 한 번만 계산되고, 각 Gate의 `aggregate.py`는 이를 read-only로 소비한다. 계산 순서(A 완료 후 B 조회 가능하도록)는 `gates/__init__.py::compute_all_gates`가 보장한다.
- **REQ-6**: 이관은 Gate 단위 Strangler Fig 방식으로 진행한다 — 한 Gate를 옮길 때마다 원래 위치(`decorators.py`/`taskresult_helpers.py`/`monitor.py`)에는 새 패키지를 가리키는 re-export/위임만 남기고, 해당 커밋 단위로 `pytest` 전량 통과를 병합 조건으로 한다.
- **REQ-7**: `decorators.py`의 기존 lazy-import 패턴(`taskresult_helpers.py`/`monitor.py`에 대한 지역 import, 30여 곳)은 새 패키지 구조에서 순환 의존이 구조적으로 사라지면 top-level import로 정리한다(선택적 정리, 필수는 아님).

## Interface

```python
# 변경 전
from agent_evaluator import InstructionConfig  # decorators.py에 정의
from agent_evaluator.helpers.taskresult_helpers import eval_instruction_adherence

# 변경 후 (하위호환 — import 경로 동일하게 동작)
from agent_evaluator import InstructionConfig  # 실제로는 gates/gate_a_goal/configs.py, decorators.py가 re-export
from agent_evaluator.helpers.taskresult_helpers import eval_instruction_adherence  # gates/gate_a_goal/evaluators.py로 위임
```

```python
# monitor.py 내부 (변경 후)
def generate_report(self) -> "EvaluationReport":
    ...
    harness_groups = gates.compute_all_gates(tasks=list(self.tcr_tracker.tasks), config=self._gate_config)
    ...
```

## Acceptance

- Gate 단위 이관마다: 이관 전/후 동일 입력에 대해 해당 Gate의 `score`/`details`가 완전히 동일(byte-diff 0).
- 전체 이관 완료 후 `decorators.py`/`taskresult_helpers.py`/`monitor.py` 각각의 파일 줄 수가 목표치(각각 대폭 축소, 구체 수치는 이관 완료 후 측정) 이하로 감소했는지 확인.
- 기존 2,795개 테스트 전량 통과(각 Gate 이관 커밋마다).
- `import agent_evaluator` 및 `from agent_evaluator import <33개 Config 중 임의>`가 이관 전후 동일하게 동작(하위호환 회귀 테스트).
- `monitor.py`와 `serve/loader.py`가 동일 입력에 대해 동일 Gate 점수를 반환(SPEC-001 REQ 검증 그대로 재사용).

## Compatibility

- 공개 API(모든 Config 클래스, `eval_*` 함수의 import 경로, `PerformanceMonitor`/`@agent_eval` 시그니처)는 완전히 하위호환 유지.
- 내부 파일 구조만 변경 — 사용자 코드 수정 불필요.

## Rollout

Gate 단위로 순차 진행하며, 각 Gate 완료 시마다 별도 PR/커밋으로 분리한다.

| 순서 | Gate | 근거 |
|---|---|---|
| 1 | F (Multi-Agent Coordination) | 최근 버그 수정 이력(17건, 2026-06-14/15)이 가장 상세히 검증되어 회귀 시 원인 추적이 쉬움 |
| 2 | E (Security Boundary) | 마찬가지로 최근 검증(15건) 완료 영역 |
| 3 | D (Performance Contract) | 최근 검증(17건) + SPEC-002/003 참조 구현이 이미 이 Gate에 있어 이관 시 패턴 재사용 용이 |
| 4 | A (Goal Achievement) | Gate B의 진단용 참조 대상이므로 B보다 먼저 이관 |
| 5 | B (Behavioral Integrity) | A 완료 후 진행(교차 참조 의존) |
| 6 | C (Reliability) | SLA 공유 로직 때문에 D 이관 완료 후 진행 |
| 7 | G (Observability) | 마지막, 다른 Gate와의 교차 의존이 가장 적음 |

각 Gate 이관 단계:
1. `gates/gate_x/{configs.py, evaluators.py, aggregate.py}` 신설, 기존 코드를 그대로 복사(로직 변경 없음).
2. `decorators.py`/`taskresult_helpers.py`/`monitor.py`의 해당 부분을 새 위치로 위임하는 얇은 re-export/wrapper로 교체.
3. `aggregate.py` 작성 시 SPEC-002(표본 가드)·SPEC-003(단일 패스) 요구사항을 함께 적용.
4. 회귀 테스트(byte-diff) 통과 확인 후 병합.

## Risks

- 33개 Config + 55개 eval 함수를 이관하는 대규모 작업이므로, Gate 단위로 잘게 쪼개도 리뷰 부담이 크다 — PR당 1개 Gate로 엄격히 제한.
- `decorators.py`의 기존 lazy-import 우회 패턴(REQ-7)을 top-level import로 정리하는 과정에서 미처 몰랐던 순환 의존이 드러날 수 있음 — REQ-7은 선택 사항으로 두어, 발견 시 lazy-import를 유지한 채로도 REQ-1~6은 완결 가능하게 한다.
- Gate 간 교차 참조(A→B, SLA→C&D)를 `shared_metrics.py`로 옮기는 과정에서 계산 순서를 잘못 바꾸면 진단값이 미묘하게 달라질 수 있음 — REQ-5의 순서 보장 테스트로 완화.
