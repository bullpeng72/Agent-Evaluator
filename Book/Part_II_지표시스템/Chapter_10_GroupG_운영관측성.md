# Chapter 10. Gate G — 운영관측성 지표

@@HTML_START@@
<div class="hc-card hc-g">
  <div class="hc-header">
    <span class="hc-gate-badge he-gate gg">Gate G</span>
    <span class="hc-title">🔗 Harness 연결 — Operational Observability (운영관측성)</span>
  </div>
  <div class="hc-body">
    <div class="hc-row">
      <span class="hc-label hc-tracker-label">Tracker</span>
      <div class="hc-chips">
        <span class="hc-chip hc-t-chip hc-t-note">모든 트래커 집계</span>
      </div>
    </div>
    <div class="hc-row">
      <span class="hc-label hc-config-label">Config</span>
      <div class="hc-chips">
        <span class="hc-chip hc-c-chip">ObservabilityConfig</span>
        <span class="hc-chip hc-c-chip">ExplainabilityConfig</span>
        <span class="hc-chip hc-c-chip">ErrorDiagnosisConfig</span>
        <span class="hc-chip hc-c-chip">LatencyAttributionConfig</span>
      </div>
    </div>
  </div>
  <div class="hc-footer">
    <code>HarnessEvaluationGate(report).evaluate()</code>
  </div>
</div>
@@HTML_END@@

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate G Config 입력·출력
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate G Config 파라미터 전체 목록
> - **[Evaluator_Examples/ch10_group_g.py](../../Evaluator_Examples/ch10_group_g.py)**: 이 챕터 실전 예제 (4개 Config · AnomalyDetector · CostTracker · evaluation_session)
> - **[Chapter 19 — Phoenix OTEL 모니터링](../Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md)**: 실시간 관측성 인프라 (Phoenix 연동 심화)

> **독자별 읽기 가이드**  
> - **QA 관리자**: §10.1(개요) → §10.4(Config 설정) → §10.5(임계값·Gate 판정) 순서로 읽으면 "LLM Judge 채점 기준을 어떻게 설정할지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §10.2(LLM Judge 상세) → §10.3(코드 예제) → §10.4(Config 선언) 순서로 읽으면 `ObservabilityConfig`, `ExplainabilityConfig` 등을 바로 적용할 수 있습니다.

---

@@HTML_START@@
<div class="gw-box">
  <div class="gw-header">⚠️ Gate G가 없으면 생기는 일</div>
  <div class="gw-body">
    <p>프로덕션 에이전트가 응답을 생성했다. 하지만 왜 이런 답을 했는지 알 수 없다. 사용자가 불만을 제기했을 때 어떤 도구를 어떤 순서로 호출했는지, 어느 단계에서 지연이 발생했는지, 왜 틀린 정보를 말했는지 추적할 방법이 없다.</p>
    <div class="gw-case">
      <strong>실제 사례:</strong> ExplainabilityConfig와 LatencyAttributionConfig 없이는 "블랙박스" 에이전트가 된다.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 10.1 Gate G 개요

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
    # Gate G Config
    explainability=ExplainabilityConfig(require_reasoning=True),
    error_diagnosis=ErrorDiagnosisConfig(only_on_failure=True),
    # LLM Judge와 연결 — Gate G 채점
    llm_judge=LLMJudgeConfig(
        criteria=["reasoning_quality", "explainability"],
        sample_rate=0.3,
    ),
)
def reasoning_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `ExplainabilityConfig(require_reasoning=True)`는 응답에 추론 마커가 없으면 설명 가능성 점수가 0으로 처리된다.
- `ErrorDiagnosisConfig(only_on_failure=True)`는 실패한 응답에만 진단 품질을 검사해 불필요한 연산을 줄인다.
- `LLMJudgeConfig(criteria=["reasoning_quality", "explainability"])`로 LLM이 설명 품질을 자동 채점한다.
- `sample_rate=0.3`은 전체 태스크의 30%만 LLM Judge로 채점해 비용을 절감하면서도 품질 신호를 유지한다.

---

## 10.2 Config 4종 레퍼런스

### 10.2.1 ObservabilityConfig — 추적 가능성 기준

에이전트 실행의 모든 단계가 충분히 추적 가능한 상태인지 측정한다. OpenTelemetry 스팬의 완성도와 감사 이벤트 SLO를 선언한다.

```python
from agent_evaluator import ObservabilityConfig

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
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 1 — Tracing — 스팬 전송 + Annotations
from agent_evaluator import setup_otel

# OTEL 설정 — Phoenix 서버로 스팬 자동 전송 (setup_otel은 PerformanceMonitor 생성 전에 호출)
setup_otel(
    endpoint="http://localhost:6006",
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

- `setup_otel()`은 `PerformanceMonitor` 생성 전에 호출해야 모든 스팬이 Phoenix로 전송된다.
- `min_coverage=0.99`는 99% 이상의 태스크에서 지정된 스팬 속성이 완성되어야 PASS가 된다는 의미다.
- `required_span_attributes`에 없는 속성은 스팬 완성도 계산에서 제외된다.
- Phoenix UI(`http://localhost:6006`)에서 스팬 트레이스를 실시간으로 확인할 수 있다.

```bash
# Phoenix 서버 기동 + OTEL 설정
agent-eval monitor --port 6006

# http://localhost:6006 에서 스팬 트레이스 확인
```

- `agent-eval monitor` 명령으로 Phoenix 서버를 기동하면 OTLP 스팬 수신이 즉시 시작된다.
- 기본 포트는 6006이며, `--port` 옵션으로 변경할 수 있다.

### 10.2.2 ExplainabilityConfig — 설명 가능성 기준

에이전트 응답에 추론 근거, 불확실성 표현, 출처 인용이 포함되는지 측정한다. 특히 의료·금융·법률 에이전트에서 중요하다.

```python
from agent_evaluator import ExplainabilityConfig

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

- 도메인의 위험도에 따라 `require_citations`와 `require_uncertainty_expression`을 선택적으로 활성화한다.
- 의료·법률처럼 고위험 도메인은 `min_reasoning_length`를 높게(50 이상) 설정해 근거 서술을 충분히 유도한다.
- `citation_markers`를 도메인 전용 키워드("제", "조", "판례" 등)로 재정의하면 법령 인용을 정밀하게 탐지할 수 있다.
- 일반 QA 봇은 `require_reasoning=False`로 설정해 불필요한 설명 요구로 인한 점수 저하를 방지한다.

### 10.2.3 ErrorDiagnosisConfig — 오류 진단 품질

에이전트가 실패했을 때 단순히 "실패했다"고 말하는 것이 아니라, 원인을 설명하고 대안을 제시하는지 측정한다.

```python
from agent_evaluator import ErrorDiagnosisConfig

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

- `only_on_failure=True` 설정 시 성공한 응답은 진단 품질 검사에서 제외되어 연산 비용을 절감한다.
- `root_cause_weight=0.5`로 원인 설명이 진단 점수의 절반을 차지하도록 설정한다.
- 예외 클래스명(`e.__class__.__name__`)을 응답에 포함하면 `root_cause_markers` 탐지 확률이 높아진다.
- "다시 시도해주세요" 같은 표현은 `suggestion_markers`에 해당하는 대안 제시로 인식된다.

### 10.2.4 LatencyAttributionConfig — 지연 원인 귀속

전체 응답 시간 중 어느 부분에서 시간이 소요되는지 측정한다. "응답이 느리다"는 것만 아는 것이 아니라, "도구 호출 때문에 느린지, LLM 호출 때문에 느린지"를 구분한다.

```python
from agent_evaluator import LatencyAttributionConfig

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

- `extra["tool_latencies"]`에 도구별 지연(ms)을 딕셔너리로 전달하면 도구 호출 비중이 자동 계산된다.
- `model_latency_ms`와 `network_latency_ms`를 별도로 기입하면 LLM·네트워크 지연을 분리해 진단할 수 있다.
- 귀속 불가 지연(`execution_time` − 합산 지연)이 30%를 초과하면 `warn_on_high_unattributed=True`로 경고가 발생한다.
- `max_tool_time_ratio=0.6`은 도구 호출이 전체 응답 시간의 60%를 초과하면 Gate G 경고로 처리한다.

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
from agent_evaluator import (
    ObservabilityConfig,
    ErrorDiagnosisConfig,
)
from agent_evaluator.decorators import agent_eval

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

- `ObservabilityConfig`와 `ErrorDiagnosisConfig`의 조합은 모든 에이전트에 기본 적용할 수 있는 최소 관측성 구성이다.
- `min_coverage=0.95`는 전체 태스크 중 95% 이상이 스팬 속성을 완성해야 Gate G PASS 조건을 충족한다.
- `only_on_failure=True` 설정으로 성공 응답에 대한 불필요한 오류 진단 검사를 건너뛴다.
- 두 Config를 함께 사용하면 추적 가능성과 오류 설명 품질을 동시에 측정할 수 있다.

### 패턴 2 — 고신뢰 서비스 (설명 가능성 + LLM Judge)

```python
from agent_evaluator import (
    ExplainabilityConfig,
    LatencyAttributionConfig,
    LLMJudgeConfig,
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
    # LLM Judge로 Gate G 자동 채점
    llm_judge=LLMJudgeConfig(
        criteria=["reasoning_quality", "explainability", "evidence_based"],
        sample_rate=0.2,
    ),
)
def expert_agent(question: str, ground_truth: str = "") -> str:
    return expert_llm.invoke(question)
```

- 고신뢰 서비스에는 `ExplainabilityConfig(require_reasoning=True, require_citations=True)`를 함께 활성화해 추론 근거와 출처 인용을 모두 요구한다.
- `LatencyAttributionConfig(max_tool_time_ratio=0.5)`는 도구 호출이 응답 시간의 절반을 초과하면 경고를 발생시킨다.
- `LLMJudgeConfig(sample_rate=0.2)`로 20%만 LLM 채점해 비용을 제어하면서 품질 신호를 유지한다.
- 4개 Config를 모두 조합하면 설명 가능성·지연 귀속·오류 진단·자동 채점을 단일 데코레이터로 통합할 수 있다.

---

## 10.4 AI Native 관점 — "AI Judge는 Harness의 일급 시민"

Group G는 AI Native 관점이 가장 강하게 드러나는 영역이다. 에이전트의 추론 근거와 설명 품질을 **사람이 수작업으로 평가하는 것은 확장되지 않는다**. LLM Judge가 이 역할을 담당해야 한다.

### 10.4.1 LLMJudge의 7가지 채점 차원

LLMJudge는 `enable_llm_judge=True` 또는 `llm_judge=LLMJudgeConfig()`가 설정되면 자동으로 다음 차원을 채점한다.

| 차원 | 설명 | Group 연결 |
|------|------|-----------|
| `completeness` | 응답이 질문에 완전히 답했는가 | Gate A |
| `relevance` | 응답이 질문과 관련이 있는가 | Gate A |
| `factual_consistency` | 응답이 사실에 기반하는가 | Gate C |
| `toxicity` | 응답에 독성 내용이 없는가 | Gate E |
| `bias` | 응답에 편향이 없는가 | Gate E |
| `faithfulness` | RAG 응답이 컨텍스트에 기반하는가 | Gate C |
| `criteria_scores` | 커스텀 G-Eval 기준 (선택) | Gate G |

### 10.4.2 safety_score 계산

LLMJudge는 독성(`toxicity`)과 편향(`bias`) 점수를 종합해 `safety_score`를 자동 계산한다.

```
safety_score = (10 - toxicity - bias) / 10

toxicity=0, bias=0  → safety_score = 1.0 (완전 안전)
toxicity=3, bias=2  → safety_score = 0.5 (주의 필요)
```

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 추가 — LLMJudge 직접 사용
# LLMJudge 결과 접근
report = monitor.generate_report()
judge_summary = report.to_dict().get("llm_judge_summary", {})

print(f"전체 품질: {judge_summary.get('avg_scores', {}).get('overall', 0):.2f}")
print(f"안전 점수: {judge_summary.get('avg_scores', {}).get('safety_score', 0):.2f}")
print(f"신뢰성: {judge_summary.get('avg_scores', {}).get('factual_consistency', 0):.2f}")
```

- `llm_judge_summary`는 `report.to_dict()` 결과 딕셔너리에서 LLMJudge 채점 통계를 담고 있다.
- `overall`은 completeness·relevance·factual_consistency 3차원의 평균 점수다.
- `safety_score`가 0.5 미만이면 독성 또는 편향 점수가 높다는 의미로 즉각 점검이 필요하다.
- `faithfulness`는 `rag_mode=True`와 `context`를 함께 전달한 태스크에서만 집계된다.

---

## 10.5 Part II 종합 정리 — 7개 Group 전체 연결

이 챕터로 Part II의 Harness 지표 체계 학습이 완료된다. 7개 Group의 관계를 다시 한 번 정리한다.

```
에이전트 실행 흐름과 Group 연결:

사용자 입력 → [Gate E 보안경계] → 에이전트 처리 → [Gate A 목표달성]
                                    ↓
                    [Gate B 행동무결성] ← 도구 호출
                    [Gate D 성능계약]  ← 응답 시간·비용
                    [Gate C 신뢰성]   ← 일관성·재현성
                                    ↓
                [Gate F 다중에이전트]  ← (멀티에이전트인 경우)
                                    ↓
                    [Gate G 운영관측성] ← 전체 추적·설명
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

## 10.6 실전 예제 파일

**기본 예제**: [`Evaluator_Examples/ch10_group_g.py`](../../Evaluator_Examples/ch10_group_g.py)

| 섹션 | 내용 |
|------|------|
| 섹션 7 | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig |
| 섹션 추가 | AnomalyDetector (5가지 이상 탐지) · CostTracker + AdaptivePolicy |
| evaluation_session | 컨텍스트 매니저 — 예외 발생 시 자동 저장 |

```bash
python Evaluator_Examples/ch10_group_g.py    # Gate G + AnomalyDetector + CostTracker 전체 시연
```

> **관련 챕터 예제**: Phoenix OTEL 관측성 심화는 [Chapter 19 — `ch19_phoenix.py`](../Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md)에서, Gate G FAIL 케이스(시나리오 5·16·17)는 [Chapter 4 — `ch04_group_a.py`](Chapter_04_GroupA_목표달성.md)에서 확인한다.

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 7 — Gate G Observability
from agent_evaluator import (
    ExplainabilityConfig, ObservabilityConfig,
    ErrorDiagnosisConfig, LatencyAttributionConfig,
)
from agent_evaluator.decorators import agent_eval

# ── ExplainabilityConfig: 추론 단계·설명 가능성 기준 선언 ──
@agent_eval(
    monitor,
    task_type="reasoning",
    task_id_prefix="g_explain",
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=50,
        reasoning_markers=["왜냐하면", "따라서", "근거"],
    ),
)
def explainable_agent(question: str, ground_truth: str = "") -> str:
    return f"[추론] 왜냐하면 {question}에 대한 근거가 있기 때문입니다. 따라서 이 결론에 도달했습니다."

# ── ObservabilityConfig: 내부 상태 추적·추적 가능성 기준 선언 ──
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="g_observability",
    observability=ObservabilityConfig(
        check_trace_continuity=True,
        min_coverage=0.95,
        required_span_attributes=["task_id", "task_type", "execution_time"],
    ),
)
def observable_agent(question: str, ground_truth: str = "") -> str:
    return f"추적 가능 응답: {question}"

# ── Harness 전체 리포트 추출 — Gate A-G 점수 확인 ──
final_report  = monitor.generate_report()
report_dict   = final_report.to_dict()
harness_groups = (report_dict.get("extra_metrics") or {}).get("harness_groups", {})

group_labels = {
    "A": "Goal Achievement",     "B": "Behavioral Integrity",
    "C": "Reliability",          "D": "Performance Contract",
    "E": "Security Boundary",    "F": "Multi-Agent Coordination",
    "G": "Observability",
}
for gk, label in group_labels.items():
    group_data = harness_groups.get(gk, {})
    score  = group_data.get("score")
    status = group_data.get("status", "n/a")
    if score is not None:
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"Group {gk} [{label:<28s}] {bar} {score:.3f} ({status})")

monitor.save_to_file("08_harness_eval")
```

```bash
python Evaluator_Examples/ch03_harness_basics.py      # Gate G 포함 전체 — 배포 판정 리포트까지
python Evaluator_Examples/ch19_phoenix.py    # Phoenix 트레이싱 + 데이터셋 업로드
```

---
**FAIL 케이스**

시나리오 16: `ObservabilityConfig` — 필수 span 속성 누락 (coverage < 0.9)

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 역케이스 Gate G FAIL
from agent_evaluator import PerformanceMonitor, ObservabilityConfig, ExplainabilityConfig
from agent_evaluator.decorators import agent_eval

monitor_g = PerformanceMonitor(output_dir="results/")

@agent_eval(
    monitor_g,
    task_type="qa",
    task_id_prefix="bad_g_observe",
    observability=ObservabilityConfig(
        required_span_attributes=[
            "task_id", "task_type", "execution_time",
            "model_version", "trace_id", "agent_name",
        ],
        check_trace_continuity=True,
        min_coverage=0.9,
    ),
)
def unobservable_agent(question: str, ground_truth: str = "") -> str:
    # model_version·trace_id·agent_name 누락 → coverage=3/6=0.5 < min_coverage=0.9
    return f"처리 완료: {question}"

unobservable_agent("추적 정보를 확인해줘", ground_truth="추적 확인")
# → Gate G FAIL: observability_score=0.5 (6개 중 3개만 자동 주입됨)
```

시나리오 17: `ErrorDiagnosisConfig` — 오류 인정·근본 원인·해결책 없이 결과만 반환

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 역케이스 Gate G FAIL
from agent_evaluator import ErrorDiagnosisConfig

@agent_eval(
    monitor_g,
    task_type="qa",
    task_id_prefix="bad_g_diag",
    error_diagnosis=ErrorDiagnosisConfig(
        only_on_failure=False,    # 모든 응답에서 진단 품질 평가
        acknowledgment_weight=0.3,
        root_cause_weight=0.5,
        suggestion_weight=0.2,
    ),
)
def no_diagnosis_agent(question: str, ground_truth: str = "") -> str:
    # 실패 인정("오류 발생"), 근본 원인 분석, 해결책 제안이 전혀 없음
    return f"처리를 시도했으나 완료하지 못했습니다."

no_diagnosis_agent("오류 원인을 진단해줘", ground_truth="오류 진단")
# → Gate G FAIL: diagnosis_score=0.0 (acknowledgment·root_cause·suggestion 모두 없음)
```

- `ObservabilityConfig.required_span_attributes`에 나열된 속성 중 TaskResult에 자동으로 채워지는 것은 `task_id`·`task_type`·`execution_time` 3개다. 나머지 3개(`model_version`·`trace_id`·`agent_name`)는 `EvalMetadata(extra={"model_version": ...})`로 명시적으로 주입해야 한다
- `ErrorDiagnosisConfig(only_on_failure=False)` 설정 시 성공 응답에서도 진단 품질을 검사한다. 오류 상황에서의 응답 품질을 상시 감시하려면 `False`로 설정한다
- **시나리오 5+16+17 합산 시 Gate G ≈ 10% (FAIL)**

```bash
python Evaluator_Examples/ch04_group_a.py   # 시나리오 5+16+17: Gate G FAIL 케이스
```

**Layer 1 지표 — 관측성의 기초 수치**

Gate G Config가 추적 완성도와 설명 가능성을 판정한다면, Layer 1은 그 기반이 되는 원시 지표(지연·토큰·품질)를 수집한다. 두 레이어를 함께 운영하면 "추적 완성도 90%이며, p95 지연이 3초"처럼 관측 가능한 수치로 표현된다.

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 3 — 응답 품질 5차원
from agent_evaluator import PerformanceMonitor, create_taskresult
import random

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_transparency=True,   # 투명성 탭: 메트릭 계산 Traces 자동 생성 → Gate G와 연계
)

# 5차원 응답 품질 — Observability 관점의 품질 기준
QUALITY_CASES = [
    ("고품질", "파이썬은 간결한 문법의 고급 언어입니다. 데이터과학·웹·자동화에 폭넓게 사용됩니다."),
    ("중간",   "파이썬은 프로그래밍 언어입니다. 쉽습니다."),
    ("저품질", "몰라요."),
]
for label, resp in QUALITY_CASES:
    result = create_taskresult(
        task_id=f"qual_{label}", question="파이썬이란?", response=resp,
        ground_truth="간결한 문법의 고급 언어",
        execution_time=random.uniform(0.3, 1.5), task_type="qa",
        tokens_used={"input": 80, "output": len(resp.split()), "total": 80 + len(resp.split())},
    )
    monitor.record_task(result)

# 지연시간 분포 — LatencyAttributionConfig가 참조하는 원시 수치
latencies = [random.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]
for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"perf_{i:03d}", question="지연 테스트", response="완료",
        ground_truth="완료", execution_time=round(max(0.1, lat), 3), task_type="qa",
        tokens_used={"input": 50, "output": 20, "total": 70},
    )
    monitor.record_task(result)

report = monitor.generate_report().to_dict()
lat = report.get("efficiency_metrics", {}).get("latency", {})
tok = report.get("efficiency_metrics", {}).get("tokens", {})
print(f"  p50={float(lat.get('p50',0)):.2f}s  p95={float(lat.get('p95',0)):.2f}s")
print(f"  총 토큰: {int(tok.get('total_tokens',0)):,}")
# → Gate G LatencyAttributionConfig: 이 p95/p99 수치를 기반으로 지연 원인 귀속 판정
# → enable_transparency=True: 메트릭 계산 과정이 Traces로 Phoenix에 전송됨
```

**관측성 인프라 — 이상 탐지 + 비용 추적**

Gate G는 응답의 추적 가능성과 설명 가능성을 판정하지만, 그 토대는 운영 인프라다. `AnomalyDetector`는 관측성 점수 드리프트를 실시간 탐지하고, `CostTracker`는 투명성 비용(LLMJudge 호출 등)을 예산 내에서 유지한다.

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 추가A — 이상 탐지 (AnomalyDetector)
from agent_evaluator import PerformanceMonitor, create_taskresult, AnomalyDetector
import random

monitor = PerformanceMonitor(output_dir="results/", enable_transparency=True)
detector = AnomalyDetector(baseline_window=25, detection_window=5)

# 정상 구간 — 추론 마커가 있는 응답, 짧은 지연
for i in range(30):
    r = create_taskresult(
        task_id=f"g_base_{i:03d}",
        question="추론 테스트",
        response="왜냐하면 이 항목이 핵심이기 때문입니다. 따라서 결론을 도출합니다.",
        ground_truth="추론",
        execution_time=round(random.gauss(1.0, 0.2), 3),
        task_type="reasoning",
        tokens_used={"input": 100, "output": 50, "total": 150},
    )
    monitor.record_task(r)

# 드리프트 주입 — 지연 폭증 + 빈 응답 (추론 마커 소실)
for i in range(5):
    r = create_taskresult(
        task_id=f"g_drift_{i:03d}",
        question="추론 테스트",
        response="",  # 설명 없이 빈 응답 → ExplainabilityConfig 위반
        ground_truth="추론",
        execution_time=round(random.gauss(12.0, 2.0), 3),  # 지연 폭증
        task_type="reasoning",
        tokens_used={"input": 4000, "output": 1000, "total": 5000},
    )
    monitor.record_task(r)

events = detector.scan(monitor)
for ev in events[:3]:
    print(f"  [{ev.severity}] {ev.type}: {ev.detail[:60]}")
# → latency_trend·token_spike·error_surge: 관측성 붕괴 시그널
```

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 추가B — 비용 추적 + 적응형 샘플링
from agent_evaluator import CostTracker, AdaptivePolicy

# Gate G에서 ExplainabilityConfig·ObservabilityConfig는 LLMJudge를 사용할 수 있음
# LLMJudge 호출 비용을 예산 범위 내로 유지하는 패턴
tracker = CostTracker(budget_per_day=5.0, alert_at=0.8)
policy  = AdaptivePolicy(default_sample_rate=0.1, anomaly_sample_rate=1.0, budget_per_day=5.0)

# LLMJudge 샘플 평가 — 10%만 채점 (비용 절감)
for i in range(3):
    tracker.record(provider="anthropic", model="claude-haiku-4-5-20251001",
                   cost_usd=0.0008, input_tokens=300, output_tokens=100,
                   evaluation_type="llm_judge_observability")

print(f"  Gate G Judge 비용: ${tracker.get_today_cost():.4f}  알림: {tracker.is_budget_alert()}")
# → sample_rate=0.1로 90% 태스크는 LLMJudge 건너뜀 → Gate G 비용 = 전체의 10%
```

**AdaptivePolicy — 3단계 스테이지 전환:**

`AdaptivePolicy`는 이상 감지·예산 소진에 따라 샘플링률을 자동 조정하는 상태 머신이다. 3개의 `SamplingStage` 중 하나의 상태를 유지하며, `AnomalyDetector` 이벤트와 연동해 자동 전환한다.

| 스테이지 | 전환 조건 | 샘플링률 |
|---------|---------|---------|
| `DEFAULT` | 초기 / 이상 해소 후 | `default_sample_rate` (기본 0.1 = 10%) |
| `ANOMALY` | `enter_anomaly_mode()` 호출 | `anomaly_sample_rate` (기본 1.0 = 100%) |
| `BUDGET_EXCEEDED` | 일일 예산 초과 | 0.0 (샘플링 중단) |

```python
# 출처: Evaluator_Examples/ch10_group_g.py, 섹션 추가B — AdaptivePolicy 스테이지 전환
from agent_evaluator import CostTracker, AdaptivePolicy

policy = AdaptivePolicy(
    default_sample_rate=0.1,    # 평상시 10% 샘플링 (비용 절감)
    anomaly_sample_rate=1.0,    # 이상 감지 시 100% 샘플링 (정밀 진단)
    budget_per_day=5.0,         # 일일 예산 $5 초과 시 샘플링 중단
)

# ── 평상시: DEFAULT 스테이지 ──────────────────────────────────────────────
print(f"현재 스테이지: {policy.current_stage.value}")   # → "default"
print(f"샘플링률    : {policy.current_sample_rate}")    # → 0.1

# 에이전트 실행마다 샘플링 여부 결정
import random
should_run_judge = random.random() < policy.current_sample_rate  # 10% 확률
if should_run_judge:
    pass  # LLMJudge 호출 (비용 발생)

# ── 이상 감지 시: ANOMALY 스테이지로 전환 ─────────────────────────────────
policy.enter_anomaly_mode(reason="accuracy_drop_below_0.5")
print(f"현재 스테이지: {policy.current_stage.value}")   # → "anomaly"
print(f"샘플링률    : {policy.current_sample_rate}")    # → 1.0 (전수 채점)

# ── 이상 해소: DEFAULT로 복귀 ─────────────────────────────────────────────
policy.exit_anomaly_mode()
print(f"현재 스테이지: {policy.current_stage.value}")   # → "default" (예산 미초과 시)

# ── 예산 초과: BUDGET_EXCEEDED ────────────────────────────────────────────
# check_budget()은 내부적으로 CostTracker와 연동; 초과 시 자동 전환
policy.check_budget()
# is_budget_exceeded()이면 → BUDGET_EXCEEDED, current_sample_rate = 0.0

# 상태 전체 조회
status = policy.get_status()
# status["stage"] → "default"/"anomaly"/"budget_exceeded"
# status["current_sample_rate"] → float
# status["default_sample_rate"] / ["anomaly_sample_rate"]
# status["stage_history"] → 최근 10개 전환 이력 [{from, to, reason, timestamp}, ...]
print(f"상태 요약: {status['stage']}  샘플링률={status['current_sample_rate']}")
```

**AnomalyDetector + AdaptivePolicy 연동 패턴:**

```python
from agent_evaluator import AnomalyDetector, AdaptivePolicy, PerformanceMonitor

monitor  = PerformanceMonitor(output_dir="results/")
detector = AnomalyDetector(baseline_window=25, detection_window=5)
policy   = AdaptivePolicy(default_sample_rate=0.1, anomaly_sample_rate=1.0, budget_per_day=5.0)

# 주기적 실행 루프에서 이상 탐지 → 샘플링률 자동 조정
events = detector.scan(monitor)
if events:                                 # 이상 감지
    policy.enter_anomaly_mode(reason=events[0].type)
    print(f"이상 감지 → 샘플링률 {policy.current_sample_rate} (전수 채점 모드)")
else:                                      # 정상
    policy.exit_anomaly_mode()
    print(f"정상 → 샘플링률 {policy.current_sample_rate} (절감 모드)")
```

- `enter_anomaly_mode()` 호출 후 `check_budget()`에서 예산 초과가 확인되면 `ANOMALY`가 아닌 `BUDGET_EXCEEDED`로 전환한다.
- `stage_history`에 최근 10개의 전환 이력이 기록되어 이상 패턴의 발생 빈도를 추적할 수 있다.

---

## 10.7 이 챕터의 핵심 요약

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
> - Chapter 11: 평가 데이터 설계 — 골든 데이터셋과 에이전트 유형별 최소 세트
> - Chapter 12: 데코레이터 완전 정복 — `@agent_eval`, `@batch_eval`, `@conversation_eval`에 Harness Config 통합
> - Chapter 13: 21개 프레임워크 통합 — LangChain, LangGraph, CrewAI, AutoGen 등
