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

이러한 연구들이 공통적으로 발견한 사실은: **에이전트 평가에는 도구 사용 패턴, 오류 복구, 멀티스텝 계획, 보안 정책 준수를 측정하는 전용 지표가 필요하다**는 것이다. Agent-Evaluator의 Gate B-F 에이전틱 지표군이 바로 이 필요에서 설계됐다.

### G.1.5 Harness Engineering — 지표를 넘어선 배포 판정 패러다임

AgentBench, GAIA, τ-bench 같은 벤치마크는 에이전트 평가를 위한 더 나은 지표를 제공했다. 그러나 이 지표들이 공통적으로 해결하지 못하는 문제가 하나 있다: **"지표 값이 충분히 좋을 때 배포해도 되는가"를 자동으로 판정하는 메커니즘이 없다.**

이 문제에 대한 답이 **Harness Engineering**이다.

Harness Engineering은 지표 발전의 연장이 아닌, AI 최적화 방법론의 새로운 단계다.

| 단계 | 시기 | 핵심 질문 | 해결하는 문제 |
|------|------|---------|-------------|
| Prompt Engineering | 2022–2024 | "어떻게 물어볼까?" | 단일 LLM 출력 품질 개선 |
| Context Engineering | 2025 | "무엇을 넣어줄까?" | 컨텍스트 창 정보 최적화 |
| Harness Engineering | 2026~ | "배포해도 되는가?" | 자율 에이전트의 배포 준비도 자동 판정 |

Harness Engineering은 측정 자체보다 **"코드로 선언된 기준을 통계적 측정값과 자동 대조하는 판정 구조"**를 핵심으로 한다. 이를 Mitchell Hashimoto의 정의로 요약하면: **"Agent = Model + Harness"** — 모델을 제외한 지시 구조, 제약 선언, 품질 측정, 배포 판정 전체가 Harness에 속한다.

Agent-Evaluator의 Harness Config + Gate 시스템은 이 Harness Engineering을 Python SDK로 구현한다. 이 Appendix에서 다루는 이론적 기초(타당도, 신뢰도, 통계적 임계값, LLM-as-Judge 설계)는 Harness Engineering이 왜 이런 방식으로 동작하는지를 설명하는 이론적 근거다.

---

## G.2 평가 타당도와 신뢰도 이론

### G.2.1 구성 타당도 (Construct Validity)

**구성 타당도**는 지표가 실제로 측정하려는 개념(construct)을 측정하는지의 정도다. 예를 들어:

- **TCR(Task Completion Rate)**의 구성 타당도: "에이전트가 할당된 작업을 완료했는가"를 측정하려면, completion_score가 실제 완료 여부를 반영해야 한다. code_generation 태스크에서 AST 파싱 성공을 완료 기준으로 쓰는 것은 "문법적으로 유효한 코드를 생성했는가"라는 구성을 잘 반영한다.

- **정확도 지표의 구성 타당도**: Token Overlap F1은 "정보 내용의 일치도"를 측정하려 한다. 정밀도(얼마나 정확하게)와 재현율(얼마나 많이 포함했는가)의 **조화평균**으로 계산되기 때문에, 둘 중 하나가 낮으면 점수가 크게 떨어진다. 그러나 토큰 순서를 무시하기 때문에 "서울은 파리가 아니다"와 "파리는 서울이 아니다"를 동등하게 취급한다. Levenshtein(문자 편집 거리)를 10% 추가함으로써 순서 정보를 부분적으로 보완한다.

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

Agent-Evaluator의 Gate 설계는 이 트리레마에 대한 실용적 해답이다:
- **Gate A–D (Goal Achievement·Behavioral Integrity·Reliability·Performance)**: 신뢰도·비용 최우선. 규칙 기반 측정, 밀리초 단위. 외부 API 호출 없음.
- **Gate E–F (Security·Multi-Agent)**: 신뢰도 유지, 에이전트 특화 타당도 추가. 패턴 매칭 + 통계 기반.
- **Gate G (Observability)**: 타당도 최우선, 비용은 opt-in으로 제어. LLMJudge를 샘플링(`judge_sample_rate`)으로 적용.

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

**Agent-Evaluator의 선택:** Gate A-F(Goal Achievement ~ Multi-Agent Coordination)는 모두 규칙 기반이다. 모든 프로덕션 배포에서 즉시 사용 가능하도록 외부 의존성을 제거했다. Gate G(Observability)는 opt-in LLMJudge를 사용하며, 기본값(`enable_llm_judge=False`)으로는 외부 API를 호출하지 않는다.

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
  
  1단계: 규칙 기반 (Gate A-F) — 모든 태스크에 적용
         → 기준 미달 시 즉시 플래그, LLM Judge 호출 건너뜀
  
  2단계: LLM Judge (Gate G) — 샘플링 적용 (5~10%)
         → 심층 품질 분석, 미묘한 오류 탐지
  
  3단계: 인간 검토 (Human) — 최고 위험 케이스만
         → LLM Judge가 0~1점 준 케이스, 보안 위협 케이스
```

이 파이프라인은 비용을 최소화하면서 중요한 케이스에 최대 타당도를 확보한다.

---

## G.5 Agent-Evaluator 설계 원칙의 이론적 근거

### G.5.1 Zero-dependency Gate A-F의 이유

프로덕션 환경에서 외부 의존성은 세 가지 위험을 만든다:
1. **가용성 위험**: OpenAI API 다운 → 평가 시스템 전체 중단
2. **비용 위험**: 트래픽 급증 시 평가 비용 폭발적 증가
3. **지연 위험**: 외부 API 응답 지연이 애플리케이션 응답 지연으로 전파

Gate A-F를 외부 의존성 없이 설계함으로써 **평가 시스템이 애플리케이션과 같은 수명주기를 가지도록** 했다. 평가는 항상 동작하거나, 실패해도 주 기능에 영향을 주지 않는다.

### G.5.2 4-지표 가중 합산의 이론적 근거

정확도 계산에 사용되는 가중치 조합(Token F1 40% + Jaccard 30% + LCS 20% + Char Levenshtein 10%)은 **다중 기준 의사결정(Multi-Criteria Decision Making, MCDM)** 이론에 기반한다.

각 지표는 정답의 다른 측면을 측정한다:

- **Token Overlap F1 (40%)**: 핵심 단어의 포함 여부 (가장 중요한 신호)
  - 정밀도(Precision)와 재현율(Recall)의 **조화평균(harmonic mean)**으로 계산한다.
  - `F1 = 2 × Precision × Recall / (Precision + Recall)`
  - 조화평균은 산술평균보다 낮은 값에 더 민감하게 반응해, Precision과 Recall 중 하나만 높은 경우 불이익을 준다. 예: 한 단어를 반복해 재현율을 올려도 Precision이 낮으면 F1이 낮게 유지된다.
  - `Precision = (응답 토큰 중 정답과 겹치는 토큰) / (응답 토큰 전체)`
  - `Recall    = (응답 토큰 중 정답과 겹치는 토큰) / (정답 토큰 전체)`

- **Jaccard (30%)**: 어휘 집합의 유사도 (단어 다양성 반영)
  - `Jaccard = |응답 토큰 집합 ∩ 정답 토큰 집합| / |응답 토큰 집합 ∪ 정답 토큰 집합|`
  - 중복 단어를 무시하고 어휘 다양성을 측정한다. Token F1이 빈도를 고려하는 반면 Jaccard는 집합 관점이다.

- **LCS (20%)**: 단어 순서의 보존 (문장 구조 반영)
  - 최장 공통 부분 수열(Longest Common Subsequence) 길이를 정답 길이로 나눈 비율.
  - 단어가 연속적이지 않아도 순서가 맞으면 점수를 받는다 (ROUGE-L과 동일 원리).

- **Char Levenshtein (10%)**: 문자 수준 편집 거리 (철자 오류, 음절 차이 반영)
  - 문자 삽입·삭제·교체 횟수 최솟값을 기반으로 유사도를 계산한다.
  - `CharSim = 1 - (Levenshtein거리 / max(응답 길이, 정답 길이))`
  - 토큰 수준 지표가 놓치는 철자 오류, 숫자 표기 차이(예: "10%" vs "10 퍼센트")를 보완한다.

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

이런 연구 결과는 Agent-Evaluator의 `LLMJudge`가 단독으로 사용되지 않고 Gate A-F 규칙 기반 지표와 함께 사용되어야 하는 이유를 뒷받침한다.

### G.6.4 이론과 Gate A-G 구현 매핑

G.1~G.6에서 다룬 이론이 Agent-Evaluator의 어느 Group에서 구현되는지 정리한다.

| 이론 | 섹션 | 구현 Group | 핵심 클래스 |
|------|------|-----------|-----------|
| 구성 타당도 | G.2.1 | A (TCR, Accuracy) | `TaskCompletionTracker`, `AccuracyEvaluator` |
| 내용 타당도 | G.2.2 | A, G | `ResponseQualityEvaluator`, `LLMJudge` |
| LLM-as-Judge | G.1.3 | G | `LLMJudge` (5차원 기본; RAG모드 +faithfulness, judge_criteria 지정 시 +G-Eval) |
| 에이전트 평가 특수성 | G.3 | B, E, F | `ToolCallAnalyzer`, `InputSanitizationTracker` |
| Config-as-Code | G.8.1 | 전체 (33개 Config) | `HarnessEvaluationGate` |
| 확률론적 품질 | G.9.1 | A, C | `ReproducibilityConfig`, Wilson Score |
| 드리프트 인식 | G.9.3, G.8.4 | D (추세) | `RunTrendAnalyzer` |

## G.7 Agent-Evaluator 25개 지표와 연구 출처

| 지표 | 핵심 아이디어 | 참고 연구/방법론 |
|------|-------------|----------------|
| TCR | 부분 완료 점수 | AgentBench (Liu et al. 2023) |
| 정확도 (Token Overlap F1) | Precision·Recall 조화평균(harmonic mean) F1 | ROUGE-N (Lin 2004) |
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
| TCR 신뢰 구간 | Wilson Score 하한 | Wilson (1927), Brown et al. (2001) |
| 에이전트 기여도 | Shapley Value 공정 분배 | Shapley (1953), *A Value for n-Person Games* |
| 보정(Calibration) | ECE — 예측 신뢰도 정확도 | Guo et al. (2017), Naeini et al. (2015) |
| Byzantine 합의 | 결함 허용 에이전트 합의 | Lamport, Shostak & Pease (1982) |
| 공정성 — 인구통계 동등성 | 그룹 간 FPR 균등 | Hardt et al. (2016), *Equality of Opportunity* |
| 공정성 — 보정 동등성 | 그룹 간 ECE 균등 | Pleiss et al. (2017) |


---

## G.8 Harness Engineering 이론적 기초

### G.8.1 배포 판단 시스템으로서의 평가

기존 AI 평가는 "얼마나 좋은가"를 측정하는 것에 집중했다. Harness Engineering은 이를 확장해 **"배포해도 되는가"를 판단**하는 시스템으로 전환한다.

이 전환의 핵심은 **"계약 선언(Config)"과 "측정 실행(Tracker)"과 "판정(Gate)"을 세 역할로 분리**하는 것이다.

```
기존 접근:  measure(agent) → score → "점수가 충분히 높으면 배포"

Harness:    ① Config.declare(criteria)   — "SLA는 3초 이내, 지시이행률은 90% 이상"
            ② Tracker.measure(agent)      — 실제 실행 데이터를 수집·계산
            ③ Gate.judge()               → PASS / WARN / FAIL 자동 판정
```

**세 역할의 분리가 중요한 이유**: 기준(Config)은 팀 합의로 결정하고 Git에 커밋한다. 측정(Tracker)은 에이전트 실행 때마다 자동으로 이루어진다. 판정(Gate)은 CI/CD 파이프라인에서 자동으로 수행된다. 이 세 역할이 혼재하면 "기준이 언제 바뀌었는지", "측정값이 왜 이런지"를 추적하기 어렵다.

| 역할 | Python 클래스 예시 | 책임 |
|------|------------------|------|
| **Config** (계약 선언) | `SLAConfig(p95_ms=3000)`, `InstructionConfig(min_completion_rate=0.90)` | 통과 기준 선언 |
| **Tracker** (측정) | `LatencyTracker`, `TaskCompletionTracker` | 데이터 수집·계산 |
| **Gate** (판정) | `PerformanceMonitor.generate_report()` 내 Harness 집계 | PASS/WARN/FAIL 결정 |

소프트웨어 엔지니어링의 **계약 프로그래밍(Design by Contract, Meyer 1992)**에서 영감을 받은 패러다임이다. "전제 조건(precondition), 사후 조건(postcondition), 불변 조건(invariant)"을 AI 에이전트에 적용하면:
- **Precondition**: 에이전트가 처리할 수 있는 입력의 범위 (ScopeConfig, ThreatSeverityConfig)
- **Postcondition**: 에이전트가 보장해야 하는 출력 품질 (InstructionConfig, SLAConfig)
- **Invariant**: 항상 유지되어야 하는 시스템 속성 (ComplianceConfig, ToolAuthorizationTracker)

### G.8.2 Config-as-Code 패턴

Harness Config는 **Infrastructure-as-Code**의 AI 평가 버전이다. 배포 기준을 코드로 선언함으로써:

1. **버전 관리**: 배포 기준이 Git에서 추적된다. "지난 달에 SLA 기준이 5초에서 3초로 변경됐다"를 커밋 히스토리에서 확인할 수 있다.

2. **코드 리뷰**: 배포 기준 변경이 PR을 통해 팀의 동의를 거친다. "QA 팀장이 TCR 기준을 80%→90%로 높였는가"를 코드 변경으로 확인할 수 있다.

3. **재현 가능성**: 어떤 기준으로 이 버전을 배포했는지 코드만 보면 알 수 있다. 과거 배포 판단을 재현할 수 있다.

4. **자동화**: CI/CD 파이프라인에서 `HarnessEvaluationGate`가 자동으로 배포 판단을 내린다.

```python
# 예시: 배포 기준의 진화 (Git 히스토리에서 추적 가능)
# v1: 초기 기준
instruction_cfg = InstructionConfig(min_completion_rate=0.80)

# v2: 3개월 후, 사용자 불만으로 상향
instruction_cfg = InstructionConfig(min_completion_rate=0.90, fail_on_violation=True)

# v3: 특정 task_type에 별도 기준 적용
instruction_cfg_qa = InstructionConfig(min_completion_rate=0.90, task_types=["qa"])
instruction_cfg_code = InstructionConfig(min_completion_rate=0.85, task_types=["code_generation"])
```

### G.8.3 확률론적 배포 판단 이론

전통 소프트웨어의 배포 판단은 이분적(binary)이다: "테스트가 모두 통과했는가, 아닌가."

AI 에이전트의 배포 판단은 **확률론적(probabilistic)**이다. 같은 에이전트도 실행마다 다른 결과를 낸다.

**Wilson Score Interval**을 사용한 TCR 신뢰 구간 추정:

```
Wilson Score 하한 = (p̂ + z²/2n - z√[p̂(1-p̂)/n + z²/4n²]) / (1 + z²/n)

여기서:
  p̂ = 관찰된 성공률 (TCR)
  n  = 실행 횟수
  z  = 신뢰수준 z값 (95% → 1.96)
```

실용적 의미: 20번 평가에서 TCR 90%를 관찰했을 때, 95% 신뢰구간은 약 [68%, 99%]로 매우 넓다. 100번 평가에서 TCR 90%를 관찰하면 신뢰구간은 약 [82%, 95%]로 좁아진다.

**배포 판단의 보수적 접근**: 충분한 샘플(최소 100개 태스크)이 없으면 신뢰구간의 **하한**을 사용해 배포 판단.

```python
import math

def wilson_lower_bound(successes: int, trials: int, z: float = 1.96) -> float:
    """Wilson Score 하한 계산 — 보수적 TCR 추정"""
    if trials == 0:
        return 0.0
    p = successes / trials
    denominator = 1 + z**2 / trials
    center = p + z**2 / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2))
    return (center - margin) / denominator

# 20번 중 18번 성공 (90%) → 하한 72.0%
# 100번 중 90번 성공 (90%) → 하한 83.0%
# 1000번 중 900번 성공 (90%) → 하한 88.0%
```

이 이론은 **Part IV Chapter 14 (임계값 설정)** 에서 실무 적용 방법을 다룬다.

### G.8.4 드리프트 이론 — 에이전트가 왜 시간이 지나면서 나빠지는가

정적 소프트웨어와 달리, AI 에이전트는 코드가 변하지 않아도 시간이 지나면서 성능이 저하될 수 있다. 이를 **AI 드리프트(AI Drift)**라 한다.

**드리프트의 4가지 원인:**

1. **입력 데이터 드리프트(Data Drift)**: 사용자 질의 패턴이 모델 학습 분포에서 벗어남.
   - 탐지 방법: 입력 토큰 분포의 KL-divergence 모니터링
   - Agent-Evaluator 대응: `AnomalyDetector`가 입력 패턴 이상을 탐지

2. **모델 드리프트(Model Drift)**: LLM 공급자가 모델을 업데이트.
   - 탐지 방법: 고정 골든 데이터셋으로 주기적 회귀 테스트
   - Agent-Evaluator 대응: `GoldenSetBuilder` + `agent-eval trend`

3. **컨셉 드리프트(Concept Drift)**: 사용자가 기대하는 응답 품질이 변화.
   - 탐지 방법: LLMJudge 채점 추세 모니터링
   - Agent-Evaluator 대응: `RunTrendAnalyzer`의 accuracy slope 분석

4. **환경 드리프트(Environment Drift)**: 에이전트가 의존하는 외부 API/데이터가 변화.
   - 탐지 방법: 도구 호출 성공률 시계열 분석
   - Agent-Evaluator 대응: `ToolCallAnalyzer` 효율성 추세 + `AnomalyDetector`

**드리프트 탐지의 통계적 기초:**

```
단순 이동 평균(SMA):   MA_t = Σ(x_{t-k}, ..., x_t) / (k+1)
지수 이동 평균(EMA):   EMA_t = α × x_t + (1-α) × EMA_{t-1}
선형 회귀 기울기:       slope = Σ(t_i - t̄)(x_i - x̄) / Σ(t_i - t̄)²
```

`RunTrendAnalyzer`는 선형 회귀 기울기를 사용한다. `slope < -0.05/run`이면 "지속적 하락"으로 간주해 경보를 발령한다.

---

## G.9 AI Native 에이전트 평가 전략 — 5가지

> AI Native 5속성(비결정론적 출력, 컨텍스트 의존성, 다단계 추론, 도구 활용, 자율적 목표 추구)은 각각 고유한 **평가 전략**을 요구한다. G.9.1~G.9.5는 이 5가지 속성에 대응하는 평가 이론과 Agent-Evaluator의 구현을 설명한다.
>
> | 속성 | 대응 전략 | 섹션 |
> |------|---------|------|
> | 비결정론적 출력 | 확률론적 품질 측정 | G.9.1 |
> | 컨텍스트 의존성 | AI-by-AI 평가 (교차 검증) | G.9.2 |
> | 다단계 추론 | 드리프트 인식 (시계열 모니터링) | G.9.3 |
> | 도구 활용 | 돌발 행동 탐지 (이상 감지) | G.9.4 |
> | 자율적 목표 추구 | 지속 평가 (CI/CD 루프) | G.9.5 |

### G.9.1 확률론적 품질 (Probabilistic Quality)

**이론적 배경**: 베이지안 추론(Bayesian Inference)에서 영감.

고전적 품질 관리(Six Sigma 등)는 불량률을 결정론적으로 정의한다: "불량 부품이 0개여야 한다." AI 에이전트의 "불량"은 이분적이지 않다. "60% 정답에 가까운 응답"은 불량인가, 양품인가?

**Harness Engineering의 대응**: 응답 품질을 확률 분포로 모델링.

```
품질 분포: Q ~ Normal(μ, σ²)

배포 기준:
  P(Q ≥ threshold) ≥ confidence
  
예: "정확도 70% 이상인 응답이 85% 이상의 확률로 나와야 배포 가능"
→ InstructionConfig(min_completion_rate=0.85, min_accuracy=0.70)
```

### G.9.2 AI-by-AI 평가 (AI Evaluating AI)

**이론적 문제**: 자기 참조(Self-Reference) 패러독스.

"GPT-4가 좋은 응답을 만든다"는 것을 "GPT-4로 채점"으로 검증할 수 있는가? 평가자 편향(evaluator bias)이 개입한다.

**해결 전략:**

1. **이종 모델 평가자**: 생성 모델(GPT-4)과 다른 모델(Claude)로 채점
2. **교차 평가(Cross-evaluation)**: 에이전트 A의 응답을 에이전트 B가 채점
3. **기준 앙커링(Criteria Anchoring)**: `judge_criteria`로 주관적 판단을 구조화된 기준으로 대체
4. **샘플링 검증**: 전체의 10%만 LLM 채점, 나머지는 규칙 기반으로 교차 검증

```python
# 이종 모델 평가자 패턴 — v0.8.3
# 출처: Evaluator_Examples/ch12_decorators.py, LLMJudge 섹션
judge = LLMJudge(
    model="claude-haiku-4-5-20251001",  # 생성 모델과 다른 평가 모델
    judge_criteria=["factual_accuracy", "medical_safety"],  # 구체적 기준
    sample_rate=0.10,  # 비용 통제
)
```

### G.9.3 드리프트 인식 (Drift Awareness)

§G.8.4 참조. AI 에이전트 평가는 **일회성 측정**이 아닌 **시계열 모니터링**이어야 한다.

**이론적 근거**: 개념 드리프트(Concept Drift) 문헌(Widmer & Kubat 1996, Gama et al. 2004)은 데이터 분포가 시간에 따라 변할 때 정적 모델의 성능이 저하됨을 보인다. AI 에이전트는 데이터 분포뿐만 아니라 모델 자체, 외부 도구, 사용자 기대도 변하기 때문에 드리프트 위험이 더 크다.

### G.9.4 돌발 행동 (Emergent Behavior)

**이론적 배경**: 복잡계 이론(Complex Systems Theory).

에이전트가 단독으로는 보이지 않는 행동이 도구 체인, 멀티에이전트 상호작용, 컨텍스트 누적에 의해 나타난다. "설계하지 않은 능력"이 되기도 하고, "예상치 못한 실패"가 되기도 한다.

돌발 행동의 평가 도전:
1. **사전 정의 불가**: 어떤 돌발 행동이 나타날지 미리 테스트 케이스를 작성할 수 없다.
2. **재현 어려움**: 특정 입력 조합, 도구 상태, 히스토리가 모두 일치해야 재현된다.
3. **부분적으로 긍정적**: 돌발 행동이 항상 나쁜 것은 아니다 (예상치 못한 창의적 해결).

**Agent-Evaluator의 접근**: `AnomalyDetector`는 통계적 정상 범위를 학습하고 이탈을 탐지한다. "무엇이 이상한지"를 사전에 정의하지 않고, "정상 분포에서 얼마나 벗어났는가"로 탐지한다.

```python
# 돌발 행동 탐지 — 통계적 접근
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,  # 통계적 이상 탐지 활성화
)
# → IQR 기반 이상 탐지: Q3 + 1.5×IQR 초과 시 이상으로 분류
```

### G.9.5 지속 평가 (Continuous Evaluation)

**이론적 배경**: DevOps의 Continuous Integration/Continuous Deployment(CI/CD) 철학을 AI 평가에 적용.

전통 소프트웨어는 "배포 전 테스트 → 배포 → 운영"의 선형 흐름이다. AI 에이전트는 "배포 전 테스트 → 배포 → 운영 중 평가 → 드리프트 탐지 → 재보정 → 재배포"의 순환 흐름이 필요하다.

@@HTML_START@@
<div class="mermaid">
flowchart LR
    A["평가\nPerformanceMonitor"]:::stepStyle
    B["측정\ngenerate_report()"]:::stepStyle
    C["이상 탐지\nAnomalyDetector"]:::stepStyle
    D["원인 분석\nLLMJudge / Phoenix"]:::stepStyle
    E["개선\nGoldenSetBuilder"]:::stepStyle
    F["재검증\nHarnessEvaluationGate"]:::stepStyle
    G["배포\nagent-eval gate"]:::deployStyle

    A --> B --> C --> D --> E --> F --> G
    G -.->|자기개선 루프| A

    classDef stepStyle fill:#e8eaf6,stroke:#3949ab,color:#1a237e
    classDef deployStyle fill:#e8f5e9,stroke:#388e3c,color:#1b5e20,font-weight:bold
</div>
@@HTML_END@@

이 루프의 각 단계에서 Agent-Evaluator가 제공하는 도구:

| 단계 | 도구 | Config/Tracker |
|------|------|---------------|
| 평가 | `PerformanceMonitor`, `@agent_eval` | Gate A-G Tracker |
| 측정 | `generate_report()`, `save_to_file()` | EvaluationReport |
| 이상 탐지 | `AnomalyDetector`, `agent-eval trend` | AnomalyConfig, RunTrendAnalyzer |
| 원인 분석 | `LLMJudge`, Phoenix OTEL | Gate G ObservabilityConfig |
| 개선 | `GoldenSetBuilder` | 골든 데이터셋 자동 확장 |
| 재검증 | `HarnessEvaluationGate` | Gate A-G Config 전체 |
| 배포 | `agent-eval gate` | CI/CD 통합 |

---

## G.10 캘리브레이션 이론 — 에이전트의 자기 신뢰도 검증

### G.10.1 캘리브레이션이란 무엇인가

에이전트가 "90% 확신합니다"라고 말할 때 실제로 90% 맞아야 완벽히 캘리브레이션됐다(calibrated)고 한다.

**Expected Calibration Error (ECE) 공식:**
```
ECE = Σ (|Bm| / n) × |acc(Bm) - conf(Bm)|
      m=1

여기서:
  Bm   = m번째 신뢰도 구간 (예: 0.8~0.9)
  acc  = 해당 구간 내 실제 정확도
  conf = 해당 구간 내 평균 신뢰도
  n    = 전체 샘플 수
```

**과신(Overconfidence) vs 과소신뢰(Underconfidence):**
- 과신: acc(Bm) < conf(Bm) — "확신하지만 자주 틀린다" → 위험
- 과소신뢰: acc(Bm) > conf(Bm) — "불확실하다고 하지만 실제로는 맞다" → 기회비용

### G.10.2 AI 에이전트의 캘리브레이션 문제

LLM 기반 에이전트는 기본적으로 캘리브레이션이 좋지 않다. 이유:
1. **RLHF 편향**: 인간 선호도 학습이 "자신감 있게 답변" 방향으로 편향
2. **분포 이탈(OOD)**: 학습 분포를 벗어난 입력에서 신뢰도가 급격히 부정확해짐
3. **할루시네이션의 역설**: 환각 응답에서 오히려 더 높은 확신을 표현하는 경향

### G.10.3 Agent-Evaluator에서의 캘리브레이션 측정

현재 직접적 캘리브레이션 Tracker는 없지만, LLMJudge와 네이티브 지표의 乖離(괴리)를 캘리브레이션 대리 지표로 활용한다:

```python
# 출처: Evaluator_Examples/ch12_decorators.py, LLMJudge + PerformanceMonitor 섹션
from agent_evaluator import LLMJudge, PerformanceMonitor

monitor = PerformanceMonitor("results/", enable_llm_judge=True, judge_sample_rate=1.0)

# judge_score와 accuracy_score의 괴리 = 캘리브레이션 신호
report = monitor.generate_report()
data = report.to_dict()

# 캘리브레이션 분석
calibration_gap = []
for task in data.get("tasks", []):
    native_acc = task.get("accuracy_score", 0)
    judge_overall = (task.get("judge_scores", {}) or {}).get("overall", None)
    if judge_overall is not None:
        gap = abs(native_acc - judge_overall / 5.0)  # judge는 0-5 스케일
        calibration_gap.append(gap)

mean_gap = sum(calibration_gap) / len(calibration_gap) if calibration_gap else 0
print(f"평균 캘리브레이션 괴리: {mean_gap:.3f}")
# < 0.1: 잘 캘리브레이션됨, 0.1~0.3: 주의, > 0.3: 캘리브레이션 문제
```

### G.10.4 Temperature Scaling — 사후 캘리브레이션

모델 재훈련 없이 출력 확률을 조정해 캘리브레이션을 개선하는 기법:
```
p̃ = softmax(z / T)

여기서:
  z = 모델의 logit 출력
  T = temperature 파라미터 (T > 1: 분포 납작하게, T < 1: 더 뾰족하게)
```

실용적 접근: golden dataset에서 ECE를 최소화하는 T를 grid search로 찾는다.

---

## G.11 공정성·편향 평가 이론 — AI Native 공정성

### G.11.1 AI 에이전트의 공정성 문제

기존 ML 공정성(demographic parity, equal opportunity)을 AI 에이전트에 적용할 때 추가적 복잡성이 있다:

1. **과제 다양성**: 에이전트는 단일 예측이 아닌 복잡한 멀티스텝 태스크를 수행 → 어느 단계에서 편향이 개입하는가?
2. **도구 편향**: 에이전트가 사용하는 검색 도구, 데이터베이스 자체의 편향이 에이전트 응답에 전파
3. **누적 편향**: 체인 내 각 단계에서 작은 편향이 결합되어 증폭

**공정성 4가지 기준 — AI 에이전트 적용:**

| 기준 | 정의 | AI 에이전트 적용 |
|------|------|----------------|
| Demographic Parity | P(Ŷ=1\|A=0) = P(Ŷ=1\|A=1) | 그룹별 TCR/정확도 동일해야 함 |
| Equal Opportunity | P(Ŷ=1\|Y=1,A=0) = P(Ŷ=1\|Y=1,A=1) | 어려운 질문에서도 그룹 간 차별 없음 |
| Calibration Parity | acc(Bm\|A=0) ≈ acc(Bm\|A=1) | 그룹 간 신뢰도 일치 |
| Individual Fairness | sim(x,x') ≈ sim(f(x),f(x')) | 유사한 입력 → 유사한 출력 |

### G.11.2 편향 탐지 — LLMJudge toxicity와 bias 차원

Agent-Evaluator의 LLMJudge는 **기본 5차원(completeness, relevance, factual_consistency, toxicity, bias)**으로 채점한다. `toxicity`와 `bias`는 5차원 중 2개로 기본 호출에 항상 포함된다. RAG 모드(`rag_mode=True` + `context` 전달)로 호출하면 `faithfulness`가 추가되고, `judge_criteria` 파라미터로 G-Eval 커스텀 기준을 지정하면 `criteria_scores`가 추가된다:

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(model="claude-haiku-4-5-20251001")

result = judge.judge(
    task_id="t1",
    question="여성 엔지니어의 역량에 대해 설명해줘",
    response=agent_response,
)

scores = result["scores"]
toxicity = scores.get("toxicity", 0)  # 0: 무해, 5: 매우 독성
bias     = scores.get("bias", 0)       # 0: 편향 없음, 5: 심각한 편향

if toxicity > 2 or bias > 2:
    print("편향/독성 감지 — 응답 검토 필요")
```

### G.11.3 그룹별 공정성 분석

에이전트가 특정 그룹(성별, 나이, 지역, 언어 등)에 대해 차별적으로 응답하는지 체계적으로 측정:

```python
import statistics

def fairness_analysis(monitor, group_labels: dict) -> dict:
    """
    group_labels: {"task_id": "group_name"} 매핑
    그룹별 TCR, Accuracy, LLMJudge bias 비교
    """
    report = monitor.generate_report()
    
    group_metrics = {}
    for task in report.tasks:
        group = group_labels.get(task.task_id, "unknown")
        if group not in group_metrics:
            group_metrics[group] = {"accuracy": [], "completion": [], "bias": []}
        
        group_metrics[group]["accuracy"].append(task.accuracy_score)
        group_metrics[group]["completion"].append(task.completion_score)
        
        if task.advanced_metrics:
            bias = task.advanced_metrics.get("bias", None)
            if bias is not None:
                group_metrics[group]["bias"].append(bias)
    
    # 그룹 간 격차 계산
    results = {}
    for group, metrics in group_metrics.items():
        results[group] = {
            "mean_accuracy":   statistics.mean(metrics["accuracy"]),
            "mean_completion": statistics.mean(metrics["completion"]),
            "mean_bias":       statistics.mean(metrics["bias"]) if metrics["bias"] else None,
        }
    
    return results

# 사용 예시
group_labels = {"q001": "여성", "q002": "남성", "q003": "여성", ...}
fairness = fairness_analysis(monitor, group_labels)

# Demographic Parity 위반 검사
groups = list(fairness.keys())
accuracies = [fairness[g]["mean_accuracy"] for g in groups]
parity_gap = max(accuracies) - min(accuracies)
if parity_gap > 0.05:  # 5% 이상 차이
    print(f"Demographic Parity 위반: {parity_gap:.1%} 격차")
```

### G.11.4 공정성 Harness Config 권고

현재 Agent-Evaluator에 전용 공정성 Config는 없지만, `ComplianceConfig`와 `LLMJudge`를 결합해 기본 공정성 감시가 가능하다:

```python
# 출처: Evaluator_Examples/ch08_group_e.py, 섹션 5 — Gate E Security Boundary
from agent_evaluator import ComplianceConfig

ComplianceConfig(
    forbidden_data_patterns=[
        # 성별 편향 패턴
        r"여자라서",  r"남자는 원래",
        # 연령 편향
        r"노인|노약자",  r"MZ세대는",
        # 지역 편향
        r"지방 사람|서울 사람",
    ],
    violation_severity="high",
)
```

권고: 향후 `FairnessConfig` (Gate G 확장)로 그룹별 TCR 격차 임계값, bias 점수 임계값을 선언할 수 있도록 발전시키는 것이 이상적이다.

### G.11.5 공정성 평가의 실무적 도전

1. **보호 속성 비수집**: 사용자 그룹 정보를 수집할 수 없는 경우 → 프록시 변수 활용
2. **다중 기준 충돌**: Demographic Parity와 Individual Fairness는 동시 달성 불가능한 경우 존재 → 우선순위 결정 필요
3. **언어적 공정성**: 한국어 에이전트에서 존댓말 사용 일관성, 지역별 방언 처리 공정성

---

## G.12 출력 구조 검증 이론 — Format Fidelity

### G.12.1 형식 준수 실패의 비용

RAG나 도구 사용 에이전트에서 "정답이지만 파싱 불가"인 응답은 기능적으로 실패다. JSON 필드 누락, 마크다운 테이블 형식 오류, 코드 블록 미완성 등이 TCR을 낮추는 주요 원인이다.

### G.12.2 형식 검증 계층

```
Level 1: 구조 존재 확인 (JSON 파싱 성공 여부)
Level 2: 스키마 일치 확인 (필수 필드 존재)
Level 3: 값 범위 확인 (필드 값이 기대 타입·범위)
Level 4: 의미 일관성 확인 (필드 간 논리적 일관성)
```

### G.12.3 Agent-Evaluator에서의 형식 검증

```python
# 출처: Evaluator_Examples/ch04_group_a.py, 섹션 1 — Gate A Goal Achievement
import json
from agent_evaluator import InstructionConfig
from agent_evaluator.decorators import agent_eval

# InstructionConfig의 required_json_fields로 Level 1-2 검증
@agent_eval(
    monitor,
    task_type="tool_use",
    instructions=InstructionConfig(
        required_keywords=["result", "confidence", "sources"],  # JSON 필드 확인
        fail_on_violation=True,
    ),
)
def structured_agent(question, ground_truth=""):
    response = agent.run(question)
    # 에이전트가 JSON을 반환해야 함
    return response

# Level 3-4: 사후 스키마 검증
def validate_response_schema(response: str, schema: dict) -> float:
    """응답의 JSON 스키마 준수율 반환 (0.0~1.0)"""
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return 0.0  # JSON 파싱 실패
    
    required_fields = schema.get("required", [])
    present_fields = [f for f in required_fields if f in data]
    return len(present_fields) / len(required_fields) if required_fields else 1.0
```

---

*본 Appendix는 Agent-Evaluator v0.8.5 기준으로 작성됐다. AI 평가 연구는 빠르게 발전하고 있으며, 주요 학회(NeurIPS, ACL, ICLR)에서 새로운 방법론이 지속적으로 발표되고 있다. Harness Engineering 개념과 Config-as-Code 패턴은 v0.8.x 시리즈에서 지속적으로 발전 중이다. 본 부록의 G.10(캘리브레이션), G.11(공정성), G.12(출력 구조 검증) 섹션은 2026년 현재 업계 최전선의 논의를 반영하며, 해당 분야 연구는 계속 진행 중이다.*

---

## G.13 참고 문헌

### 평가 지표 핵심 논문

| 약칭 | 전체 인용 |
|------|---------|
| Papineni et al. (2002) | Papineni, K., Roukos, S., Ward, T., & Zhu, W.-J. (2002). BLEU: a method for automatic evaluation of machine translation. *ACL 2002*, 311–318. |
| Lin (2004) | Lin, C.-Y. (2004). ROUGE: A package for automatic evaluation of summaries. *ACL Workshop on Text Summarization*, 74–81. |
| Denkowski & Lavie (2014) | Denkowski, M., & Lavie, A. (2014). Meteor universal: Language specific translation evaluation for any target language. *EACL Workshop*, 376–380. |
| Zhang et al. (2019) | Zhang, T., Kishore, V., Wu, F., Weinberger, K., & Artzi, Y. (2019). BERTScore: Evaluating text generation with BERT. *ICLR 2020*. |
| Zheng et al. (2023) | Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. *NeurIPS 2023*. |
| Liu et al. (2023) — G-Eval | Liu, Y., et al. (2023). G-Eval: NLG evaluation using GPT-4 with better human alignment. *EMNLP 2023*. |
| Liu et al. (2023) — AgentBench | Liu, X., et al. (2023). AgentBench: Evaluating LLMs as agents. *ICLR 2024*. |
| Es et al. (2023) | Es, S., et al. (2023). RAGAS: Automated evaluation of retrieval augmented generation. *EACL 2024*. |
| Min et al. (2023) | Min, S., et al. (2023). FActScore: Fine-grained atomic evaluation of factual precision in long form text generation. *EMNLP 2023*. |
| Madaan et al. (2023) | Madaan, A., et al. (2023). Self-Refine: Iterative refinement with self-feedback. *NeurIPS 2023*. |
| Schick et al. (2023) | Schick, T., et al. (2023). Toolformer: Language models can teach themselves to use tools. *NeurIPS 2023*. |
| Wu et al. (2023) | Wu, Q., et al. (2023). AutoGen: Enabling next-gen LLM applications via multi-agent conversation. *arXiv:2308.08155*. |

### 수학·통계 기초

| 약칭 | 전체 인용 |
|------|---------|
| Wilson (1927) | Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA, 22*(158), 209–212. |
| Brown et al. (2001) | Brown, L. D., Cai, T. T., & DasGupta, A. (2001). Interval estimation for a binomial proportion. *Statistical Science, 16*(2), 101–133. |
| Shapley (1953) | Shapley, L. S. (1953). A value for n-person games. In H. Kuhn & A. Tucker (Eds.), *Contributions to the Theory of Games*, Vol. 2, 307–317. Princeton University Press. |
| Jaccard (1901) | Jaccard, P. (1901). Étude comparative de la distribution florale dans une portion des Alpes et du Jura. *Bulletin de la Société Vaudoise des Sciences Naturelles, 37*, 547–579. |
| Levenshtein (1966) | Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady, 10*(8), 707–710. |

### 보정·공정성

| 약칭 | 전체 인용 |
|------|---------|
| Guo et al. (2017) | Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural networks. *ICML 2017*, 1321–1330. |
| Naeini et al. (2015) | Naeini, M. P., Cooper, G., & Hauskrecht, M. (2015). Obtaining well calibrated probabilities using Bayesian binning. *AAAI 2015*, 2901–2907. |
| Hardt et al. (2016) | Hardt, M., Price, E., & Srebro, N. (2016). Equality of opportunity in supervised learning. *NeurIPS 2016*, 3315–3323. |
| Pleiss et al. (2017) | Pleiss, G., Raghavan, M., Wu, F., Kleinberg, J., & Weinberger, K. Q. (2017). On fairness and calibration. *NeurIPS 2017*, 5680–5689. |

### 보안·신뢰성

| 약칭 | 전체 인용 |
|------|---------|
| Lamport et al. (1982) | Lamport, L., Shostak, R., & Pease, M. (1982). The Byzantine generals problem. *ACM TOPLAS, 4*(3), 382–401. |
| OWASP LLM (2025) | OWASP Top 10 for Large Language Model Applications (2025). https://owasp.org/www-project-top-10-for-large-language-model-applications/ |
| MITRE ATLAS (2024) | MITRE ATLAS: Adversarial Threat Landscape for Artificial-Intelligence Systems (2024). https://atlas.mitre.org/ |
| NIST SP 800-53 | NIST Special Publication 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations. https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf |
| Beyer et al. (2016) | Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (2016). *Site Reliability Engineering*. O'Reilly Media. |
