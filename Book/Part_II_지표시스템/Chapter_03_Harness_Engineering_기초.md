# Chapter 3. Harness Engineering 기초

이 챕터에서는 **Harness Engineering**의 개념과 3요소 아키텍처를 이해한다.
이후 Chapter 4~10에서 Group A-G를 각각 깊이 탐구하기 위한 공통 기반이 된다.

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 각 Tracker와 Config의 입력·출력·임계값 기본값 한눈에 조회
> - **[Appendix G — AI 품질 평가 이론적 기초](../Appendix/G_AI평가_이론적기초.md)**: Harness Engineering 설계 철학의 이론적 배경
> - **[Appendix A §Part 2 — 33개 Harness Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 파라미터 상세 레퍼런스
> - **[Evaluator_Examples/08_harness_eval.py](../../Evaluator_Examples/08_harness_eval.py)**: 이 챕터 실전 예제

---

## 3.1 Harness Engineering이란 무엇인가

### 3.1.1 "버그 없음" vs "배포 가능"

기존 소프트웨어 테스팅이 던지는 질문은 하나다. **"버그가 없는가?"**

AI 에이전트에게 그 질문은 불완전하다. 에이전트는 결정론적으로 동작하지 않는다. 같은 질문에 매번 다른 경로로 답에 도달한다. "버그 없음"을 보장하는 `assert` 테스트 수백 개가 통과해도, 프로덕션에서 에이전트가 무단으로 도구를 호출하거나, 환각으로 틀린 정보를 자신감 있게 전달하거나, 비용 계약을 초과하는 일이 일어날 수 있다.

**Harness Engineering은 다른 질문을 던진다.** 

> "이 에이전트는 *지금 이 조건*에서 배포해도 되는가?"

그리고 그 질문의 답을 코드로 선언한다.

```python
# 기존 방식 — "버그가 없는지" 확인
def test_agent_response():
    result = agent("한국의 수도는?")
    assert "서울" in result  # 결정론적 assert

# Harness Engineering — "배포 가능한지" 판정
from agent_evaluator import QuickEval
from agent_evaluator import SLAConfig, InstructionConfig

eval = QuickEval("results/")

@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=2000, fail_on_violation=True),      # SLA 선언
    instructions=InstructionConfig(expected_language="ko"),   # 언어 기준 선언
)
def agent(question, ground_truth=""):
    return llm.invoke(question)

# 배포 기준이 위반되면 자동으로 fail 처리
eval.gate(tcr=85, accuracy=70)  # → 기준 미달 시 sys.exit(1)
```

핵심 차이는 **"기준의 위치"**다. `assert`는 테스트 파일 안에 있다. Harness Config는 에이전트 코드 바로 옆, `@agent_eval` 데코레이터 안에 있다. 에이전트가 자신의 배포 기준을 소유한다.

### 3.1.2 세 가지 배포 실패 유형

Harness Engineering이 방지하려는 실패는 세 가지 유형이다.

**유형 1 — 측정 없는 배포 (blind deployment)**  
에이전트를 실행하고, "응답이 나오네요"라고 확인한 뒤 배포한다. 정확도가 얼마인지, 응답 시간이 SLA 내에 있는지, 환각이 발생하는지 알 수 없다. 프로덕션 장애가 발생하면 왜 그런지 추적할 수단이 없다.

**유형 2 — 기준 없는 측정 (measurement without criteria)**  
`accuracy=0.85`라는 숫자는 있다. 하지만 이것이 배포 가능한 수준인지 팀원마다 판단이 다르다. 같은 숫자를 보고 "충분하다"와 "부족하다"가 충돌한다. 기준이 문서나 관행에 있으면 이 문제는 반복된다.

**유형 3 — 배포 후 무감지 (silent drift)**  
배포 당시에는 품질 기준을 통과했다. 하지만 LLM 모델이 업데이트되거나, 프롬프트가 조금 바뀌거나, 입력 데이터의 분포가 달라지면서 성능이 서서히 저하된다. 아무도 감지하지 못한 채 수주가 지난다.

Harness Engineering의 세 구성 요소(Tracker, Config, Gate)는 이 세 가지 유형을 각각 해결한다.

---

## 3.2 3요소: Tracker × Config × Gate

Harness Engineering은 세 개의 구성 요소로 이루어진다. 각각 독립적으로 사용할 수도 있지만, 셋이 결합될 때 완전한 배포 판정이 이루어진다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Harness Engineering                           │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   Tracker   │ →  │   Config    │ →  │        Gate         │ │
│  │ (관찰/측정)  │    │ (기준 선언)  │    │     (배포 판정)      │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│   "무슨 일이        "어떤 수치면         "지금 배포해도         │
│    일어났나?"        배포 가능한가?"       되는가?"              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2.1 Tracker — 관찰하는 자

Tracker는 에이전트 실행 중 무슨 일이 일어나는지 측정하는 관찰자(Observer)다. 판단하지 않는다. 오직 측정만 한다.

`PerformanceMonitor`에 `record_task()`를 호출할 때마다 내부의 트래커들이 자동으로 동작한다.

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor("results/")

result = create_taskresult(
    task_id="t001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",
)

monitor.record_task(result)
# ↑ 이 순간 내부에서 자동으로 동작하는 트래커들:
#   TaskCompletionTracker → completion_score 기록
#   AccuracyEvaluator     → accuracy_score 계산
#   ResponseQualityEvaluator → quality 5차원 평가
#   LatencyTracker        → execution_time 기록
#   TokenEconomyTracker   → tokens_used 기록
```

Agent-Evaluator의 Tracker는 25개이며, Group A-G에 분산되어 있다. 보안 Tracker 5종(Group E)은 `enable_security_metrics=True`로 활성화하는 opt-in이며, 25개 안에 포함된다.

### 3.2.2 Config — 기준을 선언하는 자

Config는 "어떤 상태가 합격인가"를 선언하는 기준서(Specification)다. 측정하지 않는다. 오직 기준을 선언한다.

Config 데이터클래스는 33개이며, `@agent_eval` 데코레이터의 파라미터로 주입한다.

```python
# 출처: Evaluator_Examples/08_harness_eval.py, 섹션 1 — Harness 3-Element: Tracker·Config·Gate
from agent_evaluator import (
    SLAConfig,              # Group D: 성능계약
    InstructionConfig,      # Group A: 목표달성
    ReproducibilityConfig,  # Group C: 신뢰성
    ThreatSeverityConfig,   # Group E: 보안경계
)
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    task_type="qa",
    # Group A — 목표달성 기준
    instructions=InstructionConfig(
        expected_language="ko",           # 한국어 응답 필수
        max_words=200,                    # 최대 200단어
        fail_on_violation=True,           # 위반 시 fail 처리
    ),
    # Group C — 신뢰성 기준
    reproducibility=ReproducibilityConfig(
        runs=3,                           # 동일 입력 3회 실행
        reproducibility_threshold=0.85,   # 재현성 85% 이상
    ),
    # Group D — 성능계약 기준
    sla=SLAConfig(
        p95_ms=2000,                      # P95 응답 2초 이내
        max_cost_per_task=0.005,          # 태스크당 최대 $0.005
    ),
    # Group E — 보안경계 기준
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,            # 치명적 위협 탐지 시 fail
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

`fail_on_violation=True` 플래그가 핵심이다. 이 플래그가 활성화된 Config 조건을 위반하면 해당 `TaskResult.success`가 `False`로 강제 처리된다.

### 3.2.3 Gate — 판정하는 자

Gate는 Tracker가 측정한 데이터와 Config가 선언한 기준을 대조해 최종 배포 판정을 내리는 심판(Judge)이다.

가장 간단한 Gate는 `eval.gate()`다.

```python
eval = QuickEval("results/")

# ... 평가 실행 ...

eval.gate(tcr=85, accuracy=70)
# tcr < 85 또는 accuracy < 70 이면 sys.exit(1) → CI/CD 파이프라인 차단
```

`HarnessEvaluationGate`는 7개 Group을 한 번에 체크하는 종합 Gate다. (§3.5 참조)

---

## 3.3 58개 지표 전체 지도 — Group A-G 매핑

Tracker 25개와 Config 33개를 7개 Group으로 분류한다. (보안 Tracker 5종은 25개 안에 포함, opt-in 활성화 필요)

### Group A — 목표달성 (Goal Achievement)

**핵심 질문**: 에이전트가 사용자의 지시를 제대로 완수했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `TaskCompletionTracker` | Task Completion Rate (TCR) — 완료 비율 |
| Tracker | `AccuracyEvaluator` | 정확도 — Token F1 + Jaccard + LCS + Levenshtein 4중 가중 |
| Tracker | `ResponseQualityEvaluator` | 응답 품질 — relevance(×0.25) · completeness(×0.25) · accuracy(×0.20) · clarity(×0.15) · usefulness(×0.15) 가중 평균 |
| Config | `InstructionConfig` | 응답 형식·길이·언어 준수 기준 |
| Config | `GoalAlignmentConfig` | 목표-행동 정렬 기준 |
| Config | `PlanConfig` | 계획 실행 완성도 기준 |
| Config | `ContextRetentionConfig` | 핵심 컨텍스트 보존 기준 |
| Config | `SubtaskConfig` | 서브태스크 완료율 기준 |
| Config | `KnowledgeRetentionConfig` | 대화 중 사실 보존 기준 |

### Group B — 행동무결성 (Behavioral Integrity)

**핵심 질문**: 에이전트가 의도하지 않은 행동 없이 동작했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `ToolCallAnalyzer` | 도구 호출 패턴 분석 |
| Tracker | `WorkflowExecutionTracker` | 워크플로우 실행 분기 추적 |
| Config | `LoopDetectionConfig` | 도구 호출 루프·반복 패턴 감지 기준 |
| Config | `ScopeConfig` | 허용/금지 도구 범위 선언 |
| Config | `ToolParameterSafetyConfig` | 도구 파라미터 위험 패턴 기준 |
| Config | `ContextWindowConfig` | 컨텍스트 윈도우 포화도 기준 |
| Config | `StateConsistencyConfig` | 실행 전후 상태 일관성 기준 (v0.8.2에서 Group E→B 이동) |
| Config | `DeadlockConfig` | 교착·기아·라이브락 탐지 기준 (v0.8.2에서 Group F→B 이동) |

### Group C — 신뢰성 (Reliability)

**핵심 질문**: 같은 입력에 일관되고 재현 가능한 응답을 하는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `HallucinationDetector` | 환각 탐지 — 사실 일관성 점수 (opt-in) |
| Tracker | `RetryCorrectionTracker` | 재시도·자가수정 행동 추적 |
| Config | `ReproducibilityConfig` | 동일 입력 반복 실행 재현성 기준 |
| Config | `FaultToleranceConfig` | 장애 내성·폴백 기준 |
| Config | `GracefulDegradationConfig` | 우아한 성능 저하 기준 |
| Config | `RetryConsistencyConfig` | 재시도 일관성 기준 |
| Config | `IdempotencyConfig` | 멱등성(반복 실행 부작용 없음) 기준 |

### Group D — 성능계약 (Performance Contract)

**핵심 질문**: 약속한 SLA와 비용 계약을 지켰는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `LatencyTracker` | 응답 시간 — P50·P95·P99·TTFT |
| Tracker | `TokenEconomyTracker` | 토큰 사용량 + 비용 추정 |
| Config | `SLAConfig` | P95·P99·TTFT·비용 SLA 선언 |
| Config | `EfficiencyConfig` | 비용 대비 완료율(ROI) 기준 |
| Config | `ResourceBudgetConfig` | 토큰·비용·실행시간 예산 상한 |
| Config | `TTFTVariabilityConfig` | TTFT 변동성 기준 |
| Config | `CostPredictabilityConfig` | 비용 예측 가능성(CV) 기준 |

### Group E — 보안경계 (Security Boundary)

**핵심 질문**: 외부 공격과 데이터 유출을 차단했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `InputSanitizationTracker` | SQL·Command·Path·XSS·Prompt Injection 탐지 |
| Tracker | `OutputLeakageDetector` | 민감 데이터 출력 유출 탐지 |
| Tracker | `ToolAuthorizationTracker` | 미허가 도구 사용 탐지 |
| Tracker | `PrivilegeEscalationDetector` | 권한 상승 패턴 탐지 |
| Tracker | `ToolChainAttackDetector` | 도구 연쇄 공격 패턴 탐지 |
| Config | `ThreatSeverityConfig` | CVSS 기반 위협 심각도 기준 |
| Config | `ComplianceConfig` | PII·컴플라이언스 위반 기준 |
| Config | `ThreatResponseConfig` | 위협 탐지 시 응답 행동 기준 |

> ⚠️ **보안 트래커 활성화**: 보안 트래커 4종은 `enable_security_metrics=True`로 명시적으로 활성화해야 한다. 성능에 영향을 주므로 기본값은 `False`다.

### Group F — 다중에이전트 협업 (Multi-Agent Coordination)

**핵심 질문**: 여러 에이전트가 교착 없이 협력했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `AgentCoordinationTracker` | 에이전트 간 상호작용 추적 |
| Tracker | `ToolSelectionTracker` | 도구 선택 F1 정확도 |
| Config | `ConsensusConfig` | 다중 에이전트 합의 품질 기준 |
| Config | `PropagationConfig` | 에이전트 간 정보 전파 충실도 기준 |
| Config | `AgentRoleConfig` | 에이전트 역할 준수 기준 |
| Config | `ConflictResolutionConfig` | 에이전트 간 충돌 해결 품질 기준 |

### Group G — 운영관측성 (Operational Observability)

**핵심 질문**: 실패 원인을 즉시 추적하고 설명할 수 있는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Config | `ObservabilityConfig` | 스팬 속성 완성도·감사 이벤트 SLO 기준 |
| Config | `ExplainabilityConfig` | 응답 설명 가능성·추론 근거 기준 |
| Config | `ErrorDiagnosisConfig` | 실패 응답의 오류 진단 품질 기준 |
| Config | `LatencyAttributionConfig` | 도구·모델·네트워크 지연 귀속 기준 |

> **Group G와 LLM Judge**: Group G는 관측성과 설명 가능성을 다룬다. LLMJudge (`enable_llm_judge=True`)는 Group G와 자연스럽게 연결된다. LLM이 응답의 추론 근거와 설명 품질을 자동으로 채점하기 때문이다.

### 지표 수 요약

| Group | Tracker | Config | 합계 |
|-------|---------|--------|------|
| A 목표달성 | 3 | 6 | 9 |
| B 행동무결성 | 2 | 6 | 8 |
| C 신뢰성 | 2 | 5 | 7 |
| D 성능계약 | 2 | 5 | 7 |
| E 보안경계 | 5 | 3 | 8 |
| F 다중에이전트 | 2 | 4 | 6 |
| G 운영관측성 | 0 | 4 | 4 |
| **합계** | **16** | **33** | **49** |

> ℹ️ **지표 수 안내**: Harness Gate(A–G)에 직접 매핑되는 Native Tracker는 16개다. `ConversationSession`, `ImplicitFeedbackTracker`, `AnomalyDetector`, `CostTracker`, `StreamingEvaluator` 등 운영 지원 트래커 9개를 합산하면 SDK 전체 Native Tracker는 25개다. Harness Gate 판정 대상은 이 표의 49개(16 Tracker + 33 Config)이며, 운영 지원 트래커를 포함한 전체는 **25 + 33 = 58개**다. 전체 목록은 [Appendix A](../Appendix/A_58개지표_레퍼런스.md)에서 확인한다.

---

## 3.4 Config-as-Code 패턴

Config-as-Code는 에이전트의 배포 기준을 소스 코드로 선언하는 패턴이다. 이 패턴이 "기준 없는 측정" 문제를 해결한다.

### 3.4.1 왜 코드로 선언하는가

배포 기준을 코드 밖에 두면 세 가지 문제가 생긴다.

1. **버전 관리 불가**: 기준이 언제 바뀌었는지 추적할 수 없다
2. **팀원 간 불일치**: 같은 숫자를 보고 다른 판단을 내린다
3. **CI/CD 통합 불가**: 코드 변경마다 기준을 자동으로 검증할 수 없다

Config-as-Code는 이 세 가지를 모두 해결한다. Config 객체는 코드베이스의 일부이므로 `git`으로 버전 관리되고, PR 리뷰 시 기준 변경이 명시적으로 보이며, CI/CD 파이프라인에서 자동으로 실행된다.

### 3.4.2 에이전트 유형별 최소 Config 세트

| 에이전트 유형 | 필수 Config | 선택 Config |
|-------------|-------------|-------------|
| 단순 QA 봇 | `InstructionConfig`, `SLAConfig` | `ReproducibilityConfig` |
| RAG 에이전트 | `InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig` | `ContextRetentionConfig`, `ComplianceConfig` |
| 코드 생성 에이전트 | `ScopeConfig`, `SLAConfig`, `ComplianceConfig` | `SubtaskConfig`, `ObservabilityConfig` |
| 멀티에이전트 시스템 | `DeadlockConfig`, `AgentRoleConfig`, `SLAConfig` | `ConsensusConfig`, `PropagationConfig` |
| 보안 중심 에이전트 | `ThreatSeverityConfig`, `ComplianceConfig`, `ThreatResponseConfig` | `StateConsistencyConfig`, `ScopeConfig` |

### 3.4.3 단계적 도입 패턴

하루 만에 모든 Config를 도입할 필요는 없다. 다음 순서로 점진적으로 적용한다.

**Day 1 — 최소 시작 (측정만)**

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""):
    return llm.invoke(question)

# 이 단계에서는 Config 없이 측정만 함
# 며칠간 수집된 데이터를 보며 실제 지표 분포를 파악한다
```

**Day 7 — 첫 Config 도입 (SLA + 기본 기준)**

```python
from agent_evaluator import SLAConfig, InstructionConfig

@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000),           # 측정 데이터 P95 기반 설정
    instructions=InstructionConfig(
        expected_language="ko",
        max_words=300,
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

**Day 30 — 배포 판정 자동화 (fail_on_violation + gate)**

```python
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=2000, fail_on_violation=True),  # ← fail 활성화
    instructions=InstructionConfig(
        expected_language="ko",
        fail_on_violation=True,
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)

# CI/CD에서 자동 배포 차단
eval.gate(tcr=85, accuracy=70)
```

### 3.4.4 Config 조합 — 프로덕션 QA 에이전트 예시

```python
# 출처: Evaluator_Examples/08_harness_eval.py
from agent_evaluator import PerformanceMonitor
from agent_evaluator import (
    InstructionConfig,
    ReproducibilityConfig,
    SLAConfig,
    ResourceBudgetConfig,
    ThreatSeverityConfig,
    ObservabilityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C
    enable_security_metrics=True,         # Group E
)

@agent_eval(
    monitor,
    task_type="qa",
    # Group A — 목표달성
    instructions=InstructionConfig(
        expected_language="ko",
        max_words=500,
        forbidden_phrases=["모르겠습니다", "확인이 필요합니다"],
        fail_on_violation=True,
    ),
    # Group C — 신뢰성
    reproducibility=ReproducibilityConfig(
        runs=3,
        reproducibility_threshold=0.85,
        fail_on_low_reproducibility=False,  # 경고만, fail 없음
    ),
    # Group D — 성능계약
    sla=SLAConfig(
        p95_ms=2000,
        max_cost_per_task=0.005,
        fail_threshold=5,
    ),
    resource_budget=ResourceBudgetConfig(
        max_tokens=2000,
        warn_at_pct=0.8,
    ),
    # Group E — 보안경계
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,
        fail_score=7.0,
    ),
    # Group G — 운영관측성
    observability=ObservabilityConfig(
        min_coverage=0.99,
    ),
)
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 3.5 개발자 ↔ QA 관리자 협업 브리지

Harness Engineering에는 두 종류의 사용자가 있다. **개발자**는 Tracker와 Config로 평가를 구현하고, **QA 관리자**는 Gate A–G 판정 결과로 배포를 승인하거나 차단한다. 두 역할이 어떻게 연결되는지 이해하면 팀 전체가 같은 언어로 소통할 수 있다.

### 3.5.1 두 역할이 보는 Harness

```
┌──────────────────────────────────────────────────────────────────┐
│  개발자 관점 (구현)            QA 관리자 관점 (판정)               │
│                                                                  │
│  @agent_eval(                  대시보드 / Gate 리포트              │
│    monitor,                                                      │
│    sla=SLAConfig(p95_ms=2000)  → Gate D 성능계약: PASS ✅         │
│    scope=ScopeConfig(...)      → Gate B 행동무결성: WARN ⚠️        │
│    threat_severity=...         → Gate E 보안경계: PASS ✅         │
│  )                                                               │
│  def my_agent(...): ...                                          │
│                                                                  │
│  ← 코드로 선언 →               ← 판정 결과로 소통 →               │
└──────────────────────────────────────────────────────────────────┘
```

### 3.5.2 협업 워크플로우 — 5단계

실제 팀에서 Harness Engineering이 어떻게 흐르는지 한 사이클을 따라가 본다.

**Step 1 — 개발자: Tracker 활성화 (측정 시작)**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C Tracker
    enable_security_metrics=True,         # Group E Tracker
)
```

Tracker는 코드를 변경하지 않아도 자동으로 데이터를 수집한다. 이 시점에서 QA 관리자는 아직 개입하지 않는다.

**Step 2 — 개발자: 초기 평가 실행 (기준 없는 측정)**

```python
@agent_eval(monitor, task_type="qa")
def my_agent(question, ground_truth=""):
    return llm.invoke(question)

# 10개 샘플 실행
for q, gt in test_cases:
    my_agent(q, ground_truth=gt)

report = monitor.generate_report()
print(f"응답시간 P95: {report.to_dict()['latency_data']['p95']:.2f}초")
print(f"TCR: {report.task_completion_rate:.1f}%")
```

이 결과를 QA 관리자에게 공유한다.

**Step 3 — QA 관리자: Config 기준 결정 (기준 선언)**

측정 데이터를 바탕으로 QA 관리자가 배포 기준을 결정한다.

```
측정 결과:
  - 응답시간 P95: 1.8초  →  SLAConfig(p95_ms=2500) 설정
  - TCR: 91%            →  eval.gate(tcr=85) 설정
  - 보안 위협 탐지: 0건  →  ThreatSeverityConfig(fail_on_critical=True) 설정

QA 관리자 결정 (문서 또는 구두):
  "P95 2.5초 이내, TCR 85% 이상, 보안 위협 0건을 배포 기준으로 한다"
```

**Step 4 — 개발자: Config 코드 반영 (기준을 코드로)**

```python
@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(
        p95_ms=2500,           # QA 관리자 결정 반영
        fail_on_violation=True,
    ),
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,  # QA 관리자 결정 반영
    ),
)
def my_agent(question, ground_truth=""):
    return llm.invoke(question)

eval.gate(tcr=85, accuracy=70)  # QA 관리자 결정 반영
```

이제 기준이 소스 코드 안에 존재한다. 팀 누구나 `git log`로 기준의 변경 이력을 볼 수 있다.

**Step 5 — CI/CD: 자동 Gate 판정 (반복 검증)**

```yaml
# .github/workflows/eval.yml
- name: Harness Gate check
  run: agent-eval gate results/latest.json --tcr 85 --accuracy 70
```

PR마다 Gate가 자동으로 동작한다. 기준을 위반하면 배포가 차단된다. QA 관리자는 대시보드에서 Group별 점수를 확인하고 추가 기준을 요청할 수 있다.

### 3.5.3 Gate A–G와 Tracker·Config 매핑 요약

| Gate | 품질 질문 | 관련 Tracker | 관련 Config |
|------|----------|-------------|------------|
| **A** 목표달성 | 지시를 완수했는가? | TCR, Accuracy, ResponseQuality | InstructionConfig, GoalAlignmentConfig, PlanConfig |
| **B** 행동무결성 | 의도치 않은 행동이 없었는가? | ToolCallAnalyzer, WorkflowExecution | LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig, ContextWindowConfig, StateConsistencyConfig, DeadlockConfig |
| **C** 신뢰성 | 일관되고 재현 가능한가? | HallucinationDetector, RetryCorrection | ReproducibilityConfig, FaultToleranceConfig, IdempotencyConfig |
| **D** 성능계약 | SLA·비용을 지켰는가? | LatencyTracker, TokenEconomy | SLAConfig, ResourceBudgetConfig, EfficiencyConfig |
| **E** 보안경계 | 공격·유출을 차단했는가? | InputSanitization, OutputLeakage, ToolAuth, PrivilegeEscalation, ToolChainAttack | ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig |
| **F** 다중에이전트 | 교착 없이 협력했는가? | AgentCoordination, ToolSelection | ConsensusConfig, AgentRoleConfig, ConflictResolutionConfig |
| **G** 운영관측성 | 실패 원인을 즉시 추적할 수 있는가? | LLMJudge (7차원) | ObservabilityConfig, ExplainabilityConfig, ErrorDiagnosisConfig |

> 📖 **각 Group의 상세 내용**: Chapter 4(A) ~ Chapter 10(G)에서 Tracker·Config를 깊이 다룬다.  
> 📖 **Config 파라미터 전체 목록**: [Appendix A §Part 2](../Appendix/A_58개지표_레퍼런스.md)

---

## 3.6 HarnessEvaluationGate — 종합 배포 판정 아키텍처

### 3.6.1 Gate의 역할

`eval.gate()`는 TCR·정확도 두 개 지표만 체크하는 단순 Gate다. 에이전트가 성숙해지면 7개 Group 전체를 종합적으로 체크하는 Gate가 필요하다. 그것이 `HarnessEvaluationGate`다.

```python
from agent_evaluator import HarnessEvaluationGate

# 평가 완료 후 Gate 실행
report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

print(result)
# {
#   "passed": False,
#   "groups": {
#     "A": {"passed": True,  "score": 0.91},
#     "B": {"passed": True,  "score": 0.97},
#     "C": {"passed": False, "score": 0.72, "violations": ["reproducibility_below_threshold"]},
#     "D": {"passed": True,  "score": 0.88},
#     "E": {"passed": True,  "score": 1.00},
#     "F": {"passed": True,  "score": 0.94},
#     "G": {"passed": True,  "score": 0.89},
#   },
#   "overall_score": 0.90,
#   "blocking_violations": ["C.reproducibility_below_threshold"],
# }
```

### 3.6.2 CI/CD 파이프라인 통합

```yaml
# .github/workflows/eval.yml
name: Harness Gate

on: [pull_request]

jobs:
  harness-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run evaluation
        run: python -m pytest tests/eval/ -v
      - name: Harness Gate check
        run: |
          agent-eval gate results/latest.json \
            --tcr 85 \
            --accuracy 70 \
            --fail-on-group-violation C,E  # Group C·E 위반 시 배포 차단
```

### 3.6.3 Group별 가중치 설정

에이전트 유형에 따라 Group별 중요도가 다르다.

```python
gate = HarnessEvaluationGate(
    report,
    group_weights={
        "A": 0.25,   # 목표달성 — 가장 중요
        "B": 0.10,
        "C": 0.15,   # 신뢰성 — 의료/금융 에이전트는 더 높게
        "D": 0.15,
        "E": 0.25,   # 보안경계 — 외부 노출 에이전트는 더 높게
        "F": 0.05,
        "G": 0.05,
    },
    required_groups=["A", "E"],  # A·E는 pass 필수
)
```

---

## 3.7 AI Native 특성과 Harness Engineering의 연결

기존 소프트웨어 테스팅은 결정론적 시스템을 위해 설계됐다. AI 에이전트는 5가지 AI Native 특성을 가지며, Harness Engineering은 이 각각에 직접 대응한다.

### 특성 1 — 확률론적 품질 (Probabilistic Quality)

에이전트의 품질은 단일 점수가 아니라 **분포**다. 같은 `accuracy=0.85`라도 분산이 작으면 안정적, 크면 예측 불가능하다.

Harness 대응: `ReproducibilityConfig`는 동일 입력을 N회 실행해 분포를 측정한다. `SLAConfig.p95_ms`는 단일 측정이 아닌 퍼센타일 기반 임계값이다.

```python
# 단일 테스트 — AI Native에 부적합
assert accuracy > 0.8  # 한 번의 실행 결과

# Harness — 분포 기반 기준
reproducibility=ReproducibilityConfig(
    runs=5,                          # 5회 실행
    reproducibility_threshold=0.85,  # 5회 중 85% 일관성
)
sla=SLAConfig(p95_ms=2000)          # P95 기반 SLA
```

### 특성 2 — AI-by-AI 평가 (AI-Evaluated AI)

사람이 수백 개의 응답을 읽으며 품질을 채점하는 것은 확장되지 않는다. LLM Judge는 선택 사항이 아니라 Harness Engineering의 핵심 도구다.

Harness 대응: `ExplainabilityConfig`와 LLMJudge의 결합.

```python
from agent_evaluator import ExplainabilityConfig
from agent_evaluator.decorators import LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        criteria=["factual_accuracy", "reasoning_quality"],
        sample_rate=0.1,              # 10%만 채점 (비용 절감)
    ),
    explainability=ExplainabilityConfig(
        require_reasoning=True,       # 추론 근거 필수
        require_citations=True,       # 출처 표시 필수
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

### 특성 3 — 드리프트 인식 (Drift Awareness)

배포 당시 통과한 기준이 시간이 지나면서 의미를 잃는다. 4가지 변경 소스(코드·모델·프롬프트·데이터)에서 드리프트가 발생한다.

Harness 대응: `agent-eval trend`로 순차 실행 결과의 추세를 모니터링한다.

```bash
# 최근 20개 결과 파일의 TCR·정확도 추세 분석
agent-eval trend results/ --window 20

# 회귀 감지 시 CI/CD 실패 처리
agent-eval trend results/ --fail-on-regression

# 변경 소스 × Harness Group 영향 매트릭스
# 코드 변경  → Group B(행동무결성), Group C(신뢰성) 재검증
# 모델 교체  → Group A(목표달성), Group G(관측성) 재검증
# 프롬프트   → Group A, Group C 재검증
# 데이터 변화 → Group A, Group E(보안경계) 재검증
```

### 특성 4 — 출현 행동 대응 (Emergent Behavior Response)

에이전트는 설계자가 예측하지 못한 행동을 할 수 있다. 탐지 패턴 목록에 없는 행동이다.

Harness 대응: `AnomalyDetector`와 `ScopeConfig`의 결합. `ScopeConfig`는 "허용된 도구 목록"으로 범위를 선언하고, `AnomalyDetector`는 통계적 이상치를 자동 감지한다.

```python
from agent_evaluator import AnomalyDetector
from agent_evaluator import ScopeConfig

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,    # 이상 탐지 활성화
)

@agent_eval(
    monitor,
    task_type="tool_use",
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "translate"],
        forbidden_tools=["execute_code", "delete_file"],
        fail_on_violation=True,       # 범위 외 도구 사용 시 fail
    ),
)
def agent(question, ground_truth=""):
    return tool_agent.run(question)
```

### 특성 5 — 지속 평가 (Continuous Evaluation)

배포 전 평가만으로는 충분하지 않다. 배포 후에도 에이전트의 품질을 지속적으로 평가해야 한다.

Harness 대응: 배포 전 `HarnessEvaluationGate` + 배포 후 Phoenix OTEL 실시간 모니터링.

```
배포 전 Harness:                    배포 후 Harness:
  @agent_eval(Config 선언)    →       agent-eval monitor (Phoenix)
  HarnessEvaluationGate.evaluate()    agent-eval trend --fail-on-regression
  → 통과 시 배포 진행                  → 드리프트 감지 시 알림 + 재배포 차단
```

---

## 3.8 실습: 첫 Harness 배포 판정 (5분)

이 책의 모든 Harness 개념을 한 파일에서 경험한다.

```python
# 출처: Evaluator_Examples/08_harness_eval.py, 섹션 1
"""5분 안에 완성하는 첫 Harness 평가"""
from agent_evaluator import QuickEval
from agent_evaluator import SLAConfig, InstructionConfig

eval = QuickEval("results/")

# Step 1: Config 선언 (배포 기준을 코드로)
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000, fail_on_violation=False),    # 관찰 모드
    instructions=InstructionConfig(expected_language="ko"),
)
def simple_agent(question: str, ground_truth: str = "") -> str:
    # 실제 LLM 대신 규칙 기반 응답
    responses = {
        "한국의 수도": "서울입니다.",
        "파이썬 창시자": "귀도 반 로섬입니다.",
    }
    for key, val in responses.items():
        if key in question:
            return val
    return "모르겠습니다."

# Step 2: 평가 실행
test_cases = [
    ("한국의 수도는?", "서울"),
    ("파이썬 창시자는?", "귀도 반 로섬"),
    ("Java 창시자는?", "제임스 고슬링"),
]

for question, ground_truth in test_cases:
    simple_agent(question, ground_truth=ground_truth)

# Step 3: Harness Gate 판정
print("\n=== Harness Gate 결과 ===")
report = eval.monitor.generate_report()
d = report.to_dict()
print(f"TCR    : {d.get('tcr', 0) * 100:.1f}%")
print(f"정확도  : {d.get('accuracy', 0) * 100:.1f}%")

# Step 4: 배포 판정 (기준 미달 시 sys.exit(1))
eval.gate(tcr=60, accuracy=50)
print("\n✅ Harness Gate 통과 — 배포 가능")
```

이 코드를 실행하면 Harness Engineering의 전체 흐름을 경험할 수 있다.
- Config 선언 → 측정 → 보고서 → Gate 판정 → 배포 승인/차단

---

## 3.9 이 챕터의 핵심 요약

| 개념 | 한 줄 정의 |
|------|-----------|
| Harness Engineering | AI 에이전트의 배포 가능 여부를 코드로 판정하는 품질 공학 방법론 |
| Tracker | 런타임에 무슨 일이 일어났는지 측정하는 관찰자 (25개) |
| Config | 어떤 상태가 합격인지 코드로 선언하는 기준서 (33개) |
| Gate | Tracker 측정값과 Config 기준을 대조해 배포 판정을 내리는 심판 |
| fail_on_violation | Config 조건 위반 시 TaskResult.success를 False로 강제하는 플래그 |
| Group A-G | 58개 지표를 7개 품질 차원으로 분류하는 Harness 구조 |
| Config-as-Code | 배포 기준을 소스 코드로 선언하는 패턴 |

Chapter 4부터는 Group A(목표달성)를 시작으로 각 Group을 깊이 탐구한다.

> 🔗 **다음 챕터**: Chapter 4 — Group A: 목표달성 지표  
> 에이전트가 사용자 지시를 얼마나 충실하게 이행하는지 측정하는 3개 Tracker와 6개 Config를 완전히 이해한다.
