# M2 — Layer 1 기반 지표 6종 심층 분석

> **Agent-Evaluator v0.7.5+** 기준  
> Layer 1 지표 6종은 외부 의존성 없이 자동으로 활성화된다.
> 각 지표의 측정 원리부터 실무 활용법까지 완전히 이해한다.

---

## 목차

1. [Layer 1 개요](#1-layer-1-개요)
2. [TCR (Task Completion Rate)](#2-tcr--task-completion-rate)
3. [Accuracy (정확도)](#3-accuracy--정확도)
4. [Response Quality (응답 품질)](#4-response-quality--응답-품질)
5. [Latency (지연시간)](#5-latency--지연시간)
6. [Token Economy (토큰 경제)](#6-token-economy--토큰-경제)
7. [Hallucination Detection (환각 탐지)](#7-hallucination-detection--환각-탐지)
8. [지표 조합 전략](#8-지표-조합-전략)

---

> **🗂 실습 파일**
>
> | 예제 파일 | 다루는 내용 |
> |---------|---------|
> | `Evaluator_Examples/01_layer1_all_metrics.py` | TCR · Accuracy(QA/코드/RAG) · 할루시네이션 탐지 · 응답 품질 5차원 · 지연시간 분포 · 토큰 경제성 |
>
> ```bash
> python 01_layer1_all_metrics.py
> ```
>
> **실행 결과 (v0.8.0 기준)**
>
> ```
> === 최종 리포트 ===
>   총 태스크 : 54건
>   평균 정확도: 59.82%
>   평균 지연  : 1.41s  (p50=1.15s · p95=5.20s · p99=10.95s)
>   TCR       : 43.1%  (목표: 85%)
>
> 결과 저장 완료: results/01_layer1_all_metrics.json
> ```
>
> 결과 파일: `results/01_layer1_all_metrics.json`  
> 대시보드: `agent-eval dashboard results/`

---

### 핵심 코드 예제

#### 예제 1 — QA 정확도 + `@agent_eval`

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 1
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # HallucinationDetector 활성화
)

@agent_eval(monitor, task_type="qa", task_id_prefix="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    answers = {
        "한국의 수도는?":   "서울입니다.",
        "물의 화학식은?":   "H2O입니다.",
        "1+1은?":          "3입니다.",   # 의도적 오답
    }
    return answers.get(question, "잘 모르겠습니다.")

qa_agent("한국의 수도는?", ground_truth="서울")
qa_agent("1+1은?",         ground_truth="2")   # 오답 → accuracy_score 낮음
```

- `enable_hallucination_detection=True`를 PerformanceMonitor에 설정하면 `information_retrieval` 태스크에서 HallucinationDetector가 자동 활성화된다
- `@agent_eval`은 함수 실행 시간(LatencyTracker), 토큰 수(TokenEconomyTracker), 정확도(AccuracyEvaluator), 완료율(TCR)을 모두 자동 기록한다
- 오답(`"3입니다."` vs ground_truth `"2"`)은 TokenF1·Jaccard·LCS 복합 계산으로 낮은 accuracy_score를 받는다

---

#### 예제 2 — 지연시간 분포 측정

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 5
import random
from agent_evaluator import create_taskresult

# 정규 분포에 이상치 추가 — 현실적 지연 패턴
latencies = [random.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]  # 이상치 2개
latencies = [max(0.1, lat) for lat in latencies]

for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"perf_{i:03d}",
        question="지연시간 테스트",
        response="응답 완료",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
        tokens_used={"input": 50, "output": 20, "total": 70},
    )
    monitor.record_task(result)

report = monitor.generate_report()
lat_stats = report.to_dict().get("efficiency_metrics", {}).get("latency", {})
print(f"p50={float(lat_stats.get('p50', 0)):.2f}s")
print(f"p95={float(lat_stats.get('p95', 0)):.2f}s")   # 이상치 2개로 급등
print(f"p99={float(lat_stats.get('p99', 0)):.2f}s")
```

- `create_taskresult()`는 `execution_time`을 LatencyTracker에 자동 전달한다. 별도 API 없이 단순히 결과 객체를 만들어 `record_task()`에 넘기면 된다
- `generate_report()`가 반환하는 보고서에서 `efficiency_metrics.latency`로 p50/p95/p99 백분위 지연시간을 확인한다
- 이상치 2개(8.5s, 12.0s)가 p95를 정상 범위(~2.0s)보다 크게 올리는 것을 확인할 수 있다 — 프로덕션에서 소수의 느린 요청이 p95에 미치는 영향을 이해하는 데 유용하다

---

#### 예제 3 — 토큰 비용 추정

```python
# 출처: Evaluator_Examples/01_layer1_all_metrics.py, 섹션 6
TOKEN_MODELS = [
    ("gpt-4o",      {"input": 800, "output": 200, "total": 1000, "model": "gpt-4o"}),
    ("claude-3",    {"input": 600, "output": 150, "total": 750,  "model": "claude-3-sonnet"}),
    ("gpt-4o-mini", {"input": 400, "output": 100, "total": 500,  "model": "gpt-4o-mini"}),
]

for model_name, tokens in TOKEN_MODELS:
    result = create_taskresult(
        task_id=f"tok_{model_name}",
        question="토큰 비용 테스트",
        response="응답 내용",
        ground_truth="응답",
        execution_time=1.5,
        task_type="qa",
        tokens_used=tokens,   # "model" 키로 모델별 단가 자동 적용
    )
    monitor.record_task(result)

tok_report = monitor.generate_report().to_dict()
tok_stats = tok_report.get("efficiency_metrics", {}).get("tokens", {})
print(f"누적 토큰: {int(tok_stats.get('total_tokens', 0)):,}")
cost = tok_stats.get("total_cost")
if cost:
    print(f"예상 비용: ${float(cost):.4f} USD")
```

- `tokens_used` 딕셔너리에 `"model"` 키를 포함하면 TokenEconomyTracker가 모델별 단가를 자동으로 적용해 비용을 추정한다
- gpt-4o, claude-3-sonnet, gpt-4o-mini 등 주요 모델의 단가가 내장되어 있어 별도 설정 없이 비용 계산이 된다
- `total_cost`가 있으면 `efficiency_metrics.tokens.total_cost`로 접근한다

---

## 1. Layer 1 개요

### 1.1 2개 레이어의 구조

Agent-Evaluator의 16개 네이티브 지표는 2개 레이어로 나뉜다:

| 레이어 | 특징 | 지표 수 | 활성화 조건 |
|---|---|---|---|
| **Layer 1** | 외부 의존성 없음, 항상 자동 활성 | 6개 | `@agent_eval` 적용만으로 충분 |
| **Layer 2-A** | 외부 의존성 없음, 데이터 있을 때 자동 활성 | 5개 | `tool_calls`·`chain_steps`·`agent_interactions` 공급 시 자동 |
| **Layer 2-B** | 외부 의존성 없음, opt-in | 5개 (보안) | `security=SecurityConfig()` 또는 `enable_security_metrics=True` |

> **Layer 1과 Layer 2의 핵심 차이**: Layer 1은 모든 TaskResult에서 항상 계산된다. Layer 2는 TaskResult에 특정 필드(`tool_calls` 등)가 있어야 의미있는 값이 산출된다. 데코레이터의 `framework=` 파라미터나 `EvalMetadata`로 해당 필드를 자동/수동 공급할 수 있다.

### 1.2 Layer 1의 6가지 지표와 데코레이터 연결

| 지표 | 트래커 클래스 | 기본 활성 | 핵심 질문 | 데코레이터가 공급하는 필드 |
|---|---|---|---|---|
| TCR | `TaskCompletionTracker` | ✅ 항상 | "태스크가 얼마나 완료되는가?" | `success`, `completion_score` (예외 유무로 자동) |
| Accuracy | `AccuracyEvaluator` | ✅ 항상 | "정답과 얼마나 가까운가?" | `accuracy_score` (`ground_truth` 파라미터로 자동 계산) |
| Quality | `ResponseQualityEvaluator` | ✅ 항상 | "응답의 품질이 좋은가?" | `response`, `question` (함수 인자 자동 매핑) |
| Latency | `LatencyTracker` | ✅ 항상 | "얼마나 빠른가?" | `execution_time` (`time.perf_counter()` 자동 측정) |
| Token Economy | `TokenEconomyTracker` | ✅ 항상 | "비용 효율적인가?" | `tokens_used` (`framework=` 어댑터 자동 추출) |
| Hallucination | `HallucinationDetector` | ❌ opt-in | "사실과 다른 말을 하는가?" | `rag_mode=True` 또는 `enable_hallucination_detection=True` |

> **왜 Hallucination만 opt-in인가?**  
> 환각 탐지는 NLP 연산이 무거워 성능에 영향을 준다. 나머지 5개는 단순 통계 계산으로 오버헤드가 무시할 수준이다.

**핵심 인사이트**: Layer 1은 `@agent_eval(monitor, task_type="qa")` 한 줄만으로 6개 지표 중 5개가 자동 활성된다. Hallucination은 `rag_mode=True`를 추가하면 된다.

### 1.3 Layer 1 활성화 방법 — 아무것도 하지 않아도 된다

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa          # QuickEval 단축 데코레이터 — task_type="qa" 자동 설정
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 모든 Layer 1 지표가 자동 측정됨
my_agent("한국의 수도는?", ground_truth="서울")

report = eval.monitor.generate_report()
print(report.to_dict())
# {
#   "tcr": 1.0,
#   "full_success_rate": 1.0,
#   "overall_accuracy": 0.87,
#   "quality_score": 4.2,
#   "latency_p95": 1.23,
#   "total_tokens": 45,
#   ...
# }
```

내부적으로 일어나는 일:
1. `@eval.qa` → `@agent_eval(monitor, task_type="qa")` 로 확장
2. `my_agent()` 호출 시 데코레이터가 실행시간·정확도·성공여부를 측정해 `TaskResult` 생성
3. `monitor.record_task(task)` → Layer 1 트래커 6개에 자동 분배
4. `eval.save()` 또는 `eval.monitor.save_to_file()` 호출 시 JSON + HTML 저장

---

## 2. TCR (Task Completion Rate)

### 2.1 무엇을 측정하는가

TCR은 에이전트가 **태스크를 얼마나 성공적으로 완료**하는지 측정하는 핵심 KPI다.

단순히 "성공/실패" 이분법이 아니라 **3단계 완료 수준**으로 구분한다:

| 완료 수준 | 기준 | 예시 |
|---|---|---|
| **완전 성공 (Full Success)** | completion_score ≥ 0.8 | 정확한 답변, 정상 완료 |
| **부분 성공 (Partial Success)** | 0.3 ≤ completion_score < 0.8 | 일부 불완전한 답변 |
| **실패 (Failure)** | completion_score < 0.3 | 오류, 빈 응답, 예외 |

### 2.2 어떻게 계산되는가

```
TCR = (완전성공 수 + 0.5 × 부분성공 수) / 전체 태스크 수
```

예시:
- 전체 100태스크: 완전성공 70, 부분성공 20, 실패 10
- TCR = (70 + 0.5×20) / 100 = **80%**

#### 데코레이터가 completion_score를 자동으로 설정하는 방식

```python
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)  # 정상 반환 → completion_score = 1.0 (Full Success)

@agent_eval(monitor, task_type="qa")
def buggy_agent(question: str, ground_truth: str = "") -> str:
    raise ValueError("API 오류")  # 예외 → completion_score = 0.0 (Failure)

@agent_eval(monitor, task_type="qa")
def partial_agent(question: str, ground_truth: str = "") -> tuple:
    from agent_evaluator import EvalMetadata
    response = llm.invoke(question)
    # 직접 partial success 설정
    return response, EvalMetadata(accuracy_score=0.5)  # completion_score가 accuracy를 반영
```

#### create_taskresult()로 직접 제어할 때

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.23,
    task_type="qa",
    # completion_score를 직접 지정 가능
    # 지정 안 하면 response + ground_truth로 자동 계산
)
```

#### task_type별 구조적 완료 판정 (v0.8.0+)

ground_truth 없는 환경에서도 task_type을 기반으로 완료 여부를 구조적으로 판정한다.

| task_type | 판정 기준 | completion_score |
|-----------|----------|-----------------|
| `code_generation` / `coding` | Python AST 파싱 성공 | 1.0 (유효 코드) / 길이 기반 fallback |
| `tool_use` | `tool_calls` 비어 있지 않음 | 1.0 / 0.6 (도구 미사용) |
| 기타 | 응답 길이 ≥ 10자 | 1.0 |

```python
# code_generation: AST 성공 → completion_score = 1.0 (ground_truth 불필요)
result = create_taskresult(
    task_id="code_1",
    question="두 수를 더하는 함수",
    response="def add(a, b):\n    return a + b",
    execution_time=1.0,
    task_type="code_generation",
)
# completion_score = 1.0 → TCR 신뢰도 향상

# tool_use: 도구 미사용 → completion_score = 0.6 (부분 완료)
result = create_taskresult(
    task_id="tool_1",
    question="현재 서울 날씨",
    response="맑습니다",
    execution_time=1.0,
    task_type="tool_use",
    tool_calls=[],   # 도구 미사용
)
# completion_score = 0.6 (텍스트 반환했지만 도구를 써야 하는 태스크)
```

### 2.3 어떤 의미가 있는가

TCR은 프로덕션 배포 준비도를 나타내는 가장 직관적인 지표다.

**업계 벤치마크:**

| TCR | 상태 | 행동 |
|---|---|---|
| ≥ 90% | 🟢 프로덕션 준비 완료 | 배포 가능 |
| 80~90% | 🟡 개선 필요 | 실패 케이스 분석 필요 |
| 70~80% | 🟠 위험 | 주요 버그 수정 필요 |
| < 70% | 🔴 배포 불가 | 근본적 재설계 검토 |

### 2.4 어떻게 활성화하는가

자동 활성화된다. 별도 설정 불필요.

```python
# 자동 활성화 — 아무것도 하지 않아도 됨
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 2.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# TaskCompletionTracker 출력 필드
print(d["tcr"])                  # 0.87  (87%)
print(d["full_success_rate"])    # 0.75  (75%)
print(d["partial_success_rate"]) # 0.24  (24%)
print(d["failure_rate"])         # 0.01  (1%)
print(d["total_tasks"])          # 100   (전체 태스크 수)
```

### 2.6 실무 활용법

#### CI/CD 게이팅

```python
# GitHub Actions / Jenkins에서 품질 게이트 역할
eval.gate(tcr=85)  # TCR 85% 미달 시 sys.exit(1) → 빌드 실패
```

`.github/workflows/eval.yml` 예시:
```yaml
- name: Run evaluation
  run: python evaluate.py

- name: Quality gate
  run: python -c "
  from agent_evaluator import QuickEval
  eval = QuickEval.from_config('eval_config.json')
  eval.replay('results/evaluation.json')
  eval.gate(tcr=85, accuracy=70)
  "
```

#### 실패 원인 분석

```python
# 실패한 태스크만 필터링
failed_tasks = [
    t for t in monitor.tasks
    if t.completion_score < 0.3
]

# 공통 오류 패턴 찾기
from collections import Counter
error_types = Counter(
    e.split(":")[0]           # 오류 유형만 추출
    for t in failed_tasks
    for e in t.errors
)
print(error_types.most_common(5))
# [("ConnectionError", 12), ("TimeoutError", 5), ("ValueError", 3)]
```

---

## 3. Accuracy (정확도)

### 3.1 무엇을 측정하는가

Accuracy는 에이전트 응답이 **정답과 얼마나 가까운지** 측정한다.

단순 문자열 매칭이 아니라 **4가지 유사도 지표를 가중 합산**한다. 각 방법이 서로 다른 유사성의 측면을 포착하기 때문에 하나의 방법보다 훨씬 강건하다.

### 3.2 어떻게 계산되는가

#### 4-way Weighted Scoring

```
accuracy = 0.4 × token_f1 + 0.3 × jaccard + 0.2 × lcs_ratio + 0.1 × char_similarity
```

| 구성 요소 | 가중치 | 알고리즘 | 특징 |
|---|---|---|---|
| Token Overlap F1 | 40% | 토큰화 후 F1 계산 | 핵심 정보 포함 여부 |
| Jaccard Similarity | 30% | 집합 교집합/합집합 | 단어 집합 유사도 |
| LCS Ratio | 20% | 최장 공통 부분 수열 | 순서 보존 유사도 |
| Char Similarity | 10% | Levenshtein 거리 기반 | 오탈자/변형 허용, 문자 순서 반영 |

#### Token Overlap F1 상세

```python
def token_f1(response: str, ground_truth: str) -> float:
    # 1. 토큰화 (소문자, 구두점 제거)
    pred_tokens = set(response.lower().split())
    true_tokens = set(ground_truth.lower().split())
    
    # 2. Precision / Recall / F1
    common = pred_tokens & true_tokens
    precision = len(common) / len(pred_tokens) if pred_tokens else 0
    recall = len(common) / len(true_tokens) if true_tokens else 0
    
    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)
    return f1

# 예시
response = "대한민국의 수도는 서울입니다"
ground_truth = "서울"

# pred: {"대한민국의", "수도는", "서울입니다"}
# true: {"서울"}
# common: {} (stem이 다름)
# → LCS나 Char Similarity가 유사성을 보완
```

#### Jaccard Similarity 상세

```python
def jaccard(response: str, ground_truth: str) -> float:
    pred_set = set(response.lower().split())
    true_set = set(ground_truth.lower().split())
    
    intersection = pred_set & true_set
    union = pred_set | true_set
    
    return len(intersection) / len(union) if union else 0.0
```

#### LCS Ratio 상세

```python
def lcs_ratio(response: str, ground_truth: str) -> float:
    # 동적 프로그래밍으로 LCS 계산
    m, n = len(response), len(ground_truth)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if response[i-1] == ground_truth[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    lcs_len = dp[m][n]
    return lcs_len / max(m, n) if max(m, n) > 0 else 0.0
```

#### Char Similarity 상세 (Levenshtein 기반, v0.8.0+)

```python
def char_similarity(s1: str, s2: str) -> float:
    """Levenshtein 거리 기반 — 문자 순서 반영"""
    if s1 == s2:
        return 1.0
    m, n = len(s1), len(s2)
    if m == 0 or n == 0:
        return 0.0
    # 공간 최적화 Levenshtein (O(min(m,n)) 공간)
    if m > n:
        s1, s2, m, n = s2, s1, n, m
    prev_row = list(range(n + 1))
    for i in range(1, m + 1):
        curr_row = [i]
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            curr_row.append(min(prev_row[j]+1, curr_row[j-1]+1, prev_row[j-1]+cost))
        prev_row = curr_row
    return max(0.0, 1.0 - prev_row[n] / max(m, n))

# 예시 — 문자 순서가 중요함
char_similarity("abc", "abc")   # 1.0
char_similarity("abc", "cba")   # 0.33  ← v0.8.0 이전 집합 방식: 1.0 (오판)
char_similarity("서울시", "서울")  # 0.80  ← 어절 변형 허용
```

> **v0.8.0 변경**: 이전 버전의 집합 기반(`set(s1) & set(s2)`) 방식은 문자 순서를 무시했다. Levenshtein으로 교체하여 "abc"와 "cba"가 다른 점수를 받도록 개선.

#### 코드 생성 특수 처리

`task_type="code_generation"`일 때는 **AST 비교**를 우선 시도한다:

```python
def code_accuracy(response: str, ground_truth: str) -> float:
    try:
        # 1단계: AST 구조 비교 (완전 동치)
        import ast
        tree_response = ast.parse(response.strip())
        tree_truth = ast.parse(ground_truth.strip())
        
        if ast.dump(tree_response) == ast.dump(tree_truth):
            return 1.0
        
        # 구조가 다르면 노드 수준 유사도 계산
        nodes_r = set(ast.dump(n) for n in ast.walk(tree_response))
        nodes_t = set(ast.dump(n) for n in ast.walk(tree_truth))
        return len(nodes_r & nodes_t) / len(nodes_r | nodes_t)
        
    except SyntaxError:
        # 2단계: 정규화 후 문자열 비교 (공백, 주석 제거)
        normalized_r = normalize_code(response)
        normalized_t = normalize_code(ground_truth)
        return lcs_ratio(normalized_r, normalized_t)
```

### 3.3 어떤 의미가 있는가

**정확도 등급 가이드:**

| 정확도 범위 | 등급 | 해석 |
|---|---|---|
| 0.90 ~ 1.00 | Excellent | 정답과 거의 동일 |
| 0.80 ~ 0.90 | Good | 핵심 정보 포함, 표현 차이 있음 |
| 0.70 ~ 0.80 | Acceptable | 기본 요구 충족 |
| 0.50 ~ 0.70 | Poor | 일부 관련 정보 포함 |
| 0.00 ~ 0.50 | Fail | 정답과 무관하거나 잘못된 응답 |

### 3.4 어떻게 활성화하는가

`ground_truth`가 있으면 자동 계산된다. `ground_truth`가 비어 있으면 accuracy는 `None`이 된다.

```python
# ground_truth 있음 → accuracy 자동 계산
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

agent("한국의 수도는?", ground_truth="서울")    # accuracy 계산됨
agent("날씨 어때요?")                           # ground_truth 없음 → accuracy = None
```

#### 커스텀 정확도 함수

도메인 특화 평가가 필요하면 `score_fn`을 사용한다:

```python
# 의료 도메인: ICD-10 코드 정확도
def icd_accuracy(response: str, ground_truth: str) -> float:
    import re
    # ICD 코드 추출 (예: J18.9, K21.0)
    pred_codes = set(re.findall(r'[A-Z]\d{2}\.\d', response))
    true_codes = set(re.findall(r'[A-Z]\d{2}\.\d', ground_truth))
    
    if not true_codes:
        return 0.0
    return len(pred_codes & true_codes) / len(true_codes)

@agent_eval(monitor, task_type="qa", score_fn=icd_accuracy)
def medical_agent(question: str, ground_truth: str = "") -> str:
    return medical_llm.invoke(question)

# 수학 도메인: 수치 정확도
def numeric_accuracy(response: str, ground_truth: str) -> float:
    import re
    def extract_number(text):
        nums = re.findall(r'-?\d+\.?\d*', text)
        return float(nums[0]) if nums else None
    
    pred = extract_number(response)
    true = extract_number(ground_truth)
    
    if pred is None or true is None:
        return 0.0
    if true == 0:
        return 1.0 if pred == 0 else 0.0
    
    relative_error = abs(pred - true) / abs(true)
    return max(0.0, 1.0 - relative_error)
```

### 3.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# AccuracyEvaluator 출력 필드
print(d["overall_accuracy"])     # 0.82  (평균 정확도)
print(d["median_accuracy"])      # 0.85  (중앙값 — 이상치에 강건)
print(d["std_accuracy"])         # 0.12  (표준편차 — 일관성 지표)

# task_type별 정확도 분석
tasks_by_type = {}
for task in monitor.tasks:
    t = task.task_type.value
    if t not in tasks_by_type:
        tasks_by_type[t] = []
    if task.accuracy_score is not None:
        tasks_by_type[t].append(task.accuracy_score)

for task_type, scores in tasks_by_type.items():
    print(f"{task_type}: {sum(scores)/len(scores):.2f}")
```

### 3.6 실무 활용법

#### 약점 태스크 유형 찾기

```python
import pandas as pd

df = eval.export_to_dataframe()

# task_type별 평균 정확도
accuracy_by_type = df.groupby("task_type")["accuracy_score"].agg(["mean", "std", "count"])
print(accuracy_by_type.sort_values("mean"))

# 출력 예시:
# task_type        mean    std   count
# code_generation  0.62   0.18    25
# reasoning        0.71   0.15    30
# qa               0.84   0.11    45
```

코드 생성 정확도가 낮다면 → 프롬프트에 코드 형식 지시 추가, few-shot 예제 보강.

#### 정확도와 레이턴시 트레이드오프 분석

```python
# 정확도가 낮은데 레이턴시도 느린 태스크 → 가장 비효율적
high_cost_low_quality = df[
    (df["accuracy_score"] < 0.7) &
    (df["execution_time"] > 3.0)
]
print(f"비효율 태스크 수: {len(high_cost_low_quality)}")
print(high_cost_low_quality[["question", "accuracy_score", "execution_time"]].head())
```

---

## 4. Response Quality (응답 품질)

### 4.1 무엇을 측정하는가

Accuracy가 "정답과 얼마나 같은가"를 측정한다면, Quality는 **응답 자체의 품질**을 5가지 차원으로 평가한다.

Ground truth 없이도 측정할 수 있다는 점이 핵심 장점이다. 실시간 프로덕션 환경처럼 정답을 알 수 없는 상황에서도 품질을 모니터링할 수 있다.

### 4.2 어떻게 계산되는가

#### 5차원 품질 평가

| 차원 | 측정 내용 | 알고리즘 |
|---|---|---|
| **Relevance** (관련성) | 응답이 질문에 관련된가 | 질문-응답 간 토큰 오버랩 |
| **Completeness** (완결성) | 질문의 모든 측면을 다루는가 | 질문 키워드 커버리지 |
| **Clarity** (명확성) | 이해하기 쉬운가 | 문장 복잡도, 모호어 탐지 |
| **Conciseness** (간결성) | 불필요한 장황함이 없는가 | 응답 길이 대비 정보 밀도 |
| **Coherence** (일관성) | 논리적 흐름이 자연스러운가 | 문단 간 연결성 |

각 차원은 0.0~1.0으로 평가된다.

#### 종합 점수 계산

```
total_score = relevance + completeness + clarity + conciseness + coherence
# 범위: 0.0 ~ 5.0
```

#### 등급 변환

| total_score | 등급 | 의미 |
|---|---|---|
| 4.5 ~ 5.0 | A | 탁월한 품질 |
| 4.0 ~ 4.5 | B | 양호한 품질 |
| 3.0 ~ 4.0 | C | 보통 품질 |
| 2.0 ~ 3.0 | D | 낮은 품질 |
| 0.0 ~ 2.0 | F | 매우 낮은 품질 |

#### 내부 알고리즘 예시 — Relevance

```python
def score_relevance(question: str, response: str) -> float:
    """응답이 질문에 관련된 정도"""
    if not question or not response:
        return 0.0
    
    # 질문 핵심 토큰 추출 (불용어 제거)
    stopwords = {"은", "는", "이", "가", "을", "를", "의", "에", "서", "로"}
    q_tokens = set(question.split()) - stopwords
    r_tokens = set(response.split())
    
    if not q_tokens:
        return 0.5  # 질문이 모호한 경우 중립 점수
    
    overlap = q_tokens & r_tokens
    return len(overlap) / len(q_tokens)
```

### 4.3 어떤 의미가 있는가

**각 차원의 실무적 의미:**

- **Relevance 낮음** → 에이전트가 질문을 오해함. 프롬프트에 질문 반복 지시 추가 필요.
- **Completeness 낮음** → 일부 측면만 답함. 구조화된 출력 형식 지시 필요.
- **Clarity 낮음** → 전문 용어 과다, 문장 구조 복잡. 독자 수준 명시 필요.
- **Conciseness 낮음** → 장황한 응답. "간결하게 3문장 이내로" 지시 추가.
- **Coherence 낮음** → 논리적 흐름 부재. Chain-of-thought 프롬프팅 적용 고려.

### 4.4 어떻게 활성화하는가

자동 활성화. question과 response가 모두 있으면 자동으로 계산된다.

```python
# 자동 활성화 — 별도 설정 불필요
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 4.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# ResponseQualityEvaluator 출력 필드
print(d["quality_score"])          # 3.8   (평균 종합 점수 / 5.0)
print(d["quality_grade"])          # "B"   (등급)
print(d["dimension_scores"])       # 차원별 평균 점수
# {
#   "relevance": 0.85,
#   "completeness": 0.72,
#   "clarity": 0.78,
#   "conciseness": 0.80,
#   "coherence": 0.68,
# }
```

### 4.6 실무 활용법

#### 차원별 약점 진단

```python
d = report.to_dict()
dims = d.get("dimension_scores", {})

# 가장 낮은 차원 찾기
weakest = min(dims.items(), key=lambda x: x[1])
print(f"가장 취약한 품질 차원: {weakest[0]} ({weakest[1]:.2f})")

# 개선 행동 매핑
actions = {
    "relevance": "프롬프트에 질문 초점 재확인 지시 추가",
    "completeness": "구조화된 응답 형식 (예: 결론, 이유, 예시) 지시",
    "clarity": "독자 수준 명시, 전문 용어 정의 요청",
    "conciseness": "응답 길이 제한 (예: '3문장 이내') 지시",
    "coherence": "Chain-of-thought 프롬프팅 적용",
}
print(f"권장 행동: {actions.get(weakest[0], '프롬프트 검토')}")
```

---

## 5. Latency (지연시간)

### 5.1 무엇을 측정하는가

Latency는 에이전트의 **응답 속도**를 측정한다. 단순 평균이 아니라 **백분위수(Percentile) 통계**를 제공한다.

왜 백분위수인가? 평균은 이상치에 민감하다. P95(95번째 백분위수)는 "상위 5%의 느린 요청이 얼마나 느린가"를 나타내며 사용자 경험 SLA 설정에 더 적합하다.

### 5.2 어떻게 계산되는가

#### 자동 측정

데코레이터가 함수 실행 전후 타임스탬프를 자동으로 기록한다:

```python
# 내부 동작 (사용자는 신경 쓸 필요 없음)
import time

def measure_execution_time(fn, args, kwargs):
    start = time.perf_counter()          # 고정밀 타이머
    try:
        result = fn(*args, **kwargs)
    finally:
        elapsed = time.perf_counter() - start
    return result, elapsed
```

#### TTFT (Time-To-First-Token)

스트리밍 에이전트에서 첫 번째 토큰이 반환되는 시간. 사용자가 "응답이 시작되었다"고 느끼는 시점이다.

```python
# 제너레이터 함수에서 TTFT 자동 측정
@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = "") -> str:
    for chunk in llm.stream(question):
        yield chunk  # ← 첫 번째 yield 시점이 TTFT로 자동 기록

# 비동기 제너레이터도 동일하게 동작
@agent_eval(monitor, task_type="qa")
async def async_streaming_agent(question: str, ground_truth: str = "") -> str:
    async for chunk in llm.astream(question):
        yield chunk
```

#### 백분위수 계산

```python
import numpy as np

def compute_percentile_stats(latencies: list) -> dict:
    arr = np.array(latencies)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p50": float(np.percentile(arr, 50)),   # 중앙값
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),   # SLA 기준으로 주로 사용
        "p99": float(np.percentile(arr, 99)),   # 최악의 경우 기준
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }
```

### 5.3 어떤 의미가 있는가

**SLA 기준 가이드:**

| 레이턴시 | 사용자 경험 | 권장 행동 |
|---|---|---|
| P95 < 1초 | 🟢 즉각 응답 | 유지 |
| P95 1~3초 | 🟡 약간의 대기 | 목표 수준 |
| P95 3~5초 | 🟠 눈에 띄는 지연 | 최적화 필요 |
| P95 > 5초 | 🔴 사용자 이탈 위험 | 긴급 개선 |

#### TTFT의 중요성

전체 응답이 5초 걸려도 첫 토큰이 0.5초 내에 도착하면 사용자는 훨씬 덜 답답함을 느낀다. 스트리밍 UX 설계에서 TTFT가 전체 레이턴시보다 중요한 이유다.

| TTFT | 사용자 인식 |
|---|---|
| < 0.5초 | 즉각 반응 |
| 0.5 ~ 1초 | 자연스러운 응답 시작 |
| 1 ~ 3초 | 약간 느림 |
| > 3초 | "응답하고 있나?" |

### 5.4 어떻게 활성화하는가

자동 활성화. 모든 데코레이터가 자동으로 `execution_time`을 측정한다.

TTFT는 제너레이터 함수에서 자동으로 측정되며, `eval_context`의 `chunk_step()`을 통해서도 수동으로 기록할 수 있다.

### 5.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# LatencyTracker 출력 필드
latency_stats = d.get("latency_stats", {})
print(f"평균 레이턴시: {latency_stats['mean']:.2f}초")
print(f"P50 (중앙값): {latency_stats['p50']:.2f}초")
print(f"P95:          {latency_stats['p95']:.2f}초")
print(f"P99:          {latency_stats['p99']:.2f}초")
print(f"최대:          {latency_stats['max']:.2f}초")

# TTFT 통계 (스트리밍 에이전트만)
ttft_stats = d.get("ttft_stats", {})
if ttft_stats:
    print(f"TTFT 평균: {ttft_stats['mean']:.3f}초")
    print(f"TTFT P95: {ttft_stats['p95']:.3f}초")
```

#### task_type 필터링

```python
# 특정 task_type의 레이턴시만 조회
tracker = monitor._latency_tracker
qa_stats = tracker.get_ttft_stats(task_type="qa")
code_stats = tracker.get_ttft_stats(task_type="code_generation")
```

### 5.6 실무 활용법

#### SLA 모니터링

```python
# P95가 3초를 초과하면 알림
latency_alert = AlertRuleBuilder.when_latency_above(
    threshold=3.0,
    handler=lambda msg, tr: send_pagerduty_alert(msg),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[latency_alert])
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

#### 레이턴시 분포 시각화

```python
import pandas as pd
import matplotlib.pyplot as plt

df = eval.export_to_dataframe()

# 레이턴시 분포 히스토그램
plt.figure(figsize=(10, 4))
plt.hist(df["execution_time"], bins=50, edgecolor="black")
plt.axvline(df["execution_time"].quantile(0.95), color="red", label="P95")
plt.axvline(df["execution_time"].quantile(0.50), color="orange", label="P50")
plt.xlabel("Latency (seconds)")
plt.ylabel("Count")
plt.title("Response Latency Distribution")
plt.legend()
plt.savefig("latency_distribution.png")
```

#### CI/CD 게이팅

```python
# P95 레이턴시가 3초 이내여야 배포 허용
eval.gate(p95_latency=3.0)
```

---

## 6. Token Economy (토큰 경제)

### 6.1 무엇을 측정하는가

Token Economy는 에이전트의 **토큰 사용량과 비용**을 추적한다.

AI 에이전트는 LLM API를 호출할 때마다 토큰을 소비하고 비용이 발생한다. 이를 측정하지 않으면 월말에 예상치 못한 청구서를 받게 된다.

### 6.2 어떻게 계산되는가

#### 토큰 자동 추출

`framework` 어댑터를 통해 각 SDK의 응답 객체에서 토큰 정보를 자동 추출한다:

```python
# OpenAI
response.usage.prompt_tokens      # → input_tokens
response.usage.completion_tokens  # → output_tokens
response.usage.total_tokens       # → total_tokens

# Anthropic
response.usage.input_tokens       # → input_tokens
response.usage.output_tokens      # → output_tokens
# 캐시 토큰 (SDK ≥0.29)
response.usage.cache_creation_input_tokens
response.usage.cache_read_input_tokens

# LangChain
message.usage_metadata["input_tokens"]
message.usage_metadata["output_tokens"]
```

#### 비용 계산

```python
# 내부 가격 테이블 예시 (토큰 1000개당 USD)
PRICE_MAP = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-haiku-3-5": {"input": 0.0008, "output": 0.004},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICE_MAP.get(model, {"input": 0.001, "output": 0.002})
    input_cost = (input_tokens / 1000) * prices["input"]
    output_cost = (output_tokens / 1000) * prices["output"]
    return input_cost + output_cost
```

#### 월간 비용 추정

```python
def estimate_monthly_cost(
    total_cost_usd: float,
    total_tasks: int,
    daily_tasks: int,
) -> float:
    cost_per_task = total_cost_usd / total_tasks if total_tasks > 0 else 0
    return cost_per_task * daily_tasks * 30
```

### 6.3 어떤 의미가 있는가

**비용 효율성 지표:**

| 지표 | 의미 | 최적화 방향 |
|---|---|---|
| `avg_cost_per_task` | 태스크당 평균 비용 | 낮을수록 좋음 |
| `input/output 비율` | 입출력 토큰 비율 | 불필요한 컨텍스트 제거 |
| `estimated_monthly_cost` | 월 예상 비용 | 예산 계획 기준 |
| `cost_per_1k_tasks` | 1000 태스크당 비용 | 스케일 계획 기준 |

**실제 비용 시나리오:**

```
GPT-4o-mini로 일 1000건 처리:
- 평균 입력: 500토큰, 출력: 200토큰
- 태스크당 비용: (500/1000)×$0.00015 + (200/1000)×$0.0006 = $0.000195
- 일 비용: $0.195
- 월 비용: ~$5.85

GPT-4o로 동일 처리:
- 태스크당 비용: (500/1000)×$0.005 + (200/1000)×$0.015 = $0.0055
- 일 비용: $5.50
- 월 비용: ~$165

→ 28배 비용 차이. 정확도 차이가 허용 가능하다면 소형 모델로 전환이 유리.
```

### 6.4 어떻게 활성화하는가

자동 활성화. `framework` 파라미터를 지정하면 토큰 정보가 자동 추출된다.

```python
# framework 지정 → 토큰 자동 추출
@agent_eval(monitor, task_type="qa", framework="openai")
def agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # 응답 객체 반환
```

`framework` 없이도 `EvalMetadata`로 수동 주입 가능:

```python
@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = llm.invoke(question)
    return response["text"], EvalMetadata(tokens_used=response["token_count"])
```

### 6.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# TokenEconomyTracker 출력 필드
print(d["total_tokens"])              # 15420   (전체 토큰 합계)
print(d["total_cost_usd"])            # 0.0045  (전체 비용 USD)
print(d["avg_cost_per_task"])         # 0.000045 (태스크당 평균 비용)
print(d["estimated_monthly_cost"])    # 1.35    (월간 예상 비용 USD)

# 프레임워크별 비용 분석
tracker = monitor._token_economy_tracker
breakdown = tracker.get_cost_breakdown_by_framework()
# {
#   "openai": {"total_tokens": 10000, "total_cost_usd": 0.003},
#   "anthropic": {"total_tokens": 5420, "total_cost_usd": 0.0015},
# }
```

### 6.6 실무 활용법

#### 예산 계획

```python
d = report.to_dict()
monthly_est = d.get("estimated_monthly_cost", 0)
print(f"예상 월 비용: ${monthly_est:.2f}")

# 목표 비용으로 역산
target_monthly = 100.0  # $100/월 예산
current_daily_tasks = 500
max_affordable_tasks = (target_monthly / monthly_est) * current_daily_tasks
print(f"$100 예산으로 처리 가능한 일 태스크 수: {max_affordable_tasks:.0f}건")
```

#### 모델 교체 비용/품질 트레이드오프

```python
# 두 모델 평가 비교
eval_gpt4 = QuickEval("results/gpt4/")
eval_mini = QuickEval("results/mini/")

# 각각 평가 실행 후
comparison = eval_gpt4.compare(eval_mini)
# {
#   "accuracy_delta": -0.05,     # mini가 5% 낮음
#   "cost_delta": -0.035,        # mini가 $0.035 더 저렴 (태스크당)
#   "latency_delta": -0.8,       # mini가 0.8초 빠름
# }

# 비용 절감 대비 품질 저하 수용 가능 여부 판단
if abs(comparison["accuracy_delta"]) < 0.05:
    print("→ mini 모델로 전환 권장 (5% 이내 품질 저하로 비용 90% 절감)")
```

---

## 7. Hallucination Detection (환각 탐지)

### 7.1 무엇을 측정하는가

Hallucination(환각)은 에이전트가 **사실과 다른 내용을 자신 있게 말하는 현상**이다.

특히 RAG 시스템에서 중요하다: 검색된 문서(context)를 기반으로 답해야 하는데, 문서에 없는 내용을 창작해서 말하는 경우를 탐지한다.

### 7.2 어떻게 계산되는가

#### 알고리즘: 사실 일관성 점수

```python
def check_hallucination(response: str, context: str) -> dict:
    """응답의 주장이 컨텍스트에 의해 뒷받침되는지 확인"""
    
    # 1. 응답에서 주장(claim) 추출
    claims = extract_claims(response)
    # → ["한국의 수도는 서울이다", "서울 인구는 1000만명이다", ...]
    
    # 2. 각 주장이 컨텍스트에 있는지 확인
    supported = 0
    unsupported_claims = []
    
    for claim in claims:
        if is_claim_supported(claim, context):
            supported += 1
        else:
            unsupported_claims.append(claim)
    
    # 3. 심각도 분류
    support_rate = supported / len(claims) if claims else 1.0
    hallucination_rate = 1.0 - support_rate
    
    severity = classify_severity(hallucination_rate)
    
    return {
        "hallucination_rate": hallucination_rate,
        "unsupported_claims": unsupported_claims,
        "severity": severity,
    }

def classify_severity(rate: float) -> str:
    if rate < 0.05:   return "low"
    if rate < 0.15:   return "medium"
    if rate < 0.30:   return "high"
    return "critical"
```

#### 심각도 분류 기준

| 심각도 | 환각률 | 의미 |
|---|---|---|
| low | < 5% | 거의 없음 — 프로덕션 안전 |
| medium | 5~15% | 일부 사실 오류 — 모니터링 필요 |
| high | 15~30% | 상당한 오류 — 개선 필요 |
| critical | > 30% | 신뢰 불가 — 즉시 조치 필요 |

### 7.3 어떤 의미가 있는가

환각 탐지는 **의료, 법률, 금융** 등 사실 정확도가 중요한 도메인에서 필수 지표다.

환각이 높다는 것은:
1. 에이전트가 컨텍스트를 무시하고 학습 데이터에서 답을 "창작"하고 있다
2. 프롬프트가 컨텍스트 기반 응답을 충분히 유도하지 못하고 있다
3. 검색된 문서의 품질이 낮아 관련 정보가 부족하다

### 7.4 어떻게 활성화하는가

기본적으로 비활성화. 3가지 방법으로 활성화한다:

```python
# 방법 1: rag_mode=True (RAG 평가 시 권장)
@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,          # context_arg + enable_hallucination_detection 자동 활성화
)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(f"Context: {context}\n\nQ: {question}")

# 방법 2: enable_hallucination_detection=True (이번 호출만)
@agent_eval(
    monitor,
    task_type="qa",
    enable_hallucination_detection=True,
    context_arg="context",   # 컨텍스트 인자 이름 지정 필수
)
def agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke(question)

# 방법 3: PerformanceMonitor 레벨 활성화 (모든 태스크)
monitor = PerformanceMonitor(
    "results/",
    enable_hallucination_detection=True,  # 전체 활성화
)

# QuickEval 팩토리 사용
eval = QuickEval.for_rag("results/")  # hallucination 기본 활성
```

### 7.5 결과를 어떻게 읽는가

```python
report = monitor.generate_report()
d = report.to_dict()

# HallucinationDetector 출력 필드
hallucination = d.get("hallucination", {})
print(f"환각률: {hallucination.get('rate', 0):.1%}")
print(f"미지원 주장 수: {hallucination.get('unsupported_claims_count', 0)}")

# 심각도 분포
by_severity = hallucination.get("by_severity", {})
print(f"low: {by_severity.get('low', 0)}건")
print(f"medium: {by_severity.get('medium', 0)}건")
print(f"high: {by_severity.get('high', 0)}건")
print(f"critical: {by_severity.get('critical', 0)}건")
```

### 7.6 실무 활용법

#### RAG 시스템 품질 목표

```python
# 환각률 5% 이하 목표 (프로덕션 기준)
eval = QuickEval.for_rag("results/")

@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = retriever.retrieve(question)
    context = "\n".join(docs)
    return llm.invoke(f"Based on: {context}\n\nQ: {question}")

# 평가 후 환각률 확인
eval.gate(hallucination=5)  # 5% 초과 시 CI 실패
```

#### 환각 원인 분석

```python
# 환각이 발생한 태스크 찾기
high_hallucination_tasks = [
    t for t in monitor.tasks
    if t.extra.get("hallucination_rate", 0) > 0.15
]

# 컨텍스트 길이와 환각률의 관계 분석
import statistics
short_context_rates = [
    t.extra.get("hallucination_rate", 0)
    for t in monitor.tasks
    if len(t.extra.get("context", "")) < 500
]
long_context_rates = [
    t.extra.get("hallucination_rate", 0)
    for t in monitor.tasks
    if len(t.extra.get("context", "")) >= 500
]

print(f"짧은 컨텍스트 환각률: {statistics.mean(short_context_rates):.1%}")
print(f"긴 컨텍스트 환각률: {statistics.mean(long_context_rates):.1%}")
# → 컨텍스트가 짧을수록 환각이 많다면 → 검색 품질 개선 필요
```

---

## 8. 지표 조합 전략

### 8.1 에이전트 유형별 추천 지표 조합

#### QA 봇 (단순 질의응답)

```python
eval = QuickEval("results/")

@eval.qa
def qa_bot(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 핵심 모니터링 지표
eval.gate(
    tcr=85,           # 완료율 85% 이상
    accuracy=75,      # 정확도 75% 이상
    p95_latency=2.0,  # P95 레이턴시 2초 이하
)
```

**집중할 지표**: TCR + Accuracy + Latency

**Accuracy < 70%** → 프롬프트 개선, few-shot 예제 추가
**Latency P95 > 3초** → 모델 크기 축소, 캐싱 도입
**TCR < 80%** → 오류 패턴 분석, 재시도 로직 추가

#### RAG 시스템

```python
eval = QuickEval.for_rag("results/")  # hallucination 기본 활성

@eval.rag  # task_type="information_retrieval" + rag_mode=True 자동 설정
def rag_system(question: str, context: str = "", ground_truth: str = "") -> str:
    docs = vector_store.similarity_search(question)
    context = "\n".join([d.page_content for d in docs])
    return llm.invoke(f"Context: {context}\n\nQ: {question}")

# RAG 특화 게이팅
eval.gate(
    tcr=85,
    accuracy=70,
    hallucination=5,  # 환각률 5% 이하
    quality=3.5,      # 품질 점수 3.5/5 이상
)
```

**집중할 지표**: TCR + Accuracy + Hallucination + Quality

**Hallucination 높음** → 검색 품질 개선, 프롬프트에 "only use context" 지시 강화
**Quality Completeness 낮음** → 검색 문서 수 늘리기, 재랭킹 적용

#### 도구 호출 에이전트

```python
eval = QuickEval("results/")

@eval.tool_use
def tool_agent(question: str, ground_truth: str = "", expected_tools: list = None) -> str:
    return agent_executor.invoke({"input": question})

# Tool Use 특화 — Layer 2 지표도 활성화
eval.gate(
    tcr=80,
    p95_latency=5.0,  # 도구 호출은 시간이 더 걸림
)
```

**집중할 지표**: TCR + Latency + Token Economy + (Layer 2) Tool Selection F1

**Tool Selection F1 낮음** → 도구 설명(description) 개선, 도구 선택 예제 추가
**Token Economy 높음** → 불필요한 도구 호출 제거, 병렬 도구 호출 도입

#### 비용 최적화 분석

```python
# 모델별 비용/품질 트레이드오프 분석
eval_expensive = QuickEval("results/expensive/")   # GPT-4o
eval_cheap = QuickEval("results/cheap/")            # GPT-4o-mini

# 동일 테스트셋으로 각각 평가 실행 후

summary_exp = eval_expensive.summary()
summary_cheap = eval_cheap.summary()

print("=" * 40)
print(f"{'지표':<20} {'GPT-4o':>10} {'GPT-4o-mini':>12}")
print("=" * 40)
print(f"{'정확도':<20} {summary_exp['accuracy']:>10.1%} {summary_cheap['accuracy']:>12.1%}")
print(f"{'품질 점수':<20} {summary_exp['quality_avg']:>10.1f} {summary_cheap['quality_avg']:>12.1f}")
print(f"{'P95 레이턴시':<20} {summary_exp['p95_latency']:>9.1f}s {summary_cheap['p95_latency']:>11.1f}s")
print(f"{'태스크당 비용':<20} ${summary_exp['avg_cost_per_task']:>9.4f} ${summary_cheap['avg_cost_per_task']:>11.4f}")
print("=" * 40)

# 월 1만건 처리 시 비용 비교
monthly_tasks = 10_000
print(f"\n월 {monthly_tasks:,}건 처리 예상 비용:")
print(f"GPT-4o:     ${summary_exp['avg_cost_per_task'] * monthly_tasks:.2f}")
print(f"GPT-4o-mini: ${summary_cheap['avg_cost_per_task'] * monthly_tasks:.2f}")
```

### 8.2 지표 간 상관관계

자주 관찰되는 패턴과 해석:

| 패턴 | 의미 | 권장 행동 |
|---|---|---|
| Accuracy 높음 + Latency 높음 | 큰 모델 사용 중 | 소형 모델 + 캐싱 검토 |
| Accuracy 낮음 + Latency 낮음 | 소형 모델의 품질 한계 | 더 큰 모델 or 파인튜닝 |
| Quality 낮음 + Accuracy 높음 | 응답이 정확하나 형식이 나쁨 | 출력 형식 프롬프팅 |
| Hallucination 높음 + Accuracy 낮음 | 컨텍스트 무시 | RAG 파이프라인 재설계 |
| Token Economy 높음 + Latency 높음 | 과다한 컨텍스트 | 프롬프트 최적화 |

### 8.3 종합 대시보드 설정

```python
from agent_evaluator import QuickEval, AlertRuleBuilder

eval = QuickEval(
    "results/",
    auto_save=True,
    auto_save_interval=50,
)

# 지표별 알림 규칙
rules = [
    AlertRuleBuilder.when_accuracy_below(threshold=0.7,
        handler=lambda msg, _: print(f"[품질 경고] {msg}")),
    AlertRuleBuilder.when_latency_above(threshold=5.0,
        handler=lambda msg, _: print(f"[성능 경고] {msg}")),
    AlertRuleBuilder.when_completion_below(threshold=0.8,
        handler=lambda msg, _: print(f"[완료율 경고] {msg}")),
    AlertRuleBuilder.when_error(
        handler=lambda msg, tr: print(f"[오류] {tr.errors}")),
]

# 모든 에이전트에 공통 규칙 적용
dec = eval.decorator
dec._defaults["alert_rules"] = rules

@dec.qa
def agent1(question: str, ground_truth: str = "") -> str: ...

@dec.rag
def agent2(question: str, context: str = "", ground_truth: str = "") -> str: ...

# 평가 완료 후 종합 보고
summary = eval.summary()
print(f"""
=== 평가 요약 ===
TCR:        {summary['tcr']:.1%}
정확도:     {summary['accuracy']:.1%}
품질:       {summary['quality_avg']:.1f}/5.0
P95 레이턴시: {summary['p95_latency']:.2f}초
월 예상 비용: ${summary['total_cost_usd'] * 30:.2f}
""")

# CI 게이팅
eval.gate(tcr=85, accuracy=70, quality=3.0, p95_latency=3.0)
```

---

## 요약 카드

각 지표를 한눈에 정리한 참고 카드:

```
┌────────────────────────────────────────────────────────────────┐
│                    Layer 1 지표 요약                           │
├──────────────┬───────────────┬──────────────┬─────────────────┤
│ 지표         │ 기본 활성     │ 핵심 출력    │ 목표값 (일반)  │
├──────────────┼───────────────┼──────────────┼─────────────────┤
│ TCR          │ ✅ 자동       │ tcr          │ ≥ 85%          │
│ Accuracy     │ ✅ 자동       │ overall_acc  │ ≥ 70%          │
│ Quality      │ ✅ 자동       │ quality_score│ ≥ 3.5/5        │
│ Latency      │ ✅ 자동       │ p95_latency  │ ≤ 3.0초        │
│ Token Economy│ ✅ 자동       │ total_cost   │ 예산 내        │
│ Hallucination│ ❌ opt-in     │ halluc_rate  │ ≤ 5%           │
└──────────────┴───────────────┴──────────────┴─────────────────┘
```

---

## QA 관리자 헬스체크 가이드

### 결과를 받았을 때 읽는 순서

평가 결과(`report.to_dict()` 또는 대시보드)를 처음 열었을 때 아래 순서로 확인한다.

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
print(slow[["question", "execution_time", "tokens_total"]].head())

# ④ Quality 낮음 → 어느 차원이 문제인가?
report = eval.monitor.generate_report()
qm = report.to_dict()
# quality 5차원 상세 확인
quality_detail = qm.get("quality_metrics", {})
for dim in ["relevance", "completeness", "clarity", "conciseness", "coherence"]:
    val = quality_detail.get(f"avg_{dim}", quality_detail.get(dim, "N/A"))
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
| Accuracy | ✅ | ✅ | ✅ | `ground_truth_arg` 존재 시 | ground_truth 있으면 자동 |
| Response Quality | ✅ | ✅ | ✅ | 없음 (`enable_quality_evaluation` 선택) | response + question 자동 |
| Latency | ✅ | ✅ | ✅ | 없음 | **항상 자동** |
| TTFT | ✅ generator | ✅ `streaming_mode` | ❌ | generator 리턴 함수 | generator 시 자동 |
| Token Economy | ✅ | ✅ | ❌ | `framework=` 어댑터 or EvalMetadata | 지원 프레임워크 자동 |
| Hallucination Rate | ✅ | ✅ | ❌ | `rag_mode=True` (권장) | **수동 활성 필요** |

```python
# ① 기본 — TCR + Accuracy + Quality + Latency 자동
@agent_eval(monitor, task_type="qa")
def agent(question, ground_truth=""): ...

# ② 토큰 비용 추가
@agent_eval(monitor, framework="openai", model_name="gpt-4o-mini")
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

*다음 강의: M3 — Layer 2 에이전틱 & 보안 지표*
