# Appendix F. 용어 사전

Agent Evaluator v0.8.5에서 사용하는 주요 용어를 영문 기준 가나다 순으로 정리한다.

---

## AI First vs AI Native

AI 에이전트 평가를 이해하기 위한 핵심 패러다임 구분.

**AI First**는 기존의 소프트웨어·조직·프로세스에 AI 기능을 *추가*하는 접근이다. 기존 워크플로우가 선행하고 AI가 그것을 보조하거나 자동화한다. 평가 방식도 기존 QA 위에 AI 관련 테스트를 추가하는 방식 — 프롬프트 개선, 모델 버전 A/B 비교, 출력 수동 검토. 소프트웨어 중심 사고방식이 그대로 유지된다.

**AI Native**는 프로세스 자체를 AI 에이전트를 중심으로 *처음부터* 설계하는 접근이다. AI가 보조 도구가 아닌 핵심 실행 주체다. 에이전트는 자율적으로 도구를 선택하고, 멀티스텝 추론으로 목표를 추구하며, 사람이 하던 일을 직접 수행한다. 소프트웨어가 AI를 포함하는 것이 아니라 AI가 소프트웨어 구조를 결정한다.

| 구분 | AI First | AI Native |
|------|---------|-----------|
| **AI 위치** | 기존 프로세스에 추가 | 프로세스의 핵심 실행 주체 |
| **평가 접근** | 기존 QA + AI 테스트 추가 | 에이전트 전용 새 평가 체계 |
| **품질 기준** | "버그가 없는가?" | "지금 이 조건에서 배포해도 되는가?" |
| **측정 방식** | 결정론적 assert | 통계적 배포 판정 |
| **대표 도구** | 단위/통합 테스트 + LLM 수동 검토 | Harness Engineering (Tracker × Config × Gate) |

**평가에 대한 함의**: AI First 평가는 기존 QA를 확장하는 문제다. AI Native 평가는 에이전트의 고유한 속성(비결정론적 출력, 자율성, 다단계 추론, 도구 활용)이 기존 테스팅의 전제를 무너뜨리므로 새로운 패러다임이 필요하다.

참조: Chapter 1 §1.5 / Appendix G §G.1.5

---

## AI Native 평가란 무엇인가

**AI Native 평가(AI Native Evaluation)**는 AI 에이전트의 고유한 작동 방식에서 비롯되는 5가지 속성을 측정 대상으로 삼는 평가 패러다임이다.

기존 소프트웨어 테스팅은 "입력 X → 출력 Y, Y가 맞으면 통과"라는 결정론적 검증에 기반한다. AI 에이전트는 이 가정이 성립하지 않는다. 같은 입력에도 경로가 달라지고(비결정론적), 여러 도구를 자율적으로 선택하며(도구 활용), 이전 컨텍스트에 따라 응답이 달라진다(컨텍스트 의존성). 단일 `assert` 테스트로는 품질을 확정할 수 없으며 **통계적 측정 + 배포 판정**이 필수다.

**AI Native 평가는 "더 나은 테스팅"이 아니다.** 이는 자율 에이전트의 고유한 특성에서 비롯된 전혀 다른 평가 패러다임이다. Context Engineering이 "컨텍스트 창에 무엇을 넣을 것인가"를 최적화하듯이, AI Native 평가는 "에이전트가 외부 제어 구조(Harness) 안에서 배포 가능한 수준으로 동작하는가"를 통계적으로 판정한다.

### AI Native 평가의 구조적 어려움과 한계

AI Native 환경의 평가는 기술적으로 완전히 해결되지 않은 영역을 포함한다.

| 어려움 | 이유 | 현재 한계 |
|--------|------|----------|
| **비결정론적 출력** | 동일 입력에도 매번 다른 응답 | 단일 테스트 케이스로 품질 확정 불가 |
| **Ground Truth 부재** | 복잡한 태스크의 "정답"이 하나가 아님 | 자동 채점 정확도가 인간 판단과 괴리 |
| **평가 비용** | LLM-as-Judge는 API 비용 발생 | 프로덕션 전량 평가 불가, 샘플링 필수 |
| **순환 참조 문제** | AI로 AI를 평가할 때 Judge 편향 내재 | Judge 모델 자체의 신뢰도 보장 불가 |
| **드리프트 탐지 지연** | 성능 저하가 점진적·무증상으로 발생 | 임계값 돌파 전 조기 감지 어려움 |
| **돌발 행동** | 설계하지 않은 동작이 예상치 못하게 등장 | 사전 테스트 케이스로 커버 불가 |
| **다중에이전트 복잡성** | 에이전트 수 증가 시 상호작용 경우의 수 폭발 | 전수 테스트가 계산적으로 불가능 |

Harness Engineering은 이 한계를 인정하면서 **"완벽한 검증" 대신 "충분히 높은 통계적 신뢰 수준"** 을 목표로 설계된다. 7개 Gate는 이 어려움을 차원별로 분리해 관리 가능한 단위로 쪼갠 결과다.

### AI Native 5속성 ↔ Harness Group 매핑

| AI Native 속성 | 기존 테스팅의 한계 | 대응 Harness Group |
|--------------|----------------|------------------|
| 비결정론적 출력 | 단일 assert 통과 ≠ 재현 보장 | Gate A (정확도 통계), Gate C (재현성) |
| 컨텍스트 의존성 | 격리 테스트로 실 품질 측정 불가 | Gate A (완수율), Gate B (루프·범위) |
| 다단계 추론 | 최종 결과만 검증, 중간 오류 미탐지 | Gate B (워크플로우), Gate G (설명가능성) |
| 도구 활용 | 도구 호출 권한·패턴 검증 체계 없음 | Gate B (도구 안전성), Gate E (보안경계) |
| 자율적 목표 추구 | 범위 이탈 행동 탐지 불가 | Gate B (범위 일탈), Gate F (다중에이전트 교착) |

참조: Chapter 1 §1.5 / Appendix G §G.9

---

## AI Native 5속성 정의

Agent-Evaluator가 기존 소프트웨어 테스팅과 다른 이유를 설명하는 5가지 AI 에이전트 고유 속성.

| # | 속성 | 정의 | 연관 Group |
|---|------|------|-----------|
| 1 | **비결정론적 출력** (Non-deterministic Output) | 동일 입력에도 매번 다른 응답을 생성하는 특성. 단일 테스트로 품질을 확정할 수 없으며 통계적 측정이 필수다. | Gate A, C |
| 2 | **컨텍스트 의존성** (Context Dependency) | 이전 대화 내용·도구 결과·프롬프트 구조가 응답에 깊이 영향. 격리된 단위 테스트로는 실 품질 측정 불가. | Gate A, B |
| 3 | **다단계 추론** (Multi-step Reasoning) | 단일 응답이 아닌 계획 수립 → 도구 호출 → 결과 통합의 연쇄로 구성. 중간 단계의 오류가 최종 결과를 크게 훼손. | Gate B, G |
| 4 | **도구 활용** (Tool Utilization) | 외부 API, 파일 시스템, 데이터베이스 등을 자율적으로 호출. 도구 선택 오류·과잉 호출·인가 위반이 새로운 실패 모드를 만든다. | Gate B, E |
| 5 | **자율적 목표 추구** (Autonomous Goal Pursuit) | 명시적 지시 없이 목표 달성을 위해 스스로 행동을 선택. 설계 범위를 벗어난 행동이 예기치 않게 발생할 수 있다. | Gate B, F |

참조: Appendix G §G.9 / Chapter 1 §1.5

---

## Harness Engineering 핵심 용어

---

### AI 최적화 방법론의 3단계 진화

Harness Engineering이 어디서 왔는지를 이해하기 위한 계보.

| 단계 | 시기 | 핵심 관심사 | 핵심 질문 | 대표 정의 |
|------|------|----------|---------|---------|
| **Prompt Engineering** | 2022–2024 | 단일 LLM 호출의 입력 텍스트 최적화 | "어떻게 물어볼까?" | Few-shot, CoT, 역할 페르소나 |
| **Context Engineering** | 2025 | 컨텍스트 창 전체 정보 관리 (RAG·메모리·도구·이력) | "무엇을 넣어줄까?" | Karpathy: "컨텍스트 창을 정확히 채우는 섬세한 과학" |
| **Harness Engineering** | 2026~ | 에이전트 주변 제어 구조 전체 설계 | "배포해도 되는가?" | Hashimoto: "Agent = Model + Harness" |

Context Engineering이 모델에 *무엇을 줄 것인가(입력 관리)*를 다룬다면, Harness Engineering은 모델 주변의 *제어 구조 전체(외부 통제 시스템)*를 설계한다. Context Engineering은 실행 이전(pre-execution)에만 작동하며, 실행 후 에이전트가 실제로 어떻게 동작했는지 검증하는 **배포 준비도 공백**을 채우지 못한다.

참조: Chapter 3 §3.1.1 / Appendix G §G.1.5

---

### 배포 준비도 공백 (Deployment Readiness Gap)

Context Engineering이 해결하지 못하는 핵심 문제. 실행 이전의 입력 최적화(RAG, 메모리, 도구 스펙 구성)는 완벽하더라도, 실행 이후 에이전트가 실제로:

- 정확한 정보를 반환했는지 (정확도가 기준을 충족하는지)
- SLA 내에서 응답했는지 (P95 지연이 계약 범위 안에 있는지)
- 보안 정책을 위반하지 않았는지
- 이 상태로 프로덕션에 배포해도 되는지

…를 자동으로 판정하는 메커니즘이 없다. Harness Engineering은 이 공백을 Tracker × Config × Gate 3요소로 채운다.

참조: Chapter 3 §3.1.1

---

### Guides + Sensors

Harness Engineering의 두 가지 핵심 제어 메커니즘.

**Guides (사전 제어, Feedforward)**: 에이전트가 실행되기 *전에* 작동하는 지침과 제약. 무엇을 해도 되고 무엇을 하면 안 되는지를 선언한다. Agent-Evaluator에서 33개 Harness Config 클래스로 구현된다.

**Sensors (사후 제어, Feedback)**: 에이전트가 실행된 *후에* 작동하는 측정과 검증. 실제로 어떻게 동작했는지를 측정하고 기준과 비교한다. Agent-Evaluator에서 25개 Tracker 클래스로 구현된다.

| Harness 개념 | Agent-Evaluator 구현 | 역할 |
|-------------|---------------------|------|
| **Guide** — 행동 제약 | 33개 Config 클래스 (`InstructionConfig`, `SLAConfig`, `LoopDetectionConfig` 등) | 에이전트가 무엇을 해야 하고 무엇을 하면 안 되는가를 `@agent_eval` 데코레이터로 선언 |
| **Sensor** — 실행 측정 | 25개 Tracker 클래스 (`AccuracyEvaluator`, `LatencyTracker`, `HallucinationDetector` 등) | 에이전트가 실행된 후 자동으로 지표를 수집·계산 |
| **Gate** — 통합 판정 | `HarnessEvaluationGate`, `agent-eval gate` CLI | Guide 위반 여부와 Sensor 측정값을 종합해 PASS / WARNING / FAIL 판정 |

참조: Chapter 3 §3.1.2

---

### Gate (배포 판정)

Tracker(Sensor)가 수집한 측정값과 Config(Guide)가 선언한 기준을 대조하여 **"지금 배포해도 되는가"를 자동으로 판정**하는 단계. 두 가지 형태가 있다.

| 형태 | 사용 상황 | 체크 항목 |
|------|----------|---------|
| `eval.gate(tcr=85, accuracy=70)` | 단순 배포 기준 (TCR·Accuracy) | 2개 지표 임계값 |
| `HarnessEvaluationGate(report).evaluate()` | Gate A–G 종합 판정 | 7개 Group 전체 Config 위반 여부 |

**개발자 관점**: `fail_on_violation=True`로 선언한 Config가 위반되면 `TaskResult.success=False`가 누적되고, `gate()` 호출 시 `sys.exit(1)`로 CI/CD 파이프라인을 차단한다.

**QA 관리자 관점**: Gate 결과는 대시보드의 "Gate A–G PASS/WARN/FAIL" 상태, HTML 리포트의 `blocking_violations` 목록, `agent-eval gate` CLI의 exit code로 확인한다.

```python
# 단순 Gate
eval.gate(tcr=85, accuracy=70)   # 미달 시 sys.exit(1)

# 종합 Gate
from agent_evaluator import HarnessEvaluationGate
result = HarnessEvaluationGate(report).evaluate()
# → {"passed": True/False, "groups": {"A": ..., "B": ..., ...}}
```

참조: Chapter 3 §3.6 / Chapter 18 (CI/CD) / Appendix B (CLI)

---

### Tracker (관찰·측정자)

에이전트 실행 중 자동으로 지표를 수집하는 25개 관찰 클래스의 통칭. 판단하지 않고 오직 측정만 한다. Harness Engineering의 **Sensor** 역할이다.

`PerformanceMonitor`에 `record_task(result)`를 호출할 때 내부의 Tracker들이 자동으로 동작한다. 별도 코드 없이 `@agent_eval` 데코레이터 하나로 모든 기본 Tracker가 활성화된다.

**개발자 관점**: Tracker는 `TaskResult`의 각 필드(`execution_time`, `tool_calls`, `accuracy_score` 등)를 채운다. opt-in Tracker는 `PerformanceMonitor` 생성자 파라미터로 활성화한다.

**QA 관리자 관점**: Tracker가 수집한 데이터가 Gate A–G의 점수 원천이다. "Gate D 점수가 낮다"면 `LatencyTracker`나 `TokenEconomyTracker`가 SLA 초과를 탐지한 것이다.

| 종류 | Tracker | 담당 Group | 활성화 |
|------|---------|-----------|--------|
| 기본 자동 | `TaskCompletionTracker`, `AccuracyEvaluator`, `ResponseQualityEvaluator`, `LatencyTracker`, `TokenEconomyTracker` | A, D | 항상 |
| 기본 자동 | `ToolCallAnalyzer`, `WorkflowExecutionTracker`, `RetryCorrectionTracker` | B, C | 항상 |
| 기본 자동 | `AgentCoordinationTracker`, `ToolSelectionTracker` | F | 항상 |
| opt-in | `HallucinationDetector` | **C** | `enable_hallucination_detection=True` |
| opt-in | `InputSanitizationTracker`, `OutputLeakageDetector`, `ToolAuthorizationTracker`, `PrivilegeEscalationDetector`, `ToolChainAttackDetector` | E | `enable_security_metrics=True` |
| opt-in | `LLMJudge` (기본 5차원; RAG 시 +faithfulness, G-Eval 시 +커스텀 기준) | G | `enable_llm_judge=True` + API 키 |

참조: Chapter 2 §2.4 / Chapter 3 §3.2 / Appendix A §Part 1

---

### Config-as-Code

에이전트의 배포 기준을 소스 코드로 선언하는 패턴. "문서나 관행"이 아닌 "실행 가능한 코드"로 품질 기준을 명시한다. Harness Config 클래스들이 이 패턴의 구현체다. Harness Engineering의 **Guide** 역할이다.

```python
# Config-as-Code 예시
from agent_evaluator import SLAConfig, ThreatSeverityConfig
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor,
            sla=SLAConfig(p95_ms=2000, fail_on_violation=True),
            threat_severity=ThreatSeverityConfig(warn_score=3.0, fail_score=7.0, fail_on_critical=True))
def agent(question, ground_truth=""): ...
```

참조: Part II 전체 / Appendix A §Part 2 (33개 Config 레퍼런스)

---

### fail_on_violation

Harness Config의 공통 플래그. `True`로 설정하면 해당 Config 조건 위반 시 `TaskResult.success = False`로 강제 처리된다. CI/CD 파이프라인에서 배포를 자동 차단하는 핵심 메커니즘이다.

참조: Appendix A §Part 2 / Chapter 18 (CI/CD 품질 게이팅)

---

### Gate A-G (Harness 7차원)

58개 지표를 7개 품질 차원으로 분류하는 Harness Engineering의 핵심 구조. 7개 차원은 자율 에이전트의 본질적 속성(자율성·확률론적 동작·프로덕션 계약·외부 위협·시스템 복잡성·운영 가능성)에서 필연적으로 도출된다.

| Group | 차원 | 핵심 질문 | 도출 속성 |
|-------|------|-----------|---------|
| A | 목표달성 | 에이전트가 지시를 완수했는가? | 확률론적 동작 |
| B | 행동무결성 | 의도치 않은 행동이 없었는가? | 자율성 |
| C | 신뢰성 | 일관되고 재현 가능한가? | 확률론적 동작 |
| D | 성능계약 | SLA/비용 계약을 지켰는가? | 프로덕션 계약 |
| E | 보안경계 | 공격·유출을 차단했는가? | 외부 위협 노출 |
| F | 다중에이전트 협업 | 교착 없이 협력했는가? | 시스템 복잡성 |
| G | 운영관측성 | 실패 원인을 즉시 추적할 수 있는가? | 블랙박스 동작 |

참조: Chapter 3 (Harness Engineering 기초) / Part II 전체

---

### Harness Config

에이전트의 배포 기준을 선언하는 데이터클래스 계열. 33개 클래스가 Gate A-G에 분산되어 있다. `@agent_eval` 데코레이터나 `PerformanceMonitor`에 주입해 사용한다. Harness Engineering의 **Guide** 역할이다.

```python
from agent_evaluator import SLAConfig, ThreatSeverityConfig, ReproducibilityConfig
```

전체 목록과 사용법: Appendix A §Part 2 (33개 Config 완전 레퍼런스)

```python
# 방법 1: 데코레이터 파라미터
@agent_eval(monitor,
            sla=SLAConfig(p95_ms=2000, fail_on_violation=True),
            instructions=InstructionConfig(required_keywords=["서울"]))
def agent(question, ground_truth=""): ...

# 방법 2: HarnessEvaluationGate 일괄 적용
from agent_evaluator import HarnessEvaluationGate
gate = HarnessEvaluationGate(report)
result = gate.evaluate()  # {"passed": True, "violations": [...]}
```

---

### Harness Engineering

자율 AI 에이전트를 **외부에서 제어·측정·판정하는 시스템 전체**를 설계하는 AI-native 공학 분야. **Tracker(Sensor, 사후 측정) × Config(Guide, 사전 제약) × Gate(배포 판정)** 3요소로 구성된다.

기존 소프트웨어 테스팅("버그가 없는가?")에서 발전한 것이 아니라, **Prompt Engineering → Context Engineering → Harness Engineering** 진화 흐름의 최신 단계다. Mitchell Hashimoto의 정의: **"Agent = Model + Harness"** — 모델(가중치·추론 엔진)을 제외한 모든 것이 Harness에 속한다.

기존 QA가 "결함 부재(결정론적 통과/실패)"를 묻는다면, Harness Engineering은 "**지금 이 통계적 조건에서 배포해도 되는가?**"를 코드로 선언하고 자동으로 판정한다. Context Engineering이 실행 이전에만 작동하는 것과 달리, Harness Engineering은 실행 전(Guide: Config 선언)과 실행 후(Sensor: Tracker 측정)를 모두 제어한다.

**3가지 배포 실패 유형과 Harness의 대응:**

| 실패 유형 | 설명 | Harness 대응 |
|---------|------|-------------|
| 측정 없는 배포 | "응답이 나온다"만 확인하고 배포 | Tracker 25개 자동 측정 |
| 기준 없는 측정 | 숫자는 있으나 팀마다 판단이 달라 결정 불가 | Config-as-Code로 기준을 소스에 명시 |
| 배포 후 무감지 | 배포 당시 통과했으나 성능이 서서히 저하 | Gate + 드리프트 탐지(`agent-eval trend`) |

**두 독자의 Harness 진입점:**
- **개발자**: `@agent_eval(monitor, sla=SLAConfig(...))` — Config 선언이 Harness의 시작
- **QA 관리자**: Gate A–G 판정 결과 — Config 위반 집계가 배포 결정의 근거

참조: Chapter 1 §1.3 / Chapter 3 §3.1 / Chapter 3 §3.5

---

### HarnessEvaluationGate

Gate A-G 전체를 한 번에 체크하는 종합 배포 판정 도구. 각 Gate의 Config 위반 여부를 집계해 최종 pass/fail을 반환한다. `agent-eval gate` CLI의 내부 구현체이기도 하다.

```python
from agent_evaluator import HarnessEvaluationGate
gate = HarnessEvaluationGate(report)
result = gate.evaluate()  # {"passed": True, "violations": [...]}
```

참조: Chapter 18 (CI/CD Harness Gate)

---

### 확률론적 품질 (Probabilistic Quality)

AI 에이전트 품질을 단일 점수가 아닌 **분포**로 이해하는 패러다임. 같은 `accuracy=0.85`라도 분산이 작으면 안정적, 크면 예측 불가능한 에이전트다. AI Native 평가의 핵심 어려움 중 하나이며, Wilson Score Interval 등 통계적 신뢰구간 기반 임계값 설정이 이 패러다임의 구현이다.

참조: Chapter 14 (임계값 설정) / Appendix G §G.3.3

---

### 드리프트 (Drift)

에이전트 성능이 배포 후 시간이 지남에 따라 저하되는 현상. 코드 변경·모델 업데이트·프롬프트 수정·학습 데이터 변화 4가지 소스에서 발생한다. AI Native 평가의 구조적 어려움으로, 저하가 점진적·무증상으로 발생하므로 탐지가 어렵다. `agent-eval trend`와 `RunTrendAnalyzer`로 조기 감지한다.

참조: Chapter 18, Chapter 21

---

### 자기개선 루프 (Self-Improvement Loop)

평가 결과를 에이전트 개선에 환류하는 3단계 파이프라인.
1. **감지**: RunTrendAnalyzer로 성능 하락 탐지
2. **진단**: Group별 Tracker 드릴다운으로 원인 귀속
3. **개선**: 프롬프트/파인튜닝/Config 재조정

참조: Chapter 21 (지속 평가·자기개선 파이프라인)

---

## 영문 약어 / 클래스 / 함수 용어

---

### AccuracyEvaluator

Gate A 정확도 평가 클래스. `PerformanceMonitor` 내부에서 자동으로 초기화된다. QA 태스크에서는 TokenOverlapF1 (40%) + Jaccard (30%) + LCS (20%) + CharSimilarity/Levenshtein (10%) 가중 조합으로 정확도를 계산하고, 코드 태스크에서는 AST 비교를 사용한다. `ground_truth`가 필수이며 빈 문자열이면 0.0이 반환된다.

참조: Appendix A — Gate A 지표 / Chapter 3

---

### AdaptivePolicy

비용 최적화를 위한 적응형 샘플링 정책 클래스. 태스크 복잡도와 비용에 따라 평가 샘플링 비율을 동적으로 조정한다. `SamplingStage`와 함께 사용한다.

```python
from agent_evaluator import AdaptivePolicy, SamplingStage
```

참조: Chapter 10 §10.3 (CostTracker + AdaptivePolicy)

---

### agent_eval (데코레이터)

단일 함수를 평가 대상으로 등록하는 핵심 데코레이터. `PerformanceMonitor`에 `TaskResult`를 자동으로 기록한다. `framework=`, `rag_mode=`, `security=SecurityConfig()`, `flush_every=`, `alert_rules=` 등 다양한 파라미터를 지원한다.

```python
from agent_evaluator.decorators import agent_eval
```

참조: Appendix B / Chapter 12 (데코레이터 완전정복)

---

### AlertRuleBuilder

`SimpleTaskAlertRule` 생성을 간소화하는 팩토리 클래스. `when_accuracy_below()`, `when_latency_above()`, `when_completion_below()`, `when_error()`, `when_tool_calls_exceed()` 5개 정적 메서드를 제공한다.

참조: Chapter 16 (알림시스템 운영)

---

### AnomalyDetector

이상 탐지 클래스. 통계적 방법(Z-score, IQR)으로 지표 이상치를 자동 감지하고 `AnomalyEvent`를 발생시킨다. `explain_event()` / `scan_with_explain()`으로 원인 설명과 권고사항을 제공한다.

```python
from agent_evaluator import AnomalyDetector, AnomalyEvent
```

참조: Chapter 10 §10.3 (AnomalyDetector)

---

### batch_eval (데코레이터)

리스트 입력을 받아 일괄 처리하는 평가 데코레이터. `concurrent=True`로 병렬 처리, `return_format="dataframe"`으로 pandas DataFrame 반환이 가능하다. 함수의 첫 번째 인자는 반드시 리스트여야 한다.

```python
from agent_evaluator.decorators import batch_eval
```

참조: Chapter 12 / Appendix E (오류 #10)

---

### conversation_eval (데코레이터)

멀티턴 대화 평가 데코레이터. `session_id_arg` 파라미터로 세션을 구분하고, 각 턴의 문맥 유지율 / 주제 일관성 / 점진적 깊이를 자동으로 측정한다. 비동기 제너레이터도 지원한다.

```python
from agent_evaluator.decorators import conversation_eval
```

참조: Chapter 11 §11.4 (멀티턴 대화 평가) / Appendix E (FAQ Q7)

---

### ConversationSession

멀티턴 대화 평가의 핵심 클래스. `add_turn()`으로 사용자/에이전트 발화를 기록하고 `compute_metrics()`로 `ConversationMetrics`를 계산한다. `context_retention`, `topic_coherence`, `progressive_depth`, `session_completion` 등의 지표를 제공한다.

```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn
```

참조: Chapter 11 §11.4

---

### create_taskresult()

`TaskResult` 생성을 단순화하는 헬퍼 함수. `question`, `response`, `ground_truth`, `execution_time`, `task_type`을 입력하면 `accuracy_score`, `completion_score`, `success`, `timestamp` 등을 자동으로 계산한다.

```python
from agent_evaluator import create_taskresult
```

참조: Appendix A / Chapter 2 §2.4

---

### DeepEval

Confident AI에서 개발한 오픈소스 LLM 평가 라이브러리. Agent Evaluator의 `[eval]` extra를 통해 G-Eval, Hallucination Score, Toxicity, Bias, Answer Relevancy 5개 지표를 Gate G에서 추가로 활용할 수 있다. `pip install "agent-evaluator[eval]"`로 설치하며 `OPENAI_API_KEY`가 필요하다.

출처: docs.confident-ai.com

참조: Appendix A (Gate G) / Appendix D (평가 플랫폼 비교)

---

### EvalDecorator

`QuickEval` 내부에서 사용하는 데코레이터 클래스. 직접 인스턴스화하여 `.qa`, `.rag`, `.tool_use` 등 단축 속성을 통해 다양한 태스크 유형에 적용할 수 있다.

```python
from agent_evaluator.decorators import EvalDecorator
```

참조: Chapter 12

---

### EvaluationReport

`monitor.generate_report()`가 반환하는 불변 보고서 객체. `task_completion_rate`, `overall_accuracy`, `average_latency`, `hallucination_rate`, `security_incidents` 등 주요 지표를 속성으로 제공한다. `to_dict()` / `from_dict()` / `from_json()`으로 직렬화/역직렬화를 지원한다.

```python
from agent_evaluator import EvaluationReport
```

참조: Chapter 2 §2.4

---

### extra_metrics.harness_groups (JSON 결과 키)

평가 결과 JSON 파일에서 Gate A–G 판정 결과가 저장되는 키 경로. 내부 구현 명칭이므로 직접 접근 시 이 키를 사용해야 한다.

```python
import json

with open("results/evaluation.json") as f:
    data = json.load(f)

# Gate A–G 결과는 extra_metrics.harness_groups 아래에 위치한다
gate_results = data["extra_metrics"]["harness_groups"]
gate_a = gate_results.get("A")   # {"status": "PASS", "score": 0.91, ...}
gate_d = gate_results.get("D")   # {"status": "WARN", "violations": [...], ...}
```

> **주의**: 대시보드 UI나 HTML 리포트에서는 "Gate A–G"로 표시되지만, JSON 파일의 실제 키는 `extra_metrics.harness_groups`다. `harness_gates`라는 키는 존재하지 않는다.

참조: Chapter 3 §3.5 / Appendix A (전체 JSON 결과 구조)

---

### evaluation_session

동기 평가 세션 컨텍스트 매니저. `with` 블록 종료 시 자동으로 `save_to_file()`을 호출한다. 예외가 발생해도 데이터를 안전하게 저장한다.

```python
from agent_evaluator import evaluation_session

with evaluation_session("output_filename") as monitor:
    monitor.record_task(result)
```

비동기 버전: `async_evaluation_session`

참조: Appendix E (오류 #16)

---

### flush_every

`@agent_eval`, `@batch_eval` 데코레이터의 파라미터. N번 호출마다 `save_to_file()`을 자동으로 실행한다. 장시간 실행 평가에서 중간 저장을 보장한다.

```python
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question: str, ground_truth: str = "") -> str: ...
```

참조: Chapter 12 / Appendix E (오류 #14)

---

### faithfulness (RAG 충실도)

RAG(Retrieval-Augmented Generation) 평가에서 에이전트의 응답이 검색된 컨텍스트 문서에 얼마나 근거하고 있는지를 측정하는 0–5 점수. `LLMJudge`의 기본 5차원에는 포함되지 않으며, `rag_mode=True` + `context` 인자를 함께 전달할 때만 자동으로 추가된다.

```python
# faithfulness는 RAG 모드에서만 활성화된다
judge = LLMJudge(model="claude-haiku-4-5-20251001")
result = judge.judge("t1",
    question="...",
    response="...",
    context="검색된 문서...")   # context 전달 시 faithfulness 자동 추가
result["scores"]["faithfulness"]  # 0–5
```

> **주의**: context 없이 `judge()`를 호출하면 `faithfulness` 키가 결과에 존재하지 않는다. `None`이 저장되며 집계 통계에서 제외된다.

참조: Appendix A (Gate G) / Chapter 12 (LLMJudge) / LLM Judge (LLMJudge) 항목

---

### G-Eval (커스텀 기준 채점)

`LLMJudge`의 `judge_criteria` 파라미터로 사용자 정의 평가 기준을 추가하는 기능. DeepEval의 G-Eval 방식과 유사하게 커스텀 차원을 LLM 채점기에 주입한다. 기본 5차원과는 별도로 `criteria_scores` / `criteria_overall` 키로 반환된다.

```python
judge = LLMJudge(
    judge_criteria=["medical_accuracy", "citation_quality"],
)
result = judge.judge("t1", question="...", response="...")
result["scores"]["criteria_scores"]   # {"medical_accuracy": 4, "citation_quality": 5}
result["scores"]["criteria_overall"]  # 커스텀 기준 평균
```

데코레이터에서 사용 시:
```python
from agent_evaluator.decorators import LLMJudgeConfig

@agent_eval(monitor,
    llm_judge=LLMJudgeConfig(criteria=["safety", "evidence_based"]))
def agent(question, ground_truth=""): ...
```

참조: Chapter 12 §12.3 (LLMJudge G-Eval) / Appendix A (Gate G)

---

### GoldenSetBuilder

우수 평가 케이스를 수집하고 골든 데이터셋을 관리하는 클래스. `merge_to_golden()`, `push_to_phoenix()` 메서드를 제공한다. `agent-eval dataset build` CLI 명령어가 내부적으로 사용한다.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder
```

참조: Chapter 11 §11.3 (골든 데이터셋 관리) / Appendix B (agent-eval dataset)

---

### HallucinationDetector

**Gate C (신뢰성)** 환각 탐지 클래스 (규칙 기반). Unsupported Claim과 Numerical Inconsistency 두 가지 방법으로 탐지한다. 정확도 70~80%, 오버헤드 < 5ms. `enable_hallucination_detection=True`로 opt-in해야 한다. 외부 평가 라이브러리 DeepEval Hallucination Score(LLM 기반, 90~95% 정확도)와 점수 방향이 반대이므로 주의한다.

> ⚠️ 이전 버전 문서에 Gate A로 잘못 기재된 경우가 있음. 정확한 Group은 **C (신뢰성)**.

참조: Appendix A (Gate C #1) / Appendix E (오류 #5)

---

### LLM Judge (LLMJudge)

`ground_truth` 없이 LLM을 평가자로 사용하는 클래스. Completeness / Relevance / Factual Consistency / Toxicity / Bias 5차원을 기본 채점하며, RAG 컨텍스트가 있으면 Faithfulness(0~5)를, `judge_criteria` 지정 시 커스텀 차원을 추가한다. v0.7.8부터 기본 설치에 포함되어 있으며 API 키(`OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY`)만 있으면 바로 사용 가능하다. AI Native 평가의 **순환 참조 문제**(AI로 AI를 평가)를 내재하므로, `sample_rate`로 비용과 편향을 균형있게 관리한다.

```python
from agent_evaluator import LLMJudge
```

참조: Appendix C (환경변수) / Appendix E (오류 #13)

---

### OTEL (OpenTelemetry)

분산 시스템 관측가능성을 위한 오픈소스 표준. CNCF(Cloud Native Computing Foundation)가 관리하며 벤더 중립적 SDK와 프로토콜을 제공한다. Agent Evaluator에서는 `setup_otel()` 호출 후 `record_task()` 실행 시 OTLP 스팬을 자동으로 발행한다. v0.7.8부터 기본 설치에 포함되어 있어 별도 설치 불필요.

출처: opentelemetry.io

참조: Appendix B (agent-eval monitor) / Appendix C / Chapter 19 (Phoenix OTEL 모니터링)

---

### OTLP (OpenTelemetry Protocol)

OpenTelemetry 데이터 전송 프로토콜. HTTP 또는 gRPC 방식으로 스팬(span) 데이터를 Collector(Phoenix 등)로 전송한다. gRPC 기본 포트는 4317, HTTP 기본 포트는 4318이다. Phoenix는 6006 포트에서 OTLP HTTP를 수신한다. Agent Evaluator는 OTLP HTTP 방식(`/v1/traces` 엔드포인트)을 사용한다.

출처: opentelemetry.io/docs/specs/otlp/ · docs.arize.com/phoenix

참조: Appendix E (오류 #1) / Chapter 19

---

### PerformanceMonitor

Agent Evaluator의 중앙 오케스트레이터 클래스. 모든 Tracker(Gate A-G)를 내부에서 초기화하고 `record_task()`, `generate_report()`, `save_to_file()` 등의 메서드를 제공한다. `for_rag_evaluation()`, `for_secure_agents()` 팩토리 메서드로 용도별 최적 설정을 빠르게 적용할 수 있다.

```python
from agent_evaluator import PerformanceMonitor
```

참조: Appendix A / Chapter 2 §2.4

---

### Phoenix (Arize Phoenix)

Arize AI에서 개발한 오픈소스 LLM 관측가능성 플랫폼. OpenInference(OTEL 기반 AI 관측가능성 의미 규약) 기반으로 트레이스, 평가 지표, 데이터셋, 프롬프트 4개 탭을 제공한다. `agent-eval monitor`로 로컬에서 기동하며 기본 포트는 6006이다.

출처: docs.arize.com/phoenix

참조: Appendix B / Appendix C / Appendix E (오류 #1) / Chapter 19 (Phoenix OTEL 모니터링)

---

### QuickEval

`PerformanceMonitor`와 `EvalDecorator`를 1줄로 시작하는 원스톱 Facade 클래스. `for_rag()`, `for_security()`, `for_llm_judge()` 팩토리 메서드와 `.qa`, `.rag`, `.tool_use` 등 단축 데코레이터를 제공한다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
```

참조: Chapter 2 §2.3 / Appendix E (FAQ)

---

### Ragas

RAG(Retrieval-Augmented Generation) 평가 전문 오픈소스 라이브러리. Agent Evaluator의 `[eval]` extra를 통해 Faithfulness, Answer Relevancy, Context Precision, Context Recall 4개 지표를 Gate G에서 추가로 활용할 수 있다. `pip install "agent-evaluator[eval]"`로 설치하며 `OPENAI_API_KEY`가 필요하다. 버전 0.4.x API(`EvaluationDataset`, `SingleTurnSample`)를 사용한다.

출처: docs.ragas.io

참조: Appendix A (Gate G) / Appendix D / Appendix E (오류 #9)

---

### setup_otel()

OTEL 스팬 발행 환경을 설정하는 공개 API 함수. `PerformanceMonitor` 생성 이전에 호출해야 한다. `endpoint`는 Phoenix 서버 주소이며 경로(`/v1/traces`)는 포함하지 말 것.

```python
from agent_evaluator import setup_otel

setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-agent",
    enable_metrics=False,
)
```

참조: Appendix C / Appendix E (오류 #1)

---

### SimpleTaskAlertRule

`StreamingEvaluator` 없이 `TaskResult` 기반으로 동작하는 경량 알림 규칙 클래스. `condition` 람다, `handler` 함수, `severity`, `cooldown`으로 구성한다. `agent_eval`, `batch_eval`, `eval_context` 데코레이터의 `alert_rules=` 파라미터에 전달한다.

```python
from agent_evaluator import SimpleTaskAlertRule
```

참조: Chapter 16 (알림시스템 운영) / Appendix E (FAQ)

---

### Span

OTEL에서 단일 작업 단위를 나타내는 추적 데이터 구조. `record_task()` 호출 시 Agent Evaluator가 자동으로 스팬을 생성하여 Phoenix로 전송한다. 스팬에는 `ae.task_type`, `ae.completion_score`, `ae.framework` 등의 속성과 OpenInference 의미 규약 속성(`openinference.span.kind`, `llm.token_count.*`)이 포함된다.

출처: opentelemetry.io/docs/concepts/signals/traces/ · openinference.readthedocs.io

참조: Chapter 19

---

### TCR (Task Completion Rate)

태스크 완료율. Gate A의 핵심 지표로 전체 태스크 중 `is_completed=True`(성공적으로 완료됨)로 표시된 태스크의 비율을 백분율로 표현한다. 95% 이상 우수, 85~95% 양호, 70% 미만 개선 필요.

> **참고**: `completion_score`(0.0~1.0, 부분 완료 점수)와 혼동하지 말 것. TCR은 완료 여부(boolean)의 비율이고, `completion_score`는 완료 품질의 연속 점수다.

참조: Appendix A (Gate A #1)

---

### TaskResult

단일 태스크 실행 결과를 담는 불변 데이터클래스 (`@dataclass(frozen=True)`). 필수 11개 필드(task_id, task_type, success, completion_score, accuracy_score, execution_time, tokens_used, tool_calls, attempts, errors, timestamp)와 선택 13개 필드로 구성된다. `create_taskresult()` 헬퍼로 생성을 권장한다.

```python
from agent_evaluator import TaskResult
```

참조: Appendix A / Chapter 2 §2.4 / Appendix E (오류 #15)

---

### TaskType

태스크 유형을 정의하는 Enum. `QA`, `CODE_GENERATION`, `DATA_ANALYSIS`, `DOCUMENT_CREATION`, `INFORMATION_RETRIEVAL`, `REASONING`, `CREATIVE`, `CODING`, `PLANNING`, `TOOL_USE` 10가지를 지원한다. 문자열과 Enum 혼용이 가능하다 (`TaskType.QA` == `"qa"`).

```python
from agent_evaluator import TaskType
```

참조: Chapter 2 §2.4

---

### TTFT (Time-To-First-Token)

스트리밍 응답에서 첫 번째 토큰이 생성되기까지의 시간. `LatencyTracker.track_ttft()`로 기록하거나 데코레이터 방식에서 제너레이터 함수의 첫 청크 yield 시점에 자동으로 기록된다. v0.7.2+에서 지원.

참조: Appendix A (Gate D #4) / Chapter 7 §7.2 (TTFTVariabilityConfig)

---

### TTFTVariabilityConfig (Gate D)

Gate D(성능 계약)의 Harness Config 중 하나. TTFT(첫 토큰 응답 시간)의 **변동성**을 제어한다. 평균 TTFT가 빠르더라도 응답마다 편차가 크면 사용자 경험이 불안정하다는 점을 포착한다. `PerformanceMonitor` 수준에서 자동 집계되며, 충분한 샘플이 쌓이기 전에는 `insufficient_data_warnings` 경고가 발생할 수 있다.

```python
from agent_evaluator import TTFTVariabilityConfig
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor,
    ttft_variability=TTFTVariabilityConfig(
        max_std_ms=200,       # TTFT 표준편차 상한 (ms)
        max_p95_p50_ratio=3.0 # P95/P50 비율 상한
    ))
def agent(question, ground_truth=""): ...
```

참조: Appendix A (Gate D #4) / Chapter 7 §7.2

---

### CostPredictabilityConfig (Gate D)

Gate D(성능 계약)의 Harness Config 중 하나. task_type별 **토큰 변동계수(CV)**를 측정해 비용 예측 가능성을 관리한다. CV가 낮을수록 같은 유형의 태스크에서 비용이 일정하게 유지된다. `TTFTVariabilityConfig`와 마찬가지로 `PerformanceMonitor` 수준에서 자동 집계되며 샘플이 부족하면 경고가 표시된다.

```python
from agent_evaluator import CostPredictabilityConfig

@agent_eval(monitor,
    cost_predictability=CostPredictabilityConfig(
        max_cv=0.3,           # 토큰 변동계수 상한 (0.3 = 30%)
        fail_on_violation=True
    ))
def agent(question, ground_truth=""): ...
```

참조: Appendix A (Gate D #5) / Chapter 7 §7.3

---

## 한국어 개념 용어

---

### 골든 데이터셋

높은 점수를 받은 우수 평가 케이스의 모음. 새 모델이나 버전과의 회귀 테스트, 파인튜닝 데이터로 활용한다. `agent-eval dataset build` 명령어 또는 `GoldenSetBuilder` 클래스로 자동 생성·관리한다. 기본 저장 경로는 `data/golden_datasets/`.

참조: Appendix B (agent-eval dataset) / Chapter 11 §11.3

---

### 에이전틱 지표

에이전트 고유의 행동 패턴을 측정하는 Gate B 에이전틱 지표들의 총칭. Tool Call Efficiency, Retry & Error Recovery, Tool Selection Accuracy, Agent Coordination, Workflow Execution 5종을 포함한다. LLM API 없이 알고리즘 기반으로 계산된다.

참조: Appendix A (Gate B)

---

### 이상 탐지

정상 범위에서 벗어난 평가 지표를 자동으로 감지하는 기능. `AnomalyDetector` 클래스가 Z-score, IQR 방법으로 이상치를 탐지하고 `AnomalyEvent`를 발생시킨다. `explain_event()`로 원인과 권고사항을 확인한다. AI Native 평가에서 **돌발 행동** 탐지의 핵심 수단이다.

참조: Chapter 10 §10.3

---

### 임계값

평가 지표의 합격/불합격 기준. `agent-eval gate` 명령어에서 `--tcr`, `--accuracy` 등으로 지정하며, `generate_gate_config()`로 현재 데이터 기반 자동 제안을 받을 수 있다. AI Native 환경에서 임계값은 결정론적 통과/실패가 아닌 **통계적 분포 기반**(P95 레이턴시, 평균 TCR, 환각률 상한)으로 설정한다.

참조: Appendix A (각 지표 권장 임계값) / Appendix B (agent-eval gate)

---

### 샘플링

전체 태스크 중 일부만 평가하여 비용과 오버헤드를 줄이는 기법. AI Native 평가의 **평가 비용** 문제에 대한 핵심 대응책이다. `@agent_eval(sample_rate=0.1)`로 10%만 평가하거나, `sample_condition`으로 조건부 샘플링이 가능하다. `AdaptivePolicy`로 동적 샘플링도 지원한다.

참조: Chapter 12

---

### 품질 게이팅

CI/CD 파이프라인에서 품질 임계값 미달 시 배포를 자동으로 차단하는 메커니즘. `agent-eval gate` CLI 명령어 또는 `QuickEval.gate()` 메서드로 구현한다. 임계값 미달 시 `sys.exit(1)`로 파이프라인을 차단한다.

참조: Appendix B (agent-eval gate) / Appendix E (오류 #3)

---

### 환각 탐지

AI 에이전트가 컨텍스트에 근거가 없는 내용을 사실처럼 생성하는 현상(환각)을 탐지하는 기능. Gate C (신뢰성)의 핵심 측정 항목이다. Agent Evaluator는 두 가지 방식을 제공한다: 규칙 기반(`HallucinationDetector`, 무료, opt-in, 정확도 70~80%)과 외부 평가 라이브러리(DeepEval, 정확도 90~95%, API 비용 발생). 두 방식은 점수 방향이 반대이므로 주의가 필요하다.

참조: Appendix A (Gate C #1)

---

### 회귀 테스트

모델 또는 에이전트 업데이트 후 이전 버전 대비 성능 저하 여부를 검증하는 테스트. 골든 데이터셋을 기준으로 `QuickEval.for_regression_eval()` 팩토리 메서드와 `compare()` / `ab_test()` 메서드를 활용한다.

```python
eval = QuickEval.for_regression_eval("results/", baseline_file="baseline.json")
```

참조: Chapter 11 §11.3 / Appendix E (FAQ Q5)
