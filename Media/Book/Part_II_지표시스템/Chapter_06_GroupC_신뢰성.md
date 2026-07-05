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
        <span class="hc-chip hc-t-chip hc-t-opt">HallucinationDetector (opt-in)</span>
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
      <strong>사례 예시:</strong> 의료 정보 봇이 "아스피린은 모든 성인에게 안전합니다"라고 환각을 생성했다. HallucinationDetector를 활성화했다면 사실 일관성 점수 0.2로 조기에 탐지됐을 것이다.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 6.1 Gate C 개요

Gate C는 에이전트의 **신뢰성(Reliability)**을 측정한다. 여기서 신뢰성이란 단순한 가동률(uptime)이 아니다. AI 에이전트는 LLM의 확률론적 특성 때문에 같은 입력에 다른 결과를 낼 수 있다. Gate C는 이 **비결정론적 특성을 얼마나 통제하고 있는가**를 배포 기준으로 선언한다.

> **Harness Engineering 관점**: Gate C = "에이전트가 실패 상황에서도 얼마나 예측 가능하게 동작하는가?" 이 기준을 통과하지 못한 에이전트는 개발 환경에서는 잘 동작해도 프로덕션의 장애 상황에서 무너진다.

신뢰성은 세 가지 차원을 가진다.

1. **일관성**: 같은 입력에 일관된 결과를 내는가? (`ReproducibilityConfig`)
2. **견고성**: 장애 상황에서 적절히 대응하고 복구하는가? (`FaultToleranceConfig`, `GracefulDegradationConfig`)
3. **안전성**: 중복 실행·재시도에도 부작용이 없는가? (`IdempotencyConfig`, `RetryConsistencyConfig`)

Gate A(목표달성)가 "주어진 Task를 완료했는가?"를 묻는다면, Gate C는 "결과가 언제나, 어떤 상황에서도 신뢰성있게 제공되는가?"를 묻는다.

### Tracker vs Config — Gate C 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "얼마나 일관적이고 사실에 기반하는가?" | "이 수준의 신뢰성이면 배포 가능한가?" |
| 코드 위치 | `PerformanceMonitor` 내부 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 선언 |
| 예시 | `hallucination_score=0.15` → "15%의 사실 불일치" | `ReproducibilityConfig(reproducibility_threshold=0.85)` → "재현성 85% 필요" |

> **중요 — Tracker와 Config는 다른 개념이다**: `RetryCorrectionTracker`는 재시도 행동을 **측정**하는 런타임 트래커다. `RetryConsistencyConfig`는 재시도 품질 기준을 **선언**하는 Harness Config다. 이름이 비슷해 혼동하기 쉽지만, 트래커는 자동으로 동작하고 Config는 개발자가 명시적으로 선언해야 한다.

---

## 6.2 Tracker 2종 심화

### 6.2.1 HallucinationDetector — 사실 일관성 탐지

`HallucinationDetector`는 에이전트 응답이 ground_truth 또는 제공된 컨텍스트와 사실적으로 일치하는지 측정한다. LLM 기반 에이전트에서 가장 위험한 품질 결함인 환각(hallucination)을 자동으로 탐지한다.

**왜 환각 탐지가 신뢰성(Gate C)의 일부인가?** 환각은 단순한 품질 문제가 아니다. RAG 에이전트가 컨텍스트와 다른 정보를 일관성 없이 반환한다면, 그 에이전트는 신뢰성이 없는 에이전트다. Gate C(신뢰성)는 "언제나 사실에 기반한 응답을 제공하는가"를 배포 기준으로 선언하므로, `HallucinationDetector`는 Gate C의 핵심 측정 도구다.

> **중요**: `HallucinationDetector`는 Agent-Evaluator 구조상 Layer 1 opt-in 트래커로, `enable_hallucination_detection=True`로 명시 활성화해야 한다. NLP 연산 비용 때문에 기본값은 `False`다. SDK 점수 집계 구조상 `hallucination_rate` 측정값은 **Gate C(`_rel_vals`)와 Gate G(`_obs_vals`) 양쪽에 기여**한다. Gate C 관점에서는 "사실 불일치 에이전트를 신뢰할 수 없다"는 신뢰성 기준으로, Gate G 관점에서는 운영 중 환각 발생 관측성 지표로 활용된다. RAG 에이전트의 Gate C 검증 시 함께 활성화할 것을 권장한다.

**측정 원리:**

환각 탐지는 세 가지 신호를 조합한다.
- **사실 일관성**: 응답의 주요 주장이 ground_truth 또는 컨텍스트에 근거하는가
- **자신감-정확도 보정**: 에이전트가 높은 자신감으로 틀린 말을 하지 않는가
- **정보 출처 추적**: RAG 에이전트의 경우 응답이 검색된 문서에 기반하는가

```python
# 개념 코드 — HallucinationDetector 활성화 패턴 (LLM 불필요)
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 명시적 활성화 필수
    use_korean_tokenizer=True,
)

@agent_eval(monitor, task_type="qa", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # 실제 에이전트 구현으로 교체하세요 — HallucinationDetector는 NLP 기반 동작
    if context:
        return f"주어진 문맥을 바탕으로 답변드립니다. {question} — 문맥: {context[:40]}"
    return "문맥 정보가 없어 답변하기 어렵습니다."

rag_agent(
    "아인슈타인이 태어난 해는?",
    context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
    ground_truth="1879년",
)

report = monitor.generate_report()
d = report.to_dict()
hall_data = (d.get("accuracy_metrics") or {}).get("hallucination", {})
print(f"환각률: {hall_data.get('overall_rate', 0):.1f}%")
# 5.0  = 매우 낮은 환각 (95% 사실에 기반)
# 80.0 = 높은 환각 (20%만 사실에 기반)
```

**환각 점수 해석:**

| overall_rate (%) | 의미 | 권장 행동 |
|------------------|------|---------|
| 0~10% | 🟢 매우 안전 | 배포 가능 |
| 10~30% | 🟡 주의 | 응답 샘플 수동 검토 |
| 30~50% | 🟠 높음 | 프롬프트 개선 + RAG 품질 점검 |
| > 50% | 🔴 매우 위험 | 배포 금지 — 근본 원인 분석 필수 |

> 👨‍💻 **개발자 TIP**: `PerformanceMonitor(enable_hallucination_detection=True)`로 명시 활성화가 필수다. RAG 에이전트에서 `rag_mode=True`와 함께 사용하면 컨텍스트 대비 충실성도 함께 측정된다. `LLMJudge`와 병행 시 `judge_sample_rate=0.1`로 비용을 제어할 수 있다.

> 📋 **QA 관리자 TIP**: `overall_rate > 30%`이면 배포 전 수동 샘플 검토가 필요하고, `> 50%`이면 즉시 배포를 차단해야 한다.
> - 권장 기준: 의료·금융 `< 5%` / 일반 Q&A `< 20%` / 창의적 생성 `< 40%`
> - 경보 기준: `overall_rate > 30%`이면 프롬프트·RAG 파이프라인 즉시 점검

**RAG Faithfulness — LLM Judge 연동:**

환각 탐지를 더 정밀하게 하려면 LLMJudge와 결합한다.

```python
# 개념 코드 — RAG Faithfulness + LLMJudge 결합 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
from agent_evaluator import PerformanceMonitor, LLMJudgeConfig, agent_eval, load_env

load_env()

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    use_korean_tokenizer=True,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    llm_judge=LLMJudgeConfig(
        model=None,        # None → API 키 기반 자동 결정
        sample_rate=0.2,   # 20%만 LLM 채점
    ),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # 에이전트 응답은 mock — LLMJudge가 이 응답의 faithfulness를 LLM으로 채점
    if context:
        return f"주어진 문맥을 바탕으로 답변드립니다. {question} — 문맥: {context[:40]}"
    return "문맥 정보가 없어 답변하기 어렵습니다."

rag_agent(
    "아인슈타인이 태어난 해는?",
    context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
    ground_truth="1879년",
)

_judge = (monitor.tasks[-1].llm_judge or {}) if monitor.tasks else {}
_faith = (_judge.get("scores") or {}).get("faithfulness")
if _faith is not None:
    print(f"RAG Faithfulness: {_faith}/5 (5=모든 주장이 컨텍스트에 근거)")
elif _judge.get("skipped"):
    print("LLMJudge: sample_rate에 의해 skip됨")
elif _judge.get("error"):
    print(f"LLMJudge 오류: {_judge['error']}")
else:
    print("LLMJudge: 결과 없음 — API 키 미설정 또는 초기화 오류")
```

**결과 접근 코드 해설:**

`@agent_eval` 데코레이터는 raw 응답 문자열을 그대로 반환하므로, LLMJudge 채점 결과는 반환값이 아닌 `monitor.tasks`를 통해 사후 조회한다.

| 코드 | 설명 |
|------|------|
| `monitor.tasks[-1].llm_judge` | 마지막으로 기록된 태스크의 LLMJudge 결과 딕셔너리 (`skipped`, `scores`, `reasoning`, `cost_usd` 포함). API 키 없으면 `None` |
| `_judge.get("scores", {}).get("faithfulness")` | 0~5 정수 점수 — `None`이면 채점이 실행되지 않았음을 의미 |
| `_judge.get("skipped")` | `True`이면 `sample_rate` 확률 추출에서 제외된 것 — 오류가 아님 |
| `_judge.get("error")` | LLM 호출 실패 메시지 — API 키 오류·네트워크 타임아웃 등 |
| `else` (위 조건 모두 False) | API 키 미설정 → `task.llm_judge`가 `None` 이므로 `_judge = {}` — 별도 분기 필요 |

**`faithfulness` 점수 기준:**

| 점수 | 의미 |
|------|------|
| 5 | 모든 주장이 제공된 컨텍스트에 완전히 근거함 |
| 3~4 | 일부 주장이 컨텍스트 밖에서 추론됨 |
| 1~2 | 컨텍스트와 무관하거나 상충하는 내용 포함 |
| 0 | 컨텍스트를 전혀 참조하지 않음 |

> **`sample_rate` 설계 원칙**: `sample_rate=0.2`로 설정하면 전체 태스크의 약 20%에만 LLM 채점이 적용된다. 나머지 80%는 `skipped=True`로 기록되며, 이는 오류가 아니라 의도된 비용 절감 동작이다. 프로덕션에서는 `0.1~0.2`를, 중요한 평가 구간에서는 `1.0`을 사용한다.

`rag_mode=True`와 `llm_judge=LLMJudgeConfig(...)`를 함께 사용하면 `HallucinationDetector`(NLP 기반)와 `faithfulness`(LLM 기반) 두 신호를 동시에 얻어 환각 탐지 정밀도가 높아진다.

### 6.2.2 RetryCorrectionTracker — 재시도·자가수정 추적

에이전트가 실패 후 재시도하거나 응답을 스스로 수정하는 행동을 추적한다. 재시도가 성공으로 이어지는지, 아니면 동일한 실패를 반복하는지를 측정한다.

**측정 항목** (`["efficiency_metrics"]["retries"]`)**:**

| 항목 | 설명 |
|------|------|
| `total_tasks_with_retries` | 재시도가 발생한 총 태스크 수 |
| `retry_rate` | 전체 태스크 중 재시도가 발생한 비율 (%) |
| `first_attempt_success_rate` | 첫 시도 성공률 (%) |
| `eventual_success_rate` | 최종 성공률 — 재시도 포함 (%) |
| `retry_success_count` | 재시도 후 성공으로 전환된 태스크 수 |
| `correction_success_rate` | 재시도로 오류를 수정한 비율 (%) |
| `avg_attempts_per_task` | 태스크당 평균 시도 횟수 |
| `avg_retries_per_task` | 태스크당 평균 재시도 횟수 (avg_attempts − 1) |
| `total_retry_time` | 재시도에 소요된 총 시간 (초) |
| `avg_retry_time` | 재시도당 평균 소요 시간 (초) |
| `overall_retry_rate` | 전체 시도 중 재시도 비율 (%) |

```python
# 개념 코드 — RetryCorrectionTracker attempts/errors 기록 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

# 재시도 정보 기록 — attempts > 1 태스크만 tracker에 포함됨 (t2는 제외)
for task_id, question, response, ground_truth, attempts, errors in [
    ("t1", "복잡한 계산 태스크",   "최종 답변: 42", "42",  3, ["timeout", "invalid_format"]),
    ("t2", "단순 조회 태스크",     "조회 결과: OK", "OK",  1, []),   # 재시도 없음 — tracker 미포함
    ("t3", "네트워크 호출 태스크", "응답: 200",     "200", 2, ["connection_reset"]),
]:
    monitor.record_task(create_taskresult(
        task_id=task_id, question=question, response=response,
        execution_time=float(attempts), task_type="reasoning",
        attempts=attempts, errors=errors, ground_truth=ground_truth,
    ))

retries = (monitor.generate_report().to_dict().get("efficiency_metrics") or {}).get("retries", {})
print(f"재시도율:         {retries.get('retry_rate', 0):.1f}%")                # → 100.0%
print(f"첫 시도 성공률:   {retries.get('first_attempt_success_rate', 0):.1f}%")  # → 0.0%
print(f"최종 성공률:      {retries.get('eventual_success_rate', 0):.1f}%")     # → 100.0%
print(f"전체 재시도 비율: {retries.get('overall_retry_rate', 0):.1f}%")        # → 60.0%
```

> **`RetryCorrectionTracker` 설계 특성 — 수치 해석 전 반드시 숙지**
>
> `RetryCorrectionTracker`는 **`attempts > 1`인 태스크만** 내부에서 추적한다. 위 예제에서 t2(attempts=1)는 tracker에 포함되지 않아, 집계 대상은 t1(attempts=3)과 t3(attempts=2)뿐이다.
>
> | 지표 | 계산 | 결과 | 해석 |
> |------|------|------|------|
> | `retry_rate` | 추적된 태스크 중 재시도 발생 비율 | **100.0%** | 추적 대상이 재시도 태스크뿐이므로 항상 100% — "재시도 태스크가 존재하는가"를 확인하는 용도로만 사용 |
> | `first_attempt_success_rate` | 추적된 태스크의 첫 시도 성공 비율 | **0.0%** | 재시도 태스크만 추적하므로 항상 0% — 의미 있는 수치 아님 |
> | `overall_retry_rate` | `(총 시도 횟수 - 태스크 수) / 총 시도 횟수 × 100` → `(5 - 2) / 5 × 100` | **60.0%** | 실제 시스템 부하 관점에서 가장 유용한 지표 |
> | `eventual_success_rate` | 추적된 태스크 중 최종 성공 비율 | **100.0%** | "재시도 전략이 효과 있는가"를 직접적으로 보여줌 |
>
> `overall_retry_rate` 분자 `(총 시도 횟수 - 태스크 수)`가 재시도 횟수가 되는 이유: 각 태스크는 반드시 첫 번째 시도가 1회 존재하므로, 전체 시도에서 태스크 수만큼 빼면 순수 재시도 횟수만 남는다. 위 예제에서는 t1의 2회 + t3의 1회 = 3회다.
>
> 프로덕션 모니터링에서 실질적으로 의미 있는 지표는 **`overall_retry_rate`**와 **`eventual_success_rate`**다. `retry_rate`는 항상 100%이므로 절댓값보다 재시도 태스크 존재 여부 확인에만 활용한다.

- `attempts=3`을 `create_taskresult()`에 전달하면 `RetryCorrectionTracker`가 해당 태스크를 재시도로 자동 분류하며, `attempts > 1`이면 추적 대상에 포함된다.
- `errors=[...]` 필드는 실패 원인을 저장하지만 retry 집계 계산에는 반영되지 않는다. 재시도 성공·실패 판정은 `attempts` 수만으로 결정되며 마지막 시도가 항상 성공으로 간주된다.
- `eventual_success_rate`가 낮다면 재시도 로직이 같은 실패를 반복하고 있다는 신호로, 폴백 전략이나 오류 처리 개선이 필요하다.

> 👨‍💻 **개발자 TIP**: `create_taskresult(attempts=N)`으로 재시도 횟수를 명시해야 `RetryCorrectionTracker`가 집계한다. `@agent_eval(retry=RetryConfig(...))` 사용 시 재시도 횟수가 자동 기록되므로 별도 전달이 불필요하다. `attempts=1`인 태스크는 집계에서 제외됨에 주의한다.

> 📋 **QA 관리자 TIP**: `overall_retry_rate > 20%`이면 에이전트의 첫 시도 실패율이 높다는 신호다. `eventual_success_rate < 80%`이면 재시도 전략 자체가 효과 없으므로 오류 처리 로직 개선이 필요하다.
> - 권장 기준: `overall_retry_rate < 15%` / `eventual_success_rate > 90%`
> - 경보 기준: `eventual_success_rate < 70%`이면 재시도 정책 즉시 재검토

---

## 6.3 Config 5종 레퍼런스

### 6.3.1 ReproducibilityConfig — 재현성 측정

동일한 입력을 N회 실행해 응답의 일관성을 측정한다. AI Native 관점의 "확률론적 품질"을 직접 측정하는 핵심 Config다.

```python
# 개념 코드 — ReproducibilityConfig 전체 파라미터 참고
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py — reproducible_agent 참고)
from agent_evaluator import ReproducibilityConfig

ReproducibilityConfig(
    runs=3,                              # 동일 입력 반복 실행 횟수
    similarity_measure="token_f1",       # "token_f1"|"jaccard"|"exact"
    reproducibility_threshold=0.85,      # 재현성 합격 임계값 (0.0~1.0)
    fail_on_low_reproducibility=False,   # True 시 임계값 미달 → success=False
    skip_side_effects=False,             # True 시 부수효과 함수 재실행 건너뜀
)
```

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `runs` | `int` | `3` | 동일 입력 반복 실행 횟수 |
| `similarity_measure` | `str` | `"token_f1"` | `"token_f1"` `"jaccard"` `"exact"` |
| `reproducibility_threshold` | `float` | `0.85` | 재현성 합격 임계값 (0.0~1.0) |
| `fail_on_low_reproducibility` | `bool` | `False` | 임계값 미달 시 `TaskResult.success=False` |
| `skip_side_effects` | `bool` | `False` | 부수효과(DB 쓰기 등) 있는 함수 건너뜀 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `reproducibility_threshold` | `0.85` | 의료·금융: `0.90+` / 고객 응대: `0.80` / 창의적 작업: `0.60` |
| `runs` | `3` | 통계 안정성이 필요한 경우 `5`로 높임 |
| `fail_on_low_reproducibility` | `False` | 프로덕션 배포 차단 필요 시 `True` |

**similarity_measure 선택 가이드:**

| similarity_measure | 특징 | 권장 상황 |
|-------------------|------|---------|
| `token_f1` | 토큰 단위 정밀도-재현율 F1 조화평균 | QA, 사실 응답 (기본 권장) |
| `jaccard` | 순서 무관 단어 집합 유사도 | 긴 설명형 응답 |
| `exact` | 완전히 동일한 응답만 1.0 | 구조화 출력 (JSON, 코드) |

**사용 예시 — 금융 정보 에이전트:**

```python
# 실행 가능 예제 — 금융 정보 에이전트 ReproducibilityConfig
# (전체 예제: Evaluator_Examples/ch06_group_c.py — reproducible_agent 참고)
from agent_evaluator import PerformanceMonitor, ReproducibilityConfig, agent_eval

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    monitor,
    task_type="qa",
    reproducibility=ReproducibilityConfig(
        runs=5,                              # 5회 실행으로 분포 측정
        similarity_measure="token_f1",       # "token_f1"|"jaccard"|"exact"
        reproducibility_threshold=0.90,      # 금융 정보 — 높은 재현성 요구
        fail_on_low_reproducibility=True,    # 기준 미달 시 배포 자동 차단
        skip_side_effects=False,
    ),
)
def finance_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 실제 LLM 호출로 교체하세요.
    return f"금융 정보 답변: {question}에 대한 분석 결과입니다."

finance_agent("금리 인상이 주가에 미치는 영향은?", ground_truth="금리 인상 시 주가 하락 경향")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"재현성 점수: {gate_c_details.get('avg_reproducibility', 'N/A')}")
# → 재현성 점수: 1.0
```

> **채점 경로 — 이 예제가 1.0을 받는 이유**
>
> `finance_agent`는 결정론적 함수이므로 `runs=5`의 5회 실행이 모두 동일한 응답을 생성한다. `C(5,2)=10`쌍의 `token_f1`이 전부 1.0이 되어 pairwise 평균인 `avg_reproducibility`도 1.0이 된다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | 실행 횟수 | `run_count=5 ≥ 2` | 정상 경로 진입 |
> | 응답 동일성 | 5회 모두 동일 문자열 반환 | `token_f1=1.0` (전 쌍) |
> | pairwise 평균 | `C(5,2)=10` 쌍 전부 `1.0` | `score=1.0` |
> | 분산 | 모든 쌍이 동일값 | `variance=0.0` |
>
> 실제 LLM 에이전트는 동일 입력에도 응답이 달라질 수 있어 `score < 1.0`이 자주 발생한다. `fail_on_low_reproducibility=True` 설정 시 `score < reproducibility_threshold(0.90)`이면 해당 태스크가 실패 처리된다.

**재현성 임계값 가이드:**

| 도메인 | 권장 threshold | 이유 |
|--------|--------------|------|
| 의료·금융 | 0.90+ | 일관성 없는 정보는 치명적 |
| 고객 응대 | 0.80 | 일관된 서비스 경험 필요 |
| 창의적 작업 | 0.60 | 다양성이 오히려 가치 있음 |
| 코드 생성 | 0.85 | 동일 요구사항엔 유사한 코드 |

> 👨‍💻 **개발자 TIP**: `runs=5`이면 C(5,2)=10쌍의 pairwise 비교가 실행되어 API 비용이 5배 증가한다. `runs=3`을 기본값으로 시작하고 안정 후 올리는 것을 권장한다. `fail_on_low_reproducibility=True`로 설정하면 기준 미달 시 해당 태스크가 실패 처리되어 Gate C 점수에 반영된다.

> 📋 **QA 관리자 TIP**: `avg_reproducibility < 0.70`이면 LLM 응답 일관성이 심각하게 낮은 것이므로 프롬프트 개선이 필요하다.
> - 권장 기준: 의료·금융 `≥ 0.90` / 고객 응대 `≥ 0.80` / 창의적 작업 `≥ 0.60`
> - 경보 기준: `avg_reproducibility < 0.70`이면 배포 차단 검토

### 6.3.2 FaultToleranceConfig — 장애 내성

에이전트가 도구 실패나 부분적인 오류 상황에서 적절한 폴백(fallback) 전략을 사용하는지 측정한다.

```python
# 개념 코드 — FaultToleranceConfig 전체 파라미터 참고
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py — fault_tolerant_agent 참고)
from agent_evaluator import FaultToleranceConfig

FaultToleranceConfig(
    check_fallback_attempts=True,           # 실패 후 폴백 도구 사용 여부 추적
    partial_success_threshold=0.5,          # 부분 성공 임계값 (0.0~1.0)
    score_recovery_quality=True,            # 폴백 복구 품질 채점 여부
    expected_fallback_tools={},             # 도구명 → 폴백 도구 목록 (미선언 시 폴백 검사 불가)
)
```

**사용 예시 — 데이터베이스 쿼리 에이전트:**

```python
# 실행 가능 예제 — DB 폴백 에이전트 FaultToleranceConfig
# (전체 예제: Evaluator_Examples/ch06_group_c.py — fault_tolerant_agent 참고)
from agent_evaluator import PerformanceMonitor, FaultToleranceConfig, EvalMetadata, agent_eval

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    monitor,
    task_type="tool_use",
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.5,
        score_recovery_quality=True,
        expected_fallback_tools={"main_db": ["replica_db", "cache"]},
    ),
)
def db_agent(question: str, ground_truth: str = "") -> tuple:
    # EvalMetadata(tool_calls=[...]): main_db 실패 → replica_db 폴백 성공 시나리오 시뮬레이션
    # 현업에서는 실제 도구 호출 결과가 tool_calls에 자동으로 기록됨
    tool_calls = [
        {"name": "main_db",    "success": False, "error": "connection_timeout"},
        {"name": "replica_db", "success": True},
    ]
    return (
        f"부분 완료(폴백): 레플리카 DB에서 응답합니다. {question}",
        EvalMetadata(tool_calls=tool_calls),
    )

db_agent("최근 거래 내역을 조회해줘", ground_truth="거래 내역 조회")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"장애 내성 점수: {gate_c_details.get('avg_fault_tolerance', 'N/A')}")
# → 장애 내성 점수: 1.0
```

> **채점 경로 — 이 예제가 1.0을 받는 이유**
>
> `avg_fault_tolerance`는 `recovery_rate`(실패 도구 수 대비 복구 성공 수)를 집계한다. 이 예제는 "주 DB 실패 → 허용된 폴백으로 완전 복구" 시나리오이므로 1.0이 정확한 결과다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | 실패 탐지 | `main_db success=False` | `failed_indices=[0]` |
> | 폴백 탐지 | 다음 인덱스 도구가 다른 이름 | `fallback_attempts=1` |
> | 폴백 검증 | `"replica_db"` ∈ `expected_fallback_tools["main_db"]` | 허용된 폴백 ✅ |
> | 복구 성공 | `replica_db success=True` | `recovered=1` |
> | recovery_rate | `1 / 1` | **1.0** → `grade="good"` |
>
> `score_recovery_quality=True`로 생성되는 `recovery_quality_score`(`grade → 0~1` 변환값)는 참고용으로만 저장되며 `avg_fault_tolerance` 집계에는 사용되지 않는다. `grade="wrong_fallback"`처럼 허용 외 폴백을 쓴 경우 `recovery_rate=1.0`이지만 `recovery_quality_score=0.2`로 달라지므로 두 값을 혼동하지 않도록 주의한다.

- `check_fallback_attempts=True`는 기본 도구 실패 후 대체 도구로 전환하는 폴백 행동을 추적하며, 폴백이 없으면 장애 내성 점수가 낮아진다.
- `partial_success_threshold=0.5`는 완전 성공이 아닌 부분 완료 태스크를 허용하는 기준이며, 0.5 이상이면 부분 성공으로 인정한다.
- 분산 서비스 에이전트에서 주 DB 실패 시 레플리카나 캐시로 폴백하는 패턴이 이 Config의 대표 활용 사례다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `check_fallback_attempts` | `bool` | `True` | 실패 후 폴백 도구 사용 여부 추적 |
| `partial_success_threshold` | `float` | `0.5` | 부분 성공 인정 임계값 (0.0~1.0) |
| `score_recovery_quality` | `bool` | `True` | 폴백 복구 품질 채점 여부 |
| `expected_fallback_tools` | `Dict[str, List[str]]` | `{}` (매핑 없음) | 도구명 → 폴백 도구 목록. **미선언 시 폴백 전환 검사 불가** |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `partial_success_threshold` | `0.5` | 엄격 서비스: `0.7` / 허용적 서비스: `0.3` |
| `expected_fallback_tools` | `{}` | 폴백 전략이 있는 시스템이라면 직접 선언 필수 |

> 👨‍💻 **개발자 TIP**: `expected_fallback_tools={"main_db": ["replica_db", "cache"]}`처럼 폴백 매핑을 선언해야 `avg_fault_tolerance`가 정확히 집계된다. 선언하지 않으면 폴백 전환 여부를 추적할 수 없다. 에러를 내부에서 catch한 경우 반드시 `EvalMetadata(errors=[...], tool_calls=[...])` 튜플을 반환해야 한다.

> 📋 **QA 관리자 TIP**: `avg_fault_tolerance < 0.70`이면 장애 시 폴백 전략이 제대로 동작하지 않는다는 신호다. 분산 서비스·외부 API 의존 에이전트에서 필수로 확인한다.
> - 권장 기준: 미션 크리티컬 서비스 `≥ 0.90` / 일반 서비스 `≥ 0.75`
> - 경보 기준: `avg_fault_tolerance < 0.50`이면 폴백 로직 즉시 점검

### 6.3.3 GracefulDegradationConfig — 우아한 성능 저하

에이전트가 최적 조건이 아닐 때(도구 실패, 컨텍스트 부족, 타임아웃 등) 완전한 실패 대신 부분적인 결과를 제공하는지 측정한다. "모든 것을 실패하거나, 모든 것을 성공하거나" 대신 "가능한 것을 제공하고 부족함을 인정하는" 패턴을 장려한다.

```python
# 개념 코드 — GracefulDegradationConfig 전체 파라미터 참고
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py — fault_tolerant_agent 참고)
from agent_evaluator import GracefulDegradationConfig

GracefulDegradationConfig(
    quality_floor=0.3,                   # 최소 품질 기준 (이 이하면 빈 응답과 동일)
    partial_result_markers=[],           # 부분 결과를 나타내는 마커
    detect_timeout_fallback=True,        # 타임아웃 폴백 감지 여부
    empty_response_penalty=1.0,          # 빈 응답에 대한 패널티 (1.0 = 최대 감점)
    check_error_acknowledgment=True,     # 오류 발생 시 에이전트가 명시적으로 인정하는지 확인
)
```

**사용 예시:**

```python
# 실행 가능 예제 — GracefulDegradationConfig 우아한 저하 패턴
# (전체 예제: Evaluator_Examples/ch06_group_c.py — fault_tolerant_agent 참고)
from agent_evaluator import PerformanceMonitor, GracefulDegradationConfig, EvalMetadata, agent_eval

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    monitor,
    task_type="qa",
    graceful_degradation=GracefulDegradationConfig(
        quality_floor=0.4,
        partial_result_markers=["부분", "폴백", "fallback", "partial"],
        detect_timeout_fallback=True,
        empty_response_penalty=0.8,
        check_error_acknowledgment=True,
    ),
)
def robust_agent(question: str, ground_truth: str = "") -> tuple:
    try:
        raise TimeoutError("모의 타임아웃")  # 실제 에이전트 구현으로 교체하세요
    except TimeoutError as e:
        response = "죄송합니다. 현재 처리가 지연되고 있습니다. 부분적인 결과를 제공합니다: 캐시 응답"
        # EvalMetadata(errors=[...]): 내부에서 catch한 에러를 데코레이터에 알림
        # has_error=True → graceful_degradation이 "partial" 모드로 채점 (score=0.6)
        return response, EvalMetadata(errors=[f"TimeoutError: {e}"])
    except Exception:
        return "요청을 완전히 처리하지 못했습니다. 다시 시도해주세요."

robust_agent("현재 시스템 상태를 알려줘", ground_truth="시스템 정상")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"우아한 저하 점수: {gate_c_details.get('avg_degradation', 'N/A')}")
# → 우아한 저하 점수: 0.6
```

> **채점 경로 — 이 예제가 0.6을 받는 이유**
>
> 이 예제는 `EvalMetadata(errors=[...])` 전달로 `has_error=True`가 되고, 응답에 "부분" 마커가 포함되어 `mode="partial"` 경로로 채점된다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | `is_empty` | 응답 길이 > 0 | `False` |
> | `has_error` | `EvalMetadata(errors=[...])` 전달 | `True` |
> | `has_partial_result` | 응답에 "부분" 포함 (`partial_result_markers` 매칭) | `True` |
> | 경로 선택 | `has_error and has_partial_result` | `mode="partial"` |
> | 최종 점수 | `max(quality_floor=0.4, 0.6)` | **0.6** |
>
> 응답에 부분 결과 마커가 없었다면 `mode="acknowledged"` → `0.5`, 에러 인정 마커도 없었다면 `mode="degraded"` → `quality_floor=0.4`가 된다.

- `quality_floor=0.4`는 에이전트가 제공하는 최소 품질 기준으로, 이 점수 이하의 응답은 빈 응답과 동일하게 취급해 감점된다.
- `check_error_acknowledgment=True`는 에이전트가 오류 발생 시 명시적으로 인정하는 응답을 반환하는지 확인한다.
- `partial_result_markers`에 선언한 문자열(예: "부분", "폴백", "partial")이 응답에 포함되면 부분 완료로 인식해 완전 실패보다 높은 점수를 부여한다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `partial_result_markers` | `List[str]` | `["partial", "incomplete", "best effort", "부분", "일부", "완전하지 않"]` | 부분 결과를 나타내는 응답 마커 |
| `quality_floor` | `float` | `0.3` | 최소 품질 기준 (이 이하면 빈 응답과 동일 처리) |
| `detect_timeout_fallback` | `bool` | `True` | 타임아웃 폴백 감지 여부 |
| `empty_response_penalty` | `float` | `1.0` | 빈 응답에 대한 패널티 (1.0 = 최대 감점) |
| `check_error_acknowledgment` | `bool` | `True` | 오류 발생 시 에이전트가 명시적으로 인정하는지 확인 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `quality_floor` | `0.3` | 최소 서비스 수준에 따라 `0.3~0.5` 조정 |
| `empty_response_penalty` | `1.0` | 빈 응답이 치명적인 서비스: `1.0` 유지 |
| `partial_result_markers` | 6개 기본 마커 | 한국어 서비스에 맞게 "폴백", "fallback" 추가 |

> 👨‍💻 **개발자 TIP**: 에러를 내부에서 catch한 경우 반드시 `EvalMetadata(errors=[...])` 튜플로 반환해야 `has_error=True`로 인식된다. 이 없이 일반 문자열로 반환하면 `mode="normal"`로 오채점된다. `partial_result_markers`에 서비스 언어에 맞는 마커를 추가하면 부분 완료 탐지 정밀도가 높아진다.

> 📋 **QA 관리자 TIP**: `avg_degradation < quality_floor`이면 에이전트가 부분 응답조차 제공하지 못하는 상황이다. 에러 인정 메시지와 캐시 응답 등 최소한의 폴백 응답이 구현되어 있는지 확인한다.
> - 권장 기준: `avg_degradation ≥ 0.50` — 장애 시에도 최소 절반 품질은 유지
> - 경보 기준: `avg_degradation < 0.30`이면 "빈 응답"에 가까운 수준으로 즉시 개선 필요

### 6.3.4 RetryConsistencyConfig — 재시도 일관성

재시도 횟수와 결과를 기반으로 재시도 전략의 효율성을 평가한다. "재시도가 실제로 성공으로 이어지는가?"를 측정한다.

```python
# 개념 코드 — RetryConsistencyConfig 전체 파라미터 참고
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py — retry_consistent_agent 참고)
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
# 실행 가능 예제 — RetryConfig + RetryConsistencyConfig 조합 패턴
# (전체 예제: Evaluator_Examples/ch06_group_c.py — retry_consistent_agent 참고)
from agent_evaluator import PerformanceMonitor, RetryConsistencyConfig, EvalMetadata, agent_eval, RetryConfig

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    monitor,
    task_type="qa",
    retry_consistency=RetryConsistencyConfig(
        group_by_task_prefix=True,
        improvement_threshold=0.1,
        penalize_degradation=True,
        min_retry_count=2,
    ),
    retry=RetryConfig(max=3, on=(ValueError,), delay=0.0),
)
def retry_consistent_agent(question: str, ground_truth: str = "") -> tuple:
    # EvalMetadata(attempts=2): 1회 실패 후 재시도 성공 시나리오를 시뮬레이션
    # 현업에서는 RetryConfig의 on=(ValueError,)가 실제로 발동될 때 자동으로 기록됨
    return f"일관된 재시도 응답: {question}", EvalMetadata(attempts=2)

retry_consistent_agent("API 호출 결과를 반환해줘", ground_truth="API 응답 성공")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"재시도 일관성 점수: {gate_c_details.get('avg_retry_consistency', 'N/A')}")
# → 재시도 일관성 점수: 0.85
```

> **채점 경로 — 이 예제가 0.85를 받는 이유**
>
> `EvalMetadata(attempts=2)`는 1회 실패 후 2번째 시도에서 성공한 시나리오를 나타낸다. 성공 여부와 시도 횟수를 기반으로 efficiency 점수가 결정된다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | `attempts=2 ≥ min_retry_count=2` | 통계 포함 조건 충족 | 계산 진행 |
> | `success=True` | 최종적으로 성공 | efficiency 경로 선택 |
> | efficiency 계산 | `1.0 − (attempts−1) × 0.15` = `1.0 − 1 × 0.15` | **0.85** |
>
> 시도 횟수가 늘어날수록 efficiency가 감소한다(`attempts=3` → `0.70`, `attempts=4` → `0.55`). `min_retry_count=2` 조건을 충족하지 못하면 `None`이 반환되어 `avg_retry_consistency` 집계에서 제외된다.

- `RetryConfig`는 실패 시 자동 재시도를 *실행*하고, `RetryConsistencyConfig`는 그 재시도가 실제로 개선으로 이어졌는지를 *측정*하는 별개의 역할을 한다.
- `improvement_threshold=0.1`은 재시도 후 점수가 0.1 이상 올라야 개선으로 인정하며, 이 기준 이하면 재시도 효과가 없다고 판단한다.
- `penalize_degradation=True`는 재시도 후 오히려 점수가 낮아진 경우 패널티를 부여해 무의미한 재시도 전략을 조기에 발견할 수 있게 한다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `group_by_task_prefix` | `bool` | `True` | `task_id` 접두사 기준으로 태스크 그룹화 |
| `improvement_threshold` | `float` | `0.1` | 재시도 후 개선으로 인정할 최소 점수 상승폭 |
| `penalize_degradation` | `bool` | `True` | 재시도 후 성능 저하 시 패널티 부과 |
| `min_retry_count` | `int` | `2` | 통계에 포함할 최소 재시도 횟수 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `improvement_threshold` | `0.1` | 엄격 검증: `0.15` / 느슨한 검증: `0.05` |
| `min_retry_count` | `2` | 재시도 데이터가 충분한 경우 `3` 이상으로 높임 |

> 👨‍💻 **개발자 TIP**: `EvalMetadata(attempts=N)`으로 시도 횟수를 명시해야 채점이 가능하다. `attempts < min_retry_count`이면 `None`이 반환되어 Gate C 집계에서 제외된다. `RetryConfig`와 함께 사용하면 재시도 실행과 일관성 측정이 동시에 이루어진다.

> 📋 **QA 관리자 TIP**: `avg_retry_consistency < 0.70`이면 재시도가 성공으로 이어지지 못하거나 오히려 성능이 저하되는 패턴이 있다는 신호다. 재시도 횟수별 성공률을 함께 확인해야 한다.
> - 권장 기준: `avg_retry_consistency ≥ 0.80` — 재시도가 실제 개선으로 이어져야 함
> - 경보 기준: `avg_retry_consistency < 0.60`이면 재시도 정책·오류 처리 로직 재검토

### 6.3.5 IdempotencyConfig — 멱등성 평가

**초급자를 위한 멱등성 설명**: 멱등성(Idempotency)이란 "같은 작업을 몇 번 반복해도 결과가 달라지지 않는" 성질이다. 예를 들어 "주문 1번을 조회"는 몇 번 실행해도 같은 결과가 나오므로 멱등하다. 반면 "주문 생성"은 실행할 때마다 새 주문이 만들어지므로 멱등하지 않다. AI 에이전트가 도구를 중복 호출하면 이메일이 두 번 전송되거나 결제가 두 번 처리되는 등 실제 피해가 발생할 수 있다. `IdempotencyConfig`는 에이전트가 이런 비멱등 도구를 불필요하게 반복 호출하는지 탐지하고 감점한다.

동일한 도구를 반복 실행했을 때 부작용(side effect)이 발생하는지 평가한다. 데이터 생성·삭제·수정 등 비멱등(non-idempotent) 도구를 불필요하게 반복 호출하면 감점된다.

```python
# 개념 코드 — IdempotencyConfig 전체 파라미터 참고
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py — idempotent_agent 참고)
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
# 실행 가능 예제 — DB 쓰기 에이전트 IdempotencyConfig
# (전체 예제: Evaluator_Examples/ch06_group_c.py — _c_fail_agent 참고)
from agent_evaluator import PerformanceMonitor, IdempotencyConfig, EvalMetadata, agent_eval

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    monitor,
    task_type="tool_use",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create_record", "delete_record", "update_field"],
        duplicate_detection_markers=["already", "duplicate", "이미", "중복"],
        non_idempotent_penalty=0.3,
        warn_on_non_idempotent=True,
    ),
)
def db_write_agent(question: str, ground_truth: str = "") -> tuple:
    # EvalMetadata(tool_calls=[...]): create_record 쓰기 도구 호출 시뮬레이션
    # non_idempotent_patterns에 매칭 → penalty=0.3 → score=1.0-0.3=0.7
    # 현업에서는 실제 도구 호출 결과가 tool_calls에 자동으로 기록됨
    tool_calls = [{"name": "create_record", "success": True}]
    return (
        f"레코드 생성 완료: {question}에 대한 신규 항목이 등록되었습니다.",
        EvalMetadata(tool_calls=tool_calls),
    )

db_write_agent("최근 주문 목록을 조회해줘", ground_truth="주문 조회 완료")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"멱등성 점수: {gate_c_details.get('avg_idempotency', 'N/A')}")
# → 멱등성 점수: 0.7
```

> **채점 경로 — 이 예제가 0.7을 받는 이유**
>
> `tool_calls`의 도구 이름이 `non_idempotent_patterns`와 매칭되면 `non_idempotent_penalty`를 누적 감산한다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | 도구 이름 추출 | `tool_calls[0]["name"]` | `"create_record"` |
> | 패턴 매칭 | `"create_record"` ∈ `non_idempotent_patterns` | 비멱등 도구 1개 탐지 |
> | 중복 감지 마커 | 응답에 `duplicate_detection_markers` 없음 | `duplicate_detected=False` |
> | 감점 계산 | `1개 × penalty=0.3` | `total_penalty=0.3` |
> | 최종 점수 | `1.0 − 0.3` | **0.7** |
>
> 에이전트 응답에 "이미 등록된 항목입니다"처럼 `duplicate_detection_markers` 마커가 포함됐다면 `base_score += 0.1` 보너스가 추가되어 `0.8`이 된다.

- `non_idempotent_patterns`에 선언한 패턴이 `tool_calls`의 도구 이름과 매칭되면 비멱등 호출로 기록하고 `non_idempotent_penalty`만큼 점수를 감점한다.
- `duplicate_detection_markers`에 선언한 문자열이 응답에 포함되면 에이전트가 중복 실행을 스스로 감지했다는 보너스 점수를 부여한다.
- 데이터베이스 쓰기·이메일 전송·결제 처리처럼 중복 실행이 치명적인 에이전트에 필수로 적용한다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `non_idempotent_patterns` | `List[str]` | `["create", "delete", "insert", "update", "post", "write", "생성", "삭제", "저장", "수정", "전송"]` | 비멱등 도구 이름 패턴 목록 |
| `duplicate_detection_markers` | `List[str]` | `["already", "duplicate", "exists", "이미", "중복", "존재"]` | 중복 탐지 응답 마커 (보너스 점수) |
| `non_idempotent_penalty` | `float` | `0.2` | 비멱등 도구 호출당 감점 폭 |
| `warn_on_non_idempotent` | `bool` | `True` | 비멱등 호출 시 경고 로깅 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `non_idempotent_penalty` | `0.2` | 결제·이메일처럼 치명적 중복: `0.5` / 일반 쓰기: `0.2` |
| `non_idempotent_patterns` | 11개 기본 패턴 | 서비스 도구명에 맞게 `"create_order"`, `"send_email"` 등 추가 |

> 👨‍💻 **개발자 TIP**: `non_idempotent_patterns`에 실제 서비스 도구명을 추가해야 정확한 탐지가 가능하다. 예: `["create_order", "send_email", "process_payment"]`. `duplicate_detection_markers`에 "이미 처리된", "중복 요청" 같은 마커를 추가하면 에이전트가 중복 실행을 스스로 감지했을 때 보너스 점수를 받는다.

> 📋 **QA 관리자 TIP**: `avg_idempotency < 0.80`이면 비멱등 도구 호출이 자주 발생하는 것이다. 결제·이메일 발송·DB 삽입처럼 중복 실행이 치명적인 도구를 가진 에이전트에서 필수 확인 지표다.
> - 권장 기준: 결제·이메일 등 치명적 서비스 `≥ 0.95` / 일반 쓰기 서비스 `≥ 0.80`
> - 경보 기준: `avg_idempotency < 0.70`이면 비멱등 호출 패턴 즉시 감사(audit) 필요

---

## 6.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 의료·금융 정보 에이전트 (고신뢰성 요구)

```python
# 실행 가능 예제 — 의료·금융 고신뢰성 에이전트 Gate C 구성 패턴
# (전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
# LLMJudge 활성화 시: agent-eval init 으로 API 키 설정 후 sample_rate 조정
from agent_evaluator import (
    PerformanceMonitor, ReproducibilityConfig, LLMJudgeConfig, agent_eval, load_env,
)

load_env()  # .env 파일에서 API 키 로드 (LLMJudgeConfig 사용 시 필요)

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,   # Layer 1 내장 — 외부 의존성 없음
    use_korean_tokenizer=True,
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
        model="gpt-5-nano",
        criteria=["factual_accuracy", "medical_safety"],
        sample_rate=0.0,   # 데모용 — API 키 설정 후 0.5로 변경
    ),
)
def medical_info_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    # TODO(현업 적용): 실제 LLM 호출로 교체하세요.
    if context:
        return f"제공된 문맥에 근거한 답변: {question} — {context[:60]}"
    return f"일반 의료 정보: {question}에 대한 안전한 답변입니다."

medical_info_agent(
    "아스피린 복용 시 주의사항은?",
    context="아스피린(아세틸살리실산)은 혈액 응고를 억제하므로 수술 전 복용을 중단해야 한다.",
    ground_truth="수술 전 복용 중단 필요",
)

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
hall_data = (d.get("accuracy_metrics") or {}).get("hallucination", {})
print(f"재현성 점수:       {gate_c_details.get('avg_reproducibility', 'N/A')}")
print(f"환각 탐지율:       {hall_data.get('overall_rate', 'N/A')}%")
```

- 의료·금융 도메인은 `reproducibility_threshold=0.90`으로 재현성 요구를 높이고, `fail_on_low_reproducibility=True`로 기준 미달 시 배포를 자동 차단한다.
- `criteria=["factual_accuracy", "medical_safety"]`처럼 도메인 특화 기준을 G-Eval로 선언하면 일반 품질 지표 외에 전문 영역 안전성을 추가로 평가한다.
- `enable_hallucination_detection=True`는 NLP 기반 탐지, `llm_judge`는 LLM 기반 탐지로, 두 방식을 결합하면 환각 탐지의 재현율과 정밀도가 모두 높아진다.

> **RAG 에이전트에서 Gate C(환각 탐지) 없이 배포하면**: 검색된 컨텍스트와 다른 내용을 자신감 있게 답변하는 에이전트가 프로덕션에 배포된다. 의료 정보 봇이 "아스피린은 모든 성인에게 안전하다"고 환각을 생성했을 때, `HallucinationDetector`가 없으면 이 사실 불일치를 자동으로 탐지할 방법이 없다. Gate C 없는 RAG 에이전트는 Gate A(목표달성) 점수가 높아도 실제 배포 위험이 존재한다.

### 패턴 2 — 분산 서비스 에이전트 (장애 내성 중심)

```python
# 실행 가능 예제 — 분산 서비스 에이전트 장애 내성 패턴
# (전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
from agent_evaluator import (
    PerformanceMonitor, EvalMetadata, agent_eval,
    FaultToleranceConfig, GracefulDegradationConfig,
    RetryConsistencyConfig, RetryConfig,
)

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

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
        min_retry_count=2,
    ),
)
def resilient_agent(question: str, ground_truth: str = "") -> tuple:
    # TODO(현업 적용): raise를 distributed_agent.run(question) 실제 호출로 교체하세요.
    #   실제 tool_calls는 에이전트 실행 결과에서 자동으로 채워집니다.
    try:
        raise ConnectionError("primary_api 타임아웃")
    except ConnectionError as e:
        response = f"부분 완료(폴백): backup_api에서 응답합니다. {question}"
        tool_calls = [
            {"name": "primary_api", "success": False, "error": str(e)},
            {"name": "backup_api",  "success": True},
        ]
        return response, EvalMetadata(
            tool_calls=tool_calls,
            errors=[f"ConnectionError: {e}"],
            attempts=2,
        )

resilient_agent("외부 API에서 최신 환율 데이터를 조회해줘", ground_truth="USD/KRW 환율 조회")

report = monitor.generate_report()
d = report.to_dict()
gate_c_details = (d.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})
print(f"장애 내성 점수:   {gate_c_details.get('avg_fault_tolerance',   'N/A')}")
print(f"우아한 저하 점수: {gate_c_details.get('avg_degradation',        'N/A')}")
print(f"재시도 일관성:    {gate_c_details.get('avg_retry_consistency',  'N/A')}")
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
# 개념 코드 — 환각 집계 통계 접근 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch06_group_c.py 참고)
# 환각 집계 통계 확인
report = monitor.generate_report()
d = report.to_dict()

hall_data = (d.get("accuracy_metrics") or {}).get("hallucination", {})
avg_rate = hall_data.get("overall_rate", 0)      # 단위: % (0~100)
total = hall_data.get("total_flagged", 0)         # 환각 판정된 태스크 수
total_checked = hall_data.get("total_tasks_checked", 0)  # 탐지 대상 전체 태스크 수

print(f"환각률 평균: {avg_rate:.1f}%")
print(f"환각 탐지: {total}/{total_checked}건")
if avg_rate > 30:
    print("⚠️  고위험 — 배포 전 프롬프트 개선 및 RAG 품질 점검 필요")
```

- `report.to_dict()`는 집계 통계만 제공한다. 태스크별 환각 점수 분포를 보려면 `monitor.tasks` 리스트를 직접 순회하거나 `LLMJudge`를 활용한다.
- `overall_rate`가 높더라도 `total_checked`가 적으면 신뢰 구간이 넓으므로 데이터를 더 수집한 뒤 판단해야 한다.
- `scores > 0.5`인 고위험 태스크 비율이 5% 이상이면 배포 전에 해당 태스크의 입력 유형을 분석해 취약 구간을 찾아야 한다.

### 6.5.2 재현성과 드리프트의 연결

`ReproducibilityConfig`는 단일 평가 세션의 재현성을 측정한다. 시계열 재현성(드리프트)은 `agent-eval trend`로 측정한다. 두 측정이 함께해야 완전한 신뢰성 그림이 완성된다.

```bash
# 1. 단일 세션 재현성 (ReproducibilityConfig)
# → "오늘 같은 질문에 일관된 답변을 하는가?"

# 2. 시계열 드리프트 (agent-eval trend)
# → "지난 한 달 동안 신뢰성이 유지되고 있는가?"
agent-eval trend results/ --window 30
agent-eval trend results/ --window 30 --fail-on-regression   # 회귀 감지 시 exit 1
```

- `agent-eval trend`는 순차적으로 저장된 결과 파일들의 시계열 변화를 분석하므로 `ReproducibilityConfig`의 단일 세션 측정과 상호 보완적이다.
- `--window 30`은 최근 30개 결과 파일을 분석 대상으로 삼으며, 주기적 CI/CD 실행 환경에서 한 달치 드리프트를 한 번에 확인할 수 있다.
- `--fail-on-regression`을 추가하면 TCR·정확도가 이전 기간 대비 저하될 때 `exit 1`로 CI/CD를 자동 차단한다. `--metric` 플래그는 지원하지 않으며, trend는 TCR·정확도·비용 등 핵심 지표 전체를 자동으로 분석한다.

---

## 6.6 Gate C 판정 — 결과 접근과 배포 차단

Gate C 판정 결과는 `report.to_dict()`의 `extra_metrics.harness_groups` 키에서 가져온다. CI/CD에서는 `agent-eval gate` CLI로 자동 차단한다.

```python
# 기반 코드 — Gate C 점수 접근 패턴 (ch06_group_c.py 기반, 환각·재시도 접근 확장)
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/", enable_hallucination_detection=True)
# (에이전트 실행 코드 — 전체 예제: Evaluator_Examples/ch06_group_c.py 참고)

report = monitor.generate_report()
d = report.to_dict()

# Gate C 판정 결과 접근
harness = (d.get("extra_metrics") or {}).get("harness_groups", {})
gate_c = harness.get("C", {})
print(f"Gate C 점수: {gate_c.get('score', 'N/A')}")
print(f"Gate C 상태: {gate_c.get('status', 'N/A')}")   # "pass" / "warn" / "fail"

# Gate C 기여 지표 접근
hall_rate = (d.get("accuracy_metrics") or {}).get("hallucination", {}).get("overall_rate")
retries = (d.get("efficiency_metrics") or {}).get("retries", {})
print(f"환각률: {hall_rate:.1f}%" if hall_rate is not None else "환각률: N/A")
print(f"최종 성공률: {retries.get('eventual_success_rate', 'N/A')}%")
print(f"재시도율: {retries.get('retry_rate', 'N/A')}%")
```

```bash
# CI/CD — Gate C 기준 미달 시 배포 자동 차단
monitor.save_to_file("ch06_group_c")                       # results/ch06_group_c.json 저장
agent-eval gate results/ch06_group_c.json --tcr 80        # TCR 80% 미달 시 exit 1
```

- Gate C 결과는 `extra_metrics.harness_groups["C"]` 키에서 접근한다. `score`는 0.0~1.0, `status`는 `"pass"`·`"warn"`·`"fail"` 중 하나다(소문자).
- 환각률은 `accuracy_metrics.hallucination.overall_rate`, 재시도율은 `efficiency_metrics.retries.retry_rate`, 최종 성공률은 `efficiency_metrics.retries.eventual_success_rate`로 접근한다. LLM Judge faithfulness는 per-task `task_result.llm_judge["scores"]["faithfulness"]`에 저장되며, Gate C 점수에 우선 반영된다. 이 지표들은 `to_dict()` 최상위에 노출되지 않는다.
- 프로덕션 배포 파이프라인에서 Gate C `"fail"` 판정 시 `agent-eval gate` CLI가 `exit 1`을 반환하므로, 장애 복구 실패나 환각 임계값 초과 에이전트를 자동으로 차단할 수 있다.

---

## 이 챕터의 핵심

Gate C는 에이전트가 같은 입력에 일관된 결과를 내고, 장애 상황에서도 안전하게 동작하는지 판정한다. 출력 사실 충실성은 LLM이 사용 가능할 때 `LLMJudge`의 `faithfulness`(0–5)로 우선 채점하고, 그렇지 않으면 `HallucinationDetector`(opt-in)의 NLP 기반 점수로 폴백한다. `RetryCorrectionTracker`로 재시도 패턴을 추적하며, 5개 Config로 재현성·장애 내성·멱등성 계약을 각각 선언한다.

| 지표 / Config | 역할 | 핵심 파라미터 |
|--------------|------|-------------|
| `LLMJudge` (faithfulness) | 의미적 사실 충실성 — Gate C 우선 슬롯 | `faithfulness` (0–5 → `/5` 정규화); LLM 없을 때 `HallucinationDetector`로 자동 폴백 |
| `HallucinationDetector` | NLP 기반 사실 일관성 폴백 (opt-in) | `overall_rate`, `tasks_with_hallucinations` (`accuracy_metrics.hallucination`) |
| `RetryCorrectionTracker` | 재시도·자가수정 패턴 추적 | `retry_rate`, `eventual_success_rate`, `correction_success_rate` (`efficiency_metrics.retries`) |
| `ReproducibilityConfig` | 동일 입력 재현성 기준 | `runs`, `similarity_measure`, `reproducibility_threshold`, `fail_on_low_reproducibility` |
| `FaultToleranceConfig` | 장애 내성·폴백 기준 | `expected_fallback_tools`, `check_fallback_attempts` |
| `GracefulDegradationConfig` | 우아한 성능 저하 기준 | `quality_floor`, `check_error_acknowledgment` |
| `RetryConsistencyConfig` | 재시도 일관성 기준 | `improvement_threshold`, `penalize_degradation` |
| `IdempotencyConfig` | 멱등성 기준 | `non_idempotent_patterns`, `non_idempotent_penalty` |

> 🔗 **다음 챕터**: Chapter 7 — Gate D: 성능계약  
> 에이전트의 응답 시간·비용·토큰 사용량이 약속한 SLA를 지키는지 측정하는 2개 Tracker(`LatencyTracker` — Gate D 점수 기여, `TokenEconomyTracker` — gate score 미기여)와 5개 Config를 완전히 이해한다.


---

## 실전 예제

**기본 예제**: [`Evaluator_Examples/ch06_group_c.py`](../../Evaluator_Examples/ch06_group_c.py)
— 4개 섹션: **섹션 1** HallucinationDetector(RAG 모드) · **섹션 2** LLMJudge RAG Faithfulness · **섹션 2-b** RetryCorrectionTracker(직접 기록 패턴) · **섹션 3** FaultToleranceConfig · GracefulDegradationConfig · ReproducibilityConfig · RetryConsistencyConfig · IdempotencyConfig 5개 Config + Gate C FAIL 역케이스

> **관련 챕터 예제**: Harness 전체 Gate 통합 흐름은 [Chapter 3 — `ch03_harness_basics.py`](Chapter_03_Harness_Engineering_기초.md), Layer 1 기초 트래커는 [Chapter 1 — `ch01_first_eval.py`](../Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md)에서 확인한다.

**핵심 코드**

```python
# ch06_group_c.py 섹션 2 — LLMJudge faithfulness (Gate C 우선 반영)
# LLM API 키가 있을 때만 활성화; 없으면 HallucinationDetector 폴백
import os
from agent_evaluator import PerformanceMonitor, LLMJudgeConfig, agent_eval, load_env

load_env()  # .env 파일에서 API 키 자동 로드

monitor = PerformanceMonitor(output_dir="results/", enable_hallucination_detection=True)

if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
    @agent_eval(
        monitor,
        task_type="information_retrieval",
        rag_mode=True,
        llm_judge=LLMJudgeConfig(
            model=None,       # None → API 키 기반 자동 결정
            sample_rate=1.0,  # 예제: 100% 채점 (프로덕션은 0.2 권장)
        ),
    )
    def rag_faithfulness_agent(question: str, context: str = "", ground_truth: str = "") -> str:
        if context:
            return f"주어진 문맥을 바탕으로 답변드립니다. {question} — 문맥: {context[:40]}"
        return "문맥 정보가 없어 답변하기 어렵습니다."

    rag_faithfulness_agent(
        "아인슈타인이 태어난 해는?",
        context="알베르트 아인슈타인(1879-1955)은 독일의 물리학자이다.",
        ground_truth="1879년",
    )
    # → task.llm_judge["scores"]["faithfulness"] = 5
    # → Gate C 신뢰성 슬롯: faithfulness 5/5 = 1.000 (HallucinationDetector NLP 점수 대체)
    # (mock 에이전트가 컨텍스트를 그대로 인용하므로 LLM Judge가 5/5를 부여함)
```

```python
# ch06_group_c.py 섹션 3 핵심 패턴 — EvalMetadata 주입으로 내부 에러/재시도를 데코레이터에 전달
from agent_evaluator import (
    PerformanceMonitor,
    FaultToleranceConfig, GracefulDegradationConfig,
    ReproducibilityConfig, RetryConsistencyConfig, IdempotencyConfig,
)
from agent_evaluator import agent_eval, RetryConfig, EvalMetadata

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

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
def fault_tolerant_agent(question: str, ground_truth: str = "") -> tuple:
    """장애 내성 + 우아한 저하: 에러를 EvalMetadata로 데코레이터에 전달."""
    # TODO(현업 적용): raise를 실제 외부 API 호출로 교체하세요.
    try:
        raise RuntimeError("외부 API 타임아웃")  # 실패 시뮬레이션
    except RuntimeError as e:
        response = f"부분 완료(폴백): 캐시 데이터로 응답합니다. {question}"
        tool_calls = [
            {"name": "main_tool",  "success": False, "error": str(e)},
            {"name": "cache_tool", "success": True},
        ]
        # EvalMetadata 없이 return하면 errors=[] → has_error=False → mode="normal" (오채점)
        return response, EvalMetadata(errors=[f"RuntimeError: {e}"], tool_calls=tool_calls)

# ── RetryConsistencyConfig: 재시도 일관성 선언 ──
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="c_retry_consistency",
    retry_consistency=RetryConsistencyConfig(
        min_retry_count=2,
        improvement_threshold=0.1,
    ),
    retry=RetryConfig(max=3, on=(ValueError,), delay=0.0),
)
def retry_consistent_agent(question: str, ground_truth: str = "") -> tuple:
    """재시도 일관성: EvalMetadata(attempts=2)로 시도 횟수를 명시해야 채점 가능."""
    # TODO(현업 적용): 실제 LLM 호출로 교체하고 실제 시도 횟수를 attempts=N으로 전달하세요.
    # min_retry_count=2 이상이어야 eval_retry_consistency가 None이 아닌 점수 반환
    return f"일관된 재시도 응답: {question}", EvalMetadata(attempts=2)

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
    # TODO(현업 적용): 실제 LLM 호출로 교체하세요.
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
    """멱등성: 읽기 전용 응답이면 tool_calls 없이도 1.0 (패널티 없음)."""
    # TODO(현업 적용): 실제 LLM 호출로 교체하세요.
    return f"읽기 전용 조회 완료: {question}에 대한 데이터를 검색했습니다."

# ── 역케이스: Gate C FAIL 유도 (non-idempotent tool_calls 3개 주입) ──
_monitor_c_fail = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(
    _monitor_c_fail, task_type="tool_use", task_id_prefix="c_fail_idempotency",
    idempotency=IdempotencyConfig(
        non_idempotent_patterns=["create", "insert", "생성", "등록", "delete"],
        non_idempotent_penalty=0.4,
    ),
)
def _c_fail_agent(question: str, ground_truth: str = "") -> tuple:
    # TODO(현업 적용): 실제 tool_calls는 에이전트 실행 결과에서 자동으로 채워집니다.
    return f"레코드 생성 및 등록: {question}", EvalMetadata(
        tool_calls=[
            {"name": "create_record", "args": {"data": question}},
            {"name": "insert_db",     "args": {"row": question}},
            {"name": "delete_old",    "args": {"id": "prev"}},
        ],
    )
```

- `fault_tolerant_agent`는 `(response, EvalMetadata(...))` 튜플을 반환한다. 에러를 내부에서 catch한 뒤 `EvalMetadata(errors=[...], tool_calls=[...])` 없이 return하면 데코레이터가 `errors=[]`로 인식해 `has_error=False` → `mode="normal"`로 오채점된다.
- `retry_consistent_agent`는 `EvalMetadata(attempts=2)`를 명시해야 `eval_retry_consistency`가 `None`이 아닌 점수를 반환한다. `attempts < min_retry_count`이면 `None`이 반환되어 Gate C 집계에서 누락된다.
- `idempotent_agent`처럼 읽기 전용 응답이면 `tool_calls`가 없어도 패널티 없이 1.0을 받는다.
- 역케이스 `_c_fail_agent`는 `non_idempotent_patterns`에 해당하는 tool_calls를 3개 주입해 Gate C FAIL을 유도한다.

```bash
python Evaluator_Examples/ch06_group_c.py                 # Gate C — 4섹션 + FAIL 역케이스
python Evaluator_Examples/ch03_harness_basics.py          # Gate A–G 전체 통합 (Gate C 포함)
python Evaluator_Examples/ch01_first_eval.py              # HallucinationDetector Layer 1 기초
```

**실행 결과 예시 (`ch06_group_c.py`)**

*LLM API 키 있는 경우 — LLM Judge faithfulness가 Gate C에 우선 반영*
```
Non-idempotent tools detected in task c_fail_idempotency_...: ['insert_db', 'delete_old', 'create_record']
Non-idempotent tools detected in task c_fail_idempotency_...: ['insert_db', 'delete_old', 'create_record']
Non-idempotent tools detected in task c_fail_idempotency_...: ['insert_db', 'delete_old', 'create_record']

=== 섹션 1: HallucinationDetector + RAG 모드 ===
  환각률: 0.0%
  섹션 1 완료: RAG 2건 기록

=== 섹션 2: RAG Faithfulness + LLMJudge ===
  RAG Faithfulness: 5/5 (5=모든 주장이 컨텍스트에 근거)
  섹션 2 완료: RAG Faithfulness + LLMJudge 1건 기록

=== 섹션 2-b: RetryCorrectionTracker ===
  재시도율: 100.0%
  최종 성공률: 100.0%
  재시도 후 성공 건수: 2
  태스크당 평균 시도: 2.5회
  섹션 2-b 완료: 3건 기록

=== 섹션 3: Gate C — Reliability ===
  Reliability 패턴 실행 (장애 복구 시뮬레이션)...
  [시스템 로그] 장애 감지: 외부 API 타임아웃 발생 → 폴백 모드 전환
    ⚠️ 폴백 응답: 부분 완료(폴백): 외부 도구 일시 오류(외부 API 타임아웃 발생)로 인해 캐시...
    ✅ 정상 응답: 정상 처리 완료: 데이터를 읽어줘...
    ✅ 정상 응답: 정상 처리 완료: 현재 설정을 보여줘...
  섹션 3 완료: ~12건 기록
  ▶ 역케이스 Gate C: 24.0%  FAIL 확인 ✓

  Gate C [Reliability            ] ████████░░ 0.893 (pass)
결과 저장 완료: results/ch06_group_c.json
```

*LLM API 키 없는 경우 — HallucinationDetector NLP 폴백*
```
Non-idempotent tools detected in task c_fail_idempotency_...: ['insert_db', 'delete_old', 'create_record']
  (× 3회)

=== 섹션 2: RAG Faithfulness + LLMJudge ===
  API 키 없음 — LLMJudge 섹션 skip (OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 필요)
  ...
  Gate C [Reliability            ] ███████░░░ 0.776~0.796 (pass)  ← 실행마다 근소하게 변동(아래 참고)
```

> **⚠️ 이 시나리오는 완전히 결정론적이지 않다.** 4회 반복 실행해 실측한 결과 Gate C 점수가 0.776·0.786·0.786·0.796으로 매번 조금씩 달랐다. 원인은 `retry_consistent_agent`(`RetryConsistencyConfig`) 하나뿐이다 — `avg_retry_consistency`가 0.75~0.95 사이에서 변동했고, 나머지 4개 지표(`avg_reproducibility`·`avg_fault_tolerance`·`avg_degradation`·`avg_idempotency`)는 매 실행 동일했다. `retry_consistent_agent`는 `EvalMetadata(attempts=2)`로 시도 횟수만 고정 주입할 뿐 실제 응답 시간은 측정 시점의 실제 실행 시간을 그대로 사용하므로, 시스템 부하에 따라 "이전 시도보다 개선되었는가"의 판정이 실행마다 근소하게 달라진다. 독자가 직접 실행하면 이 범위 내에서 다른 값을 볼 수 있으며, 이는 버그가 아니라 이 Config가 실측 시간에 민감하게 반응하도록 설계된 결과다.

- `ch06_group_c.py`는 섹션 1–3과 역케이스까지 포함하며, 실행하면 `results/ch06_group_c.json`이 생성된다.
- Gate C의 출력 충실성 슬롯은 단일 항목으로 유지된다. LLM API 키가 있으면 `faithfulness / 5`를 사용하고, 없으면 `1 − hall_rate`로 자동 폴백하므로 두 환경 모두 Gate C 구조가 동일하다.
- `ch03_harness_basics.py`는 Gate A–G 모든 Config를 한 번에 실행하므로 Gate C 판정 결과를 다른 Gate와 함께 비교할 수 있다.
- `ch01_first_eval.py`의 `HallucinationDetector` 예제는 `enable_hallucination_detection=True` 설정 없이는 환각 점수가 집계되지 않으므로 반드시 `PerformanceMonitor` 생성 시 확인한다.
