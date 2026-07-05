# 운영 가이드

설치 · Docker · 환경별 설정 · 성능 최적화 · 트러블슈팅

**v0.9.7 | Python 3.8+**

---

## 목차

1. [설치 variants](#1-설치-variants)
2. [환경 설정](#2-환경-설정)
3. [AGENT_EVAL_PRESETS — 용도별 사전 설정](#3-agent_eval_presets--용도별-사전-설정)
4. [Docker 배포](#4-docker-배포)
5. [환경별 PerformanceMonitor 설정](#5-환경별-performancemonitor-설정)
6. [성능 최적화](#6-성능-최적화)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 설치 variants

```bash
# 기본 설치 — 코어 평가 엔진 (LLMJudge 포함)
pip install agent-evaluator

# SDK 기능 포함 — 대시보드 · OTEL · PDF (운영 배포 권장)
pip install "agent-evaluator[sdk]"

# 모든 예제 실행 — sdk + deepeval/ragas/langchain
pip install "agent-evaluator[examples]"

# 프레임워크 통합 (사용자 에이전트가 해당 프레임워크를 사용할 때만)
pip install "agent-evaluator[langchain]"   # LangChain + LangGraph
pip install "agent-evaluator[eval]"        # DeepEval + Ragas
pip install "agent-evaluator[crewai]"      # CrewAI (무거움 — 전이 의존성 100개+)
pip install "agent-evaluator[autogen]"     # AutoGen (무거움, 단독 격리)
pip install "agent-evaluator[full]"        # 전체 (⚠️ crewai/autogen 포함, 10분+)

# 개발 환경 (소스에서 설치)
pip install -e ".[dev]"
```

### 설치 검증

```bash
python -c "from agent_evaluator import PerformanceMonitor, QuickEval; print('OK')"
agent-eval --version
```

---

## 2. 환경 설정

### .env 파일 설정

```bash
# .env (Git에 커밋하지 말 것 — .gitignore에 추가)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 결과 저장 디렉토리 (기본값: results/)
AGENT_EVALUATOR_OUTPUT_DIR=results/

# 프로젝트 루트 지정 (Git 루트 자동 탐지가 기본값)
# AGENT_EVALUATOR_ROOT=/path/to/my/project

# 환경 구분
ENV=production
LOG_LEVEL=INFO

# LLM Judge 제공자 (v0.8.3+)
# auto: API 키 보유 제공자 자동 선택 (기본값)
# openai | anthropic: 특정 제공자 우선 사용
AGENT_EVALUATOR_JUDGE_PROVIDER=auto

# 선택: 알림 Webhook
ALERT_WEBHOOK=https://hooks.slack.com/services/...
```

### 설정 마법사

```bash
# 대화형 API 키 설정 — .env 파일 자동 생성
agent-eval init

# 현재 설정 상태 확인
agent-eval check
```

### 결과 저장 경로 자동 감지 순서

| 우선순위 | 방법 |
|---------|------|
| 1 | 환경 변수 `AGENT_EVALUATOR_OUTPUT_DIR` (최우선) |
| 2 | 환경 변수 `AGENT_EVALUATOR_ROOT` (프로젝트 루트 지정) |
| 3 | Git 저장소 루트 아래 `results/` |
| 4 | 현재 작업 디렉토리 아래 `results/` (폴백) |

```python
# 현재 감지된 경로 확인
from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir

print("프로젝트 루트:", find_project_root())
print("결과 저장 경로:", get_evaluation_results_dir())
```

### 설정 디버깅

```python
from agent_evaluator.config import load_env, get_settings

load_env()  # .env 로드
settings = get_settings()
print(settings)  # 현재 설정 출력
```

---

## 3. AGENT_EVAL_PRESETS — 용도별 사전 설정

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

## 4. Docker 배포

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir agent-evaluator

COPY agent_evaluator/ ./agent_evaluator/

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
```

```bash
# 실행
docker-compose up -d dashboard

# 로그 확인
docker-compose logs -f dashboard

# 대시보드 접속: http://localhost:8765
```

---

## 5. 환경별 PerformanceMonitor 설정

### 환경 변수 요약

| 변수 | 개발 | 스테이징 | 프로덕션 |
|------|------|----------|----------|
| `ENV` | `development` | `staging` | `production` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` |
| TCR 임계값 | 70% | 85% | 95% |
| Accuracy 임계값 | 65% | 80% | 90% |

### 환경별 PerformanceMonitor 코드

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
        return PerformanceMonitor(output_dir="results/")
```

---

## 6. 성능 최적화

### 장시간 실행 평가 — 자동 저장

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,         # 50건마다 자동 저장 — OOM 방지
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

# 낮은 비율 샘플링 — 10%만 평가 (프로덕션 비용 절감)
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def selective_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 데코레이터 주기 저장

```python
# 10번 호출마다 저장
@agent_eval(monitor, task_type="qa", flush_every=10)
def agent(question, ground_truth=""): ...

# batch_eval에도 동일 적용
@batch_eval(monitor, flush_every=5)
def batch_agent(questions, ground_truths=None): ...
```

### LLM Judge 비용 절감

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,
    judge_sample_rate=0.1,     # 10%만 LLM Judge 채점 (비용 절감)
    judge_model="claude-haiku-4-5-20251001",  # 비용 효율적인 모델
)
```

---

## 7. 트러블슈팅

### 주요 문제 및 해결책

| 문제 | 원인 | 해결책 |
|------|------|--------|
| `ModuleNotFoundError: agent_evaluator` | 패키지 미설치 | `pip install agent-evaluator` |
| `AuthenticationError: Invalid API key` | API 키 오류 | `.env` 확인, `agent-eval check` 실행 |
| `FileNotFoundError: results/` | 출력 디렉토리 없음 | `mkdir -p results/` 또는 `output_dir` 지정 |
| `ImportError: fastapi` | `[sdk]` extra 미설치 | `pip install "agent-evaluator[sdk]"` |
| `ImportError: opentelemetry` | `[sdk]` extra 미설치 | `pip install "agent-evaluator[sdk]"` |
| Quality Gate 항상 통과 | 트래커 비활성화 | `enable_hallucination_detection=True` 등 확인 |
| 보안 지표 0% | `enable_security_metrics` 미설정 | `PerformanceMonitor(enable_security_metrics=True)` |
| Accuracy 항상 0 | ground_truth 미전달 | 함수 인자에 `ground_truth` 파라미터 추가 |

### 설치 상태 확인

```bash
agent-eval check

python -c "
from agent_evaluator import PerformanceMonitor, QuickEval
from agent_evaluator.decorators import agent_eval
print('core: OK')

try:
    from agent_evaluator.serve import server
    print('serve: OK')
except ImportError:
    print('serve: NOT installed — pip install "agent-evaluator[sdk]"')

try:
    import opentelemetry
    print('otel: OK')
except ImportError:
    print('otel: NOT installed — pip install "agent-evaluator[sdk]"')
"
```

### 보안 지표 미수집 문제

```python
# 올바른 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,  # 반드시 명시
)
# v0.7.3부터 record_task() 시 5개 보안 트래커 자동 호출
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

| 목적 | 문서 |
|------|------|
| 설치 · 기본 사용법 | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| 품질 임계값 · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| 대시보드 · Phoenix 모니터링 | [06_OBSERVABILITY.md](06_OBSERVABILITY.md) |
| 전체 API 레퍼런스 | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
