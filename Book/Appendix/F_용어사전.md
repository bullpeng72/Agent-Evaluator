# Appendix F. 용어 사전

Agent Evaluator v0.8.2에서 사용하는 주요 용어를 영문 기준 가나다 순으로 정리한다.

---

## AI Native 5속성 정의

Agent-Evaluator가 기존 소프트웨어 테스팅과 다른 이유를 설명하는 5가지 AI 에이전트 고유 속성.

| # | 속성 | 정의 | 연관 Group |
|---|------|------|-----------|
| 1 | **비결정론적 출력** (Non-deterministic Output) | 동일 입력에도 매번 다른 응답을 생성하는 특성. 단일 테스트로 품질을 확정할 수 없으며 통계적 측정이 필수다. | Group A, C |
| 2 | **컨텍스트 의존성** (Context Dependency) | 이전 대화 내용·도구 결과·프롬프트 구조가 응답에 깊이 영향. 격리된 단위 테스트로는 실 품질 측정 불가. | Group A, B |
| 3 | **다단계 추론** (Multi-step Reasoning) | 단일 응답이 아닌 계획 수립 → 도구 호출 → 결과 통합의 연쇄로 구성. 중간 단계의 오류가 최종 결과를 크게 훼손. | Group B, G |
| 4 | **도구 활용** (Tool Utilization) | 외부 API, 파일 시스템, 데이터베이스 등을 자율적으로 호출. 도구 선택 오류·과잉 호출·인가 위반이 새로운 실패 모드를 만든다. | Group B, E |
| 5 | **자율적 목표 추구** (Autonomous Goal Pursuit) | 명시적 지시 없이 목표 달성을 위해 스스로 행동을 선택. 설계 범위를 벗어난 행동이 예기치 않게 발생할 수 있다. | Group B, F |

참조: Appendix G §G.6 (AI Native 평가 전략 5가지) / Chapter 1 (AI 에이전트 평가란 무엇인가)

---

## Harness Engineering 핵심 용어

---

### Config-as-Code

에이전트의 배포 기준을 소스 코드로 선언하는 패턴. "문서나 관행"이 아닌 "실행 가능한 코드"로 품질 기준을 명시한다. Harness Config 클래스들이 이 패턴의 구현체다.

```python
# Config-as-Code 예시
from agent_evaluator.decorators import SLAConfig, ThreatSeverityConfig

@agent_eval(monitor,
            sla=SLAConfig(p95_ms=2000, fail_on_violation=True),
            threat=ThreatSeverityConfig(max_critical=0))
def agent(question, ground_truth=""): ...
```

참조: Part II 전체 / Appendix A §Part 2 (33개 Config 레퍼런스)

---

### fail_on_violation

Harness Config의 공통 플래그. `True`로 설정하면 해당 Config 조건 위반 시 `TaskResult.success = False`로 강제 처리된다. CI/CD 파이프라인에서 배포를 자동 차단하는 핵심 메커니즘이다.

참조: Appendix A §Part 2 / Chapter 13 (CI/CD 품질 게이팅)

---

### Group A-G (Harness 7차원)

58개 지표를 7개 품질 차원으로 분류하는 Harness Engineering의 핵심 구조.

| Group | 차원 | 핵심 질문 |
|-------|------|-----------|
| A | 목표달성 | 에이전트가 지시를 완수했는가? |
| B | 행동무결성 | 의도치 않은 행동이 없었는가? |
| C | 신뢰성 | 일관되고 재현 가능한가? |
| D | 성능계약 | SLA/비용 계약을 지켰는가? |
| E | 보안경계 | 공격·유출을 차단했는가? |
| F | 다중에이전트 협업 | 교착 없이 협력했는가? |
| G | 운영관측성 | 실패 원인을 즉시 추적할 수 있는가? |

참조: Chapter 3 (Harness Engineering 기초) / Part II 전체

---

### Harness Config

에이전트의 배포 기준을 선언하는 데이터클래스 계열. 33개 클래스가 Group A-G에 분산되어 있다. `@agent_eval` 데코레이터나 `PerformanceMonitor`에 주입해 사용한다.

```python
from agent_evaluator.decorators import SLAConfig, ThreatSeverityConfig, ReproducibilityConfig
```

전체 목록과 사용법: Appendix A §Part 2 (33개 Config 완전 레퍼런스)

**사용법**: `@agent_eval` 데코레이터 파라미터 또는 `PerformanceMonitor` + `HarnessEvaluationGate`로 주입한다.

```python
# 방법 1: 데코레이터 파라미터
@agent_eval(monitor,
            sla=SLAConfig(p95_ms=2000, fail_on_violation=True),
            instruction=InstructionConfig(required_keywords=["서울"]))
def agent(question, ground_truth=""): ...

# 방법 2: HarnessEvaluationGate 일괄 적용
from agent_evaluator import HarnessEvaluationGate
gate = HarnessEvaluationGate(report)
result = gate.evaluate()  # {"passed": True, "violations": [...]}
```

---

### Harness Engineering

AI 에이전트를 프로덕션에 안전하게 배포하기 위한 품질 공학 방법론. Tracker(관찰/측정) × Config(기준 선언) × Gate(배포 판정) 3요소로 구성된다. 기존 소프트웨어 테스팅의 "버그 없음 확인"을 넘어 "배포 가능 여부 판정"까지 자동화한다.

참조: Chapter 1, Chapter 3

---

### HarnessEvaluationGate

Group A-G 전체를 한 번에 체크하는 종합 배포 판정 도구. 각 Group의 Config 위반 여부를 집계해 최종 pass/fail을 반환한다. `agent-eval gate` CLI의 내부 구현체이기도 하다.

```python
from agent_evaluator import HarnessEvaluationGate
gate = HarnessEvaluationGate(report)
result = gate.evaluate()  # {"passed": True, "violations": [...]}
```

참조: Chapter 18 (CI/CD Harness Gate)

---

### 확률론적 품질 (Probabilistic Quality)

AI 에이전트 품질을 단일 점수가 아닌 **분포**로 이해하는 패러다임. 같은 `accuracy=0.85`라도 분산이 작으면 안정적, 크면 예측 불가능한 에이전트다. Wilson Score Interval 등 통계적 신뢰구간 기반 임계값 설정이 이 패러다임의 구현이다.

참조: Chapter 14 (임계값 설정) / Appendix G (AI Native 이론)

---

### 드리프트 (Drift)

에이전트 성능이 배포 후 시간이 지남에 따라 저하되는 현상. 코드 변경·모델 업데이트·프롬프트 수정·학습 데이터 변화 4가지 소스에서 발생한다. `agent-eval trend`와 `RunTrendAnalyzer`로 조기 감지한다.

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

Group A 정확도 평가 클래스. `PerformanceMonitor` 내부에서 자동으로 초기화된다. QA 태스크에서는 TokenOverlapF1 (40%) + Jaccard (30%) + LCS (20%) + CharSimilarity/Levenshtein (10%) 가중 조합으로 정확도를 계산하고, 코드 태스크에서는 AST 비교를 사용한다. `ground_truth`가 필수이며 빈 문자열이면 0.0이 반환된다.

참조: Appendix A — Group A 지표 / 3장

---

### AdaptivePolicy

비용 최적화를 위한 적응형 샘플링 정책 클래스. 태스크 복잡도와 비용에 따라 평가 샘플링 비율을 동적으로 조정한다. `SamplingStage`와 함께 사용한다.

```python
from agent_evaluator import AdaptivePolicy, SamplingStage
```

참조: 5장 (비용 관리)

---

### agent_eval (데코레이터)

단일 함수를 평가 대상으로 등록하는 핵심 데코레이터. `PerformanceMonitor`에 `TaskResult`를 자동으로 기록한다. `framework=`, `rag_mode=`, `security=SecurityConfig()`, `flush_every=`, `alert_rules=` 등 다양한 파라미터를 지원한다.

```python
from agent_evaluator.decorators import agent_eval
```

참조: Appendix B / 6장 (데코레이터 패턴)

---

### AlertRuleBuilder

`SimpleTaskAlertRule` 생성을 간소화하는 팩토리 클래스. `when_accuracy_below()`, `when_latency_above()`, `when_completion_below()`, `when_error()`, `when_tool_calls_exceed()` 5개 정적 메서드를 제공한다.

참조: 8장 (알림 시스템)

---

### AnomalyDetector

이상 탐지 클래스. 통계적 방법(Z-score, IQR)으로 지표 이상치를 자동 감지하고 `AnomalyEvent`를 발생시킨다. `explain_event()` / `scan_with_explain()`으로 원인 설명과 권고사항을 제공한다.

```python
from agent_evaluator import AnomalyDetector, AnomalyEvent
```

참조: 9장 (이상 감지)

---

### batch_eval (데코레이터)

리스트 입력을 받아 일괄 처리하는 평가 데코레이터. `concurrent=True`로 병렬 처리, `return_format="dataframe"`으로 pandas DataFrame 반환이 가능하다. 함수의 첫 번째 인자는 반드시 리스트여야 한다.

```python
from agent_evaluator.decorators import batch_eval
```

참조: 6장 / Appendix E (오류 #10)

---

### conversation_eval (데코레이터)

멀티턴 대화 평가 데코레이터. `session_id_arg` 파라미터로 세션을 구분하고, 각 턴의 문맥 유지율 / 주제 일관성 / 점진적 깊이를 자동으로 측정한다. 비동기 제너레이터도 지원한다.

```python
from agent_evaluator.decorators import conversation_eval
```

참조: 7장 (멀티턴 대화 평가) / Appendix E (FAQ Q7)

---

### ConversationSession

멀티턴 대화 평가의 핵심 클래스. `add_turn()`으로 사용자/에이전트 발화를 기록하고 `compute_metrics()`로 `ConversationMetrics`를 계산한다. `context_retention`, `topic_coherence`, `progressive_depth`, `session_completion` 등의 지표를 제공한다.

```python
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn
```

참조: 7장

---

### create_taskresult()

`TaskResult` 생성을 단순화하는 헬퍼 함수. `question`, `response`, `ground_truth`, `execution_time`, `task_type`을 입력하면 `accuracy_score`, `completion_score`, `success`, `timestamp` 등을 자동으로 계산한다.

```python
from agent_evaluator import create_taskresult
```

참조: Appendix A / 4장

---

### DeepEval

Confident AI에서 개발한 오픈소스 LLM 평가 라이브러리. Agent Evaluator Group G에서 G-Eval, Hallucination Score, Toxicity, Bias, Answer Relevancy 5개 지표를 제공한다. `pip install "agent-evaluator[eval]"`로 설치하며 `OPENAI_API_KEY`가 필요하다.

출처: docs.confident-ai.com

참조: Appendix A (Group G) / Appendix D (평가 플랫폼 비교)

---

### EvalDecorator

`QuickEval` 내부에서 사용하는 데코레이터 클래스. 직접 인스턴스화하여 `.qa`, `.rag`, `.tool_use` 등 단축 속성을 통해 다양한 태스크 유형에 적용할 수 있다.

```python
from agent_evaluator.decorators import EvalDecorator
```

참조: 6장

---

### EvaluationReport

`monitor.generate_report()`가 반환하는 불변 보고서 객체. `task_completion_rate`, `overall_accuracy`, `average_latency`, `hallucination_rate`, `security_incidents` 등 주요 지표를 속성으로 제공한다. `to_dict()` / `from_dict()` / `from_json()`으로 직렬화/역직렬화를 지원한다.

```python
from agent_evaluator import EvaluationReport
```

참조: 4장

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

참조: 6장 / Appendix E (오류 #14)

---

### GoldenSetBuilder

우수 평가 케이스를 수집하고 골든 데이터셋을 관리하는 클래스. `merge_to_golden()`, `push_to_phoenix()` 메서드를 제공한다. `agent-eval dataset build` CLI 명령어가 내부적으로 사용한다.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder
```

참조: 10장 (골든 데이터셋 관리) / Appendix B (agent-eval dataset)

---

### HallucinationDetector

Group A 환각 탐지 클래스 (규칙 기반). Unsupported Claim과 Numerical Inconsistency 두 가지 방법으로 탐지한다. 정확도 70~80%, 오버헤드 < 5ms. `enable_hallucination_detection=True`로 opt-in해야 한다. 외부 평가 라이브러리 DeepEval Hallucination Score(LLM 기반, 90~95% 정확도)와 방향이 반대이므로 주의한다.

참조: Appendix A (Group A #6) / Appendix E (오류 #5)

---

### LLM Judge (LLMJudge)

`ground_truth` 없이 LLM을 평가자로 사용하는 클래스. Completeness / Relevance / Factual Consistency / Toxicity / Bias 5차원을 기본 채점하며, RAG 컨텍스트가 있으면 Faithfulness(0~5)를, `judge_criteria` 지정 시 커스텀 차원을 추가한다. v0.7.8부터 기본 설치에 포함되어 있으며 API 키(`OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY`)만 있으면 바로 사용 가능하다.

```python
from agent_evaluator import LLMJudge
```

참조: Appendix C (환경변수) / Appendix E (오류 #13)

---

### OTEL (OpenTelemetry)

분산 시스템 관측가능성을 위한 오픈소스 표준. CNCF(Cloud Native Computing Foundation)가 관리하며 벤더 중립적 SDK와 프로토콜을 제공한다. Agent Evaluator에서는 `setup_otel()` 호출 후 `record_task()` 실행 시 OTLP 스팬을 자동으로 발행한다. v0.7.8부터 기본 설치에 포함되어 있어 별도 설치 불필요.

출처: opentelemetry.io

참조: Appendix B (agent-eval monitor) / Appendix C / 11장 (Phoenix 모니터링)

---

### OTLP (OpenTelemetry Protocol)

OpenTelemetry 데이터 전송 프로토콜. HTTP 또는 gRPC 방식으로 스팬(span) 데이터를 Collector(Phoenix 등)로 전송한다. gRPC 기본 포트는 4317, HTTP 기본 포트는 4318이다. Phoenix는 6006 포트에서 OTLP HTTP를 수신한다. Agent Evaluator는 OTLP HTTP 방식(`/v1/traces` 엔드포인트)을 사용한다.

출처: opentelemetry.io/docs/specs/otlp/ · docs.arize.com/phoenix

참조: Appendix E (오류 #1) / 11장

---

### PerformanceMonitor

Agent Evaluator의 중앙 오케스트레이터 클래스. 모든 트래커(Group A-G)를 내부에서 초기화하고 `record_task()`, `generate_report()`, `save_to_file()` 등의 메서드를 제공한다. `for_rag_evaluation()`, `for_secure_agents()` 팩토리 메서드로 용도별 최적 설정을 빠르게 적용할 수 있다.

```python
from agent_evaluator import PerformanceMonitor
```

참조: Appendix A / 4장

---

### Phoenix (Arize Phoenix)

Arize AI에서 개발한 오픈소스 LLM 관측가능성 플랫폼. OpenInference(OTEL 기반 AI 관측가능성 의미 규약) 기반으로 트레이스, 평가 지표, 데이터셋, 프롬프트 4개 탭을 제공한다. `agent-eval monitor`로 로컬에서 기동하며 기본 포트는 6006이다.

출처: docs.arize.com/phoenix

참조: Appendix B / Appendix C / Appendix E (오류 #1) / 11장

---

### QuickEval

`PerformanceMonitor`와 `EvalDecorator`를 1줄로 시작하는 원스톱 Facade 클래스. `for_rag()`, `for_security()`, `for_llm_judge()` 팩토리 메서드와 `.qa`, `.rag`, `.tool_use` 등 단축 데코레이터를 제공한다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
```

참조: 4장 / Appendix E (FAQ)

---

### Ragas

RAG(Retrieval-Augmented Generation) 평가 전문 오픈소스 라이브러리. Agent Evaluator Group G에서 Faithfulness, Answer Relevancy, Context Precision, Context Recall 4개 지표를 제공한다. `pip install "agent-evaluator[eval]"`로 설치하며 `OPENAI_API_KEY`가 필요하다. 버전 0.4.x API(`EvaluationDataset`, `SingleTurnSample`)를 사용한다.

출처: docs.ragas.io

참조: Appendix A (Group G) / Appendix D / Appendix E (오류 #9)

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

참조: 8장 / Appendix E (FAQ)

---

### Span

OTEL에서 단일 작업 단위를 나타내는 추적 데이터 구조. `record_task()` 호출 시 Agent Evaluator가 자동으로 스팬을 생성하여 Phoenix로 전송한다. 스팬에는 `ae.task_type`, `ae.completion_score`, `ae.framework` 등의 속성과 OpenInference 의미 규약 속성(`openinference.span.kind`, `llm.token_count.*`)이 포함된다.

출처: opentelemetry.io/docs/concepts/signals/traces/ · openinference.readthedocs.io

참조: 11장

---

### TCR (Task Completion Rate)

태스크 완료율. Group A의 핵심 지표로 `TaskResult.completion_score` (0.0~1.0)의 평균을 백분율로 표현한다. 95% 이상 우수, 85~95% 양호, 70% 미만 개선 필요.

참조: Appendix A (Group A #1)

---

### TaskResult

단일 태스크 실행 결과를 담는 불변 데이터클래스 (`@dataclass(frozen=True)`). 필수 11개 필드(task_id, task_type, success, completion_score, accuracy_score, execution_time, tokens_used, tool_calls, attempts, errors, timestamp)와 선택 13개 필드로 구성된다. `create_taskresult()` 헬퍼로 생성을 권장한다.

```python
from agent_evaluator import TaskResult
```

참조: Appendix A / 4장 / Appendix E (오류 #15)

---

### TaskType

태스크 유형을 정의하는 Enum. `QA`, `CODE_GENERATION`, `DATA_ANALYSIS`, `DOCUMENT_CREATION`, `INFORMATION_RETRIEVAL`, `REASONING`, `CREATIVE`, `CODING`, `PLANNING`, `TOOL_USE` 10가지를 지원한다. 문자열과 Enum 혼용이 가능하다 (`TaskType.QA` == `"qa"`).

```python
from agent_evaluator import TaskType
```

참조: 4장

---

### TTFT (Time-To-First-Token)

스트리밍 응답에서 첫 번째 토큰이 생성되기까지의 시간. `LatencyTracker.track_ttft()`로 기록하거나 데코레이터 방식에서 제너레이터 함수의 첫 청크 yield 시점에 자동으로 기록된다. v0.7.2+에서 지원.

참조: Appendix A (Group D #4) / 5장 (스트리밍 평가)

---

## 한국어 개념 용어

---

### 골든 데이터셋

높은 점수를 받은 우수 평가 케이스의 모음. 새 모델이나 버전과의 회귀 테스트, 파인튜닝 데이터로 활용한다. `agent-eval dataset build` 명령어 또는 `GoldenSetBuilder` 클래스로 자동 생성·관리한다. 기본 저장 경로는 `data/golden_datasets/`.

참조: Appendix B (agent-eval dataset) / 10장

---

### 에이전틱 지표

에이전트 고유의 행동 패턴을 측정하는 Group B 에이전틱 지표들의 총칭. Tool Call Efficiency, Retry & Error Recovery, Tool Selection Accuracy, Agent Coordination, Workflow Execution 5종을 포함한다. LLM API 없이 알고리즘 기반으로 계산된다.

참조: Appendix A (Group B)

---

### 이상 탐지

정상 범위에서 벗어난 평가 지표를 자동으로 감지하는 기능. `AnomalyDetector` 클래스가 Z-score, IQR 방법으로 이상치를 탐지하고 `AnomalyEvent`를 발생시킨다. `explain_event()`로 원인과 권고사항을 확인한다.

참조: 9장

---

### 임계값

평가 지표의 합격/불합격 기준. `agent-eval gate` 명령어에서 `--tcr`, `--accuracy` 등으로 지정하며, `generate_gate_config()`로 현재 데이터 기반 자동 제안을 받을 수 있다.

참조: Appendix A (각 지표 권장 임계값) / Appendix B (agent-eval gate)

---

### 샘플링

전체 태스크 중 일부만 평가하여 비용과 오버헤드를 줄이는 기법. `@agent_eval(sample_rate=0.1)`로 10%만 평가하거나, `sample_condition`으로 조건부 샘플링이 가능하다. `AdaptivePolicy`로 동적 샘플링도 지원한다.

참조: 6장

---

### 품질 게이팅

CI/CD 파이프라인에서 품질 임계값 미달 시 배포를 자동으로 차단하는 메커니즘. `agent-eval gate` CLI 명령어 또는 `QuickEval.gate()` 메서드로 구현한다. 임계값 미달 시 `sys.exit(1)`로 파이프라인을 차단한다.

참조: Appendix B (agent-eval gate) / Appendix E (오류 #3)

---

### 환각 탐지

AI 에이전트가 컨텍스트에 근거가 없는 내용을 사실처럼 생성하는 현상(환각)을 탐지하는 기능. Agent Evaluator는 두 가지 방식을 제공한다: Group A 규칙 기반(무료, opt-in, 정확도 70~80%)과 외부 평가 라이브러리(DeepEval, 정확도 90~95%, API 비용 발생). 두 방식은 점수 방향이 반대이므로 주의가 필요하다.

참조: Appendix A (Group A #6, Group G DeepEval)

---

### 회귀 테스트

모델 또는 에이전트 업데이트 후 이전 버전 대비 성능 저하 여부를 검증하는 테스트. 골든 데이터셋을 기준으로 `QuickEval.for_regression_eval()` 팩토리 메서드와 `compare()` / `ab_test()` 메서드를 활용한다.

```python
eval = QuickEval.for_regression_eval("results/", baseline_file="baseline.json")
```

참조: 10장 / Appendix E (FAQ Q5)
