# Chapter 10. Group G — 운영관측성 지표

```
┌────────────────────────────────────────────────────────────┐
│ 🔗 Harness 연결                                             │
│ Group G — Operational Observability (운영관측성)             │
│ Tracker: (모든 트래커 데이터가 관측성 기반)                    │
│ Config 4종: ObservabilityConfig · ExplainabilityConfig ·   │
│             ErrorDiagnosisConfig · LatencyAttributionConfig  │
│ Gate 판정: HarnessEvaluationGate.check_group_G()           │
└────────────────────────────────────────────────────────────┘
```

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group G Config 입력·출력
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group G Config 파라미터 전체 목록
> - **[Evaluator_Examples/07_phoenix_hybrid.py](../../Evaluator_Examples/07_phoenix_hybrid.py)**: Phoenix OTEL 관측성 실전 예제
> - **[Chapter 19 — Phoenix OTEL 모니터링](../Part_V_프로덕션운영/Chapter_14_Phoenix_OTEL_모니터링.md)**: 실시간 관측성 인프라

---

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Group G가 없으면 생기는 일                                │
│ 프로덕션 에이전트가 응답을 생성했다. 하지만 왜 이런 답을      │
│ 했는지 알 수 없다. 사용자가 불만을 제기했을 때 어떤 도구를    │
│ 어떤 순서로 호출했는지, 어느 단계에서 지연이 발생했는지,      │
│ 왜 틀린 정보를 말했는지 추적할 방법이 없다.                   │
│ ExplainabilityConfig와 LatencyAttributionConfig 없이는      │
│ "블랙박스" 에이전트가 된다.                                   │
└────────────────────────────────────────────────────────────┘
```

---

## 10.1 Group G 개요

Group G는 에이전트의 **관측 가능성(Observability)**을 측정한다. 에이전트가 잘 동작할 때는 관측성이 필요 없다. 에이전트가 실패하거나, 예상치 못한 행동을 하거나, 성능이 저하될 때 관측성이 있어야 원인을 빠르게 찾을 수 있다.

### Group G가 답하는 4가지 질문

1. **추적 가능성**: 에이전트의 모든 행동이 추적 가능한가? (`ObservabilityConfig`)
2. **설명 가능성**: 에이전트가 왜 그런 답을 했는지 설명할 수 있는가? (`ExplainabilityConfig`)
3. **오류 진단**: 실패했을 때 원인과 대안을 제시하는가? (`ErrorDiagnosisConfig`)
4. **지연 귀속**: 응답 지연의 원인이 어디에 있는지 알 수 있는가? (`LatencyAttributionConfig`)

### Group G와 LLM Judge의 연결

Group G는 AI Native 관점에서 **"AI가 AI를 평가하는"** 패러다임이 가장 자연스럽게 적용되는 영역이다. LLMJudge를 활성화하면 에이전트 응답의 추론 근거, 설명 품질, 오류 진단 능력을 자동으로 채점한다.

```python
@agent_eval(
    monitor,
    task_type="reasoning",
    # Group G Config
    explainability=ExplainabilityConfig(require_reasoning=True),
    error_diagnosis=ErrorDiagnosisConfig(only_on_failure=True),
    # LLM Judge와 연결 — Group G 채점
    llm_judge=LLMJudgeConfig(
        criteria=["reasoning_quality", "explainability"],
        sample_rate=0.3,
    ),
)
def reasoning_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 10.2 Config 4종 레퍼런스

### 10.2.1 ObservabilityConfig — 추적 가능성 기준

에이전트 실행의 모든 단계가 충분히 추적 가능한 상태인지 측정한다. OpenTelemetry 스팬의 완성도와 감사 이벤트 SLO를 선언한다.

```python
from agent_evaluator.decorators import ObservabilityConfig

ObservabilityConfig(
    required_span_attributes=[       # 모든 스팬에 반드시 포함되어야 할 속성
        "task_id",
        "task_type",
        "execution_time",
        "model",                     # 추가 권장 속성
        "tokens_used",
    ],
    check_trace_continuity=True,     # 스팬 연속성 확인 (트레이스 단절 탐지)
    audit_events=[                   # 감사 이벤트 목록 (반드시 기록되어야 함)
        "tool_call_start",
        "tool_call_end",
        "llm_request",
    ],
    min_coverage=0.95,               # 전체 태스크 중 스팬이 완성된 비율
)
```

**Phoenix OTEL과의 통합:**

`ObservabilityConfig`는 `agent-eval monitor`(Arize Phoenix)와 함께 사용할 때 가장 강력하다.

```python
from agent_evaluator.core.otel import setup_otel

# OTEL 설정 — Phoenix 서버로 스팬 자동 전송
setup_otel(
    endpoint="http://localhost:6006/v1/traces",
    service_name="my-agent",
)

# 이후 @agent_eval 데코레이터가 자동으로 OTLP 스팬 발행
@agent_eval(
    monitor,
    task_type="qa",
    observability=ObservabilityConfig(
        required_span_attributes=["task_id", "model", "tokens_used"],
        min_coverage=0.99,
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

```bash
# Phoenix 서버 기동 + OTEL 설정
agent-eval monitor --port 6006

# http://localhost:6006 에서 스팬 트레이스 확인
```

### 10.2.2 ExplainabilityConfig — 설명 가능성 기준

에이전트 응답에 추론 근거, 불확실성 표현, 출처 인용이 포함되는지 측정한다. 특히 의료·금융·법률 에이전트에서 중요하다.

```python
from agent_evaluator.decorators import ExplainabilityConfig

ExplainabilityConfig(
    require_reasoning=True,          # 추론 근거 필수 포함
    reasoning_markers=[              # 추론을 나타내는 마커
        "because", "therefore", "since", "thus",
        "왜냐하면", "따라서", "이유는",
    ],
    require_uncertainty_expression=False,  # 불확실성 표현 요구
    uncertainty_markers=[
        "uncertain", "may", "might", "possibly",
        "불확실", "아마도", "~일 수 있습니다",
    ],
    require_citations=False,         # 출처 인용 요구
    citation_markers=[
        "according to", "based on", "source:",
        "참고:", "출처:", "기준:",
    ],
    min_reasoning_length=20,         # 최소 추론 길이 (문자 수)
    check_action_explanation_alignment=False,  # 행동-설명 일관성 확인
)
```

**도메인별 ExplainabilityConfig 예시:**

```python
# 의료 정보 에이전트 — 출처 + 불확실성 표현 필수
medical_explainability = ExplainabilityConfig(
    require_reasoning=True,
    require_uncertainty_expression=True,  # "~일 수 있습니다" 표현 장려
    require_citations=True,               # 의학 근거 인용 필수
    min_reasoning_length=50,
)

# 법률 에이전트 — 근거 조항 인용 필수
legal_explainability = ExplainabilityConfig(
    require_reasoning=True,
    require_citations=True,
    citation_markers=["제", "조", "항", "법률", "규정", "판례"],
    min_reasoning_length=30,
)

# 일반 QA 봇 — 최소 요구사항
qa_explainability = ExplainabilityConfig(
    require_reasoning=False,     # 짧은 답변에는 추론 불필요
    min_reasoning_length=0,
)
```

### 10.2.3 ErrorDiagnosisConfig — 오류 진단 품질

에이전트가 실패했을 때 단순히 "실패했다"고 말하는 것이 아니라, 원인을 설명하고 대안을 제시하는지 측정한다.

```python
from agent_evaluator.decorators import ErrorDiagnosisConfig

ErrorDiagnosisConfig(
    failure_acknowledgment_markers=[  # 오류를 인정하는 마커
        "failed", "unable", "error", "could not",
        "오류", "실패", "불가능", "할 수 없",
    ],
    root_cause_markers=[             # 근본 원인을 설명하는 마커
        "because", "due to", "caused by",
        "왜냐하면", "때문에", "원인은",
    ],
    suggestion_markers=[             # 대안·해결책을 제시하는 마커
        "try", "suggest", "recommend", "alternatively",
        "시도", "제안", "대신", "대안으로",
    ],
    only_on_failure=True,            # 실패 응답에만 적용 (성공 응답 제외)
    acknowledgment_weight=0.3,       # 오류 인정 가중치
    root_cause_weight=0.5,           # 원인 설명 가중치 (가장 중요)
    suggestion_weight=0.2,           # 대안 제시 가중치
)
```

**오류 진단 품질 비교:**

```
❌ 나쁜 오류 응답:
   "요청을 처리할 수 없습니다."
   → 인정은 했으나 원인도, 대안도 없음

🟡 보통 오류 응답:
   "죄송합니다. 데이터베이스 연결이 실패했습니다."
   → 인정 + 원인은 있으나 대안 없음

✅ 좋은 오류 응답:
   "현재 데이터베이스 연결이 불안정하여 처리할 수 없습니다.
    잠시 후 다시 시도하거나, 캐시된 데이터로 조회할 수 있습니다."
   → 인정 + 원인 + 대안 제시
```

**사용 예시:**

```python
@agent_eval(
    monitor,
    task_type="tool_use",
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=True,
        root_cause_weight=0.5,
        suggestion_weight=0.3,
    ),
)
def diagnostic_agent(question: str, ground_truth: str = "") -> str:
    try:
        return agent.run(question)
    except Exception as e:
        return f"오류가 발생했습니다 (원인: {e.__class__.__name__}). 다시 시도해주세요."
```

### 10.2.4 LatencyAttributionConfig — 지연 원인 귀속

전체 응답 시간 중 어느 부분에서 시간이 소요되는지 측정한다. "응답이 느리다"는 것만 아는 것이 아니라, "도구 호출 때문에 느린지, LLM 호출 때문에 느린지"를 구분한다.

```python
from agent_evaluator.decorators import LatencyAttributionConfig

LatencyAttributionConfig(
    tool_latency_key="tool_latencies",       # extra 딕셔너리의 도구 지연 키
    model_latency_key="model_latency_ms",    # extra 딕셔너리의 모델 지연 키
    network_latency_key="network_latency_ms",# extra 딕셔너리의 네트워크 지연 키
    max_tool_time_ratio=0.6,                 # 도구 호출 시간 허용 비율 (60%)
    max_model_time_ratio=0.5,               # LLM 호출 시간 허용 비율 (50%)
    warn_on_high_unattributed=True,          # 귀속 불가 지연 > 30% 시 경고
)
```

**지연 귀속 데이터 전달:**

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="t1",
    question="검색 후 요약",
    response="요약 결과",
    execution_time=5.2,
    task_type="tool_use",
    extra={
        "tool_latencies": {
            "web_search": 1800,   # ms
            "summarize": 1200,    # ms
        },
        "model_latency_ms": 1500,
        "network_latency_ms": 400,
        # 귀속된 지연: 1800+1200+1500+400 = 4900ms
        # 귀속 불가 지연: 5200 - 4900 = 300ms (약 6%)
    },
)
```

**지연 분석 활용:**

```
전체 응답 시간: 5.2초
 ├─ 도구 호출: 3.0초 (58%) — 최적화 우선순위
 ├─ LLM 호출:  1.5초 (29%)
 ├─ 네트워크:  0.4초 (8%)
 └─ 기타:      0.3초 (6%)

→ 도구 호출(58%)이 병목 → 병렬화 또는 캐싱 검토
```

---

## 10.3 조합 패턴 — 관측성 수준별 구성

### 패턴 1 — 기본 관측성 (모든 에이전트 권장)

```python
from agent_evaluator.decorators import (
    agent_eval, ObservabilityConfig, ErrorDiagnosisConfig
)

@agent_eval(
    monitor,
    task_type="qa",
    observability=ObservabilityConfig(
        required_span_attributes=["task_id", "task_type", "execution_time"],
        min_coverage=0.95,
    ),
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=True,
        root_cause_weight=0.5,
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 패턴 2 — 고신뢰 서비스 (설명 가능성 + LLM Judge)

```python
from agent_evaluator.decorators import (
    ExplainabilityConfig, LLMJudgeConfig, LatencyAttributionConfig
)

@agent_eval(
    monitor,
    task_type="reasoning",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        require_citations=True,
        min_reasoning_length=50,
    ),
    error_diagnosis=ErrorDiagnosisConfig(
        root_cause_weight=0.6,
        suggestion_weight=0.3,
    ),
    latency_attribution=LatencyAttributionConfig(
        max_tool_time_ratio=0.5,
        warn_on_high_unattributed=True,
    ),
    # LLM Judge로 Group G 자동 채점
    llm_judge=LLMJudgeConfig(
        criteria=["reasoning_quality", "explainability", "evidence_based"],
        sample_rate=0.2,
    ),
)
def expert_agent(question: str, ground_truth: str = "") -> str:
    return expert_llm.invoke(question)
```

---

## 10.4 AI Native 관점 — "AI Judge는 Harness의 일급 시민"

Group G는 AI Native 관점이 가장 강하게 드러나는 영역이다. 에이전트의 추론 근거와 설명 품질을 **사람이 수작업으로 평가하는 것은 확장되지 않는다**. LLM Judge가 이 역할을 담당해야 한다.

### 10.4.1 LLMJudge의 7가지 채점 차원

LLMJudge는 `enable_llm_judge=True` 또는 `llm_judge=LLMJudgeConfig()`가 설정되면 자동으로 다음 차원을 채점한다.

| 차원 | 설명 | Group 연결 |
|------|------|-----------|
| `completeness` | 응답이 질문에 완전히 답했는가 | Group A |
| `relevance` | 응답이 질문과 관련이 있는가 | Group A |
| `factual_consistency` | 응답이 사실에 기반하는가 | Group C |
| `toxicity` | 응답에 독성 내용이 없는가 | Group E |
| `bias` | 응답에 편향이 없는가 | Group E |
| `faithfulness` | RAG 응답이 컨텍스트에 기반하는가 | Group C |
| `criteria_scores` | 커스텀 G-Eval 기준 (선택) | Group G |

### 10.4.2 safety_score 계산

LLMJudge는 독성(`toxicity`)과 편향(`bias`) 점수를 종합해 `safety_score`를 자동 계산한다.

```
safety_score = (10 - toxicity - bias) / 10

toxicity=0, bias=0  → safety_score = 1.0 (완전 안전)
toxicity=3, bias=2  → safety_score = 0.5 (주의 필요)
```

```python
# LLMJudge 결과 접근
report = monitor.generate_report()
judge_summary = report.to_dict().get("llm_judge_summary", {})

print(f"전체 품질: {judge_summary.get('avg_scores', {}).get('overall', 0):.2f}")
print(f"안전 점수: {judge_summary.get('avg_scores', {}).get('safety_score', 0):.2f}")
print(f"신뢰성: {judge_summary.get('avg_scores', {}).get('factual_consistency', 0):.2f}")
```

---

## 10.5 Part II 종합 정리 — 7개 Group 전체 연결

이 챕터로 Part II의 Harness 지표 체계 학습이 완료된다. 7개 Group의 관계를 다시 한 번 정리한다.

```
에이전트 실행 흐름과 Group 연결:

사용자 입력 → [Group E 보안경계] → 에이전트 처리 → [Group A 목표달성]
                                    ↓
                    [Group B 행동무결성] ← 도구 호출
                    [Group D 성능계약]  ← 응답 시간·비용
                    [Group C 신뢰성]   ← 일관성·재현성
                                    ↓
                [Group F 다중에이전트]  ← (멀티에이전트인 경우)
                                    ↓
                    [Group G 운영관측성] ← 전체 추적·설명
                                    ↓
                    HarnessEvaluationGate → 배포 판정
```

**Group 간 의존성:**

| 우선순위 | Group | 이유 |
|---------|-------|------|
| 1순위 | A — 목표달성 | 기본 기능 없으면 나머지 무의미 |
| 2순위 | D — 성능계약 | SLA 없으면 프로덕션 불가 |
| 2순위 | E — 보안경계 | 외부 노출 에이전트는 즉시 필요 |
| 3순위 | C — 신뢰성 | 안정적 운영에 필요 |
| 3순위 | B — 행동무결성 | 도구 사용 에이전트에 필요 |
| 4순위 | G — 운영관측성 | 장기 운영·디버깅에 필요 |
| 선택 | F — 다중에이전트 | 멀티에이전트 시스템에만 해당 |

---

## 10.6 이 챕터의 핵심 요약

| Config | 역할 | 핵심 파라미터 |
|--------|------|-------------|
| `ObservabilityConfig` | 스팬 추적 완성도 기준 | `required_span_attributes`, `min_coverage` |
| `ExplainabilityConfig` | 응답 설명 가능성 기준 | `require_reasoning`, `require_citations`, `min_reasoning_length` |
| `ErrorDiagnosisConfig` | 오류 진단 품질 기준 | `only_on_failure`, `root_cause_weight`, `suggestion_weight` |
| `LatencyAttributionConfig` | 지연 원인 귀속 기준 | `max_tool_time_ratio`, `warn_on_high_unattributed` |

---

> **Part II 완료.** 7개 Group(Chapter 3~10)에서 58개 지표(25 Tracker + 33 Config)를 모두 학습했다.  
> 
> **다음 단계 — Part III: 개발자 가이드**
> - Chapter 11: 데코레이터 완전 정복 — `@agent_eval`, `@batch_eval`, `@conversation_eval`에 Harness Config 통합
> - Chapter 12: 21개 프레임워크 통합 — LangChain, LangGraph, CrewAI, AutoGen 등
> - Chapter 13: 평가 데이터 설계 — 골든 데이터셋과 에이전트 유형별 최소 세트
