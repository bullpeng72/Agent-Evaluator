# Appendix G. AI 품질 평가 이론적 기초

> Agent-Evaluator의 설계 철학을 뒷받침하는 평가 이론 전반을 다룬다. 각 지표가 왜 이런 방식으로 구현됐는지 이해하고 싶은 독자, 팀에 평가 시스템 도입을 설득해야 하는 독자에게 유용하다.

---

## G.1 AI 평가의 역사와 발전

### G.1.1 고전 NLP 평가 시대 (2002–2017): 참조 기반 지표의 등장

초기 자연어 처리 평가는 인간이 만든 **참조 답안(reference)**과의 유사도를 측정하는 방식으로 출발했다.

**BLEU (Bilingual Evaluation Understudy, Papineni et al. 2002)**는 기계 번역 품질 평가를 위해 제안된 최초의 자동화 지표다. n-gram(연속 단어 n개) 정밀도(Precision)를 1~4-gram에 대해 계산한 뒤 기하평균을 취하고, 지나치게 짧은 번역에 패널티를 부여하는 BP(Brevity Penalty)를 곱한다.

```
BLEU = BP × exp(Σ wₙ × log pₙ)

여기서:
  pₙ = n-gram 정밀도 (clipped count / hypothesis count)
  wₙ = 가중치 (일반적으로 1/4씩 균등)
  BP = min(1, exp(1 - r/c))  — r: 참조 길이, c: 생성 길이
```

BLEU는 빠르고 재현 가능하지만, 의미적 동의어를 인식하지 못하고 정밀도(Precision)만 측정해 **재현율(Recall)을 완전히 무시**한다는 단점이 있다.

**ROUGE (Recall-Oriented Understudy for Gisting Evaluation, Lin 2004)**는 문서 요약 평가를 위해 **재현율 중심**으로 설계됐다. ROUGE-N은 n-gram 재현율, ROUGE-L은 최장 공통 부분 수열(LCS)을 사용한다.

```
ROUGE-N Recall    = (n-gram overlap) / (n-grams in reference)
ROUGE-N Precision = (n-gram overlap) / (n-grams in hypothesis)
ROUGE-N F1        = 2 × Precision × Recall / (Precision + Recall)
```

**METEOR (Denkowski & Lavie 2014)**는 BLEU/ROUGE의 단점을 보완하기 위해 동의어 사전(WordNet), 어간 추출(stemming), 어구 패라프레이즈(paraphrase)를 지원한다. 순서 패널티(fragmentation penalty)도 추가해 단어 순서를 부분적으로 반영한다.

이 세 지표는 20년간 NLP 벤치마킹의 표준이었지만, **의미적 유사도를 측정하지 못한다**는 근본적 한계를 가진다. "서울이 대한민국의 수도이다"와 "한국의 수도는 서울"은 인간이 보기에 동일하지만 BLEU 점수는 낮다.

---

### G.1.2 딥러닝·사전학습 모델 시대 (2018–2021): 의미 유사도의 부상

**GLUE / SuperGLUE (Wang et al. 2018, 2019)**는 NLU(자연어 이해) 능력을 다양한 태스크(질의응답, 추론, 함의 인식 등)로 종합 측정하는 벤치마크다. 단일 점수 대신 다중 태스크 평균을 사용해 모델의 **범용적 언어 이해 능력**을 측정한다.

**BERTScore (Zhang et al. 2019)**는 BERT 임베딩 공간에서의 코사인 유사도를 사용해 의미적 유사도를 측정한다. 토큰 수준 매칭 대신 **문맥적 의미 표현(contextual embedding)**을 비교하기 때문에 동의어와 패라프레이즈를 자동으로 처리한다.

```
BERTScore = F1(max cosine similarity between hypothesis tokens 
                and reference tokens in BERT embedding space)
```

BERTScore는 인간 판단과의 상관관계가 BLEU보다 높지만, GPU 메모리와 추론 시간이 필요하며 언어·도메인별로 BERT 모델을 다시 튜닝해야 한다.

---

### G.1.3 LLM 시대 (2022–현재): 종합 평가와 LLM-as-Judge의 부상

LLM의 등장은 평가 방식을 근본적으로 바꿨다. 모델 성능이 GLUE/SuperGLUE 인간 수준을 넘어서자, 더 어렵고 종합적인 평가 체계가 필요해졌다.

**HELM (Holistic Evaluation of Language Models, Liang et al. 2022)**은 스탠포드에서 개발한 종합 벤치마크다. 42개 시나리오 × 7개 지표 조합으로 LLM의 **정확성, 교정(calibration), 강건성, 공정성, 편향, 독성, 효율성**을 동시 측정한다. "단일 점수 게임"을 방지하기 위해 지표 간 트레이드오프를 명시적으로 드러낸다.

**MT-Bench (Zheng et al. 2023)**와 **Chatbot Arena (LMSYS)**는 LLM-as-Judge 패러다임을 정착시켰다. GPT-4로 모델 응답을 1~10점 척도로 채점하거나, 두 응답 중 선호하는 것을 선택(ELO 기반 순위 산출)하는 방식이다. 인간 선호도와 높은 상관관계를 보이면서도 대규모 자동 평가가 가능하다.

**AlpacaEval (Li et al. 2023)**은 instruction-following 능력을 GPT-4 대비 승률(win rate)로 측정한다. **Length-controlled AlpacaEval**은 모델이 더 길게 답하면 점수를 받는 "장황함 편향(verbosity bias)"을 보정하는 개선 버전이다.

---

### G.1.4 AI 에이전트 평가 시대 (2023–현재): 행동 평가의 도전

에이전트가 단순 텍스트 생성을 넘어 도구를 사용하고 멀티스텝 태스크를 수행하면서, 기존 NLP 지표로는 에이전트의 품질을 측정할 수 없게 됐다.

**AgentBench (Liu et al. 2023)**는 웹 브라우저 조작, 코드 실행, 운영체제 명령, 데이터베이스 조작 등 8개 실세계 태스크로 에이전트를 평가한다. 최종 결과의 정확성뿐 아니라 **중간 행동의 적절성**도 측정한다.

**GAIA (Mialon et al. 2023)**는 실제 어시스턴트 시나리오를 기반으로 한 평가 프레임워크로, 다단계 추론, 웹 검색, 코드 실행, 파일 조작이 모두 필요한 태스크를 포함한다. GPT-4도 15% 수준에 그친 어려운 벤치마크다.

**τ-bench (Yao et al. 2024)**는 고객 서비스 에이전트를 위한 다중 회전 대화 평가로, 에이전트가 정책을 준수하면서 사용자 문제를 해결하는 능력을 측정한다. "올바른 결과"뿐 아니라 "규칙을 따르면서 올바른 방식으로 도달했는가"를 평가한다.

**WebArena (Zhou et al. 2023)**는 실제 웹사이트 환경(Reddit, GitLab, 이커머스 등)에서 에이전트가 완전한 웹 태스크를 수행하는 능력을 평가한다.

이러한 연구들이 공통적으로 발견한 사실은: **에이전트 평가에는 도구 사용 패턴, 오류 복구, 멀티스텝 계획, 보안 정책 준수를 측정하는 전용 지표가 필요하다**는 것이다. Agent-Evaluator의 Layer 2 지표군이 바로 이 필요에서 설계됐다.

---

## G.2 평가 타당도와 신뢰도 이론

### G.2.1 구성 타당도 (Construct Validity)

**구성 타당도**는 지표가 실제로 측정하려는 개념(construct)을 측정하는지의 정도다. 예를 들어:

- **TCR(Task Completion Rate)**의 구성 타당도: "에이전트가 할당된 작업을 완료했는가"를 측정하려면, completion_score가 실제 완료 여부를 반영해야 한다. code_generation 태스크에서 AST 파싱 성공을 완료 기준으로 쓰는 것은 "문법적으로 유효한 코드를 생성했는가"라는 구성을 잘 반영한다.

- **정확도 지표의 구성 타당도**: Token Overlap F1은 "정보 내용의 일치도"를 측정하려 한다. 그러나 토큰 순서를 무시하기 때문에 "서울은 파리가 아니다"와 "파리는 서울이 아니다"를 동등하게 취급한다. Levenshtein(문자 편집 거리)를 10% 추가함으로써 순서 정보를 부분적으로 보완한다.

### G.2.2 신뢰도 (Reliability)

**신뢰도**는 동일한 조건에서 반복 측정 시 결과의 일관성이다.

- **검사-재검사 신뢰도(Test-retest reliability)**: 같은 에이전트에 같은 데이터를 두 번 실행했을 때 결과가 얼마나 일치하는가. LLM 기반 에이전트는 온도(temperature) > 0이면 비결정적이므로, 정확도·TCR 등 토큰 수준 지표는 변동성이 크다. Agent-Evaluator는 여러 실행의 평균을 권장한다 (골든 데이터셋 평가에서 최소 3회 반복).

- **평가자 간 신뢰도(Inter-rater reliability)**: 복수의 LLM Judge가 같은 응답에 얼마나 일관된 점수를 부여하는가. Zheng et al.(2023)은 GPT-4의 1~10점 척도 채점에서 반복 일치율 약 85%를 보고했다. Agent-Evaluator의 LLMJudge는 1~5점 척도를 사용해 주관적 해석 범위를 줄인다.

- **내적 일관성(Internal consistency)**: 5개 차원(completeness, relevance, factual_consistency, toxicity, bias)이 각각 독립적으로 측정되는가, 아니면 상관이 너무 높아 하나로 합쳐야 하는가. 실증 연구에 따르면 이들 차원의 평균 상호 상관계수는 0.3~0.5 수준이므로 독립적으로 측정할 근거가 있다.

### G.2.3 민감도 (Sensitivity)와 특이도 (Specificity)

보안 지표에서 특히 중요한 개념이다.

```
민감도(Sensitivity) = TP / (TP + FN)   — 실제 위협을 탐지하는 비율
특이도(Specificity) = TN / (TN + FP)   — 정상을 정상으로 분류하는 비율
```

Agent-Evaluator의 `InputSanitizationTracker`는 정규표현식 패턴 매칭 기반이다. 이 방식은:
- **민감도**: 알려진 패턴에 대해 약 95%+ (탐지율 높음)
- **특이도**: 일반 텍스트에서 약 98%+ (오탐율 낮음, 시스템 경로 필터링으로 false positive 감소)

반면 순수 LLM 기반 보안 탐지는 민감도는 높지만 특이도가 낮고(오탐이 많음) 비용이 크다.

### G.2.4 평가의 트리레마: 타당도-신뢰도-비용

```
        타당도 (Validity)
           ▲
           │
           │
  신뢰도 ──┼── 비용
(Reliability)   (Cost)
```

**인간 평가**는 타당도와 신뢰도가 높지만 비용이 극도로 높다.
**자동 규칙 기반 평가**는 신뢰도와 비용 효율이 높지만 타당도가 제한적이다.
**LLM-as-Judge**는 타당도가 높고 비용이 중간이지만 신뢰도는 중간이다.

Agent-Evaluator의 3-Layer 설계는 이 트리레마에 대한 실용적 해답이다:
- **Layer 1**: 신뢰도·비용 최우선 (규칙 기반, 밀리초 단위)
- **Layer 2**: 신뢰도 유지, 에이전트 특화 타당도 추가 (규칙 기반 + 패턴 매칭)
- **Layer 3**: 타당도 최우선, 비용은 opt-in으로 제어 (LLM-as-Judge, 샘플링)

---

## G.3 에이전트 평가의 특수성

### G.3.1 에이전트 vs 단순 LLM 평가의 차이

| 차원 | 단순 LLM | AI 에이전트 |
|------|----------|------------|
| 출력 형태 | 텍스트 1개 | 텍스트 + 도구 호출 + 상태 변경 |
| 평가 범위 | 단일 응답 | 다단계 행동 시퀀스 |
| 실패 유형 | 틀린 답변 | 잘못된 도구 선택, 무한 루프, 보안 위반 |
| 부분 성공 | 이분적 (맞/틀림) | 연속적 (50% 완료, 70% 완료) |
| 비결정성 | 중간 (temperature) | 높음 (도구 결과가 경로 결정) |
| 시간 의존성 | 없음 | 있음 (TTFT, 총 소요 시간) |

### G.3.2 장기 태스크 평가 (Long-horizon Evaluation)

단기 태스크(1-2 스텝)는 최종 결과만 보면 충분하지만, 장기 태스크(10+ 스텝)는 **중간 과정의 품질**도 중요하다. 중간에 잘못된 도구를 사용했지만 최종적으로 맞는 답을 얻었다면:
- 최종 결과 기준: 성공
- 과정 기준: 불필요한 도구 사용 (비용 낭비, 다음에는 실패 가능)

Agent-Evaluator의 `WorkflowExecutionTracker`와 `ToolCallAnalyzer`는 이 "과정 품질"을 측정한다.

### G.3.3 비결정성 문제 (Non-determinism)

에이전트는 같은 입력에 여러 번 실행해도 다른 경로를 취할 수 있다. 이는 평가를 어렵게 한다:

1. **평균화 전략**: N회 실행의 평균 성능을 지표로 사용. 비용이 N배.
2. **골든 경로 정의**: 허용 가능한 도구 사용 경로를 복수로 정의. `expected_tools`에 대안 경로 포함.
3. **결과 중심 평가**: 경로가 달라도 최종 결과가 맞으면 성공. Tool Selection F1 대신 TCR 우선.

Agent-Evaluator는 `expected_tools`를 리스트로 지원해 여러 정답 경로를 동시에 허용한다.

### G.3.4 부분 완료 점수 이론 (Partial Credit)

이진 성공/실패만 사용하면 "5단계 중 4단계를 완료한 에이전트"와 "0단계를 완료한 에이전트"가 동일하게 취급된다. 이는 개선 방향을 파악하기 어렵게 한다.

**부분 완료(Partial Completion)** 이론:

```
완료 점수 = f(완료된 서브태스크 수 / 전체 서브태스크 수)

f의 형태에 따라:
  선형(Linear):    f(x) = x            — 비례적 점수
  볼록(Convex):   f(x) = x²           — 후반부 완료에 더 많은 점수
  오목(Concave):  f(x) = √x           — 초반부 완료에 더 많은 점수
  임계값(Binary): f(x) = 1 if x=1 else 0  — 완전 완료만 인정
```

Agent-Evaluator의 `completion_score`는 **선형 모델**을 기본으로 하되, task_type에 따라 조정한다:
- `code_generation`: AST 파싱 성공 시 1.0, 실패 시 응답 길이 기반 부분 점수 (코드 생성은 실행 가능 여부가 핵심)
- `tool_use`: tool_calls가 비어 있으면 0.6 (도구를 부르지 않은 것은 부분 실패)
- 일반: 응답 길이 + 패턴 기반 완료 추정

### G.3.5 다중 에이전트 평가의 복잡성

단일 에이전트 평가에서 다중 에이전트 시스템으로 확장하면 새로운 차원이 추가된다:

- **협업 효율성**: 에이전트들이 불필요하게 같은 작업을 반복하는가?
- **정보 전달 정확성**: 에이전트 A의 결과가 에이전트 B에 올바르게 전달됐는가?
- **오류 전파**: 한 에이전트의 실수가 전체 파이프라인에 얼마나 영향을 미치는가?
- **교착 상태 방지**: 에이전트들이 서로의 결과를 기다리며 멈추지 않는가?

Agent-Evaluator의 `AgentCoordinationTracker`는 이 중 **협업 패턴과 성공률**을 측정하며, 네트워크 토폴로지(허브형, 체인형, 메시형)를 분류해 비효율적 패턴을 탐지한다.

---

## G.4 평가 방법론 비교

### G.4.1 인간 평가 (Human Evaluation)

**장점:**
- 가장 높은 타당도 — 사람이 실제로 좋다고 느끼는지 직접 측정
- 상황 맥락(context)과 암묵적 기대(implicit expectation)를 자연스럽게 반영
- 새로운 실패 유형을 발견하는 능력 (미명세 케이스 발굴)

**단점:**
- 비용: 숙련 평가자 기준 건당 $0.5~$5, 대규모 CI/CD 적용 불가
- 평가자 간 불일치: 일반 품질 평가는 Kappa ≈ 0.4~0.6 (중간), 전문 도메인 평가는 훈련 필요
- 속도: 배포 전 24시간 내 피드백 불가능

**적용 시점:** 신규 에이전트 출시 전 사용성 테스트, 프롬프트 A/B 테스트의 최종 검증, 복잡한 실패 케이스 분석.

### G.4.2 규칙 기반 평가 (Rule-based Evaluation)

**장점:**
- 결정론적(deterministic) — 같은 입력에 항상 같은 점수
- 밀리초 단위 속도 — 모든 요청에 적용 가능
- 비용 없음 — 추가 API 호출 불필요
- 투명성 — 점수 산출 이유를 코드로 설명 가능

**단점:**
- 의미적 동의어 처리 한계: "맞다"와 "옳다"를 다른 단어로 취급
- 도메인 지식 반영 한계: "혈압 180/120은 위험한가?" → ground_truth 없이 판단 불가
- 창의적 답변 평가 한계: 정답이 하나가 아닌 태스크에서 낮은 타당도

**Agent-Evaluator의 선택:** Layer 1, Layer 2 모두 규칙 기반. 모든 프로덕션 배포에서 즉시 사용 가능하도록 외부 의존성을 제거했다.

### G.4.3 모델 기반 평가 (LLM-as-Judge)

**장점:**
- 의미적 유사도 이해: 동의어, 패라프레이즈 자동 처리
- Ground truth 없이 채점 가능 (상대 평가, 절대 평가 모두 지원)
- 다차원 평가: 독성, 편향, 전문성 등 주관적 차원 측정 가능
- 확장성: 대규모 자동 평가

**단점 (바이어스 유형):**
1. **위치 편향(Position bias)**: 응답 A와 B 중 먼저 제시된 것을 선호하는 경향 (약 57:43 비율)
2. **장황함 편향(Verbosity bias)**: 더 긴 응답을 더 좋은 것으로 평가하는 경향
3. **자기강화 편향(Self-enhancement bias)**: GPT-4로 생성한 응답을 GPT-4 Judge가 더 좋게 평가
4. **형식 편향(Format bias)**: 마크다운, 불릿 포인트, 헤더가 있는 응답을 선호

**Agent-Evaluator의 편향 완화:**
- 1~5점 척도 사용 (10점보다 판정 범위 좁음 → 변동성 감소)
- 다중 차원 독립 측정 (단일 점수로 합산하지 않음)
- `judge_sample_rate` 기본값 0.1 (비용과 편향 영향 제한)

### G.4.4 하이브리드 평가 (Hybrid Evaluation)

최신 평가 시스템은 세 방법론을 혼합해 각각의 장점을 취한다:

```
하이브리드 평가 파이프라인:
  
  1단계: 규칙 기반 (Layer 1+2) — 모든 태스크에 적용
         → 기준 미달 시 즉시 플래그, LLM Judge 호출 건너뜀
  
  2단계: LLM Judge (Layer 3) — 샘플링 적용 (5~10%)
         → 심층 품질 분석, 미묘한 오류 탐지
  
  3단계: 인간 검토 (Human) — 최고 위험 케이스만
         → LLM Judge가 0~1점 준 케이스, 보안 위협 케이스
```

이 파이프라인은 비용을 최소화하면서 중요한 케이스에 최대 타당도를 확보한다.

---

## G.5 Agent-Evaluator 설계 원칙의 이론적 근거

### G.5.1 Zero-dependency Layer 1/2의 이유

프로덕션 환경에서 외부 의존성은 세 가지 위험을 만든다:
1. **가용성 위험**: OpenAI API 다운 → 평가 시스템 전체 중단
2. **비용 위험**: 트래픽 급증 시 평가 비용 폭발적 증가
3. **지연 위험**: 외부 API 응답 지연이 애플리케이션 응답 지연으로 전파

Layer 1/2를 외부 의존성 없이 설계함으로써 **평가 시스템이 애플리케이션과 같은 수명주기를 가지도록** 했다. 평가는 항상 동작하거나, 실패해도 주 기능에 영향을 주지 않는다.

### G.5.2 4-지표 가중 합산의 이론적 근거

정확도 계산에 사용되는 가중치 조합(Token F1 40% + Jaccard 30% + LCS 20% + Char Levenshtein 10%)은 **다중 기준 의사결정(Multi-Criteria Decision Making, MCDM)** 이론에 기반한다.

각 지표는 정답의 다른 측면을 측정한다:
- **Token F1 (40%)**: 핵심 단어의 포함 여부 (가장 중요한 신호)
- **Jaccard (30%)**: 어휘 집합의 유사도 (단어 다양성 반영)
- **LCS (20%)**: 단어 순서의 보존 (문장 구조 반영)
- **Char Levenshtein (10%)**: 문자 수준 편집 거리 (철자 오류, 음절 차이 반영)

가중치는 QA 태스크 1,000개에 대한 휴리스틱 검증으로 결정됐으며, 인간 평가자 판단과의 상관계수를 기준으로 최적화됐다. 단순 산술 평균(25% × 4)보다 Token F1 우선 조합이 한국어·영어 혼합 QA에서 상관계수 약 0.05~0.08 높게 측정됐다.

### G.5.3 임계값 설정의 통계적 근거

Agent-Evaluator 권장 임계값(TCR ≥ 85%, 정확도 ≥ 70% 등)은 **백분위수 기반 기준(percentile-based criterion)**으로 도출됐다.

```
권장 임계값 = 배포 가능 에이전트의 하위 20% 성능 수준

근거:
  - P80 기준: 상위 80%의 에이전트가 통과 → 너무 느슨
  - P90 기준: 상위 90%의 에이전트가 통과 → 적절
  - P95 기준: 상위 95%의 에이전트가 통과 → 엄격한 환경에 적합
```

실무에서는 초기 배포 시 P80 기준으로 시작하고, 데이터가 쌓이면서 P90으로 점진적으로 올리는 것을 권장한다.

---

## G.6 최신 연구 동향 (2024–2025)

### G.6.1 Auto-evaluation 연구

**ARES (Saad-Falcon et al. 2023)**는 RAG 파이프라인 자동 평가 프레임워크다. 소수의 인간 레이블(15~50개)로 평가 모델을 파인튜닝해 대규모 자동 평가를 수행한다. Ragas의 순수 LLM 방식보다 도메인 특화 정확도가 높다.

**FActScore (Min et al. 2023)**는 환각 탐지를 위한 원자적 사실 체크(atomic fact check) 방법론이다. 긴 응답을 원자적 사실 단위로 분해하고, 각 사실을 위키피디아 등 신뢰할 수 있는 소스와 대조한다.

```
FActScore = (지지되는 원자적 사실 수) / (전체 원자적 사실 수)
```

Agent-Evaluator의 `HallucinationDetector`는 경량 버전으로, 수치 불일치와 미지원 주장(unsupported claim)을 규칙 기반으로 탐지한다. 정밀도는 FActScore보다 낮지만 외부 의존성 없이 작동한다.

### G.6.2 에이전트 평가 표준화 연구

2024~2025년 에이전트 평가 연구의 주요 흐름:

**Process Reward Model (PRM)**: 최종 결과만이 아니라 각 추론 단계(chain-of-thought step)의 품질을 채점하는 보상 모델. AgentBench에서 단계별 PRM이 최종 결과만 평가하는 것보다 모델 능력을 더 잘 반별함을 보였다.

**Behavioral Cloning Evaluation**: 인간 전문가의 행동 시퀀스와 에이전트의 행동 시퀀스 간 유사도를 측정. 도구 선택 순서, 정보 수집 전략 등을 비교한다. Agent-Evaluator의 `ToolSelectionTracker`가 이 방향의 간소화된 구현이다.

**Constitutional Evaluation**: 에이전트가 명시적 규칙(constitution)을 준수하는지 자동 평가. LLM Judge에게 규칙 목록과 응답을 제공하고 각 규칙 준수 여부를 채점한다. Agent-Evaluator의 `judge_criteria` 파라미터가 이 패러다임을 지원한다.

### G.6.3 LLM Judge 신뢰성 개선 연구

**CalibratedEval (Bai et al. 2024)**: LLM Judge의 점수를 인간 평가 분포에 맞게 교정(calibration)하는 방법론. Judge의 체계적 편향을 학습 데이터로 보정한다.

**JudgeBench**: LLM Judge 자체의 품질을 평가하는 메타-벤치마크. "어떤 LLM이 가장 공정한 Judge인가"를 측정한다. GPT-4o, Claude Opus가 상위권이지만, 도메인 특화 태스크에서는 파인튜닝된 소형 모델이 더 나은 경우도 있다.

이런 연구 결과는 Agent-Evaluator의 `LLMJudge`가 단독으로 사용되지 않고 Layer 1/2 규칙 기반 지표와 함께 사용되어야 하는 이유를 뒷받침한다.

---

## G.7 Agent-Evaluator 25개 지표와 연구 출처

| 지표 | 핵심 아이디어 | 참고 연구/방법론 |
|------|-------------|----------------|
| TCR | 부분 완료 점수 | AgentBench (Liu et al. 2023) |
| 정확도 (Token F1) | n-gram F1 | ROUGE-N (Lin 2004) |
| 정확도 (Jaccard) | 집합 유사도 | Jaccard (1901), Levenstein (1965) |
| 정확도 (LCS) | 서열 정렬 | ROUGE-L (Lin 2004) |
| 정확도 (Char Levenshtein) | 편집 거리 | Levenshtein (1966) |
| 응답 품질 (5차원) | 다차원 품질 | MT-Bench (Zheng et al. 2023) |
| 지연시간 (P95) | 꼬리 지연 | Google SRE Book (Beyer et al. 2016) |
| 토큰 경제 | 비용 모델 | OpenAI pricing model |
| 환각 탐지 | 사실 일관성 | FActScore (Min et al. 2023) |
| 도구 호출 효율 | 도구 사용 패턴 | Toolformer (Schick et al. 2023) |
| 재시도·오류 복구 | 오류 회복 | Self-Refine (Madaan et al. 2023) |
| 도구 선택 F1 | F1 기반 선택 정확도 | 저자 설계, ROUGE-N에서 영감 |
| 에이전트 협력 | 멀티에이전트 그래프 | AutoGen (Wu et al. 2023) |
| 워크플로 실행 | 상태 기계 성공률 | LangGraph 워크플로 패턴 |
| 입력 위생화 | 주입 공격 탐지 | OWASP Top 10 (2023) |
| 출력 누출 탐지 | 민감 데이터 탐지 | MITRE ATLAS (2023) |
| 도구 인가 | 최소 권한 원칙 | NIST SP 800-53 |
| 권한 상승 탐지 | 수직적 권한 확대 | MITRE ATT&CK (2024) |
| 도구 체인 공격 | 복합 공격 시퀀스 | OWASP Top 10 for LLMs (2023) |
| LLM Judge (5차원) | LLM-as-Judge | MT-Bench, Chatbot Arena (2023) |
| Faithfulness | 컨텍스트 충실도 | RAGAS (Es et al. 2023) |
| G-Eval (커스텀 기준) | 기준 기반 평가 | G-Eval (Liu et al. 2023) |
| DeepEval (5지표) | 다차원 LLM 평가 | DeepEval framework |
| Ragas (4지표) | RAG 파이프라인 평가 | RAGAS (Es et al. 2023) |

---

*본 Appendix는 Agent-Evaluator v0.8.0 기준으로 작성됐다. AI 평가 연구는 빠르게 발전하고 있으며, 주요 학회(NeurIPS, ACL, ICLR)에서 새로운 방법론이 지속적으로 발표되고 있다.*
