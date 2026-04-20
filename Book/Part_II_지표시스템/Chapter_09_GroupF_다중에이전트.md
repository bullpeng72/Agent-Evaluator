# Chapter 9. Group F — 다중에이전트 협업 지표

```
┌────────────────────────────────────────────────────────────┐
│ 🔗 Harness 연결                                             │
│ Group F — Multi-Agent Coordination (다중에이전트 협업)       │
│ Tracker 2종: AgentCoordinationTracker · ToolSelectionTracker│
│ Config 4종: ConsensusConfig · PropagationConfig ·           │
│             AgentRoleConfig · ConflictResolutionConfig      │
│ Gate 판정: HarnessEvaluationGate(report).evaluate()         │
└────────────────────────────────────────────────────────────┘
```

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group F 지표 입력·출력
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group F Config 파라미터 전체 목록
> - **[Evaluator_Examples/02_layer2_agentic_security.py](../../Evaluator_Examples/02_layer2_agentic_security.py)**: AgentCoordinationTracker 실전 예제

> **독자별 읽기 가이드**  
> - **QA 관리자**: §9.1(개요) → §9.4(Config 설정) → §9.5(임계값·Gate 판정) 순서로 읽으면 "에이전트 간 협업 기준을 어떻게 선언할지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §9.2(Tracker 상세) → §9.3(코드 예제) → §9.4(Config 선언) 순서로 읽으면 `ConsensusConfig`, `AgentRoleConfig` 등을 바로 적용할 수 있습니다.

---

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Group F가 없으면 생기는 일                                │
│ 연구자 에이전트가 수집한 핵심 수치("127억, +34.2%")가 분석가  │
│ 에이전트를 거치면서 "약 130억, 30%대 성장"으로 바뀌고, 요약   │
│ 에이전트에서 "실적 양호"로 증발한다. PropagationConfig로      │
│ key_facts를 선언했다면 왜곡 시점을 즉시 탐지할 수 있었다.    │
│                                                              │
│ 참고: 순환 위임(A→B→A) 탐지는 v0.8.2부터 Group B            │
│ DeadlockConfig.check_circular_delegation=True 담당.         │
└────────────────────────────────────────────────────────────┘
```

---

## 9.1 Group F 개요

Group F는 **다중 에이전트 시스템**의 협업 품질을 측정한다. 단일 에이전트 평가는 Group A-E로 충분하지만, 여러 에이전트가 협력하는 시스템은 추가로 다음을 측정해야 한다.

1. **합의**: 여러 에이전트가 같은 결론에 도달하는가? (`ConsensusConfig`)
2. **역할 준수**: 각 에이전트가 자신의 역할 범위 안에서 동작하는가? (`AgentRoleConfig`)
3. **정보 전달**: 에이전트 간 정보가 왜곡 없이 전달되는가? (`PropagationConfig`)

> ℹ️ **DeadlockConfig 위치 변경 (v0.8.2)**: 교착·기아·라이브락 탐지 `DeadlockConfig`는 v0.8.2에서 Group F에서 **Group B(행동무결성)** 로 이동했다. 단일 에이전트에서도 발생하는 행동 무결성 문제이기 때문이다. `DeadlockConfig` 사용 방법은 [Chapter 5 §5.3.6](Chapter_05_GroupB_행동무결성.md)를 참조한다. 단, 본 챕터의 일부 심화 예제에서는 다중에이전트 컨텍스트에서의 `DeadlockConfig` 활용을 계속 다룬다.

### 단일 에이전트 vs 다중 에이전트 평가 범위

| 측면 | 단일 에이전트 | 다중 에이전트 추가 요소 |
|------|------------|---------------------|
| 목표달성 | Group A | Group A × N 에이전트 |
| 보안 | Group E | + 에이전트 간 신뢰 경계 |
| 성능 | Group D | + 에이전트 간 지연 합산 |
| **협업** | — | **Group F 전체** |

---

## 9.2 Tracker 2종 심화

### 9.2.1 AgentCoordinationTracker — 에이전트 간 상호작용

다중 에이전트 시스템에서 에이전트 간 호출·위임·협업 패턴을 기록한다.

**측정 항목:**

| 항목 | 설명 |
|------|------|
| `coordination_score` | 전체 협업 품질 점수 (0~1) |
| `delegation_depth` | 위임 체인 깊이 |
| `parallel_execution_rate` | 병렬 실행 비율 |
| `inter_agent_latency` | 에이전트 간 통신 지연 |
| `network_topology` | 에이전트 간 연결 구조 그래프 |

```python
# 출처: Evaluator_Examples/02_layer2_agentic_security.py, 섹션 4 — AgentCoordinationTracker 멀티에이전트
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor("results/")

# 멀티에이전트 결과 기록
result = create_taskresult(
    task_id="ma_001",
    question="종합 보고서 작성",
    response="보고서 완성",
    execution_time=30.0,
    task_type="planning",
    tool_calls=[
        {"name": "researcher_agent", "args": {"task": "시장 조사"}},
        {"name": "analyst_agent",   "args": {"task": "데이터 분석"}},
        {"name": "writer_agent",    "args": {"task": "보고서 작성"}},
    ],
    extra={
        "agent_interactions": [
            {"from": "orchestrator", "to": "researcher_agent", "type": "delegation"},
            {"from": "orchestrator", "to": "analyst_agent",   "type": "delegation"},
            {"from": "analyst_agent", "to": "writer_agent",   "type": "handoff"},
        ],
        "coordination_score": 0.92,
    },
)
monitor.record_task(result)
```

### 9.2.2 ToolSelectionTracker — 도구 선택 F1

에이전트가 각 태스크에서 올바른 도구를 선택하는지 F1 기반으로 측정한다. "도구를 얼마나 많이 사용했나"가 아닌 "올바른 도구를 선택했나"를 측정한다.

**F1 기반 도구 선택 정확도:**
```
precision = 실제 사용한 도구 중 적절한 도구 비율
recall    = 필요한 도구 중 실제 사용한 도구 비율
F1        = 2 × (precision × recall) / (precision + recall)
```

```python
# 출처: Evaluator_Examples/02_layer2_agentic_security.py, 섹션 4 — ToolSelectionTracker F1
# 올바른 도구 선택 평가
result = create_taskresult(
    task_id="t1",
    question="웹 검색 후 요약",
    response="요약 완료",
    execution_time=5.0,
    task_type="tool_use",
    tool_calls=[
        {"name": "web_search"},  # 필요한 도구
        {"name": "summarize"},   # 필요한 도구
    ],
    extra={
        "expected_tools": ["web_search", "summarize"],  # 기대 도구
    },
)
# F1 = 1.0 (필요한 도구를 정확히 선택)
```

---

## 9.3 Config 4종 레퍼런스

> ℹ️ **v0.8.2 변경**: `DeadlockConfig`가 Group F에서 Group B로 이동했다. Group F Config는 4종(ConsensusConfig, PropagationConfig, AgentRoleConfig, ConflictResolutionConfig)이다.

### 9.3.1 ConsensusConfig — 다중 에이전트 합의

여러 에이전트가 같은 질문에 대해 답변할 때 합의가 이루어지는지 측정한다. `batch_eval`과 함께 사용할 때 가장 효과적이다.

```python
from agent_evaluator import ConsensusConfig

ConsensusConfig(
    consensus_method="majority",          # "majority"|"weighted"|"unanimity"
    agent_weights={                        # 에이전트별 투표 가중치
        "expert_agent": 3.0,
        "general_agent": 1.0,
        "junior_agent": 0.5,
    },
    similarity_threshold=0.7,             # 합의로 인정할 유사도
    select_consensus_response=False,      # True: 합의 응답을 최종 선택
)
```

**사용 예시 — 앙상블 에이전트:**

```python
from agent_evaluator import ConsensusConfig
from agent_evaluator.decorators import batch_eval

@batch_eval(
    monitor,
    task_type="multi_agent",
    consensus=ConsensusConfig(
        consensus_method="weighted",
        agent_weights={"expert": 3.0, "general": 1.0},
        similarity_threshold=0.75,
        select_consensus_response=True,
    ),
)
def ensemble_agent(questions: list, ground_truths: list = None) -> list:
    # 여러 에이전트가 각 질문에 답변
    return [
        {"expert": expert_agent.run(q), "general": general_agent.run(q)}
        for q in questions
    ]
```

### 9.3.2 PropagationConfig — 정보 전파 충실도

선행 에이전트가 수집한 핵심 정보가 후속 에이전트로 왜곡 없이 전달되는지 측정한다.

```python
from agent_evaluator import PropagationConfig

PropagationConfig(
    source_agent="researcher",        # 정보 출처 에이전트
    key_facts=[                        # 반드시 전달되어야 할 핵심 사실
        "마감: 2026-05-01",
        "예산: 5,000만 원",
        "담당자: 김민준",
    ],
    check_in_response=True,            # 응답 텍스트에서 사실 확인
    check_in_tool_calls=False,         # 도구 호출 인자에서도 확인
    similarity_threshold=0.7,          # 사실 일치 유사도 임계값
    penalize_distortion=True,          # 사실 왜곡 시 패널티
)
```

**사용 예시 — 리서치-라이터 파이프라인:**

```python
@agent_eval(
    monitor,
    task_type="planning",
    propagation=PropagationConfig(
        source_agent="researcher",
        key_facts=critical_facts,       # 연구자가 발견한 핵심 사실
        penalize_distortion=True,
    ),
)
def writer_agent(question: str, ground_truth: str = "") -> str:
    # 작가 에이전트 — 연구자의 사실을 기반으로 작성해야 함
    return writer.run(question)
```

### 9.3.3 AgentRoleConfig — 에이전트 역할 준수

멀티에이전트 시스템에서 각 에이전트가 자신의 역할 범위 안에서 도구와 행동을 선택하는지 측정한다.

```python
from agent_evaluator import AgentRoleConfig

AgentRoleConfig(
    role_name="researcher",              # 에이전트 역할 이름
    allowed_tools=["search", "read_doc", "extract_data"],  # 역할에 허용된 도구
    forbidden_tools=["write", "delete", "send_email"],      # 역할에 금지된 도구
    allowed_action_keywords=["검색", "조회", "분석"],        # 허용 행동 키워드
    forbidden_action_keywords=["삭제", "수정", "발송"],       # 금지 행동 키워드
    check_tool_role_alignment=True,      # 도구-역할 일치 확인
    role_violation_penalty=0.3,          # 역할 위반당 패널티
)
```

**멀티에이전트 시스템 역할 설계 예시:**

```python
# 3개 역할 × AgentRoleConfig

researcher_role = AgentRoleConfig(
    role_name="researcher",
    allowed_tools=["web_search", "read_document", "extract_data"],
    forbidden_tools=["write_report", "send_email"],
)

analyst_role = AgentRoleConfig(
    role_name="analyst",
    allowed_tools=["compute_statistics", "visualize", "compare_data"],
    forbidden_tools=["web_search", "send_email"],
)

writer_role = AgentRoleConfig(
    role_name="writer",
    allowed_tools=["write_report", "format_document", "review_draft"],
    forbidden_tools=["web_search", "delete_file"],
)
```

### 9.3.4 ConflictResolutionConfig — 충돌 해결 품질

에이전트 간 의견 충돌이 발생했을 때 적절하게 해결하는지 측정한다. 충돌을 방치하거나, 무시하거나, 에스컬레이션 없이 진행하는 것을 탐지한다.

```python
from agent_evaluator import ConflictResolutionConfig

ConflictResolutionConfig(
    conflict_markers=[               # 충돌을 나타내는 마커
        "disagree", "conflict", "contradiction",
        "반대", "충돌", "모순",
    ],
    resolution_markers=[             # 해결을 나타내는 마커
        "resolved", "consensus", "agreed", "decided",
        "해결", "합의", "결정",
    ],
    check_resolution_quality=True,   # 해결 품질 채점 여부
    require_explanation=False,       # 해결 근거 설명 요구
    unresolved_penalty=0.5,          # 미해결 충돌당 패널티
    expect_escalation_on_fail=True,  # 해결 실패 시 에스컬레이션 기대
)
```

---

## 9.4 조합 패턴 — 다중에이전트 시스템 유형별 구성

### 패턴 1 — 오케스트레이터-워커 구조

```python
from agent_evaluator import (
    DeadlockConfig,
    AgentRoleConfig,
    PropagationConfig,
    SLAConfig,
)
from agent_evaluator.decorators import agent_eval

# 오케스트레이터 에이전트
@agent_eval(
    monitor,
    task_type="planning",
    deadlock=DeadlockConfig(
        check_circular_delegation=True,
        max_delegation_depth=5,
    ),
    sla=SLAConfig(p95_ms=60000),   # 전체 파이프라인 60초 SLA
)
def orchestrator(question: str, ground_truth: str = "") -> str:
    return orchestrator_agent.run(question)

# 워커 에이전트
@agent_eval(
    monitor,
    task_type="tool_use",
    agent_role=AgentRoleConfig(
        role_name="worker",
        allowed_tools=["search", "compute"],
        role_violation_penalty=0.4,
    ),
)
def worker(question: str, ground_truth: str = "") -> str:
    return worker_agent.run(question)
```

### 패턴 2 — 앙상블 에이전트 (합의 기반)

```python
from agent_evaluator import (
    ConsensusConfig,
    ConflictResolutionConfig,
)
from agent_evaluator.decorators import batch_eval

@batch_eval(
    monitor,
    task_type="multi_agent",
    consensus=ConsensusConfig(
        consensus_method="weighted",
        agent_weights={"domain_expert": 4.0, "general": 1.0},
        similarity_threshold=0.75,
    ),
    conflict_resolution=ConflictResolutionConfig(
        check_resolution_quality=True,
        expect_escalation_on_fail=True,
        unresolved_penalty=0.6,
    ),
)
def ensemble(questions: list, ground_truths: list = None) -> list:
    return run_ensemble(questions)
```

---

## 9.5 이 챕터의 핵심 요약

| 지표/Config | 역할 | 핵심 파라미터 |
|------------|------|-------------|
| `AgentCoordinationTracker` | 에이전트 간 상호작용 추적 | `coordination_score`, `delegation_depth` |
| `ToolSelectionTracker` | 도구 선택 F1 측정 | F1 기반 `precision`, `recall` |
| `ConsensusConfig` | 다중 에이전트 합의 기준 | `consensus_method`, `agent_weights`, `similarity_threshold` |
| `PropagationConfig` | 에이전트 간 정보 전달 기준 | `key_facts`, `penalize_distortion` |
| `AgentRoleConfig` | 에이전트 역할 준수 기준 | `role_name`, `allowed_tools`, `forbidden_tools` |
| `ConflictResolutionConfig` | 에이전트 간 충돌 해결 기준 | `unresolved_penalty`, `expect_escalation_on_fail` |

> ℹ️ **DeadlockConfig**: v0.8.2에서 Group B(행동무결성)로 이동. [Chapter 5 §5.3.6](Chapter_05_GroupB_행동무결성.md) 참조.

---

## 9.6 다중에이전트 실패 심층 분석 — 4가지 핵심 장애 패턴

현장에서 반복적으로 나타나는 4가지 다중에이전트 장애 패턴을 깊이 분석한다. §9.1~§9.5가 "어떻게 측정하는가"를 다뤘다면, §9.6은 "무엇이 왜 실패하는가"를 다룬다. 측정 지표가 적신호를 보낼 때 근본 원인을 진단하는 데 활용한다.

### 9.6.1 정보 왜곡 연쇄 (Information Distortion Cascade)

에이전트 체인에서 정보가 전달될 때마다 원본에서 멀어지는 현상이다. 마치 전화 게임처럼, 각 에이전트가 앞 에이전트의 출력을 요약·해석·재표현하는 과정에서 오류가 누적된다.

**구체적 시나리오**: 4단계 파이프라인(연구자→분석가→요약자→작가)에서 핵심 수치가 소실·왜곡되는 과정.

```
연구자 원본:  "2025년 3분기 영업이익 127억 원, 전년 동기 대비 +34.2%"
분석가 전달:  "3분기 영업이익 약 130억 원, 전년 대비 30% 이상 성장"   ← 수치 반올림
요약자 전달:  "3분기 영업실적이 크게 개선됨"                          ← 수치 소실
작가 최종:    "최근 실적이 양호한 편"                                  ← 핵심 정보 증발
```

**왜 발생하는가**: 세 가지 메커니즘이 복합적으로 작용한다.
1. **컨텍스트 압축 편향**: LLM은 긴 컨텍스트를 받으면 수치보다 서술적 패턴을 우선 압축한다.
2. **요약 편향**: 각 에이전트의 프롬프트가 "핵심을 간결히 전달"을 지시하면 수치가 희생된다.
3. **추론 오류 누적**: 단계별 소량의 추론 오류가 복리로 증폭된다. n단계 체인에서 각 단계 오류율 ε이라면 최종 오류율은 `1 - (1-ε)^n`에 수렴한다.

**측정 방법**: `PropagationConfig`의 `key_facts`로 핵심 사실을 선언하고 각 단계에서 유실률을 계산한다.

```
distortion_rate = 1 - |전달된_핵심_사실 ∩ 원본_핵심_사실| / |원본_핵심_사실|
```

**탐지 코드**:

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator import PropagationConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

# 연구자가 발견한 핵심 사실 목록 (PropagationConfig에 선언)
CRITICAL_FACTS = [
    "2025년 3분기",
    "127억",
    "34.2%",
    "영업이익",
]

# 분석가 에이전트 — 연구자 출력을 입력으로 받아 처리
@agent_eval(
    monitor,
    task_type="data_analysis",
    propagation=PropagationConfig(
        source_agent="researcher",
        key_facts=CRITICAL_FACTS,
        check_in_response=True,
        similarity_threshold=0.7,
        penalize_distortion=True,
    ),
)
def analyst_agent(question: str, ground_truth: str = "") -> str:
    return analyst.run(question)

# 요약자 에이전트 — 분석가 출력을 다시 PropagationConfig로 검사
@agent_eval(
    monitor,
    task_type="document_creation",
    propagation=PropagationConfig(
        source_agent="analyst",
        key_facts=CRITICAL_FACTS,
        check_in_response=True,
        similarity_threshold=0.6,   # 요약 단계이므로 임계값 완화
        penalize_distortion=True,
    ),
)
def summarizer_agent(question: str, ground_truth: str = "") -> str:
    return summarizer.run(question)

# 평가 실행 후 정보 유실률 확인
report = monitor.generate_report()
propagation_scores = report.harness_results.get("group_f", {}).get("propagation", {})
print(f"분석가 정보 유실률: {1 - propagation_scores.get('analyst', 1.0):.1%}")
print(f"요약자 정보 유실률: {1 - propagation_scores.get('summarizer', 1.0):.1%}")
```

**임계값 가이드**:

| distortion_rate | 상태 | Gate F 영향 | 권장 조치 |
|----------------|------|------------|---------|
| 0 ~ 10% | 정상 | PASS 기여 | 현행 유지 |
| 10 ~ 25% | 경고 | WARN 발생 | 프롬프트 개선, key_facts 명시적 전달 지시 추가 |
| 25% 이상 | 위험 | Gate F FAIL | 에이전트 간 구조화된 데이터(JSON) 전달로 전환 |

**근본 해결책**: 자연어 전달 대신 구조화 데이터 핸드오프. 각 에이전트가 응답 외에 `metadata.key_facts` 딕셔너리를 명시적으로 반환하고 후속 에이전트가 이를 컨텍스트로 주입한다.

---

### 9.6.2 합의 붕괴와 소수의견 소실 (Consensus Collapse)

앙상블 에이전트 시스템에서 잘못된 합의가 형성되거나 올바른 소수의견이 다수결에 의해 무시되는 현상이다. 민주적 투표가 오히려 정확도를 떨어뜨리는 역설적 상황이 발생한다.

**Byzantine Fault Tolerance 관점**: 분산 시스템 이론에서 f개의 오류(악의적 또는 결함) 노드를 허용하려면 최소 3f+1개의 전체 노드가 필요하다.

```
n_agents ≥ 3f + 1

여기서:
  n_agents = 전체 에이전트 수
  f        = 허용 가능한 오류/환각 에이전트 수

실용 공식:
  f = floor((n_agents - 1) / 3)

예시:
  3개 에이전트 → f = 0  (단 1개의 오류 에이전트도 합의를 오염시킬 수 있음)
  4개 에이전트 → f = 1  (1개 오류 에이전트 허용)
  7개 에이전트 → f = 2  (2개 오류 에이전트 허용)
```

**Agent-Evaluator 대응**: `ConsensusConfig`의 `weighted` 방식과 `similarity_threshold`로 BFT 원리를 실용적으로 구현한다.

**위험 시나리오 1 — 다수가 동일한 환각을 공유할 때**:

```
에이전트 A: "이 약물의 치사량은 500mg이다."  (환각)
에이전트 B: "이 약물의 치사량은 500mg 정도다."  (환각, A와 유사)
에이전트 C: "이 약물의 치사량은 공개 데이터 없음."  (정확한 답변)

다수결 합의 → 500mg 채택  (올바른 소수의견 소실)
```

**위험 시나리오 2 — weighted voting이 환각을 억제하는 성공 사례**:

```python
from agent_evaluator import ConsensusConfig
from agent_evaluator.decorators import batch_eval

# 도메인 전문가에게 높은 가중치 부여 → 환각 억제
@batch_eval(
    monitor,
    task_type="multi_agent",
    consensus=ConsensusConfig(
        consensus_method="weighted",
        agent_weights={
            "medical_specialist": 5.0,  # 검증된 전문가 에이전트
            "general_llm_a": 1.0,
            "general_llm_b": 1.0,
        },
        similarity_threshold=0.75,
        select_consensus_response=True,  # 합의 응답을 최종 채택
    ),
)
def medical_ensemble(questions: list, ground_truths: list = None) -> list:
    return [
        {
            "medical_specialist": specialist.run(q),
            "general_llm_a": llm_a.run(q),
            "general_llm_b": llm_b.run(q),
        }
        for q in questions
    ]
```

**소수의견 보존 전략**: `ConsensusConfig`로 합의를 구성하되, 합의에서 이탈한 에이전트의 응답을 `extra` 필드에 보존하고 인간 검토 큐에 추가한다. 고위험 도메인(의료·법률·금융)에서는 소수의견 이탈이 오히려 더 정확한 신호일 수 있다.

---

### 9.6.3 위임 실패 분류학 (Delegation Failure Taxonomy)

단순 순환 교착(A→B→A)을 넘어선 4가지 위임 실패 유형을 체계화한다. 각 유형은 발생 조건과 탐지 방법이 다르므로 구분해서 대응해야 한다.

| 유형 | 설명 | 탐지 조건 | Agent-Evaluator 대응 |
|------|------|---------|---------------------|
| **Direct Deadlock** | A→B→A 또는 A→B→C→A 직접 순환 위임 | delegation 그래프에서 사이클 탐지 | `DeadlockConfig(check_circular_delegation=True)` |
| **Resource Deadlock** | 에이전트들이 공유 도구(DB, API)를 동시에 점유하며 서로 대기 | tool call 큐 대기 시간 임계값 초과 | `ToolParameterSafetyConfig` + `SLAConfig` |
| **Livelock** | 에이전트들이 교착은 아니지만 진전 없는 반복 전환 (A가 B에게, B가 A에게 재위임 반복) | N 윈도우 내 동일 에이전트 쌍의 위임 패턴 반복 | `DeadlockConfig(check_livelock=True, livelock_window=6)` |
| **Starvation Deadlock** | 낮은 우선순위 에이전트가 계속 대기하다가 타임아웃 | 동일 에이전트 3회+ 연속 대기 감지 | `DeadlockConfig(check_starvation=True, starvation_threshold=3)` |

**탐지 알고리즘 — Wait-for Graph 기반 순환 탐지**:

에이전트 위임 관계를 방향 그래프로 모델링하면, 교착은 그래프의 사이클로 표현된다. Deep-First Search(DFS)로 사이클을 O(V+E) 시간에 탐지할 수 있다.

```
그래프 G = (V, E)
  V = 에이전트 집합 {A, B, C, ...}
  E = 위임 관계 {(A→B): A가 B에게 위임}

사이클 존재 ⟺ Direct Deadlock 발생

DFS 방문 상태:
  WHITE = 미방문
  GRAY  = 현재 탐색 중 (스택에 있음)
  BLACK = 탐색 완료

GRAY 노드로 역방향 에지 발견 시 → 사이클 확정
```

```python
# Agent-Evaluator에서의 실용적 탐지
from agent_evaluator import (
    DeadlockConfig,
    ToolParameterSafetyConfig,
)
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    task_type="planning",
    deadlock=DeadlockConfig(
        check_circular_delegation=True,   # Direct Deadlock
        check_starvation=True,            # Starvation
        starvation_threshold=3,
        check_livelock=True,              # Livelock
        livelock_window=8,                # 8개 위임 이내 반복 패턴 탐지
        max_delegation_depth=5,           # Resource Deadlock 간접 방지
    ),
)
def orchestrator_agent(question: str, ground_truth: str = "") -> str:
    return orchestrator.run(question)
```

**각 유형별 복구 전략**:
- **Direct Deadlock**: 감지 즉시 위임 체인 강제 중단 → 오케스트레이터에 예외 반환
- **Resource Deadlock**: 타임아웃 + 지수 백오프 재시도 (Group C `FaultToleranceConfig`와 연계)
- **Livelock**: 외부 개입 트리거 — 인간 검토 또는 대체 에이전트 투입
- **Starvation**: 우선순위 역전(priority inversion) 방지 — 오래 대기한 에이전트 우선 처리

---

### 9.6.4 신뢰 경계 위반 (Trust Boundary Violation)

멀티에이전트 시스템에서 에이전트가 다른 에이전트의 출력을 검증 없이 ground truth처럼 처리해 발생하는 보안·품질 문제다. 단일 에이전트의 환각보다 훨씬 빠르게 오류가 사실화된다.

**문제 메커니즘**:

```
[정상 단일 에이전트]
사용자 질문 → 에이전트 A → 응답 (환각 가능성 있음)

[신뢰 경계 위반 멀티에이전트]
사용자 질문 → 에이전트 A (환각 생성) → 에이전트 B가 A의 출력을 사실로 수용
            → 에이전트 C가 B의 출력을 사실로 수용
            → 환각이 검증된 사실로 굳어짐
```

**실제 위험 사례**: 연구 에이전트가 존재하지 않는 논문을 인용하고, 분석 에이전트가 이 인용을 사실로 받아들여 추가 분석을 수행한 뒤, 작가 에이전트가 보고서에 허위 인용을 포함시킨다. 최종 사용자는 인용 형식이 정확해 보이므로 오류를 발견하기 어렵다.

**해결 — PropagationConfig와 ThreatSeverityConfig 결합**:

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator import (
    PropagationConfig,
    ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    "results/",
    enable_hallucination_detection=True,  # 환각 탐지 활성화
    enable_security_metrics=True,         # 보안 지표 활성화
)

# 신뢰 등급 선언: 검증된 에이전트 vs 미검증 에이전트
TRUSTED_AGENTS   = ["verified_search", "internal_db"]
UNTRUSTED_AGENTS = ["external_llm_a", "external_llm_b", "user_provided_agent"]

# 미검증 에이전트의 출력을 처리하는 통합 에이전트
@agent_eval(
    monitor,
    task_type="information_retrieval",
    propagation=PropagationConfig(
        source_agent="external_llm_a",
        key_facts=[],             # 사실 목록은 런타임에 동적으로 주입
        check_in_response=True,
        similarity_threshold=0.8, # 미검증 소스는 임계값을 높게 설정
        penalize_distortion=True,
    ),
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,    # 고위험 위협 탐지 시 즉시 차단
        warn_score=3.0,           # 미검증 소스는 엄격한 경고 임계값
        fail_score=7.0,
    ),
)
def integration_agent(question: str, ground_truth: str = "") -> str:
    # 미검증 에이전트 출력을 수용하기 전에 자체 검증 수행
    external_output = external_llm_a.run(question)
    verified_output = verify_against_trusted_source(external_output)
    return verified_output

def verify_against_trusted_source(candidate: str) -> str:
    """검증된 내부 DB와 대조해 외부 에이전트 출력의 사실성 확인"""
    db_result = internal_db.query(candidate)
    if db_result.confidence < 0.7:
        return f"[검증 불가] {candidate}"
    return candidate
```

**에이전트 간 신뢰 계층 설계 원칙**:

| 신뢰 등급 | 설명 | 출력 처리 방식 |
|---------|------|-------------|
| 완전 신뢰 | 내부 검증된 도구·DB | 직접 사용 |
| 조건부 신뢰 | 외부 LLM, 파트너 API | 핵심 사실 교차검증 후 사용 |
| 비신뢰 | 사용자 제공 에이전트, 외부 크롤링 | 독립 검증 후에만 파이프라인에 진입 허용 |

---

## 9.7 Credit Assignment — 다중에이전트 기여도 분석

단일 에이전트 평가는 귀속이 명확하다: 에이전트 A가 실패하면 A의 책임이다. 다중에이전트 시스템에서는 "누가 최종 품질을 결정했는가"를 추적해야 한다. 이 문제는 강화학습의 시간적 기여도 문제(Temporal Credit Assignment Problem)와 구조적으로 동일하다.

### 9.7.1 기여도 귀속 문제 (Credit Assignment Problem)

4단계 파이프라인(연구자→분석가→검토자→작가)에서 최종 응답 품질이 낮을 때 원인 에이전트를 특정하기가 어렵다.

```
최종 품질 점수: 0.42  (Gate A FAIL 수준)

가능한 원인:
  1. 연구자의 불량 검색 결과 → 잘못된 정보 주입
  2. 분석가의 오류 해석    → 올바른 데이터를 잘못 분석
  3. 검토자의 오류 미탐지  → 오류를 통과시킴
  4. 작가의 부실한 통합    → 좋은 재료를 나쁘게 조합
```

**수학적 모델 — Shapley Value 기반 기여도 계산**:

협력 게임 이론의 Shapley Value는 각 플레이어(에이전트)의 평균 한계 기여도를 공정하게 분배하는 유일한 방법이다 (Shapley 1953, *A Value for n-Person Games*, Princeton University Press).

```
φᵢ(v) = Σ      [|S|!(n-|S|-1)!/n!] × [v(S∪{i}) - v(S)]
         S⊆N\{i}

여기서:
  φᵢ        = 에이전트 i의 Shapley 기여도
  v(S)       = 에이전트 집합 S만으로 달성한 평가 점수 (연합 가치)
  v(S∪{i})  = 에이전트 i를 추가했을 때의 점수 상승분
  n          = 전체 에이전트 수
  N          = 전체 에이전트 집합

직관적 해석:
  에이전트 i를 포함한 모든 가능한 에이전트 조합에서
  i를 추가했을 때 발생하는 성능 향상의 가중 평균
```

**실용적 근사 — 제거 기반 기여도**:

Shapley Value는 n개 에이전트에 대해 2^n개 조합을 평가해야 하므로 실용적으로는 각 에이전트를 순차적으로 제외했을 때 성능 하락을 측정해 기여도를 근사한다.

```python
# 제거 기반 기여도 근사
baseline_score = evaluate_full_pipeline(question, ground_truth)

contributions = {}
for agent_name in ["researcher", "analyst", "reviewer", "writer"]:
    # 해당 에이전트를 제외한 파이프라인 점수
    ablated_score = evaluate_pipeline_without(agent_name, question, ground_truth)
    contributions[agent_name] = baseline_score - ablated_score
    # 양수 = 해당 에이전트가 기여, 음수 = 해당 에이전트가 품질을 해침

print("기여도 분석:", contributions)
# 출력 예: {'researcher': 0.18, 'analyst': 0.05, 'reviewer': -0.03, 'writer': 0.22}
# → reviewer가 오히려 품질을 낮추고 있음 — 집중 개선 대상
```

### 9.7.2 Agent-Evaluator에서의 기여도 추적

각 에이전트를 별도 `PerformanceMonitor`로 독립 측정하면 에이전트별 품질 분리가 가능하다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 에이전트별 독립 모니터 — 기여도 분리의 핵심
monitors = {
    "researcher": PerformanceMonitor("results/researcher/"),
    "analyst":    PerformanceMonitor("results/analyst/"),
    "reviewer":   PerformanceMonitor("results/reviewer/"),
    "writer":     PerformanceMonitor("results/writer/"),
}

# 각 에이전트를 독립 @agent_eval로 감싸 개별 측정
@agent_eval(monitors["researcher"], task_type="information_retrieval")
def researcher_agent(question: str, ground_truth: str = "") -> str:
    return researcher.run(question)

@agent_eval(monitors["analyst"], task_type="data_analysis")
def analyst_agent(question: str, ground_truth: str = "") -> str:
    # 실제로는 researcher_agent의 출력을 입력으로 받음
    return analyst.run(question)

@agent_eval(monitors["reviewer"], task_type="qa")
def reviewer_agent(question: str, ground_truth: str = "") -> str:
    return reviewer.run(question)

@agent_eval(monitors["writer"], task_type="document_creation")
def writer_agent(question: str, ground_truth: str = "") -> str:
    return writer.run(question)


def compute_agent_contributions(test_cases: list) -> dict:
    """각 에이전트의 평가 보고서에서 기여도 계산"""
    # 전체 파이프라인 실행
    for tc in test_cases:
        q, gt = tc["question"], tc["ground_truth"]
        research_result = researcher_agent(q, ground_truth=gt)
        analysis_result = analyst_agent(research_result, ground_truth=gt)
        review_result   = reviewer_agent(analysis_result, ground_truth=gt)
        writer_agent(review_result, ground_truth=gt)

    # 에이전트별 평균 품질 점수 추출
    scores = {}
    for name, monitor in monitors.items():
        report = monitor.generate_report()
        scores[name] = {
            "accuracy":    report.accuracy_score,
            "completion":  report.task_completion_rate,
            "quality":     report.avg_quality_score,
        }
        monitor.save_to_file(f"{name}_contribution")

    return scores


# 실행 결과 예시 해석
contributions = compute_agent_contributions(test_dataset)
for agent_name, score in contributions.items():
    print(
        f"{agent_name:12s} | "
        f"정확도: {score['accuracy']:.1%} | "
        f"완료율: {score['completion']:.1%} | "
        f"품질: {score['quality']:.1%}"
    )
```

**출력 해석 예시**:
```
researcher   | 정확도: 82.3% | 완료율: 95.0% | 품질: 0.78
analyst      | 정확도: 74.1% | 완료율: 91.0% | 품질: 0.71
reviewer     | 정확도: 61.2% | 완료율: 88.0% | 품질: 0.58  ← 병목
writer       | 정확도: 79.8% | 완료율: 94.0% | 품질: 0.76
```

위 결과에서 `reviewer`가 파이프라인의 병목임을 즉시 파악할 수 있다.

### 9.7.3 기여도 기반 품질 개선 우선순위

기여도 분석 결과를 개선 우선순위 결정에 어떻게 반영하는지를 3가지 전략으로 정리한다.

**전략 1 — 제거 vs 강화**: 기여도 낮은 에이전트가 비용만 높이고 품질에 기여하지 않으면 제거를 검토한다. 기여도 높고 품질 낮은 에이전트는 파이프라인에서 중요하므로 집중 개선한다.

```
기여도 매트릭스:
              기여도 높음        기여도 낮음
품질 높음  │ 핵심 자산 유지    │ 역할 재검토 (과잉 에이전트?)
품질 낮음  │ 집중 개선 대상   │ 제거 또는 교체
```

**전략 2 — 의존성 체인 분석**: 에이전트 B가 A의 출력에 의존한다면, A의 품질 저하는 B의 품질 저하로 연쇄된다. A를 개선하면 B와 B에 의존하는 모든 후속 에이전트가 동시에 이익을 얻는다. 의존성 그래프의 상류(upstream) 에이전트 개선이 ROI가 가장 높다.

**전략 3 — 비용-기여도 비율**: 각 에이전트의 토큰 사용량(비용)을 `TokenEconomyTracker`로 측정하고 기여도와 나눠 비용 효율을 산출한다. 비용-기여도 비율이 낮은 에이전트는 더 경량인 모델로 교체를 검토한다.

```python
# 비용-기여도 비율 계산
for name, monitor in monitors.items():
    report = monitor.generate_report()
    token_cost  = report.total_token_cost   # TokenEconomyTracker 추적 비용
    quality     = report.avg_quality_score  # 에이전트 품질 기여도
    efficiency  = quality / max(token_cost, 1e-6)
    print(f"{name:12s} | 비용: ${token_cost:.4f} | 품질: {quality:.2f} | 효율: {efficiency:.4f}")
```

---

## 9.8 실전 다중에이전트 시스템 Gate F 운영 가이드

§9.6~§9.7의 이론을 바탕으로 실제 프로덕션 다중에이전트 시스템에서 Gate F를 어떻게 구성하고 운영하는지 실용적 가이드를 제공한다.

### 9.8.1 에이전트 토폴로지별 Gate F 구성 권고

다중에이전트 시스템의 구조(토폴로지)에 따라 핵심 위험과 필요한 Config가 다르다.

| 토폴로지 | 설명 | 핵심 위험 | 권장 Config 조합 |
|---------|------|---------|---------------|
| **선형 파이프라인** | A→B→C 순차 실행 | 정보 왜곡 누적, 상류 장애 전파 | `PropagationConfig` + `FaultToleranceConfig` |
| **오케스트레이터-워커** | 1 오케스트레이터 + N 워커 | 교착, 워커 역할 이탈, 오케스트레이터 SPOF | `DeadlockConfig` + `AgentRoleConfig` |
| **앙상블 (투표)** | N개 병렬 + 합의 단계 | 잘못된 합의, 소수의견 소실, BFT 위반 | `ConsensusConfig` + `ConflictResolutionConfig` |
| **계층 위임** | 다단계 서브에이전트 재귀 위임 | 위임 폭주, 비용 폭발, Starvation | `DeadlockConfig(max_depth=5)` + `SLAConfig` + `ResourceBudgetConfig` |
| **피어-투-피어** | 에이전트 간 자유 통신 | 신뢰 경계 위반, 순환 루프, 무질서한 역할 | `AgentRoleConfig` + `ThreatSeverityConfig` + `DeadlockConfig` |

**선형 파이프라인 예시**:

```python
# 3단계 선형 파이프라인 — PropagationConfig 체인 설정
from agent_evaluator import PropagationConfig, FaultToleranceConfig
from agent_evaluator.decorators import agent_eval

PIPELINE_FACTS = ["핵심_수치_1", "핵심_수치_2", "마감_날짜"]

@agent_eval(
    monitors["analyst"],
    task_type="data_analysis",
    propagation=PropagationConfig(
        source_agent="researcher",
        key_facts=PIPELINE_FACTS,
        penalize_distortion=True,
        similarity_threshold=0.75,
    ),
    fault_tolerance=FaultToleranceConfig(
        recovery_rate_threshold=0.85,  # 85% 이상 복구율 요구
    ),
)
def analyst_in_pipeline(question: str, ground_truth: str = "") -> str:
    return analyst.run(question)
```

**오케스트레이터-워커 예시**:

```python
# 오케스트레이터-워커 — DeadlockConfig + AgentRoleConfig 필수
from agent_evaluator import DeadlockConfig, AgentRoleConfig
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitors["orchestrator"],
    task_type="planning",
    deadlock=DeadlockConfig(
        check_circular_delegation=True,
        check_starvation=True,
        starvation_threshold=3,
        max_delegation_depth=5,
    ),
)
def orchestrator(question: str, ground_truth: str = "") -> str:
    return orchestrator_llm.run(question)

@agent_eval(
    monitors["worker_a"],
    task_type="tool_use",
    agent_role=AgentRoleConfig(
        role_name="data_worker",
        allowed_tools=["query_db", "compute_stats"],
        forbidden_tools=["send_email", "write_file", "delete_record"],
        role_violation_penalty=0.4,
    ),
)
def worker_a(question: str, ground_truth: str = "") -> str:
    return worker_llm_a.run(question)
```

### 9.8.2 Gate F 점수 해석 가이드

Agent-Evaluator가 집계하는 Gate F 종합 점수의 범위별 의미와 권장 조치다.

| 점수 범위 | 상태 | 의미 | 권장 조치 |
|---------|------|------|---------|
| 0.90 이상 | PASS | 협업 품질 우수 — 프로덕션 배포 적합 | 현행 구성 유지, 주기적 재평가 |
| 0.75 ~ 0.90 | WARN | 간헐적 협업 이슈 발생 — 모니터링 강화 필요 | `PropagationConfig` 강화, 오류 에이전트 추적 |
| 0.60 ~ 0.75 | CAUTION | 지속적 협업 문제 — 배포 전 개선 권고 | 에이전트 역할 재설계, 기여도 분석 실행 |
| 0.60 미만 | FAIL | 협업 붕괴 — 배포 차단 | 아키텍처 재검토, 에이전트 수 축소 검토 |

**Gate F 점수 산출 방식**: 4개 Config에서 측정한 개별 점수의 가중 평균.

```
Gate_F_score = (
    w_consensus   × consensus_score   +   # 합의율 (0~1)
    w_propagation × propagation_score +   # 정보 전달 충실도 (0~1)
    w_role        × role_score        +   # 역할 준수율 (0~1)
    w_conflict    × conflict_score        # 충돌 해결률 (0~1)
) / (w_consensus + w_propagation + w_role + w_conflict)

기본 가중치: consensus=2.5, propagation=2.5, role=3.0, conflict=2.0
# 교착(DeadlockConfig)은 v0.8.2부터 Group B에서 별도 집계됨
```

**CI/CD 파이프라인에서 Gate F 자동 게이팅**:

```bash
# Gate F FAIL 시 배포 차단
agent-eval gate result.json \
  --tcr 85 \
  --accuracy 70 \
  --gate-f-threshold 0.75  # Gate F 점수 0.75 미만 시 exit 1
```

### 9.8.3 Gate F 최소 구성 vs 풀 구성

팀 규모와 시스템 복잡도에 따라 Gate F 구성 수준을 선택한다.

```python
from agent_evaluator import (
    DeadlockConfig,
    ConsensusConfig,
    PropagationConfig,
    AgentRoleConfig,
    ConflictResolutionConfig,
)

# ── 최소 구성 — 모든 다중에이전트에 기본 적용 (추가 비용 없음) ──────────────
# 교착과 역할 이탈만 탐지. 대부분의 심각한 장애를 방지한다.
minimal_group_f = [
    DeadlockConfig(
        check_circular_delegation=True,
        max_delegation_depth=8,
    ),
    AgentRoleConfig(
        role_name="agent",
        allowed_tools=APPROVED_TOOLS,
    ),
]

# ── 표준 구성 — 3개 이상 에이전트가 협업하는 시스템 ─────────────────────────
# 정보 전달 충실도와 합의 품질까지 포함.
standard_group_f = [
    DeadlockConfig(
        check_circular_delegation=True,
        check_starvation=True,
        starvation_threshold=3,
        max_delegation_depth=6,
    ),
    PropagationConfig(
        source_agent="upstream_agent",
        key_facts=CRITICAL_FACTS,
        penalize_distortion=True,
    ),
    AgentRoleConfig(
        role_name="agent",
        allowed_tools=APPROVED_TOOLS,
        forbidden_tools=FORBIDDEN_TOOLS,
        role_violation_penalty=0.3,
    ),
]

# ── 풀 구성 — 프로덕션 다중에이전트 시스템, 고위험 도메인 ────────────────────
# 5개 Config 모두 활성화. 의료·금융·법률 등 고위험 도메인 권장.
production_group_f = [
    DeadlockConfig(
        check_circular_delegation=True,
        check_starvation=True,
        check_livelock=True,
        starvation_threshold=3,
        livelock_window=8,
        max_delegation_depth=5,
    ),
    ConsensusConfig(
        consensus_method="weighted",
        agent_weights=AGENT_WEIGHTS,
        similarity_threshold=0.75,
        select_consensus_response=True,
    ),
    PropagationConfig(
        source_agent="upstream_agent",
        key_facts=CRITICAL_FACTS,
        check_in_response=True,
        similarity_threshold=0.75,
        penalize_distortion=True,
    ),
    AgentRoleConfig(
        role_name="agent",
        allowed_tools=APPROVED_TOOLS,
        forbidden_tools=FORBIDDEN_TOOLS,
        check_tool_role_alignment=True,
        role_violation_penalty=0.4,
    ),
    ConflictResolutionConfig(
        conflict_markers=CONFLICT_MARKERS,
        resolution_markers=RESOLUTION_MARKERS,
        check_resolution_quality=True,
        require_explanation=True,
        unresolved_penalty=0.5,
        expect_escalation_on_fail=True,
    ),
]
```

### 9.8.4 Gate F 모니터링 체계 구축

배포 이후에도 Gate F 지표를 지속 모니터링해 협업 품질 저하를 조기에 탐지한다.

```python
from agent_evaluator import PerformanceMonitor, AnomalyDetector
from agent_evaluator.alerts import AlertEngine
from agent_evaluator import SimpleTaskAlertRule

monitor = PerformanceMonitor("results/multi_agent/")
anomaly_detector = AnomalyDetector()
alert_engine = AlertEngine()

# Gate F 이상 탐지 규칙
deadlock_alert = SimpleTaskAlertRule(
    name="deadlock_detected",
    condition=lambda tr: tr.extra.get("deadlock_detected", False),
    handler=lambda msg, tr: alert_engine.fire("CRITICAL", f"교착 감지: {tr.task_id}"),
    severity="critical",
    cooldown=0,  # 교착은 즉시 알림, cooldown 없음
)

propagation_alert = SimpleTaskAlertRule(
    name="propagation_degraded",
    condition=lambda tr: tr.extra.get("propagation_score", 1.0) < 0.6,
    handler=lambda msg, tr: alert_engine.fire(
        "WARNING",
        f"정보 전달 저하 (점수: {tr.extra.get('propagation_score'):.2f}): {tr.task_id}"
    ),
    severity="warning",
    cooldown=300,  # 5분 쿨다운
)

# agent_eval에 알림 규칙 연결
@agent_eval(
    monitor,
    task_type="planning",
    deadlock=production_group_f[0],
    alert_rules=[deadlock_alert, propagation_alert],
)
def monitored_orchestrator(question: str, ground_truth: str = "") -> str:
    return orchestrator.run(question)
```

**운영 체크리스트**:

- [ ] 모든 에이전트에 `DeadlockConfig(check_circular_delegation=True)` 최소 적용
- [ ] 3단계 이상 파이프라인에 `PropagationConfig(key_facts=[...])` 적용
- [ ] 앙상블 시스템에 BFT 원칙 적용 (n ≥ 3f+1)
- [ ] 에이전트별 독립 `PerformanceMonitor`로 기여도 추적
- [ ] Gate F 점수 0.75 미만 시 배포 차단 CI/CD 설정
- [ ] `AnomalyDetector`로 Gate F 점수 이상 급락 실시간 탐지
- [ ] 분기별 기여도 분석으로 병목 에이전트 재설계

---

> 🔗 **다음 챕터**: Chapter 10 — Group G: 운영관측성  
> 에이전트의 실패 원인을 즉시 추적하고 설명할 수 있는지 측정하는 4개 Config를 이해한다. LLM Judge와 운영관측성의 연결을 다룬다.

---

## 9.9 실전 예제 파일

| 예제 파일 | 관련 내용 |
|---------|---------|
| [`Evaluator_Examples/08_harness_eval.py`](../../Evaluator_Examples/08_harness_eval.py) | 섹션 6: Group F Multi-Agent Coordination — 4개 Config 실전 예제 |
| [`Evaluator_Examples/02_layer2_agentic_security.py`](../../Evaluator_Examples/02_layer2_agentic_security.py) | 섹션 4: AgentCoordinationTracker·ToolSelectionTracker 실전 예제 |

**핵심 코드 (출처: `Evaluator_Examples/08_harness_eval.py`, 섹션 6 — Group F Multi-Agent Coordination)**

```python
# 출처: Evaluator_Examples/08_harness_eval.py, 섹션 6 — Group F Multi-Agent Coordination
from agent_evaluator import (
    ConsensusConfig, PropagationConfig,
    AgentRoleConfig, ConflictResolutionConfig,
)
from agent_evaluator.decorators import agent_eval, batch_eval

# ── ConsensusConfig: 에이전트 간 합의율·분쟁 탐지 선언 ──
@batch_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_consensus",
    consensus=ConsensusConfig(
        consensus_method="majority",
        similarity_threshold=0.7,
    ),
)
def consensus_agent(questions: list, ground_truths: list = None) -> list:
    """3개 에이전트 응답 집계 — majority vote."""
    return [f"에이전트 합의 결과: {q}에 대해 majority vote 완료" for q in questions]

# ── PropagationConfig: 정보 전파 정확도·왜곡 탐지 선언 ──
@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_propagation",
    propagation=PropagationConfig(
        key_facts=["project_id", "deadline"],
        check_in_response=True,
        similarity_threshold=0.6,
    ),
)
def propagation_agent(question: str, ground_truth: str = "") -> str:
    return f"project_id: PROJ-001, deadline: 2026-06-30 — {question} 처리 완료"

# ── AgentRoleConfig: 역할 준수율·역할 위반 탐지 선언 ──
@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_role",
    agent_role=AgentRoleConfig(
        role_name="summarizer",
        allowed_tools=["search", "summarize"],
        forbidden_tools=["delete", "write_db"],
        role_violation_penalty=0.3,
    ),
)
def role_bounded_agent(question: str, ground_truth: str = "") -> str:
    return f"[summarizer] 요약 수행: {question}에 대한 핵심 내용 정리 완료"

# ── ConflictResolutionConfig: 충돌 해결 패턴·해결 시간 선언 ──
@agent_eval(
    monitor,
    task_type="multi_agent",
    task_id_prefix="f_conflict",
    conflict_resolution=ConflictResolutionConfig(
        unresolved_penalty=0.3,
        check_resolution_quality=True,
    ),
)
def conflict_resolver_agent(question: str, ground_truth: str = "") -> str:
    if "충돌" in question or "disagree" in question.lower():
        return "합의 도달: 에이전트 간 의견 충돌을 resolved하고 최종 결정을 내렸습니다."
    return f"일치된 응답: {question}"
```

```bash
python Evaluator_Examples/08_harness_eval.py           # Group F 포함 전체
python Evaluator_Examples/02_layer2_agentic_security.py  # AgentCoordinationTracker 예제
```
