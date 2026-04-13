# Chapter 13. CI/CD 품질 게이팅

> **이 챕터에서 배우는 것**
> - 배포 파이프라인에 AI 품질 검문소를 설치하는 이유와 방법
> - `agent-eval gate` CLI의 모든 옵션과 동작 원리
> - GitHub Actions, GitLab CI, Jenkins 완전 통합 패턴
> - 환경별(dev/staging/prod) 차등 임계값 전략
> - 게이팅 실패 시 즉각 대응 절차

---

## 13.1 품질 게이팅이란 — 배포 파이프라인에 품질 검문소 세우기

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

## 13.2 agent-eval gate CLI 완전 가이드

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

## 13.3 GitHub Actions 통합

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

## 13.4 GitLab CI / Jenkins 통합 패턴

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

## 13.5 배포 환경별 임계값 전략

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

## 13.6 게이팅 실패 시 대응 절차

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

- **GitHub Actions 통합** 시 `--junit-xml` 옵션으로 JUnit 리포트를 생성하고, `actions/github-script`로 PR 코멘트에 품질 지표를 자동 게시할 수 있다.

- **환경별 차등 임계값** 전략을 사용하라. dev는 느슨하게, staging은 보통, prod는 엄격하게. 브랜치에 따라 `--tcr`, `--accuracy`, `--p95-latency` 값을 다르게 지정하거나, Python `QuickEval.gate()` 메서드에서 환경 변수로 분기한다.

- 게이팅 실패는 나쁜 것이 아니다. **배포 전에 문제를 발견했다**는 의미다. 낮은 케이스를 분석해 임계값 조정 vs 코드 수정을 판단하고, 회귀 케이스는 골든 데이터셋에 추가해 재발을 방지하라.
