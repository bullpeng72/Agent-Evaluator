# 배포 가이드

**Agent-Evaluator v0.8.1** — CI/CD 통합 및 프로덕션 배포 전략

---

## 목차

1. [개요](#개요)
2. [설치 및 환경 설정](#설치-및-환경-설정)
3. [데코레이터 방식 배포 패턴](#데코레이터-방식-배포-패턴)
4. [CI/CD 통합](#cicd-통합)
5. [Docker 배포](#docker-배포)
6. [환경별 설정](#환경별-설정)
7. [모니터링 통합](#모니터링-통합)
8. [Golden Dataset 기반 회귀 테스트](#golden-dataset-기반-회귀-테스트)
9. [성능 최적화](#성능-최적화)
10. [트러블슈팅](#트러블슈팅)

---

## 개요

이 가이드는 Agent-Evaluator를 프로덕션 환경에 배포하고 CI/CD 파이프라인에 통합하는 방법을 다룬다.

대상 독자:
- AI 에이전트를 프로덕션에 배포하는 개발자/MLOps 엔지니어
- 자동화된 품질 게이트를 구축하려는 팀

주요 배포 시나리오:
- **로컬 개발** — 빠른 실험, 느슨한 임계값
- **CI/CD 파이프라인** — GitHub Actions / GitLab CI, 자동 품질 게이트
- **프로덕션 모니터링** — Phoenix + OTLP, 실시간 스팬 추적

---

## 설치 및 환경 설정

### 설치 variants

```bash
# 기본 설치 — LLMJudge · 대시보드 · OTEL 모니터링 · PDF 포함 (권장)
pip install agent-evaluator

# 전체 설치 (crewai/autogen 포함, 10분+)
pip install "agent-evaluator[full]"

# 개발 환경 (소스에서 설치)
pip install -e ".[dev]"
```

### `.env` 파일 설정

```bash
# .env (Git에 커밋하지 말 것)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 결과 저장 디렉토리 (기본값: results/)
AGENT_EVALUATOR_OUTPUT_DIR=results/

# 환경 구분
ENV=production
LOG_LEVEL=INFO

# 선택: 알림
ALERT_WEBHOOK=https://hooks.slack.com/services/...
```

### 설정 마법사

```bash
# 대화형 API 키 설정 — .env 파일 자동 생성
agent-eval init

# 현재 설정 상태 확인
agent-eval check
```

### 설치 검증

```bash
python -c "from agent_evaluator import PerformanceMonitor, QuickEval; print('OK')"
agent-eval --version
```

---

## 데코레이터 방식 배포 패턴

기존 에이전트 코드에 평가를 추가할 때 가장 간단한 방법이다.

### QuickEval — 원스톱 시작

```python
from agent_evaluator import QuickEval

# 1줄로 시작 — PerformanceMonitor + EvalDecorator 자동 구성
eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

@eval.tool_use
def tool_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})

eval.save()                         # results/quickeval.json + quickeval.html
eval.gate(tcr=85, accuracy=70)      # 실패 시 sys.exit(1)
```

### AGENT_EVAL_PRESETS — 용도별 사전 설정

```python
from agent_evaluator import QuickEval
from agent_evaluator.decorators import AGENT_EVAL_PRESETS

# production: flush_every=50 + anomaly_detection=True
eval = QuickEval("results/", preset="production")

# development: llm_judge=True + auto_detect_framework=True
eval = QuickEval("results/", preset="development")

# testing: 경량 평가
eval = QuickEval("results/", preset="testing")

# canary: 카나리 배포 최적
eval = QuickEval("results/", preset="canary")
```

### agent_eval 데코레이터 — 프레임워크별 메타데이터 자동 추출

```python
from agent_evaluator.decorators import agent_eval
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor("results/")

# framework= 파라미터로 tool_calls/chain_steps/tokens_used 자동 추출
@agent_eval(monitor, task_type="tool_use", framework="langchain")
def langchain_agent(question: str, ground_truth: str = "") -> str:
    return agent_executor.invoke({"input": question})

# 지원 프레임워크 21개: langchain, langgraph, crewai, autogen, dspy,
# pydanticai, anthropic, openai, gemini, llamaindex, haystack 등

# RAG 모드 — context_arg + hallucination + IR 자동 활성화
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke(question)
```

### 팩토리 메서드 — 용도별 최적 설정

```python
from agent_evaluator import PerformanceMonitor

# RAG 평가 — hallucination_detection 기본 활성
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")

# 보안 에이전트 — security metrics 기본 활성
monitor = PerformanceMonitor.for_secure_agents(output_dir="results/")
```

### Context Manager — 세션 단위 평가

데코레이터를 적용할 수 없는 외부 코드나 복잡한 흐름에서는 `eval_context`를 사용합니다.

```python
from agent_evaluator import evaluation_session
from agent_evaluator.decorators import eval_context

with evaluation_session("evaluation") as monitor:
    for task in tasks:
        with eval_context(monitor, task_type="qa",
                          question=task["question"],
                          ground_truth=task.get("answer", "")) as ctx:
            ctx.response = agent.run(task["question"])
# 세션 종료 시 results/evaluation.json + .html 자동 저장 (예외 발생 시에도 안전)
```

> **권장**: 에이전트 함수에 `@agent_eval` 데코레이터를 붙이는 방식이 더 간결합니다. `eval_context`는 데코레이터를 붙일 수 없는 경우의 탈출구입니다.

---

## CI/CD 통합

### GitHub Actions

```yaml
# .github/workflows/quality-gate.yml
name: Agent Quality Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  quality-gate:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install agent-evaluator

      - name: Run evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/run_evaluation.py

      - name: Quality Gate
        run: |
          agent-eval gate results/eval.json --tcr 85 --accuracy 70

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-results
          path: results/
```

### `agent-eval gate` CLI

```bash
# 기본 사용
agent-eval gate results/eval.json --tcr 85 --accuracy 70

# 추가 지표 포함
agent-eval gate results/eval.json \
  --tcr 85 \
  --accuracy 70 \
  --quality 3.5 \
  --hallucination 0.1

# 실패 시 sys.exit(1) → CI/CD 파이프라인 중단
```

### pytest Quality Gate

```python
# tests/test_quality_gate.py
import pytest
from agent_evaluator import QuickEval

def test_agent_quality():
    """에이전트 품질 임계값 검증"""
    eval = QuickEval("results/")

    @eval.qa
    def agent(question, ground_truth=""):
        return my_agent_fn(question)

    test_cases = [
        {"question": "한국의 수도는?", "ground_truth": "서울"},
        {"question": "Python 창시자는?", "ground_truth": "귀도 반 로섬"},
    ]

    for case in test_cases:
        agent(case["question"], ground_truth=case["ground_truth"])

    # 실패 시 pytest AssertionError
    result = eval.gate(tcr=80, accuracy=70, raise_on_fail=False)
    assert result, f"Quality gate failed: {eval.summary()}"
```

```bash
# pytest 실행
pytest tests/test_quality_gate.py -v
```

---

## Docker 배포

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY pyproject.toml .
RUN pip install --no-cache-dir agent-evaluator

# 애플리케이션 코드
COPY agent_evaluator/ ./agent_evaluator/

# 결과 디렉토리
RUN mkdir -p results/

ENV PYTHONUNBUFFERED=1
ENV ENV=production

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import agent_evaluator; print('OK')" || exit 1

EXPOSE 8765

CMD ["agent-eval", "dashboard", "--port", "8765", "--no-open"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  dashboard:
    build: .
    container_name: agent-evaluator-dashboard
    ports:
      - "8765:8765"
    environment:
      - ENV=${ENV:-production}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - ./results:/app/results          # 평가 결과 영속화
      - ./data:/app/data                # Golden Dataset
      - ./.env:/app/.env
    command: agent-eval dashboard --port 8765 --no-open
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  results:
  data:
```

```bash
# 실행
docker-compose up -d dashboard

# 로그 확인
docker-compose logs -f dashboard

# 대시보드 접속
# http://localhost:8765
```

---

## 환경별 설정

### 환경 변수 요약

| 변수 | 개발 | 스테이징 | 프로덕션 |
|------|------|----------|----------|
| `ENV` | `development` | `staging` | `production` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` |
| TCR 임계값 | 70% | 85% | 95% |
| Accuracy 임계값 | 65% | 80% | 90% |

### 환경별 PerformanceMonitor 설정

```python
import os
from agent_evaluator import PerformanceMonitor

def get_monitor() -> PerformanceMonitor:
    """환경에 따라 최적 Monitor 반환"""
    env = os.getenv("ENV", "development")

    if env == "production":
        return PerformanceMonitor(
            output_dir="results/",
            enable_security_metrics=True,
            auto_save=True,
            auto_save_interval=50,
        )
    elif env == "staging":
        return PerformanceMonitor(
            output_dir="results/",
            enable_hallucination_detection=True,
            auto_save=True,
            auto_save_interval=20,
        )
    else:  # development
        return PerformanceMonitor(
            output_dir="results/",
        )
```

### AGENT_EVAL_PRESETS 상세

```python
from agent_evaluator import QuickEval

# production: flush_every=50, enable_anomaly_detection=True
eval = QuickEval("results/", preset="production")

# development: llm_judge=LLMJudgeConfig(), auto_detect_framework=True
eval = QuickEval("results/", preset="development")

# testing: 경량 평가 (외부 API 호출 최소화)
eval = QuickEval("results/", preset="testing")

# canary: 카나리 배포 — 트래픽 일부에만 적용
eval = QuickEval("results/", preset="canary")
```

---

## 모니터링 통합

### 개발/검증: FastAPI 대시보드

```bash
# 기본 실행 (포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 결과 디렉토리 지정
agent-eval dashboard results/

# 옵션
agent-eval dashboard --port 8080 --watch --no-open
```

대시보드는 `results/` 디렉토리의 JSON 파일을 자동 로드한다. 품질/성능/에이전틱/보안 관점별 탭을 제공한다.

### 프로덕션: Phoenix + OTLP 실시간 모니터링

```bash
# Phoenix 서버 기동 + OTLP 스팬 수신 설정
agent-eval monitor

# 포트 지정 (기본: 6006)
agent-eval monitor --port 6006

# 설치 상태 확인
agent-eval monitor --check
```

코드에서 OTEL 연결:

```python
from agent_evaluator.core.monitor import setup_otel

# Phoenix에 연결 (기본 설치에 포함)
setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-agent",
)

# 이후 PerformanceMonitor.record_task() 시 OTLP 스팬 자동 발행
monitor = PerformanceMonitor("results/")
```

```python
# 예제에서 자동 연결 패턴
def _try_setup_otel(project_name: str = "my-agent"):
    try:
        from agent_evaluator.core.monitor import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name=project_name)
        print(f"Phoenix 연결됨: http://localhost:6006 (project: {project_name})")
    except ImportError:
        pass  # 설치 오류 시 무시

_try_setup_otel("production-agent")
```

Phoenix UI에서 확인 가능한 항목:
- **Tracing** — 태스크별 스팬, 실행 시간, 오류
- **Evaluators** — TCR, Accuracy, Hallucination 점수
- **Datasets** — Golden Dataset 컨텍스트
- **Prompts** — 질문/정답 Playground 재현

---

## Golden Dataset 기반 회귀 테스트

프로덕션 배포 전 알려진 케이스에 대한 품질 회귀를 자동 검증한다.

### conftest.py 설정

```python
# tests/conftest.py
import json
import pytest

@pytest.fixture
def golden_dataset():
    with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
        return json.load(f)
```

### 회귀 테스트 작성

```python
# tests/test_quality_regression.py
from agent_evaluator import QuickEval

def test_quality_regression(golden_dataset):
    """Golden Dataset 기반 품질 회귀 테스트"""
    eval = QuickEval("results/")

    @eval.qa
    def agent(question, ground_truth=""):
        return my_agent(question)

    for pair in golden_dataset["qa_pairs"]:
        agent(pair["question"], ground_truth=pair["ground_truth"])

    # 실패 시 pytest 오류
    assert eval.gate(tcr=85, accuracy=70, raise_on_fail=False), (
        f"Quality regression detected: {eval.summary()}"
    )

def test_rag_regression(golden_dataset):
    """RAG 에이전트 hallucination 회귀 테스트"""
    eval = QuickEval.for_rag("results/")

    @eval.rag
    def rag_agent(question, context="", ground_truth=""):
        return rag_chain.invoke({"question": question, "context": context})

    for pair in golden_dataset.get("rag_pairs", []):
        rag_agent(
            pair["question"],
            context=pair["context"],
            ground_truth=pair["ground_truth"],
        )

    assert eval.gate(tcr=80, accuracy=75, hallucination=0.1, raise_on_fail=False)
```

### Golden Dataset 자동 갱신

```bash
# 평가 결과에서 고품질 케이스 자동 추출
agent-eval dataset build results/ --min-score 0.8

# 또는 Python에서
from agent_evaluator.datasets.builder import GoldenSetBuilder

builder = GoldenSetBuilder("data/golden_datasets/")
builder.merge_to_golden(new_cases, dataset_name="production_v2")
```

---

## 성능 최적화

### 장시간 실행 평가 — 자동 저장

```python
from agent_evaluator import PerformanceMonitor

# 50건마다 자동 저장 — OOM 방지
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,
    auto_save_filename="auto_checkpoint",
)
```

### 고트래픽 프로덕션 — 샘플링

```python
from agent_evaluator.decorators import agent_eval

# 10%만 평가 — 비용/성능 균형
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def production_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 조건부 샘플링 — 특정 조건에서만 평가
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kwargs: len(args[0]) > 100,  # 긴 질문만
)
def selective_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 데코레이터 주기 저장

```python
from agent_evaluator.decorators import agent_eval, batch_eval

# 10번 호출마다 저장
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question, ground_truth=""): ...

# batch_eval에도 동일 적용
@batch_eval(monitor, flush_every=5)
def batch_agent(questions, ground_truths=None): ...
```

---

## 트러블슈팅

### 주요 문제 및 해결책

| 문제 | 원인 | 해결책 |
|------|------|--------|
| `ModuleNotFoundError: agent_evaluator` | 패키지 미설치 | `pip install agent-evaluator` |
| `AuthenticationError: Invalid API key` | API 키 오류 | `.env` 확인, `agent-eval check` 실행 |
| `FileNotFoundError: results/` | 출력 디렉토리 없음 | `mkdir -p results/` 또는 `output_dir` 지정 |
| `ImportError: fastapi` | 기본 설치 미완료 | `pip install agent-evaluator` 재실행 |
| `ImportError: opentelemetry` | 기본 설치 미완료 | `pip install agent-evaluator` 재실행 |
| Quality Gate 항상 통과 | 트래커 비활성화 | `enable_hallucination_detection=True` 등 확인 |
| 보안 지표 0% | `enable_security_metrics` 미설정 | `PerformanceMonitor(enable_security_metrics=True)` |

### 설치 상태 확인

```bash
# CLI 상태 확인
agent-eval check

# 수동 확인
python -c "
from agent_evaluator import PerformanceMonitor, QuickEval
from agent_evaluator.decorators import agent_eval
print('core: OK')

try:
    from agent_evaluator.serve import server
    print('serve: OK')
except ImportError:
    print('serve: NOT installed — pip install agent-evaluator 재실행')

try:
    import opentelemetry
    print('otel: OK')
except ImportError:
    print('otel: NOT installed — pip install agent-evaluator 재실행')
"
```

### `.env` 파일 디버깅

```python
from agent_evaluator.config import load_env, get_settings

load_env()  # .env 로드
settings = get_settings()
print(settings)  # 현재 설정 출력
```

### 보안 지표 미수집 문제

```python
# 잘못된 설정 — 보안 트래커 초기화만 되고 호출 안 됨 (v0.7.2 이하 버그, v0.7.3 CRITICAL 수정)
monitor = PerformanceMonitor()  # enable_security_metrics 기본값 False

# 올바른 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,  # 반드시 명시
)
# v0.7.3부터 record_task() 시 5개 보안 트래커 자동 호출 (CRITICAL 버그 수정)
```

### 프로덕션 배포 전 체크리스트

```bash
# 1. 패키지 임포트 확인
python -c "from agent_evaluator import PerformanceMonitor, QuickEval; print('OK')"

# 2. API 키 설정 확인
agent-eval check

# 3. .env가 Git에 포함되지 않았는지 확인
git check-ignore .env   # .env 출력되어야 함

# 4. 결과 디렉토리 확인
ls -la results/

# 5. Quality Gate 테스트
agent-eval gate results/sample.json --tcr 0 --accuracy 0   # 항상 통과 테스트
```

---

## 참고 문서

- [API 레퍼런스](./07_API_REFERENCE.md) — PerformanceMonitor, TaskResult, EvaluationReport
- [모니터 가이드](./12_MONITOR_GUIDE.md) — Phoenix + OTLP 상세 설정
- [프레임워크 비교](./11_FRAMEWORK_COMPARISON.md) — 21개 프레임워크 어댑터
- [예제 코드](../Evaluator_Examples/) — 21개 실행 가능 예제
