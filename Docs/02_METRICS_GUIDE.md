# 지표 레퍼런스 — Harness Engineering 관점

Agent Evaluator **58개 지표**의 공식·출력키·임계값 참조 문서

**v0.9.12 | 25 Native Trackers + 33 Harness Config = 58개 지표 | 7개 Gate(A–G)로 배포 가능성 판정**

> 개별 트래커 API 시그니처는 [08_API_REFERENCE.md](08_API_REFERENCE.md)를 참조하세요.
> 데코레이터 방식 적용은 [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md)를 참조하세요.


---

## Harness Engineering이란

Harness Engineering은 **"이 에이전트를 프로덕션에 배포해도 되는가?"** 라는 질문에 답하는 평가 방법론입니다.

```
25 Native Trackers  →  원시 신호 수집 (API 비용 없음, 자동 활성화)
33 Harness Configs  →  배포 판단 기준 설정 (@agent_eval 파라미터)
 7 Harness Gates    →  그룹별 통과/경고/실패 판정 → 배포 가능 여부 결정
```

**Native 지표**는 에이전트 실행 중 자동으로 측정되는 원시 신호입니다.  
**Harness Config**는 "어떤 기준으로 합격/불합격을 판정할지" 개발자가 설정하는 게이트입니다.  
**7개 Gate**는 배포 전 검사해야 하는 7가지 관점입니다 — 모든 Gate가 통과해야 배포가 가능합니다.

```python
from agent_evaluator import (
    InstructionConfig, SLAConfig,
    LoopDetectionConfig, ExplainabilityConfig,
)
from agent_evaluator.decorators import agent_eval

# Harness Gate 설정 — @agent_eval 파라미터로 전달
@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["서울"], fail_on_violation=True),   # Gate A
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),                   # Gate B
    sla=SLAConfig(p95_ms=3000),                                                           # Gate D
    explainability=ExplainabilityConfig(require_reasoning=True, min_reasoning_length=30), # Gate G
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
# → 대시보드 Harness Gate 탭에서 A/B/D/G Gate 통과 여부 확인
```

---

## 전체 지표 요약 (58개)

### Native Trackers (25개) — Gate 기여 매핑

| Gate | Native 지표 | 트래커 클래스 | 활성화 |
|------|-------------|---------------|--------|
| **A** | Task Completion Rate (TCR) | `TaskCompletionTracker` | 기본 |
| **A** | Accuracy (overall_accuracy → _a_vals) | `AccuracyEvaluator` | 기본 |
| **A** | Response Quality (5차원) | `ResponseQualityEvaluator` | 기본 |
| **D** | Latency (P50·P90·P95·P99·TTFT) | `LatencyTracker` | 기본 |
| **E** | Input Sanitization | `InputSanitizationTracker` | `enable_security_metrics=True` |
| **E** | Output Leakage | `OutputLeakageDetector` | `enable_security_metrics=True` |
| **E** | Tool Authorization | `ToolAuthorizationTracker` | `enable_security_metrics=True` |
| **E** | Privilege Escalation | `PrivilegeEscalationDetector` | `enable_security_metrics=True` |
| **E** | Tool Chain Attack | `ToolChainAttackDetector` | `enable_security_metrics=True` |
| **F** | Tool Selection Accuracy | `ToolSelectionTracker` | expected_tools 지정 시 |
| **F** | Agent Coordination | `AgentCoordinationTracker` | agent_interactions 기록 시 |
| **G** | Tool Call Success Rate | `ToolCallAnalyzer` | tool_calls 기록 시 |
| **C+G** | Hallucination Rate (규칙 기반) | `HallucinationDetector` | `enable_hallucination_detection=True` |
| **C+G** | Context Recall (근사) | `HallucinationDetector` | `rag_mode=True` |
| **C+G** | Context Precision (근사) | `HallucinationDetector` | `rag_mode=True` |
| **L3** | completeness · relevance · factual | `LLMJudge` | `llm_judge=LLMJudgeConfig()` |
| **L3** | toxicity · bias · safety_score | `LLMJudge` | `llm_judge=LLMJudgeConfig()` |
| **L3** | Faithfulness *(Ragas 대체, v0.7.6+)* | `LLMJudge` | `rag_mode=True` + `llm_judge=LLMJudgeConfig()` |
| **L3** | G-Eval 커스텀 기준 *(DeepEval 대체, v0.7.6+)* | `LLMJudge` | `llm_judge=LLMJudgeConfig(criteria=[...])` |
| **L3** | Hallucination Score (NLI) | DeepEval | `HybridPerformanceMonitor` |
| **L3** | Answer Relevancy / Faithfulness / Context P·R | DeepEval·Ragas | `HybridPerformanceMonitor` |

> **C+G**: `HallucinationDetector`는 Gate C(신뢰성 — 출력 사실 충실성, `_rel_vals`)와 Gate G(관측성 — 환각률 모니터링, `_obs_vals`) 양쪽에 점수를 기여한다. 실제 감지 건수(`_detections`)가 0이면 두 Gate 모두에 미기여.

> **Operational 전용 트래커** (Gate 점수에 기여하지 않음): `RetryCorrectionTracker` (재시도 횟수·패턴 추적), `TokenEconomyTracker` (토큰 비용 추적·보고), `WorkflowExecutionTracker` (체인 단계·분기 추적). 이들의 데이터는 리포트와 대시보드에 표시되지만 Gate A–G 점수 산출에는 포함되지 않는다.

> LLMJudge(L3)는 기본 설치에 포함. DeepEval·Ragas는 `pip install agent-evaluator[eval]` 필요.

### Harness Configs (33개) — Gate 배정

| Gate | 그룹 | Config 목록 | 개수 |
|------|------|-------------|------|
| **A** | Goal Achievement | `InstructionConfig` · `GoalAlignmentConfig` · `PlanConfig` · `SubtaskConfig` · `ContextRetentionConfig` · `KnowledgeRetentionConfig` | 6 |
| **B** | Behavioral Integrity | `LoopDetectionConfig` · `ScopeConfig` · `ToolParameterSafetyConfig` · `ContextWindowConfig` · `StateConsistencyConfig` · `DeadlockConfig` | 6 |
| **C** | Reliability | `ReproducibilityConfig` · `FaultToleranceConfig` · `GracefulDegradationConfig` · `RetryConsistencyConfig` · `IdempotencyConfig` | 5 |
| **D** | Performance Contract | `SLAConfig` · `EfficiencyConfig` · `ResourceBudgetConfig` · `TTFTVariabilityConfig`† · `CostPredictabilityConfig`† | 5 |
| **E** | Security Boundary | `ThreatSeverityConfig` · `ComplianceConfig` · `ThreatResponseConfig` | 3 |
| **F** | Multi-Agent Coord. | `ConsensusConfig` · `PropagationConfig` · `AgentRoleConfig` · `ConflictResolutionConfig` | 4 |
| **G** | Observability | `ExplainabilityConfig` · `ObservabilityConfig` · `ErrorDiagnosisConfig` · `LatencyAttributionConfig` | 4 |

> †`TTFTVariabilityConfig`·`CostPredictabilityConfig`는 monitor 수준 자동 집계 (≥5 tasks). 데코레이터 파라미터 불필요.

---

## Gate A — Goal Achievement (목표 달성)

**"에이전트가 사용자의 의도를 충실히 달성했는가?"**

배포 판단의 첫 번째 관문. TCR·Accuracy Native 지표가 원시 신호를 제공하고, Harness Config A 그룹이 합격 기준을 정의합니다.

### 연결된 Native 지표

| 지표 | 핵심 역할 | 배포 기준 |
|------|-----------|-----------|
| **TCR** (Task Completion Rate) | 에이전트가 태스크를 완료했는가 | 🟢 ≥95% / 🟡 85–95% / 🔴 <85% |
| **Accuracy** | 정답과 얼마나 일치하는가 | 🟢 ≥90% / 🟡 80–90% / 🔴 <80% |

> **TCR 공식**: `TCR = Σ(completion_score) / task_count × 100`  
> **Accuracy 공식 (QA)**: `0.4 × TokenF1 + 0.3 × Jaccard + 0.2 × LCS + 0.1 × CharSimilarity`  
> → 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate A (6개)

#### `InstructionConfig` — 지시 이행률 · 이탈 감지

에이전트가 프롬프트 지시사항을 충실히 따랐는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `required_keywords` | `list[str]` | `[]` | 응답에 반드시 포함되어야 하는 키워드 |
| `forbidden_phrases` | `list[str]` | `[]` | 응답에 포함되면 안 되는 문구 |
| `expected_format` | `str\|None` | `None` | 기대 응답 형식 (`"json"`, `"markdown"`, `"yaml"`, `"plain"`) |
| `required_sections` | `list[str]` | `[]` | 응답에 반드시 포함되어야 하는 섹션 제목 |
| `max_chars` | `int\|None` | `None` | 최대 허용 문자 수 |
| `min_chars` | `int\|None` | `None` | 최소 필요 문자 수 |
| `expected_language` | `str\|None` | `None` | 기대 언어 코드 (예: `"ko"`, `"en"`) |
| `fail_on_violation` | `bool` | `False` | True이면 위반 시 success=False로 처리 |
| `violation_weight` | `float` | `0.1` | 위반당 감점 가중치 |

> 데코레이터 파라미터명: `instructions=InstructionConfig(...)` (복수형)

```python
instructions=InstructionConfig(
    required_keywords=["서울", "수도"],
    forbidden_phrases=["모르겠습니다"],
    fail_on_violation=True,
)
```

#### `GoalAlignmentConfig` — 목표 정렬 점수 · 부분 달성 인정

태스크 목표와 실제 달성 결과의 정렬도를 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `use_keyword_overlap` | `bool` | `True` | 질문 키워드 ↔ 도구명 오버랩 계산 |
| `goal_tool_map` | `dict[str, list[str]]` | `{}` | 목표 키워드 → 도구 목록 매핑 |
| `alignment_threshold` | `float` | `0.6` | 경고 발생 정렬 임계값 (0.0–1.0) |
| `use_llm_scoring` | `bool` | `False` | LLM-as-Judge 정렬 점수 (opt-in) |
| `llm_blend_weight` | `float` | `0.5` | LLM judge 블렌딩 비중 (0.0=rule only, 1.0=LLM only) |
| `ignore_no_tool_tasks` | `bool` | `True` | 도구 호출 없는 태스크 무시 |

#### `PlanConfig` — 계획 일관성 · 단계 완주율

멀티스텝 에이전트가 계획대로 실행했는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `available_tools` | `list[str]` | `[]` | 실행 가능한 도구 목록 (단계 실행 가능성 검증에 사용) |
| `check_goal_coverage` | `bool` | `True` | 목표 키워드가 계획 단계에 포함되는지 확인 |
| `check_step_ordering` | `bool` | `True` | 단계 순서 논리성 확인 |
| `check_executability` | `bool` | `True` | 각 단계가 사용 가능한 도구로 실행 가능한지 확인 |
| `min_steps` | `int` | `2` | 최소 계획 단계 수 |
| `max_steps` | `int` | `15` | 최대 계획 단계 수 |
| `use_llm_scoring` | `bool` | `False` | LLM-as-Judge 계획 품질 채점 (opt-in) |
| `llm_blend_weight` | `float` | `0.5` | LLM judge 블렌딩 비중 |
| `plan_field` | `str` | `"plan"` | 응답에서 플랜 추출할 JSON 필드명 |
| `steps_field` | `str` | `"steps"` | 플랜 내 단계 필드명 |

> 데코레이터 파라미터명: `plan_tracking=PlanConfig(...)` (`plan=`이 아님)

#### `SubtaskConfig` — 하위 태스크 분해 · 완료율

복잡한 태스크의 하위 분해 품질을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `expected_subtasks` | `list[str]` | `[]` | 예상 하위 태스크 목록 |
| `completion_markers` | `list[str]` | `["done","completed","완료",...]` | 완료 판단 마커 문자열 |
| `min_completion_rate` | `float` | `0.8` | 하위 태스크 완료율 하한 |
| `check_ordering` | `bool` | `False` | 하위 태스크 순서 검증 |
| `auto_extract` | `bool` | `False` | 응답에서 완료된 하위 태스크 자동 추출 |

> 데코레이터 파라미터명: `subtask_tracking=SubtaskConfig(...)` (`subtask=`이 아님)

#### `ContextRetentionConfig` — 대화 컨텍스트 유지율

멀티턴 대화에서 이전 컨텍스트가 유지되는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `key_entities` | `list[str]` | `[]` | 보존 여부를 검증할 핵심 엔티티 목록 |
| `context_arg` | `str` | `"context"` | 컨텍스트 인자 이름 |
| `retention_threshold` | `float` | `0.7` | 엔티티 보존율 합격 하한 |
| `check_original_goal` | `bool` | `True` | 원래 목표 보존 여부 검증 |
| `entity_weight` | `float` | `0.6` | 엔티티 보존 가중치 |
| `goal_weight` | `float` | `0.4` | 목표 보존 가중치 |

#### `KnowledgeRetentionConfig` — 지식 보존 · 활용 점수

에이전트가 주입된 지식을 올바르게 보존하고 활용하는지 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `facts_to_retain` | `list[str]` | `[]` | 보존 여부를 검증할 사실/지식 항목 |
| `seed_turns` | `int` | `2` | 지식이 주입된 초기 턴 수 |
| `check_from_turn` | `int` | `3` | 검증 시작 턴 번호 |
| `retention_threshold` | `float` | `0.6` | 지식 보존율 합격 하한 |
| `allow_implicit_retention` | `bool` | `True` | 암묵적 보존(패러프레이즈 등) 인정 |

---

## Gate B — Behavioral Integrity (행동 무결성)

**"에이전트가 예측 가능하고 안정적으로 행동하는가?"**

루프·범위 이탈·상태 불일치·교착 상태 등 에이전트가 오작동하는 패턴을 탐지합니다. Native 지표 중에서는 Tool Call Efficiency가 비정상 행동의 간접 신호를 제공합니다.

### 연결된 Native 지표

| 지표 | Gate B 연관성 |
|------|---------------|
| **Tool Call Efficiency** | 중복·실패 호출 급증 → 루프 또는 범위 이탈의 간접 지표 |

> 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate B (6개)

#### `LoopDetectionConfig` — 반복 루프 탐지

동일한 도구 호출·응답이 반복되는 루프 패턴을 탐지합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `consecutive_repeat_threshold` | `int` | `3` | N회 연속 동일 도구 호출 시 루프 감지 |
| `window_size` | `int` | `5` | 슬라이딩 윈도우 크기 |
| `duplicate_in_window_threshold` | `int` | `2` | 윈도우 내 중복 도구 호출 허용 횟수 |
| `check_response_loop` | `bool` | `False` | 응답 텍스트 루프 여부 추가 검사 |
| `response_similarity_threshold` | `float` | `0.95` | 응답 유사도 임계값 (`check_response_loop=True` 시) |
| `on_loop_detected` | `str` | `"record"` | 루프 감지 시 동작: `"record"` / `"warn"` / `"fail"` |

```python
loop_detection=LoopDetectionConfig(
    consecutive_repeat_threshold=3,
    window_size=5,
)
```

#### `ScopeConfig` — 범위 일탈 감지 · allowed_tools

에이전트가 허용된 도구 범위를 벗어난 행동을 시도하는지 탐지합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `allowed_tools` | `List[str]` | `[]` | 허용된 도구 목록 |
| `forbidden_tools` | `List[str]` | `[]` | 금지된 도구 목록 |
| `max_tool_calls` | `Optional[int]` | `None` | 태스크당 최대 도구 호출 횟수 |
| `max_unique_tools` | `Optional[int]` | `None` | 태스크당 최대 고유 도구 종류 수 |
| `fail_on_violation` | `bool` | `False` | 위반 시 task 실패 처리 |

> 데코레이터 파라미터명: `scope=ScopeConfig(...)`

#### `ToolParameterSafetyConfig` — 도구 파라미터 안전성 · 금지 패턴

도구 호출 시 전달되는 파라미터에 위험 패턴·금지 키·스키마 위반이 있는지 검사합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `tool_schemas` | `Dict[str, Dict]` | `{}` | 도구별 파라미터 스키마 (위반 검사 기준) |
| `dangerous_patterns` | `List[str]` | `[r"\.\./"...]` | 위험 패턴 정규식 목록 (기본 7개: `../`, `&&`, `\|\|` 등) |
| `forbidden_argument_keys` | `Dict[str, List[str]]` | `{}` | 도구명 → 금지 인자 키 목록 매핑 |
| `max_argument_length` | `int` | `2000` | 인자 값 최대 허용 길이 |
| `fail_on_dangerous` | `bool` | `False` | 위험 패턴 탐지 시 task 실패 처리 |

> 데코레이터 파라미터명: `tool_parameter_safety=ToolParameterSafetyConfig(...)`

#### `ContextWindowConfig` — 컨텍스트 창 활용 효율

모델 컨텍스트 창의 포화도·반복 패턴·정보 밀도를 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `window_size_tokens` | `int` | `128000` | 컨텍스트 창 최대 토큰 수 |
| `warn_at_pct` | `float` | `0.7` | 경고 발생 사용률 임계값 (70%) |
| `saturated_at_pct` | `float` | `0.9` | 포화 판단 사용률 임계값 (90%) |
| `repetition_threshold` | `int` | `3` | 반복 패턴 탐지 임계값 |
| `min_information_density` | `float` | `0.3` | 최소 정보 밀도 (이하면 경고) |

> 데코레이터 파라미터명: `context_window=ContextWindowConfig(...)`

#### `StateConsistencyConfig` — 실행 전후 상태 일관성 · unchanged_keys

에이전트 실행 전후 상태가 예상대로 변경(또는 유지)되는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `state_fn` | `Optional[Callable]` | `None` | 실행 전후 상태 딕셔너리를 반환하는 함수 |
| `expected_changes` | `Dict[str, Any]` | `{}` | 기대 변경 키 → 검증 람다 매핑 |
| `unchanged_keys` | `List[str]` | `[]` | 변경되면 안 되는 상태 키 목록 |
| `fail_on_unexpected_change` | `bool` | `False` | 예상치 못한 상태 변경 시 task 실패 처리 |

> 데코레이터 파라미터명: `state_consistency=StateConsistencyConfig(...)`

#### `DeadlockConfig` — 교착 탐지 · circular delegation · starvation

멀티에이전트 시스템에서 교착 상태, 순환 위임, 기아 현상을 탐지합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `check_circular_delegation` | `bool` | `True` | 순환 위임 탐지 활성화 |
| `check_starvation` | `bool` | `True` | 자원 기아(starvation) 탐지 활성화 |
| `starvation_threshold` | `int` | `3` | 기아 판단 연속 대기 임계값 |
| `check_livelock` | `bool` | `False` | 라이브락 탐지 활성화 |
| `livelock_window` | `int` | `6` | 라이브락 탐지 슬라이딩 윈도우 크기 |
| `max_delegation_depth` | `int` | `10` | 최대 위임 깊이 |

> 데코레이터 파라미터명: `deadlock=DeadlockConfig(...)`

---

## Gate C — Reliability (신뢰성)

**"에이전트가 동일한 입력에 일관된 결과를 내고, 오류 후 복구할 수 있는가?"**

운영 환경에서 에이전트는 간헐적 오류, 네트워크 불안정, 이상 입력에 노출됩니다. Gate C는 이 환경에서도 에이전트가 신뢰성 있게 동작하는지 검증합니다.

### 연결된 Native 지표

| 지표 | Gate C 연관성 |
|------|---------------|
| **Fault Tolerance** | 도구 호출 실패 후 복구율 — tool_calls 성공/실패 데이터가 FaultToleranceConfig의 원시 신호 (RetryCorrectionTracker는 gate score 미기여) |
| **Hallucination Rate** | 출력 사실 충실성 — `1 − hall_rate`가 `_rel_vals`에 직접 기여 (감지 건수 > 0인 경우만) |

> **공식**: `retry_success_rate = succeeded_after_retry / retried_tasks × 100`  
> 🟢 ≥80% / 🟡 60–80% / 🔴 <60%  
> → 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate C (5개)

#### `ReproducibilityConfig` — 동일 입력 반복 실행 일관성

동일한 입력에 대해 여러 번 실행해도 일관된 결과가 나오는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `runs` | `int` | `3` | 동일 입력 반복 실행 횟수 |
| `similarity_measure` | `str` | `"token_f1"` | 유사도 측정 방식: `"token_f1"` / `"jaccard"` / `"exact"` |
| `reproducibility_threshold` | `float` | `0.85` | 재현성 합격 임계값 |
| `fail_on_low_reproducibility` | `bool` | `False` | 임계값 미달 시 task 실패 처리 |
| `skip_side_effects` | `bool` | `False` | 부수효과 있는 함수 건너뜀 |

> 데코레이터 파라미터명: `reproducibility=ReproducibilityConfig(...)`

```python
reproducibility=ReproducibilityConfig(
    runs=3,
    similarity_measure="token_f1",
    reproducibility_threshold=0.9,
)
```

#### `FaultToleranceConfig` — 오류 후 복구율 · 정상 완료 비율

오류 발생 후 에이전트가 폴백 도구를 사용하여 복구하는 능력을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `check_fallback_attempts` | `bool` | `True` | 실패 후 폴백 도구 사용 여부 추적 |
| `partial_success_threshold` | `float` | `0.5` | 부분 성공 인정 임계값 |
| `score_recovery_quality` | `bool` | `True` | 폴백 복구 품질 채점 여부 |
| `expected_fallback_tools` | `Dict[str, List[str]]` | `{}` | 도구명 → 폴백 도구 목록 매핑 |

> 데코레이터 파라미터명: `fault_tolerance=FaultToleranceConfig(...)`

#### `GracefulDegradationConfig` — 품질 하한 · partial_result_markers

장애/저하 상황에서도 최소 품질 하한을 보장하는지 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `partial_result_markers` | `List[str]` | `["partial","incomplete",...]` | 부분 결과 마커 문자열 목록 (기본 6개) |
| `quality_floor` | `float` | `0.3` | 허용 최소 품질 점수 하한 |
| `detect_timeout_fallback` | `bool` | `True` | 타임아웃 폴백 탐지 여부 |
| `empty_response_penalty` | `float` | `1.0` | 빈 응답 페널티 |
| `check_error_acknowledgment` | `bool` | `True` | 오류 인정 표현 검사 여부 |

> 데코레이터 파라미터명: `graceful_degradation=GracefulDegradationConfig(...)`

#### `RetryConsistencyConfig` — 재시도 간 응답 일관성

재시도 횟수와 성공 여부를 기반으로 재시도 효율성과 개선 여부를 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `group_by_task_prefix` | `bool` | `True` | 태스크 접두사 기준 그룹화 여부 |
| `improvement_threshold` | `float` | `0.1` | 재시도 개선 최소 임계값 |
| `penalize_degradation` | `bool` | `True` | 재시도 후 성능 저하 시 감점 |
| `min_retry_count` | `int` | `2` | 일관성 측정에 필요한 최소 재시도 횟수 |

> 데코레이터 파라미터명: `retry_consistency=RetryConsistencyConfig(...)`

#### `IdempotencyConfig` — 멱등성 검증 · 중복 실행 안전성

도구 호출이 반복 실행 시 부작용을 발생시키는지 평가합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `non_idempotent_patterns` | `List[str]` | `["create","delete","insert",...]` | 비멱등 도구 패턴 목록 (기본 10개) |
| `duplicate_detection_markers` | `List[str]` | `["already","duplicate",...]` | 중복 감지 응답 마커 목록 |
| `non_idempotent_penalty` | `float` | `0.2` | 비멱등 도구 사용 시 감점 |
| `warn_on_non_idempotent` | `bool` | `True` | 비멱등 도구 사용 시 경고 |

> 데코레이터 파라미터명: `idempotency=IdempotencyConfig(...)`

---

## Gate D — Performance Contract (성능 계약)

**"에이전트가 SLA·비용·토큰 예산을 준수하는가?"**

운영팀이 에이전트 시스템에 서비스 수준 협약을 맺는 기준입니다. Latency와 Token Economy Native 지표가 원시 측정값을 제공하고, Harness Config D 그룹이 계약 임계값을 설정합니다.

### 연결된 Native 지표

| 지표 | 핵심 역할 | 배포 기준 |
|------|-----------|-----------|
| **Latency** | P50·P90·P95·P99·TTFT 측정 | 🟢 P95 <3s / 🟡 3–5s / 🔴 ≥5s |
| **Token Economy** | 토큰 사용량 + 비용 추정 | 🟢 <$0.01/태스크 / 🔴 ≥$0.05 |

> **Latency 공식**: 측정값 `TaskResult.execution_time` (초)  
> **비용 공식**: `Cost = (input_tokens × input_price + output_tokens × output_price) / 1000`  
> → 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate D (5개)

#### `SLAConfig` — SLA 응답시간 임계값 · P95/P99 위반율

서비스 수준 협약(SLA)의 응답시간 기준을 정의합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `p95_ms` | `float` | `5000.0` | P95 응답시간 합격 기준(밀리초) |
| `p99_ms` | `float` | `10000.0` | P99 응답시간 합격 기준(밀리초) |
| `ttft_ms` | `Optional[float]` | `None` | TTFT 허용 상한(밀리초, None = 제한 없음) |
| `breach_window` | `int` | `10` | 위반 집계 슬라이딩 윈도우 크기 |
| `warn_threshold` | `int` | `2` | 경고 발생 위반 횟수 |
| `fail_threshold` | `int` | `5` | 실패 판정 위반 횟수 |
| `max_cost_per_task` | `Optional[float]` | `None` | 태스크당 최대 허용 비용($) |
| `budget_usd` | `Optional[float]` | `None` | 전체 예산 상한($) |
| `token_limit` | `Optional[int]` | `None` | 태스크당 최대 허용 토큰 수 |

> 데코레이터 파라미터명: `sla=SLAConfig(...)`

```python
sla=SLAConfig(
    p95_ms=3000.0,
    p99_ms=5000.0,
    warn_threshold=2,
    fail_threshold=5,
)
```

#### `EfficiencyConfig` — 토큰 효율 · 도구 호출 대비 완료율

비용 대비 완료율(ROI)을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `cost_unit` | `str` | `"tokens"` | 비용 단위: `"tokens"` / `"usd"` / `"time_ms"` |
| `target_cost_per_completion` | `Optional[float]` | `None` | 태스크당 목표 비용 (None = 제한 없음) |
| `penalize_failed_tokens` | `bool` | `True` | 실패 태스크의 토큰도 비용에 포함 |
| `warn_ratio` | `float` | `2.0` | 목표 대비 경고 배율 |
| `fail_ratio` | `float` | `4.0` | 목표 대비 실패 배율 |

> 데코레이터 파라미터명: `efficiency=EfficiencyConfig(...)`

#### `ResourceBudgetConfig` — 토큰 예산 · 비용 상한

배포 환경에서 소비 가능한 자원의 상한을 정의합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_tokens` | `Optional[int]` | `None` | 태스크당 최대 허용 토큰 수 |
| `max_cost_usd` | `Optional[float]` | `None` | 태스크당 최대 허용 비용($) |
| `max_execution_time_ms` | `Optional[float]` | `None` | 태스크당 최대 실행 시간(밀리초) |
| `warn_at_pct` | `float` | `0.8` | 예산 사용률 경고 임계값 (80%) |
| `count_failed_tokens` | `bool` | `True` | 실패 태스크 토큰도 예산에 포함 |
| `rollover` | `bool` | `False` | 미사용 예산 다음 태스크 이월 여부 |

> 데코레이터 파라미터명: `resource_budget=ResourceBudgetConfig(...)`

#### `TTFTVariabilityConfig`† — TTFT 표준편차 · P95/P50 비율

스트리밍 에이전트의 첫 번째 토큰 도달 시간 변동성을 측정합니다.

> †**monitor 수준 자동 집계** — 데코레이터 파라미터로 전달하지 않아도 됩니다 (≥5 tasks 필요).

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_stddev_ms` | `float` | `500.0` | TTFT 표준편차 허용 상한(밀리초) |
| `max_p95_p50_ratio` | `float` | `3.0` | P95/P50 비율 상한 (변동성 지표) |
| `min_samples` | `int` | `5` | 변동성 측정에 필요한 최소 샘플 수 |
| `remove_outliers` | `bool` | `True` | 이상치 제거 후 통계 계산 |

#### `CostPredictabilityConfig`† — task_type별 토큰 CV · 비용 예측 가능성

태스크 유형별 비용 변동 계수(CV)를 측정합니다.

> †**monitor 수준 자동 집계** — 데코레이터 파라미터로 전달하지 않아도 됩니다 (≥5 tasks 필요).

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_coefficient_of_variation` | `float` | `0.3` | 허용 최대 비용 변동 계수(CV) |
| `outlier_multiplier` | `float` | `3.0` | 이상치 판단 배율 (IQR 기반) |
| `min_samples` | `int` | `5` | 측정에 필요한 최소 샘플 수 |
| `cost_metric` | `str` | `"tokens"` | 비용 지표: `"tokens"` / `"usd"` / `"time_ms"` |

---

## Gate E — Security Boundary (보안 경계)

**"에이전트가 허용된 보안 경계 안에서만 동작하는가?"**

보안 에이전트의 배포 전 필수 관문입니다. Native 보안 5개 지표가 실제 공격 탐지를 수행하고, Harness Config E 그룹이 위협 대응 정책을 정의합니다.

활성화: `PerformanceMonitor(enable_security_metrics=True)` 또는 `PerformanceMonitor.for_secure_agents()`

### 연결된 Native 지표 (보안 5개)

| 지표 | 탐지 내용 | 배포 기준 |
|------|-----------|-----------|
| **Input Sanitization** | SQL·Command Injection, XSS, Prompt Injection | 🔴 Threat rate >5%: 배포 차단 |
| **Output Leakage** | API Key, 신용카드, 이메일, 개인정보 유출 | 🔴 Critical 1건도 배포 차단 |
| **Tool Authorization** | 허가되지 않은 도구 호출 | 🔴 unauthorized_calls >0: 배포 차단 |
| **Privilege Escalation** | read→write→admin 수직 권한 상승 | 🔴 high_risk_events >0: 배포 차단 |
| **Tool Chain Attack** | 데이터 탈취, 래터럴 무브먼트 등 연쇄 공격 | 🔴 exfiltration >0: 배포 차단 |

> → 상세 탐지 패턴·API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate E (3개)

#### `ThreatSeverityConfig` — 위협 심각도 분류 · 임계값 차단

탐지된 위협의 심각도 분류 기준과 자동 차단 임계값을 설정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `severity_weights` | `Dict[str, float]` | `{}` | 위협 유형별 CVSS 가중치 매핑 |
| `warn_score` | `float` | `4.0` | 경고 발생 위협 심각도 점수 하한 |
| `fail_score` | `float` | `7.0` | 실패 판정 위협 심각도 점수 하한 |
| `fail_on_critical` | `bool` | `True` | Critical 위협 탐지 시 task 실패 처리 |

> 데코레이터 파라미터명: `threat_severity=ThreatSeverityConfig(...)`

```python
threat_severity=ThreatSeverityConfig(
    fail_score=7.0,
    fail_on_critical=True,
)
```

#### `ComplianceConfig` — 규정 준수 패턴 · PII 탐지

PII 노출 및 컴플라이언스 프레임워크 위반을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `pii_categories` | `List[str]` | `["name","email","phone",...]` | 탐지할 PII 카테고리 목록 (기본 7개) |
| `compliance_framework` | `str` | `"general"` | 규정 프레임워크: `"gdpr"` / `"hipaa"` / `"general"` |
| `require_data_minimization` | `bool` | `True` | 데이터 최소화 원칙 준수 검사 |
| `forbidden_data_patterns` | `List[str]` | `[]` | 출력 금지 데이터 패턴 (정규식) |
| `check_consent_language` | `bool` | `False` | 동의 언어 포함 여부 검사 |
| `violation_severity` | `str` | `"high"` | 위반 심각도 분류 |

> 데코레이터 파라미터명: `compliance=ComplianceConfig(...)`

#### `ThreatResponseConfig` — 위협 탐지 후 대응 행동 검증

보안 위협이 탐지되었을 때 에이전트가 적절히 차단·에스컬레이션·중단하는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `isolation_markers` | `List[str]` | `["blocked","rejected",...]` | 격리/차단 응답 마커 목록 |
| `escalation_markers` | `List[str]` | `["escalate","report",...]` | 에스컬레이션 응답 마커 목록 |
| `abort_markers` | `List[str]` | `["abort","stop",...]` | 중단/종료 응답 마커 목록 |
| `score_clean_tasks` | `bool` | `True` | 위협 없는 정상 태스크도 채점 |
| `no_response_penalty` | `float` | `0.5` | 위협 탐지 후 무응답 시 페널티 |

> 데코레이터 파라미터명: `threat_response=ThreatResponseConfig(...)`

---

## Gate F — Multi-Agent Coordination (멀티에이전트 조율)

**"복수의 에이전트가 효과적으로 협력하여 목표를 달성하는가?"**

멀티에이전트 시스템의 배포 판단 관문입니다. Agent Coordination, Tool Selection Native 지표가 실제 협력 품질을 측정하고, Harness Config F 그룹이 합격 기준을 정의합니다.

### 연결된 Native 지표

| 지표 | 핵심 역할 | 배포 기준 |
|------|-----------|-----------|
| **Tool Selection Accuracy** | F1 기반 도구 선택 정확도 — `avg_f1_score / 100`이 `_f_vals`에 기여 | 🟢 ≥90% / 🟡 80–90% / 🔴 <80% |
| **Agent Coordination** | 에이전트 간 조율 점수 — `overall_score / 10`이 `_f_vals`에 기여 | 🟢 ≥8/10 / 🟡 6–8 / 🔴 <6 |

> **주의**: WorkflowExecutionTracker와 ToolCallAnalyzer(Tool Call Efficiency)는 gate score 미기여 — 각각 chain_steps 추적 전용, Gate G 기여 지표임

> → 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate F (4개)

#### `ConsensusConfig` — 에이전트 간 합의율 · 분쟁 탐지

여러 에이전트가 결정을 내릴 때 합의에 도달하는 능력을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `consensus_method` | `str` | `"majority"` | 합의 방식: `"majority"` / `"weighted"` / `"unanimity"` |
| `agent_weights` | `Dict[str, float]` | `{}` | 에이전트별 가중치 (weighted 방식 시 사용) |
| `similarity_threshold` | `float` | `0.7` | 응답 유사도 합의 판단 임계값 |
| `select_consensus_response` | `bool` | `False` | 합의된 응답을 최종 결과로 선택 |

> 데코레이터 파라미터명: `consensus=ConsensusConfig(...)` (`@batch_eval`과 함께 사용 시 가장 효과적)

```python
consensus=ConsensusConfig(
    consensus_method="weighted",
    agent_weights={"expert": 3.0},
)
```

#### `PropagationConfig` — 정보 전파 정확도 · 왜곡 감지

에이전트 간 정보 전달 과정에서 핵심 사실이 충실히 전파되는지 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `source_agent` | `str` | `""` | 정보 원천 에이전트 이름 |
| `key_facts` | `List[str]` | `[]` | 전파 여부를 검증할 핵심 사실 목록 |
| `check_in_response` | `bool` | `True` | 응답 텍스트에서 사실 포함 여부 확인 |
| `check_in_tool_calls` | `bool` | `False` | 도구 호출 인자에서 사실 포함 여부 확인 |
| `similarity_threshold` | `float` | `0.7` | 사실 일치 판단 유사도 임계값 |
| `penalize_distortion` | `bool` | `True` | 왜곡된 정보 전파 시 감점 |

> 데코레이터 파라미터명: `propagation=PropagationConfig(...)`

#### `AgentRoleConfig` — 역할 준수율 · 역할 위반 탐지

각 에이전트가 지정된 역할을 벗어나지 않는지 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `role_name` | `str` | `""` | 평가 대상 에이전트의 역할 이름 |
| `allowed_tools` | `List[str]` | `[]` | 역할 내 허용 도구 목록 |
| `forbidden_tools` | `List[str]` | `[]` | 역할 내 금지 도구 목록 |
| `allowed_action_keywords` | `List[str]` | `[]` | 역할 내 허용 행동 키워드 |
| `forbidden_action_keywords` | `List[str]` | `[]` | 역할 내 금지 행동 키워드 |
| `check_tool_role_alignment` | `bool` | `True` | 도구-역할 정렬 검사 |
| `role_violation_penalty` | `float` | `0.3` | 역할 위반 시 감점 |

> 데코레이터 파라미터명: `agent_role=AgentRoleConfig(...)`

#### `ConflictResolutionConfig` — 충돌 해결 패턴 · 해결 시간

에이전트 간 충돌 감지 및 해결 품질을 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `conflict_markers` | `List[str]` | `["disagree","conflict",...]` | 충돌 감지 마커 목록 |
| `resolution_markers` | `List[str]` | `["resolved","consensus",...]` | 해결 감지 마커 목록 |
| `check_resolution_quality` | `bool` | `True` | 해결 품질 채점 여부 |
| `require_explanation` | `bool` | `False` | 해결 과정 설명 필수 여부 |
| `unresolved_penalty` | `float` | `0.5` | 미해결 충돌 페널티 |
| `expect_escalation_on_fail` | `bool` | `False` | 해결 실패 시 에스컬레이션 기대 여부 |

> 데코레이터 파라미터명: `conflict_resolution=ConflictResolutionConfig(...)`

---

## Gate G — Observability (관찰 가능성)

**"에이전트의 내부 동작을 이해하고 디버깅할 수 있는가?"**

운영 환경에서 에이전트 장애를 빠르게 진단하기 위한 관문입니다. Response Quality Native 지표가 응답 품질의 관찰 가능한 신호를 제공합니다.

### 연결된 Native 지표

| 지표 | Gate G 연관성 |
|------|---------------|
| **Response Quality (5차원)** | 관찰 가능한 품질 차원 — Relevance·Completeness·Accuracy·Clarity·Usefulness |
| **Hallucination Rate** | 환각 모니터링 신호 — `1 − hall_rate`가 `_obs_vals`에 기여 (Gate C에도 동시 기여, 자세한 내용은 [Hallucination Rate 레퍼런스](#hallucination-rate-규칙-기반) 참조) |

> **Quality Score 공식**: `Σ(dimension_score × weight)`, 범위 0–5  
> 🟢 ≥4.5 (A) / 🟡 4.0–4.5 (B) / 🟠 3.5–4.0 (C) / 🔴 <3.0 (F)  
> → 상세 API는 [Native Tracker 레퍼런스](#native-tracker-레퍼런스) 참조

### Harness Config — Gate G (4개)

#### `ExplainabilityConfig` — 추론 과정 설명 가능성

에이전트가 결론에 도달하는 추론 과정이 설명 가능한지 측정합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `require_reasoning` | `bool` | `True` | 추론 마커 포함 필수 여부 |
| `reasoning_markers` | `List[str]` | `["because","therefore",...]` | 추론 마커 키워드 목록 (기본 7개) |
| `require_uncertainty_expression` | `bool` | `False` | 불확실성 표현 포함 필수 여부 |
| `uncertainty_markers` | `List[str]` | `["uncertain","may",...]` | 불확실성 표현 마커 목록 |
| `require_citations` | `bool` | `False` | 인용 출처 포함 필수 여부 |
| `citation_markers` | `List[str]` | `["according to","based on",...]` | 인용 마커 목록 |
| `min_reasoning_length` | `int` | `20` | 추론 텍스트 최소 길이(문자 수) |
| `check_action_explanation_alignment` | `bool` | `False` | 행동-설명 정렬 검사 여부 |

> 데코레이터 파라미터명: `explainability=ExplainabilityConfig(...)`

```python
explainability=ExplainabilityConfig(
    require_reasoning=True,
    min_reasoning_length=50,
    require_citations=True,
)
```

#### `ObservabilityConfig` — 내부 상태 노출 · 추적 가능성

OTEL 스팬 완성도 및 감사 이벤트 SLO를 검증합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `required_span_attributes` | `List[str]` | `["task_id","task_type","execution_time"]` | OTEL 스팬에 필수로 포함될 속성 목록 |
| `check_trace_continuity` | `bool` | `True` | 스팬 연속성(부모-자식 관계) 검사 |
| `audit_events` | `List[str]` | `[]` | 감사 이벤트 유형 목록 |
| `min_coverage` | `float` | `0.95` | 추적 커버리지 합격 하한 |

> 데코레이터 파라미터명: `observability=ObservabilityConfig(...)`

#### `ErrorDiagnosisConfig` — 오류 원인 진단 정확도

실패 응답이 오류를 인정하고, 근본 원인을 제시하며, 대안을 제안하는지 평가합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `failure_acknowledgment_markers` | `List[str]` | `["failed","unable",...]` | 오류 인정 표현 마커 목록 |
| `root_cause_markers` | `List[str]` | `["because","due to",...]` | 근본 원인 제시 마커 목록 |
| `suggestion_markers` | `List[str]` | `["try","suggest",...]` | 대안 제안 마커 목록 |
| `only_on_failure` | `bool` | `True` | 실패 태스크에만 채점 적용 |
| `acknowledgment_weight` | `float` | `0.3` | 오류 인정 가중치 |
| `root_cause_weight` | `float` | `0.5` | 근본 원인 분석 가중치 |
| `suggestion_weight` | `float` | `0.2` | 대안 제안 가중치 |

> 데코레이터 파라미터명: `error_diagnosis=ErrorDiagnosisConfig(...)`

#### `LatencyAttributionConfig` — 지연 원인 분석 · 구간별 기여도

전체 실행 시간 중 도구·모델·네트워크·미귀속 지연의 비율을 분석합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `tool_latency_key` | `str` | `"tool_latencies"` | 태스크 extra에서 도구 지연 읽을 키 |
| `model_latency_key` | `str` | `"model_latency_ms"` | 태스크 extra에서 모델 지연 읽을 키 |
| `network_latency_key` | `str` | `"network_latency_ms"` | 태스크 extra에서 네트워크 지연 읽을 키 |
| `max_tool_time_ratio` | `float` | `0.6` | 도구 지연 최대 비율 (전체 실행 시간 대비) |
| `max_unattributed_ratio` | `float` | `0.3` | 미귀속 지연 최대 비율 |

> 데코레이터 파라미터명: `latency_attribution=LatencyAttributionConfig(...)`

---

## L3 — Semantic Evaluation (의미론적 평가)

Gate A–G의 규칙 기반 측정을 보완하는 LLM 기반 의미론적 평가입니다. Gate A(정확도), Gate G(품질)와 긴밀하게 연관됩니다.

### LLMJudge (네이티브, 기본 설치에 포함)

설치: `pip install agent-evaluator` (기본 포함)  
필요: `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`  
활성: `llm_judge=LLMJudgeConfig()`

**측정 차원 (최대 7+개)**

| 차원 | 범위 | 활성 조건 |
|------|------|-----------|
| `completeness` | 0–5 | 기본 |
| `relevance` | 0–5 | 기본 |
| `factual_consistency` | 0–5 | 기본 |
| `toxicity` | 0–5 (낮을수록 좋음) | 기본 |
| `bias` | 0–5 (낮을수록 좋음) | 기본 |
| `safety_score` | 0–1 | 기본 (`= (10 - toxicity - bias) / 10`) |
| `faithfulness` | 0–5 | `rag_mode=True` + context |
| `criteria_scores` | 0–5 each | `criteria=[...]` 지정 시 |
| `criteria_overall` | 0–5 | `criteria=[...]` 지정 시 평균 |

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

# 기본 5차원 + safety_score
@agent_eval(monitor, task_type="qa",
    llm_judge=LLMJudgeConfig(sample_rate=0.1)   # 10%만 채점 (비용 절감)
)
def agent(question, ground_truth=""): ...

# RAG Faithfulness (Ragas 대체)
@agent_eval(monitor, rag_mode=True,
    llm_judge=LLMJudgeConfig()
)
def rag_agent(question, context="", ground_truth=""): ...
# → scores["faithfulness"]: 0–5 (5 = 모든 주장이 컨텍스트에 근거)

# G-Eval 커스텀 기준 (DeepEval 대체)
@agent_eval(monitor,
    llm_judge=LLMJudgeConfig(criteria=["medical_accuracy", "patient_safety"])
)
def medical_agent(question, ground_truth=""): ...
# → scores["criteria_scores"]["medical_accuracy"]: 0–5
# → scores["criteria_overall"]: 커스텀 기준 평균
```

### DeepEval + Ragas (`[eval]` extra)

설치: `pip install agent-evaluator[eval]`  
필요: `OPENAI_API_KEY`  
사용: `HybridPerformanceMonitor`

> LLMJudge가 DeepEval G-Eval과 Ragas Faithfulness를 외부 패키지 없이 대체합니다 (v0.7.6+).  
> `HybridPerformanceMonitor`는 더 높은 정확도(NLI 기반 90–95%)가 필요하거나 DeepEval/Ragas 생태계와 통합할 때 사용하세요.

**DeepEval 지표 (5개)**

| 지표 | 범위 | 방향 | 기준 |
|------|------|------|------|
| G-Eval | 0–1 | ⬆ 높을수록 좋음 | ≥0.9 우수 |
| Hallucination Score | 0–1 | ⬆ (= 환각 없음) | ≥0.9 우수 |
| Toxicity | 0–1 | ⬇ 낮을수록 좋음 | <0.1 안전 |
| Bias | 0–1 | ⬇ 낮을수록 좋음 | <0.1 공정 |
| Answer Relevancy | 0–1 | ⬆ 높을수록 좋음 | ≥0.9 우수 |

> ⚠️ Hallucination Score는 L1 Hallucination Rate(규칙 기반, ⬇ 낮을수록 좋음)와 **방향이 반대**입니다.

**Ragas 지표 (4개, RAG 전용)**

| 지표 | 공식 요약 | 기준 |
|------|----------|------|
| Faithfulness | 컨텍스트 지원 주장 / 전체 주장 | ≥0.9 신뢰 |
| Answer Relevancy | 역생성 질문 ↔ 원래 질문 유사도 | ≥0.9 우수 |
| Context Precision | 관련 컨텍스트 / 전체 검색 컨텍스트 | ≥0.9 우수 |
| Context Recall | 검색 관련 정보 / 필요한 전체 정보 | ≥0.9 우수 |

```python
from agent_evaluator import HybridPerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = HybridPerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="information_retrieval",
    rag_mode=True, context_arg="context"
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

---

## Native Tracker 레퍼런스

> 공식·출력키·API 시그니처 상세 참조. Gate 컨텍스트에서 Native 지표가 어떻게 동작하는지 설명합니다.

---

### TCR — Task Completion Rate

**Gate A 핵심 지표**

**공식**

```
TCR = Σ(completion_score) / task_count × 100
```

`completion_score`는 `TaskResult` 필드 (0.0–1.0). `create_taskresult()` 사용 시 자동 계산.

> **task_type별 완료 판정 (v0.8.0+)**
> - `code_generation`/`coding`: AST 파싱 성공 시 1.0, 실패 시 길이 기반
> - `tool_use`: `tool_calls` 비어 있으면 0.6 (도구 미사용 부분 완료)
> - 기타: 응답 길이 기반 + `ground_truth` 있으면 유사도 기반

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | ≥ 95 |
| 🟡 양호 | 85–95 |
| 🟠 보통 | 70–85 |
| 🔴 개선 필요 | < 70 |

**출력 키**

```python
report.task_completion_rate                          # float (0–100)
report.to_dict()["tcr_data"]["success_rate"]         # float (0–1)
report.to_dict()["tcr_data"]["total_tasks"]          # int
report.to_dict()["tcr_data"]["successful_tasks"]     # int
```

---

### Accuracy

**Gate A 핵심 지표** — `overall_accuracy / 100` 값이 Gate A `_a_vals`에 직접 기여 (AccuracyEvaluator 평가 건수 > 0인 경우)

**공식 — QA (가중 조합)**

```
accuracy = 0.4 × TokenOverlapF1 + 0.3 × Jaccard + 0.2 × LCS + 0.1 × CharSimilarity
```

| 지표 | 가중치 | 방식 |
|------|--------|------|
| TokenOverlapF1 | 40% | 토큰 F1 (정밀도×재현율 조화평균) — 긴 응답 패딩 방지 |
| Jaccard | 30% | 집합 교집합/합집합 |
| LCS | 20% | 최장 공통 부분 수열 |
| CharSimilarity | 10% | Levenshtein 거리 기반 (문자 순서 반영, v0.8.0+) |

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
stats = monitor.accuracy_evaluator.get_accuracy_scores()
# {"overall_accuracy": float, "median_accuracy": float, ...}

by_type = monitor.accuracy_evaluator.get_accuracy_by_type()
# {"qa": float, "code_generation": float, ...}
```

---

### Latency

**Gate D 핵심 지표**

**측정값**: `TaskResult.execution_time` (초 단위)

**임계값**

| 등급 | 범위 (초) |
|------|----------|
| 🟢 우수 | < 1 |
| 🟡 양호 | 1–3 |
| 🟠 보통 | 3–5 |
| 🔴 느림 | ≥ 5 |

**주요 API**

```python
stats = monitor.latency_tracker.get_latency_stats()
# {"p50": float, "p95": float, "p99": float, "mean": float, "sla_compliance_rate": float}

# TTFT (Time-To-First-Token) — 스트리밍 에이전트 전용 (v0.7.2+)
monitor.latency_tracker.track_ttft(task_id, ttft_seconds=0.3)
ttft_stats = monitor.latency_tracker.get_ttft_stats()
# {"mean_ttft": float, "p50_ttft": float, "p95_ttft": float}
```

> 데코레이터 방식에서 generator 함수의 첫 청크 yield 시점에 TTFT가 자동 기록됩니다.

---

### Token Economy

**Gate D 핵심 지표**

**공식**

```
Cost = (input_tokens × input_price + output_tokens × output_price) / 1000
```

**설정**

```python
monitor = PerformanceMonitor(
    pricing={
        "input": 0.00005,   # GPT-5-nano: $0.05/1M tokens
        "output": 0.0006,
    }
)
monitor.token_tracker.update_pricing({"input": 0.003, "output": 0.015})
```

**임계값 (태스크당 비용)**

| 등급 | 범위 |
|------|------|
| 🟢 효율적 | < $0.01 |
| 🟡 보통 | $0.01–$0.05 |
| 🔴 비효율 | ≥ $0.05 |

**주요 API**

```python
stats = monitor.token_tracker.get_usage_stats()
# {"total_tokens": int, "avg_tokens_per_task": float, "estimated_cost": float, ...}
```

---

### Tool Call Efficiency

**Gate B·F 연관 지표**

**공식**

```
Tool Efficiency = 100 - waste_rate × 100

waste_rate = (redundant_calls + failed_calls) / total_calls
```

중복 판정: `(tool_name, json.dumps(parameters, sort_keys=True))` 조합이 동일한 경우.

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 비효율 | < 70 |

**주요 API**

```python
metrics = monitor.tool_analyzer.analyze_execution(task_id, tool_calls)
# {"total_calls": int, "unique_tools": int, "redundant_calls": int,
#  "failed_calls": int, "efficiency_score": float}

stats = monitor.tool_analyzer.get_efficiency_stats()
# {"avg_efficiency_score": float, "redundancy_rate": float, "failure_rate": float}
```

---

### Retry & Error Recovery

**Gate C 핵심 지표**

**공식**

```
retry_rate         = retried_tasks / total_tasks × 100
retry_success_rate = succeeded_after_retry / retried_tasks × 100
```

**임계값** (재시도 성공률 %)

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 80 |
| 🟡 양호 | 60–80 |
| 🟠 보통 | 40–60 |
| 🔴 불량 | < 40 |

**주요 API**

```python
stats = monitor.retry_tracker.get_retry_statistics()
# {"retry_rate": float, "retry_success_rate": float, "avg_retry_count": float}
```

---

### Tool Selection Accuracy

**Gate F 핵심 지표**

**공식 (F1 기반)**

```python
expected_set = set(expected_tools)
actual_set   = set(actual_tools)

TP = len(expected_set & actual_set)
FP = len(actual_set - expected_set)
FN = len(expected_set - actual_set)

precision = TP / len(actual_set)    if actual_set    else 0
recall    = TP / len(expected_set)  if expected_set  else 0
f1        = 2 * precision * recall / (precision + recall) if (precision+recall) > 0 else 0

accuracy  = f1 * 100  # %
```

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
result = monitor.tool_selection_tracker.evaluate_selection(
    task_id="task_001",
    expected_tools=["search", "calculator"],
    actual_tools=["search"],
)
# {"precision": float, "recall": float, "f1_score": float, "accuracy": float}

stats = monitor.tool_selection_tracker.get_accuracy_stats()
# {"avg_accuracy": float, "avg_precision": float, "avg_recall": float}
```

---

### Agent Coordination

**Gate F 핵심 지표**

**공식**

```
Coordination Score = success_rate×0.5 + diversity_score×0.3 + balance_score×0.2

success_rate    = 성공 상호작용 / 전체 상호작용 × 100
diversity_score = min(고유 에이전트 수 / 5, 1.0) × 10
balance_score   = 상호작용 유형 수 / 3 × 10
```

허용 interaction_type: `delegation`, `communication`, `collaboration`

**임계값 (0–10점)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 8 |
| 🟡 양호 | 6–8 |
| 🟠 보통 | 4–6 |
| 🔴 개선 필요 | < 4 |

**주요 API**

```python
monitor.agent_coordination_tracker.track_interaction(
    task_id, from_agent, to_agent,
    interaction_type="delegation", success=True,
)
score = monitor.agent_coordination_tracker.calculate_coordination_score()
# {"score": float(0–10), "success_rate": float, "total_interactions": int}
```

---

### Workflow Execution

**Gate F 핵심 지표**

**공식**

```
step_success_rate = 성공 스텝 수 / 전체 스텝 수 × 100
task_success_rate = 모든 스텝이 성공한 태스크 수 / 전체 태스크 수 × 100
```

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
monitor.workflow_tracker.track_step(
    task_id, step_name="retrieve", step_type="node",
    success=True, execution_time=0.5, framework="langgraph",
)
stats = monitor.workflow_tracker.calculate_execution_success_rate(task_id="t1")
# {"step_success_rate": float, "task_success_rate": float,
#  "total_steps": int, "avg_steps_per_task": float}

efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
# LangGraph 전용
```

---

### Response Quality

**Gate G 핵심 지표**

**5차원 평가 (각 0–5점)**

| 차원 | 가중치 | 계산 방식 |
|------|--------|----------|
| Relevance | 25% | 요청 단어 ∩ 응답 단어 / 요청 단어 수 × 5 |
| Completeness | 25% | expected_elements 중 응답에 포함된 비율 × 5 |
| Accuracy | 20% | 기본값 4.0 (ground_truth 기반 피드백 필요) |
| Clarity | 15% | 단어 수 + 구조 유무 기반 |
| Usefulness | 15% | 기본값 4.0 |

**공식**: `Quality Score = Σ(dimension_score × weight)`, 범위 0–5

**임계값**

| 등급 | 범위 (0–5점) |
|------|-------------|
| 🟢 A (우수) | ≥ 4.5 |
| 🟡 B (양호) | 4.0–4.5 |
| 🟠 C (보통) | 3.5–4.0 |
| 🟠 D (미흡) | 3.0–3.5 |
| 🔴 F (개선 필요) | < 3.0 |

**주요 API**

```python
stats = monitor.quality_evaluator.get_quality_metrics()
# {"avg_total_score": float, "grade_distribution": {"A":n,...}, "dimension_averages": {...}}
```

---

### Hallucination Rate (규칙 기반)

**Gate C + G 연관 지표** — 활성화 시 `1 − hall_rate`가 Gate C `_rel_vals`(신뢰성)와 Gate G `_obs_vals`(관측성) 양쪽에 기여. 실제 감지 건수(`_detections`)가 0이면 두 Gate 모두 미기여.

활성화: `PerformanceMonitor(enable_hallucination_detection=True)`

**탐지 방법**

| 방법 | 조건 | 심각도 |
|------|------|--------|
| Unsupported Claim | 응답 문장의 컨텍스트 단어 중첩률 < 30% | Medium |
| Numerical Inconsistency | 응답 숫자가 컨텍스트에 없음 | High |

**공식**

```
Hallucination Rate = 환각 플래그 작업 수 / 컨텍스트 있는 작업 수 × 100
```

**임계값**

| 등급 | 범위 (%) |
|------|---------|
| 🟢 우수 | < 1 |
| 🟡 양호 | 1–5 |
| 🟠 보통 | 5–10 |
| 🔴 위험 | ≥ 10 |

> 규칙 기반 탐지: 정확도 70–80%, 무료, < 5ms 오버헤드.  
> L3 DeepEval Hallucination Score(LLM 기반, 90–95%)와 다릅니다.

**주요 API**

```python
stats = monitor.hallucination_detector.get_hallucination_rate()
# {"overall_rate": float(0–1), "tasks_with_hallucinations": int, ...}
```

---

### 보안 5개 지표 (Gate E)

활성화: `PerformanceMonitor(enable_security_metrics=True)` 오버헤드 ~5–15ms

**Input Sanitization — 탐지 패턴**

| 공격 유형 | 예시 | 심각도 |
|----------|------|--------|
| SQL Injection | `'; DROP TABLE`, `UNION SELECT` | 🔴 Critical |
| Command Injection | `rm -rf`, `$(cmd)` | 🔴 Critical |
| Path Traversal | `../`, `/etc/passwd` | 🟠 High |
| XSS | `<script>`, `javascript:` | 🟠 High |
| Prompt Injection | `ignore previous instructions` | 🔴 Critical |

```python
result = monitor.input_sanitizer.evaluate_input(task_id, input_text)
# {"has_sql_injection": bool, "has_prompt_injection": bool,
#  "risk_level": str, "threat_count": int}
stats = monitor.input_sanitizer.get_security_stats()
# {"threat_rate": float, "sql_injection_attempts": int, ...}
```

**Output Leakage — 탐지 대상**

| 유출 유형 | 심각도 |
|----------|--------|
| API Key (`sk-...`, `AIza...`) | 🔴 Critical |
| Password / Credit Card (Luhn) | 🔴 Critical |
| Email / Phone / SSN | 🟠 High |
| Private IP / File Path | 🟡 Medium |

```python
result = monitor.output_leakage_detector.detect_leakage(task_id, output_text)
# {"contains_api_key": bool, "leakage_count": int, "severity": str}
stats = monitor.output_leakage_detector.get_leakage_stats()
# {"leakage_rate": float, "critical_severity_count": int, ...}
```

**Tool Authorization**

```python
monitor = PerformanceMonitor(
    enable_security_metrics=True,
    security_config={"allowed_tools": ["search", "read"], "restricted_tools": ["delete"]},
)
result = monitor.tool_authorizer.track_tool_call(task_id, tool_name, parameters)
# {"is_authorized": bool, "is_restricted": bool, "privilege_level": "read|write|execute|admin"}
stats = monitor.tool_authorizer.get_compliance_stats()
# {"compliance_rate": float, "unauthorized_calls": int, "violation_rate": float}
```

**Privilege Escalation**

```python
result = monitor.privilege_escalation_detector.analyze_privilege_chain(
    task_id,
    tool_calls=[
        {"tool_name": "read_file", "privilege_level": "read"},
        {"tool_name": "exec_cmd", "privilege_level": "execute"},
        {"tool_name": "read_admin", "privilege_level": "admin"},
    ],
)
# {"escalation_detected": bool, "risk_score": int(0–10), "escalation_path": [...]}
stats = monitor.privilege_escalation_detector.get_escalation_stats()
# {"escalation_rate": float, "avg_risk_score": float, "high_risk_events": int}
```

**Tool Chain Attack — 탐지 유형**

| 공격 유형 | 시퀀스 예시 |
|----------|------------|
| Data Exfiltration | `read_database → encode → http_post` |
| Lateral Movement | `get_credentials → ssh_connect → execute_remote` |
| Persistence | `write_cron → create_service → restart` |
| Defense Evasion | `disable_logging → clear_history → delete_logs` |

```python
result = monitor.tool_chain_attack_detector.analyze_tool_chain(
    task_id, tool_sequence=["read_database", "encode", "http_post"]
)
# {"is_suspicious_chain": bool, "attack_types": {...}, "threat_level": str}
stats = monitor.tool_chain_attack_detector.get_attack_stats()
# {"detection_rate": float, "data_exfiltration_detected": int, ...}
```

---

## 리포트에서 지표 읽기

```python
report = monitor.generate_report()
d = report.to_dict()

# Gate A — 목표 달성
d["tcr_data"]["success_rate"]               # float (0–1)
d["accuracy_data"]["overall_accuracy"]      # float (0–100)

# Gate C — 신뢰성
d["retry_data"]["retry_success_rate"]       # float (0–100)

# Gate D — 성능 계약
d["latency_data"]["p95"]                    # float (초)
d["latency_data"]["sla_compliance_rate"]    # float (0–1)
d["token_data"]["estimated_cost"]           # float ($)

# Gate E — 보안 경계
d["security_metrics"]["input_security"]["threat_rate"]           # float (0–100)
d["security_metrics"]["output_leakage"]["leakage_rate"]          # float (0–100)
d["security_metrics"]["authorization"]["compliance_rate"]        # float (0–100)
d["security_metrics"]["privilege_escalation"]["escalation_rate"] # float (0–100)
d["security_metrics"]["attack_detection"]["detection_rate"]      # float (0–100)

# Gate F — 멀티에이전트
d["tool_efficiency"]                                 # float (0–100)
d["tool_selection_accuracy"]                         # float (0–100)
d["coordination_score"]                              # float (0–10)
d["workflow_execution"]["step_success_rate"]         # float (0–100)

# Gate G — 관찰 가능성
d["quality_data"]["avg_total_score"]        # float (0–5)
d["hallucination_data"]["overall_rate"]     # float (0–1)
```

---

## 데코레이터 × 지표 활성화 맵

### 지표 × 데코레이터 지원 매트릭스

| 지표 | `@agent_eval` | `@batch_eval` | `@conversation_eval` | 활성 방법 |
|---|:---:|:---:|:---:|---|
| **Gate A — 목표 달성** | | | | |
| TCR | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 (`completion_fn` 선택) |
| Accuracy | ✅ 자동 | ✅ 자동 | ✅ 자동 | `ground_truth_arg` 존재 시 |
| **Gate B — 행동 무결성** | | | | |
| Tool Call Efficiency | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata.tool_calls |
| **Gate C — 신뢰성** | | | | |
| Retry & Error Recovery | ✅ `retry=RetryConfig(max=N)` | ❌ | ❌ | `RetryConfig(max>1)` + 실제 재시도 |
| Hallucination Rate (C) | ✅ `rag_mode=True` | ✅ `context_arg` 지정 | ❌ | `enable_hallucination_detection=True` + context 존재 시 Gate C에 기여 |
| **Gate D — 성능 계약** | | | | |
| Latency (p50/p95/p99) | ✅ 자동 | ✅ 자동 | ✅ 자동 | 항상 (실행 시간 자동 측정) |
| TTFT | ✅ generator | ✅ `streaming_mode` | ❌ | generator 리턴 또는 스트리밍 모드 |
| Token Economy | ✅ 자동 | ✅ 자동 | ❌ | `framework=` 어댑터 또는 EvalMetadata |
| **Gate E — 보안 경계** | | | | |
| Input Sanitization | ✅ `security=SecurityConfig()` | ❌ | ❌ | `security=SecurityConfig()` |
| Output Leakage | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Authorization | ✅ `security=SecurityConfig()` + `allowed_tools` | ❌ | ❌ | 동일 + 화이트리스트 |
| Privilege Escalation | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| Tool Chain Attack | ✅ `security=SecurityConfig()` | ❌ | ❌ | 동일 |
| **Gate F — 멀티에이전트** | | | | |
| Tool Selection F1 | ✅ `expected_tools_arg` | ✅ `expected_tools_arg` | ❌ | expected_tools + tool_calls 동시 |
| Agent Coordination | ✅ `framework="crewai/autogen"` | ❌ | ❌ | CrewAI/AutoGen 어댑터 또는 EvalMetadata |
| Workflow Execution | ✅ `framework="langchain/langgraph"` | ❌ | ❌ | LangChain/LangGraph 어댑터 |
| **Gate G — 관찰 가능성** | | | | |
| Response Quality (5차원) | ✅ 자동 | ✅ 자동 | ✅ 자동 | response + question 존재 시 |
| Hallucination Rate (G) | ✅ `rag_mode=True` | ✅ `context_arg` 지정 | ❌ | context + `enable_hallucination_detection=True` — Gate C에도 동시 기여 |
| **L3 / LLM Judge** | | | | |
| LLM Judge (5차원) | ✅ `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | 기본 설치에 포함 |
| Faithfulness | ✅ `rag_mode` + `llm_judge=LLMJudgeConfig()` | ❌ | ❌ | context 존재 시 자동 추가 |
| G-Eval 커스텀 기준 | ✅ `llm_judge=LLMJudgeConfig(criteria=[...])` | ❌ | ❌ | criteria 지정 |
| **대화 지표** | | | | |
| Context Retention | ❌ | ❌ | ✅ 자동 | 세션 flush 시 |
| Topic Coherence | ❌ | ❌ | ✅ 자동 | 세션 flush 시 |
| Progressive Depth | ❌ | ❌ | ✅ 자동 | 세션 flush 시 |
| Session Completion | ❌ | ❌ | ✅ 자동 | 세션 flush 시 |
| Per-turn Score | ❌ | ❌ | ✅ `turn_score_fn` | `turn_score_fn` 지정 시 |

### Harness Config 활성화 (33개)

| 파라미터 | Gate | 측정 내용 |
|---|---|---|
| `instructions=InstructionConfig(...)` | A | 지시 이행률·이탈 감지 |
| `goal_alignment=GoalAlignmentConfig(...)` | A | 목표 정렬 점수 |
| `plan_tracking=PlanConfig(...)` | A | 계획 일관성·단계 완주율 |
| `subtask_tracking=SubtaskConfig(...)` | A | 하위 태스크 완료율 |
| `context_retention=ContextRetentionConfig(...)` | A | 대화 컨텍스트 유지율 |
| `knowledge_retention=KnowledgeRetentionConfig(...)` | A | 지식 보존·활용 |
| `loop_detection=LoopDetectionConfig(...)` | B | 반복 루프 탐지 |
| `scope=ScopeConfig(...)` | B | 범위 일탈 감지 |
| `tool_parameter_safety=ToolParameterSafetyConfig(...)` | B | 파라미터 안전성 |
| `context_window=ContextWindowConfig(...)` | B | 컨텍스트 창 효율 |
| `state_consistency=StateConsistencyConfig(...)` | B | 실행 전후 상태 일관성 |
| `deadlock=DeadlockConfig(...)` | B | 교착·순환위임·기아 탐지 |
| `reproducibility=ReproducibilityConfig(...)` | C | 반복 실행 일관성 |
| `fault_tolerance=FaultToleranceConfig(...)` | C | 오류 후 복구율 |
| `graceful_degradation=GracefulDegradationConfig(...)` | C | 품질 하한 |
| `retry_consistency=RetryConsistencyConfig(...)` | C | 재시도 간 일관성 |
| `idempotency=IdempotencyConfig(...)` | C | 멱등성 |
| `sla=SLAConfig(...)` | D | SLA 응답시간 |
| `efficiency=EfficiencyConfig(...)` | D | 토큰 효율 |
| `resource_budget=ResourceBudgetConfig(...)` | D | 토큰 예산·비용 상한 |
| `TTFTVariabilityConfig` (monitor 자동) | D | TTFT 표준편차 |
| `CostPredictabilityConfig` (monitor 자동) | D | 비용 예측 가능성 |
| `threat_severity=ThreatSeverityConfig(...)` | E | 위협 심각도 분류 |
| `compliance=ComplianceConfig(...)` | E | 규정 준수 패턴 |
| `threat_response=ThreatResponseConfig(...)` | E | 위협 탐지 후 대응 검증 |
| `consensus=ConsensusConfig(...)` | F | 에이전트 합의율 |
| `propagation=PropagationConfig(...)` | F | 정보 전파 정확도 |
| `agent_role=AgentRoleConfig(...)` | F | 역할 준수율 |
| `conflict_resolution=ConflictResolutionConfig(...)` | F | 충돌 해결 |
| `explainability=ExplainabilityConfig(...)` | G | 설명 가능성 |
| `observability=ObservabilityConfig(...)` | G | 내부 상태 노출 |
| `error_diagnosis=ErrorDiagnosisConfig(...)` | G | 오류 진단 정확도 |
| `latency_attribution=LatencyAttributionConfig(...)` | G | 지연 원인 분석 |

### 파라미터 → 지표 활성화 요약

| 파라미터 | 활성화 지표 |
|---|---|
| `ground_truth_arg` | Accuracy |
| `rag_mode=True` | Hallucination Rate + context_arg 자동 설정 |
| `context_arg` | Hallucination Rate (`enable_hallucination_detection=True` 동반) |
| `expected_tools_arg` | Tool Selection F1 |
| `framework="langchain/langgraph"` | Tool Call Efficiency, Workflow Execution |
| `framework="crewai/autogen"` | Agent Coordination |
| `framework="openai/anthropic"` | Token Economy (정확한 토큰/캐시 비용) |
| `security=SecurityConfig()` | 보안 5개 지표 전체 |
| `allowed_tools=[...]` | Tool Authorization (화이트리스트 기준 추가) |
| `llm_judge=LLMJudgeConfig()` | LLMJudge 5차원 |
| `rag_mode=True` + `llm_judge=LLMJudgeConfig()` | + Faithfulness |
| `llm_judge=LLMJudgeConfig(criteria=[...])` | + G-Eval 커스텀 기준 점수 |
| `retry=RetryConfig(max=N)` (N>1) | Retry & Error Recovery |
| `score_fn` | Accuracy (커스텀 계산) |
| `completion_fn` | TCR (커스텀 계산) |
| Harness Config 파라미터 (33종) | Gate A–G 해당 지표 (위 표 참조) |

---

> 전체 실전 예제: `Evaluator_Examples/ch03_harness_basics.py`  
> API 시그니처 상세: `Docs/08_API_REFERENCE.md`
