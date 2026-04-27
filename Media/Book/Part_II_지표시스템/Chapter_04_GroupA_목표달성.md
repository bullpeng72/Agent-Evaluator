# Chapter 4. Gate A — 목표달성 지표

@@HTML_START@@
<div class="hc-card hc-a">
  <div class="hc-header">
    <span class="hc-gate-badge he-gate ga">Gate A</span>
    <span class="hc-title">🔗 Harness 연결 — Goal Achievement (목표달성)</span>
  </div>
  <div class="hc-body">
    <div class="hc-row">
      <span class="hc-label hc-tracker-label">Tracker</span>
      <div class="hc-chips">
        <span class="hc-chip hc-t-chip">TaskCompletionTracker</span>
        <span class="hc-chip hc-t-chip">AccuracyEvaluator</span>
        <span class="hc-chip hc-t-chip">ResponseQualityEvaluator</span>
      </div>
    </div>
    <div class="hc-row">
      <span class="hc-label hc-config-label">Config</span>
      <div class="hc-chips">
        <span class="hc-chip hc-c-chip">InstructionConfig</span>
        <span class="hc-chip hc-c-chip">GoalAlignmentConfig</span>
        <span class="hc-chip hc-c-chip">PlanConfig</span>
        <span class="hc-chip hc-c-chip">ContextRetentionConfig</span>
        <span class="hc-chip hc-c-chip">SubtaskConfig</span>
        <span class="hc-chip hc-c-chip">KnowledgeRetentionConfig</span>
      </div>
    </div>
  </div>
  <div class="hc-footer">
    <code>HarnessEvaluationGate(report).evaluate()</code>
  </div>
</div>
@@HTML_END@@

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate A 지표 입력·출력·기본값
> - **[Appendix H — 수학적 상세](../Appendix/H_알고리즘_수학적_레퍼런스.md)**: 4중 가중 정확도 공식, TCR 의사코드
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate A Config 파라미터 전체 목록
> - **[Evaluator_Examples/ch04_group_a.py](../../Evaluator_Examples/ch04_group_a.py)**: 이 챕터 실전 예제 (Gate A~G FAIL 시나리오 17개 · 배포 차단 케이스 포함)

> **독자별 읽기 가이드**  
> - **QA 관리자**: §4.1(개요) → §4.4(Config 설정) → §4.5(임계값·Gate 판정) 순서로 읽으면 "어떤 기준을 세울지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §4.2(Tracker 상세) → §4.3(코드 예제) → §4.4(Config 선언) 순서로 읽으면 구현에 바로 적용할 수 있습니다.

---

@@HTML_START@@
<div class="gw-box">
  <div class="gw-header">⚠️ Gate A가 없으면 생기는 일</div>
  <div class="gw-body">
    <p>"응답이 나왔다"는 것을 알지만, "목표를 달성했다"는 것은 알 수 없다. 에이전트가 매번 응답을 생성하더라도 TCR이 70% 이하면 3건 중 1건은 사용자가 원하는 결과를 얻지 못한다.</p>
    <div class="gw-case">
      <strong>실제 사례:</strong> 고객 응대 봇이 "응답 생성률 100%"를 보고하면서 고객 만족도가 60%에 머무른 회사. 응답은 나왔지만 질문에 맞는 답변이 아니었다. AccuracyEvaluator 미도입이 원인.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 4.1 Gate A 개요

Gate A는 에이전트가 사용자의 **목표를 달성했는가**를 측정한다. 이것이 Harness Engineering의 출발점이다. 에이전트가 아무리 빠르고 안전해도 목표를 달성하지 못하면 배포할 수 없다.

### Gate A가 첫 번째인 이유 — 에이전트의 존재 이유를 판정한다

Harness Engineering에서 Gate A는 단순히 "정확도가 높은가"를 측정하는 것이 아니다. **"이 에이전트가 배포될 자격이 있는가"의 출발 조건**을 선언한다.

- Gate D(성능)가 아무리 좋아도, Gate E(보안)가 완벽해도, Gate A를 통과하지 못하면 에이전트는 배포 불가다. 빠르고 안전하게 틀린 답을 내는 에이전트는 오히려 더 위험하다.
- Gate A는 에이전트의 **"지시 이행 계약"을 코드로 선언**한다. `InstructionConfig(expected_format="json", fail_on_violation=True)`라는 한 줄이 "JSON 형식을 지키지 않으면 성공으로 인정하지 않는다"는 배포 기준이 된다. 이것이 Config-as-Code 관점이다.
- 6개 Config는 각자 다른 목표달성 실패 유형을 커버한다: 형식 미준수(Instruction), 목표-행동 불일치(GoalAlignment), 계획 포기(Plan), 서브태스크 미완(Subtask), 컨텍스트 망각(ContextRetention), 사실 망각(KnowledgeRetention).

### Gate A가 다루는 3가지 질문

1. **완수**: 태스크가 실제로 완료되었는가? (TCR)
2. **정확**: 완료된 내용이 ground_truth와 일치하는가? (Accuracy)
3. **형식**: 응답이 요구된 형식·언어·길이를 충족하는가? (InstructionConfig)

### Tracker vs Config — Gate A 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "현재 목표달성이 어느 수준인가?" | "이 수준이면 배포 가능한가?" |
| 코드 위치 | `PerformanceMonitor` 내부 자동 동작 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 선언 |
| 결과 | `report.to_dict()["tcr"]` 등 | `fail_on_violation=True` 시 자동 fail |
| 예시 | `tcr=0.87` → "현재 87% 완료" | `InstructionConfig(max_words=200)` → "200단어 초과 불가" |

---

## 4.2 Tracker 3종 심화

Gate A에 연결된 Tracker는 세 가지다. `TaskCompletionTracker`와 `AccuracyEvaluator`는 상시 활성이며, `HallucinationDetector`는 `rag_mode=True` 또는 `task_type="information_retrieval"` 설정 시 opt-in으로 활성화된다.

> **참고**: `ResponseQualityEvaluator`는 Layer 1 Tracker로서 `@agent_eval` 데코레이터와 함께 자동 활성화되지만, Gate A 점수 산정에 직접 포함되지는 않는다. §4.2.3에서 별도로 설명한다.

### 4.2.1 TaskCompletionTracker — TCR

**Task Completion Rate(TCR)**는 에이전트가 태스크를 얼마나 성공적으로 완수하는지 보여주는 핵심 KPI다. 단순한 성공/실패 이분법 대신 3단계 완료 수준으로 측정한다.

| 완료 수준 | completion_score | 의미 |
|---------|-----------------|------|
| 완전 성공 | 1.0 | 정확한 답변, 정상 완료 |
| 부분 성공 | 0.7 ≤ score < 1.0 | 일부 불완전한 답변 |
| 실패 | score < 0.7 | 오류, 빈 응답, 예외 발생 |

**TCR 계산 공식:**
```
TCR(%) = (Σ completion_score / N) × 100
```

예: 3건의 completion_score가 1.0, 0.8, 0.0이면 TCR = (2.8 / 3) × 100 = **93.3%**

**task_type별 구조적 완료 판정 (v0.8.0+)**

ground_truth 없는 환경에서도 task_type으로 완료 여부를 자동 추론한다.

| task_type | 판정 기준 | completion_score |
|-----------|----------|-----------------|
| `code_generation` / `coding` | Python AST 파싱 성공 여부 | 1.0 or 길이 기반 |
| `tool_use` | `tool_calls` 비어 있지 않음 | 1.0 or 0.6 |
| 기타 | 응답 길이 ≥ 10자 | 1.0 (기본값) |

```python
# 출처: Evaluator_Examples/ch04_group_a.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor("results/")

# tool_use: 도구를 사용한 경우만 완전 완료
r1 = create_taskresult(
    task_id="t1",
    question="날씨 검색",
    response="서울 맑음",
    execution_time=1.0,
    task_type="tool_use",
    tool_calls=[{"name": "search", "args": {"query": "서울 날씨"}}],
)
# → completion_score = 1.0 (도구 사용 확인)

r2 = create_taskresult(
    task_id="t2",
    question="날씨 검색",
    response="서울은 보통 맑습니다",
    execution_time=0.5,
    task_type="tool_use",
    tool_calls=[],  # 도구 미사용
)
# → completion_score = 0.6 (부분 완료)

monitor.record_task(r1)
monitor.record_task(r2)

# 출처: Evaluator_Examples/ch04_group_a.py, 섹션 추가B — 토큰 경제성 & 비용 추정
report = monitor.generate_report()
d = report.to_dict()
tcr_data = d.get("accuracy_metrics", {}).get("tcr", {})
total = tcr_data.get("total_tasks", 1) or 1
tcr   = tcr_data.get("tcr", 0.0)
full  = tcr_data.get("full_success", 0)
part  = tcr_data.get("partial_success", 0)
print(f"TCR: {tcr * 100:.1f}%")                            # TCR: 80.0%
print(f"완전 성공: {full}/{total} ({full/total*100:.1f}%)")  # 1/2 (50.0%)
print(f"부분 성공: {part}/{total} ({part/total*100:.1f}%)")  # 1/2 (50.0%)
```

- **`task_type="tool_use"`**: 도구 호출이 있으면 `completion_score=1.0`, 없으면 `0.6`(부분 완료)으로 자동 계산한다
- **`tool_calls` 필드**: 실제 도구 호출 목록을 전달해야 `TaskCompletionTracker`가 도구 사용 여부를 정확히 판단한다
- **TCR 집계 경로**: `report.to_dict()["accuracy_metrics"]["tcr"]` 하위에 `tcr`·`full_success`·`partial_success` 세 값이 들어 있다
- **주의점**: `total_tasks`가 0인 경우 ZeroDivisionError를 방지하기 위해 `or 1` 가드가 필요하다

**TCR 임계값 가이드:**

| TCR | 상태 | 권장 행동 |
|-----|------|---------|
| ≥ 90% | 🟢 프로덕션 준비 | 배포 가능 |
| 80~90% | 🟡 개선 필요 | 실패 케이스 분석 |
| 70~80% | 🟠 위험 | 주요 버그 수정 필요 |
| < 70% | 🔴 배포 불가 | 근본적 재설계 검토 |

### 4.2.2 AccuracyEvaluator — 4중 가중 정확도

Accuracy는 응답이 ground_truth와 얼마나 가까운지 측정한다. BLEU나 ROUGE 대신 **4중 가중 알고리즘**을 사용한다. 각 알고리즘의 약점을 서로 보완하는 구조다.

| 지표 | 가중치 | 측정 방식 | 강점 |
|------|--------|---------|------|
| Token F1 | 40% | 토큰 단위 정밀도-재현율 조화평균 | 긴 응답의 과평가 방지 |
| Jaccard | 30% | 집합 교집합/합집합 비율 | 순서 무관 일치도 |
| LCS | 20% | Longest Common Subsequence | 연속 구절 매칭 |
| Char Similarity | 10% | Levenshtein 거리 기반 | 문자 순서·오타 반영 |

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — QA 정확도
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="t1",
    question="한국의 수도는?",
    response="한국의 수도는 서울특별시입니다.",
    ground_truth="서울",
    execution_time=0.5,
    task_type="qa",
)
print(f"정확도: {result.accuracy_score:.3f}")  # 0.78 (수도 이름 포함, 길이 차이)

result2 = create_taskresult(
    task_id="t2",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.5,
    task_type="qa",
)
print(f"정확도: {result2.accuracy_score:.3f}")  # 0.87 (더 간결, ground_truth와 가까움)
```

- **`create_taskresult()`**: `accuracy_score`를 Token F1·Jaccard·LCS·Levenshtein 4중 가중으로 자동 계산한다
- **응답 길이 영향**: `result`는 "서울특별시"를 포함해 `ground_truth="서울"`보다 길기 때문에 Token F1 재현율이 높아도 정밀도가 낮아져 0.78이 나온다
- **`result2`**: "서울입니다."로 더 간결하게 응답해 `ground_truth`와 가까워 0.87이 나온다

**코드 정확도 — AST 비교**

`task_type="code_generation"`이면 텍스트 비교 대신 Python AST 비교를 사용한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — create_taskresult 사용
result = create_taskresult(
    task_id="code1",
    question="두 수를 더하는 함수",
    response="def add(a,b):\n    return a+b",
    ground_truth="def add(a, b):\n    return a + b",
    execution_time=1.0,
    task_type="code_generation",
)
# AST 구조 동일 → accuracy_score = 1.0 (공백 차이 무시)
```

- **`task_type="code_generation"`**: 텍스트 비교 대신 Python AST 파싱 후 구조 비교를 수행한다
- **공백 무시**: `add(a,b)`와 `add(a, b)`는 AST 구조가 동일하므로 `accuracy_score=1.0`이 된다
- **AST 파싱 실패 시 fallback**: 유효한 Python 코드가 아니면 응답 길이 기반으로 `completion_score`를 계산한다

**Accuracy 임계값 가이드:**

| 정확도 | 상태 | 의미 |
|--------|------|------|
| ≥ 0.85 | 🟢 우수 | 배포 가능 |
| 0.70~0.85 | 🟡 보통 | 프롬프트 개선 권장 |
| 0.50~0.70 | 🟠 미흡 | ground_truth 품질 확인 필요 |
| < 0.50 | 🔴 낮음 | 에이전트 전면 재검토 |

### 4.2.3 ResponseQualityEvaluator — 5차원 가중 품질 평가

> **Gate A와의 관계**: `ResponseQualityEvaluator`는 Gate A의 공식 Tracker(TCR·Accuracy)와 함께 Layer 1에 속하며, `@agent_eval` 데코레이터를 붙이면 자동 활성화된다. 단, 이 Tracker의 점수는 Gate A 합산 점수에 직접 포함되지 않고 `report.to_dict()["quality_metrics"]`에 별도 집계된다. ground_truth 없이 응답 품질을 정성적으로 판단하고 싶을 때 가장 먼저 도입한다.

ground_truth 없이도 응답 자체의 품질을 5개 차원으로 평가한다. 각 차원을 0~5 척도로 측정하고 **가중 평균**으로 `quality_score`를 계산한다.

| 차원 | 가중치 | 측정 내용 |
|------|-------|---------|
| relevance | ×0.25 | 응답이 질문과 관련이 있는가? |
| completeness | ×0.25 | 응답이 질문에 완전히 답했는가? |
| accuracy | ×0.20 | 응답의 사실적 정확성이 높은가? |
| clarity | ×0.15 | 응답이 명확하고 이해하기 쉬운가? |
| usefulness | ×0.15 | 응답이 실제로 유용한가? |

```
quality_score = relevance×0.25 + completeness×0.25 + accuracy×0.20 + clarity×0.15 + usefulness×0.15
```

```python
# 출처: Evaluator_Examples/ch01_first_eval.py, [4] ResponseQualityEvaluator
from agent_evaluator import ResponseQualityEvaluator

rqe = ResponseQualityEvaluator()

result = rqe.evaluate_response(
    task_id="t1",
    response="파이썬은 범용 프로그래밍 언어로 데이터 과학, 웹 개발, 자동화에 널리 쓰입니다.",
    request="파이썬이란?",
    expected_elements=["프로그래밍", "데이터"],   # 포함 기대 키워드 (선택)
)
print(f"총점: {result['total_score']:.2f}/5  등급: {result['grade']}")

dims = result.get("dimension_scores", {})
print(f"관련성={dims.get('relevance', 0):.2f}  완전성={dims.get('completeness', 0):.2f}")
print(f"정확도={dims.get('accuracy', 0):.2f}  명확성={dims.get('clarity', 0):.2f}")
print(f"유용성={dims.get('usefulness', 0):.2f}")
```

**`PerformanceMonitor`와 자동 연동:**

```python
# 출처: Evaluator_Examples/ch04_group_a.py — PerformanceMonitor 설정
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

agent("딥러닝이란 무엇인가?")

report = monitor.generate_report()
d = report.to_dict()
qm = d.get("quality_metrics", {})
print(qm.get("avg_total_score", 0.0))    # 4.1 (0~5 척도)
print(qm.get("dimension_averages", {}))  # {"completeness": 4.5, "relevance": 4.2, ...}
```

- `evaluate_response()` 직접 호출: `task_id`(집계용 식별자), `response`(평가 대상), `request`(원래 질문), `expected_elements`(포함 기대 키워드 목록) 4개 인자를 받는다.
- `grade` 필드: `total_score` 기준 `"excellent"` (4.5+) / `"good"` (3.5+) / `"average"` (2.5+) / `"poor"` (미만).
- **ground_truth 불필요**: 응답 자체만으로 5차원을 평가하므로 ground_truth 없이도 품질을 측정할 수 있다.
- **`@agent_eval` 자동 연동**: 데코레이터만 붙이면 `AccuracyEvaluator`·`TaskCompletionTracker`와 함께 `ResponseQualityEvaluator`가 자동 활성화된다.

---

## 4.3 Config 6종 레퍼런스

### 4.3.1 InstructionConfig — 응답 형식·언어·길이 준수

응답이 선언된 형식·언어·길이 기준을 지키는지 검증한다. **가장 먼저 도입해야 할 Config**다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — InstructionConfig
from agent_evaluator import InstructionConfig

InstructionConfig(
    expected_format="json",           # "json"|"markdown"|"yaml"|"plain"|None
    required_sections=["요약", "근거"], # 응답에 포함되어야 할 섹션 이름
    max_chars=2000,                   # 최대 문자 수
    min_chars=50,                     # 최소 문자 수
    max_words=300,                    # 최대 단어 수
    min_words=20,                     # 최소 단어 수
    forbidden_phrases=[               # 응답에 포함되면 안 되는 구절
        "모르겠습니다",
        "확인이 필요합니다",
        "죄송합니다",
    ],
    required_keywords=["결론"],       # 반드시 포함해야 할 키워드
    expected_language="ko",           # "ko"|"en"|None
    fail_on_violation=True,           # 위반 시 success=False
    violation_weight=0.1,             # fail_on_violation=False 시 감점 가중치
)
```

- **`expected_format`**: 응답이 JSON·Markdown·YAML·plain 형식을 따르는지 자동으로 파싱해 검증한다
- **`forbidden_phrases`**: 에이전트의 역량 부족 신호("모르겠습니다")나 불필요한 사과 표현을 응답에서 탐지한다
- **`fail_on_violation=True`**: 위반이 발생하면 해당 `TaskResult.success`를 `False`로 강제해 TCR에 직접 반영된다
- **`violation_weight`**: `fail_on_violation=False`일 때 위반 횟수에 이 가중치를 곱해 `instruction_score`를 감점한다

**사용 예시:**

```python
# 출처: Evaluator_Examples/ch04_group_a.py — InstructionConfig
from agent_evaluator import InstructionConfig
from agent_evaluator.decorators import agent_eval

# 고객 응대 봇 — JSON 구조화 응답 강제
@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_format="json",
        required_sections=["answer", "confidence"],
        expected_language="ko",
        forbidden_phrases=["I don't know", "不知道"],
        fail_on_violation=True,
    ),
)
def customer_bot(question: str, ground_truth: str = "") -> str:
    response = llm.invoke(question)
    # 반드시 {"answer": "...", "confidence": 0.9} 형태로 반환해야 함
    return response
```

- **`expected_format="json"`**: 응답이 유효한 JSON인지 파싱해 검증하며, 위반 시 `fail_on_violation=True`에 의해 즉시 fail 처리한다
- **`required_sections`**: JSON 응답에 `"answer"`·`"confidence"` 키가 반드시 포함되어야 한다
- **`forbidden_phrases`**: 영어·중국어 거절 표현을 탐지해 한국어 전용 서비스 정책을 코드로 강제한다

**임계값 가이드:**

| 항목 | 권장 기준 |
|------|---------|
| 응답 언어 | 사용자 인터페이스 언어와 일치 |
| max_words | 사용 맥락에 맞게 (챗봇: 150, 리포트: 500) |
| forbidden_phrases | "모르겠습니다" 등 에이전트 역량 부족 신호 차단 |

### 4.3.2 GoalAlignmentConfig — 목표-행동 정렬

에이전트가 사용한 도구가 질문의 목표와 정렬되어 있는지 측정한다. "검색"이 목표인데 "코드 실행"을 사용했다면 정렬이 낮다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — GoalAlignmentConfig
from agent_evaluator import GoalAlignmentConfig

GoalAlignmentConfig(
    use_keyword_overlap=True,          # 질문 키워드 ↔ 도구명 오버랩 측정
    goal_tool_map={                    # 목표 키워드 → 적합한 도구 목록
        "검색": ["web_search", "search"],
        "요약": ["summarize", "compress"],
        "번역": ["translate"],
        "분석": ["analyze", "compute"],
    },
    use_llm_scoring=False,             # LLM-as-Judge 정렬 점수 (opt-in)
    llm_blend_weight=0.5,              # 키워드 점수와 LLM 점수의 혼합 비율 (0.0~1.0, 기본 0.5)
    alignment_threshold=0.6,           # 경고 임계값 (0.0~1.0)
    ignore_no_tool_tasks=True,         # 도구 미사용 태스크는 건너뜀
)
```

- **`goal_tool_map`**: 질문에서 "검색", "분석" 등 목표 키워드를 탐지하면 매핑된 도구가 실제로 사용되었는지 확인한다
- **`alignment_threshold=0.6`**: 목표-도구 정렬 점수가 0.6 미만이면 경고를 발생시킨다
- **`ignore_no_tool_tasks=True`**: 도구를 전혀 사용하지 않은 태스크는 정렬 계산에서 제외해 단순 QA 태스크가 점수를 낮추지 않도록 한다
- **`use_llm_scoring=True`**: LLM Judge가 목표와 도구 선택의 의미론적 정렬을 추가로 채점한다 (비용 증가)
- **`llm_blend_weight=0.5`**: `use_llm_scoring=True`일 때 키워드 오버랩 점수(50%)와 LLM 점수(50%)를 혼합한다. `0.0`이면 키워드 점수만, `1.0`이면 LLM 점수만 사용한다

### 4.3.3 PlanConfig — 계획 실행 완성도

에이전트가 계획(plan)을 수립하고 그 계획대로 실행하는지 추적한다. 다단계 추론이나 복잡한 태스크를 처리하는 에이전트에 적합하다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — PlanConfig
from agent_evaluator import PlanConfig

PlanConfig(
    plan_field="plan",                 # 응답 JSON에서 계획 추출할 필드명
    steps_field="steps",               # 계획 내 단계 필드명
    check_goal_coverage=True,          # 목표 키워드가 계획 단계에 포함되는지
    check_step_ordering=True,          # 단계 순서 논리성 확인
    check_executability=True,          # 사용 가능한 도구로 실행 가능한지
    available_tools=["search", "code_exec", "summarize"],
    use_llm_scoring=False,             # LLM-as-Judge 계획 품질 채점 (opt-in)
    llm_blend_weight=0.5,              # 규칙 기반 점수와 LLM 점수의 혼합 비율 (0.0~1.0, 기본 0.5)
    min_steps=2,                       # 최소 계획 단계 수
    max_steps=15,                      # 최대 계획 단계 수
)
```

- **`plan_field`·`steps_field`**: 응답 JSON에서 계획 구조를 추출할 필드명을 지정한다 (응답이 `{"plan": {"steps": [...]}}` 형태여야 함)
- **`check_executability=True`**: 계획 단계에서 사용하는 도구가 `available_tools` 목록에 있는지 확인해 실행 불가능한 계획을 탐지한다
- **`min_steps`·`max_steps`**: 계획 단계가 지나치게 적거나 많으면 계획 품질 점수를 낮춘다
- **`llm_blend_weight=0.5`**: `use_llm_scoring=True`일 때 규칙 기반 점수(단계 수·실행 가능성 등)와 LLM 채점 점수를 혼합하는 비율이다. `0.0`이면 규칙 기반만, `1.0`이면 LLM 점수만 사용한다

**사용 예시 — 연구 에이전트:**

```python
# 출처: Evaluator_Examples/ch04_group_a.py — PlanConfig
@agent_eval(
    monitor,
    task_type="planning",
    plan_tracking=PlanConfig(
        available_tools=["web_search", "read_document", "summarize", "write_report"],
        min_steps=3,
        max_steps=10,
        check_executability=True,
    ),
)
def research_agent(question: str, ground_truth: str = "") -> str:
    # 응답에 plan.steps 필드가 있으면 자동으로 계획 추적
    return planner.run(question)
```

- **`task_type="planning"`**: 계획 태스크임을 명시해 `PlanConfig` 집계가 Gate A Gate 점수에 포함되도록 한다
- **응답 형식 조건**: `planner.run()` 반환값이 `{"plan": {"steps": [...]}}` 구조를 포함해야 `PlanConfig`가 계획을 파싱할 수 있다
- **`check_executability=True`**: 계획 단계의 도구가 `available_tools`에 없으면 실행 불가 단계로 표시해 계획 완성도 점수를 낮춘다

### 4.3.4 ContextRetentionConfig — 핵심 컨텍스트 보존

RAG 에이전트나 멀티턴 대화 에이전트에서 원래 목표와 핵심 엔티티가 응답 전반에 유지되는지 측정한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — ContextRetentionConfig
from agent_evaluator import ContextRetentionConfig

ContextRetentionConfig(
    key_entities=["서울", "2024년", "인공지능"],  # 보존되어야 할 핵심 엔티티
    context_arg="context",                        # 컨텍스트 인자 이름
    retention_threshold=0.7,                      # 보존율 임계값
    check_original_goal=True,                     # 원래 목표 질문 보존 여부 확인
    entity_weight=0.6,                            # 엔티티 보존 가중치
    goal_weight=0.4,                              # 목표 보존 가중치
)
```

- **`key_entities`**: 응답에 반드시 언급되어야 할 핵심 엔티티 목록을 선언한다 (예: 제품명·날짜·고유명사)
- **`retention_threshold=0.7`**: 엔티티의 70% 이상이 응답에 포함되어야 통과로 처리한다
- **`entity_weight=0.6`·`goal_weight=0.4`**: 최종 `context_retention_score`를 엔티티 보존율(60%)과 목표 보존율(40%)의 가중 평균으로 계산한다

**사용 예시 — RAG 에이전트:**

```python
# 출처: Evaluator_Examples/ch04_group_a.py — ContextRetentionConfig
@agent_eval(
    monitor,
    task_type="information_retrieval",
    context_retention=ContextRetentionConfig(
        key_entities=["제품명", "버전", "오류코드"],
        retention_threshold=0.8,
        check_original_goal=True,
    ),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

- **`task_type="information_retrieval"`**: RAG 태스크에 적합한 타입으로 지정해 `ContextRetentionConfig`가 Gate A 평가에 포함된다
- **`retention_threshold=0.8`**: 제품명·버전·오류코드 세 엔티티 중 80% 이상(2.4개 이상)이 응답에 포함되어야 통과한다
- **`context` 파라미터**: RAG 에이전트는 함수 시그니처에 `context` 인자를 포함해야 `ContextRetentionConfig.context_arg`가 올바르게 동작한다

### 4.3.5 SubtaskConfig — 서브태스크 완료율

복잡한 태스크를 여러 하위 작업(subtask)으로 분해하고, 각 서브태스크의 완료 여부를 추적한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — SubtaskConfig
from agent_evaluator import SubtaskConfig

SubtaskConfig(
    expected_subtasks=["키워드 추출", "검색", "요약", "번역"],  # 기대하는 서브태스크 목록
    completion_markers=[             # 완료를 나타내는 마커 (응답 텍스트에서 탐지)
        "완료", "done", "✓", "finished", "처리됨",
    ],
    check_ordering=False,            # 서브태스크 순서 준수 여부 (False: 순서 무관)
    min_completion_rate=0.8,         # 최소 완료율 (80% 이상 완료해야 합격)
    auto_extract=False,              # True: LLM으로 서브태스크 자동 추출 (opt-in)
)
```

- **`completion_markers`**: 응답 텍스트에서 "완료", "done" 등의 마커를 탐지해 서브태스크 완료 여부를 판단한다
- **`min_completion_rate=0.8`**: 4개 서브태스크 중 3.2개 이상 완료되어야 통과한다 (실제로는 4개 중 4개 또는 3개 기준)
- **`auto_extract=True`**: LLM이 응답에서 서브태스크를 자동 추출해 `expected_subtasks`와 비교한다 (추가 API 비용 발생)

### 4.3.6 KnowledgeRetentionConfig — 대화 중 사실 보존

멀티턴 대화에서 초기 턴에 언급된 사실이 이후 응답에서도 유지되는지 측정한다. 에이전트가 대화 중 "기억"을 잃는 문제를 탐지한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — KnowledgeRetentionConfig
from agent_evaluator import KnowledgeRetentionConfig

KnowledgeRetentionConfig(
    facts_to_retain=[                # 보존되어야 할 사실 목록
        "사용자 이름: 김민준",
        "프로젝트: Agent-Evaluator",
        "마감: 2026-05-01",
    ],
    seed_turns=2,                    # 사실이 언급된 초기 턴 수
    check_from_turn=3,               # 몇 번째 턴부터 보존 여부 확인
    allow_implicit_retention=True,   # 암묵적 참조도 보존으로 인정
    retention_threshold=0.6,         # 사실 보존율 임계값
)
```

- **`facts_to_retain`**: 초기 대화 턴에서 언급된 사실로, 이후 응답에서 이 사실이 유지되는지 측정한다
- **`seed_turns=2`**: 처음 2개 턴에서 사실이 제공되며, `check_from_turn=3`부터 보존 여부를 검사한다
- **`allow_implicit_retention=True`**: "김민준 씨"처럼 간접 표현도 "사용자 이름: 김민준" 보존으로 인정한다
- **멀티턴 대화 활용**: `ConversationSession`·`@conversation_eval`과 함께 사용하면 턴별 사실 보존 추이를 자세히 추적할 수 있다

---

## 4.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 단순 QA 봇 (최소 구성)

```python
# 출처: Evaluator_Examples/ch04_group_a.py — InstructionConfig · SLAConfig
from agent_evaluator import InstructionConfig, SLAConfig

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_language="ko",
        max_words=200,
        forbidden_phrases=["모르겠습니다"],
        fail_on_violation=True,
    ),
    sla=SLAConfig(p95_ms=3000),   # Group D도 함께 선언 (권장)
)
def simple_qa(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- **최소 Config**: Group A의 `InstructionConfig` 하나로 응답 언어·길이·금지 표현을 한 번에 선언한다
- **`SLAConfig` 동시 선언**: Gate A(목표달성)와 Gate D(성능계약)를 하나의 데코레이터에 함께 선언해 두 Gate를 동시에 평가한다
- **`fail_on_violation=True`**: "모르겠습니다" 응답이 나오면 즉시 `success=False`로 처리해 TCR에 반영한다

### 패턴 2 — RAG 에이전트 (컨텍스트 보존 포함)

```python
# 출처: Evaluator_Examples/ch04_group_a.py — InstructionConfig · ContextRetentionConfig · GoalAlignmentConfig
from agent_evaluator import (
    InstructionConfig,
    ContextRetentionConfig,
    GoalAlignmentConfig,
)

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,                  # HallucinationDetector 자동 활성화
    instructions=InstructionConfig(
        expected_language="ko",
        required_keywords=["출처"],  # 응답에 출처 포함 강제
        fail_on_violation=False,
    ),
    context_retention=ContextRetentionConfig(
        key_entities=extracted_entities,
        retention_threshold=0.75,
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"검색": ["vector_search", "keyword_search"]},
        alignment_threshold=0.65,
    ),
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"question": question, "context": context})
```

- **`rag_mode=True`**: `HallucinationDetector`를 자동으로 opt-in 활성화한다. 이 Tracker는 Layer 1에 속하며, 검색된 문서와 응답의 사실 일관성(hallucination_score)을 측정해 Gate C(신뢰성) 지표에 기여한다. Gate A의 `ContextRetentionConfig`와 함께 사용하면 RAG 에이전트의 사실 정확성을 이중으로 보호할 수 있다
- **`required_keywords=["출처"]`**: 응답에 "출처" 키워드가 없으면 경고를 발생시킨다 (`fail_on_violation=False`이므로 fail은 아님)
- **3개 Config 조합**: 형식 기준(A)·컨텍스트 보존(A)·목표-도구 정렬(A)을 동시에 선언해 RAG 에이전트의 Gate A 핵심 요소를 완전히 커버한다

### 패턴 3 — 복잡한 계획 에이전트 (서브태스크 추적)

```python
# 출처: Evaluator_Examples/ch04_group_a.py — PlanConfig · SubtaskConfig · InstructionConfig
from agent_evaluator import (
    PlanConfig,
    SubtaskConfig,
    InstructionConfig,
)

@agent_eval(
    monitor,
    task_type="planning",
    plan_tracking=PlanConfig(
        available_tools=["search", "analyze", "write", "format"],
        min_steps=3,
        check_executability=True,
    ),
    subtask_tracking=SubtaskConfig(
        expected_subtasks=["조사", "분석", "작성", "검토"],
        min_completion_rate=0.75,
    ),
    instructions=InstructionConfig(
        required_sections=["개요", "결론"],
        min_words=100,
    ),
)
def research_agent(question: str, ground_truth: str = "") -> str:
    return planner.run(question)
```

- **`PlanConfig` + `SubtaskConfig` 병용**: 거시적 계획 구조(단계 수·실행 가능성)와 미시적 서브태스크 완료율을 동시에 측정한다
- **`required_sections=["개요", "결론"]`**: 연구 보고서 형식의 필수 구조를 강제해 형식 미준수 응답을 탐지한다
- **`min_completion_rate=0.75`**: 4개 서브태스크 중 3개 이상 완료되어야 Gate A 판정이 통과된다

---

## 4.5 AI Native 관점 — Group A의 확률론적 품질

### 4.5.1 TCR은 분포로 이해해야 한다

`TCR=0.85`는 완전한 정보가 아니다. 동일한 TCR이라도:
- 분산이 작은 경우: 거의 모든 태스크에서 안정적으로 85% 달성
- 분산이 큰 경우: 어떤 태스크에선 100%, 어떤 태스크에선 40%

배포 결정은 분포를 보고 내려야 한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — RunTrendAnalyzer 추세 분석
from agent_evaluator.cli.trend import RunTrendAnalyzer

# 최근 10개 평가 결과의 TCR 추세 분석 (window는 생성자에서 지정)
analyzer = RunTrendAnalyzer("results/", window=10)
report = analyzer.analyze()   # RunTrendReport 반환

if report.tcr_trend:
    print(f"TCR 추세 기울기: {report.tcr_trend.slope:.4f}")    # 음수면 하락 추세
    print(f"TCR 방향: {report.tcr_trend.direction}")            # "stable"|"improving"|"degrading"
    print(f"TCR 최초값: {report.tcr_trend.first_val:.3f}")
    print(f"TCR 최종값: {report.tcr_trend.last_val:.3f}")
print(f"회귀 감지: {report.any_regression}")   # True → 배포 위험
```

- **`RunTrendAnalyzer("results/", window=10)`**: `results/` 디렉토리의 JSON 결과 파일을 수정 시간순으로 정렬해 최근 10개를 분석한다
- **`slope` 음수**: TCR이 시간이 지나면서 하락 중임을 의미하며, `direction="degrading"`으로 표시된다
- **`any_regression=True`**: TCR·정확도·비용 중 하나라도 회귀가 감지되면 `True`가 된다 — CI/CD에서 즉시 배포 차단 신호로 활용한다

또는 CLI로 간단히 확인:

```bash
# 최근 10개 결과 추세 분석
agent-eval trend results/ --window 10

# 회귀 감지 시 CI/CD 실패 처리
agent-eval trend results/ --fail-on-regression
```

### 4.5.2 accuracy는 task_type별로 다르게 해석한다

같은 `accuracy=0.8`이라도 task_type에 따라 의미가 다르다:
- `qa`: 정보 검색 정확도 — 0.8이면 보통 수준
- `code_generation`: 코드 정확도 — 0.8이면 낮음 (프로덕션 코드는 0.95+ 권장)
- `creative`: 창의적 글쓰기 — ground_truth와의 일치도가 낮아도 품질이 높을 수 있음

```python
# 출처: Evaluator_Examples/ch04_group_a.py — 예제 코드
# task_type별 권장 Accuracy 임계값
ACCURACY_THRESHOLDS = {
    "qa": 0.70,
    "code_generation": 0.90,
    "information_retrieval": 0.75,
    "creative": 0.50,      # 창의적 작업은 낮게 설정
    "reasoning": 0.80,
    "planning": 0.70,
}

eval.gate(
    tcr=85,
    accuracy=int(ACCURACY_THRESHOLDS.get(task_type, 0.70) * 100),
)
```

- **`task_type`별 차등 임계값**: 코드 생성은 0.90처럼 높게, 창의적 작업은 0.50처럼 낮게 설정해 task_type의 특성을 반영한다
- **`eval.gate(accuracy=...)`**: `accuracy` 파라미터는 0–100 정수 퍼센트로 전달한다 (0.0–1.0 float이 아닌 점에 주의)
- **동적 임계값**: 에이전트의 `task_type`을 런타임에 조회해 gate 기준을 유연하게 적용할 수 있다

### 4.5.3 AI-by-AI 평가 — LLM Judge로 목표달성 측정

ground_truth 없이 LLM Judge가 목표달성을 5차원으로 채점한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — LLMJudgeConfig
from agent_evaluator.decorators import LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        criteria=["goal_achievement", "instruction_following", "completeness"],
        sample_rate=0.2,  # 20%만 LLM 채점 (비용 절감)
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 결과 접근
report = monitor.generate_report()
d = report.to_dict()
# LLM Judge 결과는 extra_metrics 내 llm_judge 키 하위에 집계됨
judge_data = d.get("extra_metrics", {}).get("llm_judge", {})
print(judge_data.get("criteria_scores", {}))
# {"goal_achievement": 4.2, "instruction_following": 4.5, "completeness": 3.8}
```

- **`criteria=["goal_achievement", ...]`**: Gate A 관련 커스텀 기준을 G-Eval 방식으로 LLM에게 채점 요청한다 (0–5 척도)
- **`sample_rate=0.2`**: 전체 호출의 20%만 LLM Judge로 채점해 비용을 80% 절감한다
- **결과 경로**: `report.to_dict()["extra_metrics"]["llm_judge"]["criteria_scores"]`에 기준별 평균 점수가 집계된다
- **ground_truth 불필요**: LLM Judge는 응답과 질문만으로 목표달성 여부를 판단하므로 레이블 없이도 사용할 수 있다

---

## 4.6 HarnessEvaluationGate — Gate A 판정

Group A의 Config 위반과 Tracker 지표를 종합해 배포 가능 여부를 판정한다.

```python
# 출처: Evaluator_Examples/ch04_group_a.py — InstructionConfig · GoalAlignmentConfig · SLAConfig
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate
from agent_evaluator import (
    InstructionConfig,
    GoalAlignmentConfig,
    SLAConfig,
    ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(
    monitor,
    task_type="qa",
    instructions=InstructionConfig(
        expected_language="ko",
        fail_on_violation=True,
    ),
    goal_alignment=GoalAlignmentConfig(
        alignment_threshold=0.6,
    ),
    sla=SLAConfig(p95_ms=2000),
    threat_severity=ThreatSeverityConfig(fail_on_critical=True),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 평가 실행
for question, gt in test_dataset:
    agent(question, ground_truth=gt)

# Harness Gate 판정
report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

# Gate A 상세 결과
group_a = result["groups"].get("A", {})
print(f"Gate A 통과: {group_a.get('passed', 'n/a')}")
print(f"Gate A 점수: {group_a.get('score', 0.0):.3f}")
print(f"Gate A 상태: {group_a.get('status', 'n/a')}")

# 전체 Gate 결과
if result["passed"]:
    print("✅ Harness Gate 통과 — 배포 가능")
else:
    print(f"❌ Harness Gate 실패")
    # violations: [{"group": str, "score": float, "status": str}, ...]
    for v in result.get("violations", []):
        print(f"  Group {v['group']} 실패: score={v.get('score', 0.0):.3f} ({v.get('status', '')})")
```

- **4개 Config 조합**: Gate A(`InstructionConfig`·`GoalAlignmentConfig`)와 Gate D(`SLAConfig`)·Gate E(`ThreatSeverityConfig`)를 함께 선언해 4개 Gate를 한 번에 평가한다
- **`result["groups"]["A"]`**: Group A의 점수(`score`)와 통과 여부(`passed`)를 개별적으로 확인할 수 있다
- **`result["violations"]`**: Gate 실패 시 어느 Group이 몇 점으로 실패했는지 목록으로 반환해 즉각적인 원인 파악이 가능하다
- **`gate.enforce()` 대안**: 수동으로 `result["passed"]`를 확인하는 대신 `gate.enforce()`를 호출하면 실패 시 자동으로 `sys.exit(1)`이 실행된다

---

---

## 4.7 실전 예제 파일

이 챕터에서 설명한 Gate A Config 전체를 바로 실행해볼 수 있는 예제 파일이 준비되어 있다.

**기본 예제**: [`Evaluator_Examples/ch04_group_a.py`](../../Evaluator_Examples/ch04_group_a.py)
— Gate A FAIL 시나리오 포함, InstructionConfig·GoalAlignmentConfig·ContextRetentionConfig·PlanConfig·SubtaskConfig·KnowledgeRetentionConfig 6개 Config 전용 실전 예제

> **관련 챕터 예제**: Harness 전체 Gate 통합 흐름은 [Chapter 3 — `ch03_harness_basics.py`](Chapter_03_Harness_Engineering_기초.md), Layer 1 기초 트래커는 [Chapter 1 — `ch01_first_eval.py`](../Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md)에서 확인한다.

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
from agent_evaluator import (
    PerformanceMonitor, InstructionConfig, GoalAlignmentConfig,
    PlanConfig, SubtaskConfig,
)
from agent_evaluator.decorators import agent_eval
import json

monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# ── InstructionConfig: 응답 형식·필수 키워드·최소 길이 선언 ──
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="a_instruction",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence"],
        min_chars=20,
    ),
)
def instruction_agent(question: str, ground_truth: str = "") -> str:
    return json.dumps({"result": f"{question}에 대한 답변", "confidence": 0.92})

# ── GoalAlignmentConfig: 목표-도구 정렬 임계값 선언 ──
@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="a_goal",
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분석": ["analyze_tool", "search"]},
        alignment_threshold=0.5,
    ),
)
def goal_aligned_agent(question: str, ground_truth: str = "") -> str:
    return f"분석 결과: {question}에 대한 검색 및 분석 완료"

# ── PlanConfig: 계획 일관성·단계 완주율 선언 ──
@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_plan",
    plan_tracking=PlanConfig(
        check_goal_coverage=True,
        min_steps=2,
        available_tools=["search", "analyze"],
    ),
)
def plan_agent(question: str, ground_truth: str = "") -> str:
    plan = {"plan": {"steps": [
        {"name": "search",    "tool": "search",  "description": "정보 검색"},
        {"name": "analyze",   "tool": "analyze", "description": "결과 분석"},
        {"name": "summarize", "tool": "analyze", "description": "요약 작성"},
    ]}}
    return json.dumps(plan)

# ── SubtaskConfig: 하위 태스크 분해·완료율 선언 ──
@agent_eval(
    monitor,
    task_type="planning",
    task_id_prefix="a_subtask",
    subtask_tracking=SubtaskConfig(
        expected_subtasks=["데이터 수집", "분석", "요약"],
        min_completion_rate=0.7,
    ),
)
def subtask_agent(question: str, ground_truth: str = "") -> str:
    return "데이터 수집 완료, 분석 완료, 요약 작성 완료"
```

- **`task_id_prefix`**: 각 에이전트 함수에 고유 prefix를 지정해 리포트에서 Group A의 어느 Config가 어떤 태스크를 평가했는지 식별한다
- **`plan_agent` 반환 형식**: `json.dumps({"plan": {"steps": [...]}})` 구조로 반환해야 `PlanConfig`가 계획을 파싱한다
- **`subtask_agent` 응답**: "완료" 마커가 포함된 텍스트를 반환해 `SubtaskConfig`의 `completion_markers` 탐지가 작동한다
- **단일 monitor 공유**: 4개 에이전트 함수가 동일 `monitor`를 공유하므로 `generate_report()` 한 번으로 모든 Config 결과를 통합 집계한다

**Layer 1 Tracker 예제**

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — QA 정확도
@agent_eval(monitor, task_type="qa", task_id_prefix="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    """단순 QA 에이전트 — AccuracyEvaluator 자동 활성."""
    answers = {
        "한국의 수도는?":       "서울입니다.",
        "파이썬을 만든 사람은?": "귀도 반 로섬입니다.",
        "지구의 위성은?":        "달입니다.",
    }
    return answers.get(question, "잘 모르겠습니다.")

# 실행 후 결과 확인
report = monitor.generate_report()
monitor.save_to_file("group_a_eval")
# → results/group_a_eval.json  (+ .html)
# → agent-eval dashboard --results results/
```

- **`@agent_eval(monitor, task_type="qa")`**: 데코레이터만 붙이면 `AccuracyEvaluator`·`TaskCompletionTracker`·`ResponseQualityEvaluator`가 자동으로 활성화된다
- **`save_to_file("group_a_eval")`**: `results/group_a_eval.json`과 `results/group_a_eval.html` 두 파일을 자동 생성한다
- **대시보드 확인**: `agent-eval dashboard --results results/`를 실행하면 브라우저에서 Gate A 지표를 시각적으로 확인할 수 있다

```bash
# 전체 예제 실행
python Evaluator_Examples/ch03_harness_basics.py        # Gate A~G 전체
python Evaluator_Examples/ch01_first_eval.py  # Layer 1 Tracker 전체
python Evaluator_Examples/ch04_group_a.py   # 시나리오 6+7: Gate A FAIL 케이스
```

**FAIL 케이스**

시나리오 6: `InstructionConfig` + `GoalAlignmentConfig` 동시 위반 — JSON 형식 무시·목표 도구 미사용

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 역케이스 Gate A FAIL
from agent_evaluator import PerformanceMonitor, InstructionConfig, GoalAlignmentConfig
from agent_evaluator.decorators import agent_eval

monitor_a = PerformanceMonitor(output_dir="results/")

@agent_eval(
    monitor_a,
    task_type="qa",
    task_id_prefix="bad_a_goal",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["result", "confidence", "reasoning"],
        min_chars=100,
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"분석": ["analyze_tool", "search"]},
        alignment_threshold=0.6,
        ignore_no_tool_tasks=False,
    ),
)
def goal_failing_agent(question: str, ground_truth: str = "") -> str:
    # JSON 형식 미준수, required_keywords 없음, 목표 도구 미사용
    return f"네, {question} 처리했습니다."

goal_failing_agent("이 데이터를 분석해줘", ground_truth="분석 완료")
# → Gate A FAIL: instruction_score=0.0 (format 위반) + goal_alignment=0.0 (도구 미사용)
```

시나리오 7: `ContextRetentionConfig` + `KnowledgeRetentionConfig` 위반 — 핵심 엔티티 망각

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 역케이스 Gate A FAIL
from agent_evaluator import ContextRetentionConfig, KnowledgeRetentionConfig

@agent_eval(
    monitor_a,
    task_type="qa",
    task_id_prefix="bad_a_context",
    context_retention=ContextRetentionConfig(
        key_entities=["GPT-4", "Claude", "Gemini", "LLaMA"],
        retention_threshold=0.8,
    ),
    knowledge_retention=KnowledgeRetentionConfig(
        facts_to_retain=["OpenAI", "Anthropic", "Google", "Meta"],
        retention_threshold=0.8,
    ),
)
def context_forgetting_agent(question: str, ground_truth: str = "") -> str:
    # 핵심 엔티티를 전혀 언급하지 않음 → context_retention_score=0.0
    return f"이 주제에 대해 AI 업계에서 연구 중입니다. {question}"

context_forgetting_agent("주요 LLM 모델들을 비교해줘", ground_truth="모델 비교")
# → Gate A FAIL: context_retention=0.0 + knowledge_retention=0.0
```

- `goal_failing_agent`는 `expected_format="json"` 준수 실패 + `required_keywords` 누락 + 목표 도구(`analyze_tool`) 미사용으로 Gate A FAIL을 유도한다
- `context_forgetting_agent`는 응답에 `key_entities` 목록("GPT-4", "Claude" 등)이 전혀 없어 `context_retention_score=0.0`이 된다
- 두 시나리오 합산 시 Gate A 점수 ≈ 34% (FAIL)
- **대응 방법**: 응답 함수가 `expected_format`·`required_keywords`를 반드시 포함하도록 프롬프트를 수정하고, 컨텍스트 창에 `key_entities`를 항상 포함시킨다

---

## 4.8 이 챕터의 핵심 요약

**Gate A Tracker (상시 활성)**

| Tracker | 역할 | 핵심 파라미터 |
|---------|------|-------------|
| `TaskCompletionTracker` | TCR 측정 (Gate A 핵심 지표) | completion_score 3단계 자동 계산 |
| `AccuracyEvaluator` | 4중 가중 정확도 (Gate A 핵심 지표) | Token F1 40% + Jaccard 30% + LCS 20% + Levenshtein 10% |
| `HallucinationDetector` | 사실 일관성 (opt-in, Gate C 기여) | `rag_mode=True` 또는 `task_type="information_retrieval"` 시 활성화 |
| `ResponseQualityEvaluator` | 5차원 가중 품질 (Layer 1, Gate A 외 별도 집계) | relevance(×0.25) · completeness(×0.25) · accuracy(×0.20) · clarity(×0.15) · usefulness(×0.15) |

**Gate A Config 6종 (배포 기준 선언)**

| Config | 역할 | 핵심 파라미터 |
|--------|------|-------------|
| `InstructionConfig` | 형식·언어·길이 기준 | `expected_format`, `expected_language`, `fail_on_violation` |
| `GoalAlignmentConfig` | 목표-도구 정렬 기준 | `goal_tool_map`, `alignment_threshold`, `llm_blend_weight` |
| `PlanConfig` | 계획 완성도 기준 | `available_tools`, `check_executability`, `llm_blend_weight` |
| `ContextRetentionConfig` | 컨텍스트 보존 기준 | `key_entities`, `retention_threshold` |
| `SubtaskConfig` | 서브태스크 완료율 기준 | `expected_subtasks`, `min_completion_rate` |
| `KnowledgeRetentionConfig` | 대화 중 사실 보존 기준 | `facts_to_retain`, `seed_turns` |

> 🔗 **다음 챕터**: Chapter 5 — Gate B: 행동무결성  
> 에이전트가 허가된 범위 안에서만 동작하는지, 루프나 스코프 이탈 없이 작동하는지 측정하는 2개 Tracker와 6개 Config를 완전히 이해한다.
