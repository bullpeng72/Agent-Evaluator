# M4 — Layer 3, FastAPI 대시보드, 알림 · 이상탐지 · 비용 제어 심층 분석

> **Agent-Evaluator v0.7.5+** 기준 (LLM Judge 확장 기능: v0.7.6+)  
> **대상**: 운영 환경에서 AI 에이전트를 안정적으로 모니터링하려는 ML 엔지니어 / DevOps 엔지니어  
> **전제 조건**: M1(데코레이터), M2(Layer 1), M3(Layer 2) 수강 완료  
> **핵심 메시지**: Layer 1/2만으로 부족할 때, 운영 인프라와 어떻게 통합하는가

---

> **🗂 실습 파일**
>
> | 예제 파일 | 다루는 내용 |
> |---------|---------|
> | `Evaluator_Examples/05_streaming_alerts.py` | StreamingEvaluator 슬라이딩 윈도우 · ImplicitFeedbackTracker · SimpleTaskAlertRule · AlertRuleBuilder · AlertEngine · eval_context |
> | `Evaluator_Examples/06_operational.py` | AnomalyDetector · CostTracker · AdaptivePolicy · GoldenSetBuilder · evaluation_session |
>
> ```bash
> python 05_streaming_alerts.py   # 알림·피드백·대시보드 통합
> python 06_operational.py        # 이상탐지·비용·골든셋·세션
> ```
>
> **실행 결과 (v0.8.0 기준)**
>
> ```
> # 05_streaming_alerts.py
>   [1m 윈도우] count=50  tcr=90.0%  p95=9.52s
>   피드백 통계: total=7  positive=4  negative=3
>   알림 발생: 2건  대시보드 탭: 실시간·알림·피드백·이상감지 ✅
>   총 태스크: 56건  TCR: 30.2%
>
> # 06_operational.py
>   골든 데이터셋: QA 6건 + RAG 4건 + Tool 5건 추출
>   오늘 비용: $0.0305 USD  평가 비용 탭: ✅
>   총 태스크: 28건  TCR: 46.1%
> ```
>
> 결과 파일: `results/05_streaming_alerts.json` · `results/06_operational.json`  
> 대시보드: `agent-eval dashboard results/`

### 핵심 코드 예제

#### StreamingEvaluator 슬라이딩 윈도우

```python
# 출처: Evaluator_Examples/05_streaming_alerts.py, 섹션 1
from agent_evaluator import PerformanceMonitor
from agent_evaluator.streaming.evaluator import StreamingEvaluator

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,
    anomaly_baseline_window=30,   # 앞 30건을 기준선으로
    anomaly_detection_window=10,  # 나머지 10건을 현재 상태로 비교
)
streaming = StreamingEvaluator(monitor=monitor)

# 50건 시뮬레이션 (정상 35건 + 느린 응답 10건 + 오류 5건)
for i, (acc, success, lat, tok) in enumerate(patterns):
    streaming.record(
        task_id=f"stream_{i:04d}",
        success=success,
        execution_time=round(lat, 3),
        tokens_used=tok,
        accuracy_score=acc,
        has_error=not success,
    )

# 슬라이딩 윈도우 통계
for window in ["1m", "5m"]:
    stats = streaming.get_stats(window)
    print(f"[{window}] tcr={stats.get('tcr', 0):.1f}%  p95={stats.get('p95_latency', 0):.2f}s")
```

- `StreamingEvaluator.record()`는 실시간으로 들어오는 태스크를 슬라이딩 윈도우에 집계한다. `monitor.record_task()`와 함께 호출해야 PerformanceMonitor에도 기록된다
- `get_stats("1m")`, `get_stats("5m")`, `get_stats("1h")` 세 윈도우를 지원한다. 윈도우별로 TCR, p95 레이턴시, 오류율, 평균 토큰이 집계된다
- `streaming._flush()`를 save_to_file() 전에 호출해야 대시보드 '실시간' 탭에 데이터가 표시된다

#### SimpleTaskAlertRule + @agent_eval 통합

```python
# 출처: Evaluator_Examples/05_streaming_alerts.py, 섹션 3
from agent_evaluator import SimpleTaskAlertRule
from agent_evaluator.decorators import agent_eval

alert_log = []

low_accuracy_rule = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: tr.accuracy_score < 0.5,
    handler=lambda msg, tr: alert_log.append(f"ACCURACY: {tr.task_id}={tr.accuracy_score:.2f}"),
    severity="warning",
    cooldown=0,   # 모든 위반에 즉시 알림
)

slow_response_rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 5.0,
    handler=lambda msg, tr: alert_log.append(f"SLOW: {tr.task_id}={tr.execution_time:.1f}s"),
    severity="critical",
    cooldown=0,
)

@agent_eval(
    monitor, task_type="qa",
    task_id_prefix="alert_test",
    alert_rules=[low_accuracy_rule, slow_response_rule],  # 복수 규칙 동시 적용
)
def monitored_agent(question: str, ground_truth: str = "") -> str:
    return "모름"  # 낮은 정확도 → low_accuracy_rule 발동

monitored_agent("엉뚱한 질문", ground_truth="전혀 다른 답변")

# dry_run — 핸들러 실행 없이 조건만 검증 (단위 테스트)
from agent_evaluator import create_taskresult
test_result = create_taskresult(
    task_id="dry_test", question="테스트", response="낮은 품질",
    ground_truth="다른 것", execution_time=6.0, task_type="qa", tokens_used=50,
)
triggered = slow_response_rule.dry_run(test_result)
print(f"dry_run(lat=6.0s): triggered={triggered}")  # True
```

- `SimpleTaskAlertRule`은 `StreamingEvaluator` 없이도 `TaskResult` 단위로 즉시 조건을 평가한다. `@agent_eval`, `@batch_eval`, `eval_context` 어디에나 `alert_rules=` 파라미터로 전달할 수 있다
- `dry_run(task_result)`는 핸들러를 실행하지 않고 조건(`condition`) 함수만 평가한다. 알림 규칙을 프로덕션에 배포하기 전에 단위 테스트로 검증하는 데 사용한다
- `cooldown` 초(seconds) 동안 같은 규칙이 중복 발동되지 않는다. `warning=3600`, `critical=300`으로 계층별로 다르게 설정하는 것이 권장된다

#### AnomalyDetector 이상 탐지

```python
# 출처: Evaluator_Examples/06_operational.py, 섹션 1
from agent_evaluator import AnomalyDetector, create_taskresult

detector = AnomalyDetector()

# 정상 기준선 30건 수집
baseline = []
for i in range(30):
    r = create_taskresult(
        task_id=f"base_{i:03d}", question="기준선 태스크",
        response="정상 응답", ground_truth="정상",
        execution_time=round(random.gauss(1.2, 0.3), 3),
        task_type="qa", tokens_used={"input": 100, "output": 40, "total": 140},
    )
    baseline.append(r)

# 이상 케이스 주입 후 스캔
anomaly_result = create_taskresult(
    task_id="anom_spike", question="이상 케이스",
    response="응답", ground_truth="정상",
    execution_time=15.0,  # 정상(1.2s) 대비 12배 — 지연 스파이크
    task_type="qa", tokens_used={"input": 100, "output": 40, "total": 140},
)
events = detector.scan(baseline + [anomaly_result])
print(f"이상 이벤트: {len(events)}건")

# explain_event로 원인 설명
if events:
    explanation = detector.explain_event(events[0])
    print(f"원인: {str(explanation)[:80]}")
```

- `AnomalyDetector.scan(tasks)`는 Z-Score 기반으로 지연 스파이크, 정확도 드리프트, 토큰 폭증, 오류율 급등, 패턴 이탈을 탐지한다
- 기준선(baseline) 데이터가 충분히 쌓여야 정확한 Z-Score 계산이 가능하다. 최소 20-30건 이상의 정상 데이터 수집 후 스캔하는 것이 권장된다
- `explain_event()`는 이상 이벤트의 원인(어떤 지표, 어느 정도의 편차)을 사람이 읽을 수 있는 형식으로 반환한다

---

## 0. 대시보드 메뉴 3분류 — 무엇이 자동이고 무엇이 아닌가

대시보드 21개 메뉴를 처음 보면 "어떤 탭이 자동으로 채워지고, 어떤 탭은 추가 작업이 필요한가"가 불분명하다. 먼저 전체 구조를 3가지로 분류해 명확히 한다.

### 🟢 데코레이터만으로 가능 (8개)

> `@agent_eval` + `save_to_file()` 만으로 데이터가 자동으로 채워진다.

#### 📊 개요
- **데이터 흐름**: `TaskResult` → `TaskCompletionTracker` · `LatencyTracker` · `TokenEconomyTracker` → `save_to_file()` → `summary` JSON 키
- **표시 내용**: TCR · 정확도 · 평균 지연 · 총 비용 KPI 카드, 프레임워크 분포 도넛 차트, 태스크 유형 바 차트
- **특별 설정 없음** — 모든 `@agent_eval` 호출 결과가 자동 집계됨

#### 📋 태스크
- **데이터 흐름**: `TaskResult` 객체 직렬화 → `tasks[]` JSON 배열
- **표시 내용**: 태스크별 `task_id` / `accuracy_score` / `execution_time` / `success` 테이블. 클릭 시 질문·응답·정답 전문 확인
- **정렬·검색**: 대시보드 API `/api/results?sort_by=accuracy_score&sort_desc=false` 로 문제 케이스 우선 조회 가능

#### 💡 인사이트
- **데이터 흐름**: `save_to_file()` 내부에서 TCR·정확도·P95 지연 임계값 자동 비교 → `insights.alerts` · `insights.recommendations` JSON 키
- **표시 내용**: 경고(빨간색) / 주의(노란색) / 정상(초록색) 배지, 자동 개선 권장사항
- **임계값 조정**: ⚙️ 설정 탭에서 수동 변경 가능

#### 🎯 품질
- **데이터 흐름**: `ResponseQualityEvaluator`(Relevance·Completeness·Accuracy·Clarity·Usefulness 5차원) + `AccuracyEvaluator`(Token F1·Jaccard·LCS·Char) 자동 실행
- **환각 탭 예외**: `PerformanceMonitor(enable_hallucination_detection=True)` 설정 필요. 기본값 False (성능 영향)
- **LLM Judge 섹션**: `@agent_eval(..., enable_llm_judge=True)` 파라미터 추가 시 품질 탭에 Judge 점수 섹션 추가

#### 💬 멀티턴 대화
- **데이터 흐름**: `@conversation_eval` 데코레이터 → `ConversationSession.compute_metrics()` 자동 호출 → `conversation_sessions[]` JSON 키
- **표시 내용**: 턴 수 · 컨텍스트 유지율 · 주제 일관성 · 점진적 심화도 · 세션 완료율
- **`@agent_eval`과 독립**: `@conversation_eval`은 별도 멀티턴 평가 전용 데코레이터

#### ⚡ 성능
- **데이터 흐름**: 모든 `TaskResult.execution_time` → `LatencyTracker` → `efficiency_metrics.latency` JSON 키
- **표시 내용**: 평균·P50·P90·P95·P99·최대·표준편차, 분포 히스토그램, 태스크 유형별 지연 비교
- **토큰 탭**: `TaskResult.tokens_used` → `TokenEconomyTracker` → `efficiency_metrics.tokens` 자동

#### 🤖 에이전틱
- **데이터 흐름**: `TaskResult.tool_calls` → `ToolCallAnalyzer`·`RetryCorrectionTracker`·`ToolSelectionTracker`·`AgentCoordinationTracker`·`WorkflowExecutionTracker`
- **자동 추출**: `@agent_eval(framework="langchain")` 등 프레임워크 어댑터가 응답에서 `tool_calls` 자동 파싱
- **수동 전달**: `create_taskresult(..., tool_calls=[{"name":"search","success":True}])` 직접 지정도 가능
- **에이전틱 탭 공백**: `has_agentic=False` 상태면 "트래커 미활성화" 메시지 표시 → `task_type="tool_use"` + `tool_calls` 데이터 필요

#### 🔒 보안
- **데이터 흐름**: `@agent_eval(..., security_mode=True)` → 5개 보안 트래커 활성 → `security_metrics` JSON 키
- **5개 트래커**: InputSanitization(SQL·XSS·Prompt Injection 탐지) / OutputLeakage(API Key·PII 유출) / ToolAuth(미승인 도구 호출) / PrivilegeEscalation(권한 상승) / ChainAttack(연쇄 공격 패턴)
- **성능 주의**: 보안 트래커는 각 태스크에 정규식 매칭 오버헤드 추가 → 기본값 False

---

### 🟡 데코레이터 + 추가 작업으로 가능 (6개)

> 데코레이터 사용은 전제이되, **별도 객체·플래그·외부 패키지**가 추가로 필요하다.

#### 🔬 외부 평가 (Ragas / DeepEval)
- **추가 필요**: `pip install "agent-evaluator[eval]"` + OpenAI API 키(임베딩) + `HybridPerformanceMonitor`
- **데이터 흐름**: `HybridPerformanceMonitor.record_task()` → 각 태스크 후 Ragas·DeepEval 호출 → `rag_metrics`·`advanced_metrics` JSON 키
- **비용 주의**: 태스크당 LLM 호출 1~3회 추가 발생. `judge_sample_rate=0.1`로 비용 절감 권장

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_ragas=True,        # Faithfulness·Answer Relevancy·Context Recall·Precision
    enable_deepeval=True,     # G-Eval·Hallucination·Toxicity·Bias
)
```

#### 📡 실시간
- **추가 필요**: `StreamingEvaluator` 생성 + `record()` + `_flush()` 명시 호출
- **데이터 흐름**: `StreamingEvaluator.record(task_result)` → 슬라이딩 윈도우(1m/5m/1h) 집계 → `_flush()` → `monitor._streaming_snapshot` → `save_to_file()` 시 `streaming_data` 키 포함
- **핵심 주의**: `_flush()` 호출 없으면 `streaming_data` 키가 JSON에 포함되지 않아 탭 공백

#### 🔔 알림
- **추가 필요**: `SimpleTaskAlertRule` 생성 + `alert_rules=` 전달 + **핸들러에서 JSONL 기록 직접 구현**
- **데이터 흐름**: 태스크 평가 후 `condition(task_result)` 자동 평가 → 조건 충족 시 `handler(msg, tr)` 실행 → 핸들러가 `results/alerts/YYYY-MM-DD.jsonl` 파일에 기록 → 대시보드가 JSONL 파일 직접 읽음
- **흔한 실수**: 핸들러에서 `print()`만 하고 JSONL 기록을 빠뜨리면 알림 탭이 공백

#### 👍 사용자 반응
- **추가 필요**: `monitor.record_implicit_feedback(task_id, feedback_type)` 명시 호출
- **데이터 흐름**: 외부 이벤트(UI 클릭·별점·재질문) 수집 → 평가 루프 내에서 수동 기록 → `ImplicitFeedbackTracker` 누적 → `save_to_file()` 시 `feedback` 키 포함
- **독립 인스턴스 금지**: `ImplicitFeedbackTracker()` 직접 생성 금지. 반드시 `monitor.record_implicit_feedback()` 사용

#### 🚨 이상 감지
- **추가 필요**: `PerformanceMonitor(enable_anomaly_detection=True)` 플래그 설정
- **데이터 흐름**: `save_to_file()` 내부에서 `AnomalyDetector.scan(monitor)` 자동 호출 → `anomaly_data` JSON 키 생성
- **탐지 알고리즘**: latency_trend(선형회귀, 기울기 > 0.05초/태스크) / accuracy_drift(Z-Score > 2.5σ) / token_spike(IQR 기반 Q3+2×IQR 초과) / error_surge(오류율 > 20% AND 기준선 2배)
- **최소 데이터**: 각 알고리즘별 최소 5건 이상 태스크 필요

#### 💰 평가 비용
- **토큰 비용**: `TokenEconomyTracker` 자동 — 추가 설정 불필요
- **LLM Judge 비용**: `enable_llm_judge=True` 추가 → 태스크별 `extra["llm_judge"]["cost_usd"]`에 기록
- **대시보드 UI**: 모델 선택기에서 모델을 변경하면 단가가 재계산됨. 실제 청구액과 차이 가능 (캐싱·배치 할인 미반영)

---

### 🔵 데코레이터 무관으로 가능 (6개)

> 결과 JSON 파일이 있으면 데코레이터 없이도 사용할 수 있는 관리·도구 메뉴.

| 메뉴 | 작동 방식 |
|------|----------|
| **📂 파일 비교** | 드롭다운에서 두 파일 선택 → TCR·정확도·지연·비용 차이 자동 계산. 버전 A vs B 배포 판단에 활용 |
| **📚 골든 데이터셋** | `agent-eval dataset build results/ --min-score 0.8` CLI로 자동 추출, 또는 대시보드 UI에서 수동 추가·편집 |
| **📤 내보내기** | 선택 파일의 JSON 원본·태스크별 CSV·독립형 HTML 리포트 3가지 다운로드 |
| **🔍 투명성** | `TestTransparencyManager.add_annotation()` 독립 호출로 단계별 감사 로그 기록 |
| **📖 지표 설명** | 25개 지표 설명·계산식·해석 가이드. 항상 표시 (정적) |
| **⚙️ 설정** | UI에서 임계값 직접 입력. 서버 재시작 시 초기화 (영속성 없음) |

---

## 1. Layer 1/2 이후 — 외부 연동 기능 확장

### 1.1 Layer 1/2로 커버하지 못하는 상황과 데코레이터 기반 대안

Layer 1/2는 외부 의존성 없이 동작하며 대부분의 기본 지표를 커버한다. 특수한 평가가 필요한 경우 **데코레이터 파라미터 하나로** 확장할 수 있다:

| 상황 | Layer 1/2 한계 | 데코레이터 기반 해결책 |
|------|----------------|----------------------|
| RAG — 환각 정밀 탐지 | Hallucination은 단순 패턴 매칭 | `@agent_eval(..., rag_mode=True)` |
| Ground Truth 없는 평가 | Accuracy는 정답이 있어야 계산 가능 | `@agent_eval(..., enable_llm_judge=True, judge_model="claude-sonnet-4-6")` |
| 보안 위협 탐지 | 기본은 보안 지표 비활성 | `@agent_eval(..., security_mode=True)` |
| 모든 설정 최소화 | 각 파라미터 직접 설정 필요 | `QuickEval.for_rag()` · `QuickEval.for_security()` · `QuickEval.for_llm_judge()` |

### 1.2 상황별 데코레이터 설정 패턴

```python
from agent_evaluator.decorators import agent_eval
from agent_evaluator import PerformanceMonitor, QuickEval

# ① RAG 에이전트 — hallucination 자동 활성
monitor = PerformanceMonitor.for_rag_evaluation("results/")

@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_pipeline.run(question, context)

# ② LLM Judge — ground_truth 없이 자동 채점 (completeness·relevance·factual_consistency)
@agent_eval(monitor, task_type="qa",
            enable_llm_judge=True, judge_model="claude-sonnet-4-6",
            judge_sample_rate=0.1, judge_budget_per_day=5.0)
def general_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# ③ 보안 강화 에이전트 — 5종 보안 지표 임시 활성
@agent_eval(monitor, task_type="qa", security_mode=True)
def secure_agent(question: str, ground_truth: str = "") -> str:
    return agent.run(question)

# ④ QuickEval 팩토리 — 4종
eval_rag  = QuickEval.for_rag("results/")                                      # hallucination 기본 활성
eval_sec  = QuickEval.for_security("results/")                                 # security 기본 활성
eval_llm  = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")    # LLM Judge 활성
eval_reg  = QuickEval.for_regression_eval("results/", baseline_file="results/baseline.json")  # 회귀 테스트
```

### 1.3 LLM Judge — ground_truth 없는 자동 채점

`LLMJudge`는 정답이 없는 상황에서 LLM이 직접 **5차원 기본 (v0.7.5+), +조건부 확장 (v0.7.6+)** 으로 채점한다. `@agent_eval(enable_llm_judge=True)` 한 줄로 통합된다.

```python
# 채점 결과는 TaskResult.extra["llm_judge"]에 자동 기록
# 기본 5차원: completeness·relevance·factual_consistency·toxicity·bias
# {"completeness": 4.5, "relevance": 5.0, "factual_consistency": 4.8,
#  "toxicity": 0.1, "bias": 0.0, "overall": 4.77, "safety_score": 0.99}
# v0.7.6+: rag_mode=True → + "faithfulness": 4.6
# v0.7.6+: judge_criteria=[...] → + "criteria_scores": {...}
```

**비용 제어 옵션:**
- `judge_sample_rate=0.1` — 10%만 LLM Judge로 채점
- `judge_budget_per_day=5.0` — 일일 $5 예산 초과 시 자동 스킵

### 1.4 설치

```bash
# LLM Judge · 대시보드 · OTEL 모니터링은 기본 설치에 포함
pip install agent-evaluator

# DeepEval/Ragas 외부 평가 라이브러리가 추가로 필요한 경우
pip install "agent-evaluator[eval]"
```

---

## 2. 외부 평가 도구 선택 가이드

Layer 1/2만으로 부족할 때 세 가지 외부 평가 방법을 선택할 수 있다. 중복 사용도 가능하지만 비용이 증가한다.

### 2.1 한눈에 비교

| | **LLM Judge** | **DeepEval** | **Ragas** |
|---|---|---|---|
| **설치** | 기본 설치에 포함 | `[eval]` (중간) | `[eval]` (중간) |
| **주요 용도** | 정답 없는 응답 품질 평가 | NLP 품질 + 독성/편향 | RAG 파이프라인 전문 평가 |
| **Ground Truth 필요** | 불필요 | 부분 필요 | 필요 (Recall만) |
| **API 비용** | LLM 호출 비용 | LLM 호출 비용 | 임베딩 + LLM 비용 |
| **커스터마이즈** | 제한적 | G-Eval로 가능 | 제한적 |
| **데코레이터 통합** | `enable_llm_judge=True` | `HybridPerformanceMonitor` | `HybridPerformanceMonitor` |

### 2.2 선택 플로차트

```
내 에이전트가 RAG(문서 검색+생성)인가?
    YES → Ragas 사용 (Faithfulness, Context Precision/Recall)
    NO  ↓

정답(ground_truth)을 제공할 수 있는가?
    YES → Layer 1 Accuracy로 충분 (DeepEval은 추가 품질 검증용)
    NO  ↓

퍼블릭 서비스 or 콘텐츠 생성인가?
    YES → DeepEval (독성/편향 탐지 + G-Eval 커스텀 기준)
    NO  ↓

단순히 "좋은 응답인가" 3차원으로 확인하고 싶다?
    YES → LLM Judge (가장 가벼운 선택)
```

### 2.3 비용 제어 전략

세 도구 모두 LLM API 호출이 발생한다. 프로덕션에서는 샘플링이 필수다.

```python
# LLM Judge: 10%만 샘플링
@agent_eval(monitor, task_type="qa",
            enable_llm_judge=True, judge_sample_rate=0.1, judge_budget_per_day=5.0)
def agent(q, ground_truth=""): ...

# DeepEval / Ragas: 스테이징 환경에서만, 또는 골든 데이터셋(소량)으로
# → 프로덕션에서는 Layer 1 + LLM Judge 10% 샘플링 조합 권장
```

---

## 3. DeepEval 통합 — 심층 품질 평가

### 3.1 DeepEval이 제공하는 지표

| 지표 | 의미 | 사용 시점 |
|------|------|---------|
| G-Eval | LLM이 사용자 정의 기준으로 채점 | 커스텀 평가 기준이 있을 때 |
| Hallucination | 컨텍스트와 모순되는 내용 탐지 | RAG 시스템, 사실 기반 응답 |
| Toxicity | 혐오/욕설/해악 콘텐츠 탐지 | 퍼블릭 서비스, 콘텐츠 모더레이션 |
| Bias | 성별/인종/종교 편향 탐지 | 공정성이 중요한 서비스 |
| Answer Relevancy | 질문과 답변의 관련성 | 범용 QA, 검색 시스템 |

### 3.2 기본 사용법

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,
)

@agent_eval(monitor, task_type="qa")
def content_agent(question, ground_truth=""):
    return llm.invoke(question)

# 테스트 실행
content_agent("AI의 미래는 어떻게 될까요?", ground_truth="AI는 다양한 분야에서 발전할 것입니다.")

report = monitor.generate_report()
deepeval_metrics = report.deepeval_metrics

print(f"Hallucination 점수: {deepeval_metrics.get('hallucination_score', 'N/A')}")
print(f"Answer Relevancy:   {deepeval_metrics.get('answer_relevancy', 'N/A')}")
print(f"Toxicity 점수:      {deepeval_metrics.get('toxicity_score', 'N/A')}")
```

### 3.3 G-Eval — 커스텀 평가 기준

G-Eval의 핵심 가치는 "내가 정의한 기준"으로 LLM이 평가하도록 한다는 것이다. 정량적 정답이 없는 창의성, 전문성, 어조 적합성 등을 평가할 때 유용하다.

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

# 커스텀 평가 기준 정의
professionalism_metric = GEval(
    name="전문성",
    criteria="응답이 전문적이고 명확한가? 전문 용어를 적절히 사용하는가?",
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.7,
)

empathy_metric = GEval(
    name="공감성",
    criteria="고객 서비스 응답으로서 공감적이고 도움이 되는가?",
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.6,
)

# HybridPerformanceMonitor에 커스텀 지표 추가
monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_deepeval=True,
    deepeval_metrics=[professionalism_metric, empathy_metric],
)
```

### 3.4 실무 활용 — 콘텐츠 모더레이션 파이프라인

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval, AlertRuleBuilder

monitor = HybridPerformanceMonitor("results/", use_deepeval=True)

# 독성 점수가 임계값 초과 시 즉시 알림
toxicity_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.0,  # toxicity_score > 0이면 알림
    handler=lambda msg, tr: slack_webhook.send(f"독성 콘텐츠 탐지: {msg}"),
    severity="critical",
)

@agent_eval(monitor, task_type="qa", alert_rules=[toxicity_alert])
def public_chatbot(question, ground_truth=""):
    return chatbot.respond(question)
```

---

## 4. Ragas 통합 — RAG 파이프라인 정밀 평가

### 4.1 Ragas 4가지 핵심 지표

Ragas는 RAG(Retrieval-Augmented Generation) 파이프라인을 위한 업계 표준 평가 프레임워크다.

```
입력: 질문(Q) + 검색된 컨텍스트(C) + 에이전트 응답(A) + 정답(G)

Faithfulness:         A가 C에 충실한가? (A의 주장이 C에서 뒷받침되는가)
Answer Relevancy:     A가 Q에 관련 있는가? (답변이 질문에 답하는가)
Context Precision:    C가 정확한가? (검색된 것 중 실제로 필요한 비율)
Context Recall:       C가 충분한가? (필요한 정보를 모두 검색했는가)
```

**왜 4가지가 모두 필요한가**:

```
Faithfulness 낮음 → LLM이 검색 결과를 무시하고 환각 생성
                   해결: 프롬프트에 "주어진 컨텍스트만 사용하라" 강화

Answer Relevancy 낮음 → 검색은 잘 됐지만 답변이 엉뚱한 곳으로 감
                        해결: 답변 생성 프롬프트 개선

Context Precision 낮음 → 관련 없는 문서가 검색됨
                         해결: 임베딩 모델 교체, 청킹 전략 개선

Context Recall 낮음 → 필요한 문서가 누락됨
                       해결: k(검색 개수) 증가, 재순위화(reranking) 도입
```

### 4.2 기본 사용법

```python
from agent_evaluator import HybridPerformanceMonitor, agent_eval, create_taskresult
import os

os.environ["OPENAI_API_KEY"] = "sk-..."  # Ragas는 임베딩에 OpenAI 사용

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    use_ragas=True,
)

@agent_eval(monitor, task_type="information_retrieval")
def rag_agent(question, context="", ground_truth=""):
    # 1단계: 검색
    retrieved_docs = vector_db.search(question, k=5)
    context_text = "\n".join(doc.page_content for doc in retrieved_docs)

    # 2단계: 생성
    answer = llm.invoke(
        f"Context:\n{context_text}\n\nQuestion: {question}\n\nAnswer:"
    )
    return answer

# 테스트 케이스 — context 필드가 핵심
test_cases = [
    {
        "question": "한국의 GDP는 얼마인가?",
        "context": "2023년 한국의 GDP는 약 1조 7천억 달러로 세계 13위이다.",
        "ground_truth": "약 1조 7천억 달러",
    },
    {
        "question": "서울의 인구는?",
        "context": "서울특별시의 인구는 2023년 기준 약 940만 명이다.",
        "ground_truth": "약 940만 명",
    },
]

for case in test_cases:
    rag_agent(
        case["question"],
        context=case["context"],
        ground_truth=case["ground_truth"],
    )

report = monitor.generate_report()
ragas_metrics = report.ragas_metrics

print(f"Faithfulness:      {ragas_metrics.get('faithfulness', 0):.2%}")
print(f"Answer Relevancy:  {ragas_metrics.get('answer_relevancy', 0):.2%}")
print(f"Context Precision: {ragas_metrics.get('context_precision', 0):.2%}")
print(f"Context Recall:    {ragas_metrics.get('context_recall', 0):.2%}")
```

### 4.3 QuickEval로 RAG 평가

```python
from agent_evaluator import QuickEval

# RAG 전용 설정: hallucination_detection=True 자동 활성
eval = QuickEval.for_rag("results/")

@eval.rag  # task_type="information_retrieval" + context_arg="context" + rag_mode=True 자동 설정
def rag_pipeline(question, context="", ground_truth=""):
    docs = retriever.get_relevant_documents(question)
    return chain.invoke({"question": question, "context": docs})

eval.save()
eval.gate(accuracy=0.75)  # 75% 미만이면 CI/CD 실패
```

### 4.4 실무 팁 — RAG 개선 사이클

```python
# 1. 현재 성능 측정
eval_v1 = QuickEval.for_rag("results/v1/")
# ... 테스트 실행 ...
report_v1 = eval_v1.summary()

# 2. 임베딩 모델 변경 후 재측정
eval_v2 = QuickEval.for_rag("results/v2/")
# ... 테스트 실행 ...
report_v2 = eval_v2.summary()

# 3. 비교
comparison = eval_v1.compare(eval_v2)
print(f"Faithfulness 변화: {comparison['faithfulness_delta']:+.2%}")
print(f"Context Precision 변화: {comparison['context_precision_delta']:+.2%}")
```

---

## 5. LLM Judge — 내장 LLM-as-Judge 평가

### 5.1 LLM Judge vs Ragas/DeepEval

| 특징 | LLM Judge | Ragas | DeepEval |
|------|-----------|-------|---------|
| 외부 라이브러리 | 불필요 (기본 설치에 포함) | 필요 | 필요 |
| Ground Truth 필요 | 불필요 | 부분 필요 | 부분 필요 |
| 평가 차원 | 5차원 기본 + 조건부 확장 | RAG 전문 | 다양한 NLP 지표 |
| 비용 | LLM API 호출 비용 | LLM API 호출 비용 | LLM API 호출 비용 |
| 커스터마이즈 | `judge_criteria`로 G-Eval 대체 (v0.7.6+) | 불가 | G-Eval로 가능 |

LLM Judge는 **정답이 없는 상황**에서 가장 빛난다. 창의적 글쓰기, 고객 서비스 응답, 요약 등 정량적 정답을 정의하기 어려운 경우에 사용한다.

### 5.2 평가 차원 (기본 5 + 조건부 확장)

LLM Judge는 모든 응답을 5가지 기본 차원으로 채점하고, 설정에 따라 추가 차원이 활성화된다:

```
[기본 5차원 — 항상 활성]
completeness:        응답이 질문의 모든 측면을 다루는가?
relevance:           응답이 질문에 직접적으로 관련 있는가?
factual_consistency: 응답이 사실적으로 일관성 있는가?
toxicity:            독성 콘텐츠 포함 여부 (낮을수록 좋음)
bias:                편향 콘텐츠 포함 여부 (낮을수록 좋음)

[조건부 확장 — v0.7.6+]
faithfulness:        rag_mode=True + enable_llm_judge=True + context 있을 때 자동 추가
                     0–5 척도 (5=모든 주장이 컨텍스트에 근거)
criteria_scores:     judge_criteria=[...] 지정 시 커스텀 G-Eval 기준 점수 추가
```

집계 키: `scores["overall"]` (품질 3차원 평균), `scores["safety_score"]` (안전 2차원 역산)

### 5.3 기본 사용법

```python
from agent_evaluator import LLMJudge, PerformanceMonitor, agent_eval
import os

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

monitor = PerformanceMonitor("results/")

# 방법 1: enable_llm_judge 파라미터 (해당 호출만 활성) — 기본 5차원
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
)
def creative_agent(question, ground_truth=""):
    return llm.invoke(question)

# 방법 2: RAG 에이전트 + faithfulness (v0.7.6+)
@agent_eval(
    monitor,
    task_type="information_retrieval",
    rag_mode=True,
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
)
def rag_agent(question, context="", ground_truth=""):
    return llm.rag(question, context)
# → scores["faithfulness"]: 0–5 (5=모든 주장이 컨텍스트에 근거)

# 방법 3: G-Eval 커스텀 기준 — judge_criteria (v0.7.6+, DeepEval 대체)
@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=True,
    judge_model="claude-sonnet-4-6",
    judge_criteria=["medical_accuracy", "patient_safety"],
)
def medical_agent(question, ground_truth=""):
    return medical_llm.ask(question)
# → scores["criteria_scores"]: {"medical_accuracy": 4, "patient_safety": 5}
# → scores["criteria_overall"]: 4.5

# 방법 4: QuickEval.for_llm_judge()
from agent_evaluator import QuickEval

eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

@eval.qa
def customer_service_agent(question, ground_truth=""):
    return chatbot.respond(question)

# 결과 확인 — back-propagation으로 TaskResult에 자동 반영
report = monitor.generate_report()
for task in monitor.tasks:
    judge_scores = task.extra.get("llm_judge", {})
    print(f"질문: {task.extra.get('question', 'N/A')[:40]}")
    print(f"  완결성: {judge_scores.get('completeness', 0):.2f}")
    print(f"  관련성: {judge_scores.get('relevance', 0):.2f}")
    print(f"  사실성: {judge_scores.get('factual_consistency', 0):.2f}")
    print(f"  종합 품질: {judge_scores.get('overall', 0):.2f}")     # 품질 3차원 평균
    print(f"  안전 점수: {judge_scores.get('safety_score', 0):.2f}") # (10-toxicity-bias)/10
```

---

## 6. FastAPI 대시보드 — 운영 시각화

### 6.1 데이터 생성 — `save_to_file()` 필수

대시보드는 `results/` 의 JSON 파일을 읽습니다. 데코레이터 실행 후 반드시 저장 단계가 필요합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# 방법 A: 수동 저장
monitor.save_to_file("eval")        # results/eval.json + .html

# 방법 B: auto_save — N건마다 자동 저장
# monitor = PerformanceMonitor(output_dir="results/", auto_save=True, auto_save_interval=10)

# 방법 C: 데코레이터에 flush_every 지정
# @agent_eval(monitor, task_type="qa", flush_every=50, flush_filename="periodic")
```

### 6.2 대시보드 실행

```bash
# 대시보드는 기본 설치에 포함 — 기본 실행 (results/ 디렉토리의 평가 파일 로드)
agent-eval dashboard results/

# 파일 변경 감시 모드 (실시간 갱신)
agent-eval dashboard results/ --watch

# 포트 지정
agent-eval dashboard results/ --port 8080

# 브라우저에서 접속
# http://localhost:8765
```

### 6.3 50+ API 엔드포인트 카테고리

**태스크 조회 및 필터링**:

```bash
# 특정 태스크 상세 조회
GET /tasks/{id}
# 응답: llm_judge, streaming_steps, chunk_count 포함

# 텍스트 검색
GET /tasks/search?q=오류+메시지

# 복합 조건 필터
POST /tasks/filter
Content-Type: application/json
{
  "filters": [
    {"field": "accuracy_score", "op": "lt", "value": 0.5},
    {"field": "execution_time", "op": "gt", "value": 3.0}
  ],
  "logic": "AND"
}
```

---

## 7. 알림 시스템 — AlertRuleBuilder & SimpleTaskAlertRule

### 7.1 AlertRuleBuilder 팩토리 (권장)

`AlertRuleBuilder`는 자주 쓰이는 알림 조건을 정적 메서드로 제공한다:

| 팩토리 메서드 | 트리거 조건 | 권장 severity |
|---|---|---|
| `when_accuracy_below(threshold)` | accuracy_score < threshold | `"warning"` |
| `when_latency_above(seconds)` | execution_time > seconds | `"warning"` / `"error"` |
| `when_completion_below(threshold)` | completion_score < threshold | `"error"` |
| `when_error()` | errors 리스트 비어있지 않음 | `"error"` |
| `when_tool_calls_exceed(count)` | tool_calls > count | `"warning"` |

```python
from agent_evaluator import AlertRuleBuilder, SimpleTaskAlertRule, agent_eval, PerformanceMonitor

monitor = PerformanceMonitor("results/")

# ① 팩토리 메서드로 빠르게 생성
accuracy_alert = AlertRuleBuilder.when_accuracy_below(
    threshold=0.70,
    handler=lambda msg, tr: print(f"[WARN] 정확도 저하: {msg}"),
    severity="warning",
    cooldown=300,   # 300초 쿨다운 — 같은 규칙 반복 발송 방지
)

latency_alert = AlertRuleBuilder.when_latency_above(
    seconds=5.0,
    handler=lambda msg, tr: print(f"[WARN] 응답 지연: {msg}"),
    severity="warning",
    cooldown=60,
)

completion_alert = AlertRuleBuilder.when_completion_below(
    threshold=0.80,
    handler=lambda msg, tr: print(f"[ERROR] 태스크 실패율 급등: {msg}"),
    severity="error",
    cooldown=120,
)

# ② 데코레이터에 연결 — TaskResult 기록 시 자동 평가
@agent_eval(
    monitor,
    task_type="qa",
    alert_rules=[accuracy_alert, latency_alert, completion_alert],
)
def production_agent(question, ground_truth=""):
    return llm.invoke(question)
```

### 7.2 SimpleTaskAlertRule — 커스텀 조건 알림

팩토리로 커버되지 않는 복잡한 조건은 `SimpleTaskAlertRule`로 직접 정의한다:

```python
from agent_evaluator import SimpleTaskAlertRule

# 토큰 비용 급등 알림
token_cost_alert = SimpleTaskAlertRule(
    name="token_cost_spike",
    condition=lambda tr: tr.tokens_used > 4000,
    handler=lambda msg, tr: print(f"[WARN] 토큰 과다 사용: {tr.tokens_used} tokens"),
    severity="warning",
    cooldown=180,
)

# 복합 조건 — 정확도 낮은 동시에 시간도 오래 걸린 경우
double_fail_alert = SimpleTaskAlertRule(
    name="double_failure",
    condition=lambda tr: tr.accuracy_score < 0.6 and tr.execution_time > 10.0,
    handler=lambda msg, tr: print(f"[CRITICAL] 품질+지연 동시 저하! task={tr.task_id}"),
    severity="critical",
    cooldown=600,
)

# dry_run — 핸들러를 실행하지 않고 조건만 검증 (단위 테스트 활용)
result = double_fail_alert.dry_run(some_task_result)
print(result)   # True / False
```

### 7.3 프로덕션 알림 패턴 — Slack + 이메일 + 로거

```python
import os
import logging
import requests
from agent_evaluator import AlertRuleBuilder, SimpleTaskAlertRule, agent_eval, PerformanceMonitor

logger = logging.getLogger(__name__)

# --- 핸들러 정의 ---
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")

def slack_handler(msg: str, tr) -> None:
    """Slack 채널 전송 — 환경변수 미설정 시 로그로 fallback"""
    if SLACK_WEBHOOK:
        requests.post(SLACK_WEBHOOK, json={
            "text": f"🚨 *Agent Alert*\n{msg}\n• task_id: `{tr.task_id}`\n• accuracy: `{tr.accuracy_score:.2f}`"
        }, timeout=5)
    else:
        logger.warning("[SLACK_FALLBACK] %s", msg)

def log_handler(msg: str, tr) -> None:
    logger.error("[AGENT_ALERT] %s | task=%s | latency=%.2fs", msg, tr.task_id, tr.execution_time)

# --- 5종 알림 규칙 ---
ALERT_RULES = [
    AlertRuleBuilder.when_accuracy_below(
        threshold=0.70, handler=slack_handler, severity="warning", cooldown=300),
    AlertRuleBuilder.when_latency_above(
        seconds=8.0, handler=slack_handler, severity="warning", cooldown=60),
    AlertRuleBuilder.when_completion_below(
        threshold=0.75, handler=slack_handler, severity="error", cooldown=120),
    AlertRuleBuilder.when_error(
        handler=log_handler, severity="error", cooldown=30),
    SimpleTaskAlertRule(
        name="high_retry",
        condition=lambda tr: tr.attempts >= 3,
        handler=slack_handler,
        severity="warning",
        cooldown=300,
    ),
]

# --- PerformanceMonitor + 데코레이터 연결 ---
monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa", alert_rules=ALERT_RULES, flush_every=50)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 7.4 QA 관리자 — 알림 임계값 설정 가이드

알림을 너무 많이 보내면 "알림 피로"가 생겨 정작 중요한 이슈를 놓치게 된다. 아래 기준을 초기값으로 사용하고, 2주 후 실제 분포를 보고 조정한다:

| 지표 | Warning 임계값 | Error 임계값 | cooldown |
|------|---------------|-------------|---------|
| accuracy_score | < 0.70 | < 0.55 | 300s / 60s |
| execution_time | > 5s | > 10s | 60s / 30s |
| completion_score | < 0.80 | < 0.60 | 120s / 60s |
| tokens_used | > 3000 | > 6000 | 180s / 60s |
| attempts (재시도) | ≥ 2 | ≥ 4 | 300s / 120s |

> **팁**: 최초 배포 후 1주일은 `cooldown`을 길게 잡아 알림 빈도를 낮추고, 운영이 안정되면 단계적으로 줄인다.

---

## 8. 이상 탐지 — AnomalyDetector

### 8.1 동작 원리

`AnomalyDetector`는 Z-Score 기반 통계적 이상 탐지를 사용한다.

```python
from agent_evaluator import AnomalyDetector, PerformanceMonitor

monitor = PerformanceMonitor("results/")
detector = AnomalyDetector(z_score_threshold=2.5)

# save_to_file()이 자동으로 anomaly 데이터 포함
monitor.save_to_file("evaluation")
```

---

## 9. 비용 제어 — CostTracker & AdaptivePolicy

### 9.1 AdaptivePolicy — 예산 초과 시 자동 다운그레이드

```python
from agent_evaluator import AdaptivePolicy, SamplingStage, agent_eval

policy = AdaptivePolicy(
    daily_budget_usd=100.0,
    stages=[
        SamplingStage(name="normal", sample_rate=1.0, model="gpt-4o"),
        SamplingStage(name="reduced", sample_rate=0.5, model="gpt-4o-mini"),
    ]
)

current = policy.get_current_stage()

@agent_eval(monitor, task_type="qa", sample_rate=current.sample_rate)
def cost_aware_agent(question):
    return llm.invoke(question, model=current.model)
```

---

## 10. 골든 데이터셋 — GoldenSetBuilder

### 10.1 프로덕션 마이닝

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(min_score=0.85)
cases = builder.extract_cases(monitor.tasks)
builder.push_to_phoenix(cases, dataset_name="prod_golden")
```

---

## 11. 멀티턴 대화 평가 — ConversationSession

### 11.1 6가지 대화 지표

| 지표 | 설명 | 좋은 값 |
|------|------|---------|
| `context_retention` | 이전 대화 맥락 유지 능력 | > 0.8 |
| `topic_coherence` | 주제의 일관성 | > 0.7 |
| `progressive_depth` | 대화의 심화도 | > 0.6 |
| `session_completion` | 목표 달성 여부 | > 0.8 |

### 11.2 @conversation_eval 데코레이터 (권장 방법)

v0.7.3부터 수동으로 세션을 관리하는 패턴 대신 데코레이터를 사용하는 것이 권장됩니다. `PerformanceMonitor`와 연동하여 자동으로 턴을 누적하고 지표를 계산합니다.

```python
from agent_evaluator import PerformanceMonitor, conversation_eval, flush_conversation

monitor = PerformanceMonitor("results/")

@conversation_eval(
    monitor,
    session_id_arg="session_id",        # 세션 ID를 파라미터에서 읽음
    max_turns=10,                       # 10턴 초과 시 자동 종료
    on_turn=lambda turn: print(f"턴 {turn.turn_number} 완료"),
    on_flush=lambda metrics, sid: print(f"세션 {sid} 종료: {metrics.overall_score:.2f}")
)
def chatbot_agent(user_message, session_id="default", history=None):
    # 실제 에이전트 호출 (history는 데코레이터가 자동 주입)
    response = llm.invoke(user_message, history=history or [])
    return response

# 1. 턴 호출 (자동 누적)
chatbot_agent("안녕하세요", session_id="sess_001")
chatbot_agent("서울 여행 계획 알려줘", session_id="sess_001")

# 2. 세션 명시적 종료 및 기록
flush_conversation("sess_001")

# 세션 결과는 monitor.generate_report()에 자동 포함
report = monitor.generate_report()
print(report.conversation_metrics)
```

### 11.3 monitor.conversation() — 컨텍스트 매니저 패턴 (v0.6.3+)

데코레이터를 사용할 수 없는 복잡한 루프나 스크립트 환경에서는 컨텍스트 매니저 패턴을 사용합니다.

```python
# 컨텍스트 매니저 방식
with monitor.conversation("session_002") as conv:
    for user_msg in ["안녕", "누구니?"]:
        response = chatbot.respond(user_msg, history=conv.history)
        conv.turn(
            user=user_msg,
            agent=response,
            metadata={"latency": 0.5}
        )
```

---

## 마무리 — M4 핵심 요약

```
Layer 3: "네이티브 지표로 부족할 때"
  ├── §3 DeepEval    → Toxicity, Bias, G-Eval (커스텀 기준)
  ├── §4 Ragas       → RAG 파이프라인 전문 평가 (4종)
  └── §5 LLM Judge   → Ground Truth 없는 평가 (3차원)

운영 인프라:
  ├── §6  FastAPI 대시보드 → 50+ 엔드포인트, 실시간 WebSocket
  ├── §7  AlertRuleBuilder → 5종 알림 규칙, cooldown, Slack/이메일 핸들러
  ├── §8  AnomalyDetector  → Z-Score 이상 탐지 + 원인 설명
  ├── §9  CostTracker      → 비용 추적 + AdaptivePolicy 자동 절감
  └── §10 GoldenSetBuilder → 프로덕션 트래픽 → 회귀 테스트셋 자동화

멀티턴:
  └── §11 @conversation_eval → 세션 기반 대화 품질 측정 (권장)
```

### QA 관리자 — M4 최종 점검 체크리스트

- [ ] `save_to_file()` 또는 `auto_save=True` 설정 → 대시보드 데이터 생성
- [ ] `agent-eval dashboard results/ --watch` → 대시보드 실시간 확인
- [ ] 알림 임계값(accuracy/latency/completion) 팀 기준으로 설정
- [ ] Slack Webhook 환경변수 설정 (`SLACK_WEBHOOK_URL`)
- [ ] `flush_every=50` → 장기 운영 시 주기적 저장 보장
- [ ] GoldenSetBuilder로 점수 높은 케이스 → 회귀 테스트셋 추출
