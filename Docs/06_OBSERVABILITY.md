# 관측성 가이드

대시보드 사용법 · Phoenix OTEL 실시간 모니터링

**v0.9.9 | Python 3.8+**

---

## 목차

1. [dashboard vs monitor — 역할 분리](#1-dashboard-vs-monitor--역할-분리)
2. [대시보드 실행 및 데이터 생성](#2-대시보드-실행-및-데이터-생성)
3. [22개 탭 활성화 분류](#3-22개-탭-활성화-분류)
4. [탭별 상세 가이드](#4-탭별-상세-가이드)
5. [운영 탭 설정 가이드](#5-운영-탭-설정-가이드)
6. [Phoenix OTEL 모니터링 — 빠른 시작](#6-phoenix-otel-모니터링--빠른-시작)
7. [Phoenix CLI 명세](#7-phoenix-cli-명세)
8. [setup_otel() API](#8-setup_otel-api)
9. [Phoenix 전송 데이터](#9-phoenix-전송-데이터)
10. [Phoenix UI 탭별 가이드](#10-phoenix-ui-탭별-가이드)
11. [Phoenix GraphQL 활용](#11-phoenix-graphql-활용)
12. [트러블슈팅](#12-트러블슈팅)

---

## 1. dashboard vs monitor — 역할 분리

| 구분 | `agent-eval dashboard` | `agent-eval monitor` |
|------|----------------------|----------------------|
| **대상** | 개발자 · QM | MLOps · 운영팀 |
| **단계** | 개발 · 검증 · 스테이징 | 프로덕션 · 운영 |
| **데이터 소스** | `save_to_file()` JSON | OTLP 스팬 스트림 (실시간) |
| **업데이트 방식** | 폴링 (15초 / --watch) | 스팬 수신 즉시 갱신 |
| **주요 뷰** | 지표 집계 · 태스크 테이블 | 트레이스 · 스팬 폭포수 · 실시간 오류 |
| **저장** | JSON 파일 (results/) | SQLite (Phoenix 내부) |
| **실행 방식** | 단일 FastAPI 서버 | Arize Phoenix 서버 + OTEL exporter |

```
에이전트 실행
    │
    ├─▶ save_to_file()  ──────────────▶  agent-eval dashboard
    │   (JSON 집계, 항상 동작)            개발·검증 단계 지표 확인
    │
    └─▶ OTLP Span Export (opt-in) ──▶  agent-eval monitor (Phoenix)
        (setup_otel() 호출 시)             프로덕션 실시간 트레이싱
```

---

## 2. 대시보드 실행 및 데이터 생성

```bash
# 기본 실행 (포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 포트 지정 + 파일 변경 자동 갱신
agent-eval dashboard --port 8765 --watch

# 브라우저 자동 오픈 비활성화
agent-eval dashboard --no-open

# 오프라인 모드 (CDN 에셋 로컬 캐시)
agent-eval dashboard --offline
```

대시보드는 `results/` 폴더의 JSON 파일을 자동으로 로드합니다. `--watch` 플래그 사용 시 파일 변경을 감지해 실시간 갱신됩니다.

### 데이터 생성 (save_to_file() 필수)

**방법 A — save_to_file() 직접 호출**

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

monitor.save_to_file("eval")  # results/eval.json + results/eval.html 생성
```

**방법 B — auto_save (N건마다 자동 저장)**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,
    auto_save_filename="auto_save",
)
```

**방법 C — QuickEval.save()**

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

eval.save()  # results/quickeval.json + .html 자동 생성
```

---

## 3. 22개 탭 활성화 분류

### 🟢 데코레이터만으로 가능 (10개)

`@agent_eval` / `@batch_eval` / `@conversation_eval` 적용 후 `save_to_file()` 호출만으로 자동 채워지는 탭.

| 메뉴 | 필요한 설정 |
|------|------------|
| 📊 **개요** | 기본 (항상) |
| 📋 **태스크** | 기본 (항상) |
| 💡 **인사이트** | 기본 (항상) |
| 🎯 **품질** | 기본 (환각: `enable_hallucination_detection=True`) |
| 💬 **멀티턴 대화** | `@conversation_eval` |
| ⚡ **성능** | 기본 (항상) |
| 🤖 **에이전틱** | `task_type="tool_use"` + 응답에 `tool_calls` 포함 |
| 🔁 **재현성·안정성** | Harness Gate C Config (`FaultToleranceConfig` 등) 전달 |
| 🔒 **보안** | `security=SecurityConfig()` 또는 `enable_security_metrics=True` |
| 🏗 **Harness Gate** | `@agent_eval`에 Harness Config 파라미터 전달 |

### 🟡 데코레이터 + 추가 작업으로 가능 (6개)

| 메뉴 | 추가로 필요한 것 |
|------|----------------|
| 🔬 **외부 평가 (RAG/DeepEval)** | `pip install ".[eval]"` + `HybridPerformanceMonitor` |
| 📡 **실시간** | `StreamingEvaluator` 생성 + `record()` + `_flush()` 명시 호출 |
| 🔔 **알림** | `alert_rules=` 파라미터 + 핸들러에서 JSONL 기록 |
| 👍 **사용자 반응** | `monitor.record_implicit_feedback()` 명시 호출 |
| 🚨 **이상 감지** | `PerformanceMonitor(enable_anomaly_detection=True)` |
| 💰 **평가 비용** | 토큰 비용 자동 / LLM Judge 비용: `llm_judge=LLMJudgeConfig()` |

### 🔵 데코레이터 무관으로 가능 (6개)

| 메뉴 | 작동 방식 |
|------|----------|
| 📂 **파일 비교** | `results/*.json` 2개 이상 → 드롭다운에서 두 파일 선택 |
| 🗂️ **케이스 검토** | `agent-eval dataset build`로 추출한 후보 케이스 승인/거부 |
| 📚 **골든 데이터셋** | `data/golden_datasets/*.json` 또는 `GoldenSetBuilder` |
| 📤 **내보내기** | JSON 원본 / 태스크별 CSV / 독립형 HTML 리포트 3가지 형식 |
| 🔍 **투명성** | `TestTransparencyManager.add_annotation()` 감사 로그 |
| 📖 **지표 설명** | (정적) 58개 지표 설명·계산식·해석 가이드 |
| ⚙️ **설정** | 대시보드 UI에서 임계값 직접 입력 (서버 재시작 시 초기화) |

---

## 4. 탭별 상세 가이드

### Overview 탭

- **총 태스크 수** — 평가된 전체 태스크 카운트
- **평균 완료율 (TCR)** — 전체 task completion rate 평균
- **평균 정확도** — AccuracyEvaluator 기반 전체 평균
- **평균 응답 시간** — 실행 시간 평균 (초)
- **총 토큰 비용** — 누적 비용 추정 (USD)
- 프레임워크 분포 도넛 차트, 태스크 유형 분포 바 차트

### Quality 탭

| 카드 | 표시 값 | 해석 |
|------|---------|------|
| Accuracy Score | 전체 정확도 % | >75% 권장 |
| Quality Score | `/5.0` 스케일 | >3.5/5.0 권장 |
| Hallucination | 환각 발생 건수 | 0에 가까울수록 좋음 |

> **주의**: Quality Score는 `/5.0` 스케일입니다. `/10`이 아님.

- **응답 품질 차원 레이더**: Relevance / Completeness / Accuracy / Clarity / Usefulness
- **환각 탐지 패널**: `enable_hallucination_detection=True` 설정 시에만 데이터 수집됨

### Agentic 탭 (3개 서브탭)

**실행·재시도 서브탭**
- TCR, 재시도율, 첫 시도 성공률, 평균 재시도 시간 KPI
- 태스크 유형별 재시도 분포 바 차트

**도구·협업·흐름 서브탭**
- Tool Selection F1 (Precision/Recall/F1) 패널
- 멀티에이전트 협업 패널 (상호작용 건수, 협업 패턴)
- 워크플로우 퍼널 차트 (단계 그룹별 병목 시각화)

**실행 트레이스 서브탭**
- 태스크별 전체 실행 흐름 타임라인
- 각 단계 소요 시간 바 차트, 실패 단계 하이라이트

### Security 탭

`enable_security_metrics=True`로 실행한 평가만 데이터가 표시됩니다.

- **입력 위협 패널**: SQL/Command/XSS/Path/Prompt Injection 분포
- **출력 유출 패널**: API Key / Password / Credit Card / Email / Phone / SSN / Internal IP / File Path 8가지 유형
- **권한 준수 / 권한 상승 / 공격 체인 패널**: 각 트래커별 위반율 / 탐지율

### RAG 탭

`HybridPerformanceMonitor` + `use_ragas=True` 필요.
Faithfulness / Answer Relevancy / Context Precision / Context Recall KPI 카드 및 라인 차트.

### DeepEval 탭

`HybridPerformanceMonitor` + `use_deepeval=True` 필요.
G-Eval Score / Hallucination / Toxicity / Bias / Answer Relevancy KPI 카드.

---

## 5. 운영 탭 설정 가이드

| 탭 | 데코레이터만으로 가능? | 필수 추가 조치 |
|---|:---:|---|
| **실시간** | ❌ | `StreamingEvaluator` 생성 + `record()` + `_flush()` |
| **알림** | ⚠️ 반자동 | `alert_rules=` + 핸들러 내 JSONL 기록 |
| **사용자 반응** | ❌ | `monitor.record_implicit_feedback()` 명시 호출 |
| **이상 감지** | ✅ | `PerformanceMonitor(enable_anomaly_detection=True)` |
| **평가 비용** | ✅ | 토큰 자동 / LLM Judge 비용: `llm_judge=LLMJudgeConfig()` |

### 실시간 탭

```python
from agent_evaluator.streaming.evaluator import StreamingEvaluator

monitor = PerformanceMonitor(output_dir="results/")
streaming = StreamingEvaluator(monitor=monitor, window_size=20, flush_interval=30)

result = create_taskresult(...)
monitor.record_task(result)
streaming.record(result)

streaming._flush()         # 저장 전 반드시 호출
monitor.save_to_file("eval")
```

### 알림 탭

알림 탭은 `results/alerts/YYYY-MM-DD.jsonl` 파일을 읽습니다.

```python
import json
from datetime import date, datetime
from agent_evaluator import SimpleTaskAlertRule, agent_eval
import os

_TODAY_JSONL = f"results/alerts/{date.today()}.jsonl"
os.makedirs("results/alerts", exist_ok=True)

def _write_alert_jsonl(rule_name: str, severity: str, message: str, task_id: str = ""):
    event = {
        "triggered_at": datetime.now().isoformat(),
        "rule_name": rule_name,
        "severity": severity,
        "message": message,
        "task_id": task_id,
    }
    with open(_TODAY_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

slow_rule = SimpleTaskAlertRule(
    name="slow_response",
    condition=lambda tr: tr.execution_time > 3.0,
    handler=lambda msg, tr: _write_alert_jsonl("slow_response", "warning", msg, tr.task_id),
    severity="warning",
)

@agent_eval(monitor, task_type="qa", alert_rules=[slow_rule])
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### 사용자 반응 탭

```python
monitor.record_task(result)

# feedback_type: "thumbs_up" | "thumbs_down" | "follow_up_question" |
#                "task_abandonment" | "retry_request" | "dwell_time"
monitor.record_implicit_feedback(
    task_id=result.task_id,
    feedback_type="thumbs_up",
    metadata={"dwell_time": 8.5, "source": "ui"},
)

monitor.save_to_file("eval")
```

### 이상 감지 탭

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,
    anomaly_baseline_window=50,
    anomaly_detection_window=10,
)
# save_to_file() 시 자동으로 AnomalyDetector.scan() 실행 — 별도 코드 불필요
```

| 탐지 유형 | 최소 태스크 수 | 알고리즘 |
|-----------|:---:|---------|
| `latency_trend` | 5+ | 선형 회귀 (기울기 > 0.05초/태스크) |
| `accuracy_drift` | 5+ | Z-score (기준선 대비 이탈 > 2.5σ) |
| `token_spike` | 5+ | IQR (Q3 + 2×IQR 초과) |
| `error_surge` | detection_window+ | 비율 (오류율 > 20% AND 기준선의 2배) |

---

## 6. Phoenix OTEL 모니터링 — 빠른 시작

> **처음 사용하시나요?** 이 3단계만 따라 하면 Phoenix UI에서 실시간으로 에이전트 실행 결과를 확인할 수 있습니다.

### 단계 1: 설치

```bash
# OTEL 모니터링 — [otel] 또는 [sdk] extra 필요
pip install "agent-evaluator[sdk]"
```

### 단계 2: Phoenix 서버 기동 (터미널 A)

```bash
agent-eval monitor
# 출력: Phoenix UI → http://localhost:6006
```

### 단계 3: 에이전트 실행 (터미널 B)

```python
from agent_evaluator import setup_otel, PerformanceMonitor
from agent_evaluator.decorators import agent_eval

# ① PerformanceMonitor 생성 전에 반드시 호출
setup_otel(endpoint="http://localhost:6006", service_name="my-agent")

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("한국의 수도는?", ground_truth="서울")

# 점수 저장 (Phoenix에 Annotation 전송)
monitor.save_to_file("run_001")
```

> `http://localhost:6006` → Tracing 탭에서 결과 확인

---

## 7. Phoenix CLI 명세

```bash
# Phoenix 서버 기동 + 브라우저 자동 오픈
agent-eval monitor

# 포트 지정 (기본 6006)
agent-eval monitor --port 6006

# 브라우저 자동 오픈 비활성화
agent-eval monitor --no-open

# 기존 Phoenix 서버에 연결 (자체 기동 안 함)
agent-eval monitor --attach http://localhost:6006

# 환경 상태 확인 (설치 여부, 포트 상태)
agent-eval monitor --check
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | `6006` | Phoenix UI / OTLP HTTP 포트 (Phoenix 13.x: 동일 포트) |
| `--host` | `localhost` | Phoenix 바인딩 호스트 |
| `--no-open` | (플래그) | 브라우저 자동 오픈 비활성화 |
| `--attach <url>` | — | 자체 기동 없이 기존 Phoenix에 연결 |
| `--check` | (플래그) | 설치 상태 및 포트 점유 확인 |
| `--working-dir <path>` | `./` | Phoenix DB 저장 디렉토리 |

---

## 8. setup_otel() API

```python
from agent_evaluator import setup_otel

setup_otel(
    endpoint="http://localhost:6006",   # Phoenix 13.x 기본 포트 (UI + OTLP 동일)
    service_name="my-agent",           # Phoenix UI 서비스 이름
    enabled=True,                      # False 시 no-op (CI 환경 등)
    enable_metrics=False,              # Phoenix는 /v1/metrics 미지원 — Grafana 등에서만 사용
)
```

> **순서 주의**: `setup_otel()`은 반드시 `PerformanceMonitor` 생성 **전**에 호출해야 합니다.

### CI/CD 환경에서 비활성화

```python
import os
from agent_evaluator import setup_otel

if os.getenv("CI") != "true":
    setup_otel(endpoint="http://localhost:6006")
# CI에서는 setup_otel() 미호출 → OTEL no-op, JSON 저장은 정상 동작
```

### Phoenix 미실행 시 자동 비활성화 패턴

```python
def _try_setup_otel(service_name: str) -> None:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("localhost", 6006)) != 0:
            return  # Phoenix 미실행 — no-op
    from agent_evaluator import setup_otel
    setup_otel(endpoint="http://localhost:6006", service_name=service_name)
    print(f"Phoenix 모니터링 활성화 — http://localhost:6006")

_try_setup_otel("my-service")
```

---

## 9. Phoenix 전송 데이터

### TaskType → span kind 매핑

| TaskType | span kind |
|----------|-----------|
| `qa`, `code_generation`, `coding`, `creative` | `LLM` |
| `information_retrieval` | `RETRIEVER` |
| `tool_use` | `TOOL` |
| `planning` | `AGENT` |
| `data_analysis`, `document_creation`, `reasoning` | `CHAIN` |

### Phoenix Annotations (점수 전송)

`save_to_file()` 호출 시 `/v1/span_annotations` API로 전송:

| Evaluator 이름 | 점수 범위 | 레이블 |
|----------------|-----------|--------|
| `accuracy` | 0.0–1.0 | pass (≥0.5) / fail (<0.5) |
| `completion` | 0.0–1.0 | pass / fail |
| `success` | 1.0 (성공) / 0.0 (실패) | pass / fail |

> **확인 경로**: Tracing 탭 → 스팬 클릭 → 우측 **"Annotations"** 섹션
> (상단 메뉴의 "Evaluators" 탭이 아님)

---

## 10. Phoenix UI 탭별 가이드

### Tracing 탭 — 에이전트 실행 기록

`record_task()`를 호출할 때마다 여기에 한 줄씩 기록됩니다.

- 스팬 이름 (예: `ae.task/qa/task_001`)
- 성공/실패 상태, 실행 시간, 입력/출력 텍스트
- **Annotations 확인**: 스팬 클릭 → 우측 패널 → "Annotations" 섹션 (save_to_file() 후 ~3초)

```bash
# 프로젝트별 스팬 분리
setup_otel(service_name="프로젝트명")  # Phoenix UI 상단 드롭다운에서 선택 가능
```

### Datasets 탭 — 골든 데이터셋 관리

```python
from agent_evaluator.datasets import GoldenSetBuilder

builder = GoldenSetBuilder(source_dir="results/", output_dir="data/golden_datasets/")
cases = builder.extract(strategies=["high_value"], max_cases=50)
builder.push_to_phoenix(cases, dataset_name="qa-golden-v1")
```

### Playground 탭 — 프롬프트 재현 도구

특정 스팬의 입력/출력을 가져와서 프롬프트를 수정·재시도할 수 있습니다.
`llm.prompts` 속성을 스팬에 포함하면 Playground에서 재현 가능합니다.

```python
@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> tuple:
    response = "서울입니다."
    return response, EvalMetadata(
        extra={"llm.prompts": [{"role": "user", "content": question}]}
    )
```

### Evaluators 탭

> ⚠️ **자주 하는 오해**: Agent-Evaluator의 `accuracy`/`completion`/`success` 점수는
> **이 탭에 표시되지 않습니다**. 이 점수들은 Tracing 탭 → 스팬 상세 → "Annotations" 섹션에 있습니다.
> Evaluators 탭이 비어있는 것은 정상입니다.

### Prompts 탭 — 프롬프트 버전 관리

```python
import requests

response = requests.post("http://localhost:6006/v1/prompts", json={
    "name": "qa-system-prompt",
    "version": "v1.0",
    "template": "당신은 정확한 답변을 제공하는 AI 어시스턴트입니다.\n질문: {question}\n답변:",
})
```

---

## 11. Phoenix GraphQL 활용

GraphQL UI 접속: `http://localhost:6006/graphql`

### 준비된 쿼리 5가지

**쿼리 1: 프로젝트 목록 조회**

```graphql
query {
  projects {
    edges {
      node { id name traceCount spanCount createdAt }
    }
  }
}
```

**쿼리 2: 스팬 목록 + 평가 점수 조회**

```graphql
query GetSpansWithAnnotations($projectName: String!) {
  project(name: $projectName) {
    spans(first: 20) {
      edges {
        node {
          spanId name statusCode latencyMs
          input { value }
          output { value }
          spanAnnotations { name score label }
        }
      }
    }
  }
}
```

**쿼리 3: 데이터셋 목록 조회**

```graphql
query {
  datasets {
    edges {
      node { id name description exampleCount createdAt }
    }
  }
}
```

**쿼리 4: 데이터셋 생성**

```graphql
mutation CreateDataset {
  createDataset(name: "qa-golden-v2" description: "QA 평가용 골든셋 v2") {
    dataset { id name }
  }
}
```

**쿼리 5: 데이터셋에 예시 추가**

```graphql
mutation AddDatasetExamples($datasetId: GlobalID!) {
  addSpansToDataset(datasetId: $datasetId spanIds: [] examples: [
    {
      input: { question: "한국의 수도는?" }
      output: { answer: "서울" }
      metadata: { source: "manual" }
    }
  ]) {
    dataset { id name exampleCount }
  }
}
```

### Python에서 GraphQL 호출

```python
import requests

def query_phoenix(query: str, variables: dict = None) -> dict:
    response = requests.post(
        "http://localhost:6006/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

result = query_phoenix("""
    query { projects { edges { node { id name traceCount } } } }
""")
```

---

## 12. 트러블슈팅

### 대시보드에 데이터가 없는 경우

```bash
ls results/*.json     # JSON 파일이 있는지 확인
python Evaluator_Examples/ch02_quickstart.py
agent-eval dashboard
```

### 특정 탭이 비어 있는 경우

| 탭 | 필요 설정 |
|----|----------|
| 실시간 | `StreamingEvaluator` + `record()` + `_flush()` |
| 알림 | `alert_rules=` 파라미터 + 핸들러에서 JSONL 기록 |
| 사용자 반응 | `monitor.record_implicit_feedback()` |
| 이상 감지 | `enable_anomaly_detection=True` |
| Quality — Hallucination | `enable_hallucination_detection=True` |
| Security | `enable_security_metrics=True` |
| RAG | `HybridPerformanceMonitor` + Ragas 데이터 |

### Phoenix Annotations이 안 보이는 경우

1. `setup_otel()`을 `PerformanceMonitor` **생성 전**에 호출했는지 확인
2. `save_to_file()` 호출 후 약 3초 대기 후 새로고침
3. Tracing 탭 → 스팬 클릭 → **"Annotations"** 섹션 확인 (Evaluators 탭이 아님)

### agent-eval monitor 포트 충돌

```bash
lsof -ti :6006 | xargs kill -9
agent-eval monitor
# 또는 기존 서버 유지 후 연결
agent-eval monitor --attach http://localhost:6006
```

---

| 목적 | 문서 |
|------|------|
| 설치 · 기본 사용법 | [01_GETTING_STARTED.md](01_GETTING_STARTED.md) |
| 58개 지표 상세 | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| 데코레이터 · 프레임워크 통합 | [03_INTEGRATION_GUIDE.md](03_INTEGRATION_GUIDE.md) |
| 품질 임계값 · CI/CD | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| Docker · 환경별 설정 | [07_OPERATIONS.md](07_OPERATIONS.md) |
