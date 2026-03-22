# 🤖 Agent Evaluator

AI Agent를 위한 프로덕션급 평가 프레임워크

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg) ![License](https://img.shields.io/badge/license-MIT-green.svg) ![Version](https://img.shields.io/badge/version-0.6.0-brightgreen.svg) ![Zero Configuration](https://img.shields.io/badge/Zero_Config-100%25-blue.svg) ![Security Metrics](https://img.shields.io/badge/Security_Metrics-5_Built--in-orange.svg)

## 목차

  1. [개요](<#overview>)
  2. [주요 기능](<#주요-기능>)
  3. [🆚 기존 솔루션과의 비교](<#comparison>)
     * [비교 개요](<#comparison-overview>)
     * [vs LangSmith](<#langsmith>)
     * [vs DeepEval](<#deepeval>)
     * [vs Ragas](<#ragas>)
     * [vs TruLens](<#trulens>)
     * [vs Arize Phoenix](<#phoenix>)
     * [종합 비교표](<#comparison-table>)
     * [Agent Evaluator를 선택해야 하는 이유](<#why-agent-evaluator>)
  4. [빠른 시작](<#quick-start>)
  5. [설치 옵션](<#설치-옵션>)
  6. [프로젝트 구조](<#프로젝트-구조>)
  7. [사용 예제](<#사용-예제>)
  8. [Zero Configuration](<#zero-configuration>)
  9. [데이터 레지스트리](<#데이터-레지스트리>)
  10. [문서](<#문서>)
  11. [라이센스](<#라이센스>)

* * *

## 📋 개요

**Agent Evaluator** 는 AI Agent의 성능을 측정하고 모니터링하기 위한 Production-ready 평가 프레임워크입니다.

#### 🎯 핵심 가치

  * ✅ **100% Zero Configuration** \- 경로 설정 불필요
  * ✅ **3-Layer 메트릭 체계** \- Basic + Security → Agentic + Security → Advanced
  * ✅ **실시간 Dashboard** \- FastAPI 기반 모니터링
  * ✅ **자동 레지스트리** \- 개발자 ↔ QA 간 데이터 공유
  * ✅ **프레임워크 통합** \- LangChain, LangGraph, CrewAI, AutoGen 지원

* * *

## ✨ 주요 기능

### Layer 1: Foundation Metrics (6개, 100% 무료)

외부 의존성 없이 즉시 사용 가능한 기본 성능 지표

  * **Task Completion Rate (TCR)** : 작업 성공률
  * **Accuracy** : 응답 정확도 (Token Overlap, Jaccard, LCS, Char 가중 평균)
  * **Hallucination Detection** : 룰 기반 환각 감지 (Opt-in, <1ms)
  * **Quality Metrics** : 5차원 응답 품질 평가
  * **Latency** : 실행 시간 분석 (P50/P95/P99)
  * **Token Economy** : 토큰 사용량 및 비용 추정

### Layer 2: Agentic + Security Metrics (10개, 무료)

#### 🤖 Agentic Metrics (5개)

  * **Tool Call Analysis** : 도구 호출 패턴 및 효율성 분석
  * **Retry & Correction** : 재시도 동작 및 자기 수정 능력 평가
  * **Tool Selection Accuracy** : F1 기반 올바른 도구 선택 평가
  * **Agent Coordination** : 멀티 에이전트 협업 품질
  * **Workflow Execution** : 워크플로우 실행 성공률 및 분기 추적

#### 🔒 Security Metrics (5개, Opt-in)

  * **Input Sanitization** : SQL/Command Injection, Path Traversal, XSS, Prompt Injection 탐지
  * **Output Leakage** : API 키, 비밀번호, 개인정보 유출 검사
  * **Tool Authorization** : 허가된 도구만 호출했는지 검증
  * **Privilege Escalation Detection** : Agent의 권한 상승 시도 탐지
  * **Tool Chain Attack Detection** : 연쇄 도구 호출 공격 패턴 탐지

### Layer 3: Advanced Metrics (API 비용)

  * **DeepEval** : G-Eval, Toxicity, Bias, Answer Relevancy
  * **Ragas** : Faithfulness, Context Precision/Recall, Answer Similarity

### 추가 기능

  * **🔒 보안 평가** : 입력 검증, 정보 유출 방지, 권한 관리, 공격 탐지
  * **한국어 RAG 평가** : Golden Dataset 자동 생성 및 평가
  * **Framework 통합** : LangChain, CrewAI, AutoGen, LangGraph (보안 메트릭 포함)
  * **Test Transparency** : Metric 계산 추적, Anomaly 탐지, 보안 감사 로그
  * **Threshold Configuration** : Quality Gate + 보안 정책 설정 및 비교
  * **Dashboard** : 실시간 모니터링 UI (다중 섹션, 보안 시각화 포함)

* * *

## 🆚 기존 솔루션과의 비교

#### 비교 개요

Agent Evaluator는 AI Agent 평가를 위한 **올인원 오픈소스 솔루션** 입니다. LangSmith, DeepEval, Ragas, TruLens, Arize Phoenix 등 기존 솔루션과 비교하여 **프로덕션 배포, 비용 효율성, 한국어 지원** 에서 차별화됩니다.

### 🔵 vs LangSmith (LangChain 공식)

기준 | LangSmith | Agent Evaluator  
---|---|---  
**타입** | ☁️ 클라우드 SaaS (Paid) | 🏠 **오픈소스 Self-Hosted**  
**비용** | $39/mo ~ $799/mo  
(호스팅/운영비 추가) | **$0 (Layer 1/2 무료)**  
$0.01~$0.05/eval (Layer 3 API)  
**데이터 저장** | 클라우드 (LangChain 서버) | **로컬 저장** (데이터 주권 보장)  
**프레임워크** | LangChain 중심 | **프레임워크 중립**  
(LangChain, CrewAI, AutoGen, LangGraph)  
**Agentic 메트릭** | 제한적 (Trace 기반) | **Layer 2 전용**  
(Tool Selection, Multi-Agent Coordination)  
**한국어 지원** | ❌ 제한적 | ✅ **완전 지원**  
(Korean RAG Evaluator 내장)  
**Zero Configuration** | ❌ 클라우드 설정 필요 | ✅ **100% 자동**  
**Dashboard** | 웹 기반 (클라우드) | **FastAPI Dashboard** (로컬/배포 모두)  
**네트워크 요구** | 필수 (클라우드 연결) | **선택** (Layer 3만 필요)  
**사용 사례** | LangChain 프로젝트  
클라우드 배포 선호 | **모든 프레임워크**  
온프레미스/비용 민감 프로젝트  
  
#### 💡 언제 LangSmith를 선택하나요?

  * LangChain만 사용하고 다른 프레임워크 필요 없음
  * 클라우드 관리형 서비스 선호 (운영 오버헤드 최소화)
  * 팀 협업 기능 필요 (LangSmith Teams)
  * 데이터 저장 위치가 중요하지 않음

#### ✅ Agent Evaluator를 선택하는 이유

  * **비용 절감** : $0 기본 비용 vs $468+/year
  * **데이터 주권** : 민감한 데이터 로컬 보관
  * **멀티 프레임워크** : LangChain 외 CrewAI, AutoGen 지원
  * **한국어 RAG** : 한국어 평가 특화

### 🟣 vs DeepEval (Confident AI)

기준 | DeepEval | Agent Evaluator  
---|---|---  
**타입** | 오픈소스 + 유료 클라우드 | **완전 오픈소스**  
**메트릭 초점** | LLM 품질 평가  
(G-Eval, Hallucination, Bias) | **3-Layer 체계**  
(Native + Agentic + Advanced)  
**Agentic AI** | ❌ 제한적 | ✅ **Layer 2 전용 메트릭**  
**API 의존성** | 필수 (Confident AI API) | **선택** (Layer 1/2는 무료)  
**Dashboard** | Confident AI 웹 (클라우드) | **FastAPI Dashboard** (로컬)  
**통합** | DeepEval 메트릭 사용 | **DeepEval 포함 + Layer 1/2**  
**Golden Dataset** | 수동 생성 | **자동 생성/관리**  
**사용 사례** | LLM 품질 평가 전문 | **Agent 포괄 평가**  
  
#### 💡 언제 DeepEval을 선택하나요?

  * LLM 응답 품질 평가만 필요 (G-Eval, Bias, Toxicity)
  * Agent/Tool 사용은 평가 대상 아님
  * Confident AI 클라우드 사용 가능

#### ✅ Agent Evaluator를 선택하는 이유

  * **포괄적 평가** : LLM 품질 + Agent 행동 + Tool 사용
  * **DeepEval 포함** : Layer 3에서 DeepEval 메트릭 사용 가능
  * **무료 시작** : Layer 1/2만으로도 충분한 평가
  * **FastAPI Dashboard** : Confident AI 계정 불필요

### 🟢 vs Ragas (RAG 평가)

기준 | Ragas | Agent Evaluator  
---|---|---  
**타입** | 오픈소스 (RAG 전용) | **오픈소스 (Agent 포괄)**  
**초점** | RAG 시스템 평가 | **RAG + Agent + Tool + Workflow**  
**메트릭** | Faithfulness, Context Precision/Recall  
Answer Similarity | **Ragas 포함 + Layer 1/2 16개 (6 Foundation + 10 Agentic+Security)**  
**한국어** | ❌ 제한적 (영어 중심) | ✅ **Korean RAG Evaluator 전용**  
**Golden Dataset** | 수동 준비 | **자동 생성 도구**  
**Dashboard** | ❌ 없음 (Jupyter만) | ✅ **FastAPI Dashboard**  
**통합** | Ragas 메트릭 사용 | **Ragas 포함 + 추가 메트릭**  
**사용 사례** | RAG 시스템 품질 평가 | **RAG + Agent 통합 평가**  
  
#### 💡 언제 Ragas를 선택하나요?

  * 순수 RAG 시스템만 평가 (Agent 없음)
  * Jupyter Notebook 기반 분석 선호
  * Ragas 메트릭만으로 충분

#### ✅ Agent Evaluator를 선택하는 이유

  * **Ragas 포함** : Layer 3에서 Ragas 사용 가능
  * **한국어 RAG** : 한국어 특화 평가 (KoreanRAGEvaluator)
  * **Agent 확장** : RAG + Tool + Multi-Agent
  * **FastAPI Dashboard** : 실시간 시각화 및 모니터링

### 🔴 vs TruLens (TruEra)

기준 | TruLens | Agent Evaluator  
---|---|---  
**타입** | 오픈소스 + 엔터프라이즈 | **완전 오픈소스**  
**초점** | LLM 평가 및 추적 | **Agent 포괄 평가**  
**복잡도** | 높음 (설정 복잡) | **낮음 (Zero Configuration)**  
**Dashboard** | 자체 UI (복잡) | **FastAPI Dashboard (직관적)**  
**Learning Curve** | 가파름 | **완만함 (5분 시작)**  
**프레임워크** | LangChain, LlamaIndex | **LangChain, CrewAI, AutoGen, LangGraph**  
**사용 사례** | 대규모 엔터프라이즈  
상세 추적 필요 | **중소규모 프로젝트**  
빠른 구축  
  
#### 💡 언제 TruLens를 선택하나요?

  * 엔터프라이즈급 상세 추적 필요
  * 복잡한 설정/운영 가능
  * TruEra 상용 지원 필요

#### ✅ Agent Evaluator를 선택하는 이유

  * **Zero Configuration** : 5분 내 시작 가능
  * **간단한 API** : 학습 곡선 최소화
  * **FastAPI Dashboard** : 익숙한 UI
  * **가벼운 의존성** : 설치/운영 간단

### 🟠 vs Arize Phoenix (Arize AI)

기준 | Arize Phoenix | Agent Evaluator  
---|---|---  
**타입** | 오픈소스 + 클라우드 (Arize) | **완전 오픈소스**  
**초점** | LLM Observability | **Agent Evaluation**  
**실시간 모니터링** | ✅ 강력 | ✅ FastAPI 기반  
**트레이싱** | OpenTelemetry 기반 | **자체 Test Transparency**  
**비용** | 무료 (오픈소스)  
Arize 클라우드 유료 | **$0 (Layer 1/2)**  
**데이터 저장** | Phoenix DB (로컬/클라우드) | **JSON 파일 (간단)**  
**복잡도** | 중간 (OpenTelemetry 이해 필요) | **낮음 (Zero Config)**  
**사용 사례** | 프로덕션 Observability | **개발/QA 평가 + 프로덕션**  
  
#### 💡 언제 Arize Phoenix를 선택하나요?

  * 프로덕션 LLM Observability 중심
  * OpenTelemetry 표준 사용
  * Arize AI 플랫폼 통합

#### ✅ Agent Evaluator를 선택하는 이유

  * **평가 중심** : Observability보다 Evaluation에 최적화
  * **간단한 저장** : JSON 파일로 쉬운 관리
  * **Golden Dataset** : 자동 평가 지원
  * **한국어 지원** : Korean RAG Evaluator

### 📊 종합 비교표

기능 | LangSmith | DeepEval | Ragas | TruLens | Phoenix | **Agent Evaluator**  
---|---|---|---|---|---|---  
**타입** | ☁️ SaaS | Hybrid | OSS | Hybrid | Hybrid | **🏠 OSS**  
**비용** | $39+/mo | API 비용 | 무료 | 무료/유료 | 무료/유료 | **$0**  
**Native 메트릭** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | **⭐⭐⭐⭐**  
**Agentic 메트릭** | ⭐⭐ | ⭐ | ❌ | ⭐⭐ | ⭐⭐ | **⭐⭐⭐⭐**  
**Advanced 메트릭** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | **⭐⭐⭐**  
**Zero Configuration** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 100%**  
**한국어 지원** | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | **⭐⭐⭐⭐**  
**프레임워크** | LangChain | 다양 | 다양 | LangChain  
LlamaIndex | 다양 | **모든**  
**Dashboard** | 클라우드 | 클라우드 | ❌ | 자체 UI | Phoenix UI | **FastAPI Dashboard**  
**데이터 주권** | ❌ | ⚠️ | ✅ | ✅ | ✅ | **✅ 완전**  
**Learning Curve** | 중간 | 낮음 | 중간 | 높음 | 중간 | **매우 낮음**  
**Golden Dataset** | 수동 | 수동 | 수동 | 수동 | 수동 | **자동 생성**  
**🔒 보안 메트릭** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 5개 내장**  
**🔒 입력 보안 검증** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ 자동**  
**🔒 정보 유출 방지** | ⚠️ 제한적 | ❌ | ❌ | ❌ | ❌ | **✅ API키/PW 탐지**  
**🔒 권한 관리** | ⚠️ 제한적 | ❌ | ❌ | ❌ | ❌ | **✅ Tool 권한 검증**  
  
### 🎯 Agent Evaluator를 선택해야 하는 이유

#### 1\. 💰 비용 효율성 (Cost Efficiency)

  * **$0 기본 비용** : Layer 1/2 메트릭 완전 무료
  * **선택적 API 비용** : Layer 3만 $0.01~$0.05/evaluation
  * **vs LangSmith** : 연간 $468+ 절약
  * **vs Confident AI** : 클라우드 비용 제로

#### 2\. 🏠 데이터 주권 (Data Sovereignty)

  * **100% 로컬 저장** : 민감한 데이터 외부 유출 없음
  * **온프레미스 배포** : 금융/의료 등 규제 산업 대응
  * **자체 인프라** : 외부 서비스 의존성 제로

#### 3\. 🤖 Agentic AI 특화 (Agentic-First)

  * **Layer 2 전용** : Tool Selection, Agent Coordination, Self-Correction
  * **Multi-Agent 평가** : CrewAI, AutoGen 네이티브 지원
  * **Workflow 추적** : LangGraph 워크플로우 자동 분석

#### 4\. 🇰🇷 한국어 완전 지원 (Korean-First)

  * **Korean RAG Evaluator** : 한국어 RAG 시스템 특화 평가
  * **Golden Dataset 자동 생성** : 한국어 데이터셋 자동 생성
  * **한국어 문서** : 완전한 한국어 가이드 및 예제

#### 5\. ⚡ Zero Configuration (Zero-Config)

  * **5분 시작** : 설정 파일 없이 즉시 사용
  * **자동 경로 탐지** : Dashboard 위치 자동 인식
  * **자동 레지스트리** : 데이터 파일 자동 등록/공유

#### 6\. 🔒 보안 우선 (Security-First)

  * **5개 보안 메트릭 내장** : Layer 2에 보안 메트릭 통합 (무료)
  * **입력 검증** : SQL Injection, Command Injection, Path Traversal 자동 탐지
  * **출력 보호** : API 키, 비밀번호, 토큰, 개인정보 유출 방지
  * **권한 관리** : Tool 호출 권한 검증, 권한 상승 시도 탐지
  * **공격 탐지** : 프롬프트 인젝션, Jailbreak 패턴 실시간 탐지
  * **감사 로깅** : 보안 이벤트 자동 기록 및 추적

#### 7\. 🎯 프로덕션 준비 완료 (Production-Ready)

  * **3-Layer 메트릭** : 25개 지표로 포괄적 평가 (Layer 1: 6개, Layer 2: 10개, Layer 3: 9개)
  * **FastAPI Dashboard** : 실시간 모니터링 및 보안 메트릭 시각화
  * **Test Transparency** : 메트릭 계산 과정 추적
  * **Threshold Configuration** : Quality Gate + 보안 정책 자동 검증

#### 8\. 🔄 멀티 프레임워크 (Framework-Agnostic)

  * **LangChain** : 네이티브 통합 (LangChainEvaluator)
  * **CrewAI** : Multi-Agent 자동 추적 (CrewAIEvaluator)
  * **AutoGen** : 대화형 Agent 평가 (AutoGenEvaluator)
  * **LangGraph** : 워크플로우 분석 (LangGraphEvaluator)
  * **커스텀 Agent** : 모든 Python Agent 지원

#### ⚠️ 주의사항: Agent Evaluator가 적합하지 않은 경우

  * **클라우드 관리 선호** : 운영 오버헤드를 완전히 제거하고 싶은 경우 → LangSmith 추천
  * **순수 LLM 품질만 평가** : Agent/Tool 사용 없는 단순 LLM → DeepEval/Ragas 충분
  * **엔터프라이즈 Observability** : 대규모 프로덕션 실시간 추적 → TruLens/Phoenix 고려
  * **LangChain만 사용** : 다른 프레임워크 계획 없음 → LangSmith 생태계 활용

* * *

## 🚀 빠른 시작

### Step 1: 설치

```bash
# 방법 1: PyPI에서 설치 (권장 - 프로덕션)
pip install agent-evaluator

# 방법 2: 로컬 wheel 파일로 설치
pip install /home/fomalhaut/Projects/Agent_Evaluator/dist/agent_evaluator-0.6.0-py3-none-any.whl

# 방법 3: 개발 모드 설치 (editable)
cd /path/to/Agent_Evaluator
pip install -e ".[all]"
```

#### 💡 설치 옵션 선택 가이드

  * **PyPI (pip install agent-evaluator)** : 안정 버전, 프로덕션 환경
  * **로컬 wheel** : PyPI 등록 전, 오프라인 환경, 특정 버전 고정
  * **개발 모드 (-e)** : 코드 수정 필요, 즉시 반영

### Step 2: 기본 사용 (Zero Configuration)

```python
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
from datetime import datetime

# 1. 모니터 생성 (Hallucination Detection Opt-in)
monitor = PerformanceMonitor(enable_hallucination_detection=True)

# 2. Task 기록
task = TaskResult(
    task_id="task_001",
    task_type=TaskType.QA.value,
    success=True,
    completion_score=1.0,
    accuracy_score=0.95,
    execution_time=1.2,
    tokens_used={"input": 100, "output": 50, "total": 150},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now()
)
monitor.record_task(task)

# 3. 리포트 생성
report = monitor.generate_report()
print(f"Accuracy: {report.accuracy_metrics['overall_accuracy']:.2%}")

# 4. 저장 (Zero Configuration - 자동으로 올바른 위치에 저장)
monitor.save_to_file("evaluation_results.json")
# → Dashboard/data/evaluation_results/evaluation_results.json 자동 저장
# → ~/.agent_evaluator/registry.json 레지스트리에 자동 등록
```

### Step 3: Dashboard에서 확인

```bash
pip install agent-evaluator[serve]
agent-eval serve
# → http://localhost:8765 에서 자동으로 브라우저 열림
```

#### 💡 Zero Configuration의 장점

  * ✅ **경로 지정 불필요** \- 자동으로 올바른 위치 감지
  * ✅ **자동 레지스트리** \- 개발자/QA 간 데이터 공유
  * ✅ **즉시 시작** \- 복잡한 설정 없이 바로 사용

* * *

## 📦 설치 옵션

### 옵션 1: PyPI에서 설치 (프로덕션)

```bash
pip install agent-evaluator
```

### 옵션 2: 로컬 개발 모드 설치

```bash
# 프로젝트 루트에서
cd /path/to/Agent_Evaluator
pip install -e .

# 또는 전체 기능 포함
pip install -e ".[all]"
```

#### 💡 개발 모드의 장점

  * ✅ 코드 변경 시 재설치 불필요
  * ✅ 즉시 변경사항 반영
  * ✅ 디버깅 용이

* * *

## 📁 프로젝트 구조

**Agent Evaluator는 4개의 독립적인 컴포넌트로 구성됩니다:**

#### 🎯 독립성 (Independence)

각 컴포넌트는 독립적으로 사용 가능하며, 필요에 따라 선택적으로 설치/배포할 수 있습니다.

  * **agent_evaluator/** : PyPI 배포 가능한 핵심 패키지
  * **Evaluator_Examples/** : 독립 실행 가능한 튜토리얼
  * **Dashboard/** : 데이터 저장소 (Zero Configuration)
  * **Docs/** : 독립 접근 가능한 HTML 문서

### 1\. 📦 agent_evaluator/ - 핵심 Python 패키지

**목적:** PyPI 배포 가능한 핵심 평가 엔진

```bash
pip install agent-evaluator
```

**특징:**
- Layer 1/2/3 메트릭
- 보안 메트릭
- Framework 통합

**디렉토리 구조:**

```
agent_evaluator/
├── __init__.py
├── core/                           # 핵심 평가 엔진
│   ├── agent_evaluator.py          # PerformanceMonitor (Layer 1+2)
│   └── hybrid_monitor.py           # HybridPerformanceMonitor (Layer 1+2+3)
├── integrations/                   # Framework 통합
│   ├── crewai_integration.py       # CrewAI Multi-Agent 평가
│   ├── langchain_integration.py    # LangChain Agent 평가
│   ├── langgraph_integration.py    # LangGraph Workflow 평가
│   ├── autogen_integration.py      # AutoGen Agent 평가
│   └── framework_integrations.py   # 레거시 통합 (deprecated)
├── datasets/                       # 데이터셋 생성 및 관리
│   ├── korean_rag_evaluator.py     # 한국어 RAG 평가
│   └── korean_rag_dataset_generator.py  # Golden Dataset 자동 생성
├── examples/                       # 예제 작성 유틸리티
│   ├── __init__.py
│   └── example_runner.py           # ExampleRunner 베이스 클래스
├── helpers/                        # 헬퍼 함수
│   └── taskresult_helpers.py       # 🔒 보안 함수 포함
│       ├── validate_input_security()      # Input Sanitization
│       ├── check_output_leakage()         # Output Leakage Detection
│       └── validate_tool_authorization()  # Authorization Check
├── reporting/                      # 리포트 생성
│   └── report_generator.py         # HTML/JSON 리포트
└── utils/                          # 유틸리티
    ├── path_helpers.py             # Zero Configuration 경로 탐지
    ├── data_registry.py            # 데이터 레지스트리 패턴
    └── transparency_manager.py # Test Transparency 추적
```

### 2\. 📚 Evaluator_Examples/ - 예제 및 튜토리얼

**목적:** 실행 가능한 예제 코드 (5개 플랫 파일)

**특징:** 5개 파일로 25개 지표 전체 검증 (품질 / 성능 / 에이전틱 / 보안 / 하이브리드)

**디렉토리 구조:**

```
Evaluator_Examples/
    ├── 01_quality_metrics.py     # 품질 지표 — Accuracy, Hallucination, Response Quality, RAG
    ├── 02_performance_metrics.py # 성능 지표 — TCR, Latency (p50/p95/p99), Token Economy
    ├── 03_agentic_metrics.py     # 에이전틱 지표 — Tool Call, Coordination, Workflow, Retry
    ├── 04_security_metrics.py    # 보안 지표 — Input Sanitization, Leakage, Auth, Escalation, Attack
    └── 05_hybrid_advanced.py     # 하이브리드 평가 — DeepEval, Ragas, LangSmith 통합
```

### 3\. 🌐 Dashboard/ - 데이터 저장소

**목적:** Zero Configuration 데이터 저장소 (FastAPI 대시보드는 `agent-eval serve`로 실행)

**실행 방법:**

```bash
pip install agent-evaluator[serve]
agent-eval serve              # 기본 포트 8765, 브라우저 자동 오픈
agent-eval serve --port 8080  # 포트 지정
agent-eval serve --watch       # 파일 변경 자동 갱신
```

**대시보드 서버 위치:** `agent_evaluator/serve/server.py`

**디렉토리 구조:**

```
Dashboard/
    └── data/                           # 데이터 저장소 (Zero Config 위치)
        ├── evaluation_results/         # 평가 결과 저장
        │   ├── traces/                 # Test Transparency 추적
        │   ├── annotations/            # 메트릭 주석
        │   ├── audit_logs/             # 🔒 보안 감사 로그
        │   └── transparent_reports/    # 투명성 보고서
        ├── golden_datasets/            # Golden Dataset 저장
        ├── thresholds/                 # Threshold 설정
        └── test_configs/               # Test Config 저장
```

### 4\. 📖 Docs/ - HTML 문서 (18개)

**목적:** 독립 접근 가능한 완전한 문서화

**특징:** 한국어 완전 지원, 보안 가이드 포함

**디렉토리 구조:**

```
Docs/
    ├── index.html                      # 문서 홈페이지
    ├── README.html                     # 프로젝트 개요
    │
    ├── 빠른 시작 (3개)
    │   ├── GETTING_STARTED.html        # 설치 및 기본 사용
    │   ├── DEVELOPER_QUICKSTART_GUIDE.html  # 개발자 5분 시작
    │   └── LEARNING_GUIDE.html         # 학습 로드맵
    │
    ├── 핵심 가이드 (6개)
    │   ├── METRICS_GUIDE.html          # 25개 메트릭 상세 설명
    │   ├── SECURITY_METRICS_GUIDE.html # 🔒 보안 메트릭 가이드
    │   ├── AGENTIC_AI_METRICS_GUIDE.html  # Agentic AI 메트릭
    │   ├── FRAMEWORK_INTEGRATION.html  # Framework 통합
    │   ├── KOREAN_RAG_GUIDE.html       # 한국어 RAG 평가
    │   └── GOLDEN_DATASET_GUIDE.html   # Golden Dataset 생성
    │
    ├── 고급 기능 (5개)
    │   ├── ZERO_CONFIGURATION_GUIDE.html   # Zero Config 상세
    │   ├── DATA_EDITOR_TRANSPARENCY_GUIDE.html  # 투명성 분석
    │   ├── THRESHOLD_CONFIGURATION_GUIDE.html   # Threshold 설정
    │   ├── DEPLOYMENT_GUIDE.html       # 배포 가이드
    │   └── DASHBOARD.html              # Dashboard 사용법
    │
    └── API Reference (2개)
        ├── API_REFERENCE.html          # API 상세 문서
        └── index_content.html          # 문서 색인
```

#### ⚠️ 프로젝트 루트 파일

  * **pyproject.toml, setup.py** : 패키지 빌드 설정
  * **dist/** : 빌드된 wheel/tar.gz (agent_evaluator-0.6.0-*)
  * **MANIFEST.in** : 패키지 추가 파일 포함 설정

* * *

## 📊 사용 예제

### 예제 1: 기본 평가 (Zero Configuration)

```python
from agent_evaluator import PerformanceMonitor

# Zero Configuration - 경로 지정 불필요!
monitor = PerformanceMonitor()

# Agent 실행 및 평가
# ... your agent code ...

# 결과 저장 (자동으로 Dashboard/data/evaluation_results/에 저장)
monitor.save_to_file("my_evaluation.json")
```

### 예제 2: 한국어 RAG 평가

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

# Zero Configuration
evaluator = KoreanRAGEvaluator()

result = evaluator.evaluate(
    question="서울의 인구는?",
    answer="서울의 인구는 약 1천만명입니다.",
    context="서울특별시의 인구는 2023년 기준 약 950만명입니다.",
    ground_truth="서울의 인구는 약 950만명입니다."
)

print(f"Faithfulness: {result['faithfulness']:.2f}")
print(f"Answer Relevancy: {result['answer_relevancy']:.2f}")
```

### 예제 3: Hybrid 모니터링 (Basic + Security + Advanced)

```python
from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor

# Zero Configuration + 3-Layer 메트릭
monitor = HybridPerformanceMonitor(
    enable_deepeval=True,
    enable_ragas=True
)

# Layer 1: Foundation metrics (무료, 6개)
# Layer 2: Agentic + Security metrics (무료, 10개)
# Layer 3: Advanced metrics (API 비용, 9개)
monitor.record_task(task)
report = monitor.generate_report()
```

### 예제 4: Test Transparency

```python
from agent_evaluator.utils import TestTransparencyManager

# Zero Configuration
transparency = TestTransparencyManager()

# Metric 계산 추적
trace_id = transparency.start_metric_calculation(
    metric_name="accuracy",
    metric_type="quality"
)

transparency.add_calculation_step(
    trace_id=trace_id,
    step_name="data_validation",
    description="데이터 검증"
)

transparency.complete_metric_calculation(trace_id, final_value=0.95)
# → Dashboard/data/evaluation_results/traces/에 자동 저장
```

### 예제 5: 🔒 보안 메트릭 평가

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator.helpers import (
    validate_input_security,
    check_output_leakage,
    validate_tool_authorization
)

# 보안 메트릭 활성화
monitor = PerformanceMonitor(enable_security_metrics=True)

# 1. 입력 보안 검증
user_input = "SELECT * FROM users WHERE id = '1' OR '1'='1'"
security_result = validate_input_security(user_input)
print(f"입력 보안 위협: {security_result['threat_detected']}")
print(f"위협 유형: {security_result['threat_type']}")  # SQL Injection

# 2. 출력 민감정보 검사
agent_output = "Your API key is sk-1234567890abcdef"
leakage = check_output_leakage(agent_output)
print(f"정보 유출 감지: {leakage['leakage_detected']}")
print(f"유출 유형: {leakage['leakage_types']}")  # ['api_key']

# 3. 도구 호출 권한 검증
allowed_tools = ["search", "calculator"]
requested_tool = "file_delete"
auth_result = validate_tool_authorization(requested_tool, allowed_tools)
print(f"권한 검증: {auth_result['authorized']}")  # False

# 4. 통합 보안 리포트
report = monitor.generate_report()
security_metrics = report.security_metrics
print(f"입력 검증 통과율: {security_metrics['input_sanitization']:.1f}%")
print(f"정보 유출 건수: {security_metrics['output_leakage_count']}")
print(f"권한 위반 건수: {security_metrics['authorization_violations']}")
```

### 예제 6: 🆕 Hallucination Detection

```python
from agent_evaluator import PerformanceMonitor

# Layer1 Hallucination Detection 활성화 (Opt-in, 무료, <1ms)
monitor = PerformanceMonitor(enable_hallucination_detection=True)

# Context와 Response 제공 시 자동 환각 탐지
context = "서울은 대한민국의 수도이며, 인구는 약 1천만 명입니다."
response = "서울은 약 2천5백만 명의 인구가 살고 있습니다."  # 숫자 불일치!

monitor.record_task(
    task,
    context=context,
    response=response,
    ground_truth="서울은 1천만 명"
)

# Hallucination 통계 확인
hall_stats = monitor.hallucination_detector.get_hallucination_rate()
print(f"환각률: {hall_stats['overall_rate']:.1f}%")
print(f"탐지된 환각: {hall_stats['total_flagged']}개")

# 비용 최적화: Layer1(무료) → Layer3(유료) 하이브리드 전략
# - Layer1으로 모든 응답 필터링 ($0)
# - 의심스러운 경우만 Layer3로 정밀 검증 (95% 비용 절감!)
```

#### 💡 Hallucination Detection 사용 전략

  * **개발 환경:** Layer1만 사용 (무료, 빠른 피드백)
  * **프로덕션:** Layer1 필터링 + Layer3 정밀 검증 (Adaptive)
  * **중요 도메인 (법률, 의료):** Layer1 + Layer3 이중 검증

**비용 절감 효과:** 월 10만 건 기준, $500-1,500 → $25-75 (95% 절감)

* * *

## 🎯 Zero Configuration

Agent Evaluator는 **100% Zero Configuration** 을 지원합니다. 모든 핵심 클래스가 경로 설정 없이 자동으로 올바른 위치를 감지합니다.

### Zero Configuration 지원 클래스

클래스 | 자동 감지 경로 | 기능  
---|---|---  
`PerformanceMonitor` | `Dashboard/data/evaluation_results/` | 성능 메트릭 저장  
`HybridPerformanceMonitor` | `Dashboard/data/evaluation_results/` | Hybrid 메트릭 저장  
`KoreanRAGEvaluator` | `Dashboard/data/evaluation_results/`  
`Dashboard/data/golden_datasets/` | RAG 평가 및 데이터셋  
`TestTransparencyManager` | `Dashboard/data/evaluation_results/` | Trace, Annotation, Audit  
  
### 경로 자동 감지 우선순위

  1. **환경 변수** : `AGENT_EVALUATOR_ROOT`
  2. **Git 저장소 루트** : `.git` 디렉토리 찾기
  3. **Dashboard 디렉토리** : 상위 디렉토리에서 `Dashboard/` 찾기
  4. **현재 작업 디렉토리** : 폴백 옵션

#### 📖 자세한 내용

Zero Configuration에 대한 자세한 설명은 [Zero Configuration 가이드](<ZERO_CONFIGURATION_GUIDE.html>)를 참조하세요.

* * *

## 🔗 데이터 레지스트리

Agent Evaluator는 **데이터 레지스트리 패턴** 을 통해 개발자와 품질 관리자 간 데이터를 자동으로 공유합니다.

### 개발자 측

```python
monitor = PerformanceMonitor()
# ... 평가 수행 ...
monitor.save_to_file("results.json")
# 출력: 📋 Dashboard 레지스트리에 자동 등록됨 (~/.agent_evaluator/registry.json)
```

### 품질 관리자 측 (Dashboard)

  1. Dashboard 실행: `agent-eval serve` (Port 8765)
  2. "데이터 편집" → "🔗 외부 데이터 소스" 탭
  3. 자동으로 검색된 프로젝트 선택
  4. "데이터 가져오기" 클릭

**레지스트리 위치** : `~/.agent_evaluator/registry.json`

#### 💡 레지스트리의 장점

  * ✅ **자동 공유** \- 개발자가 저장하면 QA가 바로 접근 가능
  * ✅ **프로젝트 관리** \- 여러 프로젝트의 데이터 중앙 관리
  * ✅ **버전 추적** \- 타임스탬프 기반 이력 관리

* * *

## 📚 문서

Agent Evaluator는 풍부한 문서를 제공합니다:

문서 | 설명 | 링크  
---|---|---  
**README** | 프로젝트 개요 및 빠른 시작 | [README.html](<README.html>)  
**Zero Configuration** | 경로 자동 감지 가이드 | [ZERO_CONFIGURATION_GUIDE.html](<ZERO_CONFIGURATION_GUIDE.html>)  
**Data Registry** | 데이터 레지스트리 상세 가이드 | [DATA_REGISTRY_GUIDE.html](<DATA_REGISTRY_GUIDE.html>)  
**Test Transparency** | 메트릭 계산 추적 가이드 | [TEST_TRANSPARENCY_GUIDE.html](<TEST_TRANSPARENCY_GUIDE.html>)  
**Examples** | 다양한 사용 예제 | `Evaluator_Examples/`  
  
### 예제 카탈로그

**총 5개 예제 파일 (플랫 구조)**

번호 | 예제 파일 | 설명 | Layer
---|---|---|---
01 | `01_quality_metrics.py` | 품질 지표 — Accuracy, Hallucination, Response Quality, RAG | Layer 1
02 | `02_performance_metrics.py` | 성능 지표 — TCR, Latency (p50/p95/p99), Token Economy | Layer 1
03 | `03_agentic_metrics.py` | 에이전틱 지표 — Tool Call, Coordination, Workflow, Retry | Layer 2
04 | `04_security_metrics.py` | 보안 지표 — Input Sanitization, Leakage, Auth, Escalation, Attack | Layer 2
05 | `05_hybrid_metrics.py` | 하이브리드 평가 — DeepEval, Ragas, LangSmith 통합 | Layer 3  
  
* * *

## 📄 라이센스

이 프로젝트는 MIT 라이센스를 따릅니다. 자세한 내용은 [LICENSE](<LICENSE>) 파일을 참조하세요.

**Agent Evaluator v0.6.0**

100% Zero Configuration | 3-Layer Metrics | Production-Ready

**최종 업데이트** : 2026-03-22 | **버전** : Agent Evaluator v0.6.0

Developed by **KIM SUNGWOO**

© 2024-2025 MIT License
