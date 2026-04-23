# Appendix M. 프로덕션 운영 체크리스트 — 배포 전 최종 점검 항목

AI 에이전트를 프로덕션에 배포하는 것은 일반 소프트웨어 배포와 다른 고유한 위험을 수반한다. 결정론적 프로그램과 달리 에이전트는 동일한 입력에도 다른 출력을 생성할 수 있고, 도구를 통해 외부 시스템에 실제 영향을 미치며, 예측하지 못한 방식으로 행동할 수 있다. "배포 전 잠깐의 점검"이 프로덕션 장애 수십 시간을 예방한다.

이 부록은 **Harness Engineering** 관점에서 배포 전 점검 항목을 체계화한다. Agent-Evaluator SDK의 7개 Harness Gate(A–G) 각각에 대해 Tracker(측정)와 Config(기준 선언)가 실제로 의도대로 동작하는지 확인한다. 각 항목은 **Pass/Warn/Fail** 세 가지 상태로 판정하며, Fail 항목이 하나라도 있으면 배포를 중단해야 한다. Warn 항목은 위험을 인지한 상태에서 책임자 승인 하에 배포를 진행할 수 있다.

**Gate 활성화 정책**: Gate A(목표달성)와 Gate D(성능계약)는 `PerformanceMonitor`를 생성하는 순간 항상 활성화된다. Gate B(행동무결성), C(신뢰성), E(보안경계), F(다중에이전트), G(관측가능성)는 해당 Config를 데코레이터에 선언하거나 `enable_security_metrics=True` 같은 플래그를 명시해야 활성화되는 **opt-in** Gate다. 이 체크리스트는 각 Gate가 실제로 활성화되어 있는지를 먼저 확인한 뒤 세부 항목을 점검한다.

---

## M.1 체크리스트 사용 방법

### M.1.1 체크리스트 구조

이 부록의 체크리스트는 세 계층으로 구성된다.

```
계층 1 — Gate 체크리스트 (M.2)
  7개 Harness Gate × 평균 8개 항목 = 56개 핵심 점검

계층 2 — 인프라 체크리스트 (M.3)
  환경·네트워크·시크릿·의존성 = 24개 항목

계층 3 — 운영 준비 체크리스트 (M.4)
  모니터링·알림·롤백·문서화 = 20개 항목
```

**총 100개 항목**. 소규모 프로젝트에서 모두 점검하는 데 약 2–4시간이 소요된다. CI/CD 파이프라인에 자동화된 항목(★ 표시)은 사람이 직접 점검하는 대신 CI 결과를 참조한다.

### M.1.2 판정 기준

| 상태 | 의미 | 배포 허용 |
|---|---|---|
| ✅ Pass | 기준을 충족함 | 허용 |
| ⚠️ Warn | 기준 미충족이지만 허용 범위 내 | 책임자 승인 필요 |
| ❌ Fail | 기준 미충족, 즉각 수정 필요 | 배포 중단 |
| ⬜ N/A | 해당 항목이 이 에이전트에 적용되지 않음 | — |

### M.1.3 자동화 점검 CLI

Agent-Evaluator CLI를 사용하면 Gate 체크리스트 중 측정 가능한 항목을 자동으로 점검할 수 있다.

```bash
# 골든 데이터셋 기반 Gate 전체 점검
# exit 0 = 통과 / exit 1 = 실패 → CI/CD 파이프라인 자동 차단
agent-eval gate results/golden_eval.json \
  --tcr 85 \
  --accuracy 70 \
  --min-gate-score 0.75

# 회귀 감지 — 최근 10개 결과 파일 추세 분석
# exit 0 = 정상 / exit 2 = 회귀 감지 → --fail-on-regression 플래그 사용 시
agent-eval trend results/ \
  --window 10 \
  --fail-on-regression

# 점검 결과를 JSON으로 저장 (CI/CD 아티팩트)
agent-eval gate results/golden_eval.json \
  --tcr 85 --accuracy 70 \
  --output-json gate_check.json

# 현재 설정 상태 확인 (API 키, 경로 등)
agent-eval check

# OTEL 수신 상태 및 포트 점유 확인 (Phoenix 포트 기본값: 6006)
agent-eval monitor --check

# 대시보드 실행 (기본 포트: 8765)
agent-eval dashboard
```

```python
# Python API로 동일 점검 수행
from agent_evaluator import QuickEval

eval = QuickEval("results/")
# 아래 gate() 호출은 기준 미달 시 sys.exit(1)로 CI를 실패 처리
eval.gate(tcr=85, accuracy=70)
```

---

## M.2 Harness Gate 체크리스트

### M.2.1 Gate A — Goal Achievement (목표 달성)

에이전트가 사용자의 의도를 정확히 이해하고 달성하는지 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| A-01 ★ | Task Completion Rate (TCR) ≥ 85% | 골든셋 100건 기준 | ✅/❌ | `agent-eval gate --tcr 85` |
| A-02 ★ | 정확도 점수 (Token F1) ≥ 0.70 | 골든셋 QA 항목 기준 | ✅/❌ | `agent-eval gate --accuracy 70` |
| A-03 | `InstructionConfig.required_keywords` 이행률 ≥ 90% | 필수 키워드 포함 여부 | ✅/⚠️/❌ | |
| A-04 | 목표 정렬 점수 (GoalAlignmentConfig) ≥ 0.80 | 부분 달성 포함 | ✅/⚠️/❌ | |
| A-05 | 계획 단계 완주율 (PlanConfig) ≥ 80% | 멀티스텝 태스크 | ✅/⚠️/❌ | N/A (단일 응답 에이전트) |
| A-06 | 하위 태스크 완료율 (SubtaskConfig) ≥ 85% | 분해된 태스크 기준 | ✅/⚠️/❌ | N/A (단순 에이전트) |
| A-07 | 멀티턴 컨텍스트 유지율 ≥ 85% | ContextRetentionConfig | ✅/⚠️/❌ | N/A (단발성 에이전트) |
| A-08 | LLMJudge 전체 점수 ≥ 3.5/5.0 | 골든셋 Judge 샘플링 | ✅/⚠️/❌ | LLMJudge 비활성화 시 N/A |

**A 게이트 통과 조건**: A-01, A-02가 Pass이고 나머지 적용 항목 중 Fail이 없어야 한다.

```python
# Gate A 점검 코드 예시
from agent_evaluator import PerformanceMonitor, InstructionConfig, GoalAlignmentConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/", enable_hallucination_detection=True)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        required_keywords=["근거", "출처"],
        fail_on_violation=True,
    ),
    goal_alignment=GoalAlignmentConfig(alignment_threshold=0.80),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    ...

# 골든셋 실행 후 게이팅
monitor.save_to_file("gate_a_check")
# agent-eval gate results/gate_a_check.json --tcr 85 --accuracy 70
```

---

### M.2.2 Gate B — Behavioral Integrity (행동 무결성)

에이전트가 허용된 범위 안에서만 행동하고 루프나 교착 없이 동작하는지 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| B-01 ★ | 루프 탐지 제로 (LoopDetectionConfig) | 골든셋 전체 | ✅/❌ | consecutive_repeat_threshold=3 |
| B-02 | 범위 일탈(ScopeConfig) 발생률 = 0% | allowed_tools 위반 | ✅/❌ | |
| B-03 | 도구 파라미터 안전성 위반 = 0건 | ToolParameterSafetyConfig | ✅/❌ | |
| B-04 | 상태 불일관성 (StateConsistencyConfig) = 0건 | unchanged_keys 보존 | ✅/❌ | |
| B-05 | 교착 탐지 (DeadlockConfig) = 0건 | 순환 위임·깊이 초과 | ✅/❌ | |
| B-06 | 컨텍스트 창 활용률 ≤ 85% | ContextWindowConfig | ✅/⚠️/❌ | 초과 시 잘림 위험 |
| B-07 | 도구 호출 수 / 완료 태스크 비율 ≤ 설정값 | 효율성 지표 | ✅/⚠️/❌ | |
| B-08 | 도구 파라미터 타입 오류율 ≤ 1% | 잘못된 파라미터 | ✅/⚠️/❌ | |

**B 게이트 통과 조건**: B-01~B-05 모두 Pass. 범위 일탈과 교착은 허용 범위가 없다.

```python
from agent_evaluator import (
    LoopDetectionConfig, ScopeConfig, StateConsistencyConfig, DeadlockConfig,
)

@agent_eval(
    monitor,
    task_type="tool_use",
    loop_detection=LoopDetectionConfig(
        consecutive_repeat_threshold=3,
        window_size=10,
    ),
    scope=ScopeConfig(
        allowed_tools=["search", "retrieve", "summarize"],
        fail_on_violation=True,
    ),
    state_consistency=StateConsistencyConfig(
        unchanged_keys=["user_id", "session_id", "permissions"],
    ),
    deadlock=DeadlockConfig(max_delegation_depth=3),
)
def tool_agent(question: str, ground_truth: str = "") -> str:
    ...
```

---

### M.2.3 Gate C — Reliability (신뢰성)

에이전트가 장애 상황에서도 품질을 유지하고 예측 가능하게 동작하는지 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| C-01 | 재현 가능성 — 동일 입력 3회 실행 일관성 ≥ 0.85 | ReproducibilityConfig | ✅/⚠️/❌ | temperature=0 권장 |
| C-02 ★ | 오류 후 복구율 (FaultToleranceConfig) ≥ 80% | 주입된 오류 시나리오 | ✅/⚠️/❌ | |
| C-03 | 품질 하한 (GracefulDegradationConfig) ≥ 0.60 | 부분 실패 시 최소 품질 | ✅/⚠️/❌ | |
| C-04 | 재시도 간 응답 일관성 (RetryConsistencyConfig) ≥ 0.75 | 같은 태스크 재시도 | ✅/⚠️/❌ | |
| C-05 | 멱등성 검증 통과 (IdempotencyConfig) | 중복 실행 안전 | ✅/❌ | 쓰기 작업 에이전트 필수 |
| C-06 | 타임아웃 처리 정상 동작 | 외부 API 타임아웃 | ✅/❌ | |
| C-07 | 재시도 로직 구현 (최대 횟수 제한 포함) | 무한 재시도 방지 | ✅/❌ | |
| C-08 | 부분 성공 인정 및 사용자 안내 | 완전 실패 vs 부분 성공 | ✅/⚠️/❌ | |

**C 게이트 통과 조건**: C-05, C-06, C-07은 Pass 필수. 쓰기 작업이 없는 읽기 전용 에이전트는 C-05를 N/A로 처리한다.

```python
from agent_evaluator import (
    FaultToleranceConfig, GracefulDegradationConfig, IdempotencyConfig,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    fault_tolerance=FaultToleranceConfig(
        partial_success_threshold=0.80,
        check_fallback_attempts=True,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.60,
        check_error_acknowledgment=True,
        partial_result_markers=["부분적으로", "일부", "제한된 정보"],
    ),
    idempotency=IdempotencyConfig(warn_on_non_idempotent=True),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    ...
```

---

### M.2.4 Gate D — Performance Contract (성능 계약)

SLA, 토큰 비용, 지연 시간 예측 가능성을 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| D-01 ★ | P95 응답 시간 ≤ SLA 설정값 | SLAConfig.p95_ms | ✅/❌ | 예: 5,000ms |
| D-02 ★ | P99 응답 시간 ≤ SLA 설정값 × 1.5 | SLAConfig.p99_ms | ✅/⚠️/❌ | |
| D-03 | 토큰 효율 — 도구 호출 대비 완료율 ≥ 0.60 | EfficiencyConfig | ✅/⚠️/❌ | |
| D-04 | 호출당 예상 비용 ≤ 예산 상한 | ResourceBudgetConfig.max_cost_usd | ✅/⚠️/❌ | |
| D-05 | TTFT 변동성 — P95/P50 비율 ≤ 3.0 | TTFTVariabilityConfig | ✅/⚠️/❌ | 스트리밍 에이전트 |
| D-06 | task_type별 비용 예측 가능성 (CV ≤ 0.30) | CostPredictabilityConfig | ✅/⚠️/❌ | |
| D-07 | 부하 테스트 — 동시 10 요청 시 P95 ≤ SLA × 2 | 부하 시뮬레이션 | ✅/⚠️/❌ | |
| D-08 | 월간 예상 비용 계산 및 예산 승인 완료 | 비용 예측 문서화 | ✅/❌ | |

**D 게이트 통과 조건**: D-01, D-08 Pass 필수. D-07은 트래픽이 높은 에이전트에서 필수.

```python
from agent_evaluator import SLAConfig, EfficiencyConfig, ResourceBudgetConfig

@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(
        p95_ms=5000,
        p99_ms=8000,
    ),
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=500,   # 완료 태스크당 500 토큰 이하 목표
        warn_ratio=1.5,
        fail_ratio=2.5,
        penalize_failed_tokens=True,
    ),
    resource_budget=ResourceBudgetConfig(
        max_cost_usd=0.02,
        max_tokens=4000,
    ),
)
def production_agent(question: str, ground_truth: str = "") -> str:
    ...
```

```bash
# SLA 검증 — 최근 추세에서 회귀 감지
agent-eval trend results/ --window 10 --fail-on-regression
```

---

### M.2.5 Gate E — Security Boundary (보안 경계)

입력 위협 탐지, 민감 정보 보호, 도구 권한 관리를 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| E-01 ★ | SQL/Command/XSS 인젝션 탐지율 = 100% | InputSanitizationTracker | ✅/❌ | 40개+ 패턴 |
| E-02 ★ | PII 유출 탐지율 = 100% | OutputLeakageDetector | ✅/❌ | 주민번호·카드번호 등 |
| E-03 | 프롬프트 인젝션 탐지율 ≥ 95% | InputSanitizationTracker | ✅/⚠️/❌ | |
| E-04 | Critical 위협 탐지 시 자동 차단 동작 확인 | ThreatSeverityConfig.fail_on_critical | ✅/❌ | |
| E-05 | 권한 상승 시도 탐지 = 0 허용 | PrivilegeEscalationDetector | ✅/❌ | |
| E-06 | 도구 체인 공격 탐지 동작 확인 | ToolChainAttackDetector | ✅/❌ | |
| E-07 | 도구 권한 최소 원칙 적용 확인 | ToolAuthorizationTracker | ✅/❌ | |
| E-08 | API 키·시크릿이 출력에 포함되지 않음 | ComplianceConfig 패턴 | ✅/❌ | |
| E-09 | 레드팀 평가 완료 (Appendix K 기준) | 인젝션·탈취 시나리오 | ✅/❌ | 고위험 에이전트 필수 |
| E-10 | 위협 대응 동작 (ThreatResponseConfig) 검증 | BLOCKED/ABORT 마커 | ✅/❌ | |

**E 게이트 통과 조건**: E-01~E-08 모두 Pass. 외부 사용자에게 노출되는 에이전트는 E-09 필수.

```python
from agent_evaluator import (
    ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")

@agent_eval(
    monitor,
    task_type="tool_use",
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,
        warn_score=4.0,
        fail_score=7.0,
    ),
    compliance=ComplianceConfig(
        forbidden_data_patterns=[
            r"\d{6}-\d{7}",            # 주민등록번호
            r"\d{4}-\d{4}-\d{4}-\d{4}", # 카드번호
            r"[A-Za-z0-9+/]{40,}={0,2}", # Base64 인코딩 시크릿
            r"sk-[A-Za-z0-9]{48}",      # OpenAI API 키 패턴
        ],
        pii_categories=["ssn", "credit_card", "api_key"],
    ),
    threat_response=ThreatResponseConfig(
        isolation_markers=["[BLOCKED]", "[THREAT DETECTED]"],
        abort_markers=["[ABORT]"],
    ),
)
def secure_agent(question: str, ground_truth: str = "") -> str:
    ...
```

---

### M.2.6 Gate F — Multi-Agent Coordination (멀티에이전트 조정)

에이전트 간 합의, 정보 전파 정확도, 역할 준수를 검증한다. 단일 에이전트는 이 Gate를 N/A로 처리한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| F-01 | 에이전트 간 합의율 ≥ 80% | ConsensusConfig.similarity_threshold | ✅/⚠️/❌ | N/A (단일 에이전트) |
| F-02 | 정보 전파 정확도 ≥ 90% | PropagationConfig.similarity_threshold | ✅/⚠️/❌ | N/A (단일 에이전트) |
| F-03 | 역할 준수율 = 100% | AgentRoleConfig | ✅/❌ | |
| F-04 | 충돌 해결 — 설명 포함 비율 ≥ 80% | ConflictResolutionConfig.require_explanation | ✅/⚠️/❌ | |
| F-05 | 에이전트 간 무한 위임 순환 = 0건 | DeadlockConfig.max_delegation_depth | ✅/❌ | |
| F-06 | 오케스트레이터–서브에이전트 응답 일관성 ≥ 0.85 | 독립 검증 | ✅/⚠️/❌ | |
| F-07 | 타임아웃 시 부분 결과 반환 동작 확인 | GracefulDegradationConfig | ✅/❌ | |

**F 게이트 통과 조건**: F-03, F-05 Pass 필수. 단일 에이전트는 Gate F 전체 N/A 처리 가능.

```python
from agent_evaluator import (
    ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig,
)

@agent_eval(
    monitor,
    task_type="planning",
    consensus=ConsensusConfig(
        similarity_threshold=0.80,
        consensus_method="majority",
        min_agents=2,
    ),
    propagation=PropagationConfig(
        similarity_threshold=0.90,
        penalize_distortion=True,
    ),
    agent_role=AgentRoleConfig(
        expected_role="orchestrator",
        allowed_delegations=["researcher", "writer", "reviewer"],
    ),
    conflict_resolution=ConflictResolutionConfig(
        require_explanation=True,
        expect_escalation_on_fail=True,
        max_resolution_turns=3,
    ),
)
def orchestrator_agent(question: str, ground_truth: str = "") -> str:
    ...
```

---

### M.2.7 Gate G — Observability (관측 가능성)

에이전트의 추론 과정, 오류 원인, 지연 분석이 충분히 투명한지 검증한다.

| # | 점검 항목 | 기준 | 판정 | 비고 |
|---|---|---|---|---|
| G-01 | 추론 설명 최소 길이 충족 | ExplainabilityConfig.min_reasoning_length | ✅/⚠️/❌ | |
| G-02 | 추론 마커 포함 비율 ≥ 80% | ExplainabilityConfig.reasoning_markers | ✅/⚠️/❌ | |
| G-03 | 내부 상태 추적 커버리지 ≥ 0.80 | ObservabilityConfig.min_coverage | ✅/⚠️/❌ | |
| G-04 | 오류 원인 진단 정확도 ≥ 0.70 | ErrorDiagnosisConfig.root_cause_weight | ✅/⚠️/❌ | |
| G-05 | 지연 구간별 분석 추적 설정 확인 | LatencyAttributionConfig | ✅/⚠️/❌ | |
| G-06 ★ | OTEL 스팬 Phoenix로 정상 수신 확인 | `agent-eval monitor --check` | ✅/⚠️/❌ | OTEL 사용 시 |
| G-07 | 로그 레벨 프로덕션 적합 설정 (INFO 이상) | 로깅 설정 검토 | ✅/❌ | DEBUG 로그 금지 |
| G-08 | 평가 결과 파일 자동 저장 설정 확인 | auto_save=True, interval 설정 | ✅/❌ | |

**G 게이트 통과 조건**: G-07, G-08 Pass 필수. OTEL을 사용하는 경우 G-06 Pass 필수.

```python
from agent_evaluator import (
    ExplainabilityConfig, ObservabilityConfig, ErrorDiagnosisConfig, LatencyAttributionConfig,
)

monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    explainability=ExplainabilityConfig(
        min_reasoning_length=50,
        require_reasoning=True,
        reasoning_markers=["근거:", "출처:", "왜냐하면", "따라서"],
    ),
    observability=ObservabilityConfig(min_coverage=0.85),
    error_diagnosis=ErrorDiagnosisConfig(root_cause_weight=0.7),
    latency_attribution=LatencyAttributionConfig(
        track_segments=["retrieval", "generation", "formatting"],
    ),
)
def explainable_agent(question: str, ground_truth: str = "") -> str:
    ...
```

---

## M.3 인프라 체크리스트

### M.3.1 환경 및 의존성

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| I-01 ★ | Python 버전 3.8+ 확인 | `python --version` | ✅/❌ |
| I-02 ★ | `agent-evaluator` 패키지 버전 고정 | `requirements.txt` 또는 `pyproject.toml` | ✅/❌ |
| I-03 ★ | 모든 의존성 버전 고정 (hash 또는 range) | `pip freeze` 검토 | ✅/❌ |
| I-04 | 가상 환경 또는 컨테이너 격리 확인 | venv·conda·Docker | ✅/❌ |
| I-05 | Optional extra 필요 여부 확인 및 설치 | `[eval]`·`[semantic]` 등 | ✅/❌ |
| I-06 | 외부 모델 API (OpenAI·Anthropic) 연결 테스트 | 실제 호출 확인 | ✅/❌ |

### M.3.2 시크릿 관리

민감한 자격증명을 소스 코드에 하드코딩하는 것은 보안 사고의 가장 흔한 원인이다.

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| I-07 | API 키가 소스 코드에 없음 | `grep -r "sk-" .` 결과 없음 | ✅/❌ |
| I-08 | `.env` 파일이 `.gitignore`에 포함 | `git check-ignore .env` | ✅/❌ |
| I-09 | 환경변수 주입 방식 확인 | `os.getenv()` 또는 Vault | ✅/❌ |
| I-10 | API 키 로테이션 주기 정의 | 30–90일 권장 | ✅/⚠️/❌ |
| I-11 | 프로덕션·스테이징·개발 환경별 별도 키 사용 | 키 분리 확인 | ✅/❌ |
| I-12 | 시크릿 관리 시스템 (AWS Secrets Manager·HashiCorp Vault 등) 사용 | 고위험 환경 | ✅/⚠️/❌ |

```bash
# API 키 하드코딩 검사
grep -r "sk-" --include="*.py" .
grep -r "ANTHROPIC_API_KEY\s*=" --include="*.py" .
grep -r "os.environ\[" --include="*.py" . | grep -v "os.getenv"
```

### M.3.3 네트워크 및 API 제한

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| I-13 | Rate Limit 처리 로직 구현 확인 | 429 응답 처리 | ✅/❌ |
| I-14 | 지수 백오프(exponential backoff) 구현 | 재시도 간격 2^n초 | ✅/⚠️/❌ |
| I-15 | 외부 API 타임아웃 설정 (요청당 ≤ 30초) | `httpx.timeout`, `requests.timeout` | ✅/❌ |
| I-16 | 회로 차단기(circuit breaker) 패턴 적용 | 연속 실패 시 임시 중단 | ✅/⚠️/❌ |
| I-17 | 프록시·방화벽 환경에서 API 접근 확인 | 운영 네트워크 테스트 | ✅/❌ |

### M.3.4 스케일링 및 리소스

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| I-18 | 동시 실행 최대 워커 수 설정 | 큐 또는 세마포어 | ✅/❌ |
| I-19 | 메모리 누수 없음 확인 (장기 실행 테스트) | 6시간 이상 실행 모니터링 | ✅/⚠️/❌ |
| I-20 | 디스크 사용량 — 결과 파일 로테이션 정책 | 일별 압축·30일 보관 | ✅/⚠️/❌ |

---

## M.4 운영 준비 체크리스트

### M.4.1 모니터링 및 알림

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| O-01 | AlertEngine 설정 및 핸들러 연결 확인 | Slack·이메일·PagerDuty | ✅/❌ |
| O-02 | TCR 저하 알림 규칙 설정 | TCR < 0.80 시 경고 | ✅/❌ |
| O-03 | SLA 위반 알림 규칙 설정 | P95 초과 시 즉시 알림 | ✅/❌ |
| O-04 | 보안 위협 탐지 알림 규칙 설정 | Critical 위협 즉시 알림 | ✅/❌ |
| O-05 | 비용 초과 알림 규칙 설정 | 일간 예산 80% 도달 시 | ✅/❌ |
| O-06 | AnomalyDetector 활성화 및 임계값 설정 | 이상 탐지 민감도 | ✅/⚠️/❌ |
| O-07 | 대시보드 접근 URL 및 인증 설정 완료 | `agent-eval dashboard` | ✅/❌ |

```python
from agent_evaluator import SimpleTaskAlertRule, AlertRuleBuilder
from agent_evaluator.alerts.engine import AlertEngine

# TCR 저하 알림
tcr_alert = SimpleTaskAlertRule(
    name="tcr_degradation",
    condition=lambda tr: not tr.success and tr.task_type is not None,
    handler=lambda msg, tr: send_slack(f"[ALERT] {msg}"),
    severity="warning",
    cooldown=300,  # 5분에 한 번만 알림
)

# 비용 초과 알림
cost_alert = SimpleTaskAlertRule(
    name="cost_spike",
    condition=lambda tr: (tr.cost_usd or 0) > 0.10,
    handler=lambda msg, tr: send_slack(f"[COST ALERT] 단일 호출 비용 ${tr.cost_usd:.3f}"),
    severity="warning",
    cooldown=60,
)

@agent_eval(
    monitor,
    task_type="qa",
    alert_rules=[tcr_alert, cost_alert],
)
def production_agent(question: str, ground_truth: str = "") -> str:
    ...
```

### M.4.2 롤백 계획

배포가 실패했을 때 빠르게 이전 버전으로 돌아갈 수 있는지 사전 검증한다.

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| O-08 | 롤백 절차 문서화 완료 | 단계별 RunBook 존재 | ✅/❌ |
| O-09 | 이전 버전 이미지·아티팩트 보존 확인 | 최소 2개 이전 버전 | ✅/❌ |
| O-10 | 롤백 소요 시간 측정 완료 | ≤ 15분 목표 | ✅/⚠️/❌ |
| O-11 | 롤백 후 Gate 체크리스트 자동 실행 설정 | CI/CD 파이프라인 연동 | ✅/⚠️/❌ |
| O-12 | 데이터 마이그레이션 없이 롤백 가능 확인 | 스키마 하위 호환성 | ✅/❌ |

### M.4.3 카나리 배포 및 트래픽 전환

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| O-13 | 카나리 배포 가능 여부 확인 | 트래픽 10%→50%→100% | ✅/⚠️/❌ |
| O-14 | 카나리 단계별 Gate 통과 기준 정의 | 각 단계 24시간 관찰 | ✅/⚠️/❌ |
| O-15 | 피처 플래그 또는 A/B 테스트 인프라 준비 | 점진적 전환 가능 | ✅/⚠️/❌ |

### M.4.4 문서화

| # | 점검 항목 | 기준 | 판정 |
|---|---|---|---|
| O-16 | 에이전트 동작 범위 문서화 | allowed_tools, 지원 task_type | ✅/❌ |
| O-17 | 알려진 한계(Known Limitations) 문서화 | 탐지 못하는 실패 유형 포함 | ✅/❌ |
| O-18 | 장애 대응 절차(Incident Response) 문서화 | 심각도별 대응 단계 | ✅/❌ |
| O-19 | 평가 체계 변경 이력 관리 | Config 변경 시 버전 기록 | ✅/❌ |
| O-20 | 월간 비용 예측 및 예산 승인 문서 | 경영진 승인 서명 | ✅/❌ |

---

## M.5 체크리스트 자동화 — CI/CD 파이프라인 통합

### M.5.1 GitHub Actions 예시

```yaml
# .github/workflows/pre-deploy-checklist.yml
name: Pre-Deploy Harness Gate Check

on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]

jobs:
  harness-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Agent-Evaluator
        run: pip install agent-evaluator

      - name: Run Golden Dataset Evaluation
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python scripts/run_golden_eval.py
        # scripts/run_golden_eval.py는 골든셋을 실행하고 results/golden.json을 생성

      - name: Gate A+D Check (TCR + SLA)
        run: |
          agent-eval gate results/golden.json \
            --tcr 85 \
            --accuracy 70 \
            --output-json gate_result.json

      - name: Regression Check (Trend)
        run: |
          agent-eval trend results/ \
            --window 5 \
            --fail-on-regression

      - name: Upload Gate Results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: gate-results
          path: |
            gate_result.json
            results/golden.json
```

### M.5.2 골든셋 실행 스크립트 예시

```python
# scripts/run_golden_eval.py
"""
배포 전 골든 데이터셋 평가 스크립트.
CI 환경에서 실행되므로 LLMJudge 샘플링률을 낮게 유지한다.
"""
import json
import sys
from pathlib import Path

from agent_evaluator import PerformanceMonitor, LLMJudge
from agent_evaluator import (
    InstructionConfig, SLAConfig, FaultToleranceConfig,
    ComplianceConfig, ExplainabilityConfig, LoopDetectionConfig,
    LLMJudgeConfig,
)
from agent_evaluator.decorators import agent_eval

# CI에서는 LLMJudge 샘플링 최소화 (비용 절감)
CI_JUDGE_RATE = float(os.getenv("CI_JUDGE_RATE", "0.1"))

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    enable_llm_judge=True,
    judge_model="claude-haiku-4-5-20251001",
    judge_sample_rate=CI_JUDGE_RATE,
)

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(required_keywords=[], fail_on_violation=False),
    sla=SLAConfig(p95_ms=8000),
    fault_tolerance=FaultToleranceConfig(partial_success_threshold=0.75),
    compliance=ComplianceConfig(
        forbidden_data_patterns=["password", "secret", "api_key"],
    ),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    explainability=ExplainabilityConfig(min_reasoning_length=10),
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        sample_rate=CI_JUDGE_RATE,
    ),
)
def production_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 호출
    from my_agent import call_agent
    return call_agent(question)


def main():
    golden_path = Path("golden_dataset/golden_100.json")
    if not golden_path.exists():
        print("ERROR: golden_100.json not found. Run 'agent-eval dataset build' first.")
        sys.exit(1)

    with open(golden_path) as f:
        golden = json.load(f)

    for item in golden:
        production_agent(
            question=item["question"],
            ground_truth=item.get("ground_truth", ""),
        )

    monitor.save_to_file("golden")
    print(f"Evaluated {len(golden)} golden samples. Results saved to results/golden.json")


if __name__ == "__main__":
    main()
```

---

## M.6 배포 당일 런북 (Runbook)

배포 당일 실행할 단계를 시간 순서로 정리한다. 각 단계의 담당자와 완료 시간을 기록한다.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI 에이전트 프로덕션 배포 런북
배포 일시: [YYYY-MM-DD HH:MM]
에이전트: [에이전트 이름 및 버전]
담당자: [이름]   승인자: [이름]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ T-2h ] 사전 점검
  □ 체크리스트 M.2~M.4 완료 확인 (Fail 항목 없음)
  □ 슬랙 채널 #deploy-alert 모니터링 시작
  □ 롤백 버전 아티팩트 접근 가능 확인
  □ 온콜 담당자 대기 확인

[ T-1h ] 스테이징 최종 검증
  □ 스테이징에서 골든셋 100건 실행
  □ agent-eval gate 결과 Pass 확인
  □ 대시보드에서 Gate A–G 점수 기록
    - Gate A (Goal): _____  Gate B (Behavior): _____
    - Gate C (Reliability): _____  Gate D (Performance): _____
    - Gate E (Security): _____  Gate F (Coord): _____
    - Gate G (Observability): _____

[ T-0 ] 배포 실행
  □ 카나리 10% 트래픽 전환
  □ 10분 관찰 — TCR, P95, 보안 위협 알림 없음 확인
  □ 카나리 50% 전환
  □ 30분 관찰 — 위 기준 동일
  □ 100% 전환

[ T+30m ] 배포 후 검증
  □ 프로덕션 첫 100건 결과 확인
  □ agent-eval trend results/ --window 1 실행
  □ AlertEngine 정상 동작 확인
  □ AnomalyDetector 이상 없음 확인

[ T+2h ] 안정화 확인
  □ 대시보드 Gate A–G 점수 스테이징 대비 ±5% 이내
  □ 비용 추이 예측값 ±20% 이내
  □ 배포 완료 공지 (Slack #deploy-announce)

[ 비상 롤백 트리거 조건 ]
  - TCR이 배포 전 대비 10%p 이상 하락
  - P95 지연이 SLA의 150% 초과
  - 보안 위협 Critical 탐지 1건 이상
  - 30분간 오류율 5% 초과

[ 롤백 절차 ]
  1. #deploy-alert에 롤백 시작 공지
  2. 트래픽 이전 버전으로 즉시 전환 (목표: 5분 이내)
  3. 프로덕션에서 golden 100건 재실행 확인
  4. 장애 리뷰 일정 조율 (24시간 이내)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## M.7 배포 후 운영 체크리스트 — 정기 점검

배포 후에도 에이전트 품질은 지속적으로 관리해야 한다. 아래 주기별 점검 항목을 운영 캘린더에 등록한다.

### M.7.1 일간 점검 (자동화 권장)

```bash
# cron: 0 9 * * * (매일 오전 9시)
agent-eval trend results/ \
  --window 7 \
  --fail-on-regression \
  --output-json daily_trend.json
```

| 점검 항목 | 자동화 | 기준 |
|---|---|---|
| 전일 TCR 추세 | ★ | 전주 대비 ±5%p 이내 |
| 평균 지연 시간 | ★ | SLA P95 미만 |
| 일간 LLMJudge 비용 | ★ | 예산 대비 ≤ 110% |
| Critical 보안 위협 발생 건수 | ★ | 0건 |
| AlertEngine 알림 로그 검토 | 수동 | 오탐·미탐 확인 |

### M.7.2 주간 점검

| 점검 항목 | 담당 | 기준 |
|---|---|---|
| Gate A–G 종합 점수 리뷰 | QA 담당자 | 전주 대비 개선 또는 유지 |
| 환각 탐지율 추세 | ML 엔지니어 | 이전 주 대비 ±3%p |
| 골든셋 커버리지 — 실 트래픽 분포 비교 | 데이터 엔지니어 | 이탈 20% 이내 |
| LLMJudge 비용 집계 | 운영 담당 | 예산 대비 ≤ 100% |
| 신규 실패 케이스 → 골든셋 편입 | QA 담당자 | 0건 이상이면 추가 |

### M.7.3 월간 점검

| 점검 항목 | 담당 | 비고 |
|---|---|---|
| 골든셋 전면 검토 및 갱신 | ML 엔지니어 | 분기별 200건 → 100건 필터 |
| LLMJudge vs Native Tracker 상관관계 재분석 | ML 엔지니어 | Appendix L.5.1 방법론 적용 |
| API 키 로테이션 | 보안 담당 | 30–90일 주기 |
| 체크리스트 항목 갱신 | QA 리드 | 신규 실패 패턴 반영 |
| 비용 ROI 재계산 | 제품 담당 | Appendix L.6 프레임워크 적용 |

---

## 요약: 배포 준비 결정 트리

@@HTML_START@@
<div class="mermaid">
flowchart TD
    START([🚀 배포 체크리스트 시작]):::startStyle

    START --> GA

    GA{"Gate A — Goal
TCR ≥ 85% & 정확도 ≥ 70%?"}:::gateStyle

    GA -->|Fail| FA["⚠️ 목표 달성률 개선
프롬프트·골든셋 보강 후 재점검"]:::failStyle
    GA -->|Pass ✓| GE

    GE{"Gate E — Security
보안 경계 점검 통과?"}:::gateStyle

    GE -->|Fail| FE["⛔ 즉시 배포 중단
보안 취약점 수정 후 재점검"]:::failStyle
    GE -->|Pass ✓| GD

    GD{"Gate D — Performance
P95 ≤ SLA & 비용 예산 내?"}:::gateStyle

    GD -->|Fail| FD["⚠️ 지연·비용 최적화
SLAConfig 재조정 후 재점검"]:::failStyle
    GD -->|Pass ✓| M3

    M3{"인프라 체크 — M.3
환경·시크릿·네트워크 Pass?"}:::infraStyle

    M3 -->|Fail| FM3["⚠️ 환경 설정 수정
시크릿·의존성 점검 후 재점검"]:::failStyle
    M3 -->|Pass ✓| M4

    M4{"운영 준비 — M.4
모니터링·알림·롤백 Pass?"}:::infraStyle

    M4 -->|Fail| FM4["⚠️ 문서·알림 규칙 설정
롤백 RunBook 작성 후 재점검"]:::failStyle
    M4 -->|Pass ✓| DONE

    DONE([✅ 배포 승인
카나리 10% → 50% → 100%]):::successStyle

    classDef startStyle fill:#1a237e,stroke:#1a237e,color:#fff,rx:8
    classDef gateStyle fill:#ffffff,stroke:#3949ab,stroke-width:2px,color:#1a237e
    classDef infraStyle fill:#ffffff,stroke:#0277bd,stroke-width:2px,color:#01579b
    classDef failStyle fill:#fff3e0,stroke:#ffcc80,color:#e65100
    classDef successStyle fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20,rx:8
</div>
@@HTML_END@@

**배포 판정 우선순위**: Gate A(목표달성) → Gate D(성능계약) → Gate B(행동무결성) → Gate C·E·F(신뢰성·보안경계·다중에이전트) → Gate G(관측가능성). Gate A가 1순위인 이유는 "기본 기능이 없으면 성능·보안 검증 자체가 무의미"하기 때문이다. Gate D는 SLA와 비용 계약으로 비즈니스 실행 가능성을 좌우하므로 2순위다. Gate E(보안경계)는 opt-in Gate이지만, 외부 사용자에게 노출되는 에이전트라면 **배포를 차단하는 강성 조건**으로 취급해야 한다. **런타임 처리 순서는 별개다**: 실제 에이전트 실행 시에는 Gate E(입력 보안 차단)가 먼저 동작하지만, 이는 배포 체크리스트의 우선순위와 다른 개념이다. 위 결정 트리가 A→E→D 순서로 표시한 것은 "보안 결함이 있으면 성능 측정이 무의미"라는 실용적 관점을 반영한 것이다. 체크리스트를 처음 도입하는 팀이라면 Gate A·D의 핵심 20개 항목(★ 표시)만으로 시작해 점진적으로 확장한다.

---

*이 체크리스트는 Agent-Evaluator SDK v0.8.5 기준으로 작성되었다. 신규 Gate나 Config 추가 시 체크리스트를 함께 갱신한다.*
