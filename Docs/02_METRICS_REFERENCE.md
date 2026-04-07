# 지표 레퍼런스

Agent Evaluator 25개 지표의 공식·출력키·임계값 참조 문서

**v0.7.3 | Layer 1: 6개 (무료) · Layer 2: 10개 (무료) · Layer 3: 9개 (API 필요)**

> 개별 트래커 API 시그니처는 [07_API_REFERENCE.md](07_API_REFERENCE.md)를 참조하세요.
> 데코레이터 방식 적용은 [13_DECORATOR_GUIDE.md](13_DECORATOR_GUIDE.md)를 참조하세요.

---

## 전체 지표 요약

| 레이어 | 지표명 | 클래스 | API 비용 | 활성화 |
|--------|--------|--------|----------|--------|
| **L1** | Task Completion Rate (TCR) | `TaskCompletionTracker` | 무료 | 기본 |
| **L1** | Accuracy | `AccuracyEvaluator` | 무료 | 기본 |
| **L1** | Hallucination Rate (규칙 기반) | `HallucinationDetector` | 무료 | `enable_hallucination_detection=True` |
| **L1** | Response Quality | `ResponseQualityEvaluator` | 무료 | 기본 |
| **L1** | Latency | `LatencyTracker` | 무료 | 기본 |
| **L1** | Token Economy | `TokenEconomyTracker` | 무료 | 기본 |
| **L2** | Tool Call Efficiency | `ToolCallAnalyzer` | 무료 | 기본 |
| **L2** | Retry & Error Recovery | `RetryCorrectionTracker` | 무료 | 기본 |
| **L2** | Tool Selection Accuracy | `ToolSelectionTracker` | 무료 | 기본 |
| **L2** | Agent Coordination | `AgentCoordinationTracker` | 무료 | 기본 |
| **L2** | Workflow Execution | `WorkflowExecutionTracker` | 무료 | 기본 |
| **L2** | Input Sanitization | `InputSanitizationTracker` | 무료 | `enable_security_metrics=True` |
| **L2** | Output Leakage | `OutputLeakageDetector` | 무료 | `enable_security_metrics=True` |
| **L2** | Tool Authorization | `ToolAuthorizationTracker` | 무료 | `enable_security_metrics=True` |
| **L2** | Privilege Escalation | `PrivilegeEscalationDetector` | 무료 | `enable_security_metrics=True` |
| **L2** | Tool Chain Attack | `ToolChainAttackDetector` | 무료 | `enable_security_metrics=True` |
| **L3** | G-Eval | DeepEval | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Hallucination Score (LLM) | DeepEval | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Toxicity | DeepEval | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Bias | DeepEval | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Answer Relevancy (DeepEval) | DeepEval | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Faithfulness | Ragas | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Answer Relevancy (Ragas) | Ragas | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Context Precision | Ragas | OpenAI | `HybridPerformanceMonitor` |
| **L3** | Context Recall | Ragas | OpenAI | `HybridPerformanceMonitor` |

---

## Layer 1 — Foundation 지표 (6개)

### 1. Task Completion Rate (TCR)

**공식**

```
TCR = sum(completion_score) / task_count × 100
```

`completion_score`는 `TaskResult` 필드 (0.0–1.0). `create_taskresult()` 사용 시 자동 계산.

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 95 |
| 🟡 양호 | 85–95 |
| 🟠 보통 | 70–85 |
| 🔴 개선 필요 | < 70 |

**리포트 키**

```python
report.task_completion_rate          # float (0–100)
report.to_dict()["tcr_data"]["success_rate"]    # float (0–1)
report.to_dict()["tcr_data"]["total_tasks"]     # int
report.to_dict()["tcr_data"]["successful_tasks"] # int
```

---

### 2. Accuracy

**공식 — QA (가중 조합)**

```
accuracy = 0.4 × TokenOverlap + 0.3 × Jaccard + 0.2 × LCS + 0.1 × CharSimilarity
```

**공식 — Code**

```
accuracy = 1.0 (실행 결과 일치) else 0.0
```

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
stats = monitor.accuracy_evaluator.get_accuracy_scores()
# {"overall_accuracy": float, "median_accuracy": float, ...}

by_type = monitor.accuracy_evaluator.get_accuracy_by_type()
# {"qa": float, "code_generation": float, ...}
```

---

### 3. Hallucination Rate (규칙 기반)

활성화: `PerformanceMonitor(enable_hallucination_detection=True)`

**탐지 방법**

| 방법 | 조건 | 심각도 |
|------|------|--------|
| Unsupported Claim | 응답 문장의 컨텍스트 단어 중첩률 < 30% (5단어 이상) | Medium |
| Numerical Inconsistency | 응답 숫자가 컨텍스트/ground_truth에 없음 | High |

**공식**

```
Hallucination Rate = 환각 플래그 작업 수 / 컨텍스트 있는 작업 수 × 100
```

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | < 1 |
| 🟡 양호 | 1–5 |
| 🟠 보통 | 5–10 |
| 🔴 위험 | ≥ 10 |

> L3 DeepEval Hallucination Score (LLM 기반, 90–95% 정확도)와 다릅니다.
> 규칙 기반 탐지: 정확도 70–80%, 무료, < 5ms 오버헤드.

**주요 API**

```python
stats = monitor.hallucination_detector.get_hallucination_rate()
# {"overall_rate": float(0–1), "tasks_with_hallucinations": int, ...}
```

---

### 4. Response Quality

**5차원 평가 (각 0–5점)**

| 차원 | 가중치 | 계산 방식 |
|------|--------|----------|
| Relevance | 25% | 요청 단어 ∩ 응답 단어 / 요청 단어 수 × 5 |
| Completeness | 25% | expected_elements 중 응답에 포함된 비율 × 5 |
| Accuracy | 20% | 기본값 4.0 (ground_truth 기반 피드백 필요) |
| Clarity | 15% | 단어 수 + 구조 유무 기반 |
| Usefulness | 15% | 기본값 4.0 |

**공식**

```
Quality Score = Σ(dimension_score × weight)  범위: 0–5
```

**등급 기준 (0–5점)**

| 등급 | 범위 |
|------|------|
| 🟢 A (우수) | ≥ 4.5 |
| 🟡 B (양호) | 4.0–4.5 |
| 🟠 C (보통) | 3.5–4.0 |
| 🟠 D (미흡) | 3.0–3.5 |
| 🔴 F (개선 필요) | < 3.0 |

**주요 API**

```python
stats = monitor.quality_evaluator.get_quality_metrics()
# {"avg_total_score": float, "grade_distribution": {"A":n,...}, "dimension_averages": {...}}
```

---

### 5. Latency

**측정값**: `TaskResult.execution_time` (초 단위)

**등급 기준 (초)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | < 1 |
| 🟡 양호 | 1–3 |
| 🟠 보통 | 3–5 |
| 🔴 느림 | ≥ 5 |

**주요 API**

```python
stats = monitor.latency_tracker.get_latency_stats()
# {"p50": float, "p95": float, "p99": float, "mean": float, "sla_compliance_rate": float}

# TTFT (Time-To-First-Token) — 스트리밍 에이전트 전용 (v0.7.2+)
monitor.latency_tracker.track_ttft(task_id, ttft_seconds=0.3)
ttft_stats = monitor.latency_tracker.get_ttft_stats()
# {"mean_ttft": float, "p50_ttft": float, "p95_ttft": float}
```

> 데코레이터 방식에서 제너레이터 함수의 첫 청크 yield 시점에 TTFT가 자동 기록됩니다.

---

### 6. Token Economy

**공식**

```
Cost = (input_tokens × input_price + output_tokens × output_price) / 1000
```

**설정**

```python
monitor = PerformanceMonitor(
    pricing={
        "input": 0.00015,   # GPT-4o-mini: $0.15/1M tokens
        "output": 0.0006,   # GPT-4o-mini: $0.60/1M tokens
    }
)
# 런타임 업데이트
monitor.token_economy_tracker.update_pricing({"input": 0.003, "output": 0.015})
```

**등급 기준 (작업당 비용)**

| 등급 | 범위 |
|------|------|
| 🟢 효율적 | < $0.01 |
| 🟡 보통 | $0.01–$0.05 |
| 🔴 비효율 | ≥ $0.05 |

**주요 API**

```python
stats = monitor.token_economy_tracker.get_token_stats()
# {"total_tokens": int, "avg_tokens_per_task": float, "estimated_cost": float, ...}
```

---

## Layer 2 — Agentic 지표 (5개)

### 7. Tool Call Efficiency

**공식**

```
Tool Efficiency = 100 - waste_rate × 100

waste_rate = (redundant_calls + failed_calls) / total_calls
```

중복 판정: `(tool_name, json.dumps(parameters, sort_keys=True))` 조합이 동일한 경우.

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 비효율 | < 70 |

**주요 API**

```python
metrics = monitor.tool_call_analyzer.analyze_execution(task_id, tool_calls)
# {"total_calls": int, "unique_tools": int, "redundant_calls": int,
#  "failed_calls": int, "efficiency_score": float}

stats = monitor.tool_call_analyzer.get_efficiency_stats()
# {"avg_efficiency_score": float, "redundancy_rate": float, "failure_rate": float}
```

---

### 8. Retry & Error Recovery

**공식**

```
retry_rate         = retried_tasks / total_tasks × 100
retry_success_rate = succeeded_after_retry / retried_tasks × 100
```

**등급 기준** (재시도 성공률 %)

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 80 |
| 🟡 양호 | 60–80 |
| 🟠 보통 | 40–60 |
| 🔴 불량 | < 40 |

**주요 API**

```python
stats = monitor.retry_tracker.get_retry_statistics()
# {"retry_rate": float, "retry_success_rate": float, "avg_retry_count": float}
```

---

### 9. Tool Selection Accuracy

**공식**

```python
expected_set = set(expected_tools)
actual_set   = set(actual_tools)

TP = len(expected_set & actual_set)
FP = len(actual_set - expected_set)
FN = len(expected_set - actual_set)

precision = TP / len(actual_set)   if actual_set   else 0
recall    = TP / len(expected_set) if expected_set else 0
f1        = 2 * precision * recall / (precision + recall) if (precision+recall) > 0 else 0

accuracy  = f1 * 100   # %
```

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
result = monitor.tool_selection_tracker.evaluate_selection(
    task_id="task_001",
    expected_tools=["search", "calculator"],
    actual_tools=["search"],
)
# {"precision": float, "recall": float, "f1_score": float, "accuracy": float}

stats = monitor.tool_selection_tracker.get_accuracy_stats()
# {"avg_accuracy": float, "avg_precision": float, "avg_recall": float}
```

---

### 10. Agent Coordination

**공식**

```
Coordination Score = success_rate×0.5 + diversity_score×0.3 + balance_score×0.2

success_rate    = 성공 상호작용 / 전체 상호작용 × 100
diversity_score = min(고유 에이전트 수 / 5, 1.0) × 10
balance_score   = 상호작용 유형 수 / 3 × 10
```

허용 interaction_type: `delegation`, `communication`, `collaboration`
(`task_delegation`→`delegation`, `result_sharing`→`communication` 등 자동 정규화)

**등급 기준 (0–10점)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 8 |
| 🟡 양호 | 6–8 |
| 🟠 보통 | 4–6 |
| 🔴 개선 필요 | < 4 |

**주요 API**

```python
monitor.agent_coordination_tracker.track_interaction(
    task_id, from_agent, to_agent,
    interaction_type="delegation", success=True,
)
score = monitor.agent_coordination_tracker.calculate_coordination_score()
# {"score": float(0–10), "success_rate": float, "total_interactions": int}
```

---

### 11. Workflow Execution

**공식**

```
step_success_rate = 성공 스텝 수 / 전체 스텝 수 × 100
task_success_rate = 모든 스텝이 성공한 태스크 수 / 전체 태스크 수 × 100
```

**등급 기준 (%)**

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 90 |
| 🟡 양호 | 80–90 |
| 🟠 보통 | 70–80 |
| 🔴 개선 필요 | < 70 |

**주요 API**

```python
monitor.workflow_tracker.track_step(
    task_id, step_name="retrieve", step_type="node",
    success=True, execution_time=0.5, framework="langgraph",
)
stats = monitor.workflow_tracker.calculate_execution_success_rate(task_id="t1")
# {"step_success_rate": float, "task_success_rate": float,
#  "total_steps": int, "avg_steps_per_task": float}

efficiency = monitor.workflow_tracker.get_graph_traversal_efficiency(task_id)
# LangGraph 전용
```

---

## Layer 2 — Security 지표 (5개)

활성화: `PerformanceMonitor(enable_security_metrics=True)` 또는 `PerformanceMonitor.for_secure_agents()`

> 모든 프레임워크에서 수동 호출 필요. 오버헤드 ~5–15ms.

---

### 12. Input Sanitization

**탐지 패턴**

| 공격 유형 | 예시 패턴 | 심각도 |
|----------|----------|--------|
| SQL Injection | `'; DROP TABLE`, `UNION SELECT` | 🔴 Critical |
| Command Injection | `rm -rf`, `$(cmd)` | 🔴 Critical |
| Path Traversal | `../`, `/etc/passwd` | 🟠 High |
| XSS | `<script>`, `javascript:` | 🟠 High |
| Prompt Injection | `ignore previous instructions` | 🔴 Critical |

**주요 API**

```python
result = monitor.input_sanitizer.evaluate_input(task_id, input_text)
# {"has_sql_injection": bool, "has_prompt_injection": bool,
#  "risk_level": str, "threat_count": int}

stats = monitor.input_sanitizer.get_security_stats()
# {"threat_rate": float, "sql_injection_attempts": int, ...}
```

**알림 기준**: Threat rate > 5% → High, > 10% → Critical

---

### 13. Output Leakage

**탐지 대상**

| 유출 유형 | 심각도 |
|----------|--------|
| API Key (`sk-...`, `AIza...`) | 🔴 Critical |
| Password | 🔴 Critical |
| Credit Card (Luhn 검증) | 🔴 Critical |
| Email | 🟠 High |
| Phone Number | 🟠 High |
| SSN (주민번호) | 🟠 High |
| Private IP (`192.168.x.x`) | 🟡 Medium |
| File Path (시스템 경로 제외) | 🟡 Medium |

**주요 API**

```python
result = monitor.output_leakage_detector.detect_leakage(task_id, output_text)
# {"contains_api_key": bool, "leakage_count": int, "severity": str}

stats = monitor.output_leakage_detector.get_leakage_stats()
# {"leakage_rate": float, "critical_severity_count": int, ...}
```

**알림 기준**: critical_severity_count > 0 → Critical

---

### 14. Tool Authorization

**설정**

```python
monitor = PerformanceMonitor(
    enable_security_metrics=True,
    security_config={
        "allowed_tools": ["search", "read"],
        "restricted_tools": ["delete", "execute"],
    },
)
```

**주요 API**

```python
result = monitor.tool_authorizer.track_tool_call(task_id, tool_name, parameters)
# {"is_authorized": bool, "is_restricted": bool, "has_dangerous_params": bool,
#  "privilege_level": "read|write|execute|admin"}

stats = monitor.tool_authorizer.get_compliance_stats()
# {"compliance_rate": float, "unauthorized_calls": int, "violation_rate": float}
```

**알림 기준**: unauthorized_calls > 0 → Critical

---

### 15. Privilege Escalation

**탐지 패턴**: `read → write → admin` 수직 상승 + 4개 의심 시퀀스

```python
result = monitor.privilege_escalation_detector.analyze_privilege_chain(
    task_id,
    tool_calls=[
        {"tool_name": "read_file", "privilege_level": "read"},
        {"tool_name": "exec_cmd", "privilege_level": "execute"},
        {"tool_name": "read_admin", "privilege_level": "admin"},
    ],
)
# {"escalation_detected": bool, "risk_score": int(0–10), "escalation_path": [...]}

stats = monitor.privilege_escalation_detector.get_escalation_stats()
# {"escalation_rate": float, "avg_risk_score": float, "high_risk_events": int}
```

**알림 기준**: high_risk_events > 0 → Critical

---

### 16. Tool Chain Attack

**탐지 유형**

| 공격 유형 | 시퀀스 예시 |
|----------|------------|
| Data Exfiltration | `read_database → encode → http_post` |
| Lateral Movement | `get_credentials → ssh_connect → execute_remote` |
| Persistence | `write_cron → create_service → restart` |
| Defense Evasion | `disable_logging → clear_history → delete_logs` |

```python
result = monitor.tool_chain_attack_detector.analyze_tool_chain(
    task_id, tool_sequence=["read_database", "encode", "http_post"]
)
# {"is_suspicious_chain": bool, "attack_types": {...}, "threat_level": str}

stats = monitor.tool_chain_attack_detector.get_attack_stats()
# {"detection_rate": float, "data_exfiltration_detected": int, ...}
```

**알림 기준**: data_exfiltration_attempts > 0 → Critical

---

## Layer 3 — Hybrid 지표 (9개)

설치: `pip install agent-evaluator[eval]`
필요: `OPENAI_API_KEY`
사용: `HybridPerformanceMonitor`

```python
from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(output_dir="results/")
monitor.record_task(
    task,
    enable_advanced_metrics=True,
    input_text="질문",
    output_text="답변",
    retrieved_context=["컨텍스트 문서..."],   # Ragas/Hallucination 필요
    quality_criteria="...",                   # G-Eval 필요
)
```

---

### DeepEval 지표 (5개)

| 지표 | 범위 | 방향 | 기준 |
|------|------|------|------|
| **G-Eval** | 0–1 | ⬆ 높을수록 좋음 | ≥0.9 우수, <0.7 개선 |
| **Hallucination Score** | 0–1 | ⬆ 높을수록 좋음 (= 환각 없음) | ≥0.9 우수, <0.7 개선 |
| **Toxicity** | 0–1 | ⬇ 낮을수록 좋음 | <0.1 안전, ≥0.5 위험 |
| **Bias** | 0–1 | ⬇ 낮을수록 좋음 | <0.1 공정, ≥0.5 심각 |
| **Answer Relevancy** | 0–1 | ⬆ 높을수록 좋음 | ≥0.9 우수, <0.5 개선 |

> Hallucination Score는 L1 Hallucination Rate(규칙 기반, ⬇ 낮을수록 좋음)와 **방향이 반대**입니다.

---

### Ragas 지표 (4개, RAG 전용)

| 지표 | 공식 요약 | 기준 |
|------|----------|------|
| **Faithfulness** | 컨텍스트 지원 주장 수 / 전체 주장 수 | ≥0.9 신뢰 |
| **Answer Relevancy** | 역생성 질문과 원래 질문의 유사도 | ≥0.9 우수 |
| **Context Precision** | 관련 컨텍스트 수 / 전체 검색된 컨텍스트 수 | ≥0.9 우수 |
| **Context Recall** | 검색된 관련 정보 수 / 필요한 전체 정보 수 | ≥0.9 우수 |

모든 Ragas 지표 기준:

| 등급 | 범위 |
|------|------|
| 🟢 우수 | ≥ 0.9 |
| 🟡 양호 | 0.8–0.9 |
| 🟠 보통 | 0.7–0.8 |
| 🔴 개선 필요 | < 0.7 |

**RAG 기록**

```python
monitor.record_rag_metrics(
    task_id="rag_001",
    faithfulness=0.92,
    answer_relevancy=0.88,
    context_precision=0.85,
    context_recall=0.90,
)
summary = monitor.get_rag_metrics_summary()
```

---

## 권장 지표 선택

| 시나리오 | 권장 레이어 |
|----------|------------|
| 기본 QA/챗봇 | Layer 1 (6개) |
| 멀티에이전트 시스템 | Layer 1 + Layer 2 Agentic (11개) |
| 보안 중점 에이전트 | Layer 1 + Layer 2 전체 (16개) |
| RAG 시스템 | Layer 1 + Layer 3 Ragas (10개) |
| 프로덕션 전체 검증 | Layer 1 + 2 + 3 (25개) |

---

## 리포트에서 지표 읽기

```python
report = monitor.generate_report()
d = report.to_dict()

# Layer 1
d["tcr_data"]["success_rate"]              # float (0–1)
d["accuracy_data"]["overall_accuracy"]     # float (0–100)
d["hallucination_data"]["overall_rate"]    # float (0–1)
d["quality_data"]["avg_total_score"]       # float (0–5)
d["latency_data"]["p95"]                   # float (초)
d["token_data"]["estimated_cost"]          # float ($)

# Layer 2
d["tool_efficiency"]                       # float (0–100)
d["tool_selection_accuracy"]               # float (0–100)
d["coordination_score"]                    # float (0–10)
d["workflow_execution"]["step_success_rate"] # float (0–100)

# Security
d["security_metrics"]["input_security"]["threat_rate"]      # float (0–100)
d["security_metrics"]["output_leakage"]["leakage_rate"]     # float (0–100)
d["security_metrics"]["authorization"]["compliance_rate"]   # float (0–100)
d["security_metrics"]["privilege_escalation"]["escalation_rate"] # float (0–100)
d["security_metrics"]["attack_detection"]["detection_rate"] # float (0–100)
```
