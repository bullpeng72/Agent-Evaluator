# Chapter 9. Group F — 다중에이전트 협업 지표

```
┌────────────────────────────────────────────────────────────┐
│ 🔗 Harness 연결                                             │
│ Group F — Multi-Agent Coordination (다중에이전트 협업)       │
│ Tracker 2종: AgentCoordinationTracker · ToolSelectionTracker│
│ Config 5종: DeadlockConfig · ConsensusConfig ·              │
│             PropagationConfig · AgentRoleConfig ·           │
│             ConflictResolutionConfig                        │
│ Gate 판정: HarnessEvaluationGate.check_group_F()           │
└────────────────────────────────────────────────────────────┘
```

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group F 지표 입력·출력
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group F Config 파라미터 전체 목록
> - **[Evaluator_Examples/02_layer2_agentic_security.py](../../Evaluator_Examples/02_layer2_agentic_security.py)**: AgentCoordinationTracker 실전 예제

---

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Group F가 없으면 생기는 일                                │
│ 연구자 에이전트가 작가 에이전트에게 "초안 작성해줘"라고 위임  │
│ 하고, 작가 에이전트는 "먼저 검색해줘"라고 되돌려보낸다.      │
│ 이 순환 위임이 30회 반복되다가 타임아웃. 작업은 완료되지      │
│ 않았다. DeadlockConfig.check_circular_delegation=True로    │
│ 첫 번째 순환 시점에서 차단할 수 있었다.                      │
└────────────────────────────────────────────────────────────┘
```

---

## 9.1 Group F 개요

Group F는 **다중 에이전트 시스템**의 협업 품질을 측정한다. 단일 에이전트 평가는 Group A-E로 충분하지만, 여러 에이전트가 협력하는 시스템은 추가로 다음을 측정해야 한다.

1. **교착**: 에이전트들이 서로를 기다리며 멈추지 않는가? (`DeadlockConfig`)
2. **역할 준수**: 각 에이전트가 자신의 역할 범위 안에서 동작하는가? (`AgentRoleConfig`)
3. **정보 전달**: 에이전트 간 정보가 왜곡 없이 전달되는가? (`PropagationConfig`)

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

## 9.3 Config 5종 레퍼런스

### 9.3.1 DeadlockConfig — 교착 상태 탐지

에이전트들이 서로를 기다리는 교착(deadlock), 한 에이전트가 계속 대기하는 기아(starvation), 에이전트들이 끝없이 같은 행동을 반복하는 라이브락(livelock)을 탐지한다.

```python
from agent_evaluator.decorators import DeadlockConfig

DeadlockConfig(
    check_circular_delegation=True,  # 순환 위임 탐지 (A→B→A)
    check_starvation=True,           # 기아 탐지 (특정 에이전트가 N회+ 대기)
    starvation_threshold=3,          # 기아 탐지 임계값 (대기 횟수)
    check_livelock=False,            # 라이브락 탐지 (기본 비활성)
    livelock_window=6,               # 라이브락 탐지 윈도우
    max_delegation_depth=10,         # 최대 위임 깊이
)
```

**교착 유형별 대응:**

| 유형 | 탐지 조건 | 처리 방법 |
|------|---------|---------|
| Circular Deadlock | A→B→A 순환 위임 | `fail_on_violation=True` |
| Starvation | 동일 에이전트 3회+ 연속 대기 | 경고 후 재시도 |
| Livelock | N 윈도우 내 동일 행동 반복 | 강제 중단 |

### 9.3.2 ConsensusConfig — 다중 에이전트 합의

여러 에이전트가 같은 질문에 대해 답변할 때 합의가 이루어지는지 측정한다. `batch_eval`과 함께 사용할 때 가장 효과적이다.

```python
from agent_evaluator.decorators import ConsensusConfig

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
from agent_evaluator.decorators import batch_eval, ConsensusConfig

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

### 9.3.3 PropagationConfig — 정보 전파 충실도

선행 에이전트가 수집한 핵심 정보가 후속 에이전트로 왜곡 없이 전달되는지 측정한다.

```python
from agent_evaluator.decorators import PropagationConfig

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

### 9.3.4 AgentRoleConfig — 에이전트 역할 준수

멀티에이전트 시스템에서 각 에이전트가 자신의 역할 범위 안에서 도구와 행동을 선택하는지 측정한다.

```python
from agent_evaluator.decorators import AgentRoleConfig

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

### 9.3.5 ConflictResolutionConfig — 충돌 해결 품질

에이전트 간 의견 충돌이 발생했을 때 적절하게 해결하는지 측정한다. 충돌을 방치하거나, 무시하거나, 에스컬레이션 없이 진행하는 것을 탐지한다.

```python
from agent_evaluator.decorators import ConflictResolutionConfig

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
from agent_evaluator.decorators import (
    agent_eval, DeadlockConfig, AgentRoleConfig,
    PropagationConfig, SLAConfig,
)

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
from agent_evaluator.decorators import (
    batch_eval, ConsensusConfig, ConflictResolutionConfig
)

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
| `DeadlockConfig` | 교착·기아·라이브락 탐지 | `check_circular_delegation`, `max_delegation_depth` |
| `ConsensusConfig` | 다중 에이전트 합의 기준 | `consensus_method`, `agent_weights`, `similarity_threshold` |
| `PropagationConfig` | 에이전트 간 정보 전달 기준 | `key_facts`, `penalize_distortion` |
| `AgentRoleConfig` | 에이전트 역할 준수 기준 | `role_name`, `allowed_tools`, `forbidden_tools` |
| `ConflictResolutionConfig` | 에이전트 간 충돌 해결 기준 | `unresolved_penalty`, `expect_escalation_on_fail` |

> 🔗 **다음 챕터**: Chapter 10 — Group G: 운영관측성  
> 에이전트의 실패 원인을 즉시 추적하고 설명할 수 있는지 측정하는 4개 Config를 이해한다. LLM Judge와 운영관측성의 연결을 다룬다.
