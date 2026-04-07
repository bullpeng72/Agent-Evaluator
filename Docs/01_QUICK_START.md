# 빠른 시작 가이드

Agent Evaluator를 5분 안에 첫 평가까지 완성하는 최단 경로

**v0.7.3 | Python 3.8+**

---

## 목차

1. [설치](#설치)
2. [데코레이터 방식 — 권장](#데코레이터-방식--권장)
3. [헬퍼로 간편하게](#헬퍼로-간편하게)
4. [컨텍스트 매니저 패턴](#컨텍스트-매니저-패턴)
5. [대시보드 실행](#대시보드-실행)
6. [보안·에이전틱 지표 활성화](#보안에이전틱-지표-활성화)
7. [CI/CD 품질 게이팅](#cicd-품질-게이팅)
8. [실시간 운영 모니터링](#실시간-운영-모니터링-v073)
9. [다음 단계](#다음-단계)

---

## 설치

```bash
# 기본 (Layer 1+2, 대시보드 포함)
pip install agent-evaluator[all]

# 최소 (Layer 1+2만)
pip install agent-evaluator

# 대시보드 포함 최소 구성
pip install agent-evaluator[serve]

# 프레임워크 통합 포함 (LangChain/LangGraph)
pip install agent-evaluator[langchain,serve]

# 실시간 운영 모니터링 (Phoenix + OTEL) — v0.7.3
pip install agent-evaluator[otel]
```

> **Python 3.8–3.13** 지원. numpy, pandas는 자동 설치됩니다.

---

## 데코레이터 방식 — 권장

에이전트 함수에 데코레이터 한 줄만 추가하면 자동으로 평가가 적용됩니다.

### QuickEval (가장 간단)

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa                          # task_type="qa" 자동 설정
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)   # 실제 에이전트 코드

# 데이터셋 실행
dataset = [("한국의 수도는?", "서울"), ("파이썬 창시자는?", "귀도 반 로섬")]
for question, answer in dataset:
    my_agent(question, ground_truth=answer)

eval.save()                        # results/quickeval.json + .html
eval.gate(tcr=85, accuracy=70)     # CI/CD 게이팅 — 실패 시 sys.exit(1)
```

### agent_eval 데코레이터 (세밀한 제어)

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for question, answer in dataset:
    my_agent(question, ground_truth=answer)

monitor.save_to_file("my_first_eval")  # results/my_first_eval.json + .html
report = monitor.generate_report()
print(f"TCR: {report.task_completion_rate:.1f}%")
```

### 용도별 단축 데코레이터

```python
eval = QuickEval("results/")

@eval.qa           # QA 평가
@eval.rag          # RAG — context_arg 자동, hallucination 탐지 활성
@eval.tool_use     # 도구 사용 에이전트
@eval.code         # 코드 생성
@eval.reasoning    # 추론 태스크
```

---

## 헬퍼로 간편하게

`create_taskresult()`는 question/response/ground_truth로 점수를 자동 계산합니다.

```python
from agent_evaluator import create_taskresult, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

# 점수 자동 계산 — accuracy_score, completion_score 불필요
result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",        # qa | code_generation | data_analysis | ...
)

monitor.record_task(result)
monitor.save_to_file("eval")
```

여러 태스크를 메서드 체이닝으로 기록할 수 있습니다.

```python
monitor.record_task(r1).record_task(r2).record_task(r3)
report = monitor.generate_report()
```

> 저수준 직접 생성이 필요한 경우에만 사용하세요. 일반적인 에이전트 평가는 데코레이터 방식을 권장합니다.

---

## 컨텍스트 매니저 패턴

세션 종료 시 자동 저장됩니다 (예외 발생 시에도 안전).

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("output_filename") as monitor:
    for item in dataset:
        response = my_agent.run(item["question"])
        result = create_taskresult(
            task_id=item["id"],
            question=item["question"],
            response=response,
            ground_truth=item["answer"],
            execution_time=0.5,
            task_type="qa",
        )
        monitor.record_task(result)
# 자동으로 results/output_filename.json + .html 저장
```

비동기 에이전트의 경우 `async_evaluation_session`을 사용합니다.

```python
from agent_evaluator import async_evaluation_session

async with async_evaluation_session("async_eval") as monitor:
    result = await my_async_agent.run(task)
    monitor.record_task(result)
```

---

## 대시보드 실행

```bash
# 기본 실행 (포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 옵션
agent-eval dashboard --port 8080 --watch     # 포트 지정 + 파일 감시
agent-eval dashboard --no-open               # 브라우저 자동 오픈 비활성화
agent-eval dashboard --offline               # CDN 에셋 로컬 캐시
```

대시보드는 `results/` 디렉토리의 JSON 파일을 자동으로 로드합니다.

---

## 보안·에이전틱 지표 활성화

```python
# 보안 지표 (Layer 2 Security)
monitor = PerformanceMonitor.for_secure_agents(
    output_dir="results/",
    security_config={
        "allowed_tools": ["search", "read"],
        "restricted_tools": ["delete", "execute"],
    },
)

# RAG 평가 (Hallucination 탐지 기본 활성)
monitor = PerformanceMonitor.for_rag_evaluation(output_dir="results/")
```

---

## CI/CD 품질 게이팅

```bash
# TCR 85% + Accuracy 70% 미만이면 exit 1 반환
agent-eval gate results/eval.json --tcr 85 --accuracy 70
```

---

## 실시간 운영 모니터링 (v0.7.3)

Phoenix + OpenTelemetry로 프로덕션 스팬을 실시간 추적합니다.

```bash
# Phoenix 서버 기동 + OTLP 수신 설정
agent-eval monitor

# 설치 상태 확인
agent-eval monitor --check
```

코드에서 직접 활성화:

```python
from agent_evaluator import setup_otel, PerformanceMonitor

setup_otel(endpoint="http://localhost:6006", service_name="my-agent")
monitor = PerformanceMonitor()
# record_task() 호출 시 OTLP 스팬 자동 발행
```

> 자세한 내용: [12_MONITOR_GUIDE.md](12_MONITOR_GUIDE.md)

---

## 다음 단계

| 목적 | 문서 |
|------|------|
| 25개 지표 상세 (공식·출력키·임계값) | [02_METRICS_REFERENCE.md](02_METRICS_REFERENCE.md) |
| 프레임워크 통합 (LangChain/CrewAI/AutoGen/LangGraph) | [03_FRAMEWORK_GUIDE.md](03_FRAMEWORK_GUIDE.md) |
| 골든 데이터셋 구성 | [04_GOLDEN_DATASET_GUIDE.md](04_GOLDEN_DATASET_GUIDE.md) |
| 품질 임계값 설정 | [05_THRESHOLD_GUIDE.md](05_THRESHOLD_GUIDE.md) |
| 전체 API 레퍼런스 | [07_API_REFERENCE.md](07_API_REFERENCE.md) |
| 대시보드 UI 상세 | [08_DASHBOARD_GUIDE.md](08_DASHBOARD_GUIDE.md) |
| 실시간 모니터링 (Phoenix + OTEL) | [12_MONITOR_GUIDE.md](12_MONITOR_GUIDE.md) |
| 사용 예제 파일 | [Evaluator_Examples/](../Evaluator_Examples/) |
