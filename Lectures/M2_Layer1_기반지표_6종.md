# 모듈 2 — Layer 1 기반 지표 6종 완전 분석

**소요 시간:** 4시간
**난이도:** 초급~중급
**사전 요구사항:** Module 1 완료

---

## 모듈 목표

1. 6개 지표 각각의 공식과 임계값을 설명하고 직접 계산할 수 있다
2. `add_evaluation()`, `detect_hallucination()` 등 직접 API를 호출할 수 있다
3. Layer 1 Rule-based vs Layer 3 LLM 환각 탐지 차이를 선택 기준과 함께 설명할 수 있다
4. 토큰 입출력 비율로 프롬프트 효율 문제를 진단할 수 있다
5. `@agent_eval`로 각 지표가 자동 수집되는 방식을 설명하고 적용할 수 있다

---

## 2-1. Task Completion Rate (TCR) — 작업 완료율 (30분)

### 공식

```
TCR = Σ(completion_score) / N

completion_score 해석:
  >= 0.8  → 완전 완료 (Full Success)
  0.3–0.8 → 부분 완료 (Partial Success, 0.5로 집계)
  < 0.3   → 실패 (Failure)

벤치마크:
  > 90% — Excellent
  > 75% — Good
  > 60% — Fair
  ≤ 60% — Poor
```

### completion_score가 TCR에 직접 사용되는 방식

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(output_dir="results/")

# create_taskresult() 사용 — completion_score, accuracy_score, timestamp 자동 계산
task_high = create_taskresult(
    task_id="tcr_001",
    question="질문",
    response="답변",
    ground_truth="정답",
    execution_time=1.2,
    task_type="qa",
)
# completion_score는 accuracy_score 기반으로 자동 설정됨
monitor.record_task(task_high)

# 부분 완료 케이스 — completion_score를 직접 지정하고 싶을 때
task_partial = create_taskresult(
    task_id="tcr_002",
    question="질문",
    response="불완전한 답변",
    ground_truth="완전한 정답",
    execution_time=3.5,
    task_type="qa",
)
monitor.record_task(task_partial)

report = monitor.generate_report()
print(f"TCR: {report.task_completion_rate:.1%}")
```

### @agent_eval 사용 시 TCR 자동 수집

```python
# @agent_eval 사용 시 TCR 자동 수집
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# → 함수가 성공적으로 반환 → completion_score=1.0 자동
# → 예외 발생 → completion_score=0.0 자동 + has_error=True
```

### QA 관점 포인트

> **TCR 단독 사용 금지**
>
> 에이전트가 "완료"했다고 해서 정확한 것은 아닙니다.
> "완료했지만 틀린" 케이스를 TCR 단독으로는 잡을 수 없습니다.
>
> **권장:** TCR + Accuracy 두 지표를 항상 함께 모니터링하세요.
>
> | 상황 | TCR | Accuracy | 진단 |
> |------|-----|----------|------|
> | 정상 | 높음 | 높음 | ✅ |
> | 느린 에이전트 | 낮음 | 높음 | 성능 문제 |
> | 환각 에이전트 | 높음 | 낮음 | ⚠️ 품질 위험 |
> | 시스템 장애 | 낮음 | 낮음 | 전체 점검 필요 |

---

## 2-2. Accuracy Evaluator — 정확도 평가 (45분)

### 4가지 가중 혼합 알고리즘

```
최종 정확도 = Token F1 × 40%
            + Jaccard × 30%
            + LCS Ratio × 20%
            + Char Similarity × 10%
```

### 각 알고리즘 계산 예시

**예시:**
- `ground_truth` = "서울은 대한민국의 수도"
- `prediction` = "서울은 한국의 수도이자 최대 도시"

**Token F1 (40%):**
```
GT 토큰:  [서울, 은, 대한민국, 의, 수도]
Pred 토큰: [서울, 은, 한국, 의, 수도, 이자, 최대, 도시]

교집합 = {서울, 은, 의, 수도} → 4개
Precision = 4/8 = 0.50
Recall    = 4/5 = 0.80
F1 = 2 × (0.50 × 0.80) / (0.50 + 0.80) = 0.615
```

**Jaccard (30%):**
```
교집합 = 4개, 합집합 = 9개
Jaccard = 4/9 = 0.444
```

**LCS Ratio (20%):**
```
LCS = "서울은 수도" (또는 가장 긴 공통 부분 문자열)
LCS 길이 = 5 (문자 수)
max(len(GT), len(Pred)) = max(14, 17) = 17
LCS Ratio = 5/17 ≈ 0.294
```

**최종 점수:**
```
0.615×0.4 + 0.444×0.3 + 0.294×0.2 + char×0.1
≈ 0.246 + 0.133 + 0.059 + char
```

> **포인트:** 이 예시에서 "대한민국" vs "한국"이 다른 토큰이라 점수가 낮아집니다.
> 의미상 동일한 표현의 점수 차이가 발생하는 것은 Rule-based의 한계입니다.
> 이런 케이스에 Layer 3 G-Eval이 필요한 이유입니다.

### task_type별 분기

```python
monitor.accuracy_evaluator.add_evaluation(
    task_id="code_001",
    ground_truth="def factorial(n): return 1 if n <= 1 else n * factorial(n-1)",
    prediction="def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)",
    task_type="code_generation"  # ← AST 비교 먼저 시도
)
# AST 비교 결과: 구조가 동일 → 높은 점수 (들여쓰기 무관)

# code_generation이 아닌 경우
monitor.accuracy_evaluator.add_evaluation(
    task_id="qa_001",
    ground_truth="서울은 대한민국의 수도입니다",
    prediction="서울은 한국의 수도이자 최대 도시입니다",
    task_type="qa"  # ← Token F1 + Jaccard + LCS + Char 가중 혼합
)
```

### @agent_eval 사용 시 Accuracy 자동 수집

```python
# ground_truth를 인자로 전달하면 accuracy_score 자동 계산
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
# → 반환값과 ground_truth를 AccuracyEvaluator로 자동 평가
# → accuracy_score가 TaskResult에 자동 기록됨
```

### 직접 호출 vs `create_taskresult()` — 언제 어느 쪽을 쓰나

```python
# 방법 1: create_taskresult() — 자동 계산 (권장, 간편)
task = create_taskresult(
    task_id="t001",
    question="질문",
    response="답변",
    ground_truth="정답",
    task_type="qa",
    execution_time=1.0,
)
# accuracy_score가 내부에서 자동 계산됨

# 방법 2: add_evaluation() 직접 호출 — 정밀 평가
task = create_taskresult(task_id="t001", question="질문", response="답변",
                         ground_truth="정답", task_type="qa", execution_time=1.0)
monitor.record_task(task)

# 이후 직접 평가 추가 (동일 태스크에 복수 GT 비교 가능)
monitor.accuracy_evaluator.add_evaluation(
    task_id="t001",
    ground_truth="정답 버전 1",
    prediction="답변",
    task_type="qa"
)
monitor.accuracy_evaluator.add_evaluation(
    task_id="t001",
    ground_truth="정답 버전 2",  # 복수 정답 처리
    prediction="답변",
    task_type="qa"
)
```

> **직접 호출 권장 상황:**
> - 동일 태스크에 복수 정답(GT)이 있는 경우
> - 배치 평가 후 외부 점수와 비교할 때
> - AST 비교 결과를 명시적으로 확인할 때

> **실습:** `01_quality_eval.py`를 실행하고, high/hallucination/low_quality tier별 평균 accuracy_score를 비교해보세요.

---

## 2-3. Hallucination Detector — 환각 탐지 (45분)

### 환각 3가지 유형

**1. Unsupported Claim — 컨텍스트에 없는 정보 추가**
```
컨텍스트: "서울 인구는 약 960만 명이다"
응답:     "서울과 경기도를 합치면 수도권 인구는 약 2,500만 명이다"
          ↑ 컨텍스트에 없는 "경기도", "2,500만" 정보 추가
```

**2. Contradiction — 컨텍스트와 반대 주장**
```
컨텍스트: "달은 지구 주위를 공전한다"
응답:     "달은 태양을 직접 공전하며 지구와 무관하다"
          ↑ 컨텍스트와 정반대
```

**3. Unfaithful Paraphrase — 의미 변형 재표현**
```
컨텍스트: "이 약은 일부 환자에게 경미한 부작용이 있을 수 있다"
응답:     "이 약은 매우 안전하여 부작용이 없다"
          ↑ "일부", "경미한" 제거로 의미 반전
```

### API 사용법

```python
monitor = PerformanceMonitor(
    enable_hallucination_detection=True,  # ← 반드시 True로 설정
    output_dir="results/",
)

result = monitor.hallucination_detector.detect_hallucination(
    task_id="hall_001",
    response="달은 태양을 직접 공전합니다.",
    context="달은 지구 주위를 공전하고, 지구는 태양 주위를 공전합니다.",
    ground_truth="달은 지구를 공전합니다.",
    request="달의 공전 대상은?"  # 대시보드 표시용
)

hl_rate = result.get("hallucination_rate", 1.0)
# 1.0 = 완전 정상 (환각 없음)
# 0.0 = 완전 환각
# 0.5 이하 → 환각 의심 (L3 재평가 권장)

detected = result.get("hallucination_detected", False)
indicators = result.get("indicators", [])  # 탐지된 구체적 지표들
```

### @agent_eval 사용 시 Hallucination 자동 수집

```python
# rag_mode=True 로 hallucination 탐지 자동 활성화
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return llm.invoke_with_context(question, context)
# → context 인자를 자동 감지하여 HallucinationDetector에 전달
# → hallucination_rate가 TaskResult에 자동 기록됨
```

### 🆕 Layer 1 Rule-based vs Layer 3 LLM 환각 탐지 비교

이 비교표는 기존 Docs에 없는 내용입니다. 두 방식의 특성을 이해하고 적절히 조합하세요.

| 항목 | Layer 1 HallucinationDetector | Layer 3 DeepEval Hallucination |
|------|-------------------------------|-------------------------------|
| 방식 | Rule-based 패턴 매칭 + 토큰 오버랩 | LLM이 의미 수준에서 판단 |
| 속도 | ~1–5 ms | ~1,000–3,000 ms (API 호출) |
| 비용 | $0 | ~$0.001 / 태스크 |
| 정밀도 | 중간 (false positive 발생) | 높음 |
| 한국어 | 제한적 (토큰 기반) | 완전 지원 |
| 미묘한 환각 | 어려움 | 가능 |
| 필요 설정 | `enable_hallucination_detection=True` | `HybridPerformanceMonitor` + API 키 |

**실무 권장 전략:**
```
1단계: L1 전수 탐지 (비용 $0, 즉시)
        ↓ hallucination_rate < 0.7 이면
2단계: L3 DeepEval로 해당 태스크만 정밀 재평가
        ↓ 원인 파악 후 컨텍스트/프롬프트 개선
```

> **성능 주의:** `enable_hallucination_detection=False`가 기본값입니다.
> True로 설정하면 각 태스크마다 추가 계산이 발생합니다.
> 프로덕션 전수 평가 시 성능 영향을 고려하세요.

---

## 2-4. Response Quality Evaluator — 5차원 응답 품질 (30분)

### 5차원 평가 체계 (각 0–1.0, 합산 0–5.0)

| 차원 | 측정 내용 | 0점 예시 | 1점 예시 |
|------|----------|----------|----------|
| Relevance | 질문-답변 관련성 | 완전히 다른 주제 | 질문 핵심에 직접 답함 |
| Completeness | 필요 정보 포함 | 핵심 내용 누락 | 모든 필요 정보 포함 |
| Accuracy | 사실 정확성 | 틀린 정보 포함 | 검증된 사실만 포함 |
| Clarity | 표현 명확성 | 이해하기 어려운 표현 | 누구나 이해 가능 |
| Usefulness | 실용적 유용성 | 읽어도 도움 안 됨 | 즉시 적용 가능 |

> **스케일 주의:** 총점은 0–5.0입니다. 0–10이 아닙니다.
> 대시보드 Quality 탭도 `/5.0` 스케일로 표시합니다.

### `expected_elements`로 점수 향상

```python
# expected_elements 없이 — 일반적인 품질 평가
score1 = monitor.quality_evaluator.evaluate_response(
    task_id="q001",
    request="Python 딕셔너리 순회 방법을 알려주세요",
    response="for 루프를 사용하면 됩니다.",
    ground_truth="for key, value in dict.items()를 사용합니다",
)

# expected_elements 포함 — 도메인 특화 평가 (더 정확)
score2 = monitor.quality_evaluator.evaluate_response(
    task_id="q002",
    request="Python 딕셔너리 순회 방법을 알려주세요",
    response="for key, value in dict.items()를 사용합니다. 예: for k,v in {'a':1}.items(): print(k,v)",
    ground_truth="for key, value in dict.items()",
    expected_elements=["for", "items()", "key", "value", "예시코드"],
    # ↑ 이 요소들이 응답에 포함되면 높은 점수
)
print(f"기본 평가: {score1.get('total_score', 0):.2f}/5.0")
print(f"특화 평가: {score2.get('total_score', 0):.2f}/5.0")
```

### @agent_eval 사용 시 Quality 자동 수집

```python
# @agent_eval은 응답 품질(5차원)을 자동 평가하지는 않음
# Quality 지표는 evaluate_response()를 명시적으로 호출해야 함
# 단, create_taskresult() + record_task()로 기록 후 별도 호출 가능

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 또는 on_record 콜백으로 품질 평가 추가
@agent_eval(monitor, task_type="qa",
            on_record=lambda tr: monitor.quality_evaluator.evaluate_response(
                task_id=tr.task_id,
                request=tr.question or "",
                response=tr.response or "",
            ))
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 결과 접근 패턴

```python
# quality_evaluator의 모든 평가 결과 조회
results = monitor.quality_evaluator.get_all_evaluations()
for task_id, result in results.items():
    print(f"\n태스크: {task_id}")
    print(f"  관련성:   {result.get('relevance', 0):.2f}")
    print(f"  완전성:   {result.get('completeness', 0):.2f}")
    print(f"  정확성:   {result.get('accuracy', 0):.2f}")
    print(f"  명확성:   {result.get('clarity', 0):.2f}")
    print(f"  유용성:   {result.get('usefulness', 0):.2f}")
    print(f"  총점:     {result.get('total_score', 0):.2f}/5.0")
    print(f"  등급:     {result.get('grade', 'N/A')}")
```

---

## 2-5. Latency Tracker + Token Economy — 성능 지표 (45분)

### Latency Tracker — 왜 평균이 아닌 퍼센타일인가

```
평균 응답 시간 1.5초 — 이것이 좋은 수치인가?
→ 90%는 0.5초, 10%는 10.5초일 수 있음
→ 평균은 10%의 나쁜 경험을 가려버림

퍼센타일이 진짜 사용자 경험:
  P50 (중앙값): 절반의 사용자가 경험하는 응답 시간
  P95:         95%의 사용자는 이 시간 내에 응답 받음
  P99:         최악의 1% 케이스 — 이것이 SLA 기준
```

```python
monitor.latency_tracker.record_latency(
    task_id="lat_001",
    task_type="qa",
    total_time=2.8,
    breakdown={
        "preprocessing": 0.2,    # 입력 파싱, 컨텍스트 구성
        "model_call": 2.3,        # ← 실제 LLM 호출 (대부분 여기서 시간 소요)
        "postprocessing": 0.3,    # 응답 파싱, 포맷팅
    }
)
# breakdown으로 병목 위치 정확히 파악
# model_call이 90% 이상이면 → 모델 최적화 또는 캐싱 필요
# preprocessing이 높으면 → 컨텍스트 구성 로직 최적화 필요
```

```python
# SLA 임계값 설정 및 위반 감지
latency_stats = monitor.latency_tracker.get_stats()
p95 = latency_stats.get("p95_latency", 0)
p99 = latency_stats.get("p99_latency", 0)
SLA_P95 = 5.0  # 초
SLA_P99 = 10.0

if p95 > SLA_P95:
    print(f"⚠️ P95 SLA 위반: {p95:.2f}s > {SLA_P95}s")
if p99 > SLA_P99:
    print(f"🔴 P99 SLA 위반: {p99:.2f}s > {SLA_P99}s")
```

### @agent_eval 사용 시 Latency 자동 수집

```python
# Latency는 실행 시간을 자동 측정
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)  # 시작~종료 시간 자동 계측
# → execution_time이 TaskResult에 자동 기록됨
# → LatencyTracker에 P50/P95/P99 통계 자동 누산
```

### Token Economy Tracker

```python
monitor.token_tracker.track_usage(
    task_id="tok_001",
    input_tokens=800,
    output_tokens=120,
    task_type="qa",
    model="gpt-4o"  # 모델별 단가 자동 적용
)

# 통계 확인
token_stats = monitor.token_tracker.get_stats()
print(f"총 토큰: {token_stats.get('total_tokens', 0):,}")
print(f"총 비용: ${token_stats.get('estimated_cost_usd', 0):.4f}")
print(f"월간 예측 (1만 태스크): ${token_stats.get('monthly_projection', 0):.2f}")
```

### @agent_eval 사용 시 Token 자동 수집

```python
# OpenAI/Anthropic 응답 객체 반환 시 토큰 자동 추출
@agent_eval(monitor, task_type="qa", framework="openai")
def my_agent(question: str, ground_truth: str = "") -> str:
    return client.chat.completions.create(...)  # usage.total_tokens 자동 추출
# → framework="openai" 어댑터가 usage.input_tokens/output_tokens 자동 파싱
# → TokenEconomyTracker에 자동 기록됨

# Anthropic 사용 시
@agent_eval(monitor, task_type="qa", framework="anthropic")
def my_agent(question: str, ground_truth: str = "") -> str:
    return anthropic_client.messages.create(...)  # usage.input_tokens 자동 추출
```

### 🆕 입출력 토큰 비율로 프롬프트 효율 진단

이 진단 방법은 기존 Docs에 없는 내용입니다.

```
비율 = output_tokens / input_tokens

비율 < 0.05  → 🔴 프롬프트 비효율
               시스템 프롬프트가 너무 길거나 불필요한 컨텍스트 포함
               → 시스템 프롬프트 축약, few-shot 예시 줄이기

비율 0.05-0.3 → ✅ QA/분석 태스크의 정상 범위
               입력 > 출력인 것이 자연스러움

비율 0.3-1.5 → ✅ 생성/요약 태스크의 정상 범위

비율 > 2.0   → 🟡 출력이 너무 긺
               max_tokens 제한 추가 또는 "간결하게 답변" 지시 필요
```

```python
# 비율 분석 구현 예시
token_stats = monitor.token_tracker.get_stats()
total_input = token_stats.get("total_input_tokens", 1)
total_output = token_stats.get("total_output_tokens", 0)
ratio = total_output / total_input

print(f"입출력 비율: {ratio:.3f}")
if ratio < 0.05:
    print("⚠️ 프롬프트 최적화 필요 — 시스템 프롬프트가 과도하게 길 수 있음")
elif ratio > 2.0:
    print("⚠️ 출력 제한 필요 — max_tokens 설정 또는 간결성 지시 추가")
else:
    print("✅ 정상 범위")
```

---

## 2-6. 실무 Lab — evaluation_session 패턴 + 복수 모니터 (45분)

### evaluation_session 기본 패턴

```python
from agent_evaluator import evaluation_session, create_taskresult

# 패턴 1: 기본 사용
with evaluation_session("qa_evaluation") as monitor:
    for i, (q, a, truth) in enumerate(qa_dataset):
        task = create_taskresult(
            task_id=f"qa_{i:04d}",
            question=q, response=a, ground_truth=truth,
            execution_time=measure_time(),
            task_type="qa",
        )
        monitor.record_task(task)
# → results/qa_evaluation_YYYYMMDD_HHMMSS.json 자동 저장
# → 블록 내 예외 발생 시에도 그 시점까지 저장됨

# 패턴 2: 옵션 설정
with evaluation_session("secure_eval") as monitor:
    monitor_config = {
        "enable_hallucination_detection": True,
        "enable_security_metrics": True,
    }
    # evaluation_session은 기본 PerformanceMonitor를 사용
    # 추가 옵션이 필요하면 PerformanceMonitor 직접 생성 후 save_to_file() 호출
```

### 🆕 복수 모니터 중첩 패턴 — 멀티스테이지 평가

이 패턴은 기존 Docs에 없는 내용입니다.

```python
from agent_evaluator import evaluation_session, PerformanceMonitor

# 단계별 독립 평가 후 통합 뷰 구성
# 시나리오: RAG 파이프라인 — 검색 단계 vs 생성 단계 분리 평가

# Stage 1: 검색(Retrieval) 품질만 평가
with evaluation_session("stage1_retrieval") as m_retrieval:
    for query, retrieved_docs, relevant_docs in retrieval_results:
        task = create_taskresult(
            task_id=f"ret_{query[:10]}",
            question=query,
            response=" ".join(retrieved_docs),
            ground_truth=" ".join(relevant_docs),
            execution_time=retrieval_time,
            task_type="information_retrieval",
        )
        m_retrieval.record_task(task)
# → results/stage1_retrieval_*.json

# Stage 2: 생성(Generation) 품질만 평가
with evaluation_session("stage2_generation") as m_generation:
    for prompt, response, ground_truth in generation_results:
        task = create_taskresult(
            task_id=f"gen_{prompt[:10]}",
            question=prompt,
            response=response,
            ground_truth=ground_truth,
            execution_time=generation_time,
            task_type="qa",
        )
        m_generation.record_task(task)
# → results/stage2_generation_*.json

# 대시보드에서 두 파일을 드롭다운으로 전환하며 단계별 비교 가능
print("대시보드에서 stage1_retrieval과 stage2_generation을 비교하세요")
print("agent-eval dashboard --watch")
```

### 실습 과제

> **실습:**
>
> 1. `01_quality_eval.py`를 실행하여 `results/` 폴더에 JSON 파일 생성
> 2. `agent-eval dashboard --watch` 로 대시보드 실행
> 3. Quality 탭에서 확인:
>    - "high" tier 태스크와 "hallucination" tier 태스크의 hallucination_rate 비교
>    - 5차원 레이더에서 가장 낮은 차원 확인
> 4. `02_performance_eval.py`를 실행하여 Agentic 탭 ⚡ 실행·재시도에서 retry_rate 확인

---

## 모듈 2 요약 체크리스트

| 지표 | 공식 핵심 | 주요 임계값 | 직접 API | 데코레이터 자동화 |
|------|----------|-----------|---------|-----------------|
| TCR | Σ(completion_score) / N | > 90% Excellent | `record_task()` | 성공/예외 자동 감지 |
| Accuracy | TokenF1(40%)+Jaccard(30%)+LCS(20%)+Char(10%) | > 75% 권장 | `add_evaluation()` | ground_truth 인자 자동 |
| Hallucination | hallucination_rate (1.0=정상) | > 0.8 권장 | `detect_hallucination()` | `rag_mode=True` |
| Quality | 5차원 합산 (0–5.0) | > 3.5/5.0 권장 | `evaluate_response()` | on_record 콜백 |
| Latency | P50/P95/P99 퍼센타일 | P95 < 5초 | `record_latency()` | 실행 시간 자동 계측 |
| Token | input+output 토큰, 비용 추정 | 비율 0.05–2.0 | `track_usage()` | `framework=` 자동 추출 |

---

## 다음 모듈 예고

**Module 3 — Layer 2 에이전틱 지표 + 보안 지표**

도구 선택의 F1 점수, 재시도 패턴, 멀티에이전트 협업 분석부터 5가지 보안 위협 탐지까지.
특히 Tool Selection F1 계산, 보안 5종 API 정확한 메서드명,
출력 유출 8가지 유형(file_path 포함)까지 실무에서 반드시 알아야 할 내용을 다룹니다.

---

*Agent-Evaluator SDK 강의 자료 — v0.7.3 기준 | 2026-04-07*
