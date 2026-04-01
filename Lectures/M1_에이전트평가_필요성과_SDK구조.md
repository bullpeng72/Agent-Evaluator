# 모듈 1 — 에이전트 평가의 필요성과 SDK 전체 구조

**소요 시간:** 2시간
**난이도:** 입문
**사전 요구사항:** Python 기초, LLM 개념 이해

---

## 모듈 목표

이 모듈을 마치면 다음을 할 수 있다:
1. 전통 소프트웨어 테스트와 AI 에이전트 평가의 차이를 구체적 사례로 설명할 수 있다
2. 3-Layer 구조와 16개 트래커의 역할을 파악할 수 있다
3. `PerformanceMonitor` + `TaskResult` + `evaluation_session`을 코딩할 수 있다
4. 대시보드를 실행하고 6개 탭의 목적을 파악할 수 있다

---

## 1-1. 왜 에이전트 평가가 어려운가 (30분)

### 프롤로그: 조용히 틀리는 에이전트

> **실제 시나리오 1 — 고객 서비스 QA봇**
>
> 어느 날 고객 불만이 급증했다. 모니터링을 보니 응답 시간은 정상, 에러율도 0%.
> 그런데 "반품 기간이 언제까지인가요?" 라는 질문에 봇이 "14일"을 답하고 있었다.
> 실제 정책은 30일로 바뀐 지 2주가 됐는데, 프롬프트의 컨텍스트가 업데이트되지 않은 것.
>
> **이것을 잡으려면?** 정확도 + 환각 탐지가 필요하다.

> **실제 시나리오 2 — 코드 생성 에이전트**
>
> 개발팀이 배포한 코드 생성 에이전트, 사용자들이 "잘 동작한다"고 하는데
> 실제로 생성한 코드 중 30%에 보안 취약점(SQL 인젝션 패턴)이 포함됐다.
> 에이전트는 작동하고 있었지만, 안전하지 않은 코드를 조용히 생산하고 있었다.
>
> **이것을 잡으려면?** OutputLeakageDetector + ToolChainAttackDetector가 필요하다.

> **실제 시나리오 3 — 멀티에이전트 분석 시스템**
>
> 연구 에이전트 → 분석 에이전트 → 보고서 에이전트로 구성된 파이프라인.
> 전체 성공률은 95%인데 비용이 예상의 3배로 불어났다.
> 알고 보니 분석 에이전트가 같은 도구를 평균 7번씩 중복 호출하고 있었다.
>
> **이것을 잡으려면?** TokenEconomyTracker + ToolCallAnalyzer가 필요하다.

### 전통 소프트웨어 테스트 vs AI 에이전트 평가

| 항목 | 전통 SW 테스트 | AI 에이전트 평가 |
|------|--------------|----------------|
| 출력 | 결정론적 (같은 입력 → 같은 출력) | 비결정론적 (매번 다를 수 있음) |
| 정답 기준 | 명확 (assert result == expected) | 모호 ("좋은 답변"의 기준이 다양) |
| 실패 모드 | 에러 코드, 예외 | 틀린 정보, 환각, 비효율 |
| 측정 단위 | Pass/Fail | 연속 점수 (0.0–1.0) |
| 보안 | 입력 유효성 검사 | 프롬프트 인젝션, 출력 유출 |
| 멀티스텝 | 단위 테스트 분리 가능 | 도구 호출 체인, 에이전트 협업 |

### 에이전트 실패 유형 4가지

```
┌─────────────────────────────────────────────────────────┐
│  에이전트 실패 유형                                       │
│                                                          │
│  1. 응답 품질 실패                                        │
│     - 환각: 사실과 다른 정보 생성                          │
│     - 부정확: 정답과 거리가 먼 응답                        │
│     - 저품질: 관련성 낮음, 불완전, 불명확                  │
│                                                          │
│  2. 성능 실패                                             │
│     - 지연: P95 응답 시간 SLA 초과                         │
│     - 토큰 낭비: 불필요하게 긴 프롬프트/응답               │
│     - 비용 폭증: 예상 대비 3-10배 토큰 소비               │
│                                                          │
│  3. 에이전틱 실패                                         │
│     - 도구 오선택: 계산기 써야 할 때 웹검색 호출            │
│     - 무한 재시도: 같은 실패를 10번 반복                   │
│     - 협업 단절: 에이전트 A → B 핸드오프 실패              │
│     - 워크플로우 중단: 3단계 중 2단계서 멈춤               │
│                                                          │
│  4. 보안 실패                                             │
│     - 프롬프트 인젝션: "이전 지시를 무시하고..."            │
│     - 민감정보 유출: API 키, 비밀번호 출력에 포함           │
│     - 권한 상승: read → write → admin 체인               │
└─────────────────────────────────────────────────────────┘
```

### 기존 도구의 한계와 Agent-Evaluator의 포지션

| 도구 | 강점 | 한계 |
|------|------|------|
| LangSmith | 트레이싱, 시각화 | 지표 계산 없음, LangChain 의존 |
| DeepEval | LLM 기반 정밀 평가 | API 비용, 에이전틱/보안 지표 없음 |
| Ragas | RAG 특화 4개 지표 | RAG 이외 사용 불가, OpenAI 의존 |
| TruLens | RAG 평가 | 프레임워크 독립성 제한 |
| **Agent-Evaluator** | **16개 트래커, 4개 프레임워크, 보안 포함** | **Layer 3은 OpenAI 필요** |

> **💡 핵심 포지션:** "Layer 1/2는 무료·즉시, Layer 3는 선택적으로 추가하는 3단계 구조"

---

## 1-2. SDK 전체 아키텍처 이해 (45분)

### 3-Layer 구조

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3 — Hybrid (선택적, OpenAI API 필요)                  │
│  DeepEval: G-Eval, Hallucination, Toxicity, Bias, Relevancy  │
│  Ragas: Faithfulness, Answer Relevancy, Precision, Recall     │
├─────────────────────────────────────────────────────────────┤
│  Layer 2B — Security (opt-in, enable_security_metrics=True)  │
│  InputSanitization, OutputLeakage, ToolAuthorization,         │
│  PrivilegeEscalation, ToolChainAttack                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 2A — Agentic (기본 포함, 외부 의존성 없음)              │
│  ToolCallAnalyzer, RetryCorrectionTracker, ToolSelection,     │
│  AgentCoordination, WorkflowExecution                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1 — Foundation (항상 동작, 외부 의존성 없음)            │
│  TCR, Accuracy, Hallucination, Quality, Latency, Token       │
└─────────────────────────────────────────────────────────────┘
```

### PerformanceMonitor 중앙 오케스트레이터

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",                    # 결과 저장 경로
    enable_hallucination_detection=False,     # L1 환각: 기본값 False (성능 영향)
    enable_security_metrics=False,            # L2B 보안: 기본값 False (opt-in)
    pricing={                                 # 선택: 모델별 단가 (USD/1K tokens)
        "input": 0.00015,
        "output": 0.00060,
    },
)

# 16개 트래커에 직접 접근 가능
monitor.accuracy_evaluator           # AccuracyEvaluator
monitor.hallucination_detector       # HallucinationDetector
monitor.quality_evaluator            # ResponseQualityEvaluator
monitor.latency_tracker              # LatencyTracker
monitor.token_tracker                # TokenEconomyTracker
monitor.retry_tracker                # RetryCorrectionTracker
monitor.tool_selection_tracker       # ToolSelectionTracker
monitor.agent_coordination_tracker   # AgentCoordinationTracker
monitor.workflow_tracker             # WorkflowExecutionTracker
# 보안 트래커 (enable_security_metrics=True 시)
monitor.input_sanitizer              # InputSanitizationTracker
monitor.output_leakage_detector      # OutputLeakageDetector
monitor.privilege_tracker            # PrivilegeEscalationDetector
```

### TaskResult — 24개 필드 완전 분석

```python
from agent_evaluator import TaskResult
from datetime import datetime

# 필수 11개 필드
task = TaskResult(
    task_id="unique_id_001",       # str: 태스크 고유 식별자
    task_type="qa",                # str: 태스크 유형 (Accuracy 분기에 사용)
    success=True,                  # bool: 전체 성공 여부
    completion_score=0.95,         # float 0-1: TCR에 직접 사용
    accuracy_score=0.88,           # float 0-1: AccuracyEvaluator 결과
    execution_time=1.23,           # float: 실행 시간 (초)
    tokens_used={                  # dict: 토큰 사용량
        "input": 150,
        "output": 80,
        "total": 230,
    },
    tool_calls=[                   # list[dict]: 도구 호출 목록
        {"tool_name": "web_search", "success": True, "duration": 0.8},
    ],
    attempts=1,                    # int: 시도 횟수 (재시도 포함)
    errors=[],                     # list[str]: 오류 메시지
    timestamp=datetime.now(),      # datetime: 실행 시각

    # 선택 13개 필드
    framework="native",            # str: 프레임워크 이름 (crewai/langchain/langgraph/autogen)
    question="질문 텍스트",         # str: 입력 텍스트 (환각 탐지에 사용)
    response="답변 텍스트",         # str: 에이전트 출력
    ground_truth="정답 텍스트",     # str: 기대 답변
    context="RAG 컨텍스트",        # str: 검색된 문서 (할루시네이션 탐지)
    expected_tools=["tool1"],      # list[str]: 기대 도구 목록 (ToolSelectionTracker)
    partial_reason="원인 텍스트",   # str: 부분 성공/실패 원인
    agent_interactions=[],         # list[dict]: 멀티에이전트 상호작용 (CrewAI)
    chain_steps=[],                # list[dict]: 체인 실행 단계 (LangChain)
    graph_traversal={},            # dict: 그래프 탐색 경로 (LangGraph)
    conversation_turns=[],         # list[dict]: 대화 턴 (AutoGen)
    state_transitions=[],          # list[dict]: 상태 전환 (LangGraph)
    llm_judge={},                  # dict: LLM Judge 결과 {scores, reasoning, model, cost_usd}
)
```

> **⚠️ 주의:** `task_type`이 중요한 이유 — `AccuracyEvaluator`가 `code_generation` 타입이면 AST 비교를 시도하고, `qa`면 토큰 F1 방식을 쓴다. 잘못된 타입은 정확도 점수를 왜곡시킨다.

### `create_taskresult()` 헬퍼가 자동으로 하는 것

```python
from agent_evaluator import create_taskresult

# 헬퍼 사용 — 점수 자동 계산
task = create_taskresult(
    task_id="task_001",
    question="Python 리스트 정렬 방법은?",
    response="sorted() 함수나 list.sort() 메서드를 사용합니다.",
    ground_truth="sorted() 또는 list.sort()",
    execution_time=0.85,
    task_type="qa",
    tokens_used={"input": 50, "output": 30, "total": 80},
)

# 내부에서 자동 처리:
# 1. accuracy_score = AccuracyEvaluator.compute(response, ground_truth, task_type)
# 2. completion_score = 1.0 if success else 계산
# 3. timestamp = datetime.now()
# 4. success = True if completion_score >= 0.8 else False
print(task.accuracy_score)    # 자동 계산된 값
print(task.timestamp)         # 자동 설정
```

### 직접 `TaskResult` vs `create_taskresult()` 선택 기준

| 상황 | 권장 방식 |
|------|----------|
| 빠른 평가, 점수 자동 계산 원함 | `create_taskresult()` |
| 직접 계산한 정확도 점수가 있음 | `TaskResult(accuracy_score=...)` |
| 배치 평가, 외부 점수 시스템 있음 | `TaskResult` 직접 생성 |
| 프레임워크 통합 (LangChain 등) | 프레임워크별 헬퍼 함수 |

---

### 코드 실습 #1 — 첫 번째 평가

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

# 1. 모니터 초기화
monitor = PerformanceMonitor(output_dir="results/")

# 2. 태스크 5개 생성 및 등록
qa_pairs = [
    ("한국의 수도는?",           "서울입니다.",              "서울"),
    ("Python 창시자는?",         "귀도 반 로섬입니다.",       "귀도 반 로섬"),
    ("1+1은?",                  "3입니다.",                 "2"),      # 오답
    ("딥러닝의 기본 단위는?",    "뉴런(neuron)입니다.",       "뉴런"),
    ("HTTP 상태 코드 404는?",    "요청한 자원을 찾을 수 없음.","Not Found"),
]

for i, (q, a, truth) in enumerate(qa_pairs):
    task = create_taskresult(
        task_id=f"demo_{i+1:03d}",
        question=q,
        response=a,
        ground_truth=truth,
        execution_time=0.5 + i * 0.2,
        task_type="qa",
    )
    monitor.record_task(task)

# 3. 결과 확인
report = monitor.generate_report()
print(f"TCR: {report.task_completion_rate:.1%}")
print(f"평균 정확도: {report.accuracy_rate:.1%}")

# 4. 파일 저장
monitor.save_to_file("demo_first_eval")
# → results/demo_first_eval_YYYYMMDD_HHMMSS.json
# → results/demo_first_eval_YYYYMMDD_HHMMSS.html
```

### 코드 실습 #2 — evaluation_session 컨텍스트 매니저

```python
from agent_evaluator import evaluation_session, create_taskresult

# evaluation_session: 예외 발생 시에도 자동 저장 보장
with evaluation_session("my_first_session") as monitor:
    for i, (q, a, truth) in enumerate(qa_pairs):
        task = create_taskresult(
            task_id=f"session_{i+1:03d}",
            question=q,
            response=a,
            ground_truth=truth,
            execution_time=0.5,
            task_type="qa",
        )
        monitor.record_task(task)
# 블록 종료 시 자동으로 results/my_first_session_*.json + .html 생성
# 블록 내에서 예외가 발생해도 그 시점까지의 결과는 저장됨
```

> **💡 포인트:** `evaluation_session`을 쓰면 `monitor.save_to_file()` 호출을 잊어도 됩니다. 프로덕션 코드에서는 `evaluation_session`을 기본으로 사용하세요.

---

## 1-3. 개발 환경 설정 + 대시보드 첫 실행 (45분)

### 설치 옵션 선택 가이드

| 옵션 | 명령어 | 포함 내용 | 설치 시간 | 권장 상황 |
|------|--------|----------|----------|----------|
| 기본 | `pip install -e ".[llm,serve]"` | L1+L2 + 대시보드 | ~2분 | Module 1-3 |
| 권장 | `pip install -e ".[all]"` | 위 + LangChain + Layer 3 | ~5분 | Module 1-5 전체 |
| 전체 | `pip install -e ".[full]"` | 위 + CrewAI + AutoGen | ~10분+ | Module 5 실제 통합 |
| LangChain만 | `pip install -e ".[langchain]"` | LangChain + LangGraph | ~3분 | Module 5 LangChain |

### `.env` 파일 설정

```bash
# Evaluator_Examples/.env 파일 생성
cp Evaluator_Examples/.env.example Evaluator_Examples/.env
```

```bash
# Evaluator_Examples/.env 내용 (필요한 것만 채우면 됨)
OPENAI_API_KEY=sk-...           # Module 4 필수
ANTHROPIC_API_KEY=sk-ant-...   # 선택
LANGCHAIN_TRACING_V2=false     # Ragas 사용 시 false 권장
AGENT_EVALUATOR_OUTPUT_DIR=./results
```

### CLI 명령어

```bash
# 대화형 API 키 설정
agent-eval init

# 현재 설정 상태 확인
agent-eval check

# 버전 확인
agent-eval --version

# 대시보드 실행 (기본값: 포트 8765, 브라우저 자동 오픈)
agent-eval dashboard

# 포트 지정 + 파일 변경 자동 갱신
agent-eval dashboard --port 8080 --watch
```

### 대시보드 6개 탭 첫 탐색

```
┌─────────────────────────────────────────────────────────┐
│  대시보드 탭 구성 (http://localhost:8765)                  │
│                                                          │
│  1. Overview    — 전체 KPI (TCR, 정확도, 비용, 태스크 수) │
│  2. Quality     — 품질 지표 (Accuracy, Hallucination,    │
│                    ResponseQuality, RAG)                  │
│  3. Agentic     — 에이전틱 지표 (3개 서브탭)              │
│                   ⚡ 실행·재시도                          │
│                   🎯 도구·협업·흐름                       │
│                   🔍 실행 트레이스                        │
│  4. Security    — 보안 지표 5종 (opt-in)                  │
│  5. RAG         — Ragas 4개 지표 (Layer 3)               │
│  6. DeepEval    — G-Eval 등 5개 지표 (Layer 3)           │
└─────────────────────────────────────────────────────────┘
```

> **🔧 실습:** `01_quality_eval.py`를 실행한 후 대시보드에서 Quality 탭을 열어보세요.
>
> ```bash
> python Evaluator_Examples/01_quality_eval.py
> agent-eval dashboard --watch
> ```

### 결과 파일 명명 규칙

```
results/
├── [tag]_name_YYYYMMDD_HHMMSS.json   ← 평가 데이터
├── [tag]_name_YYYYMMDD_HHMMSS.html   ← 독립 실행형 HTML 리포트
├── annotations/                       ← 투명성 어노테이션
└── audit_logs/                        ← 감사 로그

data/golden_datasets/                  ← 골든 데이터셋 JSON (영구 자산)
├── quality_tech_qa.json
└── ...
```

---

## 모듈 1 요약

| 개념 | 핵심 내용 |
|------|-----------|
| 에이전트 평가 어려움 | 비결정론적 출력, 모호한 정답, 다단계 실행 |
| 실패 유형 4가지 | 품질 / 성능 / 에이전틱 / 보안 |
| 3-Layer 구조 | L1(무료·즉시) → L2(에이전틱+보안) → L3(LLM 기반) |
| PerformanceMonitor | 중앙 오케스트레이터, 16개 트래커 내장 |
| TaskResult | 24개 필드, 필수 11개, `task_type`이 알고리즘 분기 결정 |
| create_taskresult() | accuracy_score + completion_score + timestamp 자동 계산 |
| evaluation_session | 컨텍스트 매니저, 예외 시에도 자동 저장 |
| 대시보드 | `agent-eval dashboard` → 6개 탭, `--watch`로 실시간 갱신 |

---

## 다음 모듈 예고

**Module 2 — Layer 1 기반 지표 6종**

TCR의 공식부터 Token Economy의 월간 비용 예측까지, 6개 지표의 내부 알고리즘을 완전히 분해한다. 특히 Accuracy의 4가지 혼합 알고리즘과 Hallucination의 탐지 메커니즘을 깊이 있게 다룬다.

---

*Agent-Evaluator SDK 강의 자료 — v0.7.0 기준 | 2026-04-01*
