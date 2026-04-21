# Chapter 18. CI/CD 품질 게이팅

> **이 챕터에서 배우는 것**
> - 배포 파이프라인에 AI 품질 검문소를 설치하는 이유와 방법
> - `agent-eval gate` CLI의 모든 옵션과 동작 원리
> - `agent-eval trend` CLI로 다중 실행 기울기 기반 회귀 감지
> - GitHub Actions, GitLab CI, Jenkins 완전 통합 패턴
> - 환경별(dev/staging/prod) 차등 임계값 전략
> - 게이팅 실패 시 즉각 대응 절차

> **독자별 읽기 가이드**  
> - **👨‍💻 개발자**: §18.1–§18.3(게이팅 원리·CLI) → §18.5(환경별 임계값) 순서로 읽으면 "어떤 Config 위반이 배포를 차단하는지" 파악할 수 있습니다.  
> - **📋 QA 관리자**: §18.1(게이팅 원칙) → §18.4(GitHub Actions 통합) → §18.6(실패 대응) 순서로 읽으면 "Gate 실패 시 팀이 어떻게 대응하는지" 운영 흐름을 설계할 수 있습니다.  
> - **⚙️ DevOps/MLOps**: §18.4(CI/CD 통합 패턴) → §18.5(환경별 임계값 전략) 중심으로 읽으면 파이프라인 설정에 바로 적용할 수 있습니다.  
> - **전제 지식**: Config 선언 방법 → [Chapter 12 (데코레이터)](../Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md) / 임계값 수립 → [Chapter 14](../Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md)

---

## 18.1 품질 게이팅이란 — 배포 파이프라인에 품질 검문소 세우기

소프트웨어 팀은 오래전부터 CI/CD 파이프라인에 단위 테스트, 정적 분석, 코드 커버리지 검사를 넣어왔다. 이 검사 중 하나라도 실패하면 배포가 차단된다. 이것이 **품질 게이팅(Quality Gating)**이다. 목표는 간단하다. 품질 기준을 통과하지 못한 코드는 프로덕션에 나가지 못하게 막는 것이다.

그런데 AI 에이전트에는 기존 방식이 통하지 않는다. 에이전트는 단위 테스트를 통과해도 실제 응답 품질이 나빠질 수 있다. 프롬프트 한 줄이 바뀌거나, 모델이 업데이트되거나, 문서 데이터가 달라지는 순간 에이전트의 정확도는 조용히 떨어진다. 그리고 그 변화를 눈치채는 것은 대개 고객이다.

### 게이팅 없는 배포 파이프라인의 위험

```
[코드 변경] → [단위 테스트 통과] → [프로덕션 배포] → [고객 불만 접수]
                                                           ↑
                                          "AI 답변이 이상해졌어요"
```

이 문제가 발생하는 이유는 기존 테스트가 **코드의 동작**만 검증하기 때문이다. 에이전트가 예외 없이 실행되는지, API가 응답을 반환하는지는 확인한다. 하지만 **응답의 품질**—정확한가, 환각이 없는가, 충분히 빠른가—은 확인하지 않는다.

### "코드 테스트는 통과하지만 AI 품질은 망가진" 시나리오

실제로 일어나는 시나리오를 보자.

**시나리오 1 — 프롬프트 변경 후 배포**
개발자가 프롬프트를 "더 간결하게" 수정했다. 단위 테스트는 통과했다. 그런데 배포 후 고객 서비스 에이전트의 정확도가 87%에서 71%로 떨어졌다. 품질 게이팅이 있었다면 임계값(80%)을 넘지 못해 배포가 차단됐을 것이다.

**시나리오 2 — 모델 업그레이드 후 배포**
"더 나은 모델"로 교체했다. 대부분의 케이스에서는 개선됐지만, 특정 도메인에서 환각이 증가했다. P95 레이턴시도 1.8초에서 4.2초로 늘었다. 임계값 게이팅이 없었기에 이 사실은 배포 3일 후에야 발견됐다.

**품질 게이팅의 핵심 원칙**: 측정 가능한 지표에 숫자 임계값을 설정하고, 임계값을 넘지 못하면 배포를 차단한다.

---

## 18.2 agent-eval gate CLI 완전 가이드

`agent-eval gate`는 평가 결과 JSON 파일을 읽고, 지정한 임계값과 비교해 통과/실패를 판정한다. CI/CD 시스템이 이해하는 **exit code**로 결과를 반환한다.

### 기본 사용법

```bash
# 가장 간단한 형태
agent-eval gate results/eval.json --tcr 85 --accuracy 70

# 더 많은 지표 포함
agent-eval gate results/eval.json \
  --tcr 85 \
  --accuracy 70 \
  --p95-latency 3.0 \
  --hallucination 5 \
  --llm-judge 3.5 \
  --fail-on-regression 10 \
  --junit-xml test-results/gate-results.xml
```

### 반환 코드

| Exit Code | 의미 | CI/CD 처리 |
|-----------|------|-----------|
| `0` | 모든 임계값 통과 | 빌드 계속 진행 |
| `1` | 하나 이상의 임계값 미달 | 빌드 실패 처리 |
| `2` | 회귀(Regression) 탐지 | 빌드 실패, 별도 알림 |

### 기준선 저장 및 회귀 감지

베이스라인을 저장하고 이후 실행에서 회귀를 자동으로 감지할 수 있다.

```bash
# 현재 결과를 기준선으로 저장
agent-eval gate results/eval.json --save-baseline

# 이후 실행 시 회귀 감지 (10% 이상 나빠지면 exit code 2)
agent-eval gate results/eval.json --tcr 85 --fail-on-regression 10

# 기준선 파일 경로 명시
agent-eval gate results/eval.json --tcr 85 --baseline ci/baseline.json
```

> ⚙️ **DevOps TIP**: `baseline.json`을 환경별로 관리하라. `--baseline ci/baseline.prod.json` 방식으로 환경별로 다른 기준선 파일을 사용할 수 있다.

### 모든 CLI 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--tcr` | float | — | Task Completion Rate 최솟값 (%) |
| `--accuracy` | float | — | 정확도 최솟값 (%) |
| `--p95-latency` | float | — | P95 레이턴시 최댓값 (초) |
| `--hallucination` | float | — | 환각 발생률 최댓값 (%) |
| `--llm-judge` | float | — | LLM Judge 평균 점수 최솟값 (0~5) |
| `--fail-on-regression` | float | — | 베이스라인 대비 허용 회귀율 (%) |
| `--baseline` | path | `<result_dir>/baseline.json` | 기준선 파일 경로 |
| `--save-baseline` | flag | — | 현재 결과를 기준선으로 저장 |
| `--junit-xml` | path | — | JUnit XML 결과 파일 경로 |

### 자동 gate 설정 생성

현재 지표에서 95% 임계값을 자동으로 제안하는 설정 파일을 생성할 수 있다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

# ... 평가 실행 ...

# 현재 지표 기반 95% 임계값 자동 제안
eval.generate_gate_config("gate_config.json")
```

---

## 18.3 agent-eval trend — 다중 실행 트렌드 분석

`gate`는 **단일 결과 파일**을 절대값 임계값과 비교한다. 반면 `trend`는 **여러 결과 파일의 시간 흐름**을 보고 지표가 좋아지는지 나빠지는지 기울기(slope)로 판단한다. "현재 상태가 기준을 넘는가"가 아니라 "상태가 어떤 방향으로 움직이고 있는가"를 묻는 것이다.

두 명령어는 상호 보완적이다.

| 항목 | `gate` | `trend` |
|------|--------|---------|
| 대상 | 단일 결과 파일 | 디렉토리 내 N개 결과 파일 |
| 판정 방식 | 절댓값 임계값 비교 | slope(기울기) 방향 판정 |
| 주요 용도 | 현재 빌드 pass/fail | 시간 흐름에 따른 품질 변화 감지 |
| CI 통합 | 배포 전 게이트 | 주간 리포트, 장기 회귀 경보 |

### 기본 사용법

```bash
# 최근 10개 결과 파일의 트렌드 분석 (기본)
agent-eval trend results/

# 최근 20개 파일, 특정 패턴만 분석
agent-eval trend results/ --window 20 --pattern '*quality*.json'

# 민감도 조정 (slope 0.5 미만은 stable로 판정)
agent-eval trend results/ --slope-threshold 0.5

# 회귀 감지 시 CI/CD 중단
agent-eval trend results/ --fail-on-regression

# 결과를 JSON으로 저장
agent-eval trend results/ --output-json trend_report.json
```

### 옵션 요약

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--window`, `-w` | `10` | 분석할 최근 파일 수 |
| `--pattern` | `*.json` | 파일 이름 글로브 패턴 |
| `--slope-threshold` | `0.3` | 이 절댓값 미만의 slope는 `stable`로 판정 |
| `--fail-on-regression` | — | 회귀 감지 시 exit code 1 반환 |
| `--output-json` | — | 분석 결과를 JSON 파일로 저장 |

### 분석 지표와 방향 판정

| 지표 | slope 양수 | slope 음수 |
|------|-----------|-----------|
| TCR | improving ✅ | degrading ⚠️ |
| Accuracy | improving ✅ | degrading ⚠️ |
| P95 Latency | degrading ⚠️ (지연 증가) | improving ✅ |
| Hallucination Rate | degrading ⚠️ (환각 증가) | improving ✅ |

### 출력 예시

```
트렌드 분석 결과 (최근 10회 실행)
====================================
지표              방향        slope
─────────────────────────────────────
TCR               improving   +1.23 %/run
Accuracy          stable       +0.12 %/run
P95 Latency       stable       +0.05 초/run
Hallucination     degrading   +0.87 %/run  ⚠️

⚠️ 회귀 감지: Hallucination Rate 상승 추세
```

### GitHub Actions 통합 — 주간 트렌드 감시

`trend`는 배포마다 실행하는 `gate`와 달리, 주기적으로 실행하는 회귀 감시 워크플로우에 적합하다.

```yaml
# .github/workflows/weekly-trend-check.yml
name: Weekly Quality Trend Check

on:
  schedule:
    - cron: "0 9 * * 1"   # 매주 월요일 오전 9시
  workflow_dispatch:

jobs:
  trend-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python 설정
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Agent-Evaluator 설치
        run: pip install agent-evaluator

      - name: 주간 트렌드 분석 (회귀 시 실패)
        run: |
          agent-eval trend results/ \
            --window 10 \
            --slope-threshold 0.3 \
            --fail-on-regression \
            --output-json trend_report.json

      - name: 트렌드 리포트 아티팩트 저장
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: trend-report
          path: trend_report.json
          retention-days: 90
```

> 📋 **QA 관리자 TIP**: `gate`는 배포 전 스냅샷 검사, `trend`는 스프린트 단위 장기 품질 감시에 사용하라. 두 명령어를 함께 쓰면 단기 이상과 장기 회귀를 모두 조기에 포착할 수 있다.

---

## 18.4 GitHub Actions 통합

GitHub Actions는 현재 가장 널리 쓰이는 CI/CD 플랫폼이다. 완전한 워크플로우 파일을 소개한다.

### 완전한 워크플로우 파일

```yaml
# .github/workflows/agent-quality-gate.yml
name: Agent Quality Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  evaluate-agent:
    runs-on: ubuntu-latest

    steps:
      - name: 코드 체크아웃
        uses: actions/checkout@v4

      - name: Python 3.11 설정
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Agent-Evaluator 설치
        run: |
          pip install agent-evaluator

      - name: 에이전트 평가 실행
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python ci/run_evaluation.py \
            --output results/ci_run.json \
            --sample-size 100

      - name: 품질 게이팅 실행
        run: |
          agent-eval gate results/ci_run.json \
            --tcr 85 \
            --accuracy 70 \
            --p95-latency 3.0 \
            --hallucination 5 \
            --junit-xml test-results/gate-results.xml

      - name: JUnit 결과 업로드
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: gate-results
          path: test-results/gate-results.xml

      - name: 테스트 결과 리포트 게시
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: "test-results/gate-results.xml"
          check_name: "Agent Quality Gate"

      - name: PR에 결과 코멘트 달기
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(
              fs.readFileSync('results/ci_run.json', 'utf8')
            );
            const summary = results.summary || {};

            const body = `## 🤖 Agent Quality Gate 결과

            | 지표 | 값 | 임계값 | 상태 |
            |------|-----|--------|------|
            | TCR | ${(summary.task_completion_rate * 100).toFixed(1)}% | ≥ 85% | ${summary.task_completion_rate >= 0.85 ? '✅' : '❌'} |
            | Accuracy | ${(summary.accuracy * 100).toFixed(1)}% | ≥ 70% | ${summary.accuracy >= 0.70 ? '✅' : '❌'} |
            | P95 Latency | ${summary.p95_latency?.toFixed(2)}s | ≤ 3.0s | ${summary.p95_latency <= 3.0 ? '✅' : '❌'} |

            [전체 평가 결과 보기](https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }})
            `;

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });

      - name: 평가 결과 아티팩트 저장
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: evaluation-results
          path: results/
          retention-days: 30
```

### CI 실행용 평가 스크립트

```python
# ci/run_evaluation.py
"""CI/CD 환경에서 골든 데이터셋으로 에이전트를 평가하는 스크립트."""
import argparse
import json
from agent_evaluator import QuickEval

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/ci_run.json")
    parser.add_argument("--sample-size", type=int, default=100)
    args = parser.parse_args()

    eval = QuickEval("results/", preset="testing")

    @eval.qa
    def agent(question: str, ground_truth: str = "") -> str:
        return my_agent_fn(question)  # 실제 에이전트 함수로 교체

    # 골든 데이터셋 로드
    with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
        dataset = json.load(f)

    for pair in dataset["qa_pairs"][:args.sample_size]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    eval.save()

if __name__ == "__main__":
    main()
```

> ⚙️ **DevOps TIP**: GitHub Actions Secrets에 API 키를 저장할 때, `OPENAI_API_KEY`와 `ANTHROPIC_API_KEY`를 레포지토리 설정 → Secrets and variables → Actions에 등록해두라. 절대 코드에 하드코딩하지 말 것.

---

## 18.5 GitLab CI / Jenkins 통합 패턴

### GitLab CI — `.gitlab-ci.yml`

```yaml
# .gitlab-ci.yml
stages:
  - evaluate
  - gate

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

cache:
  paths:
    - .cache/pip/

evaluate-agent:
  stage: evaluate
  image: python:3.11-slim
  script:
    - pip install agent-evaluator
    - python ci/run_evaluation.py --output results/ci_run.json
  artifacts:
    paths:
      - results/
    expire_in: 7 days
  only:
    - merge_requests
    - main

quality-gate:
  stage: gate
  image: python:3.11-slim
  dependencies:
    - evaluate-agent
  script:
    - pip install agent-evaluator
    - agent-eval gate results/ci_run.json
        --tcr 85
        --accuracy 70
        --p95-latency 3.0
        --junit-xml test-results/gate-results.xml
  artifacts:
    reports:
      junit: test-results/gate-results.xml
    paths:
      - test-results/
    when: always
  only:
    - merge_requests
    - main
```

- `evaluate` 스테이지에서 평가를 실행하고 결과를 아티팩트로 저장해 `gate` 스테이지가 참조할 수 있게 한다
- `quality-gate` 스테이지는 `dependencies`로 이전 스테이지 아티팩트를 받아 `agent-eval gate`를 실행한다
- `artifacts.reports.junit`으로 JUnit 형식 결과를 GitLab MR 페이지에 자동 표시할 수 있다

### Jenkins — `Jenkinsfile`

```groovy
// Jenkinsfile
pipeline {
    agent {
        docker {
            image 'python:3.11-slim'
        }
    }

    environment {
        ANTHROPIC_API_KEY = credentials('anthropic-api-key')
        OPENAI_API_KEY    = credentials('openai-api-key')
    }

    stages {
        stage('Install') {
            steps {
                sh 'pip install agent-evaluator'
            }
        }

        stage('Evaluate') {
            steps {
                sh '''
                    python ci/run_evaluation.py \
                        --output results/ci_run.json \
                        --sample-size 100
                '''
            }
        }

        stage('Quality Gate') {
            steps {
                sh '''
                    agent-eval gate results/ci_run.json \
                        --tcr 85 \
                        --accuracy 70 \
                        --p95-latency 3.0 \
                        --junit-xml test-results/gate-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results/gate-results.xml'
                    archiveArtifacts artifacts: 'results/**', allowEmptyArchive: true
                }
            }
        }
    }
}
```

> ⚙️ **DevOps TIP**: Jenkins를 사용하는 경우 API 키를 Credentials Plugin으로 관리하라. `credentials('anthropic-api-key')`처럼 ID로 참조하면 로그에 노출되지 않는다.

---

## 18.6 배포 환경별 임계값 전략

모든 환경에 같은 임계값을 적용하는 것은 비효율적이다. 개발 단계에서는 빠른 반복이 중요하고, 프로덕션에서는 품질이 최우선이다.

| 환경 | TCR | Accuracy | Quality | P95 Latency | 실패 시 동작 |
|------|-----|----------|---------|-------------|-------------|
| **dev** | 70% | 60% | 3.0 | 5.0초 | 경고만 (exit 0) |
| **staging** | 80% | 70% | 3.5 | 3.0초 | 배포 차단 (exit 1) |
| **prod** | 85% | 75% | 3.8 | 2.0초 | 배포 차단 + 알림 (exit 1) |

### 환경 변수로 자동 전환

```bash
# GitHub Actions 예시 — 브랜치에 따라 임계값 선택
- name: 품질 게이팅 실행
  run: |
    if [[ "${{ github.ref }}" == "refs/heads/main" ]]; then
      agent-eval gate results/ci_run.json --tcr 85 --accuracy 75 --p95-latency 2.0
    else
      agent-eval gate results/ci_run.json --tcr 80 --accuracy 70 --p95-latency 3.0
    fi
```

- `main` 브랜치는 더 엄격한 임계값(TCR 85%, 정확도 75%)을 적용해 프로덕션 배포 품질을 보장한다
- `else` 분기(PR/개발 브랜치)는 완화된 임계값을 적용해 개발 중 빠른 피드백을 허용한다
- GitHub 환경 변수 `github.ref`로 브랜치를 감지하므로 별도 설정 파일 없이 동작한다

```python
# Python에서 환경별 eval.gate() 호출
import os
from agent_evaluator import QuickEval

eval = QuickEval("results/")
env = os.getenv("ENV", "development")

thresholds = {
    "development": {"tcr": 70, "accuracy": 60},
    "staging":     {"tcr": 80, "accuracy": 70},
    "production":  {"tcr": 85, "accuracy": 75},
}

params = thresholds.get(env, thresholds["development"])
eval.gate(**params)
```

> 📋 **QA 관리자 TIP**: 임계값은 처음에는 낮게 시작해서 팀이 익숙해지면 서서히 높여라. 처음부터 너무 엄격한 임계값은 팀의 저항감을 불러일으키고 "항상 실패하는 게이트"로 전락할 수 있다.

---

## 18.7 게이팅 실패 시 대응 절차

게이트가 실패했다고 해서 당황할 필요는 없다. 실패는 품질 문제를 배포 전에 발견했다는 의미다. 체계적으로 대응하면 된다.

### 원인 분석: 낮은 케이스 조회

게이트 실패 시 가장 먼저 할 일은 어떤 케이스가 낮은 점수를 받았는지 확인하는 것이다.

```python
import json

# 평가 결과 로드
with open("results/ci_run.json", encoding="utf-8") as f:
    data = json.load(f)

# 낮은 정확도 케이스 추출
low_accuracy = [
    t for t in data.get("tasks", [])
    if t.get("accuracy_score", 1.0) < 0.5
]

for task in low_accuracy[:10]:
    print(f"질문: {task.get('question', 'N/A')}")
    print(f"응답: {task.get('response', 'N/A')}")
    print(f"정답: {task.get('ground_truth', 'N/A')}")
    print(f"정확도: {task.get('accuracy_score', 0):.2f}")
    print("---")
```

### 임계값 조정 vs 코드 수정 판단 기준

실패 원인을 파악한 후, 두 가지 선택지가 있다.

**임계값을 낮춰야 할 때**
- 임계값이 실제 운영 기준보다 지나치게 엄격한 경우
- 새로운 태스크 유형을 추가해 평균이 낮아진 경우 (의도된 변화)
- 팀이 처음 도입하는 단계에서 기준점을 파악 중인 경우

**코드를 수정해야 할 때**
- 이전 버전에서 통과했던 케이스가 실패로 바뀐 경우 (회귀)
- 특정 카테고리의 질문에서 체계적으로 실패하는 경우
- 프롬프트 변경 또는 모델 교체 후 성능이 하락한 경우

### 긴급 배포 승인 프로세스

아무리 잘 설계된 게이팅도, 긴급 상황에서 우회 경로는 필요하다. 단, 반드시 문서화하고 책임자 승인을 받아야 한다.

```yaml
# GitHub Actions — 수동 승인 후 게이팅 우회
- name: 품질 게이팅 (임계값 완화)
  if: github.event.inputs.emergency_deploy == 'true'
  run: |
    agent-eval gate results/ci_run.json \
      --tcr 50 \
      --accuracy 50
    echo "EMERGENCY DEPLOY: Quality gate relaxed by ${{ github.actor }}"
```

> 📋 **QA 관리자 TIP**: 긴급 배포 우회는 월 2회 이하로 제한하고, 매번 사후 리뷰를 의무화하라. 우회 빈도가 높다면 임계값 자체를 재검토해야 한다는 신호다.

---

## [이 챕터의 핵심]

- **CI/CD 품질 게이팅**은 AI 에이전트의 응답 품질(TCR, 정확도, 레이턴시)을 배포 파이프라인에서 자동으로 검증하는 검문소다. 코드 테스트만으로는 발견할 수 없는 품질 저하를 사전에 차단한다.

- **`agent-eval gate`**는 평가 결과 JSON을 읽어 임계값과 비교하고, exit code 0(통과)/1(실패)/2(회귀)를 반환한다. 모든 CI/CD 시스템과 통합할 수 있다.

- **`agent-eval trend`**는 N개 결과 파일의 slope(기울기)를 계산해 TCR·정확도·레이턴시·환각률의 개선/안정/회귀 방향을 판정한다. `--fail-on-regression`으로 장기 회귀를 자동 감지한다. `gate`(배포 전 단일 검사)와 함께 사용해 단기 이상과 장기 품질 저하를 모두 포착하라.

- **GitHub Actions 통합** 시 `--junit-xml` 옵션으로 JUnit 리포트를 생성하고, `actions/github-script`로 PR 코멘트에 품질 지표를 자동 게시할 수 있다.

- **환경별 차등 임계값** 전략을 사용하라. dev는 느슨하게, staging은 보통, prod는 엄격하게. 브랜치에 따라 `--tcr`, `--accuracy`, `--p95-latency` 값을 다르게 지정하거나, Python `QuickEval.gate()` 메서드에서 환경 변수로 분기한다.

- 게이팅 실패는 나쁜 것이 아니다. **배포 전에 문제를 발견했다**는 의미다. 낮은 케이스를 분석해 임계값 조정 vs 코드 수정을 판단하고, 회귀 케이스는 골든 데이터셋에 추가해 재발을 방지하라.

---

## 18.8 4가지 변경 소스 × Harness Group 영향 매트릭스

AI 에이전트 시스템에서 품질이 변화하는 원인은 크게 4가지다. 각 변경 소스가 어떤 Group 지표에 가장 먼저 영향을 미치는지 파악하면, CI/CD 게이팅에서 어떤 Harness Config를 강화해야 하는지 결정할 수 있다.

┌─────────────────────────────────────────────────────┐
│ ⚠️ 이 지표가 없으면 생기는 일                          │
│ 변경 소스를 추적하지 않으면 "어디서 무너졌는지" 모른 채  │
│ 디버깅에 수 시간을 소비한다.                           │
│ 실제 사례: 프롬프트 1줄 수정 후 Group A TCR 8% 하락.  │
│ 변경 소스 매트릭스가 없었다면 원인 파악에 3일 걸림.      │
└─────────────────────────────────────────────────────┘

### 변경 소스 × Group 영향 매트릭스

| 변경 소스 | 가장 영향받는 Group | 2순위 영향 Group | 모니터링 핵심 지표 | 권장 Config 강화 |
|---------|-------------------|----------------|-----------------|----------------|
| **코드 변경** (로직·도구·API) | Group B 행동무결성 | Group C 신뢰성 | ToolCallAnalyzer, WorkflowExecution, RetryCorrection | `ScopeConfig`, `LoopDetectionConfig` |
| **모델 교체** (버전 업/다운) | Group A 목표달성 | Group G 운영관측성 | TCR, AccuracyEvaluator, HallucinationDetector | `InstructionConfig`, `GoalAlignmentConfig`, `ObservabilityConfig` |
| **프롬프트 수정** (템플릿·지시문) | Group A 목표달성 | Group C 신뢰성 | AccuracyEvaluator, HallucinationDetector, Reproducibility | `InstructionConfig`, `ReproducibilityConfig` |
| **데이터 변경** (벡터DB·문서 갱신) | Group A 목표달성 | Group E 보안경계 | HallucinationDetector, InputSanitization, OutputLeakage | `ThreatSeverityConfig`, `IdempotencyConfig` |

### 변경 소스별 CI/CD 게이팅 강화 전략

```python
import os
from agent_evaluator import PerformanceMonitor, QuickEval

# CI 환경변수로 변경 소스 감지
change_source = os.getenv("CI_CHANGE_SOURCE", "unknown")  
# 값: "code" | "model" | "prompt" | "data"

# 변경 소스에 따라 임계값 강화
GATE_PROFILES = {
    "code": {"tcr": 85, "accuracy": 70, "groups": ["B", "C"]},
    "model": {"tcr": 90, "accuracy": 75, "groups": ["A", "G"]},
    "prompt": {"tcr": 88, "accuracy": 72, "groups": ["A", "C"]},
    "data":  {"tcr": 85, "accuracy": 70, "groups": ["A", "E"]},
    "unknown": {"tcr": 80, "accuracy": 65, "groups": []},
}

profile = GATE_PROFILES.get(change_source, GATE_PROFILES["unknown"])
print(f"변경 소스: {change_source} → TCR 기준 {profile['tcr']}%, 강화 Group: {profile['groups']}")

eval = QuickEval("results/")
eval.gate(tcr=profile["tcr"], accuracy=profile["accuracy"])
```

- `CI_CHANGE_SOURCE` 환경변수를 CI 시스템에서 주입하면 변경 소스에 따라 임계값이 자동으로 달라진다
- 모델 교체 시 TCR 90%·정확도 75%로 가장 엄격하게 검사해 모델 품질 저하를 즉시 차단한다
- `unknown` 타입은 80%/65%로 안전한 기본값을 제공해 설정 누락 시에도 완전히 무방비 상태가 되지 않는다

```yaml
# GitHub Actions — 변경 소스 자동 감지 + 게이팅 강화
name: AI Quality Gate

on:
  push:
    branches: [main, staging]

jobs:
  detect-change-source:
    runs-on: ubuntu-latest
    outputs:
      source: ${{ steps.detect.outputs.source }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - id: detect
        run: |
          CHANGED=$(git diff --name-only HEAD~1)
          if echo "$CHANGED" | grep -q "prompts/"; then
            echo "source=prompt" >> $GITHUB_OUTPUT
          elif echo "$CHANGED" | grep -q "model_config"; then
            echo "source=model" >> $GITHUB_OUTPUT
          elif echo "$CHANGED" | grep -q "data/"; then
            echo "source=data" >> $GITHUB_OUTPUT
          else
            echo "source=code" >> $GITHUB_OUTPUT
          fi

  quality-gate:
    needs: detect-change-source
    runs-on: ubuntu-latest
    env:
      CI_CHANGE_SOURCE: ${{ needs.detect-change-source.outputs.source }}
    steps:
      - uses: actions/checkout@v4
      - run: pip install agent-evaluator
      - run: python scripts/run_golden_eval.py
      - run: agent-eval gate results/*.json --tcr ${{ env.TCR_THRESHOLD }} --accuracy ${{ env.ACC_THRESHOLD }}
        env:
          TCR_THRESHOLD: ${{ needs.detect-change-source.outputs.source == 'model' && '90' || '85' }}
          ACC_THRESHOLD: ${{ needs.detect-change-source.outputs.source == 'model' && '75' || '70' }}
```

- `detect-change-source` 잡이 `git diff`로 변경된 파일을 분석해 `prompts/`, `model_config`, `data/` 경로에 따라 소스를 자동 분류한다
- `quality-gate` 잡은 앞 잡의 `outputs.source`를 참조해 조건부로 TCR·정확도 임계값을 설정한다
- 두 잡을 분리하면 변경 소스 감지 로직을 독립적으로 테스트하고 재사용할 수 있다

---

## 18.9 HarnessEvaluationGate — 완전한 CI/CD 배포 판정

`agent-eval gate` CLI는 TCR·정확도·지연 등 개별 지표 임계값을 확인한다. `HarnessEvaluationGate`는 여기서 한 단계 더 나아가 **7개 Group 전체의 Config 위반 여부**를 종합 판정한다. 단순 숫자 임계값이 아니라, **"이 에이전트가 배포 기준을 충족하는가"를 Config 선언으로 판정**한다.

### HarnessEvaluationGate 아키텍처

```
개별 Config 판정                    종합 Gate 판정
──────────────────                  ──────────────────────────
InstructionConfig  → pass/fail ─┐
SLAConfig          → pass/fail ─┤→ HarnessEvaluationGate → DEPLOY / HOLD
ThreatSeverityConfig → pass/fail┤   (모든 Config 통과 시만)
DeadlockConfig     → pass/fail ─┘
```

### 코드 예시 — CI/CD 완전 통합

```python
# 출처: Evaluator_Examples/ch03_harness_basics.py, 섹션 CI/CD 통합 — HarnessEvaluationGate 배포 차단 예제
# ci_quality_check.py — CI/CD 파이프라인에서 실행
import sys, json
from agent_evaluator import (
    PerformanceMonitor, create_taskresult,
    InstructionConfig, SLAConfig, ThreatSeverityConfig,   # Group A, D, E
    ReproducibilityConfig, DeadlockConfig, ObservabilityConfig,  # Group C, B, G
)
from agent_evaluator.decorators import agent_eval

# 1. PerformanceMonitor 생성 (Harness Config는 @agent_eval에서 선언)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,
    enable_security_metrics=True,
)

# 2. 골든 데이터셋으로 평가 실행
with open("data/golden_datasets/master_golden.json") as f:
    golden = json.load(f)

@agent_eval(
    monitor, task_type="qa",
    # Group A — 목표달성
    instructions=InstructionConfig(
        required_keywords=[],          # 필수 키워드 (빈 목록 = 모두 허용)
        fail_on_violation=True,        # 위반 시 success=False 강제
    ),
    # Group D — 성능계약
    sla=SLAConfig(
        p95_ms=3000,                   # P95 레이턴시 3초 이내
        max_cost_per_task=0.05,        # 태스크당 최대 $0.05
    ),
    # Group E — 보안경계
    threat_severity=ThreatSeverityConfig(
        warn_score=3.0,
        fail_score=7.0,
        fail_on_critical=True,         # 보안 위반은 즉시 배포 차단
    ),
    # Group C — 신뢰성
    reproducibility=ReproducibilityConfig(
        reproducibility_threshold=0.80,
        fail_on_low_reproducibility=False,  # 경고만, 배포는 허용
    ),
)
def production_agent(question: str, ground_truth: str = "") -> str:
    # 실제 에이전트 호출
    return agent_runner.invoke(question)

for pair in golden.get("qa_pairs", []):
    production_agent(pair["question"], ground_truth=pair["ground_truth"])

# 3. Harness Gate 판정
monitor.save_to_file("ci_eval")
report = monitor.generate_report()

# Harness Gate 위반 여부: report.harness_gate_results에서 FAIL 항목 집계
gate_results = getattr(report, "harness_gate_results", {})
violations = [k for k, v in gate_results.items() if v == "FAIL"]

if violations:
    print(f"❌ HarnessEvaluationGate 배포 차단")
    print(f"   위반 Gate: {', '.join(violations)}")
    sys.exit(1)
else:
    print(f"✅ HarnessEvaluationGate 배포 승인")
    print(f"   TCR: {report.task_completion_rate:.1%} | 정확도: {report.average_accuracy:.1%}")
    sys.exit(0)
```

```yaml
# GitHub Actions — HarnessEvaluationGate 통합
  harness-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install agent-evaluator
      - run: python ci_quality_check.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Upload evaluation report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: harness-eval-report
          path: results/ci_eval.html
```

- `ci_quality_check.py`가 내부에서 `sys.exit(1)`을 호출하면 이 스텝이 실패 처리되어 배포 워크플로우 전체가 중단된다
- `if: always()`를 적용한 아티팩트 업로드는 게이팅 실패 시에도 HTML 리포트를 저장해 원인 분석에 활용할 수 있다
- Harness Gate 위반 항목은 `ci_eval.html`에 Group별로 표시되므로 실패 이유를 즉시 파악할 수 있다

### CLI gate vs HarnessEvaluationGate 비교

| 항목 | `agent-eval gate` CLI | `HarnessEvaluationGate` |
|-----|----------------------|------------------------|
| 판정 기준 | 단일 숫자 임계값 (TCR, 정확도) | Config 선언 기반 (7개 Group) |
| 위반 세분성 | "통과/실패" 1가지 | Group별 위반 항목 명시 |
| fail_on_violation | 없음 | Config별 개별 설정 |
| 버전 관리 | CLI 인수 (파라미터) | Python 코드 (Git 추적) |
| 권장 사용 | 빠른 시작, 간단한 기준 | 프로덕션, 복잡한 기준 |
| Config-as-Code | ❌ | ✅ |

> **권장**: 초기에는 `agent-eval gate --tcr 85`로 빠르게 시작. Config 종류가 3개 이상 생기면 `HarnessEvaluationGate`로 전환해 Config-as-Code 패턴을 확립한다.

---

## 실전 예제

`ch10_group_g.py`를 실행하면 결과 JSON이 생성되고, `agent-eval gate`와 `agent-eval trend`로 바로 CI/CD 게이팅을 테스트할 수 있다. 실제 GitHub Actions에서 사용하는 것과 동일한 명령어를 로컬에서 먼저 검증해보는 패턴이다.

**파일**: `Evaluator_Examples/ch18_cicd_gate.py`, `Evaluator_Examples/ch10_group_g.py`, `agent-eval gate`, `agent-eval trend`

**핵심 코드 (출처: `Evaluator_Examples/ch10_group_g.py`)**

```python
# 출처: Evaluator_Examples/ch11_eval_data.py, 섹션 4 — evaluation_session — context manager + 자동 저장
from agent_evaluator import evaluation_session, create_taskresult
import sys

# CI 파이프라인에서 평가 세션 실행
with evaluation_session("ci_evaluation") as monitor:
    test_cases = [
        ("한국의 수도는?", "서울"),
        ("지구의 위성은?", "달"),
        ("물의 화학식은?", "H2O"),
        ("피타고라스 정리는?", "a² + b² = c²"),
        ("DNA의 구조는?", "이중나선"),
    ]
    
    for i, (question, answer) in enumerate(test_cases):
        result = create_taskresult(
            task_id=f"ci_task_{i:03d}",
            question=question,
            response=answer,  # 에이전트 실제 응답으로 교체
            ground_truth=answer,
            execution_time=0.8,
            task_type="qa",
        )
        monitor.record_task(result)

# 세션 종료 시 results/ci_evaluation.json 자동 저장
```

- `evaluation_session()`은 CI 파이프라인에서 평가 결과를 안전하게 저장하는 컨텍스트 매니저다
- 테스트 케이스셋을 자동화하면 PR마다 동일한 조건에서 에이전트 품질을 비교할 수 있다

```bash
# 출처: agent-eval gate CLI — JSON 결과 기반 품질 게이팅
# 저장된 평가 결과를 읽어 기준치 초과 시 exit 1 반환
agent-eval gate results/ci_evaluation.json --tcr 85 --accuracy 70

# 여러 기준 동시 적용
agent-eval gate results/ci_evaluation.json \
    --tcr 85 \
    --accuracy 70 \
    --p95-latency 3.0 \
    --hallucination 5

# GitHub Actions 연동 예시 (.github/workflows/eval.yml)
# - name: Quality Gate
#   run: agent-eval gate results/ci_evaluation.json --tcr 85 --accuracy 70
#   # exit 1 시 워크플로 자동 실패
```

- `agent-eval gate`는 저장된 JSON을 읽어 TCR·정확도·P95 지연시간·환각률을 기준치와 비교한다
- 기준치 미달 시 `exit 1`을 반환하므로 GitHub Actions, GitLab CI, Jenkins 등 모든 CI 시스템과 연동 가능하다
- `--tcr 85`는 Task Completion Rate(태스크 완료율)이 85% 이상이어야 함을 의미한다

```bash
# 출처: agent-eval trend CLI — 연속 회귀 감지
# PR 전후 추세 비교로 성능 회귀 자동 탐지
agent-eval trend results/ --fail-on-regression --window 5

# slope-threshold로 민감도 조정 (기본: 0.3 — 절댓값 기준, 작을수록 민감하게 감지)
agent-eval trend results/ --fail-on-regression --slope-threshold 0.02
```

- `--fail-on-regression`은 지표가 연속 하락하는 추세를 감지하면 `exit 1`을 반환한다
- `--window 5`는 최근 5회 평가 결과만 비교해 장기 데이터 노이즈를 제거한다
- gate(현재 기준치)와 trend(추세 기울기)를 함께 사용하면 순간적 기준치 통과와 장기 품질 저하를 모두 감지할 수 있다

```bash
# 1. 평가 결과 생성
python Evaluator_Examples/ch10_group_g.py
# → results/operational_YYYYMMDD_HHMMSS.json 생성

# 2. 단일 결과 파일 게이팅
agent-eval gate results/operational_*.json --tcr 80 --accuracy 70
# → exit 0 (통과) 또는 exit 1 (실패)

# 3. 추이 기반 회귀 감지 (복수 파일)
agent-eval trend results/ --window 10 --fail-on-regression
```

**예제 구성**

| 단계 | 명령어 | 역할 |
|------|--------|------|
| 평가 실행 | `python ch10_group_g.py` | JSON 결과 파일 생성 |
| 단일 게이트 | `agent-eval gate ... --tcr 80` | 배포 전 단일 검문소 |
| 추이 게이트 | `agent-eval trend ... --fail-on-regression` | 장기 회귀 감지 |

**실행 결과 (v0.8.4 기준)**

```
# agent-eval gate (TCR 기준 46.1% < 임계값 80%)
❌ 품질 게이팅 실패
   TCR: 46.1% (기준: 80.0%)
   정확도: 68.1% (기준: 70.0%) — 근접 통과
   exit 1

# 임계값 완화 시
agent-eval gate results/operational_*.json --tcr 40 --accuracy 60
✅ 품질 게이팅 통과
   TCR: 46.1% ≥ 40.0%
   정확도: 68.1% ≥ 60.0%
   exit 0
```

> **CI/CD 통합 팁**: GitHub Actions에서 `continue-on-error: false`로 게이팅 스텝을 설정하면 실패 시 배포 워크플로우 전체가 중단된다. `--tcr`과 `--accuracy` 임계값은 환경 변수(`GATE_TCR`, `GATE_ACCURACY`)로 관리해 dev/staging/prod 환경별로 다르게 적용한다.

**Harness Validation CI 예제 (출처: `Evaluator_Examples/ch18_cicd_gate.py`)**

```python
# 출처: Evaluator_Examples/ch18_cicd_gate.py — Harness 7개 Group CI/CD 게이팅
# 실행: python Evaluator_Examples/ch18_cicd_gate.py [--strict]
# 종료 코드: 0 = 전체 PASS/WARN, 1 = 하나 이상 FAIL
import sys
from agent_evaluator import (
    PerformanceMonitor,
    InstructionConfig, GoalAlignmentConfig,      # Group A
    LoopDetectionConfig, ScopeConfig,             # Group B
    ReproducibilityConfig, RetryConsistencyConfig, # Group C
    SLAConfig, ResourceBudgetConfig,              # Group D
    ThreatSeverityConfig, ComplianceConfig,       # Group E
    ConsensusConfig, AgentRoleConfig,             # Group F
    ExplainabilityConfig, ObservabilityConfig,    # Group G
)
from agent_evaluator.decorators import agent_eval
import json

monitor = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

# Group A + B 최소 커버리지 예제
@agent_eval(
    monitor,
    task_type="qa",
    task_id_prefix="val_a",
    instructions=InstructionConfig(
        expected_format="json",
        required_keywords=["answer", "source"],
    ),
    goal_alignment=GoalAlignmentConfig(
        goal_tool_map={"search": ["web_search"]},
        alignment_threshold=0.5,
    ),
)
def _group_a_agent(question: str, ground_truth: str = "") -> str:
    return json.dumps({"answer": question + "에 대한 검증 답변", "source": "내부 DB"})

@agent_eval(
    monitor,
    task_type="tool_use",
    task_id_prefix="val_b",
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, window_size=5),
    scope=ScopeConfig(
        allowed_tools=["search", "summarize", "report"],
        forbidden_tools=["delete_all", "drop_table"],
    ),
)
def _group_b_agent(question: str, ground_truth: str = "") -> str:
    return f"재무 리포트 조회: {question}"

# 게이트 결과 출력 및 exit code 처리
def _print_gate_and_exit(monitor: PerformanceMonitor, strict: bool = False) -> None:
    report_dict = monitor.generate_report().to_dict()
    harness     = report_dict.get("extra_metrics", {}).get("harness_groups", {})
    failed = [gk for gk in "ABCDEFG"
              if harness.get(gk, {}).get("gate", "").upper() == "FAIL"]
    warned = [gk for gk in "ABCDEFG"
              if harness.get(gk, {}).get("gate", "").upper() == "WARN"]
    print(f"\n  FAIL 그룹: {failed or '없음'}  WARN 그룹: {warned or '없음'}")
    should_fail = bool(failed) or (strict and bool(warned))
    sys.exit(1 if should_fail else 0)
```

```bash
# CI/CD 파이프라인 통합 — 7개 Gate 전체 검증
python Evaluator_Examples/ch18_cicd_gate.py           # WARN 허용
python Evaluator_Examples/ch18_cicd_gate.py --strict  # WARN도 실패 처리
```

---

**`ch04_group_a.py` — CI/CD 배포 차단 시나리오**

Gate가 실제로 FAIL을 발생시켜 배포를 차단하는 상황을 `ch04_group_a.py`로 재현한다. 아래는 CI/CD 파이프라인에서 Gate E 위반을 탐지해 배포를 차단하는 패턴이다:

```python
# 출처: Evaluator_Examples/ch08_group_e.py, 역케이스 Gate E FAIL + CI/CD 차단
import sys
from agent_evaluator import (
    PerformanceMonitor, HarnessEvaluationGate,
    ComplianceConfig, ThreatSeverityConfig,
)
from agent_evaluator.decorators import agent_eval

monitor_e = PerformanceMonitor(output_dir="results/", enable_security_metrics=True)

@agent_eval(
    monitor_e,
    task_type="qa",
    task_id_prefix="bad_e_compliance",
    compliance=ComplianceConfig(
        pii_categories=["email", "phone"],
        compliance_framework="gdpr",
    ),
    threat_severity=ThreatSeverityConfig(
        warn_score=4.0,
        fail_score=6.0,
        fail_on_critical=True,
    ),
)
def pii_leaking_agent(question: str, ground_truth: str = "") -> str:
    # PII 노출 — ComplianceConfig가 감지해 compliance_score 하락
    return f"고객 정보: user@company.com, 010-9999-8888. 처리: {question}"

pii_leaking_agent("고객 데이터를 조회해줘", ground_truth="데이터 조회")

# CI/CD 게이팅 — Gate E FAIL 시 sys.exit(1)
report = monitor_e.generate_report()
gate = HarnessEvaluationGate(report, required_groups=["E"], min_group_score=0.7)
result = gate.evaluate()
if result.get("E", {}).get("gate") == "FAIL":
    print("❌ Gate E FAIL — 배포 차단: PII 노출 탐지")
    sys.exit(1)
```

- `ComplianceConfig(pii_categories=["email", "phone"])`가 출력에서 이메일·전화번호 패턴을 탐지하면 `compliance_score`가 하락한다
- `required_groups=["E"]`로 Gate E만 필수로 지정하면 다른 Gate 상태와 무관하게 보안 위반 시 즉시 차단할 수 있다
- `sys.exit(1)` 직접 호출 대신 `gate.enforce()`를 사용하면 실패 이유 메시지와 함께 자동 종료된다

**`ch20_deployment.py` — v1 vs v2 배포 결정 자동화**

```python
# 출처: Evaluator_Examples/ch20_deployment.py — 버전 비교 기반 배포 결정
import sys
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

# v1·v2 각각의 monitor에 에이전트를 실행한 후 Gate 점수 비교
# (실제 에이전트 실행 코드는 ch20_deployment.py 참조)

def decide_deployment(monitor_v1, monitor_v2, threshold=0.7):
    """두 버전의 Harness Gate 점수를 비교해 배포 버전을 결정한다."""
    report_v1 = monitor_v1.generate_report().to_dict()
    report_v2 = monitor_v2.generate_report().to_dict()

    gates_v1 = (report_v1.get("extra_metrics") or {}).get("harness_groups", {})
    gates_v2 = (report_v2.get("extra_metrics") or {}).get("harness_groups", {})

    v1_pass = all(g.get("gate") != "FAIL" for g in gates_v1.values())
    v2_pass = all(g.get("gate") != "FAIL" for g in gates_v2.values())

    if v2_pass and not v1_pass:
        print("✅ v2 배포 승인 — v1은 Gate FAIL, v2는 PASS")
        return "v2"
    elif not v2_pass:
        print("❌ 배포 차단 — v2도 Gate FAIL 존재")
        sys.exit(1)
    else:
        # 둘 다 PASS이면 Gate A 점수가 높은 버전 선택
        a1 = gates_v1.get("A", {}).get("score", 0)
        a2 = gates_v2.get("A", {}).get("score", 0)
        winner = "v2" if a2 >= a1 else "v1"
        print(f"✅ {winner} 배포 승인 (Gate A: v1={a1:.0%}, v2={a2:.0%})")
        return winner
```

```bash
python Evaluator_Examples/ch04_group_a.py   # 17개 FAIL 시나리오 재현
python Evaluator_Examples/ch20_deployment.py       # v1 vs v2 Gate 점수 비교
```

- `ch04_group_a.py` 실행 결과로 각 Config에서 FAIL을 유발하는 임계값을 파악한 뒤 `ch18_cicd_gate.py` Config 파라미터를 조정한다
- `ch20_deployment.py`는 두 버전의 독립 `PerformanceMonitor`에서 Gate 점수를 비교해 어느 버전을 배포할지 자동으로 판정한다
- 두 파일을 CI 파이프라인 단계로 순서대로 실행하면 "FAIL 기준 보정 → 버전 비교 → 배포 결정"의 완전한 흐름이 구성된다
