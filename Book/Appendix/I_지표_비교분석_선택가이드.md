# Appendix I. 지표 비교 분석 및 선택 가이드

> "어떤 지표가 더 좋은가"가 아니라 "어떤 상황에 어떤 지표가 적합한가"를 답한다. 각 지표의 강점·약점을 수치로 비교하고, 실무 의사결정 트리를 제공한다.

---

## I.1 정확도 지표 심층 비교

### I.1.1 BLEU vs ROUGE vs Token F1 vs BERTScore

| 항목 | BLEU | ROUGE-L | Token F1 (AE) | BERTScore |
|------|------|---------|---------------|-----------|
| **측정 대상** | n-gram 정밀도 | LCS 재현율 | 토큰 F1 | 의미적 유사도 |
| **방향** | Precision 중심 | Recall 중심 | 균형 F1 | F1 (BERT 공간) |
| **동의어 처리** | ❌ 없음 | ❌ 없음 | ❌ 없음 | ✅ 자동 처리 |
| **순서 반영** | 부분 (n-gram) | ✅ LCS | ❌ 없음 | 부분 (문맥 임베딩) |
| **외부 의존성** | 없음 | 없음 | 없음 | BERT 모델 필요 |
| **속도** | ⚡ 빠름 | ⚡ 빠름 | ⚡ 빠름 | 🐢 느림 (GPU 권장) |
| **인간 판단 상관** | 중간 (~0.5) | 중간 (~0.5) | 중간 (~0.55) | 높음 (~0.7) |
| **한국어 지원** | 제한적 | 제한적 | ✅ 전체 지원 | 한국어 BERT 필요 |

**Agent-Evaluator의 선택**: Token F1은 BLEU/ROUGE보다 인간 판단과의 상관이 약간 높고, BERTScore보다 속도가 월등하다. 4개 서브지표(Token F1 + Jaccard + LCS + Char Levenshtein) 조합은 단일 지표의 맹점을 다각도로 보완한다.

### I.1.2 각 지표의 실패 사례

```
케이스 1: 동의어 응답
  질문: "한국의 수도는?"
  정답: "서울"
  응답: "Seoul" (영문 표기)

  Token F1   = 0.0  (토큰 불일치)
  Jaccard    = 0.0
  LCS        = 0.0
  Char Lev   ≈ 0.0
  BERTScore  ≈ 0.85  (의미적으로 유사)

  → 규칙 기반 정확도 지표의 한계. LLM Judge(factual_consistency)로 보완 가능.

케이스 2: 장황한 정답
  질문: "2+2는?"
  정답: "4"
  응답: "2와 2를 더하면 4가 됩니다. 왜냐하면 덧셈의 정의에 따라..."

  Token F1   ≈ 0.4  (핵심 단어 "4" 포함, but 불필요한 토큰으로 precision 하락)
  Jaccard    ≈ 0.1
  BERTScore  ≈ 0.6
  
  → 짧은 응답이 기대되는 경우 Token F1이 정확도를 과소평가할 수 있음.
    ground_truth를 더 길게 작성하거나 completion_score와 함께 판단 권장.

케이스 3: 순서 반전
  정답: "첫 번째 단계는 A, 두 번째는 B, 세 번째는 C"
  응답: "C를 먼저 한 뒤 B, A 순서로 수행한다"
  
  Token F1   ≈ 0.8  (단어 대부분 포함)
  Jaccard    ≈ 0.8
  LCS        ≈ 0.33  (순서가 역방향 — 공통 부분 수열 짧음)
  
  → LCS가 순서 오류를 효과적으로 탐지. 순서가 중요한 태스크에서는
    LCS 가중치를 높이거나 LLM Judge 활용 권장.
```

### I.1.3 태스크 유형별 권장 정확도 지표

| 태스크 유형 | 주요 지표 | 이유 |
|------------|----------|------|
| 단답형 QA | Token F1 (40%) | 키워드 매칭이 핵심 |
| 장문 요약 | LCS (40%) + Token F1 (30%) | 순서와 포괄성 모두 중요 |
| 코드 생성 | AST 기반 completion (별도) | 토큰 유사도는 코드 품질 반영 불가 |
| 번역 | Token F1 + LCS | 단어 선택과 순서 모두 중요 |
| 분류/태깅 | Token F1만 | 정해진 레이블 집합 |
| 창작 글쓰기 | LLM Judge (완전성, 관련성) | 규칙 기반 정확도 부적합 |

---

## I.2 환각 탐지 방법 비교

### I.2.1 3가지 방법론 개요

**방법 1: 규칙 기반 (Agent-Evaluator Group A-G Tracker)**
- 컨텍스트 토큰 커버리지 + 수치 불일치 탐지
- 정밀도: ~70-80%, 재현율: ~65-75%
- 비용: 0 (외부 API 없음)
- 속도: < 5ms per call

**방법 2: NLI 기반 (Natural Language Inference)**
- 학습된 NLI 모델이 [전제, 가설] 쌍에 대해 수반/중립/모순을 분류
- 정밀도: ~85-90%, 재현율: ~80-88%
- 비용: BERT 모델 추론 비용 (로컬 GPU 기준 무료, API는 유료)
- 속도: ~50-200ms per call (GPU 기준)

**방법 3: LLM 기반 (Agent-Evaluator LLM Judge)**
- LLM이 "이 응답이 컨텍스트에 근거하는가?"를 1~5점으로 채점
- 정밀도: ~90-95%, 재현율: ~88-92%
- 비용: API 호출 비용 (GPT-4o 기준 건당 약 $0.003-$0.01)
- 속도: ~500ms-2s per call

### I.2.2 정밀도-비용 트레이드오프 분석

```
                  정밀도
                    ↑
              ● LLM Judge (Group G)
             /     |
            /      |
           ● NLI   |
          /        |
         ● 규칙 기반|
        /          |
       ────────────→ 비용(API 호출 수)
```

**실무 권장 전략**:
```
1단계 (전체 태스크): 규칙 기반 환각 탐지
  → hallucination_rate > 0.15 인 케이스 플래그

2단계 (플래그된 케이스만): LLM Judge rag_mode=True
  → faithfulness 점수로 정밀 검증

3단계 (faithfulness < 2.0): 인간 검토
  → 실제 컨텍스트 무시 여부 최종 판정
```

이 3단계 전략은 모든 케이스를 LLM Judge로 평가하는 것 대비 비용을 약 90% 절감한다.

### I.2.3 한국어 특화 고려사항

한국어 환각 탐지에서 규칙 기반 방법의 추가 한계:
- 토큰화 문제: "서울이", "서울은", "서울의"가 동일 어간 "서울"임을 인식 못함
- 한자어 표기 변환: "대한민국"과 "한국"이 같은 개념임을 모름

Agent-Evaluator에서 이를 부분 완화하는 방법:
```python
# 한국어 형태소 어간 정규화 (선택적 전처리)
import re

def normalize_korean(text: str) -> str:
    # 조사 제거 패턴 (간소화)
    text = re.sub(r'(은|는|이|가|을|를|의|에|로|으로|에서|까지)\b', '', text)
    return text

# LLM Judge가 가장 효과적인 해법 — 의미를 이해하기 때문
```

---

## I.3 LLM-as-Judge 신뢰성 분석

### I.3.1 알려진 편향 유형과 크기

연구(Zheng et al. 2023, Wang et al. 2023)에서 확인된 편향:

| 편향 유형 | 효과 크기 | 설명 | 완화 방법 |
|----------|----------|------|----------|
| **위치 편향** (Position) | ~10~15% | A/B 비교에서 먼저 제시된 응답 선호 | 순서를 바꿔 2회 채점 후 평균 |
| **장황함 편향** (Verbosity) | ~8~12% | 긴 응답을 더 좋다고 채점 | Length-controlled AlpacaEval 방식 |
| **자기강화** (Self-enhancement) | ~5~8% | 자신(동일 회사 모델)이 생성한 응답 선호 | 다른 회사 Judge 사용 |
| **형식 편향** (Format) | ~5~10% | 마크다운/불릿 포인트 있는 응답 선호 | 시스템 프롬프트에 형식 중립 지시 |
| **권위 편향** (Authority) | ~3~5% | "GPT-4가 생성했다"는 레이블이 있으면 높은 점수 | 출처 블라인드 처리 |

**Agent-Evaluator의 완화 전략**:
1. **절대 채점** (상대 비교 대신): A vs B 비교 대신 각 응답을 독립적으로 채점 → 위치 편향 제거
2. **1~5 척도**: 1~10보다 좁은 범위 → 극단적 점수 감소
3. **다차원 독립 채점**: 단일 종합 점수 대신 5개 차원 독립 측정 → 편향이 한 차원에 집중
4. **샘플링**: 10% 샘플링 → 편향의 절대적 영향 감소

### I.3.2 판정 일관성 (Consistency) 측정

```python
# LLM Judge의 일관성 측정 방법
# 출처: Evaluator_Examples/04_decorator_quickeval.py, LLMJudge 섹션
def measure_consistency(judge: LLMJudge, test_cases: list, n_repeats: int = 3) -> float:
    """
    같은 케이스에 대해 n회 채점 후 표준편차로 일관성 측정
    """
    inconsistency_scores = []
    
    for case in test_cases:
        scores = []
        for _ in range(n_repeats):
            result = judge.judge(
                task_id=case["task_id"],
                question=case["question"],
                response=case["response"],
            )
            scores.append(result["scores"]["overall"])
        
        # 표준편차가 작을수록 일관성 높음
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0
        inconsistency_scores.append(std_dev)
    
    return 1.0 - (sum(inconsistency_scores) / len(inconsistency_scores) / 2.5)
    # 표준편차 0 → 일관성 1.0, 표준편차 2.5 → 일관성 0.0

# GPT-4의 1~5 척도 일관성: 약 0.85~0.90 (반복 실험 기준)
# Claude의 1~5 척도 일관성: 약 0.87~0.92
```

### I.3.3 Judge 모델 선택 가이드

| 상황 | 권장 Judge | 이유 |
|------|-----------|------|
| 범용 QA/요약 | `claude-haiku-4-5` (기본) | 빠르고 저렴, 충분한 판정 능력 |
| 전문 도메인 (의료/법률) | `claude-sonnet-4-6` | 더 높은 도메인 지식 |
| 한국어 특화 | `claude-sonnet-4-6` or `gpt-4o` | 한국어 이해도 높음 |
| 비용 최소화 | `claude-haiku-4-5` + 5% 샘플링 | |
| 최고 정확도 | `claude-opus-4-6` | 복잡한 판정 케이스 |
| Anthropic 키 없음 | `gpt-4o-mini` | OpenAI 자동 선택 |

```python
# judge_model=None 시 자동 선택 로직
def _auto_select_model():
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude-haiku-4-5-20251001"  # 기본값
    elif os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    else:
        raise ValueError("ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 필요")
```

---

## I.4 RAG 평가 지표 비교

### I.4.1 Faithfulness vs HallucinationRate

이 두 지표는 "응답이 얼마나 사실에 충실한가"를 측정하지만 방향이 반대다.

```
HallucinationRate (Group A, 규칙 기반):
  - 높을수록 나쁨: 0.0 = 완벽, 1.0 = 최악
  - 컨텍스트 없이도 측정 가능 (ground_truth 기반)
  - 수치 불일치와 미지원 주장 탐지

Faithfulness (LLM Judge, Group G):
  - 높을수록 좋음: 1~5 스케일 (5=완벽하게 충실)
  - 컨텍스트 필수 (RAG의 검색 결과가 context로 전달)
  - 응답의 모든 주장이 컨텍스트에 근거하는지 LLM이 판단

HallucinationRate ≈ 1.0 - (Faithfulness / 5.0) 으로 변환 가능하지만
  측정 메커니즘이 달라 정확히 역상관은 아님 (r ≈ -0.6~-0.75 수준)
```

### I.4.2 Ragas 4지표의 역할 분리

```
RAG 파이프라인:
  [질문] → [검색기(Retriever)] → [컨텍스트] → [생성기(Generator)] → [응답]
               ↑                    ↑                   ↑
           Context Precision    Context Recall      Faithfulness
           Context Recall                        Answer Relevancy

지표별 진단 의미:

Context Precision이 낮음:
  → 검색기가 노이즈(관련 없는 문서)를 많이 가져옴
  → 검색 알고리즘/임베딩 모델 개선 필요

Context Recall이 낮음:
  → 검색기가 필요한 정보를 놓침
  → Top-K 늘리기, 하이브리드 검색 고려

Faithfulness가 낮음:
  → 생성기가 컨텍스트를 무시하고 환각 생성
  → 프롬프트에 "반드시 제공된 정보만 사용" 지시 강화

Answer Relevancy가 낮음:
  → 응답이 질문에 직접 답하지 않음
  → 프롬프트 개선, Few-shot 예시 추가
```

### I.4.3 Ragas vs LLM Judge Faithfulness 선택 기준

| 조건 | 권장 방법 |
|------|----------|
| OpenAI API 키만 있음 | Ragas (LangChain 기반) |
| Anthropic API 키 있음 | LLM Judge (`rag_mode=True`) |
| 외부 의존성 없이 평가 | Group A HallucinationDetector |
| 가장 정밀한 RAG 평가 | Ragas 4지표 모두 |
| 빠른 배포 전 검사 | LLM Judge (`judge_sample_rate=0.1`) |
| 컨텍스트 없는 환경 | Group A 기반만 (Ragas/LLM Judge 모두 context 필요) |

---

## I.5 에이전트 특화 지표 vs 범용 LLM 지표

### I.5.1 왜 정확도만으로 에이전트를 평가할 수 없는가

```
시나리오: "비행기 예약" 에이전트

태스크: "서울→뉴욕 2026-05-15 편도 비즈니스 예약"
에이전트 실행:
  1. search_flights(origin="ICN", dest="JFK", date="2026-05-15")
  2. search_flights(origin="GMP", dest="JFK", date="2026-05-15")  ← 불필요한 반복
  3. filter_by_class(class="business")
  4. get_price(flight_id="KE081")
  5. create_booking(flight_id="KE081", class="business")

최종 응답: "KE081 편 비즈니스 예약 완료. 가격: $3,200"
정답: "예약 완료" (가정)

정확도 (Token F1): 0.85  ← 응답이 정답에 가까움
TCR: 1.0              ← 최종 완료

하지만 에이전트는 불필요한 GMP 검색 (step 2)을 수행했다!
  Tool Call Efficiency: 80% (5번 중 4번이 유효)
  이 비효율이 실제 서비스에서는 응답 시간 +0.5초, API 비용 +20%를 의미한다.
```

**정확도/TCR만 보면**: 에이전트가 "훌륭히 작동"
**Group B-G까지 보면**: 도구 사용 비효율이 포착되고, 반복 개선 방향이 명확해짐

### I.5.2 지표 간 상관관계

실제 에이전트 평가 데이터에서 관찰되는 상관관계:

| 지표 쌍 | 상관계수 | 해석 |
|---------|--------|------|
| TCR ↔ 정확도 | r ≈ 0.72 | 높은 상관 — 완료한 태스크는 대체로 정확함 |
| TCR ↔ 도구 선택 F1 | r ≈ 0.61 | 적절한 도구 선택 → 완료율 증가 |
| 도구 효율 ↔ 지연시간 | r ≈ -0.68 | 도구를 덜 쓸수록 빠름 |
| 재시도율 ↔ 정확도 | r ≈ -0.45 | 재시도 많을수록 정확도 낮음 |
| 환각율 ↔ 응답 품질 | r ≈ -0.58 | 환각이 많을수록 품질 낮음 |
| LLM Judge ↔ 정확도 | r ≈ 0.55 | 중간 상관 (서로 다른 측면 측정) |

**활용**: 상관이 낮은 지표들은 독립적인 정보를 제공하므로 함께 모니터링할 가치가 크다. 예) LLM Judge와 정확도를 모두 보면 "정확하지만 품질이 낮은" 응답을 발견할 수 있다.

---

## I.6 지표 선택 의사결정 트리

```
[시작]
  │
  ▼
배포 기준을 코드로 선언하고 Git에서 추적하고 싶은가?
  │
  ├─ YES → Harness Config 활성화
  │          @agent_eval(monitor, sla=SLAConfig(...), instructions=InstructionConfig(...))
  │          → HarnessEvaluationGate로 Group A-G 전체 배포 판정
  │
  └─ NO  → 기본 Tracker 모드 (지표 측정만, 배포 자동 차단 없음)

  ▼
에이전트가 도구를 사용하는가?
  │
  ├─ NO → Group A 지표 활성 (TCR, Accuracy, Quality, Latency, Token, Hallucination*)
  │         *(hallucination은 RAG 경우에만)
  │
  └─ YES ─→ Group A + Group B 에이전틱 지표 활성 (ToolCall, Workflow, ToolSelection)
              │
              ▼
            에이전트가 민감 데이터/외부 시스템에 접근하는가?
              │
              ├─ NO → Group A + B 지표 유지
              │
              └─ YES → Group E 보안 지표 추가
                          enable_security_metrics=True

[계속]
  │
  ▼
Ground truth를 항상 가질 수 있는가?
  │
  ├─ YES → Group A-F 기반 지표로 충분 (낮은 비용)
  │
  └─ NO → LLM Judge 추가 (Group G)
            │
            ▼
          RAG 파이프라인인가?
            │
            ├─ NO → LLM Judge (5차원) + judge_sample_rate=0.1
            │
            └─ YES → LLM Judge (rag_mode=True, faithfulness 추가)
                       OR Ragas (더 정밀한 RAG 평가 필요 시)

[심화]
  │
  ▼
특정 도메인 기준이 필요한가? (의료, 법률, 금융 등)
  │
  └─ YES → judge_criteria=["domain_accuracy", "citation_quality", ...]
             (G-Eval 스타일 커스텀 기준)

[배포 자동화]
  │
  ▼
지표 선택 완료 후 배포를 자동 차단하려면?
  │
  └─ HarnessEvaluationGate 설정
       Python: gate.evaluate() → {"passed": bool, "violations": [...]}
       CLI:    agent-eval gate result.json --tcr 85 --accuracy 70
```

---

## I.7 지표별 비용 프로파일

### I.7.1 지표당 측정 비용

| 지표 | 처리 시간 | API 비용 | 메모리 |
|------|---------|---------|-------|
| TCR | < 1ms | 없음 | 최소 |
| Accuracy (4지표) | 1~5ms | 없음 | 최소 |
| Response Quality | 2~10ms | 없음 | 최소 |
| Latency 통계 | < 1ms | 없음 | O(n) |
| Token Economy | < 1ms | 없음 | 최소 |
| Hallucination (Group A) | 5~20ms | 없음 | 최소 |
| Tool Call Efficiency | < 1ms | 없음 | 최소 |
| Tool Selection F1 | < 1ms | 없음 | 최소 |
| Agent Coordination | 2~5ms | 없음 | O(nodes) |
| Security (5개) | 10~50ms | 없음 | 최소 |
| LLM Judge (claude-haiku) | 500~1500ms | $0.001~0.003 | 없음 |
| LLM Judge (claude-sonnet) | 800~2000ms | $0.003~0.010 | 없음 |
| DeepEval G-Eval | 1000~3000ms | $0.005~0.020 | 없음 |
| Ragas (4지표) | 2000~8000ms | $0.010~0.050 | 없음 |

### I.7.2 일일 10,000 태스크 기준 월간 비용 추정

| 구성 | 월간 API 비용 | 측정 오버헤드 |
|------|------------|------------|
| Group A-G 기반만 | $0 | < 0.5% |
| Group A-G 기반 + 에이전틱 | $0 | < 1% |
| Group A-G 전체 + LLM Judge (10%) | ~$90 | < 2% |
| Group A-G 전체 + LLM Judge (100%) | ~$900 | 2~5% |
| Group A-G 전체 + Ragas (100%) | ~$1,500~$5,000 | 10~30% |

> 💡 **비용 최적화**: LLM Judge는 10% 샘플링만으로도 전수 평가 대비 90% 비용 절감, 정확도는 5~8%p 차이. 10% 샘플링이 대부분 프로덕션 환경에서 최적의 선택이다.

> **비용 추정 기준**: claude-haiku-4-5-20251001 모델, 태스크당 평균 입력 1,000 토큰 + 출력 300 토큰 기준. claude-sonnet-4-6 사용 시 약 3~5배 증가, gpt-4o-mini 사용 시 유사 수준.

---

## I.8 Agent-Evaluator 25개 Tracker 지표 전체 비교표

| # | 지표 | Group | opt-in | 외부 의존 | 속도 | 비용 | 한국어 지원 | 주요 용도 |
|---|------|-------|--------|----------|------|------|----------|----------|
| 1 | TCR | A | — | 없음 | ⚡ | $0 | ✅ | 핵심 완료율 |
| 2 | 정확도 | A | — | 없음 | ⚡ | $0 | ✅ | 응답 품질 |
| 3 | 응답 품질 | A | — | 없음 | ⚡ | $0 | ✅ | 다차원 품질 |
| 4 | 지연시간 | D | — | 없음 | ⚡ | $0 | N/A | 성능 SLA |
| 5 | 토큰 경제 | D | — | 없음 | ⚡ | $0 | N/A | 비용 추적 |
| 6 | 환각 탐지 | A | ✅ | 없음 | ⚡ | $0 | △ | RAG 품질 |
| 7 | 도구 효율 | B | — | 없음 | ⚡ | $0 | N/A | 도구 패턴 |
| 8 | 재시도·복구 | C | — | 없음 | ⚡ | $0 | N/A | 오류 회복 |
| 9 | 도구 선택 F1 | B | — | 없음 | ⚡ | $0 | N/A | 도구 정확도 |
| 10 | 에이전트 협력 | F | — | 없음 | ⚡ | $0 | N/A | 멀티에이전트 |
| 11 | 워크플로 실행 | B | — | 없음 | ⚡ | $0 | N/A | 프로세스 품질 |
| 12 | 입력 위생화 | E | ✅ | 없음 | ⚡ | $0 | ✅ | 주입 공격 |
| 13 | 출력 누출 | E | ✅ | 없음 | ⚡ | $0 | ✅ | 데이터 보호 |
| 14 | 도구 인가 | E | ✅ | 없음 | ⚡ | $0 | N/A | 권한 관리 |
| 15 | 권한 상승 | E | ✅ | 없음 | ⚡ | $0 | N/A | 보안 위협 |
| 16 | 체인 공격 | E | ✅ | 없음 | ⚡ | $0 | N/A | 복합 공격 |
| 17 | LLM Judge (완결성) | G | ✅ | LLM API | 🐢 | $$ | ✅ | 주관적 품질 |
| 18 | LLM Judge (관련성) | G | ✅ | LLM API | 🐢 | $$ | ✅ | 질문 적합성 |
| 19 | LLM Judge (사실성) | G | ✅ | LLM API | 🐢 | $$ | ✅ | 팩트체크 |
| 20 | LLM Judge (독성) | G | ✅ | LLM API | 🐢 | $$ | ✅ | 안전성 |
| 21 | LLM Judge (편향) | G | ✅ | LLM API | 🐢 | $$ | ✅ | 공정성 |
| 22 | Faithfulness | G | ✅ | LLM API | 🐢 | $$ | ✅ | RAG 충실도 |
| 23 | DeepEval (5지표) | G (외부) | ✅ | OpenAI | 🐢 | $$$ | △ | 외부 검증 |
| 24 | Ragas Faithfulness | G (외부) | ✅ | OpenAI | 🐢 | $$$ | △ | RAG 파이프라인 |
| 25 | Ragas Relevancy 外 | G (외부) | ✅ | OpenAI | 🐢 | $$$ | △ | RAG 검색 평가 |

**opt-in**: `enable_hallucination_detection=True`, `enable_security_metrics=True`, `llm_judge=LLMJudgeConfig()` 등으로 명시 활성화 필요  
**속도**: ⚡ = <50ms, 🐢 = >500ms  
**비용**: $0 = 무료, $$ = 건당 $0.001~0.01, $$$ = 건당 $0.01+

---

*본 Appendix는 Agent-Evaluator v0.8.3 기준이며 외부 서비스 가격은 2025년 기준이다. 최신 가격은 각 서비스 공식 가격표를 참조하라.*
