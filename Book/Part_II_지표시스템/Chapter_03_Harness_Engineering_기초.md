# Chapter 3. Harness Engineering 기초

Chapter 2에서 `QuickEval`과 `@eval.qa` 데코레이터로 첫 배포 판정을 경험했다. `@eval.qa`를 붙이는 순간 Tracker가 자동 활성화됐고, `eval.gate(tcr=80)`이 Gate를 실행했으며, `SLAConfig`를 추가하면 Config가 합류했다. 동작은 경험했지만 아직 "왜 이렇게 설계됐는가"는 설명하지 않았다.

이 챕터는 그 설계 원리를 다룬다. Tracker·Config·Gate 세 역할을 동등한 깊이로 분해하고, 58개 지표가 7개 Gate로 구조화된 논리를 설명한다. 이후 **Chapter 4~10**에서 Gate A-G를 각각 탐구하기 위한 공통 기반이 된다.

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 각 Tracker와 Config의 입력·출력·임계값 기본값 한눈에 조회
> - **[Appendix G — AI 품질 평가 이론적 기초](../Appendix/G_AI평가_이론적기초.md)**: Harness Engineering 설계 철학의 이론적 배경
> - **[Appendix A §Part 2 — 33개 Harness Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: 파라미터 상세 레퍼런스
> - **[Evaluator_Examples/ch03_harness_basics.py](../../Evaluator_Examples/ch03_harness_basics.py)**: 이 챕터 실전 예제 (7개 Gate PASS 시나리오 · 33개 Config 실전 시연)

---

## 3.1 Harness Engineering이란 무엇인가

> *"Agent = Model + Harness"*  
> — Mitchell Hashimoto (HashiCorp 공동창업자)

**Harness Engineering**은 자율 AI 에이전트를 **외부에서 제어·측정·검증하는 시스템 전체**를 설계하는 공학 분야다. 모델 자체(가중치, 추론 엔진)를 제외한 모든 것 — 지시 구조, 제약 선언, 품질 측정, 배포 판정 — 이 Harness에 속한다.

이 정의는 소프트웨어 공학자 Martin Fowler가 제시한 것과 일치한다.

> *"The harness is the system and control structure around a coding agent — everything except the model itself."*  
> — Martin Fowler

Harness Engineering을 이해하려면 AI 최적화 방법론이 어떻게 진화해왔는지를 먼저 살펴봐야 한다. 이 방법론은 세 단계를 거쳐 발전했다.

### 3.1.1 AI 최적화 방법론의 3단계 진화

#### 1단계: Prompt Engineering (2022–2024)

LLM 등장 초기의 최적화는 **프롬프트 자체를 정교하게 설계**하는 데 집중됐다. 같은 모델이라도 프롬프트를 어떻게 작성하느냐에 따라 출력 품질이 크게 달라진다는 사실이 밝혀지면서, Few-shot prompting, Chain-of-Thought(CoT), 역할 페르소나 설정 같은 기법이 급속히 발전했다.

그러나 Prompt Engineering은 **단일 LLM 호출**에 특화된 최적화다. 에이전트가 여러 도구를 호출하고, 멀티턴 대화를 유지하고, 외부 시스템과 연동하는 복잡한 시나리오에서는 "어떻게 질문하느냐"만으로는 한계에 부딪혔다.

#### 2단계: Context Engineering (2025)

Prompt Engineering의 한계를 돌파한 것이 **Context Engineering**이다. AI 연구자 Andrej Karpathy는 이를 이렇게 정의했다.

> *"Context Engineering is the delicate art and science of filling the context window with just the right information."*  
> — Andrej Karpathy

Context Engineering은 프롬프트 텍스트 하나가 아니라, **컨텍스트 창(context window)에 들어오는 모든 정보**를 관리 대상으로 삼는다.

| 관리 대상 | 구체적 내용 |
|----------|-----------|
| **시스템 프롬프트** | 역할 정의, 행동 지침, 제약 조건 |
| **외부 지식** | RAG 검색 결과, 문서 청크, 벡터 검색 |
| **메모리** | 단기 대화 이력, 장기 사용자 프로파일 |
| **도구 정보** | 사용 가능한 함수 스펙, 이전 호출 결과 |
| **구조화 출력** | JSON 스키마, 포맷 지정 |

Context Engineering은 에이전트 품질을 획기적으로 높였다. 그러나 여전히 해결하지 못하는 문제가 남아 있었다. **"에이전트가 실제로 어떻게 동작했는가"를 사후에 검증하고, 배포 가능 여부를 자동으로 판정하는 메커니즘**이 없었다.

#### 3단계: Harness Engineering (2026~)

Context Engineering이 모델에게 **무엇을 줄 것인가(입력 관리)**를 다룬다면, Harness Engineering은 **모델 주변의 제어 구조 전체(외부 통제 시스템)**를 설계한다.

| 구분 | Prompt Engineering | Context Engineering | Harness Engineering |
|------|-------------------|--------------------|--------------------|
| **최적화 대상** | 프롬프트 텍스트 | 컨텍스트 창 전체 | 에이전트 주변 제어 구조 |
| **관심 시점** | 호출 이전 (사전 설계) | 호출 이전 (입력 구성) | 호출 전후 (사전+사후 제어) |
| **핵심 질문** | "어떻게 물어볼까?" | "무엇을 넣어줄까?" | "어떤 조건에서 배포 가능한가?" |
| **적용 범위** | 단일 LLM 호출 | 단일~다중 호출 | 자율 에이전트 전체 생명주기 |
| **검증 방식** | 수동 평가 | 수동+부분 자동 | 코드로 선언된 자동 판정 |

Harness Engineering은 단순한 테스트 프레임워크가 아니다. Shopify CEO Tobi Lütke가 사내 AI 정책에서 선언한 것처럼, 에이전트를 자율적으로 신뢰하는 방향으로 나아가는 만큼, 그 자율성을 **외부에서 구조적으로 제어·검증할 수 있어야** 한다는 공학적 응답이다.

> *"Model is commodity, Harness is the moat."*  
> — Aakash Gupta (AI 제품 전략가)

모델 자체는 점점 상품화된다. 차별화는 **에이전트를 얼마나 신뢰할 수 있도록 제어·검증하느냐**에서 나온다.

#### Context Engineering이 해결하지 못한 문제: 배포 준비도 공백

Context Engineering은 에이전트에게 올바른 정보를 제공하는 데 탁월하다. RAG로 관련 문서를 검색하고, 대화 이력을 메모리에 보존하고, 도구 스펙을 컨텍스트 창에 정확히 구성한다. 그러나 이 모든 최적화는 **실행 이전(pre-execution)**에 작동한다.

실행이 끝난 후, 에이전트가 실제로:
- 정확한 정보를 반환했는지 (정확도가 기준을 충족하는지)
- SLA 내에서 응답했는지 (P95 지연이 계약 범위 안에 있는지)
- 보안 정책을 위반하지 않았는지 (프롬프트 인젝션이 통과됐는지)
- 이 상태로 프로덕션에 배포해도 되는지

…를 자동으로 판정하는 메커니즘은 Context Engineering의 영역 밖이다. 이 **배포 준비도 공백(deployment readiness gap)**을 채우는 것이 Harness Engineering의 존재 이유다.

Martin Fowler는 Harness Engineering을 세 가지 규제 도메인으로 분류한다:
- **유지보수성(Maintainability)**: 에이전트 코드가 지속적으로 관리 가능한가
- **아키텍처 적합성(Architecture Fitness)**: 에이전트가 설계된 시스템 경계 안에서 동작하는가
- **행동 Harness(Behavior Harness)**: 에이전트가 선언된 품질 기준을 실행마다 충족하는가

Agent-Evaluator는 이 중 세 번째 도메인 — **행동 Harness** — 을 Python SDK로 구현한다.

### 3.1.2 Harness Engineering의 작동 원리: Guides + Sensors

Harness Engineering은 두 가지 제어 메커니즘으로 구성된다.

**Guides (사전 제어, Feedforward)**는 에이전트가 실행되기 *전에* 작동하는 지침과 제약이다. 무엇을 해도 되고 무엇을 하면 안 되는지를 사전에 선언한다.

- 시스템 프롬프트의 행동 지침
- `AGENTS.md` 같은 에이전트 명세 파일
- 도구 호출 허용 목록(allowlist)
- 응답 언어·형식 제약

**Sensors (사후 제어, Feedback)**는 에이전트가 실행된 *후에* 작동하는 측정과 검증이다. 실제로 어떻게 동작했는지를 측정하고 기준과 비교한다.

- 정확도·환각 탐지 (AccuracyEvaluator, HallucinationDetector)
- 지연·비용 측정 (LatencyTracker, TokenEconomyTracker)
- 보안 패턴 탐지 (InputSanitizationTracker, OutputLeakageDetector)
- 행동 이상 감지 (ToolCallAnalyzer, WorkflowExecutionTracker)

아래 다이어그램은 Guides와 Sensors가 에이전트 실행을 감싸는 구조를 시각화한다. Guides가 실행 전 행동 범위를 선언하고, Sensors가 실행 후 측정값을 수집하며, Gate가 두 결과를 통합해 배포 판정을 내린다.

#### Agent-Evaluator의 Guides → Config, Sensors → Tracker 매핑

이 구조는 arXiv 논문 2604.17025(CAAF)에서 형식화된 것처럼, Harness를 **도메인 규칙을 기계가 읽을 수 있는 제약 레지스트리(constraint registry)로 구현하는 방식**으로 발전하고 있다. Agent-Evaluator에서 이 구조는 다음과 같이 구체화된다.

| Harness 개념 | Agent-Evaluator 구현 | 역할 |
|-------------|---------------------|------|
| **Guide** — 행동 제약 | `InstructionConfig`, `SLAConfig`, `LoopDetectionConfig`, `ComplianceConfig` 등 33개 Config 클래스 | 에이전트가 "무엇을 해야 하고 무엇을 하면 안 되는가"를 `@agent_eval` 데코레이터로 선언 |
| **Sensor** — 실행 측정 | `AccuracyEvaluator`, `LatencyTracker`, `HallucinationDetector`, `InputSanitizationTracker` 등 25개 Tracker 클래스 | 에이전트가 실행된 후 자동으로 지표를 수집·계산 |
| **Gate** — 통합 판정 | `HarnessEvaluationGate`, `agent-eval gate` CLI | Guide 위반 여부와 Sensor 측정값을 종합해 PASS / WARNING / FAIL 판정 |

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py
from agent_evaluator import PerformanceMonitor, InstructionConfig, SLAConfig
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor("results/")

@agent_eval(
    monitor,
    task_type="qa",
    # ① Guides — 실행 전 행동 제약 선언
    instructions=InstructionConfig(required_keywords=["결과"], fail_on_violation=True),
    sla=SLAConfig(p95_ms=2000, fail_on_violation=True),
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
    # ② Sensors — 실행 후 자동 측정
    # AccuracyEvaluator, LatencyTracker, TokenEconomyTracker 등이 자동 동작

# ③ Gate — Guides × Sensors 통합 판정
report = monitor.generate_report()
# → Gate A–G 중 위반 Config가 있으면 FAIL, 경계값이면 WARNING
```

### 3.1.3 핵심 3요소: Tracker · Config · Gate

Agent-Evaluator는 Harness Engineering의 Guides+Sensors 구조를 세 가지 요소로 구현한다.

| 요소 | Harness 역할 | AI 에이전트에서의 기능 |
|------|-------------|----------------------|
| **Tracker** | Sensor (사후 측정) | 에이전트 실행 중 품질 지표를 자동 수집 (TCR·정확도·지연·보안 등 25개) |
| **Config** | Guide (사전 제약 선언) | 배포 가능 기준을 코드로 선언 (33개 데이터클래스, `@agent_eval` 데코레이터로 주입) |
| **Gate** | 판정 (Guides + Sensors 통합) | Tracker 측정값과 Config 기준을 대조해 배포 승인/차단 판정 (7개 Gate A–G) |

세 요소가 결합하면 하나의 완전한 배포 검증 파이프라인이 완성된다.

**핵심 원칙은 "기준이 코드 안에 있어야 한다"는 것이다.** 품질 기준이 문서나 팀원의 암묵적 판단에 있으면, 릴리스마다 기준이 흔들리고 팀원 간 해석이 달라진다. Harness Config를 `@agent_eval` 데코레이터로 에이전트 코드 바로 옆에 선언하면, 에이전트가 자신의 배포 기준을 소유한다. 어떤 환경에서도 동일한 기준으로 반복 검증할 수 있다.

각 요소는 독립적으로도 사용 가능하다. Tracker만 단독으로 사용하면 관찰 인프라로 동작하고, Config를 추가하면 기준 검증이, Gate까지 연결하면 배포 자동화 판정이 가능해진다.

#### Agent-Evaluator 모듈 구조와의 매핑

3요소는 Agent-Evaluator 소스코드의 모듈 분리와 정확히 대응한다.

| 요소 | 핵심 모듈 | 진입 방법 |
|------|----------|---------|
| **Tracker** | `agent_evaluator/core/trackers/` — `layer1.py`(6종), `layer2.py`(5종), `security.py`(5종) | `PerformanceMonitor.record_task(result)` 호출 시 자동 실행 |
| **Config** | `agent_evaluator/decorators.py` — 33개 데이터클래스 정의 | `@agent_eval(monitor, sla=SLAConfig(...))` 데코레이터 파라미터 |
| **Gate** | `agent_evaluator/core/monitor.py` — `PerformanceMonitor`가 Harness 집계 | `HarnessEvaluationGate(report).evaluate()` 또는 `QuickEval.gate()` |

**`PerformanceMonitor`는 세 요소의 오케스트레이터다.** Tracker를 내부에 보유하고, Config를 `@agent_eval`을 통해 수신하며, Gate 판정에 필요한 집계를 자동으로 수행한다. 개발자는 Config를 선언하고 `record_task()`를 호출하는 것만으로 전체 Harness 파이프라인이 작동한다.

```python
# 3요소가 하나의 파이프라인으로 연결되는 최소 예시
from agent_evaluator import PerformanceMonitor, QuickEval, SLAConfig, InstructionConfig

# Tracker: PerformanceMonitor 내부에 자동 초기화
eval = QuickEval("results/")

# Config: 데코레이터로 선언 — 에이전트가 자신의 배포 기준을 소유
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000, fail_on_violation=True),
    instructions=InstructionConfig(required_keywords=["서울"], fail_on_violation=True),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Gate: Config 기준과 Tracker 측정값을 종합 판정
eval.gate(tcr=85, accuracy=70)   # 미달 시 sys.exit(1) → CI/CD 차단
```

이 세 줄(Config 선언 → Tracker 자동 수집 → Gate 판정)이 Chapter 4–10에서 다루는 33개 Config와 7개 Gate 전체의 공통 패턴이다.

---

### 3.1.4 "버그 없음" vs "배포 가능"

기존 소프트웨어 테스팅이 던지는 질문은 하나다. **"버그가 없는가?"**

AI 에이전트에게 그 질문은 불완전하다. 에이전트는 결정론적으로 동작하지 않는다. 같은 질문에 매번 다른 경로로 답에 도달한다. Context Engineering으로 컨텍스트 창을 정교하게 구성하더라도, "버그 없음"을 보장하는 `assert` 테스트 수백 개가 통과해도, 프로덕션에서 에이전트가 무단으로 도구를 호출하거나, 환각으로 틀린 정보를 자신감 있게 전달하거나, 비용 계약을 초과하는 일이 일어날 수 있다.

**Harness Engineering은 다른 질문을 던진다.**

> "이 에이전트는 *지금 이 조건*에서 배포해도 되는가?"

그리고 그 질문의 답을 코드로 선언한다.

```python
# 기존 방식 — "버그가 없는지" 확인
def test_agent_response():
    result = agent("한국의 수도는?")
    assert "서울" in result  # 결정론적 assert

# Harness Engineering — "배포 가능한지" 판정
from agent_evaluator import QuickEval
from agent_evaluator import SLAConfig, InstructionConfig

eval = QuickEval("results/")

@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=2000),                               # SLA 선언
    instructions=InstructionConfig(expected_language="ko"),   # 언어 기준 선언
)
def agent(question, ground_truth=""):
    return llm.invoke(question)

# 배포 기준이 위반되면 자동으로 fail 처리
eval.gate(tcr=85, accuracy=70)  # → 기준 미달 시 sys.exit(1)
```

핵심 차이는 **"기준의 위치"**다. `assert`는 테스트 파일 안에 있다. Harness Config는 에이전트 코드 바로 옆, `@agent_eval` 데코레이터 안에 있다. 에이전트가 자신의 배포 기준을 소유한다.

### 3.1.5 세 가지 배포 실패 유형

Harness Engineering이 방지하려는 실패는 세 가지 유형이다.

**유형 1 — 측정 없는 배포 (blind deployment)**  
에이전트를 실행하고, "응답이 나오네요"라고 확인한 뒤 배포한다. 정확도가 얼마인지, 응답 시간이 SLA 내에 있는지, 환각이 발생하는지 알 수 없다. 프로덕션 장애가 발생하면 왜 그런지 추적할 수단이 없다.

**유형 2 — 기준 없는 측정 (measurement without criteria)**  
`accuracy=0.85`라는 숫자는 있다. 하지만 이것이 배포 가능한 수준인지 팀원마다 판단이 다르다. 같은 숫자를 보고 "충분하다"와 "부족하다"가 충돌한다. 기준이 문서나 관행에 있으면 이 문제는 반복된다.

**유형 3 — 배포 후 무감지 (silent drift)**  
배포 당시에는 품질 기준을 통과했다. 하지만 LLM 모델이 업데이트되거나, 프롬프트가 조금 바뀌거나, 입력 데이터의 분포가 달라지면서 성능이 서서히 저하된다. 아무도 감지하지 못한 채 수주가 지난다.

Harness Engineering의 세 구성 요소(Tracker, Config, Gate)는 이 세 가지 유형을 각각 해결한다.

---

## 3.2 3요소: Tracker × Config × Gate

§3.1에서 Harness Engineering의 개념과 Guides+Sensors 작동 원리를 설명했다. 이제 세 역할 각각을 동등한 깊이로 분해한다 — Chapter 2에서 "무엇이 존재하는가"를 파악했다면, 여기서는 "각 역할이 어떻게 작동하는가"를 이해한다.

Harness Engineering은 세 개의 구성 요소로 이루어진다. 각각 독립적으로 사용할 수도 있지만, 셋이 결합될 때 완전한 배포 판정이 이루어진다.

### 3.2.1 Tracker — 관찰하는 자

Tracker는 에이전트 실행 중 무슨 일이 일어나는지 측정하는 관찰자(Observer)다. 판단하지 않는다. 오직 측정만 한다.

`PerformanceMonitor`에 `record_task()`를 호출할 때마다 내부의 트래커들이 자동으로 동작한다.

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor("results/")

result = create_taskresult(
    task_id="t001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",
)

monitor.record_task(result)
# ↑ 이 순간 내부에서 자동으로 동작하는 트래커들:
#   TaskCompletionTracker → completion_score 기록
#   AccuracyEvaluator     → accuracy_score 계산
#   ResponseQualityEvaluator → quality 5차원 평가
#   LatencyTracker        → execution_time 기록
#   TokenEconomyTracker   → tokens_used 기록
```

Agent-Evaluator의 Tracker는 25개이며, Group A-G에 분산되어 있다. 보안 Tracker 5종(Group E)은 `enable_security_metrics=True`로 활성화하는 opt-in이며, 25개 안에 포함된다.

### 3.2.2 Config — 기준을 선언하는 자

Config는 "어떤 상태가 합격인가"를 선언하는 기준서(Specification)다. 측정하지 않는다. 오직 기준을 선언한다.

Config 데이터클래스는 33개이며, `@agent_eval` 데코레이터의 파라미터로 주입한다.

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 1 — Harness 3-Element: Tracker·Config·Gate
from agent_evaluator import (
    SLAConfig,              # Group D: 성능계약
    InstructionConfig,      # Group A: 목표달성
    ReproducibilityConfig,  # Group C: 신뢰성
    ThreatSeverityConfig,   # Group E: 보안경계
)
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    task_type="qa",
    # Group A — 목표달성 기준
    instructions=InstructionConfig(
        expected_language="ko",           # 한국어 응답 필수
        max_words=200,                    # 최대 200단어
        fail_on_violation=True,           # 위반 시 fail 처리
    ),
    # Group C — 신뢰성 기준
    reproducibility=ReproducibilityConfig(
        runs=3,                           # 동일 입력 3회 실행
        reproducibility_threshold=0.85,   # 재현성 85% 이상
    ),
    # Group D — 성능계약 기준
    sla=SLAConfig(
        p95_ms=2000,                      # P95 응답 2초 이내
        max_cost_per_task=0.005,          # 태스크당 최대 $0.005
    ),
    # Group E — 보안경계 기준
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,            # 치명적 위협 탐지 시 fail
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

`fail_on_violation=True` 플래그가 핵심이다. 이 플래그가 활성화된 Config 조건을 위반하면 해당 `TaskResult.success`가 `False`로 강제 처리된다.

### 3.2.3 Gate — 판정하는 자

Gate는 Tracker가 측정한 데이터와 Config가 선언한 기준을 대조해 최종 배포 판정을 내리는 심판(Judge)이다.

가장 간단한 Gate는 `eval.gate()`다.

```python
eval = QuickEval("results/")

# ... 평가 실행 ...

eval.gate(tcr=85, accuracy=70)
# tcr < 85 또는 accuracy < 70 이면 sys.exit(1) → CI/CD 파이프라인 차단
```

`HarnessEvaluationGate`는 7개 Group을 한 번에 체크하는 종합 Gate다. (§3.5 참조)

---

## 3.3 58개 지표 전체 지도 — Gate A-G 매핑

### 왜 정확히 7개인가 — Gate 설계 논리

7개 Gate는 임의적인 분류가 아니다. **자율 에이전트를 프로덕션에서 신뢰하기 위해 독립적으로 검증해야 하는 최소 완전 집합이다.**

"독립적"이라는 점이 설계의 핵심이다. Gate A(목표달성)가 PASS여도 Gate E(보안경계)는 알 수 없다. Gate D(성능계약)가 PASS여도 Gate B(행동무결성)는 알 수 없다. 각 Gate는 다른 Gate로 대체할 수 없는 고유한 실패 차원을 담당한다. 7개 차원은 에이전트의 본질적 특성에서 도출된다.

**① 자율성(Autonomy)에서 비롯되는 차원**

에이전트는 스스로 도구를 선택하고 행동 경로를 결정한다. 이 자율성은 목표를 달성했어도 허가되지 않은 도구를 쓰거나, 루프에 빠지거나, 허용 범위를 이탈하는 위험을 만든다.

→ **Gate B — 행동무결성**: "에이전트가 의도된 범위 안에서만 행동했는가?"

**② 확률론적 동작(Stochasticity)에서 비롯되는 차원**

LLM 기반 에이전트는 동일 입력에도 다른 추론 경로와 다른 출력을 생성한다. 단일 실행의 성공이 통계적 보장을 의미하지 않는다. 출력의 사실 일치성(환각)도 실행마다 달라진다.

→ **Gate A — 목표달성**: "통계적으로 충분히 높은 정확도·TCR이 보장되는가?"  
→ **Gate C — 신뢰성**: "동일 품질이 반복 실행에서도 재현되는가?"

**③ 프로덕션 운영(Production Contract)에서 비롯되는 차원**

아무리 정확한 에이전트도 응답이 30초 걸리거나, 태스크당 비용이 예산을 초과하면 서비스가 불가능하다. 이 제약은 기능 테스트로는 알 수 없다.

→ **Gate D — 성능계약**: "SLA(응답 시간·비용)를 예측 가능하게 지키는가?"

**④ 외부 위협(External Threat)에서 비롯되는 차원**

에이전트는 외부 사용자의 입력을 그대로 처리한다. 프롬프트 인젝션·권한 상승·민감 정보 유출 공격은 기능이 완벽한 에이전트에서도 발생할 수 있다. 기능 테스트 100% 통과가 보안을 보장하지 않는다.

→ **Gate E — 보안경계**: "외부 공격을 탐지·차단하고 정보 유출을 방지하는가?"

**⑤ 시스템 복잡성(System Complexity)에서 비롯되는 차원**

단일 에이전트의 품질이 검증되어도 여러 에이전트가 협력할 때는 교착·역할 위반·정보 왜곡 같은 창발적 실패가 발생한다. 다중 에이전트 시스템은 개별 에이전트 검증으로 충분하지 않다.

→ **Gate F — 다중에이전트**: "여러 에이전트가 합의·역할 준수·교착 없이 협력하는가?"

**⑥ 운영 가능성(Operability)에서 비롯되는 차원**

배포 후 에이전트가 예상대로 동작하지 않을 때, 내부 추론 과정을 설명하고 실패 원인을 추적할 수 없다면 수정이 불가능하다. 관측 가능성은 사후에 추가할 수 없으며 처음부터 설계되어야 한다.

→ **Gate G — 운영관측성**: "추론 과정을 설명하고 실패 원인을 즉시 추적할 수 있는가?"

| 에이전트 특성 | 발생하는 위험 | 대응 Gate |
|------------|-----------|---------|
| 자율성 | 허가 범위 이탈·루프 | **B** 행동무결성 |
| 확률론적 동작 | 통계적 품질 불보장·환각 | **A** 목표달성, **C** 신뢰성 |
| 프로덕션 계약 | SLA·비용 초과 | **D** 성능계약 |
| 외부 위협 노출 | 공격·유출 | **E** 보안경계 |
| 시스템 복잡성 | 협업 창발적 실패 | **F** 다중에이전트 |
| 블랙박스 동작 | 운영·디버깅 불가 | **G** 운영관측성 |

**결론**: 7개 Gate는 자율 에이전트의 본질적 속성에서 필연적으로 도출된다. 하나라도 미확인 상태로 배포하면, 해당 속성에서 비롯되는 장애가 프로덕션에서 반드시 발생한다. 이것이 Harness Engineering이 단일 지표가 아닌 7개 독립 차원으로 배포 준비도를 판정하는 이유다.

---

Tracker 25개와 Config 33개를 7개 Gate(A-G)에 배분한다. (보안 Tracker 5종은 25개 안에 포함, opt-in 활성화 필요)

> **용어 정리 — Gate A-G와 HarnessEvaluationGate**
>
> 이 책에서 "Gate"는 두 가지 층위로 쓰인다.
>
> | 용어 | 의미 | 예시 |
> |------|------|------|
> | **Gate A-G** | 7개 배포 관문(품질 차원). Tracker+Config 58개를 배포 가능 여부 판정 단위로 묶은 것 | Gate A(목표달성) — "지시를 완수했는가?" |
> | **HarnessEvaluationGate** | Gate A-G를 한 번에 실행해 종합 배포 판정을 내리는 메커니즘(3요소 중 Gate 역할) | `HarnessEvaluationGate(report).enforce()` |
>
> `HarnessEvaluationGate.evaluate()`를 호출하면 Gate A-G 각각의 PASS/WARN/FAIL 결과가 반환된다. 코드 내부(JSON 출력, 대시보드 키)에서는 `harness_groups`, `group_key` 등 "group"이라는 표현이 함께 쓰이는데, 이는 동일한 7개 차원을 지표 분류 관점에서 부른 것이다. 개념적으로는 Gate가 더 정확하다 — 각 차원이 단순 분류가 아닌 "통과해야 하는 배포 관문"이기 때문이다.

### Gate A — 목표달성 (Goal Achievement)

**핵심 질문**: 에이전트가 사용자의 지시를 제대로 완수했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `TaskCompletionTracker` | Task Completion Rate (TCR) — 완료 비율 |
| Tracker | `AccuracyEvaluator` | 정확도 — Token F1 + Jaccard + LCS + Levenshtein 4중 가중 |
| Tracker | `ResponseQualityEvaluator` | 응답 품질 — relevance(×0.25) · completeness(×0.25) · accuracy(×0.20) · clarity(×0.15) · usefulness(×0.15) 가중 평균 |
| Config | `InstructionConfig` | 응답 형식·길이·언어 준수 기준 |
| Config | `GoalAlignmentConfig` | 목표-행동 정렬 기준 |
| Config | `PlanConfig` | 계획 실행 완성도 기준 |
| Config | `ContextRetentionConfig` | 핵심 컨텍스트 보존 기준 |
| Config | `SubtaskConfig` | 서브태스크 완료율 기준 |
| Config | `KnowledgeRetentionConfig` | 대화 중 사실 보존 기준 |

### Gate B — 행동무결성 (Behavioral Integrity)

**핵심 질문**: 에이전트가 의도하지 않은 행동 없이 동작했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `ToolCallAnalyzer` | 도구 호출 패턴 분석 |
| Tracker | `WorkflowExecutionTracker` | 워크플로우 실행 분기 추적 |
| Config | `LoopDetectionConfig` | 도구 호출 루프·반복 패턴 감지 기준 |
| Config | `ScopeConfig` | 허용/금지 도구 범위 선언 |
| Config | `ToolParameterSafetyConfig` | 도구 파라미터 위험 패턴 기준 |
| Config | `ContextWindowConfig` | 컨텍스트 윈도우 포화도 기준 |
| Config | `StateConsistencyConfig` | 실행 전후 상태 일관성 기준 (v0.8.2에서 Group F→B 이동) |
| Config | `DeadlockConfig` | 교착·기아·라이브락 탐지 기준 (v0.8.2에서 Group F→B 이동) |

### Gate C — 신뢰성 (Reliability)

**핵심 질문**: 같은 입력에 일관되고 재현 가능한 응답을 하는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `HallucinationDetector` | 환각 탐지 — 사실 일관성 점수 (opt-in) |
| Tracker | `RetryCorrectionTracker` | 재시도·자가수정 행동 추적 |
| Config | `ReproducibilityConfig` | 동일 입력 반복 실행 재현성 기준 |
| Config | `FaultToleranceConfig` | 장애 내성·폴백 기준 |
| Config | `GracefulDegradationConfig` | 우아한 성능 저하 기준 |
| Config | `RetryConsistencyConfig` | 재시도 일관성 기준 |
| Config | `IdempotencyConfig` | 멱등성(반복 실행 부작용 없음) 기준 |

### Gate D — 성능계약 (Performance Contract)

**핵심 질문**: 약속한 SLA와 비용 계약을 지켰는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `LatencyTracker` | 응답 시간 — P50·P95·P99·TTFT |
| Tracker | `TokenEconomyTracker` | 토큰 사용량 + 비용 추정 |
| Config | `SLAConfig` | P95·P99·TTFT·비용 SLA 선언 |
| Config | `EfficiencyConfig` | 비용 대비 완료율(ROI) 기준 |
| Config | `ResourceBudgetConfig` | 토큰·비용·실행시간 예산 상한 |
| Config | `TTFTVariabilityConfig` | TTFT 변동성 기준 |
| Config | `CostPredictabilityConfig` | 비용 예측 가능성(CV) 기준 |

### Gate E — 보안경계 (Security Boundary)

**핵심 질문**: 외부 공격과 데이터 유출을 차단했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `InputSanitizationTracker` | SQL·Command·Path·XSS·Prompt Injection 탐지 |
| Tracker | `OutputLeakageDetector` | 민감 데이터 출력 유출 탐지 |
| Tracker | `ToolAuthorizationTracker` | 미허가 도구 사용 탐지 |
| Tracker | `PrivilegeEscalationDetector` | 권한 상승 패턴 탐지 |
| Tracker | `ToolChainAttackDetector` | 도구 연쇄 공격 패턴 탐지 |
| Config | `ThreatSeverityConfig` | CVSS 기반 위협 심각도 기준 |
| Config | `ComplianceConfig` | PII·컴플라이언스 위반 기준 |
| Config | `ThreatResponseConfig` | 위협 탐지 시 응답 행동 기준 |

> ⚠️ **보안 트래커 활성화**: 보안 트래커 5종(`InputSanitizationTracker`, `OutputLeakageDetector`, `ToolAuthorizationTracker`, `PrivilegeEscalationDetector`, `ToolChainAttackDetector`)은 `enable_security_metrics=True`로 명시적으로 활성화해야 한다. 성능에 영향을 주므로 기본값은 `False`다.

### Gate F — 다중에이전트 협업 (Multi-Agent Coordination)

**핵심 질문**: 여러 에이전트가 교착 없이 협력했는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Tracker | `AgentCoordinationTracker` | 에이전트 간 상호작용 추적 |
| Tracker | `ToolSelectionTracker` | 도구 선택 F1 정확도 |
| Config | `ConsensusConfig` | 다중 에이전트 합의 품질 기준 |
| Config | `PropagationConfig` | 에이전트 간 정보 전파 충실도 기준 |
| Config | `AgentRoleConfig` | 에이전트 역할 준수 기준 |
| Config | `ConflictResolutionConfig` | 에이전트 간 충돌 해결 품질 기준 |

### Gate G — 운영관측성 (Operational Observability)

**핵심 질문**: 실패 원인을 즉시 추적하고 설명할 수 있는가?

| 유형 | 이름 | 설명 |
|------|------|------|
| Config | `ObservabilityConfig` | 스팬 속성 완성도·감사 이벤트 SLO 기준 |
| Config | `ExplainabilityConfig` | 응답 설명 가능성·추론 근거 기준 |
| Config | `ErrorDiagnosisConfig` | 실패 응답의 오류 진단 품질 기준 |
| Config | `LatencyAttributionConfig` | 도구·모델·네트워크 지연 귀속 기준 |

> **Gate G와 LLM Judge**: Gate G는 관측성과 설명 가능성을 다룬다. LLMJudge (`enable_llm_judge=True`)는 Gate G와 자연스럽게 연결된다. LLM이 응답의 추론 근거와 설명 품질을 자동으로 채점하기 때문이다.

### 지표 수 요약

| Gate | Tracker | Config | 합계 |
|------|---------|--------|------|
| A 목표달성 | 3 | 6 | 9 |
| B 행동무결성 | 2 | 6 | 8 |
| C 신뢰성 | 2 | 5 | 7 |
| D 성능계약 | 2 | 5 | 7 |
| E 보안경계 | 5 | 3 | 8 |
| F 다중에이전트 | 2 | 4 | 6 |
| G 운영관측성 | 0 | 4 | 4 |
| **합계** | **16** | **33** | **49** |

> ℹ️ **지표 수 안내**: Harness Gate(A–G)에 직접 매핑되는 Native Tracker는 16개다. `ConversationSession`, `ImplicitFeedbackTracker`, `AnomalyDetector`, `CostTracker`, `StreamingEvaluator` 등 운영 지원 트래커 9개를 합산하면 SDK 전체 Native Tracker는 25개다. Harness Gate 판정 대상은 이 표의 49개(16 Tracker + 33 Config)이며, 운영 지원 트래커를 포함한 전체는 **25 + 33 = 58개**다. 전체 목록은 [Appendix A](../Appendix/A_58개지표_레퍼런스.md)에서 확인한다.

§3.2에서 세 역할의 작동 방식을, §3.3에서 58개 지표의 전체 구조를 파악했다. 이제 33개 Config를 실제로 어떻게 선언하고 조합하는지 — 실전 패턴을 살펴본다.

---

## 3.4 Config-as-Code 패턴

Config-as-Code는 에이전트의 배포 기준을 소스 코드로 선언하는 패턴이다. 이 패턴이 "기준 없는 측정" 문제를 해결한다.

### 3.4.1 왜 코드로 선언하는가

배포 기준을 코드 밖에 두면 세 가지 문제가 생긴다.

1. **버전 관리 불가**: 기준이 언제 바뀌었는지 추적할 수 없다
2. **팀원 간 불일치**: 같은 숫자를 보고 다른 판단을 내린다
3. **CI/CD 통합 불가**: 코드 변경마다 기준을 자동으로 검증할 수 없다

Config-as-Code는 이 세 가지를 모두 해결한다. Config 객체는 코드베이스의 일부이므로 `git`으로 버전 관리되고, PR 리뷰 시 기준 변경이 명시적으로 보이며, CI/CD 파이프라인에서 자동으로 실행된다.

### 3.4.2 에이전트 유형별 최소 Config 세트

| 에이전트 유형 | 필수 Config | 선택 Config |
|-------------|-------------|-------------|
| 단순 QA 봇 | `InstructionConfig`, `SLAConfig` | `ReproducibilityConfig` |
| RAG 에이전트 | `InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig` | `ContextRetentionConfig`, `ComplianceConfig` |
| 코드 생성 에이전트 | `ScopeConfig`, `SLAConfig`, `ComplianceConfig` | `SubtaskConfig`, `ObservabilityConfig` |
| 멀티에이전트 시스템 | `DeadlockConfig`, `AgentRoleConfig`, `SLAConfig` | `ConsensusConfig`, `PropagationConfig` |
| 보안 중심 에이전트 | `ThreatSeverityConfig`, `ComplianceConfig`, `ThreatResponseConfig` | `StateConsistencyConfig`, `ScopeConfig` |

### 3.4.3 단계적 도입 패턴

하루 만에 모든 Config를 도입할 필요는 없다. 다음 순서로 점진적으로 적용한다.

**Day 1 — 최소 시작 (측정만)**

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""):
    return llm.invoke(question)

# 이 단계에서는 Config 없이 측정만 함
# 며칠간 수집된 데이터를 보며 실제 지표 분포를 파악한다
```

- **목적**: Config 선언 없이 기본 지표(TCR·정확도·품질·지연)를 수집만 한다
- **`@eval.qa`**: `task_type="qa"` 단축 데코레이터로 QA 태스크를 자동 인식한다
- **다음 단계**: 며칠간 데이터를 모은 뒤 실제 P95·TCR 분포를 보고 Day 7 Config 임계값을 결정한다

**Day 7 — 첫 Config 도입 (SLA + 기본 기준)**

```python
from agent_evaluator import SLAConfig, InstructionConfig

@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000),           # 측정 데이터 P95 기반 설정
    instructions=InstructionConfig(
        expected_language="ko",
        max_words=300,
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

- **`SLAConfig(p95_ms=3000)`**: Day 1 측정 데이터에서 확인한 실제 P95 응답 시간을 기준으로 SLA를 선언한다
- **`InstructionConfig`**: 한국어 응답 강제 + 300단어 상한으로 응답 품질 하한선을 코드로 선언한다
- **이 시점에서는 `fail_on_violation`이 없으므로** 위반 시 기록만 하고 실패 처리는 하지 않는다

**Day 30 — 배포 판정 자동화 (fail_on_violation + gate)**

```python
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=2000, fail_threshold=3),           # P95 응답 2초 이내, 3건 위반 시 fail
    instructions=InstructionConfig(
        expected_language="ko",
        fail_on_violation=True,
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)

# CI/CD에서 자동 배포 차단
eval.gate(tcr=85, accuracy=70)
```

- **`fail_on_violation=True`**: 언어 기준 위반 시 해당 태스크의 `TaskResult.success`를 자동으로 `False`로 강제한다
- **`sla.fail_threshold=3`**: SLA 위반이 3건을 넘으면 Gate 점수를 낮춰 배포 차단에 반영한다
- **`eval.gate(tcr=85, accuracy=70)`**: TCR 85% 미만 또는 정확도 70% 미만이면 `sys.exit(1)`로 CI/CD 파이프라인을 차단한다

### 3.4.4 Config 조합 — 프로덕션 QA 에이전트 예시

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py
from agent_evaluator import PerformanceMonitor
from agent_evaluator import (
    InstructionConfig,
    ReproducibilityConfig,
    SLAConfig,
    ResourceBudgetConfig,
    ThreatSeverityConfig,
    ObservabilityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C
    enable_security_metrics=True,         # Group E
)

@agent_eval(
    monitor,
    task_type="qa",
    # Group A — 목표달성
    instructions=InstructionConfig(
        expected_language="ko",
        max_words=500,
        forbidden_phrases=["모르겠습니다", "확인이 필요합니다"],
        fail_on_violation=True,
    ),
    # Group C — 신뢰성
    reproducibility=ReproducibilityConfig(
        runs=3,
        reproducibility_threshold=0.85,
        fail_on_low_reproducibility=False,  # 경고만, fail 없음
    ),
    # Group D — 성능계약
    sla=SLAConfig(
        p95_ms=2000,
        max_cost_per_task=0.005,
        fail_threshold=5,
    ),
    resource_budget=ResourceBudgetConfig(
        max_tokens=2000,
        warn_at_pct=0.8,
    ),
    # Group E — 보안경계
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,
        fail_score=7.0,
    ),
    # Group G — 운영관측성
    observability=ObservabilityConfig(
        min_coverage=0.99,
    ),
)
def qa_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- **멀티 Config 조합**: 하나의 `@agent_eval`에 Gate A·C·D·E·G를 동시 선언해 5개 Gate를 한 번에 평가한다
- **`enable_hallucination_detection=True`**: Gate C의 `HallucinationDetector`를 활성화한다 (기본값 False, 성능 영향 있음)
- **`enable_security_metrics=True`**: Gate E 보안 트래커 5종을 활성화한다 (기본값 False)
- **`forbidden_phrases`**: "모르겠습니다" 등 역량 부족 신호를 응답에서 탐지하면 `fail_on_violation=True`에 의해 즉시 fail 처리한다
- **`warn_at_pct=0.8`**: 토큰 예산의 80%를 소진하면 경고(fail 없음)를 발생시킨다

---

## 3.5 개발자 ↔ QA 관리자 협업 브리지

Harness Engineering에는 두 종류의 사용자가 있다. **개발자**는 Tracker와 Config로 평가를 구현하고, **QA 관리자**는 Gate A–G 판정 결과로 배포를 승인하거나 차단한다. 두 역할이 어떻게 연결되는지 이해하면 팀 전체가 같은 언어로 소통할 수 있다.

### 3.5.1 두 역할이 보는 Harness

```
┌──────────────────────────────────────────────────────────────────┐
│  개발자 관점 (구현)            QA 관리자 관점 (판정)               │
│                                                                  │
│  @agent_eval(                  대시보드 / Gate 리포트              │
│    monitor,                                                      │
│    sla=SLAConfig(p95_ms=2000)  → Gate D 성능계약: PASS ✅         │
│    scope=ScopeConfig(...)      → Gate B 행동무결성: WARN ⚠️        │
│    threat_severity=...         → Gate E 보안경계: PASS ✅         │
│  )                                                               │
│  def my_agent(...): ...                                          │
│                                                                  │
│  ← 코드로 선언 →               ← 판정 결과로 소통 →               │
└──────────────────────────────────────────────────────────────────┘
```

### 3.5.2 협업 워크플로우 — 5단계

실제 팀에서 Harness Engineering이 어떻게 흐르는지 한 사이클을 따라가 본다.

**Step 1 — 개발자: Tracker 활성화 (측정 시작)**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C Tracker
    enable_security_metrics=True,         # Group E Tracker
)
```

Tracker는 코드를 변경하지 않아도 자동으로 데이터를 수집한다. 이 시점에서 QA 관리자는 아직 개입하지 않는다.

**Step 2 — 개발자: 초기 평가 실행 (기준 없는 측정)**

```python
@agent_eval(monitor, task_type="qa")
def my_agent(question, ground_truth=""):
    return llm.invoke(question)

# 10개 샘플 실행
for q, gt in test_cases:
    my_agent(q, ground_truth=gt)

report = monitor.generate_report()
d = report.to_dict()
p95 = d.get("efficiency_metrics", {}).get("latency", {}).get("p95", 0.0)
tcr = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
print(f"응답시간 P95: {p95:.2f}초")
print(f"TCR: {tcr * 100:.1f}%")
```

이 결과를 QA 관리자에게 공유한다.

**Step 3 — QA 관리자: Config 기준 결정 (기준 선언)**

측정 데이터를 바탕으로 QA 관리자가 배포 기준을 결정한다.

```
측정 결과:
  - 응답시간 P95: 1.8초  →  SLAConfig(p95_ms=2500) 설정
  - TCR: 91%            →  eval.gate(tcr=85) 설정
  - 보안 위협 탐지: 0건  →  ThreatSeverityConfig(fail_on_critical=True) 설정

QA 관리자 결정 (문서 또는 구두):
  "P95 2.5초 이내, TCR 85% 이상, 보안 위협 0건을 배포 기준으로 한다"
```

**Step 4 — 개발자: Config 코드 반영 (기준을 코드로)**

```python
@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(
        p95_ms=2500,           # QA 관리자 결정 반영
    ),
    threat_severity=ThreatSeverityConfig(
        fail_on_critical=True,  # QA 관리자 결정 반영
    ),
)
def my_agent(question, ground_truth=""):
    return llm.invoke(question)

eval.gate(tcr=85, accuracy=70)  # QA 관리자 결정 반영
```

- **기준의 코드화**: QA 관리자가 구두나 문서로 결정한 기준을 `@agent_eval` 파라미터로 옮긴다
- **버전 관리**: 이 코드가 Git에 커밋되므로 `git log`로 기준 변경 이력을 언제든 추적할 수 있다
- **팀 가시성**: PR 리뷰 시 Config 파라미터 변경이 diff에 명시적으로 드러나 합의 절차를 자연스럽게 강제한다

이제 기준이 소스 코드 안에 존재한다. 팀 누구나 `git log`로 기준의 변경 이력을 볼 수 있다.

**Step 5 — CI/CD: 자동 Gate 판정 (반복 검증)**

```yaml
# .github/workflows/eval.yml
- name: Harness Gate check
  run: agent-eval gate results/latest.json --tcr 85 --accuracy 70
```

PR마다 Gate가 자동으로 동작한다. 기준을 위반하면 배포가 차단된다. QA 관리자는 대시보드에서 Group별 점수를 확인하고 추가 기준을 요청할 수 있다.

### 3.5.3 Gate A–G와 Tracker·Config 매핑 요약

| Gate (차원) | 품질 질문 | 관련 Tracker | 관련 Config |
|------------|----------|-------------|------------|
| **A** 목표달성 | 지시를 완수했는가? | TCR, Accuracy, ResponseQuality | InstructionConfig, GoalAlignmentConfig, PlanConfig |
| **B** 행동무결성 | 의도치 않은 행동이 없었는가? | ToolCallAnalyzer, WorkflowExecution | LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig, ContextWindowConfig, StateConsistencyConfig, DeadlockConfig |
| **C** 신뢰성 | 일관되고 재현 가능한가? | HallucinationDetector, RetryCorrection | ReproducibilityConfig, FaultToleranceConfig, IdempotencyConfig |
| **D** 성능계약 | SLA·비용을 지켰는가? | LatencyTracker, TokenEconomy | SLAConfig, ResourceBudgetConfig, EfficiencyConfig |
| **E** 보안경계 | 공격·유출을 차단했는가? | InputSanitization, OutputLeakage, ToolAuth, PrivilegeEscalation, ToolChainAttack | ThreatSeverityConfig, ComplianceConfig, ThreatResponseConfig |
| **F** 다중에이전트 | 교착 없이 협력했는가? | AgentCoordination, ToolSelection | ConsensusConfig, AgentRoleConfig, ConflictResolutionConfig |
| **G** 운영관측성 | 실패 원인을 즉시 추적할 수 있는가? | LLMJudge (7차원) | ObservabilityConfig, ExplainabilityConfig, ErrorDiagnosisConfig |

> 📖 **각 Group의 상세 내용**: Chapter 4(A) ~ Chapter 10(G)에서 Tracker·Config를 깊이 다룬다.  
> 📖 **Config 파라미터 전체 목록**: [Appendix A §Part 2](../Appendix/A_58개지표_레퍼런스.md)

---

## 3.6 HarnessEvaluationGate — 종합 배포 판정 아키텍처

### 3.6.1 Gate의 역할

`eval.gate()`는 TCR·정확도 두 개 지표만 체크하는 단순 Gate다. 에이전트가 성숙해지면 7개 Group 전체를 종합적으로 체크하는 Gate가 필요하다. 그것이 `HarnessEvaluationGate`다.

```python
from agent_evaluator import HarnessEvaluationGate

# 평가 완료 후 Gate 실행
report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

print(result)
# {
#   "passed": False,
#   "groups": {
#     "A": {"passed": True,  "score": 0.91, "status": "pass"},
#     "B": {"passed": True,  "score": 0.97, "status": "pass"},
#     "C": {"passed": False, "score": 0.72, "status": "fail"},
#     "D": {"passed": True,  "score": 0.88, "status": "pass"},
#     "E": {"passed": True,  "score": 1.00, "status": "pass"},
#     "F": {"passed": True,  "score": 0.94, "status": "pass"},
#     "G": {"passed": True,  "score": 0.89, "status": "pass"},
#   },
#   "violations": [{"group": "C", "score": 0.72, "status": "fail"}],
#   "summary": {"total_groups": 7, "passed_groups": 6, "overall_score": 0.90},
# }

# CI/CD — 실패 시 sys.exit(1)
gate.enforce()
```

- **`HarnessEvaluationGate(report)`**: `monitor.generate_report()`가 반환한 `EvaluationReport`를 받아 Gate A–G를 일괄 평가한다
- **`result["passed"]`**: 하나라도 `required_groups` 기준을 미달하면 `False`가 된다
- **`result["violations"]`**: 실패한 Gate 목록과 점수를 반환해 어디서 차단됐는지 즉시 확인한다
- **`gate.enforce()`**: `passed=False`이면 `sys.exit(1)`을 호출해 CI/CD 파이프라인을 자동 차단한다

### 3.6.2 CI/CD 파이프라인 통합

```yaml
# .github/workflows/eval.yml
name: Harness Gate

on: [pull_request]

jobs:
  harness-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run evaluation
        run: python -m pytest tests/eval/ -v
      - name: Harness Gate check
        run: |
          agent-eval gate results/latest.json \
            --tcr 85 \
            --accuracy 70 \
            --fail-on-group-violation C,E  # Group C·E 위반 시 배포 차단
```

### 3.6.3 특정 Group만 검사

에이전트 유형에 따라 검사할 Group을 지정할 수 있다.
`HarnessEvaluationGate`는 `report`, `min_group_score`, `required_groups`, `fail_on_warn`을 지원한다. `group_weights`는 지원하지 않는다.

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 7 — HarnessEvaluationGate 활용
from agent_evaluator import HarnessEvaluationGate

# 목표달성(A)·보안경계(E)만 필수 통과 — 나머지는 경고만
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],  # A·E는 점수가 있으면 반드시 통과해야 함
    min_group_score=0.7,         # 각 그룹 최소 허용 점수 70%
    fail_on_warn=False,          # warn 상태는 실패로 처리하지 않음
)
result = gate.evaluate()
gate.enforce()   # 기준 미달 시 sys.exit(1)
```

- **`required_groups=["A", "E"]`**: 목표달성과 보안경계만 필수 통과로 지정하고 나머지 Group(B·C·D·F·G)은 경고만 발생시킨다
- **`min_group_score=0.7`**: 필수 Group의 점수가 0.7 미만이면 Gate 실패로 처리한다
- **`fail_on_warn=False`**: `warn` 상태는 실패로 간주하지 않아 점진적 기준 도입 단계에서 유용하다


### 3.6.4 ch18_cicd_gate.py — CI/CD 전용 최소 검증 스크립트

`ch03_harness_basics.py`는 33개 Config 전체를 교육용으로 시연하지만, CI/CD 파이프라인에서는 **7개 Gate당 1개 Config씩 최소 검증**만 실행하는 `ch18_cicd_gate.py`를 사용한다:

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py — CI/CD 전용 최소 검증
import json, sys
from agent_evaluator import (
    PerformanceMonitor,
    InstructionConfig, GoalAlignmentConfig,      # Group A
    LoopDetectionConfig, ScopeConfig,            # Group B
    ReproducibilityConfig, RetryConsistencyConfig, # Group C
    SLAConfig, ResourceBudgetConfig,             # Group D
    ThreatSeverityConfig, ComplianceConfig,      # Group E
    ConsensusConfig, AgentRoleConfig,            # Group F
    ExplainabilityConfig, ObservabilityConfig,   # Group G
)
from agent_evaluator.decorators import agent_eval

_STRICT_MODE = "--strict" in sys.argv   # WARN도 FAIL로 처리

monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# Group A — 목표달성
@agent_eval(monitor, task_type="qa", task_id_prefix="val_a",
    instructions=InstructionConfig(required_keywords=["answer", "source"], min_chars=10),
    goal_alignment=GoalAlignmentConfig(goal_tool_map={"search": ["web_search"]}, alignment_threshold=0.5),
)
def _group_a_agent(question, ground_truth=""):
    return json.dumps({"answer": question + "에 대한 검증 답변", "source": "내부 DB"})

# Group B — 행동무결성
@agent_eval(monitor, task_type="tool_use", task_id_prefix="val_b",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, window_size=5),
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "report"],
        forbidden_tools=["delete_all", "drop_table"],
    ),
)
def _group_b_agent(question, ground_truth=""):
    return f"재무 리포트 조회: {question}"

# ... (Group C~G는 동일 패턴으로 각 1개 Config)

# 실행 및 판정
for q in ["최근 분기 실적은?", "이번 달 비용 예측을 해줘"]:
    _group_a_agent(q, ground_truth="검증 완료")
    _group_b_agent(q, ground_truth="검증 완료")

report = monitor.generate_report()
monitor.save_to_file("harness_validation")

# JSON 한 줄 요약 — CI 로그 파싱용
d = report.to_dict()
harness = d.get("harness_gates", {})
summary = {
    grp: harness.get(grp, {}).get("gate_status", "N/A")
    for grp in ["A", "B", "C", "D", "E", "F", "G"]
}
print(json.dumps(summary))  # {"A": "PASS", "B": "PASS", ...}

# exit code 결정
failures = [g for g, s in summary.items() if s == "FAIL"]
warnings = [g for g, s in summary.items() if s == "WARN"]
if failures or (_STRICT_MODE and warnings):
    sys.exit(1)
sys.exit(0)
```

```bash
# GitHub Actions 통합
python Evaluator_Examples/ch18_cicd_gate.py         # FAIL만 차단
python Evaluator_Examples/ch18_cicd_gate.py --strict  # WARN도 차단
```

- **기본 모드**: Gate 상태가 `FAIL`인 Group이 하나라도 있으면 `sys.exit(1)`로 파이프라인을 차단한다
- **`--strict` 모드**: `WARN` 상태도 실패로 처리해 더 엄격한 품질 기준을 적용한다

| 항목 | `ch03_harness_basics.py` | `ch18_cicd_gate.py` |
|------|---------------------|---------------------------|
| 목적 | 교육·시연 | CI/CD 자동화 |
| Config 수 | 33개 전부 | 7개 (Gate당 1개) |
| 실행 시간 | ~15초 | ~3초 |
| exit code | 없음 | 0 (통과) / 1 (실패) |
| `--strict` | 없음 | WARN → FAIL 처리 |


---

## 3.7 AI Native 특성과 Harness Engineering의 연결

Chapter 1 §1.5에서 AI Native 평가의 5가지 고유 도전을 개념으로 정의했고, §1.5 말미에서 각 도전이 어떤 Gate에 매핑되는지를 표로 제시했다. 이 절에서는 그 매핑의 기술적 근거를 설명한다 — 각 도전에 Harness Engineering이 어떤 구체적인 메커니즘으로 대응하는지다.

기존 소프트웨어 테스팅은 결정론적 시스템을 위해 설계됐다. AI 에이전트는 5가지 AI Native 특성을 가지며, Harness Engineering은 이 각각에 직접 대응한다.

### 특성 1 — 확률론적 품질 (Probabilistic Quality)

에이전트의 품질은 단일 점수가 아니라 **분포**다. 같은 `accuracy=0.85`라도 분산이 작으면 안정적, 크면 예측 불가능하다.

Harness 대응: `ReproducibilityConfig`는 동일 입력을 N회 실행해 분포를 측정한다. `SLAConfig.p95_ms`는 단일 측정이 아닌 퍼센타일 기반 임계값이다.

```python
# 단일 테스트 — AI Native에 부적합
assert accuracy > 0.8  # 한 번의 실행 결과

# Harness — 분포 기반 기준
reproducibility=ReproducibilityConfig(
    runs=5,                          # 5회 실행
    reproducibility_threshold=0.85,  # 5회 중 85% 일관성
)
sla=SLAConfig(p95_ms=2000)          # P95 기반 SLA
```

- **`ReproducibilityConfig(runs=5)`**: 동일 입력을 5회 실행해 결과 분산을 측정한다 (단일 `assert`로 확인 불가한 부분)
- **`reproducibility_threshold=0.85`**: 5회 중 85% 이상 일관된 결과가 나와야 통과로 처리한다
- **`SLAConfig(p95_ms=2000)`**: 단일 샘플이 아닌 전체 실행의 95번째 백분위수 응답 시간으로 SLA를 판정한다

### 특성 2 — AI-by-AI 평가 (AI-Evaluated AI)

사람이 수백 개의 응답을 읽으며 품질을 채점하는 것은 확장되지 않는다. LLM Judge는 선택 사항이 아니라 Harness Engineering의 핵심 도구다.

Harness 대응: `ExplainabilityConfig`와 LLMJudge의 결합.

```python
from agent_evaluator import ExplainabilityConfig
from agent_evaluator.decorators import LLMJudgeConfig

@agent_eval(
    monitor,
    task_type="qa",
    llm_judge=LLMJudgeConfig(
        model="claude-haiku-4-5-20251001",
        criteria=["factual_accuracy", "reasoning_quality"],
        sample_rate=0.1,              # 10%만 채점 (비용 절감)
    ),
    explainability=ExplainabilityConfig(
        min_reasoning_length=50,      # 추론 근거 최소 50자
        reasoning_markers=["왜냐하면", "근거:", "출처:"],  # 추론 마커 필수
    ),
)
def agent(question, ground_truth=""):
    return llm.invoke(question)
```

- **`LLMJudgeConfig(criteria=[...])`**: LLM이 `factual_accuracy`·`reasoning_quality` 기준으로 응답을 0–5 척도로 자동 채점한다 (ground_truth 불필요)
- **`sample_rate=0.1`**: 전체 호출의 10%만 LLM Judge로 채점해 비용을 90% 절감한다
- **`ExplainabilityConfig`**: 응답에 추론 근거 마커("왜냐하면", "근거:" 등)가 포함되어야 하며, 추론 텍스트가 최소 50자 이상이어야 한다
- **두 Config의 결합**: LLM Judge가 채점한 `reasoning_quality` 점수와 `ExplainabilityConfig`의 마커 탐지가 Group G 관측성 점수에 함께 기여한다

### 특성 3 — 드리프트 인식 (Drift Awareness)

배포 당시 통과한 기준이 시간이 지나면서 의미를 잃는다. 4가지 변경 소스(코드·모델·프롬프트·데이터)에서 드리프트가 발생한다.

Harness 대응: `agent-eval trend`로 순차 실행 결과의 추세를 모니터링한다.

```bash
# 최근 20개 결과 파일의 TCR·정확도 추세 분석
agent-eval trend results/ --window 20

# 회귀 감지 시 CI/CD 실패 처리
agent-eval trend results/ --fail-on-regression

# 변경 소스 × Harness Group 영향 매트릭스
# 코드 변경  → Group B(행동무결성), Group C(신뢰성) 재검증
# 모델 교체  → Group A(목표달성), Group G(관측성) 재검증
# 프롬프트   → Group A, Group C 재검증
# 데이터 변화 → Group A, Group E(보안경계) 재검증
```

### 특성 4 — 돌발 행동 대응 (Emergent Behavior Response)

에이전트는 설계자가 예측하지 못한 행동을 할 수 있다. 탐지 패턴 목록에 없는 행동이다.

Harness 대응: `AnomalyDetector`와 `ScopeConfig`의 결합. `ScopeConfig`는 "허용된 도구 목록"으로 범위를 선언하고, `AnomalyDetector`는 통계적 이상치를 자동 감지한다.

```python
from agent_evaluator import AnomalyDetector
from agent_evaluator import ScopeConfig

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,    # 이상 탐지 활성화
)

@agent_eval(
    monitor,
    task_type="tool_use",
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "translate"],
        forbidden_tools=["execute_code", "delete_file"],
        fail_on_violation=True,       # 범위 외 도구 사용 시 fail
    ),
)
def agent(question, ground_truth=""):
    return tool_agent.run(question)
```

- **`enable_anomaly_detection=True`**: `AnomalyDetector`를 활성화해 지연 급등·오류율 이상·토큰 소비 급증 등 통계적 이상치를 자동 탐지한다
- **`ScopeConfig(allowed_tools=[...])`**: 허용 도구 목록 외의 도구를 사용하면 `fail_on_violation=True`에 의해 즉시 실패 처리한다
- **`forbidden_tools`**: 절대 호출하면 안 되는 도구를 명시하면 설계자가 예측하지 못한 도구 호출도 차단한다

### 특성 5 — 지속 평가 (Continuous Evaluation)

배포 전 평가만으로는 충분하지 않다. 배포 후에도 에이전트의 품질을 지속적으로 평가해야 한다.

Harness 대응: 배포 전 `HarnessEvaluationGate` + 배포 후 Phoenix OTEL 실시간 모니터링.

```
배포 전 Harness:                    배포 후 Harness:
  @agent_eval(Config 선언)    →       agent-eval monitor (Phoenix)
  HarnessEvaluationGate.evaluate()    agent-eval trend --fail-on-regression
  → 통과 시 배포 진행                  → 드리프트 감지 시 알림 + 재배포 차단
```

---

## 3.8 실습: 첫 Harness 배포 판정 (5분)

이 책의 모든 Harness 개념을 한 파일에서 경험한다.

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 1
"""5분 안에 완성하는 첫 Harness 평가"""
from agent_evaluator import QuickEval
from agent_evaluator import SLAConfig, InstructionConfig

eval = QuickEval("results/")

# Step 1: Config 선언 (배포 기준을 코드로)
@eval(
    task_type="qa",
    sla=SLAConfig(p95_ms=3000),                              # 관찰 모드 (위반 시 기록만)
    instructions=InstructionConfig(expected_language="ko"),
)
def simple_agent(question: str, ground_truth: str = "") -> str:
    # 실제 LLM 대신 규칙 기반 응답
    responses = {
        "한국의 수도": "서울입니다.",
        "파이썬 창시자": "귀도 반 로섬입니다.",
    }
    for key, val in responses.items():
        if key in question:
            return val
    return "모르겠습니다."

# Step 2: 평가 실행
test_cases = [
    ("한국의 수도는?", "서울"),
    ("파이썬 창시자는?", "귀도 반 로섬"),
    ("Java 창시자는?", "제임스 고슬링"),
]

for question, ground_truth in test_cases:
    simple_agent(question, ground_truth=ground_truth)

# Step 3: Harness Gate 판정
print("\n=== Harness Gate 결과 ===")
report = eval.monitor.generate_report()
d = report.to_dict()
tcr = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
acc = d.get("accuracy_metrics", {}).get("accuracy_scores", {}).get("overall_accuracy", 0.0)
print(f"TCR    : {tcr * 100:.1f}%")
print(f"정확도  : {acc * 100:.1f}%")

# Step 4: 배포 판정 (기준 미달 시 sys.exit(1))
eval.gate(tcr=60, accuracy=50)
print("\n✅ Harness Gate 통과 — 배포 가능")
```

이 코드를 실행하면 Harness Engineering의 전체 흐름을 경험할 수 있다.
- Config 선언 → 측정 → 보고서 → Gate 판정 → 배포 승인/차단

---

## 3.9 실전 예제 파일

이 챕터에서 설명한 Harness Engineering 개념을 바로 실행해볼 수 있는 예제 파일이 준비되어 있다.

**기본 예제**: [`Evaluator_Examples/ch03_harness_basics.py`](../../Evaluator_Examples/ch03_harness_basics.py)

| 섹션 | 내용 |
|------|------|
| 섹션 1 | Harness 3요소 (Tracker·Config·Gate) 기초 흐름 |
| 섹션 2~7 | Group A–G 각 1개 Config씩 PASS 시나리오 실전 시연 |
| 섹션 7 | `HarnessEvaluationGate.enforce()` — 배포 판정 전체 흐름 |

```bash
python Evaluator_Examples/ch03_harness_basics.py    # Gate A~G 전체 PASS 시연
```

> **관련 챕터 예제**: Gate A–G FAIL 케이스는 [Chapter 4 — `ch04_group_a.py`](../Part_II_지표시스템/Chapter_04_GroupA_목표달성.md)에서, CI/CD 최소 게이팅은 [Chapter 18 — `ch18_cicd_gate.py`](../Part_V_프로덕션운영/Chapter_18_CICD_품질게이팅.md)에서, 버전 비교 배포 결정은 [Chapter 20 — `ch20_deployment.py`](../Part_V_프로덕션운영/Chapter_20_프로덕션_배포전략.md)에서 확인한다.

---

## 3.10 이 챕터의 핵심 요약

| 개념 | 한 줄 정의 |
|------|-----------|
| Harness Engineering | AI 에이전트의 배포 가능 여부를 코드로 판정하는 품질 공학 방법론 |
| Tracker | 런타임에 무슨 일이 일어났는지 측정하는 관찰자 (25개) |
| Config | 어떤 상태가 합격인지 코드로 선언하는 기준서 (33개) |
| Gate | Tracker 측정값과 Config 기준을 대조해 배포 판정을 내리는 심판 |
| Gate A-G | 7개 배포 관문 — 58개 지표를 독립적인 품질 차원별로 묶고, 각각 PASS/WARN/FAIL 판정을 내리는 구조 |
| HarnessEvaluationGate | Gate A-G를 한 번에 종합 실행하는 판정 메커니즘 (3요소 중 Gate 역할) |
| fail_on_violation | Config 조건 위반 시 TaskResult.success를 False로 강제하는 플래그 |
| Config-as-Code | 배포 기준을 소스 코드로 선언하는 패턴 |

Chapter 4부터는 Group A(목표달성)를 시작으로 각 Group을 깊이 탐구한다.

> 🔗 **다음 챕터**: Chapter 4 — Group A: 목표달성 지표  
> 에이전트가 사용자 지시를 얼마나 충실하게 이행하는지 측정하는 3개 Tracker와 6개 Config를 완전히 이해한다.
