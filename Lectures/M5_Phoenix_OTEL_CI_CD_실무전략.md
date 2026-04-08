# M5: Phoenix · OpenTelemetry · CI/CD — 프로덕션 실무 전략

> **Agent-Evaluator v0.7.4** 기준. 설치: `pip install "agent-evaluator[otel]"`

---

## 목차

1. [OpenTelemetry 개념과 에이전트 평가](#1-opentelemetry-개념과-에이전트-평가)
2. [Arize Phoenix 시작하기](#2-arize-phoenix-시작하기)
3. [Phoenix 4개 메뉴 활용법](#3-phoenix-4개-메뉴-활용법)
4. [실시간 스팬 속성 활용](#4-실시간-스팬-속성-활용)
5. [CI/CD 품질 게이팅](#5-cicd-품질-게이팅)
6. [골든 데이터셋 구축 전략](#6-골든-데이터셋-구축-전략)
7. [프로덕션 운영 전략](#7-프로덕션-운영-전략)
8. [종합 실무 파이프라인](#8-종합-실무-파이프라인)

---

## 1. OpenTelemetry 개념과 에이전트 평가

### 1-1. OpenTelemetry란?

**OpenTelemetry(OTEL)**는 분산 시스템의 관찰 가능성(Observability)을 위한 오픈 표준이다. CNCF(Cloud Native Computing Foundation)가 관리하며, 분산 추적(Distributed Tracing), 메트릭(Metrics), 로그(Logs)를 통합하는 벤더 중립적 SDK와 프로토콜을 제공한다.

AI 에이전트 평가에 OTEL이 중요한 이유는 간단하다. **에이전트 호출 하나 = 하나의 스팬(Span)**이기 때문이다. 에이전트가 여러 도구를 호출하면 각 도구 호출이 자식 스팬(Child Span)이 된다. 이를 통해 다음을 한눈에 파악할 수 있다:

- 어느 단계에서 시간이 가장 오래 걸리는가? (병목 탐지)
- 어느 호출에서 환각(hallucination)이 발생했는가?
- 토큰 사용량은 요청별로 얼마나 다른가?

```
사용자 요청
    └── 에이전트 호출 (루트 스팬, ~2.3초)
            ├── 도구 호출: search_web (자식 스팬, ~0.8초)
            ├── 도구 호출: summarize   (자식 스팬, ~1.1초)
            └── 최종 응답 생성         (자식 스팬, ~0.4초)
```

### 1-2. 핵심 개념

| 개념 | 설명 | Agent-Evaluator에서의 의미 |
|------|------|--------------------------|
| **Span** | 단일 작업 단위. 시작/종료 시각 + 속성 보유 | `record_task()` 1회 호출 = 1개 스팬 |
| **Trace** | 연관된 스팬들의 집합 (트리 구조) | 에이전트 세션 전체 = 1개 트레이스 |
| **Attribute** | 스팬에 부착되는 키-값 메타데이터 | `ae.accuracy_score`, `ae.task_type` 등 |
| **Resource** | 서비스 자체를 설명하는 메타데이터 | `service.name`, `openinference.project.name` |
| **OTLP** | OpenTelemetry Line Protocol — 스팬 전송 프로토콜 | HTTP/gRPC로 Phoenix에 전송 |

### 1-3. Agent-Evaluator의 OTEL 통합 구조

`PerformanceMonitor.record_task()`가 호출될 때 OTEL이 활성화되어 있으면 자동으로 OTLP 스팬이 발행된다. **데코레이터를 사용하면 `record_task()`가 내부에서 자동 호출**되므로, `setup_otel()` 한 번만 호출해두면 모든 데코레이터 호출마다 스팬이 자동 발행된다.

```python
# 데코레이터 방식 — setup_otel() 1회 설정으로 전체 자동화
from agent_evaluator.core.otel.provider import setup_otel
from agent_evaluator.decorators import agent_eval
from agent_evaluator import PerformanceMonitor

setup_otel(
    endpoint="http://localhost:6006/v1/traces",
    service_name="my-agent-service"
)

monitor = PerformanceMonitor("results/")

@agent_eval(monitor, task_type="tool_use", framework="langchain")
def my_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# 호출 → record_task() 내부 자동 호출 → OTLP 스팬 자동 발행 → Phoenix 전송
my_agent("검색해줘", ground_truth="...")
```

**데코레이터 → OTEL 전체 흐름:**
```
@agent_eval 실행
    → TaskResult 자동 생성 (execution_time, tokens_used, tool_calls, framework 포함)
    → monitor.record_task(task)
        → Layer 1/2 트래커 분배 (평가 지표 집계)
        → OTEL 활성 시: TaskResult 필드 → span 속성으로 자동 변환 → Phoenix로 전송
```

발행되는 스팬에는 20개 이상의 속성이 자동으로 포함된다:

```
ae.task_id               = "task_001"
ae.task_type             = "qa"
ae.framework             = "langchain"
ae.completion_score      = 0.95
ae.accuracy_score        = 0.87
ae.execution_time        = 1.23
ae.tokens_used           = 850
ae.tool_calls_count      = 3
ae.tool_names            = '["search_web", "calculator", "summarize"]'
ae.hallucination_detected = False
ae.security_threat_detected = False
openinference.span.kind  = "AGENT"
input.value              = "한국의 GDP는?"
output.value             = "2023년 기준 약 1조 7천억 달러입니다."
```

### 1-4. 설치

```bash
# OTEL 지원 포함 설치
pip install "agent-evaluator[otel]"

# 또는 전체 설치 (otel 포함)
pip install "agent-evaluator[all]"

# 설치 확인
agent-eval monitor --check
```

---

## 2. Arize Phoenix 시작하기

### 2-1. Arize Phoenix란?

**Arize Phoenix**는 오픈소스 LLM 관찰 가능성 플랫폼이다. OpenInference 표준을 따르며, OTLP로 전송된 스팬을 수신해 웹 UI로 시각화한다. 로컬에서 무료로 실행할 수 있으며, 별도 클라우드 계정 없이도 완전히 동작한다.

주요 특징:
- **완전 오픈소스** — Apache 2.0 라이선스
- **로컬 실행** — 인터넷 연결 불필요
- **LLM 특화** — 프롬프트/응답 뷰어, 평가 점수 오버레이
- **데이터 영속성** — SQLite 기반 로컬 저장

### 2-2. agent-eval monitor CLI

가장 간단한 시작 방법은 `agent-eval monitor` 명령어다. Phoenix 서버 실행과 OTLP 엔드포인트 설정을 한 번에 처리한다.

```bash
# Phoenix 서버 시작 (기본 포트 6006)
agent-eval monitor

# 포트 변경
agent-eval monitor --port 6007

# OTEL 패키지 설치 여부 및 포트 점유 확인
agent-eval monitor --check
```

실행 후 브라우저에서 `http://localhost:6006`을 열면 Phoenix UI가 표시된다.

```
$ agent-eval monitor
[Agent-Evaluator] Phoenix 서버를 시작합니다...
[Agent-Evaluator] OTLP 엔드포인트: http://localhost:6006/v1/traces
[Agent-Evaluator] Phoenix UI: http://localhost:6006
[Agent-Evaluator] 서비스명: agent-evaluator
[Agent-Evaluator] Phoenix가 준비되었습니다. Ctrl+C로 종료.
```

### 2-3. 코드에서 OTEL 설정

```python
from agent_evaluator.core.otel.provider import setup_otel
from agent_evaluator import PerformanceMonitor, QuickEval

# 방법 1: setup_otel() 직접 호출
setup_otel(
    endpoint="http://localhost:6006/v1/traces",
    service_name="my-qa-agent",
    enable_metrics=False  # Phoenix는 /v1/metrics 미지원, False 권장
)

# 방법 2: PerformanceMonitor에서 직접 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_otel_child_spans=True  # chain_steps를 자식 스팬으로 발행
)

# 방법 3: QuickEval 사용 (OTEL 자동 연결)
eval = QuickEval("results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

### 2-4. 프로젝트 분리

Phoenix는 `openinference.project.name` Resource 속성으로 프로젝트를 구분한다. 예제별, 서비스별로 별도 프로젝트를 만들 수 있다.

```python
setup_otel(
    endpoint="http://localhost:6006/v1/traces",
    service_name="customer-support-agent",  # Phoenix 프로젝트명으로 사용됨
)
```

Phoenix UI 좌측 사이드바에서 프로젝트를 선택하면 해당 서비스의 스팬만 필터링된다.

---

## 3. Phoenix 4개 메뉴 활용법

### 3-1. Tracing 탭

**Tracing** 탭은 Phoenix의 핵심이다. 모든 에이전트 호출을 타임라인으로 시각화하고, 각 스팬의 속성을 상세히 볼 수 있다.

**워터폴 뷰(Waterfall View)**에서는 각 스팬의 시작/종료 시각을 막대 그래프로 표시한다. 자식 스팬(도구 호출)이 들여쓰기되어 나타나므로, 전체 처리 흐름을 한눈에 파악할 수 있다.

```python
# enable_otel_child_spans=True 설정 시 chain_steps가 자식 스팬으로 발행됨
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_otel_child_spans=True
)

# 이렇게 record하면 Phoenix Tracing에서 워터폴로 보임:
# └── 루트 스팬: task_001 (2.3초)
#         ├── search_web (0.8초)
#         ├── calculate  (0.3초)
#         └── summarize  (1.2초)
```

**주요 활용 시나리오:**

```
시나리오 1 — 병목 탐지
  Filter: ae.execution_time > 5.0
  → 느린 호출 목록 확인
  → 워터폴에서 어느 자식 스팬이 가장 오래 걸리는지 확인

시나리오 2 — 환각 발생 추적
  Filter: ae.hallucination_detected = True
  → 환각이 발생한 호출 목록
  → 해당 스팬의 input.value, output.value 확인
  → 어떤 질문에서 환각이 발생하는지 패턴 분석

시나리오 3 — 프레임워크별 성능 비교
  Group by: ae.framework
  → LangChain vs LangGraph vs CrewAI 레이턴시 비교
```

### 3-2. Evaluators 탭

**Evaluators** 탭은 트레이스에 평가 점수를 오버레이한다. LLMJudge나 외부 평가 도구의 결과를 트레이스와 연결해 "이 호출이 왜 나쁜 점수를 받았는가"를 맥락과 함께 파악할 수 있다.

```python
from agent_evaluator import QuickEval, LLMJudge

eval = QuickEval.for_llm_judge(
    "results/",
    model="claude-sonnet-4-6"   # LLMJudge 사용 모델
)

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    response = call_llm(question)
    return response

# LLMJudge 결과 (completeness, relevance, factual_consistency)가
# 스팬 속성으로 포함되어 Evaluators 탭에 표시됨
```

**과거 트레이스 재평가:**

Phoenix Evaluators 탭에서는 기존에 수집된 트레이스를 새로운 평가 기준으로 일괄 재평가할 수 있다. 지난주 수집된 데이터를 더 엄격한 기준으로 다시 채점하는 것이 가능하다.

```python
# 예: 지난주 결과를 더 엄격한 기준으로 재평가
judge = LLMJudge(model="claude-sonnet-4-6")

# Phoenix Evaluators API를 통해 배치 재평가
# (Phoenix UI → Evaluators → "Run Evaluator" → 기간 선택)
```

### 3-3. Datasets 탭

**Datasets** 탭은 골든 데이터셋을 Phoenix에서 직접 관리한다. `GoldenSetBuilder`로 추출한 케이스를 이 탭에 업로드하면 버전 관리가 가능해진다.

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(output_dir="data/golden_datasets/")

# 방법 1: 파일에서 케이스 로드 후 Phoenix에 업로드
cases = builder.load_candidates("data/golden_datasets/candidates.json")
approved = [c for c in cases if c.get("score", 0) >= 0.8]

# Phoenix Datasets 탭에 업로드 (1-call 래퍼)
builder.push_to_phoenix(
    cases=approved,
    dataset_name="golden_v2_2026_04"
)
# → dataset.id, dataset.version, dataset.record_count 속성 자동 설정

# 방법 2: CLI로 직접 빌드 후 업로드
# agent-eval dataset build production_results/ --min-score 0.8
```

Phoenix Datasets 탭에서 볼 수 있는 정보:
- 데이터셋 이름 및 버전 (`dataset.version`)
- 레코드 수 (`dataset.record_count`)
- 각 레코드의 input/output/ground_truth
- 과거 버전과의 diff

### 3-4. Prompts 탭

**Prompts** 탭은 프롬프트 템플릿을 관리하고 **Playground**에서 재현(Replay)할 수 있다.

`llm.prompts` 스팬 속성에 질문/정답 JSON 배열을 넣으면 Phoenix가 이를 Prompts 탭에서 파싱한다.

```python
# 스팬 속성에 프롬프트 정보 포함 (PerformanceMonitor가 자동 처리)
# 수동으로 추가하려면:
import json
span.set_attribute("llm.prompts", json.dumps([
    {"role": "user", "content": "한국의 수도는?"},
    {"role": "assistant", "content": "서울입니다."}
]))
span.set_attribute("input.mime_type", "text/plain")
span.set_attribute("output.mime_type", "text/plain")
```

**Playground 활용:**

1. Tracing 탭에서 특정 스팬 선택
2. "Open in Playground" 클릭
3. 프롬프트 수정 후 재실행
4. 원본 응답과 비교

**A/B 테스트 워크플로우:**

```
1. 동일한 골든 데이터셋으로 프롬프트 A 실행
2. 동일한 골든 데이터셋으로 프롬프트 B 실행
3. Phoenix Evaluators 탭에서 두 실행의 점수 비교
4. 통계적으로 유의한 차이가 있는 케이스 식별
```

---

## 4. 실시간 스팬 속성 활용

### 4-1. 전체 스팬 속성 목록

Agent-Evaluator가 자동으로 설정하는 스팬 속성 전체 목록:

```python
# ae.* 네임스페이스 — Agent-Evaluator 커스텀 속성
ae.task_id                    # 태스크 ID (예: "task_001")
ae.task_type                  # 태스크 유형 (예: "qa", "tool_use")
ae.framework                  # 사용 프레임워크 (예: "langchain")
ae.completion_score           # 완료율 (0.0 ~ 1.0)
ae.accuracy_score             # 정확도 (0.0 ~ 1.0)
ae.execution_time             # 실행 시간 (초)
ae.tokens_used                # 총 토큰 사용량
ae.tool_calls_count           # 도구 호출 횟수
ae.tool_names                 # 도구 이름 목록 (JSON 배열 문자열)
ae.hallucination_detected     # 환각 탐지 여부 (bool)
ae.security_threat_detected   # 보안 위협 탐지 여부 (bool)
ae.anomaly_detection_enabled  # 이상 탐지 활성화 여부 (bool)
ae.attempts                   # 시도 횟수 (재시도 포함)

# openinference.* 네임스페이스 — OpenInference 표준
openinference.span.kind       # "AGENT", "LLM", "TOOL", "CHAIN" 중 하나
openinference.project.name    # 서비스/프로젝트 이름

# LLM 관련
llm.prompts                   # 프롬프트 JSON 배열 (Prompts 탭 연동)
input.value                   # 입력 텍스트
output.value                  # 출력 텍스트
input.mime_type               # 입력 MIME 타입 (기본: "text/plain")
output.mime_type              # 출력 MIME 타입

# 데이터셋 관련 (골든셋 연동 시)
dataset.id                    # 데이터셋 ID
dataset.version               # 데이터셋 버전
dataset.record_count          # 레코드 수
```

### 4-2. Phoenix에서 스팬 쿼리하기

Phoenix UI의 Tracing 탭에서 필터 표현식을 사용할 수 있다:

```
# 정확도가 낮은 QA 태스크
ae.accuracy_score < 0.7 AND ae.task_type = "qa"

# 환각이 발생한 스팬
ae.hallucination_detected = True

# LangChain 프레임워크에서 5초 이상 걸린 호출
ae.framework = "langchain" AND ae.execution_time > 5.0

# 도구를 3개 이상 호출한 에이전트
ae.tool_calls_count >= 3

# 보안 위협이 탐지된 호출
ae.security_threat_detected = True
```

### 4-3. child spans 활성화 예제

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval, EvalMetadata
from agent_evaluator.core.otel.provider import setup_otel

# OTEL 초기화
setup_otel(
    endpoint="http://localhost:6006/v1/traces",
    service_name="multi-tool-agent"
)

# child spans 활성화
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_otel_child_spans=True  # chain_steps → 자식 스팬
)

# @agent_eval + EvalMetadata로 chain_steps 주입 → Phoenix 자식 스팬 발행
@agent_eval(monitor, task_type="tool_use")
def multi_tool_agent(question: str, ground_truth: str = "") -> str:
    weather = weather_api(question)
    restaurants = restaurant_search(question)
    summary = summarize(weather, restaurants)
    return summary, EvalMetadata(
        tool_calls=["weather_api", "restaurant_search", "summarize"],
        extra={
            "chain_steps": [
                {"name": "weather_api", "duration": 0.6, "output": weather},
                {"name": "restaurant_search", "duration": 1.4, "output": restaurants},
                {"name": "summarize", "duration": 0.8, "output": summary},
            ]
        }
    )

multi_tool_agent(
    "서울의 날씨와 강남구 맛집을 알려주세요.",
    ground_truth="서울 날씨는 맑고 21도입니다.",
)
# Phoenix Tracing 탭에서 3개의 자식 스팬이 워터폴로 표시됨
```

---

## 5. CI/CD 품질 게이팅

### 5-1. agent-eval gate CLI

`agent-eval gate`는 평가 결과 파일을 읽어 임계값과 비교하고, 통과/실패 여부를 exit code로 반환한다.

```bash
agent-eval gate results/ci_run.json \
  --tcr 85 \
  --accuracy 70 \
  --p95-latency 3.0 \
  --hallucination 5 \
  --llm-judge 3.5 \
  --fail-on-regression 10 \
  --junit-xml test-results/gate-results.xml
```

**파라미터 설명:**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `--tcr` | float | Task Completion Rate 최솟값 (%) |
| `--accuracy` | float | 정확도 최솟값 (%) |
| `--p95-latency` | float | P95 레이턴시 최댓값 (초) |
| `--hallucination` | float | 환각 발생률 최댓값 (%) |
| `--llm-judge` | float | LLM Judge 평균 점수 최솟값 (0~5) |
| `--fail-on-regression` | int | 베이스라인 대비 허용 회귀율 (%) |
| `--junit-xml` | path | JUnit XML 결과 파일 경로 |

**Exit Code 의미:**

| Exit Code | 의미 | CI/CD 처리 |
|-----------|------|-----------|
| `0` | 모든 임계값 통과 | 빌드 계속 진행 |
| `1` | 하나 이상의 임계값 미달 | 빌드 실패 처리 |
| `2` | 회귀(Regression) 탐지 | 빌드 실패, 별도 알림 |

### 5-2. GitHub Actions 완전 예제

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
          pip install "agent-evaluator[llm]"
          # LLM Judge 사용 시: pip install "agent-evaluator[llm,eval]"

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
        # exit code 1 또는 2이면 스텝 실패 → 빌드 중단

      - name: JUnit 결과 업로드
        uses: actions/upload-artifact@v4
        if: always()  # 실패해도 항상 업로드
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
            const results = JSON.parse(fs.readFileSync('results/ci_run.json', 'utf8'));
            const summary = results.summary || {};
            
            const body = `## 🤖 Agent Quality Gate 결과
            
            | 지표 | 값 | 임계값 | 상태 |
            |------|-----|--------|------|
            | TCR | ${(summary.task_completion_rate * 100).toFixed(1)}% | ≥ 85% | ${summary.task_completion_rate >= 0.85 ? '✅' : '❌'} |
            | Accuracy | ${(summary.accuracy * 100).toFixed(1)}% | ≥ 70% | ${summary.accuracy >= 0.70 ? '✅' : '❌'} |
            | P95 Latency | ${summary.p95_latency?.toFixed(2)}s | ≤ 3.0s | ${summary.p95_latency <= 3.0 ? '✅' : '❌'} |
            
            [📊 전체 평가 결과 보기](https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }})
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

**CI 실행용 평가 스크립트 (`ci/run_evaluation.py`):**

```python
"""CI/CD 환경에서 실행되는 에이전트 평가 스크립트."""
import argparse
import sys
from agent_evaluator import QuickEval

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/ci_run.json")
    parser.add_argument("--sample-size", type=int, default=100)
    args = parser.parse_args()

    # CI 환경에 맞는 설정: LLM Judge 활성, 환각 탐지 활성, 샘플 전수 평가
    eval = QuickEval(
        output_dir="results/",
        enable_hallucination_detection=True,
        enable_llm_judge=True,
        judge_model="claude-sonnet-4-6",
        auto_save=True,
        auto_save_interval=10,
    )

    # 테스트 데이터 로드
    test_cases = load_test_cases("data/ci_test_cases.json")[:args.sample_size]

    @agent_eval(monitor, task_type="qa")
    def agent(question: str, ground_truth: str = "") -> str:
        return call_production_agent(question)

    # 평가 실행
    for case in test_cases:
        agent(question=case["question"], ground_truth=case["answer"])

    # 결과 저장
    eval.save(filename=args.output.replace(".json", ""))

    # 요약 출력
    summary = eval.summary()
    print(f"평가 완료: {len(test_cases)}개 태스크")
    print(f"  TCR: {summary.get('task_completion_rate', 0)*100:.1f}%")
    print(f"  Accuracy: {summary.get('accuracy', 0)*100:.1f}%")
    print(f"  P95 Latency: {summary.get('p95_latency', 0):.2f}s")


if __name__ == "__main__":
    main()
```

### 5-3. 프로그래밍 방식 게이팅

CLI 대신 Python 코드 안에서 직접 게이팅을 실행할 수 있다. 테스트 스크립트나 Jupyter 노트북에서 유용하다.

```python
from agent_evaluator import QuickEval

eval = QuickEval(
    "results/",
    enable_hallucination_detection=True,
)

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# 평가 실행
test_cases = [
    {"question": "파이썬 GIL이란?", "answer": "Global Interpreter Lock"},
    {"question": "TCP와 UDP의 차이는?", "answer": "TCP는 연결 지향..."},
    # ... 더 많은 케이스
]

for case in test_cases:
    agent(question=case["question"], ground_truth=case["answer"])

# 게이팅 — 임계값 미달 시 sys.exit(1) 호출
eval.gate(
    tcr=85,             # TCR 85% 이상
    accuracy=70,        # 정확도 70% 이상
    quality=3.5,        # 품질 점수 3.5/5.0 이상
    hallucination=5,    # 환각률 5% 이하
)
# 이 라인에 도달하면 모든 임계값 통과
print("품질 게이팅 통과! 배포 가능.")
```

### 5-4. 임계값 자동 생성

현재 실행 결과를 기반으로 임계값 설정 파일을 자동 생성할 수 있다. 처음 기준점을 잡을 때 유용하다.

```python
# 현재 지표의 95%를 임계값으로 자동 제안
eval.generate_gate_config("gate_config.json")

# 생성된 gate_config.json 예시:
# {
#   "tcr": 87.3,           # 현재 TCR 91.9%의 95%
#   "accuracy": 74.1,      # 현재 Accuracy 78.0%의 95%
#   "p95_latency": 4.2,    # 현재 P95 3.8초의 110%
#   "hallucination": 3.2,  # 현재 환각률 2.8%의 115%
#   "generated_at": "2026-04-08T10:30:00",
#   "based_on_tasks": 150
# }
```

생성된 설정 파일을 CLI에서 사용:

```bash
# gate_config.json의 임계값을 사용
agent-eval gate results/ci_run.json --config gate_config.json
```

---

## 6. 골든 데이터셋 구축 전략

### 6-1. 골든 데이터셋이 중요한 이유

골든 데이터셋(Golden Dataset)은 **재현 가능한 회귀 테스트의 핵심**이다. 매주 동일한 데이터셋으로 에이전트를 평가하면, 모델 업데이트나 프롬프트 변경이 성능에 미친 영향을 정확히 측정할 수 있다.

세 가지 수집 방법:

| 방법 | 특징 | 적합한 시기 |
|------|------|-----------|
| **수작업 제작** | 품질 최고, 시간 많이 소요 | 초기 기준점 설정 |
| **프로덕션 마이닝** | 실제 사용 패턴 반영 | 서비스 운영 2주+ |
| **합성 생성** | 대량 생성 가능, 현실성 낮을 수 있음 | 엣지 케이스 보완 |

### 6-2. 프로덕션 마이닝 워크플로우

가장 효과적인 방법은 프로덕션 트래픽에서 고품질 케이스를 자동으로 추출하는 것이다.

```python
from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.datasets.builder import GoldenSetBuilder

# Step 1: 프로덕션에서 2주간 평가 결과 수집
monitor = PerformanceMonitor(
    output_dir="production_results/",
    auto_save=True,
    auto_save_interval=50,  # 50건마다 자동 저장
)

# Step 2: CLI로 고품질 케이스 추출
# agent-eval dataset build production_results/ --min-score 0.8

# Step 3: Python에서 직접 추출
builder = GoldenSetBuilder(output_dir="data/golden_datasets/")

# min_score 0.8 이상의 케이스만 후보로 추출
candidates = builder.extract_candidates(
    results_dir="production_results/",
    min_score=0.8,
    max_candidates=500,          # 최대 500개
    deduplicate=True,            # 중복 제거
    strategy="stratified",       # task_type별 균등 샘플링
)

print(f"추출된 후보 케이스: {len(candidates)}개")

# Step 4: 후보 검토 (대시보드에서 bulk approve 가능)
builder.save_candidates(candidates, "data/golden_datasets/candidates_v2.json")
```

### 6-3. 대시보드에서 일괄 승인

```bash
# 대시보드 실행
agent-eval dashboard

# 브라우저에서 http://localhost:8765 접속
# → Golden Datasets → Candidates 탭
# → 체크박스로 선택 후 "Bulk Approve" 버튼 클릭
```

프로그래밍 방식으로도 가능:

```python
import httpx

# 대시보드 API로 일괄 승인
response = httpx.post(
    "http://localhost:8765/golden/candidates/candidates_v2/bulk-approve",
    json={"candidate_ids": ["case_001", "case_002", ...]}
)
print(f"승인된 케이스: {response.json()['approved_count']}개")
```

### 6-4. Phoenix에 업로드

```python
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder(output_dir="data/golden_datasets/")

# 승인된 케이스 로드
approved_cases = builder.load_approved("data/golden_datasets/candidates_v2.json")

# Phoenix Datasets 탭에 업로드
builder.push_to_phoenix(
    cases=approved_cases,
    dataset_name="golden_v2_2026_04",   # Phoenix에서 보이는 이름
)

# 또는 merge_to_golden() + push_to_phoenix() 별도 실행
builder.merge_to_golden(approved_cases, version="v2")
builder.push_to_phoenix(approved_cases, dataset_name="golden_v2")
```

### 6-5. 주간 회귀 테스트

```python
# weekly_regression.py — 매주 월요일 CI에서 실행

from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

# 골든 데이터셋 로드
builder = GoldenSetBuilder(output_dir="data/golden_datasets/")
golden_cases = builder.load_golden("data/golden_datasets/golden_v2.json")

eval = QuickEval(
    output_dir=f"results/regression_{TODAY}/",
    enable_hallucination_detection=True,
)

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> str:
    return call_production_agent(question)

# 전체 골든 데이터셋으로 평가
for case in golden_cases:
    agent(question=case["question"], ground_truth=case["answer"])

# 저장 및 게이팅
eval.save("regression_result")
eval.gate(tcr=90, accuracy=75)   # 회귀 테스트는 기준 더 엄격하게

# 이전 주 결과와 비교
prev_eval = QuickEval.replay(f"results/regression_{LAST_WEEK}/regression_result.json")
diff = eval.compare(prev_eval)
print(f"TCR 변화: {diff['tcr_delta']:+.1f}%")
print(f"Accuracy 변화: {diff['accuracy_delta']:+.1f}%")
```

---

## 7. 프로덕션 운영 전략

### 7-1. 샘플링 전략

프로덕션에서 모든 요청을 평가하면 레이턴시와 비용이 증가한다. 적절한 샘플링이 필수다.

```python
from agent_evaluator import QuickEval
from agent_evaluator.cost.policy import AdaptivePolicy, SamplingStage

# 방법 1: 고정 샘플링 (10%)
eval = QuickEval(
    "results/",
    sample_rate=0.1,   # 10%만 평가
)

# 방법 2: preset="production" 사용 (자동 설정)
eval = QuickEval(
    "results/",
    preset="production",   # sample_rate=0.1, flush_every=50, enable_anomaly=True 자동
)

# 방법 3: AdaptivePolicy — 예산 소진 시 자동으로 샘플링 줄임
from agent_evaluator.cost.policy import AdaptivePolicy

policy = AdaptivePolicy(
    monthly_budget_usd=50.0,      # 월 예산 50달러
    min_sample_rate=0.02,         # 최소 2%
    max_sample_rate=0.5,          # 최대 50%
)

# 방법 4: SamplingStage — task_type별 다른 샘플링 비율
stages = [
    SamplingStage(task_type="qa", sample_rate=0.05),         # QA: 5%
    SamplingStage(task_type="tool_use", sample_rate=0.20),   # 도구 사용: 20%
    SamplingStage(task_type="code_generation", sample_rate=0.30),  # 코드: 30%
]
```

### 7-2. 자동 저장 패턴

데이터 유실을 방지하는 세 가지 패턴:

```python
# 패턴 1: PerformanceMonitor 자동 저장
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,      # 10건마다 저장
    auto_save_filename="auto_checkpoint",
)

# 패턴 2: 데코레이터 flush_every
from agent_evaluator import agent_eval

@agent_eval(monitor, task_type="qa", flush_every=50, flush_filename="periodic")
def my_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
# 50번 호출마다 results/periodic.json 자동 저장

# 패턴 3: eval_context — 데코레이터 불가 시 세션 단위 탈출구
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("production_session") as monitor:
    for task in production_tasks:
        with eval_context(monitor, task_type="qa",
                          question=task["question"],
                          ground_truth=task.get("answer", "")) as ctx:
            ctx.response = process_task(task)
# 블록 종료 시 (예외 발생해도) 자동 저장

# 비동기 버전
import asyncio
from agent_evaluator import async_evaluation_session
from agent_evaluator.decorators import eval_context

async def run_async():
    async with async_evaluation_session("async_session") as monitor:
        async for task in async_task_stream():
            async with eval_context(monitor, task_type="qa",
                                    question=task["question"]) as ctx:
                ctx.response = await process_async(task)
```

### 7-3. 비용 최적화

각 평가 기능의 비용을 이해하고 선택적으로 활성화한다:

| 기능 | 비용 | 권장 설정 |
|------|------|---------|
| TCR / Latency / Token | 무료 (CPU 연산) | 항상 활성 |
| Hallucination Detection | 중간 (CPU 집약) | 스테이징, 10% 샘플링 |
| Security Metrics | 중간 (CPU 집약) | 보안 민감 서비스만 |
| LLMJudge | 유료 (API 호출) | 5% 샘플링 권장 |
| DeepEval / Ragas | 유료 (API 호출) | 오프라인 배치만 |

```python
# 프로덕션 최적화 설정 예시
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 프로덕션에서는 비활성
    enable_security_metrics=False,         # 보안 서비스만 활성
    auto_save=True,
    auto_save_interval=50,
)

# LLMJudge는 별도로 5% 샘플에만 적용
import random

@agent_eval(
    monitor,
    task_type="qa",
    enable_llm_judge=random.random() < 0.05,   # 5% 확률로만 LLMJudge 활성
    judge_model="claude-sonnet-4-6",
    flush_every=50,
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

### 7-4. 롤링 모니터링

```python
from agent_evaluator import QuickEval
from agent_evaluator.anomaly.detector import AnomalyDetector
from agent_evaluator.alerts.engine import AlertEngine
from agent_evaluator import SimpleTaskAlertRule

# 이상 탐지 설정
detector = AnomalyDetector(
    window_size=100,           # 최근 100건 기준
    z_score_threshold=3.0,    # 3 시그마 이상 = 이상
)

# 알림 규칙 정의
latency_alert = SimpleTaskAlertRule(
    name="high_latency",
    condition=lambda tr: tr.execution_time > 10.0,
    handler=lambda msg, tr: send_slack_alert(f"⚠️ 레이턴시 초과: {msg}"),
    severity="warning",
    cooldown=300,  # 5분 쿨다운
)

accuracy_alert = SimpleTaskAlertRule(
    name="low_accuracy",
    condition=lambda tr: tr.accuracy_score < 0.5,
    handler=lambda msg, tr: send_pagerduty_alert(f"🚨 정확도 급락: {msg}"),
    severity="critical",
    cooldown=60,
)

eval = QuickEval("results/", preset="production")

@eval(
    task_type="qa",
    alert_rules=[latency_alert, accuracy_alert],
    enable_anomaly_detection=True,
    flush_every=50,
)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# 디렉토리 감시 — 새 결과 파일 자동 재처리
def on_new_results(filepath: str):
    """새 평가 결과 파일이 생성되면 자동 호출."""
    report = QuickEval.replay(filepath)
    summary = report.summary()
    print(f"새 결과 처리: TCR={summary['task_completion_rate']*100:.1f}%")
    
    # 이상 패턴 감지
    anomalies = detector.scan_with_explain(report)
    if anomalies:
        for event in anomalies:
            print(f"이상 탐지: {event.description}")
            print(f"원인: {event.explanation}")
            print(f"권고: {event.recommendation}")

eval.watch(directory="results/", callback=on_new_results, max_watched_files=100)
```

### 7-5. 환경별 설정 가이드

| 설정 항목 | 개발(dev) | 스테이징(staging) | 프로덕션(prod) |
|---------|-----------|-----------------|--------------|
| `sample_rate` | 1.0 (전수) | 0.5 (50%) | 0.1 (10%) |
| `enable_hallucination_detection` | True | True | False |
| `enable_security_metrics` | True | True | 선택적 |
| `enable_llm_judge` | True | True | False |
| `flush_every` | 없음 (즉시) | 10 | 50 |
| `auto_save_interval` | 10 | 10 | 50 |
| OTEL 활성화 | 선택적 | True | True |
| Phoenix 연결 | 로컬 | 내부 서버 | 내부 서버 |
| `enable_anomaly_detection` | False | True | True |
| `preset` | `"development"` | — | `"production"` |

```python
import os

ENV = os.getenv("APP_ENV", "development")

EVAL_CONFIG = {
    "development": {
        "preset": "development",
        "sample_rate": 1.0,
        "enable_hallucination_detection": True,
        "enable_llm_judge": True,
        "auto_save_interval": 10,
    },
    "staging": {
        "sample_rate": 0.5,
        "enable_hallucination_detection": True,
        "enable_llm_judge": True,
        "auto_save_interval": 10,
        "auto_save": True,
    },
    "production": {
        "preset": "production",   # sample_rate=0.1, flush_every=50, anomaly=True 자동
        "enable_hallucination_detection": False,
        "enable_llm_judge": False,
        "auto_save": True,
    },
}

eval = QuickEval("results/", **EVAL_CONFIG[ENV])
```

---

## 8. 종합 실무 파이프라인

실제 서비스에 적용하는 엔드투엔드 파이프라인을 단계별로 구현한다.

### 8-1. 개발 단계 (Development)

```python
# dev/evaluate_agent.py
"""개발 환경: 전수 평가 + LLMJudge + 로컬 Phoenix"""
import os
from agent_evaluator import QuickEval
from agent_evaluator.core.otel.provider import setup_otel

# 로컬 Phoenix에 연결 (agent-eval monitor 먼저 실행)
if os.getenv("OTEL_ENABLED", "false").lower() == "true":
    setup_otel(
        endpoint="http://localhost:6006/v1/traces",
        service_name="my-agent-dev",
    )

eval = QuickEval(
    output_dir="results/dev/",
    preset="development",             # 전수 평가 + LLMJudge 활성
    enable_hallucination_detection=True,
    enable_security_metrics=True,
)

@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    """QA 에이전트 — 개발 환경에서 전수 평가."""
    return call_llm_api(question)

@agent_eval(monitor, task_type="tool_use")
def tool_agent(question: str, ground_truth: str = "") -> str:
    """도구 사용 에이전트 — 개발 환경."""
    return call_tool_agent(question)

# 테스트 실행
dev_cases = [
    {"question": "머신러닝의 정의는?", "answer": "데이터로부터 학습하는 알고리즘"},
    {"question": "파이썬 리스트 컴프리헨션 예시를 보여주세요.", "answer": "[x**2 for x in range(10)]"},
]

for case in dev_cases:
    qa_agent(question=case["question"], ground_truth=case["answer"])

# 결과 저장 + 요약 출력
eval.save("dev_evaluation")
summary = eval.summary()
print(f"\n개발 평가 완료:")
print(f"  TCR: {summary.get('task_completion_rate', 0)*100:.1f}%")
print(f"  Accuracy: {summary.get('accuracy', 0)*100:.1f}%")
print(f"  P95 Latency: {summary.get('p95_latency', 0):.2f}s")
print(f"  Total Cost: ${summary.get('total_cost_usd', 0):.4f}")
```

### 8-2. CI/CD 단계

```python
# ci/evaluate_and_gate.py
"""CI/CD: 배치 평가 → 품질 게이팅 → JUnit 결과"""
import sys
import os
from agent_evaluator import QuickEval

def run_ci_evaluation():
    eval = QuickEval(
        output_dir="results/ci/",
        enable_hallucination_detection=True,
        enable_llm_judge=True,
        judge_model="claude-sonnet-4-6",
        sample_rate=1.0,   # CI에서는 전수 평가
    )

    @agent_eval(monitor, task_type="qa")
    def agent(question: str, ground_truth: str = "") -> str:
        return call_production_agent(question)

    # 골든 데이터셋으로 평가
    from agent_evaluator.datasets.builder import GoldenSetBuilder
    builder = GoldenSetBuilder(output_dir="data/golden_datasets/")
    test_cases = builder.load_golden("data/golden_datasets/golden_v2.json")

    print(f"CI 평가 시작: {len(test_cases)}개 케이스")
    for i, case in enumerate(test_cases):
        agent(question=case["question"], ground_truth=case["answer"])
        if (i + 1) % 10 == 0:
            print(f"  진행: {i+1}/{len(test_cases)}")

    # 저장
    eval.save("ci_result")
    
    # 게이팅 — 실패 시 sys.exit(1)
    print("\n품질 게이팅 실행...")
    eval.gate(
        tcr=85,
        accuracy=70,
        quality=3.5,
        hallucination=5,
    )
    
    print("✅ 품질 게이팅 통과! 배포 가능.")
    return 0

if __name__ == "__main__":
    sys.exit(run_ci_evaluation())
```

### 8-3. 프로덕션 단계

```python
# production/agent_service.py
"""프로덕션: 샘플링 평가 + OTEL + Phoenix + 알림"""
import os
from agent_evaluator import QuickEval, SimpleTaskAlertRule
from agent_evaluator.core.otel.provider import setup_otel

# Phoenix에 OTEL 연결 (내부 Phoenix 서버)
PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://phoenix-server:6006/v1/traces")
setup_otel(
    endpoint=PHOENIX_ENDPOINT,
    service_name="production-qa-agent",
)

# 알림 규칙
alerts = [
    SimpleTaskAlertRule(
        name="critical_latency",
        condition=lambda tr: tr.execution_time > 15.0,
        handler=lambda msg, tr: notify_oncall(f"[CRITICAL] 레이턴시 초과: {msg}"),
        severity="critical",
        cooldown=120,
    ),
    SimpleTaskAlertRule(
        name="accuracy_drop",
        condition=lambda tr: tr.accuracy_score < 0.4,
        handler=lambda msg, tr: notify_slack(f"[WARNING] 정확도 급락: {msg}"),
        severity="warning",
        cooldown=300,
    ),
]

# 프로덕션 설정
eval = QuickEval(
    output_dir="/data/evaluation_results/",
    preset="production",         # sample_rate=0.1, flush_every=50, anomaly=True
    enable_hallucination_detection=False,   # 프로덕션에서는 CPU 절약
)

@eval(
    task_type="qa",
    alert_rules=alerts,
    flush_every=50,
    flush_filename="production_checkpoint",
)
def serve_request(question: str, ground_truth: str = "") -> str:
    """프로덕션 에이전트 서비스 엔드포인트."""
    return call_llm_api(question)


# FastAPI 등 웹 프레임워크와 통합
from fastapi import FastAPI
app = FastAPI()

@app.post("/ask")
async def ask(request: dict):
    question = request["question"]
    # ground_truth는 프로덕션에서는 없을 수 있음
    response = serve_request(question=question, ground_truth="")
    return {"answer": response}
```

### 8-4. 주간 회귀 테스트

```python
# scripts/weekly_regression.py
"""매주 월요일 자동 실행 — 골든 데이터셋 회귀 테스트"""
import os
from datetime import datetime, timedelta
from agent_evaluator import QuickEval
from agent_evaluator.datasets.builder import GoldenSetBuilder

TODAY = datetime.now().strftime("%Y%m%d")
LAST_WEEK = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
OUTPUT_DIR = f"results/regression/{TODAY}/"

def run_weekly_regression():
    # 골든 데이터셋 로드 (Phoenix에서 최신 버전 사용)
    builder = GoldenSetBuilder(output_dir="data/golden_datasets/")
    golden_cases = builder.load_golden("data/golden_datasets/golden_v2.json")
    
    print(f"주간 회귀 테스트: {len(golden_cases)}개 케이스")
    
    eval = QuickEval(
        output_dir=OUTPUT_DIR,
        enable_hallucination_detection=True,
        enable_llm_judge=True,
        judge_model="claude-sonnet-4-6",
        sample_rate=1.0,   # 회귀 테스트는 전수 평가
    )

    @agent_eval(monitor, task_type="qa")
    def agent(question: str, ground_truth: str = "") -> str:
        return call_production_agent(question)

    for case in golden_cases:
        agent(question=case["question"], ground_truth=case["answer"])

    eval.save("regression_result")

    # 이전 주 결과와 비교
    prev_result_path = f"results/regression/{LAST_WEEK}/regression_result.json"
    if os.path.exists(prev_result_path):
        prev_eval = QuickEval.replay(prev_result_path)
        diff = eval.compare(prev_eval)
        
        print(f"\n📊 전주 대비 변화:")
        print(f"  TCR:      {diff.get('tcr_delta', 0):+.1f}%")
        print(f"  Accuracy: {diff.get('accuracy_delta', 0):+.1f}%")
        print(f"  P95 Lat:  {diff.get('p95_latency_delta', 0):+.2f}s")
        
        # 회귀 발생 시 알림
        if diff.get("accuracy_delta", 0) < -5.0:
            notify_team(f"⚠️ 정확도 5% 이상 하락: {diff['accuracy_delta']:.1f}%")

    # 임계값 게이팅 (회귀 테스트는 기준 엄격)
    eval.gate(tcr=90, accuracy=75, hallucination=3)
    print("✅ 주간 회귀 테스트 통과!")

if __name__ == "__main__":
    run_weekly_regression()
```

### 8-5. 전체 파이프라인 요약

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-Evaluator 실무 파이프라인               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [개발] QuickEval(preset="development")                          │
│    │  - 전수 평가 + LLMJudge + Hallucination                     │
│    │  - 로컬 Phoenix → Tracing/Evaluators 탭 확인                │
│    ▼                                                            │
│  [PR 병합] GitHub Actions                                        │
│    │  - 100개 골든 케이스 자동 평가                               │
│    │  - agent-eval gate --tcr 85 --accuracy 70                  │
│    │  - JUnit XML → PR 코멘트 자동 게시                          │
│    ▼                                                            │
│  [프로덕션] QuickEval(preset="production")                       │
│    │  - 10% 샘플링 + 자동 저장 + OTEL → 내부 Phoenix             │
│    │  - 레이턴시/정확도 알림 규칙 활성                            │
│    │  - AdaptivePolicy로 예산 초과 시 샘플링 자동 감소            │
│    ▼                                                            │
│  [주간] 골든 데이터셋 회귀 테스트                                 │
│    │  - 프로덕션 결과에서 고품질 케이스 마이닝 (score ≥ 0.8)      │
│    │  - 전주 대비 지표 비교 + 회귀 알림                           │
│    │  - Phoenix Datasets 탭 업데이트                             │
│    └  Phoenix Prompts 탭에서 실패 케이스 프롬프트 재현/개선       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 마무리 체크리스트

프로덕션 배포 전 확인 사항:

- [ ] `agent-eval monitor --check` — OTEL 패키지 설치 확인
- [ ] `setup_otel()` 호출 확인 — Phoenix 엔드포인트 정확히 입력
- [ ] `preset="production"` 또는 `sample_rate` 설정 완료
- [ ] `flush_every` / `auto_save` 설정 — 데이터 유실 방지
- [ ] 알림 규칙 (`alert_rules`) 정의 — 레이턴시/정확도 임계값
- [ ] 골든 데이터셋 준비 — 최소 50개 이상 케이스
- [ ] CI/CD `agent-eval gate` 임계값 설정 완료
- [ ] GitHub Actions 워크플로우 파일 등록
- [ ] 주간 회귀 테스트 크론 스케줄 설정
- [ ] Phoenix에서 첫 스팬 수신 확인 — Tracing 탭

---

> **참고 파일**
> - `Evaluator_Examples/16_dashboard_demo.py` — 대시보드 + Phoenix OTEL 통합 데모
> - `Evaluator_Examples/17_phoenix_verification.py` — Phoenix 4개 메뉴 통합 데모
> - `Evaluator_Examples/13_golden_set_build.py` — GoldenSetBuilder 워크플로우
> - `agent_evaluator/core/otel/provider.py` — setup_otel() 구현
> - `agent_evaluator/cli/gate.py` — agent-eval gate 구현
