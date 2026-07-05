# Chapter 20. 프로덕션 배포 전략

> **이 챕터에서 배우는 것**
> - 개발/CI/프로덕션 환경별 최적 설정 전략과 preset 시스템
> - Docker 및 Kubernetes 배포 패턴
> - 데이터 유실 없이 장시간 운영하는 자동 저장 전략
> - 평가 오버헤드를 최소화하는 성능 최적화 기법
> - 프로덕션에서 자주 발생하는 문제 10가지와 해결책

> 📖 **사전 지식**: 환경 변수 설정과 API 키 관리는 이미 **[Chapter 2 §2.2](../Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md)**에서 다뤘습니다. 지원되는 전체 환경 변수 목록은 **[Appendix C](../Appendix/C_환경변수_설정_레퍼런스.md)**를 참조하세요. 이 챕터에서는 환경 설정을 반복하지 않고 배포 패턴에 집중합니다.

---

## 배포 전략의 핵심 관점 — Harness Engineering

**Harness Engineering**에서 배포 전략이란 단순히 "어떤 서버에 올리느냐"가 아니다. **"어떤 Gate 기준을 코드로 정의하고, 그 기준을 환경마다 어떻게 다르게 적용하느냐"**가 핵심이다.

```
배포 환경별 Gate 적용 철학:

  개발 환경  → Gate A + G 중심 (목표 달성 + 추론 품질) — 빠른 실험·반복
  CI 환경    → Gate A + D + E 중심 (정확도·SLA·보안 최소선) — 회귀 방지
  프로덕션   → Gate A~G 전체 + 샘플링 — 운영 안정성·비용 균형
```

각 환경에서 Config 객체(`SLAConfig`, `ComplianceConfig` 등)를 코드로 선언하면 **"배포 기준이 문서가 아닌 코드"**가 된다. 버전 관리(git)로 기준 변경 이력이 추적되고, CI에서 자동 검증된다.

---

## 20.1 환경별 설정 전략 — preset 시스템 활용

AI 에이전트 평가는 환경마다 목적이 다르다. 개발 환경에서는 빠른 피드백이 중요하고, CI 환경에서는 재현 가능성이, 프로덕션에서는 운영 오버헤드 최소화가 핵심이다.

### 개발 환경 (preset="development")

```python
# 개념 코드 — 개발 환경 QuickEval + preset="development" + setup_otel 패턴
# (ch20_deployment.py는 QuickEval을 사용하지 않음 — PerformanceMonitor 직접 사용)
import os
from agent_evaluator import QuickEval, setup_otel

# 로컬 Phoenix 연결 (선택)
try:
    setup_otel(endpoint="http://localhost:6006", service_name="dev-agent")
except Exception:
    pass  # Phoenix 없이도 동작

# development: llm_judge=LLMJudgeConfig() + auto_detect_framework=True
eval_q = QuickEval("results/", preset="development")

@eval_q.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

개발 환경의 특징:
- `sample_rate=1.0` — 모든 호출을 평가 (전수 평가)
- `llm_judge=LLMJudgeConfig()` — LLM Judge로 상세 채점
- `auto_detect_framework=True` — 프레임워크 자동 감지
- 로컬 Phoenix에 스팬 전송 (설치된 경우)

### CI 환경 — 골든 데이터셋 기반 평가

```python
# 개념 코드 — CI 환경 QuickEval + preset="testing" 골든 데이터셋 평가 패턴
# (ch20_deployment.py는 QuickEval 미포함 — Evaluator_Examples/ch18_cicd_gate.py 참고)
# ci/run_evaluation.py
import json
from agent_evaluator import QuickEval

# CI: 경량 설정, 골든 데이터셋 100-200개만 평가
eval_q = QuickEval("results/", preset="testing")

@eval_q.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
    dataset = json.load(f)

for pair in dataset["qa_pairs"][:100]:
    agent(pair["question"], ground_truth=pair["ground_truth"])

eval_q.save()
# 이후 agent-eval gate로 게이팅
```

CI 환경의 특징:
- 골든 데이터셋 100~200개만 평가 (속도 우선)
- LLM Judge 비활성화 (비용 절약)
- `agent-eval gate`로 임계값 검사

### 프로덕션 환경 (preset="production")

```python
# 기반 코드 — ch20_deployment.py의 PerformanceMonitor 패턴 기반 (auto_save 등 일부 설정 조합)
# production/agent.py
import os
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator import agent_eval

# 내부 Phoenix 서버 연결
otel_endpoint = os.getenv("OTEL_ENDPOINT", "http://phoenix-server:6006")
setup_otel(
    endpoint=otel_endpoint,
    service_name=os.getenv("SERVICE_NAME", "production-agent"),
)

# production: sample_rate=0.1 + flush_every=50
monitor = PerformanceMonitor(
    output_dir=os.getenv("EVAL_OUTPUT_DIR", "results/"),
    enable_hallucination_detection=False,  # CPU 절약 — 기본값 유지
    enable_security_metrics=True,          # 보안 지표 수집
    auto_save=True,
    auto_save_interval=50,
    use_korean_tokenizer=True,
)

# 10%만 평가 — 고트래픽 환경 비용/성능 균형
@agent_eval(monitor, task_type="qa", sample_rate=0.1, flush_every=50)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

프로덕션 환경의 특징:
- `sample_rate=0.1` — 10% 샘플링으로 오버헤드 90% 감소
- `flush_every=50` — 50회마다 자동 저장
- `enable_security_metrics=True` — 보안 위협 감시
- 내부 OTEL 서버로 스팬 전송

### 환경 변수로 자동 전환하는 패턴

```python
# 개념 코드 — 환경 변수 기반 PerformanceMonitor 팩토리 패턴 (create_monitor는 ch20에 없음)
# (ch20_deployment.py의 monitor_v1/v2 설정 패턴 참고)
# config.py — 환경 변수 기반 Monitor 팩토리
import os
from agent_evaluator import setup_otel, PerformanceMonitor

def create_monitor() -> PerformanceMonitor:
    """환경에 따라 최적 Monitor 반환"""
    env = os.getenv("ENV", "development")

    if env == "production":
        otel_endpoint = os.getenv("OTEL_ENDPOINT")
        if otel_endpoint:
            setup_otel(endpoint=otel_endpoint, service_name="prod-agent")

        return PerformanceMonitor(
            output_dir=os.getenv("EVAL_OUTPUT_DIR", "results/"),
            enable_security_metrics=True,
            auto_save=True,
            auto_save_interval=50,
            use_korean_tokenizer=True,
        )
    elif env == "staging":
        return PerformanceMonitor(
            output_dir="results/",
            enable_hallucination_detection=True,
            auto_save=True,
            auto_save_interval=20,
            use_korean_tokenizer=True,
        )
    else:  # development
        return PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
```

> ⚙️ **DevOps TIP**: `ENV` 환경 변수 하나로 전체 설정이 바뀌도록 설계하라. Docker 이미지를 환경마다 따로 만들지 말고, 같은 이미지를 환경 변수로 다르게 구성한다.

---

## 20.2 Docker 배포 패턴

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 의존성 설치 — LLMJudge · 대시보드 · OTEL · PDF 포함 (기본 설치)
COPY pyproject.toml .
RUN pip install --no-cache-dir agent-evaluator

# 애플리케이션 코드
COPY . .

# 결과 저장 디렉토리
RUN mkdir -p results/ data/golden_datasets/

ENV PYTHONUNBUFFERED=1
ENV ENV=production

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import agent_evaluator; print('OK')" || exit 1

EXPOSE 8765

CMD ["python", "production/agent.py"]
```

### docker-compose.yml — 에이전트 + Phoenix 통합 구성

```yaml
version: '3.8'

services:
  agent:
    build: .
    container_name: production-agent
    environment:
      - ENV=production
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OTEL_ENDPOINT=http://phoenix:6006
      - EVAL_OUTPUT_DIR=/data/evaluation_results
    volumes:
      - evaluation_results:/data/evaluation_results  # 평가 결과 영속화
      - golden_datasets:/data/golden_datasets
      - ./.env:/app/.env
    depends_on:
      phoenix:
        condition: service_healthy
    restart: unless-stopped

  phoenix:
    image: arizephoenix/phoenix:latest
    container_name: phoenix-monitor
    ports:
      - "6006:6006"
    volumes:
      - phoenix_data:/data    # Phoenix SQLite DB 영속화
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6006/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  dashboard:
    build: .
    container_name: agent-dashboard
    ports:
      - "8765:8765"
    environment:
      - ENV=production
    volumes:
      - evaluation_results:/data/evaluation_results
    command: agent-eval dashboard /data/evaluation_results --port 8765 --no-open
    depends_on:
      - agent
    restart: unless-stopped

volumes:
  evaluation_results:
  golden_datasets:
  phoenix_data:
```

```bash
# 전체 스택 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f agent

# 대시보드 접속: http://localhost:8765
# Phoenix 접속:  http://localhost:6006
```

- `docker-compose up -d`로 에이전트·Phoenix·대시보드 세 서비스를 동시에 기동한다
- `depends_on`과 `healthcheck`로 Phoenix가 준비된 뒤에 에이전트가 시작되므로 OTEL 연결 타이밍 문제가 없다
- `evaluation_results` 볼륨을 에이전트와 대시보드가 공유하므로 대시보드에서 실시간 평가 결과를 바로 확인할 수 있다

---

## 20.3 Kubernetes 운영 패턴

### 멀티 레플리카 환경에서 평가 데이터 합산

Kubernetes에서 여러 에이전트 파드가 동시에 실행되면, 평가 결과를 어떻게 합산할지 고민해야 한다.

**권장 패턴: 공유 볼륨 + 중앙 집계 파드**

```yaml
# kubernetes/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eval-results-pvc
spec:
  accessModes:
    - ReadWriteMany   # 멀티 파드 동시 쓰기 가능
  resources:
    requests:
      storage: 10Gi
---
# kubernetes/agent-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-deployment
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: agent
          image: my-agent:latest
          env:
            - name: ENV
              value: production
            - name: EVAL_OUTPUT_DIR
              value: /data/eval-results
            - name: OTEL_ENDPOINT
              value: http://phoenix-service:6006
          volumeMounts:
            - mountPath: /data/eval-results
              name: eval-results
      volumes:
        - name: eval-results
          persistentVolumeClaim:
            claimName: eval-results-pvc
```

### ConfigMap으로 gate 임계값 관리

```yaml
# kubernetes/gate-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gate-config
data:
  gate_config.json: |
    {
      "tcr": 85,
      "accuracy": 70,
      "p95_latency": 3.0,
      "hallucination": 5
    }
```

- ConfigMap에 게이팅 임계값을 JSON으로 저장하면 코드 변경 없이 `kubectl apply`로 임계값을 조정할 수 있다
- 환경별(dev/staging/prod) ConfigMap을 분리해 네임스페이스에 따라 다른 임계값을 자동으로 적용할 수 있다

```yaml
# CI Job에서 ConfigMap에서 읽은 값으로 게이팅
- name: gate
  image: python:3.11-slim
  command:
    - sh
    - -c
    - |
      pip install agent-evaluator && \
      TCR=$(cat /config/gate_config.json | python3 -c "import sys,json; print(json.load(sys.stdin)['tcr'])") && \
      ACC=$(cat /config/gate_config.json | python3 -c "import sys,json; print(json.load(sys.stdin)['accuracy'])") && \
      agent-eval gate /results/latest.json --tcr "$TCR" --accuracy "$ACC" --p95-latency 3.0
  volumeMounts:
    - mountPath: /config
      name: gate-config
    - mountPath: /results
      name: eval-results
```

- ConfigMap을 마운트해 임계값을 동적으로 읽으므로 파드 재시작 없이 게이팅 기준을 변경할 수 있다
- `python3 -c`로 JSON을 파싱해 셸 변수에 담아 `agent-eval gate`에 전달하는 패턴은 추가 도구 없이도 동작한다

> ⚙️ **DevOps TIP**: 멀티 레플리카 환경에서 각 파드마다 `output_dir`에 고유 suffix를 붙여라. `output_dir=f"results/pod-{os.getenv('POD_NAME', 'local')}"` 패턴을 쓰면 파드별 결과 충돌을 방지할 수 있다.

---

## 20.4 데이터 유실 방지 전략

프로덕션에서 평가 데이터 유실은 두 가지 상황에서 발생한다. 첫째, 프로세스가 갑자기 종료되는 경우. 둘째, 결과를 저장하는 것을 잊어버리는 경우. 두 상황 모두 방어할 수 있다.

### 이중 저장 패턴

```python
# 기반 코드 — ch20_deployment.py의 PerformanceMonitor + auto_save + flush_every 이중 저장 패턴
from agent_evaluator import PerformanceMonitor
from agent_evaluator import agent_eval

# 방어선 1: auto_save — 10건마다 자동 저장
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,
    auto_save_filename="auto_checkpoint",  # results/auto_checkpoint.json
    use_korean_tokenizer=True,
)

# 방어선 2: flush_every — 50회 호출마다 즉시 저장
@agent_eval(
    monitor,
    task_type="qa",
    flush_every=50,
)
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

- `auto_save=True`는 `auto_save_interval`마다 백그라운드에서 자동 저장해 프로세스 비정상 종료 시에도 마지막 체크포인트까지의 데이터를 보존한다
- `flush_every=50`은 50회 호출마다 `save_to_file()`을 즉시 실행해 메모리 누적 없이 주기적으로 디스크에 기록한다
- 두 설정을 함께 사용하면 짧은 주기(auto_save)와 호출 횟수 기반(flush_every) 이중 체크포인트가 구성된다

### evaluation_session — 예외 발생 시에도 안전한 저장

```python
# 개념 코드 — evaluation_session 컨텍스트 매니저 패턴
# (ch20_deployment.py는 evaluation_session을 사용하지 않음)
from agent_evaluator import evaluation_session

# 컨텍스트 매니저: 예외가 발생해도 finally에서 자동 저장
with evaluation_session("evaluation") as monitor:
    for task in tasks:
        response = agent.run(task["question"])
        # 중간에 예외가 발생해도 그때까지의 데이터는 보존됨

# 세션 종료 시 results/evaluation.json + .html 자동 저장
```

- `evaluation_session`은 `with` 블록이 정상 종료되든 예외로 종료되든 `finally`에서 반드시 `save_to_file()`을 호출한다
- 세션 이름(`"evaluation"`)이 저장 파일명이 되므로 실행마다 의미 있는 이름을 지정해 이후 분석을 용이하게 한다

```python
# 개념 코드 — async_evaluation_session 비동기 컨텍스트 매니저 패턴
# (ch20_deployment.py는 async_evaluation_session을 사용하지 않음)
# 비동기 에이전트
from agent_evaluator import async_evaluation_session

async with async_evaluation_session("async_eval") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

- `async_evaluation_session`은 FastAPI 핸들러나 async 에이전트에서 `await` 없이 동기 컨텍스트 매니저처럼 사용할 수 있다
- 내부적으로 `asyncio`와 스레드 세이프한 저장 메커니즘을 사용하므로 동시 요청 처리 중에도 안전하다

### 저장 주기 선택 가이드

| 상황 | 권장 설정 |
|------|-----------|
| 빠른 에이전트 (1초 미만) | `flush_every=100` |
| 일반 에이전트 (1~5초) | `flush_every=50` |
| 느린 에이전트 (5초 이상) | `flush_every=20` |
| 장시간 배치 처리 | `auto_save=True, auto_save_interval=10` |
| 미션 크리티컬 | 위 모두 조합 |

> 📋 **QA 관리자 TIP**: `auto_save=True`는 기본값이 `False`다. 프로덕션 배포 시 체크리스트에 이 설정 확인을 포함시켜라. 하루 종일 평가한 데이터가 프로세스 종료와 함께 사라지는 것을 방지할 수 있다.

---

## 20.5 성능 최적화 — 평가 오버헤드 최소화

에이전트 평가가 실제 서비스 응답 시간에 영향을 주어서는 안 된다. 올바르게 설정하면 Gate A-G 기반 지표의 오버헤드는 1ms 미만이다.

### 오버헤드 비교

| 설정 | 지연 추가 | CPU 추가 | 비용 추가 |
|------|----------|----------|----------|
| Gate A-G 기반 (기본) | ~1ms | 낮음 | 없음 |
| +Hallucination Detection | ~50ms | 중간 | 없음 |
| +Security Metrics | ~10ms | 낮음 | 없음 |
| +LLM Judge (전수) | ~500ms | LLM API | 높음 |
| +LLM Judge (5% 샘플) | ~25ms (평균) | 낮음 | 낮음 |

### 오버헤드 최소화 설정

```python
# 기반 코드 — ch20_deployment.py의 PerformanceMonitor 기반 오버헤드 최소화 패턴 (QuickEval 미포함)
from agent_evaluator import PerformanceMonitor
from agent_evaluator import agent_eval

# 최소 오버헤드 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 — 50ms 절약
    enable_security_metrics=False,         # 기본값 — 10ms 절약
    use_korean_tokenizer=True,
)

# 10% 샘플링 — 평가 횟수 90% 감소
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# LLM Judge: 5%만 채택 (judge_sample_rate)
# QuickEval.for_llm_judge() 사용 시 내부 설정으로 조절 가능:
# eval_q = QuickEval.for_llm_judge("results/", model="gpt-5-nano")
```

### 조건부 샘플링 — 특정 조건에서만 평가

```python
# 개념 코드 — sample_condition 조건부 샘플링 패턴 (ch20_deployment.py에 없음)
from agent_evaluator import agent_eval

# 긴 질문만 평가 (짧은 질문은 스킵)
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kwargs: len(args[0]) > 100,
)
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

- `sample_condition`에 람다를 전달하면 평가 실행 여부를 동적으로 제어할 수 있다
- 짧은 질문은 스킵하고 긴 질문(복잡한 태스크)만 평가하면 실질적인 품질 정보 손실 없이 오버헤드를 줄일 수 있다
- `args[0]`은 첫 번째 위치 인자(질문 텍스트)를 참조하며, `kwargs`를 통해 키워드 인자도 조건에 활용할 수 있다

### OTEL 오버헤드 최소화

OTEL은 비동기 `BatchSpanProcessor`를 사용하므로 스팬 전송이 에이전트 응답 시간에 직접 영향을 주지 않는다. 단, `save_to_file()` 호출 시 `force_flush(3s)`가 실행되므로 호출 빈도를 조절해야 한다.

```python
# 기반 코드 — ch20_deployment.py의 PerformanceMonitor 기반 OTEL 오버헤드 최소화 패턴
# 자동 저장으로 save_to_file() 직접 호출 최소화
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,  # 50건 쌓이면 한 번에 저장 + force_flush
    use_korean_tokenizer=True,
)
```

---

## 20.6 트러블슈팅 — 자주 발생하는 문제 10가지

### 문제 1 — Phoenix 스팬이 안 보임

**증상**: 코드를 실행했는데 Phoenix Tracing 탭에 스팬이 없다.

**원인**: `setup_otel()`을 `PerformanceMonitor` 생성 후에 호출했거나, 기본 설치가 완료되지 않았다.

**해결책**:
```bash
# 1. 기본 설치 확인 (OTEL 포함)
pip install agent-evaluator
agent-eval monitor --check

# 2. 코드에서 순서 확인
# setup_otel()이 PerformanceMonitor/QuickEval 생성 전에 있는지 확인
```

### 문제 2 — 대시보드에 데이터가 없음

**증상**: `agent-eval dashboard` 실행 후 데이터가 비어 있다.

**원인**: `save_to_file()` 또는 `eval_q.save()`를 호출하지 않았거나, `output_dir` 경로가 다르다.

**해결책**:
```python
# 개념 코드 — QuickEval 기반 대시보드 데이터 저장 패턴 (ch20_deployment.py는 monitor.save_to_file 직접 사용)
eval_q = QuickEval("results/")
# ... 평가 실행 ...
eval_q.save()  # 반드시 명시적 호출 또는 auto_save=True 설정

# 대시보드 실행 시 경로 일치 확인
# agent-eval dashboard results/
```

### 문제 3 — agent-eval gate 항상 실패

**증상**: CI에서 게이트가 항상 실패 처리된다.

**원인**: 임계값이 실제 에이전트 성능보다 너무 엄격하다.

**해결책**:
```bash
# 현재 성능 먼저 확인
python -c "
import json
with open('results/ci_run.json') as f:
    data = json.load(f)
print('TCR:', data['summary'].get('task_completion_rate', 0) * 100)
print('Accuracy:', data['summary'].get('accuracy', 0) * 100)
"
# 실제 성능보다 5-10% 낮게 임계값 설정
```

### Gate별 배포 거부 시 — 진단 빠른 가이드

CI에서 `agent-eval gate` 실패 메시지에 Gate 이름이 표시된다면, 아래 표로 첫 번째 체크포인트를 바로 찾는다.

| 실패 Gate | 원인 후보 1순위 | 개발자에게 확인할 것 | QA가 할 수 있는 것 |
|-----------|-------------|-------------------|-----------------|
| **Gate A** (목표달성) | accuracy·TCR 하락 | `ground_truth` 제공 여부, `task_type` 설정 | 임계값이 실제 성능과 괴리됐는지 Chapter 14 §14.1 재검토 |
| **Gate B** (행동무결성) | 도구 루프 or scope 이탈 | `LoopDetectionConfig`, `ScopeConfig` 선언 여부 | 대시보드 Tool Call 탭에서 반복 패턴 확인 |
| **Gate C** (신뢰성) | 환각·재시도율 상승 | `enable_hallucination_detection=True` 설정 여부 | 동일 입력 반복 실행으로 재현성 확인 |
| **Gate D** (성능계약) | P95 latency SLA 초과 or 비용 폭증 | `SLAConfig(p95_ms=...)`, `ResourceBudgetConfig` 선언 | 최근 모델·프롬프트 변경 이력 확인 |
| **Gate E** (보안경계) | 위협 탐지 누적 or 권한 상승 | `enable_security_metrics=True` 여부, `ComplianceConfig` | Appendix K 레드팀 체크리스트로 즉시 검증 |
| **Gate F** (다중에이전트) | 교착·합의 실패 | `ConsensusConfig`, `PropagationConfig` 선언 여부; 교착 방어는 Gate B `DeadlockConfig` 병행 | 에이전트 토폴로지 변경 이력 확인 |
| **Gate G** (관측성) | 추론 설명 부족 or 상태 추적 미흡 | `ExplainabilityConfig(min_reasoning_length=N)` | Phoenix 트레이스로 reasoning 길이 직접 확인 |

```bash
# Gate별 현재 점수 빠른 조회
python -c "
import json
with open('results/ci_run.json') as f:
    data = json.load(f)
gates = (data.get('extra_metrics') or {}).get('harness_groups', {})
for gate, info in gates.items():
    status = (info.get('gate') or 'N/A').upper()
    score = info.get('score', 'N/A')
    print(f'{gate}: {status} (score={score})')
"
```

> 💡 **키 구조 주의**: Gate 결과는 JSON 최상위의 `extra_metrics.harness_groups` 경로에 저장된다. `harness_gates`라는 키는 존재하지 않는다. 각 Gate 항목의 상태는 `"status"` 필드가 아니라 `"gate"` 필드(PASS/WARN/FAIL)로 확인한다.

- Gate A–G 각각의 판정 결과(`gate` 필드: PASS/WARN/FAIL)와 `score`를 즉시 조회할 수 있다
- CI 로그에서 실패 Gate를 확인한 뒤 위 표의 해당 행을 참조하면 첫 번째 체크포인트를 빠르게 찾을 수 있다

### 문제 4 — LLM Judge 비용이 너무 많이 나옴

**증상**: LLM Judge 사용 후 API 비용이 급증했다.

**원인**: 모든 호출(sample_rate=1.0)에 LLM Judge가 실행되고 있다.

**해결책**:
```python
# 개념 코드 — LLM Judge 비용 절감 패턴 (ch20_deployment.py는 QuickEval.for_llm_judge 미포함)
# QuickEval 사용 시 내부 judge_sample_rate 조절
eval_q = QuickEval.for_llm_judge("results/", model="gpt-5-nano")

# 또는 agent_eval에서 llm_judge 조건부 사용
@agent_eval(monitor, task_type="qa")  # llm_judge 기본 비활성
def agent(question, ground_truth=""): ...
```

### 문제 5 — 정확도가 0으로 나옴

**증상**: 모든 태스크의 `accuracy_score`가 0이다.

**원인**: `ground_truth`를 입력하지 않았다.

**해결책**:
```python
# 개념 코드 — ground_truth 전달 패턴 (ch20_deployment.py는 eval_q.qa 미사용)
@eval_q.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# ground_truth 반드시 전달
agent("한국의 수도는?", ground_truth="서울")  # ground_truth 필수
```

### 문제 6 — 할루시네이션이 항상 0

**증상**: `hallucination_rate`가 항상 0%다.

**원인**: `enable_hallucination_detection`의 기본값이 `False`다.

**해결책**:
```python
# 개념 코드 — 환각 탐지 활성화 패턴 (ch20_deployment.py는 QuickEval.for_rag 미포함)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 명시적으로 활성화 필요
    use_korean_tokenizer=True,
)
# 또는
eval_q = QuickEval.for_rag("results/")  # RAG 팩토리 — 자동 활성화
```

### 문제 7 — 보안 지표가 수집 안 됨

**증상**: 대시보드에서 보안 관련 지표가 모두 0이다.

**원인**: `enable_security_metrics`의 기본값이 `False`다. v0.7.2 이하에서는 초기화는 됐지만 `record_task()` 시 호출이 누락되는 버그도 있었다.

**해결책**:
```python
# 출처: Evaluator_Examples/ch20_deployment.py — PerformanceMonitor 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,  # 반드시 명시
    use_korean_tokenizer=True,
)
# v0.7.3+에서 record_task() 시 5개 보안 트래커 자동 호출 확인됨 (CRITICAL 버그 수정)
```

### 문제 8 — batch_eval DataFrame이 비어있음

**증상**: `batch_eval` 데코레이터를 사용했는데 DataFrame에 데이터가 없다.

**원인**: 함수 서명에 `ground_truths` 파라미터가 없거나, 반환값이 리스트가 아니다.

**해결책**:
```python
# 개념 코드 — batch_eval DataFrame 반환 패턴 (ch20_deployment.py에 없음)
from agent_evaluator import batch_eval

@batch_eval(monitor)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    # questions 리스트를 받아 응답 리스트를 반환
    return [call_llm(q) for q in questions]

# 호출 시 ground_truths 전달
result_df = batch_agent(
    ["질문1", "질문2"],
    ground_truths=["정답1", "정답2"]
)
```

### 문제 9 — conversation_eval 세션이 합쳐짐

**증상**: 서로 다른 대화 세션의 데이터가 하나로 합쳐진다.

**원인**: `session_id`가 중복되고 있다.

**해결책**:
```python
# 개념 코드 — conversation_eval 고유 session_id 부여 패턴 (ch20_deployment.py에 없음)
import uuid
from agent_evaluator import conversation_eval

# 각 대화마다 고유 session_id 부여
@conversation_eval(monitor, session_id=lambda args, kwargs: str(uuid.uuid4()))
def chat_agent(user_input: str) -> str:
    return call_llm(user_input)
```

### 문제 10 — ragas 설치 오류

**증상**: `pip install "agent-evaluator[eval]"` 후 `datasets` 버전 충돌 오류가 발생한다.

**원인**: ragas 0.4.x는 `datasets>=4.0.0,<6.0.0`이 필요한데, 다른 패키지가 다른 버전을 요구하는 경우.

**해결책**:
```bash
# 명시적 버전 지정
pip install "agent-evaluator[eval]" "datasets>=4.0.0,<6.0.0"

# 가상환경 격리 후 설치
python -m venv venv-eval
source venv-eval/bin/activate
pip install "agent-evaluator[eval]"
```

> 📋 **QA 관리자 TIP**: 문제 6, 7번은 가장 많이 발생하는 실수다. 팀에 `enable_hallucination_detection=False`와 `enable_security_metrics=False`가 **기본값**임을 공유하라. 기본값이 비활성화인 이유는 CPU/시간 비용 때문이다.

---

## 이 챕터의 핵심

- **Harness Engineering 배포 관점**: 배포 전략 = Gate 기준을 Config 객체로 코드화하고 환경마다 다르게 적용하는 것. 기준이 코드이므로 git으로 이력이 추적되고 CI에서 자동 검증된다.

- **환경별 preset 전략**: dev는 `preset="development"`(전수 평가 + LLM Judge), CI는 `preset="testing"`(골든셋 100개), prod는 `preset="production"`(10% 샘플링 + 자동 저장).

- **데이터 유실 방지**는 이중 저장으로 해결한다. `auto_save=True`와 `flush_every=50`을 동시에 설정하고, 세션 단위 평가는 `evaluation_session` 컨텍스트 매니저를 사용한다.

- **평가 오버헤드**는 기본 설정(Gate A-G 기반만)에서 ~1ms다. `enable_hallucination_detection`, `enable_security_metrics`는 기본값이 `False`이므로 필요할 때만 활성화한다.

- **Docker 배포**는 Phoenix 서비스와 함께 `docker-compose.yml`로 통합 구성한다. 평가 결과는 볼륨으로 영속화하고, 환경 변수로 OTEL 엔드포인트를 주입한다.

- **Gate 결과 JSON 경로**: `result["extra_metrics"]["harness_groups"]["A"]["gate"]`(PASS/WARN/FAIL). `harness_gates`라는 키는 존재하지 않는다. `HarnessEvaluationGate` 클래스는 `agent_evaluator/quick_eval.py`에 있으나 이 챕터에서는 `generate_report().to_dict()`로 직접 Gate 결과를 읽는 방식을 사용한다. CLI 게이팅은 `agent-eval gate result.json` 명령으로 수행한다.

- **트러블슈팅 핵심**: Phoenix 스팬 미전송은 `setup_otel()` 순서 문제, 정확도 0은 `ground_truth` 미입력, 할루시네이션/보안 지표 0은 `enable_*` 기본값 확인으로 해결된다.

---

## 실전 예제

**기본 예제**: [`Evaluator_Examples/ch20_deployment.py`](../../Evaluator_Examples/ch20_deployment.py)

| 패턴 | 내용 |
|------|------|
| v1 vs v2 Gate 비교 | 독립 `PerformanceMonitor` 2개로 동일 Config 적용 → Gate A–G 점수 나란히 비교 |
| 배포 자동 결정 | 필수 Gate(A·B·C·E) 전체 PASS 여부로 배포 승인/차단 자동 판정 |
| `save_to_file()` | v1·v2 결과 JSON+HTML 생성 → 대시보드에서 나란히 확인 |

```bash
python Evaluator_Examples/ch20_deployment.py    # v1 vs v2 Gate 점수 비교 · 배포 버전 결정
```

> **관련 챕터 예제**: CI/CD 최소 게이팅(`ch18_cicd_gate.py`)은 [Chapter 18](Chapter_18_CICD_품질게이팅.md)에서, Phoenix OTEL 통합(`ch19_phoenix.py`)은 [Chapter 19](Chapter_19_Phoenix_OTEL_모니터링.md)에서, Gate FAIL 임계값 확인(`ch04_group_a.py`)은 [Chapter 4](../Part_II_지표시스템/Chapter_04_GroupA_목표달성.md)에서 확인한다.

**핵심 코드**

```python
# 출처: Evaluator_Examples/ch20_deployment.py — v1 vs v2 Gate 점수 비교
# v1 에이전트: 추론 없음, 토큰 낭비, PII 노출, SLA 초과
# v2 에이전트: 추론 마커 포함, 효율적 응답, GDPR 준수, SLA 통과

from agent_evaluator import (
    PerformanceMonitor,
    InstructionConfig, ScopeConfig, SLAConfig,
    ComplianceConfig, ExplainabilityConfig,
    FaultToleranceConfig, GracefulDegradationConfig,
    ConsensusConfig, ResourceBudgetConfig,
)
from agent_evaluator import agent_eval, EvalMetadata

# 두 버전은 반드시 독립된 PerformanceMonitor 인스턴스를 사용해야
# Gate 간 데이터 교차 오염이 없다
monitor_v1 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True, use_korean_tokenizer=True)
monitor_v2 = PerformanceMonitor(output_dir="results/", enable_security_metrics=True, use_korean_tokenizer=True)

# v1·v2 각각 동일한 Harness Config로 에이전트를 장식하고 실행한 뒤
# generate_report()로 Gate 판정 결과를 추출한다
report_v1 = monitor_v1.generate_report().to_dict()
report_v2 = monitor_v2.generate_report().to_dict()

# Gate 결과는 extra_metrics.harness_groups 경로에 저장된다
gates_v1 = (report_v1.get("extra_metrics") or {}).get("harness_groups", {})
gates_v2 = (report_v2.get("extra_metrics") or {}).get("harness_groups", {})

print("=== v1 vs v2 Gate 점수 비교 ===")
for g in ["A", "B", "C", "D", "E", "F", "G"]:
    s1 = (gates_v1.get(g) or {}).get("score")
    s2 = (gates_v2.get(g) or {}).get("score")
    t1 = ((gates_v1.get(g) or {}).get("gate") or "N/A").upper()
    t2 = ((gates_v2.get(g) or {}).get("gate") or "N/A").upper()
    if s1 is not None and s2 is not None:
        delta = (s2 - s1) * 100
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        print(f"  Gate {g}: v1={s1:.0%}({t1})  v2={s2:.0%}({t2})  {arrow}{abs(delta):.1f}%p")

# 배포 결정 — 어떤 Gate가 FAIL이면 배포 차단
v1_fail = [g for g in "ABCDEFG" if ((gates_v1.get(g) or {}).get("gate") or "").upper() == "FAIL"]
v2_fail = [g for g in "ABCDEFG" if ((gates_v2.get(g) or {}).get("gate") or "").upper() == "FAIL"]

print("v1: ❌ 배포 차단 — Gate " + str(v1_fail) + " FAIL" if v1_fail else "v1: ⚠️ 배포 가능 (WARN 있음)")
print("v2: ✅ 배포 승인 — 모든 Gate 통과" if not v2_fail else "v2: ❌ 배포 차단 — Gate " + str(v2_fail) + " FAIL")

monitor_v1.save_to_file("ch20_deployment_v1")
monitor_v2.save_to_file("ch20_deployment_v2")
```

> 💡 이 챕터의 배포 판정 패턴: `generate_report().to_dict()`로 Gate 결과를 읽어 직접 판단하거나, CLI에서 `agent-eval gate result.json --tcr 85` 명령으로 수행한다. `HarnessEvaluationGate` 클래스(`agent_evaluator/quick_eval.py`)를 사용해도 동일한 판정이 가능하다.

- 두 버전의 `PerformanceMonitor`를 독립적으로 생성해야 Gate 간 데이터 교차 오염이 없다
- Gate 결과 접근 경로는 `report["extra_metrics"]["harness_groups"]["A"]["gate"]`(PASS/WARN/FAIL) 형태다
- 배포 차단 조건을 코드로 표현하는 것이 Harness Engineering의 핵심이다 — "배포 기준을 설정 파일이 아니라 Python Config 객체로 코드화하고, Gate 판정으로 자동 결정"
