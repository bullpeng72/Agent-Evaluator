# Chapter 5. Layer 3 — 외부 평가 도구 통합

이 챕터에서는 Layer 1/2만으로 충분하지 않은 상황과 그 해결책을 다룬다. v0.7.6부터 LLM Judge는 Faithfulness(Ragas 대체)와 G-Eval 커스텀 기준(DeepEval 대체)을 네이티브로 지원하며, v0.7.8부터 LLM Judge 엔진이 기본 설치에 포함되어 있다. DeepEval과 Ragas는 심층 RAG 진단이나 전문 지표가 필요한 경우에 `[eval]` extras를 추가로 설치하여 활용한다.

---

## 5.1 Layer 3이 필요한 세 가지 상황

### Ground Truth가 없을 때

Layer 1의 Accuracy는 `ground_truth`가 있어야 계산된다. 하지만 많은 실제 에이전트는 정답을 정의하기 어렵다.

- 고객 서비스 챗봇: "좋은 응답"의 기준이 상황마다 다르다
- 창의적 글쓰기 에이전트: 정량적 정답이 없다
- 요약 에이전트: 핵심 정보를 담았는지 판단이 주관적이다

이런 경우 LLM Judge를 사용한다. LLM이 직접 심사위원이 되어 completeness(완결성), relevance(관련성), factual_consistency(사실 일관성), toxicity(독성), bias(편향) **5차원 기본**으로 자동 채점한다. safety_score는 `(10 - toxicity - bias) / 10`으로 자동 계산된다.

### RAG 파이프라인을 정밀하게 평가할 때

RAG 시스템은 검색과 생성 두 단계로 구성된다. Layer 1의 Accuracy와 Hallucination Detection만으로는 "검색이 잘못되었는가" vs "생성이 잘못되었는가"를 구분할 수 없다.

Ragas는 이 문제를 해결한다. Faithfulness(응답이 검색 결과에 충실한가), Answer Relevancy(응답이 질문에 관련 있는가), Context Precision(검색된 내용이 정확한가), Context Recall(필요한 내용이 충분히 검색되었는가) — 이 4가지 지표로 검색 단계와 생성 단계를 분리하여 진단한다.

### Toxicity/Bias 탐지가 필요할 때

퍼블릭 서비스에서 에이전트가 혐오 발언, 성별/인종 편향, 해악 콘텐츠를 생성하면 법적·사회적 위험이 된다. DeepEval의 Toxicity와 Bias 지표가 이를 자동으로 탐지한다. 또한 G-Eval을 통해 "전문성", "공감성" 등 서비스 특화 평가 기준을 LLM으로 정의하고 채점할 수 있다.

---

## 5.2 외부 평가 도구 선택 가이드

### LLM Judge vs DeepEval vs Ragas 비교

| 항목 | LLM Judge (v0.7.6+) | DeepEval | Ragas |
|-----|---------|--------|-----|
| **설치** | 기본 설치에 포함 | `[eval]` (중간) | `[eval]` (중간) |
| **Ground Truth 필요** | 불필요 | 선택적 | 일부 필요 (Recall) |
| **특화 영역** | 범용 5차원 + Faithfulness + G-Eval 커스텀 | 독성/편향 전문 | RAG 심층 진단 (4-way) |
| **비용** | LLM 호출 비용 | LLM 호출 비용 | LLM + 임베딩 비용 |
| **속도** | 보통 | 보통 | 느림 (임베딩 포함) |
| **커스터마이즈** | `judge_criteria=[...]`로 무제한 | G-Eval로 가능 | 제한적 |
| **데코레이터 통합** | `enable_llm_judge=True` ✅ | `HybridPerformanceMonitor` | `HybridPerformanceMonitor` |
| **권장 시나리오** | 대부분의 범용 평가 | 독성/편향 규제 대응 | Context Precision/Recall 필요 시 |

### 선택 플로우차트

```
내 에이전트가 RAG(문서 검색 + 생성) 구조인가?
    YES → [빠른 방법] LLM Judge + rag_mode=True + enable_llm_judge=True
                      → faithfulness 차원 자동 추가 (기본 설치에 포함)
          [심층 진단] Context Precision/Recall도 필요하다 → Ragas 추가 사용

정답(ground_truth)을 제공할 수 있는가?
    YES → Layer 1 Accuracy로 충분
          (독성/편향 규제 대응이 필요하면 DeepEval 추가)
    NO  ↓

서비스 특화 기준(전문성, 공감성 등)이 필요한가?
    YES → LLM Judge + judge_criteria=[...] (G-Eval 네이티브 대체)
    NO  ↓

단순히 "좋은 응답인가"를 5차원으로 확인하고 싶은가?
    YES → LLM Judge (가장 가벼운 선택. 기본 설치에 포함)
```

---

## 5.3 LLM Judge — Ground Truth 없는 자동 채점 (v0.7.6: 확장)

### 기본 5차원 + 선택적 확장

v0.7.6부터 LLM Judge는 기본 5차원 외에 RAG 컨텍스트가 있으면 `faithfulness`를 자동 추가하고, `judge_criteria`로 무제한 커스텀 차원을 추가할 수 있다.

| 차원 | 기본 포함 | 조건부 활성 |
|-----|---------|-----------|
| completeness | ✅ | — |
| relevance | ✅ | — |
| factual_consistency | ✅ | — |
| toxicity | ✅ | — |
| bias | ✅ | — |
| **faithfulness** | — | `rag_mode=True` + `enable_llm_judge=True` |
| **커스텀 차원** | — | `judge_criteria=[...]` |

결과는 `TaskResult.extra["llm_judge"]`에 자동으로 기록된다.

```python
# 기본: {"completeness": 4.5, "relevance": 5.0, "factual_consistency": 4.8,
#         "toxicity": 0.1, "bias": 0.0, "overall": 4.77}
# RAG:  + "faithfulness": 4.6
# 커스텀: + "criteria_scores": {"professionalism": 4.0}, "criteria_overall": 4.0
```

### 코드 1: 기본 LLM Judge (enable_llm_judge=True)

```python
from agent_evaluator import PerformanceMonitor, agent_eval
import os

os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")

monitor = PerformanceMonitor("results/")

# 해당 데코레이터 호출에만 LLM Judge 활성
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
)
def customer_service_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 결과 확인 — back-propagation으로 TaskResult에 자동 반영
customer_service_agent("환불 정책이 어떻게 되나요?")
customer_service_agent("배송은 얼마나 걸리나요?")

for task in monitor.tasks:
    judge = task.extra.get("llm_judge", {})
    print(f"질문: {task.extra.get('question', '')[:40]}")
    print(f"  완결성: {judge.get('completeness', 0):.2f}")
    print(f"  관련성: {judge.get('relevance', 0):.2f}")
    print(f"  사실성: {judge.get('factual_consistency', 0):.2f}")
    print(f"  종합:   {judge.get('overall', 0):.2f}")
    print()
```

QuickEval 팩토리를 사용하면 한 줄로 설정할 수 있다.

```python
from agent_evaluator import QuickEval

eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 코드 2: Faithfulness — Ragas 대체 (v0.7.6+)

RAG 에이전트에서 응답이 검색된 컨텍스트에 얼마나 충실한지를 측정한다.  
`rag_mode=True`와 `enable_llm_judge=True`를 함께 사용하면 `faithfulness` 차원이 자동 추가된다.  
`[eval]` extras 없이 기본 설치만으로 동작한다.

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,           # context_arg="context" + 할루시네이션 감지 활성
    enable_llm_judge=True,   # faithfulness 차원 자동 추가
    judge_model="claude-sonnet-4-6",
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})

rag_agent(
    "Python의 GIL이란?",
    context="GIL(Global Interpreter Lock)은 Python 인터프리터가...",
    ground_truth="GIL은 멀티스레딩 환경에서 하나의 스레드만 Python 바이트코드를 실행하도록 제한하는 뮤텍스입니다.",
)

for task in monitor.tasks:
    judge = task.extra.get("llm_judge", {})
    print(f"Faithfulness: {judge.get('faithfulness', 0):.2f}/5.0")
    # → "Faithfulness: 4.6/5.0"
```

### 코드 3: G-Eval 커스텀 기준 — DeepEval 대체 (v0.7.6+)

`judge_criteria`에 평가 차원 이름을 리스트로 전달하면 LLMJudge가 해당 차원으로 채점한다.  
DeepEval의 G-Eval을 기본 설치만으로 대체한다.

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor(
    "results/",
    judge_criteria=["professionalism", "empathy", "clarity"],  # 글로벌 설정
)

@agent_eval(monitor, task_type="qa", enable_llm_judge=True, judge_model="claude-sonnet-4-6")
def customer_service_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 또는 특정 호출에만 적용 (temp-override)
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_criteria=["safety", "regulatory_compliance"],  # 이 호출에만 적용
)
def regulated_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 결과 확인
for task in monitor.tasks:
    judge = task.extra.get("llm_judge", {})
    criteria = judge.get("criteria_scores", {})
    print(f"전문성: {criteria.get('professionalism', 0):.2f}")
    print(f"공감성: {criteria.get('empathy', 0):.2f}")
    print(f"명확성: {criteria.get('clarity', 0):.2f}")
    print(f"커스텀 종합: {judge.get('criteria_overall', 0):.2f}")
```

### judge_sample_rate=0.1 비용 제어

모든 호출에 LLM Judge를 적용하면 비용이 빠르게 증가한다. `judge_sample_rate`로 일부만 샘플링한다.

```python
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    judge_sample_rate=0.1,  # 10%만 LLM Judge 채점
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### judge_budget_per_day=5.0 일일 예산

일일 LLM Judge 비용이 예산을 초과하면 자동으로 스킵된다.

```python
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    judge_sample_rate=0.1,
    judge_budget_per_day=5.0,   # 일일 $5 예산 — 초과 시 자동 스킵
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 👨‍💻 개발자 TIP: LLM Judge 활용 시나리오

- **개발 단계**: `judge_sample_rate=1.0`으로 전수 평가하여 에이전트 품질 파악
- **스테이징**: `judge_sample_rate=0.3`으로 적당한 커버리지 유지
- **프로덕션**: `judge_sample_rate=0.05~0.1`, `judge_budget_per_day=5.0`으로 비용 제어

---

## 5.4 DeepEval 통합

### pip install "agent-evaluator[eval]"

DeepEval과 Ragas는 동일한 `[eval]` extras에 포함된다.

```bash
pip install "agent-evaluator[eval]"
# deepeval>=3.0.0,<4.0.0 + ragas>=0.4.0,<2.0.0 + datasets>=4.0.0,<6.0.0 설치
```

### G-Eval 커스텀 기준 설정

DeepEval의 핵심 가치는 G-Eval이다. "내가 정의한 기준"으로 LLM이 평가하도록 한다. 정량적 정답이 없는 창의성, 전문성, 어조 적합성 등을 평가할 때 유용하다.

`HybridPerformanceMonitor`에서는 `generate_report(quality_criteria=...)` 파라미터로 G-Eval 기준을 문자열로 전달한다. DeepEval의 `GEval` 객체를 직접 주입하는 방식은 지원하지 않는다.

### 코드: DeepEvalAdapter 사용

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,          # DeepEval 기본 지표 활성 (Hallucination, Toxicity, Bias, Answer Relevancy)
    deepeval_model="gpt-4o-mini",  # 평가 모델 (기본값)
)

@agent_eval(monitor, task_type="qa")
def content_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

from agent_evaluator import create_taskresult

# G-Eval 커스텀 기준: record_task() 호출 시 quality_criteria 전달
task = create_taskresult(
    task_id="task_001",
    question="저희 서비스에 문제가 생겼어요. 어떻게 해야 하나요?",
    response=content_agent("저희 서비스에 문제가 생겼어요. 어떻게 해야 하나요?"),
    ground_truth="고객 지원팀에 문의하시면 즉시 도움을 드릴 수 있습니다.",
    execution_time=1.5,
)
monitor.record_task(
    task,
    quality_criteria="응답이 전문적이고 공감적인가? 고객 서비스 응답으로 적절한가?",
)

report = monitor.generate_report()
advanced = report.advanced_metrics_summary  # HybridEvaluationReport 전용 필드

hal = advanced.get("hallucination_score", {})
rel = advanced.get("answer_relevancy", {})
tox = advanced.get("toxicity_score", {})
bias = advanced.get("bias_score", {})
g_eval = advanced.get("g_eval_score", {})
print(f"Hallucination 점수: {hal.get('mean', 'N/A')}")
print(f"Answer Relevancy:   {rel.get('mean', 'N/A')}")
print(f"Toxicity 점수:      {tox.get('mean', 'N/A')}")
print(f"Bias 점수:          {bias.get('mean', 'N/A')}")
print(f"G-Eval (전문성·공감성): {g_eval.get('mean', 'N/A')}")
```

독성 점수가 임계값을 초과하면 즉시 알림을 발송하는 패턴이 실무에서 자주 사용된다.

```python
from agent_evaluator import AlertRuleBuilder

toxicity_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.0,  # toxicity_score > 0이면 알림
    handler=lambda msg, tr: print(f"[CRITICAL] 독성 콘텐츠 탐지: {msg}"),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[toxicity_alert])
def public_chatbot(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 5.5 Ragas 통합 — RAG 파이프라인 4종 지표

### faithfulness, answer_relevancy, context_precision, context_recall

Ragas는 RAG 파이프라인 평가의 업계 표준이다. 4가지 지표는 서로 다른 측면을 측정한다.

```
입력: 질문(Q) + 검색된 컨텍스트(C) + 에이전트 응답(A) + 정답(G)

Faithfulness:      A가 C에 충실한가? (A의 주장이 C에서 뒷받침되는가)
Answer Relevancy:  A가 Q에 관련 있는가? (답변이 질문에 답하는가)
Context Precision: C가 정확한가? (검색된 것 중 실제로 필요한 비율)
Context Recall:    C가 충분한가? (필요한 정보를 모두 검색했는가)
```

낮은 지표별 원인과 해결책:

| 지표 | 낮을 때 원인 | 해결책 |
|-----|-----------|------|
| Faithfulness 낮음 | LLM이 컨텍스트를 무시하고 환각 생성 | 프롬프트에 "주어진 컨텍스트만 사용" 강화 |
| Answer Relevancy 낮음 | 검색은 잘 됐지만 답변이 엉뚱한 방향 | 답변 생성 프롬프트 개선 |
| Context Precision 낮음 | 관련 없는 문서가 검색됨 | 임베딩 모델 교체, 청킹 전략 개선 |
| Context Recall 낮음 | 필요한 문서가 누락됨 | 검색 개수(k) 증가, reranking 도입 |

### 코드: RagasAdapter + QuickEval.for_rag()

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval
import os

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
# Ragas는 임베딩에 OpenAI API를 사용

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_ragas=True,
)

@agent_eval(monitor, task_type="information_retrieval")
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    retrieved_docs = vector_db.search(question, k=5)
    context_text = "\n".join(doc.page_content for doc in retrieved_docs)
    return llm.invoke(
        f"Context:\n{context_text}\n\nQuestion: {question}\n\nAnswer:"
    )

# context 필드가 핵심 — Ragas가 이 값으로 Faithfulness 등을 계산
test_cases = [
    {
        "question": "한국의 GDP는 얼마인가?",
        "context": "2023년 한국의 GDP는 약 1조 7천억 달러로 세계 13위이다.",
        "ground_truth": "약 1조 7천억 달러",
    },
    {
        "question": "서울의 인구는?",
        "context": "서울특별시의 인구는 2023년 기준 약 940만 명이다.",
        "ground_truth": "약 940만 명",
    },
]

for case in test_cases:
    rag_agent(
        case["question"],
        context=case["context"],
        ground_truth=case["ground_truth"],
    )

report = monitor.generate_report()
advanced = report.advanced_metrics_summary  # HybridEvaluationReport 전용 필드

faith = advanced.get("faithfulness", {})
rel = advanced.get("answer_relevancy", {})
prec = advanced.get("context_precision", {})
recall = advanced.get("context_recall", {})
print(f"Faithfulness:      {faith.get('mean', 0):.2%}")
print(f"Answer Relevancy:  {rel.get('mean', 0):.2%}")
print(f"Context Precision: {prec.get('mean', 0):.2%}")
print(f"Context Recall:    {recall.get('mean', 0):.2%}")
```

QuickEval을 사용하면 더 간결하다.

```python
from agent_evaluator import QuickEval

# for_rag(): hallucination_detection=True 자동 활성
eval = QuickEval.for_rag("results/")

@eval.rag  # task_type="information_retrieval" + context_arg="context" + rag_mode=True
def rag_pipeline(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.get_relevant_documents(question)
    context = "\n".join([d.page_content for d in docs])
    return chain.invoke({"question": question, "context": context})

eval.save()
eval.gate(accuracy=0.75, hallucination=5)
```

### ragas 0.4.x API (EvaluationDataset, SingleTurnSample)

Agent-Evaluator는 Ragas 0.4.x API를 완전 지원한다. 내부적으로 `EvaluationDataset`과 `SingleTurnSample`을 사용한다.

```python
# ragas 0.4.x 직접 사용 시 참고
from ragas import EvaluationDataset, SingleTurnSample
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

sample = SingleTurnSample(
    user_input="한국의 수도는?",
    retrieved_contexts=["서울은 대한민국의 수도입니다."],
    response="서울입니다.",
    reference="서울",
)

dataset = EvaluationDataset(samples=[sample])
result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
```

### 📋 QA 관리자 TIP: Ragas로 RAG 개선 사이클 운영

```python
from agent_evaluator import QuickEval

# 1단계: 현재 버전 측정
eval_v1 = QuickEval.for_rag("results/v1/")
# ... v1 에이전트로 테스트셋 실행 ...
summary_v1 = eval_v1.summary()

# 2단계: 임베딩 모델 변경 후 재측정
eval_v2 = QuickEval.for_rag("results/v2/")
# ... v2 에이전트로 동일 테스트셋 실행 ...

# 3단계: 비교
comparison = eval_v1.compare(eval_v2)
print(f"Faithfulness 변화: {comparison.get('faithfulness_delta', 0):+.2%}")
print(f"Context Precision 변화: {comparison.get('context_precision_delta', 0):+.2%}")
```

---

## 5.6 Layer 3 비용 최적화 전략

### 샘플링 평가 (judge_sample_rate)

세 도구 모두 LLM API 호출 비용이 발생한다. 전수 평가는 개발 단계에서만 사용하고, 프로덕션에서는 반드시 샘플링을 적용한다.

```python
# LLM Judge: 10% 샘플링 + 일일 예산 제한
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    judge_sample_rate=0.1,        # 10%만 채점
    judge_budget_per_day=5.0,     # 일 $5 예산
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 개발 환경에서만 전수 평가

환경 변수로 샘플링 비율을 조절하면 개발/스테이징/프로덕션을 쉽게 구분할 수 있다.

```python
import os

# 환경별 샘플링 비율
SAMPLE_RATES = {
    "development": 1.0,    # 전수 평가
    "staging":     0.3,    # 30% 샘플링
    "production":  0.05,   # 5% 샘플링
}

env = os.getenv("APP_ENV", "development")
sample_rate = SAMPLE_RATES.get(env, 0.1)

@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    judge_sample_rate=sample_rate,
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

DeepEval과 Ragas는 상대적으로 비용이 높기 때문에, 프로덕션에서는 골든 데이터셋(소량의 검증된 케이스)으로만 실행하는 것을 권장한다.

```python
# 프로덕션 권장 패턴
# 1. 일상 평가: Layer 1 + LLM Judge 5% 샘플링
# 2. 주간 품질 검토: Layer 1 + LLM Judge 100% (골든 데이터셋만)
# 3. 릴리즈 전 검증: Layer 1 + DeepEval/Ragas (골든 데이터셋만)
```

### 비용 vs 정밀도 트레이드오프

| 구성 | 비용 수준 | 정밀도 | 권장 사용 환경 |
|-----|---------|------|------------|
| Layer 1만 | 무료 | 기본 | 개발 초기, 빠른 피드백 |
| Layer 1 + LLM Judge (10%) | 낮음 | 중간 | 프로덕션 일상 모니터링 |
| Layer 1 + LLM Judge (100%) | 중간 | 높음 | 스테이징, 주간 검토 |
| Layer 1 + DeepEval | 중간~높음 | 높음 | 퍼블릭 서비스 품질 감사 |
| Layer 1 + Ragas | 높음 | 매우 높음 | RAG 시스템 개선 사이클 |
| Layer 1 + 모두 조합 | 매우 높음 | 최고 | 릴리즈 전 전수 검증 |

비용을 최소화하면서 품질을 유지하는 실용적인 조합은 **Layer 1 + LLM Judge 10% 샘플링**이다. 이 구성만으로도 에이전트의 성능 저하를 조기에 감지할 수 있다.

```python
from agent_evaluator import QuickEval

# 실용적인 프로덕션 구성
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@eval.qa  # LLM Judge 10% 샘플링 기본 적용
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 자동 저장 — 10건마다
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
```

---

## 이 챕터의 핵심

- **Layer 3이 필요한 세 가지 상황**: Ground truth가 없을 때(LLM Judge), RAG 파이프라인을 정밀하게 평가할 때(Ragas), 독성/편향 탐지가 필요할 때(DeepEval).

- **LLM Judge는 가장 가벼운 Layer 3 선택지**다. 기본 설치에 포함되어 있으며, `enable_llm_judge=True` 한 줄로 활성화된다. completeness, relevance, factual_consistency, toxicity, bias **5차원 기본**으로 ground truth 없이 자동 채점한다 (safety_score 자동 포함). v0.7.6+에서는 `rag_mode=True` 조합으로 faithfulness, `judge_criteria=[...]`로 커스텀 차원도 추가된다.

- **Ragas는 RAG 파이프라인 진단에 특화**되어 있다. Faithfulness/Answer Relevancy/Context Precision/Context Recall 4가지 지표로 "검색 문제인가, 생성 문제인가"를 분리해서 진단할 수 있다.

- **세 도구 모두 LLM API 비용이 발생**한다. 프로덕션에서는 `judge_sample_rate`와 `judge_budget_per_day`로 반드시 비용을 제어해야 한다. 실용적인 기본값은 5~10% 샘플링이다.

- **환경별 샘플링 전략**을 정의하라. 개발(100%) → 스테이징(30%) → 프로덕션(5%)으로 단계를 나누면 비용과 품질을 균형 있게 유지할 수 있다.

---

## 실전 예제

이 챕터에서 다룬 HybridPerformanceMonitor, LLM Judge, DeepEval, Ragas, Phoenix 통합을 실행할 수 있는 예제 파일이 제공된다.

**파일**: `Evaluator_Examples/07_phoenix_hybrid.py`

**핵심 코드 (출처: `Evaluator_Examples/07_phoenix_hybrid.py`)**

**모니터 초기화 — 환경에 따른 분기**

```python
# 출처: Evaluator_Examples/07_phoenix_hybrid.py, 모니터 초기화 섹션
import os

def _check_eval_packages() -> bool:
    try:
        import deepeval  # noqa: F401
        import ragas     # noqa: F401
        return True
    except ImportError:
        return False

EVAL_AVAILABLE = _check_eval_packages() and bool(os.getenv("OPENAI_API_KEY", ""))

if EVAL_AVAILABLE:
    from agent_evaluator import HybridPerformanceMonitor
    monitor = HybridPerformanceMonitor(
        use_deepeval=True,           # DeepEval G-Eval·Hallucination·Toxicity
        use_ragas=True,              # Ragas Faithfulness·Answer Relevancy·Context Precision
        deepeval_model="gpt-4o-mini",
        ragas_model="gpt-4o-mini",
        output_dir="results/",
    )
else:
    from agent_evaluator import PerformanceMonitor
    monitor = PerformanceMonitor(output_dir="results/")
    # 결과 JSON에 데모 advanced_metrics 주입 → 대시보드 '외부평가' 탭 UI 확인 가능
```

- `HybridPerformanceMonitor`는 `pip install "agent-evaluator[eval]"` + `OPENAI_API_KEY` 두 가지가 모두 필요하다
- 미설치 환경에서는 `PerformanceMonitor`로 fallback해 기본 Layer 1+2 지표만 측정한다
- 두 경우 모두 `record_task()` / `save_to_file()` 인터페이스가 동일해 코드 전환이 최소화된다

**HybridPerformanceMonitor 태스크 평가**

```python
# 출처: Evaluator_Examples/07_phoenix_hybrid.py, 섹션 1
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="hybrid_rag_001",
    question="서울의 주요 특징은?",
    response="서울은 대한민국의 수도이자 최대 도시로, 약 950만 명이 거주합니다.",
    ground_truth="서울은 대한민국의 수도",
    execution_time=1.2,
    task_type="information_retrieval",
    tokens_used={"input": 120, "output": 40, "total": 160},
)

if EVAL_AVAILABLE:
    # HybridPerformanceMonitor: input_text/output_text/retrieved_context 전달
    monitor.record_task(
        result,
        input_text="서울의 주요 특징은?",
        output_text="서울은 대한민국의 수도이자 최대 도시로, 약 950만 명이 거주합니다.",
        expected_output="서울은 대한민국의 수도",
        retrieved_context=["서울은 대한민국의 수도입니다.", "인구는 약 950만 명입니다."],
    )
    # → DeepEval G-Eval·Hallucination + Ragas Faithfulness 자동 계산
else:
    monitor.record_task(result)  # Layer 1+2만 계산
```

- `retrieved_context` 파라미터를 전달하면 Ragas의 4개 RAG 지표(Faithfulness·Answer Relevancy·Context Precision·Context Recall)가 자동 계산된다
- `HybridEvaluationReport.advanced_metrics_summary`에서 DeepEval·Ragas 결과를 집계해서 확인한다
- `advanced_metrics`는 태스크별 `TaskResult.extra["advanced_metrics"]`에도 저장되어 대시보드 태스크 목록에서 개별 확인 가능하다

**LLMJudge — 외부 패키지 없이 G-Eval/Ragas 대체**

```python
# 출처: Evaluator_Examples/07_phoenix_hybrid.py에서 사용하는 LLMJudge 패턴
from agent_evaluator import LLMJudge, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,        # LLMJudge 활성화
    judge_sample_rate=0.1,        # 10%만 채점 (비용 절감)
    judge_criteria=["accuracy", "completeness"],  # G-Eval 커스텀 기준
)

@agent_eval(
    monitor, task_type="qa",
    enable_llm_judge=True,        # 데코레이터 수준 활성화
    judge_criteria=["medical_accuracy", "citation_quality"],
)
def medical_agent(question: str, ground_truth: str = "") -> str:
    return f"의학적 답변: {question}"

# 결과에 criteria_scores 포함
# result["scores"]["criteria_scores"] = {"medical_accuracy": 4, "citation_quality": 5}
# result["scores"]["criteria_overall"] = 4.5
```

- `judge_criteria`를 지정하면 DeepEval의 G-Eval을 외부 패키지 없이 대체한다. API 키만 있으면 동작한다
- `judge_sample_rate=0.1`로 10%만 채점해 비용을 절감한다. 이상 케이스 전수 채점이 필요하면 `sample_condition=lambda r, gt: r.accuracy_score < 0.5`로 조건부 샘플링을 설정한다
- `rag_mode=True` + `enable_llm_judge=True` 조합이면 `faithfulness` 점수(0-5)도 자동 추가된다 — Ragas LLM-based Faithfulness 대체

```bash
# Phoenix 서버 없이 실행 (목업 모드 — LLM Judge 없이도 동작)
python 07_phoenix_hybrid.py

# Phoenix + 외부 평가 활성화 (OPENAI_API_KEY 필요)
agent-eval monitor                            # 별도 터미널
pip install 'agent-evaluator[eval]'           # DeepEval·Ragas 설치
OPENAI_API_KEY=sk-... python 07_phoenix_hybrid.py
```

**예제 구성**

| 섹션 | 내용 |
|------|------|
| 섹션 1 | Phoenix Tracing + task_type별 `span.kind` 자동 매핑 (LLM·TOOL·RETRIEVER·AGENT) |
| 섹션 2 | Phoenix Playground 연동 — `llm.prompts` 속성으로 프롬프트 재현 |
| 섹션 3 | Phoenix Datasets 탭 — 고품질 케이스 자동 추출·업로드 |
| 섹션 4 | Phoenix Prompts 탭 REST 등록 예시 |
| 섹션 5 | GraphQL 조회 예시 5종 |

**실행 결과 (v0.8.0 기준, 목업 모드)**

```
  Phoenix 미실행 — OTEL 비활성
  섹션 1: 5개 태스크, span.kind 자동 매핑 완료
  외부평가 데이터 주입 완료:
    G-Eval 평균: 0.793  (min=0.71, max=0.88)
    RAG 지표 건수: 2건 (faithfulness·answer_relevancy·recall·precision)
  총 태스크: 7건  TCR: 57.1%
결과 저장 완료: results/07_phoenix_hybrid.json
```

> **LLM Judge(내장)와 DeepEval·Ragas(외부) 선택 기준**: ground truth 없이 빠른 품질 채점이 필요하면 `enable_llm_judge=True`(기본 설치 포함). RAG 파이프라인 정밀 진단이 필요하면 `pip install 'agent-evaluator[eval]'` + `RagasAdapter`.
