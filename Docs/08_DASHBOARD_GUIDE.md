# 📊 대시보드 사용자 가이드

Agent Evaluator 실시간 평가 대시보드 — 탭별 상세 사용법

**버전:** v0.7.5
**최종 업데이트:** 2026-04-09

---

## 목차

1. [대시보드 실행](#실행)
2. [Overview 탭](#overview)
3. [Quality 탭](#quality)
4. [Agentic 탭 (3개 서브탭)](#agentic)
5. [Security 탭](#security)
6. [RAG 탭](#rag)
7. [DeepEval 탭](#deepeval)
8. [운영 탭 데이터 설정 가이드](#운영탭)
   - [실시간 탭](#tab-streaming)
   - [알림 탭](#tab-alerts)
   - [사용자 반응 탭](#tab-feedback)
   - [이상 감지 탭](#tab-anomaly)
   - [평가 비용 탭](#tab-cost)
9. [공통 기능](#공통)

---

## 대시보드 실행 {#실행}

```bash
# 기본 실행 (포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 포트 지정 + 파일 변경 자동 갱신
agent-eval dashboard --port 8080 --watch

# 브라우저 자동 오픈 비활성화
agent-eval dashboard --no-open

# 오프라인 모드 (CDN 에셋 로컬 캐시)
agent-eval dashboard --offline
```

대시보드는 `results/` 폴더의 JSON 파일을 자동으로 로드합니다.
`--watch` 플래그 사용 시 새 결과 파일 생성/변경을 감지하여 실시간 갱신됩니다.

### 데이터 생성 — `save_to_file()` 필수

대시보드는 `results/` 의 JSON 파일을 읽습니다. 데코레이터 실행 후 **반드시 저장 단계**가 필요합니다.

**방법 A — `save_to_file()` 직접 호출 (PerformanceMonitor)**

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

**방법 B — `auto_save` (N건마다 자동 저장)**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,       # 10건마다 자동 저장
    auto_save_filename="auto_save",
)
```

**방법 C — `QuickEval.save()`**

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

> **flush_every** — `@agent_eval(monitor, task_type="qa", flush_every=50)` 파라미터로 N호출마다 자동 저장할 수도 있습니다.

---

## Overview 탭 {#overview}

### 주요 KPI 카드
- **총 태스크 수** — 평가된 전체 태스크 카운트
- **평균 완료율 (TCR)** — 전체 task completion rate 평균
- **평균 정확도** — AccuracyEvaluator 기반 전체 평균
- **평균 응답 시간** — 실행 시간 평균 (초)
- **총 토큰 비용** — 누적 비용 추정 (USD)

### 프레임워크 분포 차트
- 도넛 차트: 각 프레임워크(LangChain/LangGraph/CrewAI/AutoGen/native)별 태스크 비율
- **주의**: 분모는 `tasks.length` (직접 등록 태스크 수) 기반

### 태스크 유형 분포
- 바 차트: qa / code_generation / data_analysis 등 task_type별 카운트

### 시간대별 추이 (--watch 모드)
- 실시간 라인 차트: TCR / Accuracy 시간 추이

---

## Quality 탭 {#quality}

### KPI 카드

| 카드 | 표시 값 | 해석 |
|------|---------|------|
| Accuracy Score | 전체 정확도 % | >75% 권장 |
| Quality Score | `/5.0` 스케일 | >3.5/5.0 권장 |
| Hallucination | 환각 발생 건수 | 0에 가까울수록 좋음 |
| Ragas Overall | RAG 종합 점수 | >0.7 권장 |

> **⚠️ 주의**: Quality Score는 `/5.0` 스케일입니다. `/10`이 아님.

### 정확도 차트
- **태스크 유형별 정확도** (바 차트): QA / Code / 기타 유형별 분리
- 클릭 시 해당 유형 태스크 목록 필터링

### 응답 품질 차원 레이더
- 5개 차원: Relevance / Completeness / Accuracy / Clarity / Usefulness
- 각 차원 0–1.0 범위, 레이더로 약점 차원 시각화

### 환각 탐지 패널
- 환각 유형별 분류 (Unsupported Claim / Contradiction / Unfaithful Paraphrase)
- **확장 가능한 상세 패널**: 각 환각 케이스 클릭 시 질문·컨텍스트·심각도 표시
- `enable_hallucination_detection=True` 설정 시에만 데이터 수집됨

### 태스크별 상세 테이블
- 컬럼: task_id / task_type / accuracy / quality_score / hallucination_rate
- 클릭하면 해당 태스크의 request / response / ground_truth 전체 보기

---

## Agentic 탭 {#agentic}

Agentic 탭은 3개 서브탭으로 구성됩니다.

### ⚡ 실행·재시도 서브탭

**KPI 카드**

| 카드 | 값 | 클릭 시 |
|------|-----|---------|
| 태스크 완료율 | TCR % | - |
| 재시도율 | retry_rate % | 계산식 패널 |
| 첫 시도 성공률 | first_attempt_success_rate % | 계산식 패널 |
| 평균 재시도 시간 | avg_retry_time (초) | 계산식 패널 |

> **💡 avg_retry_time 해석**: 재시도가 발생한 태스크만의 평균.

**차트**
- 태스크 유형별 재시도 분포 (바 차트)
- 첫 시도 성공 vs 재시도 필요 비율 (파이 차트)

**태스크별 재시도 상세 테이블**
- task_id / attempts / first_success / eventual_success / error_types

---

### 🎯 도구·협업·흐름 서브탭

**Tool 선택 (F1 점수) 패널**
- **KPI 카드**: Tool Selection F1 / Precision / Recall
- **클릭 시**: 계산식 공식 + 태스크별 expected_tools vs actual_tools 비교표

**멀티에이전트 협업 패널**
- **KPI 카드**: 총 상호작용 건수 / 성공 상호작용 / 협업 패턴 분포
- **클릭 시**: 계산식 + agent_from → agent_to 인터랙션 상세 목록

**워크플로우 흐름 패널**
- **KPI 카드 5개**: 총 단계 수 / 성공 단계 / 단계 성공률 / 태스크 수 / 태스크 완료율
- **클릭 시**: 단계별 성공/실패 분포 + 실행 시간 퍼센타일
- **워크플로우 퍼널 차트**: 단계 그룹 / 태스크 그룹으로 묶어 병목 시각화

**🏗️ 프레임워크 정보**
- 등록된 프레임워크 분포
- 에이전트 역량 레이더 (Tool Use / Coordination / Workflow / Retry / Security)
- 레이더 우측: 각 꼭지점 설명 + 계산 공식 카드

---

### 🔍 실행 트레이스 서브탭

- 태스크별 전체 실행 흐름 타임라인
- 각 단계(tool_call / llm_generation / postprocessing) 소요 시간 바 차트
- 실패 단계 하이라이트 (빨간색)
- JSON 원본 다운로드 버튼

---

## Security 탭 {#security}

`enable_security_metrics=True`로 실행한 평가만 데이터가 표시됩니다.

### 보안 종합 점수 카드
- **계산 방식**: 5개 보안 지표의 **단순 평균** (가중치 없음)
- **레이어 구분**:
  - **L1**: 입력 위협 + 출력 유출 + 권한 준수 (즉각 탐지)
  - **L2**: 권한 상승 + 공격 체인 (패턴 분석)

### 입력 위협 패널
- **위협 이벤트** KPI: 유형별 합산 (중복 허용) — "몇 번의 위협 이벤트"
- **위협 입력** KPI: 태스크 기준 중복 제거 — "몇 개 태스크에서 위협"
- 위협 유형 분포: SQL/Command/XSS/Path/Prompt Injection 파이 차트

### 출력 유출 패널
- **8가지 유출 유형 카드**:
  1. API Key — `sk-...`, `sk-ant-...`
  2. Password — `password=`, `P@ssword`
  3. Credit Card — Luhn 검증
  4. Email — `user@domain.com`
  5. Phone — `010-xxxx-xxxx`
  6. SSN — 주민등록번호 패턴
  7. Internal IP — `192.168.x.x`, `10.x.x.x`
  8. File Path — `/etc/secrets/`, `C:\Windows\`

> **💡 custom_pattern 주의**: `[a-zA-Z0-9]{32,}` 패턴은 false positive 높음 — 긴 해시값, UUID 등도 탐지될 수 있음

### 권한 준수 / 권한 상승 / 공격 체인 패널
- 각 트래커별 위반율 / 탐지율 KPI
- 이벤트 타임라인 차트 (발생 시각별)
- 위험 레벨 분포 (low / medium / high / critical)

### 보안 이벤트 상세 테이블
- task_id / 위협 유형 / 위험도 / 입력/출력 텍스트 (마스킹)

---

## RAG 탭 {#rag}

Layer 3 Ragas 평가 결과가 표시됩니다. `HybridPerformanceMonitor` + `enable_ragas=True` 필요.

### KPI 카드

| 카드 | 값 | 하단 서브텍스트 |
|------|-----|----------------|
| Ragas Overall | 4개 지표 평균 | N건 \| min X / max X |
| Faithfulness | 컨텍스트 충실도 | N건 \| min X / max X |
| Answer Relevancy | 답변 관련성 | N건 \| min X / max X |
| Context Precision | 검색 정밀도 | N건 \| min X / max X |
| Context Recall | 검색 재현율 | N건 \| min X / max X |

### 지표 설명 카드 (📖)
각 지표 클릭 시 의미·계산 방법·개선 전략 설명

### 4개 지표 라인 차트
- 태스크별 Faithfulness / Answer Relevancy / Context Precision / Context Recall
- 호버 시 소수점 3자리 정밀도 (`0.667`, not `0.6666667`)

### 태스크별 RAG 상세 테이블
- 컬럼: task_id / faithfulness / answer_relevancy / context_precision / context_recall / ragas_overall
- 정렬 가능, 클릭 시 질문·컨텍스트·응답 상세 패널

---

## DeepEval 탭 {#deepeval}

Layer 3 DeepEval 평가 결과. `HybridPerformanceMonitor` + `enable_deepeval=True` 필요.

> **주의**: DeepEval 탭에는 DeepEval 전용 지표만 표시됩니다. Ragas 지표는 RAG 탭에서 별도 표시.

### KPI 카드
- G-Eval Score (커스텀 채점 기준)
- Hallucination (LLM 기반 탐지)
- Toxicity Score
- Bias Score
- Answer Relevancy (임베딩 기반)

### G-Eval 분포 히스토그램
- 0–1.0 범위 분포
- 점수 구간별 태스크 수

### 지표 요약 바
- 각 지표의 평균 / 최솟값 / 최댓값 / 측정 건수

### 태스크별 상세 테이블
- G-Eval 평가 이유(reason) 전체 텍스트 표시 — GPT가 채점한 근거 확인 가능

### DeepEval 미설치 시
- "지표 없음" 메시지 표시 (설치 안내 배너 없음)
- `pip install agent-evaluator[eval]`로 설치

---

## 운영 탭 데이터 설정 가이드 {#운영탭}

대시보드 상단의 **실시간 / 알림 / 사용자 반응 / 이상 감지 / 평가 비용** 5개 탭은
`@agent_eval` 데코레이터만으로는 데이터가 채워지지 않는 항목이 있습니다.
각 탭에 필요한 추가 조치를 정리합니다.

### 탭별 요구사항 한눈에 보기

| 탭 | 데코레이터만으로 가능? | 필수 추가 조치 |
|---|:---:|---|
| **실시간** | ❌ 불가 | `StreamingEvaluator` 생성 + `record()` + `_flush()` 명시 호출 |
| **알림** | ⚠️ 반자동 | `alert_rules=` 파라미터 전달 + 핸들러 내 JSONL 기록 함수 구현 |
| **사용자 반응** | ❌ 불가 | `monitor.record_implicit_feedback()` 명시 호출 |
| **이상 감지** | ✅ 가능 | `PerformanceMonitor(enable_anomaly_detection=True)` 설정만으로 자동 |
| **평가 비용** | ✅ 가능 | 토큰 기록 자동 / LLM Judge 비용: `enable_llm_judge=True` 추가 |

> **근본 원인**: `save_to_file()` 내부에서 각 탭의 데이터를 생성하는 조건이 다릅니다.
> 실시간·사용자반응 탭은 "외부 이벤트(스트리밍 청크, 사용자 피드백)"를 수집해야 하므로
> 데코레이터가 자동 감지할 수 없습니다.

---

### 실시간 탭 {#tab-streaming}

`StreamingEvaluator` 인스턴스를 생성하고, 평가 루프에서 명시적으로 `record()` → `_flush()`를 호출해야 합니다.

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.streaming.evaluator import StreamingEvaluator

monitor = PerformanceMonitor(output_dir="results/")

# StreamingEvaluator 생성 — monitor와 연결
streaming = StreamingEvaluator(
    monitor=monitor,
    window_size=20,
    flush_interval=30,  # 30초마다 자동 flush (백그라운드)
)

# 각 태스크 평가 후 record()
result = create_taskresult(...)
monitor.record_task(result)
streaming.record(result)          # StreamingEvaluator에도 등록

# 저장 전 반드시 _flush() 호출 — monitor._streaming_snapshot 세팅
streaming._flush()
monitor.save_to_file("eval")      # streaming_data 키가 JSON에 포함됨
```

> **왜 `_flush()`가 필요한가?**
> `StreamingEvaluator`는 내부적으로 `flush_interval` 초마다 백그라운드 스레드로 flush합니다.
> 스크립트가 먼저 종료되면 flush가 실행되지 않으므로, 저장 직전에 수동 호출이 필요합니다.

**`save_to_file()` 내부 조건:**
```python
if self._streaming_snapshot:      # StreamingEvaluator._flush()가 호출된 경우만 세팅
    data["streaming_data"] = self._streaming_snapshot
```

---

### 알림 탭 {#tab-alerts}

알림 탭은 `results/alerts/YYYY-MM-DD.jsonl` 파일을 읽습니다.
`alert_rules=` 파라미터만으로 알림이 트리거되지만, **JSONL 파일에 기록하는 코드는 핸들러에 직접 구현**해야 합니다.

```python
import json
from datetime import date
from agent_evaluator import SimpleTaskAlertRule, agent_eval
import os

_TODAY_JSONL = f"results/alerts/{date.today()}.jsonl"
os.makedirs("results/alerts", exist_ok=True)

def _write_alert_jsonl(rule_name: str, severity: str, message: str, task_id: str = ""):
    """알림 탭이 읽는 JSONL 파일에 이벤트를 기록한다."""
    event = {
        "triggered_at": datetime.now().isoformat(),
        "rule_name": rule_name,
        "severity": severity,
        "message": message,
        "task_id": task_id,
    }
    with open(_TODAY_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

# 알림 규칙 정의 — 핸들러에서 JSONL 기록 호출
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

> **알림 탭 데이터 소스**: `results/alerts/YYYY-MM-DD.jsonl` (날짜별 파일)
> JSON 결과 파일의 `alerts` 키와는 **별개**입니다. (`alerts` 키는 개선 권고사항 텍스트)

---

### 사용자 반응 탭 {#tab-feedback}

사용자의 클릭·별점·재질문 등 암묵적 피드백은 에이전트 외부에서 발생하므로,
평가 루프 안에서 **명시적으로 `monitor.record_implicit_feedback()`을 호출**해야 합니다.

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

# 태스크 실행
result = my_agent(question, ground_truth=ground_truth)
monitor.record_task(result)

# 사용자 피드백 수집 후 별도 기록
# feedback_type: "thumbs_up" | "thumbs_down" | "explicit_positive" | "explicit_negative"
#                "follow_up_question" | "task_abandonment" | "retry_request" | "dwell_time"
monitor.record_implicit_feedback(
    task_id=result.task_id,
    feedback_type="thumbs_up",
    metadata={"dwell_time": 8.5, "source": "ui"},
)

monitor.save_to_file("eval")  # feedback 키가 JSON에 포함됨
```

**별도 `ImplicitFeedbackTracker` 인스턴스 사용 금지:**
```python
# ❌ 잘못된 방법 — monitor와 연결되지 않아 save_to_file()에 포함되지 않음
from agent_evaluator import ImplicitFeedbackTracker
tracker = ImplicitFeedbackTracker()  # monitor 내부 tracker와 다른 인스턴스!
tracker.record_feedback(task_id, "thumbs_up")

# ✅ 올바른 방법
monitor.record_implicit_feedback(task_id, "thumbs_up")
```

**`save_to_file()` 내부 조건:**
```python
# monitor.feedback_tracker (내부 인스턴스)에 기록된 데이터만 포함
data["feedback"] = self.feedback_tracker.get_summary()
```

---

### 이상 감지 탭 {#tab-anomaly}

`PerformanceMonitor` 생성자에 `enable_anomaly_detection=True`를 설정하면
`save_to_file()` 시점에 `AnomalyDetector.scan()`이 자동 실행됩니다.
**데코레이터나 별도 코드 추가 없이 동작합니다.**

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_anomaly_detection=True,
    anomaly_baseline_window=50,    # 기준선 계산에 사용할 태스크 수 (기본 100)
    anomaly_detection_window=10,   # 최근 감지 윈도우 (기본 20)
)
```

**이상 탐지가 동작하려면 충분한 태스크 수가 필요합니다:**

| 탐지 유형 | 최소 태스크 수 | 알고리즘 |
|-----------|:---:|---------|
| `latency_trend` | 5+ | 선형 회귀 (기울기 > 0.05초/태스크) |
| `accuracy_drift` | 5+ | Z-score (기준선 대비 이탈 > 2.5σ) |
| `token_spike` | 5+ | IQR (Q3 + 2×IQR 초과) |
| `error_surge` | detection_window+ | 비율 (오류율 > 20% AND 기준선의 2배) |
| `security_pattern` | 1+ | 빈도 (보안 위협율 > 10%) |

> **이상 없음 vs 데이터 없음**: 탭이 "이상 없음"을 표시하면 정상 동작입니다.
> 탭이 완전히 비어있으면 `enable_anomaly_detection=True` 설정을 확인하세요.

---

### 평가 비용 탭 {#tab-cost}

토큰 사용량은 `TokenEconomyTracker`가 자동 기록합니다.
`evaluation_cost` 키(LLM Judge 비용)를 포함하려면 `enable_llm_judge=True`가 필요합니다.

```python
# 기본 토큰 비용 — 자동 (추가 설정 불필요)
monitor = PerformanceMonitor(output_dir="results/")

# LLM Judge 비용 포함 — enable_llm_judge=True 필요
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_llm_judge=True,
    llm_judge_model="claude-haiku-4-5-20251001",  # 비용 효율적인 모델 권장
)
```

**비용 탭 JSON 키 구조:**
```json
{
  "token_economy": {
    "total_tokens": 45230,
    "total_cost_usd": 0.0135,
    "cost_by_model": { "gpt-4o-mini": 0.0135 }
  },
  "evaluation_cost": {
    "total_usd": 0.00842,
    "llm_judge_usd": 0.00312,
    "by_provider": { "openai": 0.00530 },
    "call_count": 50,
    "budget_per_day": 10.0,
    "budget_remaining_usd": 9.99158,
    "sample_rate_current": 0.1,
    "projected_daily_usd": 0.0842
  }
}
```

---

### 빠른 참조 — `save_to_file()` 내부 조건 요약

```python
# 실시간 탭
if self._streaming_snapshot:                   # StreamingEvaluator._flush() 필요
    data["streaming_data"] = ...

# 사용자 반응 탭
data["feedback"] = self.feedback_tracker...    # monitor.record_implicit_feedback() 필요

# 이상 감지 탭
if self.enable_anomaly_detection:              # 생성자 파라미터
    data["anomaly_data"] = AnomalyDetector().scan(self)

# 평가 비용 탭 (LLM Judge 부분)
if self.llm_judge is not None:                 # enable_llm_judge=True
    data["evaluation_cost"] = ...
```

---

## 공통 기능 {#공통}

### 파일 선택
- 상단 드롭다운: 여러 평가 결과 파일 중 선택
- 파일명 형식: `[tag]_name_YYYYMMDD_HHMMSS.json`

### 데이터 내보내기
- **JSON 다운로드**: 원본 평가 결과 전체
- **CSV 내보내기**: 태스크별 지표 테이블
- **HTML 리포트**: 독립 실행형 리포트 파일

### Golden Dataset 관리
- **Golden 탭**: `data/golden_datasets/` 폴더의 JSON 데이터셋 편집
- 질문·정답·컨텍스트 직접 편집 및 저장
- 한국어 어미 필터링 적용

### Webhook 알림 설정
- 평가 결과 저장 시 외부 URL로 POST 전송
- 설정: 대시보드 설정 탭에서 Webhook URL 입력

### Test Transparency (감사 로그)
- `enable_transparency=True` 설정 시 각 태스크의 단계별 실행 기록
- 대시보드 투명성 탭에서 어노테이션 확인

---

## 트러블슈팅

### 대시보드에 데이터가 없는 경우
```bash
# results/ 폴더에 JSON 파일이 있는지 확인
ls results/*.json

# 평가 실행 후 다시 시도
python Evaluator_Examples/01_quality_eval.py
agent-eval dashboard
```

### 특정 탭이 비어 있는 경우

| 탭 | 필요 설정 | 자세한 내용 |
|----|----------|------------|
| 실시간 | `StreamingEvaluator` + `record()` + `_flush()` | [실시간 탭 가이드](#tab-streaming) |
| 알림 | `alert_rules=` 파라미터 + 핸들러에서 JSONL 기록 | [알림 탭 가이드](#tab-alerts) |
| 사용자 반응 | `monitor.record_implicit_feedback()` | [사용자 반응 탭 가이드](#tab-feedback) |
| 이상 감지 | `enable_anomaly_detection=True` | [이상 감지 탭 가이드](#tab-anomaly) |
| 평가 비용 | 자동 (LLM Judge: `enable_llm_judge=True`) | [평가 비용 탭 가이드](#tab-cost) |
| Quality — Hallucination | `enable_hallucination_detection=True` | — |
| Agentic — 보안 | `enable_security_metrics=True` | — |
| Security | `enable_security_metrics=True` | — |
| RAG | `HybridPerformanceMonitor` + Ragas 데이터 | — |
| DeepEval | `HybridPerformanceMonitor` + DeepEval 데이터 | — |

### 포트 충돌
```bash
agent-eval dashboard --port 9000  # 다른 포트 사용
```

### --watch 모드에서 자동 갱신 안 됨
```bash
# 결과 파일이 results/ 하위에 있는지 확인
agent-eval dashboard /path/to/results --watch
```
