# Chapter 10. 대시보드와 시각화

> **이 챕터에서 배우는 것**
> - Agent-Evaluator 대시보드의 아키텍처와 50+ 엔드포인트 구조를 이해한다
> - 21개 메뉴를 🟢데코레이터만 / 🟡데코레이터+추가작업 / 🔵데코레이터무관 3가지로 분류하고 각 작동 방식을 파악한다
> - `save_to_file()`, `auto_save`, `QuickEval.save()` 3가지 데이터 생성 방법을 익힌다
> - 핵심 API 엔드포인트를 활용해 문제 케이스를 빠르게 찾는 법을 배운다
> - 실시간 업데이트와 데이터 내보내기 방법을 파악한다
> - QA 관리자를 위한 매일 5분 대시보드 점검 루틴을 수립한다

---

## 10.1 대시보드 아키텍처 — 50+ 엔드포인트 구조

Agent-Evaluator 대시보드는 **FastAPI 백엔드 + Alpine.js 프론트엔드** 조합으로 만들어진 경량 웹 애플리케이션이다. 별도의 데이터베이스가 없고, `results/` 디렉토리의 JSON 파일을 실시간으로 읽어서 시각화한다.

### 전체 구조

```
[Python 평가 코드]
    → monitor.save_to_file() 또는 eval.save()
    → results/eval.json + results/eval.html 생성

[대시보드 서버]
    FastAPI (포트 8765)
    ├── /api/stats                               — 전체 통계 요약
    ├── /api/results                             — 평가 파일 목록
    ├── /api/results/{file_id}                   — 특정 파일 태스크 목록 (정렬/필터)
    ├── /api/results/{file_id}/tasks/filter      — 복합 조건 필터 (POST)
    ├── /api/results/{file_id}/distributions     — 지표 분포
    ├── /api/results/{file_id}/timeline          — 시간대별 품질 추이
    ├── /api/anomalies                           — 이상 탐지 이벤트 목록
    ├── /api/cost/breakdown                      — 비용 분석
    ├── /api/cost/trend                          — 비용 추이
    ├── /api/results/{file_id}/llm_judge         — LLM Judge 점수
    ├── /api/conversation                        — 대화 세션 목록
    ├── /api/export/excel/{file_id}              — Excel 내보내기
    └── /ws/events                               — WebSocket 실시간 업데이트

[브라우저]
    Alpine.js 프론트엔드
    → Overview / Quality / Agentic / Security / RAG / DeepEval 탭
    → 차트: Chart.js (라인, 바, 도넛, 레이더, 히스토그램)
```

### 탭별 주요 기능

| 탭 | 핵심 내용 | 특이사항 |
|----|----------|---------|
| **Overview** | TCR, Accuracy, 응답시간, 비용 KPI 카드 | 프레임워크 분포 도넛 차트 |
| **Quality** | 정확도, 품질 점수, 환각 탐지, RAG 지표 | Quality는 /5.0 스케일 |
| **Agentic** | 도구 호출, 재시도, 워크플로우, 협업 | 3개 서브탭으로 구성 |
| **Security** | 5종 보안 지표, 위협 이벤트 타임라인 | `enable_security_metrics=True` 필요 |
| **RAG** | Faithfulness, Answer Relevancy, Context Precision/Recall | `HybridPerformanceMonitor` 필요 |
| **DeepEval** | G-Eval, Toxicity, Bias, Answer Relevancy | `use_deepeval=True` 필요 |

---

## 10.2 메뉴별 활성화 분류 — 무엇이 자동이고 무엇이 아닌가

대시보드를 처음 열면 일부 탭이 비어 있다. "어떤 탭은 자동으로 채워지고, 어떤 탭은 추가 작업이 필요한가"를 파악하는 것이 대시보드 활용의 출발점이다. 21개 메뉴는 세 가지 유형으로 나뉜다.

### 🟢 유형 1: 데코레이터만으로 가능 (8개)

`@agent_eval` 또는 `@batch_eval` / `@conversation_eval`을 붙이고 `save_to_file()`을 호출하면 자동으로 채워지는 탭이다. 추가 설정이 전혀 없어도 된다.

**📊 개요 · 📋 태스크 · 💡 인사이트 · ⚡ 성능**

```
@agent_eval(monitor, task_type="qa")
def my_agent(...) → TaskResult
         ↓
TaskCompletionTracker + AccuracyEvaluator + LatencyTracker + TokenEconomyTracker
         ↓ save_to_file()
JSON: summary / tasks[] / insights / efficiency_metrics
         ↓
개요(KPI 카드) · 태스크(상세 테이블) · 인사이트(자동 경고) · 성능(P95 지연·토큰)
```

**🎯 품질**

`ResponseQualityEvaluator`가 모든 태스크에서 자동으로 Relevance·Completeness·Accuracy·Clarity·Usefulness 5개 차원을 측정한다. 환각 탭은 `enable_hallucination_detection=True` 설정 시에만 활성화된다.

**💬 멀티턴 대화**

`@conversation_eval` 데코레이터 전용. `ConversationSession.compute_metrics()`가 자동 호출되어 턴 수·컨텍스트 유지율·주제 일관성 등 7개 지표를 계산한다.

**🤖 에이전틱**

응답에 `tool_calls` 데이터가 있으면 `ToolCallAnalyzer`·`RetryCorrectionTracker`·`ToolSelectionTracker` 등이 자동 실행된다. `@agent_eval(framework="langchain")` 처럼 프레임워크를 지정하면 응답 객체에서 도구 호출 이력을 자동 추출한다.

**🔒 보안**

`@agent_eval(..., security_mode=True)` 파라미터 하나로 5개 보안 트래커(입력 위협·출력 유출·도구 권한·권한 상승·체인 공격)를 활성화한다. 성능 오버헤드로 인해 기본값은 False다.

---

### 🟡 유형 2: 데코레이터 + 추가 작업으로 가능 (6개)

데코레이터 사용은 전제이되, **별도 객체 생성·플래그 설정·외부 패키지 설치** 중 하나가 추가로 필요하다.

**🔬 외부 평가**

Ragas·DeepEval 지표를 채우려면 `HybridPerformanceMonitor`와 외부 패키지가 필요하다.

```python
# pip install "agent-evaluator[eval]" + OpenAI API 키 필요
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    output_dir="results/",
    enable_ragas=True,     # Faithfulness · Answer Relevancy · Context Recall/Precision
    enable_deepeval=True,  # G-Eval · Hallucination · Toxicity · Bias
)
# → JSON: rag_metrics, advanced_metrics 키 생성
```

**📡 실시간**

`StreamingEvaluator`를 별도로 생성하고, 저장 전에 `_flush()`를 반드시 호출해야 한다. `_flush()` 없으면 `streaming_data` 키가 JSON에 포함되지 않아 탭이 공백이다.

```python
from agent_evaluator.streaming.evaluator import StreamingEvaluator

streaming = StreamingEvaluator(monitor=monitor, window_size=20)
# 태스크마다: streaming.record(task_result)
streaming._flush()   # ← 저장 전 필수
monitor.save_to_file("eval")
```

**🔔 알림**

`SimpleTaskAlertRule`을 생성하고 `alert_rules=` 파라미터로 전달한다. 대시보드 알림 탭은 `results/alerts/YYYY-MM-DD.jsonl` 파일을 직접 읽으므로, **핸들러 함수 안에서 JSONL 기록 코드를 직접 구현**해야 한다.

```python
import json
from agent_evaluator import SimpleTaskAlertRule

def _record_alert(msg, tr):
    with open(f"results/alerts/{date.today()}.jsonl", "a") as f:
        f.write(json.dumps({"message": msg, "task_id": tr.task_id}) + "\n")

rule = SimpleTaskAlertRule(
    name="slow", condition=lambda tr: tr.execution_time > 3.0,
    handler=_record_alert, severity="warning",
)

@agent_eval(monitor, task_type="qa", alert_rules=[rule])
def my_agent(...): ...
```

**👍 사용자 반응**

UI 클릭·별점·재질문 등은 에이전트 외부에서 발생하므로 평가 루프 안에서 수동으로 기록해야 한다.

```python
# 반드시 monitor의 메서드를 사용 — 독립 인스턴스 생성 금지
monitor.record_implicit_feedback(
    task_id=result.task_id,
    feedback_type="thumbs_up",   # thumbs_up/down, follow_up_question, task_abandonment 등
    metadata={"dwell_time": 8.5},
)
```

**🚨 이상 감지**

`PerformanceMonitor` 생성 시 플래그 하나를 추가하면 `save_to_file()` 시점에 자동으로 이상 탐지를 실행한다.

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,   # ← 이것만 추가
    anomaly_baseline_window=50,
)
# save_to_file() 시 AnomalyDetector.scan() 자동 호출
# → JSON: anomaly_data 키 생성
# 탐지 유형: latency_trend / accuracy_drift / token_spike / error_surge
```

**💰 평가 비용**

토큰 사용 비용은 `TokenEconomyTracker`가 자동 계산한다. LLM Judge API 호출 비용을 포함하려면 `enable_llm_judge=True`를 추가한다.

```python
# 기본 토큰 비용: 추가 설정 불필요
# LLM Judge 비용 포함 시:
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,
    llm_judge_model="claude-haiku-4-5-20251001",  # 비용 효율적 모델 권장
)
# 비용은 각 task.extra["llm_judge"]["cost_usd"]에 기록됨
```

---

### 🔵 유형 3: 데코레이터 무관으로 가능 (6개)

결과 JSON 파일이 있으면 데코레이터 없이도 완전히 동작하는 관리·도구 탭이다.

| 메뉴 | 작동 방식 | QA 활용법 |
|------|----------|----------|
| **📂 파일 비교** | `results/` 에 JSON 2개 이상 → 드롭다운 선택 → 지표 차이 자동 계산 | 신버전 배포 전 A/B 비교, 회귀 여부 판단 |
| **📚 골든 데이터셋** | `agent-eval dataset build results/ --min-score 0.8` CLI 또는 UI 직접 편집 | 높은 품질 응답을 정답 기준으로 축적 |
| **📤 내보내기** | JSON·CSV·HTML 3가지 형식 다운로드 | 주간 리포트 팀 공유, 스프레드시트 추가 분석 |
| **🔍 투명성** | `TestTransparencyManager.add_annotation()` 독립 호출 | 감사 로그, 규정 준수 근거 기록 |
| **📖 지표 설명** | 항상 표시 (정적 문서) | 지표 의미·계산식 빠른 참조 |
| **⚙️ 설정** | UI에서 임계값 입력 → 💡 인사이트 탭 경고 기준 즉시 반영 | 프로젝트별 품질 기준 조정 |

> **QA 관리자를 위한 팁**: 유형 1의 8개 탭만으로도 일상적인 품질 모니터링의 80%를 커버할 수 있다. 유형 2는 단계적으로 도입하되, 이상 감지(`enable_anomaly_detection=True`)를 첫 번째 추가 항목으로 권장한다.

---

## 10.3 데이터 생성 — save_to_file() 3가지 방법

대시보드는 데이터를 직접 생성하지 않는다. 평가 코드가 JSON 파일을 만들어야 대시보드가 읽을 수 있다. 3가지 방법이 있다.

### 방법 A — save_to_file() 직접 호출

가장 명시적인 방법. 평가가 끝난 후 명시적으로 저장한다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 평가 실행
for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# 저장 — results/evaluation.json + results/evaluation.html 동시 생성
monitor.save_to_file("evaluation")
```

`save_to_file("평가명")`을 호출하면 JSON과 HTML 두 파일이 자동으로 생성된다. JSON은 대시보드가 읽고, HTML은 독립 실행형 보고서로 이메일로 공유할 수 있다.

### 방법 B — auto_save (N건마다 자동 저장)

장시간 실행되는 평가에서 유용하다. 중간에 프로세스가 죽어도 데이터가 보존된다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,        # 10건마다 자동 저장
    auto_save_filename="auto_save",
)

@agent_eval(monitor, task_type="qa")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 1,000건 평가 실행 — 100번 자동 저장
for q, gt in large_dataset:
    my_agent(q, ground_truth=gt)
```

프로덕션 환경에서 연속 평가를 돌릴 때는 `auto_save_interval=50` 정도가 적당하다. 너무 자주 저장하면 디스크 I/O 부담이 생긴다.

### 방법 C — QuickEval.save()

가장 간편한 방법. `QuickEval`을 사용할 때의 표준 저장 방식이다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

for q, gt in dataset:
    my_agent(q, ground_truth=gt)

# results/quickeval.json + results/quickeval.html 생성
eval.save()

# 파일명 지정도 가능
eval.save("my_eval_20260409")
```

### flush_every — 데코레이터에서 N회마다 자동 저장

데코레이터 수준에서 저장 주기를 제어할 수도 있다. 여러 에이전트를 동시에 평가할 때 유용하다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval

monitor = PerformanceMonitor(output_dir="results/")

# 20회 호출마다 자동 저장
@agent_eval(monitor, task_type="qa", flush_every=20, flush_filename="periodic")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

**방법 선택 가이드:**

| 상황 | 권장 방법 |
|------|---------|
| 스크립트 단순 실행 후 결과 보기 | 방법 A (직접 호출) |
| 장시간/대량 평가 | 방법 B (auto_save) |
| QuickEval 사용 중 | 방법 C (eval.save()) |
| 프로덕션 실시간 모니터링 | 방법 B + flush_every 조합 |

---

## 10.4 대시보드 실행

```bash
# 기본 실행 — results/ 디렉토리, 포트 8765
agent-eval dashboard

# 특정 경로 + 파일 변경 감시
agent-eval dashboard results/ --watch

# 포트 변경
agent-eval dashboard --port 8080

# 브라우저 자동 오픈 비활성화 (서버 환경)
agent-eval dashboard --no-open

# 오프라인 모드 (CDN 없는 폐쇄망)
agent-eval dashboard --offline
```

접속 URL: `http://localhost:8765`

`--watch` 모드를 사용하면 `results/` 폴더에 새 JSON 파일이 생기거나 기존 파일이 변경될 때 자동으로 갱신된다. 평가 스크립트를 별도 터미널에서 실행하면서 대시보드를 동시에 보는 개발 워크플로우에 적합하다.

---

## 10.5 핵심 API 엔드포인트 활용

대시보드 UI가 편리하지만, API를 직접 호출하면 더 세밀한 분석이 가능하다. 모든 엔드포인트는 `http://localhost:8765`를 기준으로 한다.

### /api/stats — 전체 통계 한눈에 보기

```bash
curl http://localhost:8765/api/stats | python3 -m json.tool
```

응답 예시:
```json
{
  "total_tasks": 500,
  "task_completion_rate": 0.912,
  "overall_accuracy": 0.784,
  "quality_score": 3.9,
  "p95_latency": 4.2,
  "total_cost_usd": 12.45,
  "hallucination_rate": 0.032,
  "security_incidents_count": 2
}
```

매일 아침 이 숫자를 확인하는 것으로 5분 점검을 시작한다.

### /api/results/{file_id} — 태스크 목록 정렬/필터

`{file_id}`는 `results/` 디렉토리에 저장된 평가 파일명(확장자 제외)이다. 예: `evaluation`, `quickeval`.

```bash
# 정확도 낮은 케이스 10개 — 문제 케이스 우선 조사
curl "http://localhost:8765/api/results/evaluation?sort_by=accuracy_score&sort_desc=false&limit=10"

# 가장 느린 케이스 10개 — 응답시간 병목 조사
curl "http://localhost:8765/api/results/evaluation?sort_by=execution_time&sort_desc=true&limit=10"

# 특정 태스크 유형만 필터
curl "http://localhost:8765/api/results/evaluation?task_type=qa&sort_by=accuracy_score&sort_desc=false"
```

### /api/results/{file_id}/tasks/filter — 복합 조건 필터

단순 정렬로 부족할 때 복합 조건을 사용한다.

```bash
# accuracy < 0.6 AND execution_time > 5.0인 태스크 (동시에 느리고 부정확)
curl -X POST http://localhost:8765/api/results/evaluation/tasks/filter \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": [
      {"field": "accuracy_score", "op": "lt", "value": 0.6},
      {"field": "execution_time", "op": "gt", "value": 5.0}
    ],
    "logic": "AND"
  }'

# 특정 오류 메시지가 포함된 케이스
curl -X POST http://localhost:8765/api/results/evaluation/tasks/filter \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": [
      {"field": "errors", "op": "contains", "value": "timeout"}
    ]
  }'
```

지원하는 연산자: `eq` (같음), `ne` (다름), `gt` (초과), `gte` (이상), `lt` (미만), `lte` (이하), `contains` (포함), `in` (목록 중 하나)

### /api/results/{file_id}/distributions — 지표 분포 히스토그램

```bash
# accuracy_score 분포 — 점수가 어느 구간에 몰려 있는지 확인
curl "http://localhost:8765/api/results/evaluation/distributions?metric=accuracy_score"

# execution_time 분포
curl "http://localhost:8765/api/results/evaluation/distributions?metric=execution_time"
```

분포를 보면 "평균은 괜찮은데 하위 10%가 매우 나쁜" 패턴을 발견할 수 있다. 평균만 보면 놓치는 문제다.

### /api/results/{file_id}/timeline — 시간대별 품질 변화

```bash
# 시간대별 품질 추이 (배포 전후 비교에 유용)
curl "http://localhost:8765/api/results/evaluation/timeline?metric=accuracy_score&granularity=hour"

# 일별 TCR 추이
curl "http://localhost:8765/api/results/evaluation/timeline?metric=task_completion_rate&granularity=day"
```

배포 직후 `/timeline`을 확인하면 새 버전이 품질에 긍정적/부정적 영향을 주는지 즉시 파악할 수 있다.

### /api/anomalies — 이상 탐지 이벤트 목록

```bash
# 전체 이상 이벤트 목록
curl http://localhost:8765/api/anomalies

# 특정 파일의 이상 이벤트 목록
curl "http://localhost:8765/api/anomalies/evaluation"

# 특정 이벤트 상세 분석 (원인 + 권고사항)
curl "http://localhost:8765/api/results/evaluation/anomaly/explain/event_20260409_001"
```

이상 탐지(AnomalyDetector)가 활성화되어 있을 때만 데이터가 쌓인다. Z-Score 기반으로 정상 범위를 벗어난 태스크를 자동으로 표시한다.

### /api/cost/breakdown — 모델별/태스크별 비용 분석

```bash
# 비용 분석 — 어느 태스크 유형이 비용을 가장 많이 쓰는가
curl http://localhost:8765/api/cost/breakdown

# 비용 추이 — 일별 비용 변화
curl "http://localhost:8765/api/cost/trend?granularity=day"
```

응답 예시:
```json
{
  "total_cost_usd": 47.23,
  "by_task_type": {
    "qa": 12.10,
    "information_retrieval": 25.44,
    "code_generation": 9.69
  },
  "by_model": {
    "gpt-4o": 38.50,
    "gpt-4o-mini": 8.73
  }
}
```

### /api/results/{file_id}/llm_judge — LLM Judge 점수 필터링

```bash
# completeness 낮은 케이스 조회 (ground_truth 없이 평가된 케이스)
curl "http://localhost:8765/api/results/evaluation/llm_judge?min_score=0&max_score=3.0&limit=20"

# LLM Judge 전체 집계
curl "http://localhost:8765/api/results/evaluation/llm_judge?aggregate=true"
```

### /api/conversation — 대화 세션 목록

```bash
# 전체 대화 세션 목록
curl "http://localhost:8765/api/conversation"

# 특정 파일의 대화 세션 목록
curl "http://localhost:8765/api/conversation/evaluation"

# 특정 세션 상세
curl "http://localhost:8765/api/conversation/evaluation/session_001"
```

---

## 10.6 실시간 업데이트

### WebSocket — 실시간 이벤트 스트림

대시보드가 열려 있는 동안 새 태스크가 평가될 때마다 자동 업데이트를 받으려면 WebSocket을 사용한다.

```javascript
// 브라우저 콘솔에서 테스트
const ws = new WebSocket('ws://localhost:8765/ws/events');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('새 평가 이벤트:', data);
};
```

대시보드 UI는 이미 이 WebSocket을 사용하므로, `--watch` 모드로 실행하면 별도 새로고침 없이 실시간 업데이트가 된다.

### SSE — Server-Sent Events

특정 태스크의 스트리밍 평가 결과를 실시간으로 받으려면 SSE를 사용한다.

```bash
# 태스크 스트리밍 결과 실시간 수신 (file_id 기반)
curl -N "http://localhost:8765/stream/tasks/evaluation"

# 필터 기반 스트림 (accuracy_score < 0.7인 이벤트만, file_id 기반)
curl -N "http://localhost:8765/stream/filtered/evaluation"
```

---

## 10.7 데이터 내보내기

분석 결과를 팀과 공유하거나 외부 도구로 가져가야 할 때 내보내기 기능을 사용한다.

### Excel 내보내기

```bash
# Excel 파일 다운로드 (file_id 기반)
curl -o evaluation_results.xlsx "http://localhost:8765/api/export/excel/evaluation"
```

Excel 파일에는 태스크별 전체 지표가 컬럼으로 정리되어 있다. 스프레드시트 도구에서 추가 분석이 필요할 때 유용하다.

### DataFrame으로 내보내기

Python 코드 안에서 평가 결과를 DataFrame으로 변환하면 pandas를 활용한 세밀한 분석이 가능하다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
# ... 평가 실행 ...

# DataFrame으로 변환
df = eval.export_to_dataframe()
print(df.columns.tolist())
# ['task_id', 'task_type', 'accuracy_score', 'completion_score',
#  'execution_time', 'tokens_used', 'framework', 'tool_call_count',
#  'has_error', 'attempts', 'timestamp', ...]

# CSV 저장
df.to_csv("evaluation_results.csv", index=False)

# 분석 예시: task_type별 평균 accuracy
print(df.groupby("task_type")["accuracy_score"].mean())

# 분석 예시: 실패 케이스 상세
failed = df[df["completion_score"] < 0.3]
print(f"실패 케이스: {len(failed)}개")
print(failed[["task_id", "accuracy_score", "execution_time", "has_error"]])
```

---

## 📋 QA 관리자 포인트: 대시보드 5분 점검 루틴 (매일 아침)

매일 아침 대시보드를 5분만 보면 전날의 품질 상태를 파악할 수 있다. 아래 루틴을 따르면 놓치는 것이 없다.

**Step 1 (1분): 전체 통계 확인**
```bash
curl http://localhost:8765/api/stats
```
TCR이 전날보다 3% 이상 하락했는가? Accuracy가 임계값 아래로 떨어졌는가? 이상이 없으면 다음 단계.

**Step 2 (2분): 최하위 케이스 10개 확인**
```bash
curl "http://localhost:8765/api/results?sort_by=accuracy_score&sort_desc=false&limit=10"
```
정확도가 낮은 케이스들의 패턴을 확인한다. 특정 질문 유형이나 특정 프레임워크에서만 발생하는가? 공통 패턴이 보이면 더 깊이 조사한다.

**Step 3 (1분): 이상 이벤트 확인**
```bash
curl http://localhost:8765/api/anomalies
```
새로운 이상 이벤트가 있는가? 어제와 다른 패턴이 탐지되었는가?

**Step 4 (1분): 일일 비용 확인**
```bash
curl http://localhost:8765/api/cost/breakdown
```
전날 비용이 예산 내에 있는가? 특정 태스크 유형의 비용이 급증했는가?

이 4단계를 매일 실행하면 문제를 조기에 발견하고 대응할 수 있다.

---

## 이 챕터의 핵심

- **대시보드는 JSON 파일을 읽는다** — 평가 코드에서 반드시 `save_to_file()` 또는 `eval.save()`를 호출해야 데이터가 보인다
- **3가지 저장 방법** — 직접 호출(A), auto_save(B), QuickEval.save()(C) 중 상황에 맞게 선택한다. 프로덕션에서는 auto_save가 안전하다
- **API로 정밀 분석** — UI만으로 부족할 때는 `/tasks/filter` 복합 조건과 `/distributions` 분포 분석을 직접 API로 호출한다
- **5분 점검 루틴** — `/api/stats` → 최하위 케이스 → `/anomaly` → 비용 순서로 매일 아침 5분 점검 루틴을 만들면 문제를 조기에 발견한다
- **내보내기 활용** — Excel 내보내기 또는 `export_to_dataframe()`으로 팀과 분석 결과를 공유하고, pandas로 추가 분석한다
