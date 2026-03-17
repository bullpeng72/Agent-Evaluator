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
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3 — Hybrid Evaluation  (선택적 외부 라이브러리 통합)         │
│  DeepEval · Ragas · LangSmith                                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 — Agentic Metrics  (에이전트 특화 지표, 의존성 없음)        │
│  Tool Use · Retry · Coordination · Workflow · Security(5종)     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1 — Foundation Metrics  (핵심 품질 지표, 의존성 없음)         │
│  Task Completion · Accuracy · Hallucination · Quality · Latency │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1 — 기초 지표 (6종)

| 지표 | 클래스 | 설명 |
|------|--------|------|
| **Task Completion Rate** | `TaskCompletionTracker` | 성공률, 실패 원인 분류, 벤치마크 비교 |
| **Accuracy Evaluation** | `AccuracyEvaluator` | QA/코드/일반 유형별 정확도. Token Overlap(40%) + Jaccard(30%) + LCS(20%) + 문자 유사도(10%) 가중 조합 |
| **Hallucination Detection** | `HallucinationDetector` | 컨텍스트 대비 응답 사실 일관성 측정 |
| **Response Quality** | `ResponseQualityEvaluator` | 관련성·완결성·명확성·일관성·효율성·안전성 6차원 평가 |
| **Latency Tracking** | `LatencyTracker` | P50/P95/P99 백분위 지연 시간 분석 |
| **Token Economy** | `TokenEconomyTracker` | 입출력 토큰 비율, 비용 추정, 월간 예측 |

### Layer 2 — 에이전틱 지표 (9종)

| 지표 | 클래스 | 설명 |
|------|--------|------|
| **Tool Call Analysis** | `ToolCallAnalyzer` | 툴 호출 성공률, 평균 호출 수, 불필요 호출 탐지 |
| **Retry & Correction** | `RetryCorrectionTracker` | 재시도 패턴, 자기 수정 능력, 루프 탐지 |
| **Tool Selection** | `ToolSelectionTracker` | Precision/Recall/F1 기반 툴 선택 정확도 |
| **Agent Coordination** | `AgentCoordinationTracker` | 멀티 에이전트 협업 품질, 인터랙션 성공률 |
| **Workflow Execution** | `WorkflowExecutionTracker` | 워크플로우 완료율, 분기 처리, 병목 감지 |
| **Input Sanitization** | `InputSanitizationTracker` | SQL Injection, Command Injection, Prompt Injection 등 탐지 |
| **Output Leakage** | `OutputLeakageDetector` | API 키, PII, 민감 데이터 응답 노출 탐지 |
| **Tool Authorization** | `ToolAuthorizationTracker` | 비인가 툴 사용 시도 탐지 |
| **Privilege Escalation** | `PrivilegeEscalationDetector` | 권한 탈취 패턴 탐지 |
| **Tool Chain Attack** | `ToolChainAttackDetector` | 연쇄 툴 호출을 통한 공격 패턴 탐지 |

### Layer 3 — 하이브리드 평가

외부 라이브러리와 연동해 더 깊은 평가를 수행합니다.

```python
from agent_evaluator import HybridPerformanceMonitor

monitor = HybridPerformanceMonitor(
    enable_deepeval=True,   # pip install agent-evaluator[deepeval]
    enable_ragas=True,      # pip install agent-evaluator[ragas]
    enable_langsmith=True,  # LangSmith API 키 필요
)
```

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

## 대시보드

FastAPI + Alpine.js 기반 웹 대시보드로 평가 결과를 시각화합니다.
별도 설치 없이 `pip install "agent-evaluator[serve]"` 한 줄로 실행됩니다.

```bash
agent-eval serve                        # 대시보드 실행 (기본 포트 8765)
agent-eval serve --port 8080 --watch    # 포트 지정 + 파일 변경 자동 갱신
agent-eval serve --open                 # 브라우저 자동 오픈
```

**제공 기능:**
- 전체 지표 개요 및 트렌드 (TCR·정확도·할루시네이션·레이턴시·비용)
- 태스크별 정확도/지연시간 분포 및 이상치 탐지
- 툴 사용 패턴 분석 (Tool Selection F1, 효율성, 중복 호출)
- 보안 이벤트 타임라인 (L1/L2 보안 이벤트 시각화)
- Agent 협업 네트워크 그래프 (Pan/Zoom 지원)
- Layer 3 Advanced 지표 (DeepEval·Ragas, 옵션)
- 상관관계 히트맵 (4×4 Pearson 지표 행렬)
- HTML/CSV/JSON 내보내기 + PDF 출력
- OAS 3.1 API 문서 (`/api/docs`)

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
│   │   └── metric_adapters.py   # DeepEval / Ragas / LangSmith 어댑터
│   ├── helpers/
│   │   └── taskresult_helpers.py  # create_taskresult(), 토큰 추출 유틸
│   ├── reporting/
│   │   └── comprehensive_report.py  # HTML/텍스트 리포트 생성기
│   ├── datasets/
│   │   ├── korean_rag_dataset_generator.py  # 한국어 RAG 데이터셋 생성
│   │   └── korean_rag_evaluator.py          # 한국어 RAG 평가
│   └── utils/
│       └── dashboard_integration.py
│
├── Evaluator_Examples/           # 단계별 실습 예제
│   ├── level_1_foundation/       # 기초 (5~10분)
│   ├── level_2_advanced/         # 고급 (15~30분)
│   ├── level_3_production/       # 프로덕션 (30분+)
│   └── Dashboard/                # Streamlit 대시보드
│
├── Docs/Metrics/                 # 지표별 상세 문서 (43개)
├── pyproject.toml
├── LICENSE
└── CHANGELOG.md
```

---

## 예제 가이드

### Level 1 — 기초 (5~10분)

```bash
cd Evaluator_Examples
python level_1_foundation/01_quickstart.py         # 기본 워크플로우
python level_1_foundation/02_layer1_trackers.py    # Layer 1 지표 전체
python level_1_foundation/03_taskresult_helpers.py # 헬퍼 함수
python level_1_foundation/04_thresholds_validation.py  # 품질 임계값
python level_1_foundation/05_layer1_security_basic.py  # 보안 지표 기초
```

### Level 2 — 고급 (15~30분)

```bash
python level_2_advanced/01_golden_dataset.py  # 골든 데이터셋 생성·평가
python level_2_advanced/02_layer3_hybrid.py   # DeepEval/Ragas 하이브리드
python level_2_advanced/03_rag_system.py      # RAG 시스템 평가
python level_2_advanced/04_tool_selection.py  # 툴 선택 최적화
python level_2_advanced/05_multi_agent.py     # 멀티 에이전트 협업
python level_2_advanced/06_workflow.py        # 복잡한 워크플로우 추적
```

### Level 3 — 프로덕션 (30분+)

```bash
python level_3_production/01_framework_crewai.py     # CrewAI 통합
python level_3_production/02_cost_optimization.py    # 비용 최적화
python level_3_production/03_framework_langchain.py  # LangChain 통합
python level_3_production/04_framework_langgraph.py  # LangGraph 통합
python level_3_production/05_transparency.py         # 설명가능성
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
