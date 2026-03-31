# 빠른 시작 가이드

Agent Evaluator를 5분 안에 첫 평가까지 완성하는 최단 경로

**v0.6.7 | Python 3.8+**

---

## 목차

1. [설치](#설치)
2. [첫 번째 평가](#첫-번째-평가)
3. [헬퍼로 간편하게](#헬퍼로-간편하게)
4. [컨텍스트 매니저 패턴](#컨텍스트-매니저-패턴)
5. [대시보드 실행](#대시보드-실행)
6. [다음 단계](#다음-단계)

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
```

> **Python 3.8–3.12** 지원. numpy, pandas는 자동 설치됩니다.

---

## 첫 번째 평가

```python
from datetime import datetime
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# 1. 모니터 생성
monitor = PerformanceMonitor(output_dir="results/")

# 2. 에이전트 실행 결과 기록
monitor.record_task(TaskResult(
    task_id="task_001",
    task_type=TaskType.QA.value,
    success=True,
    completion_score=1.0,
    accuracy_score=0.92,
    execution_time=1.23,
    tokens_used={"input": 120, "output": 60, "total": 180},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now(),
))

# 3. 리포트 생성 & 저장
report = monitor.generate_report()
monitor.save_to_file("my_first_eval")  # results/my_first_eval.json + .html 생성

print(f"TCR: {report.task_completion_rate:.1f}%")
print(f"Accuracy: {report.overall_accuracy:.1f}%")
print(f"Avg Latency: {report.average_latency:.2f}s")
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

## 다음 단계

| 목적 | 문서 |
|------|------|
| 25개 지표 상세 (공식·출력키·임계값) | [02_METRICS_REFERENCE.md](02_METRICS_REFERENCE.md) |
| 프레임워크 통합 (LangChain/CrewAI/AutoGen/LangGraph) | [03_FRAMEWORK_GUIDE.md](03_FRAMEWORK_GUIDE.md) |
| 골든 데이터셋 구성 | [04_GOLDEN_DATASET_GUIDE.md](04_GOLDEN_DATASET_GUIDE.md) |
| 품질 임계값 설정 | [05_THRESHOLD_GUIDE.md](05_THRESHOLD_GUIDE.md) |
| 전체 API 레퍼런스 | [07_API_REFERENCE.md](07_API_REFERENCE.md) |
| 대시보드 UI 상세 | [08_DASHBOARD_GUIDE.md](08_DASHBOARD_GUIDE.md) |
| 사용 예제 파일 | [Evaluator_Examples/](../Evaluator_Examples/) |
