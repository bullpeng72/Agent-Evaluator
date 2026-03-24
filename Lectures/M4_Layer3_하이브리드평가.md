# Module 4 — Layer 3: 하이브리드 평가 (DeepEval + Ragas)

**시간:** 3시간
**참조 코드:** `Evaluator_Examples/05_hybrid_metrics.py`
**핵심 Docs:** `10_KOREAN_RAG_GUIDE.md`, `06_METRICS_GUIDE.md`, `16_KNOWN_ISSUES_AND_QUIRKS.md`
**사전 요구사항:** `OPENAI_API_KEY` 설정 필수

---

## 4-1. Rule-based 평가의 한계 (20분)

### Layer 1이 놓치는 것

M2에서 배운 Layer 1 평가는 빠르고 무료지만 한계가 있다.

```python
# Layer 1 AccuracyEvaluator로는 이 두 답을 구분 못 함
ground_truth = "서울"
response_a = "서울입니다."             # 좋은 답
response_b = "서울이긴 한데 사실 부산이 더 크다."  # 나쁜 답 (사실 오류)

# Token F1 기반 정확도
# response_a: 0.67 (토큰 일치)
# response_b: 0.40 (토큰 일치) → "더 낮긴 하지만 '서울' 포함"
# → 의미적 판단 불가
```

| 평가 한계 | 증상 | Layer 3 해결 |
|----------|------|-------------|
| 의미 동치 불인식 | "서울" vs "대한민국 수도" → 다른 답 | G-Eval criteria |
| 허위 정보 탐지 | 사실과 다른 주장 → 높은 토큰 F1 | Hallucination 지표 |
| 독성/편향 탐지 | 욕설·차별 표현 포함 → 정확도 무관 | Toxicity/Bias |
| RAG 품질 | 검색 결과 활용도 → 토큰 F1과 무관 | Ragas 4지표 |

---

### 비용 vs 정밀도 트레이드오프

```
정밀도
  │                              ● Layer 3 전수 ($1-3/1K tasks)
  │                    ● L1+L2+L3 10% 샘플 ($0.1-0.3/1K tasks)
  │         ● Layer 1+2 전수 ($0/1K tasks)
  │ ● Layer 1만 ($0/1K tasks)
  └──────────────────────────────────────── 비용
```

**실무 권장 전략:**
- **개발 중**: Layer 1 전수 (무료, ~ms)
- **스테이징**: Layer 1+2 전수 + Layer 3 10% 샘플
- **프로덕션**: Layer 1+2 전수 + Layer 3 의심 케이스만

---

## 4-2. DeepEval 5개 지표 + G-Eval 작성법 (45분)

### HybridPerformanceMonitor 초기화

```python
from agent_evaluator import HybridPerformanceMonitor, hybrid_evaluation_session
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent / ".env")

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_deepeval=True,
    enable_ragas=True,
    deepeval_config={
        "model": "gpt-4o-mini",                    # 평가에 사용할 LLM
        "criteria": "정확성, 완결성, 한국어 자연스러움",  # G-Eval 기준
        "threshold": 0.5
    }
)
```

---

### DeepEval 5개 지표

#### 1. G-Eval (커스텀 채점)

가장 유연한 지표. LLM이 사용자 정의 기준으로 응답을 채점한다.

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="geval_001",
    question="양자 컴퓨팅을 초등학생에게 설명해줘",
    response="양자 컴퓨팅은 양자역학을 이용하는 컴퓨터예요. 일반 컴퓨터가 0과 1만 쓴다면, 양자 컴퓨터는 0과 1을 동시에 쓸 수 있어요!",
    ground_truth="양자 컴퓨팅 개념 설명",
    execution_time=2.1,
    task_type="qa",
)
monitor.record_task(result)
# → G-Eval이 "이해하기 쉬운가? 초등학생 눈높이인가?"를 LLM으로 판단
```

#### 좋은 G-Eval Criteria 작성법

```python
# ❌ 나쁜 기준 — 너무 모호
bad_criteria = "좋은 응답인지 평가해줘"

# ✅ 좋은 기준 — 구체적이고 측정 가능
good_criteria = """
다음 기준으로 응답을 0.0–1.0 점수로 평가하라:
1. 정확성 (0.4): 사실 오류 없음, ground_truth와 핵심 내용 일치
2. 완결성 (0.3): 질문의 모든 측면에 답변
3. 명확성 (0.3): 대상 독자 (초등학생)에게 이해 가능한 언어 사용
"""

monitor = HybridPerformanceMonitor(
    enable_deepeval=True,
    deepeval_config={"criteria": good_criteria}
)
```

**G-Eval criteria 작성 체크리스트:**
- [ ] 평가 차원이 명시되어 있는가?
- [ ] 각 차원에 가중치가 있는가?
- [ ] 0–1.0 척도 또는 구체적 기준이 있는가?
- [ ] 대상 독자/사용 맥락이 반영되어 있는가?

---

#### 2. Hallucination (LLM 기반 환각 탐지)

Layer 1 rule-based 탐지와 달리, LLM이 의미를 이해하여 판단한다.

```python
result = create_taskresult(
    task_id="hall_001",
    question="아인슈타인의 출생년도는?",
    response="아인슈타인은 1879년 독일에서 태어났습니다.",
    ground_truth="1879년생, 독일 울름 출생",
    execution_time=1.5,
    task_type="qa",
    context=["Albert Einstein was born on March 14, 1879 in Ulm, Germany."]
)
monitor.record_task(result)
```

#### L1 rule-based vs L3 LLM 비교 (핵심)

| 비교 항목 | L1 Rule-based | L3 DeepEval Hallucination |
|----------|--------------|--------------------------|
| 속도 | ~5–20 ms | ~1,000–3,000 ms |
| 비용 | $0 | ~$0.001/태스크 |
| 의미 이해 | ❌ 패턴 매칭만 | ✅ 의미 기반 판단 |
| 한국어 동의어 | ❌ "서울" ≠ "대한민국 수도" | ✅ 동치 인식 |
| 미묘한 오류 탐지 | ❌ 놓침 | ✅ 탐지 |
| **권장 사용 상황** | 빠른 스크리닝 | 정밀 감사 |

**실무 전략:** L1으로 1차 스크리닝 → L3으로 의심 케이스 정밀 평가

---

#### 3. Toxicity Score (독성 탐지)

응답에 욕설, 혐오 표현, 폭력적 내용이 포함되어 있는지 탐지.

```python
result = create_taskresult(
    task_id="tox_001",
    question="이 사람이 왜 틀렸는지 설명해줘",
    response="이 주장은 논리적 오류가 있습니다. 첫째...",  # 정상
    ground_truth="합리적인 비판적 분석",
    execution_time=1.8,
    task_type="qa"
)
monitor.record_task(result)
# Toxicity Score → 0.0에 가까울수록 안전
```

#### 4. Bias Score (편향 탐지)

성별, 인종, 정치적 편향 등 bias 탐지.

```python
# Bias Score → 0.0에 가까울수록 중립적
```

#### 5. Answer Relevancy (임베딩 기반 관련성)

질문과 응답의 의미적 관련성을 임베딩으로 측정.

```python
# ⚠️ OpenAI API 키가 있을 때만 자동 설정
# Anthropic-only 환경: AnswerRelevancy 지표 제외됨
```

---

### DeepEval 결과 확인

```python
# 대시보드 DeepEval 탭에서 확인
# agent-eval serve --port 8765

# 코드로 직접 확인
report = monitor.generate_report()
deepeval_stats = report.get("deepeval_stats", {})

if deepeval_stats:
    print(f"G-Eval 평균: {deepeval_stats.get('avg_g_eval_score', 0):.3f}")
    print(f"Hallucination 평균: {deepeval_stats.get('avg_hallucination', 0):.3f}")
    print(f"Toxicity 평균: {deepeval_stats.get('avg_toxicity', 0):.3f}")
    print(f"평가 건수: {deepeval_stats.get('total_evaluated', 0)}")
```

---

## 4-3. Ragas 4개 지표 + RAG 개선 사이클 (45분)

### RAG 파이프라인 평가 필요성

Retrieval-Augmented Generation (RAG)에서는 두 가지 품질이 중요하다:
1. **검색(Retrieval) 품질** — 올바른 문서를 찾았는가?
2. **생성(Generation) 품질** — 찾은 문서를 잘 활용했는가?

```
사용자 질문
    ↓
[Retriever] → 관련 문서 검색
    ↓
[LLM Generator] → 문서 기반 응답 생성
    ↓
응답

Ragas는 이 파이프라인 전체를 4개 지표로 평가
```

### Ragas 4개 지표

#### 1. Faithfulness — 컨텍스트 충실도

"응답이 검색된 컨텍스트에 근거하는가?"

```
높음 (>0.8): 응답의 대부분이 컨텍스트에서 지지됨
낮음 (<0.5): 컨텍스트와 무관한 내용을 생성 (환각 위험)
```

#### 2. Answer Relevancy — 답변 관련성

"응답이 질문에 얼마나 관련 있는가?"

```
높음 (>0.8): 질문에 집중된 답변
낮음 (<0.5): 질문과 무관한 내용 포함
```

#### 3. Context Precision — 검색 정밀도

"검색된 컨텍스트가 얼마나 관련 있는가?"

```
높음 (>0.8): 검색된 문서 대부분이 관련 있음
낮음 (<0.5): 관련 없는 문서가 많이 검색됨 → 검색 쿼리 개선 필요
```

#### 4. Context Recall — 검색 재현율

"필요한 정보가 검색에서 누락되지 않았는가?"

```
높음 (>0.8): 답변에 필요한 정보가 대부분 검색됨
낮음 (<0.5): 필요한 정보 누락 → 문서 커버리지 개선 필요
```

---

### Ragas 평가 코드

```python
from agent_evaluator import HybridPerformanceMonitor, create_taskresult

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_ragas=True
)

# RAG 태스크 — context 필드 필수
rag_result = create_taskresult(
    task_id="rag_001",
    question="한국의 GDP는 얼마인가?",
    response="한국의 GDP는 약 1조 7천억 달러입니다 (2023년 기준).",
    ground_truth="약 1.7조 달러 (2023년)",
    execution_time=2.3,
    task_type="qa",
    context=[                                                   # 검색된 컨텍스트
        "South Korea GDP 2023: approximately $1.709 trillion USD",
        "Korea economy grew 1.4% in 2023 according to World Bank"
    ]
)
monitor.record_task(rag_result)
```

### ⚠️ Ragas 0.4.x API 변경 (중요)

```python
# ❌ 구버전 API (0.3.x, 동작 안 함)
from ragas import evaluate
from ragas.metrics import faithfulness
result = evaluate(Dataset.from_dict(data), metrics=[faithfulness])

# ✅ 0.4.x 이후 (현재)
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import Faithfulness

sample = SingleTurnSample(
    user_input="질문",
    response="답변",
    retrieved_contexts=["컨텍스트"],
    reference="정답"
)
dataset = EvaluationDataset(samples=[sample])
result = evaluate(dataset, metrics=[Faithfulness()])
```

> **확인:** `pip show ragas`로 버전이 0.4.0 이상인지 확인. Agent-Evaluator가 내부적으로 처리하므로 직접 호출할 필요는 없음.

---

### RAG 개선 사이클

Ragas 지표를 활용해 체계적으로 RAG 파이프라인을 개선하는 방법:

```
평가 → 진단 → 개선 → 재평가
  ↑                        ↓
  └────────────────────────┘
```

#### 진단 매트릭스

| Context Precision | Context Recall | 진단 | 개선 방향 |
|:------------------:|:--------------:|------|----------|
| 높음 | 높음 | ✅ 검색 최적 | 생성 품질 집중 |
| 낮음 | 높음 | 과검색 | 검색 결과 필터링 강화 |
| 높음 | 낮음 | 미검색 | 청킹 전략 변경, 문서 커버리지 확대 |
| 낮음 | 낮음 | 검색 실패 | 임베딩 모델 교체, 쿼리 재작성 |

#### Faithfulness vs Answer Relevancy 진단

```
Faithfulness 낮음 + Answer Relevancy 높음:
→ 질문에 잘 답하지만 컨텍스트를 무시함 → 환각 위험
→ 대책: 컨텍스트 참조를 강제하는 프롬프트 추가

Faithfulness 높음 + Answer Relevancy 낮음:
→ 컨텍스트를 잘 활용하지만 질문을 이해 못함
→ 대책: 질문 이해를 위한 쿼리 분해/개선
```

---

### 실습: 한국어 RAG 데이터셋 생성

Agent-Evaluator에는 한국어 RAG 평가용 데이터셋 생성 도구가 있다.

```python
from agent_evaluator.datasets import KoreanRAGDatasetGenerator

generator = KoreanRAGDatasetGenerator(
    domain="technology",
    num_samples=20
)

# 골든 데이터셋 생성
dataset = generator.generate()
dataset.save_to_file("results/golden_datasets/korean_rag.json")

# 대시보드 Golden 탭에서 확인 및 편집
# agent-eval serve → Golden 탭
```

---

## 4-4. 대시보드 RAG/DeepEval 탭 (30분)

### RAG 탭

```bash
agent-eval serve --port 8765
# → 브라우저에서 RAG 탭 열기
```

**KPI 카드 확인:**

| 카드 | 목표값 | 현재값 해석 |
|------|--------|------------|
| Ragas Overall | > 0.7 | 4개 지표 평균 |
| Faithfulness | > 0.8 | 컨텍스트 충실도 |
| Answer Relevancy | > 0.8 | 답변 관련성 |
| Context Precision | > 0.7 | 검색 정밀도 |
| Context Recall | > 0.7 | 검색 재현율 |

**서브텍스트 읽는 법:**
```
Faithfulness: 0.82  ← 평균값
N건 | min 0.45 / max 0.97  ← 분포 (min/max 격차 크면 일관성 문제)
```

**4개 지표 라인 차트:**
- 태스크별 변동이 큰 경우 → 특정 유형 질문에서 RAG 성능 저하
- 호버 시 소수점 3자리 표시 (`0.667`)

---

### DeepEval 탭

> **주의:** DeepEval 탭에는 DeepEval 전용 지표만. Ragas 지표는 RAG 탭에서 별도 표시됨 (v0.6.0에서 분리).

**KPI 카드:**
- G-Eval Score — 커스텀 기준 점수 (0–1.0)
- Hallucination — 환각 비율 (낮을수록 좋음)
- Toxicity Score — 독성 비율 (낮을수록 좋음)
- Bias Score — 편향 비율 (낮을수록 좋음)

**G-Eval 분포 히스토그램:**
- 0–1.0 범위에서 태스크 점수 분포 확인
- 왼쪽 편향(낮은 점수 집중) → 품질 문제

**태스크별 상세 테이블:**
- G-Eval reason 전체 텍스트 — GPT가 채점한 근거 확인
- 낮은 점수 태스크의 reason을 읽으면 개선 방향 파악 가능

---

## 4-5. 레이어 선택 매트릭스 (20분)

### 상황별 권장 레이어

| 상황 | L1 | L2A | L2B | L3 | 이유 |
|------|:--:|:---:|:---:|:--:|------|
| 개발 중 빠른 피드백 | ✅ | - | - | - | 무료, ~ms, 즉시 실행 |
| 에이전트 행동 분석 | ✅ | ✅ | - | - | Tool/Retry/Workflow |
| 보안 검증 필요 | ✅ | ✅ | ✅ | - | `enable_security_metrics=True` |
| RAG 파이프라인 최적화 | ✅ | - | - | ✅(Ragas) | 검색/생성 품질 정밀 측정 |
| 콘텐츠 안전성 | - | - | - | ✅(DeepEval) | Toxicity/Bias는 LLM 판단 필수 |
| 스테이징 회귀 테스트 | ✅ | ✅ | ✅ | - | 종합 커버리지, API 비용 없음 |
| 프로덕션 전수 감사 | ✅ | ✅ | ✅ | 10% 샘플 | 비용 최소화 |
| 최고 정밀도 평가 | ✅ | ✅ | ✅ | ✅ | 모든 레이어 활성화 |

### 비용 계산 예시

```
1,000개 태스크 평가 시:
  Layer 1+2 전수:            $0
  Layer 3 전수 (GPT-4o-mini): $1–3
  L1+L2 + L3 10% 샘플:       $0.1–0.3  ← 동등한 통계적 신뢰도
```

### 속도 비교

```
Layer 1 (AccuracyEvaluator):       ~1–5 ms / 태스크
Layer 1 (HallucinationDetector):   ~5–20 ms / 태스크
Layer 2 (보안 지표):               ~5–15 ms / 태스크
Layer 3 (DeepEval G-Eval):         ~1,000–3,000 ms / 태스크 (API 호출)
Layer 3 (Ragas Faithfulness):      ~500–2,000 ms / 태스크 (API 호출)
```

### 의사결정 흐름도

```python
def choose_evaluation_layer(
    budget: str,          # "none", "low", "medium", "unlimited"
    needs_security: bool,
    is_rag_system: bool,
    needs_toxicity_check: bool
) -> dict:

    layers = {"L1": True, "L2A": False, "L2B": False, "L3": {}}

    # 에이전트 행동 분석이 필요하면 L2A
    layers["L2A"] = True  # 항상 권장

    # 보안 검증
    if needs_security:
        layers["L2B"] = True

    # L3 선택
    if budget != "none":
        if is_rag_system:
            layers["L3"]["ragas"] = True
        if needs_toxicity_check:
            layers["L3"]["deepeval"] = True
        if budget == "low":
            layers["L3"]["sampling_rate"] = 0.1  # 10% 샘플
        else:
            layers["L3"]["sampling_rate"] = 1.0  # 전수

    return layers

# 예시
config = choose_evaluation_layer(
    budget="low",
    needs_security=True,
    is_rag_system=True,
    needs_toxicity_check=False
)
# → L1 + L2A + L2B + Ragas 10% 샘플
```

---

## 모듈 4 실습: 05_hybrid_metrics.py 실행

```bash
# OPENAI_API_KEY가 .env에 설정되어 있어야 함
cd Evaluator_Examples
python 05_hybrid_metrics.py
agent-eval serve --port 8765
```

### 확인 항목

1. **RAG 탭**
   - Ragas Overall Score KPI
   - 4개 지표 라인 차트에서 변동이 큰 태스크 식별
   - 태스크별 상세 테이블에서 낮은 점수 원인 분석

2. **DeepEval 탭**
   - G-Eval Score 분포 히스토그램
   - 낮은 점수 태스크의 reason 텍스트 확인
   - Toxicity/Bias Score 확인

3. **개선 방향 도출**
   - Context Precision < 0.7 → 검색 쿼리 개선
   - Faithfulness < 0.7 → 컨텍스트 참조 강제 프롬프트
   - G-Eval reason에서 반복되는 약점 패턴 찾기

---

## 핵심 요약

| 지표 | 도구 | 비용 | 속도 | 강점 |
|------|------|------|------|------|
| G-Eval | DeepEval | $0.001/태스크 | 1–3초 | 커스텀 기준 평가 |
| Hallucination | DeepEval | $0.001/태스크 | 1–3초 | 의미 기반 환각 탐지 |
| Toxicity/Bias | DeepEval | $0.001/태스크 | 1–3초 | LLM 안전성 |
| Faithfulness | Ragas | $0.002/태스크 | 0.5–2초 | RAG 컨텍스트 충실도 |
| Context Precision/Recall | Ragas | $0.002/태스크 | 0.5–2초 | 검색 품질 |

### API 키 요구사항 정리

```bash
# Layer 1+2: API 키 불필요
monitor = PerformanceMonitor(...)  # 무료

# Layer 3 DeepEval: OpenAI 필요
export OPENAI_API_KEY=sk-...

# Layer 3 Ragas: OpenAI 필요 (Answer Relevancy)
export OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY만 있으면 AnswerRelevancy 지표 제외됨
```

---

*Module 4 완료 — 다음: M5 프레임워크 통합 + 실무 파이프라인*
