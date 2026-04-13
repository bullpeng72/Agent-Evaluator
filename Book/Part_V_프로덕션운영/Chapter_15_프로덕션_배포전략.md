# Chapter 15. 프로덕션 배포 전략

> **이 챕터에서 배우는 것**
> - 개발/CI/프로덕션 환경별 최적 설정 전략과 preset 시스템
> - Docker 및 Kubernetes 배포 패턴
> - 데이터 유실 없이 장시간 운영하는 자동 저장 전략
> - 평가 오버헤드를 최소화하는 성능 최적화 기법
> - 프로덕션에서 자주 발생하는 문제 10가지와 해결책

> 📖 **사전 지식**: 환경 변수 설정과 API 키 관리는 이미 **[Chapter 2 §2.2](../Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md)**에서 다뤘습니다. 지원되는 전체 환경 변수 목록은 **[Appendix C](../Appendix/C_환경변수_설정_레퍼런스.md)**를 참조하세요. 이 챕터에서는 환경 설정을 반복하지 않고 배포 패턴에 집중합니다.

---

## 15.1 환경별 설정 전략 — preset 시스템 활용

AI 에이전트 평가는 환경마다 목적이 다르다. 개발 환경에서는 빠른 피드백이 중요하고, CI 환경에서는 재현 가능성이, 프로덕션에서는 운영 오버헤드 최소화가 핵심이다.

### 개발 환경 (preset="development")

```python
import os
from agent_evaluator import QuickEval, setup_otel

# 로컬 Phoenix 연결 (선택)
try:
    setup_otel(endpoint="http://localhost:6006", service_name="dev-agent")
except Exception:
    pass  # Phoenix 없이도 동작

# development: enable_llm_judge=True + auto_detect_framework=True
eval = QuickEval("results/", preset="development")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

개발 환경의 특징:
- `sample_rate=1.0` — 모든 호출을 평가 (전수 평가)
- `enable_llm_judge=True` — LLM Judge로 상세 채점
- `auto_detect_framework=True` — 프레임워크 자동 감지
- 로컬 Phoenix에 스팬 전송 (설치된 경우)

### CI 환경 — 골든 데이터셋 기반 평가

```python
# ci/run_evaluation.py
import json
from agent_evaluator import QuickEval

# CI: 경량 설정, 골든 데이터셋 100-200개만 평가
eval = QuickEval("results/", preset="testing")

@eval.qa
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

with open("data/golden_datasets/production_dataset.json", encoding="utf-8") as f:
    dataset = json.load(f)

for pair in dataset["qa_pairs"][:100]:
    agent(pair["question"], ground_truth=pair["ground_truth"])

eval.save()
# 이후 agent-eval gate로 게이팅
```

CI 환경의 특징:
- 골든 데이터셋 100~200개만 평가 (속도 우선)
- LLM Judge 비활성화 (비용 절약)
- `agent-eval gate`로 임계값 검사

### 프로덕션 환경 (preset="production")

```python
# production/agent.py
import os
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 내부 Phoenix 서버 연결
otel_endpoint = os.getenv("OTEL_ENDPOINT", "http://phoenix-server:6006")
setup_otel(
    endpoint=otel_endpoint,
    service_name=os.getenv("SERVICE_NAME", "production-agent"),
)

# production: flush_every=50, enable_anomaly_detection=True
monitor = PerformanceMonitor(
    output_dir=os.getenv("EVAL_OUTPUT_DIR", "results/"),
    enable_hallucination_detection=False,  # CPU 절약 — 기본값 유지
    enable_security_metrics=True,          # 보안 지표 수집
    auto_save=True,
    auto_save_interval=50,
)

# 10%만 평가 — 고트래픽 환경 비용/성능 균형
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
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

> ⚙️ **DevOps TIP**: `ENV` 환경 변수 하나로 전체 설정이 바뀌도록 설계하라. Docker 이미지를 환경마다 따로 만들지 말고, 같은 이미지를 환경 변수로 다르게 구성한다.

---

## 15.2 Docker 배포 패턴

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

---

## 15.3 Kubernetes 운영 패턴

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

> ⚙️ **DevOps TIP**: 멀티 레플리카 환경에서 각 파드마다 `output_dir`에 고유 suffix를 붙여라. `output_dir=f"results/pod-{os.getenv('POD_NAME', 'local')}"` 패턴을 쓰면 파드별 결과 충돌을 방지할 수 있다.

---

## 15.4 데이터 유실 방지 전략

프로덕션에서 평가 데이터 유실은 두 가지 상황에서 발생한다. 첫째, 프로세스가 갑자기 종료되는 경우. 둘째, 결과를 저장하는 것을 잊어버리는 경우. 두 상황 모두 방어할 수 있다.

### 이중 저장 패턴

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 방어선 1: auto_save — 10건마다 자동 저장
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,
    auto_save_filename="auto_checkpoint",  # results/auto_checkpoint.json
)

# 방어선 2: flush_every — 50회 호출마다 즉시 저장
@agent_eval(
    monitor,
    task_type="qa",
    flush_every=50,
    flush_filename="periodic_checkpoint",  # results/periodic_checkpoint.json
)
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

### evaluation_session — 예외 발생 시에도 안전한 저장

```python
from agent_evaluator import evaluation_session

# 컨텍스트 매니저: 예외가 발생해도 finally에서 자동 저장
with evaluation_session("evaluation") as monitor:
    for task in tasks:
        response = agent.run(task["question"])
        # 중간에 예외가 발생해도 그때까지의 데이터는 보존됨

# 세션 종료 시 results/evaluation.json + .html 자동 저장
```

```python
# 비동기 에이전트
from agent_evaluator import async_evaluation_session

async with async_evaluation_session("async_eval") as monitor:
    result = await agent.run(task)
    monitor.record_task(result)
```

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

## 15.5 성능 최적화 — 평가 오버헤드 최소화

에이전트 평가가 실제 서비스 응답 시간에 영향을 주어서는 안 된다. 올바르게 설정하면 Layer 1 기본 지표의 오버헤드는 1ms 미만이다.

### 오버헤드 비교

| 설정 | 지연 추가 | CPU 추가 | 비용 추가 |
|------|----------|----------|----------|
| Layer 1만 (기본) | ~1ms | 낮음 | 없음 |
| +Hallucination Detection | ~50ms | 중간 | 없음 |
| +Security Metrics | ~10ms | 낮음 | 없음 |
| +LLM Judge (전수) | ~500ms | LLM API | 높음 |
| +LLM Judge (5% 샘플) | ~25ms (평균) | 낮음 | 낮음 |

### 오버헤드 최소화 설정

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# 최소 오버헤드 설정
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # 기본값 — 50ms 절약
    enable_security_metrics=False,         # 기본값 — 10ms 절약
)

# 10% 샘플링 — 평가 횟수 90% 감소
@agent_eval(monitor, task_type="qa", sample_rate=0.1)
def production_agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)

# LLM Judge: 5%만 채점 (judge_sample_rate)
# QuickEval.for_llm_judge() 사용 시 내부 설정으로 조절 가능
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### 조건부 샘플링 — 특정 조건에서만 평가

```python
from agent_evaluator.decorators import agent_eval

# 긴 질문만 평가 (짧은 질문은 스킵)
@agent_eval(
    monitor,
    task_type="qa",
    sample_condition=lambda args, kwargs: len(args[0]) > 100,
)
def agent(question: str, ground_truth: str = "") -> str:
    return call_llm(question)
```

### OTEL 오버헤드 최소화

OTEL은 비동기 `BatchSpanProcessor`를 사용하므로 스팬 전송이 에이전트 응답 시간에 직접 영향을 주지 않는다. 단, `save_to_file()` 호출 시 `force_flush(3s)`가 실행되므로 호출 빈도를 조절해야 한다.

```python
# 자동 저장으로 save_to_file() 직접 호출 최소화
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=50,  # 50건 쌓이면 한 번에 저장 + force_flush
)
```

---

## 15.6 트러블슈팅 — 자주 발생하는 문제 10가지

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

**원인**: `save_to_file()` 또는 `eval.save()`를 호출하지 않았거나, `output_dir` 경로가 다르다.

**해결책**:
```python
eval = QuickEval("results/")
# ... 평가 실행 ...
eval.save()  # 반드시 명시적 호출 또는 auto_save=True 설정

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

### 문제 4 — LLM Judge 비용이 너무 많이 나옴

**증상**: LLM Judge 사용 후 API 비용이 급증했다.

**원인**: 모든 호출(sample_rate=1.0)에 LLM Judge가 실행되고 있다.

**해결책**:
```python
# QuickEval 사용 시 내부 judge_sample_rate 조절
eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

# 또는 agent_eval에서 enable_llm_judge 조건부 사용
@agent_eval(monitor, task_type="qa", enable_llm_judge=False)  # 기본 비활성
def agent(question, ground_truth=""): ...
```

### 문제 5 — 정확도가 0으로 나옴

**증상**: 모든 태스크의 `accuracy_score`가 0이다.

**원인**: `ground_truth`를 입력하지 않았다.

**해결책**:
```python
@eval.qa
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
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=True,  # 명시적으로 활성화 필요
)
# 또는
eval = QuickEval.for_rag("results/")  # RAG 팩토리 — 자동 활성화
```

### 문제 7 — 보안 지표가 수집 안 됨

**증상**: 대시보드에서 보안 관련 지표가 모두 0이다.

**원인**: `enable_security_metrics`의 기본값이 `False`다. v0.7.2 이하에서는 초기화는 됐지만 `record_task()` 시 호출이 누락되는 버그도 있었다.

**해결책**:
```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_security_metrics=True,  # 반드시 명시
)
# v0.7.3+에서 record_task() 시 5개 보안 트래커 자동 호출 확인됨 (CRITICAL 버그 수정)
```

### 문제 8 — batch_eval DataFrame이 비어있음

**증상**: `batch_eval` 데코레이터를 사용했는데 DataFrame에 데이터가 없다.

**원인**: 함수 서명에 `ground_truths` 파라미터가 없거나, 반환값이 리스트가 아니다.

**해결책**:
```python
from agent_evaluator.decorators import batch_eval

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
import uuid
from agent_evaluator.decorators import conversation_eval

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

## [이 챕터의 핵심]

- **환경별 preset 전략**: dev는 `preset="development"`(전수 평가 + LLM Judge), CI는 `preset="testing"`(골든셋 100개), prod는 `preset="production"`(10% 샘플링 + 자동 저장).

- **데이터 유실 방지**는 이중 저장으로 해결한다. `auto_save=True`와 `flush_every=50`을 동시에 설정하고, 세션 단위 평가는 `evaluation_session` 컨텍스트 매니저를 사용한다.

- **평가 오버헤드**는 기본 설정(Layer 1만)에서 ~1ms다. `enable_hallucination_detection`, `enable_security_metrics`는 기본값이 `False`이므로 필요할 때만 활성화한다.

- **Docker 배포**는 Phoenix 서비스와 함께 `docker-compose.yml`로 통합 구성한다. 평가 결과는 볼륨으로 영속화하고, 환경 변수로 OTEL 엔드포인트를 주입한다.

- **트러블슈팅 핵심**: Phoenix 스팬 미전송은 `setup_otel()` 순서 문제, 정확도 0은 `ground_truth` 미입력, 할루시네이션/보안 지표 0은 `enable_*` 기본값 확인으로 해결된다.

---

## 실전 예제

`07_phoenix_hybrid.py`는 프로덕션 배포 전략에서 설명하는 세 가지 핵심 패턴(preset 시스템, Docker 통합, 데이터 유실 방지)을 실제 코드로 보여준다. `evaluation_session` 컨텍스트 매니저로 예외 발생 시에도 데이터가 안전하게 저장되는 구조를 확인할 수 있다.

**파일**: `Evaluator_Examples/07_phoenix_hybrid.py`, `Evaluator_Examples/06_operational.py`

**핵심 코드 (출처: `Evaluator_Examples/07_phoenix_hybrid.py`, `06_operational.py`)**

```python
# 출처: Evaluator_Examples/07_phoenix_hybrid.py — HybridPerformanceMonitor 조건부 활성화
import os
from agent_evaluator import PerformanceMonitor

def create_monitor(output_dir: str = "results/") -> PerformanceMonitor:
    """환경에 따라 최적 모니터 자동 선택"""
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    try:
        from agent_evaluator import HybridPerformanceMonitor
        if has_openai:
            # DeepEval + Ragas 활성화 (OPENAI_API_KEY 필수)
            monitor = HybridPerformanceMonitor(
                output_dir=output_dir,
                use_deepeval=True,
                use_ragas=True,
            )
            print("HybridPerformanceMonitor 활성화 (DeepEval + Ragas)")
            return monitor
    except ImportError:
        pass  # [eval] extra 미설치
    
    # Fallback: 기본 PerformanceMonitor (외부 의존성 없음)
    print("PerformanceMonitor 사용 (네이티브 지표만)")
    return PerformanceMonitor(
        output_dir=output_dir,
        enable_hallucination_detection=True,
        enable_llm_judge=has_openai,  # API 키 있을 때만 LLMJudge 활성화
    )

monitor = create_monitor()
```

- 프로덕션 배포 시 환경변수(`OPENAI_API_KEY`)와 설치된 패키지에 따라 모니터를 자동으로 선택한다
- `HybridPerformanceMonitor`는 `[eval]` extras(`deepeval`, `ragas`)가 설치된 경우에만 사용 가능하다
- `try/except ImportError`로 extras 미설치 환경에서도 코드가 정상 동작하게 한다

```python
# 출처: Evaluator_Examples/06_operational.py, 섹션 4 — 프로덕션 평가 세션 안전 저장
from agent_evaluator import evaluation_session, create_taskresult
import logging

logger = logging.getLogger(__name__)

def run_production_evaluation(agent_fn, test_cases: list) -> dict:
    """프로덕션 에이전트 평가 — 예외 발생 시에도 결과 보존"""
    
    with evaluation_session("production_eval") as monitor:
        for i, (question, ground_truth) in enumerate(test_cases):
            try:
                response = agent_fn(question)
                result = create_taskresult(
                    task_id=f"prod_{i:04d}",
                    question=question,
                    response=response,
                    ground_truth=ground_truth,
                    execution_time=0.0,  # 실제는 시간 측정 필요
                    task_type="qa",
                )
                monitor.record_task(result)
            except Exception as e:
                logger.error(f"태스크 {i} 실패: {e}")
                # 오류가 있어도 세션 계속 유지
        
        report = monitor.generate_report()
        return {
            "tcr": report.task_completion_rate,
            "accuracy": report.average_accuracy,
        }
    # with 블록 종료 시 results/production_eval.json 자동 저장
```

- `evaluation_session()`은 예외가 발생해도 `finally` 블록에서 `save_to_file()`을 호출해 그때까지의 결과를 보존한다
- 개별 태스크 오류를 `try/except`로 처리해 한 태스크의 실패가 전체 평가 세션을 중단시키지 않도록 한다
- `async_evaluation_session()`을 사용하면 FastAPI 엔드포인트나 async 에이전트에도 동일하게 적용된다

```bash
# 프로덕션 preset 시뮬레이션
python Evaluator_Examples/07_phoenix_hybrid.py

# evaluation_session 데이터 유실 방지 패턴
python Evaluator_Examples/06_operational.py
```

**예제 구성**

| 파일 | 패턴 | 프로덕션 배포 연결 |
|------|------|-------------------|
| 07_phoenix_hybrid | `setup_otel()` → `PerformanceMonitor` 순서 | Docker + Phoenix 서비스 통합 |
| 07_phoenix_hybrid | `HybridPerformanceMonitor` + API 키 조건 분기 | 환경별 활성화/비활성화 |
| 06_operational | `evaluation_session` 컨텍스트 매니저 | 예외 발생 시 자동 저장 보장 |
| 06_operational | `auto_save=True, auto_save_interval=10` | 장시간 실행 중 주기 저장 |

**실행 결과 (v0.8.0 기준)**

```
# 06_operational.py (evaluation_session 섹션)
evaluation_session 시작: results/session_YYYYMMDD
  태스크 10개 처리 중 예외 시뮬레이션...
  예외 발생 → 컨텍스트 매니저 자동 저장 (8개 태스크 보존)
evaluation_session 종료: results/session_YYYYMMDD.json 저장

# 07_phoenix_hybrid.py (auto_save 섹션)
PerformanceMonitor(auto_save=True, auto_save_interval=10)
  태스크 1~10 처리: auto_save 트리거 → periodic_save_01.json
  태스크 11~20 처리: auto_save 트리거 → periodic_save_02.json
```

> **Docker 배포 환경 변수**: `OTEL_EXPORTER_OTLP_ENDPOINT`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`를 `.env` 파일로 관리하고, `python-dotenv`의 `load_env()`로 로드한다. `07_phoenix_hybrid.py` 상단의 `os.getenv()` 패턴이 Docker 환경 변수 주입과 완전히 호환된다.
