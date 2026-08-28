# 품질 게이트 가이드

임계값 설정 · 품질 게이팅 · CI/CD 통합

**v1.0.0-rc3 | Python 3.8+**

---

## 목차

1. [개요](#1-개요)
2. [게이팅 방법 4가지](#2-게이팅-방법-4가지)
3. [지원 Threshold 메트릭 전체 목록](#3-지원-threshold-메트릭-전체-목록)
4. [환경별 권장값](#4-환경별-권장값)
5. [CI/CD 통합](#5-cicd-통합)
6. [임계값 파일 관리](#6-임계값-파일-관리)
7. [추세 분석 (agent-eval trend)](#7-추세-분석-agent-eval-trend)
8. [Gate 회귀 원인진단 (agent-eval diagnose)](#8-gate-회귀-원인진단-agent-eval-diagnose)
9. [도메인별 Harness Config 프리셋](#9-도메인별-harness-config-프리셋)
10. [Best Practices](#10-best-practices)

---

## 1. 개요

**Threshold(임계값)** 는 에이전트 품질의 최저 기준선입니다.

- **품질 게이트** — 배포 전 최소 성능 보장
- **CI/CD 자동화** — 평가 점수 미달 시 파이프라인 차단 (`sys.exit(1)`)
- **회귀 방지** — 코드 변경 후 성능 저하 자동 감지

---

## 2. 게이팅 방법 4가지

### 방법 1 — CLI gate (가장 간단)

평가 결과 JSON 파일을 직접 검사합니다. CI/CD 스크립트에서 바로 사용 가능합니다.

```bash
# 기본: TCR과 정확도만 검사
agent-eval gate results/eval.json --tcr 85 --accuracy 70

# 복합: 4개 지표 동시 검사
agent-eval gate results/eval.json --tcr 85 --accuracy 70 --llm-judge 3.5 --hallucination 5

# Harness Gate A–G 복합 점수 판정 (v0.8.3+)
agent-eval gate results/eval.json --min-gate-score 0.75

# Gate별 가중치 지정 — 보안(E)·목표달성(A)을 3배 강조
agent-eval gate results/eval.json --min-gate-score 0.75 --group-weights "A:2.0,E:3.0,B:1.0"

# Gate별 개별 최소 점수 지정 — 가중 복합 점수가 아니라 Gate 각각을 독립적으로 판정
agent-eval gate results/eval.json --gate-thresholds "A:0.8,E:0.95" --required-gates "A,E" --fail-on-gate-warn
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

#### `--gate-thresholds` / `--required-gates` / `--fail-on-gate-warn` 상세

`--min-gate-score`/`--group-weights`가 **하나의 가중 복합 점수**로 판정하는 것과 달리, 이 3개 옵션은 **Gate A–G 각각을 독립적으로** 임계값과 비교합니다 — Gate별로 다른 위험 수준을 적용하고 싶을 때(예: 보안은 0.95, 나머지는 0.7) 사용합니다.

| 옵션 | 형식 | 설명 |
|------|------|------|
| `--gate-thresholds` | `"A:0.8,E:0.95"` | Gate별 개별 최소 점수. 목록에 없는 Gate는 `--min-gate-score`를 폴백으로 사용 |
| `--required-gates` | `"A,E"` | `--gate-thresholds` 검사 대상 Gate를 제한 (미지정 시 점수가 있는 Gate 전체 검사) |
| `--fail-on-gate-warn` | flag | Gate 상태가 `warn`이면 실패로 처리 (기본: warn도 통과) |

> `--required-gates`와 `--fail-on-gate-warn`은 `--gate-thresholds`가 함께 지정돼야만 동작합니다 — 단독으로 주면 아무 효과가 없습니다. `--required-gates`에 없는 Gate는 "경고"가 아니라 검사 자체에서 조용히 제외됩니다.

Python 코드에서 동등한 판정을 원하면 아래 [방법 4 — HarnessEvaluationGate](#방법-4--harnessevaluationgate-config-as-code-종합-판정)를 사용하세요 — `agent-eval gate` CLI와 `HarnessEvaluationGate`는 서로 호출하지 않는 독립 구현이므로 완전히 동일하지는 않습니다.

#### `--baseline-version` — 버전별 독립 기준선 (v0.9.8+)

여러 프롬프트/에이전트 버전을 동시에 실험할 때, 버전마다 독립된 기준선을 두고 각자의 회귀 여부를 추적합니다. 미지정 시 기존 `<result_dir>/baseline.json` 단일 경로 동작과 100% 동일합니다.

```bash
# v2-cot 실험 전용 기준선 저장 — <result_dir>/baselines/v2-cot.json 에 저장됨
agent-eval gate results/run_v2.json --save-baseline --baseline-version v2-cot

# 같은 실험의 이후 실행을 v2-cot 기준선과만 비교 (다른 버전의 기준선에 영향 없음)
agent-eval gate results/run_v2_latest.json --baseline-version v2-cot --fail-on-regression 10
```

`--baseline`(명시적 경로)을 함께 지정하면 `--baseline-version`보다 우선합니다.

#### `--golden-set` / `--fail-on-golden-regression` — 골든셋 회귀 게이트 (v0.9.8+)

사람이 승인한 골든 데이터셋(`agent-eval dataset build` 또는 대시보드 승인 워크플로우 결과, `data/golden_datasets/golden_*.json`)의 각 케이스가 **최신 실행 결과에 여전히 커버되고 통과하는지** 확인합니다. 매칭은 `task_id` 우선, 없으면 `question` 텍스트 완전 일치로 폴백합니다 — 골든셋을 병합할 때 가능하면 원본 `task_id`를 보존하세요(대시보드의 `merge_approved()`는 이미 이를 보존합니다).

> 이 게이트는 **사후 분석**입니다 — 에이전트를 재실행하지 않고 이미 생성된 결과 JSON만 검사합니다. "골든셋으로 에이전트를 다시 돌려서 검증"하려면 위의 [Golden Dataset 기반 회귀 테스트](#golden-dataset-기반-회귀-테스트) 패턴(재실행 + `eval.gate()`)을 사용하세요 — 두 방식은 서로 대체가 아니라 보완 관계입니다.

```bash
agent-eval gate results/run_latest.json \
  --golden-set data/golden_datasets/golden_20260705_120000.json \
  --fail-on-golden-regression
# exit 3: golden regression — 케이스 누락(커버리지 갭) 또는 success=False(품질 회귀)
```

`--fail-on-golden-regression` 없이 `--golden-set`만 지정하면 회귀를 stderr에 보고만 하고 종료 코드에는 반영하지 않습니다(다른 옵트인 체크와 동일한 관례) — 지정 시에만 전용 종료 코드 `3`을 반환합니다. 골든셋 파일이 없거나 파싱에 실패하면(경로 오탈자 등) 조용히 통과시키지 않고 즉시 exit 1로 실패합니다.

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

### 방법 4 — HarnessEvaluationGate (Config-as-Code 종합 판정)

`agent-eval gate`/`QuickEval.gate()`가 숫자 임계값 중심이라면, `HarnessEvaluationGate`는 **Harness Config 선언 자체를 판정 근거로 삼는** Python API입니다. `@agent_eval`에 선언한 33개 Harness Config(`InstructionConfig`, `SLAConfig`, `ThreatSeverityConfig` 등)의 결과가 Gate A–G 점수로 집계된 뒤, 이 클래스가 그 점수를 검사합니다. Config 선언이 코드(Git 추적)로 남으므로 "왜 이 기준이 정해졌는가"를 리뷰 이력으로 추적할 수 있습니다.

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()   # 인수 없음
# {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool,
#      "threshold": float, "not_measured": bool (score=None일 때만),
#      "insufficient_data_warnings": list[str] (있을 때만)}},
#  "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}

# CI/CD — 실패 시 sys.exit(1)
gate.enforce()
```

**Gate별 개별 임계값 + 미측정 Gate 강제 실패** — CLI의 `--gate-thresholds`/`--required-gates`에 대응합니다.

```python
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],
    group_thresholds={"E": 0.95},   # Security는 더 엄격하게, 나머지는 min_group_score
    strict_required=True,            # required_groups에 명시한 Gate가 score=None(Config 자체를
                                      # 설정 안 함)이면 실패 처리. 기본값(False)은 "측정 안 된 Gate는
                                      # 조용히 통과"인 CLI/QuickEval.gate()와 동일한 기존 동작 유지
)
result = gate.evaluate()
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `min_group_score` | `0.7` | 각 Gate 최소 허용 점수. `group_thresholds`에 없는 Gate에 적용 |
| `required_groups` | `None`(점수 있는 모든 Gate) | 검사할 Gate 목록 |
| `fail_on_warn` | `False` | `True`면 `warn` 상태도 실패로 처리 |
| `group_thresholds` | `None` | Gate별 개별 최소 점수 dict. CLI `--gate-thresholds`와 동일 개념 |
| `strict_required` | `False` | `required_groups`에 명시한 Gate가 미측정(`score=None`)이면 실패 처리 |

> ⚠️ `agent-eval gate` CLI(`--gate-thresholds`)·`QuickEval.gate(gate_thresholds=...)`·`HarnessEvaluationGate`는 Gate A–G 임계값 판정을 세 곳에서 각각 호출하는 서로 다른 진입점입니다 — `_compute_gate_regressions()`(베이스라인 회귀 판정 공식)와 `gates/base.py::evaluate_gate_scores()`(Gate별 score/threshold/status → passed 판정 루프)를 셋 다 공유합니다. 남은 차이는 진입점별 고유 기능뿐입니다(`HarnessEvaluationGate`의 `strict_required`, CLI의 `--baseline-version`/`--golden-set`). 세 진입점 모두 `score=None`(해당 Gate의 Config를 아예 설정하지 않은 경우)인 Gate는 기본적으로 통과 처리합니다(`HarnessEvaluationGate`만 `strict_required=True`로 이 동작을 끌 수 있습니다).

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
            --llm-judge 3.5 \
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

> 이 패턴은 에이전트를 **재실행**해 골든셋을 통과하는지 확인합니다. 이미 만들어진 결과 JSON
> 파일만으로(재실행 없이) 골든셋 커버리지/통과 여부를 확인하려면 위 "방법 1 — CLI gate"의
> `--golden-set` / `--fail-on-golden-regression` (v0.9.8+)를 사용하세요.

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

### Python API에서 파일 로드

`QuickEval.gate(config_file=...)` 를 사용하면 JSON 파일에서 임계값을 읽을 수 있습니다. CLI(`agent-eval gate`)에는 `--config` 플래그가 없으므로 Python API를 사용하세요.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
eval.gate(config_file="gate_config.json")
# 또는 환경별 파일 분리
import os
env = os.environ.get("DEPLOY_ENV", "prod")
eval.gate(config_file=f"gate_config.{env}.json")
```

### 코드에서 파일 로드 (PerformanceMonitor)

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

## 8. Gate 회귀 원인진단 (agent-eval diagnose)

`agent-eval gate`/`agent-eval trend`가 회귀를 잡아낸 *다음* 단계 — "어떤 Gate가, 어느 세부 지표
때문에, 왜" 나빠졌는지 3단계(감지 → 원인귀속 → 교차확인)로 자동 진단합니다. **CI 게이트가 아닙니다**
— pass/fail을 판정하지 않고 사람이 읽을 후보 원인과 근거만 출력합니다(HOTL 원칙). baseline이 없어도
현재 fail/warn 상태인 Gate를 감지하는 방식으로 동작합니다.

```bash
# baseline 없이 — 현재 fail/warn 상태인 Gate를 감지
agent-eval diagnose results/latest.json

# baseline과 비교 — 회귀 기반 감지로 격상
agent-eval diagnose results/latest.json --baseline results/baseline.json

# --show-diff: baseline↔current 사이 실제 git 커밋 변경 이력까지 함께 표시
agent-eval diagnose results/latest.json --baseline results/baseline.json --show-diff

# JSON으로 출력 (스크립트 연동용)
agent-eval diagnose results/latest.json --json
```

출력에는 감지 방식(`detection_mode`), 감지된 Gate 목록, Gate별 `top_detail_deltas`(baseline 대비
가장 많이 움직인 세부 지표), SQLite 위반 이력이 있으면 관련 위반 건, Gate F는 MAST(Cemri et al.,
NeurIPS 2025) 실패모드 후보까지 포함됩니다. Gate C·D가 동시에 감지되면 SLA가 공유 원인인지 먼저
확인하는 체크도 함께 표시됩니다.

Python API: `agent_evaluator.rca.diagnose()` — 상세 시그니처는 [`08_API_REFERENCE.md`의 "RCA 진단 +
추천 이력" 절](08_API_REFERENCE.md#14-rca-진단--추천-이력-agent_evaluatorrca--ontology) 참고. 대시보드
🔧 Improve 탭이 동일 결과를 시각화합니다.

> `--show-diff`가 지목한 git 커밋을 "누가/어떤 대화로 썼는지"까지 역추적하고 싶다면(선택적, 코어
> 비의존 개인 도구) [`CTX_SESSION_SEARCH.md`의 워크플로우 A](CTX_SESSION_SEARCH.md#워크플로우-a--gate-회귀--git-커밋--원본-세션-역추적)
> 참고.

---

## 9. 도메인별 Harness Config 프리셋

도메인마다 위험 허용 수준이 다릅니다. 아래 프리셋을 참고해 도메인에 맞게 임계값을 조정하세요.

### 의료 AI (엄격)

생명·안전 직결 시스템 — 오탐보다 미탐이 더 위험합니다.

```python
from agent_evaluator import (
    ThreatSeverityConfig, ComplianceConfig, SLAConfig,
    ExplainabilityConfig, FaultToleranceConfig,
)

MEDICAL_HARNESS = dict(
    # Gate E: 위협 임계값을 절반으로 낮춤 (낮은 위협도도 즉시 차단)
    threat_severity=ThreatSeverityConfig(fail_score=4.0, fail_on_critical=True),
    # Gate E: HIPAA 준수 + 데이터 최소화 필수
    compliance=ComplianceConfig(
        compliance_framework="hipaa",
        pii_categories=["ssn", "medical_record", "diagnosis", "email", "phone"],
        require_data_minimization=True,
    ),
    # Gate D: 응답 지연 엄격 (진단 보조 시스템은 빠른 응답 필수)
    sla=SLAConfig(p95_ms=2000, p99_ms=4000),
    # Gate G: 반드시 추론 과정 포함 (의사의 검토를 위해)
    explainability=ExplainabilityConfig(
        require_reasoning=True,
        min_reasoning_length=100,
        reasoning_markers=["왜냐하면", "따라서", "근거", "증거"],
    ),
    # Gate C: 오류 복구 필수 (시스템 중단 불가)
    fault_tolerance=FaultToleranceConfig(
        check_fallback_attempts=True,
        partial_success_threshold=0.8,  # 80% 이상 완성도 필요
    ),
)
```

### 금융 AI (엄격)

규제 준수 + 비용 예측 가능성이 핵심입니다.

```python
from agent_evaluator import (
    ComplianceConfig, SLAConfig, ResourceBudgetConfig,
    CostPredictabilityConfig, ThreatSeverityConfig,
)

FINANCE_HARNESS = dict(
    # Gate E: SOX/PCI-DSS 준수
    compliance=ComplianceConfig(
        compliance_framework="sox",
        pii_categories=["credit_card", "bank_account", "ssn", "tax_id"],
        require_data_minimization=True,
    ),
    # Gate D: 매우 엄격한 SLA (금융 거래 지연 = 손실)
    sla=SLAConfig(p95_ms=1000, p99_ms=2000),
    # Gate D: 비용 예산 엄격 제한 (건당 처리 비용 통제)
    resource_budget=ResourceBudgetConfig(max_tokens=800, max_cost_usd=0.005),
    # Gate D: 비용 변동성 최소화 (예산 예측 가능성)
    # monitor 생성자에 전달: PerformanceMonitor(cost_predictability_config=...)
    # CostPredictabilityConfig(max_coefficient_of_variation=0.2, min_samples=10)
    threat_severity=ThreatSeverityConfig(fail_score=5.0, fail_on_critical=True),
)
```

### 일반 챗봇 (완화)

사용자 경험 중심 — 빠른 이터레이션이 중요합니다.

```python
from agent_evaluator import (
    SLAConfig, ComplianceConfig, ExplainabilityConfig,
)

CHATBOT_HARNESS = dict(
    # Gate D: 여유로운 SLA (챗봇은 5초까지 허용)
    sla=SLAConfig(p95_ms=5000, p99_ms=10000),
    # Gate E: 기본 PII 보호만
    compliance=ComplianceConfig(
        pii_categories=["email", "phone"],
        compliance_framework="general",
    ),
    # Gate G: 추론 과정 선택 (챗봇은 간결한 답변 선호)
    explainability=ExplainabilityConfig(
        require_reasoning=False,
        min_reasoning_length=0,
    ),
)
```

### 프리셋 적용 패턴

```python
from agent_evaluator.decorators import agent_eval

# 도메인 선택
DOMAIN = "medical"  # "medical" | "finance" | "chatbot"
PRESET = {"medical": MEDICAL_HARNESS, "finance": FINANCE_HARNESS, "chatbot": CHATBOT_HARNESS}[DOMAIN]

@agent_eval(monitor, task_type="qa", **PRESET)
def domain_agent(question: str, ground_truth: str = "") -> str:
    return f"도메인 특화 응답: {question}"
```

### 도메인별 임계값 비교

| 항목 | 의료 | 금융 | 일반 챗봇 |
|------|------|------|-----------|
| SLA P95 | 2,000ms | 1,000ms | 5,000ms |
| ThreatSeverity fail_score | 4.0 | 5.0 | 7.0 (기본) |
| 추론 과정 필수 | ✅ 필수 | 권장 | 선택 |
| PII 카테고리 | 의료+개인정보 | 금융+개인정보 | 이메일·전화 |
| 비용 예산/건 | — | $0.005 | $0.01 |

---

## 10. Best Practices

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
| ctx 세션 검색 (선택적 개인 워크플로우) | [CTX_SESSION_SEARCH.md](CTX_SESSION_SEARCH.md) |
