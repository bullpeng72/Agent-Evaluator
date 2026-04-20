# Chapter 02: Agent-Evaluator 첫 시작

> 좋은 도구는 처음 사용하는 순간부터 작동해야 한다.

---

## 2.1 설치 — 용도별 extras 선택 가이드

Agent-Evaluator는 v0.7.8부터 기본 설치(`pip install agent-evaluator`)에 SDK 전체 기능이 포함됩니다. LLM Judge 엔진, FastAPI 대시보드, OTEL 모니터링, PDF 처리를 별도 설치 없이 바로 사용할 수 있습니다.

### 기본 설치에 포함된 기능

| 기능 | 패키지 | Harness 관련 |
|---|---|---|
| 25개 네이티브 트래커 (Group A-G) | numpy, pandas, python-dotenv | 전 Group |
| 33개 Harness Config 데이터클래스 | 코어 내장 | 전 Group |
| LLM Judge 엔진 (Group G) | openai, anthropic | Group G |
| FastAPI 대시보드 | fastapi, uvicorn, jinja2, python-multipart | 운영 |
| OTEL 모니터링 (Group G) | opentelemetry-sdk, arize-phoenix | Group G |
| PDF 처리 | pdfplumber | Group A |

### 별도 설치가 필요한 extras

| extras | 포함 패키지 | 사용 시기 |
|---|---|---|
| `[eval]` | deepeval, ragas, datasets | 외부 평가 도구 연동 (HybridPerformanceMonitor) |
| `[langchain]` | langchain, langchain-core, langgraph | LangChain/LangGraph 프레임워크 사용 시 |
| `[dspy]` | dspy-ai | DSPy 프로그램 평가 |
| `[pydanticai]` | pydantic-ai | PydanticAI Agent 평가 |
| `[crewai]` | crewai | CrewAI (전이 의존성 100개+, 단독 설치 권장) |
| `[autogen]` | pyautogen, autogen-agentchat | AutoGen (무거움, 단독 설치 권장) |
| `[examples]` | 기본 + eval 묶음 | 모든 예제 실행 |
| `[full]` | 위 전체 | 모든 기능 (설치 10분+ 소요) |

```bash
# 기본 설치 — 33개 Harness Config + LLMJudge + 대시보드 + OTEL 포함 (권장)
pip install agent-evaluator

# LangChain 프레임워크 통합
pip install "agent-evaluator[langchain]"

# DeepEval/Ragas 외부 평가 도구 연동
pip install "agent-evaluator[eval]"

# 모든 예제 실행
pip install "agent-evaluator[examples]"

# 전체 설치 (⚠️ crewai/autogen 포함, 10분+)
pip install "agent-evaluator[full]"

# 설치 확인
agent-eval --version
# → agent-evaluator 0.8.3
```

> 👨‍💻 **개발자 TIP**: `[crewai]`와 `[autogen]`은 의존성이 무거워 단독 extras로 분리되어 있습니다. CrewAI와 AutoGen을 동시에 설치하면 pydantic 버전 충돌이 발생할 수 있으므로, 필요한 경우에만 하나씩 설치하세요.

---

## 2.2 환경 변수 설정 (.env 파일 패턴)

Agent-Evaluator는 소스 코드에 API 키를 하드코딩하지 않는 것을 원칙으로 합니다. 프로젝트 루트에 `.env` 파일을 만들어 관리하는 것을 권장합니다.

```bash
# .env (프로젝트 루트에 생성)

# LLM API 키 (Group G — LLM Judge 사용 시 필요)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 결과 저장 경로 (생략 시 자동 감지)
# AGENT_EVALUATOR_OUTPUT_DIR=/path/to/results
# AGENT_EVALUATOR_ROOT=/path/to/project
```

`.env` 파일을 로드하는 방법은 두 가지입니다.

```python
# 방법 1: SDK가 자동 로드 (권장)
from agent_evaluator import load_env
load_env()  # 프로젝트 루트의 .env 자동 탐지 후 로드

# 방법 2: python-dotenv 직접 사용
from dotenv import load_dotenv
load_dotenv()
```

**저장 경로 자동 감지**: `output_dir`를 별도로 지정하지 않으면 SDK가 다음 순서로 경로를 자동 결정합니다.

1. 환경 변수 `AGENT_EVALUATOR_OUTPUT_DIR` (최우선)
2. 환경 변수 `AGENT_EVALUATOR_ROOT` 아래 `results/`
3. Git 저장소 루트 아래 `results/`
4. 현재 작업 디렉토리 아래 `results/` (폴백)

Git 저장소에서 작업한다면 별도 설정 없이도 항상 올바른 위치에 저장됩니다.

> 📋 **QA 관리자 TIP**: `.env` 파일은 `.gitignore`에 반드시 추가하세요. API 키가 저장소에 노출되면 심각한 보안 문제가 발생할 수 있습니다. `.env.example` 파일을 만들어 팀원이 필요한 변수 목록을 알 수 있도록 공유하는 것을 권장합니다.

> 📖 **더 깊이 알고 싶다면**: 지원되는 환경변수 전체 목록과 각 변수의 동작 방식은 **[Appendix C — 환경변수 & 설정 레퍼런스](../Appendix/C_환경변수_설정_레퍼런스.md)**를 참조하세요.

---

## 2.3 5분 안에 첫 Harness 배포 판정 경험

가장 짧은 코드로 Harness Engineering의 핵심인 **배포 판단**을 경험해봅니다. Tracker가 지표를 측정하고, Config가 기준을 선언하고, Gate가 통과/실패를 판정합니다.

### 단계 1 — QuickEval로 측정 시작 (1줄)

```python
# quick_start.py
from agent_evaluator import QuickEval

# QuickEval은 PerformanceMonitor + EvalDecorator를 하나로 감싼 Facade
eval = QuickEval("results/")
```

### 단계 2 — 에이전트 함수에 데코레이터 적용 (2줄)

```python
@eval.qa  # Group A 목표달성: AccuracyEvaluator + TCR 자동 측정
def my_agent(question: str, ground_truth: str = "") -> str:
    answers = {
        "한국의 수도는?": "서울입니다.",
        "파이썬 창시자는?": "귀도 반 로섬입니다.",
    }
    return answers.get(question, "모르겠습니다.")
```

### 단계 3 — 평가 실행 (n줄)

```python
my_agent("한국의 수도는?", ground_truth="서울")
my_agent("파이썬 창시자는?", ground_truth="귀도 반 로섬")
my_agent("우주의 나이는?", ground_truth="138억 년")
```

### 단계 4 — 첫 배포 판정 (Gate)

```python
# Harness Gate — 배포 기준 선언 및 판정
eval.gate(tcr=80, accuracy=70)  # TCR < 80% 또는 Accuracy < 70% 이면 sys.exit(1)

# 결과 저장
eval.save()
print(eval.summary())
```

실행 출력:

```
{
  "task_completion_rate": 0.667,
  "accuracy": 0.823,
  "p95_latency": 0.003,
  "total_cost_usd": 0.0,
  "quality_avg": 0.756
}
```

TCR 66.7%이 게이팅 기준 80% 미달이므로 `gate()`는 `sys.exit(1)`을 호출합니다. 이것이 Harness Engineering의 배포 판단입니다. **코드를 고쳐서 TCR이 80%를 넘길 때까지 배포는 차단됩니다.**

### Harness Config로 기준을 더 세밀하게

`gate()`는 간단한 단일 임계값 판정입니다. 더 복잡한 배포 기준은 **Harness Config** 데이터클래스로 선언합니다.

```python
# 출처: Evaluator_Examples/08_harness_eval.py, 섹션 1·4 — Group A·D Config 선언 및 통합
from agent_evaluator import (
    PerformanceMonitor, HarnessEvaluationGate,
    InstructionConfig,    # Group A — 지시 준수
    SLAConfig,           # Group D — 레이턴시·비용 계약
    ThreatSeverityConfig, # Group E — 보안 위협 수준
)
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

# Config 선언 — 배포 기준을 소스 코드로 명세
instruction_cfg = InstructionConfig(
    required_keywords=["결론"],  # 응답에 "결론" 키워드 포함 필수
    max_words=500,               # 최대 500단어
    fail_on_violation=True,      # 위반 시 해당 태스크 success=False
)
sla_cfg = SLAConfig(
    p95_ms=3000,                 # p95 응답 시간 3초 이하 필요
    max_cost_per_task=0.01,      # 태스크당 비용 $0.01 이하
)

# Tracker + Config 통합 — @agent_eval이 실행마다 Config 검증
@agent_eval(
    monitor,
    task_type="qa",
    instructions=instruction_cfg,
    sla=sla_cfg,
)
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# Gate — 전체 평가 종합 배포 판정 (기준 미달 시 sys.exit(1))
report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
gate.enforce()
```

### 배포 판정 결과 이해하기

```python
report = monitor.generate_report()
d = report.to_dict()

# 7개 Group별 상태 확인
am = d.get("accuracy_metrics", {})
em = d.get("efficiency_metrics", {})
tcr = am.get("tcr", {}).get("tcr", 0.0)
p95 = em.get("latency", {}).get("p95", 0.0)
print(f"Group A (목표달성): TCR={tcr:.1%}")
print(f"Group D (성능계약): p95={p95:.2f}s")

# Harness 그룹별 점수 확인
harness_groups = d.get("extra_metrics", {}).get("harness_groups", {})
for group_key in ["A", "B", "C", "D", "E", "F", "G"]:
    group_data = harness_groups.get(group_key, {})
    if isinstance(group_data, dict) and group_data.get("score") is not None:
        print(f"  Gate {group_key}: score={group_data['score']:.3f} ({group_data.get('status', 'n/a')})")
```

평가 결과 파일이 `results/quickeval.json`과 `results/quickeval.html`로 저장됩니다. HTML 파일을 브라우저에서 열면 Group A-G별 시각화된 리포트를 확인할 수 있습니다.

> 📋 **QA 관리자 TIP**: `gate(tcr=80)` 단일 임계값으로 시작하고, 팀이 익숙해지면 `InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig`로 세분화하세요. Part IV — Chapter 14에서 팀 수준 임계값 설정 전략을 다룹니다.

---

## 2.4 Harness 아키텍처 3분 개요

Agent-Evaluator의 58개 지표는 세 층(Layer)과 세 역할(Tracker·Config·Gate)로 구성됩니다. 이 구조를 이해하면 어느 시점에 어떤 도구를 써야 하는지 판단할 수 있습니다.

### Harness Engineering 3요소

```
┌────────────────────────────────────────────────────────────────────┐
│  Gate — HarnessEvaluationGate                                       │
│  Group A-G 전체 Config를 종합해 배포 통과/실패 판정                    │
│  → HarnessEvaluationGate(report).enforce() / QuickEval.gate() / agent-eval gate CLI │
├────────────────────────────────────────────────────────────────────┤
│  Config — 33개 Harness Config 데이터클래스                            │
│  배포 기준을 소스 코드로 선언 (fail_on_violation=True 시 강제 차단)      │
│  Group A: InstructionConfig, GoalAlignmentConfig, ...              │
│  Group B: LoopDetectionConfig, ScopeConfig, StateConsistencyConfig, DeadlockConfig, ...│
│  Group C: ReproducibilityConfig, FaultToleranceConfig, ...         │
│  Group D: SLAConfig, EfficiencyConfig, ResourceBudgetConfig, ...   │
│  Group E: ThreatSeverityConfig, ComplianceConfig, ...              │
│  Group F: ConsensusConfig, PropagationConfig, ...                  │
│  Group G: ObservabilityConfig, ExplainabilityConfig, ...           │
├────────────────────────────────────────────────────────────────────┤
│  Tracker — 25개 네이티브 트래커 (+ LLMJudge + AnomalyDetector)        │
│  에이전트 실행 중 자동으로 지표를 기록                                    │
│  ─ 항상 자동 활성 ─────────────────────────────────────────────────  │
│  TaskCompletionTracker   → TCR (Group A)                           │
│  AccuracyEvaluator       → 4중 가중 정확도 (Group A)                │
│  LatencyTracker          → p50/p95/p99 (Group D)                   │
│  TokenEconomyTracker     → 비용 추정 (Group D)                      │
│  ToolCallAnalyzer        → 도구 패턴 (Group B)                      │
│  WorkflowExecutionTracker → 워크플로우 (Group B)                    │
│  AgentCoordinationTracker → 협업 품질 (Group F)                    │
│  ToolSelectionTracker    → F1 정확도 (Group F)                      │
│  RetryCorrectionTracker  → 재시도 패턴 (Group C)                    │
│  ─ opt-in ─────────────────────────────────────────────────────── │
│  HallucinationDetector   → 환각 탐지 (Group C, hallucination=True) │
│  ResponseQualityEvaluator → 5차원 품질 (Group A)                   │
│  InputSanitizationTracker → 인젝션 탐지 (Group E, security=True)   │
│  OutputLeakageDetector   → 유출 탐지 (Group E)                      │
│  ToolAuthorizationTracker → 권한 감시 (Group E)                    │
│  PrivilegeEscalationDetector → 권한 상승 (Group E)                  │
│  ToolChainAttackDetector → 체인 공격 (Group E)                      │
│  LLMJudge                → 7차원 채점 (Group G, sample_rate=0.1)   │
└────────────────────────────────────────────────────────────────────┘
```

### 세 역할의 실행 타이밍

```
에이전트 실행 → Tracker 자동 기록
                │
                ▼
         TaskResult 생성
                │
                ▼
         Config 검증 ← fail_on_violation=True → success=False
                │
                ▼
         monitor.record_task(result) → EvaluationReport 누적
                │
                ▼ (N건 후 또는 명시적 호출)
         Gate 판정 → pass / fail → 배포 결정
```

### 핵심 클래스 3종

```python
from agent_evaluator import PerformanceMonitor, TaskResult, create_taskresult

# ① PerformanceMonitor — 중앙 오케스트레이터
#    모든 Tracker를 내부에서 구성, Config 검증, Gate 판정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # Group C opt-in (성능 영향)
    enable_security_metrics=False,         # Group E opt-in (성능 영향)
    enable_llm_judge=False,                # Group G opt-in (LLM 비용)
)

# ② TaskResult — 단일 태스크 결과 (frozen dataclass)
#    Tracker가 기록한 모든 지표를 담는 컨테이너
result = create_taskresult(
    task_id="t001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.85,
    task_type="qa",
)
# → accuracy_score, completion_score 자동 계산 포함

# ③ EvaluationReport — generate_report()가 반환하는 불변 보고서
report = monitor.generate_report()
# → task_completion_rate, average_accuracy, latency_p95 등 집계값
```

### Group A-G 활성화 방법

| Group | 기본 활성 | 활성화 방법 |
|-------|----------|-----------|
| A 목표달성 | ✅ 자동 | 항상 활성 |
| B 행동무결성 | ✅ 자동 | tool_calls 데이터 있으면 자동 |
| C 신뢰성 | ⚠️ 부분 | `enable_hallucination_detection=True` |
| D 성능계약 | ✅ 자동 | 항상 활성 |
| E 보안경계 | ❌ opt-in | `enable_security_metrics=True` 또는 `PerformanceMonitor.for_secure_agents()` |
| F 다중에이전트 | ✅ 자동 | agent_interactions 데이터 있으면 자동 |
| G 운영관측성 | ⚠️ 부분 | `enable_llm_judge=True` + API 키 (샘플링 10%) |

```python
# 모든 Group 활성화 — 최대 측정 모드
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # Group C 전체
    enable_security_metrics=True,         # Group E 전체
    enable_llm_judge=True,                # Group G LLMJudge
    judge_sample_rate=0.1,                # 비용 절감: 10%만 채점
)

# 또는 팩토리 메서드 — 용도별 최적 설정 자동 적용
monitor_rag = PerformanceMonitor.for_rag_evaluation("results/")  # Group C 강화
monitor_sec = PerformanceMonitor.for_secure_agents("results/")   # Group E 강화
```

> 📖 **더 깊이**: Group별 Tracker 파라미터와 Config 전체 레퍼런스는 → **Part II — Chapter 03~10** (Group A-G 챕터)에서 상세히 다룹니다.

---

## 2.5 개발자와 QA 관리자가 보는 것 — 역할별 데이터 흐름

같은 평가 시스템을 두 역할이 서로 다른 지점에서 만납니다. 이 흐름을 한눈에 이해하면 나머지 챕터를 각자의 관점에서 효율적으로 읽을 수 있습니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  Harness Engineering 데이터 흐름                          │
│                                                                          │
│  👨‍💻 개발자가 작성하는 것          ──────→  🗂️ SDK가 만드는 것              │
│                                                                          │
│  @agent_eval(monitor,                   Tracker 자동 측정                 │
│    sla=SLAConfig(p95_ms=2000),    →     · execution_time                │
│    scope=ScopeConfig(...),              · tool_calls                    │
│    threat_severity=ThreatSev...         · tokens_used                   │
│  )                                      · accuracy_score                 │
│  def my_agent(...): ...                 · (security events)              │
│                                              ↓                           │
│                                    TaskResult (한 건)                    │
│                                              ↓                           │
│                                    Config 위반 여부 검증                  │
│                                    fail_on_violation → success=False     │
│                                              ↓                           │
│                                    results/eval.json 누적               │
│                                              ↓                           │
│  ─────────────────────────────────  Gate 판정  ──────────────────────── │
│                                              ↓                           │
│  📊 QA 관리자가 보는 것                                                    │
│                                                                          │
│  대시보드 (agent-eval dashboard)          HTML 리포트                     │
│  · Gate A–G 통과/경고/실패               · 태스크별 Group 점수             │
│  · 지표 추세 (trend)                     · Config 위반 목록               │
│  · 이상 탐지 알림                         · 배포 권고 여부                  │
│                                                                          │
│  CI/CD (agent-eval gate CLI)                                             │
│  · pass → 배포 진행                                                       │
│  · fail → 배포 차단 + 원인 Group 표시                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 개발자가 결정하는 것 → QA 관리자에게 미치는 영향

| 개발자 선언 | Tracker가 측정 | QA 관리자가 보는 판정 |
|-----------|--------------|-------------------|
| `SLAConfig(p95_ms=2000)` | LatencyTracker → p95 집계 | Gate D 성능계약: PASS / WARN |
| `ScopeConfig(allowed_tools=["search"])` | ToolCallAnalyzer → 범위 이탈 감지 | Gate B 행동무결성: PASS / FAIL |
| `enable_security_metrics=True` | InputSanitizationTracker → 위협 탐지 | Gate E 보안경계: 위협 건수 표시 |
| `enable_llm_judge=True` | LLMJudge → 7차원 채점 | Gate G 운영관측성: 설명가능성 점수 |
| `fail_on_violation=True` (어떤 Config든) | TaskResult.success=False 처리 | TCR 하락 → Gate A 영향 |

> **개발자 읽기 경로**: Part II(지표 이해) → Part III(데코레이터·Config 구현) → Part V(CI/CD 연동)  
> **QA 관리자 읽기 경로**: Part II(지표 이해) → Part IV(임계값 설정·대시보드) → Part V(Gate 운영)

---

## 2.6 세 가지 결과 출력 시나리오

Agent-Evaluator는 평가 결과를 세 가지 방식으로 출력할 수 있습니다.

### 시나리오 ① 터미널 출력 — 빠른 확인

개발 중 빠르게 결과를 확인할 때 사용합니다.

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(output_dir="results/")

result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",
)
monitor.record_task(result)

report = monitor.generate_report()
import json
print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
```

출력 예시:

```json
{
  "summary": {
    "total_tasks": 1,
    "task_completion_rate": 1.0,
    "accuracy": 0.923,
    "response_quality": 0.812,
    "latency_p95": 0.8,
    "tokens_used_total": 0
  }
}
```

### 시나리오 ② 대시보드 — 시각화 UI

팀 내 공유나 지속적인 품질 모니터링에 적합합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

test_cases = [
    ("한국의 수도는?", "서울"),
    ("파이썬 창시자는?", "귀도 반 로섬"),
]
for question, answer in test_cases:
    my_agent(question, ground_truth=answer)

# JSON + HTML 파일 저장
monitor.save_to_file("evaluation")
```

```bash
# 대시보드 실행 (기본 설치에 포함)
agent-eval dashboard results/ --watch
# → http://localhost:8765 에서 확인
# Group A-G별 탭으로 구성
```

### 시나리오 ③ OTEL Phoenix — 실시간 운영 모니터링 (Group G)

프로덕션 환경에서 에이전트 실행을 실시간으로 추적합니다.

**터미널 1 — Phoenix 서버 기동:**

```bash
# Phoenix 서버 시작 (UI: http://localhost:6006)
agent-eval monitor

# 설치 상태 확인
agent-eval monitor --check
```

**터미널 2 — 에이전트 코드:**

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# setup_otel()은 PerformanceMonitor 생성 전에 반드시 호출
setup_otel(
    endpoint="http://localhost:6006",  # 경로("/v1/traces") 붙이지 말 것
    service_name="my-qa-agent"
)

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("한국의 수도는?", ground_truth="서울")
# → Phoenix Tracing 탭에서 ae.tcr, ae.accuracy, ae.execution_time 실시간 확인
```

---

## 2.6 언제 어느 출력을 쓰는가 — 상황별 결정표

| 상황 | 권장 방법 | Harness 연관 |
|---|---|---|
| 개발 중 빠른 검증 | 터미널 출력 (`generate_report()`) | Group A 기본 확인 |
| 팀 리뷰 또는 결과 공유 | 대시보드 (`save_to_file` + `agent-eval dashboard`) | Group A-G 전체 시각화 |
| CI/CD 파이프라인 게이팅 | CLI (`agent-eval gate`) | HarnessEvaluationGate |
| 프로덕션 실시간 모니터링 | OTEL Phoenix (`setup_otel` + `agent-eval monitor`) | Group G 운영관측성 |
| 배치 오프라인 평가 | `evaluation_session` 컨텍스트 매니저 | 전체 Group 누적 |
| 에이전트 A/B 비교 | `QuickEval.compare(other)` | Group A-D 비교 |
| 드리프트 감지 | `agent-eval trend` | Group A/D 추세 |

### CI/CD Harness Gate 예시

```bash
# GitHub Actions 또는 Jenkins에서
python run_evaluation.py        # 평가 실행 → results/eval.json 생성

# Harness Gate — Group A(TCR), Group D(레이턴시) 기준으로 판정
agent-eval gate results/evaluation_evaluation.json \
    --tcr 85 --accuracy 70 --p95-latency 3.0
# 기준 미달 시 exit 1 → 파이프라인 중단 → 배포 차단
```

### 드리프트 추세 감지 (Group A/D 지속 평가)

```bash
# 최근 10개 평가 결과의 TCR·정확도 추세 분석
agent-eval trend results/ --fail-on-regression

# 결과 예시:
# TCR slope: -0.025/run → ⚠️ 지속적 하락 감지
# P95 slope: +0.12s/run → ⚠️ 레이턴시 증가 추세
# → exit 1 (CI/CD 파이프라인 중단)
```

### QuickEval로 A/B 비교

```python
from agent_evaluator import QuickEval

# 버전 A 평가
eval_a = QuickEval("results/version_a/")

@eval_a.qa
def agent_v1(question: str, ground_truth: str = "") -> str:
    return model_v1.invoke(question)

for q, gt in test_dataset:
    agent_v1(q, ground_truth=gt)
eval_a.save("v1")

# 버전 B 평가
eval_b = QuickEval("results/version_b/")

@eval_b.qa
def agent_v2(question: str, ground_truth: str = "") -> str:
    return model_v2.invoke(question)

for q, gt in test_dataset:
    agent_v2(q, ground_truth=gt)
eval_b.save("v2")

# 비교 — Group A/D 지표 차이 확인
comparison = eval_a.compare(eval_b)
print(comparison)
```

---

> **이 챕터의 핵심**
>
> - v0.7.8부터 기본 설치(`pip install agent-evaluator`)에 33개 Harness Config · LLM Judge · 대시보드 · OTEL 모니터링이 포함됩니다. 프레임워크별 통합이 필요하면 `[langchain]`, DeepEval/Ragas가 필요하면 `[eval]`을 추가하세요.
> - **Harness Engineering 3요소**: Tracker(25개 지표 자동 기록) × Config(33개 배포 기준 선언) × Gate(종합 판정)
> - `QuickEval.gate(tcr=80)` 한 줄로 첫 배포 판정을 경험할 수 있습니다. 기준 미달 시 `sys.exit(1)` → CI/CD 배포 차단.
> - Group E 보안 지표는 `enable_security_metrics=True`로, Group G LLMJudge는 `enable_llm_judge=True` + API 키로 각각 활성화합니다.
> - `setup_otel()`은 반드시 `PerformanceMonitor` 생성 전에 호출하고, endpoint에 경로를 붙이지 마세요: `"http://localhost:6006"`.

---

## 실전 예제

챕터 2에서 설명한 Harness 아키텍처와 첫 시작 과정을 `04_decorator_quickeval.py`로 바로 체험할 수 있습니다.

**파일**: `Evaluator_Examples/04_decorator_quickeval.py`

**핵심 코드 (출처: `Evaluator_Examples/04_decorator_quickeval.py`)**

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 1 — @agent_eval 기본 사용
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return "에이전트 응답 텍스트"

# 호출하면 Group A (AccuracyEvaluator, TCR) + Group D (LatencyTracker) 자동 집계
my_agent("한국의 수도는?", ground_truth="서울")

# 보고서 저장 (JSON + HTML 동시 생성)
monitor.save_to_file("my_first_eval")
```

```python
# 출처: Evaluator_Examples/04_decorator_quickeval.py, 섹션 8 — QuickEval + Harness Gate
from agent_evaluator import QuickEval

eval_qe = QuickEval("results/")

@eval_qe.qa   # Group A 목표달성
def qa_agent(question: str, ground_truth: str = "") -> str:
    return "QA 에이전트 응답"

@eval_qe.rag  # Group A + Group C (hallucination_detection=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return "RAG 에이전트 응답"

qa_agent("수도는?", ground_truth="서울")
qa_agent("인구는?", ground_truth="5천만")

# Harness Gate — TCR 80% 미달 시 sys.exit(1) → 배포 차단
eval_qe.gate(tcr=80, accuracy=70)

eval_qe.save()  # JSON + HTML
```

**Harness 아키텍처 4단계와 예제 매핑**

| 단계 | 역할 | 코드 | 예제 파일·섹션 |
|------|------|------|---------------|
| 1. Tracker | 지표 수집 | `@eval.qa` / `@agent_eval(monitor)` | 04_decorator_quickeval, 섹션 1 |
| 2. Config | 기준 선언 | `InstructionConfig(required_keywords=["결론"], fail_on_violation=True)` | 04_decorator_quickeval, 섹션 4 |
| 3. Gate | 배포 판정 | `eval.gate(tcr=80)` | 04_decorator_quickeval, 섹션 7 |
| 4. 저장 | 결과 보존 | `eval.save()` / `monitor.save_to_file()` | 04_decorator_quickeval, 섹션 8 |

**실행 결과 (v0.8.3 기준)**

```
=== 04. 데코레이터 · QuickEval 종합 예제 ===
QuickEval("results/"): 초기화 완료

섹션 1: @eval.qa 기본
  14개 태스크 | TCR=57.1% | avg_accuracy=0.712

섹션 7: eval.gate(tcr=80, accuracy=70)
  ❌ Harness Gate 실패 — TCR 57.1% < 80.0%  ← 배포 차단
  (--tcr 50으로 완화 시 ✅ 통과)

결과 저장: results/quickeval.json + results/quickeval.html
```

> **2줄 시작 코드**: `eval = QuickEval("results/")` 한 줄로 Tracker + Config + Gate가 모두 설정됩니다. API 키 없이도 Group A-F의 지표를 측정하며, `ANTHROPIC_API_KEY` 설정 시 Group G LLMJudge가 자동 활성화됩니다.
