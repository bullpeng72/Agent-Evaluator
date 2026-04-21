# Chapter 01: AI 에이전트 평가란 무엇인가

> "측정할 수 없으면 개선할 수 없다." — Peter Drucker

---

## 1.1 LLM과 에이전트의 차이 — 왜 평가 방식이 다른가

LLM(Large Language Model)을 API로 호출하는 것과 AI 에이전트를 운영하는 것은 근본적으로 다른 문제입니다. 겉으로는 비슷해 보이지만, 내부 동작 방식과 실패 패턴이 전혀 다릅니다.

### 단순 LLM 호출: 입력 → 출력 1회

```python
# 단순 LLM 호출 — 평가가 상대적으로 간단하다
response = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "한국의 수도는?"}]
)
answer = response.choices[0].message.content
# → "서울입니다."
```

이 흐름은 결정론적에 가깝습니다. 입력이 고정되면 출력도 거의 고정됩니다(온도=0일 때). 정확성 평가는 `answer == "서울"` 수준의 비교로 충분할 때가 많습니다.

### 에이전트: 도구 호출 + 멀티스텝 + 상태 + 반복

에이전트는 다릅니다. 동일한 질문에 대해 에이전트는 다음과 같이 동작할 수 있습니다.

```
사용자: "서울의 내일 날씨를 조사해서 여행 계획을 짜줘"

에이전트 실행 흐름:
  Step 1: search_weather("서울", "내일") 도구 호출
  Step 2: 날씨 데이터 수신 → 맑음, 최고 22°C
  Step 3: get_attractions("서울", weather="맑음") 도구 호출
  Step 4: 관광지 목록 수신 → 경복궁, 북촌한옥마을, 남산타워
  Step 5: 계획 생성 → "오전 경복궁, 오후 북촌..."
  (→ 실패 시 Step 1 재시도 또는 다른 도구 선택)
```

이 흐름에서 발생하는 평가 대상은 최종 답변 하나가 아닙니다.

- **도구 선택의 정확성**: `search_weather` 대신 `wikipedia_search`를 선택했다면?
- **도구 사용 효율성**: 불필요한 도구를 5번 더 호출했다면?
- **재시도 동작**: 첫 번째 도구 호출이 실패했을 때 적절히 자기수정했는가?
- **멀티에이전트 협업**: 날씨 에이전트와 관광 에이전트가 올바르게 협력했는가?
- **보안**: 사용자 입력에 숨겨진 프롬프트 인젝션 공격을 탐지했는가?
- **비용**: 목표를 달성하는 데 토큰을 얼마나 사용했는가?

**결정론적 vs 확률론적 동작**이라는 차이도 있습니다. LLM은 동일 입력에 대해 비슷한 출력을 생성하지만, 에이전트는 도구 응답, 외부 상태, 실행 시점의 컨텍스트에 따라 완전히 다른 실행 경로를 택할 수 있습니다. 이는 재현 가능한 테스트를 작성하기 어렵게 만들고, 통계적 접근이 필요한 이유가 됩니다.

> 📋 **QA 관리자 TIP**: 에이전트 테스트는 "이 케이스가 통과했는가"가 아니라 "이 에이전트가 충분히 높은 성공률을 보이는가"로 기준을 바꿔야 합니다. 단일 테스트 케이스 통과가 아닌, 통계적 품질 임계값 관리가 핵심입니다.

---

## 1.2 프로덕션에서 발생하는 품질 위기 — 실제 사례 3가지

### 사례 1: 환각으로 인한 잘못된 정보 제공

의료 정보 서비스에 배포된 RAG(Retrieval-Augmented Generation) 에이전트가 있었습니다. 에이전트는 사용자의 약 관련 질문에 유사하지만 다른 약의 복용량 정보를 자신감 있게 답변했습니다. 검색된 문서에는 올바른 정보가 있었지만, 에이전트는 문서의 내용을 벗어난 정보를 생성했습니다.

**문제**: 개발 단계에서 몇 가지 케이스만 손으로 확인하고 배포했기 때문에, 저빈도 질의 패턴에서 발생하는 환각을 발견하지 못했습니다.

**필요했던 평가**: `HallucinationDetector` — 에이전트의 답변이 제공된 컨텍스트와 사실적으로 일치하는지 측정하는 자동화된 지표. **Group C 신뢰성** 차원의 핵심 지표입니다.

### 사례 2: 도구 권한 초과 사용 (보안 위협)

내부 업무 자동화 에이전트가 파일 시스템에 접근하는 도구를 가지고 있었습니다. 외부 사용자 입력을 처리하던 에이전트는 정교하게 설계된 프롬프트 인젝션 공격을 받아, 허가되지 않은 파일 경로에 접근하고 그 내용을 응답에 포함시켰습니다. 민감한 시스템 설정 파일의 내용이 외부로 노출되는 보안 사고가 발생했습니다.

**문제**: 에이전트의 기능 테스트만 수행했고, 악의적 입력에 대한 보안 테스트가 없었습니다.

**필요했던 평가**: `InputSanitizationTracker`(프롬프트 인젝션 탐지), `OutputLeakageDetector`(민감 정보 출력 탐지), `ToolAuthorizationTracker`(허가된 도구만 사용하는지 감시), `PrivilegeEscalationDetector`(권한 상승 패턴 탐지), `ToolChainAttackDetector`(도구 연쇄 공격 탐지). **Group E 보안경계** 차원의 5개 트래커입니다.

### 사례 3: 응답 시간 급증으로 인한 서비스 장애

고객 지원 에이전트 서비스가 트래픽 급증 시점에 갑작스러운 레이턴시 증가를 경험했습니다. 평소 2초 이내로 응답하던 에이전트가 피크 타임에 30초 이상 응답하지 못했고, 많은 사용자가 서비스를 이탈했습니다. 원인을 추적한 결과, 특정 유형의 질의에서 에이전트가 도구를 평균 12번 호출하는 것으로 확인됐습니다. 정상적인 경우는 3번이었습니다.

**문제**: 응답 시간과 도구 호출 횟수를 지속적으로 모니터링하는 체계가 없었습니다.

**필요했던 평가**: `LatencyTracker`(p95 레이턴시 + `SLAConfig` 위반 감지), `ToolCallAnalyzer`(도구 호출 패턴 분석), `AnomalyDetector`(비정상 패턴 자동 감지). **Group D 성능계약** 차원입니다.

> 👨‍💻 **개발자 TIP**: 이 세 가지 사례는 각각 신뢰성(C), 보안(E), 성능(D) 실패입니다. 개발 단계의 몇 가지 수동 테스트로는 발견할 수 없습니다. 자동화된 평가 파이프라인이 없는 상태로 에이전트를 배포하는 것은 시트벨트 없이 고속도로에 진입하는 것과 같습니다.

---

## 1.3 Harness Engineering — 배포 판단의 7차원

기존 소프트웨어 테스팅은 에이전트 배포 판단에 충분하지 않습니다. 에이전트를 배포하기 전에 "통과/실패"를 선언할 근거가 필요합니다. Harness Engineering은 이 판단을 체계화하는 3요소 프레임워크입니다.

```
Tracker (관찰/측정) × Config (기준 선언) × Gate (배포 판정)
```

- **Tracker**: 에이전트 실행 중 지표를 자동 기록 (25개 네이티브 트래커)
- **Config**: "이 에이전트는 어떤 조건에서 배포될 수 있는가"를 코드로 선언 (33개 Harness Config)
- **Gate**: Config 위반 시 `success=False` → `HarnessEvaluationGate`로 종합 판정

### 7개 품질 차원 (Group A-G)

58개 지표(25 Tracker + 33 Config)는 7개 품질 차원으로 구분됩니다.

| Group | 차원 | 핵심 질문 | Tracker 수¹ | Config 수 |
|-------|------|-----------|-----------|-----------|
| **A** | 목표달성 | 에이전트가 지시를 제대로 완수했는가? | 3 | 6 |
| **B** | 행동무결성 | 의도하지 않은 행동 없이 동작했는가? | 2 | 6 |
| **C** | 신뢰성 | 같은 입력에 일관되게 응답하는가? | 2 | 5 |
| **D** | 성능계약 | SLA/비용 계약을 지켰는가? | 2 | 5 |
| **E** | 보안경계 | 외부 공격·데이터 유출을 차단했는가? | 5 | 3 |
| **F** | 다중에이전트 협업 | 여러 에이전트가 교착 없이 협력했는가? | 2 | 4 |
| **G** | 운영관측성 | 실패 원인을 즉시 추적·설명할 수 있는가? | 0 | 4 |
| | **Harness Gate 직접 지표** | | **16** | **33** |
| | **운영 지원 Tracker** (모니터링·비용·스트리밍 등) | | **+9** | — |
| | **SDK 전체 합계** | | **25** | **33** |

> ¹ Harness Gate(A–G)에 직접 집계되는 Native Tracker는 16개다. `ConversationSession`, `ImplicitFeedbackTracker`, `AnomalyDetector`, `CostTracker`, `StreamingEvaluator` 등 운영 지원 Tracker 9개를 합산하면 SDK 전체 Native Tracker는 25개다. Group G는 별도 Tracker 없이 `LLMJudge`(선택 활성화)와 Config 4개로 관측성을 측정한다.

> 공식 표기: **"25 Tracker + 33 Config = 58개 지표"**

### 배포 판단 코드 예시 — 5줄

아래는 세 가지 차원(목표달성·성능·보안)을 선언하고 배포 판단을 내리는 최소 예제입니다.

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 1 — 3-Element Harness(Tracker·Config·Gate) 최소 예시
from agent_evaluator import (
    PerformanceMonitor, HarnessEvaluationGate,
    InstructionConfig, SLAConfig, ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

# ① Config 선언 — 배포 기준을 코드로 정의
instruction_cfg = InstructionConfig(
    required_keywords=["결과"],  # 응답에 포함되어야 할 키워드
    fail_on_violation=True,
)
sla_cfg = SLAConfig(
    p95_ms=3000,                # P95 응답 3초 이내
    max_cost_per_task=0.01,     # 태스크당 비용 $0.01 이하
)
threat_cfg = ThreatSeverityConfig(
    fail_on_critical=True,       # 치명적 위협 탐지 시 fail
    fail_score=7.0,
)

# ② Tracker 자동 수집 — @agent_eval이 실행마다 지표 기록
@agent_eval(
    monitor,
    task_type="qa",
    instructions=instruction_cfg,
    sla=sla_cfg,
    threat_severity=threat_cfg,
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# ③ Gate — Config 위반 시 배포 중단
report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
gate.enforce()   # 기준 미달 시 sys.exit(1) → CI/CD 파이프라인 차단
```

Group A-G 각 차원의 구체적인 Tracker와 Config는 **Part II — Harness 지표 체계**(Chapter 03~10)에서 상세히 다룹니다.

> 📋 **QA 관리자 TIP**: "어떤 지표를 먼저 적용해야 하나?" → 우선순위: **A(목표달성) → D(성능계약)/E(보안경계) → C(신뢰성) → B(행동무결성) → G(관측성) → F(다중에이전트)**. Group A는 모든 에이전트의 기본 판단 근거입니다. Group E 보안은 외부 입력을 처리하는 에이전트라면 즉시 적용해야 합니다.

---

## 1.4 기존 소프트웨어 테스팅의 3가지 한계

기존 QA 방법론은 왜 AI 에이전트에 충분하지 않을까요? 핵심적인 세 가지 한계를 살펴보겠습니다.

### 한계 ①: 결정론적 pass/fail의 붕괴

전통 소프트웨어 테스트는 "이 입력에 대해 이 출력이 나왔는가"를 판단합니다. 단위 테스트, 통합 테스트, E2E 테스트 모두 예상 출력을 하드코딩하고 비교합니다.

```python
# 전통 소프트웨어 테스트 — 결정론적
def test_add():
    assert add(2, 3) == 5  # 항상 5

# AI 에이전트 테스트 — 확률론적
def test_agent():
    result = agent("한국의 수도는?")
    assert result == "서울입니다."  # 이 비교는 의미가 없다.
    # "서울이 한국의 수도입니다", "수도는 서울입니다" 모두 정답인데
    # 하나만 통과 처리된다.
```

에이전트의 응답은 의미적으로 동일해도 표현이 다를 수 있습니다. 단일 케이스 통과/실패 대신, **통계적 품질 분포**로 판단해야 합니다. "이번 실행에서 통과했는가"가 아니라 "1,000번 실행했을 때 90% 이상 정확한가"가 올바른 질문입니다.

### 한계 ②: 단일 실행 테스트의 불충분성

전통 테스트는 각 케이스를 한 번씩 실행합니다. 에이전트는 실행할 때마다 다른 결과를 낼 수 있어, 단일 실행 테스트는 비결정론적 동작을 놓칩니다.

| 테스트 방식 | 전통 소프트웨어 | AI 에이전트 |
|-----------|-------------|-----------|
| 케이스 반복 | 불필요 (결정론적) | 필수 (확률론적) |
| 결과 판단 | 정확히 일치 | 임계값 기반 통계 |
| 재현 가능성 | 항상 재현 | 확률적 재현 |
| 실패 정의 | 하나라도 실패 | N% 이상 성공 |

`ReproducibilityConfig`의 `reproducibility_threshold`는 이 문제를 해결합니다. "같은 입력에 대해 70% 이상 일관된 응답을 생성하는가"를 자동 판정합니다.

### 한계 ③: 배포 후 드리프트의 미탐지

전통 소프트웨어는 코드가 변경될 때 동작이 바뀝니다. 에이전트는 코드가 동일해도 시간이 지나면서 동작이 달라질 수 있습니다.

- **데이터 드리프트**: 입력 패턴이 학습 분포에서 멀어짐
- **모델 업스트림 변경**: LLM 공급자가 모델을 조용히 업데이트
- **컨텍스트 길이 증가**: 히스토리 누적으로 컨텍스트 윈도우 포화
- **외부 API 변화**: 도구가 의존하는 외부 API 응답 형식 변경

이 드리프트는 기존 테스트 스위트를 통과해도 프로덕션에서 발생합니다. `RunTrendAnalyzer`(`agent-eval trend`)는 순차 평가 결과의 TCR·정확도 기울기를 분석해 조기 경보를 발령합니다.

```bash
# 100번 평가 결과의 드리프트를 자동 감지
agent-eval trend results/ --fail-on-regression
# → slope < -0.05 이면 exit 1 (CI/CD 파이프라인 중단)
```

> 👨‍💻 **개발자 TIP**: 세 한계의 해결책은 모두 **지속 평가**입니다. 배포 전 1회 테스트가 아닌, 프로덕션에서도 계속 측정하는 루프가 Harness Engineering의 핵심입니다.

---

## 1.5 AI Native 평가의 5가지 고유 도전

전통 소프트웨어 QA 경험이 있는 엔지니어가 AI 에이전트 평가를 처음 시작할 때 부딪히는 고유한 도전이 있습니다. 이 도전들이 Harness Engineering의 58개 지표 설계 근거가 됩니다.

### 도전 ①: 확률론적 품질 (Probabilistic Quality)

동일 입력 → 비결정론적 출력. 기존 assert 기반 테스트는 의미가 없습니다.

**해결**: TokenF1 + Jaccard + LCS + Char Levenshtein 4중 가중 알고리즘으로 **의미적 유사도**를 측정. 단일 케이스 통과 여부 대신 **평균 정확도 분포**로 판단합니다.

```
기존 방식: assert response == "서울입니다."    # ❌ 표현이 조금만 달라도 실패
Harness 방식: accuracy_score ≥ 0.85           # ✅ 의미가 같으면 통과
```

### 도전 ②: AI-by-AI 평가 (AI Evaluating AI)

에이전트 응답의 품질을 자동으로 채점하려면 또 다른 LLM이 필요합니다. 이를 LLM-as-Judge라고 합니다. 하지만 채점 LLM 자체도 편향이 있고, API 호출 비용이 발생합니다.

**해결**: `LLMJudge`는 **샘플링(기본 10%)** 방식으로 비용을 제어합니다. 7차원(completeness·relevance·factual_consistency·toxicity·bias·faithfulness·criteria_scores) 자동 채점으로 ground_truth 없이도 품질을 측정합니다.

```python
judge = LLMJudge(sample_rate=0.1)  # 10%만 LLM 채점, 나머지는 네이티브 알고리즘
```

### 도전 ③: 드리프트 인식 (Drift Awareness)

모델·데이터·환경의 변화가 코드 변경 없이 에이전트 동작을 바꿉니다.

**해결**: `RunTrendAnalyzer`가 순차 평가 결과의 기울기를 자동 계산합니다. TCR이 지속적으로 감소하는 추세를 감지하면 경보를 발령합니다.

```
평가 결과 시계열: [0.92, 0.91, 0.89, 0.86, 0.82, ...]
slope = -0.025/평가 → 드리프트 감지 → CI 경보
```

### 도전 ④: 출현 행동 대응 (Emergent Behavior)

설계하지 않은 동작이 에이전트에서 예상치 못하게 등장합니다. 특히 도구 체인이 길어질수록, 멀티에이전트 시스템일수록 예측 불가능한 상호작용이 발생합니다.

**해결**: `AnomalyDetector`가 통계적 정상 범위를 학습하고 이탈 시 즉시 탐지합니다. `ToolChainAttackDetector`는 도구 체인에서 발생하는 비정상 연쇄 호출을 추적합니다.

```python
# 도구 체인 이상 탐지 — 정상적이지 않은 연쇄 패턴을 자동 감지
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,   # Group E 활성화
    enable_anomaly_detection=True,  # 출현 행동 감지
)
```

### 도전 ⑤: 지속 평가 (Continuous Evaluation)

AI 에이전트는 배포 후에도 계속 변합니다. 일회성 배포 전 테스트만으로는 충분하지 않습니다.

**해결**: `evaluation_session` 컨텍스트 매니저 + `agent-eval trend` + Phoenix OTEL을 결합한 **자기개선 루프**를 구성합니다.

```
[운영] 실시간 평가 → [이상 탐지] 드리프트 경보 → [원인 분석] LLMJudge·Phoenix
→ [개선] 프롬프트/모델 교체 → [검증] HarnessEvaluationGate 재통과 → [배포]
```

### AI Native 5대 도전 ↔ Harness Gate A–G 매핑

5가지 도전은 추상적인 문제가 아닙니다. Harness Engineering의 7개 Gate가 각 도전에 정확히 대응합니다.

| AI Native 도전 | 핵심 질문 | 대응 Harness Gate | 주요 Tracker / Config |
|--------------|---------|-----------------|----------------------|
| ① 확률론적 품질 | "통계적으로 충분히 정확한가?" | **Gate A** 목표달성, **Gate C** 신뢰성 | AccuracyEvaluator, ReproducibilityConfig |
| ② AI-by-AI 평가 | "LLM Judge 비용 없이 품질을 측정할 수 있는가?" | **Gate G** 운영관측성 | LLMJudge (sample_rate 조절), ExplainabilityConfig |
| ③ 드리프트 인식 | "배포 후 성능 저하를 조기에 감지하는가?" | **Gate D** 성능계약, **Gate C** 신뢰성 | LatencyTracker, RunTrendAnalyzer, CostPredictabilityConfig |
| ④ 출현 행동 대응 | "예측 못한 도구 호출·루프·범위 이탈을 탐지하는가?" | **Gate B** 행동무결성, **Gate E** 보안경계 | ToolChainAttackDetector, AnomalyDetector, ScopeConfig |
| ⑤ 지속 평가 | "배포 후에도 지속적으로 품질을 검증하는가?" | **Gate A–G 전체** (CI/CD + 실시간 모니터링) | HarnessEvaluationGate, Phoenix OTEL, agent-eval trend |

**개발자 관점**: 각 도전에 대응하는 Tracker를 활성화하고 Config로 기준을 선언합니다.  
**QA 관리자 관점**: 도전이 해결됐는지를 Gate A–G의 PASS/WARN/FAIL 판정으로 확인합니다.

> 📋 **QA 관리자 TIP**: AI Native 5가지 도전은 전통 QA 역할을 없애지 않습니다. "케이스를 통과했는가" 대신 "품질 분포가 배포 기준을 만족하는가"로 판단 언어를 바꾸는 것입니다. Part IV — QA 관리자 가이드에서 이 전환을 단계별로 다룹니다.

---

## 1.6 AI 에이전트 평가 프레임워크 생태계 — 9개 도구 비교표

현재 AI 에이전트 평가를 위한 도구들이 빠르게 발전하고 있습니다. 각 도구의 특성을 이해하면 상황에 맞는 선택을 할 수 있습니다.

### 주요 도구 개요

| 프레임워크 | 유형 | 버전 (2025-2026) | 주력 기능 |
|---|---|---|---|
| **LangSmith** | SaaS + 셀프호스트 | SDK ≥0.4.25 | LangChain 생태계 관측 |
| **Ragas** | OSS 라이브러리 | v0.4.3 | RAG + 에이전트 평가 |
| **DeepEval** | OSS + SaaS | v3.8.9 | LLM 단위 테스트 |
| **Arize Phoenix** | OSS + Cloud | v8.x+ | LLM 관측가능성 (OTEL 기반) |
| **Evidently AI** | OSS + Cloud | v0.7.17+ | ML/LLM 모니터링 |
| **Braintrust** | SaaS + OSS SDK | v0.5.2 | LLM 실험 + 에이전트 관측 |
| **Helicone** | SaaS + OSS | — | LLM 프록시 + 비용 관측 |
| **W&B Weave** | SaaS + OSS SDK | v0.72+ | 에이전트 평가 + 실험 관리 |
| **Agent Evaluator** | OSS SDK | v0.8.3 | Harness Engineering 배포 판단 |

### 에이전틱 지표 지원 비교

에이전트 평가에서 가장 중요한 것은 일반 LLM 품질 지표가 아닌, 에이전트 고유의 동작을 측정하는 지표입니다.

| 지표 | LangSmith | Ragas | DeepEval | Phoenix | Evidently | Braintrust | Helicone | W&B | Agent Evaluator |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Tool 선택 정확도 (F1) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Tool 효율성 / 불필요 호출 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 재시도 / 자기수정 패턴 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 멀티에이전트 협업 품질 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 워크플로우 퍼널 / 분기 | ✅ (LangGraph) | ❌ | ❌ | 부분 | ❌ | 부분 | ❌ | 부분 | ✅ |
| 프롬프트 인젝션 탐지 | ❌ | ❌ | ⚠️ Red-team | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 출력 정보 유출 탐지 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 권한 상승 탐지 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Harness Config 배포 판정** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **✅** |
| **드리프트 추세 탐지** | 부분 | ❌ | ❌ | 부분 | ✅ | 부분 | ❌ | ✅ | ✅ |

### 비용 및 오프라인 실행 비교

| 도구 | 추가 LLM 비용 (1,000건) | 오프라인 실행 | 계산 지연 |
|---|---|---|---|
| LangSmith | $2~10 | ❌ | 수 초 |
| Ragas | $5~20 | ❌ | 수 초~분 |
| DeepEval | $3~15 | 부분 | 수 초 |
| Arize Phoenix | $3~10 | ✅ 로컬 서버 | 수 초 |
| Evidently AI | $0 | ✅ | 밀리초~초 |
| Braintrust | 선택적 | 부분 | 선택적 |
| Helicone | $0 | ❌ | 없음 (집계만) |
| W&B Weave | 선택적 | 부분 | 선택적 |
| **Agent Evaluator** | **$0** | **✅** | **밀리초** |

### 어떤 도구를 선택해야 하는가?

- **LangChain/LangGraph를 이미 사용 중이고 클라우드 서비스를 선호한다면**: LangSmith
- **RAG 파이프라인 품질을 집중적으로 평가하고 싶다면**: Ragas
- **LLM 관측가능성과 분산 트레이싱이 중심이라면**: Arize Phoenix
- **Tool 선택, 보안, 재시도 등 에이전트 고유 동작을 평가하고, 배포 판단 기준을 코드로 선언하며, 외부 API 비용 없이 로컬에서 실행하고 싶다면**: Agent Evaluator

이 책의 나머지 챕터들은 Agent-Evaluator를 중심으로 진행하지만, Part III에서 다른 도구들과의 연동 방법도 함께 다룹니다.

---

## 1.7 AI 평가 지표의 역사 — BLEU에서 LLM-as-Judge까지

Agent-Evaluator의 지표 설계를 이해하려면 AI 평가 연구가 어떤 문제를 해결하면서 발전해왔는지 아는 것이 도움이 됩니다.

### 참조 기반 지표 시대 (2002–2017)

**BLEU** (Papineni et al. 2002)는 기계 번역 품질을 인간 참조 번역과의 n-gram 정밀도로 측정하는 최초의 자동화 지표였습니다. 빠르고 재현 가능하지만 **정밀도(Precision)만 측정**하고 의미적 동의어를 인식하지 못한다는 근본적 한계를 가집니다.

**ROUGE** (Lin 2004)는 문서 요약을 위해 **재현율(Recall) 중심**으로 설계됐습니다.

**Agent-Evaluator의 대응**: BLEU/ROUGE 대신 **Token F1**(Precision+Recall 균형)을 핵심 지표로 채택하고, 4개 서브지표(Token F1 + Jaccard + LCS + Char Levenshtein) 조합으로 단일 지표의 맹점을 보완합니다. (→ Group A 목표달성 §4.2)

### 의미 유사도의 부상 (2018–2021)

**BERTScore** (Zhang et al. 2019)는 BERT 임베딩 공간에서 코사인 유사도를 계산해 의미적 유사도를 측정합니다. 동의어와 패라프레이즈를 자동 처리하며 인간 판단과의 상관이 BLEU보다 높습니다. 그러나 **GPU 메모리와 추론 시간**이 필요합니다.

**Agent-Evaluator의 대응**: 프로덕션 모니터링에서 매 요청마다 BERTScore를 계산하는 것은 비현실적입니다. 외부 의존성 없이 <1ms로 동작하는 4중 가중 알고리즘을 기본으로 제공하고, 정밀 평가가 필요한 경우에만 LLM Judge를 샘플링 방식으로 추가합니다.

### LLM-as-Judge의 등장 (2022–현재)

**HELM** (Liang et al. 2022)은 42개 시나리오 × 7개 지표로 정확성·강건성·공정성·독성을 동시 측정하는 종합 벤치마크입니다. **MT-Bench** (Zheng et al. 2023)와 **Chatbot Arena**는 GPT-4로 모델 응답을 채점하거나 두 응답 중 선호도를 선택하는 **LLM-as-Judge** 패러다임을 정착시켰습니다.

**Agent-Evaluator의 대응**: `LLMJudge` 클래스가 이 패러다임을 구현합니다. completeness·relevance·factual_consistency·toxicity·bias 5차원을 ground_truth 없이 채점하며, RAG 모드에서는 faithfulness 차원이 추가됩니다. DeepEval G-Eval의 커스텀 기준(`judge_criteria`)도 외부 패키지 없이 지원합니다. (→ Group G 운영관측성 §10.2)

```
AI 평가 발전 요약:
  BLEU (2002)       → Precision 편향, 동의어 불인식
  ROUGE (2004)      → Recall 편향
  BERTScore (2019)  → 의미적 유사도, but 느리고 무거움
  HELM (2022)       → 종합 벤치마크, 다축 측정
  LLM-as-Judge (2023) → 인간 판단 대리, 유연한 기준

  Agent-Evaluator   → 4중 가중 알고리즘(빠름) + LLM Judge 샘플링(정밀)
                       + 33개 Harness Config(배포 판단)
                       외부 의존성 없이 프로덕션에서 바로 사용 가능
```

> 📖 **더 깊이**: 각 지표의 수식과 한계 분석은 → Appendix G §G.1 (AI 평가의 역사와 발전), Appendix I §I.1 (정확도 지표 심층 비교)

---

> **이 챕터의 핵심**
>
> - AI 에이전트는 입력→출력 1회의 LLM과 달리, 도구 호출·멀티스텝·상태·반복 동작으로 평가 복잡성이 근본적으로 다릅니다.
> - 환각·보안 위협·레이턴시 급증은 평가 체계 없이는 배포 후에야 발견되는 전형적인 실패 패턴입니다. 각각 Group C·E·D 차원의 문제입니다.
> - **Harness Engineering**은 Tracker(관찰) × Config(기준) × Gate(판정)의 3요소로 배포를 판단합니다.
> - 58개 지표(25 Tracker + 33 Config)는 7개 품질 차원 Group A-G로 구조화됩니다.
> - AI Native 평가의 5가지 고유 도전(확률론적 품질·AI-by-AI 평가·드리프트·출현 행동·지속 평가)은 기존 소프트웨어 테스팅 방법론으로 해결되지 않습니다.
> - 에이전트 평가 도구 생태계에서 Harness Config 기반 배포 판정과 에이전틱 전용 지표를 LLM 없이 제공하는 도구는 Agent Evaluator가 유일합니다.

---

## 실전 예제

챕터 1에서 설명한 Harness Engineering 개념과 Group A-G 7차원을 실제 지표로 측정하려면 `ch02_first_eval.py`와 `ch05_group_b.py`로 시작합니다. API 키 없이도 네이티브 지표를 즉시 실행할 수 있습니다.

**파일**: `Evaluator_Examples/ch02_first_eval.py`, `Evaluator_Examples/ch05_group_b.py`

**핵심 코드 (출처: `Evaluator_Examples/ch02_first_eval.py`)**

```python
# 출처: Evaluator_Examples/ch02_first_eval.py, 섹션 QA — 기본 QA 평가 (Group A 목표달성)
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C 신뢰성 — 환각 감지 활성화
)

result = create_taskresult(
    task_id="qa_001",
    question="대한민국의 수도는 어디인가요?",
    response="대한민국의 수도는 서울입니다.",
    ground_truth="서울",
    execution_time=0.85,
    task_type="qa",
)

monitor.record_task(result)
report = monitor.generate_report()
d = report.to_dict()
tcr = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
acc = d.get("accuracy_metrics", {}).get("accuracy_scores", {}).get("overall_accuracy", 0.0)
print(f"TCR: {tcr:.1%}")      # Group A 목표달성
print(f"Accuracy: {acc:.1%}") # Group A 목표달성
```

- `create_taskresult()`는 `accuracy_score`를 자동 계산합니다 (TokenF1 40% + Jaccard 30% + LCS 20% + Char Levenshtein 10%)
- `enable_hallucination_detection=True`를 켜면 `task_type="information_retrieval"` 태스크에서 환각 점수(Group C)가 추가됩니다
- `generate_report()`는 TCR·정확도·지연시간·토큰 사용량을 집계한 `EvaluationReport` 객체를 반환합니다

```python
# 출처: Evaluator_Examples/ch05_group_b.py, 섹션 1 — Group E 보안경계 측정
from agent_evaluator import EvalMetadata
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="tool_use")
def tool_agent(question: str, ground_truth: str = "") -> tuple:
    result_text = f"{question}에 대한 답변"
    tool_calls_made = ["web_search", "calculator"]
    expected = ["web_search", "calculator"]
    return result_text, EvalMetadata(
        tool_calls=tool_calls_made,
        expected_tools=expected,
    )

# 데코레이터가 Group A(Accuracy) + Group B(ToolCall) + Group F(ToolSelection F1)를 자동 측정
tool_agent("2024년 GDP 상위 5개국은?", ground_truth="미국, 중국, 독일, 일본, 인도")
```

```bash
# Group A/C/D — 목표달성·신뢰성·성능계약 측정
python Evaluator_Examples/ch02_first_eval.py

# Group B/E/F — 행동무결성·보안경계·다중에이전트 측정
python Evaluator_Examples/ch05_group_b.py
```

**Group A-G와 예제 매핑**

| Group | 차원 | 측정 지표 | 예제 파일·섹션 |
|-------|------|----------|---------------|
| A | 목표달성 | AccuracyEvaluator (TokenF1·Jaccard·LCS), TCR | 01_layer1, 섹션 1~2 |
| B | 행동무결성 | ToolCallAnalyzer, WorkflowExecutionTracker | 02_layer2, 섹션 1~3 |
| C | 신뢰성 | HallucinationDetector, RetryCorrectionTracker | 01_layer1, 섹션 5~6 |
| D | 성능계약 | LatencyTracker (p95), TokenEconomyTracker | 01_layer1, 섹션 3~4 |
| E | 보안경계 | InputSanitization, OutputLeakage, ToolAuth | 02_layer2, 섹션 4~6 |
| F | 다중에이전트 | AgentCoordinationTracker, ToolSelectionTracker | 02_layer2, 섹션 7~8 |
| G | 운영관측성 | LLMJudge 7차원, Phoenix OTEL | 07_phoenix_hybrid |

**실행 결과 (v0.8.3 기준)**

```
# ch02_first_eval.py
TCR=43.1% | 54개 태스크 | p95_latency=5.20s | avg_accuracy=59.82%

# ch05_group_b.py
TCR=41.4% | 14개 태스크 | 보안 위협 3건 탐지
  - SQL Injection 시도 탐지 (Group E — InputSanitizationTracker)
  - 민감 데이터 노출 탐지 (Group E — OutputLeakageDetector)
  - 무단 도구 사용 탐지 (Group E — ToolAuthorizationTracker)
```

> **첫 실행 팁**: 두 파일 모두 API 키 없이 실행됩니다. `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`를 `.env`에 추가하면 LLMJudge(Group G)가 활성화되어 `completeness`, `relevance`, `factual_consistency` 세 차원이 추가로 측정됩니다.

**프레임워크 어댑터 — 실제 프레임워크 응답에서 Group 지표 자동 추출 (출처: `Evaluator_Examples/ch13_frameworks.py`)**

`framework=` 파라미터 하나로 LangChain·LangGraph·CrewAI·AutoGen 응답 객체에서 tool_calls·agent_interactions·tokens_used를 자동 추출한다. 실제 SDK 없이도 mock 응답 객체로 동작한다(duck typing).

```python
# 출처: Evaluator_Examples/ch13_frameworks.py, 섹션 1 — framework= 파라미터 하나로 Group B·F 자동 측정
from types import SimpleNamespace
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="lc")
def langchain_agent(question: str, ground_truth: str = ""):
    steps = [(SimpleNamespace(tool=t, tool_input="q"), f"{t} 결과")
             for t in ["web_search", "calculator"]]
    return SimpleNamespace(
        output=f"결과: {question}",
        intermediate_steps=steps,            # → Group B ToolCallAnalyzer 자동 연결
        usage_metadata={"input_tokens": 350, "output_tokens": 120},  # → TokenEconomyTracker
    )

langchain_agent("GDP 상위 5개국은?", ground_truth="미국, 중국, 독일, 일본, 인도")
# Group A: accuracy_score 자동 계산 (TokenF1·Jaccard·LCS)
# Group B: tool_calls=[web_search, calculator] 자동 기록
# Group D: tokens_used={input:350, output:120} 자동 기록
```

**버전 비교 — Harness Gate로 "어느 버전을 배포할지" 결정 (출처: `Evaluator_Examples/ch20_deployment.py`)**

```python
# 출처: Evaluator_Examples/ch20_deployment.py — v1 vs v2 Gate 점수 비교
from agent_evaluator import PerformanceMonitor
# 두 monitor를 독립적으로 운영 — Gate 간 교차 오염 없음
monitor_v1 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)
monitor_v2 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# ... v1·v2 에이전트 등록 및 동일 테스트 케이스 실행 ...

r1 = monitor_v1.generate_report().to_dict()
r2 = monitor_v2.generate_report().to_dict()
h1 = (r1.get("extra_metrics") or {}).get("harness_groups", {})
h2 = (r2.get("extra_metrics") or {}).get("harness_groups", {})

v1_fail = [g for g in "ABCDEFG" if ((h1.get(g) or {}).get("gate") or "").upper() == "FAIL"]
v2_fail = [g for g in "ABCDEFG" if ((h2.get(g) or {}).get("gate") or "").upper() == "FAIL"]
print(f"v1 FAIL Gates: {v1_fail}")   # 배포 불가
print(f"v2 FAIL Gates: {v2_fail}")   # FAIL 없으면 배포 승인
```
