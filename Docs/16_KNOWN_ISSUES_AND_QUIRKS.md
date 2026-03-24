# ⚠️ Known Issues & Quirks

Agent Evaluator의 알려진 이슈, API 주의사항, 평가 레이어 선택 가이드

**버전:** v0.6.1
**최종 업데이트:** 2026-03-24

---

## 목차

1. [알려진 이슈 목록](#알려진-이슈)
2. [API 이름 변경 이력](#api-변경)
3. [평가 레이어 선택 매트릭스](#레이어-선택)
4. [프레임워크별 제한 사항](#프레임워크-제한)
5. [False Positive 높은 지표](#false-positive)

---

## 알려진 이슈 목록 {#알려진-이슈}

### 🔴 Issue #1: AgentCoordinationTracker.overall_score = 0.0

**증상**: `calculate_coordination_score()`의 `overall_score` 필드가 항상 0.0을 반환함.

**영향 범위**: `AgentCoordinationTracker` 직접 사용, 검증 체크 로직

**잘못된 코드 (항상 FAIL)**:
```python
coord = monitor.agent_coordination_tracker.calculate_coordination_score()
if coord.get("overall_score", 0) > 5.0:  # 절대 True가 되지 않음
    print("협업 점수 양호")
```

**올바른 대안**:
```python
coord = monitor.agent_coordination_tracker.calculate_coordination_score()
# overall_score 대신 total_interactions 카운트 사용
if coord.get("total_interactions", 0) > 10:
    print("충분한 상호작용 기록됨")
```

**대시보드 영향**: 🎯 도구·협업·흐름 탭의 "협업 점수" KPI가 0으로 표시될 수 있음.
대신 "총 상호작용 건수"를 주요 지표로 활용.

**수정 예정**: `core/agent_evaluator.py` 리팩토링 시

---

### 🔴 Issue #2: avg_retry_time 분모 버그 (v0.6.0에서 수정됨)

**v0.6.0 이전 동작 (버그)**:
```
avg_retry_time = total_retry_duration / 전체_태스크_수
→ 재시도 없는 태스크까지 포함해 평균이 희석됨
```

**v0.6.0 이후 동작 (수정)**:
```
avg_retry_time = total_retry_duration / 재시도_있는_태스크_수
→ 실제 재시도가 발생한 케이스만의 평균 시간
```

**확인 방법**: `pip show agent-evaluator` 버전이 0.6.0 이상인지 확인.

---

### 🔴 Issue #3: overall_retry_rate 복붙 버그 (v0.6.0에서 수정됨)

**v0.6.0 이전 동작 (버그)**:
```python
# retry_rate와 동일한 공식으로 계산됨 (복붙 오류)
overall_retry_rate = retry_rate  # 잘못된 복사
```

**v0.6.0 이후 동작 (수정)**:
```python
overall_retry_rate = (total_retries / total_attempts) * 100  # 올바른 공식
```

---

### 🟡 Issue #4: frameworkDist() 분모 불일치 (v0.6.1에서 수정됨)

**v0.6.1 이전 동작 (버그)**:
```javascript
// 대시보드 프레임워크 분포 차트
분모 = data.total_tasks  // PerformanceMonitor 내부 카운터
```

**v0.6.1 이후 동작 (수정)**:
```javascript
분모 = tasks.length  // 직접 등록된 태스크 수
```

**영향**: 직접 TaskResult를 등록하는 방식과 프레임워크 통합 방식 혼용 시 분포 비율이 달랐음.

---

### 🟡 Issue #5: file_path_leaks 카운트 누락 (v0.6.1에서 수정됨)

**v0.6.1 이전 동작 (버그)**:
```python
# serve/loader.py _parse_security_l1()
# OutputLeakageDetector가 file_path 유출을 탐지하지만
# 대시보드 집계에서 file_path_leaks 카운트가 누락됨
```

**v0.6.1 이후 동작 (수정)**:
```python
# contains_file_path → file_path_leaks 카운트 추가
file_path_leaks = sum(1 for r in leakage_results if r.get("contains_file_path"))
```

**영향**: 대시보드 Security 탭 출력 유출 8번째 카드 (File Path) 수치가 0으로 표시됨.

---

## API 이름 변경 이력 {#api-변경}

### PrivilegeEscalationDetector 메서드명 변경

**구버전 API (동작 안 함)**:
```python
# AttributeError: 'PrivilegeEscalationDetector' has no attribute 'detect_escalation'
monitor.privilege_tracker.detect_escalation(task_id=tid, tool_calls=tc_list)
```

**현재 올바른 API**:
```python
monitor.privilege_tracker.analyze_privilege_chain(task_id=tid, tool_calls=tc_list)
```

---

### 보안 통계 메서드명

**구버전 API (동작 안 함)**:
```python
monitor.input_sanitizer.get_security_summary()    # AttributeError
monitor.output_leakage_detector.get_leakage_summary()  # AttributeError
```

**현재 올바른 API**:
```python
monitor.input_sanitizer.get_security_stats()           # ✅
monitor.output_leakage_detector.get_leakage_stats()    # ✅
```

---

### 보안 통계 딕셔너리 키 이름

**구버전 키 (KeyError)**:
```python
stats = monitor.input_sanitizer.get_security_stats()
count = stats["threat_count"]   # KeyError
leaks = stats["leak_count"]     # KeyError
```

**현재 올바른 키**:
```python
stats = monitor.input_sanitizer.get_security_stats()
count = stats["inputs_with_threats"]   # ✅

leak_stats = monitor.output_leakage_detector.get_leakage_stats()
leaks = leak_stats["outputs_with_leakage"]  # ✅
```

---

### ResponseQualityEvaluator 스케일 변경

**v0.5.x 이전**:
```
total_score 범위: 0–10
```

**v0.5.x 이후 (현재)**:
```
total_score 범위: 0–5.0
avg_grade 범위:   0–1.0 (각 차원)
```

대시보드 Quality 탭은 `/5` 스케일로 표시.

---

### Ragas 0.4.x API 변경

**구버전 (0.3.x, 동작 안 함)**:
```python
from ragas import evaluate
from ragas.metrics import faithfulness
result = evaluate(Dataset.from_dict(data), metrics=[faithfulness])
```

**0.4.x 이후 (현재)**:
```python
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import Faithfulness

sample = SingleTurnSample(
    user_input="질문",
    response="답변",
    retrieved_contexts=["컨텍스트"],
    reference="정답"
)
dataset = EvaluationDataset(samples=[sample])
result = evaluate(dataset, metrics=[Faithfulness()])
```

---

## 평가 레이어 선택 매트릭스 {#레이어-선택}

### 상황별 권장 레이어

| 상황 | L1 | L2A | L2B | L3 | 이유 |
|------|:--:|:---:|:---:|:--:|------|
| 개발 중 빠른 피드백 | ✅ | - | - | - | 무료, ~ms, 즉시 실행 |
| 에이전트 행동 분석 | ✅ | ✅ | - | - | Tool/Retry/Workflow 추가 |
| 보안 검증 필요 | ✅ | ✅ | ✅ | - | `enable_security_metrics=True` |
| RAG 파이프라인 최적화 | ✅ | - | - | ✅(Ragas) | 검색/생성 품질 정밀 측정 |
| 콘텐츠 안전성 (Toxicity/Bias) | - | - | - | ✅(DeepEval) | LLM 판단 필수 |
| 스테이징 회귀 테스트 | ✅ | ✅ | ✅ | - | 종합 커버리지, API 비용 없음 |
| 프로덕션 전수 감사 | ✅ | ✅ | ✅ | 10% 샘플 | 비용 최소화 |
| 최고 정밀도 평가 | ✅ | ✅ | ✅ | ✅ | 모든 레이어 활성화 |

### 비용 비교

```
Layer 1/2:    $0.000 / 태스크 (API 호출 없음)
Layer 3:      $0.001–0.003 / 태스크 (GPT-4o-mini 기준)

1,000 태스크 평가 시:
  L1+L2 전수:          $0
  L3 전수:             $1–3
  L1+L2 + L3 10% 샘플: $0.1–0.3 (동등한 통계적 신뢰도)
```

### 속도 비교

```
Layer 1 (AccuracyEvaluator):      ~1–5 ms / 태스크
Layer 1 (HallucinationDetector):  ~5–20 ms / 태스크
Layer 2 (보안 지표):              ~5–15 ms / 태스크
Layer 3 (DeepEval G-Eval):        ~1,000–3,000 ms / 태스크 (API 호출)
Layer 3 (Ragas Faithfulness):     ~500–2,000 ms / 태스크 (API 호출)
```

### 레이어별 활성화 코드

```python
# Layer 1만 (기본)
monitor = PerformanceMonitor(output_dir="results/")

# Layer 1 + 환각 탐지
monitor = PerformanceMonitor(
    enable_hallucination_detection=True
)

# Layer 1 + 2A + 2B (보안)
monitor = PerformanceMonitor(
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    security_config={"allowed_tools": [...], "restricted_tools": [...]}
)

# Layer 1 + 2 + 3 (전체)
from agent_evaluator import HybridPerformanceMonitor
monitor = HybridPerformanceMonitor(
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    enable_deepeval=True,
    enable_ragas=True
)
```

---

## 프레임워크별 제한 사항 {#프레임워크-제한}

### LangChain
- **토큰 추적**: 실제 API 응답값 사용 → 가장 정확
- **제한**: `langchain>=1.0.0` 필요 (LCEL Runnable API 기반)

### LangGraph
- **토큰 추적**: `AIMessage.usage_metadata` → LangChain LLM 사용 시에만 수집 (partial)
- **노드 타이밍**: `stream()` 기반 → 실측 측정 가능
- **제한**: `langgraph>=1.0.0` 필요

### CrewAI
- **토큰 추적**: `crew.usage_metrics` — **항상 0 반환** (CrewAI SDK가 외부 미노출)
  ```python
  # 토큰 0이 표시되는 것은 CrewAI SDK 제한사항, 평가 SDK 버그 아님
  total_tokens = crew.usage_metrics.get("total_tokens", 0)  # 항상 0
  ```
- **대안**: tiktoken으로 입력 텍스트 길이 기반 추정, 또는 LangChain LLM 직접 사용
- **제한**: `crewai>=1.0.0` 필요

### AutoGen
- **토큰 추적**: tiktoken 우선, 한/영 휴리스틱 fallback → 추정값 (±10–20%)
- **async-first**: `on_messages()` / `team.run()` 기반 — 동기 래퍼 `run_sync()` 제공
- **구버전 호환**: `pyautogen>=0.3.0` (0.4+ async API)는 `generate_reply()` wrapping 불가
  → UserWarning 출력 후 수동 `monitor.record_task()` 사용 필요
- **제한**: `pyautogen>=0.3.0` 또는 `autogen-agentchat>=0.4.0`

### pydantic 버전 충돌 (crewai + autogen 동시 설치)
```
crewai:   pydantic <2.12 요구
autogen:  pydantic >=2.12 선호

→ pip이 pydantic 2.11.x로 silent downgrade
→ 기능은 동작하지만 autogen 최신 기능 일부 제한
```

해결:
```bash
pip install "agent-evaluator[crewai]"   # crewai 전용 환경
pip install "agent-evaluator[autogen]"  # autogen 전용 환경
# 동시 설치 시 pydantic 2.11.x 유지 필요
```

---

## False Positive 높은 지표 {#false-positive}

### OutputLeakageDetector — generic 패턴

```python
# 이 패턴은 false positive 높음
# [a-zA-Z0-9]{32,} → 긴 해시, UUID, base64 인코딩 문자열 모두 탐지
```

**영향이 큰 케이스**:
- SHA256 해시 값 출력
- JWT 토큰 (base64 인코딩)
- UUID 문자열 (하이픈 없는 형태)
- 긴 파일명이나 URL 파라미터

**현재 권장 대응**:
- `outputs_with_leakage` 카운트를 맹신하지 말고 실제 이벤트 상세 확인
- 대시보드 Security 탭 → 출력 유출 상세 테이블에서 텍스트 직접 확인
- 개선 예정: CLAUDE.md Technical Debt 항목에 등록됨

### HallucinationDetector — Rule-based 한계

- Rule-based 패턴 매칭: "의미상 동일하지만 표현이 다른" 케이스를 환각으로 탐지할 수 있음
- "한국" vs "대한민국", "서울대" vs "서울대학교" 등
- 정밀 평가가 필요한 경우 Layer 3 DeepEval Hallucination 병행 권장

---

## 버전별 주요 변경 요약

| 버전 | 수정된 이슈 |
|------|-----------|
| v0.6.1 | file_path_leaks 누락 수정, frameworkDist 분모 버그 수정, overall_retry_rate 복붙 버그 수정 |
| v0.6.0 | avg_retry_time 분모 버그 수정, Ragas 0.4.x API 지원, analyze_privilege_chain 메서드명 확정 |
| v0.5.x | ResponseQualityEvaluator 0-5.0 스케일 변경, evaluation_session 시그니처 수정 |
