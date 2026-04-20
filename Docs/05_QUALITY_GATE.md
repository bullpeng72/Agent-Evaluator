# 품질 게이트 가이드

임계값 설정 · 품질 게이팅 · CI/CD 통합

**v0.8.3 | Python 3.8+**

---

## 목차

1. [개요](#1-개요)
2. [게이팅 방법 3가지](#2-게이팅-방법-3가지)
3. [지원 Threshold 메트릭 전체 목록](#3-지원-threshold-메트릭-전체-목록)
4. [환경별 권장값](#4-환경별-권장값)
5. [CI/CD 통합](#5-cicd-통합)
6. [임계값 파일 관리](#6-임계값-파일-관리)
7. [추세 분석 (agent-eval trend)](#7-추세-분석-agent-eval-trend)
8. [Best Practices](#8-best-practices)

---

## 1. 개요

**Threshold(임계값)** 는 에이전트 품질의 최저 기준선입니다.

- **품질 게이트** — 배포 전 최소 성능 보장
- **CI/CD 자동화** — 평가 점수 미달 시 파이프라인 차단 (`sys.exit(1)`)
- **회귀 방지** — 코드 변경 후 성능 저하 자동 감지

---

## 2. 게이팅 방법 3가지

### 방법 1 — CLI gate (가장 간단)

평가 결과 JSON 파일을 직접 검사합니다. CI/CD 스크립트에서 바로 사용 가능합니다.

```bash
# 기본: TCR과 정확도만 검사
agent-eval gate results/eval.json --tcr 85 --accuracy 70

# 복합: 4개 지표 동시 검사
agent-eval gate results/eval.json --tcr 85 --accuracy 70 --quality 3.5 --hallucination 5

# 임계값 파일 사용
agent-eval gate results/eval.json --config gate_config.json

# Harness Gate A–G 복합 점수 판정 (v0.8.3+)
agent-eval gate results/eval.json --min-gate-score 0.75

# Gate별 가중치 지정 — 보안(E)·목표달성(A)을 3배 강조
agent-eval gate results/eval.json --min-gate-score 0.75 --group-weights "A:2.0,E:3.0,B:1.0"
```

임계값을 하나라도 미달하면 비제로(non-zero) 종료 코드를 반환합니다.

#### `--min-gate-score` / `--group-weights` 상세

| 옵션 | 형식 | 설명 |
|------|------|------|
| `--min-gate-score` | `float` (0.0–1.0) | Gate A–G 가중 평균 최소값. 미달 시 exit(1) |
| `--group-weights` | `"A:W,B:W,..."` | Gate별 가중치 (생략 시 균등 가중). 미정의 Gate는 기본값 1.0 |

```bash
# 예: 보안(E) 3배, 신뢰성(C) 2배 가중, 전체 복합 점수 0.8 이상 필요
agent-eval gate results/eval.json \
  --min-gate-score 0.80 \
  --group-weights "C:2.0,E:3.0"
```

복합 점수는 `extra_metrics.harness_groups.{A-G}.score` 필드에서 추출합니다. 해당 데이터가 없는 Gate는 계산에서 제외됩니다.

---

### 방법 2 — QuickEval.gate() (코드에서)

평가와 게이팅을 한 파일에서 처리합니다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    agent(q, ground_truth=gt)

# 임계값 미달 시 sys.exit(1)
eval.gate(tcr=85, accuracy=70, quality=3.5, hallucination=5.0)

# raise_on_fail=False → 종료 대신 bool 반환
passed = eval.gate(tcr=80, accuracy=65, raise_on_fail=False)
if not passed:
    print("품질 기준 미달 — 배포 보류")

# 현재 결과 기반으로 gate_config.json 자동 생성 (현재 값의 95% 수준)
eval.generate_gate_config("gate_config.json")
```

---

### 방법 3 — monitor.thresholds (저수준 API)

`PerformanceMonitor`를 직접 사용할 때 세밀한 제어가 필요한 경우에 사용합니다.

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")
monitor.thresholds = {
    "tcr": 85.0,
    "accuracy": 70.0,
    "latency": 5.0,   # P95 기준, 초 단위
}

results = monitor.compare_with_thresholds()
for metric, data in results.items():
    status = "PASS" if data["status"] == "pass" else "FAIL"
    print(f"[{status}] {metric}: {data['value']:.1f} (기준: {data['threshold']})")
```

`compare_with_thresholds()` 반환값 구조:

```python
{
    "tcr": {
        "name": "Task Completion Rate",
        "value": 91.2,
        "threshold": 85.0,
        "status": "pass",   # "pass" | "fail"
        "direction": "higher_is_better",
        "unit": "%",
    },
    "latency": {
        "name": "P95 Latency",
        "value": 6.3,
        "threshold": 5.0,
        "status": "fail",
        "direction": "lower_is_better",
        "unit": "seconds",
    },
}
```

---

## 3. 지원 Threshold 메트릭 전체 목록

| 레이어 | 메트릭 키 | 단위 | 방향 | 권장값 (Prod) |
|--------|-----------|------|------|---------------|
| Layer 1 | `tcr` | % | 높을수록 좋음 | ≥ 85 |
| Layer 1 | `accuracy` | % | 높을수록 좋음 | ≥ 70 |
| Layer 1 | `hallucination` | % | **낮을수록 좋음** | ≤ 5 |
| Layer 1 | `quality` | 점 (0–5) | 높을수록 좋음 | ≥ 3.5 |
| Layer 1 | `latency` | 초 (P95) | **낮을수록 좋음** | ≤ 5.0 |
| Layer 1 | `cost_per_task` | USD | **낮을수록 좋음** | ≤ 0.05 |
| Layer 2 | `tool_selection_accuracy` | % (F1) | 높을수록 좋음 | ≥ 80 |
| Layer 2 | `agent_coordination` | % | 높을수록 좋음 | ≥ 75 |
| Layer 2 | `workflow_execution` | % | 높을수록 좋음 | ≥ 80 |
| Layer 2 | `retry_success_rate` | % | 높을수록 좋음 | ≥ 60 |
| Layer 2 (보안) | `input_sanitization` | % | 높을수록 좋음 | ≥ 95 |
| Layer 2 (보안) | `output_leakage` | % (탐지율) | **낮을수록 좋음** | ≤ 1 |
| Layer 2 (보안) | `authorization` | % | 높을수록 좋음 | ≥ 99 |
| Layer 2 (보안) | `privilege_escalation` | 건 | **낮을수록 좋음** | 0 |
| Layer 2 (보안) | `tool_chain_attack` | 건 | **낮을수록 좋음** | 0 |
| Layer 3 (RAG) | `faithfulness` | 점 (0–1) | 높을수록 좋음 | ≥ 0.80 |
| Layer 3 (RAG) | `answer_relevancy` | 점 (0–1) | 높을수록 좋음 | ≥ 0.75 |
| Layer 3 (RAG) | `context_recall` | 점 (0–1) | 높을수록 좋음 | ≥ 0.70 |
| Layer 3 (RAG) | `context_precision` | 점 (0–1) | 높을수록 좋음 | ≥ 0.70 |

> **주의사항**:
> - `latency`는 평균이 아닌 **P95(95 백분위수)** 기준입니다.
> - `quality`는 **5점 척도** (0–5)입니다. 10점 척도가 아닙니다.
> - `hallucination`, `output_leakage`, `privilege_escalation`, `tool_chain_attack`은 낮을수록 좋습니다 (미달 판정 방향 반전).

---

## 4. 환경별 권장값

| 메트릭 | 개발(Dev) | 스테이징(Staging) | 운영(Prod) |
|--------|-----------|-------------------|------------|
| `tcr` | ≥ 70% | ≥ 80% | ≥ 85% |
| `accuracy` | ≥ 55% | ≥ 65% | ≥ 70% |
| `hallucination` | ≤ 15% | ≤ 8% | ≤ 5% |
| `quality` | ≥ 2.5 | ≥ 3.0 | ≥ 3.5 |
| `latency` (P95) | ≤ 15초 | ≤ 8초 | ≤ 5초 |
| `cost_per_task` | ≤ 0.20 USD | ≤ 0.10 USD | ≤ 0.05 USD |

개발 환경에서는 느슨하게 시작하고, 운영 배포 전 단계적으로 강화합니다.

---

## 5. CI/CD 통합

### GitHub Actions

```yaml
name: Agent Quality Gate

on:
  push:
    branches: [main, staging]
  pull_request:

jobs:
  quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: pip install agent-evaluator

      - name: Run evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/run_evaluation.py

      - name: Quality Gate
        run: |
          agent-eval gate results/eval.json \
            --tcr 85 \
            --accuracy 70 \
            --quality 3.5 \
            --hallucination 5

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-results
          path: results/
```

### pytest Quality Gate

```python
# tests/test_quality_gate.py
import pytest
from agent_evaluator import QuickEval

def test_quality_gate():
    eval = QuickEval("results/")

    @eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return my_agent.invoke(question)

    for question, ground_truth in load_test_cases():
        agent(question, ground_truth=ground_truth)

    passed = eval.gate(tcr=80, accuracy=65, raise_on_fail=False)
    assert passed, "Agent did not meet quality thresholds"

def test_latency_gate():
    eval = QuickEval("results/")
    # ... 평가 실행 ...
    passed = eval.gate(latency=8.0, raise_on_fail=False)
    assert passed, f"P95 latency exceeded 8s threshold"
```

```bash
pytest tests/test_quality_gate.py -v
```

### GitLab CI

```yaml
evaluate:
  stage: test
  script:
    - pip install agent-evaluator
    - python scripts/run_eval.py
    - agent-eval gate results/eval.json --tcr 85 --accuracy 70
  artifacts:
    paths:
      - results/
    when: always
```

### Golden Dataset 기반 회귀 테스트

```python
# tests/test_quality_regression.py
from agent_evaluator import QuickEval

def test_quality_regression(golden_dataset):
    eval = QuickEval("results/")

    @eval.qa
    def agent(question, ground_truth=""):
        return my_agent(question)

    for pair in golden_dataset["qa_pairs"]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    assert eval.gate(tcr=85, accuracy=70, raise_on_fail=False), (
        f"Quality regression detected: {eval.summary()}"
    )
```

---

## 6. 임계값 파일 관리

임계값을 코드에 하드코딩하지 않고 파일로 관리하면 환경별 설정을 분리할 수 있습니다.

### 파일 생성 — 자동

```python
# 현재 결과의 95% 수준으로 gate_config.json 자동 생성
eval.generate_gate_config("gate_config.json")
```

### 파일 생성 — 수동

```json
{
  "tcr": 85.0,
  "accuracy": 70.0,
  "quality": 3.5,
  "hallucination": 5.0,
  "latency": 5.0
}
```

### CLI에서 파일 로드

```bash
agent-eval gate results/eval.json --config gate_config.json

# 환경별 설정 파일 분리
agent-eval gate results/eval.json --config gate_config.${DEPLOY_ENV}.json
```

### 코드에서 파일 로드

```python
import json
from agent_evaluator import PerformanceMonitor

with open("gate_config.json") as f:
    thresholds = json.load(f)

monitor = PerformanceMonitor(output_dir="results/")
monitor.thresholds = thresholds
results = monitor.compare_with_thresholds()
```

---

## 7. 추세 분석 (agent-eval trend)

순차 실행 결과의 TCR·정확도 추세를 분석하고, 회귀 감지 시 CI/CD를 차단합니다.

```bash
# 최근 10개 결과 파일 TCR·정확도 추세 분석
agent-eval trend results/

# 최근 5개 파일만 분석
agent-eval trend results/ --window 5

# 회귀 감지 시 exit 1 (CI/CD 실패 처리)
agent-eval trend results/ --fail-on-regression

# 분석 결과 JSON 저장
agent-eval trend results/ --output-json trend.json
```

---

## 8. Best Practices

**보수적으로 시작하라**
처음부터 엄격한 임계값을 설정하면 false failure가 많아집니다. 초기에는 느슨하게 설정하고 (`tcr: 70`, `accuracy: 55`), 데이터가 쌓이면 점진적으로 강화합니다.

**`generate_gate_config()`로 기준선을 잡아라**
수동으로 임계값을 정하기 어려울 때는 충분한 평가를 먼저 실행한 후 `generate_gate_config()`를 호출합니다. 현재 결과의 95% 수준을 자동 계산해줍니다.

**Latency는 P95 기준임을 명심하라**
`latency` 임계값은 평균이 아닌 P95에 적용됩니다. 평균 2초 에이전트도 P95가 10초일 수 있습니다. 사용자 경험 기반으로 P95 목표를 설정하세요.

**Quality는 5점 척도다**
`quality` 임계값은 0–5 범위입니다. `3.5` 이상이 일반적인 운영 기준입니다. 10점 척도로 혼동하지 마세요.

**Hallucination과 보안 지표는 방향이 반전된다**
`hallucination`, `output_leakage`, `privilege_escalation`, `tool_chain_attack`은 낮을수록 좋습니다. `compare_with_thresholds()`에서 `direction: "lower_is_better"`로 표시됩니다.

**환경마다 다른 임계값 파일을 유지하라**
`gate_config.dev.json`, `gate_config.staging.json`, `gate_config.prod.json`을 별도로 관리하고 CI/CD 환경 변수로 선택합니다.

---

| 목적 | 문서 |
|------|------|
| 설치 · 기본 사용법 | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| 58개 지표 상세 | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| 데코레이터 · 프레임워크 통합 | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| 골든 데이터셋 · 한국어 RAG | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| Docker · 환경별 설정 | [07_OPERATIONS.md](07_OPERATIONS.md) |
