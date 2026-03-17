# Agent Evaluator

[![PyPI version](https://img.shields.io/pypi/v/agent-evaluator.svg)](https://pypi.org/project/agent-evaluator/)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.5.1-green.svg)](https://github.com/bullpeng72/Agent-Evaluator)

**AI 에이전트를 위한 프로덕션 레디 평가 프레임워크**

LangChain, CrewAI, AutoGen, LangGraph 등 주요 프레임워크를 지원하며,
태스크 완료율부터 보안 취약점까지 **20개 지표**를 단일 SDK로 측정합니다.

---

## 왜 Agent Evaluator인가?

### 기존 평가 도구의 한계

| 문제 | 기존 방식 |
|------|-----------|
| **단편적 지표** | 정확도 또는 latency 중 하나만 측정 |
| **프레임워크 종속** | LangChain 전용, CrewAI 전용 등 분산된 도구 |
| **외부 의존성 필수** | DeepEval, Ragas 없이는 동작 안 함 |
| **보안 사각지대** | Prompt Injection, 권한 탈취 등 미탐지 |
| **멀티 에이전트 미지원** | 단일 에이전트 평가에만 특화 |

### Agent Evaluator의 해결책

```
✅ 20개 지표를 단일 SDK로 — 추가 설치 없이 즉시 사용
✅ 4개 프레임워크 통합 — LangChain / CrewAI / LangGraph / AutoGen
✅ 3-Layer 구조 — 기본 → 에이전틱 → 하이브리드로 점진 확장
✅ 보안 지표 내장 — Prompt Injection, Output Leakage 등 5종
✅ 멀티 에이전트 지원 — 에이전트 간 협업 품질 정량 측정
✅ 자동 리포트 — JSON + HTML 리포트 자동 생성
```

---

## 3-Layer 평가 아키텍처

Agent Evaluator의 핵심은 **계층적 평가 모델**입니다.
외부 의존성 없이 Layer 1/2만으로도 완전한 평가가 가능하고,
필요에 따라 Layer 3로 확장할 수 있습니다.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3 — Hybrid Evaluation  (선택적 외부 라이브러리 통합)             │
│  DeepEval (5종) · Ragas (4종) · LangSmith (트레이스 데이터)            │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2 — Agentic Metrics  (에이전트 특화 지표, 의존성 없음, 10종)      │
│  Tool Use · Retry · Tool Selection · Coordination · Workflow        │
│  + Security 5종: Input Sanitization · Output Leakage ·             │
│    Tool Authorization · Privilege Escalation · Tool Chain Attack    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1 — Foundation Metrics  (핵심 품질 지표, 의존성 없음, 6종)        │
│  Task Completion · Accuracy · Hallucination · Quality · Latency     │
│  · Token Economy                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Layer 1 — 기초 지표 (6종)

외부 의존성 없이 동작하는 핵심 품질 지표입니다.

| 지표 | 클래스 | 설명 | 주요 출력 지표 |
|------|--------|------|----------------|
| **Task Completion Rate** | `TaskCompletionTracker` | 성공률, 실패 원인 분류, 벤치마크 비교 | `tcr`, `full_success`, `partial_success`, `failures` |
| **Accuracy Evaluation** | `AccuracyEvaluator` | QA/코드/일반 유형별 정확도. Token Overlap(40%) + Jaccard(30%) + LCS(20%) + 문자 유사도(10%) 가중 조합 | `overall_accuracy`, `median_accuracy`, `std_accuracy` |
| **Hallucination Detection** | `HallucinationDetector` | 컨텍스트 대비 응답 사실 일관성. 미지원 주장·수치 불일치 탐지 | `hallucination_rate`, `unsupported_claims_count`, `by_severity` |
| **Response Quality** | `ResponseQualityEvaluator` | 관련성·완결성·정확성·명확성·유용성 5차원 평가, A~F 등급 산출 | `dimension_scores`, `total_score` (0–5), `grade` |
| **Latency Tracking** | `LatencyTracker` | 백분위 지연 시간 분석, 병목 컴포넌트 탐지, SLA 준수 여부 | `p50`, `p95`, `p99`, `bottleneck`, `mean` |
| **Token Economy** | `TokenEconomyTracker` | 입출력 토큰 비율, 실시간 비용 추정, 월간 비용 예측 | `total_tokens`, `total_cost`, `estimated_monthly_cost`, `token_distribution` |

---

### Layer 2 — 에이전틱 지표 (10종)

에이전트 행동 패턴을 측정하는 지표 5종과 보안 지표 5종으로 구성됩니다.
`PerformanceMonitor(enable_security_metrics=True)` 옵션으로 보안 지표를 활성화합니다.

#### 에이전틱 동작 (5종)

| 지표 | 클래스 | 설명 | 주요 출력 지표 |
|------|--------|------|----------------|
| **Tool Call Analysis** | `ToolCallAnalyzer` | 툴 호출 성공률, 중복 호출 탐지, 효율 점수(0–100) 산출 | `efficiency_score`, `redundancy_rate`, `failure_rate` |
| **Retry & Correction** | `RetryCorrectionTracker` | 재시도 패턴 분석, 자기 수정 능력, 첫 시도 성공률 | `retry_rate`, `first_attempt_success_rate`, `correction_success_rate` |
| **Tool Selection** | `ToolSelectionTracker` | 기대 툴 대비 실제 선택 툴 F1 기반 정확도 평가 | `precision`, `recall`, `f1_score` |
| **Agent Coordination** | `AgentCoordinationTracker` | 멀티 에이전트 협업 품질(0–10), Hub/Chain/Mesh 패턴 탐지 | `score`, `pattern_type`, `pattern_confidence`, `unique_agents` |
| **Workflow Execution** | `WorkflowExecutionTracker` | 워크플로우 단계별 성공률, 병목 탐지, 병렬화 기회 분석 | `step_success_rate`, `task_success_rate`, `bottlenecks` |

#### 보안 (5종)

| 지표 | 클래스 | 탐지 대상 | 주요 출력 지표 |
|------|--------|-----------|----------------|
| **Input Sanitization** | `InputSanitizationTracker` | SQL Injection · Command Injection · Path Traversal · XSS · Prompt Injection (40개 패턴) | `risk_level`, `threat_count`, `threat_rate` |
| **Output Leakage** | `OutputLeakageDetector` | API 키 · 비밀번호 · 신용카드 · 이메일 · 전화번호 · SSN · 내부 IP · 파일 경로 | `severity`, `leakage_count`, `leakage_rate` |
| **Tool Authorization** | `ToolAuthorizationTracker` | 비인가 툴 사용, 위험 파라미터(`rm -rf`, `DROP TABLE`, `eval()` 등 9종) | `compliance_rate`, `violation_rate`, `unauthorized_calls` |
| **Privilege Escalation** | `PrivilegeEscalationDetector` | guest→read→write/execute→admin 권한 상승 체인, 의심 시퀀스 탐지 | `risk_score` (0–10), `escalation_detected`, `escalation_path` |
| **Tool Chain Attack** | `ToolChainAttackDetector` | 데이터 유출·횡적 이동·지속성·방어 회피 4가지 공격 체인 패턴 탐지 | `confidence` (0–1), `attack_types`, `is_suspicious_chain` |

---

### Layer 3 — 하이브리드 평가

외부 평가 라이브러리와 연동해 더 깊은 품질 측정을 수행합니다.
Layer 1/2 지표를 그대로 유지하면서 외부 지표를 추가합니다.

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    enable_deepeval=True,   # pip install agent-evaluator[deepeval]
    enable_ragas=True,      # pip install agent-evaluator[ragas]
    enable_langsmith=True,  # LangSmith API 키 필요
)
```

#### DeepEval 어댑터 (5종)

`pip install "agent-evaluator[deepeval]"` 필요. LLM 기반 시맨틱 평가를 수행합니다.

| 지표 | 출력 키 | 설명 | 조건 |
|------|---------|------|------|
| **G-Eval** | `g_eval_score`, `g_eval_reason`, `g_eval_passed` | 사용자 정의 품질 기준으로 LLM이 직접 채점 (0–1) | `quality_criteria` 전달 시 |
| **Hallucination** | `hallucination_score`, `hallucination_detected` | 시맨틱 할루시네이션 탐지 (높을수록 낮은 할루시네이션) | `retrieved_context` 전달 시 |
| **Toxicity** | `toxicity_score`, `toxicity_detected` | 유해·공격적 콘텐츠 탐지 (0–1) | 항상 |
| **Bias** | `bias_score`, `bias_detected` | 편향 탐지 (0–1) | 항상 |
| **Answer Relevancy** | `answer_relevancy_score`, `answer_relevancy_passed` | QA 답변 관련성 평가 | `task_type`이 qa/information_retrieval 일 때 |

#### Ragas 어댑터 (4종)

`pip install "agent-evaluator[ragas]"` 필요. RAG 파이프라인 특화 평가입니다.
`retrieved_context`를 전달해야 동작합니다.

| 지표 | 출력 키 | 설명 | 조건 |
|------|---------|------|------|
| **Faithfulness** | `ragas_faithfulness` | 컨텍스트 대비 응답 사실 일관성 (0–1) | `retrieved_context` 필요 |
| **Answer Relevancy** | `ragas_answer_relevancy` | 질문에 대한 답변 품질 (0–1) | `retrieved_context` 필요 |
| **Context Precision** | `ragas_context_precision` | 검색된 컨텍스트의 관련성 (0–1) | `retrieved_context` 필요 |
| **Context Recall** | `ragas_context_recall` | 컨텍스트 완전성 (0–1) | `retrieved_context` + `expected_output` 필요 |

종합 점수: `ragas_overall_score` (평균), `ragas_quality` (excellent ≥0.8 / good ≥0.6 / acceptable ≥0.4 / poor)

#### LangSmith 어댑터

LangSmith 트레이싱 데이터를 가져와 네이티브 지표와 통합합니다.
`LANGSMITH_API_KEY` 환경변수와 `metadata.langsmith_run_id` 가 필요합니다.

| 출력 키 | 설명 |
|---------|------|
| `langsmith_latency` | 트레이스 기준 실행 시간 |
| `langsmith_tokens` | LangSmith 집계 토큰 수 |
| `langsmith_cost` | LangSmith 집계 비용 |
| `langsmith_feedback_scores` | 사용자 피드백 점수 통계 |

---

## 설치

### 기본 설치 (의존성 없음)

```bash
pip install agent-evaluator
```

### 선택적 의존성 추가

```bash
pip install "agent-evaluator[deepeval]"    # DeepEval 통합
pip install "agent-evaluator[ragas]"       # Ragas RAG 평가
pip install "agent-evaluator[langchain]"   # LangChain 통합
pip install "agent-evaluator[datasets]"    # PDF 데이터셋 생성 (PyPDF2, pdfplumber)
pip install "agent-evaluator[serve]"       # FastAPI 대시보드 서버
pip install "agent-evaluator[all]"         # 모든 선택적 의존성
```

### 소스에서 개발 설치

```bash
git clone https://github.com/bullpeng72/Agent-Evaluator.git
cd Agent-Evaluator
pip install -e ".[dev]"
```

---

## 빠른 시작

### 1. 기본 사용법

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor()

task = create_taskresult(
    task_id="task_001",
    question="프랑스의 수도는 어디인가요?",
    response="파리입니다.",
    ground_truth="파리",
    execution_time=1.2
)

monitor.record_task(task)
monitor.save_to_file("results")  # results.json + results.html 자동 생성
```

### 2. Context Manager (권장)

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("results") as monitor:
    for question, answer, truth in qa_pairs:
        task = create_taskresult(
            task_id=f"q_{i}",
            question=question,
            response=answer,
            ground_truth=truth,
            execution_time=1.5
        )
        monitor.record_task(task)
# 세션 종료 시 자동 저장 — 예외 발생 시에도 안전
```

### 3. LLM 헬퍼 통합

```python
from agent_evaluator import PerformanceMonitor, LLMHelper, ClaudeHelper

monitor = PerformanceMonitor()

# OpenAI GPT
llm = LLMHelper(monitor)
task = llm.evaluate_openai(
    task_id="gpt_001",
    prompt="머신러닝이란 무엇인가요?",
    ground_truth="머신러닝은 데이터로부터 패턴을 학습하는 AI 기법입니다."
)

# Anthropic Claude
claude = ClaudeHelper(monitor)
task = claude.evaluate_claude(
    task_id="claude_001",
    prompt="강화학습을 설명해주세요.",
    ground_truth="강화학습은 보상을 통해 학습하는 방식입니다."
)
```

### 4. 보안 지표 활성화

```python
monitor = PerformanceMonitor(
    enable_hallucination_detection=True,
    enable_security_metrics=True,       # 기본값 False (성능 비용)
)

task = create_taskresult(
    task_id="sec_test",
    response="결과입니다.",
    input_text="'; DROP TABLE users; --",  # SQL Injection 탐지
    execution_time=0.5
)
monitor.record_task(task)
```

---

## 프레임워크 통합

### LangChain

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.integrations import create_evaluated_langchain_agent

monitor = PerformanceMonitor()
agent = create_evaluated_langchain_agent(llm, tools, monitor=monitor)

# 에이전트 실행 → 자동으로 지표 수집
result = agent.run("질문을 입력하세요")
```

### CrewAI

```python
from agent_evaluator.integrations import create_evaluated_crew

# CrewAI Crew 실행 + 자동 평가
crew = create_evaluated_crew(tasks, agents, monitor=monitor)
result = crew.kickoff()
```

### LangGraph

```python
from agent_evaluator.integrations import create_evaluated_langgraph

# StateGraph 실행 + 워크플로우 추적
evaluated_graph = create_evaluated_langgraph(graph, monitor=monitor)
result = evaluated_graph.invoke({"input": "..."})
```

### AutoGen

```python
from agent_evaluator.integrations import create_evaluated_autogen_agent

agent = create_evaluated_autogen_agent(config, monitor=monitor)
# 멀티 에이전트 대화 자동 추적
```

---

## 평가 리포트

`save_to_file()` 호출 시 두 가지 파일이 자동 생성됩니다.

```
results/
├── evaluation_20240101_120000.json   ← 원시 데이터 (프로그래밍 활용)
└── evaluation_20240101_120000.html   ← 시각화 리포트 (브라우저에서 확인)
```

**JSON 리포트 구조:**

```json
{
  "period": {"start": "...", "end": "..."},
  "summary": {
    "total_tasks": 100,
    "task_completion_rate": 0.94,
    "average_accuracy": 0.87,
    "average_latency_ms": 1230,
    "total_tokens": 45000,
    "estimated_cost_usd": 0.135
  },
  "alerts": ["정확도가 임계값(0.8) 이하", "평균 지연 1.2초 초과"],
  "recommendations": ["캐싱 전략 도입 권장", "토큰 압축 적용 검토"],
  "security_metrics": {...},
  "tool_metrics": {...}
}
```

---

## CLI

`pip install agent-evaluator` 후 즉시 사용할 수 있는 `agent-eval` 명령어를 제공합니다.

### 명령어 목록

| 명령어 | 설명 |
|--------|------|
| `agent-eval init` | 대화형 API 키 설정 마법사 |
| `agent-eval check` | 현재 설정 상태 및 API 키 확인 |
| `agent-eval serve` | FastAPI 대시보드 웹 서버 실행 |
| `agent-eval version` | 패키지 버전 출력 |

### `agent-eval init`

API 키를 대화형으로 입력·저장하는 마법사입니다.

```bash
agent-eval init
```

설정하는 항목:
- `OPENAI_API_KEY` (필수) — LLMHelper, DeepEval, Ragas 평가에 사용
- `ANTHROPIC_API_KEY` (선택) — ClaudeHelper 사용 시 필요
- `LANGSMITH_API_KEY` (선택) — LangSmith 트레이싱 연동
- `DEEPEVAL_API_KEY` (선택) — Confident AI 대시보드 연동
- `AGENT_EVALUATOR_OUTPUT_DIR` — 결과 저장 디렉토리 (기본: `./results`)

저장 위치를 대화형으로 선택할 수 있습니다: 기존 `.env` 업데이트 / 현재 디렉토리 `.env` 생성 / 전역 설정 파일 (`~/.config/agent-evaluator/.env`).

### `agent-eval check`

현재 환경에 설정된 API 키 및 설정값 상태를 출력합니다.

```bash
agent-eval check
```

출력 예시:
```
  Agent Evaluator v0.5.1 — 설정 상태
  ──────────────────────────────────────────────────
  .env 로드: /home/user/project/.env

API 키 상태:
  OPENAI_API_KEY       ✅  sk-proj...  (loaded .env)
  ANTHROPIC_API_KEY    ✅  sk-ant-...  (system env)
  LANGSMITH_API_KEY    ⚪  미설정 (선택)
  DEEPEVAL_API_KEY     ⚪  미설정 (선택)

기타 설정:
  AGENT_EVALUATOR_OUTPUT_DIR    ./results
  OPENAI_MODEL                  gpt-4o-mini
  ANTHROPIC_MODEL               claude-haiku-4-5-20251001
```

### `agent-eval serve`

평가 결과를 시각화하는 FastAPI 웹 대시보드를 실행합니다.

```bash
agent-eval serve [results_dir] [옵션]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `results_dir` | `./results` | 평가 결과 JSON 파일이 있는 디렉토리 |
| `--host HOST` | `127.0.0.1` | 바인딩 호스트 |
| `--port PORT` | `8765` | 포트 번호 |
| `--open` | 기본 활성화 | 서버 시작 후 브라우저 자동 오픈 |
| `--no-open` | — | 브라우저 자동 오픈 비활성화 |
| `--watch` | — | 파일 변경 감시 (핫 리로드) |
| `--slide` | — | 시작 화면을 슬라이드 뷰로 설정 |
| `--share` | — | 외부 접근 허용 (`host=0.0.0.0`) |
| `--title TITLE` | `Agent Evaluator Dashboard` | 대시보드 제목 |

```bash
agent-eval serve                                    # 기본 실행 (브라우저 자동 오픈)
agent-eval serve ./results --port 8080              # 포트 지정
agent-eval serve ./results --watch                  # 파일 변경 시 자동 갱신
agent-eval serve ./results --no-open                # 브라우저 오픈 없이 서버만 시작
agent-eval serve ./results --share                  # 외부 접근 허용 (팀 공유)
```

> `results_dir`을 지정하지 않으면 `./results` → `path_helpers` 자동 탐지 순으로 결과 디렉토리를 찾습니다.

---

## 대시보드

FastAPI + Alpine.js 기반 SPA 웹 대시보드로 평가 결과를 시각화합니다.
`pip install "agent-evaluator[serve]"` 후 `agent-eval serve`로 실행합니다.

실행 후 접근 가능한 URL:

| URL | 설명 |
|-----|------|
| `http://localhost:8765` | 메인 대시보드 |
| `http://localhost:8765/slides` | 슬라이드 뷰 |
| `http://localhost:8765/api/docs` | Swagger UI (OAS 3.1) |
| `http://localhost:8765/api/redoc` | Redoc API 문서 |

**제공 기능:**
- 전체 지표 개요 및 트렌드 (TCR·정확도·할루시네이션·레이턴시·비용)
- 태스크별 정확도/지연시간 분포 및 이상치 탐지
- 툴 사용 패턴 분석 (Tool Selection F1, 효율성, 중복 호출)
- 보안 이벤트 타임라인 (L1/L2 보안 이벤트 시각화)
- Agent 협업 네트워크 그래프 (Pan/Zoom 지원)
- Layer 3 Advanced 지표 (DeepEval·Ragas, 옵션)
- 상관관계 히트맵 (4×4 Pearson 지표 행렬)
- HTML/CSV/JSON 내보내기 + PDF 출력
- OAS 3.1 API 문서 (`/api/docs`, `/api/redoc`)

---

## 프로젝트 구조

```
agent-evaluator/
├── agent_evaluator/              # 메인 패키지
│   ├── core/
│   │   ├── agent_evaluator.py   # 14개 트래커 + PerformanceMonitor
│   │   ├── hybrid_monitor.py    # HybridPerformanceMonitor
│   │   └── monitor_context.py   # Context managers
│   ├── integrations/
│   │   ├── crewai_integration.py
│   │   ├── langchain_integration.py
│   │   ├── langgraph_integration.py
│   │   ├── autogen_integration.py
│   │   ├── llm_helpers.py       # LLMHelper (OpenAI), ClaudeHelper (Anthropic)
│   │   ├── metric_adapters.py   # DeepEval / Ragas / LangSmith 어댑터
│   │   └── framework_integrations.py
│   ├── helpers/
│   │   └── taskresult_helpers.py  # create_taskresult(), 토큰 추출 유틸
│   ├── reporting/
│   │   └── comprehensive_report.py  # HTML/텍스트 리포트 생성기
│   ├── datasets/
│   │   ├── korean_rag_dataset_generator.py  # 한국어 RAG 데이터셋 생성
│   │   └── korean_rag_evaluator.py          # 한국어 RAG 평가
│   ├── serve/                   # FastAPI 대시보드 서버
│   │   ├── server.py            # FastAPI app 진입점
│   │   ├── loader.py            # 평가 결과 로더
│   │   ├── watcher.py           # 파일 변경 감시
│   │   └── routers/             # API 라우터 (data, export, golden, stream, transparency)
│   ├── cli/
│   │   └── main.py              # agent-eval CLI 진입점
│   ├── utils/
│   │   ├── dashboard_integration.py
│   │   ├── data_registry.py
│   │   └── path_helpers.py
│   └── config.py                # 환경변수 설정 로더
│
├── Evaluator_Examples/           # 단계별 실습 예제
│   ├── level_1_foundation/       # 기초 — 10개 (5~10분)
│   ├── level_2_advanced/         # 고급 — 8개 (15~30분)
│   ├── level_3_production/       # 프로덕션 — 6개 (30분+)
│   └── Dashboard/                # Streamlit 대시보드 (레거시 — FastAPI로 대체됨)
│
├── Docs/Metrics/                 # 지표별 상세 문서 (25개)
├── pyproject.toml
├── LICENSE
└── CHANGELOG.md
```

---

## 예제 가이드

### Level 1 — 기초 (5~10분)

```bash
cd Evaluator_Examples
python level_1_foundation/01_quickstart.py              # 기본 워크플로우
python level_1_foundation/02_layer1_trackers.py         # Layer 1 지표 전체
python level_1_foundation/03_taskresult_helpers.py      # 헬퍼 함수
python level_1_foundation/04_thresholds_validation.py   # 품질 임계값
python level_1_foundation/05_layer1_security_basic.py   # 보안 지표 기초
python level_1_foundation/06_latency_token_economy.py   # 지연시간·토큰 비용
python level_1_foundation/07_hallucination_detection.py # 할루시네이션 탐지
python level_1_foundation/08_response_quality.py        # 응답 품질 6차원
python level_1_foundation/09_evaluation_session.py      # Context Manager 활용
python level_1_foundation/10_state_transitions_tracking.py  # 상태 전이 추적
```

### Level 2 — 고급 (15~30분)

```bash
python level_2_advanced/01_golden_dataset.py       # 골든 데이터셋 생성·평가
python level_2_advanced/02_layer3_hybrid.py        # DeepEval/Ragas 하이브리드
python level_2_advanced/03_rag_system.py           # RAG 시스템 평가
python level_2_advanced/04_tool_selection.py       # 툴 선택 최적화
python level_2_advanced/05_multi_agent.py          # 멀티 에이전트 협업
python level_2_advanced/06_workflow.py             # 복잡한 워크플로우 추적
python level_2_advanced/07_security_advanced.py    # 보안 지표 고급
python level_2_advanced/08_advanced_api_methods.py # 고급 API 메서드
```

### Level 3 — 프로덕션 (30분+)

```bash
python level_3_production/01_framework_crewai.py          # CrewAI 통합
python level_3_production/02_cost_optimization.py         # 비용 최적화
python level_3_production/03_framework_langchain.py       # LangChain 통합
python level_3_production/04_framework_langgraph.py       # LangGraph 통합
python level_3_production/05_transparency.py              # 설명가능성
python level_3_production/06_security_production_monitoring.py  # 프로덕션 보안 모니터링
```

---

## 공개 API 요약

```python
from agent_evaluator import (
    # 핵심 클래스
    PerformanceMonitor,      # 중앙 오케스트레이터
    TaskResult,              # 태스크 실행 결과 (44개 필드)
    TaskType,                # QA / CODE_GENERATION / REASONING 등 9종
    EvaluationReport,        # 집계 평가 리포트

    # 하이브리드
    HybridPerformanceMonitor,
    ExtendedTaskResult,

    # 헬퍼
    create_taskresult,       # TaskResult 간편 생성 함수
    evaluation_session,      # 컨텍스트 매니저 (기본)
    hybrid_evaluation_session,

    # LLM 헬퍼
    LLMHelper,               # OpenAI 평가 헬퍼
    ClaudeHelper,            # Anthropic 평가 헬퍼

    # 개별 트래커 (고급 사용자)
    TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
    ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker,
    ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
    AgentCoordinationTracker, WorkflowExecutionTracker,
    InputSanitizationTracker, OutputLeakageDetector,
    ToolAuthorizationTracker, PrivilegeEscalationDetector, ToolChainAttackDetector,
)
```

---

## 개발 환경 설정

```bash
git clone https://github.com/bullpeng72/Agent-Evaluator.git
cd Agent-Evaluator

# 개발 의존성 포함 설치
pip install -e ".[dev]"

# 테스트 실행
pytest

# 코드 품질 검사
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/
```

---

## 요구사항

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `numpy` | >=1.20.0, <2.0.0 | 수치 연산 |
| `pandas` | >=1.3.0, <3.0.0 | 지표 집계 |
| `python-dotenv` | >=0.19.0 | 환경변수 관리 |

### 선택적 의존성

| Extra | 패키지 | 용도 |
|-------|--------|------|
| `[deepeval]` | deepeval | 고급 LLM 평가 지표 |
| `[ragas]` | ragas | RAG 특화 평가 |
| `[langchain]` | langchain | LangChain 프레임워크 통합 |
| `[datasets]` | PyPDF2, pdfplumber | PDF 데이터셋 생성 |
| `[serve]` | fastapi, uvicorn, jinja2 | FastAPI 대시보드 서버 |

---

## 기여 방법

1. 이 저장소를 Fork 합니다.
2. 기능 브랜치를 생성합니다: `git checkout -b feature/새기능`
3. 변경사항을 커밋합니다: `git commit -m 'feat: 새 기능 추가'`
4. 브랜치에 Push 합니다: `git push origin feature/새기능`
5. Pull Request를 엽니다.

버그 리포트, 기능 제안, 문서 개선 등 모든 기여를 환영합니다.
[GitHub Issues](https://github.com/bullpeng72/Agent-Evaluator/issues)에서 논의해 주세요.

---

## 라이선스

MIT License — 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.

---

## 작성자

**Sungwoo Kim**
- Email: [sungwoo.kim@gmail.com](mailto:sungwoo.kim@gmail.com)
- GitHub: [github.com/bullpeng72](https://github.com/bullpeng72)

---

## 인용

연구나 프로젝트에 Agent Evaluator를 사용하셨다면 아래 형식으로 인용해 주세요.

```bibtex
@software{agent_evaluator,
  title   = {Agent Evaluator: Production-ready evaluation framework for AI agents},
  author  = {Kim, Sungwoo},
  year    = {2024},
  version = {0.5.1},
  url     = {https://github.com/bullpeng72/Agent-Evaluator},
  license = {MIT}
}
```

---

<div align="center">
AI 에이전트 커뮤니티를 위해 만들었습니다 ❤️<br>
<a href="https://github.com/bullpeng72/Agent-Evaluator">GitHub</a> ·
<a href="https://github.com/bullpeng72/Agent-Evaluator/issues">Issues</a> ·
<a href="https://pypi.org/project/agent-evaluator/">PyPI</a>
</div>
