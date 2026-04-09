# M4 — Layer 3, FastAPI 대시보드, 알림 · 이상탐지 · 비용 제어 심층 분석

> **대상**: 운영 환경에서 AI 에이전트를 안정적으로 모니터링하려는 ML 엔지니어 / DevOps 엔지니어  
> **전제 조건**: M1(데코레이터), M2(Layer 1), M3(Layer 2) 수강 완료  
> **핵심 메시지**: Layer 1/2만으로 부족할 때, 운영 인프라와 어떻게 통합하는가

---

## 1. Layer 1/2 이후 — 외부 연동 기능 확장

### 1.1 Layer 1/2로 커버하지 못하는 상황과 데코레이터 기반 대안

Layer 1/2는 외부 의존성 없이 동작하며 대부분의 기본 지표를 커버한다. 특수한 평가가 필요한 경우 **데코레이터 파라미터 하나로** 확장할 수 있다:

| 상황 | Layer 1/2 한계 | 데코레이터 기반 해결책 |
|------|----------------|----------------------|
| RAG — 환각 정밀 탐지 | Hallucination은 단순 패턴 매칭 | `@agent_eval(..., rag_mode=True)` |
| Ground Truth 없는 평가 | Accuracy는 정답이 있어야 계산 가능 | `@agent_eval(..., enable_llm_judge=True, judge_model="claude-sonnet-4-6")` |
| 보안 위협 탐지 | 기본은 보안 지표 비활성 | `@agent_eval(..., security_mode=True)` |
| 모든 설정 최소화 | 각 파라미터 직접 설정 필요 | `QuickEval.for_rag()` · `QuickEval.for_security()` · `QuickEval.for_llm_judge()` |

### 1.2 상황별 데코레이터 설정 패턴

```python
from agent_evaluator.decorators import agent_eval
from agent_evaluator import PerformanceMonitor, QuickEval

# ① RAG 에이전트 — hallucination 자동 활성
monitor = PerformanceMonitor.for_rag_evaluation("results/")

@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_pipeline.run(question, context)

# ② LLM Judge — ground_truth 없이 자동 채점 (completeness·relevance·factual_consistency)
@agent_eval(monitor, task_type="qa",
            enable_llm_judge=True, judge_model="claude-sonnet-4-6",
            judge_sample_rate=0.1, judge_budget_per_day=5.0)
def general_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# ③ 보안 강화 에이전트 — 5종 보안 지표 임시 활성
@agent_eval(monitor, task_type="qa", security_mode=True)
def secure_agent(question: str, ground_truth: str = "") -> str:
    return agent.run(question)

# ④ QuickEval 팩토리 — 최소 설정
eval_rag  = QuickEval.for_rag("results/")           # hallucination 기본 활성
eval_sec  = QuickEval.for_security("results/")       # security 기본 활성
eval_llm  = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### 1.3 LLM Judge — ground_truth 없는 자동 채점

`LLMJudge`는 정답이 없는 상황에서 LLM이 직접 3차원으로 채점한다. `@agent_eval(enable_llm_judge=True)` 한 줄로 통합된다.

```python
# 채점 결과는 TaskResult.extra["llm_judge"]에 자동 기록
# {"completeness": 4.5, "relevance": 5.0, "factual_consistency": 4.8, "overall": 4.77}
```

**비용 제어 옵션:**
- `judge_sample_rate=0.1` — 10%만 LLM Judge로 채점
- `judge_budget_per_day=5.0` — 일일 $5 예산 초과 시 자동 스킵

### 1.4 설치

```bash
# LLM Judge (OpenAI/Anthropic 클라이언트)
pip install "agent-evaluator[llm]"

# 권장 실용 구성 (llm + serve + eval)
pip install "agent-evaluator[all]"
```

---

## 2. 외부 평가 도구 선택 가이드

Layer 1/2만으로 부족할 때 세 가지 외부 평가 방법을 선택할 수 있다. 중복 사용도 가능하지만 비용이 증가한다.

### 2.1 한눈에 비교

| | **LLM Judge** | **DeepEval** | **Ragas** |
|---|---|---|---|
| **설치** | `[llm]` (가벼움) | `[eval]` (중간) | `[eval]` (중간) |
| **주요 용도** | 정답 없는 응답 품질 평가 | NLP 품질 + 독성/편향 | RAG 파이프라인 전문 평가 |
| **Ground Truth 필요** | 불필요 | 부분 필요 | 필요 (Recall만) |
| **API 비용** | LLM 호출 비용 | LLM 호출 비용 | 임베딩 + LLM 비용 |
| **커스터마이즈** | 제한적 | G-Eval로 가능 | 제한적 |
| **데코레이터 통합** | `enable_llm_judge=True` | `HybridPerformanceMonitor` | `HybridPerformanceMonitor` |

### 2.2 선택 플로차트

```
내 에이전트가 RAG(문서 검색+생성)인가?
    YES → Ragas 사용 (Faithfulness, Context Precision/Recall)
    NO  ↓

정답(ground_truth)을 제공할 수 있는가?
    YES → Layer 1 Accuracy로 충분 (DeepEval은 추가 품질 검증용)
    NO  ↓

퍼블릭 서비스 or 콘텐츠 생성인가?
    YES → DeepEval (독성/편향 탐지 + G-Eval 커스텀 기준)
    NO  ↓

단순히 "좋은 응답인가" 3차원으로 확인하고 싶다?
    YES → LLM Judge (가장 가벼운 선택)
```

### 2.3 비용 제어 전략

세 도구 모두 LLM API 호출이 발생한다. 프로덕션에서는 샘플링이 필수다.

```python
# LLM Judge: 10%만 샘플링
@agent_eval(monitor, task_type="qa",
            enable_llm_judge=True, judge_sample_rate=0.1, judge_budget_per_day=5.0)
def agent(q, ground_truth=""): ...

# DeepEval / Ragas: 스테이징 환경에서만, 또는 골든 데이터셋(소량)으로
# → 프로덕션에서는 Layer 1 + LLM Judge 10% 샘플링 조합 권장
```

---

## 3. DeepEval 통합 — 심층 품질 평가

### 3.1 DeepEval이 제공하는 지표

| 지표 | 의미 | 사용 시점 |
|------|------|---------|
| G-Eval | LLM이 사용자 정의 기준으로 채점 | 커스텀 평가 기준이 있을 때 |
| Hallucination | 컨텍스트와 모순되는 내용 탐지 | RAG 시스템, 사실 기반 응답 |
| Toxicity | 혐오/욕설/해악 콘텐츠 탐지 | 퍼블릭 서비스, 콘텐츠 모더레이션 |
| Bias | 성별/인종/종교 편향 탐지 | 공정성이 중요한 서비스 |
| Answer Relevancy | 질문과 답변의 관련성 | 범용 QA, 검색 시스템 |

### 3.2 기본 사용법

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,
)

@agent_eval(monitor, task_type="qa")
def content_agent(question, ground_truth=""):
    return llm.invoke(question)

# 테스트 실행
content_agent("AI의 미래는 어떻게 될까요?", ground_truth="AI는 다양한 분야에서 발전할 것입니다.")

report = monitor.generate_report()
deepeval_metrics = report.deepeval_metrics

print(f"Hallucination 점수: {deepeval_metrics.get('hallucination_score', 'N/A')}")
print(f"Answer Relevancy:   {deepeval_metrics.get('answer_relevancy', 'N/A')}")
print(f"Toxicity 점수:      {deepeval_metrics.get('toxicity_score', 'N/A')}")
```

### 3.3 G-Eval — 커스텀 평가 기준

G-Eval의 핵심 가치는 "내가 정의한 기준"으로 LLM이 평가하도록 한다는 것이다. 정량적 정답이 없는 창의성, 전문성, 어조 적합성 등을 평가할 때 유용하다.

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

# 커스텀 평가 기준 정의
professionalism_metric = GEval(
    name="전문성",
    criteria="응답이 전문적이고 명확한가? 전문 용어를 적절히 사용하는가?",
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.7,
)

empathy_metric = GEval(
    name="공감성",
    criteria="고객 서비스 응답으로서 공감적이고 도움이 되는가?",
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.6,
)

# HybridPerformanceMonitor에 커스텀 지표 추가
monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,
    deepeval_metrics=[professionalism_metric, empathy_metric],
)
```

### 3.4 실무 활용 — 콘텐츠 모더레이션 파이프라인

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval, AlertRuleBuilder

monitor = HybridPerformanceMonitor("results/", use_deepeval=True)

# 독성 점수가 임계값 초과 시 즉시 알림
toxicity_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.0,  # toxicity_score > 0이면 알림
    handler=lambda msg, tr: slack_webhook.send(f"독성 콘텐츠 탐지: {msg}"),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[toxicity_alert])
def public_chatbot(question, ground_truth=""):
    return chatbot.respond(question)
```

---

## 4. Ragas 통합 — RAG 파이프라인 정밀 평가

### 3.1 Ragas 4가지 핵심 지표

Ragas는 RAG(Retrieval-Augmented Generation) 파이프라인을 위한 업계 표준 평가 프레임워크다.

```
입력: 질문(Q) + 검색된 컨텍스트(C) + 에이전트 응답(A) + 정답(G)

Faithfulness:         A가 C에 충실한가? (A의 주장이 C에서 뒷받침되는가)
Answer Relevancy:     A가 Q에 관련 있는가? (답변이 질문에 답하는가)
Context Precision:    C가 정확한가? (검색된 것 중 실제로 필요한 비율)
Context Recall:       C가 충분한가? (필요한 정보를 모두 검색했는가)
```

**왜 4가지가 모두 필요한가**:

```
Faithfulness 낮음 → LLM이 검색 결과를 무시하고 환각 생성
                   해결: 프롬프트에 "주어진 컨텍스트만 사용하라" 강화

Answer Relevancy 낮음 → 검색은 잘 됐지만 답변이 엉뚱한 곳으로 감
                        해결: 답변 생성 프롬프트 개선

Context Precision 낮음 → 관련 없는 문서가 검색됨
                         해결: 임베딩 모델 교체, 청킹 전략 개선

Context Recall 낮음 → 필요한 문서가 누락됨
                       해결: k(검색 개수) 증가, 재순위화(reranking) 도입
```

### 3.2 기본 사용법

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval, create_taskresult
import os

os.environ["OPENAI_API_KEY"] = "sk-..."  # Ragas는 임베딩에 OpenAI 사용

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_ragas=True,
)

@agent_eval(monitor, task_type="information_retrieval")
def rag_agent(question, context="", ground_truth=""):
    # 1단계: 검색
    retrieved_docs = vector_db.search(question, k=5)
    context_text = "\n".join(doc.page_content for doc in retrieved_docs)

    # 2단계: 생성
    answer = llm.invoke(
        f"Context:\n{context_text}\n\nQuestion: {question}\n\nAnswer:"
    )
    return answer

# 테스트 케이스 — context 필드가 핵심
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
ragas_metrics = report.ragas_metrics

print(f"Faithfulness:      {ragas_metrics.get('faithfulness', 0):.2%}")
print(f"Answer Relevancy:  {ragas_metrics.get('answer_relevancy', 0):.2%}")
print(f"Context Precision: {ragas_metrics.get('context_precision', 0):.2%}")
print(f"Context Recall:    {ragas_metrics.get('context_recall', 0):.2%}")
```

### 3.3 QuickEval로 RAG 평가

```python
from agent_evaluator import QuickEval

# RAG 전용 설정: hallucination_detection=True 자동 활성
eval = QuickEval.for_rag("results/")

@eval.rag  # task_type="information_retrieval" + context_arg="context" + rag_mode=True 자동 설정
def rag_pipeline(question, context="", ground_truth=""):
    docs = retriever.get_relevant_documents(question)
    return chain.invoke({"question": question, "context": docs})

eval.save()
eval.gate(accuracy=0.75)  # 75% 미만이면 CI/CD 실패
```

### 3.4 실무 팁 — RAG 개선 사이클

```python
# 1. 현재 성능 측정
eval_v1 = QuickEval.for_rag("results/v1/")
# ... 테스트 실행 ...
report_v1 = eval_v1.summary()

# 2. 임베딩 모델 변경 후 재측정
eval_v2 = QuickEval.for_rag("results/v2/")
# ... 테스트 실행 ...
report_v2 = eval_v2.summary()

# 3. 비교
comparison = eval_v1.compare(eval_v2)
print(f"Faithfulness 변화: {comparison['faithfulness_delta']:+.2%}")
print(f"Context Precision 변화: {comparison['context_precision_delta']:+.2%}")
```

---

## 5. LLM Judge — 내장 LLM-as-Judge 평가

### 4.1 LLM Judge vs Ragas/DeepEval

| 특징 | LLM Judge | Ragas | DeepEval |
|------|-----------|-------|---------|
| 외부 라이브러리 | 불필요 ([llm] extra만) | 필요 | 필요 |
| Ground Truth 필요 | 불필요 | 부분 필요 | 부분 필요 |
| 평가 차원 | 3가지 고정 | RAG 전문 | 다양한 NLP 지표 |
| 비용 | LLM API 호출 비용 | LLM API 호출 비용 | LLM API 호출 비용 |
| 커스터마이즈 | 제한적 | 불가 | G-Eval로 가능 |

LLM Judge는 **정답이 없는 상황**에서 가장 빛난다. 창의적 글쓰기, 고객 서비스 응답, 요약 등 정량적 정답을 정의하기 어려운 경우에 사용한다.

### 4.2 3가지 평가 차원

LLM Judge는 모든 응답을 3가지 차원으로 채점한다 (0.0–1.0):

```
completeness:        응답이 질문의 모든 측면을 다루는가?
relevance:           응답이 질문에 직접적으로 관련 있는가?
factual_consistency: 응답이 사실적으로 일관성 있는가? (ground_truth 있을 때)
```

### 4.3 기본 사용법

```python
from agent_evaluator import LLMJudge, PerformanceMonitor, agent_eval
import os

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

# LLM Judge 초기화
judge = LLMJudge(model="claude-sonnet-4-6")

monitor = PerformanceMonitor("results/")

# 방법 1: enable_llm_judge 파라미터 (해당 호출만 활성)
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
)
def creative_agent(question, ground_truth=""):
    return llm.invoke(question)

# 방법 2: QuickEval.for_llm_judge()
from agent_evaluator import QuickEval

eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@agent_eval(monitor, task_type="qa", enable_llm_judge=True, judge_model="claude-sonnet-4-6")
def customer_service_agent(question, ground_truth=""):
    return chatbot.respond(question)

# 결과 확인 — back-propagation으로 TaskResult에 자동 반영
report = monitor.generate_report()
for task in monitor.tasks:
    judge_scores = task.extra.get("llm_judge", {})
    print(f"질문: {task.extra.get('question', 'N/A')[:40]}")
    print(f"  완결성: {judge_scores.get('completeness', 0):.2f}")
    print(f"  관련성: {judge_scores.get('relevance', 0):.2f}")
    print(f"  사실성: {judge_scores.get('factual_consistency', 0):.2f}")
```

---

## 6. FastAPI 대시보드 — 운영 시각화

### 5.1 데이터 생성 — `save_to_file()` 필수

대시보드는 `results/` 의 JSON 파일을 읽습니다. 데코레이터 실행 후 반드시 저장 단계가 필요합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# 방법 A: 수동 저장
monitor.save_to_file("eval")        # results/eval.json + .html

# 방법 B: auto_save — N건마다 자동 저장
# monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# 방법 C: 데코레이터에 flush_every 지정
# @agent_eval(monitor, task_type="qa", flush_every=50, flush_filename="periodic")
```

### 5.2 대시보드 실행

```bash
pip install "agent-evaluator[serve]"

# 기본 실행 — results/ 디렉토리의 평가 파일 로드
agent-eval dashboard results/

# 파일 변경 감시 모드 (실시간 갱신)
agent-eval dashboard results/ --watch

# 포트 지정
agent-eval dashboard results/ --port 8080

# 브라우저에서 접속
# http://localhost:8765
```

### 5.3 50+ API 엔드포인트 카테고리

**태스크 조회 및 필터링**:

```bash
# 특정 태스크 상세 조회
GET /tasks/{id}
# 응답: llm_judge, streaming_steps, chunk_count 포함

# 텍스트 검색
GET /tasks/search?q=오류+메시지

# 복합 조건 필터
POST /tasks/filter
Content-Type: application/json
{
  "filters": [
    {"field": "accuracy_score", "op": "lt", "value": 0.5},
    {"field": "execution_time", "op": "gt", "value": 3.0}
  ],
  "logic": "AND"
}
```

---

## 7. 알림 시스템 — AlertRuleBuilder & SimpleTaskAlertRule

### 7.1 AlertRuleBuilder 팩토리 (권장)

`AlertRuleBuilder`는 자주 쓰이는 알림 조건을 정적 메서드로 제공한다:

| 팩토리 메서드 | 트리거 조건 | 권장 severity |
|---|---|---|
| `when_accuracy_below(threshold)` | accuracy_score < threshold | `"warning"` |
| `when_latency_above(seconds)` | execution_time > seconds | `"warning"` / `"error"` |
| `when_completion_below(threshold)` | completion_score < threshold | `"error"` |
| `when_error()` | errors 리스트 비어있지 않음 | `"error"` |
| `when_tool_calls_exceed(count)` | tool_calls > count | `"warning"` |

```python
from agent_evaluator import AlertRuleBuilder, SimpleTaskAlertRule, agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

# ① 팩토리 메서드로 빠르게 생성
accuracy_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.70,
    handler=lambda msg, tr: print(f"[WARN] 정확도 저하: {msg}"),
    severity="warning",
    cooldown=300,   # 300초 쿨다운 — 같은 규칙 반복 발송 방지
)

latency_alert = AlertRuleBuilder.when_latency_above(
    seconds=5.0,
    handler=lambda msg, tr: print(f"[WARN] 응답 지연: {msg}"),
    severity="warning",
    cooldown=60,
)

completion_alert = AlertRuleBuilder.when_completion_below(
    threshold=0.80,
    handler=lambda msg, tr: print(f"[ERROR] 태스크 실패율 급등: {msg}"),
    severity="error",
    cooldown=120,
)

# ② 데코레이터에 연결 — TaskResult 기록 시 자동 평가
@agent_eval(
    monitor,
    task_type="qa",
    alert_rules=[accuracy_alert, latency_alert, completion_alert],
)
def production_agent(question, ground_truth=""):
    return llm.invoke(question)
```

### 7.2 SimpleTaskAlertRule — 커스텀 조건 알림

팩토리로 커버되지 않는 복잡한 조건은 `SimpleTaskAlertRule`로 직접 정의한다:

```python
from agent_evaluator import SimpleTaskAlertRule

# 토큰 비용 급등 알림
token_cost_alert = SimpleTaskAlertRule(
    name="token_cost_spike",
    condition=lambda tr: tr.tokens_used > 4000,
    handler=lambda msg, tr: print(f"[WARN] 토큰 과다 사용: {tr.tokens_used} tokens"),
    severity="warning",
    cooldown=180,
)

# 복합 조건 — 정확도 낮은 동시에 시간도 오래 걸린 경우
double_fail_alert = SimpleTaskAlertRule(
    name="double_failure",
    condition=lambda tr: tr.accuracy_score < 0.6 and tr.execution_time > 10.0,
    handler=lambda msg, tr: print(f"[CRITICAL] 품질+지연 동시 저하! task={tr.task_id}"),
    severity="critical",
    cooldown=600,
)

# dry_run — 핸들러를 실행하지 않고 조건만 검증 (단위 테스트 활용)
result = double_fail_alert.dry_run(some_task_result)
print(result)   # True / False
```

### 7.3 프로덕션 알림 패턴 — Slack + 이메일 + 로거

```python
import os
import logging
import requests
from agent_evaluator import AlertRuleBuilder, SimpleTaskAlertRule, agent_eval, PerformanceMonitor

logger = logging.getLogger(__name__)

# --- 핸들러 정의 ---
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")

def slack_handler(msg: str, tr) -> None:
    """Slack 채널 전송 — 환경변수 미설정 시 로그로 fallback"""
    if SLACK_WEBHOOK:
        requests.post(SLACK_WEBHOOK, json={
            "text": f"🚨 *Agent Alert*\n{msg}\n• task_id: `{tr.task_id}`\n• accuracy: `{tr.accuracy_score:.2f}`"
        }, timeout=5)
    else:
        logger.warning("[SLACK_FALLBACK] %s", msg)

def log_handler(msg: str, tr) -> None:
    logger.error("[AGENT_ALERT] %s | task=%s | latency=%.2fs", msg, tr.task_id, tr.execution_time)

# --- 5종 알림 규칙 ---
ALERT_RULES = [
    AlertRuleBuilder.when_accuracy_below(
        threshold=0.70, handler=slack_handler, severity="warning", cooldown=300),
    AlertRuleBuilder.when_latency_above(
        seconds=8.0, handler=slack_handler, severity="warning", cooldown=60),
    AlertRuleBuilder.when_completion_below(
        threshold=0.75, handler=slack_handler, severity="error", cooldown=120),
    AlertRuleBuilder.when_error(
        handler=log_handler, severity="error", cooldown=30),
    SimpleTaskAlertRule(
        name="high_retry",
        condition=lambda tr: tr.attempts >= 3,
        handler=slack_handler,
        severity="warning",
        cooldown=300,
    ),
]

# --- PerformanceMonitor + 데코레이터 연결 ---
monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa", alert_rules=ALERT_RULES, flush_every=50)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 7.4 QA 관리자 — 알림 임계값 설정 가이드

알림을 너무 많이 보내면 "알림 피로"가 생겨 정작 중요한 이슈를 놓치게 된다. 아래 기준을 초기값으로 사용하고, 2주 후 실제 분포를 보고 조정한다:

| 지표 | Warning 임계값 | Error 임계값 | cooldown |
|------|---------------|-------------|---------|
| accuracy_score | < 0.70 | < 0.55 | 300s / 60s |
| execution_time | > 5s | > 10s | 60s / 30s |
| completion_score | < 0.80 | < 0.60 | 120s / 60s |
| tokens_used | > 3000 | > 6000 | 180s / 60s |
| attempts (재시도) | ≥ 2 | ≥ 4 | 300s / 120s |

> **팁**: 최초 배포 후 1주일은 `cooldown`을 길게 잡아 알림 빈도를 낮추고, 운영이 안정되면 단계적으로 줄인다.

---

## 8. 이상 탐지 — AnomalyDetector

### 8.1 동작 원리

`AnomalyDetector`는 Z-Score 기반 통계적 이상 탐지를 사용한다.

```python
from agent_evaluator import AnomalyDetector, PerformanceMonitor

monitor = PerformanceMonitor("results/")
detector = AnomalyDetector(z_score_threshold=2.5)

# save_to_file()이 자동으로 anomaly 데이터 포함
monitor.save_to_file("evaluation")
```

---

## 9. 비용 제어 — CostTracker & AdaptivePolicy

### 9.1 AdaptivePolicy — 예산 초과 시 자동 다운그레이드

```python
from agent_evaluator import AdaptivePolicy, SamplingStage, agent_eval

policy = AdaptivePolicy(
    daily_budget_usd=100.0,
    stages=[
        SamplingStage(name="normal", sample_rate=1.0, model="gpt-4o"),
        SamplingStage(name="reduced", sample_rate=0.5, model="gpt-4o-mini"),
    ]
)

current = policy.get_current_stage()

@agent_eval(monitor, task_type="qa", sample_rate=current.sample_rate)
def cost_aware_agent(question):
    return llm.invoke(question, model=current.model)
```

---

## 10. 골든 데이터셋 — GoldenSetBuilder

### 10.1 프로덕션 마이닝

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(min_score=0.85)
cases = builder.extract_cases(monitor.tasks)
builder.push_to_phoenix(cases, dataset_name="prod_golden")
```

---

## 11. 멀티턴 대화 평가 — ConversationSession

### 11.1 6가지 대화 지표

| 지표 | 설명 | 좋은 값 |
|------|------|---------|
| `context_retention` | 이전 대화 맥락 유지 능력 | > 0.8 |
| `topic_coherence` | 주제의 일관성 | > 0.7 |
| `progressive_depth` | 대화의 심화도 | > 0.6 |
| `session_completion` | 목표 달성 여부 | > 0.8 |

### 11.2 @conversation_eval 데코레이터 (권장 방법)

v0.7.3부터 수동으로 세션을 관리하는 패턴 대신 데코레이터를 사용하는 것이 권장됩니다. `PerformanceMonitor`와 연동하여 자동으로 턴을 누적하고 지표를 계산합니다.

```python
from agent_evaluator import PerformanceMonitor, conversation_eval, flush_conversation

monitor = PerformanceMonitor("results/")

@conversation_eval(
    monitor,
    session_id_arg="session_id",        # 세션 ID를 파라미터에서 읽음
    max_turns=10,                       # 10턴 초과 시 자동 종료
    on_turn=lambda turn: print(f"턴 {turn.turn_number} 완료"),
    on_flush=lambda metrics, sid: print(f"세션 {sid} 종료: {metrics.overall_score:.2f}")
)
def chatbot_agent(user_message, session_id="default", history=None):
    # 실제 에이전트 호출 (history는 데코레이터가 자동 주입)
    response = llm.invoke(user_message, history=history or [])
    return response

# 1. 턴 호출 (자동 누적)
chatbot_agent("안녕하세요", session_id="sess_001")
chatbot_agent("서울 여행 계획 알려줘", session_id="sess_001")

# 2. 세션 명시적 종료 및 기록
flush_conversation("sess_001")

# 세션 결과는 monitor.generate_report()에 자동 포함
report = monitor.generate_report()
print(report.conversation_metrics)
```

### 11.3 monitor.conversation() — 컨텍스트 매니저 패턴 (v0.6.3+)

데코레이터를 사용할 수 없는 복잡한 루프나 스크립트 환경에서는 컨텍스트 매니저 패턴을 사용합니다.

```python
# 컨텍스트 매니저 방식
with monitor.conversation("session_002") as conv:
    for user_msg in ["안녕", "누구니?"]:
        response = chatbot.respond(user_msg, history=conv.history)
        conv.turn(
            user=user_msg,
            agent=response,
            metadata={"latency": 0.5}
        )
```

---

## 마무리 — M4 핵심 요약

```
Layer 3: "네이티브 지표로 부족할 때"
  ├── §3 DeepEval    → Toxicity, Bias, G-Eval (커스텀 기준)
  ├── §4 Ragas       → RAG 파이프라인 전문 평가 (4종)
  └── §5 LLM Judge   → Ground Truth 없는 평가 (3차원)

운영 인프라:
  ├── §6  FastAPI 대시보드 → 50+ 엔드포인트, 실시간 WebSocket
  ├── §7  AlertRuleBuilder → 5종 알림 규칙, cooldown, Slack/이메일 핸들러
  ├── §8  AnomalyDetector  → Z-Score 이상 탐지 + 원인 설명
  ├── §9  CostTracker      → 비용 추적 + AdaptivePolicy 자동 절감
  └── §10 GoldenSetBuilder → 프로덕션 트래픽 → 회귀 테스트셋 자동화

멀티턴:
  └── §11 @conversation_eval → 세션 기반 대화 품질 측정 (권장)
```

### QA 관리자 — M4 최종 점검 체크리스트

- [ ] `save_to_file()` 또는 `auto_save=True` 설정 → 대시보드 데이터 생성
- [ ] `agent-eval dashboard results/ --watch` → 대시보드 실시간 확인
- [ ] 알림 임계값(accuracy/latency/completion) 팀 기준으로 설정
- [ ] Slack Webhook 환경변수 설정 (`SLACK_WEBHOOK_URL`)
- [ ] `flush_every=50` → 장기 운영 시 주기적 저장 보장
- [ ] GoldenSetBuilder로 점수 높은 케이스 → 회귀 테스트셋 추출
