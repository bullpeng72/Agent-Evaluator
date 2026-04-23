# Chapter 01: AI 에이전트 평가란 무엇인가

> "측정할 수 없으면 개선할 수 없다." — Peter Drucker

---

## 1.1 LLM과 에이전트의 차이 — 왜 평가 방식이 다른가

LLM(Large Language Model)을 API로 호출하는 것과 AI 에이전트를 운영하는 것은 근본적으로 다른 문제입니다. 겉으로는 비슷해 보이지만, 내부 동작 방식과 실패 패턴이 전혀 다릅니다.

### 단순 LLM 호출: 입력 → 출력 1회

```python
# 출처: Evaluator_Examples/ch01_first_eval.py — 예제 코드
# 단순 LLM 호출 — 평가가 상대적으로 간단하다
response = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "한국의 수도는?"}]
)
answer = response.choices[0].message.content
# → "서울입니다."
```

- **단일 호출**: 입력 → 출력이 1회로 완결되어 평가가 단순하다.
- **결정론적 비교**: `answer == "서울"` 수준의 정확 매칭으로 품질을 판단할 수 있다.
- **한계**: 온도(temperature) > 0 이면 같은 입력에도 다른 표현이 나오며, 이 비교 방식은 곧 한계에 부딪힌다.

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

**필요했던 평가**: `HallucinationDetector` — 에이전트의 답변이 제공된 컨텍스트와 사실적으로 일치하는지 측정하는 자동화된 지표. **Gate A 목표달성**(사실 일관성)과 **Gate C 신뢰성**(반복 실행 품질 보장) 차원 모두에 영향을 미치는 핵심 지표입니다.

> *참고: RAG 파이프라인의 문맥 이탈 환각(context-unfaithful hallucination) 패턴 — Ji et al. (2023). "Survey of Hallucination in Natural Language Generation." ACM Computing Surveys, 55(12). / Singhal et al. (2023). "Large Language Models Encode Clinical Knowledge." Nature, 620, 172–180 — 의료 LLM의 임상 지식 인코딩 능력과 정확도 한계 분석.*

### 사례 2: 도구 권한 초과 사용 (보안 위협)

내부 업무 자동화 에이전트가 파일 시스템에 접근하는 도구를 가지고 있었습니다. 외부 사용자 입력을 처리하던 에이전트는 정교하게 설계된 프롬프트 인젝션 공격을 받아, 허가되지 않은 파일 경로에 접근하고 그 내용을 응답에 포함시켰습니다. 민감한 시스템 설정 파일의 내용이 외부로 노출되는 보안 사고가 발생했습니다.

**문제**: 에이전트의 기능 테스트만 수행했고, 악의적 입력에 대한 보안 테스트가 없었습니다.

**필요했던 평가**: `InputSanitizationTracker`(프롬프트 인젝션 탐지), `OutputLeakageDetector`(민감 정보 출력 탐지), `ToolAuthorizationTracker`(허가된 도구만 사용하는지 감시), `PrivilegeEscalationDetector`(권한 상승 패턴 탐지), `ToolChainAttackDetector`(도구 연쇄 공격 탐지). **Gate E 보안경계** 차원의 5개 트래커입니다.

> *참고: 간접 프롬프트 인젝션을 통한 LLM 통합 애플리케이션 공격 실증 — Greshake et al. (2023). "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection." arXiv:2302.12173. / OWASP LLM Top 10 v1.1 (2023). LLM01: Prompt Injection. owasp.org/www-project-top-10-for-large-language-model-applications*

### 사례 3: 응답 시간 급증으로 인한 서비스 장애

고객 지원 에이전트 서비스가 트래픽 급증 시점에 갑작스러운 레이턴시 증가를 경험했습니다. 평소 2초 이내로 응답하던 에이전트가 피크 타임에 30초 이상 응답하지 못했고, 많은 사용자가 서비스를 이탈했습니다. 원인을 추적한 결과, 특정 유형의 질의에서 에이전트가 도구를 평균 12번 호출하는 것으로 확인됐습니다. 정상적인 경우는 3번이었습니다.

**문제**: 응답 시간과 도구 호출 횟수를 지속적으로 모니터링하는 체계가 없었습니다.

**필요했던 평가**: `LatencyTracker`(p95 레이턴시 + `SLAConfig` 위반 감지), `ToolCallAnalyzer`(도구 호출 패턴 분석), `AnomalyDetector`(비정상 패턴 자동 감지). **Gate D 성능계약** 차원입니다.

> *참고: 에이전트의 반복적 도구 호출 패턴 — Yao et al. (2023). "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023 — 추론-행동 반복 루프 기반 도구 호출 아키텍처 실증. / Liu et al. (2024). "AgentBench: Evaluating LLMs as Agents." ICLR 2024 — 다양한 환경에서 LLM 에이전트의 도구 호출 수행 능력 평가.*

> 👨‍💻 **개발자 TIP**: 이 세 가지 사례는 각각 목표달성/신뢰성(A·C), 보안(E), 성능(D) 실패입니다. 사례 1의 환각은 사실 정확성(Gate A)과 반복 실행 품질(Gate C) 양쪽에 걸쳐 있습니다. 개발 단계의 몇 가지 수동 테스트로는 발견할 수 없습니다. 자동화된 평가 파이프라인이 없는 상태로 에이전트를 배포하는 것은 시트벨트 없이 고속도로에 진입하는 것과 같습니다.

세 사례가 공통적으로 보여주는 첫 번째 교훈은 명확합니다. **배포 전에 에이전트가 갖춰야 할 기준이 선언되지 않았다**는 것입니다. 어떤 수준의 환각률이 허용되는지, 어떤 레이턴시 이하여야 서비스가 가능한지, 어떤 도구는 쓸 수 없는지 — 이 기준들이 코드로 존재했다면 배포 전에 차단됐을 것입니다.

그런데 여기서 더 중요한 두 번째 교훈이 있습니다. **세 사례는 서로 다른 실패 차원을 드러냅니다.** 사례 1은 출력의 사실 정확성(신뢰성), 사례 2는 외부 공격에 대한 보안 경계, 사례 3은 성능과 비용 계약의 실패입니다. 어느 한 차원을 완벽하게 측정해도 다른 차원은 알 수 없습니다 — 높은 정확도가 보안을 보장하지 않고, 빠른 응답이 환각 없음을 보장하지 않습니다. **AI 에이전트의 배포 준비도는 단일 지표로 표현할 수 없습니다.** 자율 에이전트는 구조적으로 서로 다른 여러 차원에서 독립적으로 실패할 수 있으며, 각 차원을 별도로 검증해야만 신뢰할 수 있는 배포 판단을 내릴 수 있습니다.

---

## 1.3 Harness Engineering — 배포 판단의 7차원

AI 최적화 방법론은 세 단계를 거쳐 진화했습니다.

- **Prompt Engineering (2022–2024)**: 단일 LLM 호출의 입력 텍스트를 최적화합니다. "어떻게 물어볼까?"가 핵심 질문입니다. 그러나 에이전트가 여러 도구를 호출하고 멀티턴 추론을 수행하는 복잡한 시나리오에서는 한계에 부딪힙니다.
- **Context Engineering (2025)**: 컨텍스트 창에 들어오는 모든 정보(RAG, 메모리, 도구 스펙, 이력)를 관리합니다. Andrej Karpathy가 "컨텍스트 창을 정확히 채우는 섬세한 과학"으로 정의했습니다. 에이전트 품질을 크게 높였지만, **"에이전트가 실제로 어떻게 동작했는가"를 사후에 검증하고 배포 가능 여부를 자동 판정**하는 메커니즘은 없었습니다.
- **Harness Engineering (2026~)**: 모델 주변의 제어 구조 전체를 설계합니다. Mitchell Hashimoto의 정의처럼, **"Agent = Model + Harness"** — 모델을 제외한 모든 것(지시 구조, 제약 선언, 품질 측정, 배포 판정)이 Harness에 속합니다.

에이전트를 배포하기 전에 "통과/실패"를 선언할 근거가 필요합니다. 이 책에서 Harness Engineering은 그 판단 구조를 세 가지 역할로 구현합니다. 아래 세 개념은 이 책 전체에서 반복 등장하는 핵심 용어이므로, 처음 만나는 시점에 명확히 구분해 두는 것이 중요합니다.

```
Tracker (관찰/측정) × Config (기준 선언) × Gate (배포 판정)
```

세 역할은 서로 다른 시점에 독립적으로 작동합니다.

- **Tracker**: 에이전트가 실행되는 동안 지표를 자동 기록합니다. 판단하지 않습니다. "응답 시간이 1.3초였다", "도구를 3번 호출했다"처럼 사실만 측정합니다 (25개 네이티브 트래커).
- **Config**: "이 에이전트는 어떤 조건에서 배포될 수 있는가"를 코드로 선언합니다. 측정하지 않습니다. `SLAConfig(p95_ms=2000)`처럼 기준을 정의하고, Tracker 측정값이 이 기준을 위반하면 해당 태스크를 `success=False`로 처리합니다 (33개 Harness Config). Config는 "품질 계약"을 코드로 문서화하는 수단이기도 합니다.
- **Gate**: Config 위반이 축적된 Tracker 측정값과 대조해 배포 가능 여부를 최종 판정합니다. `eval.gate(tcr=85)` 또는 `HarnessEvaluationGate.enforce()`가 이 역할을 합니다. 기준 미달이면 `sys.exit(1)`로 CI/CD 파이프라인을 차단합니다.

이 세 역할이 어떻게 실제 코드에서 보이는지는 **Chapter 2**에서 직접 경험합니다. 설계 원리와 각 역할의 내부 구조는 **Chapter 3**에서 동등한 깊이로 다룹니다.

### 7개 품질 차원 (Gate A-G)

#### 왜 7개인가 — 자율 에이전트 배포 준비도의 독립 차원

§1.2에서 확인한 세 가지 실패 사례(신뢰성·보안·성능)는 더 넓은 구조를 암시합니다. 자율 에이전트 시스템 전체를 분석하면 프로덕션 배포를 승인하기 위해 반드시 "예"로 답해야 하는 질문이 정확히 7가지임을 알 수 있습니다.

이 7가지 질문이 핵심인 이유는 **서로 독립적**이기 때문입니다. 하나를 확인해도 다른 하나는 알 수 없어서, 7개 모두 통과해야 배포를 신뢰할 수 있습니다.

- **Gate A (목표달성)**: "에이전트가 지시를 제대로 완수했는가?" — 어떤 에이전트도 생략할 수 없는 기본 요건. 정확도와 TCR로 측정.
- **Gate B (행동무결성)**: "의도된 범위 안에서만 행동했는가?" — 자율 에이전트 고유의 위험. 정답을 냈어도 허가되지 않은 도구를 썼다면 실패.
- **Gate C (신뢰성)**: "같은 품질이 반복 실행에서도 보장되는가?" — 확률론적 AI에서 한 번 성공이 통계적 보장을 의미하지 않는다.
- **Gate D (성능계약)**: "비용·응답 시간 SLA를 지켰는가?" — 정확한 답도 30초가 걸리거나 비용이 예산을 초과하면 서비스가 불가능하다.
- **Gate E (보안경계)**: "외부 공격과 정보 유출을 차단했는가?" — 기능 테스트 100% 통과가 보안을 보장하지 않는다.
- **Gate F (다중에이전트)**: "여러 에이전트가 교착 없이 협력하는가?" — 단일 에이전트의 품질이 멀티에이전트 시스템의 안전성을 보장하지 않는다.
- **Gate G (운영관측성)**: "실패 원인을 즉시 추적·설명할 수 있는가?" — 지금 성능이 좋아도 블랙박스이면 문제 발생 시 대응할 수 없다.

7개 Gate 중 하나라도 미확인 상태로 배포하면, 해당 차원에서 반드시 예상치 못한 장애가 발생합니다. §1.2의 세 사례는 각각 Gate A·C(목표달성·신뢰성 — 환각), Gate E(보안경계 — 권한 초과), Gate D(성능계약 — 레이턴시 급증)의 실패였습니다. Harness Engineering은 이 7개 질문에 코드로 선언된 기준을 대조해 자동으로 답하는 체계입니다.

58개 지표(25 Tracker + 33 Config)는 7개 품질 차원으로 구분됩니다.

| Gate | 차원 | 핵심 질문 | Tracker 수¹ | Config 수 |
|------|------|-----------|-----------|-----------|
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

> ¹ Harness Gate(A–G)에 직접 집계되는 Native Tracker는 16개다. `ConversationSession`, `ImplicitFeedbackTracker`, `AnomalyDetector`, `CostTracker`, `StreamingEvaluator` 등 운영 지원 Tracker 9개를 합산하면 SDK 전체 Native Tracker는 25개다. Gate G는 별도 Tracker 없이 `LLMJudge`(선택 활성화)와 Config 4개로 관측성을 측정한다.

> 공식 표기: **"25 Tracker + 33 Config = 58개 지표"**

### 배포 판단 코드 예시

아래는 세 가지 차원(목표달성·성능·보안)을 선언하고 배포 판단을 내리는 최소 예제입니다.

```python
# 출처: Evaluator_Examples/ch01_first_eval.py, 섹션 1 — 3-Element Harness(Tracker·Config·Gate) 최소 예시
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

- **3요소 패턴**: ① Config(기준 선언) → ② `@agent_eval`(Tracker 자동 수집) → ③ `HarnessEvaluationGate.enforce()`(종합 판정) 순서로 구성된다.
- **`InstructionConfig(required_keywords=["결과"])`**: 응답에 "결과" 키워드가 없으면 해당 태스크를 `success=False`로 처리해 TCR을 낮춘다.
- **`SLAConfig(p95_ms=3000)`**: p95 응답 시간이 3초를 초과하거나 태스크당 비용이 $0.01을 넘으면 Gate D에서 FAIL 판정을 받는다.
- **`ThreatSeverityConfig(fail_on_critical=True, fail_score=7.0)`**: 위협 점수 7.0 이상의 입력이 탐지되면 해당 태스크를 즉시 실패 처리하고 Gate E에 반영한다.
- **`gate.enforce()`**: Gate A–G 전체 Config 위반 여부를 종합 판정해 기준 미달이면 `sys.exit(1)`을 호출해 CI/CD 파이프라인을 차단한다.

Gate A-G 각 차원의 구체적인 Tracker와 Config는 **Part II — Harness 지표 체계**(Chapter 03~10)에서 상세히 다룹니다.

> 📋 **QA 관리자 TIP**: "어떤 지표를 먼저 적용해야 하나?" → 우선순위: **A(목표달성) → D(성능계약)/E(보안경계) → C(신뢰성) → B(행동무결성) → G(관측성) → F(다중에이전트)**. Gate A는 모든 에이전트의 기본 판단 근거입니다. Gate E 보안은 외부 입력을 처리하는 에이전트라면 즉시 적용해야 합니다.

§1.3에서 7개 Gate의 구조와 3요소의 역할 분리를 개념으로 확인했습니다. 그런데 왜 기존 소프트웨어 테스팅으로는 이 구조가 필요하지 않았을까요? 그 이유를 이해해야 Harness Engineering이 왜 새로운 패러다임인지가 명확해집니다.

---

## 1.4 Harness Engineering이 기존 테스팅과 근본적으로 다른 3가지 차이

Harness Engineering은 기존 소프트웨어 테스팅을 개선한 것이 아닌, AI 에이전트의 고유한 속성에서 비롯된 **AI-native 패러다임**입니다. 기존 QA가 "버그가 없는가(결함 부재)?"를 묻는다면, Harness Engineering은 "지금 이 조건에서 배포해도 되는가(배포 준비도)?"를 코드로 선언하고 자동으로 판정합니다. 이 근본적 전환을 만드는 세 가지 구조적 차이가 있습니다.

### 차이 ①: 결정론적 pass/fail → 통계적 배포 판정

전통 소프트웨어 테스트는 "이 입력에 대해 이 출력이 나왔는가"를 판단합니다. 단위 테스트, 통합 테스트, E2E 테스트 모두 예상 출력을 하드코딩하고 비교합니다.

```python
# 출처: Evaluator_Examples/ch01_first_eval.py — 예제 코드
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

- **결정론적 테스트**: 전통 함수는 입력이 같으면 항상 동일한 출력을 반환하므로 `assert` 비교로 충분하다.
- **확률론적 테스트의 문제**: 에이전트는 의미적으로 동일한 답변도 표현이 달라 단순 문자열 비교가 실패한다.
- **Harness 해결책**: `AccuracyEvaluator`의 4중 가중 알고리즘(TokenF1·Jaccard·LCS·Char)으로 의미적 유사도를 계산해 단일 케이스 통과 여부 대신 **통계적 정확도 분포**로 판단한다.

에이전트의 응답은 의미적으로 동일해도 표현이 다를 수 있습니다. 단일 케이스 통과/실패 대신, **통계적 품질 분포**로 판단해야 합니다. "이번 실행에서 통과했는가"가 아니라 "1,000번 실행했을 때 90% 이상 정확한가"가 올바른 질문입니다.

### 차이 ②: 단일 실행 검증 → 반복 통계 검증

전통 테스트는 각 케이스를 한 번씩 실행합니다. 에이전트는 실행할 때마다 다른 결과를 낼 수 있어, 단일 실행 테스트는 비결정론적 동작을 놓칩니다.

| 테스트 방식 | 전통 소프트웨어 | AI 에이전트 |
|-----------|-------------|-----------|
| 케이스 반복 | 불필요 (결정론적) | 필수 (확률론적) |
| 결과 판단 | 정확히 일치 | 임계값 기반 통계 |
| 재현 가능성 | 항상 재현 | 확률적 재현 |
| 실패 정의 | 하나라도 실패 | N% 이상 성공 |

`ReproducibilityConfig`의 `reproducibility_threshold`는 이 문제를 해결합니다. "같은 입력에 대해 70% 이상 일관된 응답을 생성하는가"를 자동 판정합니다.

### 차이 ③: 배포 후 드리프트의 미탐지

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

> 👨‍💻 **개발자 TIP**: 세 차이의 공통 대응은 **지속 평가**입니다. 배포 전 1회 테스트가 아닌, 프로덕션에서도 계속 측정하는 루프가 Harness Engineering의 핵심입니다. 이것이 Harness Engineering이 Context Engineering 다음에 나타난 이유이기도 합니다 — Context Engineering이 입력을 아무리 정교하게 구성해도, 에이전트가 프로덕션에서 실제로 어떻게 동작하는지는 사후 측정(Sensor)과 코드 선언 기준(Guide)이 없으면 알 수 없습니다.

이 세 가지 차이는 "왜 AI 에이전트 평가가 새로운 패러다임을 필요로 하는가"에 대한 구조적 설명입니다. 이 차이에서 AI Native 환경 특유의 구체적인 도전들이 파생됩니다.

---

## 1.5 AI Native 평가의 5가지 고유 도전

### AI First vs AI Native — 평가 패러다임의 출발점

AI 에이전트 평가를 논하기 전에, 먼저 두 용어를 구분해야 합니다.

**AI First**는 기존의 소프트웨어·조직·프로세스에 AI 기능을 *추가*하는 접근입니다. 기존 워크플로우가 선행하고, AI가 그것을 보조하거나 자동화합니다. 평가도 마찬가지입니다 — 기존 QA 방법론 위에 AI 관련 테스트를 추가합니다. 더 나은 프롬프트를 테스트하고, LLM 출력을 수동으로 검토하고, 모델 버전을 A/B 비교하는 방식입니다. 소프트웨어 중심의 사고방식이 그대로 유지됩니다.

**AI Native**는 프로세스 자체를 AI 에이전트를 중심으로 *처음부터* 설계하는 접근입니다. AI가 보조 도구가 아닌 핵심 실행 주체입니다. 에이전트는 사람이 하던 일을 직접 수행하고, 자율적으로 도구를 선택하며, 멀티스텝 추론을 통해 목표를 추구합니다. 소프트웨어가 AI를 포함하는 것이 아니라, AI가 소프트웨어 구조를 결정합니다.

이 차이는 평가에 근본적인 함의를 가집니다. **AI First 평가는 기존 QA를 확장하는 문제**이고, **AI Native 평가는 새로운 패러다임을 필요로 합니다.** 에이전트의 고유한 속성들이 기존 테스팅의 전제를 무너뜨리기 때문입니다.

### AI Native 평가의 어려움과 한계

AI Native 환경의 평가는 기술적으로 해결되지 않은 영역을 포함합니다.

| 어려움 | 이유 | 현재 한계 |
|--------|------|----------|
| **비결정론적 출력** | 동일 입력에도 매번 다른 응답 | 단일 테스트 케이스로 품질 확정 불가 |
| **Ground Truth 부재** | 복잡한 태스크에서 "정답"이 하나가 아님 | 자동 채점 정확도가 인간 판단과 乖離 |
| **평가 비용** | LLM-as-Judge는 API 비용 발생 | 프로덕션 전량 평가 불가, 샘플링 필수 |
| **순환 참조 문제** | AI로 AI를 평가할 때 Judge 편향 내재 | Judge 모델 자체의 신뢰도를 어떻게 보장하는가 |
| **드리프트 탐지 지연** | 성능 저하가 점진적·무증상으로 발생 | 임계값 돌파 전 조기 감지가 어려움 |
| **돌발 행동** | 설계하지 않은 동작이 예상치 못하게 등장 | 사전 테스트 케이스로 커버 불가 |
| **다중에이전트 복잡성** | 에이전트 수 증가 시 상호작용 경우의 수 폭발 | 전수 테스트가 계산적으로 불가능 |

이 어려움들은 "더 좋은 도구"로 완전히 해소되지 않습니다. Harness Engineering은 이 한계를 인정하면서 **통계적 배포 판정** — "완벽한 검증" 대신 "충분히 높은 신뢰 수준" — 을 목표로 설계됩니다.

### 5가지 고유 도전 — AI Native 환경의 실전 문제

전통 소프트웨어 QA 경험이 있는 엔지니어가 AI 에이전트 평가를 처음 시작할 때 부딪히는 5가지 고유한 도전이 있습니다.

### 도전 ①: 확률론적 품질 (Probabilistic Quality)

동일 입력 → 비결정론적 출력. 기존 assert 기반 테스트는 의미가 없습니다.

**해결**: TokenF1 + Jaccard + LCS + Char Levenshtein 4중 가중 알고리즘으로 **의미적 유사도**를 측정. 단일 케이스 통과 여부 대신 **평균 정확도 분포**로 판단합니다.

```
기존 방식: assert response == "서울입니다."    # ❌ 표현이 조금만 달라도 실패
Harness 방식: accuracy_score ≥ 0.85           # ✅ 의미가 같으면 통과
```

### 도전 ②: AI-by-AI 평가 (AI Evaluating AI)

에이전트 응답의 품질을 자동으로 채점하려면 또 다른 LLM이 필요합니다. 이를 LLM-as-Judge라고 합니다. 하지만 채점 LLM 자체도 편향이 있고, API 호출 비용이 발생합니다.

**해결**: `LLMJudge`는 **샘플링(기본 10%)** 방식으로 비용을 제어합니다. 기본 5차원(completeness·relevance·factual_consistency·toxicity·bias)으로 ground_truth 없이 품질을 측정하며, RAG 모드 활성화 시 faithfulness, 커스텀 기준(judge_criteria) 지정 시 criteria_scores/criteria_overall이 추가됩니다.

```python
judge = LLMJudge(sample_rate=0.1)  # 10%만 LLM 채점, 나머지는 네이티브 알고리즘
```

- **`sample_rate=0.1`**: 전체 태스크의 10%만 LLM으로 채점해 API 비용을 90% 절감한다.
- **나머지 90%**: 외부 API 호출 없이 네이티브 알고리즘(TokenF1·Jaccard·LCS)으로 즉시 계산된다.
- **자동 모델 결정**: `model=None`(기본값)이면 환경에 설정된 API 키를 기반으로 OpenAI 또는 Anthropic 모델을 자동 선택한다.

### 도전 ③: 드리프트 인식 (Drift Awareness)

모델·데이터·환경의 변화가 코드 변경 없이 에이전트 동작을 바꿉니다.

**해결**: `RunTrendAnalyzer`가 순차 평가 결과의 기울기를 자동 계산합니다. TCR이 지속적으로 감소하는 추세를 감지하면 경보를 발령합니다.

```
평가 결과 시계열: [0.92, 0.91, 0.89, 0.86, 0.82, ...]
slope = -0.025/평가 → 드리프트 감지 → CI 경보
```

### 도전 ④: 돌발 행동 대응 (Emergent Behavior)

설계하지 않은 동작이 에이전트에서 예상치 못하게 등장합니다. 특히 도구 체인이 길어질수록, 멀티에이전트 시스템일수록 예측 불가능한 상호작용이 발생합니다.

**해결**: `AnomalyDetector`가 통계적 정상 범위를 학습하고 이탈 시 즉시 탐지합니다. `ToolChainAttackDetector`는 도구 체인에서 발생하는 비정상 연쇄 호출을 추적합니다.

```python
# 출처: Evaluator_Examples/ch01_first_eval.py — PerformanceMonitor 설정
# 도구 체인 이상 탐지 — 정상적이지 않은 연쇄 패턴을 자동 감지
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,   # Gate E 활성화
    enable_anomaly_detection=True,  # 돌발 행동 감지
)
```

- **`enable_security_metrics=True`**: Gate E(보안경계) — `InputSanitizationTracker`, `OutputLeakageDetector`, `ToolAuthorizationTracker`, `PrivilegeEscalationDetector`, `ToolChainAttackDetector` 5개 트래커를 활성화한다.
- **`enable_anomaly_detection=True`**: `AnomalyDetector`가 통계적 정상 범위를 학습하고, 도구 호출 횟수·응답 시간 등이 비정상적으로 이탈할 때 자동으로 탐지한다.
- **opt-in 설계**: 두 옵션 모두 기본값 `False`이며, 활성화하면 태스크당 측정 오버헤드가 증가하므로 필요할 때만 켠다.

### 도전 ⑤: 지속 평가 (Continuous Evaluation)

AI 에이전트는 배포 후에도 계속 변합니다. 일회성 배포 전 테스트만으로는 충분하지 않습니다.

**해결**: `evaluation_session` 컨텍스트 매니저 + `agent-eval trend` + Phoenix OTEL을 결합한 **자기개선 루프**를 구성합니다.

```
[운영] 실시간 평가 → [이상 탐지] 드리프트 경보 → [원인 분석] LLMJudge·Phoenix
→ [개선] 프롬프트/모델 교체 → [검증] HarnessEvaluationGate 재통과 → [배포]
```

### AI Native 5대 도전 ↔ Harness Gate A–G 매핑

5가지 도전은 추상적인 문제가 아닙니다. Harness Engineering의 7개 Gate(A–G)가 각 도전에 정확히 대응합니다. 5가지 도전은 7개 Gate 중 6개(A·B·C·D·E·G)를 직접 유발하고, Gate F(다중에이전트 협업)는 단일 에이전트 시스템에서는 나타나지 않는 멀티에이전트 고유의 추가 차원입니다.

| AI Native 도전 | 핵심 질문 | 대응 Gate | 주요 Tracker / Config |
|--------------|---------|-----------|----------------------|
| ① 확률론적 품질 | "통계적으로 충분히 정확한가?" | **Gate A** 목표달성, **Gate C** 신뢰성 | AccuracyEvaluator, ReproducibilityConfig |
| ② AI-by-AI 평가 | "LLM Judge 비용 없이 품질을 측정할 수 있는가?" | **Gate G** 운영관측성 | LLMJudge (sample_rate 조절), ExplainabilityConfig |
| ③ 드리프트 인식 | "배포 후 성능 저하를 조기에 감지하는가?" | **Gate D** 성능계약, **Gate C** 신뢰성 | LatencyTracker, RunTrendAnalyzer, CostPredictabilityConfig |
| ④ 돌발 행동 대응 | "예측 못한 도구 호출·루프·범위 이탈을 탐지하는가?" | **Gate B** 행동무결성, **Gate E** 보안경계 | ToolChainAttackDetector, AnomalyDetector, ScopeConfig |
| ⑤ 지속 평가 | "배포 후에도 지속적으로 품질을 검증하는가?" | **Gate A–G 전체** (CI/CD + 실시간 모니터링) | HarnessEvaluationGate, Phoenix OTEL, agent-eval trend |
| *(멀티에이전트 고유)* | "여러 에이전트가 교착 없이 협력하는가?" | **Gate F** 다중에이전트 | AgentCoordinationTracker, ConsensusConfig |

**개발자 관점**: 각 도전에 대응하는 Tracker를 활성화하고 Config로 기준을 선언합니다.  
**QA 관리자 관점**: 도전이 해결됐는지를 Gate A–G별 PASS/WARN/FAIL 판정으로 확인합니다.

> 📋 **QA 관리자 TIP**: AI Native 5가지 도전은 전통 QA 역할을 없애지 않습니다. "케이스를 통과했는가" 대신 "품질 분포가 배포 기준을 만족하는가"로 판단 언어를 바꾸는 것입니다. Part IV — QA 관리자 가이드에서 이 전환을 단계별로 다룹니다.

5가지 도전을 정의했으니, 자연스럽게 이어지는 질문이 있습니다. **시장에는 이미 다양한 평가 도구가 존재합니다. 그 중 어떤 도구가 이 도전들을 실제로 해결하는가?**

---

## 1.6 AI 에이전트 평가 프레임워크 생태계 — 9개 도구 비교표

앞서 정의한 5가지 AI Native 도전 — 확률론적 품질, AI-by-AI 평가, 드리프트, 돌발 행동, 지속 평가 — 은 기존 도구들이 해결하지 못한 지점이기도 합니다. 현재 시장에 다양한 평가 도구가 존재하지만, 각 도구가 이 도전에 어떻게 대응하는지를 비교하면 팀 상황에 맞는 선택 기준이 명확해집니다.

### 주요 도구 개요

| 프레임워크 | 유형 | 버전 (2025-2026) | 주력 기능 |
|---|---|---|---|
| **LangSmith** | SaaS + 셀프호스트 | SDK v0.7.33 | LangChain 생태계 관측 |
| **Ragas** | OSS 라이브러리 | v0.4.3 | RAG + 에이전트 평가 |
| **DeepEval** | OSS + SaaS | v3.9.7 | LLM 단위 테스트 (Red-team → DeepTeam으로 분리) |
| **Arize Phoenix** | OSS + Cloud | v14.10.0 | LLM 관측가능성 (OTEL 기반) |
| **Evidently AI** | OSS + Cloud | v0.7.21 | ML/LLM 모니터링 |
| **Braintrust** | SaaS + OSS SDK | v0.16.0 | LLM 실험 + 에이전트 관측 |
| **Helicone** | SaaS + OSS | — | LLM 프록시 + 비용 관측 |
| **W&B Weave** | SaaS + OSS SDK | v0.52.37 | 에이전트 평가 + 실험 관리 |
| **Agent Evaluator** | OSS SDK | v0.8.5 | Harness Engineering 배포 판단 |

### 에이전틱 지표 지원 비교

에이전트 평가에서 가장 중요한 것은 일반 LLM 품질 지표가 아닌, 에이전트 고유의 동작을 측정하는 지표입니다.

| 지표 | LangSmith | Ragas | DeepEval | Phoenix | Evidently | Braintrust | Helicone | W&B | Agent Evaluator |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Tool 선택 정확도 | ❌ | ✅ | ⚠️ LLM-judge | ⚠️ LLM-judge | ❌ | ❌ | ❌ | ❌ | ✅ |
| Tool 효율성 / 불필요 호출 | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 재시도 / 자기수정 패턴 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 멀티에이전트 협업 품질 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 워크플로우 퍼널 / 분기 | ✅ (LangGraph) | ❌ | ❌ | ✅ | ❌ | 부분 | ❌ | 부분 | ✅ |
| 프롬프트 인젝션 탐지 | ❌ | ❌ | ⚠️ DeepTeam | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
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

도구를 선택했다면, 이제 그 도구들이 사용하는 지표들이 어떤 역사적 과정을 거쳐 발전했는지를 이해할 차례입니다. 각 지표가 등장한 이유와 그 한계를 알면 "왜 Token F1인가", "왜 LLM Judge가 필요한가"에 대한 답이 나올 뿐 아니라, 왜 단일 지표가 아닌 Harness Engineering처럼 다차원 구조가 필요해졌는지가 역사적 맥락에서 자연스럽게 이해됩니다.

### 참조 기반 지표 시대 (2002–2017)

**BLEU** (Papineni et al. 2002)는 기계 번역 품질을 인간 참조 번역과의 n-gram 정밀도로 측정하는 최초의 자동화 지표였습니다. 빠르고 재현 가능하지만 **정밀도(Precision)만 측정**하고 의미적 동의어를 인식하지 못한다는 근본적 한계를 가집니다.

**ROUGE** (Lin 2004)는 문서 요약을 위해 **재현율(Recall) 중심**으로 설계됐습니다.

> 🔧 **Agent-Evaluator의 대응** — BLEU/ROUGE 대신 **Token F1**(Precision+Recall 균형)을 핵심 지표로 채택하고, 4개 서브지표(Token F1 + Jaccard + LCS + Char Levenshtein) 조합으로 단일 지표의 맹점을 보완합니다. (→ Gate A 목표달성 §4.2)

### 의미 유사도의 부상 (2018–2021)

**BERTScore** (Zhang et al. 2019)는 BERT 임베딩 공간에서 코사인 유사도를 계산해 의미적 유사도를 측정합니다. 동의어와 패라프레이즈를 자동 처리하며 인간 판단과의 상관이 BLEU보다 높습니다. 그러나 **GPU 메모리와 추론 시간**이 필요합니다.

> 🔧 **Agent-Evaluator의 대응** — 프로덕션 모니터링에서 매 요청마다 BERTScore를 계산하는 것은 비현실적입니다. 외부 의존성 없이 <1ms로 동작하는 4중 가중 알고리즘을 기본으로 제공하고, 정밀 평가가 필요한 경우에만 LLM Judge를 샘플링 방식으로 추가합니다.

### LLM-as-Judge의 등장 (2022–현재)

**HELM** (Liang et al. 2022)은 42개 시나리오 × 7개 지표로 정확성·강건성·공정성·독성을 동시 측정하는 종합 벤치마크입니다. **MT-Bench**와 **Chatbot Arena** (Zheng et al. 2023)는 각각 GPT-4로 멀티턴 응답을 채점하는 **LLM-as-Judge** 방식과, 익명 인간 평가자의 쌍대 비교를 기반으로 한 **Elo 인간 선호도 랭킹**으로 LLM 평가 패러다임을 정착시켰습니다.

> 🔧 **Agent-Evaluator의 대응** — `LLMJudge` 클래스가 이 패러다임을 구현합니다. completeness·relevance·factual_consistency·toxicity·bias 5차원을 ground_truth 없이 채점하며, RAG 모드에서는 faithfulness 차원이 추가됩니다. DeepEval G-Eval의 커스텀 기준(`judge_criteria`)도 외부 패키지 없이 지원합니다. (→ Gate G 운영관측성 §10.2)

### AI 평가 발전 요약

| 지표 | 연도 | 핵심 기여 | 한계 |
|---|---|---|---|
| BLEU | 2002 | 최초의 자동화 번역 평가 | Precision 편향, 동의어 불인식 |
| ROUGE | 2004 | 요약 평가 표준화 | Recall 편향, 의미 무시 |
| BERTScore | 2019 | 의미적 유사도 측정 | GPU 필요, 느리고 무거움 |
| HELM | 2022 | 종합 벤치마크, 다축 측정 | 정적 기준, 에이전트 동작 미측정 |
| MT-Bench / LLM-as-Judge | 2023 | 인간 판단 대리, 유연한 기준 | 비용, judge 편향 |
| **Agent-Evaluator** | **2024** | **4중 가중 알고리즘(빠름) + LLM Judge 샘플링(정밀) + 33개 Harness Config(배포 판단)** | **Beta** |

> 📖 **더 깊이**: 각 지표의 수식은 → Appendix H §H.1 (수학적 상세 레퍼런스), 지표 간 한계 비교는 → Appendix I §I.1 (정확도 지표 심층 비교)

---

> **이 챕터의 핵심**
>
> - AI 에이전트는 입력→출력 1회의 LLM과 달리, 도구 호출·멀티스텝·상태·반복 동작으로 평가 복잡성이 근본적으로 다릅니다.
> - 환각·보안 위협·레이턴시 급증은 평가 체계 없이는 배포 후에야 발견되는 전형적인 실패 패턴입니다. 각각 Gate C·E·D 차원의 문제입니다.
> - **Harness Engineering**은 Tracker(실행 중 자동 측정) × Config(배포 기준 코드 선언) × Gate(종합 배포 판정)의 3요소로 작동합니다. 세 역할은 독립적으로 설계되어 있어 각각 교체·확장·제거할 수 있습니다.
> - 58개 지표(25 Tracker + 33 Config)는 서로 독립적인 7개 배포 관문 Gate A-G로 구조화됩니다.
> - AI Native 평가의 5가지 고유 도전(확률론적 품질·AI-by-AI 평가·드리프트·돌발 행동·지속 평가)은 기존 소프트웨어 테스팅 방법론으로 해결되지 않습니다.
> - 에이전트 평가 도구 생태계에서 Harness Config 기반 배포 판정과 에이전틱 전용 지표를 LLM 없이 제공하는 도구는 Agent Evaluator가 유일합니다.
>
> **→ Chapter 2**: 이 개념들을 실제 코드로 경험합니다. `pip install`부터 첫 `PASS/FAIL` 배포 판정까지 5분 안에 완료할 수 있으며, Tracker·Config·Gate가 코드에서 어떻게 보이는지 직접 확인합니다. Chapter 3에서는 그 내부 설계 원리를 자세히 탐구합니다.

---

## 실전 예제

이 챕터에서 설명한 4가지 논점을 `ch01_first_eval.py` 하나로 순서대로 실행할 수 있습니다. API 키 없이 즉시 동작합니다.

**기본 예제**: `Evaluator_Examples/ch01_first_eval.py`

```bash
python Evaluator_Examples/ch01_first_eval.py
```

| 섹션 | 대응 챕터 내용 | 핵심 API | 결과 파일 |
|---|---|---|---|
| 섹션 1 | §1.4 한계① — assert 함정 | `create_taskresult` → 정확도 점수 비교 | `ch01_first_eval.json` |
| 섹션 2 | §1.2 사례① — RAG 환각 | `@agent_eval` + `context_arg` + HallucinationDetector | `ch01_hallucination_eval.json` |
| 섹션 3 | §1.2 사례③ — SLA 위반 | `@agent_eval` + `SLAConfig(p95_ms=2000)` | `ch01_sla_eval.json` |
| 섹션 4 | §1.3 — Harness 3요소 | `InstructionConfig` + `SLAConfig` → Gate 배포 판정 | `ch01_harness_eval.json` |
| 섹션 5 | L1 트래커 직접 사용 | 6개 트래커 독립 인스턴스화 — PerformanceMonitor 없이 직접 호출 | (콘솔 출력) |

결과를 대시보드에서 확인하려면:

```bash
agent-eval dashboard --results results/
```

Ch02에서는 이 패턴을 더 단순하게 시작하는 `QuickEval`을 소개합니다.

**L1 트래커 직접 사용**

`PerformanceMonitor`는 내부적으로 6개 L1 트래커를 자동 관리한다. 세밀한 제어가 필요할 때는 트래커를 직접 인스턴스화할 수 있다.

```python
# 출처: Evaluator_Examples/ch01_first_eval.py, 섹션 5 — L1 트래커 직접 사용
from agent_evaluator import (
    TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
    ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker,
    create_taskresult,
)

# [1] TaskCompletionTracker — 작업 완료율(TCR) 계산
tcr_tracker = TaskCompletionTracker()
for t in [
    create_taskresult("t1", "서울의 날씨는?", "맑고 22도", "맑고 22도", 0.3, task_type="qa"),
    create_taskresult("t2", "파이썬 GIL이란?", "전역 인터프리터 잠금", "전역 인터프리터 잠금", 0.5, task_type="qa"),
]:
    tcr_tracker.add_task(t)
tcr = tcr_tracker.calculate_tcr()
# tcr["tcr"] → 100.0  |  tcr["total_tasks"] → 2

# [2] AccuracyEvaluator — QA 정확도 직접 계산
acc_eval = AccuracyEvaluator()
acc_eval.add_evaluation("t_a1", ground_truth="서울", prediction="서울입니다", task_type="qa")
acc_eval.add_evaluation("t_a2", ground_truth="파이썬", prediction="자바입니다", task_type="qa")
scores = acc_eval.get_accuracy_scores()
# scores["overall_accuracy"] → 0~100 (%)  |  scores["median_accuracy"] → 중앙값

# [3] HallucinationDetector — 환각 탐지 직접 호출
hd = HallucinationDetector()
ctx = "파이썬은 1991년 귀도 반 로섬이 개발한 범용 프로그래밍 언어입니다."
hd.detect_hallucination("t_h1", response="파이썬은 1991년 귀도가 개발한 언어입니다.", context=ctx)
hd.detect_hallucination("t_h2", response="파이썬은 2005년 구글이 개발했습니다.", context=ctx)
# hd.detections[n]["hallucination_rate"] → 0.0~1.0  |  ["unsupported_sentences"] → 수

# [4] ResponseQualityEvaluator — 5차원 응답 품질 평가
rqe = ResponseQualityEvaluator()
quality = rqe.evaluate_response(
    task_id="t_q",
    response="파이썬은 범용 프로그래밍 언어로 데이터 과학, 웹 개발에 쓰입니다.",
    request="파이썬이란?",
    expected_elements=["프로그래밍", "데이터"],
)
dims = quality.get("dimension_scores", {})
# quality["total_score"] → 0~5  |  dims["relevance"], dims["completeness"] → 각 차원 점수

# [5] LatencyTracker — 레이턴시 백분위 계산
lat_tracker = LatencyTracker()
for i, t in enumerate([0.12, 0.45, 0.23, 1.80, 0.31, 0.67, 0.18, 0.92]):
    lat_tracker.record_latency(f"t_l{i}", "qa", total_time=t,
                               breakdown={"retrieval": t * 0.3, "llm": t * 0.7})
lat_stats = lat_tracker.get_latency_stats()
# lat_stats["p50"], ["p95"], ["p99"], ["mean"] → 백분위·평균 (초 단위)

# [6] TokenEconomyTracker — 토큰 비용 추적
tok_tracker = TokenEconomyTracker(pricing={"input": 0.003, "output": 0.015})
tok_tracker.track_usage("t_tok", input_tokens=400, output_tokens=100,
                         task_type="qa", model="claude-sonnet-4-6")
tok_stats = tok_tracker.get_usage_stats()
# tok_stats["total_tokens"], ["total_cost"], ["avg_cost_per_task"]
```

- 6개 L1 트래커는 `PerformanceMonitor` 없이 독립적으로 사용할 수 있어 독립 서비스·배치 분석·커스텀 파이프라인에 유용하다.
- `get_accuracy_scores()["overall_accuracy"]`는 0–100 % 스케일이다 (소수 아님).
- `ResponseQualityEvaluator.evaluate_response()`의 차원 점수는 최상위 키가 아닌 `["dimension_scores"]` 중첩 딕셔너리 안에 있다.

```python
# 출처: Evaluator_Examples/ch01_first_eval.py, 섹션 2 — Gate B Behavioral Integrity
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

# 데코레이터가 Gate A(Accuracy) + Gate B(ToolCall) + Gate F(ToolSelection F1)를 자동 측정
tool_agent("2024년 GDP 상위 5개국은?", ground_truth="미국, 중국, 독일, 일본, 인도")
```

- **`EvalMetadata`**: 응답 텍스트와 함께 `tool_calls`·`expected_tools` 등 메타데이터를 반환하면 `@agent_eval`이 자동으로 파싱해 트래커에 전달한다.
- **`tool_calls`**: 실제로 호출한 도구 목록 — `ToolCallAnalyzer`(Gate B)와 `ToolSelectionTracker`(Gate F)가 분석한다.
- **`expected_tools`**: 기대 도구 목록과 실제 호출을 F1 점수로 비교해 도구 선택 정확도를 측정한다.
- **자동 측정 범위**: 단일 데코레이터 하나로 Gate A(정확도·TCR), Gate B(도구 패턴), Gate D(레이턴시), Gate F(도구 선택 F1)가 동시에 기록된다.

```bash
# Gate A/C/D — 목표달성·신뢰성·성능계약 측정
python Evaluator_Examples/ch01_first_eval.py

# Gate B/E/F — 행동무결성·보안경계·다중에이전트 측정
python Evaluator_Examples/ch05_group_b.py
```

**Gate A-G와 예제 매핑**

| Gate | 차원 | 측정 지표 | 예제 파일·섹션 |
|------|------|----------|---------------|
| A | 목표달성 | AccuracyEvaluator (TokenF1·Jaccard·LCS), TCR | ch01_first_eval, ch04_group_a |
| B | 행동무결성 | ToolCallAnalyzer, WorkflowExecutionTracker | ch05_group_b |
| C | 신뢰성 | HallucinationDetector, RetryCorrectionTracker | ch01_first_eval, ch06_group_c |
| D | 성능계약 | LatencyTracker (p95), TokenEconomyTracker | ch07_group_d |
| E | 보안경계 | InputSanitization, OutputLeakage, ToolAuth | ch08_group_e |
| F | 다중에이전트 | AgentCoordinationTracker, ToolSelectionTracker | ch09_group_f |
| G | 운영관측성 | LLMJudge(5차원 기본, RAG/G-Eval 옵션), Phoenix OTEL | ch10_group_g, ch19_phoenix |

**실행 결과 (v0.8.5 기준)**

```
# ch01_first_eval.py
TCR=43.1% | 54개 태스크 | p95_latency=5.20s | avg_accuracy=59.82%

# ch05_group_b.py
TCR=41.4% | 14개 태스크 | 보안 위협 3건 탐지
  - SQL Injection 시도 탐지 (Gate E — InputSanitizationTracker)
  - 민감 데이터 노출 탐지 (Gate E — OutputLeakageDetector)
  - 무단 도구 사용 탐지 (Gate E — ToolAuthorizationTracker)
```

> **첫 실행 팁**: 두 파일 모두 API 키 없이 실행됩니다. `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`를 `.env`에 추가하면 LLMJudge(Gate G)가 활성화되어 `completeness`, `relevance`, `factual_consistency` 세 차원이 추가로 측정됩니다.

**프레임워크 어댑터 — 실제 프레임워크 응답에서 Gate별 지표 자동 추출**

`framework=` 파라미터 하나로 LangChain·LangGraph·CrewAI·AutoGen 응답 객체에서 tool_calls·agent_interactions·tokens_used를 자동 추출한다. 실제 SDK 없이도 mock 응답 객체로 동작한다(duck typing).

```python
# 출처: Evaluator_Examples/ch01_first_eval.py, 섹션 1 — LangChain 어댑터
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
        intermediate_steps=steps,            # → Gate B ToolCallAnalyzer 자동 연결
        usage_metadata={"input_tokens": 350, "output_tokens": 120},  # → TokenEconomyTracker
    )

langchain_agent("GDP 상위 5개국은?", ground_truth="미국, 중국, 독일, 일본, 인도")
# Gate A: accuracy_score 자동 계산 (TokenF1·Jaccard·LCS)
# Gate B: tool_calls=[web_search, calculator] 자동 기록
# Gate D: tokens_used={input:350, output:120} 자동 기록
```

- **`framework="langchain"`**: LangChain AgentExecutor 응답에서 `intermediate_steps`(도구 호출 목록)와 `usage_metadata`(토큰 사용량)를 자동으로 파싱한다.
- **`SimpleNamespace` 사용**: 실제 LangChain SDK 없이도 duck typing으로 동작하므로 테스트 환경에서도 mock 객체로 프레임워크 어댑터를 검증할 수 있다.
- **자동 연결 범위**: `intermediate_steps` → Gate B `ToolCallAnalyzer`, `usage_metadata` → Gate D `TokenEconomyTracker`로 데이터가 자동 라우팅된다.

**버전 비교 — Harness Gate로 "어느 버전을 배포할지" 결정**

```python
# 출처: Evaluator_Examples/ch01_first_eval.py — v1 vs v2 Gate 점수 비교
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

- **독립 monitor**: `monitor_v1`과 `monitor_v2`를 분리해 Gate 간 데이터 교차 오염 없이 동일 테스트 케이스를 각각 평가한다.
- **`harness_groups` 경로**: `report.to_dict()["extra_metrics"]["harness_groups"]`에 Gate A–G별 `score`, `status`, `gate` 필드가 저장된다.
- **배포 결정 로직**: `v2_fail`이 빈 리스트(`[]`)이면 모든 Gate를 통과한 것이므로 v2 배포를 승인하고, v1은 차단한다.
- **`enable_security_metrics=True`**: 두 버전 모두 Gate E(보안경계) 지표를 포함해 동등한 조건에서 비교한다.
