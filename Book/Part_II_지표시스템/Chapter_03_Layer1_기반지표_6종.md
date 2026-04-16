# Chapter 3. Layer 1 — 모든 에이전트의 기반 지표 6종

이 챕터에서는 Agent-Evaluator의 Layer 1 지표 6종을 완전히 이해한다. `@agent_eval` 데코레이터 하나만 붙이면 외부 의존성 없이 자동으로 활성화되는 이 지표들이 어떻게 계산되고, 어떤 의미를 가지며, 실무에서 어떻게 활용하는지 코드와 함께 설명한다. QA 봇부터 RAG 시스템, 코드 생성 에이전트까지 에이전트 유형별 KPI 조합 전략도 함께 다룬다.

> 📖 **관련 레퍼런스**
> - **[Appendix A — 25개 지표 완전 레퍼런스](../Appendix/A_25개지표_레퍼런스.md)**: 각 지표의 입력·출력·임계값 기본값을 한눈에 조회
> - **[Appendix G — AI 품질 평가 이론적 기초](../Appendix/G_AI평가_이론적기초.md)**: Layer 1 지표 설계의 이론적 배경 (BLEU→Token F1 진화 과정)
> - **[Appendix H — 알고리즘 수학적 레퍼런스](../Appendix/H_알고리즘_수학적_레퍼런스.md)**: 4중 가중 정확도 공식, TCR 계산 의사코드, P95 수식 상세
> - **[Appendix I — 지표 비교 분석 및 선택 가이드](../Appendix/I_지표_비교분석_선택가이드.md)**: 어떤 에이전트에 어떤 지표 조합이 적합한지 결정 트리

---

## 3.1 Layer 1 설계 철학

### 외부 의존성 없이 동작하는 이유

Agent-Evaluator는 25개 지표를 세 레이어로 나눈다. Layer 1은 그 중 가장 하위이자 가장 중요한 계층으로, **외부 라이브러리를 전혀 요구하지 않는다**. numpy와 pandas만 있으면 충분하다.

이 설계 원칙은 실용적인 이유에서 비롯된다. LLM API 키가 없어도, DeepEval이나 Ragas를 설치하지 않아도, 에이전트를 처음 개발하는 날부터 측정을 시작할 수 있어야 한다. 측정을 시작하는 데 드는 마찰을 제로에 가깝게 낮추는 것이 설계 목표다.

### 모든 에이전트에 자동 적용되는 6개 지표

Layer 1의 6개 지표는 `@agent_eval` 데코레이터를 붙이는 순간부터 자동으로 수집된다. 별도 설정이 필요한 것은 `Hallucination Detection` 하나뿐이다.

| 지표 | 트래커 클래스 | 기본 활성 | 핵심 질문 |
|------|-------------|---------|---------|
| Task Completion Rate | `TaskCompletionTracker` | 자동 | 태스크가 얼마나 완료되는가? |
| Accuracy | `AccuracyEvaluator` | 자동 | 정답과 얼마나 가까운가? |
| Response Quality | `ResponseQualityEvaluator` | 자동 | 응답의 품질이 좋은가? |
| Latency | `LatencyTracker` | 자동 | 얼마나 빠른가? |
| Token Economy | `TokenEconomyTracker` | 자동 | 비용 효율적인가? |
| Hallucination Detection | `HallucinationDetector` | **opt-in** | 사실과 다른 말을 하는가? |

Hallucination만 opt-in인 이유는 NLP 연산 비용 때문이다. 나머지 5개는 단순 통계 계산이라 오버헤드가 무시할 수준이지만, 환각 탐지는 텍스트 분석이 필요해 성능에 영향을 준다.

### PerformanceMonitor와 TaskResult의 관계

Layer 1은 두 가지 핵심 객체의 협력으로 동작한다.

`TaskResult`는 단일 태스크 실행 결과를 담는 불변 데이터 클래스다. 태스크 ID, 태스크 유형, 성공 여부, 정확도, 실행 시간, 토큰 사용량 등 25개 필드(필수 10개 + 선택 15개)를 가진다. 이 객체에 평가에 필요한 모든 원시 데이터가 담긴다.

`PerformanceMonitor`는 중앙 오케스트레이터다. `record_task(result)` 메서드를 호출할 때마다 Layer 1 트래커 6개에 데이터를 분배하고, `generate_report()`를 호출하면 수집된 모든 데이터를 집계한 `EvaluationReport`를 반환한다.

`@agent_eval` 데코레이터는 이 과정을 자동화한다. 함수가 호출될 때 실행 시간과 성공 여부를 자동으로 측정하여 `TaskResult`를 생성하고, `monitor.record_task()`를 자동으로 호출한다.

```python
from agent_evaluator import QuickEval

# 1줄로 시작 — PerformanceMonitor + EvalDecorator 자동 구성
eval = QuickEval("results/")

@eval.qa  # task_type="qa" 자동 설정, Layer 1 기본 지표 5개 자동 활성 (Hallucination은 opt-in)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("한국의 수도는?", ground_truth="서울")

report = eval.monitor.generate_report()
d = report.to_dict()
# {
#   "tcr": 1.0,               # Task Completion Rate
#   "overall_accuracy": 0.87, # Accuracy
#   "quality_score": 4.2,     # Response Quality
#   "latency_p95": 1.23,      # Latency P95
#   "total_tokens": 45,       # Token Economy
# }
```

---

## 3.2 Task Completion Rate (TCR)

### 정의: 성공적으로 완료된 태스크 비율

TCR(Task Completion Rate)은 에이전트가 태스크를 얼마나 성공적으로 완료하는지 측정하는 핵심 KPI다. 프로덕션 배포 준비도를 나타내는 가장 직관적인 지표이기도 하다.

단순한 성공/실패 이분법 대신 **3단계 완료 수준**으로 구분한다.

| 완료 수준 | 기준 | 예시 |
|---------|-----|-----|
| 완전 성공 (Full Success) | completion_score = 1.0 | 정확한 답변, 정상 완료 |
| 부분 성공 (Partial Success) | 0.7 ≤ completion_score < 1.0 | 일부 불완전한 답변 |
| 실패 (Failure) | completion_score < 0.7 | 오류, 빈 응답, 예외 발생 |

### 측정 방법: completion_score 가중 평균

TCR 공식은 모든 태스크의 `completion_score`를 그대로 합산해 평균낸다.

```
TCR = (전체 completion_score 합계 / 전체 태스크 수) × 100(%)
```

예시: 전체 3건의 completion_score가 각각 1.0, 0.8, 0.0이라면 TCR = (1.0 + 0.8 + 0.0) / 3 × 100 = **60%**

데코레이터는 `completion_score`를 자동으로 결정한다. 함수가 정상 반환하면 `completion_score = 1.0`, 예외가 발생하면 `completion_score = 0.0`이다. 세밀한 제어가 필요하면 `EvalMetadata`로 직접 지정한다.

**task_type별 구조적 완료 판정 (v0.8.0+, ground_truth 없는 환경)**

| task_type | 판정 기준 | 결과 |
|-----------|----------|------|
| `code_generation`/`coding` | Python AST 파싱 성공 | 1.0 (유효 코드) / 길이 기반 fallback |
| `tool_use` | `tool_calls` 비어 있지 않음 | 1.0 / 0.6 (도구 미사용 부분 완료) |
| 기타 | 응답 길이 ≥ 10자 | 1.0 (기본값) |

```python
# code_generation: AST 파싱 가능한 코드면 completion_score = 1.0
result = create_taskresult(
    task_id="t1",
    question="두 수를 더하는 함수",
    response="def add(a, b):\n    return a + b",
    execution_time=1.0,
    task_type="code_generation",   # ground_truth 없어도 AST 파싱 → 1.0
)
# → completion_score = 1.0, TCR 신뢰도 향상

# tool_use: 도구를 실제 사용한 경우만 완전 완료
result = create_taskresult(
    task_id="t2",
    question="현재 날씨 검색",
    response="서울 맑음",
    execution_time=1.0,
    task_type="tool_use",
    tool_calls=[],                 # 도구 미사용 → completion_score = 0.6
)
```

### 코드 예시: TaskCompletionTracker 직접 사용 + create_taskresult() 활용

```python
from agent_evaluator import PerformanceMonitor, agent_eval, create_taskresult

monitor = PerformanceMonitor("results/")

# 방법 1: 데코레이터 (권장) — completion_score 자동 계산
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 방법 2: create_taskresult() — 직접 제어
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
    # completion_score를 직접 지정하거나 생략하면 자동 계산
)
monitor.record_task(result)

# 결과 확인
report = monitor.generate_report()
d = report.to_dict()
print(d["tcr"])                  # 0.87  (87%)
print(d["full_success_rate"])    # 0.75
print(d["partial_success_rate"]) # 0.24
print(d["failure_rate"])         # 0.01
```

### 📋 QA 관리자 TIP: TCR이 낮을 때 원인 분석 패턴

TCR이 임계값 이하로 떨어졌을 때 원인을 빠르게 찾는 방법이다.

```python
# 실패한 태스크만 필터링하여 오류 유형 분류
from collections import Counter

failed_tasks = [t for t in monitor.tasks if t.completion_score < 0.7]

# 공통 오류 패턴 찾기
error_types = Counter(
    e.split(":")[0]
    for t in failed_tasks
    for e in t.errors
)
print(error_types.most_common(5))
# [("ConnectionError", 12), ("TimeoutError", 5), ("ValueError", 3)]
```

오류 유형이 `ConnectionError`나 `TimeoutError`에 집중되어 있다면 인프라 문제다. `ValueError`가 많다면 프롬프트나 입력 데이터 형식 문제일 가능성이 높다.

### 임계값: 프로덕션 ≥ 85%, CI ≥ 80%

| TCR | 상태 | 권장 행동 |
|-----|-----|---------|
| ≥ 90% | 프로덕션 준비 완료 | 배포 가능 |
| 80~90% | 개선 필요 | 실패 케이스 분석 |
| 70~80% | 위험 | 주요 버그 수정 필요 |
| < 70% | 배포 불가 | 근본적 재설계 검토 |

CI/CD 파이프라인에서 TCR 게이팅을 적용하려면:

```python
# TCR 85% 미달 시 sys.exit(1) → CI 빌드 실패
eval.gate(tcr=85)
```

---

## 3.3 Accuracy — 4중 가중 알고리즘

### 왜 BLEU나 ROUGE가 아닌 Token F1인가?

AI 평가 분야에서 가장 오래된 정확도 지표는 BLEU(2002)와 ROUGE(2004)다. Agent-Evaluator가 이들 대신 Token F1을 중심으로 설계된 이유를 이해하면 4중 가중 공식이 왜 이런 형태인지 명확해진다.

| 항목 | BLEU | ROUGE-L | Token F1 (AE) | BERTScore |
|------|------|---------|---------------|-----------|
| **측정 방향** | Precision 중심 | Recall 중심 | 균형 F1 | F1 (BERT 공간) |
| **동의어 처리** | ❌ 없음 | ❌ 없음 | ❌ 없음 | ✅ 자동 처리 |
| **순서 반영** | 부분 (n-gram) | ✅ LCS | ❌ 없음 | 부분 (문맥 임베딩) |
| **외부 의존성** | 없음 | 없음 | 없음 | BERT 모델 필요 |
| **속도** | ⚡ 빠름 | ⚡ 빠름 | ⚡ 빠름 | 🐢 느림 (GPU 권장) |
| **인간 판단 상관** | 중간 (~0.5) | 중간 (~0.5) | 중간 (~0.55) | 높음 (~0.7) |
| **한국어 지원** | 제한적 | 제한적 | ✅ 전체 지원 | 한국어 BERT 필요 |

**선택 근거:**

- **BLEU는 Precision만 측정** — 응답이 얼마나 정답을 포함하는지(Recall)를 무시한다. 짧은 응답에 유리하게 편향된다.
- **ROUGE는 Recall만 측정** — 정답이 응답에 포함되는지를 보지만, 응답에 불필요한 정보가 많아도 감점이 없다.
- **Token F1은 균형** — Precision과 Recall을 동시에 고려한다. 핵심 토큰을 포함하면서도 불필요한 토큰을 최소화하는 응답이 높은 점수를 받는다.
- **BERTScore는 정밀하지만 느리고 무겁다** — 외부 BERT 모델이 필요하고 추론 시간이 수십~수백ms다. 대규모 프로덕션 모니터링에 적합하지 않다.

Token F1 하나로는 순서 정보와 문자 수준 변형을 잡지 못한다. 그래서 Jaccard(단어 집합), LCS(순서), Char Levenshtein(문자 수준)을 보완 지표로 가중 합산하는 4중 알고리즘을 사용한다.

**실패 케이스로 이해하는 각 지표의 역할:**
```
케이스: 순서 반전 응답
  정답: "첫 번째 단계는 A, 두 번째는 B, 세 번째는 C"
  응답: "C를 먼저 한 뒤 B, A 순서로 수행한다"
  
  Token F1 ≈ 0.8  (단어 대부분 포함 — 순서 오류 감지 못함)
  Jaccard  ≈ 0.8  (집합 교집합 높음 — 순서 무관)
  LCS      ≈ 0.33  (순서가 역방향 → 공통 부분 수열 짧음 ✓ 탐지)
  
→ LCS가 순서 오류를 탐지. 20% 가중치가 전체 점수를 낮춤으로써 올바른 신호를 보냄.
```

> 📖 **더 깊이**: 각 지표의 실패 사례와 태스크 유형별 권장 지표 조합은 → Appendix I §I.1

### Token Overlap F1 (40%)

가장 중요한 구성 요소다. 예측 응답과 정답을 각각 토큰으로 분리한 뒤 F1 스코어를 계산한다. 핵심 정보가 응답에 포함되었는지 확인하는 데 특화되어 있다.

```
Precision = 공통 토큰 수 / 예측 토큰 수
Recall    = 공통 토큰 수 / 정답 토큰 수
F1        = 2 × (Precision × Recall) / (Precision + Recall)
```

### Jaccard Similarity (30%)

두 텍스트를 단어 집합으로 변환한 뒤 교집합/합집합 비율을 계산한다. 순서와 관계없이 단어 집합의 유사도를 측정한다.

```
Jaccard = |교집합| / |합집합|
```

### LCS Ratio (20%)

최장 공통 부분 수열(Longest Common Subsequence)을 기반으로 계산한다. 단어 순서가 보존되는 유사도를 측정하기 때문에 Token F1이나 Jaccard가 놓치는 순서 관계를 포착한다.

### Char Similarity (10%)

**Levenshtein 거리 기반** 문자 수준 유사도다. 두 문자열 간 편집 거리(삽입·삭제·치환 최소 횟수)를 계산하여 문자 순서까지 반영한다. 오탈자나 어절 변형(예: "서울시" vs "서울")을 허용하는 유연한 매칭을 제공한다. 가중치가 낮지만 한국어처럼 형태 변화가 많은 언어에서 중요한 역할을 한다.

```
Char Similarity = 1 - (Levenshtein 거리 / max(len(s1), len(s2)))
```

> v0.8.0부터 집합 기반 문자 교집합(`set(s1) & set(s2)`) 대신 Levenshtein 거리로 통일. 문자 순서가 반영되어 "abc"와 "cba"가 다른 점수를 받는다.

### 최종 공식

```
accuracy = 0.4 × TokenOverlapF1 + 0.3 × Jaccard + 0.2 × LCSRatio + 0.1 × CharSimilarity
```

### 코드 예시: QA 평가에서 정확도 측정

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# ground_truth가 있으면 accuracy 자동 계산
qa_agent("한국의 수도는?", ground_truth="서울")
qa_agent("파이썬 탄생 연도는?", ground_truth="1991년")

report = monitor.generate_report()
d = report.to_dict()
print(d["overall_accuracy"])  # 0.82 (평균 정확도)
print(d["median_accuracy"])   # 0.85 (중앙값 — 이상치에 강건)
print(d["std_accuracy"])      # 0.12 (표준편차 — 일관성 지표)
```

### 코드 평가와 일반 평가의 차이 (AST 비교)

`task_type="code_generation"`을 지정하면 Accuracy 계산 방식이 달라진다. 텍스트 유사도 대신 **Python AST(Abstract Syntax Tree) 구조 비교**를 우선 시도한다.

```python
@agent_eval(monitor, task_type="code_generation")
def code_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(f"파이썬 코드로 작성해줘: {question}")

# AST 비교 → 정규화 비교 순으로 fallback
# 코드가 구조적으로 동일하면 accuracy = 1.0
# SyntaxError 발생 시 정규화된 문자열 비교로 전환
code_agent(
    "두 수를 더하는 함수",
    ground_truth="def add(a, b):\n    return a + b"
)
```

두 코드가 표현 방식만 다르고 동일한 AST 구조를 가지면 1.0을 반환한다. 구문 오류가 있으면 텍스트 유사도로 자동 fallback한다.

### 도메인 특화 정확도 함수

표준 알고리즘이 맞지 않는 도메인에는 커스텀 `score_fn`을 사용한다.

```python
def numeric_accuracy(response: str, ground_truth: str) -> float:
    """숫자 응답 전용 정확도 — 상대 오차 기반"""
    import re
    def extract_number(text):
        nums = re.findall(r"-?\d+\.?\d*", text)
        return float(nums[0]) if nums else None
    pred = extract_number(response)
    true = extract_number(ground_truth)
    if pred is None or true is None:
        return 0.0
    if true == 0:
        return 1.0 if pred == 0 else 0.0
    return max(0.0, 1.0 - abs(pred - true) / abs(true))

@agent_eval(monitor, task_type="qa", score_fn=numeric_accuracy)
def math_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 📋 QA 관리자 TIP: 정확도가 낮은 케이스 패턴 분류

```python
import pandas as pd

df = eval.export_to_dataframe()

# task_type별 평균 정확도 — 어떤 유형이 취약한지 파악
accuracy_by_type = df.groupby("task_type")["accuracy_score"].agg(
    ["mean", "std", "count"]
)
print(accuracy_by_type.sort_values("mean"))
# code_generation  0.62  0.18  25  ← 집중 개선 대상
# reasoning        0.71  0.15  30
# qa               0.84  0.11  45

# 정확도 낮고 레이턴시도 느린 "이중 취약" 태스크 — 최우선 개선
high_cost_low_quality = df[
    (df["accuracy_score"] < 0.7) & (df["execution_time"] > 3.0)
]
```

---

## 3.4 Response Quality — 5차원 품질 평가

### Relevance, Completeness, Accuracy, Clarity, Usefulness

Ground truth 없이도 측정할 수 있다는 점이 Response Quality의 핵심 장점이다. 실시간 프로덕션처럼 정답을 알 수 없는 환경에서도 품질을 모니터링할 수 있다.

| 차원 | 측정 내용 | 낮을 때 원인 |
|-----|---------|-----------|
| **Relevance** (관련성) | 응답이 질문에 관련되는가 | 에이전트가 질문을 오해함 |
| **Completeness** (완결성) | 질문의 모든 측면을 다루는가 | 일부 측면만 답함 |
| **Accuracy** (정확성) | 내용이 사실에 부합하는가 | 환각, 부정확한 정보 |
| **Clarity** (명확성) | 이해하기 쉬운가 | 전문 용어 과다, 복잡한 문장 |
| **Usefulness** (유용성) | 실제 도움이 되는가 | 관련은 있지만 실질적 가치 부족 |

### 각 차원 0~1 점수, 최종 5점 척도 변환

각 차원은 0.0~1.0으로 평가되고, 5개를 합산해 0.0~5.0의 총합 점수를 산출한다.

| total_score | 등급 | 의미 |
|------------|-----|-----|
| 4.5 ~ 5.0 | A | 탁월한 품질 |
| 4.0 ~ 4.5 | B | 양호한 품질 |
| 3.0 ~ 4.0 | C | 보통 품질 |
| 2.0 ~ 3.0 | D | 낮은 품질 |
| 0.0 ~ 2.0 | F | 매우 낮은 품질 |

### 코드 예시: quality_score 확인

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

agent("머신러닝과 딥러닝의 차이를 설명해줘")

report = monitor.generate_report()
d = report.to_dict()

print(d["quality_score"])    # 3.8  (5점 만점)
print(d["quality_grade"])    # "B"

# 차원별 점수 확인
dims = d.get("dimension_scores", {})
print(dims)
# {"relevance": 0.85, "completeness": 0.72, "accuracy": 0.80,
#  "clarity": 0.78, "usefulness": 0.68}

# 가장 취약한 차원 찾기
weakest = min(dims.items(), key=lambda x: x[1])
print(f"취약 차원: {weakest[0]} ({weakest[1]:.2f})")
# 취약 차원: usefulness (0.68)
```

### 👨‍💻 개발자 TIP: 차원별 대응 전략

- **Relevance 낮음** → 프롬프트에 "질문에 직접 답하라"는 명시적 지시 추가
- **Completeness 낮음** → 구조화된 응답 형식 지시 (예: "결론-이유-예시 순서로")
- **Accuracy 낮음** → 환각 방지 프롬프트 강화 ("모르면 모른다고 답하라"), RAG 컨텍스트 품질 개선
- **Clarity 낮음** → 독자 수준 명시 ("비개발자가 이해할 수 있도록")
- **Usefulness 낮음** → 응답에 구체적인 다음 단계나 실질적 가이드 포함 지시

---

## 3.5 Latency — 백분위수 기반 분석

### P50, P95, P99 설명

평균 레이턴시는 이상치에 민감해 실제 사용자 경험을 제대로 반영하지 못한다. Agent-Evaluator는 백분위수(percentile) 통계를 사용한다.

- **P50 (중앙값)**: 전체 요청의 50%가 이 시간 이내에 완료됨. 일반적인 사용자 경험
- **P95**: 전체 요청의 95%가 이 시간 이내에 완료됨. "느린 5%"가 얼마나 느린지 측정
- **P99**: 전체 요청의 99%가 이 시간 이내에 완료됨. 극단적인 케이스 탐지

SLA(Service Level Agreement)는 보통 P95를 기준으로 설정한다. "P95 3초 이내"는 "사용자의 95%가 3초 이내에 응답을 받는다"는 의미다.

### TTFT(Time-To-First-Token) — 스트리밍 에이전트

스트리밍 에이전트에서 전체 응답 완료 시간 외에 추가로 중요한 지표가 TTFT다. 첫 번째 토큰이 반환되는 시간으로, 사용자가 "응답이 시작되었다"고 인식하는 시점이다.

전체 응답이 5초 걸려도 첫 토큰이 0.5초 내에 도착하면 사용자는 훨씬 덜 답답함을 느낀다. 스트리밍 UX 설계에서 TTFT가 전체 레이턴시보다 더 중요한 경우가 많다.

### 코드 예시: execution_time 측정 + TTFT 자동 기록

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

# 일반 에이전트 — execution_time 자동 측정
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)  # 실행 시간 자동 측정

# 스트리밍 에이전트 — TTFT 자동 기록
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = "") -> str:
    for chunk in llm.stream(question):
        yield chunk  # 첫 번째 yield 시점이 TTFT로 자동 기록

agent("오늘 서울 날씨 어때?", ground_truth="맑음")

report = monitor.generate_report()
d = report.to_dict()

latency = d.get("latency_stats", {})
print(f"평균 레이턴시: {latency['mean']:.2f}초")
print(f"P50:          {latency['p50']:.2f}초")
print(f"P95:          {latency['p95']:.2f}초")
print(f"P99:          {latency['p99']:.2f}초")

# TTFT (스트리밍 에이전트만)
ttft = d.get("ttft_stats", {})
if ttft:
    print(f"TTFT 평균: {ttft['mean']:.3f}초")
    print(f"TTFT P95: {ttft['p95']:.3f}초")
```

### 📋 QA 관리자 TIP: P95 기준 SLA 설정 가이드

| P95 레이턴시 | 사용자 경험 | 권장 행동 |
|------------|---------|---------|
| < 1초 | 즉각 응답 — 우수 | 현행 유지 |
| 1~3초 | 약간의 대기 — 목표 수준 | 모니터링 지속 |
| 3~5초 | 눈에 띄는 지연 — 최적화 필요 | 캐싱, 모델 경량화 검토 |
| > 5초 | 사용자 이탈 위험 — 긴급 개선 | 즉시 조치 필요 |

P95 레이턴시 알림을 설정하려면:

```python
from agent_evaluator import AlertRuleBuilder

latency_alert = AlertRuleBuilder.when_latency_above(
    threshold_seconds=3.0,  # 3초 초과 시 알림
    handler=lambda msg, tr: print(f"[ALERT] 레이턴시 초과: {msg}"),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[latency_alert])
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

---

## 3.6 Token Economy — 비용 추정

### tokens_used (input + output)

Token Economy는 에이전트의 토큰 사용량과 비용을 추적한다. `framework` 어댑터를 지정하면 각 SDK의 응답 객체에서 토큰 정보를 자동 추출한다.

```python
# OpenAI: response.usage.prompt_tokens / completion_tokens / total_tokens
# Anthropic: response.usage.input_tokens / output_tokens
# LangChain: message.usage_metadata["input_tokens"] / ["output_tokens"]
```

프레임워크 어댑터 없이 수동으로 주입할 수도 있다.

```python
from agent_evaluator import EvalMetadata

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = custom_llm.invoke(question)
    return response["text"], EvalMetadata(tokens_used=response["token_count"])
```

### 모델별 단가 추정

내부에 모델별 가격 테이블이 내장되어 있어 `cost_usd`를 자동 계산한다.

| 모델 | 입력 (1K 토큰당) | 출력 (1K 토큰당) |
|-----|------------|------------|
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| claude-sonnet-4-6 | $0.003 | $0.015 |
| claude-haiku-4-5 | $0.00025 | $0.00125 |

### 코드 예시: 비용 집계

```python
from agent_evaluator import PerformanceMonitor, agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}]
    )  # 토큰 자동 추출

# 비용 확인
report = monitor.generate_report()
d = report.to_dict()

print(d["total_tokens"])            # 15420  (전체 토큰)
print(d["total_cost_usd"])          # 0.0045 (전체 비용 USD)
print(d["avg_cost_per_task"])       # 0.000045 (태스크당 평균)
print(d["estimated_monthly_cost"]) # 1.35   (월간 예상 비용 USD)

# 월 예산 역산
target_monthly = 100.0  # $100/월 예산
monthly_est = d.get("estimated_monthly_cost", 0)
if monthly_est > 0:
    scale_factor = target_monthly / monthly_est
    print(f"현재 규모에서 월 $100 한도 내 처리 가능 비율: {scale_factor:.1f}배")
```

### 👨‍💻 개발자 TIP: 모델 교체 비용/품질 분석

GPT-4o 대비 GPT-4o-mini의 비용 차이는 약 28배다. 정확도 저하가 5% 이내라면 소형 모델로 전환하는 것이 합리적이다.

```python
eval_large = QuickEval("results/gpt4o/")
eval_small = QuickEval("results/gpt4o_mini/")

# 각각 동일 테스트셋으로 평가 후 비교
comparison = eval_large.compare(eval_small)
# {"accuracy_delta": -0.04, "cost_delta": -0.0048, "latency_delta": -0.6}

if abs(comparison.get("accuracy_delta", 0)) < 0.05:
    print("소형 모델로 전환 권장: 5% 미만 품질 저하로 비용 90% 절감 가능")
```

---

## 3.7 Hallucination Detection — opt-in 지표

### 팩트 일관성 점수

Hallucination(환각)은 에이전트가 사실과 다른 내용을 자신 있게 말하는 현상이다. 특히 RAG 시스템에서 중요하다. 검색된 문서(context)를 기반으로 답해야 하는데, 문서에 없는 내용을 창작해서 말하는 경우를 탐지한다.

탐지 방식은 응답의 주장(claim)이 컨텍스트에 의해 뒷받침되는지 확인하는 **팩트 일관성 점수**다.

```
지원율(support_rate) = 컨텍스트로 뒷받침되는 주장 수 / 전체 주장 수
환각률(hallucination_rate) = 1.0 - support_rate
```

| 심각도 | 환각률 | 의미 |
|------|-----|-----|
| low | < 5% | 거의 없음 — 프로덕션 안전 |
| medium | 5~15% | 일부 사실 오류 — 모니터링 필요 |
| high | 15~30% | 상당한 오류 — 개선 필요 |
| critical | > 30% | 신뢰 불가 — 즉시 조치 필요 |

### enable_hallucination_detection=True 활성화

기본값은 `False`다. 성능에 영향을 주기 때문에 명시적으로 활성화해야 한다.

```python
from agent_evaluator import PerformanceMonitor

# 방법 1: PerformanceMonitor 레벨 — 모든 태스크에 적용
monitor = PerformanceMonitor(
    "results/",
    enable_hallucination_detection=True,  # 명시적 활성화
)
```

### rag_mode=True와의 관계

`rag_mode=True`는 hallucination detection을 포함한 RAG 평가에 최적화된 설정을 한 번에 활성화하는 단축 파라미터다.

```python
# rag_mode=True: context_arg 설정 + hallucination_detection 자동 활성
@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(f"Context: {context}\n\nQ: {question}")
```

### 코드 예시

```python
from agent_evaluator import QuickEval

# QuickEval.for_rag() — hallucination 기본 활성
eval = QuickEval.for_rag("results/")

@eval.rag  # task_type="information_retrieval" + rag_mode=True 자동 설정
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = vector_store.similarity_search(question)
    context = "\n".join([d.page_content for d in docs])
    return llm.invoke(f"Context: {context}\n\nQ: {question}")

rag_agent(
    "한국의 GDP는?",
    context="2023년 한국 GDP는 약 1조 7천억 달러입니다.",
    ground_truth="약 1조 7천억 달러",
)

report = eval.monitor.generate_report()
d = report.to_dict()
hallucination = d.get("hallucination", {})
print(f"환각률: {hallucination.get('rate', 0):.1%}")
print(f"미지원 주장 수: {hallucination.get('unsupported_claims_count', 0)}")

# CI/CD 게이팅 — 환각률 5% 초과 시 실패
eval.gate(hallucination=5)
```

---

## 3.8 지표 조합 전략 — 에이전트 유형별 KPI

에이전트 유형에 따라 어떤 지표를 집중해서 모니터링해야 하는지 다르다. 6개 지표를 모두 같은 가중치로 보는 것보다, 에이전트의 용도에 맞는 핵심 KPI를 정의하고 나머지는 참고 지표로 활용하는 전략이 효과적이다.

### QA 에이전트: TCR + Accuracy + Hallucination

```python
eval = QuickEval("results/")

@eval.qa
def qa_bot(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

eval.gate(
    tcr=85,        # 완료율 85% 이상
    accuracy=75,   # 정확도 75% 이상
    p95_latency=2.0,  # P95 2초 이하
)
```

**Accuracy < 70%** → 프롬프트에 few-shot 예제 추가, 모델 교체 검토  
**TCR < 80%** → 오류 패턴 분석, 재시도 로직 추가

### RAG 에이전트: Hallucination + Quality + Latency

```python
eval = QuickEval.for_rag("results/")

@eval.rag
def rag_system(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = vector_store.similarity_search(question)
    context = "\n".join([d.page_content for d in docs])
    return llm.invoke(f"Context: {context}\n\nQ: {question}")

eval.gate(
    tcr=85,
    accuracy=70,
    hallucination=5,  # 환각률 5% 이하
    quality=3.5,      # 품질 점수 3.5/5 이상
)
```

**Hallucination 높음** → 프롬프트에 "주어진 컨텍스트만 사용하라" 지시 강화, 검색 품질 개선

### 코드 에이전트: Accuracy (AST) + TCR

```python
eval = QuickEval("results/")

@eval.code  # task_type="code_generation" → AST 기반 accuracy 자동 활성
def code_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(f"파이썬 코드로: {question}")

eval.gate(
    tcr=90,       # 코드 에이전트는 완료율 기준 높게 설정
    accuracy=80,  # AST 기반 정확도
)
```

### 에이전트 유형별 핵심 지표 요약

| 에이전트 유형 | 1순위 | 2순위 | 3순위 | gate() 예시 |
|------------|-----|-----|-----|-----------|
| QA 봇 | Accuracy | TCR | Latency | `tcr=85, accuracy=75` |
| RAG 시스템 | Hallucination | Accuracy | Quality | `hallucination=5, accuracy=70` |
| 코드 생성 | Accuracy (AST) | TCR | Latency | `tcr=90, accuracy=80` |
| 대화 에이전트 | Quality | Latency | TCR | `quality=3.5, p95_latency=2.0` |
| 비용 최적화 에이전트 | TokenEconomy | TCR | Quality | `tcr=80` + 비용 모니터링 |

---

## 3.9 QA 관리자 헬스체크 가이드

평가 결과(`report.to_dict()` 또는 대시보드)를 처음 열었을 때 다음 순서로 확인한다.

### 결과를 받았을 때 읽는 순서

```
1단계: 배포 가능 여부 판단 (TCR)
    TCR ≥ 85%    → 계속
    TCR < 85%    → 즉시 중단, 실패 케이스 분석

2단계: 정확도 확인 (Accuracy)
    Accuracy ≥ 70% → 계속
    Accuracy < 70% → 프롬프트 개선 필요, 배포 보류

3단계: 사용자 경험 확인 (Quality + Latency)
    Quality ≥ 3.5 AND P95 ≤ 3.0초 → 계속
    둘 중 하나라도 미달 → 개선 후 재평가 권장

4단계: 비용 확인 (Token Economy)
    avg_cost_per_task × 예상 월 호출 수 ≤ 예산 → 계속
    예산 초과 → AdaptivePolicy 또는 모델 교체 검토

5단계: RAG 에이전트라면 환각 확인 (Hallucination)
    hallucination_rate ≤ 5% → 배포 가능
    > 5%  → 검색 품질 개선, 프롬프트 강화 필요
```

### 에이전트 유형별 최소 통과 기준

| 지표 | 내부 챗봇 | 고객 서비스 | RAG | 코드 생성 | 퍼블릭 서비스 |
|------|---------|-----------|-----|---------|------------|
| **TCR** | ≥ 80% | ≥ 90% | ≥ 85% | ≥ 85% | ≥ 95% |
| **Accuracy** | ≥ 65% | ≥ 75% | ≥ 70% | ≥ 80% | ≥ 70% |
| **Quality** | ≥ 3.0 | ≥ 4.0 | ≥ 3.5 | ≥ 3.5 | ≥ 4.0 |
| **P95 Latency** | ≤ 5.0s | ≤ 3.0s | ≤ 5.0s | ≤ 10.0s | ≤ 2.0s |
| **Hallucination** | — | ≤ 10% | ≤ 5% | — | ≤ 3% |

> 위 수치는 **업계 일반 권장값**이다. 실제 서비스 SLA와 사용자 기대치에 맞게 조정해야 한다.

### 지표 이상 징후 → 원인 분석 패턴

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
# ... 평가 실행 ...

summary = eval.summary()
df = eval.export_to_dataframe()

# ① TCR 낮음 → 어떤 태스크 유형에서 실패하는가?
failed = df[df["completion_score"] < 0.3]
print("실패 유형 분포:")
print(failed["task_type"].value_counts())

# ② Accuracy 낮음 → 특정 질문 패턴이 있는가?
low_acc = df[df["accuracy_score"] < 0.5].sort_values("accuracy_score")
print("\n정확도 하위 5개 질문:")
print(low_acc[["question", "response", "accuracy_score"]].head())

# ③ Latency 높음 → 어떤 태스크가 느린가?
slow = df[df["execution_time"] > df["execution_time"].quantile(0.95)]
print(f"\nP95 초과 태스크: {len(slow)}개")
print(slow[["question", "execution_time"]].head())

# ④ Quality 낮음 → 어느 차원이 문제인가?
report = eval.monitor.generate_report()
quality_detail = report.to_dict().get("quality_metrics", {})
for dim in ["relevance", "completeness", "clarity", "conciseness", "coherence"]:
    val = quality_detail.get(f"avg_{dim}", "N/A")
    print(f"  {dim}: {val}")
```

### 주간 품질 트렌드 모니터링

```python
# 이번 주 vs 지난 주 비교
eval_this = QuickEval("results/this_week/")
eval_last = QuickEval("results/last_week/")

comparison = eval_this.compare(eval_last)

print("주간 품질 변화:")
for metric, delta in comparison.items():
    arrow = "▲" if delta > 0 else "▼"
    print(f"  {metric}: {arrow} {delta:+.3f}")

# A/B 테스트: 통계적 유의성 검증 (scipy 있을 때)
ab = eval_this.ab_test(eval_last)
if ab.get("significant"):
    print(f"\n⚠️ 정확도 변화가 통계적으로 유의합니다 (p={ab['p_value']:.3f})")
```

---

## 보충: Layer 1 지표 × 데코레이터 활성화 방법

Layer 1 지표를 데코레이터로 수집하는 구체적인 방법 정리다.

| 지표 | `@agent_eval` | `@batch_eval` | `@conversation_eval` | 필수 파라미터 | 자동 여부 |
|---|:---:|:---:|:---:|---|---|
| TCR | ✅ | ✅ | ✅ | 없음 (`completion_fn` 선택) | **항상 자동** |
| Accuracy | ✅ | ✅ | ✅ | `ground_truth` 인자 존재 시 | ground_truth 있으면 자동 |
| Response Quality | ✅ | ✅ | ✅ | 없음 | response + question 자동 |
| Latency | ✅ | ✅ | ✅ | 없음 | **항상 자동** |
| TTFT | ✅ generator | ✅ `streaming_mode` | ❌ | generator 리턴 함수 | generator 시 자동 |
| Token Economy | ✅ | ✅ | ❌ | `framework=` 어댑터 or EvalMetadata | 지원 프레임워크 자동 |
| Hallucination Rate | ✅ | ✅ | ❌ | `rag_mode=True` (권장) | **수동 활성 필요** |

```python
# ① 기본 — TCR + Accuracy + Quality + Latency 자동
@agent_eval(monitor, task_type="qa")
def agent(question, ground_truth=""): ...

# ② 토큰 비용 추가 (OpenAI 어댑터)
@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question, ground_truth=""): ...

# ③ RAG 환각 탐지 (rag_mode 하나로 3가지 자동 설정)
@agent_eval(monitor, rag_mode=True)
def rag_agent(question, context="", ground_truth=""): ...
# 내부: context_arg="context" + enable_hallucination_detection=True + task_type="information_retrieval"

# ④ 커스텀 Accuracy 계산
@agent_eval(monitor, score_fn=lambda r, gt: custom_similarity(r, gt))
def agent(question, ground_truth=""): ...
```

---

## 이 챕터의 핵심

- **Layer 1 기본 지표 5개는 `@agent_eval` 한 줄만으로 자동 활성화**된다. Hallucination만 `enable_hallucination_detection=True` (데코레이터 또는 PerformanceMonitor) 또는 `rag_mode=True`로 활성화된다.

- **TCR은 3단계 완료 수준**으로 구분한다 (완전/부분/실패). 프로덕션 배포 기준은 TCR ≥ 85%, CI 게이팅은 ≥ 80%가 권장값이다.

- **Accuracy는 4중 가중 알고리즘**으로 계산된다 (Token F1 40% + Jaccard 30% + LCS 20% + Char 10%). 코드 생성은 AST 비교로 자동 전환된다.

- **Latency는 P95 기준으로 SLA를 설정**한다. 스트리밍 에이전트는 TTFT를 추가로 모니터링한다. P95 < 3초가 실용적 목표값이다.

- **에이전트 유형별 KPI를 정의**하고 `eval.gate()`로 CI/CD에 통합하면, 품질 저하를 배포 전에 차단할 수 있다.

---

## 실전 예제

이 챕터에서 다룬 Layer 1 지표 6종 전체를 한 번에 실행할 수 있는 예제 파일이 제공된다.

**파일**: `Evaluator_Examples/01_layer1_all_metrics.py`

**핵심 코드 (출처: `Evaluator_Examples/01_layer1_all_metrics.py`)**

**섹션 1 — QA 정확도 측정 (`AccuracyEvaluator`)**

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 1
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/", enable_hallucination_detection=True)

@agent_eval(monitor, task_type="qa", task_id_prefix="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    answers = {
        "한국의 수도는?":   "서울입니다.",
        "1+1은?":          "3입니다.",   # 의도적 오답
    }
    return answers.get(question, "잘 모르겠습니다.")

qa_agent("한국의 수도는?", ground_truth="서울")    # accuracy_score ≈ 0.9
qa_agent("1+1은?",         ground_truth="2")       # accuracy_score ≈ 0.1
```

`AccuracyEvaluator`는 TokenF1(40%)·Jaccard(30%)·LCS(20%)·Char Levenshtein(10%) 가중 합산으로 accuracy_score를 계산한다.

**섹션 3 — 할루시네이션 탐지 (`HallucinationDetector`)**

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 3
from agent_evaluator import create_taskresult

# 수치 불일치 탐지 케이스
result = create_taskresult(
    task_id="hall_001",
    question="아인슈타인의 출생 연도는?",
    response="아인슈타인은 1865년 미국 뉴욕에서 태어났습니다.",  # 연도·장소 모두 오류
    ground_truth="1879년, 독일 울름",
    context="알베르트 아인슈타인은 1879년 독일 울름에서 태어난 물리학자입니다.",
    execution_time=1.2,
    task_type="information_retrieval",   # ← 이 task_type이어야 할루시네이션 탐지 활성
    tokens_used={"input": 120, "output": 40, "total": 160},
)
monitor.record_task(result)
print(f"accuracy_score={result.accuracy_score:.2f}")  # 낮은 점수
```

`task_type="information_retrieval"` + `context` 필드가 있을 때 `enable_hallucination_detection=True`이면 HallucinationDetector가 자동 활성화된다.

**섹션 5 — 지연시간 분포 (`LatencyTracker`)**

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 5
import random

latencies = [random.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]  # 이상치 2개
for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"perf_{i:03d}", question="지연 테스트", response="완료",
        ground_truth="완료", execution_time=max(0.1, lat),
        task_type="qa", tokens_used={"input": 50, "output": 20, "total": 70},
    )
    monitor.record_task(result)

lat_stats = monitor.generate_report().to_dict().get("efficiency_metrics", {}).get("latency", {})
print(f"p95={float(lat_stats.get('p95', 0)):.2f}s")  # 이상치 2개로 급등
```

p95는 이상치 2개(8.5s, 12.0s)로 인해 정상 평균(~1.2s)보다 크게 올라간다. 소수의 느린 요청이 SLA에 미치는 영향을 측정하는 데 p95/p99가 중요한 이유다.

```bash
# Evaluator_Examples/ 디렉토리에서 실행
python 01_layer1_all_metrics.py

# 결과 대시보드 확인
agent-eval dashboard results/
```

**예제 구성**

| 섹션 | 내용 | 연관 지표 |
|------|------|----------|
| 섹션 1 | QA 정확도 (정답·오답 혼합 5건) | Accuracy (Token F1·Jaccard·LCS·Char) |
| 섹션 2 | 코드 & RAG 정확도 | Accuracy (AST 비교 / 컨텍스트 기반) |
| 섹션 3 | 할루시네이션 탐지 4건 | HallucinationDetector |
| 섹션 4 | 응답 품질 고·중·저 비교 | ResponseQualityEvaluator (5차원) |
| 섹션 5 | 지연시간 분포 시뮬레이션 | LatencyTracker (p50·p95·p99) |
| 섹션 6 | 토큰 경제성 & 비용 추정 | TokenEconomyTracker |
| 섹션 7 | TCR 목표값 비교 | TaskCompletionTracker |

**실행 결과 (v0.8.0 기준)**

```
=== 최종 리포트 ===
  총 태스크 : 54건
  평균 정확도: 59.82%
  평균 지연  : 1.41s  (p50=1.15s · p95=5.20s · p99=10.95s)
  TCR       : 43.1%  (목표: 85%)  ← 의도적 오답 포함으로 낮게 설정
  누적 토큰 : 4,523   예상 비용: $0.0265 USD

결과 저장 완료: results/01_layer1_all_metrics.json
```

**결과 파일에서 확인할 수 있는 값**

```bash
# TCR 확인
python -c "import json; d=json.load(open('results/01_layer1_all_metrics.json')); print(d['summary']['task_completion_rate'])"
# → 0.431

# P95 지연 확인
python -c "import json; d=json.load(open('results/01_layer1_all_metrics.json')); print(d['layer1']['latency']['p95_latency'])"
# → 5.2
```

---

## 3.10 Layer 1 지표 이론적 심화

> Appendix G, H와 연계되는 이론 섹션이다. 각 지표가 왜 이 방식으로 설계됐는지 이해하고 싶거나, 팀에 신뢰성을 설득해야 할 때 참고하라.

### 3.10.1 4가지 정확도 서브지표의 상호보완성

정확도를 단일 지표로 측정할 때의 맹점과 4지표 조합의 이점:

| 케이스 | Token F1 | Jaccard | LCS | Char Lev | 인간 판단 |
|--------|---------|---------|-----|---------|---------|
| 완전 일치 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 동의어 응답 ("서울" → "Seoul") | 0.0 | 0.0 | 0.0 | ~0.3 | 0.9 |
| 순서 반전 ("A→B→C" → "C→B→A") | 0.9 | 0.9 | 0.3 | ~0.6 | 0.4 |
| 장황한 정답 ("4" → "2+2=4입니다") | ~0.4 | ~0.2 | ~0.4 | ~0.2 | 0.7 |
| 철자 오류 ("서울" → "서욿") | 0.0 | 0.0 | 0.0 | ~0.8 | 0.9 |

**관찰**: 어떤 단일 지표도 모든 케이스에서 인간 판단을 정확히 추적하지 못한다. 4지표의 가중 평균은 이 불일치를 분산시킨다. 단, 동의어 응답 케이스는 모든 규칙 기반 지표가 낮게 평가한다 → LLM Judge 보완이 필요한 대표적 케이스다.

### 3.10.2 TCR vs 정확도: 무엇이 다른가

```
TCR(Task Completion Rate): "에이전트가 작업을 완료했는가?"
  → 이분적에서 연속적으로 확장된 완료 측정
  → 응답의 정확성이 아닌 태스크 실행 여부를 측정
  → 예: 10줄 코드를 생성했으면 TCR=1.0, 정확도는 그 코드의 품질

정확도(Accuracy): "응답이 정답에 얼마나 가까운가?"
  → ground_truth와의 텍스트 유사도 측정
  → TCR=1.0이어도 정확도가 낮을 수 있음 (응답했지만 틀림)

상호관계:
  TCR ↑, 정확도 ↑: 최선 (완료하고 정확)
  TCR ↑, 정확도 ↓: 위험 (응답은 했지만 틀린 내용)
  TCR ↓, 정확도 높음: 불완전 완료 (부분적 응답)
  TCR ↓, 정확도 ↓: 최악 (응답 자체가 부실)
```

CI/CD에서 TCR과 정확도를 동시에 게이팅해야 하는 이유가 여기에 있다. TCR 85% + 정확도 70% 조합은 "대부분 완료하되, 완료한 것은 7할 이상 정확해야 한다"는 이중 기준을 설정한다.

### 3.10.3 P95 지연시간이 P50보다 중요한 이유

```
정규분포 가정이 깨지는 지연시간 분포:

빈도 │
     │████
     │█████
     │██████
     │████████
     │███████████
     │████████████████
     │███████████████████████████████████████  ←  롱테일
     └─────────────────────────────────────────▶ 지연시간
          P50  P95   P99

에이전트 지연시간은 "롱테일 분포(long-tail distribution)"를 보인다.
- 대부분의 요청: 빠른 처리 (P50 기준)
- 소수의 요청: 외부 API 지연, 도구 재시도 등으로 극도로 느림

P50 기준으로 SLA를 설정하면:
  - P50 = 1.0초 → "50%의 사용자는 1초 이내 응답"
  - 하지만 P95 = 8.0초 → 5%의 사용자는 8초 이상 대기
  - 하루 1만 건이면 500건이 8초 이상 → 사용자 불만

P95 기준이 실제 사용자 경험의 95%를 커버하는 이유이다.
SLA 목표: P95 < 3초 (고객 서비스), P95 < 5초 (복잡한 에이전트)
```

### 3.10.4 Token F1이 단순 Recall보다 나은 이유 (v0.8.0 변경 배경)

v0.7.9 이전 버전에서는 토큰 중첩 지표로 **Recall**을 사용했다:
```
구버전: TokenOverlapRecall = |교집합| / |reference 크기|
```

이 방식의 문제점: 에이전트가 정답과 관계없는 토큰을 대량 추가해도 점수가 올라가지 않지만, 모든 정답 단어를 포함하면 1.0이 된다.

```
예시:
  정답: "서울"
  응답: "서울이고 그리고 또한 아울러 뿐만 아니라 대한민국의..."

  Recall = 1.0  (정답 "서울" 포함!)
  Token F1 = 2×(1/10)×1 / (1/10+1) ≈ 0.18  (장황함 패널티)
```

**F1(Precision×Recall의 조화평균)**은 이 문제를 해결한다. 불필요한 토큰을 추가하면 Precision이 내려가 F1이 낮아진다.

### 3.10.5 규칙 기반 환각 탐지의 한계와 실무 보완

`HallucinationDetector`의 규칙 기반 접근은 다음 케이스에서 한계를 가진다:

**오탐(False Positive) 원인**:
- 컨텍스트와 같은 의미의 다른 표현 ("2024년" vs "작년")
- 일반 상식 수준의 정보 (컨텍스트에 없지만 사실인 정보)
- 추론된 정보 (컨텍스트에서 논리적으로 도출되지만 명시 없음)

**미탐(False Negative) 원인**:
- 의미는 다르지만 단어는 같은 경우 (동음이의어)
- 숫자 전치 오류 ("1,234" → "1,324")

**실무 보완 전략**:
```
레벨 1 (빠른 스크리닝): HallucinationDetector — 모든 RAG 응답에 적용
레벨 2 (의심 케이스): LLM Judge (rag_mode=True) — hallucination_rate > 0.1 케이스
레벨 3 (고위험): 인간 검토 — faithfulness < 2.0 케이스

비용 비교 (1만 건/일):
  레벨 1만: $0/일
  레벨 1+2 (10% 적용): ~$10/일
  레벨 1+2 (100%): ~$100/일
  레벨 1+2+3 (1%): ~$10/일 + 인건비
```

---

> 📖 **더 깊이 알고 싶다면**
> - **Appendix G.1**: 정확도 지표의 역사 (BLEU, ROUGE, BERTScore)
> - **Appendix H.1~H.6**: 6개 지표 수식과 의사코드
> - **Appendix I.1**: 정확도 지표 간 상세 비교
> - **Appendix I.2**: 환각 탐지 방법 3종 비교
