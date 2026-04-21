# Chapter 3. Harness Engineering 기초

이 챕터에서는 **Harness Engineering**의 개념과 3요소 아키텍처를 이해한다.
이후 Chapter 4~10에서 Group A-G를 각각 깊이 탐구하기 위한 공통 기반이 된다.

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 각 Tracker와 Config의 입력·출력·임계값 기본값 한눈에 조회
> - **[Appendix G — AI 품질 평가 이론적 기초](../Appendix/G_AI평가_이론적기초.md)**: Harness Engineering 설계 철학의 이론적 배경
> - **[Appendix A §Part 2 — 33개 Harness Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 파라미터 상세 레퍼런스
> - **[Evaluator_Examples/ch03_harness_basics.py](../../Evaluator_Examples/ch03_harness_basics.py)**: 이 챕터 실전 예제
> - **[Evaluator_Examples/ch04_group_a.py](../../Evaluator_Examples/ch04_group_a.py)**: Gate A~G FAIL 시나리오 — 배포 차단 케이스 17개
> - **[Evaluator_Examples/ch20_deployment.py](../../Evaluator_Examples/ch20_deployment.py)**: v1 레거시 → v2 개선 에이전트 Harness Gate 비교

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
    sla=SLAConfig(p95_ms=2000),                               # SLA 선언
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
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 1 — Harness 3-Element: Tracker·Config·Gate
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
| Config | `StateConsistencyConfig` | 실행 전후 상태 일관성 기준 (v0.8.2에서 Group F→B 이동) |
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

> ⚠️ **보안 트래커 활성화**: 보안 트래커 5종(`InputSanitizationTracker`, `OutputLeakageDetector`, `ToolAuthorizationTracker`, `PrivilegeEscalationDetector`, `ToolChainAttackDetector`)은 `enable_security_metrics=True`로 명시적으로 활성화해야 한다. 성능에 영향을 주므로 기본값은 `False`다.

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

- **목적**: Config 선언 없이 기본 지표(TCR·정확도·품질·지연)를 수집만 한다
- **`@eval.qa`**: `task_type="qa"` 단축 데코레이터로 QA 태스크를 자동 인식한다
- **다음 단계**: 며칠간 데이터를 모은 뒤 실제 P95·TCR 분포를 보고 Day 7 Config 임계값을 결정한다

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

- **`SLAConfig(p95_ms=3000)`**: Day 1 측정 데이터에서 확인한 실제 P95 응답 시간을 기준으로 SLA를 선언한다
- **`InstructionConfig`**: 한국어 응답 강제 + 300단어 상한으로 응답 품질 하한선을 코드로 선언한다
- **이 시점에서는 `fail_on_violation`이 없으므로** 위반 시 기록만 하고 실패 처리는 하지 않는다

**Day 30 — 배포 판정 자동화 (fail_on_violation + gate)**

```python
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=2000, fail_threshold=3),           # P95 응답 2초 이내, 3건 위반 시 fail
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

- **`fail_on_violation=True`**: 언어 기준 위반 시 해당 태스크의 `TaskResult.success`를 자동으로 `False`로 강제한다
- **`sla.fail_threshold=3`**: SLA 위반이 3건을 넘으면 Gate 점수를 낮춰 배포 차단에 반영한다
- **`eval.gate(tcr=85, accuracy=70)`**: TCR 85% 미만 또는 정확도 70% 미만이면 `sys.exit(1)`로 CI/CD 파이프라인을 차단한다

### 3.4.4 Config 조합 — 프로덕션 QA 에이전트 예시

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py
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

- **멀티 Config 조합**: 하나의 `@agent_eval`에 Group A·C·D·E·G를 동시 선언해 5개 Gate를 한 번에 평가한다
- **`enable_hallucination_detection=True`**: Group C의 `HallucinationDetector`를 활성화한다 (기본값 False, 성능 영향 있음)
- **`enable_security_metrics=True`**: Group E 보안 트래커 5종을 활성화한다 (기본값 False)
- **`forbidden_phrases`**: "모르겠습니다" 등 역량 부족 신호를 응답에서 탐지하면 `fail_on_violation=True`에 의해 즉시 fail 처리한다
- **`warn_at_pct=0.8`**: 토큰 예산의 80%를 소진하면 경고(fail 없음)를 발생시킨다

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
d = report.to_dict()
p95 = d.get("efficiency_metrics", {}).get("latency", {}).get("p95", 0.0)
tcr = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
print(f"응답시간 P95: {p95:.2f}초")
print(f"TCR: {tcr * 100:.1f}%")
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
    ),
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,  # QA 관리자 결정 반영
    ),
)
def my_agent(question, ground_truth=""):
    return llm.invoke(question)

eval.gate(tcr=85, accuracy=70)  # QA 관리자 결정 반영
```

- **기준의 코드화**: QA 관리자가 구두나 문서로 결정한 기준을 `@agent_eval` 파라미터로 옮긴다
- **버전 관리**: 이 코드가 Git에 커밋되므로 `git log`로 기준 변경 이력을 언제든 추적할 수 있다
- **팀 가시성**: PR 리뷰 시 Config 파라미터 변경이 diff에 명시적으로 드러나 합의 절차를 자연스럽게 강제한다

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
#     "A": {"passed": True,  "score": 0.91, "status": "pass"},
#     "B": {"passed": True,  "score": 0.97, "status": "pass"},
#     "C": {"passed": False, "score": 0.72, "status": "fail"},
#     "D": {"passed": True,  "score": 0.88, "status": "pass"},
#     "E": {"passed": True,  "score": 1.00, "status": "pass"},
#     "F": {"passed": True,  "score": 0.94, "status": "pass"},
#     "G": {"passed": True,  "score": 0.89, "status": "pass"},
#   },
#   "violations": [{"group": "C", "score": 0.72, "status": "fail"}],
#   "summary": {"total_groups": 7, "passed_groups": 6, "overall_score": 0.90},
# }

# CI/CD — 실패 시 sys.exit(1)
gate.enforce()
```

- **`HarnessEvaluationGate(report)`**: `monitor.generate_report()`가 반환한 `EvaluationReport`를 받아 Group A–G를 일괄 평가한다
- **`result["passed"]`**: 하나라도 `required_groups` 기준을 미달하면 `False`가 된다
- **`result["violations"]`**: 실패한 Group 목록과 점수를 반환해 어디서 차단됐는지 즉시 확인한다
- **`gate.enforce()`**: `passed=False`이면 `sys.exit(1)`을 호출해 CI/CD 파이프라인을 자동 차단한다

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

### 3.6.3 특정 Group만 검사

에이전트 유형에 따라 검사할 Group을 지정할 수 있다.
`HarnessEvaluationGate`는 `report`, `min_group_score`, `required_groups`, `fail_on_warn`을 지원한다. `group_weights`는 지원하지 않는다.

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 7 — HarnessEvaluationGate 활용
from agent_evaluator import HarnessEvaluationGate

# 목표달성(A)·보안경계(E)만 필수 통과 — 나머지는 경고만
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],  # A·E는 점수가 있으면 반드시 통과해야 함
    min_group_score=0.7,         # 각 그룹 최소 허용 점수 70%
    fail_on_warn=False,          # warn 상태는 실패로 처리하지 않음
)
result = gate.evaluate()
gate.enforce()   # 기준 미달 시 sys.exit(1)
```

- **`required_groups=["A", "E"]`**: 목표달성과 보안경계만 필수 통과로 지정하고 나머지 Group(B·C·D·F·G)은 경고만 발생시킨다
- **`min_group_score=0.7`**: 필수 Group의 점수가 0.7 미만이면 Gate 실패로 처리한다
- **`fail_on_warn=False`**: `warn` 상태는 실패로 간주하지 않아 점진적 기준 도입 단계에서 유용하다


### 3.6.4 ch18_cicd_gate.py — CI/CD 전용 최소 검증 스크립트

`ch03_harness_basics.py`는 33개 Config 전체를 교육용으로 시연하지만, CI/CD 파이프라인에서는 **7개 Gate당 1개 Config씩 최소 검증**만 실행하는 `ch18_cicd_gate.py`를 사용한다:

```python
# 출처: Evaluator_Examples/ch18_cicd_gate.py — CI/CD 전용 최소 검증
import json, sys
from agent_evaluator import (
    PerformanceMonitor,
    InstructionConfig, GoalAlignmentConfig,      # Group A
    LoopDetectionConfig, ScopeConfig,            # Group B
    ReproducibilityConfig, RetryConsistencyConfig, # Group C
    SLAConfig, ResourceBudgetConfig,             # Group D
    ThreatSeverityConfig, ComplianceConfig,      # Group E
    ConsensusConfig, AgentRoleConfig,            # Group F
    ExplainabilityConfig, ObservabilityConfig,   # Group G
)
from agent_evaluator.decorators import agent_eval

_STRICT_MODE = "--strict" in sys.argv   # WARN도 FAIL로 처리

monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# Group A — 목표달성
@agent_eval(monitor, task_type="qa", task_id_prefix="val_a",
    instructions=InstructionConfig(required_keywords=["answer", "source"], min_chars=10),
    goal_alignment=GoalAlignmentConfig(goal_tool_map={"search": ["web_search"]}, alignment_threshold=0.5),
)
def _group_a_agent(question, ground_truth=""):
    return json.dumps({"answer": question + "에 대한 검증 답변", "source": "내부 DB"})

# Group B — 행동무결성
@agent_eval(monitor, task_type="tool_use", task_id_prefix="val_b",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, window_size=5),
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "report"],
        forbidden_tools=["delete_all", "drop_table"],
    ),
)
def _group_b_agent(question, ground_truth=""):
    return f"재무 리포트 조회: {question}"

# ... (Group C~G는 동일 패턴으로 각 1개 Config)

# 실행 및 판정
for q in ["최근 분기 실적은?", "이번 달 비용 예측을 해줘"]:
    _group_a_agent(q, ground_truth="검증 완료")
    _group_b_agent(q, ground_truth="검증 완료")

report = monitor.generate_report()
monitor.save_to_file("harness_validation")

# JSON 한 줄 요약 — CI 로그 파싱용
d = report.to_dict()
harness = d.get("harness_gates", {})
summary = {
    grp: harness.get(grp, {}).get("gate_status", "N/A")
    for grp in ["A", "B", "C", "D", "E", "F", "G"]
}
print(json.dumps(summary))  # {"A": "PASS", "B": "PASS", ...}

# exit code 결정
failures = [g for g, s in summary.items() if s == "FAIL"]
warnings = [g for g, s in summary.items() if s == "WARN"]
if failures or (_STRICT_MODE and warnings):
    sys.exit(1)
sys.exit(0)
```

```bash
# GitHub Actions 통합
python Evaluator_Examples/ch18_cicd_gate.py         # FAIL만 차단
python Evaluator_Examples/ch18_cicd_gate.py --strict  # WARN도 차단
```

- **기본 모드**: Gate 상태가 `FAIL`인 Group이 하나라도 있으면 `sys.exit(1)`로 파이프라인을 차단한다
- **`--strict` 모드**: `WARN` 상태도 실패로 처리해 더 엄격한 품질 기준을 적용한다

| 항목 | `ch03_harness_basics.py` | `ch18_cicd_gate.py` |
|------|---------------------|---------------------------|
| 목적 | 교육·시연 | CI/CD 자동화 |
| Config 수 | 33개 전부 | 7개 (Gate당 1개) |
| 실행 시간 | ~15초 | ~3초 |
| exit code | 없음 | 0 (통과) / 1 (실패) |
| `--strict` | 없음 | WARN → FAIL 처리 |


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

- **`ReproducibilityConfig(runs=5)`**: 동일 입력을 5회 실행해 결과 분산을 측정한다 (단일 `assert`로 확인 불가한 부분)
- **`reproducibility_threshold=0.85`**: 5회 중 85% 이상 일관된 결과가 나와야 통과로 처리한다
- **`SLAConfig(p95_ms=2000)`**: 단일 샘플이 아닌 전체 실행의 95번째 백분위수 응답 시간으로 SLA를 판정한다

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
        min_reasoning_length=50,      # 추론 근거 최소 50자
        reasoning_markers=["왜냐하면", "근거:", "출처:"],  # 추론 마커 필수
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

- **`LLMJudgeConfig(criteria=[...])`**: LLM이 `factual_accuracy`·`reasoning_quality` 기준으로 응답을 0–5 척도로 자동 채점한다 (ground_truth 불필요)
- **`sample_rate=0.1`**: 전체 호출의 10%만 LLM Judge로 채점해 비용을 90% 절감한다
- **`ExplainabilityConfig`**: 응답에 추론 근거 마커("왜냐하면", "근거:" 등)가 포함되어야 하며, 추론 텍스트가 최소 50자 이상이어야 한다
- **두 Config의 결합**: LLM Judge가 채점한 `reasoning_quality` 점수와 `ExplainabilityConfig`의 마커 탐지가 Group G 관측성 점수에 함께 기여한다

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

- **`enable_anomaly_detection=True`**: `AnomalyDetector`를 활성화해 지연 급등·오류율 이상·토큰 소비 급증 등 통계적 이상치를 자동 탐지한다
- **`ScopeConfig(allowed_tools=[...])`**: 허용 도구 목록 외의 도구를 사용하면 `fail_on_violation=True`에 의해 즉시 실패 처리한다
- **`forbidden_tools`**: 절대 호출하면 안 되는 도구를 명시하면 설계자가 예측하지 못한 도구 호출도 차단한다

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
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 1
"""5분 안에 완성하는 첫 Harness 평가"""
from agent_evaluator import QuickEval
from agent_evaluator import SLAConfig, InstructionConfig

eval = QuickEval("results/")

# Step 1: Config 선언 (배포 기준을 코드로)
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000),                              # 관찰 모드 (위반 시 기록만)
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
tcr = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
acc = d.get("accuracy_metrics", {}).get("accuracy_scores", {}).get("overall_accuracy", 0.0)
print(f"TCR    : {tcr * 100:.1f}%")
print(f"정확도  : {acc * 100:.1f}%")

# Step 4: 배포 판정 (기준 미달 시 sys.exit(1))
eval.gate(tcr=60, accuracy=50)
print("\n✅ Harness Gate 통과 — 배포 가능")
```

이 코드를 실행하면 Harness Engineering의 전체 흐름을 경험할 수 있다.
- Config 선언 → 측정 → 보고서 → Gate 판정 → 배포 승인/차단

---

## 3.9 실전 예제 파일

이 챕터에서 설명한 Harness Engineering 개념을 바로 실행해볼 수 있는 예제 파일이 준비되어 있다.

| 예제 파일 | 관련 내용 |
|---------|---------|
| [`Evaluator_Examples/ch03_harness_basics.py`](../../Evaluator_Examples/ch03_harness_basics.py) | 7개 Gate(A-G) 전체 PASS 시나리오 — 33개 Config 실전 시연 |
| [`Evaluator_Examples/ch18_cicd_gate.py`](../../Evaluator_Examples/ch18_cicd_gate.py) | CI/CD 게이팅 exit code 검증 — HarnessEvaluationGate.enforce() |
| [`Evaluator_Examples/ch04_group_a.py`](../../Evaluator_Examples/ch04_group_a.py) | 17개 시나리오 — Gate A~G 모두 FAIL 유도, 배포 차단 케이스 완전 시연 |
| [`Evaluator_Examples/ch20_deployment.py`](../../Evaluator_Examples/ch20_deployment.py) | v1 레거시 → v2 개선 에이전트 Harness Gate 비교 (+29% 향상) |

```bash
python Evaluator_Examples/ch03_harness_basics.py         # Gate A~G PASS 전체
python Evaluator_Examples/ch18_cicd_gate.py   # CI/CD 게이팅 exit code
python Evaluator_Examples/ch04_group_a.py  # Gate A~G FAIL 케이스 — 배포 차단 시나리오
python Evaluator_Examples/ch20_deployment.py   # v1 vs v2 버전 비교
```

**버전 비교 — Harness Gate로 배포 결정 (출처: `Evaluator_Examples/ch20_deployment.py`)**

`ch20_deployment.py`는 두 `PerformanceMonitor`를 독립적으로 운영해 v1·v2 에이전트의 Gate A–G 점수를 나란히 비교한다. 점수 차이가 "v2를 배포하는 이유"의 코드 근거가 된다.

```python
# 출처: Evaluator_Examples/ch20_deployment.py — 독립 monitor로 v1 vs v2 Gate 비교
from agent_evaluator import PerformanceMonitor, SLAConfig, ComplianceConfig, ExplainabilityConfig
from agent_evaluator.decorators import agent_eval

monitor_v1 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)
monitor_v2 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# Gate A: v1 — 형식 미준수 / v2 — JSON 준수
@agent_eval(monitor_v1, task_type="qa", task_id_prefix="v1_instr",
            instructions=InstructionConfig(expected_format="json", required_keywords=["result"]))
def v1_agent(question: str, ground_truth: str = "") -> str:
    return f"답: {question}"  # JSON 미준수

@agent_eval(monitor_v2, task_type="qa", task_id_prefix="v2_instr",
            instructions=InstructionConfig(expected_format="json", required_keywords=["result"]))
def v2_agent(question: str, ground_truth: str = "") -> str:
    import json
    return json.dumps({"result": f"{question}에 대한 정확한 답변"})  # JSON 준수

for q in ["분기 실적 분석", "보고서 작성", "모델 평가"]:
    v1_agent(q, ground_truth="분석")
    v2_agent(q, ground_truth="분석")

# Gate별 점수 비교
r1 = monitor_v1.generate_report().to_dict()
r2 = monitor_v2.generate_report().to_dict()
h1 = (r1.get("extra_metrics") or {}).get("harness_groups", {})
h2 = (r2.get("extra_metrics") or {}).get("harness_groups", {})

for gk in "ABCDEFG":
    s1 = (h1.get(gk) or {}).get("score") or 0.0
    s2 = (h2.get(gk) or {}).get("score") or 0.0
    delta = (s2 - s1) * 100
    print(f"  Gate {gk}: v1={s1:.0%}  v2={s2:.0%}  {'+' if delta>0 else ''}{delta:.1f}%p")

monitor_v1.save_to_file("v1_harness"); monitor_v2.save_to_file("v2_harness")
```

- **독립 monitor 2개**: v1·v2 에이전트를 각각 다른 `PerformanceMonitor`로 평가해 Group A–G 점수를 독립적으로 집계한다
- **동일 Config 선언**: 두 에이전트에 동일한 `InstructionConfig`를 적용해 같은 기준으로 비교한다
- **`harness_groups` 딕셔너리**: `report.to_dict()`의 `extra_metrics.harness_groups`에서 Group별 점수를 꺼내 delta를 계산한다
- **`save_to_file()`**: JSON + HTML 두 파일을 자동 생성하며, 대시보드에서 v1·v2를 나란히 확인할 수 있다

**Phoenix OTEL과 Harness Gate 연동 (출처: `Evaluator_Examples/ch19_phoenix.py`)**

`setup_otel()`을 Harness 평가 전에 호출하면 Gate A–G의 모든 스팬이 Phoenix로 전송되어 대시보드에서 Group별 점수 추이를 시각적으로 확인할 수 있다.

```python
# 출처: Evaluator_Examples/ch19_phoenix.py — Harness Gate + Phoenix OTEL 연동
import socket
from agent_evaluator import setup_otel, PerformanceMonitor

# Phoenix 실행 여부 확인 — CI 환경에서는 미실행이 정상
try:
    with socket.create_connection(("localhost", 6006), timeout=1):
        setup_otel(endpoint="http://localhost:6006", service_name="harness-gate")
        print("Phoenix OTEL 연결 — Gate A–G 스팬 전송 활성화")
except OSError:
    print("Phoenix 미실행 — OTEL 없이 Gate 판정만 수행")

# setup_otel() 이후에 monitor 생성 (순서 필수)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,
    enable_transparency=True,  # Harness 집계 Traces → Phoenix 전송
)
# → Phoenix http://localhost:6006 의 Traces 탭에서 Gate별 점수를 스팬으로 확인 가능
```

- **`setup_otel()` 호출 순서**: `PerformanceMonitor` 생성 전에 반드시 `setup_otel()`을 호출해야 스팬이 Phoenix로 전송된다
- **`socket.create_connection` 체크**: CI 환경에서 Phoenix가 미실행 상태여도 예외를 잡아 OTEL 없이 정상 진행하도록 안전하게 처리한다
- **`enable_transparency=True`**: Gate A–G의 집계 과정을 OTEL 스팬으로 내보내 Phoenix Traces 탭에서 시각적으로 확인할 수 있다
- **주의점**: Phoenix를 먼저 `agent-eval monitor` 명령으로 실행한 후 이 코드를 실행해야 스팬이 수신된다

---

## 3.10 이 챕터의 핵심 요약

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
