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
> - **QA 관리자**: §7.1(개요) → §7.3(Config 5종 레퍼런스) → §7.4(에이전트 유형별 조합 패턴) 순서로 읽으면 "SLA·비용 기준을 어떻게 선언할지"를 빠르게 파악할 수 있습니다.  
> - **개발자**: §7.2(Tracker 상세) → §7.3(Config 5종 레퍼런스) → §7.4(에이전트 유형별 조합 패턴) 순서로 읽으면 `SLAConfig`, `ResourceBudgetConfig` 등을 바로 적용할 수 있습니다.

---

@@HTML_START@@
<div class="gw-box">
  <div class="gw-header">⚠️ Gate D가 없으면 생기는 일</div>
  <div class="gw-body">
    <p>개발 환경에서 P95 응답 시간 1.2초. 프로덕션 트래픽에서 P95 8.7초. SLA는 3초. 한 달 뒤 SLA 위반 보고서를 받는다. SLAConfig로 배포 전에 테스트 트래픽을 시뮬레이션했다면 조기에 발견할 수 있었다.</p>
    <div class="gw-case">
      <strong>사례 예시:</strong> 토큰 사용량 모니터링 없이 운영한 에이전트가 한 달에 예상의 5배를 소비. ResourceBudgetConfig의 max_tokens 설정 하나로 방지할 수 있었다.
    </div>
  </div>
</div>
@@HTML_END@@

---

## 7.1 Gate D 개요

Gate D는 에이전트가 **약속한 성능 계약(Performance Contract)**을 지키는지 측정한다. 에이전트가 아무리 정확해도(Gate A) 응답이 10초씩 걸리거나 태스크당 $1씩 비용이 나온다면 프로덕션에 배포할 수 없다.

> **Gate D = 성능 계약서를 코드로 선언한다**  
> `SLAConfig(p95_ms=2000)`는 단순한 설정값이 아니라 "P95 응답이 2초를 초과하면 배포 불가"라는 계약 조항이다. Harness Engineering에서 Gate D는 이 계약 조항들을 코드로 명문화하고, 매 평가마다 자동으로 준수 여부를 검증한다.

> **Gate A + Gate D — 모든 에이전트의 필수 기준선**  
> Gate A(Goal Achievement)는 "에이전트가 목표한 결과를 내는가"를 묻고, Gate D(Performance Contract)는 "그 결과가 적시에·적정 비용으로 나오는가"를 묻는다. 두 Gate는 항상 활성화된 baseline이다. Gate A 없이는 정확도를 보장할 수 없고, Gate D 없이는 비용·SLA를 보장할 수 없기 때문이다.

### Gate D가 다루는 3가지 계약

1. **시간 계약**: P95·P99 응답 시간이 SLA를 지키는가? (`SLAConfig`)
2. **비용 계약**: 태스크당 토큰·비용이 예산 내에 있는가? (`ResourceBudgetConfig`, `EfficiencyConfig`)
3. **안정성 계약**: 성능이 예측 가능하고 일관적인가? (`TTFTVariabilityConfig`, `CostPredictabilityConfig`)

### Tracker vs Config — Gate D 대비표

| 관점 | Tracker (측정) | Config (기준 선언) |
|------|--------------|------------------|
| 역할 | "실제 응답 시간·비용이 얼마인가?" | "이 수준이면 SLA를 지킬 수 있는가?" |
| 코드 위치 | `PerformanceMonitor` 내부 자동 | `@agent_eval` 데코레이터 파라미터 |
| 타이밍 | 런타임 매 호출 | 배포 전 계약 선언 |
| 예시 | `latency_p95=1.85s` | `SLAConfig(p95_ms=2000)` → "P95 2초 이내" |

---

## 7.2 Tracker 2종 심화

### 7.2.1 LatencyTracker — 응답 시간 퍼센타일

`LatencyTracker`는 에이전트 응답 시간을 퍼센타일 기반으로 측정한다. 평균 응답 시간이 아닌 P95·P99를 기준으로 하는 이유는 **"대부분의 사용자가 경험하는 최악의 응답 시간"**이 더 중요하기 때문이다.

> **왜 평균이 아닌 P95인가?**  
> 100건 요청 중 95건이 1초 내에 처리되고 5건이 20초씩 걸려도 평균은 약 2초로 "양호"해 보인다. 하지만 그 5건의 사용자는 20초를 기다린다. P95는 95번째로 느린 응답, 즉 "상위 5% 사용자가 경험하는 최악의 응답 시간"이다. SLA 계약에서 P95를 기준으로 삼는 이유가 여기에 있다.

**측정 항목** (`["efficiency_metrics"]["latency"]`)**:**

| 항목 | 설명 |
|------|------|
| `mean` | 평균 응답 시간 (초) |
| `median` | 중앙값 응답 시간 (초) |
| `p50` | P50 응답 시간 — 50번째 퍼센타일 (초) |
| `p90` | P90 응답 시간 — 상위 10% 지연 탐지 (초) |
| `p95` | P95 응답 시간 — SLA 계약 기준 (초) |
| `p99` | P99 응답 시간 — 극단적 지연 탐지, 미션 크리티컬 (초) |
| `min` | 최소 응답 시간 (초) |
| `max` | 최대 응답 시간 (초) |
| `std` | 응답 시간 표준편차 (초) |

TTFT(Time-to-First-Token) 통계는 `["efficiency_metrics"]["ttft"]`에 별도 집계된다 (`mean`, `p50`, `p95`, `p99`, `min`, `max`, `count`).

```python
# 개념 코드 — @agent_eval 기반 LatencyTracker 사용 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch07_group_d.py 참고)
from agent_evaluator import PerformanceMonitor, agent_eval
import time

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return f"응답: {question}"

# 태스크 실행 — 실제 환경에서는 운영 데이터셋으로 교체
test_dataset = [
    ("서울 인구는?", "약 950만 명"),
    ("파이썬 창시자는?", "귀도 반 로섬"),
    ("HTTP 상태코드 200은?", "요청 성공"),
]
for q, gt in test_dataset:
    agent(q, ground_truth=gt)

report = monitor.generate_report()
d = report.to_dict()
lat = d.get("efficiency_metrics", {}).get("latency", {})
print(f"P50 응답 시간: {lat.get('p50', 0) * 1000:.0f}ms")  # → 0ms (mock 함수 오버헤드 수준)
print(f"P95 응답 시간: {lat.get('p95', 0) * 1000:.0f}ms")  # → 0ms
print(f"P99 응답 시간: {lat.get('p99', 0) * 1000:.0f}ms")  # → 0ms
```

> **채점 경로 — 세 퍼센타일이 모두 0ms인 이유**
>
> mock 함수(`return f"응답: {question}"`)는 측정 오버헤드 수준(< 1ms)으로 반환하므로 P50/P95/P99 모두 0ms로 출력된다. `LatencyTracker` 자체는 정상 동작 중이며, 실제 LLM 에이전트를 연결하면 500ms~5000ms 범위의 의미 있는 퍼센타일이 집계된다.
>
> | 단계 | 판정 | 값 |
> |------|------|----|
> | 태스크 수 | 3건 | 퍼센타일 추정치 불안정 (최소 20건 권장) |
> | 실행 시간 | mock 함수 즉시 반환 | < 1ms → 반올림 후 **0ms** |
> | P95 기준 | 3건 중 상위 5% | 3번째 값 ≈ 0ms |
>
> 이상치가 포함된 현실적 분포는 아래 "이상치 포함 예제"를 참고한다.

- `@agent_eval`로 감싼 함수는 실행 시간이 자동으로 `LatencyTracker`에 기록된다.
- `generate_report()`를 호출하면 P50·P95·P99 퍼센타일이 계산된다.
- `p95`는 SLA 위반 여부를 판단하는 핵심 지표다 (`efficiency_metrics["latency"]["p95"]`).
- 태스크 수가 적을수록 퍼센타일 추정치가 불안정하므로 최소 20건 이상 실행을 권장한다.

**P50/P90/P95/P99 선택 가이드:**

| 지표 | 의미 | 권장 SLA 기준 |
|------|------|-------------|
| P50 | 절반의 사용자 경험 | 내부 대시보드 모니터링 |
| P90 | 상위 10% 지연 탐지 | 중간 수준 서비스 모니터링 |
| P95 | 95% 사용자 경험 | 외부 SLA 계약 기준 (일반적) |
| P99 | 99% 사용자 경험 | 미션 크리티컬 서비스 |

**이상치가 P95/P99에 미치는 영향:**

프로덕션 트래픽에는 간헐적 타임아웃·재시도 등 극단값이 섞인다. 평균과 P50은 이상치에 둔감하지만 P95·P99는 민감하게 반응한다.

```python
# 출처: Evaluator_Examples/ch07_group_d.py — 섹션 추가A (이상치 포함 분포)
import random
from agent_evaluator import PerformanceMonitor, create_taskresult

_monitor_lat = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

# 정규 분포(평균 1.2s, 표준편차 0.4s)에 이상치(8.5s, 12.0s) 2건 추가
latencies = [random.gauss(1.2, 0.4) for _ in range(15)] + [8.5, 12.0]
latencies = [max(0.1, lat) for lat in latencies]

for i, lat in enumerate(latencies):
    result = create_taskresult(
        task_id=f"lat_{i:03d}",
        question="지연시간 측정용 쿼리",
        response="응답 완료",
        ground_truth="응답",
        execution_time=round(lat, 3),
        task_type="qa",
    )
    _monitor_lat.record_task(result)

rep = _monitor_lat.generate_report().to_dict().get("efficiency_metrics", {}).get("latency", {})
print(f"p50={rep.get('p50', 0):.2f}s  p95={rep.get('p95', 0):.2f}s  p99={rep.get('p99', 0):.2f}s")
# → p50=1.38s  p95=9.20s  p99=11.44s  ← 이상치 2건이 P95/P99를 크게 끌어올림
# (random.gauss 사용으로 실행마다 수치가 달라지나, 이상치 효과 방향은 동일)
```

> **채점 경로 — P95·P99가 P50보다 6~8배 높은 이유**
>
> `random.gauss(1.2, 0.4)`로 생성된 15건의 정규 분포 데이터에 8.5s·12.0s 이상치 2건을 추가하면 전체 17건 중 상위 5%(P95), 1%(P99)에 이상치가 포함된다.
>
> | 구간 | 데이터 | 퍼센타일 |
> |------|--------|---------|
> | 정규 분포 15건 | ~0.5s~2.0s | P50 ≈ 1.38s |
> | 이상치 2건 (8.5s, 12.0s) | 17건 중 상위 11~12% | P95·P99에 반영 |
>
> `17건 × 5% = 0.85` → P95는 정수 인덱스 반올림으로 이상치 값 구간에 걸린다. 데이터 1~2건의 이상치로도 P95/P99가 수 배 상승하므로, SLA를 P95 기준으로 선언할 때는 이상치 제거 또는 충분한 샘플 확보가 중요하다.

- `p50`(중앙값)은 약 1.38초로 대다수 요청의 실제 응답 시간과 유사하다.
- `p95`·`p99`는 이상치 2건(8.5s, 12s) 때문에 9~11초로 급등한다 — 이것이 SLA를 **P95 기준**으로 선언해야 하는 이유다.
- `create_taskresult`로 직접 데이터를 주입하면 현실적인 지연 분포를 시뮬레이션할 수 있다.

**TTFT (Time-to-First-Token) 추적:**

스트리밍 응답 에이전트에서 첫 토큰까지의 대기 시간을 별도로 측정한다.

```python
# 개념 코드 — 스트리밍 에이전트에서 TTFT 자동 기록 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch07_group_d.py 참고)
from agent_evaluator import agent_eval

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

> 👨‍💻 **개발자 TIP**: `@agent_eval`로 함수를 감싸면 실행 시간이 자동으로 `LatencyTracker`에 기록된다. 별도 코드가 필요 없다. 단, `SLAConfig`를 설정하지 않으면 측정만 수행되고 Gate D 판정 점수에는 반영되지 않는다. 퍼센타일 신뢰도를 위해 최소 20건 이상의 태스크를 실행한 뒤 `generate_report()`를 호출하는 것이 권장된다.

> 📋 **QA 관리자 TIP**: P95 응답 시간 기준 서비스별 권장 임계값 — 실시간 챗봇: `1500ms` / 일반 응답 서비스: `3000ms` / 배치 처리: `30000ms`. `fail_threshold`를 넘는 위반 건수가 쌓이는 순간 Gate D가 FAIL 처리된다.
> - 판단 기준: P95 ≤ 1초 🟢 즉각적 → 3초 🟡 허용 → 10초 🟠 느림 → 초과 🔴 배포 금지 검토
> - Gate D 점수 확인: `details.get("p95_latency_s")` (단위: 초)

### 7.2.2 TokenEconomyTracker — 토큰 사용량·비용 추정

토큰 사용량을 추적하고 LLM API 비용을 자동으로 추정한다.

**측정 항목** (`["efficiency_metrics"]["tokens"]`)**:**

| 항목 | 설명 |
|------|------|
| `total_tokens` | 전체 토큰 사용량 (input + output 합계) |
| `total_input_tokens` | 입력 토큰 총 사용량 |
| `total_output_tokens` | 출력 토큰 총 사용량 |
| `total_cost` | 전체 추정 비용 (USD) |
| `avg_tokens_per_task` | 태스크당 평균 토큰 수 |
| `avg_cost_per_task` | 태스크당 평균 비용 (USD) |
| `estimated_monthly_cost` | 월간 추정 비용 (USD, 30일 기준) |
| `token_distribution` | 입출력 토큰 비율 (`input_ratio`, `output_ratio`) |
| `cost_percentiles` | 비용 퍼센타일 (`p50`, `p90`, `p95`) |

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 추가B (단일 태스크 단순화)
from agent_evaluator import PerformanceMonitor, create_taskresult

# PerformanceMonitor 기본 단가: Claude Sonnet 4.5 기준 ($3/$15 per 1M)
# 단가를 바꾸려면 PerformanceMonitor(pricing={"input": 0.0008, "output": 0.004}) 처럼 지정
monitor = PerformanceMonitor(output_dir="results/")

result = create_taskresult(
    task_id="t1",
    question="인공지능이란?",
    response="인공지능은...",
    execution_time=1.2,
    task_type="qa",
    tokens_used={
        "input": 150,
        "output": 300,
        "model": "claude-haiku-4-5-20251001",   # 추적용 메타데이터 — 단가 계산에는 영향 없음
    },
)
monitor.record_task(result)

report = monitor.generate_report()
d = report.to_dict()
tok = d.get("efficiency_metrics", {}).get("tokens", {})
print(f"총 토큰: {tok.get('total_tokens', 0):,}")              # → 450
print(f"태스크당 평균: {tok.get('avg_tokens_per_task', 0):.0f} 토큰")  # → 450
print(f"총 비용: ${tok.get('total_cost', 0):.4f}")             # → $0.0049 (기본 단가 기준)
print(f"태스크당 평균 비용: ${tok.get('avg_cost_per_task', 0):.4f}")   # → $0.0049
```

> **채점 경로 — `tokens_used` 형식 주의 & 단가 결정 방식**
>
> `TokenEconomyTracker`는 `tokens_used`를 `dict.get("input", 0)` 방식으로 읽는다. **정수**(`tokens_used=450`)를 전달하면 `.get()` 호출에서 `AttributeError`가 발생해 `record_task()`가 실패한다 — 반드시 `{"input": N, "output": M}` dict 형식을 사용해야 한다.
>
> | 형식 | total_tokens | total_cost |
> |------|-------------|-----------|
> | `tokens_used=450` (정수) | ❌ AttributeError 발생 | (집계 불가) |
> | `tokens_used={"input": 150, "output": 300}` | **450** | **$0.0049** |
>
> 비용 계산 (기본 단가 Claude Sonnet 4.5: $3/$15 per 1M):
> ```
> input:  150 × $3.00/1M  = 150/1000 × $0.003 = $0.00045
> output: 300 × $15.00/1M = 300/1000 × $0.015 = $0.00450
> total:  $0.00495 ≈ $0.0049
> ```
> **모델별 단가를 반영하려면** `PerformanceMonitor(pricing={"input": 0.0008, "output": 0.004})` 처럼 생성 시 지정한다. `tokens_used["model"]`은 추적용 메타데이터이며 단가 계산에 영향을 주지 않는다.

- `tokens_used={"input": N, "output": M}` 형태로 전달해야 `TokenEconomyTracker`가 입출력 토큰을 분리 집계한다.
- `model` 필드가 없으면 `"default"` 모델로 집계된다 — 입출력 분리는 `input`·`output` 키에 의존하며 `model` 키 유무와 무관하다.
- `total_cost`는 참고용 추정치이며, 실제 청구 금액과 다를 수 있다.
- 여러 모델을 혼용할 경우 각 태스크에 `model` 필드를 명시해야 정확한 비용이 집계된다.

**모델별 비용 참고 (2026년 4월 기준):**

| 모델 | Input (1M 토큰) | Output (1M 토큰) |
|------|----------------|-----------------|
| claude-haiku-4-5 | $0.80 | $4.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4o | $2.50 | $10.00 |

> 👨‍💻 **개발자 TIP**: `tokens_used={"input": N, "output": M}` dict 형식이 필수다. 정수(`tokens_used=450`)로 전달하면 `record_task()` 호출 시 `AttributeError`가 발생한다. 단가 변경은 `PerformanceMonitor(pricing={"input": 0.0008, "output": 0.004})`처럼 생성 시 지정하며, `tokens_used["model"]` 필드는 추적용 메타데이터로 단가에는 영향을 주지 않는다.

> 📋 **QA 관리자 TIP**: 태스크당 평균 비용은 `avg_cost_per_task`, 30일 기준 월간 추정 비용은 `estimated_monthly_cost`로 확인한다. 비용이 예상보다 높아지면 `agent-eval trend results/`로 비용 추세를 분석하고, `CostPredictabilityConfig`의 CV 값을 함께 점검한다.
> - 비용 이상 신호: `avg_cost_per_task`가 전월 대비 20% 이상 상승 시 원인 파악
> - 권장 확인 주기: 배포 후 3일 · 7일 · 30일

---

## 7.3 Config 5종 레퍼런스

### 7.3.1 SLAConfig — SLA 준수 선언

응답 시간과 비용에 대한 SLA(Service Level Agreement)를 코드로 선언한다. **Gate D의 핵심 Config**다.

> **SLAConfig = SLA 계약서를 코드로**  
> 전통적 SLA는 문서로만 존재한다. `SLAConfig(p95_ms=2000, fail_threshold=5)`는 "P95 응답이 2초 초과 위반이 5건을 넘으면 Gate D를 fail 처리한다"는 계약 조항을 코드로 명문화한 것이다. 매 배포 전 평가에서 이 계약 조항이 자동으로 검증된다.

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 4 (SLAConfig 파라미터 전체 레퍼런스)
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

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `p95_ms` | `float` | `5000.0` | P95 응답 시간 상한 (밀리초) |
| `p99_ms` | `float` | `10000.0` | P99 응답 시간 상한 (밀리초) |
| `ttft_ms` | `float\|None` | `None` (검사 안 함) | TTFT 상한 — 스트리밍 에이전트 전용 |
| `breach_window` | `int` | `10` | 위반 판정 슬라이딩 윈도우 크기 |
| `warn_threshold` | `int` | `2` | 윈도우 내 N건 위반 시 경고 |
| `fail_threshold` | `int` | `5` | 윈도우 내 N건 위반 시 fail |
| `max_cost_per_task` | `float\|None` | `None` (제한 없음) | 태스크당 최대 비용 (USD) |
| `budget_usd` | `float\|None` | `None` (제한 없음) | 세션 전체 최대 비용 (USD) |
| `token_limit` | `int\|None` | `None` (제한 없음) | 태스크당 최대 허용 토큰 수 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `p95_ms` | `5000.0` | 실시간 챗봇: `1500` / 일반 응답: `3000` / 배치: `30000` |
| `fail_threshold` | `5` | 엄격한 SLA: `2~3` / 초기 테스트: `5` 유지 |
| `ttft_ms` | `None` | 스트리밍 챗봇: `500` 설정 권장 |

**서비스 유형별 SLAConfig 예시:**

```python
# 개념 코드 — 서비스 유형별 SLAConfig 선언 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch07_group_d.py 참고)
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

> **채점 경로 — sla_breach_rate 산출 경로**
>
> 각 태스크 실행 후 `execution_time × 1000`이 `p95_ms`와 비교되어 위반 여부가 자동 기록된다. `generate_report()` 시점에 모든 태스크의 결과를 집계해 아래 지표를 산출한다.
>
> | 평가 단위 | 반환 키 | 설명 |
> |---------|--------|------|
> | 태스크 단위 | `sla_met` (bool) | `execution_time × 1000 ≤ p95_ms`이면 `True` |
> | 태스크 단위 | `breaches` (list) | 위반 항목: `["latency 3200ms > p95 2000ms"]` 형식 |
> | 세션 집계 | `breach_rate` | 위반 태스크 수 / 전체 태스크 수 |
>
> | `breach_rate` 결과 | Gate 영향 |
> |--------------------|---------|
> | 0 | Gate D·C 최고 기여 |
> | `≥ warn_threshold / window` | Gate D 경고 |
> | `≥ fail_threshold / window` | Gate D FAIL |
>
> `SLAConfig`는 `@agent_eval` 파라미터로 선언하지만, **Gate D 점수는 `LatencyTracker`의 실측 P95 데이터가 있어야 산출**된다.
>
> ```python
> # 결과 접근 경로
> details = report.to_dict()["extra_metrics"]["harness_groups"]["D"]["details"]
> # details["p95_latency_s"]  — 실측 P95 지연 시간 (초)
> # details["insufficient_data_warnings"]  — 데이터 부족 경고 목록
> ```

> **SLAConfig의 이중 Gate 기여**  
> `SLAConfig`는 Gate D(성능계약)의 Config이지만, 내부적으로 SLA 위반율(`breach_rate`)은 **Gate C(신뢰성) 점수에도 반영**된다. PerformanceMonitor의 Gate 집계 단계에서 `1 − breach_rate` 값이 Gate C 신뢰성 점수에 포함되는 것이다. SLA를 자주 위반하는 에이전트는 "신뢰할 수 없다"는 관점에서 Gate C 점수도 낮아질 수 있다. Gate D와 Gate C를 함께 검토할 때 이 점을 참고한다.

> 👨‍💻 **개발자 TIP**: Gate D score는 `SLAConfig` 단독으로 산출되지 않는다. `LatencyTracker`의 실측 P95 데이터가 있어야 Gate D 점수가 계산된다. `breach_window=10` 슬라이딩 윈도우는 최근 10건 기준이므로, 초기 테스트 시 10건을 채우기 전에는 위반 카운트가 불안정할 수 있다. `SLAConfig`와 `ResourceBudgetConfig`를 함께 사용하면 통계·개별 태스크 두 계층을 동시에 통제할 수 있다.

> 📋 **QA 관리자 TIP**: SLA 위반율(`breach_rate`)은 Gate D뿐만 아니라 Gate C(신뢰성) 점수에도 영향을 준다. `fail_threshold` 초과 시 배포를 차단하고 응답 시간 병목(DB 쿼리, 외부 API 지연, LLM 로드)을 즉각 조사한다.
> - 권장 임계값: 챗봇 `p95_ms=2000` / API 백엔드 `p95_ms=1500` / 배치 `p95_ms=30000`
> - 경보 기준: `fail_threshold` 초과 시 → 즉각 배포 차단 / `warn_threshold` 초과 시 → 원인 파악 시작

### 7.3.2 EfficiencyConfig — 비용 대비 완료율

토큰/비용 대비 실제 완료율(ROI)을 측정한다. "돈을 쓴 만큼 가치가 나왔는가?"를 평가한다.

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 4 (EfficiencyConfig 파라미터 전체 레퍼런스)
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
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 4 (task_type·target 값 단순화)
from agent_evaluator import PerformanceMonitor, agent_eval, EfficiencyConfig

monitor = PerformanceMonitor(output_dir="results/")

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
    # TODO(현업 적용): 아래를 실제 LLM 호출로 교체하세요.
    #   예) return llm.invoke(question)  # LangChain 등 초기화된 클라이언트 사용
    return f"응답: {question}"

agent("서울 인구는?", ground_truth="약 950만 명")

report = monitor.generate_report().to_dict()
details = (report.get("extra_metrics") or {}).get("harness_groups", {}).get("D", {}).get("details", {})
print(f"효율성 점수: {details.get('avg_efficiency_ratio', 'N/A')}")
# → 효율성 점수: N/A (mock 함수는 EvalMetadata(tokens_used=...) 미주입 — 실제 LLM 연결 시 측정됨)
```

- `target_cost_per_completion`에 목표 토큰 수를 설정하면, 실제 완료 비용이 이를 초과하는 비율을 추적한다.
- `penalize_failed_tokens=True`는 실패 태스크도 비용으로 산정해 재시도 남용을 억제한다.
- `warn_ratio=2.0`이면 목표 대비 2배 초과 시 경고, `fail_ratio`에 도달하면 Gate D가 fail이 된다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `cost_unit` | `str` | `"tokens"` | 비용 단위: `"tokens"` `"usd"` `"time_ms"` |
| `target_cost_per_completion` | `float\|None` | `None` (목표 없음) | 완료 태스크당 목표 비용 |
| `penalize_failed_tokens` | `bool` | `True` | 실패 태스크 토큰도 비용으로 산정 |
| `warn_ratio` | `float` | `2.0` | 목표 대비 N배 초과 시 경고 |
| `fail_ratio` | `float` | `4.0` | 목표 대비 N배 초과 시 fail |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `target_cost_per_completion` | `None` | 챗봇: `800 tokens` / 분석: `2000 tokens` / 보고서: `5000 tokens` |
| `warn_ratio` | `2.0` | 비용 민감 서비스: `1.5` / 일반: `2.0` |
| `fail_ratio` | `4.0` | 비용 민감 서비스: `3.0` / 일반: `4.0` |

> **채점 경로 — avg_efficiency_ratio 산출 경로**
>
> `target_cost_per_completion`을 기준으로 실제 비용(토큰 수 또는 USD)을 비교해 비율을 계산한다.
>
> | 조건 | `efficiency_score` |
> |------|------------------|
> | 실제 비용 ≤ `target` | **1.0** |
> | 실제 비용 ≤ `target × warn_ratio` | **0.7** (경고) |
> | 실제 비용 ≤ `target × fail_ratio` | **0.3** (위험) |
> | 실제 비용 > `target × fail_ratio` | **0.0** (fail) |
> | `target_cost_per_completion=None` | 목표 미선언 → 집계 없음 |
>
> 결과 접근: `report.to_dict()["extra_metrics"]["harness_groups"]["D"]["details"].get("avg_efficiency_ratio")`

> 👨‍💻 **개발자 TIP**: `target_cost_per_completion=None`이면 `EfficiencyConfig`는 집계 없이 통과된다 — 반드시 목표 토큰 수를 설정해야 의미 있는 판정이 이뤄진다. mock 함수는 `EvalMetadata(tokens_used=...)` 미주입 시 `avg_efficiency_ratio`가 `N/A`로 나오는 것이 정상이며, 실제 LLM을 연결해야 측정된다.

> 📋 **QA 관리자 TIP**: `efficiency_score` 해석 기준 — `1.0` = 목표 달성 / `0.7` = 경고(목표 2배 초과) / `0.3` = 위험 / `0.0` = Gate D FAIL. 비용 민감 서비스는 `fail_ratio=3.0`으로 낮춰 더 엄격하게 통제한다.
> - 서비스별 권장 `target_cost_per_completion`: 챗봇 `800 tokens` / 분석 에이전트 `2000 tokens` / 보고서 생성 `5000 tokens`
> - `avg_efficiency_ratio`가 지속적으로 0.7 이하이면 토큰 절약형 프롬프트 최적화 또는 모델 변경 검토

### 7.3.3 ResourceBudgetConfig — 리소스 예산 상한

개별 태스크 수준에서 토큰·비용·실행시간의 하드 상한을 설정한다. `SLAConfig`가 통계적 위반을 탐지한다면, `ResourceBudgetConfig`는 개별 태스크의 폭주를 즉시 차단한다.

> **비용 초과 시 자동 차단의 비즈니스적 의미**  
> `ResourceBudgetConfig(max_cost_usd=0.05)`는 단일 태스크가 $0.05를 초과하면 Gate D를 fail 처리한다. "에이전트 한 번 호출에 $5가 청구되는" 사고를 배포 전에 막는 안전망이다. 프로덕션에서 이런 폭주는 LLM 무한 루프, 컨텍스트 누적, 재시도 남용에서 발생한다.

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py (ResourceBudgetConfig 파라미터 전체 레퍼런스)
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
# 기반 코드 — SLAConfig + ResourceBudgetConfig 조합 패턴 (값 단순화)
# 둘 다 사용하는 것이 권장
from agent_evaluator import PerformanceMonitor, agent_eval, SLAConfig, ResourceBudgetConfig

monitor = PerformanceMonitor(output_dir="results/")

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
    # TODO(현업 적용): 아래를 실제 LLM 호출로 교체하세요.
    #   예) return llm.invoke(question)  # LangChain 등 초기화된 클라이언트 사용
    return f"응답: {question}"

agent("서울 인구는?", ground_truth="약 950만 명")

report = monitor.generate_report().to_dict()
details = (report.get("extra_metrics") or {}).get("harness_groups", {}).get("D", {}).get("details", {})
print(f"예산 점수: {details.get('avg_budget_score', 'N/A')}")
# → 예산 점수: N/A (mock 함수는 EvalMetadata(tokens_used=...) 미주입 — 실제 LLM 연결 시 측정됨)
```

- `SLAConfig`는 전체 통계적 추세를, `ResourceBudgetConfig`는 개별 태스크 수준을 통제하므로 두 Config를 함께 사용하는 것이 권장된다.
- `warn_at_pct=0.75`이면 예산의 75%에 도달했을 때 미리 경고해 조기 대응이 가능하다.
- `max_execution_time_ms`는 개별 태스크 하드 상한으로, 무한 루프나 타임아웃 미설정 LLM 호출로부터 보호한다.

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_tokens` | `int\|None` | `None` (제한 없음) | 태스크당 최대 토큰 수 |
| `max_cost_usd` | `float\|None` | `None` (제한 없음) | 태스크당 최대 비용 (USD) |
| `max_execution_time_ms` | `float\|None` | `None` (제한 없음) | 태스크당 최대 실행 시간 (밀리초) |
| `warn_at_pct` | `float` | `0.8` | 예산의 N% 도달 시 사전 경고 |
| `count_failed_tokens` | `bool` | `True` | 실패 태스크 토큰도 예산에 포함 |
| `rollover` | `bool` | `False` | 미사용 예산을 다음 태스크로 이월 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `max_tokens` | `None` | 챗봇: `1500` / 분석 에이전트: `4000` / 배치: `제한 없음` |
| `warn_at_pct` | `0.8` | 조기 경고 필요 시 `0.7`로 낮춤 |
| `max_execution_time_ms` | `None` | 개별 태스크 하드 상한: SLA p99 값으로 설정 권장 |

> **채점 경로 — avg_budget_score 산출 경로**
>
> 설정된 각 상한(`max_tokens`, `max_cost_usd`, `max_execution_time_ms`)에 대해 활용률을 계산하고, **가장 높은 활용률**로 `budget_score`를 결정한다.
>
> ```
> token_util   = tokens_used / max_tokens       (미설정 시 제외)
> cost_util    = cost_usd / max_cost_usd         (미설정 시 제외)
> time_util    = elapsed_ms / max_execution_time_ms  (미설정 시 제외)
>
> budget_score = max(0.0, 1.0 − max(token_util, cost_util, time_util))
> ```
>
> | 최대 활용률 | `budget_score` |
> |-----------|--------------|
> | 50% (0.5) | **0.5** |
> | 100% (1.0) | **0.0** (예산 초과) |
> | 150% (1.5) | **0.0** (초과, `over_budget=True`) |
>
> 예: `tokens_used=1500, max_tokens=1000` → `token_util=1.5` → `budget_score=max(0, 1-1.5)=0.0`.  
> 결과 접근: `report.to_dict()["extra_metrics"]["harness_groups"]["D"]["details"].get("avg_budget_score")`

> 👨‍💻 **개발자 TIP**: `max_tokens`, `max_cost_usd`, `max_execution_time_ms` 중 하나만 설정해도 동작한다. `warn_at_pct=0.8`(기본값)은 예산의 80%에서 경고를 발생시키는데, 프로덕션에서는 `0.7`로 낮춰 조기 경보를 확보하는 것이 권장된다. `rollover=True`로 미사용 예산을 다음 태스크로 이월하면 배치 처리 시 비용 최적화가 가능하다.

> 📋 **QA 관리자 TIP**: `budget_score = 0.0`이면 단일 태스크가 예산 상한을 초과했다는 의미로 즉각 조치가 필요하다. 이는 LLM 무한 루프, 컨텍스트 누적, 재시도 남용에서 발생한다.
> - 권장 설정: 챗봇 `max_tokens=1500` / 분석 에이전트 `max_tokens=4000` / 미션 크리티컬 `max_execution_time_ms`=SLA p99 값
> - 경보 기준: `over_budget=True` 태스크가 1건이라도 발생하면 원인 분석 시작

### 7.3.4 TTFTVariabilityConfig — TTFT 변동성

첫 토큰까지의 대기 시간(TTFT) 변동성을 측정한다. 스트리밍 에이전트에서 사용자 체감 품질에 직접 영향을 준다.

> **monitor 수준 자동 집계**: `TTFTVariabilityConfig`는 `@agent_eval` 데코레이터 파라미터로 전달하지 않는다. PerformanceMonitor의 세션 집계 단계에서 세션 전체의 `ttft_ms` 데이터를 자동으로 수집·집계해 판정한다. 개별 `TaskResult`가 아닌 **모니터 전체 집계** 수준에서 동작한다.

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py (TTFTVariabilityConfig 파라미터 전체 레퍼런스)
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

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_stddev_ms` | `float` | `500.0` | TTFT 표준편차 허용 상한 (밀리초) |
| `max_p95_p50_ratio` | `float` | `3.0` | P95/P50 비율 상한 (3배 이상 = 변동성 높음) |
| `min_samples` | `int` | `5` | 통계에 필요한 최소 샘플 수 |
| `remove_outliers` | `bool` | `True` | 극단적 이상치 제거 후 계산 |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `max_stddev_ms` | `500.0` | 챗봇(엄격): `200` / 일반: `500` |
| `max_p95_p50_ratio` | `3.0` | 안정적 서비스: `2.0` / 허용적: `3.0` |
| `min_samples` | `5` | 신뢰성 있는 통계: `10` 이상 권장 |

> **채점 경로 — ttft_variability_score 산출 경로**
>
> 세션 전체 `ttft_ms` 데이터가 자동 집계되어 표준편차·P95/P50 비율을 산출한다. `@agent_eval` 파라미터가 아닌 `PerformanceMonitor(ttft_variability_config=TTFTVariabilityConfig(...))` 로 설정한다.
>
> | 조건 | Gate D 기여 |
> |------|-----------|
> | `stddev ≤ max_stddev_ms` 및 `p95/p50 ≤ max_p95_p50_ratio` | 점수 1.0 |
> | `stddev > max_stddev_ms` 또는 비율 초과 | 점수 감소 |
> | `sample_count < min_samples` | `insufficient_data_warnings` 기록, 판정 보류 |
>
> TTFT 데이터는 `ttft_seconds` 인자로 `@agent_eval`에 전달하거나 스트리밍 에이전트에서 자동 수집된다.

> 👨‍💻 **개발자 TIP**: `TTFTVariabilityConfig`는 `@agent_eval` 파라미터가 아닌 `PerformanceMonitor(ttft_variability_config=TTFTVariabilityConfig(...))` 으로 설정한다. TTFT 데이터는 `EvalMetadata(extra={"ttft_ms": X})`를 반환하거나 스트리밍 generator를 반환하면 자동 수집된다. `min_samples` 미달 시 판정이 보류되고 `insufficient_data_warnings`에 기록된다.

> 📋 **QA 관리자 TIP**: TTFT stddev가 `max_stddev_ms`를 초과하면 Gate D 점수가 감소한다. TTFT 변동 급증은 백엔드 부하 증가나 재시도 증가의 조기 신호일 수 있다.
> - 권장 임계값: 스트리밍 챗봇 `max_stddev_ms=200` / 일반 서비스 `max_stddev_ms=500`
> - 경보 기준: `p95/p50 비율 > max_p95_p50_ratio` 초과 시 응답 시간 불균형 원인 파악

### 7.3.5 CostPredictabilityConfig — 비용 예측 가능성

동일 `task_type` 내 비용의 변동 계수(CV, Coefficient of Variation)를 측정한다. 비용이 예측 가능하게 안정적인지를 평가한다.

> **monitor 수준 자동 집계**: `CostPredictabilityConfig`도 `@agent_eval` 파라미터가 아닌 PerformanceMonitor의 세션 집계 단계에서 task_type별로 자동 집계된다. 세션 전체의 토큰·비용 데이터를 모아 CV를 산출한다.

> **프로덕션 운영에서 비용 예측 가능성이 중요한 이유**  
> 월 예산이 $500인 에이전트가 어떤 날은 $10, 어떤 날은 $200을 쓴다면 재무 계획이 불가능하다. CV가 낮다는 것은 동일한 task_type에서 비용이 안정적으로 유지된다는 의미다. CV가 갑자기 높아지면 "입력 복잡도가 달라졌다", "재시도가 증가했다" 같은 운영 이상의 신호일 수 있다.

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 4 (CostPredictabilityConfig 파라미터 전체 레퍼런스)
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

**파라미터 레퍼런스:**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `max_coefficient_of_variation` | `float` | `0.3` | CV 허용 상한 (0.3 = 30% 변동성) |
| `outlier_multiplier` | `float` | `3.0` | IQR 기반 이상치 제거 기준 (IQR × N 초과 시 제거) |
| `min_samples` | `int` | `5` | 통계에 필요한 최소 샘플 수 |
| `cost_metric` | `str` | `"tokens"` | 비용 측정 단위: `"tokens"` `"usd"` `"time_ms"` |

**임계값 가이드:**

| 항목 | 기본값 | 권장 기준 |
|------|--------|---------|
| `max_coefficient_of_variation` | `0.3` | 재무 계획 가능: `0.2` / 일반 허용: `0.3` / 느슨한: `0.5` |
| `cost_metric` | `"tokens"` | 달러 기준 예산 관리 시 `"usd"`로 변경 |
| `min_samples` | `5` | 신뢰성 있는 통계: `10` 이상 권장 |

> **채점 경로 — avg_cost_predictability 산출 경로**
>
> `task_type`별 비용 데이터가 자동 집계되어 CV(변동 계수)를 산출한다. `@agent_eval` 파라미터가 아닌 `PerformanceMonitor(cost_predictability_config=CostPredictabilityConfig(...))` 로 설정한다.
>
> ```
> CV = 표준편차(비용) / 평균(비용)
>
> CV ≤ max_coefficient_of_variation  → Gate D 기여: 1.0
> CV > max_coefficient_of_variation  → Gate D 기여: max(0, 1 - CV)
> ```
>
> | CV | 의미 | `cost_predictability_score` |
> |----|------|-----------------------------|
> | 0.1 | 매우 안정적 | 1.0 |
> | 0.3 (기본 임계값) | 허용 수준 | 1.0 (임계값 이하) |
> | 0.5 | 변동성 높음 | 감소 |
> | 1.0 이상 | 매우 불안정 | 0.0 |
>
> 결과 접근: `report.to_dict()["extra_metrics"]["harness_groups"]["D"]["details"].get("avg_cost_predictability")`

**CV(변동 계수) 해석:**

```
CV = 표준편차 / 평균

CV = 0.1  → 매우 예측 가능한 비용 (±10% 수준)
CV = 0.3  → 허용 가능한 변동 (기본 임계값)
CV = 0.5  → 높은 변동 — 복잡도가 다른 태스크 혼재
CV > 0.8  → 매우 불규칙 — 비용 예산 계획 불가
```

> 👨‍💻 **개발자 TIP**: `CostPredictabilityConfig`도 `@agent_eval` 파라미터가 아닌 `PerformanceMonitor(cost_predictability_config=CostPredictabilityConfig(...))` 으로 설정한다. CV는 `task_type`별로 독립 측정되므로, 성격이 다른 태스크는 `task_type`을 분리해야 정확한 CV가 산출된다. `min_samples` 미달 시 판정이 보류되고 `insufficient_data_warnings`에 기록된다.

> 📋 **QA 관리자 TIP**: CV 해석 기준 — `0.2 이하` = 매우 안정적(재무 계획 가능) / `0.3` = 허용(기본 임계값) / `0.5 이상` = 주의 / `0.8 이상` = 비용 예산 계획 불가. CV 급증은 입력 복잡도 증가, 재시도 급증, 컨텍스트 누적의 운영 이상 신호다.
> - 모니터링: `agent-eval trend results/`로 비용 CV 추세 추적
> - 경보 기준: CV `0.5` 초과 시 `task_type`별 비용 분포 즉시 점검

---

## 7.4 조합 패턴 — 에이전트 유형별 추천 구성

### 패턴 1 — 실시간 챗봇 (저지연 중심)

```python
# 기반 코드 — 실시간 챗봇 에이전트 SLAConfig · ResourceBudgetConfig · EfficiencyConfig 조합
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    SLAConfig, ResourceBudgetConfig, EfficiencyConfig,
)

monitor = PerformanceMonitor(output_dir="results/")

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
    # TODO(현업 적용): 아래를 실제 LLM 호출로 교체하세요.
    #   예) return llm.invoke(question)  # LangChain 등 초기화된 클라이언트 사용
    return f"응답: {question}"
```

- `SLAConfig(p95_ms=1500)`은 챗봇에서 95%의 사용자가 1.5초 이내에 응답을 받아야 함을 선언한다.
- `ttft_ms=500`으로 스트리밍 첫 토큰이 0.5초 이내에 출력되도록 요구해 체감 응답성을 높인다.
- `ResourceBudgetConfig(max_tokens=1500)`은 응답 길이가 짧도록 유도해 지연 시간과 비용을 동시에 절감한다.
- `EfficiencyConfig(target_cost_per_completion=800)`은 완료 태스크당 평균 800토큰 이내를 목표로 설정한다.

### 패턴 2 — 비용 예산 관리가 중요한 에이전트

```python
# 기반 코드 — 비용 예산 관리 에이전트 SLAConfig · ResourceBudgetConfig 조합
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    SLAConfig, ResourceBudgetConfig,
)

monitor = PerformanceMonitor(output_dir="results/")

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
    # TODO(현업 적용): 아래를 실제 LLM 호출로 교체하세요.
    #   예) return llm.invoke(question)  # LangChain 등 초기화된 클라이언트 사용
    return f"응답: {question}"
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
# 개념 코드 — SLAConfig + InstructionConfig 트레이드오프 명시화 패턴
# (실행 가능 전체 예제: Evaluator_Examples/ch07_group_d.py 참고)
# 트레이드오프 명시화: 빠른 응답을 위해 응답 길이 제한
@agent_eval(
    monitor,
    task_type="qa",
    sla=SLAConfig(p95_ms=1000),              # 빠른 응답 SLA
    instructions=InstructionConfig(max_words=100),  # 짧은 응답으로 토큰 절감
)
def fast_agent(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래를 실제 빠른 모델 호출로 교체하세요.
    #   예) return fast_llm.invoke(question)  # Haiku 계열 등 저지연 모델 사용
    return f"빠른 응답: {question}"
```

- `SLAConfig(p95_ms=1000)`과 `InstructionConfig(max_words=100)`을 함께 선언하면 응답 길이 제한이 지연 시간 단축으로 이어진다.
- 빠른 응답이 필요한 경우 Haiku 계열 모델로 전환해 비용과 지연을 동시에 줄일 수 있다.
- 이 트레이드오프를 코드로 명시하면 모델 변경 시 SLA 영향을 즉시 측정할 수 있다.

### 7.5.2 비용 예측 가능성과 드리프트

같은 에이전트라도 입력의 복잡도가 달라지면 비용이 달라진다. `CostPredictabilityConfig`로 비용 변동성을 모니터링하고, `agent-eval trend`로 시간에 따른 비용 추세를 추적한다.

> **비용 드리프트**란 처음 배포할 때와 비교해 시간이 지날수록 에이전트의 평균 비용이 조금씩 상승하는 현상이다. 사용자 질문이 점점 복잡해지거나, 컨텍스트가 누적되거나, 재시도가 늘어날 때 발생한다. `agent-eval trend`로 배포 이후 비용 기울기(slope)를 추적하고 임계값 초과 시 CI/CD에서 자동 경고한다.

```bash
# 비용 드리프트 탐지
agent-eval trend results/ --window 30
# → 지난 30개 평가 결과의 비용 추세 분석
# → 기울기(slope)가 양수 + 임계값 초과 시 CI/CD 경고
```

---

## 이 챕터의 핵심

Gate D는 응답 시간과 비용이 약속한 SLA를 지키는지 판정한다. `LatencyTracker`가 응답 시간 퍼센타일을 실측해 Gate D 점수에 직접 기여하고, `TokenEconomyTracker`는 토큰·비용을 추적한다(gate score 미기여 — 리포트 집계 전용). 5개 Config가 허용 상한과 변동성 기준을 코드로 선언한다. SLA 위반 여부가 자동으로 배포 차단으로 이어지는 구조다.

| 지표 / Config | 역할 | 핵심 파라미터 |
|--------------|------|-------------|
| `LatencyTracker` | 응답 시간 퍼센타일 측정 — **Gate D 점수 기여** | `p50`, `p90`, `p95`, `p99`, `mean`, `min`, `max`, `std` (`efficiency_metrics.latency`) |
| `TokenEconomyTracker` | 토큰·비용 추적 **(gate score 미기여)** | `total_tokens`, `avg_tokens_per_task`, `total_cost`, `avg_cost_per_task` (`efficiency_metrics.tokens`) |
| `SLAConfig` | SLA 계약 선언 | `p95_ms`, `p99_ms`, `max_cost_per_task`, `fail_threshold` |
| `EfficiencyConfig` | 비용 대비 완료율 기준 | `cost_unit`, `target_cost_per_completion`, `fail_ratio` |
| `ResourceBudgetConfig` | 개별 태스크 리소스 상한 | `max_tokens`, `max_cost_usd`, `max_execution_time_ms` |
| `TTFTVariabilityConfig` | TTFT 변동성 기준 | `max_stddev_ms`, `max_p95_p50_ratio` |
| `CostPredictabilityConfig` | 비용 예측 가능성 기준 | `max_coefficient_of_variation`, `cost_metric` |

> 🔗 **다음 챕터**: Chapter 8 — Gate E: 보안경계  
> 외부 공격과 데이터 유출을 차단하는 5개 Tracker와 3개 Config를 완전히 이해한다. 패턴 매칭과 의미 기반 탐지 2계층 보안을 다룬다.


---

## 실전 예제

**기본 예제**: [`Evaluator_Examples/ch07_group_d.py`](../../Evaluator_Examples/ch07_group_d.py)
— LatencyTracker · TokenEconomyTracker · SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig 5개 Config · Gate D FAIL 시나리오

> **관련 챕터 예제**: Harness 전체 Gate 통합 흐름은 [Chapter 3 — `ch03_harness_basics.py`](Chapter_03_Harness_Engineering_기초.md)에서 확인한다.

**핵심 코드**

```python
# 기반 코드 — Evaluator_Examples/ch07_group_d.py, 섹션 4 (EvalMetadata 반환 생략, 단순화)
import time, random
from agent_evaluator import (
    PerformanceMonitor,
    SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
    TTFTVariabilityConfig, CostPredictabilityConfig,
    agent_eval,
)

monitor = PerformanceMonitor(
    output_dir="results/",
    ttft_variability_config=TTFTVariabilityConfig(max_stddev_ms=300.0, max_p95_p50_ratio=2.5),
    cost_predictability_config=CostPredictabilityConfig(max_coefficient_of_variation=0.3),
)

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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
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
python Evaluator_Examples/ch03_harness_basics.py   # Gate D 포함 전체
python Evaluator_Examples/ch01_first_eval.py       # LatencyTracker·TokenEconomy 예제
python Evaluator_Examples/ch07_group_d.py          # Gate D FAIL — 역케이스 포함 전체 예제
```

- `ch03_harness_basics.py`는 Gate D를 포함한 Harness Gate 전체 기본 예제다.
- `ch01_first_eval.py`는 `LatencyTracker`와 `TokenEconomyTracker`를 직접 다루는 Layer 1 예제다.
- `ch07_group_d.py`의 역케이스 섹션에서 TTFT 극단 분산과 ResourceBudget 초과로 Gate D FAIL 흐름을 재현한다.
