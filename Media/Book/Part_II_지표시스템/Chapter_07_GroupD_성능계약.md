# Chapter 7. Gate D — 성능계약 지표

@@HTML_START@@
<div class="hc-card hc-d">
  <div class="hc-header">
    <span class="hc-gate-badge he-gate gd">Gate D</span>
    <span class="hc-title">🔗 Harness 연결 — Performance Contract (성능계약)</span>
  </div>
  <div class="hc-body">
    <div class="hc-row">
      <span class="hc-label hc-tracker-label">Tracker</span>
      <div class="hc-chips">
        <span class="hc-chip hc-t-chip">LatencyTracker</span>
        <span class="hc-chip hc-t-chip">TokenEconomyTracker</span>
      </div>
    </div>
    <div class="hc-row">
      <span class="hc-label hc-config-label">Config</span>
      <div class="hc-chips">
        <span class="hc-chip hc-c-chip">SLAConfig</span>
        <span class="hc-chip hc-c-chip">EfficiencyConfig</span>
        <span class="hc-chip hc-c-chip">ResourceBudgetConfig</span>
        <span class="hc-chip hc-c-chip">TTFTVariabilityConfig</span>
        <span class="hc-chip hc-c-chip">CostPredictabilityConfig</span>
      </div>
    </div>
  </div>
  <div class="hc-footer">
    <code>HarnessEvaluationGate(report).evaluate()</code>
  </div>
</div>
@@HTML_END@@

> 📖 **관련 레퍼런스**
> - **[Appendix A — 58개 지표 완전 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate D 지표 입력·출력
> - **[Appendix H — 수학적 상세](../Appendix/H_알고리즘_수학적_레퍼런스.md)**: 퍼센타일 계산 공식, 비용 추정 수식
> - **[Appendix A §Part 2 — Config 레퍼런스](../Appendix/A_58개지표_레퍼런스.md)**: Gate D Config 파라미터 전체 목록
> - **[Evaluator_Examples/ch07_group_d.py](../../Evaluator_Examples/ch07_group_d.py)**: 이 챕터 실전 예제 (LatencyTracker · TokenEconomyTracker · 5개 Config · Gate D FAIL 시나리오)

> **독자별 읽기 가이드**  
> - **QA 관리자**: §7.1(개요) → §7.4(Config 설정) → §7.5(임계값·Gate 판정) 순서로 읽으면 "SLA·비용 기준을 어떻게 선언할지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §7.2(Tracker 상세) → §7.3(코드 예제) → §7.4(Config 선언) 순서로 읽으면 `SLAConfig`, `ResourceBudgetConfig` 등을 바로 적용할 수 있습니다.

---

@@HTML_START@@
<div class="gw-box">
  <div class="gw-header">⚠️ Gate D가 없으면 생기는 일</div>
  <div class="gw-body">
    <p>개발 환경에서 P95 응답 시간 1.2초. 프로덕션 트래픽에서 P95 8.7초. SLA는 3초. 한 달 뒤 SLA 위반 보고서를 받는다. SLAConfig로 배포 전에 테스트 트래픽을 시뮬레이션했다면 조기에 발견할 수 있었다.</p>
    <div class="gw-case">
      <strong>실제 사례:</strong> 토큰 사용량 모니터링 없이 운영한 에이전트가 한 달에 예상의 5배를 소비. ResourceBudgetConfig의 max_tokens 설정 하나로 방지할 수 있었다.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 7.1 Gate D 개요

Group D는 에이전트가 **약속한 성능 계약(Performance Contract)**을 지키는지 측정한다. 에이전트가 아무리 정확해도(Gate A) 응답이 10초씩 걸리거나 태스크당 $1씩 비용이 나온다면 프로덕션에 배포할 수 없다.

> **Gate D = 성능 계약서를 코드로 선언한다**  
> `SLAConfig(p95_ms=2000)`는 단순한 설정값이 아니라 "P95 응답이 2초를 초과하면 배포 불가"라는 계약 조항이다. Harness Engineering에서 Gate D는 이 계약 조항들을 코드로 명문화하고, 매 평가마다 자동으로 준수 여부를 검증한다.

> **Gate A + Gate D — 모든 에이전트의 필수 기준선**  
> Gate A(Goal Achievement)는 "에이전트가 올바른 답을 내는가"를 묻고, Gate D(Performance Contract)는 "그 답이 적시에·적정 비용으로 나오는가"를 묻는다. 두 Gate는 항상 활성화된 baseline이다. Gate A 없이는 정확도를 보장할 수 없고, Gate D 없이는 비용·SLA를 보장할 수 없기 때문이다.

### Group D가 다루는 3가지 계약

1. **시간 계약**: P95·P99 응답 시간이 SLA를 지키는가? (`SLAConfig`)
2. **비용 계약**: 태스크당 토큰·비용이 예산 내에 있는가? (`ResourceBudgetConfig`, `EfficiencyConfig`)
3. **안정성 계약**: 성능이 예측 가능하고 일관적인가? (`TTFTVariabilityConfig`, `CostPredictabilityConfig`)

### Tracker vs Config — Gate D 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "실제 응답 시간·비용이 얼마인가?" | "이 수준이면 SLA를 지킬 수 있는가?" |
| 코드 위치 | `PerformanceMonitor` 내부 자동 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 계약 선언 |
| 예시 | `latency_p95=1850ms` | `SLAConfig(p95_ms=2000)` → "P95 2초 이내" |

---

## 7.2 Tracker 2종 심화

### 7.2.1 LatencyTracker — 응답 시간 퍼센타일

`LatencyTracker`는 에이전트 응답 시간을 퍼센타일 기반으로 측정한다. 평균 응답 시간이 아닌 P95·P99를 기준으로 하는 이유는 **"대부분의 사용자가 경험하는 최악의 응답 시간"**이 더 중요하기 때문이다.

> **왜 평균이 아닌 P95인가?**  
> 100건 요청 중 95건이 1초 내에 처리되고 5건이 20초씩 걸려도 평균은 약 2초로 "양호"해 보인다. 하지만 그 5건의 사용자는 20초를 기다린다. P95는 95번째로 느린 응답, 즉 "상위 5% 사용자가 경험하는 최악의 응답 시간"이다. SLA 계약에서 P95를 기준으로 삼는 이유가 여기에 있다.

**측정 항목 (5가지 퍼센타일 + TTFT):**

| 항목 | 설명 |
|------|------|
| `latency_p50` | 중앙값 응답 시간 (50번째 퍼센타일) |
| `latency_p90` | P90 응답 시간 — 상위 10% 지연 탐지 |
| `latency_p95` | P95 응답 시간 — SLA 계약 기준 |
| `latency_p99` | P99 응답 시간 — 극단적 지연 탐지 (미션 크리티컬) |
| `latency_mean` | 평균 응답 시간 |
| `ttft_p50` | Time-to-First-Token P50 (스트리밍 에이전트) |
| `latency_histogram` | 응답 시간 분포 히스토그램 |

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 추가A — 지연시간 분포 (LatencyTracker)
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval
import time

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 50개 태스크 실행
for q, gt in test_dataset[:50]:
    agent(q, ground_truth=gt)

report = monitor.generate_report()
d = report.to_dict()
print(f"P50 응답 시간: {d.get('latency_p50', 0) * 1000:.0f}ms")
print(f"P95 응답 시간: {d.get('latency_p95', 0) * 1000:.0f}ms")
print(f"P99 응답 시간: {d.get('latency_p99', 0) * 1000:.0f}ms")
```

- `@agent_eval`로 감싼 함수는 실행 시간이 자동으로 `LatencyTracker`에 기록된다.
- `generate_report()`를 호출하면 P50·P95·P99 퍼센타일이 계산된다.
- `latency_p95`는 SLA 위반 여부를 판단하는 핵심 지표다.
- 태스크 수가 적을수록 퍼센타일 추정치가 불안정하므로 최소 20건 이상 실행을 권장한다.

**P50/P90/P95/P99 선택 가이드:**

| 지표 | 의미 | 권장 SLA 기준 |
|------|------|-------------|
| P50 | 절반의 사용자 경험 | 내부 대시보드 모니터링 |
| P90 | 상위 10% 지연 탐지 | 중간 수준 서비스 모니터링 |
| P95 | 95% 사용자 경험 | 외부 SLA 계약 기준 (일반적) |
| P99 | 99% 사용자 경험 | 미션 크리티컬 서비스 |

**TTFT (Time-to-First-Token) 추적:**

스트리밍 응답 에이전트에서 첫 토큰까지의 대기 시간을 별도로 측정한다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 추가A — 지연시간 분포 (TTFT 측정)
from agent_evaluator.decorators import agent_eval

@agent_eval(monitor, task_type="qa")
def streaming_agent(question: str, ground_truth: str = "") -> str:
    # generator 반환 시 첫 yield 시점이 자동으로 TTFT로 기록됨
    for chunk in llm.stream(question):
        yield chunk
```

- 제너레이터를 반환하면 `@agent_eval`이 첫 번째 `yield` 시점을 TTFT로 자동 기록한다.
- TTFT는 전체 응답 시간과 별도로 `ttft_p50` 등 퍼센타일로 집계된다.
- 스트리밍을 지원하지 않는 에이전트는 TTFT 대신 전체 응답 시간을 지연 지표로 사용한다.

> **TTFT 변동성이 중요한 이유**  
> TTFT 평균이 0.3초라도 어떤 요청은 0.1초, 어떤 요청은 1.5초라면 사용자는 응답이 "불안정하다"고 느낀다. 스트리밍 챗봇에서 첫 토큰이 "언제 올지 모른다"는 느낌은 전체 응답 시간보다 사용자 경험에 더 큰 부정적 영향을 미친다. `TTFTVariabilityConfig`는 이 변동성 자체를 Gate D 판정 기준으로 선언한다.

**응답 시간 임계값 가이드:**

| P95 응답 시간 | 상태 | 의미 |
|-------------|------|------|
| ≤ 1000ms | 🟢 즉각적 | 챗봇, 실시간 검색 |
| 1~3초 | 🟡 허용 | 일반 응답 |
| 3~10초 | 🟠 느림 | 사용자 체감 불만 시작 |
| > 10초 | 🔴 매우 느림 | 배포 금지 검토 |

### 7.2.2 TokenEconomyTracker — 토큰 사용량·비용 추정

토큰 사용량을 추적하고 LLM API 비용을 자동으로 추정한다.

**측정 항목:**

| 항목 | 설명 |
|------|------|
| `total_tokens` | 전체 토큰 사용량 (input + output) |
| `avg_tokens_per_task` | 태스크당 평균 토큰 수 |
| `estimated_cost_usd` | 추정 비용 (USD) |
| `cost_per_completion` | 완료 태스크당 비용 |
| `token_efficiency` | 완료율 대비 토큰 효율 |

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 추가B — 토큰 경제성 & 비용 추정
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="t1",
    question="인공지능이란?",
    response="인공지능은...",
    execution_time=1.2,
    task_type="qa",
    tokens_used=450,    # input(150) + output(300)
    extra={
        "input_tokens": 150,
        "output_tokens": 300,
        "model": "claude-haiku-4-5-20251001",
    },
)
monitor.record_task(result)

report = monitor.generate_report()
d = report.to_dict()
print(f"총 토큰: {d.get('total_tokens', 0):,}")
print(f"태스크당 평균: {d.get('avg_tokens_per_task', 0):.0f} 토큰")
print(f"추정 비용: ${d.get('estimated_cost_usd', 0):.4f}")
```

- `extra` 딕셔너리에 `input_tokens`·`output_tokens`를 넣으면 모델별 단가로 비용이 자동 추정된다.
- `model` 필드가 없으면 `tokens_used` 전체를 output 토큰으로 간주해 추정한다.
- `estimated_cost_usd`는 참고용 추정치이며, 실제 청구 금액과 다를 수 있다.
- 여러 모델을 혼용할 경우 각 태스크에 `model` 필드를 명시해야 정확한 비용이 집계된다.

**모델별 비용 참고 (2026년 4월 기준):**

| 모델 | Input (1M 토큰) | Output (1M 토큰) |
|------|----------------|-----------------|
| claude-haiku-4-5 | $0.80 | $4.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4o | $2.50 | $10.00 |

---

## 7.3 Config 5종 레퍼런스

### 7.3.1 SLAConfig — SLA 준수 선언

응답 시간과 비용에 대한 SLA(Service Level Agreement)를 코드로 선언한다. **Group D의 핵심 Config**다.

> **SLAConfig = SLA 계약서를 코드로**  
> 전통적 SLA는 문서로만 존재한다. `SLAConfig(p95_ms=2000, fail_threshold=5)`는 "P95 응답이 2초 초과 위반이 5건을 넘으면 Gate D를 fail 처리한다"는 계약 조항을 코드로 명문화한 것이다. 매 배포 전 평가에서 이 계약 조항이 자동으로 검증된다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 4 — Gate D Performance Contract
from agent_evaluator import SLAConfig

SLAConfig(
    p95_ms=3000.0,          # P95 응답 시간 상한 (ms)
    p99_ms=10000.0,         # P99 응답 시간 상한 (ms)
    ttft_ms=None,           # TTFT 상한 (스트리밍 에이전트만)
    breach_window=10,       # 최근 N건 기준으로 위반 여부 판정
    warn_threshold=2,       # N건 위반 시 경고
    fail_threshold=5,       # N건 위반 시 fail
    max_cost_per_task=None, # 태스크당 최대 비용 (USD)
    budget_usd=None,        # 전체 평가 세션 최대 비용 (USD)
)
```

- `p95_ms`·`p99_ms`는 **밀리초(ms) 단위**로 선언한다. `p95_ms=2000`이면 "2초 이내"를 뜻하며, 초 단위와 혼동하지 않도록 주의한다. 임계값을 초과하면 Gate D가 경고 또는 fail 처리된다.
- `breach_window`는 슬라이딩 윈도우 크기이며, 최근 N건 중 위반 수가 `fail_threshold`를 넘으면 fail이 된다.
- `max_cost_per_task`와 `budget_usd`는 비용 측면의 SLA 계약으로, `ResourceBudgetConfig`와 함께 사용하면 통계·개별 수준을 이중으로 통제할 수 있다.
- `ttft_ms`는 스트리밍 에이전트 전용이며, 비스트리밍 에이전트에서는 `None`으로 두면 된다.

**서비스 유형별 SLAConfig 예시:**

```python
# 출처: Evaluator_Examples/ch07_group_d.py — SLAConfig
# 실시간 챗봇 — 즉각적인 응답 필요
chatbot_sla = SLAConfig(
    p95_ms=2000,
    p99_ms=5000,
    ttft_ms=500,            # 첫 토큰 500ms 이내
    fail_threshold=3,
    max_cost_per_task=0.002,
)

# 배치 분석 에이전트 — 느린 응답 허용, 비용 절감 중요
batch_sla = SLAConfig(
    p95_ms=30000,           # 30초 허용
    p99_ms=60000,
    max_cost_per_task=0.05,
    budget_usd=10.0,        # 배치당 $10 예산
)

# API 백엔드 에이전트 — 엄격한 SLA
api_sla = SLAConfig(
    p95_ms=1500,
    p99_ms=3000,
    fail_threshold=2,       # 2번만 위반해도 fail
    max_cost_per_task=0.001,
)
```

- 실시간 챗봇은 P95 2초, 배치 에이전트는 P95 30초처럼 서비스 특성에 맞게 임계값을 조정한다.
- `ttft_ms=500` 설정은 스트리밍 챗봇에서 사용자 체감 응답성을 확보하는 데 효과적이다.
- `fail_threshold`를 낮게 설정할수록 위반에 민감하게 반응하므로, 초기 테스트 단계에서는 느슨하게 시작한다.

### 7.3.2 EfficiencyConfig — 비용 대비 완료율

토큰/비용 대비 실제 완료율(ROI)을 측정한다. "돈을 쓴 만큼 가치가 나왔는가?"를 평가한다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 4 — Gate D Performance Contract
from agent_evaluator import EfficiencyConfig

EfficiencyConfig(
    cost_unit="tokens",                   # "tokens"|"usd"|"time_ms"
    target_cost_per_completion=None,      # 완료 태스크당 목표 비용
    penalize_failed_tokens=True,          # 실패 태스크 토큰도 비용으로 산정
    warn_ratio=2.0,                       # 목표 대비 2배 초과 시 경고
    fail_ratio=4.0,                       # 목표 대비 4배 초과 시 fail
)
```

**사용 예시:**

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 4 — Gate D Performance Contract
@agent_eval(
    monitor,
    task_type="qa",
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=500,  # 완료 태스크당 목표 500 토큰
        penalize_failed_tokens=True,     # 실패해도 비용은 발생
        warn_ratio=2.0,
        fail_ratio=3.5,
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `target_cost_per_completion`에 목표 토큰 수를 설정하면, 실제 완료 비용이 이를 초과하는 비율을 추적한다.
- `penalize_failed_tokens=True`는 실패 태스크도 비용으로 산정해 재시도 남용을 억제한다.
- `warn_ratio=2.0`이면 목표 대비 2배 초과 시 경고, `fail_ratio`에 도달하면 Gate D가 fail이 된다.

### 7.3.3 ResourceBudgetConfig — 리소스 예산 상한

개별 태스크 수준에서 토큰·비용·실행시간의 하드 상한을 설정한다. `SLAConfig`가 통계적 위반을 탐지한다면, `ResourceBudgetConfig`는 개별 태스크의 폭주를 즉시 차단한다.

> **비용 초과 시 자동 차단의 비즈니스적 의미**  
> `ResourceBudgetConfig(max_cost_usd=0.05)`는 단일 태스크가 $0.05를 초과하면 Gate D를 fail 처리한다. "에이전트 한 번 호출에 $5가 청구되는" 사고를 배포 전에 막는 안전망이다. 프로덕션에서 이런 폭주는 LLM 무한 루프, 컨텍스트 누적, 재시도 남용에서 발생한다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 역케이스 Gate D FAIL (ResourceBudgetConfig)
from agent_evaluator import ResourceBudgetConfig

ResourceBudgetConfig(
    max_tokens=2000,              # 태스크당 최대 토큰 수
    max_cost_usd=0.05,           # 태스크당 최대 비용 (USD)
    max_execution_time_ms=5000,   # 태스크당 최대 실행 시간 (ms)
    warn_at_pct=0.8,             # 예산 80% 도달 시 사전 경고
    count_failed_tokens=True,     # 실패 태스크 토큰도 예산에 포함
    rollover=False,               # True: 미사용 예산 다음 태스크로 이월
)
```

> **파라미터 안내**: `ResourceBudgetConfig`의 예산 경고는 `warn_at_pct`(예산 소진 비율)로 설정한다. `EfficiencyConfig`의 `warn_ratio`·`fail_ratio`(목표 대비 배율)와는 별개 파라미터다.

**SLAConfig vs ResourceBudgetConfig 비교:**

| 관점 | SLAConfig | ResourceBudgetConfig |
|------|-----------|---------------------|
| 적용 단위 | 통계 (P95·P99) | 개별 태스크 |
| 탐지 방식 | 전체 분포 기반 | 태스크별 즉시 체크 |
| 목적 | SLA 위반 추세 감지 | 개별 폭주 방지 |
| 예시 | "P95가 3초 초과 시 경고" | "단일 태스크가 5초 초과 시 즉시 fail" |

```python
# 출처: Evaluator_Examples/ch07_group_d.py — SLAConfig · ResourceBudgetConfig
# 둘 다 사용하는 것이 권장
@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(p95_ms=2000, fail_threshold=5),
    resource_budget=ResourceBudgetConfig(
        max_tokens=3000,
        max_execution_time_ms=8000,    # 개별 태스크 하드 상한
        warn_at_pct=0.75,
    ),
)
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `SLAConfig`는 전체 통계적 추세를, `ResourceBudgetConfig`는 개별 태스크 수준을 통제하므로 두 Config를 함께 사용하는 것이 권장된다.
- `warn_at_pct=0.75`이면 예산의 75%에 도달했을 때 미리 경고해 조기 대응이 가능하다.
- `max_execution_time_ms`는 개별 태스크 하드 상한으로, 무한 루프나 타임아웃 미설정 LLM 호출로부터 보호한다.

### 7.3.4 TTFTVariabilityConfig — TTFT 변동성

첫 토큰까지의 대기 시간(TTFT) 변동성을 측정한다. 스트리밍 에이전트에서 사용자 체감 품질에 직접 영향을 준다.

> **monitor 수준 자동 집계**: `TTFTVariabilityConfig`는 `@agent_eval` 데코레이터 파라미터로 전달하지 않는다. `PerformanceMonitor._compute_harness_groups()`에서 세션 전체의 `ttft_ms` 데이터를 자동으로 수집·집계해 판정한다. 개별 `TaskResult`가 아닌 **모니터 전체 집계** 수준에서 동작한다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 역케이스 Gate D FAIL (TTFTVariabilityConfig)
from agent_evaluator import TTFTVariabilityConfig

TTFTVariabilityConfig(
    max_stddev_ms=500.0,       # TTFT 표준편차 허용 상한 (ms)
    max_p95_p50_ratio=3.0,    # P95/P50 비율 상한 (3배 이상이면 변동성 높음)
    min_samples=5,             # 통계에 필요한 최소 샘플 수
    remove_outliers=True,      # 극단적 이상치 제거 후 계산
)
```

- `max_stddev_ms=500.0`: TTFT 표준편차가 500ms를 초과하면 Gate D 경고. 단위는 밀리초.
- `max_p95_p50_ratio=3.0`: P95 TTFT가 P50 TTFT의 3배 이상이면 변동성이 너무 높다고 판정.
- `min_samples`: 최솟값 미달 시 Gate D 리포트에 `insufficient_data_warnings`가 기록되며, 판정은 보류된다.

### 7.3.5 CostPredictabilityConfig — 비용 예측 가능성

동일 `task_type` 내 비용의 변동 계수(CV, Coefficient of Variation)를 측정한다. 비용이 예측 가능하게 안정적인지를 평가한다.

> **monitor 수준 자동 집계**: `CostPredictabilityConfig`도 `@agent_eval` 파라미터가 아닌 `PerformanceMonitor._compute_harness_groups()`에서 task_type별로 자동 집계된다. 세션 전체의 토큰·비용 데이터를 모아 CV를 산출한다.

> **프로덕션 운영에서 비용 예측 가능성이 중요한 이유**  
> 월 예산이 $500인 에이전트가 어떤 날은 $10, 어떤 날은 $200을 쓴다면 재무 계획이 불가능하다. CV가 낮다는 것은 동일한 task_type에서 비용이 안정적으로 유지된다는 의미다. CV가 갑자기 높아지면 "입력 복잡도가 달라졌다", "재시도가 증가했다" 같은 운영 이상의 신호일 수 있다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 4 — Gate D Performance Contract
from agent_evaluator import CostPredictabilityConfig

CostPredictabilityConfig(
    max_coefficient_of_variation=0.3,  # CV 허용 상한 (30% = 낮은 변동성)
    outlier_multiplier=3.0,            # 이상치 제거 기준 (IQR × N)
    min_samples=5,                     # 통계에 필요한 최소 샘플 수
    cost_metric="tokens",              # "tokens"|"usd"|"time_ms"
)
```

- `max_coefficient_of_variation`은 비용 안정성 기준으로, 값이 낮을수록 비용이 예측 가능하다는 의미다.
- `min_samples`에 미달하면 Gate D 리포트에 `insufficient_data_warnings`가 기록되며 판정은 보류된다.
- `outlier_multiplier`로 IQR 기반 이상치를 제거하면 단일 극단값이 CV를 왜곡하는 것을 방지한다.
- `cost_metric="usd"`로 설정하면 토큰 수 대신 달러 기준으로 변동성을 측정한다.

**CV(변동 계수) 해석:**

```
CV = 표준편차 / 평균

CV = 0.1  → 매우 예측 가능한 비용 (±10% 수준)
CV = 0.3  → 허용 가능한 변동 (기본 임계값)
CV = 0.5  → 높은 변동 — 복잡도가 다른 태스크 혼재
CV > 0.8  → 매우 불규칙 — 비용 예산 계획 불가
```

---

## 7.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 실시간 챗봇 (저지연 중심)

```python
# 출처: Evaluator_Examples/ch07_group_d.py — SLAConfig · ResourceBudgetConfig · EfficiencyConfig
from agent_evaluator import (
    SLAConfig,
    ResourceBudgetConfig,
    EfficiencyConfig,
)

@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(
        p95_ms=1500,
        p99_ms=3000,
        ttft_ms=500,
        fail_threshold=3,
    ),
    resource_budget=ResourceBudgetConfig(
        max_tokens=1500,
        max_execution_time_ms=4000,
        warn_at_pct=0.8,
    ),
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=800,
    ),
)
def chatbot(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `SLAConfig(p95_ms=1500)`은 챗봇에서 95%의 사용자가 1.5초 이내에 응답을 받아야 함을 선언한다.
- `ttft_ms=500`으로 스트리밍 첫 토큰이 0.5초 이내에 출력되도록 요구해 체감 응답성을 높인다.
- `ResourceBudgetConfig(max_tokens=1500)`은 응답 길이가 짧도록 유도해 지연 시간과 비용을 동시에 절감한다.
- `EfficiencyConfig(target_cost_per_completion=800)`은 완료 태스크당 평균 800토큰 이내를 목표로 설정한다.

### 패턴 2 — 비용 예산 관리가 중요한 에이전트

```python
# 출처: Evaluator_Examples/ch07_group_d.py — SLAConfig · ResourceBudgetConfig · CostPredictabilityConfig
from agent_evaluator import (
    SLAConfig,
    ResourceBudgetConfig,
    CostPredictabilityConfig,
)

@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(
        p95_ms=5000,
        max_cost_per_task=0.01,    # 태스크당 최대 $0.01
        budget_usd=5.0,             # 세션 전체 $5 예산
    ),
    resource_budget=ResourceBudgetConfig(
        max_tokens=4000,
        max_cost_usd=0.015,
        warn_at_pct=0.7,
    ),
)
def cost_controlled_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

- `SLAConfig(budget_usd=5.0)`은 평가 세션 전체 비용이 $5를 초과하면 Gate D가 자동 fail 처리된다. 이는 "이 에이전트를 프로덕션에서 하루 동안 운영할 때 비용이 예산 범위 내에 있는가"를 배포 전에 검증하는 메커니즘이다.
- `max_cost_per_task`와 `max_cost_usd`를 함께 설정하면 태스크 단위·세션 단위 두 계층에서 비용을 통제한다.
- `warn_at_pct=0.7`로 예산 70% 도달 시 경고해 세션 종료 전 대응 여유를 확보한다.

---

## 7.5 AI Native 관점 — 성능은 계약이다

### 7.5.1 SLA는 협상 가능한 계약이다

소프트웨어의 성능 요구사항은 보통 고정되어 있다. AI 에이전트의 SLA는 **트레이드오프**다.

- 더 빠른 응답 → 더 작은 모델 → 더 낮은 품질
- 더 높은 정확도 → 더 많은 토큰 → 더 높은 비용

`SLAConfig`와 `InstructionConfig`를 함께 선언하면 이 트레이드오프를 명시적으로 관리할 수 있다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py — SLAConfig · InstructionConfig
# 트레이드오프 명시화: 빠른 응답을 위해 응답 길이 제한
@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(p95_ms=1000),              # 빠른 응답 SLA
    instructions=InstructionConfig(max_words=100),  # 짧은 응답으로 토큰 절감
)
def fast_agent(question: str, ground_truth: str = "") -> str:
    return fast_llm.invoke(question)         # haiku 같은 빠른 모델 사용
```

- `SLAConfig(p95_ms=1000)`과 `InstructionConfig(max_words=100)`을 함께 선언하면 응답 길이 제한이 지연 시간 단축으로 이어진다.
- 빠른 응답이 필요한 경우 Haiku 계열 모델로 전환해 비용과 지연을 동시에 줄일 수 있다.
- 이 트레이드오프를 코드로 명시하면 모델 변경 시 SLA 영향을 즉시 측정할 수 있다.

### 7.5.2 비용 예측 가능성과 드리프트

같은 에이전트라도 입력의 복잡도가 달라지면 비용이 달라진다. `CostPredictabilityConfig`로 비용 변동성을 모니터링하고, `agent-eval trend`로 시간에 따른 비용 추세를 추적한다.

> **비용 드리프트**란 처음 배포할 때와 비교해 시간이 지날수록 에이전트의 평균 비용이 조금씩 상승하는 현상이다. 사용자 질문이 점점 복잡해지거나, 컨텍스트가 누적되거나, 재시도가 늘어날 때 발생한다. `agent-eval trend`로 배포 이후 비용 기울기(slope)를 추적하고 임계값 초과 시 CI/CD에서 자동 경고한다.

```bash
# 비용 드리프트 탐지
agent-eval trend results/ --metric cost --window 30
# → 지난 30개 평가 결과의 비용 추세 분석
# → 기울기(slope)가 양수 + 임계값 초과 시 CI/CD 경고
```

---

## 7.6 실전 예제 파일

**기본 예제**: [`Evaluator_Examples/ch07_group_d.py`](../../Evaluator_Examples/ch07_group_d.py)
— LatencyTracker · TokenEconomyTracker · SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig 5개 Config · Gate D FAIL 시나리오

> **관련 챕터 예제**: Harness 전체 Gate 통합 흐름은 [Chapter 3 — `ch03_harness_basics.py`](Chapter_03_Harness_Engineering_기초.md)에서 확인한다.

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch07_group_d.py, 섹션 4 — Gate D Performance Contract
import time, random
from agent_evaluator import (
    SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
    TTFTVariabilityConfig, CostPredictabilityConfig,
)
from agent_evaluator.decorators import agent_eval

# ── SLAConfig: SLA 응답시간·비용 계약 선언 ──
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="d_sla",
    sla=SLAConfig(
        p95_ms=2000,
        p99_ms=5000,
        max_cost_per_task=0.01,
    ),
)
def sla_compliant_agent(question: str, ground_truth: str = "") -> str:
    """SLA 준수 에이전트 — 50~300ms 응답 시뮬레이션."""
    time.sleep(random.uniform(0.05, 0.3))
    return f"SLA 준수 응답: {question}"

# ── EfficiencyConfig: 비용 대비 완료율 기준 선언 ──
# task_type을 "data_analysis"로 분리해 CostPredictabilityConfig의 task_type별 CV 계산에서
# sla_compliant_agent("qa")와 독립적으로 측정되도록 한다.
@agent_eval(
    monitor,
    task_type="data_analysis",
    task_id_prefix="d_efficiency",
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=200,   # 완료 태스크당 200 토큰 이하 목표
        penalize_failed_tokens=True,
    ),
)
def efficient_agent(question: str, ground_truth: str = "") -> str:
    return f"효율적 답변: {question[:30]}"

# ── ResourceBudgetConfig: 개별 태스크 토큰·비용 상한 선언 ──
@agent_eval(
    monitor,
    task_type="reasoning",
    task_id_prefix="d_budget",
    resource_budget=ResourceBudgetConfig(
        max_tokens=1000,
        max_cost_usd=0.02,
        warn_at_pct=0.8,   # 80% 도달 시 WARN
    ),
)
def budget_aware_agent(question: str, ground_truth: str = "") -> str:
    return f"예산 내 응답: {question}"

# ── TTFTVariabilityConfig·CostPredictabilityConfig: monitor 수준 자동 집계 ──
# 이 두 Config는 @agent_eval 파라미터가 아닌 monitor 수준에서 자동 측정된다.
# extra 딕셔너리에 "ttft_ms" 값이 있으면 TTFTVariabilityConfig가 자동 집계한다.
_ttft_cfg = TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5)
_cost_cfg = CostPredictabilityConfig(max_coefficient_of_variation=0.3, min_samples=5)
```

- `SLAConfig`·`EfficiencyConfig`·`ResourceBudgetConfig`는 `@agent_eval` 파라미터로 선언하고, `TTFTVariabilityConfig`·`CostPredictabilityConfig`는 `PerformanceMonitor` 수준에서 자동 집계된다.
- `sla_compliant_agent`는 50~300ms 범위의 응답 시간을 시뮬레이션해 P95 기준을 충족하는 기본 케이스를 보여준다.
- `budget_aware_agent`의 `warn_at_pct=0.8`은 토큰 예산 80% 도달 시 WARN을 발생시켜 조기 경고를 제공한다.
- 다섯 Config를 모두 조합하면 Gate D의 시간·비용·안정성 세 계약을 완전히 커버할 수 있다.

```bash
python Evaluator_Examples/ch03_harness_basics.py          # Gate D 포함 전체
python Evaluator_Examples/ch01_first_eval.py    # LatencyTracker·TokenEconomy 예제
python Evaluator_Examples/ch04_group_a.py  # Gate D FAIL — 배포 차단 케이스
```

- `ch03_harness_basics.py`는 Group D를 포함한 Harness Gate 전체 기본 예제다.
- `ch01_first_eval.py`는 `LatencyTracker`와 `TokenEconomyTracker`를 직접 다루는 Layer 1 예제다.
- `ch04_group_a.py`의 시나리오 12에서는 TTFT 극단 분산과 ResourceBudget 초과로 Gate D FAIL 흐름을 재현한다.

---

## 7.7 이 챕터의 핵심 요약

| 지표/Config | 역할 | 핵심 파라미터 |
|------------|------|-------------|
| `LatencyTracker` | 응답 시간 퍼센타일 측정 | `latency_p50`, `latency_p90`, `latency_p95`, `latency_p99`, `ttft_p50` |
| `TokenEconomyTracker` | 토큰·비용 추적 | `total_tokens`, `avg_tokens_per_task`, `estimated_cost_usd` |
| `SLAConfig` | SLA 계약 선언 | `p95_ms`, `p99_ms`, `max_cost_per_task`, `fail_threshold` |
| `EfficiencyConfig` | 비용 대비 완료율 기준 | `cost_unit`, `target_cost_per_completion`, `fail_ratio` |
| `ResourceBudgetConfig` | 개별 태스크 리소스 상한 | `max_tokens`, `max_cost_usd`, `max_execution_time_ms` |
| `TTFTVariabilityConfig` | TTFT 변동성 기준 | `max_stddev_ms`, `max_p95_p50_ratio` |
| `CostPredictabilityConfig` | 비용 예측 가능성 기준 | `max_coefficient_of_variation`, `cost_metric` |

> 🔗 **다음 챕터**: Chapter 8 — Gate E: 보안경계  
> 외부 공격과 데이터 유출을 차단하는 5개 Tracker와 3개 Config를 완전히 이해한다. 패턴 매칭과 의미 기반 탐지 2계층 보안을 다룬다.
