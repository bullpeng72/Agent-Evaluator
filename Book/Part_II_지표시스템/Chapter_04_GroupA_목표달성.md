# Chapter 4. Group A — 목표달성 지표

```
┌────────────────────────────────────────────────────────────┐
│ 🔗 Harness 연결                                             │
│ Group A — Goal Achievement (목표달성)                       │
│ Tracker 3종: TaskCompletionTracker · AccuracyEvaluator ·   │
│              ResponseQualityEvaluator                       │
│ Config 6종: InstructionConfig · GoalAlignmentConfig ·      │
│             PlanConfig · ContextRetentionConfig ·           │
│             SubtaskConfig · KnowledgeRetentionConfig        │
│ Gate 판정: HarnessEvaluationGate.check_group_A()           │
└────────────────────────────────────────────────────────────┘
```

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group A 지표 입력·출력·기본값
> - **[Appendix H — 수학적 상세](../Appendix/H_알고리즘_수학적_레퍼런스.md)**: 4중 가중 정확도 공식, TCR 의사코드
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Group A Config 파라미터 전체 목록
> - **[Evaluator_Examples/01_layer1_all_metrics.py](../../Evaluator_Examples/01_layer1_all_metrics.py)**: Group A Tracker 실전 예제
> - **[Evaluator_Examples/08_harness_eval.py](../../Evaluator_Examples/08_harness_eval.py)**: Group A Config 실전 예제

> **독자별 읽기 가이드**  
> - **QA 관리자**: §4.1(개요) → §4.4(Config 설정) → §4.5(임계값·Gate 판정) 순서로 읽으면 "어떤 기준을 세울지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §4.2(Tracker 상세) → §4.3(코드 예제) → §4.4(Config 선언) 순서로 읽으면 구현에 바로 적용할 수 있습니다.

---

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Group A가 없으면 생기는 일                                │
│ "응답이 나왔다"는 것을 알지만, "목표를 달성했다"는 것은       │
│ 알 수 없다. 에이전트가 매번 응답을 생성하더라도 TCR이 70%     │
│ 이하면 3건 중 1건은 사용자가 원하는 결과를 얻지 못한다.       │
│                                                              │
│ 실제 사례: 고객 응대 봇이 "응답 생성률 100%"를 보고하면서     │
│ 고객 만족도가 60%에 머무른 회사. 응답은 나왔지만 질문에        │
│ 맞는 답변이 아니었다. AccuracyEvaluator 미도입이 원인.        │
└────────────────────────────────────────────────────────────┘
```

---

## 4.1 Group A 개요

Group A는 에이전트가 사용자의 **목표를 달성했는가**를 측정한다. 이것이 Harness Engineering의 출발점이다. 에이전트가 아무리 빠르고 안전해도 목표를 달성하지 못하면 배포할 수 없다.

### Group A가 다루는 3가지 질문

1. **완수**: 태스크가 실제로 완료되었는가? (TCR)
2. **정확**: 완료된 내용이 ground_truth와 일치하는가? (Accuracy)
3. **형식**: 응답이 요구된 형식·언어·길이를 충족하는가? (Instruction Config)

### Tracker vs Config — Group A 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "현재 목표달성이 어느 수준인가?" | "이 수준이면 배포 가능한가?" |
| 코드 위치 | `PerformanceMonitor` 내부 자동 동작 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 선언 |
| 결과 | `report.to_dict()["tcr"]` 등 | `fail_on_violation=True` 시 자동 fail |
| 예시 | `tcr=0.87` → "현재 87% 완료" | `InstructionConfig(max_words=200)` → "200단어 초과 불가" |

---

## 4.2 Tracker 3종 심화

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

report = monitor.generate_report()
d = report.to_dict()
print(f"TCR: {d['tcr'] * 100:.1f}%")              # TCR: 80.0%
print(f"완전 성공: {d['full_success_rate'] * 100:.1f}%")  # 50.0%
print(f"부분 성공: {d['partial_success_rate'] * 100:.1f}%")  # 50.0%
```

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
# 4중 가중 정확도 계산 예시
from agent_evaluator.helpers.taskresult_helpers import create_taskresult

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

**코드 정확도 — AST 비교**

`task_type="code_generation"`이면 텍스트 비교 대신 Python AST 비교를 사용한다.

```python
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

**Accuracy 임계값 가이드:**

| 정확도 | 상태 | 의미 |
|--------|------|------|
| ≥ 0.85 | 🟢 우수 | 배포 가능 |
| 0.70~0.85 | 🟡 보통 | 프롬프트 개선 권장 |
| 0.50~0.70 | 🟠 미흡 | ground_truth 품질 확인 필요 |
| < 0.50 | 🔴 낮음 | 에이전트 전면 재검토 |

### 4.2.3 ResponseQualityEvaluator — 5차원 품질 평가

ground_truth 없이도 응답 자체의 품질을 5개 차원으로 평가한다. 각 차원을 0~5 척도로 측정하고 `quality_score`(평균)를 계산한다.

| 차원 | 측정 내용 |
|------|---------|
| completeness | 응답이 질문에 완전히 답했는가? |
| relevance | 응답이 질문과 관련이 있는가? |
| clarity | 응답이 명확하고 이해하기 쉬운가? |
| coherence | 응답이 논리적으로 일관성 있는가? |
| depth | 응답이 충분한 깊이와 상세함을 가지는가? |

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

agent("딥러닝이란 무엇인가?")

report = monitor.generate_report()
d = report.to_dict()
print(d["quality_score"])           # 4.1 (0~5 척도)
print(d["quality_dimensions"])      # {"completeness": 4.5, "relevance": 4.2, ...}
```

---

## 4.3 Config 6종 레퍼런스

### 4.3.1 InstructionConfig — 응답 형식·언어·길이 준수

응답이 선언된 형식·언어·길이 기준을 지키는지 검증한다. **가장 먼저 도입해야 할 Config**다.

```python
from agent_evaluator.decorators import InstructionConfig

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

**사용 예시:**

```python
from agent_evaluator.decorators import agent_eval, InstructionConfig

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

**임계값 가이드:**

| 항목 | 권장 기준 |
|------|---------|
| 응답 언어 | 사용자 인터페이스 언어와 일치 |
| max_words | 사용 맥락에 맞게 (챗봇: 150, 리포트: 500) |
| forbidden_phrases | "모르겠습니다" 등 에이전트 역량 부족 신호 차단 |

### 4.3.2 GoalAlignmentConfig — 목표-행동 정렬

에이전트가 사용한 도구가 질문의 목표와 정렬되어 있는지 측정한다. "검색"이 목표인데 "코드 실행"을 사용했다면 정렬이 낮다.

```python
from agent_evaluator.decorators import GoalAlignmentConfig

GoalAlignmentConfig(
    use_keyword_overlap=True,          # 질문 키워드 ↔ 도구명 오버랩 측정
    goal_tool_map={                    # 목표 키워드 → 적합한 도구 목록
        "검색": ["web_search", "search"],
        "요약": ["summarize", "compress"],
        "번역": ["translate"],
        "분석": ["analyze", "compute"],
    },
    use_llm_scoring=False,             # LLM-as-Judge 정렬 점수 (opt-in)
    alignment_threshold=0.6,           # 경고 임계값 (0.0~1.0)
    ignore_no_tool_tasks=True,         # 도구 미사용 태스크는 건너뜀
)
```

### 4.3.3 PlanConfig — 계획 실행 완성도

에이전트가 계획(plan)을 수립하고 그 계획대로 실행하는지 추적한다. 다단계 추론이나 복잡한 태스크를 처리하는 에이전트에 적합하다.

```python
from agent_evaluator.decorators import PlanConfig

PlanConfig(
    plan_field="plan",                 # 응답 JSON에서 계획 추출할 필드명
    steps_field="steps",               # 계획 내 단계 필드명
    check_goal_coverage=True,          # 목표 키워드가 계획 단계에 포함되는지
    check_step_ordering=True,          # 단계 순서 논리성 확인
    check_executability=True,          # 사용 가능한 도구로 실행 가능한지
    available_tools=["search", "code_exec", "summarize"],
    use_llm_scoring=False,             # LLM-as-Judge 계획 품질 채점
    min_steps=2,                       # 최소 계획 단계 수
    max_steps=15,                      # 최대 계획 단계 수
)
```

**사용 예시 — 연구 에이전트:**

```python
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

### 4.3.4 ContextRetentionConfig — 핵심 컨텍스트 보존

RAG 에이전트나 멀티턴 대화 에이전트에서 원래 목표와 핵심 엔티티가 응답 전반에 유지되는지 측정한다.

```python
from agent_evaluator.decorators import ContextRetentionConfig

ContextRetentionConfig(
    key_entities=["서울", "2024년", "인공지능"],  # 보존되어야 할 핵심 엔티티
    context_arg="context",                        # 컨텍스트 인자 이름
    retention_threshold=0.7,                      # 보존율 임계값
    check_original_goal=True,                     # 원래 목표 질문 보존 여부 확인
    entity_weight=0.6,                            # 엔티티 보존 가중치
    goal_weight=0.4,                              # 목표 보존 가중치
)
```

**사용 예시 — RAG 에이전트:**

```python
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

### 4.3.5 SubtaskConfig — 서브태스크 완료율

복잡한 태스크를 여러 하위 작업(subtask)으로 분해하고, 각 서브태스크의 완료 여부를 추적한다.

```python
from agent_evaluator.decorators import SubtaskConfig

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

### 4.3.6 KnowledgeRetentionConfig — 대화 중 사실 보존

멀티턴 대화에서 초기 턴에 언급된 사실이 이후 응답에서도 유지되는지 측정한다. 에이전트가 대화 중 "기억"을 잃는 문제를 탐지한다.

```python
from agent_evaluator.decorators import KnowledgeRetentionConfig

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

---

## 4.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 단순 QA 봇 (최소 구성)

```python
from agent_evaluator.decorators import InstructionConfig, SLAConfig

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

### 패턴 2 — RAG 에이전트 (컨텍스트 보존 포함)

```python
from agent_evaluator.decorators import (
    InstructionConfig, ContextRetentionConfig, GoalAlignmentConfig
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

### 패턴 3 — 복잡한 계획 에이전트 (서브태스크 추적)

```python
from agent_evaluator.decorators import (
    PlanConfig, SubtaskConfig, InstructionConfig
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

---

## 4.5 AI Native 관점 — Group A의 확률론적 품질

### 4.5.1 TCR은 분포로 이해해야 한다

`TCR=0.85`는 완전한 정보가 아니다. 동일한 TCR이라도:
- 분산이 작은 경우: 거의 모든 태스크에서 안정적으로 85% 달성
- 분산이 큰 경우: 어떤 태스크에선 100%, 어떤 태스크에선 40%

배포 결정은 분포를 보고 내려야 한다.

```python
from agent_evaluator import RunTrendAnalyzer

# 최근 10개 평가 결과의 TCR 추세 분석
analyzer = RunTrendAnalyzer("results/")
trend = analyzer.analyze(window=10)

print(f"TCR 평균: {trend['tcr_mean']:.3f}")
print(f"TCR 표준편차: {trend['tcr_std']:.3f}")
print(f"추세 기울기: {trend['tcr_slope']:.4f}")  # 음수면 하락 추세
print(f"회귀 위험: {trend['regression_risk']}")   # "low"|"medium"|"high"
```

### 4.5.2 accuracy는 task_type별로 다르게 해석한다

같은 `accuracy=0.8`이라도 task_type에 따라 의미가 다르다:
- `qa`: 정보 검색 정확도 — 0.8이면 보통 수준
- `code_generation`: 코드 정확도 — 0.8이면 낮음 (프로덕션 코드는 0.95+ 권장)
- `creative`: 창의적 글쓰기 — ground_truth와의 일치도가 낮아도 품질이 높을 수 있음

```python
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

### 4.5.3 AI-by-AI 평가 — LLM Judge로 목표달성 측정

ground_truth 없이 LLM Judge가 목표달성을 5차원으로 채점한다.

```python
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
judge_summary = report.to_dict().get("llm_judge_summary", {})
print(judge_summary.get("criteria_scores", {}))
# {"goal_achievement": 4.2, "instruction_following": 4.5, "completeness": 3.8}
```

---

## 4.6 HarnessEvaluationGate — Group A 판정

Group A의 Config 위반과 Tracker 지표를 종합해 배포 가능 여부를 판정한다.

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate
from agent_evaluator.decorators import (
    agent_eval, InstructionConfig, GoalAlignmentConfig,
    SLAConfig, ThreatSeverityConfig,
)

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

# Group A 상세 결과
group_a = result["groups"]["A"]
print(f"Group A 통과: {group_a['passed']}")
print(f"Group A 점수: {group_a['score']:.3f}")
if not group_a['passed']:
    print(f"위반 항목: {group_a['violations']}")

# 전체 Gate 결과
if result["passed"]:
    print("✅ Harness Gate 통과 — 배포 가능")
else:
    print(f"❌ Harness Gate 실패")
    print(f"차단 위반: {result['blocking_violations']}")
```

---

## 4.7 이 챕터의 핵심 요약

| 지표/Config | 역할 | 핵심 파라미터 |
|------------|------|-------------|
| `TaskCompletionTracker` | TCR 측정 | completion_score 3단계 자동 계산 |
| `AccuracyEvaluator` | 4중 가중 정확도 | Token F1 40% + Jaccard 30% + LCS 20% + Levenshtein 10% |
| `ResponseQualityEvaluator` | 5차원 품질 | completeness · relevance · clarity · coherence · depth |
| `InstructionConfig` | 형식·언어·길이 기준 | `expected_format`, `expected_language`, `fail_on_violation` |
| `GoalAlignmentConfig` | 목표-도구 정렬 기준 | `goal_tool_map`, `alignment_threshold` |
| `PlanConfig` | 계획 완성도 기준 | `available_tools`, `check_executability` |
| `ContextRetentionConfig` | 컨텍스트 보존 기준 | `key_entities`, `retention_threshold` |
| `SubtaskConfig` | 서브태스크 완료율 기준 | `expected_subtasks`, `min_completion_rate` |
| `KnowledgeRetentionConfig` | 대화 중 사실 보존 기준 | `facts_to_retain`, `seed_turns` |

> 🔗 **다음 챕터**: Chapter 5 — Group B: 행동무결성  
> 에이전트가 허가된 범위 안에서만 동작하는지, 루프나 스코프 이탈 없이 작동하는지 측정하는 2개 Tracker와 4개 Config를 완전히 이해한다.
