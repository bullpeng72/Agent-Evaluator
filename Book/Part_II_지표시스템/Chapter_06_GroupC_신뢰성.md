# Chapter 6. Gate C — 신뢰성 지표

@@HTML_START@@
<div class="hc-card hc-c">
  <div class="hc-header">
    <span class="hc-gate-badge he-gate gc">Gate C</span>
    <span class="hc-title">🔗 Harness 연결 — Reliability (신뢰성)</span>
  </div>
  <div class="hc-body">
    <div class="hc-row">
      <span class="hc-label hc-tracker-label">Tracker</span>
      <div class="hc-chips">
        <span class="hc-chip hc-t-chip">HallucinationDetector</span>
        <span class="hc-chip hc-t-chip">RetryCorrectionTracker</span>
      </div>
    </div>
    <div class="hc-row">
      <span class="hc-label hc-config-label">Config</span>
      <div class="hc-chips">
        <span class="hc-chip hc-c-chip">ReproducibilityConfig</span>
        <span class="hc-chip hc-c-chip">FaultToleranceConfig</span>
        <span class="hc-chip hc-c-chip">GracefulDegradationConfig</span>
        <span class="hc-chip hc-c-chip">RetryConsistencyConfig</span>
        <span class="hc-chip hc-c-chip">IdempotencyConfig</span>
      </div>
    </div>
  </div>
  <div class="hc-footer">
    <code>HarnessEvaluationGate(report).evaluate()</code>
  </div>
</div>
@@HTML_END@@

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate C 지표 입력·출력
> - **[Appendix H — 수학적 상세](../Appendix/H_알고리즘_수학적_레퍼런스.md)**: 환각 탐지 알고리즘 수식
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate C Config 파라미터 전체 목록
> - **[Evaluator_Examples/ch06_group_c.py](../../Evaluator_Examples/ch06_group_c.py)**: 이 챕터 실전 예제 (HallucinationDetector · 5개 Config · Gate C FAIL 시나리오)

> **독자별 읽기 가이드**  
> - **QA 관리자**: §6.1(개요) → §6.4(Config 설정) → §6.5(임계값·Gate 판정) 순서로 읽으면 "재현성·오류 복구 기준을 어떻게 선언할지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §6.2(Tracker 상세) → §6.3(코드 예제) → §6.4(Config 선언) 순서로 읽으면 `HallucinationDetector`, `ReproducibilityConfig` 등을 바로 적용할 수 있습니다.

---

@@HTML_START@@
<div class="gw-box">
  <div class="gw-header">⚠️ Gate C가 없으면 생기는 일</div>
  <div class="gw-body">
    <p>에이전트가 어제는 "A"라고 답하고 오늘은 "B"라고 답한다. 같은 질문에 매번 다른 응답 — 사용자는 에이전트를 신뢰할 수 없다. ReproducibilityConfig 없이는 이 불일치를 배포 전에 탐지할 수 없다.</p>
    <div class="gw-case">
      <strong>또 다른 사례:</strong> 의료 정보 봇이 "아스피린은 모든 성인에게 안전합니다"라고 환각을 생성했다. HallucinationDetector를 활성화했다면 사실 일관성 점수 0.2로 조기에 탐지됐을 것이다.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 6.1 Gate C 개요

Group C는 에이전트의 **신뢰성(Reliability)**을 측정한다. 신뢰성은 두 가지 차원을 가진다.

1. **일관성**: 같은 입력에 일관된 결과를 내는가? (`ReproducibilityConfig`)
2. **견고성**: 장애 상황에서 적절히 대응하고 복구하는가? (`FaultToleranceConfig`, `GracefulDegradationConfig`)

Gate A(목표달성)가 "결과가 맞는가?"를 묻는다면, Group C는 "결과가 언제나 맞는가?"를 묻는다.

### Tracker vs Config — Gate C 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "얼마나 일관적이고 사실에 기반하는가?" | "이 수준의 신뢰성이면 배포 가능한가?" |
| 코드 위치 | `PerformanceMonitor` 내부 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 선언 |
| 예시 | `hallucination_score=0.15` → "15%의 사실 불일치" | `ReproducibilityConfig(reproducibility_threshold=0.85)` → "재현성 85% 필요" |

---

## 6.2 Tracker 2종 심화

### 6.2.1 HallucinationDetector — 사실 일관성 탐지

`HallucinationDetector`는 에이전트 응답이 ground_truth 또는 제공된 컨텍스트와 사실적으로 일치하는지 측정한다. LLM 기반 에이전트에서 가장 위험한 품질 결함인 환각(hallucination)을 자동으로 탐지한다.

> **중요**: `HallucinationDetector`는 NLP 연산이 필요하므로 **opt-in**이다. `enable_hallucination_detection=True`로 명시적으로 활성화해야 한다.

**측정 원리:**

환각 탐지는 세 가지 신호를 조합한다.
- **사실 일관성**: 응답의 주요 주장이 ground_truth 또는 컨텍스트에 근거하는가
- **자신감-정확도 보정**: 에이전트가 높은 자신감으로 틀린 말을 하지 않는가
- **정보 출처 추적**: RAG 에이전트의 경우 응답이 검색된 문서에 기반하는가

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 4 — 할루시네이션 탐지
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 명시적 활성화 필수
)

@agent_eval(monitor, task_type="qa", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})

rag_agent(
    "아인슈타인이 태어난 해는?",
    context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
    ground_truth="1879년",
)

report = monitor.generate_report()
d = report.to_dict()
print(f"환각 점수: {d.get('hallucination_score', 0):.3f}")
# 0.05 = 매우 낮은 환각 (95% 사실에 기반)
# 0.8  = 높은 환각 (20%만 사실에 기반)
```

**환각 점수 해석:**

| hallucination_score | 의미 | 권장 행동 |
|--------------------|------|---------|
| 0.0~0.1 | 🟢 매우 안전 | 배포 가능 |
| 0.1~0.3 | 🟡 주의 | 응답 샘플 수동 검토 |
| 0.3~0.5 | 🟠 높음 | 프롬프트 개선 + RAG 품질 점검 |
| > 0.5 | 🔴 매우 위험 | 배포 금지 — 근본 원인 분석 필수 |

**RAG Faithfulness — LLM Judge 연동:**

환각 탐지를 더 정밀하게 하려면 LLMJudge와 결합한다.

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 4 — 할루시네이션 탐지
from agent_evaluator import LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        sample_rate=0.2,               # 20%만 LLM 채점
    ),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})

# LLMJudge가 context 존재 시 자동으로 faithfulness 점수 추가
# result.extra["llm_judge"]["scores"]["faithfulness"]  → 0~5
```

- `rag_mode=True`와 `llm_judge=LLMJudgeConfig(...)`를 함께 사용하면 `HallucinationDetector`(NLP 기반)와 `faithfulness` 점수(LLM 기반) 두 신호를 동시에 얻어 환각 탐지 정밀도가 높아진다.
- `sample_rate=0.2`는 전체 태스크의 20%에만 LLM 채점을 적용하며, 비용 절감과 커버리지를 균형 있게 유지한다.
- `faithfulness` 점수는 0~5 스케일이며, `result.extra["llm_judge"]["scores"]["faithfulness"]`로 태스크별로 접근할 수 있다.

### 6.2.2 RetryCorrectionTracker — 재시도·자가수정 추적

에이전트가 실패 후 재시도하거나 응답을 스스로 수정하는 행동을 추적한다. 재시도가 성공으로 이어지는지, 아니면 동일한 실패를 반복하는지를 측정한다.

**측정 항목:**

| 항목 | 설명 |
|------|------|
| `retry_rate` | 전체 태스크 중 재시도가 발생한 비율 |
| `retry_success_rate` | 재시도 후 성공으로 전환된 비율 |
| `avg_retries_per_task` | 태스크당 평균 재시도 횟수 |
| `self_correction_rate` | 스스로 오류를 수정한 비율 |

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 2 — Gate B — Behavioral Integrity
from agent_evaluator import create_taskresult

# 재시도 정보 기록
result = create_taskresult(
    task_id="t1",
    question="복잡한 계산 태스크",
    response="최종 답변: 42",
    execution_time=5.0,
    task_type="reasoning",
    attempts=3,           # 3번 시도 후 성공
    errors=["timeout", "invalid_format"],  # 첫 2번 실패 원인
    ground_truth="42",
)
monitor.record_task(result)

report = monitor.generate_report()
d = report.to_dict()
print(f"재시도율: {d.get('retry_rate', 0) * 100:.1f}%")
print(f"재시도 성공률: {d.get('retry_success_rate', 0) * 100:.1f}%")
```

- `attempts=3`을 `create_taskresult()`에 전달하면 `RetryCorrectionTracker`가 해당 태스크를 재시도로 자동 분류하며, `attempts > 1`이면 재시도 기록에 포함된다.
- `errors=[...]` 필드에 실패 원인을 전달하면 재시도 원인별 분류가 가능하고, 어떤 오류 유형에서 재시도가 성공하는지 분석할 수 있다.
- `retry_success_rate`가 낮다면 재시도 로직이 같은 실패를 반복하고 있다는 신호로, 폴백 전략이나 오류 처리 개선이 필요하다.

---

## 6.3 Config 5종 레퍼런스

### 6.3.1 ReproducibilityConfig — 재현성 측정

동일한 입력을 N회 실행해 응답의 일관성을 측정한다. AI Native 관점의 "확률론적 품질"을 직접 측정하는 핵심 Config다.

```python
# 출처: Evaluator_Examples/ch06_group_c.py
from agent_evaluator import ReproducibilityConfig

ReproducibilityConfig(
    runs=3,                           # 동일 입력 반복 실행 횟수
    similarity_measure="token_f1",    # "token_f1"|"jaccard"|"exact"
    reproducibility_threshold=0.85,   # 재현성 임계값 (0.0~1.0)
)
```

**similarity_measure 선택 가이드:**

| similarity_measure | 특징 | 권장 상황 |
|-------------------|------|---------|
| `token_f1` | 토큰 단위 정밀도-재현율 F1 조화평균 | QA, 사실 응답 (기본 권장) |
| `jaccard` | 순서 무관 단어 집합 유사도 | 긴 설명형 응답 |
| `exact` | 완전히 동일한 응답만 1.0 | 구조화 출력 (JSON, 코드) |

**사용 예시 — 금융 정보 에이전트:**

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 3 — Gate C Reliability
@agent_eval(
    monitor,
    task_type="qa",
    reproducibility=ReproducibilityConfig(
        runs=5,                          # 5회 실행으로 분포 측정
        similarity_measure="token_f1",   # "token_f1"|"jaccard"|"exact"
        reproducibility_threshold=0.90,  # 금융 정보 — 높은 재현성 요구
    ),
)
def finance_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

**재현성 임계값 가이드:**

| 도메인 | 권장 threshold | 이유 |
|--------|--------------|------|
| 의료·금융 | 0.90+ | 일관성 없는 정보는 치명적 |
| 고객 응대 | 0.80 | 일관된 서비스 경험 필요 |
| 창의적 작업 | 0.60 | 다양성이 오히려 가치 있음 |
| 코드 생성 | 0.85 | 동일 요구사항엔 유사한 코드 |

### 6.3.2 FaultToleranceConfig — 장애 내성

에이전트가 도구 실패나 부분적인 오류 상황에서 적절한 폴백(fallback) 전략을 사용하는지 측정한다.

```python
# 출처: Evaluator_Examples/ch06_group_c.py
from agent_evaluator import FaultToleranceConfig

FaultToleranceConfig(
    check_fallback_attempts=True,           # 실패 후 폴백 도구 사용 여부 추적
    partial_success_threshold=0.5,          # 부분 성공 임계값 (0.0~1.0)
)
```

**사용 예시 — 데이터베이스 쿼리 에이전트:**

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 3 — Gate C Reliability
@agent_eval(
    monitor,
    task_type="tool_use",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.5,
    ),
)
def db_agent(question: str, ground_truth: str = "") -> str:
    # main_db 실패 시 replica_db로 폴백하는 에이전트
    return data_agent.run(question)
```

- `check_fallback_attempts=True`는 기본 도구 실패 후 대체 도구로 전환하는 폴백 행동을 추적하며, 폴백이 없으면 장애 내성 점수가 낮아진다.
- `partial_success_threshold=0.5`는 완전 성공이 아닌 부분 완료 태스크를 허용하는 기준이며, 0.5 이상이면 부분 성공으로 인정한다.
- 분산 서비스 에이전트에서 주 DB 실패 시 레플리카나 캐시로 폴백하는 패턴이 이 Config의 대표 활용 사례다.

### 6.3.3 GracefulDegradationConfig — 우아한 성능 저하

에이전트가 최적 조건이 아닐 때(도구 실패, 컨텍스트 부족, 타임아웃 등) 완전한 실패 대신 부분적인 결과를 제공하는지 측정한다. "모든 것을 실패하거나, 모든 것을 성공하거나" 대신 "가능한 것을 제공하고 부족함을 인정하는" 패턴을 장려한다.

```python
# 출처: Evaluator_Examples/ch06_group_c.py
from agent_evaluator import GracefulDegradationConfig

GracefulDegradationConfig(
    quality_floor=0.3,                   # 최소 품질 기준 (이 이하면 빈 응답과 동일)
    partial_result_markers=[],           # 부분 결과를 나타내는 마커
    check_error_acknowledgment=True,     # 오류 인정 여부 확인
)
```

**사용 예시:**

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 3 — Gate C Reliability
@agent_eval(
    monitor,
    task_type="qa",
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        check_error_acknowledgment=True,
        empty_response_penalty=0.8,
    ),
)
def robust_agent(question: str, ground_truth: str = "") -> str:
    try:
        return llm.invoke(question)
    except TimeoutError:
        return "죄송합니다. 현재 처리가 지연되고 있습니다. 부분적인 결과를 제공합니다: ..."
    except Exception as e:
        return f"요청을 완전히 처리하지 못했습니다. 다시 시도해주세요."
```

- `quality_floor=0.4`는 에이전트가 제공하는 최소 품질 기준으로, 이 점수 이하의 응답은 빈 응답과 동일하게 취급해 감점된다.
- `check_error_acknowledgment=True`는 에이전트가 오류 발생 시 명시적으로 인정하는 응답을 반환하는지 확인한다.
- `partial_result_markers`에 선언한 문자열(예: "부분", "폴백", "partial")이 응답에 포함되면 부분 완료로 인식해 완전 실패보다 높은 점수를 부여한다.

### 6.3.4 RetryConsistencyConfig — 재시도 일관성

재시도 횟수와 결과를 기반으로 재시도 전략의 효율성을 평가한다. "재시도가 실제로 성공으로 이어지는가?"를 측정한다.

```python
from agent_evaluator import RetryConsistencyConfig

RetryConsistencyConfig(
    group_by_task_prefix=True,           # task_id 접두사 기준 태스크 그룹화
    improvement_threshold=0.1,           # 재시도 후 개선으로 인정할 최소 점수 상승
    penalize_degradation=True,           # 재시도 후 성능이 오히려 떨어지면 패널티
    min_retry_count=2,                   # 통계에 포함할 최소 재시도 횟수
)
```

**`RetryConfig`와 `RetryConsistencyConfig`의 차이:**

| 항목 | `RetryConfig` (데코레이터 파라미터) | `RetryConsistencyConfig` (Harness Config) |
|------|--------------------------------|----------------------------------------|
| 목적 | 재시도 *실행* 방식 설정 | 재시도 *패턴* 품질 *측정* |
| 동작 | 실패 시 N번 재시도 수행 | 재시도 후 실제로 개선됐는지 평가 |
| 코드 | `retry=RetryConfig(max=3)` | `retry_consistency=RetryConsistencyConfig(...)` |

```python
from agent_evaluator import RetryConfig, RetryConsistencyConfig

@agent_eval(
    monitor,
    task_type="qa",
    retry=RetryConfig(max=3, delay=1.0, backoff=2.0),  # 재시도 실행
    retry_consistency=RetryConsistencyConfig(           # 재시도 패턴 측정
        improvement_threshold=0.1,
        penalize_degradation=True,
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `RetryConfig`는 실패 시 자동 재시도를 *실행*하고, `RetryConsistencyConfig`는 그 재시도가 실제로 개선으로 이어졌는지를 *측정*하는 별개의 역할을 한다.
- `improvement_threshold=0.1`은 재시도 후 점수가 0.1 이상 올라야 개선으로 인정하며, 이 기준 이하면 재시도 효과가 없다고 판단한다.
- `penalize_degradation=True`는 재시도 후 오히려 점수가 낮아진 경우 패널티를 부여해 무의미한 재시도 전략을 조기에 발견할 수 있게 한다.

### 6.3.5 IdempotencyConfig — 멱등성 평가

동일한 도구를 반복 실행했을 때 부작용(side effect)이 발생하는지 평가한다. 데이터 생성·삭제·수정 등 비멱등(non-idempotent) 도구를 불필요하게 반복 호출하면 감점된다.

```python
from agent_evaluator import IdempotencyConfig

IdempotencyConfig(
    non_idempotent_patterns=[            # 비멱등 도구 패턴 목록
        "create", "delete", "insert",
        "update", "post", "write",
        "생성", "삭제", "저장", "수정", "전송",
    ],
    duplicate_detection_markers=[        # 중복 탐지 응답 마커 (보너스 점수)
        "already", "duplicate", "exists",
        "이미", "중복", "존재",
    ],
    non_idempotent_penalty=0.2,          # 비멱등 호출당 감점
    warn_on_non_idempotent=True,         # 비멱등 호출 시 경고 로깅
)
```

**사용 예시 — 데이터베이스 쓰기 에이전트:**

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 역케이스 Gate C FAIL (IdempotencyConfig)
@agent_eval(
    monitor,
    task_type="tool_use",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create_record", "delete_record", "update_field"],
        non_idempotent_penalty=0.3,
        warn_on_non_idempotent=True,
    ),
)
def db_write_agent(question: str, ground_truth: str = "") -> str:
    return db_agent.run(question)
```

- `non_idempotent_patterns`에 선언한 패턴이 `tool_calls`의 도구 이름과 매칭되면 비멱등 호출로 기록하고 `non_idempotent_penalty`만큼 점수를 감점한다.
- `duplicate_detection_markers`에 선언한 문자열이 응답에 포함되면 에이전트가 중복 실행을 스스로 감지했다는 보너스 점수를 부여한다.
- 데이터베이스 쓰기·이메일 전송·결제 처리처럼 중복 실행이 치명적인 에이전트에 필수로 적용한다.

---

## 6.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 의료·금융 정보 에이전트 (고신뢰성 요구)

```python
from agent_evaluator import PerformanceMonitor, ReproducibilityConfig, LLMJudgeConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 필수
)

@agent_eval(
    monitor,
    task_type="qa",
    rag_mode=True,
    reproducibility=ReproducibilityConfig(
        runs=5,
        reproducibility_threshold=0.90,
        fail_on_low_reproducibility=True,
    ),
    llm_judge=LLMJudgeConfig(
        model="claude-sonnet-4-6",       # 고품질 모델로 판단
        criteria=["factual_accuracy", "medical_safety"],
        sample_rate=0.5,                 # 50% 샘플 (의료는 높은 비율)
    ),
)
def medical_info_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

- 의료·금융 도메인은 `reproducibility_threshold=0.90`으로 재현성 요구를 높이고, `fail_on_low_reproducibility=True`로 기준 미달 시 배포를 자동 차단한다.
- `criteria=["factual_accuracy", "medical_safety"]`처럼 도메인 특화 기준을 G-Eval로 선언하면 일반 품질 지표 외에 전문 영역 안전성을 추가로 평가한다.
- `enable_hallucination_detection=True`는 NLP 기반 탐지, `llm_judge`는 LLM 기반 탐지로, 두 방식을 결합하면 환각 탐지의 재현율과 정밀도가 모두 높아진다.

### 패턴 2 — 분산 서비스 에이전트 (장애 내성 중심)

```python
from agent_evaluator import (
    FaultToleranceConfig, GracefulDegradationConfig,
    RetryConsistencyConfig
)

@agent_eval(
    monitor,
    task_type="tool_use",
    retry=RetryConfig(max=3, delay=0.5, backoff=2.0),
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        expected_fallback_tools={
            "primary_api": ["backup_api", "cache"],
        },
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.3,
        check_error_acknowledgment=True,
    ),
    retry_consistency=RetryConsistencyConfig(
        improvement_threshold=0.1,
        penalize_degradation=True,
    ),
)
def resilient_agent(question: str, ground_truth: str = "") -> str:
    return distributed_agent.run(question)
```

- `RetryConfig(max=3, delay=0.5, backoff=2.0)`와 `FaultToleranceConfig`를 결합하면 재시도 실행과 폴백 추적이 동시에 이루어진다.
- `expected_fallback_tools`에 주 도구와 폴백 도구 매핑을 선언하면 폴백 전환 여부를 정확히 추적할 수 있다.
- `GracefulDegradationConfig(check_error_acknowledgment=True)`와 `RetryConsistencyConfig(penalize_degradation=True)`를 함께 쓰면 재시도 효과가 없을 때 부분 응답이라도 반환하는 설계를 강제할 수 있다.

---

## 6.5 AI Native 관점 — 신뢰성의 확률론적 이해

### 6.5.1 환각은 확률이다, 비율이 아니다

`hallucination_score=0.2`는 "20%의 응답에 환각이 있다"는 뜻이 아니다. 각 응답마다 사실 일관성 점수가 있고, 그 평균이 0.2다. 같은 0.2라도:

- 모든 응답에서 일정하게 낮은 점수: 예측 가능한 수준의 환각
- 어떤 응답은 0.0(완전 환각), 어떤 응답은 0.9(사실 기반): 예측 불가능한 환각

배포 결정은 이 분포를 보고 내려야 한다.

```python
# 환각 점수 분포 분석
report = monitor.generate_report()
d = report.to_dict()

hall_details = d.get("hallucination_details", [])
scores = [t["hallucination_score"] for t in hall_details]

import statistics
if scores:
    print(f"환각 점수 평균: {statistics.mean(scores):.3f}")
    print(f"환각 점수 표준편차: {statistics.stdev(scores):.3f}")
    print(f"최대 환각: {max(scores):.3f}")
    high_risk = [s for s in scores if s > 0.5]
    print(f"고위험 태스크: {len(high_risk)}/{len(scores)}건")
```

- `hallucination_details` 리스트에서 태스크별 환각 점수를 추출하면 평균이 아닌 분포를 직접 확인할 수 있다.
- 표준편차가 크면 어떤 태스크에서는 신뢰할 수 있고 어떤 태스크에서는 위험한 "불규칙 환각" 패턴이며, 이 경우 평균 점수만으로 배포 결정을 내리면 안 된다.
- `scores > 0.5`인 고위험 태스크 비율이 5% 이상이면 배포 전에 해당 태스크의 입력 유형을 분석해 취약 구간을 찾아야 한다.

### 6.5.2 재현성과 드리프트의 연결

`ReproducibilityConfig`는 단일 평가 세션의 재현성을 측정한다. 시계열 재현성(드리프트)은 `agent-eval trend`로 측정한다. 두 측정이 함께해야 완전한 신뢰성 그림이 완성된다.

```bash
# 1. 단일 세션 재현성 (ReproducibilityConfig)
# → "오늘 같은 질문에 일관된 답변을 하는가?"

# 2. 시계열 드리프트 (agent-eval trend)
# → "지난 한 달 동안 신뢰성이 유지되고 있는가?"
agent-eval trend results/ --window 30 --metric reproducibility
```

- `agent-eval trend`는 순차적으로 저장된 결과 파일들의 시계열 변화를 분석하므로 `ReproducibilityConfig`의 단일 세션 측정과 상호 보완적이다.
- `--window 30`은 최근 30개 결과 파일을 분석 대상으로 삼으며, 주기적 CI/CD 실행 환경에서 한 달치 드리프트를 한 번에 확인할 수 있다.
- `--fail-on-regression`을 추가하면 재현성이 이전 기간 대비 저하될 때 `exit 1`로 CI/CD를 자동 차단한다.

---

## 6.6 HarnessEvaluationGate — Gate C 판정

```python
from agent_evaluator import HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

group_c = result["groups"]["C"]
print(f"Gate C 통과: {group_c['passed']}")
print(f"Gate C 점수: {group_c['score']:.3f}")

# Gate C 주요 지표 접근
d = report.to_dict()
print(f"환각 점수: {d.get('hallucination_score', 'N/A')}")
print(f"재현성: {d.get('reproducibility_score', 'N/A')}")
print(f"재시도 성공률: {d.get('retry_success_rate', 'N/A')}")
```

- `result["groups"]["C"]`로 Gate C 전체 통과 여부와 점수를 직접 접근하며, `score`는 0.0~1.0 범위다.
- `hallucination_score`·`reproducibility_score`·`retry_success_rate`는 `report.to_dict()`의 최상위 키로 접근하며, 각각 환각·재현성·재시도 효율성을 대표하는 지표다.
- `gate.enforce()`는 Gate A–G 전체를 종합 판정해 임계값 미달 시 `sys.exit(1)`을 호출하므로 CI/CD 파이프라인에서 배포 차단 자동화가 가능하다.

---

---

## 6.7 실전 예제 파일

**기본 예제**: [`Evaluator_Examples/ch06_group_c.py`](../../Evaluator_Examples/ch06_group_c.py)
— HallucinationDetector · FaultToleranceConfig · ReproducibilityConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig 5개 Config · Gate C FAIL 시나리오

> **관련 챕터 예제**: Harness 전체 Gate 통합 흐름은 [Chapter 3 — `ch03_harness_basics.py`](Chapter_03_Harness_Engineering_기초.md), Layer 1 기초 트래커는 [Chapter 1 — `ch01_first_eval.py`](../Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md)에서 확인한다.

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch06_group_c.py, 섹션 3 — Gate C Reliability
from agent_evaluator import (
    FaultToleranceConfig, GracefulDegradationConfig,
    ReproducibilityConfig, RetryConsistencyConfig, IdempotencyConfig,
    RetryConfig,
)
from agent_evaluator.decorators import agent_eval

# ── FaultToleranceConfig + GracefulDegradationConfig: 장애 내성 + 우아한 저하 ──
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="c_fault",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.5,
    ),
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        partial_result_markers=["부분", "폴백", "fallback", "partial"],
        check_error_acknowledgment=True,
    ),
    retry=RetryConfig(max=2, on=(RuntimeError,), delay=0.0),
)
def fault_tolerant_agent(question: str, ground_truth: str = "") -> str:
    """실패 시 부분 완료 응답으로 우아하게 저하."""
    return f"부분 완료(폴백): 캐시 데이터로 응답합니다. {question}"

# ── ReproducibilityConfig: 동일 입력 반복 실행 일관성 선언 ──
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="c_repro",
    reproducibility=ReproducibilityConfig(
        runs=3,
        similarity_measure="token_f1",
        reproducibility_threshold=0.8,
    ),
)
def reproducible_agent(question: str, ground_truth: str = "") -> str:
    return f"재현 가능한 답변: {question}에 대해 정해진 응답을 반환합니다."

# ── IdempotencyConfig: 멱등성·중복 실행 안전성 선언 ──
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="c_idempotency",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create", "delete", "insert", "생성", "삭제"],
        non_idempotent_penalty=0.2,
    ),
)
def idempotent_agent(question: str, ground_truth: str = "") -> str:
    return f"읽기 전용 조회 완료: {question}에 대한 데이터를 검색했습니다."
```

- 각 Config를 `task_id_prefix`로 분리하면 리포트에서 `c_fault_*`·`c_repro_*`·`c_idempotency_*`별로 Gate C 위반 원인을 추적할 수 있다.
- `RetryConfig(max=2, on=(RuntimeError,), delay=0.0)`는 재시도 실행을 담당하고, `FaultToleranceConfig`와 `GracefulDegradationConfig`는 그 결과를 각각 측정한다.
- `idempotent_agent`처럼 응답에 "조회"·"검색"처럼 읽기 전용을 나타내는 문자열이 포함되면 `duplicate_detection_markers`와 결합해 중복 실행 안전성 보너스 점수를 얻을 수 있다.

```bash
python Evaluator_Examples/ch03_harness_basics.py          # Gate C 포함 전체
python Evaluator_Examples/ch01_first_eval.py    # HallucinationDetector 예제
python Evaluator_Examples/ch04_group_a.py  # Gate C FAIL — 배포 차단 케이스
```

- `ch03_harness_basics.py`는 Gate A–G 모든 Config를 한 번에 실행하므로 Gate C 판정 결과를 다른 Gate와 함께 비교할 수 있다.
- `ch01_first_eval.py`의 `HallucinationDetector` 예제는 `enable_hallucination_detection=True` 설정 없이는 실행되지 않으므로 반드시 `PerformanceMonitor` 생성 시 확인한다.
- `ch04_group_a.py`의 Gate C FAIL 시나리오를 먼저 실행해 어떤 Config가 어떤 조건에서 `success=False`를 내는지 파악한 후 자신의 에이전트에 적용하면 설정 오류를 줄일 수 있다.

---

## 6.8 이 챕터의 핵심 요약

| 지표/Config | 역할 | 핵심 파라미터 |
|------------|------|-------------|
| `HallucinationDetector` | 사실 일관성 점수 (opt-in) | `enable_hallucination_detection=True` |
| `RetryCorrectionTracker` | 재시도·자가수정 패턴 | `retry_rate`, `retry_success_rate` |
| `ReproducibilityConfig` | 동일 입력 재현성 기준 | `runs`, `similarity_measure`("token_f1"\|"jaccard"\|"exact"), `reproducibility_threshold`, `fail_on_low_reproducibility` |
| `FaultToleranceConfig` | 장애 내성·폴백 기준 | `expected_fallback_tools`, `check_fallback_attempts` |
| `GracefulDegradationConfig` | 우아한 성능 저하 기준 | `quality_floor`, `check_error_acknowledgment` |
| `RetryConsistencyConfig` | 재시도 일관성 기준 | `improvement_threshold`, `penalize_degradation` |
| `IdempotencyConfig` | 멱등성 기준 | `non_idempotent_patterns`, `non_idempotent_penalty` |

> 🔗 **다음 챕터**: Chapter 7 — Gate D: 성능계약  
> 에이전트의 응답 시간·비용·토큰 사용량이 약속한 SLA를 지키는지 측정하는 2개 Tracker와 5개 Config를 완전히 이해한다.
