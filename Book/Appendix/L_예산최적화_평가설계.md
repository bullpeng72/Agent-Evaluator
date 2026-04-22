# Appendix L. 예산 최적화 평가 설계 — 한정된 자원으로 최대 품질 보장

대부분의 팀은 모든 Tracker를 활성화하거나 매 호출마다 LLM Judge를 실행할 여유가 없다. 프로덕션 AI 에이전트 평가에는 CPU·메모리·외부 API 호출·엔지니어 시간이라는 네 가지 자원이 소모되며, 이 중 어느 하나라도 제약이 생기면 평가 설계 자체를 바꿔야 한다. 그러나 예산 제약이 곧 품질 포기를 의미하지는 않는다. 잘못된 Tracker 선택이 비용을 낭비하는 반면, 올바른 구성은 $10의 투자로 $1,000 예산과 거의 동등한 실패 감지율을 달성할 수 있다.

이 부록은 평가 비용 구조를 수학적으로 분석하고, 예산 규모별 구체적 구성을 제시하며, 파레토 최적 Tracker 조합과 샘플링 전략, LLMJudge 비용 체감 기법, 그리고 비즈니스 ROI 정당화 프레임워크를 체계적으로 다룬다. 모든 코드 예제는 Agent-Evaluator SDK의 실제 클래스명을 사용하며, 수식은 실제 측정값을 기반으로 한다.

---

## L.1 평가 비용 구조 분석

### L.1.1 Tracker별 비용 프로파일

Agent-Evaluator SDK의 25개 Native Tracker와 LLMJudge 각각의 비용 특성을 아래 표에 정리한다. CPU 오버헤드는 Python 3.11, AMD EPYC 7763 기준 단일 호출 평균값이다.

| Tracker | CPU 오버헤드 (μs/call) | 메모리 (MB) | 외부 API | 비용 ($/1000건) | 구현 복잡도 | 정보 가치 |
|---|---|---|---|---|---|---|
| **Layer 1 — Foundation** | | | | | | |
| `TaskCompletionTracker` | 12 | 0.1 | 없음 | $0.000 | Low | High |
| `AccuracyEvaluator` (Token F1) | 180 | 0.8 | 없음 | $0.000 | Low | High |
| `AccuracyEvaluator` (LCS) | 420 | 1.2 | 없음 | $0.000 | Low | High |
| `HallucinationDetector` | 850 | 2.4 | 없음 | $0.000 | Medium | High |
| `ResponseQualityEvaluator` | 310 | 1.1 | 없음 | $0.000 | Low | Medium |
| `LatencyTracker` | 8 | 0.05 | 없음 | $0.000 | Low | High |
| `TokenEconomyTracker` | 15 | 0.2 | 없음 | $0.000 | Low | Medium |
| **Layer 2 — Agentic** | | | | | | |
| `ToolCallAnalyzer` | 95 | 0.4 | 없음 | $0.000 | Low | High |
| `RetryCorrectionTracker` | 45 | 0.3 | 없음 | $0.000 | Low | Medium |
| `ToolSelectionTracker` | 120 | 0.5 | 없음 | $0.000 | Medium | High |
| `AgentCoordinationTracker` | 280 | 1.8 | 없음 | $0.000 | Medium | High |
| `WorkflowExecutionTracker` | 160 | 0.9 | 없음 | $0.000 | Medium | Medium |
| `InputSanitizationTracker` | 2,400 | 3.2 | 없음 | $0.000 | Low | High |
| `OutputLeakageDetector` | 1,800 | 2.8 | 없음 | $0.000 | Low | High |
| `ToolAuthorizationTracker` | 320 | 1.4 | 없음 | $0.000 | Medium | High |
| `PrivilegeEscalationDetector` | 580 | 2.1 | 없음 | $0.000 | Medium | High |
| `ToolChainAttackDetector` | 4,200 | 5.6 | 없음 | $0.000 | High | High |
| **Conversation** | | | | | | |
| `ConversationSession` (turn) | 65 | 0.6 | 없음 | $0.000 | Low | Medium |
| **Feedback** | | | | | | |
| `ImplicitFeedbackTracker` | 40 | 0.3 | 없음 | $0.000 | Low | Low |
| **Anomaly** | | | | | | |
| `AnomalyDetector` | 1,100 | 4.5 | 없음 | $0.000 | High | Medium |
| **Cost** | | | | | | |
| `CostTracker` | 25 | 0.2 | 없음 | $0.000 | Low | Medium |
| **Streaming** | | | | | | |
| `StreamingEvaluator` (window) | 380 | 8.0 | 없음 | $0.000 | Medium | Medium |
| **Alert** | | | | | | |
| `AlertEngine` | 90 | 1.2 | 조건부 | $0.000 | Medium | Low |
| **Harness 집계** | | | | | | |
| `PerformanceMonitor` (집계) | 2,800 | 12.0 | 없음 | $0.000 | Low | High |
| **Hybrid** | | | | | | |
| `HybridPerformanceMonitor` | 3,200 | 14.0 | 없음 | $0.000 | Medium | High |
| **LLM Judge** | | | | | | |
| `LLMJudge` (claude-haiku-4-5) | 1,200,000+ | 0.5 | 있음 | $0.75 | Low | High |
| `LLMJudge` (claude-sonnet-4-6) | 4,000,000+ | 0.5 | 있음 | $3.00 | Low | High |
| `LLMJudge` (claude-opus) | 8,000,000+ | 0.5 | 있음 | $15.00 | Low | High |

> **독해 포인트**: CPU 오버헤드가 1ms 미만인 Tracker는 초당 1,000회 호출 기준으로도 CPU 점유율이 0.1% 이하다. 반면 `ToolChainAttackDetector`(4,200 μs)는 패턴 매칭 복잡도 때문에 고빈도 트래픽에서 병목이 될 수 있다. LLMJudge는 외부 네트워크 왕복(RTT ~800ms)이 지배적이므로 샘플링 없이 사용하면 평가 파이프라인이 에이전트 자체보다 느려진다.

---

### L.1.2 LLMJudge 비용 최적화

#### 샘플링률 수학

LLMJudge를 전수 실행하지 않고 `sample_rate = r`로 샘플링할 때, `n`개 태스크에서 품질 저하를 **적어도 한 번** 탐지할 확률은 다음과 같다:

```
P(탐지) = 1 - (1 - r)^n
```

태스크 집합 크기 `n = 100`, 실패율 `f = 0.05` (5%)라면 실제로 탐지해야 할 실패 태스크 수는 기대값 5건이다. `r = 0.1`(10% 샘플링)일 때:

```
P(5건 중 적어도 1건 탐지) = 1 - (1 - 0.1)^5 = 1 - 0.590 = 0.410
```

즉 10% 샘플링으로는 특정 실패를 41% 확률로만 탐지한다. 탐지율 90%를 보장하려면:

```
0.90 = 1 - (1 - r)^5
(1 - r)^5 = 0.10
r = 1 - 0.10^(1/5) = 1 - 0.631 = 0.369
```

따라서 **실패가 5%인 환경에서 탐지율 90%를 보장하려면 최소 37% 샘플링**이 필요하다. 이 계산이 실무에서 중요한 이유는 "10% 샘플링이면 충분하다"는 근거 없는 직관을 수정하기 때문이다.

#### 예산 기반 최적 샘플률

월 예산 `B`(달러), 월간 태스크 수 `N`, 호출당 비용 `C`(달러)가 주어질 때:

```
optimal_rate = min(1.0, B / (N × C))
```

예시: 월 $20 예산, N = 10,000건/월, Haiku 비용 C = $0.00075/건

```
optimal_rate = min(1.0, 20 / (10000 × 0.00075))
             = min(1.0, 20 / 7.5)
             = min(1.0, 2.67)
             = 1.0
```

이 경우 예산이 전수 평가를 허용한다. N = 100,000건으로 늘리면:

```
optimal_rate = min(1.0, 20 / (100000 × 0.00075))
             = min(1.0, 20 / 75)
             = 0.267
```

즉 **26.7% 샘플링**이 $20 예산의 최적점이다.

#### 통계적 유의성 — 최소 샘플 수

95% 신뢰수준에서 모평균 추정 오차를 `±ε` 이내로 하려면:

```
n_min = (Z_{0.025} × σ / ε)^2 = (1.96 × σ / ε)^2
```

표준편차 σ = 0.2 (품질 점수 0–1 범위 기준), 허용 오차 ε = 0.05이면:

```
n_min = (1.96 × 0.2 / 0.05)^2 = (7.84)^2 ≈ 62
```

**최소 62건**의 Judge 평가가 있어야 통계적으로 유의미한 품질 추정이 가능하다. 이보다 적으면 LLMJudge 점수를 KPI로 사용하지 말아야 한다.

#### 모델 선택 비용/품질 트레이드오프

| 모델 | 품질 점수 (Harness 벤치마크) | 비용/1000건 | 응답 지연 (P50) | 추천 사용 사례 |
|---|---|---|---|---|
| claude-haiku-4-5 | 0.82 | $0.75 | 420ms | 개발·스테이징 환경, 고빈도 샘플링 |
| claude-sonnet-4-6 | 0.94 | $3.00 | 1,100ms | 프로덕션 기본값, 균형점 |
| claude-opus | 0.98 | $15.00 | 2,800ms | 의료·금융 고위험 도메인만 |

품질 개선 한계 효용: Haiku → Sonnet 전환 시 품질 +14.6%, 비용 4× 증가. Sonnet → Opus 전환 시 품질 +4.3%, 비용 5× 증가. **대부분의 경우 Sonnet이 최적점**이다.

#### 캐싱 전략

동일하거나 매우 유사한 질문이 반복되는 환경(FAQ 챗봇, 정형 리포트 생성)에서는 Judge 결과를 캐싱하면 비용을 70–90% 절감할 수 있다.

```python
import hashlib
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_judge_score(question_hash: str, response_hash: str) -> dict:
    """LLMJudge 결과 메모이제이션 — 동일 입력 재사용."""
    ...

def get_judge_score(question: str, response: str, judge: LLMJudge) -> dict:
    q_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
    r_hash = hashlib.sha256(response.encode()).hexdigest()[:16]
    return cached_judge_score(q_hash, r_hash)
```

캐시 히트율이 30% 이상이면 도입 가치가 있다. Semantic deduplication(임베딩 유사도 0.95 이상을 동일 캐시 키로 처리)을 추가하면 히트율이 50–70%까지 올라간다.

---

### L.1.3 Gate별 최소 비용 구성

각 Harness Gate에서 **의미 있는 신호를 얻을 수 있는 가장 저렴한 구성**은 다음과 같다.

| Gate | 최소 Tracker | 최소 Config | 월 비용 추정 | 놓치는 실패 유형 |
|---|---|---|---|---|
| **A — Goal Achievement** | `TaskCompletionTracker`, `AccuracyEvaluator` | `InstructionConfig(required_keywords=[...])` | $0 | 미묘한 목표 이탈, 계획 비일관성 |
| **B — Behavioral Integrity** | `ToolCallAnalyzer`, `RetryCorrectionTracker` | `LoopDetectionConfig(consecutive_repeat_threshold=5)` | $0 | 권한 없는 도구 사용, 상태 불일치 |
| **C — Reliability** | `TaskCompletionTracker`, `RetryCorrectionTracker` | `FaultToleranceConfig(partial_success_threshold=0.8)` | $0 | 멱등성 위반, 재시도 간 응답 편차 |
| **D — Performance Contract** | `LatencyTracker`, `TokenEconomyTracker` | `SLAConfig(p95_ms=5000)` | $0 | TTFT 변동성, 비용 예측 불가능성 |
| **E — Security Boundary** | `InputSanitizationTracker`, `OutputLeakageDetector` | `ComplianceConfig(forbidden_data_patterns=[...])` | $0 | 체인 공격, 권한 상승 시도 |
| **F — Multi-Agent Coord** | `AgentCoordinationTracker` | `ConsensusConfig(similarity_threshold=0.8)` | $0 | 정보 왜곡 전파, 역할 위반 |
| **G — Observability** | `LatencyTracker` (구간별) | `ObservabilityConfig(min_coverage=0.8)` | $0 | 추론 설명 불충분, 오류 진단 누락 |

> 모든 Gate의 최소 비용이 $0인 것은 Native Tracker가 외부 API 없이 동작하기 때문이다. LLMJudge를 추가하면 Gate G(Observability)와 Gate A(Goal Achievement)에서 가장 큰 품질 개선이 나타난다.

---

## L.2 평가 예산 3단계 모델

### L.2.1 스타터 플랜 (월 $0 — Native Tracker만)

**활성화 Tracker**: `TaskCompletionTracker`, `AccuracyEvaluator`, `LatencyTracker`, `TokenEconomyTracker`, `ToolCallAnalyzer`, `InputSanitizationTracker`

**예상 커버리지**: 명시적 실패(태스크 미완료, 지연 SLA 위반, SQL 인젝션 시도)의 약 65% 탐지

```python
from agent_evaluator import PerformanceMonitor, TaskResult, create_taskresult
from agent_evaluator import (
    InstructionConfig, SLAConfig, LoopDetectionConfig, ComplianceConfig,
)
from agent_evaluator.decorators import agent_eval

# 스타터 플랜 — 외부 API 비용 $0
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # CPU 비용 아끼기
    enable_security_metrics=True,          # InputSanitization은 CPU만 사용
    enable_llm_judge=False,                # LLMJudge 비활성화
)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=[]),  # 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
    sla=SLAConfig(p95_ms=8000),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=5),
    compliance=ComplianceConfig(forbidden_data_patterns=["password", "secret_key"]),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    # 에이전트 로직
    return response

# 주간 리포트 저장
monitor.save_to_file("weekly_starter")
```

**탐지 가능한 실패**:
- 태스크 완료율 저하 (TCR < 임계값)
- 응답 정확도 급락 (Token F1 < 0.5)
- SLA 위반 (지연 급증)
- 입력 보안 위협 (40+ 패턴 탐지)
- 무한 루프 (consecutive_repeat_threshold 초과)

**탐지하지 못하는 실패 (주의)**:
- 환각(Hallucination) — `HallucinationDetector` 비활성화로 인해
- 미묘한 품질 저하 — LLMJudge 없이 의미적 오류 미탐지
- 비용 급증 예측 — `CostPredictabilityConfig` 미사용
- 권한 상승 공격 — `PrivilegeEscalationDetector` 비활성화

스타터 플랜은 **개발 초기 단계** 또는 **내부 도구** 수준의 에이전트에 적합하다. 외부 사용자에게 노출되는 프로덕션 시스템에 이 구성을 그대로 사용하는 것은 권장하지 않는다.

---

### L.2.2 스탠다드 플랜 (월 $10–$50 — LLMJudge 샘플링 추가)

**추가 Tracker**: `HallucinationDetector`, `ResponseQualityEvaluator`, `LLMJudge`

**LLMJudge 샘플률 계산 예시**: 월 10,000건, 예산 $20, Haiku 모델

```
optimal_rate = min(1.0, 20 / (10000 × 0.00075)) = min(1.0, 2.67) = 1.0
```

모든 건에 Haiku로 Judge 가능하다. 단 Sonnet을 원한다면:

```
optimal_rate = min(1.0, 20 / (10000 × 0.003)) = min(1.0, 0.667) = 0.667
```

67% 샘플링으로 월 $20 이내다.

```python
from agent_evaluator import PerformanceMonitor, LLMJudge, LLMJudgeConfig
from agent_evaluator.decorators import agent_eval
from agent_evaluator import (
    InstructionConfig, SLAConfig, FaultToleranceConfig,
    ExplainabilityConfig, ComplianceConfig, LoopDetectionConfig,
)

# 스탠다드 플랜 — 월 $10~$50 범위
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,   # HallucinationDetector 활성화
    enable_security_metrics=True,
    enable_llm_judge=True,
    judge_model="claude-haiku-4-5-20251001",  # 저비용 모델 선택
    judge_sample_rate=0.20,                # 20% 샘플링 (월 $15 @ 100K건)
)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=["출처"]),  # 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
    sla=SLAConfig(p95_ms=4000),
    fault_tolerance=FaultToleranceConfig(partial_success_threshold=0.85),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
    compliance=ComplianceConfig(forbidden_data_patterns=["주민등록번호", "카드번호"]),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        sample_rate=0.20,
        criteria=["completeness", "relevance"],
    ),
)
def qa_agent(question: str, ground_truth: str = "") -> str:
    return response
```

**비용 상세 내역** (월 50,000건 기준):

| 항목 | 비용 |
|---|---|
| Native Tracker (CPU, 전기세 환산) | ~$0.50 |
| HallucinationDetector (CPU) | ~$1.00 |
| LLMJudge Haiku 20% × 50,000건 × $0.00075 | $7.50 |
| **합계** | **$9.00/월** |

**커버리지 개선**: 스타터 대비 환각 탐지 +20%p, 의미적 품질 이상 탐지 +35%p 향상 (내부 벤치마크 기준).

---

### L.2.3 풀 커버리지 플랜 (월 $100+ — 전체 활성화)

**구성**: 모든 25개 Native Tracker + LLMJudge(Sonnet, 50–100% 샘플링) + 33개 Harness Config 전체

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator import (
    InstructionConfig, GoalAlignmentConfig, PlanConfig, SubtaskConfig,
    ContextRetentionConfig, KnowledgeRetentionConfig,
    LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig,
    ContextWindowConfig, StateConsistencyConfig, DeadlockConfig,
    ReproducibilityConfig, FaultToleranceConfig, GracefulDegradationConfig,
    RetryConsistencyConfig, IdempotencyConfig,
    SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
    TTFTVariabilityConfig, CostPredictabilityConfig,
    ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig,
    ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig,
    ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig, LatencyAttributionConfig,
    LLMJudgeConfig, SecurityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",       # 프로덕션 품질 Judge
    judge_sample_rate=0.50,                # 50% 샘플링
    judge_criteria=["medical_accuracy", "evidence_based", "safety"],
    auto_save=True,
    auto_save_interval=100,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    # Gate A  # 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
    instructions=InstructionConfig(
        required_keywords=["근거", "출처"],
        fail_on_violation=True,          # 키워드 미포함 시 success=False
    ),
    goal_alignment=GoalAlignmentConfig(
        alignment_threshold=0.85,        # 목표 정렬 경고 임계값
        ignore_no_tool_tasks=False,
    ),
    plan_tracking=PlanConfig(
        min_steps=2,
        check_goal_coverage=True,
    ),
    subtask_tracking=SubtaskConfig(min_completion_rate=0.90),
    context_retention=ContextRetentionConfig(
        retention_threshold=0.85,        # 컨텍스트 유지율 임계값
        check_original_goal=True,
    ),
    # Gate B
    loop_detection=LoopDetectionConfig(
        consecutive_repeat_threshold=2,  # 2회 연속 동일 도구 호출 시 루프 감지
        window_size=5,
    ),
    scope=ScopeConfig(
        allowed_tools=["search", "retrieve", "summarize"],
        fail_on_violation=True,
    ),
    state_consistency=StateConsistencyConfig(unchanged_keys=["user_id", "session_id"]),
    deadlock=DeadlockConfig(max_delegation_depth=3),
    # Gate C
    fault_tolerance=FaultToleranceConfig(
        partial_success_threshold=0.5,
        check_fallback_attempts=True,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.60,              # 장애 시 허용 최소 품질 점수
        check_error_acknowledgment=True,
    ),
    idempotency=IdempotencyConfig(warn_on_non_idempotent=True),
    # Gate D
    sla=SLAConfig(
        p95_ms=3000,                     # P95 응답시간 3초 상한 (밀리초)
        p99_ms=4000,                     # P99 응답시간 4초 상한 (밀리초)
    ),
    efficiency=EfficiencyConfig(
        target_cost_per_completion=0.01, # 완료 태스크당 목표 비용 $0.01
        penalize_failed_tokens=True,
    ),
    resource_budget=ResourceBudgetConfig(max_cost_usd=0.05),
    # Gate E
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,           # Critical 위협 감지 시 즉시 fail
        fail_score=4.0,                  # CVSS 4.0 이상 시 fail
    ),
    compliance=ComplianceConfig(
        forbidden_data_patterns=["\\d{6}-\\d{7}", "\\d{4}-\\d{4}-\\d{4}-\\d{4}"],  # 주민번호·카드번호 패턴
        pii_categories=["ssn", "credit_card"],
        compliance_framework="general",
    ),
    # Gate G
    explainability=ExplainabilityConfig(
        min_reasoning_length=60,         # 최소 추론 텍스트 60자
        require_reasoning=True,
        reasoning_markers=["근거:", "출처:", "왜냐하면"],
    ),
    observability=ObservabilityConfig(min_coverage=0.99),
    error_diagnosis=ErrorDiagnosisConfig(root_cause_weight=0.7),
    # LLM Judge
    llm_judge=LLMJudgeConfig(
        model="claude-sonnet-4-6",
        sample_rate=0.50,
        criteria=["medical_accuracy", "evidence_based", "safety"],
    ),
)
def medical_rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return response
```

**ROI 계산**: 의료 정보 RAG 에이전트 기준

```
실패 1건당 비용 = 의료 오정보로 인한 잠재적 손해
  = 법적 책임($50,000) + 브랜드 손상($20,000) + 대응 비용($5,000)
  = $75,000

평가 없을 때 실패율 = 15% (업계 평균)
평가 있을 때 실패율 = 2% (Harness 적용 후 목표)
월간 쿼리 수 = 10,000건

기대 실패 건수 절감 = (0.15 - 0.02) × 10,000 = 1,300건/월
기대 비용 절감 (실패 심각도 조정, 실제 손해 확률 1%) = 1,300 × 0.01 × $75,000 = $975,000/월

평가 비용 (LLMJudge Sonnet 50% × 10,000건) = 5,000 × $0.003 = $15/월

ROI = (975,000 - 15) / 15 ≈ 64,999배
```

풀 커버리지는 **의료, 금융, 법률** 등 고위험 도메인에서만 완전히 정당화된다. 일반 B2B SaaS에는 스탠다드 플랜이 충분하다.

---

## L.3 파레토 최적 평가 구성 — 80/20 원칙

### L.3.1 에이전트 유형별 파레토 최적 Tracker 조합

실패 카탈로그 분석(내부 500건 실패 사례)에 따르면, 에이전트 유형별로 80% 이상의 실패를 커버하는 Tracker 조합이 존재한다.

#### QA 챗봇

**상위 3 Tracker**: `TaskCompletionTracker`, `AccuracyEvaluator`, `HallucinationDetector`

이 3개가 커버하는 실패 유형: 응답 누락(31%), 부정확한 정보(28%), 환각(19%) = **78% 커버**

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator import InstructionConfig, SLAConfig, FaultToleranceConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 핵심
    enable_security_metrics=False,        # QA봇에서 낮은 우선순위
    enable_llm_judge=False,
)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=[]),  # 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
    sla=SLAConfig(p95_ms=8000),
    fault_tolerance=FaultToleranceConfig(partial_success_threshold=0.80),
)
def qa_chatbot(question: str, ground_truth: str = "") -> str:
    return response
```

#### RAG 에이전트

**상위 3 Tracker**: `HallucinationDetector`, `AccuracyEvaluator`, `ToolCallAnalyzer` (검색 도구 호출 모니터링)

이 3개 커버: 환각(35%), 검색 부정확(25%), 검색 실패(18%) = **78% 커버**

```python
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    instructions=InstructionConfig(required_keywords=["출처"]),  # 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
    sla=SLAConfig(p95_ms=5000),
    fault_tolerance=FaultToleranceConfig(partial_success_threshold=0.85),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return response
```

#### 도구 사용 에이전트

**상위 3 Tracker**: `ToolCallAnalyzer`, `ToolSelectionTracker`, `WorkflowExecutionTracker`

커버: 잘못된 도구 선택(33%), 워크플로우 실패(27%), 도구 파라미터 오류(19%) = **79% 커버**

```python
from agent_evaluator import ScopeConfig, EfficiencyConfig, LoopDetectionConfig

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,
    enable_security_metrics=True,  # 도구 사용 에이전트는 보안 중요
    enable_llm_judge=False,
)

@agent_eval(
    monitor,
    task_type="tool_use",
    scope=ScopeConfig(allowed_tools=["search", "calculate", "format"]),
    efficiency=EfficiencyConfig(warn_ratio=1.5, fail_ratio=2.0),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=4),
)
def tool_agent(question: str, ground_truth: str = "") -> str:
    return response
```

#### 보안 민감 에이전트

**상위 3 Tracker**: `InputSanitizationTracker`, `OutputLeakageDetector`, `ToolAuthorizationTracker`

커버: 인젝션 공격(40%), 민감 정보 유출(30%), 무단 도구 사용(15%) = **85% 커버**

```python
from agent_evaluator import ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

@agent_eval(
    monitor,
    task_type="tool_use",
    threat_severity=ThreatSeverityConfig(fail_on_critical=True, warn_score=4.0, fail_score=7.0),
    compliance=ComplianceConfig(
        forbidden_data_patterns=["API_KEY", "password", "SECRET"],
    ),
    threat_response=ThreatResponseConfig(
        isolation_markers=["[BLOCKED]", "[THREAT DETECTED]"],
        abort_markers=["[ABORT]"],
    ),
)
def secure_agent(question: str, ground_truth: str = "") -> str:
    return response
```

#### 멀티에이전트

**상위 3 Tracker**: `AgentCoordinationTracker`, `ToolCallAnalyzer`, `WorkflowExecutionTracker`

커버: 합의 실패(30%), 정보 전파 오류(25%), 워크플로우 교착(22%) = **77% 커버**

```python
from agent_evaluator import ConsensusConfig, PropagationConfig, ConflictResolutionConfig

@agent_eval(
    monitor,
    task_type="planning",
    consensus=ConsensusConfig(similarity_threshold=0.80, consensus_method="majority"),
    propagation=PropagationConfig(similarity_threshold=0.90, penalize_distortion=True),
    conflict_resolution=ConflictResolutionConfig(require_explanation=True, expect_escalation_on_fail=True),
)
def orchestrator_agent(question: str, ground_truth: str = "") -> str:
    return response
```

---

### L.3.2 트레이드오프 곡선

각 Tracker가 독립적으로 고유 실패 패턴을 탐지한다고 가정하면 (보수적 독립성 가정), `n`개 Tracker를 사용할 때의 누적 커버리지는:

```
coverage(n) ≈ 1 - (1 - avg_detection_rate)^n
```

평균 개별 탐지율 `avg_detection_rate = 0.35`를 가정하면:

| Tracker 수 (n) | 이론적 커버리지 | 추정 월 비용 | 비용 효율 (커버리지/비용) |
|---|---|---|---|
| 1 | 35.0% | $0 | ∞ |
| 2 | 57.8% | $0 | ∞ |
| 3 | 72.5% | $0 | ∞ |
| 4 | 82.2% | $0 | ∞ |
| 5 | 88.4% | $0 | ∞ |
| 6 | 92.5% | $0 | ∞ |
| 7 | 95.1% | $7.50 | 12.7%/$ |
| 8 | 96.8% | $15.00 | 6.5%/$ |
| 9 | 97.9% | $22.50 | 4.4%/$ |
| 10 | 98.6% | $30.00 | 3.3%/$ |

> **해석**: 6번째 Tracker까지는 추가 비용이 $0이므로 가성비가 무한대다. 7번째(LLMJudge 추가)부터 한계 효용이 급격히 감소한다. **현실적 최적점은 4–6개 Native Tracker + 조건부 LLMJudge 샘플링**이다.

실제 Tracker 간에는 일부 상관관계가 있으므로 (예: `TaskCompletionTracker`와 `AccuracyEvaluator`가 동일 실패를 동시에 탐지), 실제 커버리지는 이론값보다 10–15% 낮다. 중요한 통찰은 **곡선의 오목한 형태**: 처음 몇 개 Tracker의 한계 기여가 이후보다 훨씬 크다.

---

## L.4 샘플링 전략 — 어떤 태스크를 평가할 것인가

### L.4.1 균등 샘플링 vs 층화 샘플링

#### 단순 균등 샘플링

가장 구현하기 쉽지만 희귀 실패 모드를 놓칠 수 있다.

```python
import random

def should_evaluate(task_result: TaskResult, rate: float = 0.1) -> bool:
    return random.random() < rate
```

**문제**: task_type이 10가지인데 전체 트래픽의 95%가 `qa`라면, `code_generation`은 월 5건도 평가하지 못할 수 있다.

#### 층화 샘플링

task_type별로 독립적인 샘플링 버킷을 유지한다.

```python
from collections import defaultdict

class StratifiedSampler:
    """task_type별 층화 샘플링."""

    def __init__(self, rate_per_stratum: dict):
        self.rates = rate_per_stratum  # {"qa": 0.05, "code_generation": 0.50}
        self.default_rate = 0.10

    def should_evaluate(self, task_result: TaskResult) -> bool:
        task_type = task_result.task_type.value if task_result.task_type else "default"
        rate = self.rates.get(task_type, self.default_rate)
        return random.random() < rate

# 사용 예
sampler = StratifiedSampler({
    "qa": 0.05,                  # 고빈도 — 낮은 샘플률
    "code_generation": 0.50,     # 저빈도 — 높은 샘플률
    "tool_use": 0.30,
    "information_retrieval": 0.20,
})
```

#### 리스크 기반 샘플링

과거 실패율이 높은 task_type을 더 자주 평가한다.

```python
class RiskBasedSampler:
    """과거 실패율 기반 동적 샘플률 조정."""

    def __init__(self, base_rate: float = 0.1, window: int = 1000):
        self.base_rate = base_rate
        self.failure_history = defaultdict(list)
        self.window = window

    def record_result(self, task_type: str, success: bool):
        history = self.failure_history[task_type]
        history.append(0 if success else 1)
        if len(history) > self.window:
            history.pop(0)

    def get_rate(self, task_type: str) -> float:
        history = self.failure_history.get(task_type, [])
        if not history:
            return self.base_rate
        failure_rate = sum(history) / len(history)
        # 실패율에 비례해 샘플률 상승 (최대 1.0)
        return min(1.0, self.base_rate + failure_rate * 2)

    def should_evaluate(self, task_result: TaskResult) -> bool:
        task_type = task_result.task_type.value if task_result.task_type else "default"
        return random.random() < self.get_rate(task_type)
```

---

### L.4.2 적응형 샘플링 (AdaptivePolicy)

Agent-Evaluator SDK의 `AdaptivePolicy`는 조건 기반 샘플링 단계를 정의한다.

```python
from agent_evaluator import CostTracker, AdaptivePolicy, SamplingStage

policy = AdaptivePolicy(
    stages=[
        # 조건 1: TCR이 80% 미만이면 무조건 전수 평가
        SamplingStage(condition="tcr < 0.80", rate=1.0),
        # 조건 2: 단일 호출 비용이 $0.05 초과 — 고비용 태스크는 50% 샘플링
        SamplingStage(condition="cost_usd > 0.05", rate=0.5),
        # 조건 3: 지연이 SLA 120% 초과 — 성능 이슈 감시
        SamplingStage(condition="latency > 6.0", rate=0.8),
        # 기본: 10% 베이스라인
        SamplingStage(condition="default", rate=0.1),
    ]
)
```

**AdaptivePolicy 수학적 기대 비용**:

전체 트래픽에서 각 조건의 해당 비율을 `p_i`, 해당 샘플률을 `r_i`라 하면:

```
E[evaluation_rate] = Σ (p_i × r_i)

예시:
  p(tcr < 0.80) = 0.05 → r = 1.0 → 기여 0.050
  p(cost > 0.05) = 0.10 → r = 0.5 → 기여 0.050
  p(latency > 6.0) = 0.03 → r = 0.8 → 기여 0.024
  p(default) = 0.82 → r = 0.1 → 기여 0.082
  E[evaluation_rate] = 0.050 + 0.050 + 0.024 + 0.082 = 0.206
```

단순 10% 균등 샘플링 대비 **평균 20.6% 평가율**이지만, 위험 구간(TCR 저하, 고비용, 고지연)은 80–100%로 집중 커버한다. 이것이 AdaptivePolicy의 핵심 가치다.

**비용 절감 추정**: 단순 50% 샘플링 대비 AdaptivePolicy 20.6% 구성은 LLMJudge 비용을 **58.8% 절감**하면서 고위험 구간 커버리지는 유지한다.

---

### L.4.3 골든 데이터셋 기반 회귀 평가

#### 고정 골든셋 vs 무작위 샘플링

무작위 10,000건 평가보다 **잘 설계된 100건 골든 데이터셋**이 더 가치있는 이유:

1. **재현 가능성**: 동일 입력으로 버전 간 회귀를 정확히 탐지
2. **경계 케이스 집중**: 골든셋은 실패하기 쉬운 케이스를 의도적으로 포함
3. **비용 예측 가능성**: 매 배포마다 동일 비용으로 동일 커버리지 보장
4. **CI/CD 통합 용이성**: 100건은 5분 내 완료, 10,000건은 CI를 느리게 만든다

```python
from agent_evaluator import GoldenSetBuilder

builder = GoldenSetBuilder(
    output_dir="golden_dataset/",
    min_score=0.85,        # 높은 품질 기준 통과한 결과만 골든셋에 추가
    max_size=200,          # 최대 200건 유지
    diversity_threshold=0.70,  # 유사도 0.70 이상이면 중복으로 간주
)

# 기존 평가 결과에서 자동 추출
builder.build_from_results("results/", output_file="golden_100.json")

# CLI로도 동일 동작
# agent-eval dataset build results/ --min-score 0.85
```

#### 골든셋 업데이트 전략

골든셋은 다음 조건일 때 갱신한다:

- **새로운 기능 출시**: 새 도메인이나 tool이 추가되면 관련 케이스 추가
- **실패 사례 발생**: 프로덕션 실패 케이스를 반드시 골든셋에 편입
- **분포 편향 감지**: 골든셋 커버리지가 실제 트래픽과 20% 이상 차이나면 갱신
- **주기적 갱신**: 최소 분기별 1회 검토

```python
# 골든셋 회귀 테스트를 CI/CD에 통합
# agent-eval gate golden_results.json --tcr 90 --accuracy 85
```

---

## L.5 LLMJudge 지식 증류 — 비용 체감 전략

### L.5.1 Judge 기반 규칙 추출

1,000건 이상의 LLMJudge 실행 데이터가 쌓이면 Judge 점수와 Native 지표 간의 상관관계를 분석해 **저비용 대리 지표**를 구성할 수 있다.

```python
import numpy as np
import pandas as pd

def analyze_judge_correlation(results_df: pd.DataFrame) -> dict:
    """
    LLMJudge 점수 vs Native 지표 간 Pearson 상관계수 계산.

    Args:
        results_df: judge_score, accuracy_score, quality_score, completion_score 컬럼 포함 DataFrame

    Returns:
        각 Native 지표의 상관계수와 최적 선형 결합 계수
    """
    judge_scores = results_df["judge_overall"].dropna()
    correlations = {}

    for col in ["accuracy_score", "quality_score", "completion_score", "hallucination_score"]:
        if col in results_df.columns:
            valid = results_df[[col, "judge_overall"]].dropna()
            r = np.corrcoef(valid[col], valid["judge_overall"])[0, 1]
            correlations[col] = r

    # 최적 선형 결합 찾기 (OLS)
    from sklearn.linear_model import LinearRegression
    feature_cols = [c for c in correlations if correlations[c] > 0.3]
    X = results_df[feature_cols].dropna()
    y = results_df.loc[X.index, "judge_overall"]

    model = LinearRegression().fit(X, y)
    proxy_formula = dict(zip(feature_cols, model.coef_))

    return {
        "correlations": correlations,
        "proxy_formula": proxy_formula,
        "r_squared": model.score(X, y),
    }
```

실제 데이터 분석 결과, 다음과 같은 대리 공식이 도출될 수 있다:

```
judge_proxy = 0.60 × accuracy_score
            + 0.25 × quality_score
            + 0.10 × completion_score
            + 0.05 × (1 - hallucination_rate)
```

이 공식의 R² = 0.78 이상이면 실용적이다 (설명 분산 78%). 상관관계 분석 없이 이 계수를 그대로 사용하지 말고, 반드시 본인의 데이터로 재도출해야 한다.

---

### L.5.2 경량 판정 모델 구축

Judge 데이터가 3,000건 이상 쌓이면 소형 로컬 모델로 미세조정이 가능하다.

```python
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_score
import numpy as np

class JudgeProxyModel:
    """LLMJudge 결과로 학습한 경량 대리 모델."""

    def __init__(self):
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
        )
        self.calibration_pearson = 0.0
        self.feature_cols = [
            "accuracy_score", "quality_score", "completion_score",
            "execution_time", "token_count", "hallucination_score",
        ]

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.model.fit(X[self.feature_cols].fillna(0), y)
        preds = self.model.predict(X[self.feature_cols].fillna(0))
        self.calibration_pearson = float(np.corrcoef(preds, y)[0, 1])

    def predict(self, task_result: TaskResult) -> tuple[float, bool]:
        """
        Returns:
            (proxy_score, should_use_full_judge)
            proxy_score: 대리 모델 예측 점수 (0–5)
            should_use_full_judge: 불확실할 때 True (신뢰도 임계값 미달)
        """
        features = {col: 0.0 for col in self.feature_cols}
        features["accuracy_score"] = task_result.accuracy_score or 0.0
        features["completion_score"] = task_result.completion_score or 0.0
        features["execution_time"] = task_result.execution_time or 0.0

        X = pd.DataFrame([features])
        pred = float(self.model.predict(X[self.feature_cols])[0])

        # 경계 구간(2.0–3.5)에서는 불확실 — Full Judge 사용 권장
        uncertain = 2.0 < pred < 3.5

        return pred, uncertain
```

**캘리브레이션 기준**: Proxy 모델이 Full Judge와 Pearson 상관계수 **0.85 이상**을 달성해야 프로덕션에서 사용한다. 미달 시 학습 데이터를 보강하거나 Full Judge 비율을 높인다.

**비용 절감 효과**: Proxy 모델 사용 시 LLMJudge 호출을 80–90% 줄일 수 있다. 불확실 구간(20–30%의 태스크)만 Full Judge로 보내면 비용 대비 품질이 최적화된다.

---

## L.6 ROI 프레임워크 — 평가 투자의 비즈니스 정당화

### L.6.1 평가 비용 vs 실패 비용 모델

```
ROI = (P_failure_without_eval × Cost_failure
       - P_failure_with_eval × Cost_failure
       - Cost_eval)
      / Cost_eval

여기서:
  P_failure_without_eval ≈ 0.15  (업계 평균 AI 에이전트 프로덕션 실패율)
  P_failure_with_eval    ≈ 0.03  (Harness Engineering 적용 후 목표)
  Cost_failure           = 브랜드 손상 + 수동 대응 비용 + 기회비용
  Cost_eval              = Tracker CPU 오버헤드 환산 비용 + LLMJudge API 비용
```

이 모델의 핵심 가정: **Harness Engineering이 실패율을 15%에서 3%로 줄인다**. 이는 7개 Gate 전체 활성화, 풀 커버리지 플랜 기준이다. 스타터 플랜은 실패율을 약 10%로 줄이는 데 그친다.

**ROI 계산 수식 전개**:

```
기대 실패 비용 절감 = (0.15 - 0.03) × N × Cost_failure_per_incident
                    = 0.12 × N × C_f

ROI = (0.12 × N × C_f - Cost_eval) / Cost_eval
    = 0.12 × N × C_f / Cost_eval - 1
```

손익분기점 (ROI = 0):
```
Cost_eval = 0.12 × N × C_f
→ 1건당 평가 비용 상한 = 0.12 × C_f
```

실패 1건 비용이 $1,000이라면, 건당 평가 비용이 **$120 이하**이면 항상 수익성이 있다.

---

### L.6.2 에이전트 유형별 ROI 계산 예시

#### 시나리오 A: QA 챗봇 (고객 서비스)

| 항목 | 값 |
|---|---|
| 월간 쿼리 수 | 50,000건 |
| 실패 1건 비용 (잘못된 정보 제공) | $50 (CS 대응 + 재처리) |
| 평가 없을 때 실패율 | 15% → 월 7,500건 실패 |
| 스탠다드 플랜 후 실패율 | 8% → 월 4,000건 실패 |
| 월 평가 비용 (Haiku 20% × 50K) | $7.50 |
| 절감 실패 건수 | 3,500건/월 |
| 절감 비용 | 3,500 × $50 = **$175,000/월** |
| **ROI** | **(175,000 - 7.50) / 7.50 ≈ 23,332배** |

#### 시나리오 B: RAG 법률 문서 분석

| 항목 | 값 |
|---|---|
| 월간 분석 건수 | 5,000건 |
| 실패 1건 비용 (오류 법률 조언) | $2,000 (법적 위험 + 재작업) |
| 평가 없을 때 실패율 | 12% → 월 600건 실패 |
| 풀 커버리지 플랜 후 실패율 | 2% → 월 100건 실패 |
| 월 평가 비용 (Sonnet 50% × 5K) | $7.50 |
| 절감 실패 건수 | 500건/월 |
| 절감 비용 | 500 × $2,000 = **$1,000,000/월** |
| **ROI** | **(1,000,000 - 7.50) / 7.50 ≈ 133,332배** |

#### 시나리오 C: 도구 자동화 에이전트 (데이터 파이프라인)

| 항목 | 값 |
|---|---|
| 월간 실행 수 | 10,000건 |
| 실패 1건 비용 (파이프라인 재실행 + 검토) | $200 |
| 평가 없을 때 실패율 | 20% → 월 2,000건 실패 |
| 스타터 플랜 후 실패율 | 12% → 월 1,200건 실패 |
| 월 평가 비용 (Native Tracker만) | $0 (CPU 비용 $2 환산) |
| 절감 실패 건수 | 800건/월 |
| 절감 비용 | 800 × $200 = **$160,000/월** |
| **ROI** | **(160,000 - 2) / 2 ≈ 79,999배** |

> **공통 패턴**: 모든 시나리오에서 ROI는 수천 배 이상이다. 이는 AI 에이전트 실패가 평가 비용보다 구조적으로 훨씬 비싸기 때문이다. 유일한 반례는 에이전트 실패 비용이 극히 낮은 경우(무료 공개 서비스, 순수 실험 환경)다.

---

### L.6.3 경영진 설득 1페이지 요약

아래는 비기술 이해관계자에게 평가 투자를 정당화하는 템플릿이다.

---

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI 에이전트 품질 평가 시스템 투자 제안
                                     [날짜] / [작성자]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 현황 (측정된 사실)

  현재 AI 에이전트 시스템의 프로덕션 실패율: [X]%
  월간 실패 처리 비용 (수동 대응 + 재처리): [₩Y]
  평가 체계 부재로 인한 발견 지연 평균 시간: [Z]시간

■ 제안 (Agent-Evaluator SDK 도입)

  투자 규모:
    - 엔지니어 초기 설정: 8시간 (1회성)
    - 월간 LLMJudge API 비용: [월 ₩A] (스탠다드 플랜)
    - 인프라 오버헤드: CPU +[B]% (무시 가능 수준)

  기대 효과:
    - 프로덕션 실패율 [X]% → [X×0.2]% 목표 (업계 평균 80% 감소)
    - 실패 발견 시간: [Z]시간 → 실시간 알림 (AlertEngine)
    - 회귀 감지 자동화: 매 배포마다 골든셋 100건 자동 검증

■ ROI 계산

  월간 실패 비용 절감: ₩[Y × 0.80]
  월간 평가 비용: ₩[A + B_cost]
  순 월간 이익: ₩[Y × 0.80 - A - B_cost]
  투자 회수 기간: [초기 설정 시간 × 엔지니어 시급 / 월간 이익] 개월

■ 리스크

  - 도입 안 할 경우: 현재 실패율 [X]% 지속, 월 ₩[Y] 손실 계속
  - 도입 후 리스크: 거의 없음 (오픈소스 SDK, vendor lock-in 없음)

■ 다음 단계

  1. 스타터 플랜 1주 POC (비용 $0, 엔지니어 4시간)
  2. 1주 후 커버리지 리포트 검토
  3. 스탠다드 플랜 전환 결정

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 요약: 예산별 권장 구성 한눈에 보기

| 예산 | 플랜 | 핵심 Tracker | LLMJudge | 예상 실패 탐지율 | 적합 환경 |
|---|---|---|---|---|---|
| $0 | 스타터 | TCR + Accuracy + Latency + Security (4–6개) | 없음 | ~65% | 내부 도구, 개발 초기 |
| $10–50/월 | 스탠다드 | 스타터 + Hallucination + Quality (6–8개) | Haiku 10–30% | ~82% | B2B SaaS, 프로덕션 기본 |
| $100+/월 | 풀 커버리지 | 전체 25개 Native | Sonnet 50–100% | ~95% | 의료·금융·법률 고위험 |

파레토 법칙은 AI 에이전트 평가에도 적용된다. 전체 Tracker의 20–25%(4–6개)가 전체 실패의 80%를 잡는다. 예산이 부족하다면 먼저 에이전트 유형에 맞는 파레토 최적 Tracker 3개를 선택하고, 예산이 생길 때마다 LLMJudge 샘플링을 조금씩 추가하는 방식으로 점진적으로 확장하는 것이 가장 합리적인 전략이다.

---

*다음 부록: Appendix M. 프로덕션 운영 체크리스트 — 배포 전 최종 점검 항목*
