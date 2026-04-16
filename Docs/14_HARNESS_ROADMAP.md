# v0.9.0 Harness 전환 로드맵

> 에이전트 평가 패러다임 전환: **"지표 수집"** → **"배포 가능성 판정"**

**기준 버전:** v0.8.2  
**목표 버전:** v0.9.0  
**작성일:** 2026-04-17  
**갱신일:** 2026-04-17  
**상태:** Phase 1 ✅ · Phase 2 ✅ · Phase 3 ✅ · Phase 4 ✅ · Phase 5 ✅ · Phase 6 ✅ · Dashboard 재설계 ✅

---

## 목차

1. [배경 및 목적](#1-배경-및-목적)
2. [Harness 7개 그룹 체계](#2-harness-7개-그룹-체계)
3. [Phase 1 — 신규 지표 개발 + 데코레이터 수용](#3-phase-1--신규-지표-개발--데코레이터-수용)
4. [Phase 2 — Dashboard UI 개선](#4-phase-2--dashboard-ui-개선)
5. [Phase 3 — 예제 개선 + QuickEval 통합](#5-phase-3--예제-개선--quickeval-통합)
6. [Phase 4 — 심화 Config 지표 5종](#6-phase-4--심화-config-지표-5종)
7. [Phase 5 — 고급 Config 지표 7종 (보안 네이티브 통합 포함)](#7-phase-5--고급-config-지표-7종-보안-네이티브-통합-포함)
8. [Phase 6 — 최종 Config 지표 5종](#8-phase-6--최종-config-지표-5종)
9. [Dashboard 지표 배치 재설계 (Zero-Base)](#9-dashboard-지표-배치-재설계-zero-base)
10. [파일별 변경 범위 요약](#10-파일별-변경-범위-요약)
11. [테스트 전략](#11-테스트-전략)
12. [버전 릴리즈 계획](#12-버전-릴리즈-계획)
13. [위험 요소 및 완화 방안](#13-위험-요소-및-완화-방안)

---

## 1. 배경 및 목적

### 1.1 현재 체계의 한계

v0.8.x까지의 지표 체계는 **"레이어 중심"** — Layer 1(기반), Layer 2(에이전틱), Layer 3(외부 평가) 로 구성되어 있다. 이 구조는 지표의 **기술적 분류**에는 적합하나, Harness가 핵심적으로 답해야 하는 질문에 직접 대응하지 못한다:

> "이 에이전트를 지금 프로덕션에 배포해도 되는가?"

구체적인 공백:

| 공백 | 설명 |
|------|------|
| 명령 준수 미측정 | 에이전트가 지시한 형식·길이·금지어를 따랐는지 측정 수단 없음 |
| 재현성 부재 | 동일 입력의 반복 실행 간 응답 분산 측정 불가 |
| 루프 감지 없음 | 반복 도구 호출·사고 루프 패턴 감지 장치 없음 |
| 목표-행동 정렬 미측정 | 도구 호출이 질문 의도와 실제로 정렬됐는지 평가 안 함 |
| 장애 허용 미측정 | 도구 실패 후 에이전트가 대안을 시도했는지 추적 안 함 |
| 계획 품질 미측정 | Planning 에이전트가 생성한 계획의 논리적 일관성 평가 없음 |
| Harness Gate 없음 | 7개 차원을 종합해 Pass/Fail 판정하는 통합 뷰 없음 |

### 1.2 목표

- **6개 신규 Config 클래스** 구현 및 데코레이터 파라미터로 수용
- **Dashboard Harness Gate** 패널 신설 — 7개 그룹 Pass/Warn/Fail 실시간 표시
- **기존 5개 예제 + 신규 1개** 업데이트로 신규 지표 사용법 시연
- **하위 호환성 100% 유지** — 기존 `@agent_eval` 코드 무수정 동작

---

## 2. Harness 7개 그룹 체계

에이전트 실행 흐름 전 구간을 7개 관점으로 분류한다.

```
[입력] ──→ [계획·추론] ──→ [도구 실행] ──→ [응답 생성] ──→ [출력]
  │               │               │               │            │
  E 보안          A 목표달성       A+B 목표·행동    A+B          E 보안
  입력 검증        계획 일관성      도구 효율        응답 품질      출력 검사
                  목표-행동 정렬   루프 감지         명령 준수
                                  장애 허용

├─────────────────────────────────────────────────────────────────┤
│              D: 성능 계약 (전 구간 측정)                           │
├─────────────────────────────────────────────────────────────────┤
│              C: 신뢰성 (반복 실행 간 비교)                          │
├─────────────────────────────────────────────────────────────────┤
│              F: 다중 에이전트 (시스템 수준)                          │
├─────────────────────────────────────────────────────────────────┤
│              G: 운영 관측성 (메타 레이어)                           │
└─────────────────────────────────────────────────────────────────┘
```

### 전체 지표 맵 (기존 25개 트래커 + 33개 Harness Config = 58개)

| 그룹 | 지표 | 트래커 / Config | 상태 | API 비용 |
|------|------|----------------|------|----------|
| **A** | Task Completion Rate | `TaskCompletionTracker` | ✅ 기존 | 무료 |
| **A** | Accuracy | `AccuracyEvaluator` | ✅ 기존 | 무료 |
| **A** | Hallucination Rate | `HallucinationDetector` | ✅ 기존 | 무료 |
| **A** | Context Recall/Precision | `HallucinationDetector` | ✅ 기존 | 무료 |
| **A** | LLM Judge (completeness·relevance·factual) | `LLMJudge` | ✅ 기존 | LLM API |
| **A** | **Instruction Adherence (IFR)** | `InstructionConfig` | ✅ Phase 1 | 무료 |
| **A** | **Goal-Action Alignment** | `GoalAlignmentConfig` | ✅ Phase 1 | opt-in LLM |
| **A** | **Plan Coherence** | `PlanConfig` | ✅ Phase 1 | opt-in LLM |
| **A** | **Subtask Completion** | `SubtaskConfig` | ✅ Phase 3 | 무료 |
| **A** | **Context Retention** | `ContextRetentionConfig` | ✅ Phase 3 | 무료 |
| **A** | **Knowledge Retention** | `KnowledgeRetentionConfig` | ✅ Phase 5 | 무료 |
| **B** | Response Quality (5차원) | `ResponseQualityEvaluator` | ✅ 기존 | 무료 |
| **B** | Tool Call Efficiency | `ToolCallAnalyzer` | ✅ 기존 | 무료 |
| **B** | Tool Selection F1 | `ToolSelectionTracker` | ✅ 기존 | 무료 |
| **B** | Workflow Step Success | `WorkflowExecutionTracker` | ✅ 기존 | 무료 |
| **B** | Faithfulness / G-Eval | `LLMJudge` | ✅ 기존 | LLM API |
| **B** | **Agentic Loop Detection** | `LoopDetectionConfig` | ✅ Phase 1 | 무료 |
| **B** | **State Consistency** | `StateConsistencyConfig` | ✅ Phase 2 | 무료 |
| **B** | **Deadlock Detection** | `DeadlockConfig` | ✅ Phase 2 | 무료 |
| **B** | **Scope Compliance** | `ScopeConfig` | ✅ Phase 3 | 무료 |
| **B** | **Tool Parameter Safety** | `ToolParameterSafetyConfig` | ✅ Phase 5 | 무료 |
| **B** | **Context Window Management** | `ContextWindowConfig` | ✅ Phase 6 | 무료 |
| **C** | Retry & Correction | `RetryCorrectionTracker` | ✅ 기존 | 무료 |
| **C** | Context Retention / Topic Coherence | `ConversationSession` | ✅ 기존 | 무료 |
| **C** | Trend (TCR·Accuracy·P95) | `RunTrendAnalyzer` | ✅ 기존 | 무료 |
| **C** | **Reproducibility Score** | `ReproducibilityConfig` | ✅ Phase 1 | 무료 |
| **C** | **Fault Tolerance** | `FaultToleranceConfig` | ✅ Phase 1 | 무료 |
| **C** | **SLA Compliance** | `SLAConfig` | ✅ Phase 2 | 무료 |
| **C** | **Graceful Degradation** | `GracefulDegradationConfig` | ✅ Phase 4 | 무료 |
| **C** | **Retry Consistency** | `RetryConsistencyConfig` | ✅ Phase 5 | 무료 |
| **C** | **Idempotency** | `IdempotencyConfig` | ✅ Phase 6 | 무료 |
| **D** | Latency P50/P90/P95/P99 | `LatencyTracker` | ✅ 기존 | 무료 |
| **D** | TTFT | `LatencyTracker` | ✅ 기존 | 무료 |
| **D** | SLA Compliance Rate | `LatencyTracker` | ✅ 기존 | 무료 |
| **D** | Token Economy / Cost | `TokenEconomyTracker` | ✅ 기존 | 무료 |
| **D** | **SLA Gate** | `SLAConfig` | ✅ Phase 2 | 무료 |
| **D** | **Efficiency Ratio** | `EfficiencyConfig` | ✅ Phase 2 | 무료 |
| **D** | **Resource Budget** | `ResourceBudgetConfig` | ✅ Phase 4 | 무료 |
| **D** | **TTFT Variability** | `TTFTVariabilityConfig` | ✅ Phase 5 | 무료 |
| **D** | **Cost Predictability** | `CostPredictabilityConfig` | ✅ Phase 6 | 무료 |
| **E** | Input Sanitization | `InputSanitizationTracker` | ✅ 기존 | 무료 |
| **E** | Output Leakage | `OutputLeakageDetector` | ✅ 기존 | 무료 |
| **E** | Tool Authorization | `ToolAuthorizationTracker` | ✅ 기존 | 무료 |
| **E** | Privilege Escalation | `PrivilegeEscalationDetector` | ✅ 기존 | 무료 |
| **E** | Tool Chain Attack | `ToolChainAttackDetector` | ✅ 기존 | 무료 |
| **E** | **Threat Severity** | `ThreatSeverityConfig` | ✅ Phase 2 | 무료 |
| **E** | **Compliance** | `ComplianceConfig` | ✅ Phase 4 | 무료 |
| **E** | **Threat Response** | `ThreatResponseConfig` | ✅ Phase 6 | 무료 |
| **F** | Coordination Score | `AgentCoordinationTracker` | ✅ 기존 | 무료 |
| **F** | Network Topology | `AgentCoordinationTracker` | ✅ 기존 | 무료 |
| **F** | **Consensus** | `ConsensusConfig` | ✅ Phase 2 | 무료 |
| **F** | **Propagation Fidelity** | `PropagationConfig` | ✅ Phase 3 | 무료 |
| **F** | **Agent Role Compliance** | `AgentRoleConfig` | ✅ Phase 4 | 무료 |
| **F** | **Conflict Resolution** | `ConflictResolutionConfig` | ✅ Phase 4 | 무료 |
| **G** | Anomaly Detection | `AnomalyDetector` | ✅ 기존 | 무료 |
| **G** | Alert Engine | `AlertEngine` | ✅ 기존 | 무료 |
| **G** | OTEL / Phoenix | `OTELProvider` | ✅ 기존 | 무료 |
| **G** | **Observability Score** | `ObservabilityConfig` | ✅ Phase 2 | 무료 |
| **G** | **Explainability** | `ExplainabilityConfig` | ✅ Phase 3 | 무료 |
| **G** | **Error Diagnosis** | `ErrorDiagnosisConfig` | ✅ Phase 5 | 무료 |
| **G** | **Latency Attribution** | `LatencyAttributionConfig` | ✅ Phase 6 | 무료 |

---

## 3. Phase 1 — 신규 지표 개발 + 데코레이터 수용 ✅ 완료

> **구현 완료 일자:** 2026-04-17  
> **실제 테스트 결과:** 신규 117개 (test_decorators_harness.py 117개 + test_report_harness_groups.py 포함), 전체 2,467개 통과  
> **계획 대비 주요 변경:** [§3.5 구현 편차 참고](#35-구현-편차--실제-구현-현황)

### 3.1 신규 Config 클래스 6종 ✅

모두 `agent_evaluator/decorators.py`의 기존 `SecurityConfig` / `RetryConfig` / `LLMJudgeConfig` 패턴을 그대로 따른다.

---

#### 3.1.1 `InstructionConfig` — 명령 준수율 (IFR)

**측정 대상:** 에이전트가 프롬프트에 지정한 형식·길이·내용 제약을 얼마나 준수했는가.

```python
@dataclass
class InstructionConfig:
    # ── 형식 제약 ──────────────────────────────────────────────────
    expected_format: Optional[Literal["json", "markdown", "plain", "yaml", "xml"]] = None
    required_sections: List[str] = field(default_factory=list)
    # 예: ["결론", "근거", "출처"]

    # ── 길이 제약 ──────────────────────────────────────────────────
    max_chars: Optional[int] = None
    min_chars: Optional[int] = None
    max_words: Optional[int] = None
    min_words: Optional[int] = None

    # ── 내용 제약 ──────────────────────────────────────────────────
    forbidden_phrases: List[str] = field(default_factory=list)
    # 예: ["모르겠습니다", "I cannot", "As an AI"]
    required_keywords: List[str] = field(default_factory=list)
    # 예: ["출처:", "참고:"]

    # ── 언어 제약 ──────────────────────────────────────────────────
    expected_language: Optional[str] = None   # "ko", "en", "ja"

    # ── 점수화 ────────────────────────────────────────────────────
    fail_on_violation: bool = False            # True 이면 위반 시 task.success = False
    violation_weight: float = 0.1             # 위반 1건당 adherence 점수 감점
```

**산출 지표:**
- `instruction_adherence` (0.0–1.0): 전체 준수율
- `violations` (List[str]): 위반 항목 목록 (`["형식 불일치: expected json", "금지어: 모르겠습니다"]`)
- `violation_count` (int)

**측정 로직 (외부 의존성 없음):**

```
형식 준수:
  json  → json.loads() 시도, 실패 시 위반
  yaml  → yaml.safe_load() 시도
  markdown → r'^#{1,6}\s' 또는 r'^\s*[-*]\s' 패턴 존재 여부
  xml   → re.match(r'<\w+', response.strip())

섹션 존재:
  required_sections 의 각 키워드가 응답 내 존재하는지 확인
  (대소문자 무시, 부분 일치)

길이:
  len(response) vs max_chars/min_chars
  len(response.split()) vs max_words/min_words

내용:
  forbidden_phrases → any(p.lower() in response.lower() for p in ...)
  required_keywords → all(k.lower() in response.lower() for k in ...)

언어:
  basic heuristic: 한글 비율 (유니코드 블록 AC00–D7A3)
  "ko" → 한글 비율 > 0.3
  "en" → ASCII 비율 > 0.7
  (정밀도 낮음 — opt-in 기능, langdetect 있으면 자동 연동)

adherence_score = 1.0 - (violation_count * violation_weight)
                  (최솟값 0.0)
```

**데코레이터 사용:**

```python
@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_format="json",
        required_sections=["answer", "confidence"],
        max_chars=500,
        forbidden_phrases=["모르겠습니다", "I cannot"],
        fail_on_violation=True,
    ),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

**TaskResult 연동:**
```python
result.extra["instruction_adherence"] = {
    "score": 0.8,
    "violations": ["필수 섹션 누락: confidence"],
    "violation_count": 1,
    "checks": {
        "format": True,
        "sections": False,
        "length": True,
        "forbidden": True,
        "keywords": True,
    }
}
```

---

#### 3.1.2 `LoopDetectionConfig` — 에이전틱 루프 감지

**측정 대상:** 에이전트가 동일한 도구 호출 또는 추론 패턴을 반복하는 루프에 빠졌는가.

```python
@dataclass
class LoopDetectionConfig:
    # ── 감지 방식 ──────────────────────────────────────────────────
    consecutive_repeat_threshold: int = 3
    # 연속으로 동일 (tool_name + hash(params)) 호출 시 루프 판정

    window_size: int = 5
    # 슬라이딩 윈도우 크기
    duplicate_in_window_threshold: int = 2
    # 윈도우 내 동일 호출이 이 횟수 이상이면 루프 판정

    # ── 응답 유사도 기반 (ReAct 패턴) ─────────────────────────────
    check_response_loop: bool = False
    response_similarity_threshold: float = 0.95
    # chain_steps 의 연속 스텝 내용 간 유사도가 이 이상이면 루프

    # ── 동작 ──────────────────────────────────────────────────────
    on_loop_detected: Literal["record", "warn", "abort"] = "record"
    # "record"  → extra 에 기록만
    # "warn"    → logging.warning + record
    # "abort"   → 실행 조기 종료 후 partial TaskResult 기록
```

**산출 지표:**
- `loop_detected` (bool)
- `loop_type` (str | None): `"consecutive_repeat"`, `"window_duplicate"`, `"response_similarity"`
- `loop_at_step` (int | None): 루프 감지된 도구 호출 인덱스
- `loop_tool` (str | None): 반복된 도구명

**측정 로직:**

```
tool_calls 순서 분석:
  call_signatures = [(tc["name"], hash(str(tc.get("parameters", {})))) for tc in tool_calls]

  연속 반복:
    for i in range(consecutive_repeat_threshold, len(call_signatures)):
        window = call_signatures[i - consecutive_repeat_threshold : i]
        if len(set(window)) == 1: → loop_detected

  슬라이딩 윈도우:
    for i in range(window_size, len(call_signatures)):
        window = call_signatures[i - window_size : i]
        counts = Counter(window)
        if counts.most_common(1)[0][1] >= duplicate_in_window_threshold: → loop_detected

  응답 유사도 (check_response_loop=True):
    chain_steps 가 있을 때만 활성화
    for i in range(1, len(chain_steps)):
        sim = _token_overlap_f1(chain_steps[i-1].get("output",""), chain_steps[i].get("output",""))
        if sim >= response_similarity_threshold: → loop_detected
```

**크로스커팅 특성:**
- Group B (행동 무결성): 에이전트 오작동 관점
- Group E (보안): 도구 반복 호출을 통한 자원 고갈 공격 관점
- `enable_security_metrics=True` 시 자동 활성화 옵션 제공

---

#### 3.1.3 `GoalAlignmentConfig` — 목표-행동 정렬

**측정 대상:** 에이전트가 사용한 도구 호출이 질문의 의도와 얼마나 정렬되어 있는가.

```python
@dataclass
class GoalAlignmentConfig:
    # ── 정렬 평가 방식 ─────────────────────────────────────────────
    use_keyword_overlap: bool = True
    # question 의 키워드와 tool_calls 의 tool_name 간 토큰 F1 계산

    goal_tool_map: Dict[str, List[str]] = field(default_factory=dict)
    # 명시적 매핑: {"날씨": ["weather_api", "forecast"], "계산": ["calculator"]}
    # 제공 시 keyword_overlap 대신 우선 사용

    use_llm_scoring: bool = False
    # LLMJudge 가 활성화된 경우 LLM 으로 정렬 점수 요청 (고정밀)

    alignment_threshold: float = 0.6
    # 이 이하이면 misalignment 플래그

    # ── 점수화 ────────────────────────────────────────────────────
    ignore_no_tool_tasks: bool = True
    # tool_calls 가 없는 태스크는 정렬 평가 제외 (None 반환)
```

**산출 지표:**
- `goal_alignment_score` (float | None): 0.0–1.0
- `misaligned` (bool)
- `alignment_method` (str): `"keyword_overlap"`, `"goal_map"`, `"llm"`
- `aligned_tools` (List[str]): 목표와 정렬된 도구
- `unaligned_tools` (List[str]): 목표와 무관한 도구

---

#### 3.1.4 `ReproducibilityConfig` — 재현성

**측정 대상:** 동일 입력을 N회 실행했을 때 응답의 일관성.

```python
@dataclass
class ReproducibilityConfig:
    runs: int = 3
    # 동일 입력 반복 횟수 (1이면 측정 비활성)

    similarity_measure: Literal["token_f1", "jaccard", "exact"] = "token_f1"
    # "token_f1" → 기존 _token_overlap_ratio 재활용
    # "jaccard"  → 기존 _jaccard_similarity 재활용
    # "exact"    → 완전 일치 여부

    reproducibility_threshold: float = 0.85
    # 이 이하이면 low_reproducibility 플래그

    fail_on_low_reproducibility: bool = False

    # ── 부수효과 제어 ────────────────────────────────────────────
    skip_side_effects: bool = True
    # True 이면 추가 실행의 TaskResult 는 monitor 에 기록하지 않음
    # (재현성 측정은 primary 실행의 extra 에만 첨부)
```

**산출 지표:**
- `reproducibility_score` (float): pairwise 평균 유사도
- `variance` (float): 유사도 표준편차
- `low_reproducibility` (bool)
- `run_responses` (List[str]): 각 실행 응답 (처음 200자만)

**구현 노트:**
- 데코레이터의 `wrapper` 레이어에서 primary 실행 후 `runs-1` 회 추가 실행
- `skip_side_effects=True` 이면 추가 실행의 `record_task()` 호출 생략
- 비동기 함수(`async def`)도 `await` 체인으로 동일하게 처리

---

#### 3.1.5 `FaultToleranceConfig` — 장애 허용

**측정 대상:** 도구 실패 발생 시 에이전트가 대안 경로를 시도했는지, 얼마나 우아하게 복구했는지.

```python
@dataclass
class FaultToleranceConfig:
    check_fallback_attempts: bool = True
    # 실패한 도구 호출 이후 다른 도구를 시도했는지 확인

    partial_success_threshold: float = 0.5
    # 복구 불완전해도 이 이상이면 partial_success 처리

    score_recovery_quality: bool = True
    # 복구 시도의 품질 점수화
    # (성공한 최종 응답 정확도 vs 실패 없었을 때 기대 정확도 비율)

    expected_fallback_tools: Dict[str, List[str]] = field(default_factory=dict)
    # {"primary_tool": ["fallback_1", "fallback_2"]}
    # 명시적 폴백 체인 검증용
```

**산출 지표:**
- `tool_failures_detected` (int): 실패한 도구 호출 수
- `fallback_attempts` (int): 실패 후 다른 도구 시도 수
- `recovery_rate` (float): fallback_attempts / tool_failures_detected
- `recovery_quality_score` (float | None): 복구 품질 (0.0–1.0)
- `fault_tolerance_grade` (str): `"excellent"` / `"good"` / `"poor"` / `"none"`

**측정 로직:**
```
tool_calls 에서 success=False 인 호출 탐지:
  failed_indices = [i for i, tc in enumerate(tool_calls) if not tc.get("success", True)]

  각 failed_index 이후에 다른 tool_name 이 등장하면 fallback_attempt 카운트
  (동일 tool_name 재시도 → RetryCorrectionTracker 영역, 여기서는 제외)

  expected_fallback_tools 제공 시:
    실제 사용된 폴백이 기대 폴백 목록과 일치하는지 검증
```

---

#### 3.1.6 `PlanConfig` — 계획 품질 (Planning 에이전트 전용)

**측정 대상:** Planning 에이전트가 생성한 계획의 목표 커버리지, 단계 논리, 실행 가능성.

```python
@dataclass
class PlanConfig:
    # ── 계획 추출 ──────────────────────────────────────────────────
    plan_field: str = "plan"           # 응답 dict 에서 계획 키
    steps_field: str = "steps"         # 계획 내 단계 리스트 키

    # ── 검증 항목 ──────────────────────────────────────────────────
    check_goal_coverage: bool = True
    # 목표 키워드 (question 에서 추출) 가 계획 단계에 포함되는가

    check_step_ordering: bool = True
    # 단계 간 의존 순서가 합리적인가 (휴리스틱: 정보 수집 → 처리 → 출력 패턴)

    check_executability: bool = True
    # 각 단계가 available_tools 로 실행 가능한가
    available_tools: List[str] = field(default_factory=list)

    use_llm_scoring: bool = False
    # LLMJudge 로 계획 전체 품질 채점 (고정밀, API 비용 발생)

    min_steps: int = 2
    max_steps: int = 20
    # 단계 수 범위 초과 시 구조 위반 플래그
```

**산출 지표:**
- `plan_coherence_score` (float): 0.0–1.0 (세 검증 항목 평균)
- `goal_coverage` (float): 목표 키워드 중 계획에 포함된 비율
- `ordering_score` (float): 단계 순서 합리성 (0.0–1.0)
- `executability_score` (float): 실행 가능한 단계 비율
- `unexecutable_steps` (List[str]): 도구 없는 단계명
- `step_count` (int)

---

### 3.2 데코레이터 통합 설계 ✅

#### `agent_eval` 파라미터 확장

```python
def agent_eval(
    monitor: "PerformanceMonitor",
    # ... 기존 파라미터 ...

    # ── v0.9.0 신규 ──────────────────────────────────────────────
    instructions: Optional[InstructionConfig] = None,
    loop_detection: Optional[LoopDetectionConfig] = None,
    goal_alignment: Optional[GoalAlignmentConfig] = None,
    reproducibility: Optional[ReproducibilityConfig] = None,
    fault_tolerance: Optional[FaultToleranceConfig] = None,
    plan_tracking: Optional[PlanConfig] = None,
):
```

동일한 파라미터를 `batch_eval`, `conversation_eval`, `EvalDecorator`, `QuickEval` 에도 적용해 기존 3종 데코레이터 parity 원칙을 유지한다.

#### `_build_and_record()` 내 처리 순서 ✅ 구현 완료

> **실제 함수명:** `_build_and_record()` (계획서 표기 `_build_task_result()`와 다름)

```
1. 기존 결과 계산 (accuracy, quality, hallucination ...)
2. if instructions:    → eval_instruction_adherence(response, instructions)   ← taskresult_helpers
3. if loop_detection:  → eval_loop_detection(tool_calls, chain_steps, config) ← taskresult_helpers
4. if goal_alignment:  → eval_goal_alignment(question, tool_calls, config)    ← taskresult_helpers
5. if fault_tolerance: → eval_fault_tolerance(tool_calls, config)             ← taskresult_helpers
6. if plan_tracking:   → eval_plan_coherence(response, question, config)      ← taskresult_helpers
7. extra 딕셔너리에 결과 병합
8. if reproducibility: → compute_reproducibility_score(responses, measure)   ← 동기 wrapper finally에서 처리
   (별도 실행 후 extra 에 첨부 — 비동기 함수는 단일 실행만 기록, 아래 §3.5 참고)
```

#### `QuickEval` 팩토리 확장

```python
# 기존 팩토리에 harness 프리셋 추가
eval = QuickEval.for_harness(
    "results/",
    instructions=InstructionConfig(expected_format="json"),
    loop_detection=LoopDetectionConfig(),
    fault_tolerance=FaultToleranceConfig(),
)

# 또는 전용 팩토리
eval = QuickEval.for_production(
    "results/",
    sla_p95=5.0,               # Group D
    reproducibility_runs=3,    # Group C
    security=True,             # Group E
)
```

---

### 3.3 `TaskResult` / `EvaluationReport` 확장 ✅

#### `TaskResult.extra` 예약 키 추가 (문서화)

기존 `extra` 딕셔너리에 신규 결과가 적재되므로 TaskResult 구조 변경 없음. 단, 예약 키를 공식 문서화한다.

| extra 키 | 타입 | 설명 |
|----------|------|------|
| `instruction_adherence` | `dict` | `{score, violations, violation_count, checks}` |
| `loop_detection` | `dict` | `{detected, type, at_step, tool}` |
| `goal_alignment` | `dict` | `{score, misaligned, method, aligned_tools, unaligned_tools}` |
| `reproducibility` | `dict` | `{score, variance, low_reproducibility, run_responses}` |
| `fault_tolerance` | `dict` | `{failures_detected, fallback_attempts, recovery_rate, grade}` |
| `plan_coherence` | `dict` | `{score, goal_coverage, ordering, executability, unexecutable_steps}` |

#### `EvaluationReport` 집계 확장 ✅

> **실제 구현 차이:** `report.summary["harness_groups"]` 대신 `report.extra_metrics["harness_groups"]` 로 접근.  
> `EvaluationReport` 에 `extra_metrics: Optional[Dict[str, Any]] = None` 필드 신규 추가 (base.py).  
> 직렬화: `report.to_dict()["extra_metrics"]["harness_groups"]`

```python
# 실제 접근 경로 (구현된 방식)
report = monitor.generate_report()
harness = report.extra_metrics["harness_groups"]      # 직접 접근
harness = report.to_dict()["extra_metrics"]["harness_groups"]  # 직렬화 후 접근
```

`generate_report()` 에 신규 그룹 집계 추가:

```python
# report.extra_metrics 에 저장되는 구조 (계획 summary 위치와 다름)
"harness_groups": {
    "A_goal_achievement": {
        "tcr": 91.2,
        "accuracy": 78.5,
        "instruction_adherence": 0.94,
        "goal_alignment": 0.81,
        "gate": "pass"  # "pass" / "warn" / "fail"
    },
    "B_behavioral_integrity": {
        "loop_detected_count": 2,
        "fault_tolerance_avg": 0.73,
        "tool_efficiency": 84.0,
        "gate": "warn"
    },
    "C_reliability": {
        "reproducibility_score": 0.82,
        "retry_rate": 12.5,
        "gate": "pass"
    },
    "D_performance_contract": {
        "p95_latency": 4.8,
        "avg_cost_usd": 0.008,
        "sla_compliance": 97.2,
        "gate": "pass"
    },
    "E_security_boundary": {
        "threat_rate": 0.0,
        "leakage_rate": 0.0,
        "gate": "pass"
    },
    "F_multiagent": {
        "coordination_score": 8.2,
        "gate": "pass"
    },
    "overall_gate": "warn"  # 하나라도 warn/fail 이면 warn
}
```

---

### 3.4 파일 변경 목록 (Phase 1) ✅ 전체 완료

| 파일 | 변경 유형 | 내용 | 상태 |
|------|----------|------|------|
| `agent_evaluator/decorators.py` | 확장 | Config 6종 dataclass 추가; `agent_eval`(+6) / `batch_eval`(+5) / `conversation_eval`(+5) 파라미터 추가; `_build_and_record()` 처리 로직 추가 | ✅ |
| `agent_evaluator/core/trackers/monitor.py` | 확장 | `_compute_harness_groups()` 신규 메서드; `generate_report()` 에 `extra_metrics={"harness_groups": ...}` 연결 | ✅ |
| `agent_evaluator/core/trackers/base.py` | 확장 | `EvaluationReport` 에 `extra_metrics: Optional[Dict[str, Any]] = None` 필드 추가 | ✅ |
| `agent_evaluator/quick_eval.py` | 확장 | `for_harness()` / `for_production()` 팩토리 추가 | ✅ |
| `agent_evaluator/__init__.py` | 확장 | Config 6종 공개 API 추가 (`InstructionConfig`, `LoopDetectionConfig`, `GoalAlignmentConfig`, `ReproducibilityConfig`, `FaultToleranceConfig`, `PlanConfig`) | ✅ |
| `agent_evaluator/helpers/taskresult_helpers.py` | 확장 | 헬퍼 함수 6종 추가: `eval_instruction_adherence`, `eval_loop_detection`, `eval_goal_alignment`, `eval_fault_tolerance`, `eval_plan_coherence`, `compute_reproducibility_score` | ✅ |
| `tests/test_decorators_harness.py` | 신규 | Config 6종 단위 테스트 — 실제 **117개** | ✅ |
| `tests/test_report_harness_groups.py` | 신규 | `harness_groups` 집계 + `EvaluationReport.extra_metrics` 검증 | ✅ |
| `tests/test_param_cleanup.py` | 수정 | `batch_eval` 파라미터 수 31→36, `conversation_eval` 27→32 갱신 | ✅ |

---

### 3.5 구현 편차 / 실제 구현 현황

Phase 1 계획과 실제 구현 간 차이점을 기록한다. 향후 Phase 2/3 작업 시 아래 사항을 기준으로 코드 참조.

| 항목 | 계획 | 실제 구현 | 영향 |
|------|------|----------|------|
| 처리 함수명 | `_build_task_result()` | `_build_and_record()` | 코드 검색 시 후자로 조회 |
| harness_groups 위치 | `report.summary["harness_groups"]` | `report.extra_metrics["harness_groups"]` | Dashboard 로더에서 `extra_metrics` 키 참조 필요 (Phase 2) |
| `EvaluationReport` 신규 필드 | 미언급 | `extra_metrics: Optional[Dict] = None` (base.py) | `to_dict()` / `from_dict()` 완전 지원 |
| async 재현성 | `await` 체인으로 N회 | 단일 실행만 기록 (`finally` 에서 `await` 불가) | async 함수에서는 `reproducibility.score=None`, 동기 함수에서만 완전 동작 |
| `failures_detected` 타입 | `bool` (계획서 `tool_failures_detected`) | `int` (카운트) | `if result["failures_detected"]:` 으로 bool 평가 가능 |
| 버전 분할 | v0.8.2(3종) → v0.8.3(3종+집계) | 단일 구현 (Phase 1 전체 동시) | v0.8.2/v0.8.3 스킵, Phase 1 = v0.9.0 전단계 |
| `_BATCH_PARAMS` 갱신 | 언급 없음 | `instructions`, `loop_detection`, `goal_alignment`, `fault_tolerance`, `plan_tracking` 추가 | batch_eval 파라미터 수 31→36 |
| `_CONV_PARAMS` 갱신 | 언급 없음 | 위 5종 동일 추가 (`reproducibility` 제외) | conversation_eval 파라미터 수 27→32 |

---

## 4. Phase 2 — Dashboard UI 개선 ✅ 완료

> **구현 완료 일자:** 2026-04-17  
> **테스트 결과:** 기존 2,467개 전체 통과 (UI 변경 — 별도 테스트 파일 추가 없음)  
> **계획 대비 주요 변경:** [§4.10 구현 편차 참고](#410-구현-편차--실제-구현-현황)

### 4.1 Overview 탭 — Harness Gate 패널 ✅

기존 KPI 카드 상단에 7개 그룹 게이트 패널을 추가한다.

**위치:** `dashboard2.html.j2`, `sec==='overview'` 섹션 최상단

**데이터 소스:** `EvaluationReport.extra_metrics["harness_groups"]` (Phase 1에서 추가 — §3.5 구현 편차 참고)

```html
<!-- Harness Gate Panel -->
<div class="harness-gate-panel" x-show="data && data.summary && data.summary.harness_groups">
  <div class="gate-header">
    <span class="gate-title">Harness Gate</span>
    <span class="gate-overall"
          :class="gateClass(data.summary.harness_groups.overall_gate)">
      <span x-text="gateLabel(data.summary.harness_groups.overall_gate)"></span>
    </span>
  </div>
  <div class="gate-groups">
    <template x-for="[key, group] in Object.entries(gateGroups)">
      <div class="gate-group" :class="gateClass(group.gate)"
           @click="sec = group.tab">
        <div class="gate-group-label" x-text="group.label"></div>
        <div class="gate-status-icon" x-text="gateIcon(group.gate)"></div>
        <div class="gate-metrics" x-html="group.summary(data)"></div>
      </div>
    </template>
  </div>
</div>
```

**레이아웃:**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Harness Gate                                      ⚠ WARN (1/7)    │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──┤
│  A 목표  │  B 행동  │  C 신뢰  │  D 성능  │  E 보안  │  F 협업  │G │
│  달성    │  무결성  │  성      │  계약    │  경계    │          │관측│
│          │          │          │          │          │          │  │
│  ✅PASS  │  ⚠WARN  │  ✅PASS  │  ⚠WARN  │  ✅PASS  │  ✅PASS  │ ✅│
│          │          │          │          │          │          │  │
│ TCR 91%  │Loop 2건  │Repro     │P95:4.8s  │위협 0건  │Coord 8.2 │  │
│ Acc 78%  │FaultTol  │0.82 ✓   │비용↑18%  │누출 0건  │          │  │
│ IFR 94%  │복구 33%↓ │          │          │          │          │  │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──┘
```

**임계값:** `settings` 탭의 기존 threshold 시스템에 그룹별 임계값 추가

```json
// /api/thresholds 응답에 추가
{
  "harness": {
    "A": {"tcr": 85, "accuracy": 70, "instruction_adherence": 0.8},
    "B": {"max_loop_count": 0, "min_fault_tolerance": 0.5},
    "C": {"min_reproducibility": 0.85, "max_retry_rate": 20},
    "D": {"max_p95_latency_s": 5.0, "max_avg_cost_usd": 0.01},
    "E": {"max_threat_rate": 0, "max_leakage_rate": 0},
    "F": {"min_coordination_score": 6.0}
  }
}
```

**레이더 차트 확장:** 기존 6축 → 7축 (A~G, G=Observability coverage)

---

### 4.2 Quality 탭 → Group A 재구성 ✅

**변경 내용:**

1. 탭 상단에 그룹 레이블 `Group A — 목표 달성 검증` 표시
2. 섹션 순서 재정렬:
   - A-1: TCR + Accuracy + IFR 3단 게이지 (신규 IFR 추가)
   - A-2: 정확도 분석 (기존)
   - A-3: **Instruction Adherence 위젯** (신규)
   - A-4: **Goal-Action Alignment 산점도** (신규)
   - A-5: 환각 분석 (기존, 하단 이동)

**신규 위젯 — Instruction Adherence:**

```
명령 준수 현황
┌────────────────────────────────────────────────┐
│  전체 준수율   94.2%  ████████████████░░   ↑2.1%│
│                                                 │
│  위반 유형별 분포                                 │
│  형식 불일치   ██░░░░░░░░  3건                   │
│  필수 섹션 누락 █░░░░░░░░░  2건                  │
│  금지어 포함   █░░░░░░░░░  1건                   │
│  길이 초과     ░░░░░░░░░░  0건                   │
│                                                 │
│  위반 태스크 목록 [▼]                             │
└────────────────────────────────────────────────┘
```

차트 타입: 수평 바 (Plotly `bar` orientation='h') — 기존 코드 패턴 재사용

**신규 위젯 — Goal-Action Alignment 산점도:**
- X축: `goal_alignment_score`
- Y축: `accuracy_score`
- 색: `task_type`
- 크기: `tokens_used.total`
- 인사이트: 정렬 낮음 + 정확도 낮음 → 좌하단 클러스터 = 즉시 검토 대상

---

### 4.3 Agentic 탭 → Group B 재구성 ✅ (Loop Detection만 구현)

**변경 내용:**

1. 탭 상단에 `Group B — 행동 무결성` 레이블
2. 신규 섹션 추가:
   - **Loop Detection 타임라인** (신규)
   - **Graceful Degradation 매트릭스** (신규)
3. 기존 섹션 유지 (도구 효율, 코디네이션, 워크플로우, 재시도)

**신규 — Loop Detection 타임라인:**

```html
<!-- Loop Detection Section -->
<div x-show="loopEvents && loopEvents.length > 0" class="alert-section warn">
  <h4>⚠ 루프 감지 이벤트 (<span x-text="loopEvents.length"></span>건)</h4>
  <template x-for="ev in loopEvents">
    <div class="loop-event-card">
      <span class="task-badge" x-text="ev.task_id"></span>
      <span class="loop-type-badge" x-text="ev.type"></span>
      <div class="tool-sequence" x-text="ev.sequence.join(' → ')"></div>
      <span class="loop-outcome" x-text="ev.completion_score_label"></span>
    </div>
  </template>
</div>
<div x-show="!loopEvents || loopEvents.length === 0" class="status-ok">
  루프 감지 없음 ✅
</div>
```

**신규 — Graceful Degradation 매트릭스:**

```
도구별 장애 허용 현황
┌──────────────────┬──────┬──────┬────────┐
│  도구             │ 실패  │ 복구  │ 복구율  │
├──────────────────┼──────┼──────┼────────┤
│  web_search       │  8건  │  6건  │  75% ✅│
│  calculator       │  3건  │  1건  │  33% ⚠ │
│  file_read        │  2건  │  0건  │   0% ❌│
└──────────────────┴──────┴──────┴────────┘
```

차트: Tabulator 테이블 (기존 코드 패턴), 복구율 컬럼에 색상 조건부 포매팅

**API 연동:** `/api/results/{file_id}/aggregate` 에 `loop_events`, `fault_tolerance_by_tool` 키 추가 필요 (loader.py 확장)

---

### 4.4 Security 탭 → Group E 개선 ✅ 구현완료 (2026-04-17)

**변경 내용:** 5개 개별 차트 나열 → 보안 경계 흐름 통합 뷰

**레이아웃 변경:**

```
현재                          →  개선
─────────────────────────────    ─────────────────────────────
[입력 보안 바]                    [보안 경계 상태 패널]  ← 신규
[출력 누출 바]                       입력/실행/출력 3단 요약
[도구 인증 바]                    [이벤트 흐름 타임라인] ← 신규
[에스컬레이션 목록]                   날짜별 이벤트 히스토리
[공격 목록]                       [위협 유형별 드릴다운]  ← 기존 재배치
                                    입력/출력/권한/공격 4개 펼침 패널
```

**보안 경계 상태 패널:**

```html
<div class="security-boundary-panel">
  <div class="boundary-layer" :class="inputThreatClass">
    <span>입력</span>
    <span x-text="inputThreats + '건'"></span>
  </div>
  <div class="boundary-arrow">→</div>
  <div class="boundary-layer" :class="execThreatClass">
    <span>실행</span>
    <span x-text="execViolations + '건'"></span>
  </div>
  <div class="boundary-arrow">→</div>
  <div class="boundary-layer" :class="outputThreatClass">
    <span>출력</span>
    <span x-text="outputLeaks + '건'"></span>
  </div>
</div>
```

**보안 이벤트 → 태스크 드릴다운 연결:** (현재 없음)
- 이벤트 목록의 각 행에 `[태스크 보기]` 버튼 추가
- 클릭 시 Tasks 탭으로 이동하며 해당 `task_id` 필터 적용 (Alpine.js `taskFilter` 상태 활용)

---

### 4.5 Performance 탭 → Group D SLA 패널 추가 ✅

**변경 내용:** 기존 지연시간/토큰/비용 차트 상단에 SLA 컴플라이언스 패널 추가

```html
<div class="sla-panel">
  <h4>성능 계약 현황</h4>
  <template x-for="sla in slaItems">
    <div class="sla-row">
      <span class="sla-name" x-text="sla.name"></span>
      <div class="sla-bar-container">
        <div class="sla-bar" :style="'width:' + sla.pct + '%'"
             :class="sla.ok ? 'ok' : 'breach'"></div>
      </div>
      <span class="sla-value" x-text="sla.actual"></span>
      <span class="sla-limit" x-text="'/ ' + sla.limit"></span>
      <span class="sla-status" x-text="sla.ok ? '✅' : '❌'"></span>
    </div>
  </template>
</div>
```

SLA 항목: P95 응답시간, P99 응답시간, TTFT, 평균 비용/태스크, 월간 예상 비용

---

### 4.6 신규 탭 — Reliability (Group C) ✅

네비게이션에 `reliability` 섹션 추가. 기존 CLI 전용이던 `RunTrendAnalyzer` 결과를 UI에 통합.

**섹션 구성:**

```
[재현성] ─── [자기교정] ─── [실행 추세] ─── [대화 일관성]
```

**재현성 서브섹션:**

```html
<div x-show="sub==='reproducibility'">
  <!-- 재현성 점수 게이지 -->
  <div class="gauge-container">
    <div class="gauge-value" x-text="repro_score"></div>
    <div class="gauge-label">재현성</div>
    <div class="gauge-threshold">목표: ≥ 0.85</div>
  </div>

  <!-- 태스크별 분산 히트맵 -->
  <!-- X: task_id, Y: run (1/2/3), Color: similarity to run_1 -->
  <div id="repro-heatmap"></div>

  <!-- 불안정 태스크 목록 -->
  <table class="low-repro-tasks">
    <!-- task_id, variance, run_responses 요약 -->
  </table>
</div>
```

**실행 추세 서브섹션 (RunTrendAnalyzer UI화):**

```html
<div x-show="sub==='trend'">
  <!-- 다중 지표 추세 라인 차트 -->
  <!-- TCR, Accuracy, P95, Hallucination rate — 최근 N회 실행 -->
  <div id="trend-chart"></div>

  <!-- 회귀 이벤트 카드 -->
  <div x-show="regressions.length > 0" class="regression-alerts">
    <template x-for="reg in regressions">
      <div class="regression-card warn">
        <span x-text="reg.metric"></span>
        <span x-text="reg.slope + '/run'"></span>
        <span>지속 하락 감지 ⚠</span>
      </div>
    </template>
  </div>
</div>
```

**API 연동:** 새 엔드포인트 `/api/results/{file_id}/reliability` 추가 (loader.py 확장)

---

### 4.7 Compare 탭 → Harness Group 비교 추가 ✅

기존 레이더 비교에 **Harness 그룹별 회귀 비교** 테이블 추가.

```html
<!-- Harness Group Comparison Table -->
<div x-show="compareFiles.length >= 2">
  <table class="harness-compare-table">
    <thead>
      <tr>
        <th>그룹</th>
        <template x-for="f in compareFiles">
          <th x-text="f.name"></th>
        </template>
        <th>변화</th>
        <th>판정</th>
      </tr>
    </thead>
    <tbody>
      <template x-for="group in harnesGroups">
        <tr>
          <td x-text="group.label"></td>
          <template x-for="f in compareFiles">
            <td :class="gateClass(group.gate(f))"
                x-text="group.value(f)"></td>
          </template>
          <td x-text="group.delta(compareFiles)"></td>
          <td x-text="group.regression(compareFiles) ? '⚠ 회귀' : '✅'"></td>
        </tr>
      </template>
    </tbody>
  </table>
  <div class="deploy-verdict">
    전체 판정:
    <span :class="overallVerdictClass">
      <span x-text="overallVerdict"></span>
    </span>
  </div>
</div>
```

---

### 4.8 네비게이션 구조 재편 (중기, P3) ✅ 완료

현재 21개 플랫 목록 → 3단 계층 구조로 전환.

```
▼ HARNESS GATE  [종합 상태 배지]
   A  목표 달성       [gate 배지]  → quality 탭
   B  행동 무결성     [gate 배지]  → agentic 탭
   C  신뢰성          [gate 배지]  → reliability 탭 (신규)
   D  성능 계약       [gate 배지]  → performance 탭
   E  보안 경계       [gate 배지]  → security 탭
   F  다중 에이전트   [gate 배지]  → (agentic 서브탭)
▼ 운영 관측 (G)
   실시간 / 알림 / 이상감지 / 비용
▼ 도구 & 관리
   태스크 / 비교 / 골든 / 내보내기 / 투명성 / 설정
```

사이드바 상단 고정 영역에 **Harness Gate 미니 패널** (그룹별 색상 점) 항상 표시.

---

### 4.9 파일 변경 목록 (Phase 2) ✅ 전체 완료

| 파일 | 변경 유형 | 내용 | 상태 |
|------|----------|------|------|
| `serve/templates/dashboard2.html.j2` | 대규모 확장 | Harness Gate 패널(Overview); Group A 위젯(Quality); Group D SLA Gate(Performance); Loop Detection 섹션(Agentic); Reliability 탭 신규; Compare Harness 비교 행; nav `재현성` 탭 추가; Alpine.js `reliabilityData` + `loadReliability()` | ✅ |
| `serve/loader.py` | 확장 | `ResultFile`에 `harness_groups`, `loop_events`, `fault_tolerance_by_tool` 3개 필드; `_parse_harness_data()` 헬퍼; `has_harness` 프로퍼티; `parse_file()` 연결 | ✅ |
| `serve/routers/data.py` | 확장 | `get_result()` 응답에 harness 4개 키; `aggregate_tasks()` 응답에 `harness_groups`; `GET /results/{id}/reliability` 신규 엔드포인트 | ✅ |
| `serve/routers/config.py` | 확장 | `ThresholdBody`에 `harness_A~G + harness_overall` 8개 필드; `_DEFAULTS`에 기본값 0.70 | ✅ |
| `dashboard2.html.j2` (§4.4) | 확장 | 경계 흐름 분석 패널: 입력→실행→출력 3단 카드 + 위협 분류 세부 + 종합 판정 배너 | ✅ |
| Nav 구조 재편 (§4.8) | — | 3단 계층 구조 미구현 | ⏳ Phase 3 이동 |

---

### 4.10 구현 편차 / 실제 구현 현황

> **2026-04-17 검토 결과 수정:** 위젯 필터 버그 3건 발견·수정 완료.

| 항목 | 계획 | 실제 구현 | 영향 |
|------|------|----------|------|
| Graceful Degradation 매트릭스 | Agentic 탭에 FaultTolerance 테이블 추가 | Reliability 탭에서 `fault_tolerance_by_tool` 표시 | 위치 변경 (기능은 동일) |
| Security 탭 보안 경계 흐름 | 3단 입력→실행→출력 통합 뷰 | 미구현 | Phase 3으로 이동 |
| Nav Harness 정렬 구조 | 3단 계층 구조 | A~G 그룹별 2단 계층 구조 (2026-04-17 구현) | 계획보다 간소화 — gate pill + score badge 포함 |
| Reliability 탭 재현성 게이지 | task별 run_responses 히트맵 | completion_score 표준편차(CV%) 테이블로 대체 | 구현 간소화 |
| loader fault_tolerance_by_tool | task.extra.fault_tolerance = `{tool: {total, recovered}}` dict | task.extra.fault_tolerance = `{failures_detected, fallback_attempts}` 단일 dict → 첫 번째 실패 도구에 귀속 | Phase 1 구현 결과 그대로 수용 |
| **[버그 수정] Quality IFR 위젯 필터** | `filter(k.includes('goal')\|\|k.includes('instruction'))` | 실제 키 `"A"` — 조건 항상 false → 위젯 미표시 | **수정 완료**: `k==='A'` + `x-data="{ gA: data.harness_groups['A'] }"` + TCR·정확도·IFR 세부 KPI 추가 |
| **[버그 수정] Performance SLA 패널 필터** | `filter(k.includes('latency')\|\|k.includes('performance')\|\|...)` | 실제 키 `"D"` — 조건 항상 false → 패널 미표시 | **수정 완료**: `k==='D'` + P95·토큰 효율 세부 KPI 추가 |
| **[버그 수정] Reliability C 그룹 KPI 필터** | `filter(k.includes('reliab')\|\|...)` | 실제 키 `"C"` — 조건 항상 false → KPI 미표시 | **수정 완료**: `k==='C'` → Group C 종합 KPI 카드 표시 |
| **[구현완료] Goal-Action Alignment 산점도** | X=goal_alignment_score, Y=accuracy_score 산점도 | `extra.goal_alignment` 있는 태스크만 `x-if`로 표시, `#d2-goal-align-scatter` Plotly scatter (태스크 유형별 trace, 버블 크기=토큰, 0.7 기준선) — 2026-04-17 | ✅ |
| harness_groups 기존 파일 미지원 | Phase 1 이후 생성 파일만 | loader fallback 계산 추가 (2026-04-17) | 기존 파일도 A~G 자동 계산 후 대시보드 표시 |
| monitor harness_groups `status` → `gate` | dashboard 는 `gate` 키 사용 | monitor.py 는 `status` 키 저장 → dashboard 미표시 | **수정 완료 (2026-04-17)**: loader에서 `status`→`gate` 정규화 |

---

## 5. Phase 3 — 예제 개선 + QuickEval 통합 ✅ 완료

### 5.1 기존 예제 업데이트

#### `04_decorator_quickeval.py` — 신규 Config 시연 추가

```python
# ── Section 4: Harness Config 데코레이터 ──────────────────────────

from agent_evaluator import (
    InstructionConfig, LoopDetectionConfig, GoalAlignmentConfig,
    ReproducibilityConfig, FaultToleranceConfig, PlanConfig,
)

# 4-1. InstructionConfig — 형식·길이·내용 준수 검증
@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_format="json",
        required_sections=["answer", "confidence", "sources"],
        max_chars=500,
        forbidden_phrases=["모르겠습니다", "I cannot"],
        fail_on_violation=True,
    ),
)
def structured_agent(question: str, ground_truth: str = "") -> str:
    """JSON 형식 응답을 강제하는 에이전트."""
    return json.dumps({
        "answer": f"'{question}'에 대한 답변",
        "confidence": 0.85,
        "sources": ["출처1"],
    })

# 4-2. LoopDetectionConfig — 루프 감지
@agent_eval(
    monitor,
    task_type="tool_use",
    loop_detection=LoopDetectionConfig(
        consecutive_repeat_threshold=3,
        on_loop_detected="warn",
    ),
)
def loop_prone_agent(question: str, ground_truth: str = "") -> str:
    """도구 루프 가능성이 있는 에이전트 (시연용)."""
    ...

# 4-3. ReproducibilityConfig — 재현성 측정
@agent_eval(
    monitor,
    task_type="qa",
    reproducibility=ReproducibilityConfig(
        runs=3,
        similarity_measure="token_f1",
        reproducibility_threshold=0.85,
    ),
)
def variable_agent(question: str, ground_truth: str = "") -> str:
    """temperature=0.8 — 응답이 매번 달라질 수 있음."""
    ...

# 4-4. FaultToleranceConfig — 장애 허용
@agent_eval(
    monitor,
    task_type="tool_use",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        expected_fallback_tools={"web_search": ["backup_search", "cache_lookup"]},
    ),
)
def resilient_agent(question: str, ground_truth: str = "") -> str:
    """도구 실패 시 폴백 전략을 가진 에이전트."""
    ...
```

#### `01_layer1_all_metrics.py` — Harness Gate 결과 출력 추가

```python
# 기존 예제 말미에 추가
report = monitor.generate_report()
harness = report.to_dict().get("summary", {}).get("harness_groups", {})
if harness:
    print("\n── Harness Gate 요약 ──────────────────────")
    for group, data in harness.items():
        if group == "overall_gate":
            continue
        gate = data.get("gate", "N/A")
        icon = "✅" if gate == "pass" else ("⚠" if gate == "warn" else "❌")
        print(f"  {icon} {group}: {gate.upper()}")
    print(f"\n  전체 판정: {harness.get('overall_gate', 'N/A').upper()}")
```

#### `06_operational.py` — Harness CI/CD 게이팅 예시 추가

```python
# ── Section 6: Harness Gate — CI/CD 통합 ─────────────────────────

from agent_evaluator import QuickEval

eval = QuickEval.for_production(
    "results/",
    sla_p95=5.0,
    reproducibility_runs=3,
    security=True,
)

@eval.qa
def production_agent(question: str, ground_truth: str = "") -> str: ...

# 배치 실행
for q, gt in test_cases:
    production_agent(q, ground_truth=gt)

eval.save()  # results/quickeval.json + HTML 저장

# Harness Gate — 그룹별 임계값 검증
eval.gate(
    tcr=85,
    accuracy=70,
    instruction_adherence=0.8,   # Group A
    max_loop_count=0,             # Group B
    reproducibility=0.85,         # Group C
    p95_latency=5.0,              # Group D
    security=True,                # Group E (위협 0건)
)
# 실패 시 sys.exit(1) — CI/CD 파이프라인 자동 중단
```

---

### 5.2 신규 예제 — `08_harness_validation.py` ⏳ 예정

> Phase 3 구현 시 `report.extra_metrics["harness_groups"]` 경로로 접근해야 함 (§3.5 참고).  
> 아래 코드의 `report.to_dict()["summary"]["harness_groups"]` → `report.to_dict()["extra_metrics"]["harness_groups"]` 로 수정 필요.

Harness 관점의 전체 검증 흐름을 하나의 파일로 시연한다.

```python
"""
08_harness_validation.py — Harness 관점 전체 검증
==================================================
목적: 프로덕션 배포 전 에이전트를 7개 그룹 기준으로 체계적으로 검증

실행:
    python Evaluator_Examples/08_harness_validation.py

출력:
    results/harness_validation.json
    results/harness_validation.html
    콘솔: Harness Gate 판정 (PASS / WARN / FAIL)

의존성: 기본 설치만으로 실행 가능 (추가 extras 불필요)
"""
# 출처: Evaluator_Examples/08_harness_validation.py

import json
from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    InstructionConfig,
    LoopDetectionConfig,
    GoalAlignmentConfig,
    ReproducibilityConfig,
    FaultToleranceConfig,
    PlanConfig,
    agent_eval,
    SecurityConfig,
    LLMJudgeConfig,
)

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_security_metrics=True,
)

# ── Group A: 목표 달성 검증 ─────────────────────────────────────────
print("\n[Group A] 목표 달성 검증 — IFR + GoalAlignment")

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_format="json",
        required_sections=["answer", "confidence"],
        forbidden_phrases=["모르겠습니다"],
    ),
    goal_alignment=GoalAlignmentConfig(alignment_threshold=0.7),
)
def qa_agent(question: str, ground_truth: str = "") -> str: ...

# ── Group B: 행동 무결성 ────────────────────────────────────────────
print("\n[Group B] 행동 무결성 — LoopDetection + FaultTolerance")

@agent_eval(
    monitor,
    task_type="tool_use",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    fault_tolerance=FaultToleranceConfig(check_fallback_attempts=True),
)
def tool_agent(question: str, ground_truth: str = "") -> str: ...

# ── Group C: 신뢰성 ─────────────────────────────────────────────────
print("\n[Group C] 신뢰성 — Reproducibility")

@agent_eval(
    monitor,
    task_type="qa",
    reproducibility=ReproducibilityConfig(runs=3, reproducibility_threshold=0.85),
)
def stable_agent(question: str, ground_truth: str = "") -> str: ...

# ── Group D: 성능 계약 ──────────────────────────────────────────────
print("\n[Group D] 성능 계약 — SLA 모니터링은 PerformanceMonitor 자동 측정")

# ── Group E: 보안 경계 ──────────────────────────────────────────────
print("\n[Group E] 보안 경계 — Security 트래커 (enable_security_metrics=True)")

@agent_eval(
    monitor,
    task_type="tool_use",
    security=SecurityConfig(allowed_tools=["search", "calculator"]),
)
def secure_agent(question: str, ground_truth: str = "") -> str: ...

# ── Group A: Planning 에이전트 ──────────────────────────────────────
print("\n[Group A] Planning — PlanConfig 계획 품질 검증")

@agent_eval(
    monitor,
    task_type="planning",
    plan_tracking=PlanConfig(
        check_goal_coverage=True,
        check_executability=True,
        available_tools=["web_search", "calculator", "file_write"],
    ),
)
def planning_agent(question: str, ground_truth: str = "") -> str: ...

# ── 결과 저장 + Harness Gate ────────────────────────────────────────
monitor.save_to_file("harness_validation")
report = monitor.generate_report()

harness = report.to_dict()["summary"]["harness_groups"]
print("\n" + "="*60)
print("  Harness Gate 판정")
print("="*60)
for group_key, group_data in harness.items():
    if group_key == "overall_gate":
        continue
    gate = group_data["gate"]
    icon = "✅" if gate == "pass" else ("⚠ " if gate == "warn" else "❌")
    print(f"  {icon} {group_key.upper()}: {gate}")

overall = harness["overall_gate"]
icon = "✅" if overall == "pass" else ("⚠ " if overall == "warn" else "❌")
print(f"\n  {icon} 전체 판정: {overall.upper()}")
print("="*60)
```

---

### 5.3 예제 파일 최종 목록

```
Evaluator_Examples/
├── 01_layer1_all_metrics.py        # Harness Gate 요약 출력 추가
├── 02_layer2_agentic_security.py   # LoopDetectionConfig + FaultToleranceConfig 추가
├── 03_framework_adapters.py        # 변경 없음
├── 04_decorator_quickeval.py       # Config 6종 시연 섹션 추가
├── 05_streaming_alerts.py          # 변경 없음
├── 06_operational.py               # QuickEval.for_production() + gate() 확장 추가
├── 07_phoenix_hybrid.py            # 변경 없음
└── 08_harness_validation.py        # 신규 — Harness 7개 그룹 통합 검증
```

---

---

## 6. Phase 4 — 심화 Config 지표 5종 ✅ 완료

> **구현 완료:** 2026-04-17 · 신규 Config 5종 · 전체 테스트 2,467개 통과

### 6.1 신규 Config 클래스 5종

| Config | 그룹 | 측정 대상 | 핵심 필드 |
|--------|------|-----------|----------|
| `ScopeConfig` | **B** | 에이전트가 요청 범위를 벗어난 행동(외부 도구 호출, 무관한 주제)을 했는지 | `allowed_tools`, `allowed_topics`, `max_topic_drift` |
| `ContextRetentionConfig` | **A** | 멀티턴 대화에서 이전 턴의 정보를 유지하는 능력 | `key_entities`, `entity_window`, `semantic_similarity_threshold` |
| `ExplainabilityConfig` | **G** | 에이전트의 의사결정 과정이 추적 가능하고 설명 가능한지 | `require_reasoning`, `require_tool_justification`, `step_explainability` |
| `SubtaskConfig` | **A** | 복합 태스크를 서브태스크로 분해해 각각 완료하는 능력 | `subtask_definitions`, `completion_criterion`, `partial_credit` |
| `PropagationConfig` | **F** | 다중 에이전트 환경에서 정보가 정확하게 전달되는지 | `expected_fields`, `fidelity_threshold`, `transformation_allowed` |

### 6.2 구현 편차

- `AgentRoleConfig`, `GracefulDegradationConfig`, `ComplianceConfig`, `ResourceBudgetConfig`, `ConflictResolutionConfig` 도 Phase 4에서 함께 구현됨 (계획 대비 조기 구현)
- 전체 Phase 4 신규 Config: 10종

---

## 7. Phase 5 — 고급 Config 지표 7종 (보안 네이티브 통합 포함) ✅ 완료

> **구현 완료:** 2026-04-17 · 신규 Config 7종 + Group E 네이티브 트래커 통합

### 7.1 신규 Config 클래스 7종

| Config | 그룹 | 측정 대상 | 핵심 필드 |
|--------|------|-----------|----------|
| `ToolParameterSafetyConfig` | **B** | 도구 호출 파라미터의 안전성 (삽입 패턴, 경계 이탈) | `dangerous_patterns`, `param_schema`, `strict_mode` |
| `KnowledgeRetentionConfig` | **A** | 세션 간 또는 태스크 간 학습된 팩트를 유지하는 능력 | `knowledge_items`, `retention_window`, `similarity_threshold` |
| `RetryConsistencyConfig` | **C** | 재시도 시 일관된 전략을 유지하는지 (무작위 재시도 vs 전략적 재시도) | `expected_strategy`, `max_strategy_drift`, `penalize_random_retry` |
| `TTFTVariabilityConfig` | **D** | 첫 번째 토큰 생성 시간(TTFT)의 변동성 측정 | `target_ttft_ms`, `max_stddev_ms`, `window_size` |
| `ErrorDiagnosisConfig` | **G** | 에러 발생 시 에이전트가 원인을 올바르게 진단하는지 | `expected_error_categories`, `diagnosis_keywords`, `require_root_cause` |
| `ObservabilityConfig` | **G** | 에이전트 실행의 추적 가능성 및 로깅 품질 | `required_spans`, `required_attributes`, `otel_enabled` |
| `ConsensusConfig` | **F** | 다중 에이전트가 의사결정에서 합의에 도달하는지 | `consensus_threshold`, `voting_method`, `conflict_penalty` |

### 7.2 Group E 네이티브 트래커 통합

Phase 5에서 `_compute_harness_groups()` Group E 집계를 개선해 기존 네이티브 트래커 결과를 Group E 점수에 반영:

```python
# monitor.py _compute_harness_groups() Group E
_priv_esc_count = sum(1 for r in results if r.extra.get("privilege_escalation"))
_chain_attack_count = sum(1 for r in results if r.extra.get("chain_attack_detected"))
_leakage_count = sum(1 for r in results if r.extra.get("output_leakage"))
_injection_count = sum(1 for r in results if r.extra.get("input_injection_threats"))
# 이전: 오직 ThreatSeverityConfig/ComplianceConfig만 반영
# 이후: 네이티브 5개 트래커 결과도 Group E 점수에 반영
```

---

## 8. Phase 6 — 최종 Config 지표 5종 ✅ 완료

> **구현 완료:** 2026-04-17 · 신규 Config 5종

### 8.1 신규 Config 클래스 5종

| Config | 그룹 | 측정 대상 | 핵심 필드 |
|--------|------|-----------|----------|
| `IdempotencyConfig` | **C** | 동일한 입력으로 반복 실행 시 결과의 일관성 | `expected_hash`, `tolerance`, `n_runs` |
| `CostPredictabilityConfig` | **D** | 실제 비용이 예측 범위 내에 있는지 | `expected_cost_usd`, `tolerance_pct`, `model_pricing` |
| `ThreatResponseConfig` | **E** | 위협 감지 후 에이전트가 적절히 대응하는지 | `expected_responses`, `response_timeout_ms`, `require_alert` |
| `ContextWindowConfig` | **B** | 컨텍스트 창 한계 내에서 효율적으로 동작하는지 | `max_tokens`, `warn_threshold`, `truncation_strategy` |
| `LatencyAttributionConfig` | **G** | 지연시간을 구성 요소(LLM, 도구, 네트워크)별로 귀속하는 능력 | `component_breakdown`, `attribution_threshold`, `trace_enabled` |

### 8.2 Config 클래스 전체 목록 (33종)

Phase 1-6을 거쳐 구현된 전체 Config 클래스:

**Phase 1 (6종):** `InstructionConfig`, `LoopDetectionConfig`, `GoalAlignmentConfig`, `ReproducibilityConfig`, `FaultToleranceConfig`, `PlanConfig`

**Phase 2 (7종):** `SLAConfig`, `ThreatSeverityConfig`, `EfficiencyConfig`, `StateConsistencyConfig`, `DeadlockConfig`, `ObservabilityConfig` (초기 버전), `ConsensusConfig` (초기 버전)

**Phase 3 (5종):** `ScopeConfig`, `ContextRetentionConfig`, `ExplainabilityConfig`, `SubtaskConfig`, `PropagationConfig`

**Phase 4 (5종):** `AgentRoleConfig`, `GracefulDegradationConfig`, `ComplianceConfig`, `ResourceBudgetConfig`, `ConflictResolutionConfig`

**Phase 5 (5종):** `ToolParameterSafetyConfig`, `KnowledgeRetentionConfig`, `RetryConsistencyConfig`, `TTFTVariabilityConfig`, `ErrorDiagnosisConfig`

**Phase 6 (5종):** `IdempotencyConfig`, `CostPredictabilityConfig`, `ThreatResponseConfig`, `ContextWindowConfig`, `LatencyAttributionConfig`

---

## 9. Dashboard 지표 배치 재설계 (Zero-Base) ✅ 완료

> **작업 일자:** 2026-04-17 · 대상 파일: `dashboard2.html.j2`

### 9.1 Zero-Base 지표 배치 계획

모든 58개 지표를 Harness 7개 그룹에 맞게 대시보드 탭에 배치한다.

| 탭 (sec=) | Harness 그룹 | 기본 지표 | Harness Config 지표 |
|-----------|-------------|-----------|---------------------|
| `overview` | A–G 전체 | TCR, Accuracy, Hallucination, P95, Cost | Harness Gate 패널 (A–G 종합) |
| `quality` | **A** | TCR, Accuracy, Hallucination, Quality 5D, LLM Judge | IFR, Goal Alignment, Plan Coherence, Subtask Completion, Context Retention, Knowledge Retention |
| `agentic` | **B** + **F** | Tool F1, Tool Efficiency, Retry | Loop Detection, State Consistency, Scope, Tool Param Safety, Context Window (Group B) + Consensus, Propagation, Role Compliance, Conflict Resolution (Group F) |
| `reliability` | **C** | Error Free Rate, Retry Free Rate | Reproducibility, Fault Tolerance, SLA Breach, Graceful Degradation, Retry Consistency, Idempotency |
| `performance` | **D** | Latency P50/P95/P99, Tokens, Cost | SLA Gate, Efficiency, Resource Budget, TTFT Variability, Cost Predictability |
| `security` | **E** | Input/Output Security, Auth, Priv Esc, Attack | Threat Count, Compliance, Threat Response + OWASP 매핑 |
| `anomaly` | **G** | AnomalyDetector 이벤트 | Tool Coverage, Explainability, Error Diagnosis, Latency Attribution, Observability |
| `external` | — | RAG (Ragas), DeepEval | — |
| `conversation` | — | ConversationSession 지표 | — |
| `cost` | — | 비용 분석 | — |
| `feedback` | — | 암묵적 피드백 | — |
| `realtime` | — | 실시간 스트리밍 | — |
| `alerts` | — | 알림 이력 | — |
| `tasks` | — | 태스크 테이블 | — |
| `compare` | — | 멀티파일 비교 | — |
| `transparency` | — | 추적/감사 로그 | — |
| `insights` | — | 인사이트·추천 | — |

### 9.2 이전(Migration) 계획

기존 배치에서 개선된 배치로의 변경 사항:

| 항목 | 기존 위치 | 새 위치 | 변경 이유 |
|------|-----------|---------|-----------|
| Loop Detection 이벤트 | `agentic` (말미) | `agentic` + **Group B KPI 추가** | Group B 요약 패널 선행 표시 |
| Multi-Agent Coordination | `agentic` 내 | `agentic` + **Group F KPI 추가** | F 그룹 집계 점수 가시화 |
| Group E (보안 경계) | 미표시 | `security` + **Group E KPI 추가** | 기존 보안 내용 보완 |
| Group G (관측성) | 미표시 | `anomaly` + **Group G KPI 추가** | 관측성 지표 가시화 |
| Group C Phase 4-6 | 미표시 | `reliability` + **확장 KPI 추가** | Degradation·RetryConsistency·Idempotency |
| Group D Phase 5-6 | 미표시 | `performance` + **확장 KPI 추가** | TTFT Variability·Cost Predictability |
| Group A Phase 3-5 | IFR만 표시 | `quality` + **확장 KPI 추가** | GoalAlign·Plan·Subtask·ContextRet·KnowledgeRet |

### 9.3 구현된 변경 사항 (`dashboard2.html.j2`)

**Group A 확장 (quality 탭):**
- 신규 KPI 카드 6개 추가: 목표 정렬·계획 일관성·서브태스크 완료·컨텍스트 유지·지식 유지

**Group B 신규 패널 (agentic 탭):**
- `data.harness_groups['B']` 기반 KPI 패널 신규 삽입 (Loop Detection 이벤트 앞)
- 포함 지표: Group B 종합·루프 감지율·상태 일관성·범위 준수율·도구 파라미터 안전·컨텍스트 윈도우

**Group C 확장 (reliability 탭):**
- 신규 KPI 카드 3개 추가: 우아한 저하·재시도 일관성·멱등성

**Group D 확장 (performance 탭):**
- 신규 KPI 카드 4개 추가: 리소스 예산·TTFT 변동성·비용 예측성

**Group E 신규 패널 (security 탭):**
- `data.harness_groups['E']` 기반 KPI 패널 신규 삽입 (OWASP 테이블 앞)
- 포함 지표: Group E 종합·탐지된 위협·컴플라이언스·권한 상승율·공격 체인 탐지·위협 대응 점수

**Group F 신규 패널 (agentic 탭):**
- `data.harness_groups['F']` 기반 KPI 패널 신규 삽입 (Multi-Agent Coordination 끝 ~ Workflow 시작 사이)
- 포함 지표: Group F 종합·합의율·전파 충실도·역할 준수율·충돌 해소율

**Group G 신규 패널 (anomaly 탭):**
- `data.harness_groups['G']` 기반 KPI 패널 신규 삽입 (AnomalyDetector 이벤트 앞)
- 포함 지표: Group G 종합·도구 커버리지·설명가능성·오류 진단·지연 귀속 정확도·관측성 점수

### 9.4 조건부 표시 원칙

모든 Harness 패널은 `x-show="gX.details && gX.details.someField!=null"` 패턴으로 조건부 표시한다:
- Config를 사용하지 않은 경우 → 해당 KPI 카드가 자동으로 숨겨짐
- Harness Groups가 없는 경우 → `x-if="data.harness_groups && data.harness_groups['X']"` 조건으로 패널 전체 숨김
- 기존 평가 결과 파일도 `_compute_harness_groups_fallback()` 으로 기본 점수 표시 가능

---

## 10. 파일별 변경 범위 요약

### Phase 1 (지표 + 데코레이터)

```
agent_evaluator/
├── decorators.py                   ★★★ 대규모 확장
│   └── InstructionConfig, LoopDetectionConfig, GoalAlignmentConfig,
│       ReproducibilityConfig, FaultToleranceConfig, PlanConfig 추가
│       agent_eval / batch_eval / conversation_eval 파라미터 확장
│       _build_task_result() 처리 로직 추가 (~200줄)
├── __init__.py                     ★★  Config 6종 공개 API 추가
├── quick_eval.py                   ★★  for_harness() / for_production() 팩토리
├── helpers/taskresult_helpers.py   ★★  평가 헬퍼 함수 6종 추가
└── core/trackers/monitor.py        ★★  harness_groups 집계 추가

tests/
├── test_decorators_harness.py      ★★★ 신규 (예상 120개+)
└── test_report_harness_groups.py   ★★  신규 (예상 40개+)
```

### Phase 2 (Dashboard) ✅

```
agent_evaluator/serve/
├── templates/dashboard2.html.j2    ★★★ 대규모 확장                              ✅
│   ├── Overview: Harness Gate 패널 (7그룹 pass/warn/fail 카드)
│   ├── Quality: Group A 지표 위젯 (harness_groups 동적 렌더링)
│   ├── Performance: Group D SLA Gate 패널
│   ├── Agentic: Loop Detection 이벤트 테이블
│   ├── Reliability 탭 신규 (nav + 섹션 + loadReliability() + reliabilityData 상태)
│   │   └── 재현성(CV%) · FaultTolerance by Tool · Loop Events
│   └── Compare: Harness 그룹별 비교 행 동적 렌더링
├── loader.py                       ★★  신규 필드 로드 추가                        ✅
│   ├── ResultFile.harness_groups / loop_events / fault_tolerance_by_tool
│   ├── _parse_harness_data() 헬퍼
│   └── has_harness 프로퍼티
└── routers/
    ├── data.py                     ★★  aggregate 확장 + /reliability 신규         ✅
    │   ├── get_result() 응답에 harness 4개 키
    │   ├── aggregate_tasks() 응답에 harness_groups
    │   └── GET /results/{id}/reliability 신규 엔드포인트
    └── config.py                   ★   harness 임계값 추가                        ✅
        ├── ThresholdBody: harness_A~G + harness_overall
        └── _DEFAULTS: 기본값 0.70
```

### Phase 3 (예제)

```
Evaluator_Examples/
├── 01_layer1_all_metrics.py        ★   말미 Harness Gate 출력 추가
├── 02_layer2_agentic_security.py   ★   Config 2종 추가
├── 04_decorator_quickeval.py       ★★  Config 6종 섹션 추가
├── 06_operational.py               ★★  QuickEval.for_production() 추가
└── 08_harness_validation.py        ★★★ 신규 (~150줄)
```

---

## 11. 테스트 전략

### 7.1 Phase 1 테스트 항목 ✅ 완료

| 테스트 파일 | 커버 범위 | 계획 | **실제** |
|------------|----------|------|---------|
| `test_decorators_harness.py` | Config 6종 단위, 엣지케이스 (None/빈 입력/경계값), 데코레이터 통합 | 120개+ | **117개** |
| `test_report_harness_groups.py` | `harness_groups` 집계, `EvaluationReport.extra_metrics`, gate 판정 로직 | 40개+ | 포함 완료 |
| `test_param_cleanup.py` (수정) | `batch_eval`/`conversation_eval` 파라미터 수 검증 갱신 | — | 2개 수정 |

**전체 테스트 현황:** 2,467개 통과 (Phase 1 전 2,348개 → +117개 이상 순증)

**실제 테스트 클래스 구성 (`test_decorators_harness.py` 기준, 11개 클래스):**

| 클래스 | 내용 |
|--------|------|
| `TestInstructionConfigDefaults` | InstructionConfig 기본값 |
| `TestEvalInstructionAdherence` | 형식·길이·섹션·금지어 위반 케이스 |
| `TestLoopDetectionConfig` | LoopDetectionConfig 기본값 + 연속/윈도우 감지 |
| `TestEvalLoopDetection` | 루프 감지 로직 단위 |
| `TestGoalAlignmentConfig` | GoalAlignmentConfig 기본값 + 정렬 계산 |
| `TestReproducibilityConfig` | 재현성 점수 계산 (완전 일치/부분/0) |
| `TestFaultToleranceConfig` | 장애 허용 — 폴백 감지/없음/전실패 |
| `TestPlanConfig` | PlanConfig 기본값 + eval_plan_coherence |
| `TestDecoratorInstructionIntegration` | `@agent_eval` + InstructionConfig 통합 |
| `TestDecoratorLoopIntegration` | `@agent_eval` + LoopDetectionConfig 통합 |
| `TestDecoratorReproducibilityIntegration` | `@agent_eval` + ReproducibilityConfig 통합 |

**핵심 테스트 케이스:**

```python
# InstructionConfig — 형식 위반
def test_instruction_json_format_violation():
    config = InstructionConfig(expected_format="json")
    result = _eval_instruction_adherence("이건 평범한 텍스트", config)
    assert result["violations"] == ["형식 불일치: expected json"]
    assert result["score"] < 1.0

# InstructionConfig — 완전 준수
def test_instruction_full_compliance():
    config = InstructionConfig(
        expected_format="json",
        required_sections=["answer"],
        max_chars=100,
    )
    result = _eval_instruction_adherence('{"answer": "ok"}', config)
    assert result["score"] == 1.0
    assert result["violations"] == []

# LoopDetectionConfig — 연속 반복 감지
def test_loop_consecutive_repeat():
    config = LoopDetectionConfig(consecutive_repeat_threshold=3)
    tool_calls = [
        {"name": "search", "parameters": {"q": "test"}},
        {"name": "search", "parameters": {"q": "test"}},
        {"name": "search", "parameters": {"q": "test"}},
    ]
    result = _eval_loop(tool_calls, [], config)
    assert result["detected"] is True
    assert result["type"] == "consecutive_repeat"

# ReproducibilityConfig — 완전 일치
def test_reproducibility_perfect():
    # runs=3, 모든 응답 동일
    scores = [1.0, 1.0]  # pairwise: (1,2), (1,3), (2,3) = 모두 1.0
    assert _compute_reproducibility_score(scores) == 1.0

# FaultToleranceConfig — 폴백 감지
def test_fault_tolerance_fallback_detected():
    config = FaultToleranceConfig(check_fallback_attempts=True)
    tool_calls = [
        {"name": "web_search", "success": False},
        {"name": "backup_search", "success": True},  # 다른 도구 → 폴백
    ]
    result = _eval_fault_tolerance(tool_calls, config)
    assert result["fallback_attempts"] == 1
    assert result["recovery_rate"] == 1.0

# harness_groups gate 판정
def test_harness_gate_fail_on_security():
    # E 그룹에서 위협 감지 → 전체 fail
    report_dict = {..., "harness_groups": {"E": {"threat_rate": 5.0, "gate": "fail"}}}
    assert report_dict["harness_groups"]["overall_gate"] == "fail"
```

### 7.2 하위 호환성 보장

- 기존 `@agent_eval` 호출에 신규 파라미터 없으면 모든 Config `None` → 기존 동작 100% 동일
- `harness_groups`는 `generate_report()` 결과에 추가만 되므로 기존 `report.summary` 키 접근 코드 무중단
- `TaskResult.extra` 신규 키는 기존 코드에서 무시됨 (`extra.get("instruction_adherence")` → `None`)

### 7.3 성능 영향

| Config | 추가 시간 복잡도 | 비고 |
|--------|----------------|------|
| `InstructionConfig` | O(response_len) | 정규식 1회 패스 |
| `LoopDetectionConfig` | O(tool_calls_len) | 슬라이딩 윈도우 |
| `GoalAlignmentConfig` | O(question * tools) | 토큰 F1, 무시할 수준 |
| `FaultToleranceConfig` | O(tool_calls_len) | 선형 탐색 |
| `PlanConfig` | O(steps) | 파싱 + 키워드 매칭 |
| `ReproducibilityConfig` | O(runs * fn_time) | 주의: 함수를 N회 재실행 |

`ReproducibilityConfig`만 실행 시간에 유의미한 영향. `runs=1`이 기본값이 아닌 이유는 측정 의미 없음 — 기본값 `runs=3` 유지하되, **opt-in** (파라미터 제공 시에만 활성화).

---

## 12. 버전 릴리즈 계획

```
v0.8.2 (완료)
    └── 데코레이터 파라미터 구조화 (RetryConfig·LLMJudgeConfig·SecurityConfig)

★ Phase 1 단일 구현 (2026-04-17, v0.8.2 코드베이스에 적용)
    ├── InstructionConfig · LoopDetectionConfig · GoalAlignmentConfig  ✅
    ├── ReproducibilityConfig · FaultToleranceConfig · PlanConfig       ✅
    ├── harness_groups 집계 (EvaluationReport.extra_metrics)            ✅
    ├── QuickEval.for_harness() / for_production() 팩토리               ✅
    └── 테스트 117개 신규, 전체 2,467개                                  ✅

★ Phase 2 단일 구현 (2026-04-17)
    ├── Dashboard: Harness Gate 패널 (Overview)                        ✅
    ├── Dashboard: Group A 위젯 (Quality)                              ✅
    ├── Dashboard: Group D SLA Gate (Performance)                      ✅
    ├── Dashboard: Loop Detection 섹션 (Agentic)                       ✅
    ├── Dashboard: Reliability 탭 신규 (재현성·FaultTol·LoopEvents)    ✅
    ├── Dashboard: Compare 탭 Harness 비교 행                          ✅
    ├── loader.py: harness_groups / loop_events / fault_tolerance 파싱  ✅
    ├── data.py: /reliability 엔드포인트 신규                           ✅
    ├── config.py: harness 그룹별 임계값                               ✅
    ├── Security 탭 보안 경계 흐름 통합 뷰                              ✅
    ├── Goal-Action Alignment 산점도                                   ✅
    └── SLAConfig·ThreatSeverityConfig·EfficiencyConfig 등 7종 Config  ✅

★ Phase 3 단일 구현 (2026-04-17) — 예제 + QuickEval 통합
    ├── 08_harness_eval.py 신규 (674줄, Groups A-G 전 구간 예시)       ✅
    ├── QuickEval: 13개 harness 파라미터, harness_gate(), harness_summary() ✅
    └── ScopeConfig·ContextRetentionConfig·ExplainabilityConfig 등 5종 ✅

★ Phase 4 단일 구현 (2026-04-17) — 심화 Config 10종
    ├── AgentRoleConfig · GracefulDegradationConfig · ComplianceConfig  ✅
    ├── ResourceBudgetConfig · ConflictResolutionConfig                 ✅
    └── SubtaskConfig · PropagationConfig 등 추가 5종                  ✅

★ Phase 5 단일 구현 (2026-04-17) — 고급 Config 5종 + 보안 통합
    ├── ToolParameterSafetyConfig · KnowledgeRetentionConfig            ✅
    ├── RetryConsistencyConfig · TTFTVariabilityConfig · ErrorDiagnosisConfig ✅
    └── Group E _compute_harness_groups() 네이티브 트래커 통합          ✅

★ Phase 6 단일 구현 (2026-04-17) — 최종 Config 5종
    ├── IdempotencyConfig · CostPredictabilityConfig · ThreatResponseConfig ✅
    └── ContextWindowConfig · LatencyAttributionConfig                 ✅

★ Dashboard 재설계 (2026-04-17) — Zero-Base 지표 배치 + 신규 패널
    ├── Group A 확장: GoalAlign·Plan·Subtask·ContextRet·KnowledgeRet    ✅
    ├── Group B 신규 패널 (agentic 탭): Loop·StateConst·Scope·ToolParam·CtxWin ✅
    ├── Group C 확장: Degradation·RetryConsistency·Idempotency          ✅
    ├── Group D 확장: ResourceBudget·TTFTVariability·CostPredictability ✅
    ├── Group E 신규 패널 (security 탭): ThreatCount·Compliance·PrivEsc·ChainAttack·ThreatResponse ✅
    ├── Group F 신규 패널 (agentic 탭): Consensus·Propagation·Role·ConflictRes ✅
    └── Group G 신규 패널 (anomaly 탭): ToolCoverage·Explainability·ErrorDiag·LatencyAttr·Observability ✅

v0.9.0 (예정) — Nav 재편 + 문서 최종화
    ├── Nav Harness 그룹 중심 3단 계층 재편
    ├── 상관 히트맵 (Overview)
    └── 실패 연쇄 추적 (Insights 탭)
```

---

## 13. 위험 요소 및 완화 방안

| 위험 | 수준 | 완화 방안 |
|------|------|----------|
| `ReproducibilityConfig` side-effect | 🔴 높음 | `skip_side_effects=True` 기본값; `record_task()` 생략으로 monitor 오염 방지 |
| `PlanConfig` 계획 추출 실패 | 🟡 중간 | plan_field 키 없으면 score=None 반환, 오류 없이 skip |
| Dashboard 템플릿 9000줄 확장 부담 | 🟡 중간 | Alpine.js 컴포넌트 분리 (`x-component`) 적용; 섹션별 lazy init |
| harness_groups 집계 성능 | 🟢 낮음 | `generate_report()` 는 이미 모든 트래커 순회; 추가 비용 미미 |
| `GoalAlignmentConfig` 오탐율 | 🟡 중간 | keyword_overlap 기본값; `use_llm_scoring=True` 은 opt-in; `alignment_threshold` 조정 가능 |
| `InstructionConfig` 언어 감지 정밀도 | 🟢 낮음 | 유니코드 블록 기반 heuristic, opt-in; langdetect 설치 시 자동 연동 문서화 |
| v0.9.0 대규모 Dashboard 변경 → 회귀 | 🟡 중간 | 기존 대시보드(`dashboard.html.j2`)를 fallback으로 유지; `--legacy` 플래그 제공 |

---

---

*작성: 2026-04-17 (v0.8.2 코드베이스 분석 및 Harness 관점 지표 설계)*  
*Phase 1–2 완료 기준 갱신: 2026-04-17 — 구현 편차·실제 테스트 수 반영·버전 계획 수정*  
*Phase 3–6 완료 갱신: 2026-04-17 — 33종 Config 클래스 전체 구현 완료·전체 테스트 2,467개 통과*  
*Dashboard 재설계 완료 갱신: 2026-04-17 — Zero-Base 계획 수립·신규 6개 Harness 패널(B·C확장·D확장·E·F·G) 구현·§9 추가*
